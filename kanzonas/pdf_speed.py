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


def delete_many(page, xrefs):
    """Delete these annotations (xrefs) from page, as page.delete_annot does one at a time
    (with the replies to each, and its pop-up), looking through the page's markups once.
    xrefs no longer on the page are skipped. The caller must not hold Annot objects for
    them (load them, read them, let them go, then delete)."""
    xrefs = list(dict.fromkeys(xrefs))
    if not xrefs:
        return
    if len(xrefs) < 4 or not can_delete_many():
        for x in xrefs:                 # (a few: PyMuPDF's own way is as quick)
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
        for n, r in replies.get(x, ()):     # the replies to it go first, as in PyMuPDF
            if n not in gone:
                m.pdf_delete_annot(pdfpage, r)
                gone.add(n)
        m.pdf_delete_annot(pdfpage, found[x])
        gone.add(x)
    page._delete_empty_annots()
    m.pdf_sync_annots(pdfpage)
