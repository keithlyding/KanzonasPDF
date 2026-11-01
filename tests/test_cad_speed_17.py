"""1.7: big drawings read, erased and redacted quicker, with the same results.

Reading a drawing's objects takes plain shapes (numbers and path operators, then the paint)
in one step instead of a Python step per number, makes each box without Rect's __init__, and
pauses the garbage collector meanwhile; an edit shares the scan entries it left alone. Erase
content skips the pattern walk when nothing on the page can use a pattern, and converts only
the paths near the box (get_drawings' own code). Apply redactions / Sanitize leave out
PyMuPDF's slow hidden-text search on pages with no text at all.

Each quick way is checked against the general one (or PyMuPDF's own): the same result to
the last bit.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_cad_speed_17
"""
import gc
import math
import os
import random
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402
from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import erase, erase_patterns, pdf_speed  # noqa: E402
from kanzonas import page_objects as P  # noqa: E402
from kanzonas.document_view import DocumentView  # noqa: E402


# ---- content to read ---------------------------------------------------------------------
NUMS = ["1", "-2", "3.5", "-.25", "+4", "5.", "007", "1e5", "1.2.3", "-", ".", "0", "-0",
        "12.000001", "1_0", "inf", "-inf"]
OPS = ["m", "l", "c", "v", "y", "re", "h", "S", "s", "f", "F", "f*", "B", "B*", "b", "b*", "n",
       "W", "W*", "q", "Q", "cm", "w", "gs", "cs", "CS", "scn", "SCN", "rg", "RG", "g", "G", "k",
       "K", "d", "J", "j", "M", "BT", "ET", "Tf", "Tj", "TJ", "Td", "Do", "BDC", "BMC", "EMC",
       "sh", "ri", "i", "hf", "Sx", "f*x", "mm", "true", "null"]
SEPS = [" ", " ", " ", "\n", "\r\n", "\t", "  ", "\f", "\x0b", "\x00", "",
        " \x0b", "\r\n\x0b ", "\x00 ", " \x0c\t"]
OTHER = ["/Name", "/GS0", "(str)", "(a(b)c)", "(esc\\) x)", "<414243>", "<<", ">>", "[", "]",
         "{", "}", "%comment\n", "<</MCID 3>>", "BI /W 2 /H 2 /BPC 8 /CS /G ID \x01\x02EI x EI",
         "(unterminated", "<zz>", ")"]
STATE = ["q 1 0 0 1 5 5 cm", "Q", "0.5 w", "1 0 0 RG", "/OC /L1 BDC", "EMC",
         "0 0 100 100 re W n", "/Im1 Do", "/GS1 gs", "2 0 0 2 0 0 cm", "/CS0 cs 0.3 scn", "q",
         "10 10 m 20 20 l 0.3 w S", "10 10 m 20 20 l W n", "0.2 0.4 0.6 rg",
         "1 2 m 3 4 l .6 w h .3 .12 0 RG S", "1 1 2 2 re 0 g f", "5 5 m 6 6 7 7 8 8 c 2 J\n0.5 w S",
         "1 2 m 3 4 l 5 6 l h 1 j B*", "1 2 m 3 4 l 5 6 7 l S", "1 2 m 3 4 l /GS0 gs S"]


def plain_shape(rnd):
    ops = []
    for _ in range(rnd.randint(1, 4)):
        kind = rnd.choice(["m", "l", "c", "v", "y", "re", "h"])
        k = {"m": 2, "l": 2, "c": 6, "v": 4, "y": 4, "re": 4, "h": 0}[kind]
        ops.append(" ".join("%.2f" % rnd.uniform(-500, 500) for _ in range(k)) +
                   (" " if k else "") + kind)
    return " ".join(ops) + " " + rnd.choice(["S", "s", "f", "F", "f*", "B", "B*", "b", "b*"])


def odd_content(rnd):
    """Content with plain shapes and lines among anything a content stream can hold, also
    broken: odd numbers and separators, strings, comments, inline images, clips..."""
    parts = []
    for _ in range(rnd.randint(1, 60)):
        r = rnd.random()
        if r < 0.35:
            parts.append(plain_shape(rnd))
        elif r < 0.45:
            parts.append("%.2f %.2f m %.2f %.2f l %s" % (
                rnd.random() * 9, rnd.random() * 9, rnd.random() * 9, rnd.random() * 9,
                rnd.choice(["S", "s", "b", "f", "B*"])))
        elif r < 0.75:
            parts.append(" ".join(rnd.choice(NUMS) for _ in range(rnd.randint(0, 7))) +
                         rnd.choice(SEPS) + rnd.choice(OPS))
        elif r < 0.85:
            parts.append(rnd.choice(OTHER))
        else:
            parts.append(rnd.choice(STATE))
        parts.append(rnd.choice(SEPS))
    return "".join(parts).encode("latin-1")


def cad_content(n, seed=1):
    """Like a CAD export: mostly lines, some with their own width and color, curves,
    rectangles, closed shapes, a layer, a clip, a matrix."""
    rnd = random.Random(seed)
    out = [b"1 0 0 -1 0 800 cm 0.35 w 0.2 0.4 0.1 RG"]
    for i in range(n):
        x, y = rnd.uniform(20, 1100), rnd.uniform(20, 700)
        k = i % 10
        if k < 6:
            out.append(b"%.2f %.2f m %.2f %.2f l S" % (x, y, x + rnd.uniform(-40, 40), y))
        elif k == 6:
            out.append(b"%.2f %.2f m %.2f %.2f %.2f %.2f %.2f %.2f c S" %
                       (x, y, x + 10, y + 30, x + 30, y - 10, x + 40, y + 5))
        elif k == 7:
            out.append(b"%.2f %.2f 20 -15 re f" % (x, y))
        elif k == 8:
            out.append(b"/OC /L1 BDC %.2f %.2f m %.2f %.2f l %.2f %.2f l h b EMC" %
                       (x, y, x + 20, y, x + 10, y + 15))
        else:
            out.append(b"q 0 0 600 400 re W n 2 0 0 2 1 1 cm %.2f %.2f m %.2f %.2f l 0.5 w S Q"
                       % (x / 2, y / 2, x / 2, y / 2 + 9))
    return b"\n".join(out)


def page_with(doc, content, width=1200, height=800):
    pg = doc.new_page(width=width, height=height)
    x = doc.get_new_xref()
    doc.update_object(x, "<<>>")
    doc.update_stream(x, content)
    pg.set_contents(x)
    return pg


def general(fn, *args):
    """fn(*args) read only the general way (no plain-shape shortcut)."""
    with mock.patch.object(P, "QUICK", False):
        return fn(*args)


def same(a, b):
    """Equal to the last bit (NaN equals NaN), the same types."""
    if isinstance(a, float) and isinstance(b, float):
        return a == b and math.copysign(1, a) == math.copysign(1, b) or (a != a and b != b)
    if isinstance(a, pymupdf.Matrix) and isinstance(b, pymupdf.Matrix):
        return same(tuple(a), tuple(b))
    if isinstance(a, (tuple, list)) and isinstance(b, (tuple, list)):
        return type(a) is type(b) and len(a) == len(b) and all(map(same, a, b))
    return type(a) is type(b) and a == b


def same_lines(la, lb):
    return len(la) == len(lb) and all(
        len(p) == len(q) and all(type(u) is type(v) and same(u.x, v.x) and same(u.y, v.y)
                                 for u, v in zip(p, q)) for p, q in zip(la, lb))


class Reading(unittest.TestCase):
    def assert_same_scan(self, data, label=""):
        quick, slow = P.scan(data), general(P.scan, data)
        self.assertEqual(len(quick), len(slow), label)
        for k, (x, y) in enumerate(zip(quick, slow)):
            self.assertEqual(set(x), set(y), (label, k))
            for key in x:
                self.assertTrue(same(x[key], y[key]), (label, k, key, x[key], y[key]))
        tm = pymupdf.Matrix(1, 0, 0, -1, 0, 800)
        for d in quick:
            if d.get("path"):
                self.assertTrue(same_lines(P.path_lines(data, d, tm),
                                           general(P.path_lines, data, d, tm)),
                                (label, data[d["start"]:d["end"]]))
        return quick

    def test_plain_shapes_read_at_once_are_read_the_same(self):
        rnd = random.Random(17)
        for t in range(1500):
            self.assert_same_scan(odd_content(rnd), "odd content %d" % t)
        self.assert_same_scan(cad_content(3000), "cad")

    def test_spaces_after_a_path_are_read_as_one_run(self):
        # " \x0b" is one run of white space to the general reader (and then an odd
        # operator, as it doesn't start with a PDF white-space character): the shortcut
        # must not take the " " of it
        for data in (b"5. 12.000001\r\nl \x0bri 1.19 8.89 m 0.42 1.38 l s",
                     b"1 1 m 2 2 l \x0b 3 3 l S", b"1 1 m 2 2 l\x0b 3 3 l S",
                     b"1 1 m 2 2 l S \x0b 4 4 m 5 5 l S", b"1 1 m 2 2 lx S 1 1 m 2 2 l h\x00 S"):
            self.assert_same_scan(data, data)

    def test_a_long_path_that_is_not_plain_is_turned_down_at_once(self):
        # thousands of lines, then a state setting before the paint (or a clip): the
        # shortcut must give up in one pass (a backtracking pattern took minutes here)
        for tail in (b" 0 G S", b" W n", b" 1 0 0 RG f", b"S"):
            data = b"q " + b"\n".join(b"%d.94 %d m %d %d.5 l" % (i, i, i + 3, i)
                                      for i in range(20000)) + tail + b" Q"
            t = time.perf_counter()
            self.assert_same_scan(data, tail)
            self.assertLess(time.perf_counter() - t, 5.0)

    def test_the_objects_are_the_same(self):
        d = pymupdf.open()
        page_with(d, cad_content(3000))
        rnd = random.Random(3)
        page_with(d, b"\n".join(odd_content(rnd) for _ in range(30)))
        d[1].set_rotation(90)
        for pg in d:
            a, b = P.Objects(pg), general(P.Objects, pg)
            self.assertEqual(len(a.items), len(b.items))
            for x, y in zip(a.items, b.items):
                for k in ("n", "kind", "xref", "stroke", "fill", "width", "whole"):
                    self.assertTrue(same(x.get(k), y.get(k)), (x["n"], k))
                self.assertIs(type(x["rect"]), pymupdf.Rect)
                self.assertTrue(same(tuple(x["rect"]), tuple(y["rect"])), x["n"])
                self.assertTrue(same(tuple(x["quad"].rect), tuple(y["quad"].rect)), x["n"])
                self.assertTrue(same_lines(a.lines(x), general(b.lines, y)), x["n"])
                self.assertTrue(same(tuple(a.tight(x)), tuple(b.tight(y))), x["n"])

    def test_a_box_made_quickly_is_a_full_rect(self):
        d = pymupdf.open()
        objs = P.Objects(page_with(d, b"10 20 m 30 40 l S"))
        r = objs.items[0]["rect"]
        self.assertEqual(r, pymupdf.Rect(10, 760, 30, 780))
        self.assertEqual((r + (1, 1, 1, 1)).width, 20)
        self.assertTrue(r.contains(pymupdf.Point(20, 770)))
        self.assertEqual(r.quad.rect, r)

    def test_entries_share_what_does_not_change(self):
        d = pymupdf.open()
        found = P.scan(cad_content(200))
        ctms = {id(e["ctm"]) for e in found if e["ctx"] == ((), ())}
        self.assertEqual(len(ctms), 1)      # one matrix for the shapes drawn under it

    def test_the_collector_is_paused_while_reading_and_back_after(self):
        d = pymupdf.open()
        pg = page_with(d, cad_content(500))
        seen = []
        real = P.scan_steps

        def spy(data, out):
            seen.append(gc.isenabled())
            yield from real(data, out)
        with mock.patch.object(P, "scan_steps", spy):
            P.Objects(pg)
            objs, steps = P.Objects.steps(pg)
            for _ in steps:
                self.assertTrue(gc.isenabled())     # (between steps: the app runs)
        self.assertEqual(seen, [False, False])
        self.assertTrue(gc.isenabled())
        # an edit that fails leaves it on too
        with self.assertRaises(ValueError):
            P.transform(pg, [10 ** 6], pymupdf.Matrix(1, 1), objs)
        self.assertTrue(gc.isenabled())
        gc.disable()
        try:
            P.Objects(pg)
            self.assertFalse(gc.isenabled())        # (left as it was)
        finally:
            gc.enable()

    def test_reading_a_big_sheet_is_quick(self):
        d = pymupdf.open()
        pg = page_with(d, cad_content(60000))
        t = time.perf_counter()
        objs = P.Objects(pg)
        read = time.perf_counter() - t
        t = time.perf_counter()
        for it in objs.items:
            objs.lines(it)
        lines = time.perf_counter() - t
        self.assertEqual(len(objs.items), 60000)
        # (1.6.1: about 1.4 s and 1.1 s on the machine where these were measured at 0.35 s
        # and 0.25 s; the budget leaves room for a slow build machine)
        self.assertLess(read, 2.5)
        self.assertLess(lines, 2.0)


class Lookup(unittest.TestCase):
    def test_the_box_index_is_the_same_numbers(self):
        import numpy as np
        from kanzonas import hit_index
        rnd = random.Random(2)
        rects = [pymupdf.Rect(rnd.uniform(-1e4, 1e4), rnd.uniform(-10, 10),
                              rnd.uniform(-1e4, 1e4), rnd.uniform(-1e6, 1e6))
                 for _ in range(5000)] + [pymupdf.Rect(float("nan"), 1, 2, 3),
                                          pymupdf.Rect(0, 0, float("inf"), 1)]
        grow = [rnd.random() for _ in rects]
        for g in (None, grow):
            idx = hit_index.BoxIndex(iter(rects), g)
            # as 1.6.1 made them
            a = np.array([(r.x0, r.y0, r.x1, r.y1) for r in rects], dtype=float)
            gg = 0 if g is None else np.asarray(g, dtype=float)
            e = 1e-3 + 1e-6 * np.abs(a).max(axis=1)
            want = (np.minimum(a[:, 0], a[:, 2]) - gg - e, np.minimum(a[:, 1], a[:, 3]) - gg - e,
                    np.maximum(a[:, 0], a[:, 2]) + gg + e, np.maximum(a[:, 1], a[:, 3]) + gg + e)
            for got, w in zip((idx.x0, idx.y0, idx.x1, idx.y1), want):
                self.assertTrue(np.array_equal(got, w, equal_nan=True))
        self.assertEqual(hit_index.BoxIndex([]).near(1, 1), [])


class Editing(unittest.TestCase):
    def same_objects(self, a, b):
        self.assertEqual(len(a.found), len(b.found))
        for x, y in zip(a.found, b.found):
            self.assertEqual(set(x), set(y))
            for k in x:
                self.assertTrue(same(x[k], y[k]) if k != "ctm" else
                                same(tuple(x[k]), tuple(y[k])), k)
        self.assertEqual(len(a.items), len(b.items))
        for x, y in zip(a.items, b.items):
            for k in ("n", "kind", "xref", "stroke", "fill", "width"):
                self.assertEqual(x.get(k), y.get(k), k)
            self.assertEqual(tuple(x["rect"]), tuple(y["rect"]))

    def test_edits_leave_the_old_objects_as_they_were(self):
        d = pymupdf.open()
        pg = page_with(d, cad_content(2000))
        objs = P.Objects(pg)
        m = pymupdf.Matrix(1, 0, 0, 1, 7, -3)
        shapes = [it["n"] for it in objs.items if it["kind"] == "shape"]
        for edit in (lambda o: P.transform(pg, shapes[1500:1503], m, o),
                     lambda o: P.delete(pg, shapes[1200:1201], o),
                     lambda o: P.copies(pg, shapes[1000:1001], [m, m * m], o),
                     lambda o: P.block_copies(pg, shapes[900:902], [m], o),
                     lambda o: P.transform(pg, shapes[5:6], m, o)):
            before = [dict(e) for e in objs.found]
            new = edit(objs)
            self.assertIsInstance(new, P.Objects)
            # entries an edit left alone are shared, never changed in place
            self.assertEqual(len(before), len(objs.found))
            for x, y in zip(before, objs.found):
                self.assertTrue(all(same(x[k], y[k]) for k in x))
            shared = sum(1 for e in new.found if any(e is f for f in objs.found[:50]))
            self.assertGreater(shared, 0)
            self.same_objects(new, P.Objects(pg))
            self.same_objects(new, general(P.Objects, pg))
            objs = new


class CadPrep(unittest.TestCase):
    def test_outlines_read_in_idle_time_are_set_aside(self):
        tmp = tempfile.mkdtemp()
        d = pymupdf.open()
        page_with(d, cad_content(3000))
        path = os.path.join(tmp, "cad.pdf")
        d.save(path)
        v = DocumentView(path)
        self.addCleanup(v.close_doc)
        v.cad_select = True
        v._prep_timer = QTimer(v)
        v._prep_timer.setSingleShot(True)
        objs = v.content_objects(0)
        with mock.patch("kanzonas.document_view._set_aside") as aside:
            for _ in range(200):
                v._cad_prepare_step()
                if all("lines" in it for it in objs.items if it["kind"] == "shape"):
                    v._cad_prepare_step()
                    break
            self.assertTrue(all("lines" in it for it in objs.items if it["kind"] == "shape"))
            aside.assert_called_once_with(objs)
        self.assertTrue(gc.isenabled())


# ---- Erase content ---------------------------------------------------------------------------
def _pattern_doc(where):
    """A hatched (tiling pattern) square crossing the erase box, with lines: the pattern in
    the page's resources, an indirect resource dictionary, the page tree (inherited) or a
    form drawn by the page."""
    d = pymupdf.open()
    pg = d.new_page(width=400, height=400)
    pat = d.get_new_xref()
    d.update_object(pat, "<< /Type /Pattern /PatternType 1 /PaintType 1 /TilingType 1 /BBox "
                         "[0 0 10 10] /XStep 10 /YStep 10 /Resources << >> >>")
    d.update_stream(pat, b"1 0 0 RG 0 0 m 10 10 l S")
    body = b"q /Pattern cs /P1 scn 100 150 200 150 re f Q 0 0 1 RG 50 160 m 350 160 l S"
    res = "<< /Pattern << /P1 %d 0 R >> >>" % pat
    if where == "form":
        src = pymupdf.open()
        sp = page_with(src, body, 400, 400)
        src.xref_set_key(sp.xref, "Resources",
                         "<< /Pattern << /P1 %d 0 R >> >>" % _copy_pattern(src))
        pg.show_pdf_page(pg.rect, src, 0)
        return d
    c = d.get_new_xref()
    d.update_object(c, "<<>>")
    d.update_stream(c, body)
    pg.set_contents(c)
    if where == "page":
        d.xref_set_key(pg.xref, "Resources", res)
    elif where == "indirect":
        r = d.get_new_xref()
        d.update_object(r, res)
        d.xref_set_key(pg.xref, "Resources", "%d 0 R" % r)
    else:                                   # inherited from the page tree
        d.xref_set_key(pg.xref, "Resources", "null")
        pages = int(d.xref_get_key(d.pdf_catalog(), "Pages")[1].split()[0])
        d.xref_set_key(pages, "Resources", res)
    return d


def _copy_pattern(doc):
    x = doc.get_new_xref()
    doc.update_object(x, "<< /Type /Pattern /PatternType 1 /PaintType 1 /TilingType 1 /BBox "
                         "[0 0 10 10] /XStep 10 /YStep 10 /Resources << >> >>")
    doc.update_stream(x, b"1 0 0 RG 0 0 m 10 10 l S")
    return x


def _plain_erase(page, box):
    """erase.erase as 1.6.1 did it: every path of get_drawings, the pattern walk always."""
    with mock.patch.object(erase, "_drawings_near", lambda pg, b: pg.get_drawings()), \
            mock.patch.object(erase_patterns, "_may_use_patterns", lambda *a, **k: True):
        return erase.erase(page, box)


class Erasing(unittest.TestCase):
    BOX = pymupdf.Rect(150, 150, 170, 170)

    def test_patterns_are_found_wherever_they_can_be(self):
        for where in ("page", "indirect", "inherited", "form"):
            d = _pattern_doc(where)
            self.assertTrue(erase_patterns._may_use_patterns(
                d, erase_patterns._page_chain(d[0])), where)
            self.assertEqual(len(erase_patterns.find_crossing(d[0], self.BOX)), 1, where)

    def test_no_walk_where_nothing_can_use_a_pattern(self):
        d = pymupdf.open()
        page_with(d, cad_content(500))
        d[0].insert_text((100, 100), "text and a picture")
        src = pymupdf.open()
        page_with(src, b"0 0 m 100 100 l S", 400, 400)
        d[0].show_pdf_page(pymupdf.Rect(0, 0, 200, 200), src, 0)      # a form, no pattern
        with mock.patch.object(erase_patterns._Walker, "run",
                               side_effect=AssertionError("walked")):
            self.assertEqual(erase_patterns.find_crossing(d[0], self.BOX), [])

    def test_only_the_paths_near_the_box_are_converted_and_the_same(self):
        d = pymupdf.open()
        pg = page_with(d, cad_content(3000))
        box = pymupdf.Rect(300, 200, 372, 272)
        want = [p for p in pg.get_drawings() if erase._crosses(p, box)]
        near = erase._drawings_near(pg, box)
        self.assertLess(len(near), 300)
        got = [p for p in near if erase._crosses(p, box)]
        self.assertGreater(len(got), 3)
        self.assertEqual(got, want)
        self.assertNotIn("get_cdrawings", vars(pg))     # (put back)

    def test_the_erase_is_the_same_as_before(self):
        cases = [(lambda: _pattern_doc(w), self.BOX) for w in ("page", "indirect", "inherited", "form")]

        def lines():
            d = pymupdf.open()
            page_with(d, cad_content(2000))
            d[0].insert_text((310, 220), "erase me")
            return d
        cases += [(lines, pymupdf.Rect(300, 200, 372, 272)), (lines, pymupdf.Rect(0, 0, 1200, 800)),
                  (lines, pymupdf.Rect(640, 300, 641, 700))]
        for make, box in cases:
            data = make().tobytes()
            a, b = pymupdf.open("pdf", data), pymupdf.open("pdf", data)
            na = erase.erase(a[0], box)
            nb = _plain_erase(b[0], box)
            self.assertEqual(na, nb)
            # (garbage=1: the redaction mark erase adds and takes away again has a name
            # that is new each time, see pdf_speed._annot_id)
            self.assertEqual(a.tobytes(garbage=1, no_new_id=True),
                             b.tobytes(garbage=1, no_new_id=True))


# ---- Apply redactions / Sanitize: the hidden-text search ------------------------------------
SCRUB = dict(attached_files=True, clean_pages=True, embedded_files=True, hidden_text=True,
             javascript=True, metadata=True, redactions=False, remove_links=False,
             reset_fields=False, reset_responses=True, thumbnails=True, xml_metadata=True)


def hidden_text_doc():
    """Pages with every kind of hidden text the search finds, and pages without text."""
    d = pymupdf.open()
    p = d.new_page()                                    # 1 lines only
    for i in range(300):
        p.draw_line((10 + i, 10), (10 + i, 300), width=0.3)
    p = d.new_page()                                    # 2 invisible text over lines
    p.insert_text((50, 50), "secret invisible", render_mode=3)
    p.insert_text((50, 80), "visible")
    p.draw_line((40, 52), (200, 52))
    p = d.new_page()                                    # 3 white and transparent text
    p.insert_text((50, 50), "white text", color=(1, 1, 1))
    p.insert_text((50, 90), "ghost", fill_opacity=0)
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 20, 20), 0)
    pix.clear_with(200)
    p = d.new_page()                                    # 4 text under a picture
    p.insert_text((50, 50), "under picture")
    p.insert_image(pymupdf.Rect(40, 30, 200, 70), pixmap=pix)
    src = pymupdf.open()                                # 5 text in a form XObject
    sp = src.new_page()
    sp.insert_text((50, 50), "in a form, hidden", render_mode=3)
    sp.insert_text((50, 70), "in a form, shown")
    p = d.new_page()
    p.show_pdf_page(p.rect, src, 0)
    p.draw_rect(pymupdf.Rect(20, 20, 300, 300))
    p = d.new_page()                                    # 6 a markup with text, nothing else
    p.add_freetext_annot(pymupdf.Rect(50, 50, 250, 100), "note text")
    page_with(d, b"/Span <</ActualText (SECRET AT)>> BDC 10 10 m 300 300 l S EMC "   # 7
                 b"5 w 20 20 m 40 40 l S", 595, 842)
    p = d.new_page()                                    # 8 an OCR layer over a scan
    p.insert_image(pymupdf.Rect(20, 20, 300, 300), pixmap=pix)
    p.insert_text((40, 60), "ocr words", render_mode=3)
    d.new_page()                                        # 9 empty
    p = d.new_page()                                    # 10 filled and stroked text, lines
    p.insert_text((50, 50), "bold text", render_mode=2)
    for i in range(100):
        p.draw_line((0, i * 3), (500, i * 3), width=0.2)
    return d.tobytes()


class HiddenText(unittest.TestCase):
    def scrubbed(self, data, fn):
        d = pymupdf.open("pdf", data)
        fn(d)
        return d.tobytes(garbage=4, deflate=True, no_new_id=True)

    def test_the_same_file_as_pymupdfs_scrub(self):
        own_get_text = pymupdf.Page.get_text
        data = hidden_text_doc()
        before = pdf_speed.skipped_searches
        own = self.scrubbed(data, lambda d: d.scrub(**SCRUB))
        quick = self.scrubbed(data, lambda d: pdf_speed.scrub(d, **SCRUB))
        self.assertEqual(own, quick)
        # pages 1 and 9 (no text at all) went without the search: PyMuPDF still asks for it
        # the way pdf_speed knows (else this fails: look at the new scrub)
        self.assertEqual(pdf_speed.skipped_searches - before, 2)
        out = pymupdf.open("pdf", quick)
        self.assertEqual(out[1].get_text().split(), ["visible"])
        self.assertEqual(out[7].get_text().strip(), "")
        self.assertIs(pymupdf.Page.get_text, own_get_text)          # (put back)

    def test_any_page_that_may_hold_text_is_searched(self):
        d = pymupdf.open("pdf", hidden_text_doc())
        no_text = [pdf_speed.page_has_no_text(p) for p in d]
        self.assertEqual(no_text, [True, False, False, False, False, False, False, False,
                                   True, False])
        # ActualText around nothing but paths (page 7) counts as text: placed in the paths'
        # box once vectors are collected, as the search's TEXT_COLLECT_STYLES does

    def test_a_textless_cad_sheet_is_quick(self):
        d = pymupdf.open()
        page_with(d, cad_content(30000))
        own = pymupdf.Page.get_text
        t = time.perf_counter()
        pdf_speed.scrub(d, **SCRUB)
        self.assertLess(time.perf_counter() - t, 3.0)       # (PyMuPDF's search: ~4 s)
        self.assertIs(pymupdf.Page.get_text, own)

    def test_get_text_is_put_back_after_a_failure(self):
        own = pymupdf.Page.get_text
        d = pymupdf.open()
        d.new_page()
        with mock.patch.object(pymupdf.Document, "scrub", side_effect=RuntimeError("x")):
            with self.assertRaises(RuntimeError):
                pdf_speed.scrub(d, **SCRUB)
        self.assertIs(pymupdf.Page.get_text, own)

    def test_redaction_in_the_app_removes_hidden_text(self):
        tmp = tempfile.mkdtemp()
        path = os.path.join(tmp, "h.pdf")
        with open(path, "wb") as f:
            f.write(hidden_text_doc())
        v = DocumentView(path)
        self.addCleanup(v.close_doc)
        v.doc[0].add_redact_annot(pymupdf.Rect(100, 100, 120, 120))
        v.apply_redactions(True)
        self.assertEqual(v.doc[1].get_text().split(), ["visible"])
        self.assertNotIn("ocr", v.doc[7].get_text())
        self.assertIn("note text", v.doc[5].get_text())


if __name__ == "__main__":
    unittest.main()
