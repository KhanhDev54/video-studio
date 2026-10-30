"""Đọc thông tin file media bằng ffprobe."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"}

# Trên Windows, app GUI gọi ffmpeg sẽ bật cửa sổ console đen nếu không có cờ này.
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class FFmpegMissing(RuntimeError):
    pass


def _candidate_dirs() -> list[Path]:
    """Các thư mục tìm ffmpeg trước khi tra PATH, theo thứ tự ưu tiên."""
    dirs = []
    if os.environ.get("VSTUDIO_FFMPEG_DIR"):
        dirs.append(Path(os.environ["VSTUDIO_FFMPEG_DIR"]))
    app_root = Path(__file__).resolve().parent.parent
    dirs += [app_root / "ffmpeg" / "bin", app_root / "ffmpeg"]
    if sys.platform == "win32" and os.environ.get("LOCALAPPDATA"):
        # winget đặt lối tắt ở đây; PATH chỉ có hiệu lực sau khi mở lại cửa sổ lệnh.
        dirs.append(Path(os.environ["LOCALAPPDATA"]) / "Microsoft" / "WinGet" / "Links")
    return dirs


def require_ffmpeg() -> tuple[str, str]:
    for d in _candidate_dirs():
        ffmpeg, ffprobe = shutil.which("ffmpeg", path=str(d)), shutil.which("ffprobe", path=str(d))
        if ffmpeg and ffprobe:
            return ffmpeg, ffprobe
    ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        raise FFmpegMissing("Không tìm thấy ffmpeg/ffprobe. Cài FFmpeg và thêm vào PATH, "
                            "hoặc chép ffmpeg.exe + ffprobe.exe vào thư mục ffmpeg\\bin cạnh app.")
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
    # ffprobe in JSON dạng UTF-8; Windows mặc định giải mã theo code page (cp1258...)
    # nên tên file tiếng Việt sẽ lỗi nếu không chỉ rõ encoding.
    proc = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration:stream=codec_type,width,height",
         "-of", "json", str(path)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", creationflags=NO_WINDOW,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"Không đọc được file {Path(path).name}: {proc.stderr.strip()[-300:]}")
    data = json.loads(proc.stdout or "{}")
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
