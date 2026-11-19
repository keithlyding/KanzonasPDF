"""Count markers (the Count tool, Shift+C): their groups and numbers across a document.

Each marker is one circle annotation with its group's name (props "group") and its number
(model "n"). A group whose markers keep their numbers in order (props "order", on unless
switched off in Properties) is numbered 1, 2, 3... again when one of its markers is deleted
or moved to another group, so its numbers have no gaps.

Issue #107 (19 Nov 2026): "Is there a way to reset the count and set the layers and labels
like a properties box ... if I remove one count it will just continue from the last
(checkbox would be nice to turn on or off this behavior, so that it will always have the
correct numbering if they are in the same series or group)".
"""
import pymupdf

from . import annotations
from .i18n import tr

DEFAULT_GROUP = "Count 1"


def group_of(model):
    return (model["props"].get("group") or "").strip() or DEFAULT_GROUP


def is_marker(doc, xref):
    """True when the annotation is a Count marker, from its stored kind alone (an ellipse is
    a circle annotation too: one read of each, to delete 1,000, took longer than the delete)."""
    try:
        typ, val = doc.xref_get_key(xref, annotations.KZ_KEY)
    except Exception:
        return False                # (not an object of this document: not a marker)
    return typ == "string" and '"m_count"' in val


def markers(doc, groups=None):
    """[(page index, xref, model)] of the document's Count markers (only those in groups,
    when given), in page order."""
    out = []
    for i in range(doc.page_count):
        page = doc[i]
        for a in annotations.each_annot(page, (pymupdf.PDF_ANNOT_CIRCLE,)):
            if not is_marker(doc, a.xref):
                continue
            m = annotations.read(a)
            if m and m["kind"] == "m_count" and (groups is None or group_of(m) in groups):
                out.append((i, a.xref, m))
        del page
    return out


def groups(doc):
    """The document's count groups, in the order they first appear."""
    return summary(doc)[0]


def last_numbers(doc):
    """{group: its highest number} in the document."""
    return summary(doc)[1]


def summary(doc):
    """(the groups in the order they first appear, {group: its highest number}), from one
    reading of the markers."""
    seen, last = [], {}
    for _i, _x, m in markers(doc):
        g = group_of(m)
        if g not in last:
            seen.append(g)
        last[g] = max(last.get(g, 0), m.get("n", 0))
    return seen, last


def next_group_name(doc, taken=()):
    """The first "Count N" no marker uses yet (nor any name in taken)."""
    used = set(groups(doc)) | set(taken)
    k = 1
    while tr("Count {n}").format(n=k) in used or "Count %d" % k in used:
        k += 1
    return tr("Count {n}").format(n=k)


def keeps_order(models):
    """True when the group keeps its numbers in order: none of its markers switched it off."""
    return all(m["props"].get("order", True) for m in models)


def renumbered(found, skip=()):
    """{page index: [(xref, model)]}: the markers in found ([(page, xref, model)], one or
    more groups) numbered 1, 2, 3... again in each group, in the order of their numbers
    (then page, then place on the page), leaving out the xrefs in skip (being deleted).
    Only markers whose number changes are listed."""
    by_group = {}
    for i, x, m in found:
        if (i, x) in skip:
            continue
        by_group.setdefault(group_of(m), []).append((i, x, m))
    out = {}
    for items in by_group.values():
        items.sort(key=lambda t: (t[2].get("n", 0), t[0], t[2]["points"][0].y,
                                  t[2]["points"][0].x))
        for k, (i, x, m) in enumerate(items, 1):
            if m.get("n") != k:
                m = annotations.copy(m)
                m["n"] = k
                out.setdefault(i, []).append((x, m))
    return out
