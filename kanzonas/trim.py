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
    return out


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
    """Positions along the polyline where it meets any cutter polyline."""
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    x0, x1, y0, y1 = min(xs) - 0.01, max(xs) + 0.01, min(ys) - 0.01, max(ys) + 0.01
    out = []
    for cut in cutters:
        if len(cut) < 2:
            continue
        cx = [p[0] for p in cut]
        cy = [p[1] for p in cut]
        if max(cx) < x0 or min(cx) > x1 or max(cy) < y0 or min(cy) > y1:
            continue
        for c, d in zip(cut, cut[1:]):
            if max(c[0], d[0]) < x0 or min(c[0], d[0]) > x1 or \
                    max(c[1], d[1]) < y0 or min(c[1], d[1]) > y1:
                continue
            for k in range(len(poly) - 1):
                t = _hit(poly[k], poly[k + 1], c, d)
                if t is not None:
                    out.append(cum[k] + t * (cum[k + 1] - cum[k]))
    return sorted(out)


def trim(poly, closed, click, cutters):
    """The pieces of the polyline left after trimming at click: [] when it all goes."""
    poly = [pymupdf.Point(p) for p in poly]
    cum = _cum(poly)
    total = cum[-1]
    if total <= EPS:
        return []
    s, _d = project(poly, cum, click)
    tol = 1e-4 * max(1.0, total)
    cuts = [c for c in crossings(poly, cum, cutters)
            if closed or tol < c < total - tol]
    before = [c for c in cuts if c < s - tol]
    after = [c for c in cuts if c > s + tol]
    if closed:
        if len(cuts) < 2:
            return []
        lo = before[-1] if before else cuts[-1] - total
        hi = after[0] if after else cuts[0] + total
        # what's left runs from hi round to lo (going past the start / end point)
        if lo < 0:
            return [piece(poly, cum, hi, lo + total)]
        if hi > total:
            return [piece(poly, cum, hi - total, lo)]
        return [p_ for p_ in (piece(poly, cum, hi, total)[:-1] + piece(poly, cum, 0.0, lo),)
                if len(p_) >= 2]
    lo = before[-1] if before else 0.0
    hi = after[0] if after else total
    out = []
    if lo > tol:
        out.append(piece(poly, cum, 0.0, lo))
    if hi < total - tol:
        out.append(piece(poly, cum, hi, total))
    return out
