"""Measurement summary > Export Excel... (takeoff.py): the takeoff as an .xlsx workbook. Summary
(as the Measurement summary lists it), By sheet and By space (each group's measurements by kind
and Count group with quantities, units and a subtotal of each unit, then the document's totals)
and Items (every measurement on a row, with filters). Areas and volumes are net of their
cut-outs; names from the PDF are written as text, never as formulas. Export CSV... stays.

The owner, 23 Nov 2026 (takeoff and quantity surveying, the second of seven): "Export the
Measurement summary to .xlsx (openpyxl is already a lazy-loaded dependency), grouped by sheet,
by Space and by Count group or measurement kind, with quantities, units and subtotals. Keep the
CSV export."

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_takeoff_excel
"""
import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402
from openpyxl import load_workbook  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import annotations as A, measure as M, measure_ui, takeoff  # noqa: E402

P = pymupdf.Point
FT = 0.3048


def sq(x0, y0, x1, y1):
    return [P(x0, y0), P(x1, y0), P(x1, y1), P(x0, y1)]


def add(page, kind, **kw):
    m = {"kind": kind, "props": dict(A.DEFAULTS[kind]), "rect": pymupdf.Rect()}
    m["props"].update(kw.pop("props", {}))
    m.update(kw)
    return A.write(page, m)


def takeoff_doc():
    """Two sheets (A-101, A-102) at an inch of paper to the foot. A-101: a space "Kitchen" with
    an area (4 x 4 ft less a 1 x 1 ft cut-out) and two outlets in it, a length outside it; a
    second space named like a formula. A-102: an area of 2 x 3 ft and an outlet."""
    d = pymupdf.open()
    for _ in range(2):
        M.set_scale(d.new_page(width=1200, height=900), FT / 72, "ft", "1\" = 1'-0\"")
    d.set_page_labels([{"startpage": 0, "prefix": "A-", "style": "D", "firstpagenum": 101}])
    p = d[0]
    add(p, "polygon", points=sq(50, 50, 500, 500), text="Kitchen",
        props=dict(A.DEFAULTS["space"]))
    add(p, "polygon", points=sq(600, 50, 900, 300), text="=HYPERLINK(\"x\")",
        props=dict(A.DEFAULTS["space"]))
    add(p, "m_area", points=sq(72, 72, 360, 360), holes=[sq(144, 144, 216, 216)])
    add(p, "m_count", points=[P(100, 450)], n=1, props={"group": "Outlets"})
    add(p, "m_count", points=[P(200, 450)], n=2, props={"group": "Outlets"})
    add(p, "m_length", points=[P(600, 600), P(816, 600)])          # (3 ft, in no space)
    add(p, "m_count", points=[P(700, 200)], n=3, props={"group": "Outlets"})   # (in "=...")
    p = d[1]
    add(p, "m_area", points=sq(72, 72, 216, 288))                  # (2 x 3 ft)
    add(p, "m_count", points=[P(400, 400)], n=4, props={"group": "Outlets"})
    return d


def cells(ws):
    """The worksheet's values, row by row (an empty cell reads back as "")."""
    return [["" if c.value is None else c.value for c in row] for row in ws.iter_rows()]


class Items(unittest.TestCase):
    def test_each_measurement_with_its_sheet_and_space(self):
        rows = takeoff.items(takeoff_doc())
        got = sorted((r["sheet"], r["space"], r["type"], r["group"], round(r["value"], 3),
                      r["unit"]) for r in rows)
        self.assertIn(("A-101 (Page 1)", "Kitchen", "Area", "", 15.0, "sq ft"), got)
        self.assertIn(("A-101 (Page 1)", "", "Length", "", 3.0, "ft"), got)
        self.assertIn(("A-102 (Page 2)", "", "Area", "", 6.0, "sq ft"), got)
        self.assertEqual(sum(1 for g in got if g[3] == "Outlets"), 4)
        self.assertEqual(sum(1 for g in got if g[1] == "Kitchen" and g[3] == "Outlets"), 2)

    def test_the_summary_is_as_before(self):
        d = takeoff_doc()
        self.assertEqual(measure_ui.summary_rows(d), takeoff.summary(takeoff.items(d)))
        rows = {(r[0], r[1]): r for r in measure_ui.summary_rows(d)}
        self.assertEqual(rows[("Area", "")][4], 21.0)               # (15 net + 6)
        self.assertEqual(rows[("Count", "Outlets")][3:5], (4, 4))


class Workbook(unittest.TestCase):
    def setUp(self):
        self.path = os.path.join(tempfile.mkdtemp(), "takeoff.xlsx")
        self.n = takeoff.write_xlsx(takeoff_doc(), self.path)
        self.wb = load_workbook(self.path)

    def test_its_worksheets(self):
        self.assertEqual(self.n, 7)
        self.assertEqual(self.wb.sheetnames, ["Summary", "By sheet", "By space", "Items"])
        self.assertTrue(self.wb.calculation.fullCalcOnLoad)       # (Excel works out SUBTOTALs)

    def test_by_sheet_has_each_sheet_its_rows_and_subtotals(self):
        rows = cells(self.wb["By sheet"])
        self.assertEqual(rows[0][:6], ["Sheet", "Type", "Group", "Items", "Quantity", "Unit"])
        heads = [r[0] for r in rows if r[0]]
        self.assertEqual(heads[1:3], ["A-101 (Page 1)", "A-102 (Page 2)"])
        a101 = rows.index(["A-101 (Page 1)"] + [""] * (len(rows[0]) - 1))
        block = rows[a101 + 1:rows.index(["A-102 (Page 2)"] + [""] * (len(rows[0]) - 1))]
        self.assertIn(["", "Area", "", 1, 15.0, "sq ft"], [r[:6] for r in block])
        self.assertIn(["", "Count", "Outlets", 3, 3, "count"], [r[:6] for r in block])
        subs = [r for r in block if r[1] == "Subtotal"]
        self.assertEqual(sorted(r[5] for r in subs), ["count", "ft", "sq ft"])
        self.assertTrue(all(str(r[4]).startswith("=SUBTOTAL(9,E") for r in subs))
        total = rows[rows.index(["Total"] + [""] * (len(rows[0]) - 1)):]
        self.assertIn(["", "Area", "", 2, 21.0, "sq ft"], [r[:6] for r in total])

    def test_by_space_groups_across_sheets(self):
        rows = cells(self.wb["By space"])
        heads = [r[0] for r in rows[1:] if r[0] and r[0] != "Total"]
        self.assertEqual(sorted(heads), sorted(["Kitchen", "=HYPERLINK(\"x\")", "(no space)"]))

    def test_names_from_the_pdf_are_text_not_formulas(self):
        ws = self.wb["By space"]
        got = [c for row in ws.iter_rows() for c in row if c.value == "=HYPERLINK(\"x\")"]
        self.assertTrue(got)
        self.assertTrue(all(c.data_type == "s" for c in got))
        ws = self.wb["Items"]
        got = [c for row in ws.iter_rows() for c in row if c.value == "=HYPERLINK(\"x\")"]
        self.assertTrue(got and all(c.data_type == "s" for c in got))

    def test_items_every_measurement_with_filters(self):
        ws = self.wb["Items"]
        rows = cells(ws)
        self.assertEqual(rows[0], ["Sheet", "Space", "Type", "Group", "Subject", "Quantity",
                                   "Unit"])
        self.assertEqual(len(rows) - 1, 7)
        self.assertEqual(ws.auto_filter.ref, "A1:G8")
        self.assertIn(["A-101 (Page 1)", "Kitchen", "Area", "", "", 15.0, "sq ft"], rows)


class InTheDialog(unittest.TestCase):
    def test_export_excel_and_csv_stays(self):
        dlg = measure_ui.SummaryDialog(None, takeoff_doc())
        path = os.path.join(tempfile.mkdtemp(), "out")
        dlg.ask_excel_path = lambda: path + ".xlsx"
        dlg.excel_button.click()
        self.assertEqual(load_workbook(path + ".xlsx").sheetnames[0], "Summary")
        self.assertTrue(any(b.text() == "Export CSV..." for b in dlg.findChildren(
            type(dlg.excel_button))))
        dlg.close()

    def test_openpyxl_isnt_loaded_until_a_workbook_is_written(self):
        import subprocess
        code = ("import sys, os; os.environ['QT_QPA_PLATFORM']='offscreen'; "
                "from kanzonas import takeoff, measure_ui; "
                "print('openpyxl' in sys.modules)")
        out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                             cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.assertEqual(out.stdout.strip().splitlines()[-1], "False")


class AtScale(unittest.TestCase):
    def test_three_thousand_measurements(self):
        d = pymupdf.open()
        for k in range(3):
            p = d.new_page(width=3000, height=3000)
            M.set_scale(p, FT / 72, "ft", "1\" = 1'-0\"")
            for s in range(4):
                add(p, "polygon", points=sq(s * 700, 0, s * 700 + 690, 3000), text="Room %d" % s,
                    props=dict(A.DEFAULTS["space"]))
            for i in range(1000):
                x, y = (i % 40) * 70 + 10, (i // 40) * 110 + 10
                if i % 2:
                    add(p, "m_count", points=[P(x, y)], n=i, props={"group": "G%d" % (i % 5)})
                else:
                    add(p, "m_area", points=sq(x, y, x + 60, y + 100))
        t = time.perf_counter()
        n = takeoff.write_xlsx(d, os.path.join(tempfile.mkdtemp(), "big.xlsx"))
        took = time.perf_counter() - t
        self.assertEqual(n, 3000)
        self.assertLess(took, 10.0)       # (about 2 s here)


if __name__ == "__main__":
    unittest.main()
