"""A status bar message too long for the room left of the page controls (long Spanish ones at
1440 pixels) ends in "..." instead of running under the controls, and its tool tip has all of
it; a message that fits is shown whole.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_status_message
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QPoint  # noqa: E402
from PySide6.QtGui import QHelpEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QToolTip  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas.main_window import MainWindow  # noqa: E402


class LongMessage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.w = MainWindow()
        cls.w.resize(1100, 700)
        cls.w.show()
        APP.processEvents()
        cls.sb = cls.w.statusBar()

    @classmethod
    def tearDownClass(cls):
        cls.w._close_confirmed = True
        cls.w.close()

    def tip_at(self, x):
        """The tool tip shown on hovering over the bar at x ("" for none)."""
        shown = []
        pos = QPoint(x, self.sb.height() // 2)
        with mock.patch.object(QToolTip, "showText", lambda _p, text, *_a: shown.append(text)):
            QApplication.sendEvent(self.sb, QHelpEvent(QEvent.ToolTip, pos,
                                                       self.sb.mapToGlobal(pos)))
        return shown[-1] if shown else ""

    def test_a_long_message_is_cut_short_left_of_the_controls(self):
        # (long enough for the bar as wide as it is here, in this platform's font: the Windows
        # job's bar and font measure differently from Linux's)
        unit, fm = "Modo nocturno activado: páginas dibujadas en blanco sobre negro ", \
            self.sb.fontMetrics()
        n = 6
        while fm.horizontalAdvance((unit * n).strip()) <= 2 * self.sb.message_rect().width() \
                and n < 600:
            n += 6
        long = unit * n
        self.sb.showMessage(long.strip())
        self.addCleanup(self.sb.clearMessage)
        APP.processEvents()
        shown = self.sb.shown_message()
        self.assertTrue(shown.endswith("…"), "%s (bar %d px, room %d px, message %d px)" % (
            shown[-80:], self.sb.width(), self.sb.message_rect().width(),
            fm.horizontalAdvance(long.strip())))
        room = self.sb.message_rect()
        self.assertLessEqual(self.sb.fontMetrics().horizontalAdvance(shown), room.width())
        controls = self.sb._controls()              # (the page controls...)
        self.assertTrue(controls)
        for c in controls:
            self.assertLessEqual(room.right(), c.x())
        self.assertEqual(self.tip_at(20), long.strip())
        self.sb.grab()                              # (paints)

    def test_a_short_message_is_shown_whole_without_a_tip(self):
        QToolTip.showText(self.sb.mapToGlobal(QPoint(20, 5)), "A tip", self.sb)
        self.addCleanup(QToolTip.hideText)  # (a tip's own window is no control on the bar)
        self.sb.showMessage("Saved")
        self.addCleanup(self.sb.clearMessage)
        self.assertEqual(self.sb.shown_message(), "Saved")
        self.assertEqual(self.tip_at(20), "")
        self.sb.grab()


if __name__ == "__main__":
    unittest.main()
