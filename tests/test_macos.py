"""KanzonasPDF on macOS (sys.platform "darwin", pretended here on any computer): PDFs Finder
opens (QFileOpenEvent) reach the window; About, Preferences and Quit are in the application
menu and nothing else is moved there; Quit is Command-Q and closes every window; Replace
text leaves Command-H to macOS; tool tips and the manual's shortcut table say Cmd and
Option; the fonts are looked for in the Mac's font folders; settings and the theme say
"system", not "Windows"; the app never replaces itself (Download names the disk image, which
is for Apple silicon only: an Intel Mac is told there's none yet); the self-test reads the
Mac's peak memory in bytes. Windows and Linux keep their own ways (checked where it matters).

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_macos
"""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QUrl  # noqa: E402
from PySide6.QtGui import QAction, QFileOpenEvent, QKeySequence  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog, QLabel  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import macos, manual, manual_es, manual_it, text_edit, updates  # noqa: E402


def mac():
    return mock.patch.object(sys, "platform", "darwin")


def window(platform):
    """A main window built as on platform (closed when the test ends)."""
    from kanzonas.main_window import MainWindow
    with mock.patch.object(sys, "platform", platform):
        w = MainWindow()
    return w


def close(w):
    w._close_confirmed = True
    w.close()


class Keys(unittest.TestCase):
    def test_shortcuts_as_a_mac_shows_them(self):
        k = macos.mac_keys
        self.assertEqual(k("Ctrl+K"), "⌘K")
        self.assertEqual(k("Preferences (Ctrl+K)"), "Preferences (⌘K)")
        self.assertEqual(k("Ctrl+Shift+H"), "⇧⌘H")
        self.assertEqual(k("Ctrl+Alt+F"), "⌥⌘F")
        self.assertEqual(k("Move page up (Ctrl+Shift+Up)"), "Move page up (⇧⌘↑)")
        self.assertEqual(k("Ctrl+Shift+]"), "⇧⌘]")
        self.assertEqual(k("Ctrl+;"), "⌘;")
        self.assertEqual(k("Ctrl+F1"), "⌘F1")
        self.assertEqual(k("Ctrl+Shift+Plus"), "⇧⌘+")

    def test_mouse_actions_and_words(self):
        k = macos.mac_keys
        self.assertEqual(k("Ctrl+click to open"), "Cmd+click to open")
        self.assertEqual(k("Alt+click edits a single line"), "Option+click edits a single line")
        self.assertEqual(k("Ctrl+wheel"), "Cmd+wheel")
        self.assertEqual(k("Ctrl+Z undoes it."), "⌘Z undoes it.")

    def test_keys_without_ctrl_or_alt_stay(self):
        k = macos.mac_keys
        for text in ("Shift+T", "F1", "Shift+Enter or Shift+F3 = previous", "V / H",
                     "Escape", "Delete"):
            self.assertEqual(k(text), text)

    def test_in_words(self):
        k = macos.mac_keys
        self.assertEqual(k("Ctrl+Shift+H / U / X", symbols=False), "Cmd+Shift+H / U / X")
        self.assertEqual(k("Ctrl+Alt+F", symbols=False), "Cmd+Option+F")
        self.assertEqual(k("Alt+Up", symbols=False, option="Opción"), "Opción+Up")


class Pieces(unittest.TestCase):
    def test_the_disk_image_for_this_kind_of_mac(self):
        # (Apple silicon only: one disk image, none for Intel Macs)
        self.assertEqual(macos.DMG, "KanzonasPDF-macos-arm64.dmg")
        self.assertFalse(macos.intel("arm64"))
        self.assertFalse(macos.intel("aarch64"))
        self.assertTrue(macos.intel("x86_64"))

    def test_a_pdfs_helvetica_is_written_with_the_built_in_one(self):
        # (a Mac has Helvetica, Times and Courier installed; Windows and Linux use the
        # built-in ones because they have none: the same on a Mac)
        import pymupdf
        font = None
        for d in text_edit.font_dirs():
            for f in text_edit._font_files(d) if os.path.isdir(d) else []:
                if f.lower().endswith(".ttf"):
                    try:
                        ok = all(pymupdf.Font(fontfile=f).has_glyph(ord(c)) for c in "Hello")
                    except Exception:
                        ok = False
                    if ok:
                        font = f
                        break
            if font:
                break
        if not font:
            self.skipTest("no TrueType font installed")
        doc = pymupdf.open()
        page = doc.new_page()
        span = {"font": "Helvetica-Bold", "flags": 16, "size": 12}
        with mock.patch.object(text_edit, "_system_fonts", lambda: {"helveticabold": font}):
            with mac():
                self.assertIsNone(text_edit._system_font(page, span, "Hello"))
            with mock.patch.object(sys, "platform", "linux"):
                found = text_edit._system_font(page, span, "Hello")
        self.assertIsNotNone(found)                 # (an installed font of that name is used)

    @unittest.skipIf(os.name == "nt", "Mac paths (Windows keeps its own fonts folders)")
    def test_fonts_in_the_macs_font_folders(self):
        with mac():
            dirs = text_edit.font_dirs()
        self.assertEqual(dirs, ["/System/Library/Fonts", "/Library/Fonts",
                                os.path.expanduser("~/Library/Fonts")])
        if os.name != "nt":
            with mock.patch.object(sys, "platform", "linux"):
                self.assertNotIn("/System/Library/Fonts", text_edit.font_dirs())

    def test_the_single_instance_name_is_in_the_users_temporary_folder(self):
        # (no XDG_RUNTIME_DIR on a Mac: Qt puts a plain name in $TMPDIR, the user's own)
        from kanzonas.__main__ import instance_name
        with mac(), mock.patch.dict(os.environ, {"XDG_RUNTIME_DIR": ""}):
            self.assertEqual(instance_name("KanzonasPDF", "me"), "KanzonasPDF-me")

    @unittest.skipIf(os.name == "nt", "no resource module on Windows")
    def test_peak_memory_is_in_bytes_on_a_mac(self):
        from kanzonas import selftest
        usage = mock.Mock(ru_maxrss=300 * 1024 * 1024)
        import ctypes
        with mock.patch("resource.getrusage", lambda who: usage), \
                mock.patch.object(ctypes, "windll", None, create=True):
            with mac():
                self.assertAlmostEqual(selftest._memory_mb(), 300.0)
            if os.name != "nt":
                usage.ru_maxrss = 300 * 1024            # (Linux: kilobytes)
                with mock.patch.object(sys, "platform", "linux"):
                    self.assertAlmostEqual(selftest._memory_mb(), 300.0)


class FinderOpens(unittest.TestCase):
    def test_a_file_open_event_hands_the_file_over(self):
        got = []
        f = macos.file_open_filter(got.extend)
        APP.installEventFilter(f)
        self.addCleanup(APP.removeEventFilter, f)
        path = os.path.join(tempfile.gettempdir(), "plan.pdf")
        QApplication.sendEvent(APP, QFileOpenEvent(path))
        self.assertEqual(got, [os.path.abspath(path)])
        QApplication.sendEvent(APP, QFileOpenEvent(QUrl.fromLocalFile(path)))
        self.assertEqual(got, [os.path.abspath(path)] * 2)
        # other events go on as before
        self.assertFalse(f.eventFilter(APP, QEvent(QEvent.Type.ApplicationActivate)))

    def test_main_listens_for_them_on_a_mac_only(self):
        import inspect
        from kanzonas import __main__
        src = inspect.getsource(__main__.main)
        self.assertIn('if sys.platform == "darwin":', src)
        self.assertIn("app.installEventFilter(macos.file_open_filter(deliver, app))", src)
        # (installed before the event loop starts: the files a launch from Finder brings come
        # as events once it runs, and wait for the window like files handed over early)
        self.assertLess(src.index("macos.file_open_filter"), src.index("app.exec()"))
        self.assertLess(src.index("macos.file_open_filter"), src.index("_build_window(app)"))


class ApplicationMenu(unittest.TestCase):
    def test_about_preferences_and_quit_and_nothing_else(self):
        w = window("darwin")
        self.addCleanup(close, w)
        R = QAction.MenuRole
        self.assertEqual(w.a_about.menuRole(), R.AboutRole)
        self.assertEqual(w.a_prefs.menuRole(), R.PreferencesRole)
        self.assertEqual(w.a_exit.menuRole(), R.QuitRole)
        others = [a for a in macos.menu_bar_actions(w)
                  if a not in (w.a_about, w.a_prefs, w.a_exit)]
        self.assertGreater(len(others), 100)
        self.assertEqual({a.menuRole() for a in others}, {R.NoRole})
        # the group buttons keep the tip that lists their tools
        self.assertIn("ellipse", w.shapes_btn.toolTip())

    def test_mac_keys_for_quit_and_replace(self):
        w = window("darwin")
        self.addCleanup(close, w)
        self.assertEqual(w.a_exit.shortcut(), QKeySequence(QKeySequence.Quit))
        self.assertEqual(w.a_replace.shortcut(), QKeySequence("Ctrl+Alt+F"))
        self.assertNotIn("Ctrl+H", w.a_replace.toolTip())
        # nothing else uses Command-Option-F
        same = [a for a in w.findChildren(QAction)
                if a is not w.a_replace and a.shortcut() == QKeySequence("Ctrl+Alt+F")]
        self.assertEqual(same, [])

    def test_quit_closes_the_primary_window_from_any_window(self):
        w = window("darwin")
        self.addCleanup(close, w)
        with mock.patch.object(type(w), "close") as c:
            w._quit_all()
        self.assertTrue(c.called)

    def test_tool_tips_say_command(self):
        w = window("darwin")
        self.addCleanup(close, w)
        with mac():
            w._refresh_tips()
        tip = w.a_prefs.toolTip()
        self.assertIn("⌘K", tip)
        self.assertNotIn("Ctrl+", tip)
        self.assertIn("⌥⌘F", w.a_replace.toolTip())
        self.assertEqual([a.toolTip() for a in w.findChildren(QAction)
                          if "Ctrl+" in a.toolTip()], [])
        # (and again: the tips don't change once they're right)
        before = {id(a): a.toolTip() for a in w.findChildren(QAction)}
        with mac():
            w._refresh_tips()
        self.assertEqual(before, {id(a): a.toolTip() for a in w.findChildren(QAction)})

    def test_the_menu_bar_is_always_there(self):
        w = window("darwin")
        self.addCleanup(close, w)
        self.assertFalse(w.a_menu_bar.isVisible())
        w.a_menu_bar.setChecked(False)
        with mac():
            w._apply_ui_mode()
        self.assertFalse(w.menu_btn.isVisibleTo(w))

    def test_text_style_buttons_say_command(self):
        # (Edit text's style buttons, text_styles: their tips aren't menu commands')
        from kanzonas.inline_editor import StyleBar
        editor = mock.Mock()
        editor.parentWidget.return_value = None
        with mac():
            bar = StyleBar(editor)
        self.addCleanup(bar.deleteLater)
        tips = {k: b.toolTip() for k, b in bar.buttons.items()}
        self.assertEqual(tips["bold"], "Bold (⌘B)")
        self.assertEqual(tips["larger"], "Larger text (⌘])")
        self.assertEqual([t for t in tips.values() if "Ctrl+" in t], [])

    @unittest.skipIf(sys.platform == "darwin", "Windows and Linux keep their own")
    def test_windows_and_linux_keep_theirs(self):
        w = window(sys.platform)
        self.addCleanup(close, w)
        self.assertEqual(w.a_exit.shortcut(), QKeySequence("Alt+F4"))
        self.assertEqual(w.a_replace.shortcut(), QKeySequence("Ctrl+H"))
        self.assertIn("(Ctrl+H)", w.a_replace.toolTip())
        self.assertEqual(w.a_about.menuRole(), QAction.MenuRole.TextHeuristicRole)
        self.assertTrue(w.a_menu_bar.isVisible())
        self.assertIn("Ctrl+K", w.a_prefs.toolTip())


class PreferencesOnAMac(unittest.TestCase):
    def test_system_words_and_no_menu_bar_option(self):
        from kanzonas.preferences import PreferencesDialog
        w = window("darwin")
        self.addCleanup(close, w)
        with mac():
            dlg = PreferencesDialog(w)
        self.addCleanup(dlg.deleteLater)
        self.assertEqual(dlg.theme.itemText(0), "Match system")
        self.assertEqual(dlg.language.itemText(0), "Automatic (the language of the system)")
        self.assertIsNone(dlg.desktop)                  # (Linux's applications menu option)
        texts = [b.text() for b, _a in dlg._boxes]
        self.assertNotIn(w.a_menu_bar.text(), texts)
        labels = " ".join(lab.text() for lab in dlg.findChildren(QLabel))
        self.assertIn("Settings are saved in", labels)
        self.assertNotIn("Windows user profile", labels)


class Updates(unittest.TestCase):
    def test_the_app_never_replaces_itself(self):
        with mac(), mock.patch.object(sys, "frozen", True, create=True), \
                mock.patch.dict(os.environ, {"APPIMAGE": sys.executable}):
            self.assertFalse(updates.can_self_update())
            self.assertFalse(updates.can_install_update())
            self.assertFalse(updates.can_update_appimage())

    def update_box_text(self, machine):
        w = window("darwin")
        self.addCleanup(close, w)
        w._upd = mock.Mock(release={"tag_name": "v99"}, releases=[], manual=True)
        shown = []

        def fake_exec(dlg):
            shown.append(" ".join(lab.text() for lab in dlg.findChildren(QLabel)))
            return 0
        with mac(), mock.patch.object(QDialog, "exec", fake_exec), \
                mock.patch.object(macos.platform, "machine", lambda: machine):
            self.assertIsNone(w._self_update_url())
            w._update_box("99", "https://github.com/x/releases/tag/v99")
        self.assertNotIn("Update now", shown[0])
        return shown[0]

    def test_download_names_the_disk_image(self):
        text = self.update_box_text("arm64")
        self.assertIn("KanzonasPDF-macos-arm64.dmg", text)
        self.assertNotIn("Intel", text)

    def test_an_intel_mac_isnt_offered_a_download_that_cant_run(self):
        # (run from source, or Intel code run by Rosetta 2: the disk image is Apple silicon's)
        text = self.update_box_text("x86_64")
        self.assertNotIn(".dmg", text)
        self.assertIn("no version for Intel Macs yet", text)


class Manual(unittest.TestCase):
    def table(self, html):
        start = html.index('<h2 id="shortcuts">')
        return html[start:html.index("</table>", start)]

    def test_the_shortcut_table_with_the_macs_keys(self):
        t = self.table(manual.for_mac(manual.MANUAL))
        self.assertNotIn("Ctrl+", t)
        self.assertNotIn("Alt+", t)
        self.assertIn("<td>Cmd+E</td>", t)
        self.assertIn("<td>Cmd+Option+F</td><td>Replace text</td>", t)
        self.assertIn("<td>Cmd+Q</td><td>Quit (KanzonasPDF menu)</td>", t)
        self.assertIn("<td>Cmd+Shift+H / U / X</td>", t)
        self.assertIn("<td>Option (while drawing or dragging)</td>", t)
        self.assertIn("Option+click", t)
        self.assertNotIn("menu bar", t)
        # the rest of the manual is the same
        rest = manual.for_mac(manual.MANUAL).replace(t, "")
        self.assertEqual(rest, manual.MANUAL.replace(self.table(manual.MANUAL), ""))

    def test_in_spanish(self):
        t = self.table(manual.for_mac(manual_es.MANUAL, "es"))
        self.assertNotIn("Ctrl+", t)
        self.assertIn("Opción", t)
        self.assertIn("<td>Cmd+Q</td><td>Salir (menú KanzonasPDF)</td>", t)
        self.assertIn("<td>Cmd+Option+F</td>".replace("Option", "Opción"), t)

    def test_in_italian(self):
        t = self.table(manual.for_mac(manual_it.MANUAL, "it"))
        self.assertNotIn("Ctrl+", t)
        self.assertIn("Opzione", t)
        self.assertIn("<td>Cmd+Q</td><td>Esci (menu KanzonasPDF)</td>", t)
        self.assertIn("<td>Cmd+Opzione+F</td>", t)

    def test_shown_on_a_mac_only(self):
        with mac():
            self.assertIn("<td>Cmd+Q</td>", manual.manual_html())
        if sys.platform != "darwin":
            self.assertIs(manual.manual_html(), manual.MANUAL)

    def test_the_mac_chapter(self):
        for html in (manual.MANUAL, manual_es.MANUAL, manual_it.MANUAL):
            start = html.index('<h2 id="macos">')
            chapter = html[start:html.index("<h2", start + 5)]
            self.assertNotIn("x86_64.dmg", chapter)
            self.assertIn("Intel", chapter)                 # (says there's none yet)
            for word in ("KanzonasPDF-macos-arm64.dmg", "Apple silicon", "14.4",
                         "shasum -a 256", "~/Library/Fonts",
                         "com.kanzonaspdf.KanzonasPDF.plist"):
                self.assertIn(word, chapter)
        self.assertIn("Open Anyway", manual.MANUAL)
        self.assertIn("Abrir igualmente", manual_es.MANUAL)
        self.assertIn("Apri comunque", manual_it.MANUAL)


if __name__ == "__main__":
    unittest.main()
