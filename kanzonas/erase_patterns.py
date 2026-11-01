"""Erase content: fills painted with a pattern (hatches, gradients) that cross the erase box.

MuPDF's redaction removes every vector path the box touches, and erase.py puts the parts
outside the box back with Shape, which can draw solid colors only. A hatched area or a
gradient-filled logo erased in one spot therefore vanished whole. Before the redaction this
module reads the page's content streams (and the form XObjects they draw) for fills painted
with a pattern whose outline crosses the box; afterwards it paints them again on top of the
page, clipped to everything outside the box, with the same pattern, color space, clipping
paths and position (a pattern used inside a form gets a copy whose Matrix puts it where the
form drew it).

Coordinates inside this module are PDF user space (origin bottom left), not PyMuPDF's page
coordinates; find_crossing converts the box once. Anything unexpected in a content stream is
skipped, never fatal: erase.erase treats a failure here as "nothing to repaint".
"""

import re

import pymupdf

from . import pdfcoords

MAX_DEPTH = 8                   # nested form XObjects followed

_WS = b"\x00\t\n\x0c\r "
_TOKEN = re.compile(rb"""
    (?P<ws>[\x00\t\n\x0c\r ]+) | (?P<cmt>%[^\r\n]*) |
    (?P<num>[+-]?(?:\d+\.?\d*|\.\d+)) |
    /(?P<name>[^\x00\t\n\x0c\r /\[\]()<>{}%]*) |
    (?P<str>\() | (?P<hex><(?!<)) |
    (?P<dict><<|>>) | (?P<arr>[\[\]]) | (?P<brace>[{}]) |
    (?P<op>[^\x00\t\n\x0c\r /\[\]()<>{}%]+)
""", re.X)
_FILL_OPS = {"f", "F", "f*", "B", "B*", "b", "b*"}
_END_PATH_OPS = _FILL_OPS | {"S", "s", "n"}


def _skip_string(data, i):
    """i is just past the opening '('; returns the index past the closing ')'."""
    depth, n = 1, len(data)
    while i < n and depth:
        c = data[i]
        if c == 0x5C:                       # backslash: skip the escaped byte
            i += 2
            continue
        if c == 0x28:
            depth += 1
        elif c == 0x29:
            depth -= 1
        i += 1
    return i


def _skip_inline_image(data, i):
    """i is just past 'BI'; returns the index past the matching 'EI'."""
    n = len(data)
    m = re.compile(rb"(?<![^\x00\t\n\x0c\r ])ID[\x00\t\n\x0c\r ]").search(data, i)
    if not m:
        return n
    j = m.end()
    while True:
        k = data.find(b"EI", j)
        if k < 0:
            return n
        if data[k - 1] in _WS and (k + 2 >= n or data[k + 2] in _WS):
            return k + 2
        j = k + 2


def _tokens(data):
    """(kind, value) for a content stream: 'num', 'name', 'str', 'delim' or 'op'. Inline
    images are skipped whole."""
    i, n = 0, len(data)
    while i < n:
        m = _TOKEN.match(data, i)
        if m is None:
            i += 1
            continue
        i = m.end()
        kind = m.lastgroup
        if kind in ("ws", "cmt", "brace"):
            continue
        if kind == "num":
            try:
                yield "num", float(m.group("num"))
            except ValueError:
                pass
        elif kind == "name":
            yield "name", m.group("name").decode("latin-1")
        elif kind == "str":
            i = _skip_string(data, i)
            yield "str", None
        elif kind == "hex":
            j = data.find(b">", i)
            i = n if j < 0 else j + 1
            yield "str", None
        elif kind in ("dict", "arr"):
            yield "delim", m.group().decode("latin-1")
        else:
            op = m.group("op").decode("latin-1")
            if op == "BI":
                i = _skip_inline_image(data, i)
                continue
            yield "op", op


def _xref_of(value):
    return int(value.split()[0])


def _matrix(value):
    """A PDF array string '[a b c d e f]' as a Matrix (identity when malformed)."""
    try:
        nums = [float(x) for x in value.strip("[] ").split()]
        if len(nums) == 6:
            return pymupdf.Matrix(*nums)
    except ValueError:
        pass
    return pymupdf.Matrix(1, 1)


def _fmt(*nums):
    return " ".join(f"{x:.3f}".rstrip("0").rstrip(".") if x != int(x) else str(int(x))
                    for x in nums)


def _path_str(items):
    out = []
    for it in items:
        op = it[0]
        if op == "m" or op == "l":
            out.append(f"{_fmt(it[1].x, it[1].y)} {op}")
        elif op == "c":
            out.append(f"{_fmt(it[1].x, it[1].y, it[2].x, it[2].y, it[3].x, it[3].y)} c")
        elif op == "h":
            out.append("h")
    return "\n".join(out)


def _bbox(items):
    """The points' bounding box (Rect union drops point-sized rects, so by hand)."""
    xs = [p.x for it in items for p in it[1:]]
    ys = [p.y for it in items for p in it[1:]]
    if not xs:
        return pymupdf.Rect()
    return pymupdf.Rect(min(xs), min(ys), max(xs), max(ys))


class _State:
    __slots__ = ("ctm", "cs", "pat", "clips")

    def __init__(self, ctm, clips):
        self.ctm, self.cs, self.pat, self.clips = ctm, None, None, list(clips)

    def copy(self):
        s = _State(self.ctm, self.clips)
        s.cs, s.pat = self.cs, self.pat
        return s


class _Walker:
    def __init__(self, doc, box):
        self.doc = doc
        self.box = box                  # PDF user space
        self.found = []

    # -- resources -----------------------------------------------------------------------
    def _get(self, chain, key):
        for xref, prefix in chain:
            t, v = self.doc.xref_get_key(xref, prefix + "/" + key if prefix else key)
            if t != "null":
                return t, v
        return "null", None

    def _colorspace(self, chain, name):
        """The fill color space string when it is a Pattern space, else None."""
        if name == "Pattern":
            return "/Pattern"
        t, v = self._get(chain, "ColorSpace/" + name)
        if t == "xref":
            v = self.doc.xref_object(_xref_of(v))
            t = "array" if v.lstrip().startswith("[") else "name"
        if t == "name" and v.strip() == "/Pattern":
            return "/Pattern"
        if t == "array" and v.replace(" ", "").replace("\n", "").startswith("[/Pattern"):
            return " ".join(v.split())
        return None

    def _pattern(self, chain, name):
        t, v = self._get(chain, "Pattern/" + name)
        if t == "xref":
            return "xref", _xref_of(v)
        if t == "dict":
            return "dict", v
        return None

    # -- the walk ------------------------------------------------------------------------
    def run(self, data, chain, ctm, base, clips, depth, visited):
        gs = _State(ctm, clips)
        stack, path, operands = [], [], []
        cur = start = None
        pending_clip = None

        def pt(x, y):
            return pymupdf.Point(x, y) * gs.ctm

        def nums(k):
            vals = [v for kind, v in operands if kind == "num"]
            return vals[-k:] if len(vals) >= k else None

        def end_path():
            nonlocal path, pending_clip
            if pending_clip is not None and path:
                gs.clips.append((path, pending_clip))
            pending_clip = None
            path = []

        for kind, val in _tokens(data):
            if kind != "op":
                operands.append((kind, val))
                continue
            op = val
            try:
                if op == "q":
                    stack.append(gs.copy())
                elif op == "Q":
                    if stack:
                        gs = stack.pop()
                elif op == "cm":
                    a = nums(6)
                    if a:
                        gs.ctm = pymupdf.Matrix(*a) * gs.ctm
                elif op == "m":
                    a = nums(2)
                    if a:
                        cur = start = pt(*a)
                        path.append(("m", cur))
                elif op == "l":
                    a = nums(2)
                    if a and cur is not None:
                        cur = pt(*a)
                        path.append(("l", cur))
                elif op in ("c", "v", "y"):
                    if cur is not None:
                        if op == "c":
                            a = nums(6)
                            if a:
                                p1, p2, p3 = pt(a[0], a[1]), pt(a[2], a[3]), pt(a[4], a[5])
                                path.append(("c", p1, p2, p3))
                                cur = p3
                        else:
                            a = nums(4)
                            if a:
                                q1, q2 = pt(a[0], a[1]), pt(a[2], a[3])
                                if op == "v":
                                    path.append(("c", cur, q1, q2))
                                else:
                                    path.append(("c", q1, q2, q2))
                                cur = q2
                elif op == "h":
                    if path:
                        path.append(("h",))
                        cur = start
                elif op == "re":
                    a = nums(4)
                    if a:
                        x, y, w, h = a
                        c0, c1, c2, c3 = pt(x, y), pt(x + w, y), pt(x + w, y + h), pt(x, y + h)
                        path += [("m", c0), ("l", c1), ("l", c2), ("l", c3), ("h",)]
                        cur = start = c0
                elif op in _END_PATH_OPS:
                    if op in _FILL_OPS and gs.pat is not None and path:
                        self._record(path, op.endswith("*"), gs, base)
                    end_path()
                elif op == "W":
                    pending_clip = False
                elif op == "W*":
                    pending_clip = True
                elif op == "cs":
                    gs.pat = None
                    gs.cs = self._colorspace(chain, operands[-1][1]) \
                        if operands and operands[-1][0] == "name" else None
                elif op in ("sc", "scn"):
                    gs.pat = None
                    if gs.cs is not None and operands and operands[-1][0] == "name":
                        pat = self._pattern(chain, operands[-1][1])
                        if pat is not None:
                            comps = [v for k, v in operands[:-1] if k == "num"]
                            gs.pat = (pat, comps, gs.cs)
                elif op in ("g", "rg", "k"):
                    gs.cs = gs.pat = None
                elif op == "Do":
                    if operands and operands[-1][0] == "name":
                        self._form(chain, operands[-1][1], gs, depth, visited)
            except Exception:
                pass                        # a malformed operator: skip it, keep walking
            operands = []

    def _form(self, chain, name, gs, depth, visited):
        t, v = self._get(chain, "XObject/" + name)
        if t != "xref" or depth >= MAX_DEPTH:
            return
        xref = _xref_of(v)
        if xref in visited:
            return
        if self.doc.xref_get_key(xref, "Subtype")[1] != "/Form":
            return
        t, v = self.doc.xref_get_key(xref, "Matrix")
        ctm = (_matrix(v) if t == "array" else pymupdf.Matrix(1, 1)) * gs.ctm
        clips = list(gs.clips)
        t, v = self.doc.xref_get_key(xref, "BBox")
        if t == "array":
            try:
                x0, y0, x1, y1 = [float(x) for x in v.strip("[] ").split()]
                q = [pymupdf.Point(x0, y0) * ctm, pymupdf.Point(x1, y0) * ctm,
                     pymupdf.Point(x1, y1) * ctm, pymupdf.Point(x0, y1) * ctm]
                clips.append(([("m", q[0]), ("l", q[1]), ("l", q[2]), ("l", q[3]), ("h",)],
                              False))
            except ValueError:
                pass
        data = self.doc.xref_stream(xref) or b""
        self.run(data, [(xref, "Resources")] + chain, ctm, ctm, clips, depth + 1,
                 visited | {xref})

    def _record(self, path, even_odd, gs, base):
        r = _bbox(path)
        if not r.intersects(self.box) or self.box.contains(r):
            return                          # untouched, or removed whole (as it should be)
        pat, comps, cs = gs.pat
        self.found.append({"path": list(path), "even_odd": even_odd, "clips": list(gs.clips),
                           "pattern": pat, "comps": comps, "cs": cs, "base": base,
                           "rect": r})


def _page_chain(page):
    """Where the page's resources may be: the page object, then its ancestors (inherited)."""
    doc = page.parent
    chain, xref, seen = [], page.xref, set()
    while xref and xref not in seen and len(chain) < 16:
        seen.add(xref)
        chain.append((xref, "Resources"))
        t, v = doc.xref_get_key(xref, "Parent")
        xref = _xref_of(v) if t == "xref" else 0
    return chain


def _dict_names(doc, xref, key):
    """The values (text) in dictionary key ("Resources/XObject") of object xref, following an
    indirect dictionary; None when they can't be listed."""
    t, v = doc.xref_get_key(xref, key)
    if t == "null":
        return []
    if t == "xref":
        sub = _xref_of(v)
        return [doc.xref_get_key(sub, k)[1] for k in doc.xref_get_keys(sub)]
    if t == "dict":
        from .page_objects import _dict_keys
        return [doc.xref_get_key(xref, key + "/" + k)[1] for k in _dict_keys(v)]
    return None


def _may_use_patterns(doc, chain, depth=0, seen=None):
    """False only when nothing the walk could reach has a /Pattern resource: _Walker records
    a fill only after "scn /Name" finds Name under /Pattern in the resources of the page (or
    a parent it inherits from) or of a form it draws, and it reaches forms only through the
    /XObject resources of those same dictionaries. So the walk over the content (seconds on
    a sheet with 200,000 lines) can't find anything. Anything unexpected: True (walk)."""
    seen = set() if seen is None else seen
    if depth > MAX_DEPTH + 1:
        return True
    for xref, prefix in chain:
        if doc.xref_get_key(xref, prefix + "/Pattern")[0] != "null":
            return True
        values = _dict_names(doc, xref, prefix + "/XObject")
        if values is None:
            return True
        for v in values:
            if not v.endswith(" 0 R") and not v.endswith(" R"):
                if v.strip() and v.strip() != "null":
                    return True         # (a form written inline? not seen in practice)
                continue
            try:
                x = _xref_of(v)
            except ValueError:
                return True
            if x in seen:
                continue
            seen.add(x)
            if doc.xref_get_key(x, "Subtype")[1] != "/Form":
                continue
            if _may_use_patterns(doc, [(x, "Resources")], depth + 1, seen):
                return True
    return False


def find_crossing(page, box):
    """The pattern-filled shapes on the page whose outline crosses `box` (PyMuPDF unrotated
    page coordinates). Call before the redaction; pass the result to repaint after it."""
    chain = _page_chain(page)
    if not _may_use_patterns(page.parent, chain):
        return []                       # (no patterns anywhere it could look)
    box_pdf = pymupdf.Rect(box) * pdfcoords.to_pdf(page)
    w = _Walker(page.parent, box_pdf)
    w.run(page.read_contents() or b"", chain, pymupdf.Matrix(1, 1),
          pymupdf.Matrix(1, 1), [], 0, set())
    return w.found


def _set_resource(doc, page, category, name, value):
    """Resources/<category>/<name> = value on the page, following indirect dictionaries
    (xref_set_key can't). False when the page has no Resources of its own to add to."""
    owner, path = page.xref, "Resources"
    t, v = doc.xref_get_key(owner, path)
    if t == "xref":
        owner, path = _xref_of(v), ""
    elif t != "dict":
        return False
    key = (path + "/" if path else "") + category
    t, v = doc.xref_get_key(owner, key)
    if t == "xref":
        owner, key = _xref_of(v), ""
    doc.xref_set_key(owner, (key + "/" if key else "") + name, value)
    return True


def _free_name(doc, page, category, stem):
    for i in range(1, 10000):
        name = f"{stem}{i}"
        if doc.xref_get_key(page.xref, f"Resources/{category}/{name}")[0] == "null":
            return name
    return f"{stem}x"


def repaint(page, records, box):
    """Paint the shapes from find_crossing again, clipped to everything outside `box`
    (PyMuPDF unrotated page coordinates). Returns how many were painted."""
    if not records:
        return 0
    doc = page.parent
    box_pdf = pymupdf.Rect(box) * pdfcoords.to_pdf(page)
    identity = pymupdf.Matrix(1, 1)
    parts, done = [], 0
    for rec in records:
        kind, pat = rec["pattern"]
        base = rec["base"]
        if kind == "xref" and abs(base - identity) < 1e-6:
            pxref = pat
        else:
            pxref = doc.get_new_xref()
            doc.update_object(pxref, "<<>>")        # xref_copy needs a dict to copy into
            if kind == "xref":
                doc.xref_copy(pat, pxref)
            else:
                doc.update_object(pxref, pat)
            if abs(base - identity) >= 1e-6:
                t, v = doc.xref_get_key(pxref, "Matrix")
                m = (_matrix(v) if t == "array" else identity) * base
                doc.xref_set_key(pxref, "Matrix", f"[{_fmt(m.a, m.b, m.c, m.d, m.e, m.f)}]")
        pname = _free_name(doc, page, "Pattern", "KzErP")
        if not _set_resource(doc, page, "Pattern", pname, f"{pxref} 0 R"):
            return done
        cs = rec["cs"]
        if cs != "/Pattern":
            csname = _free_name(doc, page, "ColorSpace", "KzErCS")
            _set_resource(doc, page, "ColorSpace", csname, cs)
            cs = "/" + csname
        outer = rec["rect"] + (-2, -2, 2, 2)
        lines = ["q"]
        for items, eo in rec["clips"]:
            lines.append(_path_str(items))
            lines.append("W* n" if eo else "W n")
        lines.append(f"{_fmt(outer.x0, outer.y0, outer.width, outer.height)} re "
                     f"{_fmt(box_pdf.x0, box_pdf.y0, box_pdf.width, box_pdf.height)} re W* n")
        comps = (_fmt(*rec["comps"]) + " ") if rec["comps"] else ""
        lines.append(f"{cs} cs {comps}/{pname} scn")
        lines.append(_path_str(rec["path"]))
        lines.append("f*" if rec["even_odd"] else "f")
        lines.append("Q")
        parts.append("\n".join(lines))
        done += 1
    if parts:
        page.wrap_contents()
        pymupdf.TOOLS._insert_contents(page, ("\n".join(parts) + "\n").encode("latin-1"), 1)
    return done
