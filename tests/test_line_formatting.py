"""A line's ends, middle and style, in Properties (1.15.21).

Markups (Line, Arrow, Polyline, Arc, Curve): Start arrowhead and End arrowhead (each its own
kind, PDF's line endings), Middle arrow (open or closed, drawn into the markup's appearance:
PDF has no middle ending) and Line style (solid, dashed, dotted, dash-dot).

The page's own lines (Edit objects, CAD mode): Line color, Fill color, Line style and Start /
End arrowhead and Middle arrow next to Line width. The arrowheads go into the line's own path
(they move and turn with it), recorded in its own  q ... Q  (a /KZHeads marked-content point)
so a change replaces them; on a dashed line they're cut into pieces so they're drawn solid.

The owner, 22 Nov 2026: "When clicking on a line and now the weight is in the properties
panel, others edits need to be in there too, like color, adding arrows to both ends and
middle, changing arrow type, and whatever else. Almost how Microsoft does it"; "Yes all of
them but as one release".

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_line_formatting
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
from kanzonas import main_window, mouse_modes  # noqa: E402
from kanzonas import page_objects as P  # noqa: E402

P_ = pymupdf.Point


def markup(kind, pts, **props):
    d = pymupdf.open()
    p = d.new_page(width=300, height=200)
    a = A.write(p, {"kind": kind, "props": dict(A.DEFAULTS[kind], **props),
                    "points": [P_(q) for q in pts], "rect": pymupdf.Rect(pts[0], pts[-1])})
    return d, p, a


def ink(pm, rect):
    n = 0
    for y in range(int(rect.y0), int(rect.y1)):
        for x in range(int(rect.x0), int(rect.x1)):
            if 0 <= x < pm.width and 0 <= y < pm.height and min(pm.pixel(x, y)) < 160:
                n += 1
    return n


class Markups(unittest.TestCase):
    def test_both_ends_and_their_kinds(self):
        for kind in ("line", "arrow", "polyline"):
            pts = [(30, 100), (270, 100)] if kind != "polyline" else [(30, 100), (150, 100),
                                                                      (270, 60)]
            d, p, a = markup(kind, pts, head_start="circle", head="closed")
            got = p.load_annot(a.xref)
            self.assertEqual(got.line_ends, (pymupdf.PDF_ANNOT_LE_CIRCLE,
                                             pymupdf.PDF_ANNOT_LE_CLOSED_ARROW), kind)
            m = A.read(got)
            self.assertEqual((m["props"]["head_start"], m["props"]["head"]),
                             ("circle", "closed"), kind)

    def test_a_line_has_none_by_default_an_arrow_one_at_its_end(self):
        _d, p, a = markup("line", [(30, 100), (270, 100)])
        self.assertEqual(p.load_annot(a.xref).line_ends, (0, 0))
        _d, p, a = markup("arrow", [(30, 100), (270, 100)])
        self.assertEqual(p.load_annot(a.xref).line_ends, (0, pymupdf.PDF_ANNOT_LE_OPEN_ARROW))

    def test_line_style(self):
        _d, p, a = markup("line", [(30, 100), (270, 100)], dash="dot", width=2)
        got = p.load_annot(a.xref)
        self.assertEqual(got.border["dashes"], (2, 3))
        self.assertEqual(A.read(got)["props"]["dash"], "dot")
        _d, p, a = markup("line", [(30, 100), (270, 100)], dash="solid")
        self.assertFalse(p.load_annot(a.xref).border.get("dashes"))

    def test_a_dashed_polylines_ends_are_drawn_solid(self):
        d, p, a = markup("polyline", [(30, 100), (150, 100), (270, 60)], dash="dash",
                         head="closed")
        ap = int(d.xref_get_key(a.xref, "AP/N")[1].split()[0])
        data = d.xref_stream(ap)
        self.assertIn(b"\nS\n[] 0 d\n", data)

    def test_a_middle_arrow_is_drawn_halfway_and_the_box_holds_it(self):
        for mid in ("open", "closed"):
            d, p, a = markup("line", [(30, 100), (270, 100)], mid=mid, width=2)
            pm = p.get_pixmap()
            # (a line across at y=100: the arrow's wings reach above and below it, halfway)
            self.assertGreater(ink(pm, pymupdf.Rect(140, 92, 160, 97)), 2, mid)
            self.assertEqual(ink(pm, pymupdf.Rect(60, 92, 80, 97)), 0, mid)
            self.assertTrue(p.load_annot(a.xref).rect.contains(pymupdf.Rect(140, 94, 160, 106)))

    def test_the_middle_arrow_moves_with_the_markup(self):
        d, p, a = markup("line", [(30, 100), (270, 100)], mid="closed", width=2)
        self.assertTrue(A.shift_in_place(p, a.xref, P_(0, 40)))
        pm = p.get_pixmap()
        self.assertGreater(ink(pm, pymupdf.Rect(140, 132, 160, 137)), 2)
        self.assertEqual(ink(pm, pymupdf.Rect(140, 92, 160, 97)), 0)

    def test_a_line_from_another_program_keeps_its_ends_and_dash(self):
        d = pymupdf.open()
        p = d.new_page()
        a = p.add_line_annot((30, 100), (270, 100))
        a.set_line_ends(pymupdf.PDF_ANNOT_LE_DIAMOND, pymupdf.PDF_ANNOT_LE_OPEN_ARROW)
        a.set_border(width=1, dashes=[4, 2])
        a.update()
        m = A.read(p.load_annot(a.xref))
        self.assertEqual((m["props"]["head_start"], m["props"]["head"], m["props"]["dash"]),
                         ("diamond", "open", "dash"))


def drawing():
    """A straight line, a polyline, a curve and a filled square (no outline)."""
    d = pymupdf.open()
    p = d.new_page(width=300, height=300)
    x = d.get_new_xref()
    d.update_object(x, "<<>>")
    d.update_stream(x, b"0 0 0 RG 1.5 w 20 250 m 280 250 l S "
                       b"20 200 m 120 200 l 160 140 l 280 140 l S "
                       b"20 60 m 60 20 100 60 140 20 c S "
                       b"1 0 0 rg 200 20 50 50 re f")
    d.xref_set_key(p.xref, "Contents", "%d 0 R" % x)
    return d, p


class DrawingLines(unittest.TestCase):
    def setUp(self):
        self.d, self.p = drawing()

    def objs(self):
        return P.Objects(self.p)

    def test_its_style_is_read(self):
        o = self.objs()
        self.assertEqual(P.style_of(o.found[0]), {"stroke": "#000000", "fill": None,
                                                  "dash": "solid"})
        self.assertEqual(P.style_of(o.found[3]), {"stroke": None, "fill": "#ff0000",
                                                  "dash": "solid"})

    def test_arrowheads_go_into_the_line_and_a_change_replaces_them(self):
        o = self.objs()
        P.recolor(self.p, [0, 1, 2], objs=o, heads={"start": "open", "end": "closed"})
        o = self.objs()
        self.assertEqual(len(o.items), 4)                  # (no new objects: part of the lines)
        self.assertEqual([P.heads_of(o.data, f)[:3] for f in o.found[:3]],
                         [("open", "closed", "none")] * 3)
        P.recolor(self.p, [0], objs=o, heads={"end": "open", "mid": "closed"})
        o = self.objs()
        self.assertEqual(P.heads_of(o.data, o.found[0])[:3], ("open", "open", "closed"))
        self.assertEqual(o.data.count(b"/KZHeads"), 3)
        P.recolor(self.p, [0, 1, 2], objs=o, heads={"start": "none", "end": "none",
                                                     "mid": "none"})
        o = self.objs()
        self.assertEqual([P.heads_of(o.data, f) for f in o.found], [None] * 4)
        self.assertIn(b"20 250 m 280 250 l S", o.data)     # (the line as it was)

    def test_they_move_with_the_line(self):
        o = self.objs()
        P.recolor(self.p, [0], objs=o, heads={"end": "closed"})
        o = self.objs()
        r = pymupdf.Rect(o.items[0]["rect"])
        P.move_to(self.p, [0], r, r + (0, -40, 0, -40), o)
        o = self.objs()
        self.assertEqual(P.heads_of(o.data, o.found[0])[:3], ("none", "closed", "none"))
        P.recolor(self.p, [0], objs=o, heads={"start": "open"})
        o = self.objs()
        self.assertEqual(P.heads_of(o.data, o.found[0])[:3], ("open", "closed", "none"))
        self.assertEqual(o.data.count(b"/KZHeads"), 1)

    def test_a_closed_shape_gets_none(self):
        o = self.objs()
        body = P._split(o.data[o.found[3]["start"]:o.found[3]["end"]])[1]
        self.assertFalse(P.can_have_heads(body))

    def test_line_style_and_on_a_dashed_line_solid_arrowheads(self):
        o = self.objs()
        P.recolor(self.p, [0], objs=o, heads={"end": "open"})
        o = self.objs()
        P.recolor(self.p, [0], objs=o, dash="dot")
        o = self.objs()
        self.assertEqual(P.style_of(o.found[0])["dash"], "dot")
        n = P.heads_of(o.data, o.found[0])[3]
        self.assertGreater(n, 2)                            # (cut into pieces)
        pm = self.p.get_pixmap(dpi=144)
        # (one wing of the arrowhead at the line's end, x=280, y=50 on the page: from about
        # (272.5, 46.6) to the tip; every step along it is inked, no dotted gaps)
        a, tip = P_(272.5, 46.6), P_(280, 50)
        steps = [a + (tip - a) * (k / 10) for k in range(2, 9)]
        wing = [min(min(pm.pixel(round(2 * q.x) + dx, round(2 * q.y) + dy))
                    for dx in (-1, 0, 1) for dy in (-1, 0, 1)) < 128 for q in steps]
        self.assertTrue(all(wing), wing)

    def test_a_color(self):
        o = self.objs()
        P.recolor(self.p, [0], objs=o, stroke=(0, 0.5, 0))
        self.assertEqual(P.style_of(self.objs().found[0])["stroke"], "#008000")


class InTheWindow(unittest.TestCase):
    def setUp(self):
        d, _p = drawing()
        path = os.path.join(tempfile.mkdtemp(), "plan.pdf")
        d.save(path)
        w = self.w = main_window.MainWindow()
        old = {k: w.settings.value(k) for k in ("mouse_mode", "mouse_before_cad")}

        def back():
            for k, val in old.items():
                w.settings.setValue(k, val) if val is not None else w.settings.remove(k)
            mouse_modes.apply(w.settings)
        self.addCleanup(back)
        self.addCleanup(lambda: [setattr(x, "_close_confirmed", True) or x.close()
                                 for x in main_window.windows()])
        w.resize(1200, 900)
        w.show()
        w.open_file(path)
        APP.processEvents()
        v = self.v = w.view()
        self.addCleanup(lambda: setattr(v, "dirty", False))
        w.set_tool("editobjects")
        APP.processEvents()
        self.pr = w.props

    def select(self, k):
        items = [it for it in self.v.content_objects(0).items if it["kind"] == "shape"]
        self.v.select_objects(0, [items[k]])
        APP.processEvents()

    def shown(self, key):
        return self.pr.rows[key][1].isVisible()

    def test_a_drawing_line_shows_color_style_and_arrowheads(self):
        self.select(0)
        for key in ("stroke", "width", "dash", "head_start", "head", "mid"):
            self.assertTrue(self.shown(key), key)
        self.assertFalse(self.shown("fill"))
        self.assertEqual(self.pr.rows["head"][0].text(), "End arrowhead")

    def test_a_filled_shape_shows_its_fill_and_no_arrowheads(self):
        self.select(3)
        self.assertTrue(self.shown("fill"))
        self.assertFalse(self.shown("head"))

    def test_an_arrowhead_picked_is_one_undo_step(self):
        self.select(0)
        self.pr.head.setCurrentIndex(self.pr.head.findData("closed"))
        APP.processEvents()
        self.assertEqual(self.v.object_style()["end"], "closed")
        self.assertTrue(self.v.obj_sel)                     # (still selected)
        self.v.undo()
        APP.processEvents()
        o = P.Objects(self.v.doc[0])
        self.assertIsNone(P.heads_of(o.data, o.found[0]))

    def test_the_line_tool_shows_both_ends_middle_and_style(self):
        self.v.clear_object_selection()
        self.w.set_tool("line")
        APP.processEvents()
        for key in ("head_start", "head", "mid", "dash"):
            self.assertTrue(self.shown(key), key)
        self.assertEqual(self.pr.head_start.count(), len(A.HEADS))


if __name__ == "__main__":
    unittest.main()
