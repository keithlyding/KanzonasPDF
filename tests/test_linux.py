"""KanzonasPDF on Linux: Update now replaces the running AppImage (downloaded next to it,
checked against the release's sha256, renamed over it, started again) or, when this user
can't replace it, opens the release page; Preferences adds the program to the applications
menu as the default PDF app and takes it away again (for this user only); the installed
fonts are found where fontconfig keeps them; files from a file manager (file:// addresses)
open; the single-instance socket lives in the user's own runtime folder. Windows keeps its
own ways (checked where it matters). No network: downloads come from local files.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_linux
"""
import hashlib
import os
import stat
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEventLoop, QObject, QTimer, QUrl, Signal  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import linux_desktop, text_edit, updates  # noqa: E402

# a pretend type-2 AppImage: ELF magic, then "AI\x02" at offset 8
NEW_APPIMAGE = b"\x7fELF\x02\x01\x01\x00AI\x02" + b"new version " * 2000
OLD_APPIMAGE = b"\x7fELF\x02\x01\x01\x00AI\x02" + b"old version " * 10

LINUX = sys.platform.startswith("linux")


def release(version="9.9", data=NEW_APPIMAGE, host="github.com", digest=None):
    name = updates.APPIMAGE
    return {"tag_name": "v" + version, "html_url": "https://github.com/x/releases/tag/v" + version,
            "assets": [{"name": name, "browser_download_url":
                        "https://%s/x/releases/download/v%s/%s" % (host, version, name),
                        "digest": "sha256:" + (digest or hashlib.sha256(data).hexdigest())}]}


def appimage_in(folder, data=OLD_APPIMAGE, mode=0o755):
    path = os.path.join(folder, updates.APPIMAGE)
    with open(path, "wb") as f:
        f.write(data)
    os.chmod(path, mode)
    return path


class AppImagePieces(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def test_only_a_linux_appimage_updates_this_way(self):
        path = appimage_in(self.dir)
        with mock.patch.dict(os.environ, {"APPIMAGE": path}), \
                mock.patch.object(sys, "platform", "linux"):
            self.assertEqual(updates.running_appimage(), path)
            self.assertTrue(updates.can_update_appimage())
        with mock.patch.dict(os.environ, {"APPIMAGE": path}), \
                mock.patch.object(sys, "platform", "win32"):
            self.assertFalse(updates.can_update_appimage())        # Windows: its own ways
        env = dict(os.environ)
        env.pop("APPIMAGE", None)
        with mock.patch.dict(os.environ, env, clear=True), \
                mock.patch.object(sys, "platform", "linux"):
            self.assertFalse(updates.can_update_appimage())        # run from source
        with mock.patch.dict(os.environ, {"APPIMAGE": os.path.join(self.dir, "gone")}), \
                mock.patch.object(sys, "platform", "linux"):
            self.assertFalse(updates.can_update_appimage())

    def test_the_appimage_of_a_release(self):
        r = release()
        self.assertTrue(updates.asset_url(r, updates.APPIMAGE).endswith(
            "/KanzonasPDF-x86_64.AppImage"))
        self.assertEqual(updates.asset_digest(r, updates.APPIMAGE),
                         hashlib.sha256(NEW_APPIMAGE).hexdigest())
        self.assertIsNone(updates.asset_url(release(host="evil.example"), updates.APPIMAGE))

    def test_an_appimage_is_recognized(self):
        good, bad = os.path.join(self.dir, "good"), os.path.join(self.dir, "bad")
        with open(good, "wb") as f:
            f.write(NEW_APPIMAGE)
        with open(bad, "wb") as f:
            f.write(b"<html>not found</html>")
        self.assertTrue(updates.is_appimage_file(good))
        self.assertFalse(updates.is_appimage_file(bad))
        self.assertFalse(updates.is_appimage_file(os.path.join(self.dir, "missing")))

    @unittest.skipUnless(LINUX, "Linux file modes")
    def test_the_new_file_takes_the_old_ones_place_in_one_step(self):
        target = appimage_in(self.dir, mode=0o750)
        new = os.path.join(self.dir, ".new")
        with open(new, "wb") as f:
            f.write(NEW_APPIMAGE)
        os.chmod(new, 0o600)
        updates.replace_appimage(new, target)
        self.assertFalse(os.path.exists(new))
        with open(target, "rb") as f:
            self.assertEqual(f.read(), NEW_APPIMAGE)
        self.assertEqual(stat.S_IMODE(os.stat(target).st_mode), 0o750)   # as the old one
        # an old file its owner couldn't run: the new one can be run by its owner
        os.chmod(target, 0o644)
        with open(new, "wb") as f:
            f.write(NEW_APPIMAGE)
        updates.replace_appimage(new, target)
        self.assertTrue(os.stat(target).st_mode & stat.S_IXUSR)

    @unittest.skipUnless(LINUX, "Linux permissions")
    def test_a_folder_this_user_cant_change_is_said(self):
        target = appimage_in(self.dir)
        self.assertIsNone(updates.appimage_unwritable(target))
        real = os.access
        with mock.patch.object(updates.os, "access",
                               lambda p, m: False if p == self.dir else real(p, m)):
            why = updates.appimage_unwritable(target)
        self.assertIn(self.dir, why)
        self.assertIn("permission", why)

    def test_the_restart_leaves_this_appimages_own_settings_behind(self):
        env = {"APPIMAGE": "/home/me/K.AppImage", "APPDIR": "/tmp/.mount_KzAbc",
               "ARGV0": "./K.AppImage", "OWD": "/home/me",
               "LD_LIBRARY_PATH": "/tmp/.mount_KzAbc/usr/lib",
               "LD_LIBRARY_PATH_ORIG": "/opt/lib",
               "QT_PLUGIN_PATH": "/tmp/.mount_KzAbc/usr/plugins",
               "XDG_DATA_DIRS": "/tmp/.mount_KzAbc/usr/share:/usr/share",
               "PATH": "/tmp/.mount_KzAbc/usr/bin:/usr/bin", "HOME": "/home/me"}
        with mock.patch.object(updates.os, "pathsep", ":"):     # (Linux's lists, on Windows too)
            out = updates.restart_env(env)
        for key in ("APPIMAGE", "APPDIR", "ARGV0", "OWD", "QT_PLUGIN_PATH",
                    "LD_LIBRARY_PATH_ORIG"):
            self.assertNotIn(key, out)
        self.assertEqual(out["LD_LIBRARY_PATH"], "/opt/lib")
        self.assertEqual(out["XDG_DATA_DIRS"], "/usr/share")
        self.assertEqual(out["PATH"], "/usr/bin")
        self.assertEqual(out["HOME"], "/home/me")
        # PyInstaller without an earlier value: the path into the old AppImage goes
        out = updates.restart_env({"APPDIR": "/tmp/.mount_X",
                                   "LD_LIBRARY_PATH": "/tmp/.mount_X/usr/lib"})
        self.assertNotIn("LD_LIBRARY_PATH", out)


class AppImageDownload(unittest.TestCase):
    def fetch(self, data, digest):
        folder = tempfile.mkdtemp()
        target = appimage_in(folder)
        src = os.path.join(tempfile.mkdtemp(), "download")
        with open(src, "wb") as f:
            f.write(data)
        holder = QObject()
        self.addCleanup(lambda: (holder.deleteLater(), APP.processEvents()))
        dl = updates.AppImageUpdater(QUrl.fromLocalFile(src).toString(), target, holder,
                                     expected_sha256=digest)
        out = {}
        loop = QEventLoop()
        dl.ready.connect(lambda p: (out.setdefault("ready", p), loop.quit()))
        dl.failed.connect(lambda m: (out.setdefault("failed", m), loop.quit()))
        QTimer.singleShot(10000, loop.quit)
        dl.start()
        if not out:
            loop.exec()
        return folder, target, dl, out

    def test_a_checked_appimage_waits_next_to_the_old_one(self):
        folder, target, dl, out = self.fetch(NEW_APPIMAGE,
                                             hashlib.sha256(NEW_APPIMAGE).hexdigest())
        path = out.get("ready")
        self.assertTrue(path and os.path.exists(path), out)
        self.assertEqual(os.path.dirname(path), folder)            # same disk: one rename
        with open(path, "rb") as f:
            self.assertEqual(f.read(), NEW_APPIMAGE)
        with open(target, "rb") as f:
            self.assertEqual(f.read(), OLD_APPIMAGE)              # not replaced yet

    def test_a_wrong_download_is_thrown_away(self):
        folder, target, dl, out = self.fetch(NEW_APPIMAGE, "1" * 64)
        self.assertIn("sha256", out.get("failed", ""))
        self.assertEqual(os.listdir(folder), [updates.APPIMAGE])

    def test_something_else_than_an_appimage_is_refused(self):
        page = b"<html>an error page</html>"
        folder, target, dl, out = self.fetch(page, hashlib.sha256(page).hexdigest())
        self.assertIn("AppImage", out.get("failed", ""))
        self.assertEqual(os.listdir(folder), [updates.APPIMAGE])

    def test_no_digest_no_download(self):
        folder, target, dl, out = self.fetch(NEW_APPIMAGE, None)
        self.assertIn("digest", out.get("failed", ""))
        self.assertEqual(os.listdir(folder), [updates.APPIMAGE])


def fake_download(produce):
    class FakeDownload:
        def __init__(self, url, appimage, parent=None, expected_sha256=None):
            FakeDownload.args = (url, appimage, expected_sha256)

            class S(QObject):
                progress = Signal(int, int)
                ready = Signal(str)
                failed = Signal(str)
            self.s = S()
            self.progress, self.ready, self.failed = (self.s.progress, self.s.ready,
                                                      self.s.failed)

        def start(self):
            self.ready.emit(produce())

        def cancel(self):
            pass
    return FakeDownload


@unittest.skipUnless(LINUX, "the Linux AppImage")
class AppImageUpdateNow(unittest.TestCase):
    def window(self):
        from kanzonas.main_window import MainWindow
        w = MainWindow()
        self.addCleanup(lambda: (setattr(w, "_close_confirmed", True), w.close()))
        w._upd = mock.Mock(release=release())
        return w

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.target = appimage_in(self.dir)
        self.env = mock.patch.dict(os.environ, {"APPIMAGE": self.target,
                                                "APPDIR": "/tmp/.mount_Kz1"})
        self.env.start()
        self.addCleanup(self.env.stop)

    def new_file(self):
        path = os.path.join(self.dir, ".download")
        with open(path, "wb") as f:
            f.write(NEW_APPIMAGE)
        return path

    def test_update_now_replaces_the_appimage_and_starts_it_again(self):
        w = self.window()
        fake = fake_download(self.new_file)
        with mock.patch.object(updates, "AppImageUpdater", fake), \
                mock.patch.object(w, "close", lambda: True), \
                mock.patch("subprocess.Popen") as popen, \
                mock.patch.object(QApplication, "quit") as quit_:
            self.assertTrue(w._self_update_url().endswith("/KanzonasPDF-x86_64.AppImage"))
            self.assertIn("new AppImage", w._update_now_text())
            w.update_now()
        self.assertEqual(fake.args[1], self.target)
        self.assertEqual(fake.args[2], hashlib.sha256(NEW_APPIMAGE).hexdigest())
        with open(self.target, "rb") as f:
            self.assertEqual(f.read(), NEW_APPIMAGE)
        self.assertTrue(os.access(self.target, os.X_OK))
        cmd = popen.call_args[0][0]
        # (through a shell that waits for this process to end, then runs the new AppImage)
        self.assertEqual((cmd[0], cmd[-2], cmd[-1]), ("/bin/sh", str(os.getpid()), self.target))
        env = popen.call_args[1]["env"]
        self.assertNotIn("APPIMAGE", env)
        self.assertNotIn("APPDIR", env)
        self.assertTrue(quit_.called)

    def test_a_document_kept_open_keeps_the_program_running(self):
        w = self.window()
        with mock.patch.object(updates, "AppImageUpdater", fake_download(self.new_file)), \
                mock.patch.object(w, "close", lambda: False), \
                mock.patch.object(QMessageBox, "information") as info, \
                mock.patch("subprocess.Popen") as popen, \
                mock.patch.object(QApplication, "quit") as quit_:
            w.update_now()
        self.assertFalse(popen.called)
        self.assertFalse(quit_.called)
        self.assertIn("next time", info.call_args[0][2])          # in place for next time
        with open(self.target, "rb") as f:
            self.assertEqual(f.read(), NEW_APPIMAGE)

    def test_an_appimage_this_user_cant_replace_opens_the_release_page(self):
        w = self.window()
        fake = fake_download(self.new_file)
        fake.args = None
        with mock.patch.object(updates, "appimage_unwritable", lambda p: "Not yours."), \
                mock.patch.object(updates, "AppImageUpdater", fake), \
                mock.patch.object(QMessageBox, "information") as info, \
                mock.patch("PySide6.QtGui.QDesktopServices.openUrl") as open_url:
            w.update_now()
        self.assertIsNone(fake.args)                               # nothing downloaded
        self.assertIn("Not yours.", info.call_args[0][2])
        self.assertEqual(open_url.call_args[0][0].toString(),
                         "https://github.com/x/releases/tag/v9.9")
        with open(self.target, "rb") as f:
            self.assertEqual(f.read(), OLD_APPIMAGE)

    def test_run_from_source_only_tells(self):
        self.env.stop()
        env = dict(os.environ)
        env.pop("APPIMAGE", None)
        with mock.patch.dict(os.environ, env, clear=True):
            w = self.window()
            self.assertIsNone(w._self_update_url())
        self.env.start()


class MenuEntry(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp()
        self.appimage = appimage_in(tempfile.mkdtemp(prefix="my apps "))
        self.env = mock.patch.dict(os.environ, {
            "XDG_DATA_HOME": os.path.join(self.home, "data"),
            "XDG_CONFIG_HOME": os.path.join(self.home, "config"),
            "APPIMAGE": self.appimage})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.ran = []

    def runner(self, args, **_kw):
        self.ran.append(args)
        return mock.Mock(returncode=0)

    @unittest.skipUnless(LINUX, "Linux paths in the menu entry")
    def test_added_to_the_menu_and_as_the_pdf_app_then_taken_away(self):
        with mock.patch.object(linux_desktop.shutil, "which", lambda name: "/usr/bin/" + name):
            notes = linux_desktop.add("9.9", runner=self.runner)
        self.assertEqual(notes, [])
        desk = os.path.join(self.home, "data", "applications", "kanzonaspdf.desktop")
        icon = os.path.join(self.home, "data", "icons", "hicolor", "256x256", "apps",
                            "kanzonaspdf.png")
        self.assertTrue(linux_desktop.is_added())
        with open(desk, encoding="utf-8") as f:
            text = f.read()
        # the AppImage's folder has a space: the Exec line quotes it
        self.assertIn('Exec="%s" %%F\n' % self.appimage, text)
        self.assertIn("MimeType=application/pdf;", text)
        self.assertIn("Icon=kanzonaspdf\n", text)
        with open(icon, "rb") as f:
            self.assertEqual(f.read(8), b"\x89PNG\r\n\x1a\n")
        self.assertIn(["xdg-mime", "default", "kanzonaspdf.desktop", "application/pdf"],
                      self.ran)
        self.assertIn(["update-desktop-database", os.path.dirname(desk)], self.ran)
        linux_desktop.remove(runner=self.runner)
        self.assertFalse(os.path.exists(desk))
        self.assertFalse(os.path.exists(icon))
        self.assertFalse(linux_desktop.is_added())

    def test_without_xdg_mime_the_default_is_written_in_mimeapps_list(self):
        conf = os.path.join(self.home, "config")
        os.makedirs(conf)
        with open(os.path.join(conf, "mimeapps.list"), "w") as f:
            f.write("[Default Applications]\ntext/plain=gedit.desktop;\n"
                    "application/pdf=org.gnome.Evince.desktop;\n")
        with mock.patch.object(linux_desktop.shutil, "which", lambda name: None):
            linux_desktop.add(runner=self.runner)
        self.assertEqual(self.ran, [])                             # no tools: none run
        with open(os.path.join(conf, "mimeapps.list")) as f:
            text = f.read()
        self.assertIn("application/pdf=kanzonaspdf.desktop;org.gnome.Evince.desktop;", text)
        self.assertIn("text/plain=gedit.desktop;", text)
        linux_desktop.remove(runner=self.runner)
        with open(os.path.join(conf, "mimeapps.list")) as f:
            text = f.read()
        # back as it was: the earlier app is the default again
        self.assertEqual(text, "[Default Applications]\ntext/plain=gedit.desktop;\n"
                               "application/pdf=org.gnome.Evince.desktop;\n")

    def test_a_menu_entry_kanzonaspdf_didnt_write_is_left_alone(self):
        desk = linux_desktop.desktop_path()
        os.makedirs(os.path.dirname(desk))
        with open(desk, "w") as f:
            f.write("[Desktop Entry]\nName=Someone else's\n")
        self.assertFalse(linux_desktop.is_added())
        linux_desktop.remove(runner=self.runner)
        self.assertTrue(os.path.exists(desk))

    @unittest.skipUnless(LINUX, "Linux paths in the menu entry (Windows: no menu entry)")
    def test_the_entry_follows_a_moved_appimage(self):
        with mock.patch.object(linux_desktop.shutil, "which", lambda name: None):
            linux_desktop.add(runner=self.runner)
            self.assertFalse(linux_desktop.refresh(runner=self.runner))   # still there
            moved = appimage_in(tempfile.mkdtemp())
            os.remove(self.appimage)
            with mock.patch.dict(os.environ, {"APPIMAGE": moved}):
                self.assertTrue(linux_desktop.refresh(runner=self.runner))
        with open(linux_desktop.desktop_path(), encoding="utf-8") as f:
            self.assertIn("Exec=%s %%F\n" % moved, f.read())

    def test_exec_quoting(self):
        q = linux_desktop.exec_quote
        self.assertEqual(q("/opt/KanzonasPDF.AppImage"), "/opt/KanzonasPDF.AppImage")
        self.assertEqual(q("/home/a b/K.AppImage"), '"/home/a b/K.AppImage"')
        self.assertEqual(q("/x/100%"), "/x/100%%")
        # inside quotes " ` $ \ get a backslash, and every backslash is written twice
        self.assertEqual(q('/x/$a"b'), '"/x/\\\\$a\\\\"b"')

    def test_preferences_adds_and_removes(self):
        from kanzonas.main_window import MainWindow
        from kanzonas.preferences import PreferencesDialog
        w = MainWindow()
        self.addCleanup(lambda: (setattr(w, "_close_confirmed", True), w.close()))
        with mock.patch.object(linux_desktop, "available", lambda: True), \
                mock.patch.object(linux_desktop.shutil, "which", lambda name: None), \
                mock.patch.object(QMessageBox, "information") as info:
            dlg = PreferencesDialog(w)
            self.assertIsNotNone(dlg.desktop)
            self.assertFalse(dlg.desktop.isChecked())
            dlg.desktop.setChecked(True)
            dlg._apply()
            self.assertTrue(linux_desktop.is_added())
            self.assertTrue(info.called)
            dlg.deleteLater()
            dlg = PreferencesDialog(w)
            self.assertTrue(dlg.desktop.isChecked())
            dlg.desktop.setChecked(False)
            dlg._apply()
            self.assertFalse(linux_desktop.is_added())
            dlg.deleteLater()
        with mock.patch.object(linux_desktop, "available", lambda: False):
            dlg = PreferencesDialog(w)                 # Windows: no such option
            self.assertIsNone(dlg.desktop)
            dlg.deleteLater()


class Fonts(unittest.TestCase):
    @unittest.skipIf(os.name == "nt", "the Linux font folders")
    def test_the_users_own_fonts_and_fontconfigs_folders_are_scanned(self):
        home = tempfile.mkdtemp()
        data = os.path.join(home, "data")
        mine = os.path.join(data, "fonts", "Sub")
        os.makedirs(mine)
        extra = os.path.join(home, "extra fonts")
        os.makedirs(extra)
        conf = os.path.join(home, "fonts.conf")
        with open(conf, "w") as f:
            f.write('<fontconfig><dir>%s</dir><!-- <dir>/nowhere</dir> -->'
                    '<dir prefix="xdg">fonts</dir><dir>~/.fonts</dir></fontconfig>' % extra)
        with mock.patch.dict(os.environ, {"XDG_DATA_HOME": data, "HOME": home,
                                          "XDG_DATA_DIRS": "/nonexistent"}):
            self.assertEqual(text_edit._fontconfig_dirs(conf),
                             [extra, os.path.join(data, "fonts"),
                              os.path.join(home, ".fonts")])
            with mock.patch.object(text_edit, "_fontconfig_dirs", lambda: [extra, mine]):
                dirs = text_edit.font_dirs()
        self.assertIn(os.path.join(data, "fonts"), dirs)
        self.assertIn(extra, dirs)
        self.assertNotIn(mine, dirs)        # inside a folder already scanned: once
        # a font file written in capitals is a font file too
        src = pymupdf_font_file()
        if src:
            import shutil
            shutil.copy(src, os.path.join(mine, "MYFONT.TTF"))
            self.assertEqual(text_edit._font_files(os.path.join(data, "fonts")),
                             [os.path.join(mine, "MYFONT.TTF")])

    @unittest.skipIf(os.name == "nt", "the Linux font folders")
    def test_fonts_installed_on_this_computer_are_found(self):
        found = text_edit._system_fonts()
        if not any(os.path.isdir(d) for d in text_edit.font_dirs()):
            self.skipTest("no fonts installed")
        self.assertTrue(found, text_edit.font_dirs())

    def test_windows_keeps_its_font_folders(self):
        with mock.patch.object(text_edit.os, "name", "nt"), \
                mock.patch.dict(os.environ, {"WINDIR": r"C:\Windows",
                                             "LOCALAPPDATA": r"C:\Users\me\AppData\Local"}):
            dirs = text_edit.font_dirs()
        self.assertEqual(dirs[0], os.path.join(r"C:\Windows", "Fonts"))
        self.assertEqual(len(dirs), 5)


def pymupdf_font_file():
    for d in text_edit.font_dirs():
        for f in text_edit._font_files(d):
            return f
    return None


class StartUp(unittest.TestCase):
    def test_files_from_a_file_manager(self):
        from kanzonas.__main__ import file_arguments
        d = tempfile.mkdtemp()
        # (the address a file manager passes: file:///home/... or, on Windows, file:///C:/...)
        url = QUrl.fromLocalFile(os.path.join(d, "My Plan.pdf")).toString(QUrl.FullyEncoded)
        self.assertIn("My%20Plan.pdf", url)
        got = file_arguments(["--flag", url, os.path.join(d, "b.pdf")])
        self.assertEqual(got, [os.path.join(d, "My Plan.pdf"), os.path.join(d, "b.pdf")])

    @unittest.skipUnless(LINUX, "the Linux socket")
    def test_the_socket_is_in_the_users_own_runtime_folder(self):
        from kanzonas.__main__ import instance_name
        run = tempfile.mkdtemp()
        with mock.patch.dict(os.environ, {"XDG_RUNTIME_DIR": run}):
            self.assertEqual(instance_name("KanzonasPDF", "me"),
                             os.path.join(run, "KanzonasPDF-me"))
        with mock.patch.dict(os.environ, {"XDG_RUNTIME_DIR": ""}):
            self.assertEqual(instance_name("KanzonasPDF", "me"), "KanzonasPDF-me")
        with mock.patch.object(sys, "platform", "win32"), \
                mock.patch.dict(os.environ, {"XDG_RUNTIME_DIR": run}):
            self.assertEqual(instance_name("KanzonasPDF", "me"), "KanzonasPDF-me")

    @unittest.skipUnless(LINUX, "the Linux socket")
    def test_one_window_through_a_socket_in_the_runtime_folder(self):
        import uuid
        from kanzonas.__main__ import first_instance
        name = os.path.join(tempfile.mkdtemp(), "KanzonasPDF-" + uuid.uuid4().hex[:8])
        server, sock = first_instance(name)
        self.assertIsNotNone(server)
        self.addCleanup(server.close)
        self.assertTrue(os.path.exists(name))
        self.assertEqual(stat.S_IMODE(os.stat(name).st_mode) & 0o077, 0)   # this user only
        server2, sock2 = first_instance(name)
        self.assertIsNone(server2)
        self.assertIsNotNone(sock2)
        sock2.disconnectFromServer()


# The real entry point in its own process (no backups offered, no session, no update check):
# it opens $KZ_PDF, makes an unsaved change and writes "ready" to $KZ_STATE.
SIGTERM_CHILD = r"""
import os, sys
sys.path.insert(0, os.environ["KZ_ROOT"])
from unittest import mock
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QMessageBox
for name in ("information", "warning", "critical", "question"):
    mock.patch.object(QMessageBox, name, return_value=QMessageBox.No).start()
from kanzonas import main_window
for name in ("recover_backups", "restore_session", "start_update_check"):
    mock.patch.object(main_window.MainWindow, name, lambda self: None).start()

def edit():
    w = main_window.windows()[0]
    v = w.view()
    if v is None:
        QTimer.singleShot(100, edit)
        return
    v.modify(lambda: v.doc[0].insert_text((72, 72), "unsaved"), pages=[0])
    with open(os.environ["KZ_STATE"], "w") as f:
        f.write("ready")
init = main_window.MainWindow.__init__

def start(self, *a, **k):
    init(self, *a, **k)
    if not hasattr(main_window, "_kz_timer"):
        main_window._kz_timer = True
        QTimer.singleShot(1500, edit)
        QTimer.singleShot(60000, lambda: os._exit(3))
main_window.MainWindow.__init__ = start
sys.argv = ["kanzonas", os.environ["KZ_PDF"]]
from kanzonas.__main__ import main
main()
"""


@unittest.skipUnless(LINUX, "Linux signals")
class SignOut(unittest.TestCase):
    def test_sigterm_keeps_the_files_and_a_backup_of_unsaved_changes(self):
        import signal
        import subprocess
        import time
        import uuid
        import pymupdf
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        home = tempfile.mkdtemp()
        pdf = os.path.join(home, "plan.pdf")
        d = pymupdf.open()
        d.new_page()
        d.save(pdf)
        d.close()
        state = os.path.join(home, "state")
        user = "kzterm" + uuid.uuid4().hex[:8]
        env = dict(os.environ, QT_QPA_PLATFORM="offscreen", KZ_ROOT=root, KZ_PDF=pdf,
                   KZ_STATE=state, HOME=home, XDG_CONFIG_HOME=os.path.join(home, "cfg"),
                   XDG_DATA_HOME=os.path.join(home, "data"), XDG_RUNTIME_DIR="",
                   TMPDIR=home, USER=user, LOGNAME=user)
        p = subprocess.Popen([sys.executable, "-c", SIGTERM_CHILD], cwd=home, env=env,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(lambda: (p.poll() is None and p.kill(), p.wait()))
        end = time.time() + 40
        while not os.path.exists(state) and time.time() < end and p.poll() is None:
            time.sleep(0.2)
        self.assertTrue(os.path.exists(state), "the program didn't start")
        p.send_signal(signal.SIGTERM)
        self.assertEqual(p.wait(20), 0)                 # quit by itself, without asking
        conf = os.path.join(home, "cfg", "KanzonasPDF", "KanzonasPDF.conf")
        with open(conf, encoding="utf-8") as f:
            self.assertIn("plan.pdf", f.read())         # the open files, for next time
        backups = os.path.join(home, "data", "KanzonasPDF", "KanzonasPDF", "backups")
        self.assertTrue([n for n in os.listdir(backups) if n.endswith(".pdf")],
                        "no backup of the unsaved change")



class RestartWaits(unittest.TestCase):
    @unittest.skipUnless(os.path.exists("/bin/sh"), "needs a POSIX shell")
    def test_the_new_appimage_starts_only_once_this_process_has_ended(self):
        # (started while the old one still listened, it handed its files to it and quit)
        import subprocess
        import time
        d = tempfile.mkdtemp()
        out = os.path.join(d, "ran")
        target = os.path.join(d, "new.sh")
        with open(target, "w") as f:
            f.write("#!/bin/sh\necho started > '%s'\n" % out)
        os.chmod(target, 0o755)
        old = subprocess.Popen(["sleep", "1"])
        p = subprocess.Popen(updates.restart_command(target, old.pid))
        time.sleep(0.4)
        self.assertFalse(os.path.exists(out))
        old.wait()
        p.wait(timeout=10)
        self.assertTrue(os.path.exists(out))


if __name__ == "__main__":
    unittest.main()
