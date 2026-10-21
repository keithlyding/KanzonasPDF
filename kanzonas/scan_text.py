"""Editing text on a scanned page so the result looks like the scan.

A scanned page is a picture of the paper with an invisible text layer laid over it by OCR (the
scanner's or KanzonasPDF's own). Editing that text layer alone leaves the old words showing in
the picture, so the new text would be printed over them. Instead, for a line on a scanned page:

1. find the old line's letters in the picture (its extent, the paper color around it and the
   ink color of its letters), without taking ruled lines of a form or a neighboring line;
2. find the font that reproduces them: the old words are drawn in each candidate font (the
   standard PDF fonts and common installed ones, regular and bold) at the size that gives the
   same width, and compared with the scanned letters; the closest shape wins, with its size
   and baseline;
3. replace_line() then covers the old letters with the paper color and writes the new text in
   that font, size and color on that baseline. It stays real text: search and Edit text keep
   working.

The scanned typeface can't be named from a picture, so the result is the closest of the fonts
available, not necessarily the original one.
"""

import numpy as np
import pymupdf

ZOOM = 4                 # analysis resolution: 288 dpi, about what scanners use
REF_SIZE = 40.0          # candidate fonts are drawn at this size, then scaled
MIN_CHARS = 3            # fewer letters than this can't tell fonts apart
INK_STEP = 60            # gray levels below the paper that count as a letter (for the color)
MARK_STEP = 25           # ... as something printed, faint letter edges included (extent)
FAINT_STEP = 12          # ... as a faint ruled line of a form
GAMMA = 2.2              # scanners store gray gamma-encoded
SURE = 0.65              # below this match score the old words (OCR text) don't fit the letters

# Candidate fonts: (key, label, kind, bold, italic, how to get it). Built-in PDF fonts always
# exist; the installed ones are used when present (normalized names as in text_edit._norm).
BUILTIN = [("helv", "Helvetica", "sans", False, False), ("hebo", "Helvetica", "sans", True, False),
           ("heit", "Helvetica", "sans", False, True),
           ("tiro", "Times", "serif", False, False), ("tibo", "Times", "serif", True, False),
           ("tiit", "Times", "serif", False, True),
           ("cour", "Courier", "mono", False, False), ("cobo", "Courier", "mono", True, False)]
INSTALLED = [("Arial", "sans"), ("Calibri", "sans"), ("Segoe UI", "sans"), ("Verdana", "sans"),
             ("Tahoma", "sans"), ("Century Gothic", "sans"), ("Trebuchet MS", "sans"),
             ("Aptos", "sans"), ("Arial Narrow", "sans"), ("Franklin Gothic Book", "sans"),
             ("Times New Roman", "serif"), ("Cambria", "serif"), ("Georgia", "serif"),
             ("Garamond", "serif"), ("Book Antiqua", "serif"), ("Courier New", "mono"),
             ("Consolas", "mono")]


# ---- is this a scanned line? ------------------------------------------------------------------

def _invisible(span):
    """True for OCR text: drawn invisibly (text render mode 3)."""
    return span.get("alpha", 255) == 0


def scanned_page(page):
    """True when a picture covers most of the page and most of its text is invisible (an OCR
    layer): a scanned page. Born-digital pages with a background picture don't count."""
    try:
        area = page.rect.width * page.rect.height
        if not any(pymupdf.Rect(i["bbox"]).get_area() >= 0.5 * area
                   for i in page.get_image_info()):
            return False
        seen = hidden = 0
        flags = pymupdf.TEXTFLAGS_DICT & ~pymupdf.TEXT_PRESERVE_IMAGES
        for b in page.get_text("dict", flags=flags)["blocks"]:
            for ln in b.get("lines", []):
                for s in ln["spans"]:
                    n = len(s["text"].strip())
                    seen += n
                    hidden += n if _invisible(s) else 0
        return seen > 0 and hidden * 2 >= seen
    except Exception:
        return False


# ---- the old line in the picture --------------------------------------------------------------

def _picture_only(page):
    """A one-page copy of the page without its text and rotation: what the scan shows."""
    tmp = pymupdf.open()
    tmp.insert_pdf(page.parent, from_page=page.number, to_page=page.number, annots=False)
    tp = tmp[0]
    tp.set_rotation(0)
    tp.add_redact_annot(tp.rect, fill=False)
    tp.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE,
                        graphics=pymupdf.PDF_REDACT_LINE_ART_NONE,
                        text=pymupdf.PDF_REDACT_TEXT_REMOVE)
    return tmp


def _upright(line):
    """A rotation matrix that turns the line's direction into left-to-right."""
    d = pymupdf.Point(line["dir"])
    for deg in (0, 90, 180, 270):
        m = pymupdf.Matrix(deg)
        v = d * m
        if v.x > 0.9:
            return m
    return pymupdf.Matrix(0)


class _View:
    """The picture around a line, turned so the text runs left to right, as gray / RGB arrays,
    with the mapping back to page coordinates."""

    def __init__(self, page, clip, turn):
        m = turn * pymupdf.Matrix(ZOOM, ZOOM)
        pm = page.get_pixmap(matrix=m, clip=clip, alpha=False, annots=False,
                             colorspace=pymupdf.csRGB)
        a = np.frombuffer(pm.samples, np.uint8).reshape(pm.height, pm.stride)
        self.rgb = a[:, :pm.width * 3].reshape(pm.height, pm.width, 3).astype(np.int16)
        self.gray = self.rgb.mean(axis=2)
        self._shift = pymupdf.Point(pm.x, pm.y)          # the pixmap's place in matrix space
        self._back = ~m
        self._to = m

    def to_page(self, x, y):
        return (pymupdf.Point(x, y) + self._shift) * self._back

    def rect_to_page(self, x0, y0, x1, y1):
        a, b = self.to_page(x0, y0), self.to_page(x1, y1)
        return pymupdf.Rect(min(a.x, b.x), min(a.y, b.y), max(a.x, b.x), max(a.y, b.y))

    def to_px(self, pt):
        return pymupdf.Point(pt) * self._to - self._shift


def _longest_run(row):
    best = cur = 0
    for v in row:
        cur = cur + 1 if v else 0
        if cur > best:
            best = cur
    return best


def _find_ink(view, box_px, base_y):
    """The old line's letters in the picture: (x0, y0, x1, y1) pixel box of them, the cover
    boxes (the same, minus rows a ruled line runs through), paper and ink colors (0-1 RGB),
    and the binary letter mask inside the box. None when nothing is printed there.
    base_y: the text layer's baseline (pixels), to tell the line from its neighbors."""
    gray = view.gray
    hgt, wid = gray.shape
    paper = float(np.percentile(gray, 90))
    mark = gray < paper - MARK_STEP
    faint = gray < paper - FAINT_STEP
    x0 = max(0, int(box_px.x0))
    x1 = min(wid, int(np.ceil(box_px.x1)))
    y0 = max(0, int(box_px.y0))
    y1 = min(hgt, int(np.ceil(box_px.y1)))
    if x1 - x0 < 2 or y1 - y0 < 2 or not mark[y0:y1, x0:x1].any():
        return None

    def is_rule(y, a, b):                   # one unbroken faint run across most of the line
        return _longest_run(faint[y, a:b]) > 0.6 * (b - a)

    # The line's body (its lowercase letters, or capitals): the band of rows dense with ink
    # whose bottom is nearest the text layer's baseline. OCR boxes often reach into the
    # lines above and below, and tightly set lines have no blank row between them.
    counts = np.array([0 if is_rule(y, x0, x1) else int(mark[y, x0:x1].sum())
                       for y in range(y0, y1)])
    if not counts.any():
        return None
    # 1) the cluster of inked rows around the baseline: lines are parted by nearly empty rows
    inked = counts > 0.03 * counts.max()
    clusters, start = [], None
    for i, v in enumerate(list(inked) + [False]):
        if v and start is None:
            start = i
        elif not v and start is not None:
            clusters.append((start, i))
            start = None
    b = base_y - y0

    def dist(c):
        return 0 if c[0] <= b <= c[1] + 2 else min(abs(c[0] - b), abs(c[1] - b))
    # the line itself: the one with most ink near the baseline (a text layer written by
    # another program, or an earlier edit, may sit a little off the scan's own baseline)
    near = [c for c in clusters if dist(c) <= 0.6 * (y1 - y0)] or [min(clusters, key=dist)]
    c0, c1 = max(near, key=lambda c: int(counts[c[0]:c[1]].sum()))
    # 2) its body: from the first to the last row dense with ink (the top and bottom of the
    # lowercase letters: their curves, serifs and bars)
    sub = counts[c0:c1]
    dense = np.nonzero(sub >= 0.4 * sub.max())[0]
    by0, by1 = y0 + c0 + int(dense[0]), y0 + c0 + int(dense[-1]) + 1
    body = max(1, by1 - by0)
    h_px = max(4.0, body / 0.52)            # about the font size: x-height is about half of it
    cols = np.nonzero(mark[by0:by1, x0:x1].any(axis=0))[0]
    x0, x1 = x0 + int(cols[0]), x0 + int(cols[-1]) + 1
    y0, y1 = by0, by1

    def text_row(y):
        return mark[y, x0:x1].any() and not is_rule(y, x0, x1)
    # ascenders and descenders: rows with ink next to the body, no further than they reach
    lo, hi = max(0, by0 - int(0.6 * body) - 1), min(hgt, by1 + int(0.55 * body) + 1)
    while y0 > lo and text_row(y0 - 1):
        y0 -= 1
    while y1 < hi and text_row(y1):
        y1 += 1
    # sideways over letter and word gaps (a gap wider than half the line height ends it)
    gap = max(2, int(0.5 * h_px))
    keep = [y for y in range(y0, y1) if not is_rule(y, x0, x1)]
    cols = mark[keep].any(axis=0) if keep else mark[y0:y1].any(axis=0)
    while True:
        ahead = np.nonzero(cols[x1:x1 + gap])[0]
        if not len(ahead):
            break
        x1 += int(ahead[-1]) + 1
    while x0 > 0 and cols[x0 - 1]:
        x0 -= 1
    core = (x0, y0, x1, y1)
    # a small margin of paper takes the scanner's halo along, never a neighbor's ink or a rule
    for _ in range(max(1, int(0.15 * h_px))):
        if y0 > lo and not mark[y0 - 1, x0:x1].any() and not is_rule(y0 - 1, x0, x1):
            y0 -= 1
        if y1 < hi and not mark[y1, x0:x1].any() and not is_rule(y1, x0, x1):
            y1 += 1
        if x1 < wid and not mark[y0:y1, x1].any():
            x1 += 1
        if x0 > 0 and not mark[y0:y1, x0 - 1].any():
            x0 -= 1
    # cover bands: every row but those a ruled line runs through (and its neighbors)
    rule = np.array([is_rule(y, x0, x1) for y in range(y0, y1)], bool)
    if rule.any():
        rule = rule | np.r_[rule[1:], False] | np.r_[False, rule[:-1]]
    bands, start = [], None
    for i, r in enumerate(list(rule) + [True]):
        if not r and start is None:
            start = i
        elif r and start is not None:
            bands.append((x0, y0 + start, x1, y0 + i))
            start = None
    found = {"core": core, "bands": bands, "paper_level": paper, "mark": mark,
             "paper": None, "color": None, "body": body, "h_px": h_px}
    paper_rgb = np.median(view.rgb[~mark].reshape(-1, 3), axis=0) if (~mark).any() else \
        np.array([255, 255, 255])
    found["paper"] = tuple(float(c) / 255 for c in paper_rgb)
    if not _letters(view, found, core):
        return None
    return found


def _letters(view, found, core):
    """Measure the letters inside core (pixel box): their color, their shape as a mask cut
    halfway between paper and ink, and how much ink they hold (blur spreads ink but keeps its
    amount, once the scanner's gamma-encoded gray is turned back into light). False when
    there's no ink there."""
    x0, y0, x1, y1 = core
    paper = found["paper_level"]
    g = view.gray[y0:y1, x0:x1]
    sub_ink = g < paper - INK_STEP
    letters = view.rgb[y0:y1, x0:x1][sub_ink]
    if len(letters) == 0:
        return False
    lum = letters.mean(axis=1)
    darkest = float(lum.min())
    text_rgb = np.median(letters[lum <= (darkest + paper) / 2], axis=0)
    # the letters' box where they are half dark: blur widens the faint edge on every side,
    # this box is where a crisp font's letters would end
    mask = g < (darkest + paper) / 2
    rows, cols = np.nonzero(mask.any(axis=1))[0], np.nonzero(mask.any(axis=0))[0]
    if not len(rows):
        return False
    r0, r1, k0, k1 = int(rows[0]), int(rows[-1]) + 1, int(cols[0]), int(cols[-1]) + 1
    # how much ink, over the letters' whole area (blurred halo included): blur moves ink but
    # keeps its amount. Measured this way, regular and bold scans of real documents fall
    # on the regular and bold fonts' ink shares.
    lin = (g / 255.0) ** GAMMA
    lp, lf = (paper / 255.0) ** GAMMA, (float(np.percentile(g, 2)) / 255.0) ** GAMMA
    found.update(core=core, fit=(x0 + k0, y0 + r0, x0 + k1, y0 + r1),
                 color=tuple(float(c) / 255 for c in text_rgb), mask=mask[r0:r1, k0:k1],
                 mass=float(np.clip((lp - lin) / max(1e-6, lp - lf), 0, 1).mean()))
    return True


def _trim_symbols(found, lead, trail, h_px):
    """Leave out the first `lead` and last `trail` glyphs (symbols the fonts can't draw, such
    as a checkbox the OCR read as part of a word) from the letters' box: each is the ink up
    to the next gap. Returns the trimmed (x0, x1) or None when that doesn't work out."""
    x0, y0, x1, y1 = found["core"]
    cols = found["mark"][y0:y1, x0:x1].any(axis=0)
    runs, start = [], None                        # [start, end) of inked column runs
    for i, v in enumerate(list(cols) + [False]):
        if v and start is None:
            start = i
        elif not v and start is not None:
            runs.append([start, i])
            start = None
    # glyphs touching each other count as one run: only drop runs no wider than a symbol
    if len(runs) <= lead + trail:
        return None
    if any(r[1] - r[0] > 1.6 * h_px for r in runs[:lead] + (runs[-trail:] if trail else [])):
        return None
    a = runs[lead][0]
    b = runs[len(runs) - 1 - trail][1]
    left = runs[lead - 1][1] if lead else 0            # where the symbols' ink ends / starts
    right = runs[len(runs) - trail][0] if trail else x1 - x0
    return x0 + a, x0 + b, x0 + left, x0 + right


# ---- which font -------------------------------------------------------------------------------

_CANDIDATES = None


def _all_candidates():
    """[(name, label, kind, bold, italic, source)]: source None for a built-in font, else
    {"fontfile": path}. Built once."""
    global _CANDIDATES
    if _CANDIDATES is None:
        from .text_edit import _system_fonts, _norm
        out = [(k, label, kind, bold, it, None) for k, label, kind, bold, it in BUILTIN]
        fonts = _system_fonts()
        for family, kind in INSTALLED:
            for bold in (False, True):
                key = _norm(family + (" Bold" if bold else ""))
                path = fonts.get(key)
                if path:
                    out.append(("KZM" + key[:20], family, kind, bold, False, {"fontfile": path}))
        _CANDIDATES = out
    return _CANDIDATES


def candidates():
    """The fonts a scanned line is compared with (see _all_candidates)."""
    return _all_candidates()



def _drawn(cand, text):
    """The text drawn in a candidate font at REF_SIZE: (mask cropped to its letters, ink box
    in points relative to the origin, Font) or None."""
    name, _label, _kind, _bold, _it, source = cand
    try:
        font = pymupdf.Font(fontfile=source["fontfile"]) if source else pymupdf.Font(name)
        if not all(font.has_glyph(ord(c)) for c in text if c.strip()):
            return None
        width = font.text_length(text, fontsize=REF_SIZE)
        doc = pymupdf.open()
        page = doc.new_page(width=width + 2 * REF_SIZE, height=3 * REF_SIZE)
        if source:
            page.insert_font(fontname="KZcand", **source)
            fname = "KZcand"
        else:
            fname = name
        origin = pymupdf.Point(REF_SIZE, 2 * REF_SIZE)
        page.insert_text(origin, text, fontsize=REF_SIZE, fontname=fname)
        pm = page.get_pixmap(colorspace=pymupdf.csGRAY, alpha=False)
        g = np.frombuffer(pm.samples, np.uint8).reshape(pm.height, pm.stride)[:, :pm.width]
        m = g < 128
        rows, cols = np.nonzero(m.any(axis=1))[0], np.nonzero(m.any(axis=0))[0]
        if not len(rows):
            return None
        box = pymupdf.Rect(cols[0] - origin.x, rows[0] - origin.y,
                           cols[-1] + 1 - origin.x, rows[-1] + 1 - origin.y)
        return m[rows[0]:rows[-1] + 1, cols[0]:cols[-1] + 1], box, font
    except Exception:
        return None


def _resize(mask, h, w):
    ys = (np.arange(h) * mask.shape[0] / h).astype(int)
    xs = (np.arange(w) * mask.shape[1] / w).astype(int)
    return mask[ys][:, xs]


def _grow(m):
    g = m.copy()
    g[1:] |= m[:-1]
    g[:-1] |= m[1:]
    g[:, 1:] |= m[:, :-1]
    g[:, :-1] |= m[:, 1:]
    return g


def _score(scan, drawn, h_ratio):
    """How alike the scanned letters and a candidate's are: (shape 0-1, the candidate's ink
    share). Shape = overlap of the letters (a pixel of slack), and how tall they come out at
    the width that fits."""
    cand = _resize(drawn, *scan.shape)
    a, b = scan.sum(), cand.sum()
    if not a or not b:
        return 0.0, 0.0
    precision = (cand & _grow(scan)).sum() / b
    recall = (scan & _grow(cand)).sum() / a
    shape = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return float(shape * h_ratio ** 2), float(cand.mean())


def analyze(page, line, old_text):
    """How to rewrite this line so it matches the scan, or None when the line isn't on a
    scanned page or nothing of it shows in the picture. Returns {"cover": [page rects],
    "paper", "color": RGB 0-1, "font": candidate tuple or None, "label", "kind", "bold",
    "italic", "size", "origin": baseline start Point (unrotated page coords)}."""
    if not scanned_page(page):
        return None
    spans = line["spans"]
    # A line written over the scan by an earlier edit is handled too when the old letters
    # still show in the picture under it; an edit made by this version covered them, so the
    # picture shows paper there and the line keeps its own font (None below).
    tmp = _picture_only(page)
    try:
        box = pymupdf.Rect(line["bbox"])
        turn = _upright(line)
        h = box.height if abs(line["dir"][0]) >= 0.5 else box.width   # across the text
        search = pymupdf.Rect(box.x0 - 4 * h, box.y0 - 4 * h, box.x1 + 4 * h, box.y1 + 4 * h)
        search &= tmp[0].rect
        if search.is_empty:
            return None
        view = _View(tmp[0], search, turn)
        a, b = view.to_px(box.tl), view.to_px(box.br)
        box_px = pymupdf.Rect(min(a.x, b.x), min(a.y, b.y), max(a.x, b.x), max(a.y, b.y))
        found = _find_ink(view, box_px, view.to_px(spans[0]["origin"]).y)
    finally:
        tmp.close()
    if found is None:
        return None
    x0, y0, x1, y1 = found["fit"]
    if (y1 - y0) > 3 * found["h_px"] or (x1 - x0) > box_px.width + 6 * found["h_px"]:
        return None                          # not this line's letters: leave the page alone
    cover = [view.rect_to_page(*b) for b in found["bands"]]
    ink_w, ink_h = (x1 - x0) / ZOOM, (y1 - y0) / ZOOM          # points
    first = spans[0]
    result = {"cover": cover, "paper": found["paper"], "color": found["color"], "font": None,
              "label": "Helvetica", "kind": "sans", "bold": False, "italic": False,
              "unsure": False, "lead": "", "trail": "", "cover_letters": None,
              "size": float(max(s["size"] for s in spans)),
              "origin": pymupdf.Point(first["origin"])}
    # the old words as the fonts can draw them (symbols such as a checkbox drawn by the
    # scanner's OCR as part of a word are left out; the size then comes from the height)
    words = " ".join(old_text.split())
    text = "".join(c for c in words if _plain(c)).strip()
    partial = text != words
    if partial and text and all(_plain(c) for c in text):
        # symbols only at the start / end (a scanned checkbox before a line): leave their
        # ink out and match the rest by width as usual
        lead = len(words) - len(words.lstrip("".join(set(c for c in words if not _plain(c)))))
        trail = len(words) - len(words.rstrip("".join(set(c for c in words if not _plain(c)))))
        inner = words[lead:len(words) - trail]
        if all(_plain(c) for c in inner):
            cut = _trim_symbols(found, lead, trail, found["h_px"])
            cy0, cy1 = found["core"][1], found["core"][3]
            if cut and _letters(view, found, (cut[0], cy0, cut[1], cy1)):
                x0, y0, x1, y1 = found["fit"]
                ink_w, ink_h = (x1 - x0) / ZOOM, (y1 - y0) / ZOOM
                text, partial = inner.strip(), False
                # when the new text keeps the symbols, the scan keeps showing them: only
                # the letters are covered and rewritten
                m = max(1, int(0.15 * found["h_px"]))
                lx0, lx1 = max(cut[2] + 1, x0 - m), min(cut[3] - 1, x1 + m)
                result.update(lead=words[:lead].strip(), trail=words[len(words) - trail:].strip(),
                              cover_letters=[view.rect_to_page(max(b[0], lx0), b[1],
                                                               min(b[2], lx1), b[3])
                                             for b in found["bands"]])
    if len([c for c in text if c.strip()]) < MIN_CHARS:
        if not all(_invisible(sp) for sp in spans):
            return None                  # too little to tell it's the scan's own words
        result["size"] = round(found["body"] / ZOOM / 0.52, 1)
        return result
    # 1) the typeface by the letters' shape; 2) regular, bold or italic of it by how much ink
    # the letters hold (blur thickens or thins strokes, but keeps the amount of ink)
    tried = []
    for cand in candidates():
        drawn = _drawn(cand, text)
        if drawn is None:
            continue
        mask, cbox, font = drawn
        scale = ink_h / cbox.height if partial else ink_w / cbox.width   # REF_SIZE -> scan
        h_ratio = 1.0 if partial else \
            min(cbox.height * scale, ink_h) / max(cbox.height * scale, ink_h)
        shape, ink = _score(found["mask"], mask, h_ratio)
        tried.append((shape, cand, cbox, scale, ink))
    if not tried:
        return result if all(_invisible(sp) for sp in spans) else None
    family = max(tried, key=lambda t: t[0] * (1.01 if t[1][5] is None else 1.0))[1][1]
    same = [t for t in tried if t[1][1] == family]
    shape0 = max(t[0] for t in same)
    best = min(same, key=lambda t: abs(np.log(max(1e-6, found["mass"]) / max(1e-6, t[4])))
               - (0.5 if t[0] >= shape0 - 0.03 else 0.0))
    best = (best[0], best[1], best[2], best[3], shape0)
    sc, cand, cbox, scale, shape = best
    if shape < SURE:
        if not all(_invisible(sp) for sp in spans):
            # visible text whose words aren't the letters under it (text added over the
            # scan): not a scanned line; leave the picture alone
            return None
        # the OCR text doesn't fit the letters (misread): Helvetica with the same x-height
        result.update(size=round(found["body"] / ZOOM / 0.52, 1), unsure=True)
        return result
    size = REF_SIZE * scale
    # the baseline start: where the candidate's origin sits relative to its letters, fitted
    # to the scanned letters' box (left edge and top/bottom)
    sy = (y1 - y0) / ZOOM / cbox.height
    ox = x0 / ZOOM - cbox.x0 * scale
    oy = y0 / ZOOM - cbox.y0 * sy
    origin = view.to_page(ox * ZOOM, oy * ZOOM)
    if partial:
        # the symbol comes first: keep the text layer's own start, on the fitted baseline
        o = view.to_px(result["origin"])
        origin = view.to_page(o.x, oy * ZOOM)
    result.update(font=cand, label=cand[1], kind=cand[2], bold=cand[3], italic=cand[4],
                  size=round(size, 1), origin=origin, score=round(shape, 3))
    return result


def _plain(c):
    """A character every candidate font can draw (Western text, WinAnsi)."""
    try:
        c.encode("cp1252")
        return True
    except UnicodeEncodeError:
        return False
