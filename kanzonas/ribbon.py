"""Office / PDF-XChange style ribbon: tabs of labeled button groups.

Built from the app's existing QActions (so checked states, shortcuts, enabling and tooltips
stay in sync with the menus). Double-click a tab (or Ctrl+F1) to collapse it to just the
tab names; click a tab to open it again.

Compact like LibreOffice's tabbed bar: two rows of small buttons, group names optional, and a
tab scrolls sideways (mouse wheel) when the window is too narrow for it.
"""

from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtWidgets import (QTabWidget, QWidget, QHBoxLayout, QVBoxLayout, QGridLayout,
                               QToolButton, QLabel, QFrame, QSizePolicy, QScrollArea)

LARGE_ICON = 20
SMALL_ICON = 16
ROWS = 2                       # small buttons stacked per column
SMALL_HEIGHT = 22              # one row of small buttons, pixels


class _Strip(QScrollArea):
    """A tab's contents; scrolls sideways with the mouse wheel when the window is narrow."""

    def __init__(self, inner):
        super().__init__()
        self.setWidget(inner)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.horizontalScrollBar().setFixedHeight(7)      # thin: only shows when it's needed

    def showEvent(self, e):
        # scroll instead of squeezing button names (measured now: icons are set after building)
        self.widget().setMinimumWidth(self.widget().sizeHint().width())
        super().showEvent(e)

    def wheelEvent(self, e):
        bar = self.horizontalScrollBar()
        if bar.maximum() > 0:
            bar.setValue(bar.value() - e.angleDelta().y())
            e.accept()
        else:
            super().wheelEvent(e)

    def sizeHint(self):
        h = self.widget().sizeHint()
        bar = self.horizontalScrollBar()
        return QSize(h.width(), h.height() + (bar.sizeHint().height() if bar.maximum() > 0 else 0))


class Ribbon(QTabWidget):
    collapsedChanged = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDocumentMode(True)
        self.setObjectName("ribbon")
        self._collapsed = False
        self._expanded_height = None
        self._labels = []
        self._show_labels = False
        self.tabBar().tabBarDoubleClicked.connect(lambda _i: self.set_collapsed(not self._collapsed))
        self.tabBar().tabBarClicked.connect(self._tab_clicked)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    # ---- building ---------------------------------------------------------------
    def add_tab(self, title, groups):
        """groups: [(group title, 'large' | 'small', [QAction | QWidget | None, ...])]"""
        page = QWidget()
        row = QHBoxLayout(page)
        row.setContentsMargins(2, 1, 2, 1)
        row.setSpacing(2)
        for gtitle, size, items in groups:
            row.addWidget(self._group(gtitle, size, items))
            line = QFrame()
            line.setFrameShape(QFrame.VLine)
            line.setFrameShadow(QFrame.Sunken)
            row.addWidget(line)
        row.addStretch(1)
        self.addTab(_Strip(page), title)
        return page

    def _group(self, title, size, items):
        box = QWidget()
        v = QVBoxLayout(box)
        v.setContentsMargins(2, 0, 2, 0)
        v.setSpacing(0)
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(1)
        grid.setVerticalSpacing(0)
        col = 0
        k = 0
        for item in items:
            if item is None:
                continue
            if isinstance(item, QWidget):
                w = item
            else:
                w = QToolButton()
                w.setDefaultAction(item)
                w.setAutoRaise(True)
                if size == "large":
                    w.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
                    w.setIconSize(QSize(LARGE_ICON, LARGE_ICON))
                    w.setMinimumWidth(44)
                    w.setFixedHeight(ROWS * SMALL_HEIGHT)
                else:
                    w.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
                    w.setIconSize(QSize(SMALL_ICON, SMALL_ICON))
                    w.setFixedHeight(SMALL_HEIGHT)
                    w.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            if size == "large":
                grid.addWidget(w, 0, col, ROWS, 1)
                col += 1
            else:
                grid.addWidget(w, k % ROWS, k // ROWS)
                k += 1
        v.addLayout(grid, 1)
        label = QLabel(title)
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet("color: gray; font-size: 7pt;")
        label.setVisible(self._show_labels)
        self._labels.append(label)
        v.addWidget(label)
        return box

    def set_group_names(self, on):
        """Show the group names under the buttons (Microsoft Office style); off is compact."""
        self._show_labels = bool(on)
        for label in self._labels:
            label.setVisible(self._show_labels)
        if not self._collapsed:
            self.setMaximumHeight(self.expanded_height())

    # ---- collapsing ------------------------------------------------------------
    def expanded_height(self):
        """Tab names, two rows of buttons, group names if shown and room for a thin scrollbar."""
        label = self._labels[0].sizeHint().height() if self._labels and self._show_labels else 0
        return self.tabBar().sizeHint().height() + ROWS * SMALL_HEIGHT + 2 + label + 2 + 7 + 4

    def is_collapsed(self):
        return self._collapsed

    def set_collapsed(self, on):
        self._collapsed = bool(on)
        if on:
            self.setMaximumHeight(self.tabBar().sizeHint().height())
        else:
            self.setMaximumHeight(self.expanded_height())
        self.collapsedChanged.emit(self._collapsed)

    def _tab_clicked(self, _index):
        if self._collapsed:
            self.set_collapsed(False)
