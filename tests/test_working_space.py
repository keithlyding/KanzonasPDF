"""View > Working space around pages (issue #82: "work in the free space around the page ...
for comments"): gray room around each page where markups kept outside the page are drawn, and
can be clicked, moved and drawn; they're saved, never printed. Off (the default), pages are
laid out and drawn exactly as before.

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
from PySide6.QtCore import QRectF  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import annotations as A  # noqa: E402
from kanzonas import page_widget  # noqa: E402
from kanzonas.main_window import MainWindow  # noqa: E402
from kanzonas.print_dialog import PrintDialog  # noqa: E402

BLUE = "#0000ff"
OUT = pymupdf.Rect(650, 300, 750, 400)          # beside the page's right edge (612 wide)


def pump(n=8):
    for _ in range(n):
        APP.processEvents()


def color(img, pt):
    c = img.pixelColor(pt.toPoint())
    return c.red(), c.green(), c.blue()


class WorkingSpace(unittest.TestCase):
    def setUp(self):
        A.reset_tool_props("rect")
        self.addCleanup(lambda: A.reset_tool_props("rect"))
        d = pymupdf.open()
        pg = d.new_page(width=612, height=792)
        pg.draw_rect((100, 100, 200, 200), color=(0, 0, 0), fill=(0, 0, 0))
        props = dict(A.DEFAULTS["rect"])
        props.update(fill=BLUE, stroke=BLUE)
        A.write(pg, {"kind": "rect", "rect": OUT, "text": "", "props": props})
        d.new_page(width=612, height=792)
        self.path = os.path.join(tempfile.mkdtemp(), "beside.pdf")
        d.save(self.path)
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

    def on(self):
        self.v.set_working_space(True)
        pump(20)

    def test_off_by_default_nothing_changes(self):
        if os.environ.get("KANZONAS_WORKING_SPACE") == "1":
            self.skipTest("the suite runs with the working space shown")
        self.assertFalse(self.v.working_space)
        self.assertEqual((self.pw.width(), self.pw.height()), (306, 396))
        self.assertEqual(self.pw.offset(), QPointF(0, 0))

    def test_shown_around_the_page_with_the_markup_kept_there(self):
        self.on()
        mx, my = 612 * page_widget.WS_X * 0.5, 792 * page_widget.WS_Y * 0.5
        self.assertEqual((self.pw.width(), self.pw.height()),
                         (306 + 2 * round(mx), 396 + 2 * round(my)))
        img = self.pw.grab().toImage()
        to = self.pw.to_screen_pt
        self.assertEqual(color(img, to(pymupdf.Point(150, 150))), (0, 0, 0))      # the drawing
        self.assertEqual(color(img, to(pymupdf.Point(400, 600))), (255, 255, 255))  # paper
        self.assertEqual(color(img, to(pymupdf.Point(700, 350))), (0, 0, 255))    # beside it
        ws = page_widget.WS_COLOR
        self.assertEqual(color(img, to(pymupdf.Point(700, 600))),
                         (ws.red(), ws.green(), ws.blue()))                       # gray room
        # widget <-> page both ways, outside the page too
        for pt in (pymupdf.Point(700, 350), pymupdf.Point(-50, -20), pymupdf.Point(300, 400)):
            back = self.pw.to_pdf(to(pt))
            self.assertAlmostEqual(abs(back - pt), 0, delta=0.01)
        # turned off again: as before
        self.v.set_working_space(False)
        pump()
        self.assertEqual((self.pw.width(), self.pw.height()), (306, 396))

    def send(self, kind, pt, buttons):
        pos = self.pw.to_screen_pt(pymupdf.Point(pt))
        ev = QMouseEvent(kind, pos, self.pw.mapToGlobal(pos), Qt.LeftButton, buttons,
                         Qt.NoModifier)
        {QEvent.MouseButtonPress: self.pw.mousePressEvent,
         QEvent.MouseMove: self.pw.mouseMoveEvent,
         QEvent.MouseButtonRelease: self.pw.mouseReleaseEvent}[kind](ev)
        pump(2)

    def drag(self, a, b):
        self.send(QEvent.MouseButtonPress, a, Qt.LeftButton)
        self.send(QEvent.MouseMove, ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2), Qt.LeftButton)
        self.send(QEvent.MouseMove, b, Qt.LeftButton)
        self.send(QEvent.MouseButtonRelease, b, Qt.NoButton)

    def test_clicked_moved_and_drawn_in_the_working_space(self):
        self.on()
        self.w.set_tool("select")
        pump()
        self.send(QEvent.MouseButtonPress, (700, 350), Qt.LeftButton)
        self.send(QEvent.MouseButtonRelease, (700, 350), Qt.NoButton)
        self.assertIsNotNone(self.v.selection)
        self.assertEqual(self.v.selected_model["kind"], "rect")
        self.drag((700, 350), (700, 500))                   # moved down, still beside
        pg = self.v.doc[0]                  # (kept while its markups are read)
        r = next(pg.annots()).rect
        self.assertAlmostEqual(r.y0, 449, delta=3)
        self.assertGreater(r.x0, 612)
        # a box drawn in the working space
        self.w.set_tool("rect")
        pump()
        self.drag((-150, 100), (-50, 200))
        pg = self.v.doc[0]
        rects = [a.rect for a in pg.annots()]
        self.assertTrue(any(x.x1 < 0 for x in rects), rects)

    def test_saved_not_printed(self):
        self.on()
        out = os.path.join(os.path.dirname(self.path), "saved.pdf")
        self.v.doc.save(out)
        self.assertEqual(len(A.outside_page(pymupdf.open(out)[0])), 1)      # kept
        dlg = PrintDialog(None, self.v)
        k = 72 / 72.0
        r = self.v.doc[0].rect
        img = QImage(int(r.width * k), int(r.height * k), QImage.Format_RGB32)
        img.fill(0xFFFFFFFF)
        p = QPainter(img)
        self.assertTrue(dlg._draw_bands(p, 0, QRectF(0, 0, img.width(), img.height()), 72))
        p.end()
        blue = sum(1 for x in range(0, img.width(), 4) for y in range(0, img.height(), 4)
                   if img.pixelColor(x, y).blue() > 200 and img.pixelColor(x, y).red() < 60)
        self.assertEqual(blue, 0)                           # the page only: not printed

    def test_going_to_a_page_shows_its_top(self):
        self.on()
        self.v.goto_page(1)
        pump()
        self.assertEqual(self.v.current_page(), 1)
        top = self.v.pages[1].y() + self.v.pages[1].offset().y()
        bar = self.v.verticalScrollBar().value()
        self.assertLess(abs(bar - (top - page_widget.PAGE_GAP if hasattr(page_widget, "PAGE_GAP")
                                   else top)), 40)


if __name__ == "__main__":
    unittest.main()
