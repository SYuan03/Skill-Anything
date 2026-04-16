"""Source parsers — extract knowledge chunks from various content sources."""

from __future__ import annotations

from importlib import import_module

from skill_anything.parsers.base import BaseParser

__all__ = [
    "BaseParser",
    "PDFParser",
    "VideoParser",
    "WebParser",
    "TextParser",
    "AudioParser",
    "RepoParser",
    "SkillParser",
]

_PARSER_MODULES = {
    "PDFParser": "skill_anything.parsers.pdf_parser",
    "VideoParser": "skill_anything.parsers.video_parser",
    "WebParser": "skill_anything.parsers.web_parser",
    "TextParser": "skill_anything.parsers.text_parser",
    "AudioParser": "skill_anything.parsers.audio_parser",
    "RepoParser": "skill_anything.parsers.repo_parser",
    "SkillParser": "skill_anything.parsers.skill_parser",
}


def __getattr__(name: str):
    if name == "BaseParser":
        return BaseParser
    if name in _PARSER_MODULES:
        module = import_module(_PARSER_MODULES[name])
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
