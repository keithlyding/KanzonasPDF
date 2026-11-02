"""1.6.1: a markup that is only moved (Move, a nudge, a drag, text moved with its
highlights) is moved where it is: its box and the positions it keeps are shifted and its
drawing goes along, instead of deleting it and writing it anew (30 times quicker, and a box
drawn by another program no longer grows by its border on each move). For every kind of
markup, on a plain and a turned page: the picture is the old one moved exactly, it is the
same markup (same xref, so its replies, place in the stacking order and selection stay),
it reads back as moved, Ctrl+Z puts it back, and it survives saving.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_move_in_place
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

from kanzonas import annotations  # noqa: E402
from kanzonas.document_view import DocumentView  # noqa: E402

P = pymupdf.Point
D = P(13, 7)                    # the move (whole points: the picture shifts by whole pixels)


def add(page, kind, **kw):
    m = {"kind": kind, "props": dict(annotations.DEFAULTS.get(kind, {})),
         "rect": pymupdf.Rect()}
    m["props"].update(kw.pop("props", {}))
    m.update(kw)
    return annotations.write(page, m).xref


def every_kind(rotation):
    d = pymupdf.open()
    p = d.new_page(width=800, height=800)
    p.insert_text((40, 40), "Some words here to highlight and underline", fontsize=12)
    words = p.get_text("words")
    q1, q2 = pymupdf.Rect(words[0][:4]).quad, pymupdf.Rect(words[2][:4]).quad
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 10, 10), False)
    pix.clear_with(90)
    add(p, "rect", rect=pymupdf.Rect(50, 80, 150, 150))
    add(p, "ellipse", rect=pymupdf.Rect(200, 80, 300, 150))
    add(p, "rect", rect=pymupdf.Rect(350, 80, 450, 150), props={"cloud": True})
    add(p, "polygon", points=[P(500, 80), P(600, 80), P(550, 150)])
    add(p, "polyline", points=[P(50, 200), P(100, 250), P(150, 200)])
    add(p, "opencloud", points=[P(50, 600), P(50, 700), P(200, 700)],     # (a trimmed cloud)
        cloud={"i": 2, "phase": [0.3, 0.0, 0.0], "ends": [-1, 0, 1, 0], "flip": False})
    add(p, "line", points=[P(200, 200), P(300, 250)])
    add(p, "arrow", points=[P(350, 200), P(450, 250)])
    add(p, "ink", strokes=[[P(500, 200), P(550, 240), P(600, 210)]])
    add(p, "arc", points=[P(640, 200), P(700, 170), P(760, 200)])         # (curves.py)
    add(p, "line", points=[P(560, 700), P(760, 700)], bend=P(660, 740))
    add(p, "arrow", points=[P(560, 770), P(760, 750)], bend=P(660, 720),
        props={"head": "closed"})
    add(p, "textbox", rect=pymupdf.Rect(50, 300, 200, 340), text="hello box")
    add(p, "note", rect=pymupdf.Rect(250, 300, 270, 320), text="sticky")
    add(p, "highlight", quads=[q1])
    add(p, "underline", quads=[q2])
    add(p, "comment", quads=[q1], text="a comment with its note")
    add(p, "stamp", rect=pymupdf.Rect(300, 300, 450, 350))
    add(p, "image", rect=pymupdf.Rect(500, 300, 560, 360), image_bytes=pix.tobytes("png"))
    add(p, "m_length", points=[P(50, 450), P(200, 450)])
    add(p, "m_area", points=[P(250, 420), P(350, 420), P(350, 500), P(250, 500)])
    add(p, "m_radius", points=[P(450, 600), P(500, 600)])
    add(p, "m_count", points=[P(450, 450)], n=1)
    add(p, "callout", rect=pymupdf.Rect(550, 420, 700, 460), points=[P(520, 500)],
        text="call")
    a = p.add_rect_annot(pymupdf.Rect(600, 600, 700, 680))  # (made by another program)
    a.set_border(width=4)
    a.update()
    del a
    # only the markups on the page (they are what's compared, pixel for pixel)
    for x in p.get_contents():
        d.update_stream(x, b"")
    if rotation:
        p.set_rotation(rotation)
    path = os.path.join(tempfile.mkdtemp(), "kinds.pdf")
    d.save(path)
    return path


class MoveInPlace(unittest.TestCase):
    def view(self, rotation):
        v = DocumentView(every_kind(rotation))
        self.addCleanup(v.close_doc)
        self.addCleanup(lambda: setattr(v, "dirty", False))
        return v

    def models(self, v):
        page = v.doc[0]
        return [(a.xref, annotations.read(a)) for a in annotations.each_annot(page)]

    def picture(self, v):
        return v.doc[0].get_pixmap(dpi=72, alpha=False)

    def check(self, rotation):
        v = self.view(rotation)
        before = self.models(v)
        self.assertGreaterEqual(len(before), 20)
        old_pic = self.picture(v)
        v._set_selection(0, [x for x, _m in before])
        v.cad_apply("Moved", pymupdf.Matrix(1, 0, 0, 1, D.x, D.y))
        after = dict(self.models(v))
        # the same markups (moved where they are), reading back as moved
        self.assertEqual(sorted(after), sorted(x for x, _m in before))
        for x, m in before:
            self.assertIsNotNone(annotations.translation(m, after[x]), m["kind"])
            self.assertTrue(annotations._same(
                annotations.translation(m, after[x]), D), m["kind"])
        # the picture: the old one, moved exactly (D as seen on the turned page)
        page = v.doc[0]
        shown = D * page.rotation_matrix - P(0, 0) * page.rotation_matrix
        del page
        sx, sy = round(shown.x), round(shown.y)
        new_pic = self.picture(v)
        W, H = old_pic.width, old_pic.height
        bad = 0
        for y in range(0, H):
            for x in range(0, W):
                ox, oy = x - sx, y - sy
                want = old_pic.pixel(ox, oy) if 0 <= ox < W and 0 <= oy < H else (255, 255, 255)
                # (a turned page's edges of a see-through highlight round a level or two
                # differently: not to be seen; anything moved wrongly differs by far more)
                if max(abs(a - b) for a, b in zip(new_pic.pixel(x, y), want)) > 3:
                    bad += 1
        self.assertEqual(bad, 0, f"{bad} pixels differ from the old picture moved")
        # the selection stays; Ctrl+Z puts everything back
        self.assertEqual(sorted(v.selected_xrefs()), sorted(after))
        v.undo()
        back = dict(self.models(v))
        for x, m in before:
            self.assertTrue(annotations._same(back[x]["rect"], m["rect"]), m["kind"])
        # saved and opened again, still moved
        v.redo() if hasattr(v, "redo") else v.cad_apply(
            "Moved", pymupdf.Matrix(1, 0, 0, 1, D.x, D.y))
        out = os.path.join(tempfile.mkdtemp(), "saved.pdf")
        v.doc.save(out)
        d2 = pymupdf.open(out)
        p2 = d2[0]
        again = {a.xref: annotations.read(a) for a in annotations.each_annot(p2)}
        for x, m in before:
            self.assertIsNotNone(annotations.translation(m, again[x]), m["kind"])

    def test_every_kind_on_a_plain_page(self):
        self.check(0)

    def test_every_kind_on_a_turned_page(self):
        self.check(90)

    def test_anything_more_than_a_move_is_written_anew(self):
        v = self.view(0)
        before = self.models(v)
        v._set_selection(0, [x for x, m in before if m["kind"] == "rect"])
        v.cad_apply("Turned", pymupdf.Matrix(90))
        after = {x for x, _m in self.models(v)}
        self.assertTrue(any(x not in after for x, m in before if m["kind"] == "rect"))

    def test_text_and_its_highlight_selected_together_move_once(self):
        d = pymupdf.open()
        p = d.new_page(width=400, height=300)
        p.insert_text((60, 100), "PANEL A", fontsize=12)
        p.draw_line((50, 200), (350, 200))
        r = pymupdf.Rect(p.get_text("words")[0][:4])
        add(p, "highlight", quads=[r.quad])
        path = os.path.join(tempfile.mkdtemp(), "hl.pdf")
        d.save(path)
        v = DocumentView(path)
        self.addCleanup(v.close_doc)
        self.addCleanup(lambda: setattr(v, "dirty", False))
        (x, m), = self.models(v)
        v.select_objects(0, [it for it in v.text_objects(0)])
        v._set_selection(0, [x])
        self.assertEqual(v.cad_targets()[0], "both")
        v.cad_apply("Moved", pymupdf.Matrix(1, 0, 0, 1, 0, 30))
        (_x, after), = self.models(v)
        self.assertAlmostEqual(after["quads"][0].ul.y - m["quads"][0].ul.y, 30, delta=0.01)
        words = v.doc[0].get_text("words")
        self.assertAlmostEqual(words[0][1] - r.y0, 30, delta=0.5)

    def test_a_restyle_is_not_taken_for_a_move(self):
        old = {"kind": "rect", "props": {"stroke": "#ff0000"}, "rect": pymupdf.Rect(0, 0, 10, 10)}
        new = annotations.moved(old, P(5, 5))
        new["props"] = {"stroke": "#00ff00"}
        self.assertIsNone(annotations.translation(old, new))
        self.assertIsNone(annotations.translation(old, annotations.copy(old)))


if __name__ == "__main__":
    unittest.main()
