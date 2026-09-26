"""Quiz generator — section-aware, quota-balanced (v0.3).

v0.2 looped per-chunk with a hard max_questions=40 cap, which meant a 500-page
book hit the cap inside chapter 1 and produced zero questions for the rest.
v0.3 allocates a quota per section weighted by section size with a per-section
minimum, then fans out concurrent LLM calls with disk-cached results.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from skill_anything.generators._budget import allocate_quota
from skill_anything.generators._concurrent import LLMCache, cache_key, map_llm, resolve_fast_model
from skill_anything.grounding import (
    citation_for_chunk,
    citation_from_evidence,
    dedupe_by_text,
    split_sections_for_generation,
)
from skill_anything.models import Difficulty, KnowledgeChunk, QuestionType, QuizQuestion, Section

log = logging.getLogger(__name__)

QUIZ_PROMPT_VERSION = "v0.4.1-evidence"

_QUIZ_PROMPT = """\
You are an expert assessment designer creating questions that test deep \
understanding, not just surface recall. Generate {count} high-quality questions \
from the section below (titled "{section_title}").

Every question and answer must be supported by the section text alone. Do not
invent facts, tools, scenarios, constraints, or recommended behavior. If the
section is short, favor direct recall/comprehension and avoid artificial detail.

**Use a mix of these 6 question types when the requested count allows:**

1. **multiple_choice** — 4 options, only one correct. Distractors must be \
plausible (no obviously wrong answers).
2. **true_false** — A precise statement to evaluate. Answer must be "True" or "False".
3. **fill_blank** — Test exact recall of a key term, value, or name.
4. **short_answer** — Requires 2-3 sentences. Tests comprehension and synthesis.
5. **scenario** — Present a realistic situation and ask what would happen or \
what approach to take. Include 4 options.
6. **comparison** — Ask the learner to compare/contrast two concepts, methods, \
or approaches.

**Quality requirements:**
- Difficulty distribution: 20% easy, 50% medium, 30% hard
- Every question must have a thorough explanation (explain *why*, not just restate)
- Only multiple_choice and scenario types need the "options" field
- Include one short verbatim quote from the section in "evidence". Copy it
  exactly; the item will be rejected if the quote cannot be found in the source.

Section content:
{content}

Output ONLY a valid JSON array:

[
  {{
    "question": "...",
    "type": "multiple_choice|true_false|fill_blank|short_answer|scenario|comparison",
    "options": ["A. ...", "B. ...", "C. ...", "D. ..."],
    "answer": "...",
    "explanation": "...",
    "difficulty": "easy|medium|hard",
    "evidence": "An exact supporting quote copied from the section"
  }}
]
"""


class QuizGenerator:
    """Generate quiz questions per section with a balanced global quota."""

    def __init__(
        self,
        *,
        cache_dir: Path | None = None,
        concurrency: int = 4,
        fast_model: str | None = None,
    ) -> None:
        self.cache_dir = cache_dir
        self.concurrency = concurrency
        self.fast_model = fast_model
        self.diagnostics: dict[str, int | str] = {"mode": "not-run", "requested": 0, "accepted": 0, "rejected": 0}

    def generate(
        self,
        sections_or_chunks: list,
        *,
        total: int = 30,
        count_per_chunk: int | None = None,
        max_questions: int | None = None,
    ) -> list[QuizQuestion]:
        # Back-compat: callers that pass count_per_chunk/max_questions get the
        # legacy total budget = max_questions (or len * count_per_chunk).
        if max_questions is not None:
            total = max_questions
        elif count_per_chunk is not None:
            n = len(sections_or_chunks) if sections_or_chunks else 1
            total = min(count_per_chunk * n, 40)

        sections = split_sections_for_generation(
            self._coerce_sections(sections_or_chunks), max_chars=5000,
        )
        self.diagnostics = {"mode": "not-run", "requested": total, "accepted": 0, "rejected": 0}
        if not sections:
            return []

        try:
            from skill_anything.llm import is_available
            if not is_available():
                output = self._generate_offline(
                    [c for s in sections for c in s.chunks], total,
                )
                self.diagnostics.update(mode="offline", accepted=len(output))
                return output
        except ImportError:
            output = self._generate_offline(
                [c for s in sections for c in s.chunks], total,
            )
            self.diagnostics.update(mode="offline", accepted=len(output))
            return output

        quotas = allocate_quota(sections, total, min_per_section=1)
        return self._generate_with_llm(sections, quotas)

    def _generate_with_llm(
        self, sections: list[Section], quotas: dict[str, int],
    ) -> list[QuizQuestion]:
        from skill_anything.llm import chat

        fast_model = resolve_fast_model(self.fast_model)
        cache = LLMCache(self.cache_dir / "quiz" if self.cache_dir else None)

        # Skip sections with quota 0.
        targets = [s for s in sections if quotas.get(s.id, 0) > 0]

        def per_section(section: Section) -> list[dict] | None:
            n = quotas.get(section.id, 0)
            prompt = _QUIZ_PROMPT.format(
                count=n,
                section_title=section.title,
                content=section.content[:5000],
            )
            raw = chat(
                [{"role": "user", "content": prompt}],
                temperature=0.4,
                max_tokens=3072,
                model=fast_model,
            )
            if raw is None:
                return None
            return self._parse_response_raw(raw)

        results = map_llm(
            targets,
            per_section,
            concurrency=self.concurrency,
            cache=cache,
            key_fn=lambda s: cache_key(
                _QUIZ_PROMPT.format(
                    count=quotas.get(s.id, 0),
                    section_title=s.title,
                    content=s.content[:5000],
                ),
                fast_model,
                QUIZ_PROMPT_VERSION,
            ),
            label=f"Quiz [{fast_model}]",
        )

        questions: list[QuizQuestion] = []
        rejected = 0
        for section, items in zip(targets, results):
            if not items:
                continue
            requested = quotas.get(section.id, 0)
            section_questions: list[QuizQuestion] = []
            for item in items:
                q = self._item_to_question(item)
                citation = citation_from_evidence(section, item.get("evidence"))
                if q is None or citation is None or not self._is_well_formed(q):
                    rejected += 1
                    continue
                q.citation = citation
                q.source_chunk = citation.chunk_index or 0
                section_questions.append(q)
            unique = dedupe_by_text(section_questions, lambda item: item.question)
            questions.extend(unique[:requested])
            rejected += len(section_questions) - min(len(unique), requested)
        if questions:
            output = dedupe_by_text(questions, lambda item: item.question)[:sum(quotas.values())]
            rejected += len(questions) - len(output)
            self.diagnostics.update(mode="llm", accepted=len(output), rejected=rejected)
            return output
        log.warning("All quiz calls failed; using offline fallback")
        output = self._generate_offline(
            [chunk for section in sections for chunk in section.chunks], sum(quotas.values())
        )
        self.diagnostics.update(mode="offline-fallback", accepted=len(output), rejected=rejected)
        return output

    # ------------------------------------------------------------------
    # Parsing helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _coerce_sections(items: list) -> list[Section]:
        from skill_anything.generators.knowledge_gen import KnowledgeGenerator
        return KnowledgeGenerator._coerce_sections(items)

    @staticmethod
    def _parse_response_raw(raw: str) -> list[dict]:
        raw = raw.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```\w*\n?", "", raw)
            raw = re.sub(r"\n?```$", "", raw)
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            match = re.search(r"\[.*\]", raw, re.DOTALL)
            if not match:
                return []
            try:
                data = json.loads(match.group())
            except json.JSONDecodeError:
                return []
        if not isinstance(data, list):
            return []
        return [item for item in data if isinstance(item, dict) and "question" in item]

    @staticmethod
    def _item_to_question(item: dict) -> QuizQuestion | None:
        if not isinstance(item, dict):
            return None
        question = item.get("question")
        if not isinstance(question, str) or not question.strip():
            return None
        try:
            question_type = QuestionType(str(item.get("type", "multiple_choice")))
        except ValueError:
            question_type = QuestionType.MULTIPLE_CHOICE
        try:
            difficulty = Difficulty(str(item.get("difficulty", "medium")))
        except ValueError:
            difficulty = Difficulty.MEDIUM
        raw_options = item.get("options", [])
        options = (
            [str(option).strip() for option in raw_options if str(option).strip()]
            if isinstance(raw_options, list)
            else []
        )
        return QuizQuestion(
            question=question.strip(),
            options=options,
            answer=str(item.get("answer", "")).strip(),
            explanation=str(item.get("explanation", "")).strip(),
            difficulty=difficulty,
            question_type=question_type,
        )

    @staticmethod
    def _is_well_formed(question: QuizQuestion) -> bool:
        if not question.answer.strip() or not question.explanation.strip():
            return False
        if question.question_type in {
            QuestionType.MULTIPLE_CHOICE,
            QuestionType.SCENARIO,
        }:
            options = question.options
            if len(options) != 4 or len({option.casefold() for option in options}) != 4:
                return False
        if question.question_type == QuestionType.TRUE_FALSE:
            return question.answer.strip().casefold() in {"true", "false"}
        return True

    # Back-compat for tests calling QuizGenerator._parse_response(raw)
    @staticmethod
    def _parse_response(raw: str) -> list[QuizQuestion]:
        items = QuizGenerator._parse_response_raw(raw)
        out: list[QuizQuestion] = []
        for item in items:
            q = QuizGenerator._item_to_question(item)
            if q is not None:
                out.append(q)
        return out

    # ------------------------------------------------------------------
    # Offline fallback (unchanged behaviour, takes total as cap)
    # ------------------------------------------------------------------

    @staticmethod
    def _generate_offline(
        chunks: list[KnowledgeChunk], max_questions: int
    ) -> list[QuizQuestion]:
        questions: list[QuizQuestion] = []
        for chunk in chunks:
            if len(questions) >= max_questions:
                break
            sentences = [s.strip() for s in chunk.content.split(".") if len(s.strip()) >= 15]
            for sentence in sentences[:2]:
                if len(questions) >= max_questions:
                    break
                questions.append(
                    QuizQuestion(
                        question=f'Which of the following best describes this statement?\n"{sentence[:120]}"',
                        options=[
                            "A. The statement above is accurate",
                            "B. The statement above is inaccurate",
                            "C. Cannot be determined",
                            "D. None of the above",
                        ],
                        answer="A. The statement above is accurate",
                        explanation=f"Source: {sentence[:150]}",
                        difficulty=Difficulty.EASY,
                        question_type=QuestionType.MULTIPLE_CHOICE,
                        source_chunk=chunk.chunk_index,
                        citation=citation_for_chunk(chunk, sentence),
                    )
                )
        return questions
