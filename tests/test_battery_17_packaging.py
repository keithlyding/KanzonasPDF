"""1.7 battery: the Linux AppImage's packaging, release pipeline and self-update, attacked.

- The download of a new AppImage never writes through a file someone else put in the
  AppImage's folder first (a link to another of the user's files, in a shared folder), and
  is private to this user until it is checked and put in place.
- A download far bigger than any AppImage stops (it would fill the disk the AppImage is on).
- The new AppImage never becomes changeable by other users because the old one was.
- The compatibility check of make_appimage.py fails for every version of the libraries it
  leaves to the computer (glibc, libstdc++ and its C++ ABI, libgcc_s), not only some.
- The AppStream metadata passes the build machine's own (older, stricter) validator.
- The workflow: only the publish job may write to the repository, a publish is never
  cancelled halfway by a newer push to main, and SHA256SUMS.txt lists every download.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_battery_17_packaging
"""
import hashlib
import http.server
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEventLoop, QObject, QTimer, QUrl  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import updates  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LINUX_DIR = os.path.join(ROOT, "packaging", "linux")
WORKFLOW = os.path.join(ROOT, ".github", "workflows", "build-windows.yml")
LINUX = sys.platform.startswith("linux")

NEW_APPIMAGE = b"\x7fELF\x02\x01\x01\x00AI\x02" + b"new version " * 2000
OLD_APPIMAGE = b"\x7fELF\x02\x01\x01\x00AI\x02" + b"old version " * 10

try:
    import yaml
except ImportError:
    yaml = None


def appimage_in(folder, data=OLD_APPIMAGE, mode=0o755):
    path = os.path.join(folder, updates.APPIMAGE)
    with open(path, "wb") as f:
        f.write(data)
    os.chmod(path, mode)
    return path


def download(url, target, digest):
    """Runs an AppImageUpdater to its end: {'ready': path} or {'failed': message}."""
    holder = QObject()
    dl = updates.AppImageUpdater(url, target, holder, expected_sha256=digest)
    out = {}
    loop = QEventLoop()
    dl.ready.connect(lambda p: (out.setdefault("ready", p), loop.quit()))
    dl.failed.connect(lambda m: (out.setdefault("failed", m), loop.quit()))
    QTimer.singleShot(20000, loop.quit)
    dl.start()
    if not out:
        loop.exec()
    holder.deleteLater()
    APP.processEvents()
    return out


@unittest.skipUnless(LINUX, "the Linux AppImage")
class DownloadFile(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.target = appimage_in(self.dir)
        src_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, src_dir, True)
        self.src = os.path.join(src_dir, "download")
        with open(self.src, "wb") as f:
            f.write(NEW_APPIMAGE)
        self.url = QUrl.fromLocalFile(self.src).toString()
        self.digest = hashlib.sha256(NEW_APPIMAGE).hexdigest()

    def test_a_link_planted_where_the_download_goes_is_never_written_through(self):
        # someone who can add files to the folder (a shared or sticky one) guesses the name
        # the download used (the process id) and links it to another of the user's files
        victim = os.path.join(tempfile.mkdtemp(), "bashrc")
        self.addCleanup(shutil.rmtree, os.path.dirname(victim), True)
        with open(victim, "w") as f:
            f.write("the user's own file\n")
        planted = os.path.join(self.dir, ".%s.update-%d" % (updates.APPIMAGE, os.getpid()))
        os.symlink(victim, planted)
        out = download(self.url, self.target, self.digest)
        with open(victim) as f:
            self.assertEqual(f.read(), "the user's own file\n")
        path = out.get("ready")
        self.assertTrue(path, out)
        self.assertFalse(os.path.islink(path))
        with open(path, "rb") as f:
            self.assertEqual(f.read(), NEW_APPIMAGE)

    def test_the_download_is_private_until_it_is_in_place(self):
        out = download(self.url, self.target, self.digest)
        path = out.get("ready")
        self.assertTrue(path, out)
        st = os.lstat(path)
        self.assertTrue(stat.S_ISREG(st.st_mode))
        self.assertEqual(st.st_uid, os.getuid())
        self.assertEqual(stat.S_IMODE(st.st_mode) & 0o077, 0)     # nobody else may change it
        self.assertEqual(os.path.dirname(path), self.dir)         # same disk: one rename
        os.remove(path)


class _Endless(http.server.BaseHTTPRequestHandler):
    """Sends AppImage-looking bytes until the client goes away (at most 64 MB)."""
    sent = 0
    content_length = None

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        if self.content_length is not None:
            self.send_header("Content-Length", str(self.content_length))
        self.end_headers()
        chunk = NEW_APPIMAGE[:11] + b"\0" * (64 * 1024 - 11)
        try:
            for _ in range(1024):
                self.wfile.write(chunk)
                type(self).sent += len(chunk)
                chunk = b"\0" * (64 * 1024)
                time.sleep(0.002)       # (as over a network: ~30 MB/s)
        except OSError:
            pass

    def log_message(self, *args):
        pass


@unittest.skipUnless(LINUX, "the Linux AppImage")
class HugeDownload(unittest.TestCase):
    def serve(self, content_length=None):
        handler = type("H", (_Endless,), {"sent": 0, "content_length": content_length})
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return "http://127.0.0.1:%d/KanzonasPDF-x86_64.AppImage" % server.server_port, handler

    def check_stops(self, content_length):
        folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, folder, True)
        target = appimage_in(folder)
        url, handler = self.serve(content_length)
        with mock.patch.object(updates, "APPIMAGE_MAX_BYTES", 2 * 1024 * 1024, create=True):
            out = download(url, target, "ab" * 32)
        self.assertIn("failed", out)
        self.assertNotIn("sha256", out["failed"])                 # stopped, not finished
        self.assertLess(handler.sent, 32 * 1024 * 1024)
        self.assertEqual(os.listdir(folder), [updates.APPIMAGE])  # nothing left behind

    def test_a_download_without_end_stops(self):
        self.check_stops(None)

    def test_a_download_that_says_it_is_huge_stops(self):
        self.check_stops(64 * 1024 * 1024)

    def test_one_that_had_all_come_when_stopped_is_not_kept(self):
        folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, folder, True)
        target = appimage_in(folder)
        src = os.path.join(folder, "..", os.path.basename(folder) + "-src")
        with open(src, "wb") as f:
            f.write(NEW_APPIMAGE)
        self.addCleanup(os.remove, src)
        with mock.patch.object(updates, "APPIMAGE_MAX_BYTES", 1000, create=True):
            out = download(QUrl.fromLocalFile(os.path.abspath(src)).toString(), target,
                           hashlib.sha256(NEW_APPIMAGE).hexdigest())
        self.assertIn("bigger", out.get("failed", ""), out)
        self.assertEqual(os.listdir(folder), [updates.APPIMAGE])

    def test_the_limit_is_far_above_a_real_appimage(self):
        self.assertGreaterEqual(updates.APPIMAGE_MAX_BYTES, 1000 * 1000 * 1000)


@unittest.skipUnless(LINUX, "Linux file modes")
class ReplaceModes(unittest.TestCase):
    def test_the_new_appimage_is_never_changeable_by_others(self):
        folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, folder, True)
        target = appimage_in(folder, mode=0o777)
        os.chmod(target, 0o777)
        new = os.path.join(folder, ".new")
        with open(new, "wb") as f:
            f.write(NEW_APPIMAGE)
        updates.replace_appimage(new, target)
        self.assertEqual(stat.S_IMODE(os.stat(target).st_mode), 0o755)


# ------------------------------------------------------------------------------------------
# make_appimage.py: the newest versions of the computer's libraries the bundle may need

OBJDUMP = """
%s:     file format elf64-x86-64

Dynamic Section:
  NEEDED               libc.so.6

Version References:
%s
"""


@unittest.skipUnless(LINUX and shutil.which("ldd") and shutil.which("true"), "Linux")
class CompatibilityCheck(unittest.TestCase):
    """make_appimage.py with a stand-in objdump that reports chosen version needs."""

    def run_check(self, refs, *limits):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        dist = os.path.join(tmp, "KanzonasPDF")
        os.makedirs(os.path.join(dist, "_internal"))
        shutil.copy2(shutil.which("true"), os.path.join(dist, "KanzonasPDF"))
        for n in ("LICENSE.txt", "NOTICE.txt"):
            with open(os.path.join(dist, n), "w") as f:
                f.write(n)
        bindir = os.path.join(tmp, "bin")
        os.makedirs(bindir)
        report = os.path.join(tmp, "objdump.txt")
        with open(report, "w") as f:
            f.write(OBJDUMP % ("KanzonasPDF", "\n".join(
                "  required from %s:\n    0x0 0x00 02 %s" % (lib, v) for lib, v in refs)))
        fake = os.path.join(bindir, "objdump")
        with open(fake, "w") as f:
            f.write('#!/bin/sh\ncat "%s"\n' % report)
        os.chmod(fake, 0o755)
        env = dict(os.environ, PATH=bindir + os.pathsep + os.environ.get("PATH", ""))
        r = subprocess.run([sys.executable, os.path.join(LINUX_DIR, "make_appimage.py"), dist,
                            os.path.join(tmp, "AppDir"), "--version", "9.9"] + list(limits),
                           capture_output=True, text=True, env=env)
        return r.returncode, r.stdout + r.stderr

    LIMITS = ("--max-glibc", "2.35", "--max-glibcxx", "3.4.30", "--max-cxxabi", "1.3.13",
              "--max-libgcc", "12.0.0")
    OK = [("libc.so.6", "GLIBC_2.34"), ("libstdc++.so.6", "GLIBCXX_3.4.30"),
          ("libstdc++.so.6", "CXXABI_1.3.13"), ("libgcc_s.so.1", "GCC_12.0.0")]

    def test_needs_the_oldest_system_has_pass(self):
        code, out = self.run_check(self.OK, *self.LIMITS)
        self.assertEqual(code, 0, out)

    def test_a_newer_glibc_fails(self):
        code, out = self.run_check(self.OK + [("libc.so.6", "GLIBC_2.38")], *self.LIMITS)
        self.assertEqual(code, 1, out)
        self.assertIn("GLIBC_2.38", out)

    def test_a_newer_libstdcxx_fails(self):
        code, out = self.run_check(self.OK + [("libstdc++.so.6", "GLIBCXX_3.4.32")],
                                   *self.LIMITS)
        self.assertEqual(code, 1, out)
        self.assertIn("GLIBCXX_3.4.32", out)

    def test_a_newer_cxx_abi_fails(self):
        # GCC 14 code calls __cxa_call_terminate@CXXABI_1.3.15 without needing any newer
        # GLIBCXX version: Ubuntu 22.04's libstdc++ (GCC 12) doesn't have it
        code, out = self.run_check(self.OK + [("libstdc++.so.6", "CXXABI_1.3.15")],
                                   *self.LIMITS)
        self.assertEqual(code, 1, out)
        self.assertIn("CXXABI_1.3.15", out)

    def test_a_newer_libgcc_fails(self):
        code, out = self.run_check(self.OK + [("libgcc_s.so.1", "GCC_14.0.0")], *self.LIMITS)
        self.assertEqual(code, 1, out)
        self.assertIn("GCC_14.0.0", out)

    def test_packed_relocations_need_glibc_2_36(self):
        # (-z pack-relative-relocs: a version with no number, which glibc 2.35 doesn't have)
        code, out = self.run_check(self.OK + [("libc.so.6", "GLIBC_ABI_DT_RELR")], *self.LIMITS)
        self.assertEqual(code, 1, out)
        self.assertIn("GLIBC_ABI_DT_RELR", out)

    def test_the_workflow_sets_every_limit(self):
        with open(WORKFLOW, encoding="utf-8") as f:
            text = f.read()
        for opt, var in (("--max-glibc", "MAX_GLIBC"), ("--max-glibcxx", "MAX_GLIBCXX"),
                         ("--max-cxxabi", "MAX_CXXABI"), ("--max-libgcc", "MAX_LIBGCC")):
            self.assertIn('%s "$%s"' % (opt, var), text)
        self.assertIn('MAX_CXXABI: "1.3.13"', text)          # GCC 12 (Ubuntu 22.04, Debian 12)
        self.assertIn('MAX_LIBGCC: "12.0.0"', text)


class AppStreamOnTheBuildMachine(unittest.TestCase):
    """The build checks the metadata with Ubuntu 22.04's appstreamcli (AppStream 0.15.2),
    which fails the check on warnings too (newer versions only on errors)."""

    def test_only_url_types_appstream_0_15_knows(self):
        import xml.etree.ElementTree as ET
        root = ET.parse(os.path.join(
            LINUX_DIR, "io.github.keithlyding.kanzonaspdf.metainfo.xml")).getroot()
        known = {"homepage", "bugtracker", "faq", "help", "donation", "translate", "contact"}
        for url in root.iter("url"):
            # (any other: "url-invalid-type", a warning, so the Linux build fails)
            self.assertIn(url.get("type"), known)


# ------------------------------------------------------------------------------------------
# the workflow

@unittest.skipIf(yaml is None, "PyYAML isn't installed")
class Workflow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(WORKFLOW, encoding="utf-8") as f:
            cls.wf = yaml.safe_load(f)
        cls.jobs = cls.wf["jobs"]

    def test_only_the_publish_job_may_write(self):
        # the build jobs run tests and install packages: a token that can push to main (and
        # so publish a release) must not be within their reach
        self.assertEqual(self.wf["permissions"], {"contents": "read"})
        for job in ("build", "linux"):
            self.assertNotEqual((self.jobs[job].get("permissions") or {}).get("contents"),
                                "write", job)
        self.assertEqual(self.jobs["publish"]["permissions"], {"contents": "write"})

    def test_a_push_to_main_never_cancels_a_release_halfway(self):
        # the release is made and its files uploaded one by one: cancelled in between, it
        # stays without some downloads (and the next run, same version, skips it)
        cancel = str(self.wf["concurrency"]["cancel-in-progress"])
        self.assertIn("refs/heads/main", cancel)
        self.assertIn("!=", cancel)

    def test_the_checksums_list_every_download(self):
        steps = {s.get("name"): s for s in self.jobs["publish"]["steps"]}
        sums = steps["Checksums (SHA-256) of the downloads"]
        files = steps["Publish release"]["with"]["files"]
        for line in files.strip().splitlines():
            name = os.path.basename(line.strip())
            if name != "SHA256SUMS.txt":
                self.assertIn(name.replace("${{ env.VERSION }}", "$VERSION"), sums["run"], name)


if __name__ == "__main__":
    unittest.main()
