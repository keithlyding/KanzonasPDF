"""KanzonasPDF icon and logo, drawn as vectors so they're crisp at every size.

The mark: a saguaro cactus wearing a sunflower, in front of a PDF page.
draw_icon() has a full version (48 px and up) and a simplified one for 16-32 px, where
spines, page lines and petal detail would turn to mush.
"""

import math

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import (QColor, QPainter, QPainterPath, QPen, QPixmap, QIcon, QImage, QFont,
                           QRadialGradient, QLinearGradient)

CACTUS = QColor("#14261a")
CACTUS_HI = QColor("#2c4a33")
PAGE_EDGE = QColor("#4a4a4a")
PETAL = QColor("#f6c21c")
PETAL_EDGE = QColor("#c98a00")
DISK = QColor("#6a3816")
GREEN = QColor("#4f8a2b")
INK = QColor("#161616")
GRAY = QColor("#5f6368")


def _cactus_path(simple):
    """Saguaro on a 256-unit grid: a trunk and two arms that bend up."""
    p = QPainterPath()
    p.setFillRule(Qt.WindingFill)
    p.addRoundedRect(QRectF(104, 30, 48, 220), 24, 24)                # trunk
    # left arm: out from the trunk, then up
    p.addRoundedRect(QRectF(44, 150, 76, 30), 15, 15)
    p.addRoundedRect(QRectF(44, 72, 32, 108), 16, 16)
    # right arm: higher and shorter
    p.addRoundedRect(QRectF(136, 120, 78, 30), 15, 15)
    p.addRoundedRect(QRectF(182, 58, 32, 92), 16, 16)
    return p.simplified()


def _page_path():
    p = QPainterPath()
    p.moveTo(66, 14)
    p.lineTo(186, 14)
    p.lineTo(226, 54)
    p.lineTo(226, 226)
    p.lineTo(66, 226)
    p.closeSubpath()
    return p


def draw_icon(p, size, simple=None):
    """Draw the app icon into a size x size square of painter p (transparent background)."""
    simple = size <= 32 if simple is None else simple
    p.save()
    p.setRenderHint(QPainter.Antialiasing)
    p.scale(size / 256.0, size / 256.0)

    # the page: a bolder outline when small so it still reads as a document
    p.setPen(QPen(PAGE_EDGE, 14 if simple else 7, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.setBrush(QColor("white"))
    p.drawPath(_page_path())
    fold = QPainterPath()
    fold.moveTo(186, 14)
    fold.lineTo(186, 54)
    fold.lineTo(226, 54)
    fold.closeSubpath()
    p.setBrush(QColor("#d9d9d9"))
    p.drawPath(fold)
    if not simple:
        p.setPen(QPen(QColor("#b9b9b9"), 6, Qt.SolidLine, Qt.RoundCap))
        for y in (78, 98, 118):
            p.drawLine(QPointF(168, y), QPointF(208, y))

    # cactus with a light rim so it stays visible on dark taskbars
    cactus = _cactus_path(simple)
    p.setPen(QPen(QColor("white"), 10 if simple else 6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.setBrush(Qt.NoBrush)
    p.drawPath(cactus)
    grad = QLinearGradient(40, 0, 220, 0)
    grad.setColorAt(0, CACTUS_HI)
    grad.setColorAt(0.45, CACTUS)
    grad.setColorAt(1, CACTUS)
    p.setPen(Qt.NoPen)
    p.setBrush(grad)
    p.drawPath(cactus)
    if not simple:
        # ribs and spines
        p.setPen(QPen(QColor(255, 255, 255, 38), 3, Qt.SolidLine, Qt.RoundCap))
        for x in (118, 128, 138):
            p.drawLine(QPointF(x, 50), QPointF(x, 236))
        for x in (60,):
            p.drawLine(QPointF(x, 88), QPointF(x, 166))
        p.drawLine(QPointF(198, 74), QPointF(198, 136))
        p.setPen(QPen(CACTUS, 2.5, Qt.SolidLine, Qt.RoundCap))
        spines = [(104, 222, -1), (152, 230, 1), (44, 96, -1), (44, 140, -1), (76, 92, 1),
                  (182, 80, -1), (214, 76, 1), (214, 118, 1), (152, 60, 1), (104, 54, -1)]
        for x, y, dx in spines:                     # little paired spines sticking out
            p.drawLine(QPointF(x, y), QPointF(x + 7 * dx, y - 3))
            p.drawLine(QPointF(x, y), QPointF(x + 7 * dx, y + 3))

    # sunflower
    cx, cy = 128.0, 118.0
    n = 12 if simple else 18
    length, width = (50, 26) if simple else (40, 16)
    p.setPen(QPen(PETAL_EDGE, 3 if simple else 2))
    p.setBrush(PETAL)
    for k in range(n):
        p.save()
        p.translate(cx, cy)
        p.rotate(360.0 * k / n + (0 if k % 2 else 360.0 / n / 2) * (0 if simple else 1))
        p.drawEllipse(QRectF(10, -width / 2, length, width))
        p.restore()
    disk = QRadialGradient(cx - 5, cy - 5, 26)
    disk.setColorAt(0, QColor("#8a4d22"))
    disk.setColorAt(1, DISK)
    p.setPen(QPen(QColor("#3e1f0a"), 2))
    p.setBrush(disk)
    r = 24 if simple else 19
    p.drawEllipse(QPointF(cx, cy), r, r)
    if not simple:
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 60))
        for k in range(14):
            a = k * 2.4
            d = 5 + 1.1 * k
            p.drawEllipse(QPointF(cx + d * math.cos(a), cy + d * math.sin(a)), 1.6, 1.6)
    p.restore()


def icon_pixmap(size):
    img = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    p = QPainter(img)
    draw_icon(p, size)
    p.end()
    return QPixmap.fromImage(img)


def app_icon():
    """QIcon with hand-tuned bitmaps for each common size."""
    ic = QIcon()
    for s in (16, 20, 24, 32, 40, 48, 64, 128, 256):
        ic.addPixmap(icon_pixmap(s))
    return ic


def draw_logo(p, rect, dark=False, tagline=True):
    """Horizontal logo (icon + KanzonasPDF + tagline) fitted into rect."""
    h = rect.height()
    icon = h
    p.save()
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.TextAntialiasing)
    p.translate(rect.x(), rect.y())
    draw_icon(p, int(icon), simple=False)
    x = icon * 1.08
    name = QFont("Segoe UI")
    name.setStyleHint(QFont.SansSerif)
    name.setBold(True)
    name.setPixelSize(int(h * 0.42))
    p.setFont(name)
    fm = p.fontMetrics()
    base = h * 0.58
    p.setPen(QColor("#f2f2f2") if dark else INK)
    p.drawText(QPointF(x, base), "Kanzonas")
    w1 = fm.horizontalAdvance("Kanzonas")
    p.setPen(GREEN if not dark else QColor("#7cc144"))
    p.drawText(QPointF(x + w1 + h * 0.02, base), "PDF")
    total = w1 + h * 0.02 + fm.horizontalAdvance("PDF")
    if tagline:
        p.setPen(QPen(GREEN, max(1.0, h * 0.012)))
        p.drawLine(QPointF(x, h * 0.67), QPointF(x + total, h * 0.67))
        tag = QFont(name)
        tag.setBold(False)
        tag.setPixelSize(max(8, int(h * 0.11)))
        tag.setLetterSpacing(QFont.PercentageSpacing, 112)
        p.setFont(tag)
        p.setPen(QColor("#b0b0b0") if dark else GRAY)
        p.drawText(QPointF(x, h * 0.84), "VIEW  •  EDIT  •  ANNOTATE  •  REVIEW")
    p.restore()
    return x + total


def logo_pixmap(height, dark=False, tagline=True):
    """The horizontal logo as a transparent pixmap of the given height."""
    probe = QImage(1, 1, QImage.Format_ARGB32_Premultiplied)
    p = QPainter(probe)
    width = draw_logo(p, QRectF(0, 0, height, height), dark, tagline)
    p.end()
    img = QImage(int(width + height * 0.05), int(height), QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    p = QPainter(img)
    draw_logo(p, QRectF(0, 0, height, height), dark, tagline)
    p.end()
    return QPixmap.fromImage(img)
