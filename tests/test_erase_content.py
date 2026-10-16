"""Erase content on vector fills: a solid, hatched (tiling pattern) or gradient (shading
pattern) shape that crosses the erase box keeps its outside part and loses the inside. Before
0.92.2 a hatch or gradient erased in one spot vanished whole (MuPDF's redaction removes any
path the box touches, and only solid colors were redrawn)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pymupdf  # noqa: E402

from kanzonas import erase  # noqa: E402

RED = (0.8, 0.2, 0.2)
# shape in PDF user space: x 100..300, y 150..300 (PyMuPDF page coordinates: y 100..250)
SHAPE_PDF = "100 150 200 150 re"
BOX = pymupdf.Rect(150, 150, 170, 170)          # PyMuPDF coordinates, inside the shape
HATCH = (b"0.8 0.2 0.2 RG 1 w 0 0 m 10 10 l S 0 10 m 10 0 l S", "/PaintType 1")
SHADING = ("<< /ShadingType 2 /ColorSpace /DeviceRGB /Coords [100 0 300 0] /Function "
           "<< /FunctionType 2 /Domain [0 1] /C0 [0.8 0.2 0.2] /C1 [0.2 0.2 0.8] /N 1 >> "
           "/Extend [true true] >>")


def colored(page, clip=None):
    """How many pixels of the page (or the clip, PyMuPDF coordinates) aren't white."""
    pix = page.get_pixmap(dpi=72, clip=clip, colorspace=pymupdf.csRGB, alpha=False)
    s = pix.samples
    return sum(1 for i in range(0, len(s), 3) if not (s[i] > 245 and s[i + 1] > 245 and s[i + 2] > 245))


def new_doc():
    doc = pymupdf.open()
    doc.new_page(width=400, height=400)
    return doc


def set_content(page, content, resources=None):
    doc = page.parent
    c = doc.get_new_xref()
    doc.update_object(c, "<<>>")
    doc.update_stream(c, content)
    page.set_contents(c)
    if resources is not None:
        doc.xref_set_key(page.xref, "Resources", resources)


def tiling_pattern(doc, paint_type=1, matrix=None):
    x = doc.get_new_xref()
    m = f" /Matrix {matrix}" if matrix else ""
    doc.update_object(x, "<< /Type /Pattern /PatternType 1 /PaintType %d /TilingType 1 "
                         "/BBox [0 0 10 10] /XStep 10 /YStep 10 /Resources << >>%s >>"
                      % (paint_type, m))
    if paint_type == 1:
        doc.update_stream(x, HATCH[0])
    else:
        doc.update_stream(x, b"1 w 0 0 m 10 10 l S 0 10 m 10 0 l S")   # color comes from scn
    return x


def shading_pattern(doc):
    x = doc.get_new_xref()
    doc.update_object(x, f"<< /Type /Pattern /PatternType 2 /Shading {SHADING} >>")
    return x


class EraseContent(unittest.TestCase):
    def check_cut(self, doc, before=None):
        """After erase: nothing left inside the box, most of the shape left outside."""
        page = doc[0]
        before = colored(page) if before is None else before
        self.assertGreater(before, 0)
        erase.erase(page, BOX)
        page = doc[0]
        shown = BOX * page.rotation_matrix          # where the box is on a rotated page
        self.assertEqual(colored(page, shown + (1, 1, -1, -1)), 0, "the box is not empty")
        after = colored(page)
        self.assertGreater(after, before * 0.8, "most of the shape should survive")
        self.assertLess(after, before, "something inside the box should be gone")
        return page

    def test_solid_fill_keeps_its_outside_part(self):
        doc = new_doc()
        set_content(doc[0], f"q 0.8 0.2 0.2 rg {SHAPE_PDF} f Q".encode())
        page = self.check_cut(doc)
        # a point outside the box but inside the shape is still red
        self.assertGreater(colored(page, pymupdf.Rect(110, 110, 120, 120)), 50)

    def test_hatch_pattern_fill_survives_outside_the_box(self):
        doc = new_doc()
        pat = tiling_pattern(doc)
        set_content(doc[0], f"q /Pattern cs /P1 scn {SHAPE_PDF} f Q".encode(),
                    f"<< /Pattern << /P1 {pat} 0 R >> >>")
        self.check_cut(doc)

    def test_gradient_fill_survives_outside_the_box(self):
        doc = new_doc()
        pat = shading_pattern(doc)
        set_content(doc[0], f"q /Pattern cs /P1 scn {SHAPE_PDF} f Q".encode(),
                    f"<< /Pattern << /P1 {pat} 0 R >> >>")
        page = self.check_cut(doc)
        # left end still reddish, right end still bluish: the gradient is the same one
        l = page.get_pixmap(dpi=72, clip=pymupdf.Rect(102, 102, 106, 106), alpha=False).pixel(1, 1)
        r = page.get_pixmap(dpi=72, clip=pymupdf.Rect(294, 240, 298, 244), alpha=False).pixel(1, 1)
        self.assertGreater(l[0], l[2])
        self.assertGreater(r[2], r[0])

    def test_hatch_entirely_inside_the_box_is_removed(self):
        doc = new_doc()
        pat = tiling_pattern(doc)
        set_content(doc[0], f"q /Pattern cs /P1 scn 160 160 20 20 re f Q".encode(),
                    f"<< /Pattern << /P1 {pat} 0 R >> >>")
        page = doc[0]
        self.assertGreater(colored(page), 0)
        erase.erase(page, pymupdf.Rect(100, 100, 300, 300))
        self.assertEqual(colored(doc[0]), 0)

    def test_hatch_inside_a_form_with_a_matrix(self):
        doc = new_doc()
        form_doc = pymupdf.open()
        q = form_doc.new_page(width=800, height=800)
        pat = tiling_pattern(form_doc)
        set_content(q, b"q /Pattern cs /P1 scn 200 300 400 300 re f Q",
                    f"<< /Pattern << /P1 {pat} 0 R >> >>")
        # the form is drawn at half size: its 200..600 x 300..600 lands on 100..300 x 150..300
        doc[0].show_pdf_page(pymupdf.Rect(0, 0, 400, 400), form_doc, 0)
        page = self.check_cut(doc)
        # the pattern copy used for the repaint carries the form's scale in its Matrix
        t, v = doc.xref_get_key(page.xref, "Resources/Pattern/KzErP1")
        self.assertEqual(t, "xref", "the repaint registered its pattern")
        t, m = doc.xref_get_key(int(v.split()[0]), "Matrix")
        self.assertEqual(t, "array")
        a = [float(x) for x in m.strip("[] ").split()]
        self.assertAlmostEqual(a[0], 0.5, places=3)
        self.assertAlmostEqual(a[3], 0.5, places=3)

    def test_uncolored_pattern_keeps_its_color_operands(self):
        doc = new_doc()
        pat = tiling_pattern(doc, paint_type=2)
        set_content(doc[0], f"q /CS0 cs 0 0 1 /P1 scn {SHAPE_PDF} f Q".encode(),
                    f"<< /Pattern << /P1 {pat} 0 R >> /ColorSpace << /CS0 [/Pattern /DeviceRGB] >> >>")
        page = self.check_cut(doc)
        pix = page.get_pixmap(dpi=144, clip=pymupdf.Rect(100, 100, 150, 150), alpha=False)
        blues = [pix.pixel(i, j) for i in range(pix.width) for j in range(pix.height)
                 if pix.pixel(i, j)[2] > 200 and pix.pixel(i, j)[0] < 80]
        self.assertGreater(len(blues), 20, "the hatch lines are still blue")

    def test_clipping_path_is_kept_on_the_repaint(self):
        doc = new_doc()
        pat = tiling_pattern(doc)
        # the hatch is clipped to x 120..220 (PDF) before being painted
        set_content(doc[0], f"q 120 150 100 150 re W n /Pattern cs /P1 scn {SHAPE_PDF} f Q".encode(),
                    f"<< /Pattern << /P1 {pat} 0 R >> >>")
        page = self.check_cut(doc)
        self.assertEqual(colored(page, pymupdf.Rect(230, 100, 300, 250)), 0,
                         "outside the original clip stays empty")

    def test_rotated_page(self):
        doc = new_doc()
        pat = tiling_pattern(doc)
        set_content(doc[0], f"q /Pattern cs /P1 scn {SHAPE_PDF} f Q".encode(),
                    f"<< /Pattern << /P1 {pat} 0 R >> >>")
        doc[0].set_rotation(90)
        self.check_cut(doc)         # BOX is in unrotated coordinates, like the view passes

    def test_indirect_resources_dictionary(self):
        doc = new_doc()
        pat = tiling_pattern(doc)
        res = doc.get_new_xref()
        doc.update_object(res, f"<< /Pattern << /P1 {pat} 0 R >> >>")
        set_content(doc[0], f"q /Pattern cs /P1 scn {SHAPE_PDF} f Q".encode(), f"{res} 0 R")
        self.check_cut(doc)

    def test_lines_are_still_cut_and_text_and_pictures_still_erased(self):
        doc = new_doc()
        page = doc[0]
        s = page.new_shape()
        s.draw_line(pymupdf.Point(100, 160), pymupdf.Point(300, 160))   # through the box
        s.finish(color=(0, 0, 0), width=2)
        s.commit()
        page.insert_text((155, 165), "x", fontsize=8)
        page.insert_image(pymupdf.Rect(150, 150, 170, 170),
                          stream=pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 4, 4), 0)
                          .tobytes("png"))
        erase.erase(page, BOX)
        page = doc[0]
        self.assertEqual(colored(page, BOX + (1, 1, -1, -1)), 0)
        self.assertGreater(colored(page, pymupdf.Rect(100, 155, 140, 165)), 10, "line kept left")
        self.assertGreater(colored(page, pymupdf.Rect(180, 155, 300, 165)), 10, "line kept right")
        self.assertEqual(page.get_text("text").strip(), "")

    def test_odd_content_does_not_break_the_erase(self):
        doc = new_doc()
        pat = tiling_pattern(doc)
        junk = (b"q BI /W 2 /H 2 /CS /G /BPC 8 ID \x00\xff\xff\x00 EI (str\\)ing) Tj <414>Tj "
                b"[1 2] 0 d /Nope Do 1 2 3 cm Q q /Pattern cs /P1 scn " + SHAPE_PDF.encode() + b" f Q")
        set_content(doc[0], junk, f"<< /Pattern << /P1 {pat} 0 R >> >>")
        self.check_cut(doc)


if __name__ == "__main__":
    unittest.main()
