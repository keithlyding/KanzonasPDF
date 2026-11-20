"""Ctrl+W closes the tab, as Ctrl+F4 does (File > Close tab), asking first about unsaved
changes. The owner, 19 Nov 2026: "Can ctrl+w close the tab (and ask to save if needed)?"

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_close_tab_key
"""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QKeySequence  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import main_window  # noqa: E402


def a_pdf():
    d = pymupdf.open()
    d.new_page().insert_text((72, 100), "Page 1")
    path = os.path.join(tempfile.mkdtemp(), "doc.pdf")
    d.save(path)
    return path


class CloseTabKey(unittest.TestCase):
    def setUp(self):
        w = self.w = main_window.MainWindow()
        self.addCleanup(lambda: [setattr(x, "_close_confirmed", True) or x.close()
                                 for x in main_window.windows()])
        w.resize(1000, 700)
        w.show()
        w.activateWindow()
        w.open_file(a_pdf())
        APP.processEvents()

    def press(self, key):
        QTest.keyClick(self.w.view(), key, Qt.ControlModifier)
        APP.processEvents()

    def test_both_keys_are_on_close_tab(self):
        keys = [k.toString() for k in self.w.a_close.shortcuts()]
        self.assertEqual(keys, ["Ctrl+W", "Ctrl+F4"])
        self.assertEqual(self.w.a_close.shortcut(), QKeySequence("Ctrl+W"))

    def test_ctrl_w_closes_the_tab(self):
        self.press(Qt.Key_W)
        self.assertEqual(self.w.tabs.count(), 0)

    def test_ctrl_f4_still_closes_it(self):
        self.press(Qt.Key_F4)
        self.assertEqual(self.w.tabs.count(), 0)

    def test_unsaved_changes_are_asked_about_first(self):
        v = self.w.view()
        v.dirty = True
        with mock.patch.object(QMessageBox, "question",
                               return_value=QMessageBox.Cancel) as asked:
            self.press(Qt.Key_W)
        self.assertTrue(asked.called)
        self.assertEqual(self.w.tabs.count(), 1)        # (Cancel: the tab stays)
        with mock.patch.object(QMessageBox, "question", return_value=QMessageBox.Discard):
            self.press(Qt.Key_W)
        self.assertEqual(self.w.tabs.count(), 0)

    def test_the_keys_stay_after_saved_shortcuts_are_applied(self):
        self.w._apply_saved_shortcuts()
        self.assertEqual([k.toString() for k in self.w.a_close.shortcuts()],
                         ["Ctrl+W", "Ctrl+F4"])


if __name__ == "__main__":
    unittest.main()
