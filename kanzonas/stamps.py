"""Stamps: text stamps (APPROVED, DRAFT, ... with name and date) drawn as images, and a
library of custom image stamps kept in the app-data folder."""

import os
import shutil
from datetime import datetime

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QImage, QPainter, QPen, QColor, QFont, QFontMetricsF

from . import signatures

PRESETS = ["APPROVED", "APPROVED AS NOTED", "REVIEWED", "REVISE AND RESUBMIT", "REJECTED",
           "NOT APPROVED", "DRAFT", "FINAL", "FOR CONSTRUCTION", "NOT FOR CONSTRUCTION",
           "FOR INFORMATION ONLY", "RECEIVED", "CONFIDENTIAL", "VOID", "COMPLETED"]
IMAGE_PREFIX = "image:"
SCALE = 4          # render resolution: pixels per point


def library_dir():
    from . import paths
    return paths.data_dir("stamps")


def library():
    """Custom image stamps: [file name]."""
    exts = (".png", ".jpg", ".jpeg", ".bmp")
    return sorted(f for f in os.listdir(library_dir()) if f.lower().endswith(exts))


def add_to_library(path):
    name = os.path.basename(path)
    shutil.copy2(path, os.path.join(library_dir(), name))
    return name


def detail_line(author, with_name=True, with_date=True):
    """Small line under a stamp's label: name and/or date."""
    date_s = (signatures.date_text() or datetime.now().strftime("%m/%d/%Y")) if with_date else ""
    parts = [p for p in (author if with_name else "", date_s) if p]
    return "  ·  ".join(parts)


def render(label, color="#c00000", detail=""):
    """Text stamp -> (png bytes, aspect height/width). Bold label in a double border."""
    col = QColor(color)
    big = QFont("Arial", 1)
    big.setBold(True)
    big.setPixelSize(22 * SCALE)
    small = QFont("Arial", 1)
    small.setPixelSize(10 * SCALE)
    fm_big, fm_small = QFontMetricsF(big), QFontMetricsF(small)
    pad = 10 * SCALE
    w = max(fm_big.horizontalAdvance(label), fm_small.horizontalAdvance(detail) if detail else 0)
    w += 2 * pad
    h = fm_big.height() + (fm_small.height() + 2 * SCALE if detail else 0) + 1.2 * pad
    img = QImage(int(w), int(h), QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.TextAntialiasing)
    p.setPen(QPen(col, 3 * SCALE))
    p.drawRoundedRect(QRectF(1.5 * SCALE, 1.5 * SCALE, w - 3 * SCALE, h - 3 * SCALE),
                      6 * SCALE, 6 * SCALE)
    p.setPen(QPen(col, 1 * SCALE))
    p.drawRoundedRect(QRectF(5 * SCALE, 5 * SCALE, w - 10 * SCALE, h - 10 * SCALE),
                      4 * SCALE, 4 * SCALE)
    p.setFont(big)
    top = 0.6 * pad
    p.drawText(QRectF(0, top, w, fm_big.height()), Qt.AlignCenter, label)
    if detail:
        p.setFont(small)
        p.drawText(QRectF(0, top + fm_big.height(), w, fm_small.height()), Qt.AlignCenter, detail)
    p.end()
    return signatures.qimage_to_png(img), h / w


def image_stamp(file_name):
    """Library image -> (png bytes, aspect) or (None, None) if the file is gone."""
    path = os.path.join(library_dir(), file_name)
    img = QImage(path)
    if img.isNull():
        return None, None
    return signatures.qimage_to_png(img), img.height() / img.width()


def stamp_png(props, author):
    """(png bytes, aspect) for a stamp's properties."""
    label = props.get("label") or "APPROVED"
    if label.startswith(IMAGE_PREFIX):
        return image_stamp(label[len(IMAGE_PREFIX):])
    return render(label, props.get("stroke") or "#c00000",
                  detail_line(author, props.get("name", True), props.get("date", True)))


def default_width(label):
    return 110.0 if label.startswith(IMAGE_PREFIX) else max(90.0, 9.5 * len(label) + 30)
