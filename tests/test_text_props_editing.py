"""While Edit text or Add text has its box open, Properties' Bold, Italic, Font size (and Add
text's Text color) change the words selected in the box, the selection stays selected, and
Properties shows the selected words' style; with nothing selected they change all the text in
the box. The tool's own settings stay as they were. (Before: clicking Bold in Properties
cleared the selection and did nothing.) The floating style bar shows pressed the styles all
the selected words have, in its own light colors.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_text_props_editing -t .
"""
import os
import re
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402
from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtGui import QTextCursor  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import annotations, text_edit, text_styles  # noqa: E402
from kanzonas.main_window import MainWindow  # noqa: E402
from tests.test_undo_journal import canon  # noqa: E402

TEXT = "Hello world this is added text"


def pump(n=5):
    for _ in range(n):
        APP.processEvents()


def word_styles(page):
    """[(word, bold, italic, size)] of the page's text, as Edit text reads it."""
    out = []
    for _r, ln in text_edit.text_lines(page):
        st = text_styles.read_line(page, ln)
        for m in re.finditer(r"\S+", st.text):
            k = st.keys[m.start()]
            out.append((m.group(), k.bold, k.italic, round(k.size, 1)))
    return out


class Fixture(unittest.TestCase):
    def setUp(self):
        for tool in ("addtext", "edittext"):
            annotations.reset_tool_props(tool)
        d = pymupdf.open()
        d.new_page()
        path = os.path.join(tempfile.mkdtemp(), "props.pdf")
        d.save(path)
        self.w = w = MainWindow()
        w.resize(1400, 900)
        w.show()
        pump()
        w.open_file(path)
        pump()
        self.v = w.view()
        self.pw = self.v.pages[0]
        self.at = self.pw.to_screen(pymupdf.Rect(100, 150, 100, 150)).topLeft().toPoint()

    def tearDown(self):
        self.w._close_confirmed = True
        self.w.close()
        pump()

    def click_page(self, pt):
        QTest.mouseClick(self.pw, Qt.LeftButton, Qt.NoModifier, pt)
        pump()

    def add_text(self, text=TEXT):
        self.w.set_tool("addtext")
        pump()
        self.click_page(self.at)
        QTest.keyClicks(self.v._inline.text, text)
        pump()
        return self.v._inline

    def finish(self):
        self.click_page(self.at + QPoint(0, 400))

    def open_word(self, word):
        """Edit text: click on the word on the page; the box that opens."""
        self.w.set_tool("edittext")
        pump()
        wd = next(x for x in self.v.doc[0].get_text("words") if x[4] == word)
        self.click_page(self.pw.to_screen(pymupdf.Rect(wd[:4])).center().toPoint())
        self.assertIsNotNone(self.v._inline)
        return self.v._inline

    def select(self, ed, word):
        """Double-click the word in the box, as a person selects it."""
        t = ed.text.toPlainText()
        tc = QTextCursor(ed.text.document())
        tc.setPosition(t.index(word) + 1)
        QTest.mouseDClick(ed.text.viewport(), Qt.LeftButton, Qt.NoModifier,
                          ed.text.cursorRect(tc).center())
        pump()
        self.assertEqual(ed.text.textCursor().selectedText(), word)

    def click_box(self, box):
        QTest.mouseClick(box, Qt.LeftButton, Qt.NoModifier, QPoint(5, box.height() // 2))
        pump()


class EditText(Fixture):
    def test_properties_style_the_selected_words_and_keep_them_selected(self):
        self.add_text()
        self.finish()
        ed = self.open_word("world")
        props = self.w.props
        self.select(ed, "world")
        self.assertFalse(props.bold.isChecked())
        self.click_box(props.bold)
        self.assertIs(self.v._inline, ed)                       # still editing
        self.assertEqual(ed.text.textCursor().selectedText(), "world")
        self.assertTrue(props.bold.isChecked())                 # shows the selection's style
        self.assertTrue(ed.bar.buttons["bold"].isChecked())     # the bar too
        self.select(ed, "this")
        self.assertFalse(props.bold.isChecked())
        self.click_box(props.italic)
        self.assertEqual(ed.text.textCursor().selectedText(), "this")
        self.select(ed, "added")
        props.fontsize.setValue(18)
        pump()
        self.assertEqual(ed.text.textCursor().selectedText(), "added")
        self.finish()
        got = {w: (b, i, s) for w, b, i, s in word_styles(self.v.doc[0])}
        self.assertEqual(got["world"], (True, False, 12.0))
        self.assertEqual(got["this"], (False, True, 12.0))
        self.assertEqual(got["added"], (False, False, 18.0))
        self.assertEqual(got["Hello"], (False, False, 12.0))
        # the tool's settings are as they were; Properties shows them again
        p = annotations.tool_props("edittext")
        self.assertEqual((p["bold"], p["italic"], float(p["fontsize"])), (False, False, 0.0))
        self.assertFalse(props.bold.isChecked())

    def test_nothing_selected_styles_all_the_text(self):
        self.add_text()
        self.finish()
        ed = self.open_word("Hello")
        self.assertEqual(ed.text.textCursor().selectedText(), "")
        self.click_box(self.w.props.bold)
        QTest.keyClick(ed.text, Qt.Key_Return)
        pump()
        self.assertTrue(all(b for _w, b, _i, _s in word_styles(self.v.doc[0])))

    def test_undo_takes_the_styled_edit_back_whole(self):
        self.add_text()
        self.finish()
        before = canon(self.v.doc)
        ed = self.open_word("world")
        self.select(ed, "world")
        self.click_box(self.w.props.bold)
        self.finish()
        self.assertTrue(dict((w, b) for w, b, _i, _s in word_styles(self.v.doc[0]))["world"])
        self.v.undo()
        pump()
        self.assertEqual(canon(self.v.doc), before)


class AddText(Fixture):
    def test_properties_style_the_words_being_typed(self):
        ed = self.add_text()
        self.select(ed, "added")
        self.click_box(self.w.props.bold)
        self.assertEqual(ed.text.textCursor().selectedText(), "added")
        self.finish()
        got = {w: b for w, b, _i, _s in word_styles(self.v.doc[0])}
        self.assertTrue(got["added"])
        self.assertFalse(got["Hello"])
        self.assertFalse(annotations.tool_props("addtext")["bold"])     # the default as it was


if __name__ == "__main__":
    unittest.main()
