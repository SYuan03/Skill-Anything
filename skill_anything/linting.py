"""Skill linting utilities."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from skill_anything.parsers.skill_parser import SkillParser


@dataclass
class LintIssue:
    level: str
    message: str
    path: str | None = None


@dataclass
class SkillLintResult:
    errors: list[LintIssue] = field(default_factory=list)
    warnings: list[LintIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


class SkillLinter:
    """Lint a SKILL.md directory for common packaging issues."""

    REQUIRED_FRONTMATTER = ("name", "description", "version")
    OPTIONAL_REFERENCES = ("references/detailed-notes.md", "references/glossary.md", "references/learning-path.md")
    OPTIONAL_ASSETS = ("assets/quiz.yaml", "assets/flashcards.yaml", "assets/exercises.yaml")

    def __init__(self) -> None:
        self.parser = SkillParser()

    def lint(self, source: str) -> SkillLintResult:
        result = SkillLintResult()

        try:
            skill_root = self.parser.resolve_skill_root(source)
        except FileNotFoundError as exc:
            result.errors.append(LintIssue(level="error", message=str(exc)))
            return result

        skill_md = skill_root / "SKILL.md"
        if not skill_md.exists():
            result.errors.append(LintIssue(level="error", message="Missing SKILL.md", path="SKILL.md"))
            return result

        content = skill_md.read_text(encoding="utf-8")
        try:
            frontmatter, body = self.parser._split_frontmatter(content)
        except Exception as exc:
            result.errors.append(LintIssue(level="error", message=f"Invalid frontmatter: {exc}", path="SKILL.md"))
            return result

        if not frontmatter:
            result.errors.append(LintIssue(level="error", message="Missing frontmatter block", path="SKILL.md"))
        else:
            for key in self.REQUIRED_FRONTMATTER:
                value = str(frontmatter.get(key, "")).strip()
                if not value:
                    result.errors.append(
                        LintIssue(level="error", message=f"Missing required frontmatter field: {key}", path="SKILL.md")
                    )

        self._check_referenced_files(skill_root, content, result)
        self._check_assets(skill_root, result)
        self._check_optional_files(skill_root, result)
        self._check_content_quality(body, result)
        self._check_quiz_script(skill_root, result)

        return result

    def _check_referenced_files(self, skill_root: Path, content: str, result: SkillLintResult) -> None:
        for match in re.findall(r"`((?:references|assets|scripts)/[^`]+)`", content):
            if not (skill_root / match).exists():
                result.errors.append(
                    LintIssue(level="error", message=f"Referenced file does not exist: {match}", path=match)
                )

    def _check_assets(self, skill_root: Path, result: SkillLintResult) -> None:
        validators = {
            "assets/quiz.yaml": self._validate_quiz_items,
            "assets/flashcards.yaml": self._validate_flashcard_items,
            "assets/exercises.yaml": self._validate_exercise_items,
        }

        for rel_path, validator in validators.items():
            path = skill_root / rel_path
            if not path.exists():
                continue
            try:
                data = yaml.safe_load(path.read_text(encoding="utf-8")) or []
            except Exception as exc:
                result.errors.append(LintIssue(level="error", message=f"Invalid YAML: {exc}", path=rel_path))
                continue

            if not isinstance(data, list):
                result.errors.append(LintIssue(level="error", message="Asset must be a YAML list", path=rel_path))
                continue

            validator(data, rel_path, result)

    def _check_optional_files(self, skill_root: Path, result: SkillLintResult) -> None:
        for rel_path in self.OPTIONAL_REFERENCES + self.OPTIONAL_ASSETS:
            if not (skill_root / rel_path).exists():
                result.warnings.append(
                    LintIssue(level="warning", message=f"Optional file is missing: {rel_path}", path=rel_path)
                )

    def _check_content_quality(self, body: str, result: SkillLintResult) -> None:
        overview = self.parser._extract_section(body, "Overview")
        key_concepts = self.parser._parse_list_section(self.parser._extract_section(body, "Key Concepts"))
        takeaways = self.parser._parse_list_section(self.parser._extract_section(body, "Takeaways"))

        if len(overview) < 40:
            result.warnings.append(LintIssue(level="warning", message="Overview section is missing or too thin"))
        if len(key_concepts) < 3:
            result.warnings.append(LintIssue(level="warning", message="Key Concepts section is missing or too thin"))
        if not takeaways:
            result.warnings.append(LintIssue(level="warning", message="Takeaways section is missing"))

    @staticmethod
    def _check_quiz_script(skill_root: Path, result: SkillLintResult) -> None:
        if not (skill_root / "scripts" / "quiz.py").exists():
            result.warnings.append(
                LintIssue(level="warning", message="Missing scripts/quiz.py", path="scripts/quiz.py")
            )

    @staticmethod
    def _validate_quiz_items(data: list[object], rel_path: str, result: SkillLintResult) -> None:
        for index, item in enumerate(data):
            if not isinstance(item, dict):
                result.errors.append(LintIssue(level="error", message="Quiz item must be an object", path=rel_path))
                continue
            for key in ("question", "answer", "difficulty", "type"):
                if not str(item.get(key, "")).strip():
                    result.errors.append(
                        LintIssue(level="error", message=f"Quiz item missing '{key}'", path=f"{rel_path}[{index}]")
                    )

    @staticmethod
    def _validate_flashcard_items(data: list[object], rel_path: str, result: SkillLintResult) -> None:
        for index, item in enumerate(data):
            if not isinstance(item, dict):
                result.errors.append(LintIssue(level="error", message="Flashcard item must be an object", path=rel_path))
                continue
            for key in ("front", "back"):
                if not str(item.get(key, "")).strip():
                    result.errors.append(
                        LintIssue(level="error", message=f"Flashcard item missing '{key}'", path=f"{rel_path}[{index}]")
                    )

    @staticmethod
    def _validate_exercise_items(data: list[object], rel_path: str, result: SkillLintResult) -> None:
        for index, item in enumerate(data):
            if not isinstance(item, dict):
                result.errors.append(LintIssue(level="error", message="Exercise item must be an object", path=rel_path))
                continue
            for key in ("title", "description", "difficulty", "type"):
                if not str(item.get(key, "")).strip():
                    result.errors.append(
                        LintIssue(level="error", message=f"Exercise item missing '{key}'", path=f"{rel_path}[{index}]")
                    )
