"""Drops on runs: a Polylength's vertical lengths (drops, rises) at chosen points, for conduit,
wire and pipe runs, so its total includes the vertical runs the plan doesn't show. Right-click
near one of a selected Polylength's points > Add drop or rise..., then the length; Change this
drop... and Remove this drop. Each one is named at its point on the markup ("Drop 10.00 ft");
the label shows the total with "including 2 drops, 20.00 ft"; the Measurement summary, the Excel
takeoff and legends count the total. Kept in meters by point number, so a move, copy, turn or a
change of scale keeps them where they are; Set as Default doesn't copy them.

The owner, 23 Nov 2026 (takeoff and quantity surveying, the fourth of seven): "On a
Polylength, add a vertical length (a drop or rise) at chosen points, for conduit, wire and pipe
runs, so the total includes the vertical runs the plan doesn't show. Show the drops on the
markup and in the summary."

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_poly_drops
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

from kanzonas import annotations as A, legend, main_window, measure as M, measure_ui  # noqa: E402

P = pymupdf.Point
FT = 0.3048
RUN = [P(72, 72), P(792, 72), P(792, 432)]           # (10 ft + 5 ft at an inch to the foot)


def page():
    d = pymupdf.open()
    p = d.new_page(width=1200, height=900)
    M.set_scale(p, FT / 72, "ft", "1\" = 1'-0\"")
    return d, p


def poly(p, drops=()):
    return A.write(p, {"kind": "m_poly", "props": dict(A.DEFAULTS["m_poly"],
                                                       drops=[list(d) for d in drops]),
                       "points": list(RUN)})


class Values(unittest.TestCase):
    def test_the_total_has_them(self):
        d, p = page()
        a = poly(p, [(0, 10 * FT), (2, 2 * FT)])
        self.assertIn("27.00 ft", a.info["content"])
        self.assertIn("including 2 drops, 12.00 ft", a.info["content"])
        rows = {r[0]: r for r in measure_ui.summary_rows(d)}
        self.assertAlmostEqual(rows["Polylength"][4], 27.0)
        items = legend.page_summary(d, 0)
        self.assertAlmostEqual(sum(r["m"] for r in items.values()) / FT, 27.0, 3)
        drawn = p.get_text()
        self.assertIn("Drop 10.00 ft", drawn)           # (named at its point, in its drawing)
        self.assertIn("Drop 2.00 ft", drawn)

    def test_none_as_before(self):
        d, p = page()
        a = poly(p)
        self.assertIn("15.00 ft", a.info["content"])
        self.assertNotIn("drop", a.info["content"])

    def test_bad_ones_are_left_out(self):
        self.assertEqual(M.drops_m({"drops": [[5, 1.0], [1, -2], ["x", 1], [0, 0.5]]}, 3),
                         [(0, 0.5)])

    def test_in_the_excel_takeoff(self):
        import tempfile as tf
        from openpyxl import load_workbook
        from kanzonas import takeoff
        d, p = page()
        poly(p, [(1, 4 * FT)])
        path = os.path.join(tf.mkdtemp(), "t.xlsx")
        takeoff.write_xlsx(d, path)
        items = [[c.value for c in r] for r in load_workbook(path)["Items"].iter_rows()][1:]
        self.assertEqual([(r[2], r[5]) for r in items], [("Polylength", 19.0)])


class InTheWindow(unittest.TestCase):
    def setUp(self):
        self.addCleanup(lambda: [setattr(x, "_close_confirmed", True) or x.close()
                                 for x in main_window.windows()])
        d, p = page()
        poly(p)
        path = os.path.join(tempfile.mkdtemp(), "plan.pdf")
        d.save(path)
        w = self.w = main_window.MainWindow()
        w.resize(1200, 900)
        w.show()
        w.open_file(path)
        APP.processEvents()
        v = self.v = w.view()
        self.addCleanup(lambda: setattr(v, "dirty", False))
        pg = v.doc[0]
        self.x = next(iter(pg.annots())).xref
        w.set_tool("select")            # (the Hand's right-click menu only moves around)
        APP.processEvents()
        v.select_xref(0, self.x)
        APP.processEvents()

    def model(self):
        page = self.v.doc[0]            # (kept alive while its markup is read)
        (a,) = list(page.annots())
        return a.xref, A.read(a), a.info["content"]

    def test_added_changed_removed_and_undone(self):
        v = self.v
        k = v.poly_point_at(0, self.x, P(790, 74))
        self.assertEqual(k, 1)
        self.assertIsNone(v.poly_point_at(0, self.x, P(400, 300)))
        v.set_drop(0, self.x, 1, 10 * FT)
        x, m, content = self.model()
        self.assertEqual(m["props"]["drops"], [[1, 10 * FT]])
        self.assertIn("25.00 ft", content)
        v.set_drop(0, x, 1, 3 * FT)                    # (changed: one drop at a point)
        x, m, content = self.model()
        self.assertIn("18.00 ft", content)
        v.set_drop(0, x, 1, None)
        x, m, content = self.model()
        self.assertEqual(m["props"]["drops"], [])
        self.assertIn("15.00 ft", content)
        v.undo()
        APP.processEvents()
        self.assertIn("18.00 ft", self.model()[2])

    def test_asked_from_the_right_click_menu(self):
        from unittest import mock
        from PySide6.QtCore import QPoint
        from PySide6.QtWidgets import QMenu
        v = self.v
        v.ask_drop = lambda default: 6 * FT
        seen = []

        class Menu(QMenu):
            def exec(self, *_a):
                seen.extend(self.actions())
        ev = mock.Mock()
        ev.globalPosition.return_value.toPoint.return_value = QPoint(0, 0)
        with mock.patch("PySide6.QtWidgets.QMenu", Menu):
            v.pages[0]._content_menu(ev, P(791, 73))        # (by the second point)
        acts = {a.text(): a for a in seen}
        self.assertIn("Add drop or rise...", acts)
        acts["Add drop or rise..."].trigger()
        APP.processEvents()
        self.assertIn("21.00 ft", self.model()[2])
        x = self.model()[0]
        v.select_xref(0, x)
        seen.clear()
        with mock.patch("PySide6.QtWidgets.QMenu", Menu):
            v.pages[0]._content_menu(ev, P(791, 73))
        acts = {a.text(): a for a in seen}
        self.assertIn("Change this drop...", acts)
        acts["Remove this drop"].trigger()
        APP.processEvents()
        self.assertIn("15.00 ft", self.model()[2])

    def test_moved_copied_and_not_made_a_default(self):
        v = self.v
        v.set_drop(0, self.x, 0, 5 * FT)
        x, _m, _c = self.model()
        v.select_xref(0, x)
        v.nudge(10, 0, 1.0)
        APP.processEvents()
        x, m, content = self.model()
        self.assertEqual(m["props"]["drops"], [[0, 5 * FT]])
        self.assertIn("20.00 ft", content)
        v.select_xref(0, x)
        v.set_selected_as_default()
        self.addCleanup(lambda: A.reset_tool_props("m_poly"))
        self.assertEqual(A.tool_props("m_poly")["drops"], [])
        v.select_xref(0, x)
        v.duplicate_selected()
        APP.processEvents()
        page = v.doc[0]
        got = [A.read(a) for a in page.annots()]
        self.assertEqual([g["props"]["drops"] for g in got], [[[0, 5 * FT]]] * 2)


class AtScale(unittest.TestCase):
    def write_many(self, drops):
        d, p = page()
        p.set_mediabox(pymupdf.Rect(0, 0, 3000, 3000))
        t = time.perf_counter()
        for i in range(2000):
            x, y = (i % 40) * 70 + 10, (i // 40) * 55 + 10
            A.write(p, {"kind": "m_poly",
                        "props": dict(A.DEFAULTS["m_poly"], drops=drops),
                        "points": [P(x, y), P(x + 30, y), P(x + 30, y + 20)]})
        return d, time.perf_counter() - t

    def test_two_thousand_runs_with_drops(self):
        _d, plain = self.write_many([])
        d, dropped = self.write_many([[0, FT], [2, 2 * FT]])
        t = time.perf_counter()
        rows = {r[0]: r for r in measure_ui.summary_rows(d)}
        summed = time.perf_counter() - t
        self.assertAlmostEqual(rows["Polylength"][4], 2000 * (50 / 72 + 3), 1)
        # (two labels more each: within twice the time of plain runs; summed in under 3 s)
        self.assertLess(dropped, plain * 2)
        self.assertLess(summed, 3.0)


if __name__ == "__main__":
    unittest.main()
