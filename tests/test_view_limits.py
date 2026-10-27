"""Smaller things a tester found:
- a long document at a high zoom: the pages stacked must fit in Qt's largest widget, or they
  overlap and the last ones can't be reached;
- an edit that fails and is rolled back leaves the document as unchanged as it was;
- a save whose last step fails leaves no temporary copy next to the file;
- the zoom box ignores "nan" and "inf" and takes a decimal comma;
- the manual's Find says "Not found" and stays where you were.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_view_limits
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

from kanzonas import document_view  # noqa: E402
from kanzonas.document_view import DocumentView  # noqa: E402

QT_MAX = 16_777_215


def pdf(path, n):
    d = F.open()
    for i in range(n):
        d.new_page().insert_text((72, 72), f"P{i + 1}", fontsize=24)
    d.save(path)
    d.close()
    return path


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(mock.patch.stopall)
        mock.patch.object(QMessageBox, "information", return_value=None).start()
        self.warned = []
        mock.patch.object(QMessageBox, "warning",
                          side_effect=lambda *a, **k: self.warned.append(a[1])).start()
        self.views = []
        self.addCleanup(lambda: [v.close_doc() for v in self.views])

    def view(self, n=2, name="d.pdf"):
        v = DocumentView(pdf(os.path.join(self.tmp, name), n))
        self.views.append(v)
        return v


class LongDocumentZoom(Base):
    def test_all_pages_fit_at_the_highest_zoom(self):
        v = self.view(500)
        v.resize(1200, 800)
        v.show()
        self.addCleanup(v.hide)
        for _ in range(5):
            APP.processEvents()             # it opens at Fit width
        v.set_zoom(64)
        APP.processEvents()
        self.assertLess(v.zoom, 64)
        self.assertLess(v.widget().height(), QT_MAX)
        v.goto_page(499)
        self.assertEqual(v.current_page(), 499)
        v.goto_page(400)
        self.assertEqual(v.current_page(), 400)
        self.assertTrue(all(v.pages[i + 1].y() >= v.pages[i].y() + v.pages[i].height()
                            for i in range(499)))

    def test_a_short_document_still_reaches_6400_percent(self):
        v = self.view(3)
        v.set_zoom(64)
        self.assertAlmostEqual(v.zoom, 64)

    def test_pages_added_at_a_high_zoom_lower_it(self):
        v = self.view(200)
        v.set_zoom(64)
        data = v.pages_bytes(range(200))
        v.paste_pages(data, 200)
        self.assertEqual(v.page_count(), 400)
        self.assertLess(sum(w.height() for w in v.pages), QT_MAX)


class FailedEdits(Base):
    def test_a_failed_edit_leaves_the_document_unchanged(self):
        v = self.view()
        bad = os.path.join(self.tmp, "damaged.pdf")
        with open(bad, "wb") as f:
            f.write(b"%PDF-1.7\nnot a pdf")
        v.insert_files([bad], -1)
        self.assertEqual(self.warned, ["Edit failed"])
        self.assertEqual(v.page_count(), 2)
        self.assertFalse(v.dirty)
        self.assertEqual(v._undo, [])

    def test_a_failed_edit_keeps_earlier_unsaved_changes_marked(self):
        v = self.view()
        v.insert_blank(1)
        v.modify(lambda: 1 / 0)
        self.assertTrue(v.dirty)
        self.assertEqual(v.page_count(), 3)

    def test_a_failed_save_leaves_no_temporary_copy(self):
        v = self.view()
        v.insert_blank(1)
        real = os.replace

        def locked(a, b):
            if os.path.abspath(b) == v.path:
                raise PermissionError(13, "in use by another process", b)
            return real(a, b)
        with mock.patch.object(document_view.os, "replace", locked):
            with self.assertRaises(PermissionError):
                v.save()
        self.assertEqual(os.listdir(self.tmp), ["d.pdf"])
        self.assertTrue(v.dirty)


class ZoomBox(unittest.TestCase):
    def test_zoom_box_text(self):
        from kanzonas.main_window import MainWindow
        mock.patch.object(QMessageBox, "information", return_value=None).start()
        self.addCleanup(mock.patch.stopall)
        tmp = tempfile.mkdtemp()
        w = MainWindow()
        self.addCleanup(w.deleteLater)
        w.open_file(pdf(os.path.join(tmp, "z.pdf"), 1))
        v = w.view()
        self.addCleanup(lambda: (setattr(v, "dirty", False), setattr(w, "_close_confirmed",
                                                                     True), w.close()))
        v.set_zoom(1.0)
        for text in ("nan", "inf", "-inf", "nan%", "0"):
            w.zoom_box.setEditText(text)
            w._zoom_from_box()
            self.assertAlmostEqual(v.zoom, 1.0, msg=text)
        w.zoom_box.setEditText("25,5%")
        w._zoom_from_box()
        self.assertAlmostEqual(v.zoom, 0.255)
        w.zoom_box.setEditText("150")
        w._zoom_from_box()
        self.assertAlmostEqual(v.zoom, 1.5)


class ManualFind(unittest.TestCase):
    def test_a_word_not_in_the_manual(self):
        from kanzonas.manual import ManualDialog
        dlg = ManualDialog()
        self.addCleanup(dlg.deleteLater)
        dlg.show()
        dlg.find.setText("Combine files")
        self.assertTrue(dlg.find_next())
        bar = dlg.text.verticalScrollBar()
        top, pos = bar.value(), dlg.text.textCursor().position()
        self.assertGreater(pos, 0)
        dlg.find.setText("xyzzyplugh")
        self.assertFalse(dlg.find_next())
        self.assertEqual(dlg.not_found.text(), "Not found")
        self.assertEqual(dlg.text.textCursor().position(), pos)
        self.assertEqual(bar.value(), top)
        dlg.find.setText("Combine")
        self.assertEqual(dlg.not_found.text(), "")


if __name__ == "__main__":
    unittest.main()
