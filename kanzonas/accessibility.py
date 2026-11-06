"""Accessibility (Document > Accessibility): Check accessibility lists what keeps a PDF from
being accessible to people who use screen readers and other assistive technology, and the
fixes: title and language, tab order, form field tooltips, link descriptions, alt text for
figures, marking decoration as an artifact, embedding standard fonts, and the PDF/UA
identifier. Auto-tag (autotag.py) makes the tags of an untagged document.

The checklist is PDF/UA-1 (ISO 14289-1) as the Matterhorn Protocol 1.1 of the PDF Association
spells it out (https://pdfa.org/resource/the-matterhorn-protocol/): the failure conditions a
program can test. veraPDF's PDF/UA-1 rules
(https://github.com/veraPDF/veraPDF-validation-profiles/wiki/PDFUA-Part-1-rules) were the
reference for how each is tested. WCAG 2.1 asks for the same in a PDF (Techniques for PDF,
https://www.w3.org/WAI/WCAG21/Techniques/#pdf). What only a person can judge (the reading
order makes sense, the alt text says what the picture shows, the colors contrast enough) is
listed as such. For a formal validation: PAC 2024 (free, Windows) or veraPDF's PDF/UA profile.

No Qt here: accessibility_ui.py has the windows. check() only reads; every fix is meant to
run inside DocumentView.modify (one undo step), writing through MuPDF's objects so the journal
records it.
"""

import re

import pymupdf

from .i18n import language, tr

m = pymupdf.mupdf

# ISO 32000-1 14.8.4: the standard structure types
STANDARD = set("""Document Part Art Sect Div BlockQuote Caption TOC TOCI Index NonStruct Private
P H H1 H2 H3 H4 H5 H6 L LI Lbl LBody Table TR TH TD THead TBody TFoot Span Quote Note Reference
BibEntry Code Link Annot Ruby RB RT RP Warichu WT WP Figure Formula Form""".split())
LIST_NUMBERING = {"None", "Disc", "Circle", "Square", "Decimal", "UpperRoman", "LowerRoman",
                  "UpperAlpha", "LowerAlpha"}
LONG_DOCUMENT = 20          # pages: more than this should have bookmarks
LANGUAGES = [("en-US", "English (United States)"), ("en-GB", "English (United Kingdom)"),
             ("es-ES", "Español (España)"), ("es-MX", "Español (México)"),
             ("es-US", "Español (Estados Unidos)"), ("fr-FR", "Français"),
             ("de-DE", "Deutsch"), ("it-IT", "Italiano"), ("pt-BR", "Português (Brasil)"),
             ("pt-PT", "Português (Portugal)"), ("nl-NL", "Nederlands"), ("pl-PL", "Polski"),
             ("ca-ES", "Català"), ("zh-CN", "中文 (简体)"), ("ja-JP", "日本語"),
             ("ko-KR", "한국어"), ("ar", "العربية"), ("ru-RU", "Русский")]
_LANG_TAG = re.compile(r"^[A-Za-z]{1,8}(-[A-Za-z0-9]{1,8})*$")


def default_language():
    """The document language to offer: the app's own language (en-US, es-ES)."""
    return {"es": "es-ES"}.get(language(), "en-US")


# ---- small helpers on MuPDF objects ------------------------------------------------------
def _get(obj, key):
    return m.pdf_resolve_indirect(m.pdf_dict_gets(obj, key))


def _name(obj):
    obj = m.pdf_resolve_indirect(obj)
    return m.pdf_to_name(obj) if m.pdf_is_name(obj) else None


def _text(obj):
    obj = m.pdf_resolve_indirect(obj)
    if m.pdf_is_string(obj):
        return m.pdf_to_text_string(obj)
    return None


def _num(obj):
    return m.pdf_to_num(obj) if m.pdf_is_indirect(obj) else 0


def _items(arr):
    obj = m.pdf_resolve_indirect(arr)
    if m.pdf_is_array(obj):
        return [m.pdf_array_get(obj, i) for i in range(m.pdf_array_len(obj))]
    if obj.m_internal is not None and not m.pdf_is_null(obj):
        return [arr]
    return []


def _pdf(doc):
    return pymupdf._as_pdf_document(doc)


def _catalog(doc):
    pdf = _pdf(doc)
    return m.pdf_resolve_indirect(m.pdf_dict_gets(m.pdf_trailer(pdf), "Root"))


def number_tree(obj, out=None, depth=0):
    """{number: value (unresolved)} of a number tree."""
    out = {} if out is None else out
    obj = m.pdf_resolve_indirect(obj)
    if not m.pdf_is_dict(obj) or depth > 32:
        return out
    nums = _get(obj, "Nums")
    if m.pdf_is_array(nums):
        for i in range(0, m.pdf_array_len(nums) - 1, 2):
            k = m.pdf_array_get(nums, i)
            if m.pdf_is_int(k):
                out[m.pdf_to_int(k)] = m.pdf_array_get(nums, i + 1)
    for kid in _items(m.pdf_dict_gets(obj, "Kids")):
        number_tree(kid, out, depth + 1)
    return out


# ---- the structure tree ----------------------------------------------------------------
class Node:
    """A structure element read from the document: num (its object number, 0 when direct),
    type (/S), role (the standard type it maps to), alt, actual, page (index or None),
    kids [Node], mcids [(page index, mcid)], objrs [annotation xref], attrs (the /A
    dictionaries' keys: {"Scope": "Column"...}), parent."""
    __slots__ = ("num", "type", "role", "alt", "actual", "page", "kids", "mcids", "objrs",
                 "attrs", "parent", "obj", "headers", "ident")

    def __init__(self):
        self.num = 0
        self.type = self.role = None
        self.alt = self.actual = None
        self.page = None
        self.kids = []
        self.mcids = []
        self.objrs = []
        self.attrs = {}
        self.parent = None
        self.obj = None
        self.headers = False
        self.ident = None


class Tree:
    """The document's structure tree, read once: root (StructTreeRoot object or None),
    nodes (every element, in document order), role_map {type: mapped}, by_num {object
    number: Node}, parents {(page xref, mcid): Node}, annot_parent {annot xref: Node}."""

    LIMIT = 500000

    def __init__(self, doc):
        self.doc = doc
        self.pdf = _pdf(doc)
        cat = _catalog(doc)
        self.root = _get(cat, "StructTreeRoot")
        if not m.pdf_is_dict(self.root):
            self.root = None
        self.nodes = []
        self.by_num = {}
        self.role_map = {}
        self.page_index = {doc.page_xref(i): i for i in range(doc.page_count)}
        if self.root is None:
            return
        rm = _get(self.root, "RoleMap")
        if m.pdf_is_dict(rm):
            for i in range(m.pdf_dict_len(rm)):
                k = m.pdf_to_name(m.pdf_dict_get_key(rm, i))
                v = _name(m.pdf_dict_get_val(rm, i))
                if v:
                    self.role_map[k] = v
        seen = set()
        stack = [(kid, None) for kid in reversed(_items(m.pdf_dict_gets(self.root, "K")))]
        while stack and len(self.nodes) < self.LIMIT:
            ref, parent = stack.pop()
            obj = m.pdf_resolve_indirect(ref)
            if not m.pdf_is_dict(obj):
                continue
            num = _num(ref)
            if num:
                if num in seen:
                    continue
                seen.add(num)
            n = Node()
            n.num = num
            n.obj = obj
            n.parent = parent
            n.type = _name(m.pdf_dict_gets(obj, "S")) or ""
            n.role = self.standard(n.type)
            n.alt = _text(m.pdf_dict_gets(obj, "Alt"))
            n.actual = _text(m.pdf_dict_gets(obj, "ActualText"))
            pg = m.pdf_dict_gets(obj, "Pg")
            n.page = self.page_index.get(_num(pg)) if m.pdf_is_indirect(pg) else None
            n.ident = _text(m.pdf_dict_gets(obj, "ID"))
            n.headers = m.pdf_dict_gets(obj, "Headers").m_internal is not None and \
                not m.pdf_is_null(m.pdf_dict_gets(obj, "Headers"))
            for a in _items(m.pdf_dict_gets(obj, "A")):
                a = m.pdf_resolve_indirect(a)
                if m.pdf_is_dict(a):
                    for i in range(m.pdf_dict_len(a)):
                        k = m.pdf_to_name(m.pdf_dict_get_key(a, i))
                        v = m.pdf_dict_get_val(a, i)
                        n.attrs[k] = _name(v) or _text(v) or True
            self.nodes.append(n)
            if num:
                self.by_num[num] = n
            if parent is not None:
                parent.kids.append(n)
            kids = []
            for kid in _items(m.pdf_dict_gets(obj, "K")):
                k = m.pdf_resolve_indirect(kid)
                if m.pdf_is_int(k):
                    n.mcids.append((n.page, m.pdf_to_int(k)))
                elif m.pdf_is_dict(k):
                    t = _name(m.pdf_dict_gets(k, "Type"))
                    if t == "MCR":
                        kp = m.pdf_dict_gets(k, "Pg")
                        page = self.page_index.get(_num(kp)) if m.pdf_is_indirect(kp) \
                            else n.page
                        mc = _get(k, "MCID")
                        if m.pdf_is_int(mc):
                            n.mcids.append((page, m.pdf_to_int(mc)))
                    elif t == "OBJR":
                        o = m.pdf_dict_gets(k, "Obj")
                        if m.pdf_is_indirect(o):
                            n.objrs.append(m.pdf_to_num(o))
                    else:
                        kids.append(kid)
            stack.extend((kid, n) for kid in reversed(kids))
        self._parents = None

    def standard(self, t, depth=0):
        """The standard type t maps to (t when standard), or None (no standard one)."""
        seen = set()
        while t not in STANDARD:
            if t in seen or t not in self.role_map:
                return None
            seen.add(t)
            t = self.role_map[t]
        return t

    def parent_tree(self):
        """{struct parents number: value} of the ParentTree."""
        if self._parents is None:
            self._parents = number_tree(m.pdf_dict_gets(self.root, "ParentTree")) \
                if self.root is not None else {}
        return self._parents

    def annot_node(self, annot_xref):
        """The element an annotation hangs from (through its /StructParent), or None."""
        doc = self.doc
        kind, val = doc.xref_get_key(annot_xref, "StructParent")
        if kind != "int":
            return None
        ref = self.parent_tree().get(int(val))
        if ref is None:
            return None
        return self.by_num.get(_num(ref))



# ---- problems ------------------------------------------------------------------------------
class Problem:
    """One thing found: kind (see kind_labels), page (0-based or None), text, fix (the fix
    that deals with it: "autotag", "title", "lang", "tabs", "alt", "links", "tooltips",
    "fonts", "pdfua", or None), rule (where the requirement is: ISO 14289-1 clause and
    Matterhorn failure condition), node (a structure element's object number, or 0)."""
    __slots__ = ("kind", "page", "text", "fix", "rule", "node")

    def __init__(self, kind, page, text, fix=None, rule="", node=0):
        self.kind, self.page, self.text, self.fix, self.rule, self.node = \
            kind, page, text, fix, rule, node

    @property
    def fixable(self):
        return self.fix is not None

    def __repr__(self):
        return "Problem(%r, %r, %r, %r)" % (self.kind, self.page, self.text, self.fix)


KINDS = ("document", "content", "structure", "annots", "forms", "fonts", "manual")


def kind_labels():
    return {"document": tr("The document"), "content": tr("Page content and tags"),
            "structure": tr("Headings, lists, tables and figures"),
            "annots": tr("Links, comments and tab order"), "forms": tr("Form fields"),
            "fonts": tr("Fonts and text"), "manual": tr("Check these yourself")}


def fix_labels():
    return {"autotag": tr("Auto-tag"), "title": tr("Title and language"),
            "lang": tr("Title and language"), "tabs": tr("Tab order"),
            "alt": tr("Alt text"), "links": tr("Link descriptions"),
            "tooltips": tr("Form field tooltips"), "fonts": tr("Embed fonts"),
            "pdfua": tr("Identify as PDF/UA")}


class _Stopped(Exception):
    pass


class Checker:
    """One look at a document (nothing changes). problems: [Problem]."""

    def __init__(self, doc, step=None):
        self.doc = doc
        self.step = step
        self.problems = []
        self._seen = set()

    def add(self, kind, page, text, fix=None, rule="", node=0):
        key = (kind, page, text)
        if key in self._seen:
            return
        self._seen.add(key)
        self.problems.append(Problem(kind, page, text, fix, rule, node))

    def tick(self, i=None):
        if self.step is not None and self.step() is False:
            raise _Stopped()

    def run(self):
        doc = self.doc
        if doc.is_encrypted:
            self.add("document", None, tr("The document is locked with a password: open it "
                                          "with its password to check it."), None, "")
            return self
        self.cat = _catalog(doc)
        self.tree = Tree(doc)
        self.tagged = self.tree.root is not None
        self._document()
        self._security()
        self._pages()
        if self.tagged:
            self._structure()
        self._annotations()
        self._fonts()
        self._manual()
        return self

    # -- the document (catalog, metadata)
    def _document(self):
        doc, cat, tree = self.doc, self.cat, self.tree
        mark = _get(cat, "MarkInfo")
        marked = m.pdf_is_dict(mark) and m.pdf_to_bool(_get(mark, "Marked"))
        if not self.tagged:
            self.add("document", None, tr(
                "The document isn't tagged: it has no structure for screen readers to "
                "follow (headings, paragraphs, lists, tables, pictures, reading order). "
                "Auto-tag makes one for documents with a simple layout."), "autotag",
                "ISO 14289-1 7.1")
        elif not marked:
            self.add("document", None, tr("The document has tags but doesn't say so "
                                          "(MarkInfo Marked is not true)."), "pdfua",
                     "ISO 14289-1 7.1")
        if m.pdf_is_dict(mark) and m.pdf_to_bool(_get(mark, "Suspects")):
            self.add("document", None, tr("The tags are marked as suspect (the program that "
                                          "made them wasn't sure of them): check them."),
                     None, "ISO 14289-1 7.1, Matterhorn 01-007")
        props = doc.metadata or {}
        xmp = doc.get_xml_metadata() or ""
        title = (props.get("title") or "").strip()
        xmp_title = re.search(r"<dc:title>.*?<rdf:li[^>]*>\s*([^<]*?)\s*</rdf:li>", xmp, re.S)
        if not xmp:
            self.add("document", None, tr("The document has no XMP metadata (where its title "
                                          "is read from)."), "title",
                     "ISO 14289-1 7.1, Matterhorn 06-001")
        if not title and not (xmp_title and xmp_title.group(1)):
            self.add("document", None, tr("The document has no title."), "title",
                     "ISO 14289-1 7.1, Matterhorn 06-003")
        elif xmp and not (xmp_title and xmp_title.group(1)):
            self.add("document", None, tr("The title isn't in the XMP metadata (dc:title)."),
                     "title", "ISO 14289-1 7.1, Matterhorn 06-003")
        vp = _get(cat, "ViewerPreferences")
        ddt = _get(vp, "DisplayDocTitle") if m.pdf_is_dict(vp) else None
        if ddt is None or not m.pdf_is_bool(ddt):
            self.add("document", None, tr("The window's title bar shows the file name, not "
                                          "the document's title (DisplayDocTitle isn't set)."),
                     "title", "ISO 14289-1 7.1, Matterhorn 07-001")
        elif not m.pdf_to_bool(ddt):
            self.add("document", None, tr("The window's title bar is set to show the file "
                                          "name, not the document's title (DisplayDocTitle is "
                                          "false)."), "title",
                     "ISO 14289-1 7.1, Matterhorn 07-002")
        lang = _text(m.pdf_dict_gets(cat, "Lang"))
        if not lang or not lang.strip():
            self.add("document", None, tr("The document's language isn't set, so a screen "
                                          "reader may read it with the wrong voice and "
                                          "pronunciation."), "lang",
                     "ISO 14289-1 7.2, Matterhorn 11-001")
        elif not _LANG_TAG.match(lang.strip()):
            self.add("document", None, tr("The document's language ({lang}) isn't a valid "
                                          "language tag.").format(lang=lang), "lang",
                     "ISO 14289-1 7.2")
        if self.tagged and not re.search(r"pdfuaid:part(?:>|\s*=\s*[\"'])\s*1", xmp):
            self.add("document", None, tr(
                "The file doesn't identify itself as PDF/UA (in its XMP metadata). Add the "
                "identifier once the rest of this list is fixed."), "pdfua",
                "ISO 14289-1 5, Matterhorn 06-002")
        if doc.page_count > LONG_DOCUMENT and not doc.get_toc(simple=True):
            self.add("document", None, tr(
                "The document has {n} pages and no bookmarks: bookmarks let people move "
                "around a long document (Document > Bookmarks, or the Bookmarks panel)."
            ).format(n=doc.page_count), None, "ISO 14289-1 7.17, WCAG 2.4.5")
        ocp = _get(cat, "OCProperties")
        if m.pdf_is_dict(ocp):
            d = _get(ocp, "D")
            configs = [d] + [m.pdf_resolve_indirect(c) for c in
                             _items(m.pdf_dict_gets(ocp, "Configs"))]
            if any(m.pdf_is_dict(c) and not (_text(m.pdf_dict_gets(c, "Name")) or "").strip()
                   for c in configs):
                self.add("document", None, tr("A layer configuration has no name."), None,
                         "ISO 14289-1 7.10, Matterhorn 20-001")
        if self.tagged:
            for t, v in tree.role_map.items():
                if t in STANDARD:
                    self.add("structure", None, tr("The standard tag {tag} is mapped to "
                                                   "{other}.").format(tag=t, other=v), None,
                             "ISO 14289-1 7.1, Matterhorn 02-003")
                elif tree.standard(t) is None:
                    seen, x = set(), t
                    while x in tree.role_map and x not in seen:
                        seen.add(x)
                        x = tree.role_map[x]
                    if x in seen:
                        self.add("structure", None, tr("The tag {tag} is mapped in a "
                                                       "circle.").format(tag=t), None,
                                 "ISO 14289-1 7.1, Matterhorn 02-002")
                    else:
                        self.add("structure", None, tr("The tag {tag} doesn't map to a "
                                                       "standard tag.").format(tag=t), None,
                                 "ISO 14289-1 7.1, Matterhorn 02-001")

    def _security(self):
        doc = self.doc
        enc = (doc.metadata or {}).get("encryption")
        if enc and not (doc.permissions & pymupdf.PDF_PERM_ACCESSIBILITY):
            self.add("document", None, tr(
                "The document's security settings don't let assistive technology read "
                "its text. Change them in Protect > Security properties."), None,
                "ISO 14289-1 7.16, Matterhorn 26-002")

    # -- page content: every piece tagged or an artifact
    def _pages(self):
        from . import autotag
        doc = self.doc
        self.invisible_only = {}            # font xref -> True while only seen in Tr 3
        for i in range(doc.page_count):
            self.tick()
            page = doc[i]
            if not self.tagged:
                continue
            try:
                r = autotag.PageReader(page).read()
            except Exception:
                continue
            untagged = art_in_tag = tag_in_art = 0
            for p in r.pieces:
                kinds = [k for k, _mc, _s in p.mc if k in ("mcid", "artifact")]
                if not kinds:
                    if p.kind == "text" and p.tr == 7:
                        continue
                    untagged += 1
                    continue
                for a, b in zip(kinds, kinds[1:]):
                    if a == "mcid" and b == "artifact":
                        art_in_tag += 1
                        break
                    if a == "artifact" and b == "mcid":
                        tag_in_art += 1
                        break
            if untagged:
                self.add("content", i, tr("{n} pieces of content are neither tagged nor "
                                          "marked as artifacts (decoration).").format(
                    n=untagged), None, "ISO 14289-1 7.1, Matterhorn 01-005")
            if art_in_tag:
                self.add("content", i, tr("Content marked as an artifact sits inside tagged "
                                          "content."), None,
                         "ISO 14289-1 7.1, Matterhorn 01-003")
            if tag_in_art:
                self.add("content", i, tr("Tagged content sits inside content marked as an "
                                          "artifact."), None,
                         "ISO 14289-1 7.1, Matterhorn 01-004")

    # -- the structure tree
    def _structure(self):
        tree = self.tree
        heads = []
        has_h = has_hn = False
        for n in tree.nodes:
            role = n.role
            if role is None:
                if n.type not in tree.role_map:
                    self.add("structure", n.page, tr("The tag {tag} doesn't map to a standard "
                                                     "tag.").format(tag=n.type), None,
                             "ISO 14289-1 7.1, Matterhorn 02-001", n.num)
                continue
            if role in ("Figure", "Formula") and not ((n.alt or "").strip() or
                                                      (n.actual or "").strip()):
                self.add("structure", n.page, tr("A figure has no alternate text "
                                                 "(a description for people who can't see "
                                                 "it).") if role == "Figure" else
                         tr("A formula has no alternate text."), "alt",
                         "ISO 14289-1 7.3, Matterhorn 13-004" if role == "Figure" else
                         "ISO 14289-1 7.7, Matterhorn 17-002", n.num)
            if re.fullmatch(r"H[1-6]", role):
                heads.append((int(role[1]), n))
                has_hn = True
            elif role == "H":
                has_h = True
                if sum(1 for k in (n.parent.kids if n.parent else []) if k.role == "H") > 1:
                    self.add("structure", n.page, tr("A section holds more than one H "
                                                     "heading."), None,
                             "ISO 14289-1 7.4.4, Matterhorn 14-006", n.num)
            parent_role = n.parent.role if n.parent is not None else None
            kids = [k.role for k in n.kids]
            if role == "Table":
                bad = [k for k in kids if k not in ("TR", "THead", "TBody", "TFoot",
                                                    "Caption")]
                if bad:
                    self._bad_structure(n, tr("A table holds {what} where only rows "
                                              "belong.").format(what=bad[0]), "09-004")
                if not any(x.role == "TH" for x in self._descendants(n)):
                    self.add("structure", n.page, tr(
                        "A table has no header cells (TH): screen readers can't say which "
                        "column or row a cell belongs to. Check whether it has headers."),
                        None, "ISO 14289-1 7.5, Matterhorn 15-001/15-002", n.num)
                elif not any(x.headers for x in self._descendants(n)):
                    for th in self._descendants(n):
                        if th.role == "TH" and "Scope" not in th.attrs:
                            self.add("structure", th.page, tr(
                                "A table header cell (TH) doesn't say whether it heads a "
                                "column or a row (Scope)."), None,
                                "ISO 14289-1 7.5, Matterhorn 15-003", th.num)
                            break
            elif role in ("THead", "TBody", "TFoot"):
                if parent_role != "Table":
                    self._bad_structure(n, tr("A table part ({what}) isn't in a "
                                              "table.").format(what=role), "09-004")
                if any(k != "TR" for k in kids):
                    self._bad_structure(n, tr("A table part ({what}) holds something other "
                                              "than rows.").format(what=role), "09-004")
            elif role == "TR":
                if parent_role not in ("Table", "THead", "TBody", "TFoot"):
                    self._bad_structure(n, tr("A table row isn't in a table."), "09-004")
                if any(k not in ("TH", "TD") for k in kids):
                    self._bad_structure(n, tr("A table row holds something other than "
                                              "cells."), "09-004")
            elif role in ("TH", "TD"):
                if parent_role != "TR":
                    self._bad_structure(n, tr("A table cell isn't in a row."), "09-004")
            elif role == "L":
                if any(k not in ("L", "LI", "Caption") for k in kids):
                    self._bad_structure(n, tr("A list holds something other than list "
                                              "items."), "09-005")
                ln = n.attrs.get("ListNumbering")
                if isinstance(ln, str) and ln not in LIST_NUMBERING:
                    self.add("structure", n.page, tr("A list's numbering ({what}) isn't one "
                                                     "PDF knows.").format(what=ln), None,
                             "ISO 14289-1 7.6, Matterhorn 16-002", n.num)
            elif role == "LI":
                if parent_role != "L":
                    self._bad_structure(n, tr("A list item isn't in a list."), "09-005")
                if any(k not in ("Lbl", "LBody") for k in kids):
                    self._bad_structure(n, tr("A list item holds something other than a "
                                              "label and a body."), "09-005")
            elif role in ("Lbl", "LBody"):
                if parent_role != "LI" and not (role == "Lbl" and parent_role in
                                                ("TOCI", "BibEntry", "Note")):
                    self._bad_structure(n, tr("A list label or body isn't in a list "
                                              "item."), "09-005")
        if has_h and has_hn:
            self.add("structure", None, tr("The document uses both H and H1-H6 headings."),
                     None, "ISO 14289-1 7.4.4, Matterhorn 14-007")
        if heads:
            first = heads[0]
            if first[0] != 1:
                self.add("structure", first[1].page, tr(
                    "The first heading is H{n}, not H1.").format(n=first[0]), None,
                    "ISO 14289-1 7.4.2, Matterhorn 14-002", first[1].num)
            for (a, _na), (b, nb) in zip(heads, heads[1:]):
                if b > a + 1:
                    self.add("structure", nb.page, tr(
                        "A heading level is skipped: H{a} is followed by H{b}.").format(
                        a=a, b=b), None, "ISO 14289-1 7.4.2, Matterhorn 14-003", nb.num)

    def _bad_structure(self, n, text, number):
        self.add("structure", n.page, text, None,
                 "ISO 14289-1 7.2, Matterhorn %s" % number, n.num)

    @staticmethod
    def _descendants(n):
        out = []
        stack = list(n.kids)
        while stack:
            k = stack.pop()
            out.append(k)
            stack.extend(k.kids)
        return out

    # -- annotations: tagged, described; tab order
    def _annotations(self):
        doc, tree = self.doc, self.tree
        for i in range(doc.page_count):
            self.tick()
            page = doc[i]
            xrefs = page.annot_xrefs()
            if not xrefs:
                continue
            shown = []
            for xref, _t, _id in xrefs:
                sub = doc.xref_get_key(xref, "Subtype")[1].lstrip("/")
                f = doc.xref_get_key(xref, "F")
                hidden = f[0] == "int" and int(f[1]) & 2
                if sub in ("Popup",) or hidden:
                    continue
                shown.append((xref, sub))
            if not shown:
                continue
            tabs = doc.xref_get_key(page.xref, "Tabs")
            if tabs[1] != "/S":
                self.add("annots", i, tr("The tab order of the page's links and fields "
                                         "doesn't follow the document's structure (Tabs "
                                         "isn't S)."), "tabs",
                         "ISO 14289-1 7.18.3, Matterhorn 28-008/28-009")
            for xref, sub in shown:
                contents = doc.xref_get_key(xref, "Contents")
                has_contents = contents[0] == "string" and contents[1].strip()
                node = tree.annot_node(xref) if self.tagged else None
                role = node.role if node is not None else None
                if sub == "Link":
                    if self.tagged and role != "Link":
                        self.add("annots", i, tr("A link isn't tagged as a Link."), None,
                                 "ISO 14289-1 7.18.5, Matterhorn 28-011")
                    if not has_contents:
                        self.add("annots", i, tr("A link has no description (Contents) for "
                                                 "screen readers."), "links",
                                 "ISO 14289-1 7.18.5, Matterhorn 28-012")
                elif sub == "Widget":
                    if self.tagged and role != "Form":
                        self.add("forms", i, tr("A form field isn't tagged as a Form."), None,
                                 "ISO 14289-1 7.18.4, Matterhorn 28-010")
                    if not self._tooltip(xref) and not (node is not None and node.alt):
                        self.add("forms", i, tr("A form field has no tooltip (a name screen "
                                                "readers say)."), "tooltips",
                                 "ISO 14289-1 7.18.1, Matterhorn 28-005")
                elif sub == "PrinterMark":
                    if node is not None:
                        self.add("annots", i, tr("A printer's mark is tagged as content."),
                                 None, "ISO 14289-1 7.18.8, Matterhorn 28-016")
                else:
                    if sub == "TrapNet":
                        self.add("annots", i, tr("The page has a trap network annotation, "
                                                 "which PDF/UA doesn't allow."), None,
                                 "ISO 14289-1 7.18.2, Matterhorn 28-007")
                        continue
                    if self.tagged and role != "Annot":
                        self.add("annots", i, tr("A comment or markup ({kind}) isn't tagged "
                                                 "as an Annot.").format(kind=sub), None,
                                 "ISO 14289-1 7.18.1, Matterhorn 28-002")
                    if not has_contents and not (node is not None and node.alt):
                        self.add("annots", i, tr("A comment or markup ({kind}) has no text "
                                                 "describing it (Contents).").format(kind=sub),
                                 None, "ISO 14289-1 7.18.1, Matterhorn 28-004")

    def _tooltip(self, widget_xref):
        """The field's /TU (on the widget or a parent field)."""
        doc = self.doc
        x = widget_xref
        for _ in range(16):
            k, v = doc.xref_get_key(x, "TU")
            if k == "string" and v.strip():
                return v
            k, v = doc.xref_get_key(x, "Parent")
            if k != "xref":
                return None
            x = int(v.split()[0])
        return None

    # -- fonts: embedded, mapped to Unicode
    def _fonts(self):
        from . import pdfa
        doc = self.doc
        pdf = _pdf(doc)
        seen = set()
        dry = pdfa._Pass(doc, fix=False)
        dry.font_jobs = []
        visible = self._visible_fonts()
        for i in range(doc.page_count):
            self.tick()
            page = doc[i]
            try:
                fonts = page.get_fonts(full=True)
            except Exception:
                continue
            for xref, ext, typ, base, name, enc, _ref in fonts:
                if xref in seen or not xref:
                    continue
                seen.add(xref)
                shown = re.sub(r"^[A-Z]{6}\+", "", base or name or "?")
                d = m.pdf_load_object(pdf, xref)
                if ext == "n/a" and typ not in ("Type3",) and visible.get(xref, True):
                    before = len(dry.problems)
                    dry._font(xref, d, i)
                    fixable = any(p.fixable for p in dry.problems[before:])
                    self.add("fonts", i, tr("Font {font} isn't embedded.").format(font=shown),
                             "fonts" if fixable else None, "ISO 14289-1 7.21.4.1")
                if not self._unicode_ok(d):
                    self.add("fonts", i, tr(
                        "The text in font {font} can't be read as letters (no Unicode "
                        "mapping): screen readers, search and copying get nonsense.").format(
                        font=shown), None, "ISO 14289-1 7.21.7, Matterhorn 10-001")

    def _visible_fonts(self):
        """{font xref: False} for fonts used only for invisible text (recognized text over
        a scan: PDF/UA doesn't ask for those to be embedded). Read from the page content
        (only where the page draws invisible text)."""
        from . import autotag
        doc = self.doc
        out = {}
        for i in range(doc.page_count):
            page = doc[i]
            try:
                data = b"\n".join(doc.xref_stream(x) or b"" for x in page.get_contents())
            except Exception:
                continue
            if b"Tr" not in data:
                continue
            used = {}
            font = None
            trm = 0
            stack = []
            for op, args, _s, _e in autotag.tokens(data):
                if op == b"Tf" and args and args[0][0] == "name":
                    font = data[args[0][1] + 1:args[0][2]].decode("latin-1")
                elif op == b"Tr" and args:
                    try:
                        trm = int(float(data[args[-1][1]:args[-1][2]]))
                    except ValueError:
                        trm = 0
                elif op == b"q":
                    stack.append((font, trm))
                elif op == b"Q" and stack:
                    font, trm = stack.pop()
                elif op in (b"Tj", b"TJ", b"'", b'"') and font:
                    used[font] = used.get(font, False) or trm != 3
            names = {f[4]: f[0] for f in page.get_fonts(full=True) if f[6] == 0}
            for name, vis in used.items():
                x = names.get(name)
                if x:
                    out[x] = out.get(x, False) or vis
        return out

    @staticmethod
    def _unicode_ok(d):
        if not m.pdf_is_dict(d):
            return True
        if m.pdf_is_stream(m.pdf_dict_gets(d, "ToUnicode")):
            return True
        sub = _name(m.pdf_dict_gets(d, "Subtype"))
        if sub == "Type3":
            return False
        if sub == "Type0":
            desc = _items(m.pdf_dict_gets(d, "DescendantFonts"))
            cid = m.pdf_resolve_indirect(desc[0]) if desc else None
            info = _get(cid, "CIDSystemInfo") if cid is not None else None
            if info is not None and m.pdf_is_dict(info):
                reg = _text(m.pdf_dict_gets(info, "Registry")) or ""
                order = _text(m.pdf_dict_gets(info, "Ordering")) or ""
                if reg == "Adobe" and order in ("Japan1", "GB1", "CNS1", "Korea1"):
                    return True
            return False
        enc = m.pdf_resolve_indirect(m.pdf_dict_gets(d, "Encoding"))
        fd = _get(d, "FontDescriptor")
        flags = m.pdf_to_int(_get(fd, "Flags")) if m.pdf_is_dict(fd) else 32
        symbolic = bool(flags & 4) and not flags & 32
        if m.pdf_is_name(enc) or m.pdf_is_dict(enc):
            return True
        base = _name(m.pdf_dict_gets(d, "BaseFont")) or ""
        base = re.sub(r"^[A-Z]{6}\+", "", base)
        from . import pdfa
        if pdfa.standard_font(base) is not None:
            return True
        return not symbolic and sub == "Type1"

    # -- what only a person can check
    def _manual(self):
        for text, rule in (
                (tr("The reading order makes sense (the order screen readers read the tags "
                    "in)."), "Matterhorn 09-001"),
                (tr("Alternate text says what each picture shows, or why it's there."),
                 "Matterhorn 13-004, WCAG 1.1.1"),
                (tr("Headings, lists and tables are tagged as what they are, and nothing "
                    "else is."), "Matterhorn 01-006, 14-001, 15-004, 16-003"),
                (tr("Text and its background contrast enough (4.5:1, or 3:1 for large text); "
                    "color isn't the only way something is shown."),
                 "WCAG 1.4.1, 1.4.3, Matterhorn 04-001"),
                (tr("Headers, footers and page numbers are marked as artifacts; decoration "
                    "too."), "Matterhorn 18-001, 01-001"),
                (tr("Recognized text (OCR) is accurate."), "Matterhorn 08-001")):
            self.add("manual", None, text, None, rule)


def check(doc, step=None):
    """[Problem] of doc as it is now (only reads it). step(): called now and then; False
    stops (None is returned)."""
    try:
        return Checker(doc, step).run().problems
    except _Stopped:
        return None


def summary(problems):
    """(problems a program can find, how many a fix here deals with): the manual list
    left out."""
    real = [p for p in problems if p.kind != "manual"]
    return len(real), sum(1 for p in real if p.fix is not None)


# ---- fixes ------------------------------------------------------------------------------
def _xml(text):
    from xml.sax.saxutils import escape
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f￾￿]", "", text or "")
    return escape(text, {'"': "&quot;"})


def _xmp_skeleton():
    return ('<?xpacket begin="﻿" id="W5M0MpCehiHzreSzNTczkc9d"?>\n'
            '<x:xmpmeta xmlns:x="adobe:ns:meta/">\n'
            '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">\n'
            '</rdf:RDF>\n</x:xmpmeta>\n' + "\n".join([" " * 99] * 10) +
            '\n<?xpacket end="w"?>')


def _xmp_put(xmp, prop, block, ns_prefix, ns_uri):
    """xmp with the property prop (e.g. "dc:title") set to block (its whole element, or
    None to take it out): replaced where it is, else added in a Description of its own."""
    xmp = xmp or _xmp_skeleton()
    pat = re.compile(r"<%s\b[^>]*?(?:/>|>.*?</%s>)" % (re.escape(prop), re.escape(prop)), re.S)
    attr = re.compile(r'\s%s\s*=\s*"[^"]*"' % re.escape(prop))
    if pat.search(xmp):
        return pat.sub(lambda _m: block or "", xmp, count=1)
    if attr.search(xmp):
        xmp = attr.sub("", xmp, count=1)
    if block is None:
        return xmp
    desc = '<rdf:Description rdf:about="" xmlns:%s="%s">%s</rdf:Description>\n' % (
        ns_prefix, ns_uri, block)
    k = xmp.rfind("</rdf:RDF>")
    if k < 0:
        return _xmp_put(_xmp_skeleton(), prop, block, ns_prefix, ns_uri)
    return xmp[:k] + desc + xmp[k:]


def set_title(doc, title):
    """Title in the document properties and the XMP metadata (dc:title), and the window
    shows it (ViewerPreferences DisplayDocTitle true)."""
    title = (title or "").strip()
    meta = dict(doc.metadata or {})
    meta["title"] = title
    doc.set_metadata({k: v for k, v in meta.items() if k in (
        "title", "author", "subject", "keywords", "creator", "producer", "creationDate",
        "modDate", "trapped")} | {"title": title})
    xmp = doc.get_xml_metadata() or ""
    block = '<dc:title><rdf:Alt><rdf:li xml:lang="x-default">%s</rdf:li></rdf:Alt>' \
            '</dc:title>' % _xml(title) if title else None
    doc.set_xml_metadata(_xmp_put(xmp, "dc:title", block, "dc",
                                  "http://purl.org/dc/elements/1.1/"))
    set_display_title(doc)


def set_display_title(doc):
    cat = doc.pdf_catalog()
    kind, _v = doc.xref_get_key(cat, "ViewerPreferences")
    if kind == "dict" or kind == "xref":
        doc.xref_set_key(cat, "ViewerPreferences/DisplayDocTitle", "true")
    else:
        doc.xref_set_key(cat, "ViewerPreferences", "<</DisplayDocTitle true>>")


def set_language(doc, lang):
    """The document's natural language (/Lang in the catalog), e.g. "en-US"."""
    lang = (lang or "").strip()
    cat = doc.pdf_catalog()
    doc.xref_set_key(cat, "Lang", pymupdf.get_pdf_str(lang) if lang else "null")


def get_language(doc):
    kind, v = doc.xref_get_key(doc.pdf_catalog(), "Lang")
    if kind != "string":
        return ""
    return _text(m.pdf_dict_gets(_catalog(doc), "Lang")) or ""


def suggested_title(doc):
    """The title to offer: the document's own, else its first big line of text, else ''."""
    t = ((doc.metadata or {}).get("title") or "").strip()
    if t:
        return t
    best = None
    for i in range(min(2, doc.page_count)):
        try:
            d = doc[i].get_text("dict")
        except Exception:
            continue
        for b in d.get("blocks", []):
            for ln in b.get("lines", []):
                text = " ".join(s["text"] for s in ln["spans"]).strip()
                size = max((s["size"] for s in ln["spans"]), default=0)
                if len(text) >= 3 and any(c.isalpha() for c in text) and \
                        (best is None or size > best[0] + 0.5):
                    best = (size, text)
    return best[1][:200] if best else ""


def set_tabs(doc):
    """Every page's tab order follows the structure (/Tabs /S). Returns how many changed."""
    n = 0
    for i in range(doc.page_count):
        x = doc.page_xref(i)
        if doc.xref_get_key(x, "Tabs")[1] != "/S":
            doc.xref_set_key(x, "Tabs", "/S")
            n += 1
    return n


def set_marked(doc):
    doc.xref_set_key(doc.pdf_catalog(), "MarkInfo", "<</Marked true>>")


def set_pdfua(doc):
    """The PDF/UA-1 identifier in the XMP metadata (pdfuaid:part 1); MarkInfo Marked true."""
    xmp = doc.get_xml_metadata() or ""
    xmp = _xmp_put(xmp, "pdfuaid:part", "<pdfuaid:part>1</pdfuaid:part>", "pdfuaid",
                   "http://www.aiim.org/pdfua/ns/id/")
    doc.set_xml_metadata(xmp)
    set_marked(doc)


def embed_fonts(doc):
    """Embed the standard fonts that aren't (Helvetica, Times, Courier, Symbol,
    ZapfDingbats, and Arial, Times New Roman, Courier New drawn with them) from KanzonasPDF's
    own copies, as Save as PDF/A does: the very programs they are shown with, so the pages
    look the same. Returns how many were embedded."""
    from . import pdfa
    pdf = _pdf(doc)
    job = pdfa._Pass(doc, fix=True)
    job.font_jobs = []
    seen = set()
    for i in range(doc.page_count):
        for xref, ext, *_rest in doc[i].get_fonts(full=True):
            if xref in seen or ext != "n/a":
                continue
            seen.add(xref)
            job._font(xref, m.pdf_load_object(pdf, xref), i)
    for run in job.font_jobs:
        run()
    return len(job.font_jobs)


# -- form fields
def fields(doc):
    """[{"xref" (the widget), "field" (the field object holding /T), "page", "rect", "name",
    "tooltip", "label" (the words next to the field: a suggestion)}] of every field."""
    out = []
    for i in range(doc.page_count):
        page = doc[i]
        widgets = [x for x, t, _id in page.annot_xrefs() if t == pymupdf.PDF_ANNOT_WIDGET]
        if not widgets:
            continue
        words = None
        for w in page.widgets():
            if w.xref not in widgets:
                continue
            if words is None:
                words = page.get_text("words")
            field = _field_object(doc, w.xref)
            tip = Checker(doc)._tooltip(w.xref) or ""
            out.append({"xref": w.xref, "field": field, "page": i, "rect": pymupdf.Rect(w.rect),
                        "name": w.field_name or "", "tooltip": tip,
                        "label": _label_for(words, pymupdf.Rect(w.rect)) or
                        _readable(w.field_name or "")})
    return out


def _field_object(doc, xref):
    """The object of the field the widget belongs to (itself when it holds /T)."""
    x = xref
    for _ in range(16):
        if doc.xref_get_key(x, "T")[0] == "string":
            return x
        k, v = doc.xref_get_key(x, "Parent")
        if k != "xref":
            return xref
        x = int(v.split()[0])
    return xref


def _readable(name):
    """A field name made readable: "first_name" -> "First name"."""
    t = re.sub(r"[_\-.]+", " ", name)
    t = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", t).strip()
    t = re.sub(r"\s+\d+$", "", t) if not t.isdigit() else t
    return t[:1].upper() + t[1:].lower() if t else ""


def _label_for(words, rect):
    """The words just left of the field on its line, else just above it (a form's label)."""
    if not words:
        return ""
    h = max(4.0, rect.height)
    yc = (rect.y0 + rect.y1) / 2
    left = [w for w in words if w[2] <= rect.x0 + 2 and abs((w[1] + w[3]) / 2 - yc) < h * 0.6
            and rect.x0 - w[2] < 250]
    if left:
        left.sort(key=lambda w: w[0])
        run = [left[-1]]
        for w in reversed(left[:-1]):
            if run[0][0] - w[2] < 8:
                run.insert(0, w)
            else:
                break
        return " ".join(w[4] for w in run).strip(" :*")
    above = [w for w in words if w[3] <= rect.y0 + 2 and rect.y0 - w[3] < 2.2 * h and
             w[2] > rect.x0 - 4 and w[0] < rect.x1]
    if above:
        top = max(w[3] for w in above)
        line = sorted((w for w in above if abs(w[3] - top) < 3), key=lambda w: w[0])
        return " ".join(w[4] for w in line).strip(" :*")
    return ""


def set_tooltips(doc, tips):
    """{field object xref: tooltip text} written as each field's /TU. Returns how many."""
    n = 0
    for x, text in tips.items():
        text = (text or "").strip()
        doc.xref_set_key(x, "TU", pymupdf.get_pdf_str(text) if text else "null")
        n += 1
    return n


# -- links
def links(doc):
    """[{"xref", "page", "rect", "contents", "uri", "suggestion"}] of every link (read from
    the annotations themselves)."""
    from . import pdfcoords
    pdf = _pdf(doc)
    pages = {doc.page_xref(i): i for i in range(doc.page_count)}
    out = []
    for i in range(doc.page_count):
        page = doc[i]
        xs = [x for x, t, _id in page.annot_xrefs() if t == pymupdf.PDF_ANNOT_LINK]
        if not xs:
            continue
        tm = pdfcoords.to_page(page)
        for x in xs:
            obj = m.pdf_load_object(pdf, x)
            rect = pymupdf.Rect(0, 0, 0, 0)
            r = _get(obj, "Rect")
            if m.pdf_is_array(r) and m.pdf_array_len(r) == 4:
                rect = (pymupdf.Rect([m.pdf_to_real(m.pdf_array_get(r, k))
                                      for k in range(4)]) * tm).normalize()
            contents = _text(m.pdf_dict_gets(obj, "Contents")) or ""
            action = _get(obj, "A")
            uri = ""
            dest = m.pdf_dict_gets(obj, "Dest")
            if m.pdf_is_dict(action):
                uri = _text(m.pdf_dict_gets(action, "URI")) or ""
                if _name(m.pdf_dict_gets(action, "S")) == "GoTo":
                    dest = m.pdf_dict_gets(action, "D")
            target = None
            d = m.pdf_resolve_indirect(dest)
            if m.pdf_is_array(d) and m.pdf_array_len(d):
                target = pages.get(_num(m.pdf_array_get(d, 0)))
            words = " ".join(page.get_textbox(rect).split()) if not rect.is_empty else ""
            if not words:
                if uri:
                    words = uri
                elif target is not None:
                    words = tr("Go to page {n}").format(n=target + 1)
                elif m.pdf_is_string(d) or m.pdf_is_name(d):
                    words = _text(d) or _name(d) or ""
            out.append({"xref": x, "page": i, "rect": rect, "contents": contents,
                        "uri": uri, "suggestion": words[:300]})
    return out


def set_contents(doc, texts):
    """{annotation xref: text} written as /Contents. Returns how many."""
    for x, text in texts.items():
        text = (text or "").strip()
        doc.xref_set_key(x, "Contents", pymupdf.get_pdf_str(text) if text else "null")
    return len(texts)


# -- figures and alt text
def figures(doc):
    """[{"num" (the element's object), "page", "alt", "type", "box" (as shown, or None)}] of
    the Figure (and Formula) elements, in document order."""
    tree = Tree(doc)
    out = []
    pages = {}
    for n in tree.nodes:
        if n.role not in ("Figure", "Formula") or not n.num:
            continue
        page = n.page
        if page is None:
            page = next((p for p, _mc in n.mcids if p is not None), None)
        out.append({"num": n.num, "page": page, "alt": n.alt or "", "type": n.role,
                    "box": _figure_box(doc, n, page, pages)})
    return out


def marked_content(doc, index):
    """{MCID: (box as shown or None, text)} of what page index draws in each marked-content
    sequence with an MCID (the text in drawing order)."""
    from . import autotag
    pg = doc[index]
    r = autotag.PageReader(pg).read()
    gl = autotag.page_glyphs(pg) if r.exact and r.pieces else []
    if len(gl) != r.glyphs:
        gl = []
    boxes, texts = {}, {}
    for p in r.pieces:
        mcs = [mc for k, mc, _s in p.mc if k == "mcid"]
        if not mcs:
            continue
        mc = mcs[-1]
        b = pymupdf.Rect(p.box) if p.box is not None else None
        if p.g1 > p.g0 and gl:
            for g in gl[p.g0:p.g1]:
                r_ = pymupdf.Rect(g.x0, g.y0, g.x1, g.y1)
                b = r_ if b is None else b | r_
            texts[mc] = texts.get(mc, "") + "".join(g.c for g in gl[p.g0:p.g1])
        if b is not None:
            b &= pg.rect
            if not b.is_empty:
                boxes[mc] = b if mc not in boxes else boxes[mc] | b
    return {mc: (boxes.get(mc), texts.get(mc, "")) for mc in set(boxes) | set(texts)}


def _figure_box(doc, n, page, cache):
    """Where a figure is on its page (as shown): its BBox attribute, else what its marked
    content draws. cache: {page: marked_content} shared by the figures of a document."""
    if page is None:
        return None
    a = m.pdf_resolve_indirect(m.pdf_dict_gets(n.obj, "A"))
    for d in ([a] if m.pdf_is_dict(a) else [m.pdf_resolve_indirect(x) for x in _items(a)]):
        bb = _get(d, "BBox") if m.pdf_is_dict(d) else None
        if bb is not None and m.pdf_is_array(bb) and m.pdf_array_len(bb) == 4:
            from . import pdfcoords
            pg = doc[page]
            r = pymupdf.Rect([m.pdf_to_real(m.pdf_array_get(bb, i)) for i in range(4)]) * \
                pdfcoords.to_page(pg) * pg.rotation_matrix
            r.normalize()
            if not r.is_empty:
                return r
    want = {mc for p, mc in n.mcids if p == page}
    if not want:
        return None
    if page not in cache:
        cache[page] = marked_content(doc, page)
    box = None
    for mc in want:
        b = cache[page].get(mc, (None, ""))[0]
        if b is not None:
            box = b if box is None else box | b
    return box


# -- reading order
GROUPS = {"Document", "Part", "Art", "Sect", "Div", "NonStruct", "Private", "BlockQuote"}


def page_order(doc, index):
    """The tags of page index in reading order, for Reading order: [{"num", "type", "box",
    "text", "parent"}]: the elements just inside a grouping element (Document, Sect, Div...)
    that hold content of this page."""
    tree = Tree(doc)
    content = marked_content(doc, index)
    out = []

    def gather(n, acc_box, acc_text):
        for p, mc in n.mcids:
            if p == index and mc in content:
                b, t = content[mc]
                if b is not None:
                    acc_box[0] = b if acc_box[0] is None else acc_box[0] | b
                acc_text.append(t)
        for k in n.kids:
            gather(k, acc_box, acc_text)

    def on_page(n):
        if any(p == index for p, _mc in n.mcids):
            return True
        return any(on_page(k) for k in n.kids)
    stack = [n for n in tree.nodes if n.parent is None][::-1]
    while stack:
        n = stack.pop()
        if (n.role in GROUPS or n.role is None and n.kids) and n.kids:
            stack.extend(reversed(n.kids))
            continue
        if not n.num or not on_page(n):
            continue
        box, text = [None], []
        gather(n, box, text)
        out.append({"num": n.num, "type": n.type, "box": box[0],
                    "text": " ".join(" ".join(text).split())[:200],
                    "parent": n.parent.num if n.parent is not None else 0})
    return out


def set_order(doc, items):
    """items (page_order's, in a new order): each parent's /K gets its kids among them in
    that order, in the places they held (kids of different parents keep their parents)."""
    pdf = _pdf(doc)
    by_parent = {}
    for it in items:
        by_parent.setdefault(it["parent"], []).append(it["num"])
    root = tree_root(doc)
    for parent, nums in by_parent.items():
        obj = m.pdf_load_object(pdf, parent) if parent else root
        if obj is None:
            continue
        k = m.pdf_resolve_indirect(m.pdf_dict_gets(obj, "K"))
        if not m.pdf_is_array(k):
            continue
        slots = [i for i in range(m.pdf_array_len(k))
                 if m.pdf_is_indirect(m.pdf_array_get(k, i)) and
                 m.pdf_to_num(m.pdf_array_get(k, i)) in set(nums)]
        if len(slots) != len(nums):
            continue
        for i, num in zip(slots, nums):
            m.pdf_array_put(k, i, m.pdf_new_indirect(pdf, num, 0))


def set_alt(doc, num, text):
    """The figure (structure element num) gets text as its alternate description (/Alt;
    empty: none)."""
    text = (text or "").strip()
    doc.xref_set_key(num, "Alt", pymupdf.get_pdf_str(text) if text else "null")


def make_decorative(doc, num):
    """The figure (structure element num) is decoration: its marked content becomes an
    artifact, and the element leaves the structure tree (its parent tree entries too)."""
    from . import autotag, page_objects
    tree = Tree(doc)
    node = tree.by_num.get(num)
    if node is None:
        raise ValueError(tr("The figure is no longer in the document's tags."))
    by_page = {}
    for page, mc in node.mcids:
        if page is not None:
            by_page.setdefault(page, set()).add(mc)
    for d in tree.nodes:                         # (anything tagged inside it goes too)
        if d is not node and _inside(d, node):
            for page, mc in d.mcids:
                if page is not None:
                    by_page.setdefault(page, set()).add(mc)
    for page_index, mcids in by_page.items():
        page = doc[page_index]
        r = autotag.PageReader(page).read()
        new = _retag(r.data, mcids)
        if new != r.data:
            page_objects._set_contents(page, new)
        _drop_parents(doc, tree, page, mcids)
    _unlink(doc, node)


def _inside(n, top):
    p = n.parent
    while p is not None:
        if p is top:
            return True
        p = p.parent
    return False


_MCID_BDC = re.compile(rb"/MCID\s+(\d+)")


def _retag(data, mcids):
    """data with each BDC whose MCID is in mcids made /Artifact BMC (its EMC stays)."""
    from . import autotag
    pieces = []
    for op, args, s, e in autotag.tokens(data):
        if op != b"BDC":
            continue
        mo = _MCID_BDC.search(data[s:e])
        if mo and int(mo.group(1)) in mcids:
            pieces.append((s, e))
    out = []
    pos = 0
    for s, e in pieces:
        out.append(data[pos:s])
        out.append(b"/Artifact BMC")
        pos = e
    out.append(data[pos:])
    return b"".join(out)


def _drop_parents(doc, tree, page, mcids):
    """The parent tree's entries for these MCIDs of page made null."""
    kind, val = doc.xref_get_key(page.xref, "StructParents")
    if kind != "int":
        return
    ref = tree.parent_tree().get(int(val))
    if ref is None:
        return
    arr = m.pdf_resolve_indirect(ref)
    if not m.pdf_is_array(arr):
        return
    for mc in mcids:
        if 0 <= mc < m.pdf_array_len(arr):
            m.pdf_array_put(arr, mc, m.PdfObj())


def _unlink(doc, node):
    """Take node out of its parent's /K."""
    parent_obj = node.parent.obj if node.parent is not None else tree_root(doc)
    if parent_obj is None or not node.num:
        return
    k = m.pdf_dict_gets(parent_obj, "K")
    kr = m.pdf_resolve_indirect(k)
    if m.pdf_is_array(kr):
        for i in range(m.pdf_array_len(kr) - 1, -1, -1):
            v = m.pdf_array_get(kr, i)
            if m.pdf_is_indirect(v) and m.pdf_to_num(v) == node.num:
                m.pdf_array_delete(kr, i)
    elif m.pdf_is_indirect(k) and m.pdf_to_num(k) == node.num:
        m.pdf_dict_dels(parent_obj, "K")


def tree_root(doc):
    r = _get(_catalog(doc), "StructTreeRoot")
    return r if m.pdf_is_dict(r) else None


# -- decoration chosen with Edit objects
def mark_artifacts(page, spans):
    """The page content's pieces at byte ranges spans [(start, end)] (Edit objects' items:
    pictures and shapes) become artifacts: wrapped in /Artifact BMC ... EMC where they're
    in no marked content; where they are a tagged sequence's only content, the sequence
    becomes an artifact (and its MCID leaves the structure tree). Returns how many were
    marked; raises ValueError when one sits in tagged content with other things."""
    from . import autotag, page_objects
    doc = page.parent
    r = autotag.PageReader(page).read()
    data = r.data
    wanted = []
    for s, e in spans:
        p = next((p for p in r.pieces if p.start <= s < p.end or s <= p.start < e), None)
        if p is not None and p not in wanted:
            wanted.append(p)
    wrap = []
    retag = set()
    for p in wanted:
        kinds = [(k, mc, ser) for k, mc, ser in p.mc if k in ("mcid", "artifact")]
        if any(k == "artifact" for k, _mc, _s in kinds):
            continue
        if not kinds:
            wrap.append(p)
            continue
        mc = kinds[-1][1]
        ser = kinds[-1][2]
        others = [q for q in r.pieces if q not in wanted and
                  any(k == "mcid" and x == mc and s2 == ser for k, x, s2 in q.mc)]
        if others:
            raise ValueError(tr("A selected object is tagged together with other content "
                                "(text or other objects): it can't be marked as decoration "
                                "on its own."))
        retag.add(mc)
    if retag:
        data = _retag(data, retag)
        if wrap:
            r = autotag.PageReader(page, data=data).read()
            starts = {(p.start, p.end) for p in wrap}
            wrap = []
            for p in r.pieces:
                if (p.start, p.end) in starts:
                    wrap.append(p)
    out = []
    pos = 0
    for p in sorted(wrap, key=lambda p: p.start):
        out.append(data[pos:p.start])
        out.append(b"\n/Artifact BMC\n" + data[p.start:p.end] + b"\nEMC\n")
        pos = p.end
    out.append(data[pos:])
    new = b"".join(out)
    if new != r.data or retag:
        page_objects._set_contents(page, new)
    if retag:
        tree = Tree(doc)
        _drop_parents(doc, tree, page, retag)
        for n in list(tree.nodes):
            mine = [(pg, mc) for pg, mc in n.mcids if pg == page.number and mc in retag]
            if mine:
                _drop_kids(n, retag)
                if not n.kids and len(n.mcids) == len(mine) and not n.objrs:
                    _unlink(doc, n)
    return len(wrap) + len(retag)


def _drop_kids(node, mcids):
    """Take MCIDs out of node's /K (plain numbers and MCR dictionaries)."""
    k = m.pdf_dict_gets(node.obj, "K")
    kr = m.pdf_resolve_indirect(k)
    if m.pdf_is_int(kr):
        if m.pdf_to_int(kr) in mcids:
            m.pdf_dict_dels(node.obj, "K")
        return
    if not m.pdf_is_array(kr):
        return
    for i in range(m.pdf_array_len(kr) - 1, -1, -1):
        v = m.pdf_resolve_indirect(m.pdf_array_get(kr, i))
        mc = None
        if m.pdf_is_int(v):
            mc = m.pdf_to_int(v)
        elif m.pdf_is_dict(v) and _name(m.pdf_dict_gets(v, "Type")) == "MCR":
            x = _get(v, "MCID")
            mc = m.pdf_to_int(x) if m.pdf_is_int(x) else None
        if mc is not None and mc in mcids:
            m.pdf_array_delete(kr, i)
