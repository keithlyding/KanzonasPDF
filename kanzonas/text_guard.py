"""A guard against a crash in MuPDF's text reading (MuPDF 1.28.5, and its master branch as of
November 2026: source/fitz/stext-device.c, fz_stext_end_metatext).

ActualText is marked content that gives the words a part of the page stands for (a picture
of a word, a ligature, a drawn logo). When one ActualText sits inside another, and the
inner one wraps only pictures or drawings on a page with no text read before it, MuPDF
borrows a font to place the inner text, gives it back, but leaves its "a text position is
in force" flag set; the outer ActualText then writes its text with no font, and the whole
program ends (a segmentation fault, unsaved work lost). Find, text selection, Edit text,
copying and exports all read text, so opening such a page and searching it was enough.

MuPDF's own switch TEXT_IGNORE_ACTUALTEXT leaves that branch out. Ignoring ActualText
everywhere would change what Find finds on ordinary PDFs (a word exported with ligatures is
found through its ActualText), so it is used only on pages that have one ActualText inside
another: risky(). Most pages have no ActualText at all, which a look at the bytes the page
draws (its contents, the forms, patterns, Type3 glyphs and markup appearances it reaches)
shows quickly; only a page where the bytes mention ActualText is run through a device that
notes nothing but marked-content text, to see whether any is nested.

Calls that collect styles (TEXT_COLLECT_STYLES: PyMuPDF's hidden-text search in Remove hidden
information, Sanitize, Apply redactions) don't reach the crash and are left exactly as they
are, so what redaction removes doesn't change.

apply() wraps Page.get_textpage, through which PyMuPDF's get_text, search_for and the rest
read a page; text_edit reads through a display list and asks risky() itself.
"""
import re
import zlib

import pymupdf

FLAG = getattr(pymupdf, "TEXT_IGNORE_ACTUALTEXT", 0)
applied = False
used = 0                        # pages read with the guard on (for tests)

_REF = re.compile(r"(\d+) \d+ R")
_NAME_ESCAPE = re.compile(rb"/[^\s/<>\[\]()%{}]*#[0-9A-Fa-f]{2}")
_SKIP_KEYS = ("/Parent", "/P ", "/P\n", "/Prev", "/Next", "/First", "/Last", "/Dest",
              "/StructParent", "/Popup", "/IRT")
_LIMIT = 20000                  # objects looked through before giving up (then: risky)


def _mentions_actualtext(data):
    """data (bytes) may hold an ActualText: the word, or a name written with #xx escapes."""
    return b"ActualText" in data or (b"#" in data and _NAME_ESCAPE.search(data) is not None)


def _bytes_mention(page):
    """True when anything the page draws mentions ActualText (or might: when unsure)."""
    doc = page.parent
    try:
        if _mentions_actualtext(page.read_contents() or b""):
            return True
        todo = []
        kind, res = doc.xref_get_key(page.xref, "Resources")
        if kind == "null":                      # (inherited from the page tree)
            seen_tree = set()
            x = page.xref
            while kind == "null" and x and x not in seen_tree:
                seen_tree.add(x)
                pk, parent = doc.xref_get_key(x, "Parent")
                m = _REF.match(parent) if pk == "xref" else None
                x = int(m.group(1)) if m else 0
                if x:
                    kind, res = doc.xref_get_key(x, "Resources")
        if b"ActualText" in res.encode("latin-1", "replace"):
            return True
        todo += [int(n) for n in _REF.findall(res)]
        for a in page.annot_xrefs():
            kind, ap = doc.xref_get_key(a[0], "AP")
            if kind != "null":
                if "ActualText" in ap:
                    return True
                todo += [int(n) for n in _REF.findall(ap)]
        seen = set()
        while todo:
            x = todo.pop()
            if x in seen or x <= 0:
                continue
            seen.add(x)
            if len(seen) > _LIMIT:
                return True
            src = doc.xref_object(x, compressed=True)
            if "ActualText" in src:
                return True
            if doc.xref_is_stream(x):
                sub = doc.xref_get_key(x, "Subtype")[1]
                # (pictures and font programs hold no marked content: not read)
                if sub not in ("/Image", "/Type1C", "/CIDFontType0C", "/OpenType") and \
                        "/Length1" not in src and "/Length2" not in src and \
                        _mentions_actualtext(doc.xref_stream(x) or b""):
                    return True
            for line in src.splitlines():
                if not line.lstrip().startswith(_SKIP_KEYS):
                    todo += [int(n) for n in _REF.findall(line)]
        return False
    except Exception:
        return True


def _nested(page):
    """The page has one ActualText inside another (in its contents, forms, patterns, glyphs
    or markups). True when unsure."""
    m = pymupdf.mupdf
    if not hasattr(m, "FzDevice2") or not hasattr(m.FzDevice2, "use_virtual_begin_metatext"):
        return True
    actual = getattr(m, "FZ_METATEXT_ACTUALTEXT", 0)

    class Device(m.FzDevice2):
        def __init__(self):
            super().__init__()
            self.use_virtual_begin_metatext()
            self.use_virtual_end_metatext()
            self.stack = []
            self.found = False

        def begin_metatext(self, ctx, meta, text):
            if meta == actual and actual in self.stack:
                self.found = True
            self.stack.append(meta)

        def end_metatext(self, ctx):
            if self.stack:
                self.stack.pop()

    try:
        dev = Device()
        m.fz_run_page(page.this, dev, m.FzMatrix(), m.FzCookie())
        m.fz_close_device(dev)
        return dev.found
    except Exception:
        return True


def _key(page):
    """What the answer for a page depends on, cheaply: its content streams as stored
    (number, length, checksum), its resources and its markups. (A form changed in place
    with nothing else changing isn't seen; KanzonasPDF never writes ActualText, so a form
    can't gain one that way.)"""
    doc = page.parent
    m = pymupdf.mupdf
    pdf = pymupdf._as_pdf_document(doc)
    parts = [page.xref, doc.xref_get_key(page.xref, "Resources")]
    for x in page.get_contents():
        try:
            buf = m.pdf_load_raw_stream_number(pdf, x)
            mv = buf.fz_buffer_storage_memoryview()
            parts.append((x, mv.nbytes, zlib.crc32(mv)))
            del mv
        except Exception:
            raw = doc.xref_stream_raw(x) or b""
            parts.append((x, len(raw), zlib.crc32(raw)))
    parts.append(tuple((a[0], doc.xref_get_key(a[0], "AP")[1]) for a in page.annot_xrefs()))
    return tuple(parts)


def risky(page):
    """Reading this page's text could hit MuPDF's crash (see above): ActualText inside
    ActualText somewhere it draws. (Kept per page while what it depends on is unchanged.)"""
    doc = page.parent
    if not FLAG or not getattr(doc, "is_pdf", False):
        return False
    try:
        key = _key(page)
    except Exception:
        key = None
    cache = getattr(doc, "_kz_text_guard", None)
    if cache is None:
        cache = {}
        try:
            doc._kz_text_guard = cache
        except Exception:
            pass
    if key is not None and cache.get(page.xref, (None,))[0] == key:
        return cache[page.xref][1]
    out = _bytes_mention(page) and _nested(page)
    if key is not None:
        cache[page.xref] = (key, out)
    return out


def flags_for(page, flags):
    """flags, with TEXT_IGNORE_ACTUALTEXT added when the page needs it (see above)."""
    global used
    if not FLAG or flags & FLAG or flags & pymupdf.TEXT_COLLECT_STYLES:
        return flags
    if risky(page):
        used += 1
        return flags | FLAG
    return flags


def apply():
    """Wrap Page.get_textpage (once). True when the guard is in place."""
    global applied
    if applied:
        return True
    if not FLAG:
        return False
    own = pymupdf.Page.get_textpage

    def get_textpage(self, clip=None, flags=0, matrix=None):
        return own(self, clip, flags_for(self, flags), matrix)
    get_textpage.__doc__ = own.__doc__
    pymupdf.Page.get_textpage = get_textpage
    applied = True
    return True
