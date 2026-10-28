"""The user manual in Spanish (kanzonas/manual_es.py): Help > User manual shows it when the
interface is in Spanish, it has the same chapters as the English manual, and the check that
every menu command is in the manual also passes in Spanish.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_manual_spanish
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

from kanzonas import manual, manual_es  # noqa: E402


def ids(html):
    return re.findall(r'<h2 id="([^"]+)">', html)


class SameShape(unittest.TestCase):
    """Guards against a chapter, a table or a list being dropped from the translation."""

    def test_same_chapters_in_the_same_order(self):
        self.assertEqual(ids(manual_es.MANUAL), ids(manual.MANUAL))

    def test_same_tables_and_rows(self):
        for tag in ("<table", "<tr>", "<ul>"):
            self.assertEqual(manual_es.MANUAL.count(tag), manual.MANUAL.count(tag), tag)

    def test_list_items_and_paragraphs_within_two_percent(self):
        for tag in ("<li>", "<p>", "<b>"):
            en, es = manual.MANUAL.count(tag), manual_es.MANUAL.count(tag)
            self.assertLessEqual(abs(es - en), max(1, round(en * 0.02)), "%s: %d vs %d" % (tag, es, en))

    def test_links_and_anchors_kept(self):
        for pattern in (r'<a [^>]*>', r'id="[^"]+"', r'href="[^"]+"'):
            self.assertEqual(sorted(re.findall(pattern, manual_es.MANUAL)),
                             sorted(re.findall(pattern, manual.MANUAL)), pattern)

    def test_english_interface_shows_the_english_manual(self):
        from kanzonas import i18n
        self.assertEqual(i18n.language(), "en")         # tests/__init__.py runs in English
        self.assertIs(manual.manual_html(), manual.MANUAL)
        self.assertEqual(manual.sections()[0][0], ids(manual.MANUAL)[0])


# Builds the main window with the interface in Spanish (the language is fixed per process at
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
from kanzonas import i18n, manual, manual_es
from kanzonas.main_window import MainWindow
win = MainWindow()
dlg = manual.ManualDialog(win)
out = {"lang": i18n.language(), "missing": manual.missing_from_manual(win),
       "sections": [a for a, _ in manual.sections()],
       "spanish_html": manual.manual_html() is manual_es.MANUAL,
       "title": dlg.windowTitle(),
       "contents": [dlg.contents.item(i).text() for i in range(dlg.contents.count())],
       "found": dlg.find.setText("censura") or dlg.find_next()}
sys.stdout.write("RESULT " + json.dumps(out) + "\n")
sys.stdout.flush()
os._exit(0)
"""


class InSpanish(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        env = dict(os.environ, KANZONAS_LANG="es", QT_QPA_PLATFORM="offscreen", KZ_ROOT=ROOT,
                   KZ_SETTINGS=tempfile.mkdtemp(prefix="kanzonas-test-es-"))
        proc = subprocess.run([sys.executable, "-c", CHILD], env=env, cwd=ROOT,
                              capture_output=True, text=True, timeout=180)
        line = [ln for ln in proc.stdout.splitlines() if ln.startswith("RESULT ")]
        if not line:
            raise AssertionError("the Spanish run failed:\n" + proc.stdout + proc.stderr)
        cls.result = json.loads(line[-1][len("RESULT "):])

    def test_runs_in_spanish_and_shows_the_spanish_manual(self):
        self.assertEqual(self.result["lang"], "es")
        self.assertTrue(self.result["spanish_html"])
        self.assertEqual(self.result["title"], "Manual del usuario de KanzonasPDF")
        self.assertIn("Primeros pasos", self.result["contents"])
        self.assertTrue(self.result["found"])

    def test_every_menu_command_is_in_the_spanish_manual(self):
        self.assertEqual(self.result["missing"], [])

    def test_same_chapter_ids_as_the_english_manual(self):
        self.assertEqual(self.result["sections"], ids(manual.MANUAL))


if __name__ == "__main__":
    unittest.main()
