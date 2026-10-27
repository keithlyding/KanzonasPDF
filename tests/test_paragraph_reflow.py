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


def doc_path(build, name="d.pdf", width=612, height=792):
    d = pymupdf.open()
    p = d.new_page(width=width, height=height)
    build(p)
    path = os.path.join(tempfile.mkdtemp(), name)
    d.save(path)
    return path


class RealDocuments(unittest.TestCase):
    """What a click must not take for a paragraph, and what a rewrite must keep (found
    testing Word, LibreOffice and drawing-sheet PDFs)."""

    def open(self, build, **kw):
        v = DocumentView(doc_path(build, **kw))
        self.addCleanup(v.close_doc)
        self.said = []
        v.statusMessage.connect(self.said.append)
        return v

    def shown_at(self, v, pt, one_line=False):
        v.edit_text_at(0, pymupdf.Point(pt), one_line=one_line)
        return v._inline.text.toPlainText()

    def test_side_by_side_columns_are_edited_apart(self):
        left = TEXT + " " + TEXT
        right = LONGER + " " + LONGER

        def build(p):
            p.insert_textbox(pymupdf.Rect(72, 72, 300, 400), left, fontsize=11,
                             align=pymupdf.TEXT_ALIGN_JUSTIFY)
            p.insert_textbox(pymupdf.Rect(312, 72, 540, 400), right, fontsize=11,
                             align=pymupdf.TEXT_ALIGN_JUSTIFY)
        v = self.open(build)
        before = rows(v.doc[0])
        shown = self.shown_at(v, (100, before[0][2] - 3))
        self.assertEqual(shown, left)
        v._inline.committed.emit(shown.replace("contractor", "builder", 1), 0, 0, None)
        after = rows(v.doc[0])
        self.assertEqual([r[4] for r in after if r[0] > 306], [r[4] for r in before if r[0] > 306])
        self.assertTrue(all(r[1] <= 301 for r in after if r[0] < 306))

    def test_schedule_cells_title_blocks_and_labels_edit_a_line(self):
        def build(p):
            for x, t in ((75, "101"), (115, "3'-0\" x 7'-0\""), (185, "SOLID CORE WD,"),
                         (275, "PROVIDE CLOSER AND")):
                p.insert_text((x, 140), t, fontsize=7.5)
            for x, t in ((185, "PAINT GRADE"), (275, "KICKPLATE, VERIFY")):
                p.insert_text((x, 149.6), t, fontsize=7.5)
            p.insert_text((275, 159.2), "HARDWARE SET", fontsize=7.5)
            for i, t in enumerate(("FLOOR PLAN - LEVEL 1", "PROJECT NO. 2026-114",
                                   "DRAWN BY: KL   CHECKED: JS")):
                p.insert_text((400, 600 + 12 * i), t, fontsize=8)
            for i, t in enumerate(("LIVING ROOM", "101", "KITCHEN", "102")):
                p.insert_text((200, 400 + 10 * i), t, fontsize=8)
            p.insert_text((330, 300), "25'-0\"", fontsize=8)
            p.insert_text((330, 312), "VERIFY", fontsize=8)
        v = self.open(build)
        for pt, line in (((190, 138), "SOLID CORE WD,"), ((280, 147), "KICKPLATE, VERIFY"),
                         ((410, 598), "FLOOR PLAN - LEVEL 1"),
                         ((410, 610), "PROJECT NO. 2026-114"), ((203, 408), "101"),
                         ((335, 310), "VERIFY")):
            self.assertEqual(self.shown_at(v, pt), line)
            v._inline.canceled.emit()

    def test_bullets_and_numbered_notes_stay_items(self):
        def build(p):
            y = 100
            for n, t in ((1, "ALL DIMENSIONS ARE TO FACE OF STUD UNLESS NOTED OTHERWISE ON THE"),
                         (2, "DO NOT SCALE DRAWINGS. VERIFY ALL CONDITIONS IN THE FIELD BEFORE")):
                p.insert_text((72, y), "%d." % n, fontsize=9)
                p.insert_text((86, y), t, fontsize=9)
                p.insert_text((86, y + 11), "DRAWINGS AND REPORT ANY DISCREPANCIES TO THE ARCHITECT.",
                              fontsize=9)
                y += 22
            for t in ("Air barrier membrane shall be continuous at all transitions here.",
                      "Sealant joints shall be tooled smooth and free of voids or pockets."):
                p.insert_text((72, y), "\u2022", fontsize=11)
                p.insert_text((86, y), t, fontsize=11)
                y += 14
        v = self.open(build)
        self.assertEqual(self.shown_at(v, (120, 119)),
                         "DO NOT SCALE DRAWINGS. VERIFY ALL CONDITIONS IN THE FIELD BEFORE "
                         "DRAWINGS AND REPORT ANY DISCREPANCIES TO THE ARCHITECT.")
        v._inline.committed.emit("DO NOT SCALE THE DRAWINGS. CHECK ALL CONDITIONS IN THE "
                                 "FIELD BEFORE DRAWINGS AND REPORT ANY ERRORS TO THE "
                                 "ARCHITECT.", 0, 0, None)
        words = [w for w in v.doc[0].get_text("words") if 115 < w[3] < 140]
        first = sorted((w for w in words if w[3] < 125), key=lambda w: w[0])
        self.assertEqual((round(first[0][0]), first[0][4]), (72, "2."), first)  # it stays
        self.assertEqual((round(first[1][0]), first[1][4]), (86, "DO"), first)
        self.assertEqual(min(round(w[0]) for w in words if w[3] > 125), 86)
        self.assertEqual(self.shown_at(v, (120, 141)),
                         "Air barrier membrane shall be continuous at all transitions here.")
        v._inline.canceled.emit()

    def test_hyphenated_compounds_keep_their_hyphen(self):
        d = pymupdf.open()
        p = d.new_page()
        p.insert_text((72, 100), "Provide concrete with self-", fontsize=11)
        p.insert_text((72, 113), "consolidating mixes and a well-", fontsize=11)
        p.insert_text((72, 126), "graded base under the slab.", fontsize=11)
        lines = [ln for _r, ln in text_edit.text_lines(p)]
        self.assertEqual(text_edit.paragraph_text(lines), "Provide concrete with "
                         "self-consolidating mixes and a well-graded base under the slab.")

    def test_first_line_indent_is_kept(self):
        words = ("It was a bright cold day in April and the clocks were striking thirteen "
                 "while Winston Smith slipped quickly through the glass doors of Victory "
                 "Mansions though not quickly enough to prevent a swirl of gritty dust").split()

        def build(p):
            y, line, x = 100, [], 108
            for w in words:
                trial = " ".join(line + [w])
                if pymupdf.get_text_length(trial, fontsize=11) > 504 - x and line:
                    p.insert_text((x, y), " ".join(line), fontsize=11)
                    y, line, x = y + 14, [], 72
                line.append(w)
            p.insert_text((x, y), " ".join(line), fontsize=11)
        v = self.open(build)
        first = rows(v.doc[0])
        shown = self.shown_at(v, (300, first[1][2] - 3))
        self.assertEqual(shown, " ".join(words))
        v._inline.committed.emit(shown.replace("April", "May"), 0, 0, None)
        after = rows(v.doc[0])
        self.assertAlmostEqual(after[0][0], 108, delta=1)
        self.assertTrue(all(abs(r[0] - 72) < 1 for r in after[1:]))

    def test_ragged_lines_that_end_together_stay_ragged(self):
        def build(p):
            for i, t in enumerate(("The work will begin on Monday and must be done",
                                   "within thirty days, or damages of $500 per day",
                                   "will apply after that date.")):
                p.insert_text((72, 100 + 14 * i), t, fontsize=11, fontname="cour")
        v = self.open(build)
        first = rows(v.doc[0])
        self.assertAlmostEqual(first[0][1], first[1][1], delta=0.1)       # by chance
        shown = self.shown_at(v, (100, first[0][2] - 3))
        v._inline.committed.emit(shown.replace("thirty", "forty-five"), 0, 0, None)
        gaps = set()
        words = sorted(v.doc[0].get_text("words"), key=lambda w: (round(w[3]), w[0]))
        for a, b in zip(words, words[1:]):
            if round(a[3]) == round(b[3]):
                gaps.add(round(b[0] - a[2], 1))
        self.assertEqual(gaps, {round(pymupdf.get_text_length(" ", "cour", 11), 1)})

    def test_click_puts_the_cursor_on_the_word_clicked(self):
        v = self.open(lambda p: p.insert_textbox(pymupdf.Rect(72, 72, 320, 300), TEXT,
                                                 fontsize=11))
        v.show()
        w = [w for w in v.doc[0].get_text("words") if w[4] == "discrepancies"][0]
        v.edit_text_at(0, pymupdf.Point((w[0] + w[2]) / 2, (w[1] + w[3]) / 2))
        pos = v._inline.text.textCursor().position()
        i = TEXT.index("discrepancies")
        self.assertTrue(i <= pos <= i + len("discrepancies"), (pos, i))
        v._inline.canceled.emit()

    def test_shift_enter_splits_and_a_failed_edit_says_so(self):
        v = self.open(lambda p: p.insert_textbox(pymupdf.Rect(72, 72, 320, 300), TEXT,
                                                 fontsize=11))
        first = rows(v.doc[0])
        shown = self.shown_at(v, (100, first[0][2] - 3))
        v._inline.committed.emit(shown.replace(" and report", "\nand report"), 0, 0, None)
        self.assertTrue(v.can_undo() if hasattr(v, "can_undo") else v._undo)
        self.assertTrue(any(r[4].startswith("and report") for r in rows(v.doc[0])))
        from unittest import mock
        v = self.open(lambda p: p.insert_textbox(pymupdf.Rect(72, 72, 320, 300), TEXT,
                                                 fontsize=11))
        with mock.patch("kanzonas.document_view.QMessageBox.warning"), \
                mock.patch.object(text_edit, "replace_paragraph",
                                  side_effect=ValueError("No font can write it")):
            shown = self.shown_at(v, (100, first[0][2] - 3))
            v._inline.committed.emit(shown + " more", 0, 0, None)
        self.assertIn("wasn't changed", self.said[-1])

    def test_growing_onto_the_next_paragraph_or_off_the_page_is_reported(self):
        def build(p):
            p.insert_textbox(pymupdf.Rect(72, 72, 320, 300), TEXT, fontsize=11)
            r = p.insert_textbox(pymupdf.Rect(72, 72, 320, 300), TEXT, fontsize=11,
                                 render_mode=3)          # (measure only)
        d = pymupdf.open()
        p = d.new_page()
        y = 100
        for t in ("The contractor shall verify all dimensions in the field before ordering",
                  "materials and report any discrepancies to the architect in writing.",
                  "",
                  "All work shall comply with the applicable codes and the requirements of",
                  "the authorities having jurisdiction over the project site and its work."):
            if t:
                p.insert_text((72, y), t, fontsize=10)
            y += 12
        path = os.path.join(tempfile.mkdtemp(), "even.pdf")
        d.save(path)
        v = DocumentView(path)
        self.addCleanup(v.close_doc)
        said = []
        v.statusMessage.connect(said.append)
        shown = self.shown_at(v, (100, 97))
        v._inline.committed.emit(shown + " " + LONGER, 0, 0, None)
        self.assertIn("overlaps text below", said[-1])
        v.undo()
        v.edit_text_at(0, pymupdf.Point(100, 97))
        v._inline.committed.emit(" ".join([LONGER] * 12), 0, 0, None)
        self.assertTrue(any("bottom of the page" in m or "overlaps" in m for m in said[-1:]))


if __name__ == "__main__":
    unittest.main()
