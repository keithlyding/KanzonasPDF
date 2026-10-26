"""Opening a PDF while KanzonasPDF runs brings its window to the front: the program handing
over the file lets it (AllowSetForegroundWindow), and the running one restores itself if
minimized and comes forward (on Windows; elsewhere these calls do nothing).

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_bring_to_front
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QMainWindow  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import winfocus  # noqa: E402


class FakeUser32:
    def __init__(self):
        self.calls = []

    def AllowSetForegroundWindow(self, who):
        self.calls.append(("allow", who))
        return 1

    def SetForegroundWindow(self, hwnd):
        self.calls.append(("front", hwnd))
        return 1


class BringToFront(unittest.TestCase):
    def test_the_new_program_passes_on_its_right_to_come_forward(self):
        u = FakeUser32()
        with mock.patch.object(winfocus, "_user32", lambda: u):
            winfocus.allow_foreground()
        self.assertEqual(u.calls, [("allow", 0xFFFFFFFF)])         # ASFW_ANY

    def test_the_running_window_restores_and_comes_forward(self):
        win = QMainWindow()
        self.addCleanup(win.close)
        win.show()
        win.setWindowState(Qt.WindowMinimized | Qt.WindowMaximized)
        u = FakeUser32()
        with mock.patch.object(winfocus, "_user32", lambda: u):
            winfocus.bring_to_front(win)
        self.assertFalse(win.windowState() & Qt.WindowMinimized)
        self.assertTrue(win.windowState() & Qt.WindowMaximized)    # stays maximized
        self.assertEqual(u.calls, [("front", int(win.winId()))])

    def test_nothing_happens_off_windows(self):
        with mock.patch.object(sys, "platform", "linux"):
            self.assertIsNone(winfocus._user32())
            winfocus.allow_foreground()                             # no error


if __name__ == "__main__":
    unittest.main()
