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

from .i18n import tr

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


def visible(line):
    """False for text nobody sees (a scanner's OCR layer: invisible, opacity 0)."""
    return any(s.get("alpha", 255) for s in line["spans"] if s["text"].strip())


def _row_key(r, ln):
    return (round(ln["dir"][0], 2), round(ln["dir"][1], 2), round(_baseline(ln), 1),
            _along(r, ln)[0])


def _covered(pieces, g0, g1):
    """True when the pieces of a row (sorted (start, end) along it) have text all the way
    across g0..g1."""
    x = g0 + 0.5
    for a0, a1 in pieces:
        if a1 <= x:
            continue
        if a0 > x:
            return False
        x = a1
        if x >= g1 - 0.5:
            return True
    return False


def _join_spread_pieces(rows):
    """Pieces of one line of a justified paragraph: the wide gaps between its words split
    it into pieces on the same baseline (text_lines keeps a line's pieces apart beyond a
    small gap, so labels and table cells stay separate). Join pieces of the same size up to
    1.5 letter heights apart into one line, unless the gap runs down the page: a gutter
    between columns or table cells has the rows next to it split at the same place (text on
    both sides, none across it), where a stretched space has words across it above or
    below. When the rows next to it can't tell, pieces in the same font and color join."""
    import bisect

    def key(span):
        return (span.get("font"), round(span["size"], 1), span.get("color"))
    rows = sorted(rows, key=lambda h: _row_key(*h))
    # each visual row's pieces, (start, end) along it, by direction and baseline: built once
    index = {}
    for r, ln in rows:
        d = (round(ln["dir"][0], 2), round(ln["dir"][1], 2))
        base = _baseline(ln)
        groups = index.setdefault(d, [])
        if groups and abs(groups[-1][0] - base) < 0.3:
            groups[-1][1].append(_along(r, ln))
        else:
            groups.append((base, [_along(r, ln)]))
    bases = {}
    for d, groups in index.items():
        for _b, pieces in groups:
            pieces.sort()
        bases[d] = [b for b, _p in groups]

    def neighbors_say(ln, size, g0, g1):
        """True: a row next to it has words across the gap (a stretched space); False: a
        row next to it is split there too (a gutter); None: they can't tell."""
        d = (round(ln["dir"][0], 2), round(ln["dir"][1], 2))
        groups, bs = index[d], bases[d]
        base = _baseline(ln)
        verdict = None
        for lo, hi, pick in ((base - 2.0 * size, base - 0.7 * size, -1),
                             (base + 0.7 * size, base + 2.0 * size, 0)):
            i, j = bisect.bisect_left(bs, lo), bisect.bisect_right(bs, hi)
            if i >= j:
                continue
            pieces = groups[(j - 1) if pick < 0 else i][1]      # the nearest row
            if _covered(pieces, g0, g1):
                return True
            if any(a1 <= g0 + 0.5 for _a0, a1 in pieces) and \
                    any(a0 >= g1 - 0.5 for a0, _a1 in pieces):
                verdict = False
            elif any(abs(a0 - g1) <= 1.5 for a0, _a1 in pieces):
                verdict = False         # the text after the gap starts a column's lines
        return verdict

    out = []
    for r, ln in rows:
        if out:
            lr, last = out[-1]
            size = max(s["size"] for s in ln["spans"])
            lsize = max(s["size"] for s in last["spans"])
            g0, g1 = _along(lr, last)[1], _along(r, ln)[0]
            if (abs(last["dir"][0] - ln["dir"][0]) < 0.01 and
                    abs(last["dir"][1] - ln["dir"][1]) < 0.01 and
                    abs(_baseline(last) - _baseline(ln)) < 0.25 * size and
                    abs(size - lsize) < 0.05 * size and 0 <= g1 - g0 <= 1.5 * size):
                said = neighbors_say(ln, size, g0, g1)
                if said or (said is None and key(main_span(last)) == key(main_span(ln))):
                    joined = {"bbox": pymupdf.Rect(lr) | r, "dir": last["dir"],
                              "spans": last["spans"] + ln["spans"]}
                    out[-1] = (pymupdf.Rect(joined["bbox"]), joined)
                    continue
        out.append((pymupdf.Rect(r), ln))
    return out


def text_blocks(lines):
    """The page's visible text as paragraphs: [(rect, [(rect, line), ...])], lines in
    order. Lines join a paragraph when they run the same way, are about the same size and
    sit one under the other at a normal line spacing (so what Add text wrote in one go is
    one paragraph). For Edit objects: select, move and delete text as one piece."""
    rows = _join_spread_pieces([(r, ln) for r, ln in lines if visible(ln)])
    rows.sort(key=lambda h: (round(h[1]["dir"][0], 2), round(h[1]["dir"][1], 2),
                             _baseline(h[1]), _along(h[0], h[1])[0]))
    blocks = []
    for r, ln in rows:
        size = max(s["size"] for s in ln["spans"])
        for blk in reversed(blocks[-6:]):           # paragraphs still open nearby
            lr, last = blk[-1]
            lsize = max(s["size"] for s in last["spans"])
            if (abs(last["dir"][0] - ln["dir"][0]) > 0.01 or
                    abs(last["dir"][1] - ln["dir"][1]) > 0.01 or
                    not 0.75 < size / lsize < 1.33):
                continue
            step = abs(_baseline(ln) - _baseline(last))
            a0, a1 = _along(r, ln)
            b0, b1 = _along(lr, last)
            if 0.8 * max(size, lsize) < step <= 1.75 * max(size, lsize) and \
                    (min(a1, b1) - max(a0, b0) > 0 or abs(a0 - b0) < 2 * size):
                blk.append((r, ln))
                break
        else:
            blocks.append([(r, ln)])
    out = []
    for blk in blocks:
        box = pymupdf.Rect()
        for r, _ln in blk:
            box |= r
        out.append((box, blk))
    return out


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
    want = _norm(span["font"])
    for xref, ext, _type, basefont, *_ in page.get_fonts(full=True):
        # names are written differently in different places ("DejaVuSans" in the text,
        # "DejaVu Sans Book" in the font list): compare them normalized
        if _norm(basefont) != want or ext in ("n/a", ""):
            continue
        try:
            _name, _ext, _t, buf = doc.extract_font(xref)
            if not buf:
                return None
            font = pymupdf.Font(fontbuffer=buf)
            if all(font.has_glyph(ord(c)) for c in text if c not in "\n\r"):
                name = f"KZ{xref}"
                page.insert_font(fontname=name, fontbuffer=buf)
                return name, font, {"fontbuffer": buf}
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
        return name, font, {"fontfile": path}
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


def _wrap_indented(text, font, size, width, indent=0.0):
    """Greedy word wrap of one paragraph whose first line starts indent points in (a
    negative indent sets it out)."""
    out, cur = [], ""
    for w in text.split(" "):
        trial = w if not cur else cur + " " + w
        room = width - indent if not out else width
        if cur and font.text_length(trial, fontsize=size) > room:
            out.append(cur)
            cur = w
        else:
            cur = trial
    out.append(cur)
    return out


def _winansi_ok(text):
    """Built-in PDF fonts write text in the WinAnsi (cp1252) code page: anything outside it
    comes out as a dot."""
    try:
        text.replace("\n", "").replace("\r", "").encode("cp1252")
        return True
    except UnicodeEncodeError:
        return False


def _unicode_font(page, text):
    """A font for text the built-in PDF fonts can't encode (Greek, symbols, Chinese...):
    PyMuPDF's bundled Droid Sans Fallback, embedded (only the used glyphs stay on save)."""
    try:
        font = pymupdf.Font("cjk")
        if all(font.has_glyph(ord(c)) for c in text if c not in "\n\r"):
            page.insert_font(fontname="KZUni", fontbuffer=font.buffer)
            return "KZUni", font, {"fontbuffer": font.buffer}
    except Exception:
        pass
    return None


# Fonts that cover many symbols, tried when the text's own font and the bundled Unicode font
# can't write every character (normalized names, as in _system_fonts()).
BROAD_FONTS = ("segoeui", "segoeuisymbol", "arialunicodems", "cambriamath", "dejavusans",
               "notosans", "notosanssymbols", "notosanssymbols2", "liberationsans")

# Look-alikes for characters that often come out of PDF text (or are typed) but that few
# fonts have, used only when no font can write the text as typed.
LOOKALIKES = {"\u2212": "-", "\u2010": "-", "\u2011": "-", "\u2012": "-", "\u2043": "-",
              "\u00ad": "", "\u200b": "", "\u200c": "", "\u200d": "", "\ufeff": "",
              "\u2060": "", "\t": " ", "\u2002": " ", "\u2003": " ", "\u2007": " ",
              "\u2008": " ", "\u2009": " ", "\u200a": " ", "\u202f": "\u00a0",
              "\ufb00": "ff", "\ufb01": "fi", "\ufb02": "fl", "\ufb03": "ffi",
              "\ufb04": "ffl", "\u2300": "\u00d8", "\u2610": "[ ]", "\u2611": "[x]",
              "\u2612": "[x]", "\u2713": "\u221a", "\u2714": "\u221a"}


def _broad_font(page, text):
    """An installed font from BROAD_FONTS that has every character of text."""
    fonts = _system_fonts()
    for key in BROAD_FONTS:
        path = fonts.get(key)
        if not path:
            continue
        try:
            font = pymupdf.Font(fontfile=path)
            if all(font.has_glyph(ord(c)) for c in text if c not in "\n\r"):
                name = "KZB" + key[:20]
                page.insert_font(fontname=name, fontfile=path)
                return name, font, {"fontfile": path}
        except Exception:
            continue
    return None


def _fix_spaces(page, fontname, font):
    """Many fonts (Times New Roman, Arial on Windows...) draw a space and a no-break space with
    the same glyph, and the text map PyMuPDF writes for an embedded font then names that
    glyph a no-break space (U+00A0): search, copy and paste would see it instead of a normal
    space. Point the space glyph back at U+0020."""
    try:
        gid = font.has_glyph(0x20)
        if not gid or font.has_glyph(0xA0) != gid:
            return
        doc = page.parent
        for f in page.get_fonts(full=True):
            if f[4] != fontname:
                continue
            kind, val = doc.xref_get_key(f[0], "ToUnicode")
            if kind != "xref":
                continue
            tu = int(val.split()[0])
            data = doc.xref_stream(tu)
            for hexgid in (b"%04x" % gid, b"%04X" % gid):
                for nb in (b"<00a0>", b"<00A0>"):
                    data = data.replace(b"<" + hexgid + b"> " + nb, b"<" + hexgid + b"> <0020>")
            doc.update_stream(tu, data)
    except Exception:
        pass        # the text is written either way; only search / copy would be affected


_BASE14_STYLE = {(False, False): "helv", (True, False): "hebo", (False, True): "heit",
                 (True, True): "hebi"}


def chosen_font(page, family, bold=False, italic=False, text=""):
    """(font name, Font, how to insert it) for an installed font family picked in Properties,
    in its bold / italic style when installed, or None when it isn't installed or lacks some
    characters of text. The font is embedded with only the letters used."""
    if not family:
        return None
    fonts = _system_fonts()
    base = _norm(family)
    style = ("bold" if bold else "") + ("italic" if italic else "")
    keys = ([base + style, base + style.replace("italic", "oblique")] if style else []) + [base]
    for key in keys:
        path = fonts.get(key)
        if not path:
            continue
        try:
            font = pymupdf.Font(fontfile=path)
            if not all(font.has_glyph(ord(c)) for c in text if c not in "\n\r"):
                return None
            name = "KZF" + key[:20]
            page.insert_font(fontname=name, fontfile=path)
            return name, font, {"fontfile": path}
        except Exception:
            continue
    return None


def add_text(page, origin, text, family="", bold=False, italic=False, size=12.0,
             color=(0, 0, 0), wrap_width=None):
    """Add text: write text into the page itself (not an annotation) with its first baseline
    at origin (unrotated page coordinates), reading upright as the page is displayed.
    family "" = Helvetica, which every PDF reader has built in. Returns the font name used.
    Raises ValueError (before changing anything) if no font can write the text."""
    if any(ord(c) > 0xFFFF for c in text):
        raise ValueError(tr("Emoji and other characters beyond U+FFFF can't be written into "
                            "a PDF page here. Remove them and try again."))
    found = chosen_font(page, family, bold, italic, text)
    if found is None and not _winansi_ok(text):
        # the chosen font (or Helvetica) lacks some characters: a font that has them
        found = _unicode_font(page, text) or _broad_font(page, text)
        if found is None:
            bad = _unwritable(text)
            names = ", ".join(f"{c} (U+{ord(c):04X})" for c in bad[:6]) or tr("some characters")
            raise ValueError(tr("No font on this computer can write these characters: "
                                "{names}. Remove or replace them and try again.").format(
                                    names=names))
    if found:
        fontname, font, source = found
        page.insert_font(fontname=fontname, **source)
    else:
        fontname = _BASE14_STYLE[(bool(bold), bool(italic))]
        font = pymupdf.Font(fontname)
    lines = _wrap(text, font, size, wrap_width) if wrap_width else text.split("\n")
    page.insert_text(pymupdf.Point(origin), "\n".join(lines), fontsize=size, fontname=fontname,
                     color=color, rotate=page.rotation, lineheight=1.2)
    if found:
        _fix_spaces(page, fontname, font)
    return fontname


def _pick_font(page, span, text):
    """(font name, Font, how to insert it) for text, or None to use a built-in PDF font."""
    if any(ord(c) > 0xFFFF for c in text):
        # emoji and other characters beyond U+FFFF: PDF text writing here truncates them to
        # a different character, so never write them
        raise LookupError
    found = _embedded_font(page, span, text) or _system_font(page, span, text)
    if not found and not _winansi_ok(text):
        found = _unicode_font(page, text) or _broad_font(page, text)
        if not found:
            raise LookupError
    return found


def _scan_font(page, scan, text):
    """The font matched to a scanned line, when it can write text: (found, None) for an
    installed font, (None, name) for a built-in one, (None, None) when it can't."""
    cand = scan.get("font")
    if cand is None:
        return (None, "helv") if _winansi_ok(text) else (None, None)
    name, _label, _kind, _bold, _italic, source = cand
    if source is None:
        return (None, name) if _winansi_ok(text) else (None, None)
    try:
        font = pymupdf.Font(**source)
        if all(font.has_glyph(ord(c)) for c in text if c not in "\n\r"):
            page.insert_font(fontname=name, **source)
            return (name, font, source), None
    except Exception:
        pass
    return None, None


def _unwritable(text):
    """The characters of text that no font KanzonasPDF can use has (for the error message)."""
    try:
        uni = pymupdf.Font("cjk")
    except Exception:
        uni = None
    out = []
    for c in dict.fromkeys(text):
        if ord(c) <= 0xFFFF and (c in "\n\r" or _winansi_ok(c) or
                                 (uni is not None and uni.has_glyph(ord(c)))):
            continue
        out.append(c)
    return out


def removal_bands(line):
    """Where a line's letters are taken out (unrotated page coords). A letter goes when the
    redaction touches its box, which spans the font's full height: a thin band through the
    middle of each span takes all of it (punctuation too) and never reaches the boxes of
    the lines above and below, even where those overlap this one (OCR text layers)."""
    dx, dy = line["dir"]
    out = []
    for s in line["spans"]:
        r = pymupdf.Rect(s["bbox"])
        if abs(dx) >= abs(dy):
            mid, half = (r.y0 + r.y1) / 2, max(0.5, r.height * 0.1)
            r = pymupdf.Rect(r.x0, mid - half, r.x1, mid + half)
        else:
            mid, half = (r.x0 + r.x1) / 2, max(0.5, r.width * 0.1)
            r = pymupdf.Rect(mid - half, r.y0, mid + half, r.y1)
        out.append(r)
    return out


def _remove_lines(page, lines, keep_links=True):
    """Take the lines' letters out of the page. Applying a redaction also drops every link
    it touches: keep_links puts those back (editing or moving linked words keeps the link,
    a drawing set's sheet hyperlinks included)."""
    doc = page.parent
    saved = []
    if keep_links:
        for xref, kind, *_ in page.annot_xrefs():
            if kind == pymupdf.PDF_ANNOT_LINK:
                saved.append((xref, doc.xref_object(xref, compressed=True)))
    for line in lines:
        for r in removal_bands(line):
            page.add_redact_annot(r, fill=False)
    page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE,
                          graphics=pymupdf.PDF_REDACT_LINE_ART_NONE,
                          text=pymupdf.PDF_REDACT_TEXT_REMOVE)
    if saved:
        have = {x for x, _k, *_ in page.annot_xrefs()}
        lost = [(x, src) for x, src in saved if x not in have]
        if lost:
            refs = []
            for _x, src in lost:
                new = doc.get_new_xref()
                doc.update_object(new, src)
                refs.append(f"{new} 0 R")
            kind, val = doc.xref_get_key(page.xref, "Annots")
            if kind == "xref":
                val = doc.xref_object(int(val.split()[0]))
            items = re.findall(r"\d+ 0 R", val) if kind in ("array", "xref") else []
            doc.xref_set_key(page.xref, "Annots", "[" + " ".join(items + refs) + "]")


def delete_lines(page, lines, keep_links=False):
    """Take these lines of text out of the page; pictures and line art stay. Links on them
    go too, unless keep_links."""
    from .annotations import each_annot
    if any(a.type[0] == pymupdf.PDF_ANNOT_REDACT for a in each_annot(page)):
        raise ValueError(tr("Apply or remove the redaction marks on this page before "
                            "deleting its text."))
    _remove_lines(page, lines, keep_links)


def _font_for(page, span, text):
    """(font for writing text like span, text): the span's own font when it can, otherwise
    the closest one; look-alikes replace symbols few fonts have (minus sign, diameter,
    invisible spaces, ligatures...). Raises ValueError when nothing can write it."""
    try:
        return _pick_font(page, span, text), text
    except LookupError:
        swapped = "".join(LOOKALIKES.get(c, c) for c in text)
        try:
            return _pick_font(page, span, swapped), swapped
        except LookupError:
            bad = _unwritable(swapped)
            names = ", ".join(f"{c} (U+{ord(c):04X})" for c in bad[:6]) or tr("some characters")
            raise ValueError(tr("No font on this computer can write these characters of the "
                                "new text: {names}. Remove or replace them and try again.")
                             .format(names=names))


_MARKER = re.compile(r"^\s*(?:(?:[\u2022\u2023\u2043\u2219\u25a0-\u25ff\u2700-\u27bf\ue000-\uf8ff"
                     r"\u2013\u2014*-]"
                     r"|\(?(?:\d{1,3}|[A-Za-z]|[ivxIVX]{1,4})[.)](?:\d{1,2}[.)]?)*)(?:\s|$)"
                     r"|\d{1,3}[.)](?=[A-Z]))")     # (a number run into its text: "1.Turn")
_WORD = re.compile(r"[^\W_]", re.UNICODE)


def _space_w(size):
    return 0.27 * size


def _visible_right(ln, box, measure=None):
    """Right end of a line's letters: its box without trailing spaces (word processors
    keep the space a line was broken at)."""
    t = line_text(ln)
    trail = len(t) - len(t.rstrip(" "))
    if not trail:
        return box.x1
    size = main_span(ln)["size"]
    try:
        w = measure(" " * trail, size) if measure else trail * _space_w(size)
    except Exception:
        w = trail * _space_w(size)
    return box.x1 - w


def _words(text):
    return [w for w in text.split() if _WORD.search(w)]


def flows(lines, measure=None):
    """True when lines read as wrapped text: each line (but the last) ends where the next
    line's first word wouldn't have fit, and has words enough to be running text. A column
    of labels, a title block or schedule entries stacked at a normal line spacing don't,
    and are edited a line at a time."""
    if len(lines) < 2:
        return False
    boxes = [pymupdf.Rect(ln["bbox"]) for ln in lines]
    rights = [_visible_right(ln, b, measure) for ln, b in zip(lines, boxes)]
    body = [b.x0 for b in boxes[1:]]
    if max(body) - min(body) > 1.5:
        # centered or set right: compare the lines' widths
        rights = [r - b.x0 for r, b in zip(rights, boxes)]
    full = max(rights)
    counts = []
    for ln, b, right, nxt, nb in zip(lines, boxes, rights, lines[1:], boxes[1:]):
        t, tn = line_text(ln).strip(), line_text(nxt).strip()
        if not tn or "\t" in t or "   " in t:
            return False
        n = len(_words(t))
        if n < 2:
            return False
        counts.append(n)
        word = tn.split(" ")[0]
        size = main_span(ln)["size"]
        try:
            word_w = measure(word, size) if measure else None
        except Exception:
            word_w = None
        if word_w is None:
            word_w = nb.width * len(word) / max(1, len(tn))
        if full - right > word_w + _space_w(size) + 0.3 * size:
            return False
    last = line_text(lines[-1]).strip()
    if "\t" in last or "   " in last:
        return False
    return sum(counts) / len(counts) >= 4 and sum(counts) + len(_words(last)) >= 8


def _hyphen_joins(left, right):
    """A word broken at a line's end with a hyphen: is the hyphen only the break (it goes
    when the lines are joined) or part of the word (self-/consolidating keeps it)? Only a
    joined word the dictionary knows loses it."""
    a = re.findall(r"[A-Za-z]+$", left[:-1])
    b = re.findall(r"^[a-z]+", right)
    if not a or not b:
        return False
    try:
        from . import spelling
        return spelling.is_known(a[0] + b[0])
    except Exception:
        return False


def _paragraph_parts(lines):
    """(paragraph text, where each line's text starts in it)."""
    out, starts = "", []
    for ln in lines:
        t = line_text(ln).strip()
        if not t:
            starts.append(len(out))
            continue
        if not out:
            out = t
            starts.append(0)
            continue
        if out.endswith("\u00ad"):
            out = out[:-1]
        elif out.endswith("-") and len(out) > 1 and out[-2].isalpha() and t[:1].islower():
            if _hyphen_joins(out.split(" ")[-1], t):
                out = out[:-1]
        else:
            out += " "
        starts.append(len(out))
        out += t
    return out, starts


def paragraph_text(lines):
    """The words of a paragraph's lines as one text: lines joined with a space; a word
    split by a hyphen at a line's end (spe-/cification) joined again, a hyphenated word
    (self-/consolidating) kept."""
    return _paragraph_parts(lines)[0]


def line_index(line, pt):
    """Where in line_text(line) the point pt (on the page, unrotated coords) falls along
    the line, in its own direction: the text cursor goes there when sideways text or a line
    on a rotated page is clicked (its editor box is upright, so the click can't place it)."""
    raw = line_text(line)
    at = _along(pymupdf.Rect(pt, pt), line)[0]
    pos, length, prev = 0, 0, None
    for sp in line["spans"]:
        if prev is not None:
            gap = _along(pymupdf.Rect(sp["bbox"]), line)[0] - _along(pymupdf.Rect(prev["bbox"]), line)[1]
            if gap > 0.15 * sp["size"] and not raw[:length].endswith(" ") and \
                    not sp["text"].startswith(" "):
                length += 1
        a0, a1 = _along(pymupdf.Rect(sp["bbox"]), line)
        n = len(sp["text"])
        if at >= a1:
            pos = length + n
        elif at > a0 and n:
            pos = length + int(round((at - a0) / max(a1 - a0, 0.01) * n))
            break
        else:
            pos = length
            break
        length += n
        prev = sp
    return max(0, min(pos, len(raw)))


def paragraph_index(lines, pt):
    """Where in paragraph_text(lines) the point pt (on the page) is: the text cursor goes
    there when a paragraph is clicked."""
    text, starts = _paragraph_parts(lines)
    best = min(range(len(lines)), key=lambda i: (0 if pymupdf.Rect(lines[i]["bbox"]).y0 <= pt.y <=
                                                 pymupdf.Rect(lines[i]["bbox"]).y1 else 1,
                                                 abs(_baseline(lines[i]) - pt.y)))
    ln = lines[best]
    raw = line_text(ln)
    lead = len(raw) - len(raw.lstrip())
    # walk the spans as line_text joins them (a space between pieces set apart)
    pos, length, prev = 0, 0, None
    for sp in ln["spans"]:
        if prev is not None:
            gap = _along(pymupdf.Rect(sp["bbox"]), ln)[0] - _along(pymupdf.Rect(prev["bbox"]), ln)[1]
            if gap > 0.15 * sp["size"] and not raw[:length].endswith(" ") and \
                    not sp["text"].startswith(" "):
                length += 1
        r = pymupdf.Rect(sp["bbox"])
        n = len(sp["text"])
        if pt.x >= r.x1:
            pos = length + n
        elif pt.x > r.x0 and n:
            pos = length + int(round((pt.x - r.x0) / max(r.width, 0.01) * n))
            break
        else:
            pos = length
            break
        length += n
        prev = sp
    end = starts[best + 1] if best + 1 < len(starts) else len(text)
    return max(starts[best], min(end, starts[best] + pos - lead))


def _marker_before(row, rows_on_base):
    """A bullet or number set apart just before this line (on its baseline): the line
    starts a list item."""
    r, ln = row
    size = main_span(ln)["size"]
    for r2, ln2 in rows_on_base:
        if ln2 is ln or r2.x1 > r.x0 + 0.5 or r.x0 - r2.x1 > 4 * size:
            continue
        if len(line_text(ln2).strip()) <= 6:
            return True
    return False


def _split_marker(r, ln):
    """A line that starts with a bullet or number set apart from its text ("2.   DO NOT
    SCALE...") as two pieces, so the number stays and the text is the paragraph's."""
    spans = ln["spans"]
    first = spans[0]["text"].strip()
    if len(spans) < 2 or not first or len(first) > 6 or not _MARKER.match(first + " "):
        return [(r, ln)]
    size = main_span(ln)["size"]
    # (MuPDF may fill the gap with a space of its own)
    k = next((i for i in range(1, len(spans)) if spans[i]["text"].strip()), None)
    if k is None or spans[k]["bbox"][0] - spans[0]["bbox"][2] < 0.3 * size:
        return [(r, ln)]
    mark = {"bbox": pymupdf.Rect(spans[0]["bbox"]), "dir": ln["dir"], "spans": spans[:k]}
    rest_box = pymupdf.Rect()
    for sp in spans[k:]:
        rest_box |= pymupdf.Rect(sp["bbox"])
    rest = {"bbox": rest_box, "dir": ln["dir"], "spans": spans[k:]}
    return [(pymupdf.Rect(mark["bbox"]), mark), (pymupdf.Rect(rest_box), rest)]


def paragraph_rows(lines):
    """The page's horizontal visible lines as paragraph_at reads them (a justified line's
    pieces joined, a list item's number split off), sorted by baseline. Worth keeping per
    page: paragraph_at(lines, line, rows) then answers a click quickly."""
    rows = [(r, ln) for r, ln in _join_spread_pieces(
        [(r, ln) for r, ln in lines if visible(ln)])
        if abs(ln["dir"][0] - 1) < 0.01 and abs(ln["dir"][1]) < 0.01]
    rows = [piece for h in rows for piece in _split_marker(*h)]
    rows.sort(key=lambda h: (_baseline(h[1]), h[0].x0))
    return rows


def _starts_item(ln):
    """The line begins with a list number or bullet ("1. The contractor..."): it's the first
    line of a list item, never the continuation of the line above."""
    t = line_text(ln).lstrip()
    return bool(_MARKER.match(t)) and len(t.split()) > 1


def paragraph_at(lines, line, rows=None):
    """The lines of the paragraph holding line (horizontal text; text_lines output), in
    reading order, or None when it isn't clearly a paragraph of wrapped lines: what a
    click with Edit text rewrites. Lines stack at one size and an even line spacing, lined
    up on one side or centered (the first may be indented, or set out before a list
    number); a bullet or number, a change of size or spacing, or lines that don't wrap like
    running text end it. rows: paragraph_rows(lines), when kept."""
    import bisect
    if rows is None:
        rows = paragraph_rows(lines)
    ids = {id(s) for s in line["spans"]}
    mine = [h for h in rows if h[1] is line or any(id(s) in ids for s in h[1]["spans"])]
    # (a number split off its line: the line's text is what was clicked)
    start = max(mine, key=lambda h: len(line_text(h[1]).strip())) if mine else None
    if start is None:
        # the same line from another reading of the page: match by place
        box, base = pymupdf.Rect(line["bbox"]), _baseline(line)
        start = next((h for h in rows if abs(_baseline(h[1]) - base) < 0.5 and
                      h[0].x0 - 0.5 <= box.x0 and box.x1 <= h[0].x1 + 0.5), None)
    if start is None:
        return None
    bases = [_baseline(ln) for _r, ln in rows]

    def size_of(h):
        return main_span(h[1])["size"]
    size = size_of(start)

    def on_base(h):
        b = _baseline(h[1])
        i, j = bisect.bisect_left(bases, b - 0.25 * size), bisect.bisect_right(bases, b + 0.25 * size)
        return rows[i:j]

    def near(h, down):
        """The row on the nearest baseline above / below h that overlaps it across the page."""
        b = _baseline(h[1])
        lo, hi = (b + 0.7 * size, b + 2.2 * size) if down else (b - 2.2 * size, b - 0.7 * size)
        i, j = bisect.bisect_left(bases, lo), bisect.bisect_right(bases, hi)
        cands = [c for c in rows[i:j] if abs(size_of(c) - size) <= 0.03 * size and
                 c[0].x0 < h[0].x1 + 2 * size and c[0].x1 > h[0].x0 - 2 * size]
        if not cands:
            return None
        nb = min(cands, key=lambda c: abs(_baseline(c[1]) - b))
        nb_base = _baseline(nb[1])
        same = [c for c in cands if abs(_baseline(c[1]) - nb_base) < 0.25 * size]
        # the piece running along most of h, not a number or label set apart at its start
        return max(same, key=lambda c: (min(c[0].x1, h[0].x1) - max(c[0].x0, h[0].x0),
                                        -abs(c[0].x0 - h[0].x0)))

    def lone_marker(h):
        """A list item's number or bullet on its own ("(a)", "2.", "\u2022"): never a line
        of the paragraph."""
        t = line_text(h[1]).strip()
        return len(t) <= 6 and bool(_MARKER.match(t + " "))

    tol = max(1.5, 0.15 * size)
    pitch = [None]

    def even(a, b):
        """The same line spacing as the lines taken so far (it's set by the first two)."""
        step = abs(_baseline(b[1]) - _baseline(a[1]))
        return pitch[0] is None or abs(step - pitch[0]) <= max(0.6, 0.08 * pitch[0])

    def take(a, b):
        if pitch[0] is None:
            pitch[0] = abs(_baseline(b[1]) - _baseline(a[1]))

    def edges(h):
        right = _visible_right(h[1], h[0])
        return h[0].x0, right, (h[0].x0 + right) / 2

    def lined_up(a, b):
        """The ways two lines line up: a set of 'left', 'right', 'center' (a justified
        paragraph's full lines line up on both sides)."""
        ea, eb = edges(a), edges(b)
        return {m for m, k in (("left", 0), ("right", 1), ("center", 2))
                if abs(ea[k] - eb[k]) <= tol}

    mode = [None]                       # the ways all the body's lines line up

    def ends(a, b, chain_now):
        """a, followed by b, is a paragraph's last line: the next line's first word would
        have fitted on it (a short line ends a paragraph; the next one starts another)."""
        tb = line_text(b[1]).strip()
        if not tb:
            return True
        hs = chain_now + [a, b]
        centered = mode[0] is not None and "left" not in mode[0]
        reach = [(edges(h)[1] - edges(h)[0]) if centered else edges(h)[1] for h in hs]
        word = tb.split(" ")[0]
        word_w = b[0].width * len(word) / max(1, len(tb))
        mine = (edges(a)[1] - edges(a)[0]) if centered else edges(a)[1]
        return max(reach) - mine > word_w + _space_w(size) + 0.3 * size

    def fits(a, b):
        m = lined_up(a, b)
        if mode[0] is not None:
            m &= mode[0]
        if not m:
            return False
        mode[0] = m
        return True

    def full(a, b):
        return abs(edges(a)[1] - edges(b)[1]) <= tol

    def first_line(up, cur):
        """up, just above cur, is the paragraph's first line, set in (an indent) or set out
        (a hanging indent: before a list number, or in justified text)?"""
        dx = up[0].x0 - cur[0].x0
        if mode[0] is not None and "left" not in mode[0]:
            return False
        if tol < dx <= 6 * size:
            return True
        return -6 * size <= dx < -tol and (_starts_item(up[1]) or
                                           (full(up, cur) and body_left(cur)))

    def body_left(cur):
        """cur and the line below it line up on the left (the body of a paragraph whose
        first line is set out)."""
        if mode[0] is not None:
            return "left" in mode[0]
        below = near(cur, down=True)
        return below is not None and "left" in lined_up(cur, below)

    chain = [start]
    # upward: lines lined up the same way, until the first line (set in or out, a list
    # item's first line or one with its number before it)
    if not (_marker_before(start, on_base(start)) or _starts_item(start[1])):
        cur = start
        while True:
            up = near(cur, down=False)
            if up is None or not even(up, cur) or lone_marker(up) or ends(up, cur, chain):
                break
            if first_line(up, cur):
                take(up, cur)
                chain.insert(0, up)
                mode[0] = (mode[0] or {"left"}) & {"left"}
                break
            if not fits(up, cur):
                break
            take(up, cur)
            chain.insert(0, up)
            cur = up
            if _marker_before(up, on_base(up)) or _starts_item(up[1]):
                break
    # downward: the body's lines, lined up the same way; a list item's first line ends it
    cur = chain[-1]
    while True:
        down = near(cur, down=True)
        if down is None or not even(cur, down) or _marker_before(down, on_base(down)) or \
                _starts_item(down[1]) or lone_marker(down) or ends(cur, down, chain[:-1]):
            break
        if len(chain) == 1:
            dx = down[0].x0 - cur[0].x0
            # cur is a first line set in (indent) or out before its number (hanging)
            # (a numbered first line's text may run back to the margin below its number)
            setin = -6 * size <= dx < -tol and (not _marker_before(cur, on_base(cur)) or
                                                down[0].x0 < cur[0].x0 - 2 * size)
            setout = tol < dx <= 6 * size and (_starts_item(cur[1]) or (
                full(cur, down) and body_left(down)))
            if (setin or setout) and not lined_up(cur, down) & {"left"}:
                mode[0] = {"left"}
                take(cur, down)
                chain.append(down)
                cur = down
                continue
        if not fits(cur, down):
            break
        take(cur, down)
        chain.append(down)
        cur = down
    lines_out = [ln for _r, ln in chain]
    if len(lines_out) < 2 or not flows(lines_out) or _sentence_per_line(lines_out):
        return None
    return lines_out


def _sentence_per_line(lines):
    """Every line ends a sentence and the next starts one ("Supports Ubuntu." / "Built-in
    speaker."): a list of one-line items (its bullets may be drawn, not text), not one
    paragraph."""
    for ln, nxt in zip(lines, lines[1:]):
        t = line_text(ln).rstrip().rstrip(")]\"'\u201d\u2019")
        n = line_text(nxt).lstrip()
        if not t or t[-1] not in ".!?:;" or not n[:1].isupper():
            return False
    return True


def paragraph_layout(lines, measure=None, exact=False, gaps=None):
    """How a paragraph sits on the page: {"left", "first_left" (the first line's start:
    an indent), "right", "width", "first" (first baseline), "step" (baseline to
    baseline), "align" (left, right, center, justify), "span" (its main span)}. lines: in
    reading order, horizontal. measure(text, size): the natural width of text in the
    paragraph's font, to tell justified lines (their words spread wider than that) even in
    a paragraph of two lines; exact: measure uses the paragraph's own font (any stretch
    counts), not a stand-in (only clear stretching). gaps(line): the spaces between its
    words as set on the page: justified lines have wider ones than the last line (or than
    a space), whatever the font measures."""
    boxes = [pymupdf.Rect(ln["bbox"]) for ln in lines]
    lefts = [b.x0 for b in boxes]
    rights = [_visible_right(ln, b, measure) for ln, b in zip(lines, boxes)]
    mids = [(l + r) / 2 for l, r in zip(lefts, rights)]
    bases = [ln["spans"][0]["origin"][1] for ln in lines]
    steps = sorted(b - a for a, b in zip(bases, bases[1:]))
    main = max((s for ln in lines for s in ln["spans"] if s["text"].strip()),
               key=lambda s: len(s["text"].strip()))

    def spread(v):
        return max(v) - min(v) if v else 0.0
    tol = 1.5

    def stretched(ln, box, right):
        t = line_text(ln).rstrip(" ")
        gaps = t.strip().count(" ")
        if measure is None or not gaps:
            return False
        try:
            extra = (right - box.x0) - measure(t, main["size"])
        except Exception:
            return False
        if exact:
            return extra > 1.0
        return extra / gaps > 0.12 * main["size"] and extra > 0.02 * box.width
    # a first line indented (or set out) from the rest keeps its own start
    body = lefts[1:] if len(lefts) > 1 else lefts
    first_left = lefts[0]
    left = min(body) if spread(body) <= tol else min(lefts)
    if abs(first_left - left) <= tol:
        first_left = left
    def median(v):
        v = sorted(v)
        return v[len(v) // 2] if v else None

    def wide_gaps():
        """None when the gaps can't tell; else whether the full lines' spaces are wider."""
        if gaps is None:
            return None
        try:
            natural = median(gaps(lines[-1]))
            if natural is None and measure is not None:
                natural = measure(" ", main["size"])
            if natural is None:
                return None
            per = [median(gaps(ln)) for ln in lines[:-1]]
        except Exception:
            return None
        per = [g for g in per if g is not None]
        if not per:
            return None
        wide = sum(g > natural + max(0.35, 0.1 * natural) for g in per)
        return wide * 2 > len(per)
    align = "left"
    if spread(body) <= tol:
        full = len(lines) >= 2 and spread(rights[:-1]) <= tol
        judged = wide_gaps() if full else None
        if judged is not None:
            if judged:
                align = "justify"
        elif full and measure is not None:
            hits = sum(stretched(ln, b, r) for ln, b, r in zip(lines[:-1], boxes[:-1], rights[:-1]))
            if hits * 2 >= len(lines) - 1 and (len(lines) >= 3 and rights[-1] < max(rights) - 3
                                               or hits == len(lines) - 1):
                align = "justify"
        elif full and len(lines) >= 3 and rights[-1] < max(rights) - 3:
            align = "justify"
    elif spread(rights) <= tol:
        align = "right"
    elif spread(mids) <= tol:
        align = "center"
    if align in ("right", "center"):
        first_left = left = min(lefts)
    return {"left": left, "first_left": first_left, "right": max(rights),
            "width": max(rights) - left, "first": bases[0],
            "step": steps[len(steps) // 2] if steps else main["size"] * 1.2,
            "align": align, "span": main}


def _word_gaps(words, line):
    """The spaces between a line's words as set on the page (points). words: the page's
    words around it (page.get_text("words"))."""
    box = pymupdf.Rect(line["bbox"]) + (-1, -1, 1, 1)
    base = _baseline(line)
    mine = sorted((w for w in words if w[1] - 1 <= base <= w[3] + 1 and
                   box.x0 <= w[0] and w[2] <= box.x1), key=lambda w: w[0])
    return [b[0] - a[2] for a, b in zip(mine, mine[1:]) if b[0] >= a[2] - 0.5]


def replace_paragraph(page, lines, new_text, wrap_width=None, font=None, size=None,
                      offset=(0, 0)):
    """Rewrite a whole paragraph (horizontal lines, reading order) with new_text, wrapped to
    its width (or wrap_width) in its font, size, color, line spacing and alignment. font /
    size: a font or size picked in Properties instead. offset: move it (points). Returns
    (font name, its new box, the baselines written). Raises ValueError (before changing
    anything) if no font can write it."""
    main = paragraph_layout(lines)["span"]
    text = new_text.strip()
    found = None
    if text and font and font[0]:
        found = chosen_font(page, font[0], font[1], font[2], text)
    if text and found is None:
        found, text = _font_for(page, main, text)
    # the paragraph's own font measures how far its lines were spread (justified)
    area = pymupdf.Rect()
    for ln in lines:
        area |= pymupdf.Rect(ln["bbox"])
    words = page.get_text("words", clip=area + (-1, -1, 1, 1))
    try:
        own, _t = _font_for(page, main, paragraph_text(lines))
        ruler = own[1] if own else pymupdf.Font(_base14(main))
        # exact: the paragraph's own font (embedded, installed, or a built-in PDF font it
        # names); a stand-in for a font that isn't here measures only roughly
        name = main.get("font", "").split("+")[-1]
        exact = (own is None and name.startswith(("Helvetica", "Times", "Courier"))) or \
            (own is not None and not own[0].startswith(("KZUni", "KZB")))
        lay = paragraph_layout(lines, lambda t, sz: ruler.text_length(t, fontsize=sz), exact,
                               lambda ln: _word_gaps(words, ln))
    except ValueError:
        lay = paragraph_layout(lines, gaps=lambda ln: _word_gaps(words, ln))
    size = float(size or main["size"])
    step = lay["step"] * (size / main["size"])
    _remove_lines(page, lines)
    if not text:
        return None, pymupdf.Rect(), []
    if found:
        fontname, fnt, source = found
        page.insert_font(fontname=fontname, **source)
    else:
        fontname = _base14(main)
        fnt = pymupdf.Font(fontname)
    width = wrap_width or lay["width"]
    indent = lay["first_left"] - lay["left"]         # the first line's own start
    rows = []
    for part in text.split("\n"):                    # Shift+Enter: a new paragraph
        wrapped = _wrap_indented(part, fnt, size, width, indent)
        rows += [(r, i == 0, i == len(wrapped) - 1) for i, r in enumerate(wrapped)]
    color = _rgb(main["color"])
    left, right = lay["left"] + offset[0], lay["left"] + offset[0] + width
    y = lay["first"] + offset[1]
    top = y - size
    bases = []
    for row, first, last in rows:
        bases.append(y)
        row = row.strip()
        length = fnt.text_length(row, fontsize=size)
        words = row.split(" ")
        start = left + indent if first else left
        if lay["align"] == "justify" and not last and len(words) > 1:
            gap = (right - start - sum(fnt.text_length(w, fontsize=size) for w in words)) / \
                (len(words) - 1)
            x = start
            for w in words:
                page.insert_text(pymupdf.Point(x, y), w, fontsize=size, fontname=fontname,
                                 color=color)
                x += fnt.text_length(w, fontsize=size) + gap
        else:
            x = {"right": right - length, "center": (left + right - length) / 2}.get(
                lay["align"], start)
            page.insert_text(pymupdf.Point(x, y), row, fontsize=size, fontname=fontname,
                             color=color)
        y += step
    if found:
        _fix_spaces(page, fontname, fnt)
    return fontname, pymupdf.Rect(min(left, left + indent), top, right,
                                  y - step + size * 0.25), bases


def replace_line(page, line, new_text, offset=(0, 0), wrap_width=None, font=None, size=None,
                 scan="auto", info=None):
    """Remove the line's text and write new_text in its place.

    offset: move the text by (dx, dy) points. wrap_width: wrap to this width (points).
    font: (family, bold, italic) to change the line's font to an installed one (Properties >
    Font with Edit text); None keeps the line's own font. size: new font size (points);
    None keeps the line's.
    scan: for a line on a scanned page (see scan_text), how to match the scan: "auto" works
    it out, None treats the line as ordinary text, or a scan_text.analyze() result. The old
    letters in the picture are then covered with the paper color, and the new text is
    written in the font, size, color and baseline that reproduce them (a font or size picked
    in Properties still wins). info: a dict that gets "scan" (the match used, or None).
    Returns the font name used: 'KZ…' = original embedded font, 'KZS…' = installed system
    font of the same name, 'KZF…' = a font picked in Properties, 'KZUni' = bundled Unicode
    font, otherwise a built-in PDF font.
    Raises ValueError (before changing anything) if no font can write the new text."""
    main = main_span(line)
    first = line["spans"][0]
    from .annotations import each_annot
    if any(a.type[0] == pymupdf.PDF_ANNOT_REDACT for a in each_annot(page)):
        # removing the old text applies every redaction on the page, pending ones included
        raise ValueError(tr("Apply or remove the redaction marks on this page before "
                            "editing its text."))

    if scan == "auto":
        try:
            from . import scan_text
            scan = scan_text.analyze(page, line, line_text(line))
        except Exception:
            scan = None                 # never let the scan match stop an edit
    if info is not None:
        info["scan"] = scan
    cover = scan["cover"] if scan else []
    if scan and scan.get("cover_letters") and (scan["lead"] or scan["trail"]):
        # symbols the scanner's OCR read as part of the line (a checkbox before it): when
        # the new text keeps them, the picture keeps showing them and they aren't rewritten
        t = new_text.strip()
        lead, trail = scan["lead"], scan["trail"]
        if t.startswith(lead) and t.endswith(trail) and len(t) > len(lead) + len(trail):
            new_text = t[len(lead):len(t) - len(trail)].strip()
            cover = scan["cover_letters"]

    # 1) pick the font first, so nothing is deleted if the new text can't be written
    found = None
    builtin = None                      # a built-in PDF font matched to the scan
    if new_text.strip() and font and font[0]:
        found = chosen_font(page, font[0], font[1], font[2], new_text)
    if new_text.strip() and found is None and scan:
        found, builtin = _scan_font(page, scan, new_text)
    if new_text.strip() and found is None and builtin is None:
        found, new_text = _font_for(page, main, new_text)

    # 2) remove only the text of this line (keep line art and images)
    _remove_lines(page, [line])
    if scan:
        # the old letters in the scan's picture: covered with the paper color
        for r in cover:
            if not r.is_empty:
                page.draw_rect(r, color=None, fill=scan["paper"], width=0, overlay=True)

    if not new_text.strip():
        return None
    # 3) write the replacement at the same baseline / direction
    if found:
        fontname, font, source = found
        # applying the redaction drops fonts no text uses yet, including the one just
        # chosen: add it again (without this, writing failed: "need font file or buffer")
        page.insert_font(fontname=fontname, **source)
    else:
        fontname = builtin or _base14(main)
        font = pymupdf.Font(fontname)
    size = float(size or (scan["size"] if scan else main["size"]))
    lines = _wrap(new_text, font, size, wrap_width) if wrap_width else new_text.split("\n")
    origin = pymupdf.Point(scan["origin"] if scan else first["origin"]) + offset
    page.insert_text(origin, "\n".join(lines), fontsize=size, fontname=fontname,
                     color=scan["color"] if scan else _rgb(main["color"]),
                     rotate=line_rotation(line), lineheight=1.2)
    if found:
        _fix_spaces(page, fontname, font)
    return fontname
