"""Pages panel: a page dragged to a new place scrolls the thumbnails when the pointer nears the
top or bottom, faster the nearer it gets, and keeps scrolling with the pointer above or below
the list (the owner, 11 Nov: "I need to be able to drag it to a location that is outside of
the scroll visible panel"); nothing scrolls when no page is being dragged.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_thumb_drag_scroll
"""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402
from PySide6.QtWidgets import QApplication, QListWidget  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas.main_window import MainWindow, _ThumbList  # noqa: E402


class DragScroll(unittest.TestCase):
    def setUp(self):
        d = pymupdf.open()
        for i in range(60):
            d.new_page().insert_text((72, 72), "Page %d" % (i + 1))
        path = os.path.join(tempfile.mkdtemp(), "long.pdf")
        d.save(path)
        self.w = w = MainWindow()
        w.resize(1200, 800)
        w.show()
        APP.processEvents()
        w.open_file(path)
        for _ in range(5):
            APP.processEvents()
        self.addCleanup(self.close)
        self.t = w.thumbs
        self.bar = self.t.verticalScrollBar()

    def close(self):
        self.w._close_confirmed = True
        self.w.close()
        APP.processEvents()

    def ticks(self, y, n=5):
        with mock.patch.object(self.t, "pointer_y", return_value=y):
            for _ in range(n):
                self.t.scroll_tick()

    def test_the_list_scrolls_while_a_page_is_dragged(self):
        self.assertIsInstance(self.t, _ThumbList)
        self.assertGreater(self.bar.maximum(), 0, "the list needs to scroll")
        h = self.t.viewport().height()
        self.t.dragging = True
        self.ticks(h // 2)                              # the middle: still
        self.assertEqual(self.bar.value(), 0)
        self.ticks(h - 4)                               # at the bottom edge: down
        near = self.bar.value()
        self.assertGreater(near, 0)
        self.ticks(h + 60)                              # below the list: faster
        self.assertGreater(self.bar.value() - near, near)
        top = self.bar.value()
        self.ticks(-60)                                 # above the list: back up
        self.assertLess(self.bar.value(), top)
        self.ticks(-60, 400)
        self.assertEqual(self.bar.value(), 0)           # (stops at the end)

    def test_speed_grows_toward_and_past_the_edge(self):
        h = self.t.viewport().height()
        steps = [self.t.scroll_step(y) for y in (h - 40, h - 20, h - 1, h + 30, h + 400)]
        self.assertEqual(steps, sorted(steps))
        self.assertGreater(steps[0], 0)
        self.assertEqual(steps[-1], _ThumbList.MAX_STEP)
        self.assertEqual(self.t.scroll_step(20), -self.t.scroll_step(h - 20))
        self.assertEqual(self.t.scroll_step(h // 2), 0)

    def test_nothing_scrolls_without_a_drag(self):
        self.t.dragging = False
        self.ticks(self.t.viewport().height() + 60)
        self.assertEqual(self.bar.value(), 0)

    def test_the_drag_turns_it_on_and_off(self):
        seen = {}

        def drag(lst, actions):
            seen["during"] = (lst.dragging, lst.hasAutoScroll(), lst._scroll_timer.isActive())
        with mock.patch.object(QListWidget, "startDrag", drag):
            self.t.startDrag(0)
        self.assertEqual(seen["during"], (True, False, True))
        self.assertFalse(self.t.dragging)
        self.assertTrue(self.t.hasAutoScroll())
        self.assertFalse(self.t._scroll_timer.isActive())


if __name__ == "__main__":
    unittest.main()
