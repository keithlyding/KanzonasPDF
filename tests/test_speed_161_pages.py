"""1.6.1: big documents, page operations and panels made fast, and still right.
Pages added to a shown view are laid out once; several pages are deleted in one step; the
form's field order is kept between Tabs; a signed form is told by its list of fields;
autosave writes straight to a file; the markups list re-reads only what changed; page
thumbnails are kept per document and only changed pages are drawn again.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_speed_161_pages
"""
import os
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402
from PySide6.QtCore import QEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas.document_view import DocumentView, PAGE_GAP  # noqa: E402
from kanzonas.page_widget import PageWidget  # noqa: E402


def pump(seconds=0.05):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        APP.processEvents()
    APP.sendPostedEvents(None, QEvent.DeferredDelete)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.views = []

    def tearDown(self):
        for v in self.views:
            v.hide()
            if not v.doc.is_closed:
                v.doc.close()
            v.deleteLater()
        pump(0)
        self.tmp.cleanup()

    def path(self, name):
        return os.path.join(self.tmp.name, name)

    def view(self, path, show=False):
        v = DocumentView(path)
        self.views.append(v)
        if show:
            v.resize(800, 600)
            v.show()
            pump()
        return v


def numbered_pdf(path, n, toc=(), links=()):
    """n pages, each with its number as text; toc: [(level, title, page 1-based)];
    links: [(from page, to page)] (0-based)."""
    d = pymupdf.open()
    for i in range(n):
        p = d.new_page(width=612 if i % 3 else 400, height=792)
        p.insert_text((72, 72), "page %d" % (i + 1))
    for k, (src, dst) in enumerate(links):
        d[src].insert_link({"kind": pymupdf.LINK_GOTO, "from": pymupdf.Rect(72, 100 + 20 * k, 200, 115 + 20 * k),
                            "page": dst, "to": pymupdf.Point(0, 0)})
    if toc:
        d.set_toc(list(toc))
    d.save(path)
    d.close()


def page_texts(doc):
    return [doc[i].get_text().strip() for i in range(doc.page_count)]


# ---- 1: pages added to a shown view --------------------------------------------------
class InsertLayout(Base):
    def check_layout(self, v):
        self.assertEqual(len(v.pages), v.doc.page_count)
        y = v._canvas_margin[1]
        for i, w in enumerate(v.pages):
            self.assertEqual(w.index, i)
            self.assertTrue(w.isVisible(), i)
            r = v.doc[i].rect
            self.assertEqual((w.width(), w.height()),
                             (max(1, int(r.width * v.zoom)), max(1, int(r.height * v.zoom))))
            self.assertEqual(w.y(), y, i)
            y += w.height() + PAGE_GAP

    def test_inserted_pages_are_shown_and_stacked_in_order(self):
        numbered_pdf(self.path("a.pdf"), 40)
        numbered_pdf(self.path("b.pdf"), 30)
        v = self.view(self.path("a.pdf"), show=True)
        v.goto_page(20)
        v.setFocus()
        pump()
        v.insert_pdf(self.path("b.pdf"), 20)
        pump()
        self.assertEqual(v.doc.page_count, 70)
        self.check_layout(v)
        self.assertEqual(page_texts(v.doc)[19:21], ["page 20", "page 1"])
        self.assertEqual(page_texts(v.doc)[50], "page 21")
        self.assertTrue(v.hasFocus() or not v.isActiveWindow())
        v.undo()
        pump()
        self.assertEqual(v.doc.page_count, 40)
        self.check_layout(v)
        v.redo()
        pump()
        self.check_layout(v)

    def test_inserting_many_pages_into_a_big_document_stays_quick(self):
        numbered_pdf(self.path("a.pdf"), 600)
        numbered_pdf(self.path("b.pdf"), 300)
        v = self.view(self.path("a.pdf"), show=True)
        v.goto_page(300)
        pump()
        t = time.perf_counter()
        v.insert_pdf(self.path("b.pdf"), 300)
        pump(0.3)
        took = time.perf_counter() - t
        self.check_layout(v)
        # (laid out page by page this took several seconds; now well under one)
        self.assertLess(took, 3.0)


# ---- 2: several pages deleted at once ----------------------------------------------------
class DeletePages(Base):
    TOC = [(1, "Two", 2), (1, "Three", 3), (2, "Four", 4), (1, "Seven", 7), (1, "Last", 10),
           (1, "Nine", 9)]
    LINKS = [(0, 2), (0, 5), (0, 6), (7, 3), (9, 8), (4, 9)]

    def old_way(self, path, indices):
        """What delete_pages did before: one page at a time (the reference)."""
        v = self.view(path)
        indices = sorted(set(indices), reverse=True)

        def do():
            toc = v.doc.get_toc(False)
            for i in indices:
                v.doc.delete_page(i)
            v._retarget_bookmarks(toc, set(indices), len(indices) + v.doc.page_count)
        v.modify(do, structural=True)
        return v

    def summary(self, doc):
        links = [[(ln.get("page"), tuple(round(c) for c in ln["from"])) for ln in doc[i].get_links()]
                 for i in range(doc.page_count)]
        return page_texts(doc), doc.get_toc(), links

    def test_same_pages_bookmarks_and_links_as_one_at_a_time(self):
        for gone in ([1, 2, 5], [9], [0, 8, 9], [3, 4, 5, 6]):
            path = self.path("d%s.pdf" % "_".join(map(str, gone)))
            numbered_pdf(path, 10, self.TOC, self.LINKS)
            ref = self.old_way(path, gone)
            v = self.view(path)
            self.assertTrue(v.delete_pages(gone))
            self.assertEqual(self.summary(v.doc), self.summary(ref.doc), gone)
            self.assertEqual(len(v.pages), 10 - len(gone))
            # undo puts everything back
            v.undo()
            with pymupdf.open(path) as orig:
                self.assertEqual(self.summary(v.doc), self.summary(orig))

    def test_one_call_for_many_pages(self):
        path = self.path("m.pdf")
        numbered_pdf(path, 12, self.TOC, self.LINKS)
        v = self.view(path)
        with mock.patch.object(pymupdf.Document, "delete_pages",
                               autospec=True, side_effect=pymupdf.Document.delete_pages) as dp:
            v.delete_pages([1, 3, 5, 7])
        self.assertEqual(dp.call_count, 1)
        self.assertEqual(page_texts(v.doc)[:4], ["page 1", "page 3", "page 5", "page 7"])

    def test_at_least_one_page_is_kept(self):
        path = self.path("k.pdf")
        numbered_pdf(path, 3)
        v = self.view(path)
        with mock.patch("kanzonas.document_view.QMessageBox.information"):
            self.assertFalse(v.delete_pages([0, 1, 2]))
        self.assertEqual(v.doc.page_count, 3)


# ---- 3: page sizes read without loading the pages; a page turned on its own -------------
class PageSizes(InsertLayout):
    def odd_pages(self, path):
        d = pymupdf.open()
        for k in range(14):
            p = d.new_page(width=300 + 10 * k, height=500 - 7 * k)
            p.set_rotation(90 * (k % 4))
            if k % 3 == 1:
                p.set_cropbox(pymupdf.Rect(10, 20, 200, 300))
        doc = pymupdf.open(stream=d.tobytes(), filetype="pdf")
        x = [doc.page_xref(i) for i in range(doc.page_count)]
        doc.xref_set_key(x[5], "UserUnit", "2")
        doc.xref_set_key(x[7], "Rotate", "45")               # (not a quarter turn)
        doc.xref_set_key(x[8], "MediaBox", "[0 0 0 0]")      # (an unusable box)
        doc.xref_set_key(x[9], "MediaBox", "[100 100 -50 -20]")
        doc.xref_set_key(x[10], "Rotate", "null")            # inherited from the page tree
        tree = int(doc.xref_get_key(doc.pdf_catalog(), "Pages")[1].split()[0])
        doc.xref_set_key(tree, "Rotate", "90")
        doc.save(path)

    def test_same_sizes_as_loading_each_page(self):
        path = self.path("odd.pdf")
        self.odd_pages(path)
        v = self.view(path)
        with pymupdf.open(path) as d:
            self.assertEqual(v.page_rects, [p.rect for p in d])

    def test_a_page_held_through_a_move_is_noticed(self):
        numbered_pdf(self.path("h.pdf"), 6)
        v = self.view(self.path("h.pdf"))
        self.assertFalse(v._stale_pages())
        held = v.doc[2]._pdf_page()
        v.doc.move_page(1, 4)
        self.assertTrue(v._stale_pages())
        del held

    def test_turning_a_page_resizes_only_it(self):
        numbered_pdf(self.path("r.pdf"), 30)
        v = self.view(self.path("r.pdf"), show=True)
        v.goto_page(12)
        pump()
        mirror = DocumentView.mirror(v)
        self.views.append(mirror)
        mirror.resize(600, 500)
        mirror.show()
        pump()
        widgets = list(v.pages)
        events = []
        v.structureChanged.connect(lambda: events.append("structure"))
        v.take_thumb_changes()
        with mock.patch.object(PageWidget, "reuse", side_effect=AssertionError("rebuilt")):
            v.rotate_page(12, 90)
            pump()
        self.assertEqual(events, [])
        self.assertEqual(v.pages, widgets)
        self.assertEqual(v.doc[12].rotation, 90)
        self.check_layout(v)
        self.assertEqual(v.current_page(), 12)              # still in view
        self.assertEqual(v.page_rects, [p.rect for p in v.doc])
        self.assertEqual(mirror.page_rects, v.page_rects)
        self.assertEqual(mirror.pages[12].size(), mirror.pages[12].size().__class__(
            max(1, int(v.page_rects[12].width * mirror.zoom)),
            max(1, int(v.page_rects[12].height * mirror.zoom))))
        self.assertEqual(v.thumbs_changed, {v.doc.page_xref(12)})
        v.undo()
        pump()
        self.assertEqual(v.doc[12].rotation, 0)
        self.check_layout(v)
        v.redo()
        pump()
        self.assertEqual(v.doc[12].rotation, 90)
        self.check_layout(v)


# ---- 4: form fields ----------------------------------------------------------------------
def form_pdf(path, rows=4, pages=2):
    d = pymupdf.open()
    for p in range(pages):
        page = d.new_page()
        for r in range(rows):
            for c in range(2):
                w = pymupdf.Widget()
                w.field_type = pymupdf.PDF_WIDGET_TYPE_TEXT
                w.field_name = "p%dr%dc%d" % (p, r, c)
                w.rect = pymupdf.Rect(72 + 220 * c, 100 + 60 * r, 272 + 220 * c, 120 + 60 * r)
                page.add_widget(w)
    d.save(path)
    d.close()


def names(v, order):
    out = []
    for i, x in order:
        page = v.doc[i]
        out.append(page.load_widget(x).field_name)
    return out


class FieldOrder(Base):
    def test_kept_between_tabs_and_read_again_after_a_change(self):
        path = self.path("f.pdf")
        form_pdf(path)
        v = self.view(path)
        first = v.field_order()
        self.assertEqual(names(v, first)[:3], ["p0r0c0", "p0r0c1", "p0r1c0"])
        with mock.patch.object(DocumentView, "_read_field_order",
                               side_effect=AssertionError("read again")):
            self.assertEqual(v.field_order(), first)
            # filling in a value doesn't move any field
            v._set_field(0, first[0][1], "typed")
            self.assertEqual(v.field_order(), first)
            v._set_field(0, first[1][1], "")
            self.assertEqual(v.field_order(), first)
        self.assertEqual(v.doc[0].load_widget(first[0][1]).field_value, "typed")
        # a field moved: read again
        x = first[0][1]

        def move():
            page = v.doc[0]
            w = page.load_widget(x)
            w.rect = pymupdf.Rect(72, 700, 272, 720)
            w.update()
        v.modify(move, [0])
        self.assertEqual(names(v, v.field_order())[:4], ["p0r0c1", "p0r1c0", "p0r1c1", "p0r2c0"])
        self.assertEqual(names(v, v.field_order())[7], "p0r0c0")
        # undo, a page rotated, pages moved: read again
        v.undo()
        self.assertEqual(names(v, v.field_order()), names(v, first))
        v.move_page(1, -1)
        self.assertEqual(names(v, v.field_order())[0], "p1r0c0")
        v.undo()
        self.assertEqual(names(v, v.field_order())[0], "p0r0c0")
        v.rotate_page(0, 90)
        self.assertNotEqual(names(v, v.field_order())[:2], ["p0r0c0", "p0r0c1"])
        v.undo()
        # a field made read-only leaves the order
        v.modify(lambda: v.doc.xref_set_key(first[2][1], "Ff", "1"), [0])
        self.assertNotIn(first[2], v.field_order())

    def test_a_returned_order_can_be_changed_by_the_caller(self):
        path = self.path("g.pdf")
        form_pdf(path)
        v = self.view(path)
        a = v.field_order()
        a.clear()
        self.assertTrue(v.field_order())


class SignedForm(Base):
    def make(self, name, sign=None):
        path = self.path(name)
        d = pymupdf.open()
        page = d.new_page()
        w = pymupdf.Widget()
        w.field_type = pymupdf.PDF_WIDGET_TYPE_TEXT
        w.field_name = "name"
        w.rect = pymupdf.Rect(72, 72, 272, 92)
        page.add_widget(w)
        w = pymupdf.Widget()
        w.field_type = pymupdf.PDF_WIDGET_TYPE_SIGNATURE
        w.field_name = "sig"
        w.rect = pymupdf.Rect(72, 200, 272, 260)
        page.add_widget(w)
        sx = w.xref
        if sign == "value":
            v = d.get_new_xref()
            d.update_object(v, "<< /Type /Sig /Filter /Adobe.PPKLite /Contents <00> >>")
            d.xref_set_key(sx, "V", "%d 0 R" % v)
        elif sign == "parent":
            # the signature (/FT /Sig and /V) on a parent field, the widget its kid
            v = d.get_new_xref()
            d.update_object(v, "<< /Type /Sig /Filter /Adobe.PPKLite /Contents <00> >>")
            parent = d.get_new_xref()
            d.update_object(parent, "<< /FT /Sig /T (outer) /V %d 0 R /Kids [%d 0 R] >>" % (v, sx))
            for key in ("FT", "T"):
                d.xref_set_key(sx, key, "null")
            d.xref_set_key(sx, "Parent", "%d 0 R" % parent)
            cat = d.pdf_catalog()
            typ, arr = d.xref_get_key(cat, "AcroForm/Fields")
            arr = arr.replace("%d 0 R" % sx, "%d 0 R" % parent)
            d.xref_set_key(cat, "AcroForm/Fields", arr)
        d.save(path)
        d.close()
        return path

    def old_way(self, doc):
        for page in doc:
            for w in page.widgets(types=[pymupdf.PDF_WIDGET_TYPE_SIGNATURE]):
                if w.is_signed:
                    return True
        return False

    def test_told_from_the_list_of_fields_as_from_the_widgets(self):
        for name, sign, want in (("empty.pdf", None, False), ("signed.pdf", "value", True),
                                 ("parent.pdf", "parent", True)):
            v = self.view(self.make(name, sign))
            self.assertEqual(v._has_filled_signature(), want, name)
            self.assertEqual(self.old_way(v.doc), want, name)
            if want:
                self.assertIsNotNone(v._orig_data, name)    # kept to save a copy

    def test_no_form_no_signature(self):
        path = self.path("plain.pdf")
        numbered_pdf(path, 3)
        v = self.view(path)
        self.assertFalse(v._has_filled_signature())

    def test_a_really_signed_file_opens_read_only(self):
        try:
            from kanzonas import digisign
            cert = self.path("c.p12")
            digisign.create_certificate("Test", "", "", "pw", cert)
        except Exception as ex:                        # (pyHanko missing)
            self.skipTest(str(ex))
        src = self.path("src.pdf")
        numbered_pdf(src, 2)
        out = self.path("really_signed.pdf")
        with open(src, "rb") as f:
            digisign.sign(f.read(), out, digisign.load_signer(cert, "pw"), "test")
        v = self.view(out)
        self.assertTrue(v._has_filled_signature())
        v.check_digital_signatures()
        self.assertTrue(v.sig_results)
        self.assertTrue(v.read_only)


# ---- 5: autosave -------------------------------------------------------------------------
class Autosave(Base):
    def saver(self, folder, v):
        from kanzonas import autosave

        class Tabs:
            def count(self):
                return 1

            def widget(self, i):
                return v

        class Win:
            tabs = Tabs()
        s = autosave.Autosaver.__new__(autosave.Autosaver)
        s.win = Win()
        return s

    def test_backup_written_whole_and_in_place(self):
        from kanzonas import autosave
        path = self.path("a.pdf")
        numbered_pdf(path, 5)
        v = self.view(path)
        v.modify(lambda: v.doc[2].add_rect_annot((10, 10, 50, 50)), [2])
        folder = self.path("backups")
        os.makedirs(folder)
        s = self.saver(folder, v)
        with mock.patch.object(autosave, "folder", return_value=folder):
            s.tick()
            self.assertTrue(v._backup_path)
            self.assertEqual(os.path.dirname(v._backup_path), folder)
            files = sorted(os.listdir(folder))
            self.assertEqual([f for f in files if f.endswith(".pdf")],
                             [os.path.basename(v._backup_path)])
            self.assertFalse([f for f in files if f.endswith(".part")])
            with pymupdf.open(v._backup_path) as b:
                self.assertEqual(b.page_count, 5)
                self.assertEqual(len(list(b[2].annots())), 1)
            self.assertEqual(autosave.leftovers()[0][1], v.path)
            # another change: the same copy is written again
            v.modify(lambda: v.doc[3].add_rect_annot((10, 10, 50, 50)), [3])
            s.tick()
            with pymupdf.open(v._backup_path) as b:
                self.assertEqual(len(list(b[3].annots())), 1)
            self.assertEqual(len([f for f in os.listdir(folder) if f.endswith(".pdf")]), 1)
            # a write that fails leaves the last good copy and no half-written file
            v.modify(lambda: v.doc[4].add_rect_annot((10, 10, 50, 50)), [4])
            good = v._backup_path

            def broken(doc, name, *a, **k):
                with open(name, "wb") as f:
                    f.write(b"%PDF-1.7 half")
                raise RuntimeError("disk full")
            with mock.patch.object(pymupdf.Document, "save", autospec=True, side_effect=broken):
                s.tick()
            self.assertFalse([f for f in os.listdir(folder) if f.endswith(".part")])
            with pymupdf.open(good) as b:
                self.assertEqual(len(list(b[3].annots())), 1)
            s.discard(v)
            self.assertFalse([f for f in os.listdir(folder) if f.endswith(".pdf")])


# ---- 6: markups list and comment boxes ---------------------------------------------------
def markups_pdf(path, pages=4, per_page=6):
    d = pymupdf.open()
    for i in range(pages):
        page = d.new_page()
        page.insert_text((72, 72), "Some words to mark on page %d" % (i + 1))
        for k in range(per_page):
            r = pymupdf.Rect(60 + 40 * k, 200, 90 + 40 * k, 230)
            a = page.add_rect_annot(r) if k % 3 else page.add_circle_annot(r)
            a.set_info(content="mark %d.%d" % (i, k), title="author%d" % (k % 2))
            a.set_colors(stroke=(k / per_page, 0, 1 - k / per_page))
            a.update()
        page.add_text_annot((400, 400 + i), "note on page %d" % (i + 1))
    d.save(path)
    d.close()


def table(panel):
    t = panel.table
    return [tuple(t.item(r, c).text() for c in range(t.columnCount())) + (t.isRowHidden(r),)
            for r in range(t.rowCount())]


class MarkupsList(Base):
    def setUp(self):
        super().setUp()
        from kanzonas.markups_panel import MarkupsPanel
        self.panels = []
        self.Panel = MarkupsPanel
        markups_pdf(self.path("m.pdf"))
        self.v = self.view(self.path("m.pdf"))

    def tearDown(self):
        for p in self.panels:
            p.deleteLater()
        super().tearDown()

    def panel(self):
        p = self.Panel()
        self.panels.append(p)
        return p

    def same_as_a_fresh_list(self, panel, sort=None):
        ref = self.panel()
        if sort is not None:
            ref.table.sortItems(*sort)
        ref.type_filter.setCurrentText(panel.type_filter.currentText())
        ref.text_filter.setText(panel.text_filter.text())
        # a list filled from nothing known (another document object with the same pages)
        fresh = pymupdf.open(stream=self.v.doc.tobytes(), filetype="pdf")
        self.addCleanup(fresh.close)
        ref.refresh(fresh)
        self.assertEqual(table(panel), table(ref))
        self.assertEqual(panel.count.text(), ref.count.text())

    def edit(self, page, fn):
        def do():
            pg = self.v.doc[page]
            fn(pg)
        self.v.modify(do, [page])

    def annot(self, pg, k):
        return [a for a in pg.annots()][k]

    def test_changes_shown_as_a_fresh_list_shows_them(self):
        from kanzonas import markups_panel as MP
        v, panel = self.v, self.panel()
        panel.refresh(v.doc, v.take_markup_changes())
        self.same_as_a_fresh_list(panel)
        steps = [
            (1, lambda pg: pg.add_rect_annot((300, 500, 340, 540))),           # added
            (2, lambda pg: (lambda a: (a.set_info(content="changed text"), a.update()))(
                self.annot(pg, 2))),                                            # text
            (0, lambda pg: (lambda a: (a.set_colors(stroke=(0, 1, 0)), a.update()))(
                self.annot(pg, 0))),                                            # color
            (3, lambda pg: pg.delete_annot(self.annot(pg, 4))),                 # deleted
            (1, lambda pg: (lambda a: (a.set_border(clouds=2), a.update()))(
                self.annot(pg, 1))),                                            # cloud
        ]
        for page, fn in steps:
            self.edit(page, fn)
            with mock.patch.object(MP, "_row", wraps=MP._row) as reads, \
                    mock.patch.object(panel, "_set_row", wraps=panel._set_row) as rows:
                panel.refresh(v.doc, v.take_markup_changes())
            self.assertLessEqual(reads.call_count, 1)       # only the markup that changed
            self.assertLessEqual(rows.call_count, 1)        # and only its row replaced
            self.same_as_a_fresh_list(panel)
        # filtered: the same rows hidden
        panel.text_filter.setText("author1")
        self.edit(0, lambda pg: (lambda a: (a.set_info(title="author1"), a.update()))(
            self.annot(pg, 0)))
        panel.refresh(v.doc, v.take_markup_changes())
        self.same_as_a_fresh_list(panel)
        # undo reads only what differs from the document before
        with mock.patch.object(MP, "_row", wraps=MP._row) as reads:
            v.undo()
            panel.refresh(v.doc, v.take_markup_changes())
        self.assertLessEqual(reads.call_count, 1)
        self.same_as_a_fresh_list(panel)

    def test_sorted_by_another_column_comes_out_as_a_fresh_list(self):
        from PySide6.QtCore import Qt
        v, panel = self.v, self.panel()
        panel.refresh(v.doc, v.take_markup_changes())
        for col, order in ((1, Qt.AscendingOrder), (0, Qt.DescendingOrder), (3, Qt.DescendingOrder)):
            panel.table.sortItems(col, order)
            self.edit(0, lambda pg: pg.add_circle_annot((300, 600, 340, 640)))
            self.edit(2, lambda pg: (lambda a: (a.set_info(content="zz"), a.update()))(
                self.annot(pg, 3)))
            panel.refresh(v.doc, v.take_markup_changes())
            self.same_as_a_fresh_list(panel, (col, order))

    def test_the_selected_markup_stays_selected(self):
        v, panel = self.v, self.panel()
        panel.refresh(v.doc, v.take_markup_changes())
        panel.table.selectRow(8)
        key = panel._key(8)
        self.edit(3, lambda pg: pg.add_rect_annot((300, 500, 340, 540)))
        self.edit(0, lambda pg: (lambda a: (a.set_info(content="other"), a.update()))(
            self.annot(pg, 1)))
        panel.refresh(v.doc, v.take_markup_changes())
        rows = {i.row() for i in panel.table.selectedIndexes()}
        self.assertEqual([panel._key(r) for r in rows], [key])

    def test_pages_deleted_and_another_document(self):
        v, panel = self.v, self.panel()
        panel.refresh(v.doc, v.take_markup_changes())
        v.delete_pages([1])
        panel.refresh(v.doc, v.take_markup_changes())
        self.same_as_a_fresh_list(panel)
        markups_pdf(self.path("n.pdf"), pages=2, per_page=2)
        other = self.view(self.path("n.pdf"))
        panel.refresh(other.doc, other.take_markup_changes())
        self.assertEqual(panel.table.rowCount(), 6)
        panel.refresh(None)
        self.assertEqual(panel.table.rowCount(), 0)


class CommentCards(Base):
    def test_same_cards_as_reading_every_markup(self):
        from kanzonas import annotations as A
        path = self.path("c.pdf")
        markups_pdf(path, pages=1, per_page=30)
        v = self.view(path)
        words = v.doc[0].search_for("words")
        quads = [r.quad for r in words]

        def add():
            pg = v.doc[0]
            for style in ("highlight", "underline", "strikeout"):
                A.write(pg, {"kind": "comment", "props": dict(A.DEFAULTS["comment"], markup=style),
                             "quads": quads, "rect": words[0], "text": "said " + style})
            pg.add_highlight_annot(words[0])                 # a plain highlight: no box
        v.modify(add, [0])
        cards = v.comment_cards(0)
        old = []
        page = v.doc[0]
        for a in A.each_annot(page):
            m = A.read(a)
            if m and m["kind"] == "comment":
                old.append((A.bounds(m), m.get("text", ""), a.xref))
        self.assertEqual(len(cards), 3)
        self.assertEqual(cards, old)


# ---- 7: page thumbnails --------------------------------------------------------------------
class Thumbnails(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        from kanzonas.main_window import MainWindow
        from PySide6.QtWidgets import QMessageBox
        p = mock.patch.object(QMessageBox, "question", return_value=QMessageBox.Yes)
        p.start()
        self.addCleanup(p.stop)
        self.w = MainWindow()
        self.w.resize(1200, 800)
        self.w.show()
        self.w.dock.show()
        self.w.left_tabs.setCurrentIndex(0)
        self.drawn = []
        # (1.7: a thumbnail is drawn by page_widget.thumbnail, from the page's render on
        # screen when it has one, else with get_pixmap as before: each one drawn counts)
        from kanzonas import page_widget
        orig = page_widget.thumbnail

        def counted(view, i, s):
            self.drawn.append(view.doc.page_xref(i))
            return orig(view, i, s)
        p = mock.patch.object(page_widget, "thumbnail", side_effect=counted)
        p.start()
        self.addCleanup(p.stop)

    def tearDown(self):
        for v in self.w._views():
            v.dirty = False
        self.w._close_confirmed = True
        self.w.close()
        self.w.deleteLater()
        pump(0.05)
        self.tmp.cleanup()

    def open(self, name, n):
        path = os.path.join(self.tmp.name, name)
        numbered_pdf(path, n)
        self.w.open_file(path)
        self.w.lock_btn.setChecked(False)
        self.settle()
        return self.w.view()

    def settle(self):
        for _ in range(4):
            pump(0.05)
            for _ in range(200):
                if not self.w._thumb_timer.isActive():
                    break
                self.w._thumb_step()

    def rows(self):
        t = self.w.thumbs
        return [(t.item(i).text(), t.item(i).data(0x0100)) for i in range(t.count())]

    def check_list(self, v):
        self.assertEqual(self.rows(), [(str(i + 1), v.doc.page_xref(i))
                                       for i in range(v.doc.page_count)])

    def icon_key(self, row):
        return self.w.thumbs.item(row).icon().cacheKey()

    def test_only_the_rows_in_view_are_drawn(self):
        v = self.open("a.pdf", 300)
        self.check_list(v)
        in_view = self.w._thumb_rows()
        self.assertTrue(in_view)
        self.assertLess(len(self.drawn), 60)
        self.assertEqual(set(self.drawn), {v.doc.page_xref(r) for r in in_view})
        # scrolled to the end: those are drawn then
        self.drawn.clear()
        self.w.thumbs.scrollToBottom()
        self.settle()
        self.assertIn(v.doc.page_xref(299), self.drawn)
        self.assertNotIn(v.doc.page_xref(0), self.drawn)

    def test_kept_across_tabs_and_redrawn_only_where_changed(self):
        v = self.open("a.pdf", 40)
        first = {r: self.icon_key(r) for r in self.w._thumb_rows()}
        self.open("b.pdf", 10)
        self.drawn.clear()
        self.w.tabs.setCurrentIndex(0)
        self.settle()
        self.assertEqual(self.drawn, [])                    # nothing drawn again
        self.assertEqual({r: self.icon_key(r) for r in first}, first)
        self.check_list(v)
        # an edit on page 2: only page 2 again
        v.modify(lambda: v.doc[1].add_rect_annot((10, 10, 60, 60)), [1])
        self.settle()
        self.assertEqual(self.drawn, [v.doc.page_xref(1)])
        self.assertNotEqual(self.icon_key(1), first[1])
        # pages added, removed, moved: the others keep their thumbnails
        self.drawn.clear()
        keys = {v.doc.page_xref(i): self.icon_key(i) for i in range(4)}
        v.insert_blank(1)
        self.settle()
        self.check_list(v)
        self.assertEqual(self.drawn, [v.doc.page_xref(1)])  # just the new page
        self.assertEqual(self.icon_key(0), keys[v.doc.page_xref(0)])
        self.assertEqual(self.icon_key(2), keys[v.doc.page_xref(2)])
        self.drawn.clear()
        v.move_page(3, -1)
        v.delete_pages([1])
        self.settle()
        self.check_list(v)
        self.assertEqual(self.drawn, [])
        for i in range(3):
            self.assertEqual(self.icon_key(i), keys[v.doc.page_xref(i)])
        # a page rotated: that one again
        v.rotate_page(2, 90)
        self.settle()
        self.assertEqual(self.drawn, [v.doc.page_xref(2)])
        self.check_list(v)

    def test_undo_keeps_the_list_and_draws_what_is_in_view(self):
        v = self.open("a.pdf", 200)
        v.modify(lambda: v.doc[0].add_rect_annot((10, 10, 60, 60)), [0])
        self.settle()
        items = [self.w.thumbs.item(i) for i in range(self.w.thumbs.count())]
        self.w.thumbs.setCurrentRow(0)
        self.drawn.clear()
        with mock.patch.object(self.w.thumbs, "clear", side_effect=AssertionError("rebuilt")):
            v.undo()
            self.settle()
        self.assertEqual([self.w.thumbs.item(i) for i in range(self.w.thumbs.count())], items)
        self.assertEqual(set(self.drawn), {v.doc.page_xref(r) for r in self.w._thumb_rows()})
        self.assertLess(len(self.drawn), 60)
        self.check_list(v)
        self.assertEqual(self.w.thumbs.currentRow(), v.current_page())

    def test_hidden_panel_draws_nothing_until_shown(self):
        self.w.dock.hide()
        v = self.open("a.pdf", 50)
        self.assertEqual(self.drawn, [])
        self.w.dock.show()
        self.settle()
        self.assertTrue(self.drawn)
        self.check_list(v)

    def test_at_most_thumb_keep_per_document(self):
        v = self.open("a.pdf", 200)
        self.w.THUMB_KEEP = 30
        for row in (60, 120, 199):
            self.w.thumbs.scrollToItem(self.w.thumbs.item(row))
            self.settle()
        self.assertLessEqual(len(v.thumb_icons), 30)
        blank = self.w._blank_thumb().cacheKey()
        self.assertEqual(self.icon_key(0), blank)           # (drawn again when in view)
        for r in self.w._visible_thumb_rows():
            self.assertNotEqual(self.icon_key(r), blank)


if __name__ == "__main__":
    unittest.main()
