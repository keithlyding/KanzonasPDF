"""View > Show line weights (kanzonas/line_weights.py). Off, every line of the page's drawing is
drawn thin on screen, one pixel wide, whatever its width; its fills, text, pictures, patterns
and hidden layers are as they were, and markups keep their widths. Only the screen changes:
the document, printing and export keep the true widths.

cloydcc-dev, issue #120, 22 Nov 2026: "In autocad it is an option as "display lineweight". Is
there any way to toggle this in kanzonas? ... just a simple toggle in the view ribbon tab or a
command option". The owner, 22 Nov: yes, on the View tab, named Show line weights.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_line_weights
"""
import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import line_weights as LW  # noqa: E402
from kanzonas.document_view import DocumentView  # noqa: E402

BLACK, WHITE = (0, 0, 0), (255, 255, 255)


def a_drawing():
    """A page with a 12 pt line across at y=100, a blue fill, text, a picture and a line on a
    layer (its xref second)."""
    d = pymupdf.open()
    p = d.new_page(width=300, height=300)
    p.draw_line((10, 100), (290, 100), color=(0, 0, 0), width=12)
    p.draw_rect((20, 20, 70, 70), color=None, fill=(0, 0, 1))
    p.insert_text((20, 280), "Lineweights", fontsize=24)
    pm = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 4, 4), False)
    pm.clear_with(200)
    p.insert_image((200, 200, 260, 260), pixmap=pm)
    ocg = d.add_ocg("Walls", on=True)
    p.draw_line((10, 160), (290, 160), color=(1, 0, 0), width=10, oc=ocg)
    return d, ocg


class Thin(unittest.TestCase):
    def setUp(self):
        self.d, self.ocg = a_drawing()
        self.p = self.d[0]
        self.dl = self.p.get_displaylist(annots=False)
        self.t = LW.thin(self.dl)
        self.before, self.after = self.dl.get_pixmap(), self.t.get_pixmap()

    def test_a_thick_line_is_drawn_thin(self):
        self.assertIsNot(self.t, self.dl)
        self.assertEqual(self.before.pixel(150, 95), BLACK)
        self.assertEqual(self.after.pixel(150, 95), WHITE)
        self.assertNotEqual(self.after.pixel(150, 100), WHITE)      # (still drawn, thin)

    def test_fills_text_and_pictures_are_as_they_were(self):
        for x, y in [(45, 45), (230, 230)] + [(x, y) for x in range(20, 200, 3)
                                               for y in range(258, 286, 3)]:
            self.assertEqual(self.after.pixel(x, y), self.before.pixel(x, y), (x, y))

    def test_a_hidden_layer_stays_hidden(self):
        self.assertEqual(self.after.pixel(150, 155), WHITE)     # (thin now: off the line)
        for c in self.d.layer_ui_configs():
            self.d.set_layer_ui_config(c["number"], 2)
        t = LW.thin(self.p.get_displaylist(annots=False)).get_pixmap()
        self.assertEqual(t.pixel(150, 160), WHITE)

    def test_the_page_isnt_changed(self):
        self.assertEqual(self.p.get_pixmap().pixel(150, 95), BLACK)

    def test_quick_on_a_big_sheet(self):
        d = pymupdf.open()
        p = d.new_page(width=2000, height=2000)
        sh = p.new_shape()
        for i in range(20_000):
            x, y = (i * 37) % 1990, (i * 91) % 1990
            sh.draw_line((x, y), (x + 10, y + 5))
            sh.finish(width=1 + i % 3, color=(0, 0, 0))
        sh.commit()
        dl = p.get_displaylist(annots=False)
        t = time.perf_counter()
        LW.thin(dl)
        self.assertLess(time.perf_counter() - t, 2.0)      # (about 0.07 s here)


class InTheWindow(unittest.TestCase):
    def setUp(self):
        from kanzonas.main_window import MainWindow
        d, _ocg = a_drawing()
        p = d[0]
        p.add_line_annot((10, 220), (290, 220)).set_border(width=8)
        p.load_annot(p.first_annot.xref).update()
        self.path = os.path.join(tempfile.mkdtemp(), "plan.pdf")
        d.save(self.path)
        self.addCleanup(lambda: [setattr(x, "_close_confirmed", True) or x.close()
                                 for x in __import__("kanzonas.main_window").main_window
                                 .windows()])
        old = DocumentView.line_weights
        self.addCleanup(lambda: setattr(DocumentView, "line_weights", old))
        w = self.w = MainWindow()
        self.addCleanup(lambda: w.settings.remove("line_weights"))
        w.resize(1000, 900)
        w.show()
        w.open_file(self.path)
        v = self.v = w.view()
        v.set_zoom(1.0)
        self.settle()

    def settle(self):
        end = time.monotonic() + 1.0
        while time.monotonic() < end:
            APP.processEvents()

    def at(self, x, y):
        pw = self.v.pages[0]
        img = pw.grab().toImage()
        sx = img.width() / self.v.doc[0].rect.width
        c = img.pixelColor(int(x * sx), int(y * sx))
        return c.red(), c.green(), c.blue()

    def toggle(self, on):
        if self.w.a_line_weights.isChecked() != on:
            self.w.a_line_weights.trigger()
        self.settle()

    def test_on_by_default_and_on_the_view_tab(self):
        self.assertTrue(self.w.a_line_weights.isChecked())
        self.assertTrue(DocumentView.line_weights)
        view = [a.menu() for a in self.w.menuBar().actions() if a.text() == "&View"][0]
        self.assertIn(self.w.a_line_weights, view.actions())
        # (on the View tab: under the arrow of its Display group, next to Free pan)
        from kanzonas.ribbon import GroupArrow
        arrows = [g for g in self.w.findChildren(GroupArrow)
                  if self.w.a_line_weights in g.menu().actions()]
        self.assertEqual(len(arrows), 1)
        self.assertIn(self.w.a_free_pan, arrows[0].menu().actions())

    def test_off_every_line_is_thin_and_on_again_as_drawn(self):
        self.assertEqual(self.at(150, 96), BLACK)
        self.toggle(False)
        self.assertEqual(self.at(150, 96), WHITE)
        self.assertNotEqual(self.at(150, 100), WHITE)
        self.assertEqual(self.at(45, 45), (0, 0, 255))          # (the fill as it was)
        self.toggle(True)
        self.assertEqual(self.at(150, 96), BLACK)

    def test_zoomed_in_the_tiles_are_drawn_thin_too(self):
        self.v.set_zoom(4.0)
        self.settle()
        self.v.pages[0].update()
        self.settle()
        self.assertEqual(self.at(150, 96), BLACK)
        self.toggle(False)
        self.assertEqual(self.at(150, 96), WHITE)
        self.assertNotEqual(self.at(150, 100), WHITE)

    def test_markups_keep_their_widths(self):
        thick = self.at(150, 218)
        self.toggle(False)
        self.assertEqual(self.at(150, 218), thick)

    def test_the_document_printing_and_export_keep_the_widths(self):
        self.toggle(False)
        self.assertFalse(self.v.dirty)
        self.assertEqual(self.v.doc[0].get_pixmap().pixel(150, 95), BLACK)

    def test_the_choice_is_remembered(self):
        self.toggle(False)
        self.assertEqual(self.w.settings.value("line_weights"), "false")


if __name__ == "__main__":
    unittest.main()
