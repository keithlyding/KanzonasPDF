"""Cut-outs in areas (Measure > Cut-out): an opening (a stair shaft, a window, a column) taken
out of an Area or Volume measurement. Drawn into the one selected, or the one it's drawn in, as
one undo step. The measurement shows its net area (or net volume), with a line saying what was
taken out of what; the Measurement summary and legends total the net values. Cut-outs drawn
over each other or past the area's edge aren't taken out twice or from outside. They're kept
in the markup itself, so they move, copy, undo and save with it; its drawing has them as holes
(its fill leaves them out), which other PDF viewers show, with the net value in its comment.

The owner, 23 Nov 2026 (takeoff and quantity surveying, the first of seven): "Subtract
openings from an Area or Volume measurement ... The shown value is the net area (or net
volume), and the Measurement summary shows net."

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_area_cutouts
"""
import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import annotations as A, legend, measure as M, measure_ui  # noqa: E402
from kanzonas import main_window  # noqa: E402

P = pymupdf.Point
FT = 0.3048


def sq(x0, y0, x1, y1):
    return [P(x0, y0), P(x1, y0), P(x1, y1), P(x0, y1)]


class Math(unittest.TestCase):
    def test_net_area(self):
        outer = sq(0, 0, 100, 100)
        self.assertEqual(M.net_area(outer, [sq(10, 10, 30, 30)]), 10000 - 400)
        # (over each other: the overlap once; past the edge: only the part inside)
        self.assertEqual(M.net_area(outer, [sq(10, 10, 30, 30), sq(20, 20, 40, 40),
                                            sq(90, 90, 120, 120)]), 10000 - 800)
        self.assertEqual(M.net_area(outer, None), 10000)
        self.assertEqual(M.net_area(outer, [sq(-10, -10, 110, 110)]), 0)


def sheet():
    d = pymupdf.open()
    p = d.new_page(width=600, height=600)
    M.set_scale(p, FT / 72, "ft", "1\" = 1'-0\"")      # (an inch of paper is a foot)
    path = os.path.join(tempfile.mkdtemp(), "plan.pdf")
    d.save(path)
    return path


class InTheWindow(unittest.TestCase):
    def setUp(self):
        self.addCleanup(lambda: [setattr(x, "_close_confirmed", True) or x.close()
                                 for x in main_window.windows()])
        w = self.w = main_window.MainWindow()
        w.resize(1200, 900)
        w.show()
        self.path = sheet()
        w.open_file(self.path)
        APP.processEvents()
        v = self.v = w.view()
        self.addCleanup(lambda: setattr(v, "dirty", False))

    def draw(self, tool, pts):
        if self.w.tool != tool:
            self.w.set_tool(tool)
            APP.processEvents()
        self.v.apply_poly(0, tool, pts)
        APP.processEvents()

    def areas(self):
        p = self.v.doc[0]
        return [(a.xref, A.read(a)) for a in A.each_annot(p)
                if A.read(a) and A.read(a)["kind"] in A.CUT_KINDS]

    def summary(self):
        return {(r[0], r[5]): r[4] for r in measure_ui.summary_rows(self.v.doc)}

    def test_a_cut_out_drawn_in_the_area_takes_its_part_out(self):
        A.set_tool_props("m_area", dict(A.tool_props("m_area"), fill="#ffcc00"))
        self.addCleanup(lambda: A.reset_tool_props("m_area"))
        self.draw("m_area", sq(72, 72, 360, 360))               # (4 x 4 ft = 16 sq ft)
        self.v.clear_selection()
        self.draw("m_cutout", sq(144, 144, 216, 216))           # (1 x 1 ft, inside it)
        (x, m), = self.areas()
        self.assertEqual(len(m["holes"]), 1)
        self.assertAlmostEqual(self.summary()[("Area", "sq ft")], 15.0)
        content = self.v.doc[0].load_annot(x).info["content"]
        self.assertIn("15.00 sq ft", content)
        self.assertIn("1 cut-out from 16.00 sq ft", content)
        self.assertEqual(self.v.selected_xrefs(), [x])          # (the area, selected)
        pm = self.v.doc[0].get_pixmap()
        self.assertEqual(pm.pixel(180, 180), (255, 255, 255))   # (a hole in its fill)
        self.assertNotEqual(pm.pixel(100, 300), (255, 255, 255))
        self.v.undo()
        APP.processEvents()
        (x, m), = self.areas()
        self.assertNotIn("holes", m)
        self.v.redo()
        APP.processEvents()
        (x, m), = self.areas()
        self.assertEqual(len(m["holes"]), 1)

    def test_into_the_one_selected_and_a_volume_too(self):
        self.w.set_tool("m_volume")
        props = dict(A.tool_props("m_volume"), depth=2.0)
        A.set_tool_props("m_volume", props)
        self.addCleanup(lambda: A.reset_tool_props("m_volume"))
        self.draw("m_volume", sq(72, 72, 360, 360))             # (16 sq ft x 2 ft)
        (x, _m), = self.areas()
        self.draw("m_cutout", sq(144, 144, 216, 216))
        self.draw("m_cutout", sq(400, 400, 450, 450))           # (selected: goes in it)
        (x, m), = self.areas()
        self.assertEqual(len(m["holes"]), 2)
        self.assertAlmostEqual(self.summary()[("Volume", "cu ft")], 30.0)   # ((16 - 1) x 2)

    def test_outside_any_area_nothing_changes(self):
        self.draw("m_area", sq(72, 72, 144, 144))
        self.v.clear_selection()
        said = []
        self.v.statusMessage.connect(said.append)
        rev = self.v.revision
        self.draw("m_cutout", sq(300, 300, 350, 350))
        self.assertEqual(self.v.revision, rev)
        self.assertTrue(any("inside an Area" in s for s in said))

    def test_removed_one_or_all(self):
        self.draw("m_area", sq(72, 72, 360, 360))
        self.draw("m_cutout", sq(100, 100, 130, 130))
        self.draw("m_cutout", sq(200, 200, 230, 230))
        (x, m), = self.areas()
        self.v.remove_cutouts(0, x, self.v.cutout_at(0, x, P(110, 110)))
        (x, m), = self.areas()
        self.assertEqual(len(m["holes"]), 1)
        self.assertIsNone(self.v.cutout_at(0, x, P(110, 110)))
        self.v.remove_cutouts(0, x)
        (x, m), = self.areas()
        self.assertNotIn("holes", m)
        self.assertAlmostEqual(self.summary()[("Area", "sq ft")], 16.0)

    def test_from_the_right_click_menu(self):
        # (its actions act on that measurement: the Layer menu after them reused the name the
        # first version of them looked the markup up by, when they ran)
        from unittest import mock
        from PySide6.QtCore import QPoint
        from PySide6.QtWidgets import QMenu
        self.draw("m_area", sq(72, 72, 360, 360))
        self.draw("m_cutout", sq(100, 100, 130, 130))
        self.draw("m_cutout", sq(200, 200, 230, 230))
        self.w.set_tool("select")
        (x, _m), = self.areas()
        self.v.select_xref(0, x)
        seen = []

        class Menu(QMenu):
            def exec(self, *_a):
                seen.extend(self.actions())
        ev = mock.Mock()
        ev.globalPosition.return_value.toPoint.return_value = QPoint(0, 0)
        with mock.patch("PySide6.QtWidgets.QMenu", Menu):
            self.v.pages[0]._content_menu(ev, P(110, 110))
        acts = {a.text(): a for a in seen}
        self.assertIn("Add cut-out", acts)
        acts["Remove this cut-out"].trigger()
        APP.processEvents()
        (x, m), = self.areas()
        self.assertEqual(len(m["holes"]), 1)
        self.v.select_xref(0, x)
        seen.clear()
        with mock.patch("PySide6.QtWidgets.QMenu", Menu):
            self.v.pages[0]._content_menu(ev, P(300, 300))
        acts = {a.text(): a for a in seen}
        self.assertNotIn("Remove this cut-out", acts)       # (not in one)
        acts["Remove all cut-outs"].trigger()
        APP.processEvents()
        (x, m), = self.areas()
        self.assertNotIn("holes", m)
        seen.clear()
        self.v.select_xref(0, x)
        with mock.patch("PySide6.QtWidgets.QMenu", Menu):
            self.v.pages[0]._content_menu(ev, P(300, 300))
        acts = {a.text(): a for a in seen}
        acts["Add cut-out"].trigger()
        APP.processEvents()
        self.assertEqual(self.w.tool, "m_cutout")
        self.assertEqual(self.v.selected_xrefs(), [x])      # (still selected: goes in it)

    def test_moved_copied_saved_and_in_legends(self):
        self.draw("m_area", sq(72, 72, 360, 360))
        self.draw("m_cutout", sq(144, 144, 216, 216))
        (x, _m), = self.areas()
        self.v.select_xref(0, x)
        self.v.nudge(10, 0, 1.0)
        APP.processEvents()
        (x, m), = self.areas()
        self.assertEqual([round(q.x) for q in m["holes"][0]], [154, 226, 226, 154])
        self.v.select_xref(0, x)
        self.v.duplicate_selected()
        APP.processEvents()
        got = self.areas()
        self.assertEqual(len(got), 2)
        self.assertTrue(all(len(m["holes"]) == 1 for _x, m in got))
        self.assertAlmostEqual(self.summary()[("Area", "sq ft")], 30.0)
        items = legend.page_summary(self.v.doc, 0)
        self.assertAlmostEqual(sum(r.get("m2", 0) for r in items.values()) / FT ** 2, 30.0, 3)
        out = os.path.join(tempfile.mkdtemp(), "saved.pdf")
        self.v.doc.save(out)
        d = pymupdf.open(out)
        self.assertAlmostEqual(sum(r[4] for r in measure_ui.summary_rows(d)
                                   if r[0] == "Area"), 30.0)

    def test_on_a_turned_page_the_hole_is_where_it_was_drawn(self):
        self.v.doc[0].set_rotation(90)
        A.set_tool_props("m_area", dict(A.tool_props("m_area"), fill="#ffcc00"))
        self.addCleanup(lambda: A.reset_tool_props("m_area"))
        self.draw("m_area", sq(72, 72, 360, 360))
        self.draw("m_cutout", sq(144, 144, 216, 216))
        p = self.v.doc[0]
        pm = p.get_pixmap()
        at = P(180, 180) * p.rotation_matrix
        self.assertEqual(pm.pixel(int(at.x), int(at.y)), (255, 255, 255))
        at = P(300, 300) * p.rotation_matrix
        self.assertNotEqual(pm.pixel(int(at.x), int(at.y)), (255, 255, 255))


class AtScale(unittest.TestCase):
    def write_many(self, holes):
        d = pymupdf.open()
        p = d.new_page(width=3000, height=3000)
        M.set_scale(p, FT / 72, "ft", "1\" = 1'-0\"")
        t = time.perf_counter()
        for i in range(1000):
            x, y = (i % 40) * 70 + 10, (i // 40) * 110 + 10
            m = {"kind": "m_area", "props": dict(A.DEFAULTS["m_area"]),
                 "points": sq(x, y, x + 60, y + 100)}
            if holes:
                m["holes"] = [sq(x + 10, y + 10, x + 20, y + 20), sq(x + 30, y + 50, x + 50, y + 90)]
            A.write(p, m)
        return d, time.perf_counter() - t

    def test_a_thousand_areas_with_cut_outs(self):
        _d, plain = self.write_many(False)
        d, cut = self.write_many(True)
        t = time.perf_counter()
        rows = measure_ui.summary_rows(d)
        summed = time.perf_counter() - t
        (row,) = [r for r in rows if r[0] == "Area"]
        # (each 60 x 100 pt less 100 and 800 pt^2: 5,100 pt^2, an inch of paper a foot)
        self.assertAlmostEqual(row[4], 1000 * 5100 / 72 ** 2, 1)
        # (written with their cut-outs: about half as long again as without, 3.1 s and 2.1 s
        # here; the summary of all of them 0.3 s)
        self.assertLess(cut, plain * 2)
        self.assertLess(summed, 2.0)


if __name__ == "__main__":
    unittest.main()
