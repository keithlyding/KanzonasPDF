"""Find similar symbols (Measure > Find similar, as Bluebeam's VisualSearch): one symbol picked on
a sheet (a box dragged around it), its matches found on the page or the whole document and
placed as Count markers of a group, for the user to check before keeping them.

How: the page is drawn without its markups, gray, at a resolution that makes the symbol at least
about 32 pixels across (at most 200 dpi, and never more than PIXELS in all), and OpenCV's
normalized cross-correlation (cv2.matchTemplate, TM_CCOEFF_NORMED) finds where the symbol's
picture is; with "turned" also the symbol turned by quarters. A place scores from -1 to 1; those
at sensitivity or above are matches, the best of those overlapping each other kept. A blank or
flat picked area finds nothing (it would match all the white paper).

Everything runs on the main thread, a page at a time (PyMuPDF isn't thread-safe: AGENTS.md):
the view calls search_page for each page in turn from the event loop. OpenCV and NumPy are
imported when a search runs, not at start-up."""

import math

import pymupdf

PIXELS = 24_000_000          # the most a page is drawn at for a search (a 36 x 24 in sheet at
                             # ~160 dpi), so a huge one doesn't run out of memory
MIN_PX = 32                  # the symbol drawn at least this big across (its smaller side)
MAX_DPI = 200.0
DEFAULT_SENSITIVITY = 0.8


def zoom_for(page, rect):
    """The zoom (1 = 72 dpi) a search on page for a symbol in rect draws at."""
    side = max(1.0, min(rect.width, rect.height))
    z = max(1.0, min(MAX_DPI / 72.0, MIN_PX / side))
    area = page.rect.width * page.rect.height
    if area * z * z > PIXELS:
        z = max(0.25, math.sqrt(PIXELS / area))
    return z


def _gray(page, zoom, clip=None):
    """page drawn gray without its markups at zoom, as a NumPy array (0 black..255 white)."""
    import numpy as np
    pm = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), colorspace=pymupdf.csGRAY,
                         clip=clip, annots=False, alpha=False)
    return np.frombuffer(pm.samples, dtype=np.uint8).reshape(pm.height, pm.width).copy()


def template(page, rect, zoom):
    """The picked symbol's picture (rect, unrotated page points) at zoom, or None when it's
    blank or flat (all one shade: it would match the empty paper everywhere)."""
    rect = pymupdf.Rect(rect) & page.rect
    if rect.is_empty or rect.width < 2 or rect.height < 2:
        return None
    # (drawn through the page's own matrix: a turned page's rect is in its unrotated space)
    clip = rect * page.rotation_matrix
    img = _gray(page, zoom, clip.normalize())
    if img.size == 0 or float(img.std()) < 4.0:
        return None
    return img


def search_page(page, tmpl, zoom, sensitivity=DEFAULT_SENSITIVITY, turned=False):
    """[(Rect in unrotated page points, score)] where tmpl (template()) is found on page,
    the best first, overlapping ones left out."""
    import cv2
    import numpy as np
    img = _gray(page, zoom)
    found = []
    shapes = [tmpl]
    if turned:
        shapes += [np.ascontiguousarray(np.rot90(tmpl, k)) for k in (1, 2, 3)]
    for t in shapes:
        th, tw = t.shape
        if th > img.shape[0] or tw > img.shape[1] or th < 3 or tw < 3:
            continue
        res = cv2.matchTemplate(img, t, cv2.TM_CCOEFF_NORMED)
        ys, xs = np.where(res >= sensitivity)
        for y, x in zip(ys.tolist(), xs.tolist()):
            found.append((float(res[y, x]), x, y, tw, th))
    found.sort(key=lambda f: -f[0])
    kept = []
    for score, x, y, w, h in found:
        cx, cy = x + w / 2.0, y + h / 2.0
        # (one per symbol: a place near one kept already is the same symbol a pixel over)
        if any(abs(cx - kx) < max(w, kw) * 0.6 and abs(cy - ky) < max(h, kh) * 0.6
               for kx, ky, kw, kh, _s in kept):
            continue
        kept.append((cx, cy, w, h, score))
    out = []
    to_page = page.derotation_matrix        # (drawn as shown: back to unrotated points)
    for cx, cy, w, h, score in kept:
        r = pymupdf.Rect((cx - w / 2) / zoom, (cy - h / 2) / zoom,
                         (cx + w / 2) / zoom, (cy + h / 2) / zoom)
        out.append(((r * to_page).normalize(), score))
    return out
