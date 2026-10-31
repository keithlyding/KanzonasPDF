"""Update now for an installed copy: the release's setup is downloaded into a private new
folder, checked against its sha256, and run quietly over the installation (for the current
user or all users, as installed) with /RELAUNCH so KanzonasPDF starts again; a wrong download
is thrown away. The Windows build runs the same setup command line over an older install.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_installed_update
"""
import hashlib
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEventLoop, QTimer, QUrl  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import updates  # noqa: E402

SETUP = b"MZ pretend setup " * 1000


def release(version="9.9", digest=None, host="github.com"):
    name = updates.setup_name(version)
    return {"tag_name": "v" + version, "assets": [
        {"name": name, "browser_download_url": "https://%s/x/releases/download/v%s/%s"
         % (host, version, name),
         "digest": "sha256:" + (digest or hashlib.sha256(SETUP).hexdigest())},
        {"name": updates.PORTABLE_ZIP, "browser_download_url":
         "https://github.com/x/releases/download/v%s/%s" % (version, updates.PORTABLE_ZIP),
         "digest": "sha256:" + "0" * 64}]}


class Pieces(unittest.TestCase):
    def test_the_setup_of_a_release(self):
        self.assertEqual(updates.setup_name("1.6"), "KanzonasPDF-v1.6-setup.exe")
        r = release()
        self.assertTrue(updates.asset_url(r, updates.setup_name("9.9")).endswith(
            "KanzonasPDF-v9.9-setup.exe"))
        self.assertEqual(updates.asset_digest(r, updates.setup_name("9.9")),
                         hashlib.sha256(SETUP).hexdigest())
        # only from GitHub, only with a published digest
        self.assertIsNone(updates.asset_url(release(host="evil.example"), updates.setup_name("9.9")))

    def test_who_it_was_installed_for(self):
        with mock.patch.dict(os.environ, {"ProgramFiles": "/pf", "ProgramW6432": "/pf",
                                          "ProgramFiles(x86)": "/pf86"}):
            self.assertTrue(updates.for_all_users("/pf/KanzonasPDF"))
            self.assertTrue(updates.for_all_users("/pf86/KanzonasPDF"))
            self.assertFalse(updates.for_all_users("/home/me/AppData/Local/Programs/KanzonasPDF"))
            self.assertFalse(updates.for_all_users("/pfx/KanzonasPDF"))     # not a prefix trick

    def test_the_setup_runs_quietly_over_the_installation_and_restarts_the_app(self):
        with mock.patch.dict(os.environ, {"ProgramFiles": "/pf"}):
            mine = updates.installer_command("/t/setup.exe", "/home/me/Programs/KanzonasPDF")
            everyone = updates.installer_command("/t/setup.exe", "/pf/KanzonasPDF")
        self.assertEqual(mine, ["/t/setup.exe", "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART",
                                "/SP-", "/CLOSEAPPLICATIONS", "/CURRENTUSER", "/RELAUNCH"])
        self.assertIn("/ALLUSERS", everyone)
        self.assertNotIn("/CURRENTUSER", everyone)
        # the Windows build tests this same command line, and the setup knows /RELAUNCH
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(root, ".github", "workflows", "build-windows.yml")) as f:
            self.assertIn('"/SILENT","/SUPPRESSMSGBOXES","/NORESTART","/SP-",'
                          '"/CLOSEAPPLICATIONS","/CURRENTUSER","/RELAUNCH"', f.read())
        with open(os.path.join(root, "installer", "KanzonasPDF.iss")) as f:
            iss = f.read()
        self.assertIn("Check: RelaunchAfterUpdate", iss)
        self.assertIn("'/RELAUNCH'", iss)

    def test_only_an_installed_windows_program_updates_this_way(self):
        d = tempfile.mkdtemp()
        self.assertFalse(updates.can_install_update(d))                  # not Windows, not frozen
        with mock.patch.object(updates.os, "name", "nt"), \
                mock.patch.object(sys, "frozen", True, create=True), \
                mock.patch("kanzonas.paths.is_portable", lambda: False):
            self.assertFalse(updates.can_install_update(d))              # no uninstaller here
            open(os.path.join(d, "unins000.exe"), "wb").close()
            self.assertTrue(updates.can_install_update(d))
            with mock.patch("kanzonas.paths.is_portable", lambda: True):
                self.assertFalse(updates.can_install_update(d))          # portable: its own way


class Download(unittest.TestCase):
    def fetch(self, digest):
        src = os.path.join(tempfile.mkdtemp(), "setup.exe")
        with open(src, "wb") as f:
            f.write(SETUP)
        from PySide6.QtCore import QObject
        holder = QObject()                  # owns the download, as the main window does
        self.addCleanup(lambda: (holder.deleteLater(), APP.processEvents()))
        dl = updates.InstallerUpdater(QUrl.fromLocalFile(src).toString(), "9.9", holder,
                                      expected_sha256=digest)
        self._holder = holder
        out = {}
        loop = QEventLoop()
        dl.ready.connect(lambda p: (out.setdefault("ready", p), loop.quit()))
        dl.failed.connect(lambda m: (out.setdefault("failed", m), loop.quit()))
        QTimer.singleShot(10000, loop.quit)
        dl.start()
        if not out:
            loop.exec()
        return dl, out

    def test_a_checked_setup_is_kept_in_a_new_private_folder(self):
        dl, out = self.fetch(hashlib.sha256(SETUP).hexdigest())
        path = out.get("ready")
        self.assertTrue(path and os.path.exists(path), out)
        self.assertEqual(os.path.basename(path), "KanzonasPDF-v9.9-setup.exe")
        self.assertTrue(os.path.basename(os.path.dirname(path)).startswith("kzsetup"))
        with open(path, "rb") as f:
            self.assertEqual(f.read(), SETUP)

    def test_a_wrong_download_is_thrown_away(self):
        dl, out = self.fetch("1" * 64)
        self.assertIn("sha256", out.get("failed", ""))
        self.assertFalse(os.path.exists(dl.path))

    def test_no_digest_no_download(self):
        dl, out = self.fetch(None)
        self.assertIn("digest", out.get("failed", ""))


class UpdateNow(unittest.TestCase):
    def test_update_now_closes_and_runs_the_setup(self):
        from kanzonas.main_window import MainWindow
        w = MainWindow()
        self.addCleanup(lambda: (setattr(w, "_close_confirmed", True), w.close()))
        w._upd = mock.Mock(release=release())
        setup = os.path.join(tempfile.mkdtemp(prefix="kzsetup"), "KanzonasPDF-v9.9-setup.exe")
        open(setup, "wb").close()

        class FakeDownload:
            def __init__(self, url, version, parent=None, expected_sha256=None):
                FakeDownload.args = (url, version, expected_sha256)
                from PySide6.QtCore import QObject, Signal

                class S(QObject):
                    progress = Signal(int, int)
                    ready = Signal(str)
                    failed = Signal(str)
                self.s = S()
                self.progress, self.ready, self.failed = self.s.progress, self.s.ready, self.s.failed

            def start(self):
                self.ready.emit(setup)

            def cancel(self):
                pass
        with mock.patch.object(updates, "can_self_update", lambda: False), \
                mock.patch.object(updates, "can_install_update", lambda app_dir=None: True), \
                mock.patch.object(updates, "InstallerUpdater", FakeDownload), \
                mock.patch.object(w, "close", lambda: True), \
                mock.patch("subprocess.Popen") as popen, \
                mock.patch.object(QApplication, "quit") as quit_:
            self.assertTrue(w._self_update_url().endswith("KanzonasPDF-v9.9-setup.exe"))
            self.assertIn("installs the new version", w._update_now_text())
            w.update_now()
        self.assertEqual(FakeDownload.args[1], "9.9")
        self.assertEqual(FakeDownload.args[2], hashlib.sha256(SETUP).hexdigest())
        cmd = popen.call_args[0][0]
        self.assertEqual(cmd[0], setup)
        self.assertIn("/RELAUNCH", cmd)
        self.assertTrue(quit_.called)

    def test_keeping_a_document_open_cancels_and_cleans_up(self):
        from kanzonas.main_window import MainWindow
        w = MainWindow()
        self.addCleanup(lambda: (setattr(w, "_close_confirmed", True), w.close()))
        w._upd = mock.Mock(release=release())
        folder = tempfile.mkdtemp(prefix="kzsetup")
        setup = os.path.join(folder, "KanzonasPDF-v9.9-setup.exe")
        open(setup, "wb").close()

        class FakeDownload:
            def __init__(self, *a, **k):
                from PySide6.QtCore import QObject, Signal

                class S(QObject):
                    progress = Signal(int, int)
                    ready = Signal(str)
                    failed = Signal(str)
                self.s = S()
                self.progress, self.ready, self.failed = self.s.progress, self.s.ready, self.s.failed

            def start(self):
                self.ready.emit(setup)

            def cancel(self):
                pass
        with mock.patch.object(updates, "can_self_update", lambda: False), \
                mock.patch.object(updates, "can_install_update", lambda app_dir=None: True), \
                mock.patch.object(updates, "InstallerUpdater", FakeDownload), \
                mock.patch.object(w, "close", lambda: False), \
                mock.patch("subprocess.Popen") as popen:
            w.update_now()
        self.assertFalse(popen.called)
        self.assertFalse(os.path.exists(folder))


if __name__ == "__main__":
    unittest.main()
