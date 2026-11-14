"""What changed since your version: each release's text carries short notes from
RELEASE_NOTES.md (tools/release_notes.py, run by the Windows build), and the update box shows
the notes of every release newer than the running copy, newest first, in its language when
the notes have it. The automatic check also runs while KanzonasPDF stays open, and an automatic
check that finds nothing newer says so quietly in the status bar.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_update_notes
"""
import os
import re
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


class SkippedVersions(unittest.TestCase):
    """A version never published (1.13.1 on 12 Nov 2026: its Mac build found no machine, and
    1.13.2 was merged before it) has its notes carried in the next release (owner, 12 Nov:
    carry them automatically)."""
    TEXT = NOTES.replace("## 2.0\n", "## 2.0.2\n\n**Fixed**\n- Brakes.\n\n## 2.0.2 (es)\n\n"
                         "**Correcciones**\n- Frenos.\n\n## 2.0.1\n\n**Fixed**\n- Horn.\n\n"
                         "## 2.0\n")

    def test_which_versions_were_skipped(self):
        self.assertEqual(release_notes.skipped(self.TEXT, "2.1", ["v2.0", "v1.9"]),
                         ["2.0.1", "2.0.2"])
        self.assertEqual(release_notes.skipped(self.TEXT, "2.1", ["v2.0.2", "v2.0"]), [])
        self.assertEqual(release_notes.skipped(self.TEXT, "2.0.2", ["v2.0"]), ["2.0.1"])
        # nothing known published (gh failed): nothing taken as skipped
        self.assertEqual(release_notes.skipped(self.TEXT, "2.1", []), [])
        self.assertEqual(release_notes.skipped(self.TEXT, "2.1", ["", "junk"]), [])

    def test_the_release_carries_them_and_old_copies_ignore_them(self):
        body = release_notes.with_skipped(self.TEXT, "2.1", ["v2.0"])
        self.assertIn("Also in this release: 2.0.1", body)
        self.assertIn("<!-- kanzonas-notes v=2.0.2 -->", body)
        self.assertIn("<!-- kanzonas-notes lang=es v=2.0.2 -->", body)
        self.assertTrue(body.startswith(release_notes.block(self.TEXT, "2.1")))
        # its own notes are the first block of each language, as copies before 1.15 read them
        old = re.compile(r"(?: lang=(\w+))? -->")
        own = {}
        at = body.find("<!-- kanzonas-notes")
        while at >= 0:
            m = old.match(body, at + len("<!-- kanzonas-notes"))
            if m:
                own.setdefault(m.group(1) or "en", body[m.end():body.find("<!--", m.end())])
            at = body.find("<!-- kanzonas-notes", at + 1)
        self.assertIn("Rockets", own["en"])
        self.assertIn("Cohetes", own["es"])
        self.assertNotIn("Brakes", "".join(own.values()))
        self.assertEqual(updates.release_notes({"body": body}), updates.release_notes(
            {"body": release_notes.block(self.TEXT, "2.1")}))

    def test_the_update_box_lists_each_skipped_version(self):
        body = release_notes.with_skipped(self.TEXT, "2.1", ["v2.0"])
        rels = [release("2.0", release_notes.block(self.TEXT, "2.0")), release("2.1", body)]
        got = updates.notes_since(rels, current="1.9")
        self.assertEqual([v for v, _n, _u in got], ["2.1", "2.0.2", "2.0.1", "2.0"])
        self.assertIn("Rockets", got[0][1])
        self.assertIn("Brakes", got[1][1])
        self.assertNotIn("Rockets", got[1][1])
        self.assertIn("Horn", got[2][1])
        self.assertEqual(got[1][2], rels[1]["html_url"])     # (its page: the release with it)
        es = updates.notes_since(rels, current="1.9", lang="es")
        self.assertIn("Frenos", es[1][1])
        self.assertIn("Horn", es[2][1])                      # (no Spanish: English)
        # someone on 2.0.1 sees 2.0.2 and 2.1, not 2.0.1 again
        self.assertEqual([v for v, _n, _u in updates.notes_since(rels, current="2.0.1")],
                         ["2.1", "2.0.2"])
        # a carried version that was published after all is listed once, with its own notes
        rels.append(release("2.0.2", "<!-- kanzonas-notes -->\nOwn brakes\n<!-- /kanzonas-notes -->"))
        got = updates.notes_since(rels, current="1.9")
        self.assertEqual([v for v, _n, _u in got].count("2.0.2"), 1)
        self.assertIn("Own brakes", [n for v, n, _u in got if v == "2.0.2"][0])

    def test_the_tool_reads_the_published_list(self):
        import tempfile
        d = tempfile.mkdtemp()
        lst = os.path.join(d, "published.txt")
        with open(lst, "w") as f:
            f.write("v1.13\nv1.12.2\n")
        out = os.path.join(d, "out")
        with mock.patch.dict(os.environ, {"GITHUB_OUTPUT": out}):
            self.assertEqual(release_notes.main(["x", "1.13.2", "--published", lst,
                                                 "--github-output"]), 0)
        got = open(out, encoding="utf-8").read()
        self.assertIn("<!-- kanzonas-notes v=1.13.1 -->", got)    # (the real skipped one)
        with mock.patch.dict(os.environ, {"GITHUB_OUTPUT": out + "2"}):
            release_notes.main(["x", "1.13.2", "--published", os.path.join(d, "none"),
                                "--github-output"])
        self.assertNotIn("v=1.13.1", open(out + "2", encoding="utf-8").read())


class OddAnswers(unittest.TestCase):
    """A release's text and GitHub's answer are anyone's: odd ones must not hang or fail."""

    def test_long_runs_of_spaces_are_quick(self):
        import time
        body = "<!-- kanzonas-notes -->" + " " * 300000 + "x" + " " * 300000
        t = time.monotonic()
        self.assertEqual(updates.release_notes({"body": body}), "x")
        self.assertLess(time.monotonic() - t, 0.5)
        two = "<!-- kanzonas-notes -->A<!-- kanzonas-notes lang=es -->B"
        self.assertEqual(updates.release_notes({"body": two}, "es"), "B")
        self.assertEqual(updates.release_notes({"body": two}), "A")

    def test_assets_that_are_not_entries(self):
        self.assertIsNone(updates.asset_url({"assets": [1, "x", None, []]}))
        self.assertIsNone(updates.asset_digest({"assets": [1, "x", None, []]}))

    def test_a_last_check_in_the_future_is_due(self):
        import time
        settings = mock.Mock()
        for last in (time.time() + 7 * 86400, float("nan"), float("inf")):
            settings.value.side_effect = lambda k, d=None, last=last: \
                "true" if k == "update_check" else last
            checker = updates.UpdateChecker(settings)
            with mock.patch.object(updates.UpdateChecker, "check") as check, \
                    mock.patch.object(updates.UpdateChecker, "enabled", return_value=True):
                checker.check_if_due()
            self.assertTrue(check.called, last)

    def test_one_download_at_a_time_and_none_left_when_abandoned(self):
        import tempfile
        from PySide6.QtCore import QObject
        app_dir = tempfile.mkdtemp()
        holder = QObject()
        dl = updates.PortableUpdater("https://127.0.0.1:9/z.zip", app_dir, holder,
                                     expected_sha256="c" * 64)
        with mock.patch.object(dl.net, "get", return_value=mock.MagicMock()):
            dl.start()
        self.assertTrue(updates.downloading())
        self.assertTrue(os.listdir(app_dir))
        holder.deleteLater()
        QApplication.sendPostedEvents(None, 0)
        from PySide6.QtCore import QEvent
        QApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.assertFalse(updates.downloading())
        self.assertEqual(os.listdir(app_dir), [])


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
