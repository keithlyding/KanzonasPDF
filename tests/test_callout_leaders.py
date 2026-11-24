"""Callout leaders (the owner, 23 Nov 2026: "add leaders to callouts", as Bluebeam's Add
Leader): a callout with more than one leader, each with the first one's arrowhead, drawn in
its appearance so other viewers show them; added and removed from the right-click menu,
moved by their grips, kept when saved, opened, moved and resized; one undo step each.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_callout_leaders
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
from tests.test_interaction_112 import Window, pump  # noqa: E402

P = pymupdf.Point
BOX = pymupdf.Rect(200, 300, 320, 340)
TIPS = [P(100, 200), P(450, 200), P(260, 520)]


def callout(page, tips=TIPS, **props):
    p = dict(A.tool_props("callout"), stroke="#ff0000", **props)
    return A.write(page, {"kind": "callout", "props": p, "text": "Leaders",
                          "rect": pymupdf.Rect(BOX), "points": [P(q) for q in tips]})


def inked(page, at, r=4):
    """True when something red is drawn within r points of at."""
    pix = page.get_pixmap(clip=pymupdf.Rect(at.x - r, at.y - r, at.x + r, at.y + r),
                          annots=True)
    return any(pix.pixel(x, y)[1] < 150 for x in range(pix.width) for y in range(pix.height))


def head_points(doc, annot):
    """The paths of the callout's appearance (the leaders and their heads), as point lists."""
    ap = int(doc.xref_get_key(annot.xref, "AP/N")[1].split()[0])
    lines = doc.xref_stream(ap).split(b"\n")
    out = []
    for i0, i1 in A._path_blocks(lines):
        nums = [float(x) for ln in lines[i0:i1] for x in A._NUMBER.findall(ln.decode())]
        out.append([P(nums[k], nums[k + 1]) for k in range(0, len(nums) - 1, 2)])
    return out


class Drawn(unittest.TestCase):
    def test_each_leader_drawn_with_the_first_ones_head(self):
        doc = pymupdf.open()
        page = doc.new_page()
        a = callout(page)
        for q in TIPS:
            self.assertTrue(inked(page, q), q)
        # 3 leaders and 3 heads, each head as long as the first one's
        paths = head_points(doc, a)
        self.assertEqual(len(paths), 6)
        to_pdf = page.transformation_matrix
        size = []
        for q in TIPS:
            tip = q * to_pdf
            heads = [p for p in paths if len(p) >= 3 and min(abs(r - tip) for r in p) < 0.5]
            self.assertEqual(len(heads), 1, q)
            size.append(max(abs(r - tip) for r in heads[0]))
        self.assertAlmostEqual(min(size), max(size), delta=0.05)
        # (the box holds them all: nothing cut off)
        for q in TIPS:
            self.assertTrue(a.rect.contains(q))

    def test_the_arrowhead_size_and_kind_go_to_every_leader(self):
        doc = pymupdf.open()
        page = doc.new_page()
        small = head_points(doc, callout(page))
        big = head_points(doc, callout(doc.new_page(), head_size=3.0))
        self.assertEqual(len(small), len(big))
        tip = TIPS[2] * doc[0].transformation_matrix     # (a fresh Page: pages were added)

        def reach(paths):
            return max(abs(r - tip) for p in paths if len(p) >= 3 and
                       min(abs(r - tip) for r in p) < 0.5 for r in p)
        self.assertAlmostEqual(reach(big) / reach(small), 3.0, delta=0.05)
        callout(doc.new_page(), head="closed")
        self.assertTrue(inked(doc[2], TIPS[1]))

    def test_one_leader_is_drawn_as_before(self):
        doc = pymupdf.open()
        page = doc.new_page()
        a = callout(page, tips=TIPS[:1])
        self.assertEqual(len(head_points(doc, a)), 2)
        self.assertNotIn("leaders", doc.xref_get_key(a.xref, "KZProps")[1])


class Kept(unittest.TestCase):
    def test_saved_opened_moved_and_resized(self):
        path = os.path.join(tempfile.mkdtemp(), "leaders.pdf")
        doc = pymupdf.open()
        xref = callout(doc.new_page()).xref
        doc.save(path)
        doc = pymupdf.open(path)
        page = doc[0]
        m = A.read(page.load_annot(xref))
        self.assertEqual([tuple(q) for q in m["points"]], [tuple(q) for q in TIPS])
        # moved in place: its drawing along, the leaders it keeps too
        self.assertTrue(A.shift_in_place(page, xref, P(30, 40)))
        m = A.read(page.load_annot(xref))
        self.assertEqual([tuple(q) for q in m["points"]],
                         [tuple(q + (30, 40)) for q in TIPS])
        for q in TIPS:
            self.assertTrue(inked(page, q + (30, 40)), q)
        # its box resized: the leaders still point where they did
        r = A.resized(m, pymupdf.Rect(m["rect"]) + (0, 0, 60, 30))
        self.assertEqual(r["points"], m["points"])
        moved = A.moved(m, P(5, 5))
        self.assertEqual(moved["points"], [q + (5, 5) for q in m["points"]])


class InTheApp(Window):
    def setUp(self):
        self.open(lambda pg: callout(pg, tips=TIPS[:1]))
        page = self.v.doc[0]
        xref = next(x for x, kind, *_ in page.annot_xrefs()
                    if kind == pymupdf.PDF_ANNOT_FREE_TEXT)
        self.v.select_xref(0, xref)
        pump()

    def leaders(self):
        page = self.v.doc[0]          # (kept while its markups are read)
        a = next(a for a in page.annots() if a.type[0] == pymupdf.PDF_ANNOT_FREE_TEXT)
        return A.read(a)["points"]

    def test_add_and_remove_leaders_each_one_undo_step(self):
        v = self.v
        self.assertIsNotNone(v.selected_callout())
        self.assertTrue(v.add_callout_leader(P(450, 200)))
        self.assertEqual(len(v.selected_model["points"]), 2)
        self.assertTrue(v.add_callout_leader(P(260, 520)))
        self.assertEqual([tuple(q) for q in v.selected_model["points"]],
                         [tuple(q) for q in TIPS])
        self.assertTrue(inked(v.doc[0], P(260, 520)))
        # right-clicked on its box: pointing away from the box, across from the first
        self.assertTrue(v.add_callout_leader(P(250, 320)))
        last = v.selected_model["points"][-1]
        self.assertFalse((BOX + (-4, -4, 4, 4)).contains(last))
        self.assertGreater(last.x, BOX.x1)                  # (the first points left)
        # the nearest added one removed; the first can't be
        self.assertTrue(v.remove_callout_leader(P(440, 210)))
        self.assertEqual([tuple(q) for q in v.selected_model["points"][:2]],
                         [tuple(TIPS[0]), tuple(TIPS[2])])
        w = self.w
        for n in (4, 3, 2, 1):
            w.a_undo.trigger()
            pump()
            self.assertEqual(len(self.leaders()), n)

    def test_each_leader_has_its_grip(self):
        v = self.v
        v.add_callout_leader(P(450, 200))
        pump()
        handles = v.pages[0]._handles(v.selected_model)
        self.assertIn("p0", handles)
        self.assertIn("p1", handles)
        # dragged, as the grip does: that leader alone points elsewhere
        m = A.with_endpoint(v.selected_model, 1, P(470, 180))
        self.assertEqual(m["points"][0], v.selected_model["points"][0])
        self.assertEqual(m["points"][1], P(470, 180))


if __name__ == "__main__":
    unittest.main()
