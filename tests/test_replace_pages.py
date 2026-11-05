"""Pages > Replace pages: a sheet's drawing swapped for a new revision's, by page numbers or
matched by sheet number, keeping the page object and everything on it or pointing at it
(markups, links, form fields, bookmarks, named destinations); markups kept in place or scaled
to a new size, on rotated pages too; one undo step that gives back exactly the document from
before; the new file left as it was; saved and opened again.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_replace_pages
"""
import hashlib
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf as F  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import annotations, links, measure, replace_pages  # noqa: E402
from kanzonas.document_view import DocumentView  # noqa: E402
from tests.battery_random import canon  # noqa: E402

RED = (1, 0, 0)


def sheet(doc, number, label, size=(792, 612), rotate=0, at=None):
    """A sheet: its label big at the top left, a title block with its sheet number at the
    bottom right (as displayed), a frame. rotate: the page's /Rotate, with the media box
    turned so the sheet shows the same way round (landscape) whatever it is."""
    w, h = size
    page = doc.new_page(width=w if rotate in (0, 180) else h,
                        height=h if rotate in (0, 180) else w)
    page.set_rotation(rotate)
    m = page.derotation_matrix
    page.draw_rect(F.Rect(10, 10, w - 10, h - 10) * m, color=(0, 0, 0), width=1)
    page.insert_text(F.Point(at or (60, 80)) * m, label, fontsize=24, rotate=rotate)
    page.insert_text(F.Point(w - 160, h - 30) * m, "SHEET NO: " + number, fontsize=10,
                     rotate=rotate)
    return page


def make(path, sheets, **kw):
    d = F.open()
    for number, label in sheets:
        sheet(d, number, label, **kw)
    d.save(path)
    d.close()
    return path


def shown(page, rect):
    """A rect in unrotated page coordinates as the page shows it."""
    return (F.Rect(rect) * page.rotation_matrix).normalize()


def near(a, b, tol=1.0):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


class ReplacePages(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(mock.patch.stopall)
        self.info = mock.patch.object(QMessageBox, "information", return_value=None).start()
        mock.patch.object(QMessageBox, "warning", side_effect=AssertionError("edit failed")
                          ).start()
        self.views, self.docs = [], []
        self.addCleanup(lambda: [v.close_doc() for v in self.views])
        self.addCleanup(lambda: [d.close() for d in self.docs])

    def view(self, sheets=(("A-101", "OLD 1"), ("A-102", "OLD 2"), ("A-103", "OLD 3")),
             **kw):
        path = make(os.path.join(self.tmp, "set.pdf"), sheets, **kw)
        v = DocumentView(path)
        self.views.append(v)
        return v

    def new_file(self, sheets, name="rev.pdf", **kw):
        path = make(os.path.join(self.tmp, name), sheets, **kw)
        src = F.open(path)
        self.docs.append(src)
        return path, src

    def rect_markup(self, v, index, rect):
        props = dict(v.tool_props("rect"), stroke="#ff0000", width=3)
        return v._create(index, {"kind": "rect", "rect": F.Rect(rect), "props": props})

    def labels(self, v):
        return [v.doc[i].get_text().split("\n")[0] for i in range(v.doc.page_count)]

    def markup_rects(self, page):
        return [F.Rect(a.rect) for a in page.annots(types=[F.PDF_ANNOT_SQUARE])]

    # ---- which pages ------------------------------------------------------------------
    def test_pairs_by_page_numbers(self):
        self.assertEqual(replace_pages.pairs_by_numbers("2-3", "1-2", 3, 4), [(1, 0), (2, 1)])
        self.assertEqual(replace_pages.pairs_by_numbers("3, 1", "4,2", 3, 4), [(2, 3), (0, 1)])
        for here, new in (("1-2", "1"), ("1-5", "1-5"), ("", "1"), ("x", "1")):
            with self.assertRaises(ValueError):
                replace_pages.pairs_by_numbers(here, new, 3, 4)

    def test_by_page_numbers_keeps_the_pages_and_everything_on_them(self):
        v = self.view()
        xrefs = [v.doc.page_xref(i) for i in range(3)]
        mk = self.rect_markup(v, 1, (300, 200, 400, 260))
        # a link from page 1 to page 2, a bookmark and a named destination to page 2, a field
        v.modify(lambda: v.doc[0].insert_link({"kind": F.LINK_GOTO, "page": 1,
                                               "from": F.Rect(500, 100, 560, 120)}))
        v.modify(lambda: v.doc.set_toc([[1, "Second", 2]]))

        def dest():
            names = v.doc.get_new_xref()
            v.doc.update_object(names, "<</Names[(detail) [%d 0 R /XYZ 0 600 0]]>>" % xrefs[1])
            v.doc.xref_set_key(v.doc.pdf_catalog(), "Names", "<</Dests %d 0 R>>" % names)
        v.modify(dest)

        def field():
            w = F.Widget()
            w.field_name, w.field_type = "checked_by", F.PDF_WIDGET_TYPE_TEXT
            w.rect = F.Rect(300, 400, 450, 420)
            v.doc[1].add_widget(w)
        v.modify(field)
        _p, src = self.new_file([("A-102", "NEW 2"), ("A-103", "NEW 3")])
        report = v.replace_pages(src, replace_pages.pairs_by_numbers("2-3", "1-2", 3, 2))
        self.assertEqual(report["pages"], 2)
        self.assertEqual(self.labels(v), ["OLD 1", "NEW 2", "NEW 3"])
        self.assertEqual([v.doc.page_xref(i) for i in range(3)], xrefs)
        page = v.doc[1]
        self.assertEqual([a.xref for a in page.annots()], [mk])
        self.assertTrue(near(self.markup_rects(page)[0], (298.5, 198.5, 401.5, 261.5)))
        self.assertEqual([w.field_name for w in page.widgets()], ["checked_by"])
        self.assertEqual([ln["page"] for ln in v.doc[0].get_links()], [1])
        self.assertEqual(v.doc.get_toc()[0][2], 2)
        self.assertEqual(v.doc.resolve_names()["detail"]["page"], 1)
        self.assertEqual(len(v.pages), 3)

    def test_matched_by_sheet_number(self):
        v = self.view()
        _p, src = self.new_file([("A-104", "NEW 4"), ("A-103", "NEW 3"), ("A101", "NEW 1")])
        match = replace_pages.match_sheets(v.doc, src)
        self.assertEqual(match["pairs"], {0: 2, 2: 1})
        self.assertEqual(match["new"][0]["number"], "A-104")
        v.replace_pages(src, sorted(match["pairs"].items()))
        self.assertEqual(self.labels(v), ["NEW 1", "OLD 2", "NEW 3"])

    def test_the_dialog_matches_lists_and_takes_corrections(self):
        from kanzonas.replace_pages_ui import ReplacePagesDialog
        v = self.view()
        _p, src = self.new_file([("A-104", "NEW 4"), ("A-103", "NEW 3"), ("A101", "NEW 1")],
                                size=(396, 306))
        dlg = ReplacePagesDialog(None, v.doc, src, "rev.pdf")
        self.addCleanup(dlg.deleteLater)
        self.assertEqual(dlg.pairs(), [(0, 0), (1, 1), (2, 2)])
        dlg.by_sheets.setChecked(True)
        self.assertEqual(dlg.pairs(), [(0, 2), (2, 1)])
        self.assertIn("A-104", dlg.unmatched.text())
        self.assertTrue(dlg.size_box.isEnabled())       # (the new sheets are half size)
        dlg.table.item(1, 2).setText("1")               # A-102 replaced by the new page 1
        self.assertEqual(dlg.pairs(), [(0, 2), (1, 0), (2, 1)])
        self.assertEqual(dlg.table.item(1, 3).text(), "A-104")
        self.assertNotIn("A-104", dlg.unmatched.text())
        dlg.table.item(0, 2).setText("")                # A-101 left as it is
        self.assertEqual(dlg.pairs(), [(1, 0), (2, 1)])
        dlg.table.item(0, 2).setText("9")
        with self.assertRaises(ValueError):
            dlg.pairs()
        self.assertFalse(dlg.ok.isEnabled())

    # ---- markups on a page of another size or turn ---------------------------------------
    def test_markups_scaled_to_a_smaller_sheet(self):
        v = self.view()
        mk = self.rect_markup(v, 0, (300, 200, 400, 260))
        v.modify(lambda: measure.set_scale(v.doc[0], 0.01, "ft", "1:100"))
        v.modify(lambda: v.doc[0].add_text_annot((500, 400), "a note").update())
        note = [F.Rect(a.rect) for a in v.doc[0].annots(types=[F.PDF_ANNOT_TEXT])][0]
        _p, src = self.new_file([("A-101", "NEW 1")], size=(396, 306))
        v.replace_pages(src, [(0, 0)], scale=True)
        page = v.doc[0]
        # (a note's icon keeps its size; its middle goes where the sheet's point went)
        now = [F.Rect(a.rect) for a in page.annots(types=[F.PDF_ANNOT_TEXT])][0]
        self.assertAlmostEqual(now.width, note.width, 2)
        self.assertAlmostEqual(now.height, note.height, 2)
        self.assertAlmostEqual((now.x0 + now.x1) / 2, (note.x0 + note.x1) / 4, 2)
        self.assertAlmostEqual((now.y0 + now.y1) / 2, (note.y0 + note.y1) / 4, 2)
        self.assertTrue(near(page.rect, (0, 0, 396, 306)))
        model = annotations.read(page.load_annot(mk))
        self.assertTrue(near(model["rect"], (150, 100, 200, 130), 0.01), model["rect"])
        self.assertTrue(near(self.markup_rects(page)[0], (149.5, 99.5, 200.5, 130.5), 0.01),
                        self.markup_rects(page))
        self.assertAlmostEqual(measure.get_scale(page)[0], 0.02)

    def test_markups_kept_in_place_on_another_size(self):
        v = self.view()
        mk = self.rect_markup(v, 0, (300, 200, 400, 260))
        _p, src = self.new_file([("A-101", "NEW 1")], size=(1224, 792))
        v.replace_pages(src, [(0, 0)], scale=False)
        page = v.doc[0]
        self.assertTrue(near(page.rect, (0, 0, 1224, 792)))
        model = annotations.read(page.load_annot(mk))
        self.assertTrue(near(model["rect"], (300, 200, 400, 260), 0.01), model["rect"])

    def test_rotated_new_drawing_keeps_markups_where_they_show(self):
        """The old sheet is a landscape page; the new one a portrait page turned 90 degrees
        (the same sheet as displayed): markups stay at the same spot on screen and look the
        same."""
        v = self.view()
        mk = self.rect_markup(v, 0, (300, 200, 400, 260))
        before = shown(v.doc[0], self.markup_rects(v.doc[0])[0])
        _p, src = self.new_file([("A-101", "NEW 1")], rotate=90)
        v.replace_pages(src, [(0, 0)])
        page = v.doc[0]
        self.assertEqual(page.rotation, 90)
        self.assertEqual(page.get_text().split("\n")[0], "NEW 1")
        self.assertTrue(near(shown(page, self.markup_rects(page)[0]), before, 0.01))
        # drawn the same way: the red border where it was on screen, white inside
        pix = page.get_pixmap(annots=True)
        self.assertEqual(pix.pixel(350, 201)[:3], (255, 0, 0))
        self.assertEqual(pix.pixel(301, 230)[:3], (255, 0, 0))
        self.assertEqual(pix.pixel(350, 230)[:3], (255, 255, 255))
        # and KanzonasPDF reads it as the same rectangle on screen
        model = annotations.read(page.load_annot(mk))
        self.assertTrue(near(shown(page, model["rect"]), (300, 200, 400, 260), 0.01))

    def test_rotated_old_page_replaced_by_an_upright_one(self):
        v = self.view(rotate=270)
        self.rect_markup(v, 1, F.Rect(300, 200, 400, 260) * v.doc[1].derotation_matrix)
        before = shown(v.doc[1], self.markup_rects(v.doc[1])[0])
        self.assertTrue(near(before, (300, 200, 400, 260), 2))
        _p, src = self.new_file([("A-102", "NEW 2")])
        v.replace_pages(src, [(1, 0)])
        page = v.doc[1]
        self.assertEqual(page.rotation, 0)
        self.assertTrue(near(shown(page, self.markup_rects(page)[0]), before, 0.01))
        pix = page.get_pixmap(annots=True)
        self.assertEqual(pix.pixel(350, 201)[:3], (255, 0, 0))

    # ---- links drawn into the old drawing --------------------------------------------------
    def test_links_made_on_the_old_drawing(self):
        v = self.view()
        # an underlined link on the words OLD 1, and a sheet callout link (as Link sheet
        # callouts makes) over the sheet number
        words = [w for w in v.doc[0].get_text("words") if w[4] in ("OLD", "1")][:2]
        box = F.Rect(words[0][:4]) | F.Rect(words[1][:4])
        v.modify(lambda: links.add(v.doc[0], [box], ("page", 2), look="underline",
                                   text_lines=True, on="text"))
        _p, src = self.new_file([("A-101", "NEW 1")], at=(60, 300))   # the label moved
        report = v.replace_pages(src, [(0, 0)])
        page = v.doc[0]
        kept = links.read(page)
        self.assertEqual(len(kept), 1)
        self.assertTrue(near(kept[0]["rect"], box, 0.01))
        self.assertEqual(report["check"], [(0, 1)])
        self.assertEqual(report["relinked"], 1)
        # its underline is drawn again on the new drawing
        a, b = kept[0]["under"][:2], kept[0]["under"][2:]
        lines = [d for d in page.get_drawings()
                 if d.get("color") and near(d["color"], links.BLUE, 0.01)]
        self.assertTrue(any(near(d["rect"], (a[0], a[1], b[0], b[1]), 1) for d in lines))
        self.assertEqual(self.info.call_count, 0)

    def test_link_on_words_still_there_is_not_reported(self):
        v = self.view()
        word = [w for w in v.doc[0].get_text("words") if w[4] == "OLD"][0]
        v.modify(lambda: v.doc[0].insert_link({"kind": F.LINK_GOTO, "page": 2,
                                               "from": F.Rect(word[:4])}))
        _p, src = self.new_file([("A-101", "OLD 9")])
        self.assertEqual(v.replace_pages(src, [(0, 0)])["check"], [])

    # ---- one undo step; the new file; save ------------------------------------------------
    def test_one_undo_gives_back_exactly_the_document_before(self):
        v = self.view()
        self.rect_markup(v, 0, (300, 200, 400, 260))
        self.rect_markup(v, 2, (100, 300, 200, 360))
        v.modify(lambda: v.doc.set_toc([[1, "Third", 3]]))
        before = canon(v._snapshot())
        steps = len(v._undo)
        _p, src = self.new_file([("A-101", "NEW 1"), ("A-103", "NEW 3")], size=(1224, 792),
                                rotate=90)
        v.replace_pages(src, [(0, 0), (2, 1)], scale=True)
        self.assertEqual(len(v._undo), steps + 1)
        after = canon(v._snapshot())
        self.assertNotEqual(after, before)
        v.undo()
        self.assertEqual(canon(v._snapshot()), before)
        self.assertEqual(self.labels(v), ["OLD 1", "OLD 2", "OLD 3"])
        self.assertTrue(near(v.doc[0].rect, (0, 0, 792, 612)))
        self.assertTrue(near(v.page_rects[0], (0, 0, 792, 612)))
        v.redo()
        self.assertEqual(canon(v._snapshot()), after)
        self.assertTrue(near(v.page_rects[0], (0, 0, 1224, 792)))
        self.assertEqual(self.labels(v), ["NEW 1", "OLD 2", "NEW 3"])

    def test_the_new_file_is_not_changed(self):
        v = self.view()
        path, src = self.new_file([("A-101", "NEW 1"), ("A-102", "NEW 2")], rotate=90)
        with open(path, "rb") as f:
            disk = hashlib.sha256(f.read()).hexdigest()
        mem = canon(src.tobytes())
        v.replace_pages(src, [(0, 0), (1, 1)])
        v.undo()
        v.redo()
        self.assertEqual(canon(src.tobytes()), mem)
        with open(path, "rb") as f:
            self.assertEqual(hashlib.sha256(f.read()).hexdigest(), disk)

    def test_saved_and_opened_again(self):
        v = self.view()
        mk = self.rect_markup(v, 1, (300, 200, 400, 260))
        v.modify(lambda: v.doc.set_toc([[1, "Second", 2]]))
        _p, src = self.new_file([("A-102", "NEW 2")], size=(396, 306))
        v.replace_pages(src, [(1, 0)], scale=True)
        out = os.path.join(self.tmp, "saved.pdf")
        v.save(out)
        with F.open(out) as d:
            page = d[1]
            self.assertEqual(page.get_text().split("\n")[0], "NEW 2")
            self.assertTrue(near(page.rect, (0, 0, 396, 306)))
            rects = [F.Rect(a.rect) for a in page.annots()]
            self.assertEqual(len(rects), 1)
            self.assertTrue(near(rects[0], (149.5, 99.5, 200.5, 130.5), 0.01))
            self.assertEqual(d.get_toc()[0][2], 2)
            self.assertEqual(d[0].get_text().split("\n")[0], "OLD 1")
        self.assertTrue(mk)

    def test_the_new_drawings_layers_come_along(self):
        v = self.view()
        d = F.open()
        page = sheet(d, "A-101", "NEW 1")
        walls = d.add_ocg("A-WALL", on=False)
        notes = d.add_ocg("A-NOTE", on=True)
        d.add_ocg("UNUSED", on=True)
        page.insert_text((100, 300), "wall", fontsize=12, oc=walls)
        page.draw_rect((100, 320, 200, 360), color=(0, 0, 0), oc=notes)
        path = os.path.join(self.tmp, "layers.pdf")
        d.save(path)
        d.close()
        src = F.open(path)
        self.docs.append(src)
        before = canon(v._snapshot())
        v.replace_pages(src, [(0, 0)])
        layers = {o["name"]: o["on"] for o in v.doc.get_ocgs().values()}
        self.assertEqual(layers, {"A-WALL": False, "A-NOTE": True})
        out = os.path.join(self.tmp, "layers-saved.pdf")
        v.save(out)
        with F.open(out) as saved:
            self.assertEqual({o["name"]: o["on"] for o in saved.get_ocgs().values()},
                             {"A-WALL": False, "A-NOTE": True})
            self.assertNotIn("wall", saved[0].get_text())       # (its layer is off)
        v.undo()
        self.assertEqual(canon(v._snapshot()), before)
        self.assertEqual(v.doc.get_ocgs(), {})

    def test_a_protected_document_refuses(self):
        path = make(os.path.join(self.tmp, "locked.pdf"), [("A-101", "OLD 1")])
        locked = os.path.join(self.tmp, "locked2.pdf")
        with F.open(path) as d:
            d.save(locked, encryption=F.PDF_ENCRYPT_AES_256, owner_pw="owner", user_pw="",
                   permissions=F.PDF_PERM_PRINT | F.PDF_PERM_ACCESSIBILITY)
        v = DocumentView(locked)
        self.views.append(v)
        _p, src = self.new_file([("A-101", "NEW 1")])
        self.assertIsNone(v.replace_pages(src, [(0, 0)]))
        self.assertEqual(self.info.call_args[0][1], "Protected document")
        self.assertEqual(v.doc[0].get_text().split("\n")[0], "OLD 1")

    def test_big_sheet_is_quick(self):
        import time
        v = self.view()
        self.rect_markup(v, 0, (300, 200, 400, 260))
        d = F.open()
        page = sheet(d, "A-101", "NEW 1", size=(2592, 1728))
        shape = page.new_shape()
        for k in range(20000):
            x = (k * 37) % 2500
            y = (k * 53) % 1650
            shape.draw_line((x, y), (x + 40, y + 25))
        shape.finish(color=(0, 0, 0), width=0.3)
        shape.commit()
        path = os.path.join(self.tmp, "big.pdf")
        d.save(path, deflate=True)
        d.close()
        src = F.open(path)
        self.docs.append(src)
        t = time.perf_counter()
        v.replace_pages(src, [(0, 0)])
        self.assertLess(time.perf_counter() - t, 2.0)
        self.assertTrue(near(v.doc[0].rect, (0, 0, 2592, 1728)))


if __name__ == "__main__":
    unittest.main()
