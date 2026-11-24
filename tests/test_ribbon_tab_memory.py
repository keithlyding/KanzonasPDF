"""The ribbon tab open last is opened again at start-up, remembered by name: 1.17 added the
Drawing tab after Markup, and remembered by its place (as 1.16 did), every tab after Markup
opened the one before it after updating.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_ribbon_tab_memory
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import main_window as MW, paths  # noqa: E402


class RibbonTab(unittest.TestCase):
    def setUp(self):
        self.s = paths.settings()
        self.addCleanup(lambda: [self.s.remove(k) for k in ("ribbon_tab", "ribbon_tab_name")])
        for k in ("ribbon_tab", "ribbon_tab_name"):
            self.s.remove(k)

    def window(self):
        w = MW.MainWindow()
        self.addCleanup(lambda: (setattr(w, "_close_confirmed", True), w.close()))
        return w

    def test_the_keys_are_the_tabs_in_order(self):
        r = self.window().ribbon
        self.assertEqual(r.count(), len(MW.RIBBON_TABS))
        self.assertEqual([r.tabText(i).replace("&", "").lower() for i in range(r.count())],
                         list(MW.RIBBON_TABS))

    def test_kept_by_name(self):
        w = self.window()
        w.ribbon.setCurrentIndex(MW.RIBBON_TABS.index("view"))
        self.assertEqual(self.s.value("ribbon_tab_name"), "view")
        self.assertEqual(self.window().ribbon.currentIndex(), MW.RIBBON_TABS.index("view"))

    def test_the_place_1_16_kept_opens_the_same_tab(self):
        # (1.16's tabs: Home, Markup, Measure, Arrange, Review...; Arrange was the fourth)
        self.s.setValue("ribbon_tab", 3)
        self.assertEqual(self.window().ribbon.currentIndex(), MW.RIBBON_TABS.index("arrange"))
        self.s.setValue("ribbon_tab", 1)
        self.assertEqual(MW.ribbon_tab_to_open(self.s, len(MW.RIBBON_TABS)),
                         MW.RIBBON_TABS.index("markup"))
        self.s.setValue("ribbon_tab", 99)
        self.assertEqual(MW.ribbon_tab_to_open(self.s, len(MW.RIBBON_TABS)), 0)


if __name__ == "__main__":
    unittest.main()
