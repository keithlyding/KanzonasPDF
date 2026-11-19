"""A link to a page shows that page: on a page turned a quarter (drawing sheets often are) the
link to its top went past its bottom, and the next page filled the window. The place a link
names is read as the page is shown (MuPDF gives it turned already), and a jump never goes so
far down that the page leaves the window.

The owner, 19 Nov 2026: "when clicking a link to go to a specific page, in the document I have
open, it barely shows the bottom of it and what I see is more of the page after".

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_link_jump
"""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import main_window  # noqa: E402


def sheets(rotation, dest):
    """Three letter pages; the second turned by rotation; page 1 has a link to page 2 with
    the destination dest ("/XYZ 0 792 0": its top, as PDF writers put it)."""
    d = pymupdf.open()
    for i in range(3):
        p = d.new_page(width=612, height=792)
        if i == 1:
            p.set_rotation(rotation)
    x = d.get_new_xref()
    d.update_object(x, "<< /Type /Annot /Subtype /Link /Rect [72 600 300 620] "
                       "/Border [0 0 0] /Dest [%d 0 R %s] >>" % (d[1].xref, dest))
    d.xref_set_key(d[0].xref, "Annots", "[%d 0 R]" % x)
    path = os.path.join(tempfile.mkdtemp(), "sheets.pdf")
    d.save(path)
    return path


class Base(unittest.TestCase):
    def setUp(self):
        from tests.test_back_forward import no_dialogs
        no_dialogs(self)

    def open(self, rotation, dest="/XYZ 0 792 0", zoom=1.0):
        w = main_window.MainWindow()
        self.addCleanup(lambda: [setattr(x, "_close_confirmed", True) or x.close()
                                 for x in main_window.windows()])
        w.resize(1100, 800)
        w.show()
        w.open_file(sheets(rotation, dest))
        APP.processEvents()
        v = self.v = w.view()
        v.set_zoom(zoom)
        APP.processEvents()
        v.follow_link(v.doc[0].get_links()[0])
        APP.processEvents()
        return v

    def shown(self):
        """(top, bottom) of the window, and (top, bottom) of page 2, in the scroll area."""
        v = self.v
        top = v.verticalScrollBar().value()
        page = v.pages[1]
        y = page.y() + page.offset().y()
        return (top, top + v.viewport().height()), (y, y + v.doc[1].rect.height * v.zoom)

    def assert_page_fills_the_window(self):
        (w0, w1), (p0, p1) = self.shown()
        self.assertLessEqual(p0 - 30, w0, "the page starts below the window's top")
        self.assertGreaterEqual(p1, w1, "the page ends above the window's bottom")


class Jump(Base):
    def test_to_the_top_of_a_page(self):
        self.open(0)
        (w0, _w1), (p0, _p1) = self.shown()
        self.assertLess(abs(w0 - p0), 30)

    def test_to_the_top_of_a_sheet_turned_a_quarter(self):
        self.open(90)
        (w0, _w1), (p0, _p1) = self.shown()
        self.assertLess(abs(w0 - p0), 30)

    def test_turned_three_quarters_the_page_still_fills_the_window(self):
        # (its top as written is the bottom as shown: the page is kept in the window)
        self.open(270)
        self.assert_page_fills_the_window()

    def test_turned_upside_down_the_page_still_fills_the_window(self):
        self.open(180)
        self.assert_page_fills_the_window()

    def test_a_place_near_the_bottom_shows_as_much_of_the_page_as_fits(self):
        self.open(0, dest="/XYZ 0 20 0", zoom=2.0)
        self.assert_page_fills_the_window()

    def test_a_page_without_a_place(self):
        for dest in ("/Fit", "/XYZ null null null"):
            with self.subTest(dest=dest):
                self.open(90, dest=dest)
                (w0, _w1), (p0, _p1) = self.shown()
                self.assertLess(abs(w0 - p0), 30)


def named(rotation, where):
    """Three letter pages, the second turned; page 1 links to page 2 through the named
    destination "SHEET2" ([page 2 /XYZ 0 where 0], as drawing indexes write them)."""
    d = pymupdf.open()
    for i in range(3):
        p = d.new_page(width=612, height=792)
        if i == 1:
            p.set_rotation(rotation)
    n = d.get_new_xref()
    d.update_object(n, "<< /Names [(SHEET2) [%d 0 R /XYZ 0 %g 0]] >>" % (d[1].xref, where))
    d.xref_set_key(d.pdf_catalog(), "Names", "<< /Dests %d 0 R >>" % n)
    x = d.get_new_xref()
    d.update_object(x, "<< /Type /Annot /Subtype /Link /Rect [72 600 300 620] /Border [0 0 0] "
                       "/Dest (SHEET2) >>")
    d.xref_set_key(d[0].xref, "Annots", "[%d 0 R]" % x)
    path = os.path.join(tempfile.mkdtemp(), "named.pdf")
    d.save(path)
    return path


class NamedDestinations(Base):
    """A link through a named destination: its place comes back as the PDF writes it, from
    the page's bottom (the owner's link index: "it barely shows the bottom of it")."""

    def follow(self, rotation, where, zoom=1.0):
        with mock.patch(__name__ + ".sheets", lambda _r, _d: named(rotation, where)):
            return self.open(rotation, zoom=zoom)

    def test_to_the_top_of_the_page(self):
        for rot in (0, 90):
            with self.subTest(rotation=rot):
                self.follow(rot, 792)
                (w0, _w1), (p0, _p1) = self.shown()
                self.assertLess(abs(w0 - p0), 30)

    def test_to_the_middle_of_the_page(self):
        self.follow(0, 400, zoom=2.0)       # (the page taller than the window below its middle)
        (w0, _w1), (p0, _p1) = self.shown()
        self.assertAlmostEqual(w0 - p0, 392 * 2 - 20 - 12, delta=15)


class Bookmarks(Base):
    """A bookmark's place comes back unturned (unlike a link's): turned once, it shows the
    top of a turned sheet too."""

    def test_a_bookmark_to_the_top_of_a_turned_sheet(self):
        for rot in (0, 90):
            with self.subTest(rotation=rot):
                v = self.open(rot)
                pg = v.doc[1]
                to = pymupdf.Point(0, 0) * pg.derotation_matrix   # (as view_destination)
                v.set_toc([[1, "Sheet 2", 2, {"kind": pymupdf.LINK_GOTO, "page": 1, "to": to,
                                              "zoom": 0}]])
                v.goto_page(2)
                APP.processEvents()
                item = v.get_toc(simple=False)[0]
                v.go_to_destination(item[2] - 1, item[3]["to"])
                APP.processEvents()
                (w0, _w1), (p0, _p1) = self.shown()
                self.assertLess(abs(w0 - p0), 30)


if __name__ == "__main__":
    unittest.main()
