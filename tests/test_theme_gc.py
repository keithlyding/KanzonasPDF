"""Changing the theme while Python's garbage collector frees a widget no longer used: the
theme walks every widget, and a collection in the middle of making that list deleted a
closed dialog the list already held; reading it crashed the app (Linux build of 1.15.10,
tests/test_battery_151_view's theme change, after tests that left such dialogs behind).

The collector is turned on for the test (a window turns Python's automatic collector off,
gc_main), at a collection to nearly every new object for its first FIRST_COLLECTIONS: with
2,000 closed dialogs that crashes the old code every time, and the fixed code passes in a
few seconds. (With it off, nothing was collected and the old code passed too; left at one a
new object for the whole change, the test took 23 minutes in the Mac build's full suite.)

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


FIRST_COLLECTIONS = 50      # collections at one a new object, then the usual thresholds


class Garbage:
    pass


def leave_closed_dialogs(n=2000):
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
        # (the automatic collector on for this test, as it was before gc_main: a window turns
        # it off, and the main thread's timer, which collects instead, doesn't tick in the
        # middle of a theme change; off, no collection came and nothing was tested)
        collecting = gc.isenabled()
        gc.enable()
        self.addCleanup(lambda: None if collecting else gc.disable())

        collections = [0]

        def counted(phase, _info):
            # (the first collections free the closed dialogs, while the widgets are listed
            # and polished; after FIRST_COLLECTIONS the usual thresholds are back)
            if phase == "stop":
                collections[0] += 1
                if collections[0] == FIRST_COLLECTIONS:
                    gc.set_threshold(*before)

        def apply_then_leave_garbage(app, mode):
            # (after the colors are set, so the collection comes while the widgets are listed)
            apply(app, mode)
            leave_closed_dialogs()
            collections[0] = 0
            gc.set_threshold(1)             # (a collection at nearly every new object)
        gc.callbacks.append(counted)
        self.addCleanup(gc.callbacks.remove, counted)
        for mode in ("dark", "light"):
            try:
                with mock.patch.object(theme, "apply", apply_then_leave_garbage):
                    w.set_theme(mode)
            finally:
                gc.set_threshold(*before)
            self.assertTrue(w.theme_actions[mode].isChecked())
            self.assertGreaterEqual(collections[0], 1)      # (a collection did come)


if __name__ == "__main__":
    unittest.main()
