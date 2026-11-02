"""Curved markups: the Arc (AutoCAD's three-point ARC: start, a point it passes through, end)
and lines and arrows bent by their middle grip (a quadratic Bezier curve through the grip,
also drawn with the Curve tool: start, end, then where it bends to).

No PDF markup type is a curve, so both are written as PolyLine annotations whose vertices run
along the curve, close enough together that it looks smooth at any zoom (within TOL of the
true curve), which every PDF viewer draws. The points that define the curve are kept with the
markup (annotations.py, KZProps geom "pts" / "bend"), so KanzonasPDF reads it back as an arc
or a bent line and its grips edit it. A bent arrow keeps its head: a PolyLine's line ending,
drawn along the last stretch of the curve, so it points along the curve.
"""

import math

import pymupdf

TOL = 0.01          # pt: the most the written vertices stray from the true curve
MAX_SEGMENTS = 720


def _pt(q):
    return q if isinstance(q, pymupdf.Point) else pymupdf.Point(q)


def circle_through(a, b, c):
    """(center, radius) of the circle through three points, or None when they (nearly) lie
    on one line."""
    a, b, c = _pt(a), _pt(b), _pt(c)
    d = 2 * (a.x * (b.y - c.y) + b.x * (c.y - a.y) + c.x * (a.y - b.y))
    span = max(abs(b - a), abs(c - a), abs(c - b))
    if span <= 1e-9 or abs(d) <= 1e-7 * span * span:
        return None
    sa, sb, sc = a.x * a.x + a.y * a.y, b.x * b.x + b.y * b.y, c.x * c.x + c.y * c.y
    ux = (sa * (b.y - c.y) + sb * (c.y - a.y) + sc * (a.y - b.y)) / d
    uy = (sa * (c.x - b.x) + sb * (a.x - c.x) + sc * (b.x - a.x)) / d
    center = pymupdf.Point(ux, uy)
    r = abs(a - center)
    if r > 1e6 * max(span, 1.0):            # (as good as straight)
        return None
    return center, r


def arc_sweep(a, m, c):
    """(center, radius, start angle, sweep) of the arc from a through m to c (radians, sweep
    signed), or None when the three points lie on one line."""
    got = circle_through(a, m, c)
    if got is None:
        return None
    center, r = got
    a, m, c = _pt(a), _pt(m), _pt(c)
    t0 = math.atan2(a.y - center.y, a.x - center.x)
    tm = math.atan2(m.y - center.y, m.x - center.x)
    t1 = math.atan2(c.y - center.y, c.x - center.x)
    two = 2 * math.pi
    s1 = (t1 - t0) % two
    sm = (tm - t0) % two
    sweep = s1 if sm <= s1 else s1 - two
    return center, r, t0, sweep


def _segments(span, step):
    if step <= 0:
        return MAX_SEGMENTS
    return max(4, min(MAX_SEGMENTS, int(math.ceil(span / step))))


def arc_path(a, m, c, tol=TOL):
    """Points along the arc from a through m to c (a and c exactly at its ends); the three
    points themselves when they lie on one line."""
    a, m, c = _pt(a), _pt(m), _pt(c)
    got = arc_sweep(a, m, c)
    if got is None:
        return [a, m, c]
    center, r, t0, sweep = got
    # a chord of angle s strays r * (1 - cos(s / 2)) from the circle
    step = 2 * math.acos(max(-1.0, 1 - tol / r)) if tol < r else math.pi / 2
    n = _segments(abs(sweep), step)
    pts = [pymupdf.Point(center.x + r * math.cos(t0 + sweep * k / n),
                         center.y + r * math.sin(t0 + sweep * k / n)) for k in range(1, n)]
    return [a] + pts + [c]


def bend_control(a, b, grip):
    """The control point of the quadratic curve from a to b whose middle (t = 0.5) is grip."""
    a, b, grip = _pt(a), _pt(b), _pt(grip)
    return pymupdf.Point(2 * grip.x - (a.x + b.x) / 2, 2 * grip.y - (a.y + b.y) / 2)


def bend_path(a, b, grip, tol=TOL):
    """Points along the curve from a to b bent through grip (a and b exactly at its ends)."""
    a, b = _pt(a), _pt(b)
    ctl = bend_control(a, b, grip)
    # a quadratic curve cut into n equal steps strays at most |a - 2 ctl + b| / (4 n^2)
    d = abs(pymupdf.Point(a.x - 2 * ctl.x + b.x, a.y - 2 * ctl.y + b.y))
    n = max(2, min(MAX_SEGMENTS, int(math.ceil(math.sqrt(d / (4 * tol)))))) if d > 0 else 1
    out = [a]
    for k in range(1, n):
        t = k / n
        u = 1 - t
        out.append(pymupdf.Point(u * u * a.x + 2 * u * t * ctl.x + t * t * b.x,
                                 u * u * a.y + 2 * u * t * ctl.y + t * t * b.y))
    out.append(b)
    return out


def seg_distance(p, a, b):
    """Distance from point p to the segment a-b."""
    p, a, b = _pt(p), _pt(a), _pt(b)
    dx, dy = b.x - a.x, b.y - a.y
    L = dx * dx + dy * dy
    t = 0 if L == 0 else max(0.0, min(1.0, ((p.x - a.x) * dx + (p.y - a.y) * dy) / L))
    return math.hypot(p.x - (a.x + t * dx), p.y - (a.y + t * dy))


def is_curved(model):
    """The markup is an arc or a bent line / arrow."""
    return model.get("kind") == "arc" or (model.get("kind") in ("line", "arrow") and
                                          model.get("bend") is not None)


def path(model, tol=TOL):
    """The line a point-based markup draws: along the curve for an arc or a bent line, else
    its points."""
    pts = model.get("points") or []
    if model.get("kind") == "arc" and len(pts) >= 3:
        return arc_path(pts[0], pts[1], pts[2], tol)
    if model.get("kind") in ("line", "arrow") and model.get("bend") is not None and \
            len(pts) >= 2:
        return bend_path(pts[0], pts[1], model["bend"], tol)
    return [_pt(q) for q in pts]


def grip(model):
    """Where a line's middle grip is: its bend point, or the middle of the straight line."""
    if model.get("bend") is not None:
        return _pt(model["bend"])
    a, b = model["points"][:2]
    return pymupdf.Point((a.x + b.x) / 2, (a.y + b.y) / 2)


def snap_points(model):
    """Where other drawing snaps to on a curved markup: its ends, its middle (the bend grip;
    an arc's point halfway along) and an arc's center."""
    pts = [_pt(q) for q in model["points"]]
    if model["kind"] == "arc" and len(pts) >= 3:
        out = [pts[0], pts[2], pts[1]]
        got = arc_sweep(pts[0], pts[1], pts[2])
        if got is not None:
            center, r, t0, sweep = got
            t = t0 + sweep / 2
            out += [pymupdf.Point(center.x + r * math.cos(t), center.y + r * math.sin(t)),
                    center]
        return out
    return pts[:2] + [grip(model)]
