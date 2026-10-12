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
    pm = page.get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY, annots=True, alpha=False)
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


def _grow(m):
    """The mask grown by one pixel in every direction."""
    g = m.copy()
    g[1:, :] |= m[:-1, :]
    g[:-1, :] |= m[1:, :]
    g2 = g.copy()
    g2[:, 1:] |= g[:, :-1]
    g2[:, :-1] |= g[:, 1:]
    return g2


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
        rects = [r for r in (po.rect if po else None, pn.rect if pn else None) if r is not None]
        width = max(r.width for r in rects)
        height = max(r.height for r in rects)
        size = (int(round(height * dpi / 72)) + 1, int(round(width * dpi / 72)) + 1)
        a = _gray(po, dpi, size) if po else np.full(size, 255, np.uint8)
        b = _gray(pn, dpi, size) if pn else np.full(size, 255, np.uint8)
        shift = (0, 0)
        if align and po and pn:
            shift = find_shift(a < INK, b < INK)
            if shift != (0, 0):
                b = _move(b, *shift)          # the new revision, lined up on the old one
        ink_a, ink_b = a < INK, b < INK
        if shift != (0, 0):
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
        if shift != (0, 0):
            page.insert_text((12, 26), f"Lined up: the drawing in {new_name} sits "
                             f"{-shift[1] * 72 / dpi:+.1f} pt right and {shift[0] * 72 / dpi:+.1f}"
                             f" pt up from {old_name}", fontsize=8, color=(0.4, 0, 0.4))
        if not po or not pn:
            page.insert_text((12, 26), "This page exists only in " +
                             (new_name if pn else old_name), fontsize=8, color=(0.4, 0, 0.4))
        counts.append(len(regions))
    data = out.tobytes(garbage=3, deflate=True)
    return data, counts
