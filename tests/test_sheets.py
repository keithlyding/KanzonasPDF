"""Sheet callout links: numbers and titles read from title blocks, callouts found, links made
to pages and to PDFs in the same folder, bookmarks, no duplicates, undo; and file links with
spaces (percent-encoded by MuPDF) resolve."""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tests"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox  # noqa: E402

APP = QApplication.instance() or QApplication([])

import cad_samples  # noqa: E402
from kanzonas import sheets  # noqa: E402
from kanzonas.main_window import MainWindow  # noqa: E402
from kanzonas.sheets_ui import SheetLinksDialog  # noqa: E402


def sheet_set(folder):
    """Cover with an index, A-101 with callouts, A501 (no dash); S-201 exists as a file."""
    d = pymupdf.open()
    cover = d.new_page(width=2592, height=1728)
    cover.insert_text((300, 300), "SHEET INDEX", fontsize=14)
    cover.insert_text((300, 330), "A-101   FIRST FLOOR PLAN", fontsize=10)
    cover.insert_text((300, 350), "A-501   DETAILS", fontsize=10)
    cover.insert_text((300, 370), "S-201   FRAMING PLAN", fontsize=10)
    cad_samples._title_block(cover, "COVER SHEET", "A", "G-001")
    a101 = d.new_page(width=2592, height=1728)
    cad_samples._title_block(a101, "FIRST FLOOR PLAN", "B", "A-101")
    a101.insert_text((900, 700), "3/A-501", fontsize=12)
    a101.insert_text((900, 760), "SEE A501 FOR TYP. DETAILS", fontsize=10)
    a101.insert_text((900, 820), "REFER TO S-201", fontsize=10)
    a101.insert_text((900, 880), "ASTM C150 CEMENT", fontsize=10)
    a101.insert_text((900, 940), "DETAIL 2/A-101", fontsize=10)          # self reference
    a501 = d.new_page(width=2592, height=1728)
    cad_samples._title_block(a501, "DETAILS", "A", "A501")
    other = pymupdf.open()
    other.new_page().insert_text((72, 72), "framing")
    other.save(os.path.join(folder, "S-201 Framing Plan.pdf"))
    path = os.path.join(folder, "set.pdf")
    d.save(path)
    return path


class Reading(unittest.TestCase):
    def test_numbers_and_titles_from_title_blocks(self):
        path = sheet_set(tempfile.mkdtemp())
        infos = sheets.scan(pymupdf.open(path))
        self.assertEqual([i["number"] for i in infos], ["G-001", "A-101", "A501"])
        self.assertEqual([i["title"] for i in infos], ["COVER SHEET", "FIRST FLOOR PLAN", "DETAILS"])

    def test_tokens(self):
        self.assertEqual(sheets.token("3/A-501"), "A501")
        self.assertEqual(sheets.token("(A-501)"), "A501")
        self.assertEqual(sheets.token("a1.01,"), "A1.01")
        self.assertEqual(sheets.token("LS-1.01"), "LS1.01")
        self.assertIsNone(sheets.token("PLAN"))
        self.assertIsNone(sheets.token("12345"))
        self.assertIsNone(sheets.token("W12x26"))

    def test_largest_number_in_the_block_when_no_caption(self):
        d = pymupdf.open()
        p = d.new_page(width=2592, height=1728)
        p.insert_text((2300, 1650), "A-201", fontsize=18)
        p.insert_text((2300, 1600), "REV 3", fontsize=8)
        p.insert_text((200, 200), "E-5", fontsize=30)      # big, but not in the title block
        self.assertEqual(sheets.sheet_info(p)["number"], "A-201")
        q = d.new_page()
        q.insert_text((72, 72), "nothing here")
        self.assertIsNone(sheets.sheet_info(q))


class Planning(unittest.TestCase):
    def test_plan_links_pages_and_sibling_files_not_junk(self):
        folder = tempfile.mkdtemp()
        doc = pymupdf.open(sheet_set(folder))
        pl = sheets.plan(doc, folder=folder)
        targets = sorted((i, t) for i, _r, t in pl["links"])
        self.assertEqual(targets, [(0, ("file", "S-201 Framing Plan.pdf")), (0, ("page", 1)),
                                   (0, ("page", 2)), (1, ("file", "S-201 Framing Plan.pdf")),
                                   (1, ("page", 2)), (1, ("page", 2))])
        self.assertEqual(pl["external"], {"S201": "S-201 Framing Plan.pdf"})
        self.assertEqual(set(pl["missing"]), {"C150"})

    def test_edited_numbers_drive_the_plan(self):
        folder = tempfile.mkdtemp()
        doc = pymupdf.open(sheet_set(folder))
        pl = sheets.plan(doc, {0: "", 1: "A-101", 2: "A-501"}, folder=None)
        self.assertNotIn(0, pl["pages"])
        # the cover's index lines still point at A-101 and A-501; A-101's two callouts at A-501
        self.assertEqual(sorted(t for _i, _r, t in pl["links"]),
                         [("page", 1), ("page", 2), ("page", 2), ("page", 2)])

    def test_apply_makes_links_and_bookmarks_once(self):
        folder = tempfile.mkdtemp()
        doc = pymupdf.open(sheet_set(folder))
        pl = sheets.plan(doc, folder=folder)
        self.assertEqual(sheets.apply(doc, pl, bookmarks=True), (6, 3))
        self.assertEqual([t[1] for t in doc.get_toc()],
                         ["G-001  COVER SHEET", "A-101  FIRST FLOOR PLAN", "A501  DETAILS"])
        kinds = sorted((ln["kind"], ln.get("page", -1)) for ln in doc[1].get_links())
        self.assertEqual(kinds, [(pymupdf.LINK_GOTO, 2), (pymupdf.LINK_GOTO, 2),
                                 (pymupdf.LINK_GOTOR, 0)])
        self.assertEqual(sheets.apply(doc, sheets.plan(doc, folder=folder)), (0, 0))


class Command(unittest.TestCase):
    def test_dialog_and_undo(self):
        folder = tempfile.mkdtemp()
        path = sheet_set(folder)
        w = MainWindow()
        w.show()
        w.open_file(path)
        APP.processEvents()
        self.addCleanup(lambda: (setattr(w, "_close_confirmed", True), w.close()))
        v = w.view()
        dlg_holder = {}
        real_init = SheetLinksDialog.__init__

        def init(self, *a, **k):
            real_init(self, *a, **k)
            dlg_holder["d"] = self
        with mock.patch.object(SheetLinksDialog, "__init__", init), \
                mock.patch.object(SheetLinksDialog, "exec",
                                  lambda self: (self._accept(), QDialog.Accepted)[1]):
            w.link_sheet_callouts()
        dlg = dlg_holder["d"]
        self.assertEqual(dlg.table.item(1, 1).text(), "A-101")
        self.assertIn("3 sheet(s) found; 6 callout(s)", dlg.summary.text())
        self.assertEqual(len(v.doc[1].get_links()), 3)
        self.assertEqual(len(v.doc.get_toc()), 3)
        self.assertTrue(v.dirty)
        v.undo()
        self.assertEqual(len(v.doc[1].get_links()), 0)
        self.assertEqual(v.doc.get_toc(), [])

    def test_file_link_with_spaces_opens_the_file(self):
        folder = tempfile.mkdtemp()
        path = sheet_set(folder)
        doc = pymupdf.open(path)
        sheets.apply(doc, sheets.plan(doc, folder=folder))
        doc.saveIncr()
        w = MainWindow()
        w.show()
        w.open_file(path)
        APP.processEvents()
        self.addCleanup(lambda: (setattr(w, "_close_confirmed", True), w.close()))
        v = w.view()
        link = next(ln for ln in v.doc[1].get_links() if ln["kind"] == pymupdf.LINK_GOTOR)
        self.assertIn("%20", link["file"])                  # what MuPDF hands back
        opened = []
        v.openFileRequested.connect(lambda p, pg: opened.append(p))
        with mock.patch.object(QMessageBox, "information", lambda *a, **k: self.fail(a[2])), \
                mock.patch.object(QMessageBox, "critical", lambda *a, **k: self.fail(a[2])):
            v.follow_link(link)
            APP.processEvents()
        self.assertEqual(opened, [os.path.join(folder, "S-201 Framing Plan.pdf")])
        self.assertEqual(w.tabs.count(), 2, "the linked PDF opened in a new tab")


if __name__ == "__main__":
    unittest.main()
