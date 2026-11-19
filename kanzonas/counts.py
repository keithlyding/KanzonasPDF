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


def summary(doc, found=None):
    """(the groups in the order they first appear, {group: its highest number}), from one
    reading of the markers (found: markers() already read)."""
    seen, last = [], {}
    for _i, _x, m in markers(doc) if found is None else found:
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


# New count's colors, one after the other (the Count tool's blue first): distinct on white
# and on a drawing's black lines
COLORS = ("#0050ff", "#e02020", "#109040", "#f07800", "#8040c0", "#0098a8", "#d0209c",
          "#8b5a2b")


def next_color(found, current=None):
    """A color for a new group: the first of COLORS no group of the document uses (nor
    current, the tool's color now); when all are used, the next after current."""
    used = {(m["props"].get("stroke") or "").lower() for _i, _x, m in found}
    if current:
        used.add(current.lower())
    for c in COLORS:
        if c not in used:
            return c
    k = COLORS.index(current.lower()) if current and current.lower() in COLORS else -1
    return COLORS[(k + 1) % len(COLORS)]


def look_of(found, group):
    """The color, text size and opacity of the group's highest-numbered marker ({} when the
    group has none): picking the group again gives the next ones that look."""
    mine = [m for _i, _x, m in found if group_of(m) == group]
    if not mine:
        return {}
    m = max(mine, key=lambda m: m.get("n", 0))
    return {k: m["props"][k] for k in ("stroke", "fontsize", "opacity") if k in m["props"]}


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


def problems(found, group):
    """(missing, repeated): the numbers from 1 to the group's highest that no marker has, and
    those more than one marker has. Gaps come from markers deleted with Keep the numbers in
    order off, in another PDF viewer, or before 1.15.9; repeats from numbers typed."""
    seen = {}
    for _i, _x, m in found:
        if group_of(m) == group:
            n = m.get("n", 0)
            seen[n] = seen.get(n, 0) + 1
    if not seen:
        return [], []
    missing = [n for n in range(1, max(seen) + 1) if n not in seen]
    return missing, sorted(n for n, k in seen.items() if k > 1)


def problem_text(group, missing, repeated, most=8):
    """The line Properties shows for a group whose numbers have gaps or repeats ("" when
    they don't)."""
    def listed(ns):
        out = ", ".join(str(n) for n in ns[:most])
        return out + (", ..." if len(ns) > most else "")
    parts = []
    if missing:
        parts.append(tr("missing: {numbers}").format(numbers=listed(missing)))
    if repeated:
        parts.append(tr("used more than once: {numbers}").format(numbers=listed(repeated)))
    if not parts:
        return ""
    return tr("{group} numbers {problems}").format(group=group, problems="; ".join(parts))
