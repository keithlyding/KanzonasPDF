"""A randomized editing battery, run by hand before a release (the short version in
tests/test_battery_random.py runs in every build):

    QT_QPA_PLATFORM=offscreen python tests/battery_random.py OUT_FOLDER [--ops N] [--seed S]
        [--undo-limit N] [--copy] [--render-every N]

Thousands of random edits through the app's own steps (the ones the menus, tools and keys
call: markups of every kind added, moved, resized, recolored, retyped, duplicated, restacked
and deleted; page text added, edited and replaced; pictures and shapes of the page moved,
turned and deleted; words styled in Edit text and Add text (bold, italic, underline,
strikethrough, color, size); pages rotated, inserted, duplicated, deleted, moved, reordered,
cropped, scanned in (File > Scan into the current document, with pictures made here) and
replaced from another PDF (Replace pages); bookmarks, watermarks, form fields, flattening, redaction marks applied), in a main
window, with undo and redo runs and saves mixed in, and the page layout (View > Page layout:
single page, continuous, two pages, cover page) and zoom changed between edits. Undo goes through MuPDF's journal
(kanzonas/undo_journal.py), which MuPDF makes fragile: this is what finds its bugs.

Checked:
- after every step: nothing raised and no edit failed (modify's "Edit failed" box), the view
  agrees with the document (its pages, their sizes, its cached markup boxes and text, the
  pages a single-page or two-page layout shows), every
  markup reads back and is on one page only; an edit that changes the document adds one undo
  step and an undo or redo moves one step across (a mirror of the history is kept).
  An undo must bring back exactly the document as it was before that step, and a redo
  exactly as it was after it, compared byte for byte once written out the same way (see
  canon: what legitimately differs is left out there);
- every 25 steps: each page as the view draws it (through its caches) is the page as a view
  opened fresh on the same document draws it;
- every 100 steps: Save, the file opened again: the same pages, text, markups, fields, links,
  bookmarks and attachments as in the window;
- at the end: undo all the way back gives the document from before the oldest step kept
  (the opened file, with --undo-limit 0, the default: no limit), and redo all the way forward
  gives the final document.

A failure records the seed and step, and the run goes on (from the document as it is) up to 5
failures. Writes OUT_FOLDER/battery_random.log (and the two documents of a byte-for-byte
mismatch, or the two pictures of a page drawn differently) and exits 1 if anything failed.
By default the history has no limit, so the end goes back to the opened file through every
step; --undo-limit 30 keeps the app's own limit (UNDO_LIMIT); --copy runs with a copy per
edit instead of the journal (as up to 1.6, and where the journal can't serve);
--render-every N draws and compares the pages every N steps (1: after every step).
"""

import hashlib
import os
import random
import re
import sys
import tempfile
import time
import traceback
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import tests  # noqa: E402,F401  (settings in a scratch folder, Qt torn down in order)

import pymupdf  # noqa: E402
from PySide6.QtCore import QPoint  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import annotations, dialogs, page_widget  # noqa: E402
import kanzonas.document_view as DV  # noqa: E402

MAX_FAILURES = 5
# what differs between two writes of the same document (dates, random names): blanked
VOLATILE = ("NM", "M", "CreationDate", "ModDate", "Producer", "KZGroup")


# ---- the document ----------------------------------------------------------------------------
PARAGRAPH = ("The contractor agrees to deliver the panels by the end of the month. Every "
             "panel is tested before it leaves the shop, and the test sheet goes with it.")


def png_bytes(w=40, h=30, rgb=(20, 120, 220)):
    pm = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, w, h), False)
    pm.set_rect(pm.irect, rgb)
    return pm.tobytes("png")


def sample(path, pages=4):
    """Text (lines and a paragraph), drawings, a picture, a markup per page, a form field, a
    link, bookmarks, metadata and an attachment."""
    d = pymupdf.open()
    for i in range(pages):
        p = d.new_page(width=612, height=792)
        p.insert_text((72, 72), "Page %d Contractor agrees" % (i + 1), fontsize=12)
        p.insert_text((72, 100), "Second line of text here", fontsize=11)
        p.insert_textbox(pymupdf.Rect(72, 120, 540, 190), PARAGRAPH, fontsize=11)
        p.draw_rect((100, 200, 300, 300), color=(0, 0, 1), width=2)
        p.draw_line((100, 350), (400, 380), color=(1, 0, 0), width=1)
        p.draw_circle((450, 250), 30, color=(0, 0.5, 0), fill=(0.8, 1, 0.8))
        a = p.add_rect_annot((350, 400, 450, 470))
        a.set_colors(stroke=(0, 0.5, 0))
        a.update()
        if i == 1:
            w = pymupdf.Widget()
            w.field_name = "who"
            w.field_type = pymupdf.PDF_WIDGET_TYPE_TEXT
            w.rect = pymupdf.Rect(72, 500, 300, 525)
            p.add_widget(w)
        if i == 2:
            p.insert_link({"kind": pymupdf.LINK_GOTO, "from": pymupdf.Rect(72, 600, 200, 620),
                           "page": 0})
        p.insert_image((400, 600, 500, 680), stream=png_bytes(rgb=(20 + 50 * i, 120, 220)))
    d.set_toc([[1, "First", 1], [2, "Second", 2], [1, "Third", 3]])
    d.set_metadata({"title": "Battery", "author": "Me"})
    d.embfile_add("note.txt", b"attached text")
    d.save(path, garbage=3, deflate=True)
    d.close()
    return path


def revision(path):
    """The new revision Replace pages takes drawings from: a page of the same size, a bigger
    one, a portrait page turned to show landscape, a half-size one and one cropped off its
    media box's corner, each with text, drawings, a picture, a sheet number and a markup of
    its own (which doesn't come along); two of them draw on layers (one off)."""
    d = pymupdf.open()
    for i, (w, h, turn, crop) in enumerate([(612, 792, 0, None), (1224, 792, 0, None),
                                            (612, 792, 90, None), (306, 396, 0, None),
                                            (700, 900, 0, (40, 60, 652, 852))]):
        p = d.new_page(width=w, height=h)
        if crop:
            p.set_cropbox(pymupdf.Rect(crop))
        p.set_rotation(turn)
        m = p.derotation_matrix
        r = p.rect
        p.insert_text(pymupdf.Point(60, 60) * m, "Revision B sheet %d" % (i + 1),
                      fontsize=14, rotate=turn)
        p.insert_text(pymupdf.Point(r.width - 150, r.height - 30) * m,
                      "SHEET NO: R-%d" % (i + 1), fontsize=9, rotate=turn)
        p.draw_rect(pymupdf.Rect(20, 20, r.width - 20, r.height - 20) * m, color=(0, 0, 0.6),
                    width=1.5)
        p.draw_line(pymupdf.Point(40, 120) * m, pymupdf.Point(r.width - 40, 200) * m,
                    color=(0.7, 0, 0), width=1)
        p.insert_image(pymupdf.Rect(80, 220, 160, 280) * m,
                       stream=png_bytes(rgb=(200, 40 * i, 90)), rotate=turn)
        a = p.add_circle_annot(pymupdf.Rect(200, 300, 260, 340) * m)
        a.update()
        if i in (1, 2):         # (drawn on layers: they join the document's layers)
            if i == 1:
                layers = [d.add_ocg("R-WALL", on=True), d.add_ocg("R-HIDDEN", on=False)]
            p.insert_text(pymupdf.Point(60, 330) * m, "on a layer", fontsize=11, rotate=turn,
                          oc=layers[0])
            p.draw_line(pymupdf.Point(60, 350) * m, pymupdf.Point(300, 350) * m,
                        color=(0, 0.5, 0), width=2, oc=layers[1])
    d.save(path, garbage=3, deflate=True)
    d.close()
    return path


# ---- comparing documents ---------------------------------------------------------------------
def canon(data):
    """A document's bytes (as written by DocumentView._snapshot) as bytes that two documents
    with the same content share. Left out, because they differ between two writes of the
    same content: dates and the markups' random names (VOLATILE), the file /ID, the producer,
    font subset prefixes; object numbers and unused objects (garbage=4 renumbers and drops
    them: an undone edit leaves the numbers of the objects it made unused); compression
    (expanded)."""
    d = pymupdf.open("pdf", data)
    for x in range(1, d.xref_length()):
        try:
            keys = d.xref_get_keys(x)
        except Exception:
            continue
        for k in VOLATILE:
            if k in keys:
                d.xref_set_key(x, k, "null")
    d.xref_set_key(-1, "ID", "null")
    d.set_metadata({k: v for k, v in (d.metadata or {}).items()
                    if k in ("title", "author", "subject", "keywords", "creator")})
    raw = d.tobytes(garbage=4, expand=255, no_new_id=True)
    d.close()
    return re.sub(rb"/[A-Z]{6}\+", b"/XXXXXX+", raw)


def _r(rect, nd=1):
    return tuple(round(float(v), nd) for v in rect)


def summary(doc):
    """What a person sees of a document, as plain values: per page its size, turn, crop,
    text, pictures, drawings, markups (kind, place, colors, text), fields and links; the
    bookmarks, the title and author, the attachments."""
    pages = []
    for i in range(doc.page_count):
        page = doc[i]               # (kept alive while its markups are read)
        annots = []
        for a in page.annots():
            colors = a.colors or {}
            annots.append((a.type[1], _r(a.rect), (a.info or {}).get("content", ""),
                           _r(colors.get("stroke") or (), 2), _r(colors.get("fill") or (), 2)))
        widgets = [(w.field_name, w.field_value) for w in page.widgets()]
        links = [(ln.get("kind"), _r(ln["from"]), ln.get("page"), ln.get("uri"))
                 for ln in page.get_links()]
        pages.append({
            "rotation": page.rotation, "mediabox": _r(page.mediabox), "cropbox": _r(page.cropbox),
            "text": " ".join(page.get_text().split()),
            "images": len(page.get_images()),
            "drawings": len(page.get_cdrawings()),
            "annots": annots, "widgets": widgets, "links": links})
    meta = doc.metadata or {}
    return {"pages": pages, "toc": doc.get_toc(simple=True),
            "meta": (meta.get("title"), meta.get("author")),
            "files": sorted(doc.embfile_names())}


def summary_diff(a, b):
    """Where two summaries differ, in a few words."""
    out = []
    for k in ("toc", "meta", "files"):
        if a[k] != b[k]:
            out.append("%s: %r != %r" % (k, a[k], b[k]))
    if len(a["pages"]) != len(b["pages"]):
        out.append("pages: %d != %d" % (len(a["pages"]), len(b["pages"])))
    for i, (p, q) in enumerate(zip(a["pages"], b["pages"])):
        for k in p:
            if p[k] != q[k]:
                out.append("page %d %s: %r != %r" % (i, k, p[k], q[k]))
    return "; ".join(out)[:3000] or "(the same)"


class State:
    """A document as it is at one moment: its canonical bytes (digest) and summary."""

    def __init__(self, view):
        data = view._snapshot()
        self.bytes = canon(data)
        self.digest = hashlib.sha1(self.bytes).hexdigest()
        self.summary = summary(view.doc)

    def same(self, other):
        return self.digest == other.digest


# MuPDF draws a page's content a level or two of color apart (out of 255) depending on
# its markups: one with a blend mode (a highlight multiplies) makes it draw the whole page
# as a transparency group. Up to 1.8 the view kept a content render made before such a
# markup was added (and MuPDF's page kept its old answer: up to 5 levels off); since 1.9 it
# works the answer out again and draws the content again when it changes
# (render_layers.transparency). A margin of a few levels is kept; content drawn from old
# caches is off by far more (a line missing, markups in another order)
SHADE = 3


def _differ(a, b):
    """The two QImages (the same size) differ by more than SHADE levels somewhere."""
    import numpy as np
    from PySide6.QtGui import QImage
    arrays = []
    for img in (a, b):
        img = img.convertToFormat(QImage.Format_RGB32)
        arr = np.frombuffer(img.constBits(), np.uint8, img.sizeInBytes())
        arrays.append(arr.reshape(img.height(), img.bytesPerLine())[:, :img.width() * 4]
                      .astype(np.int16))
    return int(np.abs(arrays[0] - arrays[1]).max()) > SHADE


# edits the app refuses on purpose by raising in the edit, which DocumentView.modify shows
# in its "Edit failed" box and takes back (the history check makes sure nothing changed)
REFUSALS = (
    # Edit objects / Edit text on a page with redaction marks not applied: taking text out
    # of a page applies every redaction mark on it (text_edit.py)
    "Apply or remove the redaction marks on this page before",
)


class Failed(AssertionError):
    pass


# ---- the battery -----------------------------------------------------------------------------
class Battery:
    def __init__(self, out, ops, seed, undo_limit=0, journal=True, log=None, render_every=25):
        self.render_every = render_every
        self.out, self.ops, self.seed = out, ops, seed
        self.rnd = random.Random(seed)
        self.undo_limit = undo_limit
        self.journal = journal
        self.log = log or print
        self.failures = []
        self.counts = {}
        self.boxes = []             # messages shown during the step
        self.trail = []             # the latest steps' names, for the failure messages
        self.top = None             # the step on top of the undo list after the last step
        self.trimmed = 0            # oldest steps dropped by the limits on the history

    # (the app's dialogs answered without a person)
    def _patches(self):
        battery = self

        def box(kind):
            def show(*a, **k):
                text = a[2] if len(a) > 2 else k.get("text", "")
                battery.boxes.append((kind, a[1] if len(a) > 1 else "", str(text)))
                return QMessageBox.Yes if kind == "question" else QMessageBox.Ok
            return show
        picture = os.path.join(self.out, "picture.png")
        with open(picture, "wb") as f:
            f.write(png_bytes(60, 40, (200, 60, 30)))
        attachment = os.path.join(self.out, "attached.txt")
        with open(attachment, "w") as f:
            f.write("an attached file")
        self.revision = revision(os.path.join(self.out, "revision.pdf"))
        with open(self.revision, "rb") as f:
            self.revision_hash = hashlib.sha256(f.read()).hexdigest()
        files = {"Insert image": picture, "Replace pages with pages from": self.revision}
        return [mock.patch.object(QMessageBox, name, box(name))
                for name in ("information", "warning", "critical", "question")] + [
            mock.patch.object(QMessageBox, "exec", lambda self: QMessageBox.Cancel),
            mock.patch.object(dialogs, "get_text",
                              lambda parent, title, label, text="":
                              (battery.typed(text), True)),
            mock.patch.object(dialogs, "open_file",
                              lambda parent, title, f="", folder="":
                              files.get(title, attachment)),
            mock.patch.object(DV, "USE_JOURNAL", self.journal),
            mock.patch.object(DV, "UNDO_LIMIT", self.undo_limit or 10 ** 9)]

    def typed(self, old=""):
        words = ["alpha", "bravo", "charlie", "delta", "echo", "foxtrot", "golf", "hotel"]
        new = " ".join(self.rnd.choice(words) for _ in range(self.rnd.randint(1, 4)))
        return (old + " " + new).strip() if old and self.rnd.random() < 0.5 else new

    def run(self):
        patches = self._patches()
        for p in patches:
            p.start()
        try:
            return self._run()
        finally:
            for p in reversed(patches):
                p.stop()

    def _run(self):
        from kanzonas import undo_journal
        from kanzonas.main_window import MainWindow
        undo_journal.install()      # (the app's patches of PyMuPDF are in, journal or not)
        path = sample(os.path.join(self.out, "random.pdf"))
        self.win = win = MainWindow()
        win.resize(1200, 900)
        win.show()
        win.open_file(path)
        APP.processEvents()
        v = self.v = win.view()
        v.set_zoom(0.5)
        self.cur = State(v)
        start = self.cur
        self.undone = []            # the states before each undo step (mirrors v._undo)
        self.redone = []            # the states after each redo step (mirrors v._redo)
        table = self.table()
        fns = [f for f, w in table for _ in range(w)]
        roundtrips = renders = 0
        t0 = time.perf_counter()
        for i in range(self.ops):
            fn = self.rnd.choice(fns)
            name = fn.__name__[3:]
            self.step, self.name = i, name
            self.counts[name] = self.counts.get(name, 0) + 1
            self.trail.append(name)
            try:
                self.boxes = []
                kind = fn() or "edit"
                APP.processEvents()         # (the panels, page list and timers react)
                self.check_boxes()
                self.after(kind)
                self.check_view()
                if i % self.render_every == self.render_every - 1:
                    self.check_render()
                    renders += 1
                if i % 100 == 99:
                    self.roundtrip()
                    roundtrips += 1
            except Exception:
                self.fail(traceback.format_exc())
                if len(self.failures) >= MAX_FAILURES:
                    break
                self.resync()
        took = time.perf_counter() - t0
        done = self.step + 1
        self.step, self.name = self.ops, "undo all"
        final = self.cur
        n_undo = 0
        try:
            while v.can_undo():
                self.do_undo()
                self.after("undo")
                n_undo += 1
            back = self.cur
            first = start if not self.trimmed else None     # (else checked step by step)
            if first is not None and not back.same(first):
                self.mismatch("undo all the way didn't give the opened document", first, back)
            self.name = "redo all"
            for _ in range(n_undo):
                self.do_redo()
                self.after("redo")
            if not self.cur.same(final):
                self.mismatch("redo all the way didn't give the final document", final,
                              self.cur)
            self.check_view()
            self.check_render()
        except Exception:
            self.fail(traceback.format_exc())
        stats = ("%d steps in %.0f s (%s); %d pages, %d markups at the end; %d save/open round "
                 "trips, %d render checks; %d steps undone and redone at the end" % (
                     done, took, ", ".join("%s %d" % kv for kv in sorted(self.counts.items())),
                     v.doc.page_count, sum(len(p["annots"]) for p in final.summary["pages"]),
                     roundtrips, renders, n_undo))
        v.dirty = False
        win.close()
        return stats

    # ---- bookkeeping: the mirror of the undo history ------------------------------------
    def fail(self, text):
        msg = "seed %d, step %d (%s; the steps before: %s): %s" % (
            self.seed, self.step, self.name, ", ".join(self.trail[-12:-1]), text.rstrip())
        self.failures.append(msg)
        self.log("FAIL " + msg)

    def mismatch(self, what, want, got):
        tag = "s%d-step%d" % (self.seed, self.step)
        for name, st in (("want", want), ("got", got)):
            with open(os.path.join(self.out, "%s-%s.pdf" % (tag, name)), "wb") as f:
                f.write(st.bytes)
        raise Failed("%s: %s (documents: %s-want.pdf, -got.pdf)" % (
            what, summary_diff(want.summary, got.summary), tag))

    def resync(self):
        """After a failure: go on from the document as it is now."""
        v = self.v
        try:
            if v._inline is not None:
                v._inline.cancel()
            self.cur = State(v)
        except Exception:
            self.fail("can't read the document any more:\n" + traceback.format_exc())
            self.failures.extend(["(stopped)"] * MAX_FAILURES)
            return
        self.undone = [None] * len(v._undo)
        self.redone = [None] * len(v._redo)
        self.top = v._undo[-1] if v._undo else None

    def check_boxes(self):
        for kind, title, text in self.boxes:
            if title == "Edit failed" and text.startswith(REFUSALS):
                continue                # (refused on purpose, nothing changed: see REFUSALS)
            if kind == "critical" or title in ("Edit failed", "Save failed"):
                raise Failed("%s box %r: %s" % (kind, title, text))

    def after(self, kind):
        """The step is done: check the history moved as it should, and the document is as
        the mirror says."""
        v = self.v
        before, now = self.cur, State(v)
        nu, nr = len(v._undo), len(v._redo)
        mu, mr = len(self.undone), len(self.redone)
        if kind == "undo":
            if mu == 0:
                if not now.same(before):
                    self.mismatch("Undo with nothing to undo changed the document", before, now)
            else:
                if nu != mu - 1 or not self.budget_trim(nr, mr + 1, keep=0):
                    raise Failed("Undo: %d/%d steps to undo/redo, expected %d/%d" % (
                        nu, nr, mu - 1, mr + 1))
                want = self.undone.pop()
                if want is not None and not now.same(want):
                    self.mismatch("Undo didn't bring back the document from before the step",
                                  want, now)
                self.redone.append(before)
                del self.redone[:mr + 1 - nr]       # (see budget_trim)
        elif kind == "redo":
            if mr == 0:
                if not now.same(before):
                    self.mismatch("Redo with nothing to redo changed the document", before, now)
            else:
                if nr != mr - 1 or not self.budget_trim(nu, mu + 1):
                    raise Failed("Redo: %d/%d steps to undo/redo, expected %d/%d" % (
                        nu, nr, mu + 1, mr - 1))
                want = self.redone.pop()
                if want is not None and not now.same(want):
                    self.mismatch("Redo didn't give the document as it was after the step",
                                  want, now)
                self.undone.append(before)
                if mu + 1 - nu:
                    del self.undone[:mu + 1 - nu]
                    self.trimmed += mu + 1 - nu
        elif kind == "save":
            # (Save cuts the fonts added down to the letters used, folded into the latest
            # step: the bytes may change, never what the document shows)
            if (nu, nr) != (mu, mr):
                raise Failed("Save changed the history: %d/%d steps, expected %d/%d" % (
                    nu, nr, mu, mr))
            if now.summary != before.summary:
                raise Failed("Save changed the document: " +
                             summary_diff(before.summary, now.summary))
        elif kind == "none":
            if not now.same(before) or (nu, nr) != (mu, mr):
                self.mismatch("a step that changes nothing changed the document", before, now)
        else:
            # (a new step is a new object on top of the list: at the limit the list keeps
            # its length, the oldest step dropped)
            pushed = bool(v._undo) and v._undo[-1] is not self.top
            if pushed:
                trimmed = mu + 1 - nu
                if not self.budget_trim(nu, mu + 1):
                    raise Failed("an edit left %d steps to undo, expected %d" % (nu, mu + 1))
                if trimmed:
                    del self.undone[:trimmed]
                    self.trimmed += trimmed
                self.undone.append(before)
            elif nu != mu:
                raise Failed("an edit left %d steps to undo, expected %d" % (nu, mu))
            elif not now.same(before):
                self.mismatch("an edit changed the document without an undo step", before,
                              now)
            elif not self.budget_trim(nr, mr, keep=0):
                # (an edit refused or taken back is no edit: the steps to redo stay. One
                # refused after a change had lost them: Edit objects, seed 5, 1.9)
                raise Failed("an edit that changed nothing left %d steps to redo, expected %d"
                             % (nr, mr))
            if pushed or not now.same(before):
                if nr:
                    raise Failed("an edit left %d steps to redo" % nr)
                self.redone = []
        self.cur = now
        self.top = v._undo[-1] if v._undo else None

    def budget_trim(self, n, expected, keep=1):
        """n steps left in a list where expected were: the same, or the oldest dropped by
        the app's limits (--undo-limit; with a copy per edit, the history's memory budget,
        DocumentView._trim_history, drops whole copies of the document: the steps to redo
        first, all of them if need be, then the oldest to undo but the latest)."""
        return n == expected or (keep <= n < expected and
                                 (self.undo_limit or not self.journal))

    # ---- invariants ---------------------------------------------------------------------
    def check_view(self):
        """The view agrees with the document; every markup reads back."""
        v = self.v
        doc = v.doc
        if doc.is_closed:
            raise Failed("the document is closed")
        n = doc.page_count
        if len(v.pages) != n or len(v.page_rects) != n:
            raise Failed("the view has %d pages (%d sizes), the document %d" % (
                len(v.pages), len(v.page_rects), n))
        # View > Page layout: one page (or spread) at a time shows only those; continuous
        # layouts show every page; two pages side by side: a spread's pages on one row
        shown = [i for i in range(n) if not v.pages[i].isHidden()]
        want = v.spread(v.current_page()) if v.paged() else list(range(n))
        if shown != want:
            raise Failed("the %s layout shows pages %s, not %s" % (v.page_layout, shown, want))
        if v.two_up():
            for i in range(n):
                row = v.spread(i)
                if len(row) == 2 and not v.pages[row[0]].isHidden() and \
                        v.pages[row[0]].y() != v.pages[row[1]].y():
                    raise Failed("pages %s of a spread aren't side by side" % row)
        owner = {}
        for i in range(n):
            page = doc[i]
            for x, *_ in page.annot_xrefs():
                if x in owner:
                    raise Failed("markup %d is on page %d and page %d" % (x, owner[x], i))
                owner[x] = i
            if _r(v.page_rects[i], 2) != _r(page.rect, 2):
                raise Failed("page %d is %s in the view, %s in the document" % (
                    i, v.page_rects[i], page.rect))
            for a in page.annots():
                if a.type[0] != pymupdf.PDF_ANNOT_POPUP and annotations.read(a) is None and \
                        a.type[0] not in (pymupdf.PDF_ANNOT_LINK,):
                    raise Failed("page %d: a %s markup doesn't read back" % (i, a.type[1]))
            boxes = v._card_cache.get(("annotx", i))
            if boxes is not None:
                fresh = sorted((_r(a.rect, 2), a.xref) for a in annotations.each_annot(page)
                               if a.type[0] != pymupdf.PDF_ANNOT_POPUP)
                kept = sorted((_r(r, 2), x) for r, x in boxes)
                if fresh != kept:
                    raise Failed("page %d: the cached markup boxes are old" % i)
            words = v._word_cache.get(i)
            if words is not None:
                del v._word_cache[i]
                if [w[:5] for w in v._words(i)] != [w[:5] for w in words]:
                    raise Failed("page %d: the cached text is old" % i)

    def check_render(self):
        """Each page as the view draws it (through every cache it keeps) is the page as a
        view opened fresh on the same document draws it."""
        v = self.v
        path = os.path.join(self.out, "render-check.pdf")
        with open(path, "wb") as f:
            f.write(v._snapshot())
        fresh = DV.DocumentView(path)
        try:
            fresh.resize(v.width(), v.height())
            fresh.set_zoom(v.zoom)
            for i in range(v.doc.page_count):
                mine, theirs = v.pages[i], fresh.pages[i]
                for view, w in ((v, mine), (fresh, theirs)):
                    page_widget.check_content(view, i)
                    w._render()
                a, b = mine._pix.toImage(), theirs._pix.toImage()
                if a.size() != b.size():
                    raise Failed("page %d is drawn %s, fresh %s" % (i, a.size(), b.size()))
                if a != b and _differ(a, b):
                    a.save(os.path.join(self.out, "s%d-step%d-page%d-view.png" % (
                        self.seed, self.step, i)))
                    b.save(os.path.join(self.out, "s%d-step%d-page%d-fresh.png" % (
                        self.seed, self.step, i)))
                    raise Failed("page %d as the view draws it isn't the page as it is" % i)
        finally:
            fresh.dirty = False
            fresh.close_doc()
            fresh.deleteLater()

    def roundtrip(self):
        """Save (as File > Save does), open the file again: the same document."""
        self.do_save()
        self.after("save")
        with pymupdf.open(self.v.path) as d:
            got = summary(d)
        if got != self.cur.summary:
            raise Failed("saved and opened again: " + summary_diff(self.cur.summary, got))

    # ---- helpers for the operations -----------------------------------------------------
    def page(self):
        return self.rnd.randrange(self.v.doc.page_count)

    def point(self, i, margin=20):
        cb = self.v.doc[i].cropbox
        return pymupdf.Point(self.rnd.uniform(margin, cb.width - margin),
                             self.rnd.uniform(margin, cb.height - margin))

    def box(self, i, lo=20, hi=200):
        a = self.point(i, 30)
        cb = self.v.doc[i].cropbox
        b = pymupdf.Point(min(cb.width - 5, a.x + self.rnd.uniform(lo, hi)),
                          min(cb.height - 5, a.y + self.rnd.uniform(lo, hi)))
        return a, b

    def markups(self, i):
        page = self.v.doc[i]
        out = []
        for a in annotations.each_annot(page):
            if a.type[0] in (pymupdf.PDF_ANNOT_POPUP, pymupdf.PDF_ANNOT_WIDGET,
                             pymupdf.PDF_ANNOT_LINK):
                continue
            out.append(a.xref)
        return out

    def select_some(self):
        """Select one or a few markups of a page (as clicks and Ctrl+clicks do): the page,
        or None when there is none."""
        v = self.v
        pages = [i for i in range(v.doc.page_count) if self.markups(i)]
        if not pages:
            return None
        i = self.rnd.choice(pages)
        xrefs = self.markups(i)
        pick = self.rnd.sample(xrefs, self.rnd.randint(1, min(3, len(xrefs))))
        v.select_xref(i, pick[0])
        for x in pick[1:]:
            v.select_xref(i, x, add=True)
        return i if v.selection is not None else None

    def words(self, i):
        return [w for w in self.v.doc[i].get_text("words") if w[4].strip()]

    def color(self):
        return "#%02x%02x%02x" % tuple(self.rnd.randrange(256) for _ in range(3))

    def do_undo(self):
        self.trail.append("(undo)")
        self.win.a_undo.trigger()

    def do_redo(self):
        self.trail.append("(redo)")
        self.win.a_redo.trigger()

    def do_save(self):
        if not self.win.save():
            raise Failed("Save failed: %s" % self.boxes)

    # ---- the operations (each returns what kind of step it was; None: an edit) -----------
    def table(self):
        return [
            (self.op_shape, 10), (self.op_line, 5), (self.op_poly, 4), (self.op_ink, 3),
            (self.op_textbox, 3), (self.op_callout, 2), (self.op_note, 2), (self.op_stamp, 2),
            (self.op_measure, 2), (self.op_dimension, 3), (self.op_text_markup, 6),
            (self.op_attach, 1), (self.op_legend, 2), (self.op_legend_options, 2),
            (self.op_move, 6), (self.op_nudge, 3), (self.op_resize, 3), (self.op_props, 4),
            (self.op_retype, 3), (self.op_delete, 5), (self.op_duplicate, 2),
            (self.op_copy_paste, 2), (self.op_restack, 2), (self.op_eraser, 2),
            (self.op_add_text, 3), (self.op_edit_text, 3), (self.op_styled_text, 3),
            (self.op_added_block, 3), (self.op_page_text_clip, 3),
            (self.op_object_clip, 3), (self.op_across_pages, 2),
            (self.op_replace_text, 1), (self.op_scan, 1),
            (self.op_picture, 2), (self.op_objects, 4), (self.op_erase_content, 1),
            (self.op_field, 2), (self.op_rotate_page, 3), (self.op_insert_blank, 2),
            (self.op_delete_page, 2), (self.op_move_page, 2), (self.op_reorder, 1),
            (self.op_duplicate_page, 1), (self.op_crop, 2), (self.op_bookmarks, 1),
            (self.op_replace_pages, 2), (self.op_layout, 3),
            (self.op_watermark, 1), (self.op_flatten, 1), (self.op_redact, 2),
            (self.op_undo, 14), (self.op_redo, 9), (self.op_save, 2),
        ]

    def op_shape(self):
        i = self.page()
        a, b = self.box(i)
        tool = self.rnd.choice(["rect", "ellipse", "cloud", "mask", "circle", "placeholder"])
        self.v.apply_drag_tool(i, tool, a, b, False)

    def op_line(self):
        i = self.page()
        a, b = self.box(i)
        self.v.apply_drag_tool(i, self.rnd.choice(["line", "arrow"]), a, b, False)

    def op_poly(self):
        i = self.page()
        pts = [self.point(i, 40) for _ in range(self.rnd.randint(3, 6))]
        tool = self.rnd.choice(["polygon", "polyline", "curve", "m_area", "m_poly",
                                "m_perimeter"])
        self.v.apply_poly(i, tool, pts)

    def op_ink(self):
        i = self.page()
        p = self.point(i, 60)
        pts = [p]
        for _ in range(self.rnd.randint(2, 30)):
            p = pymupdf.Point(p.x + self.rnd.uniform(-8, 8), p.y + self.rnd.uniform(-8, 8))
            pts.append(p)
        self.v.apply_ink(i, pts)

    def op_textbox(self):
        i = self.page()
        a, b = self.box(i, 40, 200)
        self.v.apply_drag_tool(i, "textbox", a, b, self.rnd.random() < 0.3)

    def op_callout(self):
        i = self.page()
        a, b = self.box(i, 30, 120)
        self.v.apply_drag_tool(i, "callout", a, b, False)

    def op_note(self):
        i = self.page()
        self.v.apply_point_tool(i, "note", self.point(i))

    def op_stamp(self):
        i = self.page()
        self.v.place_stamp(i, self.point(i, 80))

    def op_measure(self):
        i = self.page()
        a, b = self.box(i)
        if self.rnd.random() < 0.5:
            self.v.apply_drag_tool(i, self.rnd.choice(["m_length", "m_radius"]), a, b, False)
        else:
            self.v.apply_poly(i, "m_angle", [a, b, self.point(i, 40)])

    def op_dimension(self):
        """Dimensions (dimensions.py): one drawn (its two points and where its line goes, as
        the clicks give them to apply_poly), or one already there with a grip dragged (a
        measured point, or its dimension line nearer or farther: measured again) or its
        arrowheads changed. Moving, restyling and deleting them: the operations for all."""
        v = self.v
        have = [(i, x) for i in range(v.doc.page_count) for x in self.markups(i)
                if self.kind(i, x) == "m_dim"]
        r = self.rnd.random()
        if not have or r < 0.4:
            i = self.page()
            a, b = self.box(i, 20, 250)
            if self.rnd.random() < 0.5:
                b = pymupdf.Point(b.x, a.y)             # (level, as most dimensions are)
            c = (a + b) / 2 + pymupdf.Point(self.rnd.uniform(-60, 60),
                                            self.rnd.uniform(-60, 60))
            v.apply_poly(i, "m_dim", [a, b, c])
            return None
        i, x = self.rnd.choice(have)
        v.select_xref(i, x)
        m = v.selected_model
        if m is None or m["kind"] != "m_dim":
            v.clear_selection()
            return "none"
        if r < 0.85:
            # a grip dragged, as page_widget's handles do it (v0, v1: a measured point; v2:
            # the dimension line)
            k = self.rnd.randrange(3)
            to = m["points"][k] + pymupdf.Point(self.rnd.uniform(-50, 50),
                                                self.rnd.uniform(-50, 50))
            new = annotations.with_endpoint(m, k, to)
            if abs(new["points"][1] - new["points"][0]) < 1:
                v.clear_selection()
                return "none"
            v.commit_model(i, x, new)
        else:
            heads = [h for h in ("closed", "open", "slash", "dot", "none")
                     if h != m["props"].get("head")]
            v.update_selected_props({"head": self.rnd.choice(heads)})
        v.clear_selection()

    def kind(self, i, x):
        """The kind of markup x of page i (annotations.read), or None."""
        page = self.v.doc[i]
        try:
            m = annotations.read(page.load_annot(x))
        except Exception:
            m = None
        del page
        return m["kind"] if m else None

    def op_legend(self):
        # a legend of the page's or the whole document's markups (legend.py): it draws
        # itself again inside the steps that change what it lists, so every undo and redo
        # after it is checked with it there
        i = self.page()
        a, b = self.box(i, 60, 240)
        props = dict(annotations.tool_props("legend"),
                     scope=self.rnd.choice(["page", "document"]),
                     count=self.rnd.random() < 0.8, totals=self.rnd.random() < 0.8,
                     border=self.rnd.random() < 0.8)
        with mock.patch.object(self.v, "tool_props", lambda tool: dict(props)):
            self.v.apply_drag_tool(i, "legend", a, b, self.rnd.random() < 0.5)

    def op_legend_options(self):
        # a legend's options changed (as in Properties): scope, columns, title, border, size
        from kanzonas import legend
        v = self.v
        found = [(i, x) for i in range(v.doc.page_count) for x in legend.legends_on(v.doc[i])]
        if not found:
            return "none"
        i, x = self.rnd.choice(found)
        v.select_xref(i, x)
        if v.selected_model is None:
            return "none"
        k = self.rnd.choice(["scope", "count", "totals", "border", "title", "fontsize"])
        old = v.selected_model["props"].get(k)
        value = {"scope": "document" if old == "page" else "page", "count": not old,
                 "totals": not old, "border": not old, "title": self.typed(),
                 "fontsize": self.rnd.choice([6, 9, 12, 16])}[k]
        v.update_selected_props(dict(v.selected_model["props"], **{k: value}))
        v.clear_selection()

    def op_text_markup(self):
        i = self.page()
        words = self.words(i)
        if not words:
            return "none"
        k = self.rnd.randrange(len(words))
        w0, w1 = words[k], words[min(len(words) - 1, k + self.rnd.randint(0, 6))]
        tool = self.rnd.choice(["highlight", "underline", "strikeout", "squiggly", "comment"])
        self.v.apply_text_tool(i, tool, pymupdf.Point(w0[0] + 0.5, (w0[1] + w0[3]) / 2),
                               pymupdf.Point(w1[2] - 0.5, (w1[1] + w1[3]) / 2))

    def op_attach(self):
        i = self.page()
        self.v.attach_file(i, self.point(i))

    def op_move(self):
        i = self.select_some()
        if i is None:
            return "none"
        v = self.v
        page = v.doc[i]
        d = pymupdf.Point(self.rnd.uniform(-60, 60), self.rnd.uniform(-60, 60))
        have = [(x, m) for x, m in v.selected_models()
                if m["kind"] != "field" and annotations.movable(m)]
        del page
        if not have:
            v.clear_selection()
            return "none"
        v.commit_models(i, [(x, annotations.moved(m, d)) for x, m in have], olds=dict(have))
        v.clear_selection()

    def op_nudge(self):
        if self.select_some() is None:
            return "none"
        v = self.v
        v._last_nudge = (None, 0.0, -1)  # (a burst of its own, not joined to an earlier one)
        moved = 0
        for _ in range(self.rnd.randint(1, 4)):        # (presses in a row: one undo step)
            moved += bool(v.nudge(self.rnd.choice([-1, 0, 1]), self.rnd.choice([-1, 0, 1]),
                                  self.rnd.choice([1.0, 10.0, 0.1])))
        v.clear_selection()
        return "edit" if moved else "none"

    def op_resize(self):
        i = self.select_some()
        if i is None:
            return "none"
        v = self.v
        x, m = v.selected_models()[0]
        if m["kind"] not in annotations.BOXED or m["kind"] in ("field", "redact"):
            v.clear_selection()
            return "none"
        r = annotations.bounds(m)
        k = self.rnd.uniform(0.5, 1.6)
        new = pymupdf.Rect(r.x0, r.y0, r.x0 + max(12, r.width * k), r.y0 + max(12, r.height * k))
        v.commit_model(i, x, annotations.resized(m, new))
        v.clear_selection()

    def op_props(self):
        if self.select_some() is None:
            return "none"
        v = self.v
        props = v.selected_model["props"]
        choices = [k for k in ("stroke", "fill", "width", "opacity", "fontsize", "text_color")
                   if k in props]
        if not choices:
            v.clear_selection()
            return "none"
        k = self.rnd.choice(choices)
        value = {"stroke": self.color(), "fill": self.color(),
                 "width": self.rnd.choice([0.5, 1.0, 2.0, 4.0]),
                 "opacity": self.rnd.choice([0.4, 0.7, 1.0]),
                 "fontsize": self.rnd.choice([8, 11, 14, 20]),
                 "text_color": self.color()}[k]
        v.update_selected_props({k: value})
        v.clear_selection()

    def op_retype(self):
        v = self.v
        pages = [i for i in range(v.doc.page_count) if self.markups(i)]
        if not pages:
            return "none"
        i = self.rnd.choice(pages)
        v.edit_annot_text(i, self.rnd.choice(self.markups(i)))

    def op_delete(self):
        if self.select_some() is None:
            return "none"
        self.v.delete_selected()

    def op_duplicate(self):
        if self.select_some() is None:
            return "none"
        self.v.duplicate_selected()
        self.v.clear_selection()

    def op_copy_paste(self):
        if self.select_some() is None:
            return "none"
        v = self.v
        if v.copy() != "markups":
            v.clear_selection()
            return "none"
        v.clear_selection()
        i = self.page()
        v.goto_page(i)
        with mock.patch.object(v, "paste_target", lambda: (i, self.point(i, 60))):
            v.paste()
        v.clear_selection()

    def op_restack(self):
        if self.select_some() is None:
            return "none"
        self.v.arrange(self.rnd.choice(["front", "back", "forward", "backward"]))
        self.v.clear_selection()

    def op_eraser(self):
        i = self.page()
        a, b = self.box(i, 40, 300)
        self.v.apply_drag_tool(i, "eraser", a, b, False)

    def op_add_text(self):
        v = self.v
        i = self.page()
        v.add_text_at(i, self.point(i, 60))
        ed = v._inline
        if ed is None:
            return "none"
        if self.rnd.random() < 0.4:
            # a box made narrower (the words wrap) and lines of their own (Shift+Enter)
            parts = [self.typed() + " " + self.typed() for _ in range(self.rnd.randint(1, 3))]
            ed.text.setPlainText("\n".join(parts))
            if self.rnd.random() < 0.7:
                ed.resized_by_user = True
                ed.resize(int(self.rnd.uniform(60, 160) * v.zoom), ed.height())
        else:
            ed.text.setPlainText(self.typed())
        ed.commit()

    def op_added_block(self):
        """Edit text on text Add text wrote (a marked block, added_text): all of it opens,
        its words are retyped, styled or broken onto lines of their own, its box sometimes
        made wider or narrower or moved; written back as one block."""
        from PySide6.QtGui import QTextCursor
        v = self.v
        pages = [i for i in range(v.doc.page_count) if v._added_blocks(i)]
        if not pages:
            return self.op_add_text()
        i = self.rnd.choice(pages)
        blk = self.rnd.choice(v._added_blocks(i))
        r, ln = self.rnd.choice(blk.lines)
        v.edit_text_at(i, pymupdf.Point(r.x0 + 1, (r.y0 + r.y1) / 2))
        ed = v._inline
        if ed is None:
            return "none"
        text = ed.text.toPlainText()
        what = self.rnd.choice(["retype", "style", "break", "width", "move", "same"])
        if what == "retype":
            parts = text.split(" ")
            k = self.rnd.randrange(len(parts))
            parts[k] = self.rnd.choice(["", "new", parts[k].upper(), parts[k] + " more"])
            ed.text.setPlainText(" ".join(p for p in parts if p) or "x")
        elif what == "style":
            spans = [mt.span() for mt in re.finditer(r"\S+", text)]
            if spans:
                a, b = self.rnd.choice(spans)
                cur = ed.text.textCursor()
                cur.setPosition(a)
                cur.setPosition(b, QTextCursor.KeepAnchor)
                ed.text.setTextCursor(cur)
                ed.toggle(self.rnd.choice(["bold", "italic", "underline", "strike"]))
        elif what == "break" and " " in text:
            k = self.rnd.choice([m.start() for m in re.finditer(" ", text)])
            ed.text.setPlainText(text[:k] + "\n" + text[k + 1:])
        elif what == "width":
            ed.resized_by_user = True
            ed.resize(max(60, int(ed.width() * self.rnd.uniform(0.6, 1.5))), ed.height())
        elif what == "move":
            ed.move(ed.pos() + QPoint(self.rnd.randint(-30, 30), self.rnd.randint(-30, 30)))
        ed.commit()

    def op_page_text_clip(self):
        """Edit objects: the page's own text (added blocks and the page's paragraphs) copied
        and pasted (here, on another page), cut (pasted by a later step), pasted again, or
        duplicated."""
        v = self.v
        i = self.page()
        texts = v.text_objects(i)
        if not texts:
            return "none"
        self.win.set_tool("editobjects")
        try:
            pick = self.rnd.sample(texts, self.rnd.randint(1, min(2, len(texts))))
            v.select_objects(i, pick)
            what = self.rnd.choice(["copy", "copy", "cut", "dup", "paste"])
            if what == "dup":
                v.duplicate_objects()
                return None
            if what == "cut":           # (pasted by a later step: each is one step)
                v.cut()
                return None
            if what == "copy" and v.copy() != "pagetext":
                return "none"
            from kanzonas import clip
            if clip.get()[0] != "pagetext":
                return "none"
            j = self.page()
            with mock.patch.object(v, "paste_target", lambda: (j, self.point(j, 60))):
                v.paste()
        finally:
            v.clear_object_selection()
            self.win.set_tool("hand")

    def _foreign_objects(self):
        """Pictures and shapes copied from another document (kept: pasted again and again,
        its pictures are copied in once, and again after an undo took them away)."""
        got = getattr(self, "_foreign", None)
        if got is not None:
            return got
        from kanzonas import object_clip, page_objects
        d = pymupdf.open()
        p = d.new_page()
        p.draw_rect((60, 60, 160, 120), color=(0, 0, 1), fill=(1, 1, 0), width=2,
                    fill_opacity=0.6, dashes="[4 2] 0")
        p.insert_image((60, 140, 140, 200), stream=png_bytes(30, 20, (200, 60, 60)))
        ocg = d.add_ocg("Foreign layer", on=True)
        p.draw_line((180, 60), (260, 120), color=(0, 0.5, 0), width=3, oc=ocg)
        objs = page_objects.Objects(p)
        clip = object_clip.take(d, p, [it["n"] for it in objs.items], objs, uid="foreign")
        box = None
        for it in objs.items:
            r = pymupdf.Rect(it["rect"])
            box = r if box is None else box | r
        clip["disp_box"] = box
        self._foreign = {"text": None, "objects": clip, "markups": None}
        return self._foreign

    def op_object_clip(self):
        """Edit objects: the page's own pictures and shapes (and text) copied and pasted onto
        this or another page, cut, or pasted from another document."""
        v = self.v
        i = self.page()
        self.win.set_tool("editobjects")
        try:
            what = self.rnd.choice(["copy", "copy", "cut", "foreign"])
            j = self.page()
            if what == "foreign":
                return None if v.paste_page_content(j, self.point(j, 60),
                                                    self._foreign_objects()) else None
            objs = v.content_objects(i)
            pool = list(objs.items if objs else []) + \
                (list(v.text_objects(i)) if self.rnd.random() < 0.3 else [])
            if not pool:
                return "none"
            pick = self.rnd.sample(pool, self.rnd.randint(1, min(4, len(pool))))
            v.select_objects(i, pick)
            if what == "cut":
                v.cut()
                return None
            if v.copy() not in ("pagecontent", "pagetext"):
                return "none"
            with mock.patch.object(v, "paste_target", lambda: (j, self.point(j, 60))):
                v.paste()
        finally:
            v.clear_object_selection()
            self.win.set_tool("hand")

    def op_across_pages(self):
        """CAD mode's Move or Copy (or a drag) of the page's own objects, and markups with
        them, onto another page, as one step for both pages."""
        v = self.v
        if v.doc.page_count < 2:
            return "none"
        i = self.page()
        j = self.rnd.choice([k for k in range(v.doc.page_count) if k != i])
        self.win.set_tool("editobjects")
        try:
            objs = v.content_objects(i)
            pool = list(objs.items if objs else []) + \
                (list(v.text_objects(i)) if self.rnd.random() < 0.3 else [])
            if not pool:
                return "none"
            v.select_objects(i, self.rnd.sample(pool, self.rnd.randint(1, min(4, len(pool)))))
            marks = self.markups(i)
            if marks and self.rnd.random() < 0.4:
                v.select_xref(i, self.rnd.choice(marks))
            d = pymupdf.Point(self.rnd.uniform(-60, 60), self.rnd.uniform(-60, 60))
            v.transfer_selection(j, d, copy=self.rnd.random() < 0.4)
        finally:
            v.clear_object_selection()
            v.clear_selection()
            self.win.set_tool("hand")

    def op_edit_text(self):
        v = self.v
        i = self.page()
        words = self.words(i)
        if not words:
            return "none"
        w = self.rnd.choice(words)
        v.edit_text_at(i, pymupdf.Point((w[0] + w[2]) / 2, (w[1] + w[3]) / 2),
                       one_line=self.rnd.random() < 0.3)
        ed = v._inline
        if ed is None:
            return "none"
        old = ed.text.toPlainText()
        parts = old.split(" ")
        k = self.rnd.randrange(len(parts))
        parts[k] = self.rnd.choice(["", "new", parts[k].upper(), parts[k] + " more"])
        ed.text.setPlainText(" ".join(p for p in parts if p) or "x")
        ed.commit()

    def op_styled_text(self):
        """Edit text or Add text with words styled in the editor (text_styles.py), as its
        buttons and keys do: bold, italic, underline, strikethrough, a color, a size up or
        down, on a run of words picked at random; then Done (the editor's own commit)."""
        from PySide6.QtGui import QColor, QTextCursor
        v = self.v
        i = self.page()
        if self.rnd.random() < 0.3:
            v.add_text_at(i, self.point(i, 60))
            ed = v._inline
            if ed is None:
                return "none"
            ed.text.setPlainText(self.typed() + " " + self.typed())
        else:
            words = self.words(i)
            if not words:
                return "none"
            w = self.rnd.choice(words)
            v.edit_text_at(i, pymupdf.Point((w[0] + w[2]) / 2, (w[1] + w[3]) / 2),
                           one_line=self.rnd.random() < 0.3)
            ed = v._inline
            if ed is None:
                return "none"
        text = ed.text.toPlainText()
        spans = [mt.span() for mt in re.finditer(r"\S+", text)]
        if not spans:
            ed.cancel()
            return "none"
        for _ in range(self.rnd.randint(1, 3)):
            k = self.rnd.randrange(len(spans))
            a, b = spans[k][0], spans[min(len(spans) - 1, k + self.rnd.randint(0, 3))][1]
            cur = ed.text.textCursor()
            cur.setPosition(a)
            cur.setPosition(b, QTextCursor.KeepAnchor)
            ed.text.setTextCursor(cur)
            what = self.rnd.choice(["bold", "italic", "underline", "strike", "color", "size"])
            if what == "color":
                ed.set_color(QColor(self.color()))
            elif what == "size":
                ed.grow_size(self.rnd.choice([-1, 1, 2]))
            else:
                ed.toggle(what)
        if self.rnd.random() < 0.3:             # and a word typed in its style
            cur = ed.text.textCursor()
            cur.setPosition(self.rnd.choice(spans)[1])
            ed.text.setTextCursor(cur)
            ed.text.insertPlainText(" " + self.typed())
        ed.commit()

    def op_scan(self):
        """File > Scan, Done into the current document: scanned pictures (made here, JPEG or
        PNG, with no scanner) put in after the current page, one undo step (scan_dialog's
        own finish)."""
        from kanzonas import scan_dialog, scan_net
        from PySide6.QtCore import QBuffer, QByteArray, QIODevice
        from PySide6.QtGui import QColor, QImage, QPainter
        v = self.v
        if v.doc.page_count >= 10:
            return self.op_delete_page()
        v.goto_page(self.page())
        dlg = scan_dialog.ScanDialog(self.win, discover=lambda cancel=None, log=None: ([], []),
                                     open_scanner=lambda d: None)
        try:
            end = time.time() + 15
            while "find" in dlg._busy and time.time() < end:
                APP.processEvents()
                time.sleep(0.005)
            dpi = self.rnd.choice([50, 75, 100])
            pages = []
            for _ in range(self.rnd.randint(1, 2)):
                w, h = int(8.5 * dpi), int(self.rnd.choice([11, 14]) * dpi)
                if self.rnd.random() < 0.3:
                    w, h = h, w
                img = QImage(w, h, QImage.Format_RGB32)
                img.fill(QColor(250, 250, 245))
                p = QPainter(img)
                for _ in range(12):
                    p.fillRect(self.rnd.randrange(w), self.rnd.randrange(h),
                               self.rnd.randint(5, w // 3), self.rnd.randint(2, 12),
                               QColor(self.color()))
                p.end()
                data = QByteArray()
                buf = QBuffer(data)
                buf.open(QIODevice.WriteOnly)
                img.save(buf, self.rnd.choice(["JPG", "PNG"]))
                pages.append(scan_net.check_image(bytes(data), dpi))
            dlg.pages = pages
            dlg.rb_current.setChecked(True)
            dlg.ocr.setChecked(False)
            dlg.finish()
        finally:
            dlg._stop()
            dlg.deleteLater()

    def op_replace_text(self):
        find, repl = self.rnd.choice([("text", "TEXT"), ("panel", "board"), ("TEXT", "text"),
                                      ("agrees", "agreed"), ("board", "panel")])
        self.v.replace_text(find, repl)

    def op_picture(self):
        i = self.page()
        a, b = self.box(i, 30, 150)
        self.v.apply_drag_tool(i, "image", a, b, self.rnd.random() < 0.3)

    def op_objects(self):
        """Edit objects: pictures, shapes and text of the page itself moved, turned or
        deleted."""
        v = self.v
        i = self.page()
        items = [it for it in v.content_objects(i).items]
        texts = [it for it in v.text_objects(i)] if self.rnd.random() < 0.3 else []
        pool = items + texts
        if not pool:
            return "none"
        pick = self.rnd.sample(pool, self.rnd.randint(1, min(3, len(pool))))
        v.select_objects(i, pick)
        what = self.rnd.choice(["move", "move", "rotate", "delete"])
        if what == "move":
            v.move_objects(v.selected_objects_rect() + (lambda d: (d, d * 0.5, d, d * 0.5))(
                self.rnd.uniform(-40, 40)))
        elif what == "rotate":
            v.rotate_objects(self.rnd.choice([90, -90, 180]))
        else:
            v.delete_objects()
        v.clear_object_selection()

    def op_erase_content(self):
        i = self.page()
        a, b = self.box(i, 20, 120)
        self.v.erase_content(i, pymupdf.Rect(a, b))

    def op_field(self):
        v = self.v
        found = [(i, w.xref) for i in range(v.doc.page_count) for w in v.doc[i].widgets()]
        if not found:
            return "none"
        i, x = self.rnd.choice(found)
        v._set_field(i, x, self.rnd.choice(["", "Jane Doe", self.typed()]))

    def op_layout(self):
        """View > Page layout (as its menu does) and a zoom, between edits: changes nothing
        in the document (and the edits after it, and the render check, work on pages shown
        side by side, or one page or spread at a time)."""
        from kanzonas import reading
        from kanzonas.document_view import PAGE_LAYOUTS
        win, v = self.win, self.v
        if self.rnd.random() < 0.3:
            win.a_cover.setChecked(not win.a_cover.isChecked())
            reading.set_layout(win, None)
        else:
            reading.set_layout(win, self.rnd.choice(PAGE_LAYOUTS))
        k = self.rnd.random()
        if k < 0.2:
            v.fit_width()
        elif k < 0.4:
            v.fit_page()
        else:
            v.set_zoom(self.rnd.choice([0.3, 0.5, 0.75, 1.0]))
        v.goto_page(self.page())
        return "none"

    def op_rotate_page(self):
        self.v.rotate_page(self.page(), self.rnd.choice([90, -90, 180]))

    def op_insert_blank(self):
        v = self.v
        if v.doc.page_count >= 10:
            return self.op_delete_page()
        v.insert_blank(self.rnd.randint(0, v.doc.page_count))

    def op_delete_page(self):
        v = self.v
        n = v.doc.page_count
        if n <= 2:
            return "none"
        if self.rnd.random() < 0.5:
            v.delete_page(self.page())
        else:
            v.delete_pages(self.rnd.sample(range(n), self.rnd.randint(1, min(3, n - 1))))

    def op_move_page(self):
        v = self.v
        i = self.page()
        delta = self.rnd.choice([-1, 1])
        if not 0 <= i + delta < v.doc.page_count:
            return "none"
        v.move_page(i, delta)

    def op_reorder(self):
        n = self.v.doc.page_count
        order = list(range(n))
        self.rnd.shuffle(order)
        if order == list(range(n)):
            return "none"
        self.v.reorder_pages(order)

    def op_duplicate_page(self):
        v = self.v
        if v.doc.page_count >= 10:
            return self.op_delete_page()
        v.duplicate_pages([self.page()])

    def op_crop(self):
        v = self.v
        i = self.page()
        if self.rnd.random() < 0.4 and v.doc[i].cropbox != v.doc[i].mediabox:
            v.remove_crop(i, all_pages=self.rnd.random() < 0.3)
            return
        cb = v.doc[i].cropbox
        m = self.rnd.uniform(5, 60)
        v.crop_pages(i, pymupdf.Rect(m, m, cb.width - m, cb.height - m),
                     all_pages=self.rnd.random() < 0.2)

    def op_replace_pages(self):
        """Pages > Replace pages, through the window's own step: one to three pages from
        the revision (revision()), picked by page numbers or in the sheet-number list (set
        by hand there: the battery's pages have no sheet numbers), markups scaled to a new
        size or kept in place. The revision file must stay as it was."""
        from kanzonas.replace_pages_ui import ReplacePagesDialog
        from PySide6.QtWidgets import QDialog
        rnd = self.rnd

        def answer(dlg):
            n, k = dlg.doc.page_count, dlg.src.page_count
            here = rnd.sample(range(n), rnd.randint(1, min(3, n)))
            if rnd.random() < 0.5:
                new = rnd.sample(range(k), len(here))
                dlg.here.setText(", ".join(str(i + 1) for i in here))
                dlg.new.setText(", ".join(str(j + 1) for j in new))
            else:
                dlg.by_sheets.setChecked(True)
                for row in range(dlg.table.rowCount()):
                    dlg.table.item(row, 2).setText("")
                for i in here:          # (one new sheet may replace several pages here)
                    dlg.table.item(i, 2).setText(str(rnd.randrange(k) + 1))
            (dlg.scale if rnd.random() < 0.5 else dlg.keep).setChecked(True)
            dlg._accept()
            return QDialog.Accepted if dlg.result_pairs else QDialog.Rejected
        with mock.patch.object(ReplacePagesDialog, "exec", answer):
            self.win.a_replace_pages.trigger()
        with open(self.revision, "rb") as f:
            if hashlib.sha256(f.read()).hexdigest() != self.revision_hash:
                raise Failed("Replace pages changed the file the pages came from")

    def op_bookmarks(self):
        v = self.v
        n = v.doc.page_count
        toc = [[1, "Start", 1]] + [[self.rnd.choice([1, 2]), self.typed(),
                                     self.rnd.randint(1, n)]
                                    for _ in range(self.rnd.randint(0, 4))]
        v.set_toc(toc)

    def op_watermark(self):
        v = self.v
        pages = sorted(self.rnd.sample(range(v.doc.page_count),
                                       self.rnd.randint(1, min(2, v.doc.page_count))))
        v.add_watermark({"text": self.rnd.choice(["DRAFT", "COPY"]), "pages": pages,
                         "behind": self.rnd.random() < 0.5, "size": 48})

    def op_flatten(self):
        v = self.v
        if self.rnd.random() < 0.7:
            return "none"              # (rare: it makes the markups part of the page)
        v.flatten([self.page()], widgets=False)

    def op_redact(self):
        v = self.v
        i = self.page()
        r = self.rnd.random()
        if r < 0.5:
            a, b = self.box(i, 20, 120)
            v.mark_redactions(i, [pymupdf.Rect(a, b)])
        elif r < 0.6:
            v.search_redact(self.rnd.choice(["line", "panel", "Page"]))
        elif v.pending_redactions():
            # (rarely with the clean-up, which replaces the document object: kept for undo)
            v.apply_redactions(scrub=self.rnd.random() < 0.3)
        else:
            return "none"

    def op_undo(self):
        for _ in range(self.rnd.randint(1, 5)):
            self.do_undo()
            APP.processEvents()
            self.after("undo")
        return "checked"

    def op_redo(self):
        for _ in range(self.rnd.randint(1, 5)):
            self.do_redo()
            APP.processEvents()
            self.after("redo")
        return "checked"

    def op_save(self):
        self.do_save()
        return "save"


def _after_checked(after):
    def wrapped(self, kind):
        if kind == "checked":           # (undo and redo runs check each step themselves)
            return
        return after(self, kind)
    return wrapped


Battery.after = _after_checked(Battery.after)


def run(out, ops, seed, undo_limit=0, journal=True, log=print, render_every=25):
    """One run; (failures, stats)."""
    b = Battery(out, ops, seed, undo_limit, journal, log, render_every)
    stats = b.run()
    return b.failures, stats


def main(argv):
    args = argv[1:]
    out = args[0] if args and not args[0].startswith("--") else \
        tempfile.mkdtemp(prefix="kanzonas-battery-")

    def opt(name, default):
        return int(args[args.index(name) + 1]) if name in args else default
    ops, seed, limit = opt("--ops", 2000), opt("--seed", 1), opt("--undo-limit", 0)
    every = opt("--render-every", 25)
    journal = "--copy" not in args
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "battery_random.log"), "w", encoding="utf-8") as f:
        def log(text):
            print(text)
            f.write(text + "\n")
            f.flush()
        import kanzonas
        log("KanzonasPDF %s random editing battery, PyMuPDF %s, Python %s, %s; seed %d, %d "
            "steps, undo limit %s, %s" % (
                kanzonas.__version__, pymupdf.VersionBind, sys.version.split()[0], sys.platform,
                seed, ops, limit or "none", "journal" if journal else "a copy per edit"))
        t = time.perf_counter()
        try:
            failures, stats = run(out, ops, seed, limit, journal, log, every)
        except Exception:
            failures, stats = ["the battery itself failed:\n" + traceback.format_exc()], ""
            log("FAIL " + failures[0])
        log(stats)
        log("%d failure(s) in %.0f s; output in %s" % (
            len([x for x in failures if x != "(stopped)"]), time.perf_counter() - t, out))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
