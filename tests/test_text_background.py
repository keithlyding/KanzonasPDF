"""Text background: the page's own text highlighted in the page itself (a filled box drawn
behind its words, multiplied with what's under it, as a highlighter pen), not a Highlight
markup. Given with Properties > Text background (Edit objects, or Edit text / Add text with
the box open) or the box's bar button; it's each word's own (text_styles.Style.back), so it
moves, rewraps and is edited with its words, and Edit text reads it back from the page.

The owner, 22 Nov 2026: "There's a difference between a highlight markup and highlighting the
text to actually change it ... I could imagine things like that have their own use cases."

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_text_background
"""
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import text_edit, text_styles, undo_journal  # noqa: E402
from tests.test_text_objects_properties import TextObjects, pump  # noqa: E402
from tests.test_text_props_editing import Fixture  # noqa: E402

undo_journal.install()
YELLOW = 0xFFFF00


def backs(page):
    """{word: its background (sRGB, -1 none)} of the page's text, as Edit text reads it."""
    out = {}
    for _r, ln in text_edit.text_lines(page):
        st = text_styles.read_line(page, ln)
        for m in re.finditer(r"\S+", st.text):
            out[m.group()] = st.keys[m.start()].back
    return out


def a_page(back=YELLOW):
    d = pymupdf.open()
    p = d.new_page()
    p.draw_line((60, 96), (300, 96), color=(0, 0, 0), width=2)       # (crossing the words)
    p.insert_text((72, 100), "Plain words here", fontsize=12)
    p.insert_text((72, 200), "Other text", fontsize=12)
    (_r, ln), _other = text_edit.text_lines(p)
    text_edit.restyle_lines(p, [[ln]], lambda k: k._replace(back=back))
    return d, p


class OnThePage(unittest.TestCase):
    def test_drawn_behind_the_words_and_read_back(self):
        d, p = a_page()
        self.assertEqual(backs(p), {"Plain": YELLOW, "words": YELLOW, "here": YELLOW,
                                    "Other": -1, "text": -1})
        self.assertEqual(list(p.annots()), [])                 # (not a markup)
        p = pymupdf.open("pdf", d.tobytes())[0]                # (saved and opened)
        self.assertEqual(backs(p)["words"], YELLOW)
        pm = p.get_pixmap(dpi=144)
        self.assertEqual(pm.pixel(150, 203), (255, 255, 0))      # (under the P, by its stem)
        self.assertEqual(pm.pixel(150, 403), (255, 255, 255))
        dark = pm.pixel(2 * 250, 2 * 96)                       # (the line it crosses shows)
        self.assertLess(max(dark), 60)

    def test_moved_it_goes_along_and_none_takes_it_out(self):
        _d, p = a_page()
        lines = [ln for _r, ln in text_edit.text_lines(p) if "Plain" in text_edit.line_text(ln)]
        text_edit.move_lines(p, lines, (0, 300))
        self.assertEqual(backs(p)["words"], YELLOW)
        pm = p.get_pixmap()
        self.assertEqual(pm.pixel(75, 101), (255, 255, 255))    # (nothing left where it was)
        self.assertEqual(pm.pixel(75, 401), (255, 255, 0))
        lines = [ln for _r, ln in text_edit.text_lines(p) if "Plain" in text_edit.line_text(ln)]
        text_edit.restyle_lines(p, [lines], lambda k: k._replace(back=-1))
        self.assertEqual(backs(p)["words"], -1)
        self.assertEqual(p.get_pixmap().pixel(75, 401), (255, 255, 255))

    def test_an_underline_moves_and_takes_a_color_with_its_words(self):
        # (on main up to 1.15.21 a moved or recolored line was written in its main style:
        # its underline was lost and the bar stayed where the text had been)
        d = pymupdf.open()
        p = d.new_page()
        p.insert_text((72, 100), "Underlined words", fontsize=12)
        (_r, ln), = text_edit.text_lines(p)
        text_edit.restyle_lines(p, [[ln]], lambda k: k._replace(underline=True, strike=True))
        (_r, ln), = text_edit.text_lines(p)
        text_edit.move_lines(p, [ln], (0, 300))
        (_r, ln), = text_edit.text_lines(p)
        k = text_styles.read_line(p, ln).keys[0]
        self.assertEqual((k.underline, k.strike), (True, True))
        self.assertTrue(all(dr["rect"].y0 > 300 for dr in p.get_drawings()))
        text_edit.recolor_lines(p, [ln], (1, 0, 0))
        (_r, ln), = text_edit.text_lines(p)
        k = text_styles.read_line(p, ln).keys[0]
        self.assertEqual((k.underline, k.strike, k.color), (True, True, 0xFF0000))
        self.assertEqual(len(p.get_drawings()), 2)

    def test_diagonal_text_has_none_drawn(self):
        # (an underline on a diagonal watermark was drawn as the square around its slanted
        # bar, over the word; a background would have been the same)
        d = pymupdf.open()
        p = d.new_page()
        p.insert_text((200, 400), "COPY", fontsize=48,
                      morph=(pymupdf.Point(200, 400), pymupdf.Matrix(45)))
        (_r, ln), = text_edit.text_lines(p)
        text_edit.restyle_lines(p, [[ln]], lambda k: k._replace(underline=True, back=YELLOW))
        self.assertEqual(p.get_drawings(), [])
        (_r, ln), = text_edit.text_lines(p)
        self.assertEqual(text_edit.line_text(ln), "COPY")

    def test_a_table_cell_s_fill_is_not_a_background(self):
        d = pymupdf.open()
        p = d.new_page()
        p.draw_rect((60, 80, 400, 110), color=None, fill=(0.9, 0.9, 1))
        p.insert_text((72, 100), "In a cell", fontsize=12)
        self.assertEqual(set(backs(p).values()), {-1})


class InEditObjects(TextObjects):
    def test_properties_gives_and_takes_it(self):
        self.select(self.texts("Notes"))
        self.assertTrue(self.props.rows["text_back"][1].isVisible())
        self.assertTrue(self.props.no_back.isChecked())
        self.props.text_back.set_color("#ffff00")
        self.props.text_back.changed.emit()
        pump()
        got = backs(self.v.doc[0])
        self.assertEqual((got["Notes"], got["first"], got["Sheet"]), (YELLOW, YELLOW, -1))
        self.assertFalse(self.props.no_back.isChecked())
        self.click(self.props.no_back)
        self.assertEqual(backs(self.v.doc[0])["Notes"], -1)
        self.v.undo()
        pump()
        self.assertEqual(backs(self.v.doc[0])["Notes"], YELLOW)


class InTheBox(Fixture):
    def test_the_bar_button_and_properties_style_the_selected_words(self):
        self.add_text()
        self.finish()
        ed = self.open_word("world")
        self.select(ed, "world")
        ed.bar.buttons["back"].click()
        pump()
        self.assertTrue(ed.bar.buttons["back"].isChecked())
        self.assertEqual(self.w.props.text_back.color(), "#ffff00")
        self.select(ed, "added")
        self.w.props.text_back.set_color("#00ffff")
        self.w.props.text_back.changed.emit()
        pump()
        self.finish()
        got = backs(self.v.doc[0])
        self.assertEqual((got["world"], got["added"], got["Hello"]), (YELLOW, 0x00FFFF, -1))
        ed = self.open_word("Hello")             # (edited again, the words keep theirs)
        self.finish()
        got = backs(self.v.doc[0])
        self.assertEqual((got["world"], got["added"], got["Hello"]), (YELLOW, 0x00FFFF, -1))


if __name__ == "__main__":
    unittest.main()
