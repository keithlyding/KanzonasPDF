"""Switching the mouse mode keeps the page where it is on the screen (from using 1.7.1:
zoomed out past full page, going from the Select mouse to the Hand mouse put the page at the
far left). Hand and CAD modes open a canvas about a window wide around the pages (free page
movement); Standard doesn't: the margin changes, the page must not move.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_mouse_mode_keeps_view
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402
from PySide6.QtCore import QPoint  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import main_window, mouse_modes  # noqa: E402


def pdf(pages=4):
    d = pymupdf.open()
    for _ in range(pages):
        d.new_page(width=612, height=792).draw_line((100, 100), (500, 700))
    path = os.path.join(tempfile.mkdtemp(), "pages.pdf")
    d.save(path)
    return path


class KeepsPlace(unittest.TestCase):
    def setUp(self):
        w = self.w = main_window.MainWindow()
        old = {k: w.settings.value(k) for k in ("mouse_mode", "mouse_before_cad")}

        def back():
            for k, val in old.items():
                w.settings.setValue(k, val) if val is not None else w.settings.remove(k)
            mouse_modes.apply(w.settings)
        self.addCleanup(back)
        self.addCleanup(lambda: [setattr(x, "_close_confirmed", True) or x.close()
                                 for x in main_window.windows()])
        w.resize(1200, 900)
        w.show()
        w.set_mouse_mode("standard")
        w.open_file(pdf())
        APP.processEvents()
        self.v = w.view()
        self.addCleanup(lambda: setattr(self.v, "dirty", False))

    def where(self, index=None):
        """(page number, its top left corner in the window): the page shown, or index."""
        v = self.v
        index = v.current_page() if index is None else index
        return index, v.pages[index].mapTo(v.viewport(), QPoint(0, 0))

    def switch(self, mode):
        before = self.where()
        self.w.set_mouse_mode(mode)
        APP.processEvents()
        # (the same page: CAD mode's command line makes the window shorter, which can change
        # which page counts as the one shown)
        after = self.where(before[0])
        self.assertLessEqual(abs(after[1].x() - before[1].x()), 2, (mode, before, after))
        self.assertLessEqual(abs(after[1].y() - before[1].y()), 2, (mode, before, after))

    def test_zoomed_out_select_to_hand_keeps_the_page_in_place(self):
        v = self.v
        v.set_zoom(0.3)                     # (narrower than the window: centered)
        APP.processEvents()
        v.verticalScrollBar().setValue(v.pages[1].y() + 20)
        APP.processEvents()
        self.assertGreater(self.where()[1].x(), 100)     # (centered, not at the left)
        self.switch("hand")
        self.switch("cad")

    def test_zoomed_in_too(self):
        v = self.v
        v.set_zoom(2.0)
        APP.processEvents()
        v.horizontalScrollBar().setValue(v.horizontalScrollBar().maximum() // 3)
        v.verticalScrollBar().setValue(v.pages[2].y() + 300)
        APP.processEvents()
        self.switch("hand")
        self.switch("standard")


if __name__ == "__main__":
    unittest.main()
