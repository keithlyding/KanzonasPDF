"""Markups on layers (1.12, the owner, 11 Nov, from the Bluebeam comparison; issue #82 asked for
it too): a new layer for markups (listed in the Layers panel at once, the hidden ones staying
hidden), the layer new markups go on, a selection moved to a layer (one undo step), a markup on
a hidden layer neither drawn nor picked, restyled and copied markups keeping their layer, and
the Markups list's Layer column and filter. The layer is the PDF's own (/OC), so other
programs show and hide the markups with it.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_markup_layers
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

from kanzonas import annotations as A  # noqa: E402
from kanzonas import markup_layers as L  # noqa: E402
from kanzonas.document_view import DocumentView  # noqa: E402

R = pymupdf.Rect


def red(page, clip):
    pix = page.get_pixmap(clip=clip, annots=True)
    s = pix.samples
    n = pix.n
    return sum(1 for i in range(0, len(s), n) if s[i] > 200 and s[i + 1] < 80)


class Layers(unittest.TestCase):
    def setUp(self):
        d = pymupdf.open()
        d.new_page(width=612, height=792).insert_text((72, 72), "Plan", fontsize=12)
        path = os.path.join(tempfile.mkdtemp(), "plan.pdf")
        d.save(path)
        self.v = DocumentView(path)
        self.addCleanup(self.v.close_doc)

    def draw(self, rect=R(100, 100, 200, 180)):
        props = dict(A.DEFAULTS["rect"], stroke="#ff0000", fill="#ff0000")
        return self.v._create(0, {"kind": "rect", "rect": rect, "text": "", "props": props})

    def number_of(self, oc):
        return next(n for n, x in L.ui_layers(self.v.doc) if x == oc)

    def test_new_layer_and_new_markups_on_it(self):
        oc = self.v.new_markup_layer("Electrical")
        self.assertIn("Electrical", [c["text"] for c in self.v.layer_configs()])
        self.v.set_markup_layer(oc)
        x = self.draw()
        self.assertEqual(L.layer_of(self.v.doc, x), oc)
        self.v.set_markup_layer(None)
        y = self.draw(R(300, 100, 400, 180))
        self.assertIsNone(L.layer_of(self.v.doc, y))
        # text markups too (the word "Plan" highlighted)
        self.v.set_markup_layer(oc)
        before = {a.xref for a in self.v.doc[0].annots()}
        self.v.apply_text_tool(0, "highlight", pymupdf.Point(70, 64), pymupdf.Point(100, 70))
        made = [a.xref for a in self.v.doc[0].annots() if a.xref not in before]
        self.assertEqual(len(made), 1)
        self.assertEqual(L.layer_of(self.v.doc, made[0]), oc)

    def test_hidden_layer_hides_and_unpicks_its_markups(self):
        oc = self.v.new_markup_layer("Notes")
        self.v.set_markup_layer(oc)
        x = self.draw()
        inside = pymupdf.Point(150, 140)
        self.v.select_xref(0, x)
        self.assertEqual(self.v.annot_at(0, inside), x)
        self.assertGreater(red(self.v.doc[0], R(100, 100, 200, 180)), 100)
        self.v.set_layer(self.number_of(oc), False)
        self.assertIsNone(self.v.annot_at(0, inside))           # not picked
        self.assertIsNone(self.v.selection)                     # nor kept selected
        self.assertEqual(red(self.v.doc[0], R(100, 100, 200, 180)), 0)      # nor drawn
        self.v.set_layer(self.number_of(oc), True)
        self.assertEqual(self.v.annot_at(0, inside), x)

    def test_show_and_show_all_never_hide(self):
        # (1.12.1, random battery seed 9: the app passed PyMuPDF's 1, which switches a layer,
        # for "show": Show all hid the layers already shown, Show on a shown one hid it)
        a = self.v.new_markup_layer("A")
        b = self.v.new_markup_layer("B")
        self.v.set_layer(self.number_of(a), False)
        self.assertEqual(L.hidden(self.v.doc), {a})
        self.v.set_all_layers(True)
        self.assertEqual(L.hidden(self.v.doc), set())
        self.v.set_layer(self.number_of(b), True)               # (already shown: stays)
        self.assertEqual(L.hidden(self.v.doc), set())
        self.v.set_all_layers(False)
        self.assertEqual(L.hidden(self.v.doc), {a, b})
        self.v.set_layer(self.number_of(a), False)              # (already hidden: stays)
        self.assertEqual(L.hidden(self.v.doc), {a, b})

    def test_a_hidden_layer_stays_hidden_when_another_is_made(self):
        a = self.v.new_markup_layer("A")
        self.v.set_layer(self.number_of(a), False)
        b = self.v.new_markup_layer("B")
        self.assertEqual(L.hidden(self.v.doc), {a})
        self.assertEqual(len(self.v.layer_configs()), 2)
        self.assertNotEqual(a, b)

    def test_move_to_layer_one_undo_step_and_kept_through_restyle_and_copy(self):
        oc = self.v.new_markup_layer("Review")
        x = self.draw()
        self.v.select_xref(0, x)
        self.assertTrue(self.v.move_selection_to_layer(oc))
        self.assertEqual(L.layer_of(self.v.doc, x), oc)
        self.assertEqual(self.v.selection_layer(), oc)
        self.v.undo()
        self.assertIsNone(L.layer_of(self.v.doc, x))
        self.v.redo()
        self.assertEqual(L.layer_of(self.v.doc, x), oc)
        self.v.select_xref(0, x)
        self.v.update_selected_props({"width": 3.0})            # (written anew)
        restyled = self.v.selection[1]
        self.assertEqual(L.layer_of(self.v.doc, restyled), oc)
        self.v.duplicate_selected()
        copy = self.v.selection[1]
        self.assertNotEqual(copy, restyled)
        self.assertEqual(L.layer_of(self.v.doc, copy), oc)
        self.v.select_xref(0, copy)
        self.v.move_selection_to_layer(None)
        self.assertIsNone(L.layer_of(self.v.doc, copy))

    def test_saved_and_read_by_pymupdf_alone(self):
        oc = self.v.new_markup_layer("Notes")
        self.v.set_markup_layer(oc)
        x = self.draw()
        out = os.path.join(tempfile.mkdtemp(), "out.pdf")
        self.v.doc.save(out)
        d = pymupdf.open(out)
        self.assertEqual(d.xref_get_key(x, "OC"), ("xref", "%d 0 R" % oc))
        self.assertIn("Notes", [c["text"] for c in d.layer_ui_configs()])

    def test_new_layer_undone(self):
        self.v.new_markup_layer("Gone")
        self.v.undo()
        self.assertNotIn("Gone", [c["text"] for c in self.v.layer_configs()])
        self.assertEqual(L.layers(self.v.doc), [])


class MarkupsList(unittest.TestCase):
    def test_layer_column_and_filter(self):
        from kanzonas.markups_panel import COLUMNS, MarkupsPanel, collect
        d = pymupdf.open()
        d.new_page()
        path = os.path.join(tempfile.mkdtemp(), "p.pdf")
        d.save(path)
        v = DocumentView(path)
        self.addCleanup(v.close_doc)
        oc = v.new_markup_layer("Fire")
        props = dict(A.DEFAULTS["rect"])
        v.set_markup_layer(oc)
        on = v._create(0, {"kind": "rect", "rect": R(10, 10, 50, 50), "text": "a",
                           "props": props})
        v.set_markup_layer(None)
        off = v._create(0, {"kind": "rect", "rect": R(60, 10, 90, 50), "text": "b",
                            "props": props})
        rows = {r[1]: r for r in collect(v.doc)}
        self.assertEqual(rows[on][11], "Fire")
        self.assertEqual(rows[off][11], "")
        self.assertEqual(COLUMNS[8], "Layer")             # (Space after it: 1.12 too)
        panel = MarkupsPanel()
        self.addCleanup(panel.deleteLater)
        panel.refresh(v.doc)
        APP.processEvents()
        self.assertTrue(panel.layer_filter.isVisibleTo(panel))
        panel.layer_filter.setCurrentText("Fire")
        shown = [panel.table.item(r, 0).data(0x0100)[1] for r in range(panel.table.rowCount())
                 if not panel.table.isRowHidden(r)]
        self.assertEqual(shown, [on])


if __name__ == "__main__":
    unittest.main()
