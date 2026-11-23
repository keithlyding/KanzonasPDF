"""Wall area from a length: Length and Polylength have a Height in Properties (as Volume's
Depth, in the page's unit; 0 for none). With one, the measurement shows the wall area too
(length x height), for drywall, paint, insulation and masonry, and the Measurement summary and
the Excel takeoff list it as a Wall area of its own. Without one, everything is as before.

The owner, 23 Nov 2026 (takeoff and quantity surveying, the third of seven): "A Length or
Polylength measurement with a Height setting (like Volume's Depth) that shows the wall area
(length x height) as well, for drywall, paint, insulation and masonry."

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_wall_area
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

from kanzonas import annotations as A, main_window, measure as M, measure_ui, takeoff  # noqa: E402

P = pymupdf.Point
FT = 0.3048


def page(unit="ft"):
    d = pymupdf.open()
    p = d.new_page(width=1200, height=900)
    M.set_scale(p, FT / 72, unit, "1\" = 1'-0\"")          # (an inch of paper is a foot)
    return d, p


class Values(unittest.TestCase):
    def test_label_and_takeoff(self):
        d, p = page()
        a = A.write(p, {"kind": "m_poly", "props": dict(A.DEFAULTS["m_poly"], height=8.0),
                        "points": [P(72, 72), P(792, 72), P(792, 432)]})       # (10 + 5 ft)
        self.assertIn("Wall area 120.00 sq ft", a.info["content"])
        rows = {(r[0], r[5]): r for r in measure_ui.summary_rows(d)}
        self.assertAlmostEqual(rows[("Polylength", "ft")][4], 15.0)
        self.assertAlmostEqual(rows[("Wall area", "sq ft")][4], 120.0)
        self.assertEqual(rows[("Wall area", "sq ft")][3], 1)

    def test_no_height_no_wall_area(self):
        d, p = page()
        a = A.write(p, {"kind": "m_length", "props": dict(A.DEFAULTS["m_length"]),
                        "points": [P(72, 72), P(792, 72)]})
        self.assertNotIn("Wall", a.info["content"])
        self.assertEqual([r[0] for r in measure_ui.summary_rows(d)], ["Length"])
        self.assertEqual(A.DEFAULTS["m_length"]["height"], 0.0)

    def test_feet_and_inches(self):
        d, p = page("ft-in")
        a = A.write(p, {"kind": "m_length", "props": dict(A.DEFAULTS["m_length"], height=9.5),
                        "points": [P(72, 72), P(792, 72)]})                    # (10 ft)
        self.assertIn("Wall area 95", a.info["content"])
        self.assertAlmostEqual(M.wall_area("m_length", [P(72, 72), P(792, 72)], p,
                                           {"height": 9.5})[0], 95.0)

    def test_a_length_made_before_reads_with_no_height(self):
        d, p = page()
        a = p.add_line_annot((72, 72), (792, 72))       # (another program's: no KZProps)
        a.update()
        self.assertIsNone(M.wall_area("m_length", [P(72, 72), P(792, 72)], p, {}))

    def test_in_the_excel_takeoff(self):
        from openpyxl import load_workbook
        d, p = page()
        A.write(p, {"kind": "m_length", "props": dict(A.DEFAULTS["m_length"], height=10.0),
                    "points": [P(72, 72), P(504, 72)]})                        # (6 ft)
        path = os.path.join(tempfile.mkdtemp(), "t.xlsx")
        takeoff.write_xlsx(d, path)
        items = [[c.value for c in r] for r in load_workbook(path)["Items"].iter_rows()][1:]
        self.assertEqual(sorted((r[2], r[5], r[6]) for r in items),
                         [("Length", 6.0, "ft"), ("Wall area", 60.0, "sq ft")])


class InProperties(unittest.TestCase):
    def setUp(self):
        self.addCleanup(lambda: [setattr(x, "_close_confirmed", True) or x.close()
                                 for x in main_window.windows()])
        self.addCleanup(lambda: A.reset_tool_props("m_length"))
        d, _p = page()
        path = os.path.join(tempfile.mkdtemp(), "plan.pdf")
        d.save(path)
        w = self.w = main_window.MainWindow()
        w.resize(1200, 900)
        w.show()
        w.open_file(path)
        APP.processEvents()
        self.v = w.view()
        self.addCleanup(lambda: setattr(self.v, "dirty", False))

    def test_height_for_the_next_ones_and_the_selected_one(self):
        self.w.set_tool("m_length")
        APP.processEvents()
        props = self.w.props
        self.assertTrue(props.rows["height"][1].isVisible())
        self.assertEqual(props.height.text(), "none")
        props.height.setValue(8)                # (the tool's: for the next lengths)
        APP.processEvents()
        self.v.apply_drag_tool(0, "m_length", P(72, 72), P(792, 72), False)
        APP.processEvents()
        (a,) = list(self.v.doc[0].annots())
        self.assertIn("Wall area 80.00 sq ft", a.info["content"])
        self.v.select_xref(0, a.xref)            # (selected: its own height changed)
        APP.processEvents()
        props.height.setValue(10)
        APP.processEvents()
        (a,) = list(self.v.doc[0].annots())
        self.assertIn("Wall area 100.00 sq ft", a.info["content"])
        self.v.undo()
        APP.processEvents()
        (a,) = list(self.v.doc[0].annots())
        self.assertIn("Wall area 80.00 sq ft", a.info["content"])

    def test_not_on_an_area(self):
        self.w.set_tool("m_area")
        APP.processEvents()
        self.assertFalse(self.w.props.rows["height"][1].isVisible())


class AtScale(unittest.TestCase):
    def write_many(self, height):
        d, p = page()
        p.set_mediabox(pymupdf.Rect(0, 0, 3000, 3000))
        t = time.perf_counter()
        for i in range(2000):
            x, y = (i % 40) * 70 + 10, (i // 40) * 55 + 10
            A.write(p, {"kind": "m_length",
                        "props": dict(A.DEFAULTS["m_length"], height=height),
                        "points": [P(x, y), P(x + 60, y)]})
        return d, time.perf_counter() - t

    def test_two_thousand_walls(self):
        _d, plain = self.write_many(0.0)
        d, walls = self.write_many(8.0)
        t = time.perf_counter()
        rows = {r[0]: r for r in measure_ui.summary_rows(d)}
        summed = time.perf_counter() - t
        self.assertAlmostEqual(rows["Wall area"][4], 2000 * 60 / 72 * 8, 1)
        # (a label line more: about as long as without, 3 s here; summed in 0.4 s)
        self.assertLess(walls, plain * 1.5)
        self.assertLess(summed, 3.0)


if __name__ == "__main__":
    unittest.main()
