"""Web parser — extract knowledge from webpages."""

from __future__ import annotations

import logging
import re

from skill_anything.models import KnowledgeChunk, Section, SourceType
from skill_anything.parsers.base import BaseParser

log = logging.getLogger(__name__)


class WebParser(BaseParser):
    source_type = SourceType.WEBPAGE

    def parse_sections(self, source: str) -> list[Section]:
        if not source.startswith(("http://", "https://")):
            raise ValueError(f"Expected a URL, got: {source}")

        html = self._fetch(source)
        title, text = self._extract_content(html)
        return self._build_sections(text, title, source)

    @staticmethod
    def _fetch(url: str) -> str:
        try:
            import httpx

            resp = httpx.get(url, follow_redirects=True, timeout=30.0, headers={
                "User-Agent": "Mozilla/5.0 (compatible; SkillAnything/1.0)"
            })
            resp.raise_for_status()
            return resp.text
        except ImportError:
            import urllib.request

            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (compatible; SkillAnything/1.0)"
            })
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read().decode("utf-8", errors="replace")

    def _extract_content(self, html: str) -> tuple[str, str]:
        """Extract readable text from HTML. Uses BeautifulSoup if available, else regex."""
        try:
            return self._extract_bs4(html)
        except ImportError:
            return self._extract_regex(html)

    @staticmethod
    def _extract_bs4(html: str) -> tuple[str, str]:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")

        for tag in soup(["script", "style", "nav", "header", "footer", "aside", "form"]):
            tag.decompose()

        title = soup.title.string.strip() if soup.title and soup.title.string else "Untitled"

        article = soup.find("article") or soup.find("main") or soup.find("body")
        if not article:
            article = soup

        paragraphs = []
        for elem in article.find_all(["p", "h1", "h2", "h3", "h4", "li", "blockquote", "pre"]):
            text = elem.get_text(strip=True)
            if len(text) > 20:
                if elem.name.startswith("h"):
                    text = f"\n## {text}\n"
                paragraphs.append(text)

        return title, "\n\n".join(paragraphs)

    @staticmethod
    def _extract_regex(html: str) -> tuple[str, str]:
        title_match = re.search(r"<title>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
        title = title_match.group(1).strip() if title_match else "Untitled"

        html = re.sub(r"<(script|style|nav|header|footer)[^>]*>.*?</\1>", "", html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r"<[^>]+>", "\n", html)
        html = re.sub(r"&nbsp;", " ", html)
        html = re.sub(r"&[a-z]+;", "", html)

        lines = [line.strip() for line in html.splitlines() if len(line.strip()) > 20]
        return title, "\n\n".join(lines)

    def _build_sections(
        self, text: str, title: str, source: str
    ) -> list[Section]:
        # The bs4 extractor already inserts "## heading" lines for h1..h4 tags.
        # Use the same heading-split logic as TextParser so long web pages
        # produce multiple sections instead of one giant blob.
        from skill_anything.parsers.text_parser import TextParser

        heading_sections = TextParser._split_by_headings(text)
        if not heading_sections or all(not h for h, _ in heading_sections):
            heading_sections = [(title or "Web Content", text)]

        sections: list[Section] = []
        chunk_idx = 0
        for sec_idx, (heading, body) in enumerate(heading_sections):
            if not body.strip():
                continue
            section_id = f"sec-{sec_idx + 1:03d}"
            section_title = heading or title or f"Section {sec_idx + 1}"
            section_chunks: list[KnowledgeChunk] = []
            for sub in self._split_into_chunks(body, max_chars=2000):
                section_chunks.append(
                    KnowledgeChunk(
                        content=sub,
                        section=section_title,
                        section_id=section_id,
                        chunk_index=chunk_idx,
                        metadata={"source": source, "title": title},
                    )
                )
                chunk_idx += 1
            if section_chunks:
                sections.append(
                    Section(
                        id=section_id,
                        title=section_title,
                        chunks=section_chunks,
                        metadata={"source": source, "title": title},
                    )
                )
        return sections
