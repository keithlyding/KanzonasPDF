"""Shift+wheel always scrolls sideways, and undo keeps the place on the page.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_scroll_undo
"""
import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf as F
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QApplication, QMessageBox
from unittest.mock import patch

from kanzonas.document_view import DocumentView

APP = QApplication.instance() or QApplication([])


def wheel(view, dx, dy, mods=Qt.NoModifier):
    pos = QPointF(20, 20)
    view.wheelEvent(QWheelEvent(
        pos, view.mapToGlobal(pos), QPoint(0, 0), QPoint(dx, dy),
        Qt.NoButton, mods, Qt.NoScrollPhase, False))


class ScrollAndUndo(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(patch.stopall)
        for name in ("information", "warning", "critical"):
            patch.object(QMessageBox, name, return_value=None).start()
        self.views = []
        self.addCleanup(lambda: [v.close_doc() for v in self.views])

    def view(self):
        path = self.root / "in.pdf"
        doc = F.open()
        for i in range(3):
            page = doc.new_page(width=612, height=792)
            page.insert_text((72, 72), "PAGE %d" % i)
        doc.save(path)
        doc.close()
        v = DocumentView(str(path))
        self.views.append(v)
        v.resize(320, 240)
        v.show()
        APP.processEvents()
        return v

    def test_shift_wheel_scrolls_sideways_without_cad_mouse(self):
        v = self.view()
        v.cad_mouse = False
        v.page_wheel = True
        v.set_zoom(3)
        APP.processEvents()
        v.horizontalScrollBar().setValue(30)
        v.verticalScrollBar().setValue(40)
        h, vert = v.horizontalScrollBar().value(), v.verticalScrollBar().value()
        self.assertGreater(v.horizontalScrollBar().maximum(), h)
        wheel(v, 0, 120, Qt.ShiftModifier)
        self.assertLess(v.horizontalScrollBar().value(), h)
        self.assertEqual(v.verticalScrollBar().value(), vert)
        self.assertEqual(v.zoom, 3)

    def test_shift_wheel_does_not_turn_the_page(self):
        v = self.view()
        v.cad_mouse = False
        v.page_wheel = True
        v.fit_page()
        APP.processEvents()
        self.assertTrue(v._page_fits())
        page = v.current_page()
        wheel(v, 0, -240, Qt.ShiftModifier)
        self.assertEqual(v.current_page(), page)
        wheel(v, 0, -240)
        self.assertNotEqual(v.current_page(), page)

    def test_undo_keeps_the_place_on_the_page(self):
        v = self.view()
        v.set_zoom(3)
        APP.processEvents()
        v.verticalScrollBar().setValue(v.verticalScrollBar().maximum() // 2 or 50)
        v.horizontalScrollBar().setValue(v.horizontalScrollBar().maximum() // 2 or 40)
        APP.processEvents()
        anchor = v._view_anchor()
        v._create(0, {"kind": "rect", "props": {"stroke": "#0078d7", "width": 2},
                      "rect": F.Rect(40, 40, 80, 80)})
        v.undo()
        APP.processEvents()
        got = v._view_anchor()
        self.assertEqual(got[0], anchor[0])
        self.assertAlmostEqual(got[1], anchor[1], places=2)
        self.assertAlmostEqual(got[2], anchor[2], delta=2)
