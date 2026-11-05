"""The count beside Find ("2 of 3") belongs to the tab shown: another tab shows its own, and
with every document closed there's none (it stayed, with nothing to go through).

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_find_count_tabs
"""
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf
from PySide6.QtWidgets import QApplication, QMessageBox

from kanzonas.main_window import MainWindow

APP = QApplication.instance() or QApplication([])


def _pdf(path, text):
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), text, fontsize=12)
    doc.save(path)
    doc.close()


class FindCountTabs(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(patch.stopall)
        for name in ("information", "warning", "critical"):
            patch.object(QMessageBox, name, return_value=None).start()
        patch.object(QMessageBox, "question", return_value=QMessageBox.Discard).start()
        root = Path(self.tmp.name)
        self.a, self.b = str(root / "a.pdf"), str(root / "b.pdf")
        _pdf(self.a, "door door door")
        _pdf(self.b, "window only")
        self.w = MainWindow()
        self.addCleanup(self.w.deleteLater)
        self.w.show()

    def _search(self, text):
        w = self.w
        w.search.setText(text)
        w._find(False)
        end = time.time() + 10
        while time.time() < end and w.view().search_position()[2]:
            APP.processEvents()
        w._find(False)
        APP.processEvents()

    def test_count_follows_the_tab_and_goes_with_the_last_document(self):
        w = self.w
        w.open_file(self.a)
        w.open_file(self.b)
        APP.processEvents()
        w.tabs.setCurrentIndex(0)
        self._search("door")
        self.assertTrue(w.find_count.isVisible())
        self.assertIn("3", w.find_count.text())
        self.assertTrue(w.find_next_btn.isEnabled())
        w.tabs.setCurrentIndex(1)          # nothing searched in this one
        APP.processEvents()
        self.assertFalse(w.find_count.isVisible(), w.find_count.text())
        self.assertFalse(w.find_next_btn.isEnabled())
        w.tabs.setCurrentIndex(0)          # back: its own count again
        APP.processEvents()
        self.assertTrue(w.find_count.isVisible())
        self.assertIn("3", w.find_count.text())
        while w.tabs.count():
            w.close_tab(0)
            APP.processEvents()
        self.assertIsNone(w.view())
        self.assertFalse(w.find_count.isVisible(), w.find_count.text())
        self.assertFalse(w.find_next_btn.isEnabled())
        self.assertFalse(w.find_prev_btn.isEnabled())


if __name__ == "__main__":
    unittest.main()
