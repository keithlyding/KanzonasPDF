"""The Drawing tab (1.17, the owner, 23 Nov 2026): lines, arrows, polylines, polygons,
rectangles, ellipses, circles, arcs, clouds and the pen drawn into the page itself, as vector
drawing in its content stream, not as markups (annotations). "Convert to drawing" turns a
shape markup already on the page into the same kind of drawing.

All of it goes on one layer of its own, the PDF optional content group LAYER, so the Layers
panel shows and hides it, and other PDF programs that show layers do too. On the page it is
ordinary content, read back by page_objects.Objects like the drawing's own lines: Edit objects
selects, moves, restyles, groups and reorders it as it does them. What tells it apart from
markups: the Drawing tab, the layer, the selection color Edit objects shows it in
(page_widget.DRAWING_SELECTED) and Properties' "Page content" tag.

How it is written: each shape is

    q
    <line color> <fill color> <width> <dash>      (RG rg w d, as page_objects.recolor writes)
    [/KZHeads <<...>> DP]                            (a line's arrowheads, page_objects.heads_of)
    <its path> <S, f or B>
    Q

so Properties' colors, Line style, Line width and arrowheads change it in place, as they do a
drawing line restyled before; transparency and the pen's round ends are set in a q ... Q
around that. Shapes are written in the page's PDF space, after everything else on the page:
the page's own instructions are put in a q ... Q of their own first when they leave a
transformation or a style set at their end. All shapes of one page share one content stream
of their own, /OC /<name> BDC ... EMC (the layer under a name in the page's /Properties),
added to at each new shape until it is big (STREAM_LIMIT).

A cloud's scallops, and a markup converted, are written as the markup's appearance stream
draws them (the markup's own look exactly: page_objects._expand without its clip), its
resources added to the page's under new names.

Every change runs inside DocumentView.modify: one undo step per shape or per conversion.
"""

import math
import re

import pymupdf

from . import annotations as A
from . import page_objects as po
from . import pdfcoords

LAYER = "KanzonasPDF drawing"
STREAM_KEY = "KZDrawing"            # on the drawing's own content stream: the page's xref
STREAM_LIMIT = 256_000              # bytes: a new stream after this (each edit rewrites it)
PROP_NAME = "KZDraw"                # the layer's name in a page's /Properties
# the Drawing tab's tools (main_window's tool ids) and the markup tool whose clicks, previews
# and snapping each one uses (page_widget, cad_draw: they see the markup tool's id)
TOOLS = {"d_line": "line", "d_arrow": "arrow", "d_polyline": "polyline", "d_polygon": "polygon",
         "d_rect": "rect", "d_ellipse": "ellipse", "d_circle": "circle", "d_arc": "arc",
         "d_cloud": "cloud", "d_ink": "ink"}
# markups that Convert to drawing turns into page drawing (shapes and lines; measurements,
# notes, stamps, text and highlights stay markups)
CONVERTIBLE = ("rect", "ellipse", "polygon", "polyline", "line", "arrow", "arc", "ink",
               "opencloud")
KAPPA = 0.5522847498                # a quarter circle's Bezier handles, in radii
_OC_BDC = re.compile(rb"^/OC\s*/([^\s/\[\]()<>{}%]+)\s*BDC$")


def base_tool(tool):
    """The markup tool a Drawing tool draws like, or None for any other tool."""
    return TOOLS.get(tool)


def makes(tool, model):
    """Whether model is what Drawing tool tool draws (as its markup tool would make it)."""
    kind = {"circle": "ellipse", "cloud": "rect"}.get(TOOLS.get(tool), TOOLS.get(tool))
    return kind is not None and model.get("kind") == kind


def draws(model):
    """Whether a Drawing tool's shape draws anything: a line color, or a fill on a shape
    that has one."""
    p = model.get("props") or {}
    return bool(p.get("stroke")) or bool(p.get("fill")) and \
        model.get("kind") in ("rect", "ellipse", "polygon")


def convertible(model):
    """Whether Convert to drawing takes this markup (a model from annotations.read)."""
    return model is not None and model.get("kind") in CONVERTIBLE and \
        not model["props"].get("space") and not model.get("locked")


# ---- the layer ----------------------------------------------------------------------------
def layer_xref(doc, create=False):
    """The drawing layer (its OCG xref): the one named LAYER, made (shown) when create is set
    and there's none; else None."""
    try:
        found = doc.get_ocgs() or {}
    except Exception:
        found = {}
    for x, o in sorted(found.items()):
        if o.get("name") == LAYER:
            return x
    if not create:
        return None
    from . import markup_layers
    return markup_layers.new_layer(doc, LAYER)


def _names_for(doc, page, ocg):
    """The names page's /Properties gives layer ocg."""
    want = "%d 0 R" % ocg
    return [k for k, (kind, val) in po._res_entries(doc, page.xref, "Resources/Properties").items()
            if kind == "xref" and val == want]


def _prop_name(page, ocg):
    """The layer's name in the page's /Properties (added when it has none). Bytes."""
    doc = page.parent
    po._own_resources(page)
    have = _names_for(doc, page, ocg)
    if have:
        return have[0].encode("latin-1")
    taken = set(po._res_entries(doc, page.xref, "Resources/Properties"))
    name, k = PROP_NAME, 1
    while name in taken:
        k += 1
        name = "%s%d" % (PROP_NAME, k)
    po._set_resource(doc, page.xref, "Properties", name, "%d 0 R" % ocg)
    return name.encode("latin-1")


def layer_names(page):
    """The names (bytes) the page's content uses for the drawing layer: an object in
    /OC /<one of them> BDC is page drawing."""
    doc = page.parent
    ocg = layer_xref(doc)
    if ocg is None:
        return frozenset()
    return frozenset(n.encode("latin-1") for n in _names_for(doc, page, ocg))


def on_layer(ctx, names):
    """Whether an Objects entry's "ctx" puts it on the drawing layer (names: layer_names)."""
    if not names or not ctx:
        return False
    for bdc in ctx[0]:
        mo = _OC_BDC.match(bdc.strip())
        if mo and mo.group(1) in names:
            return True
    return False


# ---- writing ------------------------------------------------------------------------------
_TOP = re.compile(rb"[(%]|(?:(?<=[\s\]\)>}])|^)(q|Q|cm|w|J|j|M|d|ri|i|gs|CS|cs|SC|SCN|sc|scn|"
                  rb"G|g|RG|rg|K|k|BI|BX)(?=[\s\[\]()<>{}/%]|$)")


def _left_set(data):
    """Whether the page's instructions leave something set at their end (outside any q ...
    Q): a transformation, a color, a line style, transparency. A literal string, an inline
    picture or a BX compatibility section is taken as a yes (not worth reading through)."""
    depth, i, n = 0, 0, len(data)
    search = _TOP.search
    while i < n:
        mo = search(data, i)
        if mo is None:
            return False
        tok = mo.group()
        i = mo.end()
        if tok == b"(":
            i = po._skip_string(data, mo.start())
            continue
        if tok == b"%":
            k = data.find(b"\n", i)
            i = n if k < 0 else k
            continue
        if tok == b"q":
            depth += 1
        elif tok == b"Q":
            depth -= 1
            if depth < 0:
                return True
        elif tok in (b"BI", b"BX"):
            if depth == 0:
                return True
            # (an inline picture's data can hold anything: read past it as the scan does)
            if tok == b"BI":
                k = data.find(b"ID", i)
                if k < 0:
                    return True
                i = po._inline_end(data, k + 3)
        elif depth == 0:
            return True
    return depth != 0


def _own_last_stream(page):
    """The page's last content stream when it is the drawing's own, written for this page
    and shown by no other page; else None."""
    doc = page.parent
    conts = page.get_contents()
    if not conts:
        return None
    x = conts[-1]
    if doc.xref_get_key(x, STREAM_KEY) != ("int", str(page.xref)):
        return None
    for i in range(doc.page_count):
        px = doc.page_xref(i)
        if px != page.xref and re.search(r"\b%d 0 R" % x, doc.xref_get_key(px, "Contents")[1]):
            return None                 # (shared, as a copied page can be)
    return x


def _append(page, pieces):
    """Draw pieces (each a shape's instructions, in PDF space) on the page, after everything
    on it, on the drawing layer."""
    doc = page.parent
    ocg = layer_xref(doc, create=True)
    name = _prop_name(page, ocg)
    head = b"/OC /" + name + b" BDC\n"
    from . import tag_upkeep
    if tag_upkeep.is_tagged(doc):
        # (a tagged page: each shape an artifact, as tag_upkeep marks the page's other new
        # lines, but around its own q ... Q, which stays as Properties rewrites it)
        pieces = [b"/Artifact BMC\n" + p + b"EMC\n" for p in pieces]
    body = b"".join(pieces)
    x = _own_last_stream(page)
    if x is not None:
        data = doc.xref_stream(x) or b""
        if data.startswith(head) and data.endswith(b"EMC\n") and len(data) < STREAM_LIMIT:
            new = data[:-4] + body + b"EMC\n"
            po._put_stream(doc, x, new)
            return
    page.wrap_contents()                # (q and Q balanced)
    if _left_set(po._contents(page)):
        pymupdf.TOOLS._insert_contents(page, b"q\n", False)
        pymupdf.TOOLS._insert_contents(page, b"\nQ\n", True)
    x = pymupdf.TOOLS._insert_contents(page, b" ", True)
    data = head + body + b"EMC\n"
    po._put_stream(doc, x, data)
    doc.xref_set_key(x, STREAM_KEY, str(page.xref))


def _fmt(v):
    s = b"%.3f" % v
    s = s.rstrip(b"0").rstrip(b".") if b"." in s else s
    return b"0" if s in (b"-0", b"") else s


def _xy(p):
    return _fmt(p.x) + b" " + _fmt(p.y)


def _alpha_gs(page, stroke_a, fill_a):
    """The name of an ExtGState of the page with these opacities (added when it has none)."""
    doc = page.parent
    po._own_resources(page)
    name = "KZDrawA%d_%d" % (round(stroke_a * 1000), round(fill_a * 1000))
    have = po._res_entries(doc, page.xref, "Resources/ExtGState")
    if name not in have:
        po._set_resource(doc, page.xref, "ExtGState", name,
                         "<</Type/ExtGState/CA %g/ca %g>>" % (stroke_a, fill_a))
    return name.encode("latin-1")


def _ellipse_path(c, rx, ry):
    """An ellipse (center c, radii rx, ry, in PDF space) as four Bezier curves."""
    kx, ky = rx * KAPPA, ry * KAPPA
    x, y = c.x, c.y
    P = pymupdf.Point
    pts = [P(x + rx, y),
           P(x + rx, y + ky), P(x + kx, y + ry), P(x, y + ry),
           P(x - kx, y + ry), P(x - rx, y + ky), P(x - rx, y),
           P(x - rx, y - ky), P(x - kx, y - ry), P(x, y - ry),
           P(x + kx, y - ry), P(x + rx, y - ky), P(x + rx, y)]
    out = [_xy(pts[0]) + b" m"]
    for k in range(1, 13, 3):
        out.append(b" ".join(_xy(q) for q in pts[k:k + 3]) + b" c")
    return b" ".join(out) + b" h"


def _arc_path(a, m, c, mat):
    """An arc from a through m to c (page points) as Bezier curves in PDF space (mat: to it);
    a polyline through the three when they lie on one line."""
    from . import curves
    got = curves.arc_sweep(a, m, c)
    if got is None:
        pts = [pymupdf.Point(q) * mat for q in (a, m, c)]
        return _xy(pts[0]) + b" m " + b" ".join(_xy(q) + b" l" for q in pts[1:])
    center, r, t0, sweep = got
    n = max(1, int(math.ceil(abs(sweep) / (math.pi / 2) - 1e-9)))
    step = sweep / n
    k = 4.0 / 3.0 * math.tan(step / 4)
    P = pymupdf.Point
    start = P(a) * mat
    out = [_xy(start) + b" m"]
    for i in range(n):
        u0, u1 = t0 + step * i, t0 + step * (i + 1)
        p0 = P(center.x + r * math.cos(u0), center.y + r * math.sin(u0))
        p3 = P(center.x + r * math.cos(u1), center.y + r * math.sin(u1))
        p1 = p0 + P(-math.sin(u0), math.cos(u0)) * (k * r)
        p2 = p3 - P(-math.sin(u1), math.cos(u1)) * (k * r)
        if i == n - 1:
            p3 = P(c)
        out.append(b" ".join(_xy(q * mat) for q in (p1, p2, p3)) + b" c")
    return b" ".join(out)


def _poly_path(pts, mat, closed=False):
    pts = [pymupdf.Point(q) * mat for q in pts]
    out = [_xy(pts[0]) + b" m"] + [_xy(q) + b" l" for q in pts[1:]]
    return b" ".join(out) + (b" h" if closed else b"")


def _rgb(hex_color):
    return A.to_rgb(hex_color) if hex_color else None


def shape_piece(page, model):
    """The instructions drawing model (a markup model made by a tool: a line, arrow,
    polyline, arc, polygon, rectangle, ellipse or pen stroke, upright) as page drawing, or
    None when it draws nothing (no line color and no fill)."""
    kind, p = model["kind"], model["props"]
    mat = pdfcoords.to_pdf(page)
    stroke = _rgb(p.get("stroke"))
    fill = _rgb(p.get("fill")) if kind in ("rect", "ellipse", "polygon") else None
    width = max(0.0, float(p.get("width", 1.0) or 0.0))
    if stroke is None and fill is None:
        return None
    lines = kind in A.LINE_KINDS
    if kind == "rect":
        r = (pymupdf.Rect(model["rect"]) * mat).normalize()
        path = b"%s %s %s %s re" % (_fmt(r.x0), _fmt(r.y0), _fmt(r.width), _fmt(r.height))
    elif kind == "ellipse":
        r = (pymupdf.Rect(model["rect"]) * mat).normalize()
        path = _ellipse_path(pymupdf.Point((r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2),
                             r.width / 2, r.height / 2)
    elif kind == "polygon":
        path = _poly_path(model["points"], mat, closed=True)
    elif kind == "arc":
        a, m, c = model["points"][:3]
        path = _arc_path(a, m, c, mat)
    elif kind in ("line", "arrow", "polyline"):
        from . import curves
        path = _poly_path(curves.path(model), mat)
    elif kind == "ink":
        path = b" ".join(_poly_path(s, mat) for s in model.get("strokes") or () if len(s) > 1)
        if not path:
            return None
    else:
        raise ValueError("not a drawing shape: " + kind)
    paint = b"B" if stroke and fill else b"S" if stroke else b"f"
    ops = []
    if stroke is not None:
        ops.append(po._rgb_op(stroke, b"RG"))
    if fill is not None:
        ops.append(po._rgb_op(fill, b"rg"))
    if stroke is not None:
        ops.append(b"%.4f w" % width)
        ops.append(po._dash_op(p.get("dash") or "solid", width) if kind != "ink" else b"[] 0 d")
    body = path + b" " + paint
    marker = b""
    heads = (p.get("head_start") or "none", p.get("head") or "none", p.get("mid") or "none")
    if lines and stroke is not None and any(h in ("open", "closed") for h in heads):
        heads = tuple(h if h in po.HEAD_KINDS else "none" for h in heads)
        first = po._first_dash(b"", po._dash_op(p.get("dash") or "solid", width))
        length = max(6.0, 3.0 * width + 3.0)
        body, count = po._with_heads(body, heads, 0, length, first * 0.9 if first else None)
        if count:
            marker = b"/KZHeads <</S/%s/E/%s/M/%s/N %d>> DP\n" % (
                heads[0].encode(), heads[1].encode(), heads[2].encode(), count)
    piece = b"q\n" + b" ".join(ops) + b"\n" + marker + body + b"\nQ\n"
    outer = []
    opacity = min(1.0, max(0.0, float(p.get("opacity", 1.0))))
    fill_opacity = min(1.0, max(0.0, float(p.get("fill_opacity", 1.0)))) * opacity
    if opacity < 1 or (fill is not None and fill_opacity < 1):
        outer.append(b"/" + _alpha_gs(page, opacity, fill_opacity) + b" gs")
    if kind == "ink":
        outer.append(b"1 J 1 j")        # (round ends and corners, as the Pen markup's)
    if outer:
        piece = b"q " + b" ".join(outer) + b"\n" + piece + b"Q\n"
    return piece


def appearance_piece(page, xref, taken):
    """The instructions drawing markup xref exactly as its appearance stream does, in the
    page's PDF space (its resources added to the page's: taken, page_objects._expand), or
    None when it has none to draw (hidden, or no appearance)."""
    doc = page.parent
    flags = doc.xref_get_key(xref, "F")
    try:
        f = int(flags[1]) if flags[0] == "int" else 0
    except ValueError:
        f = 0
    if f & (pymupdf.PDF_ANNOT_IS_HIDDEN | pymupdf.PDF_ANNOT_IS_NO_VIEW):
        return None
    kind, val = doc.xref_get_key(xref, "AP/N")
    if kind != "xref":
        return None
    ap = int(val.split()[0])
    rect = pdfcoords.array_numbers(doc, xref, "Rect")
    box, fm = po._form_box(doc, ap)
    if box is None or not rect or len(rect) != 4:
        return None
    body = po._expand(doc, page, ap, taken, clip=False)
    if body is None:
        return None
    r = pymupdf.Rect(rect).normalize()
    tb = box.quad.transform(fm).rect
    if tb.width > 1e-9 and tb.height > 1e-9:
        # the appearance's box mapped onto the markup's /Rect (the PDF's rule for drawing it)
        sx, sy = r.width / tb.width, r.height / tb.height
        fit = pymupdf.Matrix(sx, 0, 0, sy, r.x0 - tb.x0 * sx, r.y0 - tb.y0 * sy)
        if any(abs(u - v) > 1e-6 for u, v in zip(fit, (1, 0, 0, 1, 0, 0))):
            body = b"\nq " + b"%.6f %.6f %.6f %.6f %.4f %.4f cm" % tuple(fit) + body + b"Q\n"
    ca = doc.xref_get_key(xref, "CA")
    try:
        alpha = float(ca[1]) if ca[0] in ("float", "int") else 1.0
    except ValueError:
        alpha = 1.0
    if alpha < 1:
        # (the appearance sets its own transparency as MuPDF writes it; one that doesn't
        # gets the markup's)
        body = b"q /" + _alpha_gs(page, alpha, alpha) + b" gs" + body + b"Q\n"
    return body.lstrip(b"\n")


def _taken(page):
    po._own_resources(page)
    doc = page.parent
    return {cat: set(po._res_entries(doc, page.xref, "Resources/" + cat))
            for cat in po._RES_KINDS}


def draw(page, model):
    """Draw model (made by a Drawing tool, as its markup tool makes it) into the page, on the
    drawing layer. Run inside DocumentView.modify. Returns True when something was drawn."""
    kind, p = model["kind"], model["props"]
    if kind in ("rect", "ellipse", "polygon") and p.get("cloud"):
        # (a cloud's scallops as MuPDF draws them: its markup's appearance, the markup gone)
        annot = A.write(page, model)
        xref = annot.xref
        annot = None
        piece = appearance_piece(page, xref, _taken(page))
        from . import pdf_speed
        pdf_speed.delete_many(page, [xref])
    else:
        piece = shape_piece(page, model)
    if not piece:
        return False
    _append(page, [piece])
    return True


def convert(page, xrefs):
    """Convert to drawing: markups xrefs (shapes and lines: convertible) drawn into the page
    as their appearance draws them, in their stacking order, on the drawing layer, and taken
    off. Run inside DocumentView.modify. Returns the xrefs converted."""
    order = [x for x in A.annot_order(page) if x in set(xrefs)]
    taken = _taken(page)
    pieces, done = [], []
    for x in order:
        piece = appearance_piece(page, x, taken)
        if piece:
            pieces.append(piece)
            done.append(x)
    if not pieces:
        return []
    _append(page, pieces)
    from . import pdf_speed
    pdf_speed.delete_many(page, done)
    return done
