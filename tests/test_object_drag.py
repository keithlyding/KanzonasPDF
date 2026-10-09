"""Dragging a group of page objects shows the shapes and does not redraw them every move.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_object_drag
"""
import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf as F
from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QApplication, QMessageBox
from unittest.mock import patch

from kanzonas.document_view import DocumentView

APP = QApplication.instance() or QApplication([])


class ObjectDrag(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(patch.stopall)
        for name in ("information", "warning", "critical"):
            patch.object(QMessageBox, name, return_value=None).start()
        self.views = []
        self.addCleanup(lambda: [v.close_doc() for v in self.views])

    def test_group_drag_keeps_a_picture_of_the_shapes(self):
        path = self.root / "shapes.pdf"
        doc = F.open()
        page = doc.new_page()
        for i in range(12):
            page.draw_rect((40 + i * 30, 40, 60 + i * 30, 80), color=(0, 0, 0), width=1)
        doc.save(path)
        doc.close()
        view = DocumentView(str(path))
        self.views.append(view)
        view.resize(500, 400)
        view.show()
        view.set_zoom(1.5)
        APP.processEvents()
        items = view.content_objects(0).items
        self.assertGreaterEqual(len(items), 12)
        view.select_objects(0, items)
        before = view.doc[0].read_contents()
        pw = view.pages[0]
        pw._obj_edit = {"mode": "move", "start": QPointF(10, 10), "preview": None}
        calls = {"n": 0}
        real = view.object_lines

        def counted(index, item):
            calls["n"] += 1
            return real(index, item)

        view.object_lines = counted
        pw._obj_edit["preview"] = pw._objects_preview(QPointF(80, 60), False)
        pw._build_object_ghost()
        ghost = pw._obj_edit["ghost_pm"]
        self.assertIsNotNone(ghost)
        self.assertFalse(ghost.isNull())
        self.assertGreater(ghost.width(), 10)
        built = calls["n"]
        self.assertGreater(built, 0)
        for i in range(25):
            pw._obj_edit["preview"] = pw._objects_preview(QPointF(80 + i, 60 + i), False)
            pw._build_object_ghost()
        self.assertEqual(calls["n"], built)
        self.assertIs(pw._obj_edit["ghost_pm"], ghost)
        self.assertEqual(view.doc[0].read_contents(), before)
