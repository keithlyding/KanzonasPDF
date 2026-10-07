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


def compare(old_bytes, new_bytes, dpi=110, progress=None, old_name="OLD", new_name="NEW"):
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
        ref = pn or po
        rects = [r for r in (po.rect if po else None, pn.rect if pn else None) if r is not None]
        width = max(r.width for r in rects)
        height = max(r.height for r in rects)
        size = (int(round(height * dpi / 72)) + 1, int(round(width * dpi / 72)) + 1)
        a = _gray(po, dpi, size) if po else np.full(size, 255, np.uint8)
        b = _gray(pn, dpi, size) if pn else np.full(size, 255, np.uint8)
        ink_a, ink_b = a < INK, b < INK
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
        if not po or not pn:
            page.insert_text((12, 26), "This page exists only in " +
                             (new_name if pn else old_name), fontsize=8, color=(0.4, 0, 0.4))
        counts.append(len(regions))
    data = out.tobytes(garbage=3, deflate=True)
    return data, counts
