"""1.6.1: what made editing slow on a page with many markups, made fast, and still right.
PyMuPDF's markup naming (each new markup's name checked against every other's) and its
delete (every markup walked for replies, once per delete) have stand-ins (pdf_speed.py);
Delete checks locks in one walk; a repaint doesn't read the selected markups again; the live
CAD highlight takes the markups one at a time.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_speed_161
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

from kanzonas import annotations, pdf_speed  # noqa: E402
from kanzonas.document_view import DocumentView  # noqa: E402
from kanzonas.page_objects import Box  # noqa: E402


def boxes(page, n, y=10):
    return [page.add_rect_annot(pymupdf.Rect(10 + 25 * i, y, 30 + 25 * i, y + 20)).xref
            for i in range(n)]


class Names(unittest.TestCase):
    def test_the_stand_in_is_in_use(self):
        self.assertTrue(pdf_speed.applied)
        self.assertIs(pymupdf.JM_add_annot_id, pdf_speed._annot_id)

    def test_every_markup_gets_its_own_name_with_pymupdfs_prefix(self):
        d = pymupdf.open()
        page = d.new_page()
        xs = boxes(page, 20)
        xs.append(page.add_text_annot((300, 300), "note").xref)
        names = [d.xref_get_key(x, "NM")[1] for x in xs]
        self.assertEqual(len(set(names)), len(names))
        self.assertTrue(all(n.startswith(pymupdf.JM_annot_id_stem + "-") for n in names))

    def test_names_differ_from_ones_already_in_a_file(self):
        d = pymupdf.open()
        page = d.new_page()
        old = boxes(page, 3)
        d.xref_set_key(old[0], "NM", "(fitz-A0)")      # as an older PyMuPDF named them
        new = boxes(page, 3, y=60)
        names = [d.xref_get_key(x, "NM")[1] for x in old + new]
        self.assertEqual(len(set(names)), 6)


class DeleteMany(unittest.TestCase):
    def setUp(self):
        self.d = pymupdf.open()
        self.page = self.d.new_page()

    def left(self):
        return sorted(x for x, *_ in self.page.annot_xrefs())

    @staticmethod
    def thread_page():
        """A page of 8 boxes; box 0 and box 7 have a reply (a note: it has a pop-up)."""
        d = pymupdf.open()
        page = d.new_page()
        xs = boxes(page, 8)
        for k in (0, 7):
            r = page.add_text_annot((15 + 25 * k, 15), "reply").xref
            d.xref_set_key(r, "IRT", f"{xs[k]} 0 R")
        return d, page, xs

    def test_leaves_the_page_as_pymupdfs_own_delete_does(self):
        d1, p1, xs = self.thread_page()
        for x in xs[:5]:
            p1.delete_annot(p1.load_annot(x))
        d2, p2, xs2 = self.thread_page()
        pdf_speed.delete_many(p2, xs2[:5])
        self.assertEqual(sorted(x for x, *_ in p2.annot_xrefs()),
                         sorted(x for x, *_ in p1.annot_xrefs()))
        kinds = sorted(a.type[1] for a in p2.annots())
        self.assertEqual(kinds, ["Square"] * 3 + ["Text"])     # box 0's reply went with it

    def test_gone_ones_are_skipped_and_the_page_still_reads(self):
        xs = boxes(self.page, 6)
        pdf_speed.delete_many(self.page, xs[:3] + [99999])
        self.assertEqual(self.left(), sorted(xs[3:]))
        self.assertEqual(len(list(self.page.annots())), 3)

    def test_an_emptied_page_has_no_annots_entry(self):
        xs = boxes(self.page, 6)
        pdf_speed.delete_many(self.page, xs)
        self.assertEqual(self.d.xref_get_key(self.page.xref, "Annots")[0], "null")

    def test_a_few_go_pymupdfs_own_way(self):
        xs = boxes(self.page, 3)
        pdf_speed.delete_many(self.page, xs[:2])
        self.assertEqual(self.left(), [xs[2]])


class View(unittest.TestCase):
    def setUp(self):
        d = pymupdf.open()
        page = d.new_page(width=600, height=400)
        page.draw_line((50, 300), (550, 300))
        page.insert_text((60, 350), "PANEL A", fontsize=10)
        boxes(page, 12)
        path = os.path.join(tempfile.mkdtemp(), "v.pdf")
        d.save(path)
        self.v = DocumentView(path)
        self.addCleanup(self.v.close_doc)
        self.addCleanup(lambda: setattr(self.v, "dirty", False))

    def xrefs(self):
        page = self.v.doc[0]
        return [a.xref for a in annotations.each_annot(page)]

    def test_delete_leaves_a_locked_markup_and_undo_brings_all_back(self):
        xs = self.xrefs()
        page = self.v.doc[0]
        a = page.load_annot(xs[3])
        a.set_flags(pymupdf.PDF_ANNOT_IS_LOCKED)
        a.update()
        del a, page
        self.v._set_selection(0, xs)
        self.v.delete_selected()
        self.assertEqual(self.xrefs(), [xs[3]])
        self.v.undo()
        self.assertEqual(len(self.xrefs()), 12)

    def test_moving_many_keeps_their_stacking_order(self):
        self.v._set_selection(0, self.xrefs())
        page = self.v.doc[0]
        before = [round(a.rect.x0) for a in annotations.each_annot(page)]
        del page
        self.v.cad_apply("Moved", pymupdf.Matrix(1, 0, 0, 1, 0, 50))
        page = self.v.doc[0]
        after = [(round(a.rect.x0), round(a.rect.y0)) for a in annotations.each_annot(page)]
        self.assertEqual(len(after), len(before))       # (each box grows by its border)
        self.assertTrue(all(abs(a - b) <= 2 for (a, _y), b in zip(after, before)))
        self.assertTrue(all(y >= 55 for _x, y in after))

    def test_a_repaint_sees_an_edit_at_once(self):
        xs = self.xrefs()
        self.v._set_selection(0, xs[:2])
        first = self.v.selected_models_to_paint()
        self.assertIs(self.v.selected_models_to_paint(), first)     # (not read again)
        self.v.commit_models(0, [(xs[0], annotations.moved(first[0][1], pymupdf.Point(0, 40))),
                                 (xs[1], first[1][1])])
        now = self.v.selected_models_to_paint()
        self.assertIsNot(now, first)
        self.assertEqual(len(now), len(self.v.selected_xrefs()))
        self.v.undo()
        self.assertIsNot(self.v.selected_models_to_paint(), now)

    def test_the_live_highlight_takes_markups_one_step_each(self):
        self.v.tool = "editobjects"
        steps = list(self.v.cad_preview_steps(0, Box(pymupdf.Rect(0, 0, 600, 400))))
        marked = [lines for lines, _r in steps[:12]]
        self.assertTrue(all(len(lines) == 1 for lines in marked))
        self.v.tool = "select"                  # (Select: markups, else the text)
        steps = list(self.v.cad_preview_steps(0, Box(pymupdf.Rect(50, 330, 200, 360))))
        self.assertTrue(any(rects for _l, rects in steps))


if __name__ == "__main__":
    unittest.main()
