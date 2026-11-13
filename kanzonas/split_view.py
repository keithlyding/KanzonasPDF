"""Split view (F10; 1.12 adds side by side, any open document and Sync): a second, read-only
view beside or under the documents, with a bar over it:

- which document it shows: the one in front (it follows the tabs, as before 1.12) or any
  other open one, to compare a plan with a detail sheet, or one revision with another;
- Side by side / Top and bottom;
- Sync, as Bluebeam's: panning and zooming either view moves the other the same way, "By page
  number" (the same page in both, as for two revisions of a set) or "By the pages in view"
  (the two pages shown when Sync was turned on stay paired, as for a plan and its detail);
- Close.

The second view is DocumentView.mirror of the chosen document's view: for looking (edits are
made in the main view, and show in both). Sync works on positions: the page at the middle of
the window, where on it (fractions of its width and height) and the zoom (sync_anchor), so it
pairs pages of different sizes and documents of different lengths."""

from PySide6.QtCore import QPoint, QSignalBlocker, QTimer, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QHBoxLayout, QSizePolicy,
                               QToolButton, QVBoxLayout, QWidget)

from .i18n import tr

FRONT = "front"


def sync_anchor(v):
    """(page, x fraction, y fraction, zoom): the page at the middle of view v's window and
    where on that page the middle is; None without pages."""
    pages = getattr(v, "pages", None)
    if not pages or v.widget() is None:
        return None
    vp = v.viewport()
    mid = v.widget().mapFrom(vp, vp.rect().center())
    cur = v.current_page()
    best, dist = cur, None
    for i in range(max(0, cur - 2), min(len(pages), cur + 3)):     # (the middle is near it)
        g = pages[i].geometry()
        d = 0 if g.contains(mid) else abs(g.center().y() - mid.y()) + abs(g.center().x() - mid.x())
        if dist is None or d < dist:
            best, dist = i, d
    pw = pages[best]
    a = pw.page_area()
    local = pw.mapFrom(v.widget(), mid)
    return (best, (local.x() - a.x()) / max(1.0, a.width()),
            (local.y() - a.y()) / max(1.0, a.height()), v.zoom)


def go_to_anchor(v, page, fx, fy, zoom=None):
    """Show page's point (fx, fy) (fractions of the page) at the middle of view v's window,
    at zoom (None: as it is)."""
    if not getattr(v, "pages", None):
        return
    if zoom is not None and abs(zoom - v.zoom) > 1e-4:
        v.set_zoom(zoom)
    page = max(0, min(page, len(v.pages) - 1))
    v._show_index(page)
    pw = v.pages[page]
    a = pw.page_area()
    pt = pw.mapTo(v.widget(), a.topLeft().toPoint()) + \
        QPoint(int(fx * a.width()), int(fy * a.height()))
    vp = v.viewport()
    v.horizontalScrollBar().setValue(int(pt.x() - vp.width() / 2))
    v.verticalScrollBar().setValue(int(pt.y() - vp.height() / 2))


class SplitPane(QWidget):
    """The second view and its bar. The window keeps it hidden until Split view is on."""
    visibilityChanged = Signal(bool)
    sourceChanged = Signal()        # the document chosen in its list changed
    orientationChanged = Signal()

    def __init__(self, win):
        super().__init__()
        self.win = win
        self.view = None            # the second view (DocumentView.mirror)
        self._link = None           # (main view, second view, page offset, zoom ratio)
        self._quiet = set()         # views being moved by Sync: their own signals are echoes
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        bar = QWidget()
        bar.setObjectName("splitBar")
        h = QHBoxLayout(bar)
        h.setContentsMargins(6, 2, 2, 2)
        self.doc_box = QComboBox()
        self.doc_box.setToolTip(tr("The document the second view shows: the one in front, or "
                                   "any other open one"))
        self.doc_box.activated.connect(lambda _i: self.sourceChanged.emit())
        self.side = QToolButton()
        self.side.setCheckable(True)
        self.side.setAutoRaise(True)
        self.side.setText(tr("Side by side"))
        self.side.setToolTip(tr("Show the second view beside the documents (on) or under "
                                "them (off)"))
        self.side.toggled.connect(lambda _on: self.orientationChanged.emit())
        self.sync = QCheckBox(tr("Sync"))
        self.sync.setToolTip(tr("Pan and zoom both views together"))
        self.sync_mode = QComboBox()
        self.sync_mode.addItem(tr("By page number"), "number")
        self.sync_mode.addItem(tr("By the pages in view"), "view")
        self.sync_mode.setToolTip(tr("By page number: the same page in both. By the pages in "
                                     "view: the two pages shown now stay paired (a plan and "
                                     "its detail)"))
        self.sync.toggled.connect(self._sync_toggled)
        self.sync_mode.activated.connect(lambda _i: self._relink())
        close = QToolButton()
        close.setAutoRaise(True)
        close.setText("✕")
        close.setToolTip(tr("Close the split view (F10)"))
        close.clicked.connect(self._close)
        h.addWidget(self.doc_box, 1)
        for w in (self.side, self.sync, self.sync_mode, close):
            h.addWidget(w)
        # (side by side, each half of the window can be narrow: the lists shrink to a few
        # letters rather than hold the halves apart; opened, they show everything)
        for box in (self.doc_box, self.sync_mode):
            box.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
            box.setMinimumContentsLength(6)
        lay.addWidget(bar)
        self.holder = QWidget()
        QVBoxLayout(self.holder).setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.holder, 1)

    def _close(self):
        self.win.a_split.setChecked(False)
        self.win._toggle_split()

    # (the window's checks and tests treat it as the old dock was)
    def setWindowTitle(self, text):
        super().setWindowTitle(text)
        self.doc_box.setToolTip(text + "\n" + tr("The document the second view shows: the "
                                                  "one in front, or any other open one"))

    def showEvent(self, e):
        super().showEvent(e)
        self.visibilityChanged.emit(True)

    def hideEvent(self, e):
        super().hideEvent(e)
        if not self.window().isMinimized():
            self.visibilityChanged.emit(False)

    # ---- which document ------------------------------------------------------------------
    def fill_documents(self, views, names, chosen):
        """The list: "The document in front", then each open document."""
        with QSignalBlocker(self.doc_box):
            self.doc_box.clear()
            self.doc_box.addItem(tr("The document in front"), FRONT)
            for v, name in zip(views, names):
                self.doc_box.addItem(name, id(v))
            at = self.doc_box.findData(id(chosen) if chosen is not None else FRONT)
            self.doc_box.setCurrentIndex(max(0, at))

    def chosen(self):
        """FRONT, or the id() of the open document chosen."""
        return self.doc_box.currentData() or FRONT

    def set_view(self, sv):
        old, self.view = self.view, sv
        self._unlink()
        if old is not None:
            # (out of the pane at once: deleteLater waits for the event loop)
            old.hide()
            self.holder.layout().removeWidget(old)
            old.deleteLater()
        if sv is not None:
            self.holder.layout().addWidget(sv)
        self._relink()

    # ---- Sync -----------------------------------------------------------------------------
    def _sync_toggled(self, _on):
        self._relink()

    def _relink(self):
        """Pair the two views as they are now (Sync on), or let them go."""
        self._unlink()
        main = self.win.view()
        sv = self.view
        if not self.sync.isChecked() or main is None or sv is None:
            return
        a, b = sync_anchor(main), sync_anchor(sv)
        if a is None or b is None:
            return
        if self.sync_mode.currentData() == "number":
            offset, ratio = 0, 1.0
        else:
            offset, ratio = b[0] - a[0], b[3] / max(1e-6, a[3])
        self._link = (main, sv, offset, ratio)
        # (each view's own slot: which view moved is known without asking Qt for the sender,
        # whose Python wrapper can be a new one, not equal to the one kept)
        self._conns = []
        for v in (main, sv):
            slot = (lambda *_a, v=v: self._moved(v))
            for sig in (v.horizontalScrollBar().valueChanged, v.verticalScrollBar().valueChanged,
                        v.zoomChanged):
                sig.connect(slot)
                self._conns.append((sig, slot))
        if offset == 0 and ratio == 1.0:
            self._follow(main)              # (by page number: the second view lines up now)

    def _unlink(self):
        if self._link is None:
            return
        for sig, slot in getattr(self, "_conns", ()):
            try:
                sig.disconnect(slot)
            except (RuntimeError, TypeError):
                pass  # (not connected, or already gone)
        self._conns = []
        self._link = None

    def linked(self):
        return self._link is not None

    def _moved(self, src):
        if self._link is None or src in self._quiet:
            return
        self._follow(src)

    def _follow(self, src):
        """The other view goes where src is (with the page offset and zoom ratio)."""
        if self._link is None:
            return
        main, sv, offset, ratio = self._link
        a = sync_anchor(src)
        if a is None:
            return
        page, fx, fy, zoom = a
        if src is main:
            dst, page, zoom = sv, page + offset, zoom * ratio
        else:
            dst, page, zoom = main, page - offset, zoom / ratio
        self._quiet.add(dst)
        try:
            go_to_anchor(dst, page, fx, fy, zoom)
        finally:
            # (a zoom lays the pages out again, and its scroll signals come after this: the
            # moved view's echoes are let go of a little later, so they don't move src back)
            QTimer.singleShot(120, lambda d=dst: self._quiet.discard(d))
