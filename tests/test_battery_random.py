"""The randomized editing battery (tests/battery_random.py), short, in every build; and the
bugs it found, each checked on its own.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_battery_random
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402

from tests import battery_random  # noqa: E402
from tests.test_undo_journal import Quiet  # noqa: E402

APP = battery_random.APP
m = pymupdf.mupdf


def chain(page):
    """The xrefs of a loaded page's markups in the order MuPDF draws them."""
    out = []
    a = m.pdf_first_annot(pymupdf._as_pdf_page(page))
    while a.m_internal:
        out.append(m.pdf_to_num(m.pdf_annot_obj(a)))
        a = m.pdf_next_annot(a)
    return out


class RandomEditing(unittest.TestCase):
    def test_short_battery(self):
        # (a few hundred random steps with undo, redo and saves mixed in: the long runs are
        # done by hand, python tests/battery_random.py OUT --ops 2000 --seed S)
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as out:
            log = []
            failures, stats = battery_random.run(out, 200, 11, log=log.append)
            self.assertEqual(failures, [], "\n".join(log))
            self.assertIn("200 steps", stats)


class FoundByTheBattery(Quiet):
    def test_copying_pages_leaves_the_document_as_it_was(self):
        # PyMuPDF takes /P and /Popup out of the markups it copies (and /P out of the form
        # fields), in the document copied from: Duplicate pages, Copy pages, Extract pages
        # and the Capture tool changed the open document, notes lost their pop-ups, and an
        # undo of the next edit didn't give the document as it was before it
        v = self.view()
        page = v.doc[0]
        note = page.add_text_annot((300, 300), "a note")
        note.set_popup(pymupdf.Rect(320, 300, 480, 380))
        note.update()
        del note, page

        def objects():
            return [v.doc.xref_object(x) for x in range(1, v.doc.xref_length())]
        before = objects()
        v.pages_bytes([0, 1, 2])
        v.extract_pages(0, 1, self.path("out.pdf"))
        self.assertEqual(objects(), before)
        from tests.test_undo_journal import canon
        start = canon(v.doc)
        v.duplicate_pages([1])
        self.assertEqual(v.doc.page_count, 5)
        v.undo()
        self.assertEqual(canon(v.doc), start)
        page = v.doc[0]
        self.assertTrue(any(a.popup_xref for a in page.annots()))     # (the note's pop-up)
        v.dirty = False

    def test_copied_markups_stay_apart(self):
        # copies of a markup came without /P (the page it is on), so two copies were equal
        # objects, and a write that merges those (Apply redactions cleans the file so, Copy
        # pages and Extract pages write so) made them one markup on two pages: moving or
        # deleting it on one page did it on the other too
        v = self.view()
        v.duplicate_pages([0])
        v.duplicate_pages([0])
        v.mark_redactions(3, [pymupdf.Rect(70, 55, 200, 80)])
        v.apply_redactions(scrub=True)

        def owners(doc):
            seen = {}
            for i in range(doc.page_count):
                for x, *_ in doc[i].annot_xrefs():
                    self.assertNotIn(x, seen, "markup %d on pages %s and %d" % (
                        x, seen.get(x), i))
                    seen[x] = i
            return seen
        self.assertEqual(len(owners(v.doc)), 6 + 2)     # (6 pages, the form field, the link)
        with pymupdf.open("pdf", v.pages_bytes([0, 1, 2])) as copy:
            owners(copy)
        v.dirty = False

    def test_an_edited_markup_is_drawn_in_its_place(self):
        # an edited markup is written anew and put back in its place in /Annots; MuPDF kept
        # its own list of the loaded page's markups, and drew the new one on top of the
        # others until the page was freed or the file saved
        from kanzonas import annotations as A
        v = self.view()
        page = v.doc[0]
        held = page.first_annot             # (the page stays loaded, as the view keeps it)
        first = v._create(0, {"kind": "rect", "props": dict(A.DEFAULTS["rect"], fill="#ff0000"),
                              "rect": pymupdf.Rect(60, 60, 160, 160)})
        v._create(0, {"kind": "rect", "props": dict(A.DEFAULTS["rect"], fill="#0000ff"),
                      "rect": pymupdf.Rect(100, 100, 200, 200)})
        model = A.read(page.load_annot(first))
        model["props"]["fill"] = "#00ff00"
        v.commit_model(0, first, model)
        order = A.annot_order(page)
        self.assertEqual([x for x in chain(page) if x in order], order)
        self.assertEqual([x for x in chain(v.doc[0]) if x in order], order)
        del held
        v.dirty = False

    def test_redo_offered_after_an_undo(self):
        # an undo told the window of the change before the step was in the list to redo:
        # Redo stayed grayed out (Ctrl+Y did nothing) after undoing a page inserted
        from kanzonas.main_window import MainWindow
        src = self.path("w.pdf")
        battery_random.sample(src)
        w = MainWindow()
        self.addCleanup(w.deleteLater)
        w.open_file(src)
        v = w.view()
        self.addCleanup(lambda: setattr(v, "dirty", False))
        for edit in (lambda: v.insert_blank(1), lambda: v.rotate_page(0, 90)):
            edit()
            APP.processEvents()
            w.a_undo.trigger()
            APP.processEvents()
            self.assertTrue(v.can_redo())
            self.assertTrue(w.a_redo.isEnabled())
            w.a_redo.trigger()
            self.assertFalse(v.can_redo())
            self.assertTrue(w.a_undo.isEnabled())


if __name__ == "__main__":
    unittest.main()
