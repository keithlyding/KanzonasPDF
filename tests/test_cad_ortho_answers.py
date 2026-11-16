"""CAD commands (CAD mouse mode): a question answered by typing Yes or No, as in AutoCAD
("Erase source objects? Yes / No"), and Shift or Ctrl keeping a clicked point straight across
or straight up and down from the point before (AutoCAD's Ortho).

The owner, 16 Nov 2026: "after the mirror action, it asks me if I want to keep or delete
original, but it doesn't register my typed in answer of no" (only the buttons' first letters,
K or D, were taken); "when I draw my line, I would like to be able to hold shift or ctrl to make
it 90 or 0 degrees".

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_cad_ortho_answers
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402
from PySide6.QtCore import QEvent, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QMouseEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import cad_commands  # noqa: E402
from kanzonas.document_view import DocumentView  # noqa: E402
from tests.test_cad_commands import segments  # noqa: E402

P = pymupdf.Point
LINE = ((100.0, 100.0), (200.0, 100.0))
MIRRORED = ((100.0, 300.0), (200.0, 300.0))     # across the line y = 200


class InCadMode(unittest.TestCase):
    rotation = 0

    def setUp(self):
        from kanzonas.main_window import MainWindow
        for k in ("snap_objects", "snap_page", "snap_grid"):
            self.addCleanup(setattr, DocumentView, k, getattr(DocumentView, k))
            setattr(DocumentView, k, False)
        d = pymupdf.open()
        page = d.new_page()
        page.draw_line(LINE[0], LINE[1])
        page.set_rotation(self.rotation)
        path = os.path.join(tempfile.mkdtemp(), "cad.pdf")
        d.save(path)
        w = self.w = MainWindow()
        old = w.settings.value("mouse_mode")
        self.addCleanup(lambda: w.settings.setValue("mouse_mode", old or "hand"))
        self.addCleanup(lambda: (setattr(w, "_close_confirmed", True), w.close()))
        w.resize(1100, 900)
        w.show()
        w.open_file(path)
        w.set_mouse_mode("cad")
        APP.processEvents()
        self.v = w.view()
        self.addCleanup(lambda: setattr(self.v, "dirty", False))
        self.line = w.cad_command_line()
        self.said = []
        w.statusBar().messageChanged.connect(self.said.append)

    def type(self, text):
        self.line.edit.setText(text)
        self.line.run()
        APP.processEvents()

    def select_line(self):
        self.v.select_objects(0, list(self.v.content_objects(0).items))

    def mirror_across_200(self):
        self.select_line()
        self.type("mi")
        self.v._cad_cmd.click(0, P(0, 200))
        self.v._cad_cmd.click(0, P(500, 200))


class Pointing(InCadMode):
    def press(self, pdf_point, mods=Qt.NoModifier):
        w = self.v.pages[0]
        pos = w.to_screen_pt(pdf_point)
        e = QMouseEvent(QEvent.MouseButtonPress, pos, w.mapToGlobal(pos.toPoint()),
                        Qt.LeftButton, Qt.LeftButton, mods)
        w.mousePressEvent(e)
        APP.processEvents()

    def hover(self, pdf_point, mods=Qt.NoModifier):
        w = self.v.pages[0]
        pos = w.to_screen_pt(pdf_point)
        e = QMouseEvent(QEvent.MouseMove, pos, w.mapToGlobal(pos.toPoint()),
                        Qt.NoButton, Qt.NoButton, mods)
        w.mouseMoveEvent(e)

    def screen(self, pdf_point):
        q = self.v.pages[0].to_screen_pt(pdf_point)
        return round(q.x(), 3), round(q.y(), 3)

    def start_mirror(self):
        self.select_line()
        self.type("mi")
        cmd = self.v._cad_cmd
        self.press(P(0, 200))
        return cmd


class TypedAnswers(InCadMode):
    def test_no_keeps_the_originals(self):
        for answer in ("no", "No", "NO", "n", "N"):
            self.mirror_across_200()
            self.type(answer)
            self.assertIsNone(self.v._cad_cmd, answer)
            self.assertEqual(segments(self.v.doc[0]), sorted([LINE, MIRRORED]), answer)
            self.v.undo()

    def test_yes_deletes_them(self):
        for answer in ("yes", "Yes", "y", "Y", "ye"):
            self.mirror_across_200()
            self.type(answer)
            self.assertIsNone(self.v._cad_cmd, answer)
            self.assertEqual(segments(self.v.doc[0]), [MIRRORED], answer)
            self.v.undo()

    def test_the_buttons_names_still_do_and_enter_is_no(self):
        self.mirror_across_200()
        self.type("k")                                  # Keep them
        self.assertEqual(segments(self.v.doc[0]), sorted([LINE, MIRRORED]))
        self.v.undo()
        self.mirror_across_200()
        self.type("delete")
        self.assertEqual(segments(self.v.doc[0]), [MIRRORED])
        self.v.undo()
        self.mirror_across_200()
        self.type("")                                   # Enter: No, as AutoCAD's <No>
        self.assertEqual(segments(self.v.doc[0]), sorted([LINE, MIRRORED]))

    def test_the_question_says_how_to_answer(self):
        self.mirror_across_200()
        self.assertIn("Yes or No", self.line.label.text())
        self.v._cad_cmd.cancel()

    def test_something_else_is_no_answer_and_the_question_stays(self):
        self.mirror_across_200()
        cmd = self.v._cad_cmd
        self.type("maybe")
        self.assertIs(self.v._cad_cmd, cmd)
        self.assertIn("isn't an answer", self.said[-1])
        self.assertEqual(segments(self.v.doc[0]), [LINE])
        self.type("n")
        self.assertEqual(segments(self.v.doc[0]), sorted([LINE, MIRRORED]))

    def test_align_takes_yes_and_no_too(self):
        for answer, scaled in (("n", False), ("yes", True)):
            self.select_line()
            self.type("al")
            cmd = self.v._cad_cmd
            for pt in ((100, 100), (100, 400), (200, 100), (300, 400)):
                cmd.click(0, P(*pt))
            self.type(answer)
            self.assertIsNone(self.v._cad_cmd, answer)
            want = ((100.0, 400.0), (300.0, 400.0)) if scaled else ((100.0, 400.0),
                                                                    (200.0, 400.0))
            self.assertEqual(segments(self.v.doc[0]), [want], answer)
            self.v.undo()

    def test_an_answer_in_the_users_language_without_its_accent(self):
        # ("Sí" typed as "si", as most keyboards make it easier)
        chosen = []

        class Asking:
            title = "Q"

            def gone(self):
                return False

            def choose(self, value):
                chosen.append(value)
        cmd = Asking()
        self.line.show_for(cmd, "?", choices=[("Mantenerlos", "keep", ("no", "No")),
                                              ("Eliminarlos", "delete", ("yes", "Sí"))])
        for typed in ("si", "Sí", "s", "n", "elim"):
            self.line.edit.setText(typed)
            self.line.run()
        self.assertEqual(chosen, ["delete", "delete", "delete", "keep", "delete"])
        self.line.done()


class StraightWithShiftOrCtrl(Pointing):
    def test_shift_makes_the_mirror_line_level(self):
        cmd = self.start_mirror()
        self.press(P(500, 230), Qt.ShiftModifier)       # (a little off level)
        self.assertEqual(self.screen(cmd.pts[1])[1], self.screen(cmd.pts[0])[1])
        self.type("n")
        self.assertEqual(segments(self.v.doc[0]), sorted([LINE, MIRRORED]))

    def test_ctrl_makes_it_upright(self):
        cmd = self.start_mirror()
        self.press(P(30, 500), Qt.ControlModifier)      # (a little off upright)
        self.assertEqual(self.screen(cmd.pts[1])[0], self.screen(cmd.pts[0])[0])
        cmd.cancel()

    def test_without_them_the_point_is_where_clicked(self):
        cmd = self.start_mirror()
        self.press(P(500, 230))
        self.assertNotEqual(self.screen(cmd.pts[1])[1], self.screen(cmd.pts[0])[1])
        cmd.cancel()

    def test_the_preview_follows_it_too(self):
        cmd = self.start_mirror()
        self.hover(P(500, 230), Qt.ShiftModifier)
        self.assertEqual(self.screen(cmd.hover)[1], self.screen(cmd.pts[0])[1])
        self.hover(P(500, 230))
        self.assertNotEqual(self.screen(cmd.hover)[1], self.screen(cmd.pts[0])[1])
        cmd.cancel()

    def test_a_move_stays_on_one_line(self):
        self.select_line()
        self.type("m")
        self.press(P(100, 100))
        self.press(P(100 + 7, 100 + 200), Qt.ShiftModifier)   # (mostly down: straight down)
        self.assertEqual(segments(self.v.doc[0]), [((100.0, 300.0), (200.0, 300.0))])

    def test_the_first_point_is_where_clicked(self):
        # (nothing before it to keep it straight from)
        self.select_line()
        self.type("mi")
        cmd = self.v._cad_cmd
        self.press(P(13, 207), Qt.ShiftModifier)
        self.assertEqual(self.screen(cmd.pts[0]), self.screen(P(13, 207)))
        cmd.cancel()

    def test_trim_picks_lines_where_clicked(self):
        self.assertIsNone(cad_commands.Trim(self.v, self.line).straight_from())


class StraightOnATurnedPage(Pointing):
    """As the page is shown: on a page turned a quarter, level on screen is upright in the
    file."""
    rotation = 90

    def test_shift_makes_the_mirror_line_level(self):
        cmd = self.start_mirror()
        first = self.screen(cmd.pts[0])
        w = self.v.pages[0]
        off_level = w.to_pdf(QPointF(first[0] + 300, first[1] + 20))
        self.press(off_level, Qt.ShiftModifier)
        self.assertEqual(self.screen(cmd.pts[1])[1], first[1])
        self.assertAlmostEqual(cmd.pts[1].x, cmd.pts[0].x, 3)    # (upright in the file)
        cmd.cancel()


if __name__ == "__main__":
    unittest.main()
