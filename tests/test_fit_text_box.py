"""Text boxes and callouts as tall as their text (issue #90, hellensvard, 12 Nov 2026; the owner
liked it: "Auto-size callout text box to fit content", as in Bluebeam): the box keeps its width
and its height follows the text, when it's made, when its text or font size changes and when its
width is dragged; its height dragged by hand keeps that box (and stops following the text);
Right-click > Fit to text fits one already on the page; "Fit the box to its text" in Properties
is part of the tool's style. Markups made before (or by other programs) keep their box.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_fit_text_box
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402

from tests.test_interaction_112 import A, P, R, Window, pump  # noqa: E402
from kanzonas import dialogs  # noqa: E402

LONG = ("Check this valve against the P&ID before the next revision, and confirm the line "
        "size with the process engineer")


def ink(page_rect, kind, text, rect, props=None):
    """Dark pixels of the markup drawn alone on a blank page (its fill and border off)."""
    d = pymupdf.open()
    pg = d.new_page(width=page_rect.width, height=page_rect.height)
    p = dict(A.DEFAULTS[kind], **(props or {}))
    p.update(stroke=None, fill=None)
    m = {"kind": kind, "props": p, "text": text, "rect": pymupdf.Rect(rect)}
    if kind == "callout":
        m["points"] = [P(50, 50)]
    A.write(pg, m)
    s = pg.get_pixmap(dpi=100, annots=True).samples
    return sum(1 for i in range(0, len(s), 3) if s[i] < 128)


class FitTextBox(Window):
    def setUp(self):
        self.w, self.v = self.open()

    def newest(self):
        page = self.v.doc[0]
        x = max(a.xref for a in page.annots())
        m = A.read(page.load_annot(x))
        return x, m

    def make(self, tool, text, a, b, click=False):
        with mock.patch.object(dialogs, "get_text", return_value=(text, True)):
            self.v.apply_drag_tool(0, tool, a, b, click)
        pump()
        return self.newest()

    def assert_all_shown(self, m):
        page = self.v.doc[0]
        r = R(m["rect"])
        tall = R(r.x0, r.y0, r.x1, r.y0 + 500)
        props = {k: m["props"][k] for k in ("fontsize", "font") if k in m["props"]}
        self.assertEqual(ink(page.rect, m["kind"], m["text"], r, props),
                         ink(page.rect, m["kind"], m["text"], tall, props))

    def test_a_callout_is_as_tall_as_its_text(self):
        x, m = self.make("callout", LONG, P(100, 100), P(200, 300))
        self.assertTrue(m["props"]["fit"])
        self.assertAlmostEqual(m["rect"].width, 160, delta=1)
        self.assertGreater(m["rect"].height, 50)            # (several lines: it was 40)
        self.assert_all_shown(m)
        # its text made shorter: the box shrinks to one line
        with mock.patch.object(dialogs, "get_text", return_value=("OK", True)):
            self.v.edit_annot_text(0, x)
        x, m2 = self.newest()
        self.assertLess(m2["rect"].height, 24)
        self.assertAlmostEqual(m2["rect"].y0, m["rect"].y0, delta=0.5)   # (its top stays)

    def test_font_size_and_width(self):
        x, m = self.make("textbox", LONG, P(100, 100), P(300, 140))
        self.assertAlmostEqual(m["rect"].width, 200, delta=1)
        h = m["rect"].height
        self.assert_all_shown(m)
        self.v.select_xref(0, x)
        props = dict(self.v.selected_model["props"], fontsize=18)
        self.v.update_selected_props(props)
        x, m = self.newest()
        self.assertGreater(m["rect"].height, h * 1.3)
        self.assert_all_shown(m)
        # its width dragged narrower (the right side's handle): taller
        pw = self.v.pages[0]
        self.v.select_xref(0, x)
        pump()
        r = R(m["rect"])
        mid = P(r.x1, (r.y0 + r.y1) / 2)
        h2 = r.height
        self.drag(pw, self.at(mid), self.at(mid - (60, 0)))
        x, m = self.newest()
        self.assertAlmostEqual(m["rect"].width, 140, delta=2)
        self.assertGreater(m["rect"].height, h2)
        self.assertTrue(m["props"]["fit"])
        self.assert_all_shown(m)
        # its height dragged by hand: that box, and it stops following its text
        self.v.select_xref(0, x)
        pump()
        r = R(m["rect"])
        bottom = P((r.x0 + r.x1) / 2, r.y1)
        self.drag(pw, self.at(bottom), self.at(bottom + (0, 80)))
        x, m = self.newest()
        self.assertAlmostEqual(m["rect"].height, r.height + 80, delta=2)
        self.assertFalse(m["props"]["fit"])
        # Fit to text: as tall as the text again, following it from then on
        self.v.select_xref(0, x)
        self.assertTrue(self.v.can_fit_to_text())
        self.v.fit_selected_to_text()
        x, m = self.newest()
        self.assertAlmostEqual(m["rect"].height, r.height, delta=1)
        self.assertTrue(m["props"]["fit"])

    def test_older_markups_keep_their_box(self):
        page = self.v.doc[0]
        a = page.add_freetext_annot(R(100, 100, 260, 140), "From another program",
                                    fontsize=11)
        a.update()
        x = a.xref
        del a, page
        self.v._clear_caches()
        page = self.v.doc[0]
        m = A.read(page.load_annot(x))
        del page
        self.assertFalse(m["props"]["fit"])
        with mock.patch.object(dialogs, "get_text", return_value=(LONG, True)):
            self.v.edit_annot_text(0, x)
        _x, m = self.newest()
        self.assertAlmostEqual(m["rect"].height, 40, delta=1.5)

    def test_part_of_the_tools_style(self):
        self.assertTrue(A.tool_props("callout")["fit"])
        self.assertTrue(A.tool_props("textbox")["fit"])
        self.w.set_tool("callout")
        pump()
        self.assertFalse(self.w.props.fit.isHidden())       # (its box in Properties)
        self.assertTrue(self.w.props.fit.isChecked())
        self.w.set_tool("rect")
        pump()
        self.assertTrue(self.w.props.fit.isHidden())


if __name__ == "__main__":
    unittest.main()
