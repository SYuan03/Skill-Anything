"""Grounding helpers shared by the content generators.

The LLM-facing generators ask for a short verbatim quote with every learning
item.  This module is the trust boundary: a citation is only created when that
quote can be found in the supplied source window after whitespace
normalisation.  Generated prose alone is never accepted as evidence.
"""

from __future__ import annotations

from dataclasses import replace

from skill_anything.models import KnowledgeChunk, Section, SourceCitation


def normalize_evidence(value: str) -> str:
    """Collapse formatting-only whitespace for quote verification."""
    return " ".join(str(value).split()).strip()


def citation_from_evidence(
    section: Section,
    evidence: object,
    *,
    min_chars: int = 8,
    max_chars: int = 500,
) -> SourceCitation | None:
    """Return a verified citation, or ``None`` when the quote is not in source."""
    if not isinstance(evidence, str):
        return None
    quote = normalize_evidence(evidence)
    if len(quote) < min_chars or len(quote) > max_chars:
        return None
    if quote.casefold() not in normalize_evidence(section.content).casefold():
        return None

    matched_chunk: KnowledgeChunk | None = None
    for chunk in section.chunks:
        if quote.casefold() in normalize_evidence(chunk.content).casefold():
            matched_chunk = chunk
            break
    if matched_chunk is None and section.chunks:
        # A quote can span the boundary between two source chunks.  It is still
        # verified against the complete prompt window; use its first chunk as
        # the stable locator.
        matched_chunk = section.chunks[0]

    metadata = section.metadata or {}
    source_title = str(metadata.get("source_section_title") or section.title)
    locator = _locator(section, matched_chunk)
    return SourceCitation(
        section=source_title,
        locator=locator,
        excerpt=quote,
        chunk_index=matched_chunk.chunk_index if matched_chunk else None,
    )


def citation_for_chunk(chunk: KnowledgeChunk, excerpt: str) -> SourceCitation:
    """Build a citation for deterministic offline output derived from a chunk."""
    locator = ""
    if chunk.metadata.get("page_range"):
        locator = f"pp.{chunk.metadata['page_range']}"
    elif chunk.source_page is not None:
        locator = f"p.{chunk.source_page}"
    elif chunk.source_time:
        locator = chunk.source_time
    elif chunk.metadata.get("path"):
        locator = str(chunk.metadata["path"])
    elif chunk.section_id:
        locator = chunk.section_id
    return SourceCitation(
        section=chunk.section or chunk.section_id or f"Chunk {chunk.chunk_index}",
        locator=locator,
        excerpt=normalize_evidence(excerpt)[:500],
        chunk_index=chunk.chunk_index,
    )


def split_sections_for_generation(
    sections: list[Section], *, max_chars: int
) -> list[Section]:
    """Split oversized sections into complete, ordered prompt windows.

    Older generators truncated ``section.content`` and silently ignored the
    tail.  Source parsers already produce bounded chunks, so grouping those
    chunks into windows preserves all content and all original locators.
    Exceptionally large chunks are split on paragraph/sentence boundaries.
    """
    if max_chars < 256:
        raise ValueError("max_chars must be at least 256")

    windows: list[Section] = []
    for section in sections:
        chunks: list[KnowledgeChunk] = []
        for chunk in section.chunks:
            chunks.extend(_split_chunk(chunk, max_chars))

        groups: list[list[KnowledgeChunk]] = []
        current: list[KnowledgeChunk] = []
        current_chars = 0
        for chunk in chunks:
            separator = 2 if current else 0
            if current and current_chars + separator + len(chunk.content) > max_chars:
                groups.append(current)
                current = []
                current_chars = 0
                separator = 0
            current.append(chunk)
            current_chars += separator + len(chunk.content)
        if current:
            groups.append(current)

        if len(groups) <= 1:
            windows.append(section)
            continue

        for index, group in enumerate(groups, 1):
            metadata = dict(section.metadata)
            metadata.update(
                {
                    "source_section_id": section.id,
                    "source_section_title": section.title,
                    "window_index": index,
                    "window_count": len(groups),
                }
            )
            windows.append(
                Section(
                    id=f"{section.id}-part-{index:03d}",
                    title=f"{section.title} (part {index}/{len(groups)})",
                    chunks=group,
                    parent_id=section.id,
                    metadata=metadata,
                )
            )
    return windows


def dedupe_by_text(items: list, value) -> list:
    """Return items in order with case/whitespace-equivalent values removed."""
    seen: set[str] = set()
    unique = []
    for item in items:
        key = normalize_evidence(value(item)).casefold()
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def _split_chunk(chunk: KnowledgeChunk, max_chars: int) -> list[KnowledgeChunk]:
    if len(chunk.content) <= max_chars:
        return [chunk]

    pieces: list[str] = []
    remaining = chunk.content.strip()
    while len(remaining) > max_chars:
        candidate = remaining[: max_chars + 1]
        breaks = [candidate.rfind("\n\n"), candidate.rfind(". "), candidate.rfind("\n")]
        split_at = max(breaks)
        if split_at < max_chars // 2:
            split_at = max_chars
        elif candidate[split_at : split_at + 2] == ". ":
            split_at += 1
        pieces.append(remaining[:split_at].strip())
        remaining = remaining[split_at:].strip()
    if remaining:
        pieces.append(remaining)
    return [replace(chunk, content=piece) for piece in pieces if piece]


def _locator(section: Section, chunk: KnowledgeChunk | None) -> str:
    metadata = section.metadata or {}
    if metadata.get("page_start") is not None:
        start = metadata["page_start"]
        end = metadata.get("page_end", start)
        return f"p.{start}" if start == end else f"pp.{start}-{end}"
    if metadata.get("time_start"):
        end = metadata.get("time_end")
        return f"{metadata['time_start']}–{end}" if end else str(metadata["time_start"])
    if metadata.get("path"):
        return str(metadata["path"])
    if chunk is not None:
        if chunk.source_page is not None:
            return f"p.{chunk.source_page}"
        if chunk.source_time:
            return chunk.source_time
        if chunk.metadata.get("page_range"):
            return f"pp.{chunk.metadata['page_range']}"
        if chunk.metadata.get("path"):
            return str(chunk.metadata["path"])
    return str(metadata.get("source_section_id") or section.id)
