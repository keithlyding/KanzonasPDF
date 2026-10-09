"""Efficiency regressions from the v0.81 efficiency audit (P01-P09).

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

    def test_annotation_walk_is_linear(self):
        # page.annots() looks each annotation up from the start (N squared); each_annot
        # walks the list once. 1,500 markups: annots() takes seconds, each_annot a fraction
        import time
        d = F.open()
        pg = d.new_page(width=2000, height=2000)
        for k in range(1500):
            x, y = (k % 50) * 39, (k // 50) * 49
            pg.add_rect_annot(F.Rect(x, y, x + 30, y + 30))
        d = F.open("pdf", d.tobytes())
        pg = d[0]
        t = time.perf_counter()
        got = A.each_annot(pg)
        took = time.perf_counter() - t
        self.assertEqual([a.xref for a in got], [a.xref for a in pg.annots()])
        self.assertLess(took, 0.5)
        self.assertEqual(len(A.each_annot(pg, types=[F.PDF_ANNOT_SQUARE])), 1500)

    def test_markups_list_rereads_only_changed_pages(self):
        from kanzonas import markups_panel as MP
        v = DocumentView(self.pdf("m.pdf", pages=4))
        for i in range(4):
            v._create(i, {"kind": "rect", "props": dict(A.DEFAULTS["rect"]),
                          "rect": F.Rect(10, 10, 50, 50)})
        panel = MP.MarkupsPanel()
        panel.refresh(v.doc, v.take_markup_changes())
        self.assertEqual(len(panel._rows), 4)
        v._create(2, {"kind": "rect", "props": dict(A.DEFAULTS["rect"]),
                      "rect": F.Rect(60, 60, 90, 90)})
        changed = v.take_markup_changes()
        self.assertEqual(changed, {2})
        with mock.patch.object(MP, "collect", wraps=MP.collect) as collect:
            panel.refresh(v.doc, changed)
        collect.assert_called_once_with(v.doc, {2})
        self.assertEqual(len(panel._rows), 5)
        self.assertEqual([r[0] for r in panel._rows], [0, 1, 2, 2, 3])

    def test_search_runs_in_slices_and_jumps_early(self):
        v = DocumentView(self.pdf("s.pdf", pages=30))
        with mock.patch.object(DV.DocumentView, "SEARCH_SLICE", 0.0):  # one page per slice
            self.assertEqual(v.find("page"), 1)        # first match shown right away
            self.assertTrue(v._search_todo)            # the rest is still to search
            while v._search_todo:
                v._search_step()
        self.assertEqual(v._search_count(), 30)
        self.assertEqual(v.find("page"), 30)           # then next / previous over all
        self.assertEqual(v.current_hit(), (1, 0))
        with mock.patch.object(DV.DocumentView, "SEARCH_SLICE", 0.0):
            self.assertEqual(v.find("nothing-like-this"), -1)  # still searching, none yet
        v.clear_search()
        self.assertIsNone(v._search_todo)


    def many(self, n=2000):
        d = F.open()
        for i in range(n):
            d.new_page(width=200, height=200).insert_text((20, 40), "p%d" % i)
        p = os.path.join(self.tmp.name, "many.pdf")
        d.save(p)
        v = DocumentView(p)
        v.resize(800, 600)
        return v

    def test_page_lookup_is_logarithmic(self):
        v = self.many()
        for i in (0, 1, 777, 1500, 1990):
            v.goto_page(i)
            self.assertEqual(v.current_page(), i)
        calls = []
        orig = type(v.pages[0]).y
        with mock.patch.object(type(v.pages[0]), "y", lambda w: calls.append(1) or orig(w)):
            v.current_page()
        self.assertLess(len(calls), 40)                 # binary search, not 1,500 widgets

    def test_scrolling_visits_only_pages_with_bitmaps(self):
        v = self.many()
        v.goto_page(1000)
        dropped = []
        for w in v.pages:
            w.drop_cache = lambda i=w.index: dropped.append(i)
        v._pix_pages = {3, 1000, 1001}
        v._on_scroll()
        self.assertEqual(dropped, [3])
        self.assertEqual(v._pix_pages, {1000, 1001})

    def test_parsed_page_caches_are_bounded(self):
        v = self.many(300)
        for i in range(200):
            v._words(i)
            v._dlists[i] = object()
        v.goto_page(250)
        self.assertLessEqual(len(v._word_cache), DV.PAGE_CACHE_PAGES)
        self.assertLessEqual(len(v._dlists), DV.PAGE_CACHE_PAGES)


if __name__ == "__main__":
    unittest.main()
