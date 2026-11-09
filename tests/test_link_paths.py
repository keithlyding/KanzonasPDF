"""Links to other files open the file when it's there (the owner: a drawing index's link said
"The linked file isn't there: C:\\Users\\176526\\OneDrive - ...\\drawings\\Drawings\\14854940.pdf"
while that drawing was in that folder).

- The path is read as the PDF writes it: percent-encoded by MuPDF, with a stray control
  character or space at its end, as /C/Users/... or /C:/Users/... (a PDF's and a file:
  address's way of writing a drive), or followed by #nameddest=Sheet1, which opens the file
  at that named destination (before: the name was taken as part of the file name).
- A file that isn't where the link says (an index made on another person's computer, folders
  moved or synced elsewhere) is found from the document's folder, as the link's last folders
  and file name; the status bar says which file opened.
- When it isn't found, the message says KanzonasPDF looked, and on Windows names the other
  person's user folder the link points into.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_link_paths -t .
"""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import link_paths  # noqa: E402
from kanzonas.document_view import DocumentView  # noqa: E402

THEIRS = ("C:\\Users\\176526\\OneDrive - Sonoco Products Company\\Chestnut Hill Capital CAA "
          "Document Review - General\\2026\\2 PC\\Palletizer\\Palletizer FAT\\Drawings and "
          "Programs\\drawings\\Drawings\\14854940.pdf")


def pdf_string(s):
    return "(" + s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") + ")"


def index_pdf(path, actions):
    """A one-page index with a link per action (a PDF action dictionary's source)."""
    d = pymupdf.open()
    pg = d.new_page()
    xs = []
    for i, a in enumerate(actions):
        x = d.get_new_xref()
        xs.append(x)
        d.update_object(x, "<</Type/Annot/Subtype/Link/Rect[72 %d 300 %d]/Border[0 0 0]/A%s>>"
                        % (700 - 30 * i, 715 - 30 * i, a))
    d.xref_set_key(pg.xref, "Annots", "[" + " ".join("%d 0 R" % x for x in xs) + "]")
    d.save(path)


def drawing(path, pages=1, dest=None):
    """A drawing PDF; dest: a named destination going to its last page."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    d = pymupdf.open()
    for _ in range(pages):
        d.new_page()
    if dest:
        names = d.get_new_xref()
        d.update_object(names, "<</Dests<</Names[(%s)[%d 0 R/Fit]]>>>>"
                        % (dest, d[pages - 1].xref))
        d.xref_set_key(d.pdf_catalog(), "Names", "%d 0 R" % names)
    d.save(path)


class Paths(unittest.TestCase):
    def test_split_link(self):
        enc = "C%3A%5CUsers%5Cme%5CA%20B%5Cx%23y%20100%25.pdf"
        self.assertEqual(link_paths.split_link(enc, windows=False),
                         ("C:\\Users\\me\\A B\\x#y 100%.pdf", None))
        self.assertEqual(link_paths.split_link("x.pdf#nameddest=Sheet%202", windows=False),
                         ("x.pdf", "Sheet 2"))
        self.assertEqual(link_paths.split_link("x.pdf#page=3", windows=False), ("x.pdf", None))
        self.assertEqual(link_paths.split_link("x.pdf%0D", windows=False)[0], "x.pdf")
        self.assertEqual(link_paths.split_link(" x.pdf\x00 ", windows=False)[0], "x.pdf")
        # a plain path (a file: address already read) is kept as it is, '#' and '%' included
        self.assertEqual(link_paths.split_link("/a/x#1 5%.pdf", encoded=False, windows=False),
                         ("/a/x#1 5%.pdf", None))

    def test_drive_written_the_pdf_way(self):
        self.assertEqual(link_paths.clean("/C/Users/me/x.pdf", windows=True), "C:/Users/me/x.pdf")
        self.assertEqual(link_paths.clean("/C:/Users/me/x.pdf", windows=True), "C:/Users/me/x.pdf")
        self.assertEqual(link_paths.clean("/Cad/x.pdf", windows=True), "/Cad/x.pdf")
        self.assertEqual(link_paths.clean("/C/x.pdf", windows=False), "/C/x.pdf")

    def test_other_user(self):
        self.assertEqual(link_paths.other_user(THEIRS, "C:\\Users\\104233"), "176526")
        self.assertIsNone(link_paths.other_user(THEIRS, "C:\\Users\\176526"))
        self.assertIsNone(link_paths.other_user("D:\\Jobs\\x.pdf", "C:\\Users\\104233"))
        self.assertIsNone(link_paths.other_user("C:\\Users\\Public\\x.pdf", "C:\\Users\\me"))

    def test_there_asks_the_folder_when_the_file_details_cannot_be_read(self):
        folder = tempfile.mkdtemp()
        path = os.path.join(folder, "14854940.pdf")
        open(path, "wb").close()
        with mock.patch("os.path.exists", return_value=False):
            self.assertTrue(link_paths.there(path))
            self.assertFalse(link_paths.there(os.path.join(folder, "other.pdf")))


class FindMoved(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.fat = os.path.join(self.root, "Palletizer FAT", "Drawings and Programs")
        self.target = os.path.join(self.fat, "drawings", "Drawings", "14854940.pdf")
        drawing(self.target)

    def test_from_the_index_folder_and_above_it(self):
        for at in (os.path.join(self.fat, "drawings", "Drawings"),
                   os.path.join(self.fat, "drawings"), self.fat,
                   os.path.join(self.fat, "drawings", "Index")):
            self.assertEqual(link_paths.find_moved(THEIRS, os.path.join(at, "index.pdf")),
                             os.path.normpath(self.target), at)

    def test_never_by_the_file_name_alone_above_the_index(self):
        other = os.path.join(self.root, "elsewhere", "index.pdf")
        lone = os.path.join(self.root, "14854940.pdf")
        drawing(lone)
        self.assertIsNone(link_paths.find_moved("C:\\Jobs\\Other\\14854940.pdf", other))
        self.assertEqual(link_paths.find_moved("C:\\Jobs\\Other\\14854940.pdf", lone),
                         os.path.normpath(lone))       # in the document's own folder: yes

    def test_nothing_there(self):
        self.assertIsNone(link_paths.find_moved(
            "C:\\x\\Drawings\\99999999.pdf", os.path.join(self.fat, "index.pdf")))


class Follow(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.fat = os.path.join(self.root, "Drawings and Programs")
        self.target = os.path.join(self.fat, "drawings", "Drawings", "14854940.pdf")
        drawing(self.target, pages=3, dest="Sheet3")
        self.index = os.path.join(self.fat, "drawings", "Index.pdf")

    def follow(self, actions):
        index_pdf(self.index, actions)
        v = DocumentView(self.index)
        self.addCleanup(v.close_doc)
        opened, said, status = [], [], []
        v.openFileRequested.connect(lambda p, pg: opened.append((p, pg)))
        v.statusMessage.connect(status.append)
        with mock.patch.object(QMessageBox, "information",
                               lambda *a, **k: said.append(a[2])):
            for link in v.doc[0].get_links():
                v.follow_link(link)
        return opened, said, status

    def test_a_link_made_on_another_computer_opens_the_drawing(self):
        opened, said, status = self.follow([
            "<</S/GoToR/F%s/D[0/Fit]>>" % pdf_string(THEIRS),
            "<</S/GoToR/F%s/D[0/Fit]>>" % pdf_string(THEIRS + "\r"),
            "<</S/GoToR/F%s/D[0/Fit]>>" % pdf_string(
                "/C/Users/176526/x/drawings/Drawings/14854940.pdf")])
        self.assertEqual(said, [])
        self.assertEqual(opened, [(os.path.normpath(self.target), 0)] * 3)
        self.assertIn(os.path.normpath(self.target), status[0])

    def test_relative_link_with_a_stray_character(self):
        opened, said, _ = self.follow(["<</S/GoToR/F%s/D[1/Fit]>>"
                                       % pdf_string("Drawings\\14854940.pdf\r".replace(
                                           "\\", os.sep))])
        self.assertEqual((opened, said), ([(os.path.normpath(self.target), 1)], []))

    def test_named_destination_opens_at_its_page(self):
        opened, said, _ = self.follow(["<</S/GoToR/F%s/D(Sheet3)>>"
                                       % pdf_string(os.path.join("Drawings", "14854940.pdf"))])
        self.assertEqual((opened, said), ([(os.path.normpath(self.target), 2)], []))

    def test_not_found_says_it_looked(self):
        opened, said, _ = self.follow(["<</S/GoToR/F%s/D[0/Fit]>>"
                                       % pdf_string(THEIRS.replace("14854940", "99999999"))])
        self.assertEqual(opened, [])
        self.assertEqual(len(said), 1)
        self.assertIn("99999999.pdf", said[0])
        self.assertIn("looked for it from this document's folder", said[0])

    @unittest.skipUnless(sys.platform == "win32", "Windows user folders")
    def test_not_found_names_the_other_users_folder(self):
        with mock.patch.dict(os.environ, {"USERPROFILE": "C:\\Users\\104233"}):
            _, said, _ = self.follow(["<</S/GoToR/F%s/D[0/Fit]>>"
                                      % pdf_string(THEIRS.replace("14854940", "99999999"))])
        self.assertIn("176526", said[0].split("\n\n")[1])


if __name__ == "__main__":
    unittest.main()
