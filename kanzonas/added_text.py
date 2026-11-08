"""Text the app writes into a page (Add text; Edit text's rewrite of it; Paste and Duplicate
of page text with Edit objects), remembered as one block.

A PDF page keeps positioned letters, not paragraphs: what Add text wrote in a box of its own
width (the words wrapped) or with Shift+Enter lines reads back as separate lines, and Edit
text could only guess they were one text. So what is written is wrapped in a marked-content
sequence (PDF 32000-1, 14.6) of its own, which every PDF reader ignores:

    /KZText <</O [72 120] /R 0 /W 180 /S 14.4 /Y [0 14.4 28.8] /H [0]>> BDC ... EMC

O: where the first line's baseline starts (unrotated page coordinates); R: the direction it
was written in (an insert_text rotation: 0, 90, 180, 270); W: the width its words wrap to
(0: only at line breaks); S: baseline to baseline; Y: each written line's baseline from the
first (farther apart where larger words needed the room); H: the lines a line break
(Shift+Enter) ends, the others but the last ending where the words wrapped.

Only numbers: never any of the text, which stays only in the letters drawn, so taking the
letters out (Apply redactions, Delete, Cut) takes out all there is of them. Which letters
are the block's is found from the numbers: the page's lines whose baseline starts where O, R
and Y put one (a line rewritten in place, Replace text, still is; one moved away no longer
is). A marker whose letters are all gone (nothing drawn inside it) counts for nothing and
is taken out (prune) whenever the page's text is taken out; Apply redactions takes the
marker off any block a redaction mark touches before it applies them (forget_under), so
nothing of a redacted block is left in the file but what is left of its letters. Taking a
marker off removes only its own BDC and EMC: marked content nested inside it (a tagged
PDF's /P <</MCID n>> BDC ... EMC) stays as it was, properly nested.

Files without the marker (and text written by other programs) are read as before.
"""

import contextlib
import re

import pymupdf

from . import text_edit as te

TAG = b"KZText"
_START = re.compile(rb"/KZText\s*<<([^<>()]*)>>\s*BDC(?![^\s\[\]()<>{}/%])")
_TOKEN = re.compile(rb"\(|%[^\r\n]*|<<|>>|<[0-9A-Fa-f\s]*>|/[^\s/\[\]()<>{}%]*|[\[\]{}]|"
                    rb"[^\s/\[\]()<>{}%]+")
_SIMPLE_STR = re.compile(rb"\((?:[^()\\]|\\.)*\)", re.S)
_KV = re.compile(rb"/([A-Za-z]+)\s*(\[[^\]]*\]|[-+]?[0-9.]+)")
_NUM = re.compile(rb"[-+]?(?:[0-9]+\.?[0-9]*|\.[0-9]+)")
_SHOW = {b"Tj", b"TJ", b"'", b'"'}
_DRAWS = re.compile(rb"T[jJ]")


def _skip_string(data, i):
    """Index just past the literal string starting at data[i] == '('."""
    m = _SIMPLE_STR.match(data, i)
    if m:
        return m.end()
    depth, n = 0, len(data)
    while i < n:
        c = data[i]
        if c == 0x5C:
            i += 2
            continue
        if c == 0x28:
            depth += 1
        elif c == 0x29:
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return n


def _end_of(data, pos):
    """(start, end of the EMC closing the sequence opened just before pos, whether letters
    are drawn inside it), or None when it can't be told (unbalanced, an inline picture)."""
    depth, draws = 1, False
    n = len(data)
    while pos < n:
        m = _TOKEN.search(data, pos)
        if m is None:
            return None
        tok = m.group()
        if tok == b"(":
            pos = _skip_string(data, m.start())
            continue
        pos = m.end()
        if tok in (b"BDC", b"BMC"):
            depth += 1
        elif tok == b"EMC":
            depth -= 1
            if depth == 0:
                return m.start(), m.end(), draws
        elif tok in _SHOW:
            draws = True
        elif tok == b"BI":
            return None
    return None


def _props(raw):
    """The marker's numbers, or None when they aren't a block's."""
    got = {}
    for key, val in _KV.findall(raw):
        nums = [float(v) for v in _NUM.findall(val)]
        got[key.decode()] = nums if val.startswith(b"[") else (nums[0] if nums else None)
    try:
        o, ys = got["O"], got["Y"]
        rot = int(round(got.get("R") or 0)) % 360
        step = float(got["S"])
        width = float(got.get("W") or 0)
        if len(o) != 2 or not ys or rot % 90 or step <= 0:
            return None
        breaks = {int(h) for h in got.get("H") or [] if 0 <= h < len(ys) - 1}
        return {"origin": pymupdf.Point(o), "rotate": rot, "width": width or None,
                "step": step, "rows": [float(y) for y in ys], "breaks": breaks}
    except (KeyError, TypeError, ValueError):
        return None


def _fmt(v):
    s = "%.3f" % float(v)
    s = s.rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def marker(props):
    """The BDC that opens a block's sequence."""
    o = props["origin"]
    nums = " ".join(_fmt(y) for y in props["rows"])
    brk = " ".join(str(k) for k in sorted(props["breaks"]))
    return ("/KZText <</O [%s %s] /R %d /W %s /S %s /Y [%s] /H [%s]>> BDC\n" % (
        _fmt(o.x), _fmt(o.y), int(props["rotate"]) % 360, _fmt(props["width"] or 0),
        _fmt(props["step"]), nums, brk)).encode()


def markers(page):
    """[{"xref", "bdc": (start, end), "emc": (start, end), "props", "draws"}] of the blocks
    marked in the page's content streams, in drawing order."""
    doc = page.parent
    out = []
    for x in page.get_contents():
        data = doc.xref_stream(x) or b""
        if TAG not in data:
            continue
        for m in _START.finditer(data):
            props = _props(m.group(1))
            end = _end_of(data, m.end())
            if props is None or end is None:
                continue
            out.append({"xref": x, "bdc": (m.start(), m.end()), "emc": end[:2],
                        "props": props, "draws": end[2]})
    return out


def has_markers(page):
    doc = page.parent
    return any(TAG in (doc.xref_stream(x) or b"") for x in page.get_contents())


# ---- finding a block's lines --------------------------------------------------------------
class Block:
    """A marked block found on the page: its numbers (props) and, for each line it wrote,
    the page's line there [(rect, line)] or None (gone: moved away, deleted or empty)."""

    def __init__(self, props, rows):
        self.props = props
        self.rows = rows

    @property
    def lines(self):
        return [r for r in self.rows if r is not None]

    @property
    def rect(self):
        box = pymupdf.Rect()
        for r, _ln in self.lines:
            box |= r
        return box

    @property
    def origin(self):
        return pymupdf.Point(self.props["origin"])

    def holds(self, line):
        ids = {id(s) for s in line["spans"]}
        return any(ln is line or any(id(s) in ids for s in ln["spans"]) for _r, ln in self.lines)


def _cell(x, y):
    return int(x // 4), int(y // 4)


def find(page, lines, found=None):
    """The page's marked blocks (Block), each with the lines of lines (text_lines output) it
    wrote. found: markers(page), when read already. A line two markers claim is the later
    one's (written over the other)."""
    found = markers(page) if found is None else found
    found = [mk for mk in found if mk["draws"]]
    if not found:
        return []
    grid = {}
    for h in lines:
        o = h[1]["spans"][0]["origin"]
        grid.setdefault(_cell(*o), []).append(h)
    from .text_styles import direction
    blocks, owner = [], {}
    for mk in found:
        p = mk["props"]
        d, n = direction(p["rotate"])
        rows = []
        for y in p["rows"]:
            want = pymupdf.Point(p["origin"].x + n[0] * y, p["origin"].y + n[1] * y)
            cx, cy = _cell(want.x, want.y)
            best = None
            for gx in (cx - 1, cx, cx + 1):
                for gy in (cy - 1, cy, cy + 1):
                    for h in grid.get((gx, gy), ()):
                        ln = h[1]
                        if abs(ln["dir"][0] - d[0]) > 0.02 or abs(ln["dir"][1] - d[1]) > 0.02:
                            continue
                        size = te.main_span(ln)["size"]
                        o = ln["spans"][0]["origin"]
                        along = (o[0] - want.x) * d[0] + (o[1] - want.y) * d[1]
                        across = (o[0] - want.x) * n[0] + (o[1] - want.y) * n[1]
                        if abs(across) > max(0.6, 0.25 * size) or \
                                abs(along) > 1.0 + 0.1 * size:
                            continue
                        dist = abs(across) + abs(along)
                        if best is None or dist < best[0]:
                            best = (dist, h)
            rows.append(best[1] if best else None)
        if any(rows):
            blk = Block(p, rows)
            for k, h in enumerate(rows):
                if h is not None:
                    prev = owner.get(id(h[1]))
                    if prev is not None:
                        pb, pk = prev
                        pb.rows[pk] = None
                    owner[id(h[1])] = (blk, k)
            blocks.append(blk)
    return [b for b in blocks if any(b.rows)]


def block_of(blocks, line):
    """The block in blocks holding line, or None."""
    for b in blocks:
        if b.holds(line):
            return b
    return None


# ---- a block's words ----------------------------------------------------------------------
def contents(page, block):
    """(Styled of the block's text: rows joined, a space where the words wrapped, a line break
    where one was typed; [(row's start in the text, letters stripped from its start, line)]
    for each row with a line)."""
    from . import text_styles as ts
    present = [(k, h) for k, h in enumerate(block.rows) if h is not None]
    styled = dict(zip([k for k, _h in present],
                      ts.read_lines(page, [h[1] for _k, h in present])))
    rows = block.rows
    breaks = block.props["breaks"]
    paras, cur = [], []
    for k in range(len(rows)):
        cur.append(k)
        if k in breaks:
            paras.append(cur)
            cur = []
    paras.append(cur)
    chars, keys, starts = [], [], []
    main = None
    for st in styled.values():
        main = st.main
        break
    for pi, para in enumerate(paras):
        if pi:
            chars.append("\n")
            keys.append(keys[-1] if keys else main)
        there = [k for k in para if k in styled]
        first = True
        for j, k in enumerate(there):
            st = styled[k]
            t, kk = st.text, list(st.keys)
            a, b = 0, len(t)
            if len(there) > 1:
                if j > 0:
                    while a < b and t[a] == " ":
                        a += 1
                if j < len(there) - 1:
                    while b > a and t[b - 1] == " ":
                        b -= 1
            if a >= b:
                continue
            if not first:
                chars.append(" ")
                keys.append(ts._joint(keys[-1], kk[a]))
            first = False
            starts.append((len(chars), a, rows[k][1]))
            chars += list(t[a:b])
            keys += kk[a:b]
    text = "".join(chars)
    decor = [r for st in styled.values() for r in st.decor]
    main = ts.main_style(text, keys, main) if keys else main
    return ts.Styled(text, keys, decor, main), starts


def index_at(starts, text, pt):
    """Where in the block's text the point pt (unrotated page coords) is: the text cursor goes
    there when the block is clicked."""
    if not starts:
        return len(text)
    best = None
    for s, a, ln in starts:
        box = pymupdf.Rect(ln["bbox"])
        dist = 0 if box.contains(pt) else abs(te._baseline(ln) - (
            pt.y if abs(ln["dir"][0]) >= abs(ln["dir"][1]) else pt.x))
        if best is None or dist < best[0]:
            best = (dist, s, a, ln)
    _d, s, a, ln = best
    k = te.line_index(ln, pt) - a
    end = text.find("\n", s)
    nxt = [x for x, _a, _l in starts if x > s]
    stop = min([len(text)] + ([end] if end >= 0 else []) + nxt)
    return max(s, min(s + max(0, k), stop))


# ---- writing ------------------------------------------------------------------------------
@contextlib.contextmanager
def marking(page):
    """with marking(page) as mk: write the block; mk["props"] = its numbers. The content the
    writing added is then wrapped in the block's marker (one stream: what more streams it
    added are joined into the first)."""
    doc = page.parent
    before = set(page.get_contents())
    mk = {}
    yield mk
    props = mk.get("props")
    if props is None:
        return
    order = page.get_contents()
    new = [x for x in order if x not in before and _DRAWS.search(doc.xref_stream(x) or b"")]
    if not new:
        return
    data = b"\n".join(doc.xref_stream(x) or b"" for x in new)
    doc.update_stream(new[0], marker(props) + data + b"\nEMC\n")
    if len(new) > 1:
        keep = [x for x in order if x not in new[1:]]
        doc.xref_set_key(page.xref, "Contents", "[%s]" % " ".join("%d 0 R" % x for x in keep))


def props_of(origin, rotate, width, step, rows):
    """A block's numbers from what text_styles.write_lines (or add_text) wrote: rows
    [(baseline offset, first, last)] of each line, first / last of its paragraph."""
    return {"origin": pymupdf.Point(origin), "rotate": int(rotate) % 360,
            "width": float(width) if width else None, "step": float(step),
            "rows": [float(r[0]) for r in rows] or [0.0],
            "breaks": {k for k, r in enumerate(rows) if r[2] and k < len(rows) - 1}}


def _refuse(text):
    """Raise ValueError (nothing changed) for text a page can't be given."""
    from .i18n import tr
    if any(ord(c) > 0xFFFF for c in text):
        raise ValueError(tr("Emoji and other characters beyond U+FFFF can't be written into "
                            "a PDF page here. Remove them and try again."))
    te.refuse_right_to_left(text)


def box_of(origin, rotate, rows, size):
    """The box (unrotated page coordinates) around lines written from origin: rows as
    text_styles.write_lines gives them."""
    from .text_styles import direction
    d, n = direction(rotate)
    o = pymupdf.Point(origin)
    box = pymupdf.Rect()
    for at, _f, _l, length in rows:
        if length <= 0:
            continue
        for a in (0.0, length):
            for c in (at - 0.8 * size, at + 0.25 * size):
                p = pymupdf.Point(o.x + d[0] * a + n[0] * c, o.y + d[1] * a + n[1] * c)
                box = box | p if not box.is_empty else pymupdf.Rect(p, p)
    return box


def write(page, origin, rotate, text, keys, step, width=None, fonts=None):
    """Write styled text (keys: one text_styles.Style per character) as a block from origin
    (its first baseline's start), lines step apart, wrapped to width (None: only at line
    breaks), marked. fonts: text_styles.resolve_all's, when resolved already (then text and
    keys are what it gave back). Returns (the font name to report, the box written in).
    Raises ValueError (before changing anything) when no font can write it."""
    from . import text_styles as ts
    if fonts is None:
        _refuse(text)
        fonts, text, keys = ts.resolve_all(page, text, keys)
    fonts = ts.reinsert(page, fonts)
    with marking(page) as mk:
        rows = ts.write_lines(page, origin, rotate, list(zip(text, keys)), fonts, step, width)
        mk["props"] = props_of(origin, rotate, width, step, rows)
    main = ts.main_style(text, keys)
    return ts.used_name(fonts, main), box_of(origin, rotate, rows, max(k.size for k in keys))


def rewrite(page, block, text, runs, width, offset=(0, 0), font=None, size=None,
            styled=None):
    """Edit text's rewrite of a marked block: its lines taken out, text written in their
    place as one block from where it started (moved by offset, points), wrapped to width
    (None: only at line breaks), each run of runs ([(text, Style)]) in its style. font:
    (family, bold, italic) picked in Properties; size: a size picked there (every word
    scaled alike, and the line spacing with them); styled: contents(page, block)[0], as it
    was read. Returns (font name, the box written in). Raises ValueError (before changing
    anything) when it can't be written."""
    from . import text_styles as ts
    te.refuse_with_marks(page)
    _refuse(text)
    if styled is None:
        styled = contents(page, block)[0]
    main = styled.main
    rtext, keys = ts.keys_of(runs) if runs else (text, [main] * len(text))
    if rtext != text:
        keys = ts.restyle(styled.text, styled.keys, text, main)
    p = block.props
    step = p["step"]
    if size and main is not None and main.size:
        ratio = float(size) / float(main.size)
        keys = [k._replace(size=round(k.size * ratio, 2)) for k in keys]
        step *= ratio
    if font and font[0]:
        keys = [k._replace(bold=k.bold or bool(font[1]), italic=k.italic or bool(font[2]))
                for k in keys]
    fonts = None
    if text.strip():
        fonts, text, keys = ts.resolve_all(page, text, keys,
                                           family=font[0] if font and font[0] else None)
    te._remove_lines(page, [ln for _r, ln in block.lines], decor=styled.decor)
    if not text.strip():
        return None, pymupdf.Rect()
    origin = pymupdf.Point(p["origin"]) + offset
    return write(page, origin, p["rotate"], text, keys, step, width, fonts=fonts)


# ---- taking markers off ----------------------------------------------------------------------
def _unwrap(page, chosen):
    """Take the markers chosen (markers() entries) off; what they wrapped stays."""
    doc = page.parent
    by = {}
    for mk in chosen:
        by.setdefault(mk["xref"], []).append(mk)
    for x, mks in by.items():
        data = bytearray(doc.xref_stream(x) or b"")
        cuts = sorted([mk["bdc"] for mk in mks] + [mk["emc"] for mk in mks], reverse=True)
        for a, b in cuts:
            data[a:b] = b" "
        doc.update_stream(x, bytes(data))
    return len(chosen)


def prune(page):
    """Take off the markers with nothing drawn in them any more (their letters taken out).
    Returns how many."""
    if not has_markers(page):
        return 0
    return _unwrap(page, [mk for mk in markers(page) if not mk["draws"]])


def forget_under(page, rects):
    """Before redaction marks are applied: take the marker off every block a mark touches (it
    becomes ordinary text, its letters left to the redaction), and off those with nothing
    drawn in them. rects: the marks' boxes."""
    if not rects or not has_markers(page):
        return 0
    found = markers(page)
    boxes = []
    for r in rects:
        r = pymupdf.Rect(r)
        boxes += [r, r * page.derotation_matrix]
    blocks = find(page, te.text_lines(page), found)
    hit = set()
    for b in blocks:
        if any(pymupdf.Rect(r).intersects(box) for r, _ln in b.lines for box in boxes):
            hit.add(id(b.props))
    chosen = [mk for mk in found if not mk["draws"] or id(mk["props"]) in hit]
    return _unwrap(page, chosen) if chosen else 0


def prune_doc(doc):
    for i in range(doc.page_count):
        prune(doc[i])


# ---- copying page text -------------------------------------------------------------------------
def font_buffers(page, keys):
    """{normalized font name: font file} of the embedded fonts keys' letters are drawn in, so a
    copy pasted elsewhere (another document) is written in them too."""
    want = {te._norm(k.font) for k in keys if k.font}
    out = {}
    if not want:
        return out
    doc = page.parent
    for xref, ext, _type, basefont, *_ in page.get_fonts(full=True):
        key = te._norm(basefont)
        if key not in want or key in out or ext in ("n/a", ""):
            continue
        try:
            buf = doc.extract_font(xref)[3]
        except Exception:
            buf = None
        if buf:
            out[key] = buf
    return out


def provide_fonts(page, keys, buffers):
    """Before writing keys' letters on page: embed there the fonts copied with them (buffers,
    font_buffers) that page doesn't have, so they're written in them."""
    if not buffers:
        return
    have = {te._norm(f[3]) for f in page.get_fonts(full=True) if f[1] not in ("n/a", "")}
    done = set()
    for k in keys:
        key = te._norm(k.font) if k.font else ""
        if not key or key in have or key in done or key not in buffers:
            continue
        done.add(key)
        try:
            te._insert_font(page, "KZP" + key[:20], fontbuffer=buffers[key])
        except Exception:
            pass                        # (written in the closest font instead)


def snapshot(page, block):
    """A block as the clipboard keeps it: {"text", "keys", "width", "step", "origin", "rotate",
    "box"} (origin and box unrotated, on its page)."""
    st, _starts = contents(page, block)
    p = block.props
    return {"text": st.text, "keys": list(st.keys), "width": p["width"], "step": p["step"],
            "origin": pymupdf.Point(p["origin"]), "rotate": p["rotate"],
            "box": pymupdf.Rect(block.rect)}


def snapshot_lines(page, lines):
    """Lines of the page's own text (not a marked block: a paragraph Edit objects selected) as
    a block for the clipboard: running text that wraps keeps wrapping to its width, other
    lines keep their line breaks; left-aligned from the first line's start."""
    from . import text_styles as ts
    lines = sorted(lines, key=lambda ln: (round(te._baseline(ln), 1),
                                          te._along(pymupdf.Rect(ln["bbox"]), ln)[0]))
    dx, dy = lines[0]["dir"]
    horizontal = abs(dx - 1) < 0.01 and abs(dy) < 0.01
    box = pymupdf.Rect()
    for ln in lines:
        box |= pymupdf.Rect(ln["bbox"])
    rotate = te.line_rotation(lines[0])
    if dy and not horizontal:
        # (reading order across sideways lines: along "down" of their direction)
        _d, n = ts.direction(rotate)
        lines = sorted(lines, key=lambda ln: ln["spans"][0]["origin"][0] * n[0] +
                       ln["spans"][0]["origin"][1] * n[1])
    if horizontal and len(lines) > 1 and te.flows(lines):
        st = ts.read_paragraph(page, lines)
        lay = te.paragraph_layout(lines)
        origin = pymupdf.Point(lay["left"], lay["first"])
        width = te._fit_width(lay["width"], None, lay["span"]["size"])
        return {"text": st.text, "keys": list(st.keys), "width": width, "step": lay["step"],
                "origin": origin, "rotate": 0, "box": box}
    parts = ts.read_lines(page, lines)
    chars, keys = [], []
    for k, st in enumerate(parts):
        if k:
            chars.append("\n")
            keys.append(keys[-1] if keys else st.main)
        chars += list(st.text)
        keys += list(st.keys)
    _d, n = ts.direction(rotate)
    o = [ln["spans"][0]["origin"] for ln in lines]
    steps = sorted(abs((b[0] - a[0]) * n[0] + (b[1] - a[1]) * n[1]) for a, b in zip(o, o[1:]))
    size = max(te.main_span(ln)["size"] for ln in lines)
    step = steps[len(steps) // 2] if steps else 1.2 * size
    if step < 0.8 * size:
        step = 1.2 * size
    text = "".join(chars)
    return {"text": text, "keys": keys, "width": None, "step": step,
            "origin": pymupdf.Point(o[0]), "rotate": rotate, "box": box}


def prepare(page, text, keys, buffers=None, family=None):
    """Before writing text (keys: a Style per character) on page: (fonts, text, keys as
    text_styles.resolve_all gives them, the fonts that aren't here, written in the closest
    standard font instead). buffers: the fonts copied with the text (font_buffers), embedded
    on page first. Raises ValueError when it can't be written."""
    from . import text_styles as ts
    _refuse(text)
    provide_fonts(page, keys, buffers)
    fonts, text, keys = ts.resolve_all(page, text, keys, family=family)
    missing = set()
    for k, f in fonts.items():
        name = (k.font or "").split("+")[-1]
        if k.font and f.source is None and te._norm(name) not in te._STANDARD_FONTS and \
                not k.family:
            missing.add(name)
    return fonts, text, keys, missing


def plain(blocks):
    """The blocks' words for other programs (plain text)."""
    return "\n\n".join(b["text"] for b in blocks)
