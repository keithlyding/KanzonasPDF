"""Fonts for tests that measure text on screen. Qt's offscreen platform on the Windows build
machine finds no font at all: every text measures 0 px wide, so an editor box thinks each word
wraps, and nothing is ever too long. ensure_font() then loads PyMuPDF's own Helvetica, Times
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


def ensure_font():
    app = QApplication.instance()
    if _done or app is None or (_measures(app.font().family()) and _measures("Arial")):
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
    if not (_measures(app.font().family()) and _measures("Arial")):
        raise RuntimeError("tests.qt_fonts: no font measures text here, even PyMuPDF's")
