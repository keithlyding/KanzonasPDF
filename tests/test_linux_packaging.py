"""The Linux AppImage's packaging (packaging/linux) and the build workflow that makes and
publishes it: desktop file, AppStream metadata, the libraries left to the computer, the
runtime hook that gives programs KanzonasPDF starts their own LD_LIBRARY_PATH, the AppDir
layout, and a release that waits for both the Windows and the Linux build.

    python -m unittest tests.test_linux_packaging
"""
import configparser
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LINUX = os.path.join(ROOT, "packaging", "linux")
WORKFLOW = os.path.join(ROOT, ".github", "workflows", "build-windows.yml")

try:
    import yaml
except ImportError:             # (PyMuPDF brings PyYAML; without it the workflow isn't read)
    yaml = None


def desktop_entry():
    cp = configparser.ConfigParser(interpolation=None)
    cp.optionxform = str
    cp.read(os.path.join(LINUX, "kanzonaspdf.desktop"), encoding="utf-8")
    return cp["Desktop Entry"]


def excluded():
    with open(os.path.join(LINUX, "excludelist"), encoding="utf-8") as f:
        return {ln.split("#")[0].strip() for ln in f} - {""}


class DesktopIntegration(unittest.TestCase):
    def test_desktop_file(self):
        e = desktop_entry()
        self.assertEqual(e["Type"], "Application")
        self.assertEqual(e["Name"], "KanzonasPDF")
        self.assertEqual(e["GenericName"], "PDF Editor")
        self.assertIn("%F", e["Exec"].split())          # several files at once
        self.assertEqual(e["Icon"], "kanzonaspdf")
        self.assertEqual(e["Categories"], "Office;Viewer;Graphics;")
        self.assertIn("application/pdf", e["MimeType"].split(";"))
        self.assertEqual(e["StartupWMClass"], "KanzonasPDF")     # the window's X11 class

    def test_appstream_metadata(self):
        name = "io.github.keithlyding.kanzonaspdf.metainfo.xml"
        root = ET.parse(os.path.join(LINUX, name)).getroot()
        self.assertEqual(root.findtext("id") + ".metainfo.xml", name)   # named after its id
        self.assertEqual(root.findtext("launchable"), "kanzonaspdf.desktop")
        self.assertIn("application/pdf", [m.text for m in root.iter("mediatype")])
        self.assertEqual(root.find("releases/release").get("version"), "@VERSION@")

    def test_icon_is_256_pixels(self):
        with open(os.path.join(ROOT, "assets", "kanzonas.png"), "rb") as f:
            head = f.read(24)
        self.assertEqual(head[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual((int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big")),
                         (256, 256))


class LibrariesLeftToTheComputer(unittest.TestCase):
    def test_system_libraries_are_not_bundled(self):
        names = excluded()
        for lib in ("libc.so.6", "ld-linux-x86-64.so.2", "libm.so.6", "libGL.so.1",
                    "libEGL.so.1", "libfontconfig.so.1", "libstdc++.so.6", "libglib-2.0.so.0"):
            self.assertIn(lib, names)

    def test_speech_client_is_the_computers(self):
        # Read aloud: libspeechd goes with the computer's speech-dispatcher service; Qt's
        # plugin for it is bundled, and may find it missing without failing the build
        self.assertIn("libspeechd.so.2", excluded())
        sys.path.insert(0, LINUX)
        try:
            import make_appimage
        finally:
            sys.path.remove(LINUX)
        self.assertIn("texttospeech/libqtexttospeech_speechd.so", make_appimage.OPTIONAL_PLUGINS)

    def test_what_desktops_may_lack_stays_bundled(self):
        # Qt's X11 platform needs these and many desktops don't install them
        names = excluded()
        for lib in ("libxcb-cursor.so.0", "libxkbcommon-x11.so.0", "libxkbcommon.so.0",
                    "libxcb-icccm.so.4", "libQt6Core.so.6", "libpython3.12.so.1.0"):
            self.assertNotIn(lib, names)


class RuntimeHook(unittest.TestCase):
    """PyInstaller starts the program with LD_LIBRARY_PATH set to its own folder; programs
    KanzonasPDF starts (xdg-open, a browser) must get the user's own value back."""

    def run_hook(self, env):
        code = ("import os, runpy; runpy.run_path(%r); "
                "print(repr(os.environ.get('LD_LIBRARY_PATH'))); "
                "print(repr(os.environ.get('LD_LIBRARY_PATH_ORIG')))"
                % os.path.join(LINUX, "pyi_rth_linux_env.py"))
        full = {k: v for k, v in os.environ.items() if not k.startswith("LD_LIBRARY_PATH")}
        full.update(env)
        out = subprocess.run([sys.executable, "-c", code], env=full, capture_output=True,
                             text=True, check=True).stdout.split()
        return out[0], out[1]

    def test_the_users_value_comes_back(self):
        self.assertEqual(self.run_hook({"LD_LIBRARY_PATH": "/app/_internal:/opt/mine",
                                        "LD_LIBRARY_PATH_ORIG": "/opt/mine"}),
                         ("'/opt/mine'", "None"))

    def test_none_when_the_user_had_none(self):
        self.assertEqual(self.run_hook({"LD_LIBRARY_PATH": "/app/_internal"}), ("None", "None"))


@unittest.skipUnless(sys.platform.startswith("linux") and shutil.which("objdump")
                     and shutil.which("ldd"), "Linux with binutils")
class AppDir(unittest.TestCase):
    def test_appdir_layout_and_pruning(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        dist = os.path.join(tmp, "KanzonasPDF")
        os.makedirs(os.path.join(dist, "_internal"))
        shutil.copy2(shutil.which("true"), os.path.join(dist, "KanzonasPDF"))   # an ELF program
        for n in ("libc.so.6", "libstdc++.so.6", "libxcb-cursor.so.0"):
            with open(os.path.join(dist, "_internal", n), "w") as f:
                f.write("not really a library")
        for n in ("LICENSE.txt", "NOTICE.txt"):
            with open(os.path.join(dist, n), "w") as f:
                f.write(n)
        appdir = os.path.join(tmp, "AppDir")
        r = subprocess.run([sys.executable, os.path.join(LINUX, "make_appimage.py"), dist, appdir,
                            "--version", "9.9"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        lib = os.path.join(appdir, "usr", "lib", "KanzonasPDF")
        self.assertTrue(os.access(os.path.join(appdir, "AppRun"), os.X_OK))
        for p in ("kanzonaspdf.desktop", "kanzonaspdf.png", ".DirIcon",
                  "usr/share/applications/kanzonaspdf.desktop",
                  "usr/share/icons/hicolor/256x256/apps/kanzonaspdf.png",
                  "usr/share/doc/kanzonaspdf/LICENSE.txt", "usr/share/doc/kanzonaspdf/NOTICE.txt",
                  "usr/lib/KanzonasPDF/KanzonasPDF", "usr/lib/KanzonasPDF/NOTICE.txt"):
            self.assertTrue(os.path.exists(os.path.join(appdir, p)), p)
        internal = os.listdir(os.path.join(lib, "_internal"))
        self.assertEqual(internal, ["libxcb-cursor.so.0"])          # the others removed
        with open(os.path.join(appdir, "usr", "share", "metainfo",
                               "io.github.keithlyding.kanzonaspdf.metainfo.xml")) as f:
            self.assertIn('version="9.9"', f.read())

    def test_no_license_no_appimage(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        dist = os.path.join(tmp, "KanzonasPDF")
        os.makedirs(dist)
        shutil.copy2(shutil.which("true"), os.path.join(dist, "KanzonasPDF"))
        r = subprocess.run([sys.executable, os.path.join(LINUX, "make_appimage.py"), dist,
                            os.path.join(tmp, "AppDir"), "--version", "9.9"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn("license files missing", r.stderr)


@unittest.skipIf(yaml is None, "PyYAML isn't installed")
class Workflow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(WORKFLOW, encoding="utf-8") as f:
            cls.wf = yaml.safe_load(f)
        cls.jobs = cls.wf["jobs"]

    def run_text(self, job):
        return "\n".join(s.get("run", "") for s in self.jobs[job]["steps"])

    def test_one_set_of_pyinstaller_options(self):
        self.assertIn("--collect-data kanzonas", self.wf["env"]["PYINSTALLER_OPTIONS"])
        for job in ("build", "linux"):
            self.assertIn("python -m PyInstaller ${{ env.PYINSTALLER_OPTIONS }}", self.run_text(job))

    def test_the_appimage_is_tested_before_it_can_be_published(self):
        linux = self.run_text("linux")
        self.assertEqual(self.jobs["linux"]["runs-on"], "ubuntu-22.04")      # oldest supported
        self.assertIn("--appimage-extract-and-run --selftest selftest-linux.log", linux)
        self.assertIn("grep -q '^FAIL' selftest-linux.log", linux)
        self.assertIn("smoke_test.sh ./KanzonasPDF-x86_64.AppImage --appimage-extract-and-run", linux)
        self.assertIn('python -m unittest discover -s tests -p "test_*.py" -t .', linux)

    def test_the_release_waits_for_both_builds_and_carries_the_appimage(self):
        pub = self.jobs["publish"]
        self.assertEqual(sorted(pub["needs"]), ["build", "linux", "macos"])
        self.assertIn("refs/heads/main", pub["if"])
        self.assertIn("refs/tags/v", pub["if"])
        names = [s.get("name") for s in pub["steps"]]
        for n in ("Is this version already released?", "Is the tagged commit on main?",
                  "Checksums (SHA-256) of the downloads", "Publish release"):
            self.assertIn(n, names)
        sums = [s for s in pub["steps"] if s.get("name") == "Checksums (SHA-256) of the downloads"][0]
        self.assertIn("KanzonasPDF-x86_64.AppImage", sums["run"])
        rel = [s for s in pub["steps"] if s.get("name") == "Publish release"][0]["with"]
        self.assertIn("release/KanzonasPDF-x86_64.AppImage", rel["files"])
        self.assertIn("SHA256SUMS.txt", rel["files"])
        self.assertIn("${{ steps.sums.outputs.text }}", rel["body"])
        # (nothing in the build jobs publishes)
        for job in ("build", "linux", "macos"):
            for s in self.jobs[job]["steps"]:
                self.assertNotIn("action-gh-release", s.get("uses", ""))


if __name__ == "__main__":
    unittest.main()
