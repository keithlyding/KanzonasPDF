"""Markups list: every annotation in the document in one sortable, filterable table.
Click a row to jump to it and select it. Export the list to CSV (opens in Excel)."""

import csv
import os

import pymupdf
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QBrush
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTableWidget,
                               QTableWidgetItem, QComboBox, QLineEdit, QPushButton, QLabel,
                               QHeaderView, QAbstractItemView, QFileDialog,
                               QMessageBox)

from . import annotations as A
from .i18n import tr

COLUMNS = [tr("Page"), tr("Type"), tr("Comment / text"), tr("Author"), tr("Date"), tr("Color")]
ALL_TYPES = tr("All types")
_SKIP = (pymupdf.PDF_ANNOT_POPUP, pymupdf.PDF_ANNOT_WIDGET, pymupdf.PDF_ANNOT_LINK)


def _date(pdf_date):
    """'D:20261007131500...' -> '2026-10-07 13:15'."""
    d = (pdf_date or "").replace("D:", "")
    if len(d) >= 12 and d[:12].isdigit():
        return f"{d[0:4]}-{d[4:6]}-{d[6:8]} {d[8:10]}:{d[10:12]}"
    return d


def _row(a):
    """(type label, text, author, date, color hex) of an annotation for the list."""
    model = A.read(a)
    label = A.LABELS.get(model["kind"], a.type[1]) if model else a.type[1]
    if model and model["kind"] == "comment":
        style = model['props'].get('markup', 'highlight')
        label = tr("Comment ({style})").format(style=A.LABELS.get(style, style).lower())
    clouds = (a.border or {}).get("clouds", -1) or -1
    if (model and model["kind"] == "rect" and model["props"].get("cloud")) or \
            (a.type[0] == pymupdf.PDF_ANNOT_SQUARE and clouds > 0):
        label = A.LABELS["cloud"]
    info = a.info
    text = info.get("content", "") or ""
    color = (model["props"].get("stroke") if model else None) or \
        A.to_hex((a.colors or {}).get("stroke")) or ""
    return (label, text.replace("\r", " ").replace("\n", " "), info.get("title", ""),
            _date(info.get("modDate") or info.get("creationDate")), color)


def collect(doc, pages=None):
    """[(page index, xref, type label, text, author, date, color hex)] for the pages given
    (default: all).
    What was read is kept with the document, by markup, under the markup's dictionary as
    written in the file: a markup whose dictionary is unchanged isn't read again (reading
    5,000 markups takes seconds; checking them, a twentieth of a second). Everything the
    row shows (kind, text, author, dates, colors, cloud border) is in that dictionary."""
    known = getattr(doc, "_kz_markup_rows", None)
    if known is None or pages is None:
        known = {}          # (all pages read: markups no longer in the file are forgotten)
    old = getattr(doc, "_kz_markup_rows", None) or {}
    rows = []
    for i in (range(doc.page_count) if pages is None else sorted(pages)):
        if not 0 <= i < doc.page_count:
            continue
        page = doc[i]
        try:
            listed = [(x, doc.xref_object(x, compressed=True))
                      for x, typ, *_ in page.annot_xrefs() if typ not in _SKIP]
        except Exception:
            listed = None
        if listed is None or any(x <= 0 for x, _stamp in listed):
            # (a damaged list of markups: read them the plain way)
            rows += [(i, a.xref) + _row(a) for a in A.each_annot(page)
                     if a.type[0] not in _SKIP]
            continue
        fresh = {}
        todo = [x for x, stamp in listed if old.get(x, (None,))[0] != stamp]
        if todo:
            # (one walk of the page for all of them; the page stays alive while they're read)
            loaded = A.load_annots(page, todo)
            fresh = {x: _row(a) for x, a in loaded.items()}
            del loaded
        for xref, stamp in listed:
            row = fresh.get(xref)
            if row is None:
                if old.get(xref, (None,))[0] != stamp:
                    continue                # (not loaded: not a markup MuPDF shows)
                row = old[xref][1]
            known[xref] = (stamp, row)
            rows.append((i, xref) + row)
    doc._kz_markup_rows = known
    return rows


def carry_over(old, new):
    """new: the same document opened afresh (undo, redo): what was read from old is still
    good for every markup whose dictionary is unchanged (same object numbers)."""
    known = getattr(old, "_kz_markup_rows", None)
    if known and new is not old:
        new._kz_markup_rows = dict(known)


class _PageItem(QTableWidgetItem):
    """Sorts numerically."""

    def __lt__(self, other):
        return int(self.text()) < int(other.text())


class MarkupsPanel(QWidget):
    activated = Signal(int, int)        # page index, xref
    editRequested = Signal(int, int)    # change the comment's text
    deleteRequested = Signal(int, int)

    def __init__(self):
        super().__init__()
        self._rows = []
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        bar = QHBoxLayout()
        self.type_filter = QComboBox()
        self.type_filter.addItem(ALL_TYPES)
        self.text_filter = QLineEdit()
        self.text_filter.setPlaceholderText(tr("Filter by text or author"))
        self.text_filter.setClearButtonEnabled(True)
        self.count = QLabel()
        export = QPushButton(tr("Export CSV..."))
        export.clicked.connect(self.export_csv)
        bar.addWidget(QLabel(tr("Show:")))
        bar.addWidget(self.type_filter)
        bar.addWidget(self.text_filter, 1)
        bar.addWidget(self.count)
        bar.addWidget(export)
        lay.addLayout(bar)
        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().hide()
        hh = self.table.horizontalHeader()
        # first page first (Qt's own default order is descending) until a header is clicked
        hh.setSortIndicator(0, Qt.AscendingOrder)
        self.table.setSortingEnabled(True)
        hh.setSectionResizeMode(2, QHeaderView.Stretch)
        for c in (0, 1, 3, 4, 5):
            hh.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        self.table.cellClicked.connect(self._clicked)
        self.table.cellDoubleClicked.connect(lambda r, _c: self.editRequested.emit(*self._key(r)))
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._menu)
        self.table.installEventFilter(self)
        lay.addWidget(self.table)
        self.type_filter.currentIndexChanged.connect(self._apply_filter)
        self.text_filter.textChanged.connect(self._apply_filter)

    def refresh(self, doc, pages=None):
        """Bring the list up to date. pages: only these pages' markups changed since the last
        refresh of this same document (None: read them all). Only the rows whose markup
        changed are replaced; the others, their order and the selected row stay."""
        old = None
        if doc is None:
            self._doc, self._by_page = None, {}
        elif pages is None or doc is not getattr(self, "_doc", None):
            self._doc, self._by_page = doc, {}
            for row in collect(doc):
                self._by_page.setdefault(row[0], []).append(row)
        else:
            fresh = {}
            for row in collect(doc, pages):
                fresh.setdefault(row[0], []).append(row)
            old = {}
            for p in sorted(set(pages) | {p for p in self._by_page if p >= doc.page_count}):
                for r in self._by_page.pop(p, ()):
                    old[r[:2]] = r
            self._by_page.update(fresh)
            new = {r[:2]: r for rows in fresh.values() for r in rows}
        self._rows = [r for p in sorted(self._by_page) for r in self._by_page[p]]
        types = sorted({r[2] for r in self._rows})
        cur = self.type_filter.currentText()
        self.type_filter.blockSignals(True)
        self.type_filter.clear()
        self.type_filter.addItem(ALL_TYPES)
        self.type_filter.addItems(types)
        self.type_filter.setCurrentText(cur if cur in types else ALL_TYPES)
        self.type_filter.blockSignals(False)
        self.table.setSortingEnabled(False)
        # sizing columns to their contents on every setItem made filling quadratic (2,000
        # markups: 3 minutes): fill with fixed columns, then size them once
        hh = self.table.horizontalHeader()
        for c in (0, 1, 3, 4, 5):
            hh.setSectionResizeMode(c, QHeaderView.Interactive)
        self.table.setUpdatesEnabled(False)
        if old is None or not self._update_rows(old, new):
            self.table.setRowCount(len(self._rows))
            for r, row in enumerate(self._rows):
                self._set_row(r, row)
        self.table.setUpdatesEnabled(True)
        for c in (0, 1, 3, 4, 5):
            self.table.resizeColumnToContents(c)
        self.table.setSortingEnabled(True)
        self._apply_filter()

    def _set_row(self, r, row):
        page, xref, label, text, author, date, color = row
        cells = [_PageItem(str(page + 1)), QTableWidgetItem(label), QTableWidgetItem(text),
                 QTableWidgetItem(author), QTableWidgetItem(date), QTableWidgetItem(color)]
        cells[0].setData(Qt.UserRole, (page, xref))
        cells[2].setToolTip(text)
        if color:
            cells[5].setBackground(QBrush(QColor(color)))
            cells[5].setForeground(QBrush(QColor("white") if QColor(color).lightness() < 128
                                          else QColor("black")))
        for c, it in enumerate(cells):
            self.table.setItem(r, c, it)

    def _update_rows(self, old, new):
        """Replace, remove and add only the rows that changed (old, new: {(page, xref): row}
        for the pages read again, in page order). False when the table must be filled again
        to come out as a fill would: many changes, a list not sorted by page (rows that tie
        in another column are in page order after a fill), or markups put in a new order."""
        gone = [k for k in old if k not in new]
        changed = [k for k, r in new.items() if k in old and old[k] != r]
        added = [r for k, r in new.items() if k not in old]
        if not (gone or changed or added):
            return True
        hh = self.table.horizontalHeader()
        if len(gone) + len(changed) + len(added) > max(200, len(self._rows) // 4) or \
                self.table.rowCount() != len(self._rows) - len(added) + len(gone) or \
                hh.sortIndicatorSection() != 0 or hh.sortIndicatorOrder() != Qt.AscendingOrder:
            return False
        # on each page: the markups that stay keep their order, new ones come after them
        # (as a fill would list them: sorted by page, then in the page's order)
        stay = [k for k in new if k in old]
        if stay != [k for k in old if k in new]:
            return False
        last = {}
        for k in new:
            if k in old and last.get(k[0]) == "added":
                return False
            last[k[0]] = "stay" if k in old else "added"
        at = {}
        for r in range(self.table.rowCount()):
            it = self.table.item(r, 0)
            key = it.data(Qt.UserRole) if it is not None else None
            if key is not None and tuple(key) in old:
                at[tuple(key)] = r
        if len(at) != len(old):
            return False                # (the table doesn't hold what it should: refill)
        for k in changed:
            self._set_row(at[k], new[k])
        for r in sorted((at[k] for k in gone), reverse=True):
            self.table.removeRow(r)
        n = self.table.rowCount()
        self.table.setRowCount(n + len(added))
        for r, row in enumerate(added, n):
            self._set_row(r, row)
        return True

    def _apply_filter(self, *_):
        t = self.type_filter.currentText()
        q = self.text_filter.text().strip().lower()
        shown = 0
        for r in range(self.table.rowCount()):
            label = self.table.item(r, 1).text()
            hay = (self.table.item(r, 2).text() + " " + self.table.item(r, 3).text()).lower()
            hide = (t != ALL_TYPES and label != t) or (q and q not in hay)
            self.table.setRowHidden(r, bool(hide))
            shown += 0 if hide else 1
        self.count.setText(tr("{shown} of {total}").format(shown=shown, total=self.table.rowCount()))

    def _key(self, row):
        return self.table.item(row, 0).data(Qt.UserRole)

    def _clicked(self, row, _col):
        self.activated.emit(*self._key(row))

    def _menu(self, pos):
        from PySide6.QtWidgets import QMenu
        row = self.table.rowAt(pos.y())
        if row < 0:
            return
        self.table.selectRow(row)
        key = self._key(row)
        self.activated.emit(*key)
        menu = QMenu(self)
        if self._editable(*key):
            menu.addAction(tr("Edit text..."), lambda: self.editRequested.emit(*key))
        menu.addAction(tr("Delete") + "\tDel", lambda: self.deleteRequested.emit(*key))
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _editable(self, index, xref):
        """Edit text... can change this markup's text (not a measurement's or a stamp's)."""
        try:
            page = self._doc[index]            # keep the page alive while using its annot
            model = A.read(page.load_annot(xref))
        except Exception:
            return False
        return model is not None and A.text_editable(model)

    def eventFilter(self, obj, e):
        from PySide6.QtCore import QEvent
        if obj is self.table and e.type() == QEvent.KeyPress and \
                e.key() in (Qt.Key_Delete, Qt.Key_Backspace) and self.table.currentRow() >= 0:
            self.deleteRequested.emit(*self._key(self.table.currentRow()))
            return True
        return super().eventFilter(obj, e)

    def export_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, tr("Export markups"), "markups.csv",
                                              tr("CSV files") + " (*.csv)")
        if not path:
            return
        from .export import csv_cell
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f)
                w.writerow(COLUMNS)
                for r in range(self.table.rowCount()):
                    if not self.table.isRowHidden(r):
                        # (comment text comes from the PDF: never a live spreadsheet formula)
                        w.writerow([csv_cell(self.table.item(r, c).text())
                                    for c in range(len(COLUMNS))])
        except OSError as ex:           # (open in Excel, read-only, a folder...)
            QMessageBox.warning(self, tr("Export markups"), tr(
                "Couldn't save {name}:\n{error}").format(name=os.path.basename(path),
                                                         error=ex.strerror or ex))
