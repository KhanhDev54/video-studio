import subprocess
from pathlib import Path

import pytest

from video_studio import scenes
from video_studio.media import probe
from video_studio.settings import RenderSettings
from video_studio.thumbnail import make_thumbnail

EXAMPLE = Path(__file__).parent.parent / "examples"


def _gray(path: Path, crop: str) -> bytes:
    return subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-vf", f"crop={crop}", "-f", "rawvideo",
                           "-pix_fmt", "gray", "-"], capture_output=True, check=True).stdout


def _mean(path: Path, crop: str) -> float:
    raw = _gray(path, crop)
    return sum(raw) / len(raw)


@pytest.fixture(scope="module")
def dark_image(tmp_path_factory):
    p = tmp_path_factory.mktemp("ảnh") / "nền tối.png"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=0x101830:s=800x600",
                    "-frames:v", "1", str(p)], check=True)
    return p


def test_thumbnail_has_title_and_character(dark_image, tmp_path):
    out = make_thumbnail(dark_image, "Mèo đi câu cá", tmp_path / "bìa.jpg",
                         character=EXAMPLE / "nhan_vat_mau" / "body.png")
    info = probe(out)
    assert (info.width, info.height) == (1280, 720)
    assert out.stat().st_size < 2 * 1024 * 1024  # giới hạn ảnh bìa của YouTube
    bright = sum(1 for v in _gray(out, "700:250:0:0") if v > 150)  # chữ vàng góc trên trái, nền rất tối
    assert bright > 5000
    assert _mean(out, "200:200:1000:450") > 80  # thân nhân vật màu cam góc phải dưới


def test_scene_export_writes_thumbnail(dark_image, tmp_path):
    s = RenderSettings()
    s.output.width, s.output.height, s.output.preset = 180, 320, "ultrafast"
    s.title.text, s.title.font_size = "Chú mèo lười", 14
    s.scene.script, s.scene.image_dir, s.scene.seconds_per_scene = "Mèo: Xin chào.", str(dark_image.parent), 1
    s.scene.character_dir = str(EXAMPLE / "dan_nhan_vat")
    out = scenes.render_scenes(s, tmp_path / "phim.mp4")
    thumb = tmp_path / "phim_thumbnail.jpg"
    assert out.exists() and (probe(thumb).width, probe(thumb).height) == (720, 1280)  # bản dọc cho Shorts
