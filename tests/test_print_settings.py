"""The Print window's paper size (on the window itself, not only behind Page setup) and each
document's last print settings, remembered (the owner, 23 Nov 2026: "paper size needs to be
included in the dialog without having to click on page setup. And the document needs to
remember the last printed settings").

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_print_settings
"""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402
from PySide6.QtGui import QPageSize  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

import tests  # noqa: E402,F401  (settings in a scratch folder)
from kanzonas import print_dialog  # noqa: E402
from kanzonas.document_view import DocumentView  # noqa: E402
from kanzonas.print_dialog import PrintDialog  # noqa: E402


class PrintSettings(unittest.TestCase):
    def view(self, name):
        d = pymupdf.open()
        for _ in range(4):
            d.new_page(width=1728, height=1152)         # 24 x 16 in
        path = os.path.join(tempfile.mkdtemp(), name)
        d.save(path)
        v = DocumentView(path)
        self.addCleanup(v.close_doc)
        return v

    def paper(self, dlg):
        return dlg.paper.currentData()

    def test_the_paper_is_on_the_window(self):
        v = self.view("a.pdf")
        dlg = PrintDialog(None, v)
        self.addCleanup(dlg.deleteLater)
        names = [dlg.paper.itemText(k) for k in range(dlg.paper.count())]
        self.assertGreater(len(names), 3)
        k = next(k for k in range(dlg.paper.count())
                 if dlg.paper.itemData(k).id() == QPageSize.ArchD)
        dlg.paper.setCurrentIndex(k)
        # the printer and the preview's sheet follow
        self.assertEqual(dlg.printer.pageLayout().pageSize().id(), QPageSize.ArchD)
        sheet, _box = dlg.sheet(0)
        self.assertAlmostEqual(max(sheet.width(), sheet.height()), 36 * 72, delta=1)
        self.assertAlmostEqual(min(sheet.width(), sheet.height()), 24 * 72, delta=1)

    def test_each_document_remembers_its_last_print(self):
        v = self.view("plans.pdf")
        dlg = PrintDialog(None, v)
        self.addCleanup(dlg.deleteLater)
        k = next(k for k in range(dlg.paper.count())
                 if dlg.paper.itemData(k).id() == QPageSize.ArchD)
        dlg.paper.setCurrentIndex(k)
        dlg.copies.setValue(3)
        dlg.range_text.setText("2-3")
        dlg.size.setCurrentIndex(1)
        dlg.marks.setChecked(True)
        with mock.patch.object(PrintDialog, "print_to", return_value=True):
            dlg._accept()                               # (printed: it's remembered)
        again = PrintDialog(None, v)
        self.addCleanup(again.deleteLater)
        self.assertEqual(self.paper(again).id(), QPageSize.ArchD)
        self.assertEqual(again.copies.value(), 3)
        self.assertTrue(again.some.isChecked())
        self.assertEqual(again.range_text.text(), "2-3")
        self.assertEqual(again.size.currentIndex(), 1)
        self.assertTrue(again.marks.isChecked())
        # another document has its own (none yet: the defaults)
        other = PrintDialog(None, self.view("other.pdf"))
        self.addCleanup(other.deleteLater)
        self.assertEqual(other.copies.value(), 1)
        self.assertTrue(other.all_pages.isChecked())
        self.assertNotEqual(self.paper(other).id(), QPageSize.ArchD)

    def test_not_printed_not_remembered(self):
        v = self.view("c.pdf")
        dlg = PrintDialog(None, v)
        self.addCleanup(dlg.deleteLater)
        dlg.copies.setValue(7)
        dlg.reject()
        self.assertEqual(print_dialog.stored_state(v), {})

    def test_a_range_past_the_end_or_a_gone_printer_is_left_alone(self):
        v = self.view("d.pdf")
        print_dialog.store_state(v, {"printer": "A printer long gone", "pages": "some",
                                     "range": "", "copies": 2, "orientation": 99})
        dlg = PrintDialog(None, v)
        self.addCleanup(dlg.deleteLater)
        self.assertEqual(dlg.copies.value(), 2)
        self.assertTrue(dlg.all_pages.isChecked())
        self.assertEqual(dlg.orientation.currentIndex(), 0)


if __name__ == "__main__":
    unittest.main()
