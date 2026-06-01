"""Flashcard generator — section-aware, quota-balanced (v0.3)."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from skill_anything.generators._budget import allocate_quota
from skill_anything.generators._concurrent import LLMCache, cache_key, map_llm, resolve_fast_model
from skill_anything.models import Flashcard, KnowledgeChunk, Section

log = logging.getLogger(__name__)

FLASHCARD_PROMPT_VERSION = "v0.3"

_FLASHCARD_PROMPT = """\
You are an expert in spaced-repetition learning design. Create {count} \
high-quality flashcards from the section below (titled "{section_title}").

**Requirements:**
1. Front: A precise, unambiguous question or concept prompt
2. Back: A concise, complete answer (1-3 sentences max)
3. Tags: 2-3 relevant category tags
4. Cover the most important knowledge points in this section
5. Each card should test exactly one atomic piece of knowledge
6. Vary styles: definitions, "why", "how", comparisons, applications

Section content:
{content}

Output ONLY a valid JSON array:

[
  {{
    "front": "What is ...?",
    "back": "...",
    "tags": ["concept", "definition"]
  }}
]
"""


class FlashcardGenerator:
    """Generate flashcards per section with a balanced global quota."""

    def __init__(
        self,
        *,
        cache_dir: Path | None = None,
        concurrency: int = 4,
        fast_model: str | None = None,
    ) -> None:
        self.cache_dir = cache_dir
        self.concurrency = concurrency
        self.fast_model = fast_model

    def generate(
        self,
        sections_or_chunks: list,
        *,
        total: int = 40,
        count_per_chunk: int | None = None,
        max_cards: int | None = None,
    ) -> list[Flashcard]:
        if max_cards is not None:
            total = max_cards
        elif count_per_chunk is not None:
            n = len(sections_or_chunks) if sections_or_chunks else 1
            total = min(count_per_chunk * n, 50)

        sections = self._coerce_sections(sections_or_chunks)
        if not sections:
            return []

        try:
            from skill_anything.llm import is_available
            if not is_available():
                return self._generate_offline(
                    [c for s in sections for c in s.chunks], total,
                )
        except ImportError:
            return self._generate_offline(
                [c for s in sections for c in s.chunks], total,
            )

        quotas = allocate_quota(sections, total, min_per_section=1)
        return self._generate_with_llm(sections, quotas)

    def _generate_with_llm(
        self, sections: list[Section], quotas: dict[str, int],
    ) -> list[Flashcard]:
        from skill_anything.llm import chat

        fast_model = resolve_fast_model(self.fast_model)
        cache = LLMCache(self.cache_dir / "flashcards" if self.cache_dir else None)
        targets = [s for s in sections if quotas.get(s.id, 0) > 0]

        def per_section(section: Section) -> list[dict] | None:
            n = quotas.get(section.id, 0)
            prompt = _FLASHCARD_PROMPT.format(
                count=n,
                section_title=section.title,
                content=section.content[:5000],
            )
            raw = chat(
                [{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=2048,
            )
            if raw is None:
                return None
            return self._parse_response_raw(raw)

        results = map_llm(
            targets,
            per_section,
            concurrency=self.concurrency,
            cache=cache,
            key_fn=lambda s: cache_key(
                _FLASHCARD_PROMPT.format(
                    count=quotas.get(s.id, 0),
                    section_title=s.title,
                    content=s.content[:5000],
                ),
                fast_model,
                FLASHCARD_PROMPT_VERSION,
            ),
            label=f"Flashcards [{fast_model}]",
        )

        cards: list[Flashcard] = []
        for section, items in zip(targets, results):
            if not items:
                continue
            for item in items:
                front = item.get("front", "")
                back = item.get("back", "")
                if front and back:
                    cards.append(
                        Flashcard(
                            front=front,
                            back=back,
                            tags=item.get("tags", []),
                            source_chunk=section.chunks[0].chunk_index if section.chunks else 0,
                        )
                    )
        return cards

    @staticmethod
    def _coerce_sections(items: list) -> list[Section]:
        from skill_anything.generators.knowledge_gen import KnowledgeGenerator
        return KnowledgeGenerator._coerce_sections(items)

    @staticmethod
    def _parse_response_raw(raw: str) -> list[dict]:
        raw = raw.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```\w*\n?", "", raw)
            raw = re.sub(r"\n?```$", "", raw)
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            match = re.search(r"\[.*\]", raw, re.DOTALL)
            if not match:
                return []
            try:
                data = json.loads(match.group())
            except json.JSONDecodeError:
                return []
        return data if isinstance(data, list) else []

    # Back-compat for tests
    @staticmethod
    def _parse_response(raw: str) -> list[Flashcard]:
        items = FlashcardGenerator._parse_response_raw(raw)
        out: list[Flashcard] = []
        for item in items:
            if isinstance(item, dict) and item.get("front") and item.get("back"):
                out.append(
                    Flashcard(
                        front=item["front"],
                        back=item["back"],
                        tags=item.get("tags", []),
                    )
                )
        return out

    @staticmethod
    def _generate_offline(
        chunks: list[KnowledgeChunk], max_cards: int
    ) -> list[Flashcard]:
        cards: list[Flashcard] = []
        for chunk in chunks:
            if len(cards) >= max_cards:
                break
            sentences = [s.strip() for s in re.split(r"[.!?]", chunk.content) if len(s.strip()) > 15]
            for sentence in sentences[:3]:
                if len(cards) >= max_cards:
                    break
                cards.append(
                    Flashcard(
                        front=f"Explain: {sentence[:60]}...",
                        back=sentence,
                        tags=[chunk.section] if chunk.section else [],
                        source_chunk=chunk.chunk_index,
                    )
                )
        return cards
