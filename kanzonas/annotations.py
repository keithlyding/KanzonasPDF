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
    "m_count": {"stroke": "#0050ff", "fontsize": 9, "group": "Count 1", "opacity": 1.0},
    "stamp": {"label": "APPROVED", "stroke": "#c00000", "name": True, "date": True, "opacity": 1.0},
    "line": {"stroke": "#0050ff", "width": 2.0, "opacity": 1.0},
    "arrow": {"stroke": "#d00000", "width": 2.0, "head": "open", "opacity": 1.0},
    "ink": {"stroke": "#0050ff", "width": 2.0, "opacity": 1.0},
    "image": {"opacity": 1.0},
    "redact": {},
    "placeholder": {"for": "initials"},
    "attach": {"stroke": "#0050ff", "icon": "Paperclip", "opacity": 1.0},
}
ATTACH_ICONS = ["Paperclip", "PushPin", "Graph", "Tag"]
LABELS = {"highlight": "Highlight", "comment": "Comment", "underline": "Underline",
          "strikeout": "Strikeout", "squiggly": "Squiggly", "note": "Sticky note", "textbox": "Text box",
          "rect": "Rectangle", "ellipse": "Ellipse", "line": "Line", "arrow": "Arrow",
          "ink": "Pen", "polygon": "Polygon", "polyline": "Polyline", "callout": "Callout",
          "stamp": "Stamp", "field": "Form field", "cloud": "Cloud",
          "m_length": "Length", "m_poly": "Polylength", "m_area": "Area", "m_count": "Count",
          "image": "Image", "attach": "Attached file", "redact": "Redaction mark",
          "placeholder": "Signature placeholder"}
PLACEHOLDER_TEXT = {"signature": "SIGN HERE", "initials": "INITIAL HERE"}
HEADS = {"open": pymupdf.PDF_ANNOT_LE_OPEN_ARROW, "closed": pymupdf.PDF_ANNOT_LE_CLOSED_ARROW,
         "open (reversed)": pymupdf.PDF_ANNOT_LE_R_OPEN_ARROW,
         "closed (reversed)": pymupdf.PDF_ANNOT_LE_R_CLOSED_ARROW,
         "circle": pymupdf.PDF_ANNOT_LE_CIRCLE, "square": pymupdf.PDF_ANNOT_LE_SQUARE,
         "diamond": pymupdf.PDF_ANNOT_LE_DIAMOND, "bar": pymupdf.PDF_ANNOT_LE_BUTT}
MARKUP = ("highlight", "comment", "underline", "strikeout", "squiggly")
COMMENT_STYLES = ["highlight", "underline", "strikeout", "squiggly"]   # how a comment marks text      # tied to text: not movable
BOXED = ("rect", "ellipse", "textbox", "field", "callout", "stamp", "image", "attach", "redact",
         "placeholder")
MEASURES = ("m_length", "m_poly", "m_area", "m_count")
POINTED = ("line", "arrow", "polygon", "polyline") + MEASURES   # geometry = list of points
VERTEXED = ("polygon", "polyline", "m_poly", "m_area")          # one handle per vertex                           # resizable via a rect
# Shapes with a "rotation" property (degrees, counterclockwise as seen on screen). Boxes keep
# their unrotated box and are drawn turned; point-based shapes have their points turned.
# Text boxes and callouts only turn in 90 degree steps (a PDF text box limitation).
ROTATABLE = ("rect", "ellipse", "cloud", "polygon", "polyline", "line", "arrow", "ink", "stamp", "image",
             "m_length", "m_poly", "m_area", "textbox", "callout")
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
    return QSettings("KanzonasPDF", "KanzonasPDF")


# A Tool Chest item in use: (tool, props) that replace the tool's defaults until another
# tool is picked normally.
OVERRIDE = {"tool": None, "props": None}


def tool_props(kind):
    props = dict(DEFAULTS.get(kind, {}))
    if OVERRIDE["tool"] == kind and OVERRIDE["props"] is not None:
        props.update({k: v for k, v in OVERRIDE["props"].items() if k in props})
    else:
        try:
            saved = json.loads(_settings().value("tool_defaults", "{}") or "{}").get(kind, {})
            props.update({k: v for k, v in saved.items() if k in props})
        except (ValueError, TypeError):
            pass
    if "rotation" in props:
        props["rotation"] = 0              # new markups always start upright
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


def author():
    """Name on stamps and recorded on new markups (Edit > Your name on stamps and markups).
    Defaults to the Windows login name."""
    name = _settings().value("author", "") or ""
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
    elif kind in ("polygon", "polyline", "m_poly", "m_area"):
        model["points"] = [pymupdf.Point(v) for v in verts]
    elif kind == "m_length":
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
    if stroke is None and kind in ("textbox", "callout", "rect", "ellipse", "polygon", "m_area"):
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
    elif kind in ("polygon", "m_area"):
        a = page.add_polygon_annot([(q.x, q.y) for q in model["points"]])
    elif kind == "m_length":
        a = page.add_line_annot(*model["points"][:2])
        a.set_line_ends(pymupdf.PDF_ANNOT_LE_BUTT, pymupdf.PDF_ANNOT_LE_BUTT)
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
        if model.get("detail") is None:
            model["detail"] = stamps.detail_line(model.get("author") or author(),
                                                 p.get("name", True), p.get("date", True))
        label = p.get("label") or "APPROVED"
        if label.startswith(stamps.IMAGE_PREFIX):
            png, _aspect = stamps.image_stamp(label[len(stamps.IMAGE_PREFIX):])
        else:
            png, _aspect = stamps.render(label, p.get("stroke") or "#c00000", model["detail"])
        if png is None:
            raise ValueError("The stamp image is missing from the stamp library.")
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
        a = page.add_freetext_annot(model["rect"], PLACEHOLDER_TEXT.get(who, "SIGN HERE"),
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
                                    fontname="helv",
                                    text_color=to_rgb(p.get("text_color")) or (0, 0, 0),
                                    fill_color=fill, border_width=width,
                                    rotate=(page.rotation + quarter(p)) % 360)
    else:
        raise ValueError("unknown annotation kind " + kind)

    if kind not in ("textbox", "callout", "stamp", "image", "redact", "placeholder"):
        if kind in ("rect", "ellipse", "polygon", "m_area"):
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
                      "m_length", "m_poly", "m_area"):
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
            label_text = measure.measure_text(kind, model["points"], page)
            info["content"] = f"{LABELS[kind]}: " + label_text.replace("\n", ", ")
    if kind == "image":
        info["content"] = text or model.get("filename") or "Image"
    if kind == "redact":
        info["content"] = text or "Redaction (not applied yet)"
    if kind == "placeholder":
        info["content"] = PLACEHOLDER_TEXT.get(p.get("for"), "SIGN HERE").capitalize()
    if kind == "stamp":
        info["content"] = (p.get("label") or "").replace("image:", "") + \
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
    pr = (b * page.transformation_matrix).normalize()
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
