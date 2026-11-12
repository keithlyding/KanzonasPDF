"""The user manual in Italian (kanzonas/manual_it.py): Help > User manual shows it when the
interface is in Italian, it has the same chapters as the English manual, and the check that
every menu command is in the manual also passes in Italian.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_manual_italian
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import manual, manual_it  # noqa: E402


def ids(html):
    return re.findall(r'<h2 id="([^"]+)">', html)


class SameShape(unittest.TestCase):
    """Guards against a chapter, a table or a list being dropped from the translation."""

    def test_same_chapters_in_the_same_order(self):
        self.assertEqual(ids(manual_it.MANUAL), ids(manual.MANUAL))

    def test_same_tables_and_rows(self):
        for tag in ("<table", "<tr>", "<ul>"):
            self.assertEqual(manual_it.MANUAL.count(tag), manual.MANUAL.count(tag), tag)

    def test_list_items_and_paragraphs_within_two_percent(self):
        for tag in ("<li>", "<p>", "<b>"):
            en, it = manual.MANUAL.count(tag), manual_it.MANUAL.count(tag)
            self.assertLessEqual(abs(it - en), max(1, round(en * 0.02)),
                                 "%s: %d vs %d" % (tag, it, en))

    def test_links_and_anchors_kept(self):
        for pattern in (r'<a [^>]*>', r'id="[^"]+"', r'href="[^"]+"'):
            self.assertEqual(sorted(re.findall(pattern, manual_it.MANUAL)),
                             sorted(re.findall(pattern, manual.MANUAL)), pattern)

    def test_no_untranslated_chapter_title(self):
        english = dict(re.findall(r'<h2 id="([^"]+)">(.*?)</h2>', manual.MANUAL))
        italian = dict(re.findall(r'<h2 id="([^"]+)">(.*?)</h2>', manual_it.MANUAL))
        same = [k for k in english if english[k] == italian.get(k) and
                english[k] not in ("macOS", "CAD", "OCR")]
        self.assertEqual(same, [])


# Builds the main window with the interface in Italian (the language is fixed per process at
# the first tr(), hence a separate process) and reports what the manual checks find. Settings
# go to a fresh folder so the developer's own are never read or written.
CHILD = r"""
import json, os, sys
sys.path.insert(0, os.environ["KZ_ROOT"])
from PySide6.QtCore import QSettings
for fmt in (QSettings.NativeFormat, QSettings.IniFormat):
    QSettings.setPath(fmt, QSettings.UserScope, os.environ["KZ_SETTINGS"])
from PySide6.QtWidgets import QApplication
app = QApplication([])
from kanzonas import i18n, manual, manual_it
from kanzonas.main_window import MainWindow
win = MainWindow()
dlg = manual.ManualDialog(win)
out = {"lang": i18n.language(), "missing": manual.missing_from_manual(win),
       "sections": [a for a, _ in manual.sections()],
       "italian_html": (manual.manual_html() is manual_it.MANUAL) if sys.platform != "darwin"
                       else manual.manual_html() == manual.for_mac(manual_it.MANUAL, "it"),
       "title": dlg.windowTitle(),
       "contents": [dlg.contents.item(i).text() for i in range(dlg.contents.count())],
       "found": dlg.find.setText("oscura") or dlg.find_next()}
sys.stdout.write("RESULT " + json.dumps(out) + "\n")
sys.stdout.flush()
os._exit(0)
"""


class InItalian(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        env = dict(os.environ, KANZONAS_LANG="it", QT_QPA_PLATFORM="offscreen", KZ_ROOT=ROOT,
                   KZ_SETTINGS=tempfile.mkdtemp(prefix="kanzonas-test-it-"))
        proc = subprocess.run([sys.executable, "-c", CHILD], env=env, cwd=ROOT,
                              capture_output=True, text=True, timeout=180)
        line = [ln for ln in proc.stdout.splitlines() if ln.startswith("RESULT ")]
        if not line:
            raise AssertionError("the Italian run failed:\n" + proc.stdout + proc.stderr)
        cls.result = json.loads(line[-1][len("RESULT "):])

    def test_runs_in_italian_and_shows_the_italian_manual(self):
        self.assertEqual(self.result["lang"], "it")
        self.assertTrue(self.result["italian_html"])
        self.assertEqual(self.result["title"], "Manuale utente di KanzonasPDF")
        self.assertIn("Primi passi", self.result["contents"])
        self.assertTrue(self.result["found"])

    def test_every_menu_command_is_in_the_italian_manual(self):
        self.assertEqual(self.result["missing"], [])

    def test_same_chapter_ids_as_the_english_manual(self):
        self.assertEqual(self.result["sections"], ids(manual.MANUAL))


if __name__ == "__main__":
    unittest.main()
