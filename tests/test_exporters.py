"""Tests for the skill exporter module."""

from __future__ import annotations

import yaml
from pathlib import Path

import pytest

from skill_anything.exporters.skill_exporter import SkillExporter
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
)


@pytest.fixture
def sample_pack() -> SkillPack:
    """Create a full SkillPack for testing."""
    return SkillPack(
        title="Test Topic",
        source_type=SourceType.TEXT,
        source_ref="test.md",
        summary="A summary of the test topic.",
        detailed_notes="## Section 1\n\nDetailed notes here.",
        key_concepts=["Concept A: first idea", "Concept B: second idea", "Concept C: third"],
        glossary=[
            GlossaryEntry(term="Alpha", definition="First letter", related_terms=["Beta"]),
            GlossaryEntry(term="Beta", definition="Second letter", related_terms=["Alpha"]),
        ],
        timeline=[TimelineEntry(position="1", title="Intro", summary="Introduction")],
        cheat_sheet="Quick reference content.",
        takeaways=["Do X", "Do Y"],
        learning_path={
            "prerequisites": ["Basic knowledge"],
            "next_steps": ["Advanced topic"],
            "resources": ["Book A"],
        },
        quiz_questions=[
            QuizQuestion(
                question="What is A?",
                options=["A) Alpha", "B) Beta", "C) Gamma", "D) Delta"],
                answer="A) Alpha",
                explanation="Alpha is the first.",
                difficulty=Difficulty.EASY,
                question_type=QuestionType.MULTIPLE_CHOICE,
            ),
            QuizQuestion(
                question="True or False: Beta comes after Alpha.",
                answer="True",
                explanation="Yes it does.",
                difficulty=Difficulty.EASY,
                question_type=QuestionType.TRUE_FALSE,
            ),
        ],
        flashcards=[
            Flashcard(front="What is Alpha?", back="First letter", tags=["basics"]),
            Flashcard(front="What is Beta?", back="Second letter", tags=["basics"]),
        ],
        practice_exercises=[
            PracticeExercise(
                title="Exercise 1",
                description="Describe the difference.",
                difficulty=Difficulty.MEDIUM,
                hints=["Think about order"],
                solution="Alpha comes first.",
                exercise_type="analysis",
            ),
        ],
    )


@pytest.fixture
def minimal_pack() -> SkillPack:
    """Create a minimal SkillPack with almost no content."""
    return SkillPack(
        title="Empty Pack",
        source_type=SourceType.TEXT,
        source_ref="empty.md",
    )


class TestSkillExporter:
    """Test the SkillExporter class."""

    def test_export_creates_directory_structure(self, sample_pack: SkillPack, tmp_path: Path):
        exporter = SkillExporter()
        skill_dir = exporter.export(sample_pack, tmp_path)

        assert skill_dir.exists()
        assert skill_dir.name == "test-topic"
        assert (skill_dir / "SKILL.md").exists()
        assert (skill_dir / "references" / "detailed-notes.md").exists()
        assert (skill_dir / "references" / "glossary.md").exists()
        assert (skill_dir / "references" / "learning-path.md").exists()
        assert (skill_dir / "assets" / "quiz.yaml").exists()
        assert (skill_dir / "assets" / "flashcards.yaml").exists()
        assert (skill_dir / "assets" / "exercises.yaml").exists()
        assert (skill_dir / "scripts" / "quiz.py").exists()

    def test_skill_md_has_valid_frontmatter(self, sample_pack: SkillPack, tmp_path: Path):
        exporter = SkillExporter()
        skill_dir = exporter.export(sample_pack, tmp_path)
        content = (skill_dir / "SKILL.md").read_text()

        assert content.startswith("---\n")
        # Extract frontmatter
        parts = content.split("---\n", 2)
        assert len(parts) >= 3
        frontmatter = yaml.safe_load(parts[1])
        assert frontmatter["name"] == "test-topic"
        assert "description" in frontmatter
        assert frontmatter["version"] == "1.0.0"

    def test_skill_md_contains_key_sections(self, sample_pack: SkillPack, tmp_path: Path):
        exporter = SkillExporter()
        skill_dir = exporter.export(sample_pack, tmp_path)
        content = (skill_dir / "SKILL.md").read_text()

        assert "## Overview" in content
        assert "## Key Concepts" in content
        assert "## Cheat Sheet" in content
        assert "## Takeaways" in content
        assert "## Interactive Resources" in content
        assert "## Additional Resources" in content
        assert "references/detailed-notes.md" in content
        assert "references/glossary.md" in content
        assert "assets/quiz.yaml" in content

    def test_skill_md_description_has_triggers(self, sample_pack: SkillPack, tmp_path: Path):
        exporter = SkillExporter()
        skill_dir = exporter.export(sample_pack, tmp_path)
        content = (skill_dir / "SKILL.md").read_text()

        # Description should contain key concept names as trigger phrases
        assert '"concept a' in content.lower()

    def test_quiz_yaml_is_valid(self, sample_pack: SkillPack, tmp_path: Path):
        exporter = SkillExporter()
        skill_dir = exporter.export(sample_pack, tmp_path)

        with open(skill_dir / "assets" / "quiz.yaml") as f:
            data = yaml.safe_load(f)

        assert isinstance(data, list)
        assert len(data) == 2
        assert data[0]["question"] == "What is A?"
        assert data[0]["type"] == "multiple_choice"
        assert data[0]["difficulty"] == "easy"

    def test_flashcards_yaml_is_valid(self, sample_pack: SkillPack, tmp_path: Path):
        exporter = SkillExporter()
        skill_dir = exporter.export(sample_pack, tmp_path)

        with open(skill_dir / "assets" / "flashcards.yaml") as f:
            data = yaml.safe_load(f)

        assert isinstance(data, list)
        assert len(data) == 2
        assert data[0]["front"] == "What is Alpha?"

    def test_exercises_yaml_is_valid(self, sample_pack: SkillPack, tmp_path: Path):
        exporter = SkillExporter()
        skill_dir = exporter.export(sample_pack, tmp_path)

        with open(skill_dir / "assets" / "exercises.yaml") as f:
            data = yaml.safe_load(f)

        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["title"] == "Exercise 1"

    def test_glossary_reference_has_table(self, sample_pack: SkillPack, tmp_path: Path):
        exporter = SkillExporter()
        skill_dir = exporter.export(sample_pack, tmp_path)
        content = (skill_dir / "references" / "glossary.md").read_text()

        assert "| **Alpha**" in content
        assert "| **Beta**" in content
        assert "Beta" in content  # related term for Alpha

    def test_learning_path_reference(self, sample_pack: SkillPack, tmp_path: Path):
        exporter = SkillExporter()
        skill_dir = exporter.export(sample_pack, tmp_path)
        content = (skill_dir / "references" / "learning-path.md").read_text()

        assert "## Prerequisites" in content
        assert "Basic knowledge" in content
        assert "## Next Steps" in content
        assert "Advanced topic" in content

    def test_quiz_script_is_generated(self, sample_pack: SkillPack, tmp_path: Path):
        exporter = SkillExporter()
        skill_dir = exporter.export(sample_pack, tmp_path)
        content = (skill_dir / "scripts" / "quiz.py").read_text()

        assert "#!/usr/bin/env python3" in content
        assert "def main():" in content
        assert "argparse" in content

    def test_minimal_pack_skips_empty_dirs(self, minimal_pack: SkillPack, tmp_path: Path):
        exporter = SkillExporter()
        skill_dir = exporter.export(minimal_pack, tmp_path)

        assert (skill_dir / "SKILL.md").exists()
        # Empty directories should be cleaned up
        assert not (skill_dir / "references").exists()
        assert not (skill_dir / "assets").exists()
        # scripts still exists because quiz.py is always generated
        assert (skill_dir / "scripts" / "quiz.py").exists()

    def test_concept_map_copy(self, sample_pack: SkillPack, tmp_path: Path):
        # Create a fake concept map
        fake_map = tmp_path / "source-map.png"
        fake_map.write_bytes(b"fake-png-data")

        exporter = SkillExporter()
        skill_dir = exporter.export(sample_pack, tmp_path, concept_map_src=fake_map)

        assert (skill_dir / "assets" / "concept-map.png").exists()
        assert (skill_dir / "assets" / "concept-map.png").read_bytes() == b"fake-png-data"

    def test_concept_map_missing_source_is_ignored(self, sample_pack: SkillPack, tmp_path: Path):
        exporter = SkillExporter()
        skill_dir = exporter.export(sample_pack, tmp_path, concept_map_src="/nonexistent/path.png")

        # Should not crash, just skip
        assert not (skill_dir / "assets" / "concept-map.png").exists()

    def test_export_idempotent(self, sample_pack: SkillPack, tmp_path: Path):
        exporter = SkillExporter()
        # Run twice
        exporter.export(sample_pack, tmp_path)
        skill_dir = exporter.export(sample_pack, tmp_path)

        assert (skill_dir / "SKILL.md").exists()


class TestEngineSkillExport:
    """Test skill export via the Engine class."""

    def test_engine_write_skill_format(self, sample_pack: SkillPack, tmp_path: Path):
        from skill_anything.engine import Engine

        engine = Engine()
        engine.write(sample_pack, tmp_path, format="skill")

        skill_dir = tmp_path / "test-topic"
        assert (skill_dir / "SKILL.md").exists()

    def test_engine_write_all_format(self, sample_pack: SkillPack, tmp_path: Path):
        from skill_anything.engine import Engine

        engine = Engine()
        engine.write(sample_pack, tmp_path, format="all")

        # Study format files
        assert (tmp_path / "test-topic.yaml").exists()
        assert (tmp_path / "test-topic.md").exists()
        # Skill format directory
        assert (tmp_path / "test-topic" / "SKILL.md").exists()

    def test_engine_write_study_format_default(self, sample_pack: SkillPack, tmp_path: Path):
        from skill_anything.engine import Engine

        engine = Engine()
        engine.write(sample_pack, tmp_path)

        assert (tmp_path / "test-topic.yaml").exists()
        assert (tmp_path / "test-topic.md").exists()
        # Skill dir should NOT exist
        assert not (tmp_path / "test-topic" / "SKILL.md").exists()

    def test_engine_write_skill_method(self, sample_pack: SkillPack, tmp_path: Path):
        from skill_anything.engine import Engine

        engine = Engine()
        skill_dir = engine.write_skill(sample_pack, tmp_path)

        assert (skill_dir / "SKILL.md").exists()
