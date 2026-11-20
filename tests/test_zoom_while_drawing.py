"""A zoom in the middle of drawing a shape keeps what's drawn so far where it was clicked on
the page: a polygon's corners, a polyline's or a measurement's points, and the first corner
of a shape drawn click, move, click. The points are held in widget pixels, and a zoom (or new
room around the page) moves the page under them.

The owner, 20 Nov 2026: "I was in the middle of drawing a polygon and had to zoom. The whole
shape moved on me."

Real mouse events (QTest) go through the page widget.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_zoom_while_drawing
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402

from tests.test_cad_click_draw import APP, Base, markups  # noqa: E402

CORNERS = [(100, 100), (300, 120), (320, 300), (120, 320)]


class Polygon(Base):
    MODE = "standard"

    def near(self, got, want, tol=1.5):
        self.assertEqual(len(got), len(want), (got, want))
        for (gx, gy), (wx, wy) in zip(got, want):
            self.assertLess(abs(gx - wx) + abs(gy - wy), tol, (got, want))

    def draw(self, tool, zoom_after, zooms=(2.0,)):
        """Clicks CORNERS with tool, zooming (to each of zooms in turn) after zoom_after
        clicks, then ends the shape with a double-click on the last corner (a click, then
        the double-click Qt sends)."""
        v = self.v
        v.set_tool(tool)
        for n, xy in enumerate(CORNERS):
            if n == zoom_after:
                for z in zooms:
                    v.set_zoom(z)
                    APP.processEvents()
            self.click(xy)
        QTest.mouseDClick(self.w(), Qt.LeftButton, Qt.NoModifier, self.at(CORNERS[-1]))
        APP.processEvents()
        return markups(v)

    def test_a_polygon_zoomed_in_halfway(self):
        got = self.draw("polygon", zoom_after=2)
        self.assertEqual(len(got), 1)
        self.near(got[0][2], CORNERS)

    def test_zoomed_out_and_in_again(self):
        got = self.draw("polygon", zoom_after=1, zooms=(0.5, 1.7))
        self.near(got[0][2], CORNERS)

    def test_a_polyline(self):
        got = self.draw("polyline", zoom_after=2, zooms=(1.5,))
        self.near(got[0][2], CORNERS)

    def test_the_preview_follows_the_page(self):
        v = self.v
        v.set_tool("polygon")
        for xy in CORNERS[:2]:
            self.click(xy)
        v.set_zoom(2.5)
        APP.processEvents()
        w = self.w()
        self.near([(round(q.x, 1), round(q.y, 1)) for q in map(w.to_pdf, w._poly)],
                  CORNERS[:2])

    def test_no_zoom_no_change(self):
        got = self.draw("polygon", zoom_after=99)
        self.near(got[0][2], CORNERS)


class ClickClick(Base):
    """CAD mode's click, move, click: the first corner, clicked before the zoom, stays."""
    MODE = "cad"

    def test_a_rectangle_started_before_a_zoom(self):
        v = self.v
        v.set_tool("rect")
        self.click((120, 150))
        v.set_zoom(1.8)
        APP.processEvents()
        self.move((200, 200))
        self.move((260, 240))
        self.click((260, 240))
        got = markups(v)
        self.assertEqual(len(got), 1)
        x0, y0, x1, y1 = got[0][1]
        self.assertLess(abs(x0 - 120) + abs(y0 - 150), 4, got)     # (its border's width)
        self.assertLess(abs(x1 - 260) + abs(y1 - 240), 4, got)


if __name__ == "__main__":
    unittest.main()
