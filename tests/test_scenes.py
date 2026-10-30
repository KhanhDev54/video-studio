import subprocess
from pathlib import Path

import pytest

from video_studio import scenes, voice
from video_studio.captions import Cue
from video_studio.media import probe
from video_studio.settings import RenderSettings


def _image(path: Path, color: str) -> Path:
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"testsrc2=size=640x480,"
                    f"drawbox=c={color}:t=fill:w=200:h=200:x=220:y=140", "-frames:v", "1", str(path)], check=True)
    return path


@pytest.fixture(scope="module")
def image_dir(tmp_path_factory):
    d = tmp_path_factory.mktemp("Ảnh nhân vật")
    _image(d / "01 mèo ngủ.png", "red")
    _image(d / "02 mèo câu cá.jpg", "blue")
    _image(d / "03 100% vui.png", "green")
    return d


def _settings(image_dir, script: str) -> RenderSettings:
    s = RenderSettings()
    s.output.width, s.output.height, s.output.preset, s.output.fps = 320, 180, "ultrafast", 25
    s.title.text, s.title.font_size = "Chú mèo lười", 16
    s.subtitle.font_size, s.subtitle.margin_v = 14, 10
    s.scene.script, s.scene.image_dir, s.scene.seconds_per_scene = script, str(image_dir), 1.5
    return s


def test_parse_script_tags_and_folder_order(image_dir):
    script = "[03 100% vui.png]\nCảnh một\nnhiều dòng.\n\nCảnh hai.\r\n\r\nCảnh ba.\n\n\nCảnh bốn."
    got = scenes.parse_script(script, image_dir)
    assert [s.text for s in got] == ["Cảnh một nhiều dòng.", "Cảnh hai.", "Cảnh ba.", "Cảnh bốn."]
    # Ảnh đã gắn thẻ không bị dùng lại theo thứ tự thư mục; hết ảnh thì giữ ảnh cảnh trước.
    assert [s.image.name for s in got] == ["03 100% vui.png", "01 mèo ngủ.png", "02 mèo câu cá.jpg",
                                          "02 mèo câu cá.jpg"]


def test_parse_script_errors(image_dir, tmp_path):
    with pytest.raises(ValueError, match="trống"):
        scenes.parse_script("  \n\n ", image_dir)
    with pytest.raises(ValueError, match="không tìm thấy ảnh"):
        scenes.parse_script("[khong_co.png]\nxin chào", image_dir)
    with pytest.raises(ValueError, match="chưa có ảnh"):
        scenes.parse_script("xin chào", tmp_path)


def test_render_scenes_without_voice(image_dir, tmp_path):
    s = _settings(image_dir, "Ngày xửa ngày xưa.\n\nCó một chú mèo.\n\n[03 100% vui.png]\nHết.")
    s.audio.keep_original = False
    out = scenes.render_scenes(s, tmp_path / "hoạt hình.mp4")
    info = probe(out)
    assert (info.width, info.height) == (320, 180) and info.has_audio
    assert info.duration == pytest.approx(4.5, abs=0.3)


def test_render_scenes_with_tts_timing(image_dir, tmp_path, monkeypatch):
    """Giả lập Edge TTS: mỗi cảnh dài theo lời đọc + pause, phụ đề lệch đúng theo cảnh."""
    def fake_tts(text, _voice, _rate, out_path, retries=2):
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "sine=duration=1",
                        "-c:a", "libmp3lame", str(out_path)], check=True)
        return [Cue(0.1 * i, 0.1 * i + 0.1, w) for i, w in enumerate(text.split())]

    seen = {}
    real_build = scenes.captions.build_ass

    def spy(*args):
        seen["cues"] = args[-1]
        return real_build(*args)

    monkeypatch.setattr(voice, "synthesize", fake_tts)
    monkeypatch.setattr(scenes.captions, "build_ass", spy)
    s = _settings(image_dir, "Một hai.\n\nBa bốn.")
    s.voice.enabled, s.scene.pause = True, 0.5
    out = scenes.render_scenes(s, tmp_path / "tts.mp4")
    assert probe(out).duration == pytest.approx(3.0, abs=0.3)
    starts = [round(c.start, 2) for c in seen["cues"]]
    assert starts[0] == 0 and 1.4 < starts[-1] < 1.7  # cảnh 2 bắt đầu sau ~1.5 s


def test_motion_filters_are_valid(image_dir, tmp_path):
    for motion in (*scenes.MOTIONS, "none"):
        vf = scenes._motion_filter(motion, 160, 90, 10, 10, 0.2)
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(image_dir / "01 mèo ngủ.png"), "-vf", vf,
                        "-frames:v", "10", str(tmp_path / f"{motion}.mp4")], check=True)


@pytest.mark.skipif(not __import__("os").environ.get("VSTUDIO_TEST_TTS"), reason="cần mạng; đặt VSTUDIO_TEST_TTS=1")
def test_scenes_with_real_tts(image_dir, tmp_path):
    s = _settings(image_dir, "Ngày xửa ngày xưa.\n\nCó một chú mèo lười.")
    s.voice.enabled = True
    out = scenes.render_scenes(s, tmp_path / "real.mp4")
    assert probe(out).duration > 1.5
