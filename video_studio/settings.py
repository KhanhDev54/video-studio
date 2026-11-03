"""Cài đặt dựng video. Mọi thứ ở đây serialize được sang JSON để lưu preset."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any


@dataclass
class CutSettings:
    min_seg: float = 3.0
    max_seg: float = 6.0
    target_duration: float = 30.0  # bị ghi đè bởi độ dài voice nếu có voice
    shuffle_clips: bool = True
    shuffle_segments: bool = True


@dataclass
class OutputSettings:
    width: int = 1080
    height: int = 1920
    fps: int = 30
    fit: str = "crop"  # "crop" (lấp đầy khung) hoặc "pad" (giữ nguyên, thêm viền đen)
    crf: int = 20
    preset: str = "veryfast"


@dataclass
class TitleSettings:
    enabled: bool = True
    text: str = ""
    font: str = "Arial"
    font_size: int = 72
    color: str = "#FFFFFF"
    outline_color: str = "#000000"
    outline: int = 4
    margin_v: int = 220  # khoảng cách từ mép trên, px


@dataclass
class SubtitleSettings:
    enabled: bool = True
    font: str = "Arial"
    font_size: int = 64
    color: str = "#FFFF00"
    outline_color: str = "#000000"
    outline: int = 4
    margin_v: int = 300  # khoảng cách từ mép dưới, px
    max_words: int = 6  # số chữ tối đa mỗi dòng phụ đề
    export_srt: bool = True  # ghi thêm file .srt cạnh video (tải lên YouTube làm phụ đề)


@dataclass
class VoiceSettings:
    enabled: bool = False
    source: str = "tts"  # "tts" (Edge TTS) hoặc "file" (file thu âm của bạn)
    file_path: str = ""  # dùng khi source == "file"
    text: str = ""  # lời thoại; với "file" chỉ dùng để làm phụ đề (chia đều theo thời gian)
    voice: str = "vi-VN-HoaiMyNeural"
    rate: str = "+0%"
    pitch: str = "+0Hz"
    volume: float = 1.0


@dataclass
class AudioSettings:
    keep_original: bool = True
    original_volume: float = 0.3
    music_path: str = ""
    music_volume: float = 0.15
    duck_music: bool = True  # tự hạ nhạc nền khi có lời đọc


@dataclass
class SceneSettings:
    """Chế độ hoạt hình theo cảnh: mỗi đoạn kịch bản là một cảnh với một ảnh."""
    script: str = ""
    image_dir: str = ""  # thư mục ảnh; đoạn không ghi [ảnh] sẽ lấy ảnh tiếp theo trong thư mục
    seconds_per_scene: float = 4.0  # độ dài mỗi cảnh khi không bật voice
    pause: float = 0.4  # nghỉ sau lời đọc của mỗi cảnh, giây
    motion: bool = True  # zoom/lia ảnh (hiệu ứng Ken Burns)
    zoom: float = 0.15  # mức zoom/lia, 0.15 = 15%
    fade: float = 0.3  # mờ dần đầu/cuối mỗi cảnh, giây
    character_dir: str = ""  # thư mục nhân vật nói khớp miệng (xem lipsync.py); trống = không dùng
    character_side: str = "right"  # "left", "center" hoặc "right"
    character_height: float = 0.55  # chiều cao nhân vật so với khung hình
    character_motion: bool = True  # nhân vật thở nhẹ và nhún khi nói
    lipsync: str = "auto"  # "auto" (Rhubarb nếu có), "rhubarb" hoặc "loudness"
    thumbnail: bool = True  # tạo ảnh bìa YouTube <tên>_thumbnail.jpg từ cảnh đầu
    thumbnail_text: str = ""  # chữ trên ảnh bìa; trống = dùng tiêu đề
    also_shorts: bool = False  # xuất thêm bản 9:16 cho YouTube Shorts khi khung chính không phải 9:16


@dataclass
class RenderSettings:
    cut: CutSettings = field(default_factory=CutSettings)
    output: OutputSettings = field(default_factory=OutputSettings)
    title: TitleSettings = field(default_factory=TitleSettings)
    subtitle: SubtitleSettings = field(default_factory=SubtitleSettings)
    voice: VoiceSettings = field(default_factory=VoiceSettings)
    audio: AudioSettings = field(default_factory=AudioSettings)
    scene: SceneSettings = field(default_factory=SceneSettings)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RenderSettings":
        return _build(cls, data)


def _build(cls, data: dict[str, Any]):
    """Dựng dataclass lồng nhau, bỏ qua khoá lạ để preset cũ vẫn mở được."""
    kwargs = {}
    for f in fields(cls):
        if f.name not in data:
            continue
        value = data[f.name]
        default = f.default_factory() if callable(f.default_factory) else None  # type: ignore[misc]
        if is_dataclass(default) and isinstance(value, dict):
            value = _build(type(default), value)
        kwargs[f.name] = value
    return cls(**kwargs)


_WINDOWS_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
                     *(f"LPT{i}" for i in range(1, 10))}


class PresetStore:
    """Lưu preset dạng file JSON trong một thư mục."""

    def __init__(self, folder: Path):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)

    def _path(self, name: str) -> Path:
        safe = "".join(c for c in name if c.isalnum() or c in " -_").strip()
        if not safe:
            raise ValueError("Tên preset không hợp lệ")
        if safe.upper() in _WINDOWS_RESERVED:
            safe += "_"  # Windows không cho tạo file tên CON, NUL, COM1...
        return self.folder / f"{safe}.json"

    def names(self) -> list[str]:
        return sorted(p.stem for p in self.folder.glob("*.json"))

    def save(self, name: str, settings: RenderSettings) -> Path:
        path = self._path(name)
        path.write_text(json.dumps(settings.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def load(self, name: str) -> RenderSettings:
        data = json.loads(self._path(name).read_text(encoding="utf-8"))
        return RenderSettings.from_dict(data)

    def delete(self, name: str) -> None:
        self._path(name).unlink(missing_ok=True)
