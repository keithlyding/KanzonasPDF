"""What the 1.9 break-it battery of markup legends, dimensions, the page scale display, Replace
pages and box snapping found, fixed (one test per bug, each failing before its fix).

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_battery_19_markups
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


def model(kind, **kw):
    m = {"kind": kind, "props": dict(A.DEFAULTS[kind]), "rect": pymupdf.Rect()}
    m["props"].update(kw.pop("props", {}))
    m.update(kw)
    return m


def sheet(path, pages=1, raw_annots=(), width=800, height=600):
    """A PDF of pages with 'Sheet n' on each; raw_annots: annotation objects (PDF source)
    put on page 1 as another program would write them."""
    d = pymupdf.open()
    for i in range(pages):
        p = d.new_page(width=width, height=height)
        p.insert_text((40, 40), "Sheet %d" % (i + 1), fontsize=12)
    if raw_annots:
        xs = []
        for s in raw_annots:
            x = d.get_new_xref()
            d.update_object(x, s)
            xs.append(x)
        d.xref_set_key(d[0].xref, "Annots", "[%s]" % " ".join("%d 0 R" % x for x in xs))
    d.save(path)
    d.close()
    return path


class Case(unittest.TestCase):
    def setUp(self):
        # a message box ("Edit failed"...) is a failure here, not a window waiting for a click
        self.boxes = []
        for name in ("information", "warning", "critical"):
            patch = mock.patch.object(QMessageBox, name,
                                      lambda *a, **k: self.boxes.append(a[1:3]))
            patch.start()
            self.addCleanup(patch.stop)
        self.addCleanup(lambda: self.assertEqual(self.boxes, []))

    def path(self, name):
        return os.path.join(tempfile.mkdtemp(), name)

    def view(self, path):
        v = DocumentView(path)
        self.addCleanup(lambda: v.doc.is_closed or v.close_doc())
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

    def rows(self, v, x):
        return L.stored(v.doc, x)["geom"]["rows"]


class ForeignColors(Case):
    def test_gray_and_cmyk_colors_of_other_programs(self):
        """A markup another program colored in gray (/IC [0.5]) or CMYK (/C [c m y k]) read
        as RGB: the gray came out "#80", and a legend on its page failed to be placed ("Edit
        failed: invalid literal for int()") or, placed before, stopped updating for good; a
        CMYK cyan read as red."""
        src = sheet(self.path("gray.pdf"), raw_annots=(
            "<</Type/Annot/Subtype/Circle/Rect[600 250 650 300]/C[1 0 0]/IC[0.5]>>",
            "<</Type/Annot/Subtype/Square/Rect[600 350 650 400]/C[1 0 0 0]>>"))
        v = self.view(src)
        page = v.doc[0]
        got = {a.type[1]: A.read(a)["props"] for a in page.annots()}
        del page
        self.assertEqual(got["Circle"]["fill"], "#808080")
        self.assertEqual(got["Square"]["stroke"], "#00ffff")
        x = self.legend(v)
        self.assertIsNotNone(x)
        styles = sorted((r["kind"], r["style"].get("fill"), r["style"]["stroke"])
                        for r in self.rows(v, x))
        self.assertEqual(styles, [("ellipse", "#808080", "#ff0000"),
                                  ("rect", None, "#00ffff")])
        # (a color the legend can't read draws no color instead of stopping the legend)
        ops, _w, _h = L.layout([{"kind": "rect", "label": "x", "n": 1, "total": "",
                                 "style": {"stroke": "#80", "fill": "nonsense"}}],
                               A.DEFAULTS["legend"])
        self.assertTrue(ops.out)


class Replies(Case):
    def test_replies_and_review_statuses_are_not_counted(self):
        """A review thread from Acrobat or Bluebeam keeps each reply as a note answering the
        markup (/IRT): a legend counted every reply (and every reply to a reply) as a sticky
        note of the drawing. Markups grouped with another (/RT /Group) still count."""
        d = pymupdf.open()
        p = d.new_page(width=800, height=600)
        xs = [d.get_new_xref() for _ in range(5)]
        objs = ["<</Type/Annot/Subtype/Square/Rect[50 50 100 100]/C[1 0 0]/Subj(Cloud)>>",
                "<</Type/Annot/Subtype/Text/Rect[50 50 70 70]/IRT %d 0 R/Contents(Agreed)"
                "/Subj(Comment)>>" % xs[0],
                "<</Type/Annot/Subtype/Text/Rect[50 50 70 70]/IRT %d 0 R/Contents(Me too)>>"
                % xs[1],
                "<</Type/Annot/Subtype/Text/Rect[50 50 70 70]/IRT %d 0 R/State(Accepted)"
                "/StateModel(Review)>>" % xs[0],
                "<</Type/Annot/Subtype/Square/Rect[150 50 200 100]/C[1 0 0]/Subj(Cloud)"
                "/IRT %d 0 R/RT/Group>>" % xs[0]]
        for x, o in zip(xs, objs):
            d.update_object(x, o)
        d.xref_set_key(p.xref, "Annots", "[%s]" % " ".join("%d 0 R" % x for x in xs))
        del p
        path = self.path("thread.pdf")
        d.save(path)
        d.close()
        v = self.view(path)
        x = self.legend(v)
        self.assertEqual({r["label"]: r["n"] for r in self.rows(v, x)}, {"Cloud": 2})


class Subjects(Case):
    def measured_sheet(self):
        v = self.view(sheet(self.path("scale.pdf"), width=600, height=600))
        made = self.add(v, 0, model("m_length", points=[P(100, 200), P(300, 200)]),
                        model("m_dim", points=[P(100, 100), P(300, 100), P(200, 80)]),
                        model("rect", rect=pymupdf.Rect(400, 400, 450, 450)))
        reply = {}

        def subjects():
            for x, name in zip(made, ("Duct run", "Opening", "Fire door")):
                v.doc.xref_set_key(x, "Subj", pymupdf.get_pdf_str(name))
            pg = v.doc[0]
            r = pg.add_text_annot((100, 100), "Check this")
            v.doc.xref_set_key(r.xref, "IRT", "%d 0 R" % made[1])
            reply["x"] = r.xref
        v.modify(subjects, [0])
        return v, made, reply["x"]

    def subjects(self, v):
        page = v.doc[0]
        return sorted(a.info["subject"] for a in page.annots() if a.info.get("subject"))

    def test_set_scale_keeps_subjects_replies_and_order(self):
        """Setting a page's scale measures its measurements again, each deleted and written
        anew: their subjects (a legend's labels) were lost, their replies deleted with
        them, and they went to the top of the stacking order."""
        from kanzonas import measure
        v, made, reply = self.measured_sheet()
        x = self.legend(v)
        order = A.annot_order(v.doc[0])
        v.set_page_scale([0], measure.scale_from_preset(96), "ft-in", '1/8" = 1\'-0"')
        self.assertEqual(self.subjects(v), ["Duct run", "Fire door", "Opening"])
        self.assertEqual({r["label"]: r["total"] for r in self.rows(v, x)},
                         {"Duct run": "22'-2 11/16\"", "Opening": "", "Fire door": ""})
        page = v.doc[0]
        dims = [a.xref for a in page.annots() if a.info.get("subject") == "Opening"]
        del page
        self.assertEqual(v.doc.xref_get_key(reply, "IRT"), ("xref", "%d 0 R" % dims[0]))
        now = A.annot_order(v.doc[0])
        self.assertEqual(now[2:], order[2:])            # (the two measurements kept their place)
        self.assertEqual(len(now), len(order))

    def test_restyled_and_copied_markups_keep_their_subject(self):
        """A markup written anew (restyled, its text changed, copied) lost its subject, so a
        legend listing it by its Bluebeam subject renamed its row to the tool's name."""
        v, made, _reply = self.measured_sheet()
        x = self.legend(v)
        v._set_selection(0, [made[2]])
        v.update_selected_props(dict(A.DEFAULTS["rect"], stroke="#00aa00"))
        self.assertIn("Fire door", [r["label"] for r in self.rows(v, x)])
        v._set_selection(0, [made[0]])
        self.assertEqual(v.duplicate_selected(), 1)
        self.assertEqual({r["label"]: r["n"] for r in self.rows(v, x)}["Duct run"], 2)


class BoxSnapping(Case):
    def setUp(self):
        super().setUp()
        for key in ("snap_page", "snap_objects", "snap_grid"):
            self.addCleanup(setattr, DocumentView, key, getattr(DocumentView, key))
        DocumentView.snap_page = DocumentView.snap_objects = True
        DocumentView.snap_grid = False

    def drop_near_center(self, line_end, off):
        """A picture markup dragged so its center is off (px) from the page's center, the
        drawing having a line ending at line_end: where its center lands, from the page's."""
        from PySide6.QtCore import QPointF
        d = pymupdf.open()
        page = d.new_page(width=600, height=400)
        page.draw_line(line_end, (line_end[0], 120), width=0.5)
        del page
        path = self.path("snap.pdf")
        d.save(path)
        d.close()
        v = self.view(path)
        v.resize(1200, 900)
        v.show()
        APP.processEvents()
        v.set_zoom(1.0)
        APP.processEvents()
        self.addCleanup(v.hide)
        pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 20, 12), False)
        x = v._create(0, {"kind": "image", "props": dict(A.DEFAULTS["image"]),
                          "rect": pymupdf.Rect(100, 80, 200, 140),
                          "image_bytes": pix.tobytes("png")})
        pw = v.pages[0]
        page = v.doc[0]
        c = pw.to_screen(page.rect * page.derotation_matrix).center()
        del page
        v.select_xref(0, x)
        m = v.selected_model
        box = pw.to_screen(A.bounds(m))
        start = box.center()
        pw._edit = {"mode": "move", "start": start, "model": m, "preview": None}
        got = pw._edit_preview(start + (c - box.center()) + QPointF(*off), snap=True)
        o = pw.to_screen(A.bounds(got)).center() - c
        return round(o.x(), 2), round(o.y(), 2)

    def test_page_center_wins_over_a_farther_line_end(self):
        """The owner's picture that wouldn't snap to the page's center: with Snap to objects
        on as well, any point of the drawing within reach of one of the picture's corners or
        edge middles won, however much nearer the center was (here a line end 6 px from its
        corner, the center 2 px away: it landed 8 px off the middle)."""
        # (the picture 100 x 60 pt at 100%: its top-left corner lands at 252, 168)
        self.assertEqual(self.drop_near_center((258, 168), (2, -2)), (0, 0))
        # (a line end nearer than the center still wins: 1 px from the corner)
        self.assertEqual(self.drop_near_center((253, 168), (2, -2)), (3, -2))


class OddScales(Case):
    def test_a_scale_that_cant_be_one_reads_as_not_set(self):
        """A page scale kept as not a number (or zero, negative, infinite, or in a unit this
        version doesn't know, as a file from elsewhere may hold) was taken as set: with Show
        scale bar on, drawing the page raised in its paint event (a painter left active) at
        every repaint."""
        from kanzonas import measure
        for val in ("nan|in|x", "inf|in|x", "0|in|x", "-1|m|x", "1|furlong|x"):
            with self.subTest(val=val):
                d = pymupdf.open()
                p = d.new_page(width=600, height=400)
                d.xref_set_key(p.xref, measure.KEY, pymupdf.get_pdf_str(val))
                self.assertFalse(measure.get_scale(p)[3])
                del p
                path = self.path("odd.pdf")
                d.save(path)
                d.close()
                with mock.patch.object(DocumentView, "show_scale_bar", True):
                    v = self.view(path)
                    v.resize(900, 700)
                    v.show()
                    APP.processEvents()
                    self.assertIsNone(v.scale_bar_pixmap(0, 1.0, v.pages[0].width()))
                    v.pages[0].grab()
                    v.hide()
        page = pymupdf.open().new_page()
        measure.set_scale(page, measure.scale_from_preset(96), "ft-in", "1/8\" = 1'-0\"")
        self.assertTrue(measure.get_scale(page)[3])


class ReplacedSheets(Case):
    def scale_sheet(self, path, note, label="PLAN"):
        d = pymupdf.open()
        p = d.new_page(width=792, height=612)
        p.insert_text((60, 80), label, fontsize=24)
        p.insert_text((600, 560), "SCALE: " + note, fontsize=10)
        del p
        d.save(path)
        d.close()
        return path

    def test_the_new_drawings_scale_note_is_read(self):
        """The scale a sheet's title block says was read once per page and kept: after Replace
        pages (or Edit text on the note) the status bar, Set scale and Read scales from title
        blocks still went by the old revision's note."""
        v = self.view(self.scale_sheet(self.path("old.pdf"), '1/4" = 1\'-0"'))
        self.assertEqual(v.sheet_scale_note(0)["ratio"], 48)
        src = pymupdf.open(self.scale_sheet(self.path("new.pdf"), '1/8" = 1\'-0"', "PLAN B"))
        self.addCleanup(src.close)
        v.replace_pages(src, [(0, 0)])
        self.assertEqual(v.sheet_scale_note(0)["ratio"], 96)
        self.assertIn('1/8"', v.page_scale_text(0))
        v.undo()
        self.assertEqual(v.sheet_scale_note(0)["ratio"], 48)


if __name__ == "__main__":
    unittest.main()
