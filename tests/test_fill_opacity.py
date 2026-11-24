"""Fill opacity (the owner, 23 Nov 2026: text boxes, callouts and other filled markups need a
fill opacity of their own; "usually only the fill changes"): the fill drawn at opacity x
fill opacity, the outline and the text at the markup's opacity, drawn in the markup's own
appearance so other viewers show it too; kept when saved, opened and moved; a row in
Properties.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_fill_opacity
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

from kanzonas import annotations as A  # noqa: E402

BOX = pymupdf.Rect(100, 100, 250, 180)
INSIDE = pymupdf.Point(175, 165)            # (in the fill, below a text box's first line)
EDGE = pymupdf.Point(100, 140)              # (on the left side of the outline)
TRIANGLE = [pymupdf.Point(100, 100), pymupdf.Point(250, 100), pymupdf.Point(175, 180)]
IN_TRIANGLE = pymupdf.Point(140, 106)     # (away from an Area's label)
KINDS = {"rect": {}, "ellipse": {}, "textbox": {"text": "MMMM"},
         "callout": {"text": "MMMM", "points": [pymupdf.Point(400, 400)]},
         "polygon": {"points": TRIANGLE}, "m_area": {"points": TRIANGLE}}


def make(page, kind, fill_opacity, opacity=1.0, fill="#00ff00"):
    p = dict(A.tool_props(kind))
    p.update(fill=fill, fill_opacity=fill_opacity, opacity=opacity, width=4.0,
             stroke="#ff0000")
    if "text_color" in p:
        p["text_color"] = "#000000"
    return A.write(page, {"kind": kind, "props": p, "rect": pymupdf.Rect(BOX), **KINDS[kind]})


def pixel(page, at):
    return page.get_pixmap(clip=pymupdf.Rect(at, at + (1, 1)), annots=True).pixel(0, 0)


def inside(kind):
    return IN_TRIANGLE if kind in ("polygon", "m_area") else INSIDE


class Drawn(unittest.TestCase):
    def setUp(self):
        self.doc = pymupdf.open()
        self.page = self.doc.new_page()

    def test_the_fill_alone_is_see_through(self):
        for kind in KINDS:
            with self.subTest(kind=kind):
                a = make(self.page, kind, 0.3)
                r, g, b = pixel(self.page, inside(kind))
                # green at 30% over white: (179, 255, 179)
                self.assertAlmostEqual(r, 179, delta=3)
                self.assertEqual(g, 255)
                self.assertAlmostEqual(b, 179, delta=3)
                if kind in ("rect", "textbox", "callout"):
                    # (the outline as solid as before)
                    self.assertEqual(pixel(self.page, EDGE)[1:], (0, 0))
                self.page.delete_annot(a)

    def test_times_the_markups_opacity(self):
        a = make(self.page, "rect", 0.3, opacity=0.5)
        self.assertAlmostEqual(pixel(self.page, INSIDE)[0], 217, delta=3)    # 15% green
        self.assertAlmostEqual(pixel(self.page, EDGE)[1], 128, delta=3)      # 50% red
        self.page.delete_annot(a)

    def test_the_text_stays_solid(self):
        make(self.page, "textbox", 0.0)
        pix = self.page.get_pixmap(clip=pymupdf.Rect(100, 100, 250, 125), annots=True)
        darkest = min(pix.pixel(x, y) for x in range(pix.width) for y in range(pix.height))
        self.assertLess(max(darkest), 40)

    def test_a_measurements_label_keeps_its_box(self):
        a = make(self.page, "m_area", 0.2)
        ap = int(self.doc.xref_get_key(a.xref, "AP/N")[1].split()[0])
        data = self.doc.xref_stream(ap)
        self.assertEqual(data.count(b"/KZFill gs"), 1)       # (the area's fill only)
        self.assertLess(data.index(b"/KZFill gs"), data.index(b"BT"))

    def test_solid_or_unfilled_is_drawn_as_before(self):
        for fill_opacity, fill in ((1.0, "#00ff00"), (0.3, None)):
            a = make(self.page, "rect", fill_opacity, fill=fill)
            ap = int(self.doc.xref_get_key(a.xref, "AP/N")[1].split()[0])
            self.assertNotIn(b"KZFill", self.doc.xref_stream(ap))
            self.page.delete_annot(a)


class Kept(unittest.TestCase):
    def test_saved_opened_and_moved(self):
        path = os.path.join(tempfile.mkdtemp(), "fill.pdf")
        doc = pymupdf.open()
        a = make(doc.new_page(), "callout", 0.25)
        xref = a.xref
        doc.save(path)
        doc = pymupdf.open(path)
        page = doc[0]
        model = A.read(page.load_annot(xref))
        self.assertEqual(model["props"]["fill_opacity"], 0.25)
        self.assertTrue(A.shift_in_place(page, xref, pymupdf.Point(0, 200)))
        r = pixel(page, INSIDE + (0, 200))[0]
        self.assertAlmostEqual(r, 191, delta=3)             # green at 25%
        # (written anew from its model, as an edit does: the same)
        moved = A.read(page.load_annot(xref))
        page.delete_annot(page.load_annot(xref))
        A.write(page, moved)
        self.assertAlmostEqual(pixel(page, INSIDE + (0, 200))[0], 191, delta=3)

    def test_made_before_1_16_4_reads_solid(self):
        doc = pymupdf.open()
        page = doc.new_page()
        a = page.add_rect_annot(BOX)
        a.set_colors(stroke=(1, 0, 0), fill=(0, 1, 0))
        a.update()
        self.assertEqual(A.read(a)["props"]["fill_opacity"], 1.0)


class InProperties(unittest.TestCase):
    def test_a_row_for_filled_kinds_and_it_applies(self):
        from kanzonas.properties import PropertiesPanel
        panel = PropertiesPanel()
        got = []
        panel.propsChanged.connect(got.append)
        props = dict(A.tool_props("rect"), fill="#00ff00", fill_opacity=0.4)
        panel.show_target("rect", props, selected=True)
        lab, w = panel.rows["fill_opacity"]
        self.assertFalse(w.isHidden())
        self.assertEqual(w.value(), 40)
        w.setValue(70)
        self.assertEqual(got[-1]["fill_opacity"], 0.7)
        self.assertEqual(got[-1]["opacity"], props["opacity"])
        panel.show_target("line", dict(A.tool_props("line")), selected=True)
        self.assertTrue(panel.rows["fill_opacity"][1].isHidden())
        # (a mask hides what's under it: no fill opacity)
        self.assertNotIn("fill_opacity", A.tool_props("mask"))


if __name__ == "__main__":
    unittest.main()
