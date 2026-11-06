"""The page's drawing scale where it can't be missed: the Measure tab's large label and the
status bar's (red "Scale not set" without one), both opening Set scale; the notice on the
first measurement of a page with no scale; and View > Show scale bar, drawn on screen only.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_scale_display
"""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import measure as M  # noqa: E402
from kanzonas import scale_display as SD  # noqa: E402
from kanzonas.document_view import DocumentView  # noqa: E402
from kanzonas.main_window import MainWindow  # noqa: E402

QUARTER = '1/4" = 1\'-0"'


def settle():
    for _ in range(5):
        APP.processEvents()


class FakeScaleDialog:
    """Set scale, answered 1:100 in meters for this page."""
    opened = []

    def __init__(self, parent, page, pdf_len=None, page_count=1):
        FakeScaleDialog.opened.append(page.number)
        self.result_scale = (M.scale_from_preset(100), "m", "1:100", False)

    def exec(self):
        return True


class BarSteps(unittest.TestCase):
    """measure.scale_bar: round numbers in the drawing's units, sized to the zoom."""

    def test_feet_and_inches(self):
        seg, labels = M.scale_bar(M.scale_from_preset(48), "ft-in", 0.7, 280)
        self.assertEqual(labels, ["0", "5'", "10'", "15'", "20'"])
        self.assertAlmostEqual(seg, 5 * 12 / 48 * 72 * 0.7)     # 5 ft at 1/4" = 1'-0"
        _seg, labels = M.scale_bar(M.scale_from_preset(48), "ft-in", 1.0, 280)
        self.assertEqual(labels, ["0", "2'", "4'", "6'", "8'"])
        # zoomed in, the steps get shorter, down to inches
        _seg, labels = M.scale_bar(M.scale_from_preset(48), "ft-in", 3.0, 280)
        self.assertEqual(labels, ["0", "1'", "2'", "3'", "4'"])
        _seg, labels = M.scale_bar(M.scale_from_preset(48), "ft-in", 4.0, 280)
        self.assertEqual(labels, ["0", '6"', "1'", "1'-6\"", "2'"])
        _seg, labels = M.scale_bar(M.scale_from_preset(12), "ft-in", 4.0, 280)
        self.assertEqual(labels[-1], '8"')
        _seg, labels = M.scale_bar(M.scale_from_preset(24), "ft-in", 4.0, 280)
        self.assertEqual(labels, ["0", '3"', '6"', '9"', "1'"])

    def test_decimal_feet_and_metric(self):
        _seg, labels = M.scale_bar(M.scale_from_preset(240), "ft", 1.0, 280)
        self.assertEqual(labels, ["0", "10", "20", "30", "40 ft"])
        _seg, labels = M.scale_bar(M.scale_from_preset(100), "m", 1.0, 280)
        self.assertEqual(labels, ["0", "2", "4", "6", "8 m"])
        _seg, labels = M.scale_bar(M.scale_from_preset(100), "m", 4.0, 280)
        self.assertEqual(labels, ["0", "0.5", "1", "1.5", "2 m"])
        # long runs of millimeters are given in meters
        _seg, labels = M.scale_bar(M.scale_from_preset(50), "mm", 1.0, 280)
        self.assertEqual(labels, ["0", "1", "2", "3", "4 m"])
        _seg, labels = M.scale_bar(M.scale_from_preset(5), "mm", 4.0, 280)
        self.assertEqual(labels[-1], "100 mm")

    def test_every_bar_fits_and_none_without_room(self):
        for _label, ratio, unit in M.PRESETS:
            for zoom in (0.1, 0.5, 1, 2, 8, 30):
                got = M.scale_bar(M.scale_from_preset(ratio), unit, zoom, 280)
                if got is not None:
                    seg, labels = got
                    self.assertLessEqual(seg * (len(labels) - 1), 280 + 1e-6)
                    self.assertEqual(labels[0], "0")
        self.assertIsNone(M.scale_bar(M.scale_from_preset(48), "ft-in", 1.0, 0))


class ScaleShown(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        doc = pymupdf.open()
        for i in range(3):
            p = doc.new_page(width=792, height=612)
            p.insert_text((72, 72), "Sheet %d" % (i + 1), fontsize=20)
        M.set_scale(doc[0], M.scale_from_preset(48), "ft-in", QUARTER)
        cls.path = os.path.join(cls.tmp, "set.pdf")
        doc.save(cls.path)
        cls.w = MainWindow()
        cls.w.resize(1366, 768)
        cls.w.show()

    @classmethod
    def tearDownClass(cls):
        cls.w._close_confirmed = True
        cls.w.close()

    def setUp(self):
        FakeScaleDialog.opened = []
        self.w.open_file(self.path)
        settle()
        self.v = self.w.view()
        self.v.goto_page(0)
        settle()
        self.addCleanup(self._close)

    def _close(self):
        self.v.dirty = False
        self.w.close_tab(self.w.tabs.indexOf(self.v))
        settle()

    def red(self, widget):
        return SD.not_set_color() in widget.styleSheet()

    def test_label_follows_the_page(self):
        panel, status = self.w.scale_panel, self.w.scale_label
        self.assertEqual(panel.text(), QUARTER)
        self.assertFalse(self.red(panel.value))
        self.assertIn(QUARTER, status.text())
        self.assertIn("font-weight: bold", status.styleSheet())
        self.assertFalse(self.red(status))
        self.v.goto_page(1)
        settle()
        self.assertEqual(panel.text(), "Scale not set")
        self.assertTrue(self.red(panel.value))
        self.assertIn("not set", status.text())
        self.assertTrue(self.red(status))
        self.assertIn("Set scale", panel.toolTip())

    def test_click_opens_set_scale_and_the_labels_update(self):
        self.v.goto_page(1)
        settle()
        with mock.patch("kanzonas.measure_ui.ScaleDialog", FakeScaleDialog):
            self.w.scale_panel.click()
        self.assertEqual(FakeScaleDialog.opened, [1])
        self.assertTrue(M.get_scale(self.v.doc[1])[3])
        self.assertEqual(self.w.scale_panel.text(), "1:100")
        self.assertFalse(self.red(self.w.scale_label))
        self.v.undo()                           # back to none: red again
        settle()
        self.assertEqual(self.w.scale_panel.text(), "Scale not set")
        self.assertTrue(self.red(self.w.scale_label))
        # the status bar's label opens it too
        with mock.patch("kanzonas.measure_ui.ScaleDialog", FakeScaleDialog):
            QTest.mouseClick(self.w.scale_label, Qt.LeftButton)
        self.assertEqual(FakeScaleDialog.opened, [1, 1])
        self.assertIn("1:100", self.w.scale_label.text())

    def measure(self, index, kind="m_length"):
        pts = [pymupdf.Point(100, 300), pymupdf.Point(300, 300)]
        if kind == "m_count":
            pts = pts[:1]
        self.v._create(index, {"kind": kind, "props": self.v.tool_props(kind), "points": pts,
                               "rect": pymupdf.Rect()})

    def banner_up(self):
        b = getattr(self.v, "_banner", None)
        return b is not None and not b.isHidden() and self.v._banner_kind == "scale"

    def test_first_unscaled_measurement_says_so_once(self):
        self.measure(0)                         # a page with a scale: nothing to say
        self.assertFalse(self.banner_up())
        self.measure(1, "m_count")              # counts don't depend on the scale
        self.assertFalse(self.banner_up())
        self.measure(1)
        self.assertTrue(self.banner_up())
        self.assertIn("Page 2 has no scale", self.v._banner_label.text())
        self.v.hide_banner()
        self.measure(1)                         # once per page
        self.assertFalse(self.banner_up())
        self.measure(2)                         # another page says it again
        self.assertTrue(self.banner_up())
        # its button opens Set scale for that page; the banner goes once it has one
        with mock.patch("kanzonas.measure_ui.ScaleDialog", FakeScaleDialog):
            self.v._banner_btn.click()
        self.assertEqual(FakeScaleDialog.opened, [2])
        self.assertFalse(self.banner_up())
        self.assertTrue(M.get_scale(self.v.doc[2])[3])

    def test_other_banners_are_kept(self):
        self.v.show_banner("The file was repaired")
        said = []
        self.v.statusMessage.connect(said.append)
        self.measure(1)
        self.assertEqual(self.v._banner_label.text(), "The file was repaired")
        self.assertTrue(any("no scale" in m for m in said))

    def set_bar(self, on):
        self.w.a_scale_bar.setChecked(on)
        self.w._toggle_scale_bar()

    def test_scale_bar_only_on_scaled_pages_and_only_when_on(self):
        self.addCleanup(self.set_bar, False)
        self.set_bar(False)
        self.assertFalse(DocumentView.show_scale_bar)
        drawn = []
        own = type(self.v.pages[0])._paint_scale_bar
        with mock.patch.object(type(self.v.pages[0]), "_paint_scale_bar",
                               lambda s, p: (drawn.append(s.index), own(s, p))):
            self.v.pages[0].repaint()
            self.assertEqual(drawn, [])
            self.set_bar(True)
            self.assertEqual(self.w.settings.value("scale_bar"), "true")     # remembered
            self.v.pages[0].repaint()
            self.assertIn(0, drawn)
        pw = self.v.pages[0]
        dpr = pw.devicePixelRatioF()
        pm = self.v.scale_bar_pixmap(0, dpr, pw.width())
        self.assertIsNotNone(pm)
        self.assertIs(self.v.scale_bar_pixmap(0, dpr, pw.width()), pm)       # made once
        self.assertIsNone(self.v.scale_bar_pixmap(1, dpr, pw.width()))       # no scale
        self.assertIsNone(self.v.scale_bar_pixmap(0, dpr, 50))               # too small
        # drawn at the page's bottom left: those pixels change, the top right doesn't
        self.set_bar(False)
        off = pw.grab().toImage()
        self.set_bar(True)
        on = pw.grab().toImage()
        h = off.height()
        corner = [(x, y) for x in range(SD.BAR_MARGIN, SD.BAR_MARGIN + 60, 3)
                  for y in range(h - SD.BAR_MARGIN - 20, h - SD.BAR_MARGIN, 2)]
        self.assertTrue(any(off.pixel(x, y) != on.pixel(x, y) for x, y in corner))
        self.assertEqual(off.pixel(off.width() - 5, 5), on.pixel(on.width() - 5, 5))
        # a new zoom draws it again; so does a change to the page's scale
        self.v.set_zoom(self.v.zoom * 2)
        settle()
        pm2 = self.v.scale_bar_pixmap(0, dpr, pw.width())
        self.assertIsNot(pm2, pm)
        self.v.set_page_scale([0], M.scale_from_preset(100), "m", "1:100")
        self.assertIsNot(self.v.scale_bar_pixmap(0, dpr, pw.width()), pm2)

    def test_night_mode_bar_is_dark(self):
        pm_day = SD.bar_pixmap(M.scale_from_preset(48), "ft-in", 1.0, 1.0, 800, False)
        pm_night = SD.bar_pixmap(M.scale_from_preset(48), "ft-in", 1.0, 1.0, 800, True)
        x, y = pm_day.width() - 3, 3
        self.assertGreater(pm_day.toImage().pixelColor(x, y).lightness(), 200)
        self.assertLess(pm_night.toImage().pixelColor(x, y).lightness(), 60)

    def test_not_in_prints(self):
        from kanzonas.print_dialog import PrintDialog
        self.addCleanup(self.set_bar, False)
        self.set_bar(False)
        dlg = PrintDialog(None, self.v)
        self.addCleanup(dlg.deleteLater)
        plain = dlg._page_image(0, 72)
        self.set_bar(True)
        self.assertEqual(dlg._page_image(0, 72), plain)


class Width(unittest.TestCase):
    def test_measure_tab_fits_a_1366_screen(self):
        w = MainWindow()
        w.resize(1366, 768)
        w.show()
        settle()
        self.addCleanup(lambda: (setattr(w, "_close_confirmed", True), w.close()))
        r = w.ribbon
        i = next(k for k in range(r.count()) if r.tabText(k) == "Measure")
        r.setCurrentIndex(i)                    # (measured as shown, with its icons)
        settle()
        self.assertLess(r.widget(i).widget().sizeHint().width(), 1366 - 40)
        # the Measure tab's scale: as tall as the large buttons, a fixed width (no shifting
        # from page to page), its switch for the scale bar beside 'Set scale'
        self.assertEqual(w.scale_panel.height(), 44)
        self.assertIs(w.scale_panel.bar.defaultAction(), w.a_scale_bar)


if __name__ == "__main__":
    unittest.main()
