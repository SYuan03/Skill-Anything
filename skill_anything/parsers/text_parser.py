"""Text parser — extract knowledge from plain text or Markdown files."""

from __future__ import annotations

import re
from pathlib import Path

from skill_anything.models import KnowledgeChunk, SourceType
from skill_anything.parsers.base import BaseParser


class TextParser(BaseParser):
    source_type = SourceType.TEXT

    def parse(self, source: str) -> list[KnowledgeChunk]:
        path = Path(source)
        if path.exists():
            text = path.read_text(encoding="utf-8")
            ref = str(path)
        else:
            text = source
            ref = "<inline>"

        sections = self._split_by_headings(text)
        if not sections:
            sections = [("", text)]

        chunks: list[KnowledgeChunk] = []
        idx = 0
        for heading, body in sections:
            if not body.strip():
                continue
            sub_chunks = self._split_into_chunks(body, max_chars=2000)
            for sub in sub_chunks:
                chunks.append(
                    KnowledgeChunk(
                        content=sub,
                        section=heading or f"Section {idx + 1}",
                        chunk_index=idx,
                        metadata={"source": ref},
                    )
                )
                idx += 1

        return chunks

    @staticmethod
    def _split_by_headings(text: str) -> list[tuple[str, str]]:
        """Split Markdown text by headings (# / ## / ###)."""
        heading_re = re.compile(r"^(#{1,4})\s+(.+)$", re.MULTILINE)
        matches = list(heading_re.finditer(text))

        if not matches:
            return [("", text)]

        sections: list[tuple[str, str]] = []

        if matches[0].start() > 0:
            preamble = text[: matches[0].start()].strip()
            if preamble:
                sections.append(("", preamble))

        for i, m in enumerate(matches):
            heading = m.group(2).strip()
            start = m.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            body = text[start:end].strip()
            if body:
                sections.append((heading, body))

        return sections
