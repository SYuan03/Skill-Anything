"""Skill parser — import a SKILL.md directory back into a SkillPack."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from skill_anything.models import (
    Difficulty,
    Flashcard,
    GlossaryEntry,
    KnowledgeChunk,
    PracticeExercise,
    QuestionType,
    QuizQuestion,
    SkillPack,
    SourceType,
)
from skill_anything.parsers.base import BaseParser


class SkillParser(BaseParser):
    """Import a SKILL.md directory into an internal SkillPack."""

    source_type = SourceType.SKILL

    def parse(self, source: str) -> list[KnowledgeChunk]:
        return self.parse_pack(source).chunks

    def parse_pack(self, source: str) -> SkillPack:
        skill_root = self.resolve_skill_root(source)
        skill_md = skill_root / "SKILL.md"
        content = skill_md.read_text(encoding="utf-8")
        frontmatter, body = self._split_frontmatter(content)

        heading_title = self._extract_h1(body)
        title = self._resolve_title(frontmatter, heading_title, skill_root.name)
        summary = self._extract_section(body, "Overview")
        cheat_sheet = self._extract_section(body, "Cheat Sheet")
        key_concepts = self._parse_list_section(self._extract_section(body, "Key Concepts"))
        takeaways = self._parse_list_section(self._extract_section(body, "Takeaways"))

        detailed_notes = self._read_reference(skill_root / "references" / "detailed-notes.md")
        glossary = self._parse_glossary_reference(skill_root / "references" / "glossary.md")
        learning_path = self._parse_learning_path(skill_root / "references" / "learning-path.md")

        quiz_questions = self._parse_quiz_questions(skill_root / "assets" / "quiz.yaml")
        flashcards = self._parse_flashcards(skill_root / "assets" / "flashcards.yaml")
        exercises = self._parse_exercises(skill_root / "assets" / "exercises.yaml")

        chunks = self._build_chunks(
            summary,
            detailed_notes,
            key_concepts,
            cheat_sheet,
            takeaways,
            learning_path,
        )

        metadata = {
            "imported_from": str(skill_root),
            "skill_root": str(skill_root),
            "skill_name": frontmatter.get("name", ""),
            "reference_files": [
                path.name for path in (skill_root / "references").glob("*")
                if path.is_file()
            ] if (skill_root / "references").exists() else [],
            "asset_files": [
                path.name for path in (skill_root / "assets").glob("*")
                if path.is_file()
            ] if (skill_root / "assets").exists() else [],
        }

        return SkillPack(
            title=title,
            source_type=SourceType.SKILL,
            source_ref=str(skill_root),
            summary=summary,
            detailed_notes=detailed_notes,
            key_concepts=key_concepts,
            glossary=glossary,
            cheat_sheet=cheat_sheet,
            takeaways=takeaways,
            learning_path=learning_path,
            quiz_questions=quiz_questions,
            flashcards=flashcards,
            practice_exercises=exercises,
            chunks=chunks,
            metadata=metadata,
        )

    @staticmethod
    def resolve_skill_root(source: str) -> Path:
        path = Path(source)
        if path.is_file() and path.name == "SKILL.md":
            return path.parent
        if path.is_dir() and (path / "SKILL.md").exists():
            return path
        raise FileNotFoundError(f"SKILL.md not found at: {source}")

    @staticmethod
    def _split_frontmatter(content: str) -> tuple[dict[str, Any], str]:
        if not content.startswith("---\n"):
            return {}, content

        match = re.match(r"^---\n(.*?)\n---\n?(.*)$", content, flags=re.DOTALL)
        if not match:
            return {}, content

        raw_frontmatter, body = match.groups()
        data = yaml.safe_load(raw_frontmatter) or {}
        if not isinstance(data, dict):
            raise ValueError("SKILL.md frontmatter must be a mapping")
        return data, body

    @staticmethod
    def _resolve_title(frontmatter: dict[str, Any], heading_title: str | None, dir_name: str) -> str:
        raw_name = str(frontmatter.get("name", "")).strip()
        if raw_name:
            return raw_name.replace("-", " ").replace("_", " ").strip().title()
        if heading_title:
            return heading_title.strip()
        return dir_name.replace("-", " ").replace("_", " ").strip().title()

    @staticmethod
    def _extract_h1(body: str) -> str | None:
        match = re.search(r"^#\s+(.+)$", body, flags=re.MULTILINE)
        return match.group(1).strip() if match else None

    @staticmethod
    def _extract_section(body: str, title: str) -> str:
        pattern = rf"^##\s+{re.escape(title)}\s*$\n?(.*?)(?=^##\s+|\Z)"
        match = re.search(pattern, body, flags=re.DOTALL | re.MULTILINE)
        return match.group(1).strip() if match else ""

    @staticmethod
    def _parse_list_section(section: str) -> list[str]:
        items: list[str] = []
        for line in section.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            stripped = re.sub(r"^\d+\.\s*", "", stripped)
            stripped = re.sub(r"^[-*]\s*", "", stripped)
            if stripped:
                items.append(stripped)
        return items

    @staticmethod
    def _read_reference(path: Path) -> str:
        if not path.exists():
            return ""
        content = path.read_text(encoding="utf-8").strip()
        return re.sub(r"^#\s+.*?\n+", "", content, count=1).strip()

    @staticmethod
    def _parse_glossary_reference(path: Path) -> list[GlossaryEntry]:
        if not path.exists():
            return []

        glossary: list[GlossaryEntry] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped.startswith("|") or stripped.startswith("|:") or "Term" in stripped:
                continue
            columns = [col.strip() for col in stripped.strip("|").split("|")]
            if len(columns) < 2:
                continue
            term = columns[0].replace("**", "").strip()
            definition = columns[1].strip()
            related_terms = []
            if len(columns) > 2 and columns[2] not in {"", "—", "-"}:
                related_terms = [item.strip() for item in columns[2].split(",") if item.strip()]
            if term:
                glossary.append(
                    GlossaryEntry(term=term, definition=definition, related_terms=related_terms)
                )
        return glossary

    def _parse_learning_path(self, path: Path) -> dict[str, list[str]]:
        if not path.exists():
            return {}

        content = path.read_text(encoding="utf-8")
        mapping = {
            "prerequisites": "Prerequisites",
            "next_steps": "Next Steps",
            "resources": "Recommended Resources",
        }
        output: dict[str, list[str]] = {}
        for key, heading in mapping.items():
            items = self._parse_list_section(self._extract_section(content, heading))
            if items:
                output[key] = items
        return output

    @staticmethod
    def _load_yaml_list(path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or []
        if not isinstance(data, list):
            raise ValueError(f"Expected a YAML list in {path}")
        for item in data:
            if not isinstance(item, dict):
                raise ValueError(f"Expected a list of objects in {path}")
        return data

    def _parse_quiz_questions(self, path: Path) -> list[QuizQuestion]:
        questions = []
        for item in self._load_yaml_list(path):
            questions.append(
                QuizQuestion(
                    question=item["question"],
                    options=item.get("options", []),
                    answer=item.get("answer", ""),
                    explanation=item.get("explanation", ""),
                    difficulty=Difficulty(item.get("difficulty", "medium")),
                    question_type=QuestionType(item.get("type", "multiple_choice")),
                )
            )
        return questions

    def _parse_flashcards(self, path: Path) -> list[Flashcard]:
        cards = []
        for item in self._load_yaml_list(path):
            cards.append(
                Flashcard(
                    front=item["front"],
                    back=item["back"],
                    tags=item.get("tags", []),
                )
            )
        return cards

    def _parse_exercises(self, path: Path) -> list[PracticeExercise]:
        exercises = []
        for item in self._load_yaml_list(path):
            exercises.append(
                PracticeExercise(
                    title=item["title"],
                    description=item["description"],
                    difficulty=Difficulty(item.get("difficulty", "medium")),
                    hints=item.get("hints", []),
                    solution=item.get("solution", ""),
                    exercise_type=item.get("type", "open_ended"),
                )
            )
        return exercises

    def _build_chunks(
        self,
        summary: str,
        detailed_notes: str,
        key_concepts: list[str],
        cheat_sheet: str,
        takeaways: list[str],
        learning_path: dict[str, list[str]],
    ) -> list[KnowledgeChunk]:
        sections = [
            ("Overview", summary),
            ("Detailed Notes", detailed_notes),
            ("Key Concepts", "\n".join(key_concepts)),
            ("Cheat Sheet", cheat_sheet),
            ("Takeaways", "\n".join(takeaways)),
            (
                "Learning Path",
                "\n".join(
                    f"{key}: {', '.join(items)}"
                    for key, items in learning_path.items()
                ),
            ),
        ]

        chunks: list[KnowledgeChunk] = []
        index = 0
        for section, text in sections:
            if not text.strip():
                continue
            for chunk in self._split_into_chunks(text, max_chars=1800, overlap=120):
                chunks.append(KnowledgeChunk(content=chunk, section=section, chunk_index=index))
                index += 1
        return chunks
