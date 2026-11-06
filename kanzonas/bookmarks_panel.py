"""Bookmarks (the PDF outline): view, jump, add, rename, delete, reorder, indent/outdent, sort,
expand/collapse, a bookmark at the current view, its destination set to the current view,
and bold, italic and color (the outline item's /F and /C).

The panel keeps each bookmark whole ([level, title, page, destination dict], as
Document.get_toc(simple=False) gives them), so editing one bookmark keeps every other
bookmark's place on its page, zoom and style."""

import re

import pymupdf
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTreeWidget, QTreeWidgetItem,
                               QToolButton, QInputDialog, QLabel, QMenu, QColorDialog)

from .i18n import tr


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
    for e in toc:
        lvl = max(1, min(int(e[0]), prev + 1))
        out.append([lvl] + list(e[1:]))
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


def dest_of(e):
    """A copy of bookmark e's destination dict ({} for a [level, title, page] entry)."""
    d = e[3] if len(e) > 3 and isinstance(e[3], dict) else {}
    d = dict(d)
    d.pop("xref", None)                 # (set_toc gives every bookmark a new object)
    return d


def _natural(text):
    """Sort key putting A-2 before A-10 and 'Section 9' before 'Section 10'."""
    return tuple((0, int(p), "") if p.isdigit() else (1, 0, p.lower())
                 for p in re.split(r"(\d+)", text) if p)


def sort_toc(toc, by="page"):
    """The bookmarks with every bookmark's children in order (by="page": by page, then
    by place on the page; by="name": by title, numbers in number order). A bookmark's
    children move with it."""
    root, stack = [], [(0, None)]
    for e in toc:
        node = [list(e), []]
        while stack[-1][0] >= e[0]:
            stack.pop()
        (stack[-1][1] if stack[-1][1] is not None else root).append(node)
        stack.append((e[0], node[1]))

    def key(node):
        e = node[0]
        if by == "name":
            return _natural(e[1])
        to = dest_of(e).get("to")
        return (e[2] if e[2] > 0 else 10 ** 9, to.y if to is not None else 0.0)
    out = []

    def walk(nodes):
        for n in sorted(nodes, key=key):
            out.append(n[0])
            walk(n[1])
    walk(root)
    return out


class BookmarksPanel(QWidget):
    jump = Signal(int)                 # 0-based page
    jump_to = Signal(int, object)      # 0-based page, point on it (unrotated)
    changed = Signal(list)             # new toc

    def __init__(self):
        super().__init__()
        self.toc = []
        self.current_page = lambda: 0
        # (page index, point (unrotated), suggested title) of what the window shows, or None
        self.current_view = lambda: None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(2, 2, 2, 2)
        bar = QHBoxLayout()
        for text, tip, fn in (("+", tr("Add a bookmark to the current page"), self._add),
                              (tr("Rename"), tr("Rename"), self._rename),
                              ("✕", tr("Delete"), self._delete),
                              ("↑", tr("Move up"), lambda: self._move(-1)),
                              ("↓", tr("Move down"), lambda: self._move(1)),
                              ("→", tr("Indent (make child)"), lambda: self._shift(1)),
                              ("←", tr("Outdent"), lambda: self._shift(-1))):
            b = QToolButton()
            b.setText(text)
            b.setToolTip(tip)
            b.clicked.connect(fn)
            bar.addWidget(b)
        self.more = QToolButton()
        self.more.setText("⋯")
        self.more.setToolTip(tr("More bookmark tools: make bookmarks from headings, a table "
                                "of contents, sort, style..."))
        self.more.setPopupMode(QToolButton.InstantPopup)
        self.menu = QMenu(self.more)
        self.more.setMenu(self.menu)
        bar.addWidget(self.more)
        bar.addStretch(1)
        lay.addLayout(bar)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.itemClicked.connect(self._clicked)
        self.tree.itemDoubleClicked.connect(lambda *_: self._rename())
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(
            lambda pos: self.menu.exec(self.tree.viewport().mapToGlobal(pos)))
        lay.addWidget(self.tree)
        self.empty = QLabel(tr("No bookmarks. Click + to add one for the current page, or "
                               "⋯ to make them from the headings."))
        self.empty.setWordWrap(True)
        self.empty.setStyleSheet("color: gray;")
        lay.addWidget(self.empty)

    def set_menu_actions(self, actions):
        """The commands of the ⋯ button and the right-click menu (None: a separator)."""
        self.menu.clear()
        for a in actions:
            if a is None:
                self.menu.addSeparator()
            else:
                self.menu.addAction(a)

    def set_toc(self, toc, select=None):
        self.toc = [[int(e[0]), str(e[1]), int(e[2])] + ([dict(e[3])] if len(e) > 3 and
                                                          isinstance(e[3], dict) else [])
                    for e in toc]
        self.tree.clear()
        parents = {0: self.tree.invisibleRootItem()}
        sel = None
        for i, e in enumerate(self.toc):
            lvl, title, page = e[:3]
            parent = parents.get(lvl - 1, self.tree.invisibleRootItem())
            it = QTreeWidgetItem(parent, [title + "   " + tr("(p. {page})").format(page=page)
                                     if page > 0 else title])
            it.setData(0, Qt.UserRole, i)
            d = dest_of(e)
            if d.get("bold") or d.get("italic"):
                f = it.font(0)
                f.setBold(bool(d.get("bold")))
                f.setItalic(bool(d.get("italic")))
                it.setFont(0, f)
            color = d.get("color")
            if color and len(color) == 3:
                it.setForeground(0, QBrush(QColor.fromRgbF(*[max(0.0, min(1.0, c))
                                                             for c in color])))
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
        e = self.toc[it.data(0, Qt.UserRole)]
        page = e[2]
        if page <= 0:
            return
        d = dest_of(e)
        if d.get("to") is not None and d.get("kind", pymupdf.LINK_GOTO) == pymupdf.LINK_GOTO:
            self.jump_to.emit(page - 1, pymupdf.Point(d["to"]))
        else:
            self.jump.emit(page - 1)

    def _commit(self, toc, select=None):
        toc = _normalize(toc)
        self.set_toc(toc, select)
        self.changed.emit(toc)

    def _copy(self):
        return [list(e[:3]) + ([dest_of(e)] if len(e) > 3 else []) for e in self.toc]

    def _insert(self, entry):
        toc = self._copy()
        i = self._index()
        if i is None:
            toc.append(entry)
            sel = len(toc) - 1
        else:                             # after the selected item, same level
            end = _subtree_end(toc, i)
            entry[0] = toc[i][0]
            toc.insert(end, entry)
            sel = end
        self._commit(toc, sel)

    def _add(self):
        page = self.current_page() + 1
        title, ok = QInputDialog.getText(self, tr("Add bookmark"),
                                         tr("Bookmark for page {page}:").format(page=page),
                                         text=tr("Page {page}").format(page=page))
        if not ok or not title.strip():
            return
        self._insert([1, title.strip(), page])

    def add_at_view(self, ask=True):
        """A bookmark to the place the window shows (the selected text's place and words,
        when text is selected), after the selected bookmark. Returns True when added."""
        here = self.current_view()
        if here is None:
            return False
        index, to, suggested = here
        page = index + 1
        title = (suggested or "").strip() or tr("Page {page}").format(page=page)
        if ask:
            title, ok = QInputDialog.getText(self, tr("Add bookmark"),
                                             tr("Bookmark for page {page}:").format(page=page),
                                             text=title)
            if not ok or not title.strip():
                return False
        self._insert([1, title.strip(), page,
                      {"kind": pymupdf.LINK_GOTO, "page": index, "to": pymupdf.Point(to),
                       "zoom": 0}])
        return True

    def set_destination(self):
        """The selected bookmark goes to the place the window shows now."""
        i = self._index()
        here = self.current_view()
        if i is None or here is None:
            return False
        index, to, _title = here
        toc = self._copy()
        d = dest_of(toc[i])
        for k in ("uri", "file", "name", "nameddest"):
            d.pop(k, None)
        d.update(kind=pymupdf.LINK_GOTO, page=index, to=pymupdf.Point(to), zoom=0)
        toc[i] = [toc[i][0], toc[i][1], index + 1, d]
        self._commit(toc, i)
        return True

    def _rename(self):
        i = self._index()
        if i is None:
            return
        title, ok = QInputDialog.getText(self, tr("Rename bookmark"), tr("Name:"),
                                         text=self.toc[i][1])
        if ok and title.strip():
            toc = self._copy()
            toc[i][1] = title.strip()
            self._commit(toc, i)

    def _delete(self):
        i = self._index()
        if i is None:
            return
        toc = self._copy()
        del toc[i:_subtree_end(toc, i)]
        self._commit(toc)

    def _move(self, d):
        i = self._index()
        if i is None:
            return
        toc = self._copy()
        j = move(toc, i, d)
        if j != i:
            self._commit(toc, j)

    def _shift(self, d):
        i = self._index()
        if i is None:
            return
        toc = self._copy()
        before = [e[0] for e in toc]
        shift(toc, i, d)
        if [e[0] for e in toc] != before:
            self._commit(toc, i)

    def sort(self, by="page"):
        """Sort the bookmarks (see sort_toc); True when the order changed."""
        if not self.toc:
            return False
        toc = sort_toc(self._copy(), by)
        if [e[:3] for e in toc] == [e[:3] for e in self.toc]:
            return False
        self._commit(toc)
        return True

    def expand_all(self):
        self.tree.expandAll()

    def collapse_all(self):
        self.tree.collapseAll()

    def _restyle(self, change):
        i = self._index()
        if i is None:
            return False
        toc = self._copy()
        e = toc[i]
        d = dest_of(e) if len(e) > 3 else {"kind": pymupdf.LINK_GOTO if e[2] > 0
                                           else pymupdf.LINK_NONE, "page": e[2] - 1}
        change(d)
        toc[i] = e[:3] + [d]
        self._commit(toc, i)
        return True

    def toggle_style(self, key):
        """Bold or italic (key) on or off for the selected bookmark."""
        return self._restyle(lambda d: d.update({key: not d.get(key)}))

    def set_color(self, rgb):
        """The selected bookmark's color ((r, g, b) 0..1; None: the default black)."""
        def change(d):
            if rgb is None:
                d.pop("color", None)
            else:
                d["color"] = tuple(float(c) for c in rgb)
        return self._restyle(change)

    def pick_color(self):
        i = self._index()
        if i is None:
            return
        old = dest_of(self.toc[i]).get("color")
        start = QColor.fromRgbF(*old) if old and len(old) == 3 else QColor(Qt.black)
        c = QColorDialog.getColor(start, self, tr("Bookmark color"))
        if c.isValid():
            self.set_color((c.redF(), c.greenF(), c.blueF()))
