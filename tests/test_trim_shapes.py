"""Trim on rectangle, polygon and cloud markups (the CAD tab's Trim): a click on a side
takes away the part between the nearest cuts on either side, a cut being where another
line crosses it (or a chosen cutting edge) or one of the shape's own corners. A closed
shape with a gap is one open markup from the gap round to the gap: a plain rectangle or
polygon an open polyline, a cloud an open cloud (clouds.py) whose arcs are drawn as they
were, so the sides left look unchanged.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_trim_shapes
"""
import math
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import annotations as A, clouds, markups_panel, pdfcoords, snapping  # noqa: E402
from kanzonas.document_view import DocumentView  # noqa: E402
from kanzonas.print_dialog import print_list  # noqa: E402

P = pymupdf.Point
BOX = pymupdf.Rect(100, 100, 400, 300)
TOP, RIGHT, BOTTOM, LEFT = P(250, 100), P(400, 200), P(250, 300), P(100, 200)
CORNERS = {TOP: (P(100, 100), P(400, 100)), RIGHT: (P(400, 100), P(400, 300)),
           BOTTOM: (P(100, 300), P(400, 300)), LEFT: (P(100, 100), P(100, 300))}
DPI = 144


def cloud_rect(**props):
    return {"kind": "rect", "props": dict(A.DEFAULTS["cloud"], **props), "rect": BOX}


def plain_rect(**props):
    return {"kind": "rect", "props": dict(A.DEFAULTS["rect"], **props), "rect": BOX}


QUAD = [P(100, 100), P(400, 150), P(300, 400), P(150, 350)]


def polygon(cloud=False):
    return {"kind": "polygon", "props": dict(A.DEFAULTS["polygon"], cloud=cloud),
            "points": list(QUAD)}


def saved(*models, lines=(), rotation=0):
    d = pymupdf.open()
    p = d.new_page(width=600, height=600)
    for a, b in lines:
        p.draw_line(a, b)
    for m in models:
        A.write(p, dict(m, author="Pat", created="D:20260101120000"))
    if rotation:
        p.set_rotation(rotation)
    path = os.path.join(tempfile.mkdtemp(), "shapes.pdf")
    d.save(path)
    return path


def near_segment(p, a, b):
    dx, dy = b.x - a.x, b.y - a.y
    L = dx * dx + dy * dy
    t = 0 if L == 0 else max(0, min(1, ((p.x - a.x) * dx + (p.y - a.y) * dy) / L))
    return math.hypot(a.x + t * dx - p.x, a.y + t * dy - p.y)


def compare(before, after, page, skip):
    """(pixels compared, pixels differing by more than 2 levels, the most any differs)
    between two renders of the page, leaving out what is within 13 points of the segments
    in skip (the part trimmed away: its arcs reach about 9 points from its line)."""
    import numpy as np
    z = before.width / page.rect.width
    mat = page.rotation_matrix * pymupdf.Matrix(z, z)
    W, H, k = before.width, before.height, before.n
    a0 = np.frombuffer(before.samples, np.uint8).reshape(H, W, k)[:, :, :3].astype(int)
    a1 = np.frombuffer(after.samples, np.uint8).reshape(H, W, k)[:, :, :3].astype(int)
    d = np.abs(a0 - a1).max(axis=2)
    ys, xs = np.mgrid[0:H, 0:W] + 0.5
    keep = np.ones((H, W), bool)
    for a, b in skip:
        a, b = P(a) * mat, P(b) * mat
        dx, dy = b.x - a.x, b.y - a.y
        L = dx * dx + dy * dy
        t = np.zeros_like(xs) if L == 0 else \
            np.clip(((xs - a.x) * dx + (ys - a.y) * dy) / L, 0, 1)
        keep &= np.hypot(a.x + t * dx - xs, a.y + t * dy - ys) >= 13 * z
    d = d[keep]
    return int(d.size), int((d > 2).sum()), int(d.max()) if d.size else 0


def arc_points(doc, page, xref):
    """Every point of a markup's appearance path (page coordinates)."""
    ap = int(doc.xref_get_key(xref, "AP/N")[1].split()[0])
    back = pdfcoords.to_page(page)
    out = []
    for ln in doc.xref_stream(ap).decode("latin-1").split("\n"):
        t = ln.split()
        if t and t[-1] in ("m", "c"):
            nums = [float(v) for v in t[:-1]]
            out += [P(nums[i], nums[i + 1]) * back for i in range(0, len(nums), 2)]
    return out


class TrimShapes(unittest.TestCase):
    def view(self, path):
        v = DocumentView(path)
        self.addCleanup(v.close_doc)
        self.addCleanup(lambda: setattr(v, "dirty", False))
        v.set_zoom(1.0)
        self.said = []
        v.statusMessage.connect(self.said.append)
        return v

    def markups(self, v):
        page = v.doc[0]
        return [(a.xref, A.read(a)) for a in A.each_annot(page)]

    def picture(self, v):
        return v.doc[0].get_pixmap(dpi=DPI, alpha=False)

    def only(self, v, kind):
        got = self.markups(v)
        self.assertEqual([m["kind"] for _x, m in got], [kind])
        return got[0]

    def assertPoints(self, pts, want):
        self.assertEqual(len(pts), len(want), pts)
        for q, w in zip(pts, want):
            self.assertLess(abs(q - w), 0.01, (pts, want))

    def assertLooksKept(self, before, after, v, skip, allow=8):
        n, bad, worst = compare(before, after, v.doc[0], skip)
        self.assertGreater(n, 100000)
        # (only anti-aliasing: a pixel or a few at an arc's edge, by a few levels)
        self.assertLessEqual(bad, allow, (n, bad, worst))
        self.assertLessEqual(worst, 16, (n, bad, worst))

    # ---- clouds ----------------------------------------------------------------------
    def test_each_side_of_a_cloud_rectangle_goes_corner_to_corner(self):
        for side, (a, b) in CORNERS.items():
            with self.subTest(side=tuple(side)):
                v = self.view(saved(cloud_rect()))
                (old_x, old), = self.markups(v)
                before = self.picture(v)
                self.assertTrue(v.cad_trim(0, side))
                x, m = self.only(v, "opencloud")
                # one open cloud, from the gap round to the gap
                self.assertEqual(len(m["points"]), 4)
                ends = {(round(m["points"][0].x), round(m["points"][0].y)),
                        (round(m["points"][-1].x), round(m["points"][-1].y))}
                self.assertEqual(ends, {(round(a.x), round(a.y)), (round(b.x), round(b.y))})
                self.assertEqual(m["props"]["stroke"], old["props"]["stroke"])
                self.assertAlmostEqual(m["props"]["width"], old["props"]["width"])
                self.assertEqual((m["author"], m["created"]), ("Pat", "D:20260101120000"))
                self.assertTrue(m.get("sides"))
                self.assertLooksKept(before, self.picture(v), v, [(a, b)])

    def test_clicking_again_takes_another_side(self):
        v = self.view(saved(cloud_rect()))
        before = self.picture(v)
        v.cad_trim(0, TOP)
        v.cad_trim(0, RIGHT)
        _x, m = self.only(v, "opencloud")
        self.assertPoints(m["points"], [P(400, 300), P(100, 300), P(100, 100)])
        self.assertLooksKept(before, self.picture(v), v, [CORNERS[TOP], CORNERS[RIGHT]])
        v.cad_trim(0, LEFT)
        _x, m = self.only(v, "opencloud")
        self.assertPoints(m["points"], [P(400, 300), P(100, 300)])
        v.cad_trim(0, BOTTOM)                   # the last side: it all goes
        self.assertEqual(self.markups(v), [])

    def test_kept_sides_look_the_same_wide_and_see_through(self):
        v = self.view(saved(cloud_rect(width=4, opacity=0.5, stroke="#0050ff")))
        before = self.picture(v)
        v.cad_trim(0, LEFT)
        _x, m = self.only(v, "opencloud")
        self.assertAlmostEqual(m["props"]["opacity"], 0.5)
        self.assertLooksKept(before, self.picture(v), v, [CORNERS[LEFT]])

    def test_a_cloud_on_a_turned_page(self):
        v = self.view(saved(cloud_rect(), rotation=90))
        before = self.picture(v)
        v.cad_trim(0, TOP)
        self.only(v, "opencloud")
        self.assertLooksKept(before, self.picture(v), v, [CORNERS[TOP]])

    def test_a_crossing_line_cuts_a_side_and_the_arcs_left_stay_put(self):
        v = self.view(saved(cloud_rect(), lines=[((250, 50), (250, 150))]))
        before = self.picture(v)
        v.cad_trim(0, P(170, 100))              # from the top left corner to the line
        _x, m = self.only(v, "opencloud")
        self.assertPoints(m["points"], [P(250, 100), P(400, 100), P(400, 300), P(100, 300),
                                        P(100, 100)])
        self.assertLooksKept(before, self.picture(v), v, [(P(100, 100), P(250, 100))])
        v.cad_trim(0, P(330, 100))              # then from the line to the other corner
        _x, m = self.only(v, "opencloud")
        self.assertPoints(m["points"], [P(400, 100), P(400, 300), P(100, 300), P(100, 100)])

    def test_chosen_cutting_edges(self):
        v = self.view(saved(cloud_rect(), lines=[((180, 50), (180, 150))]))
        edge = [[P(250, 50), P(250, 150)]]     # (the drawing's line at 180 is not an edge)
        self.assertTrue(v.cad_trim(0, P(330, 100), edge))
        _x, m = self.only(v, "opencloud")
        self.assertPoints(m["points"], [P(400, 100), P(400, 300), P(100, 300), P(100, 100),
                                        P(250, 100)])
        # a side crossing no cutting edge stays
        self.assertFalse(v.cad_trim(0, BOTTOM, [[P(500, 50), P(500, 150)]]))
        self.assertIn("doesn't cross a cutting edge", self.said[-1])

    def test_a_cloud_polygon(self):
        v = self.view(saved(polygon(cloud=True)))
        before = self.picture(v)
        v.cad_trim(0, P(250, 125))              # the side from (100, 100) to (400, 150)
        _x, m = self.only(v, "opencloud")
        self.assertPoints(m["points"], [P(400, 150), P(300, 400), P(150, 350), P(100, 100)])
        # (PyMuPDF closes the last arc of a cloud polygon with a straight line across the
        # bump at its first point; the open cloud draws that bump without it: left out)
        n, bad, worst = compare(before, self.picture(v), v.doc[0],
                                [(QUAD[0], QUAD[1]), (QUAD[0], QUAD[0] + (0.1, 0))])
        self.assertLessEqual(bad, 40, (n, bad, worst))
        self.assertLessEqual(worst, 16, (n, bad, worst))
        v.cad_trim(0, P(350, 275))
        _x, m = self.only(v, "opencloud")
        self.assertPoints(m["points"], [P(300, 400), P(150, 350), P(100, 100)])

    def test_a_cloud_ellipse_is_cut_where_lines_cross(self):
        e = {"kind": "ellipse", "props": dict(A.DEFAULTS["ellipse"], cloud=True), "rect": BOX}
        v = self.view(saved(e, lines=[((150, 50), (150, 350)), ((350, 50), (350, 350))]))
        before = self.picture(v)
        self.assertTrue(v.cad_trim(0, P(250, 100)))
        _x, m = self.only(v, "opencloud")
        self.assertFalse(m.get("sides"))        # (its points aren't corners)
        # (the top of the ellipse between the lines went)
        top = [P(250 + 150 * math.cos(t), 200 - 100 * math.sin(t))
               for t in [math.acos(100 / 150) + k * (math.pi - 2 * math.acos(100 / 150)) / 20
                         for k in range(21)]]
        n, bad, worst = compare(before, self.picture(v), v.doc[0], list(zip(top, top[1:])))
        self.assertLessEqual(bad, 30, (n, bad, worst))
        self.assertLessEqual(worst, 16, (n, bad, worst))

    def test_a_plain_ellipse_and_a_filled_shape_say_why_not(self):
        e = {"kind": "ellipse", "props": dict(A.DEFAULTS["ellipse"]), "rect": BOX}
        v = self.view(saved(e))
        self.assertFalse(v.cad_trim(0, P(250, 100)))
        self.assertIn("ellipse", self.said[-1])
        v = self.view(saved(plain_rect(fill="#ffff00")))
        self.assertFalse(v.cad_trim(0, TOP))
        self.assertIn("filled", self.said[-1])

    def test_a_click_on_a_corner_asks_for_a_side(self):
        v = self.view(saved(cloud_rect()))
        self.assertFalse(v.cad_trim(0, P(100, 100)))
        self.assertIn("corner", self.said[-1])
        self.only(v, "rect")

    def test_the_bumps_are_in_reach(self):
        v = self.view(saved(cloud_rect()))
        self.assertTrue(v.cad_trim(0, P(250, 92)))      # on a bump above the top side
        self.only(v, "opencloud")

    # ---- plain shapes -----------------------------------------------------------------
    def test_a_plain_rectangle_becomes_an_open_polyline(self):
        v = self.view(saved(plain_rect(width=3, opacity=0.7)))
        before = self.picture(v)
        self.assertTrue(v.cad_trim(0, TOP))
        _x, m = self.only(v, "polyline")
        self.assertEqual(len(m["points"]), 4)
        self.assertEqual(m["props"]["stroke"], A.DEFAULTS["rect"]["stroke"])
        self.assertAlmostEqual(m["props"]["width"], 3)
        self.assertAlmostEqual(m["props"]["opacity"], 0.7)
        self.assertEqual((m["author"], m["created"]), ("Pat", "D:20260101120000"))
        self.assertLooksKept(before, self.picture(v), v, [CORNERS[TOP]])
        v.cad_trim(0, LEFT)                     # its corners still cut
        _x, m = self.only(v, "polyline")
        self.assertEqual(len(m["points"]), 3)

    def test_a_plain_polygon(self):
        v = self.view(saved(polygon()))
        self.assertTrue(v.cad_trim(0, P(250, 125)))
        _x, m = self.only(v, "polyline")
        self.assertEqual(sorted((round(q.x), round(q.y)) for q in m["points"]),
                         sorted((round(q.x), round(q.y)) for q in QUAD))

    def test_a_crossing_line_cuts_a_plain_rectangle(self):
        v = self.view(saved(plain_rect(), lines=[((250, 50), (250, 150))]))
        v.cad_trim(0, P(330, 100))
        _x, m = self.only(v, "polyline")
        self.assertEqual({(round(m["points"][0].x), round(m["points"][0].y)),
                          (round(m["points"][-1].x), round(m["points"][-1].y))},
                         {(400, 100), (250, 100)})

    # ---- undo, save, edit --------------------------------------------------------------
    def test_undo_brings_the_closed_cloud_back_exactly_in_one_step(self):
        v = self.view(saved(cloud_rect()))
        (x, _m), = self.markups(v)
        obj = v.doc.xref_object(x)
        before = self.picture(v)
        steps = len(v._undo)
        v.cad_trim(0, TOP)
        trimmed = self.picture(v)
        self.assertEqual(len(v._undo), steps + 1)
        v.undo()
        (x2, m), = self.markups(v)
        self.assertEqual((x2, m["kind"], m["props"]["cloud"]), (x, "rect", True))
        self.assertEqual(v.doc.xref_object(x), obj)
        self.assertEqual(self.picture(v).samples, before.samples)
        v.redo()
        self.only(v, "opencloud")
        self.assertEqual(self.picture(v).samples, trimmed.samples)

    def test_saved_and_opened_again_it_is_still_an_open_cloud(self):
        v = self.view(saved(cloud_rect()))
        v.cad_trim(0, TOP)
        _x, m = self.only(v, "opencloud")
        pic = self.picture(v)
        out = os.path.join(tempfile.mkdtemp(), "trimmed.pdf")
        v.doc.save(out)
        v2 = self.view(out)
        _x, m2 = self.only(v2, "opencloud")
        self.assertTrue(A._same(m2["cloud"], clouds.cloud_of(m)))
        self.assertEqual(self.picture(v2).samples, pic.samples)
        # (another viewer draws its appearance: there, as everywhere, it reads as a cloud)
        rows = markups_panel.collect(v2.doc)
        self.assertEqual([r[2] for r in rows], [A.LABELS["opencloud"]])
        self.assertEqual(A.LABELS["opencloud"], A.LABELS["cloud"])
        v2.cad_trim(0, RIGHT)                   # and trims on
        _x, m3 = self.only(v2, "opencloud")
        self.assertEqual(len(m3["points"]), 3)

    def test_moved_in_place(self):
        v = self.view(saved(cloud_rect()))
        v.cad_trim(0, TOP)
        x, m = self.only(v, "opencloud")
        before = self.picture(v)
        v._set_selection(0, [x])
        v.cad_apply("Moved", pymupdf.Matrix(1, 0, 0, 1, 20, 10))
        x2, m2 = self.only(v, "opencloud")
        self.assertEqual(x2, x)                 # the same markup, moved where it is
        after = self.picture(v)
        sx, sy = 40, 20
        diff = 0
        for y in range(0, before.height - sy, 2):
            for xx in range(0, before.width - sx, 2):
                if before.pixel(xx, y) != after.pixel(xx + sx, y + sy):
                    diff += 1
        self.assertEqual(diff, 0)

    def transformed_arcs(self, mat, mirror=False):
        v = self.view(saved(cloud_rect()))
        v.cad_trim(0, TOP)
        x, m = self.only(v, "opencloud")
        page = v.doc[0]
        old = arc_points(v.doc, page, x)
        del page
        v._set_selection(0, [x])
        v.cad_apply("Changed", mat)
        x2, m2 = self.only(v, "opencloud")
        self.assertEqual(clouds.cloud_of(m2)["flip"], mirror)
        page = v.doc[0]
        new = arc_points(v.doc, page, x2)
        # the arcs are the old ones turned (or mirrored) exactly: the bumps stay outside
        self.assertEqual(len(new), len(old))
        want = sorted((round((q * mat).x, 1), round((q * mat).y, 1)) for q in old)
        got = sorted((round(q.x, 1), round(q.y, 1)) for q in new)
        far = sum(1 for a, b in zip(want, got) if abs(a[0] - b[0]) + abs(a[1] - b[1]) > 0.25)
        self.assertEqual(far, 0)

    def test_turned_the_arcs_turn_with_it(self):
        c = P(250, 200)
        self.transformed_arcs(pymupdf.Matrix(1, 0, 0, 1, -c.x, -c.y) * pymupdf.Matrix(90) *
                              pymupdf.Matrix(1, 0, 0, 1, c.x, c.y))

    def test_mirrored_the_bumps_stay_outside(self):
        c = P(250, 200)
        self.transformed_arcs(pymupdf.Matrix(1, 0, 0, 1, -c.x, -c.y) *
                              pymupdf.Matrix(-1, 0, 0, 1, 0, 0) *
                              pymupdf.Matrix(1, 0, 0, 1, c.x, c.y), mirror=True)

    def test_restyled(self):
        v = self.view(saved(cloud_rect()))
        v.cad_trim(0, TOP)
        x, m = self.only(v, "opencloud")
        new = A.copy(m)
        new["props"].update(stroke="#0050ff", width=3.0)
        v.commit_models(0, [(x, new)])
        x2, m2 = self.only(v, "opencloud")
        self.assertEqual(m2["props"]["stroke"], "#0050ff")
        page = v.doc[0]
        ap = int(v.doc.xref_get_key(x2, "AP/N")[1].split()[0])
        stream = v.doc.xref_stream(ap).decode()
        self.assertIn("3 w", stream)
        self.assertIn("0 .3137255 1 RG", stream)
        self.assertGreater(stream.count(" c\n"), 50)
        # wider arcs, as a cloud that wide has them
        spacing, radius = clouds.sizes(2, 3.0)
        pts = arc_points(v.doc, page, x2)
        self.assertLess(max(near_segment(q, P(100, 300), P(400, 300)) for q in pts
                            if 150 < q.x < 350 and q.y > 250), radius + 2)

    # ---- found, listed, printed, flattened ---------------------------------------------
    def test_selected_snapped_and_outlined_like_a_polyline(self):
        v = self.view(saved(cloud_rect()))
        v.cad_trim(0, TOP)
        x, m = self.only(v, "opencloud")
        self.assertEqual(v.annot_at(0, P(250, 300)), x)       # on its line
        self.assertEqual(v.annot_at(0, P(250, 307)), x)       # on a bump below it
        self.assertIsNone(v.annot_at(0, P(250, 200)))         # inside: not on it
        self.assertIsNone(v.annot_at(0, P(250, 100)))         # where the top side was
        outline, = v.cad_outlines(0, "markups", [(x, m)])
        self.assertPoints(outline, m["points"])
        snaps = snapping.markup_points(m)
        self.assertTrue(any(abs(q - P(100, 300)) < 0.01 for q in snaps))
        self.assertEqual(A.bounds(m), pymupdf.Rect(100, 100, 400, 300))

    def test_printed_and_flattened_as_shown(self):
        v = self.view(saved(cloud_rect()))
        v.cad_trim(0, TOP)
        shown = self.picture(v)
        printed = print_list(v.doc[0]).get_pixmap(matrix=pymupdf.Matrix(2, 2), alpha=False)
        self.assertEqual(printed.samples, shown.samples)
        v.flatten([0])
        self.assertEqual(self.markups(v), [])
        flat = self.picture(v)
        n, bad, worst = compare(shown, flat, v.doc[0], [])
        self.assertLessEqual(bad, 20, (n, bad, worst))
        v.undo()
        v.flatten()
        flat = self.picture(v)
        n, bad, worst = compare(shown, flat, v.doc[0], [])
        self.assertLessEqual(bad, 20, (n, bad, worst))


if __name__ == "__main__":
    unittest.main()
