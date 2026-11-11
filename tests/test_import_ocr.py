"""File > Create PDF from images and Combine files: "Make the pictures searchable (recognize
text, OCR)" (the owner, 11 Nov: OCR when making a PDF from pictures). The pages that came
from pictures are recognized once the new PDF is open, and the file is saved with their text
in it; PDF pages put in are left alone; the choice is remembered.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_import_ocr
"""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog, QFileDialog  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import combine as C  # noqa: E402
from kanzonas import paths  # noqa: E402
from kanzonas.main_window import MainWindow  # noqa: E402

LINES = ["KANZONAS CONSTRUCTION", "Change Order 14 for the east wing framing",
         "Please find attached the revised framing plan."]


def picture_of_text(folder, name="letter.png"):
    """A photo-like picture of a typed letter (no text in it, only pixels)."""
    d = pymupdf.open()
    p = d.new_page()
    for k, t in enumerate(LINES):
        p.insert_text((72, 100 + 30 * k), t, fontsize=14, fontname="tiro")
    path = os.path.join(folder, name)
    p.get_pixmap(dpi=150, colorspace=pymupdf.csGRAY).save(path)
    return path


def pdf_with_text(folder):
    d = pymupdf.open()
    d.new_page().insert_text((72, 100), "Already typed page", fontsize=12)
    path = os.path.join(folder, "typed.pdf")
    d.save(path)
    return path


class Combine(unittest.TestCase):
    def test_pages_from_pictures_are_listed(self):
        folder = tempfile.mkdtemp()
        pic = picture_of_text(folder)
        pdf = pdf_with_text(folder)
        out = os.path.join(folder, "out.pdf")
        pictures = []
        n = C.combine([pdf, pic, pdf, pic], out, pictures=pictures)
        self.assertEqual(n, 4)
        self.assertEqual(pictures, [1, 3])
        self.assertEqual(C.combine([pic], os.path.join(folder, "o2.pdf")), 1)  # (as before)


class InTheWindow(unittest.TestCase):
    def setUp(self):
        s = paths.settings()
        self.before = s.value("import_ocr")
        self.addCleanup(self.restore)
        self.w = MainWindow()
        self.w.resize(1200, 800)
        self.w.show()
        APP.processEvents()
        self.addCleanup(self.close)

    def restore(self):
        s = paths.settings()
        if self.before is None:
            s.remove("import_ocr")
        else:
            s.setValue("import_ocr", self.before)

    def close(self):
        self.w._close_confirmed = True
        self.w.close()
        APP.processEvents()

    def make(self, files, out, ocr, images=True):
        """Run Create PDF from images (or Combine files) with these files, OCR ticked or not."""
        def run(dlg):
            dlg.ocr.setChecked(ocr)
            dlg._ok()
            return dlg.result() == QDialog.Accepted
        with mock.patch.object(QFileDialog, "getOpenFileNames", return_value=(files, "")), \
                mock.patch.object(QFileDialog, "getSaveFileName", return_value=(out, "")), \
                mock.patch.object(C.CombineDialog, "exec", run):
            if images:
                self.w.pdf_from_images()
            else:
                with mock.patch.object(C.CombineDialog, "__init__", self.combine_with(files)):
                    self.w.combine_files()
        APP.processEvents()

    @staticmethod
    def combine_with(files):
        own = C.CombineDialog.__init__

        def init(dlg, parent, start_dir="", first=None, images=False):
            own(dlg, parent, start_dir, files, images)
        return init

    def test_picture_made_searchable_and_saved(self):
        folder = tempfile.mkdtemp()
        out = os.path.join(folder, "letter.pdf")
        self.make([picture_of_text(folder)], out, ocr=True)
        v = self.w.view()
        self.assertFalse(v.dirty)                       # (saved with its text)
        text = pymupdf.open(out)[0].get_text()
        self.assertIn("KANZONAS", text)
        self.assertIn("framing", text)
        self.assertEqual(paths.settings().value("import_ocr"), "true")   # remembered
        dlg = C.CombineDialog(self.w, folder, [], images=True)
        self.assertTrue(dlg.ocr.isChecked())
        dlg.deleteLater()

    def test_not_ticked_leaves_the_picture_as_it_was(self):
        folder = tempfile.mkdtemp()
        out = os.path.join(folder, "letter.pdf")
        with mock.patch("kanzonas.document_view.DocumentView.run_ocr") as run:
            self.make([picture_of_text(folder)], out, ocr=False)
        run.assert_not_called()
        self.assertEqual(pymupdf.open(out)[0].get_text().strip(), "")
        self.assertEqual(paths.settings().value("import_ocr"), "false")

    def test_combine_recognizes_only_the_pictures(self):
        folder = tempfile.mkdtemp()
        out = os.path.join(folder, "combined.pdf")
        with mock.patch("kanzonas.document_view.DocumentView.run_ocr") as run:
            self.make([pdf_with_text(folder), picture_of_text(folder)], out, ocr=True,
                      images=False)
        run.assert_called_once()
        self.assertEqual(run.call_args[0][0], [1])


if __name__ == "__main__":
    unittest.main()
