"""Trim on curves (1.7.1, asked for after 1.7: "I should be able to trim between any line
segments or curve segments"): arcs, bent lines (the Curve tool), arrows, circles and
ellipses drawn as markups, the drawing's own curves, and lines a drawing paints as thin
filled bars. What's left of a curve is the same curve, cut exactly where the lines cross.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_trim_curves
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

from kanzonas import annotations as A, curves, page_objects  # noqa: E402
from kanzonas.document_view import DocumentView  # noqa: E402

P = pymupdf.Point


def line(a, b):
    return {"kind": "line", "props": dict(A.DEFAULTS["line"]), "rect": pymupdf.Rect(),
            "points": [P(*a), P(*b)]}


def saved(*models, build=None):
    d = pymupdf.open()
    p = d.new_page(width=600, height=600)
    if build:
        build(p)
    for m in models:
        A.write(p, dict(m, author="Pat", created="D:20260101120000"))
    path = os.path.join(tempfile.mkdtemp(), "curves.pdf")
    d.save(path)
    return path


class Markups(unittest.TestCase):
    def view(self, path):
        v = DocumentView(path)
        self.addCleanup(v.close_doc)
        self.addCleanup(lambda: setattr(v, "dirty", False))
        v.set_zoom(1.0)
        self.said = []
        v.statusMessage.connect(self.said.append)
        return v

    def markups(self, v):
        page = v.doc[0]                 # (kept alive while its markups are read)
        return [A.read(a) for a in A.each_annot(page)]

    def test_an_arc_keeps_its_circle(self):
        arc = {"kind": "arc", "props": dict(A.DEFAULTS["arc"]), "rect": pymupdf.Rect(),
               "points": [P(100, 300), P(300, 100), P(500, 300)]}   # (center 300,300 r 200)
        v = self.view(saved(arc, line((300, 50), (300, 350))))
        self.assertTrue(v.cad_trim(0, P(300 - 200 * math.cos(1.2), 300 - 200 * math.sin(1.2))))
        got = [m for m in self.markups(v) if m["kind"] == "arc"]
        self.assertEqual(len(got), 1)                       # (the left half went)
        for q in curves.path(got[0]):
            self.assertLess(abs(abs(q - P(300, 300)) - 200), 0.05)
        ends = sorted(got[0]["points"][::2], key=lambda q: q.x)
        self.assertLess(abs(ends[0] - P(300, 100)), 0.05)   # (cut right at the line)
        self.assertLess(abs(ends[1] - P(500, 300)), 0.05)

    def test_a_straight_arrow_keeps_its_head_at_the_tip(self):
        arrow = {"kind": "arrow", "props": dict(A.DEFAULTS["arrow"]), "rect": pymupdf.Rect(),
                 "points": [P(100, 200), P(500, 200)]}
        v = self.view(saved(arrow, line((300, 100), (300, 300))))
        self.assertTrue(v.cad_trim(0, P(200, 200)))         # (the tail end goes)
        got = [m for m in self.markups(v) if m["points"][0].y == 200]
        self.assertEqual([m["kind"] for m in got], ["arrow"])
        self.assertLess(abs(got[0]["points"][1] - P(500, 200)), 0.01)
        v = self.view(saved(arrow, line((300, 100), (300, 300))))
        self.assertTrue(v.cad_trim(0, P(400, 200)))         # (the tip goes: a plain line)
        got = [m for m in self.markups(v) if m["points"][0].y == 200]
        self.assertEqual([m["kind"] for m in got], ["line"])

    def test_a_bent_arrow_keeps_its_bend_and_head(self):
        arrow = {"kind": "arrow", "props": dict(A.DEFAULTS["arrow"]), "rect": pymupdf.Rect(),
                 "points": [P(100, 300), P(500, 300)], "bend": P(300, 200)}
        v = self.view(saved(arrow, line((300, 100), (300, 400))))
        path = curves.path(arrow)
        self.assertTrue(v.cad_trim(0, path[len(path) // 4]))
        got = [m for m in self.markups(v) if m.get("bend") is not None]
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["kind"], "arrow")
        # the part left lies on the old curve
        for q in curves.path(got[0]):
            self.assertLess(min(abs(q - r) for r in path), 0.2)

    def test_a_circle_cut_twice_leaves_an_arc_and_once_it_goes(self):
        circle = {"kind": "ellipse", "props": dict(A.DEFAULTS["ellipse"]),
                  "rect": pymupdf.Rect(200, 200, 400, 400)}
        v = self.view(saved(circle, line((150, 300), (450, 300))))
        self.assertTrue(v.cad_trim(0, P(300, 200)))          # (the top half goes)
        got = [m for m in self.markups(v) if m["kind"] == "arc"]
        self.assertEqual(len(got), 1)
        pts = curves.path(got[0])
        self.assertGreater(min(q.y for q in pts), 299.0)     # (the bottom half is left)
        for q in pts:                                        # (on the circle as drawn)
            self.assertLess(abs(abs(q - P(300, 300)) - 100), 0.05)
        v.undo()
        self.assertEqual(sorted(m["kind"] for m in self.markups(v)), ["ellipse", "line"])
        # a line touching it at one place: the circle goes, as in AutoCAD
        v = self.view(saved(circle, line((300, 150), (300, 250))))
        self.assertTrue(v.cad_trim(0, P(400 - 0.5, 300)))
        self.assertEqual([m["kind"] for m in self.markups(v)], ["line"])

    def test_an_ellipse_leaves_a_line_along_it(self):
        e = {"kind": "ellipse", "props": dict(A.DEFAULTS["ellipse"]),
             "rect": pymupdf.Rect(100, 200, 500, 400)}
        v = self.view(saved(e, line((50, 300), (550, 300))))
        self.assertTrue(v.cad_trim(0, P(300, 200)))
        got = [m for m in self.markups(v) if m["kind"] == "polyline"]
        self.assertEqual(len(got), 1)
        self.assertGreater(min(q.y for q in got[0]["points"]), 299.0)
        self.assertGreater(len(got[0]["points"]), 20)        # (it still looks round)


class Drawing(unittest.TestCase):
    def view(self, path):
        v = DocumentView(path)
        self.addCleanup(v.close_doc)
        self.addCleanup(lambda: setattr(v, "dirty", False))
        v.set_zoom(1.0)
        return v

    def test_a_curve_of_the_drawing_stays_a_curve(self):
        def build(p):
            p.draw_bezier((100, 400), (150, 100), (450, 100), (500, 400), color=(0, 0, 1))
            p.draw_line((300, 50), (300, 500), color=(1, 0, 0))
        v = self.view(saved(build=build))
        on = page_objects._cubic_at(P(100, 400), P(150, 100), P(450, 100), P(500, 400), 0.2)
        self.assertTrue(v.cad_trim(0, on))                   # (left of the red line)
        data = page_objects._contents(v.doc[0])
        self.assertIn(b" c", data)                           # (written as a curve again)
        # what's left is the right half of the same curve: it ends on the red line
        v._obj_cache.pop(0, None)
        objs = v.content_objects(0)
        blue = [it for it in objs.items if it["kind"] == "shape" and
                it["rect"].width > 100 and it["rect"].height < 400]
        self.assertTrue(blue)
        self.assertLess(abs(blue[0]["rect"].x0 - 300), 0.5)
        self.assertLess(abs(blue[0]["rect"].x1 - 500), 0.5)
        self.assertLess(abs(blue[0]["rect"].y0 - 175), 0.5)  # (the curve's top, at x 300)

    def test_lines_drawn_as_thin_filled_bars_are_trimmed(self):
        def build(p):
            # a CAD export's lines: long thin filled rectangles, no outline
            p.draw_rect(pymupdf.Rect(100, 199, 500, 201), color=None, fill=(0, 0, 0))
            p.draw_rect(pymupdf.Rect(299, 100, 301, 300), color=None, fill=(0, 0, 0))
        v = self.view(saved(build=build))
        self.assertTrue(v.cad_trim(0, P(200, 200)))          # (left of the crossing bar)
        v._obj_cache.pop(0, None)
        bars = sorted((it["rect"] for it in v.content_objects(0).items),
                      key=lambda r: r.width)
        wide = bars[-1]
        self.assertLess(abs(wide.x0 - 299), 0.05)            # (cut at the other bar's edge)
        self.assertLess(abs(wide.x1 - 500), 0.05)
        self.assertLess(abs(wide.height - 2), 0.05)          # (as thick as before)
        pix = v.doc[0].get_pixmap(dpi=72, alpha=False)
        self.assertEqual(pix.pixel(200, 200)[:3], (255, 255, 255))  # (that part's gone)
        self.assertNotEqual(pix.pixel(400, 200)[:3], (255, 255, 255))


if __name__ == "__main__":
    unittest.main()
