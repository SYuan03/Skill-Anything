"""Quiz generator — create diverse, high-value quiz questions from knowledge chunks.

Generates 6 types of questions:
- multiple_choice: Standard 4-option MCQ
- true_false: Statement judgment
- fill_blank: Key term/concept recall
- short_answer: Open-ended comprehension
- scenario: Apply knowledge to a real situation
- comparison: Compare/contrast two concepts
"""

from __future__ import annotations

import json
import logging
import re

from skill_anything.models import Difficulty, KnowledgeChunk, QuestionType, QuizQuestion

log = logging.getLogger(__name__)

_QUIZ_PROMPT = """\
You are an expert assessment designer creating questions that test deep \
understanding, not just surface recall. Generate {count} high-quality questions \
from the content below.

**Use a mix of these 6 question types:**

1. **multiple_choice** — 4 options, only one correct. Distractors must be \
plausible (no obviously wrong answers).
2. **true_false** — A precise statement to evaluate. Answer must be "True" or "False".
3. **fill_blank** — Test exact recall of a key term, value, or name.
4. **short_answer** — Requires 2-3 sentences. Tests comprehension and synthesis.
5. **scenario** — Present a realistic situation and ask what would happen or \
what approach to take. Include 4 options.
6. **comparison** — Ask the learner to compare/contrast two concepts, methods, \
or approaches. Tests analytical thinking.

**Quality requirements:**
- Difficulty distribution: 20% easy, 50% medium, 30% hard
- Every question must have a thorough explanation (explain *why*, not just restate)
- Scenario questions must include a concrete, detailed situation
- Comparison questions should require genuine analysis
- Only multiple_choice and scenario types need the "options" field

Content:
{content}

Output ONLY a valid JSON array:

[
  {{
    "question": "Question text (scenario questions include the situation description)",
    "type": "multiple_choice|true_false|fill_blank|short_answer|scenario|comparison",
    "options": ["A. ...", "B. ...", "C. ...", "D. ..."],
    "answer": "The correct answer (for short_answer/scenario/comparison, give a reference answer)",
    "explanation": "Detailed explanation of why this is correct and the underlying reasoning",
    "difficulty": "easy|medium|hard"
  }}
]
"""


class QuizGenerator:
    """Generate diverse quiz questions from knowledge chunks using LLM."""

    def generate(
        self,
        chunks: list[KnowledgeChunk],
        *,
        count_per_chunk: int = 4,
        max_questions: int = 40,
    ) -> list[QuizQuestion]:
        try:
            from skill_anything.llm import chat, is_available

            if not is_available():
                return self._generate_offline(chunks, max_questions)
        except ImportError:
            return self._generate_offline(chunks, max_questions)

        questions: list[QuizQuestion] = []

        for chunk in chunks:
            if len(questions) >= max_questions:
                break

            remaining = min(count_per_chunk, max_questions - len(questions))
            prompt = _QUIZ_PROMPT.format(
                count=remaining,
                content=chunk.content[:3000],
            )

            raw = chat(
                [{"role": "user", "content": prompt}],
                temperature=0.4,
                max_tokens=4096,
            )

            if raw is None:
                continue

            parsed = self._parse_response(raw)
            for q in parsed:
                q.source_chunk = chunk.chunk_index
                questions.append(q)

        return questions[:max_questions]

    @staticmethod
    def _parse_response(raw: str) -> list[QuizQuestion]:
        raw = raw.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```\w*\n?", "", raw)
            raw = re.sub(r"\n?```$", "", raw)

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            match = re.search(r"\[.*\]", raw, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group())
                except json.JSONDecodeError:
                    return []
            else:
                return []

        if not isinstance(data, list):
            return []

        questions: list[QuizQuestion] = []
        for item in data:
            if not isinstance(item, dict) or "question" not in item:
                continue

            q_type = item.get("type", "multiple_choice")
            try:
                question_type = QuestionType(q_type)
            except ValueError:
                question_type = QuestionType.MULTIPLE_CHOICE

            diff = item.get("difficulty", "medium")
            try:
                difficulty = Difficulty(diff)
            except ValueError:
                difficulty = Difficulty.MEDIUM

            questions.append(
                QuizQuestion(
                    question=item["question"],
                    options=item.get("options", []),
                    answer=item.get("answer", ""),
                    explanation=item.get("explanation", ""),
                    difficulty=difficulty,
                    question_type=question_type,
                )
            )

        return questions

    @staticmethod
    def _generate_offline(
        chunks: list[KnowledgeChunk], max_questions: int
    ) -> list[QuizQuestion]:
        """Fallback: generate basic comprehension questions without LLM."""
        questions: list[QuizQuestion] = []

        for chunk in chunks:
            if len(questions) >= max_questions:
                break

            sentences = [s.strip() for s in chunk.content.split(".") if len(s.strip()) > 30]

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
                    )
                )

        return questions
