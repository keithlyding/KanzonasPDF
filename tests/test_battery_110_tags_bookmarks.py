"""What the 1.10 break-it battery found in accessibility (tags kept in step with the edits,
Check accessibility) and bookmarks, fixed:

- a parent tree whose node lists itself among its /Kids (twice): Check accessibility and
  every edit of the document never finished (each path to the node was read again: 2^32);
- Save as PDF/A on a file whose attachments' name tree lists a node among its own kids
  (or a layer order array inside itself) never finished, its memory growing;
- a structure tree thousands of elements deep, one inside the other: an edit's tags were
  left out of step (the tags were walked recursing, which ran out of stack and the edit
  went on without them) and Reading order failed;
- content tagged inside a form XObject (the form's own MCIDs, its /StructParents, MCRs
  with /Stm, as producers tag forms): the first edit that wrote the parent tree took out
  the form's entry (only pages and annotations were counted as its users), and every edit
  of its page wrapped the form's drawing in a new P of the page's (tagged twice);
- Apply redactions on such a form: MuPDF draws a redacted copy of the form and leaves the
  original in the file; the MCR still pointed at the original, so the words redacted were
  in the saved file (also with the clean-up), and the element's alternate text stayed;
- Insert table of contents on a tagged document: each title a P, the page numbers one P
  together, each link a Link holding no words, the leaders read aloud, and no link
  described (veraPDF's PDF/UA-1 check failed on 7.18.5-2 and 7.18.1-2 where it passed
  before): now a TOC of TOCI, each a Link with the entry's words, page number and link,
  the leaders an artifact, each link described (also on an untagged document);
- Auto-tag on a document whose tags were taken out but whose pages still have their
  marked content (MCIDs; as some tools leave them): those pages were "left as they were",
  their MCIDs in no element: the document came out of Auto-tag with its tags out of step
  (Check accessibility: "MCID 0 is in no element" on every page). Now tagged by that
  marking;
- bookmarks nested a thousand levels deep (PyMuPDF reads and writes the outline
  recursing): the Bookmarks panel stayed empty and Delete pages failed ("maximum
  recursion depth exceeded"); 100,000 bookmarks took 26 s to read when the file opened and
  32 s to write (a list searched for each): now 3.6 s and 3.7 s;
- a note (or any markup with a pop-up) added to a tagged document that passed veraPDF's
  PDF/UA-1 check made it fail 7.18.1-1 and 7.18.1-2: the pop-up wasn't tagged, nor
  described (veraPDF 1.28.2's rules exempt only Widget, PrinterMark and Link annotations,
  hidden ones and those outside the crop box). Now the pop-up is in its markup's Annot
  element, its Contents the markup's (also from Auto-tag, and kept the same when the
  note's text changes); checked with veraPDF 1.28.2: passes again;
- every edit of a tagged document read its whole structure tree again (a 500-page document's
  14,500 elements: a markup 0.37 s instead of 0.04, Add text 0.24 s instead of 0.004): the
  tree is kept between edits (tag_upkeep.kept_tree), read again only when an undo, redo,
  edit taken back or another tree made it old, or one of its elements is another object
  (xref_set_key, update_object); a markup now 0.056 s, Add text 0.05 s;
- Delete pages moved the bookmarks of a deleted page one by one, each reading the whole
  outline again (set_toc_item): 1,000 of 3,000 bookmarks took 10 s;
- Check accessibility's "long document without bookmarks" offered no fix: now Make
  bookmarks (from the tags' headings on a tagged document, else from the headings' look).

Each test failed before its fix.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_battery_110_tags_bookmarks
"""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import accessibility as acc, tag_upkeep  # noqa: E402
from kanzonas.document_view import DocumentView  # noqa: E402

m = pymupdf.mupdf


def _font(d):
    x = d.get_new_xref()
    d.update_object(x, "<</Type /Font /Subtype /Type1 /BaseFont /Helvetica "
                       "/Encoding /WinAnsiEncoding>>")
    return x


def tagged(content, elems, nums, resources="", next_key=1, kids=None):
    """A one-page tagged document drawing content (bytes): elems {name: dictionary source,
    "{name}" for references, "{pg}" the page, "{root}" the tree's root}, nums the parent
    tree's /Nums source, the Document element holding kids (names; None: all elems)."""
    d = pymupdf.open()
    p = d.new_page(width=400, height=400)
    font = _font(d)
    names = {"pg": p.xref, "font": font}
    for n in ["root", "doc", "pt"] + list(elems):
        names[n] = d.get_new_xref()
        d.update_object(names[n], "<<>>")
    ref = {k: "%d 0 R" % v for k, v in names.items()}
    for n, src in elems.items():
        d.update_object(names[n], src.format(**ref))
    kids = list(elems) if kids is None else kids
    d.update_object(names["doc"], "<</Type /StructElem /S /Document /P %s /K [%s]>>" % (
        ref["root"], " ".join(ref[k] for k in kids)))
    d.update_object(names["pt"], "<</Nums [%s]>>" % nums.format(**ref))
    d.update_object(names["root"], "<</Type /StructTreeRoot /K %s /ParentTree %s "
                                   "/ParentTreeNextKey %d>>" % (ref["doc"], ref["pt"],
                                                                next_key))
    d.xref_set_key(p.xref, "Resources", "<</Font <</F1 %d 0 R>> %s>>" % (
        font, resources.format(**ref)))
    c = d.get_new_xref()
    d.update_object(c, "<<>>")
    d.update_stream(c, content)
    d.xref_set_key(p.xref, "Contents", "%d 0 R" % c)
    d.xref_set_key(p.xref, "StructParents", "0")
    d.xref_set_key(d.pdf_catalog(), "StructTreeRoot", ref["root"])
    d.xref_set_key(d.pdf_catalog(), "MarkInfo", "<</Marked true>>")
    return d, names


SIMPLE = (b"/H1 <</MCID 0>> BDC BT /F1 20 Tf 30 350 Td (Title) Tj ET EMC\n"
          b"/P <</MCID 1>> BDC BT /F1 11 Tf 30 320 Td (Body words) Tj ET EMC\n")


def simple(nums="0 [{h1} {p}]"):
    return tagged(SIMPLE, {"h1": "<</Type /StructElem /S /H1 /P {doc} /Pg {pg} /K 0>>",
                           "p": "<</Type /StructElem /S /P /P {doc} /Pg {pg} /K 1>>"}, nums)


def with_form(alt="(Photo of J. Smith)", wrapped=False):
    """A page drawing a form whose text is tagged inside it (MCID 0 of the form, its
    StructParents 1, an MCR with /Stm), as producers tag forms; wrapped: the form's Do is
    inside an MCID of the page's too."""
    form = (b"/P <</MCID 0>> BDC BT /F1 12 Tf 30 200 Td (Confidential words) Tj ET EMC")
    do = b"/P <</MCID 2>> BDC q /Fm1 Do Q EMC\n" if wrapped else b"q /Fm1 Do Q\n"
    d, n = tagged(
        SIMPLE + do,
        {"h1": "<</Type /StructElem /S /H1 /P {doc} /Pg {pg} /K 0>>",
         "p": "<</Type /StructElem /S /P /P {doc} /Pg {pg} /K 1>>",
         "fp": "<</Type /StructElem /S /Figure /P {doc} /Pg {pg} /Alt %s /K [%s"
               "<</Type /MCR /MCID 0 /Stm {fm} /Pg {pg}>>]>>" % (alt, "2 " if wrapped
                                                                  else ""),
         "fm": "<<>>"},
        "0 [{h1} {p}%s] 1 [{fp}]" % (" {fp}" if wrapped else ""),
        resources="/XObject <</Fm1 {fm}>>", next_key=2, kids=["h1", "p", "fp"])
    fm = n["fm"]
    d.update_object(fm, "<</Type /XObject /Subtype /Form /BBox [0 0 400 400] "
                        "/Resources <</Font <</F1 %d 0 R>>>> /StructParents 1>>" % n["font"])
    d.update_stream(fm, form)
    return d, n


def raw(doc):
    return doc.tobytes(garbage=1, expand=255)


class Case(unittest.TestCase):
    def view(self, d):
        path = os.path.join(tempfile.mkdtemp(), "battery110.pdf")
        d.save(path)
        v = DocumentView(path)
        v.resize(900, 1100)
        v.show()
        APP.processEvents()
        self.addCleanup(lambda: v.doc.is_closed or v.close_doc())
        return v

    def quiet(self):
        for name in ("information", "warning"):
            p = mock.patch.object(QMessageBox, name, lambda *a, **k: None)
            p.start()
            self.addCleanup(p.stop)


class Robustness(Case):
    def test_a_parent_tree_listing_itself_is_read_once(self):
        d, n = simple()
        d.xref_set_key(n["pt"], "Kids", "[%d 0 R %d 0 R]" % (n["pt"], n["pt"]))
        d = pymupdf.open("pdf", d.tobytes())
        nums = tag_upkeep.number_tree(m.pdf_load_object(tag_upkeep._pdf(d), n["pt"]))
        self.assertEqual(sorted(nums), [0])
        self.assertEqual(tag_upkeep.problems(d), [])
        self.assertTrue(acc.check(d))
        d[0].add_text_annot((200, 200), "note")
        tag_upkeep.refresh(d, [0])
        self.assertEqual(tag_upkeep.problems(d), [])

    def test_save_as_pdfa_reads_a_name_tree_listing_itself_once(self):
        from kanzonas import pdfa
        d = pymupdf.open()
        d.new_page()
        d.embfile_add("a.txt", b"hello")
        tree = m.pdf_dict_getp(m.pdf_dict_gets(m.pdf_trailer(tag_upkeep._pdf(d)), "Root"),
                               "Names/EmbeddedFiles")
        x = d.get_new_xref()
        d.update_object(x, "<<>>")
        d.xref_set_key(x, "Kids", "[%d 0 R %d 0 R]" % (x, x))
        kids = m.pdf_new_array(tag_upkeep._pdf(d), 1)
        m.pdf_array_push(kids, m.pdf_new_indirect(tag_upkeep._pdf(d), x, 0))
        m.pdf_dict_puts(m.pdf_resolve_indirect(tree), "Kids", kids)
        self.assertEqual(len(pdfa._name_tree_entries(m.pdf_resolve_indirect(tree))), 1)

    def test_a_tree_thousands_of_elements_deep(self):
        d, n = simple()
        depth = 3000
        xs = [d.get_new_xref() for _ in range(depth)]
        for k, x in enumerate(xs):
            parent = n["doc"] if k == 0 else xs[k - 1]
            kid = "%d 0 R" % xs[k + 1] if k + 1 < depth else "[0 1]"
            d.update_object(x, "<</Type /StructElem /S /%s /P %d 0 R /Pg %d 0 R /K %s>>" % (
                "Span" if k + 1 < depth else "P", parent, n["pg"], kid))
        d.xref_set_key(n["doc"], "K", "[%d 0 R]" % xs[0])
        d.xref_set_key(n["pt"], "Nums", "[0 [%d 0 R %d 0 R]]" % (xs[-1], xs[-1]))
        self.assertEqual(tag_upkeep.problems(d), [])
        self.assertEqual([it["type"] for it in acc.page_order(d, 0)], ["Span"])
        # text added: tagged, the tags in step
        d[0].insert_text((30, 380), "Added words", fontname="helv")
        self.assertEqual(tag_upkeep.refresh(d, [0]), {0})
        self.assertEqual(tag_upkeep.problems(d), [])
        # the page copied: its tags copied (as deep as they are)
        d.fullcopy_page(0)
        tag_upkeep.refresh(d, None, True, [1])
        self.assertEqual(tag_upkeep.problems(d), [])
        self.assertEqual(len([e for e in tag_upkeep.Tree(d).els if e.type == "Span"]),
                         2 * (depth - 1))


class TaggedForms(Case):
    def test_an_edit_keeps_the_form_entry_of_the_parent_tree(self):
        d, n = with_form()
        self.assertEqual(tag_upkeep.problems(d), [])
        v = self.view(d)
        v.modify(lambda: v.doc[0].add_text_annot((350, 50), "A note"), [0])
        self.assertEqual(tag_upkeep.problems(v.doc), [])
        nums = tag_upkeep.number_tree(m.pdf_dict_gets(tag_upkeep.Tree(v.doc).root,
                                                      "ParentTree"))
        self.assertEqual(m.pdf_to_num(m.pdf_array_get(m.pdf_resolve_indirect(nums[1]), 0)),
                         n["fp"])
        # the form isn't wrapped in a P of the page's: its content is tagged once
        self.assertEqual(v.doc[0].read_contents().count(b"/MCID"), 2)
        self.assertEqual(sorted(e.type for e in tag_upkeep.Tree(v.doc).els),
                         ["Annot", "Document", "Figure", "H1", "P"])

    def test_redaction_of_content_tagged_inside_a_form(self):
        self.quiet()
        for scrub in (False, True):
            for wrapped in (False, True):
                d, n = with_form(wrapped=wrapped)
                v = self.view(d)
                # the whole form's text under a mark: none of it is left in the file
                v.mark_redactions(0, [pymupdf.Rect(0, 185, 400, 210)])
                v.apply_redactions(scrub=scrub)
                data = raw(v.doc)
                self.assertNotIn(b"Confidential", data, (scrub, wrapped))
                self.assertNotIn(b"J. Smith", data, (scrub, wrapped))
                self.assertEqual(tag_upkeep.problems(v.doc), [])
                figs = [e for e in tag_upkeep.Tree(v.doc).els if e.type == "Figure"]
                # (its content in the form gone: out of the tree, unless the page's own
                # MCID around the form keeps it, undescribed)
                self.assertEqual(len(figs), int(wrapped))
                self.assertFalse(any(e.stms for e in figs))
                v.close_doc()

    def test_part_of_a_form_redacted_keeps_its_tag_on_the_copy(self):
        self.quiet()
        d, n = with_form()
        v = self.view(d)
        v.mark_redactions(0, [pymupdf.Rect(0, 185, 70, 210)])
        v.apply_redactions(scrub=False)
        data = raw(v.doc)
        self.assertNotIn(b"Confidential", data)
        self.assertNotIn(b"J. Smith", data)               # (it described what's redacted)
        self.assertIn(b"words", data)
        tree = tag_upkeep.Tree(v.doc)
        fig = next(e for e in tree.els if e.type == "Figure")
        drawn = tag_upkeep.PageState(v.doc[0]).r.form_boxes
        self.assertEqual(len(fig.stms), 1)
        self.assertIn(fig.stms[0][0], drawn)              # (the copy the page draws)
        self.assertEqual(tag_upkeep.problems(v.doc), [])


class AutoTagAndCheck(Case):
    def test_auto_tag_on_pages_marked_by_a_tagger_before(self):
        from kanzonas import autotag
        d, n = simple()
        d.xref_set_key(d.pdf_catalog(), "StructTreeRoot", "null")     # (taken out)
        d = pymupdf.open("pdf", d.tobytes(garbage=1))
        self.assertFalse(tag_upkeep.is_tagged(d))
        plans = autotag.make_plans(d)
        autotag.apply(d, plans)
        self.assertEqual(tag_upkeep.problems(d), [])
        self.assertEqual([it["type"] for it in acc.page_order(d, 0)], ["H1", "P"])
        self.assertEqual([i for i, _t in autotag.notes(plans)], [0])

    def test_check_offers_to_make_bookmarks_for_a_long_document(self):
        from kanzonas import accessibility_ui, bookmarks_ui
        d = pymupdf.open()
        for i in range(acc.LONG_DOCUMENT + 1):
            d.new_page().insert_text((72, 72), "Page %d" % (i + 1))
        p = next(p for p in acc.check(d) if "no bookmarks" in p.text)
        self.assertEqual(p.fix, "bookmarks")
        self.assertIn("bookmarks", acc.fix_labels())
        v = self.view(d)
        window = mock.Mock()
        window.view.return_value = v
        with mock.patch.object(bookmarks_ui, "make_bookmarks") as make:
            accessibility_ui.run_fix(None, window, v, p.fix)
        make.assert_called_once_with(window, "headings")


class Outlines(Case):
    def deep(self, levels):
        d = pymupdf.open()
        for i in range(3):
            d.new_page().insert_text((72, 72), "Page %d" % (i + 1))
        xs = [d.get_new_xref() for _ in range(levels)]
        top = d.get_new_xref()
        d.update_object(top, "<</Type /Outlines /First %d 0 R /Last %d 0 R /Count 1>>" % (
            xs[0], xs[0]))
        for k, x in enumerate(xs):
            kid = " /First %d 0 R /Last %d 0 R /Count 1" % (xs[k + 1], xs[k + 1]) \
                if k + 1 < levels else ""
            d.update_object(x, "<</Title (Level %d) /Parent %d 0 R /Dest [%d 0 R /Fit]%s>>" % (
                k + 1, top if k == 0 else xs[k - 1], d[k % 3].xref, kid))
        d.xref_set_key(d.pdf_catalog(), "Outlines", "%d 0 R" % top)
        return d

    def test_bookmarks_nested_deep_are_read_moved_and_written(self):
        v = self.view(self.deep(1500))
        toc = v.doc.get_toc(False)
        self.assertEqual(len(toc), 1500)
        self.assertEqual(toc[-1][:2], [1500, "Level 1500"])
        self.assertTrue(v.delete_pages([1]))
        self.assertEqual(v.doc.page_count, 2)
        self.assertEqual(len(v.doc.get_toc()), 1500)
        v.undo()
        self.assertEqual(v.doc.page_count, 3)
        v.set_toc(v.doc.get_toc(False)[:10])
        self.assertEqual(len(v.doc.get_toc()), 10)

    def test_the_outline_read_as_pymupdf_reads_it(self):
        from kanzonas import bookmarks_auto as BA
        d = pymupdf.open()
        for i in range(20):
            d.new_page()
        toc = []
        for i in range(2500):
            e = {"kind": pymupdf.LINK_GOTO, "page": i % 20, "to": pymupdf.Point(0, i % 700)}
            if i % 7 == 0:
                e["bold"] = True
            if i % 5 == 0:
                e["color"] = (1, 0, 0)
            if i % 11 == 0:
                e["italic"] = True
            toc.append([[1, 2, 3, 3, 2][i % 5] if i else 1, "Mark %d" % i, i % 20 + 1, e])
        d.set_toc(toc)
        d = pymupdf.open("pdf", d.tobytes())
        first = m.pdf_dict_getl(m.pdf_trailer(tag_upkeep._pdf(d)), pymupdf.PDF_NAME("Root"),
                                pymupdf.PDF_NAME("Outlines"), pymupdf.PDF_NAME("First"))
        self.assertEqual(BA._outline_xrefs(first, []),
                         BA.PYMUPDF_OWN["JM_outline_xrefs"](first, []))
        ours = d.get_toc(False)
        items = [[lv, t, p, {k: v for k, v in dest.items()
                             if k not in ("xref", "bold", "italic", "collapse", "color",
                                          "zoom")}] for lv, t, p, dest in ours]
        BA.PYMUPDF_OWN["_extend_toc_items"](d, items)
        self.assertEqual(items, ours)


class TreeKept(Case):
    """The structure tree kept between edits (tag_upkeep.kept_tree)."""

    def setUp(self):
        from tests.test_accessibility import autotagged, sample
        d = sample(4)
        autotagged(d)
        self.v = self.view(d)
        self.v._warm_now()
        self.assertIsNotNone(getattr(self.v.doc, "_kz_tag_tree", None))

    def reads(self):
        """A counter of the trees read afresh."""
        real = tag_upkeep.Tree
        count = [0]

        class Counted(real):
            def __init__(self, doc):
                count[0] += 1
                super().__init__(doc)
        p = mock.patch.object(tag_upkeep, "Tree", Counted)
        p.start()
        self.addCleanup(p.stop)
        return count

    def edits(self, v):
        def word(i, text):
            return next(w for w in v.doc[i].get_text("words") if w[4] == text)

        def edit_text():
            wd = word(1, "Details")
            v.edit_text_at(1, pymupdf.Point((wd[0] + wd[2]) / 2, (wd[1] + wd[3]) / 2))
            ed = v._inline
            ed.text.setPlainText(ed.text.toPlainText().replace("Details", "Particulars"))
            ed.commit()

        def add_text():
            v.add_text_at(2, pymupdf.Point(300, 640))
            v._inline.text.setPlainText("Added words")
            v._inline.commit()

        def delete_markup():
            page = v.doc[0]
            page.delete_annot(next(a for a in page.annots() if a.type[1] == "Square"))
        return [
            ("markup", lambda: v.modify(
                lambda: v.doc[0].add_rect_annot(pymupdf.Rect(400, 300, 450, 350)), [0])),
            ("note", lambda: v.modify(lambda: v.doc[3].add_text_annot((400, 500), "N"), [3])),
            ("edit text", edit_text),
            ("add text", add_text),
            ("delete markup", lambda: v.modify(delete_markup, [0])),
            ("duplicate", lambda: v.duplicate_pages([1])),
            ("insert blank", lambda: v.insert_blank(2)),
            ("delete page", lambda: v.delete_pages([0])),
        ]

    def test_edits_undone_and_redone_with_the_tree_kept(self):
        from tests.battery_random import canon
        v = self.v
        with mock.patch.object(tag_upkeep, "CHECK", True):     # (kept == read afresh)
            for name, fn in self.edits(v):
                before = canon(v._snapshot())
                fn()
                self.assertEqual(tag_upkeep.problems(v.doc), [], name)
                after = canon(v._snapshot())
                self.assertNotEqual(before, after, name)
                v.undo()
                self.assertEqual(canon(v._snapshot()), before, name)
                v._warm_now()                   # (as the idle moment after an undo does)
                v.redo()
                self.assertEqual(canon(v._snapshot()), after, name)
                self.assertEqual(tag_upkeep.problems(v.doc), [], name)
                # the next edit right after the redo, the tree not read again yet
                v.modify(lambda: v.doc[0].add_text_annot((30, 30 + 20 * len(name)), name),
                         [0])
                self.assertEqual(tag_upkeep.problems(v.doc), [], name)

    def test_the_tree_is_read_only_when_it_must_be(self):
        v = self.v
        count = self.reads()
        for name, fn in self.edits(v)[:5]:
            fn()
        self.assertEqual(count[0], 0)           # (kept, edit after edit)
        v.undo()
        v.modify(lambda: v.doc[0].add_text_annot((30, 30), "after undo"), [0])
        self.assertEqual(count[0], 1)           # (an undo: read again)
        # an element replaced (xref_set_key, as Alt text writes it): read again
        fig = next(f for f in acc.figures(v.doc))
        v.modify(lambda: acc.set_alt(v.doc, fig["num"], "A chart"), [])
        v.modify(lambda: v.doc[0].add_text_annot((30, 60), "after alt"), [0])
        self.assertEqual(count[0], 2)
        # the tree changed in place elsewhere (Reading order): read again
        items = acc.page_order(v.doc, 2)
        v.modify(lambda: acc.set_order(v.doc, items[::-1]), [2])
        self.assertEqual(count[0], 3)
        self.assertEqual(tag_upkeep.problems(v.doc), [])


class Popups(Case):
    def test_a_note_and_its_popup_tagged_together(self):
        from tests.battery_random import canon
        from tests.test_accessibility import autotagged, sample
        d = sample(2)
        autotagged(d)
        v = self.view(d)
        before = canon(v._snapshot())
        v.modify(lambda: v.doc[1].add_text_annot((400, 400), "A note"), [1])
        self.assertEqual(tag_upkeep.problems(v.doc), [])
        after = canon(v._snapshot())
        note = next(a.xref for a in v.doc[1].annots() if a.type[1] == "Text")
        pop = int(v.doc.xref_get_key(note, "Popup")[1].split()[0])
        self.assertEqual(tag_upkeep.popup_of(v.doc, pop), note)
        tree = tag_upkeep.Tree(v.doc)
        (el,) = tree.objr[note]
        self.assertEqual(el.type, "Annot")
        self.assertEqual(tree.objr[pop], [el])
        self.assertEqual(v.doc.xref_get_key(pop, "Contents"), ("string", "A note"))
        v.undo()
        self.assertEqual(canon(v._snapshot()), before)
        v.redo()
        self.assertEqual(canon(v._snapshot()), after)
        # its text changed: the popup's follows; the note deleted: both leave the tags
        v.modify(lambda: v.doc.xref_set_key(note, "Contents", "(Changed)"), [1])
        self.assertEqual(v.doc.xref_get_key(pop, "Contents"), ("string", "Changed"))

        def delete():
            page = v.doc[1]
            page.delete_annot(next(a for a in page.annots() if a.xref == note))
        v.modify(delete, [1])
        self.assertEqual(tag_upkeep.problems(v.doc), [])
        self.assertNotIn("Annot", [e.type for e in tag_upkeep.Tree(v.doc).els])

    def test_auto_tag_tags_popups_with_their_markups(self):
        from kanzonas import autotag
        from tests.test_accessibility import sample
        d = sample(1)
        d[0].add_text_annot((400, 400), "Before tagging")
        autotag.apply(d, autotag.make_plans(d))
        self.assertEqual(tag_upkeep.problems(d), [])
        tree = tag_upkeep.Tree(d)
        els = [e for e in tree.els if e.type == "Annot"]
        self.assertEqual(len(els), 1)
        self.assertEqual(len(els[0].objrs), 2)


class Retarget(Case):
    def test_bookmarks_of_a_deleted_page_moved_fast_and_alike(self):
        import time
        from kanzonas import bookmarks_auto as BA
        d = pymupdf.open()
        for i in range(30):
            d.new_page().insert_text((72, 72), "Page %d" % (i + 1))
        d.set_toc([[1, "Mark %d" % i, 1 if i % 3 == 0 else i % 30 + 1,
                    {"kind": pymupdf.LINK_GOTO, "page": 0 if i % 3 == 0 else i % 30,
                     "to": pymupdf.Point(0, 100), "bold": i % 2 == 0}]
                   for i in range(3000)])
        v = self.view(d)
        t = time.perf_counter()
        self.assertTrue(v.delete_pages([0]))
        took = time.perf_counter() - t
        toc = v.doc.get_toc(False)
        moved = [e for i, e in enumerate(toc) if i % 3 == 0]
        self.assertEqual(len(moved), 1000)
        self.assertTrue(all(e[2] == 1 and e[3]["page"] == 0 for e in moved))
        self.assertTrue(all(e[3].get("bold") for e in moved[::2]))
        self.assertLess(took, 1.5, took)        # (10 s when each read the whole outline)
        # what set_toc_item writes, written alike
        a, b = (pymupdf.open("pdf", d.tobytes()) for _ in range(2))
        for doc, fn in ((a, lambda doc, i, e: doc.set_toc_item(i, dest_dict=e)),
                        (b, BA.set_toc_dest)):
            for i, e in enumerate(doc.get_toc(False)[:50]):
                fn(doc, i, dict(e[3], page=5, to=pymupdf.Point(0, 0)))
        self.assertEqual([a.xref_object(x) for x in range(1, a.xref_length())],
                         [b.xref_object(x) for x in range(1, b.xref_length())])


class TableOfContents(Case):
    def toc_doc(self, tag=True):
        from tests.test_accessibility import autotagged, sample
        d = sample(3)
        if tag:
            autotagged(d)
        d.set_toc([[1, "Section 1", 1], [2, "Details", 1], [1, "Section 2", 2],
                   [1, "Section 3", 3]])
        return d

    def insert(self, v, replace=False):
        from kanzonas import bookmarks_auto as BA
        out = {}
        v.modify(lambda: out.setdefault("r", BA.insert_toc(v.doc, 0, replace=replace)),
                 structural=True, changed=[])
        return out["r"]

    def test_a_table_of_contents_on_a_tagged_document_is_tagged_as_one(self):
        from tests.battery_random import canon
        v = self.view(self.toc_doc())
        before = canon(v._snapshot())
        self.assertEqual(self.insert(v), (0, 1))
        self.assertEqual(tag_upkeep.problems(v.doc), [])
        after = canon(v._snapshot())
        tree = tag_upkeep.Tree(v.doc)
        px = v.doc[0].xref
        toc = [e for e in tree.els if e.type == "TOC"]
        self.assertEqual(len(toc), 1)
        items = toc[0].kids
        self.assertEqual([e.type for e in items], ["TOCI"] * 4)
        words = acc.marked_content(v.doc, 0)
        for item, title, num in zip(items, ["Section 1", "Details", "Section 2", "Section 3"],
                                    ["2", "2", "3", "4"]):
            (link,) = item.kids
            self.assertEqual(link.type, "Link")
            self.assertEqual(len(link.objrs), 1)
            text = " ".join(words[mc][1] for pg, mc in link.mcids if pg == px)
            self.assertIn(title, text)
            self.assertIn(num, text)
            self.assertNotIn(". .", text)               # (the leaders: an artifact)
            self.assertEqual(v.doc.xref_get_key(link.objrs[0][0], "Contents")[1],
                             "%s, page %s" % (title, num))
        # nothing on the page tagged twice or left as a P of the old kind
        on_page = [e.type for e in tree.els if e.pg == px and not e.gone]
        self.assertEqual(on_page.count("P"), 1)          # (the title, "Contents")
        v.undo()
        self.assertEqual(canon(v._snapshot()), before)
        v.redo()
        self.assertEqual(canon(v._snapshot()), after)
        # made again in place of the old one: one table still
        self.insert(v, replace=True)
        self.assertEqual(tag_upkeep.problems(v.doc), [])
        self.assertEqual([e.type for e in tag_upkeep.Tree(v.doc).els].count("TOC"), 1)

    def test_its_links_are_described_on_an_untagged_document(self):
        v = self.view(self.toc_doc(tag=False))
        self.insert(v)
        self.assertFalse(tag_upkeep.is_tagged(v.doc))
        self.assertEqual([l["contents"] for l in acc.links(v.doc) if l["page"] == 0],
                         ["Section 1, page 2", "Details, page 2", "Section 2, page 3",
                          "Section 3, page 4"])


if __name__ == "__main__":
    unittest.main()
