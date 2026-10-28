"""One KanzonasPDF window: PDFs opened at the same moment (Explorer starts one program per
file when several are opened together) all end up as tabs in one window, and a socket file
left by a run that crashed doesn't stop the next start from taking over.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_single_instance
"""
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
import uuid

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf as F  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])


# Runs the real entry point with message boxes that don't wait, nothing from the user's own
# settings (no backups to recover, no session, no update check), writing the open tabs to
# $KZ_STATE, and quitting after $KZ_LIFE seconds.
CHILD = r"""
import json, os, sys
sys.path.insert(0, os.environ["KZ_ROOT"])
from unittest import mock
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QMessageBox
for name in ("information", "warning", "critical", "question"):
    mock.patch.object(QMessageBox, name, return_value=QMessageBox.No).start()
from kanzonas import main_window
for name in ("recover_backups", "restore_session", "start_update_check"):
    mock.patch.object(main_window.MainWindow, name, lambda self: None).start()
init = main_window.MainWindow.__init__

def dump():
    tabs = [os.path.basename(w.tabs.widget(i).path)
            for w in main_window.windows() for i in range(w.tabs.count())]
    with open(os.environ["KZ_STATE"] + ".tmp", "w") as f:
        json.dump(tabs, f)
    os.replace(os.environ["KZ_STATE"] + ".tmp", os.environ["KZ_STATE"])

def start(self, *a, **k):
    init(self, *a, **k)
    if not hasattr(main_window, "_kz_timer"):
        main_window._kz_timer = t = QTimer()
        t.timeout.connect(dump)
        t.start(100)
        QTimer.singleShot(int(float(os.environ["KZ_LIFE"]) * 1000), lambda: os._exit(0))
main_window.MainWindow.__init__ = start
sys.argv = ["kanzonas"] + sys.argv[1:]
from kanzonas.__main__ import main
main()
"""


class SingleInstance(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        user = "kztest" + uuid.uuid4().hex[:8]      # a pipe / socket name of its own
        self.env = dict(os.environ, QT_QPA_PLATFORM="offscreen", KZ_ROOT=ROOT, KZ_LIFE="30",
                        HOME=self.tmp, TMPDIR=self.tmp, TEMP=self.tmp, TMP=self.tmp,
                        LOGNAME=user, USER=user, LNAME=user, USERNAME=user)
        self.procs = []
        self.addCleanup(self.stop)

    def stop(self):
        for p in self.procs:
            if p.poll() is None:
                p.kill()
            p.wait()

    def launch(self, name):
        path = os.path.join(self.tmp, name)
        d = F.open()
        d.new_page()
        d.save(path)
        d.close()
        state = os.path.join(self.tmp, name + ".json")
        p = subprocess.Popen([sys.executable, "-c", CHILD, path], cwd=self.tmp,
                             env=dict(self.env, KZ_STATE=state),
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.procs.append(p)
        return p, state

    def tabs_when(self, states, test, timeout=40):
        end = time.time() + timeout
        while time.time() < end:
            seen = []
            for st in states:
                try:
                    with open(st) as f:
                        seen.append(json.load(f))
                except (OSError, ValueError):
                    pass
            if test(seen):
                return seen
            time.sleep(0.2)
        return seen

    def test_pdfs_opened_at_the_same_moment_share_one_window(self):
        started = [self.launch(n) for n in ("one.pdf", "two.pdf", "three.pdf")]
        seen = self.tabs_when([st for _p, st in started],
                              lambda s: any(len(t) == 3 for t in s))
        self.assertEqual(sorted(len(t) for t in seen if t), [3], seen)
        # the programs that handed their file over quit once the window has answered them
        # (they wait for its handle to bring it to the front): give them time to exit
        end = time.time() + 15
        running = [p for p, _st in started if p.poll() is None]
        while len(running) > 1 and time.time() < end:
            time.sleep(0.2)
            running = [p for p, _st in started if p.poll() is None]
        self.assertEqual(len(running), 1)

    def test_the_first_listens_and_the_next_one_connects(self):
        from kanzonas.__main__ import first_instance
        name = "KanzonasPDF-test-" + uuid.uuid4().hex[:8]
        server, sock = first_instance(name)
        self.assertIsNotNone(server)
        self.assertIsNone(sock)
        self.addCleanup(server.close)
        server2, sock2 = first_instance(name)
        self.assertIsNone(server2)
        self.assertIsNotNone(sock2)
        sock2.disconnectFromServer()

    @unittest.skipIf(sys.platform == "win32", "a Windows pipe goes away with its program")
    def test_socket_left_by_a_crash_is_taken_over(self):
        p, st = self.launch("one.pdf")
        self.tabs_when([st], lambda s: s and len(s[0]) == 1)
        p.kill()
        p.wait()
        p2, st2 = self.launch("two.pdf")
        self.tabs_when([st2], lambda s: s and len(s[0]) == 1)
        self.assertIsNone(p2.poll())                # it's the window now
        p3, _st3 = self.launch("three.pdf")
        p3.wait(20)                                 # handed its file over and quit
        seen = self.tabs_when([st2], lambda s: s and len(s[0]) == 2)
        self.assertEqual(seen, [["two.pdf", "three.pdf"]])


if __name__ == "__main__":
    unittest.main()
