"""A page looks the same however it's come to be drawn. MuPDF draws a picture from any decoded
copy of it it still has (from another page that shows all of it, or another zoom), and a copy
decoded for this page alone came out a few levels apart along its stripes: a picture pasted or
moved onto another page of the same document (Edit objects, CAD mode) looked different in the
view from the same page drawn afresh (random battery, seed 6). Decoding the pages' pictures
first for each render (1.9.1) wasn't enough: once MuPDF's store let that copy go, a page drawn
again decoded its picture another way than a view opened afresh did (1.10, seed 2103). Now a
page's content is drawn with its pictures read and decoded afresh, as a document just opened
draws them (PageWidget._content).

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_render_order
"""
import os
import random
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import page_widget  # noqa: E402
import kanzonas.document_view as DV  # noqa: E402
from tests.battery_random import _differ  # noqa: E402


def scan_like(fmt):
    """A picture like a scanned page: paper with colored stripes."""
    rnd = random.Random(2)
    pm = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 425, 550), False)
    pm.set_rect(pm.irect, (250, 250, 245))
    for _ in range(14):
        x, y = rnd.randrange(425), rnd.randrange(550)
        pm.set_rect(pymupdf.IRect(x, y, x + rnd.randint(5, 140), y + rnd.randint(2, 12)),
                    tuple(rnd.randrange(256) for _ in range(3)))
    return pm.tobytes(fmt)


def shared_picture(path, fmt):
    """Page 1 shows the whole picture; page 2 (smaller) the same picture object, partly off
    it, as a picture moved there in the same document is."""
    d = pymupdf.open()
    d.new_page(width=612, height=792)
    d.new_page(width=562, height=742)
    x = d[0].insert_image((0, 0, 612, 792), stream=scan_like(fmt))
    d[1].insert_image(pymupdf.Rect(187, 227, 799, 1019), xref=x)
    d.save(path)
    d.close()


class RenderOrder(unittest.TestCase):
    def drawn(self, path, pages, zoom=0.5):
        """Page 2 as a view draws it after drawing pages."""
        pymupdf.TOOLS.store_shrink(100)         # (nothing decoded before)
        v = DV.DocumentView(path)
        try:
            v.resize(900, 700)
            v.set_zoom(zoom)
            for i in pages:
                page_widget.check_content(v, i)
                v.pages[i]._render()
            return v.pages[1]._pix.toImage()
        finally:
            v.dirty = False
            v.close_doc()
            v.deleteLater()

    def test_a_picture_shared_with_another_page_looks_the_same(self):
        for fmt in ("png", "jpg"):
            path = os.path.join(tempfile.mkdtemp(), "shared.pdf")
            shared_picture(path, fmt)
            alone = self.drawn(path, [1])
            after = self.drawn(path, [0, 1])
            self.assertFalse(_differ(alone, after), fmt)

    def test_a_zoom_drawn_before_doesnt_change_the_page(self):
        path = os.path.join(tempfile.mkdtemp(), "zoom.pdf")
        shared_picture(path, "jpg")
        pymupdf.TOOLS.store_shrink(100)
        v = DV.DocumentView(path)
        try:
            v.resize(900, 700)
            v.set_zoom(1.0)
            page_widget.check_content(v, 1)
            v.pages[1]._render()
            v.set_zoom(0.25)
            page_widget.check_content(v, 1)
            v.pages[1]._render()
            zoomed = v.pages[1]._pix.toImage()
        finally:
            v.dirty = False
            v.close_doc()
            v.deleteLater()
        self.assertFalse(_differ(zoomed, self.drawn(path, [1], zoom=0.25)))

    def test_a_page_drawn_again_after_its_pictures_were_let_go(self):
        # (1.10, random battery seed 2103 --tagged: a picture cropped partly off its page was
        # decoded whole for the page once (1.9.1's predecode); MuPDF's store let that go and
        # the page was drawn again, its picture now decoded only where it shows, while a
        # view opened afresh decoded it whole: a pixel apart along its stripes)
        path = os.path.join(tempfile.mkdtemp(), "cropped.pdf")
        d = pymupdf.open()
        d.new_page(width=792, height=612)
        page = d[0]
        page.insert_image(page.rect, stream=scan_like("png"))
        page.set_cropbox(pymupdf.Rect(36.7, 36.7, 755.3, 575.3))
        d.save(path)
        d.close()
        pymupdf.TOOLS.store_shrink(100)
        v = DV.DocumentView(path)
        try:
            v.resize(900, 700)
            v.set_zoom(0.8737)
            page_widget.check_content(v, 0)
            v.pages[0]._render()
            # memory runs short: MuPDF's store and the view's renders let go of the page
            pymupdf.TOOLS.store_shrink(100)
            v._rc.drop_page(0)
            v.pages[0]._render()
            again = v.pages[0]._pix.toImage()
        finally:
            v.dirty = False
            v.close_doc()
            v.deleteLater()
        pymupdf.TOOLS.store_shrink(100)
        v = DV.DocumentView(path)
        try:
            v.resize(900, 700)
            v.set_zoom(0.8737)
            page_widget.check_content(v, 0)
            v.pages[0]._render()
            fresh = v.pages[0]._pix.toImage()
        finally:
            v.dirty = False
            v.close_doc()
            v.deleteLater()
        self.assertFalse(_differ(again, fresh))


if __name__ == "__main__":
    unittest.main()
