"""Battery 17, Linux: what broke when the Linux version was pushed on.

- Update now: a download that can't be written (the disk filled up) said nothing, kept its
  progress box open for ever and left the partial file next to the AppImage; an AppImage
  started with --appimage-extract-and-run (no FUSE) was restarted without it and didn't
  start; a $APPIMAGE that is a link had the link replaced and the real file left old.
- Applications menu: unticking didn't give PDFs back to the app chosen before when xdg-mime
  had replaced it (it does on most desktops); a kanzonaspdf.desktop the user made was
  overwritten and then deleted; a mimeapps.list with bytes that aren't UTF-8 had them
  replaced; an AppImage path with two spaces in a row got a TryExec naming another file.
- Fonts: a font installed only as a TrueType collection (.ttc: most Chinese, Japanese and
  Korean fonts on Linux) was never used: Add text wrote Helvetica instead.
- One window: without $XDG_RUNTIME_DIR the socket is in the shared /tmp, where another user
  could listen first and get the names of the files opened (and KanzonasPDF didn't start);
  a runtime folder path too long for a socket turned one window off.
- Ctrl+C in the terminal it was started from stopped Python code half done and KanzonasPDF
  went on; it now ends like SIGTERM (files kept, backups of unsaved changes).
- Theme: the ribbon moved 4 pixels down and right after every theme change.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_battery_17_linux
"""
import errno
import hashlib
import os
import signal
import socket
import struct
import sys
import tempfile
import unittest
import uuid
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEventLoop, QObject, QTimer, QUrl  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import linux_desktop, text_edit, updates  # noqa: E402
from tests.test_linux import (NEW_APPIMAGE, OLD_APPIMAGE, SIGTERM_CHILD,  # noqa: E402
                              appimage_in, fake_download, release)

LINUX = sys.platform.startswith("linux")


@unittest.skipUnless(LINUX, "the Linux AppImage")
class DiskFull(unittest.TestCase):
    def test_a_download_that_cant_be_written_says_so_and_leaves_nothing(self):
        folder = tempfile.mkdtemp()
        target = appimage_in(folder)
        src = os.path.join(tempfile.mkdtemp(), "download")
        data = NEW_APPIMAGE * 50
        with open(src, "wb") as f:
            f.write(data)
        real_open = open

        class Full:
            """A file on a disk that fills up after 10 kB."""
            def __init__(self, f):
                self.f, self.n = f, 0

            def write(self, b):
                self.n += len(b)
                if self.n > 10000:
                    raise OSError(errno.ENOSPC, "No space left on device")
                return self.f.write(b)

            def close(self):
                self.f.close()

        def opener(path, mode="r", *a, **k):
            f = real_open(path, mode, *a, **k)
            return Full(f) if ".update-" in str(path) and "w" in mode else f

        holder = QObject()
        self.addCleanup(lambda: (holder.deleteLater(), APP.processEvents()))
        dl = updates.AppImageUpdater(QUrl.fromLocalFile(src).toString(), target, holder,
                                     expected_sha256=hashlib.sha256(data).hexdigest())
        out = {}
        loop = QEventLoop()
        dl.ready.connect(lambda p: (out.setdefault("ready", p), loop.quit()))
        dl.failed.connect(lambda m: (out.setdefault("failed", m), loop.quit()))
        QTimer.singleShot(10000, loop.quit)
        real_fdopen = os.fdopen

        def fdopener(fd, mode="r", *a, **k):        # (the download is made with mkstemp)
            f = real_fdopen(fd, mode, *a, **k)
            return Full(f) if "w" in mode else f

        with mock.patch("builtins.open", opener), mock.patch.object(updates.os, "fdopen",
                                                                    fdopener):
            dl.start()
            if not out:
                loop.exec()
        self.assertIn("No space left", out.get("failed", ""), out)     # said, not silent
        self.assertEqual(os.listdir(folder), [updates.APPIMAGE])       # partial file gone
        self.assertFalse(updates.downloading())
        with open(target, "rb") as f:
            self.assertEqual(f.read(), OLD_APPIMAGE)


@unittest.skipUnless(LINUX, "the Linux AppImage")
class Restart(unittest.TestCase):
    def test_extract_and_run_is_kept_for_the_new_version(self):
        env = updates.restart_env({"APPIMAGE": "/home/me/K.AppImage",
                                   "APPDIR": "/tmp/appimage_extracted_0123abcd",
                                   "PATH": "/tmp/appimage_extracted_0123abcd/usr/bin:/usr/bin",
                                   "DESKTOP_STARTUP_ID": "old", "XDG_ACTIVATION_TOKEN": "old"})
        self.assertEqual(env.get("APPIMAGE_EXTRACT_AND_RUN"), "1")
        self.assertEqual(env["PATH"], "/usr/bin")
        self.assertNotIn("DESKTOP_STARTUP_ID", env)          # used up by this start
        self.assertNotIn("XDG_ACTIVATION_TOKEN", env)
        env = updates.restart_env({"APPIMAGE": "/home/me/K.AppImage",
                                   "APPDIR": "/tmp/.mount_KanzonAbc12"})
        self.assertNotIn("APPIMAGE_EXTRACT_AND_RUN", env)    # FUSE: started as usual

    def test_an_appimage_reached_through_a_link_is_updated_itself(self):
        real_dir, link_dir = tempfile.mkdtemp(), tempfile.mkdtemp()
        real = appimage_in(real_dir)
        link = os.path.join(link_dir, "kanzonas")
        os.symlink(real, link)
        with mock.patch.dict(os.environ, {"APPIMAGE": link}):
            target = updates.running_appimage()
        self.assertEqual(target, os.path.realpath(real))
        new = os.path.join(real_dir, ".new")
        with open(new, "wb") as f:
            f.write(NEW_APPIMAGE)
        updates.replace_appimage(new, target)
        self.assertTrue(os.path.islink(link))                # the link stays a link
        with open(link, "rb") as f:
            self.assertEqual(f.read(), NEW_APPIMAGE)         # to the new version

    def test_update_now_through_a_link(self):
        from kanzonas.main_window import MainWindow
        real_dir, link_dir = tempfile.mkdtemp(), tempfile.mkdtemp()
        real = appimage_in(real_dir)
        link = os.path.join(link_dir, "kanzonas")
        os.symlink(real, link)
        w = MainWindow()
        self.addCleanup(lambda: (setattr(w, "_close_confirmed", True), w.close()))
        w._upd = mock.Mock(release=release())

        def produce():
            path = os.path.join(real_dir, ".download")
            with open(path, "wb") as f:
                f.write(NEW_APPIMAGE)
            return path
        fake = fake_download(produce)
        with mock.patch.dict(os.environ, {"APPIMAGE": link, "APPDIR": "/tmp/.mount_Kz1"}), \
                mock.patch.object(updates, "AppImageUpdater", fake), \
                mock.patch.object(w, "close", lambda: True), \
                mock.patch("subprocess.Popen") as popen, \
                mock.patch.object(QApplication, "quit"):
            w.update_now()
        self.assertEqual(fake.args[1], os.path.realpath(real))
        self.assertTrue(os.path.islink(link))
        with open(real, "rb") as f:
            self.assertEqual(f.read(), NEW_APPIMAGE)
        self.assertEqual(popen.call_args[0][0][-1], os.path.realpath(real))   # (after the wait)


@unittest.skipIf(os.name == "nt", "the Linux applications menu")
class MenuEntry(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp()
        env = mock.patch.dict(os.environ, {
            "HOME": self.home, "XDG_DATA_HOME": os.path.join(self.home, "data"),
            "XDG_CONFIG_HOME": os.path.join(self.home, "cfg")})
        env.start()
        self.addCleanup(env.stop)
        os.makedirs(os.path.join(self.home, "cfg"))
        self.list = os.path.join(self.home, "cfg", "mimeapps.list")

    def write_list(self, data):
        with open(self.list, "wb") as f:
            f.write(data)

    def read_list(self):
        with open(self.list, "rb") as f:
            return f.read()

    def test_xdg_mime_replacing_the_default_gets_it_back_when_taken_away(self):
        def xdg_mime(args, **kw):
            # xdg-utils (and KDE, GNOME) write the new default in place of the old one
            import subprocess
            if args[0] == "xdg-mime":
                text = self.read_list().decode()
                text = text.replace("application/pdf=okular.desktop;",
                                    "application/pdf=" + args[2])
                self.write_list(text.encode())
            return subprocess.CompletedProcess(args, 0)
        self.write_list(b"[Default Applications]\napplication/pdf=okular.desktop;\n"
                        b"text/plain=gedit.desktop;\n")
        with mock.patch.object(linux_desktop.shutil, "which", lambda n: "/usr/bin/" + n):
            linux_desktop.add("1.7", runner=xdg_mime)
            self.assertIn(b"application/pdf=kanzonaspdf.desktop", self.read_list())
            linux_desktop.add("1.7", runner=xdg_mime)       # (ticked again: still okular)
            linux_desktop.remove(runner=xdg_mime)
        self.assertEqual(self.read_list(), b"[Default Applications]\n"
                         b"application/pdf=okular.desktop;\ntext/plain=gedit.desktop;\n")

    def test_a_default_chosen_after_adding_is_left_alone(self):
        self.write_list(b"[Default Applications]\napplication/pdf=okular.desktop;\n")
        with mock.patch.object(linux_desktop.shutil, "which", lambda n: None):
            linux_desktop.add("1.7")
            self.write_list(b"[Default Applications]\napplication/pdf=evince.desktop;\n")
            linux_desktop.remove()
        self.assertEqual(self.read_list(),
                         b"[Default Applications]\napplication/pdf=evince.desktop;\n")

    def test_other_lines_keep_their_bytes(self):
        before = (b"# caf\xe9\n[Default Applications]\napplication/pdf=okular.desktop;\n"
                  b"[X-Other]\nkey=\xff\xfe\n")
        self.write_list(before)
        with mock.patch.object(linux_desktop.shutil, "which", lambda n: None):
            linux_desktop.add("1.7")
            self.assertIn(b"# caf\xe9\n", self.read_list())
            linux_desktop.remove()
        self.assertEqual(self.read_list(), before)

    def test_a_menu_entry_the_user_made_comes_back(self):
        apps = os.path.join(self.home, "data", "applications")
        os.makedirs(apps)
        mine = "[Desktop Entry]\nType=Application\nName=My PDF thing\nExec=/opt/kz %F\n"
        path = os.path.join(apps, linux_desktop.DESKTOP_ID)
        with open(path, "w") as f:
            f.write(mine)
        with mock.patch.object(linux_desktop.shutil, "which", lambda n: None):
            linux_desktop.add("1.7")
            self.assertTrue(linux_desktop.is_added())
            self.assertEqual(os.listdir(apps).count(linux_desktop.DESKTOP_ID), 1)
            linux_desktop.remove()
        with open(path) as f:
            self.assertEqual(f.read(), mine)
        self.assertEqual(os.listdir(apps), [linux_desktop.DESKTOP_ID])

    def test_a_path_with_two_spaces_is_named_exactly(self):
        folder = os.path.join(self.home, "My  Apps\tx")
        os.makedirs(folder)
        appimage = os.path.join(folder, "Kz 100%.AppImage")
        with open(appimage, "w") as f:
            f.write("x")
        with mock.patch.dict(os.environ, {"APPIMAGE": appimage}), \
                mock.patch.object(linux_desktop.shutil, "which", lambda n: None):
            linux_desktop.add("1.7")
            with open(linux_desktop.desktop_path()) as f:
                lines = f.read().splitlines()
            tryexec = [x for x in lines if x.startswith("TryExec=")][0][len("TryExec="):]
            self.assertEqual(linux_desktop._unvalue(tryexec), appimage)
            self.assertNotIn("\t", tryexec)
            with mock.patch.object(sys, "platform", "linux"):
                self.assertFalse(linux_desktop.refresh("1.7"))     # nothing to point anew

    def test_moving_the_appimage_keeps_the_default_to_give_back(self):
        self.write_list(b"[Default Applications]\napplication/pdf=okular.desktop;\n")
        old = os.path.join(self.home, "old.AppImage")
        new = os.path.join(self.home, "new.AppImage")
        for p in (old, new):
            with open(p, "w") as f:
                f.write("x")

        def replacing(args, **kw):
            import subprocess
            if args[0] == "xdg-mime":
                self.write_list(b"[Default Applications]\napplication/pdf=kanzonaspdf.desktop\n")
            return subprocess.CompletedProcess(args, 0)
        with mock.patch.object(linux_desktop.shutil, "which", lambda n: "/usr/bin/" + n), \
                mock.patch.object(sys, "platform", "linux"):
            with mock.patch.dict(os.environ, {"APPIMAGE": old}):
                linux_desktop.add("1.7", runner=replacing)
            os.remove(old)
            with mock.patch.dict(os.environ, {"APPIMAGE": new}):
                self.assertTrue(linux_desktop.refresh("1.7", runner=replacing))
            linux_desktop.remove(runner=replacing)
        self.assertEqual(self.read_list(),
                         b"[Default Applications]\napplication/pdf=okular.desktop;\n")


def _a_truetype_file():
    """An installed TrueType font that can write "Hello" (macOS's first one may be a
    Braille or symbol font)."""
    import pymupdf
    for d in text_edit.font_dirs():
        for f in text_edit._font_files(d):
            if f.lower().endswith(".ttf"):
                try:
                    font = pymupdf.Font(fontfile=f)
                except Exception:
                    continue
                if all(font.has_glyph(ord(c)) for c in "Hello"):
                    return f
    return None


def _as_collection(ttf_bytes):
    """A TrueType collection (.ttc) holding the one font of ttf_bytes."""
    num = struct.unpack(">H", ttf_bytes[4:6])[0]
    head = bytearray(ttf_bytes[:12 + 16 * num])
    for i in range(num):
        at = 12 + 16 * i + 8
        off = struct.unpack(">I", head[at:at + 4])[0]
        head[at:at + 4] = struct.pack(">I", off + 16)        # (the collection header first)
    # 'ttcf', version 1.0, one font, at offset 16
    return b"ttcf" + struct.pack(">HHII", 1, 0, 1, 16) + bytes(head) + ttf_bytes[len(head):]


@unittest.skipIf(os.name == "nt", "the Linux font folders")
class Collections(unittest.TestCase):
    def test_a_font_installed_as_a_collection_is_used(self):
        import pymupdf
        src = _a_truetype_file()
        if not src:
            self.skipTest("no TrueType font installed")
        with open(src, "rb") as f:
            ttc = _as_collection(f.read())
        home = tempfile.mkdtemp()
        fonts = os.path.join(home, "data", "fonts")
        os.makedirs(fonts)
        path = os.path.join(fonts, "only-as-a-collection.ttc")
        with open(path, "wb") as f:
            f.write(ttc)
        name = pymupdf.Font(fontfile=path).name
        with mock.patch.object(text_edit, "font_dirs", lambda: [fonts]), \
                mock.patch.object(text_edit, "_SYSTEM_FONTS", None), \
                mock.patch.object(text_edit, "_FONT_SCAN", None):
            self.assertEqual(text_edit._font_files(fonts), [path])
            doc = pymupdf.open()
            page = doc.new_page()
            used = text_edit.add_text(page, (72, 100), "Hello", family=name)
        self.assertNotEqual(used, "helv")
        fonts_on_page = [f[3] for f in page.get_fonts()]
        self.assertTrue(any(name.split()[0] in f for f in fonts_on_page), fonts_on_page)
        self.assertEqual(page.get_text().strip(), "Hello")


@unittest.skipUnless(LINUX, "the Linux socket")
class OneWindow(unittest.TestCase):
    def listening(self):
        from PySide6.QtNetwork import QLocalServer
        name = os.path.join(tempfile.mkdtemp(), "KanzonasPDF-" + uuid.uuid4().hex[:8])
        server = QLocalServer()
        self.assertTrue(server.listen(name))
        self.addCleanup(server.close)
        return name, server

    def test_a_socket_another_user_made_gets_no_files(self):
        from kanzonas import __main__ as entry
        name, server = self.listening()
        with mock.patch.object(entry.os, "getuid", lambda: os.geteuid() + 1):
            self.assertEqual(entry.first_instance(name), (None, None))
        APP.processEvents()
        self.assertFalse(server.hasPendingConnections())          # never even connected

    def test_a_program_of_another_user_listening_gets_no_files(self):
        # (the file looks like this user's, but the kernel says who listens)
        from kanzonas import __main__ as entry
        name, server = self.listening()
        with mock.patch.object(entry, "_made_by_someone_else", lambda p: False), \
                mock.patch.object(entry.os, "getuid", lambda: os.geteuid() + 1):
            self.assertEqual(entry.first_instance(name), (None, None))

    def test_this_users_own_program_still_gets_them(self):
        from kanzonas import __main__ as entry
        name, server = self.listening()
        got, sock = entry.first_instance(name)
        self.assertIsNone(got)
        self.assertIsNotNone(sock)
        sock.disconnectFromServer()

    def test_a_runtime_folder_too_long_for_a_socket(self):
        from kanzonas.__main__ import instance_name
        deep = tempfile.mkdtemp()
        while len(deep) < 120:
            deep = os.path.join(deep, "a-rather-long-folder-name")
        os.makedirs(deep)
        with mock.patch.dict(os.environ, {"XDG_RUNTIME_DIR": deep}):
            self.assertEqual(instance_name("KanzonasPDF", "me"), "KanzonasPDF-me")


@unittest.skipUnless(LINUX, "the Linux command line")
class CommandLine(unittest.TestCase):
    def test_qt_options_are_not_files(self):
        from kanzonas.__main__ import file_arguments, without_qt_options
        args = ["-platform", "xcb", "-style", "Fusion", "/tmp/a.pdf", "-display", ":0",
                os.fsdecode(b"/tmp/caf\xe9.pdf")]
        qt = ["/tmp/a.pdf", "/tmp/caf\ufffd.pdf"]          # (what QApplication leaves)
        self.assertEqual(file_arguments(without_qt_options(args, qt)),
                         ["/tmp/a.pdf", os.fsdecode(b"/tmp/caf\xe9.pdf")])

    def test_a_real_start_with_platform_option(self):
        from kanzonas.__main__ import without_qt_options
        import subprocess
        code = ("import sys\nfrom PySide6.QtWidgets import QApplication\n"
                "app = QApplication(sys.argv)\nprint(repr(app.arguments()[1:]))\n")
        out = subprocess.run([sys.executable, "-c", code, "-platform", "offscreen",
                              "/tmp/x y.pdf"], capture_output=True, text=True, timeout=60)
        import ast
        qt = ast.literal_eval(out.stdout.strip().splitlines()[-1])
        self.assertEqual(without_qt_options(["-platform", "offscreen", "/tmp/x y.pdf"], qt),
                         ["/tmp/x y.pdf"])

    def test_file_urls_with_localhost_or_one_slash(self):
        from kanzonas.__main__ import file_arguments
        self.assertEqual(file_arguments(["file://localhost/tmp/a%20b.pdf",
                                         "file:/tmp/c.pdf",
                                         "file:///tmp/%E2%82%AC%25.pdf"]),
                         ["/tmp/a b.pdf", "/tmp/c.pdf", "/tmp/\u20ac%.pdf"])


@unittest.skipUnless(LINUX, "Linux signals")
class CtrlC(unittest.TestCase):
    def test_ctrl_c_keeps_the_files_and_a_backup_of_unsaved_changes(self):
        import subprocess
        import time
        import pymupdf
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        home = tempfile.mkdtemp()
        pdf = os.path.join(home, "plan.pdf")
        d = pymupdf.open()
        d.new_page()
        d.save(pdf)
        d.close()
        state = os.path.join(home, "state")
        user = "kzctrlc" + uuid.uuid4().hex[:8]
        env = dict(os.environ, QT_QPA_PLATFORM="offscreen", KZ_ROOT=root, KZ_PDF=pdf,
                   KZ_STATE=state, HOME=home, XDG_CONFIG_HOME=os.path.join(home, "cfg"),
                   XDG_DATA_HOME=os.path.join(home, "data"), XDG_RUNTIME_DIR="",
                   TMPDIR=home, USER=user, LOGNAME=user)
        # (as in a terminal: Python's own Ctrl+C handling, whatever this test runs under)
        child = ("import signal\nsignal.signal(signal.SIGINT, signal.default_int_handler)\n"
                 + SIGTERM_CHILD)
        p = subprocess.Popen([sys.executable, "-c", child], cwd=home, env=env,
                             stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        self.addCleanup(lambda: (p.poll() is None and p.kill(), p.wait(), p.stderr.close()))
        end = time.time() + 40
        while not os.path.exists(state) and time.time() < end and p.poll() is None:
            time.sleep(0.2)
        self.assertTrue(os.path.exists(state), "the program didn't start")
        p.send_signal(signal.SIGINT)
        try:
            code = p.wait(20)
        except subprocess.TimeoutExpired:
            code = None
        err = p.stderr.read().decode("utf-8", "replace") if code is not None else ""
        self.assertEqual(code, 0, "still running after Ctrl+C" if code is None else err)
        self.assertNotIn("KeyboardInterrupt", err)
        conf = os.path.join(home, "cfg", "KanzonasPDF", "KanzonasPDF.conf")
        with open(conf, encoding="utf-8") as f:
            self.assertIn("plan.pdf", f.read())
        backups = os.path.join(home, "data", "KanzonasPDF", "KanzonasPDF", "backups")
        self.assertTrue([n for n in os.listdir(backups) if n.endswith(".pdf")])

    def test_a_signal_set_to_be_ignored_stays_ignored(self):
        from kanzonas.__main__ import end_on_sigterm
        saved = {s: signal.getsignal(s) for s in (signal.SIGTERM, signal.SIGINT,
                                                  signal.SIGHUP)}

        def restore():
            signal.set_wakeup_fd(-1)
            r, w, notifier = getattr(APP, "_kz_sigterm", (None, None, None))
            if notifier is not None:
                notifier.setEnabled(False)
                r.close()
                w.close()
            for s, h in saved.items():
                signal.signal(s, h)
        self.addCleanup(restore)
        signal.signal(signal.SIGHUP, signal.SIG_IGN)            # (started with nohup)
        win = mock.Mock()
        self.assertIsNotNone(end_on_sigterm(APP, win))
        self.assertIs(signal.getsignal(signal.SIGHUP), signal.SIG_IGN)
        self.assertNotIn(signal.getsignal(signal.SIGINT),
                         (signal.default_int_handler, signal.SIG_DFL))


@unittest.skipUnless(LINUX, "the Linux theme")
class ThemeChange(unittest.TestCase):
    def test_the_ribbon_stays_where_it_is(self):
        from kanzonas import theme
        from kanzonas.main_window import MainWindow
        w = MainWindow()
        self.addCleanup(lambda: (setattr(w, "_close_confirmed", True), w.close()))
        w.show()
        APP.processEvents()
        before = w.ribbon_tb.layout().contentsMargins()
        start = theme._mode
        self.addCleanup(lambda: theme.apply(APP, start))
        for mode in ("dark", "system", "light", "system"):
            theme.apply(APP, mode)          # (what View > Theme does, without storing it)
            APP.processEvents()
            m = w.ribbon_tb.layout().contentsMargins()
            self.assertEqual((m.left(), m.top(), m.right(), m.bottom()),
                             (before.left(), before.top(), before.right(), before.bottom()),
                             mode)
        self.assertEqual(before.top(), 0)
        self.assertEqual(APP.style().name().lower(), "fusion")


if __name__ == "__main__":
    unittest.main()
