"""Forms > Detect form fields...: find where fields belong on a flat form (a PDF with no
fields, a scanned one after OCR) so they can be made with a click.

What counts, read from the page's vector drawings (get_drawings) and its text (through
Page.get_textpage, as AGENTS.md asks, so text_guard protects the read):
- a blank line after a label ("Name: ______", drawn or typed as underscores), or with its
  label under it (a signature line with "Signature" below);
- an empty box or table cell next to a label, under a column heading, or with a small label
  inside it at the top or left;
- a small empty square (or a box character) with a label beside it: a checkbox;
- "Signature" / "Initials" labels make signature and initials fields, "Date" a date field.
On a scanned page (one big picture, the text from OCR), the lines and boxes are found in the
picture itself.

It's careful rather than eager: a line or box with no label near it, text that is merely
underlined, the rules between paragraphs and the page's frame are left alone. Nothing is
changed here: detect() returns what it found, and the person picks what to make.
"""

import re

import pymupdf

TOL = 1.6               # points: lines this close are the same line
MIN_LINE = 30           # a blank line is at least this long
MAX_SEGMENTS = 3000     # more line pieces than this: a drawing, not a form

SIGNATURE = re.compile(r"\b(signature|sign here|signed|firma)\b", re.I)
INITIALS = re.compile(r"\b(initials?|iniciales)\b", re.I)
DATE = re.compile(r"\b(date|fecha)\b", re.I)
BOX_CHARS = set("☐□❏❑▢⬜")


class Token:
    """A word (split at underscores) with its line."""
    __slots__ = ("text", "rect", "line", "size", "under")

    def __init__(self, text, rect, line, size, under):
        self.text, self.rect, self.line, self.size, self.under = text, rect, line, size, under


def _tokens(page):
    """(words, underscore runs, box characters) of a page, from one text read."""
    tp = page.get_textpage(flags=pymupdf.TEXTFLAGS_RAWDICT & ~pymupdf.TEXT_PRESERVE_IMAGES)
    raw = page.get_text("rawdict", textpage=tp)
    words, unders, boxes = [], [], []
    for bi, b in enumerate(raw.get("blocks", [])):
        for li, ln in enumerate(b.get("lines", [])):
            if abs(ln.get("dir", (1, 0))[1]) > 0.05:
                continue            # (sideways text: not a label of a field across)
            line = (bi, li)
            for sp in ln.get("spans", []):
                size = sp.get("size", 10)
                cur, kind = [], None

                def flush():
                    if not cur:
                        return
                    text = "".join(c["c"] for c in cur)
                    r = pymupdf.Rect(cur[0]["bbox"])
                    for c in cur[1:]:
                        r |= pymupdf.Rect(c["bbox"])
                    if kind == "_":
                        if len(text) >= 3:
                            base = cur[0]["origin"][1]
                            unders.append((r.x0, r.x1, base + 0.12 * size, line, size))
                    else:
                        words.append(Token(text, r, line, size, False))
                for c in sp.get("chars", []):
                    ch = c["c"]
                    if ch in BOX_CHARS:
                        flush()
                        cur, kind = [], None
                        boxes.append((pymupdf.Rect(c["bbox"]), line, size))
                        continue
                    k = "_" if ch == "_" else (" " if ch.isspace() else "w")
                    if k != kind:
                        flush()
                        cur, kind = [], k
                    if k != " ":
                        cur.append(c)
                    else:
                        cur = []
                flush()
    return words, unders, boxes


# ---- lines and boxes -----------------------------------------------------------------------
def _segments(page):
    """Horizontal and vertical line pieces [(y, x0, x1)], [(x, y0, y1)] and small filled or
    stroked squares, from the page's vector drawings."""
    hs, vs = [], []
    for path in page.get_drawings():
        stroke, fill = path.get("color"), path.get("fill")
        if stroke is None and fill is None:
            continue
        if stroke is None and fill is not None and min(fill) > 0.93:
            continue                    # (a white box: invisible)
        w = path.get("width") or 0
        if stroke is not None and w > 3:
            continue
        for item in path["items"]:
            op = item[0]
            if op == "l":
                a, b = item[1], item[2]
                if abs(a.y - b.y) < 0.8 and abs(a.x - b.x) >= 3:
                    hs.append(((a.y + b.y) / 2, min(a.x, b.x), max(a.x, b.x)))
                elif abs(a.x - b.x) < 0.8 and abs(a.y - b.y) >= 3:
                    vs.append(((a.x + b.x) / 2, min(a.y, b.y), max(a.y, b.y)))
            elif op in ("re", "qu"):
                r = item[1] if op == "re" else item[1].rect
                if op == "qu" and not item[1].is_rectangular:
                    continue
                r = pymupdf.Rect(r).normalize()
                if r.height <= 2.5 and r.width >= 3:
                    hs.append(((r.y0 + r.y1) / 2, r.x0, r.x1))
                elif r.width <= 2.5 and r.height >= 3:
                    vs.append(((r.x0 + r.x1) / 2, r.y0, r.y1))
                elif stroke is not None:
                    hs += [(r.y0, r.x0, r.x1), (r.y1, r.x0, r.x1)]
                    vs += [(r.x0, r.y0, r.y1), (r.x1, r.y0, r.y1)]
    return hs, vs


def _scanned(page):
    """True for a page that is a picture (a scan): one image covering most of it."""
    area = abs(page.rect)
    try:
        for info in page.get_image_info():
            r = pymupdf.Rect(info["bbox"]) & page.rect
            if not r.is_empty and abs(r) >= 0.5 * area:
                return True
    except Exception:
        pass
    return False


def _raster_segments(page, dpi=100):
    """Horizontal and vertical lines found in a scanned page's picture (long, thin runs of
    dark pixels), in page coordinates."""
    import numpy as np
    pix = page.get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY, annots=False)
    a = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.stride)[:, :pix.width]
    dark = a < 140
    scale = dpi / 72.0
    to_page = page.derotation_matrix if page.rotation else None
    min_px = int(MIN_LINE * scale)

    def runs(mask):
        pad = np.zeros((mask.shape[0], mask.shape[1] + 2), dtype=np.int8)
        pad[:, 1:-1] = mask
        d = np.diff(pad, axis=1)
        rs, cs = np.nonzero(d == 1)
        re_, ce = np.nonzero(d == -1)
        keep = (ce - cs) >= min_px
        return rs[keep], cs[keep], ce[keep]

    def merge(rows, starts, ends):
        segs = []           # [first row, last row, x0, x1]
        active = {}
        for r, s, e in sorted(zip(rows.tolist(), starts.tolist(), ends.tolist())):
            hit = None
            for key, seg in list(active.items()):
                if seg[1] < r - 1:
                    del active[key]
                    continue
                if seg[1] == r - 1 and min(seg[3], e) - max(seg[2], s) >= 0.8 * min(
                        seg[3] - seg[2], e - s):
                    hit = seg
                    break
            if hit is not None:
                hit[1], hit[2], hit[3] = r, min(hit[2], s), max(hit[3], e)
            else:
                seg = [r, r, s, e]
                segs.append(seg)
                active[id(seg)] = seg
        return [s for s in segs if s[1] - s[0] + 1 <= 5]       # thin: a line, not a bar

    hs, vs = [], []
    for r0, r1, s, e in merge(*runs(dark)):
        y = (r0 + r1 + 1) / 2 / scale
        hs.append((y, s / scale, e / scale))
    for c0, c1, s, e in merge(*runs(dark.T)):
        x = (c0 + c1 + 1) / 2 / scale
        vs.append((x, s / scale, e / scale))
    if to_page is not None:
        def h2p(y, x0, x1):
            a, b = pymupdf.Point(x0, y) * to_page, pymupdf.Point(x1, y) * to_page
            return a, b
        out_h, out_v = [], []
        for seg, horizontal in [(s, True) for s in hs] + [(s, False) for s in vs]:
            c, p0, p1 = seg
            a = (pymupdf.Point(p0, c) if horizontal else pymupdf.Point(c, p0)) * to_page
            b = (pymupdf.Point(p1, c) if horizontal else pymupdf.Point(c, p1)) * to_page
            if abs(a.y - b.y) < 0.8:
                out_h.append(((a.y + b.y) / 2, min(a.x, b.x), max(a.x, b.x)))
            else:
                out_v.append(((a.x + b.x) / 2, min(a.y, b.y), max(a.y, b.y)))
        return out_h, out_v
    return hs, vs


def _merge(segs):
    """Collinear pieces joined: {position: [(start, end)]} with nearby positions as one."""
    out = []                    # [pos, [(a, b)]]
    for pos, a, b in sorted(segs):
        if out and pos - out[-1][0] <= TOL:
            out[-1][1].append((a, b))
        else:
            out.append([pos, [(a, b)]])
    lines = {}
    for pos, spans in out:
        spans.sort()
        joined = []
        for a, b in spans:
            if joined and a <= joined[-1][1] + 2.0:
                joined[-1][1] = max(joined[-1][1], b)
            else:
                joined.append([a, b])
        lines[pos] = [tuple(s) for s in joined]
    return lines


def _covers(lines, pos, a, b):
    for p, spans in lines.items():
        if abs(p - pos) <= TOL:
            for s0, s1 in spans:
                if s0 <= a + TOL and s1 >= b - TOL:
                    return True
    return False


def _cells(H, V):
    """The boxes the lines close: each found from its top-left corner as the smallest box
    with all four sides drawn."""
    ys, xs = sorted(H), sorted(V)
    cells = []
    for ya in ys:
        for xa in xs:
            if not _covers(V, xa, ya, ya + 3) or not _covers(H, ya, xa, xa + 3):
                continue
            found = None
            for yb in ys:
                if yb <= ya + 5:
                    continue
                if not _covers(V, xa, ya, yb):
                    break
                if not _covers(H, yb, xa, xa + 3):
                    continue
                for xb in xs:
                    if xb <= xa + 5:
                        continue
                    if not (_covers(H, ya, xa, xb) and _covers(H, yb, xa, xb)):
                        break
                    if _covers(V, xb, ya, yb):
                        found = pymupdf.Rect(xa, ya, xb, yb)
                        break
                if found:
                    break
            if found is not None:
                cells.append(found)
    return cells


# ---- labels -----------------------------------------------------------------------------------
def clean_label(text):
    t = re.sub(r"[_….]{2,}", " ", text)
    t = re.sub(r"^\s*(\(?[0-9]{1,2}[.)]|\(?[a-zA-Z][.)]|[•\-*])\s+", "", t)
    t = t.replace(".", "").replace("*", "").strip(" :;,-–—\t")
    t = re.sub(r"\s+", " ", t)
    if len(t) > 40:
        t = t[:40].rsplit(" ", 1)[0]
    return t


def _line_words(words, line):
    return [w for w in words if w.line == line]


def _left_label(words, x0, y, stop=None, height=14):
    """The words just left of x0 on the text line sitting at y (the label of a blank or
    a box starting there)."""
    near = [w for w in words if w.rect.x1 <= x0 + 3 and x0 - w.rect.x1 <= 60 and
            y - height - 4 <= w.rect.y1 <= y + 4 and w.rect.y0 < y and
            (stop is None or w.rect.x0 >= stop)]
    if not near:
        return None, None
    last = max(near, key=lambda w: w.rect.x1)
    group = [last]
    for w in sorted([w for w in words if w.line == last.line and w.rect.x1 <= last.rect.x0 + 1
                     and (stop is None or w.rect.x0 >= stop)],
                    key=lambda w: -w.rect.x1):
        if group[-1].rect.x0 - w.rect.x1 > 12:
            break
        group.append(w)
    group.reverse()
    text = " ".join(w.text for w in group)
    r = pymupdf.Rect(group[0].rect)
    for w in group[1:]:
        r |= w.rect
    return text, r


def _below_label(words, x0, x1, y):
    """A short label on the line right under a blank line (a signature line's caption)."""
    under = [w for w in words if y + 0.5 <= w.rect.y0 <= y + 14 and
             w.rect.x1 > x0 - 2 and w.rect.x0 < x1 + 2]
    if not under:
        return None
    line = min(under, key=lambda w: w.rect.y0).line
    whole = _line_words(words, line)
    if len(whole) > 5:
        return None
    lx0 = min(w.rect.x0 for w in whole)
    lx1 = max(w.rect.x1 for w in whole)
    if lx0 < x0 - 20 or lx1 > x1 + 20 or lx1 - lx0 > 0.75 * (x1 - x0) + 10:
        return None
    return " ".join(w.text for w in sorted(whole, key=lambda w: w.rect.x0))


def _kind(label, default="text"):
    if SIGNATURE.search(label):
        return "signature"
    if INITIALS.search(label):
        return "initials"
    if DATE.search(label):
        return "date"
    return default


def _words_in(words, r):
    return [w for w in words if r.contains(pymupdf.Point((w.rect.x0 + w.rect.x1) / 2,
                                                         (w.rect.y0 + w.rect.y1) / 2))]


# ---- the page -------------------------------------------------------------------------------
def detect(page, existing=()):
    """[{"kind", "rect", "name", "label"}] of the fields a flat form page seems to want:
    kind is text, multiline, date, check, signature or initials. existing: rects of fields
    already there (nothing is found on them)."""
    words, unders, boxchars = _tokens(page)
    hs, vs = _segments(page)
    if _scanned(page) and len(hs) + len(vs) < 8:
        rh, rv = _raster_segments(page)
        hs, vs = hs + rh, vs + rv
    if len(hs) + len(vs) > MAX_SEGMENTS:
        hs, vs = [], []
    page_w = page.mediabox.width
    H, V = _merge(hs), _merge(vs)
    found = []
    taken = [pymupdf.Rect(r) for r in existing]

    def add(kind, rect, label, prio):
        rect = pymupdf.Rect(rect)
        if rect.is_empty or rect.width < 5 or rect.height < 5:
            return
        name = clean_label(label or "")
        if not name:
            return
        for t in taken:
            inter = rect & t
            if not inter.is_empty and abs(inter) > 0.3 * min(abs(rect), abs(t)):
                return
        taken.append(rect)
        found.append({"kind": kind, "rect": rect, "name": name, "label": label, "prio": prio})

    # 1. boxes and table cells
    cells = _cells(H, V) if len(hs) + len(vs) else []
    cells = [c for c in cells if abs(c) < 0.25 * abs(page.mediabox)]
    edge_h = set()                      # (y, x0, x1) of cell sides: not blank lines
    for c in cells:
        edge_h.add((round(c.y0), round(c.x0), round(c.x1)))
        edge_h.add((round(c.y1), round(c.x0), round(c.x1)))
    text_cells = {i: _words_in(words, c) for i, c in enumerate(cells)}

    def same_row(a, b):
        return abs(a.y0 - b.y0) <= 2 * TOL and abs(a.y1 - b.y1) <= 2 * TOL

    def same_col(a, b):
        return abs(a.x0 - b.x0) <= 2 * TOL and abs(a.x1 - b.x1) <= 2 * TOL

    for i, c in enumerate(cells):
        inside = text_cells[i]
        w, h = c.width, c.height
        if not inside and w <= 20 and h <= 20 and abs(w - h) <= 2.5 and min(w, h) >= 6:
            text, _r = _right_label(words, c)
            if not text:
                text, _r = _left_label(words, c.x0, c.y1)
            if not text:
                text = _header(cells, text_cells, i, same_col)
            if text:
                add("check", c, text, 0)
            continue
        if w < 30 or h < 10:
            continue
        if not inside:
            row = _row_label(cells, text_cells, i, same_row)
            head = _header(cells, text_cells, i, same_col)
            if row and head:
                label = row + " " + head
            else:
                label = row or head
            if not label:
                label, _r = _left_label(words, c.x0, c.y1 - 2, height=max(14, h))
            if not label:
                above = [x for x in words if c.y0 - 13 <= x.rect.y1 <= c.y0 + 1 and
                         x.rect.x0 >= c.x0 - 2 and x.rect.x1 <= c.x1 + 2]
                if above and len({x.line for x in above}) == 1 and len(above) <= 5:
                    label = " ".join(x.text for x in sorted(above, key=lambda x: x.rect.x0))
            if label:
                kind = _kind(label, "multiline" if h > 60 and w >= 100 else "text")
                add(kind, c + (1.5, 1.5, -1.5, -1.5), label, 1)
            continue
        # a label inside the box: at its top (space below to write) or at its left
        if len({x.line for x in inside}) > 2 or any(x.under for x in inside):
            continue
        tb = max(x.rect.y1 for x in inside)
        tr_ = max(x.rect.x1 for x in inside)
        label = " ".join(x.text for x in sorted(inside, key=lambda x: (x.rect.y0, x.rect.x0)))
        if c.y1 - tb >= 11 and tb <= c.y0 + 0.6 * h:
            r = pymupdf.Rect(c.x0 + 1.5, tb + 1, c.x1 - 1.5, c.y1 - 1.5)
            add(_kind(label, "multiline" if r.height > 60 and w >= 100 else "text"), r, label, 1)
        elif c.x1 - tr_ >= 60 and len({x.line for x in inside}) == 1:
            r = pymupdf.Rect(tr_ + 3, c.y0 + 1.5, c.x1 - 1.5, c.y1 - 1.5)
            add(_kind(label), r, label, 1)

    # 2. box characters (☐ Yes)
    for r, line, size in boxchars:
        side = min(max(r.width, r.height * 0.75), size, 14)
        cx, cy = (r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2
        box = pymupdf.Rect(cx - side / 2, cy - side / 2, cx + side / 2, cy + side / 2)
        text, _ = _right_label(words, box)
        if not text:
            text, _ = _left_label(words, box.x0, box.y1)
        if text:
            add("check", box, text, 0)

    # 3. blank lines: drawn, or typed as underscores
    blanks = []
    for y, spans in H.items():
        for x0, x1 in spans:
            if x1 - x0 < MIN_LINE or (round(y), round(x0), round(x1)) in edge_h:
                continue
            if any(abs(round(y) - ey) <= 2 and x0 >= ex0 - 2 and x1 <= ex1 + 2
                   for ey, ex0, ex1 in edge_h):
                continue
            # a table's line: a vertical line meets it at an end
            if any(abs(vx - x0) <= TOL or abs(vx - x1) <= TOL
                   for vx, sp in V.items() for a, b in sp if a - TOL <= y <= b + TOL):
                continue
            blanks.append((y, x0, x1, None, None))
    for x0, x1, y, line, size in unders:
        blanks.append((y, x0, x1, line, size))
    blanks.sort(key=lambda b: (round(b[0]), b[1]))
    for k, (y, x0, x1, line, size) in enumerate(blanks):
        if x1 - x0 > 0.92 * page_w:
            continue                    # (a rule across the whole page)
        sitting = [w for w in words if y - 4 <= w.rect.y1 <= y + 1.5 and
                   w.rect.x1 > x0 + 1 and w.rect.x0 < x1 - 1]
        if sum(min(w.rect.x1, x1) - max(w.rect.x0, x0) for w in sitting) > 0.2 * (x1 - x0):
            continue                    # underlined text, not a blank to write on
        # (another blank to the left on the same row: the label starts after it)
        stop = max([b[2] for b in blanks[:k] if abs(b[0] - y) <= 3 and b[2] <= x0 + 1] or
                   [None], key=lambda v: -1 if v is None else v)
        label, lr = _left_label(words, x0, y, stop=stop)
        if not label:
            label = _below_label(words, x0, x1, y)
            lh = 11
        else:
            lh = lr.height
        if not label:
            continue
        kind = _kind(label)
        want = 30 if kind in ("signature", "initials") else min(22, max(13, lh * 1.25))
        above = [w.rect.y1 for w in words if w.rect.y1 < y - 3 and w.rect.x1 > x0 and
                 w.rect.x0 < x1 and w.rect.y1 > y - want - 2 and not (lr and w.rect in lr)]
        room = y - 1 - (max(above) + 1 if above else y - 1 - want)
        h = min(want, room)
        if h < 9:
            continue
        add(kind, pymupdf.Rect(x0, y - 1 - h, x1, y - 1), label, 2)

    found.sort(key=lambda f: (round(f["rect"].y0 / 3), f["rect"].x0))
    for f in found:
        f.pop("prio", None)
        if f["kind"] == "date":
            f["pattern"] = "mm/dd/yyyy"
    return found


def _right_label(words, r):
    """The words just right of a small box on its line (a checkbox's label)."""
    near = [w for w in words if 0 <= w.rect.x0 - r.x1 <= 25 and
            w.rect.y0 < r.y1 + 2 and w.rect.y1 > r.y0 - 2]
    if not near:
        return None, None
    first = min(near, key=lambda w: w.rect.x0)
    group = [first]
    for w in sorted([w for w in words if w.line == first.line and w.rect.x0 >= first.rect.x1 - 1],
                    key=lambda w: w.rect.x0):
        if w.rect.x0 - group[-1].rect.x1 > 12 or len(group) >= 6:
            break
        group.append(w)
    return " ".join(w.text for w in group), None


def _row_label(cells, text_cells, i, same_row):
    """The text of the nearest cell left of cell i in its row (with only empty cells
    between)."""
    c = cells[i]
    left = sorted([k for k, d in enumerate(cells) if k != i and same_row(d, c) and
                   d.x1 <= c.x0 + TOL], key=lambda k: -cells[k].x1)
    for k in left:
        if text_cells[k]:
            return " ".join(w.text for w in sorted(text_cells[k], key=lambda w: (w.rect.y0,
                                                                                 w.rect.x0)))
        if cells[k].width <= 20:
            continue                     # (a checkbox cell between)
    return None


def _header(cells, text_cells, i, same_col):
    """The text of the nearest cell above cell i in its column (a column heading), and the
    row number when the rows under it are blank ("Qty 2")."""
    c = cells[i]
    up = sorted([k for k, d in enumerate(cells) if k != i and same_col(d, c) and
                 d.y1 <= c.y0 + TOL], key=lambda k: -cells[k].y1)
    blank = 0
    for k in up:
        if text_cells[k]:
            head = " ".join(w.text for w in sorted(text_cells[k], key=lambda w: (w.rect.y0,
                                                                                 w.rect.x0)))
            return head if blank == 0 and not _has_rows_below(cells, text_cells, k, i,
                                                              same_col) else \
                "%s %d" % (head, blank + 1)
        blank += 1
    return None


def _has_rows_below(cells, text_cells, head, i, same_col):
    """More than one blank cell under a heading: they're numbered (Qty 1, Qty 2, ...)."""
    c = cells[head]
    return sum(1 for k, d in enumerate(cells) if same_col(d, c) and d.y0 >= c.y1 - TOL and
               not text_cells[k]) > 1
