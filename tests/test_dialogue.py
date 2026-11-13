"""Hội thoại nhiều nhân vật, phụ đề .srt và tự hạ nhạc nền."""

import json
import subprocess
from pathlib import Path

import pytest

from video_studio import captions, scenes, voice
from video_studio.captions import Cue
from video_studio.lipsync import load_cast
from video_studio.media import probe
from video_studio.pipeline import render_one, VoiceTrack
from video_studio.settings import RenderSettings

EXAMPLE = Path(__file__).parent.parent / "examples" / "nhan_vat_mau"


def _ffmpeg(*args):
    subprocess.run(["ffmpeg", "-y", "-v", "error", *args], check=True)


@pytest.fixture(scope="module")
def cast_dir(tmp_path_factory):
    """Hai nhân vật dùng lại bộ hình mẫu; Chó có giọng nam, cao giọng, vẽ quay sang phải."""
    d = tmp_path_factory.mktemp("dàn nhân vật")
    for name, cfg in (("Mèo", {}), ("Chó", {"voice": "vi-VN-NamMinhNeural", "pitch": "+15Hz",
                                            "volume": 0.8, "faces": "right"})):
        sub = d / name
        sub.mkdir()
        for f in EXAMPLE.glob("*.png"):
            (sub / f.name).write_bytes(f.read_bytes())
        if cfg:
            (sub / "nhanvat.json").write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    (d / "ghi chú").mkdir()  # thư mục không có body.png bị bỏ qua
    return d


def test_load_cast(cast_dir):
    cast = load_cast(cast_dir)
    assert sorted(cast) == ["chó", "mèo"]
    assert cast["chó"].voice == "vi-VN-NamMinhNeural" and cast["chó"].volume == 0.8
    assert cast["mèo"].voice is None and cast["chó"].faces == "right"


def test_parse_dialogue(tmp_path):
    img = tmp_path / "a.png"
    img.write_bytes(b"")
    script = ("[a.png]\nNgày xưa có hai bạn.\nMèo: Đi câu cá nhé!\nCHÓ: Được thôi,\nnhưng mang bánh mì.\n"
              "Kể: Thế là hai bạn lên đường.\nGiờ: 8 giờ sáng")
    (scene,) = scenes.parse_script(script, tmp_path, {"mèo", "chó"})
    assert [(l.speaker, l.text) for l in scene.lines] == [
        (None, "Ngày xưa có hai bạn."), ("mèo", "Đi câu cá nhé!"), ("chó", "Được thôi, nhưng mang bánh mì."),
        (None, "Thế là hai bạn lên đường. Giờ: 8 giờ sáng"),  # "Giờ" không phải nhân vật
    ]
    assert scene.speakers == ["mèo", "chó"]


def test_positions_and_flip():
    assert scenes._positions(1, "left", 1000) == ["40"]
    xs = scenes._positions(3, "right", 1000)
    assert xs[0].startswith("40+0*") and xs[2].startswith("40+2*")
    # Hình vẽ nhìn sang phải: đứng bên trái giữ nguyên, đứng bên phải thì lật lại.
    assert not scenes._needs_flip("right", 0, 2, "right") and scenes._needs_flip("right", 1, 2, "right")
    assert not scenes._needs_flip(None, 1, 2, "right") and not scenes._needs_flip("left", 1, 3, "right")


def test_build_srt():
    srt = captions.build_srt([Cue(0, 1.5, "Xin chào"), Cue(61.25, 62, "Tạm biệt"), Cue(3, 4, " ")])
    assert srt == "1\n00:00:00,000 --> 00:00:01,500\nXin chào\n\n2\n00:01:01,250 --> 00:01:02,000\nTạm biệt\n"


@pytest.fixture(scope="module")
def bg(tmp_path_factory):
    d = tmp_path_factory.mktemp("nền")
    _ffmpeg("-f", "lavfi", "-i", "color=c=0x2060a0:s=640x360", "-frames:v", "1", str(d / "nen.png"))
    return d


def _frame_rgb(video: Path, t: float, x: int, y: int, width: int = 320) -> tuple[int, int, int]:
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(t), "-i", str(video), "-frames:v", "1",
                          "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, check=True).stdout
    i = (y * width + x) * 3
    return raw[i], raw[i + 1], raw[i + 2]


def test_dialogue_scene_voices_and_actors(cast_dir, bg, tmp_path, monkeypatch):
    calls = []

    def fake_tts(text, name, rate, out_path, retries=2, pitch="+0Hz"):
        calls.append((text, name, pitch))
        _ffmpeg("-f", "lavfi", "-i", "sine=f=300:d=1", "-c:a", "libmp3lame", str(out_path))
        return [Cue(0.2 * i, 0.2 * i + 0.2, w) for i, w in enumerate(text.split())]

    monkeypatch.setattr(voice, "synthesize", fake_tts)
    s = RenderSettings()
    s.output.width, s.output.height, s.output.preset, s.output.fps = 320, 180, "ultrafast", 25
    s.title.enabled, s.subtitle.font_size = False, 14
    s.scene.script = "Mèo: Đi câu cá nhé!\nChó: Được thôi.\n\nKể: Hai bạn lên đường."
    s.scene.image_dir, s.scene.character_dir, s.scene.fade = str(bg), str(cast_dir), 0
    s.scene.lipsync, s.scene.pause = "loudness", 0.5
    s.voice.enabled = True
    out = scenes.render_scenes(s, tmp_path / "hội thoại.mp4")
    assert calls == [("Đi câu cá nhé!", "vi-VN-HoaiMyNeural", "+0Hz"),
                     ("Được thôi.", "vi-VN-NamMinhNeural", "+15Hz"),
                     ("Hai bạn lên đường.", "vi-VN-HoaiMyNeural", "+0Hz")]
    # Cảnh 1: 1 s + nghỉ 0.25 + 1 s + 0.5; cảnh 2: 1 s + 0.5.
    assert probe(out).duration == pytest.approx(4.25, abs=0.3)
    # Cảnh 1 có 2 nhân vật (trái và phải), cảnh 2 chỉ có người dẫn chuyện: không nhân vật nào.
    left_x, y = 12 + 25, 140  # nhân vật cao 99 px, thân cam ở giữa hình
    assert _frame_rgb(out, 1.0, left_x, y)[0] > 180
    assert _frame_rgb(out, 3.5, left_x, y)[2] > 120
    srt = (tmp_path / "hội thoại.srt").read_text(encoding="utf-8")
    assert "Đi câu cá nhé!" in srt and "Hai bạn lên đường." in srt


def _mean_volume(path: Path, start: float, dur: float) -> float:
    err = subprocess.run(["ffmpeg", "-v", "info", "-ss", str(start), "-t", str(dur), "-i", str(path),
                          "-af", "volumedetect", "-f", "null", "-"], capture_output=True, text=True).stderr
    return float(err.split("mean_volume:")[1].split("dB")[0])


@pytest.mark.parametrize("duck", [True, False])
def test_music_ducking(tmp_path, duck):
    clip = tmp_path / "clip.mp4"
    _ffmpeg("-f", "lavfi", "-i", "color=c=gray:s=160x90:d=4", "-c:v", "libx264", "-preset", "ultrafast",
            "-pix_fmt", "yuv420p", str(clip))
    music, speech = tmp_path / "nhạc.m4a", tmp_path / "giọng.m4a"
    _ffmpeg("-f", "lavfi", "-i", "sine=f=1000:d=4", "-c:a", "aac", str(music))
    # Lời đọc chỉ có trong 1.5 s đầu, sau đó im lặng.
    _ffmpeg("-f", "lavfi", "-i", "aevalsrc='sin(200*2*PI*t)*lt(t,1.5)':d=3.5", "-c:a", "aac", str(speech))
    s = RenderSettings()
    s.output.width, s.output.height, s.output.preset = 160, 90, "ultrafast"
    s.title.enabled, s.audio.keep_original = False, False
    s.audio.music_path, s.audio.music_volume, s.audio.duck_music = str(music), 0.5, duck
    s.voice.volume = 0.0  # chỉ nghe nhạc để đo, lời đọc vẫn dùng làm tín hiệu hạ nhạc
    out = render_one([clip], s, tmp_path / "out.mp4", seed=1,
                     voice_track=VoiceTrack(speech, 3.5, [Cue(0, 1.5, "xin chào")]))
    during, after = _mean_volume(out, 0.3, 1.0), _mean_volume(out, 2.6, 1.0)
    if duck:
        assert during < after - 6  # nhạc nhỏ hẳn khi có lời
    else:
        assert during == pytest.approx(after, abs=1.5)
    assert (tmp_path / "out.srt").is_file()
