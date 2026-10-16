"""Reading the drawing scale off the sheet itself.

Title blocks say what scale a sheet was drawn at ('SCALE: 1/4" = 1'-0"', '1" = 20'',
'1:50', 'NTS'), and detail titles repeat it for each detail. This module finds those notes in
the page text, so Set scale can offer them and Read scales from title blocks can apply them
to a whole set in one go, instead of the user typing or calibrating what is already written
on the drawing.

A note is believed, not checked: a sheet plotted at reduced size (a 24x36 printed on 11x17)
still says its original scale, and nothing on the page tells. The user interface says so
and offers Calibrate.
"""

import re

import pymupdf

from . import measure as M

_QUOTES = str.maketrans({"“": '"', "”": '"', "″": '"', "‘": "'",
                         "’": "'", "′": "'", "–": "-", "—": "-",
                         "−": "-"})
# paper length in inches: 1  1/8  3/32  1-1/2  1 1/2
_PAPER = r"(?:(?:(?P<w>\d+)\s*-?\s*)?(?P<n>\d+)\s*/\s*(?P<d>\d+)|(?P<i>\d+(?:\.\d+)?))"
# ... = real length in feet (and inches): 1'-0"  20'  1' 6"
_ARCH = re.compile(_PAPER + r"\s*(?:\"|in\b)\s*=\s*(?P<ft>\d+(?:\.\d+)?)\s*(?:'|ft\b)"
                   r"(?:\s*-?\s*(?P<fi>\d+)(?:\s+(?P<fn>\d+)/(?P<fd>\d+))?\s*\")?", re.I)
_METRIC = re.compile(r"(?<![\d:.])1\s*:\s*(?P<n>\d{1,5})(?![\d:])")
_METRIC_OK = {2, 5, 10, 20, 25, 50, 75, 100, 125, 150, 200, 250, 300, 400, 500, 1000,
              1250, 2000, 2500, 5000, 10000}
_NTS = re.compile(r"\bN\.?\s?T\.?\s?S\b\.?|\bNOT\s+TO\s+SCALE\b", re.I)
_SCALE_LABEL = re.compile(r"^\s*(?:DRAWING\s+|DWG\.?\s+|PLOT\s+)?SCALE\s*[:.]?\s*$", re.I)
_HAS_SCALE_WORD = re.compile(r"\bSCALE\b", re.I)
_PRESET_BY_RATIO = {round(r, 6): (label, unit) for label, r, unit in M.PRESETS}


def _frac(m, w, n, d, i):
    if m.group(n):
        return float(m.group(w) or 0) + int(m.group(n)) / int(m.group(d))
    return float(m.group(i))


def parse(text):
    """The scale in one line of text: (label, ratio, unit) with ratio = real length per paper
    length (96 for 1/8" = 1'-0"), ratio None for 'not to scale', or None when the line
    holds no scale."""
    t = text.translate(_QUOTES)
    m = _ARCH.search(t)
    if m:
        paper = _frac(m, "w", "n", "d", "i")
        if paper <= 0:
            return None
        real = float(m.group("ft")) * 12
        if m.group("fi"):
            real += int(m.group("fi"))
            if m.group("fn"):
                real += int(m.group("fn")) / int(m.group("fd"))
        ratio = real / paper
        unit = "ft" if (paper == 1 and not m.group("fi") and float(m.group("ft")) >= 10) else "ft-in"
        return _label(ratio, unit, m.group(0)), ratio, unit
    m = _METRIC.search(t)
    if m:
        n = int(m.group("n"))
        if n in _METRIC_OK or _HAS_SCALE_WORD.search(t):
            unit = "mm" if n <= 50 else "m"
            return _label(float(n), unit, f"1:{n}"), float(n), unit
    if _NTS.search(t):
        return "not to scale", None, ""
    return None


def _label(ratio, unit, text):
    hit = _PRESET_BY_RATIO.get(round(ratio, 6))
    if hit:
        return hit[0]
    return " ".join(text.split())


def _title_block_zone(page):
    """The lower right part of the sheet as displayed, where title blocks live."""
    r = page.rect
    return pymupdf.Rect(r.x0 + r.width * 0.55, r.y0 + r.height * 0.7, r.x1, r.y1)


def find(page):
    """Every scale note on the page: [{"label", "ratio", "unit", "where", "rect", "text",
    "labeled"}], title block first. "where" is "title block" or "drawing"; "labeled" means
    a 'SCALE' caption stood right before it. rect is in unrotated page coordinates."""
    try:
        blocks = page.get_text("dict", flags=pymupdf.TEXT_PRESERVE_WHITESPACE)["blocks"]
    except Exception:
        return []
    zone = _title_block_zone(page)
    rot = page.rotation_matrix
    lines = []
    for b in blocks:
        for ln in b.get("lines", []):
            text = "".join(sp["text"] for sp in ln["spans"]).strip()
            if text:
                lines.append((text, pymupdf.Rect(ln["bbox"])))
    found, seen = [], set()
    prev_label = False
    for text, rect in lines:
        if _SCALE_LABEL.match(text):
            prev_label = True
            continue
        hit = parse(text)
        labeled = prev_label or bool(_HAS_SCALE_WORD.search(text))
        prev_label = False
        if hit is None:
            continue
        label, ratio, unit = hit
        where = "title block" if (rect * rot).intersects(zone) else "drawing"
        key = (label, where)
        if key in seen:
            continue
        seen.add(key)
        found.append({"label": label, "ratio": ratio, "unit": unit, "where": where,
                      "rect": rect, "text": text, "labeled": labeled})
    found.sort(key=lambda f: (f["where"] != "title block", not f["labeled"], f["ratio"] is None))
    return found


def sheet_scale(page):
    """The scale the sheet was drawn at, from its title block when there is one, else the
    first scale note: a dict from find(), or None. A 'not to scale' note counts (ratio None)."""
    found = find(page)
    if not found:
        return None
    tb = [f for f in found if f["where"] == "title block"]
    return (tb or found)[0]
