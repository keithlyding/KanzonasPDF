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

import getpass
import json
import math
import weakref

import pymupdf

from . import pdf_speed, pdfcoords
from .i18n import tr

pdf_speed.apply()                       # (adding markups doesn't slow down as they add up)


def each_annot(page, types=None):
    """The page's annotations (no links, form fields or popups), as a list in page order:
    the same as page.annots(), which looks each one up from the start of the list again
    (N squared steps: 5 s for 2,000 markups on a page) where this walks it once (0.06 s).
    types: only these annotation types (PDF_ANNOT_...). Keep the page alive while using them."""
    out = []
    a = page.first_annot
    while a:
        if types is None or a.type[0] in types:
            out.append(a)
        a = a.next
    return out


def load_annots(page, xrefs):
    """{xref: Annot} for these annotations of the page (missing ones left out): one walk of
    the page for many, where page.load_annot looks each one up from the start of the list.
    Keep the page alive while using them."""
    if len(xrefs) < 8:
        out = {}
        for x in xrefs:
            try:
                out[x] = page.load_annot(x)
            except Exception:
                pass
        return out
    want = set(xrefs)
    out = {}
    a = page.first_annot
    while a:
        if a.xref in want:
            out[a.xref] = a
        a = a.next
        if a is not None:
            # Annot.next gives each one a Page object of its own, in a reference cycle that
            # keeps the page loaded until Python collects it, with its old stacking order
            # (set_annot_order): tie it to this page instead, as page.load_annot does
            a.parent = weakref.proxy(page)
    return out


KZ_KEY = "KZProps"

DEFAULTS = {
    "highlight": {"stroke": "#ffdc00", "opacity": 1.0},
    "comment": {"markup": "highlight", "stroke": "#ffdc00", "opacity": 1.0},
    "underline": {"stroke": "#00a000", "opacity": 1.0},
    "strikeout": {"stroke": "#e00000", "opacity": 1.0},
    "squiggly": {"stroke": "#e00000", "opacity": 1.0},
    "note": {"stroke": "#ffdc00", "opacity": 1.0},
    "textbox": {"font": "Helvetica", "text_color": "#000000", "stroke": "#d00000", "fill": None,
                "width": 1.0,
                "fontsize": 11, "opacity": 1.0},
    "rect": {"stroke": "#d00000", "fill": None, "width": 2.0, "cloud": False, "opacity": 1.0},
    "ellipse": {"stroke": "#d00000", "fill": None, "width": 2.0, "cloud": False, "opacity": 1.0},
    "cloud": {"stroke": "#d00000", "fill": None, "width": 1.5, "cloud": True, "opacity": 1.0},
    "polygon": {"stroke": "#d00000", "fill": None, "width": 2.0, "cloud": False, "opacity": 1.0},
    "polyline": {"stroke": "#0050ff", "width": 2.0, "opacity": 1.0},
    "callout": {"text_color": "#000000", "stroke": "#d00000", "fill": "#ffffd0", "width": 1.0,
                "fontsize": 11, "head": "open", "opacity": 1.0},
    "m_length": {"stroke": "#d00000", "width": 1.0, "fontsize": 9, "opacity": 1.0},
    "m_poly": {"stroke": "#d00000", "width": 1.0, "fontsize": 9, "opacity": 1.0},
    "m_area": {"stroke": "#d00000", "fill": None, "width": 1.0, "fontsize": 9, "opacity": 1.0},
    "m_angle": {"stroke": "#d00000", "width": 1.0, "fontsize": 9, "opacity": 1.0},
    "m_radius": {"stroke": "#d00000", "width": 1.0, "fontsize": 9, "opacity": 1.0},
    "m_perimeter": {"stroke": "#d00000", "fill": None, "width": 1.0, "fontsize": 9, "opacity": 1.0},
    "m_volume": {"stroke": "#d00000", "fill": None, "width": 1.0, "fontsize": 9, "depth": 1.0,
                 "opacity": 1.0},
    "m_count": {"stroke": "#0050ff", "fontsize": 9, "group": "Count 1", "opacity": 1.0},
    # the stamp word is printed on the page: in the user's language (a placed stamp keeps its own)
    "stamp": {"label": tr("APPROVED"), "stroke": "#c00000", "name": True, "date": True, "opacity": 1.0},
    "line": {"stroke": "#0050ff", "width": 2.0, "opacity": 1.0},
    "arrow": {"stroke": "#d00000", "width": 2.0, "head": "open", "opacity": 1.0},
    "ink": {"stroke": "#0050ff", "width": 2.0, "opacity": 1.0},
    "image": {"opacity": 1.0},
    "redact": {},
    "placeholder": {"for": "initials"},
    "attach": {"stroke": "#0050ff", "icon": "Paperclip", "opacity": 1.0},
}
# display names (Markups list, Properties, measurement text in the markup): never read back
LABELS = {"addtext": tr("Add text"), "edittext": tr("Edit text"), "highlight": tr("Highlight"),
          "comment": tr("Comment"), "underline": tr("Underline"),
          "strikeout": tr("Strikeout"), "squiggly": tr("Squiggly"), "note": tr("Sticky note"),
          "textbox": tr("Text box"),
          "rect": tr("Rectangle"), "ellipse": tr("Ellipse"), "line": tr("Line"), "arrow": tr("Arrow"),
          "ink": tr("Pen"), "polygon": tr("Polygon"), "polyline": tr("Polyline"),
          "callout": tr("Callout"),
          "stamp": tr("Stamp"), "field": tr("Form field"), "cloud": tr("Cloud"),
          "m_length": tr("Length"), "m_poly": tr("Polylength"), "m_area": tr("Area"),
          "m_count": tr("Count"),
          "m_angle": tr("Angle"), "m_radius": tr("Radius"), "m_perimeter": tr("Perimeter"),
          "m_volume": tr("Volume"),
          "image": tr("Image"), "attach": tr("Attached file"), "redact": tr("Redaction mark"),
          "placeholder": tr("Signature placeholder")}
# fonts a text box comment can use: the standard ones every PDF viewer has, so it looks the
# same everywhere (FreeText annotations can't carry other fonts reliably)
COMMENT_FONTS = {"Helvetica": "helv", "Times": "TiRo", "Courier": "Cour"}

# tools that write text into the page itself (not annotations): their settings live here too
PAGE_TEXT_TOOLS = {
    "addtext": {"font": "", "bold": False, "italic": False, "fontsize": 12,
                "text_color": "#000000"},
    "edittext": {"font": "", "bold": False, "italic": False, "fontsize": 0},   # 0: keep the line's
}

# printed in the sign-here box (made from the placeholder's kind, never read back)
PLACEHOLDER_TEXT = {"signature": tr("SIGN HERE"), "initials": tr("INITIAL HERE")}
HEADS = {"open": pymupdf.PDF_ANNOT_LE_OPEN_ARROW, "closed": pymupdf.PDF_ANNOT_LE_CLOSED_ARROW,
         "open (reversed)": pymupdf.PDF_ANNOT_LE_R_OPEN_ARROW,
         "closed (reversed)": pymupdf.PDF_ANNOT_LE_R_CLOSED_ARROW,
         "circle": pymupdf.PDF_ANNOT_LE_CIRCLE, "square": pymupdf.PDF_ANNOT_LE_SQUARE,
         "diamond": pymupdf.PDF_ANNOT_LE_DIAMOND, "bar": pymupdf.PDF_ANNOT_LE_BUTT}
MARKUP = ("highlight", "comment", "underline", "strikeout", "squiggly")
COMMENT_STYLES = ["highlight", "underline", "strikeout", "squiggly"]   # how a comment marks text      # tied to text: not movable
BOXED = ("rect", "ellipse", "textbox", "field", "callout", "stamp", "image", "attach", "redact",
         "placeholder")
MEASURES = ("m_length", "m_poly", "m_area", "m_count", "m_angle", "m_radius", "m_perimeter",
            "m_volume")
CLOSED_MEASURES = ("m_area", "m_perimeter", "m_volume")      # drawn as a closed outline
POINTED = ("line", "arrow", "polygon", "polyline") + MEASURES   # geometry = list of points
VERTEXED = ("polygon", "polyline", "m_poly", "m_angle") + CLOSED_MEASURES          # one handle per vertex                           # resizable via a rect
# Shapes with a "rotation" property (degrees, counterclockwise as seen on screen). Boxes keep
# their unrotated box and are drawn turned; point-based shapes have their points turned.
# Text boxes and callouts only turn in 90 degree steps (a PDF text box limitation).
ROTATABLE = ("rect", "ellipse", "cloud", "polygon", "polyline", "line", "arrow", "ink", "stamp", "image",
             "m_length", "m_poly", "m_area", "m_angle", "m_radius", "m_perimeter", "m_volume",
             "textbox", "callout")
QUARTER_TURNS = ("textbox", "callout")
for _k in ROTATABLE:
    DEFAULTS[_k]["rotation"] = 0
_TYPE_KIND = {pymupdf.PDF_ANNOT_SQUARE: "rect", pymupdf.PDF_ANNOT_CIRCLE: "ellipse",
              pymupdf.PDF_ANNOT_INK: "ink", pymupdf.PDF_ANNOT_FREE_TEXT: "textbox",
              pymupdf.PDF_ANNOT_TEXT: "note", pymupdf.PDF_ANNOT_HIGHLIGHT: "highlight",
              pymupdf.PDF_ANNOT_UNDERLINE: "underline",
              pymupdf.PDF_ANNOT_STRIKE_OUT: "strikeout", pymupdf.PDF_ANNOT_SQUIGGLY: "squiggly",
              pymupdf.PDF_ANNOT_LINE: "line", pymupdf.PDF_ANNOT_POLYGON: "polygon",
              pymupdf.PDF_ANNOT_POLY_LINE: "polyline", pymupdf.PDF_ANNOT_STAMP: "stamp",
              pymupdf.PDF_ANNOT_FILE_ATTACHMENT: "attach",
              pymupdf.PDF_ANNOT_REDACT: "redact"}


# ---- colors ----------------------------------------------------------------
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
    from . import paths
    return paths.settings()


def _all_saved():
    """{tool: {prop: value}} as saved (anything that isn't is left out)."""
    from . import paths
    allp = paths.stored_json(_settings(), "tool_defaults", {})
    return {k: p for k, p in allp.items() if isinstance(p, dict)}


def _fits(default, v):
    """True if a saved value can stand in for the default (a hand-edited or older setting
    can hold anything): the same kind of value, a color may be none."""
    if default is None or isinstance(default, str):
        return v is None or isinstance(v, str)
    if isinstance(default, bool):
        return isinstance(v, bool)
    if isinstance(default, (int, float)):
        return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
    return isinstance(v, type(default))


def _saved(kind, props):
    """The tool's saved values that fit props."""
    return {k: v for k, v in _all_saved().get(kind, {}).items()
            if k in props and _fits(props[k], v)}


# A Tool Chest item in use: (tool, props) that replace the tool's defaults until another
# tool is picked normally.
OVERRIDE = {"tool": None, "props": None}
# Edit text's font and size apply to the line being edited only: never saved, back to "keep
# the line's" after each edit (a size kept from an earlier edit quietly resized later ones)
TRANSIENT_TOOLS = ("edittext",)
_TRANSIENT = {}


def tool_props(kind):
    props = dict(DEFAULTS.get(kind) or PAGE_TEXT_TOOLS.get(kind, {}))
    if kind in TRANSIENT_TOOLS:
        props.update({k: v for k, v in _TRANSIENT.get(kind, {}).items() if k in props})
        return props
    if OVERRIDE["tool"] == kind and OVERRIDE["props"] is not None:
        props.update({k: v for k, v in OVERRIDE["props"].items() if k in props})
    else:
        props.update(_saved(kind, props))
    if "rotation" in props:
        props["rotation"] = 0              # new markups always start upright
    return props


def saved_tool_props(kind):
    """The tool's saved default style (ignores a Tool Chest item in use)."""
    props = dict(DEFAULTS.get(kind, {}))
    props.update(_saved(kind, props))
    return props


def set_tool_props(kind, props):
    if kind in TRANSIENT_TOOLS:
        _TRANSIENT[kind] = dict(props)
        return
    allp = _all_saved()
    allp[kind] = props
    _settings().setValue("tool_defaults", json.dumps(allp))


def reset_tool_props(kind):
    set_tool_props(kind, dict(DEFAULTS.get(kind) or PAGE_TEXT_TOOLS[kind]))


def forget_saved_transient():
    """Drop Edit text font / size choices saved by versions before 1.2.1."""
    allp = _all_saved()
    if any(k in allp for k in TRANSIENT_TOOLS):
        for k in TRANSIENT_TOOLS:
            allp.pop(k, None)
        _settings().setValue("tool_defaults", json.dumps(allp))


def author():
    """Name on stamps and recorded on new markups (Edit > Your name on stamps and markups).
    Defaults to the Windows login name."""
    from . import paths
    name = paths.stored_str(_settings(), "author")
    if not name:
        try:
            name = getpass.getuser()
        except Exception:
            name = ""
    return name


def set_author(name):
    _settings().setValue("author", name)


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
    if kind != "textbox":                      # FreeText keeps its colors elsewhere
        if cols.get("stroke"):
            props["stroke"] = to_hex(cols["stroke"])
        if "fill" in props:
            props["fill"] = to_hex(cols.get("fill")) or None
    if "width" in props and annot.border and annot.border.get("width", -1) > 0:
        props["width"] = annot.border["width"]
    if annot.opacity is not None and 0 <= annot.opacity < 1:
        props["opacity"] = annot.opacity
    props.update({k: v for k, v in stored.get("props", {}).items() if k in props})

    flags = annot.flags or 0
    model = {"kind": kind, "props": props, "text": annot.info.get("content", ""),
             "locked": bool(flags & pymupdf.PDF_ANNOT_IS_LOCKED),
             "hidden": bool(flags & pymupdf.PDF_ANNOT_IS_HIDDEN),
             "rect": pymupdf.Rect(annot.rect), "author": annot.info.get("title", ""),
             "created": annot.info.get("creationDate", "")}
    verts = annot.vertices or []
    geom = stored.get("geom", {})
    if kind in ("line", "arrow"):
        model["points"] = [pymupdf.Point(v) for v in verts[:2]]
    elif kind in ("polygon", "polyline", "m_poly", "m_angle") + CLOSED_MEASURES:
        model["points"] = [pymupdf.Point(v) for v in verts]
    elif kind in ("m_length", "m_radius"):
        model["points"] = [pymupdf.Point(v) for v in verts[:2]]
    elif kind == "m_count":
        model["points"] = [pymupdf.Point(geom.get("at", annot.rect.tl + (5, 5)))]
        model["n"] = geom.get("n", 1)
    elif kind == "callout":
        model["rect"] = pymupdf.Rect(geom.get("box", annot.rect))
        model["points"] = [pymupdf.Point(geom.get("target", annot.rect.bl))]
    elif kind == "stamp":
        model["detail"] = geom.get("detail")
        if geom.get("box"):
            model["rect"] = pymupdf.Rect(geom["box"])
    elif kind == "image":
        model["img"] = geom.get("img")
        if geom.get("box"):
            model["rect"] = pymupdf.Rect(geom["box"])
    elif kind == "attach":
        try:
            info = annot.file_info
            model["filename"] = info.get("filename", "")
            model["text"] = info.get("description", "") or model["text"]
        except Exception:
            model["filename"] = ""
        try:
            props["icon"] = doc.xref_get_key(annot.xref, "Name")[1].lstrip("/") or props["icon"]
        except Exception:
            pass
    elif kind in ("rect", "ellipse", "placeholder", "textbox") and geom.get("box"):
        model["rect"] = pymupdf.Rect(geom["box"])
    elif kind in ("rect", "ellipse", "textbox") and stored:
        # made by an older version: the PDF rect includes half the border on each side
        hw = float(props.get("width", 0) or 0) / 2 if props.get("stroke") else 0
        model["rect"] = pymupdf.Rect(annot.rect) + (hw, hw, -hw, -hw)
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
    """PDF FreeText draws its border in the text color. Patch our appearance so the
    border uses its own color: the first RG operator in the stream strokes the frame."""
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
    if stroke is None and kind in ("textbox", "callout", "rect", "ellipse", "polygon") + CLOSED_MEASURES:
        width = 0.0                          # "No border"
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
    elif kind in ("rect", "ellipse") and turned(model):
        # PDF squares and circles can't be rotated: draw the turned outline as a polygon
        a = page.add_polygon_annot([(q.x, q.y) for q in outline(model)])
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
    elif kind in ("polygon",) + CLOSED_MEASURES:
        a = page.add_polygon_annot([(q.x, q.y) for q in model["points"]])
    elif kind == "m_length":
        a = page.add_line_annot(*model["points"][:2])
        a.set_line_ends(pymupdf.PDF_ANNOT_LE_BUTT, pymupdf.PDF_ANNOT_LE_BUTT)
    elif kind == "m_radius":
        a = page.add_line_annot(*model["points"][:2])
        a.set_line_ends(pymupdf.PDF_ANNOT_LE_CIRCLE, pymupdf.PDF_ANNOT_LE_OPEN_ARROW)
    elif kind == "m_angle":
        a = page.add_polyline_annot([(q.x, q.y) for q in model["points"]])
    elif kind == "m_poly":
        a = page.add_polyline_annot([(q.x, q.y) for q in model["points"]])
    elif kind == "m_count":
        c = model["points"][0]
        a = page.add_circle_annot(pymupdf.Rect(c.x - 5, c.y - 5, c.x + 5, c.y + 5))
    elif kind == "polyline":
        a = page.add_polyline_annot([(q.x, q.y) for q in model["points"]])
    elif kind == "callout":
        box, target = pymupdf.Rect(model["rect"]), model["points"][0]
        # leader line runs from the target to the nearest middle of a box edge
        knees = [pymupdf.Point(box.x0, (box.y0 + box.y1) / 2), pymupdf.Point(box.x1, (box.y0 + box.y1) / 2),
                 pymupdf.Point((box.x0 + box.x1) / 2, box.y0), pymupdf.Point((box.x0 + box.x1) / 2, box.y1)]
        knee = min(knees, key=lambda k: abs(k - target))
        a = page.add_freetext_annot(box, text, fontsize=float(p.get("fontsize", 11)),
                                    fontname="helv",
                                    text_color=to_rgb(p.get("text_color")) or (0, 0, 0),
                                    fill_color=fill, border_width=width,
                                    callout=((target.x, target.y), (knee.x, knee.y)),
                                    line_end=HEADS.get(p.get("head"), HEADS["open"]),
                                    rotate=(page.rotation + quarter(p)) % 360)
    elif kind == "stamp":
        from . import stamps
        label = p.get("label") or tr("APPROVED")
        if model.get("detail") is None and not label.startswith(stamps.FORM_PREFIX):
            model["detail"] = stamps.detail_line(model.get("author") or author(),
                                                 p.get("name", True), p.get("date", True))
        if label.startswith(stamps.IMAGE_PREFIX):
            png, _aspect = stamps.image_stamp(label[len(stamps.IMAGE_PREFIX):])
        elif label.startswith(stamps.FORM_PREFIX):
            png, _aspect = stamps.render_form(stamps.form_fields(label),
                                              (model.get("detail") or "").split("\n"),
                                              p.get("stroke") or "#c00000")
        else:
            png, _aspect = stamps.render(label, p.get("stroke") or "#c00000", model["detail"])
        if png is None:
            raise ValueError(tr("The stamp image is missing from the stamp library."))
        turn = page.rotation + angle(model)
        if turn % 360:
            # pre-rotate the image: undo the page's display rotation (so it reads upright)
            # and add the stamp's own rotation (Qt turns clockwise, ours is counterclockwise)
            from PySide6.QtCore import Qt as _Qt
            from PySide6.QtGui import QImage, QTransform
            from .signatures import qimage_to_png
            img = QImage.fromData(png).convertToFormat(QImage.Format_ARGB32)
            png = qimage_to_png(img.transformed(QTransform().rotate(-turn), _Qt.SmoothTransformation))
        a = page.add_stamp_annot(bounds(model), stamp=pymupdf.Pixmap(png))
    elif kind == "image":
        if model.get("img"):
            # reuse the image already in the file (moving / resizing never re-encodes it)
            a = page.add_stamp_annot(bounds(model), stamp=_PLACEHOLDER_PNG())
        else:
            a = page.add_stamp_annot(bounds(model), stamp=model["image_bytes"])
    elif kind == "redact":
        a = page.add_redact_annot(model["rect"], fill=(0, 0, 0))
        a.set_colors(stroke=(0.85, 0, 0))
    elif kind == "placeholder":
        who = p.get("for", "initials")
        a = page.add_freetext_annot(model["rect"], PLACEHOLDER_TEXT.get(who, PLACEHOLDER_TEXT["signature"]),
                                    fontsize=min(10.0, max(5.0, model["rect"].height * 0.4)),
                                    fontname="helv", text_color=(0.75, 0, 0),
                                    fill_color=(1, 1, 0.75), border_width=1, align=1,
                                    rotate=page.rotation)
    elif kind == "attach":
        a = page.add_file_annot(model["rect"].tl, model["file_bytes"], model["filename"],
                                desc=text or model["filename"], icon=p.get("icon") or "Paperclip")
    elif kind == "note":
        a = page.add_text_annot(model["rect"].tl, text or " ", icon="Note")
    elif kind == "textbox":
        a = page.add_freetext_annot(model["rect"], text, fontsize=float(p.get("fontsize", 11)),
                                    fontname=COMMENT_FONTS.get(p.get("font"), "helv"),
                                    text_color=to_rgb(p.get("text_color")) or (0, 0, 0),
                                    fill_color=fill, border_width=width,
                                    rotate=(page.rotation + quarter(p)) % 360)
    else:
        raise ValueError("unknown annotation kind " + kind)

    if kind not in ("textbox", "callout", "stamp", "image", "redact", "placeholder"):
        if kind in ("rect", "ellipse", "polygon") + CLOSED_MEASURES:
            # stroke [] = no outline at all (width 0 alone still draws a hairline)
            a.set_colors(stroke=stroke if stroke else [], fill=fill)
        elif kind == "m_count":
            a.set_colors(stroke=stroke, fill=stroke)
        elif kind == "arrow" and "closed" in (p.get("head") or ""):
            a.set_colors(stroke=stroke, fill=stroke)
        else:
            a.set_colors(stroke=stroke)
        if kind in ("rect", "ellipse", "polygon") and p.get("cloud"):
            a.set_border(width=width, clouds=2)
        elif kind in ("rect", "ellipse", "line", "arrow", "ink", "polygon", "polyline",
                      "m_length", "m_poly", "m_angle", "m_radius") + CLOSED_MEASURES:
            a.set_border(width=width)
    if p.get("opacity", 1) < 1:
        a.set_opacity(float(p["opacity"]))
    if text and kind not in ("textbox", "callout"):
        a.set_info(content=text)
    now = pymupdf.get_pdf_now()
    info = {"title": model.get("author") or author(), "modDate": now,
            "creationDate": model.get("created") or now}
    label_text = None
    if kind in MEASURES:
        from . import measure
        if kind == "m_count":
            label_text = str(model.get("n", 1))
            info["content"] = f"{p.get('group') or 'Count'} #{model.get('n', 1)}"
        else:
            label_text = measure.measure_text(kind, model["points"], page, props=p)
            info["content"] = f"{LABELS[kind]}: " + label_text.replace("\n", ", ")
    if kind == "image":
        info["content"] = text or model.get("filename") or tr("Image")
    if kind == "redact":
        info["content"] = text or tr("Redaction (not applied yet)")
    if kind == "placeholder":
        info["content"] = PLACEHOLDER_TEXT.get(p.get("for"), PLACEHOLDER_TEXT["signature"]).capitalize()
    if kind == "stamp":
        from . import stamps
        label = p.get("label") or ""
        if label.startswith(stamps.FORM_PREFIX):
            # a fill-in stamp reads "PO # PO-4471, Date ordered 10/26/2026"
            values = (model.get("detail") or "").split("\n")
            info["content"] = ", ".join(
                f"{name} {values[k] if k < len(values) else ''}".strip()
                for k, name in enumerate(stamps.form_fields(label)))
        else:
            info["content"] = label.replace(stamps.IMAGE_PREFIX, "") + \
                (f" ({model['detail']})" if model.get("detail") else "")
    a.set_info(**info)
    if kind == "comment" and model.get("quads"):
        anchor = pymupdf.Rect()
        for q in model["quads"]:
            anchor |= q.rect
        a.set_popup(_popup_rect(page, anchor))
        a.set_open(False)
    a.update()

    doc = page.parent
    if kind in ("textbox", "callout") and width > 0 and stroke:
        _recolor_textbox_border(doc, a, stroke)
    store = {"kind": kind, "props": p}
    if kind == "callout":
        store["geom"] = {"box": list(model["rect"]), "target": list(model["points"][0])}
    elif kind == "stamp":
        store["geom"] = {"detail": model.get("detail") or ""}
        if turned(model):
            store["geom"]["box"] = list(model["rect"])
    elif kind == "image":
        store["geom"] = {"img": _image_appearance(page, a, model), "box": list(model["rect"])}
    elif kind in ("rect", "ellipse", "placeholder", "textbox"):
        # keep the exact box: the PDF rect grows by the border width (would creep on edits)
        store["geom"] = {"box": list(model["rect"])}
    elif kind == "m_count":
        store["geom"] = {"at": list(model["points"][0]), "n": model.get("n", 1)}
    doc.xref_set_key(a.xref, KZ_KEY, pymupdf.get_pdf_str(json.dumps(store)))
    keep = (pymupdf.PDF_ANNOT_IS_LOCKED if model.get("locked") else 0) | \
        (pymupdf.PDF_ANNOT_IS_HIDDEN if model.get("hidden") else 0)
    if keep:
        a.set_flags((a.flags or 0) | keep)
    if kind == "m_radius":
        from . import measure
        measure.add_circle(page, a, model["points"][0], model["points"][1], stroke or (0, 0, 0),
                           width)
    if label_text:
        from . import measure
        anchor, lab_angle = measure.label_anchor(kind, model["points"], page)
        measure.add_label(page, a, label_text, anchor, float(p.get("fontsize", 9)),
                          stroke or (0, 0, 0), lab_angle)
    return a


# ---- images ------------------------------------------------------------------------
_PLACEHOLDER = []


def _PLACEHOLDER_PNG():
    if not _PLACEHOLDER:
        pm = pymupdf.Pixmap(pymupdf.csRGB, (0, 0, 1, 1), False)
        _PLACEHOLDER.append(pm.tobytes("png"))
    return _PLACEHOLDER[0]


def _image_appearance(page, a, model):
    """Point the stamp's appearance at the image object (an existing one when the image is
    being moved / resized) and draw it turned by the page and markup rotation without
    resampling. Returns the image object's xref."""
    doc = page.parent
    ap = int(doc.xref_get_key(a.xref, "AP/N")[1].split()[0])
    typ, val = doc.xref_get_key(ap, "Resources/XObject/I")
    img = int(model["img"]) if model.get("img") else int(val.split()[0])
    doc.xref_set_key(ap, "Resources/XObject/I", f"{img} 0 R")
    # the image box as seen on screen, turned by the page's display rotation
    r = pymupdf.Rect(model["rect"])
    w, h = (r.height, r.width) if page.rotation in (90, 270) else (r.width, r.height)
    turn = math.radians(page.rotation + angle(model))
    b = bounds(model)
    W, H = b.width, b.height
    co, si = math.cos(turn), math.sin(turn)
    e = W / 2 - (w / 2 * co - h / 2 * si)
    f = H / 2 - (w / 2 * si + h / 2 * co)
    doc.xref_set_key(ap, "BBox", f"[0 0 {W:.4f} {H:.4f}]")
    # PyMuPDF shrinks a stamp's Rect to the picture's proportions: use the real box
    pr = (b * pdfcoords.to_pdf(page)).normalize()
    doc.xref_set_key(a.xref, "Rect", f"[{pr.x0:.4f} {pr.y0:.4f} {pr.x1:.4f} {pr.y1:.4f}]")
    doc.update_stream(ap, (f"q {w * co:.5f} {w * si:.5f} {-h * si:.5f} {h * co:.5f} "
                           f"{e:.4f} {f:.4f} cm /I Do Q\n").encode())
    # keep a direct reference so the image survives even if the appearance is rebuilt
    doc.xref_set_key(a.xref, "KZImage", f"{img} 0 R")
    return img


def image_bytes(doc, xref):
    """Encoded image (PNG/JPEG...) of an image object, for saving it back out."""
    info = doc.extract_image(xref)
    if not info.get("smask"):
        return info["image"], info.get("ext", "png")
    pm = pymupdf.Pixmap(pymupdf.Pixmap(info["image"]), pymupdf.Pixmap(doc.extract_image(info["smask"])["image"]))
    return pm.tobytes("png"), "png"


# ---- rotation --------------------------------------------------------------------
def angle(model):
    try:
        return float(model["props"].get("rotation") or 0) % 360
    except (TypeError, ValueError):
        return 0.0


def quarter(props):
    """Text box rotation, snapped to 0/90/180/270."""
    try:
        return int(round(float(props.get("rotation") or 0) / 90.0)) * 90 % 360
    except (TypeError, ValueError):
        return 0


def turned(model):
    """A box shape drawn rotated (its model keeps the unrotated box)."""
    return model["kind"] in ("rect", "ellipse", "stamp", "image") and abs(angle(model)) > 1e-6 \
        and abs(angle(model) - 360) > 1e-6


def rotate_point(q, c, deg):
    """Turn point q around c by deg, counterclockwise on screen (y grows downward)."""
    r = math.radians(deg)
    co, si = math.cos(r), math.sin(r)
    dx, dy = q.x - c.x, q.y - c.y
    return pymupdf.Point(c.x + dx * co + dy * si, c.y - dx * si + dy * co)


def outline(model, steps=72):
    """Turned outline of a rect / ellipse / stamp box as a list of points."""
    r = pymupdf.Rect(model["rect"])
    c = pymupdf.Point((r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2)
    if model["kind"] == "ellipse":
        rx, ry = r.width / 2, r.height / 2
        pts = [pymupdf.Point(c.x + rx * math.cos(2 * math.pi * k / steps),
                             c.y + ry * math.sin(2 * math.pi * k / steps)) for k in range(steps)]
    else:
        pts = [r.tl, r.tr, r.br, r.bl]
    return [rotate_point(q, c, angle(model)) for q in pts]


def rotated(model, new_angle):
    """Copy of the model turned to new_angle degrees (point shapes turn around their center)."""
    m = copy(model)
    if model["kind"] not in ROTATABLE:
        return m
    new_angle = float(new_angle) % 360
    if model["kind"] in QUARTER_TURNS:
        new_angle = int(round(new_angle / 90.0)) * 90 % 360
    delta = new_angle - angle(model)
    m["props"]["rotation"] = round(new_angle, 2)
    if model["kind"] in POINTED or model["kind"] == "ink":
        c = bounds(model)
        c = pymupdf.Point((c.x0 + c.x1) / 2, (c.y0 + c.y1) / 2)
        if "points" in m:
            m["points"] = [rotate_point(q, c, delta) for q in m["points"]]
        if "strokes" in m:
            m["strokes"] = [[rotate_point(q, c, delta) for q in s] for s in m["strokes"]]
    return m


# ---- geometry edits on a model -------------------------------------------------
def bounds(model):
    """Rect that the selection handles act on."""
    if turned(model):
        pts = outline(model)
        r = pymupdf.Rect(pts[0], pts[0])
        for q in pts[1:]:
            r |= q
        return r
    if model["kind"] in POINTED:
        r = pymupdf.Rect(model["points"][0], model["points"][0])
        for q in model["points"][1:]:
            r |= q
        return r
    if model["kind"] == "ink":
        pts = [q for s in model["strokes"] for q in s]
        r = pymupdf.Rect(pts[0], pts[0])
        for q in pts[1:]:
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


def text_editable(model):
    """Edit text... can change the markup's text. A measurement's, a stamp's and a sign-here
    placeholder's text is made from what they are (a fill-in stamp's values can change)."""
    kind = model["kind"]
    if kind == "stamp":
        from . import stamps
        return (model["props"].get("label") or "").startswith(stamps.FORM_PREFIX)
    return kind not in MEASURES + ("placeholder", "field")


def copy(model):
    m = dict(model)
    m["props"] = dict(model["props"])
    if model["kind"] == "callout" and "points" in m:
        m["points"] = [pymupdf.Point(q) for q in m["points"]]
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


def transformed(model, mat):
    """Copy of the markup under mat (a Matrix in page coordinates: a CAD tab Move, Rotate,
    Scale, Mirror or Align). Lines, polygons, clouds, ink and measurements follow it exactly;
    a box (rectangle, ellipse, stamp, picture, text box...) goes by its center, its size and
    its turn (a picture or stamp keeps reading the right way round when mirrored; text boxes
    and callouts turn in quarter turns). Highlighted words' quads only move."""
    mat = pymupdf.Matrix(mat)
    m = copy(model)
    if "points" in m:
        m["points"] = [pymupdf.Point(q) * mat for q in m["points"]]
    if "strokes" in m:
        m["strokes"] = [[pymupdf.Point(q) * mat for q in s] for s in m["strokes"]]
    if "quads" in m:
        d = pymupdf.Point(mat.e, mat.f)
        m["quads"] = [pymupdf.Quad(q.ul + d, q.ur + d, q.ll + d, q.lr + d) for q in m["quads"]]
    if "rect" in m:
        r = pymupdf.Rect(m["rect"])
        c = pymupdf.Point((r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2) * mat
        sx, sy = math.hypot(mat.a, mat.b), math.hypot(mat.c, mat.d)
        if model["kind"] in POINTED or model["kind"] == "ink":
            sx = sy = 1.0               # (a box kept with the points: they say where it is)
        w, h = r.width * sx, r.height * sy
        turn = math.degrees(math.atan2(mat.b, mat.a))          # clockwise on screen
        mirrored = mat.a * mat.d - mat.b * mat.c < 0
        a = angle(model)
        if mirrored:
            # a mirror image of a box is the same box turned: of the two turns that give it,
            # the one nearer upright, so stamps, pictures and text keep reading the right way
            new = min(((-a - turn) % 360, (-a - turn + 180) % 360),
                      key=lambda x: min(x, 360 - x))
        else:
            new = (a - turn) % 360
        if model["kind"] in ("rect", "ellipse"):
            new %= 180                  # (turned half round, they're the same shape)
        if model["kind"] in QUARTER_TURNS:
            # text boxes and callouts turn in quarter turns; a quarter turn turns their box
            q = int(round((new - a) / 90.0)) % 4
            new = int(round(new / 90.0)) * 90 % 360
            if q % 2:
                w, h = h, w
        if model["kind"] in ROTATABLE + QUARTER_TURNS and \
                model["kind"] not in POINTED + ("ink",) and abs(new - a) > 1e-6:
            m["props"]["rotation"] = round(new, 2) if model["kind"] not in QUARTER_TURNS \
                else new
        m["rect"] = pymupdf.Rect(c.x - w / 2, c.y - h / 2, c.x + w / 2, c.y + h / 2)
    return m


def page_turned(model, turn):
    """Copy of the markup for a page turned `turn` degrees (a multiple of 90) less than the
    one it was copied from, so it looks the same on screen there: its points and box turn
    with the page (a box's sides swap on a quarter turn). Its own turn is kept: a markup's
    rotation is counted from the page as shown (see write)."""
    turn = int(round(turn / 90.0)) * 90 % 360
    m = copy(model)
    if not turn:
        return m
    mat = pymupdf.Matrix(turn)
    if "points" in m:
        m["points"] = [pymupdf.Point(q) * mat for q in m["points"]]
    if "strokes" in m:
        m["strokes"] = [[pymupdf.Point(q) * mat for q in s] for s in m["strokes"]]
    if "quads" in m:
        m["quads"] = [pymupdf.Quad(q) * mat for q in m["quads"]]
    if "rect" in m:
        r = pymupdf.Rect(m["rect"])
        c = pymupdf.Point((r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2) * mat
        w, h = (r.height, r.width) if turn in (90, 270) else (r.width, r.height)
        m["rect"] = pymupdf.Rect(c.x - w / 2, c.y - h / 2, c.x + w / 2, c.y + h / 2)
    return m


def resized(model, new_rect):
    """Fit the annotation to new_rect (boxes directly, ink and lines by scaling)."""
    m = copy(model)
    old = bounds(model)
    new_rect = pymupdf.Rect(new_rect).normalize()
    if turned(m):
        # fit the turned box so its outline's bounding box becomes new_rect
        r = pymupdf.Rect(m["rect"])
        rad = math.radians(angle(m))
        c, s_ = abs(math.cos(rad)), abs(math.sin(rad))
        W, H = new_rect.width, new_rect.height
        det = c * c - s_ * s_
        if abs(det) > 0.2:
            w, h = (W * c - H * s_) / det, (H * c - W * s_) / det
        else:                              # near 45 degrees: scale evenly
            k = ((W / old.width if old.width else 1) + (H / old.height if old.height else 1)) / 2
            w, h = r.width * k, r.height * k
        w, h = max(w, 2), max(h, 2)
        cx, cy = (new_rect.x0 + new_rect.x1) / 2, (new_rect.y0 + new_rect.y1) / 2
        m["rect"] = pymupdf.Rect(cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)
        return m
    if m["kind"] in BOXED:
        m["rect"] = new_rect             # (a callout's target point stays where it is)
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


# ---- stacking order (front / back) -----------------------------------------------
def annot_order(page):
    """xrefs in the page's /Annots array, back to front."""
    doc = page.parent
    typ, val = doc.xref_get_key(page.xref, "Annots")
    if typ == "xref":
        val = doc.xref_object(int(val.split()[0]), compressed=True)
    elif typ != "array":
        return []
    nums = val.strip("[]").split()
    return [int(nums[i]) for i in range(0, len(nums) - 2, 3) if nums[i + 2] == "R"]


def set_annot_order(page, xrefs):
    """Rewrite /Annots in this order (back to front). Drop all Annot/Page objects of this
    page afterwards and reload it: MuPDF keeps its own list for a loaded page."""
    page.parent.xref_set_key(page.xref, "Annots", "[" + " ".join(f"{x} 0 R" for x in xrefs) + "]")


def replace_many(page, changes):
    """replace() for several annotations at once ([(xref, model)], in that order), as when
    many markups are aligned, restyled or nudged together: each one is found in one walk of
    the page and the stacking order is read and written once, not once for each (N squared
    steps: 18 s for 1,000 markups). Returns [(old xref, its old model or None, new xref)]."""
    by_xref = load_annots(page, [x for x, _m in changes])
    order = annot_order(page)
    place = {x: k for k, x in enumerate(order)}
    out = []
    olds = {}
    for xref, _model in changes:            # read them all first...
        a = by_xref.pop(xref, None)
        if a is None:
            a = page.load_annot(xref)       # (raises, like replace(), if it's gone)
        try:
            olds[xref] = read(a)
        except Exception:
            olds[xref] = None
        del a
    by_xref.clear()
    # ...then the old ones go in one look through the page (one at a time, each delete looked
    # through all the page's markups for replies: minutes for a few thousand)
    pdf_speed.delete_many(page, [x for x, m in changes if m["kind"] != "attach"])
    for xref, model in changes:
        if model["kind"] == "attach":
            out.append((xref, olds[xref], replace(page, xref, model)))
            continue
        out.append((xref, olds[xref], write(page, model).xref))
    # each new one takes its old one's place in the stacking order (anything else made on
    # the way, a pop-up note, stays on top as it was added)
    now = annot_order(page)
    new_at = {new: place[x] for x, _old, new in out if x in place and new != x}
    if new_at:
        kept = set(now)
        slots = list(order)
        for new, k in new_at.items():
            slots[k] = new
        final = [x for x in slots if x in kept]
        placed = set(final)
        final += [x for x in now if x not in placed]
        if final != now:
            set_annot_order(page, final)
    return out


def replace(page, xref, model):
    """Swap annotation xref for a newly written model, keeping its place in the stacking
    order. Returns the new xref."""
    if model["kind"] == "attach":
        # the embedded file stays where it is: only its icon moves / restyles
        a = page.load_annot(xref)
        a.set_rect(pymupdf.Rect(model["rect"].tl, model["rect"].tl + (a.rect.width, a.rect.height)))
        a.set_colors(stroke=to_rgb(model["props"].get("stroke")))
        a.set_opacity(float(model["props"].get("opacity", 1)))
        a.update()
        return xref
    order = annot_order(page)
    pos = order.index(xref) if xref in order else None
    page.delete_annot(page.load_annot(xref))
    new = write(page, model).xref
    if pos is not None:
        order = annot_order(page)
        if new in order:
            order.remove(new)
            order.insert(min(pos, len(order)), new)
            set_annot_order(page, order)
    return new
