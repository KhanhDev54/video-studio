"""Nhân vật 2D nói khớp miệng theo giọng đọc.

Thư mục nhân vật gồm các PNG nền trong suốt, cùng kích thước khung, xếp chồng tại góc trên trái:
    body.png                 thân + mặt, không có miệng (bắt buộc)
    mouth_X.png, mouth_A.png ... mouth_H.png   các khẩu hình (ít nhất 2 hình)
    blink.png                mắt nhắm, phủ lên khi chớp mắt (không bắt buộc)

Tên khẩu hình theo chuẩn của Rhubarb Lip Sync (MIT): X nghỉ, A mím (m/b/p), B hé răng,
C mở vừa, D mở to, E tròn, F chu môi, G răng chạm môi (f/v), H lưỡi (l). Thiếu hình nào thì
dùng hình gần nhất theo bảng FALLBACK.

Khẩu hình lấy từ Rhubarb (nếu có, bộ nhận dạng phonetic dùng được cho tiếng Việt) hoặc
từ độ to của giọng đọc (không cần cài thêm gì)."""

from __future__ import annotations

import array
import json
import os
import random
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from .media import NO_WINDOW

SHAPES = "XABCDEFGH"
FALLBACK = {
    "X": "XAB", "A": "AXB", "B": "BCA", "C": "CBD", "D": "DCB",
    "E": "ECB", "F": "FBC", "G": "GFB", "H": "HCB",
}
MIN_HOLD = 2  # số khung tối thiểu giữ một khẩu hình, tránh miệng nháy liên tục


@dataclass(frozen=True)
class MouthCue:
    start: float
    end: float
    shape: str


@dataclass(frozen=True)
class Character:
    body: Path
    mouths: dict[str, Path]
    blink: Path | None

    @classmethod
    def load(cls, folder: str | Path) -> "Character":
        folder = Path(folder)
        body = folder / "body.png"
        if not body.is_file():
            raise ValueError(f"Thư mục nhân vật {folder} thiếu body.png")
        mouths = {s: folder / f"mouth_{s}.png" for s in SHAPES if (folder / f"mouth_{s}.png").is_file()}
        if len(mouths) < 2:
            raise ValueError(f"Nhân vật {folder.name} cần ít nhất 2 hình miệng (vd. mouth_X.png và mouth_D.png)")
        blink = folder / "blink.png"
        return cls(body, mouths, blink if blink.is_file() else None)

    def mouth_for(self, shape: str) -> str:
        for s in FALLBACK.get(shape, shape):
            if s in self.mouths:
                return s
        return "X" if "X" in self.mouths else sorted(self.mouths)[0]


# ---------- khẩu hình từ âm thanh ----------

def find_rhubarb() -> str | None:
    """Tìm rhubarb: biến VSTUDIO_RHUBARB (file hoặc thư mục), thư mục rhubarb cạnh app, rồi PATH."""
    exe = "rhubarb.exe" if sys.platform == "win32" else "rhubarb"
    env = os.environ.get("VSTUDIO_RHUBARB", "").strip()
    candidates = []
    if env:
        p = Path(env)
        candidates += [p] if p.is_file() else [p / exe, *p.glob(f"*/{exe}")]
    root = Path(__file__).resolve().parent.parent / "rhubarb"
    candidates += [root / exe, *root.glob(f"*/{exe}")]
    for c in candidates:
        if c.is_file():
            return str(c)
    return shutil.which("rhubarb")


def _run_text(cmd: list[str]) -> str:
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                          creationflags=NO_WINDOW)
    if proc.returncode != 0:
        raise RuntimeError(f"{Path(cmd[0]).name} lỗi: {proc.stderr.strip()[-400:]}")
    return proc.stdout


def cues_from_rhubarb(audio: Path, ffmpeg: str, rhubarb: str, workdir: Path) -> list[MouthCue]:
    wav = workdir / f"{audio.stem}_lipsync.wav"  # Rhubarb chỉ đọc WAV/OGG
    _run_text([ffmpeg, "-y", "-v", "error", "-i", str(audio), "-ac", "1", "-ar", "16000", str(wav)])
    out = _run_text([rhubarb, "-q", "-f", "json", "-r", "phonetic", str(wav)])
    data = json.loads(out)
    return [MouthCue(float(c["start"]), float(c["end"]), c["value"]) for c in data["mouthCues"]]


def cues_from_loudness(audio: Path, ffmpeg: str, fps: int) -> list[MouthCue]:
    """Ước lượng khẩu hình theo độ to từng khung: im lặng -> X, nhỏ -> B, vừa -> C, to -> D."""
    rate = 16000
    raw = subprocess.run([ffmpeg, "-v", "error", "-i", str(audio), "-ac", "1", "-ar", str(rate),
                          "-f", "s16le", "-"], capture_output=True, check=True, creationflags=NO_WINDOW).stdout
    samples = array.array("h")
    samples.frombytes(raw[: len(raw) // 2 * 2])
    if sys.byteorder == "big":
        samples.byteswap()
    step = rate / fps
    levels = []
    for i in range(int(len(samples) / step)):
        chunk = samples[int(i * step): int((i + 1) * step)]
        levels.append((sum(s * s for s in chunk) / max(1, len(chunk))) ** 0.5)
    peak = max(levels, default=0) or 1
    shapes = []
    for lv in levels:
        r = lv / peak
        shapes.append("X" if r < 0.08 else "B" if r < 0.25 else "C" if r < 0.5 else "D")
    return _frames_to_cues(_hold(shapes), fps)


def _hold(shapes: list[str]) -> list[str]:
    out = list(shapes)
    i = 0
    while i < len(out):
        j = i
        while j < len(out) and out[j] == out[i]:
            j += 1
        if j - i < MIN_HOLD and i > 0:
            out[i:j] = [out[i - 1]] * (j - i)  # đoạn quá ngắn: giữ khẩu hình trước đó
        i = j
    return out


def _frames_to_cues(shapes: list[str], fps: int) -> list[MouthCue]:
    cues: list[MouthCue] = []
    for n, s in enumerate(shapes):
        t = n / fps
        if cues and cues[-1].shape == s:
            cues[-1] = MouthCue(cues[-1].start, t + 1 / fps, s)
        else:
            cues.append(MouthCue(t, t + 1 / fps, s))
    return cues


def mouth_cues(audio: Path, ffmpeg: str, fps: int, workdir: Path, mode: str = "auto") -> list[MouthCue]:
    """mode: "auto" (Rhubarb nếu có, không thì theo độ to), "rhubarb" hoặc "loudness"."""
    rhubarb = find_rhubarb() if mode in ("auto", "rhubarb") else None
    if mode == "rhubarb" and rhubarb is None:
        raise ValueError("Chưa tìm thấy Rhubarb Lip Sync. Tải tại github.com/DanielSWolf/rhubarb-lip-sync, "
                         "giải nén vào thư mục rhubarb cạnh app hoặc đặt biến VSTUDIO_RHUBARB.")
    if rhubarb:
        return cues_from_rhubarb(audio, ffmpeg, rhubarb, workdir)
    return cues_from_loudness(audio, ffmpeg, fps)


# ---------- dựng khung hình nhân vật ----------

def blink_times(duration: float, seed: int) -> list[tuple[float, float]]:
    rng = random.Random(seed)
    t, out = rng.uniform(1.0, 2.5), []
    while t < duration - 0.2:
        out.append((t, t + 0.12))
        t += rng.uniform(2.5, 5.0)
    return out


def build_frames(char: Character, cues: list[MouthCue], duration: float, ffmpeg: str, workdir: Path,
                 seed: int = 0) -> Path:
    """Ghép sẵn body + miệng (+ mắt nhắm) thành PNG, ghi danh sách concat theo thời gian.
    Trả về file danh sách dùng với `-f concat -safe 0 -i`."""
    # Mốc thay đổi: đầu/cuối mỗi khẩu hình và mỗi lần chớp mắt.
    blinks = blink_times(duration, seed) if char.blink else []
    marks = sorted({0.0, duration, *(c.start for c in cues), *(c.end for c in cues),
                    *(b for bl in blinks for b in bl)})
    marks = [m for m in marks if 0 <= m <= duration]

    def state_at(t: float) -> tuple[str, bool]:
        shape = next((c.shape for c in cues if c.start <= t < c.end), "X")
        return char.mouth_for(shape), any(a <= t < b for a, b in blinks)

    entries: list[tuple[tuple[str, bool], float]] = []
    for a, b in zip(marks, marks[1:]):
        if b - a <= 1e-4:
            continue
        st = state_at((a + b) / 2)
        if entries and entries[-1][0] == st:
            entries[-1] = (st, entries[-1][1] + b - a)
        else:
            entries.append((st, b - a))
    if not entries:
        entries = [((char.mouth_for("X"), False), duration)]

    frames: dict[tuple[str, bool], Path] = {}
    for st, _ in entries:
        if st in frames:
            continue
        mouth, closed = st
        out = workdir / f"char_{mouth}{'_blink' if closed else ''}.png"
        layers = [char.body, char.mouths[mouth]] + ([char.blink] if closed and char.blink else [])
        inputs = [x for p in layers for x in ("-i", str(p))]
        graph = "[0][1]overlay=format=auto" + ("[t];[t][2]overlay=format=auto" if len(layers) == 3 else "")
        _run_text([ffmpeg, "-y", "-v", "error", *inputs, "-filter_complex", graph + ",format=rgba",
                   "-frames:v", "1", str(out)])
        frames[st] = out

    lines = ["ffconcat version 1.0"]
    for st, dur in entries:
        lines += [f"file '{frames[st].name}'", f"duration {dur:.4f}"]
    lines.append(f"file '{frames[entries[-1][0]].name}'")  # concat bỏ qua duration của file cuối
    listing = workdir / f"char_{seed}.txt"
    listing.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return listing
