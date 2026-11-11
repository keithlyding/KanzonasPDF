"""Pages > Add space around page (issue #82): the page grows on the sides chosen, as it's
shown, and its text, drawing, markups (with the positions KanzonasPDF keeps for them), links
and form fields stay where they are on it; one undo step; the new space prints like the rest
of the page. Also Crop pages and Remove crop: a box or callout no longer jumps by the crop
when next edited (the positions kept in page coordinates follow: annotations.rebase_page).

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_page_space
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
from kanzonas import links, page_space  # noqa: E402
from kanzonas.document_view import DocumentView  # noqa: E402
from tests.test_undo_journal import canon  # noqa: E402

P = pymupdf.Point


def sheet(path, rotation=0, crop=None):
    """A page with a word, a filled square, a box, a callout, a line, a link with an
    underline and a text field."""
    d = pymupdf.open()
    pg = d.new_page(width=612, height=792)
    pg.insert_text((100, 90), "Anchor", fontsize=14)
    pg.draw_rect((300, 300, 340, 340), color=(0, 0, 0), fill=(0, 0, 0))
    A.write(pg, {"kind": "rect", "rect": pymupdf.Rect(100, 100, 200, 180), "text": "",
                 "props": dict(A.DEFAULTS["rect"])})
    A.write(pg, {"kind": "callout", "rect": pymupdf.Rect(150, 250, 300, 290), "text": "Look",
                 "points": [P(100, 300)], "props": dict(A.DEFAULTS["callout"])})
    A.write(pg, {"kind": "line", "rect": pymupdf.Rect(), "text": "",
                 "points": [P(100, 400), P(200, 450)], "props": dict(A.DEFAULTS["line"])})
    links.add(pg, [pymupdf.Rect(100, 500, 200, 515)], ("uri", "https://example.com"), "U")
    w = pymupdf.Widget()
    w.field_type = pymupdf.PDF_WIDGET_TYPE_TEXT
    w.field_name = "Name"
    w.rect = pymupdf.Rect(100, 600, 250, 620)
    pg.add_widget(w)
    if crop is not None:
        pg.set_cropbox(crop)
    if rotation:
        pg.set_rotation(rotation)
    d.save(path)


def where(page):
    """Positions as shown (page coordinates turned as the page is shown) of everything."""
    rot = page.rotation_matrix
    out = {}
    wd = next(w for w in page.get_text("words") if w[4] == "Anchor")
    out["word"] = (pymupdf.Rect(wd[:4]) * rot).normalize()
    for a in page.annots():
        m = A.read(a)
        out[m["kind"]] = (pymupdf.Rect(a.rect) * rot).normalize()
        if m.get("rect") is not None and m["kind"] in ("rect", "callout"):
            out[m["kind"] + " kept"] = (pymupdf.Rect(m["rect"]) * rot).normalize()
        if m.get("points"):
            out[m["kind"] + " pts"] = [P(q) * rot for q in m["points"]]
    lk = page.get_links()[0]
    out["link"] = pymupdf.Rect(lk["from"])      # (PyMuPDF gives a link's box as shown)
    out["field"] = (pymupdf.Rect(next(page.widgets()).rect) * rot).normalize()
    return out


class AddSpace(unittest.TestCase):
    MARGINS = (72, 36, 144, 0)          # left, top, right, bottom (as shown)

    def check(self, rotation=0, crop=None):
        path = os.path.join(tempfile.mkdtemp(), "sheet.pdf")
        sheet(path, rotation, crop)
        v = DocumentView(path)
        self.addCleanup(v.close_doc)
        before = where(v.doc[0])              # (links read, and kept by MuPDF, before)
        size = v.doc[0].rect
        canon_before = canon(v.doc)
        v.add_page_space([0], self.MARGINS)
        page = v.doc[0]
        left, top, right, bottom = self.MARGINS
        self.assertAlmostEqual(page.rect.width, size.width + left + right, delta=0.01)
        self.assertAlmostEqual(page.rect.height, size.height + top + bottom, delta=0.01)
        after = where(page)
        shift = P(left, top)
        for k, r in before.items():
            if isinstance(r, list):
                for q0, q1 in zip(r, after[k]):
                    self.assertAlmostEqual(abs(q1 - (q0 + shift)), 0, delta=0.05, msg=k)
            else:
                self.assertAlmostEqual(abs(after[k].tl - (r.tl + shift)), 0, delta=0.05, msg=k)
                self.assertAlmostEqual(abs(after[k].br - (r.br + shift)), 0, delta=0.05, msg=k)
        # editing a markup now keeps it in place (its kept box agrees with the page)
        x = next(a.xref for a in page.annots() if A.read(a)["kind"] == "rect")
        v.select_xref(0, x)
        v.update_selected_props({"width": 3.0})
        self.assertAlmostEqual(abs(where(v.doc[0])["rect kept"].tl - after["rect kept"].tl), 0,
                               delta=0.05)
        # one undo step gives the page back as it was
        v.undo()
        v.undo()
        self.assertEqual(canon(v.doc), canon_before)
        return v

    def test_plain_page(self):
        self.check()

    def test_turned_page(self):
        self.check(rotation=90)

    def test_cropped_page(self):
        self.check(crop=pymupdf.Rect(50, 20, 580, 760))

    def test_saved_and_opened_again(self):
        path = os.path.join(tempfile.mkdtemp(), "sheet.pdf")
        sheet(path)
        v = DocumentView(path)
        self.addCleanup(v.close_doc)
        v.add_page_space([0], self.MARGINS)
        expect = where(v.doc[0])
        out = os.path.join(os.path.dirname(path), "out.pdf")
        v.doc.save(out)
        d = pymupdf.open(out)
        got = where(d[0])
        for k, r in expect.items():
            if not isinstance(r, list):
                self.assertAlmostEqual(abs(got[k].tl - r.tl), 0, delta=0.05, msg=k)
        # the square is drawn shifted by the space added on the left and top
        pix = d[0].get_pixmap()
        self.assertEqual(pix.pixel(320 + 72, 320 + 36)[:3], (0, 0, 0))
        self.assertEqual(pix.pixel(30, 400)[:3], (255, 255, 255))

    def test_refused(self):
        path = os.path.join(tempfile.mkdtemp(), "sheet.pdf")
        sheet(path)
        v = DocumentView(path)
        self.addCleanup(v.close_doc)
        with self.assertRaises(ValueError):
            v.add_page_space([0], (-10, 0, 0, 0))
        with self.assertRaises(ValueError):
            v.add_page_space([0], (0, 0, 14400, 0))
        self.assertIsNone(page_space.check(v.doc[0], (0, 0, 72, 0)))


class Crop(unittest.TestCase):
    def test_cropped_box_and_callout_keep_their_place_when_edited(self):
        path = os.path.join(tempfile.mkdtemp(), "sheet.pdf")
        sheet(path)
        v = DocumentView(path)
        self.addCleanup(v.close_doc)
        v.crop_pages(0, pymupdf.Rect(50, 20, 580, 760))
        got = where(v.doc[0])
        # the boxes KanzonasPDF keeps moved with the crop (a callout's outline holds its
        # pointer too: its text box is compared with where it was put)
        self.assertAlmostEqual(abs(got["rect kept"].tl - got["rect"].tl), 0, delta=3)
        self.assertAlmostEqual(abs(got["callout kept"].tl - P(100, 230)), 0, delta=0.05)
        v.remove_crop(0)
        got = where(v.doc[0])
        self.assertAlmostEqual(abs(got["rect kept"].tl - P(100, 100)), 0, delta=0.05)


class OutsideIsHiddenInformation(unittest.TestCase):
    """Comments kept wholly outside the page (the working space): other PDF programs and
    printing don't show them, so Sanitize document and redaction's Remove hidden information
    take them out; a markup partly on the page stays."""
    def view(self):
        path = os.path.join(tempfile.mkdtemp(), "notes.pdf")
        d = pymupdf.open()
        pg = d.new_page(width=612, height=792)
        props = dict(A.DEFAULTS["textbox"])
        for name, r in (("on", pymupdf.Rect(100, 100, 250, 140)),
                        ("partly", pymupdf.Rect(560, 100, 700, 140)),
                        ("outside", pymupdf.Rect(650, 300, 800, 340))):
            A.write(pg, {"kind": "textbox", "rect": r, "text": name, "props": props})
        d.save(path)
        v = DocumentView(path)
        self.addCleanup(v.close_doc)
        return v

    def texts(self, v):
        return sorted(a.info.get("content", "") for a in v.doc[0].annots())

    def test_found(self):
        v = self.view()
        self.assertEqual(len(A.outside_page(v.doc[0])), 1)

    def test_sanitize(self):
        v = self.view()
        v.sanitize({"outside": True})
        self.assertEqual(self.texts(v), ["on", "partly"])
        v = self.view()
        v.sanitize({"outside": False})
        self.assertEqual(self.texts(v), ["on", "outside", "partly"])

    def test_redaction_clean_up(self):
        v = self.view()
        v.apply_redactions(True)
        self.assertEqual(self.texts(v), ["on", "partly"])
        v = self.view()
        v.apply_redactions(False)
        self.assertEqual(self.texts(v), ["on", "outside", "partly"])


if __name__ == "__main__":
    unittest.main()
