"""Erase content (Bluebeam-style): permanently remove the page's own text, images and line
art inside a box. Lines that cross the box edge are cut at the edge, not removed whole (so a
wall running through the box keeps its outside parts), unlike plain redaction.

A filled shape that crosses the edge is painted again clipped to the outside of the box (its
outline stays in the file under the clip; only shapes entirely inside are removed). Fills made
with a pattern (hatches) or a gradient, which Shape can't draw, are put back by
erase_patterns.py from the page's content streams. Redrawn pieces are drawn on top of the
page, in their original color, width, dashes and layer.
"""

import pymupdf

CURVE_STEPS = 24        # straight pieces per Bezier curve when it has to be cut


def _bezier(p0, p1, p2, p3, n=CURVE_STEPS):
    pts = []
    for i in range(n + 1):
        t = i / n
        u = 1 - t
        pts.append(p0 * (u ** 3) + p1 * (3 * u * u * t) + p2 * (3 * u * t * t) + p3 * (t ** 3))
    return pts


def _segments(path):
    """The path's outline as straight segments [(a, b), ...]."""
    segs = []
    for it in path["items"]:
        op = it[0]
        if op == "l":
            segs.append((it[1], it[2]))
        elif op == "c":
            pts = _bezier(it[1], it[2], it[3], it[4])
            segs += list(zip(pts, pts[1:]))
        elif op == "re":
            r = it[1]
            q = [r.tl, r.tr, r.br, r.bl]
            segs += list(zip(q, q[1:] + q[:1]))
        elif op == "qu":
            q = it[1]
            pts = [q.ul, q.ur, q.lr, q.ll]
            segs += list(zip(pts, pts[1:] + pts[:1]))
    return segs


def _outside(a, b, box):
    """Parts of segment a-b outside the box: 0, 1 or 2 segments (Liang-Barsky clip)."""
    dx, dy = b.x - a.x, b.y - a.y
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, a.x - box.x0), (dx, box.x1 - a.x), (-dy, a.y - box.y0), (dy, box.y1 - a.y)):
        if p == 0:
            if q < 0:
                return [(a, b)]          # parallel and outside: the whole segment stays
            continue
        t = q / p
        if p < 0:
            t0 = max(t0, t)
        else:
            t1 = min(t1, t)
    if t0 >= t1:
        return [(a, b)]                  # doesn't enter the box
    out = []
    if t0 > 1e-6:
        out.append((a, a + (b - a) * t0))
    if t1 < 1 - 1e-6:
        out.append((a + (b - a) * t1, b))
    return out


def _bulk_lines(shape, pieces):
    """Append many line segments to a Shape at once (Shape.draw_line is too slow for CAD
    sheets with tens of thousands of lines)."""
    m = shape.ipctm
    out = []
    for a, b in pieces:
        p, q = a * m, b * m
        out.append(f"{p.x:.3f} {p.y:.3f} m {q.x:.3f} {q.y:.3f} l\n")
    shape.draw_cont += "".join(out)
    shape.updateRect(pieces[0][0])
    shape.lastPoint = pieces[-1][1]


def _clip_outside(shape, rect, box):
    """Content that clips the following path to everything outside `box` (even-odd clip of a
    rectangle around `rect` and the box), in the Shape's PDF coordinates."""
    o = (pymupdf.Rect(rect) + (-2, -2, 2, 2)) * shape.ipctm
    b = pymupdf.Rect(box) * shape.ipctm
    return (f"{o.x0:.3f} {o.y0:.3f} {o.width:.3f} {o.height:.3f} re "
            f"{b.x0:.3f} {b.y0:.3f} {b.width:.3f} {b.height:.3f} re W* n\n")


def _crosses(path, box):
    """A path (from get_drawings) crosses the edge of box: it isn't untouched, and isn't
    fully inside (the redaction removes those)."""
    r = pymupdf.Rect(path["rect"])
    w = (path.get("width") or 1) / 2 + 0.01     # a level line has a zero-height rect
    r = pymupdf.Rect(r.x0 - w, r.y0 - w, r.x1 + w, r.y1 + w)
    return r.intersects(box) and not box.contains(r)


def _drawings_near(page, box):
    """page.get_drawings(), but only the paths that may cross box (each is a superset of what
    _crosses takes, and comes exactly as get_drawings gives it).

    get_drawings makes a Point, Rect or Quad of every number MuPDF hands over: on a sheet with
    200,000 lines that took seconds, for the few dozen lines an erase box crosses. Here the
    paths are sorted out from MuPDF's plain numbers first (get_cdrawings, which get_drawings
    reads itself), and only those near the box are converted, by get_drawings' own code. The
    test left out is a strict part of Rect.intersects (each box overlaps the other's span):
    a path it rules out, _crosses rules out too."""
    bx0, by0, bx1, by1 = box.x0, box.y0, box.x1, box.y1
    near = []
    for path in page.get_cdrawings():
        rect = path.get("rect")
        if rect is None or len(rect) != 4:
            near.append(path)            # (something unexpected: let get_drawings say)
            continue
        w = (path.get("width") or 1) / 2 + 0.01
        if (rect[0] - w < bx1 and bx0 < rect[2] + w and rect[1] - w < by1 and
                by0 < rect[3] + w):
            near.append(path)
    # get_drawings converts what get_cdrawings gives: given just these
    page.get_cdrawings = lambda *args, **kwargs: near
    try:
        return page.get_drawings()
    finally:
        del page.get_cdrawings


def erase(page, box):
    """Remove everything of the page's own content inside `box` (unrotated page
    coordinates). Returns how many crossing shapes were redrawn. Annotations are untouched."""
    box = pymupdf.Rect(box).normalize()
    doc = page.parent
    try:
        from . import erase_patterns
        patterned = erase_patterns.find_crossing(page, box)
    except Exception:
        patterned = []                   # an odd content stream: hatches may still vanish
    ocgs = {v.get("name"): x for x, v in (doc.get_ocgs() or {}).items()}
    crossing = [path for path in _drawings_near(page, box) if _crosses(path, box)]
    page.add_redact_annot(box, fill=False)
    page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_PIXELS,
                          graphics=pymupdf.PDF_REDACT_LINE_ART_REMOVE_IF_TOUCHED,
                          text=pymupdf.PDF_REDACT_TEXT_REMOVE)
    redrawn = 0
    shape = page.new_shape()             # one shape, committed once: fast with many paths
    for path in crossing:
        filled = path.get("fill") is not None and path.get("type") in ("f", "fs")
        kw = {"width": path.get("width") or 1, "color": path.get("color"),
              "dashes": path.get("dashes") or None,
              "stroke_opacity": path.get("stroke_opacity") or 1,
              "lineCap": max(path.get("lineCap") or (0,)),
              "lineJoin": path.get("lineJoin") or 0, "closePath": False}
        oc = ocgs.get(path.get("layer")) if path.get("layer") else None
        if oc:
            kw["oc"] = oc
        if filled:
            # a fill can't be cut like a line: put the whole shape back, clipped to the
            # outside of the box
            shape.draw_cont = _clip_outside(shape, path["rect"], box)
            for it in path["items"]:
                op = it[0]
                if op == "l":
                    shape.draw_line(it[1], it[2])
                elif op == "c":
                    shape.draw_bezier(it[1], it[2], it[3], it[4])
                elif op == "re":
                    shape.draw_rect(it[1])
                elif op == "qu":
                    shape.draw_quad(it[1])
            if path.get("type") == "f":
                kw["color"] = None          # fill only: no outline
                kw["width"] = 0
            shape.finish(fill=path.get("fill"), fill_opacity=path.get("fill_opacity") or 1,
                         even_odd=path.get("even_odd", False), **kw)
        else:
            if path.get("color") is None:
                continue
            pieces = [s for a, b in _segments(path) for s in _outside(a, b, box)]
            if not pieces:
                continue
            _bulk_lines(shape, pieces)
            shape.finish(**kw)
        redrawn += 1
    if redrawn:
        shape.commit()
    if patterned:
        try:
            redrawn += erase_patterns.repaint(page, patterned, box)
        except Exception:
            pass                         # the erase itself is done; the hatch is lost
    return redrawn
