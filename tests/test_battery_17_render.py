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


if __name__ == "__main__":
    unittest.main()
