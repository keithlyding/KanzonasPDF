"""Tools > Batch processing (kanzonas/batch.py, batch_ui.py): a folder of generated PDFs (with
markups, a form, one encrypted, one corrupt) through every step and through recipes; Bates
numbers continue across the files in list order; the originals are never touched; output
names and folders; Cancel and Stop now leave no half-written file; the report gives every
failure with its reason; recipes are saved and loaded. OCR is mocked (the engine isn't run).

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_batch
"""
import hashlib
import os
import shutil
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402
from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import batch as B  # noqa: E402
from kanzonas import page_tools  # noqa: E402


def _digest(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _text(path, password=None):
    with pymupdf.open(path) as doc:
        if password:
            doc.authenticate(password)
        return "\n".join(p.get_text() for p in doc)


def _scan_page(doc, words=True, specks=0):
    """A page that is only a picture, as from a scanner: a few words drawn into it (or a
    blank sheet with a few specks of dust)."""
    src = pymupdf.open()
    sp = src.new_page(width=612, height=792)
    if words:
        sp.insert_text((72, 120), "Invoice 4471 total 99.00", fontsize=18)
    for k in range(specks):
        sp.draw_circle((100 + 37 * k, 300 + 23 * k), 0.6, color=(0, 0, 0), fill=(0, 0, 0))
    pix = sp.get_pixmap(dpi=100, colorspace=pymupdf.csGRAY)
    page = doc.new_page(width=612, height=792)
    page.insert_image(page.rect, stream=pix.tobytes("png"))
    src.close()


class Folder:
    """The test folder: a.pdf (2 pages, a note, a square markup, a redaction mark, an author),
    b.pdf (3 pages, a filled form field), sub/c.pdf (1 page with a big picture),
    scan.pdf (picture-only pages, one of them blank), enc.pdf (open password "pw1",
    permissions password "own") and bad.pdf (not a PDF)."""

    def __init__(self):
        self.dir = tempfile.mkdtemp(prefix="kz-batch-test-")
        d = self.dir
        os.makedirs(os.path.join(d, "sub"))
        doc = pymupdf.open()
        for k in range(2):
            p = doc.new_page()
            p.insert_text((72, 72), "Alpha page %d secret 123" % (k + 1), fontsize=12)
            p.insert_text((72, 300), "Keep this line", fontsize=12)
        doc[0].add_text_annot((300, 100), "a sticky note")
        doc[0].add_rect_annot(pymupdf.Rect(300, 200, 400, 260))
        hit = doc[1].search_for("secret 123")[0]
        doc[1].add_redact_annot(hit, fill=(0, 0, 0))
        doc.set_metadata({"author": "Jane Author", "title": "Alpha"})
        self.a = os.path.join(d, "a.pdf")
        doc.save(self.a)
        doc = pymupdf.open()
        for k in range(3):
            doc.new_page().insert_text((72, 72), "Bravo page %d" % (k + 1), fontsize=12)
        w = pymupdf.Widget()
        w.field_type = pymupdf.PDF_WIDGET_TYPE_TEXT
        w.field_name = "client"
        w.field_value = "Jane Secret"
        w.rect = pymupdf.Rect(72, 400, 300, 430)
        doc[0].add_widget(w)
        self.b = os.path.join(d, "b.pdf")
        doc.save(self.b)
        doc = pymupdf.open()
        p = doc.new_page()
        p.insert_text((72, 72), "Charlie", fontsize=12)
        # a big picture with some detail (stripes), shown small: Reduce file size shrinks it
        row = b"".join(bytes((x % 255, 60, 200)) if x % 7 < 3 else b"\xc8\x78\x28"
                       for x in range(1600))
        pix = pymupdf.Pixmap(pymupdf.csRGB, 1600, 1600, row * 1600, False)
        p.insert_image(pymupdf.Rect(72, 100, 272, 300), stream=pix.tobytes("jpg", 95))
        self.c = os.path.join(d, "sub", "c.pdf")
        doc.save(self.c)
        doc = pymupdf.open()
        _scan_page(doc)
        _scan_page(doc, words=False, specks=6)
        _scan_page(doc)
        self.scan = os.path.join(d, "scan.pdf")
        doc.save(self.scan)
        doc = pymupdf.open()
        doc.new_page().insert_text((72, 72), "Echo protected", fontsize=12)
        self.enc = os.path.join(d, "enc.pdf")
        doc.save(self.enc, encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="pw1",
                 owner_pw="own", permissions=-1)
        self.bad = os.path.join(d, "bad.pdf")
        with open(self.bad, "wb") as f:
            f.write(b"%PDF-1.7\nthis is not really a PDF\n")
        self.all = [self.a, self.b, self.c, self.scan, self.enc, self.bad]
        self.digests = {p: _digest(p) for p in self.all}

    def out(self, name):
        path = os.path.join(self.dir, "out-" + name)
        return path

    def untouched(self):
        return all(_digest(p) == h for p, h in self.digests.items())


def run(files, steps, out_folder=None, **kw):
    output = kw.pop("output", {})
    if out_folder is not None:
        output = dict({"mode": "folder", "folder": out_folder}, **output)
    b = B.Batch(files, steps, output, **kw)
    b.run_all()
    return b


def fake_read(image):
    """The OCR engine's answer for a page's first tile (the top of a 612-point-wide page, all
    of its width): one line, where the words were drawn. The rest of the OCR is the app's own
    (ocr.read_page: tiles drawn from the display list, the engine in the worker)."""
    s = image.shape[1] / 612
    box = [[72 * s, 104 * s], [360 * s, 104 * s], [360 * s, 124 * s], [72 * s, 124 * s]]
    return [(box, "Invoice 4471 total 99.00", 0.96)]


class Steps(unittest.TestCase):
    """Every step on the folder's files: each output is there and has what the step does."""

    @classmethod
    def setUpClass(cls):
        cls.f = Folder()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.f.dir, ignore_errors=True)

    def tearDown(self):
        self.assertTrue(self.f.untouched(), "an original file was changed")

    def one(self, kind, files=None, **options):
        out = tempfile.mkdtemp(dir=self.f.dir, prefix="out-%s-" % kind)
        b = run(files or [self.f.a, self.f.b, self.f.c], [B.step(kind, **options)], out,
                output={"keep_structure": False})
        for r in b.results:
            self.assertEqual(r.status, B.DONE, "%s: %s %s" % (kind, r.path, r.details()))
            for p in r.outputs:
                self.assertTrue(os.path.isfile(p), p)
        return b, out

    def test_watermark(self):
        _b, out = self.one("watermark", text="CONFIDENTIAL")
        with pymupdf.open(os.path.join(out, "b.pdf")) as doc:
            self.assertTrue(all(page_tools.has_watermark(p) for p in doc))
            self.assertIn("CONFIDENTIAL", doc[2].get_text())

    def test_header_footer_and_page_numbers(self):
        _b, out = self.one("header_footer", header_left="{file}", footer_right="P{page}/{pages}")
        t = _text(os.path.join(out, "b.pdf"))
        self.assertIn("b.pdf", t)
        self.assertIn("P3/3", t)
        _b, out = self.one("page_numbers")
        self.assertIn("Page 2 of 2", _text(os.path.join(out, "a.pdf")))

    def test_flatten_comments(self):
        b, out = self.one("flatten_comments")
        with pymupdf.open(os.path.join(out, "a.pdf")) as doc:
            kinds = [a.type[1] for p in doc for a in p.annots()]
            self.assertEqual(kinds, ["Redact"])       # (a redaction mark stays a mark)
        self.assertIn("kept as marks", b.results[0].details())
        with pymupdf.open(os.path.join(out, "b.pdf")) as doc:
            self.assertEqual(len(list(doc[0].widgets())), 1)     # fields stay fillable

    def test_flatten_comments_applying_redactions_first(self):
        _b, out = self.one("flatten_comments", files=[self.f.a], redactions="apply")
        t = _text(os.path.join(out, "a.pdf"))
        self.assertIn("Alpha page 1 secret 123", t)
        self.assertNotIn("Alpha page 2 secret", t)
        with pymupdf.open(os.path.join(out, "a.pdf")) as doc:
            self.assertEqual([a for p in doc for a in p.annots()], [])

    def test_flatten_fields(self):
        _b, out = self.one("flatten_fields")
        with pymupdf.open(os.path.join(out, "b.pdf")) as doc:
            self.assertEqual(list(doc[0].widgets()), [])
            self.assertIn("Jane Secret", doc[0].get_text())
        with pymupdf.open(os.path.join(out, "a.pdf")) as doc:
            self.assertEqual(len(list(doc[0].annots())), 2)     # markups stay markups

    def test_apply_redactions(self):
        b, out = self.one("apply_redactions")
        t = _text(os.path.join(out, "a.pdf"))
        self.assertIn("Alpha page 1 secret 123", t)
        self.assertNotIn("Alpha page 2 secret", t)
        with pymupdf.open(os.path.join(out, "a.pdf")) as doc:
            self.assertEqual(doc.metadata.get("author"), "")      # scrubbed
        self.assertIn("No redaction marks", b.results[1].details())

    def test_search_and_redact_a_word_list(self):
        b, out = self.one("search_redact", words="secret\nCharlie\n")
        t = _text(os.path.join(out, "a.pdf"))
        self.assertNotIn("secret", t.lower())
        self.assertIn("Keep this line", t)
        with pymupdf.open(os.path.join(out, "b.pdf")) as doc:
            self.assertEqual(list(doc[0].widgets()), [])        # its value had the word
            raw = b"".join(doc.xref_object(x).encode() for x in range(1, doc.xref_length()))
            self.assertNotIn(b"Jane Secret", raw)
        self.assertNotIn("Charlie", _text(os.path.join(out, "c.pdf")))

    def test_search_and_redact_a_word_only_in_the_properties(self):
        b, out = self.one("search_redact", files=[self.f.a], words="Jane Author", scrub=False)
        with pymupdf.open(os.path.join(out, "a.pdf")) as doc:
            self.assertEqual(doc.metadata["author"], "[redacted]")
            self.assertEqual(doc.metadata["title"], "Alpha")
        self.assertEqual(b.results[0].details(), "Not found on the pages; removed from 1 "
                         "document propert(ies); 1 redaction mark(s) already in the file "
                         "applied too")

    def test_search_and_redact_marks_only(self):
        # (owner, 6 Nov: when only marking, the results say plainly that nothing was removed
        # yet, and the file's name says so too)
        b, out = self.one("search_redact", files=[self.f.a, self.f.c], words="Keep",
                          apply=False)
        self.assertEqual(sorted(os.listdir(out)), ["a-marked.pdf", "c.pdf"])
        with pymupdf.open(os.path.join(out, "a-marked.pdf")) as doc:
            self.assertEqual(sum(1 for p in doc for a in p.annots() if a.type[1] == "Redact"), 3)
        self.assertIn("Keep this line", _text(os.path.join(out, "a-marked.pdf")))
        self.assertEqual(b.results[0].details(),
                         "Marked 2 occurrence(s) for redaction on page(s) 1-2; nothing was "
                         "removed yet: open the file and use Apply redactions")
        # (c.pdf: nothing found, nothing marked: its usual name)
        self.assertEqual(b.results[1].details().split("; ")[0],
                         "No matches on the pages: nothing was marked")

    def test_marked_files_keep_a_name_pattern_of_the_users_own(self):
        out = self.f.out("marked-pattern")
        b = run([self.f.a], [B.step("search_redact", words="Keep", apply=False)], out,
                output={"pattern": "{name}_review"})
        self.assertEqual(os.listdir(out), ["a_review.pdf"])
        self.assertIn("nothing was removed yet", b.results[0].details())
        # marks applied by a later step: nothing marked is left, the usual name
        out = self.f.out("marked-then-applied")
        b = run([self.f.a], [B.step("search_redact", words="Keep", apply=False),
                             B.step("apply_redactions")], out)
        self.assertEqual(os.listdir(out), ["a.pdf"])
        self.assertNotIn("Keep this line", _text(os.path.join(out, "a.pdf")))
        self.assertIn("Applied 3 redaction(s) on page(s) 1-2", b.results[0].details())

    def test_sanitize(self):
        _b, out = self.one("sanitize")
        with pymupdf.open(os.path.join(out, "a.pdf")) as doc:
            self.assertEqual(doc.metadata.get("author"), "")

    def test_reduce_file_size(self):
        b, out = self.one("compress", files=[self.f.c], preset="Smallest (72 dpi images)")
        self.assertLess(os.path.getsize(os.path.join(out, "c.pdf")), os.path.getsize(self.f.c))
        self.assertIn("→", b.results[0].details())

    def test_rotate(self):
        _b, out = self.one("rotate", angle=90, which="even")
        with pymupdf.open(os.path.join(out, "b.pdf")) as doc:
            self.assertEqual([p.rotation for p in doc], [0, 90, 0])

    def test_delete_blank_pages(self):
        b, out = self.one("delete_blank", files=[self.f.scan, self.f.a])
        with pymupdf.open(os.path.join(out, "scan.pdf")) as doc:
            self.assertEqual(doc.page_count, 2)
        self.assertIn("Deleted blank page(s): 2", b.results[0].details())
        with pymupdf.open(os.path.join(out, "a.pdf")) as doc:
            self.assertEqual(doc.page_count, 2)

    def test_add_and_remove_password(self):
        _b, out = self.one("add_password", files=[self.f.a], open_pw="open1", owner_pw="own1")
        with pymupdf.open(os.path.join(out, "a.pdf")) as doc:
            self.assertTrue(doc.needs_pass)
            self.assertTrue(doc.authenticate("open1"))
        asked = []
        out2 = tempfile.mkdtemp(dir=self.f.dir)
        b = run([self.f.enc], [B.step("remove_password", password="own")], out2,
                ask_password=lambda p, kind: asked.append(kind) or "pw1")
        self.assertEqual(b.results[0].status, B.DONE, b.results[0].details())
        self.assertEqual(asked, ["open"])
        with pymupdf.open(b.results[0].outputs[0]) as doc:
            self.assertFalse(doc.needs_pass)
            self.assertFalse(doc.metadata.get("encryption"))
            self.assertIn("Echo protected", doc[0].get_text())

    def test_document_properties(self):
        _b, out = self.one("properties", title="Case 12: {name}", author="Legal")
        with pymupdf.open(os.path.join(out, "b.pdf")) as doc:
            self.assertEqual(doc.metadata["title"], "Case 12: b")
            self.assertEqual(doc.metadata["author"], "Legal")

    def test_pdfa(self):
        from kanzonas import pdfa
        b, out = self.one("pdfa", files=[self.f.a, self.f.b])
        for name in ("a.pdf", "b.pdf"):
            with open(os.path.join(out, name), "rb") as fh:
                self.assertEqual(pdfa.pdfa_part_of(fh.read()), 2)
        self.assertIn("PDF/A-2b", b.results[0].details())

    def test_pdfa_of_a_protected_file_needs_remove_password(self):
        out = tempfile.mkdtemp(dir=self.f.dir)
        b = run([self.f.enc], [B.step("pdfa")], out, ask_password=lambda p, k: "pw1")
        self.assertEqual(b.results[0].status, B.FAILED)
        self.assertIn("Remove password", b.results[0].reason)
        b = run([self.f.enc], [B.step("remove_password", password="own"), B.step("pdfa")], out,
                ask_password=lambda p, k: "pw1")
        self.assertEqual(b.results[0].status, B.DONE, b.results[0].details())

    def test_ocr(self):
        calls = []

        def read(image):
            calls.append(image.shape)
            return fake_read(image)
        with mock.patch("kanzonas.ocr._read", read):
            b, out = self.one("ocr", files=[self.f.scan, self.f.a], accuracy="fast")
        self.assertEqual(len(calls), 3)         # the scan's pages; a.pdf has text already
        with pymupdf.open(os.path.join(out, "scan.pdf")) as doc:
            self.assertIn("Invoice 4471", doc[0].get_text())
            self.assertTrue(doc[0].search_for("4471"))
        self.assertIn("every page already has text", b.results[1].details())

    def test_exports(self):
        for fmt, names in (("txt", ["a.txt"]), ("excel", ["a.xlsx"]), ("png", ["a_p1.png",
                                                                             "a_p2.png"]),
                           ("word", ["a.docx"])):
            out = tempfile.mkdtemp(dir=self.f.dir)
            b = run([self.f.a], [B.step("export", format=fmt, dpi=50)], out)
            self.assertEqual(b.results[0].status, B.DONE, b.results[0].details())
            # only the export: no step changed the PDF, so no copy of it is written
            self.assertEqual(sorted(os.listdir(out)), names, fmt)
        out = tempfile.mkdtemp(dir=self.f.dir)
        run([self.f.a], [B.step("search_redact", words="secret"), B.step("export", format="txt")],
            out)
        self.assertEqual(sorted(os.listdir(out)), ["a.pdf", "a.txt"])
        with open(os.path.join(out, "a.txt"), encoding="utf-8") as fh:
            self.assertNotIn("secret", fh.read())       # from the document as redacted


class BatesAndCombine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.f = Folder()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.f.dir, ignore_errors=True)

    def test_bates_numbers_continue_in_list_order(self):
        out = self.f.out("bates")
        b = run([self.f.b, self.f.bad, self.f.a, self.f.c],
                [B.step("bates", prefix="DEF", start=100, digits=5)], out,
                output={"keep_structure": False})
        self.assertEqual([r.status for r in b.results], [B.DONE, B.FAILED, B.DONE, B.DONE])
        tb, ta, tc = (_text(os.path.join(out, n)) for n in ("b.pdf", "a.pdf", "c.pdf"))
        for n in ("DEF00100", "DEF00101", "DEF00102"):
            self.assertIn(n, tb)
        # the corrupt file in between used no numbers
        self.assertIn("DEF00103", ta)
        self.assertIn("DEF00104", ta)
        self.assertIn("DEF00105", tc)
        self.assertNotIn("DEF00106", tc)
        self.assertIn("Bates DEF00103 to DEF00104", b.results[2].details())
        self.assertTrue(self.f.untouched())

    def test_named_by_bates_number(self):
        out = self.f.out("bates-names")
        run([self.f.a, self.f.b], [B.step("bates", prefix="X", digits=4)], out,
            output={"pattern": "{bates}"})
        self.assertEqual(sorted(os.listdir(out)), ["X0001.pdf", "X0003.pdf"])

    def test_combined_recipe(self):
        """Watermark, Bates and flatten on each file, then all combined into one PDF in list
        order, a bookmark per file, the Bates numbers running through."""
        out = self.f.out("combine")
        steps = [B.step("watermark"), B.step("bates", prefix="P"), B.step("flatten_comments"),
                 B.step("combine", name="Production")]
        self.assertEqual(B.check_steps(steps), [])
        b = run([self.f.a, self.f.b, self.f.c, self.f.bad], steps, out)
        self.assertEqual([r.status for r in b.results], [B.DONE, B.DONE, B.DONE, B.FAILED,
                                                         B.DONE])
        self.assertEqual(os.listdir(out), ["Production.pdf"])     # not each file
        with pymupdf.open(os.path.join(out, "Production.pdf")) as doc:
            self.assertEqual(doc.page_count, 6)
            self.assertEqual([t[1] for t in doc.get_toc() if t[0] == 1], ["a", "b", "c"])
            for k in range(6):
                self.assertIn("P%06d" % (k + 1), doc[k].get_text())
        self.assertTrue(b.results[-1].combined)
        self.assertIn("1 file(s) left out", b.results[-1].details())
        out = self.f.out("combine-each")
        steps[-1] = B.step("combine", keep_each=True)
        run([self.f.a, self.f.b], steps, out)
        self.assertEqual(sorted(os.listdir(out)), ["Combined.pdf", "a.pdf", "b.pdf"])
        self.assertTrue(self.f.untouched())

    def test_archive_recipe(self):
        steps = B.builtin_recipes()["Archive (OCR + PDF/A)"]
        out = self.f.out("archive")
        with mock.patch("kanzonas.ocr._read", fake_read):
            b = run([self.f.scan], steps, out)
        self.assertEqual(b.results[0].status, B.DONE, b.results[0].details())
        from kanzonas import pdfa
        with open(os.path.join(out, "scan.pdf"), "rb") as fh:
            data = fh.read()
        self.assertEqual(pdfa.pdfa_part_of(data), 2)
        with pymupdf.open(stream=data) as doc:
            self.assertIn("Invoice 4471", doc[0].get_text())


class OutputRules(unittest.TestCase):
    def setUp(self):
        self.f = Folder()

    def tearDown(self):
        self.assertTrue(self.f.untouched(), "an original file was changed")
        shutil.rmtree(self.f.dir, ignore_errors=True)

    def test_processed_folder_next_to_each_file(self):
        b = run([self.f.a, self.f.c], [B.step("rotate")])
        self.assertEqual([r.status for r in b.results], [B.DONE, B.DONE])
        self.assertTrue(os.path.isfile(os.path.join(self.f.dir, "Processed", "a.pdf")))
        self.assertTrue(os.path.isfile(os.path.join(self.f.dir, "sub", "Processed", "c.pdf")))

    def test_folder_structure_and_names(self):
        items = B.files_in(self.f.dir)
        self.assertEqual([os.path.basename(i.path) for i in items],
                         ["a.pdf", "b.pdf", "bad.pdf", "enc.pdf", "scan.pdf", "c.pdf"])
        self.assertEqual(len(B.files_in(self.f.dir, subfolders=False)), 5)
        out = self.f.out("tree")
        items = [i for i in items if i.path in (self.f.a, self.f.c)]
        run(items, [B.step("rotate")], out, output={"pattern": "{n}_{name}_ocr"})
        self.assertTrue(os.path.isfile(os.path.join(out, "001_a_ocr.pdf")))
        self.assertTrue(os.path.isfile(os.path.join(out, "sub", "002_c_ocr.pdf")))
        # Processed folders are left out when a folder is added again
        run(items, [B.step("rotate")])
        self.assertTrue(os.path.isdir(os.path.join(self.f.dir, "Processed")))
        self.assertFalse([i for i in B.files_in(self.f.dir) if "Processed" in i.path])
        # flat: the same name twice gets a number, never one over the other
        shutil.copy(self.f.a, os.path.join(self.f.dir, "sub", "a.pdf"))
        out = self.f.out("flat")
        b = run([self.f.a, os.path.join(self.f.dir, "sub", "a.pdf")], [B.step("rotate")], out,
                output={"keep_structure": False})
        self.assertEqual(sorted(os.listdir(out)), ["a (2).pdf", "a.pdf"])
        self.assertEqual([r.status for r in b.results], [B.DONE, B.DONE])

    def test_files_already_there(self):
        out = self.f.out("exists")
        os.makedirs(out)
        there = os.path.join(out, "a.pdf")
        with open(there, "wb") as fh:
            fh.write(b"old")
        b = run([self.f.a], [B.step("rotate")], out, output={"overwrite": "skip"})
        self.assertEqual(b.results[0].status, B.SKIPPED)
        self.assertIn("already exists", b.results[0].reason)
        with open(there, "rb") as fh:
            self.assertEqual(fh.read(), b"old")
        run([self.f.a], [B.step("rotate")], out, output={"overwrite": "number"})
        self.assertTrue(os.path.isfile(os.path.join(out, "a (2).pdf")))
        asked = []
        run([self.f.a, self.f.b], [B.step("rotate")], out,
            ask_overwrite=lambda p: asked.append(os.path.basename(p)) or "replace_all")
        with open(os.path.join(out, "b.pdf"), "wb") as fh:
            fh.write(b"old")
        self.assertEqual(asked, ["a.pdf"])                    # (then "all": not asked again)
        with pymupdf.open(there) as doc:
            self.assertEqual(doc[0].rotation, 90)

    def test_never_replaces_the_originals_unless_allowed(self):
        b = run([self.f.a], [B.step("rotate")], self.f.dir)
        self.assertEqual(b.results[0].status, B.SKIPPED)
        self.assertIn("replace the original", b.results[0].reason)
        self.assertTrue(self.f.untouched())
        copy = os.path.join(self.f.dir, "copy.pdf")
        shutil.copy(self.f.a, copy)
        b = run([copy], [B.step("rotate")], self.f.dir, output={"replace_originals": True})
        self.assertEqual(b.results[0].status, B.DONE)
        with pymupdf.open(copy) as doc:
            self.assertEqual(doc[0].rotation, 90)

    def test_protected_files(self):
        enc2 = os.path.join(self.f.dir, "enc2.pdf")
        shutil.copy(self.f.enc, enc2)
        steps = [B.step("watermark")]
        b = run([self.f.enc], steps, self.f.out("p0"), output={"protected": "skip"})
        self.assertEqual(b.results[0].status, B.SKIPPED)
        self.assertIn("password", b.results[0].reason)
        b = run([self.f.enc], steps, self.f.out("p1"), ask_password=lambda p, k: "wrong")
        self.assertEqual(b.results[0].status, B.SKIPPED)
        self.assertIn("doesn't open it", b.results[0].reason)
        asked = []
        b = run([self.f.enc, self.f.a, enc2], steps, self.f.out("p2"),
                ask_password=lambda p, k: asked.append(p) or "pw1")
        self.assertEqual([r.status for r in b.results], [B.DONE] * 3)
        self.assertEqual(asked, [self.f.enc])                  # asked once for both
        with pymupdf.open(b.results[2].outputs[0]) as doc:
            self.assertTrue(doc.needs_pass)                    # keeps its protection
            self.assertTrue(doc.authenticate("pw1"))
            self.assertIn("CONFIDENTIAL", doc[0].get_text())


    def test_file_that_does_not_allow_changes(self):
        """Opens without a password but its permissions forbid changes: its permissions
        password is asked (or taken from Remove password); without it the file is skipped.
        Edited, it keeps its protection."""
        doc = pymupdf.open()
        doc.new_page().insert_text((72, 72), "Restricted", fontsize=12)
        path = os.path.join(self.f.dir, "restricted.pdf")
        doc.save(path, encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="own",
                 permissions=pymupdf.PDF_PERM_PRINT)
        asked = []
        b = run([path], [B.step("watermark")], self.f.out("r1"),
                ask_password=lambda p, k: asked.append(k) or "own")
        self.assertEqual(b.results[0].status, B.DONE, b.results[0].details())
        self.assertEqual(asked, ["permissions"])
        with pymupdf.open(b.results[0].outputs[0]) as out:
            self.assertTrue(out.metadata["encryption"])
            self.assertFalse(out.permissions & pymupdf.PDF_PERM_MODIFY)
            self.assertIn("CONFIDENTIAL", out[0].get_text())
        b = run([path], [B.step("watermark")], self.f.out("r2"), ask_password=lambda p, k: None)
        self.assertEqual(b.results[0].status, B.SKIPPED)
        self.assertIn("permissions password", b.results[0].reason)
        b = run([path], [B.step("remove_password", password="own")], self.f.out("r3"))
        self.assertEqual(b.results[0].status, B.DONE, b.results[0].details())
        with pymupdf.open(b.results[0].outputs[0]) as out:
            self.assertFalse(out.metadata["encryption"])


class Report(unittest.TestCase):
    def test_failures_with_their_reasons(self):
        f = Folder()
        self.addCleanup(shutil.rmtree, f.dir, True)
        b = run([f.a, f.bad, os.path.join(f.dir, "gone.pdf"), f.enc],
                [B.step("watermark"), B.step("pdfa")], f.out("r"),
                ask_password=lambda p, k: None)
        st = [(r.status, r.reason) for r in b.results]
        self.assertEqual(st[0][0], B.DONE)
        self.assertEqual(st[1][0], B.FAILED)
        self.assertIn("isn't a PDF", st[1][1])
        self.assertEqual(st[2][0], B.FAILED)
        self.assertIn("Couldn't read it", st[2][1])
        self.assertEqual(st[3][0], B.SKIPPED)
        self.assertIn("password", st[3][1])
        text = B.report_text(b.results)
        for word in ("Done", "Failed", "Skipped", "bad.pdf", "isn't a PDF"):
            self.assertIn(word, text)
        csv_path = os.path.join(f.dir, "report.csv")
        B.write_report(b.results, csv_path)
        import csv
        with open(csv_path, encoding="utf-8-sig", newline="") as fh:
            rows = list(csv.reader(fh))
        self.assertEqual(rows[0], ["File", "Status", "Output", "Details"])
        self.assertEqual(len(rows), 5)
        self.assertEqual(rows[2][1], "Failed")
        # a cell that would run as a formula in Excel stays text
        r = B.Result("=HYPERLINK(\"x\")", B.FAILED, "+1 problem")
        B.write_report([r], csv_path)
        with open(csv_path, encoding="utf-8-sig", newline="") as fh:
            rows = list(csv.reader(fh))
        self.assertTrue(rows[1][0].startswith("'="))
        self.assertTrue(rows[1][3].startswith("'+"))

    def test_signed_file_is_skipped(self):
        f = Folder()
        self.addCleanup(shutil.rmtree, f.dir, True)
        with mock.patch.object(B.BatchDoc, "_has_filled_signature", lambda self: True,
                               create=True):
            b = run([f.a], [B.step("watermark")], f.out("s"))
        self.assertEqual(b.results[0].status, B.SKIPPED)
        self.assertIn("digitally signed", b.results[0].reason)


class Cancel(unittest.TestCase):
    def setUp(self):
        self.f = Folder()
        self.addCleanup(shutil.rmtree, self.f.dir, True)
        # the same scan three times
        self.scans = []
        for k in range(3):
            p = os.path.join(self.f.dir, "scan%d.pdf" % k)
            shutil.copy(self.f.scan, p)
            self.scans.append(p)

    def leftovers(self, folder):
        return [n for _d, _s, names in os.walk(folder) for n in names
                if n.endswith(".kanzonas-tmp")]

    def test_cancel_finishes_the_current_file(self):
        out = self.f.out("cancel")
        b = B.Batch(self.scans, [B.step("ocr"), B.step("export", format="txt")],
                    {"mode": "folder", "folder": out})

        def read(image):
            b.cancel = True                 # clicked while the first file is being read
            return fake_read(image)
        with mock.patch("kanzonas.ocr._read", read):
            b.run_all()
        self.assertEqual([r.status for r in b.results], [B.DONE, B.CANCELED, B.CANCELED])
        self.assertEqual(sorted(os.listdir(out)), ["scan0.pdf", "scan0.txt"])
        self.assertIn("Invoice 4471", _text(os.path.join(out, "scan0.pdf")))

    def test_stop_now_leaves_nothing_half_written(self):
        out = self.f.out("stop")
        b = B.Batch(self.scans, [B.step("ocr"), B.step("watermark"),
                                 B.step("export", format="txt")],
                    {"mode": "folder", "folder": out})
        seen = []

        def read(image):
            seen.append(1)
            if len(seen) == 5:          # on the second file's second page
                b.stop = True
                time.sleep(0.05)
            return fake_read(image)
        with mock.patch("kanzonas.ocr._read", read):
            b.run_all()
        self.assertEqual([r.status for r in b.results], [B.DONE, B.CANCELED, B.CANCELED])
        self.assertIn("nothing was written", b.results[1].reason)
        # the first file whole (its PDF and its export); nothing of the second
        self.assertEqual(sorted(os.listdir(out)), ["scan0.pdf", "scan0.txt"])
        self.assertEqual(self.leftovers(out), [])
        self.assertTrue(self.f.untouched())

    def test_stop_while_saving_in_the_window_loop(self):
        """The generator driven step by step, stopped at every possible point: never a
        partial or temporary file left behind."""
        k = 1
        while True:
            out = self.f.out("step%d" % k)
            b = B.Batch([self.f.a, self.f.b], [B.step("bates"), B.step("export", format="txt")],
                        {"mode": "folder", "folder": out})
            gen = b.run()
            n = 0
            for ev in gen:
                if ev is B.WAIT:
                    time.sleep(0.002)
                    continue
                n += 1
                if n == k:
                    b.stop = True
            names = sorted(os.listdir(out)) if os.path.isdir(out) else []
            self.assertEqual(self.leftovers(self.f.dir), [])
            self.assertIn(names, ([], ["a.pdf", "a.txt"], ["a.pdf", "a.txt", "b.pdf", "b.txt"]))
            if b.results[-1].status == B.DONE:
                break
            k += 1
        self.assertGreater(k, 3)


class Recipes(unittest.TestCase):
    def settings(self):
        path = os.path.join(tempfile.mkdtemp(), "s.ini")
        self.addCleanup(lambda: shutil.rmtree(os.path.dirname(path), True))
        return QSettings(path, QSettings.IniFormat)

    def test_ready_made_recipes_can_run(self):
        names = list(B.builtin_recipes())
        self.assertEqual(names, ["Make searchable (OCR)", "Archive (OCR + PDF/A)",
                                 "Confidential (watermark + flatten)",
                                 "Bates number for production", "Shrink for email"])
        for name, steps in B.builtin_recipes().items():
            self.assertEqual(B.check_steps(steps), [], name)

    def test_save_load_delete(self):
        s = self.settings()
        steps = [B.step("watermark", text="DRAFT"), B.step("add_password", open_pw="secret1",
                                                           owner_pw="secret2")]
        B.save_recipe(s, "Drafts", steps)
        got = B.recipes(s)["Drafts"]
        self.assertEqual([st["kind"] for st in got], ["watermark", "add_password"])
        self.assertEqual(got[0]["options"]["text"], "DRAFT")
        self.assertEqual(got[1]["options"]["open_pw"], "")        # passwords aren't kept
        self.assertNotIn("secret1", str(s.value(B.RECIPES_KEY)))
        self.assertIn("Make searchable (OCR)", B.recipes(s))
        self.assertEqual(B.user_recipes(s), {"Drafts"})
        self.assertTrue(B.delete_recipe(s, "Drafts"))
        self.assertNotIn("Drafts", B.recipes(s))
        self.assertFalse(B.delete_recipe(s, "Make searchable (OCR)"))   # (ready-made)

    def test_unreadable_settings(self):
        s = self.settings()
        s.setValue(B.RECIPES_KEY, '{"x": [{"kind": "nope"}, {"kind": "rotate", "options": '
                                  '{"angle": "45", "which": 7, "pages": 3}}], "y": 5}')
        got = B.recipes(s)
        self.assertEqual([st["kind"] for st in got["x"]], ["rotate"])
        self.assertEqual(got["x"][0]["options"], B.step("rotate")["options"])
        s.setValue(B.RECIPES_KEY, "not json")
        self.assertIn("Shrink for email", B.recipes(s))

    def test_checks(self):
        self.assertEqual(B.check_steps([]), ["Add at least one step."])
        p = B.check_steps([B.step("combine"), B.step("rotate")])
        self.assertTrue(any("last step" in m for m in p))
        p = B.check_steps([B.step("pdfa"), B.step("watermark")])
        self.assertTrue(any("PDF/A" in m for m in p))
        self.assertEqual(B.check_steps([B.step("pdfa"), B.step("export"), B.step("combine")]), [])
        p = B.check_steps([B.step("add_password")])
        self.assertTrue(any("password" in m for m in p))
        p = B.check_steps([B.step("rotate", pages="1-x")])
        self.assertTrue(any("1-x" in m for m in p))
        self.assertEqual(B.page_list("2-, 1", 3), [0, 1, 2])
        self.assertEqual(B.page_list("2-9", 3), [1, 2])       # past the end: stops there
        self.assertEqual(B.page_list("", 2), [0, 1])


class BlankPages(unittest.TestCase):
    def test_detector(self):
        doc = pymupdf.open()
        _scan_page(doc, words=False)
        _scan_page(doc, words=False, specks=10)
        _scan_page(doc)
        doc.new_page()                                      # empty
        p = doc.new_page()
        p.insert_text((300, 760), "3", fontsize=9)          # text: kept
        p = doc.new_page()
        p.add_text_annot((100, 100), "note")                # a markup: kept
        p = doc.new_page()
        p.draw_line((100, 400), (300, 400), width=1)       # a short line: kept
        self.assertEqual([page_tools.is_blank(pg) for pg in doc],
                         [True, True, False, True, False, False, False])


class MainsFeaturesInSteps(unittest.TestCase):
    """1.9.1's added-text blocks stay one block through the steps that rewrite pages; the
    compacting saves (Save as PDF/A, Reduce file size) keep a placed page's drawing
    (save_guard)."""

    TEXT = "A block of added words wrapped in a narrow box of its own"

    def setUp(self):
        from kanzonas import added_text, text_styles
        self.dir = tempfile.mkdtemp(prefix="kz-batch-main-")
        self.addCleanup(shutil.rmtree, self.dir, True)
        d = pymupdf.open()
        for _k in range(2):
            d.new_page().insert_text((72, 600), "Unrelated private line", fontsize=11)
        page = d[0]
        keys = [text_styles.Style(family="Helvetica", size=11.0)] * len(self.TEXT)
        added_text.write(page, pymupdf.Point(80, 120), 0, self.TEXT, keys, 13.2, 120)
        page.add_text_annot((300, 300), "note").update()
        # a page placed on page 2 (a form of its own: what a compacting save emptied)
        src = pymupdf.open()
        src.new_page().insert_text((72, 72), "Placed drawing words", fontsize=14)
        d[1].show_pdf_page(pymupdf.Rect(300, 50, 500, 300), src, 0)
        self.path = os.path.join(self.dir, "blocks.pdf")
        d.save(self.path)

    def blocks(self, path):
        from kanzonas import added_text, text_edit
        with pymupdf.open(path) as doc:
            page = doc[0]
            found = added_text.find(page, text_edit.text_lines(page))
            self.assertEqual(len(found), 1)
            self.assertEqual(" ".join(page.get_text("text", clip=found[0].rect).split()),
                             self.TEXT)
            self.assertIn("Placed drawing words", doc[1].get_text())

    def test_page_rewriting_steps_keep_the_block(self):
        chains = [[B.step("watermark"), B.step("header_footer", footer_center="{page}"),
                   B.step("bates"), B.step("flatten_comments"),
                   B.step("flatten_fields", comments=True),
                   B.step("search_redact", words="private"), B.step("sanitize"),
                   B.step("rotate", angle=180), B.step("rotate", angle=180)],
                  [B.step("compress", preset="Smallest (72 dpi images)")],
                  [B.step("pdfa")]]
        for k, steps in enumerate(chains):
            with self.subTest(steps=[st["kind"] for st in steps]):
                out = os.path.join(self.dir, "out%d" % k)
                b = run([self.path], steps, out)
                self.assertEqual(b.results[0].status, B.DONE, b.results[0].details())
                self.blocks(b.results[0].outputs[0])


class Window(unittest.TestCase):
    def test_window_runs_a_recipe(self):
        f = Folder()
        self.addCleanup(shutil.rmtree, f.dir, True)
        from kanzonas.main_window import MainWindow
        from kanzonas import batch_ui
        win = MainWindow()
        self.addCleanup(lambda: (setattr(win, "_close_confirmed", True), win.close()))
        acts = {a.text() for m in win.menuBar().actions() if m.menu()
                for a in m.menu().actions()}
        self.assertIn("&Batch processing...", acts)
        w = batch_ui.BatchWindow.open_for(win)
        self.assertIs(batch_ui.BatchWindow.open_for(win), w)
        w.subfolders.setChecked(True)
        w.add_paths([f.dir])
        while w._count_todo:
            APP.processEvents()
        rows = {it.text(0): it.text(1) for it in w._items_widgets()}
        self.assertEqual(rows["b.pdf"], "3")
        self.assertEqual(rows["enc.pdf"], "protected")
        self.assertEqual(rows["bad.pdf"], "can't read")
        w.recipe.setCurrentIndex(w.recipe.findData("Bates number for production"))
        w._load_recipe(w.recipe.currentIndex())
        self.assertEqual([s["kind"] for s in w.steps], ["bates"])
        for r in range(w.step_list.count()):
            w.step_list.setCurrentRow(r)
        w.protected.setCurrentIndex(w.protected.findData("skip"))
        out = f.out("window")
        w.out_folder.setChecked(True)
        w.folder.setText(out)
        reports = []
        with mock.patch.object(batch_ui.ReportDialog, "exec",
                               lambda self: reports.append(self.results)):
            w.run()
            t = time.monotonic()
            while w._gen is not None and time.monotonic() - t < 60:
                APP.processEvents()
        self.assertEqual(len(reports), 1)
        st = {os.path.basename(r.path): r.status for r in reports[0]}
        self.assertEqual(st, {"a.pdf": B.DONE, "b.pdf": B.DONE, "bad.pdf": B.FAILED,
                              "enc.pdf": B.SKIPPED, "scan.pdf": B.DONE, "c.pdf": B.DONE})
        self.assertTrue(os.path.isfile(os.path.join(out, "sub", "c.pdf")))
        self.assertTrue(f.untouched())
        status = {it.text(0): it.text(2) for it in w._items_widgets()}
        self.assertEqual(status["bad.pdf"], "Failed")
        # every step's options can be shown
        for kind in B.steps_table():
            w.add_step(B.step(kind))
        for r in range(w.step_list.count()):
            w.step_list.setCurrentRow(r)
        self.assertEqual(w.steps[-1]["kind"], "combine")
        w.close()


if __name__ == "__main__":
    unittest.main()
