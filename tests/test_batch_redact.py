"""Batch processing's Search & redact and Apply redactions leak nothing: they go through the
very steps of the single-file commands (DocumentView.search_redact, hidden_matches,
remove_term, apply_redactions), so every hidden place the 1.9 break-it battery found
(tests/test_battery_19_redact.py) is cleaned in a batch too: the term in a hidden layer,
cropped away or past the page's edge, in a layer's name, a bookmark's web address, a form
field on no page (and a list field's options), a note's rich text, a program's own document
information key, an XFA form's data (plain or as character references), the ActualText
wrapper MuPDF leaves around redacted words, the page's thumbnail and a program's private
copy of the page (/PieceInfo). Each saved file is read, every object and stream
uncompressed, for the term. The report says per file what was removed and where (the pages,
the other places); when only marking, that nothing was removed yet, and the file is named
name-marked.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_batch_redact
"""
import hashlib
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import batch as B  # noqa: E402
from tests.test_battery_19_redact import (WORD, _all_bytes, _with_actual_text,  # noqa: E402
                                          xfa_with)


def _page(d=None):
    d = d or pymupdf.open()
    p = d.new_page(width=500, height=700)
    p.insert_text((50, 50), "Plain %s word" % WORD, fontsize=12)
    p.insert_text((50, 100), "Other words stay", fontsize=12)
    return d, p


def hidden_layer():
    d, p = _page()
    oc = d.add_ocg("Draft notes", on=False)
    p.insert_text((50, 300), "Draft: %s again" % WORD, fontsize=12, oc=oc)
    return d


def cropped_away():
    d, p = _page()
    p.insert_text((50, 650), "Cropped %s words" % WORD, fontsize=12)
    p.insert_text((50, 760), "Past the edge %s too" % WORD, fontsize=12)
    p.set_cropbox(pymupdf.Rect(0, 0, 500, 400))
    return d


def layer_name():
    d, _p = _page()
    d.add_ocg("The %s layer" % WORD, on=True)
    return d


def bookmark_address():
    d, _p = _page()
    d.set_toc([[1, "Chapter one", 1],
               [1, "On the web", 1, {"kind": pymupdf.LINK_URI,
                                     "uri": "https://example.com/%s/page" % WORD}]])
    return d


def field_on_no_page():
    d, _p = _page()
    text, choice = d.get_new_xref(), d.get_new_xref()
    d.update_object(text, "<</T(hidden)/FT/Tx/V(Name: %s)/DV(%s)>>" % (WORD, WORD))
    d.update_object(choice, "<</T(list)/FT/Ch/V[(%s)]/Opt[[(a)(%s one)](plain)]>>" % (
        WORD, WORD))
    d.xref_set_key(d.pdf_catalog(), "AcroForm", "<</Fields[%d 0 R %d 0 R]>>" % (text, choice))
    return d


def rich_text_note():
    d, p = _page()
    a = p.add_text_annot((300, 400), "a harmless note")
    a.update()
    d.xref_set_key(a.xref, "RC", pymupdf.get_pdf_str("<body><p>about %s</p></body>" % WORD))
    return d


def own_information_key():
    d, _p = _page()
    d.set_metadata({"title": "Report on %s" % WORD})
    info = int(d.xref_get_key(-1, "Info")[1].split()[0])
    d.xref_set_key(info, "Company", "(%s Inc.)" % WORD)
    return d


def xfa_plain():
    d, _p = _page()
    xfa_with(d, b"<form><name>Mr " + WORD.encode() + b"</name></form>")
    return d


def xfa_references():
    d, _p = _page()
    xfa_with(d, b"<form><name>Mr &#84;OPSECRET</name></form>")
    return d


def actual_text():
    # (the word on the page inside a tagged span carrying it again as ActualText)
    d, p = _page()
    _with_actual_text(d, p, "Tagged %s words" % WORD)
    return d


def thumbnail():
    d, p = _page()
    thumb = d.get_new_xref()
    d.update_object(thumb, "<</Width 1/Height 1/ColorSpace/DeviceGray/BitsPerComponent 8>>")
    d.update_stream(thumb, b"THUMB " + WORD.encode())
    d.xref_set_key(p.xref, "Thumb", "%d 0 R" % thumb)
    return d


def piece_info():
    d, p = _page()
    priv = d.get_new_xref()
    d.update_object(priv, "<<>>")
    d.update_stream(priv, b"%AI private: the drawing as it was, Plain " + WORD.encode())
    d.xref_set_key(p.xref, "PieceInfo", "<</Illustrator<</LastModified(D:2026)"
                                        "/Private<</AIPrivateData1 %d 0 R>>>>>>" % priv)
    return d


def only_outside_the_pages():
    """The term in none of the pages' drawing: a layer's name, a bookmark's web address, an
    XFA form, a field on no page (four other places in the file)."""
    d = pymupdf.open()
    d.new_page().insert_text((50, 50), "Nothing to see", fontsize=12)
    d.add_ocg("%s layer" % WORD, on=True)
    d.set_toc([[1, "Web", 1, {"kind": pymupdf.LINK_URI,
                              "uri": "https://example.com/%s" % WORD}]])
    xfa_with(d, b"<form><name>" + WORD.encode() + b"</name></form>")
    field = d.get_new_xref()
    d.update_object(field, "<</T(hidden)/FT/Tx/V(%s)>>" % WORD)
    d.xref_set_key(d.pdf_catalog(), "AcroForm/Fields", "[%d 0 R]" % field)
    return d


CASES = [hidden_layer, cropped_away, layer_name, bookmark_address, field_on_no_page,
         rich_text_note, own_information_key, xfa_plain, xfa_references, actual_text,
         thumbnail, piece_info]


def _digest(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _leaks(data):
    return [w for w in (WORD.encode(), b"&#84;OPSECRET") if w in data]


class Folder(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="kz-batch-redact-")
        self.addCleanup(shutil.rmtree, self.dir, True)

    def files(self, makers):
        paths = []
        for make in makers:
            path = os.path.join(self.dir, make.__name__ + ".pdf")
            d = make()
            d.save(path)
            d.close()
            paths.append(path)
        return paths

    def run_batch(self, paths, steps, name):
        out = os.path.join(self.dir, "out-" + name)
        digests = {p: _digest(p) for p in paths}
        b = B.Batch(paths, steps, {"mode": "folder", "folder": out})
        b.run_all()
        for p, h in digests.items():         # (the originals stay as they were)
            self.assertEqual(_digest(p), h, p)
        for r in b.results:
            self.assertEqual(r.status, B.DONE, "%s: %s" % (r.path, r.details()))
            self.assertNotIn("Warning", r.details())
        return b, out


class SearchAndRedact(Folder):
    def test_every_hidden_place_is_cleaned(self):
        paths = self.files(CASES)
        for scrub in (True, False):
            with self.subTest(scrub=scrub):
                b, out = self.run_batch(paths, [B.step("search_redact", words=WORD,
                                                       scrub=scrub)], "s%d" % scrub)
                for path, r in zip(paths, b.results):
                    name = os.path.basename(path)
                    self.assertEqual(r.outputs, [os.path.join(out, name)])
                    data = _all_bytes(r.outputs[0])
                    self.assertEqual(_leaks(data), [], name)
                    self.assertIn(b"Other words stay", data, name)
                    self.assertRegex(r.details(), r"^Redacted \d+ match\(es\) on page\(s\) 1",
                                     name)

    def test_what_was_removed_and_where(self):
        paths = self.files([hidden_layer, cropped_away, layer_name, field_on_no_page,
                            only_outside_the_pages])
        b, out = self.run_batch(paths, [B.step("search_redact", words=WORD)], "where")
        details = [r.details() for r in b.results]
        # the hidden layer's copy and the cropped-away ones are on the page too
        self.assertTrue(details[0].startswith("Redacted 2 match(es) on page(s) 1"), details[0])
        self.assertTrue(details[1].startswith("Redacted 3 match(es) on page(s) 1"), details[1])
        self.assertIn("also removed from 1 other place(s) in the file", details[2])
        self.assertIn("also removed from 4 other place(s) in the file", details[3])
        # only outside the pages: removed from there (as Search & redact offers), and said
        self.assertEqual(details[4], "Not found on the pages; removed from 4 other place(s) "
                                     "in the file (layer names, web addresses, form data, "
                                     "alternate text...)")
        self.assertEqual(_leaks(_all_bytes(b.results[4].outputs[0])), [])
        with pymupdf.open(b.results[2].outputs[0]) as d:
            self.assertEqual([c["text"] for c in d.layer_ui_configs()],
                             ["The [redacted] layer"])
        with pymupdf.open(b.results[0].outputs[0]) as d:     # (the layer stays hidden)
            self.assertEqual([c["on"] for c in d.layer_ui_configs()], [0])

    def test_only_marking_removes_nothing_and_says_so(self):
        paths = self.files([hidden_layer, only_outside_the_pages])
        b, out = self.run_batch(paths, [B.step("search_redact", words=WORD, apply=False)],
                                "mark")
        self.assertEqual(sorted(os.listdir(out)),
                         ["hidden_layer-marked.pdf", "only_outside_the_pages.pdf"])
        first, second = (r.details() for r in b.results)
        self.assertEqual(first, "Marked 2 occurrence(s) for redaction on page(s) 1; nothing "
                                "was removed yet: open the file and use Apply redactions")
        self.assertIn("nothing was removed", second)
        self.assertIn("4 other place(s) in the file", second)
        # (and it's true: the words are all still there, under marks to review)
        self.assertIn(WORD.encode(), _all_bytes(b.results[0].outputs[0]))
        with pymupdf.open(b.results[0].outputs[0]) as d:
            self.assertEqual(len([a for a in d[0].annots() if a.type[1] == "Redact"]), 2)
        # applied in a second run: nothing left
        b2, _out = self.run_batch([b.results[0].outputs[0]], [B.step("apply_redactions")],
                                  "applied")
        self.assertEqual(_leaks(_all_bytes(b2.results[0].outputs[0])), [])
        self.assertTrue(b2.results[0].details().startswith(
            "Applied 2 redaction(s) on page(s) 1"), b2.results[0].details())


class ApplyRedactions(Folder):
    def marked_by_hand(self, make):
        """The file with a redaction mark drawn by hand over the line holding the word."""
        def marked():
            d = make()
            p = d[0]
            for r in p.search_for(WORD):
                p.add_redact_annot(r + (-2, -2, 2, 2), fill=(0, 0, 0)).update()
            return d
        marked.__name__ = make.__name__
        return marked

    def test_the_page_as_it_was_goes_too(self):
        # (the ActualText wrapper, the thumbnail, a program's private copy of the page)
        makers = [self.marked_by_hand(m) for m in (actual_text, thumbnail, piece_info)]
        paths = self.files(makers)
        for scrub in (True, False):
            with self.subTest(scrub=scrub):
                b, _out = self.run_batch(paths, [B.step("apply_redactions", scrub=scrub)],
                                         "a%d" % scrub)
                for path, r in zip(paths, b.results):
                    data = _all_bytes(r.outputs[0])
                    self.assertEqual(_leaks(data), [], os.path.basename(path))
                    self.assertNotIn(b"AIPrivateData", data)
                    self.assertIn(b"Other words stay", data)
                    self.assertRegex(r.details(), r"^Applied \d redaction\(s\) on page\(s\) 1")


class PartOfATaggedSpan(unittest.TestCase):
    """A mark over part of a tagged span ("/Span <</ActualText (Tagged TOPSECRET words)>>
    BDC ... EMC"): MuPDF took the letters away and kept the span's ActualText, the words
    readable in the file and even in the page's text (the 1.9 battery covered a mark over a
    whole span, whose empty wrapper the clean-up drops). Found by Batch processing's check
    after redacting; fixed in the step both commands share (document_view.redact_page)."""

    def view(self):
        from kanzonas.document_view import DocumentView
        d, p = _page()
        _with_actual_text(d, p, "Tagged %s words" % WORD)
        _with_actual_text(d, p, "Untouched (tagged) words", y=400)
        path = os.path.join(tempfile.mkdtemp(), "tagged.pdf")
        d.save(path)
        d.close()
        v = DocumentView(path)
        self.addCleanup(lambda: (setattr(v, "dirty", False), v.close_doc()))
        return v

    def check(self, v):
        out = v.path[:-4] + "-out.pdf"
        v.save(out)
        data = _all_bytes(out)
        self.assertEqual(_leaks(data), [])
        text = v.doc[0].get_text()
        self.assertNotIn(WORD, text)
        self.assertIn("Tagged", text)
        # (a span no mark touched keeps its ActualText)
        self.assertIn(b"/ActualText(Untouched \\(tagged\\) words)", data.replace(b" (", b"("))
        self.assertIn("Untouched (tagged) words", text)

    def test_apply_redactions(self):
        for scrub in (True, False):
            with self.subTest(scrub=scrub):
                v = self.view()
                self.assertEqual(v.search_redact(WORD), 2)
                v.apply_redactions(scrub)
                self.check(v)

    def test_apply_selected_redactions(self):
        v = self.view()
        v.search_redact(WORD)
        v._set_selection(0, [a.xref for a in v.doc[0].annots()])
        self.assertEqual(v.apply_selected_redactions(), 2)
        self.check(v)


if __name__ == "__main__":
    unittest.main()
