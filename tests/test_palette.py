"""Command palette: fuzzy matching, the list of commands, Enter runs one, recent first."""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QAction  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas.main_window import MainWindow  # noqa: E402
from kanzonas.palette import CommandPalette, match  # noqa: E402


class Matching(unittest.TestCase):
    def test_substring_beats_scattered_letters(self):
        self.assertGreater(match("save", "Save As"), match("save", "Shapes and values"))

    def test_letters_in_order_match_and_word_starts_score(self):
        self.assertIsNotNone(match("sv as", "Save As"))
        self.assertIsNotNone(match("rot l", "Rotate page left"))
        self.assertIsNone(match("xyz", "Save As"))
        self.assertGreater(match("rpl", "Rotate page left"), match("rpl", "Properties panel"))

    def test_empty_query_matches_everything(self):
        self.assertEqual(match("", "Anything"), 0)

    def test_case_does_not_matter(self):
        self.assertEqual(match("SAVE", "save as"), match("save", "Save As"))


class Palette(unittest.TestCase):
    def setUp(self):
        self.w = MainWindow()
        self.w.show()
        APP.processEvents()
        self.w.settings.remove("palette_recent")
        self.addCleanup(lambda: (setattr(self.w, "_close_confirmed", True), self.w.close()))

    def test_lists_commands_with_menu_and_shortcut(self):
        pal = CommandPalette(self.w)
        names = [pal.list.topLevelItem(i).data(0, Qt.UserRole)
                 for i in range(pal.list.topLevelItemCount())]
        self.assertTrue(names)
        pal.edit.setText("preferences")
        it = pal.list.topLevelItem(0)
        self.assertEqual(it.data(0, Qt.UserRole), "Preferences")
        self.assertIn("File", it.text(1))
        self.assertIn("Ctrl+K", it.text(2))

    def test_disabled_commands_are_not_offered(self):
        pal = CommandPalette(self.w)          # no document open: Save is disabled
        pal.edit.setText("save")
        names = [pal.list.topLevelItem(i).data(0, Qt.UserRole)
                 for i in range(pal.list.topLevelItemCount())]
        self.assertNotIn("Save", names)
        self.assertFalse(self.w.a_save.isEnabled())

    def test_enter_runs_the_command_and_remembers_it(self):
        ran = []
        a = QAction("Zap the &widget", self.w)
        a.triggered.connect(lambda: ran.append(1))
        self.w.addAction(a)
        pal = CommandPalette(self.w)
        pal.show()
        pal.edit.setText("zap wid")
        self.assertEqual(pal.list.topLevelItem(0).data(0, Qt.UserRole), "Zap the widget")
        QTest.keyClick(pal.edit, Qt.Key_Return)
        APP.processEvents()
        self.assertEqual(ran, [1])
        self.assertEqual(pal.chosen, "Zap the widget")
        self.assertEqual(json.loads(self.w.settings.value("palette_recent")), ["Zap the widget"])
        # next time, with nothing typed, it is first
        pal2 = CommandPalette(self.w)
        self.assertEqual(pal2.list.topLevelItem(0).data(0, Qt.UserRole), "Zap the widget")

    def test_arrow_keys_move_the_selection(self):
        pal = CommandPalette(self.w)
        pal.show()
        pal.edit.setText("page")
        self.assertGreater(pal.list.topLevelItemCount(), 2)
        QTest.keyClick(pal.edit, Qt.Key_Down)
        self.assertEqual(pal.list.indexOfTopLevelItem(pal.list.currentItem()), 1)
        QTest.keyClick(pal.edit, Qt.Key_Up)
        self.assertEqual(pal.list.indexOfTopLevelItem(pal.list.currentItem()), 0)
        QTest.keyClick(pal.edit, Qt.Key_Up)
        self.assertEqual(pal.list.indexOfTopLevelItem(pal.list.currentItem()), 0)

    def test_window_has_the_command(self):
        self.assertEqual(self.w.a_palette.shortcut().toString(), "Ctrl+Shift+P")
        self.assertIn("Command palette", self.w._shortcut_actions())


if __name__ == "__main__":
    unittest.main()
