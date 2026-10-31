"""Trim, as in CAD (the CAD tab): clicking a line removes the part of it between the nearest
lines crossing it on either side of the click (or up to its end when nothing crosses on
that side). A line that nothing crosses goes completely. Works on polylines in page
coordinates; callers write the pieces back (page_objects.rewrite_path for the drawing's own
line work, a markup's points for line markups)."""
import math

import pymupdf

EPS = 1e-6


def _cum(poly):
    out = [0.0]
    for a, b in zip(poly, poly[1:]):
        out.append(out[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
    return out


def _at(poly, cum, s):
    s = max(0.0, min(cum[-1], s))
    for k in range(len(poly) - 1):
        if cum[k + 1] >= s:
            seg = cum[k + 1] - cum[k]
            t = 0.0 if seg <= EPS else (s - cum[k]) / seg
            a, b = poly[k], poly[k + 1]
            return pymupdf.Point(a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
    return pymupdf.Point(poly[-1])


def piece(poly, cum, s0, s1):
    """The part of the polyline from position s0 to s1 (s0 < s1, both within its length)."""
    out = [_at(poly, cum, s0)]
    for k in range(1, len(poly) - 1):
        if s0 < cum[k] < s1:
            out.append(pymupdf.Point(poly[k]))
    out.append(_at(poly, cum, s1))
    return [q for k, q in enumerate(out) if k == 0 or abs(q - out[k - 1]) > EPS]


def project(poly, cum, pt):
    """(position along the polyline nearest pt, distance to it)."""
    best = (0.0, float("inf"))
    for k in range(len(poly) - 1):
        a, b = poly[k], poly[k + 1]
        dx, dy = b[0] - a[0], b[1] - a[1]
        L = dx * dx + dy * dy
        t = 0.0 if L == 0 else max(0.0, min(1.0, ((pt[0] - a[0]) * dx + (pt[1] - a[1]) * dy) / L))
        d = math.hypot(a[0] + t * dx - pt[0], a[1] + t * dy - pt[1])
        if d < best[1]:
            best = (cum[k] + t * (cum[k + 1] - cum[k]), d)
    return best


def _hit(a, b, c, d):
    """Where segment ab meets segment cd, as the fraction along ab, or None."""
    r = (b[0] - a[0], b[1] - a[1])
    q = (d[0] - c[0], d[1] - c[1])
    den = r[0] * q[1] - r[1] * q[0]
    if abs(den) < 1e-12:
        return None                     # parallel (overlapping lines don't cut)
    w = (c[0] - a[0], c[1] - a[1])
    t = (w[0] * q[1] - w[1] * q[0]) / den
    u = (w[0] * r[1] - w[1] * r[0]) / den
    if -1e-9 <= t <= 1 + 1e-9 and -1e-9 <= u <= 1 + 1e-9:
        return max(0.0, min(1.0, t))
    return None


def crossings(poly, cum, cutters):
    """Positions along the polyline where it meets any cutter polyline. The cutters' pieces
    near the polyline go into a grid of cells first, so each piece of the polyline is only
    tested against the pieces in the cells it passes (a contour on a site plan crosses a
    hundred thousand lines' worth of drawing)."""
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    x0, x1, y0, y1 = min(xs) - 0.01, max(xs) + 0.01, min(ys) - 0.01, max(ys) + 0.01
    n = 64
    cw, ch = max(x1 - x0, 1e-6) / n, max(y1 - y0, 1e-6) / n

    def col(x):
        return max(0, min(n - 1, int((x - x0) / cw)))

    def row(y):
        return max(0, min(n - 1, int((y - y0) / ch)))
    grid = {}
    for cut in cutters:
        if len(cut) < 2:
            continue
        for c, d in zip(cut, cut[1:]):
            lx, hx = min(c[0], d[0]), max(c[0], d[0])
            ly, hy = min(c[1], d[1]), max(c[1], d[1])
            if hx < x0 or lx > x1 or hy < y0 or ly > y1:
                continue
            seg = (c, d)
            for r in range(row(ly), row(hy) + 1):
                for k in range(col(lx), col(hx) + 1):
                    grid.setdefault((k, r), []).append(seg)
    out = []
    for k in range(len(poly) - 1):
        a, b = poly[k], poly[k + 1]
        lx, hx = min(a[0], b[0]), max(a[0], b[0])
        ly, hy = min(a[1], b[1]), max(a[1], b[1])
        seen = set()
        for r in range(row(ly), row(hy) + 1):
            for c_ in range(col(lx), col(hx) + 1):
                for seg in grid.get((c_, r), ()):
                    if id(seg) in seen:
                        continue
                    seen.add(id(seg))
                    c, d = seg
                    if max(c[0], d[0]) < lx or min(c[0], d[0]) > hx or \
                            max(c[1], d[1]) < ly or min(c[1], d[1]) > hy:
                        continue
                    t = _hit(a, b, c, d)
                    if t is not None:
                        out.append(cum[k] + t * (cum[k + 1] - cum[k]))
    return sorted(out)


def crosses(poly, cutters):
    """True when any of cutters crosses (or touches) the polyline."""
    poly = [pymupdf.Point(p) for p in poly]
    return bool(crossings(poly, _cum(poly), cutters))


def trim(poly, closed, click, cutters):
    """The pieces of the polyline left after trimming at click: [] when it all goes, None
    when the click is right on a crossing (it can't tell which side to cut away)."""
    poly = [pymupdf.Point(p) for p in poly]
    cum = _cum(poly)
    total = cum[-1]
    if total <= EPS:
        return []
    s, _d = project(poly, cum, click)
    tol = 1e-4 * max(1.0, total)
    cuts = []
    for c in crossings(poly, cum, cutters):
        if (closed or tol < c < total - tol) and not (cuts and c - cuts[-1] <= tol):
            cuts.append(c)              # (one cut where several lines meet at a point)
    if closed and len(cuts) > 1 and cuts[0] + total - cuts[-1] <= tol:
        cuts.pop()                      # (the same point, at the start and the end)
    if any(abs(c - s) <= max(tol, 0.5) for c in cuts):
        return None                     # the click is on a crossing: which side to cut?
    before = [c for c in cuts if c < s - tol]
    after = [c for c in cuts if c > s + tol]
    if closed:
        if len(cuts) < 2:
            return []
        lo = before[-1] if before else cuts[-1] - total
        hi = after[0] if after else cuts[0] + total
        # what's left runs from hi round to lo (going past the start / end point)
        if lo < 0:
            out = [piece(poly, cum, hi, lo + total)]
        elif hi > total:
            out = [piece(poly, cum, hi - total, lo)]
        else:
            out = [piece(poly, cum, hi, total)[:-1] + piece(poly, cum, 0.0, lo)]
        return [p_ for p_ in out if len(p_) >= 2 and _length(p_) > tol]
    lo = before[-1] if before else 0.0
    hi = after[0] if after else total
    out = []
    if lo > tol:
        out.append(piece(poly, cum, 0.0, lo))
    if hi < total - tol:
        out.append(piece(poly, cum, hi, total))
    return [p_ for p_ in out if _length(p_) > tol]


def _length(pts):
    return _cum(pts)[-1]
