"""Pages that are cropped, rotated, or both: what KanzonasPDF writes into the PDF lands where
it is shown (links on markups, pasted pictures, measurement labels, Edit objects, and what
PyMuPDF itself draws: lines, pictures, links).

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_crop_rotate_coords
"""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf as F  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import annotations as A, measure, pdfcoords  # noqa: E402
from kanzonas.document_view import DocumentView  # noqa: E402

P, R = F.Point, F.Rect


def near(a, b, tol=1.5):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


class PageMatrix(unittest.TestCase):
    """pdfcoords against MuPDF's own placement of a markup, for every rotation, with a
    CropBox off the MediaBox and a MediaBox off the origin."""

    def test_matches_mupdf(self):
        for mb in ((0, 0, 600, 800), (-50, 30, 550, 830)):
            for rot in (0, 90, 180, 270):
                d = F.open()
                p = d.new_page(width=600, height=800)
                d.xref_set_key(p.xref, "MediaBox", "[%g %g %g %g]" % mb)
                d.xref_set_key(p.xref, "CropBox", "[%g %g %g %g]" % (mb[0] + 100, mb[1] + 100,
                                                                     mb[0] + 500, mb[1] + 750))
                p = d[0]
                p.set_rotation(rot)
                a = p.add_rect_annot(R(10, 20, 60, 40))
                raw = [float(v) for v in d.xref_get_key(a.xref, "Rect")[1].strip("[]").split()]
                with self.subTest(mediabox=mb, rotation=rot):
                    self.assertTrue(near(a.rect * pdfcoords.to_pdf(p), R(raw).normalize(), 0.01))
                    self.assertTrue(near(R(raw) * pdfcoords.to_page(p), a.rect, 0.01))
                    self.assertTrue(near(R(raw) * p.transformation_matrix, a.rect, 0.01))

    def test_pymupdf_draws_in_place(self):
        """PyMuPDF's own drawing goes through page.transformation_matrix: lines, pictures,
        placed pages and links land where asked on a rotated, cropped page."""
        for rot in (0, 90, 180, 270):
            d = F.open()
            p = d.new_page(width=600, height=800)
            p.set_cropbox(R(100, 50, 500, 700))
            p.set_rotation(rot)
            p.draw_rect(R(10, 20, 60, 40), color=(1, 0, 0))
            pix = F.Pixmap(F.csRGB, F.IRect(0, 0, 10, 10), 0)
            pix.clear_with(0)
            p.insert_image(R(200, 400, 250, 450), pixmap=pix)
            p.insert_link({"kind": F.LINK_URI, "from": R(20, 500, 80, 520), "uri": "https://x.example"})
            with self.subTest(rotation=rot):
                self.assertTrue(near(p.get_drawings()[0]["rect"], R(10, 20, 60, 40)))
                self.assertTrue(near(p.get_image_info()[0]["bbox"], R(200, 400, 250, 450)))
                derotate = p.derotation_matrix
                del p                   # get_links reads the links of a freshly loaded page
                link = R(d[0].get_links()[0]["from"]) * derotate
                self.assertTrue(near(link.normalize(), R(20, 500, 80, 520)))


class CroppedPages(unittest.TestCase):
    def view(self, rot):
        """A sheet with /Rotate rot and a blue square shown at (300, 300)-(350, 350), cropped
        so that what's shown at (150, 150) is the new top-left corner."""
        d = F.open()
        p = d.new_page(width=1728, height=2592) if rot % 180 else d.new_page(width=2592, height=1728)
        p.set_rotation(rot)
        p.draw_rect((R(300, 300, 350, 350) * p.derotation_matrix).normalize(), color=(0, 0, 1),
                    fill=(0, 0, 1))
        path = os.path.join(tempfile.mkdtemp(), "c.pdf")
        d.save(path)
        v = DocumentView(path)
        self.addCleanup(v.close_doc)
        v.crop_pages(0, (R(150, 150, 1200, 900) * v.doc[0].derotation_matrix).normalize())
        return v

    def to_page(self, v, x, y):
        return P(x, y) * v.doc[0].derotation_matrix

    def shown(self, page, rect):
        return (R(rect) * page.rotation_matrix).normalize()

    def test_link_on_markup_follows_it(self):
        for rot in (0, 90, 270):
            with self.subTest(rotation=rot):
                v = self.view(rot)
                v.apply_drag_tool(0, "rect", self.to_page(v, 100, 100), self.to_page(v, 200, 160), False)
                xref = max(a.xref for a in v.doc[0].annots())
                v.select_xref(0, xref)
                v.add_link(0, None, ("uri", "https://x.example", "none"),
                           rects=[A.bounds(v.selected_model)])
                self.assertTrue(near(R(v.doc[0].get_links()[0]["from"]), R(100, 100, 200, 160)))
                v.commit_model(0, v.selection[1], A.moved(
                    v.selected_model, self.to_page(v, 50, 0) - self.to_page(v, 0, 0)))
                self.assertTrue(near(R(v.doc[0].get_links()[0]["from"]), R(150, 100, 250, 160)))

    def test_pasted_capture_lands_at_the_paste_point(self):
        for rot in (0, 90, 270):
            with self.subTest(rotation=rot):
                v = self.view(rot)
                v.capture_area(0, (R(50, 50, 300, 300) * v.doc[0].derotation_matrix).normalize())
                with mock.patch.object(v, "paste_target", lambda: (0, self.to_page(v, 400, 400))):
                    v.paste()
                pg = v.doc[0]
                stamp = [a for a in pg.annots() if a.type[0] == F.PDF_ANNOT_STAMP][0]
                self.assertTrue(near(self.shown(pg, stamp.rect), R(400, 400, 650, 650)))
                # the square, 100 pt into the captured area, is drawn there
                pm = pg.get_pixmap(dpi=72)
                self.assertEqual(pm.pixel(525, 525), (0, 0, 255))
                del stamp, pg

    def test_measurement_label_by_its_line(self):
        for rot in (0, 90, 270):
            with self.subTest(rotation=rot):
                v = self.view(rot)
                v.set_page_scale([0], measure.scale_from_preset(48), "ft-in", "x")
                v.apply_drag_tool(0, "m_length", self.to_page(v, 100, 100), self.to_page(v, 460, 100),
                                  False)
                pg = v.doc[0]
                box = self.shown(pg, next(pg.annots()).rect)
                self.assertTrue(pg.rect.contains(box), box)
                self.assertLess(box.height, 40)
                # the label is drawn above the middle of the line
                pm = pg.get_pixmap(dpi=72, clip=R(250, 80, 310, 99))
                self.assertTrue(any(pm.pixel(x, y) != (255, 255, 255) for x in range(pm.width)
                                    for y in range(pm.height)))

    def test_edit_objects_pick_shape_where_shown(self):
        for rot in (0, 90, 270):
            with self.subTest(rotation=rot):
                v = self.view(rot)
                it = v.object_at(0, self.to_page(v, 175, 175))
                self.assertIsNotNone(it)
                self.assertTrue(near(self.shown(v.doc[0], it["rect"]), R(150, 150, 200, 200)))


if __name__ == "__main__":
    unittest.main()
