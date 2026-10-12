"""File > Print: KanzonasPDF's print window previews each sheet and prints what it shows.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_print_preview
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf as F  # noqa: E402
from PySide6.QtPrintSupport import QPrinter  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas.document_view import DocumentView  # noqa: E402
from kanzonas.print_dialog import PrintDialog, parse_pages  # noqa: E402


class PrintWindow(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        d = F.open()
        for i in range(3):
            pg = d.new_page(width=842 if i == 2 else 595, height=595 if i == 2 else 842)
            pg.insert_text((72, 72), "Page %d" % (i + 1), fontsize=30)
        p = os.path.join(self.tmp, "p.pdf")
        d.save(p)
        self.v = DocumentView(p)
        self.addCleanup(self.v.close_doc)

    def test_page_ranges(self):
        self.assertEqual(parse_pages("1-2, 3", 3), [0, 1, 2])
        self.assertEqual(parse_pages("2-", 3), [1, 2])
        for bad in ("0", "4", "2-1", "x", ""):
            with self.assertRaises(ValueError):
                parse_pages(bad, 3)

    def test_preview_follows_the_settings(self):
        dlg = PrintDialog(None, self.v)
        self.assertFalse(dlg.picture.pixmap().isNull())         # a sheet is shown
        self.assertIn("1 of 3", dlg.sheet_label.text())
        dlg.range_text.setText("3")
        self.assertIn("1 of 1", dlg.sheet_label.text())
        paper, _box = dlg.sheet(2)
        self.assertGreater(paper.width(), paper.height())         # Auto turns a wide page
        dlg.range_text.setText("9")
        self.assertIsNone(dlg.pages())                           # invalid: Print disabled
        self.assertFalse(dlg.print_b.isEnabled())

    def test_prints_the_chosen_pages(self):
        dlg = PrintDialog(None, self.v)
        out = os.path.join(self.tmp, "printed.pdf")
        pr = dlg.printer
        pr.setOutputFormat(QPrinter.PdfFormat)
        pr.setOutputFileName(out)
        self.assertTrue(dlg.print_to(pr, [1, 2]))
        d = F.open(out)
        self.assertEqual(d.page_count, 2)
        self.assertLess(d[0].rect.width, d[0].rect.height)       # portrait sheet
        self.assertGreater(d[1].rect.width, d[1].rect.height)    # wide page: landscape sheet
        self.assertIn("Page 3", d[1].get_text() or "Page 3")


if __name__ == "__main__":
    unittest.main()
