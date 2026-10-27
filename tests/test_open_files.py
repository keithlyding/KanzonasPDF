"""Files open in tabs stay true to what's on disk, and opening files remembers the right
things:
- writing a new PDF over a file open in a tab (Save As, Extract pages, Combine files) asks
  first when that tab has unsaved changes, and doesn't leave the tab showing the old file;
  Extract pages can't replace the document it extracts from;
- opening a file that's open already but changed on disk shows it as it is now;
- a document opened into a tab at the back reopens at its last page all the same;
- a recovered backup copy opens unsaved, named after its original file;
- the page and zoom remembered per file keep the 200 files used most recently;
- tab names are only set again when they change (slow with many tabs).

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_open_files
"""
import json
import os
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf as F  # noqa: E402
from PySide6.QtWidgets import (QApplication, QFileDialog, QInputDialog,  # noqa: E402
                               QMessageBox)

APP = QApplication.instance() or QApplication([])

from kanzonas import autosave, combine, main_window  # noqa: E402
from kanzonas.document_view import DocumentView  # noqa: E402
from kanzonas.main_window import MainWindow  # noqa: E402


def make_pdf(path, n, label):
    d = F.open()
    for i in range(n):
        d.new_page().insert_text((72, 72), f"{label}{i + 1}", fontsize=24)
    d.save(path)
    d.close()
    return path


def labels(doc_or_path):
    d = F.open(doc_or_path) if isinstance(doc_or_path, str) else doc_or_path
    out = [p.get_text().split()[0] for p in d]
    if isinstance(doc_or_path, str):
        d.close()
    return out


def mark(v):
    v._create(0, {"kind": "rect", "props": {"stroke": "#d00000", "width": 2},
                  "rect": F.Rect(40, 40, 80, 80)})


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(mock.patch.stopall)
        mock.patch.object(QMessageBox, "information", return_value=QMessageBox.Ok).start()
        self.asked = []
        self.answer = QMessageBox.No
        for name in ("warning", "question"):
            mock.patch.object(QMessageBox, name, side_effect=lambda *a, **k: (
                self.asked.append(a[2]), self.answer)[1]).start()
        self.w = MainWindow()
        self.w.resize(1200, 800)
        self.w.show()
        self.addCleanup(self.close_window)
        self.pump()

    def close_window(self):
        for v in self.w._views():
            v.dirty = False
        self.w._close_confirmed = True
        self.w.close()
        self.w.deleteLater()
        self.pump()

    def pump(self, n=20):
        for _ in range(n):
            APP.processEvents()

    def pdf(self, name, n=1, label=None):
        return make_pdf(os.path.join(self.tmp, name), n, label or name[0].upper())

    def save_name(self, path):
        mock.patch.object(QFileDialog, "getSaveFileName", return_value=(path, "")).start()


class WritingOverOpenFiles(Base):
    def combine(self, files):
        def run(dlg):
            dlg.list.clear()
            dlg.list.add_paths(files)
            dlg._ok()
            return 1 if dlg.result_path else 0
        with mock.patch.object(combine.CombineDialog, "exec", run):
            self.w.combine_files()
        self.pump()

    def test_combine_again_to_the_same_name_shows_the_new_file(self):
        a, b, c = self.pdf("A.pdf"), self.pdf("B.pdf"), self.pdf("C.pdf")
        out = os.path.join(self.tmp, "Combined.pdf")
        self.save_name(out)
        self.combine([a, b])
        self.combine([c, b])
        self.assertEqual(labels(out), ["C1", "B1"])
        self.assertEqual(labels(self.w.view().doc), ["C1", "B1"])
        self.assertEqual(sum(1 for v in self.w._views() if v.path == out), 1)

    def test_combine_over_a_tab_with_unsaved_changes_asks_first(self):
        a, b, c = self.pdf("A.pdf"), self.pdf("B.pdf"), self.pdf("C.pdf")
        out = os.path.join(self.tmp, "Combined.pdf")
        self.save_name(out)
        self.combine([a, b])
        v = self.w.view()
        mark(v)
        self.combine([c, b])                    # answered No
        self.assertEqual(len(self.asked), 1)
        self.assertEqual(labels(out), ["A1", "B1"])
        self.assertTrue(v.dirty)
        self.assertIn(v, self.w._views())
        self.answer = QMessageBox.Yes
        self.combine([c, b])
        self.assertEqual(labels(out), ["C1", "B1"])
        self.assertEqual(labels(self.w.view().doc), ["C1", "B1"])
        self.assertFalse(self.w.view().dirty)

    def test_save_as_over_a_file_open_in_another_tab_closes_that_tab(self):
        a, b = self.pdf("A.pdf"), self.pdf("B.pdf")
        self.w.open_file(a)
        va = self.w.view()
        self.w.open_file(b)
        vb = self.w.view()
        self.save_name(a)
        self.assertTrue(self.w.save_as())
        self.pump()
        self.assertEqual(self.asked, [])                # nothing unsaved there: no question
        self.assertNotIn(va, self.w._views())
        self.assertEqual([v.path for v in self.w._views()], [a])
        self.assertIs(self.w.view(), vb)
        self.assertEqual(labels(a), ["B1"])

    def test_save_as_over_unsaved_changes_in_another_tab_can_be_refused(self):
        a, b = self.pdf("A.pdf"), self.pdf("B.pdf")
        self.w.open_file(a)
        va = self.w.view()
        mark(va)
        self.w.open_file(b)
        vb = self.w.view()
        self.save_name(a)
        self.assertFalse(self.w.save_as())
        self.assertEqual(len(self.asked), 1)
        self.assertEqual(labels(a), ["A1"])
        self.assertEqual(vb.path, b)
        self.assertIn(va, self.w._views())

    def extract(self, rng, target):
        mock.patch.object(QInputDialog, "getText", return_value=(rng, True)).start()
        self.save_name(target)
        self.w.extract_pages()
        self.pump()

    def test_extract_pages_cant_replace_its_own_document(self):
        e = self.pdf("E.pdf", 5)
        self.w.open_file(e)
        v = self.w.view()
        self.extract("2-2", e)
        self.assertEqual(labels(e), ["E1", "E2", "E3", "E4", "E5"])
        self.assertEqual(len(self.asked), 1)            # says why
        self.assertEqual(v.page_count(), 5)

    def test_extract_pages_over_a_file_open_in_another_tab_reloads_it(self):
        e, c = self.pdf("E.pdf", 5), self.pdf("C.pdf")
        self.w.open_file(c)
        self.w.open_file(e)
        self.extract("2-3", c)
        self.assertEqual(labels(c), ["E2", "E3"])
        tabs = [v for v in self.w._views() if v.path == c]
        self.assertEqual(len(tabs), 1)
        self.assertEqual(labels(tabs[0].doc), ["E2", "E3"])
        self.assertEqual(self.w.tabs.indexOf(tabs[0]), 0)     # in its old place


class OpeningAFileThatChanged(Base):
    def test_open_again_after_it_changed_on_disk_shows_the_new_file(self):
        f, g = self.pdf("F.pdf"), self.pdf("G.pdf")
        self.w.open_file(f)
        self.w.open_file(g)
        time.sleep(0.02)
        make_pdf(f, 3, "N")
        self.w.open_file(f)
        self.pump()
        self.assertEqual(labels(self.w.view().doc), ["N1", "N2", "N3"])
        self.assertEqual(self.w.tabs.count(), 2)
        self.assertEqual(self.asked, [])

    def test_unchanged_file_just_switches_to_its_tab(self):
        f, g = self.pdf("F.pdf"), self.pdf("G.pdf")
        self.w.open_file(f)
        vf = self.w.view()
        self.w.open_file(g)
        self.w.open_file(f)
        self.assertIs(self.w.view(), vf)

    def test_unsaved_changes_are_asked_about_first(self):
        f = self.pdf("F.pdf")
        self.w.open_file(f)
        vf = self.w.view()
        mark(vf)
        time.sleep(0.02)
        make_pdf(f, 2, "N")
        self.w.open_file(f)                     # answered No
        self.assertEqual(len(self.asked), 1)
        self.assertIs(self.w.view(), vf)
        self.assertTrue(vf.dirty)
        self.answer = QMessageBox.Yes
        self.w.open_file(f)
        self.pump()
        self.assertEqual(labels(self.w.view().doc), ["N1", "N2"])
        self.assertFalse(self.w.view().dirty)

    def test_a_saved_file_is_not_seen_as_changed(self):
        f = self.pdf("F.pdf")
        self.w.open_file(f)
        v = self.w.view()
        mark(v)
        self.assertTrue(self.w.save())
        self.w.open_file(f)
        self.assertIs(self.w.view(), v)


class ReopenInBackgroundTab(Base):
    def test_last_page_in_a_tab_opened_at_the_back(self):
        a, b = self.pdf("a.pdf", 100), self.pdf("b.pdf", 2)
        for mode, zoom, page in (("width", 1.0, 79), ("last", 2.0, 6)):
            with self.subTest(mode=mode):
                for i in reversed(range(self.w.tabs.count())):
                    self.w.close_tab(i)
                self.pump()
                with mock.patch.object(DocumentView, "open_view", mode), \
                        mock.patch.object(DocumentView, "reopen_page", True):
                    self.w.settings.setValue("file_states", json.dumps(
                        {os.path.normcase(a): {"page": page, "zoom": zoom}}))
                    self.w.open_file(a)
                    self.w.open_file(b)     # a goes to the back before it's laid out
                    self.pump(40)
                    self.w.tabs.setCurrentIndex(0)
                    self.pump(40)
                    self.assertEqual(self.w.view().current_page(), page)


class RecoveredCopy(Base):
    def test_recovered_copy_opens_unsaved_and_named_after_its_original(self):
        orig = self.pdf("plan.pdf", 2)
        copy = make_pdf(os.path.join(self.tmp, "plan (unsaved changes)-x.pdf"), 2, "R")
        v = self.w._open_recovered(copy, orig)
        self.pump()
        self.assertTrue(v.dirty)
        self.assertTrue(v.untitled)
        self.assertEqual(v.path, orig)
        self.assertEqual(labels(v.doc), ["R1", "R2"])
        self.assertEqual(self.w.tabs.tabText(self.w.tabs.indexOf(v)), "*plan.pdf (recovered)")
        self.assertNotIn(copy, self.w.settings.value("recent") or [])
        # Save asks where, offering the original file
        offered = []
        mock.patch.object(QFileDialog, "getSaveFileName", side_effect=lambda *a, **k: (
            offered.append(a[2]), ("", ""))[1]).start()
        self.assertFalse(self.w.save())
        self.assertEqual(offered, [orig])
        self.assertEqual(labels(orig), ["P1", "P2"])

    def test_recover_backups_uses_the_original_paths(self):
        orig = self.pdf("plan.pdf", 2)
        folder = os.path.join(self.tmp, "backups")
        os.makedirs(folder)
        copy = make_pdf(os.path.join(folder, "plan (unsaved changes)-1.pdf"), 1, "R")
        untitled = make_pdf(os.path.join(folder, "Untitled 1 (unsaved changes)-2.pdf"), 1, "U")
        with open(os.path.join(folder, autosave.INDEX), "w") as f:
            json.dump({os.path.basename(copy): orig, os.path.basename(untitled): ""}, f)
        self.answer = QMessageBox.Yes
        with mock.patch.object(autosave, "folder", return_value=folder):
            self.w.recover_backups()
        self.pump()
        views = self.w._views()
        self.assertEqual(len(views), 2)
        self.assertTrue(all(v.dirty and v.untitled for v in views))
        self.assertIn(orig, [v.path for v in views])
        self.assertFalse(any(v.path.startswith(folder) for v in views))


class RememberedPages(Base):
    def test_the_200_most_recently_used_files_are_kept(self):
        daily = self.pdf("daily.pdf", 3)
        self.w.open_file(daily)
        self.w._remember_state(self.w.view())
        states = {os.path.normcase(daily): {"page": 0, "zoom": 1}}     # used long ago...
        states.update({os.path.normcase(os.path.join(self.tmp, f"f{i}.pdf")):
                       {"page": 0, "zoom": 1} for i in range(199)})
        self.w.settings.setValue("file_states", json.dumps(states))
        self.w._remember_state(self.w.view())                          # ...and again now
        other = self.pdf("other.pdf")
        self.w.open_file(other)
        self.w._remember_state(self.w.view())
        kept = json.loads(self.w.settings.value("file_states"))
        self.assertEqual(len(kept), 200)
        self.assertIn(os.path.normcase(daily), kept)
        self.assertNotIn(os.path.normcase(os.path.join(self.tmp, "f0.pdf")), kept)


class ManyTabs(Base):
    def test_unchanged_tab_names_are_not_set_again(self):
        for i in range(5):
            self.w.open_file(self.pdf(f"t{i}.pdf"))
        self.w._update_ui()
        tabs = self.w.tabs
        with mock.patch.object(tabs, "setTabText", wraps=tabs.setTabText) as text, \
                mock.patch.object(tabs, "setTabToolTip", wraps=tabs.setTabToolTip) as tip:
            self.w._update_ui()
            self.assertEqual(text.call_count + tip.call_count, 0)
            mark(self.w.view())                 # the current tab gets its *
            self.w._update_ui()
            self.assertEqual(text.call_count, 1)


if __name__ == "__main__":
    unittest.main()
