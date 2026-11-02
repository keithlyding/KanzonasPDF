"""From using 1.6.2 in CAD mode: a selected item looked just like a blue one (and like the
box's preview); a selection box often didn't start (the hand moved a little while clicking,
which made the click a lasso, and clicking again on the same spot came as a double-click,
which cancelled the box); switching to CAD mode left another ribbon tab in front.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_cad_feedback
"""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402
from PySide6.QtCore import Qt, QPoint  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import annotations, main_window, mouse_modes, page_widget  # noqa: E402

P = pymupdf.Point


def arrows():
    """A blank sheet with blue arrows on it (what the user was trying it on)."""
    d = pymupdf.open()
    p = d.new_page(width=792, height=612)
    for a, b in [(P(100, 100), P(400, 350)), (P(450, 80), P(700, 300))]:
        props = dict(annotations.DEFAULTS["arrow"], stroke="#0050ff")
        annotations.write(p, {"kind": "arrow", "props": props, "rect": pymupdf.Rect(),
                              "points": [a, b]})
    path = os.path.join(tempfile.mkdtemp(), "arrows.pdf")
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
        w.set_mouse_mode("standard")
        w.open_file(arrows())
        APP.processEvents()
        self.v = w.view()
        self.addCleanup(lambda: setattr(self.v, "dirty", False))

    def cad(self):
        self.w.set_mouse_mode("cad")
        APP.processEvents()
        self.page = self.v.pages[0]
        # (QTest moves the real pointer: a window an earlier test left open would get the
        # moves instead of this one)
        for old in APP.topLevelWidgets():
            if old.isVisible() and old is not self.w and not self.w.isAncestorOf(old):
                old.hide()
        self.w.raise_()
        self.w.activateWindow()

    def at(self, x, y):
        return QPoint(int(x * self.v.zoom), int(y * self.v.zoom))


class Tab(CadWindow):
    def test_cad_mode_brings_the_cad_tab_forward(self):
        ribbon = self.w.ribbon
        ribbon.setCurrentIndex(0)
        self.cad()
        self.assertIs(ribbon.currentWidget(), self.w._cad_tab)
        # (back to Standard: the CAD tab goes, another one is in front)
        self.w.set_mouse_mode("standard")
        self.assertIsNot(ribbon.currentWidget(), self.w._cad_tab)


class TextOnTheCadTab(CadWindow):
    """Edit text on the CAD tab (its face), with Add text under its arrow (asked for in
    1.7.1), and both work with the CAD mouse."""
    def split(self):
        from PySide6.QtWidgets import QToolButton
        t = self.w.tool_actions
        got = [b for b in self.w._cad_tab.findChildren(QToolButton) if b.menu() is not None
               and t["edittext"] in b.menu().actions()]
        self.assertEqual(len(got), 1)
        return got[0]

    def test_edit_text_is_the_face_and_add_text_is_under_the_arrow(self):
        self.cad()
        b = self.split()
        t = self.w.tool_actions
        self.assertIs(b.defaultAction(), t["edittext"])
        self.assertEqual(b.menu().actions(), [t["edittext"], t["addtext"]])

    def test_edit_text_opens_the_words_in_cad_mode(self):
        page = self.v.doc[0]
        page.insert_text((300, 500), "PUMP ROOM", fontsize=18)
        del page
        self.v._clear_page_caches([0])
        self.cad()
        self.split().defaultAction().trigger()
        self.assertEqual(self.w.tool, "edittext")
        QTest.mouseClick(self.page, Qt.LeftButton, Qt.NoModifier, self.at(330, 494))
        APP.processEvents()
        ed = self.v._inline
        self.assertIsNotNone(ed)
        self.assertIn("PUMP ROOM", ed.text.toPlainText())

    def test_add_text_types_on_the_page_in_cad_mode(self):
        self.cad()
        self.split().menu().actions()[1].trigger()
        self.assertEqual(self.w.tool, "addtext")
        QTest.mouseClick(self.page, Qt.LeftButton, Qt.NoModifier, self.at(200, 540))
        APP.processEvents()
        ed = self.v._inline
        self.assertIsNotNone(ed)
        self.assertEqual(getattr(ed, "kz_tool", None), "addtext")


class Clicks(CadWindow):
    def setUp(self):
        super().setUp()
        self.cad()

    def started(self):
        got = self.v._cad_pick is not None
        self.v._cad_pick = None
        return got

    def test_a_click_with_the_hand_moving_a_little_starts_the_box(self):
        w, a = self.page, self.at(300, 150)
        QTest.mousePress(w, Qt.LeftButton, Qt.NoModifier, a)
        for dx in (3, 7, 12, 18):
            QTest.mouseMove(w, a + QPoint(dx, dx // 3))
        QTest.mouseRelease(w, Qt.LeftButton, Qt.NoModifier, a + QPoint(18, 6))
        self.assertTrue(self.started())

    def test_holding_and_dragging_is_still_a_lasso(self):
        w, a = self.page, self.at(300, 150)
        QTest.mousePress(w, Qt.LeftButton, Qt.NoModifier, a)
        for k in range(1, 12):
            QTest.mouseMove(w, a + QPoint(8 * k, 5 * k), 40)    # (40 ms apart: a held drag)
        QTest.mouseRelease(w, Qt.LeftButton, Qt.NoModifier, a + QPoint(88, 55), 40)
        self.assertFalse(self.started())

    def test_clicking_the_first_corner_again_keeps_the_box(self):
        w, a = self.page, self.at(420, 60)
        QTest.mouseClick(w, Qt.LeftButton, Qt.NoModifier, a)
        QTest.mouseDClick(w, Qt.LeftButton, Qt.NoModifier, a)
        self.assertIsNotNone(self.v._cad_pick)
        # and the box still finishes with the next click elsewhere
        QTest.mouseMove(w, self.at(750, 400))
        QTest.mouseClick(w, Qt.LeftButton, Qt.NoModifier, self.at(750, 400))
        self.assertIsNone(self.v._cad_pick)
        self.assertEqual(len(self.v.selected_xrefs()), 1)       # (the arrow inside it)

    def test_the_box_says_it_took(self):
        said = []
        self.v.statusMessage.connect(said.append)
        QTest.mouseClick(self.page, Qt.LeftButton, Qt.NoModifier, self.at(300, 150))
        self.assertTrue(any("corner" in s for s in said))


class DrawFromAMarkup(CadWindow):
    def test_in_cad_mode_a_line_starts_on_a_markups_end(self):
        # (AutoCAD draws from an object's endpoint; selecting is Edit objects' job. Before,
        # the first click on the arrow selected it instead of starting the line)
        self.cad()
        self.w.set_tool("line")
        w = self.page
        n = len(list(self.v.doc[0].annots()))
        end = self.at(400, 350)                 # (the first arrow's tip)
        QTest.mouseClick(w, Qt.LeftButton, Qt.NoModifier, end)
        QTest.mouseMove(w, self.at(500, 500))
        QTest.mouseClick(w, Qt.LeftButton, Qt.NoModifier, self.at(500, 500))
        APP.processEvents()
        self.assertEqual(len(list(self.v.doc[0].annots())), n + 1)
        self.assertIsNone(self.v.selection)

    def test_in_standard_mode_the_first_click_still_selects(self):
        self.w.set_tool("line")
        QTest.mouseClick(self.v.pages[0], Qt.LeftButton, Qt.NoModifier, self.at(250, 225))
        APP.processEvents()
        self.assertIsNotNone(self.v.selection)


class Selected(CadWindow):
    def setUp(self):
        super().setUp()
        self.cad()

    def record(self):
        """Patch the selection painters to note what they're given (not the painter: a
        painter kept past its paint is an error)."""
        got = {"grips": None, "dashed": 0}
        grips, dashed = page_widget.paint_grips, page_widget.paint_selected_path

        def g(p, points):
            got["grips"] = list(points)
            grips(p, points)

        def d(p, path):
            got["dashed"] += 1
            dashed(p, path)
        self.enterContext(mock.patch.object(page_widget, "paint_grips", g))
        self.enterContext(mock.patch.object(page_widget, "paint_selected_path", d))
        return got

    def test_selected_markups_get_grips_and_a_dashed_line(self):
        page = self.v.doc[0]
        xs = [a.xref for a in annotations.each_annot(page)]
        del page
        self.v._set_selection(0, xs[:1])
        got = self.record()
        self.page.repaint()
        self.assertTrue(got["dashed"])
        pts = got["grips"]
        self.assertGreaterEqual(len(pts), 2)                    # (the arrow's two ends)
        ends = {(round(q.x()), round(q.y())) for q in pts}
        self.assertIn((round(100 * self.v.zoom), round(100 * self.v.zoom)), ends)

    def test_selected_drawing_objects_get_grips(self):
        d = pymupdf.open()
        p = d.new_page(width=400, height=300)
        p.draw_line((50, 150), (350, 150), color=(0, 0, 1))
        path = os.path.join(tempfile.mkdtemp(), "line.pdf")
        d.save(path)
        self.w.open_file(path)
        APP.processEvents()
        v = self.w.view()
        self.addCleanup(lambda: setattr(v, "dirty", False))
        v.select_objects(0, list(v.content_objects(0).items))
        got = self.record()
        v.pages[0].repaint()
        self.assertGreaterEqual(len(got["grips"]), 2)

    def test_a_selection_shows_on_a_blue_line(self):
        # white under the blue dashes: pixels along a selected blue arrow aren't all blue
        page = self.v.doc[0]
        xs = [a.xref for a in annotations.each_annot(page)]
        del page
        w = self.page
        before = w.grab().toImage()
        self.v._set_selection(0, xs[:1])
        w.repaint()
        after = w.grab().toImage()
        z = self.v.zoom
        changed = 0
        for k in range(20, 80):
            x = int((100 + 3 * k) * z)
            y = int((100 + 2.5 * k) * z)
            if before.pixelColor(x, y) != after.pixelColor(x, y):
                changed += 1
        self.assertGreater(changed, 20)

    def test_grips_are_limited_on_a_huge_selection(self):
        lines = [[(i, 0.0), (i, 10.0)] for i in range(5000)]
        self.assertEqual(len(page_widget.grip_points(lines)), page_widget.GRIPS_MAX)


if __name__ == "__main__":
    unittest.main()
