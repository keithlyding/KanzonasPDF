"""Text selection that continues across page breaks.

Run: QT_QPA_PLATFORM=offscreen python -m unittest tests.test_text_span
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import tempfile
import unittest
from pathlib import Path
import pymupdf
from PySide6.QtWidgets import QApplication
from kanzonas.document_view import DocumentView

APP = QApplication.instance() or QApplication([])


class TextSpan(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.views = []
        self.addCleanup(lambda: [v.close_doc() for v in self.views])

    def two_pages(self):
        path = Path(self.tmp.name) / "span.pdf"
        doc = pymupdf.open()
        for text in ("PAGEONE", "PAGETWO"):
            page = doc.new_page()
            page.insert_text((72, 72), text)
        doc.save(path)
        doc.close()
        view = DocumentView(str(path))
        self.views.append(view)
        return view

    def first_char(self, view, index):
        words = view._words(index)
        self.assertTrue(words)
        w = words[0]
        return pymupdf.Point((w[0] + w[2]) / 2, (w[1] + w[3]) / 2)

    def last_char(self, view, index):
        words = view._words(index)
        w = words[-1]
        return pymupdf.Point((w[0] + w[2]) / 2, (w[1] + w[3]) / 2)

    def joined(self, spans):
        return "".join(ch[4] for _i, _mode, words in spans for ch in words)

    def test_drag_down_includes_both_pages(self):
        view = self.two_pages()
        spans = view.text_selection_span(0, self.first_char(view, 0),
                                         1, self.last_char(view, 1))
        text = self.joined(spans)
        self.assertIn("PAGEONE", text)
        self.assertIn("PAGETWO", text)
        self.assertEqual([i for i, _m, w in spans if w], [0, 1])

    def test_drag_up_includes_both_pages(self):
        view = self.two_pages()
        spans = view.text_selection_span(1, self.last_char(view, 1),
                                         0, self.first_char(view, 0))
        text = self.joined(spans)
        self.assertIn("PAGEONE", text)
        self.assertIn("PAGETWO", text)

    def test_same_page_does_not_include_the_other(self):
        view = self.two_pages()
        spans = view.text_selection_span(0, self.first_char(view, 0),
                                         0, self.last_char(view, 0))
        self.assertEqual([i for i, _m, _w in spans], [0])
        self.assertNotIn("PAGETWO", self.joined(spans))
        self.assertIn("PAGEONE", self.joined(spans))

    def test_copy_joins_pages_with_a_blank_line(self):
        view = self.two_pages()
        spans = view.text_selection_span(0, self.first_char(view, 0),
                                         1, self.last_char(view, 1))
        view.set_text_spans([(i, words) for i, _mode, words in spans])
        text = view.selected_text()
        self.assertIn("PAGEONE", text)
        self.assertIn("PAGETWO", text)
        self.assertIn("\n\n", text)
        one, two = text.split("\n\n", 1)
        self.assertIn("PAGEONE", one)
        self.assertIn("PAGETWO", two)
        self.assertNotIn("PAGETWO", one)


if __name__ == "__main__":
    unittest.main()
