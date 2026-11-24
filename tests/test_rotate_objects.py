"""Turning the page's own pictures, shapes and groups (Edit objects, and CAD mode): drag the
round handle above the selection (in CAD mode: click it, move, click; Shift: 15 degree
steps), or right-click > Rotate by an
angle... and type the angle (degrees, counterclockwise, as a markup's Rotation). One undo
step; text in the selection has no handle (it's moved, not turned).

The owner, 16 Nov 2026: "I need to be able to change the orientation of objects ... I'd like
to be able to grab and drag and also put in an actual value".

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_rotate_objects
"""
import math
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402
from PySide6.QtCore import QEvent, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QMouseEvent  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QInputDialog  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import main_window, mouse_modes  # noqa: E402
from kanzonas.document_view import DocumentView  # noqa: E402

# a level bar 200 wide and 20 tall, centered on (300, 300)
BAR = pymupdf.Rect(200, 290, 400, 310)
CENTER = pymupdf.Point(300, 300)


def sheet(text=False):
    d = pymupdf.open()
    p = d.new_page()
    p.draw_rect(BAR, color=(0, 0, 1), fill=(0, 0, 1), width=0)
    if text:
        p.insert_text((100, 100), "NOTE", fontsize=14)
    path = os.path.join(tempfile.mkdtemp(), "sheet.pdf")
    d.save(path)
    return path


def bar_box(page):
    """The bar's box as drawn now (its corners, wherever it turned)."""
    box = None
    for d in page.get_drawings():
        box = pymupdf.Rect(d["rect"]) if box is None else box | d["rect"]
    return box


class Turning(unittest.TestCase):
    cad = False
    text = False

    def setUp(self):
        for k in ("snap_objects", "snap_page", "snap_grid"):
            self.addCleanup(setattr, DocumentView, k, getattr(DocumentView, k))
            setattr(DocumentView, k, False)
        self.addCleanup(setattr, DocumentView, "_turn_typed", DocumentView._turn_typed)
        w = self.w = main_window.MainWindow()
        old = {k: w.settings.value(k) for k in ("mouse_mode", "mouse_before_cad")}

        def back():
            for k, val in old.items():
                w.settings.setValue(k, val) if val is not None else w.settings.remove(k)
            mouse_modes.apply(w.settings)
        self.addCleanup(back)
        self.addCleanup(lambda: [setattr(x, "_close_confirmed", True) or x.close()
                                 for x in main_window.windows()])
        w.resize(1200, 1000)
        w.show()
        w.open_file(sheet(self.text))
        APP.processEvents()
        v = self.v = w.view()
        self.addCleanup(lambda: setattr(v, "dirty", False))
        if self.cad:
            w.set_mouse_mode("cad")
        w.set_tool("editobjects")
        v.set_zoom(1.0)
        APP.processEvents()
        self.page = v.pages[0]
        v.ensureVisible(self.page.x() + 300, self.page.y() + 300, 400, 400)
        APP.processEvents()
        # (the shape, and the text with it when there is some, as a CAD selection takes both)
        v.select_objects(0, list(v.content_objects(0).items) +
                         (list(v.text_objects(0)) if self.text else []))
        APP.processEvents()

    def handle(self):
        return self.page._objects_handles().get("rot")

    def drag(self, a, b, mods=Qt.NoModifier):
        """Press at a, move to b, release; in CAD mode (1.17: no button held there) a click
        at a, the move with no button held, and a click at b."""
        w = self.page
        a, b = QPointF(a), QPointF(b)
        held = Qt.NoButton if self.cad else Qt.LeftButton
        if self.cad:
            QTest.mouseClick(w, Qt.LeftButton, Qt.NoModifier, a.toPoint())
        else:
            QTest.mousePress(w, Qt.LeftButton, Qt.NoModifier, a.toPoint())
        for k in range(1, 6):
            q = a + (b - a) * k / 5
            w.mouseMoveEvent(QMouseEvent(QEvent.MouseMove, q, w.mapToGlobal(q), Qt.NoButton,
                                         held, mods))
        if self.cad:
            QTest.mouseClick(w, Qt.LeftButton, mods, b.toPoint())
        else:
            QTest.mouseRelease(w, Qt.LeftButton, mods, b.toPoint())
        APP.processEvents()

    def turn_by_dragging(self, ccw_degrees, mods=Qt.NoModifier):
        """Drag the round handle around the selection's middle by ccw_degrees (as shown)."""
        h = self.handle().center()
        c = self.page.to_screen_pt(CENTER)
        r = math.hypot(h.x() - c.x(), h.y() - c.y())
        a0 = math.atan2(h.y() - c.y(), h.x() - c.x())
        a1 = a0 - math.radians(ccw_degrees)         # (screen y down: counterclockwise is -)
        end = QPointF(c.x() + r * math.cos(a1), c.y() + r * math.sin(a1))
        self.drag(h, end, mods)


class DragTheRoundHandle(Turning):
    def test_the_handle_is_above_the_selection(self):
        h = self.handle()
        self.assertIsNotNone(h)
        box = self.page.to_screen(self.v.selected_objects_rect())
        self.assertLess(h.center().y(), box.top())
        self.assertAlmostEqual(h.center().x(), box.center().x(), 0)

    def test_a_quarter_turn_stands_the_bar_up(self):
        self.turn_by_dragging(90)
        box = bar_box(self.v.doc[0])
        self.assertAlmostEqual(box.width, 20, 0)
        self.assertAlmostEqual(box.height, 200, 0)
        self.assertAlmostEqual((box.x0 + box.x1) / 2, 300, 0)       # (about its middle)
        self.assertAlmostEqual((box.y0 + box.y1) / 2, 300, 0)

    def test_shift_turns_in_15_degree_steps(self):
        self.turn_by_dragging(37, Qt.ShiftModifier)                 # (to 30 degrees)
        box = bar_box(self.v.doc[0])
        want_w = 200 * math.cos(math.radians(30)) + 20 * math.sin(math.radians(30))
        self.assertAlmostEqual(box.width, want_w, 0)

    def test_the_turn_is_shown_while_dragging_then_one_undo(self):
        said = []
        self.v.statusMessage.connect(said.append)
        self.turn_by_dragging(45)
        self.assertTrue(any("Rotate: 45" in s for s in said), said[-3:])
        self.assertGreater(bar_box(self.v.doc[0]).height, 100)
        self.v.undo()
        self.assertEqual(bar_box(self.v.doc[0]), BAR)

    def test_a_click_on_the_handle_turns_nothing(self):
        rev = self.v.revision
        h = self.handle().center().toPoint()
        QTest.mouseClick(self.page, Qt.LeftButton, Qt.NoModifier, h)
        APP.processEvents()
        self.assertEqual(self.v.revision, rev)
        self.assertEqual(bar_box(self.v.doc[0]), BAR)


class TypeTheAngle(Turning):
    def typed(self, deg, ok=True):
        with mock.patch.object(QInputDialog, "getDouble", return_value=(deg, ok)) as ask:
            self.v.rotate_objects_by()
        return ask

    def test_counterclockwise_as_a_markups_rotation(self):
        self.typed(30)
        page = self.v.doc[0]
        # the bar's right end goes up (counterclockwise as shown)
        pts = [q for d in page.get_drawings() for it in d["items"] for q in it[1:]
               if isinstance(q, pymupdf.Point)]
        rightmost = max(pts, key=lambda q: q.x)
        self.assertLess(rightmost.y, 300)              # (PyMuPDF's y grows downward)

    def test_minus_90_turns_it_clockwise_a_quarter(self):
        self.typed(-90)
        box = bar_box(self.v.doc[0])
        self.assertAlmostEqual(box.width, 20, 0)
        self.assertAlmostEqual(box.height, 200, 0)

    def test_cancel_or_zero_changes_nothing(self):
        rev = self.v.revision
        self.typed(30, ok=False)
        self.typed(0)
        self.assertEqual(self.v.revision, rev)

    def test_it_offers_the_last_angle_typed(self):
        self.typed(22.5)
        ask = self.typed(10)
        self.assertEqual(ask.call_args[0][3], 22.5)

    def test_the_menu_has_it(self):
        from PySide6.QtCore import QPoint
        from PySide6.QtWidgets import QMenu
        seen = {}

        class Menu(QMenu):
            def exec(self, *_a):
                seen.update({a.text(): a.isEnabled() for a in self.actions()})
        ev = mock.Mock()
        ev.globalPosition.return_value.toPoint.return_value = QPoint(0, 0)
        with mock.patch("PySide6.QtWidgets.QMenu", Menu):
            self.page._objects_menu(ev, CENTER)
        self.assertTrue(seen.get("Rotate by an angle..."))


class InCadMode(DragTheRoundHandle):
    cad = True


class WithTextSelected(Turning):
    text = True

    def test_no_handle_and_the_typed_angle_says_why(self):
        self.assertIsNone(self.handle())
        said = []
        self.v.statusMessage.connect(said.append)
        with mock.patch.object(QInputDialog, "getDouble", return_value=(30, True)):
            self.v.rotate_objects_by()
        self.assertIn("not turned", said[-1])
        self.assertEqual(bar_box(self.v.doc[0]), BAR)


if __name__ == "__main__":
    unittest.main()
