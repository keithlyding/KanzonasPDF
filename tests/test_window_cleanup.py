"""The test suite deletes the main windows it closes (tests/__init__.py): left, they kept
about 800,000 widgets by the end of the suite, and the theme change in test_theme_gc took
23 minutes in the Mac build.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_window_cleanup
"""
import gc
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import main_window  # noqa: E402


def settle():
    for _ in range(3):
        APP.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        gc.collect()


class SuiteDeletesClosedMainWindows(unittest.TestCase):
    def test_a_closed_main_window_is_gone_by_the_next_test(self):
        from tests import _delete_closed_windows
        w = main_window.MainWindow()
        w.show()
        APP.processEvents()
        n = len(QApplication.allWidgets())
        w._close_confirmed = True
        w.close()
        del w
        _delete_closed_windows()
        settle()
        self.assertLess(len(QApplication.allWidgets()), n - 1000)


if __name__ == "__main__":
    unittest.main()
