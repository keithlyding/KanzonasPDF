"""Arrange > Group / Ungroup and Flip horizontally / vertically (1.12, the owner, 11 Nov, from
the Bluebeam comparison; grouping was also asked for in issue #82). A group is the standard
PDF one (/IRT to the primary markup and /RT /Group, which Acrobat reads too): a click on one
markup selects the group; it moves, restyles and deletes together and stays a group through
restyling (markups written anew) and saving; one undo step each. Flip mirrors the selection
across its middle as the page is shown.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_group_flip
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
from kanzonas.document_view import DocumentView  # noqa: E402

R = pymupdf.Rect
P = pymupdf.Point


def sheet(rotation=0):
    d = pymupdf.open()
    pg = d.new_page(width=612, height=792)
    for r in (R(100, 100, 160, 140), R(300, 100, 330, 140), R(100, 400, 160, 440)):
        A.write(pg, {"kind": "rect", "rect": r, "text": "", "props": dict(A.DEFAULTS["rect"])})
    A.write(pg, {"kind": "line", "rect": R(), "text": "", "points": [P(100, 600), P(200, 650)],
                 "props": dict(A.DEFAULTS["line"])})
    if rotation:
        pg.set_rotation(rotation)
    path = os.path.join(tempfile.mkdtemp(), "g.pdf")
    d.save(path)
    return path


class Group(unittest.TestCase):
    def setUp(self):
        self.v = DocumentView(sheet())
        self.addCleanup(self.v.close_doc)

    def xrefs(self):
        return [a.xref for a in self.v.doc[0].annots()]

    def rect_of(self, xref):
        page = self.v.doc[0]
        return R(page.load_annot(xref).rect)

    def group_first_two(self):
        a, b = self.xrefs()[:2]
        self.v.select_xref(0, a)
        self.v.select_xref(0, b, add=True)
        self.assertTrue(self.v.can_group())
        self.assertTrue(self.v.group_selection())
        return a, b

    def test_grouped_the_standard_way_and_selected_together(self):
        a, b = self.group_first_two()
        doc = self.v.doc
        self.assertEqual(doc.xref_get_key(b, "IRT"), ("xref", "%d 0 R" % a))
        self.assertEqual(doc.xref_get_key(b, "RT"), ("name", "/Group"))
        self.assertEqual(doc.xref_get_key(a, "IRT")[0], "null")
        self.assertFalse(self.v.can_group())
        self.assertTrue(self.v.can_ungroup())
        third = self.xrefs()[2]
        self.v.select_xref(0, b)                                # a click on one: both
        self.assertEqual(sorted(self.v.selected_xrefs()), sorted([a, b]))
        self.v.select_xref(0, third, add=True)
        self.assertEqual(len(self.v.selected_xrefs()), 3)
        self.v.select_xref(0, a, add=True)                      # the group comes off whole
        self.assertEqual(self.v.selected_xrefs(), [third])
        # saved and opened again (and by PyMuPDF alone): still a group
        out = os.path.join(tempfile.mkdtemp(), "saved.pdf")
        self.v.doc.save(out)
        d = pymupdf.open(out)
        self.assertEqual(d.xref_get_key(b, "RT"), ("name", "/Group"))

    def test_moves_restyles_and_deletes_together(self):
        a, b = self.group_first_two()
        ra, rb = self.rect_of(a), self.rect_of(b)
        self.v.select_xref(0, a)
        self.assertTrue(self.v.nudge(1, 0, 10))
        xs = self.v.selected_xrefs()
        self.assertEqual(len(xs), 2)
        moved = sorted(self.rect_of(x).x0 for x in xs)
        self.assertAlmostEqual(moved[0], min(ra.x0, rb.x0) + 10, delta=0.5)
        self.assertAlmostEqual(moved[1], max(ra.x0, rb.x0) + 10, delta=0.5)
        # restyled: written anew, still one group (the members follow the new primary)
        self.v.update_selected_props({"width": 4.0})
        xs = self.v.selected_xrefs()
        t = self.v.threads(0)
        self.assertEqual(len({t.group_primary(x) for x in xs}), 1)
        self.assertEqual(sorted(t.group(xs[0])), sorted(xs))
        self.v.select_xref(0, xs[-1])
        self.assertEqual(sorted(self.v.selected_xrefs()), sorted(xs))
        self.v.delete_selected()
        self.assertEqual(len(self.xrefs()), 2)

    def test_ungroup_and_undo(self):
        a, b = self.group_first_two()
        self.v.undo()
        self.assertEqual(self.v.doc.xref_get_key(b, "RT")[0], "null")
        self.v.redo()
        self.assertEqual(self.v.doc.xref_get_key(b, "RT"), ("name", "/Group"))
        self.v.select_xref(0, b)
        self.assertTrue(self.v.ungroup_selection())
        self.v.select_xref(0, b)
        self.assertEqual(self.v.selected_xrefs(), [b])          # on its own again
        self.assertEqual(self.v.doc.xref_get_key(b, "IRT")[0], "null")

    def test_copies_of_a_group_are_a_group(self):
        a, b = self.group_first_two()
        self.v.select_xref(0, a)
        self.assertEqual(self.v.duplicate_selected(), 2)
        copies = self.v.selected_xrefs()
        self.assertEqual(len(copies), 2)
        self.assertFalse(set(copies) & {a, b})
        t = self.v.threads(0)
        self.assertEqual(len({t.group_primary(x) for x in copies}), 1)     # a group of its own
        self.assertNotIn(t.group_primary(copies[0]), (a, b))
        # copied and pasted: a group again
        self.v.select_xref(0, a)
        self.assertEqual(self.v.copy(), "markups")
        self.assertEqual(self.v.paste(), "markups")
        pasted = self.v.selected_xrefs()
        t = self.v.threads(0)
        self.assertEqual(len(pasted), 2)
        self.assertEqual(len({t.group_primary(x) for x in pasted}), 1)
        self.v.select_xref(0, pasted[1])
        self.assertEqual(sorted(self.v.selected_xrefs()), sorted(pasted))

    def test_replies_are_not_groups(self):
        from kanzonas import review
        a = self.xrefs()[0]
        page = self.v.doc[0]
        self.v.modify(lambda: review.add_reply(page, a, "A reply", "Tester"), [0])
        self.v.select_xref(0, a)
        self.assertEqual(self.v.selected_xrefs(), [a])
        self.assertFalse(self.v.can_ungroup())


class Flip(unittest.TestCase):
    def view(self, rotation=0):
        v = DocumentView(sheet(rotation))
        self.addCleanup(v.close_doc)
        return v

    def line_points(self, v):
        page = v.doc[0]                     # (kept alive while its markup is read)
        line = next(a for a in page.annots() if a.type[0] == pymupdf.PDF_ANNOT_LINE)
        return [P(p) for p in line.vertices]

    def test_a_line_flips_left_for_right(self):
        v = self.view()
        line = next(a.xref for a in v.doc[0].annots() if a.type[0] == pymupdf.PDF_ANNOT_LINE)
        v.select_xref(0, line)
        self.assertTrue(v.flip_selection(True))
        pts = sorted((round(p.x), round(p.y)) for p in self.line_points(v))
        self.assertEqual(pts, [(100, 650), (200, 600)])
        v.undo()
        pts = sorted((round(p.x), round(p.y)) for p in self.line_points(v))
        self.assertEqual(pts, [(100, 600), (200, 650)])
        line = next(a.xref for a in v.doc[0].annots() if a.type[0] == pymupdf.PDF_ANNOT_LINE)
        v.select_xref(0, line)
        self.assertTrue(v.flip_selection(False))
        pts = sorted((round(p.x), round(p.y)) for p in self.line_points(v))
        self.assertEqual(pts, [(100, 650), (200, 600)])

    def test_a_group_flips_as_one(self):
        v = self.view()
        a, b = [x.xref for x in v.doc[0].annots()][:2]     # boxes at x 100-160 and 300-360
        v.select_xref(0, a)
        v.select_xref(0, b, add=True)
        v.group_selection()
        def tops():
            page = v.doc[0]
            return {an.xref: R(an.rect) for an in page.annots()
                    if an.type[0] == pymupdf.PDF_ANNOT_SQUARE and an.rect.y0 < 200}
        before = tops()
        v.select_xref(0, a)
        v.flip_selection(True)
        after = tops()
        # mirrored across the middle of the two (they span 100-330: x 215): the wide box
        # (100-160) goes to 270-330, the narrow one (300-330) to 100-130 (each box one point
        # wider with its border)
        wide = max(after.values(), key=lambda r: r.width)
        narrow = min(after.values(), key=lambda r: r.width)
        self.assertEqual(len(before), 2)
        self.assertAlmostEqual(wide.x0, 269, delta=1.5)
        self.assertAlmostEqual(narrow.x0, 99, delta=1.5)
        t = v.threads(0)
        sel = v.selected_xrefs()
        self.assertEqual(len({t.group_primary(x) for x in sel}), 1)     # still a group

    def test_horizontal_as_the_page_is_shown(self):
        v = self.view(90)
        line = next(a.xref for a in v.doc[0].annots() if a.type[0] == pymupdf.PDF_ANNOT_LINE)
        v.select_xref(0, line)
        rot = v.doc[0].rotation_matrix
        before = sorted((round((p * rot).x), round((p * rot).y)) for p in self.line_points(v))
        v.flip_selection(True)
        after = sorted((round((p * rot).x), round((p * rot).y)) for p in self.line_points(v))
        # as shown: same x span and same y values, the ends swapped left for right
        self.assertEqual(sorted(x for x, _ in before), sorted(x for x, _ in after))
        self.assertEqual(sorted(y for _, y in before), sorted(y for _, y in after))
        self.assertNotEqual(before, after)


if __name__ == "__main__":
    unittest.main()
