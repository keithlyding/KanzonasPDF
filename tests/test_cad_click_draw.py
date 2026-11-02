"""CAD mode draws shapes click, move, click (as AutoCAD and Bluebeam do): a click starts the
shape, the preview follows the pointer with no button held, the next click ends it. A press,
drag and release still draws it. Escape or a right-click cancels; a quick second click that
arrives as a double-click still ends it; a click with a little shake is still a click.
Standard mode is unchanged: a click starts nothing, a drag draws. Also the Circle tool (from
the center to a point on the circle, an ellipse markup in a square; the radius can be typed on
the command line) and the Mask tool (a white rectangle with no outline).

Real mouse events (QTest) go through the page widget.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_cad_click_draw
"""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402
from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import annotations as A  # noqa: E402
from kanzonas import cad_draw, dialogs  # noqa: E402
from kanzonas.document_view import DocumentView  # noqa: E402

A_ = (120, 150)                     # where shapes start and end (page points, zoom 100%)
B_ = (260, 240)


def blank():
    d = pymupdf.open()
    d.new_page()
    d[0].insert_text((300, 500), "words to keep", fontsize=10)
    path = os.path.join(tempfile.mkdtemp(), "draw.pdf")
    d.save(path)
    return path


def markups(v, i=0):
    """[(kind, rect rounded, points rounded)] of the page's markups, in order."""
    page = v.doc[i]
    out = []
    for an in page.annots():
        m = A.read(an)
        pts = [(round(q.x, 1), round(q.y, 1)) for q in (m.get("points") or [])] if m else []
        r = an.rect
        out.append((m["kind"] if m else an.type[1],
                    tuple(round(x, 1) for x in (r.x0, r.y0, r.x1, r.y1)), pts))
    return out


class Base(unittest.TestCase):
    MODE = "cad"

    def setUp(self):
        for key in ("mouse_mode", "cad_select", "click_click", "lasso"):
            self.addCleanup(setattr, DocumentView, key, getattr(DocumentView, key))
        DocumentView.mouse_mode = self.MODE
        DocumentView.cad_select = self.MODE == "cad"
        DocumentView.click_click = DocumentView.lasso = self.MODE == "cad"
        self.v = self.view()

    def view(self):
        # (QTest moves the pointer itself: the window it lands on gets the move, so only the
        # view in use is shown; earlier tests' windows too are hidden)
        for old in APP.topLevelWidgets():
            if old.isVisible():
                old.hide()
        v = DocumentView(blank())
        self.addCleanup(v.close_doc)
        self.addCleanup(v.hide)
        v.snap_grid = v.snap_objects = v.snap_page = False
        v.resize(900, 1000)
        v.show()
        APP.processEvents()
        v.set_zoom(1.0)             # (after the first layout, which fits the page's width)
        APP.processEvents()
        return v

    def w(self, v=None):
        return (v or self.v).pages[0]

    def at(self, xy, v=None):
        w = self.w(v)
        p = w.to_screen_pt(pymupdf.Point(xy))
        return QPoint(round(p.x()), round(p.y()))

    def click(self, xy, v=None, button=Qt.LeftButton, mods=Qt.NoModifier):
        QTest.mouseClick(self.w(v), button, mods, self.at(xy, v))
        APP.processEvents()

    def move(self, xy, v=None):
        QTest.mouseMove(self.w(v), self.at(xy, v))
        APP.processEvents()

    def drag(self, a, b, v=None, mods=Qt.NoModifier):
        w = self.w(v)
        QTest.mousePress(w, Qt.LeftButton, mods, self.at(a, v))
        mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        QTest.mouseMove(w, self.at(mid, v))
        QTest.mouseMove(w, self.at(b, v))
        QTest.mouseRelease(w, Qt.LeftButton, mods, self.at(b, v), 300)
        APP.processEvents()

    def click_click(self, a, b, v=None):
        self.click(a, v)
        self.move(((a[0] + b[0]) / 2, (a[1] + b[1]) / 2), v)
        self.move(b, v)
        self.click(b, v)

    def pending(self, v=None):
        return cad_draw.pending(v or self.v)


def _texts():
    return mock.patch.object(dialogs, "get_text", lambda *a, **k: ("hello", True))


class ClickClick(Base):
    def both_ways(self, tool, a=A_, b=B_):
        """The markups a click, move, click makes, and those a drag makes (on another copy
        of the page)."""
        self.v.set_tool(tool)
        with _texts():
            self.click(a)
            self.assertIsNotNone(self.pending(), tool)
            self.move(b)
            self.assertEqual(markups(self.v), [], tool)         # (nothing yet: a preview)
            self.click(b)
        self.assertIsNone(self.pending())
        clicked = markups(self.v)
        other = self.view()
        other.set_tool(tool)
        with _texts():
            self.drag(a, b, other)
        dragged = markups(other)
        return clicked, dragged

    def test_the_same_markup_as_a_drag(self):
        for tool in ("line", "arrow", "rect", "cloud", "ellipse", "circle", "mask", "textbox",
                     "callout", "m_length", "m_radius"):
            with self.subTest(tool=tool):
                self.v = self.view()
                clicked, dragged = self.both_ways(tool)
                self.assertEqual(len(clicked), 1, (tool, clicked))
                self.assertEqual(clicked, dragged)

    def test_the_line_ends_where_clicked(self):
        clicked, _ = self.both_ways("line")
        kind, _r, pts = clicked[0]
        self.assertEqual(kind, "line")
        self.assertEqual([tuple(round(c) for c in p) for p in pts], [A_, B_])

    def test_the_preview_follows_the_pointer(self):
        self.v.set_tool("rect")
        self.click(A_)
        self.move((200, 200))
        a, b = cad_draw.points(self.w())
        self.assertEqual((round(a.x()), round(a.y())), A_)
        self.assertEqual((round(b.x()), round(b.y())), (200, 200))
        self.move((230, 180))
        _a, b = cad_draw.points(self.w())
        self.assertEqual((round(b.x()), round(b.y())), (230, 180))
        self.w().grab()                     # (it paints)

    def test_shift_makes_a_square(self):
        self.v.set_tool("rect")
        self.click(A_)
        w = self.w()
        QTest.mouseMove(w, self.at(B_))
        QTest.mouseClick(w, Qt.LeftButton, Qt.ShiftModifier, self.at(B_))
        (_k, r, _p), = markups(self.v)
        self.assertAlmostEqual(r[2] - r[0], r[3] - r[1], delta=4)

    def test_crop_and_link_boxes(self):
        v = self.v
        v.set_tool("crop")
        with mock.patch.object(DocumentView, "_ask_pages_scope", lambda *a: "this"), \
                mock.patch.object(DocumentView, "crop_pages") as crop:
            self.click_click(A_, B_)
        self.assertEqual(crop.call_count, 1)
        self.assertEqual(tuple(round(x) for x in crop.call_args[0][1]), A_ + B_)
        v.set_tool("link")
        with mock.patch.object(DocumentView, "add_link") as add:
            self.click_click(A_, B_)
        self.assertEqual(add.call_count, 1)
        self.assertEqual(tuple(round(x) for x in add.call_args[0][1]), A_ + B_)

    def test_a_shaky_click_is_still_a_click(self):
        self.v.set_tool("line")
        w = self.w()
        QTest.mousePress(w, Qt.LeftButton, Qt.NoModifier, self.at(A_))
        QTest.mouseMove(w, self.at((A_[0] + 4, A_[1] + 3)))
        QTest.mouseRelease(w, Qt.LeftButton, Qt.NoModifier, self.at((A_[0] + 5, A_[1] + 3)), 400)
        self.assertIsNotNone(self.pending())        # (held long, but moved under 10 px)
        cad_draw.cancel(self.v)
        # a quick one (under 250 ms) may move a little more
        QTest.mousePress(w, Qt.LeftButton, Qt.NoModifier, self.at(A_))
        QTest.mouseMove(w, self.at((A_[0] + 12, A_[1] + 4)))
        QTest.mouseRelease(w, Qt.LeftButton, Qt.NoModifier, self.at((A_[0] + 12, A_[1] + 4)), 20)
        self.assertIsNotNone(self.pending())
        cad_draw.cancel(self.v)
        # a real drag draws at once
        self.drag(A_, (A_[0] + 40, A_[1]))
        self.assertIsNone(self.pending())
        self.assertEqual(len(markups(self.v)), 1)

    def test_the_rule(self):
        from PySide6.QtCore import QPointF
        P = QPointF
        self.assertTrue(cad_draw.is_click(P(0, 0), P(6, 3), 900))
        self.assertFalse(cad_draw.is_click(P(0, 0), P(15, 0), 900))
        self.assertTrue(cad_draw.is_click(P(0, 0), P(15, 0), 100))
        self.assertFalse(cad_draw.is_click(P(0, 0), P(60, 0), 100))

    def test_a_double_click_doesnt_lose_it(self):
        self.v.set_tool("rect")
        w = self.w()
        # a click to start, then a quick second click a few pixels away: Qt makes it a
        # double-click (no second press): it ends the rectangle there
        QTest.mouseClick(w, Qt.LeftButton, Qt.NoModifier, self.at(A_))
        QTest.mouseDClick(w, Qt.LeftButton, Qt.NoModifier, self.at(B_))
        QTest.mouseRelease(w, Qt.LeftButton, Qt.NoModifier, self.at(B_))   # (as Qt sends)
        APP.processEvents()
        self.assertIsNone(self.pending())
        (kind, r, _p), = markups(self.v)
        self.assertEqual(kind, "rect")
        self.assertEqual(tuple(round(x) for x in r)[:2], (A_[0] - 1, A_[1] - 1))
        # a double-click on one spot starts a shape and keeps it (nothing to draw yet)
        QTest.mouseClick(w, Qt.LeftButton, Qt.NoModifier, self.at((300, 300)))
        QTest.mouseDClick(w, Qt.LeftButton, Qt.NoModifier, self.at((300, 300)))
        QTest.mouseRelease(w, Qt.LeftButton, Qt.NoModifier, self.at((300, 300)))
        APP.processEvents()
        self.assertIsNotNone(self.pending())
        self.move((350, 340))
        self.click((350, 340))
        self.assertEqual(len(markups(self.v)), 2)

    def test_escape_and_right_click_cancel(self):
        v = self.v
        v.set_tool("line")
        self.click(A_)
        self.move(B_)
        QTest.keyClick(v, Qt.Key_Escape)
        self.assertIsNone(self.pending())
        self.assertEqual(v.tool, "line")            # (Escape took the shape, not the tool)
        self.click(B_)                              # a new start, not an end
        self.assertIsNotNone(self.pending())
        self.assertEqual(markups(v), [])
        self.click((300, 300), button=Qt.RightButton)
        self.assertIsNone(self.pending())
        self.assertEqual(markups(v), [])

    def test_another_tool_drops_it(self):
        self.v.set_tool("line")
        self.click(A_)
        self.v.set_tool("rect")
        self.assertIsNone(self.pending())
        self.click(B_)                              # (starts a rectangle there)
        self.assertEqual(markups(self.v), [])

    def test_zoom_between_the_clicks_keeps_the_first_point(self):
        v = self.v
        v.set_tool("line")
        self.click(A_)
        v.set_zoom(2.0)
        APP.processEvents()
        self.move(B_)
        self.click(B_)
        (_k, _r, pts), = markups(v)
        self.assertEqual([tuple(round(c) for c in p) for p in pts], [A_, B_])

    def test_one_point_tools_unchanged(self):
        v = self.v
        v.set_tool("m_count")
        self.click(A_)
        self.assertIsNone(self.pending())
        self.assertEqual(len(markups(v)), 1)

    def test_eraser_click_on_a_markup_erases_it(self):
        v = self.v
        v.set_tool("rect")
        self.drag(A_, B_)
        self.assertEqual(len(markups(v)), 1)
        v.set_tool("eraser")
        self.click((A_[0], (A_[1] + B_[1]) / 2))    # on its left edge
        self.assertIsNone(self.pending())
        self.assertEqual(markups(v), [])

    def test_text_box_click_on_the_same_spot(self):
        v = self.v
        v.set_tool("textbox")
        with _texts():
            self.click(A_)
            self.click(A_)          # (QTest spaces separate clicks out: no double-click)
        (kind, r, _p), = markups(v)
        self.assertEqual(kind, "textbox")
        self.assertAlmostEqual(r[2] - r[0], 200, delta=2)   # the default size, as a click makes

    def test_circle_from_the_center(self):
        v = self.v
        v.set_tool("circle")
        self.click((200, 200))
        self.move((230, 240))
        self.click((230, 240))
        (kind, r, _p), = markups(v)
        self.assertEqual(kind, "ellipse")
        x0, y0, x1, y1 = r
        self.assertAlmostEqual((x0 + x1) / 2, 200, delta=1)
        self.assertAlmostEqual((y0 + y1) / 2, 200, delta=1)
        self.assertAlmostEqual(x1 - x0, 100, delta=3)      # radius 50
        self.assertAlmostEqual(y1 - y0, 100, delta=3)

    def test_circle_typed_radius(self):
        v = self.v
        v.set_tool("circle")
        self.click((200, 200))
        self.assertTrue(cad_draw.typed(v, "1"))     # 1 inch on paper (no scale set) = 72 pt
        (kind, r, _p), = markups(v)
        self.assertEqual(kind, "ellipse")
        self.assertAlmostEqual(r[2] - r[0], 144, delta=3)
        self.assertFalse(cad_draw.typed(v, "2"))    # (no circle in progress)

    def test_mask_hides_what_is_under_it(self):
        v = self.v
        v.set_tool("mask")
        self.click_click((290, 480), (420, 510))
        an = next(v.doc[0].annots())
        self.assertEqual(an.colors.get("fill"), [1.0, 1.0, 1.0])
        self.assertFalse(an.colors.get("stroke"))
        pix = v.doc[0].get_pixmap(clip=pymupdf.Rect(295, 485, 415, 505))
        self.assertTrue(pix.is_unicolor)            # (the words are covered)


class Standard(Base):
    MODE = "standard"

    def test_a_click_starts_nothing(self):
        v = self.v
        for tool in ("line", "rect", "circle", "m_length"):
            v.set_tool(tool)
            self.click(A_)
            self.assertIsNone(self.pending(), tool)
            self.move(B_)
            self.click(B_)
            self.assertEqual(markups(v), [], tool)

    def test_a_drag_draws(self):
        v = self.v
        v.set_tool("line")
        self.drag(A_, B_)
        (_k, _r, pts), = markups(v)
        self.assertEqual([tuple(round(c) for c in p) for p in pts], [A_, B_])
        v.set_tool("circle")
        self.drag((200, 300), (230, 340))
        self.assertEqual(markups(v)[1][0], "ellipse")


class Hand(Standard):
    MODE = "hand"


class Ribbon(unittest.TestCase):
    def test_cad_tab_split_buttons(self):
        from PySide6.QtWidgets import QToolButton
        from kanzonas.main_window import MainWindow
        from kanzonas.ribbon import SplitButton
        w = MainWindow()
        self.addCleanup(lambda: (setattr(w, "_close_confirmed", True), w.close()))
        t = w.tool_actions
        buttons = {b.defaultAction(): b for b in w._cad_tab.findChildren(SplitButton)}
        rect = buttons[t["rect"]]
        self.assertEqual([a for a in rect.menu().actions()],
                         [t["rect"], t["cloud"], t["polygon"], t["mask"]])
        # (Circle shares its button with Arc once that tool exists)
        self.assertIn(t["circle"], buttons if "arc" in t else
                      {b.defaultAction() for b in w._cad_tab.findChildren(QToolButton)})
        # the face shows the tool that's on
        t["cloud"].trigger()
        self.assertIs(rect.defaultAction(), t["cloud"])
        t["rect"].trigger()
        self.assertIs(rect.defaultAction(), t["rect"])
        reach = set()
        for b in w._cad_tab.findChildren(QToolButton):
            reach.add(b.defaultAction())
            if b.menu() is not None:
                reach.update(b.menu().actions())
        for k in ("circle", "mask", "stamp", "image", "ink", "m_angle", "m_volume"):
            self.assertIn(t[k], reach, k)


if __name__ == "__main__":
    unittest.main()
