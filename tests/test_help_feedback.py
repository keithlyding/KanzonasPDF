"""Help > Report a problem or suggest an idea opens GitHub's issue forms in the browser.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_help_feedback
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QDesktopServices  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas.main_window import MainWindow  # noqa: E402


class Feedback(unittest.TestCase):
    def setUp(self):
        self.w = MainWindow()
        self.addCleanup(lambda: (setattr(self.w, "_close_confirmed", True), self.w.close()))

    def test_opens_the_issue_forms(self):
        opened = []
        with mock.patch.object(QDesktopServices, "openUrl",
                               lambda url: opened.append(url.toString())):
            self.w.a_feedback.trigger()
        self.assertEqual(opened, ["https://github.com/keithlyding/KanzonasPDF/issues/new/choose"])
        self.assertIn("confidential", self.w.statusBar().currentMessage())

    def test_in_the_help_menu_with_nothing_open(self):
        help_menu = next(a.menu() for a in self.w.menuBar().actions() if a.text() == "&Help")
        self.assertIn(self.w.a_feedback, help_menu.actions())
        self.assertTrue(self.w.a_feedback.isEnabled())


if __name__ == "__main__":
    unittest.main()
