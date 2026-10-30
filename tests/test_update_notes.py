"""What changed since your version: each release's text carries short notes from
RELEASE_NOTES.md (tools/release_notes.py, run by the Windows build), and the update box shows
the notes of every release newer than the running copy, newest first, in its language when
the notes have it. The automatic check also runs while KanzonasPDF stays open, and an automatic
check that finds nothing newer says so quietly in the status bar.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_update_notes
"""
import os
import sys
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QDialog, QTextBrowser  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import __version__, updates  # noqa: E402
from tools import release_notes  # noqa: E402

NOTES = """# Release notes

## 2.1

**New**
- Rockets.

## 2.1 (es)

**Novedades**
- Cohetes.

## 2.0

**Fixed**
- Wheels.
"""


def release(version, body="", draft=False):
    return {"tag_name": "v" + version, "draft": draft, "body": body,
            "html_url": "https://github.com/x/releases/tag/v" + version}


class Notes(unittest.TestCase):
    def test_every_version_has_notes_in_english_and_spanish(self):
        with open(os.path.join(ROOT, "RELEASE_NOTES.md"), encoding="utf-8") as f:
            found = release_notes.sections(f.read())
        self.assertTrue(found.get((__version__, "en")), "RELEASE_NOTES.md: ## " + __version__)
        self.assertTrue(found.get((__version__, "es")), "RELEASE_NOTES.md: ## %s (es)"
                        % __version__)

    def test_the_block_a_release_carries(self):
        block = release_notes.block(NOTES, "2.1")
        self.assertIn("<!-- kanzonas-notes -->\n**New**\n- Rockets.\n<!-- /kanzonas-notes -->",
                      block)
        self.assertIn("<!-- kanzonas-notes lang=es -->", block)
        self.assertIsNone(release_notes.block(NOTES, "3.0"))
        self.assertNotIn("Cohetes", release_notes.block(NOTES, "2.0"))

    def test_notes_since_your_version(self):
        rels = [release("2.0", release_notes.block(NOTES, "2.0")),
                release("2.1", release_notes.block(NOTES, "2.1")),
                release("2.2", draft=True),
                release("1.9", "old"),
                release("2.0.1")]                                # before notes existed
        got = updates.notes_since(rels, current="1.9")
        self.assertEqual([v for v, _n, _u in got], ["2.1", "2.0.1", "2.0"])
        self.assertIn("Rockets", got[0][1])
        self.assertIsNone(got[1][1])
        self.assertIn("Wheels", got[2][1])
        es = updates.notes_since(rels, current="1.9", lang="es")
        self.assertIn("Cohetes", es[0][1])
        self.assertIn("Wheels", es[2][1])                        # no Spanish: English
        self.assertEqual(updates.notes_since(rels, current="2.1"), [])


class UpdateBox(unittest.TestCase):
    def window(self):
        from kanzonas.main_window import MainWindow
        w = MainWindow()
        self.addCleanup(lambda: (setattr(w, "_close_confirmed", True), w.close()))
        return w

    def test_the_box_lists_what_changed_since_your_version(self):
        w = self.window()
        w._updater()
        w._upd.releases = [release("98.0", release_notes.block(NOTES, "2.0")),
                           release("99.0", release_notes.block(NOTES, "2.1"))]
        w._upd.release = w._upd.releases[1]
        shown = []

        def look(dlg):
            shown.append(dlg.findChild(QTextBrowser).toPlainText())
            return 0
        with mock.patch.object(QDialog, "exec", look):
            w._update_box("99.0", "https://github.com/x")
        self.assertIn("99.0", shown[0])
        self.assertIn("Rockets", shown[0])
        self.assertIn("Wheels", shown[0])
        self.assertLess(shown[0].index("99.0"), shown[0].index("98.0"))     # newest first

    def test_checked_while_open_and_said_quietly(self):
        w = self.window()
        with mock.patch.object(updates.UpdateChecker, "check_if_due") as due:
            w.start_update_check()
        self.assertTrue(due.called)
        self.assertEqual(w._update_timer.interval(), 3600 * 1000)
        self.assertTrue(w._update_timer.isActive())
        w._upd.checked.emit("You have the latest version (1.5).")
        self.assertIn("latest version", w.statusBar().currentMessage())


if __name__ == "__main__":
    unittest.main()
