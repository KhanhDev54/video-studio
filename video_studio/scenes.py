"""Hoạt hình theo cảnh: kịch bản -> từng cảnh (ảnh + lời đọc) -> ảnh chuyển động -> ghép video.

Định dạng kịch bản: các cảnh cách nhau bởi một dòng trống. Dòng đầu của cảnh có thể là
[tên_ảnh.png] để chọn ảnh (đường dẫn tương đối tính theo thư mục ảnh). Cảnh không ghi ảnh
lấy ảnh tiếp theo chưa dùng trong thư mục, hết ảnh thì dùng lại ảnh của cảnh trước.

    [meo_ngu.png]
    Ngày xửa ngày xưa, có một chú mèo lười.

    Một hôm, chú quyết định đi câu cá.
"""

from __future__ import annotations

import re
import shutil
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path

from . import captions, voice
from .media import probe, require_ffmpeg
from .pipeline import Progress, _check, _noop, _run, finish_video
from .settings import RenderSettings

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
MOTIONS = ("zoom_in", "pan_right", "zoom_out", "pan_left")
_IMAGE_TAG = re.compile(r"^\s*\[(.+?)\]\s*$")


@dataclass(frozen=True)
class Scene:
    text: str
    image: Path


def find_images(folder: str | Path) -> list[Path]:
    if not str(folder).strip() or not Path(folder).is_dir():
        return []
    return sorted(p for p in Path(folder).iterdir() if p.suffix.lower() in IMAGE_EXTS and p.is_file())


def parse_script(script: str, image_dir: str | Path = "") -> list[Scene]:
    blocks = [b.strip() for b in re.split(r"\n\s*\n", script.replace("\r\n", "\n")) if b.strip()]
    if not blocks:
        raise ValueError("Kịch bản trống. Mỗi cảnh là một đoạn, các cảnh cách nhau bởi một dòng trống.")
    folder = Path(image_dir) if str(image_dir).strip() else None
    pool = find_images(folder) if folder else []
    scenes: list[Scene] = []
    for n, block in enumerate(blocks, 1):
        lines = block.splitlines()
        image: Path | None = None
        m = _IMAGE_TAG.match(lines[0])
        if m:
            lines = lines[1:]
            image = Path(m.group(1).strip())
            if not image.is_absolute() and folder is not None:
                image = folder / image
            if not image.is_file():
                raise ValueError(f"Cảnh {n}: không tìm thấy ảnh {image}")
            if image in pool:
                pool.remove(image)
        elif pool:
            image = pool.pop(0)
        elif scenes:
            image = scenes[-1].image
        else:
            raise ValueError(f"Cảnh {n} chưa có ảnh: ghi [tên_ảnh] ở dòng đầu hoặc chọn thư mục ảnh.")
        scenes.append(Scene(" ".join(l.strip() for l in lines if l.strip()), image))
    return scenes


def _motion_filter(motion: str, w: int, h: int, fps: int, frames: int, zoom: float) -> str:
    """Ảnh -> `frames` khung hình WxH. Phóng ảnh lên 2 lần trước khi zoompan cho chuyển động mượt."""
    W, H = w * 2, h * 2
    fill = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1"
    n = max(1, frames - 1)
    cx, cy = "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    if motion == "zoom_in":
        z, x, y = f"1+{zoom}*on/{n}", cx, cy
    elif motion == "zoom_out":
        z, x, y = f"{1 + zoom}-{zoom}*on/{n}", cx, cy
    elif motion == "pan_right":
        z, x, y = f"{1 + zoom}", f"(iw-iw/zoom)*on/{n}", cy
    elif motion == "pan_left":
        z, x, y = f"{1 + zoom}", f"(iw-iw/zoom)*(1-on/{n})", cy
    else:
        z, x, y = "1", "0", "0"
    return f"{fill},zoompan=z='{z}':x='{x}':y='{y}':d={frames}:s={w}x{h}:fps={fps}"


def _render_scene(ffmpeg: str, scene: Scene, motion: str, duration: float, voice_path: Path | None,
                  settings: RenderSettings, out: Path, cancel: threading.Event | None) -> None:
    o, sc = settings.output, settings.scene
    frames = max(1, round(duration * o.fps))
    vf = _motion_filter(motion, o.width, o.height, o.fps, frames, sc.zoom if sc.motion else 0)
    fade = min(sc.fade, duration / 3)
    if fade > 0:
        vf += f",fade=t=in:d={fade:.3f},fade=t=out:st={duration - fade:.3f}:d={fade:.3f}"
    vf += ",format=yuv420p"
    # -pattern_type none: tên ảnh có ký tự % không bị hiểu nhầm là chuỗi ảnh.
    cmd = [ffmpeg, "-y", "-v", "error", "-f", "image2", "-pattern_type", "none", "-i", str(scene.image)]
    if voice_path is not None:
        cmd += ["-i", str(voice_path)]
    else:
        cmd += ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo"]
    cmd += ["-map", "0:v:0", "-map", "1:a:0", "-vf", vf,
            "-af", f"aresample=44100,aformat=channel_layouts=stereo,apad,atrim=0:{duration:.3f}",
            "-t", f"{duration:.3f}", "-c:v", "libx264", "-preset", o.preset, "-crf", str(o.crf),
            "-r", str(o.fps), "-c:a", "aac", "-b:a", "128k", str(out)]
    _run(cmd, cancel)


def render_scenes(settings: RenderSettings, out_path: str | Path, *, progress: Progress = _noop,
                  cancel: threading.Event | None = None) -> Path:
    """Dựng video hoạt hình từ settings.scene. Voice (nếu bật) đọc riêng từng cảnh và quyết định
    độ dài cảnh; phụ đề lấy mốc từng từ của voice, không có voice thì chia đều theo cảnh."""
    sc, v = settings.scene, settings.voice
    scenes = parse_script(sc.script, sc.image_dir)
    use_tts = v.enabled and v.source == "tts"
    if v.enabled and not use_tts:
        raise ValueError("Chế độ hoạt hình hiện chỉ hỗ trợ giọng AI (Edge TTS) hoặc tắt voice.")
    ffmpeg, _ = require_ffmpeg()
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="vstudio_scenes_"))
    try:
        parts: list[Path] = []
        cues: list[captions.Cue] = []
        t = 0.0
        for n, scene in enumerate(scenes):
            _check(cancel)
            progress(0.85 * n / len(scenes), f"Cảnh {n + 1}/{len(scenes)}")
            voice_path: Path | None = None
            if use_tts and scene.text:
                voice_path = work / f"voice_{n:03d}.mp3"
                words = voice.synthesize(scene.text, v.voice, v.rate, voice_path)
                duration = probe(voice_path).duration + sc.pause
                scene_cues = captions.group_words(words, settings.subtitle.max_words)
            else:
                duration = max(0.5, sc.seconds_per_scene)
                scene_cues = captions.even_cues(scene.text, max(0.1, duration - sc.pause),
                                                settings.subtitle.max_words)
            cues += [captions.Cue(c.start + t, c.end + t, c.text) for c in scene_cues]
            part = work / f"scene_{n:03d}.mp4"
            motion = MOTIONS[n % len(MOTIONS)] if sc.motion else "none"
            _render_scene(ffmpeg, scene, motion, duration, voice_path, settings, part, cancel)
            parts.append(part)
            t += duration

        progress(0.9, "Ghép cảnh, chèn chữ và nhạc nền")
        base_volume = v.volume if use_tts else 0
        tmp_out = finish_video(ffmpeg, work, parts, t, cues, settings, base_volume, [], cancel)
        shutil.move(str(tmp_out), out_path)
        progress(1.0, "Xong")
        return out_path
    finally:
        shutil.rmtree(work, ignore_errors=True)
