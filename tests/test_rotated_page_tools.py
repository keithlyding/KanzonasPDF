"""Tools on a page with /Rotate 90 (a sheet stored portrait, shown landscape) behave as on the
page as shown: a callout, a clicked text box and a signature placeholder get their usual
shape, and Next form field (Tab) goes in reading order.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_rotated_page_tools
"""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf as F  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import annotations, dialogs  # noqa: E402
from kanzonas.document_view import DocumentView  # noqa: E402

P, R = F.Point, F.Rect


class RotatedPageTools(unittest.TestCase):
    def view(self, rot, fields=()):
        d = F.open()
        p = d.new_page(width=612, height=792)
        p.set_rotation(rot)
        for name, x, y in fields:                   # (name, top-left as shown)
            w = F.Widget()
            w.field_type = F.PDF_WIDGET_TYPE_TEXT
            w.field_name = name
            w.rect = R(x, y, x + 200, y + 20) * p.derotation_matrix
            p.add_widget(w)
        path = os.path.join(tempfile.mkdtemp(), "r.pdf")
        d.save(path)
        v = DocumentView(path)
        self.addCleanup(v.close_doc)
        return v

    def shown(self, v, xref):
        page = v.doc[0]
        return annotations.bounds(annotations.read(page.load_annot(xref))) * page.rotation_matrix

    def newest(self, v):
        return max(a.xref for a in v.doc[0].annots())

    def test_default_boxes_upright(self):
        for rot in (0, 90, 270):
            with self.subTest(rotation=rot):
                v = self.view(rot)
                dm = v.doc[0].derotation_matrix
                with mock.patch.object(dialogs, "get_text", return_value=("Revise per RFI 12", True)):
                    v.apply_drag_tool(0, "textbox", P(100, 500) * dm, P(100, 500) * dm, True)
                box = self.shown(v, self.newest(v))
                self.assertAlmostEqual(box.width, 200, delta=2)
                self.assertAlmostEqual(box.height, 40, delta=2)
                self.assertTrue(abs(box.tl - P(100, 500)) < 2)
                props = dict(annotations.tool_props("placeholder"), **{"for": "signature"})
                with mock.patch.object(v, "tool_props", return_value=props):
                    v.apply_drag_tool(0, "placeholder", P(300, 300) * dm, P(300, 300) * dm, True)
                box = self.shown(v, self.newest(v))
                self.assertAlmostEqual(box.width, 160, delta=2)
                self.assertAlmostEqual(box.height, 40, delta=2)

    def test_callout_box_upright_and_on_the_dragged_side(self):
        for rot in (0, 90, 270):
            for end, left in ((P(300, 200), False), (P(100, 200), True)):
                with self.subTest(rotation=rot, left=left):
                    v = self.view(rot)
                    dm = v.doc[0].derotation_matrix
                    with mock.patch.object(dialogs, "get_text",
                                           return_value=("See spec section 09 91 00", True)):
                        v.apply_drag_tool(0, "callout", P(200, 300) * dm, end * dm, False)
                    page = v.doc[0]
                    model = annotations.read(page.load_annot(self.newest(v)))
                    box = R(model["rect"]) * page.rotation_matrix
                    del page
                    self.assertAlmostEqual(box.width, 160, delta=2)
                    self.assertAlmostEqual(box.height, 40, delta=2)
                    self.assertAlmostEqual(box.y0, 200, delta=2)
                    self.assertAlmostEqual(box.x1 if left else box.x0, end.x, delta=2)

    def test_tab_goes_in_reading_order_as_shown(self):
        names = [("1 top left", 100, 100), ("2 top right", 450, 100),
                 ("3 bottom left", 100, 250), ("4 bottom right", 450, 250)]
        for rot in (0, 90, 270):
            with self.subTest(rotation=rot):
                v = self.view(rot, names)
                by_xref = {w.xref: w.field_name for w in v.doc[0].widgets()}
                self.assertEqual([by_xref[x] for _i, x in v.field_order()], [n[0] for n in names])


if __name__ == "__main__":
    unittest.main()
