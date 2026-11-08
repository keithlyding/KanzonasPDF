"""1.9: a compacting save (garbage 2 and up) renumbers the document's objects in the document
itself, and MuPDF replaces an object something still holds (a MuPDF object handle) with a
copy whose entry no longer says where its stream's data is: a page placed with
show_pdf_page lost its drawing (found by Save as PDF/A). kanzonas.save_guard moves such
streams among the changed objects first; every compacting save the app makes keeps every
drawing, picture and text."""
import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np  # noqa: E402
import pymupdf  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import save_guard  # noqa: E402

m = pymupdf.mupdf


def placed_pdf(pages=2):
    """Pages with another PDF's page placed on them (a form whose /Resources is another
    object: what MuPDF copies), a picture with a soft mask (/SMask: the same), text and a
    highlight."""
    g = pymupdf.open()
    gp = g.new_page()
    gp.draw_rect((10, 10, 200, 200), color=(1, 0, 0), fill=(0, 0, 1))
    gp.insert_text((50, 50), "placed page text")
    d = pymupdf.open()
    for i in range(pages):
        p = d.new_page()
        p.show_pdf_page(pymupdf.Rect(0, 0, 300, 300), g, 0)
        pm = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 40, 30), True)
        pm.set_rect(pm.irect, (200, 30, 30, 128))
        p.insert_image((300, 300, 500, 450), pixmap=pm)
        p.insert_text((72, 600), "Body text secret %d" % i)
        p.add_highlight_annot(pymupdf.Rect(70, 590, 200, 606))
    return d.tobytes(garbage=3, deflate=True)


def held_streams(doc):
    """Handles on every stream object whose dictionary names another object (as
    pdf_load_object hands them out)."""
    pdf = pymupdf._as_pdf_document(doc)
    out = []
    for x in range(1, doc.xref_length()):
        if doc.xref_is_stream(x) and " 0 R" in doc.xref_object(x, compressed=True):
            out.append(m.pdf_load_object(pdf, x))
    return out


def look(data):
    """Each page's text, pictures and pixels (summed), as a value to compare."""
    with pymupdf.open("pdf", data) as d:
        return [(" ".join(p.get_text().split()), len(p.get_images()),
                 int(np.frombuffer(p.get_pixmap(dpi=30).samples, np.uint8).sum()))
                for p in d]


class Mechanism(unittest.TestCase):
    def test_held_stream_written_without_its_data_unguarded(self):
        # MuPDF itself (the save without the guard): what the guard is for. If this fails
        # after a PyMuPDF update, MuPDF no longer loses the data: the guard can go.
        data = placed_pdf(1)
        doc = pymupdf.open("pdf", data)
        held = held_streams(doc)
        self.assertTrue(held)
        bio = __import__("io").BytesIO()
        save_guard._SAVE(doc, bio, garbage=3)
        del held
        got = look(bio.getvalue())
        self.assertNotEqual(got, look(data), "MuPDF kept the held streams' data")

    def test_guarded_save_keeps_them(self):
        data = placed_pdf()
        for garbage in (2, 3, 4):
            doc = pymupdf.open("pdf", data)
            held = held_streams(doc)
            out = doc.tobytes(garbage=garbage, deflate=True)
            self.assertEqual(look(out), look(data), "garbage=%d" % garbage)
            # (and the document itself, renumbered in place, still has them)
            del held
            self.assertEqual(look(doc.tobytes()), look(data), "garbage=%d, the document" %
                             garbage)
            doc.close()

    def test_nothing_held_nothing_moved(self):
        doc = pymupdf.open("pdf", placed_pdf())
        for p in doc:
            p.get_text()
        self.assertEqual(save_guard.guard(doc), [])
        held = held_streams(doc)
        self.assertTrue(save_guard.guard(doc))
        self.assertEqual(save_guard.guard(doc), [])     # (once moved, there to stay)
        del held

    def test_quick(self):
        d = pymupdf.open()
        for _ in range(200):
            p = d.new_page()
            for k in range(150):
                p.draw_line((k, 10), (k + 40, 300))
            p.insert_text((50, 50), "x")
        doc = pymupdf.open("pdf", d.tobytes())
        for p in doc:
            p.get_text()
        t = time.perf_counter()
        save_guard.guard(doc)
        self.assertLess(time.perf_counter() - t, 0.5)       # (30,000 objects: 0.06 s)


class Paths(unittest.TestCase):
    """Every compacting save the app makes: nothing lost."""

    def setUp(self):
        self.data = placed_pdf()
        self.want = look(self.data)
        self.dir = tempfile.mkdtemp()
        self.src = os.path.join(self.dir, "src.pdf")
        with open(self.src, "wb") as f:
            f.write(self.data)
        self.out = os.path.join(self.dir, "out.pdf")

    def read_out(self):
        with open(self.out, "rb") as f:
            return f.read()

    def test_reduce_size(self):
        from kanzonas import page_tools
        page_tools.compress(self.data, self.out, list(page_tools.COMPRESS)[-1])
        got = look(self.read_out())
        self.assertEqual([g[:2] for g in got], [w[:2] for w in self.want])

    def test_save_as_pdfa(self):
        from kanzonas import pdfa
        pdfa.convert(self.data, self.out)
        got = look(self.read_out())
        self.assertEqual([g[:2] for g in got], [w[:2] for w in self.want])

    def test_combine(self):
        from kanzonas import combine
        combine.combine([self.src, self.src], self.out)
        self.assertEqual(look(self.read_out()), self.want * 2)

    def test_compare(self):
        from kanzonas import compare
        for fn in (compare.compare, compare.compare_text):
            out, _counts = fn(self.data, self.data)
            self.assertTrue(all(t for t, _n, _s in look(out)))

    def test_view(self):
        from kanzonas import capture
        from kanzonas.document_view import DocumentView
        v = DocumentView(self.src)
        v.resize(800, 600)
        v.show()
        APP.processEvents()
        for w in v.pages:
            w._render()
        try:
            snap, _box = capture.snapshot(v.doc[0], pymupdf.Rect(0, 0, 300, 300))
            self.assertIn("placed page text", look(snap)[0][0])
            self.assertEqual(look(v.pages_bytes([0, 1])), self.want)
            v.extract_pages(0, 1, self.out)
            self.assertEqual(look(self.read_out()), self.want)
            # Apply redactions with the clean-up writes the document anew (garbage=4)
            v.mark_redactions(0, [pymupdf.Rect(60, 680, 250, 700)])     # (over nothing)
            v.apply_redactions(scrub=True)
            got = look(v._snapshot())
            self.assertEqual([g[:2] for g in got], [w[:2] for w in self.want])
        finally:
            v.dirty = False
            v.close_doc()


if __name__ == "__main__":
    unittest.main()
