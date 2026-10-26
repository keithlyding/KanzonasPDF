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


def attached(page, region, tol=1.0, share=0.6):
    """KanzonasPDF links lying mostly on region (what was made for the item that was there):
    at least `share` of the link's area. A link drawn by hand a little larger than the words
    still counts; a big link a small item merely sits in doesn't."""
    box = pymupdf.Rect(region) + (-tol, -tol, tol, tol)
    out = []
    for ln in read(page):
        if not ln["group"]:
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


def follow(page, old_rect, new_rect):
    """The item that was at old_rect is now at new_rect: its links go along."""
    o, r = pymupdf.Rect(old_rect), pymupdf.Rect(new_rect)
    links = attached(page, o)
    if not links:
        return 0
    sx = r.width / o.width if o.width else 1.0
    sy = r.height / o.height if o.height else 1.0
    m = pymupdf.Matrix(1, 0, 0, 1, -o.x0, -o.y0) * pymupdf.Matrix(sx, 0, 0, sy, r.x0, r.y0)
    transform(page, links, m)
    return len(links)
