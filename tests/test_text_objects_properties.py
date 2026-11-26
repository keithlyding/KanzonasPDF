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

    def test_a_size_wraps_a_paragraph_again_to_its_own_width(self):
        # (written again line by line, a long first line ran off the page: random battery,
        # seed 13; now it wraps as Edit text does)
        self.select(self.texts("Notes"))
        right = max(r.x1 for r, _ln in self.texts("Notes")[0]["lines"])
        self.props.fontsize.setValue(24)
        self.props.fontsize.editingFinished.emit()
        pump()
        got = styles(self.v.doc[0])
        words = [w for k in got if k != "Sheet title" for w in k.split()]
        self.assertEqual(words, "Notes for the plan read them first".split())
        self.assertEqual({got[k][4] for k in got if k != "Sheet title"}, {24.0})
        self.assertEqual(got["Notes"][6], 100.0)                       # (the first stays)
        for r, ln in text_edit.text_lines(self.v.doc[0]):
            if "Sheet" not in text_edit.line_text(ln):
                self.assertLess(r.x1, right + 30)                      # (within its width)
        self.assertEqual(got["Sheet title"][4], 12.0)
        sel = self.v.obj_sel[1]                                         # (still selected)
        self.assertEqual(len(sel), 1)
        self.assertEqual(len(sel[0]["lines"]), len(got) - 1)

    def test_a_size_on_labels_writes_them_where_they_are(self):
        self.select(self.texts("Sheet"))
        self.props.fontsize.setValue(20)
        pump()
        got = styles(self.v.doc[0])
        self.assertEqual(got["Sheet title"][4:], (20.0, 0x0000FF, 400.0))
        self.assertEqual(len(self.v.obj_sel[1]), 1)

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


class OffThePage(unittest.TestCase):
    def test_text_wholly_past_the_edge_inside_a_restyled_line_stays(self):
        # (a legend drawn partly past the page's left edge, its "Abc" samples wholly past
        # it, inside its lines' boxes: restyling the lines took the samples away. Nightly
        # battery, issue #135, seed 2026112603)
        from kanzonas.document_view import DocumentView
        d = pymupdf.open()
        p = d.new_page(width=300, height=300)
        p.insert_text((-40, 120), "Squiggly sample", fontsize=11)
        p.insert_text((-36, 119), "Abc", fontsize=7)
        path = os.path.join(tempfile.mkdtemp(), "edge.pdf")
        d.save(path)
        v = DocumentView(path)
        self.addCleanup(v.close_doc)
        self.addCleanup(setattr, v, "dirty", False)
        texts = [t for _r, ln in text_edit.text_lines(v.doc[0], outside=True)
                 for t in [text_edit.line_text(ln)]]
        self.assertIn("Abc", texts)
        self.assertNotIn("Abc", [text_edit.line_text(ln)
                                 for _r, ln in text_edit.text_lines(v.doc[0])])
        line = [it for it in v.text_objects(0)
                if any(text_edit.line_text(ln) == "Squiggly sample" for _r, ln in it["lines"])]
        self.assertEqual(len(line), 1)
        v.select_objects(0, line)
        v.style_text_objects({"underline": True, "fontsize": 14.5})
        texts = [text_edit.line_text(ln)
                 for _r, ln in text_edit.text_lines(v.doc[0], outside=True)]
        self.assertIn("Abc", texts)
        self.assertIn("Squiggly sample", texts)


class OnACopyOfItself(unittest.TestCase):
    def test_restyled_text_lying_on_a_copy_stays_selected_and_reads_back(self):
        # (two legends drawn at one place, one longer: restyled, the longer one was selected
        # again with the other's title, and its own title, starting where the copy's does,
        # read with no letters (MuPDF leaves out a letter drawn on the same letter): it read
        # back not underlined. Nightly battery, issue #135, seed 2026112603)
        from kanzonas.document_view import DocumentView
        d = pymupdf.open()
        p = d.new_page()
        words = ["Legend", "APPROVED", "Attached file", "Dimension"]
        for n in (2, 4):
            for k, w in enumerate(words[:n]):
                p.insert_text((72, 100 + 14 * k), w, fontsize=10.8 if k == 0 else 9,
                              fontname="hebo" if k == 0 else "helv")
        path = os.path.join(tempfile.mkdtemp(), "copies.pdf")
        d.save(path)
        v = DocumentView(path)
        self.addCleanup(v.close_doc)
        self.addCleanup(setattr, v, "dirty", False)
        longer = [it for it in v.text_objects(0) if len(it["lines"]) == 4]
        self.assertEqual(len(longer), 1)
        v.select_objects(0, longer)
        v.style_text_objects({"underline": True, "fontsize": 14.5})
        lines = [ln for _r, ln in v.obj_sel[1][0]["lines"]]
        self.assertEqual("".join(text_edit.line_text(ln) for ln in lines).replace(" ", ""),
                         "".join(words).replace(" ", ""))      # (its own lines, not the copy's)
        self.assertEqual({round(text_edit.main_span(ln)["size"], 1) for ln in lines}, {14.5})
        got = v.object_text_style()
        self.assertEqual((got["underline"], got["fontsize"]), (True, 14.5))


class OnABigSheet(unittest.TestCase):
    def test_400_labels_made_bold_quickly(self):
        # (each line read on its own walked the whole drawing: 8.7 s here, 1.0 s read once)
        import time
        d = pymupdf.open()
        p = d.new_page(width=3000, height=2000)
        sh = p.new_shape()
        for i in range(20000):
            x, y = (i * 37) % 2990, (i * 91) % 1990
            sh.draw_line((x, y), (x + 10, y + 5))
            sh.finish(width=1, color=(0, 0, 0))
        sh.commit()
        for i in range(400):
            p.insert_text((50 + (i % 20) * 140, 60 + (i // 20) * 90), "LABEL %d" % i,
                          fontsize=10)
        paras = [[ln] for _r, ln in text_edit.text_lines(p)]
        t = time.perf_counter()
        text_edit.restyle_lines(p, paras, lambda k: k._replace(underline=True))
        took = time.perf_counter() - t
        self.assertLess(took, 4.0)          # (the editing budget's 400 labels moved: 4 s)
        got = text_styles.read_lines(p, [ln for _r, ln in text_edit.text_lines(p)])
        self.assertEqual(len(got), 400)
        self.assertTrue(all(st.keys[0].underline for st in got))


if __name__ == "__main__":
    unittest.main()
