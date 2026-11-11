"""Office / PDF-XChange style ribbon: tabs of labeled button groups.

Built from the app's existing QActions (so checked states, shortcuts, enabling and tooltips
stay in sync with the menus). Double-click a tab (or Ctrl+F1) to collapse it to just the
tab names; click a tab to open it again.

Compact like LibreOffice's tabbed bar: two rows of small buttons, group names optional, and a
tab scrolls sideways (mouse wheel) when the window is too narrow for it. Every tab fits a
1366-pixel-wide screen in English, Spanish and Italian (tests/test_ribbon_fits.py): commands
used less often share a button with an arrow (SplitButton) or are listed under a group's own arrow
(the narrow button at its right end), and a group can mix large buttons with a column of
small ones (Stack) or a row of icon-only ones (Icons).
"""

from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtWidgets import (QTabWidget, QWidget, QHBoxLayout, QVBoxLayout, QGridLayout,
                               QToolButton, QLabel, QFrame, QSizePolicy, QScrollArea, QMenu)

from .i18n import tr

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


class SplitButton(QToolButton):
    """A small ribbon button for several similar commands, as AutoCAD's ribbon has (Circle with
    an arrow for Arc): clicking it runs the one its face shows, the arrow beside it lists them
    all. The face starts as the first and then shows the one last used, or the tool that is
    on (picked by its shortcut or a menu too). Made by split_button."""

    def __init__(self, actions, parent=None, large=False):
        super().__init__(parent)
        self.setPopupMode(QToolButton.MenuButtonPopup)
        menu = QMenu(self)
        menu.addActions(actions)
        self.setMenu(menu)
        self.setDefaultAction(actions[0])
        menu.triggered.connect(self.setDefaultAction)
        for a in actions:
            if a.isCheckable():
                a.toggled.connect(self._toggled)
        self.setAutoRaise(True)
        if large:           # (in a group of large buttons: the name under the icon)
            self.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
            self.setIconSize(QSize(LARGE_ICON, LARGE_ICON))
            self.setFixedHeight(ROWS * SMALL_HEIGHT)
        else:
            self.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
            self.setIconSize(QSize(SMALL_ICON, SMALL_ICON))
            self.setFixedHeight(SMALL_HEIGHT)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def _toggled(self, on):
        a = self.sender()
        if on and a is not None and a is not self.defaultAction():
            self.setDefaultAction(a)

    def sizeHint(self):
        # as wide as its widest face, so the tab doesn't shift when the face changes
        h = super().sizeHint()
        fm = self.fontMetrics()
        now = fm.horizontalAdvance(self.text())
        most = max((fm.horizontalAdvance(a.iconText()) for a in self.menu().actions()),
                   default=now)
        return QSize(h.width() + max(0, most - now), h.height())

    def minimumSizeHint(self):
        return self.sizeHint()


def split_button(actions, large=False):
    """One ribbon button (SplitButton) for actions (the first is its face at the start); with
    a single action, that action itself (a plain button). None when there is none. large:
    for a group of large buttons."""
    actions = [a for a in actions if a is not None]
    if len(actions) < 2:
        return actions[0] if actions else None
    return SplitButton(actions, large=large)


class Stack(list):
    """In a large group: these commands as small buttons stacked in one column (up to ROWS),
    beside the group's large buttons."""


class Icons(list):
    """In a small group: these commands as icon-only small buttons side by side, taking one
    small button's place (their names are in their tool tips)."""


def _small_button(action):
    w = QToolButton()
    w.setDefaultAction(action)
    w.setAutoRaise(True)
    w.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
    w.setIconSize(QSize(SMALL_ICON, SMALL_ICON))
    w.setFixedHeight(SMALL_HEIGHT)
    w.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    return w


def _icons_row(actions):
    row = QWidget()
    h = QHBoxLayout(row)
    h.setContentsMargins(0, 0, 0, 0)
    h.setSpacing(1)
    for a in actions:
        if a is None:
            continue
        b = QToolButton()
        b.setDefaultAction(a)
        b.setAutoRaise(True)
        b.setToolButtonStyle(Qt.ToolButtonIconOnly)
        b.setIconSize(QSize(SMALL_ICON, SMALL_ICON))
        b.setFixedHeight(SMALL_HEIGHT)
        h.addWidget(b)
    h.addStretch(1)
    row.setFixedHeight(SMALL_HEIGHT)
    return row


class GroupArrow(QToolButton):
    """The narrow arrow at a group's right end: a list of the group's commands used less often
    (like the arrow in the corner of a group on Microsoft Office's ribbon)."""

    def __init__(self, title, actions, parent=None):
        super().__init__(parent)
        self.setPopupMode(QToolButton.InstantPopup)
        self.setArrowType(Qt.DownArrow)
        self.setAutoRaise(True)
        self.setFixedSize(14, ROWS * SMALL_HEIGHT)
        self.setStyleSheet("QToolButton::menu-indicator { image: none; width: 0px; }")
        menu = QMenu(self)
        menu.addActions(actions)
        self.setMenu(menu)
        self.setToolTip(tr("More in {group}: {commands}").format(
            group=title, commands=", ".join(a.iconText() for a in actions)))


class Ribbon(QTabWidget):
    collapsedChanged = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDocumentMode(True)
        self.setObjectName("ribbon")
        self._collapsed = False
        self._labels = []
        self._show_labels = False
        self.tabBar().tabBarDoubleClicked.connect(lambda _i: self.set_collapsed(not self._collapsed))
        self.tabBar().tabBarClicked.connect(self._tab_clicked)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    # ---- building ---------------------------------------------------------------
    def add_tab(self, title, groups):
        """groups: [(group title, 'large' | 'small', [QAction | QWidget | Stack | Icons | None,
        ...][, [QAction, ...] listed under the group's arrow])]"""
        page = QWidget()
        row = QHBoxLayout(page)
        row.setContentsMargins(2, 1, 2, 1)
        row.setSpacing(2)
        for gtitle, size, items, *more in groups:
            row.addWidget(self._group(gtitle, size, items, more[0] if more else None))
            line = QFrame()
            line.setFrameShape(QFrame.VLine)
            line.setFrameShadow(QFrame.Sunken)
            row.addWidget(line)
        row.addStretch(1)
        self.addTab(_Strip(page), title)
        return page

    def _group(self, title, size, items, more=None):
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
            if isinstance(item, Stack):
                for r, a in enumerate(x for x in item if x is not None):
                    grid.addWidget(a if isinstance(a, QWidget) else _small_button(a), r, col)
                col += 1
                continue
            if isinstance(item, Icons):
                w = _icons_row(item)
            elif isinstance(item, QWidget):
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
                    w = _small_button(item)
            if size == "large":
                grid.addWidget(w, 0, col, ROWS, 1)
                col += 1
            else:
                grid.addWidget(w, k % ROWS, k // ROWS)
                k += 1
        more = [a for a in (more or []) if a is not None]
        if more:
            columns = col if size == "large" else (k + ROWS - 1) // ROWS
            grid.addWidget(GroupArrow(title, more), 0, columns, ROWS, 1)
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
