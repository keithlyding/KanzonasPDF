"""Recognize text on a page scanned upside down: the text layer lies over the letters it
reads, so Search & redact blacks out the number in the scan itself.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_ocr_orientation
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf as F  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import ocr  # noqa: E402
from kanzonas.document_view import DocumentView  # noqa: E402

R = F.Rect
SECRET = "4471-2290-18"


class ReadingOrder(unittest.TestCase):
    """The engine gives a line's corners as they lie in the picture; the text layer needs
    them in reading order."""

    def test_corners(self):
        box = [[10, 10], [110, 10], [110, 30], [10, 30]]            # a wide line
        self.assertEqual(ocr._reading_order(box, False), box)
        self.assertEqual(ocr._reading_order(box, True), box[2:] + box[:2])
        tall = [[10, 10], [30, 10], [30, 110], [10, 110]]           # read turned a quarter
        self.assertEqual(ocr._reading_order(tall, False), tall[1:] + tall[:1])
        self.assertEqual(ocr._reading_order(tall, True), tall[3:] + tall[:3])

    def test_upside_down_page(self):
        upright = ([[10, 10], [110, 10], [110, 30], [10, 30]], "Account", 0.9)
        turned = ([[110, 30], [10, 30], [10, 10], [110, 10]], "number", 0.9)
        self.assertTrue(ocr.upside_down([turned, turned, upright]))
        self.assertFalse(ocr.upside_down([turned, upright, upright]))
        self.assertFalse(ocr.mostly_vertical([turned, turned]))

    def test_text_layer_over_an_upside_down_line(self):
        doc = F.open()
        page = doc.new_page()

        class Image:                    # image pixels = displayed page points
            def to_display(self, x, y):
                return F.Point(x, y)
        # "SECRET" upside down at (300..400, 500..520): it starts at the right
        box = ocr._reading_order([[300, 500], [400, 500], [400, 520], [300, 520]], True)
        ocr.add_text_layer(page, [(box, SECRET, 0.95)], Image())
        hit = page.search_for(SECRET)[0]
        self.assertTrue(R(298, 498, 402, 522).contains(hit), hit)
        self.assertGreater(hit.width, 80)


class UpsideDownScan(unittest.TestCase):
    def scan(self):
        """A letter scanned upside down, and the box of the account number's ink on it."""
        d = F.open()
        p = d.new_page()
        lines = ["KANZONAS CONSTRUCTION", "RE: Change Order 14 - Level 2 framing",
                 "Please find attached the revised framing plan for the east wing.",
                 f"Account number {SECRET} should be used for this invoice.",
                 "Sincerely, K. Lyding"]
        for k, t in enumerate(lines):
            p.insert_text((72, 100 + 26 * k), t, fontsize=12, fontname="tiro")
        word = R(p.search_for(SECRET)[0])
        W, H = p.rect.width, p.rect.height
        pm = p.get_pixmap(dpi=200, colorspace=F.csGRAY)
        scan = F.open()
        s = scan.new_page(width=W, height=H)
        s.insert_image(s.rect, pixmap=pm, rotate=180)
        path = os.path.join(tempfile.mkdtemp(), "upside_down.pdf")
        scan.save(path)
        where = R(W - word.x1, H - word.y1, W - word.x0, H - word.y0)
        return path, self.ink(scan[0], where)

    def ink(self, page, area):
        """The bounding box of the dark pixels in area (page points)."""
        pm = page.get_pixmap(dpi=144, clip=area, colorspace=F.csGRAY)
        dark = [(i % pm.width, i // pm.width) for i, v in enumerate(pm.samples) if v < 128]
        k = 72 / 144
        return R(area.x0 + min(x for x, _ in dark) * k, area.y0 + min(y for _, y in dark) * k,
                 area.x0 + (max(x for x, _ in dark) + 1) * k,
                 area.y0 + (max(y for _, y in dark) + 1) * k)

    def test_search_and_redact_covers_the_number(self):
        path, ink = self.scan()
        v = DocumentView(path)
        self.addCleanup(v.close_doc)
        v.run_ocr([0], "normal")
        hits = v.doc[0].search_for(SECRET)
        self.assertEqual(len(hits), 1)
        self.assertTrue(hits[0].intersects(ink))
        self.assertEqual(v.search_redact(SECRET), 1)
        v.apply_redactions(True)
        pm = v.doc[0].get_pixmap(dpi=144, clip=ink, colorspace=F.csGRAY)
        light = sum(1 for b in pm.samples if b > 100)
        self.assertLess(light, 0.02 * len(pm.samples))       # all black: nothing readable

    def test_sideways_lines_found_where_they_are(self):
        """Lines standing up on a sheet (the engine reads them turned a quarter)."""
        d = F.open()
        p = d.new_page()
        for k, t in enumerate(["Sideways drawing note one", f"Account number {SECRET} here",
                               "Third line of the sideways text"]):
            p.insert_text((150 + 26 * k, 600), t, fontsize=12, rotate=90)
        for k in range(6):
            p.insert_text((300, 400 + 20 * k), f"Upright words number {k} on the sheet", fontsize=11)
        want = p.search_for(SECRET)[0]
        scan = F.open()
        s = scan.new_page()
        s.insert_image(s.rect, pixmap=p.get_pixmap(dpi=200, colorspace=F.csGRAY))
        path = os.path.join(tempfile.mkdtemp(), "sideways.pdf")
        scan.save(path)
        v = DocumentView(path)
        self.addCleanup(v.close_doc)
        v.run_ocr([0], "normal")
        hits = v.doc[0].search_for(SECRET)
        self.assertEqual(len(hits), 1)
        self.assertGreater(abs(hits[0] & want), 0.6 * abs(want))


if __name__ == "__main__":
    unittest.main()
