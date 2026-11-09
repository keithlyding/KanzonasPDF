"""Reading comfort, in the View menu: Full screen, Presentation, Page layout (single page,
continuous, two pages side by side, with or without the cover page on its own), Reading view
(the page's text reflowed in large, resizable type), Read aloud and Auto scroll.

build_actions / add_to_view_menu are called while the main window is built; everything else
(the presentation window, the reading pane, the speech engine) is made the first time it's
used, so none of it costs anything at start-up."""

import shiboken6
from PySide6.QtCore import QEvent, QObject, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QCursor
from PySide6.QtWidgets import (QApplication, QDockWidget, QFrame, QHBoxLayout, QLabel,
                               QTextBrowser, QToolBar, QToolButton, QVBoxLayout, QWidget,
                               QMessageBox)

from . import paths
from .i18n import tr

# View > Page layout and its shortcuts
LAYOUT_KEYS = (("single", "Ctrl+5"), ("continuous", "Ctrl+6"), ("two", "Ctrl+7"),
               ("two_continuous", "Ctrl+8"))


def build_actions(win):
    """The View menu's reading commands (QActions on the window, as a_full_screen etc.)."""
    act = win._act
    win.a_full_screen = act(tr("Full screen"), lambda: toggle_full_screen(win), "Ctrl+Shift+L",
                            tip=tr("Only the pages, on the whole screen: no toolbars, panels "
                                   "or menus. Move the pointer to the top edge for a slim bar; "
                                   "Escape leaves full screen"))
    win.a_full_screen.setCheckable(True)
    win.a_present = act(tr("Presentation"), lambda: start_presentation(win), "F5",
                        tip=tr("Show the pages one at a time on the whole screen, for an "
                               "audience: click or Space for the next page, B / W for a black "
                               "or white screen, L for a laser pointer, Escape to end"))
    labels = {"single": tr("Single page"), "continuous": tr("Continuous"),
              "two": tr("Two pages"), "two_continuous": tr("Two pages continuous")}
    tips = {"single": tr("One page at a time; scrolling past its end turns the page"),
            "continuous": tr("The pages one under the other, scrolling from one to the next"),
            "two": tr("Two pages side by side, one spread at a time"),
            "two_continuous": tr("Two pages side by side, the spreads one under the other")}
    win.layout_group = QActionGroup(win)
    win.layout_actions = {}
    for key, sc in LAYOUT_KEYS:
        a = act(labels[key], lambda _=False, k=key: set_layout(win, k), sc, tip=tips[key])
        a.setCheckable(True)
        win.layout_group.addAction(a)
        win.layout_actions[key] = a
    win.layout_actions["continuous"].setChecked(True)
    win.a_cover = act(tr("Show cover page separately"), lambda: set_layout(win, None),
                      tip=tr("With two pages side by side, the first page alone on the right, "
                             "so a book's left and right pages line up"))
    win.a_cover.setCheckable(True)
    win.a_reflow = act(tr("Reading view"), lambda: toggle_reflow(win), "Ctrl+4",
                       tip=tr("The page's text in a side panel, reflowed in large type you can "
                              "make bigger or smaller (Ctrl+wheel), for small screens and "
                              "tired eyes; the PDF isn't changed"))
    win.a_reflow.setCheckable(True)
    win.a_read_page = act(tr("Read this page"), lambda: read(win, "page"), "Ctrl+Shift+V",
                          tip=tr("Read the page aloud with the computer's voice"))
    win.a_read_from = act(tr("Read from selected text"), lambda: read(win, "selection"),
                          tip=tr("Read aloud from the selected text (or from the top of this "
                                 "page) to the end of the document"))
    win.a_read_doc = act(tr("Read the whole document"), lambda: read(win, "document"),
                         "Ctrl+Shift+B", tip=tr("Read the document aloud from the first page"))
    win.a_read_pause = act(tr("Pause or resume reading"), lambda: reader(win).toggle_pause(),
                           "Ctrl+Shift+C", tip=tr("Pause reading aloud, or go on from where "
                                                  "it paused"))
    win.a_read_stop = act(tr("Stop reading"), lambda: reader(win).stop(), "Ctrl+Shift+E",
                          tip=tr("Stop reading aloud"))
    win.a_autoscroll = act(tr("Auto scroll"), lambda: toggle_autoscroll(win), "Ctrl+Shift+A",
                           tip=tr("Scroll the document slowly by itself; Up and Down arrows "
                                  "change the speed, Escape stops"))
    win.a_autoscroll.setCheckable(True)
    sync(win)


# icons (Material Design Icons names) of the reading commands, in the menus, on the ribbon's
# Reading tab and on full screen's top bar
ICONS = {"a_full_screen": "fullscreen", "a_present": "projector-screen",
         "a_cover": "book-open-blank-variant", "a_reflow": "book-open-page-variant-outline",
         "a_read_page": "account-voice", "a_read_from": "text-long",
         "a_read_doc": "book-open-variant", "a_read_pause": "play-pause",
         "a_read_stop": "stop-circle-outline", "a_autoscroll": "chevron-double-down"}
LAYOUT_ICONS = {"single": "file-outline", "continuous": "view-sequential-outline",
                "two": "book-open-outline", "two_continuous": "view-grid-outline"}


def apply_icons(win):
    """(again when the theme changes: the icons are tinted for it)"""
    from . import theme
    for attr, name in ICONS.items():
        getattr(win, attr).setIcon(theme.icon_named(name))
    for key, name in LAYOUT_ICONS.items():
        win.layout_actions[key].setIcon(theme.icon_named(name))


def ribbon_groups(win):
    """The ribbon's Reading tab (main_window._build_ribbon): its groups, with the shorter
    names the commands have on it."""
    for a, label in ((win.a_read_page, tr("This page")),
                     (win.a_read_from, tr("From selection")),
                     (win.a_read_doc, tr("Whole document")),
                     (win.a_read_pause, tr("Pause")), (win.a_read_stop, tr("Stop")),
                     (win.a_cover, tr("Cover page apart"))):
        a.setIconText(label)
    lay = win.layout_actions
    return [
        (tr("Screen"), "large", [win.a_full_screen, win.a_present]),
        (tr("Page layout"), "small", [lay["single"], lay["continuous"], lay["two"],
                                      lay["two_continuous"], win.a_cover]),
        (tr("Read"), "large", [win.a_reflow, win.a_autoscroll]),
        (tr("Read aloud"), "small", [win.a_read_page, win.a_read_from, win.a_read_doc,
                                     win.a_read_pause, win.a_read_stop]),
    ]


def add_to_view_menu(win, m):
    m.addAction(win.a_full_screen)
    m.addAction(win.a_present)
    lm = m.addMenu(tr("Page layout"))
    lm.addActions(list(win.layout_actions.values()))
    lm.addSeparator()
    lm.addAction(win.a_cover)
    m.addAction(win.a_reflow)
    rm = m.addMenu(tr("Read aloud"))
    rm.addActions([win.a_read_page, win.a_read_from, win.a_read_doc])
    rm.addSeparator()
    rm.addActions([win.a_read_pause, win.a_read_stop])
    m.addAction(win.a_autoscroll)


def sync(win):
    """The menu's ticks and what's enabled, for the document shown."""
    v = win.view() if hasattr(win, "tabs") else None
    has = v is not None
    for a in (win.a_full_screen, win.a_reflow):
        a.setEnabled(True)
    for a in [win.a_present, win.a_cover, win.a_read_page, win.a_read_from, win.a_read_doc,
              win.a_autoscroll] + list(win.layout_actions.values()):
        a.setEnabled(has)
    if has:
        win.layout_actions.get(v.page_layout, win.layout_actions["continuous"]).setChecked(True)
        win.a_cover.setChecked(v.cover_page)
    r = getattr(win, "_reader", None)
    speaking = r is not None and r.state != "stopped"
    win.a_read_pause.setEnabled(speaking)
    win.a_read_stop.setEnabled(speaking)
    auto = getattr(win, "_autoscroll", None)
    win.a_autoscroll.setChecked(auto is not None and auto.active)
    pane = getattr(win, "reading_dock", None)
    win.a_reflow.setChecked(pane is not None and pane.isVisible())
    win.a_full_screen.setChecked(getattr(win, "_full", None) is not None)


# ---- page layouts --------------------------------------------------------------------------
def set_layout(win, key):
    """key: a page layout, or None to switch the cover page option."""
    v = win.view()
    if v is None:
        return
    if key is None:
        v.set_page_layout(v.page_layout, win.a_cover.isChecked())
    else:
        v.set_page_layout(key)
    win._remember_state(v)
    sync(win)


# ---- full screen ---------------------------------------------------------------------------
class _TopBar(QFrame):
    """In full screen: a slim bar that comes down when the pointer touches the top edge."""

    def __init__(self, win):
        super().__init__(win)
        self.setObjectName("kz_fullscreen_bar")
        self.setAutoFillBackground(True)
        self.setFrameShape(QFrame.StyledPanel)
        row = QHBoxLayout(self)
        row.setContentsMargins(6, 2, 6, 2)
        row.setSpacing(2)
        from PySide6.QtWidgets import QMenu
        layouts = QMenu(self)
        layouts.addActions(list(win.layout_actions.values()))
        layouts.addSeparator()
        layouts.addAction(win.a_cover)
        for a in (win.a_prev_page, win.a_next_page, None, win.a_zoom_out, win.a_zoom_in,
                  win.a_fit_width, win.a_fit_page, None, layouts, win.a_reflow,
                  win.a_read_page, win.a_read_stop):
            if a is None:
                sep = QFrame()
                sep.setFrameShape(QFrame.VLine)
                row.addWidget(sep)
                continue
            b = QToolButton()
            if isinstance(a, QMenu):            # (the page layouts, in one button)
                b.setText(tr("Page layout"))
                b.setMenu(a)
                b.setPopupMode(QToolButton.InstantPopup)
            else:
                b.setDefaultAction(a)
                # (an icon where the command has one; the words where it doesn't)
                b.setToolButtonStyle(Qt.ToolButtonTextOnly if a.icon().isNull() else
                                     Qt.ToolButtonIconOnly)
            b.setAutoRaise(True)
            row.addWidget(b)
        row.addStretch(1)
        out = QToolButton()
        out.setText(tr("Exit full screen"))
        out.setToolTip(tr("Back to the window with its toolbars and panels (Escape)"))
        out.setAutoRaise(True)
        out.clicked.connect(lambda: leave_full_screen(win))
        row.addWidget(out)
        self.hide()

    def place(self):
        w = self.parentWidget()
        self.setGeometry(0, 0, w.width(), self.sizeHint().height())
        self.raise_()


class _FullScreen(QObject):
    """What full screen hid (to bring back) and the pointer watch for the top bar."""
    EDGE = 3            # px from the top of the screen that bring the bar down

    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.hidden = []
        self.was_max = win.isMaximized()
        self.was_full = win.isFullScreen()

    def enter(self):
        win = self.win
        # (the panels and toolbars as they are, put back exactly on the way out: shown again
        # one by one, a panel tabbed with another came back in front of it, at its width)
        self.state = win.saveState()
        widgets = [win.menuBar(), win.statusBar(), win.tabs.tabBar()]
        widgets += [t for t in win.findChildren(QToolBar) if t.parent() is win]
        widgets += [d for d in win.findChildren(QDockWidget) if d.parent() is win and
                    d.objectName() != "reading"]
        for w in widgets:
            if w.isVisible():
                self.hidden.append(w)
                w.hide()
        win.showFullScreen()
        bar = getattr(win, "_fs_bar", None)
        if bar is None:
            bar = win._fs_bar = _TopBar(win)
        QApplication.instance().installEventFilter(self)

    def leave(self):
        win = self.win
        QApplication.instance().removeEventFilter(self)
        bar = getattr(win, "_fs_bar", None)
        if bar is not None:
            bar.hide()
        reading = getattr(win, "reading_dock", None)
        keep = reading is not None and reading.isVisible()
        if not self.was_full:
            if self.was_max:
                win.showMaximized()
            else:
                win.showNormal()
        for w in self.hidden:
            if shiboken6.isValid(w) and not isinstance(w, (QToolBar, QDockWidget)):
                w.show()
        self.hidden = []
        win.restoreState(self.state)
        if keep and not reading.isVisible():
            reading.show()

    def eventFilter(self, obj, e):
        if e.type() == QEvent.KeyPress and e.key() == Qt.Key_Escape and \
                not e.modifiers() and self._escape_leaves(obj):
            # (Escape where the page doesn't get it, the Reading view or the top bar having
            # the focus: full screen is left all the same, as its tip says; on the page, the
            # tool is put down first: escape_on_page)
            QTimer.singleShot(0, lambda: leave_full_screen(self.win))
            return True
        if e.type() == QEvent.MouseMove and self.win.isActiveWindow():
            bar = getattr(self.win, "_fs_bar", None)
            if bar is not None:
                y = self.win.mapFromGlobal(QCursor.pos()).y()
                if not bar.isVisible() and y <= self.EDGE:
                    bar.place()
                    bar.show()
                elif bar.isVisible() and y > bar.height() + 24 and \
                        QApplication.activePopupWidget() is None:
                    bar.hide()
        return False


    def _escape_leaves(self, obj):
        """An Escape sent to obj leaves full screen: a widget of the window outside the
        document's page (the page has its own Escape), with no menu or list popped up."""
        from PySide6.QtWidgets import QWidget
        from .document_view import DocumentView
        if not isinstance(obj, QWidget) or obj.window() is not self.win or \
                QApplication.activePopupWidget() is not None:
            return False
        w = obj
        while w is not None:
            if isinstance(w, DocumentView):
                return False
            w = w.parentWidget()
        return True


def toggle_full_screen(win):
    if getattr(win, "_full", None) is None:
        enter_full_screen(win)
    else:
        leave_full_screen(win)


def enter_full_screen(win):
    if getattr(win, "_full", None) is not None:
        return
    win._full = _FullScreen(win)
    win._full.enter()
    win.statusBar().showMessage(tr("Full screen: Escape leaves it; the top edge has a bar"),
                                3000)
    sync(win)


def leave_full_screen(win):
    full = getattr(win, "_full", None)
    if full is None:
        return
    win._full = None
    full.leave()
    full.deleteLater()
    sync(win)


def escape_on_page(win):
    """Escape on the page with nothing to cancel: in full screen, once the tool is put
    down, it leaves full screen; otherwise it puts the tool down (back to the mouse mode's
    tool)."""
    if getattr(win, "_full", None) is not None and win.tool == win.default_tool():
        leave_full_screen(win)
        return
    win.set_tool(win.default_tool())


# ---- presentation --------------------------------------------------------------------------
def start_presentation(win):
    v = win.view()
    if v is None:
        return None
    old = getattr(win, "_presentation", None)
    if old is not None and shiboken6.isValid(old) and old.isVisible():
        # (F5 again in the window, the presentation on the other screen: that one is
        # brought forward, not a second one opened over it, which closing the window left
        # behind)
        old.raise_()
        old.activateWindow()
        return old
    from .presentation import Presentation
    screen = win.screen()
    p = Presentation(v, v.current_page(), screen)
    win._presentation = p

    def done(page):
        if getattr(win, "_presentation", None) is p:
            win._presentation = None
        if shiboken6.isValid(v) and not v.doc.is_closed:
            v.goto_page(page)
    p.finished.connect(done)
    p.start()
    return p


# ---- read aloud ----------------------------------------------------------------------------
def reader(win):
    r = getattr(win, "_reader", None)
    if r is None:
        from .read_aloud import Reader
        r = win._reader = Reader(win.settings, win)
        r.stateChanged.connect(lambda _s: sync(win))
        r.message.connect(lambda m: _reader_message(win, m))
    return r


def _reader_message(win, text):
    win.statusBar().showMessage(text, 6000)
    from .read_aloud import no_speech_message
    if text == no_speech_message():
        QMessageBox.information(win, tr("Read aloud"), text)


def read(win, what):
    """what: 'page' (this page), 'selection' (from the selected text, else from the top of
    this page, to the end) or 'document' (from the first page)."""
    v = win.view()
    if v is None:
        return False
    r = reader(win)
    if what == "document":
        return r.start(v, 0, to_end=True)
    page, start = v.current_page(), None
    if what == "selection" and v.text_sel:
        index, units = v.text_sel[0]
        if units:
            u = units[0]
            page, start = index, ((u[0] + u[2]) / 2, (u[1] + u[3]) / 2)
    return r.start(v, page, start, to_end=what == "selection")


# ---- auto scroll ---------------------------------------------------------------------------
class AutoScroll(QObject):
    """View > Auto scroll: the view moves down by itself, speed pixels a second. Up / Down
    change the speed (remembered), Escape stops."""
    TICK_MS = 30

    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.view = None
        self.active = False
        self.speed = paths.stored_int(win.settings, "autoscroll_speed", 40, 5, 2000)
        self._frac = 0.0
        self.timer = QTimer(self, interval=self.TICK_MS)
        self.timer.timeout.connect(self._tick)

    def start(self, view):
        self.stop()
        self.view = view
        self.active = True
        self._frac = 0.0
        view.installEventFilter(self)
        view.destroyed.connect(self._gone)
        self.timer.start()
        self._say()

    def stop(self):
        if self.view is not None and shiboken6.isValid(self.view):
            self.view.removeEventFilter(self)
            try:
                self.view.destroyed.disconnect(self._gone)
            except (RuntimeError, TypeError):
                pass
        self.view = None
        self.active = False
        self.timer.stop()
        sync(self.win)

    def _gone(self, *_):
        self.view = None
        self.stop()

    def _say(self):
        self.win.statusBar().showMessage(tr("Auto scroll: {speed} pixels a second (Up and Down "
                                            "change it, Escape stops)").format(
                                                speed=self.speed), 4000)

    def faster(self, factor):
        self.speed = int(max(5, min(2000, round(self.speed * factor))))
        self.win.settings.setValue("autoscroll_speed", self.speed)
        self._say()

    def _tick(self):
        v = self.view
        if v is None or not shiboken6.isValid(v):
            self.stop()
            return
        bar = v.verticalScrollBar()
        self._frac += self.speed * self.TICK_MS / 1000.0
        step = int(self._frac)
        if not step:
            return
        self._frac -= step
        if bar.value() >= bar.maximum():
            if not (v.paged() and v._paged_edge(True)):
                self.stop()             # (the end of the document)
            return
        bar.setValue(bar.value() + step)

    def eventFilter(self, obj, e):
        if e.type() == QEvent.KeyPress and obj is self.view:
            k = e.key()
            if k == Qt.Key_Escape:
                self.stop()
                return True
            if k in (Qt.Key_Up, Qt.Key_Down) and not e.modifiers():
                self.faster(1.25 if k == Qt.Key_Down else 0.8)
                return True
        return False


def autoscroll(win):
    a = getattr(win, "_autoscroll", None)
    if a is None:
        a = win._autoscroll = AutoScroll(win)
    return a


def toggle_autoscroll(win):
    a = autoscroll(win)
    v = win.view()
    if a.active or v is None:
        a.stop()
    else:
        a.start(v)
        v.setFocus()
    sync(win)


# ---- reading view (reflow) ---------------------------------------------------------------
class _Text(QTextBrowser):
    def __init__(self, pane):
        super().__init__()
        self.pane = pane
        self.setOpenLinks(False)
        self.setFrameShape(QFrame.NoFrame)

    def wheelEvent(self, e):
        if e.modifiers() & Qt.ControlModifier:
            dy = e.angleDelta().y()
            if dy:
                self.pane.bigger(1 if dy > 0 else -1)
            e.accept()
            return
        super().wheelEvent(e)


class ReadingPane(QWidget):
    """The page's text, reflowed: plain paragraphs at a size you choose, headings larger."""
    SIZES = (9, 10, 11, 12, 13, 14, 16, 18, 20, 22, 24, 28, 32, 36, 42, 48)

    def __init__(self, win):
        super().__init__()
        self.win = win
        self.size = paths.stored_int(win.settings, "reflow_size", 16, 9, 48)
        self._shown = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        row = QHBoxLayout()
        row.setContentsMargins(4, 2, 4, 2)
        self.label = QLabel()
        row.addWidget(self.label, 1)
        for text, tip, step in (("A−", tr("Smaller text (Ctrl+wheel)"), -1),
                                ("A+", tr("Larger text (Ctrl+wheel)"), 1)):
            b = QToolButton()
            b.setText(text)
            b.setToolTip(tip)
            b.setAutoRaise(True)
            b.clicked.connect(lambda _=False, s=step: self.bigger(s))
            row.addWidget(b)
        b = QToolButton()
        b.setDefaultAction(win.a_read_page)
        b.setAutoRaise(True)
        row.addWidget(b)
        lay.addLayout(row)
        self.text = _Text(self)
        lay.addWidget(self.text, 1)

    def bigger(self, step):
        sizes = self.SIZES
        k = min(range(len(sizes)), key=lambda i: abs(sizes[i] - self.size))
        self.size = sizes[max(0, min(len(sizes) - 1, k + step))]
        self.win.settings.setValue("reflow_size", self.size)
        self.refresh(force=True)

    def refresh(self, force=False):
        """Show the current page's text (again when force, or when the page changed)."""
        if not self.isVisible() and not force:
            return
        v = self.win.view()
        if v is None:
            self._shown = None
            self.label.setText("")
            self.text.setHtml("")
            return
        page = v.current_page()
        key = (id(v), page, getattr(v, "_gen", 0), self.size)
        if key == self._shown and not force:
            return
        self._shown = key
        from . import reading_text
        try:
            blocks = v.reading_blocks(page)
        except Exception:
            blocks = []
        self.label.setText(tr("Page {n} of {count}").format(n=page + 1, count=v.page_count()))
        if blocks:
            html = reading_text.page_html(blocks, self.size)
        else:
            html = "<p style='font-size:%gpt; color:gray;'>%s</p>" % (
                self.size, tr("There's no text on this page. A scanned page needs Recognize "
                              "text (OCR) first."))
        bar = self.text.verticalScrollBar()
        self.text.setHtml(html)
        bar.setValue(0)


class _ReadingDock(QDockWidget):
    def __init__(self, win):
        super().__init__(tr("Reading view"), win)
        self.win = win

    def closeEvent(self, e):
        super().closeEvent(e)
        put_away(self.win)          # (its close button)


def reading_pane(win):
    dock = getattr(win, "reading_dock", None)
    if dock is None:
        dock = win.reading_dock = _ReadingDock(win)
        dock.setObjectName("reading")
        dock.setFeatures(QDockWidget.DockWidgetClosable | QDockWidget.DockWidgetMovable |
                         QDockWidget.DockWidgetFloatable)
        win.reading_pane = ReadingPane(win)
        dock.setWidget(win.reading_pane)
        dock.hide()
        dock.visibilityChanged.connect(lambda on: (sync(win), on and win.reading_pane.refresh()))
    return dock


def _side_panels(win):
    """(dock, width) of the panels shown at the window's sides."""
    return [(d, d.width()) for d in win.findChildren(QDockWidget)
            if d.parent() is win and d.objectName() != "reading" and d.isVisible() and
            not d.isFloating() and win.dockWidgetArea(d) in (Qt.LeftDockWidgetArea,
                                                              Qt.RightDockWidgetArea)]


def show_reading(win):
    """The Reading view: a column of its own at the right, beside the panels there. It's in the
    window's panel layout only while shown, and the other panels get their widths back when
    it goes (in the layout while hidden, it was saved with the window's panels, and a window
    opened later restored that layout with the panels squeezed)."""
    dock = reading_pane(win)
    if dock.isVisible():
        return dock
    win._reading_beside = _side_panels(win)
    win.addDockWidget(Qt.RightDockWidgetArea, dock, Qt.Horizontal)
    dock.show()
    dock.raise_()
    width = paths.stored_int(win.settings, "reflow_width", 420, 200, 2000)
    win.resizeDocks([dock], [width], Qt.Horizontal)
    win.reading_pane.refresh(force=True)
    return dock


def put_away(win):
    """The Reading view closed: out of the panel layout, the other panels as they were."""
    dock = getattr(win, "reading_dock", None)
    if dock is None or not shiboken6.isValid(dock) or win.dockWidgetArea(dock) == \
            Qt.NoDockWidgetArea:
        return
    if dock.isVisible() or dock.width() > 1:
        win.settings.setValue("reflow_width", dock.width())
    dock.hide()
    win.removeDockWidget(dock)
    beside = [(d, w) for d, w in getattr(win, "_reading_beside", [])
              if shiboken6.isValid(d) and d.isVisible()]
    if beside:
        win.resizeDocks([d for d, _w in beside], [w for _d, w in beside], Qt.Horizontal)
    win._reading_beside = []
    sync(win)


def toggle_reflow(win):
    dock = reading_pane(win)
    if dock.isVisible():
        put_away(win)
    else:
        show_reading(win)
    sync(win)


def page_changed(win):
    """The page or the document shown changed: the Reading view follows."""
    pane = getattr(win, "reading_pane", None)
    if pane is not None and pane.isVisible():
        pane.refresh()


def window_closing(win):
    """Before the window saves its layout: out of full screen, reading and scrolling
    stopped."""
    leave_full_screen(win)
    r = getattr(win, "_reader", None)
    if r is not None:
        r.stop()
    a = getattr(win, "_autoscroll", None)
    if a is not None:
        a.stop()
    p = getattr(win, "_presentation", None)
    if p is not None and shiboken6.isValid(p):
        p.close()
    put_away(win)                   # (the Reading view isn't in the panel layout saved)
