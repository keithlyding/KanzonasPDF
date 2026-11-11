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
numbers, each line a link to its page, in fonts embedded in its pages (PDF/A; the same in
every reader); each title is a block of added text (added_text), so Edit text opens it whole.
The pages carry /KZTOC in their page dictionary, so running it again replaces them instead of
adding another one.
"""

import html
import json
import re
import sys
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
    __slots__ = ("page", "text", "size", "bold", "chars", "rect", "yf0", "yf1", "cells",
                 "toc")

    def __init__(self, page, text, size, bold, chars, rect, yf0, yf1, cells=1, toc=False):
        self.page, self.text, self.size, self.bold, self.chars = page, text, size, bold, chars
        self.rect, self.yf0, self.yf1 = rect, yf0, yf1
        self.cells = cells      # pieces of text on its row (3 or more: a table's row)
        self.toc = toc          # a line of a table of contents: a page number at its right

    @property
    def alone(self):
        return self.cells == 1


# A page's lines are read from MuPDF's own outputs of the page's text (_mupdf_lines): its XML
# without the characters (each line's box and direction), its HTML (each piece of a line in
# one font, its size and whether the font is bold) and its JSON (the name of each line's first
# font). PyMuPDF's get_text("dict") gives the same, but builds it a character at a time
# through MuPDF calls that are each slow on macOS: a 500-page document took 3.5 s there
# against 0.6 s on Linux (PyMuPDF 2.1; MuPDF's own outputs take 0.04 s per 200 pages on
# both). A page they can't tell everything about falls back to get_text("dict") (_dict_lines):
# when the three don't list the same lines, or when a line in several fonts could have a later
# one whose name says bold though MuPDF doesn't take it as bold (only the first one's name is
# known). On 1,631 pages of 420 documents both ways gave the same lines, words, sizes, bold
# and boxes (PyMuPDF 2.0; with 2.1, which measures some fonts' lines from the font's own
# heights, a line in a symbol font on 12 of them was up to a point taller through
# get_text("dict")); 51 of them fell back (tests/test_bookmarks_auto.py: MuPDFLines).
_SUBSET = re.compile(r"^[A-Z]{6}\+")
_XML_ITEM = re.compile(r'<(block|line) bbox="([^"]*)"(?: wmode="[^"]*" dir="([^"]*)")?')
_HTML_LINE = re.compile(r"<p\b[^>]*>(.*?)</p>", re.S)
_HTML_TOKEN = re.compile(r'<(/?)([a-z]+)(?: style="([^"]*)")?\s*/?>|([^<]+)')
_HTML_SIZE = re.compile(r"font-size:([0-9.]+)pt")


def _mupdf_output(tp, write, *args):
    m = pymupdf.mupdf
    buf = m.fz_new_buffer(4096)
    out = m.FzOutput(buf)
    write(out, tp.this, *args)
    out.fz_close_output()
    return m.fz_buffer_extract_copy(buf).decode("utf-8", "replace")


def _html_pieces(line):
    """[(text, size, bold)] of one line of MuPDF's HTML (a <span> for each run in one font)."""
    out = []
    bold = 0
    size = None
    for close, tag, style, text in _HTML_TOKEN.findall(line):
        if text:
            if size is None:        # (MuPDF writes every letter in a span: not as expected)
                raise ValueError("text outside a span")
            out.append((html.unescape(text), size, bold > 0))
        elif tag == "b":
            bold += -1 if close else 1
        elif tag == "span":
            if close:
                size = None
            else:
                found = _HTML_SIZE.search(style or "")
                size = float(found.group(1)) if found else 0.0
    return out


def _mupdf_lines(page):
    """[(direction, box, [(text, size, bold)])] of the page's lines, from MuPDF's outputs;
    None when they can't tell everything get_text("dict") would."""
    try:
        return _read_mupdf_lines(page)
    except Exception:           # (something in them not as expected: read it the other way)
        return None


def _read_mupdf_lines(page):
    m = pymupdf.mupdf
    tp = page.get_textpage(flags=_FLAGS)        # (through the text guard, as everywhere)
    xml = _mupdf_output(tp, m.fz_print_stext_page_as_xml_with_flags, 0, 0)
    page_html = _mupdf_output(tp, m.fz_print_stext_page_as_html, 0)
    js = json.loads(_mupdf_output(tp, m.fz_print_stext_page_as_json, 1.0))
    area = pymupdf.Rect(tp.rect)
    ax0, ay0, ax1, ay1 = area
    everywhere = area.is_infinite
    lines, block = [], True
    for kind, box, direction in _XML_ITEM.findall(xml):
        x0, y0, x1, y1 = (float(v) for v in box.split())
        # (get_text("dict") leaves out a block, and a line, that has no area on the page)
        on = everywhere or (max(x0, ax0) < min(x1, ax1) and max(y0, ay0) < min(y1, ay1))
        if kind == "block":
            block = on
        else:
            lines.append((block and on, direction, (x0, y0, x1, y1)))
    pieces = _HTML_LINE.findall(page_html)
    firsts = [ln.get("font") or {} for b in js.get("blocks", ()) if b.get("type") == "text"
              for ln in b.get("lines", ())]
    if not (len(lines) == len(pieces) == len(firsts)):
        return None
    bold_font = {}                      # font name: MuPDF takes it as bold
    for f in firsts:
        bold_font[_SUBSET.sub("", f.get("name") or "")] = f.get("weight") == "bold"
    risky = None                        # fonts whose name says bold, MuPDF not (or unknown)
    out = []
    for (keep, direction, r), line, first in zip(lines, pieces, firsts):
        if not keep:
            continue
        spans = _html_pieces(line)
        name = _SUBSET.sub("", first.get("name") or "")
        if len(spans) > 1:
            if risky is None:
                names = {_SUBSET.sub("", f[3]) for f in page.get_fonts(full=True)}
                risky = {n for n in names | set(bold_font)
                         if _BOLD_NAME.search(n) and not bold_font.get(n)}
            if risky:
                return None
        if spans and _BOLD_NAME.search(name):
            spans[0] = (spans[0][0], spans[0][1], True)
        out.append((tuple(float(v) for v in direction.split()), pymupdf.Rect(r), spans))
    return out


def _dict_lines(page):
    """The same as _mupdf_lines, from PyMuPDF's get_text("dict")."""
    try:
        d = page.get_text("dict", flags=_FLAGS)
    except Exception:
        return []
    return [(ln["dir"], pymupdf.Rect(ln["bbox"]),
             [(s["text"], s["size"], bool(s["flags"] & 16 or _BOLD_NAME.search(s["font"] or "")))
              for s in ln["spans"]])
            for b in d.get("blocks", ()) if b.get("type") == 0 for ln in b.get("lines", ())]


def _line_pieces(page):
    """[(order, text, size, bold chars, chars, rect (unrotated), shown rect)] of the page's
    upright lines."""
    lines = _mupdf_lines(page)
    if lines is None:
        lines = _dict_lines(page)
    rot = page.rotation_matrix
    a, c = rot.a, rot.c
    upright = page.rotation == 0        # (most pages: no turning, one rect for both)
    out = []
    for (dx, dy), r, spans in lines:
        if dx * a + dy * c < 0.9:       # sideways text (labels on drawings): never a heading
            continue
        sizes = Counter()
        bold = chars = 0
        for text, size, is_bold in spans:
            n = len("".join(text.split()))      # (letters and signs, not spaces: the same
            if not n:                           # however a line is cut into pieces)
                continue
            sizes[round(size * 2) / 2] += n
            if is_bold:
                bold += n
            chars += n
        if not chars:
            continue
        text = " ".join("".join(s[0] for s in spans).split())
        out.append((len(out), text, sizes.most_common(1)[0][0], bold, chars, r,
                    r if upright else r * rot))
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
        # a title and its page number (not a table's row of cells): a contents line
        listed = len(items) in (2, 3) and _PAGE_REF.match(items[-1][1]) is not None
        for k, it in enumerate(items):
            toc = listed and k < len(items) - 1 and len(_LETTER.findall(it[1])) >= 3
            out.append((it[0], Row(index, it[1], it[2], it[3] >= 0.6 * it[4], it[4], it[5],
                                   it[6].y0 / height, it[6].y1 / height, len(items), toc)))
    out.sort(key=lambda x: x[0])
    return [r for _o, r in out]


# ---- what makes a heading ------------------------------------------------------------------
_LEADER = re.compile(r"(\.\s?){4,}|…{2,}|_{4,}|(·\s?){4,}")
_PAGE_NO = re.compile(r"^(page|p\.|pg\.?|página|pág\.)?\s*([0-9]+|[ivxlc]+)"
                      r"(\s*(of|/|de)\s*[0-9]+)?$", re.I)
_PAGE_REF = re.compile(r"^([0-9]{1,4}|(?=[ivxlc])c{0,3}(xc|xl|l?x{0,3})(ix|iv|v?i{0,3})|"
                       r"[A-Z]?-?[0-9]{1,3}(-[0-9]{1,3})?)$")
_CONTENTS = re.compile(r"^((table\s+of\s+)?contents|(tabla\s+de\s+)?contenidos?|índice)$", re.I)
_LETTER = re.compile(r"[^\W\d_]")
_DIGITS = re.compile(r"\d+")
_RANKS = [
    (re.compile(r"^division\s+\d{1,2}\b", re.I), 0),
    (re.compile(r"^section\s+\d", re.I), 1),
    (re.compile(r"^(chapter|appendix|annex|attachment|exhibit|cap\u00edtulo|capitulo|anexo|"
                r"ap\u00e9ndice)\s+"
                r"([0-9]{1,3}|[ivxlc]{1,6}|[a-z])\b", re.I), 1),
    (re.compile(r"^part\s+([0-9]{1,2}|[ivx]{1,4}|[a-z]|one|two|three|four|five|six)\b", re.I), 2),
    (re.compile(r"^(article|artículo)\s+([0-9]{1,3}|[ivxlc]{1,6})\b", re.I), 3),
    (re.compile(r"^[IVX]{1,5}\.\s+\S"), 3),
]
_BARE = re.compile(r"^(division|section|chapter|part|article|appendix|attachment|annex|exhibit|"
                   r"schedule|capítulo|capitulo|anexo|artículo|sección|parte)\s+"
                   r"[\w.\-]{1,12}$", re.I)
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
    if r.toc or len(t) < 2 or len(t) > 160 or _LEADER.search(t) or _PAGE_NO.match(t.strip(" -–—")):
        return False, None
    if len(_LETTER.findall(t)) < 2:
        return False, None
    words = len(t.split())
    if words > 18:
        return False, None
    rank = numbering(t)
    sentence = t.endswith((".", ";", ",")) and words > 5 and rank is None
    if r.size >= body * 1.12 and r.size - body >= 1.0:
        return r.cells <= 2 and not (sentence and words > 10), rank
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
        # a page with three lines or more ending in a page number is a table of contents
        listing = Counter(r.page for r in rows if r.toc)
        contents = {p for p, n in listing.items() if n >= 3}
        # [page, first row, last row, size, bold, rank, text, rect, lines, last line's look]
        heads = []
        for idx, r in enumerate(rows):
            if idx in furniture or r.page in contents:
                continue
            ok, rank = _candidate(r, body, bold_body)
            if not ok:
                continue
            h = heads[-1] if heads else None
            close = h is not None and h[0] == r.page and h[2] == idx - 1
            if close and h[8] == 1 and rank is None and _BARE.match(h[6]) and \
                    -0.2 * r.size <= r.rect.y0 - h[7].y1 < 1.5 * max(h[3], r.size):
                # "SECTION A" over "GENERAL CONDITIONS": one heading, whatever their looks
                h[2], h[3], h[4] = idx, max(h[3], r.size), h[4] or r.bold
                h[6] = h[6] + " - " + r.text
                h[7] = h[7] | r.rect
                h[9] = (r.size, r.bold)
                continue
            if close and h[9] == (r.size, r.bold) and \
                    -0.2 * r.size <= r.rect.y0 - h[7].y1 < 0.9 * r.size:
                h[2] = idx              # (the next line of the same heading, or a paragraph)
                h[8] += 1
                if rank is None or h[8] > 3:
                    h[6] = h[6] + " " + r.text
                    h[7] = h[7] | r.rect
                    continue
                h[8] -= 1
                h[2] = idx - 1
            heads.append([r.page, idx, idx, r.size, r.bold, rank, r.text, pymupdf.Rect(r.rect), 1,
                          (r.size, r.bold)])
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
        # set apart (listed unticked at level 1, not counted as a level): a "Contents"
        # heading, the lines of a cover page (a first page with none of the looks that go
        # on through the document), and one line bigger than all the rest near the start
        # (the title)
        first_page = min(r.page for r in rows)
        aside = {id(h) for hs in used.values() for h in hs if _CONTENTS.match(h[6].strip())}
        spread = {s for s, hs in used.items() if any(h[0] != first_page for h in hs)}
        if spread and not any(h[0] == first_page for s in spread for h in used[s]):
            aside |= {id(h) for hs in used.values() for h in hs if h[0] == first_page}
        order = [s for s in sorted(used) if any(id(h) not in aside for h in used[s])]
        if len(order) > 1:
            top = [h for h in used[order[0]] if id(h) not in aside]
            if len(top) == 1 and top[0][0] <= first_page + 2:
                aside.add(id(top[0]))
                order = order[1:]
        level_of = {s: k + 1 for k, s in enumerate(order)}
        for s in order[:MAX_LEVELS]:
            (size, bold), rank = slots[s]
            self.styles.append((_style_name(size, bold), level_of[s], len(used[s])))
        items = []
        for h in sorted((h for g in groups.values() for h in g), key=lambda h: (h[0], h[1])):
            if id(h) in aside:
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


# ---- outlines nested deep ------------------------------------------------------------------
def _outline_depth(doc):
    """How many levels deep the document's outline goes (as MuPDF read it)."""
    deepest = 0
    todo = [(doc.outline, 1)] if doc.outline else []
    while todo:
        o, lvl = todo.pop()
        while o is not None and o.this.m_internal:
            deepest = max(deepest, lvl)
            if o.down:
                todo.append((o.down, lvl + 1))
            o = o.next
    return deepest


def _outline_xrefs(obj, xrefs):
    """PyMuPDF's JM_outline_xrefs (the object numbers of the outline items from obj, in
    order: each item, the items under it, then the next), without recursing, and with
    the items seen in a set (it searched its list for each: 100,000 bookmarks took half a
    minute to write)."""
    m = pymupdf.mupdf
    get, is_dict, num = m.pdf_dict_gets, m.pdf_is_dict, m.pdf_to_num
    seen = set(xrefs)
    todo = [obj]
    while todo:
        this = todo.pop()
        while this.m_internal:
            x = num(this)
            if x in seen or get(this, "Type").m_internal:
                break                   # (a loop, or the top of the outline)
            xrefs.append(x)
            seen.add(x)
            first = get(this, "First")
            nxt = get(this, "Next")
            if not is_dict(nxt):
                nxt = None
            if is_dict(first):
                if nxt is not None:
                    todo.append(nxt)
                this = first
            elif nxt is not None:
                this = nxt
            else:
                break
    return xrefs


PYMUPDF_OWN = {}                # PyMuPDF's own steps replaced below (for the tests)


def set_toc_dest(doc, idx, dest):
    """Document.set_toc_item(idx, dest_dict=dest) for a bookmark to a page (dest a
    get_toc(False) destination, with its "xref"), without reading the whole outline to find
    the bookmark's object (set_toc_item does, so moving 1,000 of 3,000 bookmarks took
    10 s): dest's own xref is written."""
    xref = dest.get("xref")
    if not xref or dest.get("kind") != pymupdf.LINK_GOTO:
        doc.set_toc_item(idx, dest_dict=dest)
        return
    dest = dict(dest)
    pno = dest["page"]
    to = pymupdf.Point(dest.get("to", pymupdf.Point(72, 36)))
    to.y = doc.page_cropbox(pno).height - to.y
    dest["to"] = to
    action = pymupdf.utils.getDestStr(doc.page_xref(pno), dest)
    if not action.startswith("/A"):
        raise ValueError("bad bookmark dest")
    color = dest.get("color")
    if color:
        color = list(map(float, color))
    doc._update_toc_item(xref, action=action[2:], title=None, color=color,
                         flags=dest.get("italic", False) + 2 * dest.get("bold", False),
                         collapse=dest.get("collapse"))


def apply_deep_outlines():
    """Wrap Document.get_toc and replace JM_outline_xrefs (once): PyMuPDF reads the outline
    recursing, one call per level, so a file whose bookmarks nest a thousand levels deep
    raised RecursionError everywhere the bookmarks are read or written: the Bookmarks
    panel stayed empty and deleting a page (which moves the bookmarks) failed. get_toc is
    read again with room for the depth."""
    own = pymupdf.Document.get_toc
    if getattr(own, "_kz_deep", False):
        return
    if hasattr(pymupdf, "JM_outline_xrefs"):
        PYMUPDF_OWN["JM_outline_xrefs"] = pymupdf.JM_outline_xrefs
        pymupdf.JM_outline_xrefs = _outline_xrefs

    def get_toc(doc, simple=True):
        try:
            return own(doc, simple)
        except RecursionError:
            pass
        old = sys.getrecursionlimit()
        sys.setrecursionlimit(old + 4 * _outline_depth(doc) + 200)
        try:
            return own(doc, simple)
        finally:
            sys.setrecursionlimit(old)
    get_toc.__doc__ = own.__doc__
    get_toc._kz_deep = True
    pymupdf.Document.get_toc = get_toc
    # (the styles of many bookmarks: PyMuPDF's compiled helper searches a list for each,
    # 25 s for 100,000 when a file opened; its own Python steps, through the outline_xrefs
    # above, take a second)
    extend = getattr(pymupdf.Document, "_extend_toc_items", None)
    if extend is not None and hasattr(pymupdf, "g_use_extra"):
        def _extend_toc_items(doc, items):
            if len(items) < 2000 or not pymupdf.g_use_extra:
                return extend(doc, items)
            pymupdf.g_use_extra = False
            try:
                return extend(doc, items)
            finally:
                pymupdf.g_use_extra = True
        PYMUPDF_OWN["_extend_toc_items"] = extend
        pymupdf.Document._extend_toc_items = _extend_toc_items


apply_deep_outlines()


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


def writable(doc, dest):
    """A copy of a bookmark's destination (get_toc(simple=False)) that set_toc writes back
    as it was: one to a named destination becomes one to the place it names (set_toc can't
    write names, and would leave the bookmark going nowhere)."""
    d = dict(dest or {})
    d.pop("xref", None)                 # (set_toc gives every bookmark a new object)
    page = d.get("page", -1)
    if d.get("kind") == pymupdf.LINK_NAMED and 0 <= page < doc.page_count:
        d["kind"] = pymupdf.LINK_GOTO
        d.pop("nameddest", None)
        d.pop("name", None)
        to = d.get("to")
        if to is not None:              # (given in PDF coordinates there, from the top here)
            d["to"] = pymupdf.Point(to.x, doc.page_cropbox(page).height - to.y)
    return d


def writable_toc(doc, toc):
    """toc (entries of 3 or 4) as set_toc should be given it (see writable)."""
    return [list(e[:3]) + ([writable(doc, e[3])] if len(e) > 3 and isinstance(e[3], dict)
                           else []) for e in toc]


def combined(doc, new, replace=True):
    """The document's bookmarks after adding new (set_toc entries): new alone, or the
    bookmarks it had followed by new."""
    if replace:
        return normalize([list(e) for e in new])
    return normalize(writable_toc(doc, doc.get_toc(False)) + [list(e) for e in new])


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


def forget_title(page):
    """Apply redactions on a table of contents page: the title it remembers goes (the
    marks may have covered it on the page; the next table made in its place takes the
    default title)."""
    doc = page.parent
    if doc.xref_get_key(page.xref, TOC_KEY + "/Title")[0] != "null":
        doc.xref_set_key(page.xref, TOC_KEY + "/Title", "null")


def clean_title(doc, pat, clean):
    """Search & redact: the title the table of contents pages remember, the terms (pat)
    taken out of it (clean)."""
    for i in toc_pages(doc):
        x = doc.page_xref(i)
        kind, t = doc.xref_get_key(x, TOC_KEY + "/Title")
        if kind == "string" and pat.search(t):
            doc.xref_set_key(x, TOC_KEY + "/Title", pymupdf.get_pdf_str(clean(t)))


def _encodable(texts):
    try:
        for t in texts:
            t.encode("cp1252")
        return True
    except UnicodeEncodeError:
        return False


def _font_with(texts):
    """(name, Font, source) of an embeddable font with every character of texts: the
    bundled Unicode font (Droid Sans Fallback), else an installed font that covers many
    alphabets; the bundled one when none has them all."""
    from . import text_edit as te
    chars = {c for t in texts for c in t if not c.isspace()}
    cjk = pymupdf.Font("cjk")
    if all(cjk.has_glyph(ord(c)) for c in chars):
        return "KZUni", cjk, {"fontbuffer": cjk.buffer}
    fonts = te._system_fonts()
    for key in te.BROAD_FONTS:
        path = fonts.get(key)
        if not path:
            continue
        try:
            font = pymupdf.Font(fontfile=path)
        except Exception:
            continue
        if all(font.has_glyph(ord(c)) for c in chars):
            return "KZB" + key[:20], font, {"fontfile": path}
    return "KZUni", cjk, {"fontbuffer": cjk.buffer}


class _Measured:
    """A pymupdf.Font whose text widths are remembered letter by letter (a long table
    measures the same few letters hundreds of thousands of times)."""

    def __init__(self, font):
        self._font = font
        self._adv = {}

    def __getattr__(self, name):
        return getattr(self._font, name)

    def text_length(self, text, fontsize=11):
        adv = self._adv
        total = 0.0
        for c in text:
            w = adv.get(c)
            if w is None:
                w = adv[c] = self._font.text_length(c, fontsize=1)
            total += w
        return total * fontsize


class _Fonts:
    """The fonts the table is written in, embedded in its pages (so it looks the same in
    every reader and passes PDF/A's check): MuPDF's own Helvetica (Nimbus Sans, the
    program it draws Helvetica with) and its bold for Western texts; for titles with other
    letters (Greek, Cyrillic, Chinese...) the bundled Unicode font (or an installed one),
    made bold by thickening. styles(size, bold) gives the text_styles.Style to write with;
    table: {Style: text_styles.Font} of every style asked for (what added_text.write and
    text_styles' wrapping take)."""

    def __init__(self, texts):
        from . import text_styles as ts
        self._ts = ts
        if _encodable(texts):
            helv, hebo = pymupdf.Font("helv"), pymupdf.Font("hebo")
            self._faces = {False: ("KZHelv", _Measured(helv), {"fontbuffer": helv.buffer},
                                   False),
                           True: ("KZHebo", _Measured(hebo), {"fontbuffer": hebo.buffer},
                                  False)}
        else:
            name, font, source = _font_with(texts)
            font = _Measured(font)
            self._faces = {False: (name, font, source, False), True: (name, font, source, True)}
        self.table = {}

    def style(self, size, bold=False, color=(0, 0, 0)):
        key = self._ts.add_style("", bold, False, size, color)
        if key not in self.table:
            name, font, source, thick = self._faces[bool(bold)]
            self.table[key] = self._ts.Font(name, font, source, thick, False)
        return key

    def width(self, text, key):
        return self.table[key].font.text_length(text, fontsize=key.size)

    def on(self, page):
        """table with the fonts put into page (the names to write with there; no source:
        added_text.write doesn't put them in again for every title)."""
        from . import text_edit as te
        done, out = {}, {}
        for k, f in self.table.items():
            if f.name not in done:
                done[f.name] = te._insert_font(page, f.name, **f.source)
            out[k] = f._replace(name=done[f.name], source=None)
        return out


def _rows(text, key, fonts, width):
    """(text, the rows it wraps to at width): text_styles' own wrapping, as added_text.write
    does it; a word longer than the line is cut (a line break put into text)."""
    ts = fonts._ts
    words = []
    for w in text.split():
        while len(w) > 1 and fonts.width(w, key) > width:
            k = max(1, int(len(w) * width / max(1.0, fonts.width(w, key))) - 1)
            while k > 1 and fonts.width(w[:k], key) > width:
                k -= 1
            words.append(w[:k] + "\n")
            w = w[k:]
        words.append(w + " ")
    text = "".join(words).rstrip(" ").replace("\n ", "\n") or " "
    rows = ts.wrap([(c, key) for c in text], fonts.table, width)
    return text, ["".join(c for c, _k in ts.strip_row(r)) for r, _f, _l in rows] or [""]


def layout(entries, width, height, title, digits, fonts):
    """The table of contents laid out on pages of width x height: per page, a list of
    ("text", x, first baseline, text, Style, wrap width, [its rows], baseline to baseline)
    and ("link", rect, entry index)."""
    s = max(1.0, min(width, height) / 612.0)
    margin = 54 * s
    pages, ops = [], []
    tsize = 20 * s
    y = margin
    if title:
        key = fonts.style(tsize, True)
        text, rows = _rows(title, key, fonts, width - 2 * margin)
        ops.append(("text", margin, y + tsize, text, key, width - 2 * margin, rows,
                    tsize * 1.2))
        y += tsize * (2.2 + 1.2 * (len(rows) - 1))
    right = width - margin
    for k, (lvl, text, _target) in enumerate(entries):
        size = {1: 12, 2: 11}.get(lvl, 10) * s
        key = fonts.style(size, lvl == 1)
        plain = fonts.style(size)
        x = margin + (lvl - 1) * 18 * s
        numw = fonts.width("8" * digits, plain)
        wrap = max(40 * s, right - numw - 2 * size - x)
        text, lines = _rows(text, key, fonts, wrap)
        lh = size * 1.5
        gap = size * 0.5 if lvl == 1 and ops and ops[-1][0] == "link" else 0
        if y + gap + lh * len(lines) > height - margin and ops:
            pages.append(ops)
            ops, y, gap = [], margin, 0
        y += gap
        top = y
        ops.append(("text", x, y + size, text, key, wrap, lines, lh))
        y += lh * len(lines)
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


def _one_stream(page):
    """The page's content streams (each block of added text wrote one) joined into one."""
    doc = page.parent
    xs = page.get_contents()
    if len(xs) > 1:
        doc.update_stream(xs[0], b"\n".join(doc.xref_stream(x) or b"" for x in xs))
        doc.xref_set_key(page.xref, "Contents", "%d 0 R" % xs[0])


def _cid_maps(page):
    """PDF/A wants a TrueType CIDFont's CIDToGIDMap named (PyMuPDF leaves out /Identity,
    the default): given to the fonts the table wrote with."""
    doc = page.parent
    for f in page.get_fonts(full=True):
        if f[2] != "Type0" or not f[4].startswith("KZ"):
            continue
        kind, val = doc.xref_get_key(f[0], "DescendantFonts")
        m = re.match(r"\[\s*(\d+)\s+0\s+R", val or "") if kind == "array" else None
        if m is None:
            continue
        cid = int(m.group(1))
        if doc.xref_get_key(cid, "Subtype")[1] == "/CIDFontType2" and \
                doc.xref_get_key(cid, "CIDToGIDMap")[0] == "null":
            doc.xref_set_key(cid, "CIDToGIDMap", "/Identity")


def insert_toc(doc, at=0, title=None, depth=MAX_LEVELS, size=None, replace=True):
    """Insert a table of contents of doc's bookmarks (down to depth) before page index at,
    or in place of the one made before when replace and there is one. size: (width,
    height) of its pages; None: as shown, the size of the page it goes before. Returns
    (first page, page count), or None when there are no bookmarks to list."""
    from . import added_text, text_styles as ts
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
    gray = (0.35, 0.35, 0.35)
    for k, ops in enumerate(pages):
        page = doc[at + k]
        doc.xref_set_key(page.xref, TOC_KEY, marker)
        table = fonts.on(page)
        # each title (and the table's own) is a block of added text (added_text), wrapped
        # to its width: Edit text opens and rewraps it as one
        for op in ops:
            if op[0] == "text":
                _kind, x, base, text, key, wrap, _rows_, step = op
                added_text.write(page, (x, base), 0, text, [key] * len(text), step,
                                 width=wrap, fonts=table)
        # page numbers and dotted leaders, at the last line of each entry (the leaders an
        # artifact: a screen reader doesn't read them)
        shape = page.new_shape()
        leaders = page.new_shape()
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
            _k, x, base, _text, key, _wrap, rows, step = last_text
            base += step * (len(rows) - 1)
            plain = fonts.style(key.size)
            nw = fonts.width(num, plain)
            nx = rect.x1 - nw
            shape.insert_text((nx, base), num, fontname=table[plain].name,
                              fontsize=key.size, color=(0, 0, 0))
            start = x + fonts.width(rows[-1], key) + key.size * 0.6
            # (the dots end at the same place on every line of a size: the widest number's)
            end = rect.x1 - fonts.width("8" * digits, plain) - key.size * 0.4
            dot = fonts.width(" .", plain)
            count = int((end - start) / dot) if dot > 0 else 0
            if count >= 2:
                leaders.insert_text((end - count * dot, base), " ." * count,
                                    fontname=table[plain].name, fontsize=key.size, color=gray)
            link = {"kind": pymupdf.LINK_GOTO, "from": rect, "page": target,
                    "to": pymupdf.Point(to) if to is not None else pymupdf.Point(0, 0),
                    "zoom": zoom or 0}
            # (what a screen reader says for the link: PDF/UA wants every link described)
            links.append((link, tr("{title}, page {page}").format(
                title=" ".join(entries[e][1].split()), page=num)))
        shape.commit()
        if leaders.text_cont:
            leaders.text_cont = "/Artifact BMC\n" + leaders.text_cont + "\nEMC\n"
            leaders.commit()
        ts.fix_spaces(page, {k: f._replace(source=True) for k, f in table.items()})
        _cid_maps(page)
        _one_stream(page)
        for link, words in links:
            page.insert_link(link)
            xref = page.annot_xrefs()[-1][0]
            doc.xref_set_key(xref, "Contents", pymupdf.get_pdf_str(words))
    first = at
    for idx in to_old:
        dest = toc[idx][3]
        set_toc_dest(doc, idx, dict(dest, page=first, to=pymupdf.Point(0, 0)))
        if not dest.get("color") and dest.get("xref"):
            doc.xref_set_key(dest["xref"], "C", "null")         # (not grayed out)
    _tag_toc(doc, first, len(pages))
    return first, len(pages)


def _tag_toc(doc, first, count):
    """On a tagged document, the table's pages tagged as a table of contents (PDF 32000-1
    14.8.4.3.2): a TOC element holding a TOCI per entry, each a Link holding the entry's
    words, its page number and its link annotation; the leaders are artifacts. (Tagged
    plainly, as any page added to a tagged document, each title was a P, the page numbers
    one P together and each link a Link of its own, holding no words.)"""
    from . import pdfcoords, tag_upkeep as tu
    if not tu.is_tagged(doc):
        return
    pages = list(range(first, first + count))
    tu.refresh(doc, None, True, pages)          # (everything tagged, in step)
    tree = tu.kept_tree(doc)                    # (changed here, and kept: the refresh below)
    if tree.root is None:
        return
    toc = None
    moved = []
    for i in pages:
        page = doc[i]
        px = page.xref
        st = tu.PageState(page)
        seq_box, _pb = st.boxes()
        box_of = {}
        for ser, b in seq_box.items():
            mc = st.seqs[ser][0][2]
            box_of[mc] = b if mc not in box_of else box_of[mc] | b
        to_page = pdfcoords.to_page(page) * page.rotation_matrix
        links = []
        for num, sub, shown in tu._annot_list(doc, px, tree.pdf):
            if sub != "Link" or not shown or len(tree.objr.get(num, ())) != 1:
                continue
            try:
                r = doc.xref_get_key(num, "Rect")[1].strip("[]").split()
                links.append((num, (pymupdf.Rect([float(v) for v in r]) * to_page)
                              .normalize()))
            except (TypeError, ValueError):
                continue
        if not links:
            continue
        held = {}                       # link -> [mcid] of the words it covers
        for mc in sorted(tree.page_refs.get(px, ())):
            b = box_of.get(mc)
            if b is None or len(tree.refs.get((px, mc), ())) != 1:
                continue
            c = pymupdf.Point((b.x0 + b.x1) / 2, (b.y0 + b.y1) / 2)
            hit = next((num for num, r in links if r.contains(c)), None)
            if hit is not None:
                held.setdefault(hit, []).append(mc)
        if toc is None:
            kids = tree.top.kids if tree.top is not None else tree.tops
            olds = [tree.refs[(px, mc)][0] for mcs in held.values() for mc in mcs] + \
                [tree.objr[num][0] for num, _r in links]
            tops = []
            for e in olds:
                while e.parent is not None and e.parent is not tree.top:
                    e = e.parent
                tops.append(e)
            at = min((kids.index(e) for e in tops if e in kids), default=None)
            toc = tree.new_el("TOC", px, at=at)
        for num, _r in links:
            item = tree.new_el("TOCI", px, parent=toc)
            link = tree.new_el("Link", px, parent=item)
            for mc in held.get(num, ()):
                old = tree.refs[(px, mc)][0]
                tree.drop_mcid(old, (px, mc))
                tree.add_mcid(link, px, mc)
                moved.append(old)
            old = tree.objr[num][0]
            tree.drop_objr(old, num)
            tree.add_objr(link, num, px)
            moved.append(old)
    for e in moved:
        tree.prune(e)
    if toc is not None:
        tu.refresh(doc, pages)          # (the parent tree pointing at the new elements)

