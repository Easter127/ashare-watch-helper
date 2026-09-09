# -*- coding: utf-8 -*-
"""
生成应用图标 ICO 文件 — 直接用 PyQt5 画
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import Qt, QPoint
from PyQt5.QtGui import QColor, QIcon, QPixmap, QPainter, QPen, QPainterPath
from PyQt5.QtWidgets import QApplication


def make_pixmap(size: int) -> QPixmap:
    """画一个跟任务栏图标风格一致的图标（上涨趋势 + 红色终点）"""
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)

    # 圆角深色背景
    p.setBrush(QColor(20, 20, 24))
    p.setPen(QPen(QColor(80, 80, 90), max(1, size // 32)))
    p.drawEllipse(size // 16, size // 16, size - size // 8, size - size // 8)

    # 上涨折线
    s = size / 64.0
    pen = QPen(QColor("#ff5252"), max(2, int(4 * s)))
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)

    pts = [
        QPoint(int(14 * s), int(48 * s)),
        QPoint(int(26 * s), int(36 * s)),
        QPoint(int(36 * s), int(40 * s)),
        QPoint(int(50 * s), int(16 * s)),
    ]
    path = QPainterPath()
    path.moveTo(pts[0])
    for pt in pts[1:]:
        path.lineTo(pt)
    p.drawPath(path)

    # 终点红点
    p.setBrush(QColor("#ff5252"))
    p.setPen(QPen(QColor("#ffffff"), max(1, int(s))))
    r = max(4, int(5 * s))
    p.drawEllipse(pts[-1].x() - r, pts[-1].y() - r, r * 2, r * 2)
    p.end()
    return pix


def write_ico(path: str, sizes=(16, 24, 32, 48, 64, 128, 256)):
    """把多尺寸 PNG 写进一个 ICO 文件"""
    app = QApplication.instance() or QApplication(sys.argv)

    # 收集各尺寸 pixmap
    pixmaps = [make_pixmap(s) for s in sizes]

    # 写 ICO：先收集 PNG 字节流
    from PyQt5.QtCore import QBuffer, QIODevice
    import io as _io
    png_bytes = []
    for s, p in zip(sizes, pixmaps):
        buf = QBuffer()
        buf.open(QIODevice.WriteOnly)
        p.save(buf, "PNG")
        png_bytes.append(bytes(buf.data()))
        buf.close()

    # 写 ICO 头 + 目录
    with open(path, "wb") as f:
        # ICONDIR (6 bytes)
        f.write((0).to_bytes(2, "little"))  # reserved
        f.write((1).to_bytes(2, "little"))  # type: 1=icon
        f.write((len(sizes)).to_bytes(2, "little"))  # count

        # ICONDIRENTRY (16 bytes each)
        offset = 6 + 16 * len(sizes)
        for size, png in zip(sizes, png_bytes):
            w = size if size < 256 else 0
            h = size if size < 256 else 0
            f.write(w.to_bytes(1, "little"))  # width
            f.write(h.to_bytes(1, "little"))  # height
            f.write((0).to_bytes(1, "little"))  # color count
            f.write((0).to_bytes(1, "little"))  # reserved
            f.write((1).to_bytes(2, "little"))  # planes
            f.write((32).to_bytes(2, "little"))  # bpp
            f.write((len(png)).to_bytes(4, "little"))  # size
            f.write((offset).to_bytes(4, "little"))  # offset
            offset += len(png)

        # PNG data
        for png in png_bytes:
            f.write(png)

    print(f"[OK] {path} ({os.path.getsize(path) / 1024:.1f} KB)")


if __name__ == "__main__":
    out = os.path.join(HERE, "assets", "tray_icon.ico")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    write_ico(out)
