"""The Edit text / Add text box isn't bigger than the text it places (the owner: "the text box is
huge and it's hard to see where the text is actually going to be").

- Text too small to read at the zoom (a drawing sheet zoomed out: 12 pt at 15% is 2.5 px tall)
  is typed enlarged in a box just below its spot, and a true-size preview is drawn where it
  goes; it lands at the spot clicked, wraps at the width the box was given (in true size), and
  a click on a word puts the cursor there. (Before: the box showed it at 6 px at least, with
  its margins many times the text's size, around the spot.)
- Add text's box is as wide as what's typed, growing and shrinking with it (before: 12 letters
  wide from the start, and never narrower).

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_small_text_editing -t .
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QMouseEvent  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import annotations, inline_editor  # noqa: E402
from kanzonas.main_window import MainWindow  # noqa: E402


def pump(n=8):
    for _ in range(n):
        APP.processEvents()


class Fixture(unittest.TestCase):
    ZOOM = 0.15

    def setUp(self):
        for tool in ("addtext", "edittext"):
            annotations.reset_tool_props(tool)
        d = pymupdf.open()
        d.new_page(width=2592, height=1728)             # a 36 x 24 inch sheet
        path = os.path.join(tempfile.mkdtemp(), "sheet.pdf")
        d.save(path)
        self.w = w = MainWindow()
        w.resize(1400, 900)
        w.show()
        pump()
        w.open_file(path)
        pump()
        self.v = w.view()
        self.v.set_zoom(self.ZOOM)
        pump(20)
        self.pw = self.v.pages[0]
        self.spot = pymupdf.Point(300, 300)
        self.at = self.pw.to_screen(pymupdf.Rect(self.spot, self.spot)).topLeft().toPoint()

    def tearDown(self):
        self.w._close_confirmed = True
        self.w.close()
        pump()

    def start_add_text(self):
        self.w.set_tool("addtext")
        pump()
        QTest.mouseClick(self.pw, Qt.LeftButton, Qt.NoModifier, self.at)
        pump()
        return self.v._inline

    def words(self):
        return self.v.doc[0].get_text("words")


class SmallText(Fixture):
    def test_typed_enlarged_below_its_spot_and_lands_at_the_spot(self):
        ed = self.start_add_text()
        self.assertTrue(ed.enlarged())
        QTest.keyClicks(ed.text, "Room 101")
        pump()
        self.assertGreaterEqual(ed.text.font().pixelSize(), inline_editor.READABLE_PX - 1)
        self.assertGreater(ed.y(), self.at.y())                 # below the spot, not over it
        # the preview: the words drawn at their true size at the spot
        img = self.pw.grab().toImage()
        o = ed.preview_origin().toPoint()
        dark = sum(1 for x in range(o.x(), o.x() + 12) for y in range(o.y(), o.y() + 4)
                   if img.pixelColor(x, y).lightness() < 160)
        self.assertGreater(dark, 2)
        QTest.keyClick(ed.text, Qt.Key_Return)
        pump()
        first = self.words()[0]
        self.assertEqual(first[4], "Room")
        self.assertAlmostEqual(first[0], self.spot.x, delta=2)  # where it was clicked
        self.assertLess(first[3] - first[1], 20)                # 12 pt, not enlarged

    def test_a_narrowed_box_wraps_at_its_true_width(self):
        ed = self.start_add_text()
        QTest.keyClicks(ed.text, "one two three four five six seven eight")
        pump()
        # drag the right handle to about half the width
        r = ed._handles()["mr"].center()
        QTest.mousePress(ed, Qt.LeftButton, Qt.NoModifier, r)
        to = r - QPoint(ed.width() // 2, 0)
        QApplication.sendEvent(ed, QMouseEvent(QEvent.MouseMove, QPointF(to),
                                               QPointF(ed.mapToGlobal(to)), Qt.NoButton,
                                               Qt.LeftButton, Qt.NoModifier))
        QTest.mouseRelease(ed, Qt.LeftButton, Qt.NoModifier, to)
        pump()
        shown_lines = ed.text.document().documentLayout().blockBoundingRect(
            ed.text.document().begin()).height() / ed.text.fontMetrics().lineSpacing()
        QTest.mouseClick(self.pw, Qt.LeftButton, Qt.NoModifier, self.at + QPoint(0, 300))
        pump()
        rows = sorted({round(wd[3]) for wd in self.words()})
        self.assertGreater(len(rows), 1)                        # it wraps on the page...
        self.assertAlmostEqual(len(rows), round(shown_lines), delta=1)     # ...as in the box
        right = max(wd[2] for wd in self.words())
        self.assertLess(right - self.spot.x, 0.75 * pymupdf.get_text_length(
            "one two three four five six seven eight", fontsize=12))

    def test_a_click_on_a_word_puts_the_cursor_there_and_nothing_moves(self):
        ed = self.start_add_text()
        QTest.keyClicks(ed.text, "Room 101")
        QTest.keyClick(ed.text, Qt.Key_Return)
        pump()
        before = self.words()
        self.w.set_tool("edittext")
        pump()
        wd = next(x for x in before if x[4] == "Room")
        r = pymupdf.Rect(wd[:4])
        click = self.pw.to_screen(pymupdf.Rect(r.x0 + 0.2, r.y0, r.x0 + 0.2, r.y1))
        QTest.mouseClick(self.pw, Qt.LeftButton, Qt.NoModifier, click.center().toPoint())
        pump()
        ed = self.v._inline
        self.assertTrue(ed.enlarged())
        self.assertLessEqual(ed.text.textCursor().position(), 1)     # at "Room", not "101"
        QTest.keyClick(ed.text, Qt.Key_Return)                     # no change
        pump()
        after = self.words()
        self.assertEqual([x[4] for x in after], [x[4] for x in before])
        for a, b in zip(after, before):
            self.assertAlmostEqual(a[0], b[0], delta=0.5)
            self.assertAlmostEqual(a[3], b[3], delta=0.5)


class NormalZoom(Fixture):
    ZOOM = 1.5

    def test_not_enlarged_at_a_readable_zoom(self):
        ed = self.start_add_text()
        self.assertFalse(ed.enlarged())

    def test_add_text_box_is_as_wide_as_the_text(self):
        ed = self.start_add_text()
        empty = ed.width()
        self.assertLess(empty, 60)                      # (was 12 letters wide: ~260 px)
        QTest.keyClicks(ed.text, "Room 101")
        pump()
        text_px = ed.text.fontMetrics().horizontalAdvance("Room 101")
        self.assertLessEqual(ed.width(), text_px + 2 * inline_editor.MARGIN + 16)
        wide = ed.width()
        for _ in range(4):
            QTest.keyClick(ed.text, Qt.Key_Backspace)
        pump()
        self.assertLess(ed.width(), wide)               # shrinks with the text


if __name__ == "__main__":
    unittest.main()
