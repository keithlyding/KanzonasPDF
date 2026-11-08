"""What the 1.10 break-it battery found in accessibility (tags kept in step with the edits,
Check accessibility) and bookmarks, fixed:

- a parent tree whose node lists itself among its /Kids (twice): Check accessibility and
  every edit of the document never finished (each path to the node was read again: 2^32);
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


if __name__ == "__main__":
    unittest.main()
