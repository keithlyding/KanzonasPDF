"""1.6.1: CAD work on big sheets made quicker, with the same results.
A page's drawing is written deflated quickly (zlib) and undo steps leave out drawings an edit
replaced; the scan records each object's layer and clipping, so Copy doesn't read the whole
drawing again; after an edit the shapes left as they were are taken over; content_objects
finishes CAD mode's idle read; snap points come from MuPDF's plain numbers (the same points),
are kept for undo and made in idle time; printing draws each band from the pixels without
copying them; the spelling word list and the installed fonts load in idle time.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_speed_161_cad
"""
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

from kanzonas import page_objects as P  # noqa: E402
from kanzonas import snapping, spelling, text_edit  # noqa: E402
from kanzonas.document_view import DocumentView  # noqa: E402


def drawing(n=300, seed=1):
    """Content like a CAD export's: lines and curves with their own color and width, some
    in a layer (marked content), some under a clip, rectangles, a picture-less group of
    shapes in q ... Q with a matrix."""
    rnd = random.Random(seed)
    ops = []
    for i in range(n):
        x, y = rnd.uniform(20, 1100), rnd.uniform(20, 700)
        kind = i % 6
        if kind == 0:
            ops.append(b"%.2f %.2f m %.2f %.2f l %.2f w %.2f 0 0 RG S" %
                       (x, y, x + 40, y + 25, 0.2 + i % 5 / 10, i % 7 / 7))
        elif kind == 1:
            ops.append(b"%.2f %.2f m %.2f %.2f %.2f %.2f %.2f %.2f c S" %
                       (x, y, x + 10, y + 30, x + 30, y - 10, x + 40, y + 5))
        elif kind == 2:
            ops.append(b"%.2f %.2f %.2f %.2f re 0 0 1 rg f" % (x, y, 20, -15))
        elif kind == 3:
            ops.append(b"/OC /L%d BDC %.2f %.2f m %.2f %.2f l S EMC" % (i % 3, x, y, x + 30, y))
        elif kind == 4:
            ops.append(b"q 0 0 600 400 re W n %.2f %.2f m %.2f %.2f l S Q" % (x, y, x, y + 30))
        else:
            ops.append(b"q 1 0 0 1 5 5 cm %.2f %.2f m %.2f %.2f l %.2f %.2f l h S Q" %
                       (x, y, x + 20, y, x + 10, y + 15))
    return b"\n".join(ops)


def cad_page(doc, n=300, seed=1):
    pg = doc.new_page(width=1200, height=800)
    x = doc.get_new_xref()
    doc.update_object(x, "<<>>")
    doc.update_stream(x, drawing(n, seed))
    pg.set_contents(x)
    return pg


def same_objects(test, a, b):
    """a (worked out after edits) is what a fresh read b gives: every scan entry exactly,
    every item, and the outlines a has read."""
    test.assertEqual(len(a.found), len(b.found))
    for x, y in zip(a.found, b.found):
        test.assertEqual(set(x), set(y))
        for k in x:
            if k == "ctm":
                test.assertEqual(tuple(x[k]), tuple(y[k]))
            else:
                test.assertEqual(x[k], y[k], k)
    test.assertEqual(len(a.items), len(b.items))
    for x, y in zip(a.items, b.items):
        for k in ("n", "kind", "xref", "stroke", "fill", "width"):
            test.assertEqual(x.get(k), y.get(k), k)
        test.assertEqual(tuple(x["rect"]), tuple(y["rect"]))
        if "lines" in x:
            lb = b.lines(y)
            test.assertEqual(len(x["lines"]), len(lb))
            for l1, l2 in zip(x["lines"], lb):
                test.assertEqual(len(l1), len(l2))
                for p, q in zip(l1, l2):
                    test.assertLess(abs(p.x - q.x) + abs(p.y - q.y), 1e-3)


def partition(keys):
    ids = {}
    return [ids.setdefault(k, len(ids)) for k in keys]


class Written(unittest.TestCase):
    def test_the_drawing_is_written_deflated_and_reads_back_the_same(self):
        d = pymupdf.open()
        pg = cad_page(d)
        data = P._contents(pg)
        P._set_contents(pg, data + b"\n0 0 m 10 10 l S")
        x = pg.get_contents()[0]
        self.assertEqual(d.xref_get_key(x, "Filter"), ("name", "/FlateDecode"))
        self.assertLess(len(d.xref_stream_raw(x)), len(data) / 2)
        self.assertEqual(P._contents(pg), data + b"\n0 0 m 10 10 l S")

    def test_every_edit_leaves_it_deflated(self):
        d = pymupdf.open()
        pg = cad_page(d)
        objs = P.Objects(pg)
        shapes = [it["n"] for it in objs.items if it["kind"] == "shape"]
        m = pymupdf.Matrix(1, 0, 0, 1, 10, 5)
        for edit in (lambda o: P.transform(pg, shapes[:5], m, o),
                     lambda o: P.copies(pg, shapes[10:12], [m], o),
                     lambda o: P.block_copies(pg, shapes[20:22], [m, m * m], o),
                     lambda o: P.delete(pg, shapes[30:33], o)):
            objs = edit(objs)
            x = pg.get_contents()[0]
            self.assertEqual(d.xref_get_key(x, "Filter"), ("name", "/FlateDecode"))
            same_objects(self, objs, P.Objects(pg))

    def test_an_undo_step_leaves_out_what_nothing_uses(self):
        tmp = tempfile.mkdtemp()
        d = pymupdf.open()
        cad_page(d)
        path = os.path.join(tmp, "cad.pdf")
        d.save(path)
        v = DocumentView(path)
        self.addCleanup(v.close_doc)
        # a drawing replaced by an edit stays in the document until saved
        orphan = v.doc.get_new_xref()
        v.doc.update_object(orphan, "<<>>")
        v.doc.update_stream(orphan, os.urandom(300000), compress=False)
        page_xref = v.doc[0].xref
        snap = v._snapshot()
        self.assertLess(len(snap), 300000)
        back = pymupdf.open("pdf", snap)
        self.assertEqual(back[0].xref, page_xref)            # object numbers stay
        self.assertEqual(P._contents(back[0]), P._contents(v.doc[0]))


class Contexts(unittest.TestCase):
    def test_the_scan_knows_each_objects_layer_and_clip(self):
        data = drawing(400)
        found = P.scan(data)
        ref = P._contexts(data, [x["start"] for x in found])
        self.assertEqual(partition([x["ctx"] for x in found]),
                         partition([ref[x["start"]] for x in found]))
        self.assertGreater(len(set(x["ctx"] for x in found)), 3)

    def test_after_edits_it_is_what_a_fresh_read_gives(self):
        d = pymupdf.open()
        pg = cad_page(d, 200, seed=4)
        objs = P.Objects(pg)
        rnd = random.Random(7)
        for step in range(30):
            items = [it for it in objs.items if it["kind"] == "shape"]
            pick = sorted(it["n"] for it in rnd.sample(items, rnd.choice([1, 2, 6])))
            m = pymupdf.Matrix(1, 0, 0, 1, rnd.uniform(-30, 30), rnd.uniform(-30, 30))
            for it in rnd.sample(objs.items, 10):
                if it["kind"] == "shape":
                    objs.lines(it)
            kind = step % 5
            if kind == 0:
                new = P.transform(pg, pick, m, objs)
            elif kind == 1:
                new = P.copies(pg, pick, [m, pymupdf.Matrix(90) * m], objs)
            elif kind == 2:
                new = P.delete(pg, pick, objs)
            elif kind == 3:
                new = P.block_copies(pg, pick, [m], objs)
            else:
                st, parts, paint = P.subpaths(objs.data, objs.found[pick[0]])
                new = P.rewrite_path(pg, pick[0], st, [[[pymupdf.Point(1, 1),
                                                         pymupdf.Point(50, 60)]]], paint, objs)
            self.assertIsNotNone(new)
            fresh = P.Objects(pg)
            same_objects(self, new, fresh)
            data = P._contents(pg)
            ref = P._contexts(data, [x["start"] for x in fresh.found])
            self.assertEqual(partition([x["ctx"] for x in new.found]),
                             partition([ref[x["start"]] for x in fresh.found]))
            objs = new

    def test_copy_does_not_read_the_drawing_again(self):
        d = pymupdf.open()
        pg = cad_page(d, 3000)
        objs = P.Objects(pg)
        ns = [it["n"] for it in objs.items if it["kind"] == "shape"
              and it["obj"]["ctx"] == ((), ())][:500]
        with mock.patch.object(P, "_contexts", side_effect=AssertionError("read again")):
            t = time.perf_counter()
            new = P.copies(pg, ns, [pymupdf.Matrix(1, 0, 0, 1, 40, 0)], objs)
            took = time.perf_counter() - t
        self.assertLess(took, 10)                       # (generous: ~0.1 s here)
        same_objects(self, new, P.Objects(pg))

    def test_copies_read_once_are_read_right(self):
        inner = b"0 g 1 w q 2 0 0 2 5 5 cm 0 0 m 10 0 l S Q\n/Im1 Do\n1 0 0 RG 3 3 6 6 re S"
        heads = [b"\nq\n%.6f %.6f %.6f %.6f %.4f %.4f cm\n" % (1, 0.1 * k, 0, 1, 7 * k, -3 * k)
                 for k in range(5)]
        got = P._scan_copies(heads, inner)
        want = P.scan(b"".join(h + inner + b"\nQ\n" for h in heads))
        self.assertEqual(len(got), len(want))
        for a, b in zip(got, want):
            self.assertEqual({k: v for k, v in a.items() if k != "ctm"},
                             {k: v for k, v in b.items() if k != "ctm"})
            self.assertEqual(tuple(a["ctm"]), tuple(b["ctm"]))


class Rebuilt(unittest.TestCase):
    def test_shapes_left_alone_are_taken_over(self):
        d = pymupdf.open()
        pg = cad_page(d, 600)
        objs = P.Objects(pg)
        for it in objs.items:
            if it["kind"] == "shape":
                objs.lines(it)
        n = objs.items[300]["n"]
        new = P.transform(pg, [n], pymupdf.Matrix(1, 0, 0, 1, 3, 3), objs)
        same_objects(self, new, P.Objects(pg))
        old = {it["n"]: it for it in objs.items}
        kept = [it for it in new.items if it["n"] != n]
        # the same box object and outline: not worked out again
        self.assertTrue(all(it["rect"] is old[it["n"]]["rect"] for it in kept))
        self.assertTrue(all(it["lines"] is old[it["n"]]["lines"] for it in kept))
        # but each its own item (marks on the new ones don't touch the old)
        self.assertTrue(all(it is not old[it["n"]] for it in kept))


def _settle(seconds=0.0):
    end = time.perf_counter() + seconds
    while True:
        APP.processEvents()
        if time.perf_counter() >= end:
            return


class IdleReads(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        d = pymupdf.open()
        cad_page(d, 6000)
        self.path = os.path.join(self.tmp, "cad.pdf")
        d.save(self.path)
        self.v = DocumentView(self.path)
        self.addCleanup(self.v.close_doc)
        self.v._prep_timer = QTimer(self.v)
        self.v._prep_timer.setSingleShot(True)

    def test_content_objects_finishes_the_idle_read(self):
        v = self.v
        with mock.patch.object(DocumentView, "PREP_SLICE", 0.0):
            v._prepare_read(0)                           # one slice: far from done
        read = v._prep_read
        self.assertIsNotNone(read)
        self.assertNotIn(0, v._obj_cache)
        with mock.patch.object(P.Objects, "__init__", side_effect=AssertionError("again")):
            objs = v.content_objects(0)
        self.assertIs(objs, read["objs"])
        self.assertIsNone(v._prep_read)
        same_objects(self, objs, P.Objects(v.doc[0]))

    def test_snap_points_made_in_idle_time_are_the_ones_used(self):
        v = self.v
        with mock.patch.object(DocumentView, "snap_objects", True):
            for _ in range(500):
                v._prepare_snaps(0, time.monotonic() + 0.01)
                if v._snap_content.get(0):
                    break
            got = v._snap_content[0][0][1]
            with mock.patch.object(snapping, "content_index",
                                   side_effect=AssertionError("read again")):
                self.assertIs(v._content_snaps(0), got)
        fresh = snapping.content_index(v.doc[0])
        self.assertEqual({k: list(b) for k, b in got.buckets.items()},
                         {k: list(b) for k, b in fresh.buckets.items()})

    def test_undo_finds_the_snap_points_again(self):
        v = self.v
        before = v._content_snaps(0)
        objs = v.content_objects(0)
        v.modify(lambda: P.delete(v.doc[0], [objs.items[5]["n"]], objs), [0])
        after = v._content_snaps(0)
        self.assertIsNot(after, before)
        v.undo()
        with mock.patch.object(snapping, "content_index",
                               side_effect=AssertionError("read again")):
            self.assertIs(v._content_snaps(0), before)

    def test_a_same_length_change_is_seen(self):
        # (a nudge rewrites a wrapper's numbers: the drawing can keep its length)
        v = self.v
        page = v.doc[0]
        data = P._contents(page)
        i = data.index(b".")
        digit = b"1" if data[i + 1:i + 2] != b"1" else b"2"
        changed = data[:i + 1] + digit + data[i + 2:]
        P._set_contents(page, data)
        key = v._content_key(page)
        P._set_contents(page, changed)
        self.assertNotEqual(v._content_key(page), key)
        P._set_contents(page, data)
        self.assertEqual(v._content_key(page), key)


def old_content_index(page):
    """snapping.content_index as it was (Point objects from get_drawings)."""
    pts = []
    for path in page.get_drawings():
        for it in path["items"]:
            op = it[0]
            if op == "l":
                a, b = it[1], it[2]
                pts += [(a.x, a.y), (b.x, b.y), ((a.x + b.x) / 2, (a.y + b.y) / 2)]
            elif op == "c":
                pts += [(it[1].x, it[1].y), (it[4].x, it[4].y)]
            elif op == "re":
                r = it[1]
                pts += [(q.x, q.y) for q in (r.tl, r.tr, r.bl, r.br)]
            elif op == "qu":
                q = it[1]
                pts += [(p.x, p.y) for p in (q.ul, q.ur, q.ll, q.lr)]
    idx = snapping.PointIndex()
    for x, y in pts:
        idx.add(x, y)
    return idx


class Snapping(unittest.TestCase):
    def check(self, page):
        old = old_content_index(page)
        new = snapping.content_index(page)
        self.assertEqual(set(old.buckets), set(new.buckets))
        for k, b in old.buckets.items():
            self.assertEqual([v for x, y, _t in b for v in (x, y)], list(new.buckets[k]))
        rnd = random.Random(3)
        for _ in range(1500):
            q = pymupdf.Point(rnd.uniform(-10, 1210), rnd.uniform(-10, 810))
            for tol in (2, 9, 40):
                a, b = old.nearest(q, tol), new.nearest(q, tol)
                self.assertEqual(None if a is None else (a.x, a.y),
                                 None if b is None else (b.x, b.y))

    def test_the_same_points_as_before(self):
        d = pymupdf.open()
        self.check(cad_page(d, 500))
        pg = d.new_page(width=600, height=400)
        sh = pg.new_shape()
        sh.draw_rect(pymupdf.Rect(50, 50, 200, 120))
        sh.draw_quad(pymupdf.Rect(300, 100, 400, 160).quad.transform(
            pymupdf.Matrix(1, 0, 0, 1, -350, -130) * pymupdf.Matrix(30) *
            pymupdf.Matrix(1, 0, 0, 1, 350, 130)))
        sh.draw_bezier((10, 300), (60, 250), (120, 380), (200, 300))
        sh.draw_circle((450, 300), 40)
        sh.finish(color=(0, 0, 0), fill=(1, 0, 0))
        sh.commit()
        pg.set_rotation(90)
        self.check(pg)

    def test_in_slices(self):
        d = pymupdf.open()
        pg = cad_page(d, 500)
        steps = list(snapping.content_index_steps(pg, step=50))
        self.assertGreater(len(steps), 5)
        self.assertTrue(all(s is None for s in steps[:-1]))
        self.assertEqual(len(steps[-1]), len(snapping.content_index(pg)))


class Printing(unittest.TestCase):
    def test_bands_are_drawn_from_the_pixels_without_a_copy(self):
        from PySide6.QtGui import QPainter
        from PySide6.QtPrintSupport import QPrinter
        from kanzonas.print_dialog import PrintDialog
        tmp = tempfile.mkdtemp()
        d = pymupdf.open()
        pg = d.new_page()
        pg.draw_rect(pymupdf.Rect(0, 0, 100, 100), color=(1, 0, 0), fill=(1, 0, 0))
        p = os.path.join(tmp, "p.pdf")
        d.save(p)
        v = DocumentView(p)
        self.addCleanup(v.close_doc)
        dlg = PrintDialog(None, v)
        seen = []
        real = QPainter.drawImage

        def spy(painter, *a):
            img = a[-1]
            seen.append((img.pixelColor(2, 2).name(), img.pixelColor(img.width() - 2,
                                                                     img.height() - 2).name()))
            return real(painter, *a)
        pr = dlg.printer
        pr.setOutputFormat(QPrinter.PdfFormat)
        pr.setOutputFileName(os.path.join(tmp, "printed.pdf"))
        pr.setResolution(150)
        copied = property(lambda pm: self.fail("the band's pixels were copied"))
        with mock.patch.object(QPainter, "drawImage", spy), \
                mock.patch.object(pymupdf.Pixmap, "samples", copied):
            self.assertTrue(dlg.print_to(pr, [0]))
        self.assertEqual(seen[0], ("#ff0000", "#ffffff"))     # red corner, white page


class FirstUse(unittest.TestCase):
    def test_fonts_scanned_in_idle_time_are_the_same(self):
        saved = text_edit._SYSTEM_FONTS
        self.addCleanup(setattr, text_edit, "_SYSTEM_FONTS", saved)
        text_edit._SYSTEM_FONTS = None
        whole = text_edit._system_fonts()
        text_edit._SYSTEM_FONTS = None
        text_edit.system_fonts_soon()
        end = time.perf_counter() + 30
        while text_edit._SYSTEM_FONTS is None and time.perf_counter() < end:
            APP.processEvents()
        self.assertEqual(text_edit._SYSTEM_FONTS, whole)
        self.assertEqual(list(text_edit._SYSTEM_FONTS), list(whole))
        # one under way is finished by the first one to need it
        text_edit._SYSTEM_FONTS = None
        text_edit.system_fonts_soon()
        self.assertEqual(text_edit._system_fonts(), whole)
        self.assertIsNone(text_edit._FONT_SCAN)
        _settle(0.05)                                   # (its timer finds nothing to do)
        self.assertEqual(text_edit._SYSTEM_FONTS, whole)

    def test_the_word_list_loads_in_idle_time(self):
        saved = dict(spelling._state)
        self.addCleanup(spelling._state.update, saved)
        spelling._state["enabled"] = True
        spelling._state["checker"] = None
        spelling.load_soon(0)
        self.assertIsNone(spelling._state["checker"])           # (not right away)
        _settle(0.05)
        self.assertIsNotNone(spelling._state["checker"])
        spelling._state["enabled"] = False
        spelling._state["checker"] = None
        spelling.load_soon(0)
        _settle(0.05)
        self.assertIsNone(spelling._state["checker"])           # spell checking off: not loaded


if __name__ == "__main__":
    unittest.main()
