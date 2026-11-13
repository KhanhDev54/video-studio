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
from .. import notionists as nt
from ..voice import VIETNAMESE_VOICES

TALK = "XBCDCBXECBDCX"  # chuỗi khẩu hình để xem trước nhân vật đang nói
HUMAN_NAMES = ["Lan", "Minh", "Hoa", "Nam", "Mai", "Tuấn", "Linh", "Bảo", "An", "Vy"]


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

        # Bộ phận cho kiểu "nét vẽ tay": số thứ tự kiểu, 0 = không có (với bộ phận không bắt buộc)
        self.parts: dict[str, QSpinBox] = {}
        for group in nt.PARTS:
            box = QSpinBox()
            names = nt.variants(group)
            optional = names[0] == ""
            box.setRange(0 if optional else 1, len(names) - (1 if optional else 0))
            if optional:
                box.setSpecialValueText("Không")
            self.parts[group] = box

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
        for group, label in nt.PARTS.items():
            form.addRow(label, self.parts[group])
        self.form = form
        form.addRow("Giọng đọc", self.voice)
        form.addRow("Cao độ giọng", self.pitch)
        form.addRow("Lưu vào thư mục dàn nhân vật", dir_row)

        rand = QPushButton("Ngẫu nhiên")
        rand.clicked.connect(self.randomize)
        save = QPushButton("Lưu nhân vật")
        save.setObjectName("export")
        save.clicked.connect(lambda: self.save())  # clicked gửi kèm checked=False, không để rơi vào overwrite
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

        # Vẽ lại sau khi ngừng chỉnh một chút: kiểu nét vẽ tay mất khoảng 1 giây để dựng.
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(250)
        self._debounce.timeout.connect(self._redraw)
        # lambda: nếu nối thẳng, giá trị của tín hiệu bị hiểu là số mili giây của start(msec)
        restart = lambda *_: self._debounce.start()  # noqa: E731
        for combo in (self.kind, self.eyes, self.accessory):
            combo.currentIndexChanged.connect(restart)
        for b in (self.color, self.accent, self.hair):
            b.clicked.connect(restart)
        for box in self.parts.values():
            box.valueChanged.connect(restart)
        self.kind.currentIndexChanged.connect(self._update_fields)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(120)
        self.set_spec(cm.CharacterSpec("Lan", cm.HAND_DRAWN, nt.SKIN[0], "#90CAF9", "#3B2A20",
                                       parts=nt.default_parts()))

    # ----- thông số <-> giao diện -----
    def _update_fields(self) -> None:
        hand = self.kind.currentData() == cm.HAND_DRAWN
        for w in (self.eyes, self.accessory):
            self.form.setRowVisible(w, not hand)
        for w in self.parts.values():
            self.form.setRowVisible(w, hand)

    def _parts(self) -> dict[str, str]:
        out = {}
        for group, box in self.parts.items():
            names = [n for n in nt.variants(group) if n]
            out[group] = names[box.value() - 1] if box.value() > 0 else ""
        return out

    def spec(self) -> cm.CharacterSpec:
        return cm.CharacterSpec(
            name=self.name.text().strip(), kind=self.kind.currentData(), color=self.color.color,
            accent=self.accent.color, hair=self.hair.color, eyes=self.eyes.currentData(),
            accessory=self.accessory.currentData(), voice=self.voice.currentData(),
            pitch=f"{self.pitch.value():+d}Hz",
            parts=self._parts() if self.kind.currentData() == cm.HAND_DRAWN else {})

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
        parts = {**nt.default_parts(), **s.parts}
        for group, box in self.parts.items():
            box.blockSignals(True)
            names = [n for n in nt.variants(group) if n]
            box.setValue(names.index(parts[group]) + 1 if parts.get(group) in names else 0)
            box.blockSignals(False)
        self._update_fields()
        try:
            self.pitch.setValue(int(s.pitch.removesuffix("Hz")))
        except ValueError:
            self.pitch.setValue(0)
        self._redraw()

    def randomize(self) -> None:
        s = cm.random_spec(random.randrange(1 << 30))
        current = self.name.text().strip()
        if current in ("", *cm.KINDS.values(), *HUMAN_NAMES):  # tên mặc định: đặt tên mới hợp loài
            s.name = random.choice(HUMAN_NAMES) if s.kind in (cm.HAND_DRAWN, "nguoi") else cm.KINDS[s.kind]
        else:
            s.name = current
        self.set_spec(s)

    # ----- xem trước -----
    def _redraw(self) -> None:
        self._debounce.stop()
        self._layers = cm.layers(self.spec())
        self._tick()

    def _tick(self) -> None:
        self._frame += 1
        img = cm.compose(self._layers, TALK[self._frame % len(TALK)], self._frame % 30 in (0, 1))
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
