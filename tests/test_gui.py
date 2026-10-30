import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")


@pytest.fixture
def window(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication

    from video_studio.gui import main_window

    monkeypatch.setattr(main_window, "PRESET_DIR", tmp_path / "presets")
    app = QApplication.instance() or QApplication([])
    w = main_window.MainWindow()
    yield w
    w.close()


def test_settings_roundtrip_through_ui(window):
    from video_studio.settings import RenderSettings

    s = RenderSettings()
    s.cut.min_seg, s.cut.max_seg = 2.0, 4.5
    s.output.width, s.output.height, s.output.fit = 1920, 1080, "pad"
    s.title.text, s.title.color = "Cây chà sàn", "#FF0000"
    s.voice.enabled, s.voice.voice, s.voice.rate = True, "vi-VN-NamMinhNeural", "+10%"
    s.voice.text = "Xin chào"
    s.audio.keep_original, s.audio.music_volume = False, 0.25
    window.apply_settings(s)
    assert window.collect_settings() == s


def test_preset_save_and_apply(window):
    window.title_text.setText("Gia dụng")
    window.preset_name.setText("gia dụng")
    window._save_preset()
    window.title_text.setText("")
    window.preset_combo.setCurrentText("gia dụng")
    window._load_preset()
    assert window.title_text.text() == "Gia dụng"


def test_voice_file_source_roundtrip(window):
    from video_studio.settings import RenderSettings

    s = RenderSettings()
    s.voice.enabled, s.voice.source, s.voice.file_path = True, "file", "C:/Thu âm/giới thiệu.m4a"
    s.voice.text = "Sạch bong không cần cúi"
    window.apply_settings(s)
    assert window.collect_settings() == s
    assert not window.voice_name.isEnabled() and window.voice_file.isEnabled()


def test_scene_settings_roundtrip(window):
    from video_studio.settings import RenderSettings

    s = RenderSettings()
    s.scene.script = "[a.png]\nCảnh một.\n\nCảnh hai."
    s.scene.image_dir, s.scene.seconds_per_scene, s.scene.motion = "D:/Ảnh", 2.5, False
    s.scene.zoom, s.scene.fade, s.scene.pause = 0.25, 0.5, 0.8
    window.apply_settings(s)
    assert window.collect_settings() == s


def test_scene_export_does_not_need_clips(window, tmp_path, monkeypatch):
    from video_studio.gui import main_window

    calls = []
    monkeypatch.setattr(main_window, "render_scenes", lambda s, out, **kw: calls.append(out) or out)
    window.out_dir.setText(str(tmp_path))
    (tmp_path / "video_hoathinh.mp4").write_bytes(b"")
    window._export_scenes()
    window.thread.quit()  # thoát vòng sự kiện của luồng ngay khi job xong
    assert window.thread.wait(5000)
    assert calls == [tmp_path / "video_hoathinh_2.mp4"]
