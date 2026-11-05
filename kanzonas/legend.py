"""Markup legends (as in Bluebeam Revu): a box on the sheet listing the kinds of markups used,
each row a small sample drawn in that markup's own style (color, line width, fill, cloud,
arrowhead...) with its label (the tool's name, or the markup's subject when it has one), how
many there are and, for measurements, their total in the page's units.

A legend is a Stamp annotation with an appearance of its own (drawn here as PDF operators,
with the standard Helvetica fonts), so every PDF viewer shows it, prints it and flattens it;
its options are kept in its KZProps like any other markup's (annotations.py), and its name
(/NM) starts with NM_PREFIX so a page's legends are found in one call (page.annot_xrefs).

It updates by itself: DocumentView.modify calls refresh() at the end of every edit, inside
that edit's undo step, so Undo and Redo bring the legend back as it was with the markups and
nothing writes to the document between them (a write there would drop every step to redo).
A legend counts every markup of its page (or of the whole document) but no legend.
"""

import json
import math
import uuid
import weakref

import pymupdf

from . import pdfcoords
from .i18n import tr

KIND = "legend"
NM_PREFIX = "KZLegend-"
# what a legend never counts: legends, redaction marks waiting to be applied and sign-here
# placeholders (they are steps of work, not markups of the drawing)
NOT_COUNTED = ("legend", "redact", "placeholder")
LENGTHS = ("m_length", "m_poly", "m_perimeter")
# style properties that tell two markups of one kind apart (a red cloud and a blue one are
# two rows)
STYLE_KEYS = ("stroke", "fill", "width", "head", "opacity", "text_color", "markup", "icon")


# ---- finding legends ---------------------------------------------------------------------
def is_legend(entry):
    """entry: one of page.annot_xrefs() -> True for a legend."""
    return entry[1] == pymupdf.PDF_ANNOT_STAMP and str(entry[2] or "").startswith(NM_PREFIX)


def legends_on(page):
    """The xrefs of the legends on page (one call, no markup read)."""
    return [e[0] for e in page.annot_xrefs() if is_legend(e)]


def stored(doc, xref):
    """A legend's KZProps ({"kind", "props", "geom"}) or {}."""
    try:
        typ, val = doc.xref_get_key(xref, "KZProps")
        if typ == "string":
            got = json.loads(val)
            return got if isinstance(got, dict) else {}
    except Exception:
        pass
    return {}


# ---- what's counted ----------------------------------------------------------------------
def _stamp_word(label):
    from . import stamps
    if label.startswith(stamps.IMAGE_PREFIX):
        name = label[len(stamps.IMAGE_PREFIX):]
        return name.rsplit(".", 1)[0] or name
    if label.startswith(stamps.FORM_PREFIX):
        return stamps.form_title(label)
    return label


def sample_kind(model):
    """The kind of sample drawn for a markup: its kind, or what its tool made of it (a
    cloud, a mask, a curve)."""
    from . import annotations as A
    kind, p = model["kind"], model["props"]
    if kind in ("rect", "ellipse", "polygon") and p.get("cloud"):
        return "cloud"
    if kind == "rect" and not p.get("stroke") and (p.get("fill") or "").lower() == "#ffffff":
        return "mask"
    if kind in ("line", "arrow") and model.get("bend") is not None:
        return "curve" if kind == "line" else "arrow"
    if kind == "comment":
        return p.get("markup") if p.get("markup") in A.COMMENT_STYLES else "highlight"
    return kind


def label_of(model, subject=""):
    """The row's label: the markup's subject when it has one, else its tool's name (a count
    by its group, a stamp by its word)."""
    from . import annotations as A
    if subject and subject.strip():
        return subject.strip()
    kind, p = model["kind"], model["props"]
    if kind == "m_count":
        return (p.get("group") or "").strip() or A.LABELS["m_count"]
    if kind == "stamp":
        return _stamp_word(p.get("label") or "") or A.LABELS["stamp"]
    s = sample_kind(model)
    if s in ("cloud", "mask", "curve"):
        return A.LABELS[s]
    return A.LABELS.get(kind, kind)


def _style(model):
    p = model["props"]
    out = {}
    for k in STYLE_KEYS:
        if k in p:
            v = p[k]
            if isinstance(v, float):
                v = round(v, 2)
            out[k] = v
    if model["kind"] == "stamp":
        from . import stamps
        if (p.get("label") or "").startswith(stamps.IMAGE_PREFIX):
            out["image"] = True
    return out


def page_summary(doc, index):
    """{row key: {"kind", "label", "style", "n", "m", "m2", "m3"}} for the markups of page
    index (lengths in meters, areas in square meters, volumes in cubic meters, by the page's
    own scale). Hidden markups and legends aren't counted."""
    from . import annotations as A
    from . import measure as M
    page = doc[index]
    out = {}
    scale = None
    annots = []
    a = page.first_annot
    while a:
        annots.append(a)
        a = a.next
        if a is not None:
            # (tied to this page, as annotations.load_annots does: Annot.next gives each
            # one a Page object of its own, in a reference cycle that keeps it loaded)
            a.parent = weakref.proxy(page)
    for a in annots:
        try:
            m = A.read(a)
        except Exception:
            m = None
        if not m or m["kind"] in NOT_COUNTED or m.get("hidden"):
            continue
        subject = ""
        try:
            subject = a.info.get("subject", "") or ""
        except Exception:
            pass
        kind = sample_kind(m)
        style = _style(m)
        label = label_of(m, subject)
        key = json.dumps([label, kind, style], sort_keys=True)
        row = out.get(key)
        if row is None:
            row = out[key] = {"kind": kind, "label": label, "style": style, "n": 0,
                              "m": 0.0, "m2": 0.0, "m3": 0.0}
        row["n"] += 1
        if m["kind"] in LENGTHS + ("m_area", "m_volume") and m.get("points"):
            if scale is None:
                scale = M.get_scale(page)[0]
            pts = m["points"]
            if m["kind"] in ("m_length", "m_poly"):
                row["m"] += M.length(pts) * scale
            elif m["kind"] == "m_perimeter":
                row["m"] += M.length(pts + pts[:1]) * scale
            elif m["kind"] == "m_area":
                row["m2"] += M.area(pts) * scale * scale
            elif len(pts) >= 3:
                f, unit = scale, M.get_scale(page)[1]
                row["m3"] += M.area(pts) * f * f * M.depth_m(m["props"], unit)
    return out


def rows_for(doc, index, scope, summary=None):
    """The legend's rows on page index: [{"kind", "label", "style", "n", "total"}], sorted by
    label. scope "document" counts every page. summary(doc, i): a page's counts (the view
    passes its cached ones)."""
    from . import measure as M
    summary = summary or page_summary
    pages = range(doc.page_count) if scope == "document" else [index]
    merged = {}
    for i in pages:
        for key, r in summary(doc, i).items():
            t = merged.get(key)
            if t is None:
                merged[key] = dict(r)
            else:
                t["n"] += r["n"]
                t["m"] += r["m"]
                t["m2"] += r["m2"]
                t["m3"] += r["m3"]
    unit = M.get_scale(doc[index])[1]
    rows = []
    for key in sorted(merged, key=lambda k: (merged[k]["label"].lower(), k)):
        r = merged[key]
        total = ""
        if r["kind"] in LENGTHS:
            total = M.fmt_length(r["m"], unit)
        elif r["kind"] == "m_area":
            total = M.fmt_area(r["m2"], unit)
        elif r["kind"] == "m_volume":
            total = M.fmt_volume(r["m3"], unit)
        rows.append({"kind": r["kind"], "label": r["label"], "style": r["style"], "n": r["n"],
                     "total": total})
    return rows


# ---- drawing -----------------------------------------------------------------------------
def _f(v):
    return ("%.3f" % v).rstrip("0").rstrip(".") or "0"


def _rgb(hex_color):
    from . import annotations as A
    return A.to_rgb(hex_color) if hex_color else None


def _color(rgb, op):
    return " ".join(_f(c) for c in rgb) + " " + op


def _pdf_text(s):
    """s as a PDF literal string for the WinAnsi (cp1252) Helvetica fonts; characters they
    don't have become '?'."""
    raw = s.encode("cp1252", "replace")
    out = []
    for b in raw:
        if b in (0x28, 0x29, 0x5c):
            out.append("\\" + chr(b))
        elif b < 32 or b > 126:
            out.append("\\%03o" % b)
        else:
            out.append(chr(b))
    return "(" + "".join(out) + ")"


def _width(s, size, bold=False):
    s = s.encode("cp1252", "replace").decode("cp1252")
    return pymupdf.get_text_length(s, fontname="hebo" if bold else "helv", fontsize=size)


class _Ops:
    """PDF operators in the legend's own frame: origin at its top-left as shown, x to the
    right, y down (the frame's matrix turns it into the annotation's box)."""

    def __init__(self):
        self.out = []
        self.gs = {}            # opacity -> ExtGState name

    def add(self, *ops):
        self.out.extend(ops)

    def alpha(self, opacity, multiply=False):
        if opacity >= 0.999 and not multiply:
            return
        key = (round(opacity, 2), multiply)
        name = self.gs.setdefault(key, "G%d" % len(self.gs))
        self.add("/%s gs" % name)

    def text(self, x, y, s, size, rgb=(0, 0, 0), bold=False):
        """s with its baseline starting at (x, y)."""
        self.add("BT", "/%s %s Tf" % ("KZB" if bold else "KZH", _f(size)), _color(rgb, "rg"),
                 "1 0 0 -1 %s %s Tm" % (_f(x), _f(y)), _pdf_text(s) + " Tj", "ET")

    def path(self, pts, close=False):
        self.add("%s %s m" % (_f(pts[0][0]), _f(pts[0][1])))
        for q in pts[1:]:
            self.add("%s %s l" % (_f(q[0]), _f(q[1])))
        if close:
            self.add("h")

    def curve(self, c1, c2, q):
        self.add("%s %s %s %s %s %s c" % tuple(_f(v) for v in (*c1, *c2, *q)))

    def ellipse(self, x0, y0, x1, y1):
        cx, cy, rx, ry = (x0 + x1) / 2, (y0 + y1) / 2, (x1 - x0) / 2, (y1 - y0) / 2
        k = 0.5523
        self.add("%s %s m" % (_f(cx + rx), _f(cy)))
        self.curve((cx + rx, cy + k * ry), (cx + k * rx, cy + ry), (cx, cy + ry))
        self.curve((cx - k * rx, cy + ry), (cx - rx, cy + k * ry), (cx - rx, cy))
        self.curve((cx - rx, cy - k * ry), (cx - k * rx, cy - ry), (cx, cy - ry))
        self.curve((cx + k * rx, cy - ry), (cx + rx, cy - k * ry), (cx + rx, cy))
        self.add("h")

    def bumps(self, pts, size, close=True):
        """A revision cloud's bumps along pts (bulging to the left of the way they run: out
        of a box drawn clockwise as shown)."""
        n = len(pts)
        edges = n if close else n - 1
        self.add("%s %s m" % (_f(pts[0][0]), _f(pts[0][1])))
        for i in range(edges):
            a, b = pts[i], pts[(i + 1) % n]
            dx, dy = b[0] - a[0], b[1] - a[1]
            ln = math.hypot(dx, dy)
            if ln <= 0:
                continue
            k = max(1, int(round(ln / size)))
            ux, uy = dx / ln, dy / ln
            nx, ny = uy, -ux                    # out of a clockwise outline
            step = ln / k
            for j in range(k):
                p = (a[0] + ux * step * j, a[1] + uy * step * j)
                q = (a[0] + ux * step * (j + 1), a[1] + uy * step * (j + 1))
                h = step * 0.6
                self.curve((p[0] + nx * h, p[1] + ny * h), (q[0] + nx * h, q[1] + ny * h), q)
        if close:
            self.add("h")


def _paint(ops, stroke, fill, width, close=True):
    """Fill and/or stroke the path just made."""
    if stroke and fill:
        ops.add(_color(fill, "rg"), _color(stroke, "RG"), "%s w" % _f(width), "B")
    elif fill:
        ops.add(_color(fill, "rg"), "f")
    elif stroke:
        ops.add(_color(stroke, "RG"), "%s w" % _f(width), "S")
    else:
        ops.add("n")


def _head(ops, kind, tip, back, size, rgb, width):
    """An arrowhead of kind (annotations.HEADS keys) at tip, the line coming from back."""
    dx, dy = tip[0] - back[0], tip[1] - back[1]
    ln = math.hypot(dx, dy) or 1
    ux, uy = dx / ln, dy / ln
    if kind.endswith("(reversed)"):
        ux, uy = -ux, -uy
        kind = kind.split(" ")[0]
    px, py = -uy, ux
    s = size
    if kind in ("open", "closed"):
        b = (tip[0] - ux * s, tip[1] - uy * s)
        p1 = (b[0] + px * s * 0.5, b[1] + py * s * 0.5)
        p2 = (b[0] - px * s * 0.5, b[1] - py * s * 0.5)
        if kind == "open":
            ops.path([p1, tip, p2])
            ops.add(_color(rgb, "RG"), "%s w" % _f(width), "S")
        else:
            ops.path([p1, tip, p2], close=True)
            ops.add(_color(rgb, "rg"), _color(rgb, "RG"), "%s w" % _f(width), "B")
    elif kind == "circle":
        ops.ellipse(tip[0] - s / 2, tip[1] - s / 2, tip[0] + s / 2, tip[1] + s / 2)
        ops.add(_color(rgb, "RG"), "%s w" % _f(width), "S")
    elif kind == "square":
        ops.path([(tip[0] - s / 2, tip[1] - s / 2), (tip[0] + s / 2, tip[1] - s / 2),
                  (tip[0] + s / 2, tip[1] + s / 2), (tip[0] - s / 2, tip[1] + s / 2)], True)
        ops.add(_color(rgb, "RG"), "%s w" % _f(width), "S")
    elif kind == "diamond":
        ops.path([(tip[0] - s / 2, tip[1]), (tip[0], tip[1] - s / 2), (tip[0] + s / 2, tip[1]),
                  (tip[0], tip[1] + s / 2)], True)
        ops.add(_color(rgb, "RG"), "%s w" % _f(width), "S")
    elif kind == "bar":
        ops.path([(tip[0] + px * s / 2, tip[1] + py * s / 2),
                  (tip[0] - px * s / 2, tip[1] - py * s / 2)])
        ops.add(_color(rgb, "RG"), "%s w" % _f(width), "S")


def _sample(ops, kind, style, x, y, w, h, fs):
    """The sample of a row: kind drawn in style inside the box x, y, w, h."""
    stroke = _rgb(style.get("stroke"))
    fill = _rgb(style.get("fill"))
    text_rgb = _rgb(style.get("text_color")) or (0, 0, 0)
    width = float(style.get("width") or 1.0)
    width = max(0.4, min(width, h * 0.35))
    opacity = float(style.get("opacity") if style.get("opacity") is not None else 1.0)
    x1, y1, cx, cy = x + w, y + h, x + w / 2, y + h / 2
    m = min(w, h) * 0.12                    # (inset: thick lines stay inside the box)
    ops.add("q")
    ops.alpha(opacity)
    if kind == "highlight":
        ops.add(_color(stroke or (1, 0.86, 0), "rg"),
                "%s %s %s %s re f" % (_f(x), _f(y + h * 0.1), _f(w), _f(h * 0.8)))
    elif kind in ("underline", "strikeout", "squiggly"):
        ops.add("Q", "q")
        ops.text(x + w * 0.08, y + h * 0.8, "Abc", h * 0.85, (0.35, 0.35, 0.35))
        ops.alpha(opacity)
        rgb = stroke or (0, 0.6, 0)
        lw = max(0.6, h * 0.08)
        if kind == "underline":
            ops.path([(x, y + h * 0.95), (x1, y + h * 0.95)])
        elif kind == "strikeout":
            ops.path([(x, cy + h * 0.05), (x1, cy + h * 0.05)])
        else:
            n = 8
            ops.path([(x + w * i / n, y + h * (0.88 if i % 2 else 1.0)) for i in range(n + 1)])
        ops.add(_color(rgb, "RG"), "%s w" % _f(lw), "S")
    elif kind == "note":
        s = h
        nx = cx - s / 2
        ops.path([(nx, y), (nx + s * 0.7, y), (nx + s, y + s * 0.3), (nx + s, y1), (nx, y1)],
                 close=True)
        ops.add(_color(stroke or (1, 0.86, 0), "rg"), "0 0 0 RG", "0.5 w", "B")
        ops.path([(nx + s * 0.7, y), (nx + s * 0.7, y + s * 0.3), (nx + s, y + s * 0.3)])
        ops.add("0.5 w", "S")
    elif kind in ("textbox", "callout", "placeholder"):
        bx = x + (w * 0.4 if kind == "callout" else 0)
        ops.path([(bx + m, y + m), (x1 - m, y + m), (x1 - m, y1 - m), (bx + m, y1 - m)], True)
        _paint(ops, stroke, fill, width)
        ops.text(bx + m + h * 0.15, y1 - m - h * 0.2, "Abc", h * 0.55, text_rgb)
        if kind == "callout" and stroke:
            tip = (x + m, y1 - m)
            ops.path([(bx + m, cy), tip])
            ops.add(_color(stroke, "RG"), "%s w" % _f(width), "S")
            _head(ops, style.get("head") or "open", tip, (bx + m, cy), h * 0.45, stroke, width)
    elif kind in ("rect", "mask", "image", "attach", "stamp"):
        box = [(x + m, y + m), (x1 - m, y + m), (x1 - m, y1 - m), (x + m, y1 - m)]
        if kind == "mask":
            ops.path(box, True)
            _paint(ops, stroke, fill or (1, 1, 1), width)
            ops.path(box, True)
            ops.add("0.6 0.6 0.6 RG", "0.4 w", "[1.5 1.5] 0 d", "S", "[] 0 d")
        elif kind == "image":
            ops.path(box, True)
            ops.add("0.85 0.88 0.92 rg", "0.5 0.5 0.5 RG", "0.5 w", "B")
            ops.path([(x + m, y1 - m), (x + w * 0.4, y + h * 0.35), (x + w * 0.6, y + h * 0.6),
                      (x + w * 0.75, y + h * 0.45), (x1 - m, y1 - m)], True)
            ops.add("0.45 0.6 0.4 rg", "f")
        elif kind == "stamp":
            rgb = stroke or (0.75, 0, 0)
            ops.path(box, True)
            ops.add(_color(rgb, "RG"), "%s w" % _f(max(0.8, h * 0.08)), "S")
            i = m + h * 0.12
            ops.path([(x + i, y + i), (x1 - i, y + i), (x1 - i, y1 - i), (x + i, y1 - i)], True)
            ops.add("%s w" % _f(max(0.4, h * 0.04)), "S")
        elif kind == "attach":
            rgb = stroke or (0, 0.31, 1)
            ops.path([(cx - h * 0.15, y1 - m), (cx - h * 0.15, y + m + h * 0.15)])
            ops.curve((cx - h * 0.15, y + m - h * 0.05), (cx + h * 0.15, y + m - h * 0.05),
                      (cx + h * 0.15, y + m + h * 0.15))
            ops.add("%s %s l" % (_f(cx + h * 0.15), _f(y1 - m - h * 0.1)))
            ops.add(_color(rgb, "RG"), "%s w" % _f(max(0.6, h * 0.08)), "S")
        else:
            ops.path(box, True)
            _paint(ops, stroke, fill, width)
    elif kind in ("ellipse", "circle"):
        ops.ellipse(x + m, y + m, x1 - m, y1 - m)
        _paint(ops, stroke, fill, width)
    elif kind == "cloud":
        i = h * 0.22
        ops.bumps([(x + i, y + i), (x1 - i, y + i), (x1 - i, y1 - i), (x + i, y1 - i)], h * 0.5)
        _paint(ops, stroke, fill, width)
    elif kind == "opencloud":
        ops.bumps([(x + m, cy + h * 0.2), (x1 - m, cy + h * 0.2)], h * 0.35, close=False)
        _paint(ops, stroke, None, width, close=False)
    elif kind in ("polygon", "m_area", "m_perimeter", "m_volume"):
        pts = [(x + w * 0.08, y1 - m), (x + w * 0.25, y + m), (x + w * 0.7, y + m * 1.5),
               (x1 - m, y + h * 0.65), (x + w * 0.55, y1 - m)]
        ops.path(pts, True)
        _paint(ops, stroke, fill, width)
    elif kind in ("polyline", "m_poly"):
        ops.path([(x + m, y1 - m), (x + w * 0.35, y + m), (x + w * 0.65, y1 - m), (x1 - m, y + m)])
        _paint(ops, stroke, None, width, close=False)
    elif kind in ("arc", "curve", "ink"):
        ops.add("%s %s m" % (_f(x + m), _f(y1 - m)))
        if kind == "arc":
            ops.curve((x + m, y + m), (x1 - m, y + m), (x1 - m, y1 - m))
        elif kind == "curve":
            ops.curve((x + w * 0.4, y - h * 0.3), (x + w * 0.6, y1 + h * 0.3), (x1 - m, y + m))
        else:
            ops.curve((x + w * 0.2, y - h * 0.2), (x + w * 0.35, y1), (cx, cy))
            ops.curve((x + w * 0.65, y), (x + w * 0.8, y1 + h * 0.2), (x1 - m, y + m))
        _paint(ops, stroke, None, width, close=False)
    elif kind in ("line", "arrow", "m_length", "m_radius", "m_angle"):
        a, b = (x + m, cy), (x1 - m, cy)
        rgb = stroke or (0, 0, 0)
        if kind == "m_angle":
            v = (x + m, y1 - m)
            ops.path([(x1 - m, y1 - m), v, (x + w * 0.6, y + m)])
            ops.add(_color(rgb, "RG"), "%s w" % _f(width), "S")
        elif kind == "m_radius":
            r = h / 2 - m
            ops.ellipse(cx - r, cy - r, cx + r, cy + r)
            ops.add(_color(rgb, "RG"), "%s w" % _f(width), "[1.5 1] 0 d", "S", "[] 0 d")
            ops.path([(cx, cy), (cx + r, cy)])
            ops.add("S")
        else:
            ops.path([a, b])
            ops.add(_color(rgb, "RG"), "%s w" % _f(width), "S")
        if kind == "arrow":
            _head(ops, style.get("head") or "open", b, a, max(h * 0.5, width * 3), rgb, width)
        elif kind == "m_length":
            for e in (a, b):
                ops.path([(e[0], cy - h * 0.3), (e[0], cy + h * 0.3)])
            ops.add("S")
    elif kind == "m_count":
        r = h * 0.3
        ops.ellipse(cx - r, cy - r, cx + r, cy + r)
        rgb = stroke or (0, 0.31, 1)
        ops.add(_color(rgb, "rg"), "f")
    else:
        ops.path([(cx - h * 0.35, y + m), (cx + h * 0.35, y + m), (cx + h * 0.35, y1 - m),
                  (cx - h * 0.35, y1 - m)], True)
        _paint(ops, stroke, fill or stroke, width)
    ops.add("Q")


def layout(rows, props):
    """The legend's drawing: (operators, ExtGState names, width, height) in its own frame
    (top-left origin, y down, as shown)."""
    fs = max(2.0, float(props.get("fontsize") or 9))
    show_n, show_t = bool(props.get("count", True)), bool(props.get("totals", True))
    title = (props.get("title") or "").strip()
    text_rgb = _rgb(props.get("text_color")) or (0, 0, 0)
    gray = tuple(0.45 + 0.1 * c for c in text_rgb)
    pad, gap, rh = fs * 0.6, fs * 0.8, fs * 1.6
    sw, sh = fs * 2.6, fs * 1.05
    ts = fs * 1.2
    head_s = fs * 0.85
    any_total = show_t and any(r.get("total") for r in rows)
    label_w = max([_width(r["label"], fs) for r in rows] + [0])
    n_text = [str(r["n"]) for r in rows]
    n_w = max([_width(t, fs) for t in n_text] + [_width(tr("Count"), head_s)]) if show_n else 0
    t_w = max([_width(r.get("total") or "", fs) for r in rows] +
              [_width(tr("Total"), head_s)]) if any_total else 0
    width = pad + sw + gap + label_w + (gap + n_w if show_n else 0) + \
        (gap + t_w if any_total else 0) + pad
    if not rows:
        width = max(width, pad * 2 + _width(tr("No markups yet"), fs))
    if title:
        width = max(width, pad * 2 + _width(title, ts, bold=True))
    width = max(width, fs * 6)
    ops = _Ops()
    y = pad
    body = []                   # (drawn after the frame's fill)
    if title:
        body.append(lambda y=y: ops.text(pad, y + ts * 0.85, title, ts, text_rgb, bold=True))
        y += ts * 1.3
        if props.get("border", True):
            line_y = y - ts * 0.15
            body.append(lambda ly=line_y: (ops.path([(0, ly), (width, ly)]),
                                           ops.add(_color(_rgb(props.get("stroke")) or (0, 0, 0),
                                                          "RG"),
                                                   "%s w" % _f(max(0.3, fs / 18)), "S")))
    x_n = width - pad - (t_w + gap if any_total else 0)       # (right edge of the counts)
    x_t = width - pad
    if rows and (show_n or any_total):
        hy = y + head_s
        if show_n:
            body.append(lambda hy=hy: ops.text(x_n - _width(tr("Count"), head_s), hy,
                                               tr("Count"), head_s, gray))
        if any_total:
            body.append(lambda hy=hy: ops.text(x_t - _width(tr("Total"), head_s), hy,
                                               tr("Total"), head_s, gray))
        y += head_s * 1.4
    if not rows:
        body.append(lambda y=y: ops.text(pad, y + fs * 1.05, tr("No markups yet"), fs, gray))
        y += rh
    for r, nt in zip(rows, n_text):
        base = y + rh / 2 + fs * 0.35
        body.append(lambda r=r, y=y: _sample(ops, r["kind"], r["style"], pad,
                                             y + (rh - sh) / 2, sw, sh, fs))
        body.append(lambda r=r, base=base: ops.text(pad + sw + gap, base, r["label"], fs,
                                                    text_rgb))
        if show_n:
            body.append(lambda nt=nt, base=base: ops.text(x_n - _width(nt, fs), base, nt, fs,
                                                          text_rgb))
        if any_total and r.get("total"):
            body.append(lambda r=r, base=base: ops.text(x_t - _width(r["total"], fs), base,
                                                        r["total"], fs, text_rgb))
        y += rh
    height = y + pad * 0.6
    fill = _rgb(props.get("fill"))
    stroke = _rgb(props.get("stroke")) if props.get("border", True) else None
    if fill or stroke:
        bw = max(0.4, fs / 12)
        ops.add("%s %s %s %s re" % (_f(bw / 2), _f(bw / 2), _f(width - bw), _f(height - bw)))
        _paint(ops, stroke, fill, bw)
    for fn in body:
        fn()
    return ops, width, height


def summary_text(rows, title=""):
    """The legend as plain text (its /Contents: other programs' comment lists show it)."""
    parts = ["%s %d%s" % (r["label"], r["n"], (" (%s)" % r["total"]) if r.get("total") else "")
             for r in rows]
    return (title or tr("Legend")) + ": " + (", ".join(parts) if parts else tr("No markups yet"))


def display_rect(page, rect, width, height):
    """The legend's box (unrotated page coordinates) for a drawing width x height as shown,
    its top-left corner as shown kept where rect's is."""
    disp = (pymupdf.Rect(rect) * page.rotation_matrix).normalize()
    tl = disp.tl
    return (pymupdf.Rect(tl.x, tl.y, tl.x + width, tl.y + height) *
            page.derotation_matrix).normalize()


def draw(page, annot_xref, model, rows=None):
    """Draw the legend annot_xref (made by annotations.write) from model (its box's top-left
    corner as shown and its options): its appearance, box, contents and KZProps. rows: as
    rows_for gives them (worked out here when None). Returns the box it now has."""
    doc = page.parent
    props = model["props"]
    if rows is None:
        rows = rows_for(doc, page.number, props.get("scope") or "page")
    ops, w, h = layout(rows, props)
    rect = display_rect(page, model["rect"], w, h)
    # the frame: shown top-left origin, y down -> unrotated page -> PDF -> the box's form
    to_pdf = pdfcoords.to_pdf(page)
    disp = (rect * page.rotation_matrix).normalize()
    pr = (rect * to_pdf).normalize()
    frame = pymupdf.Matrix(1, 0, 0, 1, disp.x0, disp.y0) * page.derotation_matrix * to_pdf * \
        pymupdf.Matrix(1, 0, 0, 1, -pr.x0, -pr.y0)
    stream = ("q %s cm\n" % " ".join(_f(v) for v in tuple(frame)) + "\n".join(ops.out) +
              "\nQ\n").encode("latin-1")
    gs = "".join("/%s<</Type/ExtGState/ca %s/CA %s%s>>" % (
        name, _f(op), _f(op), "/BM/Multiply" if mult else "")
        for (op, mult), name in ops.gs.items())
    res = ("<</Font<</KZH<</Type/Font/Subtype/Type1/BaseFont/Helvetica/Encoding/WinAnsiEncoding>>"
           "/KZB<</Type/Font/Subtype/Type1/BaseFont/Helvetica-Bold/Encoding/WinAnsiEncoding>>>>"
           + ("/ExtGState<<%s>>" % gs if gs else "") + ">>")
    typ, val = doc.xref_get_key(annot_xref, "AP/N")
    if typ == "xref":
        ap = int(val.split()[0])
    else:
        ap = doc.get_new_xref()
        doc.update_object(ap, "<<>>")
        doc.xref_set_key(annot_xref, "AP", "<</N %d 0 R>>" % ap)
    doc.update_object(ap, "<</Type/XObject/Subtype/Form/BBox[0 0 %s %s]/Matrix[1 0 0 1 0 0]"
                          "/Resources%s>>" % (_f(pr.width), _f(pr.height), res))
    doc.update_stream(ap, stream)
    doc.xref_set_key(annot_xref, "Rect", "[%s %s %s %s]" % (_f(pr.x0), _f(pr.y0), _f(pr.x1),
                                                            _f(pr.y1)))
    doc.xref_set_key(annot_xref, "Contents",
                     pymupdf.get_pdf_str(summary_text(rows, props.get("title"))))
    store = {"kind": KIND, "props": props, "geom": {"box": list(rect), "rows": rows}}
    doc.xref_set_key(annot_xref, "KZProps", pymupdf.get_pdf_str(json.dumps(store)))
    return rect


def new_name():
    return NM_PREFIX + uuid.uuid4().hex[:16]


# ---- keeping legends up to date ------------------------------------------------------------
def refresh(doc, pages, structural, where, summaries):
    """Bring the document's legends up to date after an edit of pages (None or structural:
    any page). where: {page index: [legend xrefs]} and summaries: {page index: its
    page_summary}, both kept by the view between edits and emptied for the pages an edit
    touches. Returns the pages whose legend was drawn again. Cheap with no legend in the
    document (one annot_xrefs call per page touched); a legend that comes out the same isn't
    written."""
    n = doc.page_count
    everything = structural or pages is None
    touched = set(range(n)) if everything else {i for i in pages if 0 <= i < n}
    for i in range(n):
        if i not in where:
            where[i] = legends_on(doc[i])
    todo = []
    for i in range(n):
        for x in where.get(i, ()):
            st = stored(doc, x)
            if st.get("kind") != KIND:
                continue
            scope = (st.get("props") or {}).get("scope") or "page"
            if everything or i in touched or (scope == "document" and touched):
                todo.append((i, x, st))
    if not todo:
        return set()

    def summary(d, i):
        s = summaries.get(i)
        if s is None:
            s = summaries[i] = page_summary(d, i)
        return s
    changed = set()
    from . import annotations as A
    for i, x, st in todo:
        props = dict(A.DEFAULTS[KIND])
        props.update(st.get("props") or {})
        rows = rows_for(doc, i, props.get("scope") or "page", summary)
        geom = st.get("geom") or {}
        if geom.get("rows") == rows and geom.get("box"):
            continue
        page = doc[i]
        box = geom.get("box")
        rect = pymupdf.Rect(box) if box else page.load_annot(x).rect
        draw(page, x, {"kind": KIND, "props": props, "rect": rect}, rows)
        changed.add(i)
    return changed
