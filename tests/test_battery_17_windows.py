"""1.7 added Linux; Windows must work exactly as in 1.6.3. Each Linux change is behind a
platform check: these tests take the Windows side of every one (sys.platform "win32",
os.name "nt", Windows paths) where that can be done without Windows itself, and compare it
with what 1.6.3 did: the files from the command line, the one-window hand-over and its pipe
name, the update ways and their texts, the font folders, the Windows wording in the menus and
Preferences (in English and Spanish, and in the manual), and the Windows build in the
workflow (same PyInstaller command line, steps and release files). A few run only on Windows.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_battery_17_windows
"""
import ntpath
import os
import re
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import __main__ as entry  # noqa: E402
from kanzonas import i18n, text_edit, updates  # noqa: E402

try:
    import yaml
except ImportError:                     # pragma: no cover
    yaml = None

WINDOWS = os.name == "nt"
WORKFLOW = os.path.join(ROOT, ".github", "workflows", "build-windows.yml")


class SysAs:
    """The sys module as a module sees it, with another platform (the rest is the real one)."""

    def __init__(self, platform, argv=None):
        self.platform = platform
        if argv is not None:
            self.argv = argv

    def __getattr__(self, name):
        return getattr(sys, name)


def os_with_ntpath():
    """os as kanzonas.__main__ sees it on Windows: Windows paths."""
    return types.SimpleNamespace(path=ntpath, environ=os.environ, name="nt")


class CommandLine(unittest.TestCase):
    """The files Explorer (or a shortcut, or a command) hands KanzonasPDF.exe."""

    ARGS = [r"C:\Docs\plan.pdf", r"\\server\share\drawings\A-101.pdf", r"C:\a b\c d.pdf",
            r"D:relative.pdf", r"C:\Docs\..\Docs\x.PDF", "--reset-settings", r"C:\x.pdf",
            "//server/share/y.pdf", r"\\?\C:\long\path.pdf"]

    def test_windows_paths_are_taken_as_in_1_6_3(self):
        old = [ntpath.abspath(p) for p in self.ARGS if not p.startswith("--")]   # (1.6.3)
        with mock.patch.object(entry, "os", os_with_ntpath()):
            self.assertEqual(entry.file_arguments(self.ARGS), old)
        with mock.patch.object(entry, "os", os_with_ntpath()):
            got = entry.file_arguments([r"\\server\share\x.pdf", r"C:\x.pdf"])
        self.assertEqual(got, [r"\\server\share\x.pdf", r"C:\x.pdf"])

    @unittest.skipUnless(WINDOWS, "Qt's file addresses with drive letters (Windows)")
    def test_file_addresses_on_windows(self):
        got = entry.file_arguments(["file:///C:/Docs/My%20Plan.pdf",
                                    "file://server/share/x.pdf"])
        self.assertEqual(got, [r"C:\Docs\My Plan.pdf", r"\\server\share\x.pdf"])


class OneWindow(unittest.TestCase):
    """The single-instance pipe and the hand-over, Windows side."""

    def test_the_pipe_name_is_as_in_1_6_3(self):
        run = tempfile.mkdtemp()
        with mock.patch.object(entry, "sys", SysAs("win32")), \
                mock.patch.dict(os.environ, {"XDG_RUNTIME_DIR": run}):
            self.assertEqual(entry.instance_name("KanzonasPDF", "Ana"), "KanzonasPDF-Ana")

    def test_lock_file_and_server_as_in_1_6_3(self):
        import uuid
        from PySide6.QtCore import QDir
        from PySide6 import QtCore, QtNetwork
        name = "KanzonasPDF-kzwin" + uuid.uuid4().hex[:8]
        locks, options, removed = [], [], []
        real_lock, real_server = QtCore.QLockFile, QtNetwork.QLocalServer

        def lock_file(path):
            locks.append(path)
            return real_lock(path)

        class Server(real_server):
            def setSocketOptions(self, o):
                options.append(o)
                return super().setSocketOptions(o)

            @staticmethod
            def removeServer(n):
                removed.append(n)
                return real_server.removeServer(n)

        with mock.patch.object(entry, "sys", SysAs("win32")), \
                mock.patch.object(QtCore, "QLockFile", lock_file), \
                mock.patch.object(QtNetwork, "QLocalServer", Server):
            server, sock = entry.first_instance(name)
        try:
            self.assertIsNotNone(server)
            self.assertIsNone(sock)
            self.assertEqual(locks, [os.path.join(QDir.tempPath(), name + ".lock")])
            self.assertEqual(options, [])           # (the Windows pipe: Qt's own access)
            self.assertEqual(removed, [])           # (never takes a Windows name over)
        finally:
            server.close()

    def run_main(self, first, argv, env=None):
        """main() as on Windows, with a stand-in application; what it did."""
        did = types.SimpleNamespace(app=None, timers=[], sigterm=[], win=mock.MagicMock())

        class App:
            def __init__(self, args):
                did.app = self
                self.calls = []
                self.commitDataRequest = mock.Mock()

            def __getattr__(self, name):
                return lambda *a: self.calls.append((name,) + a)

            def exec(self):
                return 0

        timer = mock.Mock()
        timer.singleShot = lambda ms, fn: did.timers.append(fn)
        with mock.patch.object(entry, "sys", SysAs("win32", argv)), \
                mock.patch.object(entry, "QApplication", App), \
                mock.patch.object(entry, "QTimer", timer), \
                mock.patch.object(entry, "first_instance", lambda name: first(name)), \
                mock.patch.object(entry, "_build_window", lambda app: did.win), \
                mock.patch.object(entry, "end_on_sigterm",
                                  lambda *a: did.sigterm.append(a)), \
                mock.patch("kanzonas.theme.apply"), mock.patch("kanzonas.i18n.install_qt"), \
                mock.patch("kanzonas.spelling.load_soon"), \
                mock.patch.dict(os.environ, env or {}):
            try:
                entry.main()
            except SystemExit:
                pass
        return did

    def test_hand_over_writes_what_1_6_3_wrote(self):
        sock = mock.Mock()
        written = []
        sock.write = lambda b: written.append(bytes(b))
        names = []
        path = os.path.abspath("plan.pdf")
        with mock.patch("kanzonas.winfocus.allow_foreground") as allow, \
                mock.patch("kanzonas.winfocus.front_from_reply") as front:
            did = self.run_main(lambda n: (names.append(n), (None, sock))[1],
                                ["KanzonasPDF.exe", "plan.pdf"],
                                {"XDG_ACTIVATION_TOKEN": "not-on-windows"})
        self.assertEqual(written, [(path + "\n").encode("utf-8")])     # no other line
        self.assertTrue(allow.called)
        self.assertTrue(front.called)
        self.assertTrue(sock.disconnectFromServer.called)
        import getpass
        self.assertEqual(names, ["KanzonasPDF-" + getpass.getuser()])
        self.assertNotIn(("setDesktopFileName", "kanzonaspdf"), did.app.calls)

    def test_the_first_one_on_windows(self):
        server = mock.Mock()
        handlers = {}
        server.newConnection.connect = lambda fn: handlers.setdefault("incoming", fn)
        with mock.patch.dict(os.environ, {}):
            os.environ.pop("XDG_ACTIVATION_TOKEN", None)
            did = self.run_main(lambda n: (server, None), ["KanzonasPDF.exe"])
            names = [c[0] for c in did.app.calls]
            self.assertNotIn("setDesktopFileName", names)
            self.assertEqual(did.sigterm, [])                         # no SIGTERM handler
            self.assertNotIn(entry._refresh_menu_entry, did.timers)   # no menu entry
            self.assertIn(did.win.start_update_check, did.timers)
            did.app.commitDataRequest.connect.assert_called_with(did.win.windows_ending)
            # a file handed over: opened; a line like Linux's activation token is no file
            conn = mock.Mock()
            conn.readAll.return_value = b"XDG_ACTIVATION_TOKEN=x\nC:\\x.pdf\n"
            conn.readyRead.connect = lambda fn: handlers.setdefault("read", fn)
            server.hasPendingConnections.side_effect = [True, False]
            server.nextPendingConnection.return_value = conn
            with mock.patch("kanzonas.winfocus.bring_to_front") as front, \
                    mock.patch.object(entry, "sys", SysAs("win32")):
                handlers["incoming"]()
                handlers["read"]()
            front.assert_called_once_with(did.win)
            self.assertNotIn("XDG_ACTIVATION_TOKEN", os.environ)    # (only Linux uses it)
        did.win.open_file.assert_called_once_with("C:\\x.pdf")


class Updates(unittest.TestCase):
    """Update now on Windows: the portable zip or the setup, never the AppImage."""

    def setUp(self):
        d = tempfile.mkdtemp()
        self.appimage = os.path.join(d, updates.APPIMAGE)
        with open(self.appimage, "wb") as f:
            f.write(b"\x7fELF\x02\x01\x01\x00AI\x02")
        self.patches = [mock.patch.object(updates.os, "name", "nt"),
                        mock.patch.object(sys, "platform", "win32"),
                        mock.patch.object(sys, "frozen", True, create=True),
                        mock.patch.dict(os.environ, {"APPIMAGE": self.appimage})]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)

    def release(self):
        assets = [{"name": n, "browser_download_url":
                   "https://github.com/keithlyding/KanzonasPDF/releases/download/v9.9/" + n,
                   "digest": "sha256:" + "ab" * 32}
                  for n in (updates.PORTABLE_ZIP, updates.setup_name("9.9"), updates.APPIMAGE)]
        return {"tag_name": "v9.9", "assets": assets}

    def window(self):
        from kanzonas.main_window import MainWindow
        w = types.SimpleNamespace(_upd=types.SimpleNamespace(release=self.release()))
        for name in ("_self_update_url", "_new_version", "_update_now_text", "update_now"):
            setattr(w, name, types.MethodType(getattr(MainWindow, name), w))
        w.update_portable, w.update_installed, w.update_appimage = (mock.Mock(), mock.Mock(),
                                                                    mock.Mock())
        return w

    def test_the_windows_release_files_keep_their_names(self):
        self.assertEqual(updates.PORTABLE_ZIP, "KanzonasPDF-portable.zip")
        self.assertEqual(updates.setup_name("1.7"), "KanzonasPDF-v1.7-setup.exe")

    def test_no_appimage_on_windows(self):
        self.assertIsNone(updates.running_appimage())
        self.assertFalse(updates.can_update_appimage())

    def test_portable(self):
        w = self.window()
        with mock.patch("kanzonas.paths.is_portable", lambda: True), \
                mock.patch("kanzonas.paths.platform_updates", lambda: False):
            self.assertTrue(w._self_update_url().endswith("/v9.9/KanzonasPDF-portable.zip"))
            self.assertEqual(w._update_now_text(), (
                "Update now downloads it, closes KanzonasPDF, replaces the program files in "
                "this folder (your data folder is kept) and starts it again."))
            w.update_now()
        self.assertTrue(w.update_portable.called)
        self.assertFalse(w.update_appimage.called)

    def test_installed(self):
        w = self.window()
        with mock.patch("kanzonas.paths.is_portable", lambda: False), \
                mock.patch.object(updates.os.path, "exists",
                                  lambda p: os.path.basename(p) == "unins000.exe"
                                  or os.path.lexists(p)):
            self.assertTrue(w._self_update_url().endswith("/v9.9/KanzonasPDF-v9.9-setup.exe"))
            self.assertEqual(w._update_now_text(), (
                "Update now downloads the new setup, checks it, closes KanzonasPDF (after "
                "asking to save your work) and installs the new version over this one; "
                "KanzonasPDF starts again when it's done. Your settings are kept."))
            w.update_now()
        self.assertTrue(w.update_installed.called)
        self.assertFalse(w.update_appimage.called)

    def test_neither_portable_nor_installed_has_no_update_now(self):
        w = self.window()
        with mock.patch("kanzonas.paths.is_portable", lambda: False):
            self.assertIsNone(w._self_update_url())
            w.update_now()
        self.assertFalse(w.update_appimage.called)

    def test_no_menu_entry_work_on_windows(self):
        from kanzonas import linux_desktop
        ran = []
        self.assertFalse(linux_desktop.available())
        with mock.patch.object(linux_desktop, "is_added", lambda: True):
            self.assertFalse(linux_desktop.refresh("9.9", runner=lambda *a, **k: ran.append(a)))
        self.assertEqual(ran, [])

    def test_the_write_error_reads_as_in_1_6_3(self):
        e = OSError("disk full")
        for cls in (updates.PortableUpdater, updates.InstallerUpdater):
            dl = cls.__new__(cls)
            self.assertEqual(cls._write_error(dl, e),
                             "Can't write next to KanzonasPDF.exe (disk full).")


class Fonts(unittest.TestCase):
    ENV = {"WINDIR": r"C:\Windows", "LOCALAPPDATA": r"C:\Users\me\AppData\Local"}

    def test_the_windows_font_folders_as_in_1_6_3(self):
        with mock.patch.object(text_edit.os, "name", "nt"), \
                mock.patch.dict(os.environ, self.ENV):
            dirs = text_edit.font_dirs()
            old = [os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"),
                   os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "Windows",
                                "Fonts"),
                   "/usr/share/fonts", os.path.expanduser("~/.fonts"), "/Library/Fonts"]
        self.assertEqual(dirs, old)

    def test_the_windows_font_files_as_in_1_6_3(self):
        d = tempfile.mkdtemp()
        os.makedirs(os.path.join(d, "sub"))
        for n in ("a.ttf", "b.otf", os.path.join("sub", "c.ttf"), "d.ttc", "e.fon"):
            open(os.path.join(d, n), "wb").close()
        import glob
        with mock.patch.object(text_edit.os, "name", "nt"):
            got = text_edit._font_files(d)
        self.assertEqual(sorted(got),
                         sorted(glob.glob(os.path.join(d, "**", "*.[to]tf"), recursive=True)))

    def test_no_fontconfig_stand_in_on_windows(self):
        asked = []
        with mock.patch.object(text_edit.os, "name", "nt"), \
                mock.patch.object(text_edit, "_system_fonts", lambda: {}), \
                mock.patch.object(text_edit, "_fontconfig_family",
                                  lambda f: asked.append(f) or "DejaVu Sans"):
            self.assertIsNone(text_edit.chosen_font(None, "Sans Serif"))
        self.assertEqual(asked, [])


class Wording(unittest.TestCase):
    """What Windows shows: as in 1.6.3, in English and Spanish, and in the manual."""

    def window(self, platform):
        from kanzonas import main_window
        with mock.patch.object(main_window, "sys", SysAs(platform)):
            w = main_window.MainWindow()
        self.addCleanup(lambda: (setattr(w, "_close_confirmed", True), w.close()))
        return w

    def test_view_theme_and_the_manual_on_windows_and_linux(self):
        from kanzonas import manual
        for platform, label in (("win32", "Match &Windows"), ("linux", "Match &system")):
            w = self.window(platform)
            self.assertEqual(w.theme_actions["system"].text(), label)
            self.assertEqual(manual.missing_from_manual(w), [], platform)

    def test_preferences_on_windows(self):
        from kanzonas import linux_desktop, preferences
        w = self.window("win32")
        with mock.patch.object(preferences, "sys", SysAs("win32")), \
                mock.patch.object(linux_desktop, "sys", SysAs("win32")), \
                mock.patch("kanzonas.paths.is_portable", lambda: False):
            dlg = preferences.PreferencesDialog(w)
        self.addCleanup(dlg.deleteLater)
        self.assertEqual(dlg.theme.itemText(0), "Match Windows")
        self.assertEqual(dlg.language.itemText(0), "Automatic (the language of Windows)")
        self.assertIsNone(dlg.desktop)                  # (the setup does the menu on Windows)
        from PySide6.QtWidgets import QLabel
        texts = [lab.text() for lab in dlg.findChildren(QLabel)]
        self.assertIn("Settings are saved in your Windows user profile.", texts)
        self.assertTrue(any("If KanzonasPDF or Windows stops unexpectedly" in t for t in texts))
        self.assertFalse(any("the computer stops unexpectedly" in t for t in texts))
        self.assertFalse(any("applications menu" in t for t in texts))

    def test_spanish_for_both(self):
        from kanzonas import manual_es
        es = i18n.load("es")
        text = re.sub(r"\s+", " ", manual_es.MANUAL)
        for english in ("Match &Windows", "Match &system", "Match Windows", "Match system",
                        "Automatic (the language of Windows)",
                        "Settings are saved in your Windows user profile.",
                        "This link points to a file on another computer:\n\n{path}\n\nOpening "
                        "it sends your Windows sign-in to that computer. Open it?",
                        "Open the release page to download the installer or portable zip",
                        "Windows certificate",
                        "Certificate stored in Windows (cards and tokens too)"):
            self.assertTrue(es.get(english), english)
        for english in ("Match &Windows", "Match &system"):
            self.assertIn(es[english].replace("&", ""), text)


@unittest.skipIf(yaml is None, "PyYAML isn't installed")
class WindowsBuild(unittest.TestCase):
    """The Windows job of the workflow: the 1.6.3 build, with its release files."""

    # the Windows build's command and steps in 1.6.3 (5709c75)
    PYINSTALLER = (
        "python -m PyInstaller --noconfirm --windowed --collect-all rapidocr_onnxruntime "
        "--collect-all docx --collect-all pptx --collect-all pdf2docx --collect-all ezdxf "
        "--collect-all openpyxl --collect-all pyhanko --collect-all pyhanko_certvalidator "
        "--collect-all qtawesome --collect-all aiohttp --collect-all spellchecker "
        "--collect-data kanzonas --icon assets/kanzonas.ico --exclude-module tkinter "
        "--exclude-module pymupdf.layout --name KanzonasPDF run.py")
    STEPS = ["Install dependencies",
             "Regression tests (security, document preservation, efficiency budgets)",
             "Build exe", "Smoke test (exe starts and opens a PDF)",
             "Self test (OCR, exports, signatures, forms inside the exe)",
             "License and source notice", "Read version", "Zip",
             "Build installer (Inno Setup)",
             "Test updating (install an older version, then the new one over it, no uninstall)",
             "Test the installer (install, self test the installed app, uninstall)",
             "Portable version (settings and files stay in a data folder beside the exe)",
             "PortableApps.com package layout (finished by hand with their tools)",
             "winget manifests for this version (attached to the release; see packaging/winget)",
             "Release notes (RELEASE_NOTES.md; the update box shows them)"]
    ARTIFACTS = ["KanzonasPDF-v${{ steps.ver.outputs.version }}-portableapps-layout",
                 "KanzonasPDF-v${{ steps.ver.outputs.version }}-portable",
                 "KanzonasPDF-v${{ steps.ver.outputs.version }}-windows",
                 "KanzonasPDF-v${{ steps.ver.outputs.version }}-setup"]
    RELEASE_FILES = ["KanzonasPDF-v${{ env.VERSION }}-setup.exe", "KanzonasPDF-portable.zip",
                     "KanzonasPDF-windows.zip", "winget-manifests.zip"]

    @classmethod
    def setUpClass(cls):
        with open(WORKFLOW, encoding="utf-8") as f:
            cls.wf = yaml.safe_load(f)
        cls.build = cls.wf["jobs"]["build"]

    def step(self, name):
        return [s for s in self.build["steps"] if s.get("name") == name][0]

    def test_the_same_pyinstaller_command_line(self):
        run = self.step("Build exe")["run"].replace("${{ env.PYINSTALLER_OPTIONS }}",
                                                    self.wf["env"]["PYINSTALLER_OPTIONS"])
        self.assertEqual(run.split(), self.PYINSTALLER.split())
        self.assertNotIn("${{", run)

    def test_every_windows_step_still_there_in_order(self):
        self.assertEqual(self.build["runs-on"], "windows-latest")
        names = [s.get("name") for s in self.build["steps"] if s.get("name")]
        self.assertEqual([n for n in names if n in self.STEPS], self.STEPS)
        made = [s["with"]["name"] for s in self.build["steps"]
                if "upload-artifact" in s.get("uses", "") and s["with"]["name"] in self.ARTIFACTS]
        self.assertEqual(made, self.ARTIFACTS)
        # the build tests the setup with the command line Update now uses
        self.assertIn('"/SILENT","/SUPPRESSMSGBOXES","/NORESTART","/SP-","/CLOSEAPPLICATIONS",'
                      '"/CURRENTUSER","/RELAUNCH"', "\n".join(
                          s.get("run", "") for s in self.build["steps"]))

    def test_the_windows_release_files_keep_their_names(self):
        up = self.step("Windows release files for publishing")["with"]["path"].splitlines()
        self.assertIn("dist-installer/KanzonasPDF-v${{ steps.ver.outputs.version }}-setup.exe", up)
        self.assertIn("KanzonasPDF-portable.zip", up)
        self.assertIn("KanzonasPDF-windows.zip", up)
        self.assertIn("winget-manifests.zip", up)
        files = self.wf["jobs"]["publish"]["steps"]
        rel = [s for s in files if s.get("name") == "Publish release"][0]["with"]
        published = [os.path.basename(p.strip()) for p in rel["files"].splitlines()]
        for name in self.RELEASE_FILES:
            self.assertIn(name, published)
        sums = [s for s in files if s.get("name") == "Checksums (SHA-256) of the downloads"][0]
        for name in ("KanzonasPDF-v$VERSION-setup.exe", "KanzonasPDF-portable.zip",
                     "KanzonasPDF-windows.zip"):
            self.assertIn(name, sums["run"])
        self.assertIn("**Download `KanzonasPDF-v${{ env.VERSION }}-setup.exe`**", rel["body"])
        self.assertIn("Get-FileHash <file>", rel["body"])


if __name__ == "__main__":
    unittest.main()
