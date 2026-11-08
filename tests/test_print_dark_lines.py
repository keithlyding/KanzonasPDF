"""File > Print: thin lines print dark (the owner: "when I print documents from KanzonasPDF, the
printed lines are faint"). Pages are printed as pictures; a line thinner than a printer dot was
drawn smoothed, as a pale gray (a 0.1 pt line at 300 dpi: 55% gray) that the printer then breaks
into sparse dots. With Dark thin lines (the Print window, on unless turned off), every line
prints at least 0.15 pt wide and never less than one dot, solid; text keeps its smoothing, and
the program's rendering settings are put back right after.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_print_dark_lines -t .
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402
from PySide6.QtGui import QImage, QPainter  # noqa: E402
from PySide6.QtCore import QRectF  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas.document_view import DocumentView  # noqa: E402
from kanzonas.print_dialog import PrintDialog, print_lines  # noqa: E402

WIDTHS = (0.05, 0.1, 0.18)


def lines_doc(path):
    d = pymupdf.open()
    p = d.new_page()
    for i, w in enumerate(WIDTHS):
        y = 100 + 40 * i
        p.draw_line((72, y), (500, y + 3), color=(0, 0, 0), width=w)
    p.insert_text((72, 300), "Text keeps its smoothing", fontsize=11)
    d.save(path)


def darkest(img, k):
    """The darkest gray across each line, at its middle (0 black .. 255 white)."""
    out = []
    for i in range(len(WIDTHS)):
        y0, y1 = int((100 + 40 * i - 4) * k), int((100 + 40 * i + 7) * k)
        x = int(286 * k)
        out.append(min(QImage.pixelColor(img, x, y).lightness() for y in range(y0, y1)))
    return out


class DarkLines(unittest.TestCase):
    def setUp(self):
        path = os.path.join(tempfile.mkdtemp(), "lines.pdf")
        lines_doc(path)
        self.v = DocumentView(path)
        self.addCleanup(self.v.close_doc)

    def printed(self, dlg, dpi):
        """Page 1 drawn as the print does it, at dpi, into an image."""
        k = dpi / 72.0
        r = self.v.doc[0].rect
        img = QImage(int(r.width * k), int(r.height * k), QImage.Format_RGB32)
        img.fill(0xFFFFFFFF)
        p = QPainter(img)
        self.assertTrue(dlg._draw_bands(p, 0, QRectF(0, 0, img.width(), img.height()), dpi))
        p.end()
        return img

    def test_thin_lines_print_solid(self):
        dlg = PrintDialog(None, self.v)
        dlg.dark_lines.setChecked(True)
        for dpi in (300, 600):
            got = darkest(self.printed(dlg, dpi), dpi / 72.0)
            self.assertTrue(all(g < 40 for g in got), (dpi, got))

    def test_turned_off_they_print_as_thin_as_they_are(self):
        dlg = PrintDialog(None, self.v)
        dlg.dark_lines.setChecked(False)
        got = darkest(self.printed(dlg, 300), 300 / 72.0)
        self.assertGreater(got[0], 100)                 # 0.05 pt at 300 dpi: pale, as before

    def test_settings_put_back_and_text_smoothed(self):
        m = pymupdf.mupdf
        before = (m.fz_graphics_aa_level(), m.fz_text_aa_level())
        with print_lines(300):
            self.assertEqual(m.fz_graphics_aa_level(), 0)
            self.assertEqual(m.fz_text_aa_level(), before[1])       # text keeps smoothing
        self.assertEqual((m.fz_graphics_aa_level(), m.fz_text_aa_level()), before)
        # a page on screen after printing: its thinnest line is pale again (true width)
        pm = self.v.doc[0].get_pixmap(matrix=pymupdf.Matrix(300 / 72, 300 / 72),
                                      colorspace=pymupdf.csGRAY)
        k = 300 / 72
        col = [pm.pixel(int(286 * k), y)[0] for y in range(int(96 * k), int(107 * k))]
        self.assertGreater(min(col), 100)


if __name__ == "__main__":
    unittest.main()
