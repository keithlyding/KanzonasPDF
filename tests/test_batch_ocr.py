"""Batch processing's OCR step is Recognize text's own OCR (ocr.read_page, which
DocumentView.run_ocr uses too), not a copy of it: the same text layer from the same file; each
tile drawn from the page's display list on the GUI thread (PyMuPDF isn't thread-safe), the
engine reading it in the worker; never the whole page drawn at once; the memory given back
after the run (ocr.job_done). The engine is replaced by one that answers from the pixels it's
given, so the same pictures give the same lines.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_batch_ocr
"""
import os
import shutil
import sys
import tempfile
import threading
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np  # noqa: E402
import pymupdf  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import batch as B  # noqa: E402
from kanzonas import ocr  # noqa: E402
from kanzonas.document_view import DocumentView  # noqa: E402

MAIN = threading.get_ident()


def pixel_engine(image):
    """A line around the tile's ink, its 'text' made from the ink's size and amount: what it
    reads depends only on the pixels."""
    gray = image[:, :, 0]
    ys, xs = np.nonzero(gray < 128)
    if not len(xs):
        return []
    x0, x1, y0, y1 = int(xs.min()), int(xs.max()), int(ys.min()), int(ys.max())
    text = "ink %dx%d %d" % (x1 - x0, y1 - y0, len(xs))
    box = [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]
    return [(box, text, 0.95)]


def scans(path):
    """Three pages that are only pictures: words, a big sheet (many tiles), sideways words."""
    d = pymupdf.open()
    for w, h, rot in ((612, 792, 0), (1728, 1224, 0), (612, 792, 90)):
        src = pymupdf.open()
        sp = src.new_page(width=w, height=h)
        sp.insert_text((72, 140), "Invoice 4471 total 99.00", fontsize=18, rotate=rot)
        sp.insert_text((900 if w > 1000 else 72, 700), "Sheet note", fontsize=14)
        pix = sp.get_pixmap(dpi=100, colorspace=pymupdf.csGRAY)
        page = d.new_page(width=w, height=h)
        page.insert_image(page.rect, stream=pix.tobytes("png"))
        src.close()
    d.save(path)
    d.close()


def text_layer(doc):
    return [(round(w[0]), round(w[1]), w[4]) for p in doc for w in p.get_text("words")]


class SameAsRecognizeText(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="kz-batch-ocr-")
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.path = os.path.join(self.dir, "scans.pdf")
        scans(self.path)

    def by_the_app(self, accuracy):
        v = DocumentView(self.path)
        self.addCleanup(lambda: (setattr(v, "dirty", False), v.close_doc()))
        with mock.patch.object(ocr, "_read", pixel_engine):
            v.run_ocr(list(range(v.doc.page_count)), accuracy)
        return text_layer(v.doc)

    def by_the_batch(self, accuracy):
        out = os.path.join(self.dir, "out-" + accuracy)
        drawn, read = set(), set()
        tile = ocr.Rendering.tile

        def watched_tile(r, x0, y0, w=ocr.TILE_PX, h=ocr.TILE_PX):
            drawn.add(threading.get_ident())
            self.assertLessEqual(max(w, h), ocr.TILE_PX)      # (never the whole page)
            return tile(r, x0, y0, w, h)

        def watched_engine(image):
            read.add(threading.get_ident())
            return pixel_engine(image)
        with mock.patch.object(ocr.Rendering, "tile", watched_tile), \
                mock.patch.object(ocr, "_read", watched_engine), \
                mock.patch.object(ocr, "job_done") as done:
            b = B.Batch([self.path], [B.step("ocr", accuracy=accuracy)],
                        {"mode": "folder", "folder": out})
            b.run_all()
        self.assertEqual(b.results[0].status, B.DONE, b.results[0].details())
        self.assertEqual(drawn, {MAIN})             # PyMuPDF: the GUI thread only
        self.assertTrue(read and MAIN not in read)  # the engine: the worker
        done.assert_called_once()
        with pymupdf.open(os.path.join(out, "scans.pdf")) as doc:
            return text_layer(doc)

    def test_the_same_text_layer(self):
        for accuracy in ("auto", "high"):
            with self.subTest(accuracy=accuracy):
                app = self.by_the_app(accuracy)
                self.assertGreater(len(app), 6)
                self.assertEqual(self.by_the_batch(accuracy), app)

    def test_one_reader_for_both(self):
        # (batch.py has no page-reading code of its own any more)
        import inspect
        src = inspect.getsource(B)
        for name in ("needs_sharper", "upside_down", "mostly_vertical", "Rendering("):
            self.assertNotIn(name, src)
        self.assertIn("ocr.read_page(", inspect.getsource(DocumentView.run_ocr))


if __name__ == "__main__":
    unittest.main()
