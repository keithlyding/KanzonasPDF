"""TEMPORARY diagnostic (branch claude/win-font-probe only, never merged): what fonts measure
on this machine's offscreen Qt, and what the Add text editor's font is. Always passes."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pymupdf  # noqa: E402
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QFont, QFontDatabase, QFontInfo, QFontMetrics  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402
APP = QApplication.instance() or QApplication([])


class Probe(unittest.TestCase):
    def test_print_fonts(self):
        out = ["", "FONT PROBE on %s" % sys.platform]
        fams = QFontDatabase.families()
        out.append("  families: %d %s" % (len(fams), fams[:12]))
        af = APP.font()
        out.append("  app font %r pt %s px %s -> real %r, Mm=%d" % (
            af.family(), af.pointSizeF(), af.pixelSize(), QFontInfo(af).family(),
            QFontMetrics(af).horizontalAdvance("Mm")))
        for fam in ("Arial", "Helvetica", "Nimbus Sans", "Segoe UI"):
            f1 = QFont(fam, 9)
            f2 = QFont(fam)
            f2.setPixelSize(18)
            out.append("  %-12s pt9 Mm=%d real=%r | px18 Mm=%d real=%r" % (
                fam, QFontMetrics(f1).horizontalAdvance("Mm"), QFontInfo(f1).family(),
                QFontMetrics(f2).horizontalAdvance("Mm"), QFontInfo(f2).family()))
        from kanzonas.main_window import MainWindow
        d = pymupdf.open()
        d.new_page()
        p = os.path.join(tempfile.mkdtemp(), "p.pdf")
        d.save(p)
        w = MainWindow()
        w.resize(1400, 900)
        w.show()
        APP.processEvents()
        w.open_file(p)
        APP.processEvents()
        v = w.view()
        w.set_tool("addtext")
        pw = v.pages[0]
        at = pw.to_screen(pymupdf.Rect(100, 150, 100, 150)).topLeft().toPoint()
        QTest.mouseClick(pw, Qt.LeftButton, Qt.NoModifier, at)
        APP.processEvents()
        ed = v._inline
        QTest.keyClicks(ed.text, "Room 101")
        APP.processEvents()
        tf = ed.text.font()
        cf = ed.text.currentCharFormat().font()
        out.append("  editor widget font %r px %s real %r Mm=%d | char format font %r px %s "
                   "real %r Mm=%d | natural width %.1f | doc ideal %.1f | box %d" % (
                       tf.family(), tf.pixelSize(), QFontInfo(tf).family(),
                       QFontMetrics(tf).horizontalAdvance("Mm"), cf.family(), cf.pixelSize(),
                       QFontInfo(cf).family(), QFontMetrics(cf).horizontalAdvance("Mm"),
                       ed._natural_width(), ed.text.document().idealWidth(), ed.width()))
        w._close_confirmed = True
        w.close()
        print("\n".join(out), file=sys.stderr, flush=True)
