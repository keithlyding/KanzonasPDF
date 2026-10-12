"""Angle, Radius, Perimeter and Volume measurements: their numbers, labels, totals, and that
they read back from the PDF as the same kind (so they stay editable).

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_new_measures
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf as F  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import annotations as A, measure as M, measure_ui  # noqa: E402
from kanzonas.document_view import DocumentView  # noqa: E402

P = F.Point


class NewMeasures(unittest.TestCase):
    def page(self):
        d = F.open()
        pg = d.new_page()
        M.set_scale(pg, M.scale_from_preset(48), "ft-in", '1/4" = 1\'-0"')   # 1 pt = 48/72 in
        return d, pg

    def roundtrip(self, pg, model):
        a = A.write(pg, model)
        back = A.read(pg.load_annot(a.xref))
        self.assertEqual(back["kind"], model["kind"])
        return back, a

    def test_numbers(self):
        _d, pg = self.page()
        self.assertAlmostEqual(M.angle([P(100, 0), P(0, 0), P(0, 100)]), 90.0)
        self.assertAlmostEqual(M.angle([P(100, 0), P(0, 0), P(-100, 1e-9)]), 180.0, places=4)
        self.assertEqual(M.measure_text("m_angle", [P(10, 0), P(0, 0), P(10, 10)], pg), "45.0°")
        # 72 pt at 1/4" scale = 4 ft
        self.assertEqual(M.measure_text("m_radius", [P(0, 0), P(72, 0)], pg),
                         "R 4'-0\"\nØ 8'-0\"")
        sq = [P(0, 0), P(72, 0), P(72, 72), P(0, 72)]                        # 4 ft x 4 ft
        self.assertEqual(M.measure_text("m_perimeter", sq, pg), "16'-0\"")
        self.assertEqual(M.measure_text("m_volume", sq, pg, props={"depth": 2.5}),
                         "40.00 cu ft\n16.00 sq ft × 2'-6\"")
        self.assertAlmostEqual(M.raw_values("m_volume", sq, pg, {"depth": 2.5})[0], 40.0)

    def test_written_and_read_back(self):
        d, pg = self.page()
        sq = [P(100, 100), P(172, 100), P(172, 172), P(100, 172)]
        for kind, pts in (("m_angle", [P(300, 100), P(200, 200), P(300, 200)]),
                          ("m_radius", [P(300, 400), P(372, 400)]),
                          ("m_perimeter", sq), ("m_volume", sq)):
            props = A.tool_props(kind)
            back, a = self.roundtrip(pg, {"kind": kind, "props": props, "points": pts,
                                          "rect": F.Rect()})
            self.assertEqual(len(back["points"]), len(pts))
            self.assertIn(A.LABELS[kind], a.info["content"])
        text = pg.get_text()
        self.assertIn("45.0", d[0].get_text() + text)
        self.assertIn("16'-0\"", text)
        # the radius circle is drawn: the annotation box holds the whole circle
        r = [a for a in pg.annots() if "Radius" in a.info["content"]][0].rect
        self.assertLessEqual(r.x0, 228 + 1)
        rows = {r[0]: r for r in measure_ui.summary_rows(d)}
        self.assertEqual(rows["Volume"][5], "cu ft")
        self.assertAlmostEqual(rows["Volume"][4], 16.0)                  # depth 1 ft

    def test_angle_tool_finishes_after_three_clicks(self):
        d = F.open()
        d.new_page()
        p = os.path.join(tempfile.mkdtemp(), "a.pdf")
        d.save(p)
        v = DocumentView(p)
        self.addCleanup(v.close_doc)
        v.tool = "m_angle"
        w = v.pages[0]
        from PySide6.QtCore import QEvent, QPointF, Qt
        from PySide6.QtGui import QMouseEvent
        for x, y in ((300, 100), (100, 100), (100, 300)):
            pos = QPointF(x, y)
            for kind, f in ((QEvent.MouseButtonPress, w.mousePressEvent),
                            (QEvent.MouseButtonRelease, w.mouseReleaseEvent)):
                f(QMouseEvent(kind, pos, w.mapToGlobal(pos), Qt.LeftButton,
                              Qt.LeftButton if kind == QEvent.MouseButtonPress else Qt.NoButton,
                              Qt.NoModifier))
        annots = list(v.doc[0].annots())
        self.assertEqual(len(annots), 1)
        self.assertIn("90.0", annots[0].info["content"])


if __name__ == "__main__":
    unittest.main()
