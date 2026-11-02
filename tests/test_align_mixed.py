"""Align and Distribute on a mix of kinds: markups and the drawing's own objects (lines,
pictures, text selected with Edit objects or in CAD mode). From a test of 1.7: three items of
different kinds selected, and Align stayed grayed out (only markups were counted).

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_align_mixed
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import annotations, main_window  # noqa: E402

P = pymupdf.Point


def sheet(rotation=0):
    """A line and a rectangle drawn in the page itself, a word of page text, and a
    rectangle markup, each starting at a different left edge and height."""
    d = pymupdf.open()
    p = d.new_page(width=612, height=792)
    p.draw_line((100, 100), (250, 100), color=(0, 0, 1), width=2)
    p.draw_rect(pymupdf.Rect(160, 200, 300, 260), color=(1, 0, 0), width=2)
    p.insert_text((220, 400), "Valve", fontsize=20)
    p.set_rotation(rotation)
    annotations.write(p, {"kind": "rect", "props": dict(annotations.DEFAULTS["rect"]),
                          "rect": pymupdf.Rect(260, 500, 380, 560)})
    path = os.path.join(tempfile.mkdtemp(), "mixed.pdf")
    d.save(path)
    return path


class Mixed(unittest.TestCase):
    def setUp(self):
        w = self.w = main_window.MainWindow()
        self.addCleanup(lambda: [setattr(x, "_close_confirmed", True) or x.close()
                                 for x in main_window.windows()])
        w.resize(1200, 900)
        w.show()
        APP.processEvents()

    def open(self, rotation=0):
        self.w.open_file(sheet(rotation))
        APP.processEvents()
        v = self.v = self.w.view()
        self.addCleanup(lambda: setattr(v, "dirty", False))
        return v

    def select_all(self, with_markup=True):
        v = self.v
        if with_markup:
            xs = [a.xref for a in annotations.each_annot(v.doc[0])]
            v._set_selection(0, xs)
        shapes = [it for it in v.content_objects(0).items if it["kind"] != "text"]
        texts = v.text_objects(0)
        self.assertEqual(len(shapes), 2)
        self.assertEqual(len(texts), 1)
        v.select_objects(0, shapes + texts)
        APP.processEvents()

    def boxes(self):
        """Every item's box as seen on screen, after reading the page again."""
        v = self.v
        v._obj_cache.pop(0, None)
        page = v.doc[0]
        rot = page.rotation_matrix
        out = [pymupdf.Rect(it["rect"]) * rot for it in v.content_objects(0).items
               if it["kind"] != "text"]
        out += [pymupdf.Rect(it["rect"]) * rot for it in v.text_objects(0)]
        out += [v._display_bounds(page, annotations.read(a))
                for a in annotations.each_annot(page)]
        return out

    def test_three_objects_of_different_kinds_enable_align_and_distribute(self):
        v = self.open()
        self.select_all(with_markup=False)
        self.w._update_ui()
        A = self.w.arrange_actions
        self.assertTrue(A["al_left"].isEnabled())
        self.assertTrue(A["dist_h"].isEnabled())
        # two of them: Align yes, Distribute no
        v.select_objects(0, v.selected_objects()[:2])
        APP.processEvents()
        self.assertTrue(A["al_left"].isEnabled())
        self.assertFalse(A["dist_h"].isEnabled())
        # and a third again turns Distribute back on (the menus heard about it)
        v.select_objects(0, v.text_objects(0), add=True)
        APP.processEvents()
        self.assertTrue(A["dist_h"].isEnabled())

    def test_align_left_moves_shapes_text_and_markups_together(self):
        self.open()
        self.select_all()
        self.w._set_align_ref("selection")
        self.w._align("left")
        APP.processEvents()
        lefts = [round(b.x0, 1) for b in self.boxes()]
        self.assertEqual(len(lefts), 4)
        self.assertLess(max(lefts) - min(lefts), 1.5, lefts)
        # one undo step brings everything back
        self.v.undo()
        APP.processEvents()
        lefts = [round(b.x0) for b in self.boxes()]
        self.assertGreater(max(lefts) - min(lefts), 100)

    def test_align_on_a_turned_page(self):
        self.open(rotation=90)
        self.select_all()
        self.w._set_align_ref("selection")
        self.w._align("top")
        APP.processEvents()
        tops = [round(b.y0, 1) for b in self.boxes()]
        self.assertLess(max(tops) - min(tops), 1.5, tops)

    def test_distribute_mixed_kinds(self):
        self.open()
        self.select_all()
        self.v.distribute("v")
        APP.processEvents()
        bs = sorted(self.boxes(), key=lambda b: b.y0)
        gaps = [bs[k + 1].y0 - bs[k].y1 for k in range(3)]
        self.assertLess(max(gaps) - min(gaps), 1.5, gaps)

    def test_markups_alone_still_align(self):
        v = self.open()
        page = v.doc[0]
        annotations.write(page, {"kind": "rect", "props": dict(annotations.DEFAULTS["rect"]),
                                 "rect": pymupdf.Rect(50, 600, 90, 640)})
        del page
        xs = [a.xref for a in annotations.each_annot(v.doc[0])]
        v._set_selection(0, xs)
        v.align("right", "first")
        APP.processEvents()
        page = v.doc[0]
        rights = [round(v._display_bounds(page, annotations.read(a)).x1, 1)
                  for a in annotations.each_annot(page)]
        self.assertEqual(len(set(rights)), 1, rights)


if __name__ == "__main__":
    unittest.main()
