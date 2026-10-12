"""Rotating, deleting and moving pages (and undoing them) renumber the existing page
widgets instead of building new ones for every page, and the widgets still match the pages.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_page_ops_speed
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf as F  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas.document_view import DocumentView  # noqa: E402


class PageOpsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        path = os.path.join(self.tmp.name, "pages.pdf")
        d = F.open()
        for i in range(30):
            d.new_page(width=612 if i % 2 else 792, height=792 if i % 2 else 612)
        d.save(path)
        d.close()
        self.v = DocumentView(path)

    def tearDown(self):
        self.v.doc.close()
        self.v.deleteLater()
        self.tmp.cleanup()

    def check(self):
        v = self.v
        self.assertEqual(len(v.pages), v.doc.page_count)
        for i, w in enumerate(v.pages):
            self.assertEqual(w.index, i)
            r = v.doc[i].rect
            self.assertEqual((w.width(), w.height()),
                             (max(1, int(r.width * v.zoom)), max(1, int(r.height * v.zoom))))

    def test_widgets_reused_and_renumbered(self):
        v = self.v
        first = v.pages[0]
        extra = QLabel("old editor", v.pages[1])           # stands in for an on-page editor
        v.rotate_page(1, 90)
        self.assertIs(v.pages[0], first)                   # not rebuilt
        self.check()
        from PySide6.QtCore import QEvent
        APP.sendPostedEvents(None, QEvent.DeferredDelete)
        from shiboken6 import isValid
        self.assertFalse(isValid(extra))                   # left-over child widgets go
        v.delete_page(3)
        self.check()
        v.move_page(5, 1)
        self.check()
        v.undo(); v.undo(); v.undo()
        self.assertEqual(v.doc.page_count, 30)
        self.assertIs(v.pages[0], first)
        self.check()


if __name__ == "__main__":
    unittest.main()
