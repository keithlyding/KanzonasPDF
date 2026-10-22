"""Delete pages works on the pages selected in the page list, and with the Delete key there;
Enhance thin lines draws hairlines at least a pixel wide on screen only.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_page_delete_thin_lines
"""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np  # noqa: E402
import pymupdf  # noqa: E402
from PySide6.QtCore import QEvent, Qt  # noqa: E402
from PySide6.QtGui import QKeyEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas.document_view import DocumentView  # noqa: E402
from kanzonas.main_window import MainWindow  # noqa: E402


def numbered(path, n=5):
    d = pymupdf.open()
    for i in range(n):
        d.new_page().insert_text((72, 72), f"Page {i + 1}", fontsize=20)
    d.save(path)
    return path


def labels(doc):
    return [p.get_text().strip() for p in doc]


class DeletePages(unittest.TestCase):
    def setUp(self):
        self.w = MainWindow()
        self.w.show()
        self.w.open_file(numbered(os.path.join(tempfile.mkdtemp(), "five.pdf")))
        APP.processEvents()
        self.addCleanup(lambda: (setattr(self.w, "_close_confirmed", True), self.w.close()))
        self.w.lock_btn.setChecked(False)               # page order unlocked
        self.v = self.w.view()

    def select(self, *rows):
        t = self.w.thumbs
        t.clearSelection()
        for r in rows:
            t.item(r).setSelected(True)

    def test_the_selected_pages_are_deleted_after_asking(self):
        self.select(1, 3)
        asked = []
        with mock.patch.object(QMessageBox, "question",
                               lambda *a, **k: (asked.append(a[2]), QMessageBox.Yes)[1]):
            self.w.a_del_page.trigger()
        self.assertEqual(asked, ["Delete these 2 pages (2, 4)?"])
        self.assertEqual(labels(self.v.doc), ["Page 1", "Page 3", "Page 5"])
        self.v.undo()                                    # one step brings them all back
        self.assertEqual(labels(self.v.doc), [f"Page {i}" for i in range(1, 6)])

    def test_delete_key_in_the_page_list(self):
        self.select(0, 4)
        self.w.thumbs.setFocus()
        with mock.patch.object(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes):
            QApplication.sendEvent(self.w.thumbs, QKeyEvent(QEvent.KeyPress, Qt.Key_Delete,
                                                            Qt.NoModifier))
        self.assertEqual(labels(self.v.doc), ["Page 2", "Page 3", "Page 4"])

    def test_answering_no_keeps_them(self):
        self.select(2)
        with mock.patch.object(QMessageBox, "question", lambda *a, **k: QMessageBox.No):
            self.w.a_del_page.trigger()
        self.assertEqual(self.v.doc.page_count, 5)

    def test_a_locked_page_list_asks_to_unlock_first(self):
        self.w.lock_btn.setChecked(True)
        self.select(1)
        with mock.patch.object(QMessageBox, "question", lambda *a, **k: QMessageBox.No):
            self.w.a_del_page.trigger()              # "unlock?" answered No
        self.assertEqual(self.v.doc.page_count, 5)

    def test_every_page_selected_is_refused(self):
        self.select(0, 1, 2, 3, 4)
        said = []
        with mock.patch.object(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes), \
                mock.patch.object(QMessageBox, "information", lambda *a, **k: said.append(a[2])):
            self.w.a_del_page.trigger()
        self.assertEqual(self.v.doc.page_count, 5)
        self.assertEqual(said, ["A PDF must keep at least one page."])


class ThinLines(unittest.TestCase):
    def setUp(self):
        d = pymupdf.open()
        p = d.new_page(width=2592, height=1728)                  # a 36x24 sheet
        p.draw_line((100, 300), (2000, 300), color=(0, 0, 0), width=0.1)
        self.path = os.path.join(tempfile.mkdtemp(), "hairline.pdf")
        d.save(self.path)
        self.addCleanup(lambda: setattr(DocumentView, "thin_lines", True))

    def darkest_on_screen(self, on):
        DocumentView.thin_lines = on
        v = DocumentView(self.path)
        self.addCleanup(v.close_doc)
        v.set_zoom(0.68)
        w = v.pages[0]
        w._render()
        img = w._pix.toImage()
        y = int(300 * 0.68 * w.devicePixelRatioF())
        return min(img.pixelColor(x, yy).lightness() for x in range(200, 1200, 7)
                   for yy in range(y - 3, y + 4))

    def test_hairlines_stay_dark_on_screen_and_true_elsewhere(self):
        self.assertGreater(self.darkest_on_screen(False), 170)     # pale gray at true width
        self.assertLess(self.darkest_on_screen(True), 120)         # dark with the option on
        # the engine's setting is reset after drawing: an export keeps the true width
        pm = pymupdf.open(self.path)[0].get_pixmap(matrix=pymupdf.Matrix(0.68, 0.68),
                                                   clip=pymupdf.Rect(400, 295, 600, 305),
                                                   colorspace=pymupdf.csGRAY)
        g = np.frombuffer(pm.samples, np.uint8)
        self.assertGreater(int(g.min()), 170)

    def test_the_option_redraws_and_is_remembered(self):
        w = MainWindow()
        w.show()
        w.open_file(self.path)
        APP.processEvents()
        self.addCleanup(lambda: (setattr(w, "_close_confirmed", True), w.close()))
        self.assertTrue(w.a_thin_lines.isChecked())                # on by default
        v = w.view()
        v.pages[0]._render()
        self.assertIn(0, v._pix_pages)
        w.a_thin_lines.trigger()
        self.assertFalse(DocumentView.thin_lines)
        self.assertNotIn(0, v._pix_pages)                          # drawn again
        self.assertEqual(w.settings.value("thin_lines"), "false")
        w.a_thin_lines.trigger()
        self.assertTrue(DocumentView.thin_lines)


if __name__ == "__main__":
    unittest.main()
