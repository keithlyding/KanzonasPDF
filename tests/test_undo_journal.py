"""Undo and redo through MuPDF's journal (kanzonas/undo_journal.py, DocumentView.modify):
for every kind of edit the document comes back exactly as a copy per edit (up to 1.6)
brings it back; saving, merged steps, failed edits, protected files, a replaced document
and the memory budget keep working.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_undo_journal
"""
import io
import os
import re
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import annotations as A, undo_journal as UJ  # noqa: E402
import kanzonas.document_view as DV  # noqa: E402
from kanzonas.document_view import DocumentView  # noqa: E402

m = pymupdf.mupdf
P = pymupdf.Point
# what differs between two runs of the same edit (dates, random names)
VOLATILE = ("NM", "M", "CreationDate", "ModDate", "Producer", "KZGroup")


def png(w=40, h=30, rgb=(20, 120, 220)):
    pm = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, w, h), False)
    pm.set_rect(pm.irect, rgb)
    return pm.tobytes("png")


def sample(path, pages=4):
    """Text, drawings, a markup per page, a form field, a link, bookmarks, metadata, an
    attachment and a picture."""
    d = pymupdf.open()
    for i in range(pages):
        p = d.new_page(width=612, height=792)
        p.insert_text((72, 72), "Page %d Contractor agrees" % (i + 1), fontsize=12)
        p.insert_text((72, 100), "Second line of text here", fontsize=11)
        p.draw_rect((100, 200, 300, 300), color=(0, 0, 1), width=2)
        p.draw_line((100, 350), (400, 380), color=(1, 0, 0), width=1)
        a = p.add_rect_annot((350, 400, 450, 470))
        a.set_colors(stroke=(0, 0.5, 0))
        a.update()
        if i == 1:
            w = pymupdf.Widget()
            w.field_name = "who"
            w.field_type = pymupdf.PDF_WIDGET_TYPE_TEXT
            w.rect = pymupdf.Rect(72, 500, 300, 525)
            p.add_widget(w)
        if i == 2:
            p.insert_link({"kind": pymupdf.LINK_GOTO, "from": pymupdf.Rect(72, 600, 200, 620),
                           "page": 0})
            p.insert_image((400, 600, 500, 680), stream=png())
    d.set_toc([[1, "First", 1], [2, "Second", 2], [1, "Third", 3]])
    d.set_metadata({"title": "Test", "author": "Me"})
    d.embfile_add("note.txt", b"attached text")
    d.save(path, garbage=3, deflate=True)
    return path


def canon(doc, password=None):
    """The document as bytes that two documents with the same content share: written out,
    opened again, dates and random names blanked, compacted."""
    keep = {"encryption": pymupdf.PDF_ENCRYPT_KEEP} \
        if doc.xref_get_key(-1, "Encrypt")[0] != "null" else {}
    d = pymupdf.open("pdf", doc.tobytes(garbage=1, no_new_id=True, **keep))
    if d.needs_pass:
        d.authenticate(password or "owner")
    for x in range(1, d.xref_length()):
        try:
            keys = d.xref_get_keys(x)
        except Exception:
            continue
        for k in VOLATILE:
            if k in keys:
                d.xref_set_key(x, k, "null")
    d.xref_set_key(-1, "ID", "null")
    d.set_metadata({k: v for k, v in (d.metadata or {}).items()
                    if k in ("title", "author", "subject", "keywords", "creator")})
    raw = d.tobytes(garbage=4, expand=255, no_new_id=True)
    return re.sub(rb"/[A-Z]{6}\+", b"/XXXXXX+", raw)     # (font subset prefixes)


def look(doc):
    """Read every page the way the view does (drawn, text, markups, fields, links)."""
    for p in doc:
        p.get_pixmap(dpi=15, annots=True)
        p.get_text()
        list(p.annots())
        list(p.widgets())
        p.get_links()
    doc.get_toc()


class Quiet(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        for name, value in (("information", None), ("warning", None),
                            ("critical", None), ("question", QMessageBox.Yes)):
            patch = mock.patch.object(QMessageBox, name, return_value=value)
            patch.start()
            self.addCleanup(patch.stop)
        patch = mock.patch.object(DV, "USE_JOURNAL", True)
        patch.start()
        self.addCleanup(patch.stop)

    def path(self, name):
        return os.path.join(self.tmp.name, name)

    def view(self, journal=True, name=None):
        DV.USE_JOURNAL = journal
        src = self.path("src.pdf")
        if not os.path.exists(src):
            sample(src)
        path = self.path(name or ("j.pdf" if journal else "c.pdf"))
        with open(src, "rb") as f, open(path, "wb") as g:
            g.write(f.read())
        v = DocumentView(path)
        v.resize(900, 700)

        def close():
            if not v.doc.is_closed:
                v.dirty = False
                v.close_doc()
        self.addCleanup(close)
        return v


# ---- the journal itself, on every kind of PyMuPDF edit the app makes --------------------
def _freetext(d):
    d[0].add_freetext_annot((100, 600, 300, 650), "Hello box", fontsize=14,
                            fontname="Helv").update()


def _change_markup(d):
    page = d[0]                     # (kept alive while its markup is used)
    a = page.first_annot
    a.set_colors(stroke=(0, 1, 0))
    a.set_info(content="note")
    a.update()


def _redact(d):
    p = d[0]
    p.add_redact_annot((72, 55, 150, 80))
    p.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_PIXELS,
                       graphics=pymupdf.PDF_REDACT_LINE_ART_REMOVE_IF_TOUCHED)


def _font_text(d):
    font = pymupdf.Font("cour")
    d[3].insert_font(fontname="KZC", fontbuffer=font.buffer)
    d[3].insert_text((100, 650), "Courier text", fontname="KZC")


def _xref_ops(d):
    x = d.get_new_xref()
    d.update_object(x, "<</Type/Foo/Bar 1>>")
    d.xref_set_key(d.page_xref(0), "KZTest", "%d 0 R" % x)
    c = d[0].get_contents()[0]
    d.update_stream(c, d.xref_stream(c) + b"\n0 0 1 rg 10 10 50 50 re f\n")


def _widget_value(d):
    for w in d[1].widgets():
        w.field_value = "changed"
        w.update()


def _delete_link(d):
    p = d[2]
    p.delete_link(p.get_links()[0])


def _show_page(d):
    src = pymupdf.open()
    src.new_page().insert_text((72, 100), "Shown")
    d[3].show_pdf_page(pymupdf.Rect(0, 0, 300, 400), src, 0)


def _insert_pdf(d):
    src = pymupdf.open()
    for i in range(2):
        src.new_page().insert_text((72, 100), "Inserted %d" % i)
    d.insert_pdf(src, start_at=1)


PYMUPDF_EDITS = [
    ("add markup", lambda d: d[0].add_rect_annot((10, 10, 50, 50))),
    ("change markup", _change_markup),
    ("delete markup", lambda d: d[0].delete_annot(d[0].first_annot)),
    ("text box", _freetext),
    ("rotate page", lambda d: d[1].set_rotation(90)),
    ("crop page", lambda d: d[1].set_cropbox(pymupdf.Rect(50, 50, 400, 600))),
    ("delete pages", lambda d: d.delete_pages([1, 3])),
    ("move page", lambda d: d.move_page(3, 0)),
    ("copy page", lambda d: d.copy_page(1, 3)),
    ("new page", lambda d: d.new_page(2, width=300, height=300)),
    ("insert pdf", _insert_pdf),
    ("bookmarks", lambda d: d.set_toc([[1, "X", 2]])),
    ("no bookmarks", lambda d: d.set_toc([])),
    ("metadata", lambda d: d.set_metadata({"title": "New", "author": "x"})),
    ("no metadata", lambda d: d.set_metadata({})),
    ("attach", lambda d: d.embfile_add("b.bin", b"\x00\x01data")),
    ("remove attachment", lambda d: d.embfile_del("note.txt")),
    ("form value", _widget_value),
    ("embedded font", _font_text),
    ("picture", lambda d: d[3].insert_image((50, 50, 250, 200), stream=png())),
    ("redaction", _redact),
    ("xref and stream", _xref_ops),
    ("delete link", _delete_link),
    ("page shown on a page", _show_page),
    ("scrub", lambda d: d.scrub(metadata=True, xml_metadata=True, embedded_files=True,
                                attached_files=True, clean_pages=True, javascript=True,
                                redactions=False, remove_links=False, reset_fields=False)),
    ("flatten", lambda d: d.bake()),
]


class Journal(Quiet):
    def test_this_pymupdf_can_undo_through_the_journal(self):
        self.assertTrue(UJ.usable())

    def doc(self):
        path = self.path("src.pdf")
        if not os.path.exists(path):
            sample(path)
        return pymupdf.open(path)

    def test_each_pymupdf_edit_comes_back_exactly(self):
        for label, edit in PYMUPDF_EDITS:
            with self.subTest(label):
                d = self.doc()
                j = UJ.Journal(d)
                look(d)
                before, t0 = canon(d), j.trailer()
                j.begin()
                edit(d)
                names = j.end()
                t1 = j.trailer()
                look(d)
                after = canon(d)
                self.assertNotEqual(before, after)
                for _ in range(2):
                    self.assertTrue(j.undo(names))
                    j.set_trailer(t0, whole=True)
                    look(d)
                    self.assertEqual(canon(d), before)
                    self.assertTrue(j.redo(names))
                    j.set_trailer(t1, whole=True)
                    look(d)
                    self.assertEqual(canon(d), after)
                d.close()

    def test_saving_between_undo_and_redo(self):
        # a save marks the document as saved: the journal's undo of what changed before
        # did nothing afterwards (and deleted objects came back broken after a redo)
        for where in ("op", "undo", "redo", "op undo redo"):
            with self.subTest(where):
                d = self.doc()
                j = UJ.Journal(d)
                before = canon(d)
                j.begin()
                d.set_toc([[1, "X", 2]])
                d[0].add_rect_annot((10, 10, 50, 50))
                names = j.end()
                after = canon(d)
                if "op" in where:
                    d.tobytes(garbage=1)
                for _ in range(2):
                    self.assertTrue(j.undo(names))
                    if "undo" in where:
                        d.save(io.BytesIO(), garbage=1, deflate=True)
                    self.assertEqual(canon(d), before)
                    self.assertTrue(j.redo(names))
                    if "redo" in where:
                        d.tobytes()
                    self.assertEqual(canon(d), after)

    def test_the_journal_is_not_written_into_the_file(self):
        d = self.doc()
        j = UJ.Journal(d)
        j.begin()
        d[0].add_rect_annot((10, 10, 50, 50))
        names = j.end()
        data = d.tobytes(garbage=1)
        for mark in (b"MuPDF-Journal", b"KZJournal", names[0].encode()):
            self.assertNotIn(mark, data)

    def test_the_same_picture_or_text_box_added_again_after_an_undo(self):
        # MuPDF hands back the object it made for the same picture or font: gone after
        # the undo, so the picture went missing and the text box showed no text
        for label, edit in (("picture", lambda d: d[0].insert_image((300, 300, 400, 380),
                                                                      stream=png(9, 9))),
                            ("text box", _freetext), ("font", _font_text)):
            with self.subTest(label):
                d = self.doc()
                j = UJ.Journal(d)
                j.begin()
                edit(d)
                j.undo(j.end())
                j.begin()
                edit(d)
                j.end()
                back = pymupdf.open("pdf", d.tobytes(garbage=1))
                for x in range(1, back.xref_length()):
                    for k, (kind, val) in ((k, back.xref_get_key(x, k))
                                           for k in back.xref_get_keys(x)):
                        for ref in re.findall(r"(\d+) 0 R", val):
                            self.assertNotEqual(back.xref_object(int(ref)).strip(), "null",
                                                (x, k, val))
                text = "".join(p.get_text() for p in back)
                if label != "picture":
                    self.assertIn("text" if label == "font" else "Hello box", text)

    def test_a_change_outside_an_edit_still_works(self):
        d = self.doc()
        UJ.Journal(d)
        d.move_page(1, 3)                       # (MuPDF refuses changes outside one)
        d.get_new_xref()
        self.assertEqual(d.page_count, 4)

    def test_protected_file(self):
        d = self.doc()
        out = io.BytesIO()
        d.save(out, encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="owner",
               user_pw="user", permissions=pymupdf.PDF_PERM_PRINT)
        d = pymupdf.open("pdf", out.getvalue())
        d.authenticate("owner")
        j = UJ.Journal(d)
        before = canon(d)
        c = d[1].get_contents()[0]
        names = []
        for k in range(2):                      # (the same stream changed twice)
            j.begin()
            d.update_stream(c, d.xref_stream(c) + b"\n0 1 0 rg %d 30 50 50 re f\n" % k)
            d[1].add_rect_annot((200 + k, 200, 260, 260))
            names.append(j.end())
        after = canon(d)
        for n in reversed(names):
            j.undo(n)
        self.assertEqual(canon(d), before)
        out = io.BytesIO()
        d.save(out, garbage=1, deflate=True, encryption=pymupdf.PDF_ENCRYPT_KEEP)
        saved = pymupdf.open("pdf", out.getvalue())
        self.assertTrue(saved.needs_pass)
        self.assertTrue(saved.authenticate("user"))
        for n in names:
            j.redo(n)
        self.assertEqual(canon(d), after)


# ---- the app: every kind of edit, against a copy per edit --------------------------------
def rect_markup(v, page=0, dx=0):
    v._create(page, {"kind": "rect", "props": dict(A.DEFAULTS["rect"]),
                     "rect": pymupdf.Rect(60 + dx, 60, 160 + dx, 120)})


def _text_box(v):
    v._create(1, {"kind": "textbox", "props": dict(A.DEFAULTS["textbox"]),
                  "rect": pymupdf.Rect(60, 600, 260, 660), "text": "Hello box"})


def _move_markup(v):
    pg = v.doc[0]
    x = [a.xref for a in pg.annots()][0]
    model = A.read(pg.load_annot(x))
    del pg
    v.commit_models(0, [(x, A.moved(model, P(15, 25)))], olds={x: model})


def _nudges(v):
    pg = v.doc[0]
    x = [a.xref for a in pg.annots()][0]
    del pg
    v.select_xref(0, x)
    for _ in range(3):
        v.nudge(1, 0, 1)


def _field_value(v):
    pg = v.doc[1]
    x = next(pg.widgets()).xref
    del pg
    v._set_field(1, x, "Jane Doe")


def _redact(v, scrub=False):
    v.mark_redactions(0, [pymupdf.Rect(70, 55, 200, 80)])
    v.apply_redactions(scrub=scrub)


def _objects(v):
    v.select_objects(0, [it for it in v.content_objects(0).items if it["kind"] == "shape"])
    v.move_objects(v.selected_objects_rect() + (30, 40, 30, 40))


def _insert_file(v, tmp):
    d = pymupdf.open()
    for i in range(2):
        d.new_page().insert_text((72, 72), "Inserted %d" % i)
    path = os.path.join(tmp, "other.pdf")
    d.save(path)
    v.insert_files([path], 2)


APP_EDITS = [
    ("markup", rect_markup),
    ("text box", _text_box),
    ("move markup", _move_markup),
    ("arrow-key nudges", _nudges),
    ("delete markups", lambda v: v.delete_markups()),
    ("rotate page", lambda v: v.rotate_page(1, 90)),
    ("delete page", lambda v: v.delete_page(2)),
    ("move page", lambda v: v.move_page(0, 2)),
    ("reorder pages", lambda v: v.reorder_pages([3, 1, 2, 0])),
    ("insert blank page", lambda v: v.insert_blank(1)),
    ("insert file", None),
    ("crop", lambda v: v.crop_pages(0, pymupdf.Rect(20, 30, 500, 700))),
    ("crop all", lambda v: v.crop_pages(0, pymupdf.Rect(20, 30, 500, 700), all_pages=True)),
    ("flatten", lambda v: v.flatten()),
    ("bookmarks", lambda v: v.set_toc([[1, "Only", 2], [2, "Sub", 3]])),
    ("watermark", lambda v: v.add_watermark({"text": "DRAFT", "pages": [0, 1]})),
    ("header", lambda v: v.add_header_footer(
        {"texts": {("header", "center"): "Page <<n>> of <<total>>"}, "pages": [0, 1, 2, 3]})),
    ("form field value", _field_value),
    ("new form field", lambda v: v.create_field(0, "f_text", P(72, 650), P(250, 672), False)),
    ("replace text", lambda v: v.replace_text("Contractor", "Supplier")),
    ("redact", _redact),
    ("redact and clean", lambda v: _redact(v, True)),
    ("erase", lambda v: v.erase_content(0, pymupdf.Rect(90, 190, 310, 310))),
    ("link", lambda v: v.add_link(0, pymupdf.Rect(70, 60, 200, 80), ("page", 2, "box"))),
    ("move drawing", _objects),
    ("sanitize", lambda v: v.sanitize({"metadata": True, "javascript": True,
                                       "embedded_files": True, "thumbnails": True})),
    ("remove attachment", lambda v: v.delete_attachment(None, "note.txt")),
]


class SameAsCopies(Quiet):
    def run_sequence(self, v, edit):
        states = [canon(v.doc)]
        steps = len(v._undo)
        edit(v)
        steps = len(v._undo) - steps            # (mark and apply redactions: two)
        states.append(canon(v.doc))
        for way in ("undo", "redo", "undo"):
            for _ in range(steps):
                getattr(v, way)()
            states.append(canon(v.doc))
            self.assertEqual(len(v.pages), v.doc.page_count)
        rect_markup(v, 3, 30)                   # (a new edit: nothing to redo after it)
        states.append(canon(v.doc))
        states.append(v.can_redo())
        v.undo()
        states.append(canon(v.doc))
        v.redo()
        states.append(canon(v.doc))
        return states

    def test_every_edit_matches_the_copy_per_edit(self):
        for label, edit in APP_EDITS:
            if edit is None:
                def edit(v):
                    return _insert_file(v, self.tmp.name)
            with self.subTest(label):
                runs = []
                for journal in (True, False):
                    v = self.view(journal)
                    runs.append(self.run_sequence(v, edit))
                    kept = [type(s).__name__ for s in v._undo]
                    if journal:
                        self.assertNotIn("bytes", kept)     # (no copy of the document)
                    else:
                        self.assertEqual(set(kept), {"bytes"})
                    v.dirty = False
                    v.close_doc()
                j, c = runs
                self.assertEqual(len(j), len(c))
                for k, (a, b) in enumerate(zip(j, c)):
                    self.assertEqual(a, b, "state %d" % k)
                self.assertEqual(j[0], j[2])            # (back to the start after undo)
                self.assertEqual(j[1], j[3])
                self.assertNotEqual(j[0], j[1])


# ---- the undo history ------------------------------------------------------------------
class History(Quiet):
    def test_arrow_key_nudges_are_one_step(self):
        v = self.view()
        start = canon(v.doc)
        steps = len(v._undo)
        _nudges(v)
        self.assertEqual(len(v._undo), steps + 1)
        self.assertEqual(len(v._undo[-1].names), 3)    # (three journal entries, one step)
        v.undo()
        self.assertEqual(canon(v.doc), start)

    def test_a_failed_edit_leaves_the_document_as_it_was(self):
        v = self.view()
        rect_markup(v)
        before, doc, steps = canon(v.doc), v.doc, list(v._undo)

        def half_done():
            v.doc[1].add_rect_annot((10, 10, 80, 80))
            v.doc.delete_page(3)
            raise ValueError("halfway")
        self.assertFalse(v.modify(half_done, structural=True))
        self.assertIs(v.doc, doc)               # (taken back in place, not reopened)
        self.assertEqual(canon(v.doc), before)
        self.assertEqual(v._undo, steps)
        self.assertEqual(len(v.pages), 4)
        v.undo()
        self.assertEqual(len(list(v.doc[0].annots())), 1)

    def test_a_big_edit_is_cut_into_entries_and_undone_as_one(self):
        # (kept as one entry, 1,000 markups added in one edit took 15 s instead of 0.6)
        v = self.view()
        start = canon(v.doc)

        def many():
            page = v.doc[0]
            for i in range(600):
                x, y = 30 + (i % 30) * 18, 30 + (i // 30) * 30
                page.add_rect_annot(pymupdf.Rect(x, y, x + 12, y + 20))
        t = time.perf_counter()
        v.modify(many, [0])
        took = time.perf_counter() - t
        self.assertGreater(len(v._undo[-1].names), 10)
        self.assertLess(took, 5.0)
        self.assertEqual(len(list(v.doc[0].annots())), 601)
        v.undo()
        self.assertEqual(canon(v.doc), start)
        v.redo()
        self.assertEqual(len(list(v.doc[0].annots())), 601)

        def fails():
            many()
            raise ValueError("after 600 markups")
        v.modify(fails, [0])                    # (several entries made, then taken back)
        self.assertEqual(len(list(v.doc[0].annots())), 601)
        v.undo()
        self.assertEqual(canon(v.doc), start)

    def test_an_edit_made_during_another_is_part_of_it(self):
        v = self.view()
        start = canon(v.doc)

        def outer():
            v.doc[0].add_rect_annot((10, 10, 40, 40))
            v.modify(lambda: v.doc[1].add_rect_annot((10, 10, 40, 40)), [1])
        v.modify(outer, [0])
        self.assertEqual(len(v._undo), 1)
        v.undo()
        self.assertEqual(canon(v.doc), start)

    def test_steps_before_a_cleaned_redaction_can_still_be_undone(self):
        # Apply redactions with cleanup replaces the document: undo goes back to the one
        # before, whose own earlier steps are still there
        v = self.view()
        start = canon(v.doc)
        rect_markup(v)
        one = canon(v.doc)
        _redact(v, True)                        # (two steps: marked, applied)
        redacted = canon(v.doc)
        self.assertNotIn("Contractor", v.doc[0].get_text())
        v.undo()
        v.undo()
        self.assertEqual(canon(v.doc), one)
        self.assertIn("Contractor", v.doc[0].get_text())
        v.undo()
        self.assertEqual(canon(v.doc), start)
        for _ in range(3):
            v.redo()
        self.assertEqual(canon(v.doc), redacted)
        rect_markup(v, 1)                       # (an edit on the new document)
        v.undo()
        self.assertEqual(canon(v.doc), redacted)

    def test_save_after_undo_writes_the_undone_document(self):
        v = self.view()
        start = canon(v.doc)
        rect_markup(v)
        v.delete_page(1)
        v.undo()
        v.undo()
        v.save()
        self.assertEqual(canon(pymupdf.open(v.path)), start)
        v.redo()
        v.save()
        with pymupdf.open(v.path) as saved:
            self.assertEqual(len(list(saved[0].annots())), 2)
        v.redo()
        self.assertEqual(v.doc.page_count, 3)
        v.undo()
        v.undo()
        self.assertEqual(canon(v.doc), start)

    def test_a_save_with_steps_to_redo_keeps_them(self):
        # Save cuts embedded fonts down and packs drawings: done in the document, it
        # would have dropped the steps to redo
        v = self.view()
        rect_markup(v)
        # (something the save really changes: a stream written quickly, to be packed)
        from kanzonas import page_objects
        page = v.doc[0]
        x = page.get_contents()[0]
        page_objects._put_stream(v.doc, x, v.doc.xref_stream(x))
        del page
        rect_markup(v, 1)
        v._fonts_added = True                   # (as after a text edit)
        v.undo()
        v.save()
        with pymupdf.open(v.path) as saved:     # (packed in the file, not in the document)
            self.assertEqual(saved.xref_get_key(x, page_objects.QUICK_KEY)[0], "null")
        self.assertEqual(v.doc.xref_get_key(x, page_objects.QUICK_KEY)[1], "true")
        self.assertTrue(v.can_redo())
        v.redo()
        self.assertEqual(len(list(v.doc[1].annots())), 2)
        with pymupdf.open(v.path) as saved:
            self.assertEqual(len(list(saved[1].annots())), 1)

    def test_a_file_with_an_attachment_still_opens_its_attachments_list(self):
        # (PyMuPDF sets /PageMode /UseAttachments before a save; with a journal the save
        # leaves that to DocumentView.save, which must still do it, with or without steps
        # to redo, and without dropping them)
        for redo in (False, True):
            v = self.view()
            rect_markup(v)
            rect_markup(v, 1)
            if redo:
                v.undo()
            v.save()
            with pymupdf.open(v.path) as saved:
                self.assertEqual(saved.pdf_catalog() and saved.xref_get_key(
                    saved.pdf_catalog(), "PageMode"), ("name", "/UseAttachments"))
            self.assertEqual(v.can_redo(), redo)
            if redo:                            # (and the redo really works)
                v.redo()
                self.assertEqual(len(list(v.doc[1].annots())), 2)
                self.assertFalse(v.can_redo())

    def test_undo_back_to_the_saved_file_is_still_unsaved(self):
        # (as with copies: any undo leaves the document marked as changed)
        v = self.view()
        rect_markup(v)
        v.save()
        self.assertFalse(v.dirty)
        rev = v.revision
        v.undo()
        self.assertTrue(v.dirty)
        self.assertGreater(v.revision, rev)

    def test_steps_whose_entries_are_gone_are_dropped(self):
        v = self.view()
        rect_markup(v)
        rect_markup(v, 1)
        v._journal.discard()                    # (behind the view's back)
        v.undo()
        self.assertFalse(v.can_undo())
        self.assertEqual(len(list(v.doc[1].annots())), 2)   # (nothing undone wrongly)
        rect_markup(v, 2)                       # (and editing goes on)
        v.undo()
        self.assertEqual(len(list(v.doc[2].annots())), 1)

    def test_a_save_that_renumbers_objects_ends_the_journal(self):
        v = self.view()
        rect_markup(v)
        v.doc.tobytes(garbage=3)                # (renumbers the document's own objects)
        v.undo()                                # (refused: the entries no longer match)
        self.assertEqual(len(list(v.doc[0].annots())), 2)
        rect_markup(v, 1)
        v.undo()
        self.assertEqual(len(list(v.doc[1].annots())), 1)

    def test_a_page_held_through_a_move_doesnt_reopen_the_document(self):
        v = self.view()
        doc = v.doc
        held = v.doc[2]._pdf_page()
        v.move_page(0, 2)
        self.assertIs(v.doc, doc)
        self.assertFalse(v._stale_pages())
        texts = [v.doc[i].get_text().split()[1] for i in range(4)]
        self.assertEqual(texts, ["2", "3", "1", "4"])
        v.undo()
        self.assertEqual([v.doc[i].get_text().split()[1] for i in range(4)],
                         ["1", "2", "3", "4"])
        del held

    def test_memory_budget(self):
        # the journal can only be emptied as a whole: over the budget, the latest step
        # becomes a copy of the document and the rest goes
        v = self.view()
        for k in range(4):
            rect_markup(v, k % 4, k)
        self.assertEqual(len(v._undo), 4)
        with mock.patch.object(DV, "UNDO_BYTES_PER_DOC", 1):
            v._trim_history()
        self.assertEqual(len(v._undo), 1)
        self.assertIsInstance(v._undo[0], bytes)
        self.assertEqual(v._journal.entries(), 0)
        v.undo()
        self.assertEqual([len(list(p.annots())) for p in v.doc], [2, 2, 2, 1])
        v.redo()
        self.assertEqual([len(list(p.annots())) for p in v.doc], [2, 2, 2, 2])

    def test_an_edit_doesnt_copy_the_document(self):
        path = self.path("big.pdf")
        d = pymupdf.open()
        for i in range(3):
            d.new_page().insert_text((72, 72), "page %d" % i)
        d.embfile_add("blob", os.urandom(24 * 2**20))
        d.save(path)
        v = DocumentView(path)
        self.addCleanup(v.close_doc)
        t = time.perf_counter()
        for k in range(5):
            rect_markup(v, 0, 5 * k)
        edits = time.perf_counter() - t
        self.assertLess(v.history_bytes(), 2**20)          # (a copy is 24 MB)
        t = time.perf_counter()
        v.undo()
        v.redo()
        self.assertLess(time.perf_counter() - t, 1.0)
        self.assertLess(edits, 2.5)
        v.dirty = False


if __name__ == "__main__":
    unittest.main()
