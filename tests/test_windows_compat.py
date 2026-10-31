"""Các test cho những điểm hay hỏng trên Windows; chạy được trên mọi hệ điều hành."""

import subprocess
from pathlib import Path

import pytest

from video_studio import media, voice
from video_studio.captions import Cue
from video_studio.media import probe, require_ffmpeg
from video_studio.pipeline import render_one
from video_studio.settings import PresetStore, RenderSettings


def _ffmpeg(*args):
    subprocess.run(["ffmpeg", "-y", "-v", "error", *args], check=True)


def _small(title: str = "") -> RenderSettings:
    s = RenderSettings()
    s.output.width, s.output.height, s.output.preset = 360, 640, "ultrafast"
    s.cut.target_duration = 2
    s.title.text, s.title.font_size, s.title.margin_v = title, 48, 100
    s.subtitle.enabled = False
    return s


def _mean_brightness(video: Path, t: float = 1.0) -> float:
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(t), "-i", str(video), "-frames:v", "1",
                          "-f", "rawvideo", "-pix_fmt", "gray", "-"], capture_output=True, check=True).stdout
    return sum(raw) / len(raw)


@pytest.fixture(scope="module")
def black_clip(tmp_path_factory):
    # Tên thư mục và file có dấu + khoảng trắng như footage thật của người dùng Việt.
    p = tmp_path_factory.mktemp("Video gốc") / "Cây chà sàn ổn định.mp4"
    _ffmpeg("-f", "lavfi", "-i", "color=c=black:size=360x640:rate=25:duration=4",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(p))
    return p


def test_probe_vietnamese_filename(black_clip):
    info = probe(black_clip)
    assert info.path == black_clip and info.duration == pytest.approx(4, abs=0.1)
    assert (info.width, info.height) == (360, 640) and not info.has_audio


def test_probe_bad_file_gives_readable_error(tmp_path):
    bad = tmp_path / "hỏng.mp4"
    bad.write_bytes(b"not a video")
    with pytest.raises(RuntimeError, match="hỏng.mp4"):
        probe(bad)


def test_title_is_actually_drawn(black_clip, tmp_path):
    """Kiểm tra libass tìm được font hệ thống (điểm hay hỏng với bản FFmpeg Windows)."""
    plain = render_one([black_clip], _small(), tmp_path / "plain.mp4", seed=1)
    titled = render_one([black_clip], _small("CÂY CHÀ SÀN Ổn Định"), tmp_path / "titled.mp4", seed=1)
    assert _mean_brightness(plain) < 2
    assert _mean_brightness(titled) > _mean_brightness(plain) + 1


def test_voice_from_own_recording(black_clip, tmp_path):
    rec = tmp_path / "giọng tự thu.m4a"
    _ffmpeg("-f", "lavfi", "-i", "sine=frequency=500:duration=3", "-c:a", "aac", str(rec))
    s = _small("Tiêu đề")
    s.voice.enabled, s.voice.source, s.voice.file_path = True, "file", str(rec)
    s.voice.text = "Sạch bong không cần cúi người"
    s.subtitle.enabled = True
    out = render_one([black_clip], s, tmp_path / "rec.mp4", seed=1)
    info = probe(out)
    assert info.has_audio and info.duration == pytest.approx(3.5, abs=0.3)


def test_voice_file_missing(black_clip, tmp_path):
    s = _small()
    s.voice.enabled, s.voice.source, s.voice.file_path = True, "file", str(tmp_path / "khong_co.m4a")
    with pytest.raises(ValueError, match="file thu âm"):
        render_one([black_clip], s, tmp_path / "x.mp4")


def test_tts_failure_is_reported_clearly(monkeypatch, tmp_path):
    async def boom(*_a):
        raise ConnectionError("bị chặn")

    monkeypatch.setattr(voice, "_synthesize", boom)
    with pytest.raises(voice.VoiceError, match="File thu âm.*ConnectionError: bị chặn"):
        voice.synthesize("xin chào", "vi-VN-HoaiMyNeural", "+0%", tmp_path / "v.mp3", retries=0)


def test_preset_windows_reserved_name(tmp_path):
    store = PresetStore(tmp_path)
    path = store.save("con", RenderSettings())
    assert path.name == "con_.json"
    assert store.load("con") == RenderSettings()


def test_ffmpeg_dir_override(tmp_path, monkeypatch):
    ffmpeg, ffprobe = require_ffmpeg()
    d = tmp_path / "ffmpeg bin"
    d.mkdir()
    for exe in (ffmpeg, ffprobe):
        target = d / Path(exe).name
        try:
            target.symlink_to(exe)
        except OSError:  # Windows thường không cho tạo symlink nếu không bật Developer Mode
            import shutil

            shutil.copy(exe, target)
    monkeypatch.setenv("VSTUDIO_FFMPEG_DIR", str(d))
    assert Path(media.require_ffmpeg()[0]).parent == d


def test_tts_cache_reuses_audio(monkeypatch, tmp_path):
    calls = []

    async def fake(text, name, rate, out_path, pitch="+0Hz"):
        calls.append(text)
        out_path.write_bytes(b"ID3 giong doc")
        return [Cue(0, 0.5, "xin"), Cue(0.5, 1, "chào")]

    monkeypatch.setattr(voice, "_synthesize", fake)
    a, b, c = tmp_path / "a.mp3", tmp_path / "b.mp3", tmp_path / "c.mp3"
    w1 = voice.synthesize("xin chào", "vi-VN-HoaiMyNeural", "+0%", a)
    w2 = voice.synthesize(" xin chào ", "vi-VN-HoaiMyNeural", "+0%", b)  # khoảng trắng thừa: vẫn trúng
    voice.synthesize("xin chào", "vi-VN-HoaiMyNeural", "+0%", c, pitch="+10Hz")  # khác cao độ: gọi lại
    assert calls == ["xin chào", "xin chào"]
    assert w1 == w2 and b.read_bytes() == a.read_bytes()
