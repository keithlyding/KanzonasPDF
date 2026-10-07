"""Snapping: to a grid, and to objects (markup corners / ends / centers and the drawing's own
line work: line ends and midpoints, rectangle corners).

Points are kept in unrotated PDF coordinates in a bucket grid so lookups stay fast on CAD
sheets with hundreds of thousands of lines.
"""

import math

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


def content_index(page):
    """Snap points of the page's own vector drawing (line ends and midpoints, corners)."""
    idx = PointIndex()
    try:
        paths = page.get_drawings()
    except Exception:
        return idx
    for path in paths:
        for it in path["items"]:
            op = it[0]
            if op == "l":
                a, b = it[1], it[2]
                idx.add(a.x, a.y)
                idx.add(b.x, b.y)
                idx.add((a.x + b.x) / 2, (a.y + b.y) / 2)
            elif op == "c":
                idx.add(it[1].x, it[1].y)
                idx.add(it[4].x, it[4].y)
            elif op == "re":
                r = it[1]
                for q in (r.tl, r.tr, r.bl, r.br):
                    idx.add(q.x, q.y)
            elif op == "qu":
                q = it[1]
                for p in (q.ul, q.ur, q.ll, q.lr):
                    idx.add(p.x, p.y)
    return idx


def markup_points(model):
    """Corners, edge midpoints and center of a markup; ends and midpoints of line segments."""
    pts = []
    if model["kind"] in A.POINTED:
        q = model["points"]
        pts += q
        closed = model["kind"] in ("polygon", "m_area")
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
    for an in page.annots():
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
