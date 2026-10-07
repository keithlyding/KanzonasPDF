"""Tool Chest: saved, named markup tools (a tool + its style) for one-click reuse.

Clicking an item activates its tool with that style for the next markups, without
changing the tool's normal defaults. Chests can be exported/imported as JSON files to
share with other people.
"""

import json

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap, QIcon, QColor, QAction
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
                               QPushButton, QInputDialog, QFileDialog, QMessageBox, QLabel,
                               QMenu)

from . import annotations as A

# annotation kind -> tool that creates it
KIND_TOOL = {k: k for k in A.DEFAULTS}
KIND_TOOL.update({"rect": "rect"})


def tool_for(model):
    kind = model["kind"]
    if kind == "rect" and model["props"].get("cloud"):
        return "cloud"
    return KIND_TOOL.get(kind)


def load():
    try:
        items = json.loads(A._settings().value("tool_chest", "[]") or "[]")
        return [i for i in items if i.get("tool") in A.DEFAULTS]
    except (ValueError, TypeError):
        return []


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
        hint = QLabel("Click a tool to use it. Save a selected markup's style with "
                      "“Add”.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: gray;")
        lay.addWidget(hint)
        self.list = QListWidget()
        self.list.itemClicked.connect(self._clicked)
        self.list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._menu)
        lay.addWidget(self.list)
        row = QHBoxLayout()
        add = QPushButton("Add")
        add.setToolTip("Save the selected markup's style (or the current tool's settings)")
        add.clicked.connect(self.addRequested.emit)
        more = QPushButton("More")
        m = QMenu(more)
        m.addAction("Rename...", self._rename)
        m.addAction("Delete", self._delete)
        m.addSeparator()
        m.addAction("Export tool chest...", self._export)
        m.addAction("Import tool chest...", self._import)
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
        name, ok = QInputDialog.getText(self, "Tool chest", "Name for this tool:", text=suggested)
        if not ok or not name.strip():
            return
        self.items.append({"name": name.strip(), "tool": tool, "props": dict(props)})
        save(self.items)
        self._fill()

    def _clicked(self, li):
        it = self.items[self.list.row(li)]
        self.use.emit(it["tool"], dict(it["props"]))

    def _menu(self, pos):
        if self.list.itemAt(pos) is None:
            return
        m = QMenu(self)
        m.addAction("Rename...", self._rename)
        m.addAction("Delete", self._delete)
        m.exec(self.list.mapToGlobal(pos))

    def _rename(self):
        r = self.list.currentRow()
        if r < 0:
            return
        name, ok = QInputDialog.getText(self, "Rename", "Name:", text=self.items[r]["name"])
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
        path, _ = QFileDialog.getSaveFileName(self, "Export tool chest", "tool-chest.json",
                                              "Tool chest (*.json)")
        if path:
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"kanzonas_tool_chest": 1, "items": self.items}, f, indent=2)

    def _import(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import tool chest", "", "Tool chest (*.json)")
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            new = [i for i in data.get("items", []) if i.get("tool") in A.DEFAULTS
                   and isinstance(i.get("props"), dict) and i.get("name")]
        except (OSError, ValueError, AttributeError):
            QMessageBox.warning(self, "Tool chest", "That file isn't a tool chest.")
            return
        self.items.extend(new)
        save(self.items)
        self._fill()
        QMessageBox.information(self, "Tool chest", f"Imported {len(new)} tool(s).")
