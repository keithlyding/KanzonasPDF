"""The page's own text in Properties, and what Properties says it is changing.

Properties tags what's selected or about to be added: "Markup: on top of the page" for
markups (a Highlight, a line drawn with the Line tool...) and "Page content: changes the page
itself" for the page's own text, lines and pictures (Add text, Edit text, Edit objects, the
Image tool). While Edit text or Add text has its box open, Properties has the box's Underline,
Strikethrough and Text color next to Bold and Italic: they change the selected words, drawn
into the page (not an Underline markup).

The owner, 22 Nov 2026: "We need to do the same thing for text. Put it in the properties panel
on the right. All the things that can be done to edit text ... there needs to be a way of
differentiating whether what's being edited and added is a markup vs a document change."

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_page_text_properties
"""
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import text_edit, text_styles  # noqa: E402
from tests.test_text_props_editing import Fixture, pump  # noqa: E402


def decorations(page):
    """{word: (underline, strike, color)} of the page's text, as Edit text reads it."""
    out = {}
    for _r, ln in text_edit.text_lines(page):
        st = text_styles.read_line(page, ln)
        for m in re.finditer(r"\S+", st.text):
            k = st.keys[m.start()]
            out[m.group()] = (k.underline, k.strike, k.color)
    return out


class Tag(Fixture):
    def tag(self):
        t = self.w.props.tag
        return t.text() if t.isVisibleTo(self.w.props) else None

    def test_markup_tools_and_page_tools_say_which_they_are(self):
        for tool in ("highlight", "line", "rect", "note"):
            self.w.set_tool(tool)
            pump()
            self.assertIn("Markup", self.tag(), tool)
        for tool in ("addtext", "edittext", "editobjects"):
            self.w.set_tool(tool)
            pump()
            self.assertIn("Page content", self.tag(), tool)

    def test_a_selected_markup_and_the_page_s_own_objects(self):
        p = self.v.doc[0]
        self.v.modify(lambda: p.add_line_annot((100, 300), (300, 300)).update(), [0])
        p = self.v.doc[0]
        self.w.set_tool("select")
        pump()
        self.v.select_xref(0, p.first_annot.xref)
        pump()
        self.assertIsNotNone(self.v.selected_model)
        self.assertIn("Markup", self.tag())
        self.add_text()
        self.finish()
        self.w.set_tool("editobjects")
        pump()
        self.v.select_objects(0, list(self.v.text_objects(0)))
        pump()
        self.assertIn("Page content", self.tag())

    def test_nothing_to_set_no_tag(self):
        self.w.set_tool("capture")
        pump()
        self.assertIsNone(self.tag())


class UnderlineStrike(Fixture):
    def test_while_editing_they_change_the_selected_words_in_the_page(self):
        self.add_text()
        self.finish()
        ed = self.open_word("world")
        props = self.w.props
        self.assertTrue(props.underline.isVisible())
        self.assertTrue(props.strike.isVisible())
        self.assertTrue(props.text_color.isVisible())       # (Edit text has it too now)
        self.select(ed, "world")
        self.assertFalse(props.underline.isChecked())
        self.click_box(props.underline)
        self.assertIs(self.v._inline, ed)
        self.assertEqual(ed.text.textCursor().selectedText(), "world")
        self.assertTrue(props.underline.isChecked())
        self.select(ed, "added")
        self.assertFalse(props.underline.isChecked())       # (shows the selection's)
        self.click_box(props.strike)
        self.finish()
        got = decorations(self.v.doc[0])
        self.assertEqual(got["world"][:2], (True, False))
        self.assertEqual(got["added"][:2], (False, True))
        self.assertEqual(got["Hello"][:2], (False, False))
        self.assertEqual(list(self.v.doc[0].annots()), [])         # (no markup made)

    def test_text_color_while_editing(self):
        self.add_text()
        self.finish()
        ed = self.open_word("this")
        self.select(ed, "this")
        self.w.props.text_color.set_color("#ff0000")
        self.w.props._emit()
        pump()
        self.finish()
        got = decorations(self.v.doc[0])
        self.assertEqual(got["this"][2], 0xFF0000)
        self.assertEqual(got["world"][2], 0)

    def test_add_text_tool_settings_have_none_of_them_until_a_box_is_open(self):
        self.w.set_tool("addtext")
        pump()
        self.assertFalse(self.w.props.underline.isVisible())


if __name__ == "__main__":
    unittest.main()
