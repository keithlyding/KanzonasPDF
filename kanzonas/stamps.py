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
# fill-in stamps: you type the values when placing them (double-click one to change them)
FORM_PREFIX = "form:"
FORM_PRESETS = [FORM_PREFIX + "PO #|Date ordered", FORM_PREFIX + "Req #|Date submitted"]


def form_fields(label):
    """'form:PO #|Date ordered' -> ['PO #', 'Date ordered'] (None if not a fill-in stamp)."""
    if not label.startswith(FORM_PREFIX):
        return None
    return [f.strip() for f in label[len(FORM_PREFIX):].split("|") if f.strip()]


def form_title(label):
    return " / ".join(form_fields(label) or [])


def is_date_field(name):
    return name.lower().startswith("date")
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


def render_form(fields, values, color="#c00000"):
    """Fill-in stamp -> (png bytes, aspect): one 'Name: value' row per field, the value
    underlined, in the same double border as the text stamps."""
    col = QColor(color)
    font = QFont("Arial", 1)
    font.setBold(True)
    font.setPixelSize(12 * SCALE)
    vfont = QFont("Arial", 1)
    vfont.setPixelSize(12 * SCALE)
    fm, vfm = QFontMetricsF(font), QFontMetricsF(vfont)
    values = list(values) + [""] * (len(fields) - len(values))
    pad = 10 * SCALE
    name_w = max(fm.horizontalAdvance(f + ":") for f in fields)
    value_w = max([vfm.horizontalAdvance(v) for v in values] + [80 * SCALE])
    row = fm.height() * 1.45
    w = pad * 2 + name_w + 6 * SCALE + value_w
    h = pad * 1.6 + row * len(fields)
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
    y = pad * 0.8
    vx = pad + name_w + 6 * SCALE
    for f, v in zip(fields, values):
        p.setFont(font)
        p.drawText(QRectF(pad, y, name_w, row), Qt.AlignLeft | Qt.AlignVCenter, f + ":")
        p.setFont(vfont)
        p.drawText(QRectF(vx, y, value_w, row), Qt.AlignLeft | Qt.AlignVCenter, v)
        base = y + row / 2 + vfm.height() / 2
        p.drawLine(int(vx), int(base), int(vx + value_w), int(base))
        y += row
    p.end()
    return signatures.qimage_to_png(img), h / w


def ask_form_values(parent, label, values=None):
    """Ask for a fill-in stamp's values; dates start as today. None if canceled."""
    from PySide6.QtWidgets import QDialog, QFormLayout, QLineEdit, QDialogButtonBox
    fields = form_fields(label)
    values = list(values or [])
    dlg = QDialog(parent)
    dlg.setWindowTitle(form_title(label) + " stamp")
    form = QFormLayout(dlg)
    edits = []
    for k, f in enumerate(fields):
        e = QLineEdit(values[k] if k < len(values) else
                      (signatures.date_text() or datetime.now().strftime("%m/%d/%Y"))
                      if is_date_field(f) else "")
        form.addRow(f + ":", e)
        edits.append(e)
    btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    btns.accepted.connect(dlg.accept)
    btns.rejected.connect(dlg.reject)
    form.addRow(btns)
    if edits:
        edits[0].setFocus()
    if not dlg.exec():
        return None
    return [e.text().strip() for e in edits]


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
    if label.startswith(FORM_PREFIX):
        return render_form(form_fields(label), [], props.get("stroke") or "#c00000")
    return render(label, props.get("stroke") or "#c00000",
                  detail_line(author, props.get("name", True), props.get("date", True)))


def default_width(label):
    if label.startswith(FORM_PREFIX):
        return 170.0
    return 110.0 if label.startswith(IMAGE_PREFIX) else max(90.0, 9.5 * len(label) + 30)
