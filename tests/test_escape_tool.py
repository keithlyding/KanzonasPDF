"""Escape puts a picked tool down and goes back to the default tool (Preferences > Start-up:
Hand or Select), from any tool, and even when a toolbar button has the keyboard focus.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_escape_tool
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf as F  # noqa: E402
from PySide6.QtCore import QEvent, Qt  # noqa: E402
from PySide6.QtGui import QKeyEvent  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QToolButton  # noqa: E402

APP = QApplication.instance() or QApplication([])


class EscapeTool(unittest.TestCase):
    def window(self):
        tmp = tempfile.mkdtemp()
        os.environ["HOME"] = tmp
        from kanzonas.main_window import MainWindow
        p = os.path.join(tmp, "a.pdf")
        d = F.open()
        d.new_page()
        d.save(p)
        w = MainWindow()
        w.show()
        w.open_file(p)
        APP.processEvents()
        self.addCleanup(w.deleteLater)
        self.addCleanup(lambda: w.close_tab(w.tabs.currentIndex()))
        return w

    def test_escape_returns_to_the_default_tool_from_any_tool(self):
        w = self.window()
        v = w.view()

        def esc():
            v.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier))
        w.settings.setValue("mouse_mode", "hand")
        w.set_tool("stamp")
        v.pages[0]._ghost = v.pages[0].rect().center()      # stamp preview under the mouse
        esc()
        self.assertEqual(w.tool, "hand")
        self.assertIsNone(v.pages[0]._ghost)
        w.set_tool("select")
        esc()
        self.assertEqual(w.tool, "hand")                     # not "the last basic tool"
        esc()
        self.assertEqual(w.tool, "hand")
        w.settings.setValue("mouse_mode", "standard")
        for tool in ("rect", "crop", "hand", "m_length"):
            w.set_tool(tool)
            esc()
            self.assertEqual(w.tool, "select", tool)

    def test_escape_works_when_a_toolbar_button_has_focus(self):
        w = self.window()
        w.settings.setValue("mouse_mode", "hand")
        w.set_tool("crop")
        btn = QToolButton(w)
        btn.show()
        btn.setFocus()
        APP.processEvents()
        self.assertIs(QApplication.focusWidget(), btn)
        QTest.keyClick(btn, Qt.Key_Escape)
        self.assertEqual(w.tool, "hand")


if __name__ == "__main__":
    unittest.main()
