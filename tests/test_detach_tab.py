"""A document tab can be moved to its own window (drag it out, right-click > Move to new
window, View > Move tab to new window) and back: the document keeps its unsaved changes and
undo history, its signals follow it to the new window, a pulled-out window closes with its
last tab, and closing the main window closes the others and remembers every open file.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_detach_tab
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
from PySide6.QtCore import Qt, QMimeData, QPointF  # noqa: E402
from PySide6.QtGui import QDropEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import main_window  # noqa: E402
from kanzonas.main_window import MainWindow, TAB_MIME  # noqa: E402


class DetachTab(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["HOME"] = self.tmp
        self.addCleanup(mock.patch.stopall)
        mock.patch.object(QMessageBox, "information", return_value=None).start()
        self.paths = []
        for n in ("one", "two"):
            d = F.open()
            d.new_page().insert_text((72, 72), n)
            p = os.path.join(self.tmp, n + ".pdf")
            d.save(p)
            self.paths.append(p)

        # windows left by an earlier test (deleteLater'd, not yet gone) must not count
        self.pump()
        for x in list(main_window.WINDOWS):
            for v in x._views():
                v.dirty = False
            x._close_confirmed = True
            x.close()
        self.pump()
        main_window.WINDOWS.clear()

    def window(self):
        w = MainWindow()
        self.addCleanup(w.deleteLater)
        for p in self.paths:
            w.open_file(p)
        for v in w._views():
            self.addCleanup(lambda v=v: setattr(v, "dirty", False))
        return w

    def pump(self, n=10):
        for _ in range(n):
            APP.processEvents()

    def test_detach_keeps_edits_and_rewires_signals(self):
        w = self.window()
        v = w.tabs.widget(1)
        v._create(0, {"kind": "rect", "props": {"stroke": "#d00000", "width": 2},
                      "rect": F.Rect(40, 40, 80, 80)})
        self.assertTrue(v.dirty)
        w2 = w.detach_tab(1)
        self.pump()
        self.assertIsNotNone(w2)
        self.assertFalse(w2.primary)
        self.assertIn(w2, main_window.WINDOWS)
        self.assertEqual([w.tabs.count(), w2.tabs.count()], [1, 1])
        self.assertIs(w2.view(), v)
        self.assertTrue(v.dirty)                              # not reopened
        v.undo()                                              # history came along
        self.assertEqual(len(list(v.doc[0].annots())), 0)
        v.statusMessage.emit("moved here")
        self.assertEqual(w2.statusBar().currentMessage(), "moved here")
        self.assertNotEqual(w.statusBar().currentMessage(), "moved here")
        self.assertTrue(w2.a_detach.isEnabled())
        self.assertIn(w.a_detach, w.view_menu.actions())
        w2._close_confirmed = True
        w2.close()
        self.pump()

    def test_drop_on_the_main_windows_tabs_moves_it_back_and_closes_the_empty_window(self):
        w = self.window()
        w2 = w.detach_tab(0)
        self.pump()
        v = w2.view()
        mime = QMimeData()
        mime.setData(TAB_MIME, f"{id(w2)}:0".encode("ascii"))
        bar = w.tabs.tabBar()
        ev = QDropEvent(QPointF(5, 5), Qt.MoveAction, mime, Qt.LeftButton, Qt.NoModifier)
        bar.dropEvent(ev)          # (a synthetic drop isn't routed by QApplication::notify)
        self.assertTrue(ev.isAccepted())
        self.pump()
        self.assertEqual(w.tabs.count(), 2)
        self.assertIs(w.tabs.widget(0), v)                    # dropped on the first tab
        self.assertIs(w.view(), v)
        self.assertNotIn(w2, main_window.WINDOWS)             # closed itself, nothing left
        v.statusMessage.emit("back")
        self.assertEqual(w.statusBar().currentMessage(), "back")

    def test_closing_a_pulled_out_windows_last_tab_closes_it(self):
        w = self.window()
        w2 = w.detach_tab(1)
        self.pump()
        w2.close_tab(0)
        self.pump()
        self.assertNotIn(w2, main_window.WINDOWS)
        self.assertEqual(w.tabs.count(), 1)
        self.assertIn(w, main_window.WINDOWS)

    def test_closing_the_main_window_closes_the_others_and_remembers_all_files(self):
        w = self.window()
        w2 = w.detach_tab(1)
        self.pump()
        v2 = w2.view()
        v2._create(0, {"kind": "rect", "props": {"stroke": "#d00000", "width": 2},
                       "rect": F.Rect(40, 40, 80, 80)})
        asked = mock.patch.object(QMessageBox, "question",
                                  return_value=QMessageBox.Discard).start()
        w.close()
        self.pump()
        self.assertEqual(asked.call_count, 1)                 # the one dirty document, once
        self.assertNotIn(w2, main_window.WINDOWS)
        self.assertNotIn(w, main_window.WINDOWS)
        files = json.loads(w.settings.value("session_files"))
        self.assertEqual(sorted(os.path.basename(f) for f in files), ["one.pdf", "two.pdf"])

    def test_cancel_keeps_every_window_open(self):
        w = self.window()
        w2 = w.detach_tab(1)
        self.pump()
        w2.view()._create(0, {"kind": "rect", "props": {"stroke": "#d00000", "width": 2},
                              "rect": F.Rect(40, 40, 80, 80)})
        mock.patch.object(QMessageBox, "question", return_value=QMessageBox.Cancel).start()
        w.close()
        self.pump()
        self.assertIn(w, main_window.WINDOWS)
        self.assertIn(w2, main_window.WINDOWS)
        self.assertTrue(w2.isVisible())
        w2.view().dirty = False
        w2.close()
        self.pump()


if __name__ == "__main__":
    unittest.main()
