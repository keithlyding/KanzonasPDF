"""The page's own pictures and shapes copied, cut and pasted with Edit objects (Ctrl+C, Ctrl+X,
Ctrl+V), onto another page, a page turned another way and another open document, looking the
same as where they were (compared pixel for pixel): stroke and fill colors, widths and
dashes, transparency, a picture with a soft mask, an inline picture, a picture in its own
clip ("Print to PDF" strips), a line under a clip it shares, a pattern fill, a layer. Pasted
objects are page content again (Edit objects moves them); a picture is stored once however
often it's pasted; each step is one undo step. CAD mode's Move and Copy, and a selection
dragged with the mouse, take the selection to another page.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_object_clipboard
"""
import os
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

from kanzonas import clip, main_window, page_objects  # noqa: E402
from kanzonas.page_objects import Box  # noqa: E402
from tests.test_undo_journal import canon  # noqa: E402

AREA = pymupdf.Rect(40, 40, 560, 700)          # where the drawing is (as shown)


def pump(n=5):
    for _ in range(n):
        APP.processEvents()


def picture(w, h, rgba):
    pm = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, w, h), len(rgba) == 4)
    pm.set_rect(pm.irect, rgba)
    for x in range(0, w, 3):                    # (not one color: a real picture)
        pm.set_pixel(x, x % h, (0, 0, 0) + ((255,) if len(rgba) == 4 else ()))
    return pm


def drawing(path, pages=3, turned=2):
    """Page 1: shapes, pictures, clips, a pattern and a layer; pages 2 and 3 blank, page
    `turned` a landscape sheet shown turned a quarter (upright, as page 1)."""
    d = pymupdf.open()
    p = d.new_page()
    p.draw_rect((60, 60, 200, 140), color=(0, 0, 1), fill=(1, 1, 0), width=3,
                dashes="[6 3] 0", fill_opacity=0.5)
    p.draw_circle((300, 110), 50, color=(1, 0, 0), width=2.5)
    p.insert_image((60, 180, 200, 280), pixmap=picture(40, 30, (200, 30, 30, 120)))
    ocg = d.add_ocg("Walls", on=True)
    p.draw_line((60, 320), (300, 360), color=(0, 0.5, 0), width=4, oc=ocg)
    page_objects._own_resources(p)
    sh = d.get_new_xref()
    d.update_object(sh, "<</ShadingType 2/ColorSpace/DeviceRGB/Coords[0 0 120 0]/Function"
                        "<</FunctionType 2/Domain[0 1]/C0[1 0 0]/C1[0 0 1]/N 1>>"
                        "/Extend[true true]>>")
    pat = d.get_new_xref()
    d.update_object(pat, "<</PatternType 2/Shading %d 0 R/Matrix[1 0 0 1 340 420]>>" % sh)
    page_objects._set_resource(d, p.xref, "Pattern", "P0", "%d 0 R" % pat)
    x = d.get_new_xref()
    d.update_object(x, "<<>>")
    inline = b"".join(bytes((40 * i, 200 - 40 * i, 90)) for i in range(4))
    d.update_stream(x, b"q /Pattern cs /P0 scn 340 360 120 60 re f Q\n"
                       # a picture strip in its own clip, as Print to PDF writes them
                       b"q 380 200 100 50 re W n 0 0 1 rg 360 180 160 120 re f Q\n"
                       # two lines under one clip (it isn't either one's own)
                       b"q 60 432 220 30 re W n 1 0 1 RG 3 w 50 422 m 300 472 l S "
                       b"0 1 1 RG 50 472 m 300 422 l S Q\n"
                       b"q 60 0 0 40 400 560 cm BI /W 2 /H 2 /CS /RGB /BPC 8 ID " + inline +
                       b" EI Q\n", compress=False)
    old = p.get_contents()
    d.xref_set_key(p.xref, "Contents", "[%s]" % " ".join("%d 0 R" % c for c in old + [x]))
    for k in range(1, pages):
        if k == turned:
            q = d.new_page(width=842, height=595)
            q.set_rotation(90)
        else:
            d.new_page()
    d.save(path)
    d.close()
    return path


def shown(doc, index, rect):
    """The page as shown in rect (a fresh copy of the document, drawn once)."""
    with pymupdf.open("pdf", doc.tobytes()) as d:
        return d[index].get_pixmap(dpi=72, clip=rect).samples


def images(doc):
    return [x for x in range(1, doc.xref_length())
            if doc.xref_get_key(x, "Subtype")[1] == "/Image"]


class Fixture(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = drawing(os.path.join(self.dir, "drawing.pdf"))
        self.w = w = main_window.MainWindow()
        self.addCleanup(self.close)
        w.resize(1300, 950)
        w.show()
        pump()
        w.open_file(self.path)
        pump()
        self.v = w.view()
        self.v.set_zoom(1.0)            # (a screen pixel a point: the pointer at whole points)
        pump()

    def close(self):
        for v in self.w._views():
            v.dirty = False
        self.w._close_confirmed = True
        self.w.close()
        pump()

    def select_all_objects(self, index=0):
        """Edit objects: a box dragged around the drawing with the mouse."""
        self.w.set_tool("editobjects")
        pump()
        pw = self.v.pages[index]
        a = pw.to_screen_pt(pymupdf.Point(AREA.tl) * self.v.doc[index].derotation_matrix)
        b = pw.to_screen_pt(pymupdf.Point(AREA.br) * self.v.doc[index].derotation_matrix)
        QTest.mousePress(pw, Qt.LeftButton, Qt.NoModifier, a.toPoint())
        QTest.mouseMove(pw, ((a + b) / 2).toPoint())
        QTest.mouseMove(pw, b.toPoint())
        QTest.mouseRelease(pw, Qt.LeftButton, Qt.NoModifier, b.toPoint())
        pump()
        self.assertTrue(self.v.obj_sel and len(self.v.obj_sel[1]) >= 9,
                        self.v.obj_sel and [it["kind"] for it in self.v.obj_sel[1]])

    def keys(self, key, index=0):
        self.v.setFocus()
        QTest.keyClick(self.v.pages[index], key, Qt.ControlModifier)
        pump()

    def mouse_to(self, shown_pt, index):
        """The pointer over page index at shown_pt (a point as the page is shown). (Paste
        goes where the pointer is: QCursor.pos(), which the offscreen platform only roughly
        keeps when other windows came and went, so the point is given to Paste too.)"""
        self.v.goto_page(index)
        pump()
        pw = self.v.pages[index]
        z = self.v.zoom
        QTest.mouseMove(pw, QPoint(round(shown_pt[0] * z), round(shown_pt[1] * z)))
        pump()
        at = pymupdf.Point(round(shown_pt[0] * z) / z, round(shown_pt[1] * z) / z)
        target = (index, at * self.v.doc[index].derotation_matrix)
        self.v.paste_target = lambda: target

    def corner(self):
        """Where the copied things' top left corner was, as page 1 is shown."""
        return self.v._payload_box(clip.get()[1]).tl


class CopyAndPaste(Fixture):
    def paste_same_place(self, index):
        tl = self.corner()
        self.mouse_to((tl.x, tl.y), index)
        before = canon(self.v.doc)
        self.keys(Qt.Key_V, index)
        after = canon(self.v.doc)
        self.assertNotEqual(after, before)
        return before, after, pymupdf.Point(round(tl.x * self.v.zoom) / self.v.zoom,
                                            round(tl.y * self.v.zoom) / self.v.zoom) - tl

    def test_another_page_looks_the_same(self):
        self.select_all_objects()
        self.keys(Qt.Key_C)
        self.assertEqual(clip.get()[0], "pagecontent")
        self.assertFalse(QApplication.clipboard().image().isNull())   # (for other programs)
        before, after, off = self.paste_same_place(1)
        src = shown(self.v.doc, 0, AREA)
        self.assertEqual(shown(self.v.doc, 1, AREA + (off.x, off.y, off.x, off.y)), src)
        # page content again: Edit objects selects the pasted objects, and moves them
        sel = self.v.obj_sel
        self.assertEqual(sel[0], 1)
        self.assertGreaterEqual(len(sel[1]), 9)
        self.assertTrue(all(it["kind"] in ("shape", "picture") for it in sel[1]))
        self.assertEqual(list(self.v.doc[1].annots()), [])
        self.v.undo()
        pump()
        self.assertEqual(canon(self.v.doc), before)
        self.v.redo()
        pump()
        self.assertEqual(canon(self.v.doc), after)
        self.v.select_objects(1, sel[1])
        r = self.v.selected_objects_rect()
        self.v.move_objects(r + (0, 30, 0, 30))
        pump()
        # (the shapes and pictures above the pattern fill: Edit objects moving a shape filled
        # with a pattern leaves the pattern where it is, as before)
        top = pymupdf.Rect(40, 40, 360, 300)
        self.assertEqual(shown(self.v.doc, 1, top + (off.x, off.y + 30, off.x, off.y + 30)),
                         shown(self.v.doc, 0, top))

    def test_a_turned_page_shows_it_the_same(self):
        self.select_all_objects()
        self.keys(Qt.Key_C)
        _b, _a, off = self.paste_same_place(2)
        self.assertEqual(self.v.doc[2].rotation, 90)
        self.assertEqual(shown(self.v.doc, 2, AREA + (off.x, off.y, off.x, off.y)),
                         shown(self.v.doc, 0, AREA))

    def test_another_document_and_each_picture_once(self):
        self.select_all_objects()
        self.keys(Qt.Key_C)
        src = shown(self.v.doc, 0, AREA)
        tl = self.corner()
        d = pymupdf.open()
        d.new_page()
        other = os.path.join(self.dir, "other.pdf")
        d.save(other)
        d.close()
        self.w.open_file(other)
        pump()
        self.v = self.w.view()
        self.v.set_zoom(1.0)
        self.w.set_tool("editobjects")
        self.mouse_to((tl.x, tl.y), 0)
        self.keys(Qt.Key_V)
        z = self.v.zoom
        off = pymupdf.Point(round(tl.x * z) / z, round(tl.y * z) / z) - tl
        self.assertEqual(shown(self.v.doc, 0, AREA + (off.x, off.y, off.x, off.y)), src)
        pics = images(self.v.doc)
        self.assertTrue(pics)
        self.mouse_to((tl.x + 5, tl.y + 300), 0)
        before = canon(self.v.doc)
        self.keys(Qt.Key_V)
        self.assertEqual(images(self.v.doc), pics)          # (the same pictures, used again)
        # the layer isn't in this document: the content shows, on no layer
        self.assertNotIn(b"/OC", self.v.doc[0].read_contents())
        self.v.undo()
        pump()
        self.assertEqual(canon(self.v.doc), before)
        self.v.undo()
        pump()
        self.mouse_to((tl.x, tl.y), 0)
        self.keys(Qt.Key_V)                 # (after the undo the copies are made again)
        self.assertEqual(shown(self.v.doc, 0, AREA + (off.x, off.y, off.x, off.y)), src)

    def test_the_same_document_keeps_the_layer_and_the_pictures(self):
        self.select_all_objects()
        pics = images(self.v.doc)
        self.keys(Qt.Key_C)
        self.paste_same_place(1)
        self.assertEqual(images(self.v.doc), pics)
        self.assertIn(b"/OC", self.v.doc[1].read_contents())

    def test_cut_takes_it_off_in_one_step(self):
        self.select_all_objects()
        src = shown(self.v.doc, 0, AREA)
        before = canon(self.v.doc)
        self.keys(Qt.Key_X)
        self.assertEqual(page_objects.Objects(self.v.doc[0]).items, [])
        self.v.undo()
        pump()
        self.assertEqual(canon(self.v.doc), before)
        self.v.redo()
        pump()
        _b, _a, off = self.paste_same_place(1)
        self.assertEqual(shown(self.v.doc, 1, AREA + (off.x, off.y, off.x, off.y)), src)

    def test_text_comes_along(self):
        page = self.v.doc[0]
        page.insert_text((60, 650), "A note with the drawing", fontsize=14)
        del page
        self.v._clear_caches()
        self.select_all_objects()
        self.v.select_objects(0, self.v.obj_sel[1] + self.v.text_objects(0))
        self.assertTrue(any(it["kind"] == "text" for it in self.v.obj_sel[1]))
        self.keys(Qt.Key_C)
        self.assertIn("A note", QApplication.clipboard().text())
        _b, _a, off = self.paste_same_place(1)
        self.assertIn("A note with the drawing", self.v.doc[1].get_text())
        self.assertEqual(shown(self.v.doc, 1, AREA + (off.x, off.y, off.x, off.y)),
                         shown(self.v.doc, 0, AREA))


class AcrossPages(Fixture):
    def cad(self):
        from kanzonas import cad_select, mouse_modes
        old = {k: self.w.settings.value(k) for k in ("mouse_mode", "mouse_before_cad")}

        def back():
            for k, v in old.items():
                self.w.settings.setValue(k, v) if v is not None else self.w.settings.remove(k)
            mouse_modes.apply(self.w.settings)
        self.addCleanup(back)
        self.w.set_mouse_mode("cad")
        pump()
        cad_select.pick(self.v.pages[0], Box(pymupdf.Rect(AREA)), False, False)
        self.line = self.w.cad_command_line()

    def type(self, text):
        self.line.edit.setText(text)
        self.line.run()
        pump()

    def test_cad_move_to_another_page(self):
        self.cad()
        src = shown(self.v.doc, 0, AREA)
        before = canon(self.v.doc)
        self.type("m")
        cmd = self.v._cad_cmd
        cmd.click(0, pymupdf.Point(60, 60))
        # the outlines follow the pointer onto the other page
        cmd.move(1, pymupdf.Point(80, 100))
        self.v.pages[1].grab()
        cmd.click(1, pymupdf.Point(80, 100))
        self.assertIsNone(self.v._cad_cmd)
        self.assertEqual(page_objects.Objects(self.v.doc[0]).items, [])
        self.assertEqual(shown(self.v.doc, 1, AREA + (20, 40, 20, 40)), src)
        self.assertEqual(self.v.obj_sel[0], 1)
        self.v.undo()
        pump()
        self.assertEqual(canon(self.v.doc), before)

    def test_cad_copy_to_a_turned_page_and_on(self):
        self.cad()
        src = shown(self.v.doc, 0, AREA)
        self.type("co")
        cmd = self.v._cad_cmd
        cmd.click(0, pymupdf.Point(60, 60))
        turned = self.v.doc[2]
        cmd.click(2, pymupdf.Point(60, 60) * turned.derotation_matrix)
        cmd.click(1, pymupdf.Point(60, 60))
        self.assertEqual(cmd.made, 2)
        self.type("")
        self.assertEqual(shown(self.v.doc, 2, AREA), src)
        self.assertEqual(shown(self.v.doc, 1, AREA), src)
        self.assertEqual(shown(self.v.doc, 0, AREA), src)       # (the originals stay)

    def test_rotate_says_it_works_on_one_page(self):
        self.cad()
        self.type("ro")
        cmd = self.v._cad_cmd
        cmd.click(0, pymupdf.Point(100, 100))
        got = []
        self.v.statusMessage.connect(got.append)
        cmd.click(1, pymupdf.Point(100, 100))
        self.assertTrue(any("one page" in t and "page 1" in t for t in got), got)
        cmd.cancel()

    def test_a_selection_dragged_onto_another_page(self):
        self.w.set_tool("editobjects")
        pump()
        objs = self.v.content_objects(0)
        circle = next(it for it in objs.items if it["kind"] == "shape" and
                      abs(it["rect"].x0 - 250) < 1)
        self.v.select_objects(0, [circle])
        src = shown(self.v.doc, 0, pymupdf.Rect(240, 50, 360, 170))
        p0, p1 = self.v.pages[0], self.v.pages[1]
        start = p0.to_screen_pt(pymupdf.Point(335.36, 74.64)).toPoint()   # (on its line)
        end = p0.mapFromGlobal(p1.mapToGlobal(QPoint(start.x(), start.y())))
        QTest.mousePress(p0, Qt.LeftButton, Qt.NoModifier, start)
        QTest.mouseMove(p0, start + QPoint(5, 5))
        QTest.mouseMove(p0, end)
        self.assertEqual(getattr(self.v, "_drop_ghost", (None,))[0], 1)   # shown there
        QTest.mouseRelease(p0, Qt.LeftButton, Qt.NoModifier, end)
        pump()
        self.assertEqual(len(page_objects.Objects(self.v.doc[0]).items), len(objs.items) - 1)
        got = shown(self.v.doc, 1, pymupdf.Rect(240, 50, 360, 170))
        # (MuPDF draws a page holding transparency a level apart along edges: here the circle
        # is alone on its new page)
        self.assertEqual(len(got), len(src))
        self.assertLessEqual(max(abs(a - b) for a, b in zip(got, src)), 2)


if __name__ == "__main__":
    unittest.main()
