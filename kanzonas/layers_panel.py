"""Layers panel: show / hide a PDF's optional content layers (common in CAD plots), and (1.12)
the layer new markups go on, and New layer (markup_layers.py)."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
                               QPushButton, QLabel, QComboBox)

from .i18n import tr


class LayersPanel(QWidget):
    toggled = Signal(int, bool)        # layer number, visible
    allToggled = Signal(bool)
    markupLayerChosen = Signal(int)    # the OCG xref new markups go on (0: none)
    newLayerRequested = Signal()

    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(2, 2, 2, 2)
        row = QHBoxLayout()
        show = QPushButton(tr("Show all"))
        hide = QPushButton(tr("Hide all"))
        show.clicked.connect(lambda: self.allToggled.emit(True))
        hide.clicked.connect(lambda: self.allToggled.emit(False))
        row.addWidget(show)
        row.addWidget(hide)
        row.addStretch(1)
        lay.addLayout(row)
        self.list = QListWidget()
        self.list.itemChanged.connect(self._changed)
        lay.addWidget(self.list)
        self.empty = QLabel(tr("This document has no layers."))
        self.empty.setStyleSheet("color: gray;")
        lay.addWidget(self.empty)
        lay.addWidget(QLabel(tr("New markups go on:")))
        self.markup_box = QComboBox()
        self.markup_box.setToolTip(tr("The layer the markups you draw go on (shown and hidden "
                                      "with it, in other PDF programs too)"))
        self.markup_box.activated.connect(
            lambda _i: self.markupLayerChosen.emit(self.markup_box.currentData() or 0))
        lay.addWidget(self.markup_box)
        new = QPushButton(tr("New layer..."))
        new.setToolTip(tr("Add a layer to the document, for markups"))
        new.clicked.connect(self.newLayerRequested.emit)
        row2 = QHBoxLayout()
        row2.addWidget(new)
        row2.addStretch(1)
        lay.addLayout(row2)
        self._loading = False

    def set_markup_layers(self, layers, current):
        """layers: [(xref, name, on)] (markup_layers.layers); current: the chosen one or None."""
        self.markup_box.blockSignals(True)
        self.markup_box.clear()
        self.markup_box.addItem(tr("No layer"), 0)
        for x, name, _on in layers:
            self.markup_box.addItem(name, x)
        at = self.markup_box.findData(current or 0)
        self.markup_box.setCurrentIndex(max(0, at))
        self.markup_box.blockSignals(False)

    def set_layers(self, configs):
        """configs: PyMuPDF layer_ui_configs() entries."""
        self._loading = True
        self.list.clear()
        for c in configs:
            it = QListWidgetItem("    " * int(c.get("depth", 0)) + (c.get("text") or tr("(unnamed)")))
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
