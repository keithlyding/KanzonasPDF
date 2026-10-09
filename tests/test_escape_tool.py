"""Escape puts a picked tool down: back to the Hand or Select tool used last, then Select.

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
from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])


class EscapeTool(unittest.TestCase):
    def test_escape_returns_to_the_last_hand_or_select_tool(self):
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
        v = w.view()

        def esc():
            v.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier))
        w.set_tool("hand")
        w.set_tool("stamp")
        v.pages[0]._ghost = v.pages[0].rect().center()      # stamp preview under the mouse
        esc()
        self.assertEqual(w.tool, "hand")
        self.assertIsNone(v.pages[0]._ghost)
        esc()
        self.assertEqual(w.tool, "select")
        w.set_tool("rect")
        esc()
        self.assertEqual(w.tool, "select")
        w.close_tab(w.tabs.currentIndex())
        w.deleteLater()


if __name__ == "__main__":
    unittest.main()
