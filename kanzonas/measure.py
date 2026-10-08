"""Measurement: page scales, unit formatting, and measurement labels drawn into the PDF.

A page's scale is stored in the page dictionary (/KZScale "meters-per-point|unit|label"),
so it travels with the file. Values are recomputed whenever a measurement is redrawn, so
moving a vertex or changing the scale updates the number.
"""

import math
from fractions import Fraction

import pymupdf

PT_M = 0.0254 / 72                        # meters per PDF point (paper size)
UNITS = {"ft-in": 0.3048, "ft": 0.3048, "in": 0.0254, "yd": 0.9144, "mi": 1609.344,
         "m": 1.0, "cm": 0.01, "mm": 0.001, "km": 1000.0}
UNIT_LABELS = {"ft-in": "Feet and inches (12'-6\")", "ft": "Feet (decimal)", "in": "Inches",
               "yd": "Yards", "mi": "Miles", "m": "Meters", "cm": "Centimeters",
               "mm": "Millimeters", "km": "Kilometers"}
# (label, real length per paper length, display unit)
PRESETS = [
    ("1:1 (actual paper size)", 1, "in"),
    ('1/16" = 1\'-0"', 192, "ft-in"), ('3/32" = 1\'-0"', 128, "ft-in"),
    ('1/8" = 1\'-0"', 96, "ft-in"), ('3/16" = 1\'-0"', 64, "ft-in"),
    ('1/4" = 1\'-0"', 48, "ft-in"), ('3/8" = 1\'-0"', 32, "ft-in"),
    ('1/2" = 1\'-0"', 24, "ft-in"), ('3/4" = 1\'-0"', 16, "ft-in"),
    ('1" = 1\'-0"', 12, "ft-in"), ('1-1/2" = 1\'-0"', 8, "ft-in"), ('3" = 1\'-0"', 4, "ft-in"),
    ('1" = 10\'', 120, "ft"), ('1" = 20\'', 240, "ft"), ('1" = 30\'', 360, "ft"),
    ('1" = 40\'', 480, "ft"), ('1" = 50\'', 600, "ft"), ('1" = 60\'', 720, "ft"),
    ('1" = 100\'', 1200, "ft"), ('1" = 200\'', 2400, "ft"),
    ("1:5", 5, "mm"), ("1:10", 10, "mm"), ("1:20", 20, "mm"), ("1:50", 50, "mm"),
    ("1:100", 100, "m"), ("1:200", 200, "m"), ("1:500", 500, "m"), ("1:1000", 1000, "m"),
    ("1:2500", 2500, "m"),
]
KEY = "KZScale"
# Preferences > Measuring (set by configure())
FRACTION = 16             # feet-and-inches values round to the nearest 1/FRACTION inch
DECIMALS = None           # decimal places for decimal units; None = 2 (0 for mm)
DEFAULT_UNIT = "ft-in"    # display unit offered for a page that has no scale yet
FRACTIONS = [2, 4, 8, 16, 32, 64]


def configure(settings):
    global FRACTION, DECIMALS, DEFAULT_UNIT
    try:
        f = int(settings.value("measure_fraction", 16))
        FRACTION = f if f in FRACTIONS else 16
    except (TypeError, ValueError):
        FRACTION = 16
    d = settings.value("measure_decimals", "auto")
    DECIMALS = int(d) if str(d).isdigit() and int(d) <= 6 else None
    u = settings.value("measure_unit", "ft-in")
    DEFAULT_UNIT = u if u in UNITS else "ft-in"


# ---- page scale ------------------------------------------------------------------
def get_scale(page):
    """(meters per PDF point, unit, label, calibrated?)"""
    try:
        typ, val = page.parent.xref_get_key(page.xref, KEY)
        if typ == "string":
            f, unit, label = (val.split("|", 2) + ["", ""])[:3]
            return float(f), unit, label, True
    except Exception:
        pass
    return PT_M, "in", "not set (paper size)", False


def set_scale(page, m_per_pt, unit, label):
    page.parent.xref_set_key(page.xref, KEY, pymupdf.get_pdf_str(f"{m_per_pt!r}|{unit}|{label}"))


def scale_from_preset(ratio):
    return PT_M * ratio


def describe(page):
    _f, unit, label, ok = get_scale(page)
    return f"Scale: {label}" + (f"  ({unit})" if ok else "")


# ---- geometry -----------------------------------------------------------------------
def length(points):
    return sum(abs(b - a) for a, b in zip(points, points[1:]))


def area(points):
    """Shoelace formula, in square points."""
    s = 0.0
    for a, b in zip(points, points[1:] + points[:1]):
        s += a.x * b.y - b.x * a.y
    return abs(s) / 2


# ---- formatting ---------------------------------------------------------------------
def fmt_length(meters, unit):
    if unit == "ft-in":
        total_in = meters / 0.0254
        sign = "-" if total_in < 0 else ""
        total_in = abs(total_in)
        ft = int(total_in // 12)
        inch = total_in - ft * 12
        frac = Fraction(round(inch * FRACTION), FRACTION)      # nearest 1/FRACTION"
        whole = int(frac)
        rest = frac - whole
        if whole == 12:
            ft, whole = ft + 1, 0
        inch_s = str(whole) + (f" {rest.numerator}/{rest.denominator}" if rest else "")
        return f"{sign}{ft}'-{inch_s}\""
    value = meters / UNITS[unit]
    digits = DECIMALS if DECIMALS is not None else (0 if unit == "mm" else 2)
    return f"{value:,.{digits}f} {unit}"


def fmt_area(sq_meters, unit):
    base = "ft" if unit == "ft-in" else unit
    value = sq_meters / UNITS[base] ** 2
    digits = DECIMALS if DECIMALS is not None else 2
    return f"{value:,.{digits}f} sq {base}"


def measure_text(kind, points, page, group=""):
    f, unit, _label, _ok = get_scale(page)
    if kind in ("m_length", "m_poly"):
        return fmt_length(length(points) * f, unit)
    if kind == "m_area":
        a = fmt_area(area(points) * f * f, unit)
        per = fmt_length(length(points + points[:1]) * f, unit)
        return f"{a}\nPerimeter {per}"
    if kind == "m_count":
        return group
    return ""


def raw_values(kind, points, page):
    """Numbers for totals: (value, unit) in display units."""
    f, unit, _l, _ok = get_scale(page)
    base = "ft" if unit == "ft-in" else unit
    if kind in ("m_length", "m_poly"):
        return length(points) * f / UNITS[base], base
    if kind == "m_area":
        return area(points) * f * f / UNITS[base] ** 2, "sq " + base
    return 1, "count"


# ---- labels drawn into the annotation's appearance ---------------------------------
def _font_xref(doc):
    """A shared Helvetica font object for measurement labels (its xref is remembered in
    the document catalog so big files aren't scanned)."""
    cat = doc.pdf_catalog()
    typ, val = doc.xref_get_key(cat, "KZLabelFont")
    if typ == "xref":
        return int(val.split()[0])
    xref = doc.get_new_xref()
    doc.update_object(xref, "<</Type/Font/Subtype/Type1/BaseFont/Helvetica"
                            "/Encoding/WinAnsiEncoding>>")
    doc.xref_set_key(cat, "KZLabelFont", f"{xref} 0 R")
    return xref


def _esc(s):
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def add_label(page, annot, text, anchor, size=9.0, color=(0, 0, 0), angle=0.0):
    """Append text (with a white backing) to the annotation's appearance and grow its box.
    anchor: PyMuPDF (top-left origin, unrotated) point at the label's center."""
    if not text:
        return
    doc = page.parent
    typ, val = doc.xref_get_key(annot.xref, "AP/N")
    if typ != "xref":
        return
    ap = int(val.split()[0])
    to_pdf = ~page.transformation_matrix
    lines = text.split("\n")
    lead = size * 1.2
    width = max(pymupdf.get_text_length(t, fontname="helv", fontsize=size) for t in lines)
    height = lead * len(lines)
    c = pymupdf.Point(anchor) * to_pdf                  # PDF coordinates (y up)
    # draw in a frame rotated by `angle` around the anchor so labels follow the line
    rad = math.radians(angle)
    ca, sa = math.cos(rad), math.sin(rad)
    ops = [f"q {ca:.5f} {sa:.5f} {-sa:.5f} {ca:.5f} {c.x:.3f} {c.y:.3f} cm",
           "1 1 1 rg", f"{-width / 2 - 2:.3f} {-height / 2 - 1:.3f} {width + 4:.3f} {height + 2:.3f} re f",
           "BT", f"/KZHelv {size:g} Tf", " ".join(f"{v:g}" for v in color) + " rg"]
    y = height / 2 - size
    for t in lines:
        w = pymupdf.get_text_length(t, fontname="helv", fontsize=size)
        ops.append(f"1 0 0 1 {-w / 2:.3f} {y:.3f} Tm ({_esc(t)}) Tj")
        y -= lead
    ops += ["ET", "Q"]
    stream = doc.xref_stream(ap) + ("\n" + "\n".join(ops) + "\n").encode("latin-1", "replace")
    doc.update_stream(ap, stream)
    font = _font_xref(doc)
    doc.xref_set_key(ap, "Resources", f"<</Font<</KZHelv {font} 0 R>>>>")
    # grow BBox and the annotation Rect to include the (possibly rotated) label
    half = max(width, height) / 2 + 4
    lab = pymupdf.Rect(c.x - half, c.y - half, c.x + half, c.y + half)
    bb = doc.xref_get_key(ap, "BBox")[1].strip("[]").split()
    box = pymupdf.Rect(*map(float, bb)) | lab
    arr = f"[{box.x0:.3f} {box.y0:.3f} {box.x1:.3f} {box.y1:.3f}]"
    doc.xref_set_key(ap, "BBox", arr)
    doc.xref_set_key(annot.xref, "Rect", arr)


def label_anchor(kind, points, page=None):
    """(anchor point, angle in degrees) for a measurement label, computed so the label reads
    upright on screen even on rotated pages (anchor in unrotated page coordinates)."""
    rot = page.rotation if page is not None else 0
    to_disp = page.rotation_matrix if page is not None else pymupdf.Identity
    to_page = page.derotation_matrix if page is not None else pymupdf.Identity
    pts = [pymupdf.Point(q) * to_disp for q in points]          # as seen on screen
    if kind == "m_length":
        a, b = pts[0], pts[1]
        ang = math.degrees(math.atan2(-(b.y - a.y), b.x - a.x))
        if ang > 90:
            ang -= 180
        elif ang < -90:
            ang += 180
        mid = (a + b) / 2
        # nudge the label just off the line (perpendicular, towards the top of the screen)
        n = pymupdf.Point(-(b.y - a.y), b.x - a.x)
        n = n / (abs(n) or 1)
        if n.y > 0:
            n = -n
        anchor, angle = mid + n * 8, ang
    elif kind == "m_poly":
        a, b = pts[-2], pts[-1]
        anchor, angle = (a + b) / 2 + (0, -10), 0.0
    elif kind == "m_area":
        anchor = pymupdf.Point(sum(q.x for q in pts) / len(pts), sum(q.y for q in pts) / len(pts))
        angle = 0.0
    elif kind == "m_count":
        anchor, angle = pts[0] + (10, -8), 0.0
    else:
        anchor, angle = pts[0], 0.0
    return anchor * to_page, angle + rot
