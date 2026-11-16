"""The Image tool takes SVG drawings: they go into the page as their lines, shapes and text
(sharp at any zoom), one group in Edit objects, upright on a turned page, in the dragged box
or at their own size at a click. MuPDF reads them; a picture an SVG links to outside the file
is left out (nothing else on the computer is read).

The owner, 16 Nov 2026: "Can I insert an svg file?"

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_svg_image
"""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf as F  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import dialogs, document_view  # noqa: E402
from kanzonas.document_view import DocumentView  # noqa: E402

# red top left, green bottom left, blue on the right: which way up it is shows
SVG = ('<svg xmlns="http://www.w3.org/2000/svg" width="200" height="100">'
       '<rect x="0" y="0" width="100" height="50" fill="red"/>'
       '<rect x="0" y="50" width="100" height="50" fill="lime"/>'
       '<rect x="100" y="0" width="100" height="100" fill="blue"/></svg>')
RED, GREEN, BLUE = (255, 0, 0), (0, 255, 0), (0, 0, 255)


class SvgImage(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.svg = self.file("drawing.svg", SVG)

    def file(self, name, text):
        p = os.path.join(self.tmp, name)
        with open(p, "w", encoding="utf-8") as f:
            f.write(text)
        return p

    def view(self, rotation=0):
        d = F.open()
        d.new_page().set_rotation(rotation)
        p = os.path.join(self.tmp, "in%d.pdf" % len(os.listdir(self.tmp)))
        d.save(p)
        v = DocumentView(p)
        v.resize(900, 1100)
        v.show()
        APP.processEvents()
        self.addCleanup(v.close_doc)
        return v

    def place(self, v, path, a, b, click=False):
        page = v.doc[0]
        # (a and b as the page is shown)
        with mock.patch.object(dialogs, "open_file", return_value=path):
            v.place_image(0, F.Point(a) * page.derotation_matrix,
                          F.Point(b) * page.derotation_matrix, click)

    def test_its_drawing_goes_into_the_page_as_one_group(self):
        v = self.view()
        self.place(v, self.svg, (100, 100), (300, 200))
        self.assertEqual(len(list(v.doc[0].annots())), 0)
        self.assertEqual([it["kind"] for it in v.content_objects(0).items], ["group"])
        self.assertEqual(v.doc[0].get_images(), [])         # (lines and shapes, no picture)
        self.assertEqual(len(v.doc[0].get_drawings()), 3)

    def test_upright_on_a_page_turned_any_way(self):
        for rot in (0, 90, 180, 270):
            v = self.view(rot)
            self.place(v, self.svg, (100, 100), (300, 200))
            pix = v.doc[0].get_pixmap()                     # (as shown, turned)
            self.assertEqual(pix.pixel(140, 120), RED, rot)
            self.assertEqual(pix.pixel(140, 180), GREEN, rot)
            self.assertEqual(pix.pixel(260, 150), BLUE, rot)

    def test_in_the_dragged_box_keeping_its_proportions(self):
        v = self.view()
        self.place(v, self.svg, (100, 100), (500, 400))     # (wider room: 400 by 300)
        r = v.doc[0].get_drawings()
        box = F.Rect(r[0]["rect"])
        for d in r[1:]:
            box |= d["rect"]
        self.assertAlmostEqual(box.width, 400, 0)
        self.assertAlmostEqual(box.height, 200, 0)
        self.assertAlmostEqual(box.x0, 100, 0)
        self.assertAlmostEqual(box.y0, 100, 0)

    def test_a_click_places_it_at_its_own_size(self):
        v = self.view()
        self.place(v, self.svg, (100, 100), (100, 100), click=True)
        r = v.doc[0].get_drawings()
        box = F.Rect(r[0]["rect"])
        for d in r[1:]:
            box |= d["rect"]
        self.assertAlmostEqual(box.width, 200, 0)
        self.assertAlmostEqual(box.height, 100, 0)

    def test_undo_takes_it_away_and_redo_brings_it_back(self):
        v = self.view()
        before = v.doc.tobytes()
        self.place(v, self.svg, (100, 100), (300, 200))
        after = v.doc[0].get_pixmap().samples
        v.undo()
        self.assertEqual(v.doc[0].get_drawings(), [])
        self.assertEqual(F.open("pdf", v.doc.tobytes())[0].get_pixmap().samples,
                         F.open("pdf", before)[0].get_pixmap().samples)
        v.redo()
        self.assertEqual(v.doc[0].get_pixmap().samples, after)

    def test_saved_and_opened_again_it_is_still_there(self):
        v = self.view()
        self.place(v, self.svg, (100, 100), (300, 200))
        again = F.open("pdf", v.doc.tobytes(garbage=1))
        self.assertEqual(again[0].get_pixmap().pixel(140, 120), RED)

    def test_a_picture_it_links_to_outside_the_file_is_left_out(self):
        pm = F.Pixmap(F.csRGB, F.IRect(0, 0, 20, 20), 0)
        pm.set_rect(pm.irect, (255, 0, 0))
        png = os.path.join(self.tmp, "outside.png")
        pm.save(png)
        svg = self.file("links.svg", '<svg xmlns="http://www.w3.org/2000/svg" '
                        'xmlns:xlink="http://www.w3.org/1999/xlink" width="100" height="100">'
                        '<rect width="100" height="100" fill="blue"/>'
                        '<image x="0" y="0" width="100" height="100" xlink:href="%s"/></svg>'
                        % png.replace("\\", "/"))
        v = self.view()
        self.place(v, svg, (100, 100), (200, 200))
        self.assertEqual(v.doc[0].get_images(), [])
        self.assertEqual(v.doc[0].get_pixmap().pixel(150, 150), BLUE)

    def test_a_broken_or_empty_svg_says_so_and_changes_nothing(self):
        warned = []
        with mock.patch.object(QMessageBox, "warning",
                               side_effect=lambda *a, **k: warned.append(a[2])):
            for name, text in (("broken.svg", "<svg this is not"),
                               ("empty.svg", '<svg xmlns="http://www.w3.org/2000/svg" '
                                             'width="0" height="0"/>')):
                v = self.view()
                rev = v.revision
                self.place(v, self.file(name, text), (100, 100), (300, 200))
                self.assertEqual(v.revision, rev, name)
                self.assertEqual(v.doc[0].get_drawings(), [], name)
        self.assertEqual(len(warned), 2)
        self.assertTrue(all("SVG" in w for w in warned))

    def test_an_svg_is_known_by_its_name_or_its_start(self):
        is_svg = document_view.is_svg
        self.assertTrue(is_svg("a.SVG", b""))
        self.assertTrue(is_svg("a.svgz", b"\x1f\x8b"))
        self.assertTrue(is_svg("drawing", b"\xef\xbb\xbf  <svg xmlns=..."))
        self.assertTrue(is_svg("drawing", b'<?xml version="1.0"?>\n<svg>'))
        self.assertFalse(is_svg("a.png", b"\x89PNG\r\n"))
        self.assertFalse(is_svg("notes.xml", b'<?xml version="1.0"?><notes/>'))

    def test_the_file_picker_offers_svg(self):
        self.assertIn("*.svg", DocumentView.IMAGE_FILTER)


if __name__ == "__main__":
    unittest.main()
