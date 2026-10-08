"""Saved signature and initials.

The images are stored in the user's app-data folder. With a PIN set they're encrypted
(PBKDF2-derived key, SHAKE-256 keystream, HMAC check) so other people using the same
Windows account can't simply copy the files and reuse them.

When placed, a signature is written into the page content as an image (plus the date),
not as a movable annotation, so it can't be dragged or restyled like markup.
"""

import base64
import hashlib
import hmac
import json
import os
import secrets
from datetime import date

from PySide6.QtCore import Qt, QRectF, QBuffer, QIODevice, QByteArray
from PySide6.QtGui import QImage, QPainter, QPen, QColor, QPainterPath
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
                               QWidget, QFileDialog, QInputDialog, QLineEdit, QMessageBox,
                               QComboBox, QCheckBox, QSlider)

KINDS = ("signature", "initials")
DATE_FORMATS = ["%m/%d/%Y", "%d/%m/%Y", "%Y-%m-%d", "%B %d, %Y"]


def _dir():
    from . import paths
    return paths.data_dir("signatures")


def _meta_path():
    return os.path.join(_dir(), "settings.json")


def load_meta():
    try:
        with open(_meta_path(), "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_meta(meta):
    with open(_meta_path(), "w", encoding="utf-8") as f:
        json.dump(meta, f)


# ---- encryption (stdlib only) ------------------------------------------------------
def _derive(pin, salt):
    return hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), salt, 200_000, dklen=64)


def _xor_stream(key, nonce, data):
    stream = hashlib.shake_256(key + nonce).digest(len(data))
    return bytes(a ^ b for a, b in zip(data, stream))


def _encrypt(pin, data):
    salt, nonce = secrets.token_bytes(16), secrets.token_bytes(16)
    k = _derive(pin, salt)
    ct = _xor_stream(k[:32], nonce, data)
    tag = hmac.new(k[32:], nonce + ct, hashlib.sha256).digest()
    return b"KZS1" + salt + nonce + tag + ct


def _decrypt(pin, blob):
    if not blob.startswith(b"KZS1"):
        raise ValueError("not an encrypted signature")
    salt, nonce, tag, ct = blob[4:20], blob[20:36], blob[36:68], blob[68:]
    k = _derive(pin, salt)
    if not hmac.compare_digest(tag, hmac.new(k[32:], nonce + ct, hashlib.sha256).digest()):
        raise ValueError("wrong PIN")
    return _xor_stream(k[:32], nonce, ct)


def has_pin():
    return bool(load_meta().get("pin_check"))


def _pin_ok(pin):
    meta = load_meta()
    if not meta.get("pin_check"):
        return True
    try:
        _decrypt(pin, base64.b64decode(meta["pin_check"]))
        return True
    except ValueError:
        return False


# ---- storage -----------------------------------------------------------------------
def _path(kind):
    return os.path.join(_dir(), kind + ".kzsig")


def exists(kind):
    return os.path.exists(_path(kind))


def store(kind, png_bytes, pin=None):
    data = _encrypt(pin, png_bytes) if pin else png_bytes
    with open(_path(kind), "wb") as f:
        f.write(data)


def load(kind, pin=None):
    """PNG bytes, or raises ValueError('PIN required' / 'wrong PIN')."""
    with open(_path(kind), "rb") as f:
        blob = f.read()
    if blob.startswith(b"KZS1"):
        if not pin:
            raise ValueError("PIN required")
        return _decrypt(pin, blob)
    return blob


def set_pin(new_pin, old_pin=None):
    """Re-encrypt stored images with a new PIN ('' removes the PIN)."""
    images = {k: load(k, old_pin) for k in KINDS if exists(k)}
    meta = load_meta()
    if new_pin:
        meta["pin_check"] = base64.b64encode(_encrypt(new_pin, b"ok")).decode()
    else:
        meta.pop("pin_check", None)
    save_meta(meta)
    for k, png in images.items():
        store(k, png, new_pin or None)


def date_format():
    fmt = load_meta().get("date_format", DATE_FORMATS[0])
    return fmt if fmt in DATE_FORMATS else DATE_FORMATS[0]


def set_date_format(fmt):
    meta = load_meta()
    meta["date_format"] = fmt
    save_meta(meta)


def date_text():
    """Today's date in the chosen format (the Date tool; Preferences > You)."""
    return date.today().strftime(date_format())


# ---- image helpers ----------------------------------------------------------------
def qimage_to_png(img):
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.WriteOnly)
    img.save(buf, "PNG")
    return bytes(ba)


def clean_scan(img, threshold=200, ink=None):
    """Photo/scan of a signature -> transparent background, cropped to the ink.
    Pixels lighter than threshold become transparent; ink can be recolored."""
    import numpy as np
    img = img.convertToFormat(QImage.Format_RGBA8888)
    w, h = img.width(), img.height()
    arr = np.frombuffer(img.constBits(), np.uint8).reshape(h, img.bytesPerLine())[:, :w * 4]
    arr = arr.reshape(h, w, 4).astype(np.float32)
    lum = 0.299 * arr[..., 0] + 0.587 * arr[..., 1] + 0.114 * arr[..., 2]
    alpha = np.clip((threshold - lum) / max(1.0, threshold * 0.5), 0, 1) * 255
    alpha[lum >= threshold] = 0
    alpha[(alpha > 0) & (alpha < 40)] = 40
    out = arr.copy()
    if ink:
        c = QColor(ink)
        out[..., 0], out[..., 1], out[..., 2] = c.red(), c.green(), c.blue()
    out[..., 3] = alpha
    out = np.ascontiguousarray(out.astype(np.uint8))
    res = QImage(out.data, w, h, w * 4, QImage.Format_RGBA8888).copy()
    ys, xs = np.nonzero(alpha)
    if len(xs) == 0:
        return res
    pad = 4
    x0, y0 = max(0, xs.min() - pad), max(0, ys.min() - pad)
    x1, y1 = min(w, xs.max() + pad + 1), min(h, ys.max() + pad + 1)
    return res.copy(int(x0), int(y0), int(x1 - x0), int(y1 - y0))


class DrawPad(QWidget):
    """Draw a signature with the mouse or a pen."""

    def __init__(self):
        super().__init__()
        self.setMinimumSize(520, 180)
        self.setStyleSheet("background: white; border: 1px solid #999;")
        self.strokes = []
        self.ink = QColor("#000000")
        self.setCursor(Qt.CrossCursor)

    def clear(self):
        self.strokes = []
        self.update()

    def mousePressEvent(self, e):
        self.strokes.append([e.position()])

    def mouseMoveEvent(self, e):
        if e.buttons() and self.strokes:
            self.strokes[-1].append(e.position())
            self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), Qt.white)
        p.setPen(QPen(QColor("#cccccc"), 1, Qt.DashLine))
        p.drawLine(20, self.height() - 40, self.width() - 20, self.height() - 40)
        self._draw(p, 1.0)

    def _draw(self, p, scale):
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(self.ink, 2.6 * scale, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        for s in self.strokes:
            if len(s) == 1:
                p.drawPoint(s[0] * scale)
                continue
            path = QPainterPath(s[0] * scale)
            for q in s[1:]:
                path.lineTo(q * scale)
            p.drawPath(path)

    def image(self):
        """High-resolution transparent image cropped to the strokes."""
        if not self.strokes:
            return None
        scale = 4
        img = QImage(self.width() * scale, self.height() * scale, QImage.Format_ARGB32)
        img.fill(Qt.transparent)
        p = QPainter(img)
        self._draw(p, scale)
        p.end()
        xs = [q.x() for s in self.strokes for q in s]
        ys = [q.y() for s in self.strokes for q in s]
        pad = 6
        r = QRectF(min(xs) - pad, min(ys) - pad, max(xs) - min(xs) + 2 * pad,
                   max(ys) - min(ys) + 2 * pad)
        return img.copy(int(r.x() * scale), int(r.y() * scale),
                        int(r.width() * scale), int(r.height() * scale))


class SignatureSetup(QDialog):
    """Create / replace the saved signature or initials, choose date format, set a PIN."""

    def __init__(self, parent, kind):
        super().__init__(parent)
        self.kind = kind
        self.setWindowTitle(f"Set up your {kind}")
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(f"Draw your {kind} below, or load a scan/photo of your wet "
                             f"{kind} (signed on white paper)."))
        self.pad = DrawPad()
        lay.addWidget(self.pad)
        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumHeight(60)
        self.preview.hide()
        lay.addWidget(self.preview)
        row = QHBoxLayout()
        b_clear = QPushButton("Clear")
        b_clear.clicked.connect(self._clear)
        b_load = QPushButton("Load scan / photo...")
        b_load.clicked.connect(self._load)
        self.ink = QComboBox()
        self.ink.addItems(["Black ink", "Blue ink", "Keep original colors"])
        self.ink.currentIndexChanged.connect(self._ink_changed)
        row.addWidget(b_clear)
        row.addWidget(b_load)
        row.addWidget(self.ink)
        row.addStretch(1)
        lay.addLayout(row)
        self.thresh = QSlider(Qt.Horizontal)
        self.thresh.setRange(120, 245)
        self.thresh.setValue(200)
        self.thresh.setToolTip("Background removal for scans: move right if paper is left behind, "
                               "left if ink is lost")
        self.thresh.sliderReleased.connect(self._reprocess)
        self.thresh_label = QLabel("Background removal (scans):")
        self.thresh_label.hide()
        self.thresh.hide()
        lay.addWidget(self.thresh_label)
        lay.addWidget(self.thresh)

        self.use_pin = QCheckBox("Protect my signature and initials with a PIN "
                                 "(asked once each time the app starts)")
        self.use_pin.setChecked(has_pin())
        lay.addWidget(self.use_pin)

        btns = QHBoxLayout()
        btns.addStretch(1)
        ok = QPushButton("Save")
        ok.setDefault(True)
        ok.clicked.connect(self._save)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        btns.addWidget(ok)
        btns.addWidget(cancel)
        lay.addLayout(btns)
        self._scan = None
        self._scan_src = None
        self.png = None

    def _ink_color(self):
        return {0: "#000000", 1: "#1a3c9e"}.get(self.ink.currentIndex())

    def _ink_changed(self):
        self.pad.ink = QColor(self._ink_color() or "#000000")
        self.pad.update()
        self._reprocess()

    def _clear(self):
        self.pad.clear()
        self._scan = self._scan_src = None
        self.preview.hide()
        self.thresh.hide()
        self.thresh_label.hide()
        self.pad.show()

    def _load(self):
        path, _ = QFileDialog.getOpenFileName(self, "Signature image", "",
                                              "Images (*.png *.jpg *.jpeg *.bmp *.tif *.tiff)")
        if not path:
            return
        img = QImage(path)
        if img.isNull():
            QMessageBox.warning(self, "Signature", "Couldn't read that image.")
            return
        if img.width() > 1600:              # plenty for a signature; keeps processing quick
            img = img.scaledToWidth(1600, Qt.SmoothTransformation)
        self._scan_src = img
        self.pad.hide()
        self.thresh.show()
        self.thresh_label.show()
        self._reprocess()

    def _reprocess(self):
        if self._scan_src is None:
            return
        self._scan = clean_scan(self._scan_src, self.thresh.value(), self._ink_color())
        from PySide6.QtGui import QPixmap
        pm = QPixmap.fromImage(self._scan).scaled(500, 160, Qt.KeepAspectRatio,
                                                  Qt.SmoothTransformation)
        self.preview.setPixmap(pm)
        self.preview.show()

    def _save(self):
        img = self._scan if self._scan is not None else self.pad.image()
        if img is None:
            QMessageBox.information(self, "Signature", f"Draw or load your {self.kind} first.")
            return
        pin = None
        if self.use_pin.isChecked():
            pin = ask_pin(self, "Enter your signature PIN" if has_pin() else
                          "Choose a PIN for your signature and initials")
            if pin is None:
                return
            if has_pin() and not _pin_ok(pin):
                QMessageBox.warning(self, "Signature", "Wrong PIN.")
                return
            if not has_pin():
                try:
                    set_pin(pin)
                except ValueError:
                    QMessageBox.warning(self, "Signature",
                                        "Existing images are protected by a different PIN.")
                    return
        elif has_pin():
            old = ask_pin(self, "Enter your current PIN to remove PIN protection")
            if old is None or not _pin_ok(old):
                return
            set_pin("", old)
        store(self.kind, qimage_to_png(img), pin)
        self.png = qimage_to_png(img)
        Session.pin = pin or Session.pin
        self.accept()


def ask_pin(parent, prompt):
    pin, ok = QInputDialog.getText(parent, "Signature PIN", prompt, QLineEdit.Password)
    return pin if ok and pin else None


class Session:
    """PIN remembered for this run of the app only (never written to disk)."""
    pin = None


def get_image(parent, kind):
    """PNG bytes of the saved signature/initials, asking for setup or the PIN as needed."""
    if not exists(kind):
        dlg = SignatureSetup(parent, kind)
        if dlg.exec() != QDialog.Accepted:
            return None
        return dlg.png
    for _ in range(3):
        try:
            return load(kind, Session.pin)
        except ValueError:
            pin = ask_pin(parent, f"Enter your PIN to use your {kind}")
            if pin is None:
                return None
            if _pin_ok(pin):
                Session.pin = pin
            else:
                QMessageBox.warning(parent, "Signature", "Wrong PIN.")
    return None
