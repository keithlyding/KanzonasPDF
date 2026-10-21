"""Protecting a filled-in form locks its fields, in every reader; Shift+click with a drawing
tool starts a new markup on top of an existing one instead of moving it.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_form_protection
"""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402
from PySide6.QtCore import QEvent, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QMouseEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QCheckBox, QDialog  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas.document_view import DocumentView  # noqa: E402
from kanzonas.main_window import MainWindow  # noqa: E402


def form(path, filled=True):
    d = pymupdf.open()
    p = d.new_page()
    w = pymupdf.Widget()
    w.field_type = pymupdf.PDF_WIDGET_TYPE_TEXT
    w.field_name = "name"
    w.rect = pymupdf.Rect(72, 72, 300, 92)
    w.field_value = "Keith" if filled else ""
    p.add_widget(w)
    c = pymupdf.Widget()
    c.field_type = pymupdf.PDF_WIDGET_TYPE_CHECKBOX
    c.field_name = "agree"
    c.rect = pymupdf.Rect(72, 110, 86, 124)
    c.field_value = True if filled else False
    p.add_widget(c)
    d.save(path)
    return path


def read_only(doc):
    out = {}
    for page in doc:
        for w in page.widgets():
            out[w.field_name] = bool(w.field_flags & 1)
    return out


def open_window(path):
    w = MainWindow()
    w.show()
    w.open_file(path)
    APP.processEvents()
    return w


class Protection(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def close(self, w):
        self.addCleanup(lambda: (setattr(w, "_close_confirmed", True), w.close()))

    def form_box_default(self, w, **kw):
        """Open Security properties and read the default of 'Filling in form fields'."""
        seen = {}

        def look(dlg):
            for c in dlg.findChildren(QCheckBox):
                if c.text().startswith("Filling in form fields"):
                    seen["form"] = c.isChecked()
                if c.text().startswith("Restrict printing"):
                    seen["restrict"] = c.isChecked()
            return QDialog.Rejected
        with mock.patch.object(QDialog, "exec", look):
            w.security_properties(**kw)
        return seen

    def test_a_filled_or_signed_form_defaults_to_locked_fields(self):
        w = open_window(form(os.path.join(self.dir, "filled.pdf")))
        self.close(w)
        self.assertTrue(w.view().form_filled())
        self.assertFalse(self.form_box_default(w)["form"])
        b = open_window(form(os.path.join(self.dir, "blank.pdf"), filled=False))
        self.close(b)
        self.assertFalse(b.view().form_filled())
        self.assertTrue(self.form_box_default(b)["form"])          # a form to hand out
        seen = self.form_box_default(b, preset_restrict=True)      # just signed it
        self.assertEqual(seen, {"form": False, "restrict": True})

    def test_protected_form_fields_are_locked_in_the_file_and_unlock_again(self):
        path = form(os.path.join(self.dir, "f.pdf"))
        w = open_window(path)
        self.close(w)
        v = w.view()
        perms = (pymupdf.PDF_PERM_ACCESSIBILITY | pymupdf.PDF_PERM_PRINT |
                 pymupdf.PDF_PERM_PRINT_HQ | pymupdf.PDF_PERM_COPY)
        v.set_security("", "secret", perms)
        self.assertEqual(read_only(v.doc), {"name": True, "agree": True})   # right away
        v.undo()
        self.assertEqual(read_only(v.doc), {"name": False, "agree": False})
        v.redo()
        out = os.path.join(self.dir, "locked.pdf")
        v.save(out)
        r = pymupdf.open(out)
        self.assertTrue(r.metadata["encryption"])
        self.assertFalse(r.permissions & pymupdf.PDF_PERM_FORM)
        self.assertFalse(r.permissions & pymupdf.PDF_PERM_ANNOTATE)
        self.assertEqual(read_only(r), {"name": True, "agree": True})
        self.assertEqual(r[0].load_widget(r[0].first_widget.xref).field_value, "Keith")
        r.close()
        # the owner opens it again and takes the protection off: the fields unlock
        o = DocumentView(out)
        self.addCleanup(o.close_doc)
        self.assertTrue(o.read_only)
        self.assertTrue(o.unlock("secret"))
        o.set_security("", "", -1)
        self.assertEqual(read_only(o.doc), {"name": False, "agree": False})
        free = os.path.join(self.dir, "free.pdf")
        o.save(free)
        r = pymupdf.open(free)
        self.assertFalse(r.metadata["encryption"])
        self.assertEqual(read_only(r), {"name": False, "agree": False})

    def test_fields_already_read_only_stay_so(self):
        path = form(os.path.join(self.dir, "ro.pdf"))
        d = pymupdf.open(path)
        page = d[0]                                # (kept while its widget is used)
        wd = page.first_widget
        wd.field_flags |= 1
        wd.update()
        d.saveIncr()
        d.close()
        w = open_window(path)
        self.close(w)
        v = w.view()
        v.set_security("", "secret", pymupdf.PDF_PERM_PRINT)
        v.set_security("", "", -1)                 # unlocks only what it locked
        self.assertEqual(read_only(v.doc), {"name": True, "agree": False})

    def test_allowing_form_filling_keeps_fields_open(self):
        w = open_window(form(os.path.join(self.dir, "open.pdf"), filled=False))
        self.close(w)
        v = w.view()
        v.set_security("", "secret", pymupdf.PDF_PERM_PRINT | pymupdf.PDF_PERM_FORM)
        self.assertEqual(read_only(v.doc), {"name": False, "agree": False})

    def test_a_read_only_field_is_not_filled_in_this_app(self):
        w = open_window(form(os.path.join(self.dir, "click.pdf")))
        self.close(w)
        v = w.view()
        v.set_security("", "secret", pymupdf.PDF_PERM_PRINT)
        said = []
        v.statusMessage.connect(said.append)
        box = next(x for x in v.doc[0].widgets() if x.field_name == "agree")
        v.fill_field(0, box.xref)
        self.assertEqual(next(x for x in v.doc[0].widgets()
                              if x.field_name == "agree").field_value, box.field_value)
        self.assertTrue(any("read-only" in m and "Security properties" in m for m in said), said)


class ShiftDrawsOnMarkups(unittest.TestCase):
    def click(self, w, x, y, mods=Qt.NoModifier, double=False):
        pos = QPointF(x, y)
        for kind, f in ((QEvent.MouseButtonPress, w.mousePressEvent),
                        (QEvent.MouseButtonRelease, w.mouseReleaseEvent)):
            f(QMouseEvent(kind, pos, w.mapToGlobal(pos), Qt.LeftButton,
                          Qt.LeftButton if kind == QEvent.MouseButtonPress else Qt.NoButton, mods))
        if double:
            w.mouseDoubleClickEvent(QMouseEvent(QEvent.MouseButtonDblClick, pos, w.mapToGlobal(pos),
                                                Qt.LeftButton, Qt.LeftButton, mods))

    def setUp(self):
        d = pymupdf.open()
        p = d.new_page()
        a = p.add_polyline_annot([(100, 100), (200, 100), (200, 200)])
        a.set_border(width=2)
        a.update()
        path = os.path.join(tempfile.mkdtemp(), "poly.pdf")
        d.save(path)
        self.v = DocumentView(path)
        self.addCleanup(self.v.close_doc)
        self.v.tool = "polyline"
        self.w = self.v.pages[0]
        self.end = self.w.to_screen_pt(pymupdf.Point(200, 200))

    def polylines(self):
        """Their vertices, rounded (read while the page is held)."""
        page = self.v.doc[0]
        return [[[round(c) for c in p] for p in a.vertices] for a in page.annots()
                if a.type[0] == pymupdf.PDF_ANNOT_POLY_LINE]

    def test_shift_click_on_a_polyline_starts_a_new_one_there(self):
        e = self.end
        self.click(self.w, e.x(), e.y(), Qt.ShiftModifier)
        self.assertIsNone(self.v.selection)                     # nothing selected or moved
        self.click(self.w, e.x() + 80, e.y())
        self.click(self.w, e.x() + 80, e.y() + 80, double=True)
        lines = self.polylines()
        self.assertEqual(len(lines), 2)
        self.assertIn([[100, 100], [200, 100], [200, 200]], lines)       # the old one as it was
        new = [v for v in lines if v != [[100, 100], [200, 100], [200, 200]]][0]
        self.assertLess(pymupdf.Point(new[0]).distance_to((200, 200)), 1.5, lines)

    def test_plain_click_still_selects_the_polyline(self):
        e = self.end
        self.click(self.w, e.x(), e.y())
        self.assertIsNotNone(self.v.selection)
        self.assertEqual(len(self.polylines()), 1)


if __name__ == "__main__":
    unittest.main()
