"""A tagged document's tags (its structure tree, PDF 32000-1 14.7; PDF/UA) kept in step with
its pages after every edit.

Each tag (structure element) points at what it tags: marked content of a page by its MCID
(/P <</MCID 3>> BDC ... EMC), an annotation by an object reference (OBJR); the ParentTree
points back, from each page's MCIDs and each tagged annotation to its element. An edit of the
page (Edit text, Add text, Delete, a move with Edit objects or in CAD mode, a paste, Replace
pages, redaction...) changes the content without knowing about the tags, so DocumentView.modify
runs refresh() after each edit of a tagged document, in the same undo step:

- an MCID left with nothing drawn inside it (its content deleted, redacted, moved away)
  is taken out of the page (its BDC and EMC; anything nested in it stays, properly nested),
  of its element and of the ParentTree; an element left holding nothing leaves the tree
  (a table's empty cell or row stays: it keeps the grid), and its alternate text, ActualText
  and expansion with it;
- an MCID drawn twice (content copied with its marking) gets a new number for the copy, in
  the same element;
- content in no marked content (text Add text wrote, pasted text and pictures, text Edit
  text wrote anew) is tagged: text a P, a picture a Figure (with no description yet: Check
  accessibility asks for one), lines and shapes an artifact. Text written where an element
  lost all its content in the same edit (Edit text rewrites a heading, a cell, a list item;
  Edit objects or CAD mode moves a picture, also onto another page) goes back into that
  element, which keeps its type and its alternate text; other new elements go into the
  reading order where the page shows them (by their place on the page);
- markups, links and fields added after tagging get their Annot / Link / Form element (and
  a StructParent); those deleted leave the tree;
- pages added or copied get StructParents of their own: a page Duplicate pages copied gets
  copies of its original's tags (headings, lists, tables, figures with their descriptions,
  its links and markups), pages from another tagged file elements of the types their marked
  content names, Replace pages' new drawing (its own MCIDs taken out: unmark) is tagged
  anew; tags of pages deleted leave the tree.

forget_under(page, rects), before redaction marks are applied: the elements whose content a
mark touches lose their /Alt, /ActualText, /E and /T (they would describe what is redacted).

problems(doc): what is inconsistent (every MCID once and held by one element, the ParentTree
pointing back right, every annotation tagged once): the random battery and Check
accessibility use it.

No Qt here.
"""

import bisect
import re

import pymupdf

from . import autotag

m = pymupdf.mupdf

GROUPS = {"Document", "Part", "Art", "Sect", "Div", "NonStruct", "Private", "BlockQuote"}
GRID = {"TR", "TH", "TD", "THead", "TBody", "TFoot"}
SKIP_ANNOTS = {"Popup", "PrinterMark", "TrapNet"}
_ANNOT_TAG = {"Link": "Link", "Widget": "Form"}
_MCID = re.compile(rb"/MCID\s+(\d+)")
_SECRET_KEYS = ("Alt", "ActualText", "E", "T")
# tags that stand on their own (not parts of a list or table): content drawn with one of them
# and held by no element (a copied page, pages from another tagged file) gets one of its type
_STANDALONE = {"P", "H", "H1", "H2", "H3", "H4", "H5", "H6", "Figure", "Formula", "Caption",
               "Quote", "Code", "BlockQuote", "Note", "Span"}


# ---- small helpers on MuPDF objects ------------------------------------------------------
def _pdf(doc):
    return pymupdf._as_pdf_document(doc)


def _get(obj, key):
    return m.pdf_resolve_indirect(m.pdf_dict_gets(obj, key))


def _name(obj):
    obj = m.pdf_resolve_indirect(obj)
    return m.pdf_to_name(obj) if m.pdf_is_name(obj) else None


def _num(obj):
    return m.pdf_to_num(obj) if m.pdf_is_indirect(obj) else 0


def _null(obj):
    return obj.m_internal is None or m.pdf_is_null(obj)


def _items(obj):
    r = m.pdf_resolve_indirect(obj)
    if m.pdf_is_array(r):
        return [m.pdf_array_get(r, i) for i in range(m.pdf_array_len(r))]
    return [] if _null(r) else [obj]


def _same(a, b):
    """Whether two (resolved) objects are the same one."""
    return a.m_internal_value() == b.m_internal_value()


def _catalog(doc):
    return m.pdf_resolve_indirect(m.pdf_dict_gets(m.pdf_trailer(_pdf(doc)), "Root"))


def is_tagged(doc):
    try:
        return m.pdf_is_dict(_get(_catalog(doc), "StructTreeRoot"))
    except Exception:
        return False


def number_tree(obj, out=None, depth=0):
    """{number: value (unresolved)} of a number tree. Each node is read once, at most 32
    levels down: a node listed twice in /Kids, or among its own kids (a file made so), was
    read again for every path to it, 2^32 times for a node naming itself twice (Check
    accessibility, and every edit of the document, never finished)."""
    out = {} if out is None else out
    seen = set()
    todo = [(obj, depth)]
    while todo:
        ref, level = todo.pop()
        node = m.pdf_resolve_indirect(ref)
        if not m.pdf_is_dict(node) or level > 32:
            continue
        if m.pdf_is_indirect(ref):
            if m.pdf_to_num(ref) in seen:
                continue
            seen.add(m.pdf_to_num(ref))
        nums = _get(node, "Nums")
        if m.pdf_is_array(nums):
            for i in range(0, m.pdf_array_len(nums) - 1, 2):
                k = m.pdf_array_get(nums, i)
                if m.pdf_is_int(k):
                    out[m.pdf_to_int(k)] = m.pdf_array_get(nums, i + 1)
        todo.extend((kid, level + 1) for kid in reversed(_items(m.pdf_dict_gets(node, "Kids"))))
    return out


def _annot_list(doc, page_xref, pdf):
    """[(annot object number, subtype, shown)] of a page's /Annots (shown: not hidden and not
    a popup, printer's mark or trap network)."""
    out = []
    page = m.pdf_load_object(pdf, page_xref)
    for a in _items(m.pdf_dict_gets(page, "Annots")):
        num = _num(a)
        obj = m.pdf_resolve_indirect(a)
        if not num or not m.pdf_is_dict(obj):
            continue
        sub = _name(m.pdf_dict_gets(obj, "Subtype")) or ""
        f = _get(obj, "F")
        hidden = m.pdf_is_int(f) and m.pdf_to_int(f) & 2
        out.append((num, sub, not hidden and sub not in SKIP_ANNOTS))
    return out


def _page_forms(pdf, page_xref, seen):
    """The xrefs of the forms page page_xref's resources hold (also inside forms), not in
    seen (which gets them)."""
    out = []
    obj = m.pdf_load_object(pdf, page_xref)
    res = None
    for _n in range(64):
        res = _get(obj, "Resources")
        if m.pdf_is_dict(res) or not m.pdf_is_dict(obj):
            break
        obj = _get(obj, "Parent")
    todo = [res] if res is not None and m.pdf_is_dict(res) else []
    while todo and len(seen) < 100000:
        xo = _get(todo.pop(), "XObject")
        if not m.pdf_is_dict(xo):
            continue
        for i in range(m.pdf_dict_len(xo)):
            ref = m.pdf_dict_get_val(xo, i)
            if not m.pdf_is_indirect(ref) or m.pdf_to_num(ref) in seen:
                continue
            f = m.pdf_resolve_indirect(ref)
            if not m.pdf_is_dict(f) or _name(m.pdf_dict_gets(f, "Subtype")) != "Form":
                continue
            seen.add(m.pdf_to_num(ref))
            out.append(m.pdf_to_num(ref))
            r = _get(f, "Resources")
            if m.pdf_is_dict(r):
                todo.append(r)
    return out


_DRAWS = {b"Tj", b"TJ", b"'", b'"', b"Do", b"BI", b"sh", b"S", b"s", b"f", b"F", b"f*",
          b"B", b"B*", b"b", b"b*"}


def _form_mcids_drawn(doc, xref):
    """{mcid} of a form's own marked content holding something drawn."""
    data = doc.xref_stream(xref) or b""
    out, stack = set(), []
    for op, _args, s, e in autotag.tokens(data):
        if op in (b"BDC", b"BMC"):
            mo = _MCID.search(data[s:e]) if op == b"BDC" else None
            stack.append(int(mo.group(1)) if mo else None)
        elif op == b"EMC":
            if stack:
                stack.pop()
        elif op in _DRAWS:
            out.update(x for x in stack if x is not None)
    return out


def _int_key(obj, key):
    v = _get(obj, key)
    return m.pdf_to_int(v) if m.pdf_is_int(v) else None


# ---- the structure tree, read ------------------------------------------------------------
class El:
    """A structure element: obj (its dictionary), num (object number; 0 when direct),
    parent (El, or None at the top), type (/S), pg (its page's xref, own or inherited),
    kids [El], mcids [(page xref, mcid)], objrs [(annot number, page xref)], stms [(form
    xref, page xref)]: forms it tags content in (MCRs with /Stm), other (it holds content
    this doesn't follow: in a form, another stream; odd: other than in a form), gone (left
    the tree)."""
    __slots__ = ("obj", "num", "parent", "type", "pg", "kids", "mcids", "objrs", "other",
                 "gone", "order", "stms", "odd")

    def __init__(self, obj, num, parent, type_, pg, order):
        self.obj, self.num, self.parent, self.type, self.pg = obj, num, parent, type_, pg
        self.kids, self.mcids, self.objrs, self.stms = [], [], [], []
        self.other = self.odd = False
        self.gone = False
        self.order = order


class Tree:
    """The document's structure tree: root (StructTreeRoot), els (in tree order), refs
    {(page xref, mcid): [El]}, objr {annot number: [El]}, by_num {num: El}, top (the element
    new tags go into: the one Document-like element at the top, else None: the root)."""

    LIMIT = 500000

    def __init__(self, doc):
        self.doc = doc
        self.pdf = _pdf(doc)
        self.root = _get(_catalog(doc), "StructTreeRoot")
        self.els, self.refs, self.objr, self.by_num = [], {}, {}, {}
        self.page_refs = {}             # page xref -> {mcid} held
        self.stm_pages = {}             # page xref -> [El] tagging content in forms on it
        self.tops = []
        self.role_map = {}
        if not m.pdf_is_dict(self.root):
            self.root = None
            return
        rm = _get(self.root, "RoleMap")
        if m.pdf_is_dict(rm):
            for i in range(m.pdf_dict_len(rm)):
                v = _name(m.pdf_dict_get_val(rm, i))
                if v:
                    self.role_map[m.pdf_to_name(m.pdf_dict_get_key(rm, i))] = v
        seen = set()
        stack = [(kid, None, 0) for kid in reversed(_items(m.pdf_dict_gets(self.root, "K")))]
        while stack and len(self.els) < self.LIMIT:
            ref, parent, pg = stack.pop()
            obj = m.pdf_resolve_indirect(ref)
            if not m.pdf_is_dict(obj):
                continue
            num = _num(ref)
            if num:
                if num in seen:
                    continue
                seen.add(num)
            p = m.pdf_dict_gets(obj, "Pg")
            if m.pdf_is_indirect(p):
                pg = m.pdf_to_num(p)
            e = El(obj, num, parent, _name(m.pdf_dict_gets(obj, "S")) or "", pg, len(self.els))
            self.els.append(e)
            if num:
                self.by_num[num] = e
            if parent is None:
                self.tops.append(e)
            else:
                parent.kids.append(e)
            kids = []
            for kid in _items(m.pdf_dict_gets(obj, "K")):
                k = m.pdf_resolve_indirect(kid)
                if m.pdf_is_int(k):
                    self._ref(e, (pg, m.pdf_to_int(k)))
                elif m.pdf_is_dict(k):
                    t = _name(m.pdf_dict_gets(k, "Type"))
                    if t == "MCR":
                        kp = m.pdf_dict_gets(k, "Pg")
                        mc = _get(k, "MCID")
                        stm = m.pdf_dict_gets(k, "Stm")
                        if not _null(stm) or not m.pdf_is_int(mc):
                            e.other = True      # (in a form or another stream)
                            if m.pdf_is_indirect(stm) and m.pdf_is_int(mc):
                                spg = _num(kp) if m.pdf_is_indirect(kp) else pg
                                e.stms.append((m.pdf_to_num(stm), spg))
                                self.stm_pages.setdefault(spg, []).append(e)
                            else:
                                e.odd = True
                        else:
                            self._ref(e, (_num(kp) if m.pdf_is_indirect(kp) else pg,
                                          m.pdf_to_int(mc)))
                    elif t == "OBJR":
                        o = m.pdf_dict_gets(k, "Obj")
                        kp = m.pdf_dict_gets(k, "Pg")
                        if m.pdf_is_indirect(o):
                            a = (m.pdf_to_num(o), _num(kp) if m.pdf_is_indirect(kp) else pg)
                            e.objrs.append(a)
                            self.objr.setdefault(a[0], []).append(e)
                    else:
                        kids.append(kid)
            stack.extend((kid, e, pg) for kid in reversed(kids))
        self.top = None
        if len(self.tops) == 1 and self.role(self.tops[0].type) in GROUPS:
            self.top = self.tops[0]

    def _ref(self, e, key):
        e.mcids.append(key)
        self.refs.setdefault(key, []).append(e)
        self.page_refs.setdefault(key[0], set()).add(key[1])

    def _unref(self, e, key):
        lst = self.refs.get(key)
        if lst is not None:
            while e in lst:
                lst.remove(e)
            if not lst:
                del self.refs[key]
                self.page_refs.get(key[0], set()).discard(key[1])

    def role(self, t):
        seen = set()
        while t in self.role_map and t not in seen:
            seen.add(t)
            t = self.role_map[t]
        return t

    def held(self, e):
        """Whether e (or an element in it) tags anything. (The tree is walked without
        recursing, here and below: a tree thousands of elements deep, one inside the other,
        left every edit's tags out of step.)"""
        todo = [e]
        while todo:
            x = todo.pop()
            if x.mcids or x.objrs or x.other:
                return True
            todo.extend(k for k in x.kids if not k.gone)
        return False

    @staticmethod
    def within(e):
        """e and every element in it."""
        out, todo = [], [e]
        while todo:
            x = todo.pop()
            out.append(x)
            todo.extend(reversed(x.kids))
        return out

    def figure(self, e):
        return self.role(e.type) in ("Figure", "Formula")

    # -- changes
    def _k_array(self, e):
        """e's /K as an array (made one when it's a single kid or missing)."""
        obj = e.obj if e is not None else self.root
        k = m.pdf_dict_gets(obj, "K")
        kr = m.pdf_resolve_indirect(k)
        if m.pdf_is_array(kr):
            return kr
        arr = m.pdf_new_array(self.pdf, 4)
        if not _null(kr):
            m.pdf_array_push(arr, k if m.pdf_is_indirect(k) else m.pdf_deep_copy_obj(kr))
        m.pdf_dict_puts(obj, "K", arr)
        return m.pdf_dict_gets(obj, "K")

    def drop_mcid(self, e, key):
        """Take (page xref, mcid) out of e's /K."""
        pg, mc = key
        k = m.pdf_dict_gets(e.obj, "K")
        kr = m.pdf_resolve_indirect(k)
        entries = [kr] if not m.pdf_is_array(kr) else \
            [m.pdf_resolve_indirect(m.pdf_array_get(kr, i)) for i in range(m.pdf_array_len(kr))]
        for i in range(len(entries) - 1, -1, -1):
            v = entries[i]
            got = None
            if m.pdf_is_int(v):
                got = (e.pg, m.pdf_to_int(v))
            elif m.pdf_is_dict(v) and _name(m.pdf_dict_gets(v, "Type")) == "MCR":
                kp = m.pdf_dict_gets(v, "Pg")
                x = _get(v, "MCID")
                if m.pdf_is_int(x) and _null(m.pdf_dict_gets(v, "Stm")):
                    got = (_num(kp) if m.pdf_is_indirect(kp) else e.pg, m.pdf_to_int(x))
            if got == key:
                if m.pdf_is_array(kr):
                    m.pdf_array_delete(kr, i)
                else:
                    m.pdf_dict_dels(e.obj, "K")
        while key in e.mcids:
            e.mcids.remove(key)
        self._unref(e, key)

    def drop_objr(self, e, annot):
        k = m.pdf_dict_gets(e.obj, "K")
        kr = m.pdf_resolve_indirect(k)
        entries = [kr] if not m.pdf_is_array(kr) else \
            [m.pdf_resolve_indirect(m.pdf_array_get(kr, i)) for i in range(m.pdf_array_len(kr))]
        for i in range(len(entries) - 1, -1, -1):
            v = entries[i]
            if m.pdf_is_dict(v) and _name(m.pdf_dict_gets(v, "Type")) == "OBJR" and \
                    _num(m.pdf_dict_gets(v, "Obj")) == annot:
                if m.pdf_is_array(kr):
                    m.pdf_array_delete(kr, i)
                else:
                    m.pdf_dict_dels(e.obj, "K")
        e.objrs = [a for a in e.objrs if a[0] != annot]
        lst = self.objr.get(annot)
        if lst is not None:
            while e in lst:
                lst.remove(e)
            if not lst:
                del self.objr[annot]

    def move_stms(self, e, pg, to, alive):
        """e's MCRs into forms on page pg that are keys of to {old form: new form or None}:
        pointed at the new form when it still draws something of their MCID (alive {new
        form: {mcids}}), else taken out of e's /K. Returns whether e changed."""
        k = m.pdf_dict_gets(e.obj, "K")
        kr = m.pdf_resolve_indirect(k)
        arr = m.pdf_is_array(kr)
        entries = [m.pdf_resolve_indirect(m.pdf_array_get(kr, i))
                   for i in range(m.pdf_array_len(kr))] if arr else [kr]
        changed = False
        stms = []
        for i in range(len(entries) - 1, -1, -1):
            v = entries[i]
            if not m.pdf_is_dict(v) or _name(m.pdf_dict_gets(v, "Type")) != "MCR":
                continue
            stm = m.pdf_dict_gets(v, "Stm")
            if not m.pdf_is_indirect(stm) or not m.pdf_is_int(_get(v, "MCID")):
                continue
            x = m.pdf_to_num(stm)
            kp = m.pdf_dict_gets(v, "Pg")
            vpg = _num(kp) if m.pdf_is_indirect(kp) else e.pg
            if x in to and vpg == pg:
                changed = True
                new = to[x]
                if new and _int_key(v, "MCID") in alive.get(new, ()):
                    m.pdf_dict_puts(v, "Stm", m.pdf_new_indirect(self.pdf, new, 0))
                    x = new
                else:
                    if arr:
                        m.pdf_array_delete(kr, i)
                    else:
                        m.pdf_dict_dels(e.obj, "K")
                    continue
            stms.append((x, vpg))
        e.stms = stms[::-1]
        e.other = e.odd or bool(e.stms)
        return changed

    def add_mcid(self, e, pg, mc, after=None):
        """(pg, mc) into e's /K (after the MCID after of the same page, else at the end)."""
        arr = m.pdf_resolve_indirect(self._k_array(e))
        if e.pg == pg or not e.pg and not e.mcids:
            if not e.pg:
                m.pdf_dict_puts(e.obj, "Pg", m.pdf_new_indirect(self.pdf, pg, 0))
                e.pg = pg
            item = m.pdf_new_int(mc)
        else:
            item = m.pdf_new_dict(self.pdf, 3)
            m.pdf_dict_puts(item, "Type", m.pdf_new_name("MCR"))
            m.pdf_dict_puts(item, "Pg", m.pdf_new_indirect(self.pdf, pg, 0))
            m.pdf_dict_puts(item, "MCID", m.pdf_new_int(mc))
        at = None
        if after is not None:
            for i in range(m.pdf_array_len(arr)):
                v = m.pdf_resolve_indirect(m.pdf_array_get(arr, i))
                if m.pdf_is_int(v) and e.pg == pg and m.pdf_to_int(v) == after:
                    at = i + 1
                    break
                if m.pdf_is_dict(v) and _int_key(v, "MCID") == after and \
                        _num(m.pdf_dict_gets(v, "Pg")) in (pg, 0):
                    at = i + 1
                    break
        if at is None:
            m.pdf_array_push(arr, item)
        else:
            m.pdf_array_insert(arr, item, at)
        self._ref(e, (pg, mc))

    def add_objr(self, e, annot, pg):
        arr = m.pdf_resolve_indirect(self._k_array(e))
        item = m.pdf_new_dict(self.pdf, 3)
        m.pdf_dict_puts(item, "Type", m.pdf_new_name("OBJR"))
        m.pdf_dict_puts(item, "Obj", m.pdf_new_indirect(self.pdf, annot, 0))
        m.pdf_dict_puts(item, "Pg", m.pdf_new_indirect(self.pdf, pg, 0))
        m.pdf_array_push(arr, item)
        e.objrs.append((annot, pg))
        self.objr.setdefault(annot, []).append(e)

    def new_el(self, type_, pg, parent=None, at=None):
        """A new element of type_ on page pg, in parent (None: the top) at index at of its
        kids (None: the end)."""
        parent = parent if parent is not None else self.top
        doc = self.doc
        x = doc.get_new_xref()
        pref = "%d 0 R" % parent.num if parent is not None and parent.num else \
            "%d 0 R" % m.pdf_to_num(m.pdf_dict_gets(_catalog(doc), "StructTreeRoot"))
        doc.update_object(x, "<</Type /StructElem /S /%s /P %s /Pg %d 0 R /K []>>" % (
            type_, pref, pg))
        e = El(m.pdf_load_object(self.pdf, x), x, parent, type_, pg, len(self.els))
        self.els.append(e)
        self.by_num[x] = e
        self.link(e, parent, at)
        return e

    def link(self, e, parent, at=None):
        """e into parent's /K (None: the top) at index at of its kids."""
        parent = parent if parent is not None else self.top
        kids = parent.kids if parent is not None else self.tops
        arr = m.pdf_resolve_indirect(self._k_array(parent))
        ref = m.pdf_new_indirect(self.pdf, e.num, 0)
        if at is None or at >= len(kids):
            m.pdf_array_push(arr, ref)
            kids.append(e)
        else:
            # the place in /K of the kid it goes before
            nxt = kids[at]
            pos = None
            for i in range(m.pdf_array_len(arr)):
                v = m.pdf_array_get(arr, i)
                if m.pdf_is_indirect(v) and m.pdf_to_num(v) == nxt.num or \
                        not m.pdf_is_indirect(v) and m.pdf_is_dict(v) and _same(v, nxt.obj):
                    pos = i
                    break
            if pos is None:
                m.pdf_array_push(arr, ref)
            else:
                m.pdf_array_insert(arr, ref, pos)
            kids.insert(at, e)
        e.parent = parent
        obj = parent.obj if parent is not None else None
        if obj is not None and parent.num:
            m.pdf_dict_puts(e.obj, "P", m.pdf_new_indirect(self.pdf, parent.num, 0))
        elif obj is None:
            m.pdf_dict_puts(e.obj, "P", m.pdf_dict_gets(_catalog(self.doc), "StructTreeRoot"))

    def unlink(self, e):
        """Take e out of its parent's /K (it and everything in it leave the tree)."""
        parent = e.parent
        obj = parent.obj if parent is not None else self.root
        k = m.pdf_dict_gets(obj, "K")
        kr = m.pdf_resolve_indirect(k)
        if m.pdf_is_array(kr):
            for i in range(m.pdf_array_len(kr) - 1, -1, -1):
                v = m.pdf_array_get(kr, i)
                if e.num and m.pdf_is_indirect(v) and m.pdf_to_num(v) == e.num or \
                        not e.num and m.pdf_is_dict(m.pdf_resolve_indirect(v)) and \
                        _same(m.pdf_resolve_indirect(v), e.obj):
                    m.pdf_array_delete(kr, i)
        elif e.num and _num(k) == e.num or not e.num and _same(kr, e.obj):
            m.pdf_dict_dels(obj, "K")
        kids = parent.kids if parent is not None else self.tops
        if e in kids:
            kids.remove(e)

        for x in self.within(e):
            x.gone = True
            for key in list(x.mcids):
                self._unref(x, key)
            for a, _pg in x.objrs:
                lst = self.objr.get(a)
                if lst is not None and x in lst:
                    lst.remove(x)
                    if not lst:
                        del self.objr[a]

    def prune(self, e):
        """e, now holding nothing, leaves the tree with the elements around it left empty
        (not the top; a table's empty cell or row stays). Returns whether anything left."""
        if e.gone or e is self.top or self.held(e):
            return False
        x = e
        while x.parent is not None and x.parent is not self.top and \
                not self.held(x.parent):
            x = x.parent
        if self.role(x.type) in GRID:
            return False
        self.unlink(x)
        return True


# ---- a page's content, read --------------------------------------------------------------
def _piece_class(p):
    """"text", "figure", "art" (lines, shapes, shadings), or None (draws nothing: text with
    no characters, as redaction leaves it)."""
    if p.kind == "text":
        return "text" if p.codes > 0 else None
    if p.kind in ("image", "inline"):
        return "figure"
    if p.kind == "form":
        if p.form_text:
            return "text"
        return "figure" if p.has_image else "art"
    return "art"


def _inner(p):
    """The innermost MCID or artifact sequence around piece p: (kind, mcid, serial) or
    None."""
    for k, mc, ser in reversed(p.mc):
        if k in ("mcid", "artifact"):
            return k, mc, ser
    return None


def _enclosing(p):
    """The serial of the innermost other marked content around p (an added block's
    /KZText), or None."""
    for k, _mc, ser in reversed(p.mc):
        if k == "other":
            return ser
    return None


class PageState:
    """One page read: reader, seqs {serial: [mark, has content]}, present {mcid: [serials]},
    untagged [(piece, class)]."""

    def __init__(self, page):
        self.page = page
        self.r = r = autotag.PageReader(page).read()
        self.seqs = {}
        for mk in r.marks:
            if mk[1] == "mcid":
                self.seqs[mk[0]] = [mk, False]
        self.untagged = []
        inside = self._tagged_forms(page.parent) if r.form_boxes else set()
        for p in r.pieces:
            cls = _piece_class(p)
            inn = _inner(p)
            if inn is None:
                if p.kind == "form" and p.xobj in inside:
                    continue            # (tagged inside: its own MCIDs, its StructParents)
                self.untagged.append((p, cls))
            elif inn[0] == "mcid" and cls is not None and inn[2] in self.seqs:
                self.seqs[inn[2]][1] = True
        self.present = {}
        for ser, (mk, _full) in sorted(self.seqs.items(), key=lambda t: t[1][0][3]):
            self.present.setdefault(mk[2], []).append(ser)
        self._boxes = None

    def _tagged_forms(self, doc):
        """The forms drawn here whose content is tagged inside them (they, or a form they
        draw, have StructParents): drawn outside any marked content, as they should be,
        they were wrapped in an MCID of the page's as well, their content tagged twice."""
        r = self.r
        own = {f for f in r.form_boxes if doc.xref_get_key(f, "StructParents")[0] == "int"}
        out = set(own)
        for f in r.form_boxes:
            todo, seen = [f], set()
            while todo:
                x = todo.pop()
                if x in own:
                    out.add(f)
                    break
                if x not in seen:
                    seen.add(x)
                    todo.extend(r.form_kids.get(x, ()))
        return out

    def boxes(self):
        """({serial: box}, {piece start: box}) as shown, of what each MCID sequence and each
        piece draws (text by its characters)."""
        if self._boxes is not None:
            return self._boxes
        r = self.r
        gl = []
        if r.exact and any(p.g1 > p.g0 for p in r.pieces):
            gl = autotag.page_glyphs(self.page)
            if len(gl) != r.glyphs:
                gl = []
        seq_box, piece_box = {}, {}
        for p in r.pieces:
            b = pymupdf.Rect(p.box) if p.box is not None else None
            if p.g1 > p.g0 and gl:
                for g in gl[p.g0:p.g1]:
                    rg = pymupdf.Rect(g.x0, g.y0, g.x1, g.y1)
                    b = rg if b is None else b | rg
            if b is None:
                continue
            piece_box[p.start] = b
            inn = _inner(p)
            if inn is not None and inn[0] == "mcid":
                seq_box[inn[2]] = b if inn[2] not in seq_box else seq_box[inn[2]] | b
        self._boxes = seq_box, piece_box
        return self._boxes

    def piece_rects(self):
        """{serial: [boxes]} of each MCID sequence's pieces (each character on its own)."""
        r = self.r
        gl = []
        if r.exact and any(p.g1 > p.g0 for p in r.pieces):
            gl = autotag.page_glyphs(self.page)
            if len(gl) != r.glyphs:
                gl = []
        out = {}
        for p in r.pieces:
            inn = _inner(p)
            if inn is None or inn[0] != "mcid":
                continue
            rects = []
            if p.g1 > p.g0 and gl:
                rects = [pymupdf.Rect(g.x0, g.y0, g.x1, g.y1) for g in gl[p.g0:p.g1]]
            elif p.box is not None:
                rects = [pymupdf.Rect(p.box)]
            elif p.g1 > p.g0:
                rects = [pymupdf.Rect(self.page.rect)]  # (where isn't known: all of it)
            out.setdefault(inn[2], []).extend(rects)
        return out


def _units(st):
    """The page's untagged content in runs that can be wrapped in one marked-content
    sequence (pieces next to each other, of one class, with no nesting change between):
    [[class, [pieces], enclosing]]."""
    r = st.r
    evpos = [p for p, _op in r.events]
    order = {id(p): k for k, p in enumerate(r.pieces)}
    units = []
    last = None
    for p, cls in st.untagged:
        cls = cls or "art"
        ev = bisect.bisect_right(evpos, p.start)
        k = order[id(p)]
        if last is not None and last[0] == cls and last[1] == ev and last[2] == k - 1:
            units[-1][1].append(p)
        else:
            units.append([cls, [p], _enclosing(p)])
        last = (cls, ev, k)
    return units


def _groups(st, units):
    """The text and picture units in the elements they make: [[class, [unit], box]]:
    the text of one added block (one /KZText) together, or text runs drawn one right after
    the other (no tagged content between); each picture on its own."""
    order = {id(p): k for k, p in enumerate(st.r.pieces)}
    tagged_at = [k for k, p in enumerate(st.r.pieces) if _inner(p) is not None]
    groups = []
    prev = None
    for u in units:
        if u[0] == "art":
            continue
        first = order[id(u[1][0])]
        if u[0] == "text" and prev is not None and prev[0] == "text":
            last = order[id(prev[1][-1][1][-1])]
            between = bisect.bisect_right(tagged_at, first) - bisect.bisect_right(tagged_at,
                                                                                   last)
            if u[2] is not None and u[2] == prev[1][-1][2] or u[2] is None and \
                    prev[1][-1][2] is None and not between:
                prev[1].append(u)
                continue
        prev = [u[0], [u], None]
        groups.append(prev)
    _seq, piece_box = st.boxes() if groups else ({}, {})
    for g in groups:
        box = None
        for u in g[1]:
            for p in u[1]:
                b = piece_box.get(p.start)
                if b is not None:
                    box = b if box is None else box | b
        g[2] = box
    return groups


# ---- refresh -------------------------------------------------------------------------------
def _bdc(tag, mcid):
    return b"\n/%s <</MCID %d>> BDC\n" % (tag.encode("latin-1"), mcid)


class _Upkeep:
    def __init__(self, doc, structural):
        self.doc = doc
        self.pdf = _pdf(doc)
        self.structural = structural
        self.tree = Tree(doc)
        self.page_xrefs = [doc.page_xref(i) for i in range(doc.page_count)]
        self.index_of = {x: i for i, x in enumerate(self.page_xrefs)}
        self.nums = number_tree(m.pdf_dict_gets(self.tree.root, "ParentTree"))
        self.pt_dirty = False
        nk = _int_key(self.tree.root, "ParentTreeNextKey")
        self.next_key = max([nk or 0] + [k + 1 for k in self.nums])
        self.changed = set()
        self.candidates = []            # [(El, page index, class)] left empty by this edit
        self.waiting = []               # [(page index, group, [(mcid, tag)])] to place
        self._key_users = None

    # -- keys
    def key_users(self):
        """{StructParent(s) key: [("page" | "annot", xref)]} of the document as it is."""
        if self._key_users is None:
            out = {}
            doc = self.doc
            for x in self.page_xrefs:
                k = doc.xref_get_key(x, "StructParents")
                if k[0] == "int":
                    out.setdefault(int(k[1]), []).append(("page", x))
                for num, _sub, _shown in _annot_list(doc, x, self.pdf):
                    k = doc.xref_get_key(num, "StructParent")
                    if k[0] == "int":
                        out.setdefault(int(k[1]), []).append(("annot", num))
            # (forms with tagged content: their entries were taken out of the parent tree
            # at the first edit that wrote it)
            seen = set()
            for x in self.page_xrefs:
                for f in _page_forms(self.pdf, x, seen):
                    k = doc.xref_get_key(f, "StructParents")
                    if k[0] == "int":
                        out.setdefault(int(k[1]), []).append(("form", f))
            self._key_users = out
        return self._key_users

    def new_key(self):
        k = self.next_key
        self.next_key += 1
        return k

    def set_entry(self, key, value):
        self.nums[key] = value
        self.pt_dirty = True

    def write_parent_tree(self):
        if not self.pt_dirty:
            return
        users = self.key_users()
        tree = self.tree
        pdf = self.pdf
        arr = m.pdf_new_array(pdf, 2 * len(self.nums))
        for k in sorted(self.nums):
            if k not in users:
                continue
            v = self.nums[k]
            m.pdf_array_push(arr, m.pdf_new_int(k))
            m.pdf_array_push(arr, v if m.pdf_is_indirect(v) else m.pdf_deep_copy_obj(v))
        ref = m.pdf_dict_gets(tree.root, "ParentTree")
        pt = m.pdf_resolve_indirect(ref)
        if not m.pdf_is_dict(pt):
            x = self.doc.get_new_xref()
            self.doc.update_object(x, "<<>>")
            m.pdf_dict_puts(tree.root, "ParentTree", m.pdf_new_indirect(pdf, x, 0))
            pt = m.pdf_load_object(pdf, x)
        m.pdf_dict_dels(pt, "Kids")
        m.pdf_dict_dels(pt, "Limits")
        m.pdf_dict_puts(pt, "Nums", arr)
        m.pdf_dict_puts(tree.root, "ParentTreeNextKey", m.pdf_new_int(self.next_key))

    def page_entry(self, key):
        """The ParentTree's array for key ([refs]), or None."""
        v = self.nums.get(key)
        if v is None:
            return None
        a = m.pdf_resolve_indirect(v)
        if not m.pdf_is_array(a):
            return None
        return [m.pdf_array_get(a, i) for i in range(m.pdf_array_len(a))]

    # -- which pages to read
    def suspicious(self, i):
        """Whether page i may be out of step with the tags (cheap: no content parsing)."""
        doc, tree = self.doc, self.tree
        px = self.page_xrefs[i]
        k = doc.xref_get_key(px, "StructParents")
        data = doc[i].read_contents()
        found = [int(x) for x in _MCID.findall(data)]
        held = sorted(tree.page_refs.get(px, ()))
        if k[0] != "int":
            if found or held or data.strip():
                return True
        else:
            key = int(k[1])
            if len(self.key_users().get(key, ())) != 1:
                return True
            if sorted(found) != held or len(set(found)) != len(found):
                return True
            entry = self.page_entry(key)
            if entry is None:
                if found:
                    return True
            else:
                for mc in held:
                    if mc >= len(entry) or _num(entry[mc]) != tree.refs[(px, mc)][0].num:
                        return True
        here = _annot_list(doc, px, self.pdf)
        for num, _sub, shown in here:
            if shown and not self.annot_ok(num, px):
                return True
        nums = {num for num, _s, _sh in here}
        for a, els in tree.objr.items():
            if a not in nums and any((pg or e.pg) == px for e in els for x, pg in e.objrs
                                     if x == a):
                return True
        return False

    def annot_ok(self, num, px):
        sp = self.doc.xref_get_key(num, "StructParent")
        if sp[0] != "int":
            return False
        v = self.nums.get(int(sp[1]))
        e = self.tree.by_num.get(_num(v)) if v is not None else None
        return e is not None and not e.gone and any(a == num for a, _pg in e.objrs) and \
            len(self.tree.objr.get(num, ())) == 1

    # -- one page
    def page(self, i):
        doc, tree = self.doc, self.tree
        page = doc[i]
        px = page.xref
        st = PageState(page)
        st.edits, st.key, st.lost = [], None, []
        self.states[i] = st
        data = st.r.data
        edits = []                      # (start, end, replacement)
        sp = doc.xref_get_key(px, "StructParents")
        key = int(sp[1]) if sp[0] == "int" else None
        own_key = key is not None and self.page_entry(key) is not None and \
            [u for u in self.key_users().get(key, ()) if u[0] == "page"] == [("page", px)]
        if key is not None and not own_key:
            users = [u[1] for u in self.key_users().get(key, ()) if u[0] == "page"]
            # (a copied page shares its key: the page whose tags are its keeps it)
            mine = bool(tree.page_refs.get(px))
            if self.page_entry(key) is not None and users and mine and \
                    not any(tree.page_refs.get(u) for u in users if u != px):
                own_key = True
        old = self.page_entry(key) if own_key else None
        shared = self.page_entry(key) if key is not None and not own_key and any(
            u[0] == "page" and u[1] != px for u in self.key_users().get(key, ())) else None
        # MCIDs with nothing drawn inside: out of the page
        keep = {}                       # mcid -> serial kept
        renumber = []                   # (serial, mcid it copies)
        for mc, sers in st.present.items():
            for ser in sers:
                mk, full = st.seqs[ser]
                if not full and mk[5] is not None:
                    edits.append((mk[3], mk[4], b""))
                    edits.append((mk[5], mk[6], b""))
                    continue
                if mc not in keep:
                    keep[mc] = ser
                else:
                    renumber.append((ser, mc))
        # the tags of MCIDs gone
        lost = []
        self._forms_moved(px, st, lost)
        for mc in sorted(tree.page_refs.get(px, ())):
            pg = px
            els = tree.refs[(pg, mc)]
            if mc not in keep:
                for e in list(els):
                    tree.drop_mcid(e, (pg, mc))
                    lost.append(e)
            elif len(els) > 1:
                first = els[0]
                if old is not None and mc < len(old):
                    first = next((e for e in els if e.num == _num(old[mc])), first)
                for e in list(els):
                    if e is not first:
                        tree.drop_mcid(e, (pg, mc))
                        lost.append(e)
        used = set(keep)
        top_mc = [max(used) if used else -1]

        def next_mcid():
            top_mc[0] += 1
            return top_mc[0]
        unowned = [mc for mc in keep if (px, mc) not in tree.refs]
        seq_box, _pb = st.boxes() if (renumber or st.untagged or unowned) else ({}, {})
        if unowned and shared is not None:
            # a copied page (Duplicate pages): the tags of the page it copies, copied
            self._clone_copied(i, px, keep, set(unowned), shared, seq_box)
        # MCIDs no element holds: the element the ParentTree names, else a new one
        for mc, ser in sorted(keep.items()):
            if (px, mc) in tree.refs:
                continue
            owner = None
            if old is not None and mc < len(old):
                owner = tree.by_num.get(_num(old[mc]))
                if owner is not None and owner.gone:
                    owner = None
            if owner is not None:
                tree.add_mcid(owner, px, mc)
            else:
                kind = self._seq_class(st, ser)
                g = {"cls": kind, "box": seq_box.get(ser)}
                tag = self._tag_of(data, st.seqs[ser][0])
                if tag in _STANDALONE and (tag in ("Figure", "Formula")) == (kind == "figure"):
                    g["type"] = tag
                    # (a copied page: the original's figure gives its description)
                    if tag == "Figure" and shared is not None and mc < len(shared):
                        src = tree.by_num.get(_num(shared[mc]))
                        if src is not None and src.type == "Figure":
                            g["alt"] = m.pdf_dict_gets(src.obj, "Alt")
                self.waiting.append((i, g, [(mc, None)]))
        for ser, mc in renumber:
            new = next_mcid()
            mk = st.seqs[ser][0]
            bdc = data[mk[3]:mk[4]]
            if _MCID.search(bdc):
                bdc = _MCID.sub(b"/MCID %d" % new, bdc, count=1)
            else:
                bdc = _bdc(self._tag_of(data, mk), new).strip()
            edits.append((mk[3], mk[4], bdc))
            owners = tree.refs.get((px, mc))
            if owners:
                tree.add_mcid(owners[0], px, new, after=mc)
            else:
                self.waiting.append((i, {"cls": self._seq_class(st, ser),
                                         "box": seq_box.get(ser)}, [(new, None)]))
        # content in no marked content
        units = _units(st)
        for u in units:
            if u[0] == "art":
                edits.append((u[1][0].start, u[1][0].start, b"\n/Artifact BMC\n"))
                edits.append((u[1][-1].end, u[1][-1].end, b"\nEMC\n"))
        for g in _groups(st, units):
            mcids = []
            for u in g[1]:
                mc = next_mcid()
                mcids.append((mc, u))
            self.waiting.append((i, {"cls": g[0], "box": g[2]}, mcids))
        # empty elements: candidates for the content written anew in this same edit
        for e in lost:
            if not e.gone and not tree.held(e):
                self.candidates.append((e, i, "figure" if tree.figure(e) else "text"))
        st.edits = edits
        st.key = key if own_key else None
        st.lost = lost
        self.states[i] = st
        self.annots(i, st)

    def _forms_moved(self, px, st, lost):
        """MCRs into forms the page doesn't draw any more (redaction draws a copy of each
        form it changes and leaves the original in the file, which the MCR kept: the words
        redacted were still in the saved file; Edit objects deletes one): pointed at the
        copy (the form drawn with the same StructParents), else taken out (lost gets their
        elements)."""
        tree, doc = self.tree, self.doc
        els = [e for e in tree.stm_pages.get(px, ()) if not e.gone and e.stms]
        if not els:
            return
        drawn = set(st.r.form_boxes)
        gone = {x for e in els for x, pg in e.stms if pg == px and x not in drawn}
        if not gone:
            return
        held = {x for e in els for x, _pg in e.stms}
        by_key = {}
        for f in drawn - held:
            k = doc.xref_get_key(f, "StructParents")
            if k[0] == "int":
                by_key.setdefault(int(k[1]), []).append(f)
        to = {}
        for x in gone:
            k = doc.xref_get_key(x, "StructParents") if 0 < x < doc.xref_length() else \
                ("null", "")
            new = by_key.get(int(k[1]), []) if k[0] == "int" else []
            to[x] = new[0] if len(new) == 1 else None
        alive = {x: _form_mcids_drawn(doc, x) for x in set(to.values()) if x}
        for e in els:
            if tree.move_stms(e, px, to, alive):
                self.pt_dirty = True
                if not e.other:
                    lost.append(e)

    def _clone_copied(self, i, px, keep, unowned, shared, seq_box):
        """The elements (just inside the top) holding the content of the page that page i
        copies, copied for page i, where all their content is copied there (lists, tables,
        figures with their descriptions...): placed in the reading order where it shows."""
        tree = self.tree
        done = set()
        for mc in sorted(unowned):
            if (px, mc) in tree.refs or mc >= len(shared):
                continue
            src = tree.by_num.get(_num(shared[mc]))
            if src is None or src.gone or src is tree.top:
                continue
            top = src
            while top.parent is not None and top.parent is not tree.top:
                top = top.parent
            if id(top) in done:
                continue
            done.add(id(top))
            refs = []
            for e in tree.within(top):
                refs.extend(e.mcids)
                if e.other:
                    refs.append((None, None))
            pages = {pg for pg, _mc in refs}
            if len(pages) != 1 or None in pages:
                continue
            src_pg = next(iter(pages))
            if src_pg == px or any(x not in unowned or (px, x) in tree.refs
                                   for _pg, x in refs):
                continue
            box = None
            for _pg, x in refs:
                b = seq_box.get(keep.get(x))
                if b is not None:
                    box = b if box is None else box | b
            at = self.place_at(i, box)
            clone = self._clone(top, None, src_pg, px)
            tree.link(clone, None, at)

    def _clone(self, e, parent, src_pg, dst_pg):
        """A copy of element e (and the elements in it) tagging page dst_pg's copy of what e
        tags on src_pg (annotations left out: theirs are made for them). (Copied element by
        element, without recursing: see held.)"""
        top = self._clone_one(e, parent, src_pg, dst_pg)
        todo = [(top, e)]
        while todo:
            c, e = todo.pop()
            subs = self._clone_kids(c, e, src_pg, dst_pg)
            todo.extend(reversed(subs))
        return top

    def _clone_one(self, e, parent, src_pg, dst_pg):
        """A copy of element e alone (its /K still to fill: _clone_kids)."""
        doc, pdf, tree = self.doc, self.pdf, self.tree
        x = doc.get_new_xref()
        m.pdf_update_object(pdf, x, m.pdf_deep_copy_obj(e.obj))
        obj = m.pdf_load_object(pdf, x)
        for key in ("K", "ID", "Headers", "P"):
            m.pdf_dict_dels(obj, key)
        if e.pg == src_pg:
            m.pdf_dict_puts(obj, "Pg", m.pdf_new_indirect(pdf, dst_pg, 0))
        c = El(obj, x, parent, e.type, dst_pg if e.pg == src_pg else e.pg, len(tree.els))
        tree.els.append(c)
        tree.by_num[x] = c
        if parent is not None:
            m.pdf_dict_puts(obj, "P", m.pdf_new_indirect(pdf, parent.num, 0))
            parent.kids.append(c)
        return c

    def _clone_kids(self, c, e, src_pg, dst_pg):
        """c's /K: copies of e's; returns [(copy, element)] of the elements in it, whose own
        kids are still to copy."""
        doc, pdf, tree = self.doc, self.pdf, self.tree
        x = c.num
        arr = m.pdf_new_array(pdf, 4)
        kids = {id(k): k for k in e.kids}
        subs = []
        for kid in _items(m.pdf_dict_gets(e.obj, "K")):
            k = m.pdf_resolve_indirect(kid)
            if m.pdf_is_int(k):
                m.pdf_array_push(arr, m.pdf_new_int(m.pdf_to_int(k)))
                tree._ref(c, (dst_pg, m.pdf_to_int(k)))
            elif m.pdf_is_dict(k) and _name(m.pdf_dict_gets(k, "Type")) == "MCR":
                d = m.pdf_deep_copy_obj(k)
                m.pdf_dict_puts(d, "Pg", m.pdf_new_indirect(pdf, dst_pg, 0))
                m.pdf_array_push(arr, d)
                tree._ref(c, (dst_pg, _int_key(k, "MCID")))
            elif m.pdf_is_dict(k) and _name(m.pdf_dict_gets(k, "Type")) == "OBJR":
                # (the copy of the annotation: the one of its kind at its place)
                a = _num(m.pdf_dict_gets(k, "Obj"))
                if not a:
                    continue
                want = (doc.xref_get_key(a, "Subtype")[1], doc.xref_get_key(a, "Rect")[1])
                for num, _sub, shown in _annot_list(doc, dst_pg, pdf):
                    if shown and num not in tree.objr and want == (
                            doc.xref_get_key(num, "Subtype")[1],
                            doc.xref_get_key(num, "Rect")[1]):
                        item = m.pdf_new_dict(pdf, 3)
                        m.pdf_dict_puts(item, "Type", m.pdf_new_name("OBJR"))
                        m.pdf_dict_puts(item, "Obj", m.pdf_new_indirect(pdf, num, 0))
                        m.pdf_dict_puts(item, "Pg", m.pdf_new_indirect(pdf, dst_pg, 0))
                        m.pdf_array_push(arr, item)
                        c.objrs.append((num, dst_pg))
                        tree.objr.setdefault(num, []).append(c)
                        key = self.new_key()
                        doc.xref_set_key(num, "StructParent", str(key))
                        self.set_entry(key, m.pdf_new_indirect(pdf, x, 0))
                        self._key_users = None
                        break
            elif m.pdf_is_dict(k):
                src = next((kk for kk in kids.values() if (kk.num and kk.num == _num(kid)) or
                            (not kk.num and _same(kk.obj, k))), None)
                if src is None:
                    continue
                sub = self._clone_one(src, c, src_pg, dst_pg)
                m.pdf_array_push(arr, m.pdf_new_indirect(pdf, sub.num, 0))
                subs.append((sub, src))
        m.pdf_dict_puts(c.obj, "K", arr)
        return subs

    @staticmethod
    def _tag_of(data, mk):
        mo = re.match(rb"\s*/([^\s/\[\]()<>{}%]+)", data[mk[3]:mk[4]])
        return mo.group(1).decode("latin-1") if mo else "Span"

    @staticmethod
    def _seq_class(st, ser):
        kinds = set()
        for p in st.r.pieces:
            inn = _inner(p)
            if inn is not None and inn[2] == ser:
                kinds.add(_piece_class(p))
        return "figure" if kinds == {"figure"} else "text"

    def annots(self, i, st):
        doc, tree = self.doc, self.tree
        px = self.page_xrefs[i]
        here = _annot_list(doc, px, self.pdf)
        nums = {num for num, _s, _sh in here}
        # tags of annotations no longer on the page
        for a in [a for a in tree.objr if a not in nums]:
            for e in list(tree.objr.get(a, ())):
                if any(x == a and (pg or e.pg) == px for x, pg in e.objrs):
                    tree.drop_objr(e, a)
                    tree.prune(e)
                    self.pt_dirty = True
        for num, sub, shown in here:
            if not shown or self.annot_ok(num, px):
                continue
            for e in list(tree.objr.get(num, ())):
                vp = doc.xref_get_key(num, "StructParent")
                v = self.nums.get(int(vp[1])) if vp[0] == "int" else None
                if len(tree.objr.get(num, ())) > 1 and _num(v) == e.num:
                    continue
                if len(tree.objr.get(num, ())) > 1:
                    tree.drop_objr(e, num)
                    tree.prune(e)
            owner = tree.objr.get(num, [None])[0]
            if owner is None:
                rect = doc.xref_get_key(num, "Rect")[1]
                try:
                    box = pymupdf.Rect([float(v) for v in rect.strip("[]").split()])
                    page = doc[i]
                    from . import pdfcoords
                    box = (box * pdfcoords.to_page(page) * page.rotation_matrix).normalize()
                except Exception:
                    box = None
                self.waiting.append((i, {"cls": "annot", "box": box, "annot": num,
                                         "tag": _ANNOT_TAG.get(sub, "Annot")}, []))
            else:
                k = self.new_key()
                doc.xref_set_key(num, "StructParent", str(k))
                self.set_entry(k, m.pdf_new_indirect(self.pdf, owner.num, 0))
                self._key_users = None

    # -- putting the new tags in place
    def place_at(self, i, box):
        """The index among the top's kids where a new element shown at box of page i goes
        (before the first one that starts lower on the page or on a later page)."""
        tree = self.tree
        kids = tree.top.kids if tree.top is not None else tree.tops
        y = box.y0 if box is not None else float("inf")
        st = self.states.get(i)
        seq_y = {}
        if st is not None and box is not None:
            seq_box, _pb = st.boxes()
            for ser, b in seq_box.items():
                mc = st.seqs[ser][0][2]
                seq_y[mc] = min(seq_y.get(mc, b.y0), b.y0)
        px = self.page_xrefs[i]

        def first(e, acc):
            todo = [e]
            while todo:
                e = todo.pop()
                for pg, mc in e.mcids:
                    pi = self.index_of.get(pg)
                    if pi is not None:
                        acc.append((pi, seq_y.get(mc, -1.0) if pi == i else 0.0))
                for _a, pg in e.objrs:
                    pi = self.index_of.get(pg or e.pg)
                    if pi is not None:
                        acc.append((pi, -1.0 if pi == i else 0.0))
                todo.extend(k for k in e.kids if not k.gone)
        for n, e in enumerate(kids):
            acc = []
            first(e, acc)
            if not acc:
                continue
            at = min(acc)
            if at[0] > i or at[0] == i and at[1] > y + 1:
                return n
        _ = px
        return None

    def finish(self):
        tree, doc, pdf = self.tree, self.doc, self.pdf
        # pairs: an element left empty and content written anew, of one kind, on one page
        # (on another page: a move across pages; not for pages added, removed or replaced)
        paired = {}
        if not self.structural:
            # (across pages only from a page that wrote nothing of that kind anew to one
            # that lost nothing of it: a move, not two pages each edited)
            lost_on = {(c[1], c[2]) for c in self.candidates}
            wrote_on = {(w[0], w[1]["cls"]) for w in self.waiting}
            for scope in ("page", "doc"):
                taken = {id(e) for e in paired.values()}
                pools = {}
                for c in self.candidates:
                    if c[0].gone or id(c[0]) in taken or \
                            scope == "doc" and (c[1], c[2]) in wrote_on:
                        continue
                    pools.setdefault((c[1] if scope == "page" else 0, c[2]), [[], []])[0] \
                        .append(c[0])
                for k, w in enumerate(self.waiting):
                    if k in paired or w[1]["cls"] not in ("text", "figure") or not w[2] or \
                            w[2][0][1] is None:
                        continue
                    if scope == "doc" and (w[0], w[1]["cls"]) in lost_on:
                        continue
                    key = (w[0] if scope == "page" else 0, w[1]["cls"])
                    if key in pools:
                        pools[key][1].append(k)
                for (_pi, _cls), (els, ws) in pools.items():
                    if els and len(els) == len(ws):
                        for e, k in zip(sorted(els, key=lambda e: e.order), ws):
                            paired[k] = e
        used_els = {id(e) for e in paired.values()}
        for e, _i, _c in self.candidates:
            if id(e) not in used_els:
                tree.prune(e)
        # each page's new content and tags
        tags = {}
        for k, (i, g, mcids) in enumerate(self.waiting):
            px = self.page_xrefs[i]
            if g["cls"] == "annot":
                e = tree.new_el(g["tag"], px, at=self.place_at(i, g["box"]))
                tree.add_objr(e, g["annot"], px)
                key = self.new_key()
                doc.xref_set_key(g["annot"], "StructParent", str(key))
                self.set_entry(key, m.pdf_new_indirect(pdf, e.num, 0))
                self._key_users = None
                continue
            e = paired.get(k)
            if e is not None:
                if e.pg != px:          # (moved onto another page)
                    m.pdf_dict_puts(e.obj, "Pg", m.pdf_new_indirect(pdf, px, 0))
                    e.pg = px
                    at = self.place_at(i, g["box"])
                    tree.unlink(e)
                    e.gone = False
                    tree.link(e, None, at)
            else:
                e = tree.new_el(g.get("type") or ("Figure" if g["cls"] == "figure" else "P"),
                                px, at=self.place_at(i, g["box"]))
                alt = g.get("alt")
                if alt is not None and m.pdf_is_string(m.pdf_resolve_indirect(alt)):
                    m.pdf_dict_puts(e.obj, "Alt", m.pdf_deep_copy_obj(
                        m.pdf_resolve_indirect(alt)))
            for mc, _u in mcids:
                tree.add_mcid(e, px, mc)
                tags[(i, mc)] = e.type
        for i, st in self.states.items():
            edits = list(st.edits)
            for k, (pi, g, mcids) in enumerate(self.waiting):
                if pi != i:
                    continue
                for mc, u in mcids:
                    if u is None:
                        continue
                    tag = tags.get((i, mc), "P")
                    edits.append((u[1][0].start, u[1][0].start, _bdc(tag, mc)))
                    edits.append((u[1][-1].end, u[1][-1].end, b"\nEMC\n"))
            page = doc[i]
            px = page.xref
            if doc.xref_get_key(px, "Tabs")[1] != "/S" and \
                    any(sh for _n, _s, sh in _annot_list(doc, px, pdf)):
                doc.xref_set_key(px, "Tabs", "/S")    # (tab order follows the tags)
            if edits:
                data = st.r.data
                out, pos = [], 0
                for s, e, rep in sorted(edits, key=lambda t: (t[0], t[1])):
                    if s < pos:
                        continue
                    out.append(data[pos:s])
                    out.append(rep)
                    pos = e
                out.append(data[pos:])
                from . import page_objects
                page_objects._set_contents(page, b"".join(out))
                self.changed.add(i)
            # the page's ParentTree entry: its MCIDs' elements
            held = {mc: tree.refs[(px, mc)][0] for mc in tree.page_refs.get(px, ())}
            key = st.key
            if not held and key is None:
                continue
            if key is None:
                key = self.new_key()
                doc.xref_set_key(px, "StructParents", str(key))
                self._key_users = None
            entry = self.page_entry(key) or []
            want = [held[mc].num if mc in held else 0
                    for mc in range(max(held) + 1 if held else 0)]
            if [_num(v) for v in entry] != want:
                arr = m.pdf_new_array(pdf, len(want))
                for num in want:
                    m.pdf_array_push(arr, m.pdf_new_indirect(pdf, num, 0) if num else
                                     m.PdfObj())
                self.set_entry(key, arr)
        self.write_parent_tree()

    def run(self, pages):
        self.states = {}
        for i in pages:
            self.page(i)
        if self.structural:
            self._gone_pages()
        self.finish()

    def _gone_pages(self):
        """Tags of content on pages no longer in the document leave the tree."""
        tree = self.tree
        lost = []
        for (pg, mc), els in list(tree.refs.items()):
            if pg not in self.index_of:
                for e in list(els):
                    tree.drop_mcid(e, (pg, mc))
                    lost.append(e)
        for e in list(tree.els):
            for a, pg in list(e.objrs):
                if (pg or e.pg) not in self.index_of:
                    tree.drop_objr(e, a)
                    lost.append(e)
        for e in lost:
            if not e.gone:
                tree.prune(e)
        if lost:
            self.pt_dirty = True


def refresh(doc, pages=None, structural=False, changed=None):
    """The tags of a tagged document brought in step with pages (indices; None: all) after
    an edit (see the module's notes); structural: pages were added, removed or moved (all
    pages are looked at, those out of step read, and changed: the pages, by their indices
    once done, whose content the edit changed). Changes nothing when all is in step.
    Returns the pages whose content changed (their marking only: nothing looks different)."""
    if not is_tagged(doc):
        return set()
    up = _Upkeep(doc, structural)
    if up.tree.root is None:
        return set()
    if structural or pages is None:
        again = set(changed or ()) if structural else set()
        todo = [i for i in range(doc.page_count) if i in again or up.suspicious(i)]
    else:
        todo = sorted({i for i in pages if 0 <= i < doc.page_count})
    if not todo and not structural:
        return set()
    up.run(todo)
    return up.changed


def unmark(page):
    """The page's content without its MCIDs' marked content (BDC and EMC taken out, what
    is inside stays, properly nested): Replace pages brings in another file's drawing, whose
    MCIDs mean nothing here (refresh then tags it anew). Returns whether anything changed."""
    st = PageState(page)
    edits = []
    for mk, _full in st.seqs.values():
        if mk[5] is not None:
            edits.append((mk[3], mk[4]))
            edits.append((mk[5], mk[6]))
    if not edits:
        return False
    data = st.r.data
    out, pos = [], 0
    for s, e in sorted(edits):
        out.append(data[pos:s])
        pos = e
    out.append(data[pos:])
    from . import page_objects
    page_objects._set_contents(page, b"".join(out))
    return True


# ---- redaction ----------------------------------------------------------------------------
def forget_under(page, rects):
    """Before redaction marks rects are applied to page: every element tagging content any
    of them touches (and the elements around it) loses its alternate text, ActualText,
    expansion and title, which would still say what is redacted. Returns how many lost
    something."""
    doc = page.parent
    if not rects or not is_tagged(doc):
        return 0
    tree = Tree(doc)
    px = page.xref
    if not tree.page_refs.get(px) and not tree.objr and not tree.stm_pages.get(px):
        return 0
    st = PageState(page)
    rects = [pymupdf.Rect(r) for r in rects]
    shown = [r * page.rotation_matrix for r in rects] if page.rotation else rects
    hit_mc = set()
    for ser, boxes in st.piece_rects().items():
        if any(b.intersects(r) for b in boxes for r in rects + shown):
            hit_mc.add(st.seqs[ser][0][2])
    touched = []
    for mc in hit_mc:
        touched.extend(tree.refs.get((px, mc), ()))
    # content tagged inside a form (an MCR with /Stm) a mark touches: the form, or a form
    # drawing it, drawn where a mark is (its box)
    if tree.stm_pages.get(px):
        hit = set()
        for f, boxes in st.r.form_boxes.items():
            if any(b is not None and pymupdf.Rect(b).intersects(r) for b in boxes
                   for r in rects + shown):
                todo = [f]
                while todo:
                    x = todo.pop()
                    if x not in hit:
                        hit.add(x)
                        todo.extend(st.r.form_kids.get(x, ()))
        touched.extend(e for e in tree.stm_pages[px] if any(
            x in hit for x, pg in e.stms if pg == px))
    return _forget(tree, page, touched, rects)


def forget_hidden(doc):
    """Before Sanitize takes out hidden text: the elements tagging invisible text (text
    render mode 3) lose their alternate text, ActualText, expansion and title. Returns how
    many lost something."""
    if not is_tagged(doc):
        return 0
    tree = Tree(doc)
    n = 0
    for i in range(doc.page_count):
        page = doc[i]
        if not tree.page_refs.get(page.xref):
            continue
        st = PageState(page)
        touched = []
        for p in st.r.pieces:
            inn = _inner(p)
            if p.kind == "text" and p.tr == 3 and p.codes and inn is not None and \
                    inn[0] == "mcid":
                touched.extend(tree.refs.get((page.xref, inn[1]), ()))
        n += _forget(tree, page, touched, [])
    return n


def _forget(tree, page, touched, rects):
    """touched and the elements around them lose their texts (_SECRET_KEYS); so do the
    elements of the page's annotations a rect touches."""
    doc = page.parent
    px = page.xref
    for num, _sub, _shown in _annot_list(doc, px, tree.pdf):
        kind, val = doc.xref_get_key(num, "Rect")
        try:
            r = pymupdf.Rect([float(v) for v in val.strip("[]").split()])
            from . import pdfcoords
            r = (r * pdfcoords.to_page(page)).normalize()
        except Exception:
            continue
        if any(r.intersects(x) for x in rects):
            touched.extend(tree.objr.get(num, ()))
    done = set()
    n = 0
    for e in touched:
        x = e
        while x is not None and id(x) not in done:
            done.add(id(x))
            lost = False
            for key in _SECRET_KEYS:
                if not _null(m.pdf_dict_gets(x.obj, key)):
                    m.pdf_dict_dels(x.obj, key)
                    lost = True
            n += lost
            x = x.parent
    return n


# ---- checking ------------------------------------------------------------------------------
def problems(doc):
    """What is out of step between the tags and the pages: [(page index or None, text)]
    (plain English, for tests and the battery; Check accessibility words its own)."""
    if not is_tagged(doc):
        return []
    tree = Tree(doc)
    out = []
    pdf = tree.pdf
    nums = number_tree(m.pdf_dict_gets(tree.root, "ParentTree"))
    keys = {}
    index_of = {doc.page_xref(i): i for i in range(doc.page_count)}
    for (pg, mc), els in tree.refs.items():
        if pg not in index_of:
            out.append((None, "MCID %d of a page not in the document is tagged" % mc))
        if len(els) > 1:
            out.append((index_of.get(pg), "MCID %d is held by %d elements" % (mc, len(els))))
    for e in tree.els:
        if len(set(e.mcids)) != len(e.mcids):
            out.append((index_of.get(e.pg), "an element holds an MCID twice"))
    for i in range(doc.page_count):
        page = doc[i]
        px = page.xref
        st = PageState(page)
        present = st.present
        for mc, sers in present.items():
            if len(sers) > 1:
                out.append((i, "MCID %d is drawn %d times" % (mc, len(sers))))
            if (px, mc) not in tree.refs:
                out.append((i, "MCID %d is in no element" % mc))
        for (pg, mc) in tree.refs:
            if pg == px and mc not in present:
                out.append((i, "MCID %d is tagged but not on the page" % mc))
        for p, _cls in st.untagged:
            if p.kind == "text" and p.tr == 7:
                continue
            out.append((i, "%s content is neither tagged nor an artifact" % p.kind))
            break
        k = doc.xref_get_key(px, "StructParents")
        if present:
            if k[0] != "int":
                out.append((i, "the page has MCIDs but no StructParents"))
            else:
                keys.setdefault(int(k[1]), []).append(("page", i))
                v = nums.get(int(k[1]))
                arr = m.pdf_resolve_indirect(v) if v is not None else None
                if arr is None or not m.pdf_is_array(arr):
                    out.append((i, "the ParentTree has no entry for the page"))
                else:
                    for mc in present:
                        els = tree.refs.get((px, mc))
                        if not els:
                            continue
                        if mc >= m.pdf_array_len(arr) or \
                                _num(m.pdf_array_get(arr, mc)) != els[0].num:
                            out.append((i, "the ParentTree is wrong for MCID %d" % mc))
        elif k[0] == "int":
            keys.setdefault(int(k[1]), []).append(("page", i))
        for num, sub, shown in _annot_list(doc, px, pdf):
            sp = doc.xref_get_key(num, "StructParent")
            if sp[0] == "int":
                keys.setdefault(int(sp[1]), []).append(("annot", num))
            if not shown:
                continue
            els = tree.objr.get(num, [])
            if len(els) != 1:
                out.append((i, "a %s annotation is held by %d elements" % (sub, len(els))))
                continue
            v = nums.get(int(sp[1])) if sp[0] == "int" else None
            if v is None or _num(v) != els[0].num:
                out.append((i, "a %s annotation's StructParent is wrong" % sub))
        here = {num for num, _s, _sh in _annot_list(doc, px, pdf)}
        for e in tree.els:
            for a, pg in e.objrs:
                if (pg or e.pg) == px and a not in here:
                    out.append((i, "an element points at an annotation not on the page"))
    seen = set()
    for i in range(doc.page_count):
        for f in _page_forms(pdf, doc.page_xref(i), seen):
            sp = doc.xref_get_key(f, "StructParents")
            if sp[0] == "int":
                keys.setdefault(int(sp[1]), []).append(("form", f))
                if int(sp[1]) not in nums:
                    out.append((i, "a form's StructParents has no ParentTree entry"))
    for k, users in keys.items():
        if len(users) > 1:
            out.append((None, "StructParents key %d is used %d times" % (k, len(users))))
    return out
