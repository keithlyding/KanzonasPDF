"""What the 1.10 break-it battery found in Batch processing and reading comfort, fixed:

Batch processing (kanzonas/batch.py):
- a link in the output folder (to a file elsewhere, an original of the batch, or a folder
  elsewhere; also a link planted with the name of the temporary copy) was written through:
  a batch wrote outside its output folder and changed an original;
- Combine with a file left out (its output already there and skipped, or a full disk):
  that file's pages were still in the combined PDF, with Bates numbers the next file was
  given again;
- Search & redact only marking, then Combine: the combined PDF, still holding every word
  marked, was named Combined, not Combined-marked;
- Export before Search & redact (or Apply redactions): the exported copy held the words
  the report said were redacted;
- Remove hidden information ticked, but nothing to apply (the words not found, no marks):
  the file was copied as it was, its attachments (with the very words in them), metadata
  and scripts kept; without it, nothing said attachments aren't searched;
- the output folder inside the folder added: a second run processed the first run's
  results (into output/output/...), and a "Procesados" folder made in Spanish wasn't left
  out in English;
- name patterns: CON, NUL, LPT1 (Windows' devices: the result written nowhere), a name too
  long for the file system (a puzzling failure), characters that turn the text's direction;
- a hostile remembered setup or recipe (a number 1e999, a step kind that is a list,
  lists nested thousands deep) stopped the window from opening at all;
- a picture named .pdf failed with PyMuPDF's internal error message;
- a failure while writing a file's results (a full disk) could leave some of them;
- a file changed on disk while it was processed was copied as it is now ("nothing needed
  changing"), not as it was read and checked.

Reading comfort:
- Presentation kept the document object it started with: after Apply redactions (or
  Reload) in the window, the audience still saw the words redacted;
- Read aloud went on saying the sentences read before an edit (words just redacted or
  deleted), and closing the tab while it read raised "document closed" when the voice
  called back;
- in Full screen, Escape in the Reading view did nothing (only on the page);
- F5 again in the window opened a second presentation over the first, left behind when
  the window closed.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_battery_110_batch_reading
"""
import errno
import hashlib
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402
from PySide6.QtCore import QSettings, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import batch as B  # noqa: E402

WORD = "TOPSECRET"


def _digest(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _pdf(path, pages=1, text="Plain %s word" % WORD):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    doc = pymupdf.open()
    for k in range(pages):
        doc.new_page().insert_text((72, 72), "%s %d" % (text, k + 1), fontsize=12)
    doc.save(path)
    doc.close()
    return path


def _files(folder):
    return sorted(os.path.relpath(os.path.join(d, n), folder)
                  for d, _s, names in os.walk(folder) for n in names)


class _Dir(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="kz-b110-")
        self.addCleanup(shutil.rmtree, self.dir, True)

    def p(self, *parts):
        return os.path.join(self.dir, *parts)

    def run_batch(self, files, steps, **output):
        b = B.Batch(files, steps, dict({"mode": "folder", "folder": self.p("out")}, **output))
        b.run_all()
        return b


@unittest.skipUnless(hasattr(os, "symlink") and sys.platform != "win32",
                     "links need privileges on Windows")
class LinksInTheOutputFolder(_Dir):
    def test_a_link_to_a_file_elsewhere_or_an_original_is_replaced_not_written_through(self):
        a = _pdf(self.p("in", "a.pdf"))
        b = _pdf(self.p("in", "b.pdf"))
        victim = _pdf(self.p("elsewhere", "victim.pdf"), text="victim")
        os.makedirs(self.p("out"))
        os.symlink(victim, self.p("out", "a.pdf"))
        os.symlink(b, self.p("out", "b.pdf"))          # (to an original of this batch)
        before = {x: _digest(x) for x in (a, b, victim)}
        res = self.run_batch([a, b], [B.step("rotate")], overwrite="replace")
        self.assertEqual([r.status for r in res.results], [B.DONE, B.DONE])
        self.assertEqual({x: _digest(x) for x in before}, before)
        for name in ("a.pdf", "b.pdf"):
            self.assertFalse(os.path.islink(self.p("out", name)))
            with pymupdf.open(self.p("out", name)) as doc:
                self.assertEqual(doc[0].rotation, 90)

    def test_a_folder_link_inside_the_output_folder_is_never_written_into(self):
        s = _pdf(self.p("in", "sub", "s.pdf"))
        os.makedirs(self.p("elsewhere"))
        os.makedirs(self.p("out"))
        os.symlink(self.p("elsewhere"), self.p("out", "sub"))
        res = self.run_batch([B.Item(s, self.p("in"))], [B.step("rotate")])
        self.assertEqual(res.results[0].status, B.SKIPPED)
        self.assertIn("link", res.results[0].reason)
        self.assertEqual(os.listdir(self.p("elsewhere")), [])

    def test_a_processed_folder_that_is_a_link_is_never_written_into(self):
        a = _pdf(self.p("in", "a.pdf"))
        os.makedirs(self.p("elsewhere"))
        os.symlink(self.p("elsewhere"), self.p("in", "Processed"))
        b = B.Batch([a], [B.step("rotate")], {"mode": "next"})
        b.run_all()
        self.assertEqual(b.results[0].status, B.SKIPPED)
        self.assertEqual(os.listdir(self.p("elsewhere")), [])

    def test_a_link_with_the_temporary_copys_name_is_not_followed(self):
        a = _pdf(self.p("in", "a.pdf"))
        victim = _pdf(self.p("elsewhere", "victim.pdf"), text="victim")
        os.makedirs(self.p("out"))
        h = _digest(victim)
        # (the name the copy used to have, and any name like it: never written through)
        os.symlink(victim, self.p("out", "a.txt.kanzonas-tmp"))
        os.symlink(victim, self.p("out", "a.pdf.kanzonas-tmp"))
        with mock.patch("secrets.token_hex", side_effect=["same", "same", "other", "x", "y"]):
            os.symlink(victim, self.p("out", ".a.pdf.same.kanzonas-tmp"))
            res = self.run_batch([a], [B.step("rotate"), B.step("export", format="txt")])
        self.assertEqual(res.results[0].status, B.DONE, res.results[0].details())
        self.assertEqual(_digest(victim), h)


class Combine(_Dir):
    def test_a_file_left_out_is_not_in_the_combined_pdf_nor_its_bates_numbers(self):
        a = _pdf(self.p("in", "a.pdf"), 2)
        c = _pdf(self.p("in", "c.pdf"), 3)
        _pdf(self.p("out", "a.pdf"))                    # (a's output is already there)
        res = self.run_batch([a, c], [B.step("bates", prefix="X"),
                                      B.step("combine", keep_each=True)], overwrite="skip")
        self.assertEqual([r.status for r in res.results], [B.SKIPPED, B.DONE, B.DONE])
        with pymupdf.open(self.p("out", "Combined.pdf")) as doc:
            numbers = [p.get_text().split()[-1] for p in doc]
        self.assertEqual(numbers, ["X000001", "X000002", "X000003"])    # (c's alone, once)

    def test_a_file_that_failed_while_written_is_not_in_the_combined_pdf(self):
        a = _pdf(self.p("in", "a.pdf"), 2)
        c = _pdf(self.p("in", "c.pdf"), 3)
        real = B.shutil.copyfileobj
        calls = []

        def full(src, dst, *args):
            calls.append(1)
            if len(calls) == 1:             # (a's PDF: the disk is full)
                dst.write(b"%PDF-1.7 half")
                raise OSError(errno.ENOSPC, "No space left on device")
            return real(src, dst, *args)
        with mock.patch.object(B.shutil, "copyfileobj", full):
            res = self.run_batch([a, c], [B.step("bates", prefix="X"),
                                          B.step("combine", keep_each=True)])
        self.assertEqual([r.status for r in res.results], [B.FAILED, B.DONE, B.DONE])
        with pymupdf.open(self.p("out", "Combined.pdf")) as doc:
            self.assertEqual(doc.page_count, 3)
        self.assertEqual(_files(self.p("out")), ["Combined.pdf", "c.pdf"])

    def test_only_marked_files_combined_are_named_marked(self):
        a = _pdf(self.p("in", "a.pdf"))
        res = self.run_batch([a], [B.step("search_redact", words=WORD, apply=False),
                                   B.step("combine")])
        self.assertEqual(res.results[-1].status, B.DONE)
        self.assertEqual(_files(self.p("out")), ["Combined-marked.pdf"])


class Redaction(_Dir):
    def test_export_before_a_redaction_is_refused(self):
        for redact in (B.step("search_redact", words=WORD), B.step("apply_redactions"),
                       B.step("flatten_comments", redactions="apply")):
            steps = [B.step("export", format="txt"), redact]
            self.assertTrue(any("Export" in p for p in B.check_steps(steps)), redact)
            self.assertEqual(B.check_steps([redact, B.step("export", format="txt")]), [])
        # only marking removes nothing: an export before it is no surprise
        self.assertEqual(B.check_steps([B.step("export", format="txt"),
                                        B.step("search_redact", words=WORD, apply=False)]), [])

    def _attached(self, deflate):
        path = self.p("in", "att%d.pdf" % deflate)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        doc = pymupdf.open()
        doc.new_page().insert_text((72, 72), "Nothing to see", fontsize=12)
        doc.embfile_add("notes.txt", ("the %s plan" % WORD).encode())
        doc.set_metadata({"author": "Jane"})
        doc.save(path, deflate=deflate)
        doc.close()
        return path

    def test_hidden_information_is_removed_with_nothing_to_apply(self):
        for steps in ([B.step("search_redact", words=WORD)], [B.step("apply_redactions")]):
            path = self._attached(True)
            out = tempfile.mkdtemp(dir=self.dir)
            b = B.Batch([path], steps, {"mode": "folder", "folder": out})
            b.run_all()
            r = b.results[0]
            self.assertEqual(r.status, B.DONE, r.details())
            self.assertIn("hidden information removed", r.details())
            with pymupdf.open(r.outputs[0]) as doc:
                self.assertEqual(doc.embfile_count(), 0)
                self.assertEqual(doc.metadata.get("author"), "")

    def test_attachments_kept_without_the_clean_up_are_said(self):
        path = self._attached(True)
        res = self.run_batch([path], [B.step("search_redact", words=WORD, scrub=False)])
        self.assertIn("attached file", res.results[0].details())


class OutputFolder(_Dir):
    def test_a_second_run_leaves_out_the_first_runs_results(self):
        a = _pdf(self.p("in", "a.pdf"))
        out = self.p("in", "done")
        for _run in range(2):
            b = B.Batch(B.files_in(self.p("in")), [B.step("rotate")],
                        {"mode": "folder", "folder": out})
            b.run_all()
        self.assertEqual([r.status for r in b.results], [B.DONE, B.SKIPPED])
        self.assertIn("output folder", b.results[1].reason)
        self.assertEqual(_files(out), ["a (2).pdf", "a.pdf"])     # (never done/done/a.pdf)
        self.assertEqual(_digest(a), _digest(a))
        # a file added from the output folder itself is processed: it was chosen
        b = B.Batch(B.files_in(out), [B.step("rotate")], {"mode": "folder", "folder": out,
                                                          "pattern": "{name}-x"})
        b.run_all()
        self.assertEqual([r.status for r in b.results], [B.DONE, B.DONE])

    def test_processed_folders_of_every_language_are_left_out(self):
        _pdf(self.p("in", "a.pdf"))
        _pdf(self.p("in", "Procesados", "a.pdf"))
        _pdf(self.p("in", "Processed", "a.pdf"))
        self.assertEqual([os.path.relpath(i.path, self.dir) for i in B.files_in(self.p("in"))],
                         [os.path.join("in", "a.pdf")])


class Names(_Dir):
    def test_windows_device_names_hidden_characters_and_long_names(self):
        a = _pdf(self.p("in", "a.pdf"))
        for pattern, want in (("CON", "_CON.pdf"), ("nul", "_nul.pdf"), ("LPT1", "_LPT1.pdf"),
                              ("con.txt", "_con.txt.pdf"), ("AUX ", "_AUX.pdf"),
                              ("{name}\u202egpj", "agpj.pdf"), ("..", "a.pdf"),
                              ("../../{name}", "_.._a.pdf"), ("C:\\{name}", "C__a.pdf")):
            out = tempfile.mkdtemp(dir=self.dir)
            b = B.Batch([a], [B.step("rotate")], {"mode": "folder", "folder": out,
                                                  "pattern": pattern})
            b.run_all()
            self.assertEqual(b.results[0].status, B.DONE, (pattern, b.results[0].details()))
            self.assertEqual(os.listdir(out), [want], pattern)
        out = tempfile.mkdtemp(dir=self.dir)
        b = B.Batch([a], [B.step("rotate")], {"mode": "folder", "folder": out,
                                              "pattern": "{name}" + "é" * 300})
        b.run_all()
        self.assertEqual(b.results[0].status, B.DONE, b.results[0].details())
        (name,) = os.listdir(out)
        self.assertLessEqual(len(name.encode("utf-8")), 255)
        self.assertEqual(B._safe_name("Combined\u202e"), "Combined")


class HostileSettings(unittest.TestCase):
    def settings(self):
        path = os.path.join(tempfile.mkdtemp(), "s.ini")
        self.addCleanup(lambda: shutil.rmtree(os.path.dirname(path), True))
        return QSettings(path, QSettings.IniFormat)

    BAD = [{"kind": "bates", "options": {"start": 1e999, "size": float("nan"),
                                         "digits": "1e999"}},
           {"kind": ["bates"], "options": {}}, {"kind": {"a": 1}}, {"kind": None},
           {"kind": "watermark", "options": {"opacity": -1e999, "angle": [1]}}]

    def test_wrong_numbers_and_kinds(self):
        steps = B.normalized(json.loads(json.dumps(self.BAD)))
        self.assertEqual([st["kind"] for st in steps], ["bates", "watermark"])
        self.assertEqual(steps[0]["options"]["start"], 1)
        self.assertEqual(steps[0]["options"]["size"], 10.0)
        self.assertEqual(steps[1]["options"]["opacity"], 25)   # (its default)

    def test_recipes_and_the_window(self):
        s = self.settings()
        s.setValue(B.RECIPES_KEY, json.dumps({"mine": self.BAD}))
        self.assertEqual([st["kind"] for st in B.recipes(s)["mine"]], ["bates", "watermark"])
        s.setValue(B.RECIPES_KEY, "[" * 100000 + "]" * 100000)
        self.assertEqual(B.user_recipes(s), set())
        from kanzonas import batch_ui
        s.setValue("batch/steps", json.dumps(self.BAD))
        s.setValue("batch/output", "[" * 100000 + "]" * 100000)
        from PySide6.QtWidgets import QWidget
        win = QWidget()
        self.addCleanup(win.deleteLater)
        win.settings = s
        w = batch_ui.BatchWindow(win)
        self.addCleanup(w.deleteLater)
        self.assertEqual([st["kind"] for st in w.steps], ["bates", "watermark"])


class Inputs(_Dir):
    def test_a_picture_named_pdf(self):
        pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 20, 20))
        path = self.p("in", "photo.pdf")
        os.makedirs(os.path.dirname(path))
        pix.save(path, "png")
        res = self.run_batch([path], [B.step("rotate")])
        self.assertEqual(res.results[0].status, B.FAILED)
        self.assertIn("isn't a PDF", res.results[0].reason)
        self.assertNotIn("fz_", res.results[0].reason)

    def test_a_full_disk_leaves_none_of_the_files_results(self):
        a = _pdf(self.p("in", "a.pdf"))
        real = B.shutil.copyfileobj
        calls = []

        def full(src, dst, *args):
            calls.append(1)
            if len(calls) == 2:             # (the export, after the PDF)
                raise OSError(errno.ENOSPC, "No space left on device")
            return real(src, dst, *args)
        with mock.patch.object(B.shutil, "copyfileobj", full):
            res = self.run_batch([a], [B.step("rotate"), B.step("export", format="txt")])
        self.assertEqual(res.results[0].status, B.FAILED)
        self.assertEqual(res.results[0].outputs, [])
        self.assertEqual(_files(self.p("out")), [])

    def test_a_file_changed_while_processed_is_written_as_it_was_read(self):
        a = _pdf(self.p("in", "a.pdf"))
        res = B.Batch([a], [B.step("search_redact", words="nowhere", scrub=False)],
                      {"mode": "folder", "folder": self.p("out")})
        for ev in res.run():
            if ev is not B.WAIT and ev[1] == 1.0:
                # (the steps are done, nothing needed changing: the file is replaced now)
                _pdf(a, text="Changed after it was read and checked, %s" % WORD)
        out = self.p("out", "a.pdf")
        self.assertEqual(res.results[0].status, B.DONE)
        with pymupdf.open(out) as doc:
            self.assertNotIn("Changed", doc[0].get_text())


# ---- reading comfort ------------------------------------------------------------------------
from kanzonas import read_aloud, reading  # noqa: E402
from tests.test_reading import _Base, _FakeTTS  # noqa: E402


class PresentationFollowsTheDocument(_Base):
    def test_redacted_in_the_window_is_gone_from_the_presentation(self):
        p = reading.start_presentation(self.w)
        APP.processEvents()
        self.v.search_redact("Chapter")
        self.v.apply_redactions(True)
        APP.processEvents()
        self.assertIs(p.doc, self.v.doc)
        self.assertNotIn("Chapter", p.doc[0].get_text())
        self.v.undo()
        self.v.redo()
        self.assertIs(p.doc, self.v.doc)
        p.repaint()
        p.close()

    def test_the_document_closed_under_it(self):
        p = reading.start_presentation(self.w)
        APP.processEvents()
        self.v.close_doc()
        self.assertIsNone(p.doc)
        p._draw_ahead()
        p.go(2)
        QTest.keyClick(p, Qt.Key_End)
        p.repaint()
        p.close()

    def test_f5_again_brings_the_presentation_forward(self):
        p = reading.start_presentation(self.w)
        APP.processEvents()
        self.assertIs(reading.start_presentation(self.w), p)
        p.close()
        APP.processEvents()
        self.assertIsNone(self.w._presentation)


class ReadAloudFollowsTheDocument(_Base):
    def setUp(self):
        super().setUp()
        patch = mock.patch.object(read_aloud, "_engine_class", _FakeTTS)
        patch.start()
        self.addCleanup(patch.stop)

    def test_words_redacted_while_reading_are_not_said(self):
        self.w.a_read_page.trigger()
        eng = _FakeTTS.made[-1]
        eng.finish()
        self.assertEqual(eng.said[-1], "The left column starts here.")
        self.v.search_redact("while")
        self.v.apply_redactions(True)
        APP.processEvents()
        for _ in range(4):
            eng.finish()
        self.assertTrue(eng.said[2:])
        self.assertFalse([s for s in eng.said[2:] if "while" in s], eng.said)
        self.w._reader.stop()

    def test_the_tab_closed_while_reading(self):
        errors = []
        self.w.a_read_doc.trigger()
        eng = _FakeTTS.made[-1]
        eng.finish()
        with mock.patch.object(sys, "excepthook", lambda *a: errors.append(a)), \
                mock.patch.object(self.w, "_confirm_close", return_value=True):
            self.w.close_tab(self.w.tabs.currentIndex())
            eng.stateChanged.emit(eng.State.Ready)      # (the voice, after the document went)
            eng.sayingWord.emit("x", 0, 0, 1)
            for _ in range(3):
                APP.processEvents()
        self.assertEqual(errors, [])
        self.assertEqual(self.w._reader.state, "stopped")


class FullScreenEscape(_Base):
    def test_escape_in_the_reading_view_leaves_full_screen(self):
        reading.show_reading(self.w)
        reading.enter_full_screen(self.w)
        APP.processEvents()
        self.w.reading_pane.text.setFocus()
        QTest.keyClick(self.w.reading_pane.text, Qt.Key_Escape)
        APP.processEvents()
        self.assertFalse(self.w.isFullScreen())
        self.assertIsNone(self.w._full)


if __name__ == "__main__":
    unittest.main()
