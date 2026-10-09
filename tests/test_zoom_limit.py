"""Zoom continues past 800%, up to 6400% on a normal page.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_zoom_limit
"""
import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf as F
from PySide6.QtWidgets import QApplication, QMessageBox
from unittest.mock import patch

from kanzonas.document_view import DocumentView, MAX_ZOOM
from kanzonas.main_window import _slider_to_zoom, _zoom_to_slider

APP = QApplication.instance() or QApplication([])


class ZoomLimit(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        patch.object(QMessageBox, "information", return_value=None).start()
        self.addCleanup(patch.stopall)
        self.views = []
        self.addCleanup(lambda: [v.close_doc() for v in self.views])

    def view(self, w=612, h=792):
        path = self.root / "z.pdf"
        doc = F.open()
        doc.new_page(width=w, height=h)
        doc.save(path)
        doc.close()
        v = DocumentView(str(path))
        self.views.append(v)
        return v

    def test_zoom_passes_800_percent_and_stops_at_6400(self):
        v = self.view()
        v.set_zoom(16)                 # 1600%, used to be clamped to 800%
        self.assertAlmostEqual(v.zoom, 16)
        v.set_zoom(1000)
        self.assertAlmostEqual(v.zoom, MAX_ZOOM)
        self.assertAlmostEqual(MAX_ZOOM, 64)

    def test_huge_page_stays_within_the_widget_limit(self):
        v = self.view(w=300000, h=300000)
        v.set_zoom(64)
        self.assertLess(v.zoom, 64)
        side = max(v.pages[0].width(), v.pages[0].height())
        self.assertLessEqual(side, 16_000_000)

    def test_slider_reaches_both_ends(self):
        self.assertAlmostEqual(_slider_to_zoom(0) * 100, 10, delta=0.5)
        self.assertAlmostEqual(_slider_to_zoom(1000) * 100, 6400, delta=1)
        self.assertLess(_zoom_to_slider(1.0), 500)   # 100% is still in the lower half
        self.assertEqual(_zoom_to_slider(_slider_to_zoom(400)), 400)
