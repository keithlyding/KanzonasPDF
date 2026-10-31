"""The CAD command line (CAD mouse mode), as in AutoCAD: type M, MOV or MOVE (CO, RO, SC, MI,
E, AL, AR, TR...) and Enter (only Enter: Space types a space); any other command by its name,
found like the command palette finds it, but only a sure match runs (else "Unknown command",
nothing runs); Enter on an empty line repeats the last command; while a command runs the
same line takes its values and choices; Escape clears the line or cancels the command. In CAD
mode, letters typed over the drawing go to the line.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_cad_command_line
"""
import os
import sys
import tempfile
import unittest
import unittest.mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402
from PySide6.QtCore import QEvent, Qt  # noqa: E402
from PySide6.QtGui import QKeyEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QLineEdit  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import cad_commands  # noqa: E402
from kanzonas.document_view import DocumentView  # noqa: E402
from tests.test_cad_commands import segments  # noqa: E402

P = pymupdf.Point


def key(k, text=""):
    return QKeyEvent(QEvent.KeyPress, k, Qt.NoModifier, text)


class Names(unittest.TestCase):
    def test_short_names_and_starts_of_names(self):
        for typed, cmd in (("m", "move"), ("MOV", "move"), ("move", "move"), ("co", "copy"),
                           ("cp", "copy"), ("cop", "copy"), ("ro", "rotate"), ("sc", "scale"),
                           ("mi", "mirror"), ("e", "delete"), ("erase", "delete"),
                           ("al", "align"), ("ar", "array"), ("tr", "trim"), (" tri ", "trim")):
            self.assertEqual(cad_commands.resolve(typed), cmd, typed)
        self.assertIsNone(cad_commands.resolve("a"))            # Align or Array?
        self.assertIsNone(cad_commands.resolve("cloud"))
        self.assertIsNone(cad_commands.resolve(""))


class CommandLine(unittest.TestCase):
    def setUp(self):
        from kanzonas.main_window import MainWindow
        for k in ("snap_objects", "snap_page", "snap_grid"):
            self.addCleanup(setattr, DocumentView, k, getattr(DocumentView, k))
            setattr(DocumentView, k, False)
        d = pymupdf.open()
        d.new_page().draw_line((100, 100), (200, 100))
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

    def type(self, text):
        self.line.edit.setText(text)
        self.line.run()
        APP.processEvents()

    def select_line(self):
        self.v.select_objects(0, list(self.v.content_objects(0).items))

    def test_the_line_is_there_in_cad_mode_only(self):
        self.assertTrue(self.w.cad_bar.isVisible())
        self.w.set_mouse_mode("hand")
        self.assertFalse(self.w.cad_bar.isVisible())

    def test_typed_move_runs_move(self):
        self.select_line()
        self.type("mov")
        self.assertIsInstance(self.v._cad_cmd, cad_commands.Move)
        self.assertIn("base point", self.line.label.text())
        self.v._cad_cmd.click(0, P(100, 100))
        self.v._cad_cmd.click(0, P(100, 300))
        self.assertEqual(segments(self.v.doc[0]), [((100, 300), (200, 300))])
        self.assertIn("Command", self.line.label.text())          # back to waiting

    def test_values_and_choices_are_typed_on_the_same_line(self):
        self.select_line()
        self.type("ro")
        self.v._cad_cmd.click(0, P(100, 100))
        self.type("90")
        self.assertEqual(segments(self.v.doc[0]), [((100, 0), (100, 100))])
        self.select_line()
        self.type("mi")
        self.v._cad_cmd.click(0, P(0, 200))
        self.v._cad_cmd.click(0, P(500, 200))
        self.type("d")                                          # "Delete them"
        self.assertEqual(segments(self.v.doc[0]), [((100, 300), (100, 400))])

    def test_enter_on_an_empty_line_repeats_the_last_command(self):
        self.select_line()
        self.type("co")
        cmd = self.v._cad_cmd
        cmd.click(0, P(100, 100))
        cmd.click(0, P(100, 150))
        self.type("")                                           # Enter: done placing copies
        self.assertIsNone(self.v._cad_cmd)
        self.select_line()
        self.type("")                                           # Enter again: Copy again
        self.assertIsInstance(self.v._cad_cmd, cad_commands.Copy)

    def test_any_other_command_by_its_name(self):
        self.v.fit_mode = None
        self.type("fit page")
        self.assertEqual(self.v.fit_mode, "page")
        said = []
        self.w.statusBar().messageChanged.connect(said.append)
        before = self.v.fit_mode
        for typo in ("zzqqx", "mve", "ftpg"):           # letters scattered through a name
            self.type(typo)
            self.assertIn("Unknown command", said[-1], typo)
            self.assertEqual(self.line.edit.text(), typo)  # kept, to correct
            self.assertIsNone(self.v._cad_cmd)
        self.assertEqual(self.v.fit_mode, before)
        self.line.edit.setText("rect")
        self.line.run()
        self.assertEqual(self.w.tool, "rect")

    def test_a_command_first_then_the_selection_then_enter(self):
        # as AutoCAD: M with nothing selected asks for the selection; Enter goes on
        said = []
        self.v.statusMessage.connect(said.append)
        self.v.set_tool("editobjects")
        self.type("m")
        cmd = self.v._cad_cmd
        self.assertIsNotNone(cmd)
        self.assertTrue(cmd.selecting)
        self.line.edit.setText("")
        self.line.run()                     # Enter with nothing selected: says so, waits
        self.assertIs(self.v._cad_cmd, cmd)
        self.assertIn("nothing is selected yet", said[-1])
        self.v.select_objects(0, self.v.content_objects(0).items)
        self.line.run()                     # Enter: the selection is taken, on to the points
        self.assertIsNotNone(self.v._cad_cmd)
        self.assertFalse(self.v._cad_cmd.selecting)
        self.assertTrue(self.v._cad_cmd.ghost)
        self.v._cad_cmd.cancel()

    def test_keys_typed_over_the_drawing_go_to_the_line(self):
        self.line.take_key(key(Qt.Key_M, "m"))
        self.line.take_key(key(Qt.Key_O, "o"))
        self.assertEqual(self.line.edit.text(), "mo")
        self.line.take_key(key(Qt.Key_Space, " "))              # Space types a space
        self.assertEqual(self.line.edit.text(), "mo ")
        self.assertIsNone(self.v._cad_cmd)
        self.line.edit.setText("mo")
        self.select_line()
        self.line.take_key(key(Qt.Key_Return))                  # only Enter runs it
        self.assertIsInstance(self.v._cad_cmd, cad_commands.Move)

    def test_which_keys_go_to_the_line(self):
        w, v = self.w, self.v
        v.setFocus()
        APP.processEvents()
        with unittest.mock.patch.object(type(w), "isActiveWindow", lambda self: True), \
                unittest.mock.patch.object(QApplication, "focusWidget", lambda: v):
            self.assertTrue(w.cad_typing(v, key(Qt.Key_V, "v")))     # not the Select shortcut
            self.assertTrue(w.cad_typing(v, key(Qt.Key_Return)))     # idle: repeat
            self.assertFalse(w.cad_typing(v, QKeyEvent(QEvent.KeyPress, Qt.Key_S,
                                                       Qt.ControlModifier, "s")))
            self.assertFalse(w.cad_typing(v, key(Qt.Key_Delete)))
            self.assertFalse(w.cad_typing(v, key(Qt.Key_Escape)))
            self.assertFalse(w.cad_typing(v, key(Qt.Key_Space, " ")))   # empty line: not taken
            w.set_mouse_mode("standard")
            self.assertFalse(w.cad_typing(v, key(Qt.Key_V, "v")))    # V selects again
        box = QLineEdit(w)
        with unittest.mock.patch.object(type(w), "isActiveWindow", lambda self: True), \
                unittest.mock.patch.object(QApplication, "focusWidget", lambda: box):
            w.set_mouse_mode("cad")
            self.assertFalse(w.cad_typing(box, key(Qt.Key_V, "v")))  # typing in a box

    def test_escape_clears_the_line_then_cancels(self):
        self.line.edit.setText("mo")
        self.line.eventFilter(self.line.edit, key(Qt.Key_Escape))
        self.assertEqual(self.line.edit.text(), "")
        self.select_line()
        self.type("m")
        self.line.eventFilter(self.line.edit, key(Qt.Key_Escape))
        self.assertIsNone(self.v._cad_cmd)


if __name__ == "__main__":
    unittest.main()
