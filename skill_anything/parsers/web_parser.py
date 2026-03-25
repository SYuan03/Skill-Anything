"""Web parser — extract knowledge from webpages."""

from __future__ import annotations

import logging
import re

from skill_anything.models import KnowledgeChunk, SourceType
from skill_anything.parsers.base import BaseParser

log = logging.getLogger(__name__)


class WebParser(BaseParser):
    source_type = SourceType.WEBPAGE

    def parse(self, source: str) -> list[KnowledgeChunk]:
        if not source.startswith(("http://", "https://")):
            raise ValueError(f"Expected a URL, got: {source}")

        html = self._fetch(source)
        title, text = self._extract_content(html)
        return self._build_chunks(text, title, source)

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

    def _build_chunks(
        self, text: str, title: str, source: str
    ) -> list[KnowledgeChunk]:
        raw_chunks = self._split_into_chunks(text)

        return [
            KnowledgeChunk(
                content=chunk,
                section=title,
                chunk_index=i,
                metadata={"source": source, "title": title},
            )
            for i, chunk in enumerate(raw_chunks)
        ]
