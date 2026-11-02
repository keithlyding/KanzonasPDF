"""Snapping: to a grid, and to objects (markup corners / ends / centers and the drawing's own
line work: line ends and midpoints, rectangle corners).

Points are kept in unrotated PDF coordinates in a bucket grid so lookups stay fast on CAD
sheets with hundreds of thousands of lines.
"""

import math
from array import array

import pymupdf

from . import annotations as A

CELL = 24.0                     # bucket size, points
UNITS = {"in": 72.0, "mm": 72.0 / 25.4, "pt": 1.0}
UNIT_NAMES = {"in": "inches", "mm": "millimeters", "pt": "points"}


class PointIndex:
    """Nearest-point lookup. Each point carries a tag (an xref for markups, 0 for content)."""

    def __init__(self):
        self.buckets = {}

    def add(self, x, y, tag=0):
        key = (int(x // CELL), int(y // CELL))
        self.buckets.setdefault(key, []).append((x, y, tag))

    def nearest(self, pt, tol, exclude=()):
        best, best_d = None, tol
        r = int(math.ceil(tol / CELL))
        cx, cy = int(pt.x // CELL), int(pt.y // CELL)
        for i in range(cx - r, cx + r + 1):
            for j in range(cy - r, cy + r + 1):
                for x, y, tag in self.buckets.get((i, j), ()):
                    if tag and tag in exclude:
                        continue
                    d = math.hypot(x - pt.x, y - pt.y)
                    if d <= best_d:
                        best, best_d = pymupdf.Point(x, y), d
        return best


class ContentIndex:
    """PointIndex for the drawing's own points (no tags): each bucket keeps its points as
    one array of x, y numbers, a tenth of the memory of a tuple per point (a 200,000-line
    sheet has 600,000 of them)."""

    def __init__(self):
        self.buckets = {}               # (column, row) -> array("d", [x, y, x, y, ...])

    def __len__(self):
        return sum(len(b) for b in self.buckets.values()) // 2

    def nearest(self, pt, tol, exclude=()):
        best, best_d = None, tol
        r = int(math.ceil(tol / CELL))
        px, py = pt.x, pt.y
        cx, cy = int(px // CELL), int(py // CELL)
        hypot = math.hypot
        for i in range(cx - r, cx + r + 1):
            for j in range(cy - r, cy + r + 1):
                b = self.buckets.get((i, j))
                if b is None:
                    continue
                for k in range(0, len(b), 2):
                    d = hypot(b[k] - px, b[k + 1] - py)
                    if d <= best_d:
                        best, best_d = (b[k], b[k + 1]), d
        return None if best is None else pymupdf.Point(best)


def content_index(page):
    """Snap points of the page's own vector drawing (line ends and midpoints, corners)."""
    idx = None
    for idx in content_index_steps(page):
        pass
    return idx


def content_index_steps(page, step=20000):
    """content_index() a little at a time: a generator that yields None after reading the
    drawing (one MuPDF call) and after every `step` paths it sorts into buckets, and the
    finished ContentIndex last. The points are the ones get_drawings() gives, taken from
    MuPDF's plain numbers (no Point object for each one: a third of the time)."""
    idx = ContentIndex()
    try:
        paths = page.get_cdrawings()
    except Exception:
        yield idx
        return
    yield None
    buckets = idx.buckets
    get = buckets.get
    for s in range(0, len(paths), step):
        pts = []
        add = pts.extend
        for path in paths[s:s + step]:
            for it in path["items"]:
                op = it[0]
                if op == "l":
                    (ax, ay), (bx, by) = it[1], it[2]
                    add((ax, ay, bx, by, (ax + bx) / 2, (ay + by) / 2))
                elif op == "c":
                    add(it[1])
                    add(it[4])
                elif op == "re":
                    x0, y0, x1, y1 = it[1]
                    if x1 < x0:         # (as Rect.normalize)
                        x0, x1 = x1, x0
                    if y1 < y0:
                        y0, y1 = y1, y0
                    add((x0, y0, x1, y0, x0, y1, x1, y1))
                elif op == "qu":
                    for q in it[1]:     # ul, ur, ll, lr
                        add(q)
        for k in range(0, len(pts), 2):
            x, y = pts[k], pts[k + 1]
            key = (int(x // CELL), int(y // CELL))
            b = get(key)
            if b is None:
                b = buckets[key] = array("d")
            b.append(x)
            b.append(y)
        yield None
    yield idx


def markup_points(model):
    """Corners, edge midpoints and center of a markup; ends and midpoints of line segments."""
    pts = []
    if model["kind"] == "arc" or model.get("bend") is not None:
        from . import curves            # (its ends, its middle, an arc's center)
        return curves.snap_points(model)
    if model["kind"] in A.POINTED:
        q = model["points"]
        pts += q
        closed = model["kind"] in ("polygon",) + A.CLOSED_MEASURES
        segs = list(zip(q, q[1:] + (q[:1] if closed else [])))
        pts += [(a + b) / 2 for a, b in segs]
        return pts
    if model["kind"] == "ink":
        return [s[0] for s in model["strokes"] if s] + [s[-1] for s in model["strokes"] if s]
    if A.turned(model):
        o = A.outline(model) if model["kind"] != "ellipse" else A.outline(model, 4)
        pts += o + [(a + b) / 2 for a, b in zip(o, o[1:] + o[:1])]
        r = pymupdf.Rect(model["rect"])
        return pts + [pymupdf.Point((r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2)]
    r = A.bounds(model)
    cx, cy = (r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2
    pts += [r.tl, r.tr, r.bl, r.br, pymupdf.Point(cx, r.y0), pymupdf.Point(cx, r.y1),
            pymupdf.Point(r.x0, cy), pymupdf.Point(r.x1, cy), pymupdf.Point(cx, cy)]
    if model["kind"] == "callout":
        pts += model.get("points", [])
    return pts


def markup_index(page):
    idx = PointIndex()
    for an in A.each_annot(page):
        if an.type[0] in (pymupdf.PDF_ANNOT_POPUP, pymupdf.PDF_ANNOT_REDACT):
            continue
        try:
            m = A.read(an)
        except Exception:
            m = None
        if m is None or m["kind"] in A.MARKUP:
            continue
        for q in markup_points(m):
            idx.add(q.x, q.y, an.xref)
    return idx


def grid_snap(page, pt, spacing):
    """Nearest grid intersection. The grid starts at the top-left of the page as displayed."""
    d = pymupdf.Point(pt) * page.rotation_matrix
    d = pymupdf.Point(round(d.x / spacing) * spacing, round(d.y / spacing) * spacing)
    return d * page.derotation_matrix


def page_snap(page, pt, tol):
    """Snap to the page itself (unrotated coordinates): a corner, the middle of an edge or
    the center within tol; else onto an edge (x or y alone) within tol. None if not near."""
    r = page.rect * page.derotation_matrix
    cx, cy = (r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2
    best, best_d = None, tol
    for x in (r.x0, cx, r.x1):
        for y in (r.y0, cy, r.y1):
            d = math.hypot(x - pt.x, y - pt.y)
            if d <= best_d:
                best, best_d = pymupdf.Point(x, y), d
    if best is not None:
        return best
    x = next((e for e in (r.x0, r.x1) if abs(pt.x - e) <= tol), None)
    y = next((e for e in (r.y0, r.y1) if abs(pt.y - e) <= tol), None)
    if x is None and y is None:
        return None
    return pymupdf.Point(pt.x if x is None else x, pt.y if y is None else y)
