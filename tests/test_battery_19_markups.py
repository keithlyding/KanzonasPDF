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


if __name__ == "__main__":
    unittest.main()
