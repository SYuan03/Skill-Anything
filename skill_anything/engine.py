"""Core orchestration engine — ties parsers and generators together.

Pipeline:  Source -> Parser -> KnowledgeChunk[] -> Generators -> SkillPack
"""

from __future__ import annotations

import logging
from pathlib import Path

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
        auto_title = title or (chunks[0].metadata.get("title", "Web Content") if chunks else "Web Content")
        return self._build(chunks, SourceType.WEBPAGE, url, auto_title)

    def from_text(self, source: str, *, title: str | None = None) -> SkillPack:
        from skill_anything.parsers.text_parser import TextParser

        chunks = TextParser().parse(source)
        p = Path(source)
        auto_title = title or (p.stem.replace("_", " ").replace("-", " ").title() if p.exists() else "Text Content")
        return self._build(chunks, SourceType.TEXT, source, auto_title)

    def from_source(self, source: str, *, title: str | None = None) -> SkillPack:
        """Auto-detect source type and convert to SkillPack."""
        source_type = self._detect_source_type(source)
        dispatch = {
            SourceType.PDF: self.from_pdf,
            SourceType.VIDEO: self.from_video,
            SourceType.WEBPAGE: self.from_web,
            SourceType.TEXT: self.from_text,
        }
        return dispatch[source_type](source, title=title)

    # ------------------------------------------------------------------
    # Output
    # ------------------------------------------------------------------

    def write(self, pack: SkillPack, output_dir: str | Path) -> Path:
        """Write SkillPack to disk: YAML + Markdown study guide + concept map image."""
        import yaml

        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        slug = slugify(pack.title)

        # YAML data
        yaml_path = out / f"{slug}.yaml"
        with open(yaml_path, "w", encoding="utf-8") as f:
            yaml.dump(pack.to_dict(), f, allow_unicode=True, default_flow_style=False, sort_keys=False)

        # Concept map image
        image_filename = f"{slug}-concept-map.png"
        image_path = out / image_filename
        image_result = self.visual_gen.generate(
            pack.title, pack.key_concepts, pack.chunks, output_path=str(image_path),
        )

        # Markdown study guide
        md_path = out / f"{slug}.md"
        md_path.write_text(
            self._render_study_guide(pack, concept_map=image_filename if image_result else None),
            encoding="utf-8",
        )

        return out

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
                GlossaryEntry(term=g["term"], definition=g.get("definition", ""), related_terms=g.get("related_terms", []))
                for g in data.get("glossary", [])
            ],
            timeline=[
                TimelineEntry(position=t.get("position", ""), title=t["title"], summary=t.get("summary", ""))
                for t in data.get("timeline", [])
            ],
            cheat_sheet=data.get("cheat_sheet", ""),
            takeaways=data.get("takeaways", []),
            learning_path=data.get("learning_path", {}),
            quiz_questions=[
                QuizQuestion(
                    question=q["question"], options=q.get("options", []), answer=q.get("answer", ""),
                    explanation=q.get("explanation", ""), difficulty=Difficulty(q.get("difficulty", "medium")),
                    question_type=QuestionType(q.get("type", "multiple_choice")),
                ) for q in data.get("quiz_questions", [])
            ],
            flashcards=[
                Flashcard(front=c["front"], back=c["back"], tags=c.get("tags", []))
                for c in data.get("flashcards", [])
            ],
            practice_exercises=[
                PracticeExercise(
                    title=e["title"], description=e.get("description", ""),
                    difficulty=Difficulty(e.get("difficulty", "medium")),
                    hints=e.get("hints", []), solution=e.get("solution", ""),
                    exercise_type=e.get("type", "open_ended"),
                ) for e in data.get("practice_exercises", [])
            ],
            metadata=data.get("metadata", {}),
        )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _build(self, chunks: list, source_type: SourceType, source_ref: str, title: str) -> SkillPack:
        if not chunks:
            return SkillPack(title=title, source_type=source_type, source_ref=source_ref,
                             summary="No content could be extracted.")

        log.info("Extracted %d knowledge chunks from %s", len(chunks), source_ref)

        knowledge = self.knowledge_gen.generate(chunks)
        quiz_questions = self.quiz_gen.generate(chunks)
        flashcards = self.flashcard_gen.generate(chunks)
        exercises = self.practice_gen.generate(chunks)

        return SkillPack(
            title=title, source_type=source_type, source_ref=source_ref,
            summary=knowledge.summary, detailed_notes=knowledge.detailed_notes,
            key_concepts=knowledge.key_concepts, glossary=knowledge.glossary,
            timeline=knowledge.timeline, cheat_sheet=knowledge.cheat_sheet,
            takeaways=knowledge.takeaways, learning_path=knowledge.learning_path,
            quiz_questions=quiz_questions, flashcards=flashcards,
            practice_exercises=exercises, chunks=chunks,
            metadata={"total_chunks": len(chunks), "total_questions": len(quiz_questions),
                       "total_flashcards": len(flashcards), "total_exercises": len(exercises),
                       "total_glossary": len(knowledge.glossary)},
        )

    # ------------------------------------------------------------------
    # Markdown study guide
    # ------------------------------------------------------------------

    @staticmethod
    def _render_study_guide(pack: SkillPack, *, concept_map: str | None = None) -> str:
        source_label = {
            SourceType.PDF: "PDF", SourceType.VIDEO: "Video",
            SourceType.WEBPAGE: "Webpage", SourceType.TEXT: "Text",
        }.get(pack.source_type, "Source")

        lines = [f"# {pack.title}", "", f"> {source_label}: `{pack.source_ref}`", "", "---", ""]

        # TOC
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

        # Overview
        lines.extend(["## Overview", "", pack.summary, "", "---", ""])

        # Concept map
        if concept_map:
            lines.extend(["## Concept Map", "", f"![Concept Map]({concept_map})", "", "---", ""])

        # Timeline / outline
        if pack.timeline:
            lines.extend(["## Outline", "", "| Position | Topic | Summary |", "|:---------|:------|:--------|"])
            for t in pack.timeline:
                lines.append(f"| `{t.position}` | **{t.title}** | {t.summary} |")
            lines.extend(["", "---", ""])

        # Detailed notes
        if pack.detailed_notes:
            lines.extend(["## Detailed Notes", "", pack.detailed_notes, "", "---", ""])

        # Key concepts
        if pack.key_concepts:
            lines.extend(["## Key Concepts", ""])
            for i, concept in enumerate(pack.key_concepts, 1):
                lines.extend([f"**{i}.** {concept}", ""])
            lines.extend(["---", ""])

        # Glossary
        if pack.glossary:
            lines.extend(["## Glossary", "", "| Term | Definition | Related |", "|:-----|:-----------|:--------|"])
            for g in pack.glossary:
                related = ", ".join(g.related_terms) if g.related_terms else "-"
                lines.append(f"| **{g.term}** | {g.definition} | {related} |")
            lines.extend(["", "---", ""])

        # Cheat sheet
        if pack.cheat_sheet:
            lines.extend(["## Cheat Sheet", "", pack.cheat_sheet, "", "---", ""])

        # Takeaways
        if pack.takeaways:
            lines.extend(["## Takeaways", ""])
            for t in pack.takeaways:
                lines.append(f"- {t}")
            lines.extend(["", "---", ""])

        # Quiz
        if pack.quiz_questions:
            type_labels = {
                QuestionType.MULTIPLE_CHOICE: "MCQ", QuestionType.TRUE_FALSE: "T/F",
                QuestionType.FILL_BLANK: "Fill", QuestionType.SHORT_ANSWER: "Short",
                QuestionType.SCENARIO: "Scenario", QuestionType.COMPARISON: "Compare",
            }
            lines.extend(["## Quiz", ""])
            for i, q in enumerate(pack.quiz_questions, 1):
                label = type_labels.get(q.question_type, "Q")
                diff_marker = {"easy": "E", "medium": "M", "hard": "H"}.get(q.difficulty.value, "?")
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

        # Flashcards
        if pack.flashcards:
            lines.extend(["## Flashcards", ""])
            for i, card in enumerate(pack.flashcards, 1):
                tags = " ".join(f"`{t}`" for t in card.tags) if card.tags else ""
                lines.extend([f"**{i}. {card.front}** {tags}", f"> {card.back}", ""])
            lines.extend(["---", ""])

        # Exercises
        if pack.practice_exercises:
            lines.extend(["## Exercises", ""])
            for i, ex in enumerate(pack.practice_exercises, 1):
                diff_marker = {"easy": "E", "medium": "M", "hard": "H"}.get(ex.difficulty.value, "?")
                lines.extend([f"### Exercise {i}: {ex.title} ({diff_marker})", "", ex.description, ""])
                if ex.hints:
                    lines.append("**Hints:**")
                    for h in ex.hints:
                        lines.append(f"- {h}")
                    lines.append("")
                if ex.solution:
                    lines.extend(["<details><summary>Solution</summary>", "", ex.solution, "", "</details>", ""])
            lines.extend(["---", ""])

        # Learning path
        if pack.learning_path:
            lines.extend(["## Learning Path", ""])
            section_labels = {"prerequisites": "Prerequisites", "next_steps": "Next Steps", "resources": "Recommended Resources"}
            for key, label in section_labels.items():
                items = pack.learning_path.get(key, [])
                if items:
                    lines.append(f"### {label}")
                    for item in items:
                        lines.append(f"- {item}")
                    lines.append("")
            lines.extend(["---", ""])

        lines.append("*Generated by [Skill-Anything](https://github.com/Skill-Anything/Skill-Anything)*")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _detect_source_type(source: str) -> SourceType:
        import re
        if source.startswith(("http://", "https://")):
            if re.search(r"(youtube\.com|youtu\.be)/", source):
                return SourceType.VIDEO
            return SourceType.WEBPAGE
        suffix = Path(source).suffix.lower()
        if suffix == ".pdf":
            return SourceType.PDF
        if suffix in (".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".srt", ".vtt"):
            return SourceType.VIDEO
        return SourceType.TEXT

    @staticmethod
    def _title_from_source(source: str) -> str:
        import re
        if source.startswith("http"):
            m = re.search(r"v=([\w-]+)", source)
            return f"Video {m.group(1)[:8]}" if m else "Video Content"
        return Path(source).stem.replace("_", " ").replace("-", " ").title()
