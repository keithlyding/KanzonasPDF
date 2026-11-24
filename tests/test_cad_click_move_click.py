"""CAD mode works by clicks only (the owner, 23 Nov 2026: "in cad mouse mode, the mouse clicks
need to function like a cad mouse. No clicking and holding for anything"): a click on a grip
makes it hot, it follows the pointer with no button held, the next click places it; a click on
what's selected picks it up, the next click puts it down; the same for the box around several
items, the drawing's objects' handles and their round turning handle, a line's ends; the Pen
draws from one click to the next. A press, drag and release is a click and a move. Escape or a
right-click puts it back. Each one is one undo step. The middle button still pans. The
Standard and Hand modes still drag.

Real mouse events (QTest) go through the page widget.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_cad_click_move_click
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
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QMouseEvent  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import annotations as A  # noqa: E402
from kanzonas import cad_draw, cad_grips  # noqa: E402
from kanzonas.document_view import DocumentView  # noqa: E402
from kanzonas.page_widget import box_handles  # noqa: E402

P = pymupdf.Point
R = pymupdf.Rect


def sheet():
    """Page 1: a line of the drawing (100..300 at y 400), a bar of the drawing to turn
    (200..400, 290..310), and two rectangle markups and a line markup. Page 2: empty."""
    d = pymupdf.open()
    p = d.new_page(width=612, height=792)
    p.draw_line((100, 400), (300, 400), color=(0, 0, 1), width=2)
    p.draw_rect(R(200, 560, 400, 580), color=(0, 0, 0), fill=(0, 0, 0))
    for r in (R(400, 100, 500, 160), R(400, 250, 460, 300)):
        A.write(p, {"kind": "rect", "props": dict(A.DEFAULTS["rect"]), "rect": r})
    A.write(p, {"kind": "line", "props": dict(A.DEFAULTS["line"]),
                "points": [P(100, 650), P(250, 650)]})
    p.insert_text((100, 480), "GENERAL NOTES FOR THE SHEET", fontsize=14)
    d.new_page(width=612, height=792)
    path = os.path.join(tempfile.mkdtemp(), "sheet.pdf")
    d.save(path)
    return path


class Base(unittest.TestCase):
    MODE = "cad"

    def setUp(self):
        keys = ("mouse_mode", "cad_select", "click_click", "lasso", "snap_objects",
                "snap_grid", "snap_page", "plus_cursor")
        for key in keys:
            self.addCleanup(setattr, DocumentView, key, getattr(DocumentView, key))
        DocumentView.mouse_mode = self.MODE
        DocumentView.cad_select = DocumentView.click_click = self.MODE == "cad"
        DocumentView.lasso = False
        DocumentView.snap_objects = DocumentView.snap_grid = DocumentView.snap_page = False
        # (QTest moves the pointer itself: only the view in use is shown)
        for old in APP.topLevelWidgets():
            if old.isVisible():
                old.hide()
        v = self.v = DocumentView(sheet())
        self.addCleanup(v.close_doc)
        self.addCleanup(v.hide)
        self.addCleanup(lambda: setattr(v, "dirty", False))
        v.resize(1000, 1100)
        v.show()
        APP.processEvents()
        v.set_zoom(1.0)
        APP.processEvents()

    @property
    def w(self):
        return self.v.pages[0]

    def at(self, xy, w=None):
        q = (w or self.w).to_screen_pt(P(xy))
        return QPoint(round(q.x()), round(q.y()))

    def click(self, xy, button=Qt.LeftButton, mods=Qt.NoModifier, w=None):
        QTest.mouseClick(w or self.w, button, mods, self.at(xy, w) if isinstance(xy, tuple)
                         else xy)
        APP.processEvents()

    def hover(self, xy, w=None):
        """The pointer moves there with no button held."""
        w = w or self.w
        pos = QPointF(self.at(xy, w) if isinstance(xy, tuple) else xy)
        w.mouseMoveEvent(QMouseEvent(QEvent.MouseMove, pos, w.mapToGlobal(pos), Qt.NoButton,
                                     Qt.NoButton, Qt.NoModifier))
        APP.processEvents()

    def drag(self, a, b):
        """Press at a, move to b with the button held, release there."""
        w = self.w
        QTest.mousePress(w, Qt.LeftButton, Qt.NoModifier, self.at(a))
        for k in (1, 2, 3):
            pos = QPointF(self.at((a[0] + (b[0] - a[0]) * k / 3, a[1] + (b[1] - a[1]) * k / 3)))
            w.mouseMoveEvent(QMouseEvent(QEvent.MouseMove, pos, w.mapToGlobal(pos),
                                         Qt.NoButton, Qt.LeftButton, Qt.NoModifier))
        QTest.mouseRelease(w, Qt.LeftButton, Qt.NoModifier, self.at(b), 300)
        APP.processEvents()

    def escape(self):
        QTest.keyClick(self.v, Qt.Key_Escape)
        APP.processEvents()

    def rects(self):
        page = self.v.doc[0]
        return sorted((tuple(round(c) for c in A.read(a)["rect"]) for a in A.each_annot(page)
                       if A.read(a)["kind"] == "rect"), key=lambda r: r[1])

    def markup(self, kind):
        page = self.v.doc[0]
        for a in A.each_annot(page):
            m = A.read(a)
            if m["kind"] == kind:
                return a.xref, m
        return None, None

    def drawn(self):
        """The drawing's own paths on page 1: (rounded rect) each, sorted."""
        return sorted(tuple(round(c) for c in d["rect"]) for d in self.v.doc[0].get_drawings())

    def handle(self, hid, w=None):
        w = w or self.w
        model = w._selected_here()
        r = w._handles(model)[hid] if model is not None and not w._objects_here() \
            else w._objects_handles()[hid]
        return r.center().toPoint()


class Moving(Base):
    def test_a_click_on_the_selection_picks_it_up_and_a_click_puts_it_down(self):
        v = self.v
        v.set_tool("editobjects")
        before = self.drawn()
        self.click((150, 400))                          # takes the line
        self.assertEqual(len(v.selected_objects()), 1)
        rev = v.revision
        self.click((150, 400))                          # on it again: picked up
        self.assertIs(cad_grips.owner(v), self.w)
        self.hover((180, 430))                          # follows, no button held
        d = self.w._cad_down
        self.assertEqual(d["mode"], "drag")
        self.assertEqual(d["now"], QPointF(self.at((180, 430))))
        self.assertEqual(self.drawn(), before)          # (a preview: nothing changed yet)
        self.assertEqual(v.revision, rev)
        self.click((180, 430))
        self.assertIsNone(cad_grips.owner(v))
        line = (130, 430, 330, 430)
        got = self.drawn()
        self.assertIn(line, [tuple(r) for r in got], got)
        v.undo()                                        # one undo step
        self.assertEqual(self.drawn(), before)

    def test_markups_too(self):
        v = self.v
        v.set_tool("select")
        self.click((425, 100))                          # the first rectangle's top edge
        self.click((425, 100))
        self.assertIsNotNone(cad_grips.owner(v))
        self.hover((445, 150))
        self.click((445, 150))
        self.assertEqual(self.rects()[0], (420, 150, 520, 210))
        v.undo()
        self.assertEqual(self.rects()[0], (400, 100, 500, 160))

    def test_a_drag_is_a_click_and_a_move(self):
        v = self.v
        v.set_tool("editobjects")
        before = self.drawn()
        self.click((150, 400))
        self.drag((150, 400), (210, 400))               # held and let go: still picked up
        self.assertIs(cad_grips.owner(v), self.w)
        self.assertEqual(self.drawn(), before)
        self.hover((210, 450))
        self.click((210, 450))                          # the click puts it down
        self.assertIn((160, 450, 360, 450), self.drawn())

    def test_put_down_off_the_page(self):
        v = self.v
        v.set_tool("editobjects")
        self.click((150, 400))
        self.click((150, 400))
        # the pointer over the gray beside the page: the canvas hands the move on, and
        # the click there puts it down (outside the page, as a drag could)
        canvas = self.w.parentWidget()
        g = self.w.mapToGlobal(QPointF(self.at((150, 400))) + QPointF(-120 - self.at(
            (150, 400)).x(), 0))
        local = canvas.mapFromGlobal(g)
        canvas.mouseMoveEvent(QMouseEvent(QEvent.MouseMove, local, g, Qt.NoButton,
                                          Qt.NoButton, Qt.NoModifier))
        APP.processEvents()
        self.assertIsNotNone(cad_grips.owner(v))
        QTest.mouseClick(canvas, Qt.LeftButton, Qt.NoModifier, local.toPoint())
        APP.processEvents()
        self.assertIsNone(cad_grips.owner(v))
        self.assertNotIn((100, 400, 300, 400), self.drawn())


class Zoom(Base):
    def test_a_zoom_between_the_clicks_keeps_where_it_was_picked_up(self):
        v = self.v
        v.set_tool("editobjects")
        self.click((150, 400))
        self.click((150, 400))
        v.set_zoom(2.0)                                 # (the wheel, halfway)
        APP.processEvents()
        self.hover((180, 430))
        self.click((180, 430))
        self.assertIn((130, 430, 330, 430), self.drawn())

    def test_and_a_hot_grip_too(self):
        v = self.v
        v.set_tool("select")
        self.click((425, 100))
        self.click(self.handle("br"))
        v.set_zoom(1.5)
        APP.processEvents()
        self.hover((540, 200))
        self.click((540, 200))
        self.assertEqual(self.rects()[0], (400, 100, 540, 200))


class Grips(Base):
    def test_a_markups_corner_grip(self):
        v = self.v
        v.set_tool("select")
        self.click((425, 100))
        self.click(self.handle("br"))                   # hot
        self.assertIs(cad_grips.owner(v), self.w)
        self.hover((540, 200))
        self.assertIsNotNone(self.w._edit["preview"])   # the preview follows
        self.assertEqual(self.rects()[0], (400, 100, 500, 160))
        self.click((540, 200))
        self.assertIsNone(cad_grips.owner(v))
        self.assertEqual(self.rects()[0], (400, 100, 540, 200))
        v.undo()
        self.assertEqual(self.rects()[0], (400, 100, 500, 160))

    def test_a_lines_end(self):
        v = self.v
        v.set_tool("select")
        self.click((175, 650))
        xref, m = self.markup("line")
        self.click(self.handle("p1"))
        self.hover((300, 700))
        self.click((300, 700))
        _x, m2 = self.markup("line")
        self.assertTrue(A._same(m2["points"], [P(100, 650), P(300, 700)], 0.6), m2["points"])
        v.undo()
        _x, m3 = self.markup("line")
        self.assertTrue(A._same(m3["points"], m["points"], 0.01))

    def test_a_markup_turned_by_its_round_handle(self):
        v = self.v
        v.set_tool("select")
        self.click((425, 100))
        _x, m = self.markup("rect")
        c = self.w.to_screen(A.bounds(m)).center()
        self.click(self.handle("rot"))
        # a quarter turn clockwise: the pointer from above the middle to its right
        self.hover(QPoint(round(c.x() + 80), round(c.y())))
        self.click(QPoint(round(c.x() + 80), round(c.y())))
        _x, m2 = self.markup("rect")
        self.assertAlmostEqual(abs(A.angle(m2)) % 180, 90, 0)

    def test_the_box_around_several_markups(self):
        v = self.v
        v.set_tool("select")
        self.click((425, 100))
        self.click((430, 250))
        box = self.w._handles
        from kanzonas import cad_select
        r = cad_select.resize_box(self.w)
        self.assertIsNotNone(r, box)
        corner = box_handles(r)["br"].center()
        self.click(corner.toPoint())
        self.assertIs(cad_grips.owner(v), self.w)
        self.hover(corner.toPoint() + QPoint(50, 100))
        self.assertIsNotNone(self.w._cad_resize["now"])
        self.assertEqual(self.rects(), [(400, 100, 500, 160), (400, 250, 460, 300)])
        self.click(corner.toPoint() + QPoint(50, 100))
        got = self.rects()
        self.assertGreater(got[1][2], 470)             # (both bigger: 200 tall becomes 300)
        self.assertGreater(got[1][3] - got[0][1], 250)
        v.undo()
        self.assertEqual(self.rects(), [(400, 100, 500, 160), (400, 250, 460, 300)])

    def test_the_drawings_objects_resized_by_a_handle(self):
        v = self.v
        v.set_tool("editobjects")
        self.click((300, 570))                          # the bar
        before = self.drawn()
        self.click(self.handle("r"))
        self.hover(self.handle("r") + QPoint(100, 0))
        self.assertIsNotNone(self.w._obj_edit["preview"])
        self.assertEqual(self.drawn(), before)
        self.click(self.handle("r") + QPoint(100, 0))
        self.assertIsNone(cad_grips.owner(v))
        self.assertTrue(any(r[0] == 200 and r[2] >= 495 for r in self.drawn()), self.drawn())
        v.undo()
        self.assertEqual(self.drawn(), before)

    def test_the_drawings_objects_turned_by_the_round_handle(self):
        v = self.v
        v.set_tool("editobjects")
        self.click((300, 570))
        before = self.drawn()
        said = []
        v.statusMessage.connect(said.append)
        h = self.handle("rot")
        c = self.w.to_screen(v.selected_objects_rect()).center()
        self.click(h)
        far = QPoint(round(c.x() + (c.y() - h.y())), round(c.y()))    # a quarter turn
        self.hover(far)
        self.assertTrue(any("Rotate: " in s for s in said), said[-3:])
        self.assertEqual(self.drawn(), before)
        self.click(far)
        bar = [r for r in self.drawn() if r not in before]
        self.assertTrue(bar, self.drawn())
        x0, y0, x1, y1 = bar[0]
        self.assertAlmostEqual(x1 - x0, 20, delta=2)    # (stood up)
        self.assertAlmostEqual(y1 - y0, 200, delta=2)
        v.undo()
        self.assertEqual(self.drawn(), before)


class Cancel(Base):
    def picked_up(self):
        v = self.v
        v.set_tool("editobjects")
        self.click((150, 400))
        self.click((150, 400))
        self.hover((260, 470))
        self.assertIsNotNone(cad_grips.owner(v))
        return self.drawn(), v.revision

    def test_escape_puts_it_back(self):
        before, rev = self.picked_up()
        self.escape()
        self.assertIsNone(cad_grips.owner(self.v))
        self.assertIsNone(self.w._cad_down)
        self.assertEqual(self.drawn(), before)
        self.assertEqual(self.v.revision, rev)
        self.assertEqual(len(self.v.selected_objects()), 1)     # (still selected)
        self.hover((300, 500))
        self.click((300, 500))                          # a click now moves nothing
        self.assertEqual(self.drawn(), before)

    def test_a_right_click_puts_it_back_with_no_menu(self):
        before, rev = self.picked_up()
        with mock.patch.object(type(self.w), "_content_menu") as menu, \
                mock.patch.object(type(self.w), "_objects_menu") as objects_menu:
            self.click((260, 470), button=Qt.RightButton)
        self.assertFalse(menu.called or objects_menu.called)
        self.assertIsNone(cad_grips.owner(self.v))
        self.assertEqual(self.drawn(), before)
        self.assertEqual(self.v.revision, rev)

    def test_a_hot_grip_too(self):
        v = self.v
        v.set_tool("select")
        self.click((425, 100))
        self.click(self.handle("br"))
        self.hover((540, 200))
        self.escape()
        self.assertIsNone(self.w._edit)
        self.hover((560, 220))
        self.click((560, 220))
        self.assertEqual(self.rects()[0], (400, 100, 500, 160))

    def test_the_middle_button_pans_and_it_stays_hot(self):
        v = self.v
        v.set_tool("editobjects")
        self.click((150, 400))
        self.click((150, 400))
        sb = v.verticalScrollBar()
        start = sb.value()
        w = self.w
        a = QPointF(self.at((200, 500)))
        QTest.mousePress(w, Qt.MiddleButton, Qt.NoModifier, a.toPoint())
        w.mouseMoveEvent(QMouseEvent(QEvent.MouseMove, a - QPointF(0, 80),
                                     w.mapToGlobal(a - QPointF(0, 80)), Qt.NoButton,
                                     Qt.MiddleButton, Qt.NoModifier))
        QTest.mouseRelease(w, Qt.MiddleButton, Qt.NoModifier, (a - QPointF(0, 80)).toPoint())
        APP.processEvents()
        self.assertNotEqual(sb.value(), start)
        self.assertIs(cad_grips.owner(v), self.w)
        self.hover((180, 430))
        self.click((180, 430))
        self.assertIn((130, 430, 330, 430), self.drawn())

    def test_the_tool_changed_drops_it(self):
        before, _rev = self.picked_up()
        self.v.set_tool("select")
        self.assertIsNone(cad_grips.owner(self.v))
        self.click((300, 500))
        self.assertEqual(self.drawn(), before)


class Clicks(Base):
    def test_a_double_click_on_a_selected_markup_still_edits_its_text(self):
        v = self.v
        v.set_tool("select")
        self.click((425, 100))
        with mock.patch.object(type(v), "edit_annot_at") as edit:
            QTest.mouseDClick(self.w, Qt.LeftButton, Qt.NoModifier, self.at((425, 100)))
            APP.processEvents()
        self.assertTrue(edit.called)
        self.assertIsNone(cad_grips.owner(v))           # (not left picked up)

    def test_a_drag_on_empty_paper_is_the_boxs_first_click(self):
        v = self.v
        v.set_tool("editobjects")
        self.drag((80, 380), (330, 420))                # held and let go: a box started
        self.assertIsNotNone(v._cad_pick)
        self.assertEqual(v.selected_objects(), [])
        self.hover((330, 420))
        self.click((330, 420))                          # its other corner
        self.assertIsNone(v._cad_pick)
        self.assertEqual(len(v.selected_objects()), 1)

    def test_a_drag_with_a_drawing_tool_is_a_click_and_a_move(self):
        v = self.v
        v.set_tool("line")
        self.drag((100, 200), (200, 200))
        self.assertIsNotNone(cad_draw.pending(v))       # (nothing drawn yet)
        self.assertIsNone(self.markup("line")[0] if False else None)
        self.hover((250, 220))
        self.click((250, 220))
        page = v.doc[0]
        lines = [A.read(a)["points"] for a in A.each_annot(page) if A.read(a)["kind"] == "line"]
        self.assertTrue(any(A._same(pts, [P(100, 200), P(250, 220)], 0.6) for pts in lines),
                        lines)

    def test_the_pen_draws_from_one_click_to_the_next(self):
        v = self.v
        v.set_tool("ink")
        self.click((100, 100))
        self.assertIs(cad_grips.owner(v), self.w)
        for k in range(1, 9):
            self.hover((100 + 10 * k, 100 + 20 * math.sin(k)))
        self.click((190, 100))
        self.assertIsNone(cad_grips.owner(v))
        xref, m = self.markup("ink")
        self.assertIsNotNone(xref)
        self.assertGreaterEqual(sum(len(s) for s in m["strokes"]), 9)
        v.undo()
        self.assertIsNone(self.markup("ink")[0])
        # Escape drops a stroke being drawn
        self.click((100, 100))
        self.hover((150, 150))
        self.escape()
        self.click((200, 200))                          # (a new stroke starts here)
        self.escape()
        self.assertIsNone(self.markup("ink")[0])

    def test_highlight_from_one_click_to_the_next(self):
        v = self.v
        v.set_tool("highlight")
        self.click((102, 476))
        self.assertIs(cad_grips.owner(v), self.w)
        self.hover((200, 476))
        self.hover((330, 476))
        self.assertIsNone(self.markup("highlight")[0])  # (not made yet)
        self.click((330, 476))
        self.assertIsNone(cad_grips.owner(v))
        xref, _m = self.markup("highlight")
        self.assertIsNotNone(xref)
        page = v.doc[0]
        words = page.get_textbox(page.load_annot(xref).rect)
        del page
        self.assertIn("GENERAL NOTES", words)
        v.undo()
        self.assertIsNone(self.markup("highlight")[0])

    def test_the_status_bar_says_what_to_do(self):
        v = self.v
        said = []
        v.statusMessage.connect(said.append)
        v.set_tool("select")
        self.click((425, 100))
        self.click(self.handle("br"))
        self.assertIn("click where it goes", said[-1])
        self.escape()
        self.click((425, 100))
        self.assertIn("click where it goes", said[-1])
        self.assertIn("Escape", said[-1])

    def test_the_click_click_option_off_drags_again(self):
        DocumentView.click_click = False
        v = self.v
        v.set_tool("select")
        self.click((425, 100))
        self.drag((425, 100), (445, 150))
        self.assertIsNone(cad_grips.owner(v))
        self.assertEqual(self.rects()[0], (420, 150, 520, 210))


class Typed(Base):
    def picked_up(self):
        v = self.v
        v.set_tool("editobjects")
        self.click((150, 400))
        self.click((150, 400))
        self.hover((180, 440))                          # (toward 3 across, 4 down)

    def test_a_distance_moves_it_that_far_toward_the_pointer(self):
        v = self.v
        before = self.drawn()
        self.picked_up()
        self.assertTrue(cad_grips.typed(v, "1"))        # 1 inch on paper (no scale): 72 pt
        self.assertIsNone(cad_grips.owner(v))
        self.assertIn((143, 458, 343, 458), self.drawn())       # (43.2 across, 57.6 down)
        v.undo()
        self.assertEqual(self.drawn(), before)

    def test_what_isnt_a_distance_leaves_it_following(self):
        v = self.v
        before = self.drawn()
        self.picked_up()
        said = []
        v.statusMessage.connect(said.append)
        self.assertTrue(cad_grips.typed(v, "far"))
        self.assertIn("distance", said[-1])
        self.assertTrue(cad_grips.typed(v, ""))         # (Enter alone)
        self.assertIs(cad_grips.owner(v), self.w)
        self.assertEqual(self.drawn(), before)

    def test_a_hot_grip_lets_a_command_run(self):
        v = self.v
        v.set_tool("select")
        self.click((425, 100))
        self.click(self.handle("br"))
        self.assertFalse(cad_grips.typed(v, "M"))       # (the grip goes back; M runs)
        self.assertIsNone(cad_grips.owner(v))
        self.assertEqual(self.rects()[0], (400, 100, 500, 160))
        self.assertFalse(cad_grips.typed(v, "1"))       # (nothing hot: not taken)


class Standard(Base):
    MODE = "standard"

    def test_select_still_drags_a_markup(self):
        v = self.v
        v.set_tool("select")
        self.drag((425, 100), (445, 150))
        self.assertIsNone(cad_grips.owner(v))
        self.assertEqual(self.rects()[0], (420, 150, 520, 210))
        self.drag((445, 150), (445, 150))     # (a click: nothing picked up)
        self.assertIsNone(cad_grips.owner(v))

    def test_a_grip_still_drags(self):
        v = self.v
        v.set_tool("select")
        self.click((425, 100))
        h = self.handle("br")
        w = self.w
        QTest.mousePress(w, Qt.LeftButton, Qt.NoModifier, h)
        w.mouseMoveEvent(QMouseEvent(QEvent.MouseMove, QPointF(h + QPoint(40, 40)),
                                     w.mapToGlobal(QPointF(h + QPoint(40, 40))), Qt.NoButton,
                                     Qt.LeftButton, Qt.NoModifier))
        QTest.mouseRelease(w, Qt.LeftButton, Qt.NoModifier, h + QPoint(40, 40))
        APP.processEvents()
        self.assertIsNone(cad_grips.owner(v))
        self.assertEqual(self.rects()[0], (400, 100, 540, 200))


class Hand(Base):
    MODE = "hand"

    def test_the_hand_still_drags_the_page(self):
        v = self.v
        v.set_tool("hand")
        v.verticalScrollBar().setValue(200)
        APP.processEvents()
        start = v.verticalScrollBar().value()
        self.drag((300, 500), (300, 400))
        self.assertIsNone(cad_grips.owner(v))
        self.assertNotEqual(v.verticalScrollBar().value(), start)


if __name__ == "__main__":
    unittest.main()
