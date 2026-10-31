"""CAD mode as a CAD user expects it: it starts with Edit objects, so a blue / green box takes
the drawing's own lines (Select takes only markups and text: on a plain drawing a box took
nothing); the Home tab starts with the three mouse modes (Select, Hand, CAD); a command started
with nothing selected asks for the selection and Enter goes on (as AutoCAD); Trim takes cutting
edges, selected before TR or when it asks, and cuts only up to those; Delete started first
works the same way. One selection takes everything: the drawing's lines and text and the
markups drawn on it, by box or by click; Move and Delete do them together, as one undo step.

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


def drawing(cloud=False, text=False):
    """A level line crossed by two plumb lines (and a rectangle markup, and a label)."""
    d = pymupdf.open()
    p = d.new_page(width=400, height=300)
    p.draw_line((50, 150), (350, 150))
    p.draw_line((150, 50), (150, 250))
    p.draw_line((250, 50), (250, 250))
    if cloud:
        p.add_rect_annot(pymupdf.Rect(170, 60, 230, 120))
    if text:
        p.insert_text((60, 280), "PANEL A", fontsize=10)
    path = os.path.join(tempfile.mkdtemp(), "d.pdf")
    d.save(path)
    return path


def lines(page):
    return sorted((round(a.x), round(a.y), round(b.x), round(b.y))
                  for dr in page.get_drawings() for it in dr["items"] if it[0] == "l"
                  for a, b in [it[1:3]])


class Window(unittest.TestCase):
    """A window in CAD mode with the drawing open (no tests of its own)."""
    CLOUD = TEXT = False

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
        w.open_file(drawing(self.CLOUD, self.TEXT))
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



class CadMode(Window):
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


class StartsInCad(unittest.TestCase):
    """A window made while the saved mouse mode is CAD (start-up, a pulled-out tab) starts
    with Edit objects (it raised KeyError, and start-up then reset every setting)."""

    def test_a_new_window_in_cad_mode(self):
        w = main_window.MainWindow()
        old = {k: w.settings.value(k) for k in ("mouse_mode", "mouse_before_cad")}

        def back():
            for k, v in old.items():
                w.settings.setValue(k, v) if v is not None else w.settings.remove(k)
            mouse_modes.apply(w.settings)
        self.addCleanup(back)
        self.addCleanup(lambda: [setattr(x, "_close_confirmed", True) or x.close()
                                 for x in main_window.windows()])
        w.set_mouse_mode("cad")
        other = main_window.MainWindow()
        self.assertEqual(other.tool, "editobjects")
        self.assertTrue(other.tool_actions["editobjects"].isChecked())
        w.open_file(drawing())
        moved = w.detach_tab(0)
        self.assertIsNotNone(moved)
        self.assertEqual(moved.tabs.count(), 1)
        self.assertEqual(moved.tool, "editobjects")


class Protected(Window):
    """A file whose drawing can't be changed (markups can): a selection holding both is
    refused whole, with the reason, instead of changing only the markups."""
    CLOUD = True

    def setUp(self):
        super().setUp()
        allowed = self.v.allowed
        from unittest import mock
        patch = mock.patch.object(self.v, "allowed", side_effect=lambda p: (
            p != pymupdf.PDF_PERM_MODIFY and allowed(p)))
        patch.start()
        self.addCleanup(patch.stop)
        info = mock.patch("kanzonas.document_view.QMessageBox.information")
        self.said = info.start()
        self.addCleanup(info.stop)

    def cloud_top(self):
        page = self.v.doc[0]                # (kept alive while its annotation is read)
        return pymupdf.Rect(next(page.annots()).rect).y0

    def test_delete_and_move_of_both_are_refused_whole(self):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        self.box(140, 40, 260, 260)
        QTest.keyClick(self.v, Qt.Key_Delete)
        self.assertTrue(self.said.called)
        self.assertEqual(len(list(self.v.doc[0].annots())), 1)
        self.assertEqual(len(lines(self.v.doc[0])), 3)
        self.box(140, 40, 260, 260)
        self.type("m")
        cmd = self.v._cad_cmd
        if cmd is not None:                 # (Move may refuse to start at all)
            cmd.click(0, pymupdf.Point(200, 150))
            cmd.click(0, pymupdf.Point(200, 180))
        self.assertLess(abs(self.cloud_top() - 60), 3)
        self.assertEqual(len(lines(self.v.doc[0])), 3)
        self.assertIn((150, 50, 150, 250), lines(self.v.doc[0]))
        # through the command itself too: cad_apply refuses the whole selection
        self.v.cad_apply("Moved", pymupdf.Matrix(1, 0, 0, 1, 0, 30))
        self.assertLess(abs(self.cloud_top() - 60), 3)


class Everything(CadMode):
    """CAD mode's selection takes the drawing's objects, its text and the markups together."""
    CLOUD = TEXT = True

    def markups(self):
        return [pymupdf.Rect(a.rect) for a in self.v.doc[0].annots()]

    def test_a_box_takes_lines_text_and_markups(self):
        self.box(10, 10, 390, 295)
        kinds = sorted(it["kind"] for it in self.v.obj_sel[1])
        self.assertEqual(kinds.count("text"), 1)
        self.assertEqual(len(kinds), 4)
        self.assertEqual(len(self.v.selected_xrefs()), 1)
        self.assertEqual(self.v.cad_targets()[0], "both")

    def test_a_click_adds_a_markup_to_the_objects(self):
        from kanzonas import cad_select
        self.box(140, 40, 160, 260)                 # a plumb line
        pw = self.v.pages[0]
        xref = self.v.annot_at(0, pymupdf.Point(170, 90))
        self.assertIsNotNone(xref)
        cad_select.toggle(pw, "markup", xref, False)
        self.assertEqual(len(self.v.obj_sel[1]), 1)
        self.assertEqual(self.v.selected_xrefs(), [xref])

    def test_move_moves_both_and_one_undo_puts_both_back(self):
        self.box(140, 40, 260, 260)                 # both plumb lines and the markup
        before_lines, before_marks = lines(self.v.doc[0]), self.markups()
        self.type("m")
        cmd = self.v._cad_cmd
        cmd.click(0, pymupdf.Point(200, 150))
        cmd.click(0, pymupdf.Point(200, 180))
        self.assertIn((150, 80, 150, 280), lines(self.v.doc[0]))
        self.assertAlmostEqual(self.markups()[0].y0, before_marks[0].y0 + 30, delta=1)
        self.v.undo()
        self.assertEqual(lines(self.v.doc[0]), before_lines)
        self.assertAlmostEqual(self.markups()[0].y0, before_marks[0].y0, delta=1)

    def test_delete_takes_both_and_one_undo_puts_both_back(self):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        self.box(140, 40, 260, 260)
        QTest.keyClick(self.v, Qt.Key_Delete)
        self.assertEqual(len(lines(self.v.doc[0])), 1)
        self.assertEqual(self.markups(), [])
        self.v.undo()
        self.assertEqual(len(lines(self.v.doc[0])), 3)
        self.assertEqual(len(self.markups()), 1)

    def test_copy_places_both_each_time(self):
        self.box(140, 40, 260, 260)
        self.type("co")
        cmd = self.v._cad_cmd
        cmd.click(0, pymupdf.Point(200, 150))
        cmd.click(0, pymupdf.Point(200, 170))       # a copy...
        cmd.click(0, pymupdf.Point(200, 190))       # ...and another
        self.type("")
        self.assertEqual(len(self.markups()), 3)
        self.assertIn((150, 90, 150, 290), lines(self.v.doc[0]))
        self.assertIn((150, 70, 150, 270), lines(self.v.doc[0]))
        self.assertIn((150, 50, 150, 250), lines(self.v.doc[0]))

    def test_rotate_turns_both(self):
        self.box(140, 40, 260, 260)
        self.type("ro")
        cmd = self.v._cad_cmd
        cmd.click(0, pymupdf.Point(200, 150))       # the base point
        self.type("90")
        self.assertIn((100, 100, 300, 100), lines(self.v.doc[0]))   # (one plumb line, lying)
        c = (self.markups()[0].tl + self.markups()[0].br) / 2       # (it was at 200, 90)
        self.assertAlmostEqual(c.y, 150, delta=3)
        self.assertAlmostEqual(abs(c.x - 200), 60, delta=3)

    def test_after_a_move_both_stay_selected(self):
        self.box(140, 40, 260, 260)
        self.type("m")
        cmd = self.v._cad_cmd
        cmd.click(0, pymupdf.Point(200, 150))
        cmd.click(0, pymupdf.Point(200, 180))
        self.assertEqual(len(self.v.obj_sel[1]), 2)
        self.assertEqual(len(self.v.selected_xrefs()), 1)

    def test_array_copies_both_and_one_undo_takes_them_away(self):
        from unittest import mock
        from PySide6.QtWidgets import QDialog
        self.box(140, 40, 260, 260)
        with mock.patch.object(QDialog, "exec", return_value=QDialog.Accepted):  # 1 x 3
            self.type("ar")
        cmd = self.v._cad_cmd
        cmd.click(0, pymupdf.Point(200, 150))
        cmd.click(0, pymupdf.Point(200, 160))       # each column 10 lower
        self.assertEqual(len(self.markups()), 3)
        self.assertIn((150, 70, 150, 270), lines(self.v.doc[0]))
        self.v.undo()
        self.assertEqual(len(self.markups()), 1)
        self.assertEqual(len(lines(self.v.doc[0])), 3)

    def test_a_markup_alone_doesnt_join_an_older_undo_step(self):
        self.box(140, 40, 160, 260)
        self.type("e")                              # delete a plumb line: one step
        self.box(165, 55, 235, 125)                 # now only the markup
        self.assertIsNone(self.v.obj_sel)
        self.type("e")
        self.assertEqual(self.markups(), [])
        self.v.undo()                               # brings back the markup only
        self.assertEqual(len(self.markups()), 1)
        self.assertEqual(len(lines(self.v.doc[0])), 2)


if __name__ == "__main__":
    unittest.main()
