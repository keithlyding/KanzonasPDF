"""Compare two revisions of a document.

Two ways, for two kinds of document:

compare(): drawings. Each page pair is rendered, differences are found pixel by pixel, and
a result PDF is built: an overlay image per page (only in OLD = red, only in NEW = blue,
unchanged = gray) plus a revision cloud around every changed area, listed in the markups list.

compare_text(): text that reflows (letters, specifications, permits). One inserted sentence
moves every line after it, so an overlay would cloud whole pages; instead the words of both
documents are compared in reading order, and the result is a copy of NEW with the added words
highlighted, a red mark where words were removed, and pictures that came or went boxed, plus
a summary of every change on the last page.
"""

import difflib

import numpy as np
import pymupdf

from .i18n import tr

OLD_RGB = (220, 30, 30)
NEW_RGB = (20, 90, 230)
SAME_RGB = (150, 150, 150)
INK = 200            # pixels darker than this count as content
CELL = 6             # px: grid cell size used to group differences into areas
MIN_CELLS = 2        # ignore specks smaller than this many cells


def _gray(page, dpi, size):
    z = dpi / 72                     # (a matrix, since get_pixmap wants a whole-number dpi)
    pm = page.get_pixmap(matrix=pymupdf.Matrix(z, z), colorspace=pymupdf.csGRAY, annots=True,
                         alpha=False)
    return _fit(pm, size)


def _fit(pm, size):
    a = np.frombuffer(pm.samples, np.uint8).reshape(pm.height, pm.stride)[:, :pm.width]
    out = np.full(size, 255, np.uint8)
    h, w = min(size[0], a.shape[0]), min(size[1], a.shape[1])
    out[:h, :w] = a[:h, :w]
    return out


def _regions(mask):
    """Group changed pixels into rectangles (pixel coords) via a coarse grid + flood fill."""
    h, w = mask.shape
    gh, gw = (h + CELL - 1) // CELL, (w + CELL - 1) // CELL
    pad = np.zeros((gh * CELL, gw * CELL), bool)
    pad[:h, :w] = mask
    grid = pad.reshape(gh, CELL, gw, CELL).any(axis=(1, 3))
    # dilate by one cell so nearby changes join into one area
    dil = grid.copy()
    dil[1:, :] |= grid[:-1, :]
    dil[:-1, :] |= grid[1:, :]
    dil[:, 1:] |= grid[:, :-1]
    dil[:, :-1] |= grid[:, 1:]
    seen = np.zeros_like(dil)
    rects = []
    for y0, x0 in zip(*np.nonzero(dil)):
        if seen[y0, x0]:
            continue
        stack = [(y0, x0)]
        seen[y0, x0] = True
        ys, xs, real = [], [], 0
        while stack:
            y, x = stack.pop()
            ys.append(y)
            xs.append(x)
            real += grid[y, x]
            for ny, nx in ((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)):
                if 0 <= ny < gh and 0 <= nx < gw and dil[ny, nx] and not seen[ny, nx]:
                    seen[ny, nx] = True
                    stack.append((ny, nx))
        if real >= MIN_CELLS:
            rects.append((min(xs) * CELL, min(ys) * CELL, (max(xs) + 1) * CELL, (max(ys) + 1) * CELL))
    return rects


COARSE = 1200        # px: longest side of the copies used to find how far a sheet moved
MAX_SHIFT = 0.15     # a move larger than this share of the page isn't a move (no alignment)


def _shrink(ink, f):
    h, w = (ink.shape[0] // f) * f, (ink.shape[1] // f) * f
    return ink[:h, :w].reshape(h // f, f, w // f, f).any(axis=(1, 3)).astype(np.float32)


def _overlap(a, b, dy, dx):
    """How many ink pixels of a and b (b moved by dy, dx) coincide."""
    h, w = a.shape
    ys, yd = (slice(dy, h), slice(0, h - dy)) if dy >= 0 else (slice(0, h + dy), slice(-dy, h))
    xs, xd = (slice(dx, w), slice(0, w - dx)) if dx >= 0 else (slice(0, w + dx), slice(-dx, w))
    return int((a[ys, xs] & b[yd, xd]).sum())


def find_shift(a, b):
    """(dy, dx) in pixels that moves page image b onto a (both ink masks of one size), found
    by phase correlation on small copies, then refined at full size. (0, 0) when moving
    doesn't line them up better."""
    f = max(1, int(np.ceil(max(a.shape) / COARSE)))
    sa, sb = _shrink(a, f), _shrink(b, f)
    if sa.sum() < 20 or sb.sum() < 20:
        return 0, 0
    fa, fb = np.fft.rfft2(sa), np.fft.rfft2(sb)
    cross = fa * np.conj(fb)
    cross /= np.abs(cross) + 1e-9
    corr = np.fft.irfft2(cross, s=sa.shape)
    py, px = np.unravel_index(int(np.argmax(corr)), corr.shape)
    h, w = sa.shape
    py = py - h if py > h // 2 else py
    px = px - w if px > w // 2 else px
    if abs(py) > MAX_SHIFT * h or abs(px) > MAX_SHIFT * w:
        return 0, 0
    best, base = (0, 0), _overlap(a, b, 0, 0)
    score = base
    for dy in range(py * f - f, py * f + f + 1):
        for dx in range(px * f - f, px * f + f + 1):
            o = _overlap(a, b, dy, dx)
            if o > score:
                best, score = (dy, dx), o
    # only when it lines up clearly better than as it lies
    return best if score > base * 1.2 + 10 else (0, 0)


def _grow(m, r=1):
    """The mask grown by r pixels in every direction."""
    for _ in range(r):
        g = m.copy()
        g[1:, :] |= m[:-1, :]
        g[:-1, :] |= m[1:, :]
        g2 = g.copy()
        g2[:, 1:] |= g[:, :-1]
        g2[:, :-1] |= g[:, 1:]
        m = g2
    return m


def page_scale(old_rect, new_rect):
    """How much the new page must be scaled to be the old page's size (the same sheet plotted
    at another paper size: a 24x36 and its 11x17 print), keeping proportions; 1 when the
    pages are the same size (within 1%)."""
    if old_rect is None or new_rect is None or not new_rect.width or not new_rect.height:
        return 1.0
    s = min(old_rect.width / new_rect.width, old_rect.height / new_rect.height)
    return 1.0 if abs(s - 1) < 0.01 else s


def _ink_box(gray):
    """(x0, y0, x1, y1) in pixels around everything dark on the page, or None."""
    ink = gray < INK
    rows, cols = np.where(ink.any(axis=1))[0], np.where(ink.any(axis=0))[0]
    if len(rows) < 2 or len(cols) < 2:
        return None
    return cols[0], rows[0], cols[-1] + 1, rows[-1] + 1


def find_scale(po, pn, dpi):
    """How much the new page's drawing must be scaled to be the old page's drawing: 1 for a
    page of the same size, else the best of the paper-size ratio and the drawn-extent ratios
    (a print fitted to a paper of another shape is smaller than the paper ratio says), judged
    on small copies by how much ink coincides once lined up. An extent ratio is then measured
    again at full size, since a tenth of a percent still misaligns the far edge of a sheet."""
    base = page_scale(po.rect, pn.rect)
    if base == 1.0:
        return 1.0
    small = COARSE / max(po.rect.width, po.rect.height) * 72          # dpi for ~COARSE px

    def gray(page, d):
        return _gray(page, d, (int(page.rect.height * d / 72) + 1, int(page.rect.width * d / 72) + 1))

    def pair(a, page, d):
        """a and the page rendered at d dpi, on one canvas big enough for both (a scaled
        print may stick out past the reference page: nothing of it may be cut off)."""
        b = gray(page, d)
        shape = (max(a.shape[0], b.shape[0]), max(a.shape[1], b.shape[1]))
        pa, pb = np.full(shape, 255, np.uint8), np.full(shape, 255, np.uint8)
        pa[:a.shape[0], :a.shape[1]] = a
        pb[:b.shape[0], :b.shape[1]] = b
        return pa, pb

    def extent_ratio(a, b):
        ba, bb = _ink_box(a), _ink_box(b)
        if not ba or not bb:
            return None
        w = (ba[2] - ba[0]) / (bb[2] - bb[0])
        h = (ba[3] - ba[1]) / (bb[3] - bb[1])
        return (w + h) / 2 if abs(w - h) < 0.02 * w else None   # same drawing: same ratio both ways
    a = gray(po, small)
    cands = [(base, "paper"), (1.0, "paper")]
    ratio = extent_ratio(a, gray(pn, small))
    if ratio:
        cands.append((ratio, "extent"))
    best, best_kind, best_score, seen = base, "paper", -1, []
    for c, kind in cands:
        if not 0.2 < c < 5 or any(abs(c - x) < 0.005 for x in seen):
            continue
        seen.append(c)
        pa, bc = pair(a, pn, small * c)
        ia, ib = pa < INK, bc < INK
        shift = find_shift(ia, ib)
        score = _overlap(ia, _move(bc, *shift) < INK, 0, 0) if shift != (0, 0) else _overlap(ia, ib, 0, 0)
        if score > best_score * 1.02:            # a clearly better fit, else the earlier candidate
            best, best_kind, best_score = c, kind, score
    if best_kind == "extent":
        ratio = extent_ratio(*pair(gray(po, dpi), pn, dpi * best))
        if ratio:
            best *= ratio
    return 1.0 if abs(best - 1) < 0.01 else best


def _move(img, dy, dx, fill=255):
    out = np.full_like(img, fill)
    h, w = img.shape
    ys, yd = (slice(dy, h), slice(0, h - dy)) if dy >= 0 else (slice(0, h + dy), slice(-dy, h))
    xs, xd = (slice(dx, w), slice(0, w - dx)) if dx >= 0 else (slice(0, w + dx), slice(-dx, w))
    out[ys, xs] = img[yd, xd]
    return out


def compare(old_bytes, new_bytes, dpi=110, progress=None, old_name="OLD", new_name="NEW",
            align=True):
    """Returns (result PDF bytes, [changes per page])."""
    old = pymupdf.open(stream=old_bytes, filetype="pdf")
    new = pymupdf.open(stream=new_bytes, filetype="pdf")
    out = pymupdf.open()
    counts = []
    n = max(old.page_count, new.page_count)
    for i in range(n):
        if progress:
            progress(i, n)
        po = old[i] if i < old.page_count else None
        pn = new[i] if i < new.page_count else None
        # the old page is the reference; a new page of another paper size is scaled to it
        scale_b = find_scale(po, pn, dpi) if (po and pn and align) else 1.0
        rects = [r for r in (po.rect if po else None,
                             (pn.rect * pymupdf.Matrix(scale_b, scale_b)) if pn else None)
                 if r is not None]
        width = max(r.width for r in rects)
        height = max(r.height for r in rects)
        size = (int(round(height * dpi / 72)) + 1, int(round(width * dpi / 72)) + 1)
        a = _gray(po, dpi, size) if po else np.full(size, 255, np.uint8)
        b = _gray(pn, dpi * scale_b, size) if pn else np.full(size, 255, np.uint8)
        shift = (0, 0)
        if align and po and pn:
            shift = find_shift(a < INK, b < INK)
            if shift != (0, 0):
                b = _move(b, *shift)          # the new revision, lined up on the old one
        ink_a, ink_b = a < INK, b < INK
        # Ink within a pixel of the other revision's ink is the same line: two exports of
        # the same page differ by a pixel along the edges of their text (sub-pixel
        # placement, anti-aliasing), and a move is rarely a whole number of pixels. A sheet
        # printed smaller often keeps its pen widths, so once scaled back up its lines come
        # out thicker, and scaled renders differ by a pixel along every edge.
        r = int(np.ceil(max(scale_b, 1 / scale_b))) + 1 if scale_b != 1.0 else 1
        only_a = ink_a & ~_grow(ink_b, r)
        only_b = ink_b & ~_grow(ink_a, r)
        img = np.full(size + (3,), 255, np.uint8)
        img[ink_a & ink_b] = SAME_RGB
        img[only_a] = OLD_RGB
        img[only_b] = NEW_RGB
        pix = pymupdf.Pixmap(pymupdf.csRGB, size[1], size[0], img.tobytes(), False)
        page = out.new_page(width=width, height=height)
        page.insert_image(page.rect, pixmap=pix)
        scale = 72 / dpi
        regions = _regions(only_a | only_b)
        for k, (x0, y0, x1, y1) in enumerate(regions, 1):
            r = pymupdf.Rect(x0 * scale - 4, y0 * scale - 4, x1 * scale + 4, y1 * scale + 4)
            annot = page.add_rect_annot(r)
            annot.set_colors(stroke=(0.85, 0, 0.75))
            annot.set_border(width=1.5, clouds=1)
            removed = only_a[y0:y1, x0:x1].sum()
            added = only_b[y0:y1, x0:x1].sum()
            kind = tr("added") if removed == 0 else tr("removed") if added == 0 else tr("changed")
            annot.set_info(content=tr("Change {n} ({kind})").format(n=k, kind=kind),
                           title=tr("Compare"))
            annot.update()
        legend = tr("Compare  |  red = only in {old}  |  blue = only in {new}  |  "
                    "gray = unchanged  |  {n} change(s) on this page").format(
                        old=old_name, new=new_name, n=len(regions))
        page.insert_text((12, 14), legend, fontsize=8, color=(0.4, 0, 0.4))
        notes = []
        if scale_b != 1.0:
            notes.append(tr("{new} is {new_size} in, {old} {old_size} in: {new} was scaled "
                            "x{factor} to {old}'s size before comparing").format(
                new=new_name, old=old_name, factor=f"{scale_b:.3g}",
                new_size=f"{pn.rect.width / 72:.1f} x {pn.rect.height / 72:.1f}",
                old_size=f"{po.rect.width / 72:.1f} x {po.rect.height / 72:.1f}"))
        if shift != (0, 0):
            notes.append(tr("Lined up: the drawing in {new} sits {right} pt right and {up} pt "
                            "up from {old}").format(new=new_name, old=old_name,
                                                    right=f"{-shift[1] * 72 / dpi:+.1f}",
                                                    up=f"{shift[0] * 72 / dpi:+.1f}"))
        for k, note in enumerate(notes):
            page.insert_text((12, 26 + 12 * k), note, fontsize=8, color=(0.4, 0, 0.4))
        if not po or not pn:
            page.insert_text((12, 26), tr("This page exists only in {name}").format(
                name=new_name if pn else old_name), fontsize=8, color=(0.4, 0, 0.4))
        counts.append(len(regions))
    data = out.tobytes(garbage=3, deflate=True)
    return data, counts


# ---- text mode -----------------------------------------------------------------------

ADD_RGB = (0.45, 0.65, 1.0)          # highlight for words added in NEW
GONE_RGB = (0.85, 0.1, 0.1)          # mark where words of OLD are gone
PIC_RGB = (0.85, 0, 0.75)            # box around a picture that changed
MIN_WORDS = 20                       # a page with fewer words has no text layer to speak of


def has_text(doc, sample=24):
    """True when most of the (first `sample`) pages carry a text layer."""
    n = min(doc.page_count, sample)
    if n == 0:
        return False
    texty = 0
    for i in range(n):
        try:
            if len(doc[i].get_text("words")) >= MIN_WORDS:
                texty += 1
        except Exception:
            pass
    return texty * 2 >= n


def _words(doc):
    """[(page index, rect, text)] for the whole document, in reading order."""
    out = []
    for page in doc:
        try:
            ws = page.get_text("words")
        except Exception:
            continue
        ws.sort(key=lambda w: (w[5], w[6], w[7]))        # block, line, word
        out.extend((page.number, pymupdf.Rect(w[:4]), w[4]) for w in ws)
    return out


def text_changes(old, new):
    """The words that differ between two documents, in reading order: a list of
    {"kind": "added" | "removed" | "changed", "old": [(page, rect, text)],
    "new": [(page, rect, text)], "anchor": (page, rect) where a removal sits in NEW}."""
    wa, wb = _words(old), _words(new)
    sm = difflib.SequenceMatcher(None, [w[2] for w in wa], [w[2] for w in wb], autojunk=False)
    changes = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        kind = {"replace": "changed", "insert": "added", "delete": "removed"}[tag]
        c = {"kind": kind, "old": wa[i1:i2], "new": wb[j1:j2], "anchor": None}
        if not c["new"]:
            # the gap in NEW where the words were: right after the previous word that is in
            # both, or before the next one
            if j1 > 0:
                p, r, _t = wb[j1 - 1]
                c["anchor"] = (p, pymupdf.Rect(r.x1, r.y0, r.x1 + max(6, r.height * 0.6), r.y1))
            elif j1 < len(wb):
                p, r, _t = wb[j1]
                c["anchor"] = (p, pymupdf.Rect(r.x0 - max(6, r.height * 0.6), r.y0, r.x0, r.y1))
            else:                                    # NEW has no words at all
                c["anchor"] = (0, pymupdf.Rect(36, 36, 48, 48))
        changes.append(c)
    return changes


def _pictures(doc):
    """[(page index, rect, digest)] of every picture placed on a page."""
    out = []
    for page in doc:
        try:
            infos = page.get_image_info(hashes=True)
        except Exception:
            continue
        for info in infos:
            r = pymupdf.Rect(info["bbox"])
            if r.is_empty or r.width < 4 or r.height < 4:
                continue
            out.append((page.number, r, info.get("digest")))
    return out


def _clip_differs(po, pn, rect):
    """True when the two pages look different inside rect (a picture re-encoded on export
    has another digest but the same pixels)."""
    try:
        z = max(0.2, min(1.0, 300 / max(rect.width, rect.height)))
        m = pymupdf.Matrix(z, z)
        a = po.get_pixmap(matrix=m, clip=rect, colorspace=pymupdf.csGRAY, alpha=False)
        b = pn.get_pixmap(matrix=m, clip=rect, colorspace=pymupdf.csGRAY, alpha=False)
    except Exception:
        return True
    if (a.width, a.height) != (b.width, b.height):
        return True
    ga = np.frombuffer(a.samples, np.uint8).astype(np.int16)
    gb = np.frombuffer(b.samples, np.uint8).astype(np.int16)
    return float((np.abs(ga - gb) > 40).mean()) > 0.02


def picture_changes(old, new):
    """Pictures added, removed or resized between the documents, in the same form as
    text_changes() (the "old" / "new" entries hold (page, rect, "picture"))."""
    pa, pb = _pictures(old), _pictures(new)
    used = set()
    changes = []
    for pg, rect, digest in pb:
        same = [k for k, (p, r, d) in enumerate(pa) if k not in used and d == digest]
        if same:
            # the same picture: the one on the same page at the same place when there is one
            k = min(same, key=lambda k: (pa[k][0] != pg, abs(pa[k][1].width - rect.width)))
            used.add(k)
            r = pa[k][1]
            if pa[k][0] != pg or abs(r.width - rect.width) > 1 or abs(r.height - rect.height) > 1:
                changes.append({"kind": "changed", "old": [(pa[k][0], r, "picture")],
                                "new": [(pg, rect, "picture")], "anchor": None,
                                "what": "picture moved" if pa[k][0] != pg else "picture resized"})
            continue
        here = [k for k, (p, r, d) in enumerate(pa)
                if k not in used and p == pg and abs(r.x0 - rect.x0) < 2 and abs(r.y0 - rect.y0) < 2
                and abs(r.width - rect.width) < 2 and abs(r.height - rect.height) < 2]
        if here:
            used.add(here[0])
            if pg < old.page_count and _clip_differs(old[pg], new[pg], rect):
                changes.append({"kind": "changed", "old": [(pg, pa[here[0]][1], "picture")],
                                "new": [(pg, rect, "picture")], "anchor": None,
                                "what": "picture replaced"})
            continue
        changes.append({"kind": "added", "old": [], "new": [(pg, rect, "picture")],
                        "anchor": None, "what": "picture added"})
    for k, (pg, rect, _d) in enumerate(pa):
        if k not in used:
            changes.append({"kind": "removed", "old": [(pg, rect, "picture")], "new": [],
                            "anchor": (min(pg, new.page_count - 1), rect) if new.page_count else None,
                            "what": "picture removed"})
    return changes


def _text_of(run, limit=160):
    t = " ".join(w[2] for w in run)
    return t if len(t) <= limit else t[:limit - 3].rstrip() + "..."


def _describe(c):
    """One line saying what the change is, for the markup's comment and the summary."""
    if c.get("what"):
        w = c["what"]
        if w == "picture resized":
            o, n = c["old"][0][1], c["new"][0][1]
            return tr("Picture resized: {old} in, now {new} in").format(
                old=f"{o.width / 72:.1f} x {o.height / 72:.1f}",
                new=f"{n.width / 72:.1f} x {n.height / 72:.1f}")
        return _WHAT.get(w) or w[0].upper() + w[1:]
    if c["kind"] == "added":
        return tr("Added: {text}").format(text=_text_of(c['new']))
    if c["kind"] == "removed":
        return tr("Removed: {text}").format(text=_text_of(c['old']))
    return tr("Was: {old}  |  Now: {new}").format(old=_text_of(c['old']), new=_text_of(c['new']))


# what a picture change is (the "what" keys), as written in the result
_WHAT = {"picture moved": tr("Picture moved"), "picture replaced": tr("Picture replaced"),
         "picture added": tr("Picture added"), "picture removed": tr("Picture removed")}


def _page_ranges(pages):
    """[0, 1, 2, 5] -> 'pages 1-3, 6'."""
    pages = sorted(set(pages))
    parts, start, prev = [], pages[0], pages[0]
    for p in pages[1:] + [None]:
        if p is not None and p == prev + 1:
            prev = p
            continue
        parts.append(f"{start + 1}-{prev + 1}" if prev > start else f"{start + 1}")
        if p is not None:
            start = prev = p
    return (tr("pages {list}") if len(pages) > 1 else tr("page {list}")).format(
        list=", ".join(parts))


def _box(page, rect, color, text, clouds=0, fill=False):
    a = page.add_rect_annot(rect)
    a.set_colors(stroke=color, fill=color if fill else None)
    if fill:
        a.set_opacity(0.5)
    a.set_border(width=2 if clouds else 1, clouds=clouds)
    a.set_info(content=text, title=tr("Compare"))
    a.update()
    return a


def _legend(page, lines):
    """Small purple lines at the top of the page, upright however the page is rotated."""
    rot = page.rotation
    for k, text in enumerate(lines):
        pt = pymupdf.Point(12, 14 + 12 * k) * page.derotation_matrix
        page.insert_text(pt, text, fontsize=8, color=(0.4, 0, 0.4), rotate=rot)


def compare_text(old_bytes, new_bytes, progress=None, old_name="OLD", new_name="NEW"):
    """Word-by-word comparison. Returns (result PDF bytes, [changes per page of NEW]): a copy
    of NEW with every change marked (blue highlight = words added, red mark = words of OLD
    gone from here, box = picture added / removed / resized), each a markup whose comment
    says what changed, and a summary of all changes on the last page(s)."""
    old = pymupdf.open(stream=old_bytes, filetype="pdf")
    new = pymupdf.open(stream=new_bytes, filetype="pdf")
    if progress:
        progress(0, 3)
    changes = text_changes(old, new)
    if progress:
        progress(1, 3)
    changes += picture_changes(old, new)
    if progress:
        progress(2, 3)
    out = pymupdf.open()
    if new.page_count:
        out.insert_pdf(new)
    counts = [0] * out.page_count
    for k, c in enumerate(changes, 1):
        text = tr("Change {n}: {what}").format(n=k, what=_describe(c))
        pages = set()
        if c.get("what"):
            # pictures: a box around where the picture is (NEW) or was (OLD's place)
            color = (PIC_RGB if c["kind"] == "changed" else ADD_RGB if c["kind"] == "added"
                     else GONE_RGB)
            for pg, rect, _t in (c["new"] or c["old"]):
                if 0 <= pg < out.page_count:
                    page = out[pg]                       # (kept while its annot is used)
                    _box(page, rect + (-3, -3, 3, 3), color, text, clouds=1)
                    pages.add(pg)
        else:
            by_page = {}
            for pg, rect, _t in c["new"]:
                by_page.setdefault(pg, []).append(rect)
            for pg, rects in by_page.items():
                if 0 <= pg < out.page_count:
                    page = out[pg]
                    a = page.add_highlight_annot(rects)
                    a.set_colors(stroke=ADD_RGB)
                    a.set_info(content=text, title=tr("Compare"))
                    a.update()
                    pages.add(pg)
            if not c["new"] and c["anchor"] and 0 <= c["anchor"][0] < out.page_count:
                pg, rect = c["anchor"]
                page = out[pg]
                _box(page, rect, GONE_RGB, text, fill=True)
                pages.add(pg)
        for pg in pages:
            counts[pg] += 1
    for pg in range(out.page_count):
        n = counts[pg]
        _legend(out[pg], [tr("Compare (text)  |  blue = added in {new}  |  red mark = removed "
                             "from {old} (its comment says what)  |  {n} change(s) on this "
                             "page  |  summary on the last page").format(new=new_name,
                                                                         old=old_name, n=n)])
    # the summary: every change, repeated ones (a header on every page) once with their pages
    groups = {}
    for k, c in enumerate(changes, 1):
        key = (c["kind"], c.get("what"), _text_of(c["old"]), _text_of(c["new"]))
        pg = (c["new"] or c["old"])[0][0] if (c["new"] or c["old"]) else 0
        groups.setdefault(key, []).append((k, pg))
    lines = [tr("Compare, text mode: {new} against {old}: {n} change(s)").format(
        new=new_name, old=old_name, n=len(changes))]
    if old.page_count != new.page_count:
        lines.append(tr("{old} has {old_pages} page(s), {new} {new_pages}").format(
            old=old_name, new=new_name, old_pages=old.page_count, new_pages=new.page_count))
    lines.append(tr("Blue highlight = words added in the newer document; red mark = words of "
                    "the earlier one gone from there. Moved text counts as removed and added."))
    lines.append("")
    for key, items in sorted(groups.items(), key=lambda kv: kv[1][0][1]):
        c = changes[items[0][0] - 1]
        if len(items) == 1:
            lines.append(tr("Change {n}, page {page}: {what}").format(
                n=items[0][0], page=items[0][1] + 1, what=_describe(c)))
        elif len(items) <= 4:
            lines.append(tr("Changes {list}, {pages}: {what}").format(
                list=", ".join(str(k) for k, _pg in items),
                pages=_page_ranges([pg for _k, pg in items]), what=_describe(c)))
        else:
            lines.append(tr("Change {n} and {more} more like it, {pages}: {what}").format(
                n=items[0][0], more=len(items) - 1,
                pages=_page_ranges([pg for _k, pg in items]), what=_describe(c)))
    _summary_pages(out, lines)
    if progress:
        progress(3, 3)
    return out.tobytes(garbage=3, deflate=True), counts


def _summary_pages(out, lines):
    """Append the lines as pages of 9 pt text, as many as needed."""
    text = "\n".join(lines)
    while text:
        page = out.new_page(width=612, height=792)
        box = pymupdf.Rect(48, 54, 564, 750)
        page.insert_text((48, 40), tr("Compare: summary of changes"), fontsize=12, color=(0.4, 0, 0.4))
        rest = page.insert_textbox(box, text, fontsize=9, fontname="helv", color=(0, 0, 0))
        if rest >= 0:
            break
        # did not fit (then nothing was written): the lines that fit here, the rest after
        fit = _lines_that_fit(box, text)
        page.insert_textbox(box, "\n".join(text.split("\n")[:fit]), fontsize=9, fontname="helv")
        text = "\n".join(text.split("\n")[fit:])
        if fit == 0:
            break


def _lines_that_fit(box, text):
    probe = pymupdf.open()
    page = probe.new_page(width=612, height=792)
    rows = text.split("\n")
    lo, hi = 0, len(rows)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if page.insert_textbox(box, "\n".join(rows[:mid]), fontsize=9, fontname="helv") >= 0:
            lo = mid
        else:
            hi = mid - 1
    return lo
