"""Ảnh bìa (thumbnail) YouTube: ảnh cảnh + tiêu đề chữ to + nhân vật (nếu có)."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from . import captions
from .media import require_ffmpeg
from .pipeline import _run
from .settings import TitleSettings

YOUTUBE_SIZE = (1280, 720)  # kích thước YouTube khuyên dùng; Shorts dùng 720x1280


def _ass(width: int, height: int, text: str, title: TitleSettings, right_margin: int) -> str:
    size = int(height * (0.16 if width >= height else 0.09))
    outline = max(4, size // 12)
    return "\n".join([
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {width}", f"PlayResY: {height}", "WrapStyle: 0", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding",
        # Chữ vàng viền đen dày, canh trái phía trên: kiểu thumbnail dễ đọc trên điện thoại.
        f"Style: Thumb,{title.font},{size},&H0000E5FF,&H000000FF,&H00000000,&H96000000,-1,0,0,0,100,100,0,0,1,"
        f"{outline},{outline // 2},7,{int(width * 0.05)},{right_margin},{int(height * 0.08)},1",
        "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
        f"Dialogue: 0,0:00:00.00,0:00:10.00,Thumb,,0,0,0,,{captions._escape(text.strip().upper())}",
    ]) + "\n"


def make_thumbnail(image: str | Path, text: str, out_path: str | Path, title: TitleSettings | None = None,
                   character: Path | None = None, size: tuple[int, int] = YOUTUBE_SIZE) -> Path:
    """`character`: PNG nhân vật (nền trong suốt) đặt góc phải dưới, chữ chừa chỗ cho nhân vật."""
    ffmpeg, _ = require_ffmpeg()
    title = title or TitleSettings()
    w, h = size
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="vstudio_thumb_"))
    try:
        right = int(w * (0.42 if character is not None and w >= h else 0.05))
        (work / "thumb.ass").write_text(_ass(w, h, text, title, right), encoding="utf-8")
        bg = (f"[0:v]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1,"
              f"eq=saturation=1.25:contrast=1.08,vignette=PI/5")
        cmd = [ffmpeg, "-y", "-v", "error", "-f", "image2", "-pattern_type", "none", "-i", str(Path(image).resolve())]
        if character is not None:
            cmd += ["-i", str(Path(character).resolve())]
            ch = int(h * (0.9 if w >= h else 0.5))
            graph = (f"{bg}[b];[1:v]scale=-2:{ch},format=rgba[c];"
                     f"[b][c]overlay=x=W-w-{int(w * 0.03)}:y=H-h:format=auto,subtitles=thumb.ass[v]")
        else:
            graph = f"{bg},subtitles=thumb.ass[v]"
        tmp = work / "thumb.jpg"
        cmd += ["-filter_complex", graph, "-map", "[v]", "-frames:v", "1", "-q:v", "3", tmp.name]
        _run(cmd, None, cwd=work)
        shutil.move(str(tmp), out_path)
        return out_path
    finally:
        shutil.rmtree(work, ignore_errors=True)
