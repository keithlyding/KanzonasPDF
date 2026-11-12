"""Arrange > Group for the page's own drawing (the owner, 12 Nov 2026: "Group is grayed out
when I select multiple objects"): two or more of its lines, shapes, pictures and groups become
one group (a Form XObject, page_objects.group) that Edit objects and CAD mode select and move
as one, and Ungroup takes apart again, its pieces left selected. Markups and the page's own
objects selected together can't be one group: Group stays grayed and its tooltip says why
(the owner's choice). The page's text goes in a group too (the owner: "I definitely need text
to be able to be grouped with objects"), written again inside it as a move writes it.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_group_objects
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402

from tests.test_interaction_112 import A, P, R, Window, pump  # noqa: E402


def look(v):
    return v.doc[0].get_pixmap(dpi=50).samples


def diff(a, b):
    """The share of bytes of two renders that differ."""
    return sum(x != y for x, y in zip(a, b)) / max(len(a), 1)


def kinds(v):
    return [it["kind"] for it in v.obj_sel[1]] if v.obj_sel else []


class GroupObjects(Window):
    def setUp(self):
        def build(pg):
            pg.draw_circle(P(450, 200), 30, color=(1, 0, 0), fill=(0, 0, 1))
            pg.insert_text((100, 650), "Label text", fontsize=14)
        w, v = self.open(build)
        w.set_tool("editobjects")
        pump()
        self.shapes = [it for it in v.content_objects(0).items if it["kind"] == "shape"]
        self.assertEqual(len(self.shapes), 3)

    def test_group_move_undo_ungroup(self):
        w, v = self.w, self.v
        before = look(v)
        v.select_objects(0, self.shapes[:2])
        w._update_ui()
        self.assertTrue(w.a_group.isEnabled())
        w.a_group.trigger()
        pump()
        self.assertEqual(kinds(v), ["group"])
        self.assertEqual(look(v), before)                   # (drawn just the same)
        self.assertEqual([it["kind"] for it in v.content_objects(0).items],
                         ["group", "shape"])                # (the group where the 2nd was, then
                                                            # the circle, drawn after them)
        w._update_ui()
        self.assertTrue(w.a_ungroup.isEnabled())
        # it moves as one
        r0 = v.obj_sel[1][0]["rect"]
        QTest.keyClick(v.viewport(), Qt.Key_Right)
        pump()
        self.assertEqual(kinds(v), ["group"])
        self.assertAlmostEqual(v.obj_sel[1][0]["rect"].x0, r0.x0 + 1, delta=0.3)
        w.a_undo.trigger()                                  # (the move)
        pump()
        self.assertEqual(kinds(v), ["group"])
        # Ungroup: its two lines again, both selected, drawn the same
        w.a_ungroup.trigger()
        pump()
        self.assertEqual(kinds(v), ["shape", "shape"])
        self.assertEqual(look(v), before)
        w.a_undo.trigger()                                  # (the ungroup)
        pump()
        w.a_undo.trigger()                                  # (the group)
        pump()
        self.assertEqual(len(v.content_objects(0).items), 3)
        self.assertEqual(look(v), before)

    def test_a_group_in_a_group_and_saved(self):
        w, v = self.w, self.v
        before = look(v)
        v.select_objects(0, self.shapes[:2])
        w.a_group.trigger()
        pump()
        objs = v.content_objects(0).items
        v.select_objects(0, objs)                           # (the group and the circle)
        w._update_ui()
        self.assertTrue(w.a_group.isEnabled())
        w.a_group.trigger()
        pump()
        self.assertEqual([it["kind"] for it in v.content_objects(0).items], ["group"])
        self.assertEqual(look(v), before)
        out = os.path.join(os.path.dirname(v.path), "saved.pdf")
        v.doc.save(out, garbage=3)
        d = pymupdf.open(out)
        self.assertEqual(d[0].get_pixmap(dpi=50).samples, before)

    def test_text_goes_in_the_group(self):
        """The owner, 12 Nov: "I definitely need text to be able to be grouped with
        objects"."""
        w, v = self.w, self.v
        before = look(v)
        text = v.text_objects(0)[0]
        v.select_objects(0, [self.shapes[0], text])
        w._update_ui()
        self.assertTrue(w.a_group.isEnabled())
        w.a_group.trigger()
        pump()
        self.assertEqual(kinds(v), ["group"])
        self.assertTrue(v.obj_sel[1][0]["rect"].contains(text["rect"]))
        self.assertLess(diff(look(v), before), 0.002)       # (the text written again)
        self.assertIn("Label text", v.doc[0].get_text())    # (still text: found, copied)
        # moved as one: the line and its label together
        r0 = pymupdf.Rect(v.obj_sel[1][0]["rect"])
        for _ in range(5):
            QTest.keyClick(v.viewport(), Qt.Key_Down)
            pump()
        self.assertEqual(kinds(v), ["group"])
        self.assertAlmostEqual(v.obj_sel[1][0]["rect"].y0, r0.y0 + 5, delta=0.5)
        words = [w_ for w_ in v.doc[0].get_text("words") if w_[4] == "Label"]
        self.assertAlmostEqual(words[0][1], text["rect"].y0 + 5, delta=2)
        # a click on the label (Edit objects, then CAD mode) picks the whole group
        v.select_objects(0, [])
        self.click(v.pages[0], self.at(P(120, 650)))
        self.assertEqual(kinds(v), ["group"])
        was = v.mouse_mode
        w.set_mouse_mode("cad")
        pump()
        v.select_objects(0, [])
        self.click(v.pages[0], self.at(P(120, 650)))
        self.assertEqual(kinds(v), ["group"])
        w.set_mouse_mode(was)
        w.set_tool("editobjects")
        pump()
        # Ungroup: the line and the text on their own again
        self.click(v.pages[0], self.at(P(120, 650)))
        self.assertEqual(kinds(v), ["group"])
        w.a_ungroup.trigger()
        pump()
        self.assertIn("Label text", v.doc[0].get_text())
        self.assertEqual(sorted(it["kind"] for it in v.content_objects(0).items),
                         ["shape", "shape", "shape"])

    def test_text_alone_and_two_paragraphs(self):
        w, v = self.w, self.v
        v.doc[0].insert_text((100, 700), "Second label", fontsize=12)
        v._clear_caches()
        texts = v.text_objects(0)
        self.assertEqual(len(texts), 2)
        v.select_objects(0, texts)
        w._update_ui()
        self.assertTrue(w.a_group.isEnabled())
        w.a_group.trigger()
        pump()
        self.assertEqual(kinds(v), ["group"])
        got = v.doc[0].get_text()
        self.assertIn("Label text", got)
        self.assertIn("Second label", got)

    def test_markups_with_objects_say_why(self):
        w, v = self.w, self.v
        # a markup with one of the drawing's lines (as CAD mode selects them)
        x = v._create(0, {"kind": "rect", "rect": R(300, 500, 340, 540), "text": "",
                          "props": dict(A.DEFAULTS["rect"])})
        v.select_xref(0, x)
        v.select_objects(0, [self.shapes[0]])
        self.assertIsNotNone(v.selection)
        w._update_ui()
        self.assertFalse(w.a_group.isEnabled())
        self.assertIn("Markups and the page's own objects", w.a_group.toolTip())
        # one markup alone: grayed, and the tip says what Group needs
        v.obj_sel = None
        w._update_ui()
        self.assertFalse(w.a_group.isEnabled())
        self.assertIn("two or more markups", w.a_group.toolTip())

    def test_cad_mode_picks_the_group_whole(self):
        w, v = self.w, self.v
        v.select_objects(0, self.shapes[:2])
        w.a_group.trigger()
        pump()
        v.clear_selection()
        v.select_objects(0, [])
        was = v.mouse_mode
        w.set_mouse_mode("cad")
        self.addCleanup(lambda: (w.set_mouse_mode(was), pump()))
        pump()
        self.click(v.pages[0], self.at(P(250, 100)))       # (on the first line)
        self.assertEqual(kinds(v), ["group"])


if __name__ == "__main__":
    unittest.main()
