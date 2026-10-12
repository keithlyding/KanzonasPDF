"""File > Print preview shows every page, and printing draws the chosen pages.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_print_preview
"""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf as F  # noqa: E402
from PySide6.QtPrintSupport import QPrinter, QPrintPreviewDialog, QPrintPreviewWidget  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])


class PrintPreview(unittest.TestCase):
    def test_preview_and_print(self):
        tmp = tempfile.mkdtemp()
        os.environ["HOME"] = tmp
        from kanzonas.main_window import MainWindow
        d = F.open()
        for i in range(3):
            d.new_page().insert_text((72, 72), "Page %d" % (i + 1), fontsize=30)
        p = os.path.join(tmp, "p.pdf")
        d.save(p)
        w = MainWindow()
        w.show()
        w.open_file(p)
        APP.processEvents()
        seen = {}

        def fake_exec(dlg):
            pw = dlg.findChild(QPrintPreviewWidget)
            pw.updatePreview()
            APP.processEvents()
            seen["pages"] = pw.pageCount()
            return 0
        with mock.patch.object(QPrintPreviewDialog, "exec", fake_exec):
            w.a_print_preview.trigger()
        self.assertEqual(seen.get("pages"), 3)
        out = os.path.join(tmp, "printed.pdf")
        pr = QPrinter(QPrinter.HighResolution)
        pr.setOutputFormat(QPrinter.PdfFormat)
        pr.setOutputFileName(out)
        pr.setPrintRange(QPrinter.PageRange)
        pr.setFromTo(2, 3)
        self.assertIs(w._paint_pages(w.view(), pr, w._print_pages(w.view(), pr)), True)
        self.assertEqual(F.open(out).page_count, 2)
        w.close_tab(w.tabs.currentIndex())
        w.deleteLater()


if __name__ == "__main__":
    unittest.main()
