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
from skill_anything.grounding import (
    citation_for_chunk,
    citation_from_evidence,
    dedupe_by_text,
    split_sections_for_generation,
)
from skill_anything.models import (
    GlossaryEntry,
    KnowledgeChunk,
    Section,
    SourceCitation,
    TimelineEntry,
)

log = logging.getLogger(__name__)

KNOWLEDGE_PROMPT_VERSION = "v0.4.1-evidence"


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
    citations: list[SourceCitation] = field(default_factory=list)


_SECTION_PROMPT = """\
You are extracting study material from one section of a larger document.

Ground every statement in the supplied section. Do not introduce tools, facts,
examples, recommendations, or requirements that the section does not contain.
Keep the amount of output proportional to the amount of source evidence; never
pad a short section to meet a word or item target.

Section title: {title}
Section position: {position} of {total}

Output ONLY valid JSON with these fields:

{{
  "summary": "Concise summary of THIS section only (not the whole document).",
  "key_concepts": ["Concept name: one-sentence explanation", ... up to 5 supported items],
  "glossary": [{{"term": "...", "definition": "...", "related_terms": ["..."]}}, ... only terms present],
  "notes": "Markdown with ### subheadings, bullet points, key formulas/examples. Self-contained for this section.",
  "evidence": ["2-5 short exact quotes copied verbatim from the section that support the output"]
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

Use only claims present in those inputs. Do not add outside facts or recommend
resources that were not explicitly named. Prefer a shorter faithful result over
padding to a target length.

Per-section summaries:
{summaries}

Merged concept candidates (from sections, may overlap):
{concepts}

Merged glossary terms:
{terms}

Output ONLY valid JSON:

{{
  "summary": "Concise summary of the WHOLE document, proportional to its content.",
  "key_concepts": ["Concept: explanation", ... up to 15 globally important items, ranked],
  "cheat_sheet": "Markdown quick-reference covering the whole document. Tables/bullets, dense.",
  "takeaways": ["Verb-first action", ... up to 10 source-grounded items],
  "learning_path": {{
    "prerequisites": ["..."],
    "next_steps": ["..."],
    "resources": ["Only resources explicitly named in the source; otherwise empty"]
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
        self.diagnostics: dict[str, int | str] = {
            "mode": "not-run", "windows": 0, "accepted": 0, "rejected": 0,
        }

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def generate(self, sections_or_chunks: list) -> KnowledgeOutput:
        source_sections = self._coerce_sections(sections_or_chunks)
        self.diagnostics = {
            "mode": "not-run", "windows": 0, "accepted": 0, "rejected": 0,
        }
        if not source_sections:
            return KnowledgeOutput(summary="No content to process.")

        chunks = [c for s in source_sections for c in s.chunks]
        try:
            from skill_anything.llm import is_available

            if not is_available():
                output = self._generate_offline(chunks)
                self.diagnostics.update(mode="offline", accepted=len(output.citations))
                return output
        except ImportError:
            output = self._generate_offline(chunks)
            self.diagnostics.update(mode="offline", accepted=len(output.citations))
            return output

        prompt_sections = split_sections_for_generation(source_sections, max_chars=6000)
        self.diagnostics["windows"] = len(prompt_sections)
        output = self._generate_with_llm(prompt_sections)
        if not output.timeline:
            output.timeline = self._build_timeline_from_sections(source_sections)
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
                model=fast_model,
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

        if not any(section_results):
            log.warning("All knowledge map calls failed; using offline fallback")
            return self._generate_offline([c for section in sections for c in section.chunks])

        # Assemble detailed_notes deterministically + collect concepts/glossary.
        notes_parts: list[str] = []
        section_summaries: list[tuple[str, str]] = []
        concept_pool: list[str] = []
        glossary_pool: list[dict] = []
        citations: list[SourceCitation] = []
        rejected = 0

        for section, result in zip(sections, section_results):
            if not result:
                rejected += 1
                notes_parts.append(f"## {section.title}\n\n_Section processing failed; see source._")
                continue
            raw_evidence = result.get("evidence", [])
            if not isinstance(raw_evidence, list):
                raw_evidence = []
            verified = [
                citation
                for quote in raw_evidence
                if (citation := citation_from_evidence(section, quote)) is not None
            ]
            if not verified:
                rejected += 1
                log.warning("Rejected ungrounded knowledge output for %s", section.id)
                notes_parts.append(
                    f"## {section.title}\n\n_Section output lacked verifiable source evidence._"
                )
                continue
            notes = result.get("notes") if isinstance(result.get("notes"), str) else ""
            summary = result.get("summary") if isinstance(result.get("summary"), str) else ""
            evidence_block = "\n".join(
                f'> Source evidence ({citation.label}): “{citation.excerpt}”'
                for citation in verified
            )
            notes_parts.append(f"## {section.title}\n\n{notes.strip()}\n\n{evidence_block}")
            citations.extend(verified)
            section_summaries.append((section.title, summary.strip()))
            raw_concepts = result.get("key_concepts", [])
            if isinstance(raw_concepts, list):
                concept_pool.extend(
                    c for c in raw_concepts if isinstance(c, str) and c.strip()
                )
            raw_glossary = result.get("glossary", [])
            for g in raw_glossary if isinstance(raw_glossary, list) else []:
                if isinstance(g, dict) and g.get("term"):
                    glossary_pool.append(g)

        detailed_notes = "\n\n".join(notes_parts)
        merged_glossary = self._dedup_glossary(glossary_pool)

        if not section_summaries:
            log.warning("All knowledge outputs failed evidence verification; using offline fallback")
            output = self._generate_offline(
                [chunk for section in sections for chunk in section.chunks]
            )
            self.diagnostics.update(
                mode="offline-fallback", accepted=len(output.citations), rejected=rejected,
            )
            return output

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
                model=smart_model,
            )
            reduced = self._parse_json_object(raw) if raw else None
            if reduced:
                cache.put(reduce_key, reduced)

        if not reduced:
            # Reduce failed — fall back to using map outputs only.
            output = KnowledgeOutput(
                summary=" ".join(s for _, s in section_summaries)[:1500],
                detailed_notes=detailed_notes,
                key_concepts=concept_pool[:15],
                glossary=merged_glossary,
                cheat_sheet="",
                takeaways=[],
                learning_path={},
                citations=dedupe_by_text(citations, lambda item: item.excerpt),
            )
            self.diagnostics.update(
                mode="map-only", accepted=len(section_summaries), rejected=rejected,
            )
            return output

        reduced_concepts = reduced.get("key_concepts")
        reduced_takeaways = reduced.get("takeaways")
        reduced_path = reduced.get("learning_path")
        output = KnowledgeOutput(
            summary=str(reduced.get("summary", "")),
            detailed_notes=detailed_notes,
            key_concepts=(
                [item for item in reduced_concepts if isinstance(item, str)][:15]
                if isinstance(reduced_concepts, list)
                else concept_pool[:15]
            ),
            glossary=merged_glossary,
            cheat_sheet=str(reduced.get("cheat_sheet", "")),
            takeaways=(
                [item for item in reduced_takeaways if isinstance(item, str)][:10]
                if isinstance(reduced_takeaways, list)
                else []
            ),
            learning_path=reduced_path if isinstance(reduced_path, dict) else {},
            citations=dedupe_by_text(citations, lambda item: item.excerpt),
        )
        self.diagnostics.update(mode="llm", accepted=len(section_summaries), rejected=rejected)
        return output

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

        citations = []
        for chunk in chunks:
            candidates = [
                sentence.strip()
                for sentence in re.split(r"(?<=[.!?])\s+", chunk.content)
                if len(sentence.strip()) >= 8
            ]
            excerpt = candidates[0] if candidates else chunk.content.strip()[:500]
            if excerpt:
                citations.append(citation_for_chunk(chunk, excerpt))

        return KnowledgeOutput(
            summary=summary,
            detailed_notes=detailed_notes,
            key_concepts=key_concepts,
            takeaways=[f"Review the core content of {s}" for s in sections_seen[:5]],
            citations=dedupe_by_text(citations, lambda item: item.excerpt),
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
