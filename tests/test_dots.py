"""Dots (dots.py): a filled or outlined dot placed with one click, its number and/or its text
beside it (right, below, left or above) or its number inside it; new dots and copies take the
next number, the text is asked for when the dot shows one, and it all reads back from the PDF.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_dots
"""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402
from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import annotations as A, dialogs, dots, legend as L, main_window  # noqa: E402
from kanzonas import mouse_modes  # noqa: E402
from kanzonas.document_view import DocumentView  # noqa: E402
from kanzonas.properties import PropertiesPanel  # noqa: E402

P = pymupdf.Point


def dot(at=(200, 150), text="", **props):
    m = {"kind": "dot", "props": dict(A.DEFAULTS["dot"]), "rect": pymupdf.Rect(),
         "points": [P(*at)], "text": text}
    m["props"].update(props)
    return m


def page(rotation=0):
    d = pymupdf.open()
    p = d.new_page(width=400, height=300)
    if rotation:
        p.set_rotation(rotation)
    return d, p


def screen_box(p, rect):
    """A rect in unrotated page coordinates, as seen on screen."""
    return pymupdf.Rect(rect) * p.rotation_matrix


def word_boxes(p, word):
    """Where a word is printed on the page, as seen on screen."""
    found = [pymupdf.Rect(w[:4]) for w in p.get_text("words") if w[4] == word]
    return [rect * p.rotation_matrix for rect in found]


class Parts(unittest.TestCase):
    def test_what_is_written_where(self):
        cases = [
            (dict(show="none"), "Quota", []),
            (dict(show="number", n=4), "Quota", [("4", "right")]),
            (dict(show="number", n=4, side="above"), "", [("4", "above")]),
            (dict(show="number", n=4, inside=True), "", [("4", "inside")]),
            (dict(show="text", side="left"), "Quota", [("Quota", "left")]),
            (dict(show="both", n=2, side="right"), "Quota", [("2", "left"), ("Quota", "right")]),
            (dict(show="both", n=2, side="below"), "Quota", [("2", "above"), ("Quota", "below")]),
            (dict(show="both", n=2, inside=True, side="left"), "Quota",
             [("2", "inside"), ("Quota", "left")]),
        ]
        for props, text, want in cases:
            with self.subTest(props=props):
                self.assertEqual(dots.parts(dot(text=text, **props)), want)

    def test_no_text_writes_nothing_or_only_the_number(self):
        self.assertEqual(dots.parts(dot(show="text", text="   ")), [])
        self.assertEqual(dots.parts(dot(show="both", n=3, text="")), [("3", "right")])

    def test_unknown_side_falls_back_to_the_right(self):
        self.assertEqual(dots.parts(dot(show="number", n=1, side="nowhere")), [("1", "right")])

    def test_a_number_inside_makes_the_dot_big_enough(self):
        small = dots.radius(dot(size=4, inside=False))
        inside = dots.radius(dot(size=4, inside=True, n=123))
        self.assertEqual(small, 2)
        width = pymupdf.get_text_length("123", fontname="helv", fontsize=9)
        self.assertGreater(inside * 2, width)
        # (a big dot stays its size)
        self.assertEqual(dots.radius(dot(size=40, inside=True, n=1)), 20)


class InThePdf(unittest.TestCase):
    def test_reads_back_as_written(self):
        d, p = page()
        m = dot(text="Quota 67,5 è", show="both", side="below", filled=False, size=8,
                width=1.5, n=12, inside=True, stroke="#00a000", text_color="#0000ff")
        back = A.read(A.write(p, m))
        self.assertEqual(back["kind"], "dot")
        self.assertEqual(back["text"], "Quota 67,5 è")
        self.assertEqual(back["points"], [P(200, 150)])
        for k in ("show", "side", "filled", "size", "n", "inside", "stroke", "text_color"):
            self.assertEqual(back["props"][k], m["props"][k], k)
        self.assertAlmostEqual(back["props"]["width"], 1.5)

    def test_filled_or_outline_only(self):
        d, p = page()
        full = A.write(p, dot(at=(100, 100), filled=True))
        ring = A.write(p, dot(at=(200, 100), filled=False))
        self.assertIsNotNone(full.colors.get("fill"))
        self.assertFalse(ring.colors.get("fill"))
        pix = p.get_pixmap(dpi=72, alpha=False)
        # the middle of a filled dot is its color, of an outlined one the page
        self.assertNotEqual(pix.pixel(100, 100), (255, 255, 255))
        self.assertEqual(pix.pixel(200, 100), (255, 255, 255))

    def test_each_side_on_every_page_rotation(self):
        for rotation in (0, 90, 180, 270):
            for side in dots.SIDES:
                with self.subTest(rotation=rotation, side=side):
                    d, p = page(rotation)
                    m = dot(at=(200, 150), text="Quota", show="both", side=side, n=7)
                    a = A.write(p, m)
                    centre = screen_box(p, dots.box(m))
                    c = (centre.tl + centre.br) / 2
                    text, = word_boxes(p, "Quota")
                    number, = word_boxes(p, "7")
                    # upright on screen: wider than tall
                    self.assertGreater(text.width, text.height)
                    t = (text.tl + text.br) / 2
                    n = (number.tl + number.br) / 2
                    if side == "right":
                        self.assertGreater(text.x0, centre.x1 - 0.5)
                        self.assertLess(number.x1, centre.x0 + 0.5)
                    elif side == "left":
                        self.assertLess(text.x1, centre.x0 + 0.5)
                        self.assertGreater(number.x0, centre.x1 - 0.5)
                    elif side == "below":
                        self.assertGreater(t.y, c.y)
                        self.assertLess(n.y, c.y)
                    else:
                        self.assertLess(t.y, c.y)
                        self.assertGreater(n.y, c.y)
                    # the markup's box holds what it draws (selection, hit testing, redraws)
                    box = screen_box(p, a.rect)
                    for word in (text, number):
                        grown = pymupdf.Rect(box.x0 - 1, box.y0 - 1, box.x1 + 1, box.y1 + 1)
                        self.assertTrue(grown.contains(word), (box, word))

    def test_number_inside_is_centred_and_white_on_a_filled_dot(self):
        d, p = page()
        m = dot(at=(200, 150), show="number", inside=True, n=5, size=16)
        A.write(p, m)
        number, = word_boxes(p, "5")
        self.assertTrue(dots.box(m).contains((number.tl + number.br) / 2))
        lay, = dots.layout(p, m)
        self.assertEqual(lay[3], (1, 1, 1))
        m = dot(at=(200, 150), show="number", inside=True, n=5, size=16, filled=False)
        lay, = dots.layout(p, m)
        self.assertEqual(lay[3], (0, 0, 0))

    def test_moved_in_place_keeps_its_text_beside_it(self):
        d, p = page()
        a = A.write(p, dot(at=(100, 100), text="Quota", show="text"))
        before = word_boxes(p, "Quota")[0]
        xref = a.xref
        self.assertTrue(A.shift_in_place(p, xref, P(30, 20)))
        m = A.read(p.load_annot(xref))
        self.assertEqual(m["points"], [P(130, 120)])
        after = word_boxes(p, "Quota")[0]
        self.assertAlmostEqual(after.x0 - before.x0, 30, delta=0.6)
        self.assertAlmostEqual(after.y0 - before.y0, 20, delta=0.6)


class Placing(unittest.TestCase):
    def view(self):
        path = os.path.join(tempfile.mkdtemp(), "plan.pdf")
        d = pymupdf.open()
        d.new_page(width=600, height=400)
        d.new_page(width=600, height=400)
        d.save(path)
        v = DocumentView(path)
        self.addCleanup(v.close_doc)
        self.addCleanup(lambda: setattr(v, "dirty", False))
        return v

    def dots_in(self, v):
        out = []
        for i in range(v.doc.page_count):
            page = v.doc[i]                     # (kept alive while its markups are read)
            for a in A.each_annot(page):
                m = A.read(a)
                if m and m["kind"] == "dot":
                    out.append((i, m))
        return out

    def use(self, v, **props):
        tool = dict(A.DEFAULTS["dot"], **props)
        v.tool_props = lambda kind: dict(tool) if kind == "dot" else A.tool_props(kind)

    def test_each_new_dot_takes_the_next_number_across_pages(self):
        v = self.view()
        self.use(v, show="number")
        v.place_dot(0, P(50, 50))
        v.place_dot(0, P(90, 50))
        v.place_dot(1, P(50, 50))
        self.assertEqual(sorted(m["props"]["n"] for _i, m in self.dots_in(v)), [1, 2, 3])
        # a dot renumbered by hand: the next one follows the highest
        page = v.doc[0]
        (x, m), = [(a.xref, A.read(a)) for a in A.each_annot(page)
                   if A.read(a)["props"]["n"] == 2]
        m["props"]["n"] = 40
        v.commit_models(0, [(x, m)])
        v.place_dot(1, P(90, 50))
        self.assertEqual(max(m["props"]["n"] for _i, m in self.dots_in(v)), 41)

    def test_the_text_is_asked_for_and_cancel_places_nothing(self):
        v = self.view()
        self.use(v, show="both", side="right")
        with mock.patch.object(dialogs, "get_text", return_value=("  +67,5  ", True)) as ask:
            v.place_dot(0, P(100, 100))
        ask.assert_called_once()
        (_i, m), = self.dots_in(v)
        self.assertEqual(m["text"], "+67,5")
        with mock.patch.object(dialogs, "get_text", return_value=("", False)):
            v.place_dot(0, P(150, 100))
        self.assertEqual(len(self.dots_in(v)), 1)

    def test_a_number_only_dot_asks_nothing(self):
        v = self.view()
        self.use(v, show="number")
        with mock.patch.object(dialogs, "get_text") as ask:
            v.place_dot(0, P(100, 100))
        ask.assert_not_called()
        self.assertEqual(len(self.dots_in(v)), 1)

    def test_one_undo_step_per_dot(self):
        v = self.view()
        self.use(v, show="number")
        v.place_dot(0, P(100, 100))
        v.place_dot(0, P(150, 100))
        v.undo()
        self.assertEqual([m["props"]["n"] for _i, m in self.dots_in(v)], [1])

    def test_copies_take_the_next_numbers(self):
        v = self.view()
        self.use(v, show="both")
        with mock.patch.object(dialogs, "get_text", return_value=("A", True)):
            v.place_dot(0, P(100, 100))
            v.place_dot(0, P(200, 100))
        xrefs = [a.xref for a in A.each_annot(v.doc[0])]
        v.select_xref(0, xrefs[0])
        v.select_xref(0, xrefs[1], add=True)
        v.duplicate_selected()
        got = sorted((m["props"]["n"], m["text"]) for _i, m in self.dots_in(v))
        self.assertEqual(got, [(1, "A"), (2, "A"), (3, "A"), (4, "A")])

    def test_the_number_comes_from_dots_only(self):
        # Count markers and ellipses are Circles too: their numbers and boxes don't count,
        # and a dot whose stored style can't be read is skipped
        v = self.view()
        self.use(v, show="number")
        page = v.doc[0]
        count = {"kind": "m_count", "props": dict(A.DEFAULTS["m_count"]),
                 "rect": pymupdf.Rect(), "points": [P(30, 30)], "n": 75}
        ellipse = {"kind": "ellipse", "props": dict(A.DEFAULTS["ellipse"]),
                   "rect": pymupdf.Rect(60, 60, 120, 100), "points": []}
        v.modify(lambda: (A.write(page, count), A.write(page, ellipse)), [0],
                 permission=pymupdf.PDF_PERM_ANNOTATE)
        self.assertEqual(dots.last_number(v.doc), 0)
        v.place_dot(0, P(200, 200))
        self.assertEqual(dots.last_number(v.doc), 1)
        page = v.doc[0]                         # (kept alive while its markups are read)
        x, = [a.xref for a in A.each_annot(page) if A.read(a)["kind"] == "dot"]
        v.doc.xref_set_key(x, "KZProps", pymupdf.get_pdf_str('{"kind": "dot", "props": '))
        self.assertEqual(dots.stored_number(v.doc, x), 0)
        self.assertEqual(dots.last_number(v.doc), 0)

    def test_the_number_follows_undo_and_redo(self):
        v = self.view()
        self.use(v, show="number")
        v.place_dot(0, P(100, 100))
        v.place_dot(1, P(100, 100))
        v.undo()
        self.assertEqual(dots.last_number(v.doc), 1)
        v.place_dot(0, P(150, 100))
        self.assertEqual(sorted(m["props"]["n"] for _i, m in self.dots_in(v)), [1, 2])
        v.undo()
        v.redo()
        self.assertEqual(dots.last_number(v.doc), 2)

    def test_restyling_several_dots_keeps_their_numbers(self):
        v = self.view()
        self.use(v, show="number")
        v.place_dot(0, P(100, 100))
        v.place_dot(0, P(200, 100))
        xrefs = [a.xref for a in A.each_annot(v.doc[0])]
        v.select_xref(0, xrefs[0])
        v.select_xref(0, xrefs[1], add=True)
        props = dict(v.selected_model["props"], filled=False, stroke="#0000ff")
        v.update_selected_props(props)
        got = sorted((m["props"]["n"], m["props"]["filled"], m["props"]["stroke"])
                     for _i, m in self.dots_in(v))
        self.assertEqual(got, [(1, False, "#0000ff"), (2, False, "#0000ff")])


def counts_sheet(path, how_many):
    """A large sheet with how_many Count markers (Circles with a count's stored style)."""
    d = pymupdf.open()
    sheet = d.new_page(width=2592, height=1728)
    count = {"kind": "m_count", "props": dict(A.DEFAULTS["m_count"]),
             "rect": pymupdf.Rect(), "points": [P(20, 20)], "n": 1}
    first = A.write(sheet, count)
    stored = d.xref_get_key(first.xref, "KZProps")[1]
    for i in range(1, how_many):
        x = 20 + (i % 60) * 40
        y = 20 + (i // 60) * 30
        marker = sheet.add_circle_annot(pymupdf.Rect(x - 4, y - 4, x + 4, y + 4))
        d.xref_set_key(marker.xref, "KZProps", pymupdf.get_pdf_str(stored))
    d.save(path)


class Speed(unittest.TestCase):
    """The owner (PR review, 12 Nov): the Dot tool must stay fast, so finding the next number
    doesn't load every Circle on a sheet of Count markers."""

    def test_a_dot_on_a_sheet_of_3000_counts(self):
        import time
        path = os.path.join(tempfile.mkdtemp(), "counts.pdf")
        counts_sheet(path, 3000)
        v = DocumentView(path)
        self.addCleanup(v.close_doc)
        self.addCleanup(lambda: setattr(v, "dirty", False))
        v.tool_props = lambda kind: dict(A.DEFAULTS[kind])
        with mock.patch.object(A, "read", side_effect=AssertionError("a markup was loaded")):
            self.assertEqual(dots.last_number(v.doc), 0)
        started = time.perf_counter()
        v.place_dot(0, P(500, 900))
        took = time.perf_counter() - started
        self.assertEqual(dots.last_number(v.doc), 1)
        # (about 4 times the time on the build machine, as the self-test's editing budget;
        # reading all 3,000 Circles took about 1 s on its own)
        self.assertLess(took, 1.0, f"placing a dot took {took:.2f}s")


class Clicking(unittest.TestCase):
    """The tool in the window: a click places a dot, a click on a dot selects it, a
    double-click on a dot changes its text. (In CAD mode a drawing tool always draws: a click
    on a dot places another one there, as Count does.)"""

    def setUp(self):
        tool = dict(A.DEFAULTS["dot"], show="number")
        patch = mock.patch.object(A, "tool_props",
                                  lambda kind: dict(tool) if kind == "dot"
                                  else dict(A.DEFAULTS.get(kind, {})))
        patch.start()
        self.addCleanup(patch.stop)
        self.addCleanup(lambda: [setattr(x, "_close_confirmed", True) or x.close()
                                 for x in main_window.windows()])
        d = pymupdf.open()
        d.new_page(width=600, height=400)
        path = os.path.join(tempfile.mkdtemp(), "plan.pdf")
        d.save(path)
        w = self.w = main_window.MainWindow()
        old = {k: w.settings.value(k) for k in ("mouse_mode", "mouse_before_cad")}

        def back():
            for k, val in old.items():
                w.settings.setValue(k, val) if val is not None else w.settings.remove(k)
            mouse_modes.apply(w.settings)
        self.addCleanup(back)
        w.resize(1100, 800)
        w.show()
        w.open_file(path)
        APP.processEvents()
        v = self.v = w.view()
        self.addCleanup(lambda: setattr(v, "dirty", False))
        w.set_mouse_mode("standard")
        w.set_tool("dot")
        v.set_zoom(1.0)
        APP.processEvents()
        self.page = v.pages[0]
        v.ensureVisible(self.page.x() + 200, self.page.y() + 150, 400, 300)
        APP.processEvents()

    def at(self, x, y):
        return QPoint(int(x * self.v.zoom), int(y * self.v.zoom))

    def numbers(self):
        page = self.v.doc[0]
        return sorted(A.read(a)["props"]["n"] for a in A.each_annot(page))

    def click(self, x, y):
        QTest.mouseClick(self.page, Qt.LeftButton, Qt.NoModifier, self.at(x, y))
        APP.processEvents()

    def test_a_click_places_a_dot_and_a_click_on_it_selects_it(self):
        self.click(100, 100)
        self.click(200, 100)
        self.assertEqual(self.numbers(), [1, 2])
        self.click(100, 100)
        self.assertEqual(self.numbers(), [1, 2])
        self.assertEqual(self.v.selected_model["props"]["n"], 1)

    def test_a_double_click_on_a_dot_changes_its_text(self):
        self.click(100, 100)
        with mock.patch.object(dialogs, "get_text", return_value=("+67,5", True)) as ask:
            self.click(100, 100)
            QTest.mouseDClick(self.page, Qt.LeftButton, Qt.NoModifier, self.at(100, 100))
            APP.processEvents()
        ask.assert_called_once()
        page = self.v.doc[0]
        m, = [A.read(a) for a in A.each_annot(page)]
        self.assertEqual(m["text"], "+67,5")

    def test_a_double_click_on_the_page_places_one_dot_and_asks_nothing(self):
        # (as the system sends it: a click, then the double-click; QTest's is the second only)
        with mock.patch.object(dialogs, "get_text") as ask:
            self.click(300, 200)
            QTest.mouseDClick(self.page, Qt.LeftButton, Qt.NoModifier, self.at(300, 200))
            APP.processEvents()
        ask.assert_not_called()
        self.assertEqual(self.numbers(), [1])

    def test_in_cad_mode_a_click_on_a_dot_places_another(self):
        self.w.set_mouse_mode("cad")
        self.w.set_tool("dot")
        APP.processEvents()
        self.click(100, 100)
        self.click(100, 100)
        self.assertEqual(self.numbers(), [1, 2])


class Panel(unittest.TestCase):
    def shown(self, panel):
        return {k for k, (lab, w) in panel.rows.items() if not w.isHidden()}

    def test_rows_follow_what_the_dot_shows(self):
        panel = PropertiesPanel()
        props = dict(A.DEFAULTS["dot"], show="number")
        panel.show_target("dot", props)
        rows = self.shown(panel)
        self.assertTrue({"filled", "size", "show", "side", "inside", "stroke"} <= rows, rows)
        self.assertNotIn("n", rows)                 # (a new dot takes the next number)
        panel.show_target("dot", props, selected=True)
        self.assertIn("n", self.shown(panel))
        panel.show_target("dot", dict(props, show="none"))
        rows = self.shown(panel)
        self.assertFalse({"side", "inside", "fontsize", "text_color"} & rows, rows)
        panel.show_target("dot", dict(props, inside=True))
        self.assertNotIn("side", self.shown(panel))  # (nothing goes beside it)
        panel.show_target("dot", dict(props, inside=True, show="both"))
        self.assertIn("side", self.shown(panel))

    def test_changes_come_out_as_props(self):
        panel = PropertiesPanel()
        panel.show_target("dot", dict(A.DEFAULTS["dot"]), selected=True)
        got = []
        panel.propsChanged.connect(got.append)
        panel.filled.setCurrentIndex(1)
        panel.side.setCurrentIndex(panel.side.findData("above"))
        panel.dot_show.setCurrentIndex(panel.dot_show.findData("both"))
        panel.inside.setChecked(True)
        panel.number.setValue(9)
        panel.dot_size.setValue(10)
        last = got[-1]
        self.assertEqual((last["filled"], last["side"], last["show"], last["inside"], last["n"],
                          last["size"]), (False, "above", "both", True, 9, 10))


class Legend(unittest.TestCase):
    def test_filled_and_outlined_dots_are_separate_rows(self):
        full = L._style(dot(filled=True))
        ring = L._style(dot(filled=False))
        self.assertNotEqual(full, ring)
        self.assertEqual(L.label_of(dot()), A.LABELS["dot"])


if __name__ == "__main__":
    unittest.main()
