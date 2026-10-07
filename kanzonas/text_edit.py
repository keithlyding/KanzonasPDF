"""Editing existing page text, one line at a time.

PDF pages store positioned glyphs, not paragraphs, so true word-processor editing
isn't possible. Instead: find the line under the cursor, remove its characters
(redaction that leaves drawings and images alone), and write the new text at the same
baseline, size, color and direction. The original embedded font is reused when it
contains every needed character; otherwise the closest standard font is used.
"""

import glob
import math
import os
import re

import pymupdf

# PDF font flags as reported by PyMuPDF spans
_ITALIC, _SERIF, _MONO, _BOLD = 2, 4, 8, 16


def _baseline(line):
    """Position across the text direction (y for horizontal text, x for vertical)."""
    o = line["spans"][0]["origin"]
    dx, dy = line["dir"]
    return o[1] if abs(dx) >= abs(dy) else o[0]


def _along(rect, line):
    """(start, end) of a rect along the text direction."""
    dx, dy = line["dir"]
    if abs(dx) >= abs(dy):
        return (rect.x0, rect.x1) if dx > 0 else (-rect.x1, -rect.x0)
    return (rect.y0, rect.y1) if dy > 0 else (-rect.y1, -rect.y0)


def text_lines(page):
    """[(rect, line)] for every visual text line on the page (unrotated coords).

    PDF producers often split one visual line into several pieces (kerning, a single
    letter placed separately, another text block). Pieces on the same baseline that
    touch or nearly touch are merged, so editing a line never leaves a letter behind."""
    pieces = []
    d = page.get_text("dict", flags=pymupdf.TEXTFLAGS_DICT & ~pymupdf.TEXT_PRESERVE_IMAGES)
    for b in d["blocks"]:
        if b.get("type") != 0:
            continue
        for line in b["lines"]:
            spans = [s for s in line["spans"] if s["text"]]
            if spans and any(s["text"].strip() for s in spans):
                pieces.append({"bbox": pymupdf.Rect(line["bbox"]), "dir": line["dir"],
                               "spans": spans})
    # sort along each direction so neighbours are adjacent
    pieces.sort(key=lambda l: (round(l["dir"][0], 2), round(l["dir"][1], 2),
                               round(_baseline(l)), _along(l["bbox"], l)[0]))
    merged = []
    for piece in pieces:
        size = max(s["size"] for s in piece["spans"])
        if merged:
            last = merged[-1]
            lsize = max(s["size"] for s in last["spans"])
            same_dir = (abs(last["dir"][0] - piece["dir"][0]) < 0.01
                        and abs(last["dir"][1] - piece["dir"][1]) < 0.01)
            gap = _along(piece["bbox"], piece)[0] - _along(last["bbox"], last)[1]
            if (same_dir and abs(_baseline(last) - _baseline(piece)) < 0.25 * max(size, lsize)
                    and -0.5 * size < gap < 0.6 * max(size, lsize)):
                last["spans"].extend(piece["spans"])
                last["bbox"] |= piece["bbox"]
                continue
        merged.append({"bbox": pymupdf.Rect(piece["bbox"]), "dir": piece["dir"],
                       "spans": list(piece["spans"])})
    return [(m["bbox"], m) for m in merged]


def line_at(lines, pt):
    """Smallest line whose box contains the point (or is within 2pt of it)."""
    hits = [(r, l) for r, l in lines if (r + (-2, -2, 2, 2)).contains(pt)]
    if not hits:
        return None
    return min(hits, key=lambda h: h[0].get_area())


def line_text(line):
    """Text of a (possibly merged) line, adding a space where pieces have a visible gap."""
    out, prev = [], None
    for s in line["spans"]:
        if prev is not None:
            gap = _along(pymupdf.Rect(s["bbox"]), line)[0] - _along(pymupdf.Rect(prev["bbox"]), line)[1]
            if gap > 0.15 * s["size"] and not out[-1].endswith(" ") and not s["text"].startswith(" "):
                out.append(" ")
        out.append(s["text"])
        prev = s
    return "".join(out)


def line_rotation(line):
    """Text direction as an insert_text rotation (0/90/180/270, unrotated page space)."""
    dx, dy = line["dir"]
    return int(round(math.degrees(math.atan2(-dy, dx)) / 90.0)) % 4 * 90


def main_span(line):
    spans = [s for s in line["spans"] if s["text"].strip()]
    return max(spans, key=lambda s: len(s["text"].strip()))


def font_family_hint(line):
    """'sans' | 'serif' | 'mono' for showing the line in an on-screen editor."""
    return {"helv": "sans", "hebo": "sans", "heit": "sans", "hebi": "sans",
            "tiro": "serif", "tibo": "serif", "tiit": "serif", "tibi": "serif"}.get(
        _base14(main_span(line)), "mono")


_SANS = ("sans", "arial", "helvetica", "verdana", "calibri", "segoe", "tahoma", "gothic",
         "frutiger", "univers", "futura", "trebuchet", "aptos", "roboto", "lato", "isocp")
_SERIF_NAMES = ("times", "serif", "roman", "georgia", "garamond", "cambria", "antiqua",
                "palatino", "bookman", "century")
_MONO_NAMES = ("courier", "mono", "consolas", "console", "typewriter")


def _base14(span):
    """Closest built-in PDF font. The font name is a better guide than the PDF's flags."""
    flags, name = span["flags"], span["font"].lower()
    bold = bool(flags & _BOLD) or "bold" in name or "black" in name or "heavy" in name
    italic = bool(flags & _ITALIC) or "italic" in name or "oblique" in name
    if any(k in name for k in _MONO_NAMES):
        kind = "mono"
    elif any(k in name for k in _SANS):
        kind = "sans"
    elif any(k in name for k in _SERIF_NAMES):
        kind = "serif"
    else:
        kind = "mono" if flags & _MONO else "serif" if flags & _SERIF else "sans"
    family = {"mono": ("cour", "cobo", "coit", "cobi"),
              "serif": ("tiro", "tibo", "tiit", "tibi"),
              "sans": ("helv", "hebo", "heit", "hebi")}[kind]
    return family[(2 if italic else 0) + (1 if bold else 0)]


def _embedded_font(page, span, text):
    """Reuse the span's embedded font if it has every glyph we need. Returns a font name or None."""
    doc = page.parent
    want = span["font"]
    for xref, ext, _type, basefont, *_ in page.get_fonts(full=True):
        base = basefont.split("+", 1)[-1]
        if base != want or ext in ("n/a", ""):
            continue
        try:
            _name, _ext, _t, buf = doc.extract_font(xref)
            if not buf:
                return None
            font = pymupdf.Font(fontbuffer=buf)
            if all(font.has_glyph(ord(c)) for c in text if c not in "\n\r"):
                name = f"KZ{xref}"
                page.insert_font(fontname=name, fontbuffer=buf)
                return name, font
        except Exception:
            return None
    return None


def _norm(name):
    """'ABCDEF+Arial-BoldMT' / 'Arial Bold' -> 'arialbold'."""
    name = name.split("+", 1)[-1].lower()
    name = re.sub(r"(psmt|mt|ps|regular|book|roman$)", "", name.replace(",", ""))
    return re.sub(r"[^a-z0-9]", "", name)


_SYSTEM_FONTS = None


def _system_fonts():
    """{normalized name: font file} for fonts installed on this computer (scanned once)."""
    global _SYSTEM_FONTS
    if _SYSTEM_FONTS is None:
        _SYSTEM_FONTS = {}
        dirs = [os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"),
                os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "Windows", "Fonts"),
                "/usr/share/fonts", os.path.expanduser("~/.fonts"), "/Library/Fonts"]
        for d in dirs:
            if not os.path.isdir(d):
                continue
            for f in glob.glob(os.path.join(d, "**", "*.[to]tf"), recursive=True):
                try:
                    _SYSTEM_FONTS.setdefault(_norm(pymupdf.Font(fontfile=f).name), f)
                except Exception:
                    pass
    return _SYSTEM_FONTS


def _system_font(page, span, text):
    """Use the installed copy of the span's font (like Acrobat does) if it has every glyph."""
    path = _system_fonts().get(_norm(span["font"]))
    if not path:
        return None
    try:
        font = pymupdf.Font(fontfile=path)
        if not all(font.has_glyph(ord(c)) for c in text if c not in "\n\r"):
            return None
        name = "KZS" + _norm(span["font"])[:20]
        page.insert_font(fontname=name, fontfile=path)
        return name, font
    except Exception:
        return None


def _rgb(color_int):
    return tuple(c / 255 for c in pymupdf.sRGB_to_rgb(color_int))


def _wrap(text, font, size, width):
    """Greedy word wrap of each paragraph to `width` points."""
    out = []
    for para in text.split("\n"):
        words = para.split(" ")
        cur = ""
        for w in words:
            trial = w if not cur else cur + " " + w
            if cur and font.text_length(trial, fontsize=size) > width:
                out.append(cur)
                cur = w
            else:
                cur = trial
        out.append(cur)
    return out


def replace_line(page, line, new_text, offset=(0, 0), wrap_width=None):
    """Remove the line's text and write new_text in its place.

    offset: move the text by (dx, dy) points. wrap_width: wrap to this width (points).
    Returns the font name used: 'KZ…' = original embedded font, 'KZS…' = installed system
    font of the same name, otherwise a built-in PDF font."""
    main = main_span(line)
    first = line["spans"][0]

    # 1) remove only the text of this line (keep line art and images)
    dx, dy = line["dir"]
    for s in line["spans"]:
        r = pymupdf.Rect(s["bbox"])
        # shrink across the line's height a little so glyphs of neighbouring lines survive
        if abs(dx) >= abs(dy):
            pad = r.height * 0.15
            r = pymupdf.Rect(r.x0, r.y0 + pad, r.x1, r.y1 - pad)
        else:
            pad = r.width * 0.15
            r = pymupdf.Rect(r.x0 + pad, r.y0, r.x1 - pad, r.y1)
        page.add_redact_annot(r, fill=False)
    page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE,
                          graphics=pymupdf.PDF_REDACT_LINE_ART_NONE,
                          text=pymupdf.PDF_REDACT_TEXT_REMOVE)

    if not new_text.strip():
        return None
    # 2) write the replacement at the same baseline / direction
    found = _embedded_font(page, main, new_text) or _system_font(page, main, new_text)
    if found:
        fontname, font = found
    else:
        fontname = _base14(main)
        font = pymupdf.Font(fontname)
    size = main["size"]
    lines = _wrap(new_text, font, size, wrap_width) if wrap_width else new_text.split("\n")
    origin = pymupdf.Point(first["origin"]) + offset
    page.insert_text(origin, "\n".join(lines), fontsize=size, fontname=fontname,
                     color=_rgb(main["color"]), rotate=line_rotation(line),
                     lineheight=1.2)
    return fontname
