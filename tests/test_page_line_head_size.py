"""Arrowhead size for the drawing's own lines (1.17): the page's lines given arrowheads in
Properties (Edit objects, CAD mode) and the Drawing tab's lines get Arrowhead size, as
markups have had since 1.16.4: 100% is the size the line width gives, from 25% to 500%. It's
kept in the line's /KZHeads marker (/Z), so it stays when the line's width, Line style or
arrowheads change, and when the file is saved and opened.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_page_line_head_size
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
from kanzonas import page_objects as P  # noqa: E402
from tests.test_drawing_tab import Base  # noqa: E402
from tests.test_line_formatting import InTheWindow, drawing  # noqa: E402

def reach(data, d):
    """How far the arrowheads at a line's end reach from it (content units)."""
    h = P.heads_of(data, d)
    body = P._split(data[d["start"]:d["end"]])[1]
    subs = P._subpaths(P._path_tokens(body)[:-1])
    tip = P._points(subs[0])[-1]
    pts = [q for sub in subs[-h[3]:] for q in P._points(sub)]
    return max(abs(q - tip) for q in pts if abs(q - tip) < 60)


class PageLines(unittest.TestCase):
    def setUp(self):
        self.d, self.p = drawing()

    def objs(self):
        return P.Objects(self.p)

    def test_the_size_scales_them_and_is_kept(self):
        o = self.objs()
        P.recolor(self.p, [0], objs=o, heads={"end": "closed"})
        o = self.objs()
        one = reach(o.data, o.found[0])
        self.assertEqual(P.heads_of(o.data, o.found[0])[4], 1.0)
        self.assertNotIn(b"/Z", o.data)               # (100%: written as before)
        P.recolor(self.p, [0], objs=o, heads={"size": 2.0})
        o = self.objs()
        self.assertEqual(P.heads_of(o.data, o.found[0])[:3], ("none", "closed", "none"))
        self.assertEqual(P.heads_of(o.data, o.found[0])[4], 2.0)
        self.assertAlmostEqual(reach(o.data, o.found[0]) / one, 2.0, delta=0.01)
        # kept when its arrowheads, width or Line style change
        P.recolor(self.p, [0], objs=o, heads={"start": "open"})
        o = self.objs()
        self.assertEqual(P.heads_of(o.data, o.found[0])[4], 2.0)
        P.recolor(self.p, [0], objs=o, width=3.0)
        o = self.objs()
        h = P.heads_of(o.data, o.found[0])
        self.assertEqual((h[:3], h[4]), (("open", "closed", "none"), 2.0))
        self.assertAlmostEqual(reach(o.data, o.found[0]),
                               P.head_length(3.0, 2.0) * 1.0966, delta=0.05)
        P.recolor(self.p, [0], objs=o, dash="dash")
        o = self.objs()
        self.assertEqual(P.heads_of(o.data, o.found[0])[4], 2.0)

    def test_within_its_range_and_an_old_marker_reads_100(self):
        o = self.objs()
        P.recolor(self.p, [0], objs=o, heads={"end": "open", "size": 40})
        o = self.objs()
        self.assertEqual(P.heads_of(o.data, o.found[0])[4], P.HEAD_SCALES[1])
        self.assertEqual(P.HEAD_SCALES, A.HEAD_SCALES)
        P.recolor(self.p, [0], objs=o, heads={"size": 0.01})
        o = self.objs()
        self.assertEqual(P.heads_of(o.data, o.found[0])[4], P.HEAD_SCALES[0])
        # (a line given arrowheads by 1.16: its marker has no size)
        self.assertEqual(P._HEADS_MARK.search(
            b"/KZHeads <</S/none/E/open/M/none/N 1>> DP").group(5), None)
        self.assertEqual(P.head_scale(None), 1.0)

    def test_kept_when_saved_and_opened(self):
        o = self.objs()
        P.recolor(self.p, [0], objs=o, heads={"end": "open", "size": 1.5})
        path = os.path.join(tempfile.mkdtemp(), "heads.pdf")
        self.d.save(path)
        o = P.Objects(pymupdf.open(path)[0])
        self.assertEqual(P.heads_of(o.data, o.found[0])[4], 1.5)


class DrawingTab(Base):
    def test_the_tools_arrowhead_size_is_used(self):
        v = self.view()
        A.set_tool_props("d_arrow", dict(A.tool_props("d_arrow"), head_size=2.5))
        self.draw(v, "d_arrow", (100, 300), (400, 300))
        A.reset_tool_props("d_arrow")
        self.draw(v, "d_arrow", (100, 400), (400, 400))
        big, small = self.drawn(v)
        data = v.content_objects(0).data
        self.assertEqual(P.heads_of(data, big["obj"])[4], 2.5)
        self.assertEqual(P.heads_of(data, small["obj"])[4], 1.0)
        self.assertAlmostEqual(reach(data, big["obj"]) / reach(data, small["obj"]), 2.5,
                               delta=0.01)
        v.select_objects(0, [big])
        self.assertEqual(v.object_style()["head_size"], 2.5)
        v.select_objects(0, [big, small])
        self.assertEqual(v.object_style()["head_size"], "")       # (they differ)


class InProperties(unittest.TestCase):
    setUp, select, shown = InTheWindow.setUp, InTheWindow.select, InTheWindow.shown

    def test_shown_for_a_line_and_set_in_one_undo_step(self):
        self.select(0)
        self.assertTrue(self.shown("head_size"))
        self.assertEqual(self.pr.head_size.value(), 100)
        self.pr.head.setCurrentIndex(self.pr.head.findData("closed"))
        APP.processEvents()
        self.pr.head_size.setValue(200)
        APP.processEvents()
        o = P.Objects(self.v.doc[0])
        h = P.heads_of(o.data, o.found[0])
        self.assertEqual((h[1], h[4]), ("closed", 2.0))
        self.assertEqual(self.v.object_style()["head_size"], 2.0)
        self.assertTrue(self.v.obj_sel)                     # (still selected)
        self.v.undo()
        APP.processEvents()
        o = P.Objects(self.v.doc[0])
        self.assertEqual(P.heads_of(o.data, o.found[0])[4], 1.0)

    def test_not_for_a_filled_shape(self):
        self.select(3)
        self.assertFalse(self.shown("head_size"))

    def test_the_drawing_line_tool_has_it(self):
        self.v.clear_object_selection()
        self.w.set_tool("d_line")
        APP.processEvents()
        self.assertTrue(self.shown("head_size"))


if __name__ == "__main__":
    unittest.main()
