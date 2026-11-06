"""Print production (1.8): what a sheet needs before it goes to a plotter or a print shop.

- Page boxes: the trim box (the finished size), the bleed box (how far the drawing may run
  past it, cut off after printing) and the art box, besides the crop box (what's shown).
  PyMuPDF keeps them in the same page coordinates as everything else (unrotated, top left).
- Fix hairlines: lines drawn thinner than a width (a width of 0 is "as thin as the device
  can draw": a plotter's thinnest line, often invisible) are drawn at that width, in the page's
  own drawing and in the drawing groups it places (Form XObjects, to any depth). Each line
  keeps everything else: the width is set inside its own  q ... Q  so what's drawn after it
  is unchanged. A line under a clip set in the same object is left alone.
- Check for printing: a short report of what often goes wrong at the printer: fonts not
  embedded, pictures of too low resolution at their printed size, RGB-only pictures, mixed
  sheet sizes, no trim or bleed box, hairlines. It is not a preflight against a printing
  standard (PDF/X): it finds the usual problems, it doesn't certify a file.
- Crop marks are drawn by the Print dialog (print_dialog.py), at print time only, from
  marks_layout() here.
"""
import math
import re

import pymupdf

from .i18n import tr

BOXES = ("trimbox", "bleedbox", "artbox")
KEYS = {"trimbox": "TrimBox", "bleedbox": "BleedBox", "artbox": "ArtBox"}
MARK_OFFSET = 6.0       # pt between the trim corner and the start of its crop mark
MARK_LENGTH = 18.0      # pt: the crop mark's length
MARK_WIDTH = 0.3        # pt: the crop mark's line width
LOW_DPI = 150           # a picture printed at fewer pixels per inch than this looks soft
_REF = re.compile(rb"/([^\s/<>\[\]()%{}]+)\s+(\d+)\s+0\s+R")


# ---- page boxes ---------------------------------------------------------------------------
def box_set(page, which):
    """True when the page has its own box `which` ("trimbox", "bleedbox", "artbox"); PyMuPDF
    answers with the crop box for one that isn't set."""
    return page.parent.xref_get_key(page.xref, KEYS[which])[0] != "null"


def page_box(page, which):
    """The page's box (unrotated page coordinates), or None when it isn't set."""
    return pymupdf.Rect(getattr(page, which)) if box_set(page, which) else None


def set_box(page, which, rect):
    """Set (rect: unrotated page coordinates, inside the media box) or remove (None) one
    box. Raises ValueError with a sentence to show when the box doesn't fit."""
    doc = page.parent
    if rect is None:
        doc.xref_set_key(page.xref, KEYS[which], "null")
        return
    rect = pymupdf.Rect(rect).normalize()
    media = page.mediabox
    if rect.width < 1 or rect.height < 1:
        raise ValueError(tr("The {box} would have no size.").format(box=box_label(which)))
    if not (media + (-0.01, -0.01, 0.01, 0.01)).contains(rect):
        raise ValueError(tr("The {box} would reach past the page's media box (its whole "
                            "sheet): use smaller margins.").format(box=box_label(which)))
    rect &= media
    getattr(page, "set_" + which)(rect)


def box_label(which):
    return {"trimbox": tr("trim box"), "bleedbox": tr("bleed box"),
            "artbox": tr("art box")}[which]


def margins_box(page, margins, base="cropbox"):
    """The rectangle `margins` (left, top, right, bottom, in points; positive = inward) in
    from the page's crop box (or media box), in unrotated page coordinates, measured as the
    page is shown (a turned page's left margin is its shown left side)."""
    rot = page.rotation_matrix
    shown = getattr(page, base) * rot
    left, top, right, bottom = margins
    r = pymupdf.Rect(shown.x0 + left, shown.y0 + top, shown.x1 - right, shown.y1 - bottom)
    return (r * page.derotation_matrix).normalize()


# ---- hairlines ----------------------------------------------------------------------------
def _scale(m):
    """How much matrix m scales a line's width (the square root of its area change)."""
    return math.sqrt(abs(m.a * m.d - m.b * m.c))


def _thin(found, threshold, outer):
    """The stroked paths in scan entries `found` drawn thinner than threshold (points on the
    page) at outer scale: [(entry, its width as drawn)]."""
    out = []
    for d in found:
        if not d.get("path") or not d.get("stroke"):
            continue
        w = d.get("width", 1.0) * _scale(d["ctm"]) * outer
        if w < threshold - 1e-6:
            out.append((d, w))
    return out


def _clipped(raw):
    """The object's own instructions set a clip (W, W*): it isn't wrapped (the Q would end
    the clip for what follows)."""
    return any(t in (b"W", b"W*") for t in raw.split())


def _forms_in(doc, owner_xref, page=None):
    """{b"/Name": form xref} of the drawing groups (Form XObjects) a page or a form draws."""
    out = {}
    if page is not None:
        for x in page.get_xobjects():
            xref, name, invoker = x[0], x[1], x[2]
            if invoker == 0 and doc.xref_get_key(xref, "Subtype")[1] == "/Form":
                out[("/" + name).encode()] = xref
        return out
    kind, res = doc.xref_get_key(owner_xref, "Resources")
    if kind == "xref":
        res_x = int(res.split()[0])
        kind, xo = doc.xref_get_key(res_x, "XObject")
    elif kind == "dict":
        kind, xo = doc.xref_get_key(owner_xref, "Resources/XObject")
    else:
        return out
    if kind == "xref":
        xo = doc.xref_object(int(xo.split()[0]), compressed=True)
    elif kind != "dict":
        return out
    for name, num in _REF.findall(xo.encode("latin-1", "replace")):
        x = int(num)
        if doc.xref_get_key(x, "Subtype")[1] == "/Form":
            out[b"/" + name] = x
    return out


def find_hairlines(page, threshold):
    """The lines on the page drawn thinner than threshold (points), in its drawing and in
    the drawing groups it places: {"page": [(entry, width)], "forms": {xref: {"scale": the
    smallest scale it's drawn at, "data": its bytes, "thin": [(entry, width)]}}, "count"}."""
    from . import page_objects
    doc = page.parent
    data = page_objects._contents(page)
    found = page_objects.scan(data)
    out = {"page": _thin(found, threshold, 1.0), "forms": {}, "page_data": data}
    scales = {}                         # form xref -> smallest scale it's drawn at

    def visit(entries, names, outer, depth):
        for d in entries:
            name = d.get("name")
            if not name or name not in names or depth > 8:
                continue
            fx = names[name]
            _box, fm = page_objects._form_box(doc, fx)
            fm = fm or pymupdf.Matrix(1, 0, 0, 1, 0, 0)
            s = outer * _scale(d["ctm"]) * _scale(fm)
            if fx in scales and scales[fx] <= s + 1e-9:
                continue                # (drawn at this scale or smaller already)
            scales[fx] = s
            try:
                inner = page_objects.scan(doc.xref_stream(fx) or b"")
            except Exception:
                continue
            visit(inner, _forms_in(doc, fx), s, depth + 1)
    visit(found, _forms_in(doc, page.xref, page), 1.0, 0)
    for fx, s in scales.items():
        fdata = doc.xref_stream(fx) or b""
        thin = _thin(page_objects.scan(fdata), threshold, s)
        if thin:
            out["forms"][fx] = {"scale": s, "data": fdata, "thin": thin}
    out["count"] = len(out["page"]) + sum(len(f["thin"]) for f in out["forms"].values())
    return out


def _widened(data, thin, width, outer):
    """data with each thin path's drawing wrapped in  q <w> w ... Q  so it's drawn width
    (points on the page) wide; how many were changed."""
    from . import page_objects
    pieces = []
    for d, _w in thin:
        old = data[d["start"]:d["end"]]
        if old[:2] == b"BI" or _clipped(old):
            continue
        state, body = page_objects._split(old)
        k = _scale(d["ctm"]) * outer
        w = width / k if k > 1e-12 else width
        new = (state + b" " if state else b"") + b"\nq %.4f w\n" % w + body + b"\nQ\n"
        pieces.append((d["start"], d["end"], new))
    return page_objects._splice(data, pieces), len(pieces)


def fix_hairlines(page, threshold, width):
    """Draw every line thinner than threshold at width (points), on this page and in the
    drawing groups it places (a group other pages place too gets its lines widened there as
    well). Returns how many lines were widened. Call inside DocumentView.modify."""
    from . import page_objects
    found = find_hairlines(page, threshold)
    n = 0
    if found["page"]:
        data, k = _widened(found["page_data"], found["page"], width, 1.0)
        if k:
            page_objects._set_contents(page, data)
            n += k
    for fx, f in found["forms"].items():
        data, k = _widened(f["data"], f["thin"], width, f["scale"])
        if k:
            page_objects._put_stream(page.parent, fx, data)
            n += k
    return n


# ---- check for printing -------------------------------------------------------------------
def check(doc, pages=None, hairline=0.25, low_dpi=LOW_DPI, step=None):
    """What may go wrong when these pages (all by default) are printed: a list of
    (kind, page index or None, text). kind: "fonts", "pictures", "rgb", "sizes", "boxes",
    "hairlines". step(i) is called before each page (for a progress bar; it may return False
    to stop)."""
    pages = list(range(doc.page_count)) if pages is None else list(pages)
    out = []
    fonts_seen = set()
    sizes = {}
    rgb_seen = set()
    for i in pages:
        if step is not None and step(i) is False:
            break
        page = doc[i]
        # fonts that aren't in the file: the printer (or its RIP) puts in another
        for f in page.get_fonts(full=True):
            xref, ext, ftype, base = f[0], f[1], f[2], f[3]
            if ext == "n/a" and ftype not in ("Type3",) and (xref, base) not in fonts_seen:
                fonts_seen.add((xref, base))
                out.append(("fonts", i, tr("Font not embedded: {font}").format(
                    font=base.split("+")[-1] or tr("(no name)"))))
        # pictures: their resolution as printed, and RGB-only ones
        for info in page.get_image_info(xrefs=True):
            w, h = info.get("width", 0), info.get("height", 0)
            bbox = pymupdf.Rect(info.get("bbox", (0, 0, 0, 0)))
            if w and h and bbox.width > 1 and bbox.height > 1:
                dpi = min(w / (bbox.width / 72.0), h / (bbox.height / 72.0))
                if dpi < low_dpi:
                    out.append(("pictures", i, tr("Picture at {dpi} pixels per inch as "
                                                  "printed ({w} × {h} pixels)").format(
                        dpi=int(round(dpi)), w=w, h=h)))
            x = info.get("xref", 0)
            cs = info.get("cs-name", "") or ""
            if x and "RGB" in cs and x not in rgb_seen:
                rgb_seen.add(x)
                out.append(("rgb", i, tr("Picture in RGB colors ({w} × {h} pixels): a "
                                         "four-color press converts it").format(w=w, h=h)))
        # sheet sizes (as shown, rounded to a point)
        r = page.rect
        sizes.setdefault((round(r.width), round(r.height)), []).append(i)
        if not box_set(page, "trimbox"):
            out.append(("boxes", i, tr("No trim box (the finished size): the printer "
                                       "trims to the page")))
        elif not box_set(page, "bleedbox") or page.bleedbox == page.trimbox:
            out.append(("boxes", i, tr("No bleed past the trim box: a drawing that runs to "
                                       "the edge may show a white line after trimming")))
        if hairline:
            n = find_hairlines(page, hairline)["count"]
            if n:
                out.append(("hairlines", i, (tr("{n} lines thinner than {w} pt (Fix "
                                                "hairlines widens them)") if n != 1 else
                                             tr("{n} line thinner than {w} pt (Fix hairlines "
                                                "widens it)")).format(n=n, w="%g" % hairline)))
    if len(sizes) > 1:
        for (w, h), where in sorted(sizes.items(), key=lambda kv: -len(kv[1])):
            out.append(("sizes", where[0], (tr("{n} pages of {w} × {h} pt ({inch}): pages "
                                                "{pages}") if len(where) != 1 else
                                             tr("{n} page of {w} × {h} pt ({inch}): page "
                                                "{pages}")).format(
                n=len(where), w=w, h=h, inch="%.2f × %.2f in" % (w / 72, h / 72),
                pages=_page_list(where))))
    return out


def _page_list(where, most=12):
    shown = ", ".join(str(i + 1) for i in where[:most])
    return shown + (", ..." if len(where) > most else "")


def kind_labels():
    return {"fonts": tr("Fonts not embedded"), "pictures": tr("Low-resolution pictures"),
            "rgb": tr("RGB pictures"), "sizes": tr("Mixed sheet sizes"),
            "boxes": tr("Trim and bleed"), "hairlines": tr("Hairlines")}


# ---- crop marks (at print time) -----------------------------------------------------------
def marks_layout(page):
    """Where crop marks go for this page, all as the page is shown (rotation applied):
    {"trim": the trim box (the crop box when none is set), "content": what's printed (the
    bleed box when one is set, else the trim box; within the crop box), "job": everything
    printed, marks included}."""
    rot = page.rotation_matrix
    shown = page.rect
    trim = (page.trimbox * rot) if box_set(page, "trimbox") else pymupdf.Rect(shown)
    trim &= shown
    content = (page.bleedbox * rot) & shown if box_set(page, "bleedbox") else pymupdf.Rect(trim)
    content |= trim
    reach = MARK_OFFSET + MARK_LENGTH
    job = pymupdf.Rect(trim.x0 - reach, trim.y0 - reach, trim.x1 + reach, trim.y1 + reach)
    job |= content
    return {"trim": trim, "content": content, "job": job}


def mark_lines(trim):
    """The crop marks around the trim box: [(x0, y0, x1, y1)] in the same coordinates, two
    short lines at each corner, outside the trim box, lined up with its edges."""
    o, n = MARK_OFFSET, MARK_OFFSET + MARK_LENGTH
    out = []
    for x, sx in ((trim.x0, -1), (trim.x1, 1)):
        for y, sy in ((trim.y0, -1), (trim.y1, 1)):
            out.append((x + sx * o, y, x + sx * n, y))      # along the horizontal edge
            out.append((x, y + sy * o, x, y + sy * n))      # along the vertical edge
    return out
