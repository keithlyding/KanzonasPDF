"""Markup and form fixes found by the 1.4 user testing: a form protected only with a
permissions password opens for filling in; presses inside unfilled shapes go to what's
inside them; links stay with what they were made on and open on markups; signing a form
field needs only the form-filling permission; Flatten keeps redaction marks that aren't
applied and keeps links whole; Edit text isn't offered where it would be thrown away; fill-in
stamps read as text; copied Count markers count on; the Markups list starts with page 1;
Search & redact keeps notes with [redacted]; changing many markups at once isn't quadratic.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_markup_fixes
"""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402
from PySide6.QtCore import QEvent, Qt  # noqa: E402
from PySide6.QtGui import QColor, QImage, QMouseEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QInputDialog, QMenu, QMessageBox  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import annotations, dialogs, links, measure, signatures, stamps  # noqa: E402
from kanzonas.document_view import DocumentView  # noqa: E402
from kanzonas.main_window import MainWindow  # noqa: E402

P, R = pymupdf.Point, pymupdf.Rect


def new_pdf(build, **save):
    d = pymupdf.open()
    build(d)
    path = os.path.join(tempfile.mkdtemp(), "t.pdf")
    d.save(path, **save)
    return path


def blank(pages=2):
    def build(d):
        for _ in range(pages):
            d.new_page()
    return build


class Base(unittest.TestCase):
    def view(self, path):
        v = DocumentView(path)
        self.addCleanup(v.close_doc)
        v.check_digital_signatures()            # (the window does this when it opens one)
        return v

    def click(self, v, pt, mods=Qt.NoModifier, to=None, index=0):
        """Press at pt, drag to `to` (if given) and release, as the mouse does."""
        w = v.pages[index]
        a = w.to_screen_pt(P(pt))
        b = w.to_screen_pt(P(to)) if to is not None else a
        w.mousePressEvent(QMouseEvent(QEvent.MouseButtonPress, a, w.mapToGlobal(a),
                                      Qt.LeftButton, Qt.LeftButton, mods))
        if to is not None:
            for k in range(1, 6):
                m = a + (b - a) * (k / 5)
                w.mouseMoveEvent(QMouseEvent(QEvent.MouseMove, m, w.mapToGlobal(m),
                                             Qt.NoButton, Qt.LeftButton, mods))
        w.mouseReleaseEvent(QMouseEvent(QEvent.MouseButtonRelease, b, w.mapToGlobal(b),
                                        Qt.LeftButton, Qt.NoButton, mods))

    def stamp_label(self, label):
        """Stamp tool set to this label for the test (the tool's own setting comes back)."""
        old = annotations.tool_props("stamp")
        annotations.set_tool_props("stamp", dict(old, label=label))
        self.addCleanup(annotations.set_tool_props, "stamp", old)

    def annots(self, v, index=0):
        """[(xref, type, rect)] of the page's markups (read while the page is alive)."""
        page = v.doc[index]
        return [(a.xref, a.type[0], pymupdf.Rect(a.rect)) for a in annotations.each_annot(page)]

    def contents(self, v, index=0):
        page = v.doc[index]
        return [a.info["content"] for a in annotations.each_annot(page)]


# ---- 1 ------------------------------------------------------------------------------------
def protected_form(d):
    p = d.new_page()
    for name, rect, kind in (("name", R(100, 100, 300, 120), pymupdf.PDF_WIDGET_TYPE_TEXT),
                             ("Signature1", R(100, 200, 300, 240),
                              pymupdf.PDF_WIDGET_TYPE_SIGNATURE)):
        w = pymupdf.Widget()
        w.field_type, w.field_name, w.rect = kind, name, rect
        p.add_widget(w)
    d.xref_set_key(d.pdf_catalog(), "AcroForm/SigFlags", "3")


class ProtectedForm(Base):
    def test_permissions_password_form_with_an_empty_signature_field_fills_in(self):
        path = new_pdf(protected_form, encryption=pymupdf.PDF_ENCRYPT_AES_256,
                       owner_pw="owner", user_pw="",
                       permissions=pymupdf.PDF_PERM_PRINT | pymupdf.PDF_PERM_FORM)
        v = self.view(path)
        self.assertGreaterEqual(v.doc.get_sigflags(), 1)
        self.assertFalse(v.read_only)
        self.assertEqual(v.sig_results, [])
        self.assertTrue(v.allowed(pymupdf.PDF_PERM_FORM))

    def test_a_failed_check_without_a_filled_signature_never_locks_the_file(self):
        from kanzonas import digisign
        path = new_pdf(protected_form)
        with mock.patch.object(digisign, "validate", side_effect=RuntimeError("broken")):
            v = self.view(path)
        self.assertFalse(v.read_only)
        self.assertEqual(v.sig_results, [])


# ---- 2 ------------------------------------------------------------------------------------
class InsideUnfilledShapes(Base):
    def make(self):
        v = self.view(new_pdf(blank(1)))
        v.set_page_scale([0], measure.scale_from_preset(48), "ft-in", '1/4" = 1\'-0"')
        v.apply_poly(0, "m_area", [P(100, 100), P(400, 100), P(400, 400), P(100, 400)])
        v.clear_selection()
        return v

    def test_a_length_dragged_inside_an_area_draws(self):
        v = self.make()
        v.set_tool("m_length")
        self.click(v, (150, 250), to=(300, 250))
        page = v.doc[0]
        kinds = [annotations.read(a)["kind"] for a in annotations.each_annot(page)]
        self.assertEqual(kinds, ["m_area", "m_length"])
        area = annotations.each_annot(page)[0]
        self.assertLess(abs(area.rect.x0 - 100), 20)              # the area didn't move

    def test_count_and_cloud_inside_an_area_draw(self):
        v = self.make()
        v.set_tool("m_count")
        self.click(v, (200, 200))
        v.set_tool("cloud")
        self.click(v, (250, 300), to=(350, 360))
        self.assertEqual(len(self.contents(v)), 3)

    def test_outline_filled_and_label_still_hit(self):
        v = self.make()
        x = self.annots(v)[0][0]
        self.assertEqual(v.annot_at(0, P(101, 250)), x)            # on its outline
        self.assertIsNone(v.annot_at(0, P(180, 180)))              # inside, off the label
        # the area's label in the middle still picks it
        self.assertEqual(v.annot_at(0, P(250, 250)), x)
        # a filled rectangle is hit anywhere inside
        props = dict(annotations.tool_props("rect"), fill="#ffff00")
        v._create(0, {"kind": "rect", "props": props, "rect": R(500, 500, 560, 560)})
        self.assertIsNotNone(v.annot_at(0, P(530, 530)))

    def test_select_picks_an_unfilled_cloud_or_rectangle_by_its_outline(self):
        v = self.view(new_pdf(blank(1)))
        v.apply_drag_tool(0, "cloud", P(100, 100), P(300, 200), False)
        v.apply_drag_tool(0, "rect", P(100, 300), P(300, 400), False)
        v.apply_drag_tool(0, "ellipse", P(350, 300), P(550, 400), False)
        v.clear_selection()
        v.set_tool("select")
        for edge, inside in (((100, 150), (200, 150)), ((200, 400), (200, 350)),
                             ((350, 350), (450, 350))):
            self.click(v, inside)
            self.assertEqual(v.selected_xrefs(), [], inside)
            self.click(v, edge)
            self.assertEqual(len(v.selected_xrefs()), 1, edge)
            v.clear_selection()

    def test_the_outline_tolerance_follows_the_zoom(self):
        v = self.view(new_pdf(blank(1)))
        v.apply_drag_tool(0, "rect", P(100, 100), P(300, 300), False)
        v.clear_selection()
        v.zoom = 1.0
        self.assertIsNone(v.annot_at(0, P(110, 200)))
        v.zoom = 0.25                     # zoomed out: the same few pixels cover more page
        self.assertIsNotNone(v.annot_at(0, P(110, 200)))


# ---- 3, 4 ---------------------------------------------------------------------------------
def words(d):
    p = d.new_page()
    p.draw_rect(R(90, 85, 230, 105), width=0.5)               # a tag box around the words
    p.insert_text((100, 100), "SEE DETAIL 3/A-501", fontsize=11)
    d.new_page()


class LinkOwnership(Base):
    def make(self):
        v = self.view(new_pdf(words))
        v.add_link(0, R(100, 90, 205, 102), ("page", 1, "underline"), text_lines=True)
        v.apply_drag_tool(0, "cloud", P(80, 75), P(240, 115), False)
        cloud = self.annots(v)[-1][0]
        return v, cloud

    def link_rects(self, v):
        return [tuple(round(c) for c in ln["rect"]) for ln in links.read(v.doc[0])]

    def test_a_cloud_around_linked_words_doesnt_take_their_link(self):
        v, cloud = self.make()
        before = self.link_rects(v)
        self.assertEqual(links.read(v.doc[0])[0]["on"], "text")
        v.select_xref(0, cloud)
        v.commit_model(0, v.selection[1], annotations.moved(v.selected_model, P(150, 0)))
        self.assertEqual(self.link_rects(v), before)
        v.select_xref(0, v.selection[1])
        v.delete_selected()
        self.assertEqual(self.link_rects(v), before)

    def test_deleting_a_box_drawn_around_linked_words_keeps_their_link(self):
        v, _cloud = self.make()
        before = self.link_rects(v)
        box = next(it for it in v.content_objects(0).items
                   if it["kind"] == "shape" and it["rect"].width > 100)
        v.select_objects(0, [box])
        v.delete_objects()
        self.assertEqual(self.link_rects(v), before)

    def test_older_links_without_a_record_go_only_with_an_item_their_size(self):
        v, cloud = self.make()
        doc = v.doc
        for ln in links.read(doc[0]):
            doc.xref_set_key(ln["xref"], "KZOn", "null")     # as KanzonasPDF 1.4 made it
        self.assertIsNone(links.read(doc[0])[0]["on"])
        before = self.link_rects(v)
        v.select_xref(0, cloud)
        v.delete_selected()
        self.assertEqual(self.link_rects(v), before)
        # a markup made a link the same size still takes it along
        page = doc[0]
        self.assertEqual(len(links.attached(page, R(100, 90, 205, 102), "markup")), 1)

    def test_remove_link_on_the_words_removes_the_words_link(self):
        v, cloud = self.make()
        v.select_xref(0, cloud)
        with mock.patch.object(DocumentView, "_ask_link",
                               lambda *a, **k: ("uri", "https://cloud.example", "none")):
            v.add_link_to_selection()
        self.assertEqual(links.read(v.doc[0])[-1]["on"], "markup")
        v.remove_link_at(0, P(150, 96))
        left = [ln.get("uri") for ln in v.doc[0].get_links()]
        self.assertEqual(left, ["https://cloud.example"])


class LinkOnMarkup(Base):
    def test_hand_and_ctrl_click_open_a_link_on_a_markup_plain_click_selects(self):
        v = self.view(new_pdf(blank()))
        v.apply_drag_tool(0, "rect", P(100, 100), P(200, 160), False)
        xref = self.annots(v)[-1][0]
        v.select_xref(0, xref)
        v.add_link(0, None, ("page", 1, "none"), rects=[annotations.bounds(v.selected_model)])
        v.clear_selection()
        opened = []
        with mock.patch.object(DocumentView, "follow_link",
                               lambda self, ln: opened.append(ln["page"])):
            v.set_tool("hand")
            self.click(v, (101, 130))
            self.assertEqual(opened, [1])
            v.set_tool("select")
            self.click(v, (101, 130), Qt.ControlModifier)
            self.assertEqual(opened, [1, 1])
            self.click(v, (101, 130))
            self.assertEqual(opened, [1, 1])                    # a plain click selects
            self.assertEqual(v.selected_xrefs(), [xref])


# ---- 5 ------------------------------------------------------------------------------------
class SignWithFormPermission(Base):
    def test_signature_field_and_date_on_a_field_need_only_form_filling(self):
        def build(d):
            protected_form(d)
            d.xref_set_key(d.pdf_catalog(), "AcroForm/SigFlags", "0")
        path = new_pdf(build, encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="owner",
                       user_pw="", permissions=pymupdf.PDF_PERM_PRINT | pymupdf.PDF_PERM_FORM)
        v = self.view(path)
        v._asked_protect = True
        img = QImage(300, 100, QImage.Format_ARGB32)
        img.fill(QColor("#203080"))
        v.set_sig_image("signature", signatures.qimage_to_png(img))
        said = []
        with mock.patch.object(QMessageBox, "information",
                               lambda *a, **k: said.append(a[2])):
            field = next(w.rect for w in v.doc[0].widgets() if w.field_name == "Signature1")
            v.place_signature(0, "signature", field_rect=field)
            self.assertEqual(len(v.doc[0].get_images()), 1)
            v.place_date(0, P(110, 115))                         # in the name field
            self.assertIn(signatures.date_text(), v.doc[0].get_text())
            self.assertEqual(said, [])
            # anywhere else on the page it still changes the page: refused
            v.place_signature(0, "signature", P(400, 600))
            v.place_date(0, P(100, 500))
        self.assertEqual(len(said), 2)
        self.assertEqual(len(v.doc[0].get_images()), 1)


# ---- 6, 8 ---------------------------------------------------------------------------------
def secret(d):
    p = d.new_page()
    p.insert_text((72, 100), "SSN 123-45-6789 for J. Smith", fontsize=12)
    d.new_page()


class Flatten(Base):
    def make(self):
        v = self.view(new_pdf(secret))
        v.apply_text_tool(0, "redact", P(100, 92), P(170, 100))
        v.apply_drag_tool(0, "rect", P(300, 300), P(350, 350), False)
        v.add_link(0, R(72, 300, 160, 312), ("page", 1, "underline"), text_lines=True)
        return v

    def test_flatten_keeps_redaction_marks_that_arent_applied(self):
        for pages in (None, [0]):
            v = self.make()
            v.flatten(pages, widgets=False)
            kinds = [t for _x, t, _r in self.annots(v)]
            self.assertEqual(kinds, [pymupdf.PDF_ANNOT_REDACT], pages)
            self.assertEqual(v.pending_redactions(), 1)
            v.apply_redactions(scrub=False)
            self.assertNotIn("123-45", v.doc[0].get_text())

    def test_flatten_current_page_keeps_links_whole(self):
        v = self.make()
        v.flatten([0], widgets=False)
        ln = links.read(v.doc[0])[0]
        self.assertTrue(ln["group"] and ln["under"] and ln["on"] == "text")
        v.remove_link_at(0, P(100, 306))
        page = v.doc[0]
        self.assertEqual(page.get_links(), [])
        self.assertFalse(any(dr.get("color") and abs(dr["color"][2] - links.BLUE[2]) < 0.02
                             for dr in page.get_drawings()))

    def test_the_window_asks_before_flattening_over_redaction_marks(self):
        w = MainWindow()
        self.addCleanup(lambda: (setattr(w, "_close_confirmed", True), w.close()))
        w.open_file(new_pdf(secret))
        v = w.view()
        v.apply_text_tool(0, "redact", P(100, 92), P(170, 100))
        steps = len(v._undo)
        asked = []

        def answer(button):
            def exec_(box):
                asked.append(box.text())
                box.clickedButton = lambda: next(
                    (b for b in box.buttons() if b.text() == button), None)
                return 0
            return mock.patch.object(QMessageBox, "exec", exec_)
        pick = mock.patch.object(QInputDialog, "getItem", lambda *a, **k: ("All pages", True))
        with pick, answer(None):                               # closed: Cancel
            w.flatten_comments()
        self.assertIn("redaction mark", asked[0])
        self.assertEqual(v.pending_redactions(), 1)
        self.assertEqual(len(v._undo), steps)                  # nothing done
        with pick, answer("Keep them as marks"):
            w.flatten()
        self.assertEqual(v.pending_redactions(), 1)
        self.assertIn("123-45", v.doc[0].get_text())


# ---- 7, 9, 10 -----------------------------------------------------------------------------
class GeneratedText(Base):
    def test_edit_text_isnt_offered_on_measurements_and_stamps(self):
        v = self.view(new_pdf(blank(1)))
        v.set_page_scale([0], measure.scale_from_preset(48), "ft-in", "1/4")
        v.apply_drag_tool(0, "m_length", P(100, 100), P(172, 100), False)
        self.stamp_label("APPROVED")
        v.place_stamp(0, P(300, 300))
        v.apply_drag_tool(0, "cloud", P(100, 400), P(200, 450), False)
        steps = len(v._undo)
        asked = []
        with mock.patch.object(dialogs, "get_text",
                               lambda *a, **k: (asked.append(a[1]), ("RFI 7", True))[1]):
            for x, _t, _r in self.annots(v):
                v.edit_annot_text(0, x)
        self.assertEqual(len(asked), 1)                          # only the cloud asks
        self.assertEqual(len(v._undo), steps + 1)
        self.assertIn("RFI 7", self.contents(v))
        # the right-click menu agrees
        offered = []

        class Menu(QMenu):
            def exec(self, *_a):
                offered.append("Edit text..." in [a.text() for a in self.actions()])
        pw = v.pages[0]
        for _x, t, r in self.annots(v):
            pt = pw.to_screen_pt(P(r.x0 + 1, (r.y0 + r.y1) / 2)) \
                if t != pymupdf.PDF_ANNOT_LINE else pw.to_screen_pt(P(130, 100))
            v.clear_selection()
            with mock.patch("PySide6.QtWidgets.QMenu", Menu):
                pw.mousePressEvent(QMouseEvent(QEvent.MouseButtonPress, pt, pw.mapToGlobal(pt),
                                               Qt.RightButton, Qt.RightButton, Qt.NoModifier))
        self.assertEqual(offered, [False, False, True])

    def test_a_fill_in_stamp_reads_as_its_fields_and_values(self):
        v = self.view(new_pdf(blank(1)))
        self.stamp_label(stamps.FORM_PREFIX + "PO #|Date ordered")
        with mock.patch.object(stamps, "ask_form_values",
                               lambda *a, **k: ["PO-4471", "10/26/2026"]):
            v.place_stamp(0, P(300, 300))
        self.assertEqual(self.contents(v), ["PO # PO-4471, Date ordered 10/26/2026"])

    def test_copies_of_count_markers_count_on(self):
        v = self.view(new_pdf(blank(1)))
        for k in range(3):
            v.place_count(0, P(100 + 40 * k, 100))
        last = max(x for x, _t, _r in self.annots(v))
        v.select_xref(0, last)
        v.duplicate_selected()
        v.select_xref(0, last)
        v.copy()
        with mock.patch.object(v, "paste_target", lambda: (0, P(300, 300))):
            v.paste()
        self.assertEqual(sorted(self.contents(v)),
                         [f"Count 1 #{n}" for n in range(1, 6)])


# ---- 11 -----------------------------------------------------------------------------------
class MarkupsList(Base):
    def test_page_one_first(self):
        from kanzonas.markups_panel import MarkupsPanel

        def build(d):
            for i in range(3):
                d.new_page().add_text_annot((100, 100), f"note on page {i + 1}")
        doc = pymupdf.open(new_pdf(build))
        panel = MarkupsPanel()
        self.addCleanup(panel.deleteLater)
        panel.refresh(doc)
        t = panel.table
        self.assertEqual([t.item(r, 2).text() for r in range(t.rowCount())],
                         ["note on page 1", "note on page 2", "note on page 3"])


# ---- 12 -----------------------------------------------------------------------------------
class SearchAndRedactNotes(Base):
    def test_notes_keep_their_text_with_the_term_redacted(self):
        v = self.view(new_pdf(lambda d: d.new_page().insert_text(
            (72, 100), "Budget for CONFERENCE room", fontsize=11)))
        for text in ("Ask about the CONFERENCE AV budget", "General note"):
            with mock.patch.object(dialogs, "get_text", lambda *a, **k: (text, True)):
                v.apply_point_tool(0, "note", P(400, 300 + len(text)))
        v.search_redact("CONFERENCE")
        v.apply_redactions(scrub=False)
        self.assertEqual(sorted(self.contents(v)),
                         ["Ask about the [redacted] AV budget", "General note"])
        out = os.path.join(tempfile.mkdtemp(), "out.pdf")
        v.save(out)
        with open(out, "rb") as f:
            raw = f.read()
        self.assertNotIn(b"CONFERENCE", raw)
        self.assertIn(b"[redacted] AV budget", raw)


# ---- 13 -----------------------------------------------------------------------------------
class ManyMarkups(Base):
    def make(self, n):
        def build(d):
            p = d.new_page(width=2000, height=2000)
            for i in range(n):
                x, y = 20 + (i % 40) * 48, 20 + (i // 40) * 30 + (i % 3) * 5
                p.add_rect_annot(R(x, y, x + 30, y + 20)).update()
        v = self.view(new_pdf(build))
        v.select_in_box(0, R(-1, -1, 2001, 2001))
        return v

    def test_align_keeps_the_stacking_order_and_undoes_in_one_step(self):
        v = self.make(30)
        page = v.doc[0]
        before = [tuple(a.rect) for a in annotations.each_annot(page)]
        del page
        steps = len(v._undo)
        v.align("top")
        page = v.doc[0]
        box = {a.xref: annotations.bounds(annotations.read(a))
               for a in annotations.each_annot(page)}
        boxes = [box[x] for x in annotations.annot_order(page)]      # the file's own order
        self.assertEqual({round(b.y0, 1) for b in boxes}, {round(boxes[0].y0, 1)})
        # the same stacking order: still left to right, as they were made
        self.assertEqual([round(b.x0) for b in boxes], [round(r[0]) for r in before])
        self.assertEqual(sorted(v.selected_xrefs()),
                         sorted(a.xref for a in annotations.each_annot(page)))
        self.assertEqual(len(v._undo), steps + 1)
        del page
        v.undo()
        self.assertEqual([tuple(r) for _x, _t, r in self.annots(v)], before)

    def test_a_markups_link_follows_it_in_a_batch(self):
        v = self.make(12)
        first = v.selection[1]
        v.select_xref(0, first)
        with mock.patch.object(DocumentView, "_ask_link",
                               lambda *a, **k: ("uri", "https://m.example", "none")):
            v.add_link_to_selection()
        v.select_in_box(0, R(-1, -1, 2001, 2001))
        v.nudge(0, 1, 10)
        r = links.read(v.doc[0])[0]["rect"]
        self.assertAlmostEqual(r.y0, 30, delta=2)

    def test_the_page_is_read_once_for_the_whole_batch(self):
        # each markup used to re-read and rewrite the stacking order, re-read the page's
        # links and be looked up from the start of the page's list (N squared steps)
        v = self.make(40)
        counts = {}

        def counted(name, fn):
            def wrapper(*a, **k):
                counts[name] = counts.get(name, 0) + 1
                return fn(*a, **k)
            return wrapper
        with mock.patch.object(annotations, "annot_order",
                               counted("order", annotations.annot_order)), \
                mock.patch.object(annotations, "set_annot_order",
                                  counted("set order", annotations.set_annot_order)), \
                mock.patch.object(links, "read", counted("links", links.read)), \
                mock.patch.object(pymupdf.Page, "load_annot",
                                  counted("load", pymupdf.Page.load_annot)):
            v.update_selected_props({"stroke": "#00ff00"})
        self.assertLessEqual(counts.get("order", 0), 2)
        self.assertLessEqual(counts.get("set order", 0), 1)
        self.assertLessEqual(counts.get("links", 0), 1)
        self.assertLessEqual(counts.get("load", 0), 3)
        self.assertEqual(len(self.contents(v)), 40)


if __name__ == "__main__":
    unittest.main()
