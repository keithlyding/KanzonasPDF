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
        # the page's scale changed: the totals follow (and Undo takes them back)
        v.set_page_scale([0], M.scale_from_preset(96), "ft-in", '1/8" = 1\'-0"')
        rows = {r["label"]: r for r in self.rows(v, x)}
        self.assertEqual(rows["Length"]["total"], "24'-0\"")
        v.undo()
        rows = {r["label"]: r for r in self.rows(v, x)}
        self.assertEqual(rows["Length"]["total"], "12'-0\"")
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

    def test_dimensions_listed_with_their_own_sample(self):
        # a Dimension (dimensions.py) is a row of its own, drawn as a dimension line with
        # its extension lines in the dimension's color, not the plain square of other kinds
        v = self.view()
        v.apply_poly(0, "m_dim", [P(50, 100), P(300, 100), P(170, 140)])
        x = self.legend(v, fontsize=20)
        self.assertEqual([(r["label"], r["kind"], r["n"]) for r in self.rows(v, x)],
                         [("Dimension", "m_dim", 1)])
        page = v.doc[0]
        r = page.load_annot(x).rect
        pix = page.get_pixmap(dpi=144, clip=r, annots=True)
        red = [(i, j) for i in range(pix.width) for j in range(pix.height)
               if pix.pixel(i, j)[0] > 150 and max(pix.pixel(i, j)[1:]) < 90]
        self.assertTrue(red)
        xs = sorted({i for i, _j in red})
        ys = sorted({j for _i, j in red})
        # wider than tall (a line, not a square), and its ends taller than its middle
        self.assertGreater(xs[-1] - xs[0], 1.5 * (ys[-1] - ys[0]))
        mid = (xs[0] + xs[-1]) // 2
        end_h = len({j for i, j in red if i == xs[0]})
        mid_h = len({j for i, j in red if i == mid})
        self.assertGreater(end_h, mid_h)

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
        self.assertEqual(self.counts(v, x), {"Rectangle": 1})
        v.set_object_flags(0, [r], hidden=True)            # (Objects panel: Hide)
        self.assertEqual(self.counts(v, x), {})
        v.set_object_flags(0, [r], hidden=False)
        self.assertEqual(self.counts(v, x), {"Rectangle": 1})
        # a locked legend keeps updating, and keeps its own look
        v.set_object_flags(0, [x], locked=True)
        self.add(v, 0, model("rect", rect=pymupdf.Rect(150, 50, 200, 90)))
        self.assertEqual(self.counts(v, x), {"Rectangle": 2})
        page = v.doc[0]
        self.assertIn("Rectangle", page.get_text("text", clip=page.load_annot(x).rect))

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


class Placing(LegendCase):
    def test_the_tool_places_it_and_a_box_sets_its_width(self):
        v = self.view()
        self.add(v, 0, model("rect", rect=pymupdf.Rect(50, 50, 100, 90)))
        v.apply_drag_tool(0, "legend", P(400, 300), P(400, 300), True)
        (x,) = self.legend_xrefs(v)
        r = self.box(v, x)
        self.assertAlmostEqual(r.x0, 400, delta=0.01)
        self.assertAlmostEqual(r.y0, 300, delta=0.01)
        v.apply_drag_tool(0, "legend", P(100, 300), P(400, 340), False)
        x2 = [k for k in self.legend_xrefs(v) if k != x][0]
        self.assertAlmostEqual(self.box(v, x2).width, 300, delta=8)
        self.assertGreater(self.read_m(v, x2)["props"]["fontsize"], 9)
        self.assertEqual(self.counts(v, x2), {"Rectangle": 1})

    def test_pages_duplicated_and_deleted(self):
        v = self.view(pages=2)
        self.add(v, 0, model("rect", rect=pymupdf.Rect(50, 50, 100, 90)))
        self.legend(v, 1, scope="document")
        v.duplicate_pages([0])
        (x,) = self.legend_xrefs(v, 2)
        self.assertEqual(self.counts(v, x, 2), {"Rectangle": 2})
        v.delete_pages([0])
        (x,) = self.legend_xrefs(v, 1)
        self.assertEqual(self.counts(v, x, 1), {"Rectangle": 1})
        v.undo()
        (x,) = self.legend_xrefs(v, 2)
        self.assertEqual(self.counts(v, x, 2), {"Rectangle": 2})

    def test_properties_panel_offers_its_options(self):
        from kanzonas.properties import PropertiesPanel
        panel = PropertiesPanel()
        self.addCleanup(panel.deleteLater)
        got = []
        panel.propsChanged.connect(got.append)
        panel.show_target("legend", dict(A.DEFAULTS["legend"]))
        for key in ("title", "scope", "count", "totals", "border", "fontsize", "stroke",
                    "fill", "text_color"):
            self.assertFalse(panel.rows[key][1].isHidden(), key)
        self.assertTrue(panel.rows["label"][1].isHidden())
        panel.scope.setCurrentIndex(panel.scope.findData("document"))
        self.assertEqual(got[-1]["scope"], "document")
        panel.show_totals.setChecked(False)
        self.assertFalse(got[-1]["totals"])
        panel.title_edit.setText("Electrical")
        panel.title_edit.editingFinished.emit()
        self.assertEqual(got[-1]["title"], "Electrical")

    def test_in_the_menus_and_on_the_ribbon(self):
        from PySide6.QtWidgets import QToolButton
        from kanzonas.main_window import MainWindow
        win = MainWindow()
        self.addCleanup(win.deleteLater)
        a = win.tool_actions["legend"]
        tools = [m for m in win.menuBar().actions() if m.text() == "&Tools"][0].menu()
        self.assertIn(a, tools.actions())
        names = [win.ribbon.tabText(i) for i in range(win.ribbon.count())]
        markup = win.ribbon.widget(names.index("Markup"))
        self.assertTrue(any(b.defaultAction() is a for b in markup.findChildren(QToolButton)))


def containing(data, word):
    """The objects of a PDF (its bytes) whose dictionary or stream holds word (any case),
    with what nothing uses any more kept (written as is, garbage 0)."""
    d = pymupdf.open("pdf", data)
    pdf = pymupdf.open("pdf", d.tobytes(expand=255))
    w = word.lower()
    out = []
    for x in range(1, pdf.xref_length()):
        try:
            if w in pdf.xref_object(x).lower() or (pdf.xref_is_stream(x) and
                                                   w.encode() in (pdf.xref_stream(x) or b"").lower()):
                out.append(x)
        except Exception:
            pass
    return out


class Redaction(LegendCase):
    """1.9: a word redacted that a legend shows (a markup's subject as a row's label, its
    title) doesn't stay in the legend: Apply redactions draws the legends again from the
    markups left, inside its own step and before its clean-up writes the document anew (they
    used to be deleted whole, or left showing a markup redacted under a box until after)."""

    def setup_markups(self, v):
        def do():
            page = v.doc[0]
            for subject, r in (("Secret door", pymupdf.Rect(50, 50, 100, 90)),
                               ("Fire door", pymupdf.Rect(150, 50, 200, 90)),
                               ("Client ACME", pymupdf.Rect(250, 50, 300, 90))):
                x = A.write(page, model("rect", rect=r)).xref
                v.doc.xref_set_key(x, "Subj", pymupdf.get_pdf_str(subject))
        v.modify(do, [0], permission=pymupdf.PDF_PERM_ANNOTATE)
        here = self.legend(v, 0, title="Secret plan legend")
        there = self.legend(v, 1, scope="document")
        return here, there

    def labels(self, v):
        out = []
        for i in range(v.doc.page_count):
            for x in self.legend_xrefs(v, i):
                st = L.stored(v.doc, x)
                out.append((i, st["props"].get("title"),
                            sorted(r["label"] for r in st["geom"]["rows"])))
        return out

    def test_search_and_redact_draws_them_again(self):
        for scrub in (False, True):
            v = self.view()
            self.setup_markups(v)
            self.assertTrue(v.search_redact("Secret"))      # (the legends' rows show it too)
            v.apply_redactions(scrub=scrub)
            # (the markup whose subject held it stays, written anew without its subject)
            self.assertEqual(self.labels(v), [
                (0, "[redacted] plan legend", ["Client ACME", "Fire door", "Rectangle"]),
                (1, "Legend", ["Client ACME", "Fire door", "Rectangle"])], "scrub %s" % scrub)
            for i in range(2):
                page = v.doc[i]
                for x in self.legend_xrefs(v, i):
                    self.assertNotIn("secret", page.load_annot(x).get_text().lower())
            self.assertEqual(containing(v._snapshot(), "secret"), [], "scrub %s" % scrub)
            v.undo()
            self.assertEqual(self.labels(v)[1][2], ["Client ACME", "Fire door", "Secret door"])
            v.redo()
            self.assertEqual(self.labels(v)[1][2], ["Client ACME", "Fire door", "Rectangle"])

    def test_a_markup_under_a_box_leaves_them_before_the_clean_up(self):
        v = self.view()
        self.setup_markups(v)
        v.mark_redactions(0, [pymupdf.Rect(245, 45, 305, 95)])     # (over Client ACME)
        v.apply_redactions(scrub=True)
        self.assertEqual([lab for _i, _t, lab in self.labels(v)],
                         [["Fire door", "Secret door"]] * 2)
        # the document written anew holds no copy of the legends as they were, not even
        # one nothing uses (a write that keeps those: as Save signed copy did)
        self.assertEqual(containing(v.doc.tobytes(), "ACME"), [])

    def test_a_box_drawn_over_a_legend_takes_it_away(self):
        v = self.view()
        here, _there = self.setup_markups(v)
        v.mark_redactions(0, [self.box(v, here)])
        v.apply_redactions(scrub=False)
        self.assertEqual(self.legend_xrefs(v, 0), [])
        self.assertEqual(len(self.legend_xrefs(v, 1)), 1)

    def test_remove_term_cleans_the_title(self):
        v = self.view()
        self.setup_markups(v)
        v.remove_term("plan")
        self.assertEqual(self.labels(v)[0][1], "Secret [redacted] legend")
        self.assertEqual(containing(v._snapshot(), "plan legend"), [])

    def test_signed_copy_has_nothing_redacted(self):
        # Digital signature signs the document as it is: what Apply redactions took away
        # without its clean-up (a note, a picture) stayed in it, unused but readable
        v = self.view()
        self.setup_markups(v)
        page = v.doc[0]
        pm = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 30, 20), False)
        v.modify(lambda: page.insert_image(pymupdf.Rect(400, 300, 600, 450), pixmap=pm), [0])
        del page
        v.mark_redactions(0, [pymupdf.Rect(45, 45, 105, 95), pymupdf.Rect(390, 290, 610, 460)])
        v.apply_redactions(scrub=False)
        data = v.signing_bytes()
        self.assertEqual(containing(data, "Secret door"), [])
        d = pymupdf.open("pdf", data)
        self.assertFalse([x for x in range(1, d.xref_length())
                          if d.xref_get_key(x, "Subtype")[1] == "/Image"])
