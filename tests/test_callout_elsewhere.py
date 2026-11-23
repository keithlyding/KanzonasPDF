"""Callouts made in another program (Bluebeam, Acrobat: a FreeText with a leader, /CL) are read
as callouts, their arrow where their leader points and their box the text box inside the rect,
and a change of their text size or box keeps the arrow there (the owner, 23 Nov 2026: "I just
selected a bunch of callouts at the same time and made the text bigger. Their arrows moved to
some random location", and "Arrow also moved when I resized the box bigger"). Read as text
boxes, the leader was written to the page's corner.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_callout_elsewhere
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

import tests  # noqa: E402,F401
from kanzonas import annotations as A  # noqa: E402
from kanzonas.document_view import DocumentView  # noqa: E402

P, R = pymupdf.Point, pymupdf.Rect


class CalloutsMadeElsewhere(unittest.TestCase):
    def view(self, rotation):
        d = pymupdf.open()
        pg = d.new_page(width=612, height=792)
        pg.set_rotation(rotation)
        for k in range(2):
            a = pg.add_freetext_annot(R(300, 100 + 150 * k, 450, 140 + 150 * k),
                                      "Made elsewhere %d" % k, fontsize=10,
                                      callout=(P(120, 180 + 150 * k), P(200, 120 + 150 * k),
                                               P(300, 120 + 150 * k)),
                                      line_end=pymupdf.PDF_ANNOT_LE_OPEN_ARROW, border_width=1,
                                      rotate=rotation)
            a.update()
        path = os.path.join(tempfile.mkdtemp(), "c.pdf")
        d.save(path)
        v = DocumentView(path)
        self.addCleanup(v.close_doc)
        return v

    def callouts(self, v):
        page = v.doc[0]
        out = [(a.xref, A.read(a)) for a in A.each_annot(page)]
        del page
        return out

    def tips(self, v):
        return [(round(m["points"][0].x, 1), round(m["points"][0].y, 1))
                for _x, m in self.callouts(v)]

    def test_read_as_callouts_with_their_box_and_arrow(self):
        for rot in (0, 90, 180, 270):
            v = self.view(rot)
            got = self.callouts(v)
            self.assertEqual([m["kind"] for _x, m in got], ["callout", "callout"], rot)
            self.assertEqual(self.tips(v), [(120, 180), (120, 330)], rot)
            for (_x, m), y in zip(got, (100, 250)):
                for a, b in zip(m["rect"], (300, y, 450, y + 40)):
                    self.assertAlmostEqual(a, b, delta=1.5, msg=rot)

    def test_bigger_text_on_several_keeps_their_arrows(self):
        for rot in (0, 270):
            v = self.view(rot)
            v._set_selection(0, [x for x, _m in self.callouts(v)])
            props = dict(v.selected_model["props"])
            props["fontsize"] = float(props.get("fontsize") or 10) + 8
            v.update_selected_props(props)
            self.assertEqual(self.tips(v), [(120, 180), (120, 330)], rot)
            # (and as other programs read it: the leader's tip in the file)
            page = v.doc[0]
            for a in A.each_annot(page):
                cl = [float(t) for t in v.doc.xref_get_key(a.xref, "CL")[1].strip("[]").split()]
                self.assertNotEqual((round(cl[0]), round(cl[1])), (0, 792), rot)
            del page

    def test_a_bigger_box_keeps_its_arrow(self):
        v = self.view(0)
        x, m = self.callouts(v)[0]
        m = A.copy(m)
        r = m["rect"]
        m["rect"] = R(r.x0, r.y0, r.x1 + 80, r.y1 + 40)
        v.commit_models(0, [(x, m)])
        self.assertEqual(self.tips(v)[0], (120, 180))

    def test_a_plain_text_box_stays_a_text_box(self):
        d = pymupdf.open()
        d.new_page().add_freetext_annot(R(100, 100, 300, 140), "Just text").update()
        path = os.path.join(tempfile.mkdtemp(), "t.pdf")
        d.save(path)
        v = DocumentView(path)
        self.addCleanup(v.close_doc)
        self.assertEqual([m["kind"] for _x, m in self.callouts(v)], ["textbox"])


if __name__ == "__main__":
    unittest.main()
