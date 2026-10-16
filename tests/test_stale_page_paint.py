"""After pages are deleted (or an undo removes them), the widgets of the pages that are gone
must not paint the document: they are hidden at once, and a repaint that still reaches one
(its deleteLater is queued) fills white instead of raising IndexError inside paintEvent."""
import contextlib
import io
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas.document_view import DocumentView  # noqa: E402
from kanzonas.page_widget import PageWidget  # noqa: E402


def pdf(n=4):
    d = pymupdf.open()
    for i in range(n):
        d.new_page().insert_text((72, 72), f"page {i}")
    p = os.path.join(tempfile.mkdtemp(), "p.pdf")
    d.save(p)
    return p


class StalePagePaint(unittest.TestCase):
    def view(self):
        v = DocumentView(pdf())
        v.resize(900, 700)
        v.show()
        APP.processEvents()
        self.addCleanup(v.close_doc)
        return v

    def test_widgets_of_deleted_pages_are_hidden_at_once(self):
        v = self.view()
        widgets = list(v.pages)
        v.delete_pages([2, 3])
        self.assertEqual(len(v.pages), 2)
        for w in widgets[2:]:
            self.assertTrue(w.isHidden(), "a removed page widget stays hidden until deleted")
        for w in widgets[:2]:
            self.assertFalse(w.isHidden())

    def test_repaint_of_a_gone_page_does_not_touch_the_document(self):
        v = self.view()
        w = v.pages[-1]
        w.index = 99                    # as if its page were deleted while a repaint is queued
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            w.repaint()
            APP.processEvents()
        self.assertNotIn("Traceback", err.getvalue())
        self.assertNotIn("IndexError", err.getvalue())

    def test_undo_of_many_page_deletions_paints_cleanly(self):
        v = self.view()
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            for _ in range(3):
                v.delete_page(0)
            for _ in range(3):
                v.undo()
            for _ in range(6):
                APP.processEvents()
            for w in v.widget().findChildren(PageWidget):
                w.repaint()
            APP.processEvents()
        self.assertEqual(v.doc.page_count, 4)
        self.assertEqual(len(v.pages), 4)
        self.assertNotIn("Traceback", err.getvalue())


if __name__ == "__main__":
    unittest.main()
