"""Quy trình dựng: voice -> chọn đoạn -> chuẩn hoá từng đoạn -> nối -> chèn chữ + trộn âm."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import captions, voice
from .media import NO_WINDOW, probe, require_ffmpeg
from .planner import Segment, plan_segments
from .settings import RenderSettings

Progress = Callable[[float, str], None]


class Cancelled(Exception):
    pass


@dataclass
class VoiceTrack:
    path: Path
    duration: float
    cues: list[captions.Cue]


def _noop(_f: float, _m: str) -> None:
    pass


def _run(cmd: list[str], cancel: threading.Event | None, cwd: Path | None = None) -> None:
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, cwd=cwd,
                            creationflags=NO_WINDOW)
    while True:
        try:
            _, err = proc.communicate(timeout=0.3)
            break
        except subprocess.TimeoutExpired:
            if cancel is not None and cancel.is_set():
                proc.kill()
                proc.communicate()
                raise Cancelled()
    if proc.returncode != 0:
        tail = err.decode("utf-8", "replace").strip().splitlines()[-8:]
        raise RuntimeError("ffmpeg lỗi:\n" + "\n".join(tail))


def _check(cancel: threading.Event | None) -> None:
    if cancel is not None and cancel.is_set():
        raise Cancelled()


def prepare_voice(settings: RenderSettings, workdir: Path) -> VoiceTrack | None:
    v = settings.voice
    if not v.enabled:
        return None
    if v.source == "file":
        # Giọng tự thu: không có mốc từng từ nên phụ đề chia đều lời thoại theo độ dài file.
        path = Path(v.file_path)
        if not v.file_path.strip() or not path.is_file():
            raise ValueError("Chưa chọn file thu âm cho voice hoặc file không tồn tại")
        duration = probe(path).duration
        if duration <= 0:
            raise ValueError(f"File thu âm {path.name} không có âm thanh")
        return VoiceTrack(path, duration, captions.even_cues(v.text, duration, settings.subtitle.max_words))
    out = Path(workdir) / "voice.mp3"
    words = voice.synthesize(v.text, v.voice, v.rate, out, pitch=v.pitch)
    cues = captions.group_words(words, settings.subtitle.max_words)
    return VoiceTrack(out, probe(out).duration, cues)


def _video_filter(settings: RenderSettings) -> str:
    o = settings.output
    if o.fit == "pad":
        fit = (f"scale={o.width}:{o.height}:force_original_aspect_ratio=decrease,"
               f"pad={o.width}:{o.height}:(ow-iw)/2:(oh-ih)/2")
    else:
        fit = f"scale={o.width}:{o.height}:force_original_aspect_ratio=increase,crop={o.width}:{o.height}"
    return f"{fit},fps={o.fps},setsar=1,format=yuv420p"


def _render_segment(ffmpeg: str, seg: Segment, has_audio: bool, settings: RenderSettings,
                    out: Path, cancel: threading.Event | None) -> None:
    o = settings.output
    cmd = [ffmpeg, "-y", "-v", "error", "-ss", f"{seg.start:.3f}", "-t", f"{seg.duration:.3f}", "-i", str(seg.path)]
    use_original = has_audio and settings.audio.keep_original
    if not use_original:
        cmd += ["-f", "lavfi", "-t", f"{seg.duration:.3f}", "-i", "anullsrc=r=44100:cl=stereo"]
    cmd += ["-map", "0:v:0", "-map", "0:a:0" if use_original else "1:a:0",
            "-vf", _video_filter(settings),
            "-af", "aresample=44100,aformat=channel_layouts=stereo",
            "-c:v", "libx264", "-preset", o.preset, "-crf", str(o.crf),
            "-c:a", "aac", "-b:a", "128k", "-shortest", str(out)]
    _run(cmd, cancel)


def finish_video(ffmpeg: str, work: Path, parts: list[Path], duration: float, cues: list[captions.Cue],
                 settings: RenderSettings, base_volume: float, extra_audio: list[tuple[Path, float]],
                 cancel: threading.Event | None, voice_index: int | None = None) -> Path:
    """Nối các đoạn (cùng codec) trong `work`, vẽ tiêu đề + phụ đề, trộn âm thanh của đoạn
    (âm lượng base_volume) với các track thêm và nhạc nền. `voice_index` là vị trí track lời đọc
    (0 = âm thanh của đoạn, 1.. = extra_audio) để hạ nhạc nền khi có lời. Trả về file trong `work`."""
    (work / "list.txt").write_text("".join(f"file '{p.name}'\n" for p in parts), encoding="utf-8")
    _run([ffmpeg, "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", "list.txt",
          "-c", "copy", "base.mp4"], cancel, cwd=work)

    o = settings.output
    ass = captions.build_ass(o.width, o.height, duration, settings.title, settings.subtitle, cues)
    (work / "captions.ass").write_text(ass, encoding="utf-8")

    a = settings.audio
    inputs = ["-i", "base.mp4"]
    mix = [f"[0:a]volume={base_volume}[a0]"]
    labels = ["[a0]"]
    for path, volume in extra_audio:
        inputs += ["-i", str(Path(path).resolve())]
        mix.append(f"[{len(labels)}:a]volume={volume}[a{len(labels)}]")
        labels.append(f"[a{len(labels)}]")
    if a.music_path:
        inputs += ["-stream_loop", "-1", "-i", str(Path(a.music_path).resolve())]
        n = len(labels)
        if a.duck_music and voice_index is not None:
            # Tách track lời đọc (trước khi chỉnh âm lượng) làm tín hiệu điều khiển:
            # nhạc bị nén xuống khi có lời.
            v = voice_index
            mix[v] = mix[v].replace(f"[{v}:a]", f"[{v}:a]asplit=2[vin][sc];[vin]", 1)
            mix.append(f"[{n}:a]volume={a.music_volume}[m];"
                       f"[m][sc]sidechaincompress=threshold=0.02:ratio=10:attack=30:release=500[a{n}]")
        else:
            mix.append(f"[{n}:a]volume={a.music_volume}[a{n}]")
        labels.append(f"[a{n}]")
    graph = ";".join(
        ["[0:v]subtitles=captions.ass[v]"] + mix
        + [f"{''.join(labels)}amix=inputs={len(labels)}:duration=first:normalize=0[a]"]
    )
    out = work / "final.mp4"
    _run([ffmpeg, "-y", "-v", "error", *inputs, "-filter_complex", graph,
          "-map", "[v]", "-map", "[a]", "-t", f"{duration:.3f}",
          "-c:v", "libx264", "-preset", o.preset, "-crf", str(o.crf),
          "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", out.name], cancel, cwd=work)
    return out


def write_srt(settings: RenderSettings, cues: list[captions.Cue], video: Path) -> Path | None:
    if not (settings.subtitle.export_srt and cues):
        return None
    srt = video.with_suffix(".srt")
    srt.write_text(captions.build_srt(cues), encoding="utf-8")
    return srt


def render_one(clips: list[str | Path], settings: RenderSettings, out_path: str | Path, *,
               seed: int | None = None, voice_track: VoiceTrack | None = None,
               progress: Progress = _noop, cancel: threading.Event | None = None) -> Path:
    """Dựng một video. Nếu bật voice mà không truyền voice_track thì tự tạo voice."""
    ffmpeg, _ = require_ffmpeg()
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="vstudio_"))
    try:
        progress(0.02, "Đọc thông tin clip")
        infos = {Path(c): probe(c) for c in clips}
        _check(cancel)

        if voice_track is None and settings.voice.enabled:
            progress(0.05, "Tạo giọng đọc")
            voice_track = prepare_voice(settings, work)
        _check(cancel)

        if voice_track is not None:
            target = voice_track.duration + 0.5
            cues = voice_track.cues
        else:
            target = settings.cut.target_duration
            cues = []

        segments = plan_segments([(p, i.duration) for p, i in infos.items()], settings.cut, target, seed)
        parts: list[Path] = []
        for n, seg in enumerate(segments):
            _check(cancel)
            progress(0.1 + 0.7 * n / len(segments), f"Cắt đoạn {n + 1}/{len(segments)}")
            part = work / f"part_{n:03d}.mp4"
            _render_segment(ffmpeg, seg, infos[seg.path].has_audio, settings, part, cancel)
            parts.append(part)

        progress(0.82, "Nối đoạn")
        duration = sum(s.duration for s in segments)
        a = settings.audio
        extra = [(voice_track.path, settings.voice.volume)] if voice_track is not None else []
        progress(0.88, "Chèn chữ và trộn âm thanh")
        tmp_out = finish_video(ffmpeg, work, parts, duration, cues, settings,
                               a.original_volume if a.keep_original else 0, extra, cancel,
                               voice_index=1 if voice_track is not None else None)
        shutil.move(str(tmp_out), out_path)
        write_srt(settings, cues, out_path)
        progress(1.0, "Xong")
        return out_path
    finally:
        shutil.rmtree(work, ignore_errors=True)


def render_batch(clips: list[str | Path], settings: RenderSettings, out_dir: str | Path, count: int,
                 base_name: str = "video", *, progress: Progress = _noop,
                 cancel: threading.Event | None = None) -> list[Path]:
    """Dựng `count` phiên bản với cách cắt khác nhau; voice chỉ tạo một lần rồi dùng lại."""
    out_dir = Path(out_dir)
    results: list[Path] = []
    with tempfile.TemporaryDirectory(prefix="vstudio_voice_") as vdir:
        progress(0.0, "Chuẩn bị")
        track = prepare_voice(settings, Path(vdir))
        number = 0
        for i in range(count):
            _check(cancel)
            number += 1
            while (out_dir / f"{base_name}_{number:02d}.mp4").exists():  # không ghi đè video đã xuất
                number += 1
            name = out_dir / f"{base_name}_{number:02d}.mp4"

            def sub(f: float, m: str, i=i) -> None:
                progress((i + f) / count, f"[{i + 1}/{count}] {m}")

            results.append(render_one(clips, settings, name, seed=number, voice_track=track,
                                      progress=sub, cancel=cancel))
    return results
