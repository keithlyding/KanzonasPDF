"""A dragged picture or markup snaps by its edges and center to the page's edges and center.

Before 1.8.1 a picture in the page (Image tool, moved with Edit objects) didn't snap at all, and
a dragged markup snapped only its top-left corner: dropped near the middle of the sheet, its
center never settled there.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_snap_box
"""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf as F
from PySide6.QtCore import QPointF, QRectF
from PySide6.QtWidgets import QApplication, QMessageBox

from kanzonas import annotations as A
from kanzonas.document_view import DocumentView

APP = QApplication.instance() or QApplication([])


class SnapBox(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(patch.stopall)
        for name in ("information", "warning", "critical"):
            patch.object(QMessageBox, name, return_value=None).start()
        saved = (DocumentView.snap_page, DocumentView.snap_objects, DocumentView.snap_grid)
        self.addCleanup(lambda: setattr(DocumentView, "snap_page", saved[0]) or
                        setattr(DocumentView, "snap_objects", saved[1]) or
                        setattr(DocumentView, "snap_grid", saved[2]))
        DocumentView.snap_page, DocumentView.snap_objects, DocumentView.snap_grid = True, False, False

    def _open(self, rotate=0, markup=False):
        path = Path(self.tmp.name) / "pic.pdf"
        doc = F.open()
        page = doc.new_page(width=600, height=400)
        if markup:
            page.add_rect_annot(F.Rect(100, 80, 200, 140))
        else:
            pix = F.Pixmap(F.csRGB, F.IRect(0, 0, 20, 12), False)
            pix.set_rect(pix.irect, (200, 40, 40))
            page.insert_image(F.Rect(100, 80, 200, 140), pixmap=pix)
        page.set_rotation(rotate)
        doc.save(path)
        doc.close()
        v = DocumentView(str(path))
        self.addCleanup(v.close_doc)
        v.resize(900, 700)
        v.show()
        v.set_zoom(1.0)
        APP.processEvents()
        return v, v.pages[0]

    def _page_center(self, pw):
        page = pw.view.doc[0]
        return pw.to_screen(page.rect * page.derotation_matrix).center()

    def _drag_picture(self, pw, d, snap=True):
        """The picture's box on screen after a drag of d (widget px), as the drag shows it."""
        v = pw.view
        pic = [it for it in v.content_objects(0).items if it["kind"] == "picture"][0]
        v.select_objects(0, [pic])
        start = pw.to_screen(v.selected_objects_rect()).center()
        pw._obj_edit = {"mode": "move", "start": start, "preview": None}
        return pw._objects_preview(start + d, False, snap)

    def test_picture_settles_in_the_middle(self):
        v, pw = self._open()
        box = QRectF(pw.to_screen(v.content_objects(0).items[0]["rect"]))
        c = self._page_center(pw)
        # dropped 4 px right of and 3 px above the middle: it settles in the middle
        d = (c - box.center()) + QPointF(4, -3)
        got = self._drag_picture(pw, d)
        self.assertAlmostEqual(got.center().x(), c.x(), places=3)
        self.assertAlmostEqual(got.center().y(), c.y(), places=3)
        self.assertEqual(sorted(a for a, _ in pw._snap_guides), ["x", "y"])
        # let go: the picture in the page is in the middle
        pw._obj_edit["preview"] = got
        pw._objects_release(None, QPointF())
        r = [it for it in v.content_objects(0).items if it["kind"] == "picture"][0]["rect"]
        self.assertAlmostEqual((r.x0 + r.x1) / 2, 300, delta=0.05)
        self.assertAlmostEqual((r.y0 + r.y1) / 2, 200, delta=0.05)
        self.assertEqual(pw._snap_guides, [])

    def test_one_way_only_and_edges(self):
        v, pw = self._open()
        box = QRectF(pw.to_screen(v.content_objects(0).items[0]["rect"]))
        c = self._page_center(pw)
        # near the middle across, far from it up and down: only across snaps
        d = QPointF(c.x() - box.center().x() + 5, 40)
        got = self._drag_picture(pw, d)
        self.assertAlmostEqual(got.center().x(), c.x(), places=3)
        self.assertAlmostEqual(got.top(), box.top() + 40, places=3)
        self.assertEqual([a for a, _ in pw._snap_guides], ["x"])
        # its left edge near the page's left edge: it goes to the edge
        got = self._drag_picture(pw, QPointF(-box.left() + 4, 0))
        self.assertAlmostEqual(got.left(), 0, places=3)

    def test_far_away_or_snapping_off_stays(self):
        v, pw = self._open()
        box = QRectF(pw.to_screen(v.content_objects(0).items[0]["rect"]))
        got = self._drag_picture(pw, QPointF(60, 50))
        self.assertAlmostEqual(got.left(), box.left() + 60, places=3)
        self.assertEqual(pw._snap_guides, [])
        c = self._page_center(pw)
        got = self._drag_picture(pw, (c - box.center()) + QPointF(4, -3), snap=False)
        self.assertAlmostEqual(got.center().x(), c.x() + 4, places=3)

    def test_rotated_page(self):
        v, pw = self._open(rotate=90)
        box = QRectF(pw.to_screen(v.content_objects(0).items[0]["rect"]))
        c = self._page_center(pw)
        got = self._drag_picture(pw, (c - box.center()) + QPointF(-5, 4))
        self.assertAlmostEqual(got.center().x(), c.x(), places=3)
        self.assertAlmostEqual(got.center().y(), c.y(), places=3)

    def test_markup_center_snaps_not_only_its_corner(self):
        v, pw = self._open(markup=True)
        annot = v.doc[0].first_annot
        v.select_xref(0, annot.xref)
        model = v.selected_model
        box = pw.to_screen(A.bounds(model))
        c = self._page_center(pw)
        start = box.center()
        pw._edit = {"mode": "move", "start": start, "model": model, "preview": None}
        moved = pw._edit_preview(start + (c - box.center()) + QPointF(3, 4), snap=True)
        r = pw.to_screen(A.bounds(moved))
        self.assertAlmostEqual(r.center().x(), c.x(), delta=0.01)
        self.assertAlmostEqual(r.center().y(), c.y(), delta=0.01)


if __name__ == "__main__":
    unittest.main()
