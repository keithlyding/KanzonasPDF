"""The color picker (kanzonas/color_picker.py; the owner, 23 Nov 2026: "when making custom
colors, a recent or currently used colors section"): Qt's color dialog with a Recent row
and an In this document row of swatches, used everywhere the app asks for a color.

- Recent: newest first, each color once, at most 12, kept in the settings across a restart;
- In this document: the colors the document's markups use (line, fill, text), read from the
  markups only, without loading a page;
- a swatch clicked picks its color; every color picked goes to the front of Recent;
- every place that asked QColorDialog for a color asks the picker.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_color_picker
"""
import glob
import os
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402
from PySide6.QtCore import QRectF, QSettings, Qt  # noqa: E402
from PySide6.QtGui import QColor  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import (QApplication, QColorDialog, QDialog, QDialogButtonBox,  # noqa: E402
                               QLabel, QLineEdit)

APP = QApplication.instance() or QApplication([])

from kanzonas import annotations as A, color_picker as CP, paths  # noqa: E402
from tests.test_interaction_112 import Window  # noqa: E402

R = pymupdf.Rect


def ini():
    """A settings store of its own, in a temporary file (never the developer's settings)."""
    return QSettings(os.path.join(tempfile.mkdtemp(), "settings.ini"), QSettings.IniFormat)


class Recent(unittest.TestCase):
    def test_newest_first_each_color_once(self):
        s = ini()
        self.assertEqual(CP.recent_colors(s), [])
        for c in ("#ff0000", "#00ff00", "#0000ff", "#FF0000"):
            CP.remember(c, s)
        self.assertEqual(CP.recent_colors(s), ["#ff0000", "#0000ff", "#00ff00"])
        CP.remember(QColor(0, 255, 0), s)                     # (a QColor as well as text)
        self.assertEqual(CP.recent_colors(s), ["#00ff00", "#ff0000", "#0000ff"])

    def test_at_most_twelve_the_oldest_dropped(self):
        s = ini()
        colors = ["#%02x0000" % (i * 10) for i in range(20)]
        for c in colors:
            CP.remember(c, s)
        self.assertEqual(CP.RECENT_MAX, 12)
        self.assertEqual(CP.recent_colors(s), colors[::-1][:12])

    def test_an_invalid_color_is_not_kept(self):
        s = ini()
        CP.remember(QColor(), s)
        CP.remember("not a color", s)
        self.assertEqual(CP.recent_colors(s), [])

    def test_kept_across_a_restart(self):
        path = os.path.join(tempfile.mkdtemp(), "settings.ini")
        s = QSettings(path, QSettings.IniFormat)
        CP.remember("#123456", s)
        CP.remember("#abcdef", s)
        s.sync()
        del s
        again = QSettings(path, QSettings.IniFormat)       # (a new start reads the file)
        self.assertEqual(CP.recent_colors(again), ["#abcdef", "#123456"])

    def test_in_the_apps_settings_by_default(self):
        store = paths.settings()
        old = store.value(CP.RECENT_KEY)
        self.addCleanup(lambda: store.setValue(CP.RECENT_KEY, old) if old is not None
                        else store.remove(CP.RECENT_KEY))
        CP.remember("#13579b")
        self.assertEqual(CP.recent_colors(paths.settings())[0], "#13579b")

    def test_a_damaged_value_reads_as_empty_or_cleaned(self):
        s = ini()
        s.setValue(CP.RECENT_KEY, "[not json")
        self.assertEqual(CP.recent_colors(s), [])
        s.setValue(CP.RECENT_KEY, '["#AABBCC", 5, "red", "#aabbcc", "#010203"]')
        self.assertEqual(CP.recent_colors(s), ["#aabbcc", "#010203"])


def markups_doc():
    """A document with KanzonasPDF's markups, other programs' markups, a link and a form
    field, and the page's own drawing in a color no markup has."""
    doc = pymupdf.open()
    pg = doc.new_page()
    pg.draw_rect(R(300, 300, 400, 400), color=(0.5, 0, 0.5), fill=(0, 0.5, 0.5))
    for i in range(3):
        A.write(pg, {"kind": "rect", "rect": R(10, 10 + 30 * i, 60, 30 + 30 * i),
                     "props": dict(A.DEFAULTS["rect"], stroke="#ff0000", fill="#0000ff")})
    A.write(pg, {"kind": "textbox", "rect": R(100, 100, 250, 140), "text": "note",
                 "props": dict(A.DEFAULTS["textbox"], stroke="#ff0000",
                               text_color="#008000")})
    pg2 = doc.new_page()
    hl = pg2.add_highlight_annot(R(50, 50, 150, 70))           # (another program's: no KZProps)
    hl.set_colors(stroke=(1, 1, 0))
    hl.update()
    ft = pg2.add_freetext_annot(R(50, 100, 250, 140), "text", text_color=(0, 0, 1))
    ft.update()
    w = pymupdf.Widget()
    w.field_type = pymupdf.PDF_WIDGET_TYPE_TEXT
    w.field_name = "f"
    w.rect = R(10, 400, 100, 420)
    w.border_color = (0.9, 0.1, 0.1)
    w.text_color = (0.1, 0.9, 0.1)
    pg2.add_widget(w)
    del pg, pg2, hl, ft
    # a link with a border color (not a markup)
    link = doc.get_new_xref()
    doc.update_object(link, "<< /Type /Annot /Subtype /Link /Rect [10 300 100 320] "
                            "/C [0.2 0.4 0.6] /Border [0 0 1] >>")
    px = doc.page_xref(1)
    refs = doc.xref_get_key(px, "Annots")[1]
    doc.xref_set_key(px, "Annots", refs.rstrip("]") + " %d 0 R]" % link)
    return doc


class InThisDocument(unittest.TestCase):
    def test_the_markups_colors_most_used_first(self):
        doc = markups_doc()
        got = CP.document_colors(doc)
        # red: 3 boxes and the text box's border; blue: 3 fills and the other text's color
        self.assertEqual(got[:2], ["#ff0000", "#0000ff"])
        self.assertEqual(set(got), {"#ff0000", "#0000ff", "#008000", "#ffff00"})

    def test_not_the_pages_own_drawing_links_or_form_fields(self):
        got = CP.document_colors(markups_doc())
        for c in ("#800080", "#008080", "#336699", "#e61a1a", "#1ae61a"):
            self.assertNotIn(c, got)

    def test_read_without_loading_a_page(self):
        doc = markups_doc()
        want = CP.document_colors(doc)
        with mock.patch.object(pymupdf.Document, "load_page",
                               side_effect=AssertionError("a page loaded")):
            self.assertEqual(CP.document_colors(doc), want)

    def test_a_markup_list_kept_in_an_object_of_its_own(self):
        doc = pymupdf.open()
        pg = doc.new_page()
        a = pg.add_rect_annot(R(10, 10, 50, 50))
        a.set_colors(stroke=(0, 0.5, 0))
        a.update()
        px = doc.page_xref(0)
        refs = doc.xref_get_key(px, "Annots")[1]
        n = doc.get_new_xref()
        doc.update_object(n, refs)
        doc.xref_set_key(px, "Annots", "%d 0 R" % n)
        self.assertEqual(doc.xref_get_key(px, "Annots")[0], "xref")
        self.assertEqual(CP.document_colors(doc), ["#008000"])

    def test_gray_and_cmyk_colors(self):
        doc = pymupdf.open()
        pg = doc.new_page()
        a = pg.add_rect_annot(R(10, 10, 50, 50))
        doc.xref_set_key(a.xref, "C", "[0.5]")
        doc.xref_set_key(a.xref, "IC", "[1 0 0 0]")
        del a
        self.assertEqual(set(CP.document_colors(doc)), {"#808080", "#00ffff"})

    def test_none_without_a_document(self):
        self.assertEqual(CP.document_colors(None), [])
        doc = markups_doc()
        doc.close()
        self.assertEqual(CP.document_colors(doc), [])
        self.assertEqual(CP.document_colors(pymupdf.open()), [])     # (no markups)

    def test_at_most_two_rows(self):
        doc = pymupdf.open()
        pg = doc.new_page()
        for i in range(30):
            a = pg.add_rect_annot(R(10, 10, 50, 50))
            doc.xref_set_key(a.xref, "C", "[%g 0 0]" % (i / 30))
        self.assertEqual(len(CP.document_colors(doc)), CP.DOCUMENT_MAX)


class Dialog(unittest.TestCase):
    def picker(self, **kw):
        kw.setdefault("recent", ["#ff0000", "#00ff00"])
        kw.setdefault("in_document", ["#123456", "#abcdef"])
        d = CP.ColorPicker(QColor("#336699"), None, "Line color", **kw)
        self.addCleanup(d.deleteLater)
        return d

    def test_a_swatch_click_picks_its_color(self):
        d = self.picker()
        self.assertEqual([b.toolTip() for b in d.recent], ["#ff0000", "#00ff00"])
        self.assertEqual([b.toolTip() for b in d.in_document], ["#123456", "#abcdef"])
        d.show()
        QTest.mouseClick(d.recent[1], Qt.LeftButton)
        self.assertEqual(d.result(), QDialog.Accepted)
        self.assertEqual(d.color().name(), "#00ff00")
        d = self.picker()
        d.in_document[0].click()
        self.assertEqual(d.result(), QDialog.Accepted)
        self.assertEqual(d.color().name(), "#123456")

    def test_ok_gives_the_color_set_in_qts_dialog_cancel_none(self):
        d = self.picker()
        self.assertEqual(d.dialog.currentColor().name(), "#336699")     # (the start color)
        d.dialog.setCurrentColor(QColor("#445566"))
        d.findChild(QDialogButtonBox).button(QDialogButtonBox.Ok).click()
        self.assertEqual(d.color().name(), "#445566")
        d = self.picker()
        d.findChild(QDialogButtonBox).button(QDialogButtonBox.Cancel).click()
        self.assertFalse(d.color().isValid())

    def test_esc_in_qts_dialog_cancels_the_picker(self):
        d = self.picker()
        d.show()
        APP.processEvents()
        field = d.dialog.findChildren(QLineEdit)[0]
        field.setFocus()
        QTest.keyClick(field, Qt.Key_Escape)
        self.assertFalse(d.isVisible())
        self.assertEqual(d.result(), QDialog.Rejected)

    def test_enter_in_qts_dialog_is_ok(self):
        d = self.picker()
        d.show()
        APP.processEvents()
        field = next(f for f in d.dialog.findChildren(QLineEdit) if f.text() == "#336699")
        field.setFocus()
        field.selectAll()
        QTest.keyClicks(field, "#ff8800")
        QTest.keyClick(field, Qt.Key_Return)
        self.assertFalse(d.isVisible())
        self.assertEqual(d.result(), QDialog.Accepted)
        self.assertEqual(d.color().name(), "#ff8800")

    def test_qts_own_dialog_on_every_system(self):
        d = self.picker()
        self.assertTrue(d.dialog.testOption(QColorDialog.DontUseNativeDialog))
        self.assertTrue(d.dialog.testOption(QColorDialog.NoButtons))
        d.show()
        APP.processEvents()
        self.assertTrue(d.dialog.isVisible())
        self.assertIs(d.dialog.window(), d)                 # (inside the picker, not its own)

    def test_rows_only_with_colors(self):
        d = self.picker(recent=[], in_document=[])
        self.assertEqual((d.recent, d.in_document), ([], []))
        texts = [lb.text() for lb in d.findChildren(QLabel)]
        self.assertNotIn("Recent", texts)
        self.assertNotIn("In this document", texts)
        d = self.picker()
        texts = [lb.text() for lb in d.findChildren(QLabel)]
        self.assertIn("Recent", texts)
        self.assertIn("In this document", texts)


class GetColor(unittest.TestCase):
    def setUp(self):
        self.s = ini()
        p = mock.patch.object(CP, "_settings", lambda settings: self.s)
        p.start()
        self.addCleanup(p.stop)

    def test_a_swatch_picked_goes_to_the_front_of_recent(self):
        for c in ("#111111", "#222222", "#333333"):
            CP.remember(c)
        with mock.patch.object(CP.ColorPicker, "exec",
                               lambda d: (d.recent[2].click(), d.result())[1]):
            got = CP.get_color(QColor("#000000"), None, "Fill color")
        self.assertEqual(got.name(), "#111111")
        self.assertEqual(CP.recent_colors(), ["#111111", "#333333", "#222222"])

    def test_a_color_from_qts_dialog_too_and_cancel_keeps_none(self):
        def ok(d):
            d.dialog.setCurrentColor(QColor("#a1b2c3"))
            d.accept()
            return d.result()
        with mock.patch.object(CP.ColorPicker, "exec", ok):
            self.assertEqual(CP.get_color("#000000").name(), "#a1b2c3")
        self.assertEqual(CP.recent_colors(), ["#a1b2c3"])

        def cancel(d):
            d.reject()
            return d.result()
        with mock.patch.object(CP.ColorPicker, "exec", cancel):
            self.assertFalse(CP.get_color("#000000").isValid())
        self.assertEqual(CP.recent_colors(), ["#a1b2c3"])

    def test_the_documents_colors_offered(self):
        doc = markups_doc()
        seen = {}

        def look(d):
            seen["doc"] = [b.toolTip() for b in d.in_document]
            d.reject()
            return d.result()
        with mock.patch.object(CP.ColorPicker, "exec", look):
            CP.get_color("#000000", None, "", doc=doc)
        self.assertEqual(seen["doc"], CP.document_colors(doc))


class EveryCallSite(unittest.TestCase):
    """Every place the app asks for a color goes through the picker."""

    def test_no_other_color_dialog_in_the_program(self):
        found = []
        for path in glob.glob(os.path.join(ROOT, "kanzonas", "**", "*.py"), recursive=True):
            if os.path.basename(path) == "color_picker.py":
                continue
            with open(path, encoding="utf-8") as f:
                if "QColorDialog" in f.read():
                    found.append(os.path.relpath(path, ROOT))
        self.assertEqual(found, [])

    def picked(self, color="#2468ac"):
        return mock.patch.object(CP, "get_color", return_value=QColor(color))

    def test_properties_color_buttons(self):
        from kanzonas.properties import ColorButton
        b = ColorButton()
        b.set_color("#ffffff")
        with self.picked() as got:
            b.click()
        self.assertEqual(got.call_count, 1)
        self.assertEqual(b.color(), "#2468ac")

    def test_bookmark_color(self):
        from kanzonas.bookmarks_panel import BookmarksPanel
        p = BookmarksPanel()
        self.addCleanup(p.deleteLater)
        p.set_toc([[1, "Chapter", 1]])
        p.tree.setCurrentItem(p.tree.topLevelItem(0))
        with self.picked("#ff0000") as got:
            p.pick_color()
        self.assertEqual(got.call_count, 1)
        self.assertEqual(tuple(p.toc[0][3]["color"]), (1.0, 0.0, 0.0))

    def view(self):
        from kanzonas.document_view import DocumentView
        d = markups_doc()
        path = os.path.join(tempfile.mkdtemp(), "t.pdf")
        d.save(path)
        v = DocumentView(path)
        v.resize(800, 600)
        v.show()
        APP.processEvents()
        self.addCleanup(v.close_doc)
        return v

    def test_edit_objects_colors(self):
        v = self.view()
        with self.picked() as got, mock.patch.object(v, "recolor_objects") as rec:
            v.obj_sel = (0, [])
            v.pick_object_color("stroke")
        self.assertEqual(got.call_count, 1)
        self.assertIs(got.call_args[1]["doc"], v.doc)
        rec.assert_called_once()

    def test_the_text_editing_box(self):
        from kanzonas.inline_editor import InlineEditor
        v = self.view()
        ed = InlineEditor(v.pages[0], QRectF(10, 10, 100, 20), "abc", "sans", 14)
        self.addCleanup(ed.cancel)
        ed.text.selectAll()
        with self.picked("#00ff00") as got:
            ed.pick_color()
        self.assertEqual(got.call_count, 1)
        self.assertEqual(ed.shown_format()["text_color"], "#00ff00")
        self.assertIs(CP.open_document(ed), v.doc)      # (its document's colors offered)



class MainWindowPanels(Window):
    def test_the_panels_find_the_open_document(self):
        w, v = self.open()
        self.assertIs(CP.open_document(w.props), v.doc)
        self.assertIs(CP.open_document(w.bookmarks), v.doc)
        self.assertIs(CP.open_document(w), v.doc)


if __name__ == "__main__":
    unittest.main()
