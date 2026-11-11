"""A markup just drawn is selected, with its tool still picked (the owner, 10 Nov: after
drawing a rectangle, Properties' opacity changed the Rectangle tool's style for the next one,
not the rectangle drawn, and seemed to do nothing). Properties then changes that markup and
leaves the tool's style as it was; the next drag draws another one; right-click > Set as
Default makes a markup's style its tool's default; the panel's title says which one changes.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_drawn_markup_selected
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

from kanzonas import annotations as A  # noqa: E402
from kanzonas.main_window import MainWindow  # noqa: E402


def pump(n=5):
    for _ in range(n):
        APP.processEvents()


class Drawn(unittest.TestCase):
    def setUp(self):
        for tool in ("rect", "ellipse", "arrow"):
            A.reset_tool_props(tool)
        self.addCleanup(lambda: [A.reset_tool_props(t) for t in ("rect", "ellipse", "arrow")])
        d = pymupdf.open()
        d.new_page()
        path = os.path.join(tempfile.mkdtemp(), "drawn.pdf")
        d.save(path)
        self.w = w = MainWindow()
        w.resize(1300, 900)
        w.show()
        pump()
        w.set_mouse_mode("standard")        # (not CAD mode a test before may have left)
        w.open_file(path)
        pump()
        self.v = w.view()
        self.addCleanup(self.close)

    def close(self):
        self.w._close_confirmed = True
        self.w.close()
        pump()

    def drag(self, a, b):
        pw = self.v.pages[0]

        def send(kind, pt, buttons):
            pos = QPointF(pw.to_screen_pt(pymupdf.Point(pt)))
            ev = QMouseEvent(kind, pos, pw.mapToGlobal(pos), Qt.LeftButton, buttons,
                             Qt.NoModifier)
            {QEvent.MouseButtonPress: pw.mousePressEvent, QEvent.MouseMove: pw.mouseMoveEvent,
             QEvent.MouseButtonRelease: pw.mouseReleaseEvent}[kind](ev)
            pump(2)
        send(QEvent.MouseButtonPress, a, Qt.LeftButton)
        send(QEvent.MouseMove, ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2), Qt.LeftButton)
        send(QEvent.MouseMove, b, Qt.LeftButton)
        send(QEvent.MouseButtonRelease, b, Qt.NoButton)

    def rects(self):
        return [a for a in self.v.doc[0].annots() if a.type[0] == pymupdf.PDF_ANNOT_SQUARE]

    def test_drawn_is_selected_and_properties_change_it(self):
        self.w.set_tool("rect")
        pump()
        self.drag((100, 100), (200, 180))
        self.assertEqual(len(self.rects()), 1)
        x = self.rects()[0].xref
        self.assertEqual(self.v.selection, (0, x))
        self.assertEqual(self.w.tool, "rect")                   # the tool stays picked
        props = self.w.props
        self.assertIn("Rectangle", props.title.text())
        self.assertTrue(props.title.text().startswith("Selected"))
        props.opacity.setValue(40)            # (as a click on its track or a key)
        pump()
        self.assertAlmostEqual(self.rects()[0].opacity, 0.4, places=2)
        x = self.rects()[0].xref                # (restyled: written anew)
        self.assertEqual(float(A.tool_props("rect").get("opacity", 1)), 1.0)
        # the next drag draws another one, which is then the one selected
        self.drag((300, 300), (400, 380))
        self.assertEqual(len(self.rects()), 2)
        second = next(a.xref for a in self.rects() if a.xref != x)
        self.assertEqual(self.v.selection, (0, second))
        opac = {a.xref: a.opacity for a in self.rects()}
        self.assertIn(opac[second], (None, -1, 1, 1.0))      # the tool's style: solid

    def test_set_as_default(self):
        self.w.set_tool("rect")
        pump()
        self.drag((100, 100), (200, 180))
        self.w.props.opacity.setValue(40)
        pump()
        self.assertEqual(self.v.default_tool_of_selected(), "rect")
        self.assertTrue(self.v.set_selected_as_default())
        self.assertAlmostEqual(float(A.tool_props("rect")["opacity"]), 0.4, places=2)
        self.v.clear_selection()
        pump()
        self.assertIn("default style", self.w.props.title.text())
        self.assertAlmostEqual(self.w.props.opacity.value(), 40, delta=1)
        self.drag((300, 300), (400, 380))
        newest = max(self.rects(), key=lambda a: a.xref)
        self.assertAlmostEqual(newest.opacity, 0.4, places=2)

    def test_undo_takes_the_drawn_markup_away_and_its_selection(self):
        self.w.set_tool("ellipse")
        pump()
        self.drag((100, 100), (200, 180))
        self.assertIsNotNone(self.v.selection)
        self.v.undo()
        pump()
        self.assertEqual(list(self.v.doc[0].annots()), [])
        self.assertIsNone(self.v.selection)


if __name__ == "__main__":
    unittest.main()
