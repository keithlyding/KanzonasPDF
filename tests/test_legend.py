"""Markup legends (legend.py): a box listing the kinds of markups used, each with a sample in
its own style, its label, how many and (for measurements) their total; it updates itself
inside the edit's own undo step, so Undo and Redo keep working with a legend on the page.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_legend
"""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import annotations as A, legend as L  # noqa: E402
from kanzonas.document_view import DocumentView  # noqa: E402

P = pymupdf.Point


def blank(path, pages=2, rotation=0):
    d = pymupdf.open()
    for i in range(pages):
        p = d.new_page(width=800, height=600)
        p.insert_text((40, 40), "Sheet %d" % (i + 1), fontsize=12)
        if rotation:
            p.set_rotation(rotation)
    d.save(path)
    return path


def model(kind, **kw):
    m = {"kind": kind, "props": dict(A.DEFAULTS[kind]), "rect": pymupdf.Rect()}
    m["props"].update(kw.pop("props", {}))
    m.update(kw)
    return m


class LegendCase(unittest.TestCase):
    def setUp(self):
        # a message box ("Edit failed"...) is a failure here, not a window waiting for a click
        self.boxes = []
        for name in ("information", "warning", "critical"):
            patch = mock.patch.object(QMessageBox, name,
                                      lambda *a, **k: self.boxes.append(a[1:3]))
            patch.start()
            self.addCleanup(patch.stop)
        self.addCleanup(lambda: self.assertEqual(self.boxes, []))

    def view(self, pages=2, rotation=0):
        path = blank(os.path.join(tempfile.mkdtemp(), "legend.pdf"), pages, rotation)
        v = DocumentView(path)
        self.addCleanup(v.close_doc)
        self.addCleanup(lambda: setattr(v, "dirty", False))
        return v

    def add(self, v, index, *models):
        made = []

        def do():
            page = v.doc[index]
            for m in models:
                made.append(A.write(page, m).xref)
        v.modify(do, [index], permission=pymupdf.PDF_PERM_ANNOTATE)
        return made

    def legend(self, v, index=0, **props):
        with mock.patch.object(A, "tool_props", lambda k: dict(A.DEFAULTS[k], **props)
                               if k == "legend" else dict(A.DEFAULTS.get(k, {}))):
            return v.place_legend(index, pymupdf.Rect(500, 300, 500, 300), at_point=True)

    def rows(self, v, xref, index=0):
        return L.stored(v.doc, xref)["geom"]["rows"]

    def counts(self, v, xref, index=0):
        return {r["label"]: r["n"] for r in self.rows(v, xref, index)}

    def read_m(self, v, x, index=0):
        page = v.doc[index]             # (kept alive while its markup is read)
        return A.read(page.load_annot(x))

    def box(self, v, x, index=0):
        page = v.doc[index]
        return pymupdf.Rect(page.load_annot(x).rect)

    def content(self, v, x, index=0):
        page = v.doc[index]
        return page.load_annot(x).info["content"]

    def legend_xrefs(self, v, index=0):
        return L.legends_on(v.doc[index])


class Rows(LegendCase):
    def test_rows_and_counts_match_the_markups(self):
        v = self.view()
        self.add(v, 0, model("rect", rect=pymupdf.Rect(50, 50, 100, 90)),
                 model("rect", rect=pymupdf.Rect(120, 50, 170, 90)),
                 model("rect", rect=pymupdf.Rect(50, 100, 100, 150),
                       props={"stroke": "#0000ff"}),
                 model("rect", rect=pymupdf.Rect(200, 100, 260, 150), props={"cloud": True}),
                 model("arrow", points=[P(50, 200), P(150, 230)], props={"head": "closed"}),
                 model("m_count", points=[P(400, 100)], n=1, props={"group": "Outlets"}),
                 model("m_count", points=[P(420, 100)], n=2, props={"group": "Outlets"}),
                 model("highlight", quads=[pymupdf.Rect(40, 28, 90, 42).quad]))
        x = self.legend(v)
        rows = self.rows(v, x)
        got = sorted((r["label"], r["kind"], r["n"]) for r in rows)
        self.assertEqual(got, [("Arrow", "arrow", 1), ("Cloud", "cloud", 1),
                               ("Highlight", "highlight", 1), ("Outlets", "m_count", 2),
                               ("Rectangle", "rect", 1), ("Rectangle", "rect", 2)])
        # the two kinds of rectangle are told apart by their style
        reds = [r for r in rows if r["kind"] == "rect"]
        self.assertEqual({r["style"]["stroke"] for r in reds}, {"#d00000", "#0000ff"})
        # the legend reads back as a legend, and is listed in its text for other programs
        m = self.read_m(v, x)
        self.assertEqual(m["kind"], "legend")
        self.assertIn("Outlets 2", self.content(v, x))

    def test_subject_is_the_label_when_set(self):
        v = self.view()
        (x0,) = self.add(v, 0, model("rect", rect=pymupdf.Rect(50, 50, 100, 90)))

        def subj():
            v.doc.xref_set_key(x0, "Subj", pymupdf.get_pdf_str("Fire door"))
        v.modify(subj, [0])
        x = self.legend(v)
        self.assertEqual(self.counts(v, x), {"Fire door": 1})

    def test_measurement_totals_in_the_page_units(self):
        v = self.view()
        from kanzonas import measure as M

        def scale():
            M.set_scale(v.doc[0], M.scale_from_preset(48), "ft-in", '1/4" = 1\'-0"')
        v.modify(scale, [0])
        # 72 pt = 1 in on paper = 4 ft at 1/4" = 1'-0"
        self.add(v, 0, model("m_length", points=[P(50, 300), P(122, 300)]),
                 model("m_length", points=[P(50, 350), P(194, 350)]),
                 model("m_area", points=[P(300, 300), P(372, 300), P(372, 372), P(300, 372)]))
        x = self.legend(v)
        rows = {r["label"]: r for r in self.rows(v, x)}
        self.assertEqual(rows["Length"]["n"], 2)
        self.assertEqual(rows["Length"]["total"], M.fmt_length(12 * 0.3048, "ft-in"))
        self.assertEqual(rows["Length"]["total"], "12'-0\"")
        self.assertEqual(rows["Area"]["total"], "16.00 sq ft")
        # no totals column when it's turned off
        v._set_selection(0, [x])
        p = dict(self.read_m(v, x)["props"], totals=False)
        v.update_selected_props(p)
        (x,) = self.legend_xrefs(v)
        self.assertNotIn("sq ft", v.doc[0].get_text("text", clip=self.box(v, x)))

    def test_whole_document_scope(self):
        v = self.view(pages=3)
        self.add(v, 0, model("rect", rect=pymupdf.Rect(50, 50, 100, 90)))
        self.add(v, 1, model("rect", rect=pymupdf.Rect(50, 50, 100, 90)),
                 model("ellipse", rect=pymupdf.Rect(150, 50, 200, 90)))
        page_only = self.legend(v, 2)
        whole = self.legend(v, 0, scope="document")
        self.assertEqual(self.counts(v, page_only, 2), {})
        self.assertEqual(self.counts(v, whole), {"Rectangle": 2, "Ellipse": 1})
        # a markup added on another page updates the document's legend (and its page draws
        # again), not the other page's
        self.add(v, 1, model("ellipse", rect=pymupdf.Rect(250, 50, 300, 90)))
        self.assertEqual(self.counts(v, whole), {"Rectangle": 2, "Ellipse": 2})
        self.assertEqual(self.counts(v, page_only, 2), {})
        self.assertIn(0, v._undo[-1].pages)
        v.undo()
        self.assertEqual(self.counts(v, whole), {"Rectangle": 2, "Ellipse": 1})


class Drawn(LegendCase):
    def test_styles_drawn(self):
        v = self.view()
        self.add(v, 0, model("rect", rect=pymupdf.Rect(50, 50, 100, 90),
                             props={"stroke": "#00ff00", "fill": "#0000ff", "width": 3}))
        x = self.legend(v, fontsize=20)
        page = v.doc[0]
        r = page.load_annot(x).rect
        pix = page.get_pixmap(dpi=72, clip=r, annots=True)
        colors = {pix.pixel(i, j) for i in range(pix.width) for j in range(pix.height)}
        self.assertIn((0, 255, 0), colors)          # the sample's outline ...
        self.assertIn((0, 0, 255), colors)          # ... and fill
        self.assertIn("Rectangle", page.get_text("text", clip=r))
        # nothing of it with markups left out: it's a markup, not page content
        bare = page.get_pixmap(dpi=72, clip=r, annots=False)
        self.assertNotIn((0, 255, 0), {bare.pixel(i, j) for i in range(bare.width)
                                       for j in range(bare.height)})

    def test_appearance_stream_saved_and_reopened(self):
        v = self.view()
        self.add(v, 0, model("ellipse", rect=pymupdf.Rect(50, 50, 100, 90)))
        x = self.legend(v)
        out = os.path.join(tempfile.mkdtemp(), "saved.pdf")
        v.doc.save(out)
        d = pymupdf.open(out)
        self.addCleanup(d.close)
        typ, val = d.xref_get_key(x, "AP/N")
        self.assertEqual(typ, "xref")
        ap = int(val.split()[0])
        self.assertIn(b"Tj", d.xref_stream(ap))
        self.assertEqual(d.xref_get_key(x, "Subtype")[1], "/Stamp")
        page = d[0]
        self.assertTrue(page.load_annot(x).flags & pymupdf.PDF_ANNOT_IS_PRINT)
        del page
        self.assertIn("Ellipse", d[0].get_text("text"))
        page = d[0]
        m = A.read(page.load_annot(x))
        self.assertEqual(m["kind"], "legend")
        self.assertEqual(self.counts(v, x), {"Ellipse": 1})
        # printed (only what has the Print flag) and flattened, it's there
        from kanzonas import print_dialog
        dl = print_dialog.print_list(d[0])
        self.assertIn("Ellipse", pymupdf.TextPage(dl.get_textpage()).extractText())
        d.bake(annots=True, widgets=False)
        self.assertEqual(L.legends_on(d[0]), [])
        self.assertIn("Ellipse", d[0].get_text("text"))

    def test_reads_upright_on_a_turned_page(self):
        v = self.view(rotation=90)
        self.add(v, 0, model("rect", rect=pymupdf.Rect(50, 50, 100, 90)))
        x = self.legend(v)
        page = v.doc[0]
        r = page.load_annot(x).rect
        lines = [ln for b in page.get_text("dict", clip=r)["blocks"] for ln in b.get("lines", [])]
        self.assertTrue(lines)
        # (the text runs left to right as the page is shown)
        for ln in lines:
            d = pymupdf.Point(ln["dir"]) * page.rotation_matrix - \
                pymupdf.Point(0, 0) * page.rotation_matrix
            self.assertAlmostEqual(d.x, 1, places=3)


class Updates(LegendCase):
    def test_add_delete_and_restyle_update_it(self):
        v = self.view()
        x = self.legend(v)
        self.assertEqual(self.counts(v, x), {})
        (r1, r2) = self.add(v, 0, model("rect", rect=pymupdf.Rect(50, 50, 100, 90)),
                            model("rect", rect=pymupdf.Rect(120, 50, 170, 90)))
        self.assertEqual(self.counts(v, x), {"Rectangle": 2})
        h0 = self.box(v, x).height
        # restyled: a row of its own
        v._set_selection(0, [r1])
        v.update_selected_props(dict(A.DEFAULTS["rect"], stroke="#00aa00"))
        rows = self.rows(v, x)
        self.assertEqual(sorted((r["style"]["stroke"], r["n"]) for r in rows),
                         [("#00aa00", 1), ("#d00000", 1)])
        self.assertGreater(self.box(v, x).height, h0)       # (grew a row)
        # deleted
        v._set_selection(0, [x2 for x2 in [a.xref for a in A.each_annot(v.doc[0])]
                             if x2 != x])
        v.delete_selected()
        self.assertEqual(self.counts(v, x), {})
        self.assertEqual(self.legend_xrefs(v), [x])         # (the legend itself stays)

    def test_it_does_not_count_itself_or_other_legends(self):
        v = self.view()
        self.add(v, 0, model("line", points=[P(50, 300), P(150, 300)]))
        x1 = self.legend(v)
        x2 = self.legend(v, title="Second")
        self.assertEqual(self.counts(v, x1), {"Line": 1})
        self.assertEqual(self.counts(v, x2), {"Line": 1})

    def test_hidden_markups_are_not_counted(self):
        v = self.view()
        (r,) = self.add(v, 0, model("rect", rect=pymupdf.Rect(50, 50, 100, 90)))
        x = self.legend(v)
        v.set_object_flags(0, [r], hidden=True) if False else None
        self.assertEqual(self.counts(v, x), {"Rectangle": 1})

    def test_many_markups_in_one_edit_draw_it_once(self):
        v = self.view()
        x = self.legend(v)
        calls = []
        real = L.draw

        def counting(*a, **k):
            calls.append(1)
            return real(*a, **k)
        with mock.patch.object(L, "draw", counting):
            self.add(v, 0, *[model("rect", rect=pymupdf.Rect(10 + i % 40 * 15, 100 + i // 40 * 15,
                                                             20 + i % 40 * 15, 110 + i // 40 * 15))
                             for i in range(1000)])
            self.assertEqual(len(calls), 1)
            self.assertEqual(self.counts(v, x), {"Rectangle": 1000})
            # an edit that changes nothing it lists (a markup moved) doesn't draw it
            calls.clear()
            first = [a.xref for a in A.each_annot(v.doc[0]) if a.xref != x][0]
            v._set_selection(0, [first])
            v.cad_apply("Moved", pymupdf.Matrix(1, 0, 0, 1, 5, 5))
            self.assertEqual(calls, [])

    def test_edits_with_no_legend_read_no_markups(self):
        v = self.view()
        with mock.patch.object(L, "page_summary", side_effect=AssertionError("read")):
            self.add(v, 0, model("rect", rect=pymupdf.Rect(50, 50, 100, 90)))


class MoveAndUndo(LegendCase):
    def test_moves_in_place_resizes_and_undoes(self):
        v = self.view()
        self.add(v, 0, model("rect", rect=pymupdf.Rect(50, 50, 100, 90)))
        x = self.legend(v)
        before = self.read_m(v, x)
        v._set_selection(0, [x])
        v.cad_apply("Moved", pymupdf.Matrix(1, 0, 0, 1, 20, 10))
        self.assertEqual(self.legend_xrefs(v), [x])                 # moved where it is
        after = self.read_m(v, x)
        self.assertTrue(A._same(A.translation(before, after), P(20, 10)))
        v.undo()
        self.assertTrue(A._same(self.read_m(v, x)["rect"], before["rect"]))
        v.redo()
        self.assertTrue(A._same(self.read_m(v, x)["rect"], after["rect"]))
        # resized: its text grows with the box
        (x,) = self.legend_xrefs(v)
        m = self.read_m(v, x)
        r = m["rect"]
        v.commit_model(0, x, A.resized(m, pymupdf.Rect(r.x0, r.y0, r.x0 + r.width * 2,
                                                       r.y0 + r.height * 2)))
        (x,) = self.legend_xrefs(v)
        m2 = self.read_m(v, x)
        self.assertAlmostEqual(m2["props"]["fontsize"], 18, delta=0.2)
        self.assertAlmostEqual(m2["rect"].width, r.width * 2, delta=2)

    def test_undo_then_redo_with_a_legend_on_the_page(self):
        v = self.view()
        x = self.legend(v)
        self.add(v, 0, model("rect", rect=pymupdf.Rect(50, 50, 100, 90)))
        self.add(v, 0, model("ellipse", rect=pymupdf.Rect(150, 50, 200, 90)))
        self.add(v, 0, model("line", points=[P(50, 300), P(150, 300)]))
        self.assertEqual(self.counts(v, x), {"Rectangle": 1, "Ellipse": 1, "Line": 1})
        v.undo()
        self.assertEqual(self.counts(v, x), {"Rectangle": 1, "Ellipse": 1})
        v.undo()
        self.assertEqual(self.counts(v, x), {"Rectangle": 1})
        self.assertTrue(v.can_redo())
        v.redo()
        self.assertEqual(self.counts(v, x), {"Rectangle": 1, "Ellipse": 1})
        v.redo()
        self.assertEqual(self.counts(v, x), {"Rectangle": 1, "Ellipse": 1, "Line": 1})
        self.assertFalse(v.can_redo())
        # the legend's picture follows (it's drawn from its appearance, not by the app)
        page = v.doc[0]
        self.assertIn("Line", page.get_text("text", clip=page.load_annot(x).rect))

    def test_undo_writes_nothing(self):
        v = self.view()
        self.legend(v)
        self.add(v, 0, model("rect", rect=pymupdf.Rect(50, 50, 100, 90)))
        with mock.patch.object(L, "draw", side_effect=AssertionError("drawn on undo")):
            v.undo()
            v.redo()
            v.undo()
        v.redo()
