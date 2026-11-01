"""A page on screen is drawn in two layers: its content (the drawing, text and pictures) and
its markups (annotations and form fields).

The content is rendered once per zoom and its raw pixels are kept; the markups are drawn over
a copy of those pixels by MuPDF itself, so a highlight's Multiply blend mixes with the
content exactly as when the whole page is rendered in one go (the bytes are the same: MuPDF
runs a page as its content, then its annotations, then its widgets, onto one pixmap).
Adding, moving, restyling or deleting a markup then redraws only the markups: on a heavy CAD
sheet some 20 ms instead of most of a second.

Whether the content is still the same is told by its content key: the page's content
streams and everything its resources reach (fonts, pictures, forms, graphics states),
checksummed, with the page's boxes, rotation and the layers shown. An edit that changes any of
it (erase, redaction, Edit text, Edit objects, a CAD command, a crop) gives a new key and the
content is rendered again; a markup edit leaves it as it was.
"""

import itertools
import re
import weakref
import zlib
from collections import OrderedDict

import pymupdf

CONTENT_BYTES = 64 * 1024 * 1024   # raw content renders kept per document view ...
CONTENT_BYTES_ALL = 160 * 1024 * 1024   # ... and for all open documents together
BIG_IMAGE_PX = 4_000_000           # pictures this big are decoded once for all tiles ...
DECODE_LIMIT = 128 * 1024 * 1024   # ... unless decoded they would take more memory than this

_REF = re.compile(r"(\d+) \d+ R")    # (any generation: a file updated in place has "5 1 R")


def _crc(doc, xref):
    """(length, checksum) of an object's stream as stored (not decompressed)."""
    try:
        m = pymupdf.mupdf
        buf = m.pdf_load_raw_stream_number(pymupdf._as_pdf_document(doc), xref)
        mv = buf.fz_buffer_storage_memoryview()
        out = (mv.nbytes, zlib.crc32(mv))
        del mv
        return out
    except Exception:                   # (another PyMuPDF)
        raw = doc.xref_stream_raw(xref) or b""
        return len(raw), zlib.crc32(raw)


def _inherited(doc, xref, key):
    """A page's key, looked up through its parents in the page tree when the page has none."""
    seen = set()
    while xref and xref not in seen:
        seen.add(xref)
        kind, val = doc.xref_get_key(xref, key)
        if kind != "null":
            return kind, val
        kind, parent = doc.xref_get_key(xref, "Parent")
        m = _REF.match(parent) if kind == "xref" else None
        xref = int(m.group(1)) if m else 0
    return "null", "null"


def content_key(page):
    """What a page's content looks like on screen depends on, as a comparable value: its
    content streams (checksummed, a nudge can keep a stream's length), every object its
    resources reach (the source of each, the checksum of each stream), the page's boxes,
    rotation and transparency group, and the layers shown."""
    doc = page.parent
    if not doc.is_pdf:
        return (page.number, tuple(page.rect))
    out = [tuple(page.mediabox), tuple(page.cropbox), page.rotation]
    for x in page.get_contents():
        out.append((x,) + _crc(doc, x))
    kind, res = _inherited(doc, page.xref, "Resources")
    out.append(res)
    out.append(doc.xref_get_key(page.xref, "Group"))
    out.append(_inherited(doc, page.xref, "UserUnit"))
    todo = [int(n) for n in _REF.findall(res)]
    seen = set()
    while todo:
        x = todo.pop()
        if x in seen or x <= 0:
            continue
        seen.add(x)
        try:
            src = doc.xref_object(x, compressed=True)
        except Exception:
            out.append((x, None))
            continue
        out.append((x, src))
        if doc.xref_is_stream(x):
            out.append(_crc(doc, x))
        todo += [int(n) for n in _REF.findall(src)]
    try:
        out.append(tuple((c.get("number"), c.get("on")) for c in doc.layer_ui_configs()))
    except Exception:
        pass
    return tuple(out)


def annots_list(page):
    """The page's markups and form fields as the screen shows them (the View flags) as a
    pymupdf.DisplayList, or None when there's nothing of them to draw."""
    m = pymupdf.mupdf
    dl = m.FzDisplayList(m.fz_bound_page(page.this))
    dev = m.fz_new_list_device(dl)
    try:
        m.fz_run_page_annots(page.this, dev, m.FzMatrix(), m.FzCookie())
        m.fz_run_page_widgets(page.this, dev, m.FzMatrix(), m.FzCookie())
    finally:
        m.fz_close_device(dev)
    # (the list's own bounds are the page's: what it draws is measured by running it)
    box = m.FzRect(m.FzRect.Fixed_EMPTY)
    dev = m.fz_new_bbox_device(box)
    try:
        m.fz_run_display_list(dl, dev, m.FzMatrix(), m.FzRect(m.FzRect.Fixed_INFINITE),
                              m.FzCookie())
    finally:
        m.fz_close_device(dev)
    if m.fz_is_empty_rect(box):
        return None
    return pymupdf.DisplayList(dl)


def render(dl, s, clip=None):
    """dl at zoom s (device pixels per point), whole or the clip (page coordinates), white
    behind, as a pymupdf.Pixmap: what DisplayList.get_pixmap makes."""
    if clip is None:
        return dl.get_pixmap(matrix=pymupdf.Matrix(s, s), alpha=False)
    return dl.get_pixmap(matrix=pymupdf.Matrix(s, s), clip=clip, alpha=False)


def draw_over(base, dl, s, clip=None):
    """A copy of the pixmap base (a render of the content at zoom s, whole or of the clip)
    with dl drawn over it: the same pixels as rendering content and dl as one list, as
    DisplayList.get_pixmap runs it (a whole page: a draw device on the pixmap; a clip: one
    limited to the pixmap's box, running the list over the clip)."""
    m = pymupdf.mupdf
    # (a copy made as cut does: MuPDF's fz_clone_pixmap loses the width of a pixmap that
    # doesn't start at x = 0, a tile's)
    out = cut(base, base.irect)
    pix = out.this
    ctm = m.FzMatrix(s, 0, 0, s, 0, 0)
    if clip is None:
        dev = m.fz_new_draw_device(ctm, pix)
        area = m.FzRect(m.FzRect.Fixed_INFINITE)
    else:
        dev = m.fz_new_draw_device_with_bbox(ctm, pix, m.fz_pixmap_bbox(pix))
        area = pymupdf.JM_rect_from_py(clip)
    try:
        m.fz_run_display_list(dl.this, dev, m.FzMatrix(), area, m.FzCookie())
    finally:
        m.fz_close_device(dev)
    return out


def cut(pm, irect):
    """The part irect (device pixels) of pixmap pm, as a pixmap of its own (in pm's own
    colorspace: markups drawn over a pixmap of an equal but other RGB come out in other
    colors)."""
    m = pymupdf.mupdf
    box = pymupdf.JM_irect_from_py(irect)
    out = m.fz_new_pixmap_with_bbox(m.fz_pixmap_colorspace(pm.this), box, m.FzSeparations(), 0)
    m.fz_copy_pixmap_rect(out, pm.this, box, m.FzDefaultColorspaces(None))
    return pymupdf.Pixmap("raw", out)


def big_images(page):
    """[(xref, width, height, decoded bytes)] of the page's pictures big enough that decoding
    them again for every tile is what makes a scanned page slow at high zoom."""
    out = []
    try:
        for info in page.get_images(full=True):
            xref, w, h, bpc, cs = info[0], info[2], info[3], info[4], info[5]
            if xref > 0 and w * h >= BIG_IMAGE_PX:
                n = 1 if bpc == 1 or cs in ("DeviceGray", "CalGray", "Indexed") else \
                    4 if cs in ("DeviceCMYK",) else 3
                out.append((xref, w, h, w * h * n))
    except Exception:
        pass
    return out


def predecode(page, items):
    """Decode big pictures whole, once, at the size they're drawn at ([(xref, width, height)]
    in device pixels: MuPDF picks 1/2, 1/4... of the full size from it), into MuPDF's own
    store. Each tile of a scanned page then reads the picture from there (4 ms) instead of
    decoding the whole JPEG again (most of a second each). Whether it stays decoded is up to
    MuPDF's store, which gives it up when it needs the room (tiles then decode again)."""
    m = pymupdf.mupdf
    pdf = pymupdf._as_pdf_document(page.parent)
    for x, dw, dh in items:
        try:
            img = m.pdf_load_image(pdf, m.pdf_new_indirect(pdf, x, 0))
            ctm = m.FzMatrix(dw, 0, 0, dh, 0, 0)
            got = m.ll_fz_get_pixmap_from_image(img.m_internal, None, ctm.internal())
            m.ll_fz_drop_pixmap(got[0] if isinstance(got, (tuple, list)) else got)
        except Exception:
            pass


def nbytes(pm):
    return pm.stride * pm.height


class ContentCache:
    """Raw renders of the pages' content (no markups) for one document view, least recently
    used dropped first beyond CONTENT_BYTES, with the content key each page's renders (and its
    content display list) were made from. All the views' caches together keep at most
    CONTENT_BYTES_ALL: the documents used longest ago give theirs up first (ten documents open
    kept 64 MB each)."""

    _all = weakref.WeakSet()
    _clock = itertools.count()

    def __init__(self):
        self.renders = OrderedDict()   # (page, scale, tile or None, thin lines) -> Pixmap
        self.bytes = 0
        self.keys = {}                 # page -> content key of what's cached for it
        self.recheck = set()           # pages whose content may have changed since
        self.used = next(self._clock)
        ContentCache._all.add(self)

    def _key(self, i, s, tile, thin):
        return (i, round(s, 5), tile, bool(thin))

    def get(self, i, s, tile, thin):
        k = self._key(i, s, tile, thin)
        pm = self.renders.get(k)
        if pm is not None:
            self.renders.move_to_end(k)
            self.used = next(self._clock)
        return pm

    def put(self, i, s, tile, thin, pm):
        k = self._key(i, s, tile, thin)
        old = self.renders.pop(k, None)
        if old is not None:
            self.bytes -= nbytes(old)
        self.renders[k] = pm
        self.bytes += nbytes(pm)
        self.used = next(self._clock)
        while self.bytes > CONTENT_BYTES and len(self.renders) > 1:
            _k, gone = self.renders.popitem(last=False)
            self.bytes -= nbytes(gone)
        others = [c for c in list(ContentCache._all) if c is not self and c.renders]
        total = self.bytes + sum(c.bytes for c in others)
        for c in sorted(others, key=lambda c: c.used):
            while total > CONTENT_BYTES_ALL and c.renders:
                _k, gone = c.renders.popitem(last=False)
                c.bytes -= nbytes(gone)
                total -= nbytes(gone)
        while total > CONTENT_BYTES_ALL and len(self.renders) > 1:
            _k, gone = self.renders.popitem(last=False)
            self.bytes -= nbytes(gone)
            total -= nbytes(gone)

    def has_page(self, i):
        return any(k[0] == i for k in self.renders)

    def drop_page(self, i, whole_only=False):
        for k in [k for k in self.renders if k[0] == i and (not whole_only or k[2] is None)]:
            self.bytes -= nbytes(self.renders.pop(k))

    def clear(self):
        self.renders.clear()
        self.bytes = 0
        self.keys.clear()
        self.recheck.clear()
