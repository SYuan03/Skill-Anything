"""Audio parser — transcribe audio files into knowledge chunks.

Supports:
- Local transcription via openai-whisper
- OpenAI Whisper API fallback (requires API key)
- Formats: .mp3, .wav, .m4a, .aac, .flac, .ogg, .wma
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from skill_anything.models import KnowledgeChunk, SourceType
from skill_anything.parsers.base import BaseParser

log = logging.getLogger(__name__)


class AudioParser(BaseParser):
    source_type = SourceType.AUDIO

    SUPPORTED_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".wma"}

    def parse(self, source: str) -> list[KnowledgeChunk]:
        p = Path(source)
        if p.suffix.lower() not in self.SUPPORTED_EXTENSIONS:
            raise ValueError(
                f"Unsupported audio format: {p.suffix}. "
                f"Supported: {', '.join(sorted(self.SUPPORTED_EXTENSIONS))}"
            )
        if not p.exists():
            raise FileNotFoundError(f"Audio file not found: {source}")

        segments = self._transcribe(source)
        return self._build_chunks(segments, source)

    def _transcribe(self, path: str) -> list[tuple[str, str]]:
        """Transcribe audio. Try local Whisper first, then OpenAI API."""
        for method in [self._try_local_whisper, self._try_openai_whisper_api]:
            result = method(path)
            if result:
                return result

        raise ImportError(
            "No audio transcription backend available. Install one of:\n"
            "  pip install openai-whisper      # local transcription\n"
            "  # Or set SKILL_ANYTHING_API_KEY for OpenAI Whisper API"
        )

    @staticmethod
    def _try_local_whisper(path: str) -> list[tuple[str, str]] | None:
        """Use the openai-whisper package for local transcription."""
        try:
            import whisper
        except ImportError:
            return None

        log.info("Transcribing with local Whisper model...")
        model = whisper.load_model("base")
        result = model.transcribe(path)

        segments = []
        for seg in result.get("segments", []):
            start = seg.get("start", 0)
            text = seg.get("text", "").strip()
            mins, secs = divmod(int(start), 60)
            timestamp = f"{mins:02d}:{secs:02d}"
            if text:
                segments.append((timestamp, text))

        return segments if segments else None

    @staticmethod
    def _try_openai_whisper_api(path: str) -> list[tuple[str, str]] | None:
        """Use the OpenAI Whisper API (requires API key)."""
        try:
            from dotenv import load_dotenv

            for candidate in [Path.cwd() / ".env", Path(__file__).resolve().parent.parent.parent / ".env"]:
                if candidate.exists():
                    load_dotenv(candidate, override=False)
                    break
        except ImportError:
            pass

        api_key = os.getenv("SKILL_ANYTHING_API_KEY") or os.getenv("OPENAI_API_KEY", "")
        if not api_key:
            return None

        try:
            from openai import OpenAI
        except ImportError:
            return None

        api_base = os.getenv("SKILL_ANYTHING_API_BASE") or os.getenv("OPENAI_API_BASE")
        proxy = os.getenv("SKILL_ANYTHING_PROXY") or os.getenv("HTTPS_PROXY") or os.getenv("HTTP_PROXY")
        model = os.getenv("SKILL_ANYTHING_WHISPER_MODEL", "whisper-1")

        kwargs: dict = {"api_key": api_key}
        if api_base:
            kwargs["base_url"] = api_base
        if proxy:
            try:
                import httpx
                kwargs["http_client"] = httpx.Client(proxy=proxy, timeout=300.0)
            except ImportError:
                pass

        client = OpenAI(**kwargs)

        log.info("Transcribing with OpenAI Whisper API (model=%s)...", model)
        try:
            with open(path, "rb") as audio_file:
                resp = client.audio.transcriptions.create(
                    model=model,
                    file=audio_file,
                    response_format="verbose_json",
                    timestamp_granularities=["segment"],
                )

            segments = []
            for seg in getattr(resp, "segments", []) or []:
                start = seg.get("start", 0) if isinstance(seg, dict) else getattr(seg, "start", 0)
                text = seg.get("text", "").strip() if isinstance(seg, dict) else getattr(seg, "text", "").strip()
                mins, secs = divmod(int(start), 60)
                timestamp = f"{mins:02d}:{secs:02d}"
                if text:
                    segments.append((timestamp, text))

            # Fallback: if no segments but there is text, use the full text
            if not segments:
                full_text = getattr(resp, "text", "").strip()
                if full_text:
                    segments = [("00:00", full_text)]

            return segments if segments else None
        except Exception as e:
            log.warning("Whisper API transcription failed: %s", e)
            return None

    def _build_chunks(
        self, segments: list[tuple[str, str]], source: str
    ) -> list[KnowledgeChunk]:
        combined = "\n".join(text for _, text in segments)
        raw_chunks = self._split_into_chunks(combined, max_chars=1500)

        chunks: list[KnowledgeChunk] = []
        seg_idx = 0
        char_offset = 0

        for i, chunk_text in enumerate(raw_chunks):
            timestamp = segments[min(seg_idx, len(segments) - 1)][0] if segments else "00:00"

            chunks.append(
                KnowledgeChunk(
                    content=chunk_text,
                    section=f"@{timestamp}",
                    chunk_index=i,
                    source_time=timestamp,
                    metadata={"source": source},
                )
            )

            char_offset += len(chunk_text)
            while seg_idx < len(segments) - 1:
                seg_len = len(segments[seg_idx][1]) + 1
                if seg_len > char_offset:
                    break
                char_offset -= seg_len
                seg_idx += 1

        return chunks
