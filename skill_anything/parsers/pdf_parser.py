"""PDF parser — extract knowledge from PDF files (books, papers, docs)."""

from __future__ import annotations

import logging
from pathlib import Path

from skill_anything.models import KnowledgeChunk, SourceType
from skill_anything.parsers.base import BaseParser

log = logging.getLogger(__name__)


class PDFParser(BaseParser):
    source_type = SourceType.PDF

    def parse(self, source: str) -> list[KnowledgeChunk]:
        path = Path(source)
        if not path.exists():
            raise FileNotFoundError(f"PDF not found: {source}")

        text_by_page = self._extract_text(path)
        return self._build_chunks(text_by_page, source)

    def _extract_text(self, path: Path) -> list[tuple[int, str]]:
        """Try multiple backends to extract text from a PDF."""
        for method in [self._try_pdfplumber, self._try_pymupdf, self._try_pypdf]:
            result = method(path)
            if result:
                return result

        raise ImportError(
            "No PDF library available. Install one of: "
            "pdfplumber, pymupdf (fitz), pypdf\n"
            "  pip install pdfplumber"
        )

    @staticmethod
    def _try_pdfplumber(path: Path) -> list[tuple[int, str]] | None:
        try:
            import pdfplumber
        except ImportError:
            return None

        pages = []
        with pdfplumber.open(path) as pdf:
            for i, page in enumerate(pdf.pages):
                text = page.extract_text() or ""
                if text.strip():
                    pages.append((i + 1, text))
        return pages if pages else None

    @staticmethod
    def _try_pymupdf(path: Path) -> list[tuple[int, str]] | None:
        try:
            import fitz  # pymupdf
        except ImportError:
            return None

        pages = []
        doc = fitz.open(path)
        for i, page in enumerate(doc):
            text = page.get_text()
            if text.strip():
                pages.append((i + 1, text))
        doc.close()
        return pages if pages else None

    @staticmethod
    def _try_pypdf(path: Path) -> list[tuple[int, str]] | None:
        try:
            from pypdf import PdfReader
        except ImportError:
            return None

        pages = []
        reader = PdfReader(path)
        for i, page in enumerate(reader.pages):
            text = page.extract_text() or ""
            if text.strip():
                pages.append((i + 1, text))
        return pages if pages else None

    def _build_chunks(
        self, pages: list[tuple[int, str]], source: str
    ) -> list[KnowledgeChunk]:
        full_text = "\n\n".join(text for _, text in pages)
        raw_chunks = self._split_into_chunks(full_text)

        chunks: list[KnowledgeChunk] = []
        page_idx = 0
        char_offset = 0

        for i, chunk_text in enumerate(raw_chunks):
            while page_idx < len(pages) - 1:
                page_num, page_text = pages[page_idx]
                if char_offset + len(page_text) + 2 > full_text.find(chunk_text[:50]):
                    break
                char_offset += len(page_text) + 2
                page_idx += 1

            chunks.append(
                KnowledgeChunk(
                    content=chunk_text,
                    section=f"Page {pages[page_idx][0]}" if pages else "",
                    chunk_index=i,
                    source_page=pages[page_idx][0] if pages else None,
                    metadata={"source": source},
                )
            )

        return chunks
