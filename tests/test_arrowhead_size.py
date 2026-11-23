"""Arrowhead size (the owner, 23 Nov 2026: "be able to change arrowhead sizes"): a line's,
arrow's, polyline's, arc's, curve's, callout's and dimension's heads, and a line's middle
arrow, drawn at a size against the one the line's width gives (100%: as before), the line
as wide as before; the markup's box holds the bigger heads; the PDF's line endings stay;
kept when saved, opened and moved; a row in Properties.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_arrowhead_size
"""
import os
import re
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import annotations as A, dimensions  # noqa: E402

P = pymupdf.Point


def make(page, kind, size, points, **props):
    p = dict(A.tool_props(kind), head_size=size, **props)
    extra = {}
    if kind == "callout":
        extra = {"text": "Note", "rect": pymupdf.Rect(100, 450, 200, 500)}
    return A.write(page, {"kind": kind, "props": p, "points": points,
                          "rect": extra.pop("rect", pymupdf.Rect(0, 0, 1, 1)), **extra})


def stream(doc, annot):
    return doc.xref_stream(int(doc.xref_get_key(annot.xref, "AP/N")[1].split()[0]))


def head_reach(doc, annot, end):
    """How far the drawing reaches from end (a point in PDF coordinates), the line itself
    left out: the size of the head there."""
    blocks, cur = [], []
    for ln in stream(doc, annot).split(b"\n"):
        nums = [float(x) for x in re.findall(rb"[-+]?(?:\d+\.?\d*|\.\d+)", ln)]
        if ln.strip().endswith(b" m"):
            cur = [nums]
        elif cur and ln.strip() and ln.strip()[-1:] in (b"l", b"c"):
            cur.append(nums)
        elif cur and ln.strip() in (b"S", b"b", b"f", b"B", b"s"):
            blocks.append([P(n[k], n[k + 1]) for n in cur for k in range(0, len(n) - 1, 2)])
            cur = []
    heads = [b for b in blocks[1:] if min(abs(q - end) for q in b) < 40]
    return max(abs(q - end) for b in heads for q in b)


class Drawn(unittest.TestCase):
    def setUp(self):
        self.doc = pymupdf.open()
        self.page = self.doc.new_page()
        self.to_pdf = self.page.transformation_matrix

    def reach(self, kind, points, size, end_index=-1, **props):
        a = make(self.page, kind, size, points, **props)
        r = head_reach(self.doc, a, points[end_index] * self.to_pdf)
        return a, r

    def test_three_times_as_big_the_line_as_wide(self):
        for kind, pts, props in (
                ("arrow", [P(100, 200), P(300, 200)], {}),
                ("line", [P(100, 100), P(300, 150)], {"head": "closed"}),
                ("polyline", [P(100, 300), P(200, 350), P(300, 300)], {"head": "open"}),
                ("line", [P(100, 600), P(300, 600)], {"head": "open", "dash": "dash"})):
            with self.subTest(kind=kind, props=props):
                a1, r1 = self.reach(kind, pts, 1.0, **props)
                a3, r3 = self.reach(kind, pts, 3.0, **props)
                self.assertAlmostEqual(r3 / r1, 3.0, delta=0.05)
                self.assertIn(b"2 w", stream(self.doc, a3))
                self.assertEqual(self.doc.xref_get_key(a3.xref, "LE"),
                                 self.doc.xref_get_key(a1.xref, "LE"))

    def test_a_round_end_about_its_point(self):
        pts = [P(100, 100), P(300, 150)]
        _, r1 = self.reach("line", pts, 1.0, 0, head_start="circle")
        _, r2 = self.reach("line", pts, 2.0, 0, head_start="circle")
        self.assertAlmostEqual(r2 / r1, 2.0, delta=0.05)

    def test_a_callouts_arrow(self):
        a1 = make(self.page, "callout", 1.0, [P(400, 600)])
        a2 = make(self.page, "callout", 2.5, [P(400, 600)])
        end = P(400, 600) * self.to_pdf
        self.assertAlmostEqual(head_reach(self.doc, a2, end) / head_reach(self.doc, a1, end),
                               2.5, delta=0.05)

    def test_the_bigger_head_is_drawn_whole(self):
        # (the markup's box grows: a head past it would be cut off)
        a = make(self.page, "arrow", 4.0, [P(100, 200), P(300, 200)])
        self.assertGreater(a.rect.height, 60)
        pix = self.page.get_pixmap(clip=pymupdf.Rect(220, 160, 300, 240), annots=True)
        inked = {(x, y) for x in range(pix.width) for y in range(pix.height)
                 if pix.pixel(x, y)[1] < 150}         # (the red arrow: green is low)
        self.assertTrue(any(y < 10 for _x, y in inked))     # (a wing near the box's top)

    def test_as_before_at_100(self):
        pts = [P(100, 200), P(300, 200)]
        before = A.write(self.page, {"kind": "arrow", "props": dict(A.tool_props("arrow")),
                                     "points": pts, "rect": pymupdf.Rect(0, 0, 1, 1)})
        same = make(self.page, "arrow", 1.0, pts)
        self.assertEqual(stream(self.doc, before), stream(self.doc, same))

    def test_middle_arrow_and_dimension(self):
        pts = [P(100, 100), P(300, 100)]
        self.assertAlmostEqual(
            abs(A.mid_arrow(pts, 2, "open", 3.0)[1] - A.mid_arrow(pts, 2, "open", 3.0)[0]) /
            abs(A.mid_arrow(pts, 2, "open")[1] - A.mid_arrow(pts, 2, "open")[0]), 3.0, delta=0.01)
        dim = [P(100, 500), P(300, 500), P(200, 520)]
        d1 = make(self.page, "m_dim", 1.0, dim)
        d2 = make(self.page, "m_dim", 2.0, dim)

        def head(a):
            s = stream(self.doc, a).decode()
            m = re.search(r"([\d.]+) ([\d.]+) m ([\d.]+) ([\d.]+) l [\d. ]+ l h f", s)
            return abs(P(float(m[1]), float(m[2])) - P(float(m[3]), float(m[4])))
        self.assertAlmostEqual(head(d2) / head(d1), 2.0, delta=0.05)
        self.assertAlmostEqual(head(d1), abs(P(dimensions.head_size(1.0), dimensions.head_size(1.0) / 3)),
                               delta=0.05)

    def test_the_range(self):
        self.assertEqual(A.head_scale({"head_size": 99}), A.HEAD_SCALES[1])
        self.assertEqual(A.head_scale({"head_size": 0.01}), A.HEAD_SCALES[0])
        self.assertEqual(A.head_scale({"head_size": "x"}), 1.0)
        self.assertEqual(A.head_scale({}), 1.0)


class Kept(unittest.TestCase):
    def test_saved_opened_and_moved(self):
        path = os.path.join(tempfile.mkdtemp(), "heads.pdf")
        doc = pymupdf.open()
        page = doc.new_page()
        pts = [P(100, 200), P(300, 200)]
        a = make(page, "arrow", 2.0, pts)
        xref = a.xref
        reach = head_reach(doc, a, pts[1] * page.transformation_matrix)
        doc.save(path)
        drawn = stream(doc, a)
        doc = pymupdf.open(path)
        page = doc[0]
        self.assertEqual(A.read(page.load_annot(xref))["props"]["head_size"], 2.0)
        self.assertAlmostEqual(head_reach(doc, page.load_annot(xref),
                                          pts[1] * page.transformation_matrix), reach, delta=0.05)
        # (moved in place: the same drawing, where it was moved to, its wings whole)
        self.assertTrue(A.shift_in_place(page, xref, P(0, 100)))
        self.assertEqual(stream(doc, page.load_annot(xref)), drawn)
        pix = page.get_pixmap(clip=pymupdf.Rect(250, 270, 300, 330), annots=True)
        rows = {y for x in range(pix.width) for y in range(pix.height) if pix.pixel(x, y)[1] < 150}
        self.assertLess(min(rows), 15)                  # (a wing 18 pt above the line)
        self.assertGreater(max(rows), 45)               # (and one below)

    def test_made_before_reads_100(self):
        doc = pymupdf.open()
        page = doc.new_page()
        a = page.add_line_annot((100, 100), (200, 100))
        a.set_line_ends(0, pymupdf.PDF_ANNOT_LE_OPEN_ARROW)
        a.update()
        self.assertEqual(A.read(a)["props"]["head_size"], 1.0)


class InProperties(unittest.TestCase):
    def test_a_row_for_kinds_with_heads_and_it_applies(self):
        from kanzonas.properties import PropertiesPanel
        panel = PropertiesPanel()
        got = []
        panel.propsChanged.connect(got.append)
        panel.show_target("arrow", dict(A.tool_props("arrow"), head_size=1.5), selected=True)
        w = panel.rows["head_size"][1]
        self.assertFalse(w.isHidden())
        self.assertEqual(w.value(), 150)
        w.setValue(300)
        self.assertEqual(got[-1]["head_size"], 3.0)
        for kind in ("callout", "m_dim", "polyline"):
            panel.show_target(kind, dict(A.tool_props(kind)), selected=True)
            self.assertFalse(panel.rows["head_size"][1].isHidden(), kind)
        panel.show_target("rect", dict(A.tool_props("rect")), selected=True)
        self.assertTrue(panel.rows["head_size"][1].isHidden())


if __name__ == "__main__":
    unittest.main()
