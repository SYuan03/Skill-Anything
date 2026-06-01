"""Base parser interface for all knowledge source parsers."""

from __future__ import annotations

import abc

from skill_anything.models import KnowledgeChunk, Section, SourceType


class BaseParser(abc.ABC):
    """All parsers extract sections (and their inner chunks) from a source."""

    source_type: SourceType

    @abc.abstractmethod
    def parse_sections(self, source: str) -> list[Section]:
        """Parse a source into a list of Sections.

        Sections are the unit the v0.3 map-reduce pipeline operates on. Each
        section bundles one or more chunks that should be processed together
        (a chapter, a file, a video segment, a page range).
        """

    def parse(self, source: str) -> list[KnowledgeChunk]:
        """Back-compat shim — flatten sections into chunks (reading order)."""
        return [c for section in self.parse_sections(source) for c in section.chunks]

    @staticmethod
    def _split_into_chunks(
        text: str,
        *,
        max_chars: int = 2000,
        overlap: int = 200,
    ) -> list[str]:
        """Split a long text into overlapping chunks, respecting paragraph boundaries."""
        paragraphs = text.split("\n\n")
        chunks: list[str] = []
        current = ""

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            if len(current) + len(para) + 2 > max_chars and current:
                chunks.append(current.strip())
                tail = current[-overlap:] if overlap else ""
                current = tail + "\n\n" + para
            else:
                current = current + "\n\n" + para if current else para

        if current.strip():
            chunks.append(current.strip())

        return chunks
