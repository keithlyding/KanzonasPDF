"""Pages added, removed or moved: the whole collection (gc.collect) that frees a page held only by
a reference cycle runs only while MuPDF still has one of the document's pages loaded and in use.

It goes through every object Python has: late in the test run (1.55 million objects) it took
2.06-2.51 s of the 2.77-3.14 s that inserting 300 pages into 600 took on the Mac build machine,
which missed the 3.0 s budget three times, and 0.86 s of 1.41 s on the Linux one (15 Nov 2026).

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_structural_gc
"""
import gc
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import document_view  # noqa: E402
from tests.test_battery_151_pages import Base, first_lines, numbered  # noqa: E402


class StructuralCollection(Base):
    def collections(self, v, change):
        calls = []
        real = document_view._collect_all
        with mock.patch.object(document_view, "_collect_all",
                               side_effect=lambda: (calls.append(1), real())):
            change(v)
        return len(calls)

    def test_no_page_alive_no_collection(self):
        v = self.view(numbered())
        gc.collect()
        self.assertFalse(document_view._page_held(v.doc))
        self.assertEqual(self.collections(v, lambda v: v.move_page(1, 1)), 0)
        self.assertEqual(first_lines(v.doc), ["PAGE 1", "PAGE 3", "PAGE 2", "PAGE 4"])

    def test_a_page_alive_is_collected_first(self):
        v = self.view(numbered())
        held = v.doc[2]
        self.assertTrue(document_view._page_held(v.doc))
        self.assertEqual(self.collections(v, lambda v: v.move_page(1, 1)), 1)
        self.assertEqual(first_lines(v.doc), ["PAGE 1", "PAGE 3", "PAGE 2", "PAGE 4"])
        del held

    def test_a_page_in_a_reference_cycle_is_freed_before_the_move(self):
        v = self.view(numbered())

        class Holder:
            pass
        page = v.doc[2]
        h = Holder()
        h.page, page.holder = page, h       # (as an Annot and its Page)
        del page, h
        self.assertTrue(document_view._page_held(v.doc))
        reopened = []
        with mock.patch.object(v, "_reopen", side_effect=lambda: reopened.append(1)):
            v.move_page(1, 1)
        self.assertEqual(reopened, [])      # (freed first: nothing stale to open again for)
        self.assertFalse(document_view._page_held(v.doc))
        self.assertEqual(first_lines(v.doc), ["PAGE 1", "PAGE 3", "PAGE 2", "PAGE 4"])
        disk = pymupdf.open(stream=v.doc.tobytes(), filetype="pdf")
        self.assertEqual(first_lines(disk), ["PAGE 1", "PAGE 3", "PAGE 2", "PAGE 4"])

    def test_a_page_in_a_cycle_that_pymupdf_no_longer_lists_is_freed_too(self):
        # (the random battery, seed 9, step 1157: PyMuPDF forgets its pages at each change of
        # pages, while an Annot in a cycle kept one alive; here a page's lower-level wrapper)
        v = self.view(numbered())

        class Holder:
            pass
        h = Holder()
        h.pdf_page, h.me = v.doc[2]._pdf_page(), h
        del h
        self.assertEqual(list(v.doc._page_refs.values()), [])
        self.assertTrue(document_view._page_held(v.doc))
        reopened = []
        with mock.patch.object(v, "_reopen", side_effect=lambda: reopened.append(1)):
            v.move_page(1, 1)
        self.assertEqual(reopened, [])
        self.assertFalse(document_view._page_held(v.doc))
        self.assertEqual(first_lines(v.doc), ["PAGE 1", "PAGE 3", "PAGE 2", "PAGE 4"])

    def test_a_page_let_go_of_does_not_count(self):
        v = self.view(numbered())
        page = v.doc[1]
        self.assertTrue(document_view._page_held(v.doc))
        del page
        self.assertFalse(document_view._page_held(v.doc))

    def test_another_pymupdf_collects_as_before(self):
        class Doc:
            pass
        self.assertTrue(document_view._page_held(Doc()))


if __name__ == "__main__":
    unittest.main()
