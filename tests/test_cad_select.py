"""CAD mode selection, as in AutoCAD: a box left to right (blue window) takes what lies inside
it, right to left (green crossing) what it touches; a click or a box adds to the selection,
Shift takes out of it, Escape clears it. Click, move, click draws the box; holding the button
draws a lasso (rightward a window, leftward a crossing one); dragging moves nothing. With
Select for markups and text, with Edit objects for the drawing's own lines, text and
pictures. A plus cursor in CAD mode. Free page movement: the page can be dragged past its
edges even when it fits the window. (Most tests turn click-click and the lasso off, so a
press-drag-release draws a box.)

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_cad_select
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402
from PySide6.QtCore import QEvent, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QKeyEvent, QMouseEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import document_view, page_objects  # noqa: E402
from kanzonas.document_view import DocumentView  # noqa: E402

R = pymupdf.Rect


def saved(build):
    d = pymupdf.open()
    p = d.new_page()
    build(p)
    path = os.path.join(tempfile.mkdtemp(), "cad.pdf")
    d.save(path)
    return path


def drawing(p):
    """Line work: a short line inside (100..140, 100), a long one crossing x=160..260 at
    y=200, a plumb line at x=300, and a label."""
    p.draw_line((100, 100), (140, 100))
    p.draw_line((60, 200), (400, 200))
    p.draw_line((300, 60), (300, 400))
    p.insert_text((100, 300), "GRID A", fontsize=10)


class Geometry(unittest.TestCase):
    def test_a_line_through_a_box(self):
        box = R(10, 10, 20, 20)
        meets = page_objects.segment_meets
        self.assertTrue(meets((0, 15), (30, 15), box))          # straight through
        self.assertTrue(meets((0, 25), (25, 0), box))           # across a corner
        self.assertTrue(meets((15, 15), (16, 16), box))         # inside
        self.assertFalse(meets((0, 0), (30, 0), box))           # above it
        self.assertFalse(meets((0, 15), (5, 15), box))          # stops short


class CadMouse(unittest.TestCase):
    def setUp(self):
        for key in ("cad_select", "plus_cursor", "click_click", "lasso"):
            self.addCleanup(setattr, DocumentView, key, getattr(DocumentView, key))
        DocumentView.cad_select = DocumentView.plus_cursor = True
        DocumentView.click_click = DocumentView.lasso = False     # (press, drag, release: a box)

    def view(self, build, tool):
        v = DocumentView(saved(build))
        self.addCleanup(v.close_doc)
        v.resize(1000, 1100)
        v.show()
        v.set_zoom(1.0)
        APP.processEvents()
        v.set_tool(tool)
        return v

    def mouse(self, v, kind, pt, mods=Qt.NoModifier, held=True):
        w = v.pages[0]
        pos = QPointF(w.to_screen_pt(pymupdf.Point(pt)))
        t = {"press": QEvent.MouseButtonPress, "move": QEvent.MouseMove,
             "release": QEvent.MouseButtonRelease}[kind]
        buttons = Qt.NoButton if kind == "release" or not held else Qt.LeftButton
        ev = QMouseEvent(t, pos, w.mapToGlobal(pos), Qt.LeftButton, buttons, mods)
        {"press": w.mousePressEvent, "move": w.mouseMoveEvent,
         "release": w.mouseReleaseEvent}[kind](ev)
        APP.processEvents()

    def drag(self, v, a, b, mods=Qt.NoModifier):
        self.mouse(v, "press", a, mods)
        self.mouse(v, "move", ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2), mods)
        self.mouse(v, "move", b, mods)
        self.mouse(v, "release", b, mods)

    def click(self, v, pt, mods=Qt.NoModifier):
        self.mouse(v, "press", pt, mods)
        self.mouse(v, "release", pt, mods)

    def escape(self, v):
        v.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier))

    # ---- Edit objects ---------------------------------------------------------------
    def chosen(self, v):
        return sorted((round(it["rect"].x0), round(it["rect"].y0), it["kind"])
                      for it in v.selected_objects())

    def test_window_takes_what_is_inside_crossing_what_it_touches(self):
        v = self.view(drawing, "editobjects")
        self.drag(v, (80, 80), (180, 220))                      # left to right: window
        self.assertEqual(self.chosen(v), [(100, 100, "shape")])
        self.escape(v)
        self.assertEqual(self.chosen(v), [])
        self.drag(v, (180, 220), (80, 80))                      # right to left: crossing
        self.assertEqual(self.chosen(v), [(60, 200, "shape"), (100, 100, "shape")])
        self.escape(v)
        self.drag(v, (320, 150), (280, 160))                    # crossing a plumb line
        self.assertEqual(self.chosen(v), [(300, 60, "shape")])

    def test_crossing_takes_text_it_touches_and_window_text_inside(self):
        v = self.view(drawing, "editobjects")
        self.drag(v, (130, 312), (120, 296))                    # crossing a letter
        self.assertEqual([it["kind"] for it in v.selected_objects()], ["text"])
        self.escape(v)
        self.drag(v, (95, 284), (126, 309))                     # window around part of it
        self.assertEqual(v.selected_objects(), [])
        self.drag(v, (95, 284), (140, 309))                     # window around all of it
        self.assertEqual([it["kind"] for it in v.selected_objects()], ["text"])

    def test_clicks_add_shift_takes_out_empty_click_keeps(self):
        v = self.view(drawing, "editobjects")
        self.click(v, (120, 100))
        self.click(v, (300, 300))
        self.assertEqual(self.chosen(v), [(100, 100, "shape"), (300, 60, "shape")])
        self.click(v, (500, 600))                               # empty paper: kept
        self.assertEqual(len(v.selected_objects()), 2)
        self.click(v, (120, 100), Qt.ShiftModifier)             # Shift: out
        self.assertEqual(self.chosen(v), [(300, 60, "shape")])
        self.drag(v, (80, 80), (180, 220))                      # a box adds too
        self.assertEqual(len(v.selected_objects()), 2)
        self.drag(v, (420, 210), (50, 190), Qt.ShiftModifier)   # Shift+crossing takes out
        self.assertEqual(self.chosen(v), [(100, 100, "shape")])

    def test_dragging_moves_nothing_it_selects(self):
        v = self.view(drawing, "editobjects")
        before = [d["rect"] for d in v.doc[0].get_drawings()]
        self.drag(v, (200, 200), (90, 90))                      # starts on the long line
        self.assertEqual(self.chosen(v), [(60, 200, "shape"), (100, 100, "shape")])
        self.drag(v, (200, 200), (200, 230))                    # on it, selected: still a box
        self.assertEqual([d["rect"] for d in v.doc[0].get_drawings()], before)

    def test_click_move_click_draws_the_box(self):
        DocumentView.click_click = True
        v = self.view(drawing, "editobjects")
        self.click(v, (80, 80))                                 # first corner, on empty paper
        self.assertIsNotNone(v._cad_pick)
        self.mouse(v, "move", (180, 220), held=False)           # the box follows the pointer
        self.assertEqual(v._cad_pick["now"], QPointF(v.pages[0].to_screen_pt(
            pymupdf.Point(180, 220))))
        self.click(v, (180, 220))                               # second corner
        self.assertIsNone(v._cad_pick)
        self.assertEqual(self.chosen(v), [(100, 100, "shape")])  # left to right: window
        self.click(v, (180, 220))                               # on the line? no: empty
        self.click(v, (80, 80))                                 # right to left: crossing
        self.assertEqual(self.chosen(v), [(60, 200, "shape"), (100, 100, "shape")])
        self.click(v, (500, 600))
        self.escape(v)                                          # Escape drops a started box
        self.assertIsNone(v._cad_pick)
        self.assertEqual(len(v.selected_objects()), 2)          # (and keeps the selection)

    def test_a_lasso_follows_the_pointer(self):
        DocumentView.lasso = True
        v = self.view(drawing, "editobjects")
        # rightward: a window lasso around the short line (100..140, 100) only
        loop = [(90, 90), (150, 85), (155, 115), (95, 120), (85, 100)]
        self.mouse(v, "press", loop[0])
        for pt in loop[1:]:
            self.mouse(v, "move", pt)
        self.mouse(v, "release", loop[-1])
        self.assertEqual(self.chosen(v), [(100, 100, "shape")])
        self.escape(v)
        # leftward: a crossing lasso over the long line and the plumb line
        loop = [(320, 190), (280, 185), (270, 215), (330, 220)]
        self.mouse(v, "press", loop[0])
        for pt in loop[1:]:
            self.mouse(v, "move", pt)
        self.mouse(v, "release", loop[-1])
        self.assertEqual(self.chosen(v), [(60, 200, "shape"), (300, 60, "shape")])

    # ---- Select: markups and text ---------------------------------------------------
    def markups(self, p):
        p.insert_text((100, 500), "Wall moved east", fontsize=12)
        a = p.add_rect_annot(R(100, 100, 160, 140))             # small box
        a.update()
        a = p.add_line_annot((60, 250), (400, 250))             # long line
        a.update()
        a = p.add_rect_annot(R(80, 300, 400, 450))              # big room outline, no fill
        a.update()

    def kinds(self, v):
        return sorted(round(m["rect"].y0) if "rect" in m else m["kind"]
                      for _x, m in v.selected_models())

    def test_select_window_and_crossing_on_markups(self):
        v = self.view(self.markups, "select")
        self.drag(v, (90, 90), (200, 270))                      # window: the small box only
        self.assertEqual(len(v.selected_xrefs()), 1)
        self.escape(v)
        self.assertIsNone(v.selection)
        self.drag(v, (200, 270), (90, 90))                      # crossing: and the line
        self.assertEqual(len(v.selected_xrefs()), 2)
        self.escape(v)
        self.drag(v, (250, 400), (150, 350))                    # inside the room, no edge
        self.assertIsNone(v.selection)
        self.drag(v, (420, 400), (380, 350))                    # over its right edge
        self.assertEqual(len(v.selected_xrefs()), 1)

    def test_select_clicks_add_and_shift_takes_out(self):
        v = self.view(self.markups, "select")
        self.click(v, (130, 100))                               # the small box's edge
        self.click(v, (200, 250))                               # the line
        self.assertEqual(len(v.selected_xrefs()), 2)
        self.click(v, (600, 700))                               # empty paper: kept
        self.assertEqual(len(v.selected_xrefs()), 2)
        self.click(v, (200, 250), Qt.ShiftModifier)
        self.assertEqual(len(v.selected_xrefs()), 1)
        self.drag(v, (200, 250), (90, 90))                      # from the line: a box
        self.assertEqual(len(v.selected_xrefs()), 2)
        page = v.doc[0]                                         # (alive while its annots are)
        before = sorted(tuple(a.rect) for a in page.annots())
        self.drag(v, (200, 250), (200, 280))                    # on it, selected: no move
        page = v.doc[0]
        self.assertEqual(sorted(tuple(a.rect) for a in page.annots()), before)

    def test_select_text_by_window_and_crossing(self):
        v = self.view(self.markups, "select")
        self.drag(v, (95, 484), (125, 506))                     # window around "Wall"
        self.assertEqual(v.selected_text(), "Wall")
        self.escape(v)
        self.drag(v, (128, 506), (95, 484))                     # crossing: also "m" touched
        self.assertTrue(v.selected_text().startswith("Wall m"), v.selected_text())
        self.drag(v, (98, 484), (180, 506), Qt.ShiftModifier)   # Shift: taken out again
        self.assertEqual(v.selected_text(), "")

    # ---- cursor and free movement ---------------------------------------------------
    def test_a_plus_cursor_except_with_the_hand(self):
        v = self.view(drawing, "select")
        self.assertEqual(v.viewport().cursor().shape(), Qt.CrossCursor)
        v.set_tool("highlight")
        self.assertEqual(v.viewport().cursor().shape(), Qt.CrossCursor)
        v.set_tool("hand")
        self.assertEqual(v.viewport().cursor().shape(), Qt.OpenHandCursor)
        DocumentView.plus_cursor = False
        v.set_tool("select")
        self.assertEqual(v.viewport().cursor().shape(), Qt.IBeamCursor)


class FreeMovement(unittest.TestCase):
    def test_the_hand_drags_a_page_that_fits_the_window(self):
        old = DocumentView.free_pan
        self.addCleanup(setattr, DocumentView, "free_pan", old)
        DocumentView.free_pan = False
        v = DocumentView(saved(drawing))
        self.addCleanup(v.close_doc)
        v.resize(900, 900)
        v.show()
        APP.processEvents()
        v.fit_page()
        APP.processEvents()
        h = v.horizontalScrollBar()
        self.assertEqual(h.maximum(), 0)                         # fits: nowhere to go
        DocumentView.free_pan = True
        v.apply_canvas()
        APP.processEvents()
        self.assertGreater(h.maximum(), 0)
        v.set_tool("hand")
        w = v.pages[0]
        start = (h.value(), v.verticalScrollBar().value())
        for t, at in ((QEvent.MouseButtonPress, QPointF(300, 300)),
                      (QEvent.MouseMove, QPointF(400, 380)),
                      (QEvent.MouseButtonRelease, QPointF(400, 380))):
            ev = QMouseEvent(t, at, w.mapToGlobal(at), Qt.LeftButton,
                             Qt.NoButton if t == QEvent.MouseButtonRelease else Qt.LeftButton,
                             Qt.NoModifier)
            {QEvent.MouseButtonPress: w.mousePressEvent, QEvent.MouseMove: w.mouseMoveEvent,
             QEvent.MouseButtonRelease: w.mouseReleaseEvent}[t](ev)
            APP.processEvents()
        self.assertNotEqual((h.value(), v.verticalScrollBar().value()), start)
        self.assertLess(h.value(), start[0])                    # dragged right: view goes left
        DocumentView.free_pan = False
        v.apply_canvas()
        self.assertEqual(v._canvas_margin, (document_view.PAGE_GAP, document_view.PAGE_GAP))


if __name__ == "__main__":
    unittest.main()
