"""Split view in 1.12 (the owner, 11 Nov, from the Bluebeam comparison: Revu's split views
and Sync): side by side or top and bottom (remembered), any open document in the second view
(or the one in front), and Sync by page number or by the pages in view; a second view whose
document closes shows the one in front.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_split_sync
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import paths  # noqa: E402
from kanzonas.main_window import MainWindow  # noqa: E402
from kanzonas.split_view import go_to_anchor, sync_anchor  # noqa: E402


def pump(n=6):
    for _ in range(n):
        APP.processEvents()


def make(folder, name, n, size=(612, 792)):
    d = pymupdf.open()
    for i in range(n):
        d.new_page(width=size[0], height=size[1]).insert_text((72, 72), "%s %d" % (name, i + 1))
    path = os.path.join(folder, name + ".pdf")
    d.save(path)
    return path


class Split(unittest.TestCase):
    def setUp(self):
        s = paths.settings()
        before = s.value("split_side")
        self.addCleanup(lambda: s.setValue("split_side", before) if before is not None
                        else s.remove("split_side"))
        s.remove("split_side")
        folder = tempfile.mkdtemp()
        self.a = make(folder, "plans", 6)
        self.b = make(folder, "details", 8, (1224, 792))
        self.w = w = MainWindow()
        w.resize(1400, 900)
        w.show()
        pump()
        w.open_file(self.a)
        w.open_file(self.b)
        pump()
        self.addCleanup(self.close)

    def close(self):
        self.w._close_confirmed = True
        self.w.close()
        pump()

    def split(self, on=True):
        self.w.a_split.setChecked(on)
        self.w._toggle_split()
        pump()
        return self.w.split_dock

    def views(self):
        return self.w._views()

    def test_side_by_side_remembered(self):
        pane = self.split()
        self.assertTrue(pane.isVisible())
        self.assertIs(self.w.centralWidget(), self.w.central_split)
        self.assertEqual(self.w.central_split.orientation(), Qt.Vertical)
        pane.side.setChecked(True)
        pump()
        self.assertEqual(self.w.central_split.orientation(), Qt.Horizontal)
        sizes = self.w.central_split.sizes()
        self.assertLess(abs(sizes[0] - sizes[1]), 20)          # half and half
        self.assertEqual(paths.settings().value("split_side"), "true")
        self.split(False)
        self.assertFalse(pane.isVisible())
        self.assertIsNone(self.w._split_view)

    def test_any_open_document_and_back_to_the_one_in_front(self):
        pane = self.split()
        plans, details = self.views()
        self.assertIs(self.w._split_view._source, self.w.view())        # (the one in front)
        at = pane.doc_box.findData(id(plans))
        self.assertGreater(at, 0)
        pane.doc_box.setCurrentIndex(at)
        pane.doc_box.activated.emit(at)
        pump()
        self.assertIs(self.w._split_view._source, plans)
        self.w.tabs.setCurrentWidget(details)
        pump()
        self.assertIs(self.w._split_view._source, plans)                 # (stays)
        # the document it shows closes: it shows the one in front
        self.w.close_tab(self.w.tabs.indexOf(plans))
        pump()
        self.assertTrue(pane.isVisible())
        self.assertIs(self.w._split_view._source, self.w.view())
        self.assertEqual(pane.chosen(), "front")

    def test_sync_by_page_number(self):
        pane = self.split()
        plans, details = self.views()
        self.w.tabs.setCurrentWidget(details)
        pump()
        pane.doc_box.setCurrentIndex(pane.doc_box.findData(id(plans)))
        pane.doc_box.activated.emit(pane.doc_box.currentIndex())
        pump()
        sv = self.w._split_view
        pane.sync.setChecked(True)
        pump()
        self.assertTrue(pane.linked())
        go_to_anchor(details, 3, 0.25, 0.6, 1.5)
        pump()
        page, fx, fy, zoom = sync_anchor(sv)
        self.assertEqual(page, 3)
        self.assertAlmostEqual(zoom, details.zoom, places=3)
        self.assertAlmostEqual(fy, 0.6, delta=0.03)
        self.assertAlmostEqual(fx, 0.25, delta=0.03)
        # the other way: the second view moves the main one (once the echoes of being moved
        # by Sync are past, as by the time a person scrolls it)
        QTest.qWait(200)
        go_to_anchor(sv, 1, 0.5, 0.2)
        pump()
        self.assertEqual(sync_anchor(details)[0], 1)
        pane.sync.setChecked(False)
        pump()
        self.assertFalse(pane.linked())
        go_to_anchor(details, 5, 0.5, 0.5)
        pump()
        self.assertEqual(sync_anchor(sv)[0], 1)                 # (no longer follows)

    def test_sync_by_the_pages_in_view(self):
        pane = self.split()
        plans, details = self.views()
        self.w.tabs.setCurrentWidget(details)
        pump()
        pane.doc_box.setCurrentIndex(pane.doc_box.findData(id(plans)))
        pane.doc_box.activated.emit(pane.doc_box.currentIndex())
        pump()
        sv = self.w._split_view
        go_to_anchor(details, 0, 0.5, 0.5, 1.0)
        go_to_anchor(sv, 2, 0.5, 0.5, 2.0)
        pump()
        pane.sync_mode.setCurrentIndex(pane.sync_mode.findData("view"))
        pane.sync.setChecked(True)
        pump()
        go_to_anchor(details, 1, 0.5, 0.3, 1.25)
        pump()
        page, _fx, fy, zoom = sync_anchor(sv)
        self.assertEqual(page, 3)                               # (paired two pages on)
        self.assertAlmostEqual(zoom, 2.5, places=2)             # (twice the zoom, as paired)
        self.assertAlmostEqual(fy, 0.3, delta=0.03)

    def test_anchor_round_trip(self):
        v = self.w.view()
        go_to_anchor(v, 4, 0.3, 0.7, 2.0)
        pump()
        page, fx, fy, zoom = sync_anchor(v)
        self.assertEqual(page, 4)
        self.assertAlmostEqual(fx, 0.3, delta=0.02)
        self.assertAlmostEqual(fy, 0.7, delta=0.02)
        self.assertAlmostEqual(zoom, 2.0, places=3)


if __name__ == "__main__":
    unittest.main()
