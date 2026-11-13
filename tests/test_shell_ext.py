"""Explorer's thumbnails and Preview pane for PDFs (shell_ext/, KanzonasPDFShell.dll; the owner,
13 Nov 2026: "when I look in a folder, it doesn't just show a bunch of KanzonasPDF icons").
The DLL is built and tested on the Windows build machine (shell_ext/build.ps1,
shell_ext/kzshell_test.cpp); these check, on any system, that its class IDs are the ones the
installer registers and the workflow checks, that Windows' handler keys are the documented
ones, that it draws with PyMuPDF's own MuPDF (so a security update of PyMuPDF updates it), and
the PDFs its test uses.

    python -m unittest tests.test_shell_ext
"""
import os
import re
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def read(*path):
    with open(os.path.join(ROOT, *path), encoding="utf-8") as f:
        return f.read()


def clsids_in_header():
    """{name: "{XXXXXXXX-...}"} from shell_ext/kzshell.h's comments and initializers, which must
    agree with each other."""
    h = read("shell_ext", "kzshell.h")
    out = {}
    for comment, name, body in re.findall(
            r"// \{([0-9A-F-]{36})\}[^\n]*\nstatic const CLSID (\w+) =\s*\{([^;]*)\};", h):
        nums = [int(x, 16) for x in re.findall(r"0x([0-9a-fA-F]+)", body)]
        guid = "%08X-%04X-%04X-%02X%02X-%s" % (nums[0], nums[1], nums[2], nums[3], nums[4],
                                                "".join("%02X" % n for n in nums[5:]))
        assert guid == comment, (name, guid, comment)
        out[name] = "{%s}" % guid
    return out


THUMBNAIL_KEY = "{e357fccd-a995-4576-b01f-234630154e96}"    # IThumbnailProvider's handler key
PREVIEW_KEY = "{8895b1c6-b41f-4c1c-a562-0d564250836f}"      # IPreviewHandler's handler key
PREVHOST_64 = "{6d2b5079-2f0b-48dd-ab7f-97cec514d30b}"      # Windows' 64-bit preview host


class ShellExtension(unittest.TestCase):
    def test_the_header_has_both_handlers(self):
        ids = clsids_in_header()
        self.assertEqual(set(ids), {"CLSID_KzThumbnail", "CLSID_KzPreview"})
        self.assertNotEqual(ids["CLSID_KzThumbnail"], ids["CLSID_KzPreview"])

    def test_the_installer_registers_the_same_ones(self):
        ids = clsids_in_header()
        iss = read("installer", "KanzonasPDF.iss")
        # (Inno writes a "{" as "{{")
        self.assertIn('#define ThumbCLSID "{%s"' % ids["CLSID_KzThumbnail"], iss)
        self.assertIn('#define PrevCLSID "{%s"' % ids["CLSID_KzPreview"], iss)
        self.assertIn("KanzonasPDF.Document\\ShellEx\\{%s\"; ValueType: string; ValueData: "
                      "\"{#ThumbCLSID}\"" % THUMBNAIL_KEY, iss)
        self.assertIn("KanzonasPDF.Document\\ShellEx\\{%s\"; ValueType: string; ValueData: "
                      "\"{#PrevCLSID}\"" % PREVIEW_KEY, iss)
        self.assertIn('ValueName: "AppID"; ValueData: "{%s"' % PREVHOST_64, iss)
        self.assertEqual(iss.count('ValueData: "{app}\\KanzonasPDFShell.dll"'), 2)
        self.assertEqual(iss.count('ValueName: "ThreadingModel"; ValueData: "Apartment"'), 2)
        # (the program's own icon stays for files it can't draw)
        self.assertIn("KanzonasPDF.Document\\DefaultIcon", iss)
        # registered and removed with the PDF entry, never outside it
        for line in iss.splitlines():
            if "KzShell" in line or "CLSID}" in line or "PreviewHandlers" in line:
                if line.startswith("Root:"):
                    self.assertIn("Tasks: pdfdefault", line, line)

    def test_the_workflow_checks_the_same_ones(self):
        ids = clsids_in_header()
        wf = read(".github", "workflows", "build-windows.yml")
        self.assertIn('$thumb = "%s"' % ids["CLSID_KzThumbnail"], wf)
        self.assertIn('$prev = "%s"' % ids["CLSID_KzPreview"], wf)
        self.assertIn("shell_ext\\build.ps1", wf)
        self.assertIn("kzshell_test.exe dist\\KanzonasPDF\\KanzonasPDFShell.dll", wf)
        self.assertIn('kzshell_test.exe "$dir\\KanzonasPDFShell.dll"', wf)
        # built before the zip and the installer take the program's folder
        self.assertLess(wf.index("shell_ext\\build.ps1"), wf.index("Compress-Archive"))
        self.assertLess(wf.index("shell_ext\\build.ps1"), wf.index("installer\\KanzonasPDF.iss"))

    def test_it_draws_with_pymupdfs_own_mupdf(self):
        ps = read("shell_ext", "build.ps1")
        self.assertIn("mupdf-devel", ps)
        self.assertIn("/DELAYLOAD:mupdfcpp64.dll", ps)
        cpp = read("shell_ext", "kzshell.cpp")
        self.assertIn('L"pymupdf\\\\mupdfcpp64.dll"', cpp)
        self.assertIn("_internal", cpp)
        self.assertNotIn("fz_try", cpp)     # (MuPDF's C++ functions throw; no C error jumps)
        # every handler class the factory makes
        self.assertIn("Factory<Thumbnail>", cpp)
        self.assertIn("Factory<Preview>", cpp)
        defs = read("shell_ext", "kzshell.def")
        self.assertIn("DllGetClassObject", defs)
        self.assertIn("DllCanUnloadNow", defs)

    def test_the_pdfs_its_test_uses(self):
        import pymupdf
        from tests import make_shell_ext_pdfs
        d = tempfile.mkdtemp()
        make_shell_ext_pdfs.main(d)
        page = pymupdf.open(os.path.join(d, "page.pdf"))
        self.assertEqual(page.page_count, 1)
        self.assertLess(page[0].rect.width, page[0].rect.height)
        wide = pymupdf.open(os.path.join(d, "wide.pdf"))
        self.assertGreater(wide[0].rect.width, wide[0].rect.height)
        self.assertEqual(pymupdf.open(os.path.join(d, "two.pdf")).page_count, 2)
        locked = pymupdf.open(os.path.join(d, "locked.pdf"))
        self.assertTrue(locked.needs_pass)
        self.assertFalse(locked.authenticate(""))       # (no empty user password)
        with self.assertRaises(Exception):
            pymupdf.open(os.path.join(d, "garbage.pdf"), filetype="pdf")
        # the box covers a part of the page, as the test's dark-pixel counts expect
        pix = page[0].get_pixmap(dpi=24)
        s = pix.samples
        dark = sum(1 for i in range(0, len(s), pix.n) if s[i] < 80)
        self.assertGreater(dark, pix.width * pix.height / 20)
        self.assertLess(dark, pix.width * pix.height / 2)


if __name__ == "__main__":
    unittest.main()
