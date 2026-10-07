"""Bookmarks (the PDF outline): view, jump, add, rename, delete, reorder, indent/outdent."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTreeWidget, QTreeWidgetItem,
                               QToolButton, QInputDialog, QLabel)


def _subtree_end(toc, i):
    """Index just past item i and all of its children."""
    lvl = toc[i][0]
    j = i + 1
    while j < len(toc) and toc[j][0] > lvl:
        j += 1
    return j


def _normalize(toc):
    """Keep levels valid: first item level 1, never jump more than one level deeper."""
    out, prev = [], 0
    for lvl, title, page in toc:
        lvl = max(1, min(lvl, prev + 1))
        out.append([lvl, title, page])
        prev = lvl
    return out


def move(toc, i, direction):
    """Move item i (with its children) past its previous/next sibling. Returns new index."""
    lvl = toc[i][0]
    end = _subtree_end(toc, i)
    block = toc[i:end]
    if direction < 0:
        j = i - 1
        while j >= 0 and toc[j][0] > lvl:
            j -= 1
        if j < 0 or toc[j][0] != lvl:
            return i
        toc[j:end] = block + toc[j:i]
        return j
    if end >= len(toc) or toc[end][0] != lvl:
        return i
    nend = _subtree_end(toc, end)
    toc[i:nend] = toc[end:nend] + block
    return i + (nend - end)


def shift(toc, i, delta):
    """Indent (+1) / outdent (-1) item i with its children."""
    end = _subtree_end(toc, i)
    if delta > 0 and (i == 0 or toc[i - 1][0] < toc[i][0]):
        return
    if delta < 0 and toc[i][0] == 1:
        return
    for k in range(i, end):
        toc[k][0] += delta


class BookmarksPanel(QWidget):
    jump = Signal(int)                 # 0-based page
    changed = Signal(list)             # new toc

    def __init__(self):
        super().__init__()
        self.toc = []
        self.current_page = lambda: 0
        lay = QVBoxLayout(self)
        lay.setContentsMargins(2, 2, 2, 2)
        bar = QHBoxLayout()
        for text, tip, fn in (("+", "Add a bookmark to the current page", self._add),
                              ("Rename", "Rename", self._rename), ("✕", "Delete", self._delete),
                              ("↑", "Move up", lambda: self._move(-1)),
                              ("↓", "Move down", lambda: self._move(1)),
                              ("→", "Indent (make child)", lambda: self._shift(1)),
                              ("←", "Outdent", lambda: self._shift(-1))):
            b = QToolButton()
            b.setText(text)
            b.setToolTip(tip)
            b.clicked.connect(fn)
            bar.addWidget(b)
        bar.addStretch(1)
        lay.addLayout(bar)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.itemClicked.connect(self._clicked)
        self.tree.itemDoubleClicked.connect(lambda *_: self._rename())
        lay.addWidget(self.tree)
        self.empty = QLabel("No bookmarks. Click + to add one for the current page.")
        self.empty.setWordWrap(True)
        self.empty.setStyleSheet("color: gray;")
        lay.addWidget(self.empty)

    def set_toc(self, toc, select=None):
        self.toc = [[int(e[0]), str(e[1]), int(e[2])] for e in toc]
        self.tree.clear()
        parents = {0: self.tree.invisibleRootItem()}
        sel = None
        for i, (lvl, title, page) in enumerate(self.toc):
            parent = parents.get(lvl - 1, self.tree.invisibleRootItem())
            it = QTreeWidgetItem(parent, [f"{title}   (p. {page})" if page > 0 else title])
            it.setData(0, Qt.UserRole, i)
            parents[lvl] = it
            if i == select:
                sel = it
        self.tree.expandAll()
        if sel is not None:
            self.tree.setCurrentItem(sel)
        self.empty.setVisible(not self.toc)

    def _index(self):
        it = self.tree.currentItem()
        return None if it is None else it.data(0, Qt.UserRole)

    def _clicked(self, it, _col):
        page = self.toc[it.data(0, Qt.UserRole)][2]
        if page > 0:
            self.jump.emit(page - 1)

    def _commit(self, toc, select=None):
        toc = _normalize(toc)
        self.set_toc(toc, select)
        self.changed.emit(toc)

    def _add(self):
        page = self.current_page() + 1
        title, ok = QInputDialog.getText(self, "Add bookmark", f"Bookmark for page {page}:",
                                         text=f"Page {page}")
        if not ok or not title.strip():
            return
        toc = [list(e) for e in self.toc]
        i = self._index()
        if i is None:
            toc.append([1, title.strip(), page])
            sel = len(toc) - 1
        else:                             # after the selected item, same level
            end = _subtree_end(toc, i)
            toc.insert(end, [toc[i][0], title.strip(), page])
            sel = end
        self._commit(toc, sel)

    def _rename(self):
        i = self._index()
        if i is None:
            return
        title, ok = QInputDialog.getText(self, "Rename bookmark", "Name:", text=self.toc[i][1])
        if ok and title.strip():
            toc = [list(e) for e in self.toc]
            toc[i][1] = title.strip()
            self._commit(toc, i)

    def _delete(self):
        i = self._index()
        if i is None:
            return
        toc = [list(e) for e in self.toc]
        del toc[i:_subtree_end(toc, i)]
        self._commit(toc)

    def _move(self, d):
        i = self._index()
        if i is None:
            return
        toc = [list(e) for e in self.toc]
        j = move(toc, i, d)
        if j != i:
            self._commit(toc, j)

    def _shift(self, d):
        i = self._index()
        if i is None:
            return
        toc = [list(e) for e in self.toc]
        before = [e[0] for e in toc]
        shift(toc, i, d)
        if [e[0] for e in toc] != before:
            self._commit(toc, i)
