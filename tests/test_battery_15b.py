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


class OpenItems(unittest.TestCase):
    """The four left open after the second battery."""

    def test_a_page_is_read_a_little_at_a_time_to_the_same_result(self):
        d = pymupdf.open()
        p = d.new_page()
        sh = p.new_shape()
        for i in range(3000):
            sh.draw_line((i % 500, i // 10), (i % 500 + 5, i // 10 + 3))
            sh.finish()
        sh.commit()
        objs, steps = page_objects.Objects.steps(p)
        pauses = sum(1 for _ in steps)
        self.assertGreater(pauses, 5)
        whole = page_objects.Objects(p)
        self.assertEqual([(it["n"], tuple(it["rect"])) for it in objs.items],
                         [(it["n"], tuple(it["rect"])) for it in whole.items])

    def test_an_array_of_a_group_counts_what_it_draws(self):
        d = pymupdf.open()
        p = d.new_page()
        sh = p.new_shape()
        for i in range(50):
            sh.draw_line((i, 0), (i, 50))
            sh.finish()
        sh.commit()
        objs = page_objects.Objects(p)
        page_objects.block_copies(p, [it["n"] for it in objs.items],
                                  [pymupdf.Matrix(1, 0, 0, 1, 60 * k, 0) for k in range(1, 22)])
        g = [it for it in page_objects.Objects(p).items if it["kind"] == "group"][0]
        self.assertEqual(page_objects.group_size(d, g["xref"]), 50)

    def test_small_and_big_arrays_stack_the_same(self):
        pix = []
        for big in (False, True):
            d = pymupdf.open()
            p = d.new_page()
            p.draw_rect(pymupdf.Rect(10, 10, 60, 60), color=(0, 0, 1), fill=(1, 0, 0))
            p.draw_rect(pymupdf.Rect(40, 40, 90, 90), color=(0, 0, 0), fill=(0, 1, 0))
            mats = [pymupdf.Matrix(1, 0, 0, 1, 15 * k, 0) for k in range(1, 22)]
            make = page_objects.block_copies if big else page_objects.copies
            placed = {}
            make(p, [0, 1], mats, None, placed)
            self.assertEqual(placed["originals"], [0, 1])
            pix.append(p.get_pixmap(dpi=36).samples)
        self.assertEqual(pix[0], pix[1])

    def test_a_window_around_a_curve_takes_it(self):
        d = pymupdf.open()
        p = d.new_page()
        p.draw_bezier((100, 300), (150, 100), (250, 100), (300, 300))
        objs = page_objects.Objects(p)
        top = min(q.y for line in objs.lines(objs.items[0]) for q in line)
        win = pymupdf.Rect(90, top - 5, 310, 310)
        self.assertEqual(len(objs.pick(page_objects.Box(win))), 1)
        self.assertEqual(len(objs.inside(win)), 1)
        self.assertEqual(objs.pick(page_objects.Box(pymupdf.Rect(190, 120, 210, 140)), True), [])


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


class TypingOption(Window):
    def test_letters_can_stay_tool_shortcuts_in_cad_mode(self):
        from PySide6.QtCore import QEvent
        from PySide6.QtGui import QKeyEvent
        from kanzonas import mouse_modes
        from kanzonas.document_view import DocumentView
        v = self.open()
        self.w.set_mouse_mode("cad")
        ev = QKeyEvent(QEvent.KeyPress, Qt.Key_R, Qt.NoModifier, "r")
        self.assertTrue(self.typing(v, ev))                 # on: R goes to the command line
        mouse_modes.set_option(self.w.settings, "cad", "type_to_line", False)
        self.w.apply_mouse_mode()
        self.assertFalse(DocumentView.type_to_line)
        self.assertFalse(self.typing(v, ev))                # off: R is the Rectangle tool again
        self.w.settings.remove("mouse/cad/type_to_line")

    def test_who_had_the_cad_style_mouse_keeps_the_letter_shortcuts(self):
        class Settings(dict):
            def value(self, k, d=None):
                return self.get(k, d)

            def setValue(self, k, v):
                self[k] = v
        from kanzonas import mouse_modes
        old = Settings({"cad_mouse": "true"})               # a 1.4.2 user with F11 on
        self.assertEqual(mouse_modes.apply(old), "cad")
        self.assertFalse(mouse_modes.option(old, "cad", "type_to_line"))
        new = Settings({"mouse_mode": "cad"})               # chose CAD mode in 1.5
        mouse_modes.apply(new)
        self.assertTrue(mouse_modes.option(new, "cad", "type_to_line"))
        mouse_modes.apply(self.w.settings)


class GoTo(Window):
    def test_view_go_to_commands_and_home_end(self):
        from PySide6.QtCore import QEvent
        from PySide6.QtGui import QKeyEvent
        v = self.open(5)
        w = self.w

        def at():
            APP.processEvents()
            return v.current_page()
        w.a_last_page.trigger()
        self.assertEqual(at(), 4)
        w.a_prev_page.trigger()
        self.assertEqual(at(), 3)
        w.a_first_page.trigger()
        self.assertEqual(at(), 0)
        w.a_next_page.trigger()
        self.assertEqual(at(), 1)
        v.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_End, Qt.NoModifier))
        self.assertEqual(at(), 4)
        v.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Home, Qt.NoModifier))
        self.assertEqual(at(), 0)
        w._update_ui()
        self.assertFalse(w.a_prev_page.isEnabled())
        self.assertTrue(w.a_next_page.isEnabled())

    def test_the_command_line_finds_them(self):
        self.open(5)
        line = self.w.cad_command_line()
        self.assertEqual(line._pick("last page"), ("action", "Last page"))
        self.assertEqual(line._pick("next page"), ("action", "Next page"))


class CadTab(Window):
    def test_the_cad_tab_has_what_cad_mode_needs_most(self):
        from PySide6.QtWidgets import QToolButton
        self.open()
        self.w.set_mouse_mode("cad")
        tab = self.w._cad_tab
        on_tab = {b.defaultAction() for b in tab.findChildren(QToolButton) if b.defaultAction()}
        t, A_ = self.w.tool_actions, self.w.arrange_actions
        wanted = [t[k] for k in ("cloud", "textbox", "callout", "line", "arrow", "polyline",
                                 "m_length", "m_area", "m_count", "m_calibrate",
                                 "erasecontent")] + \
            [self.w.a_snap_objects, self.w.a_snap_grid, self.w.a_snap_page, A_["z_front"],
             A_["z_back"]] + [self.w.cad_actions[k] for k in ("move", "trim")]
        self.assertEqual([a.text() for a in wanted if a not in on_tab], [])


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
