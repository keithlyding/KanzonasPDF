"""A window pulled out of the main one (Window > Move to new window) is deleted when it
closes, with everything in it: in the classic layout the zoom row (Fit page, Fit width,
Actual size and the zoom slider) had no parent, and each closed window left it behind.

The test suite deletes the main windows it closes (tests/__init__.py): left, they kept
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

from kanzonas import main_window, paths  # noqa: E402


def settle():
    for _ in range(3):
        APP.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        gc.collect()


class PulledOutWindow(unittest.TestCase):
    def setUp(self):
        self.settings = paths.settings()
        old = self.settings.value("ui_mode")
        self.addCleanup(lambda: self.settings.setValue("ui_mode", old) if old is not None
                        else self.settings.remove("ui_mode"))
        self.addCleanup(lambda: [setattr(x, "_close_confirmed", True) or x.close()
                                 for x in main_window.windows()])

    def left_after_closing_one(self, layout):
        # (the layout set before the main window is made: changed after, the main window
        # would rebuild its own bars when the new window applies it)
        self.settings.setValue("ui_mode", layout)
        main = main_window.MainWindow()
        main.show()
        settle()
        # (the widgets' Python objects kept while comparing: an id is reused once its
        # object is freed, and a widget there all along would count as new)
        self.kept = QApplication.allWidgets()
        before = set(map(id, self.kept))
        w = main_window.MainWindow(primary=False)
        w.show()
        APP.processEvents()
        self.assertGreater(len(QApplication.allWidgets()), len(before) + 100)
        w._close_confirmed = True
        w.close()
        del w
        settle()
        return [type(x).__name__ for x in QApplication.allWidgets() if id(x) not in before]

    def test_nothing_left_in_the_classic_layout(self):
        self.assertEqual(self.left_after_closing_one("classic"), [])

    def test_nothing_left_in_the_ribbon_layout(self):
        self.assertEqual(self.left_after_closing_one("ribbon"), [])


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
