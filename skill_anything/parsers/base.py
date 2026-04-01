"""Base parser interface for all knowledge source parsers."""

from __future__ import annotations

import abc

from skill_anything.models import KnowledgeChunk, SourceType


class BaseParser(abc.ABC):
    """All parsers extract a list of KnowledgeChunks from a source."""

    source_type: SourceType

    @abc.abstractmethod
    def parse(self, source: str) -> list[KnowledgeChunk]:
        """Parse a source (path, URL, or raw text) into knowledge chunks.

        Args:
            source: File path, URL, or raw text depending on the parser type.

        Returns:
            A list of KnowledgeChunk objects.
        """

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
