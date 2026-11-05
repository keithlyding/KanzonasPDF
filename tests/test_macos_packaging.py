"""The macOS app's packaging (packaging/macos) and the build workflow's macos job: Info.plist
(bundle id, version, PDF as a document type, the oldest macOS), the icon, the Mach-O checks
(code for the right kind of Mac, nothing needing a newer macOS), no Intel-only pins left, and
a release that waits for the Apple silicon build and carries its disk image (unsigned, with
Open Anyway explained; signing ready but off). No Intel Mac build, the owner's decision.

    python -m unittest tests.test_macos_packaging
"""
import os
import plistlib
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAC = os.path.join(ROOT, "packaging", "macos")
WORKFLOW = os.path.join(ROOT, ".github", "workflows", "build-windows.yml")
sys.path.insert(0, ROOT)
sys.path.insert(0, MAC)

import make_app  # noqa: E402

try:
    import yaml
except ImportError:             # (PyMuPDF brings PyYAML; without it the workflow isn't read)
    yaml = None


def version():
    with open(os.path.join(ROOT, "kanzonas", "__init__.py"), encoding="utf-8") as f:
        return re.search(r'__version__ = "([^"]+)"', f.read()).group(1)


def macho(cpu, minos=(14, 0, 0), legacy=False):
    """A tiny 64-bit Mach-O file for cpu ('arm64' / 'x86_64') needing macOS minos."""
    v = (minos[0] << 16) | (minos[1] << 8) | minos[2]
    if legacy:
        cmd = struct.pack("<IIII", make_app.LC_VERSION_MIN_MACOSX, 16, v, v)
    else:
        cmd = struct.pack("<IIIIII", make_app.LC_BUILD_VERSION, 24, make_app.PLATFORM_MACOS,
                          v, v, 0)
    head = struct.pack("<IiiIIIII", make_app.MH_MAGIC_64, make_app.CPU[cpu], 0, 2, 1,
                       len(cmd), 0, 0)
    return head + cmd


def fat(*slices):
    """A universal file of the thin files given as (cpu, data)."""
    off = 4096
    head = struct.pack(">II", make_app.FAT_MAGIC, len(slices))
    body = b""
    for cpu, data in slices:
        head += struct.pack(">iiIII", make_app.CPU[cpu], 0, off + len(body), len(data), 12)
        body += data
    return head + b"\0" * (off - len(head)) + body


def fake_app(folder, binaries):
    """A KanzonasPDF.app as PyInstaller lays it out, with the given Mach-O files
    ({path in Contents: bytes})."""
    app = os.path.join(folder, "KanzonasPDF.app")
    for rel, data in binaries.items():
        p = os.path.join(app, "Contents", rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as f:
            f.write(data)
    os.makedirs(os.path.join(app, "Contents", "Resources"), exist_ok=True)
    with open(os.path.join(app, "Contents", "Resources", "generated-1a2b.icns"), "wb") as f:
        f.write(b"icns")
    with open(os.path.join(app, "Contents", "Info.plist"), "wb") as f:
        plistlib.dump({"CFBundleExecutable": "KanzonasPDF", "CFBundleIconFile": "generated-1a2b.icns",
                       "CFBundleIdentifier": "KanzonasPDF", "CFBundleShortVersionString": "0.0.0",
                       "LSBackgroundOnly": False}, f)
    lic = os.path.join(folder, "licenses")
    os.makedirs(lic, exist_ok=True)
    for name in make_app.LICENSES:
        with open(os.path.join(lic, name), "w") as f:
            f.write(name)
    return app, lic


class InfoPlist(unittest.TestCase):
    def test_entries(self):
        from kanzonas import macos
        info = make_app.info_plist({"CFBundleExecutable": "KanzonasPDF", "Other": 1}, "1.9", "14.0")
        self.assertEqual(info["CFBundleIdentifier"], macos.BUNDLE_ID)
        self.assertEqual(info["CFBundleShortVersionString"], "1.9")
        self.assertEqual(info["CFBundleVersion"], "1.9")
        self.assertEqual(info["LSMinimumSystemVersion"], "14.0")
        self.assertEqual(info["CFBundleIconFile"], "KanzonasPDF.icns")
        self.assertTrue(info["NSHighResolutionCapable"])
        self.assertFalse(info["NSRequiresAquaSystemAppearance"])          # dark mode
        self.assertEqual(info["Other"], 1)                                  # PyInstaller's kept
        pdf, = info["CFBundleDocumentTypes"]
        self.assertEqual(pdf["LSItemContentTypes"], ["com.adobe.pdf"])
        self.assertIn(pdf["LSHandlerRank"], ("Default", "Owner", "Alternate"))
        self.assertIn(pdf["CFBundleTypeRole"], ("Editor", "Viewer"))
        plistlib.dumps(info)                                                # writable

    def test_the_bundle_id_matches_linuxs_metadata(self):
        from kanzonas import macos
        self.assertTrue(os.path.exists(os.path.join(
            ROOT, "packaging", "linux", macos.BUNDLE_ID + ".metainfo.xml")))
        self.assertEqual(make_app.BUNDLE_ID, macos.BUNDLE_ID)


class Icon(unittest.TestCase):
    def test_icns_from_the_icon_sources(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "KanzonasPDF.icns")
            make_app.make_icns(out)
            with open(out, "rb") as f:
                self.assertEqual(f.read(4), b"icns")
            with Image.open(out) as im:
                sizes = {s[0] * s[2] for s in im.info["sizes"]}
            self.assertTrue({16, 32, 256, 512, 1024} <= sizes | {16}, sizes)

    def test_small_sizes_from_the_small_source(self):
        imgs = make_app.icon_images(
            os.path.join(ROOT, "assets", "kanzonas-icon-source.png"),
            os.path.join(ROOT, "assets", "kanzonas-icon-small-source.png"))
        self.assertEqual(sorted(imgs), list(make_app.ICON_SIZES))
        self.assertEqual(imgs[1024].size, (1024, 1024))


class MachO(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, True)

    def write(self, name, data):
        p = os.path.join(self.dir, name)
        with open(p, "wb") as f:
            f.write(data)
        return p

    def test_reading_thin_and_universal_files(self):
        self.assertEqual(make_app.macho_info(self.write("a", macho("arm64", (14, 0, 0)))),
                         {"arm64": (14, 0, 0)})
        self.assertEqual(make_app.macho_info(self.write("b", macho("x86_64", (10, 13, 0), True))),
                         {"x86_64": (10, 13, 0)})
        both = fat(("x86_64", macho("x86_64", (10, 9, 0))), ("arm64", macho("arm64", (11, 0, 0))))
        self.assertEqual(make_app.macho_info(self.write("c", both)),
                         {"x86_64": (10, 9, 0), "arm64": (11, 0, 0)})
        self.assertIsNone(make_app.macho_info(self.write("d", b"%PDF-1.7 not a program")))
        java = b"\xca\xfe\xba\xbe\x00\x00\x00\x34" + b"\0" * 32     # a Java class file
        self.assertIsNone(make_app.macho_info(self.write("e", java)))
        self.assertIsNone(make_app.macho_info(self.write("f", b"")))

    def test_code_for_the_other_kind_of_mac_or_a_newer_macos_fails(self):
        app, _lic = fake_app(self.dir, {
            "MacOS/KanzonasPDF": macho("arm64"),
            "Frameworks/QtCore.framework/Versions/A/QtCore": fat(
                ("x86_64", macho("x86_64")), ("arm64", macho("arm64"))),
            "Frameworks/numpy/_core.so": macho("x86_64"),
            "Frameworks/cv2/cv2.abi3.so": macho("arm64", (15, 0, 0))})
        problems, n, newest = make_app.check_binaries(app, "arm64", "14.0")
        self.assertEqual(n, 4)
        self.assertEqual(newest, (15, 0, 0))
        text = "\n".join(problems)
        self.assertIn("numpy/_core.so: no arm64 code", text)
        self.assertIn("cv2.abi3.so: needs macOS 15.0.0", text)
        self.assertNotIn("QtCore", text)
        self.assertEqual(len(problems), 2)
        problems, _n, _newest = make_app.check_binaries(app, "x86_64", "15.0")
        self.assertEqual(len(problems), 2)          # (the arm64-only program and cv2)

    def test_qt_for_pythons_own_modules_name_their_sdk(self):
        # (PySide6 6.12.0's bindings say macOS 26, the SDK's; Qt's own libraries are checked)
        app, _lic = fake_app(self.dir, {
            "MacOS/KanzonasPDF": macho("arm64"),
            "Frameworks/PySide6/QtCore.abi3.so": macho("arm64", (26, 0, 0)),
            "Frameworks/shiboken6/libshiboken6.abi3.6.12.dylib": macho("arm64", (26, 0, 0)),
            "Frameworks/PySide6/Qt/lib/QtCore.framework/Versions/A/QtCore":
                macho("arm64", (26, 0, 0)),
            "Frameworks/other/PySide6/x.so": macho("arm64", (26, 0, 0))})
        problems, n, newest = make_app.check_binaries(app, "arm64", "14.4")
        self.assertEqual(n, 5)
        self.assertEqual(sorted(p.split(":")[0] for p in problems),
                         ["Contents/Frameworks/PySide6/Qt/lib/QtCore.framework/Versions/A/QtCore",
                          "Contents/Frameworks/other/PySide6/x.so"])
        # (and still: code for the other kind of Mac fails there too)
        app2, _lic = fake_app(os.path.join(self.dir, "b"), {
            "MacOS/KanzonasPDF": macho("arm64"),
            "Frameworks/PySide6/QtGui.abi3.so": macho("x86_64", (26, 0, 0))})
        problems, _n, _newest = make_app.check_binaries(app2, "arm64", "14.4")
        self.assertEqual(len(problems), 1)

    def test_finishing_an_app(self):
        app, lic = fake_app(self.dir, {
            "MacOS/KanzonasPDF": macho("x86_64"),
            "Frameworks/libpython3.12.dylib": macho("x86_64", (10, 13, 0))})
        make_app.finish(app, "1.9", "x86_64", "14.0", licenses=lic)
        with open(os.path.join(app, "Contents", "Info.plist"), "rb") as f:
            info = plistlib.load(f)
        self.assertEqual(info["CFBundleShortVersionString"], "1.9")
        self.assertFalse(info["LSBackgroundOnly"])
        res = os.path.join(app, "Contents", "Resources")
        self.assertTrue(os.path.isfile(os.path.join(res, "KanzonasPDF.icns")))
        self.assertFalse(os.path.exists(os.path.join(res, "generated-1a2b.icns")))
        for name in make_app.LICENSES:
            self.assertTrue(os.path.isfile(os.path.join(res, name)), name)

    def test_a_wrong_app_fails(self):
        app, lic = fake_app(self.dir, {"MacOS/KanzonasPDF": macho("arm64")})
        with self.assertRaises(SystemExit):
            make_app.finish(app, "1.9", "x86_64", "14.0", licenses=lic)
        app2, lic2 = fake_app(os.path.join(self.dir, "b"), {"MacOS/KanzonasPDF": macho("arm64")})
        with self.assertRaises(SystemExit):                     # (no license files)
            make_app.finish(app2, "1.9", "arm64", "14.0")
        with self.assertRaises(SystemExit):
            make_app.finish(self.dir, "1.9", "arm64", "14.0", licenses=lic)


class Pins(unittest.TestCase):
    def test_every_platform_gets_the_same_versions(self):
        # (no Intel Mac build: no pins held back for it, every platform gets the patched ones)
        with open(os.path.join(ROOT, "constraints.txt"), encoding="utf-8") as f:
            text = f.read()
        self.assertNotIn("platform_machine", text)
        self.assertNotIn("pymupdf-lite", text)
        self.assertEqual(len(re.findall(r"(?m)^onnxruntime==", text)), 1)
        self.assertFalse(os.path.exists(os.path.join(MAC, "pymupdf_standin.py")))


class Scripts(unittest.TestCase):
    @unittest.skipUnless(shutil.which("bash") and os.name != "nt", "needs bash (not Windows')")
    def test_smoke_test_script_is_valid_and_executable(self):
        path = os.path.join(MAC, "smoke_test.sh")
        subprocess.run(["bash", "-n", path], check=True)
        if os.name != "nt":
            self.assertTrue(os.access(path, os.X_OK))

    def test_entitlements(self):
        with open(os.path.join(MAC, "entitlements.plist"), "rb") as f:
            ent = plistlib.load(f)
        self.assertEqual(set(ent), {"com.apple.security.cs.allow-unsigned-executable-memory",
                                    "com.apple.security.cs.disable-library-validation"})


@unittest.skipIf(yaml is None, "PyYAML isn't installed")
class Workflow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(WORKFLOW, encoding="utf-8") as f:
            cls.text = f.read()
        cls.wf = yaml.safe_load(cls.text)
        cls.jobs = cls.wf["jobs"]
        cls.mac = cls.jobs["macos"]
        cls.script = "\n".join(s.get("run", "") for s in cls.mac["steps"])
        cls.steps = {s.get("name"): s for s in cls.mac["steps"]}

    def test_apple_silicon_only(self):
        from kanzonas import macos
        self.assertNotIn("strategy", self.mac)
        self.assertEqual(self.mac["runs-on"], "macos-15")       # (the oldest macOS GitHub has)
        self.assertEqual(self.mac["name"], "macos (arm64)")      # (the check's name)
        self.assertEqual(macos.DMG, "KanzonasPDF-macos-arm64.dmg")
        self.assertIn('test "$(uname -m)" = arm64', self.script)
        self.assertIn("test \"$(python -c 'import platform; print(platform.machine())')\" = arm64",
                      self.script)
        self.assertIn("--arch arm64", self.script)               # (every Mach-O file checked)
        for word in ("x86_64", "standin", "find-links"):
            self.assertNotIn(word, self.script)
        # nothing is left to carry on past a failure
        for step in self.mac["steps"]:
            self.assertNotIn("continue-on-error", step)

    def test_the_same_pyinstaller_options_and_pins(self):
        self.assertIn("python -m PyInstaller ${{ env.PYINSTALLER_OPTIONS }} run.py", self.script)
        self.assertIn("--only-binary :all: -r requirements.txt -c constraints.txt pyinstaller",
                      self.script)

    def test_tested_before_it_can_be_published(self):
        self.assertIn('python -m unittest discover -s tests -p "test_*.py" -t .', self.script)
        self.assertEqual(self.steps["Regression tests (security, document preservation, "
                                    "efficiency budgets)"]["env"], {"QT_QPA_PLATFORM": "offscreen"})
        selftest = self.steps["Self test (inside the app; OCR, exports, signatures, forms)"]["run"]
        self.assertIn("QT_QPA_PLATFORM=offscreen dist/KanzonasPDF.app/Contents/MacOS/KanzonasPDF "
                      "--selftest selftest-macos.log", selftest)
        self.assertIn("grep -q '^FAIL' selftest-macos.log", selftest)
        self.assertIn("grep -q '^PASS performance budget' selftest-macos.log", selftest)
        self.assertIn("packaging/macos/smoke_test.sh dist/KanzonasPDF.app smoke-macos.png", self.script)
        finish = self.steps["Finish the app (Info.plist, icon, licenses; architecture and "
                            "macOS version checks)"]["run"]
        for part in ("--arch arm64", '--min-macos "$MACOS_MIN"', "--adhoc-sign",
                     "--licenses licenses"):
            self.assertIn(part, finish)
        self.assertEqual(self.mac["env"]["MACOS_MIN"], "14.4")
        # the order: built, finished, tested, then packed
        order = [s.get("name") or s.get("uses") for s in self.mac["steps"]]
        idx = {n: i for i, n in enumerate(order)}
        self.assertLess(idx["Finish the app (Info.plist, icon, licenses; architecture and "
                            "macOS version checks)"],
                        idx["Self test (inside the app; OCR, exports, signatures, forms)"])
        self.assertLess(idx["Smoke test (opened from Finder, a second PDF into the running app)"],
                        idx["Disk image"])

    def test_signing_is_ready_but_off(self):
        self.assertEqual(self.mac["env"]["MACOS_SIGNING"], "off")
        gated = [s for s in self.mac["steps"] if "(signing" in (s.get("name") or "")]
        self.assertEqual(len(gated), 2)
        for s in gated:
            self.assertEqual(s["if"], "env.MACOS_SIGNING == 'on'")
        self.assertIn("--options runtime", gated[0]["run"])
        self.assertIn("packaging/macos/entitlements.plist", gated[0]["run"])
        self.assertIn("notarytool submit", gated[1]["run"])
        self.assertIn("stapler staple", gated[1]["run"])
        # (no secret reaches a step that runs while signing is off)
        for s in self.mac["steps"]:
            if s not in gated:
                self.assertNotIn("secrets.", str(s))

    def test_least_privilege(self):
        self.assertNotIn("permissions", self.mac)
        self.assertEqual(self.wf["permissions"], {"contents": "read"})
        for s in self.mac["steps"]:
            self.assertNotIn("action-gh-release", s.get("uses", ""))

    def test_the_release_carries_the_disk_image(self):
        pub = self.jobs["publish"]
        self.assertIn("macos", pub["needs"])
        steps = {s.get("name"): s for s in pub["steps"]}
        self.assertIn("${{ needs.macos.outputs.version }}",
                      steps["Same version on Windows, Linux and macOS"]["run"])
        dl = [s for s in pub["steps"] if "download-artifact" in s.get("uses", "")
              and "macos" in str(s.get("with"))]
        self.assertEqual(len(dl), 1)
        # the artifact the macos job uploads is the one publish downloads
        up = [s for s in self.mac["steps"] if "upload-artifact" in s.get("uses", "")
              and "dmg" in str(s.get("with"))][0]["with"]
        self.assertEqual(up["name"], "KanzonasPDF-v${{ steps.ver.outputs.version }}-macos-arm64")
        self.assertEqual(dl[0]["with"]["name"],
                         "KanzonasPDF-v${{ needs.macos.outputs.version }}-macos-arm64")
        self.assertEqual(up["path"], "KanzonasPDF-macos-arm64.dmg")
        sums = steps["Checksums (SHA-256) of the downloads"]["run"]
        rel = steps["Publish release"]["with"]
        name = "KanzonasPDF-macos-arm64.dmg"
        self.assertIn(name, sums)
        self.assertIn("release/" + name, rel["files"])
        self.assertIn(name, rel["body"])
        self.assertNotIn("x86_64.dmg", self.text)
        for word in ("Apple silicon (M1 or newer)", "14.4", "no version for Intel Macs",
                     "Open Anyway", "Privacy & Security", "shasum -a 256"):
            self.assertIn(word, rel["body"])


class Readme(unittest.TestCase):
    def test_install_and_open_anyway(self):
        with open(os.path.join(ROOT, "README.md"), encoding="utf-8") as f:
            text = f.read()
        self.assertIn("### macOS (disk image)", text)
        for word in ("KanzonasPDF-macos-arm64.dmg", "Apple silicon", "no version for Intel Macs",
                     "Open Anyway", "Privacy & Security", "shasum -a 256"):
            self.assertIn(word, text)
        self.assertNotIn("x86_64.dmg", text)
        self.assertNotIn("no macOS version", text)


if __name__ == "__main__":
    unittest.main()
