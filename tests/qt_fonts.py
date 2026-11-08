"""Fonts for tests that measure text on screen. Qt's offscreen platform on the Windows build
machine has no font at all (QFontDatabase.families() is empty); once the app loads its icon
font, Material Design Icons, every family falls back to it, which has no letters: every text
measures 0 px wide, so an editor box thinks each word wraps, and nothing is ever too long. ensure_font() then loads PyMuPDF's own Helvetica, Times
and Courier (Nimbus Sans, Roman, Mono), makes them the application's font and stands them in
for the families the app asks for (Arial, Helvetica, Times New Roman...), and checks that text
measures; elsewhere it changes nothing."""
from PySide6.QtCore import QByteArray
from PySide6.QtGui import QFont, QFontDatabase, QFontMetrics
from PySide6.QtWidgets import QApplication

_done = []

# the families the app's editors and widgets ask for, by kind
STAND_INS = {
    "helv": ("Arial", "Helvetica", "Segoe UI", "MS Shell Dlg 2", "Sans Serif", "sans-serif",
             "DejaVu Sans", "Liberation Sans", "Arimo", "Tahoma", "Verdana", "Calibri"),
    "tiro": ("Times New Roman", "Times", "serif", "Liberation Serif", "DejaVu Serif",
             "Georgia", "Cambria"),
    "cour": ("Courier New", "Courier", "monospace", "Consolas", "Liberation Mono",
             "DejaVu Sans Mono"),
}


def _measures(family):
    return QFontMetrics(QFont(family, 9)).horizontalAdvance("Mm") > 0


def _text_families():
    """The installed families that hold letters (not the app's own icon font)."""
    return [f for f in QFontDatabase.families() if "Material Design" not in f]


def ensure_font():
    app = QApplication.instance()
    # (measuring doesn't tell: before the app loads its icon font, Qt's fallback measures;
    # after, the icon font is the only font there is and every family falls back to it)
    if _done or app is None or _text_families():
        return
    import pymupdf
    first = None
    for code, names in STAND_INS.items():
        i = QFontDatabase.addApplicationFontFromData(
            QByteArray(bytes(pymupdf.Font(code).buffer)))
        families = QFontDatabase.applicationFontFamilies(i) if i >= 0 else []
        if not families:
            continue
        first = first or families[0]
        for name in names:
            QFont.insertSubstitution(name, families[0])
    if first:
        app.setFont(QFont(first, 9))
        _done.append(first)
    if not (_text_families() and _measures("Arial")):
        raise RuntimeError("tests.qt_fonts: no font measures text here, even PyMuPDF's")
