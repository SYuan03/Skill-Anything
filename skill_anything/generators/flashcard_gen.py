"""Flashcard generator — section-aware, quota-balanced (v0.3)."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from skill_anything.generators._budget import allocate_quota
from skill_anything.generators._concurrent import LLMCache, cache_key, map_llm, resolve_fast_model
from skill_anything.grounding import (
    citation_for_chunk,
    citation_from_evidence,
    dedupe_by_text,
    split_sections_for_generation,
)
from skill_anything.models import Flashcard, KnowledgeChunk, Section

log = logging.getLogger(__name__)

FLASHCARD_PROMPT_VERSION = "v0.4.1-evidence"

_FLASHCARD_PROMPT = """\
You are an expert in spaced-repetition learning design. Create {count} \
high-quality flashcards from the section below (titled "{section_title}").

Use only facts stated in the section. Do not introduce external examples,
requirements, or recommendations. Avoid near-duplicate cards when source
material is limited.

**Requirements:**
1. Front: A precise, unambiguous question or concept prompt
2. Back: A concise, complete answer (1-3 sentences max)
3. Tags: 2-3 relevant category tags
4. Cover the most important knowledge points in this section
5. Each card should test exactly one atomic piece of knowledge
6. Vary styles: definitions, "why", "how", comparisons, applications
7. Include a short verbatim "evidence" quote copied from the section. The card
   will be rejected if that quote cannot be found in the supplied text.

Section content:
{content}

Output ONLY a valid JSON array:

[
  {{
    "front": "What is ...?",
    "back": "...",
    "tags": ["concept", "definition"],
    "evidence": "An exact supporting quote copied from the section"
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
        self.diagnostics: dict[str, int | str] = {"mode": "not-run", "requested": 0, "accepted": 0, "rejected": 0}

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

        sections = split_sections_for_generation(
            self._coerce_sections(sections_or_chunks), max_chars=5000,
        )
        self.diagnostics = {"mode": "not-run", "requested": total, "accepted": 0, "rejected": 0}
        if not sections:
            return []

        try:
            from skill_anything.llm import is_available
            if not is_available():
                output = self._generate_offline(
                    [c for s in sections for c in s.chunks], total,
                )
                self.diagnostics.update(mode="offline", accepted=len(output))
                return output
        except ImportError:
            output = self._generate_offline(
                [c for s in sections for c in s.chunks], total,
            )
            self.diagnostics.update(mode="offline", accepted=len(output))
            return output

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
                model=fast_model,
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
        rejected = 0
        for section, items in zip(targets, results):
            if not items:
                continue
            requested = quotas.get(section.id, 0)
            section_cards: list[Flashcard] = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                front = item.get("front", "")
                back = item.get("back", "")
                citation = citation_from_evidence(section, item.get("evidence"))
                if (
                    isinstance(front, str)
                    and front.strip()
                    and isinstance(back, str)
                    and back.strip()
                    and citation is not None
                ):
                    raw_tags = item.get("tags", [])
                    tags = (
                        [str(tag).strip() for tag in raw_tags if str(tag).strip()]
                        if isinstance(raw_tags, list)
                        else []
                    )
                    section_cards.append(
                        Flashcard(
                            front=front.strip(),
                            back=back.strip(),
                            tags=list(dict.fromkeys(tags))[:5],
                            source_chunk=citation.chunk_index or 0,
                            citation=citation,
                        )
                    )
                else:
                    rejected += 1
            unique = dedupe_by_text(section_cards, lambda item: item.front)
            cards.extend(unique[:requested])
            rejected += len(section_cards) - min(len(unique), requested)
        if cards:
            output = dedupe_by_text(cards, lambda item: item.front)[:sum(quotas.values())]
            rejected += len(cards) - len(output)
            self.diagnostics.update(mode="llm", accepted=len(output), rejected=rejected)
            return output
        log.warning("All flashcard calls failed; using offline fallback")
        output = self._generate_offline(
            [chunk for section in sections for chunk in section.chunks], sum(quotas.values())
        )
        self.diagnostics.update(mode="offline-fallback", accepted=len(output), rejected=rejected)
        return output

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
            if (
                isinstance(item, dict)
                and isinstance(item.get("front"), str)
                and item["front"].strip()
                and isinstance(item.get("back"), str)
                and item["back"].strip()
            ):
                raw_tags = item.get("tags", [])
                out.append(
                    Flashcard(
                        front=item["front"].strip(),
                        back=item["back"].strip(),
                        tags=(
                            [str(tag).strip() for tag in raw_tags if str(tag).strip()]
                            if isinstance(raw_tags, list)
                            else []
                        ),
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
                        citation=citation_for_chunk(chunk, sentence),
                    )
                )
        return cards
