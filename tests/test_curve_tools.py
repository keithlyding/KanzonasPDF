"""Curvy lines (curves.py), for AutoCAD users:

- the Arc tool, as AutoCAD's three-point ARC: click the start, a point it passes through and
  the end; the preview follows the pointer; Escape cancels, Backspace takes back a point;
- a Line or Arrow bends by dragging its middle grip (a diamond): it becomes a smooth curve
  through the grip (a quadratic Bezier curve), its ends stay, an arrowhead points along the
  curve; dragged back onto the straight line it's straight again. One undo step per drag;
- the Curve tool: click the start, the end, then where it bends to (a bent line).

Both are written as PolyLine markups along the curve (every PDF viewer shows them), with their
defining points kept so KanzonasPDF reads them back as an arc or a bent line: they move where
they are, turn, restyle, undo, save and reopen, are hit along the curve, snap, outline and
flatten.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_curve_tools
"""
import math
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QKeyEvent, QMouseEvent  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import annotations as A  # noqa: E402
from kanzonas import curves, snapping  # noqa: E402
from kanzonas.document_view import DocumentView  # noqa: E402

P = pymupdf.Point


def blank():
    d = pymupdf.open()
    d.new_page(width=600, height=600)
    path = os.path.join(tempfile.mkdtemp(), "blank.pdf")
    d.save(path)
    return path


def on_circle(pts, center, r):
    return max(abs(abs(q - center) - r) for q in pts)


class Geometry(unittest.TestCase):
    def test_an_arc_passes_through_its_three_points_and_is_circular(self):
        a, m, c = P(100, 300), P(180, 210), P(320, 260)
        pts = curves.arc_path(a, m, c)
        center, r = curves.circle_through(a, m, c)
        self.assertEqual((pts[0], pts[-1]), (a, c))
        self.assertLess(on_circle(pts, center, r), 1e-6)
        # the through point lies on the drawn line (within the flattening tolerance)
        near = min(curves.seg_distance(m, p, q) for p, q in zip(pts, pts[1:]))
        self.assertLess(near, curves.TOL * 1.01)
        # smooth: each chord strays at most TOL from the circle
        for p, q in zip(pts, pts[1:]):
            mid = P((p.x + q.x) / 2, (p.y + q.y) / 2)
            self.assertLess(r - abs(mid - center), curves.TOL * 1.01)
        # the other way round it's the other side of the circle, through the same point
        back = curves.arc_path(c, m, a)
        self.assertLess(min(curves.seg_distance(m, p, q) for p, q in zip(back, back[1:])),
                        curves.TOL * 1.01)

    def test_a_big_arc_the_long_way_round(self):
        a, m, c = P(100, 100), P(100, 300), P(150, 100)    # (most of a circle)
        pts = curves.arc_path(a, m, c)
        center, r = curves.circle_through(a, m, c)
        length = sum(abs(q - p) for p, q in zip(pts, pts[1:]))
        self.assertGreater(length, 1.5 * math.pi * r)

    def test_three_points_on_a_line(self):
        self.assertIsNone(curves.circle_through(P(0, 0), P(5, 5), P(10, 10)))
        self.assertEqual(curves.arc_path(P(0, 0), P(5, 5), P(10, 10)),
                         [P(0, 0), P(5, 5), P(10, 10)])

    def test_a_bent_line_passes_through_its_grip(self):
        a, b, g = P(0, 0), P(200, 0), P(80, -60)
        ctl = curves.bend_control(a, b, g)
        self.assertEqual(ctl, P(60, -120))                 # 2 * grip - (a + b) / 2
        pts = curves.bend_path(a, b, g)
        self.assertEqual((pts[0], pts[-1]), (a, b))
        self.assertLess(min(curves.seg_distance(g, p, q) for p, q in zip(pts, pts[1:])),
                        curves.TOL * 1.01)

    def test_bent_and_straight_again(self):
        m = {"kind": "line", "props": dict(A.DEFAULTS["line"]), "points": [P(0, 0), P(100, 0)]}
        b = A.bent(m, P(50, 30), 2)
        self.assertEqual(b["bend"], P(50, 30))
        self.assertTrue(curves.is_curved(b))
        self.assertNotIn("bend", A.bent(b, P(40, 1.5), 2))
        self.assertAlmostEqual(A.bounds(b).y1, 30, 1)      # (the box holds the curve)


class Tools(unittest.TestCase):
    def setUp(self):
        for key in ("cad_select", "snap_objects", "snap_grid", "snap_page"):
            self.addCleanup(setattr, DocumentView, key, getattr(DocumentView, key))
        DocumentView.cad_select = True                  # CAD mouse mode: clicks, no drags
        DocumentView.snap_objects = DocumentView.snap_grid = DocumentView.snap_page = False

    def view(self, tool, path=None):
        v = DocumentView(path or blank())
        self.addCleanup(v.close_doc)
        self.addCleanup(lambda: setattr(v, "dirty", False))
        self.addCleanup(v.hide)
        v.resize(900, 900)
        v.show()
        v.set_zoom(1.0)
        APP.processEvents()
        v.set_tool(tool)
        return v

    def at(self, v, pt):
        q = v.pages[0].to_screen_pt(P(pt))
        return QPoint(round(q.x()), round(q.y()))

    def click(self, v, pt):
        QTest.mouseClick(v.pages[0], Qt.LeftButton, Qt.NoModifier, self.at(v, pt))
        APP.processEvents()

    def hover(self, v, pt):
        # (sent to the page itself: QTest.mouseMove moves the real pointer, over whatever
        # other window is under it)
        w = v.pages[0]
        pos = QPointF(self.at(v, pt))
        w.mouseMoveEvent(QMouseEvent(QEvent.MouseMove, pos, w.mapToGlobal(pos), Qt.NoButton,
                                     Qt.NoButton, Qt.NoModifier))
        APP.processEvents()

    def key(self, v, k):
        v.keyPressEvent(QKeyEvent(QEvent.KeyPress, k, Qt.NoModifier))
        APP.processEvents()

    def vertices(self, v, xref):
        page = v.doc[0]
        return [P(q) for q in page.load_annot(xref).vertices]

    def markups(self, v):
        page = v.doc[0]
        return [(a.xref, a.type[0], A.read(a)) for a in A.each_annot(page)]

    def drag(self, v, a, b):
        """Press at a, move to b with the button held, release (page points)."""
        w = v.pages[0]

        def send(kind, pt, buttons):
            pos = QPointF(self.at(v, pt))
            ev = QMouseEvent(kind, pos, w.mapToGlobal(pos), Qt.LeftButton, buttons,
                             Qt.NoModifier)
            {QEvent.MouseButtonPress: w.mousePressEvent, QEvent.MouseMove: w.mouseMoveEvent,
             QEvent.MouseButtonRelease: w.mouseReleaseEvent}[kind](ev)
            APP.processEvents()
        send(QEvent.MouseButtonPress, a, Qt.LeftButton)
        send(QEvent.MouseMove, ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2), Qt.LeftButton)
        send(QEvent.MouseMove, b, Qt.LeftButton)
        send(QEvent.MouseButtonRelease, b, Qt.NoButton)

    # ---- Arc ------------------------------------------------------------------------
    def test_arc_by_three_clicks_with_a_preview(self):
        v = self.view("arc")
        self.click(v, (100, 300))
        self.click(v, (200, 200))
        self.hover(v, (300, 300))
        w = v.pages[0]
        self.assertEqual(len(w._poly), 2)
        # the preview is the arc through the pointer: drawn at its top, not on the chord
        img = w.grab().toImage()
        top = self.at(v, (200, 200))
        chord_mid = self.at(v, (200, 300))
        dark = [img.pixelColor(top.x(), top.y() + dy).lightness() < 200 for dy in (-1, 0, 1)]
        self.assertTrue(any(dark))
        self.assertGreater(img.pixelColor(chord_mid).lightness(), 200)
        self.click(v, (300, 300))
        self.assertEqual(w._poly, [])
        (xref, typ, m), = self.markups(v)
        self.assertEqual((typ, m["kind"]), (pymupdf.PDF_ANNOT_POLY_LINE, "arc"))
        self.assertEqual(A.LABELS["arc"], "Arc")
        for got, want in zip(m["points"], [(100, 300), (200, 200), (300, 300)]):
            self.assertLess(abs(got - P(want)), 1.0)
        vert = self.vertices(v, xref)
        center, r = curves.circle_through(*m["points"])
        self.assertLess(on_circle(vert, center, r), 0.01)
        self.assertGreater(len(vert), 40)                   # (smooth at any zoom)
        # hit along the curve, not inside it
        self.assertEqual(v.annot_at(0, P(center.x, center.y - r)), xref)
        self.assertIsNone(v.annot_at(0, P(200, 290)))
        # undo takes it away, redo puts it back
        v.undo()
        self.assertEqual(self.markups(v), [])
        v.redo()
        self.assertEqual(len(self.markups(v)), 1)

    def test_escape_cancels_and_backspace_takes_back_a_point(self):
        v = self.view("arc")
        self.click(v, (100, 300))
        self.click(v, (150, 150))
        self.key(v, Qt.Key_Backspace)
        self.assertEqual(len(v.pages[0]._poly), 1)
        self.click(v, (200, 200))
        self.key(v, Qt.Key_Escape)
        self.assertEqual(v.pages[0]._poly, [])
        self.assertEqual(self.markups(v), [])
        # two points and Enter make no arc (it needs three)
        self.click(v, (100, 300))
        self.click(v, (200, 200))
        self.key(v, Qt.Key_Return)
        self.assertEqual(self.markups(v), [])

    def test_arc_moves_in_place_turns_restyles_and_reopens(self):
        v = self.view("arc")
        for pt in ((100, 300), (200, 220), (300, 300)):
            self.click(v, pt)
        (xref, _t, m), = self.markups(v)
        v._set_selection(0, [xref])
        v.cad_apply("Moved", pymupdf.Matrix(1, 0, 0, 1, 20, 10))
        (x2, _t, m2), = self.markups(v)
        self.assertEqual(x2, xref)                          # moved where it is
        self.assertTrue(A._same(A.translation(m, m2), P(20, 10)))
        # turned 90 degrees about (220, 270): its three points turn with it
        c = P(220, 270)
        mat = pymupdf.Matrix(1, 0, 0, 1, -c.x, -c.y) * pymupdf.Matrix(90) * \
            pymupdf.Matrix(1, 0, 0, 1, c.x, c.y)
        v._set_selection(0, [x2])
        v.cad_apply("Rotated", mat)
        (x3, _t, m3), = self.markups(v)
        for got, old in zip(m3["points"], m2["points"]):
            self.assertLess(abs(got - old * mat), 0.01)
        vert = self.vertices(v, x3)
        center, r = curves.circle_through(*m3["points"])
        self.assertLess(on_circle(vert, center, r), 0.01)
        # restyled: red and wider, still an arc
        v._set_selection(0, [x3])
        v.update_selected_props({"stroke": "#ff0000", "width": 4.0})
        (x4, _t, m4), = self.markups(v)
        self.assertEqual((m4["kind"], m4["props"]["stroke"], m4["props"]["width"]),
                         ("arc", "#ff0000", 4.0))
        # saved and opened again
        out = os.path.join(tempfile.mkdtemp(), "arc.pdf")
        v.doc.save(out)
        d = pymupdf.open(out)
        pg = d[0]
        again = [A.read(a) for a in A.each_annot(pg)]
        self.assertEqual([a["kind"] for a in again], ["arc"])
        self.assertTrue(A._same(again[0]["points"], m4["points"]))
        # shown: red pixels along the arc (and none on its chord)
        pix = pg.get_pixmap(dpi=144)
        s = 2.0
        for k in range(1, 10):
            t = k / 10
            q = curves.arc_path(*m4["points"])[round(t * (len(vert) - 1))]
            px = pix.pixel(int(q.x * s), int(q.y * s))
            self.assertTrue(px[0] > 200 and px[1] < 80, (q, px))
        del pg
        d.close()

    def test_arc_snap_points_outline_and_flatten(self):
        v = self.view("arc")
        for pt in ((100, 300), (200, 200), (300, 300)):
            self.click(v, pt)
        (xref, _t, m), = self.markups(v)
        snaps = snapping.markup_points(m)
        self.assertTrue(any(abs(q - P(200, 300)) < 0.5 for q in snaps))     # its center
        self.assertTrue(any(abs(q - P(100, 300)) < 0.5 for q in snaps))     # an end
        lines = v.cad_outlines(0, "markups", [(xref, m)])
        self.assertGreater(len(lines[0]), 40)                               # along the curve
        v.flatten()
        self.assertEqual(self.markups(v), [])
        drawn = v.doc[0].get_drawings()
        self.assertTrue(drawn and drawn[0]["rect"].y0 < 205)               # its top drawn

    # ---- bending a line by its middle grip --------------------------------------------
    def line(self, v, kind="line", a=(100, 300), b=(400, 300), **props):
        m = {"kind": kind, "props": dict(A.DEFAULTS[kind], **props), "points": [P(a), P(b)],
             "rect": pymupdf.Rect()}
        xref = v._create(0, m, select=True)
        APP.processEvents()
        return xref

    def test_dragging_the_middle_grip_bends_a_line_and_back(self):
        v = self.view("select")
        self.line(v)
        w = v.pages[0]
        self.assertIn("mid", w._handles(v.selected_model))
        img = w.grab().toImage()                            # (the diamond is drawn)
        self.assertLess(img.pixelColor(self.at(v, (250, 300)) + QPoint(0, -4)).lightness(), 240)
        self.drag(v, (250, 300), (250, 220))
        (xref, typ, m), = self.markups(v)
        self.assertEqual((typ, m["kind"]), (pymupdf.PDF_ANNOT_POLY_LINE, "line"))
        self.assertLess(abs(m["bend"] - P(250, 220)), 1.0)
        self.assertEqual(m["points"], [P(100, 300), P(400, 300)])      # the ends stay
        vert = self.vertices(v, xref)
        self.assertLess(min(curves.seg_distance(m["bend"], p, q)
                            for p, q in zip(vert, vert[1:])), 0.05)    # through the grip
        self.assertEqual(v.selected_xrefs(), [xref])                    # still selected
        # the grip is now on the curve: dragging it bends it more
        self.assertLess(abs(curves.grip(v.selected_model) - m["bend"]), 1e-6)
        self.drag(v, (250, 220), (250, 180))
        (_x, _t, m2), = self.markups(v)
        self.assertLess(abs(m2["bend"] - P(250, 180)), 1.0)
        # one undo step per drag
        v.undo()
        (_x, _t, back), = self.markups(v)
        self.assertLess(abs(back["bend"] - P(250, 220)), 1.0)
        # dragged back onto the straight line: a plain straight line again
        v._set_selection(0, [self.markups(v)[0][0]])
        self.drag(v, (250, 220), (251, 301))
        (_x, typ, m3), = self.markups(v)
        self.assertEqual((typ, m3["kind"]), (pymupdf.PDF_ANNOT_LINE, "line"))
        self.assertNotIn("bend", m3)

    def test_a_bent_arrow_keeps_its_head_along_the_curve(self):
        v = self.view("select")
        self.line(v, "arrow", head="closed")
        self.drag(v, (250, 300), (250, 200))
        (xref, typ, m), = self.markups(v)
        self.assertEqual((typ, m["kind"], m["props"]["head"]),
                         (pymupdf.PDF_ANNOT_POLY_LINE, "arrow", "closed"))
        self.assertEqual(A.LABELS[m["kind"]], "Arrow")
        page = v.doc[0]
        an = page.load_annot(xref)
        self.assertEqual(an.line_ends[1], pymupdf.PDF_ANNOT_LE_CLOSED_ARROW)
        # the last stretch of the curve runs along its tangent at the end: 2 (b - control)
        ctl = curves.bend_control(*m["points"], m["bend"])
        tangent = m["points"][1] - ctl
        vert = an.vertices
        last = P(vert[-1]) - P(vert[-2])
        angle = math.degrees(abs(math.atan2(last.y, last.x) - math.atan2(tangent.y, tangent.x)))
        self.assertLess(angle, 2)
        del an, page
        # one head, drawn behind the end along the tangent (pixels: with it - without it)
        def picture(head):
            d = pymupdf.open()
            p = d.new_page(width=600, height=600)
            mm = A.copy(m)
            mm["props"]["head"] = head
            if head is None:
                mm["kind"] = "line"
            A.write(p, mm)
            return p.get_pixmap(dpi=144)
        with_head, without = picture("closed"), picture(None)
        diff = [(x / 2, y / 2) for y in range(0, with_head.height, 2)
                for x in range(0, with_head.width, 2)
                if with_head.pixel(x, y) != without.pixel(x, y)]
        self.assertGreater(len(diff), 10)
        cx = sum(x for x, _y in diff) / len(diff)
        cy = sum(y for _x, y in diff) / len(diff)
        to_c = P(cx, cy) - m["points"][1]
        t = tangent / abs(tangent)
        along = to_c.x * t.x + to_c.y * t.y
        across = abs(to_c.x * t.y - to_c.y * t.x)
        self.assertLess(along, 0)                       # behind the tip...
        self.assertLess(across, abs(along))             # ...along the curve, not beside it
        self.assertTrue(all(abs(P(x, y) - m["points"][1]) < 25 for x, y in diff))

    def test_a_bent_arrow_moves_in_place_turns_and_reopens(self):
        v = self.view("select")
        self.line(v, "arrow")
        self.drag(v, (250, 300), (250, 230))
        (xref, _t, m), = self.markups(v)
        v._set_selection(0, [xref])
        v.cad_apply("Moved", pymupdf.Matrix(1, 0, 0, 1, 15, -5))
        (x2, _t, m2), = self.markups(v)
        self.assertEqual(x2, xref)
        self.assertTrue(A._same(A.translation(m, m2), P(15, -5)))
        self.assertLess(abs(m2["bend"] - (m["bend"] + P(15, -5))), 1e-3)
        mat = pymupdf.Matrix(30)
        v._set_selection(0, [x2])
        v.cad_apply("Rotated", mat)
        (x3, _t, m3), = self.markups(v)
        self.assertLess(abs(m3["bend"] - m2["bend"] * mat), 0.01)
        self.assertLess(abs(m3["points"][1] - m2["points"][1] * mat), 0.01)
        # mirrored: still a bent arrow, through its mirrored grip
        mir = pymupdf.Matrix(-1, 0, 0, 1, 600, 0)
        v._set_selection(0, [x3])
        v.cad_apply("Mirrored", mir)
        (x4, _t, m4), = self.markups(v)
        self.assertLess(abs(m4["bend"] - m3["bend"] * mir), 0.01)
        v.undo()
        (_x, _t, back), = self.markups(v)
        self.assertLess(abs(back["bend"] - m3["bend"]), 0.01)
        out = os.path.join(tempfile.mkdtemp(), "arrow.pdf")
        v.doc.save(out)
        d = pymupdf.open(out)
        pg = d[0]
        again = [A.read(a) for a in A.each_annot(pg)]
        self.assertEqual([a["kind"] for a in again], ["arrow"])
        self.assertLess(abs(again[0]["bend"] - m3["bend"]), 0.01)
        del pg
        d.close()

    def test_a_bent_line_is_not_trimmed(self):
        v = self.view("select")
        self.line(v)
        self.drag(v, (250, 300), (250, 220))
        self.line(v, a=(250, 100), b=(250, 400))            # (crosses it)
        before = self.markups(v)
        top = curves.bend_path(P(100, 300), P(400, 300), P(250, 220))
        self.assertFalse(v.cad_trim(0, top[len(top) // 4]))
        self.assertEqual(len(self.markups(v)), len(before))

    # ---- Curve tool -----------------------------------------------------------------
    def test_curve_tool_start_end_then_bend(self):
        v = self.view("curve")
        self.click(v, (100, 400))
        self.click(v, (400, 400))
        self.hover(v, (250, 300))
        img = v.pages[0].grab().toImage()
        self.assertLess(min(img.pixelColor(self.at(v, (250, 300)) + QPoint(0, dy)).lightness()
                            for dy in (-1, 0, 1)), 200)        # the preview bends there
        self.click(v, (250, 300))
        (xref, typ, m), = self.markups(v)
        self.assertEqual((typ, m["kind"]), (pymupdf.PDF_ANNOT_POLY_LINE, "line"))
        self.assertLess(abs(m["bend"] - P(250, 300)), 1.0)
        # Enter after two clicks: a straight line; a double-click too
        self.click(v, (100, 500))
        self.click(v, (400, 500))
        self.key(v, Qt.Key_Return)
        self.assertEqual(sorted(t for _x, t, _m in self.markups(v)),
                         sorted([pymupdf.PDF_ANNOT_POLY_LINE, pymupdf.PDF_ANNOT_LINE]))
        self.click(v, (100, 550))
        self.click(v, (400, 550))           # (a double-click: its first press, then...)
        QTest.mouseDClick(v.pages[0], Qt.LeftButton, Qt.NoModifier, self.at(v, (400, 550)))
        APP.processEvents()
        self.assertEqual(len(self.markups(v)), 3)

    def test_the_grip_bends_a_line_in_the_standard_mouse_mode_too(self):
        DocumentView.cad_select = False
        v = self.view("select")
        self.line(v, "arrow")
        self.drag(v, (250, 300), (260, 360))
        (_x, _t, m), = self.markups(v)
        self.assertEqual(m["kind"], "arrow")
        self.assertLess(abs(m["bend"] - P(260, 360)), 1.0)


class InTheWindow(unittest.TestCase):
    def test_arc_and_curve_in_the_menus_the_shapes_and_the_cad_tab(self):
        from PySide6.QtWidgets import QToolButton
        from kanzonas.main_window import MainWindow
        w = MainWindow()
        self.addCleanup(lambda: (setattr(w, "_close_confirmed", True), w.close()))
        old = w.settings.value("mouse_mode")
        self.addCleanup(lambda: w.settings.setValue("mouse_mode", old or "hand"))
        t = w.tool_actions
        self.assertEqual((t["arc"].text(), t["curve"].text()), ("Arc", "Curve"))
        self.assertFalse(t["arc"].icon().isNull() or t["curve"].icon().isNull())
        self.assertIn(t["arc"], w.tool_group.actions())             # (Tools menu)
        self.assertIn(t["curve"], w.shapes_btn.menu().actions())    # (classic toolbar)
        w.set_mouse_mode("cad")
        # the CAD tab's Line button starts as Line, with Curve under its arrow; once Curve is
        # in use its face shows Curve (as AutoCAD's ribbon shows the one used last)
        split = [b for b in w._cad_tab.findChildren(QToolButton) if b.menu() is not None and
                 b.defaultAction() is t["line"]]
        self.assertEqual(len(split), 1)
        self.assertIn(t["curve"], split[0].menu().actions())
        t["curve"].trigger()
        self.assertEqual(w.tool, "curve")
        self.assertIs(split[0].defaultAction(), t["curve"])


if __name__ == "__main__":
    unittest.main()
