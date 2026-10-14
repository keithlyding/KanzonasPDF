"""0.92.1 polish: Ctrl+wheel zooms around the pointer in the normal mouse mode; the on-page
text editors show black text whatever the theme; double-click selects a word and a third
click its line.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_polish_0921
"""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf as F  # noqa: E402
from PySide6.QtCore import Qt, QPoint, QPointF, QEvent  # noqa: E402
from PySide6.QtGui import QWheelEvent, QMouseEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas.document_view import DocumentView  # noqa: E402
from kanzonas.inline_editor import InlineEditor  # noqa: E402


def pdf(text="hello world\nsecond line here"):
    d = F.open()
    d.new_page().insert_text((72, 100), text, fontsize=14)
    p = os.path.join(tempfile.mkdtemp(), "t.pdf")
    d.save(p)
    return p


class Polish(unittest.TestCase):
    def view(self):
        v = DocumentView(pdf())
        v.resize(800, 600)
        v.show()
        APP.processEvents()
        self.addCleanup(v.close_doc)
        return v

    def test_ctrl_wheel_zooms_around_the_pointer(self):
        v = self.view()
        v.cad_mouse = False
        v.set_zoom(1.0)
        vp = QPoint(300, 200)
        ev = QWheelEvent(QPointF(vp), QPointF(v.viewport().mapToGlobal(vp)), QPoint(0, 0),
                         QPoint(0, 120), Qt.NoButton, Qt.ControlModifier, Qt.NoScrollPhase, False)
        with mock.patch.object(v, "zoom_at", wraps=v.zoom_at) as at:
            v.wheelEvent(ev)
        self.assertEqual(at.call_count, 1)
        self.assertEqual(at.call_args[0][1], vp)
        self.assertAlmostEqual(v.zoom, 1.2, places=3)

    def test_editors_show_black_text_in_any_theme(self):
        v = self.view()
        from PySide6.QtCore import QRectF
        ed = InlineEditor(v.pages[0], QRectF(10, 10, 100, 20), "abc", "sans", 14)
        self.assertIn("color: black", ed.text.styleSheet())
        ed.cancel()

    def test_double_click_selects_a_word_and_a_third_click_the_line(self):
        v = self.view()
        v.set_tool("select")
        pw = v.pages[0]
        units = v._words(0)
        w = next(u for u in units if u[4] == "w")             # the w of "world"
        pt = F.Point((w[0] + w[2]) / 2, (w[1] + w[3]) / 2)
        pos = pw.to_screen_pt(pt)

        def mouse(kind):
            return QMouseEvent(kind, pos, pw.mapToGlobal(pos), Qt.LeftButton, Qt.LeftButton,
                               Qt.NoModifier)
        pw.mousePressEvent(mouse(QEvent.MouseButtonPress))
        pw.mouseReleaseEvent(mouse(QEvent.MouseButtonRelease))
        pw.mouseDoubleClickEvent(mouse(QEvent.MouseButtonDblClick))
        pw.mouseReleaseEvent(mouse(QEvent.MouseButtonRelease))
        self.assertEqual(v.selected_text(), "world")
        pw.mousePressEvent(mouse(QEvent.MouseButtonPress))     # the third click
        pw.mouseReleaseEvent(mouse(QEvent.MouseButtonRelease))
        self.assertEqual(v.selected_text(), "hello world")
        # a double-click away from text selects nothing (and doesn't raise)
        far = pw.to_screen_pt(F.Point(400, 500))
        pw.mouseDoubleClickEvent(QMouseEvent(QEvent.MouseButtonDblClick, far, pw.mapToGlobal(far),
                                             Qt.LeftButton, Qt.LeftButton, Qt.NoModifier))
        self.assertEqual(v.selected_text(), "")


if __name__ == "__main__":
    unittest.main()
