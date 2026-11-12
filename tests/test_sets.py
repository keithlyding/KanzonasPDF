"""Sets (1.12, the owner, 11 Nov, from the Bluebeam comparison: Revu's Sets): several PDFs
browsed as one document without combining them. The set file (paths relative to it, so a set
moves with its folder), the Sets panel (files and their sheets, by sheet number and title
from the title block on drawing-size pages), opening a sheet, Next / Previous sheet across
the files (a file the set opened and left unchanged closed when it goes on), and Combine to
one PDF.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_sets
"""
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import doc_sets  # noqa: E402
from kanzonas.sets_panel import ROLE, SetsPanel  # noqa: E402


def pump(n=6):
    for _ in range(n):
        APP.processEvents()


def sheet_pdf(path, sheets, size=(2592, 1728)):
    """A PDF of drawing sheets, each with a title block (SHEET NO / SHEET TITLE)."""
    d = pymupdf.open()
    for number, title in sheets:
        p = d.new_page(width=size[0], height=size[1])
        p.insert_text((100, 100), "PLAN " + number, fontsize=30)
        p.insert_text((size[0] - 400, size[1] - 160), "SHEET TITLE: " + title, fontsize=12)
        p.insert_text((size[0] - 400, size[1] - 100), "SHEET NO: " + number, fontsize=24)
    d.save(path)
    return path


def letter_pdf(path, n):
    d = pymupdf.open()
    for i in range(n):
        d.new_page().insert_text((72, 72), "Specifications page %d A1" % (i + 1))
    d.save(path)
    return path


class SetFile(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp()
        doc_sets.forget()

    def test_saved_relative_and_moved_with_its_folder(self):
        sub = os.path.join(self.folder, "dwg")
        os.makedirs(sub)
        a = sheet_pdf(os.path.join(sub, "A-101.pdf"), [("A-101", "FLOOR PLAN")])
        b = letter_pdf(os.path.join(self.folder, "specs.pdf"), 2)
        outside = letter_pdf(os.path.join(tempfile.mkdtemp(), "far.pdf"), 1)
        path = os.path.join(self.folder, "job.kzset")
        ds = doc_sets.DocSet("Job", [a, b, outside], path)
        ds.save()
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["kind"], doc_sets.KIND)
        self.assertEqual([f["path"] for f in data["files"]],
                         ["dwg/A-101.pdf", "specs.pdf", outside])
        moved = os.path.join(tempfile.mkdtemp(), "moved")
        shutil.copytree(self.folder, moved)
        again = doc_sets.DocSet.load(os.path.join(moved, "job.kzset"))
        self.assertEqual(again.name, "Job")
        self.assertEqual(again.files, [os.path.join(moved, "dwg", "A-101.pdf"),
                                       os.path.join(moved, "specs.pdf"), outside])

    def test_not_a_set(self):
        path = os.path.join(self.folder, "x.kzset")
        with open(path, "w") as f:
            f.write("{\"files\": 3}")
        with self.assertRaises(doc_sets.SetError):
            doc_sets.DocSet.load(path)

    def test_add_remove_move_and_step_across_files(self):
        a = letter_pdf(os.path.join(self.folder, "a.pdf"), 2)
        b = letter_pdf(os.path.join(self.folder, "b.pdf"), 3)
        missing = os.path.join(self.folder, "gone.pdf")
        ds = doc_sets.DocSet("S", [a])
        self.assertEqual(ds.add([b, a, missing]), 2)
        self.assertEqual(ds.step(a, 1, 1), (b, 0))
        self.assertEqual(ds.step(b, 0, -1), (a, 1))
        self.assertEqual(ds.step(b, 2, 1), None)            # (the missing file: skipped)
        self.assertEqual(ds.step(a, 0, -1), None)
        self.assertTrue(ds.move(b, -1))
        self.assertEqual(ds.files[:2], [b, a])
        self.assertFalse(ds.move(b, -1))
        ds.remove(missing)
        self.assertEqual(ds.files, [b, a])

    def test_sheet_numbers_read_on_drawing_pages_only(self):
        a = sheet_pdf(os.path.join(self.folder, "a.pdf"), [("A-101", "FLOOR PLAN"),
                                                             ("A-201", "ELEVATIONS")])
        s = letter_pdf(os.path.join(self.folder, "s.pdf"), 1)
        self.assertEqual(doc_sets.file_info(a)["big"], {0, 1})
        self.assertEqual(doc_sets.file_info(s)["big"], set())
        self.assertIs(doc_sets.sheet(a, 1), False)          # (not read yet)
        doc_sets.read_sheets(a, [0, 1])
        self.assertEqual(doc_sets.sheet(a, 1), {"number": "A-201", "title": "ELEVATIONS"})


class Panel(unittest.TestCase):
    def setUp(self):
        doc_sets.forget()
        self.folder = tempfile.mkdtemp()
        self.a = sheet_pdf(os.path.join(self.folder, "arch.pdf"),
                           [("A-101", "FLOOR PLAN"), ("A-201", "ELEVATIONS")])
        self.s = letter_pdf(os.path.join(self.folder, "specs.pdf"), 2)
        self.path = os.path.join(self.folder, "job.kzset")

    def texts(self, panel):
        out = []
        for k in range(panel.tree.topLevelItemCount()):
            top = panel.tree.topLevelItem(k)
            out.append((top.text(0), [top.child(c).text(0) for c in range(top.childCount())
                                      if not top.child(c).isHidden()]))
        return out

    def test_files_and_their_sheets(self):
        panel = SetsPanel()
        self.addCleanup(panel.deleteLater)
        ds = panel.new_set(self.path, [self.a, self.s, os.path.join(self.folder, "gone.pdf")])
        self.assertTrue(os.path.isfile(self.path))
        for _ in range(50):
            if not panel._timer.isActive():
                break
            pump()
        self.assertEqual(self.texts(panel), [
            ("arch.pdf", ["A-101  FLOOR PLAN", "A-201  ELEVATIONS"]),
            ("specs.pdf", ["Page 1", "Page 2"]),
            ("gone.pdf (not found)", [])])
        panel.find.setText("elev")
        self.assertEqual(self.texts(panel)[0], ("arch.pdf", ["A-201  ELEVATIONS"]))
        panel.find.setText("")
        # a click opens the sheet
        got = []
        panel.openRequested.connect(lambda f, i: got.append((f, i)))
        top = panel.tree.topLevelItem(0)
        panel._clicked(top.child(1))
        self.assertEqual(got, [(self.a, 1)])
        # changes are saved at once
        panel.move_file(self.s, -1)
        self.assertEqual(doc_sets.DocSet.load(self.path).files[0], self.s)
        panel.rename("Tower")
        self.assertEqual(doc_sets.DocSet.load(self.path).name, "Tower")
        panel.remove_file(os.path.join(self.folder, "gone.pdf"))
        self.assertEqual(len(doc_sets.DocSet.load(self.path).files), 2)
        self.assertIs(ds, panel.docset)
        panel.set_docset(None)
        self.assertFalse(panel.tree.isVisibleTo(panel))


class InTheWindow(unittest.TestCase):
    def setUp(self):
        doc_sets.forget()
        self.folder = tempfile.mkdtemp()
        self.a = sheet_pdf(os.path.join(self.folder, "arch.pdf"),
                           [("A-101", "FLOOR PLAN"), ("A-201", "ELEVATIONS")])
        self.s = sheet_pdf(os.path.join(self.folder, "struct.pdf"), [("S-101", "FOUNDATION")])
        self.path = os.path.join(self.folder, "job.kzset")
        doc_sets.DocSet("Job", [self.a, self.s], self.path).save()
        from kanzonas.main_window import MainWindow
        self.w = MainWindow()
        self.w.resize(1300, 850)
        self.w.show()
        pump()
        self.addCleanup(self.close)

    def close(self):
        self.w._close_confirmed = True
        for v in self.w._views():
            v.dirty = False
        self.w.close()
        pump()

    def paths(self):
        return [os.path.normcase(v.path) for v in self.w._views()]

    def test_open_browse_across_files_and_combine(self):
        w = self.w
        w.open_file(self.path)                  # (a .kzset: opened as a set)
        pump()
        self.assertIsNotNone(w.sets.docset)
        self.assertTrue(w.dock.isVisible())
        self.assertEqual(self.paths(), [os.path.normcase(self.a)])      # its first sheet
        w._set_step(1)
        self.assertEqual(w.view().current_page(), 1)
        w._set_step(1)                          # on to the next file; the first, unchanged,
        pump()                                  # is closed
        self.assertEqual(self.paths(), [os.path.normcase(self.s)])
        self.assertEqual(w.view().current_page(), 0)
        cur = w.sets.tree.currentItem()
        self.assertEqual(cur.data(0, ROLE), (self.s, 0))
        w._set_step(1)                          # (the end: stays)
        self.assertEqual(self.paths(), [os.path.normcase(self.s)])
        # a file changed stays open when the set goes on
        w.view().dirty = True
        w._set_step(-1)
        pump()
        self.assertEqual(sorted(self.paths()), sorted([os.path.normcase(self.a),
                                                       os.path.normcase(self.s)]))
        self.assertEqual(w.view().current_page(), 1)
        for v in w._views():
            v.dirty = False
        # Combine to one PDF: Combine files with the set's files
        seen = {}

        class Dlg:
            def __init__(self, parent, start, files, **kw):
                seen["files"] = files
                self.result_path = None
                self.ocr_pages = []

            def exec(self):
                return 0
        with mock.patch("kanzonas.combine.CombineDialog", Dlg):
            w.sets.m_combine.trigger()
        self.assertEqual(seen["files"], [self.a, self.s])


if __name__ == "__main__":
    unittest.main()
