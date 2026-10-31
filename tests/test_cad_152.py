"""CAD mode as a CAD user expects it: it starts with Edit objects, so a blue / green box takes
the drawing's own lines (Select takes only markups and text: on a plain drawing a box took
nothing); the Home tab starts with the three mouse modes (Select, Hand, CAD); a command started
with nothing selected asks for the selection and Enter goes on (as AutoCAD); Trim takes cutting
edges, selected before TR or when it asks, and cuts only up to those; Delete started first
works the same way.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_cad_152
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402
from PySide6.QtWidgets import QApplication, QToolButton  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import main_window, mouse_modes  # noqa: E402
from kanzonas.page_objects import Box  # noqa: E402


def drawing():
    """A level line crossed by two plumb lines."""
    d = pymupdf.open()
    p = d.new_page(width=400, height=300)
    p.draw_line((50, 150), (350, 150))
    p.draw_line((150, 50), (150, 250))
    p.draw_line((250, 50), (250, 250))
    path = os.path.join(tempfile.mkdtemp(), "d.pdf")
    d.save(path)
    return path


def lines(page):
    return sorted((round(a.x), round(a.y), round(b.x), round(b.y))
                  for dr in page.get_drawings() for it in dr["items"] if it[0] == "l"
                  for a, b in [it[1:3]])


class CadMode(unittest.TestCase):
    def setUp(self):
        w = self.w = main_window.MainWindow()
        old = {k: w.settings.value(k) for k in ("mouse_mode", "mouse_before_cad")}

        def back():
            for k, v in old.items():
                w.settings.setValue(k, v) if v is not None else w.settings.remove(k)
            mouse_modes.apply(w.settings)
        self.addCleanup(back)
        self.addCleanup(lambda: [setattr(x, "_close_confirmed", True) or x.close()
                                 for x in main_window.windows()])
        w.resize(1000, 800)
        w.show()
        w.set_mouse_mode("cad")
        w.open_file(drawing())
        APP.processEvents()
        self.v = w.view()
        self.addCleanup(lambda: setattr(self.v, "dirty", False))
        self.line = w.cad_command_line()

    def type(self, text):
        self.line.edit.setText(text)
        self.line.run()

    def box(self, x0, y0, x1, y1):
        from kanzonas import cad_select
        cad_select.pick(self.v.pages[0], Box(pymupdf.Rect(x0, y0, x1, y1)), False, False)

    def test_cad_mode_selects_the_drawings_lines(self):
        self.assertEqual(self.v.tool, "editobjects")
        self.box(40, 40, 360, 260)
        self.assertEqual(len(self.v.obj_sel[1]), 3)

    def test_the_home_tab_starts_with_select_hand_cad(self):
        home = self.w.ribbon.widget(0)
        buttons = [b.defaultAction() for b in home.findChildren(QToolButton)
                   if b.defaultAction() is not None]
        self.assertEqual(buttons[:3], [self.w.a_mouse_standard, self.w.a_mouse_hand,
                                       self.w.a_cad_mouse])

    def test_move_first_then_select_then_enter(self):
        self.type("m")
        cmd = self.v._cad_cmd
        self.assertTrue(cmd.selecting)
        self.box(140, 40, 160, 260)         # the first plumb line
        self.type("")
        self.assertFalse(cmd.selecting)
        cmd.click(0, pymupdf.Point(150, 150))
        cmd.click(0, pymupdf.Point(180, 150))
        self.assertIn((180, 50, 180, 250), lines(self.v.doc[0]))

    def test_trim_first_then_cutting_edges_then_enter(self):
        self.type("tr")
        cmd = self.v._cad_cmd
        self.assertTrue(cmd.selecting)
        self.box(140, 40, 260, 260)         # the two plumb lines are the edges
        self.type("")
        self.assertIsNotNone(cmd.edges)
        cmd.click(0, pymupdf.Point(200, 150))
        self.type("")
        self.assertEqual(lines(self.v.doc[0]), [(50, 150, 150, 150), (150, 50, 150, 250),
                                                (250, 50, 250, 250), (250, 150, 350, 150)])

    def test_edges_selected_before_trim_are_its_only_edges(self):
        self.box(140, 40, 160, 260)         # only the first plumb line
        self.type("tr")
        cmd = self.v._cad_cmd
        self.assertFalse(cmd.selecting)
        cmd.click(0, pymupdf.Point(300, 150))   # right of it: cut to its end, not to x=250
        self.type("")
        self.assertIn((50, 150, 150, 150), lines(self.v.doc[0]))
        self.assertNotIn((250, 150, 350, 150), lines(self.v.doc[0]))

    def test_delete_first_then_select_then_enter(self):
        self.type("e")
        self.assertTrue(self.v._cad_cmd.selecting)
        self.box(140, 40, 160, 260)
        self.type("")
        self.assertIsNone(self.v._cad_cmd)
        self.assertEqual(len(lines(self.v.doc[0])), 2)


if __name__ == "__main__":
    unittest.main()
