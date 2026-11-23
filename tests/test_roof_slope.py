"""Slope for roof areas: an Area's Slope in Properties, a pitch typed as rise to run (6:12, 6/12)
or in degrees (30°), turns its plan area into the sloped area, for roofing and framing. The
label shows the sloped area and the plan area it's worked out from ("Sloped 1,341.64 sq ft",
"Plan 1,200.00 sq ft at 6:12"); the Measurement summary, the Excel takeoff and legends count the
sloped area (net of its cut-outs). Empty: a flat area, as before.

The owner, 23 Nov 2026 (takeoff and quantity surveying, the sixth of seven): "An optional pitch
on an Area (for example 6:12, or degrees) that turns the plan area into the sloped area, for
roofing and framing."

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_roof_slope
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

from kanzonas import annotations as A, legend, main_window, measure as M, measure_ui  # noqa: E402

P = pymupdf.Point
FT = 0.3048
SQ = [P(72, 72), P(792, 72), P(792, 792), P(72, 792)]     # (10 x 10 ft: 100 sq ft)


def page():
    d = pymupdf.open()
    p = d.new_page(width=1200, height=900)
    M.set_scale(p, FT / 72, "ft", "1\" = 1'-0\"")
    return d, p


class Factor(unittest.TestCase):
    def test_pitches(self):
        k, ang = M.slope_factor("6:12")
        self.assertAlmostEqual(k, math.sqrt(1 + 0.25))
        self.assertAlmostEqual(ang, math.degrees(math.atan(0.5)))
        self.assertAlmostEqual(M.slope_factor("6/12")[0], k)
        self.assertAlmostEqual(M.slope_factor("6 in 12")[0], k)
        self.assertAlmostEqual(M.slope_factor("30°")[0], 1 / math.cos(math.radians(30)))
        self.assertAlmostEqual(M.slope_factor("30 deg")[0], 1 / math.cos(math.radians(30)))
        self.assertAlmostEqual(M.slope_factor("12:12")[0], math.sqrt(2))

    def test_none_or_nonsense_is_flat(self):
        for t in ("", None, "steep", "6:0", "0:12", "95°", "-5°"):
            self.assertEqual(M.slope_factor(t), (1.0, 0.0), t)


class Values(unittest.TestCase):
    def test_label_summary_legend(self):
        d, p = page()
        a = A.write(p, {"kind": "m_area", "props": dict(A.DEFAULTS["m_area"], slope="6:12"),
                        "points": list(SQ)})
        self.assertIn("Sloped 111.80 sq ft", a.info["content"])
        self.assertIn("Plan 100.00 sq ft at 6:12", a.info["content"])
        rows = {r[0]: r for r in measure_ui.summary_rows(d)}
        self.assertAlmostEqual(rows["Area"][4], 111.8, 1)
        items = legend.page_summary(d, 0)
        self.assertAlmostEqual(sum(r["m2"] for r in items.values()) / FT ** 2, 111.80, 1)

    def test_with_a_cut_out(self):
        d, p = page()
        A.write(p, {"kind": "m_area", "props": dict(A.DEFAULTS["m_area"], slope="12:12"),
                    "points": list(SQ),
                    "holes": [[P(144, 144), P(216, 144), P(216, 216), P(144, 216)]]})
        rows = {r[0]: r for r in measure_ui.summary_rows(d)}
        self.assertAlmostEqual(rows["Area"][4], 99 * math.sqrt(2), 1)   # (net, then sloped)

    def test_flat_as_before(self):
        d, p = page()
        a = A.write(p, {"kind": "m_area", "props": dict(A.DEFAULTS["m_area"]), "points": list(SQ)})
        self.assertNotIn("Sloped", a.info["content"])
        self.assertAlmostEqual(measure_ui.summary_rows(d)[0][4], 100.0)


class InProperties(unittest.TestCase):
    def test_slope_typed_for_a_selected_area_with_undo(self):
        self.addCleanup(lambda: [setattr(x, "_close_confirmed", True) or x.close()
                                 for x in main_window.windows()])
        d, p = page()
        A.write(p, {"kind": "m_area", "props": dict(A.DEFAULTS["m_area"]), "points": list(SQ)})
        path = os.path.join(tempfile.mkdtemp(), "roof.pdf")
        d.save(path)
        w = main_window.MainWindow()
        w.resize(1200, 900)
        w.show()
        w.open_file(path)
        APP.processEvents()
        v = w.view()
        self.addCleanup(lambda: setattr(v, "dirty", False))
        w.set_tool("select")
        pg = v.doc[0]
        v.select_xref(0, next(iter(pg.annots())).xref)
        APP.processEvents()
        self.assertTrue(w.props.rows["slope"][1].isVisible())
        w.props.slope.setText("30°")
        w.props.slope.editingFinished.emit()
        APP.processEvents()
        self.assertAlmostEqual(measure_ui.summary_rows(v.doc)[0][4],
                               100 / math.cos(math.radians(30)), 1)
        v.undo()
        APP.processEvents()
        self.assertAlmostEqual(measure_ui.summary_rows(v.doc)[0][4], 100.0)
        w.set_tool("m_length")
        APP.processEvents()
        self.assertFalse(w.props.rows["slope"][1].isVisible())     # (an Area's only)


if __name__ == "__main__":
    unittest.main()
