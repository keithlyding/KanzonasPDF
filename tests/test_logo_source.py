"""KanzonasPDF's logo is Kanzonas-Site's: the single source of truth for every Kanzonas logo.

The logo is made there (brand/make_logos.py) and brought in with tools/update_logo.py, which
records the site commit and the file's SHA-256 in assets/LOGO_SOURCE.txt. A logo edited here by
hand (or branding_data.py out of step with it) fails this test. No download: it checks the copy.

    python -m unittest tests.test_logo_source
"""
import importlib.util
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _tool():
    spec = importlib.util.spec_from_file_location(
        "update_logo", os.path.join(ROOT, "tools", "update_logo.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class LogoSource(unittest.TestCase):
    def test_the_logo_is_the_sites(self):
        tool = _tool()
        self.assertEqual(tool.check(), [])
        rec = tool.read_record()
        self.assertEqual(rec["repo"], "https://github.com/keithlyding/Kanzonas-Site")
        self.assertRegex(rec["commit"], r"^[0-9a-f]{40}$")
        self.assertEqual(rec["path"], "brand/out/kanzonas-logo-source.png")

    def test_a_logo_edited_here_is_caught(self):
        tool = _tool()
        data = open(tool.LOGO, "rb").read()
        real_open = open

        def fake_open(path, mode="r", *a, **k):
            if path == tool.LOGO and "b" in mode:
                import io
                return io.BytesIO(data[:-1] + bytes([data[-1] ^ 1]))
            return real_open(path, mode, *a, **k)
        tool.open = fake_open           # (the module's own open: nothing on disk changes)
        found = tool.check()
        self.assertTrue(any("Kanzonas-Site" in p for p in found), found)

    def test_updating_keeps_the_icons(self):
        tool = _tool()
        text = open(tool.BRANDING, encoding="utf-8").read()
        new = tool.branding_with_logo(text, b"\x89PNG\r\n\x1a\nnot really")
        cut = text.index("LOGO = ")
        self.assertEqual(new[:cut], text[:cut])
        self.assertEqual(tool.branding_with_logo(text, open(tool.LOGO, "rb").read()), text)


if __name__ == "__main__":
    unittest.main()
