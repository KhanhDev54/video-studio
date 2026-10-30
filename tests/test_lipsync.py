import os
import subprocess
from pathlib import Path

import pytest

from video_studio import lipsync, scenes, voice
from video_studio.captions import Cue
from video_studio.media import probe, require_ffmpeg
from video_studio.settings import RenderSettings


def _png(path: Path, color: str, box: tuple[int, int, int, int], size: str = "200x300") -> Path:
    x0, x1, y0, y1 = box
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
                    f"color=c={color}:s={size},format=rgba,geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':"
                    f"a='if(between(X,{x0},{x1})*between(Y,{y0},{y1}),255,0)'",
                    "-frames:v", "1", str(path)], check=True)
    return path


@pytest.fixture(scope="module")
def character(tmp_path_factory):
    d = tmp_path_factory.mktemp("Nhân vật mèo")
    _png(d / "body.png", "orange", (50, 150, 50, 250))
    _png(d / "mouth_X.png", "black", (90, 110, 160, 162))
    _png(d / "mouth_D.png", "red", (80, 120, 150, 175))
    _png(d / "blink.png", "black", (70, 130, 90, 95))
    return d


@pytest.fixture(scope="module")
def speechlike(tmp_path_factory):
    """Âm thanh có đoạn to, nhỏ, im lặng xen kẽ để giả lập lời nói."""
    p = tmp_path_factory.mktemp("voice") / "giọng.mp3"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
                    "aevalsrc='sin(220*2*PI*t)*between(mod(t,0.6),0,0.35)*(0.3+0.7*between(t,1,2))':d=3",
                    "-c:a", "libmp3lame", str(p)], check=True)
    return p


def test_character_load_and_fallback(character, tmp_path):
    ch = lipsync.Character.load(character)
    assert set(ch.mouths) == {"X", "D"} and ch.blink is not None
    assert ch.mouth_for("C") == "D" and ch.mouth_for("A") == "X" and ch.mouth_for("G") == "X"
    with pytest.raises(ValueError, match="body.png"):
        lipsync.Character.load(tmp_path)


def test_loudness_cues_follow_audio(speechlike):
    ffmpeg, _ = require_ffmpeg()
    cues = lipsync.cues_from_loudness(speechlike, ffmpeg, 25)
    assert cues[0].start == 0 and cues[-1].end == pytest.approx(3, abs=0.1)
    shape_at = lambda t: next(c.shape for c in cues if c.start <= t < c.end)  # noqa: E731
    assert shape_at(0.5) == "X"  # khoảng lặng
    assert shape_at(1.2) == "D"  # đoạn to nhất
    assert all(round((c.end - c.start) * 25) >= lipsync.MIN_HOLD for c in cues[1:-1])


def test_build_frames_sequence(character, tmp_path):
    ffmpeg, _ = require_ffmpeg()
    ch = lipsync.Character.load(character)
    cues = [lipsync.MouthCue(0, 1, "X"), lipsync.MouthCue(1, 2, "D"), lipsync.MouthCue(2, 6, "X")]
    pattern = lipsync.build_frames(ch, cues, 6.0, 25, ffmpeg, tmp_path, seed=1)
    frames = sorted(pattern.parent.glob("f_*.png"))
    assert len(frames) == 150
    same = lambda a, b: a.read_bytes() == b.read_bytes()  # noqa: E731
    assert same(frames[37], tmp_path / "char_D.png") and same(frames[5], frames[60])
    assert not same(frames[5], frames[37])
    blinks = lipsync.blink_times(6.0, 1)
    assert blinks and same(frames[int(blinks[0][0] * 25) + 1], tmp_path / "char_D_blink.png")  # chớp mắt lúc đang nói (1.2 s)
    out = tmp_path / "char.mov"
    subprocess.run([ffmpeg, "-y", "-v", "error", "-framerate", "25", "-start_number", "0", "-i", str(pattern),
                    "-c:v", "png", str(out)], check=True)
    assert probe(out).duration == pytest.approx(6.0, abs=0.15)


def _scene_settings(image_dir: Path, character: Path) -> RenderSettings:
    s = RenderSettings()
    s.output.width, s.output.height, s.output.preset, s.output.fps = 320, 180, "ultrafast", 25
    s.subtitle.font_size, s.subtitle.margin_v, s.title.enabled = 14, 10, False
    s.scene.script, s.scene.image_dir = "Xin chào các bạn.\n\nHôm nay mèo đi câu cá.", str(image_dir)
    s.scene.character_dir, s.scene.fade = str(character), 0
    return s


@pytest.fixture(scope="module")
def bg_dir(tmp_path_factory):
    d = tmp_path_factory.mktemp("bối cảnh")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=0x2060a0:s=640x360",
                    "-frames:v", "1", str(d / "nen.png")], check=True)
    return d


def _frame_rgb(video: Path, t: float, x: int, y: int) -> tuple[int, int, int]:
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(t), "-i", str(video), "-frames:v", "1",
                          "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, check=True).stdout
    i = (y * 320 + x) * 3
    return raw[i], raw[i + 1], raw[i + 2]


def test_scene_with_talking_character(character, bg_dir, speechlike, tmp_path, monkeypatch):
    def fake_tts(text, _voice, _rate, out_path, retries=2):
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(speechlike), "-c", "copy", str(out_path)],
                       check=True)
        return [Cue(0.1 * i, 0.1 * i + 0.1, w) for i, w in enumerate(text.split())]

    monkeypatch.setattr(voice, "synthesize", fake_tts)
    s = _scene_settings(bg_dir, character)
    s.voice.enabled, s.scene.lipsync = True, "loudness"
    out = scenes.render_scenes(s, tmp_path / "nói.mp4")
    assert probe(out).duration == pytest.approx(6.8, abs=0.3)
    # Nhân vật cao 55% khung (98 px), đứng góc phải dưới: thân màu cam, nền xanh vẫn ở góc trái.
    r, g, b = _frame_rgb(out, 0.5, 290, 150)
    assert r > 180 and b < 100
    r, g, b = _frame_rgb(out, 0.5, 20, 20)
    assert b > r


def test_scene_character_without_voice_stays_idle(character, bg_dir, tmp_path):
    s = _scene_settings(bg_dir, character)
    s.scene.seconds_per_scene = 1.0
    out = scenes.render_scenes(s, tmp_path / "im.mp4")
    assert probe(out).duration == pytest.approx(2.0, abs=0.3)


@pytest.mark.skipif(not lipsync.find_rhubarb(), reason="chưa cài Rhubarb (đặt VSTUDIO_RHUBARB)")
def test_rhubarb_cues(speechlike, tmp_path):
    ffmpeg, _ = require_ffmpeg()
    cues = lipsync.mouth_cues(speechlike, ffmpeg, 25, tmp_path, "rhubarb")
    assert cues and all(c.shape in lipsync.SHAPES for c in cues)
    assert cues[-1].end == pytest.approx(3, abs=0.1)


@pytest.mark.skipif(not (os.environ.get("VSTUDIO_TEST_TTS") and lipsync.find_rhubarb()),
                    reason="cần mạng + Rhubarb")
def test_rhubarb_on_real_vietnamese_tts(tmp_path):
    ffmpeg, _ = require_ffmpeg()
    audio = tmp_path / "vi.mp3"
    voice.synthesize("Xin chào các bạn, hôm nay chúng ta cùng đi câu cá nhé.", "vi-VN-HoaiMyNeural", "+0%", audio)
    cues = lipsync.mouth_cues(audio, ffmpeg, 25, tmp_path, "rhubarb")
    assert len({c.shape for c in cues}) >= 3  # có nhiều khẩu hình khác nhau, không chỉ đóng/mở


def test_example_character_is_valid():
    ch = lipsync.Character.load(Path(__file__).parent.parent / "examples" / "nhan_vat_mau")
    assert set(ch.mouths) == {"X", "B", "C", "D"} and ch.blink is not None
