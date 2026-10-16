"""The panels (Pages, Properties, Tool chest, Markups list) come back as they were when
KanzonasPDF was last closed; the Split view always starts closed."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import paths  # noqa: E402
from kanzonas.main_window import MainWindow  # noqa: E402


class PanelLayout(unittest.TestCase):
    def setUp(self):
        self._forget_layout()           # the settings store is shared by the whole test run

    def tearDown(self):
        self._forget_layout()           # leave no remembered layout for the next test module

    @staticmethod
    def _forget_layout():
        s = paths.settings()
        for key in ("window_state", "geometry", "ui_mode"):
            s.remove(key)
        s.sync()

    def window(self):
        w = MainWindow()
        w.resize(1200, 800)
        w.show()
        APP.processEvents()
        return w

    def close(self, w):
        w._close_confirmed = True
        w.close()
        APP.processEvents()

    def test_default_layout_without_a_saved_one(self):
        w = self.window()
        self.assertTrue(w.dock.isVisible())
        self.assertTrue(w.props_dock.isVisible())
        self.assertFalse(w.markups_dock.isVisible())
        self.assertFalse(w.split_dock.isVisible())
        self.close(w)

    def test_panels_come_back_as_they_were(self):
        w = self.window()
        w.props_dock.hide()
        w.dock.hide()
        w.markups_dock.show()
        w.chest_dock.show()
        w.split_dock.show()
        APP.processEvents()
        self.close(w)
        self.assertIsNotNone(w.settings.value("window_state"))

        w2 = self.window()
        self.addCleanup(self.close, w2)
        self.assertFalse(w2.props_dock.isVisible(), "Properties stays closed")
        self.assertFalse(w2.dock.isVisible(), "Pages stays closed")
        self.assertTrue(w2.markups_dock.isVisible(), "Markups list comes back")
        self.assertTrue(w2.chest_dock.isVisible(), "Tool chest comes back")
        self.assertFalse(w2.split_dock.isVisible(), "Split view always starts closed")
        # the menu check marks agree with the panels
        self.assertFalse(w2.a_props.isChecked())
        self.assertFalse(w2.a_sidebar.isChecked())
        self.assertTrue(w2.a_markups.isChecked())

    def test_tool_chest_in_front_is_remembered(self):
        w = self.window()
        w.chest_dock.show()
        w.chest_dock.raise_()
        APP.processEvents()
        self.assertTrue(w._chest_showing())
        self.close(w)

        w2 = self.window()
        self.addCleanup(self.close, w2)
        self.assertTrue(w2._chest_showing(), "Tool chest is the tab in front")
        self.assertTrue(w2.a_chest.isChecked())

    def test_toolbars_follow_the_ui_mode_not_the_saved_layout(self):
        w = self.window()
        w.a_ribbon.setChecked(False)           # classic toolbars
        w._toggle_ribbon()
        self.close(w)
        w2 = self.window()
        self.assertFalse(w2.ribbon_tb.isVisible())
        self.assertTrue(w2.tools_tb.isVisible())
        self.assertTrue(w2.main_tb.isVisible())
        w2.a_ribbon.setChecked(True)            # back to the ribbon; the layout saved in
        w2._toggle_ribbon()                     # classic mode must not hide it
        self.close(w2)
        w3 = self.window()
        self.addCleanup(self.close, w3)
        self.assertTrue(w3.ribbon_tb.isVisible())
        self.assertFalse(w3.tools_tb.isVisible())
        self.assertFalse(w3.main_tb.isVisible())


if __name__ == "__main__":
    unittest.main()
