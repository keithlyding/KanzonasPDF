"""Dots: a filled or outlined dot placed with one click, with its number, a text or both
written beside it (right, below, left or above) or the number inside it.

A dot is a Circle annotation; its number is the "n" property and its text is the
annotation's content (so it is edited like any markup's text). The number and the text
are appended to the circle's appearance here, laid out as seen on screen, so they read
upright on rotated pages too.
"""

import math

import pymupdf

from . import pdfcoords

SIDES = ("right", "below", "left", "above")
SHOWS = ("none", "number", "text", "both")
_OPPOSITE = {"right": "left", "left": "right", "below": "above", "above": "below"}


def _size(props):
    return max(1.0, float(props.get("size", 6.0)))


def _fontsize(props):
    return max(1.0, float(props.get("fontsize", 9)))


def number_text(props):
    return str(props.get("n", 1))


def shows_number(props):
    return props.get("show", "number") in ("number", "both")


def shows_text(props):
    return props.get("show", "number") in ("text", "both")


def number_inside(props):
    return shows_number(props) and bool(props.get("inside"))


def radius(model):
    """The dot's radius: its size, or larger when its number is written inside it."""
    p = model["props"]
    r = _size(p) / 2
    if number_inside(p):
        fs = _fontsize(p)
        w = pymupdf.get_text_length(number_text(p), fontname="helv", fontsize=fs)
        r = max(r, max(w, fs * 0.75) / 2 + 1.5)
    return r


def box(model):
    """The dot's circle (unrotated page coordinates)."""
    c = pymupdf.Point(model["points"][0])
    r = radius(model)
    return pymupdf.Rect(c.x - r, c.y - r, c.x + r, c.y + r)


def parts(model):
    """[(text, place)]: what is written around the dot, place one of SIDES or "inside"."""
    p = model["props"]
    side = p.get("side", "right")
    if side not in SIDES:
        side = "right"
    text = (model.get("text") or "").strip()
    out = []
    if shows_text(p) and text:
        if shows_number(p):
            out.append((number_text(p), "inside" if number_inside(p) else _OPPOSITE[side]))
        out.append((text, side))
    elif shows_number(p):
        out.append((number_text(p), "inside" if number_inside(p) else side))
    return out


def _block_center(place, center, r, w, h, gap):
    """Center of a w x h text block put at place around a dot (display coordinates)."""
    if place == "right":
        return center + (r + gap + w / 2, 0)
    if place == "left":
        return center - (r + gap + w / 2, 0)
    if place == "below":
        return center + (0, r + gap + h / 2)
    if place == "above":
        return center - (0, r + gap + h / 2)
    return pymupdf.Point(center)


def _align(place):
    return {"right": "left", "left": "right"}.get(place, "center")


def layout(page, model):
    """[(lines, anchor, align, color)] for each text around the dot: anchor is the text
    block's center in unrotated page coordinates."""
    p = model["props"]
    fs = _fontsize(p)
    lead = fs * 1.2
    gap = max(1.5, fs * 0.25)
    r = radius(model) + float(p.get("width", 1.0)) / 2
    to_disp = page.rotation_matrix
    to_page = page.derotation_matrix
    center = pymupdf.Point(model["points"][0]) * to_disp
    from .annotations import to_rgb
    text_color = to_rgb(p.get("text_color")) or (0, 0, 0)
    out = []
    for text, place in parts(model):
        lines = text.split("\n")
        w = max(pymupdf.get_text_length(t, fontname="helv", fontsize=fs) for t in lines)
        h = lead * len(lines)
        at = _block_center(place, center, r, w, h, gap) * to_page
        color = text_color
        if place == "inside" and p.get("filled", True):
            color = (1, 1, 1)                   # (on the dot's own color)
        out.append((lines, at, _align(place), color))
    return out


def draw(page, annot, model):
    """Append the dot's number and text to its appearance and grow its box to hold them."""
    placed = layout(page, model)
    if not placed:
        return
    doc = page.parent
    typ, val = doc.xref_get_key(annot.xref, "AP/N")
    if typ != "xref":
        return
    ap = int(val.split()[0])
    from . import measure
    p = model["props"]
    fs = _fontsize(p)
    lead = fs * 1.2
    to_pdf = pdfcoords.to_pdf(page)
    # each block is drawn in a frame turned with the page, so it reads upright on screen
    rad = math.radians(page.rotation)
    ca, sa = math.cos(rad), math.sin(rad)
    # (the box holds each text with room for its accents and descenders)
    pad = max(1.0, fs * 0.3)
    ops = []
    grown = pymupdf.Rect()
    for lines, anchor, align, color in placed:
        c = pymupdf.Point(anchor) * to_pdf
        frame = pymupdf.Matrix(ca, sa, -sa, ca, c.x, c.y)
        widths = [pymupdf.get_text_length(t, fontname="helv", fontsize=fs) for t in lines]
        w, h = max(widths), lead * len(lines)
        ops += [f"q {ca:.5f} {sa:.5f} {-sa:.5f} {ca:.5f} {c.x:.3f} {c.y:.3f} cm", "BT",
                f"/KZHelv {fs:g} Tf", " ".join(f"{v:g}" for v in color) + " rg"]
        y = h / 2 - fs * 0.85
        for t, tw in zip(lines, widths):
            x = {"left": -w / 2, "right": w / 2 - tw}.get(align, -tw / 2)
            raw = measure._esc(t).encode("cp1252", "replace").decode("latin-1")
            ops.append(f"1 0 0 1 {x:.3f} {y:.3f} Tm ({raw}) Tj")
            y -= lead
        ops += ["ET", "Q"]
        grown |= pymupdf.Rect(-w / 2 - pad, -h / 2 - pad, w / 2 + pad, h / 2 + pad) * frame
    stream = doc.xref_stream(ap) + ("\n" + "\n".join(ops) + "\n").encode("latin-1")
    doc.update_stream(ap, stream)
    font = measure._font_xref(doc)
    # (the font joins the appearance's resources, keeping its transparency state)
    typ, val = doc.xref_get_key(ap, "Resources")
    if typ in ("null", ""):
        doc.xref_set_key(ap, "Resources", f"<</Font<</KZHelv {font} 0 R>>>>")
    else:
        target = int(val.split()[0]) if typ == "xref" else ap
        key = "Font/KZHelv" if typ == "xref" else "Resources/Font/KZHelv"
        doc.xref_set_key(target, key, f"{font} 0 R")
    bb = doc.xref_get_key(ap, "BBox")[1].strip("[]").split()
    whole = pymupdf.Rect(*map(float, bb)) | grown
    arr = f"[{whole.x0:.3f} {whole.y0:.3f} {whole.x1:.3f} {whole.y1:.3f}]"
    doc.xref_set_key(ap, "BBox", arr)
    doc.xref_set_key(annot.xref, "Rect", arr)
