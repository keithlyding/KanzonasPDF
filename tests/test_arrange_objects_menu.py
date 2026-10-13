"""Arrange > Order (Bring to front...) stays available for the page's own objects selected
with Edit objects after an edit: an edit clears the selection and reselects the objects, and
the menus must hear about it (before, the buttons grayed out after one use).

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_arrange_objects_menu
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf as F  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas.main_window import MainWindow  # noqa: E402


class ArrangeObjectsMenu(unittest.TestCase):
    def test_order_buttons_stay_enabled_after_edits(self):
        d = F.open()
        p = d.new_page()
        p.draw_rect(F.Rect(100, 100, 200, 200), color=(1, 0, 0), fill=(0, 0, 1))
        p.draw_rect(F.Rect(150, 150, 250, 250), color=(0, 1, 0), fill=(1, 1, 0))
        path = os.path.join(tempfile.mkdtemp(), "z.pdf")
        d.save(path)
        w = MainWindow()
        self.addCleanup(w.deleteLater)
        w.open_file(path)
        v = w.view()
        self.addCleanup(lambda: setattr(v, "dirty", False))
        w.tool_actions["editobjects"].trigger()
        v.select_objects(0, [v.content_objects(0).items[0]])
        front = w.arrange_actions["z_front"]
        self.assertTrue(front.isEnabled())
        front.trigger()                                    # Bring to front
        self.assertIsNotNone(v.obj_sel)
        self.assertTrue(front.isEnabled())                 # was grayed out here
        r = v.selected_objects_rect()
        v.move_objects(r + (10, 10, 10, 10))               # a move reselects the same way
        self.assertIsNotNone(v.obj_sel)
        self.assertTrue(front.isEnabled())
        w.arrange_actions["z_back"].trigger()
        self.assertTrue(w.arrange_actions["z_back"].isEnabled())


if __name__ == "__main__":
    unittest.main()
