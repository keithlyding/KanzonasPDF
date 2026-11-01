"""Undo and redo through MuPDF's own journal of changes, instead of a copy of the whole
document per edit.

MuPDF can record, for each operation, the objects it changed (their earlier versions), and
step back and forth through those records: about 2 ms and a few kilobytes per edit, and an
undo of a few milliseconds, where a copy of a big plan set took a second and a hundred
megabytes. The journal has gaps, filled here:

- MuPDF throws on any change made outside an operation. Every document with a journal
  keeps an "ambient" implicit operation open between edits (Journal); MuPDF folds what is
  changed in it into the latest edit, as it does with its own implicit operations, so a
  change made outside DocumentView.modify still works (and is undone with that edit).
- pdf_update_object and pdf_delete_object aren't recorded: an object replaced or deleted
  that way came back wrong after an undo and redo. They first make the journal keep the
  object as it is, and a deleted object is made an empty dictionary instead (the journal
  can't bring back a deleted one; nothing refers to it, so a Save leaves it out).
- Saving (and tobytes) marks the document as just saved, after which the journal's undo
  of anything changed before did nothing: the mark is put back as it was. PyMuPDF's own
  step before a save that sets /PageMode for attachments is left out (it would have
  dropped the redo steps).
- MuPDF keeps fonts and images it added in tables, to give back the same object when the
  same one is added again: after an undo that object is gone, and a text box added again
  showed no text. Those tables are emptied after each undo and redo (reset_resources).
- PyMuPDF checks for an open operation by asking for the undo state, which MuPDF refuses
  during an operation: get_new_xref, update_object, insert_pdf, show_pdf_page and
  insert_font always failed. That check is answered properly, and the two steps PyMuPDF
  does in its compiled helper (new_page, insert_pdf) are run the plain Python way.
- The document's trailer (where /Info is) isn't journaled: DocumentView keeps it per step
  (trailer(), set_trailer()).
- A big edit kept as one entry slowed down steeply (see SPLIT_EVERY): it is cut into
  several entries, undone together.

Where the journal can't serve (see DocumentView.modify and the steps it keeps): an edit
that replaces the document object keeps the one before for undo; a damaged file MuPDF
repairs while it's edited, or a save that renumbers the document's objects, ends the
journal (the steps kept in it are dropped); without the resource tables found
(usable() False: another MuPDF), each edit keeps a copy of the document, as up to 1.6.
"""

import ctypes

import pymupdf

m = pymupdf.mupdf
_installed = []
_probe = []                 # [True/False]: the resource tables could be found and reset


def _pdf(doc):
    """The pdf_document of a PyMuPDF Document with a journal, or None."""
    try:
        pdf = pymupdf._as_pdf_document(doc, required=0)
    except Exception:
        return None
    if pdf is None or pdf.m_internal is None or not pdf.m_internal.journal:
        return None
    return pdf


# ---- MuPDF's tables of added fonts and images -----------------------------------------
class _Tail(ctypes.Structure):
    # the end of MuPDF's pdf_document (mupdf/pdf/document.h, 1.28): the resource tables
    # sit between fields the bindings can read, which is how they are found and checked
    _fields_ = [("num_type3_fonts", ctypes.c_int), ("max_type3_fonts", ctypes.c_int),
                ("type3_fonts", ctypes.c_void_p),
                ("fonts", ctypes.c_void_p), ("colorspaces", ctypes.c_void_p),
                ("images", ctypes.c_void_p),
                ("orphans_max", ctypes.c_int), ("orphans_count", ctypes.c_int),
                ("orphans", ctypes.c_void_p), ("xfa", ctypes.c_void_p),
                ("journal", ctypes.c_void_p), ("throw_on_repair", ctypes.c_int)]


_TAIL_AT = []
_SCAN = 1 << 18             # (the struct holds a 64 KB buffer before these fields)


def _address(swig):
    return int(swig.this) if hasattr(swig, "this") else int(swig)


def _ptr(swig):
    try:
        return _address(swig) if swig is not None else 0
    except Exception:
        return None


def _tail(pdf):
    raw = pdf.m_internal
    base = _address(raw)
    if not _TAIL_AT:
        journal = _address(raw.journal)
        step = ctypes.sizeof(ctypes.c_void_p)
        jo = _Tail.journal.offset
        for off in range(jo, _SCAN, step):
            if ctypes.c_void_p.from_address(base + off).value != journal:
                continue
            t = _Tail.from_address(base + off - jo)
            if (t.num_type3_fonts, t.max_type3_fonts, t.orphans_max, t.orphans_count,
                    t.throw_on_repair) == (raw.num_type3_fonts, raw.max_type3_fonts,
                                           raw.orphans_max, raw.orphans_count,
                                           raw.throw_on_repair) and \
                    (t.type3_fonts or 0) == (_ptr(raw.type3_fonts) or 0) and \
                    (t.xfa or 0) == (_ptr(raw.xfa) or 0):
                _TAIL_AT.append(off - jo)
                break
        else:
            raise RuntimeError("MuPDF's document layout isn't the one expected")
    t = _Tail.from_address(base + _TAIL_AT[0])
    if t.journal != _address(raw.journal):
        raise RuntimeError("MuPDF's document layout isn't the one expected")
    return t


def reset_resources(doc_or_pdf):
    """Empty MuPDF's tables of the fonts, images and color spaces added to the document
    (they are made again as needed): after an undo, an entry may name an object that is
    gone."""
    pdf = doc_or_pdf if isinstance(doc_or_pdf, m.PdfDocument) else _pdf(doc_or_pdf)
    if pdf is None:
        return
    t = _tail(pdf)
    m.ll_pdf_drop_resource_tables(pdf.m_internal)
    t.fonts = None
    t.colorspaces = None
    t.images = None


def _probe_resources():
    """Check once, on a small document, that the tables are found and that emptying them
    works (an image added, its table seen, emptied, the image added again)."""
    if _probe:
        return _probe[0]
    ok = False
    try:
        d = pymupdf.open()
        d.new_page()
        d = pymupdf.open("pdf", d.tobytes())
        pdf = pymupdf._as_pdf_document(d)
        m.pdf_enable_journal(pdf)
        pm = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 4, 4), False)
        png = pm.tobytes("png")
        m.pdf_begin_operation(pdf, "probe")
        d[0].insert_image((0, 0, 10, 10), stream=png)
        m.pdf_end_operation(pdf)
        had = _tail(pdf).images
        m.pdf_undo(pdf)
        d.InsertedImages = {}
        reset_resources(pdf)
        emptied = not _tail(pdf).images
        m.pdf_begin_operation(pdf, "probe 2")
        d[0].insert_image((0, 0, 10, 10), stream=png)
        m.pdf_end_operation(pdf)
        x = d[0].get_images()[0][0]
        ok = bool(had) and emptied and len(d.xref_stream_raw(x) or b"") > 0
        d.close()
    except Exception:
        ok = False
    _probe.append(ok)
    return ok


# ---- PyMuPDF steps made to work with a journal --------------------------------------------
def _have_operation(pdf):
    """PyMuPDF's JM_have_operation, answered properly: MuPDF refuses to give the undo state
    during an operation, and that is the sign of one."""
    if not pdf.m_internal.journal:
        return 1
    try:
        m.pdf_undoredo_state(pdf)
    except Exception:
        return 1
    return 0


def _touch(pdf, num):
    """Make the journal keep object num as it is now."""
    if num <= 0 or num >= m.pdf_xref_len(pdf):
        return
    try:
        obj = m.pdf_load_object(pdf, num)
    except Exception:
        return                          # (not there: nothing to keep)
    if m.pdf_is_dict(obj):
        key = m.pdf_new_name("KZJournal")
        m.pdf_dict_put(obj, key, m.pdf_new_int(1))
        m.pdf_dict_del(obj, key)
    elif m.pdf_is_array(obj):
        m.pdf_array_push(obj, m.pdf_new_int(0))
        m.pdf_array_delete(obj, m.pdf_array_len(obj) - 1)


# An edit kept as one entry slows down steeply as it grows: each MuPDF step that opens an
# operation of its own (adding a markup, setting its color...) merges into the edit's entry
# by comparing every object recorded so far with every other (1,000 markups added in one
# edit: 15 s instead of 0.6). So an edit in progress (Journal.begin) is cut into entries
# of SPLIT_EVERY such steps; one undo step undoes them all.
SPLIT_EVERY = 25
_ACTIVE = {}                # pdf_document address -> Journal with an edit in progress


def _tick(pdf):
    """One more step of the edit in progress on pdf (a pdf_document)."""
    if not _ACTIVE or pdf is None or pdf.m_internal is None:
        return
    j = _ACTIVE.get(_address(pdf.m_internal))
    if j is not None:
        j._calls += 1
        if j._calls >= SPLIT_EVERY:
            j._split()


def _annot_pdf(annot):
    try:
        return pymupdf._pdf_annot_page(annot).doc()
    except Exception:
        return None


def install():
    """Patch PyMuPDF (once) as the module's docstring says."""
    if _installed:
        return
    _installed.append(True)
    pymupdf.JM_have_operation = _have_operation
    update, delete = m.pdf_update_object, m.pdf_delete_object

    def update_object(pdf, num, obj):
        if pdf.m_internal is None or not pdf.m_internal.journal:
            return update(pdf, num, obj)
        _touch(pdf, num)
        update(pdf, num, obj)
        _tick(pdf)

    def delete_object(pdf, num):
        if pdf.m_internal is None or not pdf.m_internal.journal:
            return delete(pdf, num)
        _touch(pdf, num)
        update(pdf, num, m.pdf_new_dict(pdf, 0))
        _tick(pdf)
    m.pdf_update_object = update_object
    m.pdf_delete_object = delete_object

    # (the steps an edit of many markups repeats: see SPLIT_EVERY)
    # (pdf_speed replaces JM_add_annot_id, and its test checks that: hooked after it instead)
    postprocess = pymupdf.annot_postprocess

    def annot_added(page, annot):
        postprocess(page, annot)
        if _ACTIVE:
            _tick(_pdf(page.parent))
    pymupdf.annot_postprocess = annot_added
    annot_update = pymupdf.Annot.update

    def update_annot(self, *a, **k):
        out = annot_update(self, *a, **k)
        if _ACTIVE:
            _tick(_annot_pdf(self.this))
        return out
    update_annot.__doc__ = annot_update.__doc__
    pymupdf.Annot.update = update_annot

    save = pymupdf.Document.save

    def journaled_save(self, *a, **k):
        pdf = _pdf(self)
        if pdf is None:
            return save(self, *a, **k)
        raw = pdf.m_internal
        sections = raw.num_incremental_sections
        clean = pymupdf.JM_embedded_clean
        pymupdf.JM_embedded_clean = lambda pdf: None
        incremental = k.get("incremental") or (len(a) > 6 and a[6])
        garbage = k.get("garbage", a[1] if len(a) > 1 else 0) or 0
        try:
            return save(self, *a, **k)
        finally:
            pymupdf.JM_embedded_clean = clean
            if not incremental:
                raw.num_incremental_sections = sections
            if garbage >= 2:
                # objects were renumbered in the document itself: the journal no longer
                # matches it
                self._kz_journal_broken = True
    pymupdf.Document.save = journaled_save

    def plain(fn):
        def call(self, *a, **k):
            if _pdf(self) is None or not pymupdf.g_use_extra:
                return fn(self, *a, **k)
            pymupdf.g_use_extra = False
            try:
                return fn(self, *a, **k)
            finally:
                pymupdf.g_use_extra = True
        call.__name__ = fn.__name__
        call.__doc__ = fn.__doc__
        return call
    for name in ("_newPage", "insert_pdf"):
        setattr(pymupdf.Document, name, plain(getattr(pymupdf.Document, name)))


def usable():
    """True when undo can go through the journal in this PyMuPDF / MuPDF."""
    install()
    return _probe_resources()


# ---- one document's journal -------------------------------------------------------------
class Journal:
    """MuPDF's journal of one document. Between edits an implicit operation stays open (see
    the module's docstring); an edit is begin() ... end() (or abandon()), each a journal
    entry with a name of its own, so an undo can check that the entries it is about to undo
    are the ones it recorded."""

    def __init__(self, doc):
        install()
        self.doc = doc
        self.pdf = pymupdf._as_pdf_document(doc)
        self.raw = self.pdf.m_internal
        m.pdf_enable_journal(self.pdf)
        self.repaired = self.raw.repair_attempted
        self.epoch = 0              # one more each time the entries are all forgotten
        self.bytes = 0              # what measure() found
        self._n = 0
        self._parts = None          # the entries of the edit in progress
        self._ambient = False
        self._open()

    # (the implicit operation between edits)
    def _open(self):
        if not self._ambient:
            m.pdf_begin_implicit_operation(self.pdf)
            self._ambient = True

    def _close(self):
        if self._ambient:
            self._ambient = False
            m.pdf_end_operation(self.pdf)

    @property
    def alive(self):
        """False once the journal can't be trusted: the document was closed, repaired
        (MuPDF rebuilt its table of objects) or saved with objects renumbered."""
        doc = self.doc
        return not getattr(doc, "is_closed", True) and doc.this is not None and \
            not getattr(doc, "_kz_journal_broken", False) and \
            self.raw.repair_attempted == self.repaired and bool(self.raw.journal)

    @property
    def busy(self):
        """An edit is in progress (between begin and end or abandon)."""
        return self._parts is not None

    def begin(self):
        """Start an edit (kept in one or more entries: see SPLIT_EVERY)."""
        self._close()
        self._parts = []
        self._next_part()
        _ACTIVE[_address(self.raw)] = self

    def _next_part(self):
        self._n += 1
        self._name = "kz %d %d" % (id(self), self._n)
        self._calls = 0
        m.pdf_begin_operation(self.pdf, self._name)

    def _end_part(self):
        m.pdf_end_operation(self.pdf)
        pos, _steps = m.pdf_undoredo_state(self.pdf)
        if pos > 0 and m.pdf_undoredo_step(self.pdf, pos - 1) == self._name:
            self._parts.append(self._name)      # (nothing changed: no entry)

    def _split(self):
        self._end_part()
        self._next_part()

    def end(self):
        """End the edit: the names of its entries, oldest first ([]: nothing changed)."""
        _ACTIVE.pop(_address(self.raw), None)
        try:
            self._end_part()
        finally:
            parts, self._parts = self._parts, None
            self._open()
        return parts

    def abandon(self):
        """Take back the edit in progress (it failed)."""
        _ACTIVE.pop(_address(self.raw), None)
        try:
            m.pdf_abandon_operation(self.pdf)
            for name in reversed(self._parts or []):
                pos, _steps = m.pdf_undoredo_state(self.pdf)
                if pos > 0 and m.pdf_undoredo_step(self.pdf, pos - 1) == name:
                    m.pdf_undo(self.pdf)        # (left as steps to redo that none uses)
            # (unlike an undo, MuPDF's abandon leaves its caches of the objects as they were)
            m.pdf_empty_store(self.pdf)
            self._refresh()
        finally:
            self._parts = None
            self._open()

    def _names(self, lo, hi):
        return [m.pdf_undoredo_step(self.pdf, i) for i in range(lo, hi)]

    def undo(self, names):
        """Undo the entries names (oldest first) when they are the latest ones in force:
        True if done."""
        return self._step(names, -1)

    def redo(self, names):
        return self._step(names, 1)

    def _step(self, names, way):
        if not names:
            return True
        if not self.alive:
            return False
        self._close()
        try:
            pos, steps = m.pdf_undoredo_state(self.pdf)
            k = len(names)
            if way < 0:
                if pos < k or self._names(pos - k, pos) != list(names):
                    return False
                for _ in names:
                    m.pdf_undo(self.pdf)
            else:
                if pos + k > steps or self._names(pos, pos + k) != list(names):
                    return False
                for _ in names:
                    m.pdf_redo(self.pdf)
            self._refresh()
            return True
        finally:
            self._open()

    def _refresh(self):
        """What PyMuPDF and MuPDF keep about the document that the undo made old."""
        doc = self.doc
        try:
            m.ll_pdf_drop_page_tree_internal(self.raw)
            m.pdf_sync_open_pages(self.pdf)
        except Exception:
            pass
        reset_resources(self.pdf)
        doc.InsertedImages = {}
        doc.FontInfos = []
        doc.Graftmaps = {}
        try:
            doc.init_doc()          # (its outline and metadata, read once by PyMuPDF)
        except Exception:
            pass

    def measure(self):
        """Bytes the journal holds (its entries as MuPDF writes them out)."""
        self._close()
        try:
            buf = m.fz_new_buffer(1 << 16)
            out = m.FzOutput(buf)
            m.pdf_write_journal(self.pdf, out)
            out.fz_close_output()
            self.bytes = buf.m_internal.len
        except Exception:
            self.bytes = 0
        finally:
            self._open()
        return self.bytes

    def entries(self):
        """How many entries the journal holds (in force or undone)."""
        self._close()
        try:
            return m.pdf_undoredo_state(self.pdf)[1]
        finally:
            self._open()

    def discard(self):
        """Forget every entry (the steps that used them can't be undone any more)."""
        self._close()
        try:
            m.ll_pdf_discard_journal(self.raw.journal)
        finally:
            self.epoch += 1
            self.bytes = 0
            self._open()

    def restart(self):
        """Start afresh on the same document after the journal stopped matching it (a
        repair, a save that renumbered its objects)."""
        self.discard()
        self.repaired = self.raw.repair_attempted
        self.doc._kz_journal_broken = False

    def trailer(self):
        """The trailer's keys (/ID left out: every save makes it anew)."""
        doc = self.doc
        return {k: doc.xref_get_key(-1, k)[1] for k in doc.xref_get_keys(-1) if k != "ID"}

    @staticmethod
    def trailer_change(before, after):
        """(old, new): the keys an edit changed, with their values before and after (None:
        not there)."""
        keys = [k for k in set(before) | set(after) if before.get(k) != after.get(k)]
        return {k: before.get(k) for k in keys}, {k: after.get(k) for k in keys}

    def set_trailer(self, keys, whole=False):
        """Give the trailer's keys these values (None: remove it); whole: and remove the
        keys not given."""
        doc = self.doc
        now = self.trailer()
        for k in set(keys) | (set(now) if whole else set()):
            if now.get(k) != keys.get(k):
                doc.xref_set_key(-1, k, keys.get(k) or "null")
