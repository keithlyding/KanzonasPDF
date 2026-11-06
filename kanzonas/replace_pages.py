"""Pages > Replace pages...: a sheet's drawing swapped for a new revision's, keeping its markups
(Acrobat's Replace Pages; Bluebeam's Batch Slip Sheet).

The page object stays: only what draws the page (its content streams, resources, page boxes,
rotation, transparency group, user unit) is taken from the new file's page, copied in with
MuPDF's graft map (one for the whole replacement, so fonts and pictures the new sheets share
come in once). Everything that points at the page (bookmarks, links from other pages, named
destinations) and everything kept on it (markups, links, form fields, its scale) stays.

Markups are kept in PDF user space, which may differ between the old drawing and the new one
(other page boxes, another rotation, another size). They are mapped from the old page as
displayed to the new page as displayed: at the same spot measured from the top-left corner,
or scaled to the new page. Each markup is moved where it is (its position keys and the
geometry KanzonasPDF keeps in KZProps mapped, its appearance reused: it fits itself to the
new /Rect), never written anew, so markups of other programs come through exactly too.

What was drawn into the old page belongs to the old drawing and goes with it: the underline
of a link made with KanzonasPDF and the text a link wrote are drawn again on the new drawing;
a link over words that aren't at the same place on the new drawing is reported to check.
The layers the new drawings use join the document's /OCProperties, and MuPDF reads its list
of layers again (undo_journal.reload_layers), so a layer that is off in the new file is off.
"""

import json
import re

import pymupdf

from . import annotations, links, measure, pdfcoords, sheets, undo_journal
from .i18n import tr

m = pymupdf.mupdf

# the keys that make the drawing: taken from the new page (inheritable ones looked up through
# the new file's page tree), removed from the page when the new one has none
_INHERITED = ("Resources", "MediaBox", "CropBox", "Rotate")
_OWN = ("Contents", "TrimBox", "BleedBox", "ArtBox", "BoxColorInfo", "Group", "UserUnit",
        "VP", "SeparationInfo", "PZ", "Metadata")
# kept about the old drawing only: dropped (a thumbnail picture of it, another program's data)
_STALE = ("Thumb", "PieceInfo", "LastModified")

# annotation keys holding x y pairs in PDF user space (InkList: lists of them)
_PAIRS = ("Vertices", "L", "QuadPoints", "InkList", "CL")
# fixed-size icons (a note, a file attachment, a note's pop-up): moved, not resized
_ICONS = (pymupdf.PDF_ANNOT_TEXT, pymupdf.PDF_ANNOT_FILE_ATTACHMENT, pymupdf.PDF_ANNOT_POPUP)
_NUMBER = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")
TOL = 0.5                   # points: page sizes closer than this are the same size


# ---- which pages ---------------------------------------------------------------------------
def pairs_by_numbers(here, new, n_here, n_new):
    """[(page index here, page index in the new file)] for page ranges typed as '3-5, 8'
    (here) and '1-4' (the new file), paired in order. ValueError when a range is wrong or
    they don't hold as many pages."""
    if not (here or "").strip() or not (new or "").strip():
        raise ValueError(tr("Type the pages to replace and the pages of the new file."))
    a = _ranges(here, n_here)
    b = _ranges(new, n_new)
    if len(a) != len(b):
        raise ValueError(tr("{here} page(s) to replace but {new} page(s) of the new file: "
                            "give as many of each.").format(here=len(a), new=len(b)))
    return list(zip(a, b))


def _ranges(text, count):
    """Page indices for '1-3, 7' in the order typed (each page once)."""
    from .page_tools import parse_pages
    out = []
    for part in text.replace(" ", "").split(","):
        if part:
            for i in parse_pages(part, count):
                if i not in out:
                    out.append(i)
    return out


def match_sheets(here, new, step=None):
    """Pages paired by the sheet number in their title blocks (sheets.sheet_info, as Link
    sheet callouts reads them). Returns {"here": [info or None], "new": [info or None],
    "pairs": {page index here: page index in new}}. A sheet number found on several pages
    of the new file takes its first one. step(): called after each page read (a progress
    bar; it may raise to stop)."""
    infos_here, infos_new = [], []
    for doc, out in ((here, infos_here), (new, infos_new)):
        for i in range(doc.page_count):
            try:
                out.append(sheets.sheet_info(doc[i]))
            except Exception:           # an odd page must not stop the others
                out.append(None)
            if step is not None:
                step()
    by_key = {}
    for j, info in enumerate(infos_new):
        if info:
            by_key.setdefault(sheets.norm(info["number"]), j)
    pairs = {}
    for i, info in enumerate(infos_here):
        if info and sheets.norm(info["number"]) in by_key:
            pairs[i] = by_key[sheets.norm(info["number"])]
    return {"here": infos_here, "new": infos_new, "pairs": pairs}


def sizes_differ(here, new, pairs):
    """The pairs whose pages have another size as displayed."""
    out = []
    for i, j in pairs:
        a, b = here[i].rect, new[j].rect
        if abs(a.width - b.width) > TOL or abs(a.height - b.height) > TOL:
            out.append((i, j))
    return out


# ---- replacing -----------------------------------------------------------------------------
def _display(page):
    """Matrix from PDF user space to the page as displayed (MuPDF's own)."""
    return pdfcoords.to_page(page) * page.rotation_matrix


def _is_identity(mat, tol=1e-6):
    return all(abs(x - y) <= tol for x, y in zip(mat, (1, 0, 0, 1, 0, 0)))


def replace(doc, src, pairs, scale=True):
    """Give the pages of doc the drawings of src's pages: pairs [(page index in doc, page
    index in src)]. scale: markups on a page whose size changes are scaled to the new page
    (else kept at the same spot from the top-left corner). src is only read. Run it inside
    DocumentView.modify (one undo step). Returns {"pages": count, "markups": markups moved,
    "check": [(page index, links over words that moved)], "relinked": links drawn again}."""
    pdf = pymupdf._as_pdf_document(doc)
    spdf = pymupdf._as_pdf_document(src)
    graft = m.pdf_new_graft_map(pdf)
    report = {"pages": 0, "markups": 0, "check": [], "relinked": 0}
    for i, j in pairs:
        page = doc[i]
        new = src[j]
        # what belongs to the old drawing, read before it goes
        before = _display(page)
        old_to_pdf = pdfcoords.to_pdf(page)
        old_rect = page.rect
        old_links = links.read(page)
        words = _link_words(page, old_links)
        texts = _link_texts(page, old_links)
        _graft_drawing(doc, pdf, i, spdf, j, graft)
        _sync(page)
        after = _display(page)
        k = (page.rect.width / old_rect.width if old_rect.width else 1.0,
             page.rect.height / old_rect.height if old_rect.height else 1.0)
        if not scale or (abs(old_rect.width - page.rect.width) <= TOL and
                         abs(old_rect.height - page.rect.height) <= TOL):
            k = (1.0, 1.0)
        # old PDF space -> new PDF space, through the page as displayed
        t = before * pymupdf.Matrix(k[0], 0, 0, k[1], 0, 0) * ~after
        tp = old_to_pdf * t * pdfcoords.to_page(page)     # old page coords -> new page coords
        if not _is_identity(t):
            report["markups"] += _map_annots(doc, page, t, tp)
            _map_scale(doc, page, k)
        _take_scale(doc, src, page, new)
        report["relinked"] += _redraw_links(page, old_links, texts, tp, k)
        moved = _moved_words(page, old_links, words, tp)
        if moved:
            report["check"].append((i, moved))
        _sync(page)
        report["pages"] += 1
    _register_layers(doc, pdf, spdf, graft, [j for _i, j in pairs])
    return report


# ---- layers (optional content) of the new drawings -----------------------------------------
def _used_layers(spdf, pages):
    """Object numbers of the layers (OCGs) the new file's pages draw with: named in their
    resources' /Properties (directly or through a membership dictionary) or on their forms
    and pictures (/OC), at any depth."""
    found, seen = set(), set()
    name = m.pdf_new_name

    def layer(obj):
        if not obj.m_internal or not m.pdf_is_dict(obj):
            return
        typ = m.pdf_dict_get(obj, name("Type"))
        if m.pdf_name_eq(typ, name("OCG")) and m.pdf_is_indirect(obj):
            found.add(m.pdf_to_num(obj))
        elif m.pdf_name_eq(typ, name("OCMD")):
            ocgs = m.pdf_dict_get(obj, name("OCGs"))
            if m.pdf_is_array(ocgs):
                for k in range(m.pdf_array_len(ocgs)):
                    layer(m.pdf_array_get(ocgs, k))
            else:
                layer(ocgs)

    def walk(res):
        if not res.m_internal or not m.pdf_is_dict(res):
            return
        if m.pdf_is_indirect(res):
            if m.pdf_to_num(res) in seen:
                return
            seen.add(m.pdf_to_num(res))
        props = m.pdf_dict_get(res, name("Properties"))
        if m.pdf_is_dict(props):
            for k in range(m.pdf_dict_len(props)):
                layer(m.pdf_dict_get_val(props, k))
        xobjs = m.pdf_dict_get(res, name("XObject"))
        if m.pdf_is_dict(xobjs):
            for k in range(m.pdf_dict_len(xobjs)):
                x = m.pdf_dict_get_val(xobjs, k)
                if not m.pdf_is_dict(x) or (m.pdf_is_indirect(x) and m.pdf_to_num(x) in seen):
                    continue
                if m.pdf_is_indirect(x):
                    seen.add(m.pdf_to_num(x))
                layer(m.pdf_dict_get(x, name("OC")))
                walk(m.pdf_dict_get(x, name("Resources")))
    for j in set(pages):
        walk(m.pdf_dict_get_inheritable(m.pdf_lookup_page_obj(spdf, j), name("Resources")))
    return found


def _register_layers(doc, pdf, spdf, graft, pages):
    """The new drawings' layers join the document's list of layers (/OCProperties), on or off
    as in the new file, so other readers, and KanzonasPDF's Layers tab once the file is
    opened again, can show and hide them (unlisted, they would always show)."""
    name = m.pdf_new_name
    sroot = m.pdf_dict_get(m.pdf_trailer(spdf), name("Root"))
    socp = m.pdf_dict_get(sroot, name("OCProperties"))
    if not m.pdf_is_dict(socp):
        return
    used = _used_layers(spdf, pages)
    if not used:
        return
    off = m.pdf_dict_get(m.pdf_dict_get(socp, name("D")), name("OFF"))
    off_nums = {m.pdf_to_num(m.pdf_array_get(off, k)) for k in range(m.pdf_array_len(off))} \
        if m.pdf_is_array(off) else set()
    root = m.pdf_dict_get(m.pdf_trailer(pdf), name("Root"))
    ocp = m.pdf_dict_get(root, name("OCProperties"))
    if not m.pdf_is_dict(ocp):
        ocp = m.pdf_dict_put_dict(root, name("OCProperties"), 2)
    ocgs = m.pdf_dict_get(ocp, name("OCGs"))
    if not m.pdf_is_array(ocgs):
        ocgs = m.pdf_dict_put_array(ocp, name("OCGs"), len(used))
    d = m.pdf_dict_get(ocp, name("D"))
    if not m.pdf_is_dict(d):
        d = m.pdf_dict_put_dict(ocp, name("D"), 2)
    order = m.pdf_dict_get(d, name("Order"))
    if not m.pdf_is_array(order):
        # (the order layers are listed in; MuPDF lists none without it)
        order = m.pdf_dict_put_array(d, name("Order"), m.pdf_array_len(ocgs) + len(used))
        for k in range(m.pdf_array_len(ocgs)):
            m.pdf_array_push(order, m.pdf_array_get(ocgs, k))
    have = {m.pdf_to_num(m.pdf_array_get(ocgs, k)) for k in range(m.pdf_array_len(ocgs))}
    added = False
    for num in sorted(used):
        ref = m.pdf_graft_mapped_object(graft, m.pdf_new_indirect(spdf, num, 0))
        if m.pdf_to_num(ref) in have:
            continue
        have.add(m.pdf_to_num(ref))
        m.pdf_array_push(ocgs, ref)
        added = True
        if m.pdf_is_array(order):
            m.pdf_array_push(order, ref)
        if num in off_nums:
            arr = m.pdf_dict_get(d, name("OFF"))
            if not m.pdf_is_array(arr):
                arr = m.pdf_dict_put_array(d, name("OFF"), 1)
            m.pdf_array_push(arr, ref)
    if added:
        undo_journal.reload_layers(doc)     # (MuPDF reads its list of layers again)


def _graft_drawing(doc, pdf, i, spdf, j, graft):
    """Page i of doc gets the drawing keys of page j of the new file (copied in through
    graft); the page object, its markups and its own keys stay."""
    obj = m.pdf_lookup_page_obj(pdf, i)
    sobj = m.pdf_lookup_page_obj(spdf, j)
    for key in _INHERITED:
        name = m.pdf_new_name(key)
        val = m.pdf_dict_get_inheritable(sobj, name)
        if val.m_internal:
            m.pdf_dict_put(obj, name, m.pdf_graft_mapped_object(graft, val))
        elif key == "Resources":
            m.pdf_dict_put(obj, name, m.pdf_new_dict(pdf, 1))
        elif key == "Rotate":
            m.pdf_dict_put_int(obj, name, 0)
        else:
            m.pdf_dict_del(obj, name)
            if key == "CropBox" and m.pdf_dict_get_inheritable(obj, name).m_internal:
                # (the page tree above it has one: the new page shows its whole media box)
                m.pdf_dict_put(obj, name, m.pdf_copy_array(
                    m.pdf_dict_get(obj, m.pdf_new_name("MediaBox"))))
    for key in _OWN:
        name = m.pdf_new_name(key)
        val = m.pdf_dict_get(sobj, name)
        if val.m_internal:
            m.pdf_dict_put(obj, name, m.pdf_graft_mapped_object(graft, val))
        else:
            m.pdf_dict_del(obj, name)
    for key in _STALE:
        m.pdf_dict_del(obj, m.pdf_new_name(key))


def _sync(page):
    """MuPDF's loaded page reads its links and markups again (their places on the page as
    displayed were worked out with the old page boxes)."""
    try:
        m.pdf_sync_page(m.pdf_page_from_fz_page(page.this))
    except Exception:
        pass


# ---- markups --------------------------------------------------------------------------------
def _fmt(n):
    return ("%.4f" % n).rstrip("0").rstrip(".") or "0"


def _map_pairs(text, t):
    """A PDF array of x y pairs (nested or not) with each pair mapped through t."""
    nums = [float(x) for x in _NUMBER.findall(text)]
    out = []
    for a in range(0, len(nums) - 1, 2):
        p = pymupdf.Point(nums[a], nums[a + 1]) * t
        out += [p.x, p.y]
    it = iter(out)
    k = [0]

    def sub(_mo):
        k[0] += 1
        return _fmt(next(it, 0.0))
    if len(nums) % 2:
        return text                     # (not pairs: left alone)
    return _NUMBER.sub(sub, text)


def _rect_numbers(val):
    nums = [float(x) for x in _NUMBER.findall(val)]
    return pymupdf.Rect(nums[:4]).normalize() if len(nums) >= 4 else None


def _rect_array(r):
    return "[%s]" % " ".join(_fmt(v) for v in (r.x0, r.y0, r.x1, r.y1))


def _mapped_rect(r, t):
    return pymupdf.Rect(r).quad.transform(t).rect


def _map_annots(doc, page, t, tp):
    """Map every annotation of the page (markups, links, form fields, pop-ups) through t (PDF
    user space, old drawing -> new) and the geometry KanzonasPDF keeps through tp (page
    coordinates). Returns how many."""
    turned = abs(t.b) > 1e-9 or abs(t.c) > 1e-9
    lin = pymupdf.Matrix(t.a, t.b, t.c, t.d, 0, 0)
    sx, sy = abs(pymupdf.Point(1, 0) * lin), abs(pymupdf.Point(0, 1) * lin)
    n = 0
    for xref, kind, *_ in page.annot_xrefs():
        typ, val = doc.xref_get_key(xref, "Rect")
        old = _rect_numbers(val) if typ == "array" else None
        if old is None:
            continue
        if kind in _ICONS:
            # (an icon keeps its size: its middle goes where it goes)
            c = pymupdf.Point((old.x0 + old.x1) / 2, (old.y0 + old.y1) / 2) * t
            w, h = old.width / 2, old.height / 2
            new = pymupdf.Rect(c.x - w, c.y - h, c.x + w, c.y + h)
        else:
            new = _mapped_rect(old, t)
        doc.xref_set_key(xref, "Rect", _rect_array(new))
        for key in _PAIRS:
            kt, kv = doc.xref_get_key(xref, key)
            if kt == "array" and "R" not in kv:
                doc.xref_set_key(xref, key, _map_pairs(kv, t))
            elif kt == "xref":
                ref = int(kv.split()[0])
                doc.update_object(ref, _map_pairs(doc.xref_object(ref, compressed=True), t))
        kt, kv = doc.xref_get_key(xref, "RD")
        if kt == "array" and kind not in _ICONS:
            d = [float(x) for x in _NUMBER.findall(kv)][:4]
            if len(d) == 4:
                f = (sx, sy, sx, sy) if not turned else ((sx + sy) / 2,) * 4
                doc.xref_set_key(xref, "RD", "[%s]" % " ".join(
                    _fmt(v * s) for v, s in zip(d, f)))
        if turned and kind not in _ICONS:
            _turn_appearance(doc, xref, lin)
        _map_kzprops(doc, xref, tp)
        kt, kv = doc.xref_get_key(xref, "KZUnder")
        if kt == "array":
            doc.xref_set_key(xref, "KZUnder", _map_pairs(kv, tp))
        n += 1
    return n


def _turn_appearance(doc, xref, lin):
    """A markup whose page as displayed turned against its PDF space: its drawing turns with
    it (fitted into the new /Rect, as every reader draws an appearance)."""
    streams = set()
    for state in ("N", "D", "R"):
        st, sv = doc.xref_get_key(xref, "AP/" + state)
        if st == "xref":
            x = int(sv.split()[0])
            if doc.xref_is_stream(x):
                streams.add(x)
                continue
            sv = doc.xref_object(x, compressed=True)    # (states: a check box's on and off)
        elif st != "dict":
            continue
        streams.update(int(r) for r in re.findall(r"(\d+)\s+0\s+R", sv))
    for x in streams:
        if not doc.xref_is_stream(x):
            continue
        mt, mv = doc.xref_get_key(x, "Matrix")
        nums = [float(v) for v in _NUMBER.findall(mv)] if mt == "array" else []
        cur = pymupdf.Matrix(*nums[:6]) if len(nums) >= 6 else pymupdf.Matrix(1, 0, 0, 1, 0, 0)
        doc.xref_set_key(x, "Matrix", "[%s]" % " ".join(_fmt(v) for v in cur * lin))


def _map_kzprops(doc, xref, tp):
    """The geometry KanzonasPDF keeps for its markups (page coordinates)."""
    kt, kv = doc.xref_get_key(xref, annotations.KZ_KEY)
    if kt != "string":
        return
    try:
        store = json.loads(kv)
    except ValueError:
        return
    geom = store.get("geom") if isinstance(store, dict) else None
    if not isinstance(geom, dict):
        return
    for key in ("box", "target", "at", "pts", "bend"):
        vals = geom.get(key)
        if not isinstance(vals, list) or len(vals) < 2 or \
                not all(isinstance(v, (int, float)) for v in vals):
            continue
        pts = [pymupdf.Point(vals[a], vals[a + 1]) * tp for a in range(0, len(vals) - 1, 2)]
        if key == "box" and len(pts) >= 2:
            r = pymupdf.Rect(pts[0], pts[1]).normalize()
            geom[key] = [r.x0, r.y0, r.x1, r.y1] + vals[4:]
        else:
            geom[key] = [c for p in pts for c in (p.x, p.y)] + vals[2 * len(pts):]
    doc.xref_set_key(xref, annotations.KZ_KEY, pymupdf.get_pdf_str(json.dumps(store)))


def _map_scale(doc, page, k):
    """A page scaled evenly to the new size keeps measuring right: its scale goes along."""
    if abs(k[0] - k[1]) > 0.01 * max(k) or abs(k[0] - 1) < 1e-6:
        return
    f, unit, label, ok = measure.get_scale(page)
    if ok:
        measure.set_scale(page, f / ((k[0] + k[1]) / 2), unit, label)


def _take_scale(doc, src, page, new):
    """A new page calibrated with KanzonasPDF brings its own scale."""
    typ, val = src.xref_get_key(new.xref, measure.KEY)
    if typ == "string":
        doc.xref_set_key(page.xref, measure.KEY, pymupdf.get_pdf_str(val))


# ---- links drawn into the old drawing ---------------------------------------------------
def _center_in(rect, box):
    return box.contains(pymupdf.Point((rect.x0 + rect.x1) / 2, (rect.y0 + rect.y1) / 2))


def _words_in(words, box):
    box = pymupdf.Rect(box) + (-1, -1, 1, 1)
    return [w[4] for w in words if _center_in(pymupdf.Rect(w[:4]), box)]


def _link_words(page, page_links):
    """{link xref: the words under it} on the old drawing, for the links made on the
    drawing's text (not the text a link wrote itself, nor on markups and areas)."""
    check = [ln for ln in page_links if not ln["text"] and ln["on"] in (None, "text")]
    if not check:
        return {}
    words = page.get_text("words")
    out = {}
    for ln in check:
        found = _words_in(words, ln["rect"])
        if found:
            out[ln["xref"]] = found
    return out


def _link_texts(page, page_links):
    """{link xref: (baseline start, size)} of the text links wrote into the old drawing."""
    from . import text_edit
    mine = [ln for ln in page_links if ln["text"]]
    if not mine:
        return {}
    out = {}
    lines = text_edit.text_lines(page)
    for ln in mine:
        want = " ".join(ln["text"].split())
        for r, line in lines:
            if _center_in(r, ln["rect"] + (-2, -2, 2, 2)) and \
                    " ".join(text_edit.line_text(line).split()) == want:
                span = line["spans"][0]
                out[ln["xref"]] = (pymupdf.Point(span["origin"]), float(span["size"]))
                break
    return out


def _redraw_links(page, page_links, texts, tp, k):
    """The text and underlines links made with KanzonasPDF drew into the old drawing, drawn
    again on the new one where the links now are. Returns how many links."""
    from . import text_edit
    doc = page.parent
    f = (k[0] + k[1]) / 2
    n = 0
    for ln in page_links:
        done = False
        if ln["text"] and ln["xref"] in texts:
            origin, size = texts[ln["xref"]]
            try:
                text_edit.add_text(page, origin * tp, " ".join(ln["text"].split()),
                                   size=size * f, color=links.BLUE)
                done = True
            except ValueError:
                pass
        if ln["look"] == "underline":
            kt, kv = doc.xref_get_key(ln["xref"], "KZUnder")
            nums = [float(v) for v in _NUMBER.findall(kv)] if kt == "array" else []
            if len(nums) >= 4:
                page.draw_line(pymupdf.Point(nums[0], nums[1]), pymupdf.Point(nums[2], nums[3]),
                               color=links.BLUE, width=0.75)
                done = True
        n += done
    return n


def _moved_words(page, page_links, words, tp):
    """How many links lay over words of the old drawing that aren't under them on the new
    one (a callout moved in the new revision)."""
    if not words:
        return 0
    now = page.get_text("words")
    moved = 0
    for ln in page_links:
        old = words.get(ln["xref"])
        if not old:
            continue
        rect = (pymupdf.Rect(ln["rect"]) * tp).normalize()
        if _words_in(now, rect) != old:
            moved += 1
    return moved
