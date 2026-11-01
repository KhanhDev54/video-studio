"""Cửa sổ "Tạo nhân vật": chọn loài, màu, mắt, phụ kiện, giọng; xem trước nhân vật đang nói."""

from __future__ import annotations

import random
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QComboBox, QDialog, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPushButton, QSpinBox, QVBoxLayout,
)

from .. import character_maker as cm
from ..voice import VIETNAMESE_VOICES

TALK = "XBCDCBXECBDCX"  # chuỗi khẩu hình để xem trước nhân vật đang nói


class CharacterDialog(QDialog):
    def __init__(self, cast_dir: str = "", parent=None):
        from .main_window import ColorButton  # tránh import vòng

        super().__init__(parent)
        self.setWindowTitle("Tạo nhân vật")
        self.saved: Path | None = None
        self._frame = 0

        self.name = QLineEdit("Mèo")
        self.kind = QComboBox()
        for key, label in cm.KINDS.items():
            self.kind.addItem(label, key)
        self.color = ColorButton("#F4A340")
        self.accent = ColorButton("#FFFFFF")
        self.hair = ColorButton("#3B2A20")
        self.eyes = QComboBox()
        for key, label in cm.EYES.items():
            self.eyes.addItem(label, key)
        self.accessory = QComboBox()
        for key, label in cm.ACCESSORIES.items():
            self.accessory.addItem(label, key)
        self.voice = QComboBox()
        for key, label in VIETNAMESE_VOICES.items():
            self.voice.addItem(label, key)
        self.pitch = QSpinBox()
        self.pitch.setRange(-50, 50)
        self.pitch.setSuffix(" Hz")
        self.cast_dir = QLineEdit(cast_dir or str(Path.home() / "VideoStudio" / "nhan_vat"))
        pick = QPushButton("…")
        pick.setFixedWidth(32)
        pick.clicked.connect(self._pick_dir)
        dir_row = QHBoxLayout()
        dir_row.addWidget(self.cast_dir)
        dir_row.addWidget(pick)

        self.preview = QLabel()
        self.preview.setFixedSize(240, 360)
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)

        form = QFormLayout()
        form.addRow("Tên (dùng trong kịch bản)", self.name)
        form.addRow("Loài", self.kind)
        form.addRow("Màu lông / da", self.color)
        form.addRow("Màu bụng / áo", self.accent)
        form.addRow("Màu tóc (người)", self.hair)
        form.addRow("Mắt", self.eyes)
        form.addRow("Phụ kiện", self.accessory)
        form.addRow("Giọng đọc", self.voice)
        form.addRow("Cao độ giọng", self.pitch)
        form.addRow("Lưu vào thư mục dàn nhân vật", dir_row)

        rand = QPushButton("Ngẫu nhiên")
        rand.clicked.connect(self.randomize)
        save = QPushButton("Lưu nhân vật")
        save.setObjectName("export")
        save.clicked.connect(self.save)
        btns = QHBoxLayout()
        btns.addWidget(rand)
        btns.addStretch()
        btns.addWidget(save)

        top = QHBoxLayout()
        top.addLayout(form)
        top.addWidget(self.preview)
        root = QVBoxLayout(self)
        root.addLayout(top)
        root.addWidget(QLabel("Nhân vật được vẽ sẵn đủ khẩu hình để nhép miệng. Thư mục tạo ra có thể "
                              "sửa tiếp bằng phần mềm vẽ bất kỳ."))
        root.addLayout(btns)

        for combo in (self.kind, self.eyes, self.accessory):
            combo.currentIndexChanged.connect(self._redraw)
        for b in (self.color, self.accent, self.hair):
            b.clicked.connect(self._redraw)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(120)
        self._redraw()

    # ----- thông số <-> giao diện -----
    def spec(self) -> cm.CharacterSpec:
        return cm.CharacterSpec(
            name=self.name.text().strip(), kind=self.kind.currentData(), color=self.color.color,
            accent=self.accent.color, hair=self.hair.color, eyes=self.eyes.currentData(),
            accessory=self.accessory.currentData(), voice=self.voice.currentData(),
            pitch=f"{self.pitch.value():+d}Hz")

    def set_spec(self, s: cm.CharacterSpec) -> None:
        self.name.setText(s.name)
        for combo, value in ((self.kind, s.kind), (self.eyes, s.eyes), (self.accessory, s.accessory),
                             (self.voice, s.voice)):
            i = combo.findData(value)
            if i >= 0:
                combo.setCurrentIndex(i)
        self.color.set_color(s.color)
        self.accent.set_color(s.accent)
        self.hair.set_color(s.hair)
        try:
            self.pitch.setValue(int(s.pitch.removesuffix("Hz")))
        except ValueError:
            self.pitch.setValue(0)
        self._redraw()

    def randomize(self) -> None:
        s = cm.random_spec(random.randrange(1 << 30))
        s.name = cm.KINDS[s.kind] if self.name.text().strip() in ("", *cm.KINDS.values()) else self.name.text()
        self.set_spec(s)

    # ----- xem trước -----
    def _redraw(self) -> None:
        self._spec = self.spec()
        self._body = cm.draw_body(self._spec)
        self._blink = cm.draw_blink(self._spec)
        self._mouths = {m: cm.draw_mouth(m) for m in set(TALK)}
        self._tick()

    def _tick(self) -> None:
        from PySide6.QtGui import QPainter

        self._frame += 1
        img = self._body.copy()
        p = QPainter(img)
        p.drawImage(0, 0, self._mouths[TALK[self._frame % len(TALK)]])
        if self._frame % 30 in (0, 1):
            p.drawImage(0, 0, self._blink)
        p.end()
        self.preview.setPixmap(QPixmap.fromImage(img).scaled(
            self.preview.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

    # ----- lưu -----
    def _pick_dir(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Chọn thư mục dàn nhân vật", self.cast_dir.text())
        if d:
            self.cast_dir.setText(d)

    def save(self, overwrite: bool | None = None) -> Path | None:
        """`overwrite`: None thì hỏi khi trùng tên (test truyền True/False để không hiện hộp thoại)."""
        s = self.spec()
        cast = self.cast_dir.text().strip()
        try:
            if not cast:
                raise ValueError("Chưa chọn thư mục dàn nhân vật")
            if (Path(cast) / "body.png").is_file():
                raise ValueError("Thư mục này là một nhân vật, hãy chọn thư mục cha chứa các nhân vật")
            try:
                self.saved = cm.make_character(s, cast, overwrite=bool(overwrite))
            except FileExistsError:
                if overwrite is None and QMessageBox.question(
                        self, "Trùng tên", f"Đã có nhân vật \"{s.name}\". Ghi đè?") == QMessageBox.StandardButton.Yes:
                    self.saved = cm.make_character(s, cast, overwrite=True)
                else:
                    return None
        except (OSError, ValueError) as e:
            if overwrite is None:
                QMessageBox.warning(self, "Không lưu được", str(e))
                return None
            raise
        self.accept()
        return self.saved
