"""The page's own text, read for Edit text and Edit objects (text_edit.page_textpage), keeps
every letter inside the page, whatever else is on it. MuPDF's TEXT_MEDIABOX_CLIP, reading a
display list, dropped glyphs of right-to-left text on a turned page: the first letter of
"delta hotel bravo" always, and the whole line once a drawing group elsewhere on the page was
deleted. The text was still there and still drawn, but Edit text and Edit objects no longer
saw it (random battery, seed 1112, step 1076, 13 Nov 2026; also in 1.13). The page box is now
asked of MuPDF as a clip rectangle.

tests/fixtures/turned_rtl_text_and_group.pdf is that page, cut out of the battery's document.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_text_page_clip
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pymupdf  # noqa: E402

from kanzonas import page_objects, text_edit  # noqa: E402

PDF = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures",
                   "turned_rtl_text_and_group.pdf")


def lines_with(page, word):
    return [text_edit.line_text(ln) for _r, ln in text_edit.text_lines(page)
            if word in text_edit.line_text(ln)]


class TextPageClip(unittest.TestCase):
    def setUp(self):
        self.doc = pymupdf.open(PDF)
        self.page = self.doc[0]
        self.assertEqual(self.page.rotation, 90)

    def test_every_letter_read(self):
        self.assertEqual(lines_with(self.page, "hotel"), ["delta hotel bravo"])

    def test_still_read_after_a_group_elsewhere_is_deleted(self):
        objs = page_objects.Objects(self.page)
        groups = [it for it in objs.items if it["kind"] == "group"]
        self.assertEqual(len(groups), 1)
        self.assertFalse(groups[0]["rect"].intersects(
            pymupdf.Rect(447, 457, 544, 472)))      # (the line isn't in the group)
        page_objects.delete(self.page, [groups[0]["n"]], objs)
        self.assertEqual(lines_with(self.page, "hotel"), ["delta hotel bravo"])

    def test_text_past_the_page_box_is_still_left_out(self):
        # (what the page box clip is for: text written outside the page isn't the page's)
        d = pymupdf.open()
        pg = d.new_page(width=300, height=300)
        pg.insert_text((20, 50), "inside the page", fontsize=12)
        pg.insert_text((20, 400), "below the page", fontsize=12)
        got = [text_edit.line_text(ln) for _r, ln in text_edit.text_lines(pg)]
        self.assertIn("inside the page", got)
        self.assertNotIn("below the page", got)

    def test_a_clip_asked_for_stays_inside_the_page(self):
        tp, _flags = text_edit.page_textpage(self.page, pymupdf.TEXTFLAGS_DICT,
                                             clip=pymupdf.Rect(400, 440, 2000, 500))
        self.assertIn("delta hotel bravo", tp.extractText())


if __name__ == "__main__":
    unittest.main()
