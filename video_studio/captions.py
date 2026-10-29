"""Tạo phụ đề và tiêu đề dưới dạng một file ASS để ffmpeg/libass vẽ lên video.

Dùng ASS thay cho drawtext vì libass tự tìm font hệ thống theo tên (hiển thị
tiếng Việt đúng) và tránh phải escape đường dẫn font trên Windows."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .settings import SubtitleSettings, TitleSettings


@dataclass(frozen=True)
class Cue:
    start: float
    end: float
    text: str


def group_words(words: list[Cue], max_words: int) -> list[Cue]:
    """Gộp các mốc từng-từ thành dòng phụ đề, ngắt ở dấu câu hoặc khi đủ max_words."""
    lines: list[Cue] = []
    buf: list[Cue] = []
    for w in words:
        buf.append(w)
        if len(buf) >= max_words or re.search(r"[.!?,;:…]$", w.text):
            lines.append(Cue(buf[0].start, buf[-1].end, " ".join(x.text for x in buf)))
            buf = []
    if buf:
        lines.append(Cue(buf[0].start, buf[-1].end, " ".join(x.text for x in buf)))
    return lines


def even_cues(text: str, duration: float, max_words: int) -> list[Cue]:
    """Chia đều văn bản theo thời gian, dùng khi không có mốc thời gian từ TTS."""
    words = text.split()
    if not words or duration <= 0:
        return []
    step = duration / len(words)
    timed = [Cue(i * step, (i + 1) * step, w) for i, w in enumerate(words)]
    return group_words(timed, max_words)


def _ass_color(hex_color: str) -> str:
    h = hex_color.lstrip("#")
    if len(h) != 6:
        h = "FFFFFF"
    r, g, b = h[0:2], h[2:4], h[4:6]
    return f"&H00{b}{g}{r}".upper()


def _ts(seconds: float) -> str:
    seconds = max(0.0, seconds)
    cs = int(round(seconds * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}").replace("\n", "\\N")


def build_ass(width: int, height: int, duration: float, title: TitleSettings,
              subtitle: SubtitleSettings, cues: list[Cue]) -> str:
    def style(name, s, align):
        return (f"Style: {name},{s.font},{s.font_size},{_ass_color(s.color)},&H000000FF,"
                f"{_ass_color(s.outline_color)},&H64000000,-1,0,0,0,100,100,0,0,1,{s.outline},1,"
                f"{align},60,60,{s.margin_v},1")

    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {width}",
        f"PlayResY: {height}",
        "WrapStyle: 0",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding",
        style("Title", title, 8),  # 8 = giữa phía trên
        style("Sub", subtitle, 2),  # 2 = giữa phía dưới
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    if title.enabled and title.text.strip():
        lines.append(f"Dialogue: 1,{_ts(0)},{_ts(duration)},Title,,0,0,0,,{_escape(title.text.strip())}")
    if subtitle.enabled:
        for c in cues:
            if c.text.strip() and c.start < duration:
                lines.append(f"Dialogue: 0,{_ts(c.start)},{_ts(min(c.end, duration))},Sub,,0,0,0,,{_escape(c.text)}")
    return "\n".join(lines) + "\n"
