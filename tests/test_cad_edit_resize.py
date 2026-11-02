"""CAD mode (from using 1.7.1): a double-click on text edits it (the page's own text opens in
Edit text, a markup's text in its editor), and a selection can be resized there: one markup
by its own handles, several items (markups, or markups and the drawing's objects) by one box
around them all, one undo step.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_cad_edit_resize
"""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402
from PySide6.QtCore import Qt, QEvent, QPoint, QPointF  # noqa: E402
from PySide6.QtGui import QMouseEvent  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import annotations as A, cad_select, main_window, mouse_modes  # noqa: E402
from kanzonas.page_widget import box_handles  # noqa: E402

P = pymupdf.Point


def sheet():
    d = pymupdf.open()
    p = d.new_page(width=792, height=612)
    p.insert_text((100, 100), "GENERAL NOTES", fontsize=16)
    p.draw_line((100, 400), (300, 400), color=(0, 0, 1), width=2)
    A.write(p, {"kind": "rect", "props": dict(A.DEFAULTS["rect"]),
                "rect": pymupdf.Rect(400, 100, 500, 160)})
    A.write(p, {"kind": "rect", "props": dict(A.DEFAULTS["rect"]),
                "rect": pymupdf.Rect(400, 250, 460, 300)})
    path = os.path.join(tempfile.mkdtemp(), "sheet.pdf")
    d.save(path)
    return path


class CadWindow(unittest.TestCase):
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
        w.open_file(sheet())
        APP.processEvents()
        v = self.v = w.view()
        self.addCleanup(lambda: setattr(v, "dirty", False))
        w.set_mouse_mode("cad")
        w.set_tool("editobjects")
        v.set_zoom(1.0)
        APP.processEvents()
        self.page = v.pages[0]
        v.ensureVisible(self.page.x() + 300, self.page.y() + 250, 500, 400)
        APP.processEvents()

    def at(self, x, y):
        return QPoint(int(x * self.v.zoom), int(y * self.v.zoom))

    def rects(self):
        page = self.v.doc[0]
        return sorted((A.read(a)["rect"] for a in A.each_annot(page)), key=lambda r: r.y0)

    def xrefs(self):
        page = self.v.doc[0]
        return [a.xref for a in A.each_annot(page)]

    def drag(self, a, b, mods=Qt.NoModifier):
        """Press at a, move to b, release; mods held while moving (Shift at the press itself
        takes an item out of a CAD selection)."""
        w = self.page
        a, b = QPointF(a), QPointF(b)
        QTest.mousePress(w, Qt.LeftButton, Qt.NoModifier, a.toPoint())
        for k in range(1, 6):
            w.mouseMoveEvent(QMouseEvent(QEvent.MouseMove, a + (b - a) * k / 5,
                                         w.mapToGlobal(a + (b - a) * k / 5), Qt.NoButton,
                                         Qt.LeftButton, mods))
        QTest.mouseRelease(w, Qt.LeftButton, mods, b.toPoint())
        APP.processEvents()


class DoubleClick(CadWindow):
    def test_on_the_pages_text_opens_edit_text(self):
        QTest.mouseDClick(self.page, Qt.LeftButton, Qt.NoModifier, self.at(150, 95))
        APP.processEvents()
        ed = self.v._inline
        self.assertIsNotNone(ed)
        self.assertIn("GENERAL NOTES", ed.text.toPlainText())
        self.assertIsNone(self.v._cad_pick)                 # (no box left started)

    def test_with_select_too(self):
        self.w.set_tool("select")
        QTest.mouseDClick(self.page, Qt.LeftButton, Qt.NoModifier, self.at(150, 95))
        APP.processEvents()
        self.assertIsNotNone(self.v._inline)

    def test_on_a_markup_edits_its_text(self):
        with mock.patch.object(type(self.v), "edit_annot_text") as edit:
            QTest.mouseDClick(self.page, Qt.LeftButton, Qt.NoModifier, self.at(450, 100))
        self.assertTrue(edit.called)

    def test_on_empty_paper_it_is_still_a_click(self):
        QTest.mouseClick(self.page, Qt.LeftButton, Qt.NoModifier, self.at(650, 500))
        QTest.mouseDClick(self.page, Qt.LeftButton, Qt.NoModifier, self.at(650, 500))
        self.assertIsNotNone(self.v._cad_pick)              # (the box stays started)
        self.assertIsNone(self.v._inline)


class Resize(CadWindow):
    def test_one_markup_by_its_own_handles(self):
        x = [k for k, r in zip(self.xrefs(), self.rects()) if r.y0 == 100] or self.xrefs()[:1]
        self.v._set_selection(0, x)
        self.page.repaint()
        model = self.page._selected_here()
        corner = self.page._handles(model)["br"].center()
        self.drag(corner, corner + QPointF(50, 40))
        r = self.rects()[0]
        self.assertGreater(r.width, 120)
        self.assertGreater(r.height, 80)

    def test_several_markups_by_one_box(self):
        self.v._set_selection(0, self.xrefs())
        APP.processEvents()
        box = cad_select.resize_box(self.page)
        self.assertIsNotNone(box)
        right = box_handles(box)["r"].center()
        before = self.rects()
        self.drag(right, right + QPointF(100, 0))
        after = self.rects()
        for b, a in zip(before, after):
            self.assertAlmostEqual(a.x0, b.x0 + (b.x0 - 400) * 1.0, delta=0.6)
            self.assertGreater(a.width, b.width * 1.9)
            self.assertAlmostEqual(a.height, b.height, delta=0.6)
        self.v.undo()                                       # (one step)
        self.assertEqual([tuple(round(c, 1) for c in r) for r in self.rects()],
                         [tuple(round(c, 1) for c in r) for r in before])

    def test_markups_and_the_drawings_line_together(self):
        self.v._set_selection(0, self.xrefs()[:1])
        line = [it for it in self.v.content_objects(0).items if it["kind"] == "shape"]
        self.v.select_objects(0, line)
        APP.processEvents()
        box = cad_select.resize_box(self.page)
        self.assertIsNotNone(box)
        corner = box_handles(box)["bl"].center()
        self.drag(corner, corner + QPointF(-50, 0), Qt.ShiftModifier)     # (Shift: free)
        self.v._obj_cache.pop(0, None)
        shapes = [it for it in self.v.content_objects(0).items if it["kind"] == "shape"]
        self.assertLess(shapes[0]["rect"].x0, 95)           # (the line got longer, leftward)

    def test_on_a_turned_page_it_resizes_as_seen(self):
        self.v.doc[0].set_rotation(90)
        self.v._clear_caches()
        self.v._relayout()
        APP.processEvents()
        self.v._set_selection(0, self.xrefs())
        APP.processEvents()
        page = self.v.doc[0]
        seen = [self.v._display_bounds(page, A.read(a)) for a in A.each_annot(page)]
        del page
        box = cad_select.resize_box(self.page)
        right = box_handles(box)["r"].center()
        self.drag(right, right + QPointF(80, 0))
        page = self.v.doc[0]
        now = [self.v._display_bounds(page, A.read(a)) for a in A.each_annot(page)]
        for b, a in zip(seen, now):
            self.assertGreater(a.width, b.width * 1.2)          # (wider on the screen)
            self.assertAlmostEqual(a.height, b.height, delta=0.6)

    def test_a_handle_shows_a_resize_arrow(self):
        self.v._set_selection(0, self.xrefs())
        APP.processEvents()
        box = cad_select.resize_box(self.page)
        spot = box_handles(box)["r"].center()
        w = self.page
        w.mouseMoveEvent(QMouseEvent(QEvent.MouseMove, spot, w.mapToGlobal(spot),
                                     Qt.NoButton, Qt.NoButton, Qt.NoModifier))
        self.assertEqual(self.page.cursor().shape(), Qt.SizeHorCursor)


if __name__ == "__main__":
    unittest.main()
