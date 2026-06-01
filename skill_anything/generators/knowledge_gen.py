"""Knowledge generator — map-reduce pipeline over sections (v0.3).

v0.2 truncated the entire source to 15 000 characters and asked one LLM call
to emit summary + notes + concepts + glossary + cheat sheet + takeaways +
learning path. That worked on short PDFs and webpages; on a 500-page book it
discarded ~98% of the source and frequently failed JSON parsing because the
output also overflowed.

v0.3 changes the shape:

  Map     — per-section call (cheap model). Each section yields its own
            summary / concepts / glossary terms / structured notes. Results
            are cached on disk and computed concurrently.
  Reduce  — one global call (smart model). Input is the concatenation of
            per-section summaries plus the merged concept/glossary lists,
            never the raw source. The reduce step produces the global
            summary, cheat sheet, takeaways, and learning path.

Detailed notes are assembled deterministically by concatenating section
notes (no LLM cost). Glossary is deduplicated in code.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from skill_anything.generators._concurrent import (
    LLMCache,
    cache_key,
    map_llm,
    resolve_fast_model,
    resolve_smart_model,
)
from skill_anything.models import GlossaryEntry, KnowledgeChunk, Section, TimelineEntry

log = logging.getLogger(__name__)

KNOWLEDGE_PROMPT_VERSION = "v0.3-mapreduce"


@dataclass
class KnowledgeOutput:
    summary: str = ""
    detailed_notes: str = ""
    key_concepts: list[str] = field(default_factory=list)
    glossary: list[GlossaryEntry] = field(default_factory=list)
    timeline: list[TimelineEntry] = field(default_factory=list)
    cheat_sheet: str = ""
    takeaways: list[str] = field(default_factory=list)
    learning_path: dict[str, list[str]] = field(default_factory=dict)


_SECTION_PROMPT = """\
You are extracting study material from one section of a larger document.

Section title: {title}
Section position: {position} of {total}

Output ONLY valid JSON with these fields:

{{
  "summary": "120-200 word summary of THIS section only (not the whole document).",
  "key_concepts": ["Concept name: one-sentence explanation", ... 2-5 items],
  "glossary": [{{"term": "...", "definition": "...", "related_terms": ["..."]}}, ... 2-6 items],
  "notes": "Markdown with ### subheadings, bullet points, key formulas/examples. Self-contained for this section."
}}

Section content:
---
{content}
---
"""

_REDUCE_PROMPT = """\
You are synthesising a study pack from per-section summaries.

The document has {n} sections. Each per-section summary is shown below in
reading order. Use them — plus the merged concept list and glossary terms —
to produce a coherent, document-level study package.

Per-section summaries:
{summaries}

Merged concept candidates (from sections, may overlap):
{concepts}

Merged glossary terms:
{terms}

Output ONLY valid JSON:

{{
  "summary": "300-500 word summary of the WHOLE document.",
  "key_concepts": ["Concept: explanation", ... 10-15 globally important items, ranked],
  "cheat_sheet": "Markdown quick-reference covering the whole document. Tables/bullets, dense.",
  "takeaways": ["Verb-first action", ... 5-10 items],
  "learning_path": {{
    "prerequisites": ["..."],
    "next_steps": ["..."],
    "resources": ["..."]
  }}
}}
"""


class KnowledgeGenerator:
    """Generate a knowledge package from sections using map-reduce."""

    def __init__(
        self,
        *,
        cache_dir: Path | None = None,
        concurrency: int = 4,
        fast_model: str | None = None,
        smart_model: str | None = None,
    ) -> None:
        self.cache_dir = cache_dir
        self.concurrency = concurrency
        self.fast_model = fast_model
        self.smart_model = smart_model

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def generate(self, sections_or_chunks: list) -> KnowledgeOutput:
        sections = self._coerce_sections(sections_or_chunks)
        if not sections:
            return KnowledgeOutput(summary="No content to process.")

        chunks = [c for s in sections for c in s.chunks]
        try:
            from skill_anything.llm import is_available

            if not is_available():
                return self._generate_offline(chunks)
        except ImportError:
            return self._generate_offline(chunks)

        output = self._generate_with_llm(sections)
        if not output.timeline:
            output.timeline = self._build_timeline_from_sections(sections)
        return output

    # ------------------------------------------------------------------
    # LLM path
    # ------------------------------------------------------------------

    def _generate_with_llm(self, sections: list[Section]) -> KnowledgeOutput:
        from skill_anything.llm import chat

        fast_model = resolve_fast_model(self.fast_model)
        smart_model = resolve_smart_model(self.smart_model)

        cache = LLMCache(self.cache_dir / "knowledge" if self.cache_dir else None)
        total = len(sections)

        def per_section(section: Section) -> dict | None:
            prompt = _SECTION_PROMPT.format(
                title=section.title,
                position=section.id,
                total=total,
                content=section.content[:6000],
            )
            raw = chat(
                [{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=2048,
            )
            if raw is None:
                return None
            return self._parse_json_object(raw)

        section_results = map_llm(
            sections,
            per_section,
            concurrency=self.concurrency,
            cache=cache,
            key_fn=lambda s: cache_key(
                _SECTION_PROMPT.format(
                    title=s.title, position=s.id, total=total,
                    content=s.content[:6000],
                ),
                fast_model,
                KNOWLEDGE_PROMPT_VERSION,
            ),
            label=f"Knowledge (map) [{fast_model}]",
        )

        # Assemble detailed_notes deterministically + collect concepts/glossary.
        notes_parts: list[str] = []
        section_summaries: list[tuple[str, str]] = []
        concept_pool: list[str] = []
        glossary_pool: list[dict] = []

        for section, result in zip(sections, section_results):
            if not result:
                notes_parts.append(f"## {section.title}\n\n_Section processing failed; see source._")
                continue
            notes = result.get("notes") or ""
            summary = result.get("summary") or ""
            notes_parts.append(f"## {section.title}\n\n{notes.strip()}")
            section_summaries.append((section.title, summary.strip()))
            concept_pool.extend(c for c in result.get("key_concepts", []) if isinstance(c, str) and c.strip())
            for g in result.get("glossary", []):
                if isinstance(g, dict) and g.get("term"):
                    glossary_pool.append(g)

        detailed_notes = "\n\n".join(notes_parts)
        merged_glossary = self._dedup_glossary(glossary_pool)

        # Reduce step.
        summaries_block = "\n\n".join(
            f"[{title}] {summary}" for title, summary in section_summaries
        )[:12000]
        concepts_block = "\n".join(f"- {c}" for c in concept_pool[:80])[:4000]
        terms_block = ", ".join(g.term for g in merged_glossary[:40])

        reduce_prompt = _REDUCE_PROMPT.format(
            n=len(sections),
            summaries=summaries_block,
            concepts=concepts_block,
            terms=terms_block,
        )

        reduce_key = cache_key(reduce_prompt, smart_model, KNOWLEDGE_PROMPT_VERSION)
        reduce_cached = cache.get(reduce_key)
        if reduce_cached is not None:
            reduced = reduce_cached
        else:
            # The reduce call still goes through the regular chat() (not
            # wrapped in map_llm) — but we use the same on-disk cache for
            # idempotency on rerun.
            raw = chat(
                [{"role": "user", "content": reduce_prompt}],
                temperature=0.2,
                max_tokens=4096,
            )
            reduced = self._parse_json_object(raw) if raw else None
            if reduced:
                cache.put(reduce_key, reduced)

        if not reduced:
            # Reduce failed — fall back to using map outputs only.
            return KnowledgeOutput(
                summary=" ".join(s for _, s in section_summaries)[:1500],
                detailed_notes=detailed_notes,
                key_concepts=concept_pool[:15],
                glossary=merged_glossary,
                cheat_sheet="",
                takeaways=[],
                learning_path={},
            )

        return KnowledgeOutput(
            summary=reduced.get("summary", ""),
            detailed_notes=detailed_notes,
            key_concepts=reduced.get("key_concepts", concept_pool[:15]),
            glossary=merged_glossary,
            cheat_sheet=reduced.get("cheat_sheet", ""),
            takeaways=reduced.get("takeaways", []),
            learning_path=reduced.get("learning_path", {}),
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _coerce_sections(items: list) -> list[Section]:
        """Accept either sections directly or legacy chunk lists (back-compat)."""
        if not items:
            return []
        if isinstance(items[0], Section):
            return items
        # Legacy: list of KnowledgeChunk — bucket by section_id or section name.
        from collections import OrderedDict
        groups: OrderedDict[str, list[KnowledgeChunk]] = OrderedDict()
        for c in items:
            key = getattr(c, "section_id", "") or c.section or f"sec-{c.chunk_index}"
            groups.setdefault(key, []).append(c)
        sections = []
        for i, (key, group) in enumerate(groups.items(), 1):
            sections.append(
                Section(id=key if key.startswith("sec-") else f"sec-{i:03d}",
                        title=group[0].section or f"Section {i}",
                        chunks=group)
            )
        return sections

    @staticmethod
    def _parse_json_object(raw: str) -> dict | None:
        raw = raw.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```\w*\n?", "", raw)
            raw = re.sub(r"\n?```$", "", raw)
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if not match:
                return None
            try:
                data = json.loads(match.group())
            except json.JSONDecodeError:
                return None
        return data if isinstance(data, dict) else None

    @staticmethod
    def _dedup_glossary(items: list[dict]) -> list[GlossaryEntry]:
        seen: dict[str, GlossaryEntry] = {}
        for g in items:
            term = str(g.get("term", "")).strip()
            if not term:
                continue
            norm = term.lower()
            existing = seen.get(norm)
            definition = str(g.get("definition", "")).strip()
            related = [str(r).strip() for r in g.get("related_terms", []) if str(r).strip()]
            if existing is None:
                seen[norm] = GlossaryEntry(term=term, definition=definition, related_terms=related)
            else:
                # Keep the longer/richer definition; merge related terms.
                if len(definition) > len(existing.definition):
                    existing.definition = definition
                for r in related:
                    if r not in existing.related_terms:
                        existing.related_terms.append(r)
        return list(seen.values())

    @staticmethod
    def _build_timeline_from_sections(sections: list[Section]) -> list[TimelineEntry]:
        entries: list[TimelineEntry] = []
        for s in sections:
            meta = s.metadata or {}
            if "page_start" in meta and "page_end" in meta:
                position = f"pp.{meta['page_start']}-{meta['page_end']}"
            elif "time_start" in meta:
                position = str(meta["time_start"])
            elif "path" in meta:
                position = str(meta["path"])
            else:
                position = s.id
            first_chunk = s.chunks[0].content if s.chunks else ""
            entries.append(
                TimelineEntry(
                    position=position,
                    title=s.title,
                    summary=first_chunk.split(".")[0][:120],
                )
            )
        return entries

    # ------------------------------------------------------------------
    # Offline fallback (preserved for the no-LLM path)
    # ------------------------------------------------------------------

    @staticmethod
    def _generate_offline(chunks: list[KnowledgeChunk]) -> KnowledgeOutput:
        if not chunks:
            return KnowledgeOutput(summary="No content to process.")

        all_text = "\n".join(c.content for c in chunks)
        sentences = re.split(r"[.!?]", all_text)
        sentences = [s.strip() for s in sentences if len(s.strip()) > 15]

        summary = ". ".join(sentences[:5]) + "." if sentences else all_text[:300]

        notes_parts = []
        for c in chunks:
            heading = c.section or f"Section {c.chunk_index + 1}"
            notes_parts.append(f"## {heading}\n\n{c.content[:500]}")
        detailed_notes = "\n\n".join(notes_parts)

        sections_seen = sorted({c.section for c in chunks if c.section})
        key_concepts = [f"{s}: See corresponding section for details" for s in sections_seen[:10]]
        if not key_concepts:
            key_concepts = [f"Concept {i + 1}" for i in range(min(5, len(chunks)))]

        return KnowledgeOutput(
            summary=summary,
            detailed_notes=detailed_notes,
            key_concepts=key_concepts,
            takeaways=[f"Review the core content of {s}" for s in sections_seen[:5]],
        )

    # Back-compat: kept so existing tests (test_knowledge_gen_parse_response)
    # continue working without refactor.
    @staticmethod
    def _parse_response(raw: str, chunks: list[KnowledgeChunk]) -> KnowledgeOutput:
        data = KnowledgeGenerator._parse_json_object(raw)
        if data is None:
            return KnowledgeGenerator._generate_offline(chunks)
        glossary = []
        for g in data.get("glossary", []):
            if isinstance(g, dict) and g.get("term"):
                glossary.append(
                    GlossaryEntry(
                        term=g["term"],
                        definition=g.get("definition", ""),
                        related_terms=g.get("related_terms", []),
                    )
                )
        return KnowledgeOutput(
            summary=data.get("summary", ""),
            detailed_notes=data.get("detailed_notes", ""),
            key_concepts=data.get("key_concepts", []),
            glossary=glossary,
            cheat_sheet=data.get("cheat_sheet", ""),
            takeaways=data.get("takeaways", []),
            learning_path=data.get("learning_path", {}),
        )

    @staticmethod
    def _build_timeline_offline(chunks: list[KnowledgeChunk]) -> list[TimelineEntry]:
        entries = []
        for c in chunks:
            pos = c.source_time or (f"p.{c.source_page}" if c.source_page else f"§{c.chunk_index + 1}")
            title = c.section or f"Part {c.chunk_index + 1}"
            first_sentence = c.content.split(".")[0][:80]
            entries.append(TimelineEntry(position=pos, title=title, summary=first_sentence))
        return entries
