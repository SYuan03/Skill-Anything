"""v0.4 portable sharing and interoperability tests."""

from __future__ import annotations

import csv
import json
import zipfile
from pathlib import Path

import httpx
import pytest

from skill_anything.engine import Engine
from skill_anything.exporters import AnkiExporter, WebExporter
from skill_anything.generators._concurrent import map_llm
from skill_anything.generators.knowledge_gen import KnowledgeGenerator
from skill_anything.llm import _allows_custom_temperature, chat
from skill_anything.models import KnowledgeChunk, Section, SkillPack


def test_web_export_is_self_contained_and_contains_pack(
    sample_pack: SkillPack, tmp_path: Path
) -> None:
    index = WebExporter().export(sample_pack, tmp_path)
    page = index.read_text(encoding="utf-8")

    assert index == tmp_path / "machine-learning-basics-site" / "index.html"
    assert "Machine Learning Basics" in page
    assert 'id="pack-data"' in page
    assert "Flashcards" in page
    assert "localStorage" in page
    assert "Supervised learning uses labeled training data" in page
    assert "Source:" in page
    assert "<script src=" not in page
    assert "<link rel=" not in page

    raw_payload = page.split('id="pack-data" type="application/json">', 1)[1].split(
        "</script>", 1
    )[0]
    payload = json.loads(raw_payload)
    assert payload["title"] == sample_pack.title
    assert len(payload["quiz_questions"]) == 2


def test_web_export_escapes_script_end_tags(sample_pack: SkillPack, tmp_path: Path) -> None:
    sample_pack.summary = "Safe </script><script>alert('no')</script> content"
    page = WebExporter().export(sample_pack, tmp_path).read_text(encoding="utf-8")

    assert "</script><script>alert" not in page
    assert "\\u003c/script\\u003e" in page


def test_anki_export_has_import_headers_and_all_cards(
    sample_pack: SkillPack, tmp_path: Path
) -> None:
    path = AnkiExporter().export(sample_pack, tmp_path)
    lines = path.read_text(encoding="utf-8").splitlines()

    assert path.name == "machine-learning-basics-anki.tsv"
    assert lines[:4] == [
        "#separator:Tab",
        "#html:true",
        "#columns:Front\tBack\tTags",
        "#tags column:3",
    ]
    rows = list(csv.reader(lines[4:], delimiter="\t"))
    assert len(rows) == len(sample_pack.flashcards) + len(sample_pack.quiz_questions)
    assert rows[0][0] == "What is ML?"
    assert "skill-anything" in rows[0][2]
    assert "<strong>Answer:</strong>" in rows[-1][1]
    assert "Source (" in rows[-1][1]
    assert "scenario" in rows[-1][2]


def test_portable_exports_do_not_call_image_api(
    sample_pack: SkillPack, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = Engine()

    def fail_if_called(*args: object, **kwargs: object) -> None:
        raise AssertionError("portable export must not invoke image generation")

    monkeypatch.setattr(engine.visual_gen, "generate", fail_if_called)
    engine.write(sample_pack, tmp_path, format="web")
    engine.write(sample_pack, tmp_path, format="anki")


def test_all_format_includes_v04_exports(
    sample_pack: SkillPack, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = Engine()
    monkeypatch.setattr(engine.visual_gen, "generate", lambda *args, **kwargs: None)
    engine.write(sample_pack, tmp_path, format="all")

    assert (tmp_path / "machine-learning-basics.yaml").exists()
    assert (tmp_path / "machine-learning-basics.md").exists()
    assert (tmp_path / "machine-learning-basics" / "SKILL.md").exists()
    assert (tmp_path / "machine-learning-basics-site" / "index.html").exists()
    assert (tmp_path / "machine-learning-basics-anki.tsv").exists()


def test_unknown_export_format_fails_loudly(sample_pack: SkillPack, tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Unknown output format"):
        Engine().write(sample_pack, tmp_path, format="mystery")


def test_engine_cache_can_follow_custom_output(tmp_path: Path) -> None:
    engine = Engine(cache_dir=tmp_path / ".skill-anything")
    assert engine.cache_dir == tmp_path / ".skill-anything"
    assert engine.concurrency == 6


def test_fast_and_smart_models_are_actually_routed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sections = [
        Section(
            id=f"sec-{index}",
            title=f"Section {index}",
            chunks=[KnowledgeChunk(content="Grounded source text.", section=f"Section {index}")],
        )
        for index in range(2)
    ]
    models: list[str | None] = []

    def fake_chat(messages: list[dict[str, str]], **kwargs: object) -> str:
        models.append(kwargs.get("model"))
        prompt = messages[0]["content"]
        if "synthesising" in prompt:
            return json.dumps(
                {
                    "summary": "Global summary",
                    "key_concepts": ["Concept"],
                    "cheat_sheet": "Cheat sheet",
                    "takeaways": ["Practice"],
                    "learning_path": {},
                }
            )
        return json.dumps(
            {
                "summary": "Section summary", "key_concepts": [],
                "glossary": [], "notes": "Notes",
                "evidence": ["Grounded source text."],
            }
        )

    monkeypatch.setattr("skill_anything.llm.is_available", lambda: True)
    monkeypatch.setattr("skill_anything.llm.chat", fake_chat)
    result = KnowledgeGenerator(
        cache_dir=tmp_path / "cache",
        concurrency=2,
        fast_model="cheap-map-model",
        smart_model="strong-reduce-model",
    ).generate(sections)

    assert result.summary == "Global summary"
    assert models.count("cheap-map-model") == 2
    assert models.count("strong-reduce-model") == 1


def test_engine_accepts_long_inline_text_without_treating_it_as_a_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("skill_anything.llm.is_available", lambda: False)
    pack = Engine(cache_enabled=False).from_text("A long inline lesson. " * 100, title="Inline")
    assert pack.title == "Inline"
    assert pack.chunks


def test_reasoning_models_omit_custom_temperature() -> None:
    assert not _allows_custom_temperature("gpt-5.6-terra")
    assert not _allows_custom_temperature("GPT-6-Astra")
    assert not _allows_custom_temperature("o3-mini")
    assert _allows_custom_temperature("gpt-4o-mini")


def test_httpx_chat_fallback_uses_selected_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request: dict[str, object] = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"choices": [{"message": {"content": " fallback works "}}]}

    class FakeClient:
        def __init__(self, **kwargs: object) -> None:
            request["client_kwargs"] = kwargs

        def __enter__(self) -> "FakeClient":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def post(self, url: str, **kwargs: object) -> FakeResponse:
            request["url"] = url
            request.update(kwargs)
            return FakeResponse()

    monkeypatch.setenv("SKILL_ANYTHING_API_KEY", "test-key")
    monkeypatch.setenv("SKILL_ANYTHING_API_BASE", "https://llm.example/v1")
    monkeypatch.delenv("HTTPS_PROXY", raising=False)
    monkeypatch.delenv("HTTP_PROXY", raising=False)
    monkeypatch.setattr("skill_anything.llm._get_client", lambda: (None, "default-model"))
    monkeypatch.setattr("httpx.Client", FakeClient)

    result = chat(
        [{"role": "user", "content": "Hello"}],
        model="gpt-5.6-terra",
        temperature=0.2,
    )

    assert result == "fallback works"
    assert request["url"] == "https://llm.example/v1/chat/completions"
    body = request["json"]
    assert isinstance(body, dict)
    assert body["model"] == "gpt-5.6-terra"
    assert "temperature" not in body


def test_total_llm_failure_falls_back_to_nonempty_pack(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("skill_anything.llm.is_available", lambda: True)
    monkeypatch.setattr("skill_anything.llm.chat", lambda *args, **kwargs: None)

    pack = Engine(cache_enabled=False).from_text(
        "# Topic\n\nA sufficiently long sentence explains reliable fallback behavior.",
        title="Fallback",
    )

    assert pack.summary
    assert pack.quiz_questions
    assert pack.flashcards
    assert pack.practice_exercises


def test_adaptive_budgets_do_not_overgenerate_from_short_sources() -> None:
    short_sections = [
        Section(
            id=f"sec-{index}",
            title=f"Section {index}",
            chunks=[KnowledgeChunk(content="x" * 180)],
        )
        for index in range(4)
    ]
    long_sections = [
        Section(
            id=f"sec-{index}",
            title=f"Section {index}",
            chunks=[KnowledgeChunk(content="x" * 1_000)],
        )
        for index in range(30)
    ]

    assert Engine._adaptive_generation_budgets(short_sections) == {
        "quiz": 4,
        "flashcards": 6,
        "exercises": 4,
    }
    assert Engine._adaptive_generation_budgets(long_sections) == {
        "quiz": 30,
        "flashcards": 40,
        "exercises": 10,
    }


def test_share_command_creates_valid_zip(
    sample_pack: SkillPack, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from skill_anything.cli import share

    source = tmp_path / "source"
    destination = tmp_path / "shared"
    engine = Engine()
    monkeypatch.setattr(engine.visual_gen, "generate", lambda *args, **kwargs: None)
    engine.write(sample_pack, source, format="study")

    share(str(source / "machine-learning-basics.yaml"), str(destination), no_zip=False)

    archive = destination / "machine-learning-basics-site.zip"
    assert archive.exists()
    with zipfile.ZipFile(archive) as bundle:
        assert bundle.testzip() is None
        assert "machine-learning-basics-site/index.html" in bundle.namelist()


def test_map_runner_does_not_retry_non_retryable_400() -> None:
    calls = 0

    def fail(_: object) -> object:
        nonlocal calls
        calls += 1
        request = httpx.Request("POST", "https://llm.example/v1/chat/completions")
        response = httpx.Response(400, request=request)
        raise httpx.HTTPStatusError("bad request", request=request, response=response)

    assert map_llm([object()], fail, max_retries=2, show_progress=False) == [None]
    assert calls == 1
