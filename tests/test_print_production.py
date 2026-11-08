"""Print production (1.8, the Print tab): Set page boxes, Show page boxes, Fix hairlines,
Check for printing, and crop marks in the Print window.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_print_production
"""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402
from PySide6.QtPrintSupport import QPrinter  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import i18n, print_production as pp  # noqa: E402
from kanzonas.document_view import DocumentView  # noqa: E402
from kanzonas.print_dialog import PrintDialog  # noqa: E402

P = pymupdf.Point


def raw_page(doc, content, width=612, height=792):
    """A page drawn by exactly these instructions."""
    p = doc.new_page(width=width, height=height)
    x = doc.get_new_xref()
    doc.update_object(x, "<<>>")
    doc.update_stream(x, content)
    p.set_contents(x)
    return p


def saved(doc):
    path = os.path.join(tempfile.mkdtemp(), "sheet.pdf")
    doc.save(path)
    return path


def widths(page):
    return sorted(round(d.get("width") or 0, 3) for d in page.get_drawings())


class Hairlines(unittest.TestCase):
    def sheet(self):
        d = pymupdf.open()
        p = raw_page(d, b"q 0 w 0 0 1 RG 50 700 m 500 700 l S Q\n"           # zero width
                        b"q 0.5 0 0 0.5 0 0 cm 0.4 w 100 1000 m 900 1000 l S Q\n"  # 0.2 pt
                        b"q 1 w 50 650 m 500 650 l S Q\n"                       # fine
                        b"q 0.1 w 50 600 m 500 600 l 500 500 l W S Q\n")        # clips
        # a drawing group with a 0.3 pt line, placed at half its size: 0.15 pt as printed
        src = pymupdf.open()
        sp = src.new_page(width=400, height=400)
        sp.draw_line((10, 10), (390, 10), width=0.3)
        sp.draw_line((10, 50), (390, 50), width=2)
        p.show_pdf_page(pymupdf.Rect(50, 200, 250, 400), src, 0)
        return d

    def test_finds_page_and_group_lines_and_widens_only_those(self):
        d = self.sheet()
        p = d[0]
        f = pp.find_hairlines(p, 0.25)
        # (the line that sets a clip in its own instructions isn't taken: widening it inside
        # q ... Q would end its clip for what follows)
        self.assertEqual(sorted(round(w, 3) for _d, w in f["page"]), [0.0, 0.2])
        self.assertEqual([round(w, 3) for v in f["forms"].values() for _d, w in v["thin"]],
                         [0.15])
        n = pp.fix_hairlines(p, 0.25, 0.3)
        self.assertEqual(n, 3)
        got = widths(p)
        self.assertEqual(got.count(0.3), 3)
        self.assertIn(1.0, got)                 # (the 1 pt line as it was)
        self.assertIn(0.1, got)                 # (the line clipped in its own object stays)

    def test_the_view_does_it_as_one_undo_step(self):
        v = DocumentView(saved(self.sheet()))
        self.addCleanup(v.close_doc)
        self.addCleanup(lambda: setattr(v, "dirty", False))
        before = widths(v.doc[0])
        self.assertEqual(v.fix_hairlines([0], 0.25, 0.5), 3)
        self.assertEqual(widths(v.doc[0]).count(0.5), 3)
        self.assertEqual(v.fix_hairlines([0], 0.25, 0.5), 0)     # (nothing left to widen)
        v.undo()
        self.assertEqual(widths(v.doc[0]), before)

    def test_a_protected_file_says_so(self):
        d = self.sheet()
        path = os.path.join(tempfile.mkdtemp(), "locked.pdf")
        d.save(path, encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="o", user_pw="",
               permissions=pymupdf.PDF_PERM_PRINT)
        v = DocumentView(path)
        self.addCleanup(v.close_doc)
        with mock.patch.object(QMessageBox, "information", lambda *a, **k: QMessageBox.Ok):
            self.assertIsNone(v.fix_hairlines([0], 0.25, 0.5))


class Boxes(unittest.TestCase):
    def view(self, rotation=0):
        d = pymupdf.open()
        p = d.new_page(width=612, height=792)
        p.set_mediabox(pymupdf.Rect(0, 0, 660, 840))     # (a sheet with room for bleed)
        p.set_rotation(rotation)
        v = DocumentView(saved(d))
        self.addCleanup(v.close_doc)
        self.addCleanup(lambda: setattr(v, "dirty", False))
        return v

    def test_set_from_margins_and_undo(self):
        v = self.view()
        v.set_page_boxes([0], {"trimbox": (24, 24, 24, 24), "bleedbox": (15, 15, 15, 15)})
        page = v.doc[0]
        self.assertEqual(pp.page_box(page, "trimbox"), pymupdf.Rect(24, 24, 636, 816))
        self.assertEqual(pp.page_box(page, "bleedbox"), pymupdf.Rect(15, 15, 645, 825))
        self.assertIsNone(pp.page_box(page, "artbox"))
        self.assertEqual([w for w, _r in v.page_boxes_shown(0)], ["trimbox", "bleedbox"])
        del page
        v.set_page_boxes([0], {"bleedbox": None})
        self.assertIsNone(pp.page_box(v.doc[0], "bleedbox"))
        v.undo()
        v.undo()
        self.assertIsNone(pp.page_box(v.doc[0], "trimbox"))

    def test_margins_are_as_the_page_is_shown(self):
        v = self.view(rotation=90)
        v.set_page_boxes([0], {"trimbox": (10, 0, 0, 0)})        # (10 pt off the shown left)
        page = v.doc[0]
        shown = page.trimbox * page.rotation_matrix
        self.assertAlmostEqual(shown.x0, page.rect.x0 + 10, places=3)
        self.assertAlmostEqual(shown.x1, page.rect.x1, places=3)

    def test_a_box_that_wont_fit_changes_nothing(self):
        v = self.view()
        rev = v.revision
        with self.assertRaises(ValueError):
            v.set_page_boxes([0], {"trimbox": (-30, 0, 0, 0)})    # (past the media box)
        with self.assertRaises(ValueError) as e:
            v.set_page_boxes([0], {"trimbox": (10, 10, 10, 10), "bleedbox": (20, 20, 20, 20)})
        self.assertIn("bleed", str(e.exception))
        self.assertEqual(v.revision, rev)
        self.assertIsNone(pp.page_box(v.doc[0], "trimbox"))


class Check(unittest.TestCase):
    def test_what_it_finds(self):
        d = pymupdf.open()
        p = d.new_page(width=612, height=792)
        p.insert_text((72, 72), "Notes", fontname="helv")          # (not embedded)
        pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 60, 40), False)
        pix.set_rect(pix.irect, (200, 30, 30))
        p.insert_image(pymupdf.Rect(72, 100, 372, 300), pixmap=pix)   # (60 px over 300 pt)
        p.draw_line((72, 400), (500, 400), width=0.1)
        q = d.new_page(width=1224, height=792)                    # (another sheet size)
        q.set_mediabox(pymupdf.Rect(0, 0, 1240, 808))
        q.set_trimbox(pymupdf.Rect(8, 8, 1232, 800))
        q.set_bleedbox(pymupdf.Rect(2, 2, 1238, 806))
        found = pp.check(d)
        kinds = {k for k, _i, _t in found}
        self.assertEqual(kinds, {"fonts", "pictures", "rgb", "hairlines", "boxes", "sizes"})
        self.assertEqual({i for k, i, _t in found if k == "boxes"}, {0})   # (page 2 has both)
        low = [t for k, _i, t in found if k == "pictures"][0]
        self.assertIn("14 pixels per inch", low)                  # 60 px / (300/72) in

    def test_one_page_and_one_line_are_singular(self):
        d = pymupdf.open()
        for _ in range(2):
            d.new_page(width=612, height=792)
        p = d.new_page(width=1224, height=792)
        p.draw_line((72, 400), (500, 400), width=0.1)               # (one hairline)
        found = pp.check(d)
        sizes = sorted(t for k, _i, t in found if k == "sizes")
        self.assertTrue(sizes[0].startswith("1 page of 1224 × 792 pt"), sizes)
        self.assertTrue(sizes[0].endswith(": page 3"), sizes)
        self.assertTrue(sizes[1].startswith("2 pages of 612 × 792 pt"), sizes)
        self.assertTrue(sizes[1].endswith(": pages 1, 2"), sizes)
        thin = [t for k, _i, t in found if k == "hairlines"]
        self.assertEqual(thin, ["1 line thinner than 0.25 pt (Fix hairlines widens it)"])
        es = i18n.load("es")                                        # (and in Spanish)
        self.assertEqual(es["{n} page of {w} × {h} pt ({inch}): page {pages}"],
                         "{n} página de {w} × {h} pt ({inch}): página {pages}")

    def test_the_boxes_shown_have_their_own_names(self):
        # (View > Show page boxes: "Trim" alone is the CAD command, a verb in Spanish)
        es = i18n.load("es")
        self.assertEqual([es[k] for k in ("Trim box", "Bleed box", "Art box")],
                         ["Recorte final", "Sangrado", "Arte"])
        self.assertEqual(es["Trim"], "Recortar")
        import inspect
        from kanzonas.page_widget import PageWidget
        src = inspect.getsource(PageWidget._paint_page_boxes)
        self.assertIn('tr("Trim box")', src)
        self.assertNotIn('tr("Trim")', src)

    def test_a_clean_page_has_nothing(self):
        d = pymupdf.open()
        p = d.new_page(width=612, height=792)
        p.set_mediabox(pymupdf.Rect(0, 0, 630, 810))
        p.set_trimbox(pymupdf.Rect(9, 9, 621, 801))
        p.set_bleedbox(pymupdf.Rect(0, 0, 630, 810))
        p.draw_line((72, 400), (500, 400), width=1)
        self.assertEqual(pp.check(d), [])


class CropMarks(unittest.TestCase):
    def test_marks_lie_outside_the_trim_corners(self):
        trim = pymupdf.Rect(100, 100, 300, 200)
        lines = pp.mark_lines(trim)
        self.assertEqual(len(lines), 8)
        for x0, y0, x1, y1 in lines:
            inside = trim.x0 < (x0 + x1) / 2 < trim.x1 and trim.y0 < (y0 + y1) / 2 < trim.y1
            self.assertFalse(inside)

    def test_the_print_window_prints_them(self):
        d = pymupdf.open()
        p = d.new_page(width=612, height=792)
        p.set_mediabox(pymupdf.Rect(0, 0, 640, 820))
        p.set_trimbox(pymupdf.Rect(14, 14, 626, 806))
        p.set_bleedbox(pymupdf.Rect(5, 5, 635, 815))
        p.draw_rect(pymupdf.Rect(0, 0, 640, 820), color=None, fill=(0.8, 0.9, 1))
        v = DocumentView(saved(d))
        self.addCleanup(v.close_doc)
        dlg = PrintDialog(None, v)
        self.addCleanup(dlg.deleteLater)
        _paper, plain = dlg.sheet(0)
        dlg.marks.setChecked(True)
        _paper, marked = dlg.sheet(0)
        self.assertLess(marked.width(), plain.width())            # (room for the marks)
        self.assertFalse(dlg.picture.pixmap().isNull())
        out = os.path.join(tempfile.mkdtemp(), "printed.pdf")
        pr = dlg.printer
        pr.setOutputFormat(QPrinter.PdfFormat)
        pr.setOutputFileName(out)
        self.assertTrue(dlg.print_to(pr, [0]))
        got = pymupdf.open(out)
        lines = [dr for dr in got[0].get_drawings()
                 if dr["items"] and dr["items"][0][0] == "l"]
        self.assertGreaterEqual(len(lines), 8)                     # (the eight marks)


if __name__ == "__main__":
    unittest.main()


class Windows(unittest.TestCase):
    """The Print tab, the Pages > Print production menu and the three windows."""
    def setUp(self):
        from kanzonas import main_window
        w = self.w = main_window.MainWindow()
        self.addCleanup(lambda: [setattr(x, "_close_confirmed", True) or x.close()
                                 for x in main_window.windows()])
        w.show()
        d = pymupdf.open()
        p = d.new_page(width=612, height=792)
        p.set_mediabox(pymupdf.Rect(0, 0, 640, 820))
        p.draw_line((72, 400), (500, 400), width=0.05)
        w.open_file(saved(d))
        APP.processEvents()
        self.v = w.view()
        self.addCleanup(lambda: setattr(self.v, "dirty", False))

    def test_tab_and_menu(self):
        r = self.w.ribbon
        tabs = [r.tabText(i) for i in range(r.count())]
        self.assertIn("Print", tabs)
        for a in (self.w.a_page_boxes, self.w.a_fix_hairlines, self.w.a_print_check):
            self.assertTrue(a.isEnabled())
        from PySide6.QtWidgets import QMenu
        menu = [a.text() for m in self.w.menuBar().findChildren(QMenu) for a in m.actions()]
        self.assertIn("Set page &boxes...", menu)

    def test_page_boxes_window(self):
        from kanzonas.print_production_ui import PageBoxesDialog
        dlg = PageBoxesDialog(self.w, self.v)
        self.addCleanup(dlg.deleteLater)
        dlg.unit.setCurrentIndex(0)                                   # points
        what, spins = dlg.rows["trimbox"]
        for s in spins:
            s.setValue(14)
        self.assertEqual(what.currentIndex(), 1)                      # (typing sets it)
        dlg._ok()
        self.assertEqual(pp.page_box(self.v.doc[0], "trimbox"), pymupdf.Rect(14, 14, 626, 806))
        # shown on the page when Show page boxes is on
        self.w.a_show_boxes.setChecked(True)
        self.w._toggle_show_boxes()
        self.addCleanup(lambda: (self.w.a_show_boxes.setChecked(False),
                                 self.w._toggle_show_boxes()))
        drawn = []
        own = self.v.pages[0]._paint_page_boxes
        with mock.patch.object(type(self.v.pages[0]), "_paint_page_boxes",
                               lambda s, p, page: (drawn.append(1), own(p, page))):
            self.v.pages[0].repaint()
        self.assertTrue(drawn)

    def test_hairlines_window(self):
        from kanzonas.print_production_ui import HairlinesDialog
        dlg = HairlinesDialog(self.w, self.v)
        self.addCleanup(dlg.deleteLater)
        dlg._ok()
        self.assertIn(0.25, widths(self.v.doc[0]))
        with mock.patch.object(QMessageBox, "information") as said:
            HairlinesDialog(self.w, self.v)._ok()                     # (none left)
        self.assertTrue(said.called)

    def test_check_window(self):
        from kanzonas.print_production_ui import CheckDialog, check_pages
        found = check_pages(self.w, self.v, [0])
        dlg = CheckDialog(self.w, self.v, found, [0])
        self.addCleanup(dlg.deleteLater)
        tops = [dlg.tree.topLevelItem(i).text(0) for i in range(dlg.tree.topLevelItemCount())]
        self.assertTrue(any(t.startswith("Hairlines") for t in tops))
        self.assertTrue(any(t.startswith("Trim and bleed") for t in tops))
