"""1.6.1: what runs on every mouse move or repaint, made quick, with the same answers as
before. Each test checks the quick way against the old one (kept here) at many points:
the text a drag selects, the markup under the pointer (and its tooltip), the object or
line of text under it with Edit objects / Edit text, the selection's highlight and a CAD
command's preview as drawn, night mode's pixels, and a rendered page as shown. Also:
a big drawing is set aside from the garbage collector, and given back when the file closes.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_speed_161_hover
"""
import gc
import os
import random
import sys
import tempfile
import time
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np  # noqa: E402
import pymupdf  # noqa: E402
from PySide6.QtCore import QPointF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import annotations, cad_commands, document_view, hit_index  # noqa: E402
from kanzonas import page_objects, page_widget, text_edit  # noqa: E402
from kanzonas.document_view import DocumentView  # noqa: E402
from kanzonas.page_objects import _inside, _near  # noqa: E402

P = pymupdf.Point
WORDS = ("panel", "breaker", "conduit", "feeder", "ground", "neutral", "load", "circuit",
         "the", "of", "to", "and", "schedule", "riser", "transformer", "main", "sub")


def save(d, name):
    path = os.path.join(tempfile.mkdtemp(), name)
    d.save(path)
    return path


def text_pdf():
    """Two pages of text in columns, sizes and fonts mixed (the second one turned)."""
    rnd = random.Random(7)
    d = pymupdf.open()
    for rot in (0, 90):
        p = d.new_page(width=612, height=792)
        p.insert_text((72, 60), "A TITLE ACROSS THE COLUMNS", fontsize=16)
        for col in range(3):
            y = 90
            while y < 420:
                n = rnd.randint(8, 40)
                text = " ".join(rnd.choice(WORDS) for _ in range(n))
                size = rnd.choice((7, 8, 9, 10, 12))
                r = pymupdf.Rect(40 + col * 185, y, 40 + col * 185 + 170, y + 120)
                left = p.insert_textbox(r, text, fontsize=size,
                                        fontname=rnd.choice(("helv", "tiro", "cour")))
                y += 120 - max(0, left) + 10 if left >= 0 else 130
        p.insert_text((300, 760), "page footer 1 of 2", fontsize=6)
        if rot:
            p.set_rotation(rot)
    return save(d, "text.pdf")


# ---- the old ways (1.6.1 before these changes), to check against -------------------------
def old_word_near(words, pt, limit=None):
    best, best_d = None, None
    for i, w in enumerate(words):
        r = pymupdf.Rect(w[:4])
        if r.contains(pt):
            return i
        dx = max(r.x0 - pt.x, 0, pt.x - r.x1)
        dy = max(r.y0 - pt.y, 0, pt.y - r.y1)
        d = (dx * dx + 4 * dy * dy) ** 0.5
        if best_d is None or d < best_d:
            best, best_d = i, d
    if limit is not None and (best_d is None or best_d > limit):
        return None
    return best


def old_word_in_box(r, box):
    if not r.intersects(box):
        return False
    inter = pymupdf.Rect(r) & box
    return inter.get_area() >= 0.4 * r.get_area()


def old_text_selection(words, a, b):
    if not words:
        return ("box", [])
    si = old_word_near(words, a, DocumentView.NEAR)
    if si is None:
        box = pymupdf.Rect(a, b).normalize()
        return ("box", [w for w in words if old_word_in_box(pymupdf.Rect(w[:4]), box)])
    ei = old_word_near(words, b)
    ws, we = words[si], words[ei]
    if ws[5] == we[5]:
        blk = [w for w in words if w[5] == ws[5]]
        i, j = blk.index(ws), blk.index(we)
        return ("text", blk[min(i, j):max(i, j) + 1])
    bb = {}
    for w in words:
        bb[w[5]] = bb.get(w[5], pymupdf.Rect(w[:4])) | pymupdf.Rect(w[:4])
    span = bb[ws[5]] | bb[we[5]]
    top, bottom = min(ws[1], we[1]), max(ws[3], we[3])
    cands = [w for w in words
             if bb[w[5]].x1 > span.x0 and bb[w[5]].x0 < span.x1
             and w[3] > top and w[1] < bottom]
    order = DocumentView._reading_order(cands)
    i, j = order.index(ws), order.index(we)
    return ("text", order[min(i, j):max(i, j) + 1])


def old_line_rects(words):
    lines, order = {}, []
    for w in words:
        key = (w[5], w[6])
        if key not in lines:
            lines[key] = pymupdf.Rect(w[:4])
            order.append(key)
        else:
            lines[key] |= pymupdf.Rect(w[:4])
    return [lines[k] for k in order]


def old_annot_under(v, index, pt):
    tol = v._hit_tol()
    page = v.doc[index]
    hits = [an for an in annotations.each_annot(page)
            if an.type[0] != pymupdf.PDF_ANNOT_POPUP and DocumentView._annot_hit(an, pt, tol)]
    return page, (min(hits, key=lambda an: an.rect.get_area()) if hits else None)


def old_tooltip(v, index, pt):
    _page, a = old_annot_under(v, index, pt)
    if a is None:
        return ""
    model = annotations.read(a)
    label = annotations.LABELS.get(model["kind"], a.type[1]) if model else a.type[1]
    content = a.info.get("content", "")
    return f"{label}: {content}" if content else label


def old_objects_at(objs, pt, tol):
    pt = pymupdf.Point(pt)
    filled = None
    for it in reversed(objs.items):
        r = it["rect"]
        pad = tol + it.get("width", 0) / 2
        if not (r.x0 - pad <= pt.x <= r.x1 + pad and r.y0 - pad <= pt.y <= r.y1 + pad):
            continue
        if it["kind"] in ("picture", "group"):
            if pt in it["quad"] and filled is None and not it.get("whole"):
                filled = it
            continue
        for line in objs.lines(it):
            if _near(line, pt, pad):
                return it
        if it["fill"] and filled is None and _inside(objs.lines(it), pt):
            filled = it
    return filled


def old_object_at(v, index, pt):
    pad = 2 / v.zoom
    hits = [it for it in v.text_objects(index)
            if (it["rect"] + (-pad, -pad, pad, pad)).contains(pt)]
    if hits:
        return min(hits, key=lambda it: it["rect"].get_area())
    objs = v.content_objects(index)
    return old_objects_at(objs, pt, 4 / v.zoom) if objs is not None else None


def old_night(samples, width, height, stride):
    a = np.frombuffer(samples, dtype=np.uint8)
    rows = a[: height * stride].reshape(height, stride)[:, : width * 3].reshape(height, width, 3)
    rows = rows.astype(np.int16)
    offset = 255 - rows.max(axis=2) - rows.min(axis=2)
    return (rows + offset[:, :, None]).clip(0, 255).astype(np.uint8).tobytes()


def view(path, zoom=1.0):
    v = DocumentView(path)
    v.set_zoom(zoom)
    return v


class Base(unittest.TestCase):
    def open(self, path, zoom=1.0):
        v = view(path, zoom)
        self.addCleanup(v.close_doc)
        self.addCleanup(lambda: setattr(v, "dirty", False))
        return v


# ---- text selection --------------------------------------------------------------------
class TextSelection(Base):
    @classmethod
    def setUpClass(cls):
        cls.path = text_pdf()

    def points(self, rnd, words, rect, n):
        pts = []
        for k in range(n):
            if k % 3 == 0:
                pts.append(P(rnd.uniform(-10, rect.width + 10), rnd.uniform(-10, rect.height + 10)))
            else:
                w = rnd.choice(words)
                pts.append(P(rnd.uniform(w[0] - 4, w[2] + 4), rnd.uniform(w[1] - 4, w[3] + 4)))
        for w in rnd.sample(words, 15):             # right on characters' corners
            pts += [P(w[0], w[1]), P(w[2], w[3]), P(w[2], w[1]), P(w[0], w[3])]
        return pts

    def test_drags_select_what_they_selected_before(self):
        v = self.open(self.path)
        rnd = random.Random(11)
        for index in range(v.doc.page_count):
            words = v._words(index)
            self.assertGreater(len(words), 1000)
            pts = self.points(rnd, words, v.doc[index].rect, 45)
            for k, a in enumerate(pts):
                b = pts[(k * 7 + 5) % len(pts)]
                got = v.text_selection(index, a, b)
                self.assertEqual(got, old_text_selection(words, a, b), (index, a, b))
                self.assertEqual(v.line_rects(got[1]), old_line_rects(got[1]))
                for limit in ((None, DocumentView.NEAR) if k % 3 == 0 else ()):
                    self.assertEqual(v._word_near(index, a, limit),
                                     old_word_near(words, a, limit))
            # the whole page in reading order (a drag across pages takes it)
            self.assertEqual(v._page_order(index), DocumentView._reading_order(words))

    def test_box_drags_and_words_under_a_click(self):
        v = self.open(self.path)
        rnd = random.Random(12)
        words = v._words(0)
        for _ in range(40):
            a = P(rnd.uniform(0, 612), rnd.uniform(0, 792))
            b = a + (rnd.uniform(-300, 300), rnd.uniform(-300, 300))
            span = v.text_selection_span(0, a, 0, b, box=True)
            box = pymupdf.Rect(a, b).normalize()
            want = [w for w in words if old_word_in_box(pymupdf.Rect(w[:4]), box)]
            self.assertEqual(span, [(0, "box", want)])
        for w in rnd.sample(words, 30):
            pt = P((w[0] + w[2]) / 2, (w[1] + w[3]) / 2)
            under = words[old_word_near(words, pt, DocumentView.NEAR)]
            self.assertEqual(v.line_at(0, pt), [u for u in words if u[5:7] == under[5:7]])
            if under[4].strip():
                self.assertIn(under, v.word_at(0, pt))

    def test_a_drag_across_pages_still_reads_in_order(self):
        v = self.open(self.path)
        spans = v.text_selection_span(0, P(100, 100), 1, P(300, 300))
        self.assertEqual([s[0] for s in spans], [0, 1])
        order0 = DocumentView._reading_order(v._words(0))
        self.assertEqual(spans[0][2], order0[order0.index(spans[0][2][0]):])

    def test_a_mouse_move_of_a_drag_is_quick(self):
        v = self.open(self.path)
        words = v._words(0)
        v.text_selection(0, P(50, 100), P(60, 110))          # (the page's lookups made)
        t = time.perf_counter()
        n = 0
        for k in range(60):
            w = words[(k * 97) % len(words)]
            v.text_selection(0, P(45, 95), P(w[0], w[1]))
            n += 1
        per_move = (time.perf_counter() - t) / n
        self.assertLess(per_move, 0.02, f"{per_move * 1000:.1f} ms per mouse move")


class Joins(unittest.TestCase):
    """The plain-number boxes match pymupdf.Rect joins, rounding included."""

    def test_join_matches_rect_or(self):
        rnd = random.Random(3)
        for _ in range(3000):
            a = [rnd.uniform(-100, 900) for _ in range(4)]
            b = [rnd.uniform(-100, 900) for _ in range(4)]
            if rnd.random() < 0.2:
                b[2] = b[0]                         # an empty one
            want = tuple(pymupdf.Rect(a) | pymupdf.Rect(b))
            self.assertEqual(hit_index.join(a, b), want)

    def test_line_boxes_with_empty_characters(self):
        rnd = random.Random(4)
        for _ in range(500):
            units = []
            for n in range(rnd.randint(1, 6)):
                x = rnd.uniform(0, 500) + 0.1 * rnd.random()
                y = rnd.uniform(0, 500)
                w = rnd.choice((0.0, 0.0, rnd.uniform(0, 9)))
                units.append((x, y, x + w, y + rnd.uniform(1, 9), "a", 0, rnd.randint(0, 1), n))
            self.assertEqual([pymupdf.Rect(b) for b in hit_index.line_boxes(units)],
                             old_line_rects(units))


# ---- the markup under the pointer --------------------------------------------------------
def add(page, kind, **kw):
    m = {"kind": kind, "props": dict(annotations.DEFAULTS.get(kind, {})), "rect": pymupdf.Rect()}
    m["props"].update(kw.pop("props", {}))
    m.update(kw)
    return annotations.write(page, m).xref


def markups_pdf(rotation=0):
    d = pymupdf.open()
    p = d.new_page(width=800, height=800)
    p.insert_text((40, 40), "Some words here to highlight and underline", fontsize=12)
    words = p.get_text("words")
    q1, q2 = pymupdf.Rect(words[0][:4]).quad, pymupdf.Rect(words[2][:4]).quad
    add(p, "rect", rect=pymupdf.Rect(50, 80, 150, 150))
    add(p, "rect", rect=pymupdf.Rect(60, 90, 140, 140), props={"fill": "#ffcc00"})
    add(p, "ellipse", rect=pymupdf.Rect(200, 80, 300, 150))
    add(p, "rect", rect=pymupdf.Rect(350, 80, 450, 150), props={"cloud": True})
    add(p, "polygon", points=[P(500, 80), P(600, 80), P(550, 150)])
    add(p, "polyline", points=[P(50, 200), P(100, 250), P(150, 200)])
    add(p, "line", points=[P(200, 200), P(300, 250)])
    add(p, "arrow", points=[P(350, 200), P(450, 250)])
    add(p, "ink", strokes=[[P(500, 200), P(550, 240), P(600, 210)], [P(520, 230)]])
    add(p, "textbox", rect=pymupdf.Rect(50, 300, 200, 340), text="hello box")
    add(p, "note", rect=pymupdf.Rect(250, 300, 270, 320), text="sticky")
    add(p, "highlight", quads=[q1])
    add(p, "underline", quads=[q2])
    add(p, "comment", quads=[q1], text="a comment with its note")
    add(p, "stamp", rect=pymupdf.Rect(300, 300, 450, 350))
    add(p, "m_length", points=[P(50, 450), P(200, 450)])
    add(p, "m_area", points=[P(250, 420), P(350, 420), P(350, 500), P(250, 500)])
    add(p, "m_radius", points=[P(450, 600), P(500, 600)])
    add(p, "m_count", points=[P(450, 450)], n=1)
    add(p, "callout", rect=pymupdf.Rect(550, 420, 700, 460), points=[P(520, 500)], text="call")
    for k, flag in enumerate((pymupdf.PDF_ANNOT_IS_LOCKED, pymupdf.PDF_ANNOT_IS_HIDDEN)):
        a = p.add_rect_annot(pymupdf.Rect(600 + 60 * k, 600, 650 + 60 * k, 680))
        a.set_flags(flag)
        a.update()
        del a
    a = p.add_rect_annot(pymupdf.Rect(600, 700, 700, 780))      # (made by another program)
    a.set_border(width=4)
    a.update()
    del a
    if rotation:
        p.set_rotation(rotation)
    return save(d, f"markups{rotation}.pdf")


class MarkupUnderPointer(Base):
    def points(self, v, rnd, n=260):
        page = v.doc[0]
        rects = [a.rect for a in annotations.each_annot(page)]
        pts = []
        for _ in range(n):
            r = rnd.choice(rects)
            c = rnd.random()
            if c < 0.4:
                pts.append(P(rnd.choice((r.x0, r.x1)) + rnd.uniform(-5, 5),
                             rnd.uniform(r.y0 - 5, r.y1 + 5)))
            elif c < 0.85:
                pts.append(P(rnd.uniform(r.x0 - 6, r.x1 + 6), rnd.uniform(r.y0 - 6, r.y1 + 6)))
            else:
                pts.append(P(rnd.uniform(0, 800), rnd.uniform(0, 800)))
        return pts

    def test_the_same_markup_and_tooltip_as_before(self):
        rnd = random.Random(21)
        for rotation in (0, 90):
            v = self.open(markups_pdf(rotation))
            for zoom in (1.0, 0.4):
                v.set_zoom(zoom)
                found = 0
                for pt in self.points(v, rnd):
                    _page, a = old_annot_under(v, 0, pt)
                    want = a.xref if a is not None else None
                    self.assertEqual(v.annot_at(0, pt), want, (rotation, zoom, pt))
                    if want is not None:
                        found += 1
                        self.assertEqual(v.annot_tooltip(0, pt), old_tooltip(v, 0, pt))
                        _page, got = v._annot_under(0, pt)
                        self.assertEqual(got.xref, want)
                self.assertGreater(found, 60)

    def test_an_edit_is_seen_at_once(self):
        v = self.open(markups_pdf())
        pt = P(100, 80)                         # on the first box's top edge
        x = v.annot_at(0, pt)
        self.assertIsNotNone(x)
        v._set_selection(0, [x])
        v.delete_selected()
        self.assertNotEqual(v.annot_at(0, pt), x)
        v.undo()
        self.assertEqual(v.annot_at(0, pt), x)

    def test_one_mouse_move_tests_once_and_loads_little(self):
        d = pymupdf.open()
        p = d.new_page(width=2000, height=2000)
        for i in range(1500):
            r = pymupdf.Rect(20 + (i % 40) * 48, 20 + (i // 40) * 48, 60 + (i % 40) * 48,
                             60 + (i // 40) * 48)
            [p.add_rect_annot, p.add_circle_annot, p.add_freetext_annot][i % 3](
                r, *(["note %d" % i] if i % 3 == 2 else []))
        v = self.open(save(d, "many.pdf"))
        calls = []
        real_hit = DocumentView._annot_hit.__func__

        def counting(cls, an, pt, tol=4.0):
            calls.append(an.xref)
            return real_hit(cls, an, pt, tol)
        loads = []
        real_load = pymupdf.Page.load_annot

        def counting_load(page, ident):
            loads.append(ident)
            return real_load(page, ident)
        pts = [P(41 + (k % 30) * 48, 30 + (k // 30) * 97) for k in range(60)]
        with mock.patch.object(DocumentView, "_annot_hit", classmethod(counting)), \
                mock.patch.object(pymupdf.Page, "load_annot", counting_load):
            for pt in pts:
                calls.clear()
                v.annot_at(0, pt)
                once = len(calls)
                v.annot_tooltip(0, pt)
                v.annot_label(0, pt)
                self.assertEqual(len(calls), once)          # (the move's answer reused)
            loads.clear()
            t = time.perf_counter()
            for pt in pts:                              # the same places again
                v.annot_at(0, pt)
                v.annot_tooltip(0, pt)
            per_move = (time.perf_counter() - t) / len(pts)
        self.assertEqual(loads, [])                    # nothing loaded again
        self.assertLess(per_move, 0.01, f"{per_move * 1000:.1f} ms per mouse move")


# ---- Edit objects / Edit text: what's under the pointer -----------------------------------
def drawing_pdf():
    rnd = random.Random(5)
    d = pymupdf.open()
    p = d.new_page(width=1200, height=900)
    for _ in range(1500):
        x, y = rnd.uniform(0, 1150), rnd.uniform(0, 850)
        p.draw_line((x, y), (x + rnd.uniform(-60, 60), y + rnd.uniform(-60, 60)),
                    width=rnd.choice((0.5, 1, 3)))
    for _ in range(40):                          # long lines (contours): many pieces each
        x, y = rnd.uniform(0, 1000), rnd.uniform(0, 800)
        pts = [(x + k * 3, y + 20 * np.sin(k / 5)) for k in range(rnd.randint(70, 200))]
        p.draw_polyline(pts, width=0.7)
    for _ in range(60):
        x, y = rnd.uniform(0, 1100), rnd.uniform(0, 800)
        p.draw_rect(pymupdf.Rect(x, y, x + rnd.uniform(5, 90), y + rnd.uniform(5, 90)),
                    color=(0, 0, 0), fill=rnd.choice((None, (0.8, 0.8, 1))))
    for _ in range(20):
        x, y = rnd.uniform(0, 1100), rnd.uniform(0, 800)
        p.draw_bezier((x, y), (x + 40, y - 60), (x + 80, y + 60), (x + 120, y), width=1)
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 8, 8), False)
    pix.clear_with(120)
    p.insert_image(pymupdf.Rect(600, 600, 700, 680), pixmap=pix)
    for k in range(120):
        p.insert_text((rnd.uniform(0, 1100), rnd.uniform(20, 880)),
                      " ".join(rnd.choice(WORDS) for _ in range(3)),
                      fontsize=rnd.choice((5, 8, 11)))
    return save(d, "drawing.pdf")


class ObjectUnderPointer(Base):
    @classmethod
    def setUpClass(cls):
        cls.path = drawing_pdf()

    def test_the_same_object_and_line_as_before(self):
        v = self.open(self.path)
        rnd = random.Random(31)
        objs = v.content_objects(0)
        lines = v._lines(0)
        self.assertGreater(len(objs.items), 1500)
        for zoom in (1.0, 0.3):
            v.set_zoom(zoom)
            for k in range(400):
                c = k % 3
                if c == 0:
                    r = rnd.choice(objs.items)["rect"]
                    pt = P(rnd.uniform(r.x0 - 3, r.x1 + 3), rnd.uniform(r.y0 - 3, r.y1 + 3))
                elif c == 1:
                    r = rnd.choice(lines)[0]
                    pt = P(rnd.choice((r.x0 - 2, r.x1 + 2, rnd.uniform(r.x0, r.x1))),
                           rnd.choice((r.y0 - 2, r.y1 + 2, rnd.uniform(r.y0, r.y1))))
                else:
                    pt = P(rnd.uniform(0, 1200), rnd.uniform(0, 900))
                self.assertIs(v.object_at(0, pt), old_object_at(v, 0, pt), pt)
                self.assertIs(objs.at(pt, 4 / v.zoom), old_objects_at(objs, pt, 4 / v.zoom))
                self.assertEqual(v._line_at(0, pt), text_edit.line_at(lines, pt))

    def test_long_lines_tested_at_once_as_piece_by_piece(self):
        rnd = random.Random(32)
        for _ in range(300):
            line = [P(rnd.uniform(0, 100), rnd.uniform(0, 100)) for _ in range(rnd.randint(1, 30))]
            if rnd.random() < 0.3 and len(line) > 2:
                line[1] = P(line[0])                    # a piece of no length
            lines = [line, line[:2]]
            segs = hit_index.Segments(lines)
            for _ in range(20):
                pt = P(rnd.uniform(-5, 105), rnd.uniform(-5, 105))
                tol = rnd.choice((0.0, 0.5, 2, 6))
                self.assertEqual(segs.near(pt, tol), any(_near(ln, pt, tol) for ln in lines))

    def test_hovering_a_big_drawing_is_quick(self):
        v = self.open(self.path)
        v.content_objects(0)
        v.object_at(0, P(1, 1))                          # (lookups made once)
        rnd = random.Random(33)
        pts = [P(rnd.uniform(0, 1200), rnd.uniform(0, 900)) for _ in range(100)]
        t = time.perf_counter()
        for pt in pts:
            v.object_at(0, pt)
            v._line_at(0, pt)
        per_move = (time.perf_counter() - t) / len(pts)
        self.assertLess(per_move, 0.01, f"{per_move * 1000:.1f} ms per mouse move")


# ---- drawn the same way -------------------------------------------------------------------
def image():
    img = QImage(900, 700, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.white)
    return img


def pixels(img):
    a = np.frombuffer(bytes(img.constBits()), dtype=np.uint8).reshape(img.height(), -1, 4)
    return a[:, :img.width()]


def assert_same_picture(test, old, new, note=""):
    """The same picture: the old way rounded each point to MuPDF's 32-bit numbers on its
    way to the screen, which can tip a pixel at the very edge of a line one way or the
    other; nothing more may differ."""
    a, b = pixels(old), pixels(new)
    drawn = int((a != 255).any(axis=2).sum())
    test.assertGreater(drawn, 500, note)                # (something was drawn)
    d = np.abs(a.astype(int) - b.astype(int)).max(axis=2)
    differ, far = int((d > 0).sum()), int((d > 48).sum())
    test.assertLessEqual(far, max(8, drawn // 1000), (note, differ, far, int(d.max()), drawn))
    test.assertLessEqual(differ, drawn // 100, (note, differ, far, int(d.max()), drawn))


class Drawing(Base):
    @classmethod
    def setUpClass(cls):
        cls.path = drawing_pdf()

    def pens(self):
        return (QPen(QColor(0, 120, 215, 220), 2), QPen(QColor(0, 120, 215, 200), 2, Qt.DashLine),
                QPen(cad_commands.GHOST, 1, Qt.DashLine), QPen(QColor(0, 90, 200), 1.75))

    def test_selection_highlight_as_drawn_a_piece_at_a_time(self):
        for rotation in (0, 90):
            v = self.open(self.path)
            v.doc[0].set_rotation(rotation)
            v.set_zoom(0.7)
            w = v.pages[0]
            objs = v.content_objects(0)
            items = [it for it in objs.items if it["rect"].intersects(
                pymupdf.Rect(200, 200, 700, 600))]
            v.select_objects(0, items)
            page = v.doc[0]
            for aa in (False, True):
                for pen in self.pens():
                    old, new = image(), image()
                    p = QPainter(old)
                    p.setRenderHint(QPainter.Antialiasing, aa)
                    p.setPen(pen)
                    for it in items:
                        for line in v.object_lines(0, it):
                            pts = [w.to_screen_pt(q, page) for q in line]
                            for a, b in zip(pts, pts[1:]):
                                p.drawLine(a, b)
                    p.end()
                    p = QPainter(new)
                    p.setRenderHint(QPainter.Antialiasing, aa)
                    p.setPen(pen)
                    p.drawPath(w._selection_path(page))
                    p.end()
                    assert_same_picture(self, old, new, (rotation, aa, pen.style()))

    def test_selection_box_is_kept_until_the_selection_changes(self):
        v = self.open(self.path)
        objs = v.content_objects(0)
        v.select_objects(0, objs.items[:50])
        first = v.selected_objects_rect()
        self.assertEqual(first, page_objects.bounding(it["rect"] for it in objs.items[:50]))
        first.x0 -= 1000                                # (a caller changing its copy)
        self.assertEqual(v.selected_objects_rect(),
                         page_objects.bounding(it["rect"] for it in objs.items[:50]))
        v.select_objects(0, objs.items[60:70])
        self.assertEqual(v.selected_objects_rect(),
                         page_objects.bounding(it["rect"] for it in objs.items[60:70]))
        v.clear_object_selection()
        self.assertTrue(v.selected_objects_rect().is_empty)

    def test_command_preview_as_drawn_a_piece_at_a_time(self):
        v = self.open(self.path)
        v.doc[0].set_rotation(270)
        v.set_zoom(0.55)
        w = v.pages[0]
        objs = v.content_objects(0)
        items = objs.items[100:400]
        cmd = cad_commands.Move(v, None)
        cmd.kind, cmd.page, cmd.items = "objects", 0, items
        cmd.ghost = v.cad_outlines(0, "objects", items)
        cmd.pts = [P(300, 300)]
        cmd.hover = P(337.3, 321.9)
        self.assertLess(sum(len(ln) - 1 for ln in cmd.ghost), cad_commands.GHOST_SEGMENTS)
        new, old = image(), image()
        p = QPainter(new)
        p.setRenderHint(QPainter.Antialiasing)
        cmd.paint(w, p)
        p.end()
        # the old way: every piece moved, then drawn on its own
        to = v.doc[0].rotation_matrix * pymupdf.Matrix(v.zoom, v.zoom)

        def sp(q):
            q = pymupdf.Point(q) * to
            return QPointF(q.x, q.y)
        p = QPainter(old)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(cad_commands.GHOST, 1, Qt.DashLine))
        m = cad_commands.translate(cmd.hover - cmd.pts[0])
        for line in cmd.ghost:
            pts = [pymupdf.Point(q) * m for q in line]
            for a, b in zip(pts, pts[1:]):
                p.drawLine(sp(a), sp(b))
        p.setPen(QPen(cad_commands.BAND, 1, Qt.DashLine))
        p.drawLine(sp(cmd.pts[0]), sp(cmd.hover))
        p.setPen(QPen(cad_commands.BAND, 1))
        for q in cmd.pts:
            c = QPointF(sp(q))
            p.drawLine(c + QPointF(-5, 0), c + QPointF(5, 0))
            p.drawLine(c + QPointF(0, -5), c + QPointF(0, 5))
        p.end()
        assert_same_picture(self, old, new)


# ---- night mode and the rendered page ----------------------------------------------------
class Pixels(Base):
    def test_night_mode_bytes_as_before(self):
        rng = np.random.default_rng(1)
        for w, h, pad in ((1, 1, 0), (7, 3, 1), (333, 211, 3), (1000, 400, 0)):
            stride = w * 3 + pad
            data = rng.integers(0, 256, size=h * stride, dtype=np.uint8).tobytes()
            self.assertEqual(page_widget.night_samples(data, w, h, stride),
                             old_night(data, w, h, stride))
        # every gray and the pure colors
        data = bytes(v for c in range(256) for v in (c, c, c)) + bytes(
            [255, 0, 0, 0, 255, 0, 0, 0, 255, 255, 255, 0, 0, 255, 255, 255, 0, 255])
        n = len(data) // 3
        self.assertEqual(page_widget.night_samples(data, n, 1, n * 3), old_night(data, n, 1, n * 3))

    def test_rendered_page_as_before_and_its_own_copy(self):
        v = self.open(drawing_pdf())
        w = v.pages[0]
        dl = v.doc[0].get_displaylist()
        for night in (False, True):
            DocumentView.night_mode = night
            self.addCleanup(setattr, DocumentView, "night_mode", False)
            pm = dl.get_pixmap(matrix=pymupdf.Matrix(1.3, 1.3), alpha=False)
            data = old_night(pm.samples, pm.width, pm.height, pm.stride) if night \
                else pm.samples
            stride = pm.width * 3 if night else pm.stride
            want = QPixmap.fromImage(QImage(data, pm.width, pm.height, stride,
                                            QImage.Format_RGB888).copy()).toImage()
            pix = w._to_qpixmap(pm, 1.0)
            del pm                                  # (the pixmap must not need its memory)
            gc.collect()
            junk = [bytearray(b"\x5a" * 4_000_000) for _ in range(4)]   # reuse freed memory
            got = pix.toImage()
            del junk
            self.assertEqual(got.convertToFormat(QImage.Format_RGB32),
                             want.convertToFormat(QImage.Format_RGB32), night)


# ---- the garbage collector -------------------------------------------------------------
class SetAside(Base):
    def tearDown(self):
        gc.unfreeze()

    def test_a_big_drawing_is_set_aside_and_given_back(self):
        gc.unfreeze()
        document_view._set_aside(types.SimpleNamespace(items=[0] * 100))
        self.assertEqual(gc.get_freeze_count(), 0)             # (a small one: left alone)
        document_view._set_aside(None)
        self.assertEqual(gc.get_freeze_count(), 0)
        document_view._set_aside(types.SimpleNamespace(
            items=[0] * document_view.FREEZE_ITEMS))
        self.assertGreater(gc.get_freeze_count(), 0)
        document_view._collect_all()
        self.assertEqual(gc.get_freeze_count(), 0)

    def test_what_is_set_aside_is_still_freed(self):
        import weakref

        class Thing:
            pass
        t = Thing()
        t.me = t                                         # a cycle: only the collector frees it
        gone = weakref.ref(t)
        document_view._set_aside(types.SimpleNamespace(items=[0] * document_view.FREEZE_ITEMS))
        del t
        gc.collect()
        self.assertIsNotNone(gone())                     # set aside: not collected yet
        document_view._collect_all()
        self.assertIsNone(gone())

    def test_closing_the_file_gives_it_back(self):
        v = view(markups_pdf())
        v.dirty = False
        document_view._set_aside(types.SimpleNamespace(items=[0] * document_view.FREEZE_ITEMS))
        self.assertGreater(gc.get_freeze_count(), 0)
        v.close_doc()
        self.assertEqual(gc.get_freeze_count(), 0)


if __name__ == "__main__":
    unittest.main()
