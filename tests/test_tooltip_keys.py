"""Every button's tool tip shows how to reach its command from the keyboard.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_tooltip_keys
"""
import json
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QPoint
from PySide6.QtGui import QAction, QHelpEvent, QKeySequence
from PySide6.QtWidgets import QApplication, QToolButton, QToolTip

from kanzonas.main_window import MainWindow

APP = QApplication.instance() or QApplication([])


class TooltipKeys(unittest.TestCase):
    def setUp(self):
        self.w = MainWindow()
        self.addCleanup(self._close)
        self.w.show()
        APP.processEvents()

    def _close(self):
        self.w.settings.remove("shortcuts")
        self.w.close()
        self.w.deleteLater()
        APP.processEvents()

    def _buttons(self):
        seen = set()
        for b in self.w.findChildren(QToolButton):
            a = b.defaultAction()
            if a is not None and id(a) not in seen:
                seen.add(id(a))
                yield b, a

    def test_every_button_with_a_shortcut_shows_it(self):
        n = 0
        for b, a in self._buttons():
            sc = a.shortcut().toString(QKeySequence.NativeText)
            if sc and b not in (self.w.shapes_btn, self.w.measure_btn):
                n += 1
                self.assertIn(sc, b.toolTip(), a.text())
        self.assertGreater(n, 50)
        # the ones that didn't before 1.8.1
        self.assertEqual(self.w.a_new.toolTip().count("(Ctrl+N)"), 1)
        for name in ("a_thumbs", "a_props", "a_markups"):
            a = getattr(self.w, name, None)
            if a is not None and not a.shortcut().isEmpty():
                self.assertTrue(a.toolTip().endswith(
                    "(%s)" % a.shortcut().toString(QKeySequence.NativeText)), a.toolTip())

    def test_never_twice(self):
        for _ in range(3):
            self.w._refresh_tips()
            self.w._apply_icons()
        for a in self.w.findChildren(QAction):
            sc = a.shortcut().toString(QKeySequence.NativeText)
            if sc:
                self.assertLessEqual(a.toolTip().count("(%s)" % sc), 1, a.toolTip())
        # a tip that names its key itself isn't given it again
        self.assertEqual(self.w.a_night.toolTip().count("F12"), 1)

    def test_custom_shortcut_shows(self):
        a = self.w.tool_actions["rect"]
        names = {n: x for n, x in self.w._shortcut_actions().items() if x is a}
        self.assertTrue(names)
        self.w.settings.setValue("shortcuts", json.dumps({next(iter(names)): "Ctrl+Alt+J"}))
        self.w._apply_saved_shortcuts()
        key = QKeySequence("Ctrl+Alt+J").toString(QKeySequence.NativeText)
        self.assertTrue(a.toolTip().endswith("(%s)" % key), a.toolTip())
        self.assertNotIn("(R)", a.toolTip())

    def test_cad_commands_give_the_letters(self):
        tips = {k: a.toolTip() for k, a in self.w.cad_actions.items()}
        self.assertIn("(type M and press Enter)", tips["move"])
        self.assertIn("(type CO and press Enter)", tips["copy"])
        self.assertIn("(type TR and press Enter)", tips["trim"])

    def test_group_button_names_its_tool_and_key(self):
        b = self.w.shapes_btn
        shown = {}
        orig = QToolTip.showText

        def grab(pos, text, w=None, *args):
            shown["text"] = text
        QToolTip.showText = grab
        self.addCleanup(lambda: setattr(QToolTip, "showText", orig))
        QApplication.sendEvent(b, QHelpEvent(QEvent.ToolTip, QPoint(2, 2), b.mapToGlobal(QPoint(2, 2))))
        face = b.defaultAction()
        key = face.shortcut().toString(QKeySequence.NativeText)
        self.assertIn(key, shown.get("text", ""))
        self.assertIn("Shapes:", shown["text"])
        # after another tool is picked, the tip follows it
        other = self.w.tool_actions["ellipse"]
        b.setDefaultAction(other)
        QApplication.sendEvent(b, QHelpEvent(QEvent.ToolTip, QPoint(2, 2), b.mapToGlobal(QPoint(2, 2))))
        self.assertTrue(shown["text"].startswith(other.toolTip()))
        self.assertIn("Shapes:", shown["text"])


if __name__ == "__main__":
    unittest.main()
