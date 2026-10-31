import os
import subprocess
from pathlib import Path

import pytest

from video_studio import captions
from video_studio.media import probe
from video_studio.pipeline import render_batch, render_one
from video_studio.planner import plan_segments
from video_studio.settings import CutSettings, PresetStore, RenderSettings


def _make_clip(path: Path, seconds: int, size: str, audio: bool) -> Path:
    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"testsrc=size={size}:rate=25:duration={seconds}"]
    if audio:
        cmd += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}", "-shortest"]
    cmd += ["-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(path)]
    subprocess.run(cmd, check=True)
    return path


@pytest.fixture(scope="module")
def clips(tmp_path_factory):
    d = tmp_path_factory.mktemp("clips")
    return [
        _make_clip(d / "landscape_audio.mp4", 6, "640x360", True),
        _make_clip(d / "portrait_silent.mp4", 4, "360x640", False),
    ]


@pytest.fixture(scope="module")
def music(tmp_path_factory):
    p = tmp_path_factory.mktemp("music") / "music.m4a"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=220:duration=2",
                    "-c:a", "aac", str(p)], check=True)
    return p


def small_settings() -> RenderSettings:
    s = RenderSettings()
    s.output.width, s.output.height, s.output.preset = 360, 640, "ultrafast"
    s.cut.target_duration = 7
    s.title.text = "Cây chà sàn 3 in 1"
    s.title.font_size = 28
    return s


def test_plan_reaches_target_and_respects_bounds():
    cut = CutSettings(min_seg=2, max_seg=3)
    segs = plan_segments([(Path("a.mp4"), 10.0), (Path("b.mp4"), 1.5)], cut, 12, seed=1)
    assert sum(s.duration for s in segs) == pytest.approx(12, abs=0.05)
    for s in segs:
        length = 10.0 if s.path.name == "a.mp4" else 1.5
        assert s.start >= 0 and s.start + s.duration <= length + 1e-6


def test_plan_is_deterministic_per_seed():
    clips_ = [(Path("a.mp4"), 10.0), (Path("b.mp4"), 8.0)]
    cut = CutSettings()
    assert plan_segments(clips_, cut, 20, seed=3) == plan_segments(clips_, cut, 20, seed=3)
    assert plan_segments(clips_, cut, 20, seed=3) != plan_segments(clips_, cut, 20, seed=4)


def test_group_words_breaks_on_punctuation_and_length():
    words = [captions.Cue(i, i + 1, w) for i, w in enumerate("Sạch bong, không cần cúi người lau nhà".split())]
    lines = captions.group_words(words, max_words=4)
    assert [l.text for l in lines] == ["Sạch bong,", "không cần cúi người", "lau nhà"]
    assert lines[1].start == 2 and lines[1].end == 6


def test_ass_contains_title_and_escapes_braces():
    s = RenderSettings()
    s.title.text = "Giá {sốc}"
    ass = captions.build_ass(1080, 1920, 10, s.title, s.subtitle, [captions.Cue(0, 2, "xin chào")])
    assert "Title,,0,0,0,,Giá \\{sốc\\}" in ass
    assert "Sub,,0,0,0,,xin chào" in ass


def test_escape_backslash_does_not_become_ass_command():
    # "\\N" gõ trong chữ phải hiện nguyên văn, không thành xuống dòng.
    assert captions._escape("C:\\New") == "C:\\\u200bNew"


def test_preset_roundtrip(tmp_path):
    store = PresetStore(tmp_path)
    s = RenderSettings()
    s.cut.min_seg = 2.5
    s.title.text = "Gia dụng"
    store.save("gia dụng của trường", s)
    assert store.names() == ["gia dụng của trường"]
    assert store.load("gia dụng của trường") == s


def test_preset_ignores_unknown_keys():
    s = RenderSettings.from_dict({"cut": {"min_seg": 1.0, "khoa_la": 1}, "khac": {}})
    assert s.cut.min_seg == 1.0


def test_render_one_produces_vertical_video(clips, music, tmp_path):
    s = small_settings()
    s.audio.music_path = str(music)
    out = render_one(clips, s, tmp_path / "out.mp4", seed=1)
    info = probe(out)
    assert (info.width, info.height) == (360, 640)
    assert info.has_audio
    assert info.duration == pytest.approx(7, abs=0.3)


def test_render_batch_makes_n_files(clips, tmp_path):
    s = small_settings()
    s.cut.target_duration = 3
    s.output.fit = "pad"
    outs = render_batch(clips, s, tmp_path / "batch", 2, base_name="sp")
    assert [p.name for p in outs] == ["sp_01.mp4", "sp_02.mp4"]
    assert all(p.exists() for p in outs)
    again = render_batch(clips, s, tmp_path / "batch", 1, base_name="sp")  # xuất lại không ghi đè
    assert [p.name for p in again] == ["sp_03.mp4"]


def test_prepare_voice_passes_pitch(monkeypatch, tmp_path):
    from video_studio import pipeline, voice
    seen = {}

    def fake(text, name, rate, out, pitch="+0Hz", **_):
        seen["pitch"] = pitch
        _make_clip(Path(out).with_suffix(".tmp.mp4"), 1, "16x16", True).rename(out)
        return [captions.Cue(0, 0.5, "xin")]

    monkeypatch.setattr(voice, "synthesize", fake)
    s = RenderSettings()
    s.voice.enabled, s.voice.text, s.voice.pitch = True, "xin", "+20Hz"
    pipeline.prepare_voice(s, tmp_path)
    assert seen["pitch"] == "+20Hz"


needs_tts = pytest.mark.skipif(not os.environ.get("VSTUDIO_TEST_TTS"), reason="cần mạng; đặt VSTUDIO_TEST_TTS=1 để chạy")


@needs_tts
def test_edge_tts_returns_word_timings(tmp_path):
    from video_studio import voice

    out = tmp_path / "v.mp3"
    words = voice.synthesize("Cây chà sàn ba trong một.", "vi-VN-HoaiMyNeural", "+0%", out)
    assert out.stat().st_size > 1000 and probe(out).duration > 0.5
    assert len(words) >= 4 and all(w.end > w.start >= 0 for w in words)
    assert "chà" in " ".join(w.text for w in words)


@needs_tts
def test_render_with_voice(clips, tmp_path):
    s = small_settings()
    s.voice.enabled = True
    s.voice.text = "Cây chà sàn ba trong một, sạch bong không cần cúi người."
    out = render_one(clips, s, tmp_path / "voice.mp4", seed=1)
    assert probe(out).duration > 2


def test_render_with_prepared_voice_track(clips, music, tmp_path):
    from video_studio.pipeline import VoiceTrack

    voice_path = tmp_path / "voice.m4a"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=660:duration=4",
                    "-c:a", "aac", str(voice_path)], check=True)
    cues = [captions.Cue(0, 2, "Sạch bong"), captions.Cue(2, 4, "không cần cúi")]
    s = small_settings()
    s.audio.music_path = str(music)
    out = render_one(clips, s, tmp_path / "v.mp4", seed=2, voice_track=VoiceTrack(voice_path, 4.0, cues))
    # Độ dài video bám theo voice (+0.5 s), không theo target_duration.
    assert probe(out).duration == pytest.approx(4.5, abs=0.3)
