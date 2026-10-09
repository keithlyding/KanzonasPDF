"""Markups list: every annotation in the document in one sortable, filterable table.
Click a row to jump to it and select it. Export the list to CSV (opens in Excel)."""

import csv

import pymupdf
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QBrush
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTableWidget,
                               QTableWidgetItem, QComboBox, QLineEdit, QPushButton, QLabel,
                               QHeaderView, QAbstractItemView, QFileDialog)

from . import annotations as A

COLUMNS = ["Page", "Type", "Comment / text", "Author", "Date", "Color"]
_SKIP = (pymupdf.PDF_ANNOT_POPUP, pymupdf.PDF_ANNOT_WIDGET, pymupdf.PDF_ANNOT_LINK)


def _date(pdf_date):
    """'D:20261007131500...' -> '2026-10-07 13:15'."""
    d = (pdf_date or "").replace("D:", "")
    if len(d) >= 12 and d[:12].isdigit():
        return f"{d[0:4]}-{d[4:6]}-{d[6:8]} {d[8:10]}:{d[10:12]}"
    return d


def collect(doc, pages=None):
    """[(page index, xref, type label, text, author, date, color hex)] for the pages given
    (default: all)."""
    rows = []
    for i in (range(doc.page_count) if pages is None else sorted(pages)):
        if not 0 <= i < doc.page_count:
            continue
        page = doc[i]
        for a in A.each_annot(page):
            if a.type[0] in _SKIP:
                continue
            model = A.read(a)
            label = A.LABELS.get(model["kind"], a.type[1]) if model else a.type[1]
            if model and model["kind"] == "comment":
                label = f"Comment ({model['props'].get('markup', 'highlight')})"
            clouds = (a.border or {}).get("clouds", -1) or -1
            if (model and model["kind"] == "rect" and model["props"].get("cloud")) or \
                    (a.type[0] == pymupdf.PDF_ANNOT_SQUARE and clouds > 0):
                label = "Cloud"
            info = a.info
            text = info.get("content", "") or ""
            color = (model["props"].get("stroke") if model else None) or \
                A.to_hex((a.colors or {}).get("stroke")) or ""
            rows.append((i, a.xref, label, text.replace("\r", " ").replace("\n", " "),
                         info.get("title", ""), _date(info.get("modDate") or info.get("creationDate")),
                         color))
    return rows


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
        self.type_filter.addItem("All types")
        self.text_filter = QLineEdit()
        self.text_filter.setPlaceholderText("Filter by text or author")
        self.text_filter.setClearButtonEnabled(True)
        self.count = QLabel()
        export = QPushButton("Export CSV...")
        export.clicked.connect(self.export_csv)
        bar.addWidget(QLabel("Show:"))
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
        self.table.setSortingEnabled(True)
        hh = self.table.horizontalHeader()
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
        """Rebuild the list. pages: only these pages' markups changed since the last refresh
        of this same document (None: read them all)."""
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
            for p in pages:
                self._by_page.pop(p, None)
            self._by_page.update(fresh)
            for p in [p for p in self._by_page if p >= doc.page_count]:
                del self._by_page[p]
        self._rows = [r for p in sorted(self._by_page) for r in self._by_page[p]]
        types = sorted({r[2] for r in self._rows})
        cur = self.type_filter.currentText()
        self.type_filter.blockSignals(True)
        self.type_filter.clear()
        self.type_filter.addItem("All types")
        self.type_filter.addItems(types)
        self.type_filter.setCurrentText(cur if cur in types else "All types")
        self.type_filter.blockSignals(False)
        self.table.setSortingEnabled(False)
        # sizing columns to their contents on every setItem made filling quadratic (2,000
        # markups: 3 minutes): fill with fixed columns, then size them once
        hh = self.table.horizontalHeader()
        for c in (0, 1, 3, 4, 5):
            hh.setSectionResizeMode(c, QHeaderView.Interactive)
        self.table.setUpdatesEnabled(False)
        self.table.setRowCount(len(self._rows))
        for r, (page, xref, label, text, author, date, color) in enumerate(self._rows):
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
        self.table.setUpdatesEnabled(True)
        for c in (0, 1, 3, 4, 5):
            self.table.resizeColumnToContents(c)
        self.table.setSortingEnabled(True)
        self._apply_filter()

    def _apply_filter(self, *_):
        t = self.type_filter.currentText()
        q = self.text_filter.text().strip().lower()
        shown = 0
        for r in range(self.table.rowCount()):
            label = self.table.item(r, 1).text()
            hay = (self.table.item(r, 2).text() + " " + self.table.item(r, 3).text()).lower()
            hide = (t != "All types" and label != t) or (q and q not in hay)
            self.table.setRowHidden(r, bool(hide))
            shown += 0 if hide else 1
        self.count.setText(f"{shown} of {self.table.rowCount()}")

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
        menu.addAction("Edit text...", lambda: self.editRequested.emit(*key))
        menu.addAction("Delete\tDel", lambda: self.deleteRequested.emit(*key))
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def eventFilter(self, obj, e):
        from PySide6.QtCore import QEvent
        if obj is self.table and e.type() == QEvent.KeyPress and \
                e.key() in (Qt.Key_Delete, Qt.Key_Backspace) and self.table.currentRow() >= 0:
            self.deleteRequested.emit(*self._key(self.table.currentRow()))
            return True
        return super().eventFilter(obj, e)

    def export_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export markups", "markups.csv",
                                              "CSV (*.csv)")
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(COLUMNS)
            for r in range(self.table.rowCount()):
                if not self.table.isRowHidden(r):
                    w.writerow([self.table.item(r, c).text() for c in range(len(COLUMNS))])
