"""Objects panel: the current page's markups from front to back. Select any of them, even when
it's completely covered by others; lock or hide them. The page's original PDF content is the
bottom row: it can't be split into separate objects."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
                               QAbstractItemView, QHeaderView, QLabel, QPushButton)

PAGE_ROW = "Page content (the original PDF: text, drawing, images)"


class ObjectsPanel(QWidget):
    selectRequested = Signal(list)          # xrefs, in click order
    flagsChanged = Signal(list, object, object)   # xrefs, locked (bool/None), hidden (bool/None)
    arrange = Signal(str)                   # front / forward / backward / back

    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(2, 2, 2, 2)
        self.title = QLabel()
        lay.addWidget(self.title)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Lock", "Show", "Object (top is in front)"])
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self._selected)
        self.table.itemChanged.connect(self._changed)
        lay.addWidget(self.table)
        row = QHBoxLayout()
        for key, text, tip in (("front", "Front", "Bring to front"), ("forward", "Up", "Bring forward"),
                               ("backward", "Down", "Send backward"), ("back", "Back", "Send to back")):
            b = QPushButton(text)
            b.setToolTip(tip)
            b.clicked.connect(lambda _=False, k=key: self.arrange.emit(k))
            row.addWidget(b)
        lay.addLayout(row)
        hint = QLabel("Click a row to select it, even if it's covered. Locked objects can't be "
                      "clicked or moved on the page.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: gray;")
        lay.addWidget(hint)
        self._xrefs = []
        self._loading = False
        self._order = []                    # rows in the order the user clicked them

    def refresh(self, view):
        self._loading = True
        self.table.clearContents()
        self._xrefs = []
        if view is None:
            self.table.setRowCount(0)
            self.title.setText("")
            self._loading = False
            return
        index = view.current_page()
        objs = view.page_objects(index)
        self.title.setText(f"Page {index + 1}: {len(objs)} markup(s)")
        self.table.setRowCount(len(objs) + 1)
        sel = set(view.selected_xrefs()) if view.selection and view.selection[0] == index else set()
        for r, (xref, label, locked, hidden) in enumerate(objs):
            lk = QTableWidgetItem()
            lk.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            lk.setCheckState(Qt.Checked if locked else Qt.Unchecked)
            vis = QTableWidgetItem()
            vis.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            vis.setCheckState(Qt.Unchecked if hidden else Qt.Checked)
            name = QTableWidgetItem(("\U0001F512 " if locked else "") + label)
            if locked or hidden:
                name.setForeground(Qt.gray)
            self.table.setItem(r, 0, lk)
            self.table.setItem(r, 1, vis)
            self.table.setItem(r, 2, name)
            self._xrefs.append(xref)
            if xref in sel:
                self.table.selectRow(r)
        last = len(objs)
        page_item = QTableWidgetItem(PAGE_ROW)
        page_item.setFlags(Qt.ItemIsEnabled)
        page_item.setForeground(Qt.gray)
        for c in (0, 1):
            blank = QTableWidgetItem("")
            blank.setFlags(Qt.ItemIsEnabled)
            self.table.setItem(last, c, blank)
        self.table.setItem(last, 2, page_item)
        self._loading = False

    def _selected(self):
        if self._loading:
            return
        rows = sorted({i.row() for i in self.table.selectedItems() if i.row() < len(self._xrefs)})
        # keep the order rows were picked in (the first one is the alignment reference)
        self._order = [r for r in self._order if r in rows] + [r for r in rows if r not in self._order]
        xrefs = [self._xrefs[r] for r in self._order]
        if xrefs:
            self.selectRequested.emit(xrefs)

    def _changed(self, item):
        if self._loading or item.row() >= len(self._xrefs):
            return
        xref = self._xrefs[item.row()]
        on = item.checkState() == Qt.Checked
        if item.column() == 0:
            self.flagsChanged.emit([xref], on, None)
        elif item.column() == 1:
            self.flagsChanged.emit([xref], None, not on)
