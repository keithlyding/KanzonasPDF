"""What the 1.5 battery found in settings, printing, exports and windows, fixed: one bad
stored setting no longer stops KanzonasPDF from starting or Preferences from opening;
printing follows the annotations' Print flag, shows its progress and can be canceled;
Combine files and Insert pages refuse a PDF that doesn't allow copying (unless its
permissions password is typed); a CSV that can't be written says so; Reset all to defaults
sticks; closing a pulled-out window asks about that window; View options and the theme stay
checked alike in every window; exporting pictures asks before replacing files; odd release
tags don't break the update check; '1,000%' in the zoom box is 1000%.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_battery_151_view
"""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402
from PySide6.QtCore import QByteArray, QSettings, QTimer  # noqa: E402
from PySide6.QtPrintSupport import QPrinter  # noqa: E402
from PySide6.QtWidgets import (QDialog, QFileDialog, QInputDialog, QMessageBox,  # noqa: E402
                               QProgressDialog, QPushButton)

from tests.test_battery_15 import APP, Window, a_pdf  # noqa: E402

from kanzonas import combine, main_window, paths, updates  # noqa: E402
from kanzonas.document_view import DocumentView  # noqa: E402
from kanzonas.print_dialog import PrintDialog, print_list  # noqa: E402


class StoredValues(unittest.TestCase):
    """The readers fall back to the default for a value of the wrong kind."""

    def setUp(self):
        self.st = QSettings(os.path.join(tempfile.mkdtemp(), "s.ini"), QSettings.IniFormat)

    def test_readers(self):
        st = self.st
        st.setValue("a", ["Smith", "John"])     # what author=Smith, John in an .ini reads as
        self.assertEqual(paths.stored_str(st, "a"), "Smith, John")
        st.setValue("t", "abc")
        self.assertEqual(paths.stored_str(st, "t", "system", ("system", "light", "dark")),
                         "system")
        st.setValue("t", -7)
        self.assertEqual(paths.stored_str(st, "t", "x"), "x")
        for bad in ("abc", "nan", "1e400", "99999999999999999999", ["1", "2"], QByteArray(b"x")):
            st.setValue("n", bad)
            self.assertEqual(paths.stored_int(st, "n", 5, 0, 60), 5, bad)
            self.assertEqual(paths.stored_float(st, "n", 0.5, 0.001, 10000), 0.5, bad)
        st.setValue("n", "7")
        self.assertEqual(paths.stored_int(st, "n", 5, 0, 60), 7)
        for bad in ("[]", "-1", "{", 3, ["a", "b"]):
            st.setValue("j", bad)
            self.assertEqual(paths.stored_json(st, "j", {}), {}, bad)
        st.setValue("j", '{"a": 1}')
        self.assertEqual(paths.stored_json(st, "j", {}), {"a": 1})
        st.setValue("g", "abc")
        self.assertIsNone(paths.stored_bytes(st, "g"))


BAD_SETTINGS = [("theme", "Dark"), ("theme", ["a", "b"]), ("geometry", "abc"),
                ("window_state", "x"), ("shortcuts", "[]"), ("tool_chest", "[1]"),
                ("tool_chest", '{"a": [1]}'), ("tool_defaults", "0"),
                ("tool_defaults", '{"rect": {"width": "abc"}, "line": 5}'),
                ("autosave_minutes", "99999999999"), ("backup_dir", ["D:\\b", "old"]),
                ("file_states", "[]"), ("file_states", '{"x": 5}'), ("session_files", "-1"),
                ("author", ["Smith", "John"]), ("grid_value", "abc"), ("grid_major", "abc"),
                ("grid_unit", ["a"]), ("align_ref", ["a"]), ("measure_unit", ["a"]),
                ("new_pdf_size", ["a"]), ("recent", -7), ("open_view", ["a"]),
                ("measure_decimals", "abc"), ("palette_recent", '[["x"]]'),
                ("security_presets", "[1]"), ("trusted_certs", "{")]


class BadSettings(unittest.TestCase):
    def test_one_bad_value_never_stops_start_up_or_preferences(self):
        st = paths.settings()
        pdf = a_pdf(2)
        for key, value in BAD_SETTINGS:
            with self.subTest(key=key, value=value):
                old = {k: st.value(k) for k in (key, "restore_session", "session_files")}

                def back(old=old):
                    for k, v in old.items():
                        st.setValue(k, v) if v is not None else st.remove(k)
                self.addCleanup(back)
                st.setValue("restore_session", "true")
                st.setValue("session_files", '["%s"]' % pdf.replace("\\", "\\\\"))
                st.setValue(key, value)
                w = main_window.MainWindow()
                try:
                    w.show()
                    w.restore_session()
                    w.open_file(pdf)
                    APP.processEvents()
                    with mock.patch.object(QDialog, "exec", lambda self: 1):
                        w.preferences()
                finally:
                    w._close_confirmed = True
                    for v in w._views():
                        v.dirty = False
                    w.close()
                    APP.processEvents()
                back()

    def test_the_last_line_of_defense_starts_with_default_settings(self):
        from kanzonas import __main__ as entry
        st = paths.settings()
        st.setValue("kz_test_marker", "1")
        real = main_window.MainWindow
        tries = []

        def build():
            tries.append(1)
            if len(tries) == 1:
                raise RuntimeError("a setting no reader expected")
            return real()
        folder = tempfile.mkdtemp()
        kept = {k: st.value(k) for k in st.allKeys()}

        def back():
            for k, v in kept.items():
                st.setValue(k, v)
        self.addCleanup(back)
        with mock.patch.object(entry, "MainWindow", build), \
                mock.patch.object(paths, "data_dir", lambda sub="": folder), \
                mock.patch.object(QMessageBox, "warning") as warned:
            win = entry._build_window(APP)
            APP.processEvents()
        self.addCleanup(lambda: (setattr(win, "_close_confirmed", True), win.close()))
        self.assertEqual(len(tries), 2)
        self.assertIsNone(st.value("kz_test_marker"))           # settings cleared
        with open(os.path.join(folder, "settings-before-reset.txt"), encoding="utf-8") as f:
            self.assertIn("kz_test_marker", f.read())            # ... and kept in a file
        self.assertTrue(os.path.exists(os.path.join(folder, "startup-errors.log")))
        warned.assert_called_once()


def flags_pdf():
    d = pymupdf.open()
    pg = d.new_page(width=612, height=792)
    for rect, rgb, flags in (((50, 50, 250, 250), (1, 0, 0), 0),          # screen only
                             ((300, 50, 500, 250), (0, 0, 1),            # print only
                              pymupdf.PDF_ANNOT_IS_PRINT | pymupdf.PDF_ANNOT_IS_NO_VIEW),
                             ((50, 400, 250, 600), (0, 0.6, 0), pymupdf.PDF_ANNOT_IS_PRINT)):
        a = pg.add_rect_annot(rect)
        a.set_colors(stroke=rgb)
        a.set_border(width=12)
        a.update()
        a.set_flags(flags)
    path = os.path.join(tempfile.mkdtemp(), "flags.pdf")
    d.save(path)
    return path


class Printing(unittest.TestCase):
    def setUp(self):
        self.v = DocumentView(flags_pdf())
        self.addCleanup(self.v.close_doc)

    def test_the_print_flag_decides_what_prints(self):
        page = self.v.doc[0]
        pix = print_list(page).get_pixmap()
        self.assertEqual(pix.pixel(55, 150), (255, 255, 255))      # no Print flag: not printed
        self.assertEqual(pix.pixel(305, 150)[2], 255)               # Print + NoView: printed
        self.assertGreater(pix.pixel(55, 500)[1], 100)              # Print: printed
        screen = page.get_pixmap()
        self.assertNotEqual(screen.pixel(55, 150), (255, 255, 255))  # the screen is unchanged
        self.assertEqual(screen.pixel(305, 150), (255, 255, 255))
        bare = print_list(page, markups=False).get_pixmap()
        self.assertEqual(bare.pixel(305, 150), (255, 255, 255))

    def printer(self, dlg):
        pr = dlg.printer
        pr.setOutputFormat(QPrinter.PdfFormat)
        pr.setOutputFileName(os.path.join(tempfile.mkdtemp(), "out.pdf"))
        return pr

    def test_the_window_responds_while_printing_and_cancel_stops_it(self):
        dlg = PrintDialog(None, self.v)
        ran = []
        QTimer.singleShot(0, lambda: ran.append(1))
        self.assertTrue(dlg.print_to(self.printer(dlg), [0]))
        self.assertTrue(ran)                    # the event loop ran during printing
        dlg = PrintDialog(None, self.v)
        pr = self.printer(dlg)
        # Cancel clicked while the first sheet prints: the job is dropped (a PDF "printer"
        # can't drop a job, a real one can: abort is what's asked)
        with mock.patch.object(QProgressDialog, "wasCanceled", side_effect=[False, True]), \
                mock.patch.object(QPrinter, "abort") as abort:
            self.assertFalse(dlg.print_to(pr, [0, 0]))
        abort.assert_called_once()
        self.assertEqual(pymupdf.open(pr.outputFileName()).page_count, 1)


def no_copy_pdf(folder):
    d = pymupdf.open()
    d.new_page().insert_text((72, 72), "SECRET", fontsize=20)
    path = os.path.join(folder, "nocopy.pdf")
    d.save(path, encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="o",
           permissions=pymupdf.PDF_PERM_PRINT)
    return path


class NoCopySources(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.src = no_copy_pdf(self.dir)
        self.plain = a_pdf(1)

    def test_combine_refuses_unless_the_permissions_password_is_given(self):
        out = os.path.join(self.dir, "out.pdf")
        with self.assertRaises(PermissionError) as cm:
            combine.combine([self.plain, self.src], out)
        self.assertIn("not allowed", str(cm.exception))
        self.assertFalse(os.path.exists(out))
        with self.assertRaises(PermissionError):
            combine.combine([self.src], out, ask_owner=lambda p: None)
        answers = iter(["wrong", "o"])
        self.assertEqual(combine.combine([self.plain, self.src], out,
                                         ask_owner=lambda p: next(answers)), 2)

    def test_insert_pages_refuses_too(self):
        doc = pymupdf.open(self.plain)
        with self.assertRaises(PermissionError):
            combine.insert_files(doc, [self.src], 0, (612, 792))
        self.assertEqual(doc.page_count, 1)
        with self.assertRaises(PermissionError):
            combine.owner_passwords([self.src], lambda p: None)
        owner = combine.owner_passwords([self.plain, self.src], lambda p: "o")
        self.assertEqual(owner, {self.src: "o"})
        combine.insert_files(doc, [self.src], 0, (612, 792), owner)
        self.assertEqual(doc.page_count, 2)


class Windows(Window):
    def test_a_csv_that_cant_be_written_says_so(self):
        self.open()
        self.w.a_markups.trigger()
        APP.processEvents()
        with mock.patch.object(QFileDialog, "getSaveFileName",
                               return_value=(tempfile.mkdtemp(), "")), \
                mock.patch.object(QMessageBox, "warning") as warned:
            self.w.markups.export_csv()
        warned.assert_called_once()
        from kanzonas.measure_ui import SummaryDialog
        dlg = SummaryDialog(self.w, self.w.view().doc)
        with mock.patch.object(QFileDialog, "getSaveFileName",
                               return_value=(tempfile.mkdtemp(), "")), \
                mock.patch.object(QMessageBox, "warning") as warned:
            dlg._export()
        warned.assert_called_once()

    def test_reset_all_to_defaults_sticks(self):
        w = self.w
        w.settings.setValue("shortcuts", '{"Print": "F2"}')
        w._apply_saved_shortcuts()
        self.assertEqual(w.a_print.shortcut().toString(), "F2")

        def press_reset(dlg):
            [b for b in dlg.findChildren(QPushButton) if b.text() == "Reset all to defaults"][0] \
                .click()
            return 0
        with mock.patch.object(QDialog, "exec", press_reset), \
                mock.patch.object(QMessageBox, "information"):
            w.edit_shortcuts()
        self.assertEqual(w.a_print.shortcut().toString(), "Ctrl+P")
        with mock.patch.object(QDialog, "exec", lambda dlg: 1):
            w.edit_shortcuts()                  # OK without changes keeps the defaults
        self.assertEqual(w.a_print.shortcut().toString(), "Ctrl+P")
        self.assertEqual(paths.stored_json(w.settings, "shortcuts", {}), {})

    def two_windows(self):
        self.open()
        self.open()
        w2 = self.w.detach_tab(1)
        APP.processEvents()
        return w2

    def test_closing_a_pulled_out_window_asks_about_that_window(self):
        w2 = self.two_windows()
        self.w.open_file(a_pdf(1))
        self.w.move_view(self.w.tabs.widget(1), w2)
        seen = []
        with mock.patch.object(QMessageBox, "exec",
                               lambda box: seen.append((box.windowTitle(), box.text())) or 0):
            self.assertEqual(w2._ask_exit(2, []), "cancel")
            self.w._ask_exit(2, [])
        self.assertEqual(seen[0][0], "Close window")
        self.assertIn("in this window", seen[0][1])
        self.assertNotIn("exit", seen[0][1])
        self.assertEqual(seen[1][0], "Close KanzonasPDF")

    def test_view_options_are_checked_alike_in_every_window(self):
        w, w2 = self.w, self.two_windows()
        old = {k: w.settings.value(k) for k in ("grid_on", "snap_grid", "comment_boxes",
                                                 "highlight_fields", "update_check",
                                                 "spell_check", "theme")}

        def back():
            for k, v in old.items():
                w.settings.setValue(k, v) if v is not None else w.settings.remove(k)
            from kanzonas import spelling
            spelling._state["enabled"] = None
        self.addCleanup(back)
        for name in ("a_grid", "a_snap_grid", "a_cards", "a_hl_fields", "a_show_markups",
                     "a_auto_updates", "a_spell"):
            for _ in range(2):
                getattr(w, name).trigger()
                APP.processEvents()
                self.assertEqual(getattr(w2, name).isChecked(), getattr(w, name).isChecked(),
                                 name)
        self.assertTrue(w2._views()[0].show_comment_boxes)
        theme = w.settings.value("theme") or "system"
        w.set_theme("dark")
        self.assertTrue(w2.theme_actions["dark"].isChecked())
        w.set_theme(theme)

    def test_exporting_pictures_asks_before_replacing_them(self):
        folder = tempfile.mkdtemp()
        self.w.open_file(a_pdf(2))
        APP.processEvents()
        mine = os.path.join(folder, "plan_p1.png")
        with open(mine, "wb") as f:
            f.write(b"mine")
        target = os.path.join(folder, "plan.png")
        with mock.patch.object(QFileDialog, "getSaveFileName", return_value=(target, "")), \
                mock.patch.object(QInputDialog, "getItem", return_value=("All pages", True)), \
                mock.patch.object(QMessageBox, "question", return_value=QMessageBox.No) as q:
            self.w.export_as("png")
        q.assert_called_once()
        with open(mine, "rb") as f:
            self.assertEqual(f.read(), b"mine")
        self.assertFalse(os.path.exists(os.path.join(folder, "plan_p2.png")))

    def test_the_zoom_box(self):
        v = self.open()
        for typed, zoom in (("1,000%", 10.0), ("25,5", 0.255), ("150 %", 1.5)):
            self.w.zoom_box.setEditText(typed)
            self.w._zoom_from_box()
            self.assertAlmostEqual(v.zoom, min(zoom, main_window.MAX_ZOOM), msg=typed)
        self.w.zoom_box.setEditText("25,5")
        self.w._zoom_from_box()
        self.assertEqual(self.w.zoom_box.currentText(), "25.5%")
        self.assertEqual(main_window.zoom_text(1.5), "150%")
        self.assertIsNone(main_window.parse_zoom("nan"))


class UpdateTags(unittest.TestCase):
    def test_odd_tags(self):
        self.assertIsNone(updates.newest([{"tag_name": "v1.5.0"}], "1.5"))
        self.assertIsNone(updates.newest([{"tag_name": "v1.5"}], "1.5.0"))
        self.assertEqual(updates.newest([{"tag_name": "v1.5.1"}], "1.5")[0], "1.5.1")
        self.assertIsNone(updates.newest([{"tag_name": "v" + "9" * 5000}], "1.5"))
        self.assertEqual(updates.newest([{"tag_name": "v9.0", "html_url": 7}], "1.5"),
                         ("9.0", updates.RELEASES_PAGE))
        self.assertEqual(updates.notes_since([{"tag_name": "v1.5.0"}], "1.5"), [])
        self.assertEqual(updates.version_tuple("v1.0-beta"), (1, 0))


if __name__ == "__main__":
    unittest.main()
