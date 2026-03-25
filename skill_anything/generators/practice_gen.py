"""Practice exercise generator — create hands-on exercises from knowledge chunks.

Unlike quiz questions (which test recall), exercises ask the learner to
*apply* knowledge: design something, analyze a case, solve a problem,
write/code something, or make a decision.
"""

from __future__ import annotations

import json
import logging
import re

from skill_anything.models import Difficulty, KnowledgeChunk, PracticeExercise

log = logging.getLogger(__name__)

_EXERCISE_PROMPT = """\
You are an expert course designer. Create {count} high-quality hands-on \
exercises based on the content below.

**These are NOT quiz questions.** They are tasks that require the learner to \
actively apply, build, or analyze something.

**Exercise types:**
- **analysis**: Given a case/dataset/situation, analyze and draw conclusions
- **design**: Design a system, architecture, workflow, or solution
- **implementation**: Build, code, or construct something concrete
- **critique**: Evaluate an existing approach — identify strengths, weaknesses, improvements
- **research**: Investigate a topic and synthesize findings

**Requirements:**
- Each exercise has a clear, detailed description with specific deliverables
- Include 1-3 helpful hints to get started
- Provide a reference solution or key solution points
- Distribute difficulty across easy/medium/hard

Content:
{content}

Output ONLY a valid JSON array:

[
  {{
    "title": "Exercise title",
    "description": "Detailed task description including context, requirements, and expected output",
    "type": "analysis|design|implementation|critique|research",
    "difficulty": "easy|medium|hard",
    "hints": ["Hint 1: ...", "Hint 2: ..."],
    "solution": "Reference solution or key points of the answer"
  }}
]
"""


class PracticeGenerator:
    """Generate hands-on practice exercises from knowledge chunks."""

    def generate(
        self,
        chunks: list[KnowledgeChunk],
        *,
        count_per_chunk: int = 1,
        max_exercises: int = 10,
    ) -> list[PracticeExercise]:
        try:
            from skill_anything.llm import chat, is_available

            if not is_available():
                return self._generate_offline(chunks, max_exercises)
        except ImportError:
            return self._generate_offline(chunks, max_exercises)

        combined = "\n\n---\n\n".join(c.content for c in chunks)
        if len(combined) > 10000:
            combined = combined[:10000] + "\n\n[... truncated ...]"

        total = min(len(chunks) * count_per_chunk, max_exercises)
        prompt = _EXERCISE_PROMPT.format(count=total, content=combined)

        raw = chat(
            [{"role": "user", "content": prompt}],
            temperature=0.4,
            max_tokens=4096,
        )

        if raw is None:
            return self._generate_offline(chunks, max_exercises)

        return self._parse_response(raw)[:max_exercises]

    @staticmethod
    def _parse_response(raw: str) -> list[PracticeExercise]:
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

        exercises: list[PracticeExercise] = []
        for item in data:
            if not isinstance(item, dict) or not item.get("title"):
                continue

            diff = item.get("difficulty", "medium")
            try:
                difficulty = Difficulty(diff)
            except ValueError:
                difficulty = Difficulty.MEDIUM

            exercises.append(
                PracticeExercise(
                    title=item["title"],
                    description=item.get("description", ""),
                    difficulty=difficulty,
                    hints=item.get("hints", []),
                    solution=item.get("solution", ""),
                    exercise_type=item.get("type", "open_ended"),
                )
            )

        return exercises

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
