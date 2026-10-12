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


if __name__ == "__main__":
    unittest.main()
