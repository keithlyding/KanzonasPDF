"""Command palette (Ctrl+Shift+P): type a few letters of what you want to do, pick the
command from the list, Enter runs it. Every menu command and tool is there, with its menu
and keyboard shortcut, so nothing has to be hunted for on the ribbon. Commands you used
from the palette lately come first.

Matching is fuzzy: the letters typed must appear in order in the command's name or its menu
("sv a" finds "Save As..."); runs of letters, word starts and a match at the very start
score higher, so the obvious command is at the top.
"""

import json

from PySide6.QtCore import Qt, QEvent
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QLineEdit, QTreeWidget, QTreeWidgetItem,
                               QLabel, QAbstractItemView)

MAX_ROWS = 14
RECENT = 8                  # commands remembered as "used lately"


def match(query, text):
    """Score of `query` against `text` (higher is better), or None when the letters of the
    query don't all appear in order. Case doesn't matter."""
    q = query.lower().strip()
    if not q:
        return 0
    t = text.lower()
    # a plain substring is the strongest kind of match
    pos = t.find(q)
    if pos >= 0:
        score = 100 - pos
        if pos == 0 or not t[pos - 1].isalnum():
            score += 20                     # at a word start
        return score
    score, ti, last = 0, 0, -2
    for ch in q:
        if ch == " ":
            continue
        i = t.find(ch, ti)
        if i < 0:
            return None
        if i == last + 1:
            score += 6                      # consecutive letters
        elif i == 0 or not t[i - 1].isalnum():
            score += 4                      # a word start
        else:
            score += 1
        score -= min(i - ti, 10) * 0.5      # gaps cost a little
        last, ti = i, i + 1
    return score


def menu_paths(menubar):
    """{QAction: "Menu > Submenu"} for every action reachable from the menu bar."""
    out = {}

    def walk(menu, path):
        for a in menu.actions():
            if a.menu() is not None:
                walk(a.menu(), path + [a.text().replace("&", "")])
            elif a not in out and not a.isSeparator():
                out[a] = " > ".join(path)
    for top in menubar.actions():
        if top.menu() is not None:
            walk(top.menu(), [top.text().replace("&", "")])
    return out


class CommandPalette(QDialog):
    def __init__(self, win):
        super().__init__(win, Qt.Popup | Qt.FramelessWindowHint)
        self.win = win
        self.setObjectName("command_palette")
        self.actions = win._shortcut_actions()          # name -> QAction
        self.paths = menu_paths(win.menuBar())
        self.chosen = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        self.edit = QLineEdit()
        self.edit.setPlaceholderText("Type a command (for example 'rotate', 'sv as', 'night')")
        self.edit.setClearButtonEnabled(True)
        self.edit.installEventFilter(self)
        lay.addWidget(self.edit)
        self.list = QTreeWidget()
        self.list.setColumnCount(3)
        self.list.setHeaderHidden(True)
        self.list.setRootIsDecorated(False)
        self.list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.list.setUniformRowHeights(True)
        self.list.setFocusPolicy(Qt.NoFocus)
        self.list.itemClicked.connect(lambda *_: self._run())
        lay.addWidget(self.list)
        self.hint = QLabel("Enter runs the command, Escape closes. Up/Down move.")
        self.hint.setStyleSheet("color: palette(mid);")
        lay.addWidget(self.hint)
        self.edit.textChanged.connect(self.refresh)
        self.resize(560, 420)
        self.refresh("")

    # -- the list --------------------------------------------------------------------------
    def _recent(self):
        try:
            return [n for n in json.loads(self.win.settings.value("palette_recent", "[]") or "[]")
                    if n in self.actions]
        except (TypeError, ValueError):
            return []

    def rows(self, query):
        """[(name, action)] best matches first (recent ones first when nothing is typed)."""
        recent = self._recent()
        scored = []
        for name, a in self.actions.items():
            if not a.isEnabled():
                continue
            path = self.paths.get(a, "")
            s = match(query, name)
            sp = match(query, path + " " + name) if path else None
            best = max(x for x in (s, sp) if x is not None) if (s is not None or sp is not None) else None
            if best is None:
                continue
            if name in recent:
                best += 50 - recent.index(name)     # used lately: first
            scored.append((best, name, a))
        scored.sort(key=lambda r: (-r[0], r[1].lower()))
        return [(n, a) for _s, n, a in scored[:MAX_ROWS]]

    def refresh(self, query):
        self.list.clear()
        for name, a in self.rows(query):
            label = name
            if a.isCheckable():
                label += "   [on]" if a.isChecked() else "   [off]"
            it = QTreeWidgetItem([label, self.paths.get(a, "Tool"),
                                  a.shortcut().toString(QKeySequence.NativeText)])
            it.setData(0, Qt.UserRole, name)
            it.setToolTip(0, a.toolTip())
            it.setForeground(1, self.palette().mid())
            self.list.addTopLevelItem(it)
        for c in range(3):
            self.list.resizeColumnToContents(c)
        if self.list.topLevelItemCount():
            self.list.setCurrentItem(self.list.topLevelItem(0))

    # -- keys ------------------------------------------------------------------------------
    def eventFilter(self, obj, e):
        if obj is self.edit and e.type() == QEvent.KeyPress:
            k = e.key()
            if k in (Qt.Key_Down, Qt.Key_Up, Qt.Key_PageDown, Qt.Key_PageUp):
                n = self.list.topLevelItemCount()
                if n:
                    cur = self.list.indexOfTopLevelItem(self.list.currentItem())
                    step = {Qt.Key_Down: 1, Qt.Key_Up: -1, Qt.Key_PageDown: 6, Qt.Key_PageUp: -6}[k]
                    self.list.setCurrentItem(self.list.topLevelItem(max(0, min(n - 1, cur + step))))
                return True
            if k in (Qt.Key_Return, Qt.Key_Enter):
                self._run()
                return True
        return super().eventFilter(obj, e)

    def _run(self):
        it = self.list.currentItem()
        if it is None:
            return
        name = it.data(0, Qt.UserRole)
        a = self.actions.get(name)
        if a is None or not a.isEnabled():
            return
        recent = [name] + [n for n in self._recent() if n != name]
        self.win.settings.setValue("palette_recent", json.dumps(recent[:RECENT]))
        self.chosen = name
        self.accept()
        a.trigger()                     # after closing: the command may open its own dialog

    def showEvent(self, e):
        super().showEvent(e)
        # centered near the top of the window, like editors do
        g = self.win.geometry()
        self.move(g.x() + (g.width() - self.width()) // 2, g.y() + 80)
        self.edit.setFocus()
