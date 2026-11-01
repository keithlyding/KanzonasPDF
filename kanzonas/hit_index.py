"""Quick lookups for what's under the mouse, so moving it over a busy page stays a few
milliseconds: built once per page (cache them until the page changes) from plain numbers,
then each lookup is a handful of numpy comparisons instead of a Python loop over every
character, line or shape, each made into a pymupdf.Rect.

The answers are the same as the plain loops gave, to the last bit: where PyMuPDF rounds a
rectangle to MuPDF's 32-bit numbers (joining or cutting rectangles, testing a point inside
one), the same rounding is done here; elsewhere the quick test only narrows the search and
the exact test runs on what's left."""
import math
import struct

_F = struct.Struct("f")
_BIG = 3.4028234663852886e38


def f32(x):
    """x as MuPDF stores it (a C float)."""
    if not -_BIG <= x <= _BIG:
        return x if x != x else math.copysign(math.inf, x)
    return _F.unpack(_F.pack(x))[0]


def _empty(r):
    return r[0] >= r[2] or r[1] >= r[3]


def join(a, b):
    """pymupdf.Rect(a) | b, in plain numbers (a box around both; an empty one is left out,
    and MuPDF's rounding is kept)."""
    if _empty(b):
        return tuple(a)
    if _empty(a):
        return tuple(b)
    return (f32(min(a[0], b[0])), f32(min(a[1], b[1])), f32(max(a[2], b[2])),
            f32(max(a[3], b[3])))


def _joined(boxes, start_joined):
    """The box PyMuPDF makes from boxes (each one's (x0, y0, x1, y1)) with r = Rect(first)
    then r |= each next one; start_joined: it started with Rect(first) | first instead.
    Worked out at once: one box joined by MuPDF is rounded, a lone box isn't."""
    full = [b for b in boxes if not (b[0] >= b[2] or b[1] >= b[3])]
    if not full:
        return tuple(boxes[0][:4])
    if len(full) == 1 and not (start_joined and full[0] is boxes[0]):
        return tuple(full[0][:4])
    return (f32(min(b[0] for b in full)), f32(min(b[1] for b in full)),
            f32(max(b[2] for b in full)), f32(max(b[3] for b in full)))


def line_boxes(units):
    """DocumentView.line_rects in plain numbers: [(x0, y0, x1, y1)] of each text line the
    selected characters are on, in the order they come."""
    lines, order = {}, []
    for w in units:
        key = (w[5], w[6])
        got = lines.get(key)
        if got is None:
            lines[key] = [w]
            order.append(key)
        else:
            got.append(w)
    return [_joined(lines[k], False) for k in order]


class TextIndex:
    """A page's selectable characters (DocumentView._words: (x0, y0, x1, y1, text, block,
    line, n), in block order) ready for the text selection's questions."""

    def __init__(self, words):
        import numpy as np
        self.words = words
        a = np.array([w[:4] for w in words], dtype=float).reshape(-1, 4)
        self.x0, self.y0, self.x1, self.y1 = (np.ascontiguousarray(a[:, k]) for k in range(4))
        self.block = np.array([w[5] for w in words], dtype=np.int64)
        # a block's characters come one after the other: [first, last + 1) of each
        self.span = {}
        for i, w in enumerate(words):
            b = w[5]
            if b in self.span:
                self.span[b][1] = i + 1
            else:
                self.span[b] = [i, i + 1]
        # each block's box as text_selection joined it (Rect(w) | w, then |= each next)
        self.bbox = {b: _joined(words[s:e], True) for b, (s, e) in self.span.items()}
        self._order = None
        self._yc = None

    # -- the character under (or nearest to) a point ------------------------------------
    def near(self, pt, limit=None):
        """DocumentView._word_near: the first character whose box holds pt; else the
        nearest one (distance with heights counted double); None past limit."""
        import numpy as np
        import pymupdf
        words = self.words
        if not words:
            return None
        px, py = pt.x, pt.y
        # (a box that holds the point is inside this slightly bigger search)
        e = 1e-3 + 1e-6 * (abs(px) + abs(py))
        cand = np.flatnonzero((self.x0 <= px + e) & (self.x1 >= px - e) &
                              (self.y0 <= py + e) & (self.y1 >= py - e))
        for i in cand.tolist():
            if pymupdf.Rect(words[i][:4]).contains(pt):
                return i
        dx = np.maximum(np.maximum(self.x0 - px, 0), px - self.x1)
        dy = np.maximum(np.maximum(self.y0 - py, 0), py - self.y1)
        s = dx * dx + 4 * dy * dy
        smin = float(s.min())
        if smin != smin:            # (a box with no numbers: the plain loop's way)
            return self._near_loop(pt, limit)
        # the nearest by the squared distance, and any whose square root may round the same
        best, best_d = None, None
        for i in np.flatnonzero(s <= smin * (1 + 1e-9)).tolist():
            w = words[i]
            ddx = max(w[0] - px, 0, px - w[2])
            ddy = max(w[1] - py, 0, py - w[3])
            d = (ddx * ddx + 4 * ddy * ddy) ** 0.5
            if best_d is None or d < best_d:
                best, best_d = i, d
        if limit is not None and (best_d is None or best_d > limit):
            return None
        return best

    def _near_loop(self, pt, limit):
        import pymupdf
        best, best_d = None, None
        for i, w in enumerate(self.words):
            r = pymupdf.Rect(w[:4])
            if r.contains(pt):
                return i
            dx = max(r.x0 - pt.x, 0, pt.x - r.x1)
            dy = max(r.y0 - pt.y, 0, pt.y - r.y1)
            d = (dx * dx + 4 * dy * dy) ** 0.5
            if best_d is None or d < best_d:
                best, best_d = i, d
        if limit is not None and (best_d is None or best_d > limit):
            return None
        return best

    # -- characters a box takes -----------------------------------------------------------
    def in_box(self, box):
        """Indexes of the characters a selection box takes (box: a normalized
        pymupdf.Rect): those it overlaps by at least 40% of their area. The overlap is cut
        as MuPDF cuts it (in 32-bit numbers), the areas worked as PyMuPDF works them."""
        import numpy as np
        bx0, by0, bx1, by1 = box.x0, box.y0, box.x1, box.y1
        if bx0 >= bx1 or by0 >= by1 or box.is_infinite:
            return []
        x0, y0, x1, y1 = self.x0, self.y0, self.x1, self.y1
        hit = ((x0 < x1) & (y0 < y1) & (x0 < bx1) & (bx0 < x1) & (y0 < by1) & (by0 < y1))
        idx = np.flatnonzero(hit)
        if not len(idx):
            return []
        x0, y0, x1, y1 = x0[idx], y0[idx], x1[idx], y1[idx]
        f = np.float32
        ix0 = np.maximum(x0.astype(f), f(bx0)).astype(float)
        iy0 = np.maximum(y0.astype(f), f(by0)).astype(float)
        ix1 = np.minimum(x1.astype(f), f(bx1)).astype(float)
        iy1 = np.minimum(y1.astype(f), f(by1)).astype(float)
        inter = np.maximum(ix1 - ix0, 0) * np.maximum(iy1 - iy0, 0)
        area = np.maximum(x1 - x0, 0) * np.maximum(y1 - y0, 0)
        return idx[inter >= 0.4 * area].tolist()

    # -- reading order ----------------------------------------------------------------------
    def _prepare_order(self):
        if self._yc is None:
            import numpy as np
            self._yc = [(w[1] + w[3]) / 2 for w in self.words]
            self._h = [w[3] - w[1] for w in self.words]
            # sorted by the middle of each character; equal ones keep their order, as
            # sorted() keeps them
            self._by_y = np.argsort(np.array(self._yc, dtype=float), kind="stable")

    def reading_order(self, mask=None):
        """DocumentView._reading_order of the characters (all of them, or those where mask
        is true), as indexes: rows top to bottom, then left to right."""
        self._prepare_order()
        if mask is None:
            if self._order is None:
                self._order = self._rows(self._by_y.tolist())
            return self._order
        by_y = self._by_y
        return self._rows(by_y[mask[by_y]].tolist())

    def _rows(self, ids):
        yc, hs, words = self._yc, self._h, self.words
        rows, row_y, row_h = [], None, None
        for i in ids:
            y, h = yc[i], hs[i]
            if row_y is None or abs(y - row_y) > 0.5 * max(h, row_h):
                rows.append([i])
                row_y, row_h = y, h
            else:
                rows[-1].append(i)
        out = []
        for row in rows:
            if len(row) > 1:
                row.sort(key=lambda i: words[i][0])
            out.extend(row)
        return out

    def flow(self, si, ei):
        """text_selection's flow between characters si and ei of different blocks: the
        characters in reading order, limited to the columns those blocks occupy and the
        rows between them. Indexes."""
        import numpy as np
        words = self.words
        ws, we = words[si], words[ei]
        span = join(self.bbox[ws[5]], self.bbox[we[5]])
        top, bottom = min(ws[1], we[1]), max(ws[3], we[3])
        cols = np.zeros(max(self.span) + 1 if self.span else 1, dtype=bool)
        for b, r in self.bbox.items():
            if b >= 0 and r[2] > span[0] and r[0] < span[2]:
                cols[b] = True
        mask = cols[self.block] & (self.y1 > top) & (self.y0 < bottom)
        order = self.reading_order(mask)
        i, j = order.index(si), order.index(ei)
        return order[min(i, j):max(i, j) + 1]


class BoxIndex:
    """Boxes of many things on a page, to find the few near a point. It errs on the side
    of more: the caller tests each one it gives the exact way."""

    def __init__(self, rects, grow=None):
        """rects: pymupdf.Rect each; grow: how much more to add around each (as a line's
        half width), or None."""
        import numpy as np
        from operator import attrgetter
        rects = rects if isinstance(rects, list) else list(rects)
        n = len(rects)
        # (each coordinate straight into its array: a list of 200,000 tuples first took
        # most of a second for a big drawing)
        ax0, ay0, ax1, ay1 = (np.fromiter(map(attrgetter(k), rects), dtype=float, count=n)
                              for k in ("x0", "y0", "x1", "y1"))
        x0 = np.minimum(ax0, ax1)
        x1 = np.maximum(ax0, ax1)
        y0 = np.minimum(ay0, ay1)
        y1 = np.maximum(ay0, ay1)
        g = 0 if grow is None else np.asarray(grow, dtype=float)
        # a little room for rounding (MuPDF tests in 32-bit numbers)
        e = 1e-3 + 1e-6 * np.maximum.reduce([np.abs(ax0), np.abs(ay0), np.abs(ax1),
                                             np.abs(ay1)]) if n else 0
        self.x0, self.y0 = x0 - g - e, y0 - g - e
        self.x1, self.y1 = x1 + g + e, y1 + g + e
        self.size = n

    def near(self, x, y, pad=0.0):
        """Indexes (in order) of the boxes within about pad of point (x, y)."""
        import numpy as np
        if not self.size:
            return []
        pad = pad + 1e-3 + 1e-6 * (abs(x) + abs(y))
        return np.flatnonzero((self.x0 <= x + pad) & (self.x1 >= x - pad) &
                              (self.y0 <= y + pad) & (self.y1 >= y - pad)).tolist()


class Segments:
    """A shape's lines (lists of points) as arrays of their pieces, to test them all at once:
    near() is page_objects._near on every line, worked the same way number for number."""

    def __init__(self, lines):
        import numpy as np
        self.lines = lines
        a = [(p.x, p.y, q.x, q.y) for line in lines for p, q in zip(line, line[1:])]
        a = np.array(a, dtype=float).reshape(-1, 4)
        self.ax, self.ay = a[:, 0].copy(), a[:, 1].copy()
        self.dx, self.dy = a[:, 2] - a[:, 0], a[:, 3] - a[:, 1]
        self.L = self.dx * self.dx + self.dy * self.dy
        self.flat = self.L == 0

    def near(self, p, tol):
        """True if a piece passes within tol of point p."""
        import numpy as np
        if not len(self.ax):
            return False
        px, py = p.x, p.y
        with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
            t = ((px - self.ax) * self.dx + (py - self.ay) * self.dy) / self.L
            # max(0.0, min(1.0, t)), and 0.0 for a piece of no length
            t = np.fmax(0.0, np.fmin(1.0, t))
            t[self.flat] = 0.0
            ex = self.ax + t * self.dx - px
            ey = self.ay + t * self.dy - py
            return bool(((ex * ex + ey * ey) <= tol * tol).any())
