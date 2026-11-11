"""Markups list: every annotation in the document in one sortable, filterable table.
Click a row to jump to it and select it. Export the list to CSV (opens in Excel).

Replies (review.py) are listed under the markup they answer, indented, in a thread that can
be folded (the Replies column), and a markup's review status is in the Status column, with a
filter. A thread's rows sort with their markup: each of a reply's cells sorts as its
markup's (the table sorts stably), so a thread stays together under its markup."""

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
from . import review
from .i18n import tr

COLUMNS = [tr("Page"), tr("Type"), tr("Comment / text"), tr("Author"), tr("Date"), tr("Color"),
           tr("Status"), tr("Replies"), tr("Layer"), tr("Space")]
ALL_TYPES = tr("All types")
ALL_LAYERS = tr("All layers")
ALL_SPACES = tr("All spaces")
ALL_STATUSES = tr("All statuses")
NO_STATUS = tr("No status")
SORT = Qt.UserRole + 1          # what a cell sorts by (a reply's: its markup's)
ROOT = Qt.UserRole + 2          # (Page column) the markup a reply belongs to; 0: none
DEPTH = Qt.UserRole + 3         # (Page column) 0: a markup, 1: a reply, 2: a reply to it...
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
    if model and model["kind"] == "polygon" and model["props"].get("space"):
        label = A.LABELS["space"]            # (spaces.py)
    info = a.info
    text = info.get("content", "") or ""
    color = (model["props"].get("stroke") if model else None) or \
        A.to_hex((a.colors or {}).get("stroke")) or ""
    return (label, text.replace("\r", " ").replace("\n", " "), info.get("title", ""),
            _date(info.get("modDate") or info.get("creationDate")), color)


def collect(doc, pages=None):
    """[(page index, xref, type label, text, author, date, color hex, status, root, depth,
    replies)] for the pages given (default: all): each markup, then the replies in its thread
    (root: the markup's xref, depth 1 and on; a markup's own row has root 0, depth 0 and its
    number of replies). Review statuses aren't rows: a markup's latest one is its status.
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
        rows += _threaded(review.Threads(page), _page_rows(doc, page, i, old, known))
    doc._kz_markup_rows = known
    # (1.12) the layer each markup is on (markup_layers.py), then the space it's in
    # (spaces.py), last; a reply's: none
    from . import markup_layers, spaces
    names = markup_layers.names(doc)
    if names:
        rows = [r + ("" if r[9] else names.get(markup_layers.layer_of(doc, r[1]), ""),)
                for r in rows]
    else:
        rows = [r + ("",) for r in rows]
    where = {}
    for i in sorted({r[0] for r in rows}):
        where.update(spaces.of_markups(doc, doc[i], [r[1] for r in rows
                                                     if r[0] == i and not r[9]]))
    return [r + ("" if r[9] else where.get(r[1], ""),) for r in rows]


def _threaded(threads, base):
    """A page's rows (page, xref, label, text, author, date, color) as the list shows them:
    each markup with its status, followed by its thread's replies."""
    by_xref = {r[1]: r for r in base}
    out = []
    for r in base:
        x = r[1]
        if threads.is_linked(x):
            continue
        state, _ln, marked = threads.status(x)
        replies = [(d, ln) for d, ln in threads.replies(x) if ln.xref in by_xref]
        out.append(tuple(r) + (review.status_label(state, marked), 0, 0, len(replies)))
        for d, ln in replies:
            rr = by_xref[ln.xref]
            out.append((rr[0], rr[1], tr("Reply"), rr[3], rr[4], rr[5], "", "", x, d, 0))
    return out


def _page_rows(doc, page, i, old, known):
    """The page's markups as (page, xref, label, text, author, date, color), each read only
    when its dictionary changed."""
    rows = []
    try:
        listed = [(x, doc.xref_object(x, compressed=True))
                  for x, typ, *_ in page.annot_xrefs() if typ not in _SKIP]
    except Exception:
        listed = None
    if listed is None or any(x <= 0 for x, _stamp in listed):
        # (a damaged list of markups: read them the plain way)
        return [(i, a.xref) + _row(a) for a in A.each_annot(page)
                if a.type[0] not in _SKIP]
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
    return rows


def carry_over(old, new):
    """new: the same document opened afresh (undo, redo): what was read from old is still
    good for every markup whose dictionary is unchanged (same object numbers)."""
    known = getattr(old, "_kz_markup_rows", None)
    if known and new is not old:
        new._kz_markup_rows = dict(known)


class _Item(QTableWidgetItem):
    """Sorts by its SORT value (a page number as a number; a reply's cells as its markup's,
    so that a thread sorts as one: the table's sort is stable)."""

    def __lt__(self, other):
        a, b = self.data(SORT), other.data(SORT)
        if a is None or b is None or type(a) is not type(b):
            return self.text() < other.text()
        return a < b


_PageItem = _Item           # (the name the Page column's cells had)


class MarkupsPanel(QWidget):
    activated = Signal(int, int)        # page index, xref
    editRequested = Signal(int, int)    # change the comment's text (a reply's: its own)
    deleteRequested = Signal(int, int)
    replyRequested = Signal(int, int)   # reply to a markup or a reply
    statusRequested = Signal(int, int, str)     # set a status (review.REVIEW / MARKED)
    exportRequested = Signal(object)    # export comments: {page: [xref]} or None (all)

    def __init__(self):
        super().__init__()
        self._rows = []
        self._collapsed = set()         # (page, xref) of markups whose thread is folded
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        bar = QHBoxLayout()
        self.type_filter = QComboBox()
        self.type_filter.addItem(ALL_TYPES)
        self.status_filter = QComboBox()
        self.status_filter.addItem(ALL_STATUSES, None)
        self.status_filter.addItem(NO_STATUS, "")
        for key in review.REVIEW[:-1] + review.MARKED:
            self.status_filter.addItem(review.STATE_LABELS[key], key)
        self.layer_filter = QComboBox()             # (1.12: markups on layers)
        self.layer_filter.addItem(ALL_LAYERS)
        self.layer_filter.setVisible(False)         # (shown when the document has layers)
        self.space_filter = QComboBox()             # (1.12: spaces)
        self.space_filter.addItem(ALL_SPACES)
        self.space_filter.setVisible(False)         # (shown when markups are in spaces)
        self.text_filter = QLineEdit()
        self.text_filter.setPlaceholderText(tr("Filter by text or author"))
        self.text_filter.setClearButtonEnabled(True)
        self.count = QLabel()
        export = QPushButton(tr("Export CSV..."))
        export.clicked.connect(self.export_csv)
        comments = QPushButton(tr("Export comments..."))
        comments.setToolTip(tr("The markups shown (with their replies and statuses) as an "
                               "XFDF or FDF file"))
        comments.clicked.connect(lambda: self.exportRequested.emit(self.shown_markups()))
        bar.addWidget(QLabel(tr("Show:")))
        bar.addWidget(self.type_filter)
        bar.addWidget(self.status_filter)
        bar.addWidget(self.layer_filter)
        bar.addWidget(self.space_filter)
        bar.addWidget(self.text_filter, 1)
        bar.addWidget(self.count)
        bar.addWidget(export)
        bar.addWidget(comments)
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
        # a header clicked (even back to Page): rows that tie keep that sort's order, not the
        # page's; the next refresh fills the table again (a fill lists them in page order)
        self._as_filled = False
        hh.sortIndicatorChanged.connect(lambda *_: setattr(self, "_as_filled", False))
        hh.setSectionResizeMode(2, QHeaderView.Stretch)
        for c in _SIZED:
            hh.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        self.table.cellClicked.connect(self._clicked)
        self.table.cellDoubleClicked.connect(self._double_clicked)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._menu)
        self.table.installEventFilter(self)
        lay.addWidget(self.table)
        self.type_filter.currentIndexChanged.connect(self._apply_filter)
        self.status_filter.currentIndexChanged.connect(self._apply_filter)
        self.layer_filter.currentIndexChanged.connect(self._apply_filter)
        self.space_filter.currentIndexChanged.connect(self._apply_filter)
        self.text_filter.textChanged.connect(self._apply_filter)

    def refresh(self, doc, pages=None):
        """Bring the list up to date. pages: only these pages' markups changed since the last
        refresh of this same document (None: read them all). Only the rows whose markup
        changed are replaced; the others, their order and the selected row stay."""
        old = None
        if doc is None:
            self._doc, self._by_page = None, {}
        elif pages is None or doc is not getattr(self, "_doc", None):
            if doc is not getattr(self, "_doc", None):
                self._collapsed = set()
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
        types = sorted({r[2] for r in self._rows if not r[9]})
        cur = self.type_filter.currentText()
        self.type_filter.blockSignals(True)
        self.type_filter.clear()
        self.type_filter.addItem(ALL_TYPES)
        self.type_filter.addItems(types)
        self.type_filter.setCurrentText(cur if cur in types else ALL_TYPES)
        self.type_filter.blockSignals(False)
        layers = sorted({r[11] for r in self._rows if not r[9] and r[11]})
        cur = self.layer_filter.currentText()
        self.layer_filter.blockSignals(True)
        self.layer_filter.clear()
        self.layer_filter.addItem(ALL_LAYERS)
        self.layer_filter.addItems(layers)
        self.layer_filter.setCurrentText(cur if cur in layers else ALL_LAYERS)
        self.layer_filter.setVisible(bool(layers))
        self.layer_filter.blockSignals(False)
        named = sorted({r[12] for r in self._rows if not r[9] and r[12]}, key=str.lower)
        cur = self.space_filter.currentText()
        self.space_filter.blockSignals(True)
        self.space_filter.clear()
        self.space_filter.addItem(ALL_SPACES)
        self.space_filter.addItems(named)
        self.space_filter.setCurrentText(cur if cur in named else ALL_SPACES)
        self.space_filter.setVisible(bool(named))
        self.space_filter.blockSignals(False)
        self.table.setSortingEnabled(False)
        # sizing columns to their contents on every setItem made filling quadratic (2,000
        # markups: 3 minutes): fill with fixed columns, then size them once
        hh = self.table.horizontalHeader()
        for c in _SIZED:
            hh.setSectionResizeMode(c, QHeaderView.Interactive)
        self.table.setUpdatesEnabled(False)
        self._parents = {(r[0], r[1]): r for r in self._rows if not r[9]}
        if old is None or not self._update_rows(old, new):
            self.table.setRowCount(len(self._rows))
            for r, row in enumerate(self._rows):
                self._set_row(r, row)
            self._as_filled = True
        self.table.setUpdatesEnabled(True)
        for c in _SIZED:
            self.table.resizeColumnToContents(c)
        self.table.setSortingEnabled(True)
        self._apply_filter()

    def _set_row(self, r, row):
        page, xref, label, text, author, date, color, status, root, depth, n, layer, space = row
        values = [page + 1, label, text, author, date, color, status, n, layer, space]
        cells = [_Item(str(page + 1)), _Item(label), _Item(text), _Item(author), _Item(date),
                 _Item(color), _Item(status), _Item(""), _Item(layer), _Item(space)]
        if depth:
            # a reply: indented under its markup, and sorted as its markup
            cells[1].setText("    " * (depth - 1) + "↳ " + label)
            cells[2].setText("    " * depth + text)
            parent = self._parents.get((page, root))
            if parent is not None:
                values = [parent[0] + 1, parent[2], parent[3], parent[4], parent[5],
                          parent[6], parent[7], parent[10], parent[11], parent[12]]
        elif n:
            folded = (page, xref) in self._collapsed
            cells[7].setText(("▸ " if folded else "▾ ") + str(n))
            cells[7].setToolTip(tr("Click to show or hide the replies"))
        for c, v in enumerate(values):
            cells[c].setData(SORT, v if c == 0 or c == 7 else str(v))
        cells[0].setData(Qt.UserRole, (page, xref))
        cells[0].setData(ROOT, root)
        cells[0].setData(DEPTH, depth)
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
        in another column are in page order after a fill), markups put in a new order, or a
        thread of replies changed (its rows go under its markup)."""
        gone = [k for k in old if k not in new]
        changed = [k for k, r in new.items() if k in old and old[k] != r]
        added = [r for k, r in new.items() if k not in old]
        if not (gone or changed or added):
            return True
        if any(r[9] or r[10] for r in [old[k] for k in gone + changed] +
               [new[k] for k in changed] + added):
            return False
        hh = self.table.horizontalHeader()
        if not self._as_filled or \
                len(gone) + len(changed) + len(added) > max(200, len(self._rows) // 4) or \
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
        want = self.status_filter.currentData()
        layer = self.layer_filter.currentText()
        space = self.space_filter.currentText()
        q = self.text_filter.text().strip().lower()
        replies_hay = {}
        if q:
            for row in self._rows:
                if row[9]:
                    replies_hay.setdefault((row[0], row[8]), []).append(
                        (row[3] + " " + row[4]).lower())
        shown = total = 0
        hidden_roots = set()
        rows = []
        for r in range(self.table.rowCount()):
            it = self.table.item(r, 0)
            page, xref = it.data(Qt.UserRole)
            depth = it.data(DEPTH) or 0
            if depth:
                rows.append((r, (page, it.data(ROOT))))
                continue
            row = self._parents.get((page, xref))
            label = row[2] if row is not None else self.table.item(r, 1).text()
            status = row[7] if row is not None else ""
            hay = (self.table.item(r, 2).text() + " " + self.table.item(r, 3).text()).lower()
            hide = (t != ALL_TYPES and label != t) or \
                (layer != ALL_LAYERS and (row[11] if row is not None else "") != layer) or \
                (space != ALL_SPACES and (row[12] if row is not None else "") != space) or \
                (q and q not in hay and not any(q in h for h in replies_hay.get(
                    (page, xref), ()))) or \
                (want is not None and not _status_matches(status, want))
            self.table.setRowHidden(r, bool(hide))
            if hide:
                hidden_roots.add((page, xref))
            total += 1
            shown += 0 if hide else 1
        for r, root in rows:
            self.table.setRowHidden(r, root in hidden_roots or root in self._collapsed)
        self.count.setText(tr("{shown} of {total}").format(shown=shown, total=total))

    def shown_markups(self):
        """{page: [xref]} of the markups the list shows (filtered), or None when it shows
        them all."""
        out, every = {}, True
        for r in range(self.table.rowCount()):
            it = self.table.item(r, 0)
            if it.data(DEPTH):
                continue
            if self.table.isRowHidden(r):
                every = False
                continue
            page, xref = it.data(Qt.UserRole)
            out.setdefault(page, []).append(xref)
        return None if every else out

    def _key(self, row):
        return self.table.item(row, 0).data(Qt.UserRole)

    def _is_reply(self, row):
        return bool(self.table.item(row, 0).data(DEPTH))

    def _clicked(self, row, col):
        if col == 7 and not self._is_reply(row):
            key = tuple(self._key(row))
            if self._parents.get(key, (0,) * 11)[10]:
                self.toggle_thread(key)
                return
        self.activated.emit(*self._key(row))

    def _double_clicked(self, row, col):
        if col == 7:
            return                      # (a click there folds the thread)
        self.editRequested.emit(*self._key(row))

    def toggle_thread(self, key, show=None):
        """Fold or unfold the replies under markup key (page, xref)."""
        key = tuple(key)
        folded = key in self._collapsed if show is None else show
        if folded:
            self._collapsed.discard(key)
        else:
            self._collapsed.add(key)
        for r in range(self.table.rowCount()):
            it = self.table.item(r, 0)
            if not it.data(DEPTH) and tuple(it.data(Qt.UserRole)) == key:
                n = self._parents[key][10]
                self.table.item(r, 7).setText(("▾ " if folded else "▸ ") + str(n))
                break
        self._apply_filter()

    def _menu(self, pos):
        from PySide6.QtWidgets import QMenu
        row = self.table.rowAt(pos.y())
        if row < 0:
            return
        self.table.selectRow(row)
        key = self._key(row)
        self.activated.emit(*key)
        menu = QMenu(self)
        if self._is_reply(row):
            menu.addAction(tr("Edit reply..."), lambda: self.editRequested.emit(*key))
            menu.addAction(tr("Reply..."), lambda: self.replyRequested.emit(*key))
            menu.addSeparator()
            menu.addAction(tr("Delete reply"), lambda: self.deleteRequested.emit(*key))
            menu.exec(self.table.viewport().mapToGlobal(pos))
            return
        if self._editable(*key):
            menu.addAction(tr("Edit text..."), lambda: self.editRequested.emit(*key))
        menu.addAction(tr("Reply..."), lambda: self.replyRequested.emit(*key))
        sub = menu.addMenu(tr("Set status"))
        status = (self._parents.get(tuple(key)) or (None,) * 11)[7] or ""
        from .review_ui import STATE_ACTIONS
        for k, label in STATE_ACTIONS:
            a = sub.addAction(label, lambda s=k: self.statusRequested.emit(key[0], key[1], s))
            a.setCheckable(True)
            a.setChecked(_status_matches(status, k if k != "None" else ""))
        sub.addSeparator()
        marked = status.startswith("✓")
        a = sub.addAction(tr("Marked"), lambda: self.statusRequested.emit(
            key[0], key[1], "Unmarked" if marked else "Marked"))
        a.setCheckable(True)
        a.setChecked(marked)
        n = (self._parents.get(tuple(key)) or (0,) * 11)[10]
        if n:
            menu.addAction(tr("Show or hide replies"), lambda: self.toggle_thread(key))
        menu.addSeparator()
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
                        w.writerow([csv_cell(self.table.item(r, c).text().strip())
                                    for c in range(len(COLUMNS))])
        except OSError as ex:           # (open in Excel, read-only, a folder...)
            QMessageBox.warning(self, tr("Export markups"), tr(
                "Couldn't save {name}:\n{error}").format(name=os.path.basename(path),
                                                         error=ex.strerror or ex))


_SIZED = (0, 1, 3, 4, 5, 6, 7, 8, 9)       # (columns sized to their contents)


def _status_matches(label, want):
    """The Status column's text label is status want ("": none; a review state or
    Marked / Unmarked)."""
    marked = label.startswith("✓")
    state = label.lstrip("✓ ").strip()
    if want == "Marked":
        return marked
    if want == "Unmarked":
        return not marked
    if want == "":
        return not state
    return state == review.STATE_LABELS.get(want, want)
