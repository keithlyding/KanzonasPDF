"""A setup updating KanzonasPDF while it runs (the installer closes running copies), or
Windows shutting down, ends the program without closing its windows: the open files are still
remembered for Preferences > Start-up > Reopen the documents..., and unsaved changes are kept
as backup copies offered at the next start.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_windows_ending
"""
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf as F  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import autosave, main_window, paths  # noqa: E402
from kanzonas.main_window import MainWindow  # noqa: E402


class WindowsEnding(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(mock.patch.stopall)
        mock.patch.object(QMessageBox, "information", return_value=None).start()
        self.paths = []
        for n in ("one", "two"):
            d = F.open()
            d.new_page().insert_text((72, 72), n)
            p = os.path.join(self.tmp, n + ".pdf")
            d.save(p)
            self.paths.append(p)
        APP.processEvents()
        for x in main_window.windows():          # left by an earlier test
            for v in x._views():
                v.dirty = False
            x._close_confirmed = True
            x.close()
        APP.processEvents()
        self.backups = os.path.join(self.tmp, "backups")
        os.makedirs(self.backups)
        self.settings = paths.settings()
        old = {k: self.settings.value(k) for k in ("backup_dir", "restore_session",
                                                   "session_files")}
        self.addCleanup(lambda: [self.settings.setValue(k, v) if v is not None
                                 else self.settings.remove(k) for k, v in old.items()])
        self.settings.setValue("backup_dir", self.backups)
        self.settings.setValue("restore_session", "true")
        self.settings.setValue("session_files", "[]")

    def window(self):
        w = MainWindow()
        self.addCleanup(lambda: (setattr(w, "_close_confirmed", True), w.close()))
        for p in self.paths:
            w.open_file(p)
        for v in w._views():
            self.addCleanup(lambda v=v: setattr(v, "dirty", False))
        return w

    def test_open_files_are_remembered_and_changes_backed_up(self):
        w = self.window()
        w2 = w.detach_tab(1)                      # a pulled-out window counts too
        w2.view()._create(0, {"kind": "rect", "props": {"stroke": "#d00000", "width": 2},
                              "rect": F.Rect(40, 40, 80, 80)})
        self.assertTrue(w2.view().dirty)
        w.autosave.set_minutes(5)
        w2.autosave.set_minutes(5)
        w.windows_ending(None)
        self.assertEqual(len(w._views()) + len(w2._views()), 2)
        self.settings.sync()
        files = json.loads(self.settings.value("session_files"))
        self.assertEqual(sorted(os.path.basename(f) for f in files), ["one.pdf", "two.pdf"])
        left = autosave.leftovers()
        self.assertEqual([os.path.basename(o) for _p, o, _t in left], ["two.pdf"])

        # the next start reopens both (and offers the backup of the unsaved one)
        again = MainWindow()
        self.addCleanup(lambda: (setattr(again, "_close_confirmed", True), again.close()))
        again.restore_session()
        self.assertEqual(sorted(os.path.basename(v.path) for v in again._views()),
                         ["one.pdf", "two.pdf"])

    def test_no_backups_when_they_are_turned_off(self):
        w = self.window()
        w.view()._create(0, {"kind": "rect", "props": {"stroke": "#d00000", "width": 2},
                             "rect": F.Rect(40, 40, 80, 80)})
        w.autosave.set_minutes(0)
        w.windows_ending(None)
        self.assertEqual(autosave.leftovers(), [])
        self.assertEqual(len(json.loads(self.settings.value("session_files"))), 2)

    def test_the_app_listens_for_windows_ending_it(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(root, "kanzonas", "__main__.py"), encoding="utf-8") as f:
            self.assertIn("app.commitDataRequest.connect(win.windows_ending)", f.read())


if __name__ == "__main__":
    unittest.main()
