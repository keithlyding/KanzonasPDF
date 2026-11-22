"""Properties with the page's own text selected in Edit objects (or CAD mode): Font, Font size,
Bold, Italic, Underline, Strikethrough and Text color. They show the text's style (Font size
blank and the color "several" when it differs), and a change is given to all of the selected
text, written again in the page where it is, each word keeping the rest of its style, as one
step Undo takes back; it stays selected. A size spreads a paragraph's lines apart as much as
it grows the text. Nothing becomes a markup.

The owner, 22 Nov 2026: "We need to do the same thing for text. Put it in the properties panel
on the right. All the things that can be done to edit text."

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_text_objects_properties
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
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

from tests.qt_fonts import ensure_font  # noqa: E402

ensure_font()

from kanzonas import main_window, mouse_modes, text_edit, text_styles  # noqa: E402


def pump(n=4):
    for _ in range(n):
        APP.processEvents()


def sheet():
    d = pymupdf.open()
    p = d.new_page()
    p.insert_text((72, 100), "Notes for the plan", fontsize=12)
    p.insert_text((72, 115), "read them first", fontsize=12)
    p.insert_text((72, 400), "Sheet title", fontsize=12, color=(0, 0, 1))
    path = os.path.join(tempfile.mkdtemp(), "plan.pdf")
    d.save(path)
    return path


def styles(page):
    """{line text: (bold, italic, underline, strike, size, color, baseline y)}."""
    out = {}
    for _r, ln in text_edit.text_lines(page):
        st = text_styles.read_line(page, ln)
        k = st.keys[re.search(r"\S", st.text).start()]
        out[text_edit.line_text(ln).strip()] = (k.bold, k.italic, k.underline, k.strike,
                                                round(k.size, 1), k.color & 0xFFFFFF,
                                                round(ln["spans"][0]["origin"][1], 1))
    return out


class TextObjects(unittest.TestCase):
    def setUp(self):
        w = self.w = main_window.MainWindow()
        old = {k: w.settings.value(k) for k in ("mouse_mode", "mouse_before_cad")}

        def back():
            for k, val in old.items():
                w.settings.setValue(k, val) if val is not None else w.settings.remove(k)
            mouse_modes.apply(w.settings)
        self.addCleanup(back)
        self.addCleanup(lambda: [setattr(x, "_close_confirmed", True) or x.close()
                                 for x in main_window.windows()])
        w.resize(1300, 900)
        w.show()
        w.open_file(sheet())
        pump()
        v = self.v = w.view()
        self.addCleanup(lambda: setattr(v, "dirty", False))
        w.set_tool("editobjects")
        pump()
        self.props = w.props

    def texts(self, word):
        return [it for it in self.v.text_objects(0)
                if any(word in text_edit.line_text(ln) for _r, ln in it["lines"])]

    def select(self, items):
        self.v.select_objects(0, items)
        pump()

    def click(self, box):
        QTest.mouseClick(box, Qt.LeftButton, Qt.NoModifier, QPoint(5, box.height() // 2))
        pump()

    def test_it_shows_the_text_s_style(self):
        self.select(self.texts("Notes"))
        self.assertIn("Page content", self.props.tag.text())
        for row in ("font", "fontsize", "text_color"):
            self.assertTrue(self.props.rows[row][1].isVisible(), row)
        self.assertTrue(self.props.underline.isVisible())
        self.assertAlmostEqual(self.props.fontsize.value(), 12)
        self.assertFalse(self.props.bold.isChecked())
        self.assertEqual(self.props.text_color.color(), "#000000")

    def test_bold_underline_strike_each_one_step_and_it_stays_selected(self):
        self.select(self.texts("Notes"))
        before = styles(self.v.doc[0])
        self.click(self.props.bold)
        self.click(self.props.underline)
        got = styles(self.v.doc[0])
        self.assertEqual(got["Notes for the plan"][:4], (True, False, True, False))
        self.assertEqual(got["read them first"][:4], (True, False, True, False))
        self.assertEqual(got["Sheet title"], before["Sheet title"])      # (not selected)
        self.assertTrue(self.v.obj_sel and self.v.obj_sel[1][0]["kind"] == "text")
        self.assertTrue(self.props.bold.isChecked())
        self.assertEqual(list(self.v.doc[0].annots()), [])               # (not markups)
        self.v.undo()
        pump()
        self.assertEqual(styles(self.v.doc[0])["Notes for the plan"][:4],
                         (True, False, False, False))
        self.v.undo()
        pump()
        self.assertEqual(styles(self.v.doc[0]), before)

    def test_a_size_spreads_the_lines_as_it_grows_the_text(self):
        self.select(self.texts("Notes"))
        self.props.fontsize.setValue(24)
        self.props.fontsize.editingFinished.emit()
        pump()
        got = styles(self.v.doc[0])
        self.assertEqual(got["Notes for the plan"][4], 24.0)
        self.assertEqual(got["Notes for the plan"][6], 100.0)            # (the first stays)
        self.assertEqual(got["read them first"][6], 130.0)               # (15 pt -> 30 pt)
        self.assertEqual(got["Sheet title"][4], 12.0)

    def test_several_colors_show_several_and_one_picked_goes_to_all(self):
        self.select(self.texts("Notes") + self.texts("Sheet"))
        self.assertEqual(self.props.text_color.text(), "several")
        self.props.text_color.set_color("#00aa00")
        self.props.text_color.changed.emit()
        pump()
        got = styles(self.v.doc[0])
        self.assertEqual({got[k][5] for k in got}, {0x00AA00})

    def test_several_sizes_show_blank(self):
        self.select(self.texts("Sheet"))
        self.props.fontsize.setValue(20)
        pump()
        self.select(self.texts("Notes") + self.texts("Sheet"))
        self.assertEqual(self.props.fontsize.text().strip(), "")


if __name__ == "__main__":
    unittest.main()
