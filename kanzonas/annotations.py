"""Annotation model.

Every annotation the app makes is described by a small model:
    {"kind": "rect", "rect": Rect, "points": [...], "strokes": [[...]], "quads": [...],
     "text": "...", "props": {...}}
`write()` creates a PDF annotation from a model and `read()` turns an annotation back into
one, so editing (move, resize, restyle, retype) is "read, change, delete, write" inside
one undo step. Style properties are also stored in the annotation (/KZProps) so they
survive a save and reopen exactly.

Per-tool default styles are kept in QSettings so they persist between sessions.
"""

import json

import pymupdf
from PySide6.QtCore import QSettings

KZ_KEY = "KZProps"

DEFAULTS = {
    "highlight": {"stroke": "#ffdc00", "opacity": 1.0},
    "comment": {"markup": "highlight", "stroke": "#ffdc00", "opacity": 1.0},
    "underline": {"stroke": "#00a000", "opacity": 1.0},
    "strikeout": {"stroke": "#e00000", "opacity": 1.0},
    "squiggly": {"stroke": "#e00000", "opacity": 1.0},
    "note": {"stroke": "#ffdc00", "opacity": 1.0},
    "textbox": {"text_color": "#000000", "stroke": "#d00000", "fill": None, "width": 1.0,
                "fontsize": 11, "opacity": 1.0},
    "rect": {"stroke": "#d00000", "fill": None, "width": 2.0, "opacity": 1.0},
    "ellipse": {"stroke": "#d00000", "fill": None, "width": 2.0, "opacity": 1.0},
    "line": {"stroke": "#0050ff", "width": 2.0, "opacity": 1.0},
    "arrow": {"stroke": "#d00000", "width": 2.0, "head": "open", "opacity": 1.0},
    "ink": {"stroke": "#0050ff", "width": 2.0, "opacity": 1.0},
}
LABELS = {"highlight": "Highlight", "comment": "Comment", "underline": "Underline",
          "strikeout": "Strikeout", "squiggly": "Squiggly", "note": "Sticky note", "textbox": "Text box",
          "rect": "Rectangle", "ellipse": "Ellipse", "line": "Line", "arrow": "Arrow",
          "ink": "Pen"}
HEADS = {"open": pymupdf.PDF_ANNOT_LE_OPEN_ARROW, "closed": pymupdf.PDF_ANNOT_LE_CLOSED_ARROW,
         "open (reversed)": pymupdf.PDF_ANNOT_LE_R_OPEN_ARROW,
         "closed (reversed)": pymupdf.PDF_ANNOT_LE_R_CLOSED_ARROW,
         "circle": pymupdf.PDF_ANNOT_LE_CIRCLE, "square": pymupdf.PDF_ANNOT_LE_SQUARE,
         "diamond": pymupdf.PDF_ANNOT_LE_DIAMOND, "bar": pymupdf.PDF_ANNOT_LE_BUTT}
MARKUP = ("highlight", "comment", "underline", "strikeout", "squiggly")
COMMENT_STYLES = ["highlight", "underline", "strikeout", "squiggly"]   # how a comment marks text      # tied to text: not movable
BOXED = ("rect", "ellipse", "textbox")                           # resizable via a rect
_TYPE_KIND = {pymupdf.PDF_ANNOT_SQUARE: "rect", pymupdf.PDF_ANNOT_CIRCLE: "ellipse",
              pymupdf.PDF_ANNOT_INK: "ink", pymupdf.PDF_ANNOT_FREE_TEXT: "textbox",
              pymupdf.PDF_ANNOT_TEXT: "note", pymupdf.PDF_ANNOT_HIGHLIGHT: "highlight",
              pymupdf.PDF_ANNOT_UNDERLINE: "underline",
              pymupdf.PDF_ANNOT_STRIKE_OUT: "strikeout", pymupdf.PDF_ANNOT_SQUIGGLY: "squiggly",
              pymupdf.PDF_ANNOT_LINE: "line"}


# ---- colours ----------------------------------------------------------------
def to_rgb(hex_color):
    if not hex_color:
        return None
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def to_hex(rgb):
    if not rgb:
        return None
    return "#" + "".join(f"{max(0, min(255, round(c * 255))):02x}" for c in rgb[:3])


# ---- per-tool defaults (persist across sessions) ------------------------------
def _settings():
    return QSettings("KanzonasPDF", "KanzonasPDF")


def tool_props(kind):
    props = dict(DEFAULTS.get(kind, {}))
    try:
        saved = json.loads(_settings().value("tool_defaults", "{}") or "{}").get(kind, {})
        props.update({k: v for k, v in saved.items() if k in props})
    except (ValueError, TypeError):
        pass
    return props


def set_tool_props(kind, props):
    s = _settings()
    try:
        allp = json.loads(s.value("tool_defaults", "{}") or "{}")
    except (ValueError, TypeError):
        allp = {}
    allp[kind] = props
    s.setValue("tool_defaults", json.dumps(allp))


def reset_tool_props(kind):
    set_tool_props(kind, dict(DEFAULTS[kind]))


# ---- read / write ----------------------------------------------------------------
def read(annot):
    """Annotation -> model, or None for annotation types the app doesn't edit."""
    kind = _TYPE_KIND.get(annot.type[0])
    if kind is None:
        return None
    doc = annot.parent.parent
    stored = {}
    try:
        typ, val = doc.xref_get_key(annot.xref, KZ_KEY)
        if typ == "string":
            stored = json.loads(val)
    except Exception:
        stored = {}
    if kind == "line" and annot.line_ends and annot.line_ends[1] != pymupdf.PDF_ANNOT_LE_NONE:
        kind = "arrow"
    kind = stored.get("kind", kind)
    if kind not in DEFAULTS:
        return None

    props = dict(DEFAULTS[kind])
    cols = annot.colors or {}
    if kind != "textbox":                      # FreeText keeps its colours elsewhere
        if cols.get("stroke"):
            props["stroke"] = to_hex(cols["stroke"])
        if "fill" in props:
            props["fill"] = to_hex(cols.get("fill")) or None
    if "width" in props and annot.border and annot.border.get("width", -1) > 0:
        props["width"] = annot.border["width"]
    if annot.opacity is not None and 0 <= annot.opacity < 1:
        props["opacity"] = annot.opacity
    props.update({k: v for k, v in stored.get("props", {}).items() if k in props})

    model = {"kind": kind, "props": props, "text": annot.info.get("content", ""),
             "rect": pymupdf.Rect(annot.rect)}
    verts = annot.vertices or []
    if kind in ("line", "arrow"):
        model["points"] = [pymupdf.Point(v) for v in verts[:2]]
    elif kind == "ink":
        model["strokes"] = [[pymupdf.Point(p) for p in s] for s in verts]
    elif kind in MARKUP:
        model["quads"] = [pymupdf.Quad(verts[i:i + 4]) for i in range(0, len(verts) - 3, 4)]
    if kind == "note":
        model["rect"] = pymupdf.Rect(annot.rect)
    return model


def _popup_rect(page, anchor):
    r = pymupdf.Rect(anchor.x1 + 12, anchor.y0, anchor.x1 + 192, anchor.y0 + 90)
    pr = page.rect * page.derotation_matrix
    if r.x1 > pr.x1:
        r = pymupdf.Rect(pr.x1 - 180, anchor.y1 + 6, pr.x1, anchor.y1 + 96)
    return r


def _recolor_textbox_border(doc, annot, stroke_rgb):
    """PDF FreeText draws its border in the text colour. Patch our appearance so the
    border uses its own colour: the first RG operator in the stream strokes the frame."""
    try:
        typ, val = doc.xref_get_key(annot.xref, "AP/N")
        if typ != "xref":
            return
        xref = int(val.split()[0])
        lines = doc.xref_stream(xref).decode("latin-1").split("\n")
        for i, ln in enumerate(lines):
            if ln.endswith(" RG"):
                lines[i] = " ".join(f"{c:g}" for c in stroke_rgb) + " RG"
                break
        doc.update_stream(xref, "\n".join(lines).encode("latin-1"))
    except Exception:
        pass


def write(page, model):
    """Model -> new annotation on page. Returns the annotation."""
    kind, p = model["kind"], model["props"]
    stroke = to_rgb(p.get("stroke"))
    fill = to_rgb(p.get("fill"))
    width = float(p.get("width", 1))
    text = model.get("text", "")

    markup = p.get("markup", "highlight") if kind == "comment" else kind
    if markup == "highlight":
        a = page.add_highlight_annot(model["quads"])
    elif markup == "underline":
        a = page.add_underline_annot(model["quads"])
    elif markup == "strikeout":
        a = page.add_strikeout_annot(model["quads"])
    elif markup == "squiggly":
        a = page.add_squiggly_annot(model["quads"])
    elif kind == "rect":
        a = page.add_rect_annot(model["rect"])
    elif kind == "ellipse":
        a = page.add_circle_annot(model["rect"])
    elif kind in ("line", "arrow"):
        a = page.add_line_annot(*model["points"][:2])
        if kind == "arrow":
            a.set_line_ends(pymupdf.PDF_ANNOT_LE_NONE, HEADS.get(p.get("head"), HEADS["open"]))
    elif kind == "ink":
        a = page.add_ink_annot([[(q.x, q.y) for q in s] for s in model["strokes"]])
    elif kind == "note":
        a = page.add_text_annot(model["rect"].tl, text or " ", icon="Note")
    elif kind == "textbox":
        a = page.add_freetext_annot(model["rect"], text, fontsize=float(p.get("fontsize", 11)),
                                    fontname="helv",
                                    text_color=to_rgb(p.get("text_color")) or (0, 0, 0),
                                    fill_color=fill, border_width=width,
                                    rotate=page.rotation)
    else:
        raise ValueError("unknown annotation kind " + kind)

    if kind != "textbox":
        if kind in ("rect", "ellipse"):
            a.set_colors(stroke=stroke, fill=fill)
        elif kind == "arrow" and "closed" in (p.get("head") or ""):
            a.set_colors(stroke=stroke, fill=stroke)
        else:
            a.set_colors(stroke=stroke)
        if kind in ("rect", "ellipse", "line", "arrow", "ink"):
            a.set_border(width=width)
    if p.get("opacity", 1) < 1:
        a.set_opacity(float(p["opacity"]))
    if text and kind != "textbox":
        a.set_info(content=text)
    if kind == "comment" and model.get("quads"):
        anchor = pymupdf.Rect()
        for q in model["quads"]:
            anchor |= q.rect
        a.set_popup(_popup_rect(page, anchor))
        a.set_open(False)
    a.update()

    doc = page.parent
    if kind == "textbox" and width > 0 and stroke:
        _recolor_textbox_border(doc, a, stroke)
    elif kind == "textbox" and width > 0 and not stroke:
        pass
    doc.xref_set_key(a.xref, KZ_KEY, pymupdf.get_pdf_str(json.dumps({"kind": kind, "props": p})))
    return a


# ---- geometry edits on a model -------------------------------------------------
def bounds(model):
    """Rect that the selection handles act on."""
    if model["kind"] in ("line", "arrow"):
        a, b = model["points"]
        return pymupdf.Rect(a, b).normalize()
    if model["kind"] == "ink":
        r = pymupdf.Rect()
        for s in model["strokes"]:
            for q in s:
                r |= q
        return r
    if model["kind"] in MARKUP:
        r = pymupdf.Rect()
        for q in model["quads"]:
            r |= q.rect
        return r
    return pymupdf.Rect(model["rect"])


def movable(model):
    return model["kind"] not in MARKUP


def copy(model):
    m = dict(model)
    m["props"] = dict(model["props"])
    if "rect" in m:
        m["rect"] = pymupdf.Rect(m["rect"])
    if "points" in m:
        m["points"] = [pymupdf.Point(q) for q in m["points"]]
    if "strokes" in m:
        m["strokes"] = [[pymupdf.Point(q) for q in s] for s in m["strokes"]]
    return m


def moved(model, delta):
    m = copy(model)
    if "rect" in m:
        m["rect"] = m["rect"] + (delta.x, delta.y, delta.x, delta.y)
    if "points" in m:
        m["points"] = [q + delta for q in m["points"]]
    if "strokes" in m:
        m["strokes"] = [[q + delta for q in s] for s in m["strokes"]]
    return m


def resized(model, new_rect):
    """Fit the annotation to new_rect (boxes directly, ink and lines by scaling)."""
    m = copy(model)
    old = bounds(model)
    new_rect = pymupdf.Rect(new_rect).normalize()
    if m["kind"] in BOXED:
        m["rect"] = new_rect
        return m
    sx = new_rect.width / old.width if old.width else 1
    sy = new_rect.height / old.height if old.height else 1

    def f(q):
        return pymupdf.Point(new_rect.x0 + (q.x - old.x0) * sx, new_rect.y0 + (q.y - old.y0) * sy)
    if "points" in m:
        m["points"] = [f(q) for q in m["points"]]
    if "strokes" in m:
        m["strokes"] = [[f(q) for q in s] for s in m["strokes"]]
    return m


def with_endpoint(model, i, pt):
    m = copy(model)
    m["points"][i] = pymupdf.Point(pt)
    return m
