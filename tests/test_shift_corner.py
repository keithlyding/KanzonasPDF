"""Shift while dragging a corner of a polygon (or a polyline, or a closed measurement) keeps
its sides straight: near a spot where both its sides run straight (0, 45 or 90 degrees) from
the corners before and after it, it lands there (a square corner); elsewhere it slides along
the nearest straight side from one of them, which gets longer or shorter. Before, only the
side to the corner before it was kept straight, and a polyline's first point lined up with
its last one.

The owner, 20 Nov 2026: "when lengthening or shortening lines of the polygon (to make them
connect straight and at right angles), holding shift did not work to make the lines
straight when I adjusted them".

Real mouse events go through the page widget (Shift held during the drag, as a person does).

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_shift_corner
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QMouseEvent  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402

from tests.test_cad_click_draw import APP, Base, markups  # noqa: E402

SQUARE_BUT_ONE = [(100, 100), (300, 100), (310, 290), (100, 300)]


class Corner(Base):
    MODE = "standard"

    def shape(self, tool, pts):
        v = self.v
        v.set_tool(tool)
        for xy in pts:
            self.click(xy)
        QTest.mouseDClick(self.w(), Qt.LeftButton, Qt.NoModifier, self.at(pts[-1]))
        APP.processEvents()
        v.set_tool("select")
        a, b = pts[0], pts[1]
        self.click(((a[0] + b[0]) / 2, (a[1] + b[1]) / 2))          # (on its first side)
        self.assertTrue(v.selected_xrefs())

    def drag_corner(self, start, end, mods=Qt.ShiftModifier):
        """Presses on the corner at start, then drags it to end with mods held."""
        w = self.w()
        QTest.mousePress(w, Qt.LeftButton, Qt.NoModifier, self.at(start))
        mid = ((start[0] + end[0]) / 2, (start[1] + end[1]) / 2)
        for xy in (mid, end):
            p = QPointF(self.at(xy))
            w.mouseMoveEvent(QMouseEvent(QEvent.MouseMove, p, w.mapToGlobal(p), Qt.NoButton,
                                         Qt.LeftButton, mods))
        p = QPointF(self.at(end))
        w.mouseReleaseEvent(QMouseEvent(QEvent.MouseButtonRelease, p, w.mapToGlobal(p),
                                        Qt.LeftButton, Qt.NoButton, mods))
        APP.processEvents()
        return markups(self.v)[0][2]

    def near(self, got, want, tol=1.5):
        for (gx, gy), (wx, wy) in zip(got, want):
            self.assertLess(abs(gx - wx) + abs(gy - wy), tol, (got, want))

    def test_a_square_corner_near_one(self):
        self.shape("polygon", SQUARE_BUT_ONE)
        got = self.drag_corner((310, 290), (318, 305))
        self.near(got, [(100, 100), (300, 100), (300, 300), (100, 300)])

    def test_away_from_one_a_side_stays_straight_and_gets_longer(self):
        self.shape("polygon", SQUARE_BUT_ONE)
        got = self.drag_corner((310, 290), (305, 200))
        self.near(got, [(100, 100), (300, 100), (300, 200), (100, 300)])

    def test_the_first_corner_of_a_polygon_has_the_last_as_a_neighbor(self):
        self.shape("polygon", [(110, 95), (300, 100), (300, 300), (100, 300)])
        got = self.drag_corner((110, 95), (92, 108))
        self.near(got, [(100, 100), (300, 100), (300, 300), (100, 300)])

    def test_a_polylines_end_has_one_neighbor(self):
        self.shape("polyline", [(100, 100), (300, 100), (300, 300)])
        got = self.drag_corner((100, 100), (90, 108))
        self.near(got, [(90, 100), (300, 100), (300, 300)])

    def test_without_shift_the_corner_goes_where_it_is_dragged(self):
        self.shape("polygon", SQUARE_BUT_ONE)
        got = self.drag_corner((310, 290), (318, 305), mods=Qt.NoModifier)
        self.near(got, [(100, 100), (300, 100), (318, 305), (100, 300)])


class CornerInCadMode(Corner):
    MODE = "cad"


if __name__ == "__main__":
    unittest.main()
