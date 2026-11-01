"""What the 1.6.1 break-it battery found, fixed.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_battery_161
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

from kanzonas import annotations  # noqa: E402
from kanzonas.document_view import DocumentView  # noqa: E402

P = pymupdf.Point


class SplitView(unittest.TestCase):
    def test_the_split_view_follows_markup_edits_in_the_main_view(self):
        d = pymupdf.open()
        d.new_page().insert_text((72, 72), "Some words on the page")
        path = os.path.join(tempfile.mkdtemp(), "m.pdf")
        d.save(path)
        v = DocumentView(path)
        self.addCleanup(v.close_doc)
        self.addCleanup(lambda: setattr(v, "dirty", False))

        def add():
            a = v.doc[0].add_text_annot((400, 400), "first content")
            a.update()
        v.modify(add, [0])
        m = DocumentView.mirror(v)
        self.addCleanup(m.deleteLater)
        here, there = P(405, 405), P(445, 405)
        self.assertEqual(m.annot_tooltip(0, here), v.annot_tooltip(0, here))
        v._set_selection(0, [v.annot_at(0, here)])
        x, model = v.selected_models()[0]
        model = dict(model, text="second content")
        v.commit_models(0, [(x, model)])
        self.assertIn("second content", m.annot_tooltip(0, here))   # (it read the old text)
        v._set_selection(0, [v.annot_at(0, here)])
        v.nudge(40, 0, 1)
        self.assertEqual(m.annot_tooltip(0, here), "")              # (it showed it here still)
        self.assertEqual(m.annot_tooltip(0, there), v.annot_tooltip(0, there))
        v.undo()
        self.assertEqual(m.annot_tooltip(0, here), v.annot_tooltip(0, here))


class Markups(unittest.TestCase):
    def view(self, build):
        d = pymupdf.open()
        p = d.new_page(width=600, height=800)
        p.insert_text((60, 100), "A line of words with a note on it", fontsize=12)
        build(d, p)
        path = os.path.join(tempfile.mkdtemp(), "m.pdf")
        d.save(path)
        v = DocumentView(path)
        self.addCleanup(v.close_doc)
        self.addCleanup(lambda: setattr(v, "dirty", False))
        return v

    def annots(self, v):
        page = v.doc[0]
        return {a.xref: (a.type[1], pymupdf.Rect(a.rect), a.info.get("content"))
                for a in page.annots()}

    def test_a_box_held_by_references_moves_and_keeps_its_box(self):
        # (a legal PDF: the numbers of /Rect are objects of their own; moving it in place
        # turned the references into others, and the markup vanished)
        made = {}

        def build(d, p):
            nums = []
            for val in (100, 500, 200, 600):
                n = d.get_new_xref()
                d.update_object(n, str(val))
                nums.append(n)
            ap = d.get_new_xref()
            d.update_object(ap, "<</Type/XObject/Subtype/Form/BBox[0 0 100 100]/Length 0>>")
            d.update_stream(ap, b"1 0 0 RG 3 w 2 2 96 96 re S")
            x = d.get_new_xref()
            d.update_object(x, "<</Type/Annot/Subtype/Square/Rect[%d 0 R %d 0 R %d 0 R %d 0 R]"
                            "/C[1 0 0]/AP<</N %d 0 R>>/F 4>>" % (*nums, ap))
            d.xref_set_key(p.xref, "Annots", "[%d 0 R]" % x)
            made["x"] = x
        v = self.view(build)
        before = self.annots(v)[made["x"]][1]
        v._set_selection(0, [made["x"]])
        v.cad_apply("Moved", pymupdf.Matrix(1, 0, 0, 1, 10, 20))
        (_kind, after, _c), = self.annots(v).values()
        self.assertAlmostEqual(after.width, before.width, delta=3)
        self.assertAlmostEqual(after.x0 - before.x0, 10, delta=2)
        self.assertAlmostEqual(after.y0 - before.y0, 20, delta=2)

    def test_a_restyled_note_keeps_its_replies(self):
        made = {}

        def build(d, p):
            made["note"] = p.add_text_annot((300, 300), "the note").xref
            r = p.add_text_annot((330, 300), "a reply")
            made["reply"] = r.xref
            d.xref_set_key(r.xref, "IRT", "%d 0 R" % made["note"])
        v = self.view(build)
        v._set_selection(0, [made["note"]])
        (x, m), = v.selected_models()
        m = annotations.copy(m)
        m["props"]["stroke"] = "#00aa00"
        v.commit_models(0, [(x, m)])
        now = self.annots(v)
        self.assertIn(made["reply"], now)                       # (it was deleted with the note)
        kind, val = v.doc.xref_get_key(made["reply"], "IRT")
        self.assertEqual(kind, "xref")
        self.assertIn(int(val.split()[0]), now)                 # (it answers the new note)
        self.assertEqual(now[int(val.split()[0])][2], "the note")

    def test_locking_a_measurement_keeps_its_label(self):
        def build(d, p):
            annotations.write(p, {"kind": "m_length", "rect": pymupdf.Rect(),
                                  "props": dict(annotations.DEFAULTS.get("m_length", {})),
                                  "points": [P(100, 400), P(400, 400)]})
        v = self.view(build)
        before = v.doc[0].get_pixmap(dpi=72).samples
        x, = self.annots(v)
        v.set_object_flags(0, [x], locked=True)
        self.assertEqual(v.doc[0].get_pixmap(dpi=72).samples, before)
        self.assertTrue(v.markup_locked(0, x))
        v.set_object_flags(0, [x], hidden=True)
        self.assertNotEqual(v.doc[0].get_pixmap(dpi=72).samples, before)   # (hidden: not drawn)

    def test_edit_text_moves_a_line_carrying_a_note_with_replies(self):
        made = {}

        def build(d, p):
            made["note"] = p.add_text_annot((62, 88), "on the line").xref
            r = p.add_text_annot((400, 400), "a reply")
            d.xref_set_key(r.xref, "IRT", "%d 0 R" % made["note"])
        v = self.view(build)
        y0 = self.annots(v)[made["note"]][1].y0
        v.move_text_line(0, P(70, 95), (0, 40))
        now = self.annots(v)
        self.assertIn(made["note"], now)                        # (moved where it is)
        self.assertAlmostEqual(now[made["note"]][1].y0 - y0, 40, delta=0.5)
        self.assertEqual(len(now), 2)                           # (the note and its reply)


class Pages(unittest.TestCase):
    def view(self, pages=3):
        d = pymupdf.open()
        for i in range(pages):
            pg = d.new_page()
            pg.insert_text((72, 72), "page %d" % (i + 1))
            w = pymupdf.Widget()
            w.field_type = pymupdf.PDF_WIDGET_TYPE_TEXT
            w.field_name = "f%d" % i
            w.rect = pymupdf.Rect(72, 100, 300, 120)
            pg.add_widget(w)
        path = os.path.join(tempfile.mkdtemp(), "p.pdf")
        d.save(path)
        v = DocumentView(path)
        v.resize(800, 600)
        v.show()
        APP.processEvents()
        self.addCleanup(v.close_doc)
        self.addCleanup(lambda: setattr(v, "dirty", False))
        return v

    def values(self, v):
        return {w.field_name: w.field_value for pg in v.doc for w in pg.widgets()}

    def typing(self, v, index, text):
        from PySide6.QtWidgets import QLineEdit
        page = v.doc[index]
        xref = next(page.widgets()).xref
        del page
        v._edit_text_field(index, xref)
        ed = v.pages[index].findChildren(QLineEdit)[-1]
        ed.setText(text)                    # (typed, not yet confirmed)

    def test_a_value_being_typed_survives_turning_its_page(self):
        v = self.view()
        self.typing(v, 1, "typed before the turn")
        v.rotate_page(1, 90)
        APP.processEvents()
        self.assertEqual(self.values(v)["f1"], "typed before the turn")

    def test_a_value_being_typed_survives_deleting_an_earlier_page(self):
        v = self.view()
        self.typing(v, 2, "typed, then page 1 deleted")
        self.assertTrue(v.delete_pages([0]))
        APP.processEvents()
        self.assertEqual(self.values(v)["f2"], "typed, then page 1 deleted")

    def test_delete_pages_says_so_when_it_was_refused(self):
        from unittest import mock
        v = self.view()
        with mock.patch.object(v, "allowed", return_value=False), \
                mock.patch("kanzonas.document_view.QMessageBox.information"):
            self.assertFalse(v.delete_pages([0]))
        self.assertEqual(v.doc.page_count, 3)


if __name__ == "__main__":
    unittest.main()
