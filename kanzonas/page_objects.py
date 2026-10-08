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

import pymupdf

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
    space bounds), "stroke", "fill" and "width"."""
    out = []
    ctm = pymupdf.Matrix(1, 0, 0, 1, 0, 0)
    width = 1.0
    stack = []
    path_start = None
    clip = False
    xs, ys = [], []
    for op, args, start, end in _tokens(data):
        if op in _CONSTRUCT:
            if path_start is None:
                path_start = start
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
            continue
        if path_start is not None and op in _STATE:
            if op == b"w" and args:
                width = _num(args[-1]) or 0.0
            continue
        if path_start is not None:
            if op in _PAINT and not clip and xs:
                stroke, fill = _PAINT[op]
                out.append({"start": path_start, "end": end, "ctm": pymupdf.Matrix(ctm),
                            "path": True, "box": (min(xs), min(ys), max(xs), max(ys)),
                            "stroke": stroke, "fill": fill, "width": width})
            path_start = None
            if op in _PAINT or op == b"n":
                continue
        if op == b"q":
            stack.append((ctm, width))
        elif op == b"Q":
            if stack:
                ctm, width = stack.pop()
        elif op == b"cm" and len(args) >= 6:
            vals = [_num(t) for t in args[-6:]]
            if None not in vals:
                ctm = pymupdf.Matrix(*vals) * ctm
        elif op == b"w" and args:
            width = _num(args[-1]) or 0.0
        elif op == b"Do" and args and isinstance(args[-1], bytes) and args[-1][:1] == b"/":
            out.append({"start": start, "end": end, "ctm": pymupdf.Matrix(ctm),
                        "name": args[-1]})
        elif op == b"BI":
            out.append({"start": start, "end": end, "ctm": pymupdf.Matrix(ctm), "name": None})
    return out


def _bezier(p0, p1, p2, p3):
    pts = []
    for i in range(1, CURVE_STEPS + 1):
        t = i / CURVE_STEPS
        u = 1 - t
        pts.append(p0 * (u ** 3) + p1 * (3 * u * u * t) + p2 * (3 * u * t * t) + p3 * (t ** 3))
    return pts


def path_lines(data, obj, tm):
    """A shape's outline as polylines in page coordinates: [[Point, ...], ...]."""
    mat = obj["ctm"] * tm
    out = []
    cur = None
    first = None
    for op, args, _s, _e in _tokens(data[obj["start"]:obj["end"]]):
        k = _CONSTRUCT.get(op)
        if k is None:
            continue
        vals = [_num(t) for t in args[-k:]] if k else []
        if k and (len(args) < k or None in vals):
            continue
        P = [pymupdf.Point(vals[i], vals[i + 1]) for i in range(0, len(vals), 2)]
        if op == b"m":
            cur = [P[0] * mat]
            first = P[0]
            out.append(cur)
            last = P[0]
        elif op == b"re":
            x, y, w, h = vals
            c = [pymupdf.Point(x, y), pymupdf.Point(x + w, y), pymupdf.Point(x + w, y + h),
                 pymupdf.Point(x, y + h), pymupdf.Point(x, y)]
            out.append([q * mat for q in c])
            cur = None
            first = last = c[0]
        elif cur is None:
            continue
        elif op == b"l":
            cur.append(P[0] * mat)
            last = P[0]
        elif op == b"c":
            cur += [q * mat for q in _bezier(last, P[0], P[1], P[2])]
            last = P[2]
        elif op == b"v":
            cur += [q * mat for q in _bezier(last, last, P[0], P[1])]
            last = P[1]
        elif op == b"y":
            cur += [q * mat for q in _bezier(last, P[0], P[1], P[1])]
            last = P[1]
        elif op == b"h" and first is not None:
            cur.append(first * mat)
            last = first
    return out


def _contents(page):
    doc = page.parent
    return b"\n".join(doc.xref_stream(x) or b"" for x in page.get_contents())


def _set_contents(page, data):
    """Give the page one new content stream (never edits a stream another page may share)."""
    doc = page.parent
    x = doc.get_new_xref()
    doc.update_object(x, "<<>>")
    doc.update_stream(x, data)
    page.set_contents(x)


class Objects:
    """The editable objects of one page, read once (cache it until the page changes)."""

    def __init__(self, page):
        self.data = _contents(page)
        self.tm = page.transformation_matrix
        self.items = []
        if not self.data.strip():
            return
        names = {}
        for it in page.get_images(full=True):
            if it[-1] == 0:             # drawn by the page itself, not inside a form
                names[("/" + it[7]).encode()] = it[0]
        # placed signatures and initials aren't editable here
        typ, val = page.parent.xref_get_key(page.xref, "KZSig")
        sigs = {int(v) for v in val.strip("[]").split()} if typ == "array" else set()
        tm = self.tm
        for k, d in enumerate(scan(self.data)):
            m = d["ctm"] * tm
            if abs(m.a * m.d - m.b * m.c) < 1e-12:
                continue
            if d.get("path"):
                x0, y0, x1, y1 = d["box"]
                quad = pymupdf.Rect(x0, y0, x1, y1).quad.transform(m)
                scale = math.sqrt(abs(m.a * m.d - m.b * m.c))
                self.items.append({"n": k, "kind": "shape", "rect": quad.rect, "xref": 0,
                                   "quad": quad, "stroke": d["stroke"], "fill": d["fill"],
                                   "width": d["width"] * scale, "obj": d})
                continue
            if d["name"] is None:
                xref = 0
            else:
                xref = names.get(d["name"])
                if xref is None or xref in sigs:
                    continue            # a form or something else, or a signature
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

    def at(self, pt, tol):
        """The topmost object at page point pt: a line within tol of it first, then a filled
        shape or picture under it."""
        pt = pymupdf.Point(pt)
        filled = None
        for it in reversed(self.items):
            r = it["rect"]
            pad = tol + it.get("width", 0) / 2
            if not (r.x0 - pad <= pt.x <= r.x1 + pad and r.y0 - pad <= pt.y <= r.y1 + pad):
                continue
            if it["kind"] == "picture":
                if pt in it["quad"] and filled is None:
                    filled = it
                continue
            for line in self.lines(it):
                if _near(line, pt, pad):
                    return it
            if it["fill"] and filled is None and _inside(self.lines(it), pt):
                filled = it
        return filled

    def inside(self, box):
        """Objects lying entirely inside box."""
        box = pymupdf.Rect(box)
        return [it for it in self.items if box.contains(it["rect"])]


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
def _edit(page, ns, new):
    """Replace the drawing instructions of objects ns with new(old_bytes, ctm)."""
    data = _contents(page)
    found = scan(data)
    pieces = []
    for n in sorted(set(ns), reverse=True):
        if n >= len(found):
            raise ValueError("The object is no longer on the page.")
        d = found[n]
        pieces.append((d["start"], d["end"], new(data[d["start"]:d["end"]], d["ctm"])))
    for s, e, piece in pieces:          # back to front: earlier offsets stay valid
        data = data[:s] + piece + data[e:]
    _set_contents(page, data)


def _split(old):
    """A shape's instructions -> (graphics state settings, path and paint operators), so a
    wrap or delete leaves the state settings in effect for what's drawn after it."""
    state, path = [], []
    for op, _a, s_, e_ in _tokens(old):
        (state if op in _STATE else path).append(old[s_:e_])
    return b" ".join(state), b" ".join(path)


_WRAP = re.compile(rb"\nq ((?:-?[\d.]+ ){6})cm\n$")


def transform(page, ns, t_page):
    """Apply t_page (a Matrix in unrotated page coordinates) to objects ns. An object this
    module moved before already sits in a  q <M> cm ... Q  wrapper: the new move is folded
    into that one matrix, so nudging a shape a hundred times doesn't nest a hundred
    wrappers."""
    tm = page.transformation_matrix
    t_pdf = tm * t_page * ~tm
    data = _contents(page)
    found = scan(data)
    pieces = []
    for n in sorted(set(ns), reverse=True):
        if n >= len(found):
            raise ValueError("The object is no longer on the page.")
        d = found[n]
        s, e, ctm = d["start"], d["end"], d["ctm"]
        m = ctm * t_pdf * ~ctm                      # the move, in the object's own space
        old = data[s:e]
        w = _WRAP.search(data, max(0, s - 120), s)
        if w and w.end() == s and data[e:e + 3] == b"\nQ\n":
            outer = pymupdf.Matrix(*[float(v) for v in w.group(1).split()])
            pieces.append((w.start(), e + 3, b"\nq %.6f %.6f %.6f %.6f %.4f %.4f cm\n"
                           % tuple(m * outer) + old + b"\nQ\n"))
            continue
        state, body = _split(old) if old[:2] != b"BI" else (b"", old)
        pieces.append((s, e, state + b"\nq %.6f %.6f %.6f %.6f %.4f %.4f cm\n" % tuple(m)
                       + body + b"\nQ\n"))
    for s, e, piece in pieces:          # back to front: earlier offsets stay valid
        data = data[:s] + piece + data[e:]
    _set_contents(page, data)


def move_to(page, ns, old_rect, new_rect):
    """Move / scale objects ns so their common box old_rect becomes new_rect."""
    o, r = pymupdf.Rect(old_rect), pymupdf.Rect(new_rect)
    sx = r.width / o.width if o.width else 1.0
    sy = r.height / o.height if o.height else 1.0
    t = pymupdf.Matrix(1, 0, 0, 1, -o.x0, -o.y0) * pymupdf.Matrix(sx, 0, 0, sy, r.x0, r.y0)
    transform(page, ns, t)


def rotate(page, ns, rect, degrees):
    """Turn objects ns about the center of rect (positive = clockwise as shown)."""
    r = pymupdf.Rect(rect)
    c = (r.tl + r.br) / 2
    t = pymupdf.Matrix(1, 0, 0, 1, -c.x, -c.y) * pymupdf.Matrix(degrees) * \
        pymupdf.Matrix(1, 0, 0, 1, c.x, c.y)
    transform(page, ns, t)


def delete(page, ns):
    _edit(page, ns, lambda old, ctm: b" " + (_split(old)[0] if old[:2] != b"BI" else b"") +
          b" ")


def images(page):
    """The page's editable pictures (kept for callers and tests)."""
    return [it for it in Objects(page).items if it["kind"] == "picture"]
