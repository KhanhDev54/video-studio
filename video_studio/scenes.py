"""Hoạt hình theo cảnh: kịch bản -> từng cảnh (ảnh + lời đọc) -> ảnh chuyển động -> ghép video.

Định dạng kịch bản: các cảnh cách nhau bởi một dòng trống. Dòng đầu của cảnh có thể là
[tên_ảnh.png] để chọn ảnh (đường dẫn tương đối tính theo thư mục ảnh). Cảnh không ghi ảnh
lấy ảnh tiếp theo chưa dùng trong thư mục, hết ảnh thì dùng lại ảnh của cảnh trước.

Hội thoại: dòng "Tên: lời thoại" do nhân vật cùng tên trong thư mục dàn nhân vật nói (giọng,
khẩu hình riêng). Dòng không có tên nối tiếp lời của dòng trước; "Kể:" là lời người dẫn chuyện.

    [bo_song.png]
    Ngày xửa ngày xưa, bên bờ sông có hai người bạn.
    Mèo: Hôm nay mình đi câu cá nhé!
    Chó: Được thôi,
    nhưng nhớ mang theo bánh mì.
"""

from __future__ import annotations

import re
import shutil
import tempfile
import threading
from dataclasses import dataclass, field
from pathlib import Path

from . import captions, lipsync, voice
from .media import probe, require_ffmpeg
from .pipeline import Progress, _check, _noop, _run, finish_video, write_srt
from .settings import RenderSettings

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
MOTIONS = ("zoom_in", "pan_right", "zoom_out", "pan_left")
NARRATOR_TAGS = {"kể", "dẫn truyện", "người kể", "người dẫn chuyện"}
LINE_GAP = 0.25  # nghỉ giữa hai câu thoại, giây
_IMAGE_TAG = re.compile(r"^\s*\[(.+?)\]\s*$")
_SPEAKER = re.compile(r"^\s*([^:：]{1,30})\s*[:：]\s*(.*)$")


@dataclass(frozen=True)
class Line:
    speaker: str | None  # khoá nhân vật (viết thường) hoặc None = người dẫn chuyện
    text: str


@dataclass(frozen=True)
class Scene:
    lines: tuple[Line, ...]
    image: Path

    @property
    def text(self) -> str:
        return " ".join(l.text for l in self.lines)

    @property
    def speakers(self) -> list[str]:
        return list(dict.fromkeys(l.speaker for l in self.lines if l.speaker))


def find_images(folder: str | Path) -> list[Path]:
    if not str(folder).strip() or not Path(folder).is_dir():
        return []
    return sorted(p for p in Path(folder).iterdir() if p.suffix.lower() in IMAGE_EXTS and p.is_file())


def _parse_lines(raw: list[str], speakers: set[str]) -> tuple[Line, ...]:
    lines: list[Line] = []
    for row in (r.strip() for r in raw):
        if not row:
            continue
        m = _SPEAKER.match(row)
        name = m.group(1).strip().lower() if m else None
        if m and (name in speakers or name in NARRATOR_TAGS):
            lines.append(Line(name if name in speakers else None, m.group(2).strip()))
        elif lines:  # dòng nối tiếp lời của người đang nói
            lines[-1] = Line(lines[-1].speaker, f"{lines[-1].text} {row}".strip())
        else:
            lines.append(Line(None, row))
    return tuple(l for l in lines if l.text)


def parse_script(script: str, image_dir: str | Path = "", speakers: set[str] | frozenset = frozenset()
                 ) -> list[Scene]:
    """`speakers`: tên nhân vật (viết thường) được nhận là người nói trong dòng "Tên: lời"."""
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
        scenes.append(Scene(_parse_lines(lines, set(speakers)), image))
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


@dataclass
class Actor:
    """Một nhân vật xuất hiện trong cảnh: khung hình đã dựng, vị trí và có lật ngang không."""
    frames: Path
    x: str
    flip: bool = False


def _positions(n: int, side: str, width: int) -> list[str]:
    margin = int(width * 0.04)
    if n == 1:
        return [{"left": str(margin), "center": "(W-w)/2"}.get(side, f"W-w-{margin}")]
    return [f"{margin}+{i}*(W-2*{margin}-w)/{n - 1}" for i in range(n)]


def _needs_flip(faces: str | None, index: int, count: int, side: str) -> bool:
    """Lật để nhân vật quay mặt vào giữa khung. `faces` là hướng nhìn trong hình vẽ gốc."""
    if faces not in ("left", "right"):
        return False
    pos = (index / (count - 1)) if count > 1 else {"left": 0.0, "center": 0.5}.get(side, 1.0)
    if pos == 0.5:
        return False
    want = "right" if pos < 0.5 else "left"
    return faces != want


def _render_scene(ffmpeg: str, scene: Scene, motion: str, duration: float, voice_path: Path | None,
                  settings: RenderSettings, out: Path, cancel: threading.Event | None,
                  actors: list[Actor] = ()) -> None:
    """`actors`: các nhân vật (chuỗi khung từ lipsync.build_frames) phủ lên cảnh theo thứ tự."""
    o, sc = settings.output, settings.scene
    frames = max(1, round(duration * o.fps))
    bg = _motion_filter(motion, o.width, o.height, o.fps, frames, sc.zoom if sc.motion else 0)
    ch = max(2, int(o.height * sc.character_height) // 2 * 2)
    graph = [f"[0:v]{bg}[b0]"]
    for i, actor in enumerate(actors):
        flip = ",hflip" if actor.flip else ""
        graph.append(f"[{i + 2}:v]scale=-2:{ch}{flip},format=rgba[c{i}]")
        graph.append(f"[b{i}][c{i}]overlay=x={actor.x}:y=H-h:format=auto[b{i + 1}]")
    tail = f"[b{len(actors)}]"
    fade = min(sc.fade, duration / 3)
    if fade > 0:
        tail += f"fade=t=in:d={fade:.3f},fade=t=out:st={duration - fade:.3f}:d={fade:.3f},"
    else:
        tail += "null,"
    graph.append(tail + "format=yuv420p[v]")
    # -pattern_type none: tên ảnh có ký tự % không bị hiểu nhầm là chuỗi ảnh.
    cmd = [ffmpeg, "-y", "-v", "error", "-f", "image2", "-pattern_type", "none", "-i", str(scene.image)]
    if voice_path is not None:
        cmd += ["-i", str(voice_path)]
    else:
        cmd += ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo"]
    for actor in actors:
        cmd += ["-framerate", str(o.fps), "-start_number", "0", "-i", str(actor.frames)]
    cmd += ["-filter_complex", ";".join(graph), "-map", "[v]", "-map", "1:a:0",
            "-af", f"aresample=44100,aformat=channel_layouts=stereo,apad,atrim=0:{duration:.3f}",
            "-t", f"{duration:.3f}", "-c:v", "libx264", "-preset", o.preset, "-crf", str(o.crf),
            "-r", str(o.fps), "-c:a", "aac", "-b:a", "128k", str(out)]
    _run(cmd, cancel)


@dataclass
class _SpokenLine:
    line: Line
    start: float
    path: Path | None = None
    duration: float = 0.0
    words: list[captions.Cue] = field(default_factory=list)


def _voice_for(line: Line, cast: dict[str, lipsync.CastMember], settings: RenderSettings
               ) -> tuple[str, str, str, float]:
    v = settings.voice
    m = cast.get(line.speaker) if line.speaker else None
    if m is None:
        return v.voice, v.rate, v.pitch, v.volume
    return m.voice or v.voice, m.rate or v.rate, m.pitch or v.pitch, m.volume * v.volume


def _mix_lines(ffmpeg: str, spoken: list[_SpokenLine], volumes: list[float], out: Path) -> None:
    """Đặt từng câu thoại vào đúng thời điểm (adelay) rồi trộn thành một track."""
    inputs, graph = [], []
    for i, (sp, vol) in enumerate(zip(spoken, volumes)):
        inputs += ["-i", str(sp.path)]
        ms = int(round(sp.start * 1000))
        graph.append(f"[{i}:a]aresample=44100,aformat=channel_layouts=stereo,volume={vol},"
                     f"adelay={ms}|{ms}[l{i}]")
    graph.append("".join(f"[l{i}]" for i in range(len(spoken)))
                 + f"amix=inputs={len(spoken)}:duration=longest:normalize=0[a]")
    _run([ffmpeg, "-y", "-v", "error", *inputs, "-filter_complex", ";".join(graph),
          "-map", "[a]", str(out)], None)


def render_scenes(settings: RenderSettings, out_path: str | Path, *, progress: Progress = _noop,
                  cancel: threading.Event | None = None) -> Path:
    """Dựng video hoạt hình từ settings.scene. Voice (nếu bật) đọc riêng từng câu với giọng của
    người nói và quyết định độ dài cảnh; phụ đề lấy mốc từng từ, không có voice thì chia đều.

    Thư mục nhân vật có body.png: một nhân vật đọc mọi lời. Thư mục chứa nhiều thư mục con có
    body.png: dàn nhân vật cho hội thoại, ai được gọi tên trong cảnh thì xuất hiện trong cảnh đó."""
    sc, v = settings.scene, settings.voice
    narrator: lipsync.Character | None = None
    cast: dict[str, lipsync.CastMember] = {}
    if sc.character_dir.strip():
        folder = Path(sc.character_dir)
        if (folder / "body.png").is_file():
            narrator = lipsync.Character.load(folder)
        else:
            cast = lipsync.load_cast(folder)
            if not cast:
                raise ValueError(f"Thư mục {folder} không có body.png hoặc thư mục nhân vật con nào")
    scenes = parse_script(sc.script, sc.image_dir, set(cast))
    use_tts = v.enabled and v.source == "tts"
    if v.enabled and not use_tts:
        raise ValueError("Chế độ hoạt hình hiện chỉ hỗ trợ giọng AI (Edge TTS) hoặc tắt voice.")
    ffmpeg, _ = require_ffmpeg()
    fps = settings.output.fps
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
            # 1. Lời thoại: mỗi câu một file, đặt nối tiếp nhau với khoảng nghỉ LINE_GAP.
            spoken: list[_SpokenLine] = []
            pos = 0.0
            per_line = max(0.5, sc.seconds_per_scene) / max(1, len(scene.lines))
            for k, line in enumerate(scene.lines):
                sp = _SpokenLine(line, pos)
                if use_tts:
                    name, rate, pitch, _vol = _voice_for(line, cast, settings)
                    sp.path = work / f"line_{n:03d}_{k:02d}.mp3"
                    sp.words = voice.synthesize(line.text, name, rate, sp.path, pitch=pitch)
                    sp.duration = probe(sp.path).duration
                    line_cues = captions.group_words(sp.words, settings.subtitle.max_words)
                else:
                    sp.duration = per_line
                    line_cues = captions.even_cues(line.text, per_line, settings.subtitle.max_words)
                cues += [captions.Cue(c.start + t + pos, c.end + t + pos, c.text) for c in line_cues]
                spoken.append(sp)
                pos += sp.duration + (LINE_GAP if use_tts else 0)
            duration = max(0.5, (pos - (LINE_GAP if use_tts and spoken else 0)) + (sc.pause if use_tts else 0))
            if not scene.lines:
                duration = max(0.5, sc.seconds_per_scene)

            voice_path: Path | None = None
            if use_tts and spoken:
                voice_path = work / f"voice_{n:03d}.wav"
                _mix_lines(ffmpeg, spoken, [_voice_for(sp.line, cast, settings)[3] for sp in spoken], voice_path)

            # 2. Nhân vật: ai nói thì miệng cử động trong câu của mình, còn lại đứng nghỉ.
            def mouths(owner) -> list[lipsync.MouthCue]:
                out: list[lipsync.MouthCue] = []
                for sp in spoken:
                    if sp.path is None or not owner(sp.line):
                        continue
                    out += [lipsync.MouthCue(c.start + sp.start, c.end + sp.start, c.shape)
                            for c in lipsync.mouth_cues(sp.path, ffmpeg, fps, work, sc.lipsync)]
                return out

            actors: list[Actor] = []
            if narrator is not None:
                frames = lipsync.build_frames(narrator, mouths(lambda _l: True), duration, fps, ffmpeg,
                                              work, seed=n * 10)
                actors.append(Actor(frames, _positions(1, sc.character_side, settings.output.width)[0]))
            elif cast:
                names = scene.speakers
                xs = _positions(len(names), sc.character_side, settings.output.width)
                for i, key in enumerate(names):
                    member = cast[key]
                    frames = lipsync.build_frames(member.character, mouths(lambda l, k=key: l.speaker == k),
                                                  duration, fps, ffmpeg, work, seed=n * 10 + i)
                    actors.append(Actor(frames, xs[i], _needs_flip(member.faces, i, len(names),
                                                                    sc.character_side)))

            part = work / f"scene_{n:03d}.mp4"
            motion = MOTIONS[n % len(MOTIONS)] if sc.motion else "none"
            _render_scene(ffmpeg, scene, motion, duration, voice_path, settings, part, cancel, actors)
            parts.append(part)
            t += duration

        progress(0.9, "Ghép cảnh, chèn chữ và nhạc nền")
        tmp_out = finish_video(ffmpeg, work, parts, t, cues, settings, 1.0 if use_tts else 0, [], cancel,
                               voice_index=0 if use_tts else None)
        shutil.move(str(tmp_out), out_path)
        write_srt(settings, cues, out_path)
        progress(1.0, "Xong")
        return out_path
    finally:
        shutil.rmtree(work, ignore_errors=True)
