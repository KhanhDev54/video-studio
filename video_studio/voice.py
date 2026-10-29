"""Tạo giọng đọc bằng Edge TTS (miễn phí, cần mạng) kèm mốc thời gian từng từ."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from .captions import Cue

VIETNAMESE_VOICES = {
    "vi-VN-HoaiMyNeural": "Hoài My (nữ)",
    "vi-VN-NamMinhNeural": "Nam Minh (nam)",
}


async def _synthesize(text: str, voice: str, rate: str, out_path: Path) -> list[Cue]:
    import edge_tts  # import muộn để app vẫn chạy khi chưa cài

    communicate = edge_tts.Communicate(text, voice, rate=rate, boundary="WordBoundary",
                                       proxy=os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy"))
    words: list[Cue] = []
    with open(out_path, "wb") as f:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                start = chunk["offset"] / 10_000_000
                words.append(Cue(start, start + chunk["duration"] / 10_000_000, chunk["text"]))
    return words


def synthesize(text: str, voice: str, rate: str, out_path: str | Path) -> list[Cue]:
    """Ghi MP3 ra out_path và trả về mốc thời gian từng từ."""
    if not text.strip():
        raise ValueError("Chưa nhập lời thoại cho voice")
    return asyncio.run(_synthesize(text, voice, rate, Path(out_path)))
