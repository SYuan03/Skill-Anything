"""Tests for the orchestration engine."""

import tempfile
from pathlib import Path

from skill_anything.engine import Engine
from skill_anything.models import GlossaryEntry, SkillPack, SourceType, TimelineEntry


def test_engine_from_text():
    engine = Engine()
    content = "# Machine Learning\n\nMachine learning is a branch of AI that enables computers to learn from data."
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(content)
        f.flush()
        pack = engine.from_text(f.name, title="ML Basics")
    assert pack.title == "ML Basics"
    assert pack.source_type == SourceType.TEXT
    assert len(pack.chunks) >= 1


def test_engine_write_and_load():
    engine = Engine()
    pack = SkillPack(
        title="Test Pack", source_type=SourceType.TEXT, source_ref="test.md",
        summary="A test summary.",
        detailed_notes="## Notes\n\nSome notes.",
        key_concepts=["Concept A", "Concept B"],
        glossary=[GlossaryEntry(term="X", definition="Y", related_terms=["Z"])],
        timeline=[TimelineEntry(position="p.1", title="Intro", summary="Intro text")],
        cheat_sheet="Quick ref here.",
        takeaways=["Do this"],
        learning_path={"prerequisites": ["Math"], "next_steps": ["Advanced"]},
    )
    with tempfile.TemporaryDirectory() as tmpdir:
        engine.write(pack, tmpdir)
        yaml_files = list(Path(tmpdir).glob("*.yaml"))
        assert len(yaml_files) == 1
        md_files = list(Path(tmpdir).glob("*.md"))
        assert len(md_files) == 1

        loaded = Engine.load(str(yaml_files[0]))
        assert loaded.title == "Test Pack"
        assert loaded.summary == "A test summary."
        assert len(loaded.glossary) == 1
        assert loaded.glossary[0].term == "X"
        assert len(loaded.timeline) == 1
        assert "Math" in loaded.learning_path.get("prerequisites", [])


def test_engine_detect_source_type():
    assert Engine._detect_source_type("paper.pdf") == SourceType.PDF
    assert Engine._detect_source_type("https://youtube.com/watch?v=abc") == SourceType.VIDEO
    assert Engine._detect_source_type("https://example.com") == SourceType.WEBPAGE
    assert Engine._detect_source_type("notes.md") == SourceType.TEXT
    assert Engine._detect_source_type("video.mp4") == SourceType.VIDEO
    assert Engine._detect_source_type("video.srt") == SourceType.VIDEO


def test_engine_render_study_guide(sample_pack: SkillPack):
    md = Engine._render_study_guide(sample_pack)
    assert "# Machine Learning Basics" in md
    assert "## Overview" in md
    assert "## Key Concepts" in md
    assert "## Glossary" in md
    assert "## Cheat Sheet" in md
    assert "## Takeaways" in md
    assert "## Quiz" in md
    assert "## Flashcards" in md
    assert "## Exercises" in md
    assert "## Learning Path" in md
    assert "## Outline" in md
    assert "Table of Contents" in md
    assert "Skill-Anything" in md
