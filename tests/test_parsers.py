"""Tests for parsers."""

import tempfile

import pytest

from skill_anything.parsers.base import BaseParser
from skill_anything.parsers.text_parser import TextParser


def test_text_parser_from_file():
    content = "# Chapter 1\n\nThis is the first chapter content.\n\n# Chapter 2\n\nThis is the second chapter."
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(content)
        f.flush()
        parser = TextParser()
        chunks = parser.parse(f.name)
        assert len(chunks) >= 1
        assert chunks[0].section in ("Chapter 1", "Chapter 2", "Section 1")


def test_text_parser_from_inline():
    parser = TextParser()
    text = "This is a test content with enough words to be meaningful and useful for testing purposes."
    chunks = parser.parse(text)
    assert len(chunks) >= 1
    assert chunks[0].content


def test_text_parser_markdown_headings():
    parser = TextParser()
    md = "# Introduction\n\nSome intro text here.\n\n## Methods\n\nSome methods text.\n\n## Results\n\nSome results."
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(md)
        f.flush()
        chunks = parser.parse(f.name)
        sections = [c.section for c in chunks]
        assert any("Introduction" in s or "Methods" in s for s in sections)


def test_base_parser_split_chunks():
    long_text = "A" * 500 + "\n\n" + "B" * 500 + "\n\n" + "C" * 500
    chunks = BaseParser._split_into_chunks(long_text, max_chars=600, overlap=50)
    assert len(chunks) >= 2
    for chunk in chunks:
        assert len(chunk) <= 700


def test_text_parser_empty_file():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("")
        f.flush()
        parser = TextParser()
        chunks = parser.parse(f.name)
        assert len(chunks) == 0


def test_web_parser_rejects_non_url():
    from skill_anything.parsers.web_parser import WebParser
    parser = WebParser()
    with pytest.raises(ValueError, match="Expected a URL"):
        parser.parse("not-a-url")


def test_video_parser_url_detection():
    from skill_anything.parsers.video_parser import VideoParser
    parser = VideoParser()
    assert parser._is_youtube_url("https://www.youtube.com/watch?v=abc123")
    assert parser._is_youtube_url("https://youtu.be/abc123")
    assert not parser._is_youtube_url("https://example.com")
    assert parser._is_subtitle_file("test.srt")
    assert parser._is_subtitle_file("test.vtt")
    assert not parser._is_subtitle_file("test.pdf")


def test_video_parser_srt_parsing():
    from skill_anything.parsers.video_parser import VideoParser
    srt = "1\n00:00:01,000 --> 00:00:05,000\nHello world\n\n2\n00:00:06,000 --> 00:00:10,000\nThis is a test"
    segments = VideoParser._parse_srt_text(srt)
    assert len(segments) == 2
    assert segments[0][1] == "Hello world"
    assert segments[1][1] == "This is a test"
