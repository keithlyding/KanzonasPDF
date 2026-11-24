"""The Drawing tab (1.17, the owner, 23 Nov 2026): line, arrow, polyline, polygon, rectangle,
ellipse, circle, arc, cloud and pen drawn into the page itself (vector drawing in its content
stream, not markups), on a layer of their own, "KanzonasPDF drawing"; and Convert to drawing,
which turns a shape markup already on the page into that drawing, looking as it did.

Checked here: each tool writes page content on the layer with the geometry drawn and the
tool's style, read back by Edit objects as an ordinary object (selected, restyled, grouped with
the drawing's own lines, sent to the back, all keeping the layer); the layer in the Layers
panel hides it; Convert to drawing for a polygon, a rectangle and a line, pixel for pixel; one
undo step per shape, redo, Save and open again; pages turned 90, 180 and 270 degrees, drawn
with real mouse events.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_drawing_tab
"""
import os
import re
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402
from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import annotations as A  # noqa: E402
from kanzonas import drawing, page_objects as po  # noqa: E402
from kanzonas.document_view import DocumentView  # noqa: E402

P = pymupdf.Point
R = pymupdf.Rect


def sheet(rotation=0, line=True):
    """A page with one line of its own drawing (blue, 2 pt) across its top, saved."""
    d = pymupdf.open()
    p = d.new_page(width=600, height=800)
    if line:
        p.draw_line((40, 60), (560, 60), color=(0, 0, 1), width=2)
    p.insert_text((40, 760), "the page's own text", fontsize=10)
    if rotation:
        p.set_rotation(rotation)
    path = os.path.join(tempfile.mkdtemp(), "sheet.pdf")
    d.save(path)
    return path


def near(a, b, tol=0.05):
    return abs(a[0] - b[0]) <= tol and abs(a[1] - b[1]) <= tol


def pixels(page, annots=True):
    """The page drawn at 2x (as shown: turned with the page), its samples."""
    pix = page.get_pixmap(matrix=pymupdf.Matrix(2, 2), annots=annots, alpha=False)
    return pix


def differing(a, b, level=60):
    """How many pixels of two same-sized pictures differ by more than level in a channel."""
    assert (a.width, a.height) == (b.width, b.height)
    sa, sb, n = a.samples, b.samples, a.n
    count = 0
    for i in range(0, len(sa), n):
        if any(abs(sa[i + k] - sb[i + k]) > level for k in range(n)):
            count += 1
    return count


def dark_near(pix, pt, r=2):
    """Whether pix (a 2x picture) has a dark pixel within r pixels of pt (shown points)."""
    x0, y0 = int(pt.x * 2), int(pt.y * 2)
    for y in range(y0 - r, y0 + r + 1):
        for x in range(x0 - r, x0 + r + 1):
            if 0 <= x < pix.width and 0 <= y < pix.height:
                if sum(pix.pixel(x, y)[:3]) < 450:
                    return True
    return False


class Base(unittest.TestCase):
    MODE = "standard"

    def setUp(self):
        for key in ("mouse_mode", "cad_select", "click_click", "lasso", "reuse_tools"):
            self.addCleanup(setattr, DocumentView, key, getattr(DocumentView, key))
        DocumentView.mouse_mode = self.MODE
        DocumentView.cad_select = False
        DocumentView.click_click = DocumentView.lasso = False
        DocumentView.reuse_tools = True
        for tool in A.DRAW_TOOLS:
            A.reset_tool_props(tool)
            self.addCleanup(A.reset_tool_props, tool)

    def view(self, path=None, show=False):
        if show:
            for old in APP.topLevelWidgets():
                if old.isVisible():
                    old.hide()
        v = DocumentView(path or sheet())
        self.addCleanup(v.close_doc)
        self.addCleanup(setattr, v, "dirty", False)
        v.snap_grid = v.snap_objects = v.snap_page = False
        if show:
            self.addCleanup(v.hide)
            v.resize(900, 1000)
            v.show()
            APP.processEvents()
            v.set_zoom(1.0)
            APP.processEvents()
        return v

    def drawn(self, v, i=0):
        """The page's objects on the drawing layer, in drawing order."""
        objs = v.content_objects(i)
        names = v.drawing_names(i)
        return [it for it in objs.items if drawing.on_layer(it["obj"].get("ctx"), names)]

    def draw(self, v, tool, *geom, i=0):
        """Draw with a Drawing tool as the page widget does when the mouse ends it."""
        v.set_tool(tool)
        base = drawing.base_tool(tool)
        if base in ("polyline", "polygon", "arc"):
            v.apply_poly(i, base, [P(q) for q in geom[0]])
        elif base == "ink":
            v.apply_ink(i, [P(q) for q in geom[0]])
        else:
            v.apply_drag_tool(i, base, P(geom[0]), P(geom[1]), False)
        APP.processEvents()

    def lines(self, v, it, i=0):
        return [[(q[0], q[1]) for q in line] for line in v.content_objects(i).lines(it)]


class EachTool(Base):
    """Each tool writes the page's own drawing, on the layer, as it was drawn."""

    CASES = [
        ("d_line", ((100, 100), (300, 200))),
        ("d_arrow", ((100, 300), (300, 250))),
        ("d_polyline", ([(50, 400), (150, 420), (200, 380), (260, 470)],)),
        ("d_polygon", ([(300, 400), (450, 420), (380, 520)],)),
        ("d_rect", ((320, 120), (480, 220))),
        ("d_ellipse", ((100, 520), (260, 600))),
        ("d_circle", ((400, 620), (440, 650))),
        ("d_arc", ([(300, 300), (360, 260), (420, 300)],)),
        ("d_cloud", ((60, 640), (200, 720))),
        ("d_ink", ([(450, 120), (470, 140), (500, 130), (520, 160)],)),
    ]

    def test_every_tool_writes_page_content_on_the_layer(self):
        v = self.view()
        page_annots = lambda: len(list(v.doc[0].annots()))   # noqa: E731
        self.assertIsNone(drawing.layer_xref(v.doc))
        before = po._contents(v.doc[0])
        for k, (tool, geom) in enumerate(self.CASES):
            with self.subTest(tool=tool):
                self.draw(v, tool, *geom)
                self.assertEqual(page_annots(), 0, "a markup was made")
                got = self.drawn(v)
                self.assertEqual(len(got), k + 1)
                self.check_shape(v, tool, geom, got[-1])
        # one layer, in the Layers panel's list, named as the owner asked
        self.assertEqual([o["name"] for o in v.doc.get_ocgs().values()], [drawing.LAYER])
        self.assertIn(drawing.LAYER, [c.get("text") for c in v.layer_configs()])
        # the page's own line and text are still there, first, as they were
        self.assertTrue(po._contents(v.doc[0]).startswith(before.rstrip(b"\n")) or
                        before.strip() in po._contents(v.doc[0]))
        objs = v.content_objects(0)
        self.assertFalse(drawing.on_layer(objs.items[0]["obj"]["ctx"], v.drawing_names(0)))
        # one undo step a shape, back to the page as it was; redo brings them back
        for k in range(len(self.CASES), 0, -1):
            self.assertEqual(len(self.drawn(v)), k)
            v.undo()
        self.assertEqual(self.drawn(v), [])
        self.assertEqual(po._contents(v.doc[0]), before)
        self.assertIsNone(drawing.layer_xref(v.doc))
        for k in range(1, len(self.CASES) + 1):
            v.redo()
            self.assertEqual(len(self.drawn(v)), k)

    def check_shape(self, v, tool, geom, it):
        d = it["obj"]
        st = po.style_of(d)
        self.assertEqual(st["stroke"], "#000000")       # (the Drawing tab's default: black)
        self.assertAlmostEqual(po.page_width(d), 1.0, places=3)
        if tool not in ("d_cloud", "d_ink"):
            self.assertEqual(st["dash"], "solid")
        box = it["rect"]
        lines = self.lines(v, it)
        ends = [q for line in lines for q in (line[0], line[-1])]
        if tool in ("d_line", "d_arrow"):
            a, b = geom
            self.assertTrue(any(near(q, a) for q in ends), (tool, ends))
            self.assertTrue(any(near(q, b) for q in ends), (tool, ends))
            data = v.content_objects(0).data
            heads = po.heads_of(data, d)
            if tool == "d_arrow":
                self.assertEqual(heads[:3], ("none", "open", "none"))
            else:
                self.assertIsNone(heads)
        elif tool in ("d_polyline", "d_polygon"):
            pts = geom[0]
            flat = [q for line in lines for q in line]
            for q in pts:
                self.assertTrue(any(near(q, f) for f in flat), (tool, q))
            self.assertTrue(near((box.x0, box.y0), (min(x for x, _ in pts),
                                                    min(y for _, y in pts))))
            if tool == "d_polygon":
                self.assertEqual(lines[0][0], lines[0][-1])     # (closed)
        elif tool in ("d_rect", "d_ellipse"):
            want = R(geom[0], geom[1])
            self.assertTrue(near(box.tl, want.tl) and near(box.br, want.br), (tool, box))
        elif tool == "d_circle":
            c, on = P(geom[0]), P(geom[1])
            r = abs(on - c)
            self.assertTrue(near(box.tl, (c.x - r, c.y - r)) and
                            near(box.br, (c.x + r, c.y + r)), box)
        elif tool == "d_arc":
            a, m, c = geom[0]
            flat = [q for line in lines for q in line]
            self.assertTrue(near(flat[0], a) and near(flat[-1], c), (flat[0], flat[-1]))
            # (the point it passes through: on the curve as drawn)
            self.assertLess(min(abs(P(q) - P(m)) for q in flat), 1.0)
        elif tool == "d_cloud":
            want = R(geom[0], geom[1])
            self.assertTrue(box.contains(want), (box, want))
            self.assertLess(box.width, want.width + 30)
        elif tool == "d_ink":
            flat = [q for line in lines for q in line]
            for q in geom[0]:
                self.assertTrue(any(near(q, f) for f in flat), q)
            ops = [op for op, *_r in po._tokens(d["state"])]
            self.assertIn(b"J", ops)            # (round ends and corners, as the Pen's)
            self.assertIn(b"j", ops)

    def test_the_tools_style_is_used(self):
        v = self.view()
        A.set_tool_props("d_rect", dict(A.tool_props("d_rect"), stroke="#ff0000",
                                        fill="#0000ff", width=3.0, dash="dash",
                                        fill_opacity=0.5))
        A.set_tool_props("d_line", dict(A.tool_props("d_line"), stroke="#00a000", width=2.0,
                                        dash="dot", head_start="closed", head="open"))
        self.draw(v, "d_rect", (100, 100), (300, 200))
        self.draw(v, "d_line", (100, 300), (400, 300))
        rect, line = self.drawn(v)
        st = po.style_of(rect["obj"])
        self.assertEqual((st["stroke"], st["fill"], st["dash"]), ("#ff0000", "#0000ff", "dash"))
        self.assertAlmostEqual(po.page_width(rect["obj"]), 3.0, places=3)
        # the fill half see-through, the outline not (an ExtGState of the page's)
        gs = [op for op in rect["obj"]["state"].split() if op.startswith(b"/KZDrawA")]
        self.assertEqual(len(gs), 1)
        page = v.doc[0]
        text = page.parent.xref_get_key(page.xref, "Resources/ExtGState/" + gs[0][1:].decode())
        self.assertEqual(text[0], "dict")
        nums = dict(re.findall(r"/(CA|ca) ([\d.]+)", text[1]))
        self.assertEqual((float(nums["CA"]), float(nums["ca"])), (1.0, 0.5))
        st = po.style_of(line["obj"])
        self.assertEqual((st["stroke"], st["dash"]), ("#00a000", "dot"))
        self.assertAlmostEqual(po.page_width(line["obj"]), 2.0, places=3)
        heads = po.heads_of(v.content_objects(0).data, line["obj"])
        self.assertEqual(heads[:3], ("closed", "open", "none"))
        # what Properties shows for them
        v.select_objects(0, [line])
        self.assertEqual(v.object_style(), {"stroke": "#00a000", "dash": "dot",
                                            "start": "closed", "end": "open", "mid": "none"})
        self.assertTrue(v.objects_drawn())

    def test_no_outline_and_no_fill_draws_nothing(self):
        v = self.view()
        A.set_tool_props("d_rect", dict(A.tool_props("d_rect"), stroke=None, fill=None))
        rev = v.revision
        self.draw(v, "d_rect", (100, 100), (300, 200))
        self.assertEqual(v.revision, rev)
        self.assertEqual(self.drawn(v), [])

    def test_a_drawing_tool_draws_over_a_markup(self):
        # (it doesn't pick the markup under the click to move it, as the markup tools do)
        v = self.view(show=True)
        v.set_tool("rect")
        v.apply_drag_tool(0, "rect", P(100, 100), P(300, 300), False)
        v.clear_selection()
        v.set_tool("d_line")
        w = v.pages[0]

        def at(xy):
            q = w.to_screen_pt(P(xy))
            return QPoint(round(q.x()), round(q.y()))
        QTest.mousePress(w, Qt.LeftButton, Qt.NoModifier, at((150, 100)))
        QTest.mouseMove(w, at((200, 150)))
        QTest.mouseMove(w, at((250, 200)))
        QTest.mouseRelease(w, Qt.LeftButton, Qt.NoModifier, at((250, 200)), 300)
        APP.processEvents()
        self.assertIsNone(v.selection)
        got = self.drawn(v)
        self.assertEqual(len(got), 1)
        self.assertEqual(len(list(v.doc[0].annots())), 1)        # (the markup as it was)


class EditObjects(Base):
    """Edit objects works on the drawing as on the page's own lines."""

    def test_selected_restyled_and_kept_on_the_layer(self):
        v = self.view()
        A.set_tool_props("d_rect", dict(A.tool_props("d_rect"), fill="#c0c0c0"))
        self.draw(v, "d_rect", (100, 100), (300, 200))
        self.draw(v, "d_arrow", (100, 300), (300, 300))
        v.set_tool("editobjects")
        rect, arrow = self.drawn(v)
        # a click on its outline selects it, as any of the page's lines
        hit = v.content_objects(0).at(P(100, 150), 3)
        self.assertIsNotNone(hit)
        self.assertEqual(hit["rect"], rect["rect"])
        v.select_objects(0, [rect])
        v.style_objects(stroke="#ff0000", fill="#00ff00")
        v.set_object_width(4.0)
        rect = self.drawn(v)[0]
        st = po.style_of(rect["obj"])
        self.assertEqual((st["stroke"], st["fill"]), ("#ff0000", "#00ff00"))
        self.assertAlmostEqual(po.page_width(rect["obj"]), 4.0, places=3)
        # arrowheads changed on the arrow, as on a line of the drawing
        arrow = self.drawn(v)[1]
        v.select_objects(0, [arrow])
        v.style_objects(heads={"start": "closed"})
        arrow = self.drawn(v)[1]
        self.assertEqual(po.heads_of(v.content_objects(0).data, arrow["obj"])[:3],
                         ("closed", "open", "none"))
        # moved: still on the layer, one undo step
        before = po._contents(v.doc[0])
        v.select_objects(0, [arrow])
        v.move_objects(v.selected_objects_rect() + (30, 40, 30, 40))
        moved = self.drawn(v)
        self.assertEqual(len(moved), 2)
        self.assertTrue(near(moved[1]["rect"].tl, (arrow["rect"].x0 + 30, arrow["rect"].y0 + 40),
                             0.1))
        v.undo()
        self.assertEqual(po._contents(v.doc[0]), before)

    def test_grouped_with_the_drawings_own_lines(self):
        v = self.view()
        self.draw(v, "d_line", (100, 100), (300, 200))
        objs = v.content_objects(0)
        own = objs.items[0]                 # (the page's own blue line, on no layer)
        mine = self.drawn(v)[0]
        self.assertFalse(drawing.on_layer(own["obj"]["ctx"], v.drawing_names(0)))
        v.set_tool("editobjects")
        v.select_objects(0, [own, mine])
        self.assertIsNone(po.group_problem(v.content_objects(0), [own, mine]))
        self.assertIsNot(v.group_objects(), False)
        groups = [it for it in v.content_objects(0).items if it["kind"] == "group"]
        self.assertEqual(len(groups), 1)
        # inside the group the drawn line keeps its layer: hiding it hides that line only
        doc = v.doc
        body = doc.xref_stream(groups[0]["xref"])
        self.assertIn(b"/OC /", body)
        shown = pixels(doc[0])
        self.assertTrue(dark_near(shown, P(200, 150)))
        self.assertTrue(dark_near(shown, P(300, 60)))
        number = [c["number"] for c in v.layer_configs() if c.get("text") == drawing.LAYER][0]
        v.set_layer(number, False)
        hidden = pixels(doc[0])
        self.assertFalse(dark_near(hidden, P(200, 150)))
        self.assertTrue(dark_near(hidden, P(300, 60)))
        v.set_layer(number, True)
        # Ungroup gives both back, the drawn line on its layer
        v.select_objects(0, groups)
        v.ungroup_objects()
        self.assertEqual(len(self.drawn(v)), 1)

    def test_grouped_with_a_cad_sheets_clipped_lines(self):
        # (a plotted sheet draws its lines inside its frame, a clip; the Drawing tab's have
        # none: a clip holding all of them cuts nothing, so they can be one group)
        d = pymupdf.open()
        p = d.new_page(width=600, height=800)
        x = d.get_new_xref()
        d.update_object(x, "<<>>")
        d.update_stream(x, b"q 10 10 580 780 re W n 0 0 1 RG 2 w 40 740 m 560 740 l S "
                           b"40 700 m 560 700 l S Q\nq 30 600 100 50 re W n 0 0 1 RG 2 w "
                           b"20 620 m 300 620 l S Q\n")
        p.set_contents(x)
        path = os.path.join(tempfile.mkdtemp(), "plot.pdf")
        d.save(path)
        v = self.view(path)
        self.draw(v, "d_line", (100, 200), (300, 300))
        objs = v.content_objects(0)
        framed, cut, mine = objs.items[0], objs.items[2], objs.items[3]
        self.assertTrue(drawing.on_layer(mine["obj"]["ctx"], v.drawing_names(0)))
        self.assertIsNone(po.group_problem(objs, [framed, objs.items[1], mine]))
        # (a clip that cuts one of them off is still one they can't be grouped across)
        self.assertIsNotNone(po.group_problem(objs, [cut, mine]))
        before = pixels(v.doc[0])
        v.set_tool("editobjects")
        v.select_objects(0, [framed, objs.items[1], mine])
        self.assertIsNot(v.group_objects(), False)
        self.assertEqual(len([it for it in v.content_objects(0).items
                              if it["kind"] == "group"]), 1)
        self.assertEqual(differing(before, pixels(v.doc[0])), 0)

    def test_sent_to_the_back_on_its_layer(self):
        v = self.view()
        A.set_tool_props("d_rect", dict(A.tool_props("d_rect"), fill="#ffff00"))
        self.draw(v, "d_rect", (100, 40), (300, 100))      # (over the page's blue line)
        mine = self.drawn(v)[0]
        self.assertGreater(mine["n"], 0)
        v.set_tool("editobjects")
        v.select_objects(0, [mine])
        v.arrange_objects("back")
        got = self.drawn(v)
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["n"], 0)                   # (first in the drawing order)
        # the page's blue line is drawn over the yellow box now
        pix = pixels(v.doc[0])
        r, g, b = pix.pixel(400, 120)[:3]
        self.assertGreater(b, 150)
        self.assertLess(r, 120)
        # and it's still the layer's: hidden with it
        number = [c["number"] for c in v.layer_configs() if c.get("text") == drawing.LAYER][0]
        v.set_layer(number, False)
        r, g, b = pixels(v.doc[0]).pixel(300, 160)[:3]
        self.assertGreater(min(r, g, b), 240)             # (white: the box is hidden)
        v.set_layer(number, True)


class Layer(Base):
    def test_turning_the_layer_off_hides_the_drawing(self):
        v = self.view()
        self.draw(v, "d_rect", (100, 300), (300, 400))
        self.draw(v, "d_line", (100, 500), (300, 500))
        page = v.doc[0]
        on = pixels(page)
        self.assertTrue(dark_near(on, P(100, 350)))
        self.assertTrue(dark_near(on, P(200, 500)))
        configs = v.layer_configs()
        self.assertEqual([c.get("text") for c in configs], [drawing.LAYER])
        v.set_layer(configs[0]["number"], False)
        off = pixels(v.doc[0])
        self.assertFalse(dark_near(off, P(100, 350)))
        self.assertFalse(dark_near(off, P(200, 500)))
        self.assertTrue(dark_near(off, P(300, 60)))         # (the page's own line stays)
        v.set_layer(configs[0]["number"], True)
        self.assertTrue(dark_near(pixels(v.doc[0]), P(100, 350)))

    def test_drawing_on_the_hidden_layer_shows_it_again(self):
        v = self.view()
        self.draw(v, "d_rect", (100, 300), (300, 400))
        number = v.layer_configs()[0]["number"]
        v.set_layer(number, False)
        self.assertFalse(v.layer_configs()[0]["on"])
        self.draw(v, "d_line", (100, 500), (300, 500))
        self.assertTrue(v.layer_configs()[0]["on"])
        self.assertTrue(dark_near(pixels(v.doc[0]), P(200, 500)))

    def test_the_layer_is_made_once_and_kept_by_name(self):
        v = self.view()
        for k in range(3):
            self.draw(v, "d_line", (100, 100 + 50 * k), (300, 100 + 50 * k))
        self.assertEqual(len(v.doc.get_ocgs()), 1)
        page = v.doc[0]
        # all of them in one content stream of the drawing's own
        mine = [x for x in page.get_contents()
                if v.doc.xref_get_key(x, drawing.STREAM_KEY)[0] == "int"]
        self.assertEqual(len(mine), 1)
        self.assertEqual(v.doc.xref_stream(mine[0]).count(b"BDC"), 1)


class ConvertToDrawing(Base):
    """A markup already on the page made into page drawing, looking as it did."""

    def markups(self, v):
        v.set_tool("polygon")
        A.set_tool_props("polygon", dict(A.tool_props("polygon"), fill="#80c0ff",
                                         stroke="#d00000", width=3.0))
        self.addCleanup(A.reset_tool_props, "polygon")
        v.apply_poly(0, "polygon", [P(80, 120), P(260, 140), P(170, 300)])
        v.set_tool("rect")
        v.apply_drag_tool(0, "rect", P(320, 120), P(520, 260), False)
        v.set_tool("line")
        v.apply_drag_tool(0, "line", P(80, 400), P(500, 480), False)
        v.set_tool("editobjects")
        return [an.xref for an in v.doc[0].annots()]

    def test_polygon_rectangle_and_line_keep_their_look(self):
        v = self.view()
        xrefs = self.markups(v)
        self.assertEqual(len(xrefs), 3)
        before = pixels(v.doc[0])
        content = po._contents(v.doc[0])
        v._set_selection(0, xrefs)
        self.assertEqual(len(v.convertible_selection()), 3)
        self.assertEqual(v.convert_to_drawing(), 3)
        page = v.doc[0]
        self.assertEqual(list(page.annots()), [])
        self.assertGreaterEqual(len(self.drawn(v)), 3)
        after = pixels(page)
        # (antialiasing at the edges aside: the same picture)
        self.assertLess(differing(before, after), 40)
        # restyled with Properties as any of the page's shapes
        poly = [it for it in self.drawn(v) if it["obj"].get("fill")][0]
        v.select_objects(0, [poly])
        self.assertEqual(v.object_style().get("fill"), "#80c0ff")
        # one undo step: the markups back, the page's content as it was
        v.undo()
        self.assertEqual(sorted(an.xref for an in v.doc[0].annots()), sorted(xrefs))
        self.assertEqual(po._contents(v.doc[0]), content)
        self.assertEqual(differing(before, pixels(v.doc[0])), 0)
        v.redo()
        self.assertEqual(list(v.doc[0].annots()), [])
        self.assertLess(differing(before, pixels(v.doc[0])), 40)

    def test_measurements_notes_and_highlights_stay_markups(self):
        v = self.view()
        v.set_tool("m_length")
        v.apply_drag_tool(0, "m_length", P(80, 400), P(300, 400), False)
        x = [an.xref for an in v.doc[0].annots()]
        v._set_selection(0, x)
        self.assertEqual(v.convertible_selection(), [])
        self.assertEqual(v.convert_to_drawing(), 0)
        self.assertEqual(len(list(v.doc[0].annots())), 1)

    def test_see_through_markup_keeps_its_look(self):
        v = self.view()
        v.set_tool("rect")
        A.set_tool_props("rect", dict(A.tool_props("rect"), fill="#00a000", opacity=0.5))
        self.addCleanup(A.reset_tool_props, "rect")
        v.apply_drag_tool(0, "rect", P(100, 30), P(400, 120), False)    # (over the blue line)
        before = pixels(v.doc[0])
        v._set_selection(0, [an.xref for an in v.doc[0].annots()])
        self.assertEqual(v.convert_to_drawing(), 1)
        self.assertLess(differing(before, pixels(v.doc[0]), level=12), 40)


class Tagged(Base):
    def test_a_tagged_pages_drawing_is_an_artifact(self):
        # (PDF/UA: lines and shapes added to a tagged page are marked as artifacts, as
        # tag_upkeep does for the page's other new drawing; the tags stay consistent)
        from kanzonas import autotag, tag_upkeep
        path = sheet()
        d = pymupdf.open(path)
        autotag.apply(d, autotag.make_plans(d), lang="en-US")
        d.saveIncr()
        d.close()
        v = self.view(path)
        self.assertEqual(tag_upkeep.problems(v.doc), [])
        self.draw(v, "d_arrow", (100, 300), (300, 400))
        v.set_tool("rect")
        v.apply_drag_tool(0, "rect", P(320, 300), P(500, 400), False)
        v._set_selection(0, [an.xref for an in v.doc[0].annots()])
        self.assertEqual(v.convert_to_drawing(), 1)
        self.assertEqual(tag_upkeep.problems(v.doc), [])
        got = self.drawn(v)
        self.assertEqual(len(got), 2)
        for it in got:
            self.assertIn(b"/Artifact BMC", it["obj"]["ctx"][0])
        # (marked around its own q ... Q: its arrowhead still read as one, Properties keeps it)
        heads = po.heads_of(v.content_objects(0).data, got[0]["obj"])
        self.assertEqual(heads[:3], ("none", "open", "none"))


class SaveAndOpen(Base):
    def test_saved_and_opened_again(self):
        v = self.view()
        self.draw(v, "d_polygon", [(100, 100), (300, 120), (200, 300)])
        self.draw(v, "d_arrow", (100, 400), (300, 450))
        v.set_tool("rect")
        v.apply_drag_tool(0, "rect", P(320, 120), P(520, 260), False)
        v._set_selection(0, [an.xref for an in v.doc[0].annots()])
        v.convert_to_drawing()
        shown = pixels(v.doc[0])
        out = os.path.join(tempfile.mkdtemp(), "saved.pdf")
        v.save(out)
        w = self.view(out)
        self.assertEqual([o["name"] for o in w.doc.get_ocgs().values()], [drawing.LAYER])
        self.assertEqual(len(self.drawn(w)), len(self.drawn(v)))
        self.assertEqual(differing(shown, pixels(w.doc[0])), 0)
        arrow = [it for it in self.drawn(w)
                 if po.heads_of(w.content_objects(0).data, it["obj"])]
        self.assertEqual(len(arrow), 1)
        # undo still works after the save, and drawing goes on in the file opened again
        v.undo()
        self.assertEqual(len(list(v.doc[0].annots())), 1)
        self.draw(w, "d_line", (50, 600), (500, 650))
        self.assertEqual(len(self.drawn(w)), len(self.drawn(v)) + 2)
        self.assertEqual(len(w.doc.get_ocgs()), 1)


class TurnedPages(Base):
    """Drawn with the mouse on a page turned 90, 180 and 270 degrees: the shape lands where
    the pointer went, on the page as shown."""

    def mouse(self, v, pts, double=False):
        w = v.pages[0]

        def at(xy):
            q = w.to_screen_pt(P(xy))
            return QPoint(round(q.x()), round(q.y()))
        if len(pts) == 2 and not double:
            QTest.mousePress(w, Qt.LeftButton, Qt.NoModifier, at(pts[0]))
            QTest.mouseMove(w, at(((pts[0][0] + pts[1][0]) / 2, (pts[0][1] + pts[1][1]) / 2)))
            QTest.mouseMove(w, at(pts[1]))
            QTest.mouseRelease(w, Qt.LeftButton, Qt.NoModifier, at(pts[1]), 300)
        else:
            for q in pts:
                QTest.mouseClick(w, Qt.LeftButton, Qt.NoModifier, at(q))
                APP.processEvents()
            QTest.mouseDClick(w, Qt.LeftButton, Qt.NoModifier, at(pts[-1]))
        APP.processEvents()

    def test_rotated_pages(self):
        tol = 1.5                       # (a screen pixel at 100%)
        for rot in (90, 180, 270):
            with self.subTest(rotation=rot):
                v = self.view(sheet(rot), show=True)
                v.set_tool("d_rect")
                self.mouse(v, [(150, 200), (350, 300)])
                v.set_tool("d_line")
                self.mouse(v, [(100, 500), (400, 600)])
                v.set_tool("d_polygon")
                self.mouse(v, [(300, 650), (450, 650), (380, 740)], double=True)
                got = self.drawn(v)
                self.assertEqual(len(got), 3, rot)
                rect, line, poly = got
                self.assertTrue(near(rect["rect"].tl, (150, 200), tol) and
                                near(rect["rect"].br, (350, 300), tol), (rot, rect["rect"]))
                ends = [q for ln in self.lines(v, line) for q in (ln[0], ln[-1])]
                self.assertTrue(any(near(q, (100, 500), tol) for q in ends), (rot, ends))
                self.assertTrue(any(near(q, (400, 600), tol) for q in ends), (rot, ends))
                flat = [q for ln in self.lines(v, poly) for q in ln]
                for q in ((300, 650), (450, 650), (380, 740)):
                    self.assertTrue(any(near(q, f, tol) for f in flat), (rot, q, flat))
                # drawn where it shows: the page as turned has the rectangle's corner there
                page = v.doc[0]
                shown = pixels(page)
                corner = P(150, 250) * page.rotation_matrix
                self.assertTrue(dark_near(shown, corner, 3), rot)
                # a markup converted on the turned page keeps its look
                v.set_tool("rect")
                v.apply_drag_tool(0, "rect", P(380, 100), P(520, 180), False)
                before = pixels(v.doc[0])
                v._set_selection(0, [an.xref for an in v.doc[0].annots()])
                self.assertEqual(v.convert_to_drawing(), 1)
                self.assertLess(differing(before, pixels(v.doc[0])), 40, rot)
                # undo, one step each
                for _k in range(5):         # (the markup drawn to convert is a step too)
                    v.undo()
                self.assertEqual(self.drawn(v), [])


class CadMode(Base):
    """In CAD mode the tools draw click, move, click, as the markup tools do there."""
    MODE = "cad"

    def test_click_move_click(self):
        DocumentView.click_click = True
        v = self.view(show=True)
        v.set_tool("d_line")
        w = v.pages[0]

        def at(xy):
            q = w.to_screen_pt(P(xy))
            return QPoint(round(q.x()), round(q.y()))
        QTest.mouseClick(w, Qt.LeftButton, Qt.NoModifier, at((100, 300)))
        APP.processEvents()
        QTest.mouseMove(w, at((200, 300)))
        QTest.mouseMove(w, at((300, 300)))
        APP.processEvents()
        self.assertEqual(self.drawn(v), [])            # (in progress)
        QTest.mouseClick(w, Qt.LeftButton, Qt.NoModifier, at((300, 300)))
        APP.processEvents()
        got = self.drawn(v)
        self.assertEqual(len(got), 1)
        self.assertTrue(near(got[0]["rect"].tl, (100, 300), 1.5) and
                        near(got[0]["rect"].br, (300, 300), 1.5), got[0]["rect"])


if __name__ == "__main__":
    unittest.main()
