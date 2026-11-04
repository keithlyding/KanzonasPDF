"""Moving a picture drawn in its own clipping window moves the window with it.

"Print to PDF" of a protected file writes each page as picture strips, each one
q <x y w h> re W n <picture> Q . Moving a strip used to leave its clip behind: the picture
went out of its own window and everything on it vanished.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_move_clipped_picture
"""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf as F
from PySide6.QtWidgets import QApplication, QMessageBox

from kanzonas import page_objects as po
from kanzonas.document_view import DocumentView

APP = QApplication.instance() or QApplication([])

RED = (220, 30, 30)
BLUE = (30, 30, 220)


def _picture(color):
    pix = F.Pixmap(F.csRGB, F.IRect(0, 0, 40, 30), False)
    pix.set_rect(pix.irect, color)
    pix.set_rect(F.IRect(0, 12, 40, 18), (0, 0, 0))
    return pix


def _strips(page, colors, text=False, shared=False):
    """One picture per color, side by side, each in its own clip like a print driver writes
    them (shared: all under one clip; text: a word inside each strip's window). Page 400 x
    300; strip i covers x 20 + 120 i .. + 100, y 40..140 (top-left coordinates)."""
    doc = page.parent
    for color in colors:
        page.insert_image(F.Rect(0, 0, 10, 10), pixmap=_picture(color))
    names = {img[0]: img[7] for img in page.get_images(full=True)}
    names = [names[x] for x in sorted(names)]
    if text:
        page.insert_font(fontname="helv")
    draws = [b"q 100 0 0 100 %d 160 cm /%s Do Q\n" % (20 + i * 120, names[i].encode())
             for i in range(len(colors))]
    if shared:
        body = b"q 0 0 400 300 re W n\n" + b"".join(draws) + b"Q\n"
    else:
        body = b""
        for i, dr in enumerate(draws):
            x = 20 + i * 120
            word = b"BT /helv 9 Tf 1 0 0 1 %d 200 Tm (x) Tj ET\n" % (x + 5) if text else b""
            body += b"q %d 160 100 100 re W n\n" % x + dr + word + b"Q\n"
    xref = page.get_contents()[0]
    for other in page.get_contents()[1:]:
        doc.update_stream(other, b"")
    doc.update_stream(xref, body)


def _count(page, color, rect=None):
    pm = page.get_pixmap(dpi=36, clip=rect)
    n = 0
    for y in range(pm.height):
        for x in range(pm.width):
            r, g, b = pm.pixel(x, y)[:3]
            n += abs(r - color[0]) < 40 and abs(g - color[1]) < 40 and abs(b - color[2]) < 40
    return n


def _pictures(page):
    return [it for it in po.Objects(page).items if it["kind"] == "picture"]


class MoveClipped(unittest.TestCase):
    def setUp(self):
        self.doc = F.open()
        self.page = self.doc.new_page(width=400, height=300)

    def tearDown(self):
        self.doc.close()

    def test_strip_moves_whole_with_its_window(self):
        _strips(self.page, [RED, BLUE])
        red0, blue0 = _count(self.page, RED), _count(self.page, BLUE)
        self.assertGreater(red0, 100)
        red = [it for it in _pictures(self.page) if it["rect"].x0 < 100][0]
        po.transform(self.page, [red["n"]], F.Matrix(1, 0, 0, 1, 30, 120))
        self.assertEqual(_count(self.page, RED), red0)              # all of it still shows
        self.assertEqual(_count(self.page, BLUE), blue0)            # the other stays
        self.assertEqual(_count(self.page, RED, F.Rect(20, 40, 50, 160)), 0)   # gone from there
        self.assertGreater(_count(self.page, RED, F.Rect(50, 160, 150, 260)), red0 * 0.9)

    def test_moving_again_folds_into_one_wrapper(self):
        _strips(self.page, [RED, BLUE])
        red0 = _count(self.page, RED)
        n = [it for it in _pictures(self.page) if it["rect"].x0 < 100][0]["n"]
        for _ in range(5):
            po.transform(self.page, [n], F.Matrix(1, 0, 0, 1, 0, 4))
        data = po._contents(self.page)
        self.assertEqual(data.count(b" cm\nq 20 160 100 100 re W n"), 1)    # not nested 5 deep
        self.assertEqual(_count(self.page, RED), red0)
        moved = [it for it in _pictures(self.page) if it["n"] == n][0]
        self.assertAlmostEqual(moved["rect"].x0, 20, delta=0.1)
        self.assertAlmostEqual(moved["rect"].y0, 60, delta=0.1)

    def test_objects_returned_match_a_fresh_read(self):
        _strips(self.page, [RED, BLUE, (30, 160, 30)])
        objs = po.Objects(self.page)
        ns = [it["n"] for it in objs.items if it["kind"] == "picture"][:2]
        got = po.transform(self.page, ns, F.Matrix(1, 0, 0, 1, 10, 50), objs)
        fresh = po.scan(po._contents(self.page))
        self.assertIsNotNone(got)
        self.assertEqual(len(got.found), len(fresh))
        for a, b in zip(got.found, fresh):
            self.assertEqual((a["start"], a["end"]), (b["start"], b["end"]))
            for x, y in zip(tuple(a["ctm"]), tuple(b["ctm"])):
                self.assertAlmostEqual(x, y, places=3)

    def test_shared_window_stays(self):
        """Pictures under one clip together: the clip isn't one picture's to take along."""
        _strips(self.page, [RED, BLUE], shared=True)
        before = po._contents(self.page)
        red = [it for it in _pictures(self.page) if it["rect"].x0 < 100][0]
        po.transform(self.page, [red["n"]], F.Matrix(1, 0, 0, 1, 30, 20))
        data = po._contents(self.page)
        self.assertEqual(data.count(b"re W n"), 1)
        self.assertTrue(data.startswith(b"q 0 0 400 300 re W n"))    # the clip wasn't wrapped
        self.assertNotEqual(data, before)

    def test_window_with_text_stays(self):
        """A clip that also holds text isn't the picture's own (moving it would take the
        text along)."""
        _strips(self.page, [RED], text=True)
        pic = _pictures(self.page)[0]
        po.transform(self.page, [pic["n"]], F.Matrix(1, 0, 0, 1, 30, 20))
        data = po._contents(self.page)
        self.assertTrue(data.startswith(b"q 20 160 100 100 re W n"))
        self.assertIn("x", self.page.get_text())

    def test_shape_in_its_own_window(self):
        """Not only pictures: a filled shape alone in its clip moves with it."""
        self.page.draw_rect((0, 0, 1, 1), color=None, fill=(1, 1, 1))      # (a contents stream)
        xref = self.page.get_contents()[0]
        self.doc.update_stream(xref, b"q 50 150 100 100 re W n\n1 0 0 rg 0 0 400 300 re f\nQ\n")
        red0 = _count(self.page, (255, 0, 0))
        n = [it for it in po.Objects(self.page).items if it["kind"] == "shape"][0]["n"]
        po.transform(self.page, [n], F.Matrix(1, 0, 0, 1, 100, 0))
        self.assertEqual(_count(self.page, (255, 0, 0)), red0)
        self.assertEqual(_count(self.page, (255, 0, 0), F.Rect(50, 50, 150, 150)), 0)


class MoveClippedInApp(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(patch.stopall)
        for name in ("information", "warning", "critical"):
            patch.object(QMessageBox, name, return_value=None).start()

    def test_move_and_undo(self):
        path = Path(self.tmp.name) / "strips.pdf"
        doc = F.open()
        page = doc.new_page(width=400, height=300)
        _strips(page, [RED, BLUE])
        red0 = _count(page, RED)
        doc.save(path)
        doc.close()
        view = DocumentView(str(path))
        self.addCleanup(view.close_doc)
        view.resize(600, 500)
        view.show()
        APP.processEvents()
        red = [it for it in view.content_objects(0).items
               if it["kind"] == "picture" and it["rect"].x0 < 100][0]
        view.select_objects(0, [red])
        old = view.selected_objects_rect()
        view.move_objects(old + (40, 100, 40, 100))
        page = view.doc[0]
        self.assertEqual(_count(page, RED), red0)
        self.assertEqual(_count(page, RED, F.Rect(20, 40, 60, 140)), 0)
        view.undo()
        page = view.doc[0]
        self.assertEqual(_count(page, RED), red0)
        self.assertGreater(_count(page, RED, F.Rect(20, 40, 120, 140)), red0 * 0.9)


if __name__ == "__main__":
    unittest.main()
