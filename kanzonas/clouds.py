"""Cloudy borders: an open cloud (a cloud with part of it trimmed away) drawn exactly as
MuPDF draws the cloudy border of a rectangle, ellipse or polygon, so the part that is left
looks unchanged.

PDF has a cloudy border only for closed shapes (Square, Circle, Polygon), so an open cloud
is a PolyLine annotation along the cloud's base line (where the closed shape's outline
was), with an appearance stream holding the arcs. Every PDF viewer shows that appearance;
one that draws the markup anew from its points shows a plain polyline there. What it takes
to draw the arcs again (after a move, turn, mirror, restyle or trim) is kept with the
markup (/KZProps, see annotations.py) as model["cloud"]:

    i      the cloud's intensity (2 for KanzonasPDF's clouds, as /BE /I)
    phase  one entry per point: for the first, how far past an arc's center the path starts,
           as a part of the spacing between arcs; for the others 0 when an arc is centered
           there (a rectangle's corners), else null (the arcs carry on round the corner,
           as on a polygon)
    ends   where the arcs just beyond each end were (the ones trimmed away), as
           [along, across] from the first arc's center and [along, across] from the last
           one's, in spacings, across = to the side the bumps are on: each end arc is the
           arc it was in the closed cloud
    flip   the bumps are on the other side (it was mirrored)

The arithmetic follows MuPDF's pdf-appearance.c (start_cloud, add_cloud_line, emit_cloud,
draw_arc, draw_arc_seg, end_cloud), which follows Acrobat's: arcs of one radius, centered on
points spaced along the outline, each from where it meets the circle before to where it
meets the one after, plus a short tail curling into the next.
"""
import math

import pymupdf

from . import pdfcoords

TAIL = math.pi / 8
EPS = 1e-6


def sizes(intensity, width):
    """(spacing between the arcs' centers, radius of the arcs), as MuPDF's start_cloud."""
    intensity = float(intensity or 0)
    width = float(width or 0)
    return intensity * 6.666667 + width * 0.8333333, intensity * 4.0 + width * 0.5


# ---- the centers ----------------------------------------------------------------
def _cum(verts):
    out = [0.0]
    for a, b in zip(verts, verts[1:]):
        out.append(out[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
    return out


def walk(verts, phases, spacing):
    """The arcs' centers along a path, as MuPDF's add_cloud_line places them:
    [(point, segment, position along the path)]. phases as model["cloud"]["phase"], in
    spacings (None: carry on from the segment before)."""
    out = []
    n = len(verts)
    if n < 2 or spacing <= EPS:
        return out
    pos = 0.0
    carry = 0.0
    for k in range(n - 1):
        ph = phases[k] if k < len(phases) else None
        if ph is None:
            ph = carry if k else 0.0
        else:
            ph = max(0.0, min(float(ph), 0.999999)) * spacing
        (x0, y0), (x1, y1) = verts[k], verts[k + 1]
        dx, dy = x1 - x0, y1 - y0
        total = math.hypot(dx, dy)
        used = 0.0
        if ph == 0:
            out.append(((x0, y0), k, pos))
        while total - used > spacing - ph:
            used += spacing - ph
            t = used / total
            out.append(((x0 + dx * t, y0 + dy * t), k, pos + used))
            ph = 0.0
        carry = ph + total - used
        pos += total
    if len(phases) >= n and phases[n - 1] is not None and float(phases[n - 1]) == 0:
        out.append((tuple(verts[-1]), n - 2, pos))
    return out


def _frame(verts, seg):
    """(along, across) unit vectors of a segment; across is to the left (y up), the side
    the bumps are on."""
    seg = max(0, min(seg, len(verts) - 2))
    (x0, y0), (x1, y1) = verts[seg], verts[seg + 1]
    d = math.hypot(x1 - x0, y1 - y0)
    ux, uy = ((x1 - x0) / d, (y1 - y0) / d) if d > EPS else (1.0, 0.0)
    return (ux, uy), (-uy, ux)


def _beyond(center, verts, off, spacing):
    (pt, seg, _pos) = center
    (ux, uy), (nx, ny) = _frame(verts, seg)
    a, c = off
    return (pt[0] + spacing * (a * ux + c * nx), pt[1] + spacing * (a * uy + c * ny))


def _offset(center, verts, p, spacing):
    (pt, seg, _pos) = center
    (ux, uy), (nx, ny) = _frame(verts, seg)
    dx, dy = p[0] - pt[0], p[1] - pt[1]
    return [round((dx * ux + dy * uy) / spacing, 6), round((dx * nx + dy * ny) / spacing, 6)]


# ---- the arcs (MuPDF's emit_cloud, draw_arc, draw_arc_seg) -----------------------
def _meet(p0, p1, r, sel):
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    d = math.hypot(dx, dy)
    if d >= r + r or d <= 0:
        return 0.0
    a = d / 2
    h = math.sqrt(r * r - a * a)
    x3 = (p0[0] + p1[0]) / 2 - h * dy / d
    y3 = (p0[1] + p1[1]) / 2 + h * dx / d
    if sel == 0:
        return math.atan2(y3 - p1[1], x3 - p1[0])
    return math.atan2(y3 - p0[1], x3 - p0[0])


def _arc_seg(out, r, xc, yc, th0, th1, move):
    x1, y1 = xc + r * math.cos(th0), yc + r * math.sin(th0)
    x4, y4 = xc + r * math.cos(th1), yc + r * math.sin(th1)
    ax, ay, bx, by = x1 - xc, y1 - yc, x4 - xc, y4 - yc
    q1 = ax * ax + ay * ay
    q2 = q1 + ax * bx + ay * by
    cross = ax * by - ay * bx
    if move:
        out.append(("m", (x1, y1)))
    if abs(cross) < 1e-12:
        return
    k2 = (4.0 / 3.0) * (math.sqrt(max(0.0, 2 * q1 * q2)) - q2) / cross
    out.append(("c", (xc + ax - k2 * ay, yc + ay + k2 * ax),
                (xc + bx + k2 * by, yc + by - k2 * bx), (x4, y4)))


def _arc(out, r, xc, yc, th0, th1, move):
    d = th0 - th1
    if d > math.pi / 4:
        _arc(out, r, xc, yc, th0, th0 - d / 2, move)
        _arc(out, r, xc, yc, th0 - d / 2, th1, False)
    else:
        _arc_seg(out, r, xc, yc, th0, th1, move)


def arcs(centers, before, after, r):
    """Path pieces ("m", p) / ("c", p1, p2, p3) of the arcs round centers (points), the
    first one meeting the circle at before, the last the one at after."""
    out = []
    pts = list(centers)
    for k, b in enumerate(pts):
        a = pts[k - 1] if k else before
        c = pts[k + 1] if k + 1 < len(pts) else after
        th0 = _meet(a, b, r, 0)
        th1 = _meet(b, c, r, 1)
        while th1 > th0:
            th1 -= math.pi * 2
        _arc(out, r, b[0], b[1], th0, th1, True)
        _arc_seg(out, r, b[0], b[1], th1, th1 - TAIL, False)
    return out


# ---- an open cloud, in drawing space -----------------------------------------------
# Drawing space: PDF user space (y up), mirrored left to right when the cloud is flipped,
# so the bumps are always to the left of the way the path goes.
def _to_space(page, flip):
    m = pdfcoords.to_pdf(page)
    if flip:
        m = m * pymupdf.Matrix(-1, 0, 0, 1, 0, 0)
    return m


def default_cloud(n):
    return {"i": 2, "phase": [0.0] + [None] * (n - 1), "ends": [-1.0, 0.0, 1.0, 0.0],
            "flip": False}


def cloud_of(model):
    """model["cloud"] with anything missing or not fitting the points filled in."""
    n = len(model.get("points") or [])
    c = dict(default_cloud(n))
    got = model.get("cloud")
    if isinstance(got, dict):
        try:
            c["i"] = float(got.get("i", 2)) or 2
        except (TypeError, ValueError):
            pass
        ph = got.get("phase")
        if isinstance(ph, list) and len(ph) == n and \
                all(p is None or isinstance(p, (int, float)) for p in ph):
            c["phase"] = list(ph)
        e = got.get("ends")
        if isinstance(e, list) and len(e) == 4 and all(isinstance(v, (int, float)) for v in e):
            c["ends"] = list(e)
        c["flip"] = bool(got.get("flip"))
    return c


def open_shape(page, model):
    """An open cloud model in drawing space: {"verts", "centers", "before", "after",
    "spacing", "radius", "flip", "i", "phase"}."""
    c = cloud_of(model)
    m = _to_space(page, c["flip"])
    verts = [tuple(pymupdf.Point(q) * m) for q in model["points"]]
    width = float(model["props"].get("width", 1) or 0)
    spacing, radius = sizes(c["i"], width)
    centers = walk(verts, c["phase"], spacing)
    out = {"verts": verts, "centers": centers, "spacing": spacing, "radius": radius,
           "flip": c["flip"], "i": c["i"], "phase": c["phase"], "closed": False,
           "before": None, "after": None}
    if centers:
        e = c["ends"]
        out["before"] = _beyond(centers[0], verts, e[0:2], spacing)
        out["after"] = _beyond(centers[-1], verts, e[2:4], spacing)
    return out


def appearance(page, annot, model):
    """Draw the open cloud's arcs as the PolyLine's appearance (its box grown to hold
    them). Call it last: a PyMuPDF setter after it (set_flags, set_info...) has MuPDF draw
    the plain polyline again."""
    doc = page.parent
    annot.update()                      # (a plain polyline, and nothing left to redo)
    stroke = model["props"].get("stroke")
    shape = open_shape(page, model)
    sign = -1.0 if shape["flip"] else 1.0
    pieces = arcs([c[0] for c in shape["centers"]], shape["before"], shape["after"],
                  shape["radius"]) if shape["centers"] and stroke else []
    xs, ys = [], []

    def put(p):
        x, y = sign * p[0], p[1]
        xs.append(x)
        ys.append(y)
        return f"{_n(x)} {_n(y)}"
    ops = []
    for pc in pieces:
        if pc[0] == "m":
            ops.append(put(pc[1]) + " m")
        else:
            ops.append(" ".join(put(p) for p in pc[1:]) + " c")
    ap = int(doc.xref_get_key(annot.xref, "AP/N")[1].split()[0])
    old = doc.xref_stream(ap).decode("latin-1").split("\n")
    head = []
    for ln in old:                      # opacity, width and color as MuPDF wrote them
        if ln.endswith((" m", " l", " re")) or ln in ("S", "s", "Q"):
            break
        head.append(ln)
    body = head + (["2 j"] + ops + ["S"] if ops else [])
    if head and head[0] == "q":
        body.append("Q")
    # its box: the arcs and the base line, with room for the line's width
    for q in model["points"]:
        p = pymupdf.Point(q) * pdfcoords.to_pdf(page)
        xs.append(p.x)
        ys.append(p.y)
    grow = float(model["props"].get("width", 1) or 0) + 1
    box = (min(xs) - grow, min(ys) - grow, max(xs) + grow, max(ys) + grow)
    rect = "[" + " ".join(_n(v) for v in box) + "]"
    doc.update_stream(ap, ("\n".join(body) + "\n").encode("latin-1"))
    doc.xref_set_key(ap, "BBox", rect)
    doc.xref_set_key(ap, "Matrix", "[1 0 0 1 0 0]")
    doc.xref_set_key(annot.xref, "Rect", rect)
    # the cloudy border, said as for a polygon (viewers draw the appearance; the hit test
    # and the Markups list read it)
    doc.xref_set_key(annot.xref, "BE", f"<</S/C/I {_n(shape['i'])}>>")


def _n(v):
    s = ("%.4f" % v).rstrip("0").rstrip(".")
    return "0" if s in ("", "-0") else s


# ---- a closed rectangle, ellipse or polygon, as MuPDF goes round it -----------------
def _numbers(doc, xref, key):
    kind, val = doc.xref_get_key(xref, key)
    if kind != "array":
        return None
    try:
        return [float(v) for v in val.strip("[]").split()]
    except ValueError:
        return None


def _winding(pts):
    """MuPDF's polygon_winding: True when it goes round the points in their order."""
    n = len(pts)
    min_x = min(p[0] for p in pts)
    mid_y = sum(p[1] for p in pts) / n
    area = 0.0
    q = pts[0]
    for r in pts[1:]:
        if (r[1] > mid_y > q[1]) or (r[1] < mid_y < q[1]):
            w = 1 if r[1] > mid_y else -1
            x = r[0] + (q[0] - r[0]) * (r[1] - mid_y) / (r[1] - q[1])
            area += (x - min_x) * w
        q = r
    return area < 0


def closed_shape(page, annot):
    """The outline of a rectangle, ellipse or polygon markup where its line is drawn, in
    PDF user space, going round as MuPDF's cloudy border does: {"verts" (the first point
    again at the end), "corners" (its points are corners: not an ellipse), "clouds" (the
    cloud intensity, 0 for none), "width"}; None for anything else."""
    doc = page.parent
    t = annot.type[0]
    border = annot.border or {}
    width = border.get("width", 1)
    width = 1.0 if width is None or width < 0 else float(width)
    clouds = float(border.get("clouds") or 0)
    clouds = clouds if clouds > 0 else 0
    if t in (pymupdf.PDF_ANNOT_SQUARE, pymupdf.PDF_ANNOT_CIRCLE):
        r = _numbers(doc, annot.xref, "Rect")
        if not r or len(r) != 4:
            r = list((pymupdf.Rect(annot.rect) * pdfcoords.to_pdf(page)).normalize())
        x0, y0, x1, y1 = min(r[0], r[2]), min(r[1], r[3]), max(r[0], r[2]), max(r[1], r[3])
        rd = _numbers(doc, annot.xref, "RD")
        rd = rd if rd and len(rd) == 4 else [0.0] * 4
        rd = [max(v, width / 2) for v in rd]
        x, y = x0 + rd[0], y0 + rd[1]
        w, h = max(1.0, x1 - x0 - rd[0] - rd[2]), max(1.0, y1 - y0 - rd[1] - rd[3])
        if t == pymupdf.PDF_ANNOT_SQUARE:
            verts = [(x, y), (x, y + h), (x + w, y + h), (x + w, y), (x, y)]
            return {"verts": verts, "phase": [0.0, 0.0, 0.0, 0.0, None], "corners": True,
                    "clouds": clouds, "width": width}
        cx, cy, rx, ry = x + w / 2, y + h / 2, w / 2, h / 2
        da = -math.pi * 2 / 32
        verts = [(cx + math.cos(i * da) * rx, cy + math.sin(i * da) * ry) for i in range(33)]
        return {"verts": verts, "phase": [0.0] + [None] * 32, "corners": False,
                "clouds": clouds, "width": width}
    if t == pymupdf.PDF_ANNOT_POLYGON:
        m = pdfcoords.to_pdf(page)
        pts = [tuple(pymupdf.Point(v) * m) for v in (annot.vertices or [])]
        if len(pts) < 2:
            return None
        if not _winding(pts):
            pts = pts[::-1]
        verts = pts + [pts[0]]
        return {"verts": verts, "phase": [0.0] + [None] * len(pts), "corners": True,
                "clouds": clouds, "width": width}
    return None


def closed_cloud(shape):
    """The arcs' centers of a closed cloud (closed_shape with clouds), in drawing space
    (PDF user space)."""
    spacing, radius = sizes(shape["clouds"], shape["width"])
    verts = shape["verts"]
    return {"verts": verts, "centers": walk(verts, shape["phase"], spacing),
            "spacing": spacing, "radius": radius, "flip": False, "i": shape["clouds"],
            "closed": True, "before": None, "after": None}


def closed_appearance(shape):
    """Path pieces of a closed cloud as MuPDF draws it (to compare with)."""
    c = closed_cloud(shape)
    pts = [x[0] for x in c["centers"]]
    if len(pts) < 2:
        return []
    return arcs(pts, pts[-1], pts[0], c["radius"])


# ---- a part of a cloud -----------------------------------------------------------------
def part(cloud, s0, s1):
    """The part of a cloud (closed_cloud or open_shape) from s0 to s1 along it (s0 < s1;
    round a closed one, s1 may pass its end), as an open cloud in drawing space:
    {"verts", "phase", "ends"}, or None when no arc's center is on it (nothing would show).
    Its arcs are the ones centered on that part, each drawn as it was."""
    verts = list(cloud["verts"])
    cum = _cum(verts)
    total = cum[-1]
    spacing = cloud["spacing"]
    eps = 1e-6 * max(1.0, total)
    centers = [(c[0], c[2]) for c in cloud["centers"]]
    if not centers or total <= EPS:
        return None
    if cloud["closed"]:
        # the way round twice over, and the centers a time round before and after
        nseg = len(verts) - 1
        path = [(verts[k % nseg] if k < 2 * nseg else verts[0], cum[k % nseg] + total * (k // nseg))
                for k in range(2 * nseg + 1)]
        ring = [(p, s + total * j) for j in (-1, 0, 1, 2) for p, s in centers]
        start_ph = None
    else:
        path = list(zip(verts, cum))
        ring = [(cloud["before"], -math.inf)] + centers + [(cloud["after"], math.inf)]
        ph0 = cloud["phase"][0] if cloud["phase"] else 0.0
        start_ph = -(float(ph0 or 0.0) * spacing)       # (an arc's center before the start)
    # the path's points from s0 to s1
    pts = [(_at(path, s0), s0)]
    for q, s in path:
        if s0 + eps < s < s1 - eps:
            pts.append((q, s))
    pts.append((_at(path, s1), s1))
    on = [(p, s) for p, s in ring if s0 - eps <= s <= s1 + eps]
    if not on:
        return None

    def center_at(s):
        return any(abs(c - s) <= eps for _p, c in ring)
    # how far past an arc's center the part starts
    back = [c for _p, c in ring if c <= s0 + eps]
    if start_ph is not None:
        back.append(start_ph)
    last = max(back) if back else s0
    first_ph = 0.0 if s0 - last <= eps else min((s0 - last) / spacing, 0.999999)
    phase = [round(first_ph, 6)] + [0.0 if center_at(s) else None for _q, s in pts[1:]]
    out = [q for q, _s in pts]
    # (a point twice over, as where a cut falls on a corner, goes)
    keep_v, keep_p = [out[0]], [phase[0]]
    for q, ph in zip(out[1:], phase[1:]):
        if math.hypot(q[0] - keep_v[-1][0], q[1] - keep_v[-1][1]) > eps:
            keep_v.append(q)
            keep_p.append(ph)
        elif ph == 0.0:
            keep_p[-1] = 0.0
    if len(keep_v) < 2:
        return None
    # the arcs beyond each end: the ones the part's first and last arcs met
    i0 = ring.index(on[0])
    i1 = ring.index(on[-1])
    before, after = ring[i0 - 1][0], ring[i1 + 1][0]
    mine = walk(keep_v, keep_p, spacing)
    if not mine:
        return None
    ends = _offset(mine[0], keep_v, before, spacing) + _offset(mine[-1], keep_v, after, spacing)
    return {"verts": keep_v, "phase": keep_p, "ends": ends}


def _at(path, s):
    """The point at s along path [(point, position)]."""
    for k in range(len(path) - 1):
        (a, sa), (b, sb) = path[k], path[k + 1]
        if sb >= s:
            t = 0.0 if sb - sa <= EPS else max(0.0, min(1.0, (s - sa) / (sb - sa)))
            return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
    return tuple(path[-1][0])


def part_model(page, model, cloud, s0, s1, sides):
    """An open cloud markup for the part from s0 to s1 of cloud (in drawing space), styled
    as model (the closed cloud or open cloud it is cut from); None if nothing would show."""
    got = part(cloud, s0, s1)
    if got is None:
        return None
    back = ~_to_space(page, cloud["flip"])
    from . import annotations
    props = dict(annotations.DEFAULTS["opencloud"])
    props.update({k: v for k, v in model["props"].items() if k in props})
    props["rotation"] = 0
    out = {"kind": "opencloud", "props": props, "text": model.get("text", ""),
           "author": model.get("author", ""), "created": model.get("created", ""),
           "locked": model.get("locked", False), "hidden": model.get("hidden", False),
           "points": [pymupdf.Point(q) * back for q in got["verts"]],
           "cloud": {"i": cloud["i"], "phase": got["phase"], "ends": got["ends"],
                     "flip": cloud["flip"]},
           "sides": bool(sides)}
    out["rect"] = annotations.bounds(out)
    return out
