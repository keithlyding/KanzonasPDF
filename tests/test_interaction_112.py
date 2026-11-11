"""The owner's reports of 11 Nov 2026 on 1.11.1, tested with real mouse and keyboard events in
a main window (the random battery calls the view's steps directly, so it can't see what the
pointer and the keys do):

- markups put or moved in the gray around a page "disappear until I click": a stamp following
  the pointer, a box dragged off the page, a markup moved off it and a polygon's next side
  are drawn over the gray while they're placed (the canvas paints the page's preview there);
- snapping "doesn't seem to be working": a shape of the page's own drawing moved with Edit
  objects snaps to the drawing's points (only markups were targets);
- with the Hand, a drag on a markup moves it (it selected it and panned nothing);
- text moved with the arrow keys onto another line took that line's letters away on the next
  press, and a paragraph moved over another block picked it up: the line passed over stays,
  written again where it was, and the selection stays the text that was selected;
- a group (Arrange > Group) is aligned and distributed as one.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_interaction_112
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402
from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import annotations as A  # noqa: E402

P = pymupdf.Point
R = pymupdf.Rect


def pump(n=4):
    for _ in range(n):
        APP.processEvents()


def blocks(doc):
    return sorted(b[4].strip() for b in doc[0].get_text("blocks"))


class Window(unittest.TestCase):
    def open(self, build=None):
        from kanzonas.main_window import MainWindow
        d = pymupdf.open()
        pg = d.new_page(width=612, height=792)
        pg.draw_line(P(100, 100), P(400, 100))
        pg.draw_rect(R(100, 300, 300, 450))
        if build is not None:
            build(pg)
        path = os.path.join(tempfile.mkdtemp(), "t.pdf")
        d.save(path)
        self.w = w = MainWindow()
        w.settings.setValue("ask_beside", "false")      # (the one-time question about print)
        w.resize(1300, 900)
        w.show()
        w.open_file(path)
        pump()
        self.v = v = w.view()
        v.set_zoom(1.0)
        pump()
        self.addCleanup(self.close)
        return w, v

    def close(self):
        self.v.dirty = False
        self.w._close_confirmed = True
        self.w.close()
        pump()

    def at(self, pt):
        return self.v.pages[0].to_screen_pt(pt).toPoint()

    def drag(self, widget, a, b, steps=6):
        QTest.mousePress(widget, Qt.LeftButton, Qt.NoModifier, a)
        pump(1)
        for k in range(1, steps + 1):
            QTest.mouseMove(widget, a + (b - a) * k / steps)
            pump(1)
        QTest.mouseRelease(widget, Qt.LeftButton, Qt.NoModifier, b)
        pump()

    def click(self, widget, pos):
        QTest.mouseClick(widget, Qt.LeftButton, Qt.NoModifier, pos)
        pump()


class Snapping(Window):
    def test_edit_objects_snaps_to_the_drawing(self):
        w, v = self.open()
        w.a_snap_objects.trigger()
        self.assertTrue(v.snap_objects)
        w.set_tool("editobjects")
        pump()
        pw = v.pages[0]
        # the rectangle's top-left corner dropped 3 pt from the line's end: it lands on it
        self.drag(pw, self.at(P(100, 375)), self.at(P(103, 178)))
        corners = sorted((round(d["rect"].x0, 1), round(d["rect"].y0, 1))
                         for d in v.doc[0].get_drawings())
        self.assertEqual(corners, [(100.0, 100.0), (100.0, 100.0)])
        # (a small move isn't held back by the objects' own points where they were)
        v.undo()
        pump()
        self.drag(pw, self.at(P(100, 375)), self.at(P(102, 377)))
        corners = sorted((round(d["rect"].x0, 1), round(d["rect"].y0, 1))
                         for d in v.doc[0].get_drawings())
        self.assertEqual(corners, [(100.0, 100.0), (102.0, 302.0)])


class Hand(Window):
    def test_a_drag_on_a_markup_moves_it(self):
        w, v = self.open()
        x = v._create(0, {"kind": "rect", "rect": R(150, 150, 200, 200), "text": "",
                          "props": dict(A.DEFAULTS["rect"])})
        v.clear_selection()
        w.set_tool("hand")
        pump()
        self.drag(v.pages[0], self.at(P(150, 175)), self.at(P(110, 135)))
        page = v.doc[0]
        r = page.load_annot(x).rect
        self.assertAlmostEqual(r.x0, 109, delta=1)
        self.assertAlmostEqual(r.y0, 109, delta=1)


class TextOverText(Window):
    def build(self, pg):
        pg.insert_text((100, 200), "First paragraph line one", fontsize=11)
        pg.insert_text((100, 214), "First paragraph line two", fontsize=11)
        pg.insert_text((100, 260), "Second block of text here", fontsize=11)

    def nudge(self, v, key, n, mods=Qt.NoModifier):
        for _ in range(n):
            QTest.keyClick(QApplication.focusWidget() or v, key, mods)
            pump(2)
            self.assertIsNotNone(v.obj_sel)             # (never unselected mid-move)

    def test_a_paragraph_moved_through_another_block(self):
        w, v = self.open(self.build)
        w.set_tool("editobjects")
        pump()
        self.click(v.pages[0], self.at(P(150, 197)))
        self.assertEqual([it["kind"] for it in v.obj_sel[1]], ["text"])
        self.nudge(v, Qt.Key_Down, 12, Qt.ShiftModifier)        # 120 pt, over the block
        self.assertEqual(blocks(v.doc), ["First paragraph line one\nFirst paragraph line two",
                                         "Second block of text here"])
        # only the paragraph is selected, and it's where it was moved to
        sel = v.obj_sel[1]
        self.assertEqual(len(sel), 1)
        self.assertEqual(len(sel[0]["lines"]), 2)
        self.assertAlmostEqual(sel[0]["rect"].y0, 200 - 11 * 1.07 + 120, delta=3)
        # the block stayed where it was
        second = next(b for b in v.doc[0].get_text("blocks") if b[4].startswith("Second"))
        self.assertAlmostEqual(second[1], 248.2, delta=1.5)

    def test_a_line_moved_onto_another_one_keeps_it(self):
        def build(pg):
            pg.insert_text((100, 240), "Another line, small", fontsize=8)
            pg.insert_text((100, 280), "Helvetica line here", fontsize=11)
        w, v = self.open(build)
        w.set_tool("editobjects")
        pump()
        self.click(v.pages[0], self.at(P(130, 238)))
        self.nudge(v, Qt.Key_Down, 15, Qt.ShiftModifier)
        self.assertEqual(blocks(v.doc), ["Another line, small", "Helvetica line here"])
        # one undo step brings it all back as it was
        v.undo()
        pump()
        b = {x[4].strip(): x[1] for x in v.doc[0].get_text("blocks")}
        self.assertAlmostEqual(b["Another line, small"], 240 - 8 * 1.07, delta=1.5)


class AngledAndRefused(Window):
    """Found by the random battery's new arrow-key step (seeds 5 and 1112): a move refused
    (redaction marks on the page) unselected the text; text at an angle (a diagonal
    watermark, a tilted label) came out level, or left its end letters behind."""

    def angles(self, v):
        import math
        out = {}
        for b in v.doc[0].get_text("dict")["blocks"]:
            for ln in b.get("lines", []):
                dx, dy = ln["dir"]
                text = "".join(s["text"] for s in ln["spans"])
                out[text] = (round(math.degrees(math.atan2(-dy, dx))),
                             [round(c) for c in ln["spans"][0]["origin"]],
                             ln["spans"][0].get("alpha"))
        return out

    def test_text_at_an_angle_moves_whole_at_its_angle(self):
        def build(pg):
            o = P(200, 500)
            sh = pg.new_shape()
            sh.insert_text(o, "COPY", fontsize=60, fontname="helv", color=(0.7, 0, 0),
                           morph=(o, pymupdf.Matrix(45)), fill_opacity=0.3,
                           stroke_opacity=0.3)
            sh.commit()
            o = P(100, 200)
            sh = pg.new_shape()
            sh.insert_text(o, "Tilted label", fontsize=14, fontname="helv",
                           morph=(o, pymupdf.Matrix(30)))
            sh.commit()
        w, v = self.open(build)
        for it in list(v.text_objects(0)):
            v.select_objects(0, [it])
            v.move_objects(v.selected_objects_rect() + (20, 10, 20, 10))
            self.assertIsNotNone(v.obj_sel)
        got = self.angles(v)
        self.assertEqual(sorted(got), ["COPY", "Tilted label"])     # (no letters left behind)
        self.assertEqual(got["COPY"][:2], (45, [220, 510]))
        self.assertLess(got["COPY"][2], 255)                        # (still see-through)
        self.assertEqual(got["Tilted label"][:2], (30, [120, 210]))

    def test_a_refused_move_keeps_the_selection(self):
        def build(pg):
            pg.insert_text((100, 200), "Some text to move", fontsize=11)
        w, v = self.open(build)
        page = v.doc[0]
        v.modify(lambda: page.add_redact_annot(R(300, 600, 400, 650)), [0])
        del page
        from unittest import mock
        from PySide6.QtWidgets import QMessageBox
        w.set_tool("editobjects")
        pump()
        self.click(v.pages[0], self.at(P(150, 197)))
        self.assertIsNotNone(v.obj_sel)
        with mock.patch.object(QMessageBox, "warning", lambda *a, **k: QMessageBox.Ok):
            for _ in range(3):
                QTest.keyClick(QApplication.focusWidget() or v, Qt.Key_Down)
                pump(2)
                self.assertIsNotNone(v.obj_sel)
        self.assertEqual(blocks(v.doc), ["Some text to move"])


class GrayPreviews(Window):
    """Each preview is drawn on the gray canvas where it reaches past the page."""

    def setUp(self):
        w, v = self.open()
        v.set_zoom(0.5)
        pump()
        self.pw = pw = v.pages[0]
        self.canvas = v.widget()
        g = pw.geometry()
        v.horizontalScrollBar().setValue(max(0, g.left() - 300))
        v.verticalScrollBar().setValue(max(0, g.top() - 100))
        pump()
        self.g = pw.geometry()
        self.gray = QPoint(self.g.left() - 40, self.g.top() + 60)      # left of the page

    def shot(self):
        pump(3)
        return self.canvas.grab().toImage()

    def changed(self, before, after, at, r=6):
        return sum(1 for dx in range(-r, r + 1) for dy in range(-r, r + 1)
                   if before.pixel(at.x() + dx, at.y() + dy) !=
                   after.pixel(at.x() + dx, at.y() + dy))

    def test_a_stamp_following_the_pointer(self):
        self.w.set_tool("stamp")
        pump()
        before = self.shot()
        QTest.mouseMove(self.canvas, self.gray + QPoint(-30, 20))   # (from somewhere else)
        QTest.mouseMove(self.canvas, self.gray)
        self.assertIsNotNone(self.pw._ghost)
        self.assertGreater(self.changed(before, self.shot(), self.gray), 10)

    def test_a_box_dragged_off_the_page(self):
        self.w.set_tool("rect")
        pump()
        before = self.shot()
        start, end = QPoint(30, 30), self.gray - self.g.topLeft()
        QTest.mousePress(self.pw, Qt.LeftButton, Qt.NoModifier, start)
        for k in range(1, 6):
            QTest.mouseMove(self.pw, start + (end - start) * k / 5)
            pump(1)
        self.assertGreater(self.changed(before, self.shot(), self.gray), 10)
        QTest.mouseRelease(self.pw, Qt.LeftButton, Qt.NoModifier, end)
        pump()
        self.assertEqual(len(list(self.v.doc[0].annots())), 1)

    def test_a_markup_moved_off_the_page(self):
        v = self.v
        v._create(0, {"kind": "rect", "rect": R(100, 100, 200, 200), "text": "",
                      "props": dict(A.DEFAULTS["rect"], fill="#ff0000")})
        v.clear_selection()
        self.w.set_tool("select")
        pump()
        on = self.pw.to_screen_pt(P(100, 150)).toPoint()
        to = on + QPoint(-140, 0)
        before = self.shot()
        QTest.mousePress(self.pw, Qt.LeftButton, Qt.NoModifier, on)
        for k in range(1, 6):
            QTest.mouseMove(self.pw, on + (to - on) * k / 5)
            pump(1)
        self.assertGreater(self.changed(before, self.shot(), to + self.g.topLeft()), 10)
        QTest.mouseRelease(self.pw, Qt.LeftButton, Qt.NoModifier, to)

    def test_a_polygons_next_side(self):
        self.w.set_tool("polygon")
        pump()
        self.click(self.pw, QPoint(40, 40))
        self.click(self.pw, QPoint(80, 40))
        before = self.shot()
        QTest.mouseMove(self.canvas, self.gray)
        self.assertGreater(self.changed(before, self.shot(), self.gray, 3), 3)


class AlignGroups(Window):
    def test_a_group_is_aligned_as_one(self):
        w, v = self.open()
        props = dict(A.DEFAULTS["rect"])
        a = v._create(0, {"kind": "rect", "rect": R(100, 500, 140, 540), "text": "",
                          "props": props})
        b = v._create(0, {"kind": "rect", "rect": R(200, 520, 240, 560), "text": "",
                          "props": props})
        c = v._create(0, {"kind": "rect", "rect": R(300, 600, 340, 640), "text": "",
                          "props": props})
        v.select_xref(0, a)
        v.select_xref(0, b, add=True)
        v.group_selection()
        v.select_xref(0, c)
        v.select_xref(0, a, add=True)          # (the whole group with it)
        self.assertEqual(len(v.selected_xrefs()), 3)
        v.align("top", ref="first")             # (c first: the group's top goes to c's)
        page = v.doc[0]
        ys = sorted(round(an.rect.y0) for an in page.annots())
        # the group moved 100 down as one (its two boxes still 20 apart), c stayed
        self.assertEqual(ys, [599, 599, 619])


if __name__ == "__main__":
    unittest.main()
