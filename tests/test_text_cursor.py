"""The pointer over the page, outside the CAD mouse mode: Select shows the text cursor over
text (a drag from there selects text) and the arrow elsewhere. The Hand only views: always a
hand (the closed hand while it moves the page, a pointing hand on a link), and it never
selects text, markups or objects. In the Standard (Select) mouse mode the Hand picked is
Select: nothing there drags the page. Space held: any tool drags the page. In CAD mode the
plus (or the arrow), no text cursor (the owner, 12 Nov: not unless typing or with a text tool).

The owner, 18 Nov 2026: "When I'm selecting text (not in cad mouse), the cursor is a hand
instead of the text cursor"; 19 Nov: "I want the hand to always show no matter what.
Selecting text or objects while in hand should not be doable. Hand is like a view only type
thing".

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_text_cursor
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402
from PySide6.QtCore import QEvent, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QEnterEvent, QMouseEvent  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import main_window, mouse_modes  # noqa: E402

P = pymupdf.Point
ON_TEXT = (P(110, 94), P(200, 95))
BLANK = (P(110, 400), P(200, 401))
NOTE = pymupdf.Rect(300, 500, 400, 560)


def sheet():
    d = pymupdf.open()
    p = d.new_page()
    p.insert_text((100, 100), "Hello world some text here", fontsize=20)
    p.insert_text((300, 540), "Under the note", fontsize=14)
    p.insert_text((1, 300), "EDGE", fontsize=12)
    a = p.add_rect_annot(NOTE)
    a.set_colors(stroke=(1, 0, 0), fill=(1, 1, 0))      # (filled: a click inside takes it)
    a.update()
    path = os.path.join(tempfile.mkdtemp(), "sheet.pdf")
    d.save(path)
    return path


class Cursor(unittest.TestCase):
    mode = "standard"

    def setUp(self):
        w = self.w = main_window.MainWindow()
        keys = ("mouse_mode", "mouse_before_cad")
        old = {k: w.settings.value(k) for k in keys}

        def back():
            for k, val in old.items():
                w.settings.setValue(k, val) if val is not None else w.settings.remove(k)
            mouse_modes.apply(w.settings)
        self.addCleanup(back)
        self.addCleanup(lambda: [setattr(x, "_close_confirmed", True) or x.close()
                                 for x in main_window.windows()])
        w.resize(1200, 900)
        w.show()
        w.open_file(sheet())
        APP.processEvents()
        v = self.v = w.view()
        self.addCleanup(lambda: setattr(v, "dirty", False))
        w.set_mouse_mode(self.mode)
        v.set_zoom(1.0)
        APP.processEvents()
        self.page = v.pages[0]

    def use(self, tool):
        self.w.set_tool(tool)
        APP.processEvents()

    def move(self, q, buttons=Qt.NoButton):
        w = self.page
        w.mouseMoveEvent(QMouseEvent(QEvent.MouseMove, q, w.mapToGlobal(q), Qt.NoButton,
                                     buttons, Qt.NoModifier))
        APP.processEvents()

    def hover(self, pt):
        self.move(self.page.to_screen_pt(pt))
        return self.page.cursor().shape()

    def drag(self, a, b):
        """A drag from page point a to b; True when it moved the page."""
        v = self.v
        a, b = self.page.to_screen_pt(a), self.page.to_screen_pt(b)
        self.move(a)
        before = (v.horizontalScrollBar().value(), v.verticalScrollBar().value())
        QTest.mousePress(self.page, Qt.LeftButton, Qt.NoModifier, a.toPoint())
        for k in range(1, 5):
            self.move(QPointF(a + (b - a) * k / 4), Qt.LeftButton)
        QTest.mouseRelease(self.page, Qt.LeftButton, Qt.NoModifier, b.toPoint())
        APP.processEvents()
        return (v.horizontalScrollBar().value(), v.verticalScrollBar().value()) != before


class SelectTests:
    """Select, in the Standard and Hand mouse modes."""

    def test_select_shows_the_text_cursor_over_text_and_the_arrow_elsewhere(self):
        self.use("select")
        self.assertEqual(self.hover(ON_TEXT[0]), Qt.IBeamCursor)
        self.assertEqual(self.hover(BLANK[0]), Qt.ArrowCursor)

    def test_select_over_a_markup_shows_the_move_arrows(self):
        self.use("select")
        self.assertEqual(self.hover(P(350, 535)), Qt.SizeAllCursor)

    def test_no_text_cursor_left_behind_from_the_gray_beside_the_page(self):
        self.gray_then_blank_paper("select")

    def gray_then_blank_paper(self, tool):
        self.use(tool)
        w = self.page
        canvas = w.parentWidget()
        edge = w.to_screen_pt(P(3, 296))                    # ("EDGE", at the page's left edge)
        gray = QPointF(w.x() - 2, w.y() + edge.y())         # (the gray just left of it)
        canvas.mouseMoveEvent(QMouseEvent(QEvent.MouseMove, gray, canvas.mapToGlobal(gray),
                                          Qt.NoButton, Qt.NoButton, Qt.NoModifier))
        APP.processEvents()
        self.assertEqual(canvas.cursor().shape(), Qt.IBeamCursor)   # (text right there)
        inside = QPointF(w.to_screen_pt(BLANK[0]))
        QApplication.sendEvent(w, QEnterEvent(inside, w.mapToGlobal(inside),
                                              w.mapToGlobal(inside)))
        self.assertEqual(self.hover(BLANK[0]), Qt.ArrowCursor)


class StandardMode(SelectTests, Cursor):
    """The owner, 18 Nov 2026: "When in select mode, the hand should not drag the page": the
    Hand picked in the Standard (Select) mouse mode is Select."""

    def test_the_hand_picked_is_select(self):
        said = []
        self.w.statusBar().messageChanged.connect(said.append)
        self.use("hand")
        self.assertEqual(self.w.tool, "select")
        self.assertEqual(self.v.tool, "select")
        self.assertTrue(self.w.tool_actions["select"].isChecked())
        self.assertTrue(any("doesn't move the page" in m for m in said), said)

    def test_a_drag_on_blank_paper_never_moves_the_page(self):
        self.v.set_zoom(3.0)
        APP.processEvents()
        self.use("hand")
        self.v.ensureVisible(self.page.x() + 600, self.page.y() + 1200, 200, 200)
        APP.processEvents()
        self.assertFalse(self.drag(*BLANK))

    def test_a_drag_from_text_selects_it(self):
        self.use("hand")
        self.assertFalse(self.drag(*ON_TEXT))
        self.assertEqual(self.v.selected_text(), "Hello world")

    def test_the_hand_mode_still_gets_its_hand(self):
        self.w.set_mouse_mode("hand")
        APP.processEvents()
        self.use("hand")
        self.assertEqual(self.v.tool, "hand")


class HandMode(SelectTests, Cursor):
    """The Hand only views (the owner, 19 Nov 2026: "I want the hand to always show no matter
    what. Selecting text or objects while in hand should not be doable"): an open hand over
    paper, text and markups, the closed hand while it moves the page, a pointing hand on a
    link; a drag anywhere moves the page and selects nothing."""
    mode = "hand"

    def test_always_the_open_hand(self):
        self.use("hand")
        for where in (BLANK[0], ON_TEXT[0], P(350, 535)):
            with self.subTest(where=where):
                self.assertEqual(self.hover(where), Qt.OpenHandCursor)

    def test_the_closed_hand_while_it_moves_the_page(self):
        self.v.set_zoom(3.0)
        APP.processEvents()
        self.use("hand")
        a = self.page.to_screen_pt(BLANK[0])
        b = a + QPointF(-40, -40)
        self.move(a)
        QTest.mousePress(self.page, Qt.LeftButton, Qt.NoModifier, a.toPoint())
        self.move(b, Qt.LeftButton)
        self.assertEqual(self.v.viewport().cursor().shape(), Qt.ClosedHandCursor)
        QTest.mouseRelease(self.page, Qt.LeftButton, Qt.NoModifier, b.toPoint())
        APP.processEvents()
        self.assertEqual(self.v.viewport().cursor().shape(), Qt.OpenHandCursor)

    def test_a_drag_from_text_moves_the_page_and_selects_nothing(self):
        self.v.set_zoom(3.0)
        APP.processEvents()
        self.use("hand")
        self.v.ensureVisible(self.page.x() + 300, self.page.y() + 280, 300, 300)
        APP.processEvents()
        self.assertTrue(self.drag(*ON_TEXT))
        self.assertEqual(self.v.selected_text(), "")

    def test_a_click_on_a_markup_selects_nothing(self):
        self.use("hand")
        q = self.page.to_screen_pt(P(350, 535)).toPoint()
        QTest.mouseClick(self.page, Qt.LeftButton, Qt.NoModifier, q)
        APP.processEvents()
        self.assertIsNone(self.v.selection)

    def test_a_double_click_selects_and_edits_nothing(self):
        self.use("hand")
        for where in (P(120, 94), P(350, 535)):
            q = self.page.to_screen_pt(where).toPoint()
            QTest.mouseDClick(self.page, Qt.LeftButton, Qt.NoModifier, q)
            APP.processEvents()
        self.assertEqual(self.v.selected_text(), "")
        self.assertIsNone(self.v.selection)
        self.assertIsNone(self.v._inline)

    def test_the_hand_options_are_gone(self):
        self.assertEqual([k for k, _l, _d in mouse_modes.options("hand")],
                         ["free_pan", "page_wheel"])


class SpaceToPan(Cursor):
    """Hold Space and drag: the page moves, with any tool (as in Acrobat); let go of Space,
    the tool is back."""
    mode = "standard"

    def test_space_held_moves_the_page_with_select(self):
        self.v.set_zoom(3.0)
        APP.processEvents()
        self.use("select")
        self.v.ensureVisible(self.page.x() + 300, self.page.y() + 1200, 300, 300)
        APP.processEvents()
        QTest.keyPress(self.v, Qt.Key_Space)
        self.assertEqual(self.v.viewport().cursor().shape(), Qt.OpenHandCursor)
        self.assertTrue(self.drag(*ON_TEXT))
        self.assertEqual(self.v.selected_text(), "")
        QTest.keyRelease(self.v, Qt.Key_Space)
        self.assertFalse(self.v.space_pan)
        self.assertEqual(self.v.viewport().cursor().shape(), Qt.ArrowCursor)

    def test_without_space_select_selects_again(self):
        self.use("select")
        QTest.keyPress(self.v, Qt.Key_Space)
        QTest.keyRelease(self.v, Qt.Key_Space)
        self.assertFalse(self.drag(*ON_TEXT))
        self.assertEqual(self.v.selected_text(), "Hello world")


class CadMode(Cursor):
    mode = "cad"

    def test_no_text_cursor_with_select_or_the_hand(self):
        self.use("select")
        self.assertNotEqual(self.hover(ON_TEXT[0]), Qt.IBeamCursor)
        self.use("hand")
        self.assertEqual(self.hover(ON_TEXT[0]), Qt.OpenHandCursor)

    def test_the_hand_only_moves_the_page(self):
        self.use("hand")
        self.drag(*ON_TEXT)
        self.assertEqual(self.v.selected_text(), "")

    def test_text_tools_keep_the_plus(self):
        self.use("highlight")
        self.assertEqual(self.hover(ON_TEXT[0]), Qt.CrossCursor)


if __name__ == "__main__":
    unittest.main()
