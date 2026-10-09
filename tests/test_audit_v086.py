"""Regressions from the v0.85 program audit: lost inline text edits, stale editor and field
focus after undo / page changes, Find after closing, flatten form fields, and the
Search & redact / attachment / link safety fixes.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_audit_v086
"""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf as F  # noqa: E402
from PySide6.QtCore import QEvent, Qt  # noqa: E402
from PySide6.QtGui import QKeyEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas.document_view import DocumentView  # noqa: E402


class AuditV086(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(mock.patch.stopall)
        for n in ("information", "warning", "critical"):
            mock.patch.object(QMessageBox, n, return_value=None).start()
        self.views = []
        self.addCleanup(lambda: [v.close_doc() for v in self.views if not v.doc.is_closed])

    def pdf(self, pages=3, fields=False):
        d = F.open()
        for i in range(pages):
            pg = d.new_page()
            pg.insert_text((72, 72), "PAGE %d HELLO" % i, fontsize=14)
            if fields:
                w = F.Widget()
                w.field_type = F.PDF_WIDGET_TYPE_TEXT
                w.field_name = "f%d" % i
                w.field_value = "val%d" % i
                w.rect = F.Rect(72, 200, 272, 230)
                pg.add_widget(w)
        p = os.path.join(self.tmp.name, "in%d.pdf" % len(self.views))
        d.save(p)
        return p

    def view(self, path):
        v = DocumentView(path)
        self.views.append(v)
        v.resize(800, 1000)
        v.show()
        APP.processEvents()
        return v

    def test_save_keeps_text_typed_in_the_open_editor(self):
        p = self.pdf()
        v = self.view(p)
        v.edit_text_at(0, F.Point(80, 68))
        v._inline.text.setPlainText("CHANGED")
        v.save()
        self.assertIn("CHANGED", F.open(p)[0].get_text())

    def test_undo_with_the_editor_open_leaves_clicks_working(self):
        v = self.view(self.pdf())
        v._create(1, {"kind": "rect", "props": {"stroke": "#0078d7", "width": 2},
                      "rect": F.Rect(40, 40, 80, 80)})
        v.edit_text_at(0, F.Point(80, 68))
        v.undo()
        self.assertIsNone(v._inline)
        v.edit_text_at(0, F.Point(80, 68))           # raised "already deleted" before
        self.assertIsNotNone(v._inline)

    def test_deleting_the_focused_fields_page_clears_the_focus(self):
        v = self.view(self.pdf(pages=2, fields=True))
        xref = v.doc[1].first_widget.xref
        v._set_field_focus(1, xref)
        v.delete_pages([1])
        self.assertIsNone(v.field_focus)
        v.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier))

    def test_closing_stops_a_running_find(self):
        d = F.open()
        for i in range(1500):
            d.new_page(width=200, height=200).insert_text((20, 40), "p%d" % i)
        p = os.path.join(self.tmp.name, "many.pdf")
        d.save(p)
        v = self.view(p)
        v.find("nomatch")
        v.close_doc()
        errors = []
        old = sys.excepthook
        sys.excepthook = lambda *a: errors.append(a)
        try:
            for _ in range(20):
                APP.processEvents()
        finally:
            sys.excepthook = old
        self.assertEqual(errors, [])

    def test_flatten_one_page_keeps_field_names_and_no_orphans(self):
        p = self.pdf(pages=2, fields=True)
        v = self.view(p)
        v.flatten(pages=[0], widgets=False)
        out = os.path.join(self.tmp.name, "out.pdf")
        v.save(out)
        d = F.open(out)
        names = sorted(w.field_name for pg in d for w in pg.widgets())
        self.assertEqual(names, ["f0", "f1"])
        fields = d.xref_get_key(d.pdf_catalog(), "AcroForm/Fields")[1]
        self.assertEqual(fields.count(" 0 R"), 2)

    def test_search_redact_removes_term_from_options_tooltips_and_links(self):
        d = F.open()
        pg = d.new_page()
        pg.insert_text((72, 72), "SECRET4242 here")
        w = F.Widget()
        w.field_type = F.PDF_WIDGET_TYPE_COMBOBOX
        w.field_name = "pick"
        w.choice_values = ["a", "SECRET4242"]
        w.field_value = "a"
        w.rect = F.Rect(72, 200, 272, 230)
        pg.add_widget(w)
        w2 = F.Widget()
        w2.field_type = F.PDF_WIDGET_TYPE_TEXT
        w2.field_name = "t"
        w2.field_label = "tip SECRET4242"
        w2.rect = F.Rect(72, 300, 272, 330)
        pg.add_widget(w2)
        pg.insert_link({"kind": F.LINK_URI, "from": F.Rect(72, 400, 200, 420),
                        "uri": "https://x/?q=SECRET4242"})
        p = os.path.join(self.tmp.name, "red.pdf")
        d.save(p)
        v = self.view(p)
        self.assertGreater(v.hidden_matches("SECRET4242")["links"], 0)
        v.search_redact("SECRET4242")
        v.apply_redactions()
        out = os.path.join(self.tmp.name, "red_out.pdf")
        v.save(out)
        r = F.open(out)
        left = [x for x in range(1, r.xref_length()) if "SECRET4242" in (r.xref_object(x) or "")]
        self.assertEqual(left, [])

    def test_attachment_names_cannot_dodge_the_type_check(self):
        for name in ("evil.exe.", "evil.exe ", "x.exe::$DATA", "a\\b/evil.hta.", "doc.docm"):
            safe = DocumentView.safe_file_name(name)
            self.assertNotIn(os.path.splitext(safe)[1].lower(), DocumentView.SAFE_OPEN, name)
        self.assertEqual(DocumentView.safe_file_name("ok.pdf"), "ok.pdf")

    def test_network_paths_are_recognized(self):
        self.assertTrue(DocumentView._is_network_path("\\\\attacker\\s\\a.pdf"))
        self.assertTrue(DocumentView._is_network_path("//attacker/s/a.pdf"))
        self.assertFalse(DocumentView._is_network_path("/home/me/a.pdf"))


if __name__ == "__main__":
    unittest.main()
