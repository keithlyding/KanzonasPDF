"""Compare two revisions of a document.

Each page pair is rendered, differences are found pixel by pixel, and a result PDF is
built: an overlay image per page (only in OLD = red, only in NEW = blue, unchanged = gray)
plus a revision cloud around every changed area, listed in the markups list.
"""

import numpy as np
import pymupdf

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
        if scale_b != 1.0:
            # scaled renders differ by a pixel along every edge, and a sheet printed smaller
            # often keeps its pen widths, so its lines come out thicker once scaled back up:
            # ink within a few pixels of the other revision's ink is the same line
            r = int(np.ceil(max(scale_b, 1 / scale_b))) + 1
            only_a = ink_a & ~_grow(ink_b, r)
            only_b = ink_b & ~_grow(ink_a, r)
        elif shift != (0, 0):
            # a move is rarely a whole number of pixels: edges then differ by one pixel
            only_a = ink_a & ~_grow(ink_b)
            only_b = ink_b & ~_grow(ink_a)
        else:
            only_a = ink_a & ~ink_b
            only_b = ink_b & ~ink_a
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
            kind = "added" if removed == 0 else "removed" if added == 0 else "changed"
            annot.set_info(content=f"Change {k} ({kind})", title="Compare")
            annot.update()
        legend = (f"Compare  |  red = only in {old_name}  |  blue = only in {new_name}  |  "
                  f"gray = unchanged  |  {len(regions)} change(s) on this page")
        page.insert_text((12, 14), legend, fontsize=8, color=(0.4, 0, 0.4))
        notes = []
        if scale_b != 1.0:
            notes.append(f"{new_name} is {pn.rect.width / 72:.1f} x {pn.rect.height / 72:.1f} in, "
                         f"{old_name} {po.rect.width / 72:.1f} x {po.rect.height / 72:.1f} in: "
                         f"{new_name} was scaled x{scale_b:.3g} to {old_name}'s size before comparing")
        if shift != (0, 0):
            notes.append(f"Lined up: the drawing in {new_name} sits "
                         f"{-shift[1] * 72 / dpi:+.1f} pt right and {shift[0] * 72 / dpi:+.1f}"
                         f" pt up from {old_name}")
        for k, note in enumerate(notes):
            page.insert_text((12, 26 + 12 * k), note, fontsize=8, color=(0.4, 0, 0.4))
        if not po or not pn:
            page.insert_text((12, 26), "This page exists only in " +
                             (new_name if pn else old_name), fontsize=8, color=(0.4, 0, 0.4))
        counts.append(len(regions))
    data = out.tobytes(garbage=3, deflate=True)
    return data, counts
