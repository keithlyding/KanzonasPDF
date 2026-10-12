"""Crop pages: crop this page or all pages to a dragged box, and Remove crop.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_crop
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf as F  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas.document_view import DocumentView  # noqa: E402


class Crop(unittest.TestCase):
    def view(self):
        d = F.open()
        for i in range(3):
            d.new_page(width=600, height=800).insert_text((120, 150), f"Keep {i}")
        p = os.path.join(tempfile.mkdtemp(), "c.pdf")
        d.save(p)
        v = DocumentView(p)
        self.addCleanup(v.close_doc)
        return v

    def test_crop_this_page_then_again_then_remove(self):
        v = self.view()
        v.crop_pages(0, F.Rect(100, 100, 400, 500))
        self.assertEqual(v.doc[0].rect, F.Rect(0, 0, 300, 400))
        self.assertEqual(v.doc[1].rect, F.Rect(0, 0, 600, 800))
        self.assertIn("Keep 0", v.doc[0].get_text())
        self.assertEqual(v.pages[0].width(), int(300 * v.zoom))      # view follows
        # cropping a cropped page: the box is in what you see now
        v.crop_pages(0, F.Rect(10, 10, 110, 110))
        self.assertEqual(v.doc[0].cropbox, F.Rect(110, 110, 210, 210))
        v.undo()
        self.assertEqual(v.doc[0].cropbox, F.Rect(100, 100, 400, 500))
        v.remove_crop(0)
        self.assertEqual(v.doc[0].rect, F.Rect(0, 0, 600, 800))

    def test_crop_all_pages(self):
        v = self.view()
        v.crop_pages(1, F.Rect(50, 60, 350, 460), all_pages=True)
        for i in range(3):
            self.assertEqual(v.doc[i].cropbox, F.Rect(50, 60, 350, 460))
        v.remove_crop(0, all_pages=True)
        for i in range(3):
            self.assertEqual(v.doc[i].rect, F.Rect(0, 0, 600, 800))

    def test_rotated_page(self):
        v = self.view()
        v.doc[0].set_rotation(90)
        v.crop_pages(0, F.Rect(100, 100, 400, 500))
        self.assertEqual(v.doc[0].rect, F.Rect(0, 0, 400, 300))      # shown turned


if __name__ == "__main__":
    unittest.main()
