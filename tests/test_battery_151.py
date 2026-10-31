"""What the core-PDF break-it battery of 1.5 found in forms, signing, sanitizing, opening and
saving, fixed: Sanitize and Apply redactions take out JavaScript written inline and Launch
actions; form data on a parent field is cleared and an emptied field looks empty; a field
is renamed where its name lives; a blank dropdown doesn't make a form "filled"; fields on a
turned page read upright; fields side by side are one row; text added after a Save shows
(Save cuts fonts down to the glyphs used); Save asks before replacing a file another
program changed; a file open in another window isn't opened twice; a canceled password
prompt is no error; a repaired file says so.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_battery_151
"""
import os
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402
from PySide6.QtWidgets import QApplication, QInputDialog, QMessageBox  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import document_view, main_window  # noqa: E402
from kanzonas.document_view import DocumentView  # noqa: E402

P = pymupdf.Point


def a_pdf(rotation=0, pages=1):
    d = pymupdf.open()
    for _ in range(pages):
        d.new_page().insert_text((72, 100), "hello world", fontsize=12)
    if rotation:
        d[0].set_rotation(rotation)
    path = os.path.join(tempfile.mkdtemp(), "t.pdf")
    d.save(path)
    return path


class Scripts(unittest.TestCase):
    def test_inline_javascript_and_launch_actions_go(self):
        d = pymupdf.open()
        p = d.new_page()
        cat = d.pdf_catalog()
        d.xref_set_key(cat, "OpenAction", "<</S/JavaScript/JS(OPENJS)>>")
        d.xref_set_key(cat, "AA", "<</WC<</S/JavaScript/JS(DOCAAJS)>>>>")
        d.xref_set_key(p.xref, "AA", "<</O<</S/JavaScript/JS(PAGEAAJS)>>>>")
        p.insert_link({"kind": pymupdf.LINK_LAUNCH, "from": pymupdf.Rect(72, 200, 200, 214),
                       "file": "LAUNCHME.exe"})
        document_view.remove_scripts(d)
        data = d.tobytes(garbage=4)
        for word in (b"OPENJS", b"DOCAAJS", b"PAGEAAJS", b"LAUNCHME"):
            self.assertNotIn(word, data, word)


class View(unittest.TestCase):
    def view(self, rotation=0, pages=1):
        v = DocumentView(a_pdf(rotation, pages))
        self.addCleanup(v.close_doc)
        self.addCleanup(lambda: setattr(v, "dirty", False))
        return v


class Forms(View):
    def text_field(self, v, rect=(72, 72, 250, 92)):
        v.create_field(0, "f_text", P(*rect[:2]), P(*rect[2:]), False)
        return next(v.doc[0].widgets())

    def test_form_data_on_a_parent_field_is_cleared_and_looks_empty(self):
        v = self.view()
        w = self.text_field(v)
        v._set_field(0, w.xref, "SSN 123-45-6789")
        document_view.clear_form_data(v.doc)
        data = v.doc.tobytes(garbage=4, deflate=False)
        self.assertNotIn(b"123-45-6789", data)

    def test_clearing_a_field_by_typing_nothing_clears_its_look(self):
        v = self.view()
        w = self.text_field(v)
        v._set_field(0, w.xref, "visible words")
        v._set_field(0, w.xref, "")
        self.assertNotIn(b"visible words", v.doc.tobytes(garbage=4, deflate=False))

    def test_renaming_names_the_field(self):
        v = self.view()
        w = self.text_field(v)
        with mock.patch.object(QInputDialog, "getText", return_value=("applicant_name", True)):
            v.edit_field_properties(0, w.xref)
        self.assertEqual(next(v.doc[0].widgets()).field_name, "applicant_name")

    def test_a_blank_dropdown_isnt_an_answer(self):
        v = self.view()
        with mock.patch("kanzonas.dialogs.get_text", return_value=("One\nTwo", True)):
            v.create_field(0, "f_combo", P(72, 120), P(250, 140), False)
        self.assertFalse(v.form_filled())

    def test_a_field_on_a_turned_page_reads_upright(self):
        v = self.view(rotation=90)
        w = self.text_field(v)
        self.assertEqual(v.doc.xref_get_key(w.xref, "MK/R"), ("int", "90"))

    def test_fields_side_by_side_are_one_row(self):
        v = self.view()
        v.create_field(0, "f_text", P(300, 101), P(400, 121), False)
        v.create_field(0, "f_text", P(72, 100), P(200, 120), False)
        order = v.field_order()
        xs = [pymupdf.Rect(v.doc[0].load_widget(x).rect).x0 for _i, x in order]
        self.assertEqual(xs, sorted(xs))


class Fonts(View):
    def test_text_added_after_a_save_shows(self):
        from kanzonas import text_edit
        v = self.view()
        page = v.doc[0]
        text_edit.add_text(page, (72, 200), "αβγ", size=20)
        v._fonts_added = True
        out = os.path.join(tempfile.mkdtemp(), "s.pdf")
        v.save(out)
        page = v.doc[0]
        text_edit.add_text(page, (72, 300), "δεζ", size=20)
        pm = page.get_pixmap(clip=pymupdf.Rect(60, 270, 200, 310))
        ink = sum(1 for k in range(0, len(pm.samples), pm.n) if pm.samples[k] < 128)
        self.assertGreater(ink, 20)


class Opening(unittest.TestCase):
    def setUp(self):
        self.w = main_window.MainWindow()
        self.addCleanup(lambda: [setattr(x, "_close_confirmed", True) or x.close()
                                 for x in main_window.windows()])

    def test_save_asks_before_replacing_a_file_changed_elsewhere(self):
        path = a_pdf()
        self.w.open_file(path)
        v = self.w.view()
        time.sleep(0.05)
        d = pymupdf.open()
        d.new_page().insert_text((72, 72), "NEWER")
        d.save(path)
        os.utime(path, (time.time() + 5, time.time() + 5))
        with mock.patch.object(QMessageBox, "exec", return_value=0) as box:
            self.assertFalse(self.w.save())
        self.assertTrue(box.called)
        self.assertIn("NEWER", pymupdf.open(path)[0].get_text())
        v.dirty = False

    def test_a_file_open_in_another_window_isnt_opened_twice(self):
        path = a_pdf()
        self.w.open_file(path)
        other = self.w.detach_tab(0)
        self.w.open_file(path)
        self.assertEqual(self.w.tabs.count(), 0)
        self.assertEqual(other.tabs.count(), 1)

    def test_a_canceled_password_prompt_is_no_error(self):
        d = pymupdf.open()
        d.new_page()
        path = os.path.join(tempfile.mkdtemp(), "e.pdf")
        d.save(path, encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="u", owner_pw="o")
        with mock.patch.object(QInputDialog, "getText", return_value=("", False)), \
                mock.patch.object(QMessageBox, "critical") as crit:
            self.w.open_file(path)
        self.assertFalse(crit.called)
        self.assertEqual(self.w.tabs.count(), 0)


if __name__ == "__main__":
    unittest.main()
