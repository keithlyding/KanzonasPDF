"""Closing KanzonasPDF with several documents open asks once: Save all / Don't save / Cancel
when some have unsaved changes, "Close them all and exit?" when none has (a preference turns
that one off). One document keeps the usual per-document question.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_exit_confirm
"""
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

from kanzonas import main_window  # noqa: E402
from kanzonas.main_window import MainWindow  # noqa: E402


def rect(v):
    v._create(0, {"kind": "rect", "props": {"stroke": "#d00000", "width": 2},
                  "rect": F.Rect(40, 40, 80, 80)})


class ExitConfirm(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["HOME"] = self.tmp
        self.addCleanup(mock.patch.stopall)
        mock.patch.object(QMessageBox, "information", return_value=None).start()
        self.pump()
        for x in main_window.windows():
            for v in x._views():
                v.dirty = False
            x._close_confirmed = True
            x.close()
        self.pump()

    def pump(self, n=10):
        for _ in range(n):
            APP.processEvents()

    def window(self, n):
        w = MainWindow()
        self.addCleanup(w.deleteLater)
        for i in range(n):
            d = F.open()
            d.new_page().insert_text((72, 72), f"doc {i}")
            p = os.path.join(self.tmp, f"d{i}.pdf")
            d.save(p)
            w.open_file(p)
        w.settings.setValue("confirm_exit", "true")
        for v in w._views():
            self.addCleanup(lambda v=v: setattr(v, "dirty", False))
        return w

    def test_all_saved_asks_once_and_cancel_keeps_it_open(self):
        w = self.window(3)
        ask = mock.patch.object(w, "_ask_exit", return_value="cancel").start()
        w.close()
        self.pump()
        self.assertEqual(ask.call_args[0], (3, []))
        self.assertIn(w, main_window.windows())
        ask.return_value = "discard"
        w.close()
        self.pump()
        self.assertNotIn(w, main_window.windows())

    def test_preference_off_closes_saved_documents_without_asking(self):
        w = self.window(2)
        w.settings.setValue("confirm_exit", "false")
        ask = mock.patch.object(w, "_ask_exit").start()
        w.close()
        self.pump()
        ask.assert_not_called()
        self.assertNotIn(w, main_window.windows())

    def test_unsaved_documents_are_listed_and_save_all_saves_them(self):
        w = self.window(3)
        rect(w.tabs.widget(0))
        rect(w.tabs.widget(2))
        ask = mock.patch.object(w, "_ask_exit", return_value="save").start()
        saved = []
        mock.patch.object(w, "save", side_effect=lambda: saved.append(w.view().path) or True).start()
        w.close()
        self.pump()
        self.assertEqual(ask.call_args[0], (3, ["d0.pdf", "d2.pdf"]))
        self.assertEqual([os.path.basename(p) for p in saved], ["d0.pdf", "d2.pdf"])
        self.assertNotIn(w, main_window.windows())

    def test_a_failed_save_keeps_everything_open(self):
        w = self.window(2)
        rect(w.tabs.widget(1))
        mock.patch.object(w, "_ask_exit", return_value="save").start()
        mock.patch.object(w, "save", return_value=False).start()
        w.close()
        self.pump()
        self.assertIn(w, main_window.windows())

    def test_dont_save_closes_without_saving(self):
        w = self.window(2)
        rect(w.tabs.widget(0))
        mock.patch.object(w, "_ask_exit", return_value="discard").start()
        save = mock.patch.object(w, "save").start()
        w.close()
        self.pump()
        save.assert_not_called()
        self.assertNotIn(w, main_window.windows())

    def test_one_document_keeps_the_per_document_question(self):
        w = self.window(1)
        rect(w.tabs.widget(0))
        ask = mock.patch.object(w, "_ask_exit").start()
        q = mock.patch.object(QMessageBox, "question", return_value=QMessageBox.Discard).start()
        w.close()
        self.pump()
        ask.assert_not_called()
        self.assertEqual(q.call_count, 1)
        self.assertNotIn(w, main_window.windows())


if __name__ == "__main__":
    unittest.main()
