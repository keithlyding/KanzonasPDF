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


def visible(line):
    """False for text nobody sees (a scanner's OCR layer: invisible, opacity 0)."""
    return any(s.get("alpha", 255) for s in line["spans"] if s["text"].strip())


def _join_spread_pieces(rows):
    """Pieces of one line of a justified paragraph: the wide gaps between its words split
    it into pieces on the same baseline (text_lines keeps a line's pieces apart beyond a
    small gap, so labels and table cells stay separate). Join pieces in the same font, size
    and color up to 1.5 letter heights apart into one line."""
    def key(span):
        return (span.get("font"), round(span["size"], 1), span.get("color"))
    rows = sorted(rows, key=lambda h: (round(h[1]["dir"][0], 2), round(h[1]["dir"][1], 2),
                                       round(_baseline(h[1]), 1), _along(h[0], h[1])[0]))
    out = []
    for r, ln in rows:
        if out:
            lr, last = out[-1]
            size = max(s["size"] for s in ln["spans"])
            gap = _along(r, ln)[0] - _along(lr, last)[1]
            if (abs(last["dir"][0] - ln["dir"][0]) < 0.01 and
                    abs(last["dir"][1] - ln["dir"][1]) < 0.01 and
                    abs(_baseline(last) - _baseline(ln)) < 0.25 * size and
                    0 <= gap <= 1.5 * size and
                    key(main_span(last)) == key(main_span(ln))):
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
        raise ValueError("Emoji and other characters beyond U+FFFF can't be written into a "
                         "PDF page here. Remove them and try again.")
    found = chosen_font(page, family, bold, italic, text)
    if found is None and not _winansi_ok(text):
        # the chosen font (or Helvetica) lacks some characters: a font that has them
        found = _unicode_font(page, text) or _broad_font(page, text)
        if found is None:
            bad = _unwritable(text)
            names = ", ".join(f"{c} (U+{ord(c):04X})" for c in bad[:6]) or "some characters"
            raise ValueError("No font on this computer can write these characters: "
                             f"{names}. Remove or replace them and try again.")
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
        raise ValueError("Apply or remove the redaction marks on this page before deleting "
                         "its text.")
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
            names = ", ".join(f"{c} (U+{ord(c):04X})" for c in bad[:6]) or "some characters"
            raise ValueError("No font on this computer can write these characters of the new "
                             f"text: {names}. Remove or replace them and try again.")


def flows(lines):
    """True when lines read as wrapped text: each line (but the last) ends where the next
    line's first word wouldn't have fit. A column of labels or schedule entries stacked at a
    normal line spacing doesn't, and is edited a line at a time."""
    boxes = [pymupdf.Rect(ln["bbox"]) for ln in lines]
    full = max(b.width for b in boxes)
    for ln, b, nxt, nb in zip(lines, boxes, lines[1:], boxes[1:]):
        t = line_text(nxt).strip()
        if not t:
            return False
        word = t.split(" ")[0]
        size = max(s["size"] for s in ln["spans"])
        word_w = nb.width * len(word) / max(1, len(t))
        if full - b.width > word_w + 0.8 * size:
            return False
    return True


def paragraph_text(lines):
    """The words of a paragraph's lines as one text: lines joined with a space, a word
    split by a hyphen at a line's end joined again."""
    out = ""
    for ln in lines:
        t = line_text(ln).strip()
        if not t:
            continue
        if not out:
            out = t
        elif out.endswith("-") and len(out) > 1 and out[-2].isalpha() and t[:1].islower():
            out = out[:-1] + t
        else:
            out += " " + t
    return out


def paragraph_layout(lines, measure=None, exact=False):
    """How a paragraph sits on the page: {"left", "right", "width", "first" (first
    baseline), "step" (baseline to baseline), "align" (left, right, center, justify),
    "span" (its main span)}. lines: in reading order, horizontal. measure(text, size): the
    natural width of text in the paragraph's font, to tell justified lines (their words
    spread wider than that) even in a paragraph of two lines; exact: measure uses the
    paragraph's own font (any stretch counts), not a stand-in (only clear stretching)."""
    boxes = [pymupdf.Rect(ln["bbox"]) for ln in lines]
    lefts = [b.x0 for b in boxes]
    rights = [b.x1 for b in boxes]
    mids = [(b.x0 + b.x1) / 2 for b in boxes]
    bases = [ln["spans"][0]["origin"][1] for ln in lines]
    steps = sorted(b - a for a, b in zip(bases, bases[1:]))
    main = max((s for ln in lines for s in ln["spans"] if s["text"].strip()),
               key=lambda s: len(s["text"].strip()))

    def spread(v):
        return max(v) - min(v) if v else 0.0
    tol = 1.5

    def stretched(ln, box):
        t = line_text(ln)
        gaps = t.strip().count(" ")
        if measure is None or not gaps:
            return False
        try:
            extra = box.width - measure(t, main["size"])
        except Exception:
            return False
        if exact:
            return extra > 1.0
        return extra / gaps > 0.12 * main["size"] and extra > 0.02 * box.width
    align = "left"
    if spread(lefts) <= tol:
        full = len(lines) >= 2 and spread(rights[:-1]) <= tol
        if full and len(lines) >= 3 and rights[-1] < max(rights) - 3:
            align = "justify"
        elif full and measure is not None and \
                all(stretched(ln, b) for ln, b in zip(lines[:-1], boxes[:-1])):
            align = "justify"
    elif spread(rights) <= tol:
        align = "right"
    elif spread(mids) <= tol:
        align = "center"
    return {"left": min(lefts), "right": max(rights), "width": max(rights) - min(lefts),
            "first": bases[0], "step": steps[len(steps) // 2] if steps else main["size"] * 1.2,
            "align": align, "span": main}


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
    try:
        own, _t = _font_for(page, main, paragraph_text(lines))
        ruler = own[1] if own else pymupdf.Font(_base14(main))
        # exact: the paragraph's own font (embedded, installed, or a built-in PDF font it
        # names); a stand-in for a font that isn't here measures only roughly
        name = main.get("font", "").split("+")[-1]
        exact = (own is None and name.startswith(("Helvetica", "Times", "Courier"))) or \
            (own is not None and not own[0].startswith(("KZUni", "KZB")))
        lay = paragraph_layout(lines, lambda t, sz: ruler.text_length(t, fontsize=sz), exact)
    except ValueError:
        lay = paragraph_layout(lines)
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
    rows = []
    for part in text.split("\n"):                    # Shift+Enter: a new paragraph
        wrapped = _wrap(part, fnt, size, width)
        rows += [(r, i == len(wrapped) - 1) for i, r in enumerate(wrapped)]
    color = _rgb(main["color"])
    left, right = lay["left"] + offset[0], lay["left"] + offset[0] + width
    y = lay["first"] + offset[1]
    top = y - size
    bases = []
    for row, last in rows:
        bases.append(y)
        row = row.strip()
        length = fnt.text_length(row, fontsize=size)
        words = row.split(" ")
        if lay["align"] == "justify" and not last and len(words) > 1:
            gap = (width - sum(fnt.text_length(w, fontsize=size) for w in words)) / (len(words) - 1)
            x = left
            for w in words:
                page.insert_text(pymupdf.Point(x, y), w, fontsize=size, fontname=fontname,
                                 color=color)
                x += fnt.text_length(w, fontsize=size) + gap
        else:
            x = {"right": right - length, "center": (left + right - length) / 2}.get(
                lay["align"], left)
            page.insert_text(pymupdf.Point(x, y), row, fontsize=size, fontname=fontname,
                             color=color)
        y += step
    if found:
        _fix_spaces(page, fontname, fnt)
    return fontname, pymupdf.Rect(left, top, right, y - step + size * 0.25), bases


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
        raise ValueError("Apply or remove the redaction marks on this page before editing "
                         "its text.")

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
