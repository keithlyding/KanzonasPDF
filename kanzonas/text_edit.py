"""Editing existing page text, one line at a time.

PDF pages store positioned glyphs, not paragraphs, so true word-processor editing
isn't possible. Instead: find the line under the cursor, remove its characters
(redaction that leaves drawings and images alone), and write the new text at the same
baseline, size, colour and direction. The original embedded font is reused when it
contains every needed character; otherwise the closest standard font is used.
"""

import glob
import math
import os
import re

import pymupdf

# PDF font flags as reported by PyMuPDF spans
_ITALIC, _SERIF, _MONO, _BOLD = 2, 4, 8, 16


def text_lines(page):
    """[(rect, line_dict)] for every non-empty text line on the page (unrotated coords)."""
    out = []
    d = page.get_text("dict", flags=pymupdf.TEXTFLAGS_DICT & ~pymupdf.TEXT_PRESERVE_IMAGES)
    for b in d["blocks"]:
        if b.get("type") != 0:
            continue
        for line in b["lines"]:
            if any(s["text"].strip() for s in line["spans"]):
                out.append((pymupdf.Rect(line["bbox"]), line))
    return out


def line_at(lines, pt):
    """Smallest line whose box contains the point (or is within 2pt of it)."""
    hits = [(r, l) for r, l in lines if (r + (-2, -2, 2, 2)).contains(pt)]
    if not hits:
        return None
    return min(hits, key=lambda h: h[0].get_area())


def line_text(line):
    return "".join(s["text"] for s in line["spans"])


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
                return name
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
        return name
    except Exception:
        return None


def _rgb(color_int):
    return tuple(c / 255 for c in pymupdf.sRGB_to_rgb(color_int))


def replace_line(page, line, new_text):
    """Remove the line's text and write new_text in its place.

    Returns the font name used: 'KZ…' = original embedded font, 'KZS…' = installed system
    font of the same name, otherwise a built-in PDF font."""
    spans = [s for s in line["spans"] if s["text"].strip()]
    main = max(spans, key=lambda s: len(s["text"].strip()))
    first = line["spans"][0]

    # 1) remove only the text of this line (keep line art and images)
    for s in line["spans"]:
        r = pymupdf.Rect(s["bbox"])
        # shrink across the line's height a little so glyphs of neighbouring lines survive
        dx, dy = line["dir"]
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
    dx, dy = line["dir"]
    rotate = int(round(math.degrees(math.atan2(-dy, dx)) / 90.0)) % 4 * 90
    fontname = (_embedded_font(page, main, new_text) or _system_font(page, main, new_text)
                or _base14(main))
    page.insert_text(pymupdf.Point(first["origin"]), new_text, fontsize=main["size"],
                     fontname=fontname, color=_rgb(main["color"]), rotate=rotate)
    return fontname
