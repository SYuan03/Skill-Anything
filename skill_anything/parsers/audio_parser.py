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

from skill_anything.models import KnowledgeChunk, Section, SourceType
from skill_anything.parsers.base import BaseParser

log = logging.getLogger(__name__)

SECTION_DURATION_SECONDS = 300


class AudioParser(BaseParser):
    source_type = SourceType.AUDIO

    SUPPORTED_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".wma"}

    def parse_sections(self, source: str) -> list[Section]:
        p = Path(source)
        if p.suffix.lower() not in self.SUPPORTED_EXTENSIONS:
            raise ValueError(
                f"Unsupported audio format: {p.suffix}. "
                f"Supported: {', '.join(sorted(self.SUPPORTED_EXTENSIONS))}"
            )
        if not p.exists():
            raise FileNotFoundError(f"Audio file not found: {source}")

        segments = self._transcribe(source)
        return self._build_sections(segments, source)

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

    def _build_sections(
        self, segments: list[tuple[str, str]], source: str
    ) -> list[Section]:
        if not segments:
            return []

        sections: list[Section] = []
        chunk_index = 0
        sec_idx = 0
        bucket_start = 0
        bucket: list[tuple[int, str, str]] = []

        for ts, text in segments:
            sec_time = self._timestamp_to_seconds(ts)
            if sec_time - bucket_start >= SECTION_DURATION_SECONDS and bucket:
                sec_idx += 1
                chunk_index = self._flush(sections, bucket, sec_idx, chunk_index, source)
                bucket_start = sec_time
                bucket = []
            bucket.append((sec_time, ts, text))

        if bucket:
            sec_idx += 1
            self._flush(sections, bucket, sec_idx, chunk_index, source)

        return sections

    def _flush(
        self,
        sections: list[Section],
        segs: list[tuple[int, str, str]],
        sec_idx: int,
        chunk_index: int,
        source: str,
    ) -> int:
        if not segs:
            return chunk_index
        section_id = f"sec-{sec_idx:03d}"
        first_ts = segs[0][1]
        last_ts = segs[-1][1]
        title = f"{first_ts}–{last_ts}"
        body = "\n".join(text for _, _, text in segs)
        section_chunks: list[KnowledgeChunk] = []
        for sub in self._split_into_chunks(body, max_chars=1500):
            section_chunks.append(
                KnowledgeChunk(
                    content=sub,
                    section=title,
                    section_id=section_id,
                    chunk_index=chunk_index,
                    source_time=first_ts,
                    metadata={"source": source, "time_range": title},
                )
            )
            chunk_index += 1
        if section_chunks:
            sections.append(
                Section(
                    id=section_id,
                    title=title,
                    chunks=section_chunks,
                    metadata={
                        "source": source,
                        "time_start": first_ts,
                        "time_end": last_ts,
                    },
                )
            )
        return chunk_index

    @staticmethod
    def _timestamp_to_seconds(ts: str) -> int:
        parts = ts.split(":")
        try:
            if len(parts) == 2:
                return int(parts[0]) * 60 + int(parts[1])
            if len(parts) == 3:
                return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        except ValueError:
            return 0
        return 0
