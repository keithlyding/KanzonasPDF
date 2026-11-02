"""What the 1.6.3 break-it battery of everyday markup editing (Standard and Hand mouse modes)
found, fixed.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_battery_163_markups
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import annotations as A  # noqa: E402


class MaskAndCircleStyles(unittest.TestCase):
    """The Mask tool's style has no outline. Properties (and Preferences > Markup styles, the
    same panel) gave it a black one at the first change of anything else (its fill, its
    opacity...), and offered no "No border" to take it away again; the Circle tool, unlike
    the Ellipse it draws, had no "No border" either."""

    def panel(self, kind):
        from kanzonas.properties import PropertiesPanel
        p = PropertiesPanel()
        self.addCleanup(p.deleteLater)
        got = []
        p.propsChanged.connect(got.append)
        p.show_target(kind, dict(A.DEFAULTS[kind]))
        return p, got

    def test_changing_the_mask_style_keeps_it_without_an_outline(self):
        p, got = self.panel("mask")
        self.assertTrue(p.no_stroke.isVisibleTo(p))
        self.assertTrue(p.no_stroke.isChecked())
        p.opacity.setValue(50)
        p._emit()
        self.assertIsNone(got[-1]["stroke"])
        self.assertEqual(got[-1]["fill"], "#ffffff")

    def test_circle_offers_no_border_as_the_ellipse_does(self):
        p, got = self.panel("circle")
        self.assertTrue(p.no_stroke.isVisibleTo(p))
        p.no_stroke.setChecked(True)
        p._emit()
        self.assertIsNone(got[-1]["stroke"])


class PreferencesStyles(unittest.TestCase):
    def test_markup_styles_lists_each_tool_once(self):
        """A trimmed cloud's own kind (opencloud, made by CAD Trim, not a tool) was listed as a
        second "Cloud" in Preferences > Markup styles."""
        from kanzonas.main_window import MainWindow
        from kanzonas.preferences import PreferencesDialog
        w = MainWindow()
        self.addCleanup(w.deleteLater)
        d = PreferencesDialog(w)
        self.addCleanup(d.deleteLater)
        kinds = [d.kinds.item(i).data(0x0100) for i in range(d.kinds.count())]
        names = [d.kinds.item(i).text() for i in range(d.kinds.count())]
        self.assertNotIn("opencloud", kinds)
        self.assertEqual(len(names), len(set(names)), names)
        for k in ("circle", "mask", "arc", "curve"):
            self.assertIn(k, kinds)


class ShapesButton(unittest.TestCase):
    def test_the_shapes_button_tooltip_names_every_shape(self):
        """The classic toolbar's Shapes button listed the shapes before 1.6.3: no circle,
        mask, arc or curve."""
        from kanzonas.main_window import MainWindow
        w = MainWindow()
        self.addCleanup(w.deleteLater)
        tip = w.shapes_btn.toolTip().lower()
        for a in w.shapes_btn.menu().actions():
            self.assertIn(a.text().replace("&", "").lower(), tip)


if __name__ == "__main__":
    unittest.main()
