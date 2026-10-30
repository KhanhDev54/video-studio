"""Cửa sổ chính: nhập file bên trái, preview ở giữa, các tab cài đặt bên phải."""

from __future__ import annotations

import os
import tempfile
import threading
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QThread, QUrl, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QColorDialog, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout,
    QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget, QMainWindow, QMessageBox, QPlainTextEdit,
    QProgressBar, QPushButton, QSpinBox, QSplitter, QTabWidget, QVBoxLayout, QWidget,
)

from .. import __version__
from ..media import VIDEO_EXTS, find_videos
from ..pipeline import Cancelled, render_batch, render_one
from ..scenes import render_scenes
from ..settings import PresetStore, RenderSettings
from ..voice import VIETNAMESE_VOICES

PRESET_DIR = Path.home() / ".video_studio" / "presets"

STYLE = """
QWidget { background: #1e1f24; color: #e6e6e6; font-size: 13px; }
QGroupBox { border: 1px solid #34363d; border-radius: 6px; margin-top: 14px; padding-top: 6px; font-weight: bold; }
QGroupBox::title { subcontrol-origin: margin; left: 8px; color: #8fb8ff; }
QPushButton { background: #2f6fde; border: none; border-radius: 4px; padding: 6px 10px; }
QPushButton:hover { background: #3d7ff0; }
QPushButton:disabled { background: #3a3c44; color: #888; }
QPushButton#export { background: #23a55a; font-size: 15px; font-weight: bold; padding: 10px; }
QPushButton#stop { background: #c93636; }
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPlainTextEdit, QListWidget {
  background: #26282e; border: 1px solid #3a3c44; border-radius: 4px; padding: 3px; }
QTabBar::tab { background: #26282e; padding: 6px 12px; }
QTabBar::tab:selected { background: #2f6fde; }
QProgressBar { border: 1px solid #3a3c44; border-radius: 4px; text-align: center; }
QProgressBar::chunk { background: #23a55a; }
"""


class Worker(QObject):
    progress = Signal(float, str)
    finished = Signal(list)
    failed = Signal(str)

    def __init__(self, fn, cancel: threading.Event):
        super().__init__()
        self.fn, self.cancel = fn, cancel

    def run(self):
        try:
            self.finished.emit(self.fn(lambda f, m: self.progress.emit(f, m), self.cancel))
        except Cancelled:
            self.failed.emit("Đã dừng.")
        except Exception as e:  # hiện mọi lỗi ra giao diện thay vì làm sập app
            self.failed.emit(str(e))


class ColorButton(QPushButton):
    def __init__(self, color: str):
        super().__init__()
        self.clicked.connect(self._pick)
        self.set_color(color)

    def set_color(self, color: str):
        self.color = color
        self.setText(color)
        self.setStyleSheet(f"background:{color}; color:{'#000' if QColor(color).lightness() > 128 else '#fff'};")

    def _pick(self):
        c = QColorDialog.getColor(QColor(self.color), self)
        if c.isValid():
            self.set_color(c.name().upper())


def _spin(lo, hi, value, step=1.0, decimals=1):
    w = QDoubleSpinBox()
    w.setRange(lo, hi)
    w.setDecimals(decimals)
    w.setSingleStep(step)
    w.setValue(value)
    return w


def _ispin(lo, hi, value):
    w = QSpinBox()
    w.setRange(lo, hi)
    w.setValue(value)
    return w


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"Video Studio v{__version__}")
        self.resize(1400, 860)
        self.presets = PresetStore(PRESET_DIR)
        self.thread: QThread | None = None
        self.cancel = threading.Event()
        self.preview_dir = Path(tempfile.mkdtemp(prefix="vstudio_preview_"))

        splitter = QSplitter()
        splitter.addWidget(self._build_left())
        splitter.addWidget(self._build_preview())
        splitter.addWidget(self._build_tabs())
        splitter.setSizes([320, 480, 600])
        self.setCentralWidget(splitter)
        self.apply_settings(RenderSettings())
        self._refresh_presets()

    # ---------- bố cục ----------
    def _build_left(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)

        box = QGroupBox("1. Video nguồn (của bạn)")
        b = QVBoxLayout(box)
        row = QHBoxLayout()
        add_files = QPushButton("Chọn video")
        add_files.clicked.connect(self._add_files)
        add_dir = QPushButton("Chọn thư mục")
        add_dir.clicked.connect(self._add_folder)
        row.addWidget(add_files)
        row.addWidget(add_dir)
        b.addLayout(row)
        self.clip_list = QListWidget()
        b.addWidget(self.clip_list)
        clear = QPushButton("Xoá danh sách")
        clear.setObjectName("stop")
        clear.clicked.connect(self.clip_list.clear)
        b.addWidget(clear)
        lay.addWidget(box)

        box = QGroupBox("2. Đầu ra")
        f = QFormLayout(box)
        out_row = QHBoxLayout()
        self.out_dir = QLineEdit(str(Path.home() / "Videos" / "video_studio"))
        pick = QPushButton("…")
        pick.setFixedWidth(32)
        pick.clicked.connect(self._pick_out_dir)
        out_row.addWidget(self.out_dir)
        out_row.addWidget(pick)
        f.addRow("Thư mục", out_row)
        self.base_name = QLineEdit("video")
        f.addRow("Tên file", self.base_name)
        self.count = _ispin(1, 100, 3)
        f.addRow("Số video", self.count)
        lay.addWidget(box)

        self.export_btn = QPushButton("▶  Xuất hàng loạt")
        self.export_btn.setObjectName("export")
        self.export_btn.clicked.connect(self._export)
        self.stop_btn = QPushButton("■  Dừng")
        self.stop_btn.setObjectName("stop")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.cancel.set)
        open_out = QPushButton("Mở thư mục xuất")
        open_out.clicked.connect(self._open_out_dir)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.status = QLabel("Sẵn sàng")
        self.status.setWordWrap(True)
        for x in (self.export_btn, self.stop_btn, open_out, self.progress, self.status):
            lay.addWidget(x)
        lay.addStretch()
        return w

    def _build_preview(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        title = QLabel("XEM TRƯỚC")
        title.setAlignment(Qt.AlignCenter)
        lay.addWidget(title)
        try:
            from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
            from PySide6.QtMultimediaWidgets import QVideoWidget

            self.video = QVideoWidget()
            self.player = QMediaPlayer(self)
            self.audio_out = QAudioOutput(self)
            self.player.setAudioOutput(self.audio_out)
            self.player.setVideoOutput(self.video)
            lay.addWidget(self.video, 1)
        except Exception:  # máy thiếu codec/backend multimedia: vẫn dùng app được
            self.player = None
            lay.addWidget(QLabel("Không mở được trình phát. Video preview sẽ được lưu ra file."), 1)
        row = QHBoxLayout()
        self.preview_btn = QPushButton("Dựng preview nhanh")
        self.preview_btn.clicked.connect(self._preview)
        play = QPushButton("Phát / Dừng")
        play.clicked.connect(self._toggle_play)
        row.addWidget(self.preview_btn)
        row.addWidget(play)
        lay.addLayout(row)
        return w

    def _build_tabs(self) -> QWidget:
        tabs = QTabWidget()

        # Cắt ghép
        t = QWidget()
        f = QFormLayout(t)
        self.min_seg = _spin(0.5, 60, 3)
        self.max_seg = _spin(0.5, 60, 6)
        self.target = _spin(3, 600, 30)
        self.shuffle_clips = QCheckBox("Xáo trộn thứ tự video")
        self.shuffle_segments = QCheckBox("Xáo trộn đoạn")
        self.fit = QComboBox()
        self.fit.addItem("Cắt lấp đầy khung", "crop")
        self.fit.addItem("Giữ nguyên, thêm viền", "pad")
        self.ratio = QComboBox()
        self.ratio.addItem("9:16 (1080x1920)", "1080x1920")
        self.ratio.addItem("16:9 (1920x1080)", "1920x1080")
        self.ratio.addItem("1:1 (1080x1080)", "1080x1080")
        f.addRow("Đoạn ngắn nhất (s)", self.min_seg)
        f.addRow("Đoạn dài nhất (s)", self.max_seg)
        f.addRow("Độ dài video (s)", self.target)
        f.addRow(QLabel("Khi bật voice, độ dài video theo độ dài lời đọc."))
        f.addRow(self.shuffle_clips)
        f.addRow(self.shuffle_segments)
        f.addRow("Khung hình", self.ratio)
        f.addRow("Cách khớp khung", self.fit)
        tabs.addTab(t, "Cắt ghép")

        # Chữ & phụ đề
        t = QWidget()
        lay = QVBoxLayout(t)
        g = QGroupBox("Tiêu đề sản phẩm")
        f = QFormLayout(g)
        self.title_on = QCheckBox("Hiện tiêu đề trên video")
        self.title_text = QLineEdit()
        self.title_text.setPlaceholderText("VD: CÂY CHÀ SÀN 3 IN 1")
        self.title_font = QLineEdit()
        self.title_size = _ispin(10, 200, 72)
        self.title_color = ColorButton("#FFFFFF")
        self.title_margin = _ispin(0, 1500, 220)
        f.addRow(self.title_on)
        f.addRow("Nội dung", self.title_text)
        f.addRow("Font", self.title_font)
        f.addRow("Cỡ chữ", self.title_size)
        f.addRow("Màu", self.title_color)
        f.addRow("Cách mép trên (px)", self.title_margin)
        lay.addWidget(g)
        g = QGroupBox("Phụ đề (từ lời đọc)")
        f = QFormLayout(g)
        self.sub_on = QCheckBox("Hiện phụ đề")
        self.sub_font = QLineEdit()
        self.sub_size = _ispin(10, 200, 64)
        self.sub_color = ColorButton("#FFFF00")
        self.sub_margin = _ispin(0, 1500, 300)
        self.sub_words = _ispin(1, 20, 6)
        f.addRow(self.sub_on)
        f.addRow("Font", self.sub_font)
        f.addRow("Cỡ chữ", self.sub_size)
        f.addRow("Màu", self.sub_color)
        f.addRow("Cách mép dưới (px)", self.sub_margin)
        f.addRow("Số chữ mỗi dòng", self.sub_words)
        lay.addWidget(g)
        lay.addStretch()
        tabs.addTab(t, "Chữ && Phụ đề")

        # Voice
        t = QWidget()
        f = QFormLayout(t)
        self.voice_on = QCheckBox("Dùng giọng đọc")
        self.voice_source = QComboBox()
        self.voice_source.addItem("Giọng AI (Edge TTS, cần mạng)", "tts")
        self.voice_source.addItem("File thu âm của bạn", "file")
        voice_file_row = QHBoxLayout()
        self.voice_file = QLineEdit()
        self.voice_file.setPlaceholderText("File giọng tự thu (mp3, m4a, wav)")
        pick_voice = QPushButton("…")
        pick_voice.setFixedWidth(32)
        pick_voice.clicked.connect(self._pick_voice_file)
        voice_file_row.addWidget(self.voice_file)
        voice_file_row.addWidget(pick_voice)
        self.voice_name = QComboBox()
        for key, label in VIETNAMESE_VOICES.items():
            self.voice_name.addItem(label, key)
        self.voice_rate = _ispin(-50, 100, 0)
        self.voice_rate.setSuffix(" %")
        self.voice_volume = _spin(0, 3, 1, 0.1)
        self.voice_text = QPlainTextEdit()
        self.voice_text.setPlaceholderText("Lời thoại giới thiệu sản phẩm…")
        f.addRow(self.voice_on)
        f.addRow("Nguồn giọng", self.voice_source)
        f.addRow("File thu âm", voice_file_row)
        f.addRow("Giọng", self.voice_name)
        f.addRow("Tốc độ", self.voice_rate)
        f.addRow("Âm lượng", self.voice_volume)
        f.addRow("Lời thoại", self.voice_text)
        f.addRow(QLabel("Với file thu âm, lời thoại chỉ dùng làm phụ đề (chia đều theo độ dài file)."))
        self.voice_source.currentIndexChanged.connect(self._update_voice_source)
        tabs.addTab(t, "Voice")

        # Âm thanh
        t = QWidget()
        f = QFormLayout(t)
        self.keep_orig = QCheckBox("Giữ âm thanh gốc của video")
        self.orig_volume = _spin(0, 3, 0.3, 0.1)
        music_row = QHBoxLayout()
        self.music_path = QLineEdit()
        self.music_path.setPlaceholderText("Nhạc nền bạn có quyền sử dụng (mp3, m4a, wav)")
        pick = QPushButton("…")
        pick.setFixedWidth(32)
        pick.clicked.connect(self._pick_music)
        music_row.addWidget(self.music_path)
        music_row.addWidget(pick)
        self.music_volume = _spin(0, 3, 0.15, 0.05, 2)
        f.addRow(self.keep_orig)
        f.addRow("Âm lượng gốc", self.orig_volume)
        f.addRow("Nhạc nền", music_row)
        f.addRow("Âm lượng nhạc", self.music_volume)
        tabs.addTab(t, "Âm thanh")

        # Hoạt hình theo cảnh
        t = QWidget()
        f = QFormLayout(t)
        self.scene_script = QPlainTextEdit()
        self.scene_script.setPlaceholderText(
            "Mỗi cảnh một đoạn, cách nhau bởi một dòng trống.\n"
            "Dòng đầu có thể là [tên_ảnh.png] để chọn ảnh cho cảnh.\n\n"
            "[meo_ngu.png]\nNgày xửa ngày xưa, có một chú mèo lười.\n\n"
            "Một hôm, chú quyết định đi câu cá.")
        image_row = QHBoxLayout()
        self.scene_dir = QLineEdit()
        self.scene_dir.setPlaceholderText("Thư mục ảnh nhân vật/bối cảnh của bạn")
        pick = QPushButton("…")
        pick.setFixedWidth(32)
        pick.clicked.connect(self._pick_scene_dir)
        image_row.addWidget(self.scene_dir)
        image_row.addWidget(pick)
        self.scene_seconds = _spin(0.5, 60, 4)
        self.scene_pause = _spin(0, 5, 0.4, 0.1)
        self.scene_motion = QCheckBox("Ảnh chuyển động (zoom, lia)")
        self.scene_zoom = _spin(0, 0.5, 0.15, 0.05, 2)
        self.scene_fade = _spin(0, 2, 0.3, 0.1)
        scene_btns = QHBoxLayout()
        self.scene_preview_btn = QPushButton("Preview hoạt hình")
        self.scene_preview_btn.clicked.connect(self._preview_scenes)
        self.scene_export_btn = QPushButton("Xuất video hoạt hình")
        self.scene_export_btn.setObjectName("export")
        self.scene_export_btn.clicked.connect(self._export_scenes)
        scene_btns.addWidget(self.scene_preview_btn)
        scene_btns.addWidget(self.scene_export_btn)
        f.addRow("Kịch bản", self.scene_script)
        f.addRow("Thư mục ảnh", image_row)
        f.addRow("Giây/cảnh (khi tắt voice)", self.scene_seconds)
        f.addRow("Nghỉ sau lời đọc (s)", self.scene_pause)
        f.addRow(self.scene_motion)
        f.addRow("Mức zoom/lia", self.scene_zoom)
        f.addRow("Mờ chuyển cảnh (s)", self.scene_fade)
        f.addRow(QLabel("Giọng đọc, phụ đề, tiêu đề, nhạc nền và khung hình lấy từ các tab khác.\n"
                        "Chỉ dùng ảnh bạn tự vẽ, tự tạo hoặc có quyền sử dụng."))
        f.addRow(scene_btns)
        tabs.addTab(t, "Hoạt hình")

        # Preset
        t = QWidget()
        f = QFormLayout(t)
        self.preset_name = QLineEdit()
        self.preset_name.setPlaceholderText("Tên preset…")
        save = QPushButton("Lưu cài đặt hiện tại")
        save.clicked.connect(self._save_preset)
        self.preset_combo = QComboBox()
        apply = QPushButton("Áp dụng")
        apply.clicked.connect(self._load_preset)
        delete = QPushButton("Xoá")
        delete.setObjectName("stop")
        delete.clicked.connect(self._delete_preset)
        row = QHBoxLayout()
        row.addWidget(self.preset_combo, 1)
        row.addWidget(apply)
        row.addWidget(delete)
        f.addRow("Tên", self.preset_name)
        f.addRow(save)
        f.addRow("Preset", row)
        f.addRow(QLabel(f"Lưu tại: {PRESET_DIR}"))
        tabs.addTab(t, "Preset")
        return tabs

    # ---------- đồng bộ cài đặt <-> giao diện ----------
    def collect_settings(self) -> RenderSettings:
        s = RenderSettings()
        s.cut.min_seg, s.cut.max_seg = self.min_seg.value(), self.max_seg.value()
        s.cut.target_duration = self.target.value()
        s.cut.shuffle_clips = self.shuffle_clips.isChecked()
        s.cut.shuffle_segments = self.shuffle_segments.isChecked()
        s.output.width, s.output.height = map(int, self.ratio.currentData().split("x"))
        s.output.fit = self.fit.currentData()
        s.title.enabled = self.title_on.isChecked()
        s.title.text = self.title_text.text()
        s.title.font = self.title_font.text() or "Arial"
        s.title.font_size = self.title_size.value()
        s.title.color = self.title_color.color
        s.title.margin_v = self.title_margin.value()
        s.subtitle.enabled = self.sub_on.isChecked()
        s.subtitle.font = self.sub_font.text() or "Arial"
        s.subtitle.font_size = self.sub_size.value()
        s.subtitle.color = self.sub_color.color
        s.subtitle.margin_v = self.sub_margin.value()
        s.subtitle.max_words = self.sub_words.value()
        s.voice.enabled = self.voice_on.isChecked()
        s.voice.source = self.voice_source.currentData()
        s.voice.file_path = self.voice_file.text().strip()
        s.voice.voice = self.voice_name.currentData()
        s.voice.rate = f"{self.voice_rate.value():+d}%"
        s.voice.volume = self.voice_volume.value()
        s.voice.text = self.voice_text.toPlainText()
        s.audio.keep_original = self.keep_orig.isChecked()
        s.audio.original_volume = self.orig_volume.value()
        s.audio.music_path = self.music_path.text().strip()
        s.audio.music_volume = self.music_volume.value()
        s.scene.script = self.scene_script.toPlainText()
        s.scene.image_dir = self.scene_dir.text().strip()
        s.scene.seconds_per_scene = self.scene_seconds.value()
        s.scene.pause = self.scene_pause.value()
        s.scene.motion = self.scene_motion.isChecked()
        s.scene.zoom = self.scene_zoom.value()
        s.scene.fade = self.scene_fade.value()
        return s

    def apply_settings(self, s: RenderSettings) -> None:
        self.min_seg.setValue(s.cut.min_seg)
        self.max_seg.setValue(s.cut.max_seg)
        self.target.setValue(s.cut.target_duration)
        self.shuffle_clips.setChecked(s.cut.shuffle_clips)
        self.shuffle_segments.setChecked(s.cut.shuffle_segments)
        i = self.ratio.findData(f"{s.output.width}x{s.output.height}")
        self.ratio.setCurrentIndex(max(i, 0))
        self.fit.setCurrentIndex(max(self.fit.findData(s.output.fit), 0))
        self.title_on.setChecked(s.title.enabled)
        self.title_text.setText(s.title.text)
        self.title_font.setText(s.title.font)
        self.title_size.setValue(s.title.font_size)
        self.title_color.set_color(s.title.color)
        self.title_margin.setValue(s.title.margin_v)
        self.sub_on.setChecked(s.subtitle.enabled)
        self.sub_font.setText(s.subtitle.font)
        self.sub_size.setValue(s.subtitle.font_size)
        self.sub_color.set_color(s.subtitle.color)
        self.sub_margin.setValue(s.subtitle.margin_v)
        self.sub_words.setValue(s.subtitle.max_words)
        self.voice_on.setChecked(s.voice.enabled)
        self.voice_source.setCurrentIndex(max(self.voice_source.findData(s.voice.source), 0))
        self.voice_file.setText(s.voice.file_path)
        self._update_voice_source()
        self.voice_name.setCurrentIndex(max(self.voice_name.findData(s.voice.voice), 0))
        try:
            self.voice_rate.setValue(int(s.voice.rate.rstrip("%")))
        except ValueError:
            self.voice_rate.setValue(0)
        self.voice_volume.setValue(s.voice.volume)
        self.voice_text.setPlainText(s.voice.text)
        self.keep_orig.setChecked(s.audio.keep_original)
        self.orig_volume.setValue(s.audio.original_volume)
        self.music_path.setText(s.audio.music_path)
        self.music_volume.setValue(s.audio.music_volume)
        self.scene_script.setPlainText(s.scene.script)
        self.scene_dir.setText(s.scene.image_dir)
        self.scene_seconds.setValue(s.scene.seconds_per_scene)
        self.scene_pause.setValue(s.scene.pause)
        self.scene_motion.setChecked(s.scene.motion)
        self.scene_zoom.setValue(s.scene.zoom)
        self.scene_fade.setValue(s.scene.fade)

    # ---------- hành động ----------
    def clips(self) -> list[str]:
        return [self.clip_list.item(i).text() for i in range(self.clip_list.count())]

    def _add_paths(self, paths):
        existing = set(self.clips())
        for p in paths:
            if str(p) not in existing:
                self.clip_list.addItem(str(p))

    def _add_files(self):
        exts = " ".join(f"*{e}" for e in sorted(VIDEO_EXTS))
        files, _ = QFileDialog.getOpenFileNames(self, "Chọn video", "", f"Video ({exts})")
        self._add_paths(files)

    def _add_folder(self):
        d = QFileDialog.getExistingDirectory(self, "Chọn thư mục video")
        if d:
            self._add_paths(find_videos(d))

    def _pick_out_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Chọn nơi lưu", self.out_dir.text())
        if d:
            self.out_dir.setText(d)

    def _pick_music(self):
        f, _ = QFileDialog.getOpenFileName(self, "Chọn nhạc nền", "", "Audio (*.mp3 *.m4a *.wav *.aac *.ogg)")
        if f:
            self.music_path.setText(f)

    def _pick_scene_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Chọn thư mục ảnh", self.scene_dir.text())
        if d:
            self.scene_dir.setText(d)

    def _pick_voice_file(self):
        f, _ = QFileDialog.getOpenFileName(self, "Chọn file thu âm", "", "Audio (*.mp3 *.m4a *.wav *.aac *.ogg)")
        if f:
            self.voice_file.setText(f)

    def _update_voice_source(self):
        tts = self.voice_source.currentData() == "tts"
        self.voice_name.setEnabled(tts)
        self.voice_rate.setEnabled(tts)
        self.voice_file.setEnabled(not tts)

    def _open_out_dir(self):
        from PySide6.QtGui import QDesktopServices

        Path(self.out_dir.text()).mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(self.out_dir.text()))

    def _refresh_presets(self):
        self.preset_combo.clear()
        self.preset_combo.addItems(self.presets.names())

    def _save_preset(self):
        name = self.preset_name.text().strip()
        try:
            self.presets.save(name, self.collect_settings())
        except ValueError as e:
            QMessageBox.warning(self, "Preset", str(e))
            return
        self._refresh_presets()
        self.status.setText(f"Đã lưu preset “{name}”")

    def _load_preset(self):
        name = self.preset_combo.currentText()
        if name:
            self.apply_settings(self.presets.load(name))
            self.status.setText(f"Đã áp dụng preset “{name}”")

    def _delete_preset(self):
        name = self.preset_combo.currentText()
        if name and QMessageBox.question(self, "Xoá preset", f"Xoá preset “{name}”?") == QMessageBox.Yes:
            self.presets.delete(name)
            self._refresh_presets()

    def _toggle_play(self):
        if self.player is None:
            return
        from PySide6.QtMultimedia import QMediaPlayer

        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def _start(self, fn, on_done, need_clips: bool = True):
        if need_clips and not self.clips():
            QMessageBox.information(self, "Thiếu video", "Hãy chọn ít nhất một video nguồn.")
            return
        self.cancel.clear()
        self.thread = QThread()
        self.worker = Worker(fn, self.cancel)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(lambda f, m: (self.progress.setValue(int(f * 1000)), self.status.setText(m)))
        self.worker.finished.connect(on_done)
        self.worker.failed.connect(lambda m: self.status.setText(f"Lỗi: {m}" if m != "Đã dừng." else m))
        for sig in (self.worker.finished, self.worker.failed):
            sig.connect(self.thread.quit)
            sig.connect(lambda *_: self._busy(False))
        self.thread.finished.connect(self.thread.deleteLater)
        self._busy(True)
        self.thread.start()

    def _busy(self, busy: bool):
        for b in (self.export_btn, self.preview_btn, self.scene_export_btn, self.scene_preview_btn):
            b.setEnabled(not busy)
        self.stop_btn.setEnabled(busy)

    def _export(self):
        clips, s = self.clips(), self.collect_settings()
        out_dir, count = self.out_dir.text(), self.count.value()
        base = self.base_name.text().strip() or "video"

        def job(progress, cancel):
            return render_batch(clips, s, out_dir, count, base, progress=progress, cancel=cancel)

        self._start(job, lambda paths: self.status.setText(f"Đã xuất {len(paths)} video vào {out_dir}"))

    def _preview_settings(self) -> RenderSettings:
        """Cài đặt hiện tại thu nhỏ còn cạnh dài ~720 px để dựng preview nhanh."""
        s = self.collect_settings()
        scale = 360 / max(s.output.width, s.output.height) * 2
        s.output.width = int(s.output.width * scale) // 2 * 2
        s.output.height = int(s.output.height * scale) // 2 * 2
        s.output.preset = "ultrafast"
        for st in (s.title, s.subtitle):
            st.font_size = max(8, int(st.font_size * scale))
            st.margin_v = int(st.margin_v * scale)
            st.outline = max(1, int(st.outline * scale))
        return s

    def _play_preview(self, paths):
        self.status.setText(f"Preview: {paths[0]}")
        if self.player is not None:
            self.player.setSource(QUrl.fromLocalFile(str(paths[0])))
            self.player.play()

    def _preview(self):
        clips, s = self.clips(), self._preview_settings()
        out = self.preview_dir / f"preview_{os.getpid()}_{id(s)}.mp4"

        def job(progress, cancel):
            return [render_one(clips, s, out, seed=1, progress=progress, cancel=cancel)]

        self._start(job, self._play_preview)

    def _preview_scenes(self):
        s = self._preview_settings()
        out = self.preview_dir / f"scenes_{os.getpid()}_{id(s)}.mp4"

        def job(progress, cancel):
            return [render_scenes(s, out, progress=progress, cancel=cancel)]

        self._start(job, self._play_preview, need_clips=False)

    def _export_scenes(self):
        s = self.collect_settings()
        out_dir = Path(self.out_dir.text())
        base = self.base_name.text().strip() or "video"
        out, i = out_dir / f"{base}_hoathinh.mp4", 2
        while out.exists():  # không ghi đè video đã xuất
            out, i = out_dir / f"{base}_hoathinh_{i}.mp4", i + 1

        def job(progress, cancel):
            return [render_scenes(s, out, progress=progress, cancel=cancel)]

        self._start(job, lambda paths: self.status.setText(f"Đã xuất {paths[0]}"), need_clips=False)

    def closeEvent(self, event):
        self.cancel.set()
        # Chờ luồng dựng dừng hẳn (ffmpeg bị kill) để tránh lỗi "QThread destroyed while running".
        try:
            if self.thread is not None and self.thread.isRunning():
                # quit() gọi thẳng: tín hiệu finished->quit xếp hàng ở luồng chính đang bị chặn.
                self.thread.quit()
                self.thread.wait(5000)
        except RuntimeError:  # QThread đã bị deleteLater
            pass
        super().closeEvent(event)


def main():
    import sys

    app = QApplication(sys.argv)
    app.setStyleSheet(STYLE)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())
