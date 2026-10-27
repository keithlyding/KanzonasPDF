"""Dragging thumbnails in the page list: several pages dragged at once are one undo step, and
a drag that's refused (a document protected against changes) puts the list back in the
document's order.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_page_list_drag
"""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf as F  # noqa: E402
from PySide6.QtCore import QModelIndex, QPersistentModelIndex  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas.main_window import MainWindow  # noqa: E402


class PageListDrag(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(mock.patch.stopall)
        mock.patch.object(QMessageBox, "information", return_value=QMessageBox.Ok).start()
        mock.patch.object(QMessageBox, "question", return_value=QMessageBox.Yes).start()
        self.w = MainWindow()
        self.w.show()
        self.addCleanup(self.close_window)

    def close_window(self):
        for v in self.w._views():
            v.dirty = False
        self.w._close_confirmed = True
        self.w.close()
        self.w.deleteLater()
        self.pump()

    def pump(self, n=30):
        for _ in range(n):
            APP.processEvents()

    def open(self, n, **save):
        path = os.path.join(self.tmp, "d.pdf")
        d = F.open()
        for i in range(n):
            d.new_page().insert_text((72, 72), f"p{i + 1}", fontsize=24)
        d.save(path, **save)
        d.close()
        self.w.open_file(path)
        self.pump()
        self.w.lock_btn.setChecked(False)
        return self.w.view()

    def drop(self, rows, r):
        """What QListView's drop does for an internal move: one moveRow per dragged row."""
        m = self.w.thumbs.model()
        for p in sorted([QPersistentModelIndex(m.index(x, 0)) for x in rows],
                        key=lambda p: p.row()):
            if r != p.row() and r != p.row() + 1:
                m.moveRow(QModelIndex(), p.row(), QModelIndex(), r)
            r = p.row() + 1
        self.pump()

    def labels(self, v):
        return [p.get_text().split()[0] for p in v.doc]

    def listed(self):
        return [self.w.thumbs.item(i).text() for i in range(self.w.thumbs.count())]

    def test_dragging_several_pages_is_one_undo_step(self):
        v = self.open(8)
        self.drop([1, 2], 6)                    # p2, p3 dropped before p7
        self.assertEqual(self.labels(v), ["p1", "p4", "p5", "p6", "p2", "p3", "p7", "p8"])
        self.assertEqual(len(v._undo), 1)
        self.assertEqual(self.listed(), [str(i) for i in range(1, 9)])
        self.drop([7, 0], 3)
        self.assertEqual(self.labels(v), ["p4", "p5", "p1", "p8", "p6", "p2", "p3", "p7"])
        v.undo()
        self.assertEqual(self.labels(v), ["p1", "p4", "p5", "p6", "p2", "p3", "p7", "p8"])

    def test_refused_drag_puts_the_list_back(self):
        v = self.open(4, encryption=F.PDF_ENCRYPT_AES_256, owner_pw="o",
                      permissions=F.PDF_PERM_PRINT)
        self.drop([0], 3)
        self.assertEqual(self.labels(v), ["p1", "p2", "p3", "p4"])
        self.assertEqual(self.listed(), ["1", "2", "3", "4"])
        self.assertFalse(v.dirty)


if __name__ == "__main__":
    unittest.main()
