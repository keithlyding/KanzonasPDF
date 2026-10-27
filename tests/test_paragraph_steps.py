"""Edit text on documents like an appliance manual, a permit and a product wiki: numbered
steps with no space between them, "(a)" set apart before its text, Wingdings bullets, a list
of one-line items with drawn bullets, a table's cells, and the outline under the pointer
showing what a click edits.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_paragraph_steps
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import text_edit  # noqa: E402
from kanzonas.document_view import DocumentView  # noqa: E402

STEP = 15.6


def page_with(rows, size=12):
    """A page with these (x, text) rows, one under the other."""
    d = pymupdf.open()
    p = d.new_page()
    for i, (x, t) in enumerate(rows):
        if t:
            p.insert_text((x, 100 + STEP * i), t, fontsize=size)
    return d, p


def para_of(p, needle):
    lines = text_edit.text_lines(p)
    ln = next(ln for _r, ln in lines if needle in text_edit.line_text(ln))
    got = text_edit.paragraph_at(lines, ln)
    return None if got is None else [text_edit.line_text(x).strip() for x in got]


class Steps(unittest.TestCase):
    def test_numbered_steps_without_space_between_them(self):
        _d, p = page_with([
            (54, "1.Remove the Porcelain Grills, Grease Drain Pan and Heat Baffle from the"),
            (54, "interior of the grill before you start it the very first time."),
            (54, "2.Open the Pellet Hopper Lid, make sure there are no foreign objects in"),
            (54, "the Auger and Hopper."),
            (54, "3.With the Switch in the OFF position, plug the power cord into a 110"),
            (54, "Volt AC grounded outlet near the grill and turn it on."),
        ])
        two = ["2.Open the Pellet Hopper Lid, make sure there are no foreign objects in",
               "the Auger and Hopper."]
        self.assertEqual(para_of(p, "2.Open"), two)
        self.assertEqual(para_of(p, "the Auger and"), two)
        self.assertEqual(len(para_of(p, "Volt AC") or []), 2)

    def test_a_paragraph_ends_at_its_short_last_line(self):
        _d, p = page_with([
            (54, "Turn on your grill and turn the Temperature Dial to the SMOKE position and"),
            (54, "check the following things."),
            (54, "Hold your fingers above the Firepot to confirm the fan is blowing air through"),
            (54, "the Firepot and the hot rod is heating up as it should be doing now."),
        ])
        self.assertEqual(len(para_of(p, "check the following") or []), 2)
        self.assertEqual(len(para_of(p, "the Firepot and") or []), 2)

    def test_label_set_apart_before_the_first_line(self):
        words = ("The permittee shall pay an annual Title V fee in accordance with the rule "
                 "based upon the applicable base fee; the applicable permit modification fees; "
                 "the responsible official's choice of actual emissions, allowable emissions, "
                 "or a combination of actual and allowable emissions for the year.").split()
        rows, cur = [], []
        for w in words:            # wrapped as a word processor does: first line set in
            room = 460 - (108 if not rows else 72)
            if cur and pymupdf.get_text_length(" ".join(cur + [w]), fontsize=10) > room:
                rows.append(" ".join(cur))
                cur = [w]
            else:
                cur.append(w)
        rows.append(" ".join(cur))
        d = pymupdf.open()
        p = d.new_page()
        p.insert_text((72, 100), "(a)", fontsize=10)
        y = 100
        for i, t in enumerate(rows):
            p.insert_text((108 if i == 0 else 72, y), t, fontsize=10)
            y += 11.5
        p.insert_text((72, y), "(b)", fontsize=10)
        p.insert_text((108, y), "Title V sources shall pay allowable based emission fees until", fontsize=10)
        self.assertEqual(len(rows), 4, rows)
        for needle in ("The permittee", rows[2][:20], rows[3][:20]):
            got = para_of(p, needle)
            self.assertEqual(len(got or []), 4, needle)
            self.assertTrue(got[0].startswith("The permittee"), got)

    def test_symbol_font_bullets_are_list_markers(self):
        for bullet in ("", "▪", "➢"):
            self.assertTrue(text_edit._MARKER.match(bullet + " Hold your fingers"), bullet)
        self.assertTrue(text_edit._MARKER.match("1.Turn the Platform"))
        self.assertFalse(text_edit._MARKER.match("U.S. Army Corps"))

    def test_one_line_items_with_drawn_bullets_stay_items(self):
        _d, p = page_with([
            (57, "10-point capacitive touch with toughened glass panel, hardness up to 6H."),
            (57, "With the operating temperature of -5~60C, it can be widely applied."),
            (57, "Adopting optical bonding technology for a better display of images."),
        ], size=10)
        self.assertIsNone(para_of(p, "With the operating"))


class TableCells(unittest.TestCase):
    def test_a_cell_beside_a_label_is_one_paragraph(self):
        d = pymupdf.open()
        p = d.new_page()
        cell = ["Grill temperature is influenced by", "environmental factors such as high",
                "temperature, wind and direct sun.", "Place unit in shaded area. Open the lid",
                "to reduce inside temperature. After", "start your grill in 40 minutes, the grill",
                "will reach your desired temperature."]
        for i, t in enumerate(cell):
            p.insert_text((330, 100 + STEP * i), t, fontsize=12)
        p.insert_text((232, 100 + STEP * 3), "External Factor", fontsize=12)
        self.assertEqual(len(para_of(p, "Place unit") or []), 7)
        self.assertEqual(len(para_of(p, "Grill temperature") or []), 7)


class HoverOutline(unittest.TestCase):
    def test_the_outline_shows_what_a_click_edits(self):
        d, _p = page_with([
            (54, "Turn on your grill and turn the Temperature Dial to the SMOKE position and"),
            (54, "check the following things before you go on with the next step here."),
            (54, "Then wait."),
        ])
        path = os.path.join(tempfile.mkdtemp(), "h.pdf")
        d.save(path)
        v = DocumentView(path)
        self.addCleanup(v.close_doc)
        pt = pymupdf.Point(100, 100 + STEP - 3)
        para = v.text_target_rect(0, pt)
        line = v.text_target_rect(0, pt, one_line=True)
        self.assertGreater(para.height, 1.6 * line.height)      # the whole paragraph
        self.assertEqual(line, v.text_line_rect(0, pt))         # Alt: the line


if __name__ == "__main__":
    unittest.main()
