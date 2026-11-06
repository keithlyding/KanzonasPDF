"""Document > Accessibility > Auto-tag: a structure tree (tags) for an untagged PDF, made from
what the pages draw, so screen readers can read it in order, with its headings, lists,
tables and pictures (PDF/UA, ISO 14289-1; WCAG 2.1).

How a page is read
------------------
1. The content stream is read operator by operator (read_page): every text-showing operator
   (Tj TJ ' "), painted path, picture (Do, inline image), form (Do) and shading (sh), with
   the graphics state needed to place it (transformation, font, text rendering mode).
2. Where each character is comes from MuPDF itself: Page.get_texttrace() lists every glyph
   the page draws, in drawing order, with its position, size and font. The reader counts the
   character codes each text operator shows (one byte per code in simple fonts, two in
   Identity-H fonts, a CMap's code ranges otherwise), so glyph k of the trace is code k of
   the stream. The two counts must agree; when they don't (an unusual font, text in a
   pattern), the page is tagged as one paragraph in drawing order and says so.
3. Layout (analyze): characters into lines (rows, split at wide gaps), lines into blocks;
   page headers and footers repeated across pages, and page numbers, are pagination
   artifacts; headings by font size and weight, levels ranked across the document and never
   skipped; bulleted and numbered lists (Lbl for the bullet, LBody for the text); tables with
   ruling lines (PyMuPDF's find_tables) as Table / TR / TH / TD; pictures as Figure (with no
   description yet: the Alt text window asks for one); lines, boxes and other drawings as
   artifacts; links, form fields and comments as Link / Form / Annot with their annotation.
   Anything not recognized for sure is a paragraph (P). Reading order: blocks top to bottom,
   columns left to right (an XY cut: bands across the page, columns found where several
   bands share a gutter).
4. Writing (apply, inside DocumentView.modify: one undo step): each run of content that
   belongs to one element is wrapped in  /Tag <</MCID n>> BDC ... EMC  (text operators are
   split between characters where one shows text of two elements: exact, the positions
   don't change), the rest in /Artifact; the page gets /StructParents and /Tabs /S; the
   catalog a StructTreeRoot with a ParentTree, /MarkInfo <</Marked true>> and /Lang. Marked
   content never crosses q/Q, BT/ET or marked content that was already there (it's opened
   right before the content and closed right after it), so the tags nest properly.

Not handled (left as paragraphs or artifacts, said in the manual): multi-level and nested
lists (flattened), tables without ruling lines, merged table cells (not a table then),
captions, footnotes, formulas, charts drawn with vector graphics (artifacts: describe them
in the text), text inside a pattern, documents that are tagged already (refused).

No Qt here: accessibility_ui.py runs it with a progress window.
"""

import math
import re
import statistics

import pymupdf

from . import pdfcoords
from .i18n import tr

m = pymupdf.mupdf

# ---- reading a content stream ------------------------------------------------------------
_TOKEN = re.compile(rb"\s+|%[^\r\n]*|/[^\s/\[\]()<>{}%]*|<<|>>|<[0-9A-Fa-f\s]*>|[\[\]{}]|"
                    rb"[^\s/\[\]()<>{}%]+")
_WS = b" \t\r\n\f\x00"
_NUM_START = frozenset(b"+-.0123456789")
_CONSTRUCT = {b"m": 2, b"l": 2, b"c": 6, b"v": 4, b"y": 4, b"re": 4, b"h": 0}
_PAINT = {b"S", b"s", b"f", b"F", b"f*", b"B", b"B*", b"b", b"b*"}
_SHOW = {b"Tj", b"TJ", b"'", b'"'}
OPEN_OPS = {b"q", b"BT", b"BDC", b"BMC"}
CLOSE_OPS = {b"Q", b"ET", b"EMC"}


def skip_string(data, i):
    """Index just past the literal string starting at data[i] == '('."""
    depth = 0
    n = len(data)
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


def _inline_end(data, i):
    """data[i:] is an inline image's data after 'ID '. Index just past its 'EI'."""
    n = len(data)
    j = i
    while True:
        k = data.find(b"EI", j)
        if k < 0:
            return n
        before = data[k - 1] if k > 0 else 0x20
        after = data[k + 2] if k + 2 < n else 0x20
        if before in _WS and (after in _WS or after in b"/[(<%"):
            return k + 2
        j = k + 2


def _num(tok):
    try:
        return float(tok)
    except (TypeError, ValueError):
        return None


def tokens(data):
    """(operator, operands, start, end) for each operator of a content stream; operands are
    (kind, start, end): kind "str" (a literal string), "hex", "name", "num", "[", "]", "<<",
    ">>" or "word" (true, false, null inside an array or dictionary). Inline images come as
    (b"BI", [], start, end). start is where the first operand starts."""
    args = []
    i, n = 0, len(data)
    op_start = None
    depth = 0                       # inside [ ] or << >>: words are operands
    match = _TOKEN.match
    while i < n:
        c = data[i]
        if c == 0x28:
            j = skip_string(data, i)
            if op_start is None:
                op_start = i
            args.append(("str", i, j))
            i = j
            continue
        mt = match(data, i)
        if mt is None:
            i += 1
            continue
        j = mt.end()
        c = data[i]
        if c in _WS or c == 0x25:
            i = j
            continue
        tok = data[i:j]
        kind = None
        if c == 0x2F:
            kind = "name"
        elif tok == b"<<":
            kind = "<<"
            depth += 1
        elif tok == b">>":
            kind = ">>"
            depth = max(0, depth - 1)
        elif c == 0x3C:
            kind = "hex"
        elif tok == b"[":
            kind = "["
            depth += 1
        elif tok == b"]":
            kind = "]"
            depth = max(0, depth - 1)
        elif tok in (b"{", b"}"):
            kind = "word"
        elif c in _NUM_START and _num(tok) is not None:
            kind = "num"
        elif depth:
            kind = "word"
        if kind is not None:
            if op_start is None:
                op_start = i
            args.append((kind, i, j))
            i = j
            continue
        start = op_start if op_start is not None else i
        if tok == b"BI":
            k = data.find(b"ID", j)
            while k >= 0 and not (data[k - 1] in _WS and (k + 2 >= n or data[k + 2] in _WS)):
                k = data.find(b"ID", k + 2)
            if k < 0:
                return
            j = _inline_end(data, k + 3)
            yield b"BI", [], i, j
        else:
            yield tok, args, start, j
        args = []
        op_start = None
        depth = 0
        i = j


_ESCAPES = {ord("n"): 10, ord("r"): 13, ord("t"): 9, ord("b"): 8, ord("f"): 12,
            ord("("): 0x28, ord(")"): 0x29, ord("\\"): 0x5C}


def decode_literal(raw):
    """The bytes of a literal string token "(...)"."""
    s = raw[1:-1] if raw.endswith(b")") else raw[1:]
    if b"\\" not in s and b"\r" not in s:
        return bytes(s)
    out = bytearray()
    i, n = 0, len(s)
    while i < n:
        c = s[i]
        if c == 0x5C and i + 1 < n:
            d = s[i + 1]
            if d in _ESCAPES:
                out.append(_ESCAPES[d])
                i += 2
            elif 0x30 <= d <= 0x37:
                j = i + 1
                k = 0
                while j < n and j < i + 4 and 0x30 <= s[j] <= 0x37:
                    k = k * 8 + s[j] - 0x30
                    j += 1
                out.append(k & 0xFF)
                i = j
            elif d == 0x0D:                         # a line continuation
                i += 3 if i + 2 < n and s[i + 2] == 0x0A else 2
            elif d == 0x0A:
                i += 2
            else:
                out.append(d)
                i += 2
        elif c == 0x0D:                             # an end of line is read as \n
            out.append(0x0A)
            i += 2 if i + 1 < n and s[i + 1] == 0x0A else 1
        elif c == 0x5C:
            i += 1
        else:
            out.append(c)
            i += 1
    return bytes(out)


def decode_hex(raw):
    h = re.sub(rb"[^0-9A-Fa-f]", b"", raw)
    if len(h) % 2:
        h += b"0"
    return bytes.fromhex(h.decode())


def string_bytes(data, kind, s, e):
    return decode_literal(data[s:e]) if kind == "str" else decode_hex(data[s:e])


# ---- fonts: how many bytes each character code takes ---------------------------------
def _name(obj):
    obj = m.pdf_resolve_indirect(obj)
    return m.pdf_to_name(obj) if m.pdf_is_name(obj) else None


def _get(obj, key):
    return m.pdf_resolve_indirect(m.pdf_dict_gets(obj, key))


def _codespace(text):
    """[(bytes, low, high)] of a CMap's begincodespacerange sections."""
    out = []
    for sec in re.findall(rb"begincodespacerange(.*?)endcodespacerange", text, re.S):
        for lo, hi in re.findall(rb"<([0-9A-Fa-f\s]*)>\s*<([0-9A-Fa-f\s]*)>", sec):
            lo, hi = decode_hex(lo), decode_hex(hi)
            if lo and len(lo) == len(hi):
                out.append((len(lo), lo, hi))
    return sorted(out)


def _utf16_codes(s):
    out = []
    i, n = 0, len(s)
    while i < n:
        k = 4 if 0xD8 <= s[i] <= 0xDB and i + 3 < n else 2
        out.append(min(k, n - i))
        i += k
    return out


class _Font:
    """How a font splits a string into character codes: codes(bytes) -> [length of each
    code], or None when that can't be told (the page is then tagged as a whole)."""
    __slots__ = ("kind", "ranges")

    def __init__(self, kind, ranges=None):
        self.kind, self.ranges = kind, ranges

    def codes(self, s):
        k = self.kind
        if k == 1:
            return [1] * len(s)
        if k == 2:
            return [2] * (len(s) // 2) + ([1] if len(s) % 2 else [])
        if k == "utf16":
            return _utf16_codes(s)
        if k == "ranges":
            out = []
            i, n = 0, len(s)
            ranges = self.ranges
            while i < n:
                got = 1
                for size, lo, hi in ranges:
                    if i + size > n:
                        continue
                    if all(lo[t] <= s[i + t] <= hi[t] for t in range(size)):
                        got = size
                        break
                out.append(got)
                i += got
            return out
        return None


_ONE = _Font(1)
_UNKNOWN = _Font(None)


def font_codes(font):
    """The _Font of a font dictionary (a resolved MuPDF object)."""
    if not m.pdf_is_dict(font):
        return _UNKNOWN
    sub = _name(m.pdf_dict_gets(font, "Subtype"))
    if sub != "Type0":
        return _ONE
    enc = m.pdf_dict_gets(font, "Encoding")
    name = _name(enc)
    if name is not None:
        if name in ("Identity-H", "Identity-V") or "UCS2" in name:
            return _Font(2)
        if "UTF16" in name:
            return _Font("utf16")
        return _UNKNOWN
    enc = m.pdf_resolve_indirect(enc)
    if m.pdf_is_stream(enc):
        try:
            text = bytes(m.fz_buffer_extract_copy(m.pdf_load_stream(enc)))
        except Exception:
            return _UNKNOWN
        ranges = _codespace(text)
        if ranges:
            sizes = {r[0] for r in ranges}
            if sizes == {2} and all(r[1] == b"\0\0" and r[2] == b"\xff\xff" for r in ranges):
                return _Font(2)
            return _Font("ranges", ranges)
        use = _name(m.pdf_dict_gets(enc, "UseCMap"))
        if use in ("Identity-H", "Identity-V"):
            return _Font(2)
    return _UNKNOWN


# ---- the page's content, operator by operator --------------------------------------------
class Piece:
    """One thing the page draws: kind "text" (a text-showing operator), "path", "image",
    "inline", "form", "shade"; start / end: its bytes (operands included); level: the
    nesting it's at (the q / BT / marked content around it, by serial number); mc: the
    marked content around it, outermost first (each ("artifact"|"mcid"|"other", mcid,
    serial)); g0, g1: its glyphs in the page's glyph sequence; box: (x0, y0, x1, y1) in
    the page as shown, for what isn't text."""
    __slots__ = ("kind", "start", "end", "level", "mc", "g0", "g1", "box", "op", "strings",
                 "elems", "codes", "has_image", "font", "tr", "form_text", "ctm")

    def __init__(self, kind, start, end, level, mc):
        self.kind, self.start, self.end, self.level, self.mc = kind, start, end, level, mc
        self.g0 = self.g1 = 0
        self.box = None
        self.op = None
        self.strings = None             # text: [(bytes, [code lengths])]
        self.elems = None               # TJ: [("s", i) | ("n", raw bytes)]
        self.codes = 0
        self.has_image = False
        self.font = None
        self.tr = 0
        self.form_text = 0
        self.ctm = None


class Unsupported(Exception):
    pass


def _mat_mul(a, b):
    return (a[0] * b[0] + a[1] * b[2], a[0] * b[1] + a[1] * b[3],
            a[2] * b[0] + a[3] * b[2], a[2] * b[1] + a[3] * b[3],
            a[4] * b[0] + a[5] * b[2] + b[4], a[4] * b[1] + a[5] * b[3] + b[5])


def _box(xs, ys, mat):
    pts = [(x * mat[0] + y * mat[2] + mat[4], x * mat[1] + y * mat[3] + mat[5])
           for x in xs for y in ys] if len(xs) == 2 else \
        [(x * mat[0] + y * mat[2] + mat[4], x * mat[1] + y * mat[3] + mat[5])
         for x, y in zip(xs, ys)]
    if not pts:
        return None
    return (min(p[0] for p in pts), min(p[1] for p in pts),
            max(p[0] for p in pts), max(p[1] for p in pts))


class PageReader:
    """Reads a page's content (and the forms it draws, for their glyph count) into Pieces.

    pieces: in drawing order; events: [(position, op)] where nesting changes (q Q BT ET BDC
    BMC EMC); glyphs: the number of glyphs the content shows (as MuPDF's trace counts them);
    exact: False when a font's codes couldn't be told apart."""

    def __init__(self, page, data=None, turn=None):
        self.page = page
        self.doc = page.parent
        self.pdf = pymupdf._as_pdf_document(self.doc)
        self.data = data if data is not None else b"\n".join(
            self.doc.xref_stream(x) or b"" for x in page.get_contents())
        page_obj = m.pdf_load_object(self.pdf, page.xref)
        self.resources = self._page_resources(page_obj)
        # PDF user space -> the page as shown
        shown = pdfcoords.to_page(page) * page.rotation_matrix
        if turn is not None:
            shown = shown * turn
        self.to_shown = tuple(shown)
        self.pieces = []
        self.events = []
        self.glyphs = 0
        self.exact = True
        self.mcids = set()
        self._fonts = {}
        self._forms = {}
        self.text_forms = 0

    def _page_resources(self, obj):
        seen = 0
        while m.pdf_is_dict(obj) and seen < 64:
            res = _get(obj, "Resources")
            if m.pdf_is_dict(res):
                return res
            obj = _get(obj, "Parent")
            seen += 1
        return m.pdf_new_dict(self.pdf, 1)

    def _font(self, res, name):
        ref = m.pdf_dict_gets(_get(res, "Font"), name)
        f = m.pdf_resolve_indirect(ref)
        key = m.pdf_to_num(ref) if m.pdf_is_indirect(ref) else None
        got = self._fonts.get(key) if key else None
        if got is None:
            got = font_codes(f) if m.pdf_is_dict(f) else _UNKNOWN
            if key:
                self._fonts[key] = got
        return got

    def _mc_kind(self, res, args, data):
        """("artifact" | "mcid" | "other", mcid) of a BDC / BMC's operands."""
        tag = None
        mcid = None
        for kind, s, e in args:
            if kind == "name" and tag is None:
                tag = data[s + 1:e]
                continue
        if tag == b"Artifact":
            return "artifact", None
        # the properties: inline << ... /MCID n ... >> or a name in /Properties
        i = 0
        while i < len(args):
            kind, s, e = args[i]
            if kind == "name" and data[s:e] == b"/MCID" and i + 1 < len(args) and \
                    args[i + 1][0] == "num":
                v = _num(data[args[i + 1][1]:args[i + 1][2]])
                mcid = int(v) if v is not None else None
                break
            i += 1
        if mcid is None and len(args) >= 2 and args[-1][0] == "name" and \
                args[0][0] == "name":
            prop = data[args[-1][1] + 1:args[-1][2]].decode("latin-1")
            obj = _get(_get(res, "Properties"), prop)
            if m.pdf_is_dict(obj):
                v = _get(obj, "MCID")
                if m.pdf_is_int(v):
                    mcid = m.pdf_to_int(v)
        if mcid is not None:
            return "mcid", mcid
        return "other", None

    def read(self):
        self._run(self.data, self.resources, (1, 0, 0, 1, 0, 0), top=True)
        return self

    def _run(self, data, res, ctm, top, state=None, depth=0):
        """Read one content stream. top: the page's own (records pieces); else a form's:
        returns (glyph count, has image) and records nothing."""
        pieces, events = self.pieces, self.events
        stack = []
        font = state[0] if state else None
        trm = state[1] if state else 0
        mc = []                         # (kind, mcid, serial) of the marked content around
        level = [0]
        serial = [0]
        lvl_stack = []
        path_start = None
        xs, ys = [], []
        glyphs = 0
        has_image = False
        to_shown = self.to_shown

        def push(op, pos):
            lvl_stack.append(level[0])
            serial[0] += 1
            level[0] = serial[0]
            if top:
                events.append((pos, op))

        def pop(op, pos):
            if lvl_stack:
                level[0] = lvl_stack.pop()
            if top:
                events.append((pos, op))

        for op, args, s, e in tokens(data):
            if op in _CONSTRUCT:
                if path_start is None:
                    path_start = s
                    xs, ys = [], []
                k = _CONSTRUCT[op]
                if k and len(args) >= k:
                    vals = [_num(data[a[1]:a[2]]) for a in args[-k:]]
                    if None not in vals:
                        if op == b"re":
                            x, y, w, h = vals
                            xs += [x, x + w]
                            ys += [y, y + h]
                        else:
                            xs += vals[0::2]
                            ys += vals[1::2]
                continue
            if op in _PAINT or op == b"n":
                if path_start is not None and op != b"n" and top:
                    p = Piece("path", path_start, e, level[0], tuple(mc))
                    p.op = op
                    p.ctm = _mat_mul(ctm, to_shown)
                    if xs:
                        p.box = _box(xs, ys, _mat_mul(ctm, to_shown))
                    pieces.append(p)
                path_start = None
                continue
            if op in (b"W", b"W*"):
                continue
            if path_start is not None and op not in (b"w", b"J", b"j", b"M", b"d", b"ri",
                                                       b"i", b"gs", b"CS", b"cs", b"SC",
                                                       b"SCN", b"sc", b"scn", b"G", b"g",
                                                       b"RG", b"rg", b"K", b"k"):
                path_start = None           # (a path never painted)
            if op in _SHOW:
                strings = []
                elems = None
                if op == b"TJ":
                    elems = []
                    for kind, a0, a1 in args:
                        if kind in ("str", "hex"):
                            elems.append(("s", len(strings)))
                            strings.append(string_bytes(data, kind, a0, a1))
                        elif kind == "num":
                            elems.append(("n", data[a0:a1]))
                else:
                    for kind, a0, a1 in reversed(args):
                        if kind in ("str", "hex"):
                            strings.append(string_bytes(data, kind, a0, a1))
                            break
                f = font if font is not None else _UNKNOWN
                split = []
                n = 0
                for st in strings:
                    c = f.codes(st)
                    if c is None:
                        self.exact = False
                        c = [1] * len(st)
                    split.append((st, c))
                    n += len(c)
                n = n if trm != 7 else 0
                if top:
                    p = Piece("text", s, e, level[0], tuple(mc))
                    p.op = op
                    p.strings = split
                    p.elems = elems
                    p.codes = n
                    p.g0 = self.glyphs + glyphs
                    p.g1 = p.g0 + n
                    p.tr = trm
                    pieces.append(p)
                glyphs += n
                continue
            if op == b"Tf" and len(args) >= 2 and args[0][0] == "name":
                font = self._font(res, data[args[0][1] + 1:args[0][2]].decode("latin-1"))
                continue
            if op == b"Tr" and args and args[-1][0] == "num":
                v = _num(data[args[-1][1]:args[-1][2]])
                trm = int(v) if v is not None else 0
                continue
            if op == b"cm" and len(args) >= 6:
                vals = [_num(data[a[1]:a[2]]) for a in args[-6:]]
                if None not in vals:
                    ctm = _mat_mul(tuple(vals), ctm)
                continue
            if op == b"q":
                stack.append((ctm, font, trm))
                push(op, s)
                continue
            if op == b"Q":
                if stack:
                    ctm, font, trm = stack.pop()
                pop(op, s)
                continue
            if op == b"BT":
                push(op, s)
                continue
            if op == b"ET":
                pop(op, s)
                continue
            if op in (b"BDC", b"BMC"):
                kind, mcid = self._mc_kind(res, args, data)
                if top and mcid is not None:
                    self.mcids.add(mcid)
                push(op, s)
                mc.append((kind, mcid, level[0]))
                continue
            if op == b"EMC":
                if mc:
                    mc.pop()
                pop(op, s)
                continue
            if op == b"BI":
                has_image = True
                if top:
                    p = Piece("inline", s, e, level[0], tuple(mc))
                    p.box = _box([0, 1], [0, 1], _mat_mul(ctm, to_shown))
                    pieces.append(p)
                continue
            if op == b"sh":
                if top:
                    pieces.append(Piece("shade", s, e, level[0], tuple(mc)))
                continue
            if op == b"Do" and args and args[-1][0] == "name":
                name = data[args[-1][1] + 1:args[-1][2]].decode("latin-1")
                xo_ref = m.pdf_dict_gets(_get(res, "XObject"), name)
                xo = m.pdf_resolve_indirect(xo_ref)
                sub = _name(m.pdf_dict_gets(xo, "Subtype")) if m.pdf_is_dict(xo) else None
                if sub == "Image":
                    has_image = True
                    if top:
                        p = Piece("image", s, e, level[0], tuple(mc))
                        p.box = _box([0, 1], [0, 1], _mat_mul(ctm, to_shown))
                        pieces.append(p)
                    continue
                if sub == "Form":
                    n, img, box = self._form(xo_ref, xo, res, ctm, (font, trm), depth)
                    has_image = has_image or img
                    if top:
                        p = Piece("form", s, e, level[0], tuple(mc))
                        p.g0 = self.glyphs + glyphs
                        p.g1 = p.g0 + n
                        p.form_text = n
                        p.has_image = img
                        p.box = box
                        pieces.append(p)
                        if n:
                            self.text_forms += 1
                    glyphs += n
                continue
        if top:
            self.glyphs += glyphs
            return None
        return glyphs, has_image

    def _form(self, ref, xo, res, ctm, state, depth):
        """(glyphs, has image, box as shown) of a form drawn with ctm."""
        fm = (1, 0, 0, 1, 0, 0)
        mat = _get(xo, "Matrix")
        if m.pdf_is_array(mat) and m.pdf_array_len(mat) == 6:
            fm = tuple(m.pdf_to_real(m.pdf_array_get(mat, i)) for i in range(6))
        full = _mat_mul(fm, ctm)
        bb = _get(xo, "BBox")
        box = None
        if m.pdf_is_array(bb) and m.pdf_array_len(bb) == 4:
            v = [m.pdf_to_real(m.pdf_array_get(bb, i)) for i in range(4)]
            box = _box([v[0], v[2]], [v[1], v[3]], _mat_mul(full, self.to_shown))
        num = m.pdf_to_num(ref)
        key = (num, id(state[0]), state[1] == 7)
        got = self._forms.get(key)
        if got is None:
            if depth > 12 or num in getattr(self, "_running", ()):
                return 0, False, box
            self._running = getattr(self, "_running", set()) | {num}
            try:
                data = bytes(m.fz_buffer_extract_copy(m.pdf_load_stream(ref))) \
                    if m.pdf_is_stream(ref) else b""
            except Exception:
                data = b""
            fres = _get(xo, "Resources")
            if not m.pdf_is_dict(fres):
                fres = res
            got = self._run(data, fres, full, top=False, state=state, depth=depth + 1)
            self._running.discard(num)
            self._forms[key] = got
        return got[0], got[1], box


# ---- MuPDF's glyphs ----------------------------------------------------------------------
_BOLD_NAME = re.compile(r"bold|black|heavy|semibold|demi", re.I)


class Glyph:
    __slots__ = ("c", "x", "y", "x0", "y0", "x1", "y1", "size", "bold", "horiz", "font",
                 "owner", "line", "dir", "key")

    def __init__(self, c, x, y, box, size, bold, horiz, font, dir_):
        self.c, self.x, self.y = c, x, y
        self.x0, self.y0, self.x1, self.y1 = box
        self.size, self.bold, self.horiz, self.font, self.dir = size, bold, horiz, font, dir_
        self.owner = None
        self.line = None
        self.key = None


def _trace(page):
    """PyMuPDF's text trace of the page's own content (Page.get_texttrace without the
    markups, and without turning a rotated page upright: positions as the page is shown)."""
    rc = []
    try:
        from pymupdf import extra
        dev = extra.JM_new_texttrace_device(rc)
    except Exception:
        dev = pymupdf.JM_new_texttrace_device(rc)
    m.fz_run_page_contents(page.this, dev, m.FzMatrix(), m.FzCookie())
    m.fz_close_device(dev)
    return rc


def page_glyphs(page):
    """The glyphs MuPDF draws in the page's content, in drawing order, in the page as shown
    (each character of a text drawn filled and then stroked is listed once; clipping text
    isn't listed, as MuPDF's trace leaves it out)."""
    out = []
    prev = None
    groups = []
    for span in _trace(page):
        if groups and groups[-1][0] == span["seqno"]:
            groups[-1][1].append(span)
        else:
            groups.append((span["seqno"], [span]))
    for seq, spans in groups:
        typ = spans[0]["type"]
        chars = [ch[0] for sp in spans for ch in sp["chars"]]
        if typ == 1 and prev is not None and prev[0] == seq - 1 and prev[1] == 0 and \
                prev[2] == chars:
            prev = None
            continue                    # (the stroke of text just filled: one glyph each)
        prev = (seq, typ, chars)
        for sp in spans:
            dx, dy = sp["dir"]
            horiz = abs(dy) < 0.02 and dx > 0
            fname = sp.get("font") or ""
            bold = bool(sp.get("flags", 0) & 16) or bool(_BOLD_NAME.search(fname))
            size = float(sp.get("size") or 0)
            d = (round(dx, 2), round(dy, 2))
            for uc, _gid, org, box in sp["chars"]:
                ch = chr(uc) if 0 <= uc < 0x110000 else "\ufffd"
                x0, y0, x1, y1 = box
                out.append(Glyph(ch, org[0], org[1], (min(x0, x1), min(y0, y1), max(x0, x1),
                                                      max(y0, y1)), size, bold, horiz, fname, d))
    return out


# ---- layout: lines, blocks, what each is -------------------------------------------------
_SPACE = set(" \t\r\n\xa0   ​　")
BULLETS = set("•◦▪▫■□●○►▸‣⁃"
              "–—-*·✓✔➢➤❖◆◇∙◘"
              "◙♦→⇒")
_NUMBERED = re.compile(r"^\(?(\d{1,3}|[a-zA-Z]|[ivxlcdm]{1,6}|[IVXLCDM]{1,6})[.)]$")
_TOC_NUMBER = re.compile(r"^[.\u2026]*(\d{1,4}|[ivxlcdm]{1,6}|[IVXLCDM]{1,6})$")
_PAGE_NUMBER = re.compile(r"^\s*(?:(?:page|página|pag\.?|p\.)\s*)?(\d{1,5}|[ivxlcdm]{1,7}|"
                          r"[IVXLCDM]{1,7})(?:\s*(?:/|of|de)\s*\d{1,5})?\s*$", re.I)


def _is_bullet(c):
    return c in BULLETS or 0xE000 <= ord(c) <= 0xF8FF


def _numbering(token):
    """ListNumbering of a list marker token ("1.", "a)", "(iv)")."""
    t = token.strip("()").rstrip(".)")
    if t.isdigit():
        return "Decimal"
    if re.fullmatch(r"[ivxlcdm]+", t) and (len(t) > 1 or t == "i"):
        return "LowerRoman"
    if re.fullmatch(r"[IVXLCDM]+", t) and (len(t) > 1 or t == "I"):
        return "UpperRoman"
    return "LowerAlpha" if t.islower() else "UpperAlpha"


def _bullet_numbering(c):
    if c in "○◦●" and c != "●":
        return "Circle"
    if c in "▪▫■□":
        return "Square"
    if c in "•●·∙":
        return "Disc"
    return "None"


class Line:
    __slots__ = ("gl", "x0", "y0", "x1", "y1", "size", "bold", "text", "marker", "block",
                 "horiz", "toc")

    def __init__(self, gl, glyphs, horiz=True):
        self.gl = gl
        self.horiz = horiz
        gs = [glyphs[i] for i in gl]
        self.x0 = min(g.x0 for g in gs)
        self.y0 = min(g.y0 for g in gs)
        self.x1 = max(g.x1 for g in gs)
        self.y1 = max(g.y1 for g in gs)
        sizes = sorted(g.size for g in gs)
        self.size = sizes[len(sizes) // 2] or (self.y1 - self.y0) or 1
        self.bold = sum(1 for g in gs if g.bold) >= 0.8 * len(gs)
        # the text, a space where the characters part (for the list markers, and to show)
        parts = []
        prev = None
        for g in gs:
            if prev is not None and horiz and g.x0 - prev.x1 > 0.15 * max(g.size, 1):
                parts.append(" ")
            parts.append(g.c)
            prev = g
        self.text = "".join(parts)
        self.marker = None
        self.block = None
        self.toc = False


class Block:
    __slots__ = ("lines", "x0", "y0", "x1", "y1", "size", "bold", "kind", "level", "elem",
                 "artifact", "numbering", "rank", "marker_x", "list_kind")

    def __init__(self, line):
        self.lines = [line]
        self.x0, self.y0, self.x1, self.y1 = line.x0, line.y0, line.x1, line.y1
        self.size = line.size
        self.bold = line.bold
        self.kind = "P"
        self.level = 0
        self.elem = None
        self.artifact = None
        self.numbering = None
        self.marker_x = None
        self.list_kind = None

    def add(self, line):
        self.lines.append(line)
        self.x0, self.y0 = min(self.x0, line.x0), min(self.y0, line.y0)
        self.x1, self.y1 = max(self.x1, line.x1), max(self.y1, line.y1)

    @property
    def text(self):
        return " ".join(ln.text for ln in self.lines)

    @property
    def box(self):
        return (self.x0, self.y0, self.x1, self.y1)


def _make_lines(glyphs, idx):
    """Lines (Line) of the glyphs idx (not spaces): horizontal ones in rows (the app's
    reading-order rule: a new row where the middle moves by more than half a character's
    height), split where characters part by more than one and a half times their size;
    other directions by drawing order."""
    horiz = [i for i in idx if glyphs[i].horiz]
    other = [i for i in idx if not glyphs[i].horiz]
    horiz.sort(key=lambda i: (glyphs[i].y0 + glyphs[i].y1) / 2)
    rows = []
    row_y = row_h = None
    for i in horiz:
        g = glyphs[i]
        yc, h = (g.y0 + g.y1) / 2, g.y1 - g.y0
        if row_y is None or abs(yc - row_y) > 0.5 * max(h, row_h):
            rows.append([i])
            row_y, row_h = yc, h
        else:
            rows[-1].append(i)
    lines = []
    for row in rows:
        row.sort(key=lambda i: glyphs[i].x0)
        segs = [[row[0]]]
        for a, b in zip(row, row[1:]):
            ga, gb = glyphs[a], glyphs[b]
            if gb.x0 - ga.x1 > 1.5 * max(ga.size, gb.size, 1):
                segs.append([])
            segs[-1].append(b)
        toc = False
        if len(segs) >= 2 and _TOC_NUMBER.match("".join(glyphs[i].c for i in segs[-1])) and \
                len(segs[-2]) > 2:
            # a page number at the end of a row (a table of contents entry): with its row
            segs[-2].extend(segs.pop())
            toc = True
        for seg in segs:
            lines.append(Line(seg, glyphs))
        lines[-1].toc = toc
    # other directions: runs in drawing order, same direction and baseline
    run = []
    for i in sorted(other):
        g = glyphs[i]
        if run:
            p = glyphs[run[-1]]
            dx, dy = g.dir
            # distance across the writing direction
            across = abs((g.x - p.x) * -dy + (g.y - p.y) * dx)
            if g.dir != p.dir or across > 0.3 * max(g.size, 1) or i != run[-1] + 1 and \
                    math.hypot(g.x - p.x, g.y - p.y) > 3 * max(g.size, 1):
                lines.append(Line(run, glyphs, horiz=False))
                run = []
        run.append(i)
    if run:
        lines.append(Line(run, glyphs, horiz=False))
    for ln in lines:
        _find_marker(ln, glyphs)
    return lines


def _find_marker(line, glyphs):
    """line.marker = (kind "bullet" | "number", the marker's glyphs, numbering) when the
    line starts with a list bullet or number followed by a space."""
    if not line.horiz or len(line.gl) < 2:
        return
    first = glyphs[line.gl[0]]
    if _is_bullet(first.c) or first.c == "�":
        nxt = glyphs[line.gl[1]]
        if nxt.x0 - first.x1 > 0.12 * max(first.size, 1) or first.c in "•●":
            if first.c == "�" and nxt.x0 - first.x1 < 0.3 * max(first.size, 1):
                return
            if first.c in "-*–—" and nxt.x0 - first.x1 < 0.2 * max(first.size, 1):
                return
            line.marker = ("bullet", [line.gl[0]], _bullet_numbering(first.c))
        return
    # a number: the first word, up to a space
    k = 0
    while k + 1 < len(line.gl):
        a, b = glyphs[line.gl[k]], glyphs[line.gl[k + 1]]
        if b.x0 - a.x1 > 0.15 * max(a.size, 1):
            break
        k += 1
    if k + 1 >= len(line.gl) or k > 5:
        return
    token = "".join(glyphs[i].c for i in line.gl[:k + 1])
    if _NUMBERED.match(token):
        line.marker = ("number", line.gl[:k + 1], _numbering(token))


def _make_blocks(lines):
    """Lines into blocks (paragraphs): a line joins the block right above it when the gap
    between them is small and steady, they overlap across, their size and weight match, it
    doesn't start a list item, and it doesn't start a new indented paragraph."""
    lines = sorted(lines, key=lambda ln: (round(ln.y0, 1), ln.x0))
    blocks = []
    for ln in lines:
        best = None
        if ln.horiz and ln.marker is None:
            for b in blocks:
                last = b.lines[-1]
                if not last.horiz:
                    continue
                h = max(ln.size, last.size)
                gap = ln.y0 - last.y1
                if gap < -0.5 * h or gap > 0.6 * h:
                    continue
                if len(b.lines) >= 2:
                    before = last.y0 - b.lines[-2].y1
                    if gap > before + 0.35 * h:
                        continue
                if not (ln.x0 < b.x1 - 1 and ln.x1 > b.x0 + 1):
                    continue
                if abs(ln.size - b.size) > 0.12 * b.size or ln.bold != b.bold:
                    continue
                left = min(x.x0 for x in b.lines[1:]) if len(b.lines) > 1 else b.x0
                if b.lines[0].marker is not None:
                    left = min([x.x0 for x in b.lines[1:]] or [ln.x0])
                if ln.x0 > left + 0.8 * h and last.x1 < b.x1 - 2 * h:
                    continue            # an indented first line after a short one
                if best is None or gap < best[0]:
                    best = (gap, b)
        if best is not None:
            best[1].add(ln)
            ln.block = best[1]
        else:
            b = Block(ln)
            ln.block = b
            blocks.append(b)
    return blocks


# ---- reading order ---------------------------------------------------------------------
def reading_order(items, box=lambda it: it.box):
    """items in reading order: bands top to bottom; where several bands in a row share a
    gutter and one of them has a paragraph of more than one line, they are columns, read
    one after the other, left to right; within a band without columns, top to bottom then
    left to right."""
    items = list(items)
    if len(items) <= 1:
        return items
    tops = sorted(items, key=lambda it: (box(it)[1], box(it)[0]))
    bands = []
    bottom = None
    for it in tops:
        b = box(it)
        if bands and b[1] < bottom - 0.5:
            bands[-1].append(it)
            bottom = max(bottom, b[3])
        else:
            bands.append([it])
            bottom = b[3]

    def gutters(band):
        spans = sorted((box(it)[0], box(it)[2]) for it in band)
        out = []
        reach = spans[0][1]
        for x0, x1 in spans[1:]:
            if x0 > reach + 0.5:
                out.append((reach, x0))
            reach = max(reach, x1)
        return out

    def tall(band):
        return any(getattr(it, "tall", False) for it in band)

    merged = []
    for band in bands:
        g = gutters(band)
        if merged and g and merged[-1][1]:
            pg = merged[-1][1]
            common = [(max(a0, b0), min(a1, b1)) for a0, a1 in pg for b0, b1 in g
                      if min(a1, b1) - max(a0, b0) > 2]
            if common and (tall(band) or tall(merged[-1][0])):
                both = merged[-1][0] + band
                merged[-1] = (both, gutters(both) or common)
                continue
        merged.append((band, g))
    out = []
    for band, g in merged:
        g = gutters(band)
        if not g:
            out.extend(sorted(band, key=lambda it: (box(it)[1], box(it)[0])))
            continue
        cols = []
        edges = [c[1] for c in g]
        for it in band:
            k = sum(1 for e in edges if box(it)[0] >= e - 0.01)
            while len(cols) <= k:
                cols.append([])
            cols[k].append(it)
        for col in cols:
            if len(col) == len(band):            # (can't happen; guards the recursion)
                out.extend(sorted(col, key=lambda it: (box(it)[1], box(it)[0])))
            else:
                out.extend(reading_order(col, box))
    return out


# ---- elements ------------------------------------------------------------------------
class Elem:
    """A structure element being made: type (P, H1, Figure...), kids (Elem, an MCID on the
    element's page, or ("objr", annotation xref)), alt, attrs (PDF text of /A), page,
    key (where it starts in reading order), sort (kids put in reading order)."""
    __slots__ = ("type", "kids", "alt", "attrs", "page", "key", "sort", "label", "xref",
                 "box")

    def __init__(self, type_, page=None, sort=True, attrs=None, label=""):
        self.type, self.page, self.sort, self.attrs, self.label = type_, page, sort, attrs, label
        self.kids = []
        self.alt = None
        self.key = None
        self.xref = 0
        self.box = None

    def add(self, kid):
        self.kids.append(kid)
        return kid

    def __repr__(self):
        return "<%s %s>" % (self.type, self.label[:30])


ART = "artifact"
HEADER = ("pagination", "Header")
FOOTER = ("pagination", "Footer")


def _norm(text):
    return re.sub(r"\d+", "#", " ".join(text.lower().split()))


class Layout:
    """A page read for tagging: the reader, glyphs, lines, blocks, tables, pictures."""

    def __init__(self, page):
        self.index = page.number
        self.ok = True
        self.why = ""
        g = self.glyphs = page_glyphs(page)
        # most of the text running another way (a landscape page drawn sideways): the page
        # is read turned so that it runs left to right
        turn = None
        rect = pymupdf.Rect(page.rect)
        dirs = {}
        for gl in g:
            dirs[gl.dir] = dirs.get(gl.dir, 0) + 1
        if dirs:
            main = max(dirs.items(), key=lambda kv: kv[1])[0]
            if main in ((0.0, 1.0), (-1.0, 0.0), (0.0, -1.0)) and dirs[main] > 0.5 * len(g):
                turn = pymupdf.Matrix(-math.degrees(math.atan2(main[1], main[0])))
                r = (rect * turn).normalize()
                turn = turn * pymupdf.Matrix(1, 0, 0, 1, -r.x0, -r.y0)   # (at 0, 0 again)
                rect = (rect * turn).normalize()
                for gl in g:
                    p = pymupdf.Point(gl.x, gl.y) * turn
                    b = (pymupdf.Rect(gl.x0, gl.y0, gl.x1, gl.y1) * turn).normalize()
                    gl.x, gl.y = p.x, p.y
                    gl.x0, gl.y0, gl.x1, gl.y1 = b.x0, b.y0, b.x1, b.y1
                    d = pymupdf.Point(gl.dir) * pymupdf.Matrix(turn.a, turn.b, turn.c,
                                                               turn.d, 0, 0)
                    gl.dir = (round(d.x, 2), round(d.y, 2))
                    gl.horiz = abs(d.y) < 0.02 and d.x > 0
        self.turn = turn
        r = self.reader = PageReader(page, turn=turn).read()
        self.rect = tuple(rect)
        self.tables = []
        self.figures = []
        self.lines = []
        self.blocks = []
        if not r.exact or r.glyphs != len(g):
            self.ok = False
            self.why = "glyphs"
            return
        if any(k == "mcid" for p in r.pieces for k, _m, _s in p.mc):
            self.ok = False
            self.why = "tagged"
            return
        skip = set()
        for p in r.pieces:
            if p.g1 > p.g0 and any(k == "artifact" for k, _m, _s in p.mc):
                skip.update(range(p.g0, p.g1))
        x0, y0, x1, y1 = self.rect
        usable = []
        for i, gl in enumerate(g):
            if i in skip:
                continue
            cx, cy = (gl.x0 + gl.x1) / 2, (gl.y0 + gl.y1) / 2
            if not (x0 - 1 <= cx <= x1 + 1 and y0 - 1 <= cy <= y1 + 1) or gl.size <= 0.1:
                gl.owner = ART
                continue
            if gl.c in _SPACE or not gl.c.strip():
                continue
            usable.append(i)
        self.tables = _grid_tables(page, r, g, usable)
        if self.tables:
            taken = {i for t in self.tables for i in t["glyphs"]}
            usable = [i for i in usable if i not in taken]
        self.lines = _make_lines(g, usable)
        self.blocks = _make_blocks(self.lines)
        area = max(1.0, (x1 - x0) * (y1 - y0))
        for p in r.pieces:
            if p.kind not in ("image", "inline", "form") or p.box is None or \
                    any(k == "artifact" for k, _m, _s in p.mc):
                continue
            if p.kind == "form" and (p.form_text or not p.has_image):
                continue
            bx0, by0, bx1, by1 = p.box
            bx0, by0, bx1, by1 = max(bx0, x0), max(by0, y0), min(bx1, x1), min(by1, y1)
            w, h = bx1 - bx0, by1 - by0
            if w < 6 or h < 6 or w * h < 64:
                continue                # a dot, a spacer, a bullet picture
            if w * h >= 0.75 * area and len(usable) + sum(len(t["glyphs"]) for t in
                                                         self.tables) > 0:
                continue                # a scan behind its recognized text
            self.figures.append({"piece": p, "box": (bx0, by0, bx1, by1)})


def _edges(piece, data):
    """The straight, level or upright lines a path draws, as shown: [("h", y, x0, x1) |
    ("v", x, y0, y1)]: the lines of a stroked path, a thin filled rectangle as a line."""
    mat = piece.ctm
    out = []
    pts = []                            # (x, y) of the current subpath
    sub_start = None
    curved = False
    stroke = piece.op not in (b"f", b"F", b"f*")

    def tf(x, y):
        return (x * mat[0] + y * mat[2] + mat[4], x * mat[1] + y * mat[3] + mat[5])

    def seg(a, b):
        if abs(a[1] - b[1]) < 0.5:
            out.append(("h", (a[1] + b[1]) / 2, min(a[0], b[0]), max(a[0], b[0])))
        elif abs(a[0] - b[0]) < 0.5:
            out.append(("v", (a[0] + b[0]) / 2, min(a[1], b[1]), max(a[1], b[1])))

    def thin(x0, y0, x1, y1):
        if x1 - x0 >= y1 - y0 and y1 - y0 < 2.5:
            out.append(("h", (y0 + y1) / 2, x0, x1))
        elif y1 - y0 > x1 - x0 and x1 - x0 < 2.5:
            out.append(("v", (x0 + x1) / 2, y0, y1))
    for op, args, _s, _e in tokens(data[piece.start:piece.end]):
        sub = data[piece.start:piece.end]
        vals = [_num(sub[a[1]:a[2]]) for a in args if a[0] == "num"]
        if op == b"m" and len(vals) >= 2:
            pts = [tf(vals[-2], vals[-1])]
            sub_start = pts[0]
        elif op == b"l" and len(vals) >= 2 and pts:
            q = tf(vals[-2], vals[-1])
            if stroke:
                seg(pts[-1], q)
            pts.append(q)
        elif op == b"re" and len(vals) >= 4:
            x, y, w, h = vals[-4:]
            c = [tf(x, y), tf(x + w, y), tf(x + w, y + h), tf(x, y + h)]
            if stroke:
                for a, b in zip(c, c[1:] + c[:1]):
                    seg(a, b)
            else:
                xs, ys = [p[0] for p in c], [p[1] for p in c]
                if abs(c[0][1] - c[1][1]) < 0.01 or abs(c[0][0] - c[1][0]) < 0.01:
                    thin(min(xs), min(ys), max(xs), max(ys))
            pts = [c[0]]
            sub_start = c[0]
        elif op == b"h" and pts and sub_start is not None:
            if stroke:
                seg(pts[-1], sub_start)
            pts.append(sub_start)
        elif op in (b"c", b"v", b"y"):
            curved = True
            if len(vals) >= 2:
                pts.append(tf(vals[-2], vals[-1]))
    if not stroke and not curved and len(pts) in (4, 5) and not out:
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        thin(min(xs), min(ys), max(xs), max(ys))
    return out


def _cluster(values, tol=2.0):
    """Sorted values merged where they are within tol: [(mean, [values])]."""
    out = []
    for v in sorted(values):
        if out and v - out[-1][1][-1] <= tol:
            out[-1][1].append(v)
        else:
            out.append((None, [v]))
    return [(sum(vs) / len(vs), vs) for _m, vs in out]


def _grid_tables(page, reader, glyphs, usable):
    """Tables drawn with ruling lines on every side of every cell (a full grid: no merged
    cells), 2 rows and 2 columns at least: [{"box", "rows": [[cell box]], "glyphs":
    {glyph: (row, col)}, "header": bool}]."""
    paths = [p for p in reader.pieces if p.kind == "path" and p.ctm is not None and
             not any(k == "artifact" for k, _m, _s in p.mc)]
    if len(paths) < 4 or len(paths) > 4000 or not usable:
        return []
    hs, vs = [], []
    for p in paths:
        for e in _edges(p, reader.data):
            (hs if e[0] == "h" else vs).append(e[1:])
    if len(hs) < 3 or len(vs) < 3:
        return []
    # groups of lines that touch each other
    lines = [("h",) + e for e in hs] + [("v",) + e for e in vs]
    parent = list(range(len(lines)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    tol = 2.0
    import bisect
    upright = sorted((e[1], j) for j, e in enumerate(lines) if e[0] == "v")
    xs_sorted = [x for x, _j in upright]
    for i, a in enumerate(lines):
        if a[0] != "h":
            continue
        # a: ("h", y, x0, x1); the upright lines whose x is within it: (x, y0, y1)
        lo = bisect.bisect_left(xs_sorted, a[2] - tol)
        hi = bisect.bisect_right(xs_sorted, a[3] + tol)
        for _x, j in upright[lo:hi]:
            b = lines[j]
            if b[2] - tol <= a[1] <= b[3] + tol:
                parent[find(i)] = find(j)
    groups = {}
    for i in range(len(lines)):
        groups.setdefault(find(i), []).append(lines[i])
    out = []
    for grp in groups.values():
        gh = [e for e in grp if e[0] == "h"]
        gv = [e for e in grp if e[0] == "v"]
        ys = [c for c, _v in _cluster([e[1] for e in gh])]
        xs = [c for c, _v in _cluster([e[1] for e in gv])]
        if len(ys) < 3 or len(xs) < 3:
            continue

        def covered(kind, at, a, b):
            """The span a..b at position at is drawn by lines of that kind."""
            spans = sorted((e[2], e[3]) for e in (gh if kind == "h" else gv)
                           if abs(e[1] - at) <= tol)
            reach = a
            for s0, s1 in spans:
                if s0 > reach + tol:
                    break
                reach = max(reach, s1)
            return reach >= b - tol
        ok = True
        for r in range(len(ys) - 1):
            for c in range(len(xs) - 1):
                if not (covered("h", ys[r], xs[c], xs[c + 1]) and
                        covered("h", ys[r + 1], xs[c], xs[c + 1]) and
                        covered("v", xs[c], ys[r], ys[r + 1]) and
                        covered("v", xs[c + 1], ys[r], ys[r + 1])):
                    ok = False
                    break
            if not ok:
                break
        if not ok:
            continue
        rows = [[(xs[c], ys[r], xs[c + 1], ys[r + 1]) for c in range(len(xs) - 1)]
                for r in range(len(ys) - 1)]
        cells = {}
        for i in usable:
            gl = glyphs[i]
            cx, cy = (gl.x0 + gl.x1) / 2, (gl.y0 + gl.y1) / 2
            if not (xs[0] <= cx <= xs[-1] and ys[0] <= cy <= ys[-1]):
                continue
            r = next(k for k in range(len(ys) - 1) if cy <= ys[k + 1] or k == len(ys) - 2)
            c = next(k for k in range(len(xs) - 1) if cx <= xs[k + 1] or k == len(xs) - 2)
            cells[i] = (r, c)
        if not cells:
            continue
        nrow, ncol = len(rows), len(rows[0])
        if len(set(cells.values())) < 0.5 * nrow * ncol:
            continue                    # mostly empty boxes: a form's frame, not a table
        texts = {}
        for i in sorted(cells, key=lambda i: (glyphs[i].y0, glyphs[i].x0)):
            texts.setdefault(cells[i], []).append(glyphs[i])
        if max(len(v) for v in texts.values()) > 400:
            continue                    # a paragraph in a box: not a table
        out.append({"box": (xs[0], ys[0], xs[-1], ys[-1]), "rows": rows, "glyphs": cells,
                    "header": _header_row(texts, nrow, ncol)})
    return out


def _header_row(texts, nrow, ncol):
    """Whether the first row of a table is its header: it looks different (bold, bigger),
    or it holds only words where the other rows have numbers."""
    def look(r):
        gs = [gl for (ri, _c), v in texts.items() if ri == r for gl in v]
        return (sum(1 for gl in gs if gl.bold) / max(1, len(gs)),
                statistics.median([gl.size for gl in gs]) if gs else 0)
    b0, s0 = look(0)
    rest = [look(r) for r in range(1, nrow)]
    rb = sum(x[0] for x in rest) / len(rest)
    rs = statistics.median([x[1] for x in rest if x[1]] or [s0])
    num = re.compile(r"[\s\d.,%$()+\-]+")
    words = ["".join(gl.c for gl in texts.get((0, c), [])) for c in range(ncol)]
    numeric = any(num.fullmatch("".join(gl.c for gl in v)) for (ri, _c), v in texts.items()
                  if ri > 0)
    return (b0 > 0.6 and rb < 0.4) or (s0 > rs * 1.1) or \
        (all(w.strip() for w in words) and numeric and not any(num.fullmatch(w)
                                                               for w in words))


# ---- the document's survey (first pass) -------------------------------------------------
def _band(box, rect, lines=1):
    """"top" or "bottom" when a line (or a block of at most two lines) sits in the page's
    top or bottom tenth, where headers and footers go."""
    h = rect[3] - rect[1]
    if lines > 2:
        return None
    if box[3] <= rect[1] + 0.1 * h:
        return "top"
    if box[1] >= rect[1] + 0.9 * h:
        return "bottom"
    return None


def _short(block):
    text = block.text.strip()
    return not any(ln.toc for ln in block.lines) and len(block.lines) <= 3 and 0 < len(text) <= 160 and any(c.isalpha() for c in text) \
        and all(ln.horiz for ln in block.lines)


class Survey:
    """What the whole document shares: the body text size, the heading styles and their
    levels, the headers and footers repeated on its pages."""

    def __init__(self, pages):
        self.pages = pages
        self.sizes = {}
        self.styles = {}
        self.bands = {}
        self.levels = {}
        self.body = 10.0

    def add(self, layout):
        for ln in layout.lines:
            band = _band((ln.x0, ln.y0, ln.x1, ln.y1), layout.rect)
            if band:
                self.bands.setdefault(self._band_key(band, ln), set()).add(layout.index)
        for b in layout.blocks:
            n = sum(len(ln.gl) for ln in b.lines)
            key = round(b.size * 2) / 2
            self.sizes[key] = self.sizes.get(key, 0) + n
            if _short(b) and b.lines[0].marker is None:
                st = (key, b.bold)
                self.styles[st] = self.styles.get(st, 0) + 1
        for t in layout.tables:
            for i in t["glyphs"]:
                key = round(layout.glyphs[i].size * 2) / 2
                self.sizes[key] = self.sizes.get(key, 0) + 1

    def finish(self):
        if self.sizes:
            self.body = max(self.sizes.items(), key=lambda kv: (kv[1], -kv[0]))[0]
        heads = [st for st in self.styles if self.heading_style(st)]
        heads.sort(key=lambda st: (-st[0], not st[1]))
        self.levels = {st: min(6, k + 1) for k, st in enumerate(heads)}

    def heading_style(self, st):
        size, bold = st
        return size >= 1.15 * self.body or (bold and size >= 0.95 * self.body)

    def repeated(self, layout, line):
        """HEADER or FOOTER when the line is a page header or footer (a page number, or
        the same words in the same place on many pages), else None."""
        band = _band((line.x0, line.y0, line.x1, line.y1), layout.rect)
        if band is None:
            return None
        text = line.text.strip()
        kind = HEADER if band == "top" else FOOTER
        if _PAGE_NUMBER.match(text) and line.size <= 1.3 * self.body:
            return kind
        if line.size > 1.15 * self.body:
            return None                 # (big: a heading, not a running header)
        need = max(2, int(0.4 * self.pages + 0.999)) if self.pages > 1 else 10 ** 9
        if len(self.bands.get(self._band_key(band, line), ())) >= need:
            return kind
        return None

    @staticmethod
    def _band_key(band, line):
        """Lines in the same band, with the same words (any number in them), in the same
        place (within a few points), at the same size, are a running header or footer."""
        return (band, _norm(line.text), round(line.y0 / 6), round(line.size))


# ---- one page's tags -----------------------------------------------------------------
class _Item:
    __slots__ = ("box", "kind", "obj", "tall", "rank")

    def __init__(self, box, kind, obj, tall=False):
        self.box, self.kind, self.obj, self.tall = box, kind, obj, tall
        self.rank = 0


class PagePlan:
    """What auto-tag writes for one page: content (new bytes, or None to leave it), elems
    (its top-level elements in reading order), parents (MCID -> element), annots
    [(xref, element)], note (why the page was tagged as a whole or left, or "")."""

    def __init__(self, index):
        self.index = index
        self.content = None
        self.elems = []
        self.parents = []
        self.annots = []
        self.note = ""
        self.keys = {}


def _annotations(page, turn=None):
    """[(xref, subtype, box as shown)] of the markups, links and fields screen readers must
    find (not popups, printer marks or hidden ones)."""
    doc = page.parent
    to_shown = pdfcoords.to_page(page) * page.rotation_matrix
    if turn is not None:
        to_shown = to_shown * turn
    out = []
    for xref, _t, _id in page.annot_xrefs():
        sub = doc.xref_get_key(xref, "Subtype")[1].lstrip("/")
        if sub in ("Popup", "PrinterMark", "TrapNet"):
            continue
        f = doc.xref_get_key(xref, "F")
        if f[0] == "int" and int(f[1]) & 2:
            continue
        kind, rect = doc.xref_get_key(xref, "Rect")
        try:
            r = pymupdf.Rect([float(v) for v in rect.strip("[]").split()]) * to_shown
        except Exception:
            r = pymupdf.Rect(0, 0, 0, 0)
        out.append((xref, sub, tuple(r.normalize())))
    return out


def _bdc(owner, mcid):
    if owner == ART:
        return b"\n/Artifact BMC\n"
    if isinstance(owner, tuple):
        return b"\n/Artifact <</Type /Pagination /Subtype /%s>> BDC\n" % owner[1].encode()
    return b"\n/%s <</MCID %d>> BDC\n" % (owner.type.encode(), mcid)


def _hexstr(b):
    return b"<" + b.hex().encode() + b">"


def _split_show(piece, data, owners):
    """The text operator piece in parts, one per run of codes with one owner:
    [(owner, bytes)] (bytes None: the operator as it was)."""
    runs = []
    k = 0
    for si, (st, codes) in enumerate(piece.strings):
        off = 0
        for n in codes:
            o = owners[k]
            if runs and runs[-1][0] == o:
                runs[-1][1].append((si, off, n))
            else:
                runs.append((o, [(si, off, n)]))
            off += n
            k += 1
    if len(runs) <= 1:
        return [(runs[0][0] if runs else ART, None)]
    args = list(tokens(data[piece.start:piece.end]))
    prefix = b""
    if piece.op == b"'":
        prefix = b"T* "
    elif piece.op == b'"':
        nums = [a for a in args[0][1] if a[0] == "num"] if args else []
        sub = data[piece.start:piece.end]
        if len(nums) >= 2:
            prefix = sub[nums[0][1]:nums[0][2]] + b" Tw " + sub[nums[1][1]:nums[1][2]] + \
                b" Tc T* "
    out = []
    if piece.op == b"TJ":
        # each string element's codes go with their run; a number goes with the string
        # after it (it moves the position before that string's first glyph)
        where = {}
        for ri, (_o, codes) in enumerate(runs):
            for si, off, n in codes:
                where.setdefault(si, []).append((ri, off, n))
        parts = [[] for _ in runs]
        pending = []
        last = 0
        for kind, val in piece.elems:
            if kind == "n":
                pending.append(val)
                continue
            st = piece.strings[val][0]
            for ri, off, n in where.get(val, []):
                if pending:
                    parts[ri].extend(pending)
                    pending = []
                if parts[ri] and parts[ri][-1][:1] == b"<":
                    parts[ri][-1] = parts[ri][-1][:-1] + st[off:off + n].hex().encode() + b">"
                else:
                    parts[ri].append(_hexstr(st[off:off + n]))
                last = ri
        if pending:
            parts[last].extend(pending)
        for ri, (o, _c) in enumerate(runs):
            out.append((o, (prefix if ri == 0 else b"") + b"[" + b" ".join(parts[ri]) +
                        b"] TJ"))
        return out
    for ri, (o, codes) in enumerate(runs):
        b = b"".join(piece.strings[si][0][off:off + n] for si, off, n in codes)
        out.append((o, (prefix if ri == 0 else b"") + _hexstr(b) + b" Tj"))
    return out


def plan_page(page, layout, survey, state):
    """The PagePlan of one page (state: what carries from page to page: the level of the
    heading before)."""
    plan = PagePlan(layout.index)
    annots = _annotations(page, getattr(layout, "turn", None))
    if not layout.ok:
        _whole_page(plan, layout, annots)
        return plan
    glyphs = layout.glyphs
    items = []
    body = []
    for ln in layout.lines:
        art = survey.repeated(layout, ln)
        if art is None:
            body.append(ln)
            continue
        for i in ln.gl:
            glyphs[i].owner = art
    for b in _make_blocks(body):
        items.append(_Item(b.box, "block", b, tall=len(b.lines) > 1))
    for t in layout.tables:
        items.append(_Item(t["box"], "table", t, tall=True))
    for f in layout.figures:
        items.append(_Item(f["box"], "figure", f))
    # links over text become part of it; the rest are items of their own
    link_glyphs = {}
    for xref, sub, box in annots:
        if sub == "Link":
            inside = [i for i, gl in enumerate(glyphs) if gl.owner is None and
                      gl.c not in _SPACE and box[0] <= (gl.x0 + gl.x1) / 2 <= box[2] and
                      box[1] <= (gl.y0 + gl.y1) / 2 <= box[3]]
            if inside:
                link_glyphs[xref] = inside
                continue
        items.append(_Item(box, "annot", (xref, sub)))
    order = reading_order(items)
    for k, it in enumerate(order):
        it.rank = k
    # elements, in reading order
    tops = []
    k = 0
    while k < len(order):
        it = order[k]
        k += 1
        if it.kind == "block":
            b = it.obj
            st = (round(b.size * 2) / 2, b.bold)
            lv = survey.levels.get(st)
            if lv and _short(b) and survey.heading_style(st) and \
                    (b.lines[0].marker is None or b.lines[0].marker[0] == "number"):
                level = min(lv, state.get("level", 0) + 1)
                state["level"] = level
                e = Elem("H%d" % level, page.number, label=b.text)
                tops.append((it, e))
                _own(glyphs, b, e)
                continue
            mk = b.lines[0].marker
            if mk is not None:
                group = [b]
                while k < len(order) and order[k].kind == "block":
                    nb = order[k].obj
                    nm = nb.lines[0].marker
                    if nm is None or nm[0] != mk[0] or abs(glyphs[nm[1][0]].x0 -
                                                         glyphs[mk[1][0]].x0) > nb.size:
                        break
                    group.append(nb)
                    k += 1
                if mk[0] == "bullet" or len(group) >= 2:
                    lst = Elem("L", page.number, sort=False,
                               attrs="<</O /List /ListNumbering /%s>>" % mk[2],
                               label=group[0].text)
                    for gb in group:
                        li = lst.add(Elem("LI", page.number, sort=False, label=gb.text))
                        lbl = li.add(Elem("Lbl", page.number))
                        body = li.add(Elem("LBody", page.number, label=gb.text))
                        marks = set(gb.lines[0].marker[1])
                        for ln in gb.lines:
                            for i in ln.gl:
                                glyphs[i].owner = lbl if i in marks else body
                                glyphs[i].line = ln
                    tops.append((it, lst))
                    continue
                k -= len(group) - 1     # (a lone numbered line: a paragraph)
            e = Elem("P", page.number, label=b.text)
            tops.append((it, e))
            _own(glyphs, b, e)
        elif it.kind == "table":
            t = it.obj
            tab = Elem("Table", page.number, sort=False)
            cells = {}
            for ri, row in enumerate(t["rows"]):
                tr_ = tab.add(Elem("TR", page.number, sort=False))
                for ci, _c in enumerate(row):
                    if ri == 0 and t["header"]:
                        cells[ri, ci] = tr_.add(Elem("TH", page.number,
                                                     attrs="<</O /Table /Scope /Column>>"))
                    else:
                        cells[ri, ci] = tr_.add(Elem("TD", page.number))
            for i, rc in t["glyphs"].items():
                glyphs[i].owner = cells[rc]
            tab.label = " ".join("".join(glyphs[i].c for i in sorted(
                (i for i, rc in t["glyphs"].items() if rc[0] == 0),
                key=lambda i: glyphs[i].x0)).split())[:60]
            tops.append((it, tab))
        elif it.kind == "figure":
            f = it.obj
            e = Elem("Figure", page.number, label=tr("Picture"))
            e.box = f["box"] if layout.turn is None else \
                tuple((pymupdf.Rect(f["box"]) * ~layout.turn).normalize())
            f["elem"] = e
            tops.append((it, e))
        else:
            xref, sub = it.obj
            e = Elem("Link" if sub == "Link" else "Form" if sub == "Widget" else "Annot",
                     page.number, label=sub)
            e.add(("objr", xref))
            plan.annots.append((xref, e))
            tops.append((it, e))
    rank_of = {}
    for it, e in tops:
        rank_of[id(e)] = it.rank
    # links over text: an element in the one that holds most of its characters
    for xref, sub, box in annots:
        inside = link_glyphs.get(xref)
        if not inside:
            continue
        owners = {}
        for i in inside:
            o = glyphs[i].owner
            if isinstance(o, Elem):
                owners[id(o)] = (owners.get(id(o), (0, o))[0] + 1, o)
        if not owners:
            e = Elem("Link", page.number, label=sub)
            e.add(("objr", xref))
            plan.annots.append((xref, e))
            tops.append((_Item(box, "annot", None), e))
            continue
        host = max(owners.values(), key=lambda t: t[0])[1]
        link = host.add(Elem("Link", page.number, label=""))
        for i in inside:
            if isinstance(glyphs[i].owner, Elem):
                glyphs[i].owner = link
        link.add(("objr", xref))
        plan.annots.append((xref, link))
    # every glyph's place in reading order
    item_rank = {}

    def mark(e, rank):
        item_rank[id(e)] = rank
        for kid in e.kids:
            if isinstance(kid, Elem):
                mark(kid, rank)
    for it, e in tops:
        mark(e, it.rank)
    for gl in glyphs:
        if isinstance(gl.owner, Elem):
            y = gl.line.y0 if gl.line is not None else gl.y0
            gl.key = (item_rank.get(id(gl.owner), 0), round(y, 1), gl.x0)
    figure_of = {id(f["piece"]): f.get("elem") for f in layout.figures}
    plan.content = _write(plan, layout, figure_of, item_rank)
    plan.elems = _finish(tops, plan.keys)
    return plan


def _own(glyphs, block, e):
    for ln in block.lines:
        for i in ln.gl:
            glyphs[i].owner = e
            glyphs[i].line = ln


def _whole_page(plan, layout, annots):
    """A page whose characters couldn't be matched with its content: all of it as one
    paragraph (when no artifact is marked in it already), its markups tagged."""
    r = layout.reader
    if layout.why == "tagged":
        plan.note = "tagged"
    elif any(k == "artifact" for p in r.pieces for k, _m, _s in p.mc) or \
            any(k == "mcid" for p in r.pieces for k, _m, _s in p.mc):
        plan.note = "left"
    elif r.data.strip() and r.pieces:
        e = Elem("P", layout.index, label=tr("Page {n}").format(n=layout.index + 1))
        e.kids.append(0)
        plan.parents = [e]
        plan.content = _bdc(e, 0) + r.data + b"\nEMC\n"
        plan.elems = [e]
        plan.note = "whole"
    for xref, sub, box in annots:
        e = Elem("Link" if sub == "Link" else "Form" if sub == "Widget" else "Annot",
                 layout.index, label=sub)
        e.add(("objr", xref))
        plan.annots.append((xref, e))
        plan.elems.append(e)


def _write(plan, layout, figure_of, item_rank):
    """The page's content with each run of content wrapped in its marked content; fills
    plan.parents (MCID -> element) and each element's MCIDs (with their keys)."""
    import bisect
    r = layout.reader
    data = r.data
    glyphs = layout.glyphs
    evpos = [p for p, _op in r.events]
    units = []                          # (start, end, owner, replacement, key)
    for p in r.pieces:
        if any(k == "artifact" for k, _m, _s in p.mc):
            continue                    # (marked as an artifact already)
        if p.kind == "text":
            if p.g1 <= p.g0:
                units.append((p.start, p.end, ART, None, None))
                continue
            owners = [glyphs[i].owner for i in range(p.g0, p.g1)]
            # spaces and unplaced characters go with the character before (or after)
            last = None
            for k, o in enumerate(owners):
                if o is None:
                    owners[k] = last
                else:
                    last = o
            nxt = None
            for k in range(len(owners) - 1, -1, -1):
                if owners[k] is None:
                    owners[k] = nxt
                else:
                    nxt = owners[k]
            if owners and owners[0] is None:
                prev = next((glyphs[i].owner for i in range(p.g0 - 1, -1, -1)
                             if glyphs[i].owner is not None), ART)
                owners = [prev] * len(owners)
            keys = {}
            for k, o in enumerate(owners):
                gk = glyphs[p.g0 + k].key
                if isinstance(o, Elem) and gk is not None:
                    if id(o) not in keys or gk < keys[id(o)]:
                        keys[id(o)] = gk
            parts = _split_show(p, data, owners)
            if len(parts) == 1:
                o = parts[0][0]
                units.append((p.start, p.end, o, None, keys.get(id(o))))
            else:
                for n, (o, b) in enumerate(parts):
                    if n == 0:
                        units.append((p.start, p.end, o, b, keys.get(id(o))))
                    else:
                        units.append((p.end, p.end, o, b, keys.get(id(o))))
            continue
        if p.kind == "form" and p.g1 > p.g0:
            count = {}
            for i in range(p.g0, p.g1):
                o = glyphs[i].owner
                if o is not None:
                    count[id(o)] = (count.get(id(o), (0, o))[0] + 1, o)
            o = max(count.values(), key=lambda t: t[0])[1] if count else ART
            key = min((glyphs[i].key for i in range(p.g0, p.g1) if glyphs[i].owner is o and
                       glyphs[i].key is not None), default=None) \
                if isinstance(o, Elem) else None
            units.append((p.start, p.end, o, None, key))
            continue
        fe = figure_of.get(id(p))
        if fe is not None:
            units.append((p.start, p.end, fe, None,
                          (item_rank.get(id(fe), 0), round(p.box[1], 1), p.box[0])))
        else:
            units.append((p.start, p.end, ART, None, None))
    out = []
    pos = 0
    cur = None                          # (owner, events before, mcid)
    last_end = 0
    keys = {}
    for start, end, owner, repl, key in units:
        ev = bisect.bisect_right(evpos, start)
        if cur is not None and (cur[0] is not owner or cur[1] != ev):
            out.append(data[pos:last_end])
            out.append(b"\nEMC\n")
            pos = last_end
            cur = None
        if cur is None:
            out.append(data[pos:start])
            pos = start
            mcid = None
            if isinstance(owner, Elem):
                mcid = len(plan.parents)
                plan.parents.append(owner)
                owner.kids.append(mcid)
            out.append(_bdc(owner, mcid))
            cur = (owner, ev, mcid)
        if cur[2] is not None and key is not None:
            if cur[2] not in keys or key < keys[cur[2]]:
                keys[cur[2]] = key
        if repl is not None:
            out.append(data[pos:start])
            out.append(b" " + repl + b" ")
            pos = end
        last_end = end
    if cur is not None:
        out.append(data[pos:last_end])
        out.append(b"\nEMC\n")
        pos = last_end
    out.append(data[pos:])
    plan.keys = keys
    return b"".join(out)


def _finish(tops, mkeys):
    """The page's top elements in reading order, each with its kids in order, empty ones
    left out (but a table's empty cells stay: they keep the grid)."""
    out = []
    for _it, e in sorted(tops, key=lambda t: t[0].rank):
        if _settle(e, mkeys):
            out.append(e)
    return out


def _settle(e, mkeys):
    """Put e's kids in reading order (when e.sort) and drop empty kids; e.key = its first
    content's place. Returns whether e holds anything."""
    kept = []
    for kid in e.kids:
        if isinstance(kid, Elem):
            if _settle(kid, mkeys) or kid.type in ("TD", "TH", "TR"):
                kept.append((kid.key, kid))
        elif isinstance(kid, int):
            kept.append((mkeys.get(kid), kid))
        else:
            kept.append((None, kid))
    if e.sort:
        kept.sort(key=lambda t: (t[0] is None, t[0] or ()))
    e.kids = [k for _key, k in kept]
    keys = [k for k, _kid in kept if k is not None]
    e.key = min(keys) if keys else None
    return bool(kept)


# ---- the whole document ----------------------------------------------------------------
class Stopped(Exception):
    pass


def is_tagged(doc):
    """Whether the document has a structure tree already."""
    cat = doc.pdf_catalog()
    return doc.xref_get_key(cat, "StructTreeRoot")[0] not in ("null",)


def make_plans(doc, step=None):
    """[PagePlan] for every page (read only: nothing changes). step(done, total) is called
    as pages are read (twice over: the survey, then the tags); it returns False to stop
    (then Stopped is raised)."""
    n = doc.page_count
    survey = Survey(n)
    keep = {}
    budget = 300000                     # glyphs kept between the two passes
    for i in range(n):
        if step is not None and step(i, 2 * n) is False:
            raise Stopped()
        lay = Layout(doc[i])
        survey.add(lay)
        if budget > 0:
            keep[i] = lay
            budget -= len(lay.glyphs)
    survey.finish()
    plans = []
    state = {}
    for i in range(n):
        if step is not None and step(n + i, 2 * n) is False:
            raise Stopped()
        page = doc[i]
        lay = keep.pop(i, None) or Layout(page)
        plans.append(plan_page(page, lay, survey, state))
    return plans


def _ref(x):
    return "%d 0 R" % x


def _pdf_box(page, box):
    """A box in the page as shown -> [x0 y0 x1 y1] in PDF user space."""
    to_pdf = ~(pdfcoords.to_page(page) * page.rotation_matrix)
    r = (pymupdf.Rect(box) * to_pdf).normalize()
    return "[%.2f %.2f %.2f %.2f]" % (r.x0, r.y0, r.x1, r.y1)


def apply(doc, plans, lang=None):
    """Write the plans: content, structure elements, the tree's root and parent tree, the
    catalog's /MarkInfo and /Lang, each page's /StructParents and /Tabs. Run it inside
    DocumentView.modify (one undo step). Returns the number of elements written."""
    from . import page_objects
    cat = doc.pdf_catalog()
    root = doc.get_new_xref()
    doc.update_object(root, "<</Type /StructTreeRoot>>")
    top = doc.get_new_xref()
    doc.update_object(top, "<</Type /StructElem /S /Document>>")
    nums = []
    key = 0
    tops = []
    count = [0]

    def alloc(e):
        e.xref = doc.get_new_xref()
        count[0] += 1
        for kid in e.kids:
            if isinstance(kid, Elem):
                alloc(kid)

    def write(e, parent, page):
        pg = page.xref
        kids = []
        for kid in e.kids:
            if isinstance(kid, Elem):
                write(kid, e.xref, page)
                kids.append(_ref(kid.xref))
            elif isinstance(kid, int):
                kids.append(str(kid))
            else:
                kids.append("<</Type /OBJR /Obj %s /Pg %s>>" % (_ref(kid[1]), _ref(pg)))
        extra = ""
        if e.alt is not None:
            extra += " /Alt " + pymupdf.get_pdf_str(e.alt)
        attrs = e.attrs
        if e.type == "Figure" and e.box is not None:
            attrs = "<</O /Layout /BBox %s>>" % _pdf_box(page, e.box)
        if attrs:
            extra += " /A " + attrs
        doc.update_object(e.xref, "<</Type /StructElem /S /%s /P %s /Pg %s /K [%s]%s>>" % (
            e.type, _ref(parent), _ref(pg), " ".join(kids), extra))

    for plan in plans:
        page = doc[plan.index]
        if plan.content is not None:
            page_objects._set_contents(page, plan.content)
        for e in plan.elems:
            alloc(e)
        for e in plan.elems:
            write(e, top, page)
            tops.append(e.xref)
        if plan.parents:
            doc.xref_set_key(page.xref, "StructParents", str(key))
            nums.append("%d [%s]" % (key, " ".join(_ref(e.xref) for e in plan.parents)))
            key += 1
        for xref, e in plan.annots:
            doc.xref_set_key(xref, "StructParent", str(key))
            nums.append("%d %s" % (key, _ref(e.xref)))
            key += 1
        doc.xref_set_key(page.xref, "Tabs", "/S")
    tree = doc.get_new_xref()
    doc.update_object(tree, "<</Nums [%s]>>" % " ".join(nums))
    doc.update_object(top, "<</Type /StructElem /S /Document /P %s /K [%s]>>" % (
        _ref(root), " ".join(_ref(x) for x in tops)))
    doc.update_object(root, "<</Type /StructTreeRoot /K %s /ParentTree %s "
                            "/ParentTreeNextKey %d>>" % (_ref(top), _ref(tree), key))
    doc.xref_set_key(cat, "StructTreeRoot", _ref(root))
    doc.xref_set_key(cat, "MarkInfo", "<</Marked true>>")
    if lang:
        doc.xref_set_key(cat, "Lang", pymupdf.get_pdf_str(lang))
    return count[0] + 1


def notes(plans):
    """What the user should know about pages tagged differently: [(page, text)]."""
    out = []
    for p in plans:
        if p.note == "whole":
            out.append((p.index, tr("The characters on this page couldn't be matched with "
                                    "its drawing instructions (an unusual font), so the page "
                                    "is tagged as one paragraph, in drawing order.")))
        elif p.note in ("left", "tagged"):
            out.append((p.index, tr("This page has marked content already, so it was left "
                                    "as it was (not tagged).")))
    return out


def counts(plans):
    """{"H", "P", "L", "Table", "Figure", "Annot" (links, fields, comments)}: how many of
    each the plans tag."""
    out = {"H": 0, "P": 0, "L": 0, "Table": 0, "Figure": 0, "Annot": 0}

    def walk(e):
        t = e.type
        if t.startswith("H") and t[1:].isdigit():
            out["H"] += 1
        elif t in ("P", "L", "Table", "Figure"):
            out[t] += 1
        elif t in ("Link", "Form", "Annot"):
            out["Annot"] += 1
        for k in e.kids:
            if isinstance(k, Elem):
                walk(k)
    for p in plans:
        for e in p.elems:
            walk(e)
    return out
