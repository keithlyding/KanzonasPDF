"""What a review of 1.4.1 found: a markup on the PDF's own link stays selectable with the
Hand tool; numbered and hanging-indent paragraphs edit whole; a two-line justified
paragraph of separately placed words is one paragraph; a page's paragraph rows are kept
between clicks; Compress and Digital signature don't warn about losing changes they keep.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_review_141
"""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402
from PySide6.QtCore import QEvent, Qt  # noqa: E402
from PySide6.QtGui import QMouseEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import text_edit  # noqa: E402
from kanzonas.document_view import DocumentView  # noqa: E402


def saved(d, name="d.pdf"):
    path = os.path.join(tempfile.mkdtemp(), name)
    d.save(path)
    return path


def heads(lines):
    return None if lines is None else [text_edit.line_text(ln)[:12] for ln in lines]


class HandOnHighlightedLink(unittest.TestCase):
    def test_hand_selects_a_highlight_on_the_pdfs_own_link(self):
        d = pymupdf.open()
        d.new_page()
        d.new_page()
        p = d[0]
        p.insert_text((72, 100), "Chapter 2 ............ 7", fontsize=12)
        p.insert_link({"kind": pymupdf.LINK_GOTO, "page": 1,
                       "from": pymupdf.Rect(70, 88, 220, 104)})
        p.add_highlight_annot(pymupdf.Rect(72, 89, 130, 103))
        v = DocumentView(saved(d, "toc.pdf"))
        self.addCleanup(v.close_doc)
        v.resize(900, 1200)
        v.show()
        APP.processEvents()
        followed = []
        v.follow_link = followed.append
        self.assertIsNone(v.link_to_follow(0, pymupdf.Point(100, 96)))
        self.assertIsNotNone(v.link_to_follow(0, pymupdf.Point(200, 96)))   # off the markup
        w = v.pages[0]
        pos = w.to_screen_pt(pymupdf.Point(100, 96))
        v.set_tool("hand")
        for t in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease):
            ev = QMouseEvent(t, pos, w.mapToGlobal(pos), Qt.LeftButton,
                             Qt.LeftButton if t == QEvent.MouseButtonPress else Qt.NoButton,
                             Qt.NoModifier)
            (w.mousePressEvent if t == QEvent.MouseButtonPress else w.mouseReleaseEvent)(ev)
        APP.processEvents()
        self.assertEqual(followed, [])
        self.assertIsNotNone(v.selection)


class HangingIndents(unittest.TestCase):
    def test_numbered_paragraph_with_a_hanging_indent(self):
        d = pymupdf.open()
        p = d.new_page()
        lines = ["1. The contractor shall verify all dimensions in the field before",
                 "ordering materials and report any discrepancies to the architect",
                 "in writing within two working days of finding them on the site and",
                 "shall not proceed with the affected work until they are resolved."]
        for i, t in enumerate(lines):
            p.insert_text((72 if i == 0 else 84, 100 + 13.5 * i), t, fontsize=11)
        tl = text_edit.text_lines(p)
        for y in (97, 111, 124, 138):
            hit = text_edit.line_at(tl, pymupdf.Point(200, y))
            self.assertEqual(len(text_edit.paragraph_at(tl, hit[1]) or []), 4, y)

    def test_justified_paragraph_with_its_first_line_set_out(self):
        font = pymupdf.Font("helv")
        words = ("The contractor shall verify all dimensions in the field before ordering "
                 "materials and report any discrepancies to the architect in writing within "
                 "two working days of finding them on the site, and shall not proceed with "
                 "affected work until resolved.").split()
        rows, cur = [], []
        for w in words:
            room = 360 - (72 if not rows else 90)
            if cur and font.text_length(" ".join(cur + [w]), 11) > room:
                rows.append(cur)
                cur = [w]
            else:
                cur.append(w)
        rows.append(cur)
        d = pymupdf.open()
        p = d.new_page()
        for i, ws in enumerate(rows):
            x0 = 72 if i == 0 else 90
            gap = ((360 - x0 - sum(font.text_length(w, 11) for w in ws)) / (len(ws) - 1)
                   if i < len(rows) - 1 else font.text_length(" ", 11))
            x = x0
            for w in ws:
                p.insert_text((x, 100 + 13.5 * i), w, fontsize=11)
                x += font.text_length(w, 11) + gap
        tl = text_edit.text_lines(p)
        for i in range(len(rows)):
            ln = min((ln for _r, ln in tl if abs(text_edit._baseline(ln) - 100 - 13.5 * i) < 1),
                     key=lambda ln: ln["bbox"][0])
            self.assertEqual(len(text_edit.paragraph_at(tl, ln) or []), len(rows), i)


class TwoLineJustified(unittest.TestCase):
    def test_words_placed_apart_still_make_a_paragraph(self):
        d = pymupdf.open()
        p = d.new_page()
        font = pymupdf.Font("helv")
        x = 72
        for w in "Contractors shall verify every dimension shown on drawings".split():
            p.insert_text((x, 100), w, fontsize=11)
            x += font.text_length(w, 11) + 12
        x = 72
        for w in "in the field.".split():
            p.insert_text((x, 113.5), w, fontsize=11)
            x += font.text_length(w + " ", 11)
        tl = text_edit.text_lines(p)
        self.assertEqual([len(blk) for _b, blk in text_edit.text_blocks(tl)], [2])
        self.assertEqual(len(text_edit.paragraph_at(tl, tl[0][1]) or []), 2)

    def test_table_columns_stay_apart(self):
        d = pymupdf.open()
        p = d.new_page()
        for i in range(3):
            for x, t in ((72, "W-%d" % i), (110, "Vinyl window"), (200, "See detail %d" % i)):
                p.insert_text((x, 100 + 12 * i), t, fontsize=10)
        tl = text_edit.text_lines(p)
        rows = text_edit._join_spread_pieces([(r, ln) for r, ln in tl])
        self.assertEqual(len(rows), 9)


class KeptRows(unittest.TestCase):
    def test_a_pages_rows_are_kept_until_it_changes(self):
        d = pymupdf.open()
        p = d.new_page()
        p.insert_textbox(pymupdf.Rect(72, 72, 320, 300), "The contractor shall verify all "
                         "dimensions in the field before ordering materials and report any "
                         "discrepancies to the architect in writing.", fontsize=11)
        v = DocumentView(saved(d))
        self.addCleanup(v.close_doc)
        line = v._lines(0)[0][1]
        with mock.patch.object(text_edit, "paragraph_rows",
                               wraps=text_edit.paragraph_rows) as made:
            v._paragraph_of(0, line)
            v._paragraph_of(0, line)
            self.assertEqual(made.call_count, 1)
            v._clear_page_caches([0])
            v._paragraph_of(0, v._lines(0)[0][1])
            self.assertEqual(made.call_count, 2)


class WritingItsOwnChanges(unittest.TestCase):
    def test_no_lose_your_changes_question_for_the_document_written(self):
        from kanzonas.main_window import MainWindow
        d = pymupdf.open()
        d.new_page().insert_text((72, 72), "x")
        path = saved(d)
        w = MainWindow()
        self.addCleanup(lambda: (setattr(w, "_close_confirmed", True), w.close()))
        w.open_file(path)
        v = w.view()
        v.dirty = True
        with mock.patch.object(QMessageBox, "warning", return_value=QMessageBox.No) as asked:
            self.assertIsNotNone(w._writing_over(path, source=v))
            self.assertFalse(asked.called)
            self.assertIsNone(w._writing_over(path))           # another writer: asks
            self.assertTrue(asked.called)
        v.dirty = False


if __name__ == "__main__":
    unittest.main()
