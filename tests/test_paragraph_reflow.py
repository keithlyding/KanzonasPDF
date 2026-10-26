"""Edit text rewrites a whole paragraph: the words rewrap to its width in its font, size,
line spacing and alignment (left, right, centered, justified); Alt+click edits one line;
growing into text below is reported.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_paragraph_reflow
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

TEXT = ("The contractor shall verify all dimensions in the field before ordering materials "
        "and report any discrepancies to the architect in writing.")
LONGER = ("The general contractor shall carefully verify all of the dimensions in the field "
          "before ordering any materials and shall report every discrepancy found to the "
          "architect in writing within two working days.")


def rows(page):
    """[(x0, x1, baseline, size, text)] of the page's visible lines (a justified line's
    pieces joined), top to bottom."""
    out = []
    for _box, blk in text_edit.text_blocks(text_edit.text_lines(page)):
        for r, ln in blk:
            out.append((r.x0, r.x1, ln["spans"][0]["origin"][1],
                        round(max(s["size"] for s in ln["spans"]), 2), text_edit.line_text(ln)))
    return sorted(out, key=lambda t: t[2])


class Reflow(unittest.TestCase):
    def view(self, align=pymupdf.TEXT_ALIGN_LEFT, rotation=0, below=None, text=TEXT):
        d = pymupdf.open()
        p = d.new_page()
        p.set_rotation(rotation)
        p.insert_textbox(pymupdf.Rect(72, 72, 320, 300), text, fontsize=11, fontname="helv",
                         align=align)
        if below:
            p.insert_text(below, "Other note below", fontsize=11)
        path = os.path.join(tempfile.mkdtemp(), "p.pdf")
        d.save(path)
        v = DocumentView(path)
        self.addCleanup(v.close_doc)
        return v

    def edit(self, v, pt, new, one_line=False):
        v.edit_text_at(0, pymupdf.Point(pt), one_line=one_line)
        ed = v._inline
        self.assertIsNotNone(ed)
        shown = ed.text.toPlainText()
        ed.committed.emit(new, 0, 0, None)
        return shown

    def test_click_edits_the_whole_paragraph_and_rewraps_it(self):
        v = self.view()
        before = rows(v.doc[0])
        self.assertGreater(len(before), 1)
        shown = self.edit(v, (100, before[0][2] - 3), LONGER)
        self.assertEqual(shown, TEXT)                       # the whole paragraph, one text
        after = rows(v.doc[0])
        self.assertEqual(" ".join(r[4] for r in after), LONGER)
        self.assertGreater(len(after), len(before))          # it rewrapped onto more lines
        self.assertTrue(all(abs(r[0] - 72) < 1.5 for r in after))     # same left edge
        self.assertTrue(all(r[1] <= 320 + 1 for r in after))           # inside its width
        self.assertEqual({r[3] for r in after}, {11.0})                # same size
        step = before[1][2] - before[0][2]
        self.assertAlmostEqual(after[1][2] - after[0][2], step, delta=0.2)   # same spacing
        self.assertAlmostEqual(after[0][2], before[0][2], delta=0.2)
        v.undo()
        self.assertEqual([r[4] for r in rows(v.doc[0])], [r[4] for r in before])

    def test_justified_and_centered_stay_so(self):
        v = self.view(pymupdf.TEXT_ALIGN_JUSTIFY, text=TEXT + " " + TEXT)
        first = rows(v.doc[0])
        self.edit(v, (100, first[0][2] - 3), LONGER + " " + LONGER)
        after = rows(v.doc[0])
        right = max(r[1] for r in after)
        self.assertTrue(all(abs(r[1] - right) < 1.5 for r in after[:-1]))   # full lines
        self.assertLess(after[-1][1], right - 3)                            # last one short
        self.edit(v, (100, after[0][2] - 3), TEXT + " " + TEXT)      # and again
        again = rows(v.doc[0])
        self.assertEqual(" ".join(r[4] for r in again), TEXT + " " + TEXT)
        v = self.view(pymupdf.TEXT_ALIGN_CENTER)
        first = rows(v.doc[0])
        self.edit(v, (196, first[0][2] - 3), LONGER)
        mids = [(r[0] + r[1]) / 2 for r in rows(v.doc[0])]
        self.assertLess(max(mids) - min(mids), 1.5)

    def test_two_lines_justified_or_not(self):
        two = ("1. The contractor shall verify all dimensions in the field before ordering "
               "materials and report any discrepancies to the architect in writing.")
        longer = ("1. The general contractor shall verify all dimensions and existing conditions "
                  "in the field before ordering any materials, and shall report every "
                  "discrepancy to the architect in writing within two working days.")
        for align, justified in ((pymupdf.TEXT_ALIGN_JUSTIFY, True),
                                 (pymupdf.TEXT_ALIGN_LEFT, False)):
            d = pymupdf.open()
            d.new_page(width=420, height=300).insert_textbox(
                pymupdf.Rect(36, 56, 384, 120), two, fontsize=10.5, fontname="tiro",
                align=align)
            path = os.path.join(tempfile.mkdtemp(), "two.pdf")
            d.save(path)
            v = DocumentView(path)
            self.addCleanup(v.close_doc)
            first = rows(v.doc[0])
            self.assertEqual(len(first), 2)
            self.edit(v, (100, first[0][2] - 3), longer)
            after = rows(v.doc[0])
            full = [abs(r[1] - 384) < 1 for r in after[:-1]]
            self.assertEqual(all(full), justified, after)

    def test_a_column_of_labels_is_edited_a_line_at_a_time(self):
        d = pymupdf.open()
        p = d.new_page()
        for i, label in enumerate(("LIVING ROOM 214", "BATH", "KITCHEN", "BEDROOM 2")):
            p.insert_text((72, 100 + i * 13), label, fontsize=10)
        path = os.path.join(tempfile.mkdtemp(), "labels.pdf")
        d.save(path)
        v = DocumentView(path)
        self.addCleanup(v.close_doc)
        v.edit_text_at(0, pymupdf.Point(80, 110))
        self.assertEqual(v._inline.text.toPlainText(), "BATH")
        v._inline.canceled.emit()

    def test_alt_click_edits_one_line(self):
        v = self.view()
        before = rows(v.doc[0])
        self.edit(v, (100, before[0][2] - 3), "Just the first line", one_line=True)
        after = rows(v.doc[0])
        self.assertEqual(after[0][4], "Just the first line")
        self.assertEqual([r[4] for r in after[1:]], [r[4] for r in before[1:]])

    def test_hyphenated_words_join(self):
        d = pymupdf.open()
        p = d.new_page()
        p.insert_text((72, 100), "A long specifi-", fontsize=11)
        p.insert_text((72, 113), "cation follows here", fontsize=11)
        lines = [ln for _r, ln in text_edit.text_lines(p)]
        self.assertEqual(text_edit.paragraph_text(lines), "A long specification follows here")

    def test_growing_into_text_below_is_reported(self):
        v = self.view(below=(72, 140))
        said = []
        v.statusMessage.connect(said.append)
        first = rows(v.doc[0])
        self.edit(v, (100, first[0][2] - 3), LONGER + " " + LONGER)
        self.assertTrue(any("overlaps text below" in m for m in said), said)
        # room below: no warning
        v = self.view()
        said = []
        v.statusMessage.connect(said.append)
        first = rows(v.doc[0])
        self.edit(v, (100, first[0][2] - 3), LONGER)
        self.assertTrue(any("Paragraph rewritten" in m for m in said), said)

    def test_rotated_page_edits_a_line(self):
        v = self.view(rotation=90)
        r, ln = text_edit.text_lines(v.doc[0])[0]
        c = pymupdf.Point((r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2)
        v.edit_text_at(0, c)
        self.assertEqual(v._inline.text.toPlainText(), text_edit.line_text(ln))
        v._inline.canceled.emit()


if __name__ == "__main__":
    unittest.main()
