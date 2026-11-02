"""Break-it tests for 1.6.3's engine: the new markup kinds (circle, mask, arc, curve, bent lines,
trimmed shapes and open clouds, click-click drawing) through undo, the content renders and the
speed budgets.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_battery_163_engine
"""
import os
import random
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402
from PySide6.QtCore import QPointF  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import annotations as A  # noqa: E402
from kanzonas import cad_select, page_objects  # noqa: E402
from kanzonas.document_view import DocumentView  # noqa: E402

P = pymupdf.Point


def sheet(n, seed=7):
    """A drawing of n short lines (as a CAD export's), saved; its path."""
    rnd = random.Random(seed)
    out = [b"1 0 0 -1 0 800 cm 0.35 w 0.2 0.4 0.1 RG"]
    for _ in range(n):
        x, y = rnd.uniform(20, 1100), rnd.uniform(20, 700)
        out.append(b"%.2f %.2f m %.2f %.2f l S" % (x, y, x + rnd.uniform(-40, 40), y))
    d = pymupdf.open()
    pg = d.new_page(width=1200, height=800)
    x = d.get_new_xref()
    d.update_object(x, "<<>>")
    d.update_stream(x, b"\n".join(out))
    pg.set_contents(x)
    path = os.path.join(tempfile.mkdtemp(), "sheet.pdf")
    d.save(path, deflate=True)
    d.close()
    return path


def best_of(fn, n=5):
    fn()
    best = 1e9
    for _ in range(n):
        t = time.perf_counter()
        fn()
        best = min(best, time.perf_counter() - t)
    return best


class Speed(unittest.TestCase):
    """What's drawn on each paint in CAD mode stays quick (1.6.2's times in brackets)."""

    def setUp(self):
        for key in ("mouse_mode", "cad_select"):
            self.addCleanup(setattr, DocumentView, key, getattr(DocumentView, key))
        DocumentView.mouse_mode = "cad"
        DocumentView.cad_select = True

    def view(self, path):
        v = DocumentView(path)
        self.addCleanup(lambda: (setattr(v, "dirty", False), v.doc.is_closed or v.close_doc()))
        self.addCleanup(v.hide)
        v.resize(1300, 900)
        v.show()
        APP.processEvents()
        v.set_zoom(1.0)
        APP.processEvents()
        v.set_tool("editobjects")
        return v

    def test_a_big_selection_of_drawing_objects_repaints_quickly(self):
        # 1.6.3 drew the selection dashed over a white line with round ends: Qt strokes a
        # path of many pieces with round ends very slowly (2,500 lines: 380 ms a paint, on
        # every hover or repaint while they were selected) [3 ms]
        v = self.view(sheet(6000))
        items = v.cad_objects(0, page_objects.Box(pymupdf.Rect(-5, -5, 1300, 900)), False)
        v.select_objects(0, items[:2500])
        w = v.pages[0]
        took = best_of(w.repaint)
        self.assertLess(took, 0.06, "%.0f ms a paint" % (took * 1000))

    def test_many_markups_selected_in_cad_mode_repaint_quickly(self):
        # (1,000 ms a paint in 1.6.3 for 2,000 selected markups, the same round ends) [72 ms]
        d = pymupdf.open()
        pg = d.new_page()
        for i in range(2000):
            x, y = 20 + (i % 40) * 14, 20 + (i // 40) * 15
            pg.add_rect_annot(pymupdf.Rect(x, y, x + 10, y + 10))
        path = os.path.join(tempfile.mkdtemp(), "marks.pdf")
        d.save(path)
        v = self.view(path)
        page = v.doc[0]
        xs = [a.xref for a in A.each_annot(page)]
        del page
        v._set_selection(0, xs)
        took = best_of(v.pages[0].repaint)
        self.assertLess(took, 0.15, "%.0f ms a paint" % (took * 1000))

    def test_the_box_preview_glow_on_a_heavy_sheet(self):
        # the glow over what a box would take is drawn again on every pointer move: each
        # point was put on the screen by loading the page again (3,000 lines: 330 ms a
        # paint, 370 ms in 1.6.2); a 15,000-piece command preview has 80 ms
        v = self.view(sheet(20000))
        w = v.pages[0]
        lines = []
        for got, _rects in v.cad_preview_steps(0, page_objects.Box(
                pymupdf.Rect(-5, -5, 1300, 900)), False):
            lines += got
        self.assertGreaterEqual(len(lines), cad_select.LIMIT)
        w._cad_down = {"start": QPointF(1, 1), "pts": [QPointF(1, 1)], "dir": 1,
                       "mode": "box", "now": QPointF(1250, 850), "target": None,
                       "remove": False, "t": 0, "link": False}
        self.addCleanup(setattr, w, "_cad_down", None)
        w._cad_preview = (False, lines[:cad_select.LIMIT], [])
        self.addCleanup(setattr, w, "_cad_preview", None)
        took = best_of(w.repaint)
        self.assertLess(took, 0.08, "%.0f ms a paint" % (took * 1000))


if __name__ == "__main__":
    unittest.main()
