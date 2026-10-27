"""Opening a PDF while KanzonasPDF runs brings its window to the front. Windows lets only the
program started by the click do that, so the running KanzonasPDF answers the hand-over with
its window handle and the new program brings that window forward (restored if minimized)
before quitting; the running one also tries itself. Off Windows these calls do nothing.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_bring_to_front
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtNetwork import QLocalServer, QLocalSocket  # noqa: E402
from PySide6.QtWidgets import QApplication, QMainWindow  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import winfocus  # noqa: E402


class FakeUser32:
    """Windows' user32 as far as bringing a window forward goes: SetForegroundWindow
    succeeds only when `allowed` (Windows' foreground lock), or with the input of the
    window in front attached."""

    def __init__(self, allowed=True, minimized=False):
        self.calls = []
        self.allowed = allowed
        self.minimized = minimized
        self.front = 99
        self.attached = False

    def AllowSetForegroundWindow(self, who):
        self.calls.append(("allow", who))
        return 1

    def IsIconic(self, hwnd):
        return self.minimized

    def ShowWindow(self, hwnd, how):
        self.calls.append(("show", hwnd, how))
        self.minimized = False
        return 1

    def SetForegroundWindow(self, hwnd):
        self.calls.append(("front", hwnd))
        if self.allowed or self.attached:
            self.front = hwnd
            return 1
        return 0

    def GetForegroundWindow(self):
        return self.front

    def GetWindowThreadProcessId(self, hwnd, pid):
        return 7

    def AttachThreadInput(self, a, b, on):
        self.calls.append(("attach", on))
        self.attached = bool(on)
        return 1

    def BringWindowToTop(self, hwnd):
        return 1


class Activate(unittest.TestCase):
    def setUp(self):
        p = mock.patch.object(winfocus, "_current_thread", lambda: 3)
        p.start()
        self.addCleanup(p.stop)

    def test_the_new_program_passes_on_its_right_to_come_forward(self):
        u = FakeUser32()
        with mock.patch.object(winfocus, "_user32", lambda: u):
            winfocus.allow_foreground()
        self.assertEqual(u.calls, [("allow", 0xFFFFFFFF)])         # ASFW_ANY

    def test_a_minimized_window_is_restored_and_brought_forward(self):
        u = FakeUser32(minimized=True)
        with mock.patch.object(winfocus, "_user32", lambda: u):
            self.assertTrue(winfocus.activate(1234))
        self.assertEqual(u.calls[:2], [("show", 1234, winfocus.SW_RESTORE), ("front", 1234)])
        self.assertEqual(u.front, 1234)

    def test_when_windows_says_no_it_takes_the_input_of_the_window_in_front(self):
        u = FakeUser32(allowed=False)
        with mock.patch.object(winfocus, "_user32", lambda: u):
            self.assertTrue(winfocus.activate(1234))
        self.assertIn(("attach", True), u.calls)
        self.assertEqual(u.calls[-1], ("attach", False))          # and lets go again
        self.assertEqual(u.front, 1234)

    def test_nothing_happens_off_windows(self):
        with mock.patch.object(sys, "platform", "linux"):
            self.assertIsNone(winfocus._user32())
            winfocus.allow_foreground()                             # no error
            self.assertFalse(winfocus.activate(1234))


class HandOver(unittest.TestCase):
    def test_the_running_window_answers_and_the_new_program_brings_it_forward(self):
        name = "kz-front-%d" % os.getpid()
        QLocalServer.removeServer(name)
        server = QLocalServer()
        self.assertTrue(server.listen(name))
        self.addCleanup(server.close)
        got = []

        def incoming():
            conn = server.nextPendingConnection()
            conn.write(b"HWND 4321\n")           # what __main__ answers, straight away
            conn.flush()
            conn.readyRead.connect(lambda: got.append(bytes(conn.readAll())))
        server.newConnection.connect(incoming)
        sock = QLocalSocket()
        sock.connectToServer(name)
        self.assertTrue(sock.waitForConnected(2000))
        sock.write(b"C:/plans/A-101.pdf\n")
        sock.flush()
        u = FakeUser32(allowed=True)
        with mock.patch.object(winfocus, "_user32", lambda: u), \
                mock.patch.object(winfocus, "_current_thread", lambda: 3):
            # (the server answers when the event loop runs: wait for it as the new program does)
            for _ in range(50):
                APP.processEvents()
                if sock.bytesAvailable():
                    break
                sock.waitForReadyRead(20)
            self.assertTrue(winfocus.front_from_reply(sock, 1000))
        self.assertEqual(u.front, 4321)
        sock.disconnectFromServer()

    def test_no_answer_is_no_harm(self):
        class Silent:
            def canReadLine(self):
                return False

            def waitForReadyRead(self, ms):
                return False
        self.assertFalse(winfocus.front_from_reply(Silent(), 10))

    def test_main_answers_with_the_window_handle(self):
        with open(os.path.join(os.path.dirname(winfocus.__file__), "__main__.py")) as f:
            src = f.read()
        self.assertIn('"HWND %d\\n" % winfocus.handle(state["win"])', src)
        self.assertIn("winfocus.front_from_reply(sock)", src)


class RunningWindow(unittest.TestCase):
    def test_the_running_window_restores_and_tries_to_come_forward(self):
        win = QMainWindow()
        self.addCleanup(win.close)
        win.show()
        win.setWindowState(Qt.WindowMinimized | Qt.WindowMaximized)
        u = FakeUser32()
        with mock.patch.object(winfocus, "_user32", lambda: u), \
                mock.patch.object(winfocus, "handle", lambda w: 777), \
                mock.patch.object(winfocus, "_current_thread", lambda: 3):
            winfocus.bring_to_front(win)
        self.assertFalse(win.windowState() & Qt.WindowMinimized)
        self.assertTrue(win.windowState() & Qt.WindowMaximized)    # stays maximized
        self.assertIn(("front", 777), u.calls)


if __name__ == "__main__":
    unittest.main()
