"""Speed work of 1.5, checked for being right: after a move, copy, array, trim or delete the
page's objects are worked out from the edit instead of reading the whole drawing again, and
they must be exactly what a fresh read gives (the lines carried over too); big arrays are
copies by reference (one drawing group placed again and again) and must look the same as
written-out copies; the quick reader of plain shapes must read them as the full one does;
in CAD mode the page is made ready while nothing happens.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_speed_15
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

from kanzonas import page_objects as po  # noqa: E402
from kanzonas.document_view import DocumentView  # noqa: E402

P = pymupdf.Point


def drawing():
    d = pymupdf.open()
    p = d.new_page(width=400, height=400)
    p.draw_line((10, 10), (40, 30), color=(1, 0, 0), width=2, dashes="[3 2] 0")
    p.draw_rect(pymupdf.Rect(12, 35, 30, 50), color=(0, 0, 1), fill=(0, 1, 0), width=1.5)
    p.draw_circle((50, 20), 8, color=(0.5, 0, 0.5), width=0.7)
    p.draw_polyline([(60, 60), (90, 60), (90, 90)], color=(0, 0, 0), width=1)
    return d, p


def summary(objs):
    return [(it["n"], it["kind"], tuple(round(v, 2) for v in it["rect"]),
             [[(round(q.x, 2), round(q.y, 2)) for q in line] for line in objs.lines(it)])
            for it in objs.items]


class Incremental(unittest.TestCase):
    def check(self, page, got):
        self.assertIsNotNone(got)
        fresh = po.Objects(page)
        self.assertEqual(summary(got), summary(fresh))
        self.assertEqual([(f["start"], f["end"]) for f in got.found],
                         [(f["start"], f["end"]) for f in fresh.found])

    def read_all(self, objs):
        for it in objs.items:
            objs.lines(it)              # (lines read before the edit carry over after it)
        return objs

    def test_move_copy_array_trim_delete_match_a_fresh_read(self):
        d, p = drawing()
        objs = self.read_all(po.Objects(p))
        ns = [it["n"] for it in objs.items]
        got = po.transform(p, ns[:2], pymupdf.Matrix(1, 0, 0, 1, 30, 5), objs)
        self.check(p, got)
        got = po.copies(p, [got.items[0]["n"], got.items[2]["n"]],
                        [pymupdf.Matrix(1, 0, 0, 1, 0, 100), pymupdf.Matrix(1, 0, 0, 1, 100, 0)],
                        self.read_all(got))
        self.check(p, got)
        mats = [pymupdf.Matrix(1, 0, 0, 1, 40 * c, 40 * r) for r in range(3) for c in range(3)
                if r or c]
        got = po.block_copies(p, [it["n"] for it in got.items[:3]], mats, self.read_all(got))
        self.check(p, got)
        line = next(it for it in got.items if it["kind"] == "shape" and not it["fill"])
        state, parts, paint = po.subpaths(got.data, line["obj"])
        got = po.rewrite_path(p, line["n"], state, [parts[0][0]], paint, self.read_all(got))
        self.check(p, got)
        got = po.delete(p, [got.items[-1]["n"]], self.read_all(got))
        self.check(p, got)

    def test_copies_by_reference_look_like_written_out_copies(self):
        mats = [pymupdf.Matrix(1, 0, 0, 1, 60 * c, 70 * r) for r in range(4) for c in range(5)
                if r or c]
        pix = []
        for make in (po.copies, po.block_copies):
            d, p = drawing()
            objs = po.Objects(p)
            make(p, [it["n"] for it in objs.items], mats, objs)
            pix.append(p.get_pixmap(dpi=72).samples)
            path = os.path.join(tempfile.mkdtemp(), "a.pdf")
            d.save(path)
            self.assertEqual(pymupdf.open(path)[0].get_pixmap(dpi=72).samples, pix[-1])
        self.assertEqual(pix[0], pix[1])

    def test_the_quick_reader_reads_shapes_as_the_full_one(self):
        d, p = drawing()
        objs = po.Objects(p)
        quick = po._path_tokens
        for it in objs.items:
            a = po.path_lines(objs.data, it["obj"], objs.tm), po.subpaths(objs.data, it["obj"])
            po._path_tokens = lambda raw: None
            try:
                b = (po.path_lines(objs.data, it["obj"], objs.tm),
                     po.subpaths(objs.data, it["obj"]))
            finally:
                po._path_tokens = quick
            self.assertEqual(a[0], b[0])
            self.assertEqual((a[1][0], a[1][2]), (b[1][0], b[1][2]))
        self.assertIsNone(po._path_tokens(b"1 0 0 RG (text) Tj"))
        piece = b"\n0.3 w 1 0 0 RG 10 10 m 20 20 l 30 5 l S\n"
        entry, own = po._quick_entry(piece)
        full = po.scan(piece)[0]
        self.assertEqual((entry["start"], entry["end"], entry["box"]),
                         (full["start"], full["end"], full["box"]))
        self.assertEqual(own, b"0.3 w 1 0 0 RG")


class Prepared(unittest.TestCase):
    def test_cad_mode_reads_the_page_while_nothing_happens(self):
        old = DocumentView.cad_select, DocumentView.PREP_WAIT
        self.addCleanup(lambda: (setattr(DocumentView, "cad_select", old[0]),
                                 setattr(DocumentView, "PREP_WAIT", old[1])))
        DocumentView.cad_select = True
        DocumentView.PREP_WAIT = 10
        d, p = drawing()
        path = os.path.join(tempfile.mkdtemp(), "p.pdf")
        d.save(path)
        v = DocumentView(path)
        self.addCleanup(v.close_doc)
        v.resize(800, 800)
        v.show()
        v._cad_prepare_soon()
        end = time.monotonic() + 5
        while time.monotonic() < end:
            APP.processEvents()
            objs = v._obj_cache.get(0)
            if objs is not None and all("lines" in it for it in objs.items
                                        if it["kind"] == "shape"):
                break
        objs = v._obj_cache.get(0)
        self.assertIsNotNone(objs)
        self.assertTrue(all("lines" in it for it in objs.items if it["kind"] == "shape"))


if __name__ == "__main__":
    unittest.main()
