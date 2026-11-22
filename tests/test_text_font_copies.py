"""Text written again (Text color, moved, Edit text) in a font the page has several copies of
uses a copy that draws its letters. Save cuts each embedded font down to the letters its text
uses: the copy left for one line still answers "yes" for the other letters, but they're empty
shells. A line added later in the same font, then recolored or moved, was written with that
copy and drew nothing (on main up to 1.15.19: ink 856 -> 0).

Found by the random battery, seed 13 (22 Nov 2026), step 1167: "text that wasn't selected
lost letters" after Text color on a turned, cropped page. The owner: "If we know about a bug,
we need to fix it."

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_text_font_copies
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402

from kanzonas import text_edit, undo_journal  # noqa: E402

undo_journal.install()
HELV = pymupdf.Font("helv").buffer


def a_page():
    """'on a layer' written and saved (its font cut down to those letters), then
    'SHEET NO: R-3' written with a whole copy of the same font."""
    d = pymupdf.open()
    p = d.new_page()
    p.insert_font(fontname="KZA", fontbuffer=HELV)
    p.insert_text((72, 100), "on a layer", fontname="KZA", fontsize=12)
    d.subset_fonts()
    d = pymupdf.open("pdf", d.tobytes())
    p = d[0]
    p.insert_font(fontname="KZB", fontbuffer=HELV + b"\0")
    p.insert_text((72, 200), "SHEET NO: R-3", fontname="KZB", fontsize=12)
    return d


def sheet(p):
    return [(r, ln) for r, ln in text_edit.text_lines(p) if "SHEET" in text_edit.line_text(ln)]


def ink(p, rect):
    pm = p.get_pixmap(clip=rect + (-2, -2, 2, 2), dpi=144, colorspace=pymupdf.csGRAY)
    return sum(1 for b in pm.samples if b < 128)


class FontCopies(unittest.TestCase):
    def setUp(self):
        self.d = a_page()
        self.p = self.d[0]
        (self.rect, self.line), = sheet(self.p)
        self.ink = ink(self.p, self.rect)
        self.assertGreater(self.ink, 300)

    def check(self, rect):
        got = sheet(self.p)
        self.assertEqual(len(got), 1)
        self.assertAlmostEqual(got[0][0].width, self.rect.width, delta=0.05)
        self.assertEqual(ink(self.p, rect), self.ink)

    def test_the_cut_down_copy_doesnt_draw_the_new_letters(self):
        x = [f[0] for f in self.p.get_fonts(full=True) if "+" in f[3]][0]
        cut = pymupdf.Font(fontbuffer=self.d.extract_font(x)[3])
        self.assertTrue(cut.has_glyph(ord("S")))                 # (it says it has them)
        self.assertFalse(text_edit.draws_letters(cut, "SHEET"))
        self.assertTrue(text_edit.draws_letters(cut, "on a layer"))
        self.assertTrue(text_edit.draws_letters(pymupdf.Font("helv"), "SHEET NO: R-3"))

    def test_text_color(self):
        text_edit.recolor_lines(self.p, [self.line], (0, 0, 0))
        self.check(self.rect)

    def test_moved(self):
        text_edit.move_lines(self.p, [self.line], (0, 60))
        self.check(self.rect + (0, 60, 0, 60))

    def test_edit_text(self):
        text_edit.replace_line(self.p, self.line, "SHEET NO: R-3")
        self.check(self.rect)

    def test_the_other_line_is_as_it_was(self):
        (r, _ln), = [(r, ln) for r, ln in text_edit.text_lines(self.p)
                     if "layer" in text_edit.line_text(ln)]
        before = ink(self.p, r)
        text_edit.move_lines(self.p, [self.line], (0, 60))
        self.assertEqual(ink(self.p, r), before)


if __name__ == "__main__":
    unittest.main()
