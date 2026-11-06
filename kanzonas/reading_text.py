"""A page's text as a reader takes it in: blocks in reading order (columns one after the
other, as well as the page's text allows), each with its lines and words, the words' places on
the page and the block's type size. Used by View > Reading view (the text reflowed) and View >
Read aloud (sentences spoken one by one, the word being read highlighted on the page).

Pure Python on top of PyMuPDF: the text is read once per page through Page.get_textpage (which
text_guard wraps) and kept by the document view (DocumentView._reading_cache) until the page
changes."""

import html
import re
from collections import Counter

import pymupdf

COLUMN_GAP = 10.0       # points of empty paper between blocks side by side: separate columns
MIN_COLUMN = 0.12       # a column is at least this part of the text's width (not a list's bullets)


class Block:
    """A paragraph-like piece of the page's text. lines: [[(word, (x0, y0, x1, y1)), ...]];
    size: its type size (the one most of its characters have); bold: most of it bold; src:
    the MuPDF text block it comes from (one that runs across columns is cut in pieces)."""
    __slots__ = ("bbox", "lines", "size", "bold", "src")

    def __init__(self, bbox, lines, size, bold, src=None):
        self.bbox, self.lines, self.size, self.bold = bbox, lines, size, bold
        self.src = src

    def text(self):
        return join_lines([" ".join(w for w, _r in line) for line in self.lines])


def join_lines(lines):
    """Lines of a paragraph as one text: a word broken with a hyphen at a line's end is put
    back together ("read-" + "ing" -> "reading")."""
    out = ""
    for ln in lines:
        ln = ln.strip()
        if not ln:
            continue
        if out.endswith("-") and len(out) > 1 and out[-2].isalpha() and ln[:1].islower():
            out = out[:-1] + ln
        else:
            out = out + " " + ln if out else ln
    return out


def read_page(page):
    """The page's text blocks in reading order (see order_blocks). The words' rects are in
    the page's unrotated coordinates (like search hits). Text that runs sideways or upside
    down (a drawing's title block, a scan turned with the page's rotation) is put in order as
    a reader turning the page would read it."""
    flags = pymupdf.TEXTFLAGS_DICT & ~pymupdf.TEXT_PRESERVE_IMAGES
    tp = page.get_textpage(flags=flags)
    d = page.get_text("dict", textpage=tp)
    turn = _reading_frame(d)
    words = {}
    for x0, y0, x1, y1, w, b, ln, _n in page.get_text("words", textpage=tp):
        words.setdefault((b, ln), []).append((w, (x0, y0, x1, y1)))
    blocks = []
    for blk in d.get("blocks", ()):
        if blk.get("type") != 0:
            continue
        sizes, bold = Counter(), 0
        total = 0
        lines = []
        for k, line in enumerate(blk.get("lines", ())):
            for span in line.get("spans", ()):
                n = len(span.get("text", "").strip())
                sizes[round(span.get("size", 0), 1)] += n
                total += n
                if span.get("flags", 0) & 16 or "bold" in span.get("font", "").lower():
                    bold += n
            ws = words.get((blk.get("number"), k))
            if ws:
                lines.append(ws)
        if not lines or not total:
            continue
        size = sizes.most_common(1)[0][0]
        bold = bold * 2 > total
        if turn is not None:
            box = tuple((pymupdf.Rect(blk["bbox"]) * turn).normalize())
            blocks.append(Block(box, lines, size, bold, len(blocks)))
            continue
        pieces = []
        for line in lines:
            for piece in _pieces(line, size):
                box = (min(r[0] for _w, r in piece), min(r[1] for _w, r in piece),
                       max(r[2] for _w, r in piece), max(r[3] for _w, r in piece))
                pieces.append(Block(box, [piece], size, bold))
        if len(pieces) == len(lines) and not _columns(pieces):
            blocks.append(Block(tuple(blk["bbox"]), lines, size, bold, len(blocks)))
            continue
        # MuPDF put text of two columns in one block (lines at the same height): each piece
        # is read where its column is
        src = len(blocks) + 1000000
        for b in pieces:
            b.src = (src, round(b.bbox[0] / 4))
            blocks.append(b)
    return _rejoin(order_blocks(blocks))


def _reading_frame(d):
    """None when most of the text runs left to right; else the turn (a matrix) after which
    it does."""
    dirs = Counter()
    for blk in d.get("blocks", ()):
        for line in blk.get("lines", ()):
            dx, dy = line.get("dir", (1, 0))
            n = sum(len(sp.get("text", "")) for sp in line.get("spans", ()))
            dirs[(round(dx), round(dy))] += n
    if not dirs:
        return None
    main = dirs.most_common(1)[0][0]
    # (x, y) -> (x', y') so that the text runs along x' and the lines follow along y'
    return {(0, 1): pymupdf.Matrix(0, -1, 1, 0, 0, 0),      # top to bottom: x' = y, y' = -x
            (0, -1): pymupdf.Matrix(0, 1, -1, 0, 0, 0),     # bottom to top: x' = -y, y' = x
            (-1, 0): pymupdf.Matrix(-1, 0, 0, -1, 0, 0)}.get(main)


def _pieces(line, size):
    """A line's words, cut where the gap between two words is much wider than a space."""
    gap = max(COLUMN_GAP, 1.6 * size)
    out = [[line[0]]]
    for w in line[1:]:
        if w[1][0] - out[-1][-1][1][2] > gap:
            out.append([w])
        else:
            out[-1].append(w)
    return out


def _rejoin(blocks):
    """Pieces of one cut block that are read one after the other (the lines of one column)
    become one block again."""
    out = []
    for b in blocks:
        if out and b.src == out[-1].src and isinstance(b.src, tuple):
            last = out[-1]
            box = (min(last.bbox[0], b.bbox[0]), min(last.bbox[1], b.bbox[1]),
                   max(last.bbox[2], b.bbox[2]), max(last.bbox[3], b.bbox[3]))
            out[-1] = Block(box, last.lines + b.lines, last.size, last.bold, last.src)
        else:
            out.append(b)
    return out


# ---- reading order: a recursive XY cut ---------------------------------------------------
def _groups(items, axis, gap):
    """items split where gap or more of empty space runs across them along axis (0: side by
    side, 1: one above the other), in order. [(start, end, [items])]."""
    lo, hi = (0, 2) if axis == 0 else (1, 3)
    out = []
    for b in sorted(items, key=lambda b: b.bbox[lo]):
        if out and b.bbox[lo] < out[-1][1] + gap:
            g = out[-1]
            g[1] = max(g[1], b.bbox[hi])
            g[2].append(b)
        else:
            out.append([b.bbox[lo], b.bbox[hi], [b]])
    return out


def _columns(items):
    """items split into columns (left to right) when there are real columns, else None."""
    cols = _groups(items, 0, COLUMN_GAP)
    if len(cols) < 2:
        return None
    width = max(c[1] for c in cols) - min(c[0] for c in cols)
    if any(c[1] - c[0] < MIN_COLUMN * width for c in cols):
        return None
    return cols


def _gutters(cols):
    return [(a[1], b[0]) for a, b in zip(cols, cols[1:])]


def _overlap(g1, g2):
    return any(a0 < b1 and b0 < a1 for a0, a1 in g1 for b0, b1 in g2)


def _crosses(items, gutters):
    return any(b.bbox[0] < g1 and b.bbox[2] > g0 for b in items for g0, g1 in gutters)


def _bands(items):
    """items in bands one above the other ([items, gutters]), where the empty paper runs
    right across. Neighboring bands whose columns line up (both columns of a page happen to
    have a gap at the same height) are one band again, read column by column, and so is a
    piece of one column between two of them (beside a picture in the other column)."""
    out = []
    for r in _groups(items, 1, 0.5):
        g = _gutters(_columns(r[2]) or [])
        if out and g and out[-1][1] and _overlap(g, out[-1][1]):
            out[-1][0].extend(r[2])
            out[-1][1] = g
        else:
            out.append([list(r[2]), g])
    i = 1
    while i < len(out) - 1:
        a, m, c = out[i - 1], out[i], out[i + 1]
        if not m[1] and a[1] and c[1] and _overlap(a[1], c[1]) and not _crosses(m[0], a[1]):
            a[0].extend(m[0] + c[0])
            a[1] = c[1]
            del out[i:i + 2]
        else:
            i += 1
    return out


def _cut(items):
    if len(items) <= 1:
        return list(items)
    bands = _bands(items)
    if len(bands) > 1:
        return [b for band in bands for b in _cut(band[0])]
    cols = _columns(items)
    if cols:
        return [b for c in cols for b in _cut(c[2])]
    return sorted(items, key=lambda b: (b.bbox[1], b.bbox[0]))


def order_blocks(blocks):
    """Blocks in reading order: a heading across the page, then the left column top to
    bottom, then the right one, then what spans the page under them, and so on."""
    return _cut(blocks)


# ---- the Reading view: the page's text as simple HTML ------------------------------------
def body_size(blocks):
    """The page's usual type size: the size most of its characters have."""
    c = Counter()
    for b in blocks:
        c[b.size] += sum(len(w) for line in b.lines for w, _r in line)
    return c.most_common(1)[0][0] if c else 10.0


def heading_level(block, body):
    """1-3 for a heading (bigger than the text around it, or a short bold line), else 0."""
    chars = sum(len(w) for line in block.lines for w, _r in line)
    if chars > 300:
        return 0
    ratio = block.size / max(body, 1)
    if ratio >= 1.7:
        return 1
    if ratio >= 1.35:
        return 2
    if ratio >= 1.12 or block.bold and len(block.lines) <= 2 and chars < 120:
        return 3
    return 0


SCALE = {1: 1.9, 2: 1.5, 3: 1.2}


def page_html(blocks, size_pt, fg=None, title=None):
    """The blocks as HTML paragraphs at size_pt points, headings larger (by how much larger
    they are on the page)."""
    body = body_size(blocks)
    parts = []
    if title:
        parts.append('<p style="font-size:%gpt; color:gray;">%s</p>' % (
            round(size_pt * 0.8, 1), html.escape(title)))
    for b in blocks:
        text = html.escape(b.text())
        if not text:
            continue
        level = heading_level(b, body)
        if level:
            parts.append('<h%d style="font-size:%gpt; margin-top:%dpx;">%s</h%d>' % (
                level, round(size_pt * SCALE[level], 1), int(size_pt * 0.8), text, level))
        else:
            parts.append('<p style="font-size:%gpt; line-height:150%%; margin-bottom:%dpx;">'
                         '%s</p>' % (size_pt, int(size_pt * 0.7), text))
    color = ' style="color:%s;"' % fg if fg else ""
    return "<html><body%s>%s</body></html>" % (color, "\n".join(parts))


# ---- Read aloud: sentences with the place of each word ---------------------------------
_END = re.compile(r'[.!?…]["”’)\]]*$')
_ABBREV = {"mr.", "mrs.", "ms.", "dr.", "st.", "no.", "vs.", "e.g.", "i.e.", "etc.", "fig.",
           "p.", "pp.", "sr.", "jr.", "sra.", "dra.", "núm.", "pág.", "ej."}
MAX_SENTENCE = 400      # characters: a longer run (a list, a table) is spoken in pieces


class Sentence:
    """text: what is spoken; words: [(start, end, [rects])] where each word is in text and
    on the page; page: the page index."""
    __slots__ = ("page", "text", "words")

    def __init__(self, page, text, words):
        self.page, self.text, self.words = page, text, words

    def word_at(self, pos):
        """The word at character pos of text (or the last one before it)."""
        best = None
        for w in self.words:
            if w[0] <= pos:
                best = w
            else:
                break
        return best

    def rects(self):
        return [r for w in self.words for r in w[2]]


def _tokens(block):
    """(word, [rects]) of a block, in order, a word broken at a line's end joined again."""
    out = []
    for line in block.lines:
        for k, (w, r) in enumerate(line):
            if k == 0 and out and out[-1][0].endswith("-") and len(out[-1][0]) > 1 and \
                    out[-1][0][-2].isalpha() and w[:1].islower():
                prev = out[-1]
                out[-1] = (prev[0][:-1] + w, prev[1] + [r])
            else:
                out.append((w, [r]))
    return out


def sentences(blocks, page_index, start=None):
    """The blocks' text cut into sentences (each block ends one: headings are read on their
    own). start: a point (x, y) on the page; sentences start at the word nearest to it."""
    toks = []          # (word, rects, block number)
    for bi, b in enumerate(blocks):
        for w, rects in _tokens(b):
            toks.append((w, rects, bi))
    if start is not None and toks:
        sx, sy = start

        def dist(t):
            x0, y0, x1, y1 = t[1][0]
            return (max(x0 - sx, 0, sx - x1) + 2 * max(y0 - sy, 0, sy - y1), y0, x0)
        first = min(range(len(toks)), key=lambda k: dist(toks[k]))
        toks = toks[first:]
    out = []
    text, words = "", []

    def flush():
        nonlocal text, words
        if words:
            out.append(Sentence(page_index, text, words))
        text, words = "", []
    for k, (w, rects, bi) in enumerate(toks):
        if words:
            text += " "
        words.append((len(text), len(text) + len(w), rects))
        text += w
        last = k + 1 == len(toks) or toks[k + 1][2] != bi
        if last or (_END.search(w) and w.lower() not in _ABBREV and
                    (toks[k + 1][0][:1].isupper() or not toks[k + 1][0][:1].isalpha())) or \
                len(text) > MAX_SENTENCE and w[-1:] in ",;:":
            flush()
        elif len(text) > MAX_SENTENCE * 1.5:
            flush()
    flush()
    return out
