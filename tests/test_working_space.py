"""Markups anywhere in the gray around the pages (issue #82; the owner, 11 Nov: "just make it
so you can put markups in the gray space, but the gray space still functions exactly the same
as it always has"): a page with markups outside it gets just the room they need on those sides
(the same left and right, so the pages stay lined up), drawn in the canvas's own gray; a
click or drag in the gray goes to the nearest page; Review > Show markups on the page and Show
markups outside pages hide one or the other (hidden, the room closes up); Fit page and Fit width
fit the pages as always, Fit page and markups fits a page with its room; in two pages side by
side the room keeps the next page off them. They're saved; printed only when asked: on the same
sheet (the page smaller) or on an extra sheet after the page (the page at scale). The first one
in a document asks how they print.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_working_space
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402
from PySide6.QtCore import QEvent, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QImage, QMouseEvent, QPainter  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import annotations as A  # noqa: E402
from kanzonas import page_widget, paths  # noqa: E402
from kanzonas.main_window import MainWindow  # noqa: E402
from kanzonas.print_dialog import PrintDialog  # noqa: E402

BLUE = "#0000ff"
OUT = pymupdf.Rect(650, 300, 750, 400)          # beside the page's right edge (612 wide)
PAD = 18.0


def pump(n=8):
    for _ in range(n):
        APP.processEvents()


def color(img, pt):
    c = img.pixelColor(pt.toPoint())
    return c.red(), c.green(), c.blue()


def sample(path, beside=True):
    d = pymupdf.open()
    pg = d.new_page(width=612, height=792)
    pg.draw_rect((100, 100, 200, 200), color=(0, 0, 0), fill=(0, 0, 0))
    props = dict(A.DEFAULTS["rect"])
    props.update(fill=BLUE, stroke=BLUE)
    A.write(pg, {"kind": "rect", "rect": OUT if beside else pymupdf.Rect(300, 300, 400, 400),
                 "text": "", "props": props})
    d.new_page(width=612, height=792)
    d.new_page(width=612, height=792)
    d.save(path)


class Gray(unittest.TestCase):
    beside = True

    def setUp(self):
        A.reset_tool_props("rect")
        st = paths.settings()
        for k in ("ask_beside", "print_beside"):
            st.remove(k)
        st.setValue("ask_beside", "false")          # (the question has its own test)
        self.addCleanup(lambda: [st.remove(k) for k in ("ask_beside", "print_beside")])
        self.addCleanup(lambda: A.reset_tool_props("rect"))
        self.path = os.path.join(tempfile.mkdtemp(), "beside.pdf")
        sample(self.path, self.beside)
        self.w = w = MainWindow()
        w.resize(1400, 900)
        w.show()
        pump()
        w.open_file(self.path)
        pump()
        self.v = w.view()
        self.v.set_zoom(0.5)
        pump()
        self.pw = self.v.pages[0]
        self.addCleanup(self.close)

    def close(self):
        self.w._close_confirmed = True
        self.w.close()
        pump()

    def send(self, widget, kind, pos, buttons):
        ev = QMouseEvent(kind, pos, widget.mapToGlobal(pos), Qt.LeftButton, buttons,
                         Qt.NoModifier)
        {QEvent.MouseButtonPress: widget.mousePressEvent,
         QEvent.MouseMove: widget.mouseMoveEvent,
         QEvent.MouseButtonRelease: widget.mouseReleaseEvent}[kind](ev)
        pump(2)

    def drag(self, widget, a, b):
        self.send(widget, QEvent.MouseButtonPress, a, Qt.LeftButton)
        self.send(widget, QEvent.MouseMove, (a + b) / 2, Qt.LeftButton)
        self.send(widget, QEvent.MouseMove, b, Qt.LeftButton)
        self.send(widget, QEvent.MouseButtonRelease, b, Qt.NoButton)

    def at(self, pt):
        return self.pw.to_screen_pt(pymupdf.Point(pt))

    def rects(self, i=0):
        pg = self.v.doc[i]                  # (kept while its markups are read)
        return [pymupdf.Rect(a.rect) for a in pg.annots()]


class Room(Gray):
    def test_room_on_the_sides_needed_drawn_in_the_canvas_gray(self):
        z = self.v.zoom
        reach = self.rects()[0].x1 - 612 + PAD          # (its box with its border)
        side = round(reach * z)
        self.assertEqual(self.v.outside_margins(0), (reach, 0, reach, 0))
        self.assertEqual((self.pw.width(), self.pw.height()), (306 + 2 * side, 396))
        self.assertEqual(self.v.outside_margins(1), (0, 0, 0, 0))
        self.assertEqual((self.v.pages[1].width(), self.v.pages[1].height()), (306, 396))
        # lined up: the pages' left edges where they were
        a = self.pw.mapTo(self.v.widget(), self.pw.page_area().topLeft().toPoint())
        b = self.v.pages[1].mapTo(self.v.widget(), self.v.pages[1].page_area().topLeft().toPoint())
        self.assertEqual(a.x(), b.x())
        img = self.pw.grab().toImage()
        self.assertEqual(color(img, self.at((150, 150))), (0, 0, 0))            # the drawing
        self.assertEqual(color(img, self.at((700, 350))), (0, 0, 255))          # beside it
        ws = page_widget.WS_COLOR
        self.assertEqual(color(img, self.at((700, 600))), (ws.red(), ws.green(), ws.blue()))
        for pt in (pymupdf.Point(700, 350), pymupdf.Point(-50, 20), pymupdf.Point(300, 400)):
            self.assertAlmostEqual(abs(self.pw.to_pdf(self.at(pt)) - pt), 0, delta=0.01)

    def test_clicked_moved_and_drawn_beyond_the_room_in_the_gray(self):
        self.w.set_tool("select")
        pump()
        self.send(self.pw, QEvent.MouseButtonPress, self.at((700, 350)), Qt.LeftButton)
        self.send(self.pw, QEvent.MouseButtonRelease, self.at((700, 350)), Qt.NoButton)
        self.assertEqual(self.v.selected_model["kind"], "rect")
        self.drag(self.pw, self.at((700, 350)), self.at((700, 500)))
        r = self.rects()[0]
        self.assertAlmostEqual(r.y0, 449, delta=3)
        self.assertGreater(r.x0, 612)
        # a box drawn in the gray left of the page, beyond its room: the canvas hands the
        # drag to the page; the room grows to it
        self.w.set_tool("rect")
        pump()
        canvas = self.v.widget()
        a = QPointF(self.pw.mapTo(canvas, self.at((-200, 100)).toPoint()))
        b = QPointF(self.pw.mapTo(canvas, self.at((-120, 180)).toPoint()))
        self.assertIsNone(canvas.childAt(a.toPoint()))          # (the gray, not a page)
        self.drag(canvas, a, b)
        made = [r for r in self.rects() if r.x1 < 0]
        self.assertEqual(len(made), 1, self.rects())
        self.assertAlmostEqual(made[0].x0, -201, delta=3)
        self.assertGreaterEqual(self.v.outside_margins(0)[0], 200)
        # undone: the room it took is given back
        self.v.undo()
        pump()
        self.assertAlmostEqual(self.v.outside_margins(0)[0], self.rects()[0].x1 - 612 + PAD)

    def test_the_three_switches(self):
        a_page, a_out = self.w.a_show_page_markups, self.w.a_show_outside
        a_out.trigger()                     # outside pages hidden: the room closes up
        pump()
        self.addCleanup(lambda: (a_out.setChecked(True), self.w._toggle_show_outside()))
        self.assertEqual((self.pw.width(), self.pw.height()), (306, 396))
        self.assertIsNone(self.v.annot_at(0, pymupdf.Point(700, 350)))
        a_out.trigger()
        pump()
        self.assertGreater(self.pw.width(), 306)
        self.assertIsNotNone(self.v.annot_at(0, pymupdf.Point(700, 350)))
        a_page.trigger()                    # on the page hidden: the one beside still shows
        pump()
        self.addCleanup(lambda: (a_page.setChecked(True), self.w._toggle_show_page_markups()))
        img = self.pw.grab().toImage()
        self.assertEqual(color(img, self.at((700, 350))), (0, 0, 255))
        a_page.trigger()
        pump()

    def test_fit_as_always_and_fit_with_markups(self):
        self.v.fit_width()
        pump()
        widest = max(r.width for r in self.v.page_rects)
        z_fit = self.v.zoom
        self.assertAlmostEqual(z_fit * widest, self.v.viewport().width() - 2 * 12 - 4
                               - (0 if self.v.verticalScrollBar().isVisible() else
                                  self.v.verticalScrollBar().sizeHint().width()), delta=2)
        self.v.fit_markups()
        pump()
        self.assertLess(self.v.zoom, z_fit)
        self.assertLessEqual(self.pw.width(), self.v.viewport().width())

    def test_two_pages_side_by_side_make_room(self):
        self.w.layout_actions["two_continuous"].trigger()
        pump()
        p0, p1 = self.v.pages[0], self.v.pages[1]
        right_of_markup = p0.mapTo(self.v.widget(), self.at((750, 350)).toPoint()).x()
        self.assertLess(right_of_markup, p1.geometry().left())  # page 2 doesn't cover it

    def test_saved_and_printed_only_when_asked(self):
        out = os.path.join(os.path.dirname(self.path), "saved.pdf")
        self.v.doc.save(out)
        self.assertEqual(len(A.outside_page(pymupdf.open(out)[0])), 1)
        dlg = PrintDialog(None, self.v)
        self.assertTrue(dlg.beside.isEnabled())
        self.assertEqual(dlg.beside.currentIndex(), 0)              # left out
        self.assertEqual(dlg.sheets([0, 1]), [(0, False), (1, False)])
        paper0, box0 = dlg.sheet(0)

        def printed(extra=False):
            paper, box = dlg.sheet(0, extra)
            img = QImage(int(paper.width()), int(paper.height()), QImage.Format_RGB32)
            img.fill(0xFFFFFFFF)
            p = QPainter(img)
            self.assertTrue(dlg._draw_bands(p, 0, box, 72))
            self.assertTrue(dlg._draw_beside(p, 0, box, 72, extra=extra))
            p.end()
            k = box.width() / 612
            c = img.pixelColor(QPointF(box.x() + 700 * k, box.y() + 350 * k).toPoint())
            return box, (c.red(), c.green(), c.blue())
        box, c = printed()
        self.assertNotEqual(c, (0, 0, 255))                         # not printed
        dlg.beside.setCurrentIndex(1)                               # the same sheet
        box, c = printed()
        self.assertLess(box.width(), box0.width())
        self.assertEqual(c, (0, 0, 255))
        self.assertEqual(dlg.sheets([0, 1]), [(0, False), (1, False)])
        dlg.beside.setCurrentIndex(2)                               # an extra sheet
        self.assertEqual(dlg.sheets([0, 1]), [(0, False), (0, True), (1, False)])
        self.assertEqual(dlg.sheet(0)[1], box0)                     # the page at its size
        _box, c = printed(extra=True)
        self.assertEqual(c, (0, 0, 255))


class Asked(Gray):
    beside = False

    def test_asked_once_how_they_print(self):
        st = paths.settings()
        st.remove("ask_beside")
        self.w.set_tool("rect")
        pump()
        self.drag(self.pw, self.at((200, 500)), self.at((300, 560)))      # on the page
        self.assertIsNone(getattr(self.w, "_outside_box", None))
        self.drag(self.pw, self.at((560, 500)), self.at((700, 560)))      # partly beside it
        box = self.w._outside_box
        self.assertTrue(box.isVisible())
        self.assertIn("outside the page", box.text())
        box.checkBox().setChecked(True)                                  # Don't ask again
        next(b for b in box.buttons() if b.text() == "Extra sheet").click()
        pump()
        self.assertEqual(st.value("print_beside"), "extra")
        self.assertEqual(st.value("ask_beside"), "false")
        self.w._outside_box = None
        self.drag(self.pw, self.at((560, 600)), self.at((700, 660)))
        self.assertIsNone(self.w._outside_box)
        self.assertEqual(PrintDialog(None, self.v).beside.currentIndex(), 2)


if __name__ == "__main__":
    unittest.main()
