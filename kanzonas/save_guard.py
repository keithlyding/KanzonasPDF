"""A compacting save (garbage 2 and up) that can't lose a stream's data.

Writing with garbage >= 2 renumbers the objects of the document being written, in the
document itself (MuPDF's renumberobjs). An object something else still holds (a MuPDF
object handle: pdf_load_object, a PyMuPDF/mupdf object still alive) is not rewritten in
place: MuPDF puts a copy of it in its place with pdf_update_object. For a stream read from
the file and not changed since, that copy gets a new entry in the table of objects without
where the stream's data is (the entry's stream offset), so the stream was written empty: a
page placed with show_pdf_page lost its drawing in Save as PDF/A, and the document open
lost it too.

guard() moves each such stream (loaded and held by something) into the document's table
of changed objects first, the way MuPDF does it before any change, with its data's place,
and puts a copy of it there that nothing else holds: renumbering then rewrites it in place.
Nothing else changes (the file written is the same, held or not). Importing this module
(kanzonas/__init__ does) makes every Document.save and tobytes of a PDF do it.
"""

import pymupdf

_SAVE = pymupdf.Document.save


def guard(doc):
    """Make doc safe for a compacting write (see the module's docstring). Returns the
    object numbers moved."""
    m = pymupdf.mupdf
    try:
        pdf = pymupdf._as_pdf_document(doc, required=0)
    except Exception:
        return []
    if pdf is None or pdf.m_internal is None:
        return []
    raw = pdf.m_internal
    moved = []
    for num in range(1, m.ll_pdf_xref_len(raw)):
        try:
            e = m.ll_pdf_get_xref_entry_no_change(raw, num)
        except Exception:
            continue
        # (not loaded: nothing can hold it; not a stream: its copy keeps all there is)
        if e is None or e.obj is None or (not e.stm_ofs and e.stm_buf is None):
            continue
        if m.ll_pdf_obj_refs(e.obj) <= 1:
            continue
        # (already among the changed objects: a no-op there)
        m.ll_pdf_xref_ensure_incremental_object(raw, num)
        # and in its place a copy nothing else holds: renumbering rewrites that one in
        # place. (The copy MuPDF makes of a held object is held twice itself, by a
        # reference it doesn't give back: when garbage >= 3 finds duplicates, renumbering
        # runs again on a table rebuilt as read from a file, and copied it again into an
        # entry with no stream data at all.) Whatever held the object keeps it, apart
        # from the document, as after MuPDF's own copy.
        copy = m.ll_pdf_deep_copy_obj(m.ll_pdf_get_xref_entry_no_change(raw, num).obj)
        try:
            m.ll_pdf_update_object(raw, num, copy)
        finally:
            m.ll_pdf_drop_obj(copy)
        moved.append(num)
    return moved


def _garbage(a, k):
    g = k.get("garbage", a[1] if len(a) > 1 else 0)
    return int(g or 0)


def save(self, *a, **k):
    incremental = k.get("incremental") or (len(a) > 6 and a[6])
    if not incremental and getattr(self, "is_pdf", False) and not self.is_closed:
        try:
            if _garbage(a, k) >= 2:
                guard(self)
        except Exception:
            pass                        # (another PyMuPDF: saved as it would be)
    return _SAVE(self, *a, **k)


save.__doc__ = _SAVE.__doc__
pymupdf.Document.save = save
