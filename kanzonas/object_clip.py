"""Copy and paste the page's own pictures and shapes (Edit objects, CAD mode's selection), to
another page or another open document, as real page content again.

Copying (take): each selected object's drawing instructions are written out to draw the same
on their own, in the page's PDF space: its transformation, colors, line style, transparency
(ExtGState) and the clipping paths in effect at it (a clip that is the object's own, such as
a "Print to PDF" strip's window, comes as it was written), as

    q <clip ctm> cm <clip path> W n ... <its ctm> cm <its state> <its instructions> Q

(objects in a row that share all of that share one q ... Q). The resources they use
(pictures with their soft masks, forms, ExtGState, color spaces, patterns, shadings, layers)
are copied once into a small PDF of the clipboard's own (MuPDF's graft), so the copy stays
whole when the document it came from changes or is closed.

Pasting (put): the instructions go into the page as one new content stream after what's
there,  q <the move> cm ... Q,  so each object is ordinary page content again (Edit objects
selects, moves, deletes and copies it as before; a group stays the group it was). The
resources go into the page under names it doesn't use yet:
- pasted in the document it was copied from, the objects it used are used again (a picture
  isn't stored twice) and the layers stay (the content stays in its layer);
- in another document they're copied in, once per document however often it's pasted (the
  copies are remembered, and checked to still be there after an undo); layer membership is
  dropped there (the content shows as if on no layer): the other document doesn't have the
  layer, and adding one is a Layers decision for the person.
A pattern fill is laid out in the page's own space, not the shape's: each paste gets its
pattern again with its matrix moved along, so the fill moves with the shape.
"""

import re

import pymupdf

from . import page_objects as po
from . import pdfcoords

m = pymupdf.mupdf
_NAME = re.compile(rb"/([^\s/\[\]()<>{}%]+)")
_CATS = ("XObject", "ExtGState", "ColorSpace", "Pattern", "Shading", "Properties", "Font")
_OC_BDC = re.compile(rb"^/OC\s*/([^\s/\[\]()<>{}%]+)\s*BDC$")


def _fmt(mat):
    return b"%.6f %.6f %.6f %.6f %.4f %.4f cm" % tuple(mat)


def _invertible(mat):
    return abs(mat.a * mat.d - mat.b * mat.c) > 1e-12


def _pdf(doc):
    return pymupdf._as_pdf_document(doc)


def _page_resources(doc, page):
    """The page's resource dictionary (pdf_obj, inherited one included), or None."""
    obj = m.pdf_lookup_page_obj(_pdf(doc), page.number)
    res = m.pdf_dict_get_inheritable(obj, m.pdf_new_name("Resources"))
    return res if res.m_internal and m.pdf_is_dict(res) else None


def _head_and_data(piece):
    """(the part of an object's instructions whose names are resource names, the rest): an
    inline picture's data after ID is left alone."""
    if piece[:2] == b"BI":
        k = piece.find(b"ID")
        while k >= 0 and not (piece[k - 1:k] in (b" ", b"\n", b"\r", b"\t") and
                              piece[k + 2:k + 3] in (b" ", b"\n", b"\r", b"\t", b"")):
            k = piece.find(b"ID", k + 2)
        if k > 0:
            return piece[:k], piece[k:]
    return piece, b""


def _own_span_ctm(data, q0, s, ctm):
    """The matrix in effect at data[q0] for an object at data[s] drawn with ctm (the
    matrices set between them taken back), or None."""
    inner, stack = pymupdf.Matrix(1, 0, 0, 1, 0, 0), []
    for op, args, _s, _e in po._tokens(data[q0:s]):
        if op == b"q":
            stack.append(inner)
        elif op == b"Q":
            if stack:
                inner = stack.pop()
        elif op == b"cm" and len(args) >= 6:
            try:
                inner = pymupdf.Matrix(*[float(v) for v in args[-6:]]) * inner
            except (TypeError, ValueError):
                return None
    if not _invertible(inner):
        return None
    return ~inner * ctm


def _layer(ctx):
    """The layer (a /Properties name) the marked content around an object puts it in, or
    None: only /OC /Name BDC counts (structure tags and other marks aren't the object's)."""
    for bdc in reversed(ctx[0] if ctx else ()):
        mo = _OC_BDC.match(bdc.strip())
        if mo:
            return mo.group(1)
    return None


def _instructions(data, found, ns, clip_paths):
    """[(bytes, layer name or None)] drawing objects ns on their own, in PDF space."""
    starts = [x["start"] for x in found]
    groups = []                          # [key, [bodies], head, layer]
    heads = {}
    for n in sorted(set(ns)):
        d = found[n]
        s, e, ctm = d["start"], d["end"], d["ctm"]
        ctx = d.get("ctx") or ((), ())
        clip_ids = ctx[1]
        own = None
        inner = clip_paths[clip_ids[-1]][0] if clip_ids and clip_ids[-1] < len(clip_paths) \
            else None
        if inner is not None and (n == 0 or inner > found[n - 1]["start"]):
            # (its own clip is set after the object before it: a clip set earlier, as a
            # sheet's frame, is many objects', and isn't looked for each of them)
            span = po._own_clip_span(data, starts, s, e)
            if span is not None:
                at_q = _own_span_ctm(data, span[0], s, ctm)
                if at_q is not None:
                    own = (span, at_q)
        body = data[s:e] if own is None else data[own[0][0]:own[0][1]]
        mat = ctm if own is None else own[1]
        layer = _layer(ctx)
        state = d.get("state", b"")
        key = (tuple(mat), state, clip_ids, layer, own[0][0] if own is not None else None)
        if groups and groups[-1][0] == key and own is None:
            groups[-1][1].append(body)
            continue
        hk = (key[0], clip_ids, own[0][0] if own is not None else None)
        head = heads.get(hk)
        if head is None:
            # the clipping paths in effect that aren't its own, then its matrix
            prefix, prev = [], pymupdf.Matrix(1, 0, 0, 1, 0, 0)
            for cid in clip_ids:
                if cid >= len(clip_paths):
                    continue
                ps, pe, cctm = clip_paths[cid]
                if ps is None or (own is not None and ps >= own[0][0]) or \
                        not _invertible(prev):
                    continue
                prefix.append(_fmt(cctm * ~prev) + b"\n" + data[ps:pe] + b" n")
                prev = cctm
            head = heads[hk] = b"\n".join(prefix + [_fmt(mat * ~prev)]) \
                if _invertible(prev) else False
        if head is False:
            continue
        groups.append([key, [body], head + b"\n" + state, layer])
    return [(b"q\n" + head + b"\n" + b"\n".join(bodies) + b"\nQ", layer)
            for _key, bodies, head, layer in groups]


_INLINE = re.compile(rb"((?<=\s)BI\s.*?\sID\s.*?\sEI(?=\s|$))", re.S)


def _outside_pictures(content):
    """[(text, True: names in it are resource names)] of content, an inline picture's data
    after ID left out (False)."""
    out = []
    for k, part in enumerate(_INLINE.split(content)):
        if k % 2 and part.startswith(b"BI"):
            head, rest = _head_and_data(part)
            out += [(head, True), (rest, False)]
        else:
            out.append((part, True))
    return out


def _names_in(pieces):
    names = set()
    for piece, _layer in pieces:
        for text, names_here in _outside_pictures(piece):
            if names_here:
                names.update(_NAME.findall(text))
    return {n.decode("latin-1") for n in names}


def take(doc, page, ns, objs=None, uid=None):
    """Copy objects ns of page (Edit objects numbers) for the clipboard: {"pieces" (the
    instructions, PDF space of page, each with its layer's name or None), "doc" (a PDF holding
    the resources they use, under their names on page), "res" {(category, name): its object
    number there}, "same" {(category, name): (value as written on page, check)} to use
    them again in the document they came from, "uid" (that document's), "to_shown" (Matrix:
    PDF space -> page as shown), "count"}."""
    data = po._contents(page)
    if objs is not None and objs.found and objs.data == data:
        found = objs.found
    else:
        found = po.scan(data)
    sel = [n for n in sorted(set(ns)) if n < len(found)]
    if not sel:
        return None
    clip_paths = []
    if any((found[n].get("ctx") or ((), ()))[1] for n in sel):
        found, clip_paths = po.scan_with_clips(data)     # (the clips' own paths)
    pieces = _instructions(data, found, sel, clip_paths)
    layers = {p[1].decode("latin-1") for p in pieces if p[1]}
    names = _names_in(pieces) | layers
    res = _page_resources(doc, page)
    cdoc = pymupdf.open()
    cdoc.new_page(width=10, height=10)
    cpdf = _pdf(cdoc)
    graft = m.pdf_new_graft_map(cpdf)
    got, same = {}, {}
    for cat in _CATS:
        cd = m.pdf_dict_get(res, m.pdf_new_name(cat)) if res is not None else None
        if cd is None or not m.pdf_is_dict(cd):
            continue
        for name in sorted(names):
            val = m.pdf_dict_gets(cd, name)
            if not val.m_internal:
                continue
            if cat == "Properties" and name not in layers:
                continue
            g = m.pdf_graft_mapped_object(graft, val)
            if not m.pdf_is_indirect(g):
                g = m.pdf_add_object(cpdf, g)
            got[(cat, name)] = m.pdf_to_num(g)
            if m.pdf_is_indirect(val):
                num = m.pdf_to_num(val)
                same[(cat, name)] = ("%d 0 R" % num, check(doc, num))
    import uuid
    return {"pieces": pieces, "doc": cdoc, "res": got, "same": same, "uid": uid,
            "token": uuid.uuid4().hex, "layers": layers,
            "to_shown": pdfcoords.to_page(page) * page.rotation_matrix}


def _content(clip, layers=True):
    """The copied instructions; layers: in their layers (/OC /Name BDC ... EMC)."""
    out = []
    for piece, layer in clip["pieces"]:
        if layer and layers:
            piece = b"/OC /" + layer + b" BDC\n" + piece + b"\nEMC"
        out.append(piece)
    return b"\n".join(out)


def check(doc, num):
    """What tells an object is still the one it was: (stream?, Type, Subtype, length)."""
    try:
        if num <= 0 or num >= doc.xref_length():
            return None
        stream = doc.xref_is_stream(num)
        return (stream, doc.xref_get_key(num, "Type")[1], doc.xref_get_key(num, "Subtype")[1],
                doc.xref_get_key(num, "Length")[1] if stream else "",
                doc.xref_get_key(num, "Width")[1])
    except Exception:
        return None


def _taken(doc, page):
    """{category: names the page's resources have}."""
    po._own_resources(page)
    return {cat: set(po._res_entries(doc, page.xref, "Resources/" + cat)) for cat in _CATS}


def _cache(doc):
    """What doc remembers of pastes into it: {"maps": {clip token: graft map}, "objs":
    {(clip token, number in the clip's PDF): (number in doc, check)}}."""
    got = getattr(doc, "_kz_pasted", None)
    if got is None:
        got = doc._kz_pasted = {"maps": {}, "objs": {}}
    return got


def _grafted(doc, clip, keys):
    """{key: object number in doc} of clip's resources keys, copied in from the clipboard's
    PDF once per document: the copies an earlier paste made are used again while they're
    all still there (an undo takes them away); else all of them are copied in anew."""
    memo = _cache(doc)
    tok = clip["token"]
    have = {k: memo["objs"].get((tok, clip["res"][k])) for k in keys}
    if keys and tok in memo["maps"] and all(
            h is not None and check(doc, h[0]) == h[1] for h in have.values()):
        return {k: h[0] for k, h in have.items()}
    graft = memo["maps"][tok] = m.pdf_new_graft_map(_pdf(doc))
    out = {}
    for k in keys:
        num = clip["res"][k]
        ref = m.pdf_graft_mapped_object(graft, m.pdf_new_indirect(_pdf(clip["doc"]), num, 0))
        new = out[k] = m.pdf_to_num(ref)
        memo["objs"][(tok, num)] = (new, check(doc, new))
    return out


def _moved_pattern(doc, num, mat):
    """A copy of pattern num whose matrix is moved by mat (its fill moves with the shape)."""
    kind, val = doc.xref_get_key(num, "Matrix")
    old = pymupdf.Matrix(1, 0, 0, 1, 0, 0)
    if kind == "array":
        try:
            old = pymupdf.Matrix(*[float(v) for v in val.strip("[] ").split()])
        except (TypeError, ValueError):
            pass  # (not a matrix: the one set before stays)
    new = doc.get_new_xref()
    doc.update_object(new, doc.xref_object(num, compressed=True))
    if doc.xref_is_stream(num):
        data = doc.xref_stream(num)
        for key in ("Filter", "DecodeParms", "Length"):
            doc.xref_set_key(new, key, "null")
        doc.update_stream(new, data)
    doc.xref_set_key(new, "Matrix", "[%s]" % " ".join("%.6f" % v for v in tuple(old * mat)))
    return new


def put(doc, page, clip, mat, uid=None):
    """Draw clip (take's) on page, its PDF space mapped by mat onto the page's PDF space.
    Run inside DocumentView.modify. Returns the start of what was written in the page's
    content (po._contents), where the pasted objects' instructions begin."""
    same_doc = uid is not None and uid == clip.get("uid")
    po._own_resources(page)
    values, wanted = {}, []
    for (cat, name), _num in sorted(clip["res"].items()):
        if same_doc and (cat, name) in clip["same"]:
            text, chk = clip["same"][(cat, name)]
            num = int(text.split()[0])
            if check(doc, num) == chk:
                values[(cat, name)] = num       # (the very object, used again)
                continue
        if cat == "Properties" and not same_doc:
            continue                    # (another document: the layer isn't there)
        wanted.append((cat, name))
    values.update(_grafted(doc, clip, wanted))
    for key in [k for k in values if k[0] == "Pattern"]:
        values[key] = _moved_pattern(doc, values[key], mat)
    have = {cat: po._res_entries(doc, page.xref, "Resources/" + cat) for cat in _CATS}
    used = set().union(*[set(v) for v in have.values()])
    by_name = {}
    for (cat, name), value in values.items():
        by_name.setdefault(name, []).append((cat, value))
    rename = {}
    for name, entries in sorted(by_name.items()):
        if all(have[cat].get(name) == ("xref", "%d 0 R" % v) for cat, v in entries):
            continue                    # (the page has these very ones under this name)
        new = name
        if name in used:
            k = 1
            while "KZc%d%s" % (k, name) in used:
                k += 1
            new = "KZc%d%s" % (k, name)
        used.add(new)
        rename[name] = new
        for cat, v in entries:
            po._set_resource(doc, page.xref, cat, new, "%d 0 R" % v)
    content = _content(clip, layers=same_doc)
    swap = {k.encode("latin-1"): v.encode("latin-1") for k, v in rename.items() if k != v}
    if swap:
        content = _renamed(content, swap)
    data = b"q\n" + _fmt(mat) + b"\n" + content + b"\nQ\n"
    page.wrap_contents()                # (what's there leaves the state as it found it)
    xref = pymupdf.TOOLS._insert_contents(page, b" ", True)
    po._put_stream(doc, xref, data)
    return len(po._contents(page)) - len(data)


def _renamed(content, swap):
    """content with the resource names in swap ({old: new}) changed, outside inline
    pictures' data."""
    pat = re.compile(rb"/(" + b"|".join(re.escape(k) for k in sorted(swap, key=len, reverse=True))
                     + rb")(?=[\s/\[\]()<>{}%]|$)")
    return b"".join(pat.sub(lambda mo: b"/" + swap[mo.group(1)], text) if names else text
                    for text, names in _outside_pictures(content))


PICTURE_LIMIT = 300_000          # instructions' bytes up to which a picture is made (quick)


def picture(clip, box, dpi=150, limit=2_000_000):
    """A PNG of the copied objects (for other programs), box: where they are as shown on
    their page; or None (also for a big drawing: it isn't worth the wait)."""
    if sum(len(b) for b, _l in clip["pieces"]) > PICTURE_LIMIT:
        return None
    try:
        w, h = max(box.width, 1), max(box.height, 1)
        cdoc = pymupdf.open()
        pg = cdoc.new_page(width=w, height=h)
        # (shown on their page) -> this page's PDF space: shifted to the box, y up
        mat = clip["to_shown"] * pymupdf.Matrix(1, 0, 0, 1, -box.x0, -box.y0) * \
            pymupdf.Matrix(1, 0, 0, -1, 0, h)
        put(cdoc, pg, clip, mat)
        zoom = min(dpi / 72, (limit / (w * h)) ** 0.5)
        png = pg.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=True).tobytes("png")
        cdoc.close()
        return png
    except Exception:
        return None
