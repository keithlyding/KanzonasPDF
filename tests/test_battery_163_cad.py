"""Battery for 1.6.3's CAD additions (click, move, click drawing; Circle, Mask, Arc, Curve,
bent lines; Trim on shapes and open clouds; split buttons): what broke when it was tried.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_battery_163_cad
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import annotations as A, cad_draw  # noqa: E402
from tests.test_cad_click_draw import Base, markups  # noqa: E402


class CircleRadiusTyped(Base):
    """The radius typed on the command line while a circle is drawn."""

    def radius_of(self, text):
        v = self.v
        v.set_tool("circle")
        self.click((300, 400))
        self.assertIsNotNone(self.pending())
        said = []
        v.statusMessage.connect(said.append)
        self.assertTrue(cad_draw.typed(v, text))
        v.statusMessage.disconnect(said.append)
        got = markups(v)
        if not got:
            return None, said
        (kind, r, _p), = got
        self.assertEqual(kind, "ellipse")
        return (r[2] - r[0]) / 2, said

    def test_a_decimal_comma_is_a_decimal_point(self):
        # as Rotate and Scale take "0,5" on the same line (cad_commands.number): not 5
        r, _said = self.radius_of("0,5")
        self.assertAlmostEqual(r, 36 + 1, delta=1.5)         # half an inch, plus half the width
        cad_draw.cancel(self.v)

    def test_feet_and_inches_with_a_decimal_comma(self):
        r, _said = self.radius_of("1'-0,5\"")
        self.assertAlmostEqual(r, 12.5 * 72 + 1, delta=1.5)

    def test_too_small_to_draw_says_so_and_keeps_the_circle(self):
        # 0.001 inch is 0.07 pt: the Circle tool makes nothing that small; the circle being
        # drawn used to go without a word
        r, said = self.radius_of("0.001")
        self.assertIsNone(r)
        self.assertIsNotNone(self.pending())                # still waiting for a radius
        self.assertTrue(said and "radius" in said[-1], said)
        cad_draw.cancel(self.v)


class FlatBoxes(Base):
    """Two corners level with each other (snapping along a line puts them so): a rectangle,
    cloud, ellipse or mask with no height used to stop on an "Edit failed: rect is infinite
    or empty" message box."""

    def setUp(self):
        super().setUp()
        self.warned = []
        patch = mock.patch.object(QMessageBox, "warning",
                                  lambda *a, **k: self.warned.append(a[1:]))
        patch.start()
        self.addCleanup(patch.stop)

    def test_a_flat_box_goes_on_to_a_real_corner(self):
        for tool in ("rect", "cloud", "ellipse", "mask"):
            with self.subTest(tool=tool):
                self.v = self.view()
                self.v.set_tool(tool)
                self.click((100, 200))
                self.move((250, 200))
                self.click((250, 200))                  # level: nothing to draw yet
                self.assertEqual(self.warned, [])
                self.assertEqual(markups(self.v), [])
                self.assertIsNotNone(self.pending())    # still drawing it
                self.move((250, 260))
                self.click((250, 260))
                self.assertEqual(len(markups(self.v)), 1)
                self.assertIsNone(self.pending())

    def test_a_flat_drag_makes_nothing_quietly(self):
        self.v.set_tool("rect")
        self.v.apply_drag_tool(0, "rect", pymupdf.Point(100, 300), pymupdf.Point(300, 300),
                               False)
        self.v.apply_drag_tool(0, "ellipse", pymupdf.Point(100, 300), pymupdf.Point(100, 400),
                               False)
        self.assertEqual(self.warned, [])
        self.assertEqual(markups(self.v), [])


class FlatBoxesStandard(Base):
    MODE = "standard"

    def test_a_drag_along_a_line_makes_nothing_quietly(self):
        warned = []
        with mock.patch.object(QMessageBox, "warning", lambda *a, **k: warned.append(a[1:])):
            self.v.set_tool("cloud")
            self.drag((100, 300), (300, 300))
        self.assertEqual(warned, [])
        self.assertEqual(markups(self.v), [])


if __name__ == "__main__":
    unittest.main()
