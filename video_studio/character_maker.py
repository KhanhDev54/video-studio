"""Tạo nhân vật hoạt hình 2D ngay trong app, không cần tự vẽ.

Chọn loài, màu, kiểu mắt, phụ kiện -> vẽ ra bộ PNG đúng định dạng của lipsync.Character:
body.png, mouth_X.png ... mouth_H.png (đủ 9 khẩu hình Rhubarb) và blink.png, kèm nhanvat.json
chứa giọng đọc. Vẽ bằng QPainter của PySide6 nên không cần thêm thư viện nào."""

from __future__ import annotations

import json
import random
from dataclasses import asdict, dataclass
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen, QPolygonF

from .lipsync import SHAPES
from .settings import _WINDOWS_RESERVED

W, H = 600, 900  # khung hình nhân vật (dọc), mọi lớp PNG cùng kích thước

KINDS = {"meo": "Mèo", "cho": "Chó", "tho": "Thỏ", "gau": "Gấu", "nguoi": "Người", "quai_vat": "Quái vật"}
EYES = {"tron": "Tròn", "long_lanh": "To long lanh", "cham": "Chấm nhỏ"}
ACCESSORIES = {"none": "Không", "no": "Nơ", "kinh": "Kính", "mu": "Mũ", "khan": "Khăn quàng"}

# Bảng màu gợi ý cho nút "Ngẫu nhiên"
FUR = ["#F4A340", "#8D6E63", "#BDBDBD", "#FFFFFF", "#5D4037", "#F6D7A7", "#424242", "#E0A96D"]
SKIN = ["#FFDBB4", "#F1C27D", "#E0AC69", "#C68642", "#8D5524"]
BRIGHT = ["#7E57C2", "#26A69A", "#EF5350", "#42A5F5", "#9CCC65", "#FFCA28", "#EC407A"]
HAIR = ["#3B2A20", "#1C1C1C", "#A0522D", "#E6C27A", "#B03A2E"]

EYE_L, EYE_R, EYE_Y = 225, 375, 285
MOUTH = QPointF(300, 400)
MOUTH_DARK, TONGUE, LINE = QColor("#5A1F25"), QColor("#E86A7A"), QColor("#3A1A1A")


@dataclass
class CharacterSpec:
    name: str = "Nhân vật"
    kind: str = "meo"
    color: str = "#F4A340"   # lông (con vật) hoặc da (người)
    accent: str = "#FFFFFF"  # bụng/mõm (con vật) hoặc áo (người)
    hair: str = "#3B2A20"    # chỉ dùng cho người
    eyes: str = "tron"
    accessory: str = "none"
    voice: str = "vi-VN-HoaiMyNeural"
    rate: str = "+0%"
    pitch: str = "+0Hz"


def random_spec(seed: int | None = None, name: str = "Nhân vật") -> CharacterSpec:
    rng = random.Random(seed)
    kind = rng.choice(list(KINDS))
    color = rng.choice(SKIN if kind == "nguoi" else BRIGHT if kind == "quai_vat" else FUR)
    accent = rng.choice(BRIGHT if kind == "nguoi" else ["#FFFFFF", "#FFF3E0", "#FCE4EC", "#F5F5F5"])
    return CharacterSpec(
        name=name, kind=kind, color=color, accent=accent, hair=rng.choice(HAIR),
        eyes=rng.choice(list(EYES)), accessory=rng.choice(list(ACCESSORIES)),
        voice=rng.choice(["vi-VN-HoaiMyNeural", "vi-VN-NamMinhNeural"]),
        pitch=f"{rng.choice([-20, -10, 0, 10, 20, 30]):+d}Hz")


# ---------- vẽ ----------

def _canvas() -> tuple[QImage, QPainter]:
    img = QImage(W, H, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    return img, p


def _style(p: QPainter, fill: QColor | str | None, outline: QColor | str | None = "auto", width: float = 7):
    """outline="auto": viền đậm hơn màu tô; None: không viền."""
    if outline == "auto":
        outline = QColor(fill).darker(170) if fill is not None else None
    if outline is None:
        p.setPen(Qt.PenStyle.NoPen)
    else:
        pen = QPen(QColor(outline), width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
    p.setBrush(QColor(fill) if fill is not None else Qt.BrushStyle.NoBrush)


def _ellipse(p, x, y, w, h, fill, outline="auto", width=7):
    _style(p, fill, outline, width)
    p.drawEllipse(QRectF(x, y, w, h))


def _poly(p, pts, fill, outline="auto", width=7):
    _style(p, fill, outline, width)
    p.drawPolygon(QPolygonF([QPointF(x, y) for x, y in pts]))


def _face_color(s: CharacterSpec) -> QColor:
    return QColor(s.color)


def _draw_ears_back(p: QPainter, s: CharacterSpec):
    c, inner = QColor(s.color), QColor("#F8BBD0")
    if s.kind == "meo":
        for sx in (1, -1):
            x = lambda v: 300 + sx * (v - 300)  # noqa: E731
            _poly(p, [(x(125), 230), (x(150), 55), (x(270), 150)], c)
            _poly(p, [(x(150), 200), (x(165), 95), (x(240), 155)], inner, outline=None)
    elif s.kind == "tho":
        for x0 in (180, 350):
            _ellipse(p, x0, 5, 70, 240, c)
            _ellipse(p, x0 + 18, 35, 34, 170, inner, outline=None)
    elif s.kind == "gau":
        for x0 in (105, 385):
            _ellipse(p, x0, 105, 110, 110, c)
            _ellipse(p, x0 + 25, 130, 60, 60, QColor(s.color).darker(125), outline=None)
    elif s.kind == "quai_vat":
        horn = QColor(s.accent)
        _poly(p, [(175, 165), (140, 30), (235, 135)], horn)
        _poly(p, [(425, 165), (460, 30), (365, 135)], horn)
    elif s.kind == "nguoi":
        for x0 in (85, 465):
            _ellipse(p, x0, 270, 50, 75, c)


def _draw_body(p: QPainter, s: CharacterSpec):
    c, a = QColor(s.color), QColor(s.accent)
    human = s.kind == "nguoi"
    limb = a if human else c
    # chân, thân, tay
    for x0 in (205, 315):
        _ellipse(p, x0, 735, 80, 150, QColor("#33415C") if human else c)
    _style(p, a if human else c)
    p.drawRoundedRect(QRectF(165, 445, 270, 335), 110, 110)
    if not human:
        _ellipse(p, 220, 515, 160, 225, a, outline=None)
    for x0 in (110, 410):
        _ellipse(p, x0, 480, 80, 230, limb)
    if human:  # bàn tay
        for x0 in (118, 418):
            _ellipse(p, x0, 670, 64, 64, c)


def _draw_head(p: QPainter, s: CharacterSpec):
    c = QColor(s.color)
    _ellipse(p, 100, 120, 400, 360, c)
    if s.kind == "cho":  # tai cụp phủ hai bên đầu
        ear = QColor(s.color).darker(135)
        _ellipse(p, 60, 160, 115, 240, ear)
        _ellipse(p, 425, 160, 115, 240, ear)
    if s.kind in ("meo", "cho", "gau", "tho"):  # mõm sáng màu quanh miệng
        _ellipse(p, 215, 335, 170, 115, QColor(s.accent), outline=None)
    if s.kind == "nguoi":  # tóc
        path = QPainterPath()
        path.moveTo(95, 280)
        path.arcTo(QRectF(95, 95, 410, 360), 180, -180)
        path.cubicTo(470, 200, 380, 175, 300, 190)
        path.cubicTo(220, 175, 130, 200, 95, 280)
        _style(p, QColor(s.hair))
        p.drawPath(path)
    # mũi
    if s.kind in ("cho", "gau"):
        _ellipse(p, 272, 330, 56, 38, "#2B2B2B", outline=None)
    elif s.kind in ("meo", "tho"):
        _poly(p, [(282, 340), (318, 340), (300, 360)], "#F48FB1", outline="#C2185B", width=4)
    elif s.kind == "nguoi":
        _style(p, None, QColor(s.color).darker(150), 5)
        p.drawArc(QRectF(288, 330, 24, 24), 200 * 16, 140 * 16)
    # má hồng
    for x0 in (150, 390):
        _ellipse(p, x0, 330, 60, 34, QColor(255, 105, 140, 90), outline=None)


def _draw_eyes(p: QPainter, s: CharacterSpec):
    for cx in (EYE_L, EYE_R):
        if s.eyes == "cham":
            _ellipse(p, cx - 16, EYE_Y - 22, 32, 44, "#1E1E1E", outline=None)
            _ellipse(p, cx - 6, EYE_Y - 14, 10, 10, "#FFFFFF", outline=None)
        elif s.eyes == "long_lanh":
            _ellipse(p, cx - 42, EYE_Y - 48, 84, 96, "#FFFFFF", "#2B2B2B", 5)
            _ellipse(p, cx - 28, EYE_Y - 26, 56, 64, "#3E2723", outline=None)
            _ellipse(p, cx - 16, EYE_Y - 18, 18, 18, "#FFFFFF", outline=None)
            _ellipse(p, cx + 6, EYE_Y + 14, 9, 9, "#FFFFFF", outline=None)
        else:
            _ellipse(p, cx - 35, EYE_Y - 40, 70, 80, "#FFFFFF", "#2B2B2B", 5)
            _ellipse(p, cx - 18, EYE_Y - 14, 36, 40, "#1E1E1E", outline=None)
            _ellipse(p, cx - 9, EYE_Y - 8, 12, 12, "#FFFFFF", outline=None)


def _eye_box(s: CharacterSpec) -> tuple[float, float]:
    return {"cham": (20, 26), "long_lanh": (46, 52)}.get(s.eyes, (39, 44))


def _draw_glasses(p: QPainter):
    for cx in (EYE_L, EYE_R):
        _ellipse(p, cx - 56, EYE_Y - 56, 112, 112, QColor(200, 230, 255, 60), "#222222", 8)
    _style(p, None, "#222222", 8)
    p.drawLine(QPointF(EYE_L + 56, EYE_Y - 8), QPointF(EYE_R - 56, EYE_Y - 8))


def _draw_accessory(p: QPainter, s: CharacterSpec):
    if s.accessory == "no":
        red = QColor("#E84A5F")
        _poly(p, [(395, 140), (340, 105), (340, 175)], red)
        _poly(p, [(395, 140), (450, 105), (450, 175)], red)
        _ellipse(p, 378, 123, 34, 34, red)
    elif s.accessory == "kinh":
        _draw_glasses(p)
    elif s.accessory == "mu":
        hat = QColor("#2E3A59")
        _style(p, hat)
        p.drawRoundedRect(QRectF(200, 30, 200, 120), 30, 30)
        p.drawRoundedRect(QRectF(140, 130, 320, 34), 17, 17)
        _style(p, QColor("#E84A5F"), outline=None)
        p.drawRect(QRectF(204, 108, 192, 20))
    elif s.accessory == "khan":
        scarf = QColor("#E84A5F")
        _style(p, scarf)
        p.drawRoundedRect(QRectF(185, 440, 230, 52), 26, 26)
        p.drawRoundedRect(QRectF(330, 470, 50, 120), 20, 20)


def draw_body(s: CharacterSpec) -> QImage:
    img, p = _canvas()
    _draw_ears_back(p, s)
    _draw_body(p, s)
    _draw_head(p, s)
    _draw_eyes(p, s)
    _draw_accessory(p, s)
    p.end()
    return img


def draw_blink(s: CharacterSpec) -> QImage:
    """Mắt nhắm: phủ màu mặt lên mắt rồi vẽ đường cong; vẽ lại kính nếu có."""
    img, p = _canvas()
    rx, ry = _eye_box(s)
    for cx in (EYE_L, EYE_R):
        _ellipse(p, cx - rx, EYE_Y - ry, rx * 2, ry * 2, _face_color(s), outline=None)
        _style(p, None, "#2B2B2B", 7)
        p.drawArc(QRectF(cx - rx * 0.8, EYE_Y - 20, rx * 1.6, 34), 200 * 16, 140 * 16)
    if s.accessory == "kinh":
        _draw_glasses(p)
    p.end()
    return img


def draw_mouth(shape: str) -> QImage:
    """Khẩu hình theo chuẩn Rhubarb: X nghỉ, A mím, B hé răng, C mở vừa, D mở to, E tròn,
    F chu môi, G răng chạm môi, H lưỡi."""
    if shape not in SHAPES:  # kiểm tra trước khi mở QPainter: QPainter bỏ dở sẽ làm sập Qt
        raise ValueError(f"Khẩu hình không hợp lệ: {shape}")
    img, p = _canvas()
    x, y = MOUTH.x(), MOUTH.y()
    teeth = QColor("#FFFFFF")
    if shape == "X":
        _style(p, None, LINE, 7)
        path = QPainterPath(QPointF(x - 35, y - 5))
        path.quadTo(QPointF(x, y + 20), QPointF(x + 35, y - 5))
        p.drawPath(path)
    elif shape == "A":
        _style(p, None, LINE, 9)
        p.drawLine(QPointF(x - 26, y + 2), QPointF(x + 26, y + 2))
    elif shape in ("B", "G"):
        _style(p, MOUTH_DARK, LINE, 5)
        p.drawRoundedRect(QRectF(x - 30, y - 12, 60, 26), 12, 12)
        _style(p, teeth, outline=None)
        p.drawRoundedRect(QRectF(x - 25, y - 9, 50, 10 if shape == "B" else 13), 4, 4)
        if shape == "G":  # môi dưới chạm răng trên
            _style(p, None, TONGUE.darker(130), 7)
            p.drawLine(QPointF(x - 24, y + 8), QPointF(x + 24, y + 8))
    elif shape in ("C", "D", "H"):
        w, h = (64, 46) if shape == "C" else (84, 72) if shape == "D" else (64, 52)
        _ellipse(p, x - w / 2, y - h / 2, w, h, MOUTH_DARK, LINE, 5)
        if shape == "H":  # lưỡi chạm lợi trên
            _ellipse(p, x - 17, y - h / 2 + 5, 34, 18, TONGUE, outline=None)
        else:
            _ellipse(p, x - w * 0.3, y + h * 0.08, w * 0.6, h * 0.38, TONGUE, outline=None)
        if shape == "D":
            _style(p, teeth, outline=None)
            p.drawChord(QRectF(x - w / 2 + 6, y - h / 2 + 4, w - 12, h * 0.5), 30 * 16, 120 * 16)
    elif shape == "E":
        _ellipse(p, x - 24, y - 25, 48, 50, MOUTH_DARK, LINE, 5)
        _ellipse(p, x - 13, y + 3, 26, 15, TONGUE, outline=None)
    else:  # F
        _ellipse(p, x - 15, y - 13, 30, 26, MOUTH_DARK, TONGUE.darker(130), 8)
    p.end()
    return img


def preview(s: CharacterSpec, mouth: str = "X", blink: bool = False) -> QImage:
    """Ảnh ghép body + miệng (+ mắt nhắm) để xem trước."""
    img = draw_body(s)
    p = QPainter(img)
    p.drawImage(0, 0, draw_mouth(mouth))
    if blink:
        p.drawImage(0, 0, draw_blink(s))
    p.end()
    return img


# ---------- lưu ----------

def safe_folder_name(name: str) -> str:
    safe = "".join(c for c in name if c.isalnum() or c in " -_").strip()
    if not safe:
        raise ValueError("Tên nhân vật không hợp lệ")
    if safe.upper() in _WINDOWS_RESERVED:
        safe += "_"
    return safe


def make_character(s: CharacterSpec, cast_dir: str | Path, overwrite: bool = False) -> Path:
    """Ghi nhân vật vào `cast_dir/<tên>/`. Tên thư mục là tên dùng trong kịch bản ("Tên: lời")."""
    if s.kind not in KINDS:
        raise ValueError(f"Loài không hợp lệ: {s.kind}")
    folder = Path(cast_dir) / safe_folder_name(s.name)
    if (folder / "body.png").exists() and not overwrite:
        raise FileExistsError(f"Đã có nhân vật {folder.name} trong {cast_dir}")
    folder.mkdir(parents=True, exist_ok=True)
    layers = {"body": draw_body(s), "blink": draw_blink(s), **{f"mouth_{m}": draw_mouth(m) for m in SHAPES}}
    for name, img in layers.items():
        if not img.save(str(folder / f"{name}.png")):
            raise OSError(f"Không ghi được {folder / name}.png")
    cfg = {"voice": s.voice, "rate": s.rate, "pitch": s.pitch, "tao_boi_app": asdict(s)}
    (folder / "nhanvat.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    return folder


def load_spec(folder: str | Path) -> CharacterSpec | None:
    """Đọc lại thông số nhân vật đã tạo bằng app (để sửa tiếp); None nếu nhân vật tự vẽ."""
    path = Path(folder) / "nhanvat.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig")).get("tao_boi_app")
    except (OSError, ValueError, AttributeError):
        return None
    if not isinstance(data, dict):
        return None
    known = CharacterSpec.__dataclass_fields__
    return CharacterSpec(**{k: v for k, v in data.items() if k in known})
