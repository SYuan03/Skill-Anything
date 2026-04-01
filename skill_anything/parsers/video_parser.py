"""Video parser — extract knowledge from video transcripts.

Supports:
- YouTube URLs (via youtube-transcript-api or yt-dlp)
- Local subtitle files (.srt, .vtt)
- Local video files (requires whisper or ffmpeg for subtitle extraction)
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from skill_anything.models import KnowledgeChunk, SourceType
from skill_anything.parsers.base import BaseParser

log = logging.getLogger(__name__)


class VideoParser(BaseParser):
    source_type = SourceType.VIDEO

    def parse(self, source: str) -> list[KnowledgeChunk]:
        if self._is_youtube_url(source):
            segments = self._parse_youtube(source)
        elif self._is_subtitle_file(source):
            segments = self._parse_subtitle_file(source)
        else:
            segments = self._parse_local_video(source)

        return self._build_chunks(segments, source)

    @staticmethod
    def _is_youtube_url(source: str) -> bool:
        return bool(re.match(r"https?://(www\.)?(youtube\.com|youtu\.be)/", source))

    @staticmethod
    def _is_subtitle_file(source: str) -> bool:
        return Path(source).suffix.lower() in (".srt", ".vtt", ".txt")

    def _parse_youtube(self, url: str) -> list[tuple[str, str]]:
        """Extract transcript from a YouTube video. Returns list of (timestamp, text)."""
        for method in [self._try_youtube_transcript_api, self._try_yt_dlp]:
            result = method(url)
            if result:
                return result

        raise ImportError(
            "No YouTube transcript library available. Install one of:\n"
            "  pip install youtube-transcript-api\n"
            "  pip install yt-dlp"
        )

    @staticmethod
    def _try_youtube_transcript_api(url: str) -> list[tuple[str, str]] | None:
        try:
            from youtube_transcript_api import YouTubeTranscriptApi
        except ImportError:
            return None

        video_id = None
        m = re.search(r"(?:v=|youtu\.be/)([\w-]{11})", url)
        if m:
            video_id = m.group(1)
        if not video_id:
            return None

        try:
            ytt = YouTubeTranscriptApi()
            try:
                transcript = ytt.fetch(video_id, languages=["zh-Hans", "zh", "en"])
            except Exception:
                transcript = ytt.fetch(video_id)
        except Exception as e:
            log.warning("Failed to get YouTube transcript: %s", e)
            return None

        segments = []
        for entry in transcript:
            start = getattr(entry, "start", 0) if not isinstance(entry, dict) else entry.get("start", 0)
            text = getattr(entry, "text", "") if not isinstance(entry, dict) else entry.get("text", "")
            mins, secs = divmod(int(start), 60)
            timestamp = f"{mins:02d}:{secs:02d}"
            if text:
                segments.append((timestamp, text))

        return segments if segments else None

    @staticmethod
    def _try_yt_dlp(url: str) -> list[tuple[str, str]] | None:
        try:
            import subprocess

            result = subprocess.run(
                ["yt-dlp", "--write-auto-sub", "--skip-download", "--sub-format", "vtt",
                 "--sub-langs", "zh,en", "-o", "/tmp/sa_video_sub", url],
                capture_output=True, text=True, timeout=60,
            )
            if result.returncode != 0:
                return None

            for ext in [".zh.vtt", ".en.vtt", ".vtt"]:
                sub_path = Path(f"/tmp/sa_video_sub{ext}")
                if sub_path.exists():
                    text = sub_path.read_text(encoding="utf-8")
                    segments = VideoParser._parse_vtt_text(text)
                    sub_path.unlink(missing_ok=True)
                    return segments if segments else None

        except (ImportError, FileNotFoundError, subprocess.TimeoutExpired):
            return None

        return None

    def _parse_subtitle_file(self, path: str) -> list[tuple[str, str]]:
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"Subtitle file not found: {path}")

        text = p.read_text(encoding="utf-8")
        suffix = p.suffix.lower()

        if suffix == ".srt":
            return self._parse_srt_text(text)
        elif suffix == ".vtt":
            return self._parse_vtt_text(text)
        else:
            return [("00:00", line.strip()) for line in text.splitlines() if line.strip()]

    def _parse_local_video(self, path: str) -> list[tuple[str, str]]:
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"Video file not found: {path}")

        srt_path = p.with_suffix(".srt")
        vtt_path = p.with_suffix(".vtt")
        if srt_path.exists():
            return self._parse_subtitle_file(str(srt_path))
        if vtt_path.exists():
            return self._parse_subtitle_file(str(vtt_path))

        raise FileNotFoundError(
            f"No subtitle file found alongside {path}. "
            f"Please provide a .srt or .vtt file, or use a YouTube URL.\n"
            f"You can generate subtitles with: whisper {path} --output_format srt"
        )

    @staticmethod
    def _parse_srt_text(text: str) -> list[tuple[str, str]]:
        blocks = re.split(r"\n\n+", text.strip())
        segments: list[tuple[str, str]] = []
        for block in blocks:
            lines = block.strip().splitlines()
            if len(lines) < 3:
                continue
            time_match = re.match(r"(\d{2}:\d{2}:\d{2})", lines[1])
            timestamp = time_match.group(1)[:5] if time_match else "00:00"
            content = " ".join(lines[2:]).strip()
            content = re.sub(r"<[^>]+>", "", content)
            if content:
                segments.append((timestamp, content))
        return segments

    @staticmethod
    def _parse_vtt_text(text: str) -> list[tuple[str, str]]:
        lines = text.strip().splitlines()
        segments: list[tuple[str, str]] = []
        i = 0
        while i < len(lines):
            if "-->" in lines[i]:
                time_match = re.match(r"(\d{2}:\d{2})", lines[i])
                timestamp = time_match.group(1) if time_match else "00:00"
                content_lines = []
                i += 1
                while i < len(lines) and lines[i].strip() and "-->" not in lines[i]:
                    cleaned = re.sub(r"<[^>]+>", "", lines[i].strip())
                    if cleaned:
                        content_lines.append(cleaned)
                    i += 1
                if content_lines:
                    segments.append((timestamp, " ".join(content_lines)))
            else:
                i += 1
        return segments

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
