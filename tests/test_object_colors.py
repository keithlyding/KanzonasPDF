"""Colors of the page's own drawing and text (the owner, 12 Nov 2026: "Need a way of changing
text's color and changing the fill color of an object", "Both": the fill and the line; put
on hold, then asked for on 14 Nov). Edit objects (and CAD mode) > right-click > Line color...,
Fill color... and Text color... change what's selected, in one undo step, and it stays
selected. A shape's color is set in a  q ... Q  of its own (page_objects.recolor), so what's
drawn after it keeps its colors, and coloring it again replaces that color (no nesting);
text is written again where it is in the new color (text_edit.recolor_lines), each word
keeping its font, size and style.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_object_colors
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402

from tests.test_interaction_112 import P, R, Window, pump  # noqa: E402
from kanzonas import page_objects  # noqa: E402

RED, GREEN, BLUE, YELLOW = (1, 0, 0), (0, 0.6, 0), (0, 0, 1), (1, 0.85, 0)


def pixel(v, pt):
    """The color at page point pt (72 dpi, unrotated page)."""
    pix = v.doc[0].get_pixmap(dpi=72)
    return pix.pixel(int(pt.x), int(pt.y))


def near(got, rgb, tol=40):
    return all(abs(g - c * 255) <= tol for g, c in zip(got, rgb))


def span_colors(v, word):
    out = []
    for b in v.doc[0].get_text("dict")["blocks"]:
        for ln in b.get("lines", []):
            for s in ln["spans"]:
                if word in s["text"]:
                    out.append(pymupdf.sRGB_to_rgb(s["color"]))     # (0-255)
    return out


class ObjectColors(Window):
    def setUp(self):
        def build(pg):
            pg.draw_rect(R(320, 300, 420, 380), color=(0, 0, 0), fill=BLUE, width=6)
            pg.draw_rect(R(450, 300, 550, 380), color=(0, 0, 0), fill=GREEN, width=6)
            pg.insert_text((100, 600), "Plain words here", fontsize=20)
        w, v = self.open(build)
        w.set_tool("editobjects")
        pump()

    def shapes(self):
        return [it for it in self.v.content_objects(0).items if it["kind"] == "shape"]

    def filled(self):
        """The two filled rectangles (the window's line and outline aside), left to right."""
        return sorted((it for it in self.shapes() if it.get("fill")), key=lambda it: it["rect"].x0)

    def test_fill_and_line_of_one_shape(self):
        v = self.v
        first, second = self.filled()
        v.select_objects(0, [first])
        self.assertEqual(v.object_colors(), {"stroke", "fill"})
        v.recolor_objects(fill=RED)
        pump()
        self.assertTrue(near(pixel(v, P(370, 340)), RED), pixel(v, P(370, 340)))
        self.assertTrue(near(pixel(v, P(500, 340)), GREEN))            # (the next one: as it was)
        self.assertTrue(near(pixel(v, P(451, 340)), (0, 0, 0)))        # (and its outline)
        self.assertTrue(near(pixel(v, P(321, 340)), (0, 0, 0)))        # (its own line: unchanged)
        self.assertEqual(len(v.obj_sel[1]), 1)                         # (still selected)
        v.recolor_objects(stroke=YELLOW)
        pump()
        self.assertTrue(near(pixel(v, P(321, 340)), YELLOW), pixel(v, P(321, 340)))
        self.assertTrue(near(pixel(v, P(370, 340)), RED))              # (its fill kept)
        self.assertTrue(near(pixel(v, P(451, 340)), (0, 0, 0)))
        # undone one step at a time, redone
        v.undo()
        pump()
        self.assertTrue(near(pixel(v, P(321, 340)), (0, 0, 0)))
        self.assertTrue(near(pixel(v, P(370, 340)), RED))
        v.undo()
        pump()
        self.assertTrue(near(pixel(v, P(370, 340)), BLUE))
        v.redo()
        v.redo()
        pump()
        self.assertTrue(near(pixel(v, P(370, 340)), RED))
        self.assertTrue(near(pixel(v, P(321, 340)), YELLOW))

    def test_colored_again_is_replaced_not_nested(self):
        v = self.v
        v.select_objects(0, [self.filled()[0]])
        v.recolor_objects(fill=RED)
        size = len(page_objects._contents(v.doc[0]))
        for rgb in (GREEN, YELLOW, BLUE, RED):
            v.recolor_objects(fill=rgb)
        pump()
        self.assertTrue(near(pixel(v, P(370, 340)), RED))
        data = page_objects._contents(v.doc[0])
        self.assertLessEqual(len(data), size + 4)
        self.assertEqual(data.count(b"\nq\n"), page_objects._contents(v.doc[0]).count(b"\nq\n"))
        self.assertEqual(len(self.filled()), 2)                        # (still the same shapes)

    def test_moved_then_colored_and_colored_then_moved(self):
        v = self.v
        v.select_objects(0, [self.filled()[0]])
        v.move_objects(v.selected_objects_rect() + (0, 40, 0, 40))
        pump()
        v.recolor_objects(fill=RED)
        pump()
        self.assertTrue(near(pixel(v, P(370, 380)), RED))
        v.move_objects(v.selected_objects_rect() + (-20, 0, -20, 0))
        pump()
        self.assertTrue(near(pixel(v, P(350, 380)), RED))
        self.assertTrue(near(pixel(v, P(500, 340)), GREEN))
        self.assertEqual(len(self.filled()), 2)

    def test_two_shapes_at_once_in_one_step(self):
        v = self.v
        v.select_objects(0, self.filled())
        v.recolor_objects(fill=YELLOW)
        pump()
        self.assertTrue(near(pixel(v, P(370, 340)), YELLOW))
        self.assertTrue(near(pixel(v, P(500, 340)), YELLOW))
        v.undo()
        pump()
        self.assertTrue(near(pixel(v, P(370, 340)), BLUE))
        self.assertTrue(near(pixel(v, P(500, 340)), GREEN))

    def test_text_color(self):
        v = self.v
        t = v.text_objects(0)
        t = [it for it in t if "Plain" in "".join(ln["spans"][0]["text"] for _r, ln in it["lines"])]
        self.assertEqual(len(t), 1)
        v.select_objects(0, t)
        self.assertEqual(v.object_colors(), {"text"})
        v.recolor_objects(text=RED)
        pump()
        got = span_colors(v, "Plain")
        self.assertTrue(got and all(near(g, RED, 3) for g in got), got)
        self.assertIn("Plain words here", v.doc[0].get_text())        # (the same words)
        self.assertEqual([it["kind"] for it in v.obj_sel[1]], ["text"])  # (still selected)
        v.undo()
        pump()
        self.assertTrue(all(near(g, (0, 0, 0), 3)
                            for g in span_colors(v, "Plain")))

    def test_mixed_selection_colors_only_what_it_can(self):
        v = self.v
        t = v.text_objects(0)
        v.select_objects(0, [self.filled()[0]] + t[:1])
        self.assertEqual(v.object_colors(), {"stroke", "fill", "text"})
        v.recolor_objects(fill=RED)                 # (the text as it was)
        pump()
        self.assertTrue(near(pixel(v, P(370, 340)), RED))
        self.assertTrue(all(near(g, (0, 0, 0), 3)
                            for g in span_colors(v, "Plain")))
        self.assertEqual(len(v.obj_sel[1]), 2)

    def test_the_menu_and_the_color_dialog(self):
        from PySide6.QtGui import QColor
        from PySide6.QtWidgets import QColorDialog
        v = self.v
        v.select_objects(0, [self.filled()[1]])
        with mock.patch.object(QColorDialog, "getColor", return_value=QColor(255, 0, 0)) as got:
            v.pick_object_color("fill")
        self.assertTrue(near(pixel(v, P(500, 340)), RED))
        with mock.patch.object(QColorDialog, "getColor", return_value=QColor()) as got:
            v.pick_object_color("fill")             # (Cancel: nothing changes)
        self.assertEqual(got.call_args[0][0].name(), "#ff0000")      # (the last color offered)
        self.assertTrue(near(pixel(v, P(500, 340)), RED))
        # the right-click menu: Fill color... enabled for a filled shape, Text color... not
        from PySide6.QtCore import QPoint
        from PySide6.QtWidgets import QMenu
        seen = {}

        class Menu(QMenu):
            def exec(self, *_a):
                seen.update({a.text(): a.isEnabled() for a in self.actions()})
        pw = v.pages[0]
        ev = mock.Mock()
        ev.globalPosition.return_value.toPoint.return_value = QPoint(0, 0)
        with mock.patch("PySide6.QtWidgets.QMenu", Menu):
            pw._objects_menu(ev, P(500, 340))
        self.assertTrue(seen.get("Fill color..."))
        self.assertTrue(seen.get("Line color..."))
        self.assertFalse(seen.get("Text color...", True))


class ShapeColorsInContent(unittest.TestCase):
    """page_objects.recolor on its own: what it writes."""

    def page(self):
        d = pymupdf.open()
        pg = d.new_page(width=300, height=200)
        pg.draw_rect(R(20, 20, 100, 100), color=(0, 0, 0), fill=BLUE, width=4)
        pg.draw_rect(R(150, 20, 230, 100), color=(0, 0, 0), fill=GREEN, width=4)
        self._doc = d
        return pg

    def test_written_in_its_own_save_and_restore(self):
        pg = self.page()
        objs = page_objects.Objects(pg)
        first = [it for it in objs.items if it["kind"] == "shape"][0]
        got = page_objects.recolor(pg, [first["n"]], fill=RED, objs=objs)
        data = page_objects._contents(pg)
        self.assertIn(b"\nq\n1 0 0 rg\n", data)
        # the Objects worked out without reading the page again are the ones a read gives
        fresh = page_objects.Objects(pg)
        self.assertEqual([(a["n"], a["kind"], tuple(a["rect"])) for a in got.items],
                         [(a["n"], a["kind"], tuple(a["rect"])) for a in fresh.items])

    def test_nothing_asked_nothing_changed(self):
        pg = self.page()
        before = page_objects._contents(pg)
        page_objects.recolor(pg, [0, 1])
        self.assertEqual(page_objects._contents(pg), before)


if __name__ == "__main__":
    unittest.main()
