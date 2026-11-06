"""The review workflow (review.py, xfdf.py, review_ui.py): replies to markups, review status,
comments exchanged as XFDF / FDF, the comment summary, and threads in the Markups list.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_review
"""
import os
import sys
import tempfile
import time
import unittest
import xml.etree.ElementTree as ET
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import annotations as A, review, xfdf  # noqa: E402
from kanzonas import markups_panel as MP  # noqa: E402
from kanzonas.document_view import DocumentView  # noqa: E402

P = pymupdf.Point
R = pymupdf.Rect


def sample(path, pages=3):
    d = pymupdf.open()
    for i in range(pages):
        p = d.new_page(width=612, height=792)
        p.insert_text((72, 100), "Page %d has words to comment on" % (i + 1), fontsize=12)
    d.save(path)
    d.close()
    return path


def model(kind, **kw):
    m = {"kind": kind, "props": dict(A.DEFAULTS[kind]), "rect": R()}
    m["props"].update(kw.pop("props", {}))
    m.update(kw)
    return m


def acrobat_style(path):
    """A file as Acrobat writes a review: a sticky note with a reply (/IRT, /RT /R, /F 28, its
    own pop-up and rich text), a reply to that reply, a review status and a check mark
    (hidden status replies, /F 30), and a markup grouped with the note (/RT /Group: not a
    reply)."""
    d = pymupdf.open()
    page = d.new_page(width=612, height=792)
    pg = page.xref
    objs = {}

    def obj(body):
        x = d.get_new_xref()
        d.update_object(x, body)
        return x
    ap = obj("<</Type/XObject/Subtype/Form/BBox[0 0 20 20]/Resources<<>>>>")
    d.update_stream(ap, b"1 0.82 0 rg 0 0 20 20 re f")
    note = obj("<</Type/Annot/Subtype/Text/Rect[100 650 120 670]/Contents(Check this span)"
               "/T(Reviewer One)/M(D:20261101090000-05'00')/CreationDate(D:20261101090000-05'00')"
               "/NM(a1b2c3d4-0001)/F 28/Name/Comment/C[1 0.82 0]/Subj(Sticky Note)"
               f"/AP<</N {ap} 0 R>>/P {pg} 0 R>>")
    objs["note"] = note
    reply = obj(f"<</Type/Annot/Subtype/Text/Rect[100 650 120 670]/IRT {note} 0 R/RT/R"
                "/Contents(Agreed, will fix)/RC(<?xml version=\"1.0\"?><body><p>Agreed, will fix"
                "</p></body>)/T(Author Two)/M(D:20261102100000-05'00')"
                "/CreationDate(D:20261102100000-05'00')/NM(a1b2c3d4-0002)/F 28/Name/Comment"
                f"/C[1 0.82 0]/Subj(Sticky Note)/P {pg} 0 R>>")
    objs["reply"] = reply
    popup = obj(f"<</Type/Annot/Subtype/Popup/Rect[400 600 580 700]/Parent {reply} 0 R/Open false"
                f"/F 28/P {pg} 0 R>>")
    d.xref_set_key(reply, "Popup", f"{popup} 0 R")
    reply2 = obj(f"<</Type/Annot/Subtype/Text/Rect[100 650 120 670]/IRT {reply} 0 R/RT/R"
                 "/Contents(Thanks)/T(Reviewer One)/M(D:20261103110000-05'00')"
                 "/CreationDate(D:20261103110000-05'00')/NM(a1b2c3d4-0003)/F 28/Name/Comment"
                 f"/P {pg} 0 R>>")
    objs["reply2"] = reply2
    state = obj(f"<</Type/Annot/Subtype/Text/Rect[100 650 120 670]/IRT {note} 0 R"
                "/Contents(Accepted set by Author Two)/T(Author Two)"
                "/M(D:20261102100500-05'00')/CreationDate(D:20261102100500-05'00')"
                "/NM(a1b2c3d4-0004)/F 30/Name/Comment/State(Accepted)/StateModel(Review)"
                f"/P {pg} 0 R>>")
    objs["state"] = state
    mark = obj(f"<</Type/Annot/Subtype/Text/Rect[100 650 120 670]/IRT {note} 0 R"
               "/Contents(Marked set by Reviewer One)/T(Reviewer One)"
               "/M(D:20261102100600-05'00')/NM(a1b2c3d4-0005)/F 30/Name/Comment"
               f"/State(Marked)/StateModel(Marked)/P {pg} 0 R>>")
    objs["mark"] = mark
    group = obj(f"<</Type/Annot/Subtype/Square/Rect[200 600 260 640]/IRT {note} 0 R/RT/Group"
                "/C[0 0 1]/T(Reviewer One)/Contents(grouped box)/NM(a1b2c3d4-0006)/F 4"
                f"/P {pg} 0 R>>")
    objs["group"] = group
    d.xref_set_key(pg, "Annots", "[%s]" % " ".join(
        f"{x} 0 R" for x in (note, reply, popup, reply2, state, mark, group)))
    d.save(path)
    d.close()
    return objs


class Base(unittest.TestCase):
    def setUp(self):
        self.boxes = []
        for name in ("information", "warning", "critical"):
            patch = mock.patch.object(QMessageBox, name,
                                      lambda *a, **k: self.boxes.append(a[1:3]))
            patch.start()
            self.addCleanup(patch.stop)
        self.answer = QMessageBox.Yes
        self.asked = []

        def question(*a, **k):
            self.asked.append(a[2] if len(a) > 2 else "")
            return self.answer
        patch = mock.patch.object(QMessageBox, "question", question)
        patch.start()
        self.addCleanup(patch.stop)
        patch = mock.patch.object(A, "author", lambda: "Tester")
        patch.start()
        self.addCleanup(patch.stop)
        self.dir = tempfile.mkdtemp()

    def path(self, name):
        return os.path.join(self.dir, name)

    def view(self, path=None, pages=3):
        v = DocumentView(path or sample(self.path("doc%d.pdf" % time.perf_counter_ns()), pages))
        self.addCleanup(v.close_doc)
        self.addCleanup(lambda: setattr(v, "dirty", False))
        return v

    def add(self, v, index, m):
        v._create(index, m)
        return [x for x, typ, _nm in v.doc[index].annot_xrefs()
                if typ != pymupdf.PDF_ANNOT_POPUP][-1]

    def rect(self, v, index=0, box=(100, 200, 200, 260), props=None):
        return self.add(v, index, model("rect", rect=R(box), text="a box",
                                        props=props or {}))

    def threads(self, v, index=0):
        return review.Threads(v.doc[index])


# ---- replies ----------------------------------------------------------------------------------
class Replies(Base):
    def test_reply_written_read_and_threaded(self):
        v = self.view()
        box = self.rect(v)
        r1 = v.reply_to(0, box, "First reply")
        r2 = v.reply_to(0, r1, "A reply to the reply")
        r3 = v.reply_to(0, box, "Second reply")
        t = self.threads(v)
        self.assertEqual(t.root(r2), box)
        self.assertEqual([(d, ln.text, ln.author) for d, ln in t.replies(box)],
                         [(1, "First reply", "Tester"), (2, "A reply to the reply", "Tester"),
                          (1, "Second reply", "Tester")])
        doc = v.doc
        # the standard way: a Text annotation, /IRT to its parent, /RT /R, author and dates
        for x, parent in ((r1, box), (r2, r1), (r3, box)):
            self.assertEqual(doc.xref_get_key(x, "Subtype"), ("name", "/Text"))
            self.assertEqual(doc.xref_get_key(x, "IRT"), ("xref", f"{parent} 0 R"))
            self.assertEqual(doc.xref_get_key(x, "RT"), ("name", "/R"))
            self.assertEqual(doc.xref_get_key(x, "T"), ("string", "Tester"))
            self.assertTrue(doc.xref_get_key(x, "CreationDate")[1].startswith("D:"))
            self.assertTrue(doc.xref_get_key(x, "M")[1].startswith("D:"))
            self.assertEqual(doc.xref_get_key(x, "F"), ("int", "28"))
        # each reply is its own undo step
        v.undo()
        self.assertEqual(len(self.threads(v).replies(box)), 2)
        v.redo()
        self.assertEqual(len(self.threads(v).replies(box)), 3)

    def test_replies_draw_nothing_on_the_page(self):
        v = self.view()
        box = self.rect(v, box=(100, 200, 200, 260))
        before = v.doc[0].get_pixmap().samples
        v.reply_to(0, box, "Not an icon on the page")
        self.assertEqual(v.doc[0].get_pixmap().samples, before)

    def test_replies_survive_save_and_reopen(self):
        v = self.view()
        box = self.rect(v)
        r1 = v.reply_to(0, box, "Kept")
        v.reply_to(0, r1, "Kept too")
        v.set_review_status(0, [box], "Rejected")
        out = self.path("saved.pdf")
        v.save(out)
        d = pymupdf.open(out)
        self.addCleanup(d.close)
        t = review.Threads(d[0])
        roots = [x for x in t.order if not t.is_linked(x)]
        self.assertEqual(len(roots), 1)
        self.assertEqual([(dp, ln.text) for dp, ln in t.replies(roots[0])],
                         [(1, "Kept"), (2, "Kept too")])
        self.assertEqual(t.status(roots[0])[0], "Rejected")

    def test_acrobat_style_file(self):
        objs = acrobat_style(self.path("acrobat.pdf"))
        v = self.view(self.path("acrobat.pdf"))
        t = self.threads(v)
        note = objs["note"]
        self.assertEqual([(d, ln.author, ln.text) for d, ln in t.replies(note)],
                         [(1, "Author Two", "Agreed, will fix"), (2, "Reviewer One", "Thanks")])
        state, link, marked = t.status(note)
        self.assertEqual((state, link.author, marked), ("Accepted", "Author Two", True))
        self.assertFalse(t.is_linked(objs["group"]))      # (/RT /Group: a markup of its own)
        # the Markups list: the note with its status, its two replies under it; the
        # grouped box a row of its own; statuses and pop-ups aren't rows
        rows = MP.collect(v.doc)
        self.assertEqual([(r[1], r[2], r[7], r[8], r[9], r[10]) for r in rows], [
            (note, A.LABELS["note"], "\u2713 Accepted", 0, 0, 2),
            (objs["reply"], "Reply", "", note, 1, 0),
            (objs["reply2"], "Reply", "", note, 2, 0),
            (objs["group"], A.LABELS["rect"], "", 0, 0, 0)])
        # a click on the reply selects the note
        v.select_xref(0, objs["reply2"])
        self.assertEqual(v.selection, (0, note))
        # the thread shows when the note is opened
        with mock.patch("kanzonas.dialogs.get_text", return_value=("", False)) as ask:
            v.edit_annot_text(0, note)
        label = ask.call_args[0][2]
        self.assertIn("Agreed, will fix", label)
        self.assertIn("Accepted set by Author Two", label)
        # editing a reply changes it in place and drops Acrobat's rich text (shown instead)
        self.assertTrue(v.edit_reply(0, objs["reply"], "Agreed, fixed"))
        self.assertEqual(v.doc.xref_get_key(objs["reply"], "Contents")[1], "Agreed, fixed")
        self.assertEqual(v.doc.xref_get_key(objs["reply"], "RC")[0], "null")
        self.assertEqual(v.doc.xref_get_key(objs["reply"], "IRT")[1], f"{note} 0 R")

    def test_edit_text_of_a_reply_edits_the_reply(self):
        v = self.view()
        box = self.rect(v)
        r = v.reply_to(0, box, "old")
        with mock.patch("kanzonas.dialogs.get_text", return_value=("new words", True)):
            v.edit_annot_text(0, r)
        self.assertEqual(v.doc.xref_get_key(r, "Contents")[1], "new words")
        self.assertEqual(v.doc.xref_get_key(box, "Contents")[1], "a box")
        self.assertEqual(self.threads(v).root(r), box)

    def test_reply_isnt_hit_and_selects_its_markup(self):
        v = self.view()
        note = self.add(v, 0, model("note", rect=R(300, 300, 320, 320), text="note"))
        r = v.reply_to(0, note, "reply")
        self.assertEqual(v.annot_at(0, P(301, 301)), note)
        v.select_xref(0, r)
        self.assertEqual(v.selection, (0, note))
        v._set_selection(0, [r, note])
        self.assertEqual(v.selected_xrefs(), [note])
        self.assertEqual([x for _i, x in v.review_items()], [note])

    def test_deleting_a_markup_asks_and_takes_its_thread(self):
        v = self.view()
        box = self.rect(v)
        other = self.rect(v, box=(300, 400, 350, 450))
        r1 = v.reply_to(0, box, "one")
        v.reply_to(0, r1, "two")
        v.set_review_status(0, [box], "Completed")
        before = sorted(x for x, *_ in v.doc[0].annot_xrefs())
        steps = len(v._undo)
        # No: nothing deleted
        self.answer = QMessageBox.No
        v.select_xref(0, box)
        v.delete_selected()
        self.assertEqual(len(self.asked), 1)
        self.assertIn("2 replies", self.asked[0])
        self.assertEqual(sorted(x for x, *_ in v.doc[0].annot_xrefs()), before)
        # Yes: the markup, its replies, the replies to those and its status, in one step
        self.answer = QMessageBox.Yes
        v.select_xref(0, box)
        v.delete_selected()
        self.assertEqual([x for x, *_ in v.doc[0].annot_xrefs()], [other])
        self.assertEqual(len(v._undo), steps + 1)
        v.undo()
        self.assertEqual(sorted(x for x, *_ in v.doc[0].annot_xrefs()), before)
        t = self.threads(v)
        self.assertEqual([ln.text for _d, ln in t.replies(box)], ["one", "two"])
        self.assertEqual(t.status(box)[0], "Completed")
        # a markup without replies is deleted without asking
        v.select_xref(0, other)
        v.delete_selected()
        self.assertEqual(len(self.asked), 2)

    def test_deleting_a_reply_alone(self):
        v = self.view()
        box = self.rect(v)
        r1 = v.reply_to(0, box, "one")
        r2 = v.reply_to(0, r1, "two")
        r3 = v.reply_to(0, box, "three")
        v.delete_reply(0, r1)                   # (with the reply to it)
        xs = {x for x, *_ in v.doc[0].annot_xrefs()}
        self.assertTrue({box, r3} <= xs)
        self.assertFalse({r1, r2} & xs)

    def test_replies_move_with_their_markup(self):
        v = self.view()
        box = self.rect(v)
        r = v.reply_to(0, box, "follows")
        before = review._rect_of(v.doc, r)
        page = v.doc[0]
        x, m = box, A.read(page.load_annot(box))
        del page
        v.commit_models(0, [(x, A.moved(m, P(30, 40)))], olds={x: m})
        after = review._rect_of(v.doc, r)
        # (page coordinates down, PDF up)
        self.assertAlmostEqual(after.x0 - before.x0, 30, 3)
        self.assertAlmostEqual(after.y0 - before.y0, -40, 3)
        self.assertEqual(v.doc.xref_get_key(r, "IRT")[1], f"{box} 0 R")

    def test_a_markup_written_anew_keeps_its_thread(self):
        v = self.view()
        box = self.rect(v)
        r = v.reply_to(0, box, "stays")
        page = v.doc[0]
        m = A.read(page.load_annot(box))
        del page
        m["props"]["stroke"] = "#00ff00"
        v.commit_model(0, box, m)
        t = self.threads(v)
        roots = [x for x in t.order if not t.is_linked(x)]
        self.assertEqual(len(roots), 1)
        self.assertEqual(t.root(r), roots[0])

    def test_apply_redactions_and_sanitize_with_threads(self):
        """Clean-up removes replies (PyMuPDF's own step failed on a reply to a reply)."""
        for how in ("redact", "sanitize"):
            v = self.view()
            box = self.rect(v)
            r = v.reply_to(0, box, "one")
            v.reply_to(0, r, "two")
            v.set_review_status(0, [box], "Accepted")
            if how == "redact":
                v.mark_redactions(0, [R(300, 600, 400, 650)])
                v.apply_redactions(scrub=True)
            else:
                v.sanitize({"markups": True})
            self.assertEqual(self.boxes, [], how)
            t = self.threads(v)
            self.assertEqual(t.links, {}, how)

    def test_redaction_over_a_thread(self):
        """A redaction mark over a markup takes it with its whole thread; Search & redact
        cleans a reply where it is (its thread kept)."""
        v = self.view()
        box = self.rect(v, box=(300, 600, 360, 640))
        r = v.reply_to(0, box, "one")
        v.reply_to(0, r, "two")
        keep = self.rect(v, box=(100, 300, 160, 340))
        r2 = v.reply_to(0, keep, "the words plan")
        v.mark_redactions(0, [R(290, 590, 370, 650)])
        v.search_redact("words")
        v.apply_redactions(scrub=False)
        self.assertEqual(self.boxes, [])
        t = self.threads(v)
        xs = {x for x, *_ in v.doc[0].annot_xrefs()}
        self.assertNotIn(box, xs)
        self.assertEqual([ln.text for _d, ln in t.replies(keep)], ["the [redacted] plan"])
        self.assertEqual(t.root(r2), keep)

    def test_new_scale_keeps_a_measurements_replies(self):
        v = self.view()
        m = self.add(v, 0, model("m_length", points=[P(100, 600), P(300, 600)]))
        r = v.reply_to(0, m, "check this length")
        page = v.doc[0]
        before = page.load_annot(m).info["content"]
        del page
        v.set_page_scale([0], 0.01, "m", "1:100")
        t = self.threads(v)
        roots = [x for x in t.order if not t.is_linked(x)]
        self.assertEqual(len(roots), 1)
        page = v.doc[0]
        self.assertNotEqual(page.load_annot(roots[0]).info["content"], before)
        del page
        self.assertEqual(t.root(r), roots[0])
        self.assertEqual(self.boxes, [])

    def test_legend_doesnt_count_replies(self):
        from kanzonas import legend as L
        v = self.view()
        note = self.add(v, 0, model("note", rect=R(300, 300, 320, 320), text="note"))
        v.reply_to(0, note, "reply")
        v.set_review_status(0, [note], "Accepted")
        rows = L.page_summary(v.doc, 0)
        self.assertEqual(sum(r["n"] for r in rows.values()), 1)


# ---- review status -------------------------------------------------------------------------
class Status(Base):
    def test_set_changed_history_kept(self):
        v = self.view()
        box = self.rect(v)
        v.set_review_status(0, [box], "Accepted")
        v.set_review_status(0, [box], "Rejected")
        v.set_review_status(0, [box], "Marked")
        t = self.threads(v)
        self.assertEqual(t.status(box)[0], "Rejected")
        self.assertTrue(t.status(box)[2])
        hist = [(ln.state, ln.model, ln.author) for ln in t.states(box)]
        self.assertEqual(hist, [("Accepted", "Review", "Tester"), ("Rejected", "Review", "Tester"),
                                ("Marked", "Marked", "Tester")])
        x = t.states(box)[0].xref
        self.assertEqual(v.doc.xref_get_key(x, "F"), ("int", "30"))     # (hidden)
        self.assertEqual(v.doc.xref_get_key(x, "State"), ("string", "Accepted"))
        self.assertEqual(v.doc.xref_get_key(x, "StateModel"), ("string", "Review"))
        v.set_review_status(0, [box], "None")
        v.set_review_status(0, [box], "Unmarked")
        self.assertEqual(self.threads(v).status(box)[0], "")
        self.assertFalse(self.threads(v).status(box)[2])
        v.undo()
        self.assertTrue(self.threads(v).status(box)[2])

    def test_several_markups_one_step_and_a_reply_means_its_markup(self):
        v = self.view()
        a, b = self.rect(v), self.rect(v, box=(300, 300, 360, 360))
        r = v.reply_to(0, a, "reply")
        n = len(v._undo)
        v.set_review_status(0, [r, b], "Completed")
        self.assertEqual(len(v._undo), n + 1)
        t = self.threads(v)
        self.assertEqual((t.status(a)[0], t.status(b)[0]), ("Completed", "Completed"))
        self.assertEqual(t.states(r), [])

    def test_status_column_and_filter(self):
        from kanzonas.markups_panel import MarkupsPanel
        v = self.view()
        a = self.rect(v)
        b = self.rect(v, box=(300, 300, 360, 360))
        c = self.rect(v, 1)
        v.set_review_status(0, [a], "Accepted")
        v.set_review_status(0, [b], "Rejected")
        v.set_review_status(0, [b], "Marked")
        panel = MarkupsPanel()
        self.addCleanup(panel.deleteLater)
        panel.refresh(v.doc)
        t = panel.table
        status = {tuple(t.item(r, 0).data(Qt.UserRole)): t.item(r, 6).text()
                  for r in range(t.rowCount())}
        self.assertEqual(status, {(0, a): "Accepted", (0, b): "\u2713 Rejected", (1, c): ""})

        def shown(key):
            panel.status_filter.setCurrentIndex(panel.status_filter.findData(key))
            return sorted(tuple(t.item(r, 0).data(Qt.UserRole)) for r in range(t.rowCount())
                          if not t.isRowHidden(r))
        self.assertEqual(shown("Accepted"), [(0, a)])
        self.assertEqual(shown("Rejected"), [(0, b)])
        self.assertEqual(shown("Marked"), [(0, b)])
        self.assertEqual(shown("Unmarked"), [(0, a), (1, c)])
        self.assertEqual(shown(""), [(1, c)])
        self.assertEqual(shown(None), [(0, a), (0, b), (1, c)])
        self.assertIsNone(panel.shown_markups())            # (all of them: export all)
        shown("Accepted")
        self.assertEqual(panel.shown_markups(), {0: [a]})   # (Export comments... the shown)
        shown(None)
        # the list's own menu asks the window: the signal carries the markup and status
        got = []
        panel.statusRequested.connect(lambda *s: got.append(s))
        panel.statusRequested.emit(0, a, "Cancelled")
        self.assertEqual(got, [(0, a, "Cancelled")])

    def test_status_menu_actions(self):
        from PySide6.QtWidgets import QMenu
        from kanzonas import review_ui
        v = self.view()
        a = self.rect(v)
        v.set_review_status(0, [a], "Accepted")
        menu = QMenu()
        self.addCleanup(menu.deleteLater)
        review_ui.add_review_actions(menu, v, 0, [a])
        texts = [x.text() for x in menu.actions()]
        self.assertIn("Reply...", texts)
        sub = [x for x in menu.actions() if x.menu()][0].menu()
        checked = [x.text() for x in sub.actions() if x.isChecked()]
        self.assertEqual(checked, ["Accepted"])
        [x for x in sub.actions() if x.text() == "Completed"][0].trigger()
        self.assertEqual(self.threads(v).status(a)[0], "Completed")


# ---- XFDF / FDF -----------------------------------------------------------------------------
def snapshot(doc):
    """Every markup as what a person sees of it, by name, with its thread links by name."""
    out = {}
    for i in range(doc.page_count):
        page = doc[i]
        t = review.Threads(page)
        names = {x: nm for x, _typ, nm in page.annot_xrefs()}
        for a in page.annots():
            if a.type[0] == pymupdf.PDF_ANNOT_POPUP:
                continue
            info = a.info
            cols = a.colors or {}
            ln = t.links.get(a.xref)
            out[info.get("name") or names[a.xref]] = (
                i, a.type[1], tuple(round(v, 2) for v in a.rect), info.get("content"),
                info.get("title"), info.get("creationDate"), info.get("modDate"),
                tuple(round(c, 3) for c in cols.get("stroke") or ()),
                tuple(round(c, 3) for c in cols.get("fill") or ()),
                a.opacity, a.flags,
                names.get(ln.parent) if ln else None, ln.state if ln else None,
                ln.model if ln else None,
                doc.xref_get_key(a.xref, A.KZ_KEY)[1])
    return out


class Exchange(Base):
    def marked_up(self):
        v = self.view()
        page = v.doc[0]
        quads = [w.quad for w in page.search_for("words")]
        del page
        a = self.rect(v, props={"stroke": "#00aa00", "fill": "#ffeedd", "opacity": 0.6})
        self.add(v, 0, model("rect", rect=R(300, 300, 400, 380), text="cloud",
                             props={"cloud": True}))
        self.add(v, 0, model("comment", quads=quads, rect=quads[0].rect, text="reword"))
        self.add(v, 0, model("arrow", points=[P(50, 500), P(200, 560)]))
        self.add(v, 1, model("polygon", points=[P(50, 50), P(150, 60), P(100, 160)],
                             text="area"))
        self.add(v, 1, model("ink", strokes=[[P(300, 300), P(320, 340), P(350, 310)]]))
        self.add(v, 1, model("textbox", rect=R(100, 400, 300, 460), text="Text box"))
        self.add(v, 2, model("note", rect=R(500, 100, 520, 120), text="Sticky"))
        self.add(v, 2, model("m_length", points=[P(100, 600), P(300, 600)]))
        self.add(v, 2, model("callout", rect=R(300, 300, 420, 340), points=[P(250, 250)],
                             text="Callout"))
        self.add(v, 2, model("stamp", rect=R(100, 680, 220, 730), detail="Tester 11/6/2026"))
        self.add(v, 1, model("m_dim", points=[P(100, 700), P(300, 700), P(200, 720)]))
        self.add(v, 1, model("m_area", points=[P(400, 500), P(500, 500), P(450, 580)]))
        r = v.reply_to(0, a, "Reply \u00e9\u00e8 \u2603 <&>")
        v.reply_to(0, r, "Second level")
        v.set_review_status(0, [a], "Accepted")
        v.set_review_status(0, [a], "Marked")
        return v

    def test_xfdf_round_trip_identical(self):
        v = self.marked_up()
        recs, skipped = xfdf.records(v.doc)
        self.assertEqual(skipped, {})
        data = xfdf.to_xfdf(recs, "doc.pdf")
        other = self.view()                     # (the same pages, no markups)
        steps = len(other._undo)
        rep = other.import_comments(xfdf.from_xfdf(data))
        self.assertEqual((rep.added, rep.replaced, rep.unchanged, rep.skipped),
                         (len(recs), 0, 0, {}))
        self.assertEqual(len(other._undo), steps + 1)           # (one undo step)
        self.assertEqual(snapshot(other.doc), snapshot(v.doc))
        # and drawn the same (a level of blending aside)
        for i in range(3):
            a, b = v.doc[i].get_pixmap(), other.doc[i].get_pixmap()
            self.assertLessEqual(max(abs(x - y) for x, y in zip(a.samples, b.samples)), 2)
        # imported again: nothing new
        rep = other.import_comments(xfdf.from_xfdf(data))
        self.assertEqual((rep.added, rep.unchanged), (0, len(recs)))
        # undo takes the whole import back
        other.undo()
        other.undo()
        self.assertEqual(sum(len(other.doc[i].annot_xrefs()) for i in range(3)), 0)

    def test_fdf_round_trip_identical(self):
        v = self.marked_up()
        recs, _skipped = xfdf.records(v.doc)
        data = xfdf.to_fdf(recs, "doc.pdf")
        self.assertTrue(data.startswith(b"%FDF-1.2"))
        other = self.view()
        rep = other.import_comments(xfdf.from_fdf(data))
        self.assertEqual(rep.added, len(recs))
        self.assertEqual(snapshot(other.doc), snapshot(v.doc))

    def test_selected_markups_take_their_thread(self):
        v = self.marked_up()
        a = [x for x in self.threads(v).order if not self.threads(v).is_linked(x)][0]
        recs, _ = xfdf.records(v.doc, {0: [a]})
        self.assertEqual(sorted(r["subtype"] for r in recs), ["Square", "Text", "Text", "Text",
                                                              "Text"])

    def test_xfdf_follows_the_spec(self):
        """The shape of the file (Adobe XFDF Specification 3.0 / ISO 19444-1): root <xfdf>
        in the XFDF namespace, <annots> with one element per annotation named for its
        subtype, page numbers from 0, rect "x1,y1,x2,y2", colors "#RRGGBB", flags by name,
        dates in PDF form, replies by inreplyto (the parent's name) and replyType, statuses by
        state / statemodel, <contents>, <vertices> and <inklist><gesture> as "x,y;x,y",
        coords for text markups, start / end / head / tail for lines, <f href>."""
        v = self.marked_up()
        recs, _ = xfdf.records(v.doc)
        root = ET.fromstring(xfdf.to_xfdf(recs, "doc.pdf"))
        ns = "{http://ns.adobe.com/xfdf/}"
        self.assertEqual(root.tag, ns + "xfdf")
        self.assertEqual(root.get("{http://www.w3.org/XML/1998/namespace}space"), "preserve")
        annots = root.find(ns + "annots")
        tags = sorted(el.tag[len(ns):] for el in annots)
        self.assertEqual(tags, sorted(["square", "square", "highlight", "line", "polygon",
                                       "ink", "freetext", "text", "line", "text", "text",
                                       "text", "text", "freetext", "stamp", "line",
                                       "polygon"]))
        self.assertEqual(root.find(ns + "f").get("href"), "doc.pdf")
        names = {el.get("name") for el in annots}
        import re
        for el in annots:
            self.assertRegex(el.get("page"), r"^\d+$")
            self.assertRegex(el.get("rect"), r"^-?[\d.]+(,-?[\d.]+){3}$")
            if el.get("color"):
                self.assertRegex(el.get("color"), r"^#[0-9A-F]{6}$")
            self.assertTrue(set(el.get("flags", "print").split(",")) <= set(xfdf.FLAG_NAMES))
            self.assertRegex(el.get("date"), r"^D:\d{14}")
            if el.get("inreplyto"):
                self.assertIn(el.get("inreplyto"), names)
                self.assertEqual(el.get("replyType"), "reply")
                self.assertEqual(el.tag, ns + "text")
            if el.get("state"):
                self.assertIn(el.get("statemodel"), ("Review", "Marked"))
            for sub in el.iter(ns + "vertices"):
                self.assertRegex(sub.text, r"^-?[\d.]+,-?[\d.]+(;-?[\d.]+,-?[\d.]+)+$")
            for sub in el.iter(ns + "gesture"):
                self.assertRegex(sub.text, r"^-?[\d.]+,-?[\d.]+(;-?[\d.]+,-?[\d.]+)+$")
            if el.tag == ns + "highlight":
                self.assertEqual(len(re.split(",", el.get("coords"))) % 8, 0)
                self.assertIsNotNone(el.find(ns + "popup"))
            if el.tag == ns + "line":
                self.assertRegex(el.get("start"), r"^-?[\d.]+,-?[\d.]+$")
                self.assertRegex(el.get("end"), r"^-?[\d.]+,-?[\d.]+$")
        reply = [el for el in annots if el.find(ns + "contents") is not None and
                 "\u2603" in el.find(ns + "contents").text][0]
        self.assertEqual(reply.find(ns + "contents").text, "Reply \u00e9\u00e8 \u2603 <&>")

    def test_import_into_fewer_pages_reports_what_was_skipped(self):
        v = self.marked_up()
        recs, _ = xfdf.records(v.doc)
        data = xfdf.to_xfdf(recs)
        small = self.view(pages=1)
        rep = small.import_comments(xfdf.from_xfdf(data))
        on0 = sum(1 for r in recs if r["page"] == 0)
        self.assertEqual(rep.added, on0)
        self.assertEqual(rep.skipped, {"page 2 isn't in this document": 5,
                                       "page 3 isn't in this document": 4})
        self.assertIn("page 3 isn't in this document", rep.text())
        t = self.threads(small)
        roots = [x for x in t.order if not t.is_linked(x)]
        sq = [x for x in roots if small.doc.xref_get_key(x, "Subtype")[1] == "/Square" and
              t.replies(x)]
        self.assertEqual([ln.text for _d, ln in t.replies(sq[0])],
                         ["Reply \u00e9\u00e8 \u2603 <&>", "Second level"])

    def test_replies_sent_back_attach_to_the_markups_already_there(self):
        v = self.marked_up()
        recs, _ = xfdf.records(v.doc)
        # a colleague replies in their copy and sends all the comments back
        theirs = self.view()
        theirs.import_comments(xfdf.from_xfdf(xfdf.to_xfdf(recs)))
        t = self.threads(theirs)
        note = [x for x in t.order if not t.is_linked(x) and
                theirs.doc.xref_get_key(x, "Subtype")[1] == "/Text"]
        sq = [x for x in t.order if t.replies(x)][0]
        theirs.reply_to(0, sq, "From the colleague")
        back = xfdf.to_xfdf(xfdf.records(theirs.doc)[0])
        rep = v.import_comments(xfdf.from_xfdf(back))
        self.assertEqual(rep.added, 1)
        self.assertEqual(rep.unchanged, len(recs))
        t = self.threads(v)
        texts = [ln.text for x in t.order if not t.is_linked(x) for _d, ln in t.replies(x)]
        self.assertIn("From the colleague", texts)
        self.assertEqual(note, note)

    def test_xfdf_from_another_program(self):
        """An XFDF file as Acrobat writes one (no KanzonasPDF style): a highlight with a
        reply and a status, a cloudy square, a polygon and an ink drawing."""
        data = b"""<?xml version="1.0" encoding="UTF-8" ?>
<xfdf xmlns="http://ns.adobe.com/xfdf/" xml:space="preserve"><annots>
<highlight color="#FFFF00" creationdate="D:20261101090000-05'00'" flags="print"
 date="D:20261101090000-05'00'" name="0d9c3a3e-aaaa" page="0"
 coords="72,754.9,150,754.9,72,738.4,150,738.4" rect="71,737,151,756"
 subject="Highlight" title="Reviewer One"><contents>Rephrase this</contents>
 <popup flags="print,nozoom,norotate" open="no" page="0" rect="400,600,580,700"/></highlight>
<text color="#FFFF00" creationdate="D:20261102090000-05'00'" flags="print,nozoom,norotate"
 date="D:20261102090000-05'00'" name="0d9c3a3e-bbbb" page="0" rect="71,737,91,757"
 subject="Sticky Note" title="Author Two" icon="Comment" inreplyto="0d9c3a3e-aaaa"
 replyType="reply"><contents>Done</contents></text>
<text color="#FFFF00" creationdate="D:20261102090100-05'00'"
 flags="hidden,print,nozoom,norotate" date="D:20261102090100-05'00'"
 name="0d9c3a3e-cccc" page="0" rect="71,737,91,757" title="Author Two"
 inreplyto="0d9c3a3e-aaaa" state="Completed" statemodel="Review"
 replyType="reply"><contents>Completed set by Author Two</contents></text>
<square color="#FF0000" date="D:20261101090000" name="0d9c3a3e-dddd" page="1"
 rect="100,100,300,200" width="2" style="cloudy" intensity="2" title="Reviewer One"/>
<polygon color="#0000FF" date="D:20261101090000" name="0d9c3a3e-eeee" page="1"
 rect="300,300,420,420" width="1" title="Reviewer One">
 <vertices>310,310;410,320;360,410</vertices></polygon>
<ink color="#00AA00" date="D:20261101090000" name="0d9c3a3e-ffff" page="1"
 rect="50,500,200,600" width="3" title="Reviewer One">
 <inklist><gesture>60,510;100,590;190,520</gesture></inklist></ink>
</annots><f href="review.pdf"/></xfdf>"""
        v = self.view()
        rep = v.import_comments(xfdf.from_xfdf(data))
        self.assertEqual((rep.added, rep.skipped), (6, {}))
        t = self.threads(v)
        roots = [x for x in t.order if not t.is_linked(x) and
                 v.doc.xref_get_key(x, "Subtype")[1] != "/Popup"]
        self.assertEqual(len(roots), 1)
        hl = roots[0]
        self.assertEqual([(ln.author, ln.text) for _d, ln in t.replies(hl)],
                         [("Author Two", "Done")])
        self.assertEqual(t.status(hl)[0], "Completed")
        self.assertEqual(v.doc.xref_get_key(hl, "T")[1], "Reviewer One")
        page = v.doc[0]
        a = page.load_annot(hl)
        self.assertEqual(a.type[1], "Highlight")
        self.assertEqual(a.info["content"], "Rephrase this")
        self.assertIsNotNone(a.popup_rect)
        del a, page
        page = v.doc[1]
        kinds = sorted(a.type[1] for a in page.annots())
        self.assertEqual(kinds, ["Ink", "Polygon", "Square"])
        sq = [a for a in page.annots() if a.type[1] == "Square"][0]
        self.assertEqual(sq.border.get("clouds"), 2)
        self.assertEqual(v.doc.xref_get_key(sq.xref, "AP")[0], "dict")     # (drawn by MuPDF)
        ink = [a for a in page.annots() if a.type[1] == "Ink"][0]
        self.assertEqual([[tuple(round(c) for c in p) for p in g] for g in ink.vertices],
                         [[(60, 792 - 510), (100, 792 - 590), (190, 792 - 520)]])
        # exported again, it says the same
        recs, _ = xfdf.records(v.doc)
        again = {r["keys"]["NM"]: r for r in xfdf.from_xfdf(xfdf.to_xfdf(recs))}
        self.assertEqual(again["0d9c3a3e-bbbb"]["irt"], "0d9c3a3e-aaaa")
        self.assertEqual(again["0d9c3a3e-cccc"]["keys"]["State"], "Completed")
        self.assertEqual(again["0d9c3a3e-eeee"]["keys"]["Vertices"],
                         [310, 310, 410, 320, 360, 410])

    def test_bad_files(self):
        with self.assertRaises(ValueError):
            xfdf.from_xfdf(b"<notxfdf/>")
        with self.assertRaises(ValueError):
            xfdf.from_xfdf(b"<?xml version='1.0'?><!DOCTYPE x [<!ENTITY a 'b'>]><xfdf/>")
        with self.assertRaises(ValueError):
            xfdf.from_fdf(b"%PDF-1.7 nothing")
        # an element of a kind not exchanged, a reference smuggled into a value: left out
        recs = xfdf.from_xfdf(
            b'<xfdf xmlns="http://ns.adobe.com/xfdf/"><annots>'
            b'<sound page="0" rect="1,2,3,4"/>'
            b'<square page="0" rect="10,10,50,50" color="#FF0000" icon="X 1 0 R"/>'
            b'</annots></xfdf>')
        v = self.view()
        rep = v.import_comments(recs)
        self.assertEqual(rep.added, 1)
        self.assertEqual(sum(rep.skipped.values()), 1)
        x = v.doc[0].annot_xrefs()[0][0]
        self.assertEqual(v.doc.xref_get_key(x, "Name")[0], "null")

    def test_pictures_are_not_exported(self):
        v = self.view()
        self.add(v, 0, model("image", rect=R(100, 100, 160, 140),
                             image_bytes=pymupdf.Pixmap(pymupdf.csRGB, (0, 0, 4, 4), 0)
                             .tobytes("png")))
        self.rect(v)
        recs, skipped = xfdf.records(v.doc)
        self.assertEqual(len(recs), 1)
        self.assertEqual(sum(skipped.values()), 1)


# ---- summary ---------------------------------------------------------------------------------
class Summary(Base):
    def test_entries_and_pdf(self):
        v = self.view()
        a = self.rect(v)
        self.add(v, 1, model("note", rect=R(300, 300, 320, 320), text="Second page note"))
        r = v.reply_to(0, a, "A reply in the summary")
        v.reply_to(0, r, "Deeper")
        v.set_review_status(0, [a], "Completed")
        items = review.entries(v.doc)
        self.assertEqual([(e["page"], e["text"], e["status"], [x[3] for x in e["replies"]])
                          for e in items],
                         [(0, "a box", "Completed", ["A reply in the summary", "Deeper"]),
                          (1, "Second page note", "", [])])
        for sort in review.SORTS:
            for thumbs in (True, False):
                out = review.summarize(v.doc, sort, thumbs, "doc.pdf")
                text = " ".join(" ".join(out[i].get_text().split())
                                for i in range(out.page_count))
                for want in ("Comment summary", "a box", "A reply in the summary", "Deeper",
                             "Status: Completed", "Second page note", "Tester"):
                    self.assertIn(want, text, (sort, thumbs))
                images = sum(len(out[i].get_images()) for i in range(out.page_count))
                self.assertEqual(images, 2 if thumbs and sort == "page" else 0, (sort, thumbs))
                out.close()
        out = review.summarize(v.doc, "page", True)
        text = out[0].get_text()
        self.assertLess(text.index("Page 1"), text.index("a box"))
        self.assertLess(text.index("a box"), text.index("Page 2"))

    def test_sorted_by_author_and_date(self):
        items = [{"page": 0, "y": 5, "author": "b", "when": "2", "type": "X"},
                 {"page": 1, "y": 1, "author": "a", "when": "3", "type": "W"},
                 {"page": 0, "y": 1, "author": "c", "when": "1", "type": "Y"}]
        self.assertEqual([e["author"] for e in review.sorted_entries(items, "page")],
                         ["c", "b", "a"])
        self.assertEqual([e["author"] for e in review.sorted_entries(items, "author")],
                         ["a", "b", "c"])
        self.assertEqual([e["author"] for e in review.sorted_entries(items, "date")],
                         ["c", "b", "a"])
        self.assertEqual([e["author"] for e in review.sorted_entries(items, "type")],
                         ["a", "b", "c"])

    def test_summarize_opens_a_new_tab(self):
        from kanzonas import review_ui
        from kanzonas.main_window import MainWindow
        path = sample(self.path("w.pdf"))
        win = MainWindow()
        self.addCleanup(win.deleteLater)
        win.open_file(path)
        v = win.view()
        self.rect(v)
        n = win.tabs.count()
        s = review_ui.summarize_comments(win, v, ask=False)
        self.assertEqual(win.tabs.count(), n + 1)
        self.assertIn("a box", s.doc[0].get_text())
        for w in (s, v):
            w.dirty = False


# ---- the Markups list ------------------------------------------------------------------------
class MarkupsListThreads(Base):
    def panel(self, v):
        from kanzonas.markups_panel import MarkupsPanel
        p = MarkupsPanel()
        self.addCleanup(p.deleteLater)
        p.refresh(v.doc)
        return p

    def rows(self, p):
        t = p.table
        return [(t.item(r, 1).text(), t.item(r, 2).text().strip(), t.isRowHidden(r))
                for r in range(t.rowCount())]

    def test_threads_indented_collapsible_and_sorted_together(self):
        v = self.view()
        a = self.rect(v, box=(100, 100, 150, 150))
        b = self.add(v, 0, model("ellipse", rect=R(300, 300, 360, 360), text="zz ellipse"))
        r1 = v.reply_to(0, a, "first")
        v.reply_to(0, r1, "nested")
        v.reply_to(0, b, "on the ellipse")
        p = self.panel(v)
        self.assertEqual(self.rows(p), [
            ("Rectangle", "a box", False), ("\u21b3 Reply", "first", False),
            ("    \u21b3 Reply", "nested", False),
            ("Ellipse", "zz ellipse", False), ("\u21b3 Reply", "on the ellipse", False)])
        self.assertEqual(p.table.item(0, 7).text(), "\u25be 2")
        self.assertEqual(p.count.text(), "2 of 2")
        # folded
        p._clicked(0, 7)
        self.assertEqual([h for *_x, h in self.rows(p)], [False, True, True, False, False])
        self.assertEqual(p.table.item(0, 7).text(), "\u25b8 2")
        p._clicked(0, 7)
        self.assertEqual([h for *_x, h in self.rows(p)], [False] * 5)
        # sorted by any column, each thread stays under its markup
        for col, order in ((2, Qt.DescendingOrder), (2, Qt.AscendingOrder),
                           (1, Qt.DescendingOrder), (3, Qt.AscendingOrder),
                           (0, Qt.DescendingOrder)):
            p.table.sortItems(col, order)
            texts = [x[1] for x in self.rows(p)]
            k = texts.index("a box")
            self.assertEqual(texts[k:k + 3], ["a box", "first", "nested"], (col, order))
            k = texts.index("zz ellipse")
            self.assertEqual(texts[k:k + 2], ["zz ellipse", "on the ellipse"], (col, order))
        # the text filter finds a markup by its replies' words
        p.text_filter.setText("nested")
        self.assertEqual(sorted(x[1] for x in self.rows(p) if not x[2]),
                         ["a box", "first", "nested"])

    def test_list_follows_edits_as_a_fresh_list(self):
        v = self.view()
        a = self.rect(v)
        p = self.panel(v)
        v.take_markup_changes()
        r = v.reply_to(0, a, "added later")
        p.refresh(v.doc, v.take_markup_changes())
        fresh = self.panel(v)
        self.assertEqual(self.rows(p), self.rows(fresh))
        self.assertEqual(self.rows(p)[1], ("\u21b3 Reply", "added later", False))
        v.delete_reply(0, r)
        p.refresh(v.doc, v.take_markup_changes())
        self.assertEqual(self.rows(p), [("Rectangle", "a box", False)])

    def test_reply_rows_edit_and_delete_the_reply(self):
        from kanzonas.main_window import MainWindow
        path = sample(self.path("w.pdf"))
        win = MainWindow()
        self.addCleanup(win.deleteLater)
        win.open_file(path)
        v = win.view()
        a = self.rect(v)
        r = v.reply_to(0, a, "reply")
        with mock.patch("kanzonas.dialogs.get_text", return_value=("changed", True)):
            win._edit_markup(0, r)
        self.assertEqual(v.doc.xref_get_key(r, "Contents")[1], "changed")
        win._delete_markup(0, r)
        self.assertIn(a, [x for x, *_ in v.doc[0].annot_xrefs()])
        self.assertNotIn(r, [x for x, *_ in v.doc[0].annot_xrefs()])
        # Review > Reply... and Set status work on the selection
        v.select_xref(0, a)
        with mock.patch("kanzonas.dialogs.get_text", return_value=("menu reply", True)):
            win.a_reply.trigger()
        win.status_actions["Rejected"].trigger()
        t = self.threads(v)
        self.assertEqual([ln.text for _d, ln in t.replies(a)], ["menu reply"])
        self.assertEqual(t.status(a)[0], "Rejected")
        win._status_menu_shown()
        self.assertTrue(win.status_actions["Rejected"].isChecked())
        v.dirty = False

    def test_thousands_of_markups_with_replies_list_quickly(self):
        d = pymupdf.open()
        page = d.new_page()
        xs = []
        for k in range(2000):
            a = page.add_rect_annot(R(k % 50 * 10, k // 50 * 10, k % 50 * 10 + 8,
                                      k // 50 * 10 + 8))
            xs.append(a.xref)
        del a
        for x in xs[::10]:
            review.add_reply(page, x, "reply", "R")
        review.set_status(page, xs[::5], "Accepted", "R")
        t0 = time.perf_counter()
        rows = MP.collect(d)
        took = time.perf_counter() - t0
        self.assertEqual(sum(1 for r in rows if not r[9]), 2000)
        self.assertEqual(sum(1 for r in rows if r[9]), 200)
        self.assertEqual(sum(1 for r in rows if r[7]), 400)
        self.assertLess(took, 5.0)
        t0 = time.perf_counter()
        t = review.Threads(page)
        self.assertLess(time.perf_counter() - t0, 0.5)
        self.assertEqual(len(t.links), 600)


if __name__ == "__main__":
    unittest.main()
