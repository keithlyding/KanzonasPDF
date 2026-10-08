"""Layers panel: show / hide a PDF's optional content layers (common in CAD plots)."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
                               QPushButton, QLabel)


class LayersPanel(QWidget):
    toggled = Signal(int, bool)        # layer number, visible
    allToggled = Signal(bool)

    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(2, 2, 2, 2)
        row = QHBoxLayout()
        show = QPushButton("Show all")
        hide = QPushButton("Hide all")
        show.clicked.connect(lambda: self.allToggled.emit(True))
        hide.clicked.connect(lambda: self.allToggled.emit(False))
        row.addWidget(show)
        row.addWidget(hide)
        row.addStretch(1)
        lay.addLayout(row)
        self.list = QListWidget()
        self.list.itemChanged.connect(self._changed)
        lay.addWidget(self.list)
        self.empty = QLabel("This document has no layers.")
        self.empty.setStyleSheet("color: gray;")
        lay.addWidget(self.empty)
        self._loading = False

    def set_layers(self, configs):
        """configs: PyMuPDF layer_ui_configs() entries."""
        self._loading = True
        self.list.clear()
        for c in configs:
            it = QListWidgetItem("    " * int(c.get("depth", 0)) + (c.get("text") or "(unnamed)"))
            it.setData(Qt.UserRole, c["number"])
            if c.get("type") in ("checkbox", "radiobox"):
                it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
                it.setCheckState(Qt.Checked if c.get("on") else Qt.Unchecked)
                if c.get("locked"):
                    it.setFlags(it.flags() & ~Qt.ItemIsEnabled)
            self.list.addItem(it)
        self.empty.setVisible(not configs)
        self.list.setVisible(bool(configs))
        self._loading = False

    def _changed(self, it):
        if not self._loading:
            self.toggled.emit(it.data(Qt.UserRole), it.checkState() == Qt.Checked)
