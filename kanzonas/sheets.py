"""Sheet sets: sheet numbers read from title blocks, and the callouts that refer to them.

Drawing sets refer to other sheets all the time: a detail bubble "3 / A-501" (detail 3 on
sheet A-501), a note "SEE A-201", the sheet index on the cover. Plotted to PDF without
hyperlinks, none of that is clickable. This module reads each page's sheet number (and
title) from its title block, finds every word that names a sheet of the set, and turns those
words into links: to the page when the sheet is in this document, to a PDF in the same folder
whose name carries the sheet number when it isn't.

Only numbers that were found as sheets of the set are linked, so a stray "C150" in a spec
note is never mistaken for a sheet unless a sheet C-150 exists. "A101" and "A-101" are the
same sheet (title blocks and callouts disagree about the dash all the time).
"""

import os
import re

import pymupdf

# A-101  A101  A1.01  S-201  M-1  E1.0  AD-101  LS1.01  A-101A
_TOKEN = re.compile(r"^(?P<l>[A-Z]{1,3})[-\s]?(?P<n>\d{1,3}(?:\.\d{1,2})?)(?P<s>[A-Z]?)$")
_CAPTION = re.compile(r"^(SHEET|SHT|DWG|DRAWING)\.?\s*(NO\.?|NUMBER|#)?\s*(/\s*REV\.?)?\s*[:.]?"
                      r"(?:\s+(?P<v>\S.*))?$", re.I)
_TITLE_CAPTION = re.compile(r"^(SHEET\s+TITLE|DRAWING\s+TITLE|SHEET\s+NAME|TITLE)\s*[:.]?"
                            r"(?:\s+(?P<v>\S.*))?$", re.I)
_STRIP = ".,;:()[]{}<>\"'"


def norm(number):
    """Key that makes A-101, A101 and a-101 the same sheet."""
    return re.sub(r"[-\s]", "", number.upper())


def token(word):
    """The sheet number in one word ('A-501', '3/A-501', '(A-501)'), normalized form, or
    None."""
    w = word.strip(_STRIP).upper()
    if not w:
        return None
    parts = w.split("/") if "/" in w else [w]
    for part in parts:
        part = part.strip(_STRIP)
        if _TOKEN.match(part):
            return norm(part)
    return None


def _zone(page):
    """Where title blocks live, as displayed: the right strip and the bottom band."""
    r = page.rect
    right = pymupdf.Rect(r.x0 + r.width * 0.65, r.y0, r.x1, r.y1)
    bottom = pymupdf.Rect(r.x0, r.y0 + r.height * 0.65, r.x1, r.y1)
    return right, bottom


def _lines(page):
    try:
        blocks = page.get_text("dict", flags=pymupdf.TEXT_PRESERVE_WHITESPACE)["blocks"]
    except Exception:
        return []
    out = []
    for b in blocks:
        for ln in b.get("lines", []):
            text = "".join(sp["text"] for sp in ln["spans"]).strip()
            if text:
                size = max((sp["size"] for sp in ln["spans"]), default=0)
                out.append((text, pymupdf.Rect(ln["bbox"]), size))
    return out


def sheet_info(page):
    """{"number", "title", "rect"} read from the title block, or None. The number comes from
    the value after a SHEET / DWG NO caption when there is one, else the largest sheet-like
    token in the title block area; the title from a SHEET TITLE caption."""
    right, bottom = _zone(page)
    rot = page.rotation_matrix
    lines = [(t, r, s) for t, r, s in _lines(page)
             if (r * rot).intersects(right) or (r * rot).intersects(bottom)]
    number = title = None
    rect = None
    for i, (text, r, _s) in enumerate(lines):
        m = _TITLE_CAPTION.match(text)
        if m and title is None:
            value = m.group("v")
            if not value and i + 1 < len(lines):
                value = lines[i + 1][0]
            if value and not _CAPTION.match(value):
                title = value.strip()
            continue
        m = _CAPTION.match(text)
        if m and number is None:
            value = m.group("v")
            if not value and i + 1 < len(lines):
                value, r = lines[i + 1][0], lines[i + 1][1]
            if value:
                for w in value.split():
                    key = token(w)
                    if key:
                        number, rect = w.strip(_STRIP).upper(), r
                        break
    if number is None:
        best = None
        for text, r, size in lines:
            for w in text.split():
                if token(w) and (best is None or size > best[2] or
                                 (size == best[2] and (r * rot).y1 > (best[1] * rot).y1)):
                    best = (w.strip(_STRIP).upper(), r, size)
        if best:
            number, rect = best[0], best[1]
    if number is None:
        return None
    return {"number": number, "title": title, "rect": rect}


def scan(doc):
    """[sheet_info or None] for every page."""
    return [sheet_info(doc[i]) for i in range(doc.page_count)]


def references(page, known, own_rect=None, skip_key=None):
    """Words on the page naming a sheet in `known` ({normalized number: anything}):
    [(key, rect)]. The sheet's own number in its title block (own_rect) and self references
    (skip_key) are left out."""
    out = []
    try:
        words = page.get_text("words")
    except Exception:
        return out
    for w in words:
        key = token(w[4])
        if key is None or key not in known or key == skip_key:
            continue
        rect = pymupdf.Rect(w[:4])
        if own_rect is not None and rect.intersects(own_rect):
            continue
        out.append((key, rect))
    return out


def sibling_files(folder, keys):
    """{normalized sheet number: file name} for PDFs in `folder` whose name carries one of
    the sheet numbers (A-501 Details.pdf, Project_A501.pdf)."""
    out = {}
    try:
        names = sorted(os.listdir(folder))
    except OSError:
        return out
    for name in names:
        if not name.lower().endswith(".pdf"):
            continue
        stem = os.path.splitext(name)[0]
        for part in re.split(r"[\s_,;()\[\]]+", stem):
            key = token(part)
            if key in keys and key not in out:
                out[key] = name
    return out


def plan(doc, numbers=None, folder=None):
    """What Link sheet callouts would do. numbers: {page index: sheet number} (from scan(),
    possibly edited by the user). Returns {"pages": {index: {"number", "title"}},
    "links": [(index, rect, target)], "external": {key: file name}, "missing": {key: count}}
    where target is ("page", index) or ("file", file name)."""
    infos = scan(doc) if numbers is None else None
    pages = {}
    for i in range(doc.page_count):
        if numbers is not None:
            num = (numbers.get(i) or "").strip().upper()
            info = sheet_info(doc[i]) if num else None
            if num:
                pages[i] = {"number": num, "title": (info or {}).get("title"),
                            "rect": (info or {}).get("rect") if info and norm(info["number"]) == norm(num) else None}
        elif infos[i]:
            pages[i] = {"number": infos[i]["number"], "title": infos[i]["title"],
                        "rect": infos[i]["rect"]}
    by_key = {norm(p["number"]): i for i, p in pages.items()}
    # every sheet-like word on every page counts as a candidate for a file in the folder
    candidates = {}
    for i in range(doc.page_count):
        for w in doc[i].get_text("words"):
            k = token(w[4])
            if k and k not in by_key:
                candidates[k] = candidates.get(k, 0) + 1
    external = sibling_files(folder, set(candidates)) if folder else {}
    known = dict(by_key)
    known.update({k: None for k in external})
    links = []
    for i in range(doc.page_count):
        own = pages.get(i)
        refs = references(doc[i], known, own["rect"] if own else None,
                          norm(own["number"]) if own else None)
        for key, rect in refs:
            if key in by_key:
                links.append((i, rect, ("page", by_key[key])))
            else:
                links.append((i, rect, ("file", external[key])))
    missing = {k: n for k, n in candidates.items() if k not in external}
    return {"pages": pages, "links": links, "external": external, "missing": missing}


def _covered(page, rect):
    """True when the page already has a link over most of rect."""
    for ln in page.get_links():
        r = pymupdf.Rect(ln["from"])
        if (r & rect).get_area() > 0.5 * rect.get_area():
            return True
    return False


def apply(doc, plan_, show_box=False, bookmarks=False):
    """Create the links of a plan (skipping words that already have one) and, when asked,
    bookmarks "A-101  FIRST FLOOR PLAN" for the sheets. Returns (links made, bookmarks made)."""
    made = 0
    for index, rect, target in plan_["links"]:
        page = doc[index]
        box = rect + (-1.5, -1.5, 1.5, 1.5)
        if _covered(page, box):
            continue
        if target[0] == "page":
            link = {"kind": pymupdf.LINK_GOTO, "from": box, "page": target[1],
                    "to": pymupdf.Point(0, 0)}
        else:
            link = {"kind": pymupdf.LINK_GOTOR, "from": box, "file": target[1], "page": 0,
                    "to": pymupdf.Point(0, 0)}
        before = {x for x, _t, *_ in page.annot_xrefs()}
        page.insert_link(link)
        for xref, kind, *_ in page.annot_xrefs():
            if xref in before or kind != pymupdf.PDF_ANNOT_LINK:
                continue
            if show_box:
                doc.xref_set_key(xref, "BS", "<</W 1/S/S>>")
                doc.xref_set_key(xref, "C", "[0 0.35 0.85]")
            else:
                doc.xref_set_key(xref, "Border", "[0 0 0]")
        made += 1
    marks = 0
    if bookmarks and plan_["pages"]:
        toc = []
        for i in sorted(plan_["pages"]):
            p = plan_["pages"][i]
            label = p["number"] + (f"  {p['title']}" if p.get("title") else "")
            toc.append([1, label, i + 1])
        doc.set_toc(toc)
        marks = len(toc)
    return made, marks
