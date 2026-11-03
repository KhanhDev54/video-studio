import json
import subprocess
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from video_studio import character_maker as cm  # noqa: E402
from video_studio import scenes  # noqa: E402
from video_studio.lipsync import SHAPES, Character, load_cast  # noqa: E402
from video_studio.media import probe  # noqa: E402
from video_studio.settings import RenderSettings  # noqa: E402


def test_make_character_writes_full_set(tmp_path):
    s = cm.CharacterSpec("Mèo Mun", "meo", "#424242", "#FFFFFF", eyes="long_lanh", accessory="kinh",
                         voice="vi-VN-NamMinhNeural", pitch="-10Hz")
    folder = cm.make_character(s, tmp_path)
    assert folder.name == "Mèo Mun"
    ch = Character.load(folder)
    assert sorted(ch.mouths) == sorted(SHAPES) and ch.blink is not None
    cfg = json.loads((folder / "nhanvat.json").read_text(encoding="utf-8"))
    assert (cfg["voice"], cfg["pitch"]) == ("vi-VN-NamMinhNeural", "-10Hz")
    assert cm.load_spec(folder) == s
    with pytest.raises(FileExistsError):
        cm.make_character(s, tmp_path)
    cm.make_character(s, tmp_path, overwrite=True)


@pytest.mark.parametrize("kind", list(cm.KINDS))
@pytest.mark.parametrize("eyes", list(cm.EYES))
def test_blink_closes_eyes(kind, eyes):
    s = cm.CharacterSpec(kind=kind, eyes=eyes, color="#3366CC")
    open_ = cm.preview(s)
    closed = cm.preview(s, blink=True)
    # Tâm đồng tử: mắt mở màu tối, mắt nhắm là màu mặt.
    assert open_.pixelColor(cm.EYE_L, cm.EYE_Y + 4).lightness() < 80
    assert closed.pixelColor(cm.EYE_L, cm.EYE_Y + 4).name() == "#3366cc"


def test_mouth_shapes_are_distinct():
    imgs = [cm.draw_mouth(m) for m in SHAPES]
    assert all(a != b for i, a in enumerate(imgs) for b in imgs[i + 1:])
    with pytest.raises(ValueError):
        cm.draw_mouth("Z")


def test_random_spec_is_valid_and_deterministic():
    assert cm.random_spec(7) == cm.random_spec(7)
    for seed in range(30):
        s = cm.random_spec(seed)
        assert s.kind in cm.KINDS and s.eyes in cm.EYES and s.accessory in cm.ACCESSORIES


def test_safe_folder_name():
    assert cm.safe_folder_name("Bé: Na?") == "Bé Na"
    assert cm.safe_folder_name("con") == "con_"
    with pytest.raises(ValueError):
        cm.safe_folder_name("???")


def _pixel(video: Path, t: float, x: int, y: int, width: int) -> tuple[int, int, int]:
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(t), "-i", str(video), "-frames:v", "1",
                          "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, check=True).stdout
    i = (y * width + x) * 3
    return raw[i], raw[i + 1], raw[i + 2]


def test_generated_cast_in_dialogue_video(tmp_path):
    cast = tmp_path / "dàn"
    cm.make_character(cm.CharacterSpec("Đỏ", "gau", "#D03030", "#D03030"), cast)
    cm.make_character(cm.CharacterSpec("Xanh", "tho", "#3040D0", "#3040D0"), cast)
    assert set(load_cast(cast)) == {"đỏ", "xanh"}
    bg = tmp_path / "nền"
    bg.mkdir()
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=white:s=640x360",
                    "-frames:v", "1", str(bg / "nen.png")], check=True)
    s = RenderSettings()
    s.output.width, s.output.height, s.output.preset, s.output.fps = 320, 180, "ultrafast", 25
    s.title.enabled = s.subtitle.enabled = False
    s.voice.enabled = False
    s.scene.script = "Đỏ: Chào bạn!\nXanh: Chào!"
    s.scene.image_dir, s.scene.character_dir, s.scene.fade = str(bg), str(cast), 0
    s.scene.seconds_per_scene, s.scene.motion = 1.0, False
    out = scenes.render_scenes(s, tmp_path / "gau_tho.mp4")
    assert probe(out).duration == pytest.approx(1.0, abs=0.2)
    # Nhân vật cao 99 px, rộng 66 px; bụng ở khoảng 60% chiều cao. Trái là Đỏ, phải là Xanh.
    y = 180 - 99 + int(99 * 0.65)
    left, right = _pixel(out, 0.5, 12 + 33, y, 320), _pixel(out, 0.5, 320 - 12 - 33, y, 320)
    assert left[0] > 150 and left[2] < 100, left
    assert right[2] > 150 and right[0] < 100, right


def test_actor_y_expression():
    a = scenes.Actor(Path("f_%05d.png"), "0", talk=[(0.5, 1.5)])
    assert scenes._actor_y(a, 400, False) == "H-h"
    y = scenes._actor_y(a, 400, True)
    assert "sin(" in y and "between(t,0.500,1.500)" in y and y.startswith("'")


def _top_row(video: Path, t: float, x: int, width: int, height: int) -> int:
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(t), "-i", str(video), "-frames:v", "1",
                          "-f", "rawvideo", "-pix_fmt", "gray", "-"], capture_output=True, check=True).stdout
    return next(y for y in range(height) if raw[y * width + x] < 200)


@pytest.mark.parametrize("motion", [True, False])
def test_character_moves_while_talking(tmp_path, monkeypatch, motion):
    from video_studio import voice
    from video_studio.captions import Cue

    def fake_tts(text, name, rate, out_path, retries=2, pitch="+0Hz"):
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "sine=f=300:d=2",
                        "-c:a", "libmp3lame", str(out_path)], check=True)
        return [Cue(0, 2, text)]

    monkeypatch.setattr(voice, "synthesize", fake_tts)
    cast = tmp_path / "dàn"
    cm.make_character(cm.CharacterSpec("Gấu", "gau", "#8D6E63"), cast)
    bg = tmp_path / "nền"
    bg.mkdir()
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=white:s=640x360",
                    "-frames:v", "1", str(bg / "nen.png")], check=True)
    s = RenderSettings()
    s.output.width, s.output.height, s.output.preset, s.output.fps = 640, 360, "ultrafast", 25
    s.title.enabled = s.subtitle.enabled = False
    s.voice.enabled = True
    s.scene.script, s.scene.image_dir, s.scene.character_dir = "Gấu: Xin chào các bạn.", str(bg), str(cast)
    s.scene.fade, s.scene.motion, s.scene.lipsync, s.scene.pause = 0, False, "loudness", 0
    s.scene.character_side, s.scene.character_motion = "center", motion
    out = scenes.render_scenes(s, tmp_path / "nhun.mp4")
    tops = {_top_row(out, t, 320, 640, 360) for t in (0.1, 0.3, 0.55, 0.8, 1.05, 1.3)}
    assert (len(tops) > 1) == motion, tops
