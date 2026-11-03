"""Nhân vật người phong cách Notionists: nửa người, nét vẽ tay.

Thiết kế: Zoish (https://heyzoish.gumroad.com/l/notionists), giấy phép CC0 1.0. Các mảnh SVG
được xuất từ gói @dicebear/notionists (mã nguồn MIT) bằng tools/export_notionists.mjs vào
assets/notionists.json. App tô màu da, tóc, áo rồi ráp bằng QtSvg nên không cần mạng hay Node."""

from __future__ import annotations

import json
import re
import sys
from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QRegion
from PySide6.QtSvg import QSvgRenderer

ASSET = Path(__file__).resolve().parent / "assets" / "notionists.json"
SIZE = 900  # cạnh ảnh PNG xuất ra (khung vuông, thân chạm đáy)

# Khẩu hình Rhubarb -> kiểu môi gần nhất trong bộ Notionists
LIPS = {"X": "variant04", "A": "variant13", "B": "variant27", "C": "variant25", "D": "variant11",
        "E": "variant15", "F": "variant29", "G": "variant05", "H": "variant14"}
# Bộ phận chọn được; bộ phận có "không" đứng đầu danh sách là không bắt buộc
PARTS = {"hair": "Kiểu tóc", "body": "Áo", "gesture": "Tay", "eyes": "Mắt", "brows": "Lông mày",
         "nose": "Mũi", "glasses": "Kính", "beard": "Râu"}
OPTIONAL = {"gesture", "glasses", "beard", "bodyIcon"}
SKIN = ["#F9D9C0", "#F1C27D", "#E0AC69", "#C68642", "#8D5524"]
HAIR = ["#1C1C1C", "#3B2A20", "#6D4C41", "#A0522D", "#E6C27A", "#B03A2E"]
SHIRT = ["#FFFFFF", "#90CAF9", "#A5D6A7", "#FFCC80", "#F48FB1", "#CE93D8", "#FFF59D"]


@lru_cache(maxsize=1)
def data() -> dict:
    return json.loads(ASSET.read_text(encoding="utf-8"))


def variants(group: str) -> list[str]:
    """Tên các kiểu của một bộ phận, sắp theo số (variant01, variant02...)."""
    names = sorted(data()["components"][group])
    return ([""] if group in OPTIONAL else []) + names


def default_parts() -> dict[str, str]:
    return {"hair": "variant12", "body": "variant03", "gesture": "", "eyes": "variant01",
            "brows": "variant01", "nose": "variant01", "glasses": "", "beard": "", "bodyIcon": ""}


def random_parts(rng) -> dict[str, str]:
    prob = data()["probability"]
    parts = {g: rng.choice(variants(g)[1:] if g in OPTIONAL else variants(g)) for g in PARTS}
    for g in ("gesture", "glasses", "beard"):
        if rng.random() * 100 >= prob.get(f"{g}Probability", 0):
            parts[g] = ""
    parts["bodyIcon"] = ""
    return parts


def _recolor(group: str, svg: str, skin: str, hair: str, shirt: str) -> str:
    """Bộ gốc trắng đen: tô da cho đầu và tay, màu áo cho thân, màu tóc cho tóc và râu."""
    if group in ("base", "gesture"):
        return svg.replace('fill="#fff"', f'fill="{skin}"')
    if group == "body":
        return svg.replace('fill="#fff"', f'fill="{shirt}"')
    if group in ("hair", "beard") and QColor(hair).lightness() > 40:
        # chỉ tô mảng tóc; giữ nét viền đen để tóc sáng màu vẫn rõ hình
        return svg.replace('fill="#000"', f'fill="{hair}" stroke="#000" stroke-width="6"')
    return svg


def _fragment(group: str, variant: str, parts: dict[str, str], colors: tuple[str, str, str]) -> str:
    if not variant:
        return ""
    svg = data()["components"][group].get(variant)
    if svg is None:  # kiểu không có trong bộ hình (vd. file nhanvat.json cũ): bỏ qua bộ phận này
        return ""
    svg = re.sub(r"\{\{(\w+)\}\}",
                 lambda m: _fragment(m.group(1), parts.get(m.group(1), ""), parts, colors), svg)
    return _recolor(group, svg, *colors)


def svg(parts: dict[str, str], colors: tuple[str, str, str], only: set[str] | None = None,
        skip: set[str] = frozenset(), extra: str = "") -> str:
    """Ráp SVG. `only`/`skip`: chọn lớp; `extra`: SVG thêm vào cuối (vd. mắt nhắm)."""
    d = data()
    body = []
    for layer in d["layers"]:
        g = layer["group"]
        if (only is not None and g not in only) or g in skip:
            continue
        variant = parts.get(g) or ("variant01" if g == "base" else "")  # đầu chỉ có một kiểu
        frag = _fragment(g, variant, parts, colors)
        if frag:
            body.append(f'<g transform="{layer["transform"]}">{frag}</g>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{d["viewBox"]}" fill="none">'
            + "".join(body) + extra + "</svg>")


def render(svg_text: str, size: int = SIZE) -> QImage:
    img = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    r = QSvgRenderer(QByteArray(svg_text.encode("utf-8")))
    if not r.isValid():
        raise ValueError("SVG nhân vật không hợp lệ")
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    r.render(p, QRectF(0, 0, size, size))
    p.end()
    return img


def _eye_boxes(parts: dict[str, str], colors) -> list[tuple[float, float, float, float]]:
    """Khung bao từng mắt (toạ độ viewBox), tìm từ ảnh chỉ có lớp mắt."""
    n = 436  # ảnh nhỏ (1/4) là đủ để dò
    img = render(svg(parts, colors, only={"eyes"}), n)
    scale = float(data()["viewBox"].split()[2]) / n
    cols = [x for x in range(n) if any(img.pixelColor(x, y).alpha() > 40 for y in range(n // 4, n * 3 // 4))]
    boxes, start = [], None
    for i, x in enumerate(cols):
        if start is None:
            start = x
        if i + 1 == len(cols) or cols[i + 1] > x + 3:  # hết một cụm cột liền nhau = một mắt
            ys = [y for y in range(n) for xx in range(start, x + 1) if img.pixelColor(xx, y).alpha() > 40]
            boxes.append((start * scale, min(ys) * scale, (x + 1) * scale, (max(ys) + 1) * scale))
            start = None
    return boxes


def _closed_eyes_svg(boxes) -> str:
    """Nét mi cong thay cho mắt mở, kèm kính vẽ lại phía trên."""
    lines = []
    for x0, y0, x1, y1 in boxes:
        cy, w = (y0 + y1) / 2, x1 - x0
        lines.append(f'<path d="M{x0:.0f} {cy:.0f} Q{x0 + w / 2:.0f} {cy + max(14, w * 0.35):.0f} {x1:.0f} {cy:.0f}" '
                     f'stroke="#000" stroke-width="14" stroke-linecap="round" fill="none"/>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{data()["viewBox"]}" fill="none">'
            + "".join(lines) + "</svg>")


def _skin_fill(parts: dict[str, str], colors, boxes) -> QImage:
    """Mặt trong bộ gốc chỉ có nét viền (trong suốt bên trong): loang màu da từ giữa hai mắt
    ra tới nét viền của đầu, tóc và áo (tóc khép kín phía trên đầu)."""
    n = SIZE
    head = render(svg(parts, colors, only={"base", "hair", "body", "beard"}), n).convertToFormat(QImage.Format.Format_ARGB32)
    alpha = bytes(head.constBits())[3::4] if sys.byteorder == "little" else bytes(head.constBits())[0::4]
    scale = n / float(data()["viewBox"].split()[2])
    sx = int(sum((b[0] + b[2]) / 2 for b in boxes) / len(boxes) * scale) if boxes else n // 2
    sy = int(max(b[3] for b in boxes) * scale) if boxes else n // 2
    filled = bytearray(n * n)
    stack = [sy * n + sx]
    while stack:
        i = stack.pop()
        if filled[i] or alpha[i] > 100:
            continue
        filled[i] = 1
        x, y = i % n, i // n
        if x == 0 or y == 0 or x == n - 1 or y == n - 1:
            return QImage()  # tràn ra ngoài: hình đầu không kín, bỏ qua
        stack += (i - 1, i + 1, i - n, i + n)
    out = QImage(n, n, QImage.Format.Format_ARGB32)
    out.fill(Qt.GlobalColor.transparent)
    c = QColor(colors[0])
    p = QPainter(out)
    p.setPen(c)
    for y in range(n):
        row, x = y * n, 0
        while x < n:
            if filled[row + x]:
                x0 = x
                while x < n and filled[row + x]:
                    x += 1
                p.drawLine(x0 - 1, y, x, y)  # lấn 1 px vào nét viền cho kín mép
            x += 1
    p.end()
    return out


def _stack(*images: QImage, clip: list[tuple[float, float, float, float]] | None = None,
           clipped: int = 0) -> QImage:
    """Chồng ảnh theo thứ tự; `clipped` ảnh đầu tiên chỉ vẽ trong vùng `clip` (khung mắt)."""
    img = QImage(SIZE, SIZE, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    if clip is not None:
        k = SIZE / float(data()["viewBox"].split()[2])
        region = QRegion()
        for x0, y0, x1, y1 in clip:
            region += QRegion(int((x0 - 10) * k), int((y0 - 10) * k), int((x1 - x0 + 20) * k) + 1,
                              int((y1 - y0 + 20) * k) + 1)
        p.setClipRegion(region)
    for i, layer in enumerate(images):
        if i == clipped:
            p.setClipping(False)
        if not layer.isNull():
            p.drawImage(0, 0, layer)
    p.end()
    return img


def layers(parts: dict[str, str], colors: tuple[str, str, str]) -> dict[str, QImage]:
    """Đủ bộ PNG cho lipsync.Character: body, blink, mouth_X..H."""
    boxes = _eye_boxes(parts, colors)
    skin = _skin_fill(parts, colors, boxes)
    out = {"body": _stack(skin, render(svg(parts, colors, skip={"lips"}))),
           # mắt nhắm: trong khung mắt vẽ lại da + mọi thứ trừ mắt, rồi nét mi và kính
           "blink": _stack(skin, render(svg(parts, colors, skip={"eyes", "lips", "glasses"})),
                           render(_closed_eyes_svg(boxes)), render(svg(parts, colors, only={"glasses"})),
                           clip=boxes, clipped=2)}
    for shape, lips in LIPS.items():
        out[f"mouth_{shape}"] = render(svg({**parts, "lips": lips}, colors, only={"lips"}))
    return out
