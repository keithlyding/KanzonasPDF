"""Whatever another PDF editor can change, KanzonasPDF can change too: flattened markups
become drawing groups (Form XObjects) that Edit objects selects, moves and deletes.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_flattened_objects
"""
import os
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


class FlattenedObjects(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        patch = mock.patch.object(QMessageBox, "warning", return_value=None)
        patch.start()
        self.addCleanup(patch.stop)

    def flattened(self):
        d = F.open()
        pg = d.new_page()
        pg.add_rect_annot(F.Rect(100, 100, 200, 150))
        pg.add_freetext_annot(F.Rect(100, 200, 300, 240), "STAMP TEXT")
        p = os.path.join(self.tmp, "in.pdf")
        d.save(p)
        v = DocumentView(p)
        v.flatten()
        out = os.path.join(self.tmp, "flat.pdf")
        v.save(out)
        v.close_doc()
        return out

    def test_flattened_markups_can_be_selected_moved_and_deleted(self):
        v = DocumentView(self.flattened())
        objs = v.content_objects(0)
        groups = [it for it in objs.items if it["kind"] == "group"]
        self.assertEqual(len(groups), 2)
        it = v.object_at(0, F.Point(150, 125))
        self.assertIsNotNone(it)
        v.select_objects(0, [it])
        v.move_objects(it["rect"] + (50, 50, 50, 50))
        moved = [g for g in v.content_objects(0).items if g["n"] == it["n"]][0]
        self.assertAlmostEqual(moved["rect"].x0, it["rect"].x0 + 50, places=1)
        text = v.object_at(0, F.Point(200, 220))
        v.select_objects(0, [text])
        v.delete_objects()
        self.assertNotIn("STAMP TEXT", v.doc[0].get_text())
        v.close_doc()

    def test_a_group_filling_the_page_needs_a_selection_box(self):
        d = F.open()
        pg = d.new_page()
        src = F.open()
        sp = src.new_page()
        sh = sp.new_shape()
        sh.draw_rect(sp.rect + (20, 20, -20, -20))
        sh.draw_line((50, 50), (500, 700))
        sh.finish(color=(0, 0, 0))
        sh.commit()
        pg.show_pdf_page(pg.rect, src, 0)        # the whole drawing as one group
        objs = P.Objects(pg)
        self.assertEqual([it["kind"] for it in objs.items], ["group"])
        self.assertIsNone(objs.at(F.Point(300, 300), 2))
        self.assertEqual(len(objs.inside(pg.rect + (-1, -1, 1, 1))), 1)


if __name__ == "__main__":
    unittest.main()
