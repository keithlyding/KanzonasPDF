"""Efficiency regressions from the v0.81 efficiency audit (P01, P02, P07, P08).

    QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests -p "test_*.py"
"""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf as F  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import annotations as A, autosave, ocr  # noqa: E402
import kanzonas.document_view as DV  # noqa: E402
from kanzonas.document_view import DocumentView  # noqa: E402


class PerformanceBudgets(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        patch = mock.patch.object(QMessageBox, "information", return_value=None)
        patch.start()
        self.addCleanup(patch.stop)

    def pdf(self, name, pages=3, size=(612, 792), filler=0):
        d = F.open()
        for i in range(pages):
            pg = d.new_page(width=size[0], height=size[1])
            pg.insert_text((72, 72), "page %d" % i)
            if filler:                      # uncompressed bulk, so each copy is large
                pg.insert_text((72, 100), "x" * 10)
                d.embfile_add("blob%d" % i, os.urandom(filler))
        p = os.path.join(self.tmp.name, name)
        d.save(p)
        return p

    def rect(self, v, k=0):
        v._create(0, {"kind": "rect", "props": dict(A.DEFAULTS["rect"]),
                      "rect": F.Rect(10 + k, 10, 50 + k, 50)})

    def test_undo_history_has_a_memory_budget(self):
        v = DocumentView(self.pdf("big.pdf", filler=4 * 2**20))      # ~12 MB per copy
        with mock.patch.object(DV, "UNDO_BYTES_PER_DOC", 40 * 2**20):
            for k in range(10):
                self.rect(v, k)
            self.assertLessEqual(v.history_bytes(), 40 * 2**20)
            self.assertGreaterEqual(len(v._undo), 1)                  # the last step is kept
            v.undo()
            self.assertLessEqual(v.history_bytes(), 40 * 2**20)

    def test_undo_budget_shared_by_open_documents(self):
        a = DocumentView(self.pdf("a.pdf", filler=4 * 2**20))
        b = DocumentView(self.pdf("b.pdf", filler=4 * 2**20))
        with mock.patch.object(DV, "UNDO_BYTES_TOTAL", 60 * 2**20):
            for k in range(4):
                self.rect(a, k)
                self.rect(b, k)
            self.assertLessEqual(a.history_bytes() + b.history_bytes(), 60 * 2**20)
            self.assertTrue(a._undo and b._undo)

    def test_ocr_batch_releases_page_images(self):
        r = ocr.Rendering(F.open(self.pdf("o.pdf", pages=1))[0], dpi=72)
        self.assertIsNotNone(r.image)
        r.release()
        self.assertIsNone(r.image)
        self.assertIsNotNone(r.to_display(10, 10))         # placing text still works

    def test_autosave_skips_unchanged_documents(self):
        v = DocumentView(self.pdf("s.pdf"))
        self.rect(v)
        saver = autosave.Autosaver.__new__(autosave.Autosaver)
        saver.views = lambda: [v]
        writes = []
        with mock.patch.object(autosave, "folder", return_value=self.tmp.name), \
                mock.patch.object(saver, "backup", wraps=saver.backup) as backup:
            saver.tick()
            saver.tick()
            saver.tick()
            writes.append(backup.call_count)
            self.rect(v, 5)
            saver.tick()
            writes.append(backup.call_count)
        self.assertEqual(writes, [1, 2])
        saver.discard(v)

    def test_one_page_edit_keeps_other_pages_cached(self):
        v = DocumentView(self.pdf("c.pdf", pages=4))
        for i in range(4):
            v.pages[i]._display_list()
        self.rect(v)
        self.assertEqual(sorted(v._dlists), [1, 2, 3])
        v.rotate_page(1, 90)                                 # structural: everything goes
        self.assertEqual(v._dlists, {})


if __name__ == "__main__":
    unittest.main()
