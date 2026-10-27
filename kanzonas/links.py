"""Links made with KanzonasPDF (Links tool, right-click > Add link...).

A link may cover several areas that act as one (a selection over two lines of text), show
itself with an underline drawn into the page, a box or nothing, write its own text into the
page, and stay with the text, picture, shape or markup it was made for when that moves or
is deleted. What ties the pieces together is kept on each link annotation (other PDF readers
ignore it):

  /KZGroup  (id)          the link areas that act as one
  /KZLook   /U /B /N      underline, box, nothing
  /KZUnder  [x0 y0 x1 y1] the underline drawn into the page (unrotated page coordinates)
  /KZText   (text)        text this link wrote into the page (removed with the link)

All rectangles here are in unrotated page coordinates, like the rest of KanzonasPDF.
"""

import re
import uuid

import pymupdf

BLUE = (0.0, 0.35, 0.85)            # link text, underlines and boxes
LOOKS = ("underline", "box", "none")
_LOOK_KEY = {"underline": "/U", "box": "/B", "none": "/N"}
_KEY_LOOK = {v[1:]: k for k, v in _LOOK_KEY.items()}


def _pdf_string(text):
    """A PDF text string: UTF-16 hex when it isn't plain ASCII."""
    if all(32 <= ord(c) < 127 for c in text):
        return "(" + text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") + ")"
    return "<FEFF" + text.encode("utf-16-be").hex().upper() + ">"


def _rect_from_pdf(page, value):
    nums = [float(v) for v in re.findall(r"-?\d*\.?\d+(?:[eE]-?\d+)?", value)]
    if len(nums) < 4:
        return None
    return (pymupdf.Rect(nums[:4]) * ~page.transformation_matrix).normalize()


def _string(doc, xref, key):
    kind, val = doc.xref_get_key(xref, key)
    if kind != "string":
        return None
    return val


def read(page):
    """The page's link annotations: [{"xref", "rect", "group", "look", "under", "text"}].
    group is the /KZGroup id (None for links not made by KanzonasPDF)."""
    doc = page.parent
    out = []
    for xref, kind, *_ in page.annot_xrefs():
        if kind != pymupdf.PDF_ANNOT_LINK:
            continue
        rect = _rect_from_pdf(page, doc.xref_get_key(xref, "Rect")[1])
        if rect is None:
            continue
        look = doc.xref_get_key(xref, "KZLook")
        under = doc.xref_get_key(xref, "KZUnder")
        nums = [float(v) for v in re.findall(r"-?\d*\.?\d+", under[1])] if under[0] == "array" \
            else []
        out.append({"xref": xref, "rect": rect, "group": _string(doc, xref, "KZGroup"),
                    "look": _KEY_LOOK.get(look[1].lstrip("/")) if look[0] == "name" else None,
                    "under": nums[:4] if len(nums) >= 4 else None,
                    "text": _string(doc, xref, "KZText")})
    return out


def group(page, xref):
    """The link areas that act as one with link xref (just that one for other links)."""
    links = read(page)
    me = next((ln for ln in links if ln["xref"] == xref), None)
    if me is None:
        return []
    if not me["group"]:
        return [me]
    return [ln for ln in links if ln["group"] == me["group"]]


def _link_dict(rect, target):
    if target[0] == "page":
        return {"kind": pymupdf.LINK_GOTO, "from": rect, "page": target[1],
                "to": pymupdf.Point(0, 0)}
    return {"kind": pymupdf.LINK_URI, "from": rect, "uri": target[1]}


def _underline(page, rect, text_line=False):
    """Where the underline under rect goes, as seen on screen (the bottom of the rect as
    displayed), in unrotated page coordinates: just under the letters for a line of text,
    along the bottom edge for anything else."""
    disp = rect * page.rotation_matrix
    disp.normalize()
    y = disp.y1 - (0.14 * disp.height if text_line else 0)
    a = pymupdf.Point(disp.x0, y) * page.derotation_matrix
    b = pymupdf.Point(disp.x1, y) * page.derotation_matrix
    return a, b


def add(page, rects, target, look="box", text=None, text_lines=False):
    """Add one link over rects (all acting as one). target: ("uri", address) or ("page",
    index). look: "underline" (drawn into the page), "box" (a thin box readers draw) or
    "none". text: {"text", "origin" (baseline start), "size"} to write the link's own text
    into the page in link blue (rects are then its line). text_lines: the rects are lines
    of text (the underline goes just under the letters). Returns the group id."""
    from . import text_edit
    doc = page.parent
    rects = [pymupdf.Rect(r).normalize() for r in rects]
    words = None
    if text:
        words = " ".join(text["text"].split())
        origin = pymupdf.Point(text["origin"])
        text_edit.add_text(page, origin, words, size=text["size"], color=BLUE)
        rects = [_written_line(page, origin, words) or
                 pymupdf.Rect(origin.x, origin.y - text["size"], origin.x + len(words) *
                              text["size"] * 0.55, origin.y + text["size"] * 0.25)]
        text_lines = True
    gid = uuid.uuid4().hex[:12]
    for r in rects:
        if r.is_empty:
            continue
        before = {x for x, _k, *_ in page.annot_xrefs()}
        page.insert_link(_link_dict(r, target))
        new = [x for x, k, *_ in page.annot_xrefs()
               if x not in before and k == pymupdf.PDF_ANNOT_LINK]
        if not new:
            continue
        xref = new[0]
        doc.xref_set_key(xref, "KZGroup", _pdf_string(gid))
        doc.xref_set_key(xref, "KZLook", _LOOK_KEY.get(look, "/N"))
        if words:
            doc.xref_set_key(xref, "KZText", _pdf_string(words))
        if look == "box":
            doc.xref_set_key(xref, "BS", "<</W 1/S/S>>")
            doc.xref_set_key(xref, "C", "[%g %g %g]" % BLUE)
        else:
            doc.xref_set_key(xref, "Border", "[0 0 0]")
        if look == "underline":
            a, b = _underline(page, r, text_lines)
            page.draw_line(a, b, color=BLUE, width=0.75)
            doc.xref_set_key(xref, "KZUnder", "[%g %g %g %g]" % (a.x, a.y, b.x, b.y))
    return gid


def _written_line(page, origin, words):
    """The box of the line just written at origin."""
    from . import text_edit
    best = None
    for r, ln in text_edit.text_lines(page):
        o = pymupdf.Point(ln["spans"][0]["origin"])
        if abs(o.x - origin.x) < 1 and abs(o.y - origin.y) < 1 and \
                text_edit.line_text(ln).strip() == words:
            best = r
    return best


def _underline_shapes(page, unders):
    """Edit objects numbers of the underlines drawn for these links."""
    from . import page_objects
    if not unders:
        return [], None
    objs = page_objects.Objects(page)
    found = []
    for u in unders:
        a, b = pymupdf.Point(u[0], u[1]), pymupdf.Point(u[2], u[3])
        box = pymupdf.Rect(a, b).normalize()
        for it in objs.items:
            if it["kind"] == "shape" and it["n"] not in found and \
                    abs(it["rect"].x0 - box.x0) < 1 and abs(it["rect"].x1 - box.x1) < 1 and \
                    abs(it["rect"].y0 - box.y0) < 1 and abs(it["rect"].y1 - box.y1) < 1:
                found.append(it["n"])
                break
    return found, objs


def remove(page, links, keep_text=False):
    """Delete these links, their underlines and (unless keep_text) the text they wrote."""
    from . import page_objects, text_edit
    shapes, _objs = _underline_shapes(page, [ln["under"] for ln in links if ln["under"]])
    if shapes:
        page_objects.delete(page, shapes)
    if not keep_text:
        boxes = [ln["rect"] for ln in links if ln["text"]]
        if boxes:
            lines = [ln for r, ln in text_edit.text_lines(page)
                     if any(b.contains(pymupdf.Point((r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2))
                            for b in boxes)]
            if lines:
                text_edit.delete_lines(page, lines)
    for ln in links:
        page.delete_link({"xref": ln["xref"]})


def attached(page, region, tol=1.0, share=0.6, foreign=False):
    """KanzonasPDF links lying mostly on region (what was made for the item that was there):
    at least `share` of the link's area. A link drawn by hand a little larger than the words
    still counts; a big link a small item merely sits in doesn't. foreign: links the PDF
    came with count too (a paragraph moved with Edit text takes its links along)."""
    box = pymupdf.Rect(region) + (-tol, -tol, tol, tol)
    out = []
    for ln in read(page):
        if not ln["group"] and not foreign:
            continue
        r = ln["rect"]
        area = r.width * r.height
        if box.contains(r) or (area > 0 and abs(r & box) / area >= share):
            out.append(ln)
    return out


def transform(page, links, m):
    """Move links (and their underlines) with the item they belong to: m maps the item's
    old place to its new one (unrotated page coordinates)."""
    from . import page_objects
    doc = page.parent
    m = pymupdf.Matrix(m)
    shapes, objs = _underline_shapes(page, [ln["under"] for ln in links if ln["under"]])
    if shapes:
        page_objects.transform(page, shapes, m, objs)
    tm = page.transformation_matrix
    for ln in links:
        r = (ln["rect"] * m).normalize()
        pdf = (r * tm).normalize()
        doc.xref_set_key(ln["xref"], "Rect", "[%g %g %g %g]" % (pdf.x0, pdf.y0, pdf.x1, pdf.y1))
        if ln["under"]:
            a = pymupdf.Point(ln["under"][0], ln["under"][1]) * m
            b = pymupdf.Point(ln["under"][2], ln["under"][3]) * m
            doc.xref_set_key(ln["xref"], "KZUnder", "[%g %g %g %g]" % (a.x, a.y, b.x, b.y))


def follow(page, old_rect, new_rect, foreign=False):
    """The item that was at old_rect is now at new_rect: its links go along (foreign: the
    PDF's own links on it too)."""
    o, r = pymupdf.Rect(old_rect), pymupdf.Rect(new_rect)
    links = attached(page, o, foreign=foreign)
    if not links:
        return 0
    sx = r.width / o.width if o.width else 1.0
    sy = r.height / o.height if o.height else 1.0
    m = pymupdf.Matrix(1, 0, 0, 1, -o.x0, -o.y0) * pymupdf.Matrix(sx, 0, 0, sy, r.x0, r.y0)
    transform(page, links, m)
    return len(links)


# ---- copying pages ----------------------------------------------------------------------
# PyMuPDF's insert_pdf makes new links on the copied pages: only those going to pages copied
# in the same call, and without the keys above (or the link's color and border). Copying
# pages (Copy pages, Duplicate pages) copies the link annotations itself instead.
#
# A link to a page that isn't copied along is parked on the copy (no action, so other
# readers ignore it) until it's pasted:
#   /KZToPage  n        the page's object number in the document it was copied from
#   /KZFrom    (id)     that document (see DocumentView.pages_bytes)
#   /KZTo      (text)   the rest of the destination (/XYZ left top zoom, /Fit...)

_NOT_COPIED = {"Type", "Subtype", "Rect", "A", "Dest", "P", "NM", "Popup", "IRT",
               "StructParent", "KZToPage", "KZFrom", "KZTo"}
_REF = re.compile(r"\d+\s+\d+\s+R")


def _goto(doc, xref):
    """(page object number, rest of the destination) of a link to a page of its own
    document, else None."""
    for key in ("A", "Dest"):
        typ, val = doc.xref_get_key(xref, key)
        if typ == "xref":
            val = doc.xref_object(int(val.split()[0]), compressed=True)
        elif typ not in ("dict", "array"):
            continue
        if key == "A":
            if not re.search(r"/S\s*/GoTo(?![A-Za-z])", val):
                return None
            m = re.search(r"/D\s*\[\s*(\d+)\s+\d+\s+R([^\]]*)\]", val)
        else:
            m = re.match(r"\s*\[\s*(\d+)\s+\d+\s+R([^\]]*)\]", val)
        return (int(m.group(1)), m.group(2).strip()) if m else None
    return None


def _action(doc, xref):
    """The /A of a link going elsewhere (a web address, another file), to copy as it is;
    None when it refers to other objects of the document."""
    typ, val = doc.xref_get_key(xref, "A")
    if typ == "xref":
        val = doc.xref_object(int(val.split()[0]), compressed=True)
    elif typ != "dict":
        return None
    return None if _REF.search(val) else val


def _add_annot(doc, page_xref, rect, action, extras):
    new = doc.get_new_xref()
    doc.update_object(new, "<</Type/Annot/Subtype/Link/Rect%s%s/P %d 0 R%s>>"
                      % (rect, action, page_xref, "".join("/%s %s" % kv for kv in extras)))
    typ, val = doc.xref_get_key(page_xref, "Annots")
    if typ == "xref":
        arr = int(val.split()[0])
        doc.update_object(arr, doc.xref_object(arr, compressed=True).rstrip()[:-1] +
                          " %d 0 R]" % new)
    elif typ == "array":
        doc.xref_set_key(page_xref, "Annots", val.rstrip()[:-1] + " %d 0 R]" % new)
    else:
        doc.xref_set_key(page_xref, "Annots", "[%d 0 R]" % new)


def copy_page_links(src, pairs, dst, park=None, outside=None):
    """Copy the links on src's pages to their copies in dst, made with insert_pdf(...,
    links=False). pairs: [(page index in src, index of its copy in dst)]. A link to a page
    copied too goes to that copy. A link to a page not copied is parked on the copy when
    park (the id of src) is given, else left out. A parked link found in src goes where
    outside(id, page object number) says: a page object number in dst, or None (left out)."""
    copies = {src.page_xref(s): dst.page_xref(d) for s, d in pairs}
    for s, d in pairs:
        page_xref = dst.page_xref(d)
        named = {ln["xref"]: ln for ln in src[s].get_links()
                 if ln.get("kind") == pymupdf.LINK_NAMED and 0 <= ln.get("page", -1) < len(src)}
        for xref, kind, *_ in src[s].annot_xrefs():
            if kind != pymupdf.PDF_ANNOT_LINK:
                continue
            typ, rect = src.xref_get_key(xref, "Rect")
            if typ != "array":
                continue
            extras = []
            for key in src.xref_get_keys(xref):
                kt, kv = src.xref_get_key(xref, key)
                # (references to other objects can't come along)
                if key in _NOT_COPIED or kt in ("xref", "null") or \
                        kt != "string" and _REF.search(kv):
                    continue
                extras.append((key, _pdf_string(kv) if kt == "string" else kv))
            parked = src.xref_get_key(xref, "KZToPage")
            goto = _goto(src, xref)
            if goto is None and xref in named:
                # a named destination: the page and spot it names (in PDF coordinates)
                ln = named[xref]
                to = ln.get("to") or pymupdf.Point(0, 0)
                goto = (src.page_xref(ln["page"]),
                        "/XYZ %g %g %g" % (to.x, to.y, ln.get("zoom") or 0))
            if parked[0] == "int":
                target = outside(_string(src, xref, "KZFrom"), int(parked[1])) \
                    if outside else None
                if target is None:
                    continue
                action = "/A<</S/GoTo/D[%d 0 R %s]>>" % (target, _string(src, xref, "KZTo")
                                                         or "/XYZ null null 0")
            elif goto is not None:
                target = copies.get(goto[0])
                if target is not None:
                    action = "/A<</S/GoTo/D[%d 0 R %s]>>" % (target, goto[1])
                elif park is not None:
                    action = ""
                    extras += [("KZToPage", str(goto[0])), ("KZFrom", _pdf_string(park)),
                               ("KZTo", _pdf_string(goto[1]))]
                else:
                    continue
            else:
                action = _action(src, xref)
                if action is None:
                    continue
                action = "/A" + action
            _add_annot(dst, page_xref, rect, action, extras)
