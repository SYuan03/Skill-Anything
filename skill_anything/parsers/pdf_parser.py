"""PDF parser — extract knowledge from PDF files (books, papers, docs).

v0.3 adds outline-aware sectioning: when a PDF has a TOC/bookmarks (most
books and many papers do), each top-level outline entry becomes a Section
covering its page range. PDFs without an outline fall back to fixed-size
page-range sections so long documents are still chunked evenly.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from skill_anything.models import KnowledgeChunk, Section, SourceType
from skill_anything.parsers.base import BaseParser

log = logging.getLogger(__name__)

# Fallback: pages per section when no outline is available.
PAGES_PER_FALLBACK_SECTION = 20


@dataclass
class _OutlineEntry:
    title: str
    page: int  # 1-based


class PDFParser(BaseParser):
    source_type = SourceType.PDF

    def parse_sections(self, source: str) -> list[Section]:
        path = Path(source)
        if not path.exists():
            raise FileNotFoundError(f"PDF not found: {source}")

        pages, outline = self._extract(path)
        if not pages:
            return []

        page_ranges = self._build_page_ranges(pages, outline)
        return self._build_sections(pages, page_ranges, source)

    # ------------------------------------------------------------------
    # Extraction
    # ------------------------------------------------------------------

    def _extract(self, path: Path) -> tuple[list[tuple[int, str]], list[_OutlineEntry]]:
        """Try multiple backends; return (pages, outline)."""
        for method in [self._try_pdfplumber, self._try_pymupdf, self._try_pypdf]:
            result = method(path)
            if result is not None:
                pages, outline = result
                if pages:
                    # If we got pages but no outline, try to pull an outline
                    # from pymupdf as a supplementary step (it has the best
                    # bookmark access). Safe even if pymupdf is the backend.
                    if not outline:
                        outline = self._try_outline_pymupdf(path)
                    return pages, outline

        raise ImportError(
            "No PDF library available. Install one of: "
            "pdfplumber, pymupdf (fitz), pypdf\n"
            "  pip install pdfplumber"
        )

    @staticmethod
    def _try_outline_pymupdf(path: Path) -> list[_OutlineEntry]:
        try:
            import fitz
        except ImportError:
            return []
        outline: list[_OutlineEntry] = []
        try:
            doc = fitz.open(path)
            try:
                for level, title, page in doc.get_toc() or []:
                    if level == 1 and title and isinstance(page, int) and page >= 1:
                        outline.append(_OutlineEntry(title=title.strip(), page=page))
            finally:
                doc.close()
        except Exception as e:
            log.debug("pymupdf outline fallback failed: %s", e)
        return outline

    @staticmethod
    def _try_pdfplumber(path: Path) -> tuple[list[tuple[int, str]], list[_OutlineEntry]] | None:
        try:
            import pdfplumber
        except ImportError:
            return None

        pages: list[tuple[int, str]] = []
        outline: list[_OutlineEntry] = []
        with pdfplumber.open(path) as pdf:
            for i, page in enumerate(pdf.pages):
                text = page.extract_text() or ""
                if text.strip():
                    pages.append((i + 1, text))
            # pdfplumber exposes outline lazily; fall through to pymupdf for it.
        return pages, outline

    @staticmethod
    def _try_pymupdf(path: Path) -> tuple[list[tuple[int, str]], list[_OutlineEntry]] | None:
        try:
            import fitz  # pymupdf
        except ImportError:
            return None

        pages: list[tuple[int, str]] = []
        outline: list[_OutlineEntry] = []
        doc = fitz.open(path)
        try:
            for i, page in enumerate(doc):
                text = page.get_text()
                if text.strip():
                    pages.append((i + 1, text))
            try:
                toc = doc.get_toc() or []
                # Each entry: [level, title, page] (page is 1-based)
                for level, title, page in toc:
                    if level == 1 and title and isinstance(page, int) and page >= 1:
                        outline.append(_OutlineEntry(title=title.strip(), page=page))
            except Exception as e:
                log.debug("pymupdf get_toc failed: %s", e)
        finally:
            doc.close()
        return pages, outline

    @staticmethod
    def _try_pypdf(path: Path) -> tuple[list[tuple[int, str]], list[_OutlineEntry]] | None:
        try:
            from pypdf import PdfReader
        except ImportError:
            return None

        pages: list[tuple[int, str]] = []
        outline: list[_OutlineEntry] = []
        reader = PdfReader(path)
        for i, page in enumerate(reader.pages):
            text = page.extract_text() or ""
            if text.strip():
                pages.append((i + 1, text))
        # pypdf outline access is fragile; skip and rely on fallback.
        return pages, outline

    # ------------------------------------------------------------------
    # Sectioning
    # ------------------------------------------------------------------

    @staticmethod
    def _build_page_ranges(
        pages: list[tuple[int, str]], outline: list[_OutlineEntry]
    ) -> list[tuple[str, int, int]]:
        """Return [(title, start_page, end_page)] covering all pages.

        Uses the outline when available, otherwise fixed-size page ranges.
        """
        if not pages:
            return []
        first_page = pages[0][0]
        last_page = pages[-1][0]

        # Outline path: use top-level entries, clipped to actual page range.
        clean_outline = sorted(
            {e.page: e for e in outline if first_page <= e.page <= last_page}.values(),
            key=lambda e: e.page,
        )
        if clean_outline:
            if clean_outline[0].page > first_page:
                clean_outline.insert(0, _OutlineEntry(title="Frontmatter", page=first_page))
            ranges: list[tuple[str, int, int]] = []
            for i, entry in enumerate(clean_outline):
                start = entry.page
                end = clean_outline[i + 1].page - 1 if i + 1 < len(clean_outline) else last_page
                if end < start:
                    end = start
                ranges.append((entry.title, start, end))
            return ranges

        # Fallback path: N pages per section.
        ranges = []
        sec_idx = 1
        cursor = first_page
        while cursor <= last_page:
            end = min(cursor + PAGES_PER_FALLBACK_SECTION - 1, last_page)
            ranges.append((f"Pages {cursor}-{end}", cursor, end))
            cursor = end + 1
            sec_idx += 1
        return ranges

    def _build_sections(
        self,
        pages: list[tuple[int, str]],
        ranges: list[tuple[str, int, int]],
        source: str,
    ) -> list[Section]:
        # page -> text lookup for quick range slicing
        page_text = dict(pages)
        sections: list[Section] = []
        chunk_idx = 0

        for sec_idx, (title, start, end) in enumerate(ranges):
            body_parts = [page_text[p] for p in range(start, end + 1) if p in page_text]
            body = "\n\n".join(body_parts).strip()
            if not body:
                continue

            section_id = f"sec-{sec_idx + 1:03d}"
            section_chunks: list[KnowledgeChunk] = []
            for sub in self._split_into_chunks(body, max_chars=2000):
                section_chunks.append(
                    KnowledgeChunk(
                        content=sub,
                        section=title,
                        section_id=section_id,
                        chunk_index=chunk_idx,
                        source_page=start,
                        metadata={"source": source, "page_range": f"{start}-{end}"},
                    )
                )
                chunk_idx += 1
            if section_chunks:
                sections.append(
                    Section(
                        id=section_id,
                        title=title,
                        chunks=section_chunks,
                        metadata={
                            "source": source,
                            "page_start": start,
                            "page_end": end,
                        },
                    )
                )
        return sections
