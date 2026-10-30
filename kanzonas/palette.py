"""Command palette (Ctrl+Shift+P): type a few letters of what you want to do, pick the
command from the list, Enter runs it. Every menu command and tool is there, with its menu
and keyboard shortcut, so nothing has to be hunted for on the ribbon. Commands you used
from the palette lately come first.

Matching is fuzzy: the letters typed must appear in order in the command's name or its menu
("sv a" finds "Save As..."); runs of letters, word starts and a match at the very start
score higher, so the obvious command is at the top.

In another language the commands are listed, and found, by their translated names; their
English names find them too (and the recent commands are remembered by the English name, so
they survive a change of language).
"""

import json

from PySide6.QtCore import Qt, QEvent
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QLineEdit, QTreeWidget, QTreeWidgetItem,
                               QLabel, QAbstractItemView)

from .i18n import tr

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


class Finder:
    """The commands the palette (and the CAD command line, cad_commands.py) find: every menu
    command and tool, by its name, its menu, or its English name."""

    def __init__(self, win):
        self.win = win
        self.actions = win._shortcut_actions()          # English name -> QAction
        # the names as the menus show them (the same as the English ones in English)
        self.names = {n: win.action_name(a) for n, a in self.actions.items()}
        self.paths = menu_paths(win.menuBar())

    def _recent(self):
        try:
            return [n for n in json.loads(self.win.settings.value("palette_recent", "[]") or "[]")
                    if n in self.actions]
        except (TypeError, ValueError):
            return []

    def remember(self, name):
        """name was just run: it comes first among the recent commands."""
        recent = [name] + [n for n in self._recent() if n != name]
        self.win.settings.setValue("palette_recent", json.dumps(recent[:RECENT]))

    def rows(self, query):
        """[(name, action)] best matches first (recent ones first when nothing is typed);
        name is the English name (the id), self.names[name] the one shown."""
        recent = self._recent()
        scored = []
        for name, a in self.actions.items():
            if not a.isEnabled():
                continue
            shown = self.names.get(name, name)
            path = self.paths.get(a, "")
            scores = [match(query, shown)]
            if path:
                scores.append(match(query, path + " " + shown))
            if shown != name:
                # the English name finds it too (a shade lower, so on a tie the name the user
                # sees wins)
                en = match(query, name)
                scores.append(None if en is None else en - 3)
            scores = [x for x in scores if x is not None]
            if not scores:
                continue
            best = max(scores)
            if name in recent:
                best += 50 - recent.index(name)     # used lately: first
            scored.append((best, shown.lower(), name, a))
        scored.sort(key=lambda r: (-r[0], r[1]))
        return [(n, a) for _s, _shown, n, a in scored[:MAX_ROWS]]


class CommandPalette(QDialog):
    def __init__(self, win):
        super().__init__(win, Qt.Popup | Qt.FramelessWindowHint)
        self.win = win
        self.finder = Finder(win)
        self.actions, self.names, self.paths = (self.finder.actions, self.finder.names,
                                                self.finder.paths)
        self.rows, self._recent, self.remember = (self.finder.rows, self.finder._recent,
                                                  self.finder.remember)
        self.setObjectName("command_palette")
        self.chosen = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        self.edit = QLineEdit()
        self.edit.setPlaceholderText(tr("Type a command (for example 'rotate', 'sv as', 'night')"))
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
        self.hint = QLabel(tr("Enter runs the command, Escape closes. Up/Down move."))
        self.hint.setStyleSheet("color: palette(mid);")
        lay.addWidget(self.hint)
        self.edit.textChanged.connect(self.refresh)
        self.resize(560, 420)
        self.refresh("")

    # -- the list --------------------------------------------------------------------------
    def refresh(self, query):
        self.list.clear()
        for name, a in self.rows(query):
            label = self.names.get(name, name)
            if a.isCheckable():
                label += "   " + (tr("[on]") if a.isChecked() else tr("[off]"))
            it = QTreeWidgetItem([label, self.paths.get(a, tr("Tool")),
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
        self.remember(name)
        self.chosen = name
        self.accept()
        a.trigger()                     # after closing: the command may open its own dialog

    def showEvent(self, e):
        super().showEvent(e)
        # centered near the top of the window, like editors do
        g = self.win.geometry()
        self.move(g.x() + (g.width() - self.width()) // 2, g.y() + 80)
        self.edit.setFocus()
