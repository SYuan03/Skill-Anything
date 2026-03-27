"""Export SkillPack as a standard SKILL.md directory.

Produces a directory compatible with Claude Code, Cursor, and Codex skill formats:

    skill-name/
    ├── SKILL.md              # Frontmatter + core knowledge
    ├── references/
    │   ├── detailed-notes.md
    │   ├── glossary.md
    │   └── learning-path.md
    ├── assets/
    │   ├── quiz.yaml
    │   ├── flashcards.yaml
    │   ├── exercises.yaml
    │   └── concept-map.png   # copied if available
    └── scripts/
        └── quiz.py           # standalone CLI quiz runner
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from skill_anything.models import SkillPack, slugify


class SkillExporter:
    """Convert a SkillPack into a SKILL.md-based directory."""

    def export(
        self,
        pack: SkillPack,
        output_dir: str | Path,
        *,
        concept_map_src: str | Path | None = None,
    ) -> Path:
        """Write a SKILL.md directory for *pack* under *output_dir*.

        Returns the path to the created skill directory.
        """
        slug = slugify(pack.title)
        skill_dir = Path(output_dir) / slug
        skill_dir.mkdir(parents=True, exist_ok=True)

        # Sub-directories
        refs_dir = skill_dir / "references"
        assets_dir = skill_dir / "assets"
        scripts_dir = skill_dir / "scripts"
        for d in (refs_dir, assets_dir, scripts_dir):
            d.mkdir(exist_ok=True)

        # SKILL.md
        (skill_dir / "SKILL.md").write_text(
            self._render_skill_md(pack), encoding="utf-8",
        )

        # references/
        if pack.detailed_notes:
            (refs_dir / "detailed-notes.md").write_text(
                self._render_detailed_notes(pack), encoding="utf-8",
            )
        if pack.glossary:
            (refs_dir / "glossary.md").write_text(
                self._render_glossary(pack), encoding="utf-8",
            )
        if pack.learning_path:
            (refs_dir / "learning-path.md").write_text(
                self._render_learning_path(pack), encoding="utf-8",
            )

        # assets/ (YAML data files)
        self._write_yaml_asset(assets_dir / "quiz.yaml", self._quiz_data(pack))
        self._write_yaml_asset(assets_dir / "flashcards.yaml", self._flashcard_data(pack))
        self._write_yaml_asset(assets_dir / "exercises.yaml", self._exercise_data(pack))

        # Copy concept map if available
        if concept_map_src:
            src = Path(concept_map_src)
            if src.exists():
                shutil.copy2(src, assets_dir / "concept-map.png")

        # scripts/quiz.py
        (scripts_dir / "quiz.py").write_text(
            self._render_quiz_script(slug), encoding="utf-8",
        )

        # Clean up empty directories
        for d in (refs_dir, assets_dir, scripts_dir):
            if d.exists() and not any(d.iterdir()):
                d.rmdir()

        return skill_dir

    # ------------------------------------------------------------------
    # SKILL.md
    # ------------------------------------------------------------------

    def _render_skill_md(self, pack: SkillPack) -> str:
        slug = slugify(pack.title)
        description = self._build_description(pack)
        lines: list[str] = []

        # Frontmatter
        lines.append("---")
        lines.append(f"name: {slug}")
        lines.append(f"description: >-")
        for desc_line in description.split("\n"):
            lines.append(f"  {desc_line}")
        lines.append("version: 1.0.0")
        lines.append("---")
        lines.append("")

        # Title
        lines.append(f"# {pack.title}")
        lines.append("")

        # Overview
        if pack.summary:
            lines.append("## Overview")
            lines.append("")
            lines.append(pack.summary)
            lines.append("")

        # Key Concepts
        if pack.key_concepts:
            lines.append("## Key Concepts")
            lines.append("")
            for i, concept in enumerate(pack.key_concepts, 1):
                lines.append(f"{i}. {concept}")
            lines.append("")

        # Cheat Sheet
        if pack.cheat_sheet:
            lines.append("## Cheat Sheet")
            lines.append("")
            lines.append(pack.cheat_sheet)
            lines.append("")

        # Takeaways
        if pack.takeaways:
            lines.append("## Takeaways")
            lines.append("")
            for t in pack.takeaways:
                lines.append(f"- {t}")
            lines.append("")

        # Interactive resources
        lines.append("## Interactive Resources")
        lines.append("")
        lines.append("Run the built-in quiz to test knowledge:")
        lines.append("")
        lines.append("```bash")
        lines.append(f"python ${{CLAUDE_SKILL_DIR}}/scripts/quiz.py")
        lines.append("```")
        lines.append("")

        # Additional Resources
        lines.append("## Additional Resources")
        lines.append("")
        lines.append("### Reference Files")
        lines.append("")
        if pack.detailed_notes:
            lines.append("- **`references/detailed-notes.md`** — Comprehensive structured notes")
        if pack.glossary:
            lines.append("- **`references/glossary.md`** — Domain terms and definitions")
        if pack.learning_path:
            lines.append("- **`references/learning-path.md`** — Prerequisites, next steps, and recommended resources")
        lines.append("")
        lines.append("### Data Assets")
        lines.append("")
        if pack.quiz_questions:
            lines.append(f"- **`assets/quiz.yaml`** — {len(pack.quiz_questions)} quiz questions (6 types, 3 difficulty levels)")
        if pack.flashcards:
            lines.append(f"- **`assets/flashcards.yaml`** — {len(pack.flashcards)} spaced-repetition flashcards")
        if pack.practice_exercises:
            lines.append(f"- **`assets/exercises.yaml`** — {len(pack.practice_exercises)} hands-on practice exercises")
        lines.append("")

        return "\n".join(lines)

    def _build_description(self, pack: SkillPack) -> str:
        # Extract trigger phrases from key concepts
        triggers: list[str] = []
        for concept in pack.key_concepts[:5]:
            # Take the concept name (before colon if present)
            name = concept.split(":")[0].strip().strip("*").strip()
            if name:
                triggers.append(f'"{name.lower()}"')

        trigger_str = ", ".join(triggers) if triggers else f'"{pack.title.lower()}"'
        topic = pack.title.lower()

        return (
            f'This skill should be used when the user asks about {trigger_str}, '
            f'or discusses {topic}. Provides comprehensive knowledge including '
            f'key concepts, study notes, quiz questions, flashcards, and practice exercises '
            f'generated from source material.'
        )

    # ------------------------------------------------------------------
    # Reference files
    # ------------------------------------------------------------------

    def _render_detailed_notes(self, pack: SkillPack) -> str:
        lines = [f"# {pack.title} — Detailed Notes", ""]
        lines.append(pack.detailed_notes)
        return "\n".join(lines)

    def _render_glossary(self, pack: SkillPack) -> str:
        lines = [f"# {pack.title} — Glossary", ""]
        lines.append("| Term | Definition | Related Terms |")
        lines.append("|:-----|:-----------|:-------------|")
        for g in pack.glossary:
            related = ", ".join(g.related_terms) if g.related_terms else "—"
            lines.append(f"| **{g.term}** | {g.definition} | {related} |")
        lines.append("")
        return "\n".join(lines)

    def _render_learning_path(self, pack: SkillPack) -> str:
        lines = [f"# {pack.title} — Learning Path", ""]
        section_labels = {
            "prerequisites": "Prerequisites",
            "next_steps": "Next Steps",
            "resources": "Recommended Resources",
        }
        for key, label in section_labels.items():
            items = pack.learning_path.get(key, [])
            if items:
                lines.append(f"## {label}")
                lines.append("")
                for item in items:
                    lines.append(f"- {item}")
                lines.append("")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Asset data
    # ------------------------------------------------------------------

    @staticmethod
    def _quiz_data(pack: SkillPack) -> list[dict[str, Any]]:
        return [q.to_dict() for q in pack.quiz_questions]

    @staticmethod
    def _flashcard_data(pack: SkillPack) -> list[dict[str, Any]]:
        return [f.to_dict() for f in pack.flashcards]

    @staticmethod
    def _exercise_data(pack: SkillPack) -> list[dict[str, Any]]:
        return [e.to_dict() for e in pack.practice_exercises]

    @staticmethod
    def _write_yaml_asset(path: Path, data: list[dict[str, Any]]) -> None:
        if not data:
            return
        import yaml
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    # ------------------------------------------------------------------
    # Quiz script
    # ------------------------------------------------------------------

    @staticmethod
    def _render_quiz_script(slug: str) -> str:
        return f'''#!/usr/bin/env python3
"""Standalone quiz runner for the {slug} skill.

Usage:
    python quiz.py                    # run all questions
    python quiz.py -n 10              # run 10 questions
    python quiz.py -d hard            # hard questions only
"""

import argparse
import random
import sys
from pathlib import Path

import yaml


def load_questions(path: Path | None = None):
    if path is None:
        path = Path(__file__).parent.parent / "assets" / "quiz.yaml"
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or []


def run_quiz(questions, count=None, difficulty=None, shuffle=True):
    if difficulty:
        questions = [q for q in questions if q.get("difficulty") == difficulty]
    if shuffle:
        random.shuffle(questions)
    if count:
        questions = questions[:count]
    if not questions:
        print("No questions match the given filters.")
        return

    score = 0
    total = len(questions)

    for i, q in enumerate(questions, 1):
        q_type = q.get("type", "short_answer")
        diff = q.get("difficulty", "medium")
        print(f"\\n--- Q{{i}}/{{total}} ---  {{diff.upper()}}  ({{q_type}})")
        print(f"\\n  {{q[\\'question\\']}}")

        if q.get("options"):
            for opt in q["options"]:
                print(f"    {{opt}}")

        user_answer = input("\\n  Answer > ").strip()
        print(f"\\n  Correct answer: {{q.get(\\'answer\\', \\'N/A\\')}}")
        if q.get("explanation"):
            print(f"  Explanation: {{q[\\'explanation\\']}}")

        correct = input("  Did you get it right? (y/n) > ").strip().lower()
        if correct == "y":
            score += 1

    pct = (score / total) * 100 if total else 0
    grade = "A+" if pct >= 97 else "A" if pct >= 93 else "A-" if pct >= 90 else \\
            "B+" if pct >= 87 else "B" if pct >= 83 else "B-" if pct >= 80 else \\
            "C+" if pct >= 77 else "C" if pct >= 73 else "C-" if pct >= 70 else \\
            "D" if pct >= 60 else "F"
    print(f"\\n  Score: {{score}}/{{total}} ({{pct:.0f}}%)  Grade: {{grade}}")


def main():
    parser = argparse.ArgumentParser(description="Interactive quiz runner")
    parser.add_argument("-n", "--count", type=int, help="Number of questions")
    parser.add_argument("-d", "--difficulty", choices=["easy", "medium", "hard"])
    parser.add_argument("--no-shuffle", action="store_true")
    parser.add_argument("path", nargs="?", help="Path to quiz.yaml")
    args = parser.parse_args()

    path = Path(args.path) if args.path else None
    questions = load_questions(path)
    run_quiz(questions, count=args.count, difficulty=args.difficulty, shuffle=not args.no_shuffle)


if __name__ == "__main__":
    main()
'''
