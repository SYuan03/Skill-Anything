"""Practice exercise generator — section-aware, quota-balanced (v0.3).

v0.2 concatenated *all* chunks into a single 10k-char-truncated prompt and
asked for len(chunks) exercises in one shot — guaranteed to fail on long
sources both because input was truncated and because output would exceed
max_tokens. v0.3 generates 1-2 exercises per section concurrently.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from skill_anything.generators._budget import allocate_quota
from skill_anything.generators._concurrent import LLMCache, cache_key, map_llm, resolve_fast_model
from skill_anything.models import Difficulty, KnowledgeChunk, PracticeExercise, Section

log = logging.getLogger(__name__)

PRACTICE_PROMPT_VERSION = "v0.4-grounded"

_EXERCISE_PROMPT = """\
You are an expert course designer. Create {count} hands-on exercises based on the section below \
(titled "{section_title}"). These are NOT quiz questions — they are tasks that ask the learner \
to actively apply, build, or analyse something.

Ground every exercise and reference solution in the supplied section. A task
may ask the learner to apply an idea, but it must not assume tools, facts, or
constraints absent from the source.

**Exercise types:**
- **analysis**: Given a case/dataset/situation, analyze and draw conclusions
- **design**: Design a system, architecture, workflow, or solution
- **implementation**: Build, code, or construct something concrete
- **critique**: Evaluate an existing approach — strengths, weaknesses, improvements
- **research**: Investigate a topic and synthesize findings

**Requirements:**
- Each exercise has a clear, detailed description with specific deliverables
- Include 1-3 helpful hints
- Provide a reference solution or key solution points
- Vary difficulty across easy/medium/hard

Section content:
{content}

Output ONLY a valid JSON array:

[
  {{
    "title": "Exercise title",
    "description": "Detailed task description",
    "type": "analysis|design|implementation|critique|research",
    "difficulty": "easy|medium|hard",
    "hints": ["Hint 1: ...", "Hint 2: ..."],
    "solution": "Reference solution or key points"
  }}
]
"""


class PracticeGenerator:
    """Generate practice exercises per section with a balanced global quota."""

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

    def generate(
        self,
        sections_or_chunks: list,
        *,
        total: int = 10,
        count_per_chunk: int | None = None,
        max_exercises: int | None = None,
    ) -> list[PracticeExercise]:
        if max_exercises is not None:
            total = max_exercises
        elif count_per_chunk is not None:
            n = len(sections_or_chunks) if sections_or_chunks else 1
            total = min(count_per_chunk * n, 15)

        sections = self._coerce_sections(sections_or_chunks)
        if not sections:
            return []

        try:
            from skill_anything.llm import is_available
            if not is_available():
                return self._generate_offline(
                    [c for s in sections for c in s.chunks], total,
                )
        except ImportError:
            return self._generate_offline(
                [c for s in sections for c in s.chunks], total,
            )

        quotas = allocate_quota(sections, total, min_per_section=1)
        return self._generate_with_llm(sections, quotas)

    def _generate_with_llm(
        self, sections: list[Section], quotas: dict[str, int],
    ) -> list[PracticeExercise]:
        from skill_anything.llm import chat

        fast_model = resolve_fast_model(self.fast_model)
        cache = LLMCache(self.cache_dir / "practice" if self.cache_dir else None)
        targets = [s for s in sections if quotas.get(s.id, 0) > 0]

        def per_section(section: Section) -> list[dict] | None:
            n = quotas.get(section.id, 0)
            prompt = _EXERCISE_PROMPT.format(
                count=n,
                section_title=section.title,
                content=section.content[:5000],
            )
            raw = chat(
                [{"role": "user", "content": prompt}],
                temperature=0.4,
                max_tokens=2560,
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
                _EXERCISE_PROMPT.format(
                    count=quotas.get(s.id, 0),
                    section_title=s.title,
                    content=s.content[:5000],
                ),
                fast_model,
                PRACTICE_PROMPT_VERSION,
            ),
            label=f"Exercises [{fast_model}]",
        )

        exercises: list[PracticeExercise] = []
        for _, items in zip(targets, results):
            if not items:
                continue
            for item in items:
                ex = self._item_to_exercise(item)
                if ex is not None:
                    exercises.append(ex)
        if exercises:
            return exercises
        log.warning("All exercise calls failed; using offline fallback")
        return self._generate_offline(
            [chunk for section in sections for chunk in section.chunks], sum(quotas.values())
        )

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
        return data if isinstance(data, list) else []

    @staticmethod
    def _item_to_exercise(item: dict) -> PracticeExercise | None:
        if not isinstance(item, dict) or not item.get("title"):
            return None
        try:
            difficulty = Difficulty(item.get("difficulty", "medium"))
        except ValueError:
            difficulty = Difficulty.MEDIUM
        return PracticeExercise(
            title=item["title"],
            description=item.get("description", ""),
            difficulty=difficulty,
            hints=item.get("hints", []),
            solution=item.get("solution", ""),
            exercise_type=item.get("type", "open_ended"),
        )

    @staticmethod
    def _parse_response(raw: str) -> list[PracticeExercise]:
        items = PracticeGenerator._parse_response_raw(raw)
        out: list[PracticeExercise] = []
        for item in items:
            ex = PracticeGenerator._item_to_exercise(item)
            if ex is not None:
                out.append(ex)
        return out

    @staticmethod
    def _generate_offline(
        chunks: list[KnowledgeChunk], max_exercises: int
    ) -> list[PracticeExercise]:
        exercises: list[PracticeExercise] = []
        for chunk in chunks:
            if len(exercises) >= max_exercises:
                break
            section = chunk.section or f"Section {chunk.chunk_index + 1}"
            exercises.append(
                PracticeExercise(
                    title=f'Summarize the key ideas of "{section}"',
                    description=f'Review the content of "{section}" and produce: '
                    f"(1) 3-5 core concepts with brief explanations, "
                    f"(2) a paragraph connecting them together, "
                    f"(3) one real-world application example.",
                    difficulty=Difficulty.MEDIUM,
                    hints=[
                        "Read through the content and highlight key terms",
                        "Try to explain the ideas without looking at the source",
                        "Think about where this knowledge applies in practice",
                    ],
                    exercise_type="analysis",
                )
            )
        return exercises
