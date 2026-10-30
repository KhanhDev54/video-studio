"""Tạo giọng đọc bằng Edge TTS (miễn phí, cần mạng) kèm mốc thời gian từng từ."""

from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path

from .captions import Cue

VIETNAMESE_VOICES = {
    "vi-VN-HoaiMyNeural": "Hoài My (nữ)",
    "vi-VN-NamMinhNeural": "Nam Minh (nam)",
}


class VoiceError(RuntimeError):
    """Lỗi tạo giọng đọc, kèm thông điệp dễ hiểu cho người dùng."""


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


def synthesize(text: str, voice: str, rate: str, out_path: str | Path, retries: int = 2) -> list[Cue]:
    """Ghi MP3 ra out_path và trả về mốc thời gian từng từ. Thử lại khi lỗi mạng."""
    if not text.strip():
        raise ValueError("Chưa nhập lời thoại cho voice")
    try:
        import edge_tts  # noqa: F401
    except ImportError as e:
        raise VoiceError("Chưa cài thư viện edge-tts (pip install edge-tts).") from e
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            words = asyncio.run(_synthesize(text, voice, rate, Path(out_path)))
            if Path(out_path).stat().st_size == 0:
                raise VoiceError("Edge TTS không trả về âm thanh")
            return words
        except Exception as e:  # lỗi mạng/dịch vụ: thử lại vài lần rồi báo rõ
            last = e
            if attempt < retries:
                time.sleep(1.5 * (attempt + 1))
    raise VoiceError(
        "Không tạo được giọng đọc Edge TTS (kiểm tra kết nối mạng, tường lửa/proxy; dịch vụ có thể "
        "tạm ngừng). Bạn có thể chọn \"File thu âm\" trong tab Voice để dùng giọng tự thu. "
        f"Chi tiết: {type(last).__name__}: {last}"
    ) from last
