"""Editing existing page text, one line at a time.

PDF pages store positioned glyphs, not paragraphs, so true word-processor editing
isn't possible. Instead: find the line under the cursor, remove its characters
(redaction that leaves drawings and images alone), and write the new text at the same
baseline, size, color and direction. The original embedded font is reused when it
contains every needed character; otherwise the closest standard font is used.
"""

import contextlib
import glob
import math
import os
import re
import sys
import unicodedata

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


def page_text_dict(page, flags):
    """page.get_text("dict") of the page's own text only: not the words markups (text boxes,
    stamps, measurement labels) and form fields draw over it. Those belong to the markup or
    field: taken as page text, moving or editing them wrote their words into the page and
    took the text box away. (Unrotated coordinates, as get_text gives.)"""
    tp, flags = page_textpage(page, flags)
    return page.get_text("dict", flags=flags, textpage=tp)


def page_textpage(page, flags, clip=None):
    """(TextPage of the page's own text, without its markups; the flags it was read with).
    clip: read only there (a Rect, unrotated coordinates)."""
    from . import text_guard, undo_journal
    flags = text_guard.flags_for(page, flags)      # (MuPDF's crash on nested ActualText)
    turn = page.rotation
    # (turned upright for a moment, as PyMuPDF's own get_textpage does: not a change the
    # undo journal keeps, see undo_journal.detached)
    with undo_journal.detached(page.parent) if turn else contextlib.nullcontext():
        if turn:
            page.set_rotation(0)
        try:
            dl = page.get_displaylist(annots=False)
            stp = None
            # The page box clip is asked of MuPDF as a clip rectangle, not as its own
            # TEXT_MEDIABOX_CLIP: that one, reading a display list, dropped a line of
            # right-to-left text on a turned page once a drawing group elsewhere on it was
            # deleted (the glyph test it uses went wrong), while the text was still there and
            # still drawn: Edit text and Edit objects no longer saw it. Random battery, seed
            # 1112, 13 Nov 2026 (tests/test_text_page_clip.py); MuPDF 1.28.
            c = pymupdf.Rect(clip) if clip is not None else None
            if flags & pymupdf.TEXT_MEDIABOX_CLIP:
                c = (c & page.rect) if c is not None else pymupdf.Rect(page.rect)
            if c is not None:
                try:
                    m = pymupdf.mupdf
                    opts = m.FzStextOptions()
                    opts.flags = (flags & ~pymupdf.TEXT_MEDIABOX_CLIP) | m.FZ_STEXT_CLIP_RECT
                    box = m.FzRect(c.x0, c.y0, c.x1, c.y1)     # (kept alive while used)
                    opts.clip = box.internal()
                    stp = m.FzStextPage(dl.this, opts)
                except Exception:
                    stp = None          # (the whole page instead)
            if stp is None:
                stp = dl.get_textpage(flags=flags)
            tp = pymupdf.TextPage(stp)
        finally:
            if turn:
                page.set_rotation(turn)
    tp.parent = page
    return tp, flags


def text_lines(page):
    """[(rect, line)] for every visual text line on the page (unrotated coords).

    PDF producers often split one visual line into several pieces (kerning, a single
    letter placed separately, another text block). Pieces on the same baseline that
    touch or nearly touch are merged, so editing a line never leaves a letter behind."""
    pieces = []
    d = page_text_dict(page, pymupdf.TEXTFLAGS_DICT & ~pymupdf.TEXT_PRESERVE_IMAGES)
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


def right_to_left(text):
    """True when text has letters written right to left (Hebrew, Arabic...)."""
    return any(c > "\u058f" and unicodedata.bidirectional(c) in ("R", "AL") for c in text or "")


def refuse_right_to_left(*texts):
    """Raise ValueError when one of texts is written right to left. A page's letters are
    written left to right, one after another, unshaped: Hebrew and Arabic came out in the
    wrong order (and Arabic's letters unjoined), and a line edited, moved or replaced in
    was rewritten backwards from where it started, off the page's edge."""
    if any(right_to_left(t) for t in texts):
        raise ValueError(right_to_left_message())


def right_to_left_message():
    return tr("Text written right to left (Hebrew, Arabic...) can't be rewritten here yet: "
              "it would come out in the wrong order. Nothing was changed.")


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


def line_angle(line):
    """The text's direction in degrees, counterclockwise as shown (unrotated page space)."""
    dx, dy = line["dir"]
    return math.degrees(math.atan2(-dy, dx))


def off_quarter(line):
    """The line runs at an angle that isn't a quarter turn (a diagonal watermark): its
    exact angle, else None."""
    a = line_angle(line)
    off = (a - line_rotation(line) + 180) % 360 - 180
    return a if abs(off) > 0.5 else None


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
_FONT_SCAN = None                       # the scan system_fonts_soon() started, until done


def _system_fonts():
    """{normalized name: font file} for fonts installed on this computer (scanned once)."""
    global _SYSTEM_FONTS, _FONT_SCAN
    if _SYSTEM_FONTS is None:
        scan, _FONT_SCAN = _FONT_SCAN or _font_scan(), None
        found = None
        for found in scan:              # (finishes one already under way)
            pass
        if _SYSTEM_FONTS is None:
            _SYSTEM_FONTS = found
    return _SYSTEM_FONTS


def _fontconfig_dirs(conf="/etc/fonts/fonts.conf"):
    """The font folders fontconfig is told about in its main file (<dir> lines; a
    prefix="xdg" one is under each XDG data folder, ~ is the home folder)."""
    try:
        with open(conf, encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError:
        return []
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    home = os.path.expanduser("~")
    data_home = os.environ.get("XDG_DATA_HOME") or os.path.join(home, ".local", "share")
    out = []
    for attrs, d in re.findall(r"<dir\b([^>]*)>([^<]*)</dir>", text):
        d = d.strip()
        if not d:
            continue
        if re.search(r"prefix\s*=\s*[\"']xdg[\"']", attrs):
            out.append(os.path.join(data_home, d))
        elif d.startswith("~"):
            out.append(home + d[1:])
        elif os.path.isabs(d):
            out.append(d)
    return out


def font_dirs():
    """The folders installed fonts are in. Windows: the system's and this user's Fonts
    folders. Linux: the folders fontconfig uses (the ones in its fonts.conf, the user's
    ~/.local/share/fonts and ~/.fonts, /usr/share/fonts, /usr/local/share/fonts and the
    fonts folder of every XDG data folder), each once, none inside another. macOS: its
    system, shared and user Fonts folders."""
    if sys.platform == "darwin" and os.name != "nt":
        # macOS (the Apple silicon build, and run from source)
        return ["/System/Library/Fonts", "/Library/Fonts",
                os.path.expanduser("~/Library/Fonts")]
    if os.name == "nt":
        return [os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"),
                os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "Windows",
                             "Fonts"),
                "/usr/share/fonts", os.path.expanduser("~/.fonts"), "/Library/Fonts"]
    home = os.path.expanduser("~")
    data_home = os.environ.get("XDG_DATA_HOME") or os.path.join(home, ".local", "share")
    data_dirs = (os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share").split(":")
    found = ([os.path.join(data_home, "fonts"), os.path.join(home, ".fonts")]
             + _fontconfig_dirs()
             + [os.path.join(d, "fonts") for d in data_dirs if os.path.isabs(d)]
             + ["/usr/share/fonts", "/usr/local/share/fonts"])
    real, out = [], []
    for d in found:
        if not os.path.isdir(d):
            continue
        r = os.path.realpath(d)
        if any(r == k or r.startswith(k.rstrip(os.sep) + os.sep) for k in real):
            continue                    # (scanned already, as part of a folder above it)
        keep = [i for i, k in enumerate(real) if not k.startswith(r.rstrip(os.sep) + os.sep)]
        real, out = [real[i] for i in keep], [out[i] for i in keep]
        real.append(r)
        out.append(d)
    return out


def _font_files(d):
    """Font files (.ttf, .otf) under folder d. Windows: as its file names are written
    (Windows doesn't tell upper from lower case); elsewhere also FONT.TTF, Font.Otf... and
    TrueType collections (.ttc: many Linux fonts, Chinese, Japanese and Korean ones among
    them, come only as one; its first font is used)."""
    if os.name == "nt":
        return glob.glob(os.path.join(d, "**", "*.[to]tf"), recursive=True)
    out, seen = [], set()
    for root, dirs, files in os.walk(d, followlinks=True):
        real = os.path.realpath(root)
        if real in seen:                # (a link back up the tree: walked already)
            dirs[:] = []
            continue
        seen.add(real)
        dirs.sort()
        out += [os.path.join(root, f) for f in sorted(files)
                if f.lower().endswith((".ttf", ".otf", ".ttc"))]
    return out


def _font_scan(per_step=8):
    """Scan the fonts folders: a generator that yields None every per_step fonts and the
    finished {normalized name: font file} last."""
    out = {}
    dirs = font_dirs()
    count = 0
    for d in dirs:
        if not os.path.isdir(d):
            continue
        for f in _font_files(d):
            try:
                out.setdefault(_norm(pymupdf.Font(fontfile=f).name), f)
            except Exception:
                pass  # (a font file PyMuPDF can't read: left out)
            count += 1
            if count % per_step == 0:
                yield None
    yield out


def system_fonts_soon():
    """Scan the installed fonts in idle time, a few at a time (Windows has hundreds), so the
    first Edit text change doesn't wait for it. Call it once the window is up."""
    from PySide6.QtCore import QTimer
    global _FONT_SCAN
    if _SYSTEM_FONTS is not None or _FONT_SCAN is not None:
        return
    _FONT_SCAN = _font_scan()

    def step():
        global _SYSTEM_FONTS, _FONT_SCAN
        if _FONT_SCAN is None:
            return                      # (done, or finished by _system_fonts)
        try:
            found = next(_FONT_SCAN)
        except Exception:
            _FONT_SCAN = None
            return
        if found is None:
            QTimer.singleShot(0, step)
            return
        _FONT_SCAN = None
        if _SYSTEM_FONTS is None:
            _SYSTEM_FONTS = found
    QTimer.singleShot(0, step)


_SUBSET = re.compile(r"^[A-Z]{6}\+")


def _insert_font(page, name, **source):
    """page.insert_font, but a name already on the page for a font cut down to the glyphs
    used (Save keeps only those, and so do other programs) gets a fresh name: PyMuPDF
    reuses the font already there under that name, and new letters came out invisible.
    After a Save cut the document's fonts down (font_salt, set by the view), the font's
    bytes get a few zero bytes added: MuPDF otherwise finds the same font file it embedded
    before and hands back the cut-down copy, whatever the name. Returns the name to write
    with."""
    taken = {f[4]: f[3] for f in page.get_fonts()}
    if name in taken and not _SUBSET.match(taken[name] or ""):
        page.insert_font(fontname=name, **source)      # (already here, whole)
        return name
    if name in taken:
        k = 2
        while "%s_%d" % (name, k) in taken:
            k += 1
        name = "%s_%d" % (name, k)
    salt = getattr(page.parent, "font_salt", 0)
    if salt:
        if "fontfile" in source:
            with open(source["fontfile"], "rb") as f:
                buf = f.read()
        else:
            buf = source["fontbuffer"]
        source = {"fontbuffer": bytes(buf) + b"\0" * salt}
    page.insert_font(fontname=name, **source)
    return name


# the standard fonts every PDF reader has built in, as _norm() writes their names
_STANDARD_FONTS = {f + s for f in ("helvetica", "courier") for s in
                   ("", "bold", "oblique", "boldoblique")} | \
    {"times", "timesbold", "timesitalic", "timesbolditalic"}


def _system_font(page, span, text):
    """Use the installed copy of the span's font (like Acrobat does) if it has every glyph."""
    if sys.platform == "darwin" and _norm(span["font"]) in _STANDARD_FONTS \
            and _winansi_ok(text):
        # (macOS has Helvetica, Times and Courier installed: a PDF's standard font is
        # written with the built-in one there too, as on Windows and Linux, which have none)
        return None
    path = _system_fonts().get(_norm(span["font"]))
    if not path:
        return None
    try:
        font = pymupdf.Font(fontfile=path)
        if not all(font.has_glyph(ord(c)) for c in text if c not in "\n\r"):
            return None
        name = _insert_font(page, "KZS" + _norm(span["font"])[:20], fontfile=path)
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
            name = _insert_font(page, "KZUni", fontbuffer=font.buffer)
            return name, font, {"fontbuffer": font.buffer}
    except Exception:
        pass  # (no CJK font here: the next font is tried)
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
                name = _insert_font(page, "KZB" + key[:20], fontfile=path)
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
    if os.name != "nt" and not any(k in fonts for k in keys):
        # Linux: a name fontconfig stands in for ("Sans Serif", "Monospace"...) is written
        # with the font it stands for
        real = _fontconfig_family(family)
        if real and _norm(real) != base:
            return chosen_font(page, real, bold, italic, text)
    for key in keys:
        path = fonts.get(key)
        if not path:
            continue
        try:
            font = pymupdf.Font(fontfile=path)
            if not all(font.has_glyph(ord(c)) for c in text if c not in "\n\r"):
                return None
            name = _insert_font(page, "KZF" + key[:20], fontfile=path)
            return name, font, {"fontfile": path}
        except Exception:
            continue
    return None


def _fontconfig_family(family):
    """The installed family a font name resolves to on screen (Linux: "Sans Serif" is
    "DejaVu Sans" on many systems), or None."""
    try:
        from PySide6.QtGui import QFont, QFontInfo, QGuiApplication
        if QGuiApplication.instance() is None:
            return None
        return QFontInfo(QFont(family)).family() or None
    except Exception:
        return None


def add_text(page, origin, text, family="", bold=False, italic=False, size=12.0,
             color=(0, 0, 0), wrap_width=None, runs=None, mark=True):
    """Add text: write text into the page itself (not an annotation) with its first baseline
    at origin (unrotated page coordinates), reading upright as the page is displayed.
    family "" = Helvetica, which every PDF reader has built in. runs: [(text,
    text_styles.Style)] making up text, when some words have a style of their own (bold,
    color, underline...). mark: remembered as one block (added_text: Edit text opens all
    of it, wrapped as it was). Returns the font name used. Raises ValueError (before
    changing anything) if no font can write the text."""
    from . import added_text
    with added_text.marking(page) as mk:
        name, rows, step = _add_text(page, origin, text, family, bold, italic, size, color,
                                     wrap_width, runs)
        if mark:
            mk["props"] = added_text.props_of(origin, page.rotation, wrap_width, step, rows)
    return name


def _add_text(page, origin, text, family, bold, italic, size, color, wrap_width, runs):
    """add_text's writing: (font name, the lines written as text_styles.write_lines gives
    them, baseline to baseline)."""
    if any(ord(c) > 0xFFFF for c in text):
        raise ValueError(tr("Emoji and other characters beyond U+FFFF can't be written into "
                            "a PDF page here. Remove them and try again."))
    refuse_right_to_left(text)
    if runs is not None:
        from . import text_styles
        rtext, keys = text_styles.keys_of(runs)
        base = text_styles.add_style(family, bold, italic, size, color)
        if rtext == text and keys and any(k != base for k in keys):
            fonts, text, keys = text_styles.resolve_all(page, text, keys)
            fonts = text_styles.reinsert(page, fonts)
            main = text_styles.main_style(text, keys)
            rows = text_styles.write_lines(page, origin, page.rotation, list(zip(text, keys)),
                                           fonts, 1.2 * main.size, wrap_width)
            return text_styles.used_name(fonts, main), rows, 1.2 * main.size
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
        fontname, font, source = found      # (already on the page: chosen_font inserted it)
    else:
        fontname = _BASE14_STYLE[(bool(bold), bool(italic))]
        font = pymupdf.Font(fontname)
    rows = []
    for para in text.split("\n"):
        part = _wrap(para, font, size, wrap_width) if wrap_width else [para]
        rows += [(r, i == 0, i == len(part) - 1) for i, r in enumerate(part)]
    page.insert_text(pymupdf.Point(origin), "\n".join(r[0] for r in rows), fontsize=size,
                     fontname=fontname, color=color, rotate=page.rotation, lineheight=1.2)
    if found:
        _fix_spaces(page, fontname, font)
    step = 1.2 * float(size)
    return fontname, [(k * step, first, last) for k, (_r, first, last) in enumerate(rows)], step


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
            name = _insert_font(page, name, **source)
            return (name, font, source), None
    except Exception:
        pass  # (a font PyMuPDF can't load: the next one is tried)
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
    if min(abs(dx), abs(dy)) > 0.01:
        # (text at an angle: its letters' boxes are level boxes around turned letters, and
        # a level band through the line's middle missed its ends: small squares along its
        # middle instead, one every quarter of its size. 1.12)
        nx, ny = -dy, dx                # "down", across the text
        for s in line["spans"]:
            if not s["text"].strip():
                continue
            size = float(s["size"])
            ox, oy = s["origin"]
            r = pymupdf.Rect(s["bbox"])
            along = [(p.x - ox) * dx + (p.y - oy) * dy for p in (r.tl, r.tr, r.bl, r.br)]
            a, a1 = max(min(along), 0.0), max(along)
            half, step = max(0.5, 0.1 * size), max(0.5, 0.25 * size)
            while a <= a1:
                cx = ox + dx * a - nx * 0.3 * size
                cy = oy + dy * a - ny * 0.3 * size
                out.append(pymupdf.Rect(cx - half, cy - half, cx + half, cy + half))
                a += step
        return out
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


def _span_key(s):
    return (round(s["origin"][0], 1), round(s["origin"][1], 1), s["text"])


def _others_of(page, lines):
    """The page's text lines without the spans of these lines: a justified line's words, a
    piece set apart, can be grouped into lines another way than these were (what's left of a
    line is a line of its own)."""
    mine = {_span_key(s) for ln in lines for s in ln["spans"]}
    out = []
    for _r, ln in text_lines(page):
        rest = [s for s in ln["spans"] if _span_key(s) not in mine]
        if not rest or not any(s["text"].strip() for s in rest):
            continue
        if len(rest) != len(ln["spans"]):
            box = pymupdf.Rect()
            for s in rest:
                box |= pymupdf.Rect(s["bbox"])
            ln = {"bbox": box, "dir": ln["dir"], "spans": rest}
        out.append(ln)
    return out


def touched_lines(page, lines):
    """The page's other text lines whose letters the removal bands of these lines reach (and
    theirs in turn): a line lying over another one (moved onto it with the arrow keys, an
    overprinted label) would take that one's letters with it. Only lines near the bands are
    looked at (a grid of the page's spans)."""
    bands = [r for ln in lines for r in removal_bands(ln)]
    if not bands:
        return []
    cell = 48.0
    others = _others_of(page, lines)
    grid = {}
    for k, ln in enumerate(others):
        for sp in ln["spans"]:
            if not sp["text"].strip():
                continue
            b = pymupdf.Rect(sp["bbox"])
            for i in range(int(b.x0 // cell), int(b.x1 // cell) + 1):
                for j in range(int(b.y0 // cell), int(b.y1 // cell) + 1):
                    grid.setdefault((i, j), set()).add(k)
    found = set()
    todo = list(bands)
    while todo:
        r = todo.pop()
        near = set()
        for i in range(int(r.x0 // cell), int(r.x1 // cell) + 1):
            for j in range(int(r.y0 // cell), int(r.y1 // cell) + 1):
                near |= grid.get((i, j), set())
        for k in near - found:
            if any(pymupdf.Rect(sp["bbox"]).intersects(r) for sp in others[k]["spans"]
                   if sp["text"].strip()):
                found.add(k)
                todo += removal_bands(others[k])
    return [others[k] for k in sorted(found)]


def _remove_lines(page, lines, keep_links=True, decor=()):
    """Take the lines' letters out of the page. Applying a redaction also drops every link
    it touches: keep_links puts those back (editing or moving linked words keeps the link,
    a drawing set's sheet hyperlinks included). decor: the boxes of the lines' underlines
    and strikethrough lines (text_styles.read_*), taken out too: only a drawing lying
    wholly inside one of them goes (a table border running on stays).

    Another line the removal would reach (one these lie over) is taken out with them and
    written again where it was, as it was (the owner, 11 Nov: text moved with the arrow keys
    onto another line took that line's letters away on the next press)."""
    others = touched_lines(page, lines)
    kept = _plan_lines(page, others) if others else None   # (fonts found before anything goes)
    if kept is not None:
        lines = list(lines) + others
        decor = list(decor) + kept[2]
    doc = page.parent
    saved = []
    for xref, kind, *_ in page.annot_xrefs():
        # links, and text boxes (applying a redaction takes away a text box it touches, one
        # lying over the moved or edited words, too)
        if (kind == pymupdf.PDF_ANNOT_LINK and keep_links) or kind == pymupdf.PDF_ANNOT_FREE_TEXT:
            saved.append((xref, doc.xref_object(xref, compressed=True)))
    for line in lines:
        for r in removal_bands(line):
            page.add_redact_annot(r, fill=False)
    page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE,
                          graphics=pymupdf.PDF_REDACT_LINE_ART_NONE,
                          text=pymupdf.PDF_REDACT_TEXT_REMOVE)
    if decor:
        for r in decor:
            page.add_redact_annot(pymupdf.Rect(r) + (-0.5, -0.5, 0.5, 0.5), fill=False)
        page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE,
                              graphics=pymupdf.PDF_REDACT_LINE_ART_REMOVE_IF_COVERED,
                              text=pymupdf.PDF_REDACT_TEXT_NONE)
    if kept is not None:
        _write_lines(page, kept[0], kept[1], (0, 0))
    from . import added_text
    added_text.prune(page)              # (a block whose letters all went is no block)
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
            try:                        # (the open page lists the ones put back, too)
                m = pymupdf.mupdf
                m.pdf_sync_open_pages(m.pdf_document_from_fz_document(doc.this))
            except Exception:
                pass  # (MuPDF can't refresh this now: what it has loaded stays as it is)


def delete_lines(page, lines, keep_links=False):
    """Take these lines of text out of the page; pictures and line art stay. Links on them
    go too, unless keep_links."""
    refuse_with_marks(page, deleting=True)
    _remove_lines(page, lines, keep_links)


def refuse_with_marks(page, deleting=False):
    """Raise ValueError when page has redaction marks not applied yet: taking text out of a
    page applies every redaction mark on it, pending ones included. An edit that also changes
    other things checks this before changing anything (an edit refused after a change is
    taken back, but MuPDF has dropped the steps to redo by then)."""
    from .annotations import each_annot
    if any(a.type[0] == pymupdf.PDF_ANNOT_REDACT for a in each_annot(page)):
        if deleting:
            raise ValueError(tr("Apply or remove the redaction marks on this page before "
                                "deleting its text."))
        raise ValueError(tr("Apply or remove the redaction marks on this page before "
                            "editing its text."))


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


def _styled_text(runs, text, main, font, size, strip=True):
    """The letters' styles of runs ([(text, text_styles.Style)], the text before strip())
    for text, or None when they're all in the paragraph's own style (written as before).
    font / size picked in Properties apply to every run (a size scales them all)."""
    from . import text_styles
    rtext, keys = text_styles.keys_of(runs)
    if strip:
        a = len(rtext) - len(rtext.lstrip())
        b = len(rtext.rstrip())
        rtext, keys = rtext[a:b], keys[a:b]
    if rtext != text or not keys or text_styles.plain(keys, text_styles.span_style(main)):
        return None
    if size:
        ratio = float(size) / float(main["size"])
        keys = [k._replace(size=round(k.size * ratio, 2)) for k in keys]
    if font and font[0]:
        keys = [k._replace(bold=k.bold or bool(font[1]), italic=k.italic or bool(font[2]))
                for k in keys]
    return keys


def replace_paragraph(page, lines, new_text, wrap_width=None, font=None, size=None,
                      offset=(0, 0), runs=None, decor=()):
    """Rewrite a whole paragraph (horizontal lines, reading order) with new_text, wrapped to
    its width (or wrap_width) in its font, size, color, line spacing and alignment. font /
    size: a font or size picked in Properties instead. offset: move it (points). runs:
    [(text, text_styles.Style)] making up new_text: each word in its own style (bold,
    italic, color, size, underline...); decor: the old text's underline boxes, taken out
    with it (text_styles.read_paragraph). Returns (font name, its new box, the baselines
    written). Raises ValueError (before changing anything) if no font can write it."""
    main = paragraph_layout(lines)["span"]
    text = new_text.strip()
    refuse_right_to_left(paragraph_text(lines), text)
    found = None
    keys = _styled_text(runs, text, main, font, size) if runs is not None and text else None
    if keys is not None:
        from . import text_styles
        fonts, text, keys = text_styles.resolve_all(
            page, text, keys, family=font[0] if font and font[0] else None)
    if keys is None and text and font and font[0]:
        found = chosen_font(page, font[0], font[1], font[2], text)
    if keys is None and text and found is None:
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
    _remove_lines(page, lines, decor=decor)
    if not text:
        return None, pymupdf.Rect(), []
    if keys is not None:
        return _write_styled_paragraph(page, lay, text, keys, fonts, wrap_width, offset,
                                       step, size)
    if found:
        fontname, fnt, source = found
        fontname = _insert_font(page, fontname, **source)
    else:
        fontname = _base14(main)
        fnt = pymupdf.Font(fontname)
    width = wrap_width or lay["width"]
    fit = _fit_width(width, wrap_width, size)
    indent = lay["first_left"] - lay["left"]         # the first line's own start
    rows = []
    for part in text.split("\n"):                    # Shift+Enter: a new paragraph
        wrapped = _wrap_indented(part, fnt, size, fit, indent)
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


def _fit_width(width, wrap_width, size):
    """The width a paragraph's words are wrapped to. Its own width (wrap_width None) is
    that of its longest line as the page measures it, in the PDF's glyph widths (often
    rounded, in thousandths of the size); the font measures the same words a little wider,
    so that line, written again, didn't fit any more: every edit pushed a word down and the
    paragraph got narrower and longer with each one. A little room keeps the lines as they
    were (less than a space and the shortest word: a word that didn't fit still doesn't)."""
    return width if wrap_width else width + 0.12 * float(size)


def _write_styled_paragraph(page, lay, text, keys, fonts, wrap_width, offset, step, size):
    """replace_paragraph's writing, each run in its own style (text_styles)."""
    from . import text_styles
    fonts = text_styles.reinsert(page, fonts)
    main = text_styles.main_style(text, keys)
    width = wrap_width or lay["width"]
    indent = lay["first_left"] - lay["left"]
    rows = text_styles.wrap(list(zip(text, keys)), fonts, _fit_width(width, wrap_width, size),
                            indent)
    left, right = lay["left"] + offset[0], lay["left"] + offset[0] + width
    y = lay["first"] + offset[1]
    top = y - max(k.size for k in keys)
    bases = []
    shape = page.new_shape()
    prev = None
    for row, first, last in rows:
        row = text_styles.strip_row(row)
        cur = text_styles.row_size(row, size)
        if prev is not None:
            # (farther apart where words in larger letters need the room)
            y += text_styles.advance(step, size, prev, cur)
        prev = cur
        bases.append(y)
        start = left + indent if first else left
        spread = None
        if lay["align"] == "justify" and not last and \
                sum(1 for c, _k in row if c == " ") > 0:
            spread = right - start
        ps = text_styles.pieces(row, fonts, spread)
        length = ps[-1][3] if ps else 0.0
        x = start if spread is not None else {
            "right": right - length, "center": (left + right - length) / 2}.get(
                lay["align"], start)
        text_styles.write_row(shape, pymupdf.Point(x, y), 0, ps, fonts)
    shape.commit(True)
    text_styles.fix_spaces(page, fonts)
    tail = max(k.size for k in keys) * 0.25
    box = pymupdf.Rect(min(left, left + indent), top, right, y + tail)
    return text_styles.used_name(fonts, main), box, bases


def move_lines(page, lines, offset, blocks=()):
    """Move these lines of the page's text by offset (points), each in its own font, size and
    color, as replace_line(page, line, its own text, offset, scan=None) does one by one, but
    with one redaction for all of them: one at a time, a drawing's 400 labels took most of a
    minute. blocks: the marked blocks (added_text.Block) among them: each stays one block,
    marked where it now is. Returns the font names written with. Raises ValueError (before
    changing anything) if a line can't be written."""
    refuse_with_marks(page)
    plans, styled, decor = _plan_lines(page, lines)     # 1) the fonts first
    _remove_lines(page, lines, decor=decor)     # 2) all their letters out at once
    return _write_lines(page, plans, styled, offset, blocks)    # 3) each written again


def recolor_lines(page, lines, rgb, blocks=()):
    """Write these lines of the page's text again where they are, every word in color rgb
    ((r, g, b) from 0 to 1), each keeping its font, size, bold, italic and underline (Edit
    objects > Text color...). One redaction for all of them, as move_lines; blocks: the
    marked blocks (added_text) among them, each kept one block. Returns the font names
    written with. Raises ValueError (before changing anything) if a line can't be written."""
    refuse_with_marks(page)
    plans, styled, decor = _plan_lines(page, lines, rgb)
    _remove_lines(page, lines, decor=decor)
    return _write_lines(page, plans, styled, pymupdf.Point(0, 0), blocks)


def _plan_lines(page, lines, color=None):
    """How each line is written again (its font found before anything changes: nothing goes
    if one can't be written): (plans, styled, decor) for _write_lines. color: (r, g, b) for
    every word instead of its own."""
    from . import text_styles
    srgb = text_styles.to_int(color) if color is not None else None
    plans = []
    styled, decor = [], []
    for line in lines:                  # 1) the fonts first: nothing goes if one can't write
        text = line_text(line)
        if not text.strip():
            continue
        refuse_right_to_left(text)
        if mixed_styles(line):
            # words in styles of their own (bold, colors, invisible words): each kept, as
            # dragging the line with Edit text does (written in the line's main style, a
            # hidden word showed)
            st = text_styles.read_line(page, line)
            if srgb is not None:
                st = st._replace(keys=[k._replace(color=srgb) for k in st.keys])
            fonts, t, keys = text_styles.resolve_all(page, st.text, st.keys)
            styled.append((line, t, keys, fonts))
            decor += st.decor
            continue
        main = main_span(line)
        if srgb is not None:
            main = dict(main, color=srgb)
        found, text = _font_for(page, main, text)
        plans.append((line, text, main, found))
    return plans, styled, decor


def _write_lines(page, plans, styled, offset, blocks=()):
    """Write the lines planned (_plan_lines) again, moved by offset; returns the font names
    written with."""
    inserted = {}                       # font name -> (name written with, Font)
    used = []
    # one drawing for all of them, added to the page once (page.insert_text adds each
    # line on its own, reading the whole page each time: most of the time on a big sheet);
    # one for each marked block, which is marked again where it now is
    shape = page.new_shape()
    owner = {id(ln): k for k, b in enumerate(blocks) for _r, ln in b.lines}
    shapes = {}

    def shape_for(line):
        k = owner.get(id(line))
        if k is None:
            shapes.setdefault(None, shape)
            return shape
        if k not in shapes:
            shapes[k] = page.new_shape()
        return shapes[k]
    for line, text, keys, fonts in styled:
        from . import text_styles
        fonts = text_styles.reinsert(page, fonts)
        origin = pymupdf.Point(line["spans"][0]["origin"]) + offset
        angle = off_quarter(line)
        text_styles.write_row(shape_for(line), origin,
                              line_rotation(line) if angle is None else angle,
                              text_styles.pieces(list(zip(text, keys)), fonts), fonts)
        inserted.update({f.name: (f.name, f.font) for f in fonts.values()
                         if f.source is not None})
        used.append(text_styles.used_name(fonts, text_styles.main_style(text, keys)))
    for line, text, main, found in plans:   # 3) each written again, moved
        if found:
            fontname, font, source = found
            if fontname not in inserted:
                # (applying the redaction drops fonts no text uses yet: add it again)
                inserted[fontname] = (_insert_font(page, fontname, **source), font)
            name = inserted[fontname][0]
        else:
            name = _base14(main)
        origin = pymupdf.Point(line["spans"][0]["origin"]) + offset
        angle = off_quarter(line)
        if angle is not None:
            # (at its own angle, a diagonal watermark: insert_text turns only by quarters;
            # moved, it came out level. Random battery, seed 1112, 1.12)
            shape_for(line).insert_text(origin, text, fontsize=float(main["size"]),
                                        fontname=name, color=_rgb(main["color"]),
                                        morph=(origin, pymupdf.Matrix(angle)), lineheight=1.2)
        else:
            shape_for(line).insert_text(origin, text, fontsize=float(main["size"]),
                                        fontname=name, color=_rgb(main["color"]),
                                        rotate=line_rotation(line), lineheight=1.2)
        used.append(name)
    from . import added_text
    for k, sh in shapes.items():
        if k is None:
            sh.commit(True)
            continue
        with added_text.marking(page) as mk:
            sh.commit(True)
            p = dict(blocks[k].props)
            p["origin"] = pymupdf.Point(p["origin"]) + offset
            mk["props"] = p
    for name, font in inserted.values():
        _fix_spaces(page, name, font)
    return used


def mixed_styles(line):
    """True when a line's words aren't all in one style (font, size, color, bold, italic),
    or some are invisible or see-through: written again in the line's main style, they
    would lose theirs (and a hidden word would show)."""
    seen = set()
    for s in line["spans"]:
        if not s["text"].strip():
            continue
        alpha = s.get("alpha", 255)
        if alpha != 255:
            return True
        seen.add((s["font"], round(s["size"], 1), s["color"], s["flags"] & (_ITALIC | _BOLD)))
    return len(seen) > 1


def replace_line(page, line, new_text, offset=(0, 0), wrap_width=None, font=None, size=None,
                 scan="auto", info=None, runs=None, decor=()):
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
    runs: [(text, text_styles.Style)] making up new_text, each word in its own style;
    decor: the line's underline boxes, taken out with it (text_styles.read_line).
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
    refuse_right_to_left(line_text(line), new_text)

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
    keys = None
    if runs is None and not scan and new_text.strip() and mixed_styles(line):
        # (Replace text: the words kept keep their styles, a hidden word stays hidden)
        from . import text_styles
        styled = text_styles.read_line(page, line)
        runs = text_styles.runs_of(new_text, text_styles.restyle(
            styled.text, styled.keys, new_text, styled.main))
        decor = styled.decor
    if runs is not None and not scan and new_text.strip():
        keys = _styled_text(runs, new_text, main, font, size, strip=False)
    if keys is not None:
        from . import text_styles
        fonts, new_text, keys = text_styles.resolve_all(
            page, new_text, keys, family=font[0] if font and font[0] else None)
    elif new_text.strip() and font and font[0]:
        found = chosen_font(page, font[0], font[1], font[2], new_text)
    if keys is None and new_text.strip() and found is None and scan:
        found, builtin = _scan_font(page, scan, new_text)
    if keys is None and new_text.strip() and found is None and builtin is None:
        found, new_text = _font_for(page, main, new_text)

    # 2) remove only the text of this line (keep line art and images)
    _remove_lines(page, [line], decor=() if scan else decor)
    if scan:
        # the old letters in the scan's picture: covered with the paper color
        for r in cover:
            if not r.is_empty:
                page.draw_rect(r, color=None, fill=scan["paper"], width=0, overlay=True)

    if not new_text.strip():
        return None
    # 3) write the replacement at the same baseline / direction
    if keys is not None:
        from . import text_styles
        fonts = text_styles.reinsert(page, fonts)
        step = 1.2 * float(size or main["size"])
        text_styles.write_lines(page, pymupdf.Point(first["origin"]) + offset,
                                line_rotation(line), list(zip(new_text, keys)), fonts, step,
                                wrap_width)
        return text_styles.used_name(fonts, text_styles.main_style(new_text, keys))
    if found:
        fontname, font, source = found
        # applying the redaction drops fonts no text uses yet, including the one just
        # chosen: add it again (without this, writing failed: "need font file or buffer")
        fontname = _insert_font(page, fontname, **source)
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
