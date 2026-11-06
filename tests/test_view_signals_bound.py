"""Signals the main window takes from the shown view only: layersChanged (page thumbnails redrawn
when a layer is turned on or off) and textToolPropsChanged (Edit text's font and size in the
Properties panel). They were connected to lambdas that checked self.sender(), which inside a
lambda isn't the view that sent the signal, so neither ever ran.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_view_signals_bound
"""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf
from PySide6.QtWidgets import QApplication, QMessageBox

from kanzonas.main_window import MainWindow

APP = QApplication.instance() or QApplication([])


class ViewSignalsBound(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(patch.stopall)
        for name in ("information", "warning", "critical"):
            patch.object(QMessageBox, name, return_value=None).start()
        patch.object(QMessageBox, "question", return_value=QMessageBox.Discard).start()
        self.paths = []
        for k in range(2):
            p = str(Path(self.tmp.name) / ("doc%d.pdf" % k))
            d = pymupdf.open()
            d.new_page().insert_text((72, 72), "page %d" % k)
            d.save(p)
            d.close()
            self.paths.append(p)
        self.w = MainWindow()
        self.addCleanup(self.w.deleteLater)
        self.w.show()
        for p in self.paths:
            self.w.open_file(p)
        APP.processEvents()

    def test_shown_view_reaches_the_window_and_others_dont(self):
        w = self.w
        w.tabs.setCurrentIndex(1)
        APP.processEvents()
        shown, other = w.tabs.widget(1), w.tabs.widget(0)
        with patch.object(w, "_rebuild_thumbs") as thumbs, \
                patch.object(w, "_refresh_props") as props:
            shown.layersChanged.emit()
            shown.textToolPropsChanged.emit()
            self.assertEqual(thumbs.call_count, 1)
            self.assertEqual(props.call_count, 1)
            other.layersChanged.emit()          # a tab in the background: not shown here
            other.textToolPropsChanged.emit()
            self.assertEqual(thumbs.call_count, 1)
            self.assertEqual(props.call_count, 1)


if __name__ == "__main__":
    unittest.main()
