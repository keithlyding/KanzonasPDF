"""OCR in less memory (the owner: "How do we get OCR memory down?").

A page is never rendered whole any more: each tile is rendered when it's read, from the page's
display list, on the GUI thread (PyMuPDF), and read by the engine in a worker thread while the
next one is rendered. A tile of a scanned page is exactly that part of the page's whole image,
so the engine reads the same pixels as before. ONNX Runtime's sessions keep no memory pattern
(RapidOCR already turns its arena off); after a job the memory freed goes back to the system,
and the engine itself is let go once unused for a while.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_ocr_memory
"""
import os
import sys
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np  # noqa: E402
import pymupdf  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import ocr  # noqa: E402


def whole_image(page, rotation, dpi):
    """The page's whole image as OCR used to make it (one gray pixmap)."""
    r = page.rect
    scale = min(dpi / 72, ocr.MAX_SIDE_PX / max(r.width, r.height))
    m = pymupdf.Matrix(scale, scale) * pymupdf.Matrix(rotation)
    pm = page.get_pixmap(matrix=m, annots=False, alpha=False, colorspace=pymupdf.csGRAY)
    return np.frombuffer(pm.samples, np.uint8).reshape(pm.height, pm.stride)[:, :pm.width]


def scanned_sheet(width=24 * 72, height=18 * 72):
    """A sheet scanned at 100 dpi: a picture with some writing on it, as a scan is."""
    d = pymupdf.open()
    p = d.new_page(width=width, height=height)
    for k in range(40):
        p.insert_text((40 + (k % 4) * 400, 40 + k * 30), "Sheet note %d: verify in field" % k,
                      fontsize=14)
        p.draw_line((20, 30 + k * 31), (width - 20, 60 + k * 29), width=0.6)
    pm = p.get_pixmap(dpi=100, colorspace=pymupdf.csGRAY)
    scan = pymupdf.open()
    s = scan.new_page(width=width, height=height)
    s.insert_image(s.rect, pixmap=pm)
    return scan


class Tiles(unittest.TestCase):
    def test_a_scans_tiles_are_its_whole_image_pixel_for_pixel(self):
        scan = scanned_sheet()
        page = scan[0]
        for rotation in (0, 90, 180, 270):
            r = ocr.Rendering(page, rotation, dpi=200)
            old = whole_image(page, rotation, 200)
            self.assertEqual((r.height, r.width), old.shape)
            n = 0
            for y0 in ocr._starts(r.height):
                for x0 in ocr._starts(r.width):
                    tile = r.tile(x0, y0)
                    self.assertTrue(np.array_equal(
                        tile, old[y0:y0 + ocr.TILE_PX, x0:x0 + ocr.TILE_PX]), (rotation, x0, y0))
                    n += 1
            self.assertGreater(n, 4)
            # the coordinates map back as before
            p = r.to_display(r.width / 2, r.height / 2)
            self.assertAlmostEqual(p.x, page.rect.width / 2, delta=1)
            self.assertAlmostEqual(p.y, page.rect.height / 2, delta=1)

    def test_a_drawings_tiles_are_where_its_whole_image_is(self):
        # (lines drawn into a tile are antialiased a hair differently where MuPDF clips them:
        # a few gray levels on a few pixels, never a line moved)
        d = pymupdf.open()
        p = d.new_page(width=36 * 72, height=24 * 72)
        for k in range(60):
            p.draw_line((10, 10 + k * 28), (36 * 72 - 10, 24 * 72 - 10 - k * 25), width=1)
        r = ocr.Rendering(p, 90, dpi=150)
        old = whole_image(p, 90, 150)
        worst = []
        for y0 in ocr._starts(r.height):
            for x0 in ocr._starts(r.width):
                tile = r.tile(x0, y0).astype(int)
                part = old[y0:y0 + ocr.TILE_PX, x0:x0 + ocr.TILE_PX].astype(int)
                self.assertEqual(tile.shape, part.shape)
                diff = np.abs(tile - part)
                worst.append(int(diff.max()))
                self.assertLess((diff > 0).mean(), 0.1)         # (lines' edge pixels only)
        self.assertLessEqual(max(worst), 32)                      # (an eighth of black)

    def test_the_whole_page_is_never_drawn_at_once(self):
        scan = scanned_sheet()
        r = ocr.Rendering(scan[0], dpi=200)
        sizes, threads = [], set()
        tile = ocr.Rendering.tile

        def watched(self, x0, y0, w=ocr.TILE_PX, h=ocr.TILE_PX):
            out = tile(self, x0, y0, w, h)
            sizes.append(out.shape)
            threads.add(threading.get_ident())
            return out

        read_in = set()

        def fake_read(image):
            read_in.add(threading.get_ident())
            return [([[100, 100], [300, 100], [300, 130], [100, 130]], "word", 0.9)]
        with mock.patch.object(ocr.Rendering, "tile", watched), \
                mock.patch.object(ocr, "_read", fake_read), \
                ThreadPoolExecutor(max_workers=1) as pool:
            res = ocr.recognize(r, executor=pool)
        self.assertTrue(sizes)
        self.assertLessEqual(max(max(s) for s in sizes), ocr.TILE_PX)
        self.assertEqual(threads, {threading.get_ident()})      # PyMuPDF: this thread only
        self.assertNotIn(threading.get_ident(), read_in)         # the engine: the worker
        self.assertEqual(len(res), len(sizes))                   # one line kept per tile

    def test_in_a_worker_or_here_the_same_lines(self):
        scan = scanned_sheet()

        def fake_read(image):
            # a line at each tile's corners and middle: those in the shared margins are kept
            # by one tile only
            h, w = image.shape[:2]
            out = []
            for x, y in ((20, 20), (w // 2, h // 2), (w - 60, h - 30), (w - 60, 20)):
                out.append(([[x, y], [x + 40, y], [x + 40, y + 12], [x, y + 12]],
                            "%d,%d,%d" % (x, y, int(image[0, 0, 0])), 0.9))
            return out
        r = ocr.Rendering(scan[0], dpi=200)
        with mock.patch.object(ocr, "_read", fake_read):
            here = ocr.recognize(r)
            with ThreadPoolExecutor(max_workers=1) as pool:
                there = ocr.recognize(r, executor=pool)
        self.assertEqual(here, there)
        centres = [(round(sum(p[0] for p in b) / 4), round(sum(p[1] for p in b) / 4))
                   for b, _t, _c in here]
        self.assertEqual(len(centres), len(set(centres)))

    def test_cancel_stops_between_tiles(self):
        scan = scanned_sheet()
        r = ocr.Rendering(scan[0], dpi=200)
        calls = []

        def fake_read(image):
            calls.append(1)
            return []
        with mock.patch.object(ocr, "_read", fake_read):
            ocr.recognize(r, cancelled=lambda: len(calls) >= 2)
        self.assertEqual(len(calls), 2)

    def test_released_after_reading(self):
        scan = scanned_sheet()
        r = ocr.Rendering(scan[0], dpi=100)
        self.assertIsNotNone(r.image)
        r.release()
        self.assertIsNone(r.image)
        self.assertIsNone(r._dl)
        self.assertIsNotNone(r.to_display(10, 10))


class Engine(unittest.TestCase):
    def test_sessions_keep_no_memory_pattern_or_arena(self):
        # (the module that makes the sessions: utils in RapidOCR 1.2, utils.infer_engine
        # from 1.3 on; the patch must land where they are made, or it does nothing)
        module = ocr.session_module()
        if module is None:
            self.skipTest("RapidOCR isn't installed here")
        ocr._lean_sessions()
        ocr._lean_sessions()                    # (once is enough: not wrapped twice)
        options = module.SessionOptions()
        self.assertFalse(options.enable_mem_pattern)
        self.assertFalse(options.enable_cpu_mem_arena)
        self.assertTrue(module.SessionOptions.kz_lean)

    def test_the_session_module_is_found_in_every_layout(self):
        # RapidOCR 1.2: utils is one file holding SessionOptions; 1.3 and later: a package
        # whose infer_engine holds it
        made = []

        def options():
            made.append(1)

        one_file = mock.MagicMock(spec=["SessionOptions"], SessionOptions=options)
        package_engine = mock.MagicMock(spec=["SessionOptions"], SessionOptions=options)
        package = mock.MagicMock(spec=["infer_engine"], infer_engine=package_engine)
        rapid_old = mock.MagicMock(utils=one_file)
        rapid_new = mock.MagicMock(utils=package)
        old = {"rapidocr_onnxruntime": rapid_old, "rapidocr_onnxruntime.utils": one_file,
               "rapidocr_onnxruntime.utils.infer_engine": None}
        new = {"rapidocr_onnxruntime": rapid_new, "rapidocr_onnxruntime.utils": package,
               "rapidocr_onnxruntime.utils.infer_engine": package_engine}
        with mock.patch.dict(sys.modules, old):
            self.assertIs(ocr.session_module(), one_file)
        with mock.patch.dict(sys.modules, new):
            self.assertIs(ocr.session_module(), package_engine)
        nothing = {"rapidocr_onnxruntime": None,
                   "rapidocr_onnxruntime.utils": None,
                   "rapidocr_onnxruntime.utils.infer_engine": None}
        with mock.patch.dict(sys.modules, nothing):
            self.assertIsNone(ocr.session_module())

    def test_the_engine_is_let_go_only_when_unused_a_while(self):
        with mock.patch.object(ocr, "_engine", object()), \
                mock.patch.object(ocr, "_last_used", time.monotonic()):
            self.assertFalse(ocr.release_engine(ocr.ENGINE_IDLE_S))
            self.assertIsNotNone(ocr._engine)
            self.assertTrue(ocr.release_engine(0))
            self.assertIsNone(ocr._engine)
        self.assertFalse(ocr.release_engine(0))         # (none loaded)
        ocr.trim_memory()                               # (harmless anywhere)


if __name__ == "__main__":
    unittest.main()
