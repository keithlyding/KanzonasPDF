"""Styled words for Edit text and Add text: each word keeps its own font, size, color, bold,
italic, underline and strikethrough through an edit and the paragraph's reflow.

Reading (read_paragraph, read_line): the page's text is read once more around the words
edited, with MuPDF noting how each letter is drawn: filled and outlined at once (render
mode 2: a bold made by thickening the letters), leaning (a sheared text matrix: an italic
made by slanting them), and the thin lines drawn near the text. Each letter gets a Style.
A thin straight line just under a run of letters, or through the middle of their x-height,
running from the run's first letter to its last (as Word's PDF export writes underlines),
is taken as that run's underline or strikethrough; anything longer than the text, thicker,
farther off or under spaces only (a table border, a title block's rule, a form's blank) is
left alone.

Writing (wrap, pieces, write_row, write_lines; text_edit's replace_paragraph,
replace_line and add_text use them): the words wrap across runs, each run in its own font,
size and color. Bold and italic keep the line's font: the same family's real bold or
italic when the PDF has it embedded or it's installed; otherwise the very same font is
thickened (render mode 2, a stroke about 3% of the size in the text's color) or slanted
(a shear of about 12 degrees). Only text the font can't write at all goes to another font,
as before. Underline and strikethrough are drawn as thin filled bars in the run's color,
one per line piece, turned with sideways text.
"""

import difflib
import math
import re
import struct
from typing import NamedTuple

import pymupdf

from . import text_edit as te
from .i18n import tr

SHEAR = 0.21                    # tan(~12 degrees): a slanted (synthetic) italic
STROKE = 0.03                   # a thickened (synthetic) bold's stroke, x font size
_FILLED, _STROKED = 16, 32      # MuPDF's letter flags (FZ_STEXT_FILLED, FZ_STEXT_STROKED)
_FLAGS = ((pymupdf.TEXTFLAGS_DICT & ~pymupdf.TEXT_PRESERVE_IMAGES) |
          pymupdf.TEXT_COLLECT_STYLES | pymupdf.TEXT_COLLECT_VECTORS)
_KEEP_FLAGS = 2 | 4 | 8 | 16    # italic, serif, mono, bold (not superscript)


class Style(NamedTuple):
    """How a letter looks. font: the PDF font of the text it came from (its name, as the
    page's text gives it); family: a family picked for Add text or in Properties."""
    font: str = ""
    flags: int = 0
    size: float = 12.0
    color: int = 0                  # sRGB
    bold: bool = False
    italic: bool = False
    underline: bool = False
    strike: bool = False
    family: str = ""
    alt: int = 0                    # (1: runs its font can't write, given another one)


_BOLD_WORDS = re.compile(r"bold|black|heavy|demi|semibold", re.I)
_ITALIC_WORDS = re.compile(r"italic|oblique|slanted|kursiv", re.I)


def natural(font, flags=0):
    """(bold, italic) of the font itself, from its name (and the PDF's font flags)."""
    name = (font or "").split("+", 1)[-1]
    return (bool(flags & 16) or bool(_BOLD_WORDS.search(name)),
            bool(flags & 2) or bool(_ITALIC_WORDS.search(name)))


def span_style(span, bold=False, italic=False):
    """The Style of a span from the page's text (bold / italic: drawn so, thickened or
    slanted)."""
    flags = int(span.get("flags", 0)) & _KEEP_FLAGS
    font = _SUBSET.sub("", span.get("font", ""))    # (two subsets of a font are one font)
    nb, ni = natural(font, flags)
    return Style(font, flags, round(float(span["size"]), 2),
                 int(span.get("color", 0)), nb or bold, ni or italic)


_SUBSET = re.compile(r"^[A-Z]{6}\+")


def _even_sizes(keys, size):
    """Sizes within 1% of the paragraph's (10.98 for 11) are its size."""
    size = round(float(size), 2)
    return [k._replace(size=size) if k.size != size and abs(k.size - size) <= 0.01 * size
            else k for k in keys]


def to_int(rgb):
    """(r, g, b) 0..1 -> sRGB integer."""
    r, g, b = (max(0, min(255, int(round(float(c) * 255))))
               for c in (tuple(rgb) + (0, 0, 0))[:3])
    return (r << 16) | (g << 8) | b


def add_style(family="", bold=False, italic=False, size=12.0, color=(0, 0, 0)):
    """The Style of new text written with Add text's settings."""
    return Style("", 0, round(float(size), 2), to_int(color), bool(bold), bool(italic),
                 False, False, family or "")


class Styled(NamedTuple):
    """Text as read from the page: its letters' styles (one per character of text), the
    boxes of the underlines and strikethrough lines drawn for it, its main style."""
    text: str
    keys: list
    decor: list
    main: Style


def runs_of(text, keys):
    """[(text, Style)] of consecutive letters in the same style."""
    out = []
    for c, k in zip(text, keys):
        if out and out[-1][1] == k:
            out[-1][0].append(c)
        else:
            out.append(([c], k))
    return [("".join(t), k) for t, k in out]


def keys_of(runs):
    """(text, one Style per character) of [(text, Style)]."""
    text = "".join(t for t, _k in runs)
    keys = [k for t, k in runs for _c in t]
    return text, keys


def main_style(text, keys, default=None):
    """The style most of the letters have (spaces don't count)."""
    count = {}
    for c, k in zip(text, keys):
        if not c.isspace():
            count[k] = count.get(k, 0) + 1
    if not count:
        return default if default is not None else (keys[0] if keys else Style())
    return max(count, key=count.get)


def restyle(old_text, old_keys, new_text, default):
    """Styles for new_text, an edit of old_text whose letters had old_keys: letters kept
    keep theirs; letters typed over others take the style of the first one typed over
    (a bold word changed stays bold); typed letters take the style of the letter before them
    (the one after, at the start); a text typed from nothing takes default."""
    if not old_keys:
        return [default] * len(new_text)
    out = [None] * len(new_text)
    sm = difflib.SequenceMatcher(None, old_text, new_text, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            out[j1:j2] = old_keys[i1:i2]
        elif tag == "replace" and i2 - i1 == j2 - j1:
            out[j1:j2] = old_keys[i1:i2]          # (letters typed over, one for one)
        elif tag == "replace":
            out[j1:j2] = [old_keys[i1]] * (j2 - j1)
    for j in range(len(out)):
        if out[j] is None:
            if j > 0:
                out[j] = out[j - 1]
            else:
                nxt = next((k for k in out if k is not None), None)
                out[j] = nxt if nxt is not None else old_keys[0]
    return out


def restyled(styled, runs):
    """True when runs (what was typed, [(text, Style)]) style the words of styled (as read
    from the page) differently."""
    if runs is None:
        return False
    text, keys = keys_of(runs)
    now = [k for c, k in zip(text, keys) if not c.isspace()]
    was = [k for c, k in zip(styled.text, styled.keys) if not c.isspace()]
    return now != was


def plain(keys, main):
    """True when every letter is in the main style, as the font draws it (no letter made
    bold or italic another way, none underlined or struck through): the text can be
    written as before, in one style."""
    nb, ni = natural(main.font, main.flags)
    if main.underline or main.strike or main.bold != nb or main.italic != ni:
        return False
    return all(k == main for k in keys)


# ---- reading ------------------------------------------------------------------------
def _area(lines):
    box = pymupdf.Rect()
    for ln in lines:
        box |= pymupdf.Rect(ln["bbox"])
    size = max(s["size"] for ln in lines for s in ln["spans"])
    return box + (-size, -size, size, size)


def _read_area(page, area):
    """The letters around area as MuPDF reads them with their drawing styles, and the thin
    straight drawings nearby: ({(char, x, y): (row, index)} by each letter's origin, where
    row is the letters on that baseline in order along it, each [char, flags, shear, a0,
    a1]; the drawings). (MuPDF splits a line where its letters' style changes: the letters
    are put in order along their baseline again.)"""
    tp, flags = te.page_textpage(page, _FLAGS, clip=area)
    rows = {}
    for b in tp.this:
        if b.m_internal.type != 0:
            continue
        for ln in b:
            d = ln.m_internal.dir
            dx, dy = d.x, d.y
            for ch in ln:
                c = ch.m_internal
                q = c.quad
                vx, vy = q.ul.x - q.ll.x, q.ul.y - q.ll.y
                h = math.hypot(vx, vy) or 1.0
                a0 = q.ll.x * dx + q.ll.y * dy
                a1 = q.lr.x * dx + q.lr.y * dy
                try:
                    char = chr(c.c)
                except (ValueError, OverflowError):
                    char = "\ufffd"
                ox, oy = c.origin.x, c.origin.y
                key = (round(dx, 2), round(dy, 2), round(oy * dx - ox * dy, 2))
                rows.setdefault(key, []).append(
                    [char, c.flags, (vx * dx + vy * dy) / h, min(a0, a1), max(a0, a1),
                     ox * dx + oy * dy, ox, oy])
    found = {}
    thick = []
    for row in rows.values():
        row.sort(key=lambda e: e[5])
        for i, e in enumerate(row):
            found.setdefault((e[0], round(e[6], 1), round(e[7], 1)), (row, i))
            if e[1] & _FILLED and e[1] & _STROKED:
                thick.append(e)
    if thick:
        # filled and outlined: thickened only when outlined in its own color with a real
        # stroke (not an outline effect, not a hairline)
        strokes = _strokes(page)
        for e in thick:
            got = strokes.get((e[0], round(e[6], 1), round(e[7], 1)))
            if got is None:
                e[1] &= ~_STROKED
            else:
                e.append(got)               # (stroke width, stroke color)
    d = page.get_text("dict", flags=flags, textpage=tp)
    vecs = [b for b in d["blocks"] if b.get("type") == 3 and b.get("isrect", True)
            and b.get("alpha", 255)]
    return found, vecs


def _strokes(page):
    """{(char, x, y): (stroke width, sRGB color)} of the letters the page outlines."""
    from contextlib import nullcontext
    from . import undo_journal
    turn = page.rotation
    # (PyMuPDF turns a rotated page upright to read it: not a change to keep)
    with undo_journal.detached(page.parent) if turn else nullcontext():
        trace = page.get_texttrace()
    out = {}
    for sp in trace:
        if sp.get("type") != 1 or not sp.get("linewidth"):
            continue
        col = tuple(sp.get("color") or (0,))
        if len(col) == 1:
            col = col * 3
        elif len(col) == 4:
            c, m, y, k = col
            col = ((1 - c) * (1 - k), (1 - m) * (1 - k), (1 - y) * (1 - k))
        for ch in sp.get("chars", ()):
            try:
                key = (chr(ch[0]), round(ch[2][0], 1), round(ch[2][1], 1))
            except (ValueError, OverflowError, TypeError, IndexError):
                continue
            out[key] = (float(sp["linewidth"]), to_int(col[:3]))
    return out


def _same_color(a, b):
    return all(abs(((a >> s) & 255) - ((b >> s) & 255)) <= 3 for s in (0, 8, 16))


def _span_entries(span, found):
    """Per character of the span: its [char, flags, shear, a0, a1, ...] as read, or None."""
    text = span["text"]
    out = [None] * len(text)
    if not text:
        return out
    o = span["origin"]
    hit = found.get((text[0], round(o[0], 1), round(o[1], 1)))
    if hit is None:
        return out
    row, i = hit
    for k, ch in enumerate(text):
        if i + k >= len(row) or row[i + k][0] != ch:
            break
        out[k] = row[i + k]
    return out


def _line_info(line, found):
    """[[char, Style, (a0, a1) or None]] for line_text(line), letter by letter."""
    out, prev = [], None
    for s in line["spans"]:
        if prev is not None:
            gap = te._along(pymupdf.Rect(s["bbox"]), line)[0] - \
                te._along(pymupdf.Rect(prev["bbox"]), line)[1]
            if gap > 0.15 * s["size"] and not (out and out[-1][0] == " ") and \
                    not s["text"].startswith(" "):
                out.append([" ", out[-1][1] if out else span_style(prev), None])
        entries = _span_entries(s, found) if found else [None] * len(s["text"])
        styles = {}
        for ch, e in zip(s["text"], entries):
            sb = bool(e and e[1] & _FILLED and e[1] & _STROKED and len(e) > 8 and
                      e[8][0] >= 0.01 * s["size"] and _same_color(e[8][1], s["color"]))
            si = bool(e and e[2] > 0.08)
            st = styles.get((sb, si))
            if st is None:
                st = styles[(sb, si)] = span_style(s, sb, si)
            out.append([ch, st, (e[3], e[4]) if e else None])
        prev = s
    return out


def _decorate(line, info, vecs, used):
    """Mark the letters of line (info: _line_info) that a thin line underlines or strikes
    through; returns the boxes of the lines taken."""
    dx, dy = line["dir"]
    nx, ny = -dy, dx                    # "down", across the text
    ox, oy = line["spans"][0]["origin"]
    base = ox * nx + oy * ny
    size = te.main_span(line)["size"]
    ext = [(i, e[2][0], e[2][1]) for i, e in enumerate(info) if e[2] is not None]
    ink = [x for x in ext if not info[x[0]][0].isspace()]
    if not ink:
        return []
    lo, hi = min(x[1] for x in ink), max(x[2] for x in ink)
    tol = max(0.75, 0.15 * size)
    out = []
    for vi, v in enumerate(vecs):
        if vi in used:
            continue
        r = pymupdf.Rect(v["bbox"])
        corners = (r.tl, r.tr, r.bl, r.br)
        along = [p.x * dx + p.y * dy for p in corners]
        across = [p.x * nx + p.y * ny - base for p in corners]
        v0, v1, c0, c1 = min(along), max(along), min(across), max(across)
        thick, length = c1 - c0, v1 - v0
        if thick > 0.2 * size + 0.6 or length < max(3 * thick, 0.25 * size):
            continue                    # not a thin line along the text
        mid = (c0 + c1) / 2
        if 0.02 * size <= mid <= 0.35 * size:
            kind = "underline"
        elif -0.5 * size <= mid <= -0.12 * size:
            kind = "strike"
        else:
            continue
        if v0 < lo - tol or v1 > hi + tol:
            continue                    # longer than the text: a border or a rule
        cov = [x for x in ext if v0 - 0.01 <= (x[1] + x[2]) / 2 <= v1 + 0.01]
        if not any(not info[i][0].isspace() for i, _a, _b in cov):
            continue                    # under spaces only: a form's blank
        if abs(min(x[1] for x in cov) - v0) > tol or abs(max(x[2] for x in cov) - v1) > tol:
            continue                    # doesn't start and end with the letters
        idx = {i for i, _a, _b in cov}
        lo_i, hi_i = min(idx), max(idx)
        for i in range(lo_i, hi_i + 1):         # (a space put between pieces too)
            if i in idx or info[i][2] is None:
                info[i][1] = info[i][1]._replace(**{kind: True})
        used.add(vi)
        out.append(r)
    return out


def _strip(info):
    a, b = 0, len(info)
    while a < b and info[a][0].isspace():
        a += 1
    while b > a and info[b - 1][0].isspace():
        b -= 1
    return info[a:b]


def _joint(before, after):
    """The style of a space put between two letters: the one before's, underlined or
    struck through only when both are."""
    return before._replace(underline=before.underline and after.underline,
                           strike=before.strike and after.strike)


def _uniform(text, span):
    st = span_style(span)
    return Styled(text, [st] * len(text), [], st)


def read_paragraph(page, lines):
    """Styled(text, keys, decor, main) of a paragraph's lines (text_edit.paragraph_at), its
    text exactly paragraph_text(lines)."""
    text = te.paragraph_text(lines)
    main_span = te.paragraph_layout(lines)["span"]
    try:
        found, vecs = _read_area(page, _area(lines))
        used, decor, out = set(), [], []
        for ln in lines:
            info = _line_info(ln, found)
            decor += _decorate(ln, info, vecs, used)
            t = _strip(info)
            if not t:
                continue
            if not out:
                out = [[c, k] for c, k, _e in t]
                continue
            if out[-1][0] == "­":
                out.pop()
            elif out[-1][0] == "-" and len(out) > 1 and out[-2][0].isalpha() and \
                    t[0][0].islower():
                if te._hyphen_joins("".join(c for c, _k in out).split(" ")[-1],
                                    "".join(c for c, _k, _e in t)):
                    out.pop()
            else:
                out.append([" ", _joint(out[-1][1], t[0][1])])
            out += [[c, k] for c, k, _e in t]
        if "".join(c for c, _k in out) != text:
            return _uniform(text, main_span)
        keys = _even_sizes([k for _c, k in out], main_span["size"])
        return Styled(text, keys, decor, main_style(text, keys, span_style(main_span)))
    except Exception:
        return _uniform(text, main_span)        # (never let reading styles stop an edit)


def read_line(page, line):
    """Styled(text, keys, decor, main) of one line, its text exactly line_text(line)."""
    text = te.line_text(line)
    try:
        found, vecs = _read_area(page, _area([line]))
        info = _line_info(line, found)
        decor = _decorate(line, info, vecs, set())
        if "".join(c for c, _k, _e in info) != text:
            return _uniform(text, te.main_span(line))
        keys = _even_sizes([k for _c, k, _e in info], te.main_span(line)["size"])
        return Styled(text, keys, decor,
                      main_style(text, keys, span_style(te.main_span(line))))
    except Exception:
        return _uniform(text, te.main_span(line))


# ---- fonts ----------------------------------------------------------------------------
class Font(NamedTuple):
    """A font a run is written in: its name on the page, the Font, how to insert it (None:
    a built-in PDF font), whether to thicken (bold) or slant (italic) it."""
    name: str
    font: object
    source: object
    bold: bool
    italic: bool


_STYLE_END = re.compile(r"(semibold|demibold|extrabold|ultrabold|bold|black|heavy)?"
                        r"(italic|oblique)?$")


def family_key(name):
    """'ABCDEF+Arial-BoldItalicMT' -> 'arial' (normalized as text_edit._norm, the style
    words at its end taken off)."""
    n = te._norm(name or "")
    fam = _STYLE_END.sub("", n)
    return fam or n


def _style_keys(fam, bold, italic):
    if bold and italic:
        return [fam + "bolditalic", fam + "boldoblique"]
    if bold:
        return [fam + "bold"]
    if italic:
        return [fam + "italic", fam + "oblique"]
    return [fam]


def _writes(font, text):
    return all(font.has_glyph(ord(c)) for c in text if c not in "\n\r")


def _variant(page, fontname, bold, italic, text):
    """The same family's real bold / italic / regular as asked, embedded in the PDF (this
    page first) or installed, when it has every character of text: (name, Font, source)."""
    keys = _style_keys(family_key(fontname), bold, italic)
    if te._norm(fontname) in keys:
        return None                     # (that's the font itself)
    doc = page.parent
    pages = [page.number] + [i for i in range(min(doc.page_count, 200)) if i != page.number]
    seen = set()
    for pno in pages:
        try:
            fonts = doc.get_page_fonts(pno, full=True)
        except Exception:
            continue
        for xref, ext, _type, basefont, *_ in fonts:
            if xref in seen or ext in ("n/a", "") or te._norm(basefont) not in keys:
                continue
            seen.add(xref)
            try:
                _n, _e, _t, buf = doc.extract_font(xref)
                if not buf:
                    continue
                font = pymupdf.Font(fontbuffer=buf)
                if _writes(font, text):
                    name = te._insert_font(page, "KZ%d" % xref, fontbuffer=buf)
                    return name, font, {"fontbuffer": buf}
            except Exception:
                continue
    fonts = te._system_fonts()
    for key in keys:
        path = fonts.get(key)
        if not path:
            continue
        try:
            font = pymupdf.Font(fontfile=path)
            if _writes(font, text):
                name = te._insert_font(page, "KZS" + key[:20], fontfile=path)
                return name, font, {"fontfile": path}
        except Exception:
            continue
    return None


_BASE14 = (("helv", "hebo", "heit", "hebi"), ("tiro", "tibo", "tiit", "tibi"),
           ("cour", "cobo", "coit", "cobi"))


def _base14_for(st, bold, italic):
    name = te._base14({"font": st.font, "flags": st.flags})
    for fam in _BASE14:
        if name in fam:
            return fam[(2 if italic else 0) + (1 if bold else 0)]
    return name


def _font_style(font):
    """(bold, italic) of a font picked to write with."""
    try:
        nb, ni = natural(font.name, 0)
        return nb or bool(font.is_bold), ni or bool(font.is_italic)
    except Exception:
        return False, False


def resolve(page, st, text, family=None):
    """(Font, text) to write text in style st: see the module's notes. family: a family
    picked in Properties (or Add text's), else st.family / st.font. The text may come back
    with look-alikes for symbols no font has. Raises ValueError when nothing can write it."""
    b, i = st.bold, st.italic
    fam = family or st.family
    if fam or not st.font:
        return _resolve_family(page, fam, b, i, text, st)
    span = {"font": st.font, "flags": st.flags, "size": st.size, "color": st.color}
    nb, ni = natural(st.font, st.flags)
    if (b, i) != (nb, ni):
        v = _variant(page, st.font, b, i, text)
        if v is not None:
            return Font(v[0], v[1], v[2], False, False), text
    found, text = te._font_for(page, span, text)
    if found is None:
        name = _base14_for(st, b, i)        # the built-in family's own bold / italic
        return Font(name, pymupdf.Font(name), None, False, False), text
    name, font, source = found
    # the span's own font (embedded: KZ<xref>, or its installed copy: KZS...) is as bold
    # as the text was; a font for characters it lacks (KZUni, KZB...) is as its name says
    own = name.startswith("KZ") and not name.startswith(("KZUni", "KZB", "KZF"))
    fb, fi = (nb, ni) if own else _font_style(font)
    return Font(name, font, source, b and not fb, i and not fi), text


def _resolve_family(page, fam, b, i, text, st):
    if fam:
        if b or i:
            found = te.chosen_font(page, fam, b, i, text)
            if found is not None:
                fb, fi = _font_style(found[1])
                return Font(found[0], found[1], found[2], b and not fb, i and not fi), text
        found = te.chosen_font(page, fam, False, False, text)
        if found is not None:
            return Font(found[0], found[1], found[2], b, i), text
    if te._winansi_ok(text):
        name = te._BASE14_STYLE[(bool(b), bool(i))]
        return Font(name, pymupdf.Font(name), None, False, False), text
    found = te._unicode_font(page, text) or te._broad_font(page, text)
    if found is None:
        swapped = "".join(te.LOOKALIKES.get(c, c) for c in text)
        if swapped != text:
            return _resolve_family(page, fam, b, i, swapped, st)
        raise ValueError(tr("No font on this computer can write these characters of the "
                               "new text: {names}. Remove or replace them and try again.")
                         .format(names=", ".join(f"{c} (U+{ord(c):04X})"
                                                 for c in te._unwritable(text)[:6])))
    return Font(found[0], found[1], found[2], b, i), text


def _fallback(f):
    """A font picked only for characters the text's own font lacks."""
    return f.name.startswith(("KZUni", "KZB"))


def resolve_all(page, text, keys, family=None):
    """{Style: Font} for every style in keys, and the text and keys again (look-alikes put
    in for symbols no font has). A word whose font lacks some of its characters goes to
    another font on its own (its style with alt=1): the style's other words keep theirs.
    Raises ValueError (nothing changed) when a word can't be written."""
    groups = {}
    for c, k in zip(text, keys):
        if c != "\n":
            groups.setdefault(k, []).append(c)
    fonts, swap = {}, {}
    for k, chars in list(groups.items()):
        f, t2 = resolve(page, k, "".join(chars), family)
        if _fallback(f):
            # some word has characters the font lacks: only those words go to another font
            spans, i = [], 0
            while i < len(text):
                if keys[i] != k or text[i].isspace():
                    i += 1
                    continue
                j = i
                while j < len(text) and keys[j] == k and not text[j].isspace():
                    j += 1
                spans.append((i, j))
                i = j
            bad = [(i, j) for i, j in spans
                   if _fallback(resolve(page, k, text[i:j], family)[0])]
            if len(bad) < len(spans):
                alt = k._replace(alt=1)
                keys = list(keys)
                for i, j in bad:
                    keys[i:j] = [alt] * (j - i)
                odd = "".join(text[i:j] for i, j in bad)
                fonts[alt], t3 = resolve(page, alt, odd, family)
                if t3 != odd:
                    swap[alt] = True
                chars = [c for c, kk in zip(text, keys) if kk == k and c != "\n"]
                f, t2 = resolve(page, k, "".join(chars), family)
        fonts[k] = f
        if t2 != "".join(chars):
            swap[k] = True
    if swap:
        t, ks = [], []
        for c, k in zip(text, keys):
            r = te.LOOKALIKES.get(c, c) if k in swap else c
            t.append(r)
            ks += [k] * len(r)
        text, keys = "".join(t), ks
    return fonts, text, keys


def used_name(fonts, main):
    """The font name to report for styled text written with fonts ({Style: Font}): the
    main style's; when that's a built-in PDF font but another run's font was embedded, that
    one (Save then keeps only the letters used)."""
    name = fonts[main].name
    if not name.startswith("KZ"):
        name = next((f.name for f in fonts.values() if f.name.startswith("KZ")), name)
    return name


def reinsert(page, fonts):
    """Applying the redaction drops fonts no text uses yet: add them again. Returns
    {Style: Font} with the names to write with."""
    done, out = {}, {}
    for k, f in fonts.items():
        if f.source is None:
            out[k] = f
            continue
        key = (f.name, id(f.source))
        if key not in done:
            done[key] = te._insert_font(page, f.name, **f.source)
        out[k] = f._replace(name=done[key])
    return out


# ---- underline and strikethrough metrics ------------------------------------------------
_DECO_CACHE = {}
_BASE14_DECO = {"helv": (0.1, 0.05, 0.26), "tiro": (0.1, 0.05, 0.22),
                "cour": (0.1, 0.05, 0.21)}


def _sfnt(buf):
    """(underline center below the baseline, its thickness, strikethrough center above
    the baseline) in units of the font size, from a TrueType / OpenType font's own tables
    (post, OS/2, head), or None."""
    if not buf or len(buf) < 12:
        return None
    off = 0
    if buf[:4] == b"ttcf":
        off = struct.unpack(">I", buf[12:16])[0]
    n = struct.unpack(">H", buf[off + 4:off + 6])[0]
    tables = {}
    for k in range(min(n, 200)):
        rec = off + 12 + 16 * k
        tag = bytes(buf[rec:rec + 4])
        o, ln = struct.unpack(">II", buf[rec + 8:rec + 16])
        tables[tag] = (o, ln)
    if b"head" not in tables:
        return None
    o = tables[b"head"][0]
    upem = struct.unpack(">H", buf[o + 18:o + 20])[0] or 1000
    under, thick, strike = 0.1, 0.05, 0.26
    if b"post" in tables:
        o = tables[b"post"][0]
        pos, th = struct.unpack(">hh", buf[o + 8:o + 12])
        if th > 0:
            thick = th / upem
        if pos:
            under = -pos / upem + thick / 2
    if b"OS/2" in tables:
        o, ln = tables[b"OS/2"]
        ver = struct.unpack(">H", buf[o:o + 2])[0]
        ssize, spos = struct.unpack(">hh", buf[o + 26:o + 30])
        xh = struct.unpack(">h", buf[o + 86:o + 88])[0] if ver >= 2 and ln >= 88 else 0
        if xh > 0:
            strike = xh / upem / 2
        elif spos > 0:
            strike = spos / upem - max(ssize, 0) / upem / 2
    return under, thick, strike


def deco_metrics(f):
    """(underline offset, thickness, strikethrough offset) x size for a Font."""
    key = f.name if f.source is None else (f.name, len(getattr(f.font, "buffer", b"") or b""))
    if key in _DECO_CACHE:
        return _DECO_CACHE[key]
    got = None
    if f.source is None:
        for fam in _BASE14:
            if f.name in fam:
                got = _BASE14_DECO[fam[0]]
    else:
        try:
            got = _sfnt(f.font.buffer)
        except Exception:
            got = None
    under, thick, strike = got or (0.1, 0.05, 0.26)
    got = (min(0.2, max(0.08, under)), min(0.08, max(0.045, thick)),
           min(0.4, max(0.15, strike)))
    _DECO_CACHE[key] = got
    return got


# ---- writing ----------------------------------------------------------------------------
def _rgb(color):
    return tuple(c / 255 for c in pymupdf.sRGB_to_rgb(color))


def direction(rotate):
    """(along, down) unit vectors in unrotated page space for an insert_text rotation."""
    a = math.radians(rotate)
    d = (round(math.cos(a), 6), round(-math.sin(a), 6))
    return d, (-d[1], d[0])


def _width(fonts, key, text):
    return fonts[key].font.text_length(text, fontsize=key.size)


def _groups(chars):
    """Consecutive (char, key) pairs in the same style: [(text, key)]."""
    out = []
    for c, k in chars:
        if out and out[-1][1] == k:
            out[-1][0].append(c)
        else:
            out.append(([c], k))
    return [("".join(t), k) for t, k in out]


def _split(chars, sep):
    """chars split at sep: (parts, the separators' keys)."""
    parts, seps, cur = [], [], []
    for c, k in chars:
        if c == sep:
            parts.append(cur)
            seps.append(k)
            cur = []
        else:
            cur.append((c, k))
    parts.append(cur)
    return parts, seps


def wrap(chars, fonts, width=None, indent=0.0):
    """Greedy word wrap of styled text (chars: [(char, key)]) to width points (None: only
    at line breaks), measuring each run in its own font: [(row chars, first, last)], first
    and last of each paragraph (a "\\n" starts one); the first line indent points in."""
    rows = []
    for part in _split(chars, "\n")[0]:
        if width is None:
            rows.append((part, True, True))
            continue
        words, spaces = _split(part, " ")
        out, cur, cur_w = [], [], 0.0
        for n, w in enumerate(words):
            ww = sum(_width(fonts, k, c) for c, k in w)
            sp = spaces[n - 1] if n else None
            sw = _width(fonts, sp, " ") if sp is not None else 0.0
            room = width - indent if not out else width
            if cur and cur_w + sw + ww > room:
                out.append(cur)
                cur, cur_w = list(w), ww
            elif cur:
                cur = cur + [(" ", sp)] + list(w)
                cur_w += sw + ww
            else:
                cur, cur_w = list(w), ww
        out.append(cur)
        rows += [(r, i == 0, i == len(out) - 1) for i, r in enumerate(out)]
    return rows


def strip_row(row):
    a, b = 0, len(row)
    while a < b and row[a][0] == " ":
        a += 1
    while b > a and row[b - 1][0] == " ":
        b -= 1
    return row[a:b]


def pieces(row, fonts, spread=None):
    """[(text, key, a0, a1, written)] of a row from its start (points along the text);
    spread: the room to justify it to (its words spread to fill it)."""
    out = []
    if spread is not None:
        words, spaces = _split(row, " ")
        if len(words) > 1:
            widths = [sum(_width(fonts, k, c) for c, k in w) for w in words]
            gap = (spread - sum(widths)) / (len(words) - 1)
            a = 0.0
            for n, w in enumerate(words):
                for text, k in _groups(w):
                    wd = _width(fonts, k, text)
                    out.append((text, k, a, a + wd, True))
                    a += wd
                if n < len(spaces):
                    out.append((" ", spaces[n], a, a + gap, False))
                    a += gap
            return out
    a = 0.0
    for text, k in _groups(row):
        wd = _width(fonts, k, text)
        out.append((text, k, a, a + wd, True))
        a += wd
    return out


def _shear(d, n):
    """The slant (synthetic italic) as an insert_text morph matrix: along the text, the
    top of each letter leans forward."""
    t = SHEAR
    return pymupdf.Matrix(1 + t * n[0] * d[0], t * n[0] * d[1], t * n[1] * d[0],
                          1 + t * n[1] * d[1], 0, 0)


def write_row(shape, origin, rotate, row_pieces, fonts):
    """Write a row's pieces from origin (its baseline's start, unrotated page space) in the
    direction of rotate, with their underlines and strikethrough lines."""
    d, n = direction(rotate)
    origin = pymupdf.Point(origin)

    def at(a, c=0.0):
        return pymupdf.Point(origin.x + d[0] * a + n[0] * c, origin.y + d[1] * a + n[1] * c)
    for text, k, a0, _a1, written in row_pieces:
        if not written or not text:
            continue
        f = fonts[k]
        pt = at(a0)
        rgb = _rgb(k.color)
        kw = {"fontsize": k.size, "fontname": f.name, "color": rgb, "rotate": rotate}
        if f.bold:
            kw.update(render_mode=2, fill=rgb, border_width=STROKE)
        if f.italic:
            kw["morph"] = (pt, _shear(d, n))
        shape.insert_text(pt, text, **kw)
    for kind in ("underline", "strike"):
        group = []
        for p in list(row_pieces) + [None]:
            on = p is not None and getattr(p[1], kind)
            if group and (not on or p[1].color != group[0][1].color):
                _bar(shape, at, kind, group, fonts)
                group = []
            if on:
                group.append(p)


def _bar(shape, at, kind, group, fonts):
    while group and group[-1][0].isspace() and len(group) > 1:
        group = group[:-1]              # (not under the spaces a row ends with)
    k = group[0][1]
    size = max(p[1].size for p in group)
    under, thick, strike = deco_metrics(fonts[k])
    mid = under * size if kind == "underline" else -strike * size
    half = thick * size / 2
    a0, a1 = group[0][2], group[-1][3]
    pts = [at(a0, mid - half), at(a1, mid - half), at(a0, mid + half), at(a1, mid + half)]
    r = pymupdf.Rect(min(p.x for p in pts), min(p.y for p in pts),
                     max(p.x for p in pts), max(p.y for p in pts))
    shape.draw_rect(r)
    shape.finish(color=None, fill=_rgb(k.color), width=0)


def fix_spaces(page, fonts):
    seen = set()
    for f in fonts.values():
        if f.source is not None and f.name not in seen:
            seen.add(f.name)
            te._fix_spaces(page, f.name, f.font)


def write_lines(page, origin, rotate, chars, fonts, step, wrap_width=None):
    """Write styled text from origin (the first baseline's start), lines step points apart,
    left-aligned, wrapped to wrap_width (None: only at line breaks)."""
    _d, n = direction(rotate)
    shape = page.new_shape()
    o = pymupdf.Point(origin)
    for k, (row, _first, _last) in enumerate(wrap(chars, fonts, wrap_width)):
        row = strip_row(row) if wrap_width else row
        pt = pymupdf.Point(o.x + n[0] * step * k, o.y + n[1] * step * k)
        write_row(shape, pt, rotate, pieces(row, fonts), fonts)
    shape.commit(True)
    fix_spaces(page, fonts)
