"""Edit objects: move, resize, rotate and delete the pictures and vector shapes that are part
of a page's own content (not markups), like Bluebeam's Edit content / PDF-XChange's Edit
objects.

The page's content stream is read once to find each object with the transformation in effect:
  picture: an image XObject drawn with "/Name Do", or an inline image (BI ... EI)
  shape:   a path (m l c v y h re ...) and the operator that paints it (S f B ...)
An edit rewrites only those drawing instructions:
  move / resize / rotate: wrapped as  q <M> cm <instructions> Q
  delete:                 removed
so objects keep their place in the drawing order (text drawn over a picture stays over it),
colors and line styles are untouched, and picture data is never decoded or re-encoded.
Clipping paths and objects inside Form XObjects aren't editable. Resizing a shape scales its
line width with it.
"""

import math
import re
import zlib

import pymupdf

from . import pdfcoords
from .i18n import tr

_TOKEN = re.compile(rb"\s+|%[^\r\n]*|/[^\s/\[\]()<>{}%]*|<<|>>|<[0-9A-Fa-f\s]*>|[\[\]{}]|"
                    rb"\(|[^\s/\[\]()<>{}%]+")
_WS = b" \t\r\n\f\x00"
_CONSTRUCT = {b"m": 2, b"l": 2, b"c": 6, b"v": 4, b"y": 4, b"re": 4, b"h": 0}
_PAINT = {b"S": (True, False), b"s": (True, False), b"f": (False, True), b"F": (False, True),
          b"f*": (False, True), b"B": (True, True), b"B*": (True, True), b"b": (True, True),
          b"b*": (True, True)}
# graphics state operators some producers write between a path and its paint operator
_STATE = {b"w", b"J", b"j", b"M", b"d", b"ri", b"i", b"gs", b"CS", b"cs", b"SC", b"SCN", b"sc",
          b"scn", b"G", b"g", b"RG", b"rg", b"K", b"k"}
CURVE_STEPS = 12
# graphics state that an object's look depends on, kept so it can be redrawn elsewhere in the
# drawing order (Bring to front / Send to back): category -> the operators that set it
_FILL = {b"g", b"rg", b"k", b"sc", b"scn"}
_STROKE = {b"G", b"RG", b"K", b"SC", b"SCN"}
_KEEP = {b"w", b"J", b"j", b"M", b"d", b"ri", b"i"}


def _new_state():
    return {"cs": [], "fill": [], "CS": [], "stroke": [], "keep": {}, "gs": []}


def _note(st, op, raw):
    """Record a graphics-state operator (its bytes) in st."""
    if op == b"cs":
        st["cs"], st["fill"] = [raw], []
    elif op == b"CS":
        st["CS"], st["stroke"] = [raw], []
    elif op in _FILL:
        if op in (b"g", b"rg", b"k"):
            st["cs"] = []
        st["fill"] = [raw]
    elif op in _STROKE:
        if op in (b"G", b"RG", b"K"):
            st["CS"] = []
        st["stroke"] = [raw]
    elif op in _KEEP:
        st["keep"][op] = raw
    elif op == b"gs":
        st["gs"].append(raw)


def _state_after(state, ops):
    """The state bytes after applying the operators in `ops` (bytes) to `state` (bytes from
    _state_bytes): how a full read would record an object whose own settings moved
    in front of it."""
    st = _new_state()
    for chunk in (state, ops):
        for op, _a, s_, e_ in _tokens(chunk):
            _note(st, op, chunk[s_:e_])
    return _state_bytes(st)


def _state_bytes(st):
    return b" ".join(st["cs"] + st["fill"] + st["CS"] + st["stroke"] +
                     [v for _k, v in sorted(st["keep"].items())] + st["gs"])


def _skip_string(data, i):
    """Index just past the literal string starting at data[i] == '('."""
    depth = 0
    n = len(data)
    while i < n:
        c = data[i]
        if c == 0x5C:                   # backslash: skip the escaped character
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
    """data[i:] is the inline image data after 'ID '. Index just past its 'EI'."""
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


def _tokens(data):
    """(operator, operands, start of operands, end) for each operator in a content stream.
    Inline images come as ("BI", [], start, end)."""
    operands = []
    i, n = 0, len(data)
    op_start = None
    match = _TOKEN.match
    while i < n:
        if data[i] == 0x28:             # "(" literal string
            if op_start is None:
                op_start = i
            i = _skip_string(data, i)
            operands.append(None)
            continue
        m = match(data, i)
        if m is None:
            i += 1
            continue
        tok = m.group()
        j = m.end()
        c = tok[0]
        if c in _WS or c == 0x25:
            i = j
            continue
        if c in b"/<[]{}" or (c in b"+-.0123456789" and _num(tok) is not None):
            if op_start is None:
                op_start = i
            operands.append(tok)
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
            yield tok, operands, start, j
        operands = []
        op_start = None
        i = j


def scan(data):
    """Objects in a content stream, in drawing order. Each is a dict with "start", "end"
    (byte range of its drawing instructions), "ctm" (Matrix to PDF space) and either
    "name" (b"/Im1" for Do, None for an inline image) or "path": True with "box" (content
    space bounds), "stroke", "fill" and "width". "ctx" is (the marked content around it,
    the clipping paths in effect, by their number in the stream): two objects with the same
    one are drawn under the same clip, in the same layer."""
    out = []
    for _ in scan_steps(data, out):
        pass
    return out


STEP = 1000                             # instructions read between two pauses (scan_steps)


def scan_steps(data, out):
    """scan() a little at a time: a generator that fills out, pausing (yield) every STEP
    instructions, so a big drawing can be read in idle time without freezing the window."""
    count = 0
    ctm = pymupdf.Matrix(1, 0, 0, 1, 0, 0)
    width = 1.0
    stack = []
    st = _new_state()
    bdc, clips, nclip = [], [], 0
    ctx = ((), ())

    def copy(s):
        return {k: (dict(v) if isinstance(v, dict) else list(v)) for k, v in s.items()}

    def note(op, start, end):
        _note(st, op, data[start:end])
    path_start = None
    path_state = None
    path_ctx = ctx
    clip = False
    xs, ys = [], []
    for op, args, start, end in _tokens(data):
        count += 1
        if count >= STEP:
            count = 0
            yield
        if op in _CONSTRUCT:
            if path_start is None:
                path_start = start
                path_state = None
                path_ctx = ctx
                clip = False
                xs, ys = [], []
            k = _CONSTRUCT[op]
            vals = [_num(t) for t in args[-k:]] if k else []
            if k and (len(args) < k or None in vals):
                continue
            if op == b"re":
                x, y, w, h = vals
                xs += [x, x + w]
                ys += [y, y + h]
            else:
                xs += vals[0::2]
                ys += vals[1::2]
            continue
        if op in (b"W", b"W*"):
            clip = True
            clips.append(nclip)
            nclip += 1
            ctx = (ctx[0], tuple(clips))
            continue
        if path_start is not None and op in _STATE:
            if op == b"w" and args:
                width = _num(args[-1]) or 0.0
            if path_state is None:
                path_state = _state_bytes(st)      # the state the path started with
            note(op, start, end)
            continue
        if path_start is not None:
            if op in _PAINT and not clip and xs:
                stroke, fill = _PAINT[op]
                out.append({"start": path_start, "end": end, "ctm": pymupdf.Matrix(ctm),
                            "path": True, "box": (min(xs), min(ys), max(xs), max(ys)),
                            "stroke": stroke, "fill": fill, "width": width,
                            "state": path_state if path_state is not None
                            else _state_bytes(st), "ctx": path_ctx})
            path_start = None
            if op in _PAINT or op == b"n":
                continue
        note(op, start, end)
        if op == b"q":
            stack.append((ctm, width, copy(st), len(clips)))
        elif op == b"Q":
            if stack:
                ctm, width, st, k = stack.pop()
                if len(clips) > k:
                    del clips[k:]
                    ctx = (ctx[0], tuple(clips))
        elif op in (b"BDC", b"BMC"):
            bdc.append(data[start:end])
            ctx = (tuple(bdc), ctx[1])
        elif op == b"EMC":
            if bdc:
                bdc.pop()
                ctx = (tuple(bdc), ctx[1])
        elif op == b"cm" and len(args) >= 6:
            vals = [_num(t) for t in args[-6:]]
            if None not in vals:
                ctm = pymupdf.Matrix(*vals) * ctm
        elif op == b"w" and args:
            width = _num(args[-1]) or 0.0
        elif op == b"Do" and args and isinstance(args[-1], bytes) and args[-1][:1] == b"/":
            out.append({"start": start, "end": end, "ctm": pymupdf.Matrix(ctm),
                        "name": args[-1], "state": _state_bytes(st), "ctx": ctx})
        elif op == b"BI":
            out.append({"start": start, "end": end, "ctm": pymupdf.Matrix(ctm), "name": None,
                        "state": _state_bytes(st), "ctx": ctx})


def _bezier(p0, p1, p2, p3):
    pts = []
    for i in range(1, CURVE_STEPS + 1):
        t = i / CURVE_STEPS
        u = 1 - t
        pts.append(p0 * (u ** 3) + p1 * (3 * u * u * t) + p2 * (3 * u * t * t) + p3 * (t ** 3))
    return pts


_OPS = set(_CONSTRUCT) | set(_PAINT) | _STATE | {b"n", b"W", b"W*"}


def _path_tokens(raw):
    """[(operator, [operand bytes], raw bytes)] of a shape's instructions, by splitting at
    spaces: several times quicker than _tokens for the plain numbers and operators a drawing's
    lines are made of. None when the bytes have anything that needs the full reader (strings,
    hex, dictionaries, comments, an unknown operator)."""
    if b"(" in raw or b"<" in raw or b"%" in raw:
        return None
    out, args = [], []
    for t in raw.split():
        if t in _OPS:
            out.append((t, args, b" ".join(args + [t])))
            args = []
        elif t[:1].isalpha() and t not in (b"true", b"false", b"null"):
            return None                 # an operator this shortcut doesn't know
        else:
            args.append(t)
    return out


def _quick_entry(piece):
    """scan() of a piece that is one plain shape (state settings, path, paint), worked out
    from _path_tokens: (entry, its own state settings), or None when it isn't one."""
    toks = _path_tokens(piece)
    if toks is None or not toks or toks[-1][0] not in _PAINT:
        return None
    xs, ys, own = [], [], []
    width = None
    start = None
    at = 0
    last = len(toks) - 1
    for k_, (op, args, raw) in enumerate(toks):
        i = piece.find(raw, at)
        if i < 0:
            return None
        at = i + len(raw)
        if op in _STATE:
            own.append(raw)
            if op == b"w" and args:
                width = _num(args[-1])
            continue
        if op in _PAINT:
            if k_ != last:
                return None             # (more than one shape)
            continue
        k = _CONSTRUCT.get(op)
        if k is None:
            return None                 # (a clip, n...: not one plain shape)
        if start is None:
            start = i
        vals = [_num(t) for t in args[-k:]] if k else []
        if k and (len(args) < k or None in vals):
            return None
        if op == b"re":
            x, y, w, h = vals
            xs += [x, x + w]
            ys += [y, y + h]
        else:
            xs += vals[0::2]
            ys += vals[1::2]
    if start is None or not xs:
        return None
    stroke, fill = _PAINT[toks[-1][0]]
    entry = {"start": start, "end": at, "ctm": pymupdf.Matrix(1, 0, 0, 1, 0, 0), "path": True,
             "box": (min(xs), min(ys), max(xs), max(ys)), "stroke": stroke, "fill": fill,
             "width": 1.0 if width is None else width}
    return entry, b" ".join(own)


def _bezier_xy(p0, p1, p2, p3):
    """_bezier on plain (x, y) pairs (much quicker than pymupdf Points for big drawings)."""
    out = []
    for i in range(1, CURVE_STEPS + 1):
        t = i / CURVE_STEPS
        u = 1 - t
        a, b, c, d = u * u * u, 3 * u * u * t, 3 * u * t * t, t * t * t
        out.append((p0[0] * a + p1[0] * b + p2[0] * c + p3[0] * d,
                    p0[1] * a + p1[1] * b + p2[1] * c + p3[1] * d))
    return out


def path_lines(data, obj, tm):
    """A shape's outline as polylines in page coordinates: [[Point, ...], ...]."""
    mat = obj["ctm"] * tm
    ma, mb, mc, md, me, mf = mat.a, mat.b, mat.c, mat.d, mat.e, mat.f
    out = []
    cur = None
    first = last = None
    Point = pymupdf.Point
    raw = data[obj["start"]:obj["end"]]
    toks = _path_tokens(raw)
    if toks is None:
        toks = [(op, args, None) for op, args, _s, _e in _tokens(raw)]
    for op, args, _raw in toks:
        k = _CONSTRUCT.get(op)
        if k is None:
            if op in (b"s", b"b", b"b*") and cur and first is not None and cur[-1] != first:
                cur.append(first)       # (these paint operators close the last subpath)
            continue
        vals = [_num(t) for t in args[-k:]] if k else []
        if k and (len(args) < k or None in vals):
            continue
        if op == b"m":
            first = last = (vals[0], vals[1])
            cur = [first]
            out.append(cur)
        elif op == b"re":
            x, y, w, h = vals
            out.append([(x, y), (x + w, y), (x + w, y + h), (x, y + h), (x, y)])
            cur = None
            first = last = (x, y)
        elif cur is None:
            continue
        elif op == b"l":
            last = (vals[0], vals[1])
            cur.append(last)
        elif op == b"c":
            cur += _bezier_xy(last, vals[0:2], vals[2:4], vals[4:6])
            last = (vals[4], vals[5])
        elif op == b"v":
            cur += _bezier_xy(last, last, vals[0:2], vals[2:4])
            last = (vals[2], vals[3])
        elif op == b"y":
            cur += _bezier_xy(last, vals[0:2], vals[2:4], vals[2:4])
            last = (vals[2], vals[3])
        elif op == b"h" and first is not None:
            cur.append(first)
            last = first
    return [[Point(x * ma + y * mc + me, x * mb + y * md + mf) for x, y in line]
            for line in out]


def _form_box(doc, xref):
    """(BBox, Matrix) of a Form XObject, or (None, None) when it has no usable BBox."""
    def nums(key):
        kind, val = doc.xref_get_key(xref, key)
        if kind != "array":
            return None
        try:
            return [float(v) for v in val.strip("[]").split()]
        except ValueError:
            return None
    b = nums("BBox")
    if not b or len(b) != 4:
        return None, None
    m = nums("Matrix")
    fm = pymupdf.Matrix(*m) if m and len(m) == 6 else pymupdf.Matrix(1, 0, 0, 1, 0, 0)
    box = pymupdf.Rect(b).normalize()
    return (box, fm) if not box.is_empty else (None, None)


def _contents(page):
    doc = page.parent
    return b"\n".join(doc.xref_stream(x) or b"" for x in page.get_contents())


def _put_stream(doc, xref, data):
    """Write stream xref deflated quickly (zlib level 1): MuPDF's own compression packs it
    tighter but took two seconds for a big CAD sheet's 7 MB drawing, and left uncompressed
    the drawing made every undo step about four times bigger."""
    doc.update_stream(xref, zlib.compress(data, 1), compress=False)
    doc.xref_set_key(xref, "Filter", "/FlateDecode")     # (update_stream took it away)
    # Save packs it tightly again (see pack_quick_streams): Save's own deflate leaves alone a
    # stream already compressed, and files saved after a CAD edit came out up to half bigger
    doc.xref_set_key(xref, QUICK_KEY, "true")
    quick = getattr(doc, "_kz_quick", None)
    if quick is None:
        quick = doc._kz_quick = set()
    quick.add(xref)


QUICK_KEY = "KZQuick"


def pack_quick_streams(doc):
    """Compress tightly (MuPDF's deflate) the streams _put_stream wrote quickly, before a
    Save: about a second for a big sheet's drawing, paid once when saving, not on each
    edit. doc._kz_quick: the xrefs written so (carried from document to document by undo
    and redo); each is checked for the mark, so one that changed since is left alone."""
    for x in sorted(getattr(doc, "_kz_quick", ()) or ()):
        try:
            if x >= doc.xref_length() or doc.xref_get_key(x, QUICK_KEY)[1] != "true" or \
                    not doc.xref_is_stream(x):
                continue
            data = doc.xref_stream(x)
            doc.update_stream(x, data, compress=True)
            doc.xref_set_key(x, QUICK_KEY, "null")
        except Exception:
            continue                    # (left as it is: still a valid, compressed stream)
    # (the list stays: an undo after this Save brings back streams written quickly)


def _set_contents(page, data):
    """Give the page one new content stream (never edits a stream another page may share)."""
    doc = page.parent
    # The stream an earlier edit wrote for this page is written over (a new one each time
    # left every old drawing in the file: an undo step on a big sheet carried all of them)
    # when no other page uses it.
    x = _own_stream(doc, page)
    if x is None:
        x = doc.get_new_xref()
        doc.update_object(x, "<</KzPage %d>>" % page.xref)
    _put_stream(doc, x, data)
    page.set_contents(x)


def _own_stream(doc, page):
    """The page's one content stream when an edit here wrote it for this page and no other
    page shows it, else None."""
    kind, val = doc.xref_get_key(page.xref, "Contents")
    if kind != "xref":
        return None
    x = int(val.split()[0])
    if doc.xref_get_key(x, "KzPage") != ("int", str(page.xref)):
        return None
    for i in range(doc.page_count):
        px = doc.page_xref(i)
        if px != page.xref and doc.xref_get_key(px, "Contents")[1].split()[:1] == [str(x)]:
            return None                 # (shared, as a copied page can be)
    return x


class _Shape(dict):
    """A shape item: its "quad" is worked out when first asked for (most never are; making
    one for each of 100,000 lines took seconds)."""

    def __missing__(self, key):
        if key != "quad":
            raise KeyError(key)
        x0, y0, x1, y1 = self["obj"]["box"]
        q = pymupdf.Rect(x0, y0, x1, y1).quad.transform(self["obj"]["ctm"] * self["_tm"])
        self["quad"] = q
        return q


def _mul(m, n):
    """m x n of (a, b, c, d, e, f) tuples, as pymupdf.Matrix does it (m first, then n)."""
    return (m[0] * n[0] + m[1] * n[2], m[0] * n[1] + m[1] * n[3],
            m[2] * n[0] + m[3] * n[2], m[2] * n[1] + m[3] * n[3],
            m[4] * n[0] + m[5] * n[2] + n[4], m[4] * n[1] + m[5] * n[3] + n[5])


def _inv(m):
    a, b, c, d, e, f = m
    det = a * d - b * c
    return (d / det, -b / det, -c / det, a / det, (c * f - d * e) / det, (b * e - a * f) / det)


class Objects:
    """The editable objects of one page, read once (cache it until the page changes)."""

    def __init__(self, page, data=None, found=None, reuse=None):
        """data / found: the page's content and its scan when the caller already has them
        (after a move: see transform), so a big drawing isn't read again. reuse: {number in
        found: the shape item it had before an edit that left it as it was} (see _rebuilt)."""
        for _ in self.build_steps(page, data, found, reuse):
            pass

    @classmethod
    def steps(cls, page):
        """(the Objects, a generator that reads them a little at a time): they're ready once
        it's run out (CAD mode reads a big page in idle time like this)."""
        objs = cls.__new__(cls)
        return objs, objs.build_steps(page, None, None)

    def build_steps(self, page, data, found, reuse=None):
        self.data = _contents(page) if data is None else data
        self.tm = pdfcoords.to_page(page)
        self.items = []
        self.found = []
        if not self.data.strip():
            return
        if found is None:
            found = []
            yield from scan_steps(self.data, found)
        self.found = found
        names = {}
        for it in page.get_images(full=True):
            if it[-1] == 0:             # drawn by the page itself, not inside a form
                names[("/" + it[7]).encode()] = it[0]
        # drawing groups (Form XObjects) the page places itself: flattened markups and stamps
        # become these, and other PDF editors (Acrobat's Edit PDF, PDF-XChange's Edit
        # Content) select and move them as one object, so Edit objects does too
        groups = {}
        doc = page.parent
        for gx in page.get_xobjects():
            xref, gname, invoker = gx[0], gx[1], gx[2]
            if invoker != 0:
                continue
            groups[("/" + gname).encode()] = (xref, _form_box(doc, xref))
        page_area = abs(page.rect) or 1
        tm = self.tm
        tt = tuple(tm)
        Rect = pymupdf.Rect
        reuse = reuse or {}
        for k, d in enumerate(self.found):
            if k % STEP == STEP - 1:
                yield
            old = reuse.get(k)
            if old is not None:
                # the same shape, only further along in the drawing: its box and outline
                # stay (working them out again took a second on a 200,000-line sheet)
                it = _Shape(old)
                it["n"] = k
                it["obj"] = d
                self.items.append(it)
                continue
            if d.get("path"):
                # plain arithmetic: a big drawing has tens of thousands of these
                a, b, c, e_, e, f = _mul(tuple(d["ctm"]), tt)
                det = a * e_ - b * c
                if abs(det) < 1e-12:
                    continue
                x0, y0, x1, y1 = d["box"]
                xs = (x0 * a + y0 * c + e, x1 * a + y0 * c + e, x0 * a + y1 * c + e,
                      x1 * a + y1 * c + e)
                ys = (x0 * b + y0 * e_ + f, x1 * b + y0 * e_ + f, x0 * b + y1 * e_ + f,
                      x1 * b + y1 * e_ + f)
                self.items.append(_Shape({"n": k, "kind": "shape",
                                          "rect": Rect(min(xs), min(ys), max(xs), max(ys)),
                                          "xref": 0, "stroke": d["stroke"], "fill": d["fill"],
                                          "width": d["width"] * math.sqrt(abs(det)), "obj": d,
                                          "_tm": tm}))
                continue
            m = d["ctm"] * tm
            if abs(m.a * m.d - m.b * m.c) < 1e-12:
                continue
            if d["name"] is not None and d["name"] in groups:
                gxref, (box, fm) = groups[d["name"]]
                if box is None:
                    continue
                quad = box.quad.transform(fm * m)
                self.items.append({"n": k, "kind": "group", "rect": quad.rect, "xref": gxref,
                                   "quad": quad, "obj": d,
                                   # a group filling the page (some programs wrap the whole
                                   # drawing in one) is picked by a selection box, not by a
                                   # click anywhere on the sheet
                                   "whole": abs(quad.rect) >= 0.9 * page_area})
                continue
            if d["name"] is None:
                xref = 0
            else:
                xref = names.get(d["name"])
                if xref is None:
                    continue            # something else, not a picture
            quad = pymupdf.Rect(0, 0, 1, 1).quad.transform(m)
            self.items.append({"n": k, "kind": "picture", "rect": quad.rect, "xref": xref,
                               "quad": quad, "obj": d})

    def lines(self, item):
        """A shape's outline (cached), or the picture's outline."""
        if "lines" not in item:
            if item["kind"] == "shape":
                item["lines"] = path_lines(self.data, item["obj"], self.tm)
            else:
                q = item["quad"]
                item["lines"] = [[q.ul, q.ur, q.lr, q.ll, q.ul]]
        return item["lines"]

    def tight(self, item):
        """The box around a shape's line as drawn (its "rect" holds a curve's control
        points too)."""
        if "tight" not in item:
            pts = [q for line in self.lines(item) for q in line]
            item["tight"] = pymupdf.Rect(min(q.x for q in pts), min(q.y for q in pts),
                                         max(q.x for q in pts), max(q.y for q in pts)) \
                if pts else item["rect"]
        return item["tight"]

    def at_index(self):
        """The lookup at() finds the objects near a point with (made once)."""
        from . import hit_index
        near = getattr(self, "_at_index", None)
        if near is None or near.size != len(self.items):
            near = self._at_index = hit_index.BoxIndex(
                (it["rect"] for it in self.items),
                [it.get("width", 0) / 2 for it in self.items])
            self._segments = {}
        return near

    def at(self, pt, tol):
        """The topmost object at page point pt: a line within tol of it first, then a filled
        shape or picture under it."""
        pt = pymupdf.Point(pt)
        filled = None
        items = self.items
        # only the objects whose box is near: a quick lookup made once (going through all
        # of a big drawing's objects took 40 ms on each mouse move)
        for it in (items[i] for i in reversed(self.at_index().near(pt.x, pt.y, tol))):
            r = it["rect"]
            pad = tol + it.get("width", 0) / 2
            if not (r.x0 - pad <= pt.x <= r.x1 + pad and r.y0 - pad <= pt.y <= r.y1 + pad):
                continue
            if it["kind"] in ("picture", "group"):
                if pt in it["quad"] and filled is None and not it.get("whole"):
                    filled = it
                continue
            lines = self.lines(it)
            if sum(len(line) for line in lines) > 64:
                # a long line (a contour, a hatch): all its pieces at once
                segs = self._segments.get(it["n"])
                if segs is None or segs.lines is not lines:
                    from .hit_index import Segments
                    segs = self._segments[it["n"]] = Segments(lines)
                if segs.near(pt, pad):
                    return it
            elif any(_near(line, pt, pad) for line in lines):
                return it
            if it["fill"] and filled is None and _inside(lines, pt):
                filled = it
        return filled

    def inside(self, box):
        """Objects lying entirely inside box."""
        box = pymupdf.Rect(box)
        return [it for it in self.items if box.contains(it["rect"]) or (
            it["kind"] == "shape" and overlap(it["rect"], box) and box.contains(self.tight(it)))]

    def pick(self, region, crossing=False):
        """Objects a CAD selection region (Box or Lasso) takes. A window (crossing False)
        takes the ones lying entirely inside it; a crossing region also the ones it touches:
        a line running through it, a filled shape or a picture it is on. A group filling the
        page is only taken whole (inside a window)."""
        return [it for it, taken in self.pick_steps(region, crossing) if taken]

    def pick_steps(self, region, crossing=False):
        """pick() one object at a time: (item, taken) for each object it looks at, so the live
        highlight can do a little at a time (reading a big drawing's lines takes a while)."""
        bounds = region.bounds
        for it in self.items:
            r = it["rect"]
            if not overlap(r, bounds):
                continue
            pic = it["kind"] in ("picture", "group")
            if not crossing and not (bounds.x0 <= r.x0 and r.x1 <= bounds.x1 and
                                     bounds.y0 <= r.y0 and r.y1 <= bounds.y1):
                if pic:
                    continue            # (can't lie inside: no need to read its lines)
                # a curve's box holds its control points, which can stick out well past the
                # curve itself: what counts is the line as drawn
                r = self.tight(it)
                if not (bounds.x0 <= r.x0 and r.x1 <= bounds.x1 and
                        bounds.y0 <= r.y0 and r.y1 <= bounds.y1):
                    continue
            if region.contains_rect(r) or not pic and not isinstance(region, Box) and \
                    region.contains_lines(self.lines(it)):
                yield it, True
            elif not crossing or it.get("whole"):
                yield it, False
            elif pic:
                q = it["quad"]
                yield it, (region.touches_lines([[q.ul, q.ur, q.lr, q.ll, q.ul]]) or
                           pymupdf.Point(region.inner_point()) in q)
            else:
                yield it, (region.touches_lines(self.lines(it)) or bool(
                    it["fill"] and _inside(self.lines(it),
                                           pymupdf.Point(region.inner_point()))))


def bounding(rects):
    """The box around rects. Not Rect() |= ...: PyMuPDF joins a flat box (a straight
    horizontal or vertical line's) as if it were empty."""
    x0 = y0 = float("inf")
    x1 = y1 = float("-inf")
    for r in rects:
        x0, y0 = min(x0, r[0], r[2]), min(y0, r[1], r[3])
        x1, y1 = max(x1, r[0], r[2]), max(y1, r[1], r[3])
    return pymupdf.Rect(x0, y0, x1, y1) if x0 <= x1 else pymupdf.Rect()


def overlap(a, b):
    """Rects a and b share a point (also a level or plumb line's empty rect)."""
    return a.x0 <= b.x1 and b.x0 <= a.x1 and a.y0 <= b.y1 and b.y0 <= a.y1


class Box:
    """A rectangular CAD selection region (window or crossing box)."""

    def __init__(self, rect):
        self.bounds = pymupdf.Rect(rect).normalize()

    def inner_point(self):
        b = self.bounds
        return ((b.x0 + b.x1) / 2, (b.y0 + b.y1) / 2)

    def contains_point(self, p):
        b = self.bounds
        return b.x0 <= p[0] <= b.x1 and b.y0 <= p[1] <= b.y1

    def contains_rect(self, r):
        b = self.bounds
        return b.x0 <= r.x0 and r.x1 <= b.x1 and b.y0 <= r.y0 and r.y1 <= b.y1

    def contains_lines(self, lines):
        return all(self.contains_point(p) for line in lines for p in line)

    def touches_rect(self, r):
        return overlap(pymupdf.Rect(r), self.bounds)

    def touches_lines(self, lines):
        return lines_meet(lines, self.bounds)


class Lasso:
    """A freehand CAD selection region (its outline closes back to its start). Its edges are
    sorted into a grid of cells and horizontal bands, so a test only looks at the edges near
    it (a crossing lasso over a 100,000-line sheet is redrawn while the pointer moves)."""
    CELLS = 24

    def __init__(self, points):
        self.pts = [(float(p[0]), float(p[1])) for p in points]
        xs = [p[0] for p in self.pts]
        ys = [p[1] for p in self.pts]
        self.bounds = pymupdf.Rect(min(xs), min(ys), max(xs), max(ys))
        self.edges = list(zip(self.pts, self.pts[1:] + self.pts[:1]))
        b = self.bounds
        self._cw = max(b.width, 1e-6) / self.CELLS
        self._ch = max(b.height, 1e-6) / self.CELLS
        self._grid = {}
        self._rows = [[] for _ in range(self.CELLS)]
        for e in self.edges:
            (x0, y0), (x1, y1) = e
            c0, c1 = self._col(min(x0, x1)), self._col(max(x0, x1))
            r0, r1 = self._row(min(y0, y1)), self._row(max(y0, y1))
            for r in range(r0, r1 + 1):
                self._rows[r].append(e)
                for c in range(c0, c1 + 1):
                    self._grid.setdefault((c, r), []).append(e)

    def _col(self, x):
        return max(0, min(self.CELLS - 1, int((x - self.bounds.x0) / self._cw)))

    def _row(self, y):
        return max(0, min(self.CELLS - 1, int((y - self.bounds.y0) / self._ch)))

    def inner_point(self):
        return self.pts[0]

    def contains_point(self, p):
        if not (self.bounds.x0 <= p[0] <= self.bounds.x1 and
                self.bounds.y0 <= p[1] <= self.bounds.y1):
            return False
        hit = False
        x, y = p[0], p[1]
        for (x0, y0), (x1, y1) in self._rows[self._row(y)]:
            if (y0 > y) != (y1 > y) and x < x0 + (y - y0) * (x1 - x0) / (y1 - y0):
                hit = not hit
        return hit

    def _cuts(self, a, b):
        """Segment ab crosses the lasso's outline."""
        lo_x, hi_x = min(a[0], b[0]), max(a[0], b[0])
        lo_y, hi_y = min(a[1], b[1]), max(a[1], b[1])
        if hi_x < self.bounds.x0 or lo_x > self.bounds.x1 or hi_y < self.bounds.y0 or \
                lo_y > self.bounds.y1:
            return False
        c0, c1 = self._col(lo_x), self._col(hi_x)
        r0, r1 = self._row(lo_y), self._row(hi_y)
        seen = set()
        for r in range(r0, r1 + 1):
            for c in range(c0, c1 + 1):
                for e in self._grid.get((c, r), ()):
                    if id(e) in seen:
                        continue
                    seen.add(id(e))
                    (cx, cy), (dx, dy) = e
                    if max(cx, dx) < lo_x or min(cx, dx) > hi_x or \
                            max(cy, dy) < lo_y or min(cy, dy) > hi_y:
                        continue
                    if _segments_cross(a, b, e[0], e[1]):
                        return True
        return False

    def contains_lines(self, lines):
        pts = [p for line in lines for p in line]
        if not pts or not all(self.contains_point(p) for p in pts):
            return False
        return not any(self._cuts(a, b) for line in lines for a, b in zip(line, line[1:]))

    def touches_lines(self, lines):
        for line in lines:
            if line and self.contains_point(line[0]):
                return True
            if any(self._cuts(a, b) for a, b in zip(line, line[1:])):
                return True
        return False

    def contains_rect(self, r):
        r = pymupdf.Rect(r)
        return self.contains_lines([[r.tl, r.tr, r.br, r.bl, r.tl]])

    def touches_rect(self, r):
        r = pymupdf.Rect(r)
        if self.touches_lines([[r.tl, r.tr, r.br, r.bl, r.tl]]):
            return True
        return any(r.x0 <= p[0] <= r.x1 and r.y0 <= p[1] <= r.y1 for p in self.pts[:1])


def _segments_cross(a, b, c, d):
    """Segments ab and cd meet."""
    def orient(p, q, r):
        v = (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
        return (v > 1e-12) - (v < -1e-12)

    def on(p, q, r):
        return min(p[0], r[0]) - 1e-9 <= q[0] <= max(p[0], r[0]) + 1e-9 and \
            min(p[1], r[1]) - 1e-9 <= q[1] <= max(p[1], r[1]) + 1e-9
    o1, o2, o3, o4 = orient(a, b, c), orient(a, b, d), orient(c, d, a), orient(c, d, b)
    if o1 != o2 and o3 != o4:
        return True
    return (o1 == 0 and on(a, c, b)) or (o2 == 0 and on(a, d, b)) or \
        (o3 == 0 and on(c, a, d)) or (o4 == 0 and on(c, b, d))


def segment_meets(a, b, box):
    """The straight line from point a to point b passes through (or touches) rect box."""
    x0, y0, x1, y1 = box.x0, box.y0, box.x1, box.y1
    t0, t1 = 0.0, 1.0
    dx, dy = b[0] - a[0], b[1] - a[1]
    for p, q in ((-dx, a[0] - x0), (dx, x1 - a[0]), (-dy, a[1] - y0), (dy, y1 - a[1])):
        if p == 0:
            if q < 0:
                return False
        else:
            t = q / p
            if p < 0:
                t0 = max(t0, t)
            else:
                t1 = min(t1, t)
            if t0 > t1:
                return False
    return True


def lines_meet(lines, box):
    """Any segment of these polylines passes through rect box."""
    for line in lines:
        if len(line) == 1 and pymupdf.Point(line[0]) in box:
            return True
        for a, b in zip(line, line[1:]):
            if segment_meets(a, b, box):
                return True
    return False


def _near(line, p, tol):
    t2 = tol * tol
    for a, b in zip(line, line[1:]):
        dx, dy = b.x - a.x, b.y - a.y
        L = dx * dx + dy * dy
        t = 0.0 if L == 0 else max(0.0, min(1.0, ((p.x - a.x) * dx + (p.y - a.y) * dy) / L))
        ex, ey = a.x + t * dx - p.x, a.y + t * dy - p.y
        if ex * ex + ey * ey <= t2:
            return True
    return False


def _inside(lines, p):
    """Even-odd point in polygon over all subpaths."""
    hit = False
    for line in lines:
        for a, b in zip(line, line[1:] + line[:1]):
            if (a.y > p.y) != (b.y > p.y):
                x = a.x + (p.y - a.y) * (b.x - a.x) / (b.y - a.y)
                if x > p.x:
                    hit = not hit
    return hit


# ---- edits ---------------------------------------------------------------------------
def _edit(page, ns, new, objs=None):
    """Replace the drawing instructions of objects ns with new(old_bytes, ctm). objs: the
    page's Objects when the caller has them (saves reading a big drawing again)."""
    data = _contents(page)
    have = objs is not None and objs.found and objs.data == data
    found = objs.found if have else scan(data)
    pieces = []
    for n in sorted(set(ns), reverse=True):
        if n >= len(found):
            raise ValueError(tr("The object is no longer on the page."))
        d = found[n]
        pieces.append((d["start"], d["end"], new(data[d["start"]:d["end"]], d["ctm"]), n))
    new_data = _splice(data, pieces)
    _set_contents(page, new_data)
    if not have:
        return None
    # the new scan: what was rewritten is scanned on its own, in its place and matrix
    by_n = {p[3]: p for p in pieces}
    out, origin, shift = [], [], 0
    for n, d in enumerate(found):
        p = by_n.get(n)
        if p is None:
            e = dict(d)
            e["start"] += shift
            e["end"] += shift
            out.append(e)
            origin.append((n, None))
            continue
        s_, e_, piece, _n = p
        quick = _quick_entry(piece)
        if quick is not None:
            entries, own = [quick[0]], quick[1]
        else:
            entries, own = scan(piece), _split(piece)[0]
        for x in entries:
            x = dict(x)
            x["start"] += s_ + shift
            x["end"] += s_ + shift
            x["ctm"] = x["ctm"] * d["ctm"]
            x["ctx"] = d.get("ctx")     # (a piece has no clipping or marked content)
            x["state"] = _state_after(d.get("state", b""), own) if own else d.get("state", b"")
            if x.get("path"):
                x["width"] = d.get("width", x["width"])
            out.append(x)
            origin.append(None)
        shift += len(piece) - (e_ - s_)
    return _rebuilt(page, new_data, out, objs, origin)


def _split(old):
    """A shape's instructions -> (graphics state settings, path and paint operators), so a
    wrap or delete leaves the state settings in effect for what's drawn after it."""
    state, path = [], []
    for op, _a, s_, e_ in _tokens(old):
        (state if op in _STATE else path).append(old[s_:e_])
    return b" ".join(state), b" ".join(path)


_WRAP = re.compile(rb"\nq ((?:-?[\d.]+ ){6})cm\n$")


def transform(page, ns, t_page, objs=None):
    """Apply t_page (a Matrix in unrotated page coordinates) to objects ns. An object this
    module moved before already sits in a  q <M> cm ... Q  wrapper: the new move is folded
    into that one matrix, so nudging a shape a hundred times doesn't nest a hundred
    wrappers.

    objs: the page's Objects (already read) to reuse instead of reading the drawing again.
    Returns the page's new Objects, updated in place of a second full read (None when it
    can't be: then read it again)."""
    tm = pdfcoords.to_page(page)
    t_pdf = tm * t_page * ~tm
    data = _contents(page)
    if objs is not None and objs.found and objs.data == data:
        found = objs.found
    else:
        found = scan(data)
    pieces = []
    tp = tuple(t_pdf)
    for n in sorted(set(ns), reverse=True):
        if n >= len(found):
            raise ValueError(tr("The object is no longer on the page."))
        d = found[n]
        s, e, ctm = d["start"], d["end"], d["ctm"]
        c = tuple(ctm)
        m = _mul(_mul(c, tp), _inv(c))              # the move, in the object's own space
        old = data[s:e]
        w = _WRAP.search(data, max(0, s - 120), s)
        if w and w.end() == s and data[e:e + 3] == b"\nQ\n":
            outer = pymupdf.Matrix(*[float(v) for v in w.group(1).split()])
            head = b"\nq %.6f %.6f %.6f %.6f %.4f %.4f cm\n" % _mul(m, tuple(outer))
            # the object's matrix becomes (written wrapper) x (what was under the old one)
            pieces.append((w.start(), e + 3, head + old + b"\nQ\n", n, len(head), len(old),
                           _written(head) * ~outer, b""))
            continue
        state, body = _split(old) if old[:2] != b"BI" else (b"", old)
        head = b"\nq %.6f %.6f %.6f %.6f %.4f %.4f cm\n" % tuple(m)
        pieces.append((s, e, state + head + body + b"\nQ\n", n,
                       len(state) + len(head), len(body), _written(head), state))
    data = _splice(data, pieces)
    _set_contents(page, data)
    same = objs is not None and objs.found is found      # (else its lines don't apply)
    return _moved(page, data, found, pieces, objs if same else None, t_page)


def _scan_copies(heads, inner, tail=b"\nQ\n"):
    """scan(b"".join(head + inner + tail for head in heads)) where each head is a
    "q <a b c d e f> cm" wrapper and inner draws the same in each: inner is read once and
    its objects repeated under each head's matrix (copying a big selection writes the same
    instructions for every copy). Each copy starts from the same state (q ... Q), so the
    result is exactly what reading it all would give."""
    one = scan(inner)
    out, pos = [], 0
    for head in heads:
        m = _written(head)
        base = pos + len(head)
        for x in one:
            y = dict(x)
            y["start"] += base
            y["end"] += base
            y["ctm"] = x["ctm"] * m
            out.append(y)
        pos = base + len(inner) + len(tail)
    return out


def _splice(data, pieces):
    """data with each (start, end, new bytes, ...) of pieces put in, in one pass (not one
    copy of a whole big drawing for each of thousands of pieces)."""
    out, pos = [], 0
    for s, e, piece, *_ in sorted(pieces, key=lambda p: p[0]):
        out.append(data[pos:s])
        out.append(piece)
        pos = e
    out.append(data[pos:])
    return b"".join(out)


def _written(head):
    """The matrix exactly as written in a  q a b c d e f cm  wrapper (rounded), so the
    object's matrix matches what reading the page gives."""
    return pymupdf.Matrix(*[float(v) for v in head.split()[1:7]])


def _rebuilt(page, data, found, objs, origin):
    """The page's Objects after an edit, from its new scan entries `found` (no second read of
    the whole drawing). origin[k] says where entry k came from: (old number, None) for an
    object left as it was, (old number, Matrix) for one moved or copied by that matrix (in
    page coordinates), None for one written anew. Lines already read carry over (moved
    along), so a big drawing's lines aren't read again after every command."""
    if objs is None:
        return Objects(page, data, found)
    old = {it["n"]: it for it in objs.items}
    # shapes left as they were (same matrix and box: only their place in the stream moved)
    # are taken over as they are, with their outline
    reuse = {}
    for k, o in enumerate(origin):
        if o is not None and o[1] is None:
            src = old.get(o[0])
            if src is not None and src["kind"] == "shape":
                reuse[k] = src
    new = Objects(page, data, found, reuse)
    Point = pymupdf.Point
    for it in new.items:
        o = origin[it["n"]] if it["n"] < len(origin) else None
        if o is None or it["n"] in reuse:
            continue
        src = old.get(o[0])
        if src is None or "lines" not in src or src["kind"] != it["kind"]:
            continue
        if o[1] is None:
            it["lines"] = src["lines"]
        else:
            a, b, c, d, e, f = tuple(o[1])
            it["lines"] = [[Point(q.x * a + q.y * c + e, q.x * b + q.y * d + f) for q in line]
                           for line in src["lines"]]
    return new


def _moved(page, data, found, pieces, objs=None, t_page=None):
    """The page's Objects after transform, from the old scan instead of reading the whole
    drawing again: a moved object is wrapped in its own  q M cm ... Q, which leaves the
    graphics state of everything after it as it was, so the other objects only shift by
    the bytes added before them, and the moved one gets M in front of its matrix.
    An object's own state settings (CAD exporters put the color and width inside the shape)
    move in front of it, so its recorded state is the state after them."""
    new = [dict(d) for d in found]
    by_n = {p[3]: p for p in pieces}
    shift = 0
    edits = sorted(pieces)                      # front to back
    k = 0
    for n, d in enumerate(found):
        while k < len(edits) and edits[k][1] <= d["start"] and edits[k][3] != n:
            s, e, piece = edits[k][:3]
            shift += len(piece) - (e - s)
            k += 1
        p = by_n.get(n)
        if p is None:
            new[n]["start"] = d["start"] + shift
            new[n]["end"] = d["end"] + shift
            continue
        s, e, piece, _n, off, size, m, state = p
        new[n]["start"] = s + shift + off
        new[n]["end"] = new[n]["start"] + size
        new[n]["ctm"] = pymupdf.Matrix(m) * d["ctm"]
        if state:
            new[n]["state"] = _state_after(d.get("state", b""), state)
        shift += len(piece) - (e - s)
        k += 1
    origin = [(n, t_page if n in by_n else None) for n in range(len(found))]
    return _rebuilt(page, data, new, objs, origin)


def move_to(page, ns, old_rect, new_rect, objs=None):
    """Move / scale objects ns so their common box old_rect becomes new_rect. Returns the
    page's new Objects when it could be worked out without reading the page again."""
    o, r = pymupdf.Rect(old_rect), pymupdf.Rect(new_rect)
    sx = r.width / o.width if o.width else 1.0
    sy = r.height / o.height if o.height else 1.0
    t = pymupdf.Matrix(1, 0, 0, 1, -o.x0, -o.y0) * pymupdf.Matrix(sx, 0, 0, sy, r.x0, r.y0)
    return transform(page, ns, t, objs)


def rotate(page, ns, rect, degrees, objs=None):
    """Turn objects ns about the center of rect (positive = clockwise as shown)."""
    r = pymupdf.Rect(rect)
    c = (r.tl + r.br) / 2
    t = pymupdf.Matrix(1, 0, 0, 1, -c.x, -c.y) * pymupdf.Matrix(degrees) * \
        pymupdf.Matrix(1, 0, 0, 1, c.x, c.y)
    return transform(page, ns, t, objs)


def copies(page, ns, matrices, objs=None, placed=None):
    """Copies of objects ns, one for each Matrix in matrices (unrotated page coordinates): each
    drawn right after its original, in a  q <M> cm ... Q  wrapper, so it looks the same (the
    state in effect there is the original's) and leaves the state of what follows alone."""
    tm = pdfcoords.to_page(page)
    data = _contents(page)
    if objs is not None and objs.found and objs.data == data:
        found = objs.found
    else:
        found = scan(data)
    have = objs is not None and objs.found and objs.data == data
    ns = sorted(set(ns))
    if ns and ns[-1] >= len(found):
        raise ValueError(tr("The object is no longer on the page."))
    if len(ns) > 1 and _groupable(page, data, found, ns):
        return _copies_together(page, data, found, ns, matrices, objs if have else None,
                                placed)
    adds = []
    tps = [tuple(tm * pymupdf.Matrix(t) * ~tm) for t in matrices]
    for n in sorted(set(ns)):
        if n >= len(found):
            raise ValueError(tr("The object is no longer on the page."))
        d = found[n]
        old = data[d["start"]:d["end"]]
        state, body = _split(old) if old[:2] != b"BI" else (b"", old)
        c = tuple(d["ctm"])
        ci = _inv(c)
        heads = [b"\nq %.6f %.6f %.6f %.6f %.4f %.4f cm\n" % _mul(_mul(c, tp), ci) for tp in tps]
        add = b"".join(h + body + b"\nQ\n" for h in heads)
        adds.append((d["end"], d["end"], add, n, state, heads, body))
    new_data = _splice(data, adds)
    _set_contents(page, new_data)
    got = {a[3]: _scan_copies(a[5], a[6]) for a in adds}
    if placed is not None:
        # where the originals are now: each one's copies come right after it
        placed["originals"], before = [], 0
        for a in adds:
            placed["originals"].append(a[3] + before)
            before += len(got[a[3]])
    if not have:
        return None
    # the new scan: each original, then its copies (scanned on their own, under its matrix)
    by_n = {a[3]: a for a in adds}
    out, origin, shift = [], [], 0
    for n, d in enumerate(found):
        e = dict(d)
        e["start"] += shift
        e["end"] += shift
        out.append(e)
        origin.append((n, None))
        a = by_n.get(n)
        if a is None:
            continue
        at, _e, add, _n, state = a[:5]
        after = _state_after(d.get("state", b""), state) if state else d.get("state", b"")
        mine = got[n]
        for k, x in enumerate(mine):
            x = dict(x)
            x["start"] += at + shift
            x["end"] += at + shift
            x["ctm"] = x["ctm"] * d["ctm"]
            x["ctx"] = d.get("ctx")
            x["state"] = after
            if x.get("path"):
                x["width"] = d.get("width", x["width"])
            out.append(x)
            # (one object per copy: its lines are the original's, moved)
            origin.append((n, matrices[k]) if len(mine) == len(matrices) else None)
        shift += len(add)
    return _rebuilt(page, new_data, out, objs, origin)


def _copies_together(page, data, found, ns, matrices, objs, placed=None):
    """copies() of several objects that can be drawn together (_groupable): each copy of the
    whole selection goes after the last selected object, its objects in their order, as a big
    array's group copies do, so a copy is drawn over the originals (as CAD programs draw new
    objects on top) and small and big arrays stack the same way."""
    tm = pdfcoords.to_page(page)
    _own_resources(page)
    _add_reset_gs(page)
    last = found[ns[-1]]
    ci = _inv(tuple(last["ctm"]))
    inner = b"\n".join([_DEFAULTS] + _standalone(data, found, ns))
    heads = [b"\nq\n%.6f %.6f %.6f %.6f %.4f %.4f cm\n" %
             _mul(tuple(tm * pymupdf.Matrix(t) * ~tm), ci) for t in matrices]
    add = b"".join(h + inner + b"\nQ\n" for h in heads)
    at = last["end"]
    new_data = data[:at] + add + data[at:]
    _set_contents(page, new_data)
    if placed is not None:
        placed["originals"] = list(ns)  # (the copies all come after them)
    if objs is None:
        return None
    after = _after_last(data, last)
    got = _scan_copies(heads, inner)
    one_each = len(got) == len(matrices) * len(ns)
    out, origin = [], []
    for n, d in enumerate(found):
        e = dict(d)
        if d["start"] >= at:
            e["start"] += len(add)
            e["end"] += len(add)
        out.append(e)
        origin.append((n, None))
        if n == ns[-1]:
            states = {}
            for k, x in enumerate(got):
                x = dict(x)
                x["start"] += at
                x["end"] += at
                x["ctm"] = x["ctm"] * last["ctm"]
                x["ctx"] = last.get("ctx")
                own = x.get("state", b"")
                if own not in states:   # (copies share a few distinct settings)
                    states[own] = _state_after(after, own)
                x["state"] = states[own]
                out.append(x)
                # (copy k // len(ns) of object ns[k % len(ns)]: its lines, moved)
                origin.append((ns[k % len(ns)], matrices[k // len(ns)]) if one_each else None)
    return _rebuilt(page, new_data, out, objs, origin)


def _contexts(data, starts):
    """{start: (marked content around it, clipping in effect)} for objects starting at
    starts: two objects with the same value are drawn under the same clip, in the same
    layer."""
    want = sorted(set(starts))
    out, i = {}, 0
    bdc, clip, stack = [], [], []
    for op, _args, s_, e_ in _tokens(data):
        while i < len(want) and want[i] <= s_:
            out[want[i]] = (tuple(bdc), tuple(clip))
            i += 1
        if i >= len(want):
            break
        if op == b"q":
            stack.append(len(clip))
        elif op == b"Q":
            if stack:
                del clip[stack.pop():]
        elif op in (b"BDC", b"BMC"):
            bdc.append(data[s_:e_])
        elif op == b"EMC":
            if bdc:
                bdc.pop()
        elif op in (b"W", b"W*"):
            clip.append(s_)
    for w in want[i:]:
        out[w] = (tuple(bdc), tuple(clip))
    return out


def _used_resources(doc, page, body):
    """A resource dictionary (text) with just the page's resources that body uses."""
    used = {}
    for op, args, _s, _e in _tokens(body):
        cat = _RES_OPS.get(op)
        if cat is not None:
            for a in args:
                if isinstance(a, bytes) and a.startswith(b"/"):
                    used.setdefault(cat, set()).add(a[1:].decode("latin-1"))
    parts = []
    for cat, keys in sorted(used.items()):
        have = _res_entries(doc, page.xref, "Resources/" + cat)
        items = []
        for k in sorted(keys):
            if k in have:
                text = _value_text(*have[k])
                if text is not None:
                    items.append("/%s %s" % (k, text))
        if items:
            parts.append("/%s<<%s>>" % (cat, " ".join(items)))
    return "<<%s>>" % "".join(parts)


def group_size(doc, xref, memo=None, depth=0):
    """How many objects drawing group xref draws, counting the groups inside it (an Array of
    a group copies all of them)."""
    memo = {} if memo is None else memo
    if xref in memo:
        return memo[xref]
    memo[xref] = 1                      # (a group inside itself counts once)
    try:
        data = doc.xref_stream(xref) or b""
        inner = {("/" + k).encode(): v for k, v in
                 _res_entries(doc, xref, "Resources/XObject").items()}
    except Exception:
        return 1
    n = 0
    for d in scan(data):
        kind, val = inner.get(d.get("name"), (None, None))
        if d.get("name") and kind == "xref" and depth < 8:
            sub = int(val.split()[0])
            if doc.xref_get_key(sub, "Subtype")[1] == "/Form":
                n += group_size(doc, sub, memo, depth + 1)
                continue
        n += 1
    memo[xref] = max(n, 1)
    return memo[xref]


def _groupable(page, data, found, ns):
    """Objects ns can be drawn together somewhere else and look the same: plain shapes and
    pictures (a group's own size isn't known), all under the same clipping and in the same
    layer (marked content), as copies placed right after the last of them are."""
    pictures = {("/" + g[7]).encode() for g in page.get_images(full=True)}
    if any(not found[n].get("path") and found[n].get("name") not in pictures for n in ns):
        return False
    ctx = [found[n].get("ctx") for n in ns]
    if None in ctx:                     # (entries made some other way: read the stream)
        ctx = _contexts(data, [found[n]["start"] for n in ns]).values()
    return len(set(ctx)) == 1


def _standalone(data, found, ns):
    """Each of objects ns as instructions that draw it the same anywhere (after _DEFAULTS):
    q <its matrix> cm <its colors, line style...> <its instructions> Q."""
    out = []
    for n in ns:
        d = found[n]
        out.append(b"q\n%.6f %.6f %.6f %.6f %.4f %.4f cm\n" % tuple(d["ctm"]) +
                   d.get("state", b"") + b"\n" + data[d["start"]:d["end"]] + b"\nQ")
    return out


def _after_last(data, last):
    """The state in effect right after object last: its own settings (colors, width) stay."""
    lo = data[last["start"]:last["end"]]
    own = _split(lo)[0] if lo[:2] != b"BI" else b""
    return _state_after(last.get("state", b""), own) if own else last.get("state", b"")


def block_copies(page, ns, matrices, objs=None, placed=None):
    """Copies of objects ns by reference, for big arrays: the objects go once into a drawing
    group (a Form XObject, as CAD programs export blocks), and each copy is one line placing
    it,  q <M> cm /KzBlockN Do Q,  right after the last of them (where the drawing's
    position matrix is that object's). Much quicker, and the file stays small, where copying
    every object for every copy would write the drawing out hundreds of times. The copies
    are groups in Edit objects (Ungroup takes one apart). Returns the page's new Objects
    when objs was given."""
    doc = page.parent
    tm = pdfcoords.to_page(page)
    data = _contents(page)
    have = objs is not None and objs.found and objs.data == data
    found = objs.found if have else scan(data)
    ns = sorted(set(ns))
    if not ns or ns[-1] >= len(found):
        raise ValueError(tr("The object is no longer on the page."))
    # Only where a group looks exactly like copies written out one by one: plain shapes and
    # pictures (a group's own size isn't known here), all under the same clipping and in the
    # same layer (marked content), as the copies placed after the last of them will be.
    # Anything else is copied the usual way.
    if not _groupable(page, data, found, ns):
        return copies(page, ns, matrices, objs, placed)
    _own_resources(page)
    _add_reset_gs(page)
    body = [_DEFAULTS] + _standalone(data, found, ns)
    xs, ys, pad = [], [], 0.0
    for n in ns:
        d = found[n]
        x0, y0, x1, y1 = d["box"] if d.get("path") else (0, 0, 1, 1)
        if d.get("path"):
            c = d["ctm"]                # (the width is in the object's units, the box isn't)
            scale = math.sqrt(abs(c.a * c.d - c.b * c.c))
            pad = max(pad, (d.get("width", 1.0) * 2 + 1) * max(scale, 1.0))
        for x, y in ((x0, y0), (x1, y0), (x0, y1), (x1, y1)):
            q = pymupdf.Point(x, y) * d["ctm"]
            xs.append(q.x)
            ys.append(q.y)
    # the group's own resources: only what its drawing uses (sharing the page's whole set
    # made each Ungroup copy all of it into the page again)
    res = _used_resources(doc, page, b"\n".join(body))
    xref = doc.get_new_xref()
    doc.update_object(xref, "<</Type/XObject/Subtype/Form/BBox[%g %g %g %g]/Resources %s>>"
                      % (min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad, res))
    _put_stream(doc, xref, b"\n".join(body))
    name = b"KzBlock%d" % xref
    _set_resource(doc, page.xref, "XObject", name.decode(), "%d 0 R" % xref)
    last = found[ns[-1]]
    ci = _inv(tuple(last["ctm"]))
    heads = [b"\nq\n%.6f %.6f %.6f %.6f %.4f %.4f cm\n" % _mul(tuple(tm * pymupdf.Matrix(t) * ~tm),
                                                                ci) for t in matrices]
    inner = b"/%s Do" % name
    add = b"".join(h + inner + b"\nQ\n" for h in heads)
    at = last["end"]
    new_data = data[:at] + add + data[at:]
    _set_contents(page, new_data)
    if placed is not None:
        placed["originals"] = list(ns)  # (the copies all come after them)
    if not have:
        return None
    after = _after_last(data, last)
    out, origin = [], []
    for n, d in enumerate(found):
        e = dict(d)
        if d["start"] >= at:
            e["start"] += len(add)
            e["end"] += len(add)
        out.append(e)
        origin.append((n, None))
        if n == ns[-1]:
            for x in _scan_copies(heads, inner):
                x = dict(x)
                x["start"] += at
                x["end"] += at
                x["ctm"] = x["ctm"] * last["ctm"]
                x["ctx"] = last.get("ctx")
                x["state"] = after
                out.append(x)
                origin.append(None)
    return _rebuilt(page, new_data, out, objs, origin)


def subpaths(data, obj):
    """A path object's pieces: (state bytes, [(subpath bytes, polyline in the object's own
    coordinates, closed)], paint operator bytes)."""
    state, parts, paint = [], [], b""
    cur = None
    first = last = None
    old = data[obj["start"]:obj["end"]]
    toks = _path_tokens(old)
    if toks is None:
        toks = [(op, args, old[s_:e_]) for op, args, s_, e_ in _tokens(old)]
    for op, args, raw in toks:
        if op in _STATE:
            state.append(raw)
            continue
        if op in _PAINT or op == b"n":
            paint = raw
            if op in (b"s", b"b", b"b*") and cur is not None and not cur[2]:
                if cur[1][-1] != first:
                    cur[1].append(first)
                cur[2] = True           # (these paint operators close the last subpath)
            continue
        k = _CONSTRUCT.get(op)
        if k is None:
            continue
        vals = [_num(t) for t in args[-k:]] if k else []
        if k and (len(args) < k or None in vals):
            continue
        P = [pymupdf.Point(vals[i], vals[i + 1]) for i in range(0, len(vals), 2)]
        if op == b"m":
            cur = [raw, [P[0]], False]
            parts.append(cur)
            first = last = P[0]
        elif op == b"re":
            x, y, w, h = vals
            c = [pymupdf.Point(x, y), pymupdf.Point(x + w, y), pymupdf.Point(x + w, y + h),
                 pymupdf.Point(x, y + h), pymupdf.Point(x, y)]
            parts.append([raw, c, True])
            cur = None
            first = last = c[0]
        elif cur is None:
            continue
        else:
            cur[0] += b" " + raw
            if op == b"l":
                cur[1].append(P[0])
                last = P[0]
            elif op == b"c":
                cur[1] += _bezier(last, P[0], P[1], P[2])
                last = P[2]
            elif op == b"v":
                cur[1] += _bezier(last, last, P[0], P[1])
                last = P[1]
            elif op == b"y":
                cur[1] += _bezier(last, P[0], P[1], P[1])
                last = P[1]
            elif op == b"h" and first is not None:
                cur[1].append(first)
                cur[2] = True
                last = first
    return b" ".join(state), [tuple(p_) for p_ in parts], paint


def _polyline_ops(pts):
    out = [b"%.4f %.4f m" % (pts[0].x, pts[0].y)]
    out += [b"%.4f %.4f l" % (q.x, q.y) for q in pts[1:]]
    return b" ".join(out)


def rewrite_path(page, n, state, parts, paint, objs=None):
    """Write path object n again from (state, [(subpath bytes, polyline, closed) or a list of
    new polylines], paint): a subpath given as bytes is kept as it was, polylines are drawn as
    straight lines. Nothing left: the object goes."""
    body = []
    for part in parts:
        if isinstance(part, bytes):
            body.append(part)
        else:
            body += [_polyline_ops(pts) for pts in part if len(pts) >= 2]
    if not body:
        return delete(page, [n], objs)
    if paint == b"s" and parts and isinstance(parts[-1], bytes):
        body[-1] += b" h"               # (s closed the last subpath, kept as it was)
    paint = b"S" if paint in (b"s", b"") else paint
    new = (state + b" " if state else b"") + b" ".join(body) + b" " + paint
    return _edit(page, [n], lambda old, ctm: b"\n" + new + b"\n", objs)


def delete(page, ns, objs=None):
    """Take objects ns off the page. Returns the page's new Objects when objs (the old
    ones) were given, else None."""
    return _edit(page, ns, lambda old, ctm: b" " + (_split(old)[0] if old[:2] != b"BI"
                                                    else b"") + b" ", objs)


_RESET = b"KZReset"
_DEFAULTS = b"0 g 0 G 1 w 0 J 0 j 10 M [] 0 d /KZReset gs"


def _add_reset_gs(page):
    """Give the page an ExtGState /KZReset (fully opaque, normal blending, no soft mask), so
    a moved object can drop the transparency in effect where it lands."""
    doc = page.parent
    value = "<</Type/ExtGState/CA 1/ca 1/BM/Normal/SMask/None>>"
    kind, val = doc.xref_get_key(page.xref, "Resources")
    if kind == "xref":
        res_xref, prefix = int(val.split()[0]), ""
    else:
        if kind != "dict":
            doc.xref_set_key(page.xref, "Resources", "<<>>")
        res_xref, prefix = page.xref, "Resources/"
    kind, val = doc.xref_get_key(res_xref, prefix + "ExtGState")
    if kind == "xref":
        doc.xref_set_key(int(val.split()[0]), "KZReset", value)
    else:
        if kind != "dict":
            doc.xref_set_key(res_xref, prefix + "ExtGState", "<<>>")
        doc.xref_set_key(res_xref, prefix + "ExtGState/KZReset", value)


def reorder(page, ns, how, dry_run=False):
    """Change where objects ns sit in the drawing order: front, back (of everything on the
    page, text included), forward, backward (past the next / previous object they overlap).
    Each moved object is redrawn as  q <matrix> cm <its colors, line style, transparency>
    <its instructions> Q  at the new place, so it looks the same; its old instructions are
    removed (state settings kept for what follows). A clipping path that was in effect at
    its old place doesn't come with it. Returns False if there's nowhere to move (dry_run:
    only check)."""
    tm = pdfcoords.to_page(page)
    data = _contents(page)
    found = scan(data)
    sel = sorted(set(n for n in ns if n < len(found)))
    if not sel:
        return False

    def bounds(d):
        if d.get("path"):
            x0, y0, x1, y1 = d["box"]
            return pymupdf.Rect(x0, y0, x1, y1).quad.transform(d["ctm"] * tm).rect
        return pymupdf.Rect(0, 0, 1, 1).quad.transform(d["ctm"] * tm).rect
    area = bounding(bounds(found[n]) for n in sel)
    ident = pymupdf.Matrix(1, 0, 0, 1, 0, 0)
    if how == "front":
        at, target = len(data), ident
    elif how == "back":
        at, target = 0, ident
    elif how == "forward":
        later = [k for k in range(sel[-1] + 1, len(found))
                 if k not in sel and overlap(bounds(found[k]), area)]
        if not later:
            return False
        d = found[later[0]]
        at, target = d["end"], d["ctm"]
    else:
        earlier = [k for k in range(sel[0] - 1, -1, -1)
                   if k not in sel and overlap(bounds(found[k]), area)]
        if not earlier:
            return False
        d = found[earlier[0]]
        at, target = d["start"], d["ctm"]
    if abs(target.a * target.d - target.b * target.c) < 1e-12:
        return False
    if dry_run:
        return True
    snippet = b""
    pieces = []
    for n in sel:
        d = found[n]
        old = data[d["start"]:d["end"]]
        m = d["ctm"] * ~target
        snippet += (b"\nq %.6f %.6f %.6f %.6f %.4f %.4f cm\n" % tuple(m) + _DEFAULTS + b" " +
                    d.get("state", b"") +
                    b"\n" + old + b"\nQ\n")
        keep = _split(old)[0] if old[:2] != b"BI" else b""
        pieces.append((d["start"], d["end"], b" " + keep + b" "))
    pieces.append((at, at, snippet))
    for s, e, piece in sorted(pieces, key=lambda p: (p[0], p[1]), reverse=True):
        data = data[:s] + piece + data[e:]
    _add_reset_gs(page)
    _set_contents(page, data)
    return True


def images(page):
    """The page's editable pictures (kept for callers and tests)."""
    return [it for it in Objects(page).items if it["kind"] == "picture"]


# ---- ungroup ---------------------------------------------------------------------------------
# operator -> the resource category its name operand comes from
_RES_OPS = {b"Tf": "Font", b"Do": "XObject", b"gs": "ExtGState", b"cs": "ColorSpace",
            b"CS": "ColorSpace", b"scn": "Pattern", b"SCN": "Pattern", b"sh": "Shading",
            b"BDC": "Properties", b"DP": "Properties"}
_RES_KINDS = ("Font", "XObject", "ExtGState", "ColorSpace", "Pattern", "Shading", "Properties")


def _dict_keys(text):
    """Top-level keys of a PDF dictionary written as text: '<</F1 5 0 R/F2 <<...>>>>'."""
    keys, depth, i, n = [], 0, 0, len(text)
    while i < n:
        if text.startswith("<<", i):
            depth += 1
            i += 2
        elif text.startswith(">>", i):
            depth -= 1
            i += 2
        elif text[i] in "[(" and depth == 1:
            i = _skip_value(text, i)        # an array or string value, whole
        elif text[i] == "/" and depth == 1:
            m = re.match(r"/([^\s/\[\]()<>{}%]+)", text[i:])
            name = m.group(1)
            i += m.end()
            keys.append(name)
            # its value: skip a name value too, so it isn't taken for the next key
            j = i
            while j < n and text[j] in " \r\n\t":
                j += 1
            if text.startswith("/", j):
                m2 = re.match(r"/[^\s/\[\]()<>{}%]*", text[j:])
                i = j + m2.end()
        else:
            i += 1
    return keys


def _skip_value(text, i):
    """Index just past the array "[...]" or string "(...)" starting at text[i]."""
    open_, close = (text[i], "]" if text[i] == "[" else ")")
    depth, n = 0, len(text)
    while i < n:
        c = text[i]
        if c == "\\" and open_ == "(":
            i += 2
            continue
        if c == open_:
            depth += 1
        elif c == close:
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return n


def _res_entries(doc, xref, path):
    """{key: value text} of the resource dictionary at xref/path (e.g. 'Resources/Font')."""
    kind, val = doc.xref_get_key(xref, path)
    if kind == "xref":
        sub = int(val.split()[0])
        return {k: doc.xref_get_key(sub, k) for k in doc.xref_get_keys(sub)}
    if kind == "dict":
        return {k: doc.xref_get_key(xref, path + "/" + k) for k in _dict_keys(val)}
    return {}


def _own_resources(page):
    """Make sure the page has its own /Resources (not only one inherited from its parents),
    so names added to it don't land in a dictionary other pages depend on unchanged."""
    doc = page.parent
    kind, _v = doc.xref_get_key(page.xref, "Resources")
    if kind != "null":
        return
    x = page.xref
    while True:
        k, parent = doc.xref_get_key(x, "Parent")
        if k != "xref":
            doc.xref_set_key(page.xref, "Resources", "<<>>")
            return
        x = int(parent.split()[0])
        k, v = doc.xref_get_key(x, "Resources")
        if k in ("xref", "dict"):
            doc.xref_set_key(page.xref, "Resources", v)
            return


def _set_resource(doc, xref, cat, key, text):
    """Resources/<cat>/<key> = text on object xref, following indirect dictionaries (which
    xref_set_key can't write through)."""
    kind, val = doc.xref_get_key(xref, "Resources")
    path = "Resources/"
    if kind == "xref":
        xref, path = int(val.split()[0]), ""
    kind, val = doc.xref_get_key(xref, path + cat)
    if kind == "xref":
        doc.xref_set_key(int(val.split()[0]), key, text)
    elif kind == "dict":
        doc.xref_set_key(xref, f"{path}{cat}/{key}", text)
    else:
        doc.xref_set_key(xref, path + cat, f"<</{key} {text}>>")


def _value_text(kind, val):
    return {"xref": val, "dict": val, "array": val, "name": val, "int": val, "float": val,
            "bool": val, "string": val}.get(kind)


def _expand(doc, page, fx, taken, depth=0):
    """The drawing instructions of Form XObject fx, to stand in for its "/Name Do" on the
    page (None when fx isn't a usable form). A group holding nothing but one other group (a
    wrapper, as many programs write) is taken apart too."""
    if fx is None or depth > 8 or doc.xref_get_key(fx, "Subtype")[1] != "/Form":
        return None
    box, fm = _form_box(doc, fx)
    if box is None:
        return None
    # the group's resources, renamed into the page's
    rename, forms = {}, {}
    page_res = {}
    for cat in _RES_KINDS:
        page_res[cat] = {k: _value_text(*v) for k, v in
                         _res_entries(doc, page.xref, "Resources/" + cat).items()}
    for cat in _RES_KINDS:
        for key, (kind, val) in _res_entries(doc, fx, "Resources/" + cat).items():
            text = _value_text(kind, val)
            if text is None:
                continue
            if key in taken[cat] and page_res.get(cat, {}).get(key) == text:
                # the page has this very one under this name already
                if cat == "XObject" and kind == "xref":
                    forms[("/" + key).encode()] = int(val.split()[0])
                continue
            k = 1
            while f"KZ{k}{key}" in taken[cat]:
                k += 1
            new = f"KZ{k}{key}"
            taken[cat].add(new)
            _set_resource(doc, page.xref, cat, new, text)
            rename[(cat, ("/" + key).encode())] = ("/" + new).encode()
            if cat == "XObject" and kind == "xref":
                forms[("/" + new).encode()] = int(val.split()[0])
    body = doc.xref_stream(fx) or b""
    out, last = [], 0
    for op, args, s_, e_ in _tokens(body):
        cat = _RES_OPS.get(op)
        if cat is None:
            continue
        for a in args:
            new = rename.get((cat, a)) if isinstance(a, bytes) else None
            if new is not None:
                at = body.find(a, s_, e_)
                if at >= 0:
                    out.append(body[last:at])
                    out.append(new)
                    last = at + len(a)
                break
    out.append(body[last:])
    body = b"".join(out)
    inner = scan(body)
    if len(inner) == 1 and inner[0].get("name") in forms:
        sub = _expand(doc, page, forms[inner[0]["name"]], taken, depth + 1)
        if sub is not None:
            body = body[:inner[0]["start"]] + sub + body[inner[0]["end"]:]
    m = " ".join(f"{v:g}" for v in (fm.a, fm.b, fm.c, fm.d, fm.e, fm.f)).encode()
    clip = f"{box.x0:g} {box.y0:g} {box.width:g} {box.height:g} re W n".encode()
    return b"\nq " + m + b" cm " + clip + b"\n" + body + b"\nQ\n"


def ungroup(page, ns):
    """Turn the groups (Form XObjects drawn with /Name Do) among objects ns into ordinary page
    content: the "Do" is replaced by the group's own drawing instructions, kept inside its
    matrix and bounding box, and the fonts, pictures and styles it uses are added to the
    page's resources under new names. Afterwards each shape, picture and line of text in it
    can be selected and edited on its own. Returns how many groups were taken apart."""
    doc = page.parent
    data = _contents(page)
    found = scan(data)
    forms = {("/" + g[1]).encode(): g[0] for g in page.get_xobjects() if g[2] == 0}
    _own_resources(page)
    taken = {cat: set(_res_entries(doc, page.xref, "Resources/" + cat)) for cat in _RES_KINDS}
    pieces = []
    for n in sorted(set(ns), reverse=True):
        if n >= len(found):
            raise ValueError(tr("The object is no longer on the page."))
        d = found[n]
        piece = _expand(doc, page, forms.get(d.get("name")), taken)
        if piece is not None:
            pieces.append((d["start"], d["end"], piece))
    for s, e, piece in pieces:          # back to front: earlier offsets stay valid
        data = data[:s] + piece + data[e:]
    if pieces:
        _set_contents(page, data)
    return len(pieces)
