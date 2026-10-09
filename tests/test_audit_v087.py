"""Regressions from the v0.86 UX / performance audit: Markups list fill time, hover
hit-testing caches, read-only split view, Open recent with INI settings, 0-page PDFs,
cached Next comment order.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_audit_v087
"""
import os
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf as F  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import annotations as A  # noqa: E402
from kanzonas.document_view import DocumentView  # noqa: E402


class AuditV087(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(mock.patch.stopall)
        for n in ("information", "warning", "critical"):
            mock.patch.object(QMessageBox, n, return_value=None).start()

    def pdf(self, name, annots=0, fields=0, pages=1):
        d = F.open()
        for _ in range(pages):
            pg = d.new_page()
            for i in range(annots):
                x, y = 20 + (i % 50) * 11, 20 + (i // 50) * 11
                pg.add_rect_annot(F.Rect(x, y, x + 8, y + 8)).set_info(content="note %d" % i)
            for i in range(fields):
                w = F.Widget()
                w.field_type = F.PDF_WIDGET_TYPE_TEXT
                w.field_name = "f%d" % i
                x, y = 20 + (i % 10) * 55, 20 + (i // 10) * 12
                w.rect = F.Rect(x, y, x + 50, y + 10)
                pg.add_widget(w)
        p = os.path.join(self.tmp.name, name)
        d.save(p)
        return p

    def test_markups_list_fills_quickly(self):
        os.environ["HOME"] = self.tmp.name
        from kanzonas.main_window import MainWindow
        w = MainWindow()
        w.show()
        w.open_file(self.pdf("many.pdf", annots=5, pages=400))
        APP.processEvents()
        t = time.perf_counter()
        w.a_markups.trigger()                   # F7: the list fills as it opens
        for _ in range(5):
            APP.processEvents()
        took = time.perf_counter() - t
        self.assertEqual(w.markups.table.rowCount(), 2000)
        self.assertLess(took, 20, "2,000 markups took %.1fs to list" % took)   # was ~3 min
        w.close_tab(w.tabs.currentIndex())
        w.deleteLater()

    def test_hover_hit_tests_are_cached_and_follow_edits(self):
        v = DocumentView(self.pdf("hit.pdf", annots=50, fields=20))
        xref = v.annot_at(0, F.Point(24, 24))
        self.assertIsNotNone(xref)
        self.assertIsNotNone(v.widget_at(0, F.Point(470, 37)))       # field 18
        self.assertIsNone(v.widget_at(0, F.Point(5, 5)))
        with mock.patch.object(A, "each_annot", side_effect=AssertionError("rescanned")):
            v.annot_at(0, F.Point(24, 24))            # served from the cache
        v.modify(lambda: v.doc[0].delete_annot(v.doc[0].load_annot(xref)), [0])
        self.assertNotEqual(v.annot_at(0, F.Point(24, 24)), xref)
        v.close_doc()

    def test_split_view_cannot_change_the_document(self):
        v = DocumentView(self.pdf("one.pdf", annots=1))
        m = DocumentView.mirror(v)
        xref = v.doc[0].first_annot.xref
        m.modify(lambda: m.doc[0].delete_annot(m.doc[0].load_annot(xref)), [0])
        self.assertEqual(len(list(v.doc[0].annots())), 1)
        self.assertFalse(m.can_undo())
        v.close_doc()

    def test_zero_page_pdf_is_refused(self):
        p = os.path.join(self.tmp.name, "zero.pdf")
        with open(p, "wb") as f:
            f.write(b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
                    b"2 0 obj<</Type/Pages/Kids[]/Count 0>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF")
        with self.assertRaises(Exception):
            DocumentView(p)

    def test_next_comment_order_is_cached_until_an_edit(self):
        v = DocumentView(self.pdf("rev.pdf", annots=5, pages=3))
        first = v.review_items()
        self.assertEqual(len(first), 15)
        with mock.patch.object(A, "each_annot", side_effect=AssertionError("rescanned")):
            self.assertEqual(v.review_items(), first)
        v.modify(lambda: v.doc[1].add_rect_annot(F.Rect(300, 300, 320, 320)), [1])
        self.assertEqual(len(v.review_items()), 16)
        v.close_doc()

    def test_open_recent_survives_a_single_entry_in_ini_settings(self):
        from PySide6.QtCore import QSettings
        os.environ["HOME"] = self.tmp.name
        from kanzonas.main_window import MainWindow
        w = MainWindow()
        ini = QSettings(os.path.join(self.tmp.name, "s.ini"), QSettings.IniFormat)
        ini.setValue("recent", "/one/file.pdf")             # INI hands one entry back as a str
        w.settings = ini
        w._add_recent("/two/other.pdf")
        self.assertEqual(list(w.settings.value("recent")), ["/two/other.pdf", "/one/file.pdf"])
        w.deleteLater()


if __name__ == "__main__":
    unittest.main()
