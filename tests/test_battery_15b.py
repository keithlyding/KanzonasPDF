"""What the second break-it battery of 1.5 found, fixed: a straight level line selected with
Edit objects has a real box (rotate turns it about its middle, the handles sit on it, Bring
forward sees what crosses it); a few letters typed on the CAD command line never quit (EX is
AutoCAD's Extend) or run one of several commands; accents don't matter in the palette; the
keyboard goes back to the page when a command ends; a command whose selection changed under
it ends; a box being drawn goes with a change to the document; switching tools applies the
text being edited; Ctrl+C copies a picture selected with Edit objects; no busy pointer over a
message box.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_battery_15b
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from tests.test_battery_15 import APP, Window  # noqa: E402

from kanzonas import cad_commands, cad_select, document_view, page_objects, palette  # noqa: E402


class StraightLines(unittest.TestCase):
    def test_the_box_around_level_and_plumb_lines(self):
        self.assertEqual(page_objects.bounding([pymupdf.Rect(350, 120, 500, 120)]),
                         pymupdf.Rect(350, 120, 500, 120))
        self.assertEqual(page_objects.bounding([pymupdf.Rect(10, 10, 20, 10),
                                                pymupdf.Rect(30, 10, 40, 10)]),
                         pymupdf.Rect(10, 10, 40, 10))
        self.assertTrue(page_objects.bounding([]).is_empty)


class BigArrays(unittest.TestCase):
    def page(self, content):
        d = pymupdf.open()
        p = d.new_page()
        x = d.get_new_xref()
        d.update_object(x, "<<>>")
        d.update_stream(x, content)
        p.set_contents(x)
        return d, p

    def mats(self):
        return [pymupdf.Matrix(1, 0, 0, 1, 30 * k, 0) for k in range(1, 22)]

    def test_a_block_holds_only_what_it_uses_and_ungroup_adds_nothing_twice(self):
        d, p = self.page(b"0 0 0 RG 10 10 m 20 20 l S 30 10 m 40 20 l S")
        page_objects.block_copies(p, [0, 1], self.mats())
        res = d.xref_object(int(d.xref_get_key(p.xref, "Resources")[1].split()[0])
                            if d.xref_get_key(p.xref, "Resources")[0] == "xref" else p.xref)
        before = len(d.tobytes(garbage=1))
        for _ in range(5):
            found = page_objects.scan(page_objects._contents(p))
            groups = [k for k, f in enumerate(found) if not f.get("path")]
            page_objects.ungroup(p, groups[:1])
        self.assertLess(len(d.tobytes(garbage=1)), before + 2000, res)

    def test_under_a_clip_or_in_a_layer_copies_are_written_out(self):
        d, p = self.page(b"q 0 0 100 100 re W n 0 0 0 RG 10 10 m 20 20 l S Q "
                         b"0 0 1 RG 30 10 m 40 20 l S")
        page_objects.block_copies(p, [0, 1], self.mats())
        self.assertNotIn(b"KzBlock", page_objects._contents(p))
        d, p = self.page(b"0 0 0 RG 10 10 m 20 20 l S 30 10 m 40 20 l S")
        page_objects.block_copies(p, [0, 1], self.mats())
        self.assertIn(b"KzBlock", page_objects._contents(p))

    def test_trim_keeps_the_closing_edge_of_an_s_shape(self):
        d, p = self.page(b"0 0 0 RG 10 10 m 60 10 l 35 60 l 100 10 m 150 10 l 125 60 l s")
        found = page_objects.scan(page_objects._contents(p))
        state, parts, paint = page_objects.subpaths(page_objects._contents(p), found[0])
        self.assertFalse(parts[0][2])           # s closes only the last subpath
        self.assertTrue(parts[1][2])
        page_objects.rewrite_path(p, 0, state, [[[pymupdf.Point(10, 10),
                                                  pymupdf.Point(40, 10)]], parts[1][0]], paint)
        self.assertTrue(page_objects._contents(p).rstrip().endswith(b"h S"))

    def test_an_edit_writes_over_its_own_stream(self):
        d, p = self.page(b"0 0 0 RG 10 10 m 20 20 l S")
        for k in range(6):
            page_objects.transform(p, [0], pymupdf.Matrix(1, 0, 0, 1, 1, 0))
        sizes = [len(d.tobytes())]
        for k in range(6):
            page_objects.transform(p, [0], pymupdf.Matrix(1, 0, 0, 1, 1, 0))
        sizes.append(len(d.tobytes()))
        self.assertLess(sizes[1] - sizes[0], 200)


class Lines(Window):
    def select_line(self, v):
        v.set_tool("editobjects")
        objs = v.content_objects(0)
        v.select_objects(0, [it for it in objs.items if it["kind"] == "shape"])
        return objs

    def test_a_level_line_turns_about_its_middle(self):
        v = self.open()
        self.select_line(v)
        r = v.selected_objects_rect()
        self.assertAlmostEqual(r.x0, 100, 1)
        self.assertAlmostEqual(r.x1, 200, 1)
        v.rotate_objects(90)
        line = [it for it in v.content_objects(0).items if it["kind"] == "shape"][0]
        self.assertAlmostEqual((line["rect"].x0 + line["rect"].x1) / 2, 150, 0)
        self.assertGreater(line["rect"].height, 90)

    def test_bring_forward_sees_a_filled_box_crossing_a_line(self):
        d = pymupdf.open()
        p = d.new_page()
        p.draw_line((100, 100), (200, 100))
        p.draw_rect(pymupdf.Rect(140, 80, 160, 120), color=(0, 0, 1), fill=(1, 0, 0))
        self.assertTrue(page_objects.reorder(p, [0], "forward"))
        found = page_objects.scan(page_objects._contents(p))
        self.assertTrue(found[-1]["path"] and found[-1]["box"][1] == found[-1]["box"][3])

    def test_ctrl_c_copies_a_picture_selected_with_edit_objects(self):
        v = self.open()
        v.set_tool("editobjects")
        pic = {"kind": "picture", "xref": 0, "rect": pymupdf.Rect(10, 10, 50, 50), "n": 0}
        with mock.patch.object(type(v), "selected_objects", lambda s: [pic]), \
                mock.patch.object(type(v), "copy_picture") as cp:
            self.assertEqual(v.copy(), "picture")
        self.assertTrue(cp.called)

    def test_switching_tools_applies_the_text_being_edited(self):
        v = self.open()
        with mock.patch.object(type(v), "commit_pending") as commit:
            v.set_tool("editobjects")
        self.assertTrue(commit.called)


class CommandLine(Window):
    def line(self):
        self.open()
        return self.w.cad_command_line()

    def test_a_few_letters_never_quit_or_guess(self):
        line = self.line()
        for text in ("ex", "EX", "a", "u", "p", "re", "ch", "sa"):
            self.assertIsNone(line._pick(text), text)
        self.assertEqual(line._pick("fit page"), ("action", "Fit page"))
        self.assertEqual(line._pick("save as"), ("action", "Save As"))
        line.edit.setText("ex")
        line.run()
        self.assertTrue(self.w.isVisible())

    def test_accents_dont_matter(self):
        self.assertTrue(cad_commands._word_start("ajustar pagina", "Ajustar página"))
        self.assertIsNotNone(palette.match("pagina", "Página siguiente"))

    def test_the_keyboard_goes_back_to_the_page_when_a_command_ends(self):
        v = self.open()
        v.set_tool("editobjects")
        objs = v.content_objects(0)
        v.select_objects(0, objs.items)
        self.w.start_cad_command("rotate")
        line = self.w.cad_line
        line.edit.setFocus()
        APP.processEvents()
        v._cad_cmd.cancel()
        APP.processEvents()
        self.assertFalse(line.isAncestorOf(QApplication.focusWidget()))
        self.assertEqual(line.cancel_btn.focusPolicy(), Qt.NoFocus)

    def test_a_command_ends_when_its_selection_changes_under_it(self):
        v = self.open()
        v.set_tool("editobjects")
        v.select_objects(0, v.content_objects(0).items)
        self.w.start_cad_command("move")
        self.assertIsNotNone(v._cad_cmd)
        v.delete_objects()
        APP.processEvents()
        self.assertIsNone(v._cad_cmd)

    def test_a_box_being_drawn_goes_with_a_change(self):
        v = self.open()
        w = v.pages[0]
        v._cad_pick = {"w": w, "at": pymupdf.Point(10, 10)}
        w._cad_down = {"ignore": True}
        v.modify(lambda: None, pages=[0])
        self.assertIsNone(v._cad_pick)
        self.assertIsNone(w._cad_down)


class Busy(unittest.TestCase):
    def test_no_busy_pointer_over_a_message_box(self):
        seen = []
        with mock.patch.object(QMessageBox, "warning",
                               lambda *a: seen.append(QApplication.overrideCursor())):
            with document_view._busy():
                with document_view._not_busy():
                    QMessageBox.warning(None, "x", "y")
                self.assertIsNotNone(QApplication.overrideCursor())
        self.assertEqual(seen, [None])
        self.assertIsNone(QApplication.overrideCursor())


if __name__ == "__main__":
    unittest.main()
