"""The Dimension tool (dimensions.py), like Bluebeam's Dimension and AutoCAD's DIMALIGNED:
click the two points to measure, then where the dimension line goes (in the standard mouse
mode a drag gives the two points too). It draws two extension lines, a dimension line with
arrowheads and the measured length above it, in the page's scale and unit as Length does.

Checked: drawn by clicks and by a drag; the measured text with a calibrated scale; its grips
re-measure (the third keeps to the middle of the dimension line); moved where it is, turned,
undone and redone; saved and opened again; on a turned page its text reads upright; it's
written as a PDF Line annotation other viewers show as a dimension (leader lines, caption,
/IT /LineDimension, /Measure) with its own appearance; it's hit along its dimension line,
snaps, shows in the measurement summary, restyles (arrowheads), and is in the menus, the
Measure tab and the CAD tab with its shortcut.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_dimension
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QKeyEvent, QMouseEvent  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import annotations as A  # noqa: E402
from kanzonas import dimensions, measure, measure_ui, snapping  # noqa: E402
from kanzonas.document_view import DocumentView  # noqa: E402

P = pymupdf.Point
SCALE = (measure.scale_from_preset(96), "ft-in", '1/8" = 1\'-0"')
# 192 pt on paper = 2 2/3 in = 21'-4" at 1/8" = 1'-0"
A_, B_, C_ = (100, 300), (292, 300), (180, 260)


def sheet(rotation=0):
    d = pymupdf.open()
    p = d.new_page(width=600, height=600)
    measure.set_scale(p, *SCALE)
    if rotation:
        p.set_rotation(rotation)
    path = os.path.join(tempfile.mkdtemp(), "dim.pdf")
    d.save(path)
    return path


class Geometry(unittest.TestCase):
    def test_extension_lines_and_the_dimension_line(self):
        a, b, a2, b2, n, d = dimensions.geometry([P(A_), P(B_), P(C_)])
        self.assertEqual((a2, b2), (P(100, 260), P(292, 260)))
        self.assertAlmostEqual(d, 40)               # /LL: up on the page is positive
        self.assertEqual(dimensions.normalized([P(A_), P(B_), P(C_)])[2], P(196, 260))
        self.assertEqual(dimensions.path([P(A_), P(B_), P(C_)]),
                         [P(A_), P(100, 260), P(292, 260), P(B_)])
        back = dimensions.from_leader(P(A_), P(B_), 40)
        self.assertTrue(A._same(back, [P(A_), P(B_), P(196, 260)]))

    def test_measured_between_its_two_points_in_the_page_scale(self):
        d = pymupdf.open(sheet())
        pg = d[0]
        self.assertEqual(measure.measure_text("m_dim", [P(A_), P(B_), P(C_)], pg), "21'-4\"")
        value, unit = measure.raw_values("m_dim", [P(A_), P(B_), P(C_)], pg)
        self.assertEqual(unit, "ft")
        self.assertAlmostEqual(value, 21 + 1 / 3)


class Drawing(unittest.TestCase):
    MODE_CAD = True

    def setUp(self):
        for key in ("cad_select", "snap_objects", "snap_grid", "snap_page", "mouse_mode"):
            self.addCleanup(setattr, DocumentView, key, getattr(DocumentView, key))
        DocumentView.cad_select = self.MODE_CAD
        DocumentView.mouse_mode = "cad" if self.MODE_CAD else "standard"
        DocumentView.snap_objects = DocumentView.snap_grid = DocumentView.snap_page = False

    def view(self, tool="m_dim", path=None, rotation=0):
        v = DocumentView(path or sheet(rotation))
        self.addCleanup(v.close_doc)
        self.addCleanup(lambda: setattr(v, "dirty", False))
        self.addCleanup(v.hide)
        v.resize(900, 900)
        v.show()
        APP.processEvents()
        v.set_zoom(1.0)             # (after the first layout, which fits the page's width)
        APP.processEvents()
        self.assertEqual(v.zoom, 1.0)
        v.set_tool(tool)
        return v

    def at(self, v, pt):
        q = v.pages[0].to_screen_pt(P(pt))
        return QPoint(round(q.x()), round(q.y()))

    def click(self, v, pt):
        QTest.mouseClick(v.pages[0], Qt.LeftButton, Qt.NoModifier, self.at(v, pt))
        APP.processEvents()

    def send(self, v, kind, pt, buttons):
        w = v.pages[0]
        pos = QPointF(self.at(v, pt))
        button = Qt.NoButton if kind == QEvent.MouseMove and buttons == Qt.NoButton \
            else Qt.LeftButton
        ev = QMouseEvent(kind, pos, w.mapToGlobal(pos), button, buttons, Qt.NoModifier)
        {QEvent.MouseButtonPress: w.mousePressEvent, QEvent.MouseMove: w.mouseMoveEvent,
         QEvent.MouseButtonRelease: w.mouseReleaseEvent}[kind](ev)
        APP.processEvents()

    def hover(self, v, pt):
        self.send(v, QEvent.MouseMove, pt, Qt.NoButton)

    def drag(self, v, a, b):
        self.send(v, QEvent.MouseButtonPress, a, Qt.LeftButton)
        self.send(v, QEvent.MouseMove, ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2), Qt.LeftButton)
        self.send(v, QEvent.MouseMove, b, Qt.LeftButton)
        self.send(v, QEvent.MouseButtonRelease, b, Qt.NoButton)

    def key(self, v, k):
        v.keyPressEvent(QKeyEvent(QEvent.KeyPress, k, Qt.NoModifier))
        APP.processEvents()

    def markups(self, v):
        page = v.doc[0]
        return [(a.xref, A.read(a)) for a in A.each_annot(page)]

    def draw(self, v, a=A_, b=B_, c=C_):
        self.click(v, a)
        self.click(v, b)
        self.hover(v, c)
        self.click(v, c)
        (xref, m), = self.markups(v)
        return xref, m

    def check_written(self, v, xref, text="21'-4\""):
        doc = v.doc
        obj = doc.xref_object(xref)
        page = doc[0]
        an = page.load_annot(xref)
        self.assertEqual(an.type[0], pymupdf.PDF_ANNOT_LINE)
        self.assertEqual(an.info["content"], text)              # (its /Cap caption)
        for key in ("/IT /LineDimension", "/Cap true", "/CP /Top", "/Subtype /RL",
                    "/LE [ /ClosedArrow /ClosedArrow ]"):
            self.assertIn(key, obj)
        self.assertEqual(doc.xref_get_key(xref, "Measure/R")[1], '1/8" = 1\'-0"')
        typ, val = doc.xref_get_key(xref, "AP/N")
        self.assertEqual(typ, "xref")
        stream = doc.xref_stream(int(val.split()[0])).decode("latin-1")
        self.assertIn("(%s) Tj" % text.replace("(", "\\(").replace(")", "\\)"), stream)
        self.assertIn(" f", stream)                              # (filled arrowheads)
        del an, page

    def test_three_clicks_with_a_preview(self):
        v = self.view()
        w = v.pages[0]
        self.click(v, A_)
        self.click(v, B_)
        self.assertEqual(len(w._poly), 2)
        self.hover(v, C_)
        # the preview: the dimension line is drawn up where the pointer is
        img = w.grab().toImage()
        mid = self.at(v, (196, 260))
        self.assertTrue(any(img.pixelColor(mid.x(), mid.y() + dy).lightness() < 200
                            for dy in (-1, 0, 1)))
        self.assertEqual(self.markups(v), [])
        self.click(v, C_)
        self.assertEqual(w._poly, [])
        (xref, m), = self.markups(v)
        self.assertEqual(m["kind"], "m_dim")
        self.assertEqual(A.LABELS["m_dim"], "Dimension")
        self.assertTrue(A._same(m["points"], [P(A_), P(B_), P(196, 260)], 0.6))
        self.assertAlmostEqual(float(v.doc.xref_get_key(xref, "LL")[1]), 40, delta=0.6)
        self.check_written(v, xref)
        # drawn: red along the dimension line and the extension lines
        pg = v.doc[0]
        pix = pg.get_pixmap(dpi=144)
        for x, y in ((150, 260), (240, 260), (100, 280), (292, 280)):
            px = min((pix.pixel(2 * x + dx, 2 * y + dy) for dx in (-1, 0, 1)
                      for dy in (-1, 0, 1)), key=lambda c: c[1])
            self.assertTrue(px[0] > 150 and px[1] < 100, ((x, y), px))
        del pg
        # hit along its dimension line and on its text, not between its points only
        self.assertEqual(v.annot_at(0, P(150, 260)), xref)
        self.assertEqual(v.annot_at(0, P(196, 252)), xref)
        self.assertEqual(v.annot_at(0, P(100, 290)), xref)
        self.assertIsNone(v.annot_at(0, P(196, 285)))
        # undo takes it away, redo puts it back
        v.undo()
        self.assertEqual(self.markups(v), [])
        v.redo()
        self.assertEqual(len(self.markups(v)), 1)

    def test_escape_cancels_and_two_points_make_none(self):
        v = self.view()
        self.click(v, A_)
        self.click(v, B_)
        self.key(v, Qt.Key_Escape)
        self.assertEqual(v.pages[0]._poly, [])
        self.click(v, A_)
        self.click(v, B_)
        self.key(v, Qt.Key_Return)
        self.assertEqual(self.markups(v), [])

    def test_grips_measure_again(self):
        v = self.view()
        xref, m = self.draw(v)
        v.set_tool("select")
        v._set_selection(0, [xref])
        APP.processEvents()
        w = v.pages[0]
        self.assertEqual(sorted(w._handles(v.selected_model)), ["rot", "v0", "v1", "v2"])
        # the second point dragged on: measured again (288 pt = 4 in = 32'-0")
        self.drag(v, B_, (388, 300))
        (x2, m2), = self.markups(v)
        self.assertEqual(m2["kind"], "m_dim")
        self.assertEqual(v.doc[0].load_annot(x2).info["content"], "32'-0\"")
        self.assertTrue(A._same(m2["points"][2], P(244, 260), 0.6))   # (kept in the middle)
        # the dimension line's grip moved down past the points: the same length, the line
        # below them now
        v._set_selection(0, [x2])
        APP.processEvents()
        self.drag(v, (244, 260), (250, 340))
        (x3, m3), = self.markups(v)
        self.assertTrue(A._same(m3["points"], [P(A_), P(388, 300), P(244, 340)], 0.6))
        self.assertAlmostEqual(float(v.doc.xref_get_key(x3, "LL")[1]), -40, delta=0.6)
        self.assertEqual(v.doc[0].load_annot(x3).info["content"], "32'-0\"")
        # one undo step each
        v.undo()
        (_x, back), = self.markups(v)
        self.assertTrue(A._same(back["points"], m2["points"], 0.01))
        v.undo()
        (_x, back), = self.markups(v)
        self.assertTrue(A._same(back["points"], m["points"], 0.01))

    def test_moves_in_place_turns_restyles_and_reopens(self):
        v = self.view()
        xref, m = self.draw(v)
        v._set_selection(0, [xref])
        v.cad_apply("Moved", pymupdf.Matrix(1, 0, 0, 1, 20, 10))
        (x2, m2), = self.markups(v)
        self.assertEqual(x2, xref)                          # moved where it is
        self.assertTrue(A._same(A.translation(m, m2), P(20, 10)))
        # turned a quarter turn: the same length, its points turned
        c = P(216, 290)
        mat = pymupdf.Matrix(1, 0, 0, 1, -c.x, -c.y) * pymupdf.Matrix(90) * \
            pymupdf.Matrix(1, 0, 0, 1, c.x, c.y)
        v._set_selection(0, [x2])
        v.cad_apply("Rotated", mat)
        (x3, m3), = self.markups(v)
        for got, old in zip(m3["points"], m2["points"]):
            self.assertLess(abs(got - old * mat), 0.01)
        self.assertEqual(v.doc[0].load_annot(x3).info["content"], "21'-4\"")
        # restyled: green, slashes for arrowheads, bigger text
        v._set_selection(0, [x3])
        v.update_selected_props({"stroke": "#00a000", "head": "slash", "fontsize": 12.0})
        (x4, m4), = self.markups(v)
        self.assertEqual((m4["kind"], m4["props"]["stroke"], m4["props"]["head"],
                          m4["props"]["fontsize"]), ("m_dim", "#00a000", "slash", 12.0))
        self.assertIn("/LE [ /Slash /Slash ]", v.doc.xref_object(x4))
        # saved and opened again
        out = os.path.join(tempfile.mkdtemp(), "dim.pdf")
        v.doc.save(out)
        d = pymupdf.open(out)
        pg = d[0]
        again = [A.read(a) for a in A.each_annot(pg)]
        self.assertEqual([a["kind"] for a in again], ["m_dim"])
        self.assertTrue(A._same(again[0]["points"], m4["points"]))
        self.assertEqual(again[0]["props"]["head"], "slash")
        typ, val = d.xref_get_key(x4, "AP/N")
        self.assertEqual(typ, "xref")
        self.assertIn(b"21'-4\"", d.xref_stream(int(val.split()[0])))
        del pg
        d.close()

    def test_on_a_turned_page_its_text_reads_upright(self):
        for rot in (90, 180, 270):
            v = self.view(rotation=rot)
            pg = v.doc[0]
            # a line level on screen: the measured points as the turned page shows them
            pts = [P(q) * pg.derotation_matrix for q in ((100, 300), (292, 300), (196, 260))]
            v.apply_poly(0, "m_dim", pts)
            (xref, m), = self.markups(v)
            self.check_written(v, xref)
            anchor, ang = dimensions.label_place(m["points"], pg, 9, 1)
            self.assertAlmostEqual((ang - rot) % 360, 0, delta=0.01)
            shown = anchor * pg.rotation_matrix
            self.assertLess(shown.y, 260)                   # above its dimension line
            self.assertAlmostEqual(shown.x, 196, delta=0.01)
            # the text is drawn there, upright: dark pixels just above the line's middle
            pix = pg.get_pixmap(dpi=72)
            dark = sum(1 for x in range(186, 207) for y in range(248, 258)
                       if pix.pixel(x, y)[1] < 128)
            self.assertGreater(dark, 5, rot)
            del pg

    def test_snaps_and_in_the_measurement_summary(self):
        v = self.view()
        xref, m = self.draw(v)
        pts = snapping.markup_points(m)
        for want in (P(A_), P(B_), P(100, 260), P(292, 260), P(196, 260)):
            self.assertTrue(any(abs(q - want) < 0.6 for q in pts), want)
        rows = measure_ui.summary_rows(v.doc)
        self.assertEqual([r[0] for r in rows], ["Dimension"])
        self.assertEqual(rows[0][3:], (1, 21.33, "ft"))
        # a new scale measures it again
        v.set_page_scale([0], measure.scale_from_preset(48), "ft-in", '1/4" = 1\'-0"')
        (x2, _m), = self.markups(v)
        self.assertEqual(v.doc[0].load_annot(x2).info["content"], "10'-8\"")


class DrawingStandardMode(Drawing):
    MODE_CAD = False

    def test_a_drag_gives_its_two_points_and_a_click_its_line(self):
        v = self.view()
        self.drag(v, A_, B_)
        self.assertEqual(len(v.pages[0]._poly), 2)
        self.hover(v, C_)
        self.click(v, C_)
        (xref, m), = self.markups(v)
        self.assertTrue(A._same(m["points"], [P(A_), P(B_), P(196, 260)], 0.6))
        self.check_written(v, xref)


class InTheWindow(unittest.TestCase):
    def test_in_the_menus_the_measure_tab_and_the_cad_tab(self):
        from PySide6.QtWidgets import QToolButton
        from kanzonas.main_window import MainWindow
        from kanzonas.properties import PropertiesPanel
        w = MainWindow()
        self.addCleanup(lambda: (setattr(w, "_close_confirmed", True), w.close()))
        old = w.settings.value("mouse_mode")
        self.addCleanup(lambda: w.settings.setValue("mouse_mode", old or "hand"))
        t = w.tool_actions
        self.assertEqual(t["m_dim"].text(), "Dimension")
        self.assertEqual(t["m_dim"].shortcut().toString(), "Shift+D")
        self.assertFalse(t["m_dim"].icon().isNull())
        self.assertIn(t["m_dim"], w.tool_group.actions())           # (Tools menu)
        self.assertIn(t["m_dim"], w.measure_btn.menu().actions())   # (classic toolbar)
        w.set_mouse_mode("cad")
        split = [b for b in w._cad_tab.findChildren(QToolButton) if b.menu() is not None and
                 t["m_length"] in b.menu().actions()]
        self.assertEqual(len(split), 1)
        self.assertIn(t["m_dim"], split[0].menu().actions())
        r = w.ribbon
        measure_tab = next(r.widget(i) for i in range(r.count()) if r.tabText(i) == "Measure")
        self.assertTrue(any(b.defaultAction() is t["m_dim"]
                            for b in measure_tab.findChildren(QToolButton)))
        t["m_dim"].trigger()
        self.assertEqual(w.tool, "m_dim")
        # Properties: its own arrowheads
        panel = PropertiesPanel()
        panel.show_target("m_dim", A.tool_props("m_dim"))
        heads = [panel.head.itemData(i) for i in range(panel.head.count())]
        self.assertEqual(heads, list(dimensions.HEADS))
        panel.show_target("arrow", A.tool_props("arrow"))
        self.assertEqual(panel.head.count(), len(A.HEADS))


if __name__ == "__main__":
    unittest.main()
