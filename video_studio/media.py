"""Đọc thông tin file media bằng ffprobe."""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"}


class FFmpegMissing(RuntimeError):
    pass


def require_ffmpeg() -> tuple[str, str]:
    ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        raise FFmpegMissing("Không tìm thấy ffmpeg/ffprobe. Cài FFmpeg và thêm vào PATH.")
    return ffmpeg, ffprobe


@dataclass(frozen=True)
class MediaInfo:
    path: Path
    duration: float
    has_audio: bool
    width: int = 0
    height: int = 0


def probe(path: str | Path) -> MediaInfo:
    _, ffprobe = require_ffmpeg()
    out = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration:stream=codec_type,width,height",
         "-of", "json", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout
    data = json.loads(out)
    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), {})
    return MediaInfo(
        path=Path(path),
        duration=float(data.get("format", {}).get("duration", 0) or 0),
        has_audio=any(s.get("codec_type") == "audio" for s in streams),
        width=int(video.get("width", 0) or 0),
        height=int(video.get("height", 0) or 0),
    )


def find_videos(folder: str | Path) -> list[Path]:
    return sorted(p for p in Path(folder).rglob("*") if p.suffix.lower() in VIDEO_EXTS and p.is_file())
