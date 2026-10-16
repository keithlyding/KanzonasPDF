"""Night mode: pages drawn with their lightness inverted and hues kept; only the screen."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas.document_view import DocumentView  # noqa: E402
from kanzonas.main_window import MainWindow  # noqa: E402
from kanzonas.page_widget import night_samples  # noqa: E402


def pdf():
    d = pymupdf.open()
    p = d.new_page(width=300, height=300)
    p.draw_line((20, 150), (280, 150), color=(0, 0, 0), width=6)            # black line
    p.draw_line((150, 20), (150, 280), color=(1, 0, 0), width=6)            # red line
    p.draw_rect(pymupdf.Rect(200, 200, 260, 260), color=None, fill=(1, 1, 0))  # yellow box
    path = os.path.join(tempfile.mkdtemp(), "n.pdf")
    d.save(path)
    return path


class NightSamples(unittest.TestCase):
    def test_black_and_white_swap_and_hues_are_kept(self):
        px = bytes([0, 0, 0, 255, 255, 255, 255, 0, 0, 255, 255, 0, 128, 0, 0, 90, 90, 90])
        out = night_samples(px, 6, 1, 18)
        rgb = [tuple(out[i:i + 3]) for i in range(0, 18, 3)]
        self.assertEqual(rgb[0], (255, 255, 255))     # black -> white
        self.assertEqual(rgb[1], (0, 0, 0))           # white -> black
        self.assertEqual(rgb[2], (255, 0, 0))         # pure red stays red
        self.assertEqual(rgb[3], (255, 255, 0))       # yellow stays yellow
        self.assertEqual(rgb[4], (255, 127, 127))     # dark red -> light red (same hue)
        self.assertEqual(rgb[5], (165, 165, 165))     # dark gray -> light gray

    def test_stride_padding_is_ignored(self):
        row = bytes([0, 0, 0, 255, 255, 255]) + bytes([7, 7])     # 2 px + 2 padding bytes
        out = night_samples(row * 2, 2, 2, 8)
        self.assertEqual(len(out), 12)
        self.assertEqual(tuple(out[:3]), (255, 255, 255))
        self.assertEqual(tuple(out[6:9]), (255, 255, 255))


class NightView(unittest.TestCase):
    def tearDown(self):
        DocumentView.night_mode = False

    def pixel(self, v, x, y):
        w = v.pages[0]
        w._pix = None
        w._render()
        img = w._pix.toImage()
        c = img.pixelColor(int(x * v.zoom), int(y * v.zoom))
        return c.red(), c.green(), c.blue()

    def test_page_is_drawn_white_on_black_with_colors_kept(self):
        v = DocumentView(pdf())
        v.resize(600, 600)
        v.show()
        v.set_zoom(1.0)
        APP.processEvents()
        self.addCleanup(v.close_doc)
        self.assertEqual(self.pixel(v, 40, 40), (255, 255, 255))          # paper
        self.assertEqual(self.pixel(v, 60, 150), (0, 0, 0))               # black line
        DocumentView.night_mode = True
        v.redraw_pages()
        self.assertEqual(self.pixel(v, 40, 40), (0, 0, 0))                # paper now black
        self.assertEqual(self.pixel(v, 60, 150), (255, 255, 255))         # line now white
        r, g, b = self.pixel(v, 150, 60)
        self.assertGreater(r, 200)
        self.assertLess(max(g, b), 60)                                    # red still red
        r, g, b = self.pixel(v, 230, 230)
        self.assertGreater(min(r, g), 200)
        self.assertLess(b, 60)                                            # yellow still yellow

    def test_window_toggle_is_remembered_and_redraws(self):
        w = MainWindow()
        w.show()
        w.open_file(pdf())
        APP.processEvents()
        self.addCleanup(lambda: (setattr(w, "_close_confirmed", True), w.close()))
        w.a_night.setChecked(True)
        w._toggle_night()
        self.assertTrue(DocumentView.night_mode)
        self.assertEqual(w.settings.value("night_mode"), "true")
        self.assertEqual(self.pixel(w.view(), 40, 40), (0, 0, 0))
        w.a_night.setChecked(False)
        w._toggle_night()
        self.assertFalse(DocumentView.night_mode)
        self.assertEqual(self.pixel(w.view(), 40, 40), (255, 255, 255))

    def test_export_and_print_rendering_are_not_affected(self):
        v = DocumentView(pdf())
        self.addCleanup(v.close_doc)
        DocumentView.night_mode = True
        pix = v.doc[0].get_pixmap(dpi=36)        # what print/export/thumbnails render from
        self.assertEqual(pix.pixel(2, 2), (255, 255, 255))


if __name__ == "__main__":
    unittest.main()
