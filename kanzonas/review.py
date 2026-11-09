"""Review workflow: replies to markups, review status, comments exchanged as XFDF / FDF,
and the comment summary. Everything is stored the standard way, so Acrobat, PDF-XChange,
Bluebeam and others read it (ISO 32000-1, 12.5.6.2 "Markup annotations" and 12.5.6.10
"Text annotations"; Adobe's XFDF Specification 3.0 / ISO 19444-1):

- A reply is a Text annotation whose /IRT points to the markup it answers, with /RT /R and
  its own author (/T), dates (/CreationDate, /M) and text (/Contents). A reply to a reply
  points to that reply; together they make a thread. KanzonasPDF gives its replies an empty
  appearance (and /F 28: print, no zoom, no rotate, as Acrobat writes them), so they show in
  the thread and never as an icon on the page.
- A review status is the same kind of reply with /State and /StateModel: "Review" (Accepted,
  Rejected, Cancelled, Completed, None) or "Marked" (Marked, Unmarked). It is hidden (/F 30,
  as Acrobat writes it). Each change is a new one, so who set which status and when is kept;
  the markup's status is the latest one.
- An annotation with /RT /Group is grouped with the one it points to, not a reply: it stays a
  markup of its own.

Speed: a page's links (replies and statuses) are read in one walk of its markups through
MuPDF (links(): about 4 ms for 1,000 markups), never one lookup per markup.
"""

import re
import uuid

import pymupdf

from . import annotations as A
from .i18n import tr

REVIEW = ("Accepted", "Rejected", "Cancelled", "Completed", "None")
MARKED = ("Marked", "Unmarked")
STATE_LABELS = {"Accepted": tr("Accepted"), "Rejected": tr("Rejected"),
                "Cancelled": tr("Cancelled"), "Completed": tr("Completed"),
                "None": tr("None"), "Marked": tr("Marked"), "Unmarked": tr("Unmarked")}
REPLY_FLAGS = pymupdf.PDF_ANNOT_IS_PRINT | pymupdf.PDF_ANNOT_IS_NO_ZOOM | \
    pymupdf.PDF_ANNOT_IS_NO_ROTATE                                  # 28
STATE_FLAGS = REPLY_FLAGS | pymupdf.PDF_ANNOT_IS_HIDDEN            # 30
_SKIP = (pymupdf.PDF_ANNOT_POPUP, pymupdf.PDF_ANNOT_WIDGET, pymupdf.PDF_ANNOT_LINK)


# ---- reading: one walk of a page's markups ------------------------------------------------
class Link:
    """A reply or status on a page: parent (the xref it answers), role "reply" or "state",
    state and model (a status), author, created and modified (PDF dates), text."""
    __slots__ = ("xref", "parent", "role", "state", "model", "author", "created", "modified",
                 "text")

    def when(self):
        return norm_date(self.modified or self.created)


def norm_date(d):
    """A PDF date as digits only (YYYYMMDDHHmmSS...), for sorting."""
    return re.sub(r"\D", "", (d or "").replace("D:", ""))[:14]


def _text(m, obj, key):
    o = m.pdf_dict_gets(obj, key)
    return m.pdf_to_text_string(o) if o.m_internal else ""


def links(page):
    """({xref: Link} of the page's replies and statuses, [xref of every markup on the page in
    stacking order]), read in one walk of the page's markups. A reply whose markup isn't on the
    page (a broken file, a page copied without it) counts as a markup of its own."""
    m = pymupdf.mupdf
    out, present = {}, []
    try:
        pdfpage = page._pdf_page()
        a = m.pdf_first_annot(pdfpage)
    except Exception:                   # (not a PDF)
        return out, present
    while a.m_internal:
        obj = m.pdf_annot_obj(a)
        n = m.pdf_to_num(obj)
        present.append(n)
        irt = m.pdf_dict_gets(obj, "IRT")
        if irt.m_internal and m.pdf_is_indirect(irt):
            rt = m.pdf_dict_gets(obj, "RT")
            if not (rt.m_internal and m.pdf_to_name(rt) == "Group"):
                ln = Link()
                ln.xref, ln.parent = n, m.pdf_to_num(irt)
                ln.state = _text(m, obj, "State")
                ln.model = _text(m, obj, "StateModel")
                if ln.state and not ln.model:
                    ln.model = "Marked" if ln.state in MARKED else "Review"
                ln.role = "state" if ln.state else "reply"
                ln.author = _text(m, obj, "T")
                ln.created = _text(m, obj, "CreationDate")
                ln.modified = _text(m, obj, "M")
                ln.text = _text(m, obj, "Contents")
                out[n] = ln
        a = m.pdf_next_annot(a)
    on_page = set(present)
    return {x: ln for x, ln in out.items() if ln.parent in on_page and ln.parent != x}, present


class Threads:
    """A page's threads: which markups answer which (one walk: links())."""

    def __init__(self, page):
        self.links, self.order = links(page)
        self.children = {}
        for x in self.order:                    # (in stacking order: the order they were added)
            ln = self.links.get(x)
            if ln is not None:
                self.children.setdefault(ln.parent, []).append(x)

    def is_linked(self, x):
        """A reply or status (not a markup of its own)."""
        return x in self.links

    def root(self, x):
        """The markup a thread hangs from."""
        seen = set()
        while x in self.links and x not in seen:
            seen.add(x)
            x = self.links[x].parent
        return x

    def descendants(self, xrefs):
        """Every reply and status under these markups (replies to replies too)."""
        out, todo = [], list(xrefs)
        seen = set(xrefs)
        while todo:
            for c in self.children.get(todo.pop(), ()):
                if c not in seen:
                    seen.add(c)
                    out.append(c)
                    todo.append(c)
        return out

    def replies(self, root):
        """[(depth, Link)] of the replies in root's thread (no statuses), oldest first within
        each level, each followed by the replies to it."""
        out, seen = [], {root}

        def kids(x):
            got = [self.links[c] for c in self.children.get(x, ())
                   if self.links[c].role == "reply" and c not in seen]
            got.sort(key=lambda ln: norm_date(ln.created or ln.modified))
            return got
        # (depth first without recursion: a thread of thousands of replies, each answering
        # the one before, went past Python's limit on calls inside calls, and the Markups
        # list, Summarize comments and Reply stopped with an error on that document)
        todo = [(1, ln) for ln in reversed(kids(root))]
        while todo:
            depth, ln = todo.pop()
            if ln.xref in seen:
                continue
            seen.add(ln.xref)
            out.append((depth, ln))
            todo.extend((depth + 1, c) for c in reversed(kids(ln.xref)))
        return out

    def states(self, root):
        """The statuses set on root, oldest first."""
        kids = [self.links[c] for c in self.children.get(root, ())
                if self.links[c].role == "state"]
        pos = {x: k for k, x in enumerate(self.order)}
        return sorted(kids, key=lambda ln: (ln.when(), pos.get(ln.xref, 0)))

    def status(self, root):
        """(review state or "", the Link that set it or None, marked: bool)."""
        review = marked = None
        for ln in self.states(root):
            if ln.model == "Marked":
                marked = ln
            else:
                review = ln
        state = review.state if review is not None and review.state != "None" else ""
        return state, review, bool(marked is not None and marked.state == "Marked")

    def reply_count(self, root):
        return len(self.replies(root))


def status_label(state, marked):
    """What the Markups list's Status column shows."""
    words = STATE_LABELS.get(state, state) if state else ""
    if marked:
        words = ("✓ " + words).strip()
    return words


# ---- writing: replies and statuses ------------------------------------------------------------
def _rect_of(doc, xref):
    kind, val = doc.xref_get_key(xref, "Rect")
    try:
        nums = [float(v) for v in val.strip("[]").split()]
        return pymupdf.Rect(nums[:4]).normalize()
    except (ValueError, TypeError):
        return pymupdf.Rect(0, 0, 18, 18)


def _empty_appearance(doc, w=18, h=18):
    """A Form XObject that draws nothing, the size of the annotation's box: a reply shows in
    its thread, never on the page. (With no appearance at all, MuPDF draws a note icon of
    its own the next time it updates the page, and makes the box the icon's size; a status
    has one too, so its box never changes either.)"""
    ap = doc.get_new_xref()
    doc.update_object(ap, "<</Type/XObject/Subtype/Form/BBox[0 0 %s %s]/Resources<<>>>>" % (
        _n(w), _n(h)))
    doc.update_stream(ap, b"")
    return ap


def _n(v):
    return ("%.4f" % v).rstrip("0").rstrip(".") or "0"


def _append_annots(page, xrefs):
    """Put new annotation objects on the page (on top), MuPDF's list of them read again."""
    A.set_annot_order(page, A.annot_order(page) + list(xrefs))


def _linked(page, parent, text, author, state=None, model=None):
    doc = page.parent
    r = _rect_of(doc, parent)
    x0, y1 = round(r.x0, 4), round(r.y1, 4)
    box = f"[{_n(x0)} {_n(y1 - 18)} {_n(x0 + 18)} {_n(y1)}]"     # (its parent's top left)
    now = pymupdf.get_pdf_now()
    body = (f"/Type/Annot/Subtype/Text/Rect{box}/P {page.xref} 0 R/IRT {parent} 0 R/RT/R"
            f"/T{pymupdf.get_pdf_str(author or '')}/Contents{pymupdf.get_pdf_str(text or '')}"
            f"/CreationDate{pymupdf.get_pdf_str(now)}/M{pymupdf.get_pdf_str(now)}"
            f"/NM{pymupdf.get_pdf_str(str(uuid.uuid4()))}/Name/Comment/Open false"
            f"/C[1 0.82 0]")
    if state:
        body += (f"/F {STATE_FLAGS}/State{pymupdf.get_pdf_str(state)}"
                 f"/StateModel{pymupdf.get_pdf_str(model or 'Review')}")
    else:
        body += f"/F {REPLY_FLAGS}"
    body += f"/AP<</N {_empty_appearance(doc)} 0 R>>"
    x = doc.get_new_xref()
    doc.update_object(x, "<<" + body + ">>")
    return x


def add_reply(page, parent, text, author=None):
    """A reply to markup parent (or to a reply) on page. Returns its xref."""
    x = _linked(page, parent, text, A.author() if author is None else author)
    _append_annots(page, [x])
    return x


def thread_of(doc, threads, x):
    """The replies and statuses under markup x (threads: its page's Threads) as plain values,
    each after the one it answers: [{"parent": index in the list (-1: x), "text", "author",
    "created", "modified", "state", "model"}], for put_thread."""
    kids = threads.descendants([x])
    at = {c: k for k, c in enumerate(kids)}
    out = []
    for c in kids:
        ln = threads.links[c]
        out.append({"parent": at.get(ln.parent, -1), "text": ln.text or "",
                    "author": ln.author or "", "created": ln.created or "",
                    "modified": ln.modified or "", "state": ln.state or "",
                    "model": ln.model or ""})
    return out


def put_thread(page, x, thread):
    """Put replies and statuses (thread_of) under markup x of page, their authors and dates
    as they were. Returns their xrefs."""
    doc = page.parent
    new = []
    for e in thread:
        parent = x if e["parent"] < 0 or e["parent"] >= len(new) else new[e["parent"]]
        y = _linked(page, parent, e["text"], e["author"], e["state"] or None,
                    e["model"] or None)
        for key, val in (("CreationDate", e["created"]), ("M", e["modified"])):
            if val:
                doc.xref_set_key(y, key, pymupdf.get_pdf_str(val))
        new.append(y)
    if new:
        _append_annots(page, new)
    return new


def set_status(page, parents, state, author=None):
    """Set a review status (REVIEW) or mark (MARKED) on these markups: a status reply on
    each, the earlier ones kept as history. Returns the new xrefs."""
    model = "Marked" if state in MARKED else "Review"
    who = A.author() if author is None else author
    words = tr("{state} set by {name}").format(state=STATE_LABELS.get(state, state), name=who)
    new = [_linked(page, p, words, who, state, model) for p in parents]
    _append_annots(page, new)
    return new


def edit_reply(doc, xref, text):
    """Change a reply's text (its rich text, if another program wrote one, goes: it would be
    shown instead)."""
    doc.xref_set_key(xref, "Contents", pymupdf.get_pdf_str(text))
    doc.xref_set_key(xref, "RC", "null")
    doc.xref_set_key(xref, "M", pymupdf.get_pdf_str(pymupdf.get_pdf_now()))


def shift_replies(page, moved, threads=None):
    """The replies and statuses of markups moved in place go along: moved {xref: (dx, dy) in
    PDF units}. Replies already in moved are left as they are."""
    if not moved:
        return
    doc = page.parent
    threads = threads or Threads(page)
    if not threads.links:
        return
    for x, (dx, dy) in moved.items():
        for c in threads.descendants([x]):
            if c in moved:
                continue
            targets = [c]
            kind, val = doc.xref_get_key(c, "Popup")
            if kind == "xref":
                targets.append(int(val.split()[0]))
            for t in targets:
                kind, val = doc.xref_get_key(t, "Rect")
                if kind == "array" and "R" not in val:
                    doc.xref_set_key(t, "Rect", A._shift_pairs(val, dx, dy))


def move_threads(src, dest, moved):
    """The replies and statuses of markups moved to another page go with them: moved {old
    xref on page src: its new xref on page dest}. The same objects (and their pop-ups) leave
    src's /Annots for dest's, answer the new markup and keep their place beside it. Returns
    the old xrefs whose threads went (call pdf_speed.delete_many(src, those,
    keep_replies=True) for the markups themselves afterwards)."""
    if not moved:
        return set()
    doc = src.parent
    threads = Threads(src)
    carried, done = [], set()
    for old, new in moved.items():
        kids = [c for c in threads.descendants([old]) if c not in moved]
        if not kids:
            continue
        done.add(old)
        o, n = _rect_of(doc, old), _rect_of(doc, new)
        dx, dy = n.x0 - o.x0, n.y1 - o.y1
        for c in kids:
            if c in carried:
                continue
            carried.append(c)
            parent = threads.links[c].parent
            if parent in moved:             # (it answers one written anew there)
                doc.xref_set_key(c, "IRT", f"{moved[parent]} 0 R")
            targets = [c]
            kind, val = doc.xref_get_key(c, "Popup")
            if kind == "xref":
                pop = int(val.split()[0])
                targets.append(pop)
                carried.append(pop)
            for t in targets:
                doc.xref_set_key(t, "P", f"{dest.xref} 0 R")
                kind, val = doc.xref_get_key(t, "Rect")
                if kind == "array" and "R" not in val:
                    doc.xref_set_key(t, "Rect", A._shift_pairs(val, dx, dy))
    if carried:
        gone = set(carried)
        A.set_annot_order(src, [x for x in A.annot_order(src) if x not in gone])
        there = A.annot_order(dest)
        have = set(there)
        A.set_annot_order(dest, there + [x for x in carried if x not in have])
    return done


# ---- the comment summary ----------------------------------------------------------------------
SORTS = ("page", "author", "date", "type")


def entries(doc):
    """Every markup (not the replies and statuses: they go with it) as a dict: page, xref,
    type, text, author, date (shown), when (for sorting), status, color, replies
    [(depth, author, date, text)]. One walk of each page's markups."""
    from .markups_panel import _date, _row
    out = []
    for i in range(doc.page_count):
        page = doc[i]
        threads = Threads(page)
        roots = [x for x, typ, _nm in page.annot_xrefs()
                 if typ not in _SKIP and not threads.is_linked(x)]
        loaded = A.load_annots(page, roots)
        for x in roots:
            a = loaded.get(x)
            if a is None:
                continue
            label, _text, author, date, color = _row(a)
            info = a.info
            state, _ln, marked = threads.status(x)
            out.append({
                "page": i, "xref": x, "type": label, "text": info.get("content", "") or "",
                "author": author, "date": date,
                "when": norm_date(info.get("modDate") or info.get("creationDate")),
                "status": status_label(state, marked), "color": color,
                "y": (a.rect * page.rotation_matrix).y0,
                "replies": [(d, ln.author, _date(ln.modified or ln.created), ln.text)
                            for d, ln in threads.replies(x)]})
        loaded.clear()
    return out


def sorted_entries(items, sort="page"):
    if sort == "author":
        key = (lambda e: (e["author"].lower(), e["page"], e["y"]))
    elif sort == "date":
        key = (lambda e: (e["when"], e["page"], e["y"]))
    elif sort == "type":
        key = (lambda e: (e["type"].lower(), e["page"], e["y"]))
    else:
        key = (lambda e: (e["page"], e["y"]))
    return sorted(items, key=key)


class _Layout:
    """Lines of text laid out down pages of a new PDF (Letter, portrait)."""
    W, H, M = 612, 792, 40

    def __init__(self, out):
        self.out = out
        self.fonts = {"": pymupdf.Font("helv"), "b": pymupdf.Font("hebo")}
        self.uni = None
        self.page = None
        self.y = self.H

    def _font(self, text, bold=False):
        try:
            text.encode("cp1252")
            return self.fonts["b" if bold else ""]
        except UnicodeEncodeError:
            if self.uni is None:
                self.uni = pymupdf.Font("cjk")      # (any language: MuPDF's own Unicode font)
            return self.uni

    def new_page(self):
        self.flush()
        self.page = self.out.new_page(width=self.W, height=self.H)
        self.writers = {}
        self.shape = self.page.new_shape()
        self.y = self.M

    def flush(self):
        if self.page is not None:
            for color, tw in self.writers.items():
                tw.write_text(self.page, color=color)
            self.shape.commit()
            self.page = None

    def room(self, h):
        if self.page is None or self.y + h > self.H - self.M:
            self.new_page()
            return False
        return True

    def wrap(self, text, width, size, bold=False):
        lines = []
        for para in (text or "").replace("\r", "\n").split("\n"):
            words, cur = para.split(" "), ""
            for w in words:
                trial = (cur + " " + w) if cur else w
                if self._font(trial, bold).text_length(trial, size) <= width or not cur:
                    cur = trial
                else:
                    lines.append(cur)
                    cur = w
            lines.append(cur)
        return lines

    def text(self, x, text, size, color=(0, 0, 0), bold=False, width=None):
        """Write text from x to the right margin (wrapped), moving down."""
        width = width or (self.W - self.M - x)
        for line in self.wrap(text, width, size, bold):
            self.room(size * 1.3)
            tw = self.writers.get(color)
            if tw is None:
                tw = self.writers[color] = pymupdf.TextWriter(self.page.rect)
            if line:
                tw.append((x, self.y + size), line, font=self._font(line, bold), fontsize=size)
            self.y += size * 1.3


def summarize(doc, sort="page", thumbnails=True, title=""):
    """A new PDF listing every comment: for each its page, type, author, date, status, text
    and replies, sorted by page (with each page's thumbnail beside its comments when
    thumbnails), author, date or type, as Acrobat's Summarize Comments does."""
    items = sorted_entries(entries(doc), sort)
    out = pymupdf.open()
    L = _Layout(out)
    L.new_page()
    L.text(L.M, tr("Comment summary"), 18, bold=True)
    if title:
        L.text(L.M, title, 11, (0.3, 0.3, 0.3))
    L.text(L.M, tr("{n} comments, sorted by {how}").format(
        n=len(items), how={"page": tr("page"), "author": tr("author"), "date": tr("date"),
                           "type": tr("type")}.get(sort, sort)), 10, (0.3, 0.3, 0.3))
    L.y += 8
    if not items:
        L.text(L.M, tr("This document has no comments."), 11)
    group = object()
    thumb_bottom, thumb_page = 0, None
    tw = 140                                # thumbnail width
    gray = (0.35, 0.35, 0.35)
    for n, e in enumerate(items, 1):
        if sort == "page":
            g = e["page"]
            heading = tr("Page {n}").format(n=g + 1)
        elif sort == "author":
            g = e["author"]
            heading = tr("Author: {name}").format(name=g or tr("(no name)"))
        elif sort == "type":
            g = e["type"]
            heading = g
        else:
            g, heading = None, None
        left = L.M
        if g != group:
            group = g
            L.y = max(L.y, thumb_bottom) + 6
            thumb_bottom = 0
            src = doc[e["page"]] if sort == "page" and thumbnails else None
            h = tw * src.rect.height / max(src.rect.width, 1) if src is not None else 0
            if heading is not None:
                L.room(50 + h)                  # (a heading never ends a page)
                L.shape.draw_line((L.M, L.y), (L.W - L.M, L.y))
                L.shape.finish(color=(0.6, 0.6, 0.6), width=0.5)
                L.y += 4
                L.text(L.M, heading, 13, bold=True)
            if src is not None:
                w = tw if h <= 300 else tw * 300 / h       # (a very tall page: narrower)
                h = min(h, 300)
                box = pymupdf.Rect(L.M, L.y + 2, L.M + w, L.y + 2 + h)
                z = w * 2 / max(src.rect.width, 1)
                L.page.insert_image(box, pixmap=src.get_pixmap(matrix=pymupdf.Matrix(z, z)))
                L.shape.draw_rect(box)
                L.shape.finish(color=(0.7, 0.7, 0.7), width=0.5)
                thumb_bottom = box.y1 + 6
                thumb_page = L.page
        if sort == "page" and thumbnails and thumb_bottom and L.page is thumb_page:
            left = L.M + tw + 14
        L.room(30)
        meta = [e["type"], e["author"] or tr("(no name)"), e["date"]]
        if sort != "page":
            meta.insert(0, tr("Page {n}").format(n=e["page"] + 1))
        if e["status"]:
            meta.append(tr("Status: {status}").format(status=e["status"]))
        y0 = L.y
        if e["color"]:
            rgb = A.to_rgb(e["color"])
            if rgb:
                L.shape.draw_rect(pymupdf.Rect(left, y0 + 2, left + 8, y0 + 10))
                L.shape.finish(color=(0.3, 0.3, 0.3), fill=rgb, width=0.3)
        L.text(left + 12, "%d. %s" % (n, "  •  ".join(m for m in meta if m)), 9, gray,
               bold=True)
        if e["text"].strip():
            L.text(left + 12, e["text"], 10)
        for depth, who, when, text in e["replies"]:
            indent = left + 12 + 16 * min(depth, 4)
            L.text(indent, "↳ " + tr("{name}, {date}:").format(
                name=who or tr("(no name)"), date=when), 9, gray)
            L.text(indent + 10, text, 10)
        L.y += 6
        if L.page is not thumb_page:
            thumb_bottom = 0
    L.flush()
    try:
        out.subset_fonts()
    except Exception:
        pass
    out.set_metadata({"title": tr("Comment summary") + (" - " + title if title else ""),
                      "creator": "KanzonasPDF"})
    return out
