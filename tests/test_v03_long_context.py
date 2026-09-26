"""Tests for v0.3 long-context features: Section model, map-reduce generators,
disk cache, per-section quotas, and failure isolation."""

from __future__ import annotations

import json
import threading
from pathlib import Path

from skill_anything.generators._budget import allocate_quota
from skill_anything.generators._concurrent import LLMCache, cache_key, map_llm
from skill_anything.generators.flashcard_gen import FlashcardGenerator
from skill_anything.generators.knowledge_gen import KnowledgeGenerator
from skill_anything.generators.quiz_gen import QuizGenerator
from skill_anything.models import KnowledgeChunk, Section

# ----------------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------------


def _make_book_sections(n_chapters: int = 30, chunks_per: int = 1) -> list[Section]:
    sections = []
    chunk_idx = 0
    for i in range(1, n_chapters + 1):
        chunks = []
        for j in range(chunks_per):
            chunks.append(
                KnowledgeChunk(
                    content=f"Chapter {i} content paragraph {j+1}. " * 30,
                    section=f"Chapter {i}",
                    section_id=f"sec-{i:03d}",
                    chunk_index=chunk_idx,
                )
            )
            chunk_idx += 1
        sections.append(
            Section(id=f"sec-{i:03d}", title=f"Chapter {i}", chunks=chunks)
        )
    return sections


# ----------------------------------------------------------------------
# Quota allocation
# ----------------------------------------------------------------------


def test_quota_every_section_gets_one_when_budget_allows():
    sections = _make_book_sections(30)
    quotas = allocate_quota(sections, total=30)
    assert sum(quotas.values()) == 30
    assert all(q >= 1 for q in quotas.values())


def test_quota_weighted_by_section_size():
    big = Section(id="big", title="Big", chunks=[KnowledgeChunk(content="x" * 10_000)])
    small = Section(id="small", title="Small", chunks=[KnowledgeChunk(content="x" * 100)])
    quotas = allocate_quota([big, small], total=20)
    assert quotas["big"] > quotas["small"]
    assert sum(quotas.values()) == 20


def test_quota_handles_total_smaller_than_section_count():
    sections = _make_book_sections(10)
    quotas = allocate_quota(sections, total=3)
    # Should distribute 3 to as many sections as possible, not give 0 to all
    # except one. Total still adds up to 3.
    assert sum(quotas.values()) == 3


# ----------------------------------------------------------------------
# Cache + concurrent executor
# ----------------------------------------------------------------------


def test_llm_cache_round_trip(tmp_path: Path):
    cache = LLMCache(tmp_path / "cache")
    key = cache_key("hello world", "model-x")
    assert cache.get(key) is None
    cache.put(key, {"foo": "bar"})
    assert cache.get(key) == {"foo": "bar"}


def test_map_llm_caches_so_second_run_makes_no_calls(tmp_path: Path):
    cache = LLMCache(tmp_path / "cache")
    call_count = {"n": 0}
    lock = threading.Lock()

    def fn(item: str) -> dict:
        with lock:
            call_count["n"] += 1
        return {"echo": item}

    items = [f"item-{i}" for i in range(5)]
    def key_fn(item):
        return cache_key(item, "test-model")

    map_llm(items, fn, concurrency=2, cache=cache, key_fn=key_fn, show_progress=False)
    assert call_count["n"] == 5

    # Second run: every key is cached, fn must not be called.
    map_llm(items, fn, concurrency=2, cache=cache, key_fn=key_fn, show_progress=False)
    assert call_count["n"] == 5, "cache should have prevented additional fn calls"


def test_map_llm_isolates_failures(tmp_path: Path):
    def fn(item: int) -> str:
        if item == 3:
            raise RuntimeError("boom")
        return f"ok-{item}"

    results = map_llm(
        list(range(5)), fn, concurrency=2, max_retries=0, show_progress=False,
    )
    assert results[0] == "ok-0"
    assert results[3] is None
    assert results[4] == "ok-4"


def test_map_llm_retries_empty_responses(monkeypatch):
    attempts = {"n": 0}
    monkeypatch.setattr("skill_anything.generators._concurrent.time.sleep", lambda _: None)

    def fn(item: str) -> str | None:
        attempts["n"] += 1
        return None if attempts["n"] == 1 else f"ok-{item}"

    assert map_llm(["item"], fn, max_retries=1, show_progress=False) == ["ok-item"]
    assert attempts["n"] == 2


def test_map_llm_respects_concurrency_cap():
    in_flight = {"n": 0, "max": 0}
    lock = threading.Lock()

    def fn(item: int) -> int:
        with lock:
            in_flight["n"] += 1
            in_flight["max"] = max(in_flight["max"], in_flight["n"])
        # Hold briefly so concurrent calls overlap.
        import time
        time.sleep(0.05)
        with lock:
            in_flight["n"] -= 1
        return item

    map_llm(list(range(20)), fn, concurrency=3, show_progress=False)
    assert in_flight["max"] <= 3, f"expected <=3 concurrent, saw {in_flight['max']}"


# ----------------------------------------------------------------------
# Generators with mocked LLM — verify per-section quota coverage
# ----------------------------------------------------------------------


def test_quiz_generator_covers_every_section(monkeypatch, tmp_path: Path):
    sections = _make_book_sections(30)
    seen_sections: list[str] = []
    lock = threading.Lock()

    def fake_chat(messages, **kwargs):
        # Extract section title from prompt to verify coverage.
        prompt = messages[0]["content"]
        import re
        m = re.search(r'titled "(Chapter \d+)"', prompt)
        with lock:
            if m:
                seen_sections.append(m.group(1))
        return json.dumps([
            {
                "question": f"Q for {m.group(1) if m else '?'}",
                "type": "multiple_choice",
                "options": ["A", "B", "C", "D"],
                "answer": "A",
                "explanation": "...",
                "difficulty": "medium",
                "evidence": f"Chapter {m.group(1).split()[-1]} content paragraph 1",
            }
        ])

    monkeypatch.setattr("skill_anything.llm.is_available", lambda: True)
    monkeypatch.setattr("skill_anything.llm.chat", fake_chat)

    gen = QuizGenerator(cache_dir=tmp_path / "cache", concurrency=4)
    questions = gen.generate(sections, total=30)

    assert len(questions) >= 25, f"expected ~30 questions, got {len(questions)}"
    # Every chapter should appear in the coverage list.
    unique_chapters = set(seen_sections)
    assert len(unique_chapters) == 30, (
        f"only {len(unique_chapters)} of 30 chapters got quiz coverage"
    )


def test_flashcard_generator_covers_every_section(monkeypatch, tmp_path: Path):
    sections = _make_book_sections(20)
    seen_sections: list[str] = []
    lock = threading.Lock()

    def fake_chat(messages, **kwargs):
        import re
        m = re.search(r'titled "(Chapter \d+)"', messages[0]["content"])
        with lock:
            if m:
                seen_sections.append(m.group(1))
        chapter = m.group(1) if m else "Chapter 1"
        return json.dumps([{
            "front": f"Q for {chapter}", "back": "A", "tags": [],
            "evidence": f"{chapter} content paragraph 1",
        }])

    monkeypatch.setattr("skill_anything.llm.is_available", lambda: True)
    monkeypatch.setattr("skill_anything.llm.chat", fake_chat)

    gen = FlashcardGenerator(cache_dir=tmp_path / "cache", concurrency=4)
    cards = gen.generate(sections, total=20)

    assert len(cards) >= 18
    assert len(set(seen_sections)) == 20


def test_knowledge_gen_map_reduce_cache_hits_skip_calls(monkeypatch, tmp_path: Path):
    sections = _make_book_sections(5)
    call_count = {"n": 0}
    lock = threading.Lock()

    def fake_chat(messages, **kwargs):
        with lock:
            call_count["n"] += 1
        prompt = messages[0]["content"]
        if '"summary"' in prompt and '"key_concepts"' in prompt and '"cheat_sheet"' in prompt:
            return json.dumps({
                "summary": "Global summary.",
                "key_concepts": ["A", "B"],
                "cheat_sheet": "Cheat.",
                "takeaways": ["T1"],
                "learning_path": {"prerequisites": [], "next_steps": [], "resources": []},
            })
        # Per-section
        chapter_match = __import__("re").search(r"Chapter (\d+) content", prompt)
        chapter_number = chapter_match.group(1) if chapter_match else "1"
        return json.dumps({
            "summary": "Sec summary.",
            "key_concepts": ["C1"],
            "glossary": [{"term": "T", "definition": "D", "related_terms": []}],
            "notes": "Notes.",
            "evidence": [f"Chapter {chapter_number} content paragraph 1"],
        })

    monkeypatch.setattr("skill_anything.llm.is_available", lambda: True)
    monkeypatch.setattr("skill_anything.llm.chat", fake_chat)

    cache_dir = tmp_path / "cache"
    gen = KnowledgeGenerator(cache_dir=cache_dir, concurrency=4)
    out1 = gen.generate(sections)
    first_calls = call_count["n"]
    assert out1.summary
    assert first_calls == 6  # 5 map + 1 reduce

    # Second run: same sections, same prompts → cache hits, no new calls.
    gen2 = KnowledgeGenerator(cache_dir=cache_dir, concurrency=4)
    out2 = gen2.generate(sections)
    assert call_count["n"] == first_calls, (
        "cache should have prevented additional LLM calls on rerun"
    )
    assert out2.summary == out1.summary


def test_knowledge_gen_handles_section_failure_gracefully(monkeypatch, tmp_path: Path):
    sections = _make_book_sections(5)
    call_idx = {"n": 0}
    lock = threading.Lock()

    def fake_chat(messages, **kwargs):
        with lock:
            call_idx["n"] += 1
            n = call_idx["n"]
        prompt = messages[0]["content"]
        if '"cheat_sheet"' in prompt:
            return json.dumps({
                "summary": "Global summary.",
                "key_concepts": [],
                "cheat_sheet": "",
                "takeaways": [],
                "learning_path": {},
            })
        if n == 2:
            return None  # simulate one section failing
        chapter_match = __import__("re").search(r"Chapter (\d+) content", prompt)
        chapter_number = chapter_match.group(1) if chapter_match else "1"
        return json.dumps({
            "summary": "Sec summary.",
            "key_concepts": ["C"],
            "glossary": [],
            "notes": "N",
            "evidence": [f"Chapter {chapter_number} content paragraph 1"],
        })

    monkeypatch.setattr("skill_anything.llm.is_available", lambda: True)
    monkeypatch.setattr("skill_anything.llm.chat", fake_chat)

    gen = KnowledgeGenerator(cache_dir=tmp_path / "cache", concurrency=2)
    out = gen.generate(sections)
    # Even though one section failed, we still got the global reduce and
    # at least the other 4 sections' notes.
    assert out.summary == "Global summary."
    assert "failed" in out.detailed_notes.lower() or out.detailed_notes.count("##") >= 4


# ----------------------------------------------------------------------
# Section model + parser back-compat
# ----------------------------------------------------------------------


def test_text_parser_produces_sections_and_chunks(tmp_path: Path):
    from skill_anything.parsers.text_parser import TextParser

    md = "# Chapter 1\n\n" + "Body text. " * 50 + "\n\n# Chapter 2\n\n" + "Body. " * 50
    sections = TextParser().parse_sections(md)
    assert len(sections) == 2
    assert sections[0].title == "Chapter 1"
    assert sections[0].chunks[0].section_id == "sec-001"

    # Back-compat: parse() still returns flat chunks.
    chunks = TextParser().parse(md)
    assert len(chunks) >= 2
    assert all(hasattr(c, "section_id") for c in chunks)


def test_repo_parser_uses_budget_not_hard_cap(tmp_path: Path):
    from skill_anything.parsers.repo_parser import RepoParser

    repo_dir = tmp_path / "demo"
    (repo_dir / "docs").mkdir(parents=True)
    # Create 25 doc files (v0.2 cap was 12).
    for i in range(25):
        (repo_dir / "docs" / f"d{i:02d}.md").write_text(
            f"# Doc {i}\n\n" + ("paragraph " * 30), encoding="utf-8"
        )
    (repo_dir / "README.md").write_text("# Demo\n\n" + ("readme " * 100), encoding="utf-8")

    parser = RepoParser(max_chars_budget=1_000_000)  # generous budget
    sections = parser.parse_sections(str(repo_dir))
    selected_paths = parser.stats["selected_paths"]
    # With a generous budget we expect more than the old hard cap of 12 docs.
    doc_paths = [p for p in selected_paths if p.startswith("docs/")]
    assert len(doc_paths) > 12, (
        f"expected budget-based selection to keep >12 docs, got {len(doc_paths)}"
    )
    # Sections are 1:1 with files.
    assert len(sections) == len(selected_paths)
