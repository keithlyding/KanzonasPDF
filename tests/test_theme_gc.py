"""Changing the theme while Python's garbage collector frees a widget no longer used: the
theme walks every widget, and a collection in the middle of making that list deleted a
closed dialog the list already held; reading it crashed the app (Linux build of 1.15.10,
tests/test_battery_151_view's theme change, after tests that left such dialogs behind).

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_theme_gc
"""
import gc
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QDialog, QTableWidget  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import main_window, theme  # noqa: E402


class Garbage:
    pass


def leave_closed_dialogs(n=30):
    """Dialogs only a reference cycle keeps (freed at the next collection), each with Qt's
    own child widgets (scroll bars, headers) that Python has no object for yet: making the
    list of widgets makes those objects, and that can start a collection."""
    for _ in range(n):
        g = Garbage()
        g.dialog = QDialog()
        g.dialog.kz_garbage = g
        QTableWidget(5, 5, g.dialog)


class ThemeAndCollector(unittest.TestCase):
    def test_a_collection_while_the_theme_changes(self):
        w = main_window.MainWindow()
        self.addCleanup(lambda: [setattr(x, "_close_confirmed", True) or x.close()
                                 for x in main_window.windows()])
        old = w.settings.value("theme")
        self.addCleanup(lambda: w.settings.setValue("theme", old) if old is not None
                        else w.settings.remove("theme"))
        before = gc.get_threshold()
        apply = theme.apply

        def apply_then_leave_garbage(app, mode):
            # (after the colors are set, so the collection comes while the widgets are listed)
            apply(app, mode)
            leave_closed_dialogs()
            gc.set_threshold(1)             # (a collection at nearly every new object)
        for mode in ("dark", "light"):
            try:
                with mock.patch.object(theme, "apply", apply_then_leave_garbage):
                    w.set_theme(mode)
            finally:
                gc.set_threshold(*before)
            self.assertTrue(w.theme_actions[mode].isChecked())


if __name__ == "__main__":
    unittest.main()
