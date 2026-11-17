"""The page's own objects in Properties, and snapping to pictures.

Properties (Edit objects, and CAD mode): one picture or group selected shows its Rotation
(counterclockwise as the page is shown), and typing an angle turns it to that angle; lines and
shapes (or several objects) keep no angle, so Rotate by turns them by what's typed and goes back
to 0. Text is moved, not turned. Snapping: a picture's corners, edge middles and center, also
when it's turned, as a CAD command's points snap to them.

The owner, 16 Nov 2026: "I would like rotate to show up in the properties panel. Also, snap to
isn't working when in cad mode to click on a point on the image I'm trying to rotate".

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_rotation_props_snap
"""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import main_window, mouse_modes, page_objects, snapping  # noqa: E402
from kanzonas.document_view import DocumentView  # noqa: E402

P = pymupdf.Point
PIC = pymupdf.Rect(100, 100, 300, 200)


def sheet(rotation=0, text=False):
    pm = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 40, 20), 0)
    pm.set_rect(pm.irect, (200, 30, 30))
    d = pymupdf.open()
    p = d.new_page()
    p.set_rotation(rotation)
    # (upright as the page is shown, as the Image tool places it)
    p.insert_image(PIC * p.derotation_matrix, pixmap=pm, rotate=p.rotation)
    p.draw_line(P(100, 400) * p.derotation_matrix, P(300, 400) * p.derotation_matrix)
    if text:
        p.insert_text((100, 600), "NOTE", fontsize=14)
    path = os.path.join(tempfile.mkdtemp(), "sheet.pdf")
    d.save(path)
    return path


class Window(unittest.TestCase):
    rotation = 0
    text = False

    def setUp(self):
        w = self.w = main_window.MainWindow()
        old = {k: w.settings.value(k) for k in ("mouse_mode", "mouse_before_cad")}

        def back():
            for k, val in old.items():
                w.settings.setValue(k, val) if val is not None else w.settings.remove(k)
            mouse_modes.apply(w.settings)
        self.addCleanup(back)
        self.addCleanup(lambda: [setattr(x, "_close_confirmed", True) or x.close()
                                 for x in main_window.windows()])
        w.resize(1200, 900)
        w.show()
        w.open_file(sheet(self.rotation, self.text))
        APP.processEvents()
        v = self.v = w.view()
        self.addCleanup(lambda: setattr(v, "dirty", False))
        w.set_tool("editobjects")
        APP.processEvents()
        self.props = w.props

    def items(self, kind):
        return [it for it in self.v.content_objects(0).items if it["kind"] == kind]

    def select(self, items):
        self.v.select_objects(0, items)
        APP.processEvents()

    def shown(self, key):
        lab, w = self.props.rows[key]
        return w.isVisible()


class PictureRotation(Window):
    def test_one_picture_shows_its_rotation(self):
        self.select(self.items("picture"))
        self.assertTrue(self.shown("rotation"))
        self.assertFalse(self.shown("turn"))
        self.assertEqual(self.props.rotation.value(), 0)
        self.assertIn("1 picture", self.props.title.text())

    def test_an_angle_typed_turns_it_to_that_angle(self):
        before = pymupdf.Rect(self.v.doc[0].get_image_info()[0]["bbox"])
        self.select(self.items("picture"))
        self.props.rotation.setValue(30)
        APP.processEvents()
        self.assertAlmostEqual(self.v.objects_angle(), 30, 1)
        self.assertAlmostEqual(self.props.rotation.value(), 30, 1)
        self.props.rotation.setValue(-90)
        APP.processEvents()
        self.assertAlmostEqual(self.v.objects_angle(), -90, 1)
        self.v.undo()
        self.v.undo()
        APP.processEvents()
        box = pymupdf.Rect(self.v.doc[0].get_image_info()[0]["bbox"])
        self.assertAlmostEqual(abs(box.tl - before.tl) + abs(box.br - before.br), 0, 1)

    def test_counterclockwise_as_shown(self):
        self.select(self.items("picture"))
        self.props.rotation.setValue(30)
        APP.processEvents()
        m = pymupdf.Matrix(self.v.doc[0].get_image_info()[0]["transform"])
        top_right = P(1, 0) * m * self.v.doc[0].rotation_matrix
        top_left = P(0, 0) * m * self.v.doc[0].rotation_matrix
        self.assertLess(top_right.y, top_left.y)               # (its top edge goes up)


class OnATurnedPage(PictureRotation):
    """As the page is shown: an upright picture on a page turned a quarter is at 0."""
    rotation = 90

    def test_counterclockwise_as_shown(self):
        super().test_counterclockwise_as_shown()


class ShapesRotateBy(Window):
    def test_lines_and_shapes_turn_by_what_is_typed(self):
        self.select(self.items("shape"))
        self.assertTrue(self.shown("turn"))
        self.assertFalse(self.shown("rotation"))
        self.props.turn.setValue(90)
        APP.processEvents()
        box = self.v.doc[0].get_drawings()[0]["rect"]
        self.assertAlmostEqual(box.width, 0, 0)                # (upright now)
        self.assertAlmostEqual(box.height, 200, 0)
        self.assertEqual(self.props.turn.value(), 0)           # (ready for the next turn)

    def test_several_objects_turn_by_too(self):
        self.select(self.items("shape") + self.items("picture"))
        self.assertTrue(self.shown("turn"))
        self.assertIsNone(self.v.objects_angle())


class WithText(Window):
    text = True

    def test_text_is_moved_not_turned(self):
        self.select(self.items("picture") + list(self.v.text_objects(0)))
        self.assertFalse(self.shown("turn"))
        self.assertFalse(self.shown("rotation"))
        self.assertIn("not turned", self.props.hint.text())


class Markups(Window):
    def test_nothing_selected_no_rotation(self):
        self.select(self.items("picture"))
        self.v.clear_object_selection()
        APP.processEvents()
        self.assertFalse(self.shown("turn"))
        self.assertFalse(self.shown("rotation"))


class PictureSnapPoints(unittest.TestCase):
    def page(self, turn=0):
        d = pymupdf.open(sheet())
        p = d[0]
        if turn:
            objs = page_objects.Objects(p)
            n = [it["n"] for it in objs.items if it["kind"] == "picture"]
            page_objects.rotate(p, n, PIC, turn, objs)
        return d, p

    def test_corners_edge_middles_and_center(self):
        d, p = self.page()
        idx = snapping.content_index(p)
        for q in (P(100, 100), P(300, 200), P(200, 100), P(300, 150), P(200, 150)):
            hit = idx.nearest(q + (2, 2), 5)
            self.assertIsNotNone(hit, q)
            self.assertAlmostEqual(abs(hit - q), 0, 3)

    def test_a_turned_pictures_corners_where_they_are(self):
        d, p = self.page(turn=90)
        m = pymupdf.Matrix(p.get_image_info()[0]["transform"])
        idx = snapping.content_index(p)
        for corner in (P(0, 0), P(1, 0), P(1, 1), P(0, 1)):
            q = corner * m
            hit = idx.nearest(q + (2, 1), 5)
            self.assertIsNotNone(hit, q)
            self.assertAlmostEqual(abs(hit - q), 0, 3)

    def test_a_page_without_pictures_isnt_read_for_them(self):
        d = pymupdf.open()
        p = d.new_page()
        p.draw_line((0, 0), (100, 100))
        with mock.patch.object(pymupdf.Page, "get_image_info") as info:
            snapping.content_index(p)
        self.assertFalse(info.called)


class CommandSnapsToAPicture(Window):
    def test_a_rotate_commands_base_point_snaps_to_the_pictures_corner(self):
        for k in ("snap_objects", "snap_page", "snap_grid"):
            self.addCleanup(setattr, DocumentView, k, getattr(DocumentView, k))
        DocumentView.snap_objects = True
        DocumentView.snap_page = False
        DocumentView.snap_grid = False
        v = self.v
        v._snap_content.clear()
        hit = v.snap_point(0, P(102, 103))
        self.assertIsNotNone(hit)
        self.assertAlmostEqual(abs(pymupdf.Point(hit[0]) - P(100, 100)), 0, 3)


if __name__ == "__main__":
    unittest.main()
