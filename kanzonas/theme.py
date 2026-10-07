"""Light / dark theme and toolbar icons (Material Design Icons via QtAwesome, MIT)."""

import os

os.environ.setdefault("QT_API", "pyside6")

from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette, QColor, QGuiApplication, QIcon

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
    "signature": "signature-freehand", "initials": "signature-text",
    "m_length": "ruler", "m_poly": "vector-polyline-edit", "m_area": "texture-box",
    "m_count": "counter", "m_calibrate": "tape-measure", "redact": "marker-cancel",
    "f_text": "form-textbox", "f_check": "checkbox-marked-outline", "f_radio": "radiobox-marked",
    "f_combo": "form-dropdown", "f_sign": "draw-pen",
}

_mode = "light"


def is_dark():
    return _mode == "dark"


def icon(key):
    """Icon tinted for the current theme (empty icon if the icon font isn't available)."""
    name = ICONS.get(key)
    if not name:
        return QIcon()
    try:
        import qtawesome as qta
        color = "#e6e6e6" if is_dark() else "#303030"
        return qta.icon("mdi6." + name, color=color, color_active=color)
    except Exception:
        return QIcon()


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
