"""View > Rulers (Ctrl+R), the page size and pointer position on the status bar, and the status
bar's Reuse switch (1.12, the owner, 11 Nov, from a colleague's Bluebeam Revu screenshot: rulers
in inches, "(17.93, 8.82)" on the status bar, a Reuse button).

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_rulers
"""
import math
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402
from PySide6.QtCore import QEvent, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QMouseEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import paths, rulers  # noqa: E402
from kanzonas.main_window import MainWindow  # noqa: E402


def pump(n=5):
    for _ in range(n):
        APP.processEvents()


class Steps(unittest.TestCase):
    def test_labels_far_enough_apart_and_round(self):
        for ppu in (0.01, 0.3, 1, 2.83, 7.2, 72, 300, 5000):
            step, ticks = rulers.step_for(ppu)
            self.assertGreaterEqual(step * ppu, rulers.MIN_GAP * 0.999, ppu)
            self.assertLess(step * ppu, rulers.MIN_GAP * 5.01, ppu)
            mant = step / 10 ** math.floor(math.log10(step))
            self.assertIn(round(mant, 6), (1, 2, 5, 10), ppu)
            self.assertGreaterEqual(step * ppu / ticks, 5 - 1e-9, ppu)

    def test_units(self):
        self.assertAlmostEqual(rulers.to_units(72, "in"), 1)
        self.assertAlmostEqual(rulers.to_units(72, "mm"), 25.4)
        self.assertEqual(rulers.fmt(17.934, "in"), "17.93")
        self.assertEqual(rulers.fmt(25.44, "mm"), "25.4")
        self.assertEqual(rulers.fmt(612.4, "pt"), "612")


class InTheWindow(unittest.TestCase):
    def setUp(self):
        s = paths.settings()
        self.saved = {k: s.value(k) for k in ("show_rulers", "ruler_units", "reuse_tools")}
        self.addCleanup(self.restore)
        s.setValue("ruler_units", "in")
        rulers.forget_units()
        d = pymupdf.open()
        d.new_page(width=612, height=792)
        d.new_page(width=2592, height=1728)              # a 36 x 24 in sheet
        d[1].set_rotation(90)
        self.path = os.path.join(tempfile.mkdtemp(), "sheets.pdf")
        d.save(self.path)
        self.w = w = MainWindow()
        w.resize(1300, 900)
        w.show()
        pump()
        w.set_mouse_mode("standard")
        w.open_file(self.path)
        pump()
        self.v = w.view()
        self.addCleanup(self.close)

    def restore(self):
        s = paths.settings()
        for k, val in self.saved.items():
            if val is None:
                s.remove(k)
            else:
                s.setValue(k, val)
        rulers.forget_units()

    def close(self):
        self.w._close_confirmed = True
        self.w.close()
        pump()

    def rulers_on(self, on=True):
        self.w.a_rulers.setChecked(on)
        self.w._toggle_rulers()
        pump()

    def move(self, index, x_pt, y_pt):
        """The pointer to (x, y) points on page index as shown, through the page's own
        mouse handling."""
        pw = self.v.pages[index]
        o = pw.offset()
        pos = QPointF(o.x() + x_pt * self.v.zoom, o.y() + y_pt * self.v.zoom)
        ev = QMouseEvent(QEvent.MouseMove, pos, pw.mapToGlobal(pos), Qt.NoButton,
                         Qt.NoButton, Qt.NoModifier)
        pw.mouseMoveEvent(ev)
        pump(2)

    def test_rulers_on_and_off_and_remembered(self):
        self.assertFalse(self.v.rulers_shown())
        self.rulers_on()
        self.assertTrue(self.v.rulers_shown())
        m = self.v.viewportMargins()
        self.assertEqual((m.left(), m.top()), (rulers.THICKNESS, rulers.THICKNESS))
        top, left, corner = self.v._rulers
        vp = self.v.viewport().geometry()
        self.assertEqual(top.geometry().x(), vp.x())
        self.assertEqual(top.geometry().width(), vp.width())
        self.assertEqual(top.geometry().bottom() + 1, vp.y())
        self.assertEqual(left.geometry().y(), vp.y())
        self.assertEqual(paths.settings().value("show_rulers"), "true")
        for r in (top, left, corner):           # (each paints: inches, mm, points)
            for unit in rulers.UNITS:
                rulers.set_units(unit)
                r.grab()
        # a document opened now has them too
        other = os.path.join(tempfile.mkdtemp(), "other.pdf")
        pymupdf.open(self.path).save(other)
        self.w.open_file(other)
        pump()
        self.assertTrue(self.w.view().rulers_shown())
        self.rulers_on(False)
        self.assertFalse(self.v.rulers_shown())
        m = self.v.viewportMargins()
        self.assertEqual((m.left(), m.top()), (0, 0))

    def test_rulers_measure_from_the_page_s_corner(self):
        self.rulers_on()
        top, left, _corner = self.v._rulers
        self.move(0, 100, 200)
        index, start, zoom = top.page_span()
        pw = self.v.pages[0]
        corner = pw.mapTo(self.v.viewport(), pw.offset().toPoint())
        self.assertEqual(index, 0)
        self.assertEqual(start, corner.x())
        self.assertEqual(left.page_span()[1], corner.y())
        self.assertEqual(zoom, self.v.zoom)

    def test_rulers_below_a_banner(self):
        self.rulers_on()
        self.v.show_banner("A note across the top", closable=True)
        pump()
        b = self.v._banner.height()
        m = self.v.viewportMargins()
        self.assertEqual(m.top(), b + rulers.THICKNESS)
        self.assertEqual(self.v._rulers[0].geometry().y(), b)
        self.v.hide_banner()
        pump()
        self.assertEqual(self.v.viewportMargins().top(), rulers.THICKNESS)

    def test_status_bar_shows_size_and_pointer(self):
        self.move(0, 72, 144)
        self.assertEqual(self.w.pointer_label.text(), "8.50 × 11.00 in   (1.00, 2.00)")
        rulers.set_units("mm")
        self.v.units_changed()
        self.assertIn("215.9 × 279.4 mm   (25.4, 50.8)", self.w.pointer_label.text())
        rulers.set_units("in")
        # a turned sheet: its size and the pointer as it's shown (24 x 36 in, upright)
        self.v.goto_page(1)
        pump()
        self.move(1, 72 * 3, 72 * 30)
        self.assertEqual(self.w.pointer_label.text(), "24.00 × 36.00 in   (3.00, 30.00)")
        # off the document: the size of the page in view only
        self.v.pages[1].leaveEvent(QEvent(QEvent.Leave))
        pump()
        self.assertEqual(self.w.pointer_label.text(), "24.00 × 36.00 in")
        self.assertIsNone(self.v.pointer_pos())


class Reuse(unittest.TestCase):
    """Reuse on (as since 1.11): the tool stays picked after drawing; off: back to the mouse
    mode's tool. Either way what was drawn stays selected."""

    def setUp(self):
        from tests.test_drawn_markup_selected import Drawn
        self.case = Drawn("test_set_as_default")
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        s = paths.settings()
        before = s.value("reuse_tools")
        self.addCleanup(lambda: s.setValue("reuse_tools", before) if before is not None
                        else s.remove("reuse_tools"))

    def test_on_and_off(self):
        w, v = self.case.w, self.case.v
        self.assertTrue(w.reuse_btn.isChecked())
        w.set_tool("rect")
        pump()
        self.case.drag((100, 100), (200, 180))
        self.assertEqual(w.tool, "rect")
        self.assertIsNotNone(v.selection)
        w.reuse_btn.setChecked(False)
        self.assertEqual(paths.settings().value("reuse_tools"), "false")
        self.case.drag((300, 300), (400, 380))
        self.assertEqual(w.tool, w.default_tool())
        newest = max(a.xref for a in self.case.rects())
        self.assertEqual(v.selection, (0, newest))


if __name__ == "__main__":
    unittest.main()
