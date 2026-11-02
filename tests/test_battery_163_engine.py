"""Break-it tests for 1.6.3's engine: the new markup kinds (circle, mask, arc, curve, bent lines,
trimmed shapes and open clouds, click-click drawing) through undo, the content renders and the
speed budgets.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_battery_163_engine
"""
import os
import random
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402
from PySide6.QtCore import QPointF  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import annotations as A  # noqa: E402
from kanzonas import cad_select, page_objects  # noqa: E402
from kanzonas.document_view import DocumentView  # noqa: E402

P = pymupdf.Point


def sheet(n, seed=7):
    """A drawing of n short lines (as a CAD export's), saved; its path."""
    rnd = random.Random(seed)
    out = [b"1 0 0 -1 0 800 cm 0.35 w 0.2 0.4 0.1 RG"]
    for _ in range(n):
        x, y = rnd.uniform(20, 1100), rnd.uniform(20, 700)
        out.append(b"%.2f %.2f m %.2f %.2f l S" % (x, y, x + rnd.uniform(-40, 40), y))
    d = pymupdf.open()
    pg = d.new_page(width=1200, height=800)
    x = d.get_new_xref()
    d.update_object(x, "<<>>")
    d.update_stream(x, b"\n".join(out))
    pg.set_contents(x)
    path = os.path.join(tempfile.mkdtemp(), "sheet.pdf")
    d.save(path, deflate=True)
    d.close()
    return path


def best_of(fn, n=5):
    fn()
    best = 1e9
    for _ in range(n):
        t = time.perf_counter()
        fn()
        best = min(best, time.perf_counter() - t)
    return best


class Speed(unittest.TestCase):
    """What's drawn on each paint in CAD mode stays quick (1.6.2's times in brackets)."""

    def setUp(self):
        for key in ("mouse_mode", "cad_select"):
            self.addCleanup(setattr, DocumentView, key, getattr(DocumentView, key))
        DocumentView.mouse_mode = "cad"
        DocumentView.cad_select = True

    def view(self, path):
        v = DocumentView(path)
        self.addCleanup(lambda: (setattr(v, "dirty", False), v.doc.is_closed or v.close_doc()))
        self.addCleanup(v.hide)
        v.resize(1300, 900)
        v.show()
        APP.processEvents()
        v.set_zoom(1.0)
        APP.processEvents()
        v.set_tool("editobjects")
        return v

    def test_a_big_selection_of_drawing_objects_repaints_quickly(self):
        # 1.6.3 drew the selection dashed over a white line with round ends: Qt strokes a
        # path of many pieces with round ends very slowly (2,500 lines: 380 ms a paint, on
        # every hover or repaint while they were selected) [3 ms]
        v = self.view(sheet(6000))
        items = v.cad_objects(0, page_objects.Box(pymupdf.Rect(-5, -5, 1300, 900)), False)
        v.select_objects(0, items[:2500])
        w = v.pages[0]
        took = best_of(w.repaint)
        self.assertLess(took, 0.06, "%.0f ms a paint" % (took * 1000))

    def test_many_markups_selected_in_cad_mode_repaint_quickly(self):
        # (1,000 ms a paint in 1.6.3 for 2,000 selected markups, the same round ends) [72 ms]
        d = pymupdf.open()
        pg = d.new_page()
        for i in range(2000):
            x, y = 20 + (i % 40) * 14, 20 + (i // 40) * 15
            pg.add_rect_annot(pymupdf.Rect(x, y, x + 10, y + 10))
        path = os.path.join(tempfile.mkdtemp(), "marks.pdf")
        d.save(path)
        v = self.view(path)
        page = v.doc[0]
        xs = [a.xref for a in A.each_annot(page)]
        del page
        v._set_selection(0, xs)
        took = best_of(v.pages[0].repaint)
        self.assertLess(took, 0.15, "%.0f ms a paint" % (took * 1000))

    def test_many_curved_markups_selected_repaint_quickly(self):
        # each paint drew every selected markup's box, worked out from its curve point by
        # point (a curve's box: hundreds of points through PyMuPDF's Rect): 300 selected
        # arcs took 140 ms a paint, 300 straight lines 15 ms
        DocumentView.mouse_mode = "standard"
        DocumentView.cad_select = False
        d = pymupdf.open()
        pg = d.new_page(width=1200, height=900)
        for k in range(300):
            x, y = 60 + (k % 30) * 36, 60 + (k // 30) * 36
            if k % 2:
                A.write(pg, {"kind": "arc", "props": dict(A.DEFAULTS["arc"]),
                             "points": [P(x, y), P(x + 15, y - 12), P(x + 30, y)]})
            else:
                A.write(pg, {"kind": "line", "props": dict(A.DEFAULTS["line"]),
                             "points": [P(x, y), P(x + 30, y)], "bend": P(x + 15, y - 12)})
        path = os.path.join(tempfile.mkdtemp(), "curves.pdf")
        d.save(path)
        v = self.view(path)
        v.set_tool("select")
        page = v.doc[0]
        xs = [a.xref for a in A.each_annot(page)]
        del page
        v._set_selection(0, xs)
        took = best_of(v.pages[0].repaint)
        self.assertLess(took, 0.06, "%.0f ms a paint" % (took * 1000))
        # (the box is still the curve's)
        m = v.selected_models()[1][1]
        from kanzonas import curves
        pts = curves.path(m)
        want = pymupdf.Rect(min(q.x for q in pts), min(q.y for q in pts),
                            max(q.x for q in pts), max(q.y for q in pts))
        self.assertLess(max(abs(a - b) for a, b in zip(A.bounds(m), want)), 1e-9)

    def test_the_box_preview_glow_on_a_heavy_sheet(self):
        # the glow over what a box would take is drawn again on every pointer move: each
        # point was put on the screen by loading the page again (3,000 lines: 330 ms a
        # paint, 370 ms in 1.6.2); a 15,000-piece command preview has 80 ms
        v = self.view(sheet(20000))
        w = v.pages[0]
        lines = []
        for got, _rects in v.cad_preview_steps(0, page_objects.Box(
                pymupdf.Rect(-5, -5, 1300, 900)), False):
            lines += got
        self.assertGreaterEqual(len(lines), cad_select.LIMIT)
        w._cad_down = {"start": QPointF(1, 1), "pts": [QPointF(1, 1)], "dir": 1,
                       "mode": "box", "now": QPointF(1250, 850), "target": None,
                       "remove": False, "t": 0, "link": False}
        self.addCleanup(setattr, w, "_cad_down", None)
        w._cad_preview = (False, lines[:cad_select.LIMIT], [])
        self.addCleanup(setattr, w, "_cad_preview", None)
        took = best_of(w.repaint)
        self.assertLess(took, 0.08, "%.0f ms a paint" % (took * 1000))


def _cloud_then_trim(v, sides=(P(250, 520),), kind="cloud"):
    v.apply_drag_tool(0, kind, P(150, 520), P(350, 700), False)
    for at in sides:
        v.cad_trim(0, at)


def _bend(v):
    x = v._create(0, {"kind": "arrow", "props": dict(A.DEFAULTS["arrow"]),
                      "points": [P(100, 730), P(400, 760)], "rect": pymupdf.Rect()})
    page = v.doc[0]
    m = A.read(page.load_annot(x))
    del page
    v.commit_models(0, [(x, A.bent(m, P(250, 700), 0.5))], olds={x: m})


def _click_click(v, tool, b):
    from kanzonas import cad_draw
    v.set_tool(tool)
    pk = {"w": v.pages[0], "index": 0, "xref": v.doc.page_xref(0), "tool": tool,
          "at": P(120, 520), "now": P(120, 520)}
    v._cad_shape = pk
    cad_draw.end(v, pk, b)
    v.set_tool("hand")


def _typed_circle(v):
    from kanzonas import cad_draw
    v.set_tool("circle")
    v._cad_shape = {"w": v.pages[1], "index": 1, "xref": v.doc.page_xref(1),
                    "tool": "circle", "at": P(300, 300), "now": P(300, 300)}
    cad_draw.typed(v, "1.5")
    v.set_tool("hand")


def _mirror_open_cloud(v):
    _cloud_then_trim(v)
    page = v.doc[0]
    xs = [a.xref for a in A.each_annot(page) if A.read(a)["kind"] == "opencloud"]
    del page
    v._set_selection(0, xs)
    v.cad_apply("Mirrored", pymupdf.Matrix(-1, 0, 0, 1, 600, 0))


NEW_EDITS = [
    ("circle", lambda v: v.apply_drag_tool(0, "circle", P(300, 300), P(360, 340), False)),
    ("mask", lambda v: v.apply_drag_tool(0, "mask", P(60, 50), P(220, 90), False)),
    ("arc", lambda v: v.apply_poly(0, "arc", [P(100, 500), P(200, 430), P(320, 520)])),
    ("curve", lambda v: v.apply_poly(2, "curve", [P(100, 500), P(320, 520), P(200, 430)])),
    ("bend an arrow by its middle grip", _bend),
    ("trim a cloud: an open cloud", _cloud_then_trim),
    ("trim an open cloud again", lambda v: _cloud_then_trim(v, (P(250, 520), P(350, 610)))),
    ("trim a rectangle: a polyline", lambda v: _cloud_then_trim(v, kind="rect")),
    ("trim a markup on the page", lambda v: v.cad_trim(1, P(400, 400))),
    ("click, move, click a line", lambda v: _click_click(v, "line", P(300, 580))),
    ("click, move, click a circle", lambda v: _click_click(v, "circle", P(160, 560))),
    ("typed circle radius", _typed_circle),
    ("mirror an open cloud", _mirror_open_cloud),
]


class UndoNewKinds(unittest.TestCase):
    """Every new kind of edit, undone and redone through MuPDF's journal, gives what a copy
    per edit gives (as tests/test_undo_journal.py checks the older ones)."""

    def test_every_new_edit_matches_the_copy_per_edit(self):
        from tests.test_undo_journal import Quiet, SameAsCopies
        for key in ("mouse_mode", "cad_select"):
            self.addCleanup(setattr, DocumentView, key, getattr(DocumentView, key))
        DocumentView.mouse_mode = "cad"
        DocumentView.cad_select = True
        q = Quiet("run")
        q.setUp()
        self.addCleanup(q.doCleanups)
        for label, edit in NEW_EDITS:
            with self.subTest(label):
                runs = []
                for journal in (True, False):
                    v = q.view(journal)
                    runs.append(SameAsCopies.run_sequence(self, v, edit))
                    if journal:
                        self.assertNotIn("bytes", [type(s).__name__ for s in v._undo])
                    v.dirty = False
                    v.close_doc()
                j, c = runs
                for k, (a, b) in enumerate(zip(j, c)):
                    self.assertEqual(a, b, "state %d" % k)
                self.assertEqual(j[0], j[2])            # (back to the start after undo)
                self.assertEqual(j[1], j[3])
                self.assertNotEqual(j[0], j[1], "the edit changed nothing")


class ArcHover(unittest.TestCase):
    def test_hover_over_many_arcs(self):
        # an arc is written as a PolyLine of hundreds of points (within 0.01 pt of the
        # curve), and the hit test went through them a piece at a time in Python: the
        # pointer over 80 arcs whose boxes hold it took 28 ms a move (budget: 10 ms)
        import math
        d = pymupdf.open()
        pg = d.new_page(width=1200, height=900)
        c = P(600, 450)
        for k in range(80):
            r = 150 + k * 4
            A.write(pg, {"kind": "arc", "props": dict(A.DEFAULTS["arc"]),
                         "points": [c + (r * math.cos(t), r * math.sin(t))
                                    for t in (0.2, 2.0, 5.9)]})
        path = os.path.join(tempfile.mkdtemp(), "arcs.pdf")
        d.save(path)
        v = DocumentView(path)
        self.addCleanup(v.close_doc)
        v.set_zoom(1.0)
        inside = [P(600 + 30 * math.cos(k), 450 + 30 * math.sin(k)) for k in range(60)]
        on = [P(600 + 150 * math.cos(1.0 + k * 0.01), 450 + 150 * math.sin(1.0 + k * 0.01))
              for k in range(60)]
        for q in inside + on:
            v.annot_at(0, q)                # (each markup read once, as moving does)
        self.assertIsNone(v.annot_at(0, inside[0]))
        self.assertIsNotNone(v.annot_at(0, on[0]))
        t = time.perf_counter()
        for q in inside + on:
            v._annot_memo = None
            v.annot_at(0, q)
        took = (time.perf_counter() - t) / len(inside + on)
        self.assertLess(took, 0.01, "%.1f ms a move" % (took * 1000))

    def test_the_quick_hit_test_finds_what_the_slow_one_did(self):
        import random as R
        rnd = R.Random(5)
        DV = DocumentView
        for _ in range(300):
            n = rnd.choice([2, 3, 30, 100, 400])
            pts = [(rnd.uniform(0, 100), rnd.uniform(0, 100)) for _ in range(n)]
            if rnd.random() < 0.2:
                pts[1] = pts[0]                 # (a piece of no length)
            q = P(rnd.uniform(-10, 110), rnd.uniform(-10, 110))
            tol = rnd.choice([0.5, 2.0, 6.0])
            slow = any(DV._seg_dist(q, pts[k], pts[k + 1]) <= tol for k in range(n - 1))
            self.assertEqual(DV._near_path(q, pts, tol), slow)


class LongCloud(unittest.TestCase):
    def test_a_part_of_a_cloud_with_thousands_of_points(self):
        # Trim on a cloud polygon of 3,000 points: each of its points was looked for among
        # every arc's center (0.3 s of the trim's 1 s; on a slow machine much more), and its
        # appearance worked out the page's matrix again for each point (0.1 s)
        import math
        from kanzonas import clouds
        d = pymupdf.open()
        pg = d.new_page(width=3000, height=2000)
        n = 3000
        pts = [P(1500 + 1300 * math.cos(t * 2 * math.pi / n),
                 1000 + 900 * math.sin(t * 2 * math.pi / n)) for t in range(n)]
        A.write(pg, {"kind": "polygon", "props": dict(A.DEFAULTS["polygon"], cloud=True),
                     "points": pts})
        cloud = clouds.closed_cloud(clouds.closed_shape(pg, pg.first_annot))
        total = clouds._cum(cloud["verts"])[-1]
        t = time.perf_counter()
        got = clouds.part(cloud, 5.0, total - 5.0)
        took = time.perf_counter() - t
        self.assertIsNotNone(got)
        self.assertGreater(len(got["verts"]), 2900)
        self.assertEqual(len(got["phase"]), len(got["verts"]))
        self.assertLess(took, 0.1, "%.2f s" % took)


if __name__ == "__main__":
    unittest.main()
