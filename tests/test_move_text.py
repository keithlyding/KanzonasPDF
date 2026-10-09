"""Edit text: press on a line and drag to move it; a plain click still opens it for typing.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_move_text
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf as F  # noqa: E402
from PySide6.QtCore import QEvent, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QMouseEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas.document_view import DocumentView  # noqa: E402


class MoveText(unittest.TestCase):
    def view(self):
        d = F.open()
        d.new_page().insert_text((72, 100), "Move me please", fontsize=14)
        p = os.path.join(tempfile.mkdtemp(), "m.pdf")
        d.save(p)
        v = DocumentView(p)
        v.resize(900, 1100)
        v.show()
        APP.processEvents()
        v.tool = "edittext"
        self.addCleanup(v.close_doc)
        return v

    def mouse(self, pw, kind, pos):
        btn = Qt.LeftButton
        ev = QMouseEvent(kind, pos, pw.mapToGlobal(pos), btn,
                         btn if kind != QEvent.MouseButtonRelease else Qt.NoButton, Qt.NoModifier)
        {QEvent.MouseButtonPress: pw.mousePressEvent, QEvent.MouseMove: pw.mouseMoveEvent,
         QEvent.MouseButtonRelease: pw.mouseReleaseEvent}[kind](ev)

    def test_drag_moves_the_line(self):
        v = self.view()
        pw = v.pages[0]
        s = pw.to_screen_pt(F.Point(90, 96))
        before = v.doc[0].search_for("Move me please")[0]
        self.mouse(pw, QEvent.MouseButtonPress, s)
        for i in range(1, 6):
            self.mouse(pw, QEvent.MouseMove, s + QPointF(i * 20, i * 10))
        self.mouse(pw, QEvent.MouseButtonRelease, s + QPointF(100, 50))
        after = v.doc[0].search_for("Move me please")[0]
        self.assertAlmostEqual(after.x0 - before.x0, 100 / v.zoom, delta=1.5)
        self.assertAlmostEqual(after.y0 - before.y0, 50 / v.zoom, delta=1.5)
        self.assertIsNone(v._inline)

    def test_click_opens_the_line_for_typing(self):
        v = self.view()
        pw = v.pages[0]
        s = pw.to_screen_pt(F.Point(80, 96))
        self.mouse(pw, QEvent.MouseButtonPress, s)
        self.mouse(pw, QEvent.MouseButtonRelease, s)
        self.assertIsNotNone(v._inline)


if __name__ == "__main__":
    unittest.main()
