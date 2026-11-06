"""What the 1.9 break-it battery found in redaction and Sanitize, fixed: what was redacted
stayed readable in the saved file in places Apply redactions didn't reach:

- Search & redact's term in a layer's name, a bookmark's web address, a form field on no
  page (or a list field's options), a note's rich text (/RC) when its plain text was
  different, and (without the clean-up) a program's own document information key;
- the words under any mark in the marked-content wrapper MuPDF leaves around them
  ("/Span <</ActualText (the words)>> BDC EMC"), without the clean-up and with Apply
  selected redactions (which never cleans up);
- the page as it was before: its thumbnail (without the clean-up, Apply selected
  redactions) and a program's private copy of it (/PieceInfo: Illustrator's whole drawing),
  also with the clean-up and after Sanitize.

Each test reads the saved file's every object and stream, uncompressed, for the words.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_battery_19_redact
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas.document_view import DocumentView  # noqa: E402

WORD = "TOPSECRET"


def _all_bytes(path):
    """The file's every object and stream, uncompressed."""
    with pymupdf.open(path) as d:
        return d.tobytes(expand=255)


class Case(unittest.TestCase):
    def path(self, name):
        if not hasattr(self, "_dir"):
            self._dir = tempfile.mkdtemp()
        return os.path.join(self._dir, name)

    def doc(self):
        """A page showing the word (so Search & redact finds it), saved later by the test."""
        d = pymupdf.open()
        p = d.new_page(width=500, height=700)
        p.insert_text((50, 50), "Plain %s word" % WORD, fontsize=12)
        p.insert_text((50, 100), "Other words stay", fontsize=12)
        return d, p

    def view(self, d):
        path = self.path("in%d.pdf" % len(os.listdir(self.path(""))))
        d.save(path)
        d.close()
        v = DocumentView(path)
        self.addCleanup(lambda: (setattr(v, "dirty", False), v.close_doc()))
        return v

    def saved(self, v):
        out = self.path("out%d.pdf" % len(os.listdir(self.path(""))))
        v.save(out)
        return _all_bytes(out)

    def redact_word(self, d, scrub=True):
        v = self.view(d)
        self.assertGreater(v.search_redact(WORD), 0)
        v.apply_redactions(scrub)
        return v, self.saved(v)


class SearchAndRedact(Case):
    def test_a_layer_named_with_the_term(self):
        for scrub in (True, False):
            with self.subTest(scrub=scrub):
                d, _p = self.doc()
                d.add_ocg("The %s layer" % WORD, on=True)
                v, data = self.redact_word(d, scrub)
                self.assertNotIn(WORD.encode(), data)
                self.assertEqual([c["text"] for c in v.doc.layer_ui_configs()],
                                 ["The [redacted] layer"])

    def test_a_bookmark_to_a_web_address_with_the_term(self):
        d, _p = self.doc()
        d.set_toc([[1, "Chapter one", 1],
                   [1, "On the web", 1, {"kind": pymupdf.LINK_URI,
                                         "uri": "https://example.com/%s/page" % WORD}]])
        v, data = self.redact_word(d)
        self.assertNotIn(WORD.encode(), data)
        self.assertEqual([e[1] for e in v.doc.get_toc()], ["Chapter one", "On the web"])

    def test_a_form_field_on_no_page(self):
        # (a field the form lists but no page shows: its value and options stayed)
        d, _p = self.doc()
        text, choice = d.get_new_xref(), d.get_new_xref()
        d.update_object(text, "<</T(hidden)/FT/Tx/V(Name: %s)/DV(%s)>>" % (WORD, WORD))
        d.update_object(choice, "<</T(list)/FT/Ch/V[(%s)]/Opt[[(a)(%s one)](plain)]>>" % (
            WORD, WORD))
        d.xref_set_key(d.pdf_catalog(), "AcroForm", "<</Fields[%d 0 R %d 0 R]>>" % (text, choice))
        _v, data = self.redact_word(d)
        self.assertNotIn(WORD.encode(), data)
        self.assertIn(b"plain", data)

    def test_a_note_whose_rich_text_holds_the_term(self):
        # (its plain text didn't: another program changed one and not the other)
        d, p = self.doc()
        a = p.add_text_annot((300, 400), "a harmless note")
        a.update()
        d.xref_set_key(a.xref, "RC", pymupdf.get_pdf_str("<body><p>about %s</p></body>" % WORD))
        for scrub in (True, False):
            with self.subTest(scrub=scrub):
                dd = pymupdf.open("pdf", d.tobytes())
                v, data = self.redact_word(dd, scrub)
                self.assertNotIn(WORD.encode(), data)
                notes = [x for x in v.doc[0].annots() if x.type[0] == pymupdf.PDF_ANNOT_TEXT]
                self.assertEqual([x.info["content"] for x in notes], ["a harmless note"])

    def test_document_information_of_its_own_without_the_clean_up(self):
        # (a key of the program that made the file: only the standard ones were cleaned)
        d, _p = self.doc()
        d.set_metadata({"title": "Report on %s" % WORD})
        info = int(d.xref_get_key(-1, "Info")[1].split()[0])
        d.xref_set_key(info, "Company", "(%s Inc.)" % WORD)
        v, data = self.redact_word(d, scrub=False)
        self.assertNotIn(WORD.encode(), data)
        self.assertEqual(v.doc.metadata["title"], "Report on [redacted]")
        self.assertIn(b"[redacted] Inc.", data)


def _with_actual_text(d, p, words, y=300):
    """Add words to p's drawing inside a marked-content span carrying them as ActualText
    (as tagged PDFs do); returns where they show."""
    font = p.get_fonts()[0][4]
    x = d.get_new_xref()
    d.update_object(x, "<<>>")
    d.update_stream(x, b"/Span <</ActualText (%s)>> BDC BT /%s 12 Tf 50 %d Td (%s) Tj ET EMC" % (
        words.encode(), font.encode(), y, words.encode()))
    d.xref_set_key(p.xref, "Contents", "[%s %d 0 R]" % (
        " ".join("%d 0 R" % c for c in p.get_contents()), x))
    return p.search_for(words)[0]


class PageAsItWas(Case):
    def test_actual_text_of_the_words_under_a_mark(self):
        # MuPDF's redaction takes the words away and leaves their wrapper, ActualText and
        # all: without the clean-up (and with Apply selected redactions, which never cleans
        # up) the words stayed in the file
        for how in ("apply", "selected"):
            with self.subTest(how=how):
                d, p = self.doc()
                where = _with_actual_text(d, p, "HIDDENWORDS")
                v = self.view(d)
                v.mark_redactions(0, [where + (-2, -2, 2, 2)])
                if how == "apply":
                    v.apply_redactions(False)
                else:
                    v._set_selection(0, [a.xref for a in v.doc[0].annots()])
                    self.assertEqual(v.apply_selected_redactions(), 1)
                data = self.saved(v)
                self.assertNotIn(b"HIDDENWORDS", data)
                self.assertIn("Other words stay", v.doc[0].get_text())

    def test_the_thumbnail_of_a_redacted_page(self):
        # (a picture of the page as it was, words and all)
        for how in ("apply", "selected"):
            with self.subTest(how=how):
                d, p = self.doc()
                thumb = d.get_new_xref()
                d.update_object(thumb, "<</Width 1/Height 1/ColorSpace/DeviceGray"
                                       "/BitsPerComponent 8>>")
                d.update_stream(thumb, b"THUMBPIXELS")
                d.xref_set_key(p.xref, "Thumb", "%d 0 R" % thumb)
                v = self.view(d)
                v.mark_redactions(0, [pymupdf.Rect(40, 30, 200, 60)])
                if how == "apply":
                    v.apply_redactions(False)
                else:
                    v._set_selection(0, [a.xref for a in v.doc[0].annots()])
                    v.apply_selected_redactions()
                self.assertNotIn(b"THUMBPIXELS", self.saved(v))

    def piece_info(self, d, p):
        priv = d.get_new_xref()
        d.update_object(priv, "<<>>")
        d.update_stream(priv, b"%AI private: the drawing as it was, Plain " + WORD.encode())
        d.xref_set_key(p.xref, "PieceInfo", "<</Illustrator<</LastModified(D:2026)"
                                            "/Private<</AIPrivateData1 %d 0 R>>>>>>" % priv)

    def test_a_programs_private_copy_of_the_page(self):
        # Illustrator keeps its whole drawing in the page's /PieceInfo: what was redacted
        # from the page stayed there, with or without the clean-up
        for scrub in (True, False):
            with self.subTest(scrub=scrub):
                d, p = self.doc()
                self.piece_info(d, p)
                v = self.view(d)
                v.mark_redactions(0, [pymupdf.Rect(40, 30, 200, 60)])
                v.apply_redactions(scrub)
                data = self.saved(v)
                self.assertNotIn(b"AIPrivateData", data)
                self.assertNotIn(WORD.encode(), data)

    def test_sanitize_removes_private_data(self):
        d, p = self.doc()
        self.piece_info(d, p)
        v = self.view(d)
        v.sanitize({"metadata": True})
        self.assertNotIn(b"AIPrivateData", self.saved(v))
        self.assertIn("Plain %s word" % WORD, v.doc[0].get_text())


if __name__ == "__main__":
    unittest.main()
