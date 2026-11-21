"""A selected markup shows it's selected: a box (white under dashed blue) around it on the
page. A count marker or a dot is one point, and its outline was a box of no size hidden under
its dot, so nothing showed; in CAD mode the box around several of them in a row had no
height (a thin band through them). Now they're outlined by the box they're drawn in.

cloydcc-dev, issue #107, 21 Nov 2026: "there is no box or any visible indicator on what is
selected on the page so box or an ant pattern will be great for visibility".
(A dot has a small size of its own; it gets the same white-under-blue outline.)

Real mouse events go through the page widget; what's on the screen is read from its pixels.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_selection_visible
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QRect, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402

from tests.test_cad_click_draw import APP, Base  # noqa: E402

ROW = [(100, 100), (160, 100), (220, 100)]


class Visible(Base):
    MODE = "standard"
    TOOL = "m_count"

    def setUp(self):
        super().setUp()
        self.v.set_zoom(1.5)
        APP.processEvents()
        self.v.set_tool(self.TOOL)
        for xy in ROW:
            self.click(xy)
        self.v.set_tool("select")
        APP.processEvents()

    def picture(self):
        """The page around the middle marker, as shown."""
        c = self.at(ROW[1])
        img = self.w().grab(QRect(c.x() - 40, c.y() - 40, 80, 80)).toImage()
        return {(x, y): img.pixelColor(x, y).name() for x in range(img.width())
                for y in range(img.height())}

    def outline_pixels(self, before, after):
        """Pixels the selection turned the selection's blue (the dashed line)."""
        return [xy for xy, c in after.items() if c != before[xy] and c == "#0078d7"]

    def select_middle(self):
        self.click(ROW[1])
        self.assertEqual(len(self.v.selected_xrefs()), 1)

    def test_one_selected_shows_a_box(self):
        before = self.picture()
        self.select_middle()
        self.assertGreater(len(self.outline_pixels(before, self.picture())), 40)

    def test_its_box_is_the_one_it_is_drawn_in(self):
        self.select_middle()
        m = self.v.selected_model
        box = self.w()._shown_box(m)
        self.assertEqual(box, m["rect"])
        self.assertGreater(box.width, 5)
        self.assertGreater(box.height, 5)

    def test_the_selection_goes_away_again(self):
        before = self.picture()
        self.select_middle()
        self.v.clear_selection()
        APP.processEvents()
        self.assertEqual(self.outline_pixels(before, self.picture()), [])


class VisibleInCadMode(Visible):
    MODE = "cad"

    def test_the_box_around_several_has_their_height(self):
        from kanzonas import cad_select
        w = self.w()
        self.click((70, 70))                    # (a window around the row: click, click)
        self.move((150, 120))
        self.click((250, 130))
        self.assertEqual(len(self.v.selected_xrefs()), 3)
        box = cad_select.resize_box(w)
        self.assertIsNotNone(box)
        self.assertGreater(box.height(), 15 * self.v.zoom)


class DotVisible(Visible):
    TOOL = "dot"

    def test_its_box_is_the_one_it_is_drawn_in(self):
        # (a dot has a size of its own: its bounds, not its box with the number)
        self.select_middle()
        box = self.w()._shown_box(self.v.selected_model)
        self.assertGreater(box.width, 3)
        self.assertGreater(box.height, 3)


class DotVisibleInCadMode(VisibleInCadMode):
    TOOL = "dot"

    def test_its_box_is_the_one_it_is_drawn_in(self):
        self.select_middle()
        box = self.w()._shown_box(self.v.selected_model)
        self.assertGreater(box.width, 3)
        self.assertGreater(box.height, 3)

    def test_the_box_around_several_has_their_height(self):
        from kanzonas import cad_select
        self.click((70, 70))
        self.move((150, 120))
        self.click((250, 130))
        self.assertEqual(len(self.v.selected_xrefs()), 3)
        self.assertGreater(cad_select.resize_box(self.w()).height(), 3 * self.v.zoom)


class Unchanged(Base):
    """A markup with a size keeps the box it had: a rectangle's outline is its own box."""
    MODE = "standard"

    def test_a_rectangle(self):
        v = self.v
        v.set_tool("rect")
        self.drag((100, 100), (200, 160))
        v.set_tool("select")
        self.click((100, 130))                  # (on its left side)
        m = v.selected_model
        self.assertEqual(m["kind"], "rect")
        from kanzonas import annotations as A
        self.assertEqual(self.w()._shown_box(m), A.bounds(m))


if __name__ == "__main__":
    unittest.main()
