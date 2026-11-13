"""Chọn các đoạn cắt từ clip nguồn sao cho tổng độ dài đạt mục tiêu."""

from __future__ import annotations

import random
from dataclasses import dataclass
from pathlib import Path

from .settings import CutSettings


@dataclass(frozen=True)
class Segment:
    path: Path
    start: float
    duration: float


def plan_segments(clips: list[tuple[Path, float]], cut: CutSettings, target: float,
                  seed: int | None = None) -> list[Segment]:
    """Lần lượt lấy đoạn dài ngẫu nhiên [min_seg, max_seg] từ từng clip, quay vòng
    qua các clip cho tới khi đủ `target` giây. Đoạn cuối được cắt ngắn cho vừa.

    `clips` là danh sách (đường dẫn, độ dài giây). Clip ngắn hơn min_seg vẫn được
    dùng nguyên clip để không bỏ phí footage."""
    if target <= 0:
        raise ValueError("Độ dài mục tiêu phải > 0")
    usable = [(Path(p), d) for p, d in clips if d > 0.2]
    if not usable:
        raise ValueError("Không có clip nào dùng được")
    lo, hi = sorted((max(0.5, cut.min_seg), max(0.5, cut.max_seg)))
    rng = random.Random(seed)

    order = list(usable)
    if cut.shuffle_clips:
        rng.shuffle(order)

    # Mỗi clip giữ một con trỏ để các lần lấy sau không lặp lại đoạn cũ khi còn footage.
    cursor = {p: 0.0 for p, _ in order}
    segments: list[Segment] = []
    total = 0.0
    i = 0
    while total < target - 0.05:
        path, length = order[i % len(order)]
        i += 1
        want = min(rng.uniform(lo, hi), target - total)
        dur = min(want, length)
        start = cursor[path]
        if start + dur > length:
            # Đã dùng hết footage mới của clip này: lấy lại một đoạn bất kỳ.
            start = rng.uniform(0, length - dur) if cut.shuffle_segments else 0.0
        segments.append(Segment(path, round(start, 3), round(dur, 3)))
        cursor[path] = start + dur
        total += dur
        if i > 10_000:
            raise RuntimeError("Không lập được kế hoạch cắt")

    if cut.shuffle_segments:
        rng.shuffle(segments)
    return segments
