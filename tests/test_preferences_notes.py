"""Preferences: the Scroll one page per wheel step option (of the Standard and Hand mouse modes)
says, in plain sight (not only in a tooltip), that it applies only while the whole page fits
in the window."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel, QCheckBox  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas.main_window import MainWindow  # noqa: E402
from kanzonas.preferences import PreferencesDialog  # noqa: E402


class PreferencesNotes(unittest.TestCase):
    def test_page_wheel_note_is_visible_text(self):
        w = MainWindow()
        self.addCleanup(w.close)
        w._close_confirmed = True
        d = PreferencesDialog(w)
        self.addCleanup(d.close)
        boxes = [b for b in d.findChildren(QCheckBox)
                 if b.text() == "Scroll one page per wheel step"]
        self.assertEqual(len(boxes), 2)                 # Standard and Hand mouse modes
        notes = [lab for lab in d.findChildren(QLabel)
                 if lab.text().startswith("Only when the whole page fits in the window")]
        self.assertEqual(len(notes), 2)
        for box, note in zip(boxes, notes):
            self.assertTrue(note.wordWrap())
            # same parent as the box it explains
            self.assertIs(note.parentWidget(), box.parentWidget())


if __name__ == "__main__":
    unittest.main()
