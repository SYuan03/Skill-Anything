"""Core data models for Skill-Anything.

Defines the data structures that flow through the pipeline:
  Source → KnowledgeChunk[] → SkillPack (notes, quiz, flashcards, exercises, ...)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SourceType(str, Enum):
    PDF = "pdf"
    VIDEO = "video"
    WEBPAGE = "webpage"
    TEXT = "text"
    AUDIO = "audio"
    REPO = "repo"
    SKILL = "skill"


class Difficulty(str, Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class QuestionType(str, Enum):
    MULTIPLE_CHOICE = "multiple_choice"
    TRUE_FALSE = "true_false"
    FILL_BLANK = "fill_blank"
    SHORT_ANSWER = "short_answer"
    SCENARIO = "scenario"
    COMPARISON = "comparison"


# ======================================================================
# Knowledge extraction
# ======================================================================


@dataclass
class KnowledgeChunk:
    """A piece of extracted knowledge from a source."""

    content: str
    section: str = ""
    chunk_index: int = 0
    source_page: int | None = None
    source_time: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        label = self.section or f"chunk-{self.chunk_index}"
        return f"[{label}] {self.content[:80]}..."


@dataclass
class GlossaryEntry:
    """A term and its definition extracted from the content."""

    term: str
    definition: str
    related_terms: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"term": self.term, "definition": self.definition}
        if self.related_terms:
            d["related_terms"] = self.related_terms
        return d


@dataclass
class TimelineEntry:
    """A point in the content timeline (timestamp for video, page for PDF, section for text)."""

    position: str
    title: str
    summary: str

    def to_dict(self) -> dict[str, Any]:
        return {"position": self.position, "title": self.title, "summary": self.summary}


# ======================================================================
# Interactive outputs
# ======================================================================


@dataclass
class QuizQuestion:
    """A single quiz question generated from knowledge."""

    question: str
    options: list[str] = field(default_factory=list)
    answer: str = ""
    explanation: str = ""
    difficulty: Difficulty = Difficulty.MEDIUM
    question_type: QuestionType = QuestionType.MULTIPLE_CHOICE
    source_chunk: int = 0

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "question": self.question,
            "answer": self.answer,
            "explanation": self.explanation,
            "difficulty": self.difficulty.value,
            "type": self.question_type.value,
        }
        if self.options:
            d["options"] = self.options
        return d


@dataclass
class Flashcard:
    """A flashcard for spaced-repetition review."""

    front: str
    back: str
    tags: list[str] = field(default_factory=list)
    source_chunk: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {"front": self.front, "back": self.back, "tags": self.tags}


@dataclass
class PracticeExercise:
    """A hands-on practice exercise."""

    title: str
    description: str
    difficulty: Difficulty = Difficulty.MEDIUM
    hints: list[str] = field(default_factory=list)
    solution: str = ""
    exercise_type: str = "open_ended"

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "title": self.title,
            "description": self.description,
            "difficulty": self.difficulty.value,
            "type": self.exercise_type,
        }
        if self.hints:
            d["hints"] = self.hints
        if self.solution:
            d["solution"] = self.solution
        return d


# ======================================================================
# SkillPack — the complete output
# ======================================================================


@dataclass
class SkillPack:
    """Complete output of skill generation from a knowledge source.

    This is the main deliverable — a comprehensive learning package that includes
    structured notes, quizzes, flashcards, exercises, glossary, and more.
    """

    title: str
    source_type: SourceType
    source_ref: str

    # --- Knowledge ---
    summary: str = ""
    detailed_notes: str = ""
    key_concepts: list[str] = field(default_factory=list)
    glossary: list[GlossaryEntry] = field(default_factory=list)
    timeline: list[TimelineEntry] = field(default_factory=list)
    cheat_sheet: str = ""
    takeaways: list[str] = field(default_factory=list)
    learning_path: dict[str, list[str]] = field(default_factory=dict)

    # --- Interactive ---
    quiz_questions: list[QuizQuestion] = field(default_factory=list)
    flashcards: list[Flashcard] = field(default_factory=list)
    practice_exercises: list[PracticeExercise] = field(default_factory=list)

    # --- Meta ---
    chunks: list[KnowledgeChunk] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "source_type": self.source_type.value,
            "source_ref": self.source_ref,
            "summary": self.summary,
            "detailed_notes": self.detailed_notes,
            "key_concepts": self.key_concepts,
            "glossary": [g.to_dict() for g in self.glossary],
            "timeline": [t.to_dict() for t in self.timeline],
            "cheat_sheet": self.cheat_sheet,
            "takeaways": self.takeaways,
            "learning_path": self.learning_path,
            "quiz_questions": [q.to_dict() for q in self.quiz_questions],
            "flashcards": [f.to_dict() for f in self.flashcards],
            "practice_exercises": [e.to_dict() for e in self.practice_exercises],
            "metadata": self.metadata,
        }

    @property
    def stats(self) -> dict[str, int]:
        return {
            "key_concepts": len(self.key_concepts),
            "glossary": len(self.glossary),
            "timeline": len(self.timeline),
            "quiz_questions": len(self.quiz_questions),
            "flashcards": len(self.flashcards),
            "exercises": len(self.practice_exercises),
            "takeaways": len(self.takeaways),
        }


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60] or "skill-pack"
