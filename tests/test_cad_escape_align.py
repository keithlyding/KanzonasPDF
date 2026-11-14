"""CAD mode: Escape unselects, and Align to first selected goes by the order things were
selected (the owner, 14 Nov 2026: "in cad mouse mode, escape is not always unselecting
objects. Also, aligning with first selected object isn't working either").

Escape left the selection when the keyboard was in the CAD command line (after a letter typed
over the drawing, or a click in the line), and when a click on empty space had started a
selection box. Align took the drawing's objects in drawing order, and the markups before
them, so "first selected" was whichever came first in the file.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_cad_escape_align
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from tests.test_interaction_112 import A, P, R, Window, pump  # noqa: E402

LINE = P(250, 100)          # on the line (100, 100)-(400, 100), drawn first
RED = P(400, 500)           # on the red rectangle (350, 500, 450, 560), drawn last


class CadWindow(Window):
    def setUp(self):
        def build(pg):
            pg.draw_rect(R(350, 500, 450, 560), color=(1, 0, 0), width=2)
        w, v = self.open(build)
        was = v.mouse_mode
        w.set_mouse_mode("cad")
        # (the mouse mode is kept in the settings and the views' class attributes: put back
        # for the tests that come after)
        self.addCleanup(lambda: (w.set_mouse_mode(was), pump()))
        w.set_tool("editobjects")
        pump()
        self.assertTrue(v.cad_select)

    def selected(self):
        v = self.v
        return (len(v.obj_sel[1]) if v.obj_sel else 0) + len(v.selected_xrefs())

    def lefts(self):
        """The drawing's objects' left edges, by where they are on the page (read again)."""
        v = self.v
        v._obj_cache.pop(0, None)
        return sorted((round(it["rect"].y0), round(it["rect"].x0))
                      for it in v.content_objects(0).items)

    def escape(self):
        QTest.keyClick(QApplication.focusWidget() or self.v.viewport(), Qt.Key_Escape)
        pump()


class Escape(CadWindow):
    def test_on_the_page(self):
        self.click(self.v.pages[0], self.at(RED))
        self.click(self.v.pages[0], self.at(LINE))
        self.assertEqual(self.selected(), 2)
        self.escape()
        self.assertEqual(self.selected(), 0)

    def test_after_a_letter_typed_over_the_drawing(self):
        w, v = self.w, self.v
        self.click(v.pages[0], self.at(RED))
        QTest.keyClick(v.viewport(), Qt.Key_M)          # (into the command line)
        pump()
        self.assertIs(QApplication.focusWidget(), w.cad_line.edit)
        self.escape()
        self.assertEqual(self.selected(), 0)
        self.assertEqual(w.cad_line.edit.text(), "")
        self.assertIs(QApplication.focusWidget(), v)     # (and the keyboard back on the page)

    def test_with_the_keyboard_in_the_empty_command_line(self):
        w, v = self.w, self.v
        self.click(v.pages[0], self.at(RED))
        w.cad_line.edit.setFocus()
        pump()
        self.escape()
        self.assertEqual(self.selected(), 0)

    def test_after_a_click_on_empty_space_started_a_box(self):
        v = self.v
        self.click(v.pages[0], self.at(RED))
        self.click(v.pages[0], self.at(P(500, 700)))     # (nothing there: a box's corner)
        self.assertIsNotNone(v._cad_pick)
        self.escape()
        self.assertIsNone(v._cad_pick)
        self.assertEqual(self.selected(), 0)

    def test_markups_too(self):
        v = self.v
        x = v._create(0, {"kind": "rect", "rect": R(100, 650, 160, 700), "text": "",
                          "props": dict(A.DEFAULTS["rect"])})
        v.select_xref(0, x)
        self.click(v.pages[0], self.at(RED))
        self.assertEqual(self.selected(), 2)
        self.w.cad_line.edit.setFocus()
        pump()
        self.escape()
        self.assertEqual(self.selected(), 0)

    def test_a_command_running_is_cancelled_first(self):
        """As before: the first Escape ends the command, the selection stays for the next."""
        w, v = self.w, self.v
        self.click(v.pages[0], self.at(RED))
        w.start_cad_command("move")
        self.assertIsNotNone(v._cad_cmd)
        self.escape()
        self.assertIsNone(v._cad_cmd)
        self.assertEqual(self.selected(), 1)
        self.escape()
        self.assertEqual(self.selected(), 0)


class AlignToFirstSelected(CadWindow):
    def test_the_first_clicked_not_the_first_drawn(self):
        w, v = self.w, self.v
        self.click(v.pages[0], self.at(RED))             # (drawn last, clicked first)
        self.click(v.pages[0], self.at(LINE))
        w._set_align_ref("first")
        w._align("left")
        pump()
        self.assertEqual(self.lefts(), [(100, 350), (300, 100), (500, 350)])
        # again, with the selection read again after the move: the same one stays first
        w._align("right")
        pump()
        v._obj_cache.pop(0, None)
        rights = sorted((round(it["rect"].y0), round(it["rect"].x1))
                        for it in v.content_objects(0).items)
        self.assertEqual(rights, [(100, 450), (300, 300), (500, 450)])

    def test_the_other_way_round(self):
        w, v = self.w, self.v
        self.click(v.pages[0], self.at(LINE))
        self.click(v.pages[0], self.at(RED))
        w._set_align_ref("first")
        w._align("left")
        pump()
        self.assertEqual(self.lefts(), [(100, 100), (300, 100), (500, 100)])

    def test_last_selected(self):
        w, v = self.w, self.v
        self.click(v.pages[0], self.at(LINE))
        self.click(v.pages[0], self.at(RED))
        w._set_align_ref("last")
        self.addCleanup(lambda: w._set_align_ref("first"))
        w._align("left")
        pump()
        self.assertEqual(self.lefts(), [(100, 350), (300, 100), (500, 350)])

    def test_an_object_selected_before_a_markup(self):
        w, v = self.w, self.v
        x = v._create(0, {"kind": "rect", "rect": R(100, 650, 160, 700), "text": "",
                          "props": dict(A.DEFAULTS["rect"])})
        v.select_objects(0, [])
        v.clear_selection()
        self.click(v.pages[0], self.at(RED))             # (the object first)
        self.click(v.pages[0], self.at(P(100, 675)))     # (then the markup, on its edge)
        self.assertEqual(v.selected_xrefs(), [x])
        w._set_align_ref("first")
        w._align("left")
        pump()
        self.assertEqual(self.lefts()[-1], (500, 350))  # (the object stayed)
        page = v.doc[0]
        box = v._display_bounds(page, A.read(page.load_annot(x)))
        self.assertAlmostEqual(box.x0, 350, delta=1.5)


if __name__ == "__main__":
    unittest.main()
