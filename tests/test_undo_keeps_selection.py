"""Undo and Redo keep what's selected selected (the owner, 12 Nov 2026: "when clicking undo or
redo, whatever I had selected becomes unselected"), with the menu commands as the owner uses
them: markups by xref, the drawing's own shapes by their place in the drawing order or their
box, text by its lines. What the step took away stays unselected.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_undo_keeps_selection
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402

from tests.test_interaction_112 import A, P, R, Window, pump  # noqa: E402


def boxes(v):
    return [(it["kind"], tuple(round(c) for c in it["rect"])) for it in v.obj_sel[1]] \
        if v.obj_sel else []


class Markups(Window):
    def setUp(self):
        w, v = self.open()
        props = dict(A.DEFAULTS["rect"])
        self.a = v._create(0, {"kind": "rect", "rect": R(300, 500, 340, 540), "text": "",
                               "props": props})
        self.b = v._create(0, {"kind": "rect", "rect": R(400, 520, 440, 560), "text": "",
                               "props": props})
        pump()

    def test_a_move_undone_and_redone(self):
        w, v = self.w, self.v
        v.select_xref(0, self.a)
        v.select_xref(0, self.b, add=True)
        QTest.keyClick(v.viewport(), Qt.Key_Right)
        pump()
        w.a_undo.trigger()
        pump()
        self.assertEqual(v.selected_xrefs(), [self.a, self.b])
        w._update_ui()
        self.assertTrue(w.a_group.isEnabled())          # (the menus follow it)
        w.a_redo.trigger()
        pump()
        self.assertEqual(v.selected_xrefs(), [self.a, self.b])

    def test_what_the_undo_takes_away_stays_unselected(self):
        w, v = self.w, self.v
        v.select_xref(0, self.a)
        v.select_xref(0, self.b, add=True)
        w.a_undo.trigger()                              # (b's creation undone)
        pump()
        self.assertEqual(v.selected_xrefs(), [self.a])


class DrawingObjects(Window):
    def setUp(self):
        def build(pg):
            pg.insert_text((100, 600), "Hello world text line", fontsize=14)
        w, v = self.open(build)
        w.set_tool("editobjects")
        pump()

    def test_shapes_moved_and_the_move_undone(self):
        w, v = self.w, self.v
        self.drag(v.pages[0], self.at(P(80, 80)), self.at(P(450, 470)))
        self.assertEqual(len(v.obj_sel[1]), 2)
        before = boxes(v)
        QTest.keyClick(v.viewport(), Qt.Key_Right)
        pump()
        moved = boxes(v)
        self.assertNotEqual(moved, before)
        w.a_undo.trigger()
        pump()
        self.assertEqual(boxes(v), before)
        w.a_redo.trigger()
        pump()
        self.assertEqual(boxes(v), moved)

    def test_bring_to_front_undone_keeps_the_same_shape(self):
        w, v = self.w, self.v
        objs = v.content_objects(0).items
        first = [it for it in objs if it["kind"] == "shape"][0]
        v.select_objects(0, [first])
        box = boxes(v)
        w.arrange_actions["z_front"].trigger()
        pump()
        self.assertEqual(boxes(v), box)
        w.a_undo.trigger()
        pump()
        self.assertEqual(boxes(v), box)                 # (the same line, not the other one)

    def test_text_moved_and_the_move_undone(self):
        w, v = self.w, self.v
        t = v.text_objects(0)[0]
        v.select_objects(0, [t])
        before = boxes(v)
        for _ in range(3):
            QTest.keyClick(v.viewport(), Qt.Key_Down)
            pump()
        w.a_undo.trigger()
        pump()
        self.assertEqual([k for k, _b in boxes(v)], ["text"])
        self.assertAlmostEqual(v.obj_sel[1][0]["rect"].y0, before[0][1][1], delta=1.5)


if __name__ == "__main__":
    unittest.main()
