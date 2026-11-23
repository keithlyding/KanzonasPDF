"""The takeoff: every measurement of a document as a row (its sheet, the Space it's in, its
kind, its Count group or subject, its quantity and unit), and the Excel workbook made from
them (Measurement summary > Export Excel...): grouped by sheet, by Space and by Count group or
kind, with quantities, units and subtotals, the start of a bill of quantities.

The owner, 23 Nov 2026 (takeoff and quantity surveying, the second of seven): "Export the
Measurement summary to .xlsx ... grouped by sheet, by Space and by Count group or measurement
kind, with quantities, units and subtotals. Keep the CSV export."

openpyxl is imported only when a workbook is written (it's heavy: AGENTS.md). Names written
into the workbook come from the PDF (Space names, Count groups, subjects, page labels): they're
always written as text, never as formulas, as export.to_excel does."""

import json
import math

import pymupdf

from . import annotations as A
from . import measure as M
from . import spaces
from .i18n import tr

# A document's takeoff settings, in its catalog (JSON): each Count group's quantities per
# counted item and its waste, {"groups": {name: {"items": [{"name", "qty", "unit"}],
# "waste": percent}}}. Read by every PDF program as an unknown key it leaves alone.
SETTINGS_KEY = "KZTakeoff"


def settings(doc):
    """The document's takeoff settings ({"groups": {...}}; empty when it has none)."""
    try:
        kind, val = doc.xref_get_key(doc.pdf_catalog(), SETTINGS_KEY)
        got = json.loads(val) if kind == "string" else {}
    except (ValueError, RuntimeError):
        got = {}                        # (unreadable: as if it had none)
    return got if isinstance(got, dict) else {}


def group_setup(doc, group, got=None):
    """(items, waste) of a Count group: [(name, quantity per counted item, unit)] and its
    waste or extra percent; ([], 0.0) when it has none."""
    g = ((got if got is not None else settings(doc)).get("groups") or {}).get(group) or {}
    items = []
    for it in g.get("items") or ():
        try:
            name, qty = str(it.get("name") or "").strip(), float(it.get("qty"))
        except (TypeError, ValueError, AttributeError):
            continue
        if name and math.isfinite(qty) and qty > 0:
            items.append((name, qty, str(it.get("unit") or "").strip()))
    return items, _percent(g.get("waste"))


def set_group_setup(doc, group, items, waste):
    """Give a Count group its quantities per counted item ([(name, qty, unit)]) and waste
    (percent), in the document's catalog (run it inside DocumentView.modify)."""
    got = settings(doc)
    groups = dict(got.get("groups") or {})
    entry = {"items": [{"name": n, "qty": float(q), "unit": u} for n, q, u in items],
             "waste": _percent(waste)}
    if entry["items"] or entry["waste"]:
        groups[group] = entry
    else:
        groups.pop(group, None)
    got["groups"] = groups
    doc.xref_set_key(doc.pdf_catalog(), SETTINGS_KEY, pymupdf.get_pdf_str(json.dumps(got)))


def _percent(v):
    try:
        v = float(v or 0.0)
    except (TypeError, ValueError):
        return 0.0
    return v if math.isfinite(v) and 0 <= v <= 1000 else 0.0


def _unit_name(unit):
    """A quantity's unit as shown ("count", "degrees" and "ft (radius)" are worded)."""
    if unit == "count":
        return tr("count")
    if unit == "degrees":
        return tr("degrees")
    if unit.endswith(" (radius)"):
        return tr("{unit} (radius)").format(unit=unit[:-len(" (radius)")])
    return unit


def sheet_name(page):
    """How a page is named in the takeoff: its page label (A-101) when it has one, with its
    number."""
    label = ""
    try:
        label = (page.get_label() or "").strip()
    except Exception:
        label = ""                      # (a broken page label tree: the number alone)
    n = tr("Page {n}").format(n=page.number + 1)
    return "%s (%s)" % (label, n) if label else n


def items(doc):
    """[{"page", "sheet", "space", "kind", "type", "group", "subject", "value", "unit"}] for
    every measurement of doc, page by page: "type" the kind's name, "group" a Count marker's
    group, "space" the Space its middle is in ("" for none), "value" its quantity in "unit"
    (an Area's or Volume's net of its cut-outs; 1 for a Count marker). A Length or
    Polylength with a height has a second row after it, its wall area (kind "wall"). "waste"
    is the percent to add (a measurement's own, a Count marker's group's), and a Count marker
    of a group with quantities per counted item has a row for each of them after it (kind
    "item": its name as the type, its group, the quantity per item and its unit)."""
    got = settings(doc)
    setups = {}
    out = []
    for i in range(doc.page_count):
        page = doc[i]
        found = []
        for a in A.each_annot(page):
            m = A.read(a)
            if m and m["kind"] in A.MEASURES:
                found.append((a.xref, m))
        if not found:
            continue
        where = spaces.of_markups(doc, page, [x for x, _m in found])
        name = sheet_name(page)
        for x, m in found:
            value, unit = M.raw_values(m["kind"], m["points"], page, m["props"], m.get("holes"))
            group = (m["props"].get("group") or "") if m["kind"] == "m_count" else ""
            if m["kind"] == "m_count":
                if group not in setups:
                    setups[group] = group_setup(doc, group, got)
                per, waste = setups[group]
            else:
                per, waste = (), _percent(m["props"].get("waste"))
            row = {"page": i, "sheet": name, "space": where.get(x, ""),
                   "kind": m["kind"], "type": A.LABELS[m["kind"]], "group": group,
                   "subject": m.get("subject") or "", "value": value, "unit": unit,
                   "waste": waste}
            out.append(row)
            for item, qty, item_unit in per:
                # (each counted item's own quantities: "each fixture = 2 boxes + 1 whip")
                out.append(dict(row, kind="item", type=item, value=qty,
                                unit=item_unit or "each"))
            wall = M.wall_area(m["kind"], m["points"], page, m["props"])
            if wall is not None:
                # (a Length or Polylength with a height: its wall area as a row of its own)
                out.append(dict(row, kind="wall", type=tr("Wall area"), value=wall[0],
                                unit=wall[1]))
    return out


def with_waste(r):
    """A row's quantity with its waste or extra percent added."""
    return (1 if r["unit"] == "count" else r["value"]) * (1 + r.get("waste", 0.0) / 100.0)


def summary(rows):
    """[(type, group, pages, items, total, unit, with waste)] of rows (items()) per kind,
    Count group and unit, as the Measurement summary lists them; "with waste" "" when none of
    them has any."""
    groups = {}
    for r in rows:
        g = groups.setdefault((r["type"], r["group"], r["unit"]),
                              {"count": 0, "total": 0.0, "pages": set(), "waste": 0.0,
                               "any": False})
        g["count"] += 1
        g["total"] += r["value"]
        g["waste"] += with_waste(r)
        g["any"] = g["any"] or bool(r.get("waste"))
        g["pages"].add(r["page"] + 1)
    out = []
    for (label, group, unit), g in sorted(groups.items()):
        pages = ", ".join(str(p) for p in sorted(g["pages"]))
        total = g["count"] if unit == "count" else round(g["total"], 2)
        out.append((label, group, pages, g["count"], total, _unit_name(unit),
                    round(g["waste"], 2) if g["any"] else ""))
    return out


# ---- the workbook ---------------------------------------------------------------------
def _cols():
    return [tr("Type"), tr("Group"), tr("Items"), tr("Quantity"), tr("Unit"), tr("With waste")]


def _waste_total(rs):
    """The rows' quantities with their waste added, or "" when none of them has any."""
    return round(sum(with_waste(r) for r in rs), 4) if any(r.get("waste") for r in rs) else ""


def _key(r):
    return (r["type"], r["group"], r["unit"])


def write_xlsx(doc, path, rows=None):
    """Write the takeoff of doc (rows: items(doc), when already read) to the Excel workbook
    path: Summary (as the Measurement summary), By sheet and By space (each group's rows by
    kind and Count group with their subtotals, and a total of each kind and unit), and Items
    (every measurement on a row, with filters, for a pivot table or a bill of quantities).
    Subtotals are SUBTOTAL formulas, worked out when Excel opens the file (so a quantity
    changed there changes them). Returns the number of rows written in Items (a measurement's
    wall area is a row of its own)."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import get_column_letter
    rows = items(doc) if rows is None else rows
    bold = Font(bold=True)
    band = PatternFill("solid", fgColor="DDE7F5")
    wb = Workbook()
    wb.calculation.fullCalcOnLoad = True

    def put(ws, values, font=None, fill=None, number_cols=()):
        ws.append(values)
        for k, cell in enumerate(ws[ws.max_row]):
            if isinstance(cell.value, str) and not (k in number_cols and
                                                     cell.value.startswith("=SUBTOTAL(")):
                cell.data_type = "s"        # (names from the PDF: text, never a formula)
            if font is not None:
                cell.font = font
            if fill is not None:
                cell.fill = fill
            if isinstance(cell.value, float):
                cell.number_format = "#,##0.00"

    # Summary
    ws = wb.active
    ws.title = tr("Summary")[:31]
    put(ws, [tr("Type"), tr("Group"), tr("Pages"), tr("Items"), tr("Total"), tr("Unit"),
             tr("With waste")], bold, band)
    for r in summary(rows):
        put(ws, list(r))

    def grouped(title, part, label):
        """A worksheet with rows grouped by part(r) (a sheet, a Space), each group's kinds
        and Count groups, its subtotals, and the whole document's totals at the end."""
        ws = wb.create_sheet(title[:31])
        put(ws, [label] + _cols(), bold, band)
        order = []
        for r in rows:
            if part(r) not in order:
                order.append(part(r))
        for p in order:
            put(ws, [p or tr("(no space)")], bold)
            mine = [r for r in rows if part(r) == p]
            first = ws.max_row + 1
            per = {}
            for r in mine:
                per.setdefault(_key(r), []).append(r)
            for (typ, group, unit), rs in sorted(per.items()):
                total = len(rs) if unit == "count" else round(sum(r["value"] for r in rs), 4)
                put(ws, ["", typ, group, len(rs), total, _unit_name(unit), _waste_total(rs)])
            last = ws.max_row
            # (a subtotal of each unit: a sum across units would mean nothing)
            for unit in sorted({_key(r)[2] for r in mine}):
                put(ws, ["", tr("Subtotal"), "", "", '=SUBTOTAL(9,%s)' % _range_if(
                    first, last, unit, ws), _unit_name(unit)], bold, number_cols=(4,))
        put(ws, [])
        put(ws, [tr("Total")] + [""] * 6, bold, band)
        per = {}
        for r in rows:
            per.setdefault(_key(r), []).append(r)
        for (typ, group, unit), rs in sorted(per.items()):
            total = len(rs) if unit == "count" else round(sum(r["value"] for r in rs), 4)
            put(ws, ["", typ, group, len(rs), total, _unit_name(unit), _waste_total(rs)],
                bold)
        return ws

    grouped(tr("By sheet"), lambda r: r["sheet"], tr("Sheet"))
    grouped(tr("By space"), lambda r: r["space"], tr("Space"))

    # Items
    ws = wb.create_sheet(tr("Items")[:31])
    put(ws, [tr("Sheet"), tr("Space"), tr("Type"), tr("Group"), tr("Subject"), tr("Quantity"),
             tr("Unit"), tr("Waste %"), tr("With waste")], bold, band)
    for r in rows:
        put(ws, [r["sheet"], r["space"], r["type"], r["group"], r["subject"],
                 1 if r["unit"] == "count" else round(r["value"], 4),
                 _unit_name(r["unit"]), r.get("waste") or "",
                 round(with_waste(r), 4) if r.get("waste") else ""])
    ws.auto_filter.ref = "A1:I%d" % max(1, ws.max_row)
    ws.freeze_panes = "A2"

    for sheet in wb.worksheets:
        for col in sheet.columns:
            width = max((len(str(c.value)) for c in col
                         if c.value is not None and not str(c.value).startswith("=")),
                        default=8)
            sheet.column_dimensions[get_column_letter(col[0].column)].width = \
                min(50, max(10, width + 2))
    wb.save(path)
    return len(rows)


def _range_if(first, last, unit, ws):
    """The cells of column E between rows first and last whose unit (column F) is unit, as a
    SUBTOTAL range: the whole block when they all are, else each row's cell."""
    name = _unit_name(unit)
    rows = [k for k in range(first, last + 1) if ws.cell(row=k, column=6).value == name]
    if rows and rows == list(range(rows[0], rows[-1] + 1)):
        return "E%d:E%d" % (rows[0], rows[-1])
    return ",".join("E%d" % k for k in rows) or "E%d" % first
