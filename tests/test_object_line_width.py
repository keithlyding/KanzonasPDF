"""Properties > Line width on the page's own lines (Edit objects, CAD mode): the selected shapes
with an outline show their width as drawn on the page, and a width typed redraws them that wide
(points on the page, whatever scale they're drawn at), in one undo step, the rest of the page
as it was. Several of different widths show a blank width; the one typed goes to all.

The owner, 22 Nov 2026 (issue #120, from @cloydcc-dev: he looked in Properties and found only
Rotation): "Can we already individually change line weights? If not, let's add that too".

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_object_line_width
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import main_window, mouse_modes, page_objects  # noqa: E402

# a 3 pt line, a 2 pt line drawn at twice the scale (1 unit wide: 2 pt on the page), a filled
# square with no outline, and a 4 pt blue line
CONTENT = (b"0 0 0 RG 3 w 100 100 m 400 100 l S "
           b"q 2 0 0 2 0 0 cm 1 w 50 100 m 200 100 l S Q "
           b"0 0 1 rg 100 300 50 50 re f "
           b"0 0 1 RG 4 w 100 500 m 400 500 l S")


def sheet():
    d = pymupdf.open()
    p = d.new_page()
    x = d.get_new_xref()
    d.update_object(x, "<<>>")
    d.update_stream(x, CONTENT)
    d.xref_set_key(p.xref, "Contents", "%d 0 R" % x)
    path = os.path.join(tempfile.mkdtemp(), "plan.pdf")
    d.save(path)
    return path


class LineWidth(unittest.TestCase):
    def setUp(self):
        w = self.w = main_window.MainWindow()
        old = {k: w.settings.value(k) for k in ("mouse_mode", "mouse_before_cad")}

        def back():
            for k, val in old.items():
                w.settings.setValue(k, val) if val is not None else w.settings.remove(k)
            mouse_modes.apply(w.settings)
        self.addCleanup(back)
        self.addCleanup(lambda: [setattr(x, "_close_confirmed", True) or x.close()
                                 for x in main_window.windows()])
        w.resize(1200, 900)
        w.show()
        w.open_file(sheet())
        APP.processEvents()
        v = self.v = w.view()
        self.addCleanup(lambda: setattr(v, "dirty", False))
        w.set_tool("editobjects")
        APP.processEvents()
        self.props = w.props

    def shapes(self):
        return [it for it in self.v.content_objects(0).items if it["kind"] == "shape"]

    def select(self, items):
        self.v.select_objects(0, items)
        APP.processEvents()

    def widths(self):
        """The outlined shapes' widths on the page (the square has none: left out)."""
        objs = page_objects.Objects(self.v.doc[0])
        return [round(page_objects.page_width(d), 3) for d in objs.found if d.get("stroke")]

    def shown(self):
        return self.props.rows["width"][1].isVisible()

    def type_width(self, w):
        self.props.width.setValue(w)
        APP.processEvents()

    def test_one_line_shows_its_width_as_drawn(self):
        self.select(self.shapes()[:1])
        self.assertTrue(self.shown())
        self.assertAlmostEqual(self.props.width.value(), 3.0)
        self.select([self.shapes()[1]])
        self.assertAlmostEqual(self.props.width.value(), 2.0)      # (1 unit at twice the scale)

    def test_a_width_typed_redraws_it_that_wide_in_one_undo_step(self):
        self.select(self.shapes()[:1])
        self.type_width(8)
        self.assertEqual(self.widths(), [8.0, 2.0, 4.0])
        self.assertTrue(self.v.obj_sel and len(self.v.obj_sel[1]) == 1)    # (still selected)
        self.v.undo()
        APP.processEvents()
        self.assertEqual(self.widths(), [3.0, 2.0, 4.0])

    def test_at_another_scale_it_is_the_width_on_the_page(self):
        self.select([self.shapes()[1]])
        self.type_width(6)
        self.assertEqual(self.widths()[1], 6.0)

    def test_several_of_different_widths_show_blank_and_all_take_the_one_typed(self):
        lines = [it for it in self.shapes() if it.get("stroke")]
        self.select(lines)
        self.assertTrue(self.shown())
        self.assertEqual(self.props.width.text().strip(), "")
        self.type_width(1.5)
        self.assertEqual(self.widths(), [1.5, 1.5, 1.5])

    def test_the_color_stays_and_a_second_change_replaces_the_first(self):
        blue = self.shapes()[3]
        self.select([blue])
        self.type_width(10)
        self.select([self.shapes()[3]])
        self.type_width(2)
        self.assertEqual(self.widths()[2], 2.0)
        data = page_objects._contents(self.v.doc[0])
        self.assertEqual(data.count(b"\nq\n"), 1)                 # (one wrapper, not nested)
        pm = self.v.doc[0].get_pixmap()                 # (y=500 up from the bottom of 842)
        self.assertEqual(pm.pixel(250, 342), (0, 0, 255))

    def test_the_arrows_step_it_and_a_number_typed_applies_on_enter(self):
        # (the owner, 22 Nov 2026: "when I edit a line width, I can't change it with the arrow
        # nor by typing in a value": the page read again kept the old width, so the box went
        # back to it and the next step started from there)
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        self.select(self.shapes()[:1])
        box = self.props.width
        box.setFocus()
        for k in range(1, 4):
            QTest.keyClick(box, Qt.Key_Up)
            APP.processEvents()
            self.assertAlmostEqual(box.value(), 3 + 0.5 * k)
            self.assertEqual(self.widths()[0], 3 + 0.5 * k)
        box.lineEdit().selectAll()
        QTest.keyClicks(box.lineEdit(), "7.5")
        APP.processEvents()
        self.assertEqual(self.widths()[0], 4.5)             # (not as each key is typed)
        QTest.keyClick(box, Qt.Key_Return)
        APP.processEvents()
        self.assertAlmostEqual(box.value(), 7.5)
        self.assertEqual(self.widths(), [7.5, 2.0, 4.0])
        self.assertAlmostEqual(self.v.object_line_width(), 7.5)
        self.v.undo()
        APP.processEvents()
        self.assertEqual(self.widths()[0], 4.5)             # (one step for the number typed)

    def test_a_shape_with_no_outline_shows_no_width(self):
        self.select([self.shapes()[2]])
        self.assertFalse(self.shown())

    def test_a_markup_selected_after_shows_its_own_width(self):
        self.select(self.shapes())
        p = self.v.doc[0]
        a = p.add_line_annot((100, 700), (400, 700))
        a.set_border(width=5)
        a.update()
        self.w.set_tool("select")
        self.v.clear_selection()
        APP.processEvents()
        self.props.show_target("line", {"width": 5.0, "stroke": "#000000"}, selected=True)
        self.assertEqual(self.props.width.text().strip()[:1], "5")


if __name__ == "__main__":
    unittest.main()
