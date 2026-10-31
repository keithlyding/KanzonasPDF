"""1.4.3, from an outside audit: CSV exports never hand a spreadsheet a live formula; the
shared undo-memory budget is kept when the biggest history can't give anything up; odd bytes
under KanzonasPDF's own clipboard format don't break Paste.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_audit_143
"""
import csv
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402
from PySide6.QtCore import QMimeData  # noqa: E402
from PySide6.QtWidgets import QApplication, QFileDialog  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import clip, document_view  # noqa: E402
from kanzonas.document_view import DocumentView  # noqa: E402
from kanzonas.export import csv_cell  # noqa: E402


def pdf(build=None):
    d = pymupdf.open()
    p = d.new_page()
    if build:
        build(p)
    path = os.path.join(tempfile.mkdtemp(), "t.pdf")
    d.save(path)
    return path


class CsvFormulas(unittest.TestCase):
    def test_formula_text_is_kept_as_text(self):
        for bad in ('=HYPERLINK("http://x","click")', "+1+cmd", "-2+3", "@SUM(A1:A9)",
                    "\t=1", "\r=1"):
            self.assertEqual(csv_cell(bad), "'" + bad)
        for fine in ("-5", "+12.5", "1,050.00", "-12%", "Length: 4'-0\"", "", 7, 3.5, None):
            self.assertEqual(csv_cell(fine), fine)

    def test_markups_list_export(self):
        def build(p):
            a = p.add_text_annot((100, 100), '=HYPERLINK("http://evil.example","Open")')
            a.set_info(title="@attacker")
            a.update()
        v = DocumentView(pdf(build))
        self.addCleanup(v.close_doc)
        from kanzonas.markups_panel import MarkupsPanel
        panel = MarkupsPanel()
        self.addCleanup(panel.deleteLater)
        panel.refresh(v.doc)
        out = os.path.join(tempfile.mkdtemp(), "m.csv")
        with mock.patch.object(QFileDialog, "getSaveFileName", lambda *a, **k: (out, "")):
            panel.export_csv()
        with open(out, encoding="utf-8-sig", newline="") as f:
            cells = [c for row in csv.reader(f) for c in row]
        self.assertIn("'=HYPERLINK(\"http://evil.example\",\"Open\")", cells)
        self.assertIn("'@attacker", cells)
        self.assertFalse(any(c[:1] in "=+@" for c in cells if c), cells)


class UndoBudget(unittest.TestCase):
    def test_other_documents_give_up_steps_when_the_biggest_cant(self):
        a, b = DocumentView(pdf()), DocumentView(pdf())
        self.addCleanup(a.close_doc)
        self.addCleanup(b.close_doc)
        with mock.patch.object(document_view, "UNDO_BYTES_TOTAL", 24), \
                mock.patch.object(document_view, "UNDO_BYTES_PER_DOC", 10 ** 9):
            a._undo, a._redo = [b"x" * 20], []          # one big step: always kept
            b._undo, b._redo = [b"y" * 4] * 4, []        # 16 bytes that can go
            b._trim_history()
            a._trim_history()
            self.assertEqual(len(a._undo), 1)
            self.assertLessEqual(a.history_bytes() + b.history_bytes(), 24)
            self.assertEqual(len(b._undo), 1)            # its newest step stays too


class OddClipboard(unittest.TestCase):
    def test_bytes_that_arent_text_are_not_ours(self):
        md = QMimeData()
        md.setData(clip.MIME, b"\xff\xfe\x00markups:\x80\x81")
        QApplication.clipboard().setMimeData(md)
        self.assertEqual(clip.get(), (None, None))
        v = DocumentView(pdf())
        self.addCleanup(v.close_doc)
        v.paste()                                        # no exception


class EditorCoversParagraph(unittest.TestCase):
    def test_the_old_lines_never_peek_out_below_the_editor(self):
        """The edit box covers the whole paragraph, also when the screen font fits its words
        on fewer lines than the page does (found making screenshots)."""
        text = ("1.01 SUMMARY. Section includes cast-in-place concrete, including formwork, "
                "reinforcement, concrete materials, mixture design, placement procedures, and "
                "finishes, for footings, slabs-on-grade, foundation walls and elevated slabs as "
                "shown on the drawings.")

        def build(p):
            p.insert_textbox(pymupdf.Rect(72, 122, 540, 260), text, fontsize=11,
                             fontname="tiro", align=pymupdf.TEXT_ALIGN_JUSTIFY)
        v = DocumentView(pdf(build))
        self.addCleanup(v.close_doc)
        v.resize(1200, 900)
        v.show()
        v.set_zoom(1.6)
        APP.processEvents()
        from kanzonas import text_edit
        v.edit_text_at(0, pymupdf.Point(200, 135))
        ed = v._inline
        self.assertIsNotNone(ed)
        box = pymupdf.Rect()
        for _r, ln in text_edit.text_lines(v.doc[0]):
            box |= pymupdf.Rect(ln["bbox"])
        w = v.pages[0]
        covered = w.to_screen(box)
        self.assertGreaterEqual(ed.y() + ed.height(), covered.bottom())
        ed.canceled.emit()


if __name__ == "__main__":
    unittest.main()
