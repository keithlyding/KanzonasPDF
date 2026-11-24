"""The window's panels (Pages, Bookmarks, Layers, Objects, Sets, Properties, Tool chest,
Markups list): each one a Qt dock widget of its own, so several can be open at once, stacked
on the left or the right side with a handle between them to share the height, or side by side
as tabs.

Dock widgets rather than splitters of our own: the window already kept Properties, Tool chest
and the Markups list as dock widgets, and QMainWindow gives the rest for nothing: the handles
between panels and beside the page, dragging a panel by its title to the other side or onto
another panel (tabs), and saveState / restoreState for the layout across restarts (see
MainWindow._restore_layout). Panels don't float in windows of their own (a panel left on a
monitor that's gone would be lost); they move between the sides.
"""

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QDockWidget

from .i18n import tr

SIDES = (Qt.LeftDockWidgetArea, Qt.RightDockWidgetArea)
# a panel shown again lower than this gets its share of its side's height (a panel that was
# closed when the layout was saved comes back as a sliver, Qt's size for a hidden panel)
FAIR_MIN = 120


class PanelDock(QDockWidget):
    """One panel. Right-click its title: Move to the left side / Move to the right side, then
    the window's list of panels and toolbars to show or hide."""

    def __init__(self, name, title, widget, parent=None):
        super().__init__(title, parent)
        self.setObjectName(name)
        self.setWidget(widget)
        self.setFeatures(QDockWidget.DockWidgetClosable | QDockWidget.DockWidgetMovable)

    def _on_title(self, pos):
        w = self.widget()
        return w is None or pos.y() < w.geometry().top()

    def contextMenuEvent(self, e):
        win = self.parentWidget()
        if not self._on_title(e.pos()) or not hasattr(win, "createPopupMenu"):
            super().contextMenuEvent(e)         # (inside the panel: the window's own menu)
            return
        menu = title_menu(win, self)
        menu.exec(e.globalPos())
        menu.deleteLater()
        e.accept()


def title_menu(win, dock):
    """The menu of a panel's title bar: the moves to the other side, then the window's own
    list of panels and toolbars (QMainWindow.createPopupMenu)."""
    menu = win.createPopupMenu()
    first = menu.actions()[0] if menu.actions() else None
    area = win.dockWidgetArea(dock)
    for side, text in ((Qt.LeftDockWidgetArea, tr("Move to the &left side")),
                       (Qt.RightDockWidgetArea, tr("Move to the &right side"))):
        if side != area:
            a = menu.addAction(text)
            a.triggered.connect(lambda _=False, s=side: move_to(win, dock, s))
            if first is not None:
                menu.insertAction(first, a)
    if first is not None:
        menu.insertSeparator(first)
    return menu


def showing(dock):
    """The panel is on screen: open and not a tab behind another panel."""
    return dock.isVisible() and not dock.visibleRegion().isEmpty()


def toggle(win, dock):
    """A panel's icon on the strip, its menu command or its key: open it (in front, when it's
    a tab), or close it when it's showing."""
    if showing(dock):
        dock.hide()
    else:
        show(win, dock)


def show(win, dock):
    """Open the panel, in front of the panels it shares a tab bar with."""
    dock.show()
    dock.raise_()
    # (sizes are known once the window has laid the panel out)
    QTimer.singleShot(0, dock, lambda: fair_share(win, dock))


def move_to(win, dock, side):
    """Put the panel at the bottom of side (Qt.LeftDockWidgetArea or Qt.RightDockWidgetArea),
    open; what dropping it there by its title does."""
    win.addDockWidget(side, dock, Qt.Vertical)
    show(win, dock)


def column(win, dock):
    """The panels showing in the same column as dock on its side, top to bottom (dock
    included)."""
    area = win.dockWidgetArea(dock)
    g = dock.geometry()
    out = [d for d in win.findChildren(QDockWidget)
           if d.parentWidget() is win and not d.isFloating() and showing(d) and
           win.dockWidgetArea(d) == area and d.geometry().left() < g.right() and
           g.left() < d.geometry().right()]
    return sorted(out, key=lambda d: d.geometry().top())


def fair_share(win, dock):
    """A panel shown as a sliver gets an equal share of its column's height."""
    if not showing(dock) or win.dockWidgetArea(dock) not in SIDES or \
            dock.height() >= FAIR_MIN:
        return
    docks = column(win, dock)
    if len(docks) < 2:
        return
    total = sum(d.height() for d in docks)
    win.resizeDocks(docks, [total // len(docks)] * len(docks), Qt.Vertical)
