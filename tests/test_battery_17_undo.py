"""Break-it tests for undo and redo through MuPDF's journal (1.7): sequences through the
app's own steps that went wrong once, each checked against what a copy per edit (up to
1.6) gives.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_battery_17_undo
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402

from tests.test_undo_journal import Quiet, canon, rect_markup, sample  # noqa: E402


def annots(doc):
    return [len(list(p.annots())) for p in doc]


def damaged(path, src):
    """A PDF whose table of objects points the contents of page 4 at another object: MuPDF
    repairs the file only when it first reads that object."""
    sample(src)
    with pymupdf.open(src) as d:
        data = d.tobytes(garbage=3, use_objstms=0, expand=255)
    with pymupdf.open("pdf", data) as d:
        target = d[3].get_contents()[0]
    i = data.rindex(b"\nxref\n")
    lines = data[i + 1:].split(b"\n")
    lines[2 + target] = lines[2 + 1]            # ("xref", "0 n", then one line per object)
    with open(path, "wb") as f:
        f.write(data[:i + 1] + b"\n".join(lines))
    return path


class Battery(Quiet):
    def test_a_file_repaired_after_an_edit_keeps_the_edit(self):
        # MuPDF rebuilds the table of objects of a damaged file when it first reads the
        # broken object, and every change made before is lost: a markup added, then the
        # damaged page looked at (or the file saved) dropped the markup, also from the file
        src = damaged(self.path("damaged.pdf"), self.path("sample.pdf"))
        for journal in (True, False):
            with self.subTest(journal=journal):
                v = self.view(journal, name="d%d.pdf" % journal)
                with open(src, "rb") as f, open(v.path, "wb") as g:
                    g.write(f.read())
                v.close_doc()
                from kanzonas.document_view import DocumentView
                v = DocumentView(v.path)
                self.addCleanup(lambda v=v: v.doc.is_closed or v.close_doc())
                self.assertFalse(v.doc.is_repaired)
                rect_markup(v, 0)
                v.doc[3].get_pixmap(dpi=20)            # (reads the broken object)
                self.assertEqual(annots(v.doc), [2, 1, 1, 1])
                rect_markup(v, 1)
                v.save()
                with pymupdf.open(v.path) as saved:
                    self.assertEqual(annots(saved), [2, 2, 1, 1])
                v.undo()
                v.undo()
                self.assertEqual(annots(v.doc), [1, 1, 1, 1])
                v.redo()
                self.assertEqual(annots(v.doc), [2, 1, 1, 1])
                v.dirty = False

    def test_redact_and_sanitize_after_an_undo(self):
        # an undo leaves the numbers of the objects the edit had made with no entry at
        # all, and PyMuPDF's scrub reads every object: Apply redactions (it cleans the file
        # too) and Sanitize failed with "cannot find object in xref" after any undo, and
        # the text wasn't redacted
        from kanzonas import undo_journal
        from unittest import mock
        warned = []

        def redact(v):
            v.mark_redactions(0, [pymupdf.Rect(70, 55, 200, 80)])
            v.apply_redactions()

        def sanitize(v):
            v.sanitize({"metadata": True, "javascript": True, "embedded_files": True,
                        "thumbnails": True})
        for label, edit in (("redact", redact), ("sanitize", sanitize)):
            runs = []
            for journal in (True, False):
                with self.subTest(label, journal=journal), \
                        mock.patch("PySide6.QtWidgets.QMessageBox.warning",
                                   lambda *a, **k: warned.append(a[2])):
                    v = self.view(journal)
                    start = canon(v.doc)
                    rect_markup(v, 0)
                    v.undo()
                    steps = len(v._undo)
                    edit(v)
                    self.assertEqual(warned, [])
                    self.assertGreater(len(v._undo), steps)
                    if label == "redact":
                        self.assertNotIn("Contractor", v.doc[0].get_text())
                    done = canon(v.doc)
                    while len(v._undo) > steps:
                        v.undo()
                    self.assertEqual(canon(v.doc), start)
                    runs.append(done)
                    v.dirty = False
                    v.close_doc()
            self.assertEqual(runs[0], runs[1], label)
        # (only an object an undo took back reads as deleted: a number past the end still
        # raises)
        v = self.view()
        rect_markup(v, 0)
        with self.assertRaises(Exception):
            v.doc.xref_object(v.doc.xref_length() + 5)
        self.assertTrue(undo_journal._installed)
        v.dirty = False

    def test_copying_pages_between_undo_and_redo(self):
        # Copy pages, Extract pages and the Capture tool copy pages out with PyMuPDF's
        # insert_pdf, which takes /P out of the copied markups in the document itself:
        # MuPDF then dropped its entries to redo, and Redo did nothing
        from kanzonas import capture
        actions = {
            "copy pages": lambda v: v.pages_bytes([0, 1, 2]),
            "extract pages": lambda v: v.extract_pages(0, 2, self.path("out.pdf")),
            "capture": lambda v: capture.snapshot(v.doc[2], pymupdf.Rect(50, 50, 400, 400)),
        }
        for label, act in actions.items():
            with self.subTest(label):
                v = self.view()
                rect_markup(v, 0)
                rect_markup(v, 2)
                done = canon(v.doc)
                v.undo()
                act(v)
                self.assertTrue(v.can_redo())
                v.redo()
                self.assertEqual(canon(v.doc), done)
                self.assertEqual(annots(v.doc), [2, 1, 2, 1])
                v.dirty = False
                v.close_doc()
        if os.path.exists(self.path("out.pdf")):
            with pymupdf.open(self.path("out.pdf")) as out:
                self.assertEqual(annots(out), [2, 1, 1])     # (the copy has the markups)

    def test_a_field_shown_on_two_pages(self):
        # one field with a widget on page 1 and another on page 3: a value typed on page 1
        # shows on both, but only page 1 was drawn again (also after an undo or redo through
        # the journal, where a copy per edit drew every page again)
        path = self.path("twin.pdf")
        d = pymupdf.open()
        for i in range(3):
            d.new_page().insert_text((72, 72), "Page %d" % (i + 1))
        parent = d.get_new_xref()
        d.update_object(parent, "<</FT/Tx/T(who)/V(start)/DA(0 g /Helv 11 Tf)>>")
        kids = []
        for i, y in ((0, 100), (2, 200)):
            x = d.get_new_xref()
            d.update_object(x, "<</Type/Annot/Subtype/Widget/Rect[72 %d 300 %d]/Parent %d 0 R"
                               "/P %d 0 R/F 4>>" % (y, y + 25, parent, d.page_xref(i)))
            d.xref_set_key(d.page_xref(i), "Annots", "[%d 0 R]" % x)
            kids.append(x)
        d.xref_set_key(parent, "Kids", "[%d 0 R %d 0 R]" % tuple(kids))
        d.xref_set_key(d.pdf_catalog(), "AcroForm", "<</Fields[%d 0 R]/DA(0 g /Helv 11 Tf)>>"
                       % parent)
        d.save(path)
        d.close()
        for journal in (True, False):
            with self.subTest(journal=journal):
                from kanzonas import document_view as DV
                from kanzonas.document_view import DocumentView
                DV.USE_JOURNAL = journal
                v = DocumentView(path)
                self.addCleanup(lambda v=v: v.doc.is_closed or v.close_doc())
                v.resize(900, 700)
                self.assertEqual(v._field_pages(0, kids[0]), [0, 2])
                for step in ("type", "undo", "redo"):
                    for w in v.pages:
                        w.grab()                # (drawn: each keeps its picture)
                    self.assertIsNotNone(v.pages[2]._pix)
                    if step == "type":
                        v._set_field(0, kids[0], "Jane Doe")
                    else:
                        getattr(v, step)()
                    self.assertIsNone(v.pages[2]._pix, step)    # (drawn again)
                    if journal or step == "type":   # (a copy brings back every page)
                        self.assertIsNotNone(v.pages[1]._pix, step)  # (not this one)
                v.dirty = False
                v.close_doc()

    def test_the_authors_of_the_markups(self):
        # (Delete comments lists them: the page went before its markups were read, and
        # it raised "annotation not bound to any page" whenever there was a markup)
        for undo in (False, True):
            v = self.view()
            rect_markup(v, 0)
            rect_markup(v, 2)
            if undo:
                v.undo()
            from kanzonas import annotations
            # (the sample's own markups have no author)
            self.assertEqual(v.markup_authors(), sorted({"", annotations.author()}))
            v.dirty = False
            v.close_doc()

    def test_reading_a_turned_page_between_undo_and_redo(self):
        # PyMuPDF reads a rotated page's text and drawings with the page turned upright for
        # a moment (/Rotate set to 0 and back), and so does Edit text: MuPDF dropped its
        # entries to redo at that change, so on a document with a turned page, Redo did
        # nothing once the page's text was read (Find, hover, Edit text, Edit objects...)
        reads = {
            "text": lambda v: v.doc[1].get_text(),
            "words": lambda v: v.doc[1].get_text("words"),
            "search": lambda v: v.doc[1].search_for("Contractor"),
            "drawings": lambda v: v.doc[1].get_drawings(),
            "texttrace": lambda v: v.doc[1].get_texttrace(),
            "bboxlog": lambda v: v.doc[1].get_bboxlog(),
            "edit text lines": lambda v: v._lines(1),
            "objects": lambda v: (v.content_objects(1), v.text_objects(1)),
        }
        for label, read in reads.items():
            with self.subTest(label):
                v = self.view()
                v.rotate_page(1, 90)
                rect_markup(v, 0)
                done = canon(v.doc)
                v.undo()
                v._clear_caches()
                read(v)
                self.assertEqual(v._journal.ahead(), v._redo[-1].names)
                v.redo()
                self.assertEqual(canon(v.doc), done)
                self.assertEqual(v.doc[1].rotation, 90)
                v.undo()
                v.undo()
                self.assertEqual(v.doc[1].rotation, 0)
                v.dirty = False
                v.close_doc()

    def test_a_failed_edit_and_the_steps_to_redo(self):
        # a failed edit takes nothing away from the steps to undo; but MuPDF drops its
        # entries to redo at an edit's first change, and taking the edit back doesn't bring
        # them back: Redo was still offered, and did nothing. (A failed edit that changed
        # nothing keeps them)
        for many in (0, 5, 60):
            with self.subTest(many=many):
                v = self.view()
                states = [canon(v.doc)]
                for k in range(3):
                    rect_markup(v, k)
                    states.append(canon(v.doc))
                v.undo()

                def fails():
                    pg = v.doc[3]
                    for i in range(many):
                        pg.add_rect_annot((10 + i, 10, 30 + i, 30))
                    raise ValueError("halfway")
                self.assertFalse(v.modify(fails, [3]))
                self.assertEqual(canon(v.doc), states[2])
                if not many:
                    v.redo()
                    self.assertEqual(canon(v.doc), states[3])
                    v.undo()
                else:
                    self.assertFalse(v.can_redo())
                for k in (1, 0):
                    v.undo()
                    self.assertEqual(canon(v.doc), states[k])
                v.dirty = False
                v.close_doc()


if __name__ == "__main__":
    unittest.main()
