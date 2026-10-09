"""Moving the page's own objects (Edit objects) on CAD drawings: after a move the object
list is worked out from the earlier read instead of reading the whole drawing again,
and it must match a full read exactly.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_object_move_speed
"""
import os
import random
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf as F  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import page_objects as P  # noqa: E402
from kanzonas.document_view import DocumentView  # noqa: E402


def cad_page(doc):
    """A CAD-export-like page: the color and line width sit inside each shape's commands
    (between the path and the paint operator), as AutoCAD-style exporters write them."""
    pg = doc.new_page(width=1200, height=800)
    ops = []
    for i in range(300):
        x, y = (i * 37) % 1100 + 20, (i * 53) % 700 + 20
        ops.append(b"%d %d m %d %d l %.2f w %.2f 0 0 RG S" % (x, y, x + 40, y + 25,
                                                              0.2 + i % 5 / 10, i % 7 / 7))
    ops.append(b"q 200 0 0 100 300 300 cm 0 0 1 rg 0 0 1 1 re f Q")
    x = doc.get_new_xref()
    doc.update_object(x, "<<>>")
    doc.update_stream(x, b"\n".join(ops))
    pg.set_contents(x)
    return pg


def same(a, b):
    assert len(a.found) == len(b.found)
    for x, y in zip(a.found, b.found):
        for k in set(x) | set(y):
            if k == "ctm":
                assert max(abs(p - q) for p, q in zip(x[k], y[k])) < 1e-3, k
            else:
                assert x.get(k) == y.get(k), k
    assert [it["n"] for it in a.items] == [it["n"] for it in b.items]


class ObjectMoveSpeed(unittest.TestCase):
    def test_updated_objects_match_a_full_read(self):
        d = F.open()
        pg = cad_page(d)
        objs = P.Objects(pg)
        rnd = random.Random(3)
        for _ in range(40):
            pick = rnd.sample(objs.items, rnd.choice([1, 1, 3]))
            ns = [it["n"] for it in pick]
            r = F.Rect()
            for it in pick:
                r |= it["rect"]
            if rnd.random() < 0.25:
                new = P.rotate(pg, ns, r, 90, objs)
            else:
                dx, dy = rnd.uniform(-40, 40), rnd.uniform(-40, 40)
                new = P.move_to(pg, ns, r, r + (dx, dy, dx, dy), objs)
            self.assertIsNotNone(new)
            same(new, P.Objects(pg))
            objs = new

    def test_moving_does_not_read_the_drawing_again(self):
        d = F.open()
        cad_page(d)
        p = os.path.join(tempfile.mkdtemp(), "cad.pdf")
        d.save(p)
        v = DocumentView(p)
        objs = v.content_objects(0)
        it = objs.items[10]
        v.select_objects(0, [it])
        with mock.patch.object(P, "scan", side_effect=AssertionError("read again")), \
                mock.patch.object(QMessageBox, "warning", return_value=None):
            v.move_objects(it["rect"] + (15, 10, 15, 10))
            moved = v.content_objects(0)
        self.assertTrue(v.can_undo())
        self.assertEqual(v.selected_objects()[0]["n"], it["n"])
        self.assertAlmostEqual(moved.items[10]["rect"].x0, it["rect"].x0 + 15, places=2)
        v.close_doc()


if __name__ == "__main__":
    unittest.main()
