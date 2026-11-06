"""Dimension markups (Bluebeam's Dimension, AutoCAD's DIMALIGNED): two extension lines from
the measured points, a dimension line between them with arrowheads, and the measured length
centered above it, in the page's scale and unit (as Length measures).

A dimension's model keeps three points (page coordinates): the two measured points and a
third on the dimension line, halfway along it (normalized() puts it there; moving it moves
the dimension line nearer or farther). It's written as a standard PDF Line annotation with
what other PDF viewers read as a dimension: leader lines (/LL /LLE, the extension lines),
the caption shown above the line (/Cap /CP, the text in /Contents), the intent
/IT /LineDimension and a /Measure dictionary with the page's scale. Its picture (the
appearance stream) is drawn here, as MuPDF's own draws the caption black at 12 pt and
doesn't turn it upright on a turned page; the label is measure.add_label's.

Leader lines: MuPDF draws a positive /LL to the left of the line from its first point to its
second (in PDF space, y up), as Acrobat does; in page coordinates (y down) that is n below.
"""

import math

import pymupdf

from . import pdfcoords

EXT = 3.0               # pt: the extension lines run this far past the dimension line (/LLE)
# arrowhead styles (Properties > Arrowhead), and the PDF line ending other viewers draw
HEADS = ("closed", "open", "slash", "dot", "none")
PDF_ENDS = {"closed": "ClosedArrow", "open": "OpenArrow", "slash": "Slash", "dot": "Circle",
            "none": "None"}


def _pt(q):
    return pymupdf.Point(q[0], q[1])


def geometry(points):
    """(a, b, a2, b2, n, d): the measured points a and b, the dimension line's ends a2 and b2,
    the unit normal n it is moved along (page coordinates) and how far (d, signed: /LL)."""
    a, b = _pt(points[0]), _pt(points[1])
    c = _pt(points[2]) if len(points) > 2 else (a + b) / 2
    u = b - a
    length = abs(u)
    n = pymupdf.Point(u.y / length, -u.x / length) if length > 1e-9 else pymupdf.Point(0, -1)
    d = (c.x - a.x) * n.x + (c.y - a.y) * n.y
    return a, b, a + n * d, b + n * d, n, d


def normalized(points):
    """The three points with the third moved to the middle of the dimension line (only how
    far it is from the measured points counts)."""
    a, b, a2, b2, _n, _d = geometry(points)
    return [a, b, (a2 + b2) / 2]


def path(points):
    """The dimension's outline as one line: first point, along its extension line, the
    dimension line, back down the other extension line."""
    a, b, a2, b2, _n, _d = geometry(points)
    return [a, a2, b2, b]


def from_leader(a, b, ll):
    """The three points of a dimension written with /L a b and /LL ll (page coordinates)."""
    a, b = _pt(a), _pt(b)
    u = b - a
    length = abs(u)
    n = pymupdf.Point(u.y / length, -u.x / length) if length > 1e-9 else pymupdf.Point(0, -1)
    return [a, b, (a + b) / 2 + n * float(ll)]


def leader(annot):
    """A Line annotation's /LL (0 when it has none): a dimension's extension lines."""
    try:
        doc = annot.parent.parent
        typ, val = doc.xref_get_key(annot.xref, "LL")
        return float(val) if typ in ("int", "float", "real") else 0.0
    except Exception:
        return 0.0


def hit(pt, verts, ll, tol, seg_dist):
    """A press at pt is on the dimension drawn from /L verts with /LL ll: near one of its
    lines, or on its label (above the middle of the dimension line)."""
    if len(verts) < 2:
        return False
    pts = path(from_leader(verts[0], verts[1], ll))
    if any(seg_dist(pt, pts[k], pts[k + 1]) <= tol for k in range(3)):
        return True
    a2, b2 = pts[1], pts[2]
    u = b2 - a2
    length = abs(u)
    if length < 1e-9:
        return False
    along = ((pt.x - a2.x) * u.x + (pt.y - a2.y) * u.y) / length
    across = abs((pt.x - a2.x) * u.y - (pt.y - a2.y) * u.x) / length
    return abs(along - length / 2) <= max(length / 4, 12) and across <= tol + 14


def head_size(width):
    """An arrowhead's length (pt) for a line width."""
    return 5.0 + 2.0 * max(0.0, float(width or 0))


def label_place(points, page, size, width):
    """(anchor, angle) for the measured length: centered above the dimension line, reading
    upright on screen (also on turned pages), as measure.label_anchor gives them."""
    rot = page.rotation
    _a, _b, a2, b2, _n, _d = geometry(points)
    s, e = a2 * page.rotation_matrix, b2 * page.rotation_matrix     # as seen on screen
    ang = math.degrees(math.atan2(-(e.y - s.y), e.x - s.x))
    if ang > 90.001:            # (a vertical one reads from the bottom up, as in CAD)
        ang -= 180
    elif ang < -89.999:
        ang += 180
    r = math.radians(ang)
    up = pymupdf.Point(-math.sin(r), -math.cos(r))                  # the text's up, on screen
    lift = size * 0.6 + 1 + max(0.0, float(width or 0)) / 2 + 1.5
    anchor = (s + e) / 2 + up * lift
    return anchor * page.derotation_matrix, ang + rot


def measure_dict(page):
    """The /Measure dictionary for the page's scale (PDF 32000 12.9: a rectilinear
    measure), so other programs that measure read the same scale."""
    from . import measure
    f, unit, label, ok = measure.get_scale(page)
    if not ok:
        label = "1 in = 1 in"
    base = "ft" if unit == "ft-in" else unit
    per_pt = f / measure.UNITS[base]                    # display units per PDF point
    digits = measure.DECIMALS if measure.DECIMALS is not None else (0 if unit == "mm" else 2)
    if unit == "ft-in":
        x = ("[<</Type/NumberFormat/U(ft)/C %s/D 1/F/T>>"
             "<</Type/NumberFormat/U(in)/C 12/D %d/F/F>>]") % (
                 _num(per_pt), measure.FRACTION)
    else:
        x = "[<</Type/NumberFormat/U%s/C %s/D %d/F/D>>]" % (
            pymupdf.get_pdf_str(base), _num(per_pt), 10 ** digits)
    area = "[<</Type/NumberFormat/U%s/C %s/D 100/F/D>>]" % (
        pymupdf.get_pdf_str("sq " + base), _num(per_pt * per_pt))
    return "<</Type/Measure/Subtype/RL/R%s/X%s/D%s/A%s>>" % (
        pymupdf.get_pdf_str(label), x, x, area)


def _num(v):
    s = ("%.10f" % v).rstrip("0").rstrip(".")
    return s or "0"


def finish(page, annot, model):
    """After the Line annotation is written (write): the keys that make it a dimension for
    other PDF viewers, and its picture drawn anew (the label is added after this)."""
    doc = page.parent
    x = annot.xref
    p = model["props"]
    to_pdf = pdfcoords.to_pdf(page)
    a, b, a2, b2, n, d = geometry(model["points"])
    A, B, A2, B2 = (q * to_pdf for q in (a, b, a2, b2))
    head = p.get("head") if p.get("head") in HEADS else "closed"
    doc.xref_set_key(x, "LL", _num(round(d, 4)))
    doc.xref_set_key(x, "LLE", _num(EXT))
    doc.xref_set_key(x, "Cap", "true")
    doc.xref_set_key(x, "CP", "/Top")
    doc.xref_set_key(x, "IT", "/LineDimension")
    doc.xref_set_key(x, "LE", "[/%s/%s]" % (PDF_ENDS[head], PDF_ENDS[head]))
    doc.xref_set_key(x, "Measure", measure_dict(page))
    typ, val = doc.xref_get_key(x, "AP/N")
    if typ != "xref":
        return
    ap = int(val.split()[0])
    old = doc.xref_stream(ap).decode("latin-1", "replace").split("\n")
    from . import annotations
    color = annotations.to_rgb(p.get("stroke")) or (0, 0, 0)
    width = max(0.0, float(p.get("width", 1) or 0))
    rgb = " ".join("%g" % c for c in color)
    ops = [ln for ln in old if ln.strip().endswith(" gs")]      # (its opacity)
    ops += ["%g w" % width, "0 J", "0 j", rgb + " RG", rgb + " rg"]
    box = []

    def line(p0, p1):
        ops.append("%.3f %.3f m %.3f %.3f l S" % (p0.x, p0.y, p1.x, p1.y))
        box.extend((p0, p1))

    # the extension lines, from the measured points to a little past the dimension line
    out = A2 - A
    if abs(out) > 1e-6:
        e = out / abs(out) * EXT
        line(A, A2 + e)
        line(B, B2 + e)
    # the dimension line and its heads (outside the extension lines when it's too short for
    # them inside, as CAD programs draw them)
    s = head_size(width)
    u = B2 - A2
    length = abs(u)
    t = u / length if length > 1e-9 else pymupdf.Point(1, 0)
    m = pymupdf.Point(-t.y, t.x)
    inside = head in ("slash", "dot", "none") or length >= 3 * s
    if inside:
        line(A2, B2)
    else:
        line(A2 - t * (s + 2), B2 + t * (s + 2))
    for tip, k in ((A2, 1), (B2, -1)):
        into = t * k if inside else t * -k              # from the tip along the head
        if head in ("closed", "open"):
            p1 = tip + into * s + m * (s / 3)
            p2 = tip + into * s - m * (s / 3)
            if head == "closed":
                ops.append("%.3f %.3f m %.3f %.3f l %.3f %.3f l h f" % (
                    tip.x, tip.y, p1.x, p1.y, p2.x, p2.y))
            else:
                ops.append("%.3f %.3f m %.3f %.3f l %.3f %.3f l S" % (
                    p1.x, p1.y, tip.x, tip.y, p2.x, p2.y))
            box.extend((tip, p1, p2))
        elif head == "slash":
            v = (t + m) * (s / 2 / math.sqrt(2))
            ops.append("q %g w %.3f %.3f m %.3f %.3f l S Q" % (
                max(width * 1.5, 0.5), tip.x - v.x, tip.y - v.y, tip.x + v.x, tip.y + v.y))
            box.extend((tip - v, tip + v))
        elif head == "dot":
            r = s / 4
            k_ = 0.5523 * r
            cx, cy = tip.x, tip.y
            ops.append(
                "%.3f %.3f m %.3f %.3f %.3f %.3f %.3f %.3f c %.3f %.3f %.3f %.3f %.3f %.3f c "
                "%.3f %.3f %.3f %.3f %.3f %.3f c %.3f %.3f %.3f %.3f %.3f %.3f c f" % (
                    cx + r, cy, cx + r, cy + k_, cx + k_, cy + r, cx, cy + r,
                    cx - k_, cy + r, cx - r, cy + k_, cx - r, cy,
                    cx - r, cy - k_, cx - k_, cy - r, cx, cy - r,
                    cx + k_, cy - r, cx + r, cy - k_, cx + r, cy))
            box.extend((tip - (r, r), tip + (r, r)))
    doc.update_stream(ap, ("\n".join(ops) + "\n").encode("latin-1"))
    r = pymupdf.Rect(box[0], box[0]) if box else pymupdf.Rect(A, A)
    for q in box[1:]:
        r |= q
    r |= A
    r |= B
    pad = width / 2 + 1
    r = pymupdf.Rect(r.x0 - pad, r.y0 - pad, r.x1 + pad, r.y1 + pad)
    arr = "[%.3f %.3f %.3f %.3f]" % (r.x0, r.y0, r.x1, r.y1)
    doc.xref_set_key(ap, "BBox", arr)
    doc.xref_set_key(ap, "Matrix", "[1 0 0 1 0 0]")
    doc.xref_set_key(x, "Rect", arr)
