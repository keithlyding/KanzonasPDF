"""Light / dark theme and toolbar icons (the Material Design Icons font that ships with the
QtAwesome package)."""

import os

os.environ.setdefault("QT_API", "pyside6")

from PySide6.QtCore import Qt, QPoint, QRect
from PySide6.QtGui import (QPalette, QColor, QGuiApplication, QIcon, QIconEngine, QFont,
                           QPainter, QPixmap)

ICONS = {
    "image": "image-outline", "attach": "paperclip", "placeholder": "draw-pen",
    "cad_mouse": "mouse-move-vertical", "grid": "grid", "snap_grid": "magnet",
    "snap_objects": "vector-point",
    # arrange
    "al_left": "align-horizontal-left", "al_hcenter": "align-horizontal-center",
    "al_right": "align-horizontal-right", "al_top": "align-vertical-top",
    "al_vmiddle": "align-vertical-center", "al_bottom": "align-vertical-bottom",
    "dist_h": "distribute-horizontal-center", "dist_v": "distribute-vertical-center",
    "z_front": "arrange-bring-to-front", "z_back": "arrange-send-to-back",
    "z_forward": "arrange-bring-forward", "z_backward": "arrange-send-backward",
    # file / view
    "open": "folder-open-outline", "save": "content-save-outline", "print": "printer-outline",
    "undo": "undo", "redo": "redo", "zoom_in": "magnify-plus-outline",
    "zoom_out": "magnify-minus-outline", "fit_width": "arrow-expand-horizontal",
    "fit_page": "fit-to-page-outline", "ocr": "ocr", "forms": "form-select",
    "rot_l": "rotate-left", "rot_r": "rotate-right",
    # tools
    "select": "cursor-default-outline", "hand": "hand-back-right-outline",
    "edittext": "format-text", "highlight": "marker", "underline": "format-underline",
    "strikeout": "format-strikethrough", "comment": "comment-text-outline",
    "note": "note-text-outline", "textbox": "format-textbox", "callout": "message-text-outline",
    "rect": "rectangle-outline", "ellipse": "ellipse-outline", "cloud": "cloud-outline",
    "polygon": "vector-polygon", "line": "vector-line", "arrow": "arrow-top-right",
    "polyline": "vector-polyline", "ink": "draw", "stamp": "stamper", "eraser": "eraser",
    "erasecontent": "eraser-variant", "capture": "camera-outline",
    "editobjects": "image-edit-outline",
    "signature": "signature-freehand", "initials": "signature-text",
    "m_length": "ruler", "m_poly": "vector-polyline-edit", "m_area": "texture-box",
    "m_count": "counter", "m_calibrate": "tape-measure", "redact": "marker-cancel",
    "f_text": "form-textbox", "f_check": "checkbox-marked-outline", "f_radio": "radiobox-marked",
    "f_combo": "form-dropdown", "f_sign": "draw-pen",
}

_mode = "light"


def is_dark():
    return _mode == "dark"


_font = {}        # "family", "chars": the Material Design Icons font, loaded once


def _load_font():
    """Load the MDI 6 font that ships inside the qtawesome package, without importing
    qtawesome itself (that import costs about 0.2 s of start-up)."""
    if _font:
        return _font.get("family")
    _font["family"] = None
    try:
        import importlib.util
        import json
        import sys
        dirs = []
        spec = importlib.util.find_spec("qtawesome")
        if spec and spec.submodule_search_locations:
            dirs += list(spec.submodule_search_locations)
        if getattr(sys, "_MEIPASS", None):
            dirs.append(os.path.join(sys._MEIPASS, "qtawesome"))
        for d in dirs:
            fonts = os.path.join(d, "fonts")
            if not os.path.isdir(fonts):
                continue
            names = os.listdir(fonts)
            ttf = [n for n in names if n.startswith("materialdesignicons6") and n.endswith(".ttf")]
            cmap = [n for n in names if n.startswith("materialdesignicons6") and n.endswith(".json")]
            if not ttf or not cmap:
                continue
            from PySide6.QtGui import QFontDatabase
            fid = QFontDatabase.addApplicationFont(os.path.join(fonts, ttf[0]))
            fams = QFontDatabase.applicationFontFamilies(fid) if fid >= 0 else []
            if not fams:
                continue
            with open(os.path.join(fonts, cmap[0]), encoding="utf-8") as f:
                _font["chars"] = json.load(f)
            _font["family"] = fams[0]
            break
    except Exception:
        _font["family"] = None
    return _font["family"]


class _GlyphEngine(QIconEngine):
    """Draws one font glyph at whatever size and screen scale Qt asks for (sharp on any
    display), grayed out when the button is disabled."""

    def __init__(self, char, color):
        super().__init__()
        self.char, self.color = char, QColor(color)

    def paint(self, painter, rect, mode, state):
        painter.save()
        font = QFont(_font["family"])
        font.setPixelSize(max(1, round(rect.height() * 0.875)))
        painter.setFont(font)
        c = QColor(self.color)
        if mode == QIcon.Disabled:
            c.setAlphaF(0.35)
        painter.setPen(c)
        painter.drawText(rect, Qt.AlignCenter, self.char)
        painter.restore()

    def pixmap(self, size, mode, state):
        pm = QPixmap(size)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        self.paint(p, QRect(QPoint(0, 0), size), mode, state)
        p.end()
        return pm

    def clone(self):
        return _GlyphEngine(self.char, self.color)


def icon_named(name):
    """Icon by Material Design Icons name, tinted for the current theme (empty icon if the
    icon font isn't available)."""
    color = "#e6e6e6" if is_dark() else "#303030"
    if _load_font():
        code = _font["chars"].get(name)
        if code:
            return QIcon(_GlyphEngine(chr(int(code, 16)), color))
        return QIcon()
    try:                                # fallback: the font wasn't found on its own
        import qtawesome as qta
        return qta.icon("mdi6." + name, color=color, color_active=color)
    except Exception:
        return QIcon()


def icon(key):
    """Icon for a toolbar key (see ICONS)."""
    name = ICONS.get(key)
    return icon_named(name) if name else QIcon()


def _system_prefers_dark():
    try:
        return QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark
    except Exception:
        return False


def apply(app, mode):
    """mode: 'light' | 'dark' | 'system'."""
    global _mode
    _mode = "dark" if mode == "dark" or (mode == "system" and _system_prefers_dark()) else "light"
    app.setStyle("Fusion")
    if _mode == "light":
        app.setPalette(app.style().standardPalette())
        return
    p = QPalette()
    base, window, text = QColor(37, 37, 38), QColor(45, 45, 48), QColor(230, 230, 230)
    p.setColor(QPalette.Window, window)
    p.setColor(QPalette.WindowText, text)
    p.setColor(QPalette.Base, base)
    p.setColor(QPalette.AlternateBase, window)
    p.setColor(QPalette.ToolTipBase, QColor(60, 60, 60))
    p.setColor(QPalette.ToolTipText, text)
    p.setColor(QPalette.Text, text)
    p.setColor(QPalette.Button, window)
    p.setColor(QPalette.ButtonText, text)
    p.setColor(QPalette.BrightText, QColor(255, 80, 80))
    p.setColor(QPalette.Highlight, QColor(0, 120, 215))
    p.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
    p.setColor(QPalette.Link, QColor(80, 160, 255))
    p.setColor(QPalette.PlaceholderText, QColor(150, 150, 150))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        p.setColor(QPalette.Disabled, role, QColor(120, 120, 120))
    app.setPalette(p)
