"""Edit objects: move, resize, rotate and delete the pictures that are part of a page's own
content (not markups), like PDF-XChange's Edit objects / Bluebeam's Edit content.

The page's content stream is read once to find each picture: an image XObject drawn with
"/Name Do" or an inline image (BI ... EI), with the transformation in effect at that point.
An edit rewrites only that one drawing instruction:
  move / resize / rotate: wrapped as  q <M> cm <instruction> Q
  delete:                 removed
so the picture keeps its place in the drawing order (text drawn over it stays over it) and
its data is never decoded or re-encoded. Pictures inside Form XObjects aren't editable.
"""

import re

import pymupdf

_TOKEN = re.compile(rb"\s+|%[^\r\n]*|/[^\s/\[\]()<>{}%]*|<<|>>|<[0-9A-Fa-f\s]*>|[\[\]{}]|"
                    rb"\(|[^\s/\[\]()<>{}%]+")
_WS = b" \t\r\n\f\x00"


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
    except ValueError:
        return None


def scan(data):
    """Picture drawing instructions in a content stream, in drawing order:
    [{"start", "end", "ctm": Matrix (unit square -> PDF space), "name": b"/Im1" or None}]."""
    out = []
    ctm = pymupdf.Matrix(1, 0, 0, 1, 0, 0)
    stack = []
    operands = []
    i, n = 0, len(data)
    op_start = None                     # where the current operands began
    while i < n:
        if data[i] == 0x28:             # "(" literal string
            if op_start is None:
                op_start = i
            i = _skip_string(data, i)
            operands.append(None)
            continue
        m = _TOKEN.match(data, i)
        if m is None:
            i += 1
            continue
        tok = m.group()
        j = m.end()
        c = tok[:1]
        if c in b" \t\r\n\f\x00" or c == b"%":
            i = j
            continue
        if c in b"/<[]{}" or (c in b"+-.0123456789" and _num(tok) is not None):
            if op_start is None:
                op_start = i
            operands.append(tok)
            i = j
            continue
        # an operator
        start = op_start if op_start is not None else i
        if tok == b"q":
            stack.append(ctm)
        elif tok == b"Q":
            if stack:
                ctm = stack.pop()
        elif tok == b"cm" and len(operands) >= 6:
            vals = [_num(t) if isinstance(t, bytes) else None for t in operands[-6:]]
            if None not in vals:
                ctm = pymupdf.Matrix(*vals) * ctm
        elif tok == b"Do" and operands and isinstance(operands[-1], bytes) \
                and operands[-1].startswith(b"/"):
            out.append({"start": start, "end": j, "ctm": pymupdf.Matrix(ctm),
                        "name": operands[-1]})
        elif tok == b"BI":
            k = data.find(b"ID", j)
            while k >= 0 and not (data[k - 1] in _WS and (k + 2 >= n or data[k + 2] in _WS)):
                k = data.find(b"ID", k + 2)
            if k < 0:
                break
            end = _inline_end(data, k + 3)
            out.append({"start": i, "end": end, "ctm": pymupdf.Matrix(ctm), "name": None})
            j = end
        operands = []
        op_start = None
        i = j
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


def images(page):
    """The page's editable pictures, in drawing order:
    [{"n": index, "rect": Rect (unrotated page coordinates), "xref": int or 0 (inline)}]."""
    data = _contents(page)
    if b"Do" not in data and b"BI" not in data:
        return []
    doc = page.parent
    names = {}
    for it in page.get_images(full=True):
        if it[-1] == 0:                 # drawn by the page itself, not inside a form
            names[("/" + it[7]).encode()] = it[0]
    tm = page.transformation_matrix
    out = []
    for k, d in enumerate(scan(data)):
        if d["name"] is None:
            xref = 0
        else:
            xref = names.get(d["name"])
            if xref is None:
                continue                # a form or something else, not a picture
        r = pymupdf.Rect(0, 0, 1, 1).transform(d["ctm"] * tm)
        if r.is_empty or abs(d["ctm"].a * d["ctm"].d - d["ctm"].b * d["ctm"].c) < 1e-12:
            continue
        out.append({"n": k, "rect": r, "xref": xref,
                    "quad": pymupdf.Rect(0, 0, 1, 1).quad.transform(d["ctm"] * tm)})
    return out


def _edit(page, n, new):
    """Replace drawing instruction number n with new(old_bytes, ctm)."""
    data = _contents(page)
    found = scan(data)
    if n >= len(found):
        raise ValueError("The picture is no longer on the page.")
    d = found[n]
    piece = new(data[d["start"]:d["end"]], d["ctm"])
    _set_contents(page, data[:d["start"]] + piece + data[d["end"]:])


def transform(page, n, t_page):
    """Apply t_page (a Matrix in unrotated page coordinates) to picture n."""
    tm = page.transformation_matrix
    t_pdf = tm * t_page * ~tm

    def new(old, ctm):
        m = ctm * t_pdf * ~ctm
        return (b"q %.6f %.6f %.6f %.6f %.4f %.4f cm " % tuple(m) + old + b" Q")
    _edit(page, n, new)


def move_to(page, n, old_rect, new_rect):
    """Move / scale picture n so its box old_rect becomes new_rect."""
    o, r = pymupdf.Rect(old_rect), pymupdf.Rect(new_rect)
    sx, sy = r.width / o.width, r.height / o.height
    t = pymupdf.Matrix(1, 0, 0, 1, -o.x0, -o.y0) * pymupdf.Matrix(sx, 0, 0, sy, r.x0, r.y0)
    transform(page, n, t)


def rotate(page, n, rect, degrees):
    """Turn picture n about its center (positive = clockwise as shown)."""
    r = pymupdf.Rect(rect)
    c = (r.tl + r.br) / 2
    t = pymupdf.Matrix(1, 0, 0, 1, -c.x, -c.y) * pymupdf.Matrix(degrees) * \
        pymupdf.Matrix(1, 0, 0, 1, c.x, c.y)
    transform(page, n, t)


def delete(page, n):
    _edit(page, n, lambda old, ctm: b" ")
