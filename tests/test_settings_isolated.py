"""The tests keep their settings in a temporary folder on every system (tests/__init__.py):
never the developer's real KanzonasPDF settings, which on Windows (the registry) and macOS
(the user's preferences) Qt keeps outside any folder the tests could point it at. On 13 Nov
2026 a contributor's remembered CAD mouse mode and Snap to objects made two tests fail on
his Windows machine. Run with -t . (the package's __init__ does the redirect):

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_settings_isolated
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings  # noqa: E402

from kanzonas import paths  # noqa: E402


def inside(path, folder):
    path, folder = os.path.realpath(path), os.path.realpath(folder)
    return os.path.commonpath([path, folder]) == folder


class SettingsIsolated(unittest.TestCase):
    def test_the_apps_settings_are_a_file_in_the_temporary_folder(self):
        st = paths.settings()
        self.assertEqual(st.format(), QSettings.IniFormat)       # (not the registry)
        self.assertTrue(inside(st.fileName(), tempfile.gettempdir()), st.fileName())

    def test_plain_qsettings_too(self):
        st = QSettings()                                          # (as Print's dark lines)
        self.assertEqual(st.format(), QSettings.IniFormat)
        self.assertTrue(inside(st.fileName(), tempfile.gettempdir()), st.fileName())

    def test_a_main_window_uses_them(self):
        from kanzonas.main_window import MainWindow
        from PySide6.QtWidgets import QApplication
        QApplication.instance() or QApplication([])
        w = MainWindow()
        self.addCleanup(w.deleteLater)
        self.assertEqual(w.settings.fileName(), paths.settings().fileName())


if __name__ == "__main__":
    unittest.main()
