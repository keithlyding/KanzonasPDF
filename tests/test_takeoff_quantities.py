"""A quantity per count, and waste. A Count group can have quantities per counted item (Properties
> Quantities and waste...: "each fixture = 2 boxes + 1 whip", each item with its own unit) and a
waste or extra percent; a Length, Polylength, Area, Perimeter or Volume has its own Waste / extra
in Properties. The Measurement summary and the Excel takeoff show the counts, each item's
resulting quantity (a row of its own, in the group's name) and the quantities with waste added.
The group's setup is kept in the document (its catalog), with undo.

The owner, 23 Nov 2026 (takeoff and quantity surveying, the fifth of seven): "For a Count group:
an optional quantity per item ("each fixture = 2 boxes + 1 whip", with its own items and units)
and a waste or extra percentage for a group or measurement. The summary and the Excel export
show the counts and the resulting quantities."

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_takeoff_quantities
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


def doc_with_counts(n=4):
    d = pymupdf.open()
    p = d.new_page(width=1200, height=900)
    M.set_scale(p, FT / 72, "ft", "1\" = 1'-0\"")
    for i in range(n):
        A.write(p, {"kind": "m_count", "props": dict(A.DEFAULTS["m_count"], group="Fixtures"),
                    "points": [P(100 + 50 * i, 100)], "n": i + 1})
    return d, p


class Rows(unittest.TestCase):
    def test_items_per_count_and_waste(self):
        d, p = doc_with_counts(4)
        takeoff.set_group_setup(d, "Fixtures", [("Box", 2, "ea"), ("Whip", 1, "ea")], 10)
        A.write(p, {"kind": "m_area", "props": dict(A.DEFAULTS["m_area"], waste=5),
                    "points": [P(72, 200), P(360, 200), P(360, 488), P(72, 488)]})    # (16 sq ft)
        rows = {(r[0], r[1]): r for r in measure_ui.summary_rows(d)}
        self.assertEqual(rows[("Count", "Fixtures")][3:7], (4, 4, "count", 4.4))
        self.assertEqual(rows[("Box", "Fixtures")][3:7], (4, 8.0, "ea", 8.8))
        self.assertEqual(rows[("Whip", "Fixtures")][3:7], (4, 4.0, "ea", 4.4))
        self.assertEqual(rows[("Area", "")][4:7], (16.0, "sq ft", 16.8))

    def test_none_set_as_before(self):
        d, _p = doc_with_counts(3)
        (row,) = measure_ui.summary_rows(d)
        self.assertEqual(row, ("Count", "Fixtures", "1", 3, 3, "count", ""))
        self.assertEqual(takeoff.group_setup(d, "Fixtures"), ([], 0.0))

    def test_bad_settings_are_left_out(self):
        d, _p = doc_with_counts(1)
        d.xref_set_key(d.pdf_catalog(), takeoff.SETTINGS_KEY, pymupdf.get_pdf_str(
            '{"groups": {"Fixtures": {"items": [{"name": "Box", "qty": "x"}, '
            '{"name": "", "qty": 1}, {"name": "Whip", "qty": -1}, {"name": "Tag", "qty": 3}], '
            '"waste": "lots"}}}'))
        self.assertEqual(takeoff.group_setup(d, "Fixtures"), ([("Tag", 3.0, "")], 0.0))
        d.xref_set_key(d.pdf_catalog(), takeoff.SETTINGS_KEY, pymupdf.get_pdf_str("not json"))
        self.assertEqual(takeoff.settings(d), {})

    def test_saved_with_the_document(self):
        d, _p = doc_with_counts(2)
        takeoff.set_group_setup(d, "Fixtures", [("Box", 2, "ea")], 0)
        d2 = pymupdf.open("pdf", d.tobytes())
        self.assertEqual(takeoff.group_setup(d2, "Fixtures"), ([("Box", 2.0, "ea")], 0.0))
        takeoff.set_group_setup(d2, "Fixtures", [], 0)              # (nothing: taken out)
        self.assertNotIn("Fixtures", takeoff.settings(d2).get("groups", {}))

    def test_in_the_excel_takeoff(self):
        from openpyxl import load_workbook
        d, _p = doc_with_counts(2)
        takeoff.set_group_setup(d, "Fixtures", [("Box", 2, "ea")], 50)
        path = os.path.join(tempfile.mkdtemp(), "t.xlsx")
        takeoff.write_xlsx(d, path)
        wb = load_workbook(path)
        summary = [[c.value for c in r] for r in wb["Summary"].iter_rows()]
        self.assertEqual(summary[0][-1], "With waste")
        self.assertIn(["Box", "Fixtures", "1", 2, 4, "ea", 6], summary)
        items = [[c.value for c in r] for r in wb["Items"].iter_rows()][1:]
        self.assertIn(["Page 1", None, "Box", "Fixtures", None, 2, "ea", 50, 3], items)


class InTheWindow(unittest.TestCase):
    def setUp(self):
        self.addCleanup(lambda: [setattr(x, "_close_confirmed", True) or x.close()
                                 for x in main_window.windows()])
        d, _p = doc_with_counts(3)
        path = os.path.join(tempfile.mkdtemp(), "plan.pdf")
        d.save(path)
        w = self.w = main_window.MainWindow()
        w.resize(1200, 900)
        w.show()
        w.open_file(path)
        APP.processEvents()
        self.v = w.view()
        self.addCleanup(lambda: setattr(self.v, "dirty", False))

    def test_quantities_and_waste_from_properties_with_undo(self):
        w, v = self.w, self.v
        w.set_tool("select")
        pg = v.doc[0]
        v.select_xref(0, next(iter(pg.annots())).xref)
        APP.processEvents()
        self.assertTrue(w.props.rows["setup"][1].isVisible())

        def answer(dlg):
            self.assertIn("Fixtures", dlg.windowTitle())
            dlg.add_row("Box", 2, "ea")
            dlg.add_row("Whip", "", "ea")            # (no number: left out)
            dlg.waste.setValue(10)
            return True
        w.run_count_setup = answer
        w.props.count_setup.click()
        APP.processEvents()
        self.assertEqual(takeoff.group_setup(v.doc, "Fixtures"), ([("Box", 2.0, "ea")], 10.0))
        v.undo()
        APP.processEvents()
        self.assertEqual(takeoff.group_setup(v.doc, "Fixtures"), ([], 0.0))
        v.redo()
        APP.processEvents()
        self.assertEqual(takeoff.group_setup(v.doc, "Fixtures"), ([("Box", 2.0, "ea")], 10.0))

    def test_waste_on_a_measurement(self):
        w, v = self.w, self.v
        self.addCleanup(lambda: A.reset_tool_props("m_length"))
        w.set_tool("m_length")
        APP.processEvents()
        self.assertTrue(w.props.rows["waste"][1].isVisible())
        w.props.waste.setValue(15)
        APP.processEvents()
        v.apply_drag_tool(0, "m_length", P(72, 500), P(792, 500), False)     # (10 ft)
        APP.processEvents()
        rows = {r[0]: r for r in measure_ui.summary_rows(v.doc)}
        self.assertAlmostEqual(rows["Length"][6], 11.5)

    def test_not_for_a_markup(self):
        self.w.set_tool("rect")
        APP.processEvents()
        self.assertFalse(self.w.props.rows["waste"][1].isVisible())
        self.assertFalse(self.w.props.rows["setup"][1].isVisible())


class AtScale(unittest.TestCase):
    def test_three_thousand_counts_with_items(self):
        d = pymupdf.open()
        p = d.new_page(width=3000, height=3000)
        for i in range(3000):
            A.write(p, {"kind": "m_count",
                        "props": dict(A.DEFAULTS["m_count"], group="G%d" % (i % 6)),
                        "points": [P((i % 60) * 48 + 10, (i // 60) * 55 + 10)], "n": i})
        for g in range(6):
            takeoff.set_group_setup(d, "G%d" % g, [("A", 2, "ea"), ("B", 0.5, "ft")], 5)
        t = time.perf_counter()
        rows = takeoff.items(d)
        took = time.perf_counter() - t
        self.assertEqual(len(rows), 9000)
        self.assertLess(took, 4.0)          # (the group setup read once: about 1 s here)


if __name__ == "__main__":
    unittest.main()
