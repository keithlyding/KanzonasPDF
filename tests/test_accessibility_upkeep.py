"""A tagged document's tags kept in step with its pages after every edit (tag_upkeep.py, run
by DocumentView.modify in the edit's own undo step), and the edits of 1.9 and 1.9.1 on a
tagged document:

- Auto-tag tags the text Add text wrote (its /KZText marked content holding the /P MCID
  sequence, nested); deleting that text takes out the marker, the MCID, its element and its
  ParentTree entry together;
- text added after tagging (Add text, page text pasted, Edit text writing a line anew) is
  tagged; a heading or list item rewritten by Edit text keeps its element (its type); a
  picture moved with Edit objects, also onto another page, keeps its Figure and alt text;
  a picture pasted is a Figure Check accessibility asks a description for;
- markups added after tagging get an Annot element and a StructParent, and leave the tree
  when deleted; pages duplicated, inserted, replaced and deleted keep the tree right;
- Header & footer and Bates numbers on a tagged document are pagination artifacts;
- Apply redactions: the alt text, ActualText, expansion and title of tagged content a mark
  touches are taken out of the file (a mark drawn by hand left "Photo of J. Smith" in it),
  the elements of content wholly redacted leave the tree;
- Check accessibility finds tags out of step with the pages (a file another program
  changed), and its Repair tags puts them right.

After each: tag_upkeep.problems finds nothing (every MCID drawn once and held by one
element, none held that isn't drawn, the ParentTree pointing back, every markup tagged once,
nothing neither tagged nor an artifact), and Undo gives back exactly the document before.
veraPDF's PDF/UA-1 profile passed each kind of edit on the tagged sample with the fixes
applied when this was written (veraPDF 1.28.2); the tests don't need it.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_accessibility_upkeep
"""
import os
import re
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox  # noqa: E402

APP = QApplication.instance() or QApplication([])

from tests.qt_fonts import ensure_font  # noqa: E402

ensure_font()      # (Windows' offscreen Qt has no font: texts measure 0 px)

from kanzonas import accessibility as acc, tag_upkeep  # noqa: E402
from tests.test_accessibility import autotagged, consistent, hand_tagged, sample  # noqa: E402

m = pymupdf.mupdf


def raw(doc):
    """Every object and stream of the document as written (uncompressed)."""
    return doc.tobytes(garbage=3, expand=255, no_new_id=True)


class Upkeep(unittest.TestCase):
    def window(self, doc, tag=True):
        from kanzonas.main_window import MainWindow
        folder = tempfile.mkdtemp()
        path = os.path.join(folder, "a.pdf")
        if tag:
            autotagged(doc)
        doc.save(path)
        w = MainWindow()
        w.show()
        w.open_file(path)
        APP.processEvents()
        self.addCleanup(lambda: (setattr(w, "_close_confirmed", True), w.close()))
        return w, w.view()

    def in_step(self, v):
        self.assertEqual(tag_upkeep.problems(v.doc), [])

    def undoes(self, v, fn):
        """fn() is one undo step: undone, the document as before; redone, as after."""
        from tests.battery_random import canon
        before = canon(v._snapshot())
        fn()
        self.in_step(v)
        after = canon(v._snapshot())
        self.assertNotEqual(before, after)
        v.undo()
        self.assertEqual(canon(v._snapshot()), before)
        v.redo()
        self.assertEqual(canon(v._snapshot()), after)
        self.in_step(v)

    @staticmethod
    def order(v, i):
        return [(it["type"], it["text"]) for it in acc.page_order(v.doc, i)]

    @staticmethod
    def word(v, i, text):
        return next(w for w in v.doc[i].get_text("words") if w[4] == text)

    def edit_word(self, v, i, text, new):
        wd = self.word(v, i, text)
        v.edit_text_at(i, pymupdf.Point((wd[0] + wd[2]) / 2, (wd[1] + wd[3]) / 2))
        ed = v._inline
        ed.text.setPlainText(ed.text.toPlainText().replace(text, new))
        ed.commit()

    def add_text(self, v, i, pt, text):
        v.add_text_at(i, pymupdf.Point(pt))
        ed = v._inline
        ed.text.setPlainText(text)
        ed.commit()

    # ---- Add text and Auto-tag
    def test_auto_tag_tags_added_text_inside_its_block(self):
        w, v = self.window(sample(1), tag=False)
        self.add_text(v, 0, (300, 230), "Words added here")
        from kanzonas import accessibility_ui as ui

        def accept(dlg):
            return QDialog.Accepted
        with mock.patch.object(ui.AutoTagDialog, "exec", accept), \
                mock.patch.object(QMessageBox, "information", lambda *a, **k: None):
            self.assertTrue(ui.auto_tag(w, v))
        data = v.doc[0].read_contents()
        # /KZText <<...>> BDC ... /P <</MCID n>> BDC ... EMC ... EMC
        self.assertRegex(data, rb"(?s)/KZText\s*<<[^>]*>>\s*BDC(?:(?!EMC).)*?/P <</MCID \d+>> BDC"
                               rb"(?:(?!BDC).)*?EMC\s*(?:ET\s*Q\s*)*EMC", )
        consistent(self, v.doc)
        self.in_step(v)
        self.assertIn(("P", "Words added here"), self.order(v, 0))
        # its words deleted: the marker, the MCID, its element and its entry go together
        self.assertTrue(v._added_blocks(0))
        wd = self.word(v, 0, "Words")
        self.undoes(v, lambda: v.delete_text_at(0, pymupdf.Point(
            (wd[0] + wd[2]) / 2, (wd[1] + wd[3]) / 2)))
        self.assertFalse(v._added_blocks(0))
        self.assertNotIn(b"KZText", v.doc[0].read_contents())
        self.assertNotIn("Words added here", " ".join(t for _ty, t in self.order(v, 0)))

    def test_text_added_after_tagging_is_tagged_in_reading_order(self):
        w, v = self.window(sample(1))
        self.undoes(v, lambda: self.add_text(v, 0, (300, 230), "Hello added words"))
        order = self.order(v, 0)
        self.assertIn(("P", "Hello added words"), order)
        # where the page shows it: after the list, before the picture below it
        k = order.index(("P", "Hello added words"))
        self.assertEqual(order[k - 1][0], "L")
        self.assertEqual(order[k + 1][0], "Figure")
        self.assertEqual([p for p in acc.check(v.doc) if p.kind == "content"], [])

    # ---- Edit text
    def test_edit_text_keeps_the_elements(self):
        w, v = self.window(sample(1))
        self.undoes(v, lambda: self.edit_word(v, 0, "Section", "Chapter"))
        self.assertIn(("H2", "Chapter 1"), self.order(v, 0))
        self.undoes(v, lambda: self.edit_word(v, 0, "Second", "Next"))
        lst = next(it for it in acc.page_order(v.doc, 0) if it["type"] == "L")
        self.assertIn("Next point", lst["text"])
        self.assertEqual([n.type for n in acc.Tree(v.doc).nodes].count("LBody"), 3)
        # a word made bold (its own run, in the line's bold font)
        from PySide6.QtGui import QTextCursor
        wd = self.word(v, 0, "screen")

        def bold():
            v.edit_text_at(0, pymupdf.Point((wd[0] + wd[2]) / 2, (wd[1] + wd[3]) / 2))
            ed = v._inline
            a = ed.text.toPlainText().index("screen")
            cur = ed.text.textCursor()
            cur.setPosition(a)
            cur.setPosition(a + 6, QTextCursor.KeepAnchor)
            ed.text.setTextCursor(cur)
            ed.toggle("bold")
            ed.commit()
        self.undoes(v, bold)
        self.assertEqual(sum(1 for t, _x in self.order(v, 0) if t == "P"), 3)

    def test_replace_text_on_several_pages(self):
        # (each page's heading rewritten stays that page's heading: an element emptied on
        # one page never takes text written on another one edited in the same step; random
        # battery seed 23, --tagged)
        w, v = self.window(sample(3))
        self.undoes(v, lambda: v.replace_text("Section", "Chapter"))
        for i in range(3):
            self.assertIn(("H2", "Chapter %d" % (i + 1)), self.order(v, i))

    def test_an_added_block_edited_again(self):
        w, v = self.window(sample(1))
        self.add_text(v, 0, (300, 230), "One block of words")
        blk = v._added_blocks(0)[0]
        r, _ln = blk.lines[0]

        def edit():
            v.edit_text_at(0, pymupdf.Point(r.x0 + 1, (r.y0 + r.y1) / 2))
            ed = v._inline
            ed.text.setPlainText("One block\nof other words")
            ed.commit()
        self.undoes(v, edit)
        texts = [t for ty, t in self.order(v, 0) if ty == "P"]
        self.assertIn("One block of other words", texts)

    # ---- Edit objects, CAD mode, the object clipboard
    def test_a_picture_moved_keeps_its_figure_and_alt_text(self):
        w, v = self.window(sample(2))
        fig = acc.figures(v.doc)[0]
        v.modify(lambda: acc.set_alt(v.doc, fig["num"], "A red box"), [])

        def pictures(i):
            return [it for it in v.content_objects(i).items if it["kind"] == "picture"]

        def move():
            v.select_objects(0, pictures(0))
            v.move_objects(v.selected_objects_rect() + (30, 10, 30, 10))
            v.clear_object_selection()
        self.undoes(v, move)
        self.assertIn((fig["num"], "A red box", 0),
                      [(f["num"], f["alt"], f["page"]) for f in acc.figures(v.doc)])

        def across():
            w.set_tool("editobjects")
            v.select_objects(0, pictures(0))
            v.transfer_selection(1, pymupdf.Point(0, 200))
            v.clear_object_selection()
            w.set_tool("hand")
        self.undoes(v, across)
        self.assertIn((fig["num"], "A red box", 1),
                      [(f["num"], f["alt"], f["page"]) for f in acc.figures(v.doc)])
        self.assertEqual([t for t, _x in self.order(v, 1)].count("Figure"), 2)
        self.assertNotIn("Figure", [t for t, _x in self.order(v, 0)])

    def test_pasted_pictures_and_text_are_tagged(self):
        w, v = self.window(sample(2))
        w.set_tool("editobjects")
        pics = [it for it in v.content_objects(1).items if it["kind"] == "picture"]
        v.select_objects(1, pics)
        self.assertEqual(v.copy(), "pagecontent")

        def paste(j, pt):
            with mock.patch.object(v, "paste_target", lambda: (j, pymupdf.Point(pt))):
                v.paste()
        before = len(acc.figures(v.doc))
        self.undoes(v, lambda: paste(0, (400, 600)))
        self.assertEqual(len(acc.figures(v.doc)), before + 1)
        self.assertTrue(any("figure has no alternate text" in p.text
                            for p in acc.check(v.doc) if p.page == 0))
        v.clear_object_selection()
        v.select_objects(1, v.text_objects(1)[:1])
        self.assertEqual(v.copy(), "pagetext")
        self.undoes(v, lambda: paste(1, (300, 650)))
        v.clear_object_selection()
        w.set_tool("hand")
        self.assertEqual([p for p in acc.check(v.doc) if p.kind == "content"], [])

    # ---- markups
    def test_markups_added_and_deleted_after_tagging(self):
        w, v = self.window(sample(1))

        def add():
            v.doc[0].add_rect_annot(pymupdf.Rect(400, 100, 450, 150))
        self.undoes(v, lambda: v.modify(add, [0]))
        x = next(a.xref for a in v.doc[0].annots() if a.type[1] == "Square")
        node = acc.Tree(v.doc).annot_node(x)
        self.assertIsNotNone(node)
        self.assertEqual(node.type, "Annot")
        self.assertIn(x, node.objrs)
        self.assertNotIn("isn't tagged as an Annot", " ".join(p.text for p in acc.check(v.doc)))

        def delete():
            p = v.doc[0]
            p.delete_annot(p.load_annot(x))
        self.undoes(v, lambda: v.modify(delete, [0]))
        self.assertNotIn("Annot", [n.type for n in acc.Tree(v.doc).nodes])

    # ---- pages
    def test_pages_duplicated_inserted_replaced_deleted(self):
        from tests.battery_random import revision
        w, v = self.window(sample(2))
        v.modify(lambda: v.doc[0].add_rect_annot(pymupdf.Rect(400, 100, 450, 150)), [0])
        fig = next(f for f in acc.figures(v.doc) if f["page"] == 0)
        v.modify(lambda: acc.set_alt(v.doc, fig["num"], "A red box"), [])
        first = self.order(v, 0)
        self.undoes(v, lambda: v.duplicate_pages([0]))
        # (the copy gets copies of the page's own tags: its headings, list, table, figure
        # with its description, link, markup; in the same reading order)
        self.assertEqual(self.order(v, 1), first)
        self.assertIn(("A red box", 1), [(f["alt"], f["page"]) for f in acc.figures(v.doc)])
        t = acc.Tree(v.doc)
        for x, _t, _id in v.doc[1].annot_xrefs():
            self.assertEqual(t.annot_node(x).page, 1)
        self.assertNotEqual(v.doc.xref_get_key(v.doc.page_xref(0), "StructParents"),
                            v.doc.xref_get_key(v.doc.page_xref(1), "StructParents"))
        self.undoes(v, lambda: v.insert_blank(1))
        path = os.path.join(tempfile.mkdtemp(), "rev.pdf")
        revision(path)
        src = pymupdf.open(path)
        self.undoes(v, lambda: v.replace_pages(src, [(2, 0)]))
        self.assertIn("Revision B sheet 1", " ".join(t for _ty, t in self.order(v, 2)))
        self.undoes(v, lambda: v.delete_page(0))

    def test_pages_from_a_tagged_file(self):
        w, v = self.window(sample(1))
        other = sample(1)
        autotagged(other)
        self.undoes(v, lambda: v.modify(lambda: v.doc.insert_pdf(other), structural=True,
                                        changed=[1]))
        self.assertTrue(self.order(v, 1))

    # ---- Header & footer
    def test_header_footer_and_bates_are_pagination_artifacts(self):
        spec = {"texts": {("footer", "right"): "AB{bates}", ("header", "center"): "Page {page}"},
                "size": 9, "pages": [0], "bates_prefix": "X", "bates_start": 1,
                "bates_digits": 5}
        w, v = self.window(sample(1))
        before = len(acc.Tree(v.doc).nodes)
        self.undoes(v, lambda: v.add_header_footer(dict(spec)))
        data = v.doc[0].read_contents()
        self.assertIn(b"/Artifact <</Type /Pagination /Subtype /Header>> BDC", data)
        self.assertIn(b"/Artifact <</Type /Pagination /Subtype /Footer>> BDC", data)
        self.assertEqual(len(acc.Tree(v.doc).nodes), before)
        self.assertNotIn("X00001", " ".join(t for _ty, t in self.order(v, 0)))
        # (an untagged document's page gets no marking)
        w2, v2 = self.window(sample(1), tag=False)
        v2.add_header_footer(dict(spec))
        self.assertNotIn(b"/Artifact", v2.doc[0].read_contents())

    # ---- redaction
    def test_redaction_takes_out_the_alt_text_of_what_it_removes(self):
        w, v = self.window(sample(2))
        figs = acc.figures(v.doc)
        alts = ["Photo of J. Smith", "Photo of A. Jones"]
        for f, alt in zip(figs, alts):
            v.modify(lambda f=f, alt=alt: acc.set_alt(v.doc, f["num"], alt), [])
        # a heading with an expansion and ActualText of its own
        h1 = next(n for n in acc.Tree(v.doc).nodes if n.type == "H1")
        v.modify(lambda: (v.doc.xref_set_key(h1.num, "ActualText", "(Secret Plans)"),
                          v.doc.xref_set_key(h1.num, "E", "(Secret Plans Expanded)")), [])
        boxes = {it["type"]: it["box"] for it in acc.page_order(v.doc, 0)}
        fig0 = boxes["Figure"]
        h1_box = boxes["H1"]
        # page 1: the whole picture and the heading under marks drawn by hand; page 2: a
        # corner of the picture
        v.mark_redactions(0, [fig0 + (-2, -2, 2, 2), h1_box + (-1, -1, 1, 1)])
        f1 = next(it["box"] for it in acc.page_order(v.doc, 1) if it["type"] == "Figure")
        v.mark_redactions(1, [pymupdf.Rect(f1.x0 + 4, f1.y0 + 4, f1.x0 + 20, f1.y0 + 20)])
        self.assertIn(b"J. Smith", raw(v.doc))
        with mock.patch.object(QMessageBox, "information", lambda *a, **k: None):
            self.undoes(v, lambda: v.apply_redactions(scrub=False))
        data = raw(v.doc)
        for secret in (b"J. Smith", b"A. Jones", b"Secret Plans"):
            self.assertNotIn(secret, data)
        types = [(n.type, n.page) for n in acc.Tree(v.doc).nodes]
        self.assertNotIn(("Figure", 0), types)          # (wholly redacted: gone)
        self.assertNotIn(("H1", 0), types)
        self.assertIn(("Figure", 1), types)             # (a corner: there, undescribed)
        self.assertTrue(any("figure has no alternate text" in p.text
                            for p in acc.check(v.doc) if p.page == 1))

    def test_redaction_with_the_clean_up_and_selected_redactions(self):
        w, v = self.window(sample(2))
        for f in acc.figures(v.doc):
            v.modify(lambda f=f: acc.set_alt(v.doc, f["num"], "Photo of J. Smith"), [])
        for i in range(2):
            box = next(it["box"] for it in acc.page_order(v.doc, i) if it["type"] == "Figure")
            v.mark_redactions(i, [box])
        with mock.patch.object(QMessageBox, "information", lambda *a, **k: None):
            v.select_xref(1, next(a.xref for a in v.doc[1].annots()
                                  if a.type[0] == pymupdf.PDF_ANNOT_REDACT))
            self.assertEqual(v.apply_selected_redactions(), 1)
            self.in_step(v)
            self.assertEqual(len(acc.figures(v.doc)), 1)
            v.apply_redactions(scrub=True)
        self.in_step(v)
        self.assertNotIn(b"J. Smith", raw(v.doc))
        self.assertEqual(acc.figures(v.doc), [])

    def test_sanitize_hidden_text(self):
        w, v = self.window(sample(1))
        page = v.doc[0]
        # invisible text (as OCR leaves) tagged with ActualText of its own

        def hidden():
            pg = v.doc[0]
            pg.insert_text((72, 700), "Hidden words", render_mode=3)
        v.modify(hidden, [0])
        el = next(n for n in acc.Tree(v.doc).nodes if n.type == "P" and
                  any("Hidden" in t for t in [acc.marked_content(v.doc, 0).get(mc, ("", ""))[1]
                                              for _p, mc in n.mcids]))
        v.modify(lambda: v.doc.xref_set_key(el.num, "ActualText", "(Hidden secret)"), [])
        del page
        v.sanitize({"hidden_text": True})
        self.in_step(v)
        self.assertNotIn(b"Hidden secret", raw(v.doc))

    # ---- Check accessibility and Repair tags
    def test_check_finds_tags_out_of_step_and_repairs_them(self):
        d = hand_tagged()
        p = d[0]
        x = p.get_contents()[0]
        data = d.xref_stream(x)
        # another program: the figure's content deleted, a paragraph's MCID drawn twice,
        # text drawn in no marked content
        data = re.sub(rb"/Figure <</MCID 3>> BDC.*?EMC\n", b"", data, flags=re.S)
        data += b"/P <</MCID 1>> BDC BT /F1 11 Tf 72 640 Td (Again) Tj ET EMC\n"
        data += b"BT /F1 11 Tf 72 620 Td (Loose words) Tj ET\n"
        d.update_stream(x, data)
        n_before = len(acc.page_order(d, 0))
        found = [p for p in acc.check(d) if p.kind in ("structure", "content")]
        self.assertTrue(found)
        self.assertEqual({p.fix for p in found}, {"repair"})
        w, v = self.window(d, tag=False)
        from kanzonas import accessibility_ui as ui
        self.assertTrue(tag_upkeep.problems(v.doc))
        self.undoes(v, lambda: ui.run_fix(w, w, v, "repair"))
        self.assertEqual([p for p in acc.check(v.doc) if p.kind in ("structure", "content")],
                         [])
        # (the loose words a paragraph of their own; the figure gone with its content)
        self.assertEqual([t for t, _x in self.order(v, 0)], ["H1", "P", "P"])
        self.assertEqual(n_before, 3)

    # ---- the engine on its own
    def test_an_mcid_copied_gets_a_number_of_its_own(self):
        d = sample(1)
        autotagged(d)
        p = d[0]
        data = p.read_contents()
        mo = re.search(rb"/H1 <</MCID (\d+)>> BDC.*?EMC", data, re.S)
        from kanzonas import page_objects
        page_objects._set_contents(p, data + b"\nq 1 0 0 1 0 -30 cm BT /hebo 24 Tf 72 702 Tm "
                                   + mo.group(0) + b" ET Q\n")
        self.assertTrue(tag_upkeep.problems(d))
        tag_upkeep.refresh(d, [0])
        self.assertEqual(tag_upkeep.problems(d), [])
        h1 = next(n for n in acc.Tree(d).nodes if n.type == "H1")
        self.assertEqual(len(h1.mcids), 2)
        # nothing to do: nothing changes
        before = raw(d)
        self.assertEqual(tag_upkeep.refresh(d, [0]), set())
        tag_upkeep.refresh(d, None, structural=True)
        self.assertEqual(raw(d), before)

    def test_untagged_documents_are_left_alone(self):
        d = sample(1)
        before = raw(d)
        self.assertEqual(tag_upkeep.refresh(d, [0]), set())
        self.assertEqual(raw(d), before)
        self.assertEqual(tag_upkeep.problems(d), [])


if __name__ == "__main__":
    unittest.main()
