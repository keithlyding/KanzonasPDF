"""A font for tests that measure text on screen. Qt's offscreen platform on the Windows build
machine finds no font at all: every text measures 0 px wide, so an editor box thinks each word
wraps, and nothing is ever too long. ensure_font() then gives the application PyMuPDF's own
Helvetica (Nimbus Sans) to measure and draw with; elsewhere it changes nothing."""
from PySide6.QtCore import QByteArray
from PySide6.QtGui import QFont, QFontDatabase, QFontMetrics
from PySide6.QtWidgets import QApplication

_done = []


def ensure_font():
    app = QApplication.instance()
    if _done or app is None or QFontMetrics(app.font()).horizontalAdvance("Mm") > 0:
        return
    import pymupdf
    i = QFontDatabase.addApplicationFontFromData(QByteArray(bytes(pymupdf.Font("helv").buffer)))
    families = QFontDatabase.applicationFontFamilies(i) if i >= 0 else []
    if families:
        app.setFont(QFont(families[0], 9))
        _done.append(families[0])
