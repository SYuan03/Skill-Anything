"""Regression tests for source grounding and production safety gates."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from skill_anything.engine import Engine
from skill_anything.generators.quiz_gen import QuizGenerator
from skill_anything.grounding import citation_from_evidence, split_sections_for_generation
from skill_anything.models import KnowledgeChunk, Section
from skill_anything.validation import audit_pack


def _section(content: str, *, title: str = "Evidence") -> Section:
    return Section(
        id="sec-001",
        title=title,
        chunks=[
            KnowledgeChunk(
                content=content,
                section=title,
                section_id="sec-001",
                chunk_index=7,
                source_page=12,
            )
        ],
    )


def test_citation_requires_quote_present_in_source() -> None:
    section = _section("Alpha   beta\n gamma is the verified source statement.")

    citation = citation_from_evidence(section, "Alpha beta gamma")

    assert citation is not None
    assert citation.section == "Evidence"
    assert citation.locator == "p.12"
    assert citation.chunk_index == 7
    assert citation_from_evidence(section, "This was invented elsewhere") is None


def test_prompt_windows_preserve_oversized_section_tail() -> None:
    chunks = [
        KnowledgeChunk(
            content=f"marker-{index} " + (chr(65 + index) * 900),
            section="Long chapter",
            section_id="sec-001",
            chunk_index=index,
        )
        for index in range(8)
    ]
    original = Section(id="sec-001", title="Long chapter", chunks=chunks)

    windows = split_sections_for_generation([original], max_chars=2200)

    assert len(windows) > 1
    assert all(window.total_chars <= 2200 for window in windows)
    combined = " ".join(window.content for window in windows)
    assert all(f"marker-{index}" in combined for index in range(8))
    assert windows[-1].metadata["source_section_title"] == "Long chapter"


def test_quiz_rejects_fabricated_evidence_and_uses_grounded_fallback(
    monkeypatch,
) -> None:
    section = _section(
        "Reliable systems validate every generated claim against an exact source quote."
    )

    def fake_chat(*args, **kwargs):
        return json.dumps(
            [
                {
                    "question": "What imaginary framework is required?",
                    "type": "multiple_choice",
                    "options": ["A", "B", "C", "D"],
                    "answer": "A",
                    "explanation": "An unsupported claim.",
                    "difficulty": "medium",
                    "evidence": "The source mandates the Imaginary Framework.",
                }
            ]
        )

    monkeypatch.setattr("skill_anything.llm.is_available", lambda: True)
    monkeypatch.setattr("skill_anything.llm.chat", fake_chat)

    generator = QuizGenerator(concurrency=1)
    questions = generator.generate([section], total=1)

    assert len(questions) == 1
    assert "imaginary framework" not in questions[0].question.lower()
    assert questions[0].citation is not None
    assert questions[0].citation.excerpt in section.content
    assert generator.diagnostics == {
        "mode": "offline-fallback",
        "requested": 1,
        "accepted": 1,
        "rejected": 1,
    }


def test_quiz_deduplicates_before_enforcing_section_quota(monkeypatch) -> None:
    section = _section("Alpha is the first concept. Beta is the second concept.")

    def fake_chat(*args, **kwargs):
        def item(question: str, answer: str, evidence: str) -> dict:
            return {
                "question": question,
                "type": "multiple_choice",
                "options": ["A. yes", "B. no", "C. maybe", "D. unknown"],
                "answer": "A. yes",
                "explanation": answer,
                "difficulty": "easy",
                "evidence": evidence,
            }

        return json.dumps(
            [
                item("What is Alpha?", "Alpha is first.", "Alpha is the first concept."),
                item("What is Alpha?", "Duplicate.", "Alpha is the first concept."),
                item("What is Beta?", "Beta is second.", "Beta is the second concept."),
            ]
        )

    monkeypatch.setattr("skill_anything.llm.is_available", lambda: True)
    monkeypatch.setattr("skill_anything.llm.chat", fake_chat)

    questions = QuizGenerator(concurrency=1).generate([section], total=2)

    assert [question.question for question in questions] == ["What is Alpha?", "What is Beta?"]


def test_inline_text_does_not_leak_into_source_ref(monkeypatch) -> None:
    monkeypatch.setattr("skill_anything.llm.is_available", lambda: False)
    source = "A private inline lesson explains one sufficiently detailed fact."

    pack = Engine(cache_enabled=False).from_text(source, title="Private")

    assert pack.source_ref == "<inline>"
    assert source not in pack.to_dict()["source_ref"]


def test_citations_survive_yaml_round_trip(
    sample_pack, tmp_path: Path, monkeypatch
) -> None:
    engine = Engine()
    monkeypatch.setattr(engine.visual_gen, "generate", lambda *args, **kwargs: None)
    engine.write(sample_pack, tmp_path, format="study")
    yaml_path = next(tmp_path.glob("*.yaml"))

    raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    loaded = Engine.load(str(yaml_path))

    assert raw["quiz_questions"][0]["source"]["locator"] == "p.1"
    assert loaded.quiz_questions[0].citation == sample_pack.quiz_questions[0].citation
    assert loaded.flashcards[1].citation == sample_pack.flashcards[1].citation
    assert loaded.practice_exercises[0].citation is not None


def test_offline_pipeline_is_strict_audit_clean(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr("skill_anything.llm.is_available", lambda: False)
    source = (
        "# Reliability\n\n"
        "Reliable systems validate every generated claim against an exact source quote. "
        "Atomic writes prevent readers from observing partially written cache files."
    )
    engine = Engine(cache_enabled=False)
    monkeypatch.setattr(engine.visual_gen, "generate", lambda *args, **kwargs: None)

    pack = engine.from_text(source, title="Reliability")
    engine.write(pack, tmp_path, format="all")
    report = audit_pack(pack, strict=True)

    assert report.ok, report.to_dict()
    assert report.metrics["citation_coverage"] == 1.0
    assert pack.metadata["generation"]["knowledge"]["mode"] == "offline"
    assert pack.metadata["generation"]["quiz"]["mode"] == "offline"
    assert (tmp_path / "reliability-site" / "index.html").exists()
    assert (tmp_path / "reliability-anki.tsv").exists()
