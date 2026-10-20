"""Compare documents lines up a revision whose drawing moved on the sheet, so only the real
change is reported instead of every line.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_compare_align
"""
import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pymupdf as F  # noqa: E402

from kanzonas import compare  # noqa: E402


def drawing(dx=0, dy=0, extra=False, w=1224, h=792):
    d = F.open()
    pg = d.new_page(width=w, height=h)
    for i in range(40):
        x, y = 60 + (i * 97) % 1000 + dx, 60 + (i * 53) % 600 + dy
        pg.draw_rect(F.Rect(x, y, x + 80, y + 40), color=(0, 0, 0), width=1)
        pg.insert_text((x + 4, y + 20), f"Room {i}", fontsize=8)
    if extra:
        pg.draw_circle((600 + dx, 720 + dy), 30, color=(0, 0, 0), width=2)
    return d.tobytes()


class CompareAlign(unittest.TestCase):
    def test_moved_sheet_shows_only_the_real_change(self):
        old, new = drawing(), drawing(dx=14, dy=-9, extra=True)
        _data, plain = compare.compare(old, new, align=False)
        t = time.time()
        data, aligned = compare.compare(old, new)
        self.assertLess(time.time() - t, 10)
        self.assertGreater(plain[0], 10)            # unaligned: everything looks changed
        self.assertEqual(aligned[0], 1)             # aligned: just the added circle
        self.assertIn("sits +13.7 pt right and +9.2 pt up", F.open(stream=data)[0].get_text())

    def test_unmoved_sheet_not_shifted(self):
        old, new = drawing(), drawing(extra=True)
        data, counts = compare.compare(old, new)
        self.assertEqual(counts[0], 1)
        self.assertNotIn("Lined up", F.open(stream=data)[0].get_text())

    def test_unrelated_pages_not_forced_together(self):
        a = F.open()
        a.new_page().insert_text((72, 72), "Only text here", fontsize=20)
        b = F.open()
        b.new_page().draw_rect(F.Rect(300, 500, 500, 700), color=(0, 0, 0), fill=(0, 0, 0))
        data, _ = compare.compare(a.tobytes(), b.tobytes())
        self.assertNotIn("Lined up", F.open(stream=data)[0].get_text())




def replot(src_bytes, w_in, h_in, extra=None):
    """The first page of src printed fitted onto another paper size (as a plotter does)."""
    src = F.open(stream=src_bytes)
    out = F.open()
    pg = out.new_page(width=w_in * 72, height=h_in * 72)
    pg.show_pdf_page(pg.rect, src, 0)
    if extra:
        extra(pg)
    return out.tobytes()


def sheet():
    """A 36x24 inch sheet with a border, many thin lines and small text, like a plot."""
    d = F.open()
    pg = d.new_page(width=36 * 72, height=24 * 72)
    pg.draw_rect(F.Rect(36, 36, 36 * 72 - 36, 24 * 72 - 36), color=(0, 0, 0), width=1.5)
    for i in range(60):
        x, y = 100 + (i * 131) % 2300, 100 + (i * 71) % 1500
        pg.draw_rect(F.Rect(x, y, x + 150, y + 90), color=(0, 0, 0), width=0.5)
        pg.draw_line(F.Point(x, y), F.Point(x + 150, y + 90), color=(0, 0, 0), width=0.3)
        pg.insert_text((x + 6, y + 20), f"ROOM {i:03d}  12'-6\"", fontsize=7)
    return d.tobytes()


class ComparePaperSizes(unittest.TestCase):
    """The same drawing printed at another paper size is not a changed drawing."""

    def test_half_size_print_shows_no_changes(self):
        old = sheet()
        data, counts = compare.compare(old, replot(old, 18, 12))
        self.assertEqual(counts, [0])
        text = F.open(stream=data)[0].get_text()
        self.assertIn("NEW is 18.0 x 12.0 in, OLD 36.0 x 24.0 in", text)
        self.assertIn("scaled x2 to OLD's size", text)

    def test_print_fitted_to_a_paper_of_another_shape(self):
        # 11x17 and ANSI D are not 3:2 like the 36x24 sheet: the fit is smaller than the
        # paper ratio says, and the drawing sits centered on the sheet
        old = sheet()
        for w, h in ((17, 11), (34, 22), (48, 36)):
            with self.subTest(paper=(w, h)):
                _data, counts = compare.compare(old, replot(old, w, h))
                self.assertEqual(counts, [0])

    def test_a_real_change_on_a_reduced_print_is_still_found(self):
        old = sheet()
        new = replot(old, 17, 11, extra=lambda pg: pg.draw_rect(
            F.Rect(700, 300, 760, 340), color=(0, 0, 0), fill=(0, 0, 0)))
        data, counts = compare.compare(old, new)
        self.assertEqual(counts, [1])
        res = F.open(stream=data)[0]
        change = next(a for a in res.annots())
        self.assertIn("added", change.info["content"])
        # the box on the 11x17 print sits where it would on the 36x24 sheet (scale 24/11,
        # centered sideways): about x 1480-1610, y 655-740
        self.assertTrue(F.Rect(1400, 600, 1700, 800).contains(change.rect), change.rect)

    def test_same_size_pages_are_not_scaled(self):
        old, new = drawing(), drawing(extra=True)
        data, counts = compare.compare(old, new)
        self.assertEqual(counts[0], 1)
        self.assertNotIn("scaled", F.open(stream=data)[0].get_text())
        self.assertEqual(compare.page_scale(F.Rect(0, 0, 612, 792), F.Rect(0, 0, 612, 792)), 1.0)
        self.assertAlmostEqual(compare.page_scale(F.Rect(0, 0, 2592, 1728), F.Rect(0, 0, 1224, 792)),
                               min(2592 / 1224, 1728 / 792))


if __name__ == "__main__":
    unittest.main()
