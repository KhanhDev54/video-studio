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
    s.scene.character_dir, s.scene.character_side = "D:/Nhân vật/mèo", "left"
    s.scene.character_height, s.scene.lipsync = 0.4, "loudness"
    s.scene.also_shorts, s.subtitle.export_srt, s.audio.duck_music = True, False, False
    s.voice.pitch = "-20Hz"
    s.scene.thumbnail, s.scene.thumbnail_text = False, "Mèo đi câu"
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


def test_export_also_shorts(window, tmp_path, monkeypatch):
    from video_studio.gui import main_window

    calls = []
    monkeypatch.setattr(main_window, "render_scenes",
                        lambda s, out, **kw: calls.append((out.name, s.output.width, s.output.height)) or out)
    window.out_dir.setText(str(tmp_path))
    window.ratio.setCurrentIndex(window.ratio.findData("1920x1080"))
    window.also_shorts.setChecked(True)
    window._export_scenes()
    window.thread.quit()
    assert window.thread.wait(5000)
    assert calls == [("video_hoathinh.mp4", 1920, 1080), ("video_hoathinh_shorts.mp4", 1080, 1920)]


def test_char_info_lists_cast(window, tmp_path):
    for name in ("Mèo", "Chó"):
        (tmp_path / name).mkdir()
        for shape in ("body", "mouth_X", "mouth_D"):
            (tmp_path / name / f"{shape}.png").write_bytes(b"")
    window.char_dir.setText(str(tmp_path))
    assert "Chó, Mèo" in window.char_info.text()


def test_preset_keeps_fields_without_widgets(window):
    from video_studio.settings import RenderSettings
    s = RenderSettings()
    s.output.fps, s.output.crf, s.title.outline = 30, 18, 7
    window.apply_settings(s)
    got = window.collect_settings()
    assert (got.output.fps, got.output.crf, got.title.outline) == (30, 18, 7)


def test_character_dialog_creates_cast_member(window, tmp_path):
    from video_studio.gui.character_dialog import CharacterDialog
    from video_studio.lipsync import load_cast

    dlg = CharacterDialog(str(tmp_path / "cast"), window)
    dlg.randomize()
    dlg.name.setText("Bé Na")
    dlg.pitch.setValue(15)
    dlg._tick()
    assert not dlg.preview.pixmap().isNull()
    folder = dlg.save(overwrite=False)
    assert folder == tmp_path / "cast" / "Bé Na"
    member = load_cast(tmp_path / "cast")["bé na"]
    assert member.pitch == "+15Hz" and len(member.character.mouths) == 9
    again = CharacterDialog(str(tmp_path / "cast"), window)
    again.set_spec(dlg.spec())
    assert again.save(overwrite=False) is None  # trùng tên, không ghi đè


def test_character_dialog_hand_drawn_parts(window):
    from video_studio import character_maker as cm
    from video_studio.gui.character_dialog import CharacterDialog

    dlg = CharacterDialog("", window)
    assert dlg.kind.currentData() == cm.HAND_DRAWN
    assert dlg.parts["eyes"].text() == "1" and dlg.parts["glasses"].text() == "Không"
    dlg.parts["glasses"].setValue(2)
    assert dlg.spec().parts["glasses"] == "variant02"
    dlg.set_spec(cm.CharacterSpec("Mèo", "meo"))
    assert dlg.spec().parts == {}


def test_character_dialog_save_button_and_debounce(window, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox, QPushButton

    from video_studio.gui.character_dialog import CharacterDialog

    dlg = CharacterDialog(str(tmp_path / "cast"), window)
    dlg.parts["hair"].setValue(40)  # giá trị không được thành thời gian chờ vẽ lại
    assert dlg._debounce.interval() == 250
    save = next(b for b in dlg.findChildren(QPushButton) if b.text() == "Lưu nhân vật")
    save.click()
    assert dlg.saved is not None and (dlg.saved / "body.png").is_file()
    # Trùng tên: nút Lưu phải hỏi ghi đè (trước đây clicked gửi False nên lặng lẽ không lưu).
    asked = []
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: asked.append(a) or QMessageBox.StandardButton.Yes)
    again = CharacterDialog(str(tmp_path / "cast"), window)
    next(b for b in again.findChildren(QPushButton) if b.text() == "Lưu nhân vật").click()
    assert asked and again.saved == dlg.saved
