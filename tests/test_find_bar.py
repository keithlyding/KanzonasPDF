"""Find: the count beside the Find box ("3 of 120", "120+" while still searching), up / down
arrows, Shift+Enter for the previous match, and in whole-page view the match's page is
brought in front, centered.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_find_bar
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf as F  # noqa: E402
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas.document_view import DocumentView  # noqa: E402
from kanzonas.main_window import MainWindow  # noqa: E402
from kanzonas.page_widget import HIT_FRAME_MIN, hit_frame  # noqa: E402


def three_pages():
    """hit on page 1 twice and on page 3 once (nothing on page 2)."""
    d = F.open()
    p = d.new_page()
    p.insert_text((72, 100), "first hit here")
    p.insert_text((72, 300), "second hit here")
    d.new_page().insert_text((72, 100), "nothing on this page")
    d.new_page().insert_text((72, 500), "third hit here")
    path = os.path.join(tempfile.mkdtemp(), "find.pdf")
    d.save(path)
    return path


def settle(v):
    for _ in range(30):
        APP.processEvents()
        if not v._search_todo:
            break


class FindView(unittest.TestCase):
    def view(self):
        v = DocumentView(three_pages())
        v.resize(700, 500)
        v.show()
        APP.processEvents()
        self.addCleanup(v.close_doc)
        return v

    def test_position_count_and_direction(self):
        v = self.view()
        got = []
        v.searchChanged.connect(lambda n, t, s: got.append((n, t, s)))
        v.find("hit")
        settle(v)
        self.assertEqual(v.search_position(), (1, 3, False))
        self.assertEqual(got[-1], (1, 3, False))
        v.find("hit")                                    # next
        self.assertEqual(v.search_position()[:2], (2, 3))
        v.find("hit", backwards=True)                    # up
        self.assertEqual(v.search_position()[:2], (1, 3))
        v.find("hit", backwards=True)                    # wraps to the last
        self.assertEqual(v.search_position()[:2], (3, 3))
        self.assertEqual(v.current_hit()[0], 2)
        v.clear_search()
        self.assertEqual(got[-1], (0, 0, False))
        self.assertEqual(v.search_position(), (0, 0, False))
        v.find("zzz")
        settle(v)
        self.assertEqual(v.search_position(), (0, 0, False))
        self.assertEqual(v.search_text(), "zzz")        # a search with no matches

    def test_whole_page_view_centers_the_matched_page(self):
        v = self.view()
        v.fit_page()
        APP.processEvents()
        v.find("third")
        settle(v)
        self.assertEqual(v.current_hit()[0], 2)
        w = v.pages[2]
        want = int(w.y() - (v.viewport().height() - w.height()) / 2)
        self.assertEqual(v.verticalScrollBar().value(), want)
        self.assertEqual(v.current_page(), 2)
        # not in whole-page view: the match itself is scrolled into view (as before)
        v.set_zoom(2.0)
        v.goto_page(0)
        v.find("third")
        settle(v)
        r = w.to_screen(v.search_hits[2][0])
        top = w.y() + r.y()
        bar = v.verticalScrollBar()
        self.assertTrue(bar.value() < top < bar.value() + v.viewport().height())

    def test_current_match_gets_a_frame_you_can_see_when_zoomed_out(self):
        from PySide6.QtCore import QRectF
        small = hit_frame(QRectF(100, 100, 6, 3))        # tiny text at a low zoom
        self.assertEqual((small.width(), small.height()), HIT_FRAME_MIN)
        self.assertEqual(small.center(), QRectF(100, 100, 6, 3).center())
        big = hit_frame(QRectF(100, 100, 200, 40))
        self.assertEqual((big.width(), big.height()), (206, 46))
        v = self.view()
        v.set_zoom(0.2)
        v.find("third")
        settle(v)
        w = v.pages[2]
        sr = w.to_screen(v.search_hits[2][0])
        self.assertLess(sr.height(), HIT_FRAME_MIN[1])  # the text itself is tiny here
        img = w.grab().toImage()
        frame = hit_frame(sr)
        x, y = int(frame.center().x()), int(frame.top())
        orange = [img.pixelColor(x, y + dy) for dy in range(-2, 3)]
        self.assertTrue(any(c.red() > 200 and c.green() < 150 and c.blue() < 80 for c in orange),
                        [c.name() for c in orange])


class FindBar(unittest.TestCase):
    def window(self):
        w = MainWindow()
        self.addCleanup(w.deleteLater)
        w.open_file(three_pages())
        v = w.view()
        self.addCleanup(lambda: setattr(v, "dirty", False))
        return w, v

    def test_count_arrows_and_shift_enter(self):
        w, v = self.window()
        self.assertFalse(w.find_count.isVisibleTo(w))
        w.search.setText("hit")
        QTest.keyClick(w.search, Qt.Key_Return)
        settle(v)
        w._show_find_count(*v.search_position())
        self.assertEqual(w.find_count.text(), "1 of 3")
        w.find_next_btn.click()
        self.assertEqual(w.find_count.text(), "2 of 3")
        w.find_prev_btn.click()
        self.assertEqual(w.find_count.text(), "1 of 3")
        QTest.keyClick(w.search, Qt.Key_Return, Qt.ShiftModifier)
        self.assertEqual(w.find_count.text(), "3 of 3")
        self.assertTrue(w.find_next_btn.isEnabled())
        w.search.setText("zzz")
        QTest.keyClick(w.search, Qt.Key_Return)
        settle(v)
        w._show_find_count(*v.search_position())
        self.assertEqual(w.find_count.text(), "No matches")
        self.assertFalse(w.find_next_btn.isEnabled())
        w.search.clear()
        self.assertEqual(w.find_count.text(), "")

    def test_box_count_and_arrows_stay_together_in_both_layouts(self):
        w, v = self.window()
        for ribbon in (True, False, True):
            w.a_ribbon.setChecked(ribbon)
            w._apply_ui_mode()
            self.assertIs(w.search.parentWidget(), w.find_group)
            self.assertIs(w.find_next_btn.parentWidget(), w.find_group)
            holder = w.find_group.parentWidget()
            self.assertIs(holder, w.ribbon_right if ribbon else w.main_tb)


if __name__ == "__main__":
    unittest.main()
