"""Spaces (1.12, the owner, 11 Nov, from the Bluebeam comparison: Revu's Spaces): named
areas of a sheet (Room 101, Level 2, Zone A). A space is drawn with the Space tool like a
polygon (click each corner, double-click or Enter to finish) and named; it's a see-through
Polygon markup in the PDF, its name its text (other programs show it as a shape with that
comment), marked as a space in its KZProps (props "space").

Each markup on the page whose middle is inside a space is in that space (in the smallest
one, when spaces overlap): the Markups list shows it in its Space column and filters by it,
so counts, lengths and areas can be read space by space. The view writes each space's name
in it (on screen only).

Everything here reads the PDF's own keys (Rect, Vertices, Contents), in PDF coordinates,
without loading the markups: the Markups list calls it for every page it reads."""

import json
import re

import pymupdf

from .i18n import tr

_NUM = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")


def _nums(text):
    return [float(t) for t in _NUM.findall(text or "")]


def is_space(doc, xref):
    """Markup xref is a space (a Polygon marked as one)."""
    try:
        kind, val = doc.xref_get_key(xref, "KZProps")
    except Exception:
        return False
    if kind != "string" or '"space"' not in val:
        return False
    try:
        return bool(json.loads(val).get("props", {}).get("space"))
    except Exception:
        return False


def _name(doc, xref):
    try:
        kind, val = doc.xref_get_key(xref, "Contents")
    except Exception:
        return ""
    return (val or "").strip() if kind == "string" else ""


def area(pts):
    a = 0.0
    for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]):
        a += x0 * y1 - x1 * y0
    return abs(a) / 2


def inside(pts, x, y):
    """Point (x, y) is inside the polygon pts (even-odd)."""
    hit = False
    j = len(pts) - 1
    for i in range(len(pts)):
        xi, yi = pts[i]
        xj, yj = pts[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            hit = not hit
        j = i
    return hit


def on_page(doc, page):
    """[(xref, name, corners)] of the page's spaces, corners in PDF coordinates; the
    smallest first (a markup goes in the first one it's inside)."""
    out = []
    try:
        listed = page.annot_xrefs()
    except Exception:
        return out
    for x, typ, *_ in listed:
        if typ != pymupdf.PDF_ANNOT_POLYGON or not is_space(doc, x):
            continue
        try:
            kind, val = doc.xref_get_key(x, "Vertices")
        except Exception:
            continue
        n = _nums(val) if kind == "array" else []
        pts = list(zip(n[0::2], n[1::2]))
        if len(pts) >= 3:
            out.append((x, _name(doc, x) or tr("(unnamed space)"), pts))
    out.sort(key=lambda t: area(t[2]))
    return out


def middle(doc, xref):
    """The middle of markup xref's box, in PDF coordinates (None: no box)."""
    try:
        kind, val = doc.xref_get_key(xref, "Rect")
    except Exception:
        return None
    n = _nums(val) if kind == "array" else []
    if len(n) != 4:
        return None
    return (n[0] + n[2]) / 2, (n[1] + n[3]) / 2


def space_at(spaces, x, y):
    """The name of the (smallest) space point (x, y) is in, or ""."""
    for _xref, name, pts in spaces:
        if inside(pts, x, y):
            return name
    return ""


def of_markups(doc, page, xrefs):
    """{xref: the name of the space it's in} for the markups given (spaces themselves: in
    none); {} when the page has no spaces."""
    spaces = on_page(doc, page)
    if not spaces:
        return {}
    own = {s[0] for s in spaces}
    out = {}
    for x in xrefs:
        if x in own:
            continue
        m = middle(doc, x)
        if m is not None:
            name = space_at(spaces, *m)
            if name:
                out[x] = name
    return out


def labels(page):
    """[(name, middle as PyMuPDF page point, unrotated)] of the page's spaces shown now
    (not hidden, nor on a hidden layer), to write their names on screen."""
    from . import markup_layers
    doc = page.parent
    off = markup_layers.hidden(doc)
    to_mu = page.transformation_matrix
    out = []
    for x, name, pts in on_page(doc, page):
        try:
            flags = int(doc.xref_get_key(x, "F")[1] or 0)
        except (ValueError, TypeError):
            flags = 0
        if flags & pymupdf.PDF_ANNOT_IS_HIDDEN or markup_layers.layer_of(doc, x) in off:
            continue
        cx = sum(p[0] for p in pts) / len(pts)
        cy = sum(p[1] for p in pts) / len(pts)
        if not inside(pts, cx, cy):     # (an L-shaped room: a corner's middle instead)
            cx, cy = _point_inside(pts, cx, cy)
        out.append((name, pymupdf.Point(cx, cy) * to_mu))
    return out


def _point_inside(pts, cx, cy):
    """A point inside the polygon near (cx, cy): the middle of the widest piece of the
    level line through cy that lies inside."""
    xs = []
    j = len(pts) - 1
    for i in range(len(pts)):
        (xi, yi), (xj, yj) = pts[i], pts[j]
        if (yi > cy) != (yj > cy):
            xs.append((xj - xi) * (cy - yi) / (yj - yi) + xi)
        j = i
    xs.sort()
    pieces = [(xs[k], xs[k + 1]) for k in range(0, len(xs) - 1, 2)]
    if not pieces:
        return pts[0]
    a, b = max(pieces, key=lambda t: t[1] - t[0])
    return (a + b) / 2, cy


def next_name(doc):
    """"Space 1", "Space 2"...: the first not used in the document."""
    used = set()
    for i in range(doc.page_count):
        used |= {name for _x, name, _p in on_page(doc, doc[i])}
    n = 1
    while tr("Space {n}").format(n=n) in used:
        n += 1
    return tr("Space {n}").format(n=n)
