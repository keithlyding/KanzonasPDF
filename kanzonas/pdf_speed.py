"""Faster stand-ins for two PyMuPDF steps that slow down steeply on a page with many markups.

1. Adding a markup: PyMuPDF names each one (/NM) with the first free "fitz-A0", "fitz-A1"...
   and to find it reads the name of every markup on the page and tries 0, 1, 2... against
   that list, so adding 2,000 markups to a page took 24 s. The stand-in makes a name that is
   unique without looking: the same prefix and kind letter, then a token for this run of
   the app and a counter (2,000 markups: under 2 s). KanzonasPDF never reads these names;
   they only have to differ on a page.
2. Deleting many markups: page.delete_annot walks every markup on the page once for each
   one deleted, looking for replies to it (97% of the time). delete_many() looks once.

apply() runs once (annotations.py imports it). If a PyMuPDF update renames what the stand-in
replaces, PyMuPDF's own (slower, correct) step stays in use: the self-test's check
"PyMuPDF speed fixes" then fails the build, so it is noticed and looked at.
"""
import itertools
import os

import pymupdf

_RUN = os.urandom(4).hex()          # this run of the app: names never repeat across runs
_COUNT = itertools.count()
applied = False


def _annot_id(annot, stem):
    """PyMuPDF's JM_add_annot_id without the search: a fresh /NM for annot."""
    mupdf = pymupdf.mupdf
    name = "%s-%s%s%d" % (pymupdf.JM_annot_id_stem, stem, _RUN, next(_COUNT))
    mupdf.pdf_dict_puts(mupdf.pdf_annot_obj(annot), "NM", mupdf.pdf_new_string(name, len(name)))
    # (as PyMuPDF's own does after setting the name)
    pymupdf._pdf_annot_page(annot).doc().m_internal.resynth_required = 0


def apply():
    """Put the stand-in in place (once). True when it is in use."""
    global applied
    if applied:
        return True
    needed = ("JM_add_annot_id", "JM_annot_id_stem", "_pdf_annot_page")
    if not all(hasattr(pymupdf, n) for n in needed):
        return False                    # (a PyMuPDF that changed: its own step stays)
    pymupdf.JM_add_annot_id = _annot_id
    applied = True
    return True


def can_delete_many():
    m = pymupdf.mupdf
    return all(hasattr(m, n) for n in ("pdf_first_annot", "pdf_next_annot", "pdf_annot_obj",
                                       "pdf_to_num", "pdf_dict_gets", "pdf_delete_annot",
                                       "pdf_sync_annots")) and \
        hasattr(pymupdf.Page, "_pdf_page") and hasattr(pymupdf.Page, "_delete_empty_annots")


def delete_many(page, xrefs, keep_replies=False):
    """Delete these annotations (xrefs) from page, as page.delete_annot does one at a time
    (with the replies to each, and its pop-up), looking through the page's markups once.
    xrefs no longer on the page are skipped. The caller must not hold Annot objects for
    them (load them, read them, let them go, then delete). keep_replies: the replies stay (a
    markup written anew in its place: they are then pointed at the new one)."""
    xrefs = list(dict.fromkeys(xrefs))
    if not xrefs:
        return
    if not can_delete_many():
        for x in xrefs:                 # (a PyMuPDF without what's needed: its own way)
            try:
                a = page.load_annot(x)
            except Exception:
                continue
            if a is not None:
                page.delete_annot(a)
            del a
        return
    m = pymupdf.mupdf
    pdfpage = page._pdf_page()
    want = set(xrefs)
    found, replies = {}, {}
    a = m.pdf_first_annot(pdfpage)
    while a.m_internal:
        obj = m.pdf_annot_obj(a)
        n = m.pdf_to_num(obj)
        if n in want:
            found[n] = a
        irt = m.pdf_dict_gets(obj, "IRT")
        if irt.m_internal:
            replies.setdefault(m.pdf_to_num(irt), []).append((n, a))
        a = m.pdf_next_annot(a)
    gone = set()
    for x in xrefs:
        if x not in found or x in gone:
            continue
        for n, r in () if keep_replies else replies.get(x, ()):
            if n not in gone:               # (the replies to it go first, as in PyMuPDF)
                m.pdf_delete_annot(pdfpage, r)
                gone.add(n)
        m.pdf_delete_annot(pdfpage, found[x])
        gone.add(x)
    page._delete_empty_annots()
    m.pdf_sync_annots(pdfpage)


# ---- Remove hidden information: the hidden-text search on pages without any text -------
# doc.scrub(hidden_text=True) looks on every page for text no one can see (invisible text, an
# OCR layer, fully transparent text) with page.get_text("dict", flags=TEXT_PRESERVE_SPANS |
# TEXT_COLLECT_STYLES) and redacts each such span. TEXT_COLLECT_STYLES has MuPDF collect
# every line and fill of the page to test the text against (underline, strike-out), which
# slows down steeply with the number of lines: 32 s for a CAD sheet of 200,000 lines that
# holds no text at all, on every page of a plan set.
#
# scrub() below runs PyMuPDF's own scrub, step for step, and leaves out only that search on
# a page where it can't find anything: one with no ActualText (or other marked-content
# replacement text) anywhere it is run, and where MuPDF's text extraction yields no
# character. ActualText is looked for first, with a device that only notes it
# (_has_metatext): the page's run with TEXT_COLLECT_VECTORS crashed MuPDF 1.28 (a
# segmentation fault, the app gone) on ActualText inside ActualText around a drawing, which
# PyMuPDF's own search reads without trouble; and ActualText is the one way a character
# appears without a text callback. Such a page gets PyMuPDF's own search, unchanged.
# Otherwise the characters are checked with page.get_textpage(flags=TEXT_PRESERVE_SPANS):
# the same MuPDF text device (stext-device.c, MuPDF 1.28) on the same run of the page
# (contents, forms, markups), with these differences only:
#   - characters come from the text callbacks (fill, stroke, clip, clip-stroke and ignore
#     text: invisible text included) and from ActualText being placed (none here); no flag
#     adds or removes a text callback;
#   - with TEXT_COLLECT_STYLES the device takes text drawn twice (fill, then stroke) a second
#     time, and may merge a character into one already there (fake bold): with no character
#     from the first time there is nothing to take again or merge into;
#   - with TEXT_COLLECT_STYLES paths are collected (to test text against), and only count
#     for the box of an ActualText (none here); they never become text.
# So when that text page holds no text block, the search's dict would have no text block,
# no span and nothing to redact: it is answered with the dict MuPDF gives for a page without
# text, and the rest of scrub goes on exactly as before (the same steps in the same order).
# A page with any block gets PyMuPDF's own search, unchanged. Nothing is narrowed: whatever
# would have been redacted still is. If a PyMuPDF update asks for the search differently,
# the stand-in doesn't recognize it and PyMuPDF's own search runs.

_HIDDEN_TEXT_FLAGS = pymupdf.TEXT_PRESERVE_SPANS | pymupdf.TEXT_COLLECT_STYLES
skipped_searches = 0                # pages scrub() answered without the search (for tests)


def _has_metatext(page):
    """Anything in the page's run (contents, forms, patterns, markups) is marked with
    ActualText (or Alt, E...): MuPDF's interpreter tells a device so with begin_metatext. A
    device that does nothing else, so nothing that reads the text can crash. True when
    unsure."""
    m = pymupdf.mupdf
    if not hasattr(m, "FzDevice2") or not hasattr(m.FzDevice2, "use_virtual_begin_metatext"):
        return True

    class Device(m.FzDevice2):
        found = False

        def __init__(self):
            super().__init__()
            self.use_virtual_begin_metatext()

        def begin_metatext(self, *args):
            self.found = True

    try:
        dev = Device()
        m.fz_run_page(page.this, dev, m.FzMatrix(), m.FzCookie())
        m.fz_close_device(dev)
        return dev.found
    except Exception:
        return True


def page_has_no_text(page):
    """MuPDF's text extraction finds no character on page (see above). False when unsure."""
    try:
        if not isinstance(page.this, pymupdf.mupdf.FzPage) or _has_metatext(page):
            return False
        tp = page.get_textpage(flags=pymupdf.TEXT_PRESERVE_SPANS)
        return not tp.this.m_internal.first_block
    except Exception:
        return False


def scrub(doc, **options):
    """doc.scrub(**options), with the same result, leaving out the hidden-text search where
    it can't find anything (see above)."""
    if not options.get("hidden_text", True):
        return doc.scrub(**options)
    own = pymupdf.Page.get_text

    def get_text(page, option="text", **kwargs):
        global skipped_searches
        if option == "dict" and kwargs == {"flags": _HIDDEN_TEXT_FLAGS} and \
                type(page) is pymupdf.Page and page_has_no_text(page):
            skipped_searches += 1
            r = page.rect
            return {"width": r.width, "height": r.height, "blocks": []}
        return own(page, option, **kwargs)
    pymupdf.Page.get_text = get_text
    try:
        return doc.scrub(**options)
    finally:
        pymupdf.Page.get_text = own
