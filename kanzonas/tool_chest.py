"""Tool Chest: saved, named markup tools (a tool + its style) for one-click reuse.

Clicking an item activates its tool with that style for the next markups, without
changing the tool's normal defaults. Chests can be exported/imported as JSON files to
share with other people.
"""

import json

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap, QIcon, QColor
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
                               QPushButton, QInputDialog, QFileDialog, QMessageBox, QLabel,
                               QMenu)

from . import annotations as A
from .i18n import tr

# annotation kind -> tool that creates it
KIND_TOOL = {k: k for k in A.DEFAULTS}
KIND_TOOL.update({"rect": "rect"})


def tool_for(model):
    kind = model["kind"]
    if kind == "rect" and model["props"].get("cloud"):
        return "cloud"
    return KIND_TOOL.get(kind)


def _starter():
    """A few ready-made tools so a new chest isn't empty (delete or rename them freely). Their
    names and stamp words are in the user's language when the chest is first made."""
    def t(name, tool, **change):
        props = dict(A.DEFAULTS[tool])
        props.update(change)
        return {"name": name, "tool": tool, "props": props}
    return [
        t(tr("Red revision cloud"), "cloud", stroke="#d00000", width=1.5),
        t(tr("Yellow highlight"), "highlight", stroke="#ffdc00"),
        t(tr("Green highlight"), "highlight", stroke="#7ee07e"),
        t(tr("Red arrow"), "arrow", stroke="#d00000", width=2.0),
        t(tr("Blue box"), "rect", stroke="#0050ff", width=2.0),
        t(tr("Red note text box"), "textbox", text_color="#d00000", stroke="#d00000"),
        t(tr("Yellow callout"), "callout", fill="#ffffd0"),
        t(tr("APPROVED stamp"), "stamp", label=tr("APPROVED"), stroke="#008000"),
        t(tr("REJECTED stamp"), "stamp", label=tr("REJECTED"), stroke="#c00000"),
    ]


def _valid(items):
    """The usable tools in a saved or imported chest: a name, a known tool and its style
    (style values that don't fit the tool are left out)."""
    out = []
    for i in items if isinstance(items, list) else []:
        if isinstance(i, dict) and i.get("tool") in A.DEFAULTS and \
                isinstance(i.get("name"), str) and i["name"] and isinstance(i.get("props"), dict):
            base = A.DEFAULTS[i["tool"]]
            props = {k: v for k, v in i["props"].items() if k not in base or A._fits(base[k], v)}
            out.append(dict(i, props=props))
    return out


def load():
    from . import paths
    if A._settings().value("tool_chest", None) is None:     # never used: the starter set
        return _starter()
    return _valid(paths.stored_json(A._settings(), "tool_chest", []))


def save(items):
    A._settings().setValue("tool_chest", json.dumps(items))


def _icon(props):
    pm = QPixmap(16, 16)
    pm.fill(QColor(props.get("stroke") or props.get("text_color") or "#888888"))
    return QIcon(pm)


class ToolChestPanel(QWidget):
    use = Signal(str, dict)          # tool id, props
    addRequested = Signal()

    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        hint = QLabel(tr("Your favorite markup styles, one click away. Click one, then draw "
                         "on the page: it uses that tool with that color and size, without "
                         "changing the tool's normal settings. To save your own: draw and style "
                         "a markup, select it, click “Add”."))
        hint.setWordWrap(True)
        hint.setStyleSheet("color: gray;")
        lay.addWidget(hint)
        self.list = QListWidget()
        self.list.itemClicked.connect(self._clicked)
        self.list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._menu)
        lay.addWidget(self.list)
        row = QHBoxLayout()
        add = QPushButton(tr("Add"))
        add.setToolTip(tr("Save the selected markup's style (or the current tool's settings)"))
        add.clicked.connect(self.addRequested.emit)
        more = QPushButton(tr("More"))
        m = QMenu(more)
        m.addAction(tr("Rename..."), self._rename)
        m.addAction(tr("Delete"), self._delete)
        m.addAction(tr("Add the starter tools"), self._add_starter)
        m.addSeparator()
        m.addAction(tr("Export tool chest..."), self._export)
        m.addAction(tr("Import tool chest..."), self._import)
        more.setMenu(m)
        row.addWidget(add)
        row.addWidget(more)
        lay.addLayout(row)
        self.items = load()
        self._fill()

    def _fill(self):
        self.list.clear()
        for it in self.items:
            label = A.LABELS.get(it["tool"], it["tool"])
            li = QListWidgetItem(_icon(it["props"]), f"{it['name']}   ({label})")
            li.setToolTip(", ".join(f"{k}: {v}" for k, v in it["props"].items()))
            self.list.addItem(li)

    def add(self, tool, props, suggested):
        name, ok = QInputDialog.getText(self, tr("Tool chest"), tr("Name for this tool:"),
                                        text=suggested)
        if not ok or not name.strip():
            return
        self.items.append({"name": name.strip(), "tool": tool, "props": dict(props)})
        save(self.items)
        self._fill()

    def _add_starter(self):
        have = {i["name"] for i in self.items}
        self.items += [i for i in _starter() if i["name"] not in have]
        save(self.items)
        self._fill()

    def _clicked(self, li):
        it = self.items[self.list.row(li)]
        self.use.emit(it["tool"], dict(it["props"]))

    def _menu(self, pos):
        if self.list.itemAt(pos) is None:
            return
        m = QMenu(self)
        m.addAction(tr("Rename..."), self._rename)
        m.addAction(tr("Delete"), self._delete)
        m.exec(self.list.mapToGlobal(pos))

    def _rename(self):
        r = self.list.currentRow()
        if r < 0:
            return
        name, ok = QInputDialog.getText(self, tr("Rename"), tr("Name:"), text=self.items[r]["name"])
        if ok and name.strip():
            self.items[r]["name"] = name.strip()
            save(self.items)
            self._fill()

    def _delete(self):
        r = self.list.currentRow()
        if r >= 0:
            del self.items[r]
            save(self.items)
            self._fill()

    def _export(self):
        path, _ = QFileDialog.getSaveFileName(self, tr("Export tool chest"), "tool-chest.json",
                                              tr("Tool chest") + " (*.json)")
        if path:
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"kanzonas_tool_chest": 1, "items": self.items}, f, indent=2)

    def _import(self):
        path, _ = QFileDialog.getOpenFileName(self, tr("Import tool chest"), "",
                                              tr("Tool chest") + " (*.json)")
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            new = _valid(data.get("items", []))
        except (OSError, ValueError, AttributeError):
            QMessageBox.warning(self, tr("Tool chest"), tr("That file isn't a tool chest."))
            return
        self.items.extend(new)
        save(self.items)
        self._fill()
        QMessageBox.information(self, tr("Tool chest"),
                                tr("Imported {n} tool(s).").format(n=len(new)))
