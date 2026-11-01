"""What the 1.7 break-it battery on layered rendering, instant zoom and progressive drawing
found, fixed: what a page shows must be what a fresh one-pass render of it shows.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_battery_17_render
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402
from PySide6.QtGui import QImage  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import page_widget as PW  # noqa: E402
from kanzonas.document_view import DocumentView  # noqa: E402


def expected(page, s, markups=True, night=False, thin=True):
    """The page as one render (markups, night mode and thin lines as the view has them), as a
    32-bit QImage."""
    with PW.screen_lines(thin):
        pm = page.get_displaylist(annots=markups).get_pixmap(matrix=pymupdf.Matrix(s, s),
                                                              alpha=False)
    if night:
        data = PW.night_samples(pm.samples, pm.width, pm.height, pm.stride)
        img = QImage(data, pm.width, pm.height, pm.width * 3, QImage.Format_RGB888)
    else:
        img = QImage(pm.samples, pm.width, pm.height, pm.stride, QImage.Format_RGB888)
    return img.convertToFormat(QImage.Format_RGB32)


def layered_pdf():
    """A page with a layer (a blue box), some text and a highlight over it."""
    d = pymupdf.open()
    p = d.new_page()
    ocg = d.add_ocg("Walls", on=True)
    p.draw_rect(pymupdf.Rect(100, 100, 300, 300), color=(0, 0, 0), fill=(0, 0, 1), oc=ocg)
    p.insert_text((72, 72), "Some words", fontsize=14)
    p.add_highlight_annot(pymupdf.Rect(70, 58, 160, 76))
    path = os.path.join(tempfile.mkdtemp(), "layered.pdf")
    d.save(path)
    return path


class SplitView(unittest.TestCase):
    """The second (split) view draws the same document: a view option (night mode, thin
    lines, Show markups) or a layer shown or hidden must redraw it too, not only the tabs."""

    def setUp(self):
        self.addCleanup(setattr, DocumentView, "night_mode", False)
        self.addCleanup(setattr, DocumentView, "thin_lines", True)
        self.addCleanup(setattr, DocumentView, "show_markups", True)

    def shows(self, v):
        """What page 0 of view v shows once painted, against a fresh render of it."""
        w = v.pages[0]
        v.viewport().repaint()
        APP.processEvents()
        if w._pix is None:              # (not painted: the offscreen dock may be too small)
            w._render()
        s = v.zoom * w.devicePixelRatioF()
        want = expected(v.doc[0], s, v.show_markups, v.night_mode, v.thin_lines)
        return w._pix.toImage().convertToFormat(QImage.Format_RGB32) == want

    def test_the_split_view_follows_view_options_and_layers(self):
        from kanzonas.main_window import MainWindow
        win = MainWindow()
        win.resize(1200, 1000)
        win.show()
        win.open_file(layered_pdf())
        APP.processEvents()
        v = win.view()
        self.addCleanup(lambda: (setattr(v, "dirty", False),
                                 setattr(win, "_close_confirmed", True), win.close()))
        win.a_split.setChecked(True)
        win._toggle_split()
        APP.processEvents()
        sv = win._split_view
        self.assertIsNotNone(sv)
        for view in (v, sv):
            view.set_zoom(1.0)
        APP.processEvents()
        self.assertTrue(self.shows(v) and self.shows(sv))

        number = v.layer_configs()[0]["number"]
        v.set_layer(number, False)                      # (Layers panel: a layer hidden)
        self.assertTrue(self.shows(v))
        self.assertTrue(self.shows(sv), "split view after a layer was hidden")
        v.set_layer(number, True)
        self.assertTrue(self.shows(sv), "split view after a layer was shown")

        win.a_night.setChecked(True)
        win._toggle_night()
        self.assertTrue(self.shows(v))
        self.assertTrue(self.shows(sv), "split view in night mode")
        win.a_night.setChecked(False)
        win._toggle_night()
        self.assertTrue(self.shows(sv), "split view after night mode")

        win.a_thin_lines.setChecked(False)
        win._toggle_thin_lines()
        self.assertTrue(self.shows(sv), "split view without Enhance thin lines")
        win.a_thin_lines.setChecked(True)
        win._toggle_thin_lines()

        win.a_show_markups.setChecked(False)
        win._toggle_show_markups()
        self.assertTrue(self.shows(v))
        self.assertTrue(self.shows(sv), "split view with markups hidden")
        win.a_show_markups.setChecked(True)
        win._toggle_show_markups()
        self.assertTrue(self.shows(sv), "split view with markups shown again")


def pages_pdf(n=12, size=(612, 792)):
    d = pymupdf.open()
    for k in range(n):
        p = d.new_page(width=size[0], height=size[1])
        p.insert_text((72, 100), "Page %d" % (k + 1), fontsize=30)
        p.draw_rect(pymupdf.Rect(60, 200, 500, 600), color=(0, 0, 1), fill=(0.8, 0.9, 1))
    path = os.path.join(tempfile.mkdtemp(), "pages.pdf")
    d.save(path)
    return path


class ContentKeys(unittest.TestCase):
    def test_pages_with_nothing_kept_are_not_read_to_compare(self):
        """A layer shown, Show markups, or an edit seen by the split view checks every page's
        content key: a page whose renders were let go (scrolled far away) is not read again
        for it (each check reads the page's drawing and everything it uses)."""
        from unittest import mock
        from kanzonas import render_layers as RL
        v = DocumentView(pages_pdf(40, (300, 200)))
        v.resize(900, 700)
        v.show()
        APP.processEvents()
        self.addCleanup(v.close_doc)
        v.set_zoom(1.0)
        for i in range(len(v.pages)):          # every page visited
            v.goto_page(i)
            v.viewport().repaint()
            APP.processEvents()
        v.goto_page(0)
        v.viewport().repaint()
        APP.processEvents()
        kept = {i for i in range(len(v.pages))
                if i in v._dlists or v._rc.has_page(i) or any(k[0] == i for k in v._tiles)}
        self.assertLess(len(kept), len(v.pages))
        calls = []
        real = RL.content_key
        with mock.patch.object(RL, "content_key", lambda page: calls.append(page.number) or
                               real(page)):
            v._redraw_all()                     # (as after a layer was shown or hidden)
        self.assertLessEqual(set(calls), kept)
        # and the pages are still drawn as a fresh render draws them
        for i in (0, len(v.pages) - 1):
            v.goto_page(i)
            v.viewport().repaint()
            APP.processEvents()
            w = v.pages[i]
            self.assertIsNotNone(w._pix)
            self.assertTrue(w._pix.toImage().convertToFormat(QImage.Format_RGB32) ==
                            expected(v.doc[i], v.zoom * w.devicePixelRatioF()))


class Memory(unittest.TestCase):
    def test_all_documents_together_keep_a_bounded_amount_of_content_renders(self):
        """Each document view keeps its pages' content renders up to CONTENT_BYTES; many
        documents open must not keep that much each."""
        from unittest import mock
        from kanzonas import render_layers as RL
        per, total = 8 * 1024 * 1024, 12 * 1024 * 1024
        views = []
        with mock.patch.object(RL, "CONTENT_BYTES", per), \
                mock.patch.object(RL, "CONTENT_BYTES_ALL", total):
            for _n in range(4):
                v = DocumentView(pages_pdf(4))
                v.resize(900, 700)
                v.show()
                APP.processEvents()
                self.addCleanup(v.close_doc)
                views.append(v)
                v.set_zoom(1.5)                 # (a page: about 3 MB of pixels)
                for i in range(4):
                    v.pages[i]._render()
                self.assertLessEqual(v._rc.bytes, per)
            together = sum(v._rc.bytes for v in views)
            self.assertLessEqual(together, total)
            self.assertGreater(views[-1]._rc.bytes, 0)  # (the one in use keeps its own)
            # what was let go is drawn again as before
            v = views[0]
            w = v.pages[0]
            w._pix = None
            w._render()
            self.assertTrue(w._pix.toImage().convertToFormat(QImage.Format_RGB32) ==
                            expected(v.doc[0], v.zoom * w.devicePixelRatioF()))


class Forms(unittest.TestCase):
    def test_a_field_shown_on_several_pages_shows_its_new_value_on_each(self):
        """A form field can have a widget on several pages (a name repeated at the top of each
        page): filling it in on one page changes what every page shows."""
        d = pymupdf.open()
        for _n in range(3):
            p = d.new_page(width=400, height=300)
            w = pymupdf.Widget()
            w.field_name = "Name"
            w.field_type = pymupdf.PDF_WIDGET_TYPE_TEXT
            w.rect = pymupdf.Rect(50, 50, 300, 80)
            w.field_value = "first"
            p.add_widget(w)
        path = os.path.join(tempfile.mkdtemp(), "fields.pdf")
        d.save(path)
        v = DocumentView(path)
        v.resize(900, 1200)
        v.show()
        APP.processEvents()
        self.addCleanup(v.close_doc)
        self.addCleanup(lambda: setattr(v, "dirty", False))
        v.set_zoom(1.0)
        for w in v.pages:
            w._render()
        xref = next(v.doc[0].widgets()).xref
        v._set_field(0, xref, "second")
        v.viewport().repaint()
        APP.processEvents()
        for i, w in enumerate(v.pages):
            self.assertEqual(next(v.doc[i].widgets()).field_value, "second")
            if w._pix is None:
                w._render()
            self.assertTrue(w._pix.toImage().convertToFormat(QImage.Format_RGB32) ==
                            expected(v.doc[i], v.zoom * w.devicePixelRatioF()),
                            "page %d shows the old value" % i)
        v.undo()
        v.viewport().repaint()
        APP.processEvents()
        for i, w in enumerate(v.pages):
            if w._pix is None:
                w._render()
            self.assertTrue(w._pix.toImage().convertToFormat(QImage.Format_RGB32) ==
                            expected(v.doc[i], v.zoom * w.devicePixelRatioF()),
                            "page %d after undo" % i)


class HighDpiTiles(unittest.TestCase):
    def test_the_last_partly_covered_device_pixels_are_painted(self):
        """At 150% screen scaling a widget pixel covers one and a half device pixels: a repaint
        of an area ending inside a device pixel (a scroll exposes a strip) must still paint
        that last device pixel, also where it's the first of the next tile (it kept what was
        on the screen before: a line of old pixels)."""
        from unittest import mock
        from PySide6.QtCore import QRect
        from PySide6.QtGui import QColor, QPainter
        d = pymupdf.open()
        p = d.new_page(width=2592, height=1728)
        p.draw_rect(p.rect, color=None, fill=(0, 0, 1))
        path = os.path.join(tempfile.mkdtemp(), "big.pdf")
        d.save(path)
        dpr = 1.5
        with mock.patch.object(PW.PageWidget, "devicePixelRatioF", lambda self: dpr):
            v = DocumentView(path)
            v.resize(900, 700)
            v.show()
            APP.processEvents()
            self.addCleanup(v.close_doc)
            v.progressive = False
            v.set_zoom(3.0)
            w = v.pages[0]
            self.assertTrue(w._tiled())
            img = QImage(1200, 1200, QImage.Format_RGB32)
            img.setDevicePixelRatio(dpr)
            img.fill(QColor(255, 0, 255))           # (what was on the screen before)
            painter = QPainter(img)
            w._paint_tiles(painter, QRect(0, 0, 342, 342))  # device pixels 0 to 512
            painter.end()
            for x, y in ((511, 100), (512, 100), (100, 512), (512, 512)):
                self.assertEqual(img.pixelColor(x, y).name(), "#0000ff", (x, y))
            # and what's drawn later for an area is what a repaint of it asks for
            v.progressive = True
            v._note_render_cost(0, 1.0)
            v._tiles.clear()
            v._rc.clear()
            with mock.patch.object(PW.PageWidget, "visibleRegion",
                                   lambda self: __import__("PySide6.QtGui").QtGui.QRegion(
                                       QRect(0, 0, 342, 342))):
                self.assertTrue(w.render_step())
                self.assertFalse(w.render_step())   # (nothing left: no repaint waits for it)
            self.assertIn((0, round(v.zoom * dpr, 5), 1, 1), v._tiles)

    def test_the_page_edge_is_painted_to_its_last_device_pixel(self):
        """A page 3890 widget pixels wide at 125% is 4862.5 device pixels: the tiles must
        reach the half-covered last one (an unpainted line along the right and bottom edges
        kept what was on the screen before)."""
        import math
        from unittest import mock
        from PySide6.QtCore import QRect
        from PySide6.QtGui import QColor, QPainter
        d = pymupdf.open()
        p = d.new_page(width=2592, height=1728)
        p.draw_rect(p.rect, color=None, fill=(0, 0, 1))
        path = os.path.join(tempfile.mkdtemp(), "big.pdf")
        d.save(path)
        for dpr in (1.25, 1.75):
            with mock.patch.object(PW.PageWidget, "devicePixelRatioF", lambda self, d=dpr: d):
                v = DocumentView(path)
                v.resize(900, 700)
                v.show()
                APP.processEvents()
                self.addCleanup(v.close_doc)
                v.progressive = False
                v.set_zoom(1.501)
                w = v.pages[0]
                self.assertTrue(w._tiled())
                width, height = w.width(), w.height()
                self.assertNotEqual(width * dpr, int(width * dpr))
                img = QImage(math.ceil(width * dpr), math.ceil(height * dpr), QImage.Format_RGB32)
                img.setDevicePixelRatio(dpr)
                img.fill(QColor(255, 0, 255))
                painter = QPainter(img)
                w._paint_tiles(painter, QRect(0, 0, width, height))
                painter.end()
                self.assertEqual(img.pixelColor(img.width() - 1, 100).name(), "#0000ff", dpr)
                self.assertEqual(img.pixelColor(100, img.height() - 1).name(), "#0000ff", dpr)


class ContentKeyReach(unittest.TestCase):
    def test_objects_referenced_with_another_generation_are_in_the_key(self):
        """A file updated in place can reference an object as "5 1 R": what it draws is part
        of the page's content all the same."""
        from kanzonas import render_layers as RL
        d = pymupdf.open()
        p = d.new_page()
        fx = d.get_new_xref()
        d.update_object(fx, "<</Type/XObject/Subtype/Form/BBox[0 0 100 100]>>")
        d.update_stream(fx, b"1 0 0 rg 0 0 100 100 re f")
        d.xref_set_key(p.xref, "Resources", "<</XObject<</F1 %d 1 R>>>>" % fx)
        c = d.get_new_xref()
        d.update_object(c, "<<>>")
        d.update_stream(c, b"q 1 0 0 1 100 100 cm /F1 Do Q")
        d.xref_set_key(p.xref, "Contents", "%d 0 R" % c)
        self.assertEqual(p.get_pixmap().pixel(150, 692), (255, 0, 0))
        before = RL.content_key(p)
        d.update_stream(fx, b"0 0 1 rg 0 0 100 100 re f")
        self.assertEqual(p.get_pixmap().pixel(150, 692), (0, 0, 255))
        self.assertNotEqual(RL.content_key(p), before)


class FailedRender(unittest.TestCase):
    def test_a_heavy_page_mupdf_cant_draw_ends_white_not_blurred(self):
        # (drawn later, its render failed: the stand-in stayed up for good)
        from unittest import mock
        v = DocumentView(layered_pdf())
        v.resize(900, 700)
        v.show()
        APP.processEvents()
        self.addCleanup(v.close_doc)
        v.set_zoom(1.0)
        v.viewport().repaint()
        APP.processEvents()
        w = v.pages[0]
        v._note_render_cost(0, 1.0)             # (as a heavy sheet)
        v.set_zoom(1.25)
        v.viewport().repaint()
        self.assertIn(w, v._render_wait)
        with mock.patch.object(PW.PageWidget, "_render", side_effect=RuntimeError("bad")):
            v._render_tick()
            self.assertEqual(w._no_defer, round(1.25 * w.devicePixelRatioF(), 5))
            img = QImage(w.size(), QImage.Format_RGB32)
            img.fill(0xff00ff)
            w.render(img)                       # (the direct path: white)
        self.assertNotIn(w, v._render_wait)
        c = img.pixelColor(w.width() // 2, w.height() // 2)
        self.assertEqual((c.red(), c.green(), c.blue()), (255, 255, 255))


if __name__ == "__main__":
    unittest.main()
