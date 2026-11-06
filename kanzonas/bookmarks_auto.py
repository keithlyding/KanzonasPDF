"""Bookmarks made from the document itself, and a table of contents page made from them.

Three ways to find what the bookmarks should be:

- Headings, from the look of the text (HeadingScan): the body text is the size most of the
  letters have; a line is a heading when it is clearly bigger, or bold and alone on its row,
  or numbered the way headings are ("1.2 Scope", "SECTION 08 71 00", "PART 2 - PRODUCTS").
  Headers and footers (the same words at the same place on page after page, or with only a
  page number changing) never count. Levels come from the look, the same for the whole
  document: bigger text is a higher level, then bold, then the numbering's depth (SECTION
  over PART over 1.1 over 1.1.1).
- The tagged structure (TaggedScan): in a tagged PDF the headings are marked H1-H6 (H), so
  the levels and words are exact.
- Sheet numbers (SheetScan): a drawing set's sheet number and title from each title block
  (sheets.sheet_info), "A-101  FIRST FLOOR PLAN", optionally under its discipline.

Each scan reads the pages one at a time in run(), a generator that yields after every page,
so the window drives it in short slices with a progress bar and Cancel (no thread touches
the document). propose() then gives the bookmarks as items:
{"level", "title", "page" (index), "to" (point on the page, unrotated), "on"}.

insert_toc() makes the table of contents pages: the bookmarks with dotted leaders and page
numbers, each line a link to its page. The pages carry /KZTOC in their page dictionary, so
running it again replaces them instead of adding another one.
"""

import html
import re
from collections import Counter, defaultdict

import pymupdf

from .i18n import tr

MAX_LEVELS = 3
TOC_KEY = "KZTOC"           # in the page dictionary of a table of contents made here

_FLAGS = pymupdf.TEXT_PRESERVE_WHITESPACE | pymupdf.TEXT_MEDIABOX_CLIP
_BOLD_NAME = re.compile(r"bold|black|heavy|semibold|demi|extrabold|ultrabold|-bd\b|,bd\b", re.I)


# ---- reading the lines of a page -------------------------------------------------------------
class Row:
    """One line of text as shown (pieces on the same baseline close together joined)."""
    __slots__ = ("page", "text", "size", "bold", "chars", "rect", "yf0", "yf1", "alone")

    def __init__(self, page, text, size, bold, chars, rect, yf0, yf1, alone):
        self.page, self.text, self.size, self.bold, self.chars = page, text, size, bold, chars
        self.rect, self.yf0, self.yf1, self.alone = rect, yf0, yf1, alone


def _line_pieces(page):
    """[(order, text, size, bold chars, chars, rect (unrotated), shown rect)] of the page's
    upright lines."""
    try:
        d = page.get_text("dict", flags=_FLAGS)
    except Exception:
        return []
    rot = page.rotation_matrix
    turn = pymupdf.Matrix(rot.a, rot.b, rot.c, rot.d, 0, 0)
    out = []
    for b in d.get("blocks", ()):
        if b.get("type") != 0:
            continue
        for ln in b.get("lines", ()):
            v = pymupdf.Point(ln["dir"]) * turn
            if v.x < 0.9:               # sideways text (labels on drawings): never a heading
                continue
            sizes = Counter()
            bold = chars = 0
            for s in ln["spans"]:
                n = len(s["text"].strip())
                if not n:
                    continue
                sizes[round(s["size"] * 2) / 2] += n
                if s["flags"] & 16 or _BOLD_NAME.search(s["font"] or ""):
                    bold += n
                chars += n
            if not chars:
                continue
            text = " ".join("".join(s["text"] for s in ln["spans"]).split())
            r = pymupdf.Rect(ln["bbox"])
            out.append((len(out), text, sizes.most_common(1)[0][0], bold, chars, r, r * rot))
    return out


def page_rows(page, index):
    """The page's rows in reading order: [Row]."""
    pieces = _line_pieces(page)
    if not pieces:
        return []
    height = max(1.0, page.rect.height)
    pieces.sort(key=lambda p: (p[6].y0 + p[6].y1) / 2)
    rows, cur, centre, tall = [], [], 0.0, 0.0
    for p in pieces:                    # pieces whose middles line up make one row
        c, h = (p[6].y0 + p[6].y1) / 2, p[6].height
        if cur and abs(c - centre) <= 0.35 * max(h, tall):
            cur.append(p)
        else:
            if cur:
                rows.append(cur)
            cur, centre, tall = [p], c, h
    rows.append(cur)
    out = []
    for row in rows:
        row.sort(key=lambda p: p[6].x0)
        items = [list(row[0])]
        for p in row[1:]:
            last = items[-1]
            size = max(last[2], p[2])
            if p[6].x0 - last[6].x1 < 2.5 * size and 0.8 <= p[2] / max(0.1, last[2]) <= 1.25:
                # "1.2" and "Scope" set apart by a tab: one line
                big = p[4] > last[4]
                last[0] = min(last[0], p[0])
                last[1] = last[1] + " " + p[1]
                last[2] = p[2] if big else last[2]
                last[3] += p[3]
                last[4] += p[4]
                last[5] = last[5] | p[5]
                last[6] = last[6] | p[6]
            else:
                items.append(list(p))
        alone = len(items) == 1
        for it in items:
            out.append((it[0], Row(index, it[1], it[2], it[3] >= 0.6 * it[4], it[4], it[5],
                                   it[6].y0 / height, it[6].y1 / height, alone)))
    out.sort(key=lambda x: x[0])
    return [r for _o, r in out]


# ---- what makes a heading ------------------------------------------------------------------
_LEADER = re.compile(r"(\.\s?){4,}|…{2,}|_{4,}|(·\s?){4,}")
_PAGE_NO = re.compile(r"^(page|p\.|pg\.?|página|pág\.)?\s*([0-9]+|[ivxlc]+)"
                      r"(\s*(of|/|de)\s*[0-9]+)?$", re.I)
_LETTER = re.compile(r"[^\W\d_]")
_DIGITS = re.compile(r"\d+")
_RANKS = [
    (re.compile(r"^division\s+\d{1,2}\b", re.I), 0),
    (re.compile(r"^section\s+\d", re.I), 1),
    (re.compile(r"^(chapter|appendix|annex|capítulo|capitulo|anexo|apéndice)\s+"
                r"([0-9]{1,3}|[ivxlc]{1,6}|[a-z])\b", re.I), 1),
    (re.compile(r"^part\s+([0-9]{1,2}|[ivx]{1,4}|[a-z]|one|two|three|four|five|six)\b", re.I), 2),
    (re.compile(r"^(article|artículo)\s+([0-9]{1,3}|[ivxlc]{1,6})\b", re.I), 3),
    (re.compile(r"^[IVX]{1,5}\.\s+\S"), 3),
]
_NUMBERED = re.compile(r"^(\d{1,3}(?:\.\d{1,3}){0,4})\.?\)?\s+(\S)")


def numbering(text):
    """The rank of a heading's numbering, lower for bigger divisions: DIVISION 0, SECTION
    and CHAPTER 1, PART 2, ARTICLE 3, then 1 -> 4, 1.1 -> 5, 1.1.1 -> 6; None when
    unnumbered."""
    for rx, rank in _RANKS:
        if rx.match(text):
            return rank
    m = _NUMBERED.match(text)
    if m and (m.group(2).isupper() or m.group(2) in "(\"'“"):
        return 3 + m.group(1).count(".") + 1
    return None


def _caps(text):
    letters = _LETTER.findall(text)
    return len(letters) >= 3 and sum(1 for c in letters if c.isupper()) >= 0.85 * len(letters)


def _candidate(r, body, bold_body):
    """(True, numbering rank) when row r looks like a heading."""
    t = r.text
    if len(t) < 2 or len(t) > 160 or _LEADER.search(t) or _PAGE_NO.match(t.strip(" -–—")):
        return False, None
    if len(_LETTER.findall(t)) < 2:
        return False, None
    words = len(t.split())
    if words > 18:
        return False, None
    rank = numbering(t)
    sentence = t.endswith((".", ";", ",")) and words > 5 and rank is None
    if r.size >= body * 1.12 and r.size - body >= 1.0:
        return not (sentence and words > 10), rank
    if r.size < body * 0.92:
        return False, None
    if r.bold and not bold_body and r.alone and words <= 12 and not sentence:
        return True, rank
    if rank is not None and r.alone and words <= 12:
        if rank <= 3 or _caps(t):
            return True, rank
    return False, None


def _style_name(size, bold):
    return ("%g pt" % size) + (" " + tr("bold") if bold else "")


class HeadingScan:
    """Headings found by their look. run() reads the pages (yields after each one);
    propose() gives the bookmarks."""

    def __init__(self, doc, pages=None):
        self.doc = doc
        self.pages = list(range(doc.page_count)) if pages is None else list(pages)
        self.rows = []
        self.styles = []                # (description, level) for the preview

    def run(self):
        skip = set(toc_pages(self.doc))
        for n, i in enumerate(self.pages):
            if i not in skip:
                self.rows.extend(page_rows(self.doc[i], i))
            yield n + 1

    # -- headers and footers
    def _furniture(self):
        """Indexes of the rows that repeat at the same place on nearby pages (the same words,
        or with only the page number changing): running headers, footers, page numbers."""
        rows = self.rows
        pages = {r.page for r in rows}
        if len(pages) < 2:
            return set()
        need = 3 if len(pages) >= 3 else 2
        occ = defaultdict(list)
        for idx, r in enumerate(rows):
            if len(r.text) > 160:
                continue
            t = r.text.lower()
            occ[_DIGITS.sub("#", t)].append((int(r.yf0 * 50), r.page, idx, t))
        out = set()
        for lst in occ.values():
            if len(lst) < need:
                continue
            lst.sort()
            cluster = [lst[0]]
            for o in lst[1:]:
                if o[0] - cluster[-1][0] <= 1:
                    cluster.append(o)
                else:
                    out |= self._repeats(cluster, need)
                    cluster = [o]
            out |= self._repeats(cluster, need)
        return out

    @staticmethod
    def _repeats(cluster, need):
        if len({o[1] for o in cluster}) < need:
            return set()
        by_page = sorted(cluster, key=lambda o: o[1])
        linked = set()
        for k, a in enumerate(by_page):
            for b in by_page[k + 1:k + 6]:
                gap = b[1] - a[1]
                if gap > 2:
                    break
                if gap < 1:
                    continue
                if a[3] == b[3]:
                    same = True
                else:                   # only a page number differs, by the pages between
                    na = [int(x) for x in _DIGITS.findall(a[3])]
                    nb = [int(x) for x in _DIGITS.findall(b[3])]
                    diff = [(x, y) for x, y in zip(na, nb) if x != y]
                    same = len(na) == len(nb) and len(diff) == 1 and diff[0][1] - diff[0][0] == gap
                if same:
                    linked.add(a[2])
                    linked.add(b[2])
        linked_pages = len({o[1] for o in cluster if o[2] in linked})
        margin = not 0.12 <= sum(o[0] for o in cluster) / (50.0 * len(cluster)) <= 0.88
        if linked_pages < (need if margin else max(4, need)) or len(linked) < 0.5 * len(cluster):
            return set()        # (away from the margins: only on four pages or more)
        return {o[2] for o in cluster}

    def propose(self):
        rows = self.rows
        self.styles = []
        if not rows:
            return []
        weights = Counter()
        for r in rows:
            weights[r.size] += r.chars
        body = weights.most_common(1)[0][0]
        bold_body = sum(r.chars for r in rows if r.size == body and r.bold) > 0.5 * weights[body]
        furniture = self._furniture()
        heads = []                      # [page, first, last, size, bold, rank, text, rect, n]
        for idx, r in enumerate(rows):
            if idx in furniture:
                continue
            ok, rank = _candidate(r, body, bold_body)
            if not ok:
                continue
            h = heads[-1] if heads else None
            if h is not None and h[0] == r.page and h[2] == idx - 1 and h[3] == r.size and \
                    h[4] == r.bold and -0.2 * r.size <= r.rect.y0 - h[7].y1 < 0.9 * r.size:
                h[2] = idx              # (the next line of the same heading, or a paragraph)
                h[8] += 1
                if rank is None or h[8] > 3:
                    h[6] = h[6] + " " + r.text
                    h[7] = h[7] | r.rect
                    continue
                h[8] -= 1
                h[2] = idx - 1
            heads.append([r.page, idx, idx, r.size, r.bold, rank, r.text, pymupdf.Rect(r.rect), 1])
        heads = [h for h in heads if h[8] <= 3]         # four lines or more: a paragraph
        if not heads:
            return []
        text_pages = max(1, len({r.page for r in rows}))
        # the look of each heading; too many of one look on a page: labels, not headings
        groups = defaultdict(list)
        for h in heads:
            groups[(h[3], h[4])].append(h)
        for key in list(groups):
            if len(groups[key]) > 6 * text_pages:
                del groups[key]
        slots = []                       # ((size, bold), sub-rank) from the top level down
        for key in sorted(groups, key=lambda k: (-k[0], not k[1])):
            ranks = sorted({h[5] for h in groups[key] if h[5] is not None})
            for k, rank in enumerate(ranks or [None]):
                slots.append((key, rank))
        if not slots:
            return []

        def slot_of(h):
            key = (h[3], h[4])
            ranks = [s[1] for s in slots if s[0] == key]
            rank = h[5] if h[5] in ranks else ranks[0]
            return slots.index((key, rank))
        used = defaultdict(list)
        for key, g in groups.items():
            for h in g:
                used[slot_of(h)].append(h)
        order = sorted(used)
        title = None
        first_page = min(r.page for r in rows)
        top = used[order[0]]
        if len(order) > 1 and len(top) == 1 and top[0][0] <= first_page + 1:
            title = top[0]              # one line bigger than all the rest: the title
            order = order[1:]
        level_of = {s: k + 1 for k, s in enumerate(order)}
        for s in order[:MAX_LEVELS]:
            (size, bold), rank = slots[s]
            self.styles.append((_style_name(size, bold), level_of[s], len(used[s])))
        items = []
        for h in sorted((h for g in groups.values() for h in g), key=lambda h: (h[0], h[1])):
            if h is title:
                level, on = 1, False
            else:
                level, on = level_of[slot_of(h)], True
            if level > MAX_LEVELS:
                continue
            items.append(_item(level, h[6], h[0], h[7], on))
        return items


def _item(level, title, page, rect, on=True):
    text = " ".join(str(title).split())
    title = (text.rstrip(" .:–—-").lstrip(" –—-") or text)[:200]
    return {"level": level, "title": title, "page": page,
            "to": pymupdf.Point(0, max(0.0, rect.y0 - 2)), "on": on}


# ---- tagged PDFs ---------------------------------------------------------------------------
_REF = re.compile(r"(\d+)\s+0\s+R")
_INLINE = re.compile(r"<<.*?>>", re.S)
_PG = re.compile(r"/Pg\s+(\d+)\s+0\s+R")
_NAME_PAIR = re.compile(r"/([^\s/<>\[\]()]+)\s*/([^\s/<>\[\]()]+)")
_HEADING = re.compile(r"^H([1-9]?)$")
# structure elements that never hold a heading (no need to look inside them)
_LEAVES = frozenset((
    "P", "Span", "Link", "Figure", "Formula", "Table", "TR", "TD", "TH", "THead", "TBody",
    "TFoot", "L", "LI", "Lbl", "LBody", "Note", "Reference", "BibEntry", "Code", "Quote",
    "Annot", "Form", "Caption", "Ruby", "Warichu", "RB", "RT", "RP", "WT", "WP", "TOC", "TOCI",
    "Index", "Artifact", "Em", "Strong", "Sub", "FENote", "Title"))


def _xref_of(value):
    m = _REF.match(value or "")
    return int(m.group(1)) if m else 0


def struct_root(doc):
    """The xref of the document's structure tree root (0 when it isn't tagged)."""
    try:
        kind, value = doc.xref_get_key(doc.pdf_catalog(), "StructTreeRoot")
    except Exception:
        return 0
    return _xref_of(value) if kind == "xref" else 0


class TaggedScan:
    """Headings from a tagged PDF's structure (H1-H6, H). run() walks the structure tree
    for the pages that hold headings, then reads those pages' marked text."""

    LIMIT = 400000              # structure elements looked at, at most

    def __init__(self, doc):
        self.doc = doc
        self.found = []         # (page, level, text, rect)
        self.total = 0          # pages to read (known once the tree is walked)

    def run(self):
        doc = self.doc
        root = struct_root(doc)
        if not root:
            return
        roles = {}
        kind, value = doc.xref_get_key(root, "RoleMap")
        if kind == "xref":
            value = doc.xref_object(_xref_of(value), compressed=True)
        if kind in ("dict", "xref"):
            roles = dict(_NAME_PAIR.findall(value))
        page_of = {doc.page_xref(i): i for i in range(doc.page_count)}

        def role(name):
            seen = 0
            while name in roles and seen < 10 and not _HEADING.match(name):
                name, seen = roles[name], seen + 1
            return name
        pages, unknown = set(), False
        todo = [(x, 0) for x in self._kids(root)[0]]
        seen, n = set(), 0
        while todo and n < self.LIMIT:
            x, pg = todo.pop()
            if x in seen:
                continue
            seen.add(x)
            n += 1
            if n % 2000 == 0:
                yield 0
            kind, s = doc.xref_get_key(x, "S")
            if kind != "name":
                continue
            s = role(s.lstrip("/"))
            kind, p = doc.xref_get_key(x, "Pg")
            pg = _xref_of(p) if kind == "xref" else pg
            kids, inline = self._kids(x)
            if _HEADING.match(s):
                m = _PG.search(inline)
                page = page_of.get(pg or (int(m.group(1)) if m else 0))
                if page is None:
                    unknown = True
                else:
                    pages.add(page)
                continue
            if s in _LEAVES:
                continue
            todo.extend((k, pg) for k in reversed(kids))
        if unknown or n >= self.LIMIT:
            pages = set(range(doc.page_count))
        self.total = len(pages)
        for k, i in enumerate(sorted(pages)):
            self.found.extend(self._read(i))
            yield k + 1

    def _kids(self, x):
        """([struct element xrefs], text of the inline kids) of the element at xref x."""
        kind, k = self.doc.xref_get_key(x, "K")
        if kind == "xref":
            return [_xref_of(k)], ""
        if kind != "array":
            return [], k if kind == "dict" else ""
        inline = " ".join(_INLINE.findall(k))
        return [int(m) for m in _REF.findall(_INLINE.sub(" ", k))], inline

    _TOKEN = re.compile(r'<struct\b([^>]*)>|</struct>|<line\b[^>]*?\btext="([^"]*)"')
    _ATTR = re.compile(r'\b(std|bbox)="([^"]*)"')

    def _read(self, i):
        """[(page, level, text, rect)] of the headings marked on page i, in order."""
        try:
            xml = self.doc[i].get_text("xml", flags=pymupdf.TEXT_COLLECT_STRUCTURE | _FLAGS)
        except Exception:
            return []
        out, stack = [], []
        for m in self._TOKEN.finditer(xml):
            if m.group(1) is not None:
                attrs = dict(self._ATTR.findall(m.group(1)))
                std = attrs.get("std", "")
                try:
                    rect = pymupdf.Rect([float(v) for v in attrs.get("bbox", "").split()])
                except (TypeError, ValueError):
                    rect = pymupdf.Rect()
                stack.append([std, [], rect])
            elif m.group(0) == "</struct>":
                if not stack:
                    continue
                std, words, rect = stack.pop()
                h = _HEADING.match(std)
                text = " ".join(" ".join(words).split())
                if h and text:
                    level = int(h.group(1)) if h.group(1) else \
                        max(1, sum(1 for e in stack if e[0] in ("Sect", "Part", "Art")))
                    out.append((i, level, text, rect))
            else:
                for e in reversed(stack):
                    if _HEADING.match(e[0]):
                        e[1].append(html.unescape(m.group(2)))
                        break
        return out

    def propose(self):
        levels = sorted({lv for _p, lv, _t, _r in self.found})
        rank = {lv: k + 1 for k, lv in enumerate(levels)}
        return [_item(rank[lv], t, p, r) for p, lv, t, r in self.found
                if rank[lv] <= MAX_LEVELS]


# ---- drawing sets ------------------------------------------------------------------------------
def disciplines():
    """Sheet number letters -> discipline (the U.S. National CAD Standard's designators)."""
    return {
        "G": tr("General"), "H": tr("Hazardous Materials"), "V": tr("Survey / Mapping"),
        "B": tr("Geotechnical"), "W": tr("Civil Works"), "C": tr("Civil"),
        "L": tr("Landscape"), "S": tr("Structural"), "A": tr("Architectural"),
        "I": tr("Interiors"), "Q": tr("Equipment"), "F": tr("Fire Protection"),
        "P": tr("Plumbing"), "D": tr("Process"), "M": tr("Mechanical"), "E": tr("Electrical"),
        "T": tr("Telecommunications"), "R": tr("Resource"), "X": tr("Other Disciplines"),
        "Z": tr("Contractor / Shop Drawings"), "O": tr("Operations"),
    }


class SheetScan:
    """Sheet numbers and titles from the title blocks (sheets.sheet_info)."""

    def __init__(self, doc):
        self.doc = doc
        self.infos = []

    def run(self):
        from . import sheets
        for i in range(self.doc.page_count):
            try:
                self.infos.append(sheets.sheet_info(self.doc[i]))
            except Exception:
                self.infos.append(None)
            yield i + 1

    def propose(self, group=False):
        names = disciplines()
        items, last = [], None
        for i, info in enumerate(self.infos):
            if not info:
                continue
            title = info["number"] + ("  " + info["title"] if info.get("title") else "")
            if group:
                letter = info["number"][:1].upper()
                if letter != last:
                    last = letter
                    name = names.get(letter, tr("Other Disciplines"))
                    items.append({"level": 1, "title": "%s - %s" % (letter, name), "page": i,
                                  "to": None, "on": True})
            items.append({"level": 2 if group else 1, "title": title, "page": i, "to": None,
                          "on": True})
        return items


# ---- making the bookmarks ------------------------------------------------------------------------
_SMALL = frozenset("a an and as at but by for from in into nor of on or per the to vs via with "
                   "de del el la las los y en con por para".split())


def title_case(text):
    """'FIRST FLOOR PLAN' -> 'First Floor Plan' (words with digits, and texts that aren't all
    capitals, are left as they are)."""
    if not _caps(text):
        return text
    out = []
    for k, w in enumerate(text.split(" ")):
        if any(c.isdigit() for c in w) or not w:
            out.append(w)
        elif k and w.lower() in _SMALL:
            out.append(w.lower())
        else:
            out.append("-".join(p[:1].upper() + p[1:].lower() for p in w.split("-")))
    return " ".join(out)


def normalize(toc):
    """Levels kept valid for set_toc: the first at level 1, none deeper than the one before
    plus one."""
    prev = 0
    for e in toc:
        e[0] = max(1, min(int(e[0]), prev + 1))
        prev = e[0]
    return toc


def toc_entries(items, depth=MAX_LEVELS, titlecase=False):
    """set_toc entries of the ticked items down to depth."""
    out = []
    for it in items:
        if not it.get("on", True) or it["level"] > depth:
            continue
        title = it["title"].strip()
        if not title:
            continue
        if titlecase:
            title = title_case(title)
        dest = {"kind": pymupdf.LINK_GOTO, "page": it["page"]}
        if it.get("to") is not None:
            dest["to"] = pymupdf.Point(it["to"])
            dest["zoom"] = 0
        out.append([it["level"], title, it["page"] + 1, dest])
    return normalize(out)


def combined(doc, new, replace=True):
    """The document's bookmarks after adding new (set_toc entries): new alone, or the
    bookmarks it had followed by new."""
    if replace:
        return normalize([list(e) for e in new])
    return normalize([list(e) for e in doc.get_toc(False)] + [list(e) for e in new])


# ---- the table of contents page -------------------------------------------------------------------
def toc_pages(doc):
    """Indexes of the pages of a table of contents made here."""
    out = []
    for i in range(doc.page_count):
        try:
            if doc.xref_get_key(doc.page_xref(i), TOC_KEY)[0] != "null":
                out.append(i)
        except Exception:
            pass
    return out


def toc_settings(doc, pages=None):
    """The title and depth the table of contents was made with: {"title", "depth"}."""
    pages = toc_pages(doc) if pages is None else pages
    out = {}
    if pages:
        x = doc.page_xref(pages[0])
        kind, t = doc.xref_get_key(x, TOC_KEY + "/Title")
        if kind == "string":
            out["title"] = t
        kind, d = doc.xref_get_key(x, TOC_KEY + "/Depth")
        if kind == "int":
            out["depth"] = max(1, min(MAX_LEVELS, int(d)))
    return out


def _encodable(texts):
    try:
        for t in texts:
            t.encode("cp1252")
        return True
    except UnicodeEncodeError:
        return False


class _Fonts:
    """Helvetica for Western texts; MuPDF's built-in Unicode font when a title has other
    letters (Greek, Cyrillic, Chinese...)."""

    def __init__(self, texts):
        if _encodable(texts):
            self.regular, self.bold = "helv", "hebo"
            self._font = None
        else:
            self.regular = self.bold = "china-s"
            self._font = pymupdf.Font("china-s")

    def width(self, text, font, size):
        if self._font is None:          # (Helvetica's widths are tabled: fast)
            return pymupdf.get_text_length(text, fontname=font, fontsize=size)
        return self._font.text_length(text, fontsize=size)


def _wrap(text, fonts, font, size, width):
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = (cur + " " + w) if cur else w
        if cur and fonts.width(trial, font, size) > width:
            lines.append(cur)
            cur = w
        else:
            cur = trial
    if cur:
        lines.append(cur)
    out = []
    for ln in lines:                    # a single word longer than the line: cut
        while fonts.width(ln, font, size) > width and len(ln) > 1:
            k = max(1, int(len(ln) * width / max(1.0, fonts.width(ln, font, size))) - 1)
            out.append(ln[:k])
            ln = ln[k:]
        out.append(ln)
    return out or [""]


def layout(entries, width, height, title, digits, fonts):
    """The table of contents laid out on pages of width x height: per page, a list of
    ("text", x, baseline, text, font, size) and ("link", rect, entry index)."""
    s = max(1.0, min(width, height) / 612.0)
    margin = 54 * s
    pages, ops = [], []
    tsize = 20 * s
    y = margin
    if title:
        ops.append(("text", margin, y + tsize, title, fonts.bold, tsize))
        y += tsize * 2.2
    right = width - margin
    for k, (lvl, text, _target) in enumerate(entries):
        size = {1: 12, 2: 11}.get(lvl, 10) * s
        font = fonts.bold if lvl == 1 else fonts.regular
        x = margin + (lvl - 1) * 18 * s
        numw = fonts.width("8" * digits, fonts.regular, size)
        lines = _wrap(text, fonts, font, size, max(40 * s, right - numw - 2 * size - x))
        lh = size * 1.5
        gap = size * 0.5 if lvl == 1 and ops and ops[-1][0] == "link" else 0
        if y + gap + lh * len(lines) > height - margin and ops:
            pages.append(ops)
            ops, y, gap = [], margin, 0
        y += gap
        top = y
        for ln in lines:
            ops.append(("text", x, y + size, ln, font, size))
            y += lh
        ops.append(("link", pymupdf.Rect(x, top, right, y - lh + size * 1.25), k))
    pages.append(ops)
    return pages


def _listed(doc, toc, depth, old):
    """([level, title, (page xref, point, zoom)] of the bookmarks the table lists, [indexes
    of the bookmarks to a page of the old table (old: its page indexes)])."""
    old_xrefs = {doc.page_xref(i) for i in old}
    entries, to_old = [], []
    for idx, (lvl, text, page, dest) in enumerate(toc):
        if dest.get("kind") != pymupdf.LINK_GOTO or not 1 <= page <= doc.page_count:
            continue
        xref = doc.page_xref(page - 1)
        if xref in old_xrefs:
            to_old.append(idx)          # (a bookmark to the old table: to the new one)
            continue
        if lvl <= depth:
            entries.append([lvl, text, (xref, dest.get("to"), dest.get("zoom", 0))])
    return normalize(entries), to_old


def toc_list(doc, depth=MAX_LEVELS, replace=True):
    """[(level, title, page index)] that a table of contents would list."""
    entries, _old = _listed(doc, doc.get_toc(False), depth, toc_pages(doc) if replace else [])
    index_of = {doc.page_xref(i): i for i in range(doc.page_count)}
    return [(e[0], e[1], index_of[e[2][0]]) for e in entries]


def insert_toc(doc, at=0, title=None, depth=MAX_LEVELS, size=None, replace=True):
    """Insert a table of contents of doc's bookmarks (down to depth) before page index at,
    or in place of the one made before when replace and there is one. size: (width,
    height) of its pages; None: as shown, the size of the page it goes before. Returns
    (first page, page count), or None when there are no bookmarks to list."""
    title = tr("Contents") if title is None else title
    old = toc_pages(doc) if replace else []
    toc = doc.get_toc(False)
    entries, to_old = _listed(doc, toc, depth, old)
    if not entries:
        return None
    if old:
        at = old[0]
        doc.delete_pages(old)
    at = max(0, min(at, doc.page_count))
    if size is None:
        ref = doc[min(at, doc.page_count - 1)].rect
        size = (ref.width, ref.height)
    width, height = size
    fonts = _Fonts([title] + [e[1] for e in entries])
    n = 1
    for _ in range(4):                  # the page count changes the page numbers' width
        digits = len(str(doc.page_count + n))
        pages = layout(entries, width, height, title, digits, fonts)
        if len(pages) == n:
            break
        n = len(pages)
    for k in range(len(pages)):
        doc.new_page(at + k, width=width, height=height)
    index_of = {doc.page_xref(i): i for i in range(doc.page_count)}
    marker = "<</Title %s/Depth %d>>" % (pymupdf.get_pdf_str(title), depth)
    for k, ops in enumerate(pages):
        page = doc[at + k]
        doc.xref_set_key(page.xref, TOC_KEY, marker)
        shape = page.new_shape()
        for op in ops:
            if op[0] == "text":
                _kind, x, base, text, font, fsize = op
                shape.insert_text((x, base), text, fontname=font, fontsize=fsize, color=(0, 0, 0))
        # page numbers and dotted leaders, at the last line of each entry
        last_text = None
        links = []
        for op in ops:
            if op[0] == "text":
                last_text = op
                continue
            _kind, rect, e = op
            xref, to, zoom = entries[e][2]
            target = index_of[xref]
            num = str(target + 1)
            _k, x, base, text, font, fsize = last_text
            nw = fonts.width(num, fonts.regular, fsize)
            nx = rect.x1 - nw
            shape.insert_text((nx, base), num, fontname=fonts.regular, fontsize=fsize,
                              color=(0, 0, 0))
            start = x + fonts.width(text, font, fsize) + fsize * 0.6
            # (the dots end at the same place on every line of a size: the widest number's)
            end = rect.x1 - fonts.width("8" * digits, fonts.regular, fsize) - fsize * 0.4
            dot = fonts.width(" .", fonts.regular, fsize)
            count = int((end - start) / dot) if dot > 0 else 0
            if count >= 2:
                shape.insert_text((end - count * dot, base), " ." * count,
                                  fontname=fonts.regular, fontsize=fsize, color=(0.35, 0.35, 0.35))
            link = {"kind": pymupdf.LINK_GOTO, "from": rect, "page": target,
                    "to": pymupdf.Point(to) if to is not None else pymupdf.Point(0, 0),
                    "zoom": zoom or 0}
            links.append(link)
        shape.commit()
        for link in links:
            page.insert_link(link)
    first = at
    for idx in to_old:
        dest = toc[idx][3]
        doc.set_toc_item(idx, dest_dict=dict(dest, page=first, to=pymupdf.Point(0, 0)))
        if not dest.get("color") and dest.get("xref"):
            doc.xref_set_key(dest["xref"], "C", "null")         # (not grayed out)
    return first, len(pages)

