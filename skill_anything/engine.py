"""Core orchestration engine — ties parsers and generators together.

Pipeline:  Source -> Parser -> KnowledgeChunk[] -> Generators -> SkillPack
"""

from __future__ import annotations

import logging
from pathlib import Path

from skill_anything.exporters.skill_exporter import SkillExporter
from skill_anything.generators.flashcard_gen import FlashcardGenerator
from skill_anything.generators.knowledge_gen import KnowledgeGenerator
from skill_anything.generators.practice_gen import PracticeGenerator
from skill_anything.generators.quiz_gen import QuizGenerator
from skill_anything.generators.visual_gen import VisualGenerator
from skill_anything.models import (
    Difficulty,
    Flashcard,
    GlossaryEntry,
    PracticeExercise,
    QuestionType,
    QuizQuestion,
    SkillPack,
    SourceType,
    TimelineEntry,
    slugify,
)

log = logging.getLogger(__name__)


class Engine:
    """High-level API that converts any knowledge source into a SkillPack."""

    def __init__(self) -> None:
        self.knowledge_gen = KnowledgeGenerator()
        self.quiz_gen = QuizGenerator()
        self.flashcard_gen = FlashcardGenerator()
        self.practice_gen = PracticeGenerator()
        self.visual_gen = VisualGenerator()
        self.skill_exporter = SkillExporter()

    # ------------------------------------------------------------------
    # Public entry points
    # ------------------------------------------------------------------

    def from_pdf(self, path: str, *, title: str | None = None) -> SkillPack:
        from skill_anything.parsers.pdf_parser import PDFParser

        chunks = PDFParser().parse(path)
        auto_title = title or Path(path).stem.replace("_", " ").replace("-", " ").title()
        return self._build(chunks, SourceType.PDF, path, auto_title)

    def from_video(self, source: str, *, title: str | None = None) -> SkillPack:
        from skill_anything.parsers.video_parser import VideoParser

        chunks = VideoParser().parse(source)
        auto_title = title or self._title_from_source(source)
        return self._build(chunks, SourceType.VIDEO, source, auto_title)

    def from_web(self, url: str, *, title: str | None = None) -> SkillPack:
        from skill_anything.parsers.web_parser import WebParser

        chunks = WebParser().parse(url)
        auto_title = title or (
            chunks[0].metadata.get("title", "Web Content") if chunks else "Web Content"
        )
        return self._build(chunks, SourceType.WEBPAGE, url, auto_title)

    def from_text(self, source: str, *, title: str | None = None) -> SkillPack:
        from skill_anything.parsers.text_parser import TextParser

        chunks = TextParser().parse(source)
        p = Path(source)
        auto_title = title or (
            p.stem.replace("_", " ").replace("-", " ").title() if p.exists() else "Text Content"
        )
        return self._build(chunks, SourceType.TEXT, source, auto_title)

    def from_audio(self, path: str, *, title: str | None = None) -> SkillPack:
        from skill_anything.parsers.audio_parser import AudioParser

        chunks = AudioParser().parse(path)
        auto_title = title or Path(path).stem.replace("_", " ").replace("-", " ").title()
        return self._build(chunks, SourceType.AUDIO, path, auto_title)

    def from_repo(self, source: str, *, title: str | None = None) -> SkillPack:
        from skill_anything.parsers.repo_parser import RepoParser

        parser = RepoParser()
        chunks = parser.parse(source)
        auto_title = title or parser.stats.get("repo_label", self._title_from_source(source))
        pack = self._build(chunks, SourceType.REPO, source, auto_title)
        pack.metadata.update(parser.stats)
        return pack

    def from_skill(self, source: str, *, title: str | None = None) -> SkillPack:
        from skill_anything.parsers.skill_parser import SkillParser

        parser = SkillParser()
        pack = parser.parse_pack(source)
        if title:
            pack.title = title
        pack.source_type = SourceType.SKILL
        pack.source_ref = source
        return pack

    def from_source(self, source: str, *, title: str | None = None) -> SkillPack:
        """Auto-detect source type and convert to SkillPack."""
        source_type = self._detect_source_type(source)
        dispatch = {
            SourceType.PDF: self.from_pdf,
            SourceType.VIDEO: self.from_video,
            SourceType.WEBPAGE: self.from_web,
            SourceType.TEXT: self.from_text,
            SourceType.AUDIO: self.from_audio,
            SourceType.REPO: self.from_repo,
            SourceType.SKILL: self.from_skill,
        }
        return dispatch[source_type](source, title=title)

    # ------------------------------------------------------------------
    # Output
    # ------------------------------------------------------------------

    def write(self, pack: SkillPack, output_dir: str | Path, *, format: str = "study") -> Path:
        """Write SkillPack to disk.

        Args:
            format: "study" (YAML + Markdown + PNG), "skill" (SKILL.md directory),
                    or "all" (both formats).
        """
        import yaml

        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        slug = slugify(pack.title)

        image_filename = f"{slug}-concept-map.png"
        image_path = out / image_filename
        image_result = None
        if format in ("study", "all"):
            image_result = self.visual_gen.generate(
                pack.title,
                pack.key_concepts,
                pack.chunks,
                output_path=str(image_path),
            )

        if format in ("study", "all"):
            yaml_path = out / f"{slug}.yaml"
            with open(yaml_path, "w", encoding="utf-8") as f:
                yaml.dump(
                    pack.to_dict(),
                    f,
                    allow_unicode=True,
                    default_flow_style=False,
                    sort_keys=False,
                )

            md_path = out / f"{slug}.md"
            md_path.write_text(
                self._render_study_guide(
                    pack,
                    concept_map=image_filename if image_result else None,
                ),
                encoding="utf-8",
            )

        if format in ("skill", "all"):
            if format == "skill":
                image_result = self.visual_gen.generate(
                    pack.title,
                    pack.key_concepts,
                    pack.chunks,
                    output_path=str(image_path),
                )
            concept_map_src = image_path if image_result else None
            self.skill_exporter.export(pack, out, concept_map_src=concept_map_src)

        return out

    def write_skill(self, pack: SkillPack, output_dir: str | Path) -> Path:
        """Write SkillPack as a SKILL.md directory."""
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        slug = slugify(pack.title)

        image_path = out / f"{slug}-concept-map.png"
        image_result = self.visual_gen.generate(
            pack.title,
            pack.key_concepts,
            pack.chunks,
            output_path=str(image_path),
        )

        return self.skill_exporter.export(
            pack,
            out,
            concept_map_src=image_path if image_result else None,
        )

    @staticmethod
    def load(path: str) -> SkillPack:
        """Load a SkillPack from a YAML file."""
        import yaml

        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        return SkillPack(
            title=data.get("title", ""),
            source_type=SourceType(data.get("source_type", "text")),
            source_ref=data.get("source_ref", ""),
            summary=data.get("summary", ""),
            detailed_notes=data.get("detailed_notes", ""),
            key_concepts=data.get("key_concepts", []),
            glossary=[
                GlossaryEntry(
                    term=g["term"],
                    definition=g.get("definition", ""),
                    related_terms=g.get("related_terms", []),
                )
                for g in data.get("glossary", [])
            ],
            timeline=[
                TimelineEntry(
                    position=t.get("position", ""),
                    title=t["title"],
                    summary=t.get("summary", ""),
                )
                for t in data.get("timeline", [])
            ],
            cheat_sheet=data.get("cheat_sheet", ""),
            takeaways=data.get("takeaways", []),
            learning_path=data.get("learning_path", {}),
            quiz_questions=[
                QuizQuestion(
                    question=q["question"],
                    options=q.get("options", []),
                    answer=q.get("answer", ""),
                    explanation=q.get("explanation", ""),
                    difficulty=Difficulty(q.get("difficulty", "medium")),
                    question_type=QuestionType(q.get("type", "multiple_choice")),
                )
                for q in data.get("quiz_questions", [])
            ],
            flashcards=[
                Flashcard(front=c["front"], back=c["back"], tags=c.get("tags", []))
                for c in data.get("flashcards", [])
            ],
            practice_exercises=[
                PracticeExercise(
                    title=e["title"],
                    description=e.get("description", ""),
                    difficulty=Difficulty(e.get("difficulty", "medium")),
                    hints=e.get("hints", []),
                    solution=e.get("solution", ""),
                    exercise_type=e.get("type", "open_ended"),
                )
                for e in data.get("practice_exercises", [])
            ],
            metadata=data.get("metadata", {}),
        )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _build(
        self,
        chunks: list,
        source_type: SourceType,
        source_ref: str,
        title: str,
    ) -> SkillPack:
        if not chunks:
            return SkillPack(
                title=title,
                source_type=source_type,
                source_ref=source_ref,
                summary="No content could be extracted.",
            )

        log.info("Extracted %d knowledge chunks from %s", len(chunks), source_ref)

        knowledge = self.knowledge_gen.generate(chunks)
        quiz_questions = self.quiz_gen.generate(chunks)
        flashcards = self.flashcard_gen.generate(chunks)
        exercises = self.practice_gen.generate(chunks)

        return SkillPack(
            title=title,
            source_type=source_type,
            source_ref=source_ref,
            summary=knowledge.summary,
            detailed_notes=knowledge.detailed_notes,
            key_concepts=knowledge.key_concepts,
            glossary=knowledge.glossary,
            timeline=knowledge.timeline,
            cheat_sheet=knowledge.cheat_sheet,
            takeaways=knowledge.takeaways,
            learning_path=knowledge.learning_path,
            quiz_questions=quiz_questions,
            flashcards=flashcards,
            practice_exercises=exercises,
            chunks=chunks,
            metadata={
                "total_chunks": len(chunks),
                "total_questions": len(quiz_questions),
                "total_flashcards": len(flashcards),
                "total_exercises": len(exercises),
                "total_glossary": len(knowledge.glossary),
            },
        )

    # ------------------------------------------------------------------
    # Markdown study guide
    # ------------------------------------------------------------------

    @staticmethod
    def _render_study_guide(pack: SkillPack, *, concept_map: str | None = None) -> str:
        source_label = {
            SourceType.PDF: "PDF",
            SourceType.VIDEO: "Video",
            SourceType.WEBPAGE: "Webpage",
            SourceType.TEXT: "Text",
            SourceType.AUDIO: "Audio",
            SourceType.REPO: "Repository",
            SourceType.SKILL: "Skill",
        }.get(pack.source_type, "Source")

        lines = [f"# {pack.title}", "", f"> {source_label}: `{pack.source_ref}`", "", "---", ""]

        lines.append("## Table of Contents\n")
        toc_items = ["[Overview](#overview)"]
        if concept_map:
            toc_items.append("[Concept Map](#concept-map)")
        if pack.timeline:
            toc_items.append("[Outline](#outline)")
        if pack.detailed_notes:
            toc_items.append("[Detailed Notes](#detailed-notes)")
        if pack.key_concepts:
            toc_items.append("[Key Concepts](#key-concepts)")
        if pack.glossary:
            toc_items.append("[Glossary](#glossary)")
        if pack.cheat_sheet:
            toc_items.append("[Cheat Sheet](#cheat-sheet)")
        if pack.takeaways:
            toc_items.append("[Takeaways](#takeaways)")
        if pack.quiz_questions:
            toc_items.append(f"[Quiz ({len(pack.quiz_questions)}q)](#quiz)")
        if pack.flashcards:
            toc_items.append(f"[Flashcards ({len(pack.flashcards)})](#flashcards)")
        if pack.practice_exercises:
            toc_items.append(f"[Exercises ({len(pack.practice_exercises)})](#exercises)")
        if pack.learning_path:
            toc_items.append("[Learning Path](#learning-path)")
        for i, item in enumerate(toc_items, 1):
            lines.append(f"{i}. {item}")
        lines.extend(["", "---", ""])

        lines.extend(["## Overview", "", pack.summary, "", "---", ""])

        if concept_map:
            lines.extend(["## Concept Map", "", f"![Concept Map]({concept_map})", "", "---", ""])

        if pack.timeline:
            lines.extend(
                ["## Outline", "", "| Position | Topic | Summary |", "|:---------|:------|:--------|"]
            )
            for t in pack.timeline:
                lines.append(f"| `{t.position}` | **{t.title}** | {t.summary} |")
            lines.extend(["", "---", ""])

        if pack.detailed_notes:
            lines.extend(["## Detailed Notes", "", pack.detailed_notes, "", "---", ""])

        if pack.key_concepts:
            lines.extend(["## Key Concepts", ""])
            for i, concept in enumerate(pack.key_concepts, 1):
                lines.extend([f"**{i}.** {concept}", ""])
            lines.extend(["---", ""])

        if pack.glossary:
            lines.extend(
                ["## Glossary", "", "| Term | Definition | Related |", "|:-----|:-----------|:--------|"]
            )
            for g in pack.glossary:
                related = ", ".join(g.related_terms) if g.related_terms else "-"
                lines.append(f"| **{g.term}** | {g.definition} | {related} |")
            lines.extend(["", "---", ""])

        if pack.cheat_sheet:
            lines.extend(["## Cheat Sheet", "", pack.cheat_sheet, "", "---", ""])

        if pack.takeaways:
            lines.extend(["## Takeaways", ""])
            for takeaway in pack.takeaways:
                lines.append(f"- {takeaway}")
            lines.extend(["", "---", ""])

        if pack.quiz_questions:
            type_labels = {
                QuestionType.MULTIPLE_CHOICE: "MCQ",
                QuestionType.TRUE_FALSE: "T/F",
                QuestionType.FILL_BLANK: "Fill",
                QuestionType.SHORT_ANSWER: "Short",
                QuestionType.SCENARIO: "Scenario",
                QuestionType.COMPARISON: "Compare",
            }
            lines.extend(["## Quiz", ""])
            for i, q in enumerate(pack.quiz_questions, 1):
                label = type_labels.get(q.question_type, "Q")
                diff_marker = {"easy": "E", "medium": "M", "hard": "H"}.get(
                    q.difficulty.value,
                    "?",
                )
                lines.extend([f"### Q{i} [{label}] ({diff_marker})", "", f"**{q.question}**", ""])
                if q.options:
                    for opt in q.options:
                        lines.append(f"- {opt}")
                    lines.append("")
                lines.extend(["<details><summary>Answer</summary>", "", f"**{q.answer}**", ""])
                if q.explanation:
                    lines.extend([f"_{q.explanation}_", ""])
                lines.extend(["</details>", ""])
            lines.extend(["---", ""])

        if pack.flashcards:
            lines.extend(["## Flashcards", ""])
            for i, card in enumerate(pack.flashcards, 1):
                tags = " ".join(f"`{tag}`" for tag in card.tags) if card.tags else ""
                lines.extend([f"**{i}. {card.front}** {tags}", f"> {card.back}", ""])
            lines.extend(["---", ""])

        if pack.practice_exercises:
            lines.extend(["## Exercises", ""])
            for i, exercise in enumerate(pack.practice_exercises, 1):
                diff_marker = {"easy": "E", "medium": "M", "hard": "H"}.get(
                    exercise.difficulty.value,
                    "?",
                )
                lines.extend(
                    [
                        f"### Exercise {i}: {exercise.title} ({diff_marker})",
                        "",
                        exercise.description,
                        "",
                    ]
                )
                if exercise.hints:
                    lines.append("**Hints:**")
                    for hint in exercise.hints:
                        lines.append(f"- {hint}")
                    lines.append("")
                if exercise.solution:
                    lines.extend(
                        [
                            "<details><summary>Solution</summary>",
                            "",
                            exercise.solution,
                            "",
                            "</details>",
                            "",
                        ]
                    )
            lines.extend(["---", ""])

        if pack.learning_path:
            lines.extend(["## Learning Path", ""])
            section_labels = {
                "prerequisites": "Prerequisites",
                "next_steps": "Next Steps",
                "resources": "Recommended Resources",
            }
            for key, label in section_labels.items():
                items = pack.learning_path.get(key, [])
                if items:
                    lines.append(f"### {label}")
                    for item in items:
                        lines.append(f"- {item}")
                    lines.append("")
            lines.extend(["---", ""])

        lines.append("*Generated by [Skill-Anything](https://github.com/SYuan03/Skill-Anything)*")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _detect_source_type(source: str) -> SourceType:
        import re

        path = Path(source)

        if path.is_file() and path.name == "SKILL.md":
            return SourceType.SKILL
        if path.is_dir():
            return SourceType.SKILL if (path / "SKILL.md").exists() else SourceType.REPO

        if source.startswith(("http://", "https://")):
            if re.match(r"https?://github\.com/[^/]+/[^/]+(?:/.*)?$", source):
                return SourceType.REPO
            if re.search(r"(youtube\.com|youtu\.be)/", source):
                return SourceType.VIDEO
            return SourceType.WEBPAGE

        suffix = Path(source).suffix.lower()
        if suffix == ".md" and Path(source).name == "SKILL.md":
            return SourceType.SKILL
        if suffix == ".pdf":
            return SourceType.PDF
        if suffix in (".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".wma"):
            return SourceType.AUDIO
        if suffix in (".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".srt", ".vtt"):
            return SourceType.VIDEO
        return SourceType.TEXT

    @staticmethod
    def _title_from_source(source: str) -> str:
        import re

        path = Path(source)
        if path.exists() and path.is_dir():
            return path.name.replace("_", " ").replace("-", " ").title()
        if source.startswith("http"):
            gh_match = re.match(r"https?://github\.com/([^/]+)/([^/]+)", source)
            if gh_match:
                return f"{gh_match.group(1)}/{gh_match.group(2).removesuffix('.git')}"
            match = re.search(r"v=([\w-]+)", source)
            return f"Video {match.group(1)[:8]}" if match else "Video Content"
        return Path(source).stem.replace("_", " ").replace("-", " ").title()
