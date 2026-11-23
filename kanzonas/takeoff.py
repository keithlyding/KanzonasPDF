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

from . import annotations as A
from . import measure as M
from . import spaces
from .i18n import tr


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
    Polylength with a height has a second row after it, its wall area (kind "wall")."""
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
            row = {"page": i, "sheet": name, "space": where.get(x, ""),
                   "kind": m["kind"], "type": A.LABELS[m["kind"]],
                   "group": (m["props"].get("group") or "") if m["kind"] == "m_count"
                   else "", "subject": m.get("subject") or "", "value": value, "unit": unit}
            out.append(row)
            wall = M.wall_area(m["kind"], m["points"], page, m["props"])
            if wall is not None:
                # (a Length or Polylength with a height: its wall area as a row of its own)
                out.append(dict(row, kind="wall", type=tr("Wall area"), value=wall[0],
                                unit=wall[1]))
    return out


def summary(rows):
    """[(type, group, pages, items, total, unit)] of rows (items()) per kind, Count group and
    unit, as the Measurement summary lists them."""
    groups = {}
    for r in rows:
        g = groups.setdefault((r["type"], r["group"], r["unit"]),
                              {"count": 0, "total": 0.0, "pages": set()})
        g["count"] += 1
        g["total"] += r["value"]
        g["pages"].add(r["page"] + 1)
    out = []
    for (label, group, unit), g in sorted(groups.items()):
        pages = ", ".join(str(p) for p in sorted(g["pages"]))
        total = g["count"] if unit == "count" else round(g["total"], 2)
        out.append((label, group, pages, g["count"], total, _unit_name(unit)))
    return out


# ---- the workbook ---------------------------------------------------------------------
def _cols():
    return [tr("Type"), tr("Group"), tr("Items"), tr("Quantity"), tr("Unit")]


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
    put(ws, [tr("Type"), tr("Group"), tr("Pages"), tr("Items"), tr("Total"), tr("Unit")],
        bold, band)
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
                put(ws, ["", typ, group, len(rs), total, _unit_name(unit)])
            last = ws.max_row
            # (a subtotal of each unit: a sum across units would mean nothing)
            for unit in sorted({_key(r)[2] for r in mine}):
                put(ws, ["", tr("Subtotal"), "", "", '=SUBTOTAL(9,%s)' % _range_if(
                    first, last, unit, ws), _unit_name(unit)], bold, number_cols=(4,))
        put(ws, [])
        put(ws, [tr("Total")] + [""] * 5, bold, band)
        per = {}
        for r in rows:
            per.setdefault(_key(r), []).append(r)
        for (typ, group, unit), rs in sorted(per.items()):
            total = len(rs) if unit == "count" else round(sum(r["value"] for r in rs), 4)
            put(ws, ["", typ, group, len(rs), total, _unit_name(unit)], bold)
        return ws

    grouped(tr("By sheet"), lambda r: r["sheet"], tr("Sheet"))
    grouped(tr("By space"), lambda r: r["space"], tr("Space"))

    # Items
    ws = wb.create_sheet(tr("Items")[:31])
    put(ws, [tr("Sheet"), tr("Space"), tr("Type"), tr("Group"), tr("Subject"), tr("Quantity"),
             tr("Unit")], bold, band)
    for r in rows:
        put(ws, [r["sheet"], r["space"], r["type"], r["group"], r["subject"],
                 1 if r["unit"] == "count" else round(r["value"], 4),
                 _unit_name(r["unit"])])
    ws.auto_filter.ref = "A1:G%d" % max(1, ws.max_row)
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
