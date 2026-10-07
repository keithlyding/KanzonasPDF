"""Office / PDF-XChange style ribbon: tabs of labeled button groups.

Built from the app's existing QActions (so checked states, shortcuts, enabling and tooltips
stay in sync with the menus). Double-click a tab (or Ctrl+F1) to collapse it to just the
tab names; click a tab to open it again.
"""

from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtWidgets import (QTabWidget, QWidget, QHBoxLayout, QVBoxLayout, QGridLayout,
                               QToolButton, QLabel, QFrame, QSizePolicy)

LARGE_ICON = 26
SMALL_ICON = 16
ROWS = 3                       # small buttons stacked per column


class Ribbon(QTabWidget):
    collapsedChanged = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDocumentMode(True)
        self.setObjectName("ribbon")
        self._collapsed = False
        self._expanded_height = None
        self.tabBar().tabBarDoubleClicked.connect(lambda _i: self.set_collapsed(not self._collapsed))
        self.tabBar().tabBarClicked.connect(self._tab_clicked)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    # ---- building ---------------------------------------------------------------
    def add_tab(self, title, groups):
        """groups: [(group title, 'large' | 'small', [QAction | QWidget | None, ...])]"""
        page = QWidget()
        row = QHBoxLayout(page)
        row.setContentsMargins(4, 2, 4, 0)
        row.setSpacing(4)
        for gtitle, size, items in groups:
            row.addWidget(self._group(gtitle, size, items))
            line = QFrame()
            line.setFrameShape(QFrame.VLine)
            line.setFrameShadow(QFrame.Sunken)
            row.addWidget(line)
        row.addStretch(1)
        self.addTab(page, title)
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
                    w.setMinimumWidth(48)
                    w.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
                else:
                    w.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
                    w.setIconSize(QSize(SMALL_ICON, SMALL_ICON))
                    w.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            if size == "large":
                grid.addWidget(w, 0, col, ROWS, 1)
                col += 1
            else:
                grid.addWidget(w, k % ROWS, k // ROWS)
                k += 1
        v.addLayout(grid, 1)
        label = QLabel(title)
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet("color: gray; font-size: 8pt;")
        v.addWidget(label)
        return box

    # ---- collapsing ------------------------------------------------------------
    def is_collapsed(self):
        return self._collapsed

    def set_collapsed(self, on):
        self._collapsed = bool(on)
        if on:
            self.setMaximumHeight(self.tabBar().sizeHint().height())
        else:
            self.setMaximumHeight(16777215)
        self.collapsedChanged.emit(self._collapsed)

    def _tab_clicked(self, _index):
        if self._collapsed:
            self.set_collapsed(False)
