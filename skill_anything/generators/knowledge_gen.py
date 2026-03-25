"""Knowledge generator — produce structured notes, glossary, cheat sheet,
takeaways, and learning path from knowledge chunks via LLM.

This is the core "value" generator: it turns raw extracted text into
a comprehensive, organized learning package.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field

from skill_anything.models import GlossaryEntry, KnowledgeChunk, TimelineEntry

log = logging.getLogger(__name__)


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


_KNOWLEDGE_PROMPT = """\
You are an expert knowledge architect and instructional designer. Analyze the \
following content and produce a comprehensive, structured learning package.

Your goal is to create materials with **genuine learning value** — not generic \
summaries, but deeply organized knowledge that lets a learner master the topic \
without returning to the original source.

Produce all 7 sections in a single JSON object:

### 1. summary (200-400 words)
- Identify the central thesis, methodology, and conclusions
- Capture the logical chain of reasoning, not just surface-level facts
- Write in clear, precise prose

### 2. detailed_notes (Markdown format, thorough)
- Use hierarchical headings (##/###) to organize
- Include key formulas, data points, quotes, and examples
- Use bold for critical terms, bullet lists for supporting details
- Goal: reading these notes should fully replace re-reading the source

### 3. key_concepts (10-15 core concepts)
- Format: "Concept Name: one-sentence explanation"
- Order from foundational to advanced
- Each explanation must be precise and self-contained

### 4. glossary (15-25 terms)
- Every domain-specific term, acronym, or technical phrase
- Precise definitions (not dictionary-generic)
- Include related_terms to show connections

### 5. cheat_sheet (Markdown, fits on one page)
- The most essential information condensed for quick reference
- Use tables, bullet lists, and code blocks for density
- Suitable for printing and pinning to a wall

### 6. takeaways (5-10 actionable items)
- Not "what was covered" but "what to do with this knowledge"
- Concrete, specific actions the learner should take next
- Start each with a verb

### 7. learning_path
- prerequisites: what someone needs to know before this material
- next_steps: what to study after mastering this
- resources: specific books, courses, tools, papers, or URLs to explore

Content:
---
{content}
---

Output ONLY valid JSON. No markdown fences, no commentary:

{{
  "summary": "...",
  "detailed_notes": "## Section 1\\n\\n...",
  "key_concepts": ["Concept: explanation", ...],
  "glossary": [{{"term": "...", "definition": "...", "related_terms": ["..."]}}],
  "cheat_sheet": "## Quick Reference\\n\\n| ... |\\n...",
  "takeaways": ["Build a ...", "Practice ...", "Read ..."],
  "learning_path": {{
    "prerequisites": ["..."],
    "next_steps": ["..."],
    "resources": ["..."]
  }}
}}
"""

_TIMELINE_PROMPT = """\
Given the following content chunks with position markers, generate a structured \
outline/timeline. Each entry needs: position (timestamp, page number, or section), \
title (short heading), and summary (1-2 sentences).

Content chunks:
{chunks_summary}

Output ONLY a valid JSON array:
[{{"position": "...", "title": "...", "summary": "..."}}]
"""


class KnowledgeGenerator:
    """Generate comprehensive knowledge package from chunks."""

    def generate(self, chunks: list[KnowledgeChunk]) -> KnowledgeOutput:
        combined = "\n\n---\n\n".join(c.content for c in chunks)
        if len(combined) > 15000:
            combined = combined[:15000] + "\n\n[... content truncated ...]"

        output = KnowledgeOutput()

        try:
            from skill_anything.llm import chat, is_available

            if is_available():
                output = self._generate_with_llm(combined, chunks)
            else:
                output = self._generate_offline(chunks)
        except ImportError:
            output = self._generate_offline(chunks)

        if not output.timeline and len(chunks) > 1:
            output.timeline = self._build_timeline_offline(chunks)

        return output

    def _generate_with_llm(
        self, combined: str, chunks: list[KnowledgeChunk]
    ) -> KnowledgeOutput:
        from skill_anything.llm import chat

        prompt = _KNOWLEDGE_PROMPT.format(content=combined)
        raw = chat(
            [{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=8192,
        )

        if raw is None:
            return self._generate_offline(chunks)

        output = self._parse_response(raw, chunks)

        if len(chunks) > 2:
            timeline = self._generate_timeline(chunks)
            if timeline:
                output.timeline = timeline

        return output

    def _generate_timeline(self, chunks: list[KnowledgeChunk]) -> list[TimelineEntry]:
        from skill_anything.llm import chat

        summaries = []
        for c in chunks[:20]:
            pos = c.source_time or (f"p.{c.source_page}" if c.source_page else c.section)
            summaries.append(f"[{pos}] {c.content[:200]}")

        prompt = _TIMELINE_PROMPT.format(chunks_summary="\n\n".join(summaries))
        raw = chat(
            [{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=2048,
        )

        if raw is None:
            return []

        return self._parse_timeline(raw)

    @staticmethod
    def _parse_response(raw: str, chunks: list[KnowledgeChunk]) -> KnowledgeOutput:
        raw = raw.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```\w*\n?", "", raw)
            raw = re.sub(r"\n?```$", "", raw)

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
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
    def _parse_timeline(raw: str) -> list[TimelineEntry]:
        raw = raw.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```\w*\n?", "", raw)
            raw = re.sub(r"\n?```$", "", raw)

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return []

        if not isinstance(data, list):
            return []

        entries = []
        for item in data:
            if isinstance(item, dict) and item.get("title"):
                entries.append(
                    TimelineEntry(
                        position=item.get("position", ""),
                        title=item["title"],
                        summary=item.get("summary", ""),
                    )
                )
        return entries

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

        sections = sorted({c.section for c in chunks if c.section})
        key_concepts = [f"{s}: See corresponding section for details" for s in sections[:10]]
        if not key_concepts:
            key_concepts = [f"Concept {i + 1}" for i in range(min(5, len(chunks)))]

        return KnowledgeOutput(
            summary=summary,
            detailed_notes=detailed_notes,
            key_concepts=key_concepts,
            takeaways=[f"Review the core content of {s}" for s in sections[:5]],
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
