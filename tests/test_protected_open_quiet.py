"""A PDF protected against changes opens without a message box (from using 1.7.1: the box
came up every time such a sheet was opened, though it's mostly only read). The window title
says [protected] and the status bar says why; an attempt to change it explains, and Edit text
says so before any typing.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_protected_open_quiet
"""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import main_window  # noqa: E402


def protected():
    d = pymupdf.open()
    p = d.new_page()
    p.insert_text((72, 100), "Sheet A-101 general notes", fontsize=14)
    path = os.path.join(tempfile.mkdtemp(), "protected.pdf")
    d.save(path, encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="owner", user_pw="",
           permissions=pymupdf.PDF_PERM_PRINT | pymupdf.PDF_PERM_COPY)
    return path


class Quiet(unittest.TestCase):
    def setUp(self):
        self.boxes = []

        def box(*a, **k):
            self.boxes.append(a[2] if len(a) > 2 else "")
            return QMessageBox.Ok
        self.enterContext(mock.patch.object(QMessageBox, "information", box))
        self.enterContext(mock.patch.object(QMessageBox, "warning", box))
        w = self.w = main_window.MainWindow()
        self.addCleanup(lambda: [setattr(x, "_close_confirmed", True) or x.close()
                                 for x in main_window.windows()])
        w.show()
        w.open_file(protected())
        for _ in range(3):
            APP.processEvents()
        self.v = w.view()

    def test_no_box_on_opening_but_the_tab_and_status_bar_say_so(self):
        self.assertTrue(self.v.read_only)
        self.assertEqual(self.boxes, [])
        self.assertIn("protected", self.w.statusBar().currentMessage())
        self.assertIn("[protected]", self.w.windowTitle())

    def test_an_edit_still_explains(self):
        self.v.modify(lambda: None, [0])
        self.assertEqual(len(self.boxes), 1)
        self.assertIn("protected against changes", self.boxes[0])

    def test_edit_text_says_so_before_any_typing(self):
        self.v.edit_text_at(0, pymupdf.Point(120, 96))
        self.assertIsNone(self.v._inline)            # (no editor opened)
        self.assertEqual(len(self.boxes), 1)


if __name__ == "__main__":
    unittest.main()
