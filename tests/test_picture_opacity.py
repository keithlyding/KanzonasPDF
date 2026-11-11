"""Opacity on pictures (issue #82: "the transparency function isn't working for captured
elements"): a pasted picture or Capture area's vector capture draws at its opacity, set when
it's placed or changed afterwards in Properties, and keeps it when moved, saved and opened.
(Before: the picture's appearance was written anew without the transparency PyMuPDF had put
in it, so it drew solid whatever the opacity said.)

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_picture_opacity
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import annotations, capture  # noqa: E402
from kanzonas.document_view import DocumentView  # noqa: E402

CAP = pymupdf.Rect(300, 100, 420, 220)
PIC = pymupdf.Rect(300, 400, 420, 520)


def black_png():
    pm = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 40, 40), False)
    pm.clear_with(0)
    return pm.tobytes("png")


def sample(path, opacity):
    """A page with a black square, a capture of it and a black picture, both at opacity."""
    d = pymupdf.open()
    pg = d.new_page()
    pg.draw_rect((100, 100, 200, 200), color=(0, 0, 0), fill=(0, 0, 0))
    data, box = capture.snapshot(pg, pymupdf.Rect(90, 90, 210, 210))
    form = capture.make_form(d, data, box)
    pg = d[0]
    annotations.write(pg, {"kind": "image", "rect": CAP, "img": form, "text": "",
                           "props": {"opacity": opacity}})
    annotations.write(pg, {"kind": "image", "rect": PIC, "image_bytes": black_png(),
                           "text": "", "props": {"opacity": opacity}})
    d.save(path)


def gray(doc, rect):
    """The gray (0 black .. 255 white) at the middle of rect, as the page draws."""
    c = (rect.tl + rect.br) / 2
    return doc[0].get_pixmap(clip=pymupdf.Rect(c, c + (1, 1))).pixel(0, 0)[0]


class Opacity(unittest.TestCase):
    def setUp(self):
        self.path = os.path.join(tempfile.mkdtemp(), "pictures.pdf")

    def test_placed_at_half_opacity_draws_half(self):
        sample(self.path, 0.5)
        d = pymupdf.open(self.path)
        for r in (CAP, PIC):
            self.assertAlmostEqual(gray(d, r), 128, delta=3)

    def test_solid_stays_solid(self):
        sample(self.path, 1.0)
        d = pymupdf.open(self.path)
        for r in (CAP, PIC):
            self.assertEqual(gray(d, r), 0)

    def test_changed_in_properties_moved_and_saved(self):
        sample(self.path, 1.0)
        v = DocumentView(self.path)
        self.addCleanup(v.close_doc)
        for r in (CAP, PIC):
            x = next(a.xref for a in v.doc[0].annots() if a.rect.intersects(r))
            v.select_xref(0, x)
            v.update_selected_props({"opacity": 0.25})
            self.assertAlmostEqual(gray(v.doc, r), 191, delta=3)
        # moved: the opacity goes along
        x = next(a.xref for a in v.doc[0].annots() if a.rect.intersects(PIC))
        v.select_xref(0, x)
        v.nudge(0, 1, 100)
        moved = PIC + (0, 100, 0, 100)
        self.assertAlmostEqual(gray(v.doc, moved), 191, delta=3)
        out = os.path.join(os.path.dirname(self.path), "saved.pdf")
        v.doc.save(out)
        d = pymupdf.open(out)
        self.assertAlmostEqual(gray(d, CAP), 191, delta=3)
        self.assertAlmostEqual(gray(d, moved), 191, delta=3)


if __name__ == "__main__":
    unittest.main()
