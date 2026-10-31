"""Tạo giọng đọc bằng Edge TTS (miễn phí, cần mạng) kèm mốc thời gian từng từ."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
import time
from pathlib import Path

from .captions import Cue

VIETNAMESE_VOICES = {
    "vi-VN-HoaiMyNeural": "Hoài My (nữ)",
    "vi-VN-NamMinhNeural": "Nam Minh (nam)",
}


CACHE_LIMIT = 300 * 1024 * 1024  # dung lượng tối đa của bộ đệm giọng đọc


class VoiceError(RuntimeError):
    """Lỗi tạo giọng đọc, kèm thông điệp dễ hiểu cho người dùng."""


def cache_dir() -> Path:
    return Path(os.environ.get("VSTUDIO_CACHE_DIR") or Path.home() / ".video_studio" / "tts_cache")


def _cache_key(text: str, voice: str, rate: str, pitch: str) -> str:
    return hashlib.sha256(json.dumps([text.strip(), voice, rate, pitch], ensure_ascii=False).encode()).hexdigest()


def _cache_get(key: str, out_path: Path) -> list[Cue] | None:
    mp3, meta = cache_dir() / f"{key}.mp3", cache_dir() / f"{key}.json"
    if not (mp3.is_file() and meta.is_file()):
        return None
    try:
        words = [Cue(*w) for w in json.loads(meta.read_text(encoding="utf-8"))]
    except (ValueError, TypeError):
        return None
    shutil.copyfile(mp3, out_path)
    os.utime(mp3)  # đánh dấu mới dùng để không bị dọn
    return words


def _cache_put(key: str, audio: Path, words: list[Cue]) -> None:
    try:
        d = cache_dir()
        d.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(audio, d / f"{key}.mp3")
        (d / f"{key}.json").write_text(json.dumps([[w.start, w.end, w.text] for w in words], ensure_ascii=False),
                                       encoding="utf-8")
        files = sorted(d.glob("*.mp3"), key=lambda p: p.stat().st_mtime)
        total = sum(p.stat().st_size for p in files)
        while files and total > CACHE_LIMIT:  # dọn file cũ nhất
            old = files.pop(0)
            total -= old.stat().st_size
            old.unlink(missing_ok=True)
            old.with_suffix(".json").unlink(missing_ok=True)
    except OSError:
        pass  # bộ đệm hỏng không được làm hỏng việc dựng video


async def _synthesize(text: str, voice: str, rate: str, out_path: Path, pitch: str = "+0Hz") -> list[Cue]:
    import edge_tts  # import muộn để app vẫn chạy khi chưa cài

    communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch, boundary="WordBoundary",
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


def synthesize(text: str, voice: str, rate: str, out_path: str | Path, retries: int = 2,
               pitch: str = "+0Hz") -> list[Cue]:
    """Ghi MP3 ra out_path và trả về mốc thời gian từng từ. Thử lại khi lỗi mạng."""
    if not text.strip():
        raise ValueError("Chưa nhập lời thoại cho voice")
    key = _cache_key(text, voice, rate, pitch)
    cached = _cache_get(key, Path(out_path))
    if cached is not None:
        return cached
    try:
        import edge_tts  # noqa: F401
    except ImportError as e:
        raise VoiceError("Chưa cài thư viện edge-tts (pip install edge-tts).") from e
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            words = asyncio.run(_synthesize(text, voice, rate, Path(out_path), pitch))
            if Path(out_path).stat().st_size == 0:
                raise VoiceError("Edge TTS không trả về âm thanh")
            _cache_put(key, Path(out_path), words)
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
