"""The CAD tab's commands, as in AutoCAD: select, then Move, Copy, Rotate, Scale, Mirror,
Delete, Align, Array or Trim, answering the prompts with clicks on the page (or a typed value).
On the drawing's own line work (Edit objects) and on markups. The CAD tab and menu show only
in CAD mouse mode.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_cad_commands
"""
import math
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402
from PySide6.QtCore import QEvent, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QKeyEvent, QMouseEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import annotations, cad_commands  # noqa: E402
from kanzonas.document_view import DocumentView  # noqa: E402

P = pymupdf.Point


def saved(build):
    d = pymupdf.open()
    p = d.new_page()
    build(p)
    path = os.path.join(tempfile.mkdtemp(), "cad.pdf")
    d.save(path)
    return path


def one_line(p):
    p.draw_line((100, 100), (200, 100))


def segments(page):
    """Every straight piece of the page's line work, rounded: [((x0, y0), (x1, y1))]."""
    out = []
    for d in page.get_drawings():
        for it in d["items"]:
            if it[0] == "l":
                a, b = sorted([(round(it[1].x, 1), round(it[1].y, 1)),
                               (round(it[2].x, 1), round(it[2].y, 1))])
                out.append((a, b))
    return sorted(out)


class Commands(unittest.TestCase):
    def view(self, build, tool="editobjects"):
        for key in ("snap_objects", "snap_page", "snap_grid"):
            self.addCleanup(setattr, DocumentView, key, getattr(DocumentView, key))
            setattr(DocumentView, key, False)           # the clicks land where they're made
        v = DocumentView(saved(build))
        self.addCleanup(v.close_doc)
        v.resize(900, 1000)
        v.show()
        v.set_zoom(1.0)
        APP.processEvents()
        v.set_tool(tool)
        self.prompt = cad_commands.Prompt()
        self.addCleanup(self.prompt.deleteLater)
        return v

    def select_all_objects(self, v):
        objs = v.content_objects(0)
        v.select_objects(0, list(objs.items))

    def command(self, v, key, clicks=(), typed=None, choose=None):
        cmd = cad_commands.COMMANDS[key](v, self.prompt)
        self.assertTrue(cmd.start(), key)
        w = v.pages[0]
        for pt in clicks:
            pos = QPointF(w.to_screen_pt(P(pt)))
            for t in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease):
                ev = QMouseEvent(t, pos, w.mapToGlobal(pos), Qt.LeftButton,
                                 Qt.LeftButton if t == QEvent.MouseButtonPress else Qt.NoButton,
                                 Qt.NoModifier)
                (w.mousePressEvent if t == QEvent.MouseButtonPress else w.mouseReleaseEvent)(ev)
        if typed is not None:
            self.prompt.edit.setText(typed)
            self.prompt._typed()
        if choose is not None:
            cmd.choose(choose)
        APP.processEvents()
        return cmd

    def test_move(self):
        v = self.view(one_line)
        self.select_all_objects(v)
        self.command(v, "move", [(300, 300), (330, 350)])
        self.assertEqual(segments(v.doc[0]), [((130, 150), (230, 150))])
        self.assertIsNone(v._cad_cmd)

    def test_copy_places_as_many_as_clicked(self):
        v = self.view(one_line)
        self.select_all_objects(v)
        cmd = self.command(v, "copy", [(100, 100), (100, 150), (100, 200)])
        self.assertIs(v._cad_cmd, cmd)                          # still placing copies
        cmd.enter()
        self.assertIsNone(v._cad_cmd)
        self.assertEqual(segments(v.doc[0]), [((100, 100), (200, 100)),
                                              ((100, 150), (200, 150)),
                                              ((100, 200), (200, 200))])

    def test_rotate_by_a_typed_angle(self):
        v = self.view(one_line)
        self.select_all_objects(v)
        self.command(v, "rotate", [(100, 100)], typed="90")       # counterclockwise: up
        self.assertEqual(segments(v.doc[0]), [((100, 0), (100, 100))])

    def test_rotate_by_a_clicked_point(self):
        v = self.view(one_line)
        self.select_all_objects(v)
        self.command(v, "rotate", [(100, 100), (100, 300)])       # straight down: -90
        self.assertEqual(segments(v.doc[0]), [((100, 100), (100, 200))])

    def test_scale_typed_and_by_two_lengths(self):
        v = self.view(one_line)
        self.select_all_objects(v)
        self.command(v, "scale", [(100, 100)], typed="2")
        self.assertEqual(segments(v.doc[0]), [((100, 100), (300, 100))])
        self.select_all_objects(v)
        self.command(v, "scale", [(100, 100), (300, 100), (200, 100)])    # 200 long becomes 100
        self.assertEqual(segments(v.doc[0]), [((100, 100), (200, 100))])

    def test_mirror_keeps_or_deletes_the_originals(self):
        v = self.view(one_line)
        self.select_all_objects(v)
        self.command(v, "mirror", [(0, 150), (500, 150)], choose="keep")
        self.assertEqual(segments(v.doc[0]), [((100, 100), (200, 100)),
                                              ((100, 200), (200, 200))])
        v.select_objects(0, [v.content_objects(0).items[0]])
        self.command(v, "mirror", [(250, 0), (250, 500)], choose="delete")
        self.assertIn(((300, 100), (400, 100)), segments(v.doc[0]))
        self.assertNotIn(((100, 100), (200, 100)), segments(v.doc[0]))

    def test_align_two_pairs_of_points(self):
        v = self.view(one_line)
        self.select_all_objects(v)
        # the line's ends go to (300, 300) and straight below it
        self.command(v, "align", [(100, 100), (300, 300), (200, 100), (300, 500)], choose="no")
        self.assertEqual(segments(v.doc[0]), [((300, 300), (300, 400))])
        self.select_all_objects(v)
        self.command(v, "align", [(300, 300), (300, 300), (300, 400), (300, 500)], choose="yes")
        self.assertEqual(segments(v.doc[0]), [((300, 300), (300, 500))])

    def test_array_rows_and_columns(self):
        v = self.view(one_line)
        self.select_all_objects(v)

        def answer(dlg):
            from PySide6.QtWidgets import QSpinBox
            rows, cols = dlg.findChildren(QSpinBox)
            rows.setValue(2)
            cols.setValue(3)
            return QDialog.Accepted
        with mock.patch.object(QDialog, "exec", answer):
            self.command(v, "array", [(100, 100), (100, 120), (300, 100)])
        got = segments(v.doc[0])
        self.assertEqual(len(got), 6)
        self.assertIn(((300, 140), (400, 140)), got)            # row 2, column 3

    def test_delete(self):
        v = self.view(one_line)
        self.select_all_objects(v)
        from kanzonas.main_window import MainWindow
        w = MainWindow()
        self.addCleanup(lambda: (setattr(w, "_close_confirmed", True), w.close()))
        with mock.patch.object(w, "view", lambda: v):
            w.start_cad_command("delete")
        self.assertEqual(segments(v.doc[0]), [])

    def test_trim_cuts_between_the_crossing_lines(self):
        def build(p):
            p.draw_line((100, 100), (400, 100))
            p.draw_line((200, 50), (200, 150))
            p.draw_line((300, 50), (300, 150))
        v = self.view(build)
        cmd = self.command(v, "trim", [(250, 100)])                 # no selection needed
        self.assertIs(v._cad_cmd, cmd)
        self.assertEqual(segments(v.doc[0]), [((100, 100), (200, 100)),
                                              ((200, 50), (200, 150)),
                                              ((300, 50), (300, 150)),
                                              ((300, 100), (400, 100))])
        cmd.click(0, P(350, 100))                               # to the free end
        self.assertNotIn(((300, 100), (400, 100)), segments(v.doc[0]))
        cmd.click(0, P(200, 60))                                # nothing crosses above
        self.assertIn(((200, 100), (200, 150)), segments(v.doc[0]))
        cmd.enter()
        self.assertIsNone(v._cad_cmd)
        v.undo()
        self.assertIn(((200, 50), (200, 150)), segments(v.doc[0]))

    def test_trim_a_line_markup(self):
        def build(p):
            p.draw_line((200, 50), (200, 150))
            a = p.add_line_annot((100, 100), (400, 100))
            a.update()
        v = self.view(build, "select")
        self.command(v, "trim", [(300, 100)])
        page = v.doc[0]
        lines = [annotations.read(a) for a in page.annots()]
        self.assertEqual(len(lines), 1)
        xs = sorted(round(q.x) for q in lines[0]["points"])
        self.assertEqual(xs, [100, 200])

    def test_markups_move_and_turn(self):
        def build(p):
            a = p.add_line_annot((100, 100), (200, 100))
            a.update()
            a = p.add_rect_annot(pymupdf.Rect(300, 300, 400, 340))
            a.update()
        v = self.view(build, "select")
        page = v.doc[0]
        v._set_selection(0, [a.xref for a in page.annots()])
        self.command(v, "rotate", [(100, 100)], typed="90")
        models = {m["kind"]: m for m in (annotations.read(a) for a in v.doc[0].annots())}
        line = sorted((round(q.x), round(q.y)) for q in models["line"]["points"])
        self.assertEqual(line, [(100, 0), (100, 100)])
        self.assertAlmostEqual(annotations.angle(models["rect"]), 90, places=1)

    def test_a_command_needs_a_selection(self):
        v = self.view(one_line)
        cmd = cad_commands.COMMANDS["move"](v, self.prompt)
        said = []
        v.statusMessage.connect(said.append)
        self.assertFalse(cmd.start())
        self.assertIsNone(v._cad_cmd)
        self.assertIn("select what to change first", said[-1])

    def test_escape_cancels(self):
        v = self.view(one_line)
        self.select_all_objects(v)
        self.command(v, "move", [(300, 300)])
        self.assertIsNotNone(v._cad_cmd)
        v.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier))
        self.assertIsNone(v._cad_cmd)
        self.assertEqual(segments(v.doc[0]), [((100, 100), (200, 100))])


class Geometry(unittest.TestCase):
    def test_mirror_and_rotation_matrices(self):
        m = cad_commands.mirror(P(0, 0), P(10, 0))              # the x axis
        self.assertEqual(P(3, 4) * m, P(3, -4))
        r = cad_commands.rotation(P(0, 0), 90)                  # counterclockwise on screen
        q = P(10, 0) * r
        self.assertAlmostEqual(q.x, 0, places=6)
        self.assertAlmostEqual(q.y, -10, places=6)
        self.assertAlmostEqual(cad_commands.screen_angle(P(0, 0), P(0, -5)), 90)
        a = cad_commands.align(P(0, 0), P(10, 10), P(1, 0), P(10, 12), scale=True)
        self.assertAlmostEqual((P(1, 0) * a).y, 12, places=6)
        self.assertTrue(math.isclose((P(0, 0) * a).x, 10))


class CadTab(unittest.TestCase):
    def test_only_in_cad_mode(self):
        from kanzonas.main_window import MainWindow
        w = MainWindow()
        self.addCleanup(lambda: (setattr(w, "_close_confirmed", True), w.close()))
        old = w.settings.value("mouse_mode")
        self.addCleanup(lambda: w.settings.setValue("mouse_mode", old or "hand"))
        i = w.ribbon.indexOf(w._cad_tab)
        w.set_mouse_mode("hand")
        self.assertFalse(w.ribbon.isTabVisible(i))
        self.assertFalse(w.cad_menu.menuAction().isVisible())
        w.set_mouse_mode("cad")
        self.assertTrue(w.ribbon.isTabVisible(i))
        self.assertTrue(w.cad_menu.menuAction().isVisible())
        w.set_mouse_mode("standard")
        self.assertFalse(w.ribbon.isTabVisible(i))


if __name__ == "__main__":
    unittest.main()
