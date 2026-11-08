"""1.9: every place KanzonasPDF rewrites a stream that is already there (a markup's
appearance it redraws or patches, a page's content stream it wraps or cleans), in edits
made one after the other, undoes and redoes exactly: each edit is undone back to the
document as it was before it and redone to the document as it was after it, byte for byte
(as tests/battery_random.py compares them), with saves in between.

Legends draw a new appearance object at each redraw (an appearance stream rewritten in
place came back from an undo with a later drawing: random battery, seed 1, 1.9). The rest,
checked here edit after edit as the random battery does it: a markup restyled, resized or
measured again is written anew (a new markup and appearance; what measure.py, clouds.py,
dimensions.py and annotations.py add to its appearance is added inside that same edit), a
form field's appearance is rewritten in place by MuPDF at each value, and page content
streams are rewritten in place by Remove watermarks, Background (added, changed, removed),
headers and footers, Edit text and Edit objects.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_appearance_rewrites
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402

from tests import battery_random as BR  # noqa: E402
from tests.test_undo_journal import Quiet  # noqa: E402
from kanzonas import annotations as A  # noqa: E402
import kanzonas.document_view as DV  # noqa: E402

APP = BR.APP
P, R = pymupdf.Point, pymupdf.Rect


class InPlace(Quiet):
    def setUp(self):
        super().setUp()
        self.addCleanup(setattr, DV, "UNDO_LIMIT", DV.UNDO_LIMIT)
        DV.UNDO_LIMIT = 10 ** 6

    def run_edits(self, setup, *edits):
        """setup(v) (not checked), then each edit(v) as its own undo step; then all undone
        and all redone, each state compared with the one it must be."""
        v = self.view()
        v.show()
        APP.processEvents()
        setup(v)
        states = [BR.State(v)]
        for k, edit in enumerate(edits):
            before = len(v._undo)
            edit(v)
            APP.processEvents()
            self.assertEqual(len(v._undo), before + 1, "edit %d made no undo step" % k)
            if k % 2:
                v._snapshot()               # (a save's write in between: see undo_journal)
            states.append(BR.State(v))
        n = len(edits)
        for k in range(n, 0, -1):
            v.undo()
            self.assertTrue(BR.State(v).same(states[k - 1]), "undo of edit %d" % (k - 1))
        for k in range(1, n + 1):
            v.redo()
            self.assertTrue(BR.State(v).same(states[k]), "redo of edit %d" % (k - 1))
        return v


def last(v, i=0):
    """The newest markup of page i."""
    return max(x for x, t, *_ in v.doc[i].annot_xrefs()
               if t not in (pymupdf.PDF_ANNOT_WIDGET, pymupdf.PDF_ANNOT_LINK,
                            pymupdf.PDF_ANNOT_POPUP))


def restyle(**props):
    def edit(v):
        v.select_xref(0, last(v))
        v.update_selected_props(props)
        v.clear_selection()
    return edit


def resize(k):
    def edit(v):
        x = last(v)
        v.select_xref(0, x)
        m = v.selected_model
        r = A.bounds(m)
        v.commit_model(0, x, A.resized(m, R(r.x0, r.y0, r.x0 + r.width * k,
                                              r.y0 + r.height * k)))
        v.clear_selection()
    return edit


def grip(k, d):
    def edit(v):
        x = last(v)
        v.select_xref(0, x)
        m = v.selected_model
        v.commit_model(0, x, A.with_endpoint(m, k, m["points"][k] + P(d, d / 2)))
        v.clear_selection()
    return edit


def field(value):
    def edit(v):
        v._set_field(1, [w.xref for w in v.doc[1].widgets()][0], value)
    return edit


def watermark(text, pages):
    return lambda v: v.add_watermark({"text": text, "pages": pages, "behind": False,
                                      "size": 48})


def no_watermarks(pages):
    return lambda v: v.remove_watermarks(pages)


def background(color, opacity=1.0):
    return lambda v: v.add_background({"kind": "color", "color": color,
                                       "opacity": opacity}, [0, 1])


def edit_text(word, new):
    def edit(v):
        r = v.doc[0].search_for(word)[0]
        v.edit_text_at(0, P((r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2))
        ed = v._inline
        ed.text.setPlainText(ed.text.toPlainText().replace(word, new, 1))
        ed.commit()
    return edit


def move_objects(d):
    def edit(v):
        v.select_objects(0, v.content_objects(0).items[:2])
        v.move_objects(v.selected_objects_rect() + (d, d, d, d))
        v.clear_object_selection()
    return edit


class Appearances(InPlace):
    def test_measurement_label(self):
        self.run_edits(lambda v: v.apply_drag_tool(0, "m_length", P(100, 500), P(300, 520),
                                                   False),
                       restyle(stroke="#00ff00"), restyle(fontsize=14),
                       restyle(stroke="#0000ff"))

    def test_radius_circle(self):
        self.run_edits(lambda v: v.apply_drag_tool(0, "m_radius", P(200, 500), P(260, 540),
                                                   False),
                       restyle(stroke="#00ff00"), restyle(width=3.0))

    def test_cloud(self):
        self.run_edits(lambda v: v.apply_drag_tool(0, "cloud", P(100, 500), P(300, 600), False),
                       restyle(stroke="#00ff00"), restyle(width=3.0), restyle(stroke="#123456"))

    def test_text_box_border(self):
        self.run_edits(lambda v: v._create(0, {"kind": "textbox", "text": "A text box",
                                               "props": dict(A.DEFAULTS["textbox"]),
                                               "rect": R(100, 500, 300, 560)}),
                       restyle(stroke="#00ff00"), restyle(stroke="#0000ff"),
                       restyle(text_color="#ff00ff"))

    def test_dimension(self):
        self.run_edits(lambda v: v.apply_poly(0, "m_dim", [P(100, 500), P(300, 500),
                                                           P(200, 450)]),
                       grip(0, 20), grip(2, -15), restyle(head="dot"), grip(1, 10))

    def test_stamp(self):
        self.run_edits(lambda v: v.place_stamp(0, P(300, 600)),
                       resize(1.3), resize(0.7), restyle(opacity=0.5), resize(1.1))

    def test_picture(self):
        from unittest import mock
        from kanzonas import dialogs
        png = self.path("picture.png")
        with open(png, "wb") as f:
            f.write(BR.png_bytes(60, 40, (200, 60, 30)))
        with mock.patch.object(dialogs, "open_file", lambda *a, **k: png):
            self.run_edits(lambda v: v.apply_drag_tool(0, "image", P(100, 500), P(250, 600),
                                                       False),
                           resize(1.3), restyle(rotation=90), resize(0.8))

    def test_form_field_value(self):
        self.run_edits(lambda v: None, field("Jane"), field("John Smith"), field(""),
                       field("Ann"))


class PageContent(InPlace):
    def test_watermarks(self):
        self.run_edits(lambda v: None, watermark("DRAFT", [0]), no_watermarks([0]),
                       watermark("COPY", [0, 1]), watermark("DRAFT", [0]),
                       no_watermarks([0, 1]), watermark("X", [1]))

    def test_backgrounds(self):
        self.run_edits(lambda v: None, background("#ffeeaa"), background("#aaeeff", 0.5),
                       lambda v: v.remove_background([0]), watermark("DRAFT", [0]),
                       background("#eeeeee"), no_watermarks([0]),
                       lambda v: v.remove_background([0, 1]))

    def test_header_and_footer(self):
        def hf(text):
            return lambda v: v.add_header_footer({"pages": [0, 1], "size": 9,
                                                  "texts": {("header", "left"): text}})
        self.run_edits(lambda v: None, hf("Top <<page>>"), hf("Again"), watermark("W", [0]))

    def test_edit_text_and_objects(self):
        self.run_edits(lambda v: None, edit_text("Contractor", "Builder"),
                       edit_text("Builder", "Maker"), move_objects(10), edit_text("Maker", "Firm"),
                       move_objects(-5))


if __name__ == "__main__":
    unittest.main()
