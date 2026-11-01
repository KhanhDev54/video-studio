"""Tự kiểm tra bản đóng gói (.exe): nạp thư viện, tìm FFmpeg, tạo một nhân vật rồi dựng thử
một cảnh hoạt hình 1 giây có nhân vật đó.

Bản .exe dạng cửa sổ không có console nên kết quả ghi ra file JSON."""

from __future__ import annotations

import json
import subprocess
import tempfile
import traceback
from pathlib import Path


def selftest(out: str | Path, tts: bool = False) -> int:
    report: dict = {"ok": False}
    try:
        from PySide6 import QtMultimedia, QtWidgets  # noqa: F401
        import PySide6

        from . import __version__
        from .character_maker import CharacterSpec, make_character
        from .media import NO_WINDOW, app_root, probe, require_ffmpeg
        from .scenes import render_scenes
        from .settings import RenderSettings

        report.update(version=__version__, pyside=PySide6.__version__, app_root=str(app_root()))
        ffmpeg, _ = require_ffmpeg()
        report["ffmpeg"] = ffmpeg
        with tempfile.TemporaryDirectory(prefix="vstudio_selftest_") as d:
            img = Path(d) / "ảnh.png"
            subprocess.run([ffmpeg, "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=0x2060a0:s=320x180",
                            "-frames:v", "1", str(img)], check=True, creationflags=NO_WINDOW)
            s = RenderSettings()
            s.output.width, s.output.height, s.output.preset = 320, 180, "ultrafast"
            s.title.text, s.title.font_size = "Tự kiểm tra", 20
            cast = Path(d) / "dàn nhân vật"
            make_character(CharacterSpec("Mèo"), cast)
            s.scene.script, s.scene.image_dir, s.scene.seconds_per_scene = "Mèo: Xin chào.", d, 1.0
            s.scene.character_dir, s.scene.lipsync = str(cast), "loudness"
            s.scene.thumbnail = False
            if tts:
                s.voice.enabled = True
            video = render_scenes(s, Path(d) / "kiểm tra.mp4")
            report["video_seconds"] = round(probe(video).duration, 2)
        report["ok"] = True
    except Exception:  # ghi lại mọi lỗi để đọc trong CI
        report["error"] = traceback.format_exc()
    Path(out).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if report["ok"] else 1
