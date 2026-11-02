"""What the 1.6.3 core-PDF break-it battery found, fixed: Sanitize and Apply redactions take
out the scripts PyMuPDF's scrub leaves (a Rendition action's JavaScript, an XFA form's
scripts, javascript: web addresses); Compress keeps the document's password protection;
Compare asks for the password of a protected earlier revision; Search & redact takes the
term out of the text kept outside the page drawing (tags' alternate text, link notes, page
labels, named destinations).

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_battery_163_core
"""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402
from PySide6.QtWidgets import (QApplication, QDialog, QFileDialog, QInputDialog,  # noqa: E402
                               QMessageBox)

APP = QApplication.instance() or QApplication([])

from kanzonas import document_view  # noqa: E402
from kanzonas.document_view import DocumentView  # noqa: E402
from kanzonas.main_window import MainWindow  # noqa: E402


def _tmp(name):
    return os.path.join(tempfile.mkdtemp(), name)


def _all_bytes(path, pw=None):
    """The file's every object and stream, decrypted and uncompressed."""
    d = pymupdf.open(path)
    if d.needs_pass:
        d.authenticate(pw or "")
    return d.tobytes(expand=255, encryption=pymupdf.PDF_ENCRYPT_NONE)


class Scripts(unittest.TestCase):
    def scripted(self):
        d = pymupdf.open()
        p = d.new_page()
        p.insert_text((72, 72), "Hello")
        # a GoTo link whose next action plays a Rendition carrying JavaScript
        p.insert_link({"kind": pymupdf.LINK_URI, "from": pymupdf.Rect(150, 50, 190, 60),
                       "uri": "https://example.com"})
        r = d.get_new_xref()
        d.update_object(r, "<</S/Rendition/OP 0/JS(app.alert('RENDITIONJS'))>>")
        x = [a for a, t, _ in p.annot_xrefs() if t == pymupdf.PDF_ANNOT_LINK][0]
        d.xref_set_key(x, "A", "<</S/GoTo/D[%d 0 R/Fit]/Next %d 0 R>>" % (p.xref, r))
        # a Rendition written straight into a link
        p.insert_link({"kind": pymupdf.LINK_URI, "from": pymupdf.Rect(250, 50, 290, 60),
                       "uri": "https://example.org"})
        x2 = [a for a, t, _ in p.annot_xrefs() if t == pymupdf.PDF_ANNOT_LINK][1]
        d.xref_set_key(x2, "A", "<</S/Rendition/OP 0/JS(app.alert('INLINERENDITIONJS'))>>")
        p.insert_link({"kind": pymupdf.LINK_URI, "from": pymupdf.Rect(350, 50, 390, 60),
                       "uri": "https://kept.example"})
        # a web address that is a script
        p.insert_link({"kind": pymupdf.LINK_URI, "from": pymupdf.Rect(50, 50, 90, 60),
                       "uri": "javascript:alert('URIJS')"})
        # an XFA form with a script (Acrobat runs it)
        xfa = d.get_new_xref()
        d.update_object(xfa, "<<>>")
        d.update_stream(xfa, b"<template><field><event><script contentType='application/"
                             b"x-javascript'>app.alert('XFAJS')</script></event></field>"
                             b"</template>")
        d.xref_set_key(d.pdf_catalog(), "AcroForm", "<</Fields[]/XFA %d 0 R>>" % xfa)
        path = _tmp("scripts.pdf")
        d.save(path)
        return path

    WORDS = (b"RENDITIONJS", b"INLINERENDITIONJS", b"URIJS", b"XFAJS")

    def test_remove_scripts_takes_out_what_scrub_leaves(self):
        d = pymupdf.open(self.scripted())
        d.scrub(javascript=True, hidden_text=False)
        document_view.remove_scripts(d)
        data = d.tobytes(garbage=4, expand=255)
        for word in self.WORDS:
            self.assertNotIn(word, data, word)
        # the ordinary link stays
        self.assertIn(b"https://kept.example", data)

    def test_sanitize_and_apply_redactions_leave_no_script_in_the_saved_file(self):
        src = self.scripted()
        for how in ("sanitize", "redact"):
            v = DocumentView(src)
            self.addCleanup(v.close_doc)
            if how == "sanitize":
                v.sanitize({k: on for k, _label, on in v.SANITIZE_OPTIONS})
            else:
                v.apply_redactions(True)
            out = _tmp(how + ".pdf")
            v.save(out)
            data = _all_bytes(out)
            for word in self.WORDS:
                self.assertNotIn(word, data, (how, word))


class Compress(unittest.TestCase):
    def window(self, path, pw):
        w = MainWindow()
        self.addCleanup(lambda: (setattr(w, "_close_confirmed", True), w.close()))
        with mock.patch.object(QInputDialog, "getText", lambda *a, **k: (pw, True)), \
                mock.patch.object(QMessageBox, "information", lambda *a, **k: QMessageBox.Ok):
            w.open_file(path)
        v = w.view()
        self.addCleanup(lambda: setattr(v, "dirty", False))
        return w, v

    def compress(self, w):
        out = _tmp("small.pdf")
        with mock.patch.object(QInputDialog, "getItem", lambda *a, **k: (a[3][1], True)), \
                mock.patch.object(QFileDialog, "getSaveFileName", lambda *a, **k: (out, "")), \
                mock.patch.object(QMessageBox, "information", lambda *a, **k: QMessageBox.Ok), \
                mock.patch.object(QMessageBox, "critical",
                                  lambda *a, **k: self.fail("compress failed: %s" % (a,))):
            w.compress()
        return out

    def protected(self, **kw):
        d = pymupdf.open()
        d.new_page().insert_text((72, 72), "Protected words")
        path = _tmp("p.pdf")
        d.save(path, encryption=pymupdf.PDF_ENCRYPT_AES_256, **kw)
        return path

    def test_the_smaller_copy_keeps_the_open_password(self):
        w, v = self.window(self.protected(owner_pw="owner", user_pw="user"), "user")
        out = self.compress(w)
        small = pymupdf.open(out)
        self.assertTrue(small.needs_pass)               # (it came out unprotected)
        self.assertTrue(small.authenticate("user"))
        self.assertIn("Protected words", small[0].get_text())

    def test_the_smaller_copy_keeps_the_permissions(self):
        perms = pymupdf.PDF_PERM_PRINT | pymupdf.PDF_PERM_ANNOTATE
        w, v = self.window(self.protected(owner_pw="owner", permissions=perms), "")
        out = self.compress(w)
        small = pymupdf.open(out)
        self.assertFalse(small.needs_pass)
        self.assertTrue((small.metadata or {}).get("encryption"))
        self.assertFalse(small.permissions & pymupdf.PDF_PERM_MODIFY)
        self.assertFalse(small.permissions & pymupdf.PDF_PERM_COPY)

    def test_protection_set_but_not_saved_yet_goes_on_the_copy(self):
        d = pymupdf.open()
        d.new_page().insert_text((72, 72), "Plain words")
        path = _tmp("plain.pdf")
        d.save(path)
        w, v = self.window(path, "")
        v.set_security("newopen", "newowner", pymupdf.PDF_PERM_PRINT)
        out = self.compress(w)
        small = pymupdf.open(out)
        self.assertTrue(small.needs_pass)
        self.assertTrue(small.authenticate("newopen"))

    def test_a_plain_document_stays_plain(self):
        d = pymupdf.open()
        d.new_page().insert_text((72, 72), "Plain words")
        path = _tmp("plain.pdf")
        d.save(path)
        w, v = self.window(path, "")
        out = self.compress(w)
        small = pymupdf.open(out)
        self.assertFalse(small.needs_pass)
        self.assertFalse((small.metadata or {}).get("encryption"))


class CompareProtected(unittest.TestCase):
    def test_a_protected_earlier_revision_asks_for_its_password(self):
        d = pymupdf.open()
        d.new_page().insert_text((72, 72), "First words")
        old = _tmp("old.pdf")
        d.save(old, encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="o", user_pw="u")
        d = pymupdf.open()
        d.new_page().insert_text((72, 72), "Second words")
        new = _tmp("new.pdf")
        d.save(new)
        w = MainWindow()
        self.addCleanup(lambda: (setattr(w, "_close_confirmed", True), w.close()))
        w.open_file(new)
        asked, failed = [], []

        def get_text(*a, **k):
            asked.append(a[1:3])
            return ("wrong", True) if len(asked) == 1 else ("u", True)
        with mock.patch.object(QFileDialog, "getOpenFileName", lambda *a, **k: (old, "")), \
                mock.patch.object(QInputDialog, "getText", get_text), \
                mock.patch.object(QDialog, "exec", lambda self: QDialog.Accepted), \
                mock.patch.object(QMessageBox, "information", lambda *a, **k: QMessageBox.Ok), \
                mock.patch.object(QMessageBox, "critical",
                                  lambda *a, **k: failed.append(a[1:3])):
            w.compare_documents()
        self.assertEqual(failed, [])            # ("Compare failed: document closed or encrypted")
        self.assertEqual(len(asked), 2)         # a wrong password is asked again
        self.assertEqual(w.tabs.count(), 2)     # the comparison opened
        for v in w._views():
            v.dirty = False

    def test_canceling_the_password_compares_nothing(self):
        d = pymupdf.open()
        d.new_page().insert_text((72, 72), "First words")
        old = _tmp("old.pdf")
        d.save(old, encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="o", user_pw="u")
        d = pymupdf.open()
        d.new_page()
        new = _tmp("new.pdf")
        d.save(new)
        w = MainWindow()
        self.addCleanup(lambda: (setattr(w, "_close_confirmed", True), w.close()))
        w.open_file(new)
        failed = []
        with mock.patch.object(QFileDialog, "getOpenFileName", lambda *a, **k: (old, "")), \
                mock.patch.object(QInputDialog, "getText", lambda *a, **k: ("", False)), \
                mock.patch.object(QDialog, "exec", lambda self: QDialog.Rejected), \
                mock.patch.object(QMessageBox, "critical",
                                  lambda *a, **k: failed.append(a[1:3])):
            w.compare_documents()
        self.assertEqual(failed, [])
        self.assertEqual(w.tabs.count(), 1)


class SearchRedactOutsideTheDrawing(unittest.TestCase):
    def tagged(self):
        """A tagged page: the word is on the page and in the structure tree's alternate text
        and ActualText, a link's note, the page label and a named destination's name."""
        d = pymupdf.open()
        p = d.new_page(width=400, height=400)
        p.insert_text((50, 50), "Plain TOPSECRET word", fontsize=12)
        se, root = d.get_new_xref(), d.get_new_xref()
        d.update_object(se, "<</Type/StructElem/S/Figure/P %d 0 R/Pg %d 0 R/K 0"
                            "/Alt(TOPSECRET alt)/ActualText(the TOPSECRET actual)"
                            "/T(TOPSECRET title)/E(TOPSECRET expansion)>>" % (root, p.xref))
        d.update_object(root, "<</Type/StructTreeRoot/K %d 0 R>>" % se)
        d.xref_set_key(d.pdf_catalog(), "StructTreeRoot", "%d 0 R" % root)
        d.xref_set_key(d.pdf_catalog(), "MarkInfo", "<</Marked true>>")
        p.insert_link({"kind": pymupdf.LINK_URI, "from": pymupdf.Rect(50, 300, 150, 312),
                       "uri": "https://example.com/x"})
        lx = [x for x, t, _ in p.annot_xrefs() if t == pymupdf.PDF_ANNOT_LINK][0]
        d.xref_set_key(lx, "Contents", "(a TOPSECRET link note)")
        d.set_page_labels([{"startpage": 0, "prefix": "TOPSECRET-", "style": "D"}])
        d.xref_set_key(d.pdf_catalog(), "Names",
                       "<</Dests<</Names[(TOPSECRETdest) [%d 0 R /XYZ 0 0 0]]>>>>" % p.xref)
        # a Unicode string (UTF-16) holding the word too
        d.xref_set_key(se, "Lang", "(en)")
        d.xref_set_key(root, "Alt", pymupdf.get_pdf_str("café TOPSECRET été"))
        path = _tmp("tagged.pdf")
        d.save(path)
        return path

    def test_the_term_is_gone_from_the_saved_file(self):
        v = DocumentView(self.tagged())
        self.addCleanup(v.close_doc)
        self.assertEqual(v.search_redact("TOPSECRET"), 1)
        v.apply_redactions(True)
        out = _tmp("out.pdf")
        v.save(out)
        data = _all_bytes(out)
        self.assertNotIn(b"TOPSECRET", data)
        d = pymupdf.open(out)
        self.assertNotIn("TOPSECRET", d[0].get_text())
        self.assertEqual([lab.get("prefix") for lab in d.get_page_labels()], ["[redacted]-"])
        # still tagged, the rest of the text kept
        self.assertIn(b"[redacted] alt", data)
        self.assertNotEqual(d.xref_get_key(d.pdf_catalog(), "StructTreeRoot")[0], "null")

    def test_styles_and_markup_data_naming_the_term_are_left_alone(self):
        # ("fill" is in every shape's private data and "Helv" in a field's style)
        from kanzonas import annotations
        d = pymupdf.open()
        p = d.new_page()
        p.insert_text((72, 72), "Please fill Helv in", fontsize=12)
        w = pymupdf.Widget()
        w.field_type = pymupdf.PDF_WIDGET_TYPE_TEXT
        w.field_name = "name"
        w.rect = pymupdf.Rect(72, 300, 250, 320)
        p.add_widget(w)
        path = _tmp("styles.pdf")
        d.save(path)
        v = DocumentView(path)
        self.addCleanup(v.close_doc)
        self.addCleanup(lambda: setattr(v, "dirty", False))
        model = {"kind": "rect", "props": dict(annotations.DEFAULTS["rect"], fill="#00ff00"),
                 "rect": pymupdf.Rect(300, 400, 400, 500)}
        v.modify(lambda: annotations.write(v.doc[0], model), [0])
        before = [annotations.read(a) for a in v.doc[0].annots()]
        da = v.doc.xref_get_key(next(v.doc[0].widgets()).xref, "DA")
        for word in ("fill", "Helv"):
            v.search_redact(word)
        v.apply_redactions(True)
        after = [annotations.read(a) for a in v.doc[0].annots()]
        self.assertEqual([m["props"] for m in after], [m["props"] for m in before])
        self.assertEqual(v.doc.xref_get_key(next(v.doc[0].widgets()).xref, "DA"), da)
        self.assertNotIn("fill", v.doc[0].get_text())

    def test_a_mark_not_applied_keeps_its_term(self):
        # (Apply selected redactions writes the others back: their term must stay with them)
        v = DocumentView(self.tagged())
        self.addCleanup(v.close_doc)
        self.addCleanup(lambda: setattr(v, "dirty", False))
        v.search_redact("TOPSECRET")
        v.search_redact("word")
        marks = {a.info["content"]: a.xref for a in v.doc[0].annots()}
        v._set_selection(0, [marks["Redaction: TOPSECRET"]])
        self.assertEqual(v.apply_selected_redactions(), 1)
        left = [a.info["content"] for a in v.doc[0].annots()]
        self.assertEqual(left, ["Redaction: word"])


if __name__ == "__main__":
    unittest.main()
