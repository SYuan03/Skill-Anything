"""Text parser — extract knowledge from plain text or Markdown files."""

from __future__ import annotations

import re
from pathlib import Path

from skill_anything.models import KnowledgeChunk, Section, SourceType
from skill_anything.parsers.base import BaseParser


class TextParser(BaseParser):
    source_type = SourceType.TEXT
    _FILE_SUFFIXES = {".md", ".markdown", ".txt", ".text", ".rst"}

    def parse_sections(self, source: str) -> list[Section]:
        # Inline text strings (esp. multi-line) can exceed OS path-length
        # limits, which makes a naive Path(source).exists() raise OSError.
        # Anything with newlines or beyond typical path length is treated as
        # inline content, not a path.
        looks_like_path = "\n" not in source and len(source) < 512
        path = Path(source) if looks_like_path else None
        if path is not None and path.exists():
            text = path.read_text(encoding="utf-8")
            ref = str(path)
        else:
            if path is not None and path.suffix.lower() in self._FILE_SUFFIXES:
                raise FileNotFoundError(f"Text source file not found: {source}")
            text = source
            ref = "<inline>"

        heading_sections = self._split_by_headings(text)
        if not heading_sections:
            heading_sections = [("", text)]

        sections: list[Section] = []
        chunk_idx = 0
        for sec_idx, (heading, body) in enumerate(heading_sections):
            if not body.strip():
                continue
            section_id = f"sec-{sec_idx + 1:03d}"
            section_title = heading or f"Section {sec_idx + 1}"
            section_chunks: list[KnowledgeChunk] = []
            for sub in self._split_into_chunks(body, max_chars=2000):
                section_chunks.append(
                    KnowledgeChunk(
                        content=sub,
                        section=section_title,
                        section_id=section_id,
                        chunk_index=chunk_idx,
                        metadata={"source": ref},
                    )
                )
                chunk_idx += 1
            if section_chunks:
                sections.append(
                    Section(
                        id=section_id,
                        title=section_title,
                        chunks=section_chunks,
                        metadata={"source": ref},
                    )
                )
        return sections

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
