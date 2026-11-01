"""1.7: a page is drawn in two layers, its content (rendered once per zoom and kept) and its
markups (drawn over a copy of it by MuPDF). The result must be the same pixels as rendering
the whole page in one go, for every kind of page and option; a markup edit must not render
the content again, a content edit must; Ctrl+wheel zooming shows the page as it was, scaled,
and draws it sharp once the wheel stops; thumbnails come from the renders already made."""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np  # noqa: E402
import pymupdf  # noqa: E402
from PySide6.QtCore import QRect  # noqa: E402
from PySide6.QtGui import QImage  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import annotations as A  # noqa: E402
from kanzonas import page_widget as PW  # noqa: E402
from kanzonas import render_layers as RL  # noqa: E402
from kanzonas.document_view import DocumentView  # noqa: E402


def marked_pdf():
    """Pages with every kind of thing that's drawn: text and drawings under a Multiply
    highlight, a see-through Multiply fill, a text box, a form field, a markup hidden on
    screen, a page turned 90 degrees, a page whose crop box doesn't start at 0, 0."""
    d = pymupdf.open()
    for n in range(3):
        p = d.new_page(width=612, height=792)
        p.insert_text((72, 100), "Text under a yellow highlight, page %d" % (n + 1), fontsize=18)
        p.draw_rect(pymupdf.Rect(60, 300, 400, 500), color=(0, 0, 0.6), fill=(0.7, 0.9, 0.7),
                    width=1.5)
        for k in range(40):
            p.draw_line((60 + 8 * k, 520), (300, 700), color=(0.3, 0, 0), width=0.2)
        if n == 1:
            p.set_rotation(90)
        if n == 2:
            p.set_cropbox(pymupdf.Rect(30, 40, 580, 760))
    for p in d:
        m = p.derotation_matrix
        p.add_highlight_annot(pymupdf.Rect(70, 82, 400, 106) * m if p.rotation else
                              pymupdf.Rect(70, 82, 400, 106))
        a = p.add_rect_annot(pymupdf.Rect(100, 320, 350, 450))
        a.set_colors(stroke=(1, 0, 0), fill=(0, 0, 1))
        a.set_opacity(0.45)
        a.set_blendmode("Multiply")
        a.update()
        p.add_freetext_annot(pymupdf.Rect(80, 560, 330, 610), "A text box", fontsize=14)
        hid = p.add_circle_annot(pymupdf.Rect(400, 100, 500, 200))
        hid.set_flags(pymupdf.PDF_ANNOT_IS_HIDDEN)
        hid.update()
        w = pymupdf.Widget()
        w.field_name = "field%d" % p.number
        w.field_type = pymupdf.PDF_WIDGET_TYPE_TEXT
        w.rect = pymupdf.Rect(360, 600, 560, 630)
        w.field_value = "filled in"
        p.add_widget(w)
    path = os.path.join(tempfile.mkdtemp(), "marked.pdf")
    d.save(path)
    return path


def expected(page, s, markups=True, night=False, thin=True):
    """The page as one render (the way it was drawn before 1.7), as a 32-bit QImage."""
    with PW.screen_lines(thin):
        pm = page.get_displaylist(annots=markups).get_pixmap(matrix=pymupdf.Matrix(s, s),
                                                              alpha=False)
    if night:
        data = PW.night_samples(pm.samples, pm.width, pm.height, pm.stride)
        img = QImage(data, pm.width, pm.height, pm.width * 3, QImage.Format_RGB888)
    else:
        img = QImage(pm.samples, pm.width, pm.height, pm.stride, QImage.Format_RGB888)
    return img.convertToFormat(QImage.Format_RGB32)


def same(test, got, want, msg=""):
    got = got.convertToFormat(QImage.Format_RGB32)
    test.assertEqual((got.width(), got.height()), (want.width(), want.height()), msg)
    test.assertTrue(got == want, "pixels differ " + msg)


class Layers(unittest.TestCase):
    def setUp(self):
        self.addCleanup(setattr, DocumentView, "night_mode", False)
        self.addCleanup(setattr, DocumentView, "thin_lines", True)
        self.addCleanup(setattr, DocumentView, "show_markups", True)

    def view(self, path=None, size=(900, 700)):
        v = DocumentView(path or marked_pdf())
        v.resize(*size)
        v.show()
        APP.processEvents()
        self.addCleanup(v.close_doc)
        return v

    def render(self, v, i):
        w = v.pages[i]
        w._pix = None
        w._render()
        return w._pix.toImage()

    def test_pages_are_drawn_as_one_render_draws_them(self):
        v = self.view()
        for night, thin, markups in ((False, True, True), (True, True, True),
                                     (False, False, True), (False, True, False)):
            DocumentView.night_mode, DocumentView.thin_lines = night, thin
            DocumentView.show_markups = markups
            v.refresh_markup_display()
            for z in (1.0, 1.37):
                v.set_zoom(z)
                for i in range(3):
                    w = v.pages[i]
                    s = v.zoom * w.devicePixelRatioF()
                    same(self, self.render(v, i),
                         expected(v.doc[i], s, markups, night, thin),
                         f"page {i} zoom {z} night {night} thin {thin} markups {markups}")

    def test_high_dpi_screens(self):
        v = self.view()
        v.set_zoom(0.8)
        for dpr in (1.25, 1.5, 2.0):
            with mock.patch.object(PW.PageWidget, "devicePixelRatioF", lambda self, d=dpr: d):
                for i in range(3):
                    img = self.render(v, i)
                    same(self, img, expected(v.doc[i], v.zoom * dpr), f"dpr {dpr} page {i}")
                    self.assertEqual(v.pages[i]._pix.devicePixelRatio(), dpr)

    def test_a_markup_edit_keeps_the_content_render(self):
        v = self.view()
        v.set_zoom(1.0)
        self.render(v, 0)
        s = v.zoom * v.pages[0].devicePixelRatioF()
        content = v._rc.get(0, s, None, True)
        self.assertIsNotNone(content)
        dl = v._dlists[0]
        v._create(0, {"kind": "rect", "props": dict(A.DEFAULTS["rect"]),
                      "rect": pymupdf.Rect(200, 200, 260, 260)})
        self.assertIsNone(v.pages[0]._pix)                       # drawn again ...
        with mock.patch.object(RL, "render", side_effect=AssertionError("content rendered")):
            img = self.render(v, 0)                              # ... without the content
        self.assertIs(v._rc.get(0, s, None, True), content)
        self.assertIs(v._dlists[0], dl)
        same(self, img, expected(v.doc[0], s), "after a markup was added")
        # moved, restyled, deleted: the same
        xref = max(x for x, *_ in v.doc[0].annot_xrefs())
        page = v.doc[0]
        v.modify(lambda: A.shift_in_place(page, xref, pymupdf.Point(30, 10)), [0])
        with mock.patch.object(RL, "render", side_effect=AssertionError("content rendered")):
            img = self.render(v, 0)
        same(self, img, expected(v.doc[0], s), "after a markup was moved")

    def test_a_content_edit_renders_the_content_again(self):
        v = self.view()
        v.set_zoom(1.0)
        self.render(v, 0)
        s = v.zoom * v.pages[0].devicePixelRatioF()
        old = v._rc.get(0, s, None, True)
        page = v.doc[0]
        v.modify(lambda: page.draw_rect(pymupdf.Rect(400, 400, 500, 500), color=(1, 0, 0),
                                        fill=(1, 0.5, 0)), [0])
        self.assertIsNone(v._rc.get(0, s, None, True))
        self.assertNotIn(0, v._dlists)
        img = self.render(v, 0)
        self.assertIsNot(v._rc.get(0, s, None, True), old)
        same(self, img, expected(v.doc[0], s), "after the content changed")

    def test_a_picture_changed_in_place_counts_as_content(self):
        # the page's own stream stays the same: what its resources reach is in the key
        d = pymupdf.open()
        p = d.new_page()
        pm = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 20, 20), False)
        pm.set_rect(pm.irect, (255, 0, 0))
        xref = p.insert_image(pymupdf.Rect(100, 100, 300, 300), pixmap=pm)
        before = RL.content_key(p)
        p.add_rect_annot(pymupdf.Rect(10, 10, 50, 50))
        self.assertEqual(RL.content_key(p), before)              # a markup: not content
        pm.set_rect(pm.irect, (0, 0, 255))
        p.replace_image(xref, pixmap=pm)
        self.assertNotEqual(RL.content_key(p), before)
        before = RL.content_key(p)
        p.set_cropbox(pymupdf.Rect(10, 10, 500, 700))
        self.assertNotEqual(RL.content_key(p), before)

    def test_undo_and_redo(self):
        v = self.view()
        v.set_zoom(1.0)
        want0 = expected(v.doc[0], v.zoom)
        self.render(v, 0)
        v._create(0, {"kind": "rect", "props": dict(A.DEFAULTS["rect"]),
                      "rect": pymupdf.Rect(200, 200, 260, 260)})
        want1 = expected(v.doc[0], v.zoom)
        same(self, self.render(v, 0), want1)
        v.undo()
        same(self, self.render(v, 0), want0, "after undo")
        v.redo()
        same(self, self.render(v, 0), want1, "after redo")
        page = v.doc[0]
        v.modify(lambda: page.draw_circle((300, 300), 50, color=(0, 1, 0)), [0])
        want2 = expected(v.doc[0], v.zoom)
        same(self, self.render(v, 0), want2)
        v.undo()
        same(self, self.render(v, 0), want1, "after undoing a content edit")

    def test_tiles_of_a_big_page(self):
        d = pymupdf.open()
        p = d.new_page(width=2592, height=1728)
        for k in range(30):
            p.insert_text((100 + 70 * k, 200 + 40 * k), "Label %d" % k, fontsize=12)
            p.draw_rect(pymupdf.Rect(100 + 70 * k, 220 + 40 * k, 160 + 70 * k, 250 + 40 * k),
                        color=(0, 0, 1), fill=(0.9, 0.9, 0.2))
        p.add_highlight_annot(pymupdf.Rect(100, 185, 900, 205))
        path = os.path.join(tempfile.mkdtemp(), "big.pdf")
        d.save(path)
        v = self.view(path)
        v.set_zoom(3.0)
        w = v.pages[0]
        self.assertTrue(w._tiled())
        v.verticalScrollBar().setValue(w.y() + 300)
        v.horizontalScrollBar().setValue(200)
        v.viewport().repaint()
        APP.processEvents()
        mine = [k for k in v._tiles if k[0] == 0]
        self.assertTrue(mine)

        def check(why):
            full = v.doc[0].get_displaylist(annots=True)
            for key in [k for k in v._tiles if k[0] == 0]:
                pix, x, y = v._tiles[key]
                s = key[1]
                clip = pymupdf.Rect(x, y, x + pix.width(), y + pix.height()) / s
                with PW.screen_lines(True):
                    pm = full.get_pixmap(matrix=pymupdf.Matrix(s, s), clip=clip, alpha=False)
                want = QImage(pm.samples, pm.width, pm.height, pm.stride,
                              QImage.Format_RGB888).convertToFormat(QImage.Format_RGB32)
                same(self, pix.toImage(), want, f"tile {key} {why}")
        check("first drawn")
        # a markup added: the tiles are drawn again from the content kept
        v._create(0, {"kind": "rect", "props": dict(A.DEFAULTS["rect"]),
                      "rect": pymupdf.Rect(300, 250, 600, 400)})
        with mock.patch.object(RL, "render", side_effect=AssertionError("content rendered")):
            v.viewport().repaint()
            APP.processEvents()
        check("after a markup was added")

    def test_split_view_follows_markup_edits(self):
        v = self.view()
        m = DocumentView.mirror(v)
        m.resize(900, 700)
        m.show()
        APP.processEvents()
        m.set_zoom(1.0)
        self.render(m, 0)
        v._create(0, {"kind": "rect", "props": dict(A.DEFAULTS["rect"]),
                      "rect": pymupdf.Rect(200, 200, 260, 260)})
        APP.processEvents()
        same(self, self.render(m, 0), expected(v.doc[0], m.zoom), "split view")

    def test_layers_shown_or_hidden_redraw_the_content(self):
        d = pymupdf.open()
        p = d.new_page()
        ocg = d.add_ocg("Walls", on=True)
        p.draw_rect(pymupdf.Rect(100, 100, 300, 300), color=(0, 0, 0), fill=(0, 0, 1), oc=ocg)
        path = os.path.join(tempfile.mkdtemp(), "layers.pdf")
        d.save(path)
        v = self.view(path)
        v.set_zoom(1.0)
        on = self.render(v, 0)
        self.assertEqual(on.pixelColor(200, 200).blue(), 255)
        number = v.layer_configs()[0]["number"]
        v.set_layer(number, False)
        off = self.render(v, 0)
        self.assertEqual(off.pixelColor(200, 200).lightness(), 255)    # the paper
        same(self, off, expected(v.doc[0], v.zoom * v.pages[0].devicePixelRatioF()))

    def test_a_scan_is_decoded_once_for_its_tiles(self):
        d = pymupdf.open()
        p = d.new_page(width=2500, height=2000)
        y, x = np.mgrid[0:4000, 0:5000]
        img = ((x // 7 + y // 5) % 256).astype(np.uint8)          # a 20-megapixel gray scan
        pm = pymupdf.Pixmap(pymupdf.csGRAY, 5000, 4000, img.tobytes(), False)
        p.insert_image(p.rect, stream=pm.tobytes("jpg"))
        path = os.path.join(tempfile.mkdtemp(), "scan.pdf")
        d.save(path)
        v = self.view(path)
        v.set_zoom(0.9)                     # (drawn at half size: decoded at 1/2)
        w = v.pages[0]
        self.assertTrue(w._tiled())
        # (a slow render of its tiles is what has the picture decoded once: as if slow here)
        with mock.patch.object(PW, "PREDECODE_AFTER_S", 0):
            v.viewport().repaint()
            APP.processEvents()
        self.assertEqual({(k[0], k[2]) for k in v._decoded}, {(0, 1)})
        self.assertTrue([k for k in v._tiles if k[0] == 0])
        # another zoom: decoded at its size before its tiles are rendered
        v.set_zoom(1.8)
        v.viewport().repaint()
        APP.processEvents()
        self.assertEqual({(k[0], k[2]) for k in v._decoded}, {(0, 1), (0, 0)})
        s = round(v.zoom * w.devicePixelRatioF(), 5)
        self.assertTrue([k for k in v._tiles if k[0] == 0 and k[1] == s])


class Zooming(unittest.TestCase):
    def view(self):
        v = DocumentView(marked_pdf())
        v.resize(900, 700)
        v.show()
        APP.processEvents()
        self.addCleanup(v.close_doc)
        v.set_zoom(1.0)
        v.viewport().repaint()
        APP.processEvents()
        return v

    def settle(self, v):
        import time
        t = time.monotonic()
        while time.monotonic() - t < 10 and (v._zooming or
                                              getattr(v, "_render_wait", None)):
            APP.processEvents()
        APP.processEvents()

    def test_wheel_zoom_shows_the_page_scaled_then_sharp(self):
        v = self.view()
        w = v.pages[0]
        self.assertIsNotNone(w._pix)
        v._note_render_cost(0, 1.0)                 # (as a heavy sheet)
        with mock.patch.object(PW.PageWidget, "_render",
                               side_effect=AssertionError("rendered while zooming")):
            v._quick_zoom()
            v.set_zoom(1.2)
            v.viewport().repaint()
            APP.processEvents()
        self.assertIsNone(w._pix)
        img = w.grab(QRect(0, 0, 200, 200)).toImage()     # the old bitmap, scaled
        self.assertTrue(any(img.pixelColor(x, y).lightness() < 200
                            for x in range(0, 200, 4) for y in range(0, 200, 4)))
        self.settle(v)
        self.assertIsNotNone(w._pix)
        s = v.zoom * w.devicePixelRatioF()
        same(self, w._pix.toImage(), expected(v.doc[0], s), "sharp after the wheel stopped")

    def test_light_pages_are_drawn_at_once(self):
        v = self.view()
        w = v.pages[0]
        v._quick_zoom()
        v.set_zoom(1.0)
        v._costs.clear() if getattr(v, "_costs", None) else None
        w._preview = None
        v.set_zoom(1.3)
        v.viewport().repaint()
        APP.processEvents()
        self.assertIsNotNone(w._pix)                # no stand-in: rendered right away

    def test_a_heavy_page_is_drawn_after_showing_it_as_it_was(self):
        v = self.view()
        w = v.pages[0]
        v._note_render_cost(0, 1.0)
        v.set_zoom(1.25)                            # (a zoom button, not the wheel)
        v.viewport().repaint()
        self.assertIsNone(w._pix)                   # (drawn once the event loop runs)
        self.assertIn(w, v._render_wait)
        self.settle(v)
        self.assertIsNotNone(w._pix)


class Thumbnails(unittest.TestCase):
    def test_from_the_render_on_screen(self):
        v = DocumentView(marked_pdf())
        v.resize(900, 700)
        v.show()
        APP.processEvents()
        self.addCleanup(v.close_doc)
        page = v.doc[0]
        s = min(120 / page.rect.width, 160 / page.rect.height)
        pm = page.get_pixmap(matrix=pymupdf.Matrix(s, s), annots=True)
        before = QImage(pm.samples, pm.width, pm.height, pm.stride, QImage.Format_RGB888)
        # not drawn on screen yet: as before
        v._rc.clear()
        v._dlists.clear()
        got = PW.thumbnail(v, 0, s)
        self.assertTrue(got.convertToFormat(QImage.Format_RGB32) ==
                        before.convertToFormat(QImage.Format_RGB32))
        # drawn on screen: scaled down from that render, without rendering the page again
        v.pages[0]._render()
        with mock.patch.object(pymupdf.Page, "get_pixmap", side_effect=AssertionError):
            got = PW.thumbnail(v, 0, s)
        self.assertEqual((got.width(), got.height()), (before.width(), before.height()))

        def arr(img):
            img = img.convertToFormat(QImage.Format_RGB888)
            b = bytes(img.constBits())[: img.bytesPerLine() * img.height()]
            return np.frombuffer(b, np.uint8).reshape(img.height(), img.bytesPerLine())[
                :, : img.width() * 3].astype(int)
        self.assertLess(np.abs(arr(got) - arr(before)).mean(), 12)


if __name__ == "__main__":
    unittest.main()
