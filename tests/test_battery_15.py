"""What a break-it battery of 1.5 found, fixed: Enter finishes a polygon in CAD mode; the Hand
tool selects markups in every mode; the command line gives the keyboard back to the page;
Shift+letter shortcuts, form fields and Up / Down picks keep working; a CAD command ends with
its tab and with a mode change in any window; Update now closes every window first; the
setup's own uninstall entry says who it was installed for; manual and automatic update checks
don't mix; odd GitHub answers don't stop the check; notes without a closing mark don't eat the
next language; recovered files aren't opened twice; the backups folder is matched as a folder.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_battery_15
"""
import os
import sys
import tempfile
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402
from PySide6.QtCore import QEvent, Qt  # noqa: E402
from PySide6.QtGui import QKeyEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import cad_commands, main_window, mouse_modes, updates  # noqa: E402
from kanzonas.document_view import DocumentView  # noqa: E402

P = pymupdf.Point


def key(k, text="", mods=Qt.NoModifier):
    return QKeyEvent(QEvent.KeyPress, k, mods, text)


def a_pdf(n=1):
    d = pymupdf.open()
    for _ in range(n):
        d.new_page().draw_line((100, 100), (200, 100))
    path = os.path.join(tempfile.mkdtemp(), "t.pdf")
    d.save(path)
    return path


class Window(unittest.TestCase):
    def setUp(self):
        from kanzonas.main_window import MainWindow
        w = self.w = MainWindow()
        old = {k: w.settings.value(k) for k in ("mouse_mode", "mouse_before_cad", "start_tool",
                                                "shortcuts")}

        def back():
            for k, v in old.items():
                w.settings.setValue(k, v) if v is not None else w.settings.remove(k)
            mouse_modes.apply(w.settings)
        self.addCleanup(back)
        self.addCleanup(lambda: [setattr(x, "_close_confirmed", True) or x.close()
                                 for x in main_window.windows()])
        w.resize(1000, 800)
        w.show()
        APP.processEvents()

    def open(self, n=1):
        self.w.open_file(a_pdf(n))
        APP.processEvents()
        v = self.w.view()
        self.addCleanup(lambda: setattr(v, "dirty", False))
        return v

    def typing(self, obj, ev):
        with mock.patch.object(type(self.w), "isActiveWindow", lambda s: True), \
                mock.patch.object(QApplication, "focusWidget", lambda: obj):
            return self.w.cad_typing(obj, ev)


class Keys(Window):
    def test_enter_finishes_a_polygon_in_cad_mode(self):
        v = self.open()
        self.w.set_mouse_mode("cad")
        self.w.set_tool("polygon")
        v.pages[0]._poly = [v.pages[0].rect().center()]
        self.assertFalse(self.typing(v, key(Qt.Key_Return)))
        v.pages[0]._poly = []
        self.assertTrue(self.typing(v, key(Qt.Key_Return)))      # idle: repeat last

    def test_form_fields_keep_space_and_enter(self):
        v = self.open()
        self.w.set_mouse_mode("cad")
        v.field_focus = (0, 1)
        self.assertFalse(self.typing(v, key(Qt.Key_Return)))
        self.assertFalse(self.typing(v, key(Qt.Key_Space, " ")))
        v.field_focus = None

    def test_shift_letter_shortcuts_still_work(self):
        v = self.open()
        self.w.set_mouse_mode("cad")
        self.assertFalse(self.typing(v, key(Qt.Key_M, "M", Qt.ShiftModifier)))
        self.w.cad_command_line().edit.setText("fit")
        self.assertTrue(self.typing(v, key(Qt.Key_P, "P", Qt.ShiftModifier)))   # typing on
        self.w.cad_line.edit.clear()

    def test_up_down_pick_wins_over_a_cad_name(self):
        self.open()
        self.w.set_mouse_mode("cad")
        line = self.w.cad_command_line()
        line.edit.setText("m")
        line._suggest("m")
        self.assertGreater(line.list.count(), 1)
        line.eventFilter(line.edit, key(Qt.Key_Down))
        picked = line.list.currentItem().data(Qt.UserRole)
        self.assertNotEqual(picked, ("cad", "move"))
        self.assertEqual(line._pick("m"), picked)

    def test_the_page_gets_the_keyboard_back(self):
        v = self.open()
        self.w.set_mouse_mode("cad")
        v.select_objects(0, list(v.content_objects(0).items))
        line = self.w.cad_command_line()
        with mock.patch.object(cad_commands.CommandLine, "_back_to_page") as back:
            line.edit.setText("e")
            line.run()
        self.assertTrue(back.called)
        self.assertEqual(line.edit.text(), "")

    def test_a_link_click_or_double_click_starts_no_box(self):
        v = self.open()
        self.w.set_mouse_mode("cad")
        from kanzonas import cad_select
        w = v.pages[0]
        w._link_press = ("link", None)
        cad_select.press(w, mock.Mock(modifiers=lambda: Qt.NoModifier), w.rect().center(),
                         P(400, 400))
        w._link_press = None
        cad_select.release(w, None, w.rect().center())
        self.assertIsNone(v._cad_pick)
        v._cad_pick = {"w": w, "at": w.to_pdf(w.rect().center()), "now": w.rect().center(),
                       "remove": False}
        w.mouseDoubleClickEvent(mock.Mock(position=lambda: w.rect().center().toPointF(),
                                          button=lambda: Qt.LeftButton,
                                          modifiers=lambda: Qt.NoModifier))
        self.assertIsNone(v._cad_pick)


class Modes(Window):
    def test_the_hand_tool_selects_markups_in_every_mode(self):
        for m in ("standard", "cad", "hand"):
            self.w.set_mouse_mode(m)
            self.assertTrue(DocumentView.hand_selects, m)

    def test_a_mode_change_reaches_every_window(self):
        self.open(2)
        self.open(1)
        self.w.set_mouse_mode("standard")
        w2 = self.w.detach_tab(1)
        APP.processEvents()
        self.assertEqual(w2.tool, "select")
        self.w.set_mouse_mode("hand")
        self.assertEqual(w2.tool, "hand")
        self.assertEqual(w2.view().tool, "hand")

    def test_f11_goes_back_to_the_mode_of_before_1_5(self):
        self.w.settings.remove("mouse_before_cad")
        self.w.settings.setValue("start_tool", "select")
        self.w.settings.setValue("mouse_mode", "cad")
        self.w.set_mouse_mode("cad", toggle=True)
        self.assertEqual(mouse_modes.mode(self.w.settings), "standard")

    def test_a_cad_command_ends_with_its_tab(self):
        va = self.open()
        vb = self.open()
        self.w.set_mouse_mode("cad")
        self.w.tabs.setCurrentWidget(va)
        va.select_objects(0, list(va.content_objects(0).items))
        self.w.start_cad_command("rotate")
        self.assertIsNotNone(va._cad_cmd)
        self.w.tabs.setCurrentWidget(vb)
        self.assertIsNone(va._cad_cmd)
        self.assertIsNone(self.w.cad_line.command)
        vb.select_objects(0, list(vb.content_objects(0).items))
        self.w.start_cad_command("move")
        with mock.patch.object(self.w, "_confirm_close", lambda v: True):
            self.w.close_tab(self.w.tabs.indexOf(vb))
        self.assertIsNone(self.w.cad_line.command)

    def test_cad_copy_has_its_own_name_for_shortcuts_and_the_palette(self):
        acts = self.w._shortcut_actions()
        self.assertIs(acts["CAD Copy"], self.w.cad_actions["copy"])
        self.assertIsNot(acts["Copy"], self.w.cad_actions["copy"])

    def test_a_pre_1_5_f11_shortcut_carries_over(self):
        import json
        self.w.settings.setValue("shortcuts", json.dumps(
            {"CAD-style mouse (wheel zooms, hold wheel to pan)": "F9"}))
        self.w._apply_saved_shortcuts()
        self.assertEqual(self.w.a_cad_mouse.shortcut().toString(), "F9")

    def test_enter_repeats_a_command_run_from_the_palette(self):
        self.open()
        line = self.w.cad_command_line()
        from kanzonas.palette import Finder
        Finder(self.w).remember("Fit page")
        self.assertEqual(line.last, ("action", "Fit page"))

    def test_the_list_goes_with_the_bar_and_the_focus(self):
        self.open()
        self.w.set_mouse_mode("cad")
        line = self.w.cad_command_line()
        line.edit.setText("cl")
        line._suggest("cl")
        self.assertTrue(line.list.isVisible())
        self.w.set_mouse_mode("hand")
        self.assertFalse(line.list.isVisible())
        self.assertEqual(line.edit.text(), "")


class UpdateNow(Window):
    def test_update_from_a_pulled_out_window_asks_every_window_first(self):
        self.open()
        self.open()
        w2 = self.w.detach_tab(1)
        APP.processEvents()
        with mock.patch.object(type(self.w), "close", lambda s: False):
            self.assertFalse(w2._close_all_for_update())      # the main window said no

    def test_session_and_recovered_copies(self):
        self.assertTrue(main_window._inside("/x/Backups/a.pdf", "/x/Backups"))
        self.assertFalse(main_window._inside("/x/Backups 2026/a.pdf", "/x/Backups"))
        v = self.open()
        v.recovered = True
        import json
        old = self.w.settings.value("restore_session"), self.w.settings.value("session_files")
        self.addCleanup(lambda: [self.w.settings.setValue(k, x) for k, x in
                                 zip(("restore_session", "session_files"), old) if x is not None])
        self.w.settings.setValue("restore_session", "true")
        self.w.settings.setValue("session_files", json.dumps([v.path]))
        n = self.w.tabs.count()
        self.w.restore_session()
        self.assertEqual(self.w.tabs.count(), n)               # not opened a second time
        v.recovered = False


class Updates(unittest.TestCase):
    def test_who_it_was_installed_for_comes_from_the_setups_entry(self):
        where = {"hklm": None, "hkcu": None}

        class Key:
            def __init__(self, hive):
                self.hive = hive

            def __enter__(self):
                if where[self.hive] is None:
                    raise OSError
                return self

            def __exit__(self, *a):
                return False
        fake = types.SimpleNamespace(
            HKEY_LOCAL_MACHINE="hklm", HKEY_CURRENT_USER="hkcu", KEY_READ=1,
            KEY_WOW64_64KEY=0x100, KEY_WOW64_32KEY=0x200,
            OpenKey=lambda hive, path, res, access: Key(hive),
            QueryValueEx=lambda k, name: (where[k.hive], 1))
        with mock.patch.dict(sys.modules, {"winreg": fake}), \
                mock.patch.dict(os.environ, {"ProgramFiles": "/pf"}):
            where["hklm"] = "/apps/KanzonasPDF"                 # all users, custom folder
            self.assertTrue(updates.for_all_users("/apps/KanzonasPDF"))
            where.update(hklm=None, hkcu="/pf/KanzonasPDF")    # per user, odd folder
            self.assertFalse(updates.for_all_users("/pf/KanzonasPDF"))
            where.update(hkcu=None)                             # no entry: by the folder
            self.assertTrue(updates.for_all_users("/pf/KanzonasPDF"))

    def test_odd_answers_and_notes(self):
        rels = ["junk", {"tag_name": 99}, {"tag_name": "v99.1", "body": 5},
                {"tag_name": "v99.2", "body": "<!-- kanzonas-notes -->\nNew\n"
                 "<!-- kanzonas-notes lang=es -->\nNuevo\n<!-- /kanzonas-notes -->"}]
        self.assertEqual(updates.newest_release(rels)["tag_name"], "v99.2")
        got = updates.notes_since(rels, current="1.0", lang="es")
        self.assertEqual(got[0][1], "Nuevo")                    # not swallowed by the English
        self.assertEqual(updates.notes_since(rels, current="1.0")[0][1], "New")
        self.assertIsNone(updates._sha256_hex({"digest": "sha256:abc123"}))

    def test_a_manual_check_and_the_automatic_one_dont_mix(self):
        from PySide6.QtNetwork import QNetworkReply
        c = updates.UpdateChecker(mock.Mock(value=lambda *a: None, setValue=lambda *a: None))
        said = []
        c.result.connect(said.append)
        reply = mock.Mock()
        reply.error.return_value = QNetworkReply.HostNotFoundError
        reply.errorString.return_value = "offline"
        c.manual = False                                        # (another check meanwhile)
        c._done(reply, manual=True)
        self.assertTrue(said and "offline" in said[0])

    def test_unique_output_delimiter(self):
        from tools import release_notes
        out = os.path.join(tempfile.mkdtemp(), "out")
        with mock.patch.dict(os.environ, {"GITHUB_OUTPUT": out}):
            self.assertEqual(release_notes.main(["x", "1.5", "--github-output"]), 0)
        with open(out, encoding="utf-8") as f:
            text = f.read()
        end = text.split("<<", 1)[1].split("\n", 1)[0]
        self.assertTrue(end.startswith("KZ_NOTES_END_") and len(end) > 20)
        self.assertTrue(text.rstrip().endswith(end))

    def test_spanish_names_without_accents(self):
        self.assertEqual(cad_commands._plain("Simetría"), "simetria")


class CadCommands(unittest.TestCase):
    """The CAD tester's findings."""

    def view(self, build, tool="editobjects", rotation=0):
        for k in ("snap_objects", "snap_page", "snap_grid", "cad_select", "click_click"):
            self.addCleanup(setattr, DocumentView, k, getattr(DocumentView, k))
        DocumentView.snap_objects = DocumentView.snap_page = DocumentView.snap_grid = False
        d = pymupdf.open()
        p = d.new_page()
        build(p)
        if rotation:
            p.set_rotation(rotation)
        path = os.path.join(tempfile.mkdtemp(), "c.pdf")
        d.save(path)
        v = DocumentView(path)
        self.addCleanup(v.close_doc)
        v.resize(900, 1000)
        v.show()
        APP.processEvents()
        v.set_tool(tool)
        self.prompt = cad_commands.Prompt()
        self.addCleanup(self.prompt.deleteLater)
        return v

    def run_cmd(self, v, key, clicks=(), typed=None):
        cmd = cad_commands.COMMANDS[key](v, self.prompt)
        cmd.start()
        for pt in clicks:
            cmd.click(0, P(pt))
        if typed is not None:
            cmd.typed(typed)
        return cmd

    def line(self, p):
        p.draw_line((100, 100), (200, 100))

    def test_values_that_would_break_the_drawing_are_refused(self):
        v = self.view(self.line)
        v.select_objects(0, list(v.content_objects(0).items))
        before = v.doc[0].read_contents()
        for key, value in (("scale", "nan"), ("scale", "inf"), ("scale", "1e300"),
                           ("scale", "0.000001"), ("rotate", "nan"), ("rotate", "inf")):
            cmd = self.run_cmd(v, key, [(100, 100)], value)
            self.assertIs(v._cad_cmd, cmd, (key, value))           # still asking
            cmd.cancel()
        self.assertEqual(v.doc[0].read_contents(), before)
        self.assertEqual(cad_commands.number("90\u00b0"), 90)
        cmd = self.run_cmd(v, "scale", [(100, 100), (200, 100), (100, 100)])   # to nothing
        self.assertIs(v._cad_cmd, cmd)
        cmd.cancel()
        cmd = self.run_cmd(v, "align", [(100, 100), (300, 300), (200, 100), (300, 300)])
        cmd.choose("yes")                                       # both ends to one point
        self.assertIs(v._cad_cmd, cmd)
        cmd.cancel()
        self.assertEqual(v.doc[0].read_contents(), before)

    def test_trim_cuts_the_line_nearest_the_click_unsnapped(self):
        def build(p):
            p.draw_line((100, 100), (400, 100))
            p.draw_line((300, 50), (300, 150))
            p.draw_line((200, 50), (200, 150))
        DocumentView.snap_objects = True
        v = self.view(build)
        cmd = cad_commands.COMMANDS["trim"](v, self.prompt)
        self.assertFalse(cmd.snap)
        cmd.start()
        said = []
        v.statusMessage.connect(said.append)
        cmd.click(0, P(200, 100))                               # right on a crossing
        self.assertIn("lines cross", said[-1])
        cmd.click(0, P(298, 100))                               # just beside the crossing
        segs = sorted(tuple(sorted(((round(i[1].x), round(i[1].y)), (round(i[2].x),
                                                                       round(i[2].y)))))
                      for d in v.doc[0].get_drawings() for i in d["items"])
        self.assertIn(((300, 50), (300, 150)), segs)            # the plumb line is whole
        self.assertNotIn(((100, 100), (400, 100)), segs)        # the level one was cut

    def test_trim_leaves_hidden_and_locked_markups_alone(self):
        def build(p):
            a = p.add_line_annot((100, 100), (400, 100))
            a.set_flags(pymupdf.PDF_ANNOT_IS_LOCKED)
            a.update()
            b = p.add_line_annot((250, 50), (250, 150))
            b.set_flags(pymupdf.PDF_ANNOT_IS_HIDDEN)
            b.update()
        v = self.view(build, "select")
        cmd = self.run_cmd(v, "trim", [(300, 100)])
        page = v.doc[0]
        self.assertEqual(len(list(page.annots())), 2)
        locked = [a for a in page.annots() if a.flags & pymupdf.PDF_ANNOT_IS_LOCKED][0]
        self.assertEqual(round(locked.vertices[0][0]), 100)
        cmd.cancel()

    def test_rotate_by_a_click_on_a_turned_page(self):
        for rot in (90, 180, 270):
            v = self.view(self.line, rotation=rot)
            v.select_objects(0, list(v.content_objects(0).items))
            page = v.doc[0]
            rm = page.rotation_matrix
            base = P(100, 100)
            # a click straight above the base point as shown
            shown = base * rm + (0, -50)
            self.run_cmd(v, "rotate", [base, shown * page.derotation_matrix])
            objs = v.content_objects(0)
            line = objs.lines(objs.items[0])[0]                 # (the app's page points)
            a, b = line[0] * rm, line[-1] * rm
            far = b if abs(b - base * rm) > abs(a - base * rm) else a
            # as shown, the line turned a quarter counterclockwise: from "east" to the click
            # the way it was shown before (y grows downward on screen)
            u = P(200, 100) * rm - base * rm
            want = base * rm + P(u.y, -u.x)
            self.assertAlmostEqual(far.x, want.x, delta=0.5, msg=rot)
            self.assertAlmostEqual(far.y, want.y, delta=0.5, msg=rot)

    def test_mirror_keeps_stamps_and_text_upright_and_quarter_turns_turn_the_box(self):
        from kanzonas import annotations as A
        m = {"kind": "textbox", "rect": pymupdf.Rect(100, 100, 300, 140),
             "props": {"rotation": 0}, "text": "x"}
        mirrored = A.transformed(m, cad_commands.mirror(P(400, 0), P(400, 500)))
        self.assertEqual(A.angle(mirrored), 0)
        turned = A.transformed(m, cad_commands.rotation(P(200, 120), 90))
        self.assertEqual(A.angle(turned), 90)
        self.assertAlmostEqual(turned["rect"].width, 40, places=3)
        stamp = {"kind": "stamp", "rect": pymupdf.Rect(0, 0, 100, 30), "props": {"rotation": 0}}
        for line in ((P(50, 0), P(50, 10)), (P(0, 50), P(10, 50))):
            self.assertEqual(A.angle(A.transformed(stamp, cad_commands.mirror(*line))), 0)
        rect = {"kind": "rect", "rect": pymupdf.Rect(0, 0, 100, 30), "props": {"rotation": 0}}
        self.assertEqual(A.angle(A.transformed(rect, cad_commands.rotation(P(0, 0), 180))), 0)

    def test_a_started_box_survives_a_zoom_but_not_a_command(self):
        DocumentView.cad_select = DocumentView.click_click = True
        v = self.view(self.line)
        from kanzonas import cad_select
        w = v.pages[0]
        v._cad_pick = {"w": w, "at": P(90, 90), "now": w.rect().center(), "remove": False}
        v.set_zoom(v.zoom / 2)
        APP.processEvents()
        self.assertEqual(v._cad_pick["at"], P(90, 90))           # a page point: it stays
        v.select_objects(0, list(v.content_objects(0).items))
        self.run_cmd(v, "move")
        self.assertIsNone(v._cad_pick)
        v._cad_cmd.cancel()
        self.assertTrue(callable(cad_select.cancel))


if __name__ == "__main__":
    unittest.main()
