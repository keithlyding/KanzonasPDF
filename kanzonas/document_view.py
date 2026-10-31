"""Scrolling view of one open document, plus every editing operation on it."""

import json
import math
import os
import re
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor

import pymupdf
from PySide6.QtCore import Qt, Signal, QTimer, QObject, QEvent, QPointF, QRectF
from PySide6.QtGui import (QColor, QGuiApplication, QPixmap, QPainter, QPen, QCursor, QImage)
from PySide6.QtWidgets import (QScrollArea, QWidget, QVBoxLayout, QInputDialog,
                               QMessageBox, QLineEdit, QProgressDialog, QApplication,
                               QMenu, QPlainTextEdit, QHBoxLayout, QLabel, QPushButton)

from . import annotations, dialogs, signatures, text_edit
from .i18n import tr
from .inline_editor import InlineEditor
from .page_widget import PageWidget

PAGE_GAP = 12
MIN_ZOOM, MAX_ZOOM = 0.1, 64.0     # 10% to 6400%, the same ceiling as Acrobat and PDF-XChange
# Qt refuses a widget larger than this on one side. A normal page still reaches 6400%;
# an oversized sheet stops a little earlier so the window can still hold it.
WIDGET_PX = 16_000_000
UNDO_LIMIT = 30
# Undo keeps whole-document copies, so the history also has a memory budget: per document,
# and for all open documents together (the oldest steps go first; the latest is always kept)
UNDO_BYTES_PER_DOC = 256 * 1024 * 1024
UNDO_BYTES_TOTAL = 512 * 1024 * 1024
PAGE_CACHE_PAGES = 24     # parsed per-page data kept for at most about this many pages


_ERASER_CURSOR = None


def disk_stamp(path):
    """(modified time, size) of a file, to notice when it has changed on disk; None when it
    can't be read."""
    try:
        st = os.stat(path)
    except OSError:
        return None
    return st.st_mtime_ns, st.st_size


def eraser_cursor():
    """A drawn eraser icon; the hotspot is the bottom-left tip that does the erasing."""
    global _ERASER_CURSOR
    if _ERASER_CURSOR is None:
        pm = QPixmap(32, 32)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        p.translate(16, 16)
        p.rotate(-45)
        p.setPen(QPen(QColor(40, 40, 40), 1.5))
        p.setBrush(QColor(240, 110, 130))
        p.drawRoundedRect(QRectF(-4, -6, 16, 12), 2, 2)     # pink rubber body
        p.setBrush(QColor(250, 250, 250))
        p.drawRoundedRect(QRectF(-12, -6, 8, 12), 2, 2)     # white tip
        p.end()
        _ERASER_CURSOR = QCursor(pm, 6, 26)
    return _ERASER_CURSOR



def link_border(doc, xref):
    """(width, (r, g, b), style) of a link's visible border, or None when it has none.
    style: "S" solid, "D" dashed, "U" underline."""
    if not xref:
        return None
    try:
        kind, w = doc.xref_get_key(xref, "BS/W")
        width = float(w) if kind in ("int", "float") else None
        if width is None:
            kind, arr = doc.xref_get_key(xref, "Border")
            nums = arr.strip("[]").split() if kind == "array" else []
            width = float(nums[2]) if len(nums) >= 3 else 0.0
        if width <= 0:
            return None
        kind, c = doc.xref_get_key(xref, "C")
        rgb = tuple(float(v) for v in c.strip("[]").split()) if kind == "array" else (0, 0, 0)
        if len(rgb) != 3:
            rgb = (0, 0, 0)
        style = doc.xref_get_key(xref, "BS/S")[1].lstrip("/") or "S"
        return width, rgb, style if style in ("S", "D", "U") else "S"
    except (ValueError, IndexError, RuntimeError):
        return None

class _busy:
    """The busy pointer while a command works (most take a fraction of a second; on a huge
    drawing it shows the program is at it)."""

    depth = 0

    def __enter__(self):
        _busy.depth += 1
        QApplication.setOverrideCursor(Qt.WaitCursor)

    def __exit__(self, *exc):
        _busy.depth -= 1
        QApplication.restoreOverrideCursor()
        return False


_JS_ACTION = re.compile(r"/S\s*/(JavaScript|Launch)\b")    # (Launch: runs a program)


def remove_scripts(doc):
    """Take every JavaScript action, Launch action (runs a program) and automatic action
    out of doc. PyMuPDF's scrub empties
    the JavaScript actions stored as objects of their own; one written straight into a
    catalog's /OpenAction, an /AA or a link's /A (a common way) stays, so this removes those
    too: /AA (actions run on opening, closing, printing, page visits...) goes wherever it is,
    an /OpenAction or /A only when it is (or leads to) JavaScript, and the document-level
    scripts (the /JavaScript name tree) go."""
    for xref in range(1, doc.xref_length()):
        try:
            keys = doc.xref_get_keys(xref)
        except Exception:
            continue
        if "AA" in keys:
            doc.xref_set_key(xref, "AA", "null")
        for key in ("OpenAction", "A"):
            if key not in keys:
                continue
            kind, val = doc.xref_get_key(xref, key)
            if kind == "xref":
                try:
                    val = doc.xref_object(int(val.split()[0]))
                except Exception:
                    continue
            if kind in ("dict", "xref") and (_JS_ACTION.search(val) or "/Next" in val and
                                              "JavaScript" in val):
                doc.xref_set_key(xref, key, "null")
        if "Names" in keys and doc.xref_get_key(xref, "Names/JavaScript")[0] != "null":
            doc.xref_set_key(xref, "Names/JavaScript", "null")


def blank_appearance(doc, widget_xref):
    """Make an emptied text / choice field look empty. PyMuPDF doesn't redraw a field set
    to "" (its old text stayed on the page and in the file), so the field's normal
    appearance is written over with an empty one."""
    kind, val = doc.xref_get_key(widget_xref, "AP/N")
    if kind == "xref":
        doc.update_stream(int(val.split()[0]), b"/Tx BMC\nEMC\n")


def clear_form_data(doc):
    """Empty every form field (Sanitize > Data typed into form fields). The value is kept on
    the field, which is often a parent dictionary above the widget (KanzonasPDF's own fields
    since PyMuPDF 2.0, many Acrobat forms): PyMuPDF's scrub resets only the widget, so the
    value stayed in the file. Each widget is emptied through PyMuPDF (new appearance), then
    every field dictionary loses its /V."""
    for i in range(doc.page_count):
        page = doc[i]
        for w in list(page.widgets() or []):
            t = w.field_type
            try:
                if t in (pymupdf.PDF_WIDGET_TYPE_CHECKBOX, pymupdf.PDF_WIDGET_TYPE_RADIOBUTTON):
                    w.field_value = False
                elif t in (pymupdf.PDF_WIDGET_TYPE_TEXT, pymupdf.PDF_WIDGET_TYPE_COMBOBOX,
                           pymupdf.PDF_WIDGET_TYPE_LISTBOX):
                    w.field_value = ""
                else:
                    continue
                w.update()
                if t != pymupdf.PDF_WIDGET_TYPE_CHECKBOX and \
                        t != pymupdf.PDF_WIDGET_TYPE_RADIOBUTTON:
                    blank_appearance(doc, w.xref)
            except Exception:
                pass
    for xref in range(1, doc.xref_length()):
        try:
            keys = doc.xref_get_keys(xref)
        except Exception:
            continue
        if "V" in keys and ("FT" in keys or "T" in keys or "Kids" in keys):
            doc.xref_set_key(xref, "V", "null")
            if "RV" in keys:
                doc.xref_set_key(xref, "RV", "null")


class _not_busy:
    """A message box while a command works: the usual pointer over it, the busy one after."""

    def __enter__(self):
        self.n = _busy.depth
        for _ in range(self.n):
            QApplication.restoreOverrideCursor()

    def __exit__(self, *exc):
        for _ in range(self.n):
            QApplication.setOverrideCursor(Qt.WaitCursor)
        return False


class DocumentView(QScrollArea):
    _orig_data = None               # original file bytes (signed / protected files only)
    _orig_enc = None                # original protection, to keep it when saving edits
    pageChanged = Signal(int)
    documentChanged = Signal()      # content edited (thumbnails / title need refresh)
    structureChanged = Signal()     # pages added / removed / reordered / rotated
    zoomChanged = Signal(float)
    statusMessage = Signal(str)
    searchChanged = Signal(int, int, bool)   # match shown (1-based, 0 = none), matches, still searching
    openFileRequested = Signal(str, int)      # a link to another PDF: path, page (0-based)
    selectionChanged = Signal()
    signedDocument = Signal()
    oneShotPlaced = Signal()        # a signature / initials / date was placed
    selectToolRequested = Signal()
    previousToolRequested = Signal()    # Escape: back to the default tool (Hand or Select)
    calibrateRequested = Signal(int, float)    # page index, drawn length in points
    scaleChanged = Signal()
    layersChanged = Signal()
    requestSignature = Signal(int, int)      # page index, signature field xref
    textToolPropsChanged = Signal()          # Edit text: the line's font / size to show

    def __init__(self, path, parent=None, doc=None):
        """doc: a new document not yet saved (File > New PDF); path is then the name Save
        suggests, and Save asks where to save it (see untitled)."""
        super().__init__(parent)
        self.path = os.path.abspath(path)
        self.untitled = doc is not None
        # the file as it was read, to notice a newer one (see MainWindow.open_file)
        self.disk_stamp = None if doc is not None else disk_stamp(self.path)
        if doc is not None:
            data = None
            self.doc = doc
        else:
            # Load from memory so the file is not locked on Windows and can be overwritten
            # on save.
            with open(self.path, "rb") as f:
                data = f.read()
            self.doc = pymupdf.open(stream=data, filetype="pdf")
        # Keep what's needed to save without losing the file's protection or signatures:
        # the original bytes (an unchanged file is saved as an exact copy) and its encryption.
        self._orig_data = data
        self._orig_enc = None
        if (self.doc.metadata or {}).get("encryption") or self.doc.needs_pass:
            self._orig_enc = {"needs_pass": bool(self.doc.needs_pass), "user_pw": None,
                              "owner_pw": None}
        if self.doc.needs_pass:
            pw, ok = QInputDialog.getText(self, tr("Password required"),
                                          tr("{name} is protected:").format(
                                              name=os.path.basename(path)),
                                          QLineEdit.Password)
            rc = self.doc.authenticate(pw) if ok else 0
            if not rc:
                raise ValueError(tr("Wrong or missing password"))
            if rc & 2:
                self._orig_enc["user_pw"] = pw
            if rc & 4:
                self._orig_enc["owner_pw"] = pw
        if self.doc.page_count == 0:
            raise ValueError(tr("The PDF has no pages"))
        if self._orig_enc is not None:
            self._orig_enc["perms"] = self.doc.permissions
        try:
            signed = self.doc.get_sigflags() >= 1
        except Exception:
            signed = False
        if self._orig_enc is None and not signed:
            self._orig_data = None          # plain file: no need to keep a second copy
        self._owner_authorized = self._orig_enc is None or bool(self._orig_enc.get("owner_pw"))
        self._check_permissions()
        self._init_state()
        self._build_pages()
        self._fitted = False

    def _init_state(self):
        self.dirty = False
        self.zoom = 1.0
        self.tool = "select"
        self.selection = None          # (page index, annotation xref): the first one selected
        self.selected_model = None
        self.extra = []                # more selected xrefs on the same page, in click order
        self.show_comment_boxes = True
        self._inline = None
        self.sig_images = {}           # kind -> (png bytes, QPixmap)
        self._stamp_cache = {}
        self.signed = False
        self.security = None           # new security to apply when saving (see set_security)
        self.search_hits = {}
        self._search_list = []
        self._search_pos = -1
        self._search_text = None
        self._search_cur = None         # (page, match) shown now
        self._search_todo = None        # pages still to search (a search runs in slices)
        self._search_gen = 0            # bumped to stop a running search
        self._undo = []
        self._redo = []
        self._pan_origin = None
        self._clear_caches()
        self._fonts_added = False
        self._last_page = -1
        self.setWidgetResizable(False)
        self.setAlignment(Qt.AlignHCenter)
        self.setStyleSheet("QScrollArea { background: #525659; border: none; }")
        self.verticalScrollBar().valueChanged.connect(self._on_scroll)

    # ---- page layout ----------------------------------------------------
    def page_count(self):
        return self.doc.page_count

    def _build_pages(self):
        keep = self.verticalScrollBar().value()
        self.page_rects = [p.rect for p in self.doc]
        if self.zoom > self._zoom_cap():        # pages added at a high zoom: they must fit
            self.zoom = self._zoom_cap()
            self.zoomChanged.emit(self.zoom)
        old = getattr(self, "pages", None)
        lay = self.widget().layout() if old and self.widget() is not None else None
        if lay is not None:
            # reuse the page widgets: renumber them and add or remove the difference
            n = self.doc.page_count
            for w in old[n:]:
                lay.removeWidget(w)
                w.hide()                # not painted again before deleteLater runs
                w.deleteLater()
            del old[n:]
            for i, w in enumerate(old):
                w.reuse(i)
            for i in range(len(old), n):
                w = PageWidget(self, i)
                lay.addWidget(w, 0, Qt.AlignHCenter)
                old.append(w)
            self.widget().adjustSize()
            self.verticalScrollBar().setValue(keep)
            return
        container = QWidget()
        container.setStyleSheet("background: #525659;")
        lay = QVBoxLayout(container)
        lay.setSpacing(PAGE_GAP)
        lay.setContentsMargins(PAGE_GAP, PAGE_GAP, PAGE_GAP, PAGE_GAP)
        self.pages = []
        for i in range(self.doc.page_count):
            w = PageWidget(self, i)
            lay.addWidget(w, 0, Qt.AlignHCenter)
            self.pages.append(w)
        self.setWidget(container)
        self._canvas_margin = (PAGE_GAP, PAGE_GAP)
        self.apply_canvas()
        container.adjustSize()
        self.verticalScrollBar().setValue(keep)

    def center_horizontally(self, index=None):
        """Scroll sideways so the page is centered in the window (needed in CAD mouse mode,
        where open canvas lies left and right of the pages)."""
        if not getattr(self, "pages", None):
            return
        w = self.pages[self.current_page() if index is None else index]
        bar = self.horizontalScrollBar()
        bar.setValue(int(w.x() + w.width() / 2 - self.viewport().width() / 2))

    def apply_canvas(self):
        """CAD mouse mode or Free page movement: open canvas about a window wide around the
        pages, so the drawing can be dragged anywhere, even when it fits in the window (as in
        Bluebeam). The view stays where it was when the margin changes."""
        lay = self.widget().layout() if self.widget() is not None else None
        if lay is None:
            return
        vp = self.viewport()
        if self.free_pan:
            mx = max(PAGE_GAP, int(vp.width() * 0.9))
            my = max(PAGE_GAP, int(vp.height() * 0.9))
        else:
            mx = my = PAGE_GAP
        old = getattr(self, "_canvas_margin", (PAGE_GAP, PAGE_GAP))
        if (mx, my) == old:
            return
        h, v = self.horizontalScrollBar(), self.verticalScrollBar()
        hv, vv = h.value(), v.value()
        self._canvas_margin = (mx, my)
        lay.setContentsMargins(mx, my, mx, my)
        self.widget().adjustSize()
        h.setValue(hv + mx - old[0])
        v.setValue(vv + my - old[1])

    def _relayout(self):
        for w in self.pages:
            w.update_size()
        self.widget().adjustSize()

    def _on_scroll(self, *_):
        cur = self.current_page()
        if cur != self._last_page:
            old = self._last_page
            self._last_page = cur
            if 0 <= old < len(self.pages):
                self.pages[old].update()
            if 0 <= cur < len(self.pages):
                self.pages[cur].update()
            self.pageChanged.emit(cur)
            self._cad_prepare_soon()
        # Free rendered bitmaps for pages far from the viewport to keep memory low. Only the
        # pages that hold one are visited, so scrolling costs the same on 10 or 10,000 pages.
        lo, hi = max(0, cur - 4), cur + 6
        for i in [i for i in self._pix_pages if i < lo or i > hi]:
            self._pix_pages.discard(i)
            if i < len(self.pages):
                self.pages[i].drop_cache()
        self._trim_page_caches(cur)

    def _trim_page_caches(self, cur):
        """Forget parsed data (drawings, text, snap points, objects) for pages far from the
        current one, so a long session over a big file doesn't keep every page it visited."""
        keep = {cur}
        if self.text_sel:
            for i, _words in self.text_sel:
                keep.add(i)
        if self._text_drag:
            for i, _mode, _words in self._text_drag:
                keep.add(i)
        if self.obj_sel:
            keep.add(self.obj_sel[0])
        for cache in (self._dlists, self._line_cache, self._row_cache, self._hover_para,
                      self._word_cache, self._snap_markups, self._obj_cache,
                      self._snap_content):
            if len(cache) <= PAGE_CACHE_PAGES:
                continue
            for i in [i for i in cache
                      if abs(i - cur) > PAGE_CACHE_PAGES // 2 and i not in keep]:
                del cache[i]

    def current_page(self):
        if not getattr(self, "pages", None):
            return 0
        mid = self.verticalScrollBar().value() + self.viewport().height() // 3
        pages = self.pages
        # pages are stacked top to bottom: binary-search for the first one reaching mid
        lo, hi = 0, len(pages)
        while lo < hi:
            m = (lo + hi) // 2
            w = pages[m]
            if w.y() + w.height() + PAGE_GAP // 2 >= mid:
                hi = m
            else:
                lo = m + 1
        return min(lo, len(pages) - 1)

    def goto_page(self, index, y_offset=0):
        index = max(0, min(index, len(self.pages) - 1))
        self.verticalScrollBar().setValue(self.pages[index].y() - PAGE_GAP + int(y_offset))
        self._on_scroll()

    def showEvent(self, e):
        super().showEvent(e)
        if not self._fitted:
            self._fitted = True
            QTimer.singleShot(0, self._initial_view)

    def _initial_view(self):
        if not self.isVisible():
            # its tab went to the back before this ran (several files opened at once): the
            # page layout isn't updated while hidden, so wait until the tab is shown again
            self._fitted = False
            return
        state = getattr(self, "initial_state", None)
        page = int(state.get("page", 0)) if state and self.reopen_page else 0
        mode = self.open_view
        if mode == "last" and state:
            self.set_zoom(float(state.get("zoom", 1.0)))
        elif mode == "width" or mode == "last":
            self.fit_width()
        elif mode == "actual":
            self.set_zoom(1.0)
        if mode == "page":
            self.goto_page(page)
            self.fit_page()
        else:
            self.goto_page(page)
            self.center_horizontally(page)

    @classmethod
    def mirror(cls, other):
        """A second, read-only view onto another view's document (split view)."""
        self = cls.__new__(cls)
        QScrollArea.__init__(self)
        self.path = other.path
        self.untitled = other.untitled
        self.doc = other.doc
        self._init_state()
        self.read_only = True
        self.sig_results = []
        self._source = other
        self._build_pages()
        self._fitted = False
        other.documentChanged.connect(self._mirror_changed)
        other.structureChanged.connect(self._mirror_structure)
        return self

    def _mirror_changed(self):
        for w in self.pages:
            w.invalidate()

    def _mirror_structure(self):
        page = self.current_page()
        self.doc = self._source.doc            # undo/redo replaces the document object
        self._clear_caches()
        self._build_pages()
        self.goto_page(min(page, self.doc.page_count - 1))

    # ---- zoom -------------------------------------------------------------
    fit_mode = None     # "width" / "page" while the zoom follows the window size

    def _zoom_cap(self):
        """Highest zoom for this file: 6400%, or less when a page, or all the pages stacked
        one under the other, would exceed Qt's widget size."""
        cap = MAX_ZOOM
        rects = getattr(self, "page_rects", None) or []
        for r in rects:
            side = max(r.width, r.height, 1)
            cap = min(cap, WIDGET_PX / side)
        if rects:
            tall = sum(r.height for r in rects)
            cap = min(cap, (WIDGET_PX - (len(rects) + 1) * PAGE_GAP) / max(tall, 1))
        return max(MIN_ZOOM, cap)

    def set_zoom(self, z, keep_fit=False):
        if not keep_fit:
            self.fit_mode = None       # a chosen zoom stays put when the window resizes
        z = max(MIN_ZOOM, min(self._zoom_cap(), z))
        if abs(z - self.zoom) < 1e-4:
            return
        vbar = self.verticalScrollBar()
        page = self.current_page()
        w = self.pages[page]
        frac = (vbar.value() - w.y()) / max(1, w.height())
        self.zoom = z
        self._relayout()
        w = self.pages[page]
        vbar.setValue(int(w.y() + frac * w.height()))
        self.zoomChanged.emit(z)

    def zoom_in(self):
        self.set_zoom(self.zoom * 1.2)

    def zoom_out(self):
        self.set_zoom(self.zoom / 1.2)

    def fit_width(self):
        widest = max((r.width for r in self.page_rects), default=612)
        avail = self.viewport().width() - 2 * PAGE_GAP - 4
        if not self.verticalScrollBar().isVisible():
            avail -= self.verticalScrollBar().sizeHint().width()
        self.set_zoom(avail / widest, keep_fit=True)
        self.fit_mode = "width"
        self.center_horizontally()

    def fit_page(self):
        r = self.page_rects[self.current_page()]
        avail_w = self.viewport().width() - 2 * PAGE_GAP
        avail_h = self.viewport().height() - 2 * PAGE_GAP
        page = self.current_page()
        self.set_zoom(min(avail_w / r.width, avail_h / r.height), keep_fit=True)
        self.fit_mode = "page"
        self.show_whole_page(page)

    highlight_fields = True        # shade fillable form fields (View / Forms menu)
    show_markups = True            # Review > Show markups (off: the page as if unmarked)

    def redraw_pages(self):
        """Draw every page again from its display list (after a display option changed, such
        as night mode); selections, search hits and caches of the page text are kept."""
        self._tiles.clear()
        for i in list(getattr(self, "_pix_pages", ())):
            if i < len(self.pages):
                self.pages[i].drop_cache()
        self._pix_pages = set()
        for pw in self.pages:
            pw.update()

    def refresh_markup_display(self):
        self.clear_selection()
        self._clear_caches()
        for pw in self.pages:
            pw.invalidate()

    # ---- objects: lock, hide, list (Objects panel) ---------------------------------------------
    def page_objects(self, index):
        """[(xref, label, locked, hidden)] for a page's markups, front (top) to back."""
        page = self.doc[index]
        order = annotations.annot_order(page)
        info = {}
        for an in annotations.each_annot(page):
            if an.type[0] == pymupdf.PDF_ANNOT_POPUP:
                continue
            m = annotations.read(an)
            name = annotations.LABELS.get(m["kind"], an.type[1]) if m else an.type[1]
            text = (an.info.get("content", "") or "").replace("\n", " ").strip()
            who = an.info.get("title", "")
            label = name + (f": {text[:40]}" if text else "") + (f"  ({who})" if who else "")
            f = an.flags or 0
            info[an.xref] = (an.xref, label, bool(f & pymupdf.PDF_ANNOT_IS_LOCKED),
                             bool(f & pymupdf.PDF_ANNOT_IS_HIDDEN))
        ordered = [info[x] for x in order if x in info] + [v for x, v in info.items() if x not in order]
        return list(reversed(ordered))

    def set_object_flags(self, index, xrefs, locked=None, hidden=None):
        """Lock / unlock and hide / show markups (one undo step)."""
        def do():
            pg = self.doc[index]
            for x in xrefs:
                a = pg.load_annot(x)
                f = a.flags or 0
                if locked is not None:
                    f = f | pymupdf.PDF_ANNOT_IS_LOCKED if locked else f & ~pymupdf.PDF_ANNOT_IS_LOCKED
                if hidden is not None:
                    f = f | pymupdf.PDF_ANNOT_IS_HIDDEN if hidden else f & ~pymupdf.PDF_ANNOT_IS_HIDDEN
                a.set_flags(f)
                a.update()
        if locked or hidden:
            self.clear_selection()
        self.modify(do, [index], permission=pymupdf.PDF_PERM_ANNOTATE)

    def lock_selected(self):
        if self.selection is None:
            return 0
        index, xrefs = self.selection[0], self.selected_xrefs()
        self.set_object_flags(index, xrefs, locked=True)
        return len(xrefs)

    def unlock_all(self):
        locked = {i: [x for x, _l, lk, _h in self.page_objects(i) if lk]
                  for i in range(self.doc.page_count)}
        locked = {i: x for i, x in locked.items() if x}
        if not locked:
            return 0

        def do():
            for i, xrefs in locked.items():
                pg = self.doc[i]
                for x in xrefs:
                    a = pg.load_annot(x)
                    a.set_flags((a.flags or 0) & ~pymupdf.PDF_ANNOT_IS_LOCKED)
                    a.update()
        self.modify(do, list(locked), permission=pymupdf.PDF_PERM_ANNOTATE)
        return sum(len(x) for x in locked.values())

    # ---- review: walk through, delete, flatten comments ---------------------------------------
    def review_items(self):
        """[(page, xref)] of every markup in reading order (page, then top to bottom)."""
        out = []
        for i in range(self.doc.page_count):
            # cached per page (cleared when the page changes): Next comment on a long
            # document used to reload every markup on every key press
            key = ("review", i)
            order = self._card_cache.get(key)
            if order is None:
                pg = self.doc[i]
                items = []
                for an in annotations.each_annot(pg):
                    if an.type[0] == pymupdf.PDF_ANNOT_POPUP or (an.flags or 0) & (
                            pymupdf.PDF_ANNOT_IS_LOCKED | pymupdf.PDF_ANNOT_IS_HIDDEN):
                        continue
                    r = an.rect * pg.rotation_matrix
                    items.append((round(r.y0 / 6), r.x0, an.xref))
                order = self._card_cache[key] = [x for _y, _x, x in sorted(items)]
            out += [(i, x) for x in order]
        return out

    def goto_markup(self, step):
        """Select the next (step=1) or previous (step=-1) markup, wrapping around."""
        if not self.show_markups:
            self.statusMessage.emit(tr("Markups are hidden (Review > Show markups)."))
            return None
        items = self.review_items()
        if not items:
            self.statusMessage.emit(tr("No comments or markups in this document."))
            return None
        cur = self.selection if self.selection in items else getattr(self, "_review_pos", None)
        if cur in items:
            k = (items.index(cur) + step) % len(items)
        else:
            page = self.current_page()
            after = [k for k, (i, _x) in enumerate(items) if i >= page]
            k = (after[0] if after else 0) if step > 0 else \
                ([k for k, (i, _x) in enumerate(items) if i < page] or [len(items)])[-1] % len(items)
        index, xref = items[k]
        self.reveal(index, xref)                   # (markups this app can't edit: shown only)
        self._review_pos = (index, xref)
        self.statusMessage.emit(tr("Markup {n} of {total} (page {page})").format(
            n=k + 1, total=len(items), page=index + 1))
        return index, xref

    def markup_authors(self):
        names = set()
        for i in range(self.doc.page_count):
            for an in annotations.each_annot(self.doc[i]):
                if an.type[0] != pymupdf.PDF_ANNOT_POPUP:
                    names.add(an.info.get("title", "") or "")
        return sorted(names)

    def delete_markups(self, author=None, pages=None):
        """Delete markups (all, or only those by author) on pages (None: all). Returns count."""
        pages = range(self.doc.page_count) if pages is None else pages
        doomed = {}
        for i in pages:
            pg = self.doc[i]
            for an in pg.annots():
                if an.type[0] == pymupdf.PDF_ANNOT_POPUP:
                    continue
                if author is None or (an.info.get("title", "") or "") == author:
                    doomed.setdefault(i, []).append(an.xref)
        if not doomed:
            return 0

        def do():
            for i, xrefs in doomed.items():
                pg = self.doc[i]
                for x in xrefs:
                    try:
                        pg.delete_annot(pg.load_annot(x))
                    except Exception:
                        pass
        self.clear_selection()
        self.modify(do, list(doomed), permission=pymupdf.PDF_PERM_ANNOTATE)
        return sum(len(x) for x in doomed.values())

    def field_rects(self, index):
        """[(rect, required)] of fillable form fields on a page (cached until the next edit)."""
        cache = self._card_cache.setdefault(("fields", index), None)
        if cache is None:
            cache = []
            for w in self.doc[index].widgets():
                if w.field_type == pymupdf.PDF_WIDGET_TYPE_BUTTON:
                    continue
                cache.append((pymupdf.Rect(w.rect), bool(w.field_flags & 2)))
            self._card_cache[("fields", index)] = cache
        return cache

    # ---- grid and snapping (View menu; settings shared by all documents) -------------
    grid_on = False
    grid_spacing = 36.0            # points between grid lines
    grid_major = 4                 # every Nth line drawn darker
    snap_grid = False
    snap_objects = False
    snap_page = False              # page corners, edge middles, center and edges
    SNAP_PX = 9                    # snap distance on screen, pixels

    def _content_key(self, page):
        doc = page.parent
        return tuple((x, len(doc.xref_stream_raw(x) or b"")) for x in page.get_contents())

    def _content_snaps(self, index):
        from . import snapping
        page = self.doc[index]
        cached = self._snap_content.get(index)
        if cached is not None and index in self._snap_recheck:
            self._snap_recheck.discard(index)
            if cached[0] != self._content_key(page):
                cached = None
        if cached is None:
            cached = (self._content_key(page), snapping.content_index(page))
            self._snap_content[index] = cached
        return cached[1]

    def snap_point(self, index, pt, exclude=()):
        """Snap a PDF point: to the nearest object point within SNAP_PX, else to the page
        (corners, edge middles, center, edges), else to the grid. Returns (point, kind) with
        kind 'object', 'page' or 'grid', or None when nothing applies."""
        from . import snapping
        page = self.doc[index]
        if self.snap_objects:
            tol = self.SNAP_PX / self.zoom
            if index not in self._snap_markups:
                self._snap_markups[index] = snapping.markup_index(page)
            hits = [h for h in (self._snap_markups[index].nearest(pt, tol, exclude),
                                self._content_snaps(index).nearest(pt, tol)) if h is not None]
            if hits:
                return min(hits, key=lambda h: abs(h - pt)), "object"
        if self.snap_page:
            hit = snapping.page_snap(page, pt, self.SNAP_PX / self.zoom)
            if hit is not None:
                return hit, "page"
        if self.snap_grid and self.grid_spacing > 0:
            return snapping.grid_snap(page, pt, self.grid_spacing), "grid"
        return None

    # CAD-style mouse (View menu): the wheel zooms around the cursor, like AutoCAD.
    # Holding the wheel (middle button) down and dragging pans in either mode.
    # Mouse mode (mouse_modes.py sets these from Preferences > Mouse)
    mouse_mode = "hand"         # "standard", "hand" or "cad"
    wheel_zoom = False          # CAD: the wheel zooms at the cursor, Ctrl+wheel scrolls
    plus_cursor = False         # CAD: a plus pointer with every tool but the Hand
    cad_select = False          # CAD: window / crossing boxes; clicks add, Shift takes out
    click_click = False         # CAD: click, move, click draws the selection box
    lasso = False               # CAD: holding the button and dragging draws a lasso
    type_to_line = False        # CAD: letters typed over the drawing go to the command line
    _cad_pick = None            # CAD: a click, move, click box in progress (cad_select.py)
    hand_selects = True         # Hand: clicking a markup selects it
    free_pan = False            # Free page movement: the page can be dragged past its edges
    page_wheel = False          # one wheel step = one page when the page fits the window
    night_mode = False          # pages drawn with their lightness inverted (CAD night mode)
    thin_lines = True           # Enhance thin lines: lines at least a pixel wide on screen
    untitled = False            # a new document never saved yet (File > New PDF)
    open_view = "width"         # zoom for newly opened files: width, page, actual, last
    reopen_page = True          # reopen files at the page they were left on

    def wheelEvent(self, e):
        delta = e.angleDelta()
        dy, dx = delta.y(), delta.x()
        if dy == 0 and dx == 0:          # a trackpad may send pixels instead of a notch
            pix = e.pixelDelta()
            dy, dx = pix.y(), pix.x()
        mods = e.modifiers()
        shift = bool(mods & Qt.ShiftModifier)
        ctrl = bool(mods & Qt.ControlModifier)

        def scroll(bar, step):
            if step:
                bar.setValue(bar.value() - step)
            e.accept()

        # Shift+wheel always moves sideways: with CAD mouse on or off, and even when a
        # plain wheel step would turn the page. The notch may arrive on either axis.
        if shift:
            scroll(self.horizontalScrollBar(), dy or dx)
            return
        if dx and not dy:
            scroll(self.horizontalScrollBar(), dx)
            return
        if self.wheel_zoom and ctrl:
            # CAD mouse (Bluebeam-style): the wheel zooms; Ctrl+wheel scrolls up and down
            scroll(self.verticalScrollBar(), dy or dx)
            return
        if self.wheel_zoom:
            if dy:
                vp = self.viewport().mapFromGlobal(QCursor.pos())
                self.zoom_at(self.zoom * 1.15 ** (dy / 120.0), vp)
            e.accept()
        elif ctrl:
            # zoom around the pointer, like CAD-style mouse, not around the window's center
            if dy:
                vp = self.viewport().mapFromGlobal(e.globalPosition().toPoint())
                self.zoom_at(self.zoom * (1.2 if dy > 0 else 1 / 1.2), vp)
            e.accept()
        elif self.page_wheel and dy and self._page_fits():
            # one wheel step = one whole page (when the page fits in the window)
            self._wheel_acc = getattr(self, "_wheel_acc", 0) + dy
            if abs(self._wheel_acc) >= 120:         # touchpads send many small steps
                step = -1 if self._wheel_acc > 0 else 1
                self._wheel_acc = 0
                self.show_whole_page(self.current_page() + step)
            e.accept()
        else:
            super().wheelEvent(e)

    def _page_fits(self):
        if not getattr(self, "pages", None):
            return False
        # only when the whole page, top to bottom and side to side, is in the window
        w = self.pages[self.current_page()]
        vp = self.viewport()
        return w.height() <= vp.height() and w.width() <= vp.width()

    def show_whole_page(self, index):
        """Scroll so page `index` is centered top to bottom in the window."""
        index = max(0, min(index, len(self.pages) - 1))
        w = self.pages[index]
        self.verticalScrollBar().setValue(int(w.y() - (self.viewport().height() - w.height()) / 2))
        self.center_horizontally(index)
        self._on_scroll()

    def zoom_at(self, z, vp_pos):
        """Zoom keeping the page point under vp_pos (viewport coordinates) where it is."""
        cont = self.widget()
        cpos = cont.mapFrom(self.viewport(), vp_pos)
        target = None
        for w in self.pages:
            if w.geometry().contains(cpos):
                target = w
                break
        if target is None:
            self.set_zoom(z)
            return
        fx = (cpos.x() - target.x()) / max(1, target.width())
        fy = (cpos.y() - target.y()) / max(1, target.height())
        self.set_zoom(z)
        nx = target.x() + fx * target.width()
        ny = target.y() + fy * target.height()
        self.horizontalScrollBar().setValue(int(nx - vp_pos.x()))
        self.verticalScrollBar().setValue(int(ny - vp_pos.y()))

    # ---- hand tool --------------------------------------------------------
    def begin_pan(self, gpos):
        self._pan_origin = (gpos, self.horizontalScrollBar().value(),
                            self.verticalScrollBar().value())
        self.viewport().setCursor(Qt.ClosedHandCursor)

    def continue_pan(self, gpos):
        if self._pan_origin is None:
            return
        start, h, v = self._pan_origin
        d = gpos - start
        self.horizontalScrollBar().setValue(int(h - d.x()))
        self.verticalScrollBar().setValue(int(v - d.y()))

    def end_pan(self):
        self._pan_origin = None
        self._tool_cursor()

    def set_tool(self, tool):
        from . import cad_select
        # text typed in Edit text and not yet applied is applied, as Save and Undo do (the
        # next click on the page would otherwise only apply it)
        self.commit_pending()
        cad_select.drop(self)           # (a lasso held while the mode changed selects nothing)
        if self._cad_cmd is not None:
            self._cad_cmd.cancel()
        self.tool = tool
        for w in getattr(self, "pages", []):
            # a stamp / signature preview or a shape half-drawn belongs to the old tool
            if w._ghost is not None or w._drag_start is not None or w._poly:
                w._ghost, w._drag_start, w._drag_now, w._poly = None, None, None, []
                w.update()
        self.clear_selection()
        self.clear_object_selection()
        self.clear_text_selection()
        self._tool_cursor()

    def _tool_cursor(self):
        self._cad_prepare_soon()            # (a tool or the mouse mode changed)
        tool = self.tool
        if tool == "eraser" and not self.plus_cursor:
            self.viewport().setCursor(eraser_cursor())
            return
        text_cursor = ("select", "edittext", "addtext", "highlight", "underline", "strikeout", "comment",
                       "redact")
        cursors = {"hand": Qt.OpenHandCursor, **{t: Qt.IBeamCursor for t in text_cursor}}
        if self.plus_cursor and tool != "hand":
            cursors = {}                # CAD mouse: a plus, as in CAD programs
        self.viewport().setCursor(cursors.get(tool, Qt.CrossCursor))

    # ---- undo / modify ----------------------------------------------------
    def _snapshot(self):
        # a protected file's undo copies keep its encryption, so saving after an undo can
        # still keep the original passwords and permissions (see save)
        if self._orig_enc is not None and (self.doc.metadata or {}).get("encryption"):
            return self.doc.tobytes(encryption=pymupdf.PDF_ENCRYPT_KEEP)
        return self.doc.tobytes()

    def _view_anchor(self):
        """Where the window is looking, as a fraction of the current page, so a rebuild
        (undo, redo) can put that same spot back instead of jumping to the top."""
        if not getattr(self, "pages", None):
            return None
        page = self.current_page()
        w = self.pages[page]
        return (page,
                (self.verticalScrollBar().value() - w.y()) / max(1, w.height()),
                self.horizontalScrollBar().value() - w.x())

    def _apply_view_anchor(self, anchor):
        import shiboken6
        if anchor is None or not shiboken6.isValid(self) or not getattr(self, "pages", None):
            return                      # (queued with a timer: the view may be gone by now)
        page, vfrac, h_off = anchor
        page = max(0, min(page, len(self.pages) - 1))
        w = self.pages[page]
        self.verticalScrollBar().setValue(int(w.y() + vfrac * w.height()))
        self.horizontalScrollBar().setValue(int(w.x() + h_off))
        self._on_scroll()

    def _restore(self, data, dirty=True):
        """Show the document saved in data (undo, redo, a rolled-back edit); dirty: whether
        it then has unsaved changes."""
        anchor = self._view_anchor()
        self._inline = None             # its widget goes with the rebuilt pages
        self.field_focus = None
        self._clear_caches()
        self.markups_changed = None
        self.selection = None
        self.selected_model = None
        self.extra = []
        fresh = pymupdf.open(stream=data, filetype="pdf")
        if fresh.needs_pass and self._orig_enc is not None:
            for pw in (self._orig_enc.get("owner_pw"), self._orig_enc.get("user_pw")):
                if pw and fresh.authenticate(pw):
                    break
        old = self.doc
        self.doc = fresh
        self.search_hits.clear()
        self._search_list = []
        self._search_text = None
        self._search_cur = None
        self._search_todo = None
        self._search_gen += 1
        self.searchChanged.emit(0, 0, False)
        self._build_pages()
        old.close()
        self._apply_view_anchor(anchor)
        # a fit that was queued by the rebuild runs after this returns; put the spot back
        if anchor is not None:
            QTimer.singleShot(0, lambda a=anchor: self._apply_view_anchor(a))
        self.dirty = dirty
        self.structureChanged.emit()
        self.selectionChanged.emit()

    def modify(self, fn, pages=None, structural=False, permission=pymupdf.PDF_PERM_MODIFY):
        """Run an edit with an undo snapshot. pages = indices to repaint. Returns True when
        the edit was made (not refused or rolled back)."""
        if getattr(self, "_source", None) is not None:
            # the split view shares the main view's document but not its undo history or
            # unsaved-changes mark: edits must go through the main view
            self.statusMessage.emit(tr("The split view is read-only: edit in the main view."))
            return
        if not self.allowed(permission):
            if getattr(self, "sig_results", None):
                with _not_busy():
                    QMessageBox.information(self, tr("Digitally signed document"),
                                            tr("This PDF is digitally signed, so it's read-only "
                                               "to keep the signature valid. Click \u201cEdit "
                                               "anyway\u201d in the banner if you really need to "
                                               "change it."))
            else:
                with _not_busy():
                    QMessageBox.information(self, tr("Protected document"),
                                            tr("This PDF is protected against changes. Use "
                                               "Protect > Unlock with password if you have its "
                                               "permissions password."))
            return
        self.commit_pending()           # a text edit in progress becomes its own undo step
        from . import cad_select
        cad_select.drop(self)
        # a burst of arrow-key nudges is one undo step: later presses reuse the first snapshot
        merge = getattr(self, "_merge_edit", False) and bool(self._undo)
        snap = None if merge else self._snapshot()
        # only the pages this edit touches lose their parsed drawings, text and snap points;
        # a structural change (pages added, removed, moved) or an unknown extent clears all
        if structural or pages is None:
            self._clear_caches()
            self.markups_changed = None             # the markups list re-reads everything
        else:
            self._clear_page_caches(pages)
            if self.markups_changed is not None:
                self.markups_changed |= set(pages)
        was_dirty = self.dirty
        try:
            fn()
        except Exception as ex:
            with _not_busy():
                QMessageBox.warning(self, tr("Edit failed"), str(ex))
            # rolled back: nothing changed
            self._restore(snap if snap is not None else self._undo.pop(), dirty=was_dirty)
            return
        if snap is not None:
            self._undo.append(snap)
        self._cad_prepare_soon()            # (in CAD mode: the changed page made ready again)
        del self._undo[:-UNDO_LIMIT]
        self._redo.clear()
        self._trim_history()
        self.dirty = True
        # any edit can change the page text: the next Find searches again
        self._search_text = None
        self._search_todo = None
        self._search_gen += 1
        self.searchChanged.emit(0, 0, False)
        if structural:
            self._inline = None
            self.field_focus = None     # its page may be gone or moved
            page = self.current_page()
            self.search_hits.clear()
            self._search_list = []
            self._search_text = None
            self._search_cur = None
            self.selection = None
            self.selected_model = None
            self.extra = []
            self._build_pages()
            self.goto_page(min(page, self.doc.page_count - 1))
            self.structureChanged.emit()
            self.selectionChanged.emit()
        else:
            for i in pages or []:
                self.pages[i].invalidate()
            self.documentChanged.emit()
        return True

    def can_undo(self):
        return bool(self._undo)

    def can_redo(self):
        return bool(self._redo)

    def commit_pending(self):
        """Apply a text edit still open in the on-page editor (typed but not yet confirmed
        with Enter), so Save, Undo, closing the tab or a page change doesn't drop it."""
        if self._inline is not None:
            try:
                self._inline.commit()   # clears _inline, then applies the edit
            except RuntimeError:        # its widget was already deleted
                pass
            self._inline = None

    def undo(self):
        from . import cad_select
        if self._cad_cmd is not None and self._cad_cmd.needs_selection:
            self._cad_cmd.cancel()      # (its selection is gone with the change)
        cad_select.drop(self)
        self.commit_pending()
        if self._undo:
            self._redo.append(self._snapshot())
            self._restore(self._undo.pop())
            self._trim_history()

    def redo(self):
        from . import cad_select
        if self._cad_cmd is not None and self._cad_cmd.needs_selection:
            self._cad_cmd.cancel()
        cad_select.drop(self)
        self.commit_pending()
        if self._redo:
            self._undo.append(self._snapshot())
            self._restore(self._redo.pop())
            self._trim_history()

    # every change bumps the revision, so autosave can tell whether anything changed since
    # its last backup
    revision = 0
    _dirty = False

    @property
    def dirty(self):
        return self._dirty

    @dirty.setter
    def dirty(self, value):
        if value:
            self.revision += 1
            if self._cad_cmd is not None:
                # a change the command didn't make itself (Delete, a page rotated...): it
                # ends, once this change is done (cad_apply marks its own changes as seen)
                QTimer.singleShot(0, self._cad_check)
        self._dirty = bool(value)

    def _cad_check(self):
        import shiboken6
        if shiboken6.isValid(self) and self._cad_cmd is not None:
            self._cad_cmd.gone()

    markups_changed = None      # pages whose markups changed since the list last read them
                                # (None: all of them)

    def take_markup_changes(self):
        """Pages to re-read for the markups list (None: all), and start counting afresh."""
        changed, self.markups_changed = self.markups_changed, set()
        return changed

    _views = None                       # all open documents (weak), for the shared budget

    def history_bytes(self):
        return sum(len(s) for s in self._undo) + sum(len(s) for s in self._redo)

    def _trim_history(self):
        """Keep undo/redo within UNDO_BYTES_PER_DOC for this document and UNDO_BYTES_TOTAL
        for all open documents, dropping the oldest steps first (redo's furthest first).
        The most recent undo step of each document is always kept."""
        import weakref
        if DocumentView._views is None:
            DocumentView._views = weakref.WeakSet()
        DocumentView._views.add(self)

        def drop_one(v):
            if v._redo:
                v._redo.pop(0)                  # the redo step furthest in the future
                return True
            if len(v._undo) > 1:
                v._undo.pop(0)                  # the oldest step
                return True
            return False
        while self.history_bytes() > UNDO_BYTES_PER_DOC and drop_one(self):
            pass
        views = [v for v in DocumentView._views if hasattr(v, "_undo")]
        while sum(v.history_bytes() for v in views) > UNDO_BYTES_TOTAL:
            # the biggest history first; one that can't give up a step (just its last undo
            # step left) is passed over, not the end of trimming
            if not any(drop_one(v) for v in sorted(views, key=lambda v: -v.history_bytes())):
                break

    # ---- caches (cleared on every change) ------------------------------------
    def _clear_caches(self):
        self._dlists = {}              # page index -> parsed drawing (DisplayList)
        self._tiles = OrderedDict()    # (page, scale, tx, ty) -> rendered tile, LRU
        self._line_cache = {}
        self._row_cache = {}           # page index -> text_edit.paragraph_rows (Edit text)
        self._hover_para = {}          # page index -> {line id: what a click there edits}
        self._word_cache = {}
        self._card_cache = {}
        self.text_sel = None           # [(page index, selected character units), ...]
        self._text_drag = None         # [(page, mode, words)] while a text drag is in progress
        self._snap_markups = {}        # page index -> snapping.PointIndex of markup points
        self._obj_cache = {}           # page index -> page_objects.Objects (Edit objects)
        self._text_obj_cache = {}      # page index -> paragraphs of text (Edit objects)
        self.obj_sel = None            # (page index, [objects]) selected with Edit objects
        # the drawing's own line work rarely changes: re-check it lazily instead of dropping it
        if not hasattr(self, "_snap_content"):
            self._snap_content = {}    # page index -> (content key, PointIndex)
        self._snap_recheck = set(self._snap_content)
        if not hasattr(self, "_pix_pages"):
            self._pix_pages = set()    # page indexes whose widget may hold a rendered bitmap

    def _clear_page_caches(self, pages):
        """Forget what's cached for these pages only (an edit that leaves the others as
        they were)."""
        pages = set(pages)
        for i in pages:
            self._dlists.pop(i, None)
            self._line_cache.pop(i, None)
            self._row_cache.pop(i, None)
            self._hover_para.pop(i, None)
            self._word_cache.pop(i, None)
            self._snap_markups.pop(i, None)
            self._obj_cache.pop(i, None)
            self._text_obj_cache.pop(i, None)
            for key in ("fields", "links", "fieldx", "annotx", "review"):
                self._card_cache.pop((key, i), None)
            self._card_cache.pop(i, None)
            self._snap_recheck.add(i)
        for key in [k for k in self._tiles if k[0] in pages]:
            del self._tiles[key]
        self.text_sel = None
        self._text_drag = None
        self.obj_sel = None

    def _words(self, index):
        """Selectable text units: individual characters, so selections can start and end
        mid-word. Same tuple shape as PyMuPDF words: (x0, y0, x1, y1, text, block, line, n)."""
        if index not in self._word_cache:
            out = []
            flags = pymupdf.TEXTFLAGS_RAWDICT & ~pymupdf.TEXT_PRESERVE_IMAGES
            d = self.doc[index].get_text("rawdict", flags=flags)
            for bi, blk in enumerate(d["blocks"]):
                if blk.get("type") != 0:
                    continue
                for li, line in enumerate(blk["lines"]):
                    n = 0
                    for span in line["spans"]:
                        for ch in span["chars"]:
                            r = pymupdf.Rect(ch["bbox"])
                            if r.width <= 0:              # some spaces have no width
                                r.x1 = r.x0 + span["size"] * 0.25
                            if r.height <= 0:
                                continue
                            out.append((r.x0, r.y0, r.x1, r.y1, ch["c"], bi, li, n))
                            n += 1
            self._word_cache[index] = out
        return self._word_cache[index]

    # ---- text selection (live, like a normal text cursor) ---------------------
    NEAR = 12   # points: how close to text a drag must start to select text

    def _word_near(self, words, pt, limit=None):
        best, best_d = None, None
        for i, w in enumerate(words):
            r = pymupdf.Rect(w[:4])
            if r.contains(pt):
                return i
            dx = max(r.x0 - pt.x, 0, pt.x - r.x1)
            dy = max(r.y0 - pt.y, 0, pt.y - r.y1)
            d = (dx * dx + 4 * dy * dy) ** 0.5
            if best_d is None or d < best_d:
                best, best_d = i, d
        if limit is not None and (best_d is None or best_d > limit):
            return None
        return best

    @staticmethod
    def _reading_order(cands):
        """Order words as a reader would: rows top to bottom, then left to right."""
        cands = sorted(cands, key=lambda w: (w[1] + w[3]) / 2)
        rows, row_y, row_h = [], None, None
        for w in cands:
            yc, h = (w[1] + w[3]) / 2, w[3] - w[1]
            if row_y is None or abs(yc - row_y) > 0.5 * max(h, row_h):
                rows.append([w])
                row_y, row_h = yc, h
            else:
                rows[-1].append(w)
        return [w for row in rows for w in sorted(row, key=lambda w: w[0])]

    @staticmethod
    def _word_in_box(r, box):
        if not r.intersects(box):
            return False
        inter = pymupdf.Rect(r) & box
        return inter.get_area() >= 0.4 * r.get_area()

    def text_selection(self, index, a, b):
        """('text'|'box', words) for a drag from a to b.

        Starting on (or right next to) text selects like a text cursor: from the word under
        the start to the word under the mouse, in reading order, staying within the column
        of the start and end text. Starting away from text selects words inside the box."""
        words = self._words(index)
        if not words:
            return ("box", [])
        si = self._word_near(words, a, self.NEAR)
        if si is None:
            box = pymupdf.Rect(a, b).normalize()
            return ("box", [w for w in words if self._word_in_box(pymupdf.Rect(w[:4]), box)])
        ei = self._word_near(words, b)
        ws, we = words[si], words[ei]
        if ws[5] == we[5]:                      # same text block: its own order
            blk = [w for w in words if w[5] == ws[5]]
            i, j = blk.index(ws), blk.index(we)
            return ("text", blk[min(i, j):max(i, j) + 1])
        # different blocks: geometric flow limited to the columns those blocks occupy
        bb = {}
        for w in words:
            bb[w[5]] = bb.get(w[5], pymupdf.Rect(w[:4])) | pymupdf.Rect(w[:4])
        span = bb[ws[5]] | bb[we[5]]
        top, bottom = min(ws[1], we[1]), max(ws[3], we[3])
        cands = [w for w in words
                 if bb[w[5]].x1 > span.x0 and bb[w[5]].x0 < span.x1
                 and w[3] > top and w[1] < bottom]
        order = self._reading_order(cands)
        i, j = order.index(ws), order.index(we)
        return ("text", order[min(i, j):max(i, j) + 1])

    def text_selection_span(self, i0, a, i1, b, box=False):
        """[(page, mode, words)] for a drag from point a on page i0 to point b on page i1.

        One page keeps the usual selection. Across pages, text the drag started on is taken
        in reading order from that character through the character under the pointer, including
        every page in between. A drag that starts away from text (or Ctrl+drag) takes the words
        on each page that the drag covers."""
        a, b = pymupdf.Point(a), pymupdf.Point(b)
        if i0 == i1 and not box:
            mode, words = self.text_selection(i0, a, b)
            return [(i0, mode, words)]
        if i0 == i1:
            rect = pymupdf.Rect(a, b).normalize()
            words = [w for w in self._words(i0) if self._word_in_box(pymupdf.Rect(w[:4]), rect)]
            return [(i0, "box", words)]
        started_on_text = bool(self._words(i0)) and self._word_near(self._words(i0), a, self.NEAR) is not None
        if box or not started_on_text:
            return self._box_span(i0, a, i1, b)
        return self._flow_span(i0, a, i1, b)

    def _flow_span(self, i0, a, i1, b):
        """Reading-order text from the press to the pointer, across page breaks."""
        def anchor(index, pt):
            words = self._words(index)
            if not words:
                return None
            i = self._word_near(words, pt)
            return None if i is None else words[i]

        w0, w1 = anchor(i0, a), anchor(i1, b)
        if i0 <= i1:
            first, first_w, last, last_w = i0, w0, i1, w1
        else:
            first, first_w, last, last_w = i1, w1, i0, w0
        spans = []

        def chunk(index, word, through_end):
            order = self._reading_order(self._words(index))
            if not order or word is None:
                return
            try:
                i = order.index(word)
            except ValueError:
                spans.append((index, "text", order))
                return
            part = order[i:] if through_end else order[:i + 1]
            if part:
                spans.append((index, "text", part))

        chunk(first, first_w, True)
        for p in range(first + 1, last):
            order = self._reading_order(self._words(p))
            if order:
                spans.append((p, "text", order))
        if last != first:
            chunk(last, last_w, False)
        return spans

    def _box_span(self, i0, a, i1, b):
        """Words on each page the drag crosses, from the start point toward the end point."""
        lo, hi = (i0, i1) if i0 <= i1 else (i1, i0)
        spans = []
        for p in range(lo, hi + 1):
            words = self._words(p)
            if p == i0 and i1 > i0:
                picked = [w for w in words if w[3] >= a.y]
            elif p == i0 and i1 < i0:
                picked = [w for w in words if w[1] <= a.y]
            elif p == i1 and i0 < i1:
                picked = [w for w in words if w[1] <= b.y]
            elif p == i1 and i0 > i1:
                picked = [w for w in words if w[3] >= b.y]
            else:
                picked = list(words)
            if picked:
                spans.append((p, "box", self._reading_order(picked)))
        return spans

    def page_point_from(self, origin, pos):
        """(page index, PDF point) under a point in a page widget's coordinates.

        The point may be outside that page (the drag crossed the gap). Pages are stacked, so
        the page is found by height, and the point is clamped onto it."""
        if not self.pages:
            return origin.index, origin.to_pdf(pos)
        content = self.widget().mapFromGlobal(origin.mapToGlobal(pos))
        y = content.y()
        pages = self.pages
        lo, hi = 0, len(pages)
        while lo < hi:
            m = (lo + hi) // 2
            w = pages[m]
            if w.y() + w.height() >= y:
                hi = m
            else:
                lo = m + 1
        if lo >= len(pages):
            best = len(pages) - 1
        elif y >= pages[lo].y() or lo == 0:
            best = lo
        else:
            prev = pages[lo - 1]
            best = lo - 1 if y - (prev.y() + prev.height()) <= pages[lo].y() - y else lo
        w = pages[best]
        local = w.mapFromGlobal(origin.mapToGlobal(pos))
        clamped = QPointF(min(max(local.x(), 0), max(0, w.width() - 1)),
                          min(max(local.y(), 0), max(0, w.height() - 1)))
        return best, w.to_pdf(clamped)

    def autoscroll_toward(self, global_pos):
        """Scroll a little when a drag is held against the top or bottom of the window,
        so the selection can reach the next page."""
        p = self.viewport().mapFromGlobal(global_pos)
        margin = 28
        if p.y() < margin:
            dy = p.y() - margin
        elif p.y() > self.viewport().height() - margin:
            dy = p.y() - (self.viewport().height() - margin)
        else:
            return
        dy = max(-28, min(28, dy))
        bar = self.verticalScrollBar()
        bar.setValue(int(bar.value() + dy))

    def _set_text_drag(self, spans):
        old = {s[0] for s in (self._text_drag or [])}
        self._text_drag = [s for s in (spans or []) if s[2]] or None
        new = {s[0] for s in (self._text_drag or [])}
        for i in old | new:
            if 0 <= i < len(self.pages):
                self.pages[i].update()

    @staticmethod
    def line_rects(words):
        lines, order = {}, []
        for w in words:
            key = (w[5], w[6])
            if key not in lines:
                lines[key] = pymupdf.Rect(w[:4])
                order.append(key)
            else:
                lines[key] |= pymupdf.Rect(w[:4])
        return [lines[k] for k in order]

    @staticmethod
    def _words_text(units):
        """Selected text: characters on a line join directly; lines are separated by newlines."""
        out, last = [], None
        for w in units:
            key = (w[5], w[6])
            if last is not None and key != last:
                out.append("\n")
            elif last is not None and len(w[4]) > 1:      # whole words (older callers)
                out.append(" ")
            out.append(w[4])
            last = key
        return "\n".join(line.strip() for line in "".join(out).split("\n"))

    # ---- copy, cut, paste ------------------------------------------------------
    def set_text_selection(self, index, words):
        self.set_text_spans([(index, words)] if words else [])

    def set_text_spans(self, spans):
        old = {i for i, _words in (self.text_sel or [])}
        clean = [(i, list(words)) for i, words in spans if words]
        self.text_sel = clean or None
        for i in old | {i for i, _words in clean}:
            if 0 <= i < len(self.pages):
                self.pages[i].update()

    def clear_text_selection(self):
        if self.text_sel:
            self.set_text_spans([])

    def select_all_text(self):
        index = self.current_page()
        words = self._words(index)
        self.set_text_selection(index, words)
        return len(self.selected_text())

    def word_at(self, index, pt):
        """The characters of the word under pt (unrotated page point), or []."""
        words = self._words(index)
        i = self._word_near(words, pt, self.NEAR) if words else None
        if i is None or not words[i][4].strip():
            return []
        key = (words[i][5], words[i][6])
        a = b = i
        while a > 0 and (words[a - 1][5], words[a - 1][6]) == key and words[a - 1][4].strip():
            a -= 1
        while b + 1 < len(words) and (words[b + 1][5], words[b + 1][6]) == key and \
                words[b + 1][4].strip():
            b += 1
        return words[a:b + 1]

    def line_at(self, index, pt):
        """The characters of the line of text under pt, or []."""
        words = self._words(index)
        i = self._word_near(words, pt, self.NEAR) if words else None
        if i is None:
            return []
        key = (words[i][5], words[i][6])
        return [w for w in words if (w[5], w[6]) == key]

    def selected_text(self):
        if not self.text_sel:
            return ""
        return "\n\n".join(self._words_text(words) for _i, words in self.text_sel)

    def copy(self):
        """Copy the selected text, the selected markups, or one picture selected with Edit
        objects. Returns what was copied."""
        from . import clip
        if not self.require_permission(pymupdf.PDF_PERM_COPY, tr("Copying")):
            return None
        if self.text_sel:
            QGuiApplication.clipboard().setText(self.selected_text())
            return "text"
        items = self.selected_objects()
        if self.tool == "editobjects" and len(items) == 1 and items[0]["kind"] == "picture":
            self.copy_picture()             # (as right-click > Copy picture)
            return "picture"
        models = self._models_for_clipboard()
        if models:
            text = "\n".join(m.get("text", "") for m in models if m.get("text"))
            clip.put("markups", models, text)
            return "markups"
        return None

    def _models_for_clipboard(self):
        if self.selection is None:
            return []
        page = self.doc[self.selection[0]]
        out = []
        for x, m in self.selected_models():
            if m["kind"] in ("field", "redact"):
                continue
            m = annotations.copy(m)
            if m["kind"] == "image" and m.get("img"):
                from . import capture
                img = m.pop("img")
                if capture.is_form(self.doc, img):
                    # vector capture: same file pastes the vector drawing, others a picture
                    m["form"] = (id(self.doc), img)
                    m["image_bytes"] = page.load_annot(x).get_pixmap(dpi=200).tobytes("png")
                else:
                    m["image_bytes"] = annotations.image_bytes(self.doc, img)[0]
            if m["kind"] == "attach":
                an = page.load_annot(x)
                m["file_bytes"] = an.get_file()
                m["filename"] = an.file_info.get("filename", "attachment")
            m.pop("author", None)
            m.pop("created", None)
            m["locked"] = False
            out.append(m)
        return out

    def duplicate_selected(self, offset=12):
        """Copies of the selected markups, offset down-right on screen; the copies are selected."""
        models = self._models_for_clipboard()
        if not models:
            return 0
        models = self._next_counts(models)
        index = self.selection[0]
        page = self.doc[index]
        m_ = page.derotation_matrix
        d = pymupdf.Point(offset, offset) * m_ - pymupdf.Point(0, 0) * m_
        made = []

        def do():
            pg = self.doc[index]
            for m in models:
                made.append(annotations.write(pg, annotations.moved(m, d)).xref)
        self.modify(do, [index], permission=pymupdf.PDF_PERM_ANNOTATE)
        if made:
            self._set_selection(index, made)
        return len(made)

    def cut(self):
        """Cut the selected text (removed from the page) or the selected markups."""
        what = self.copy()
        if what == "text":
            spans = list(self.text_sel)

            def do():
                for index, words in spans:
                    pg = self.doc[index]
                    for w in words:
                        r = pymupdf.Rect(w[:4])
                        padx, pady = r.width * 0.08, r.height * 0.15
                        pg.add_redact_annot(pymupdf.Rect(r.x0 + padx, r.y0 + pady,
                                                         r.x1 - padx, r.y1 - pady), fill=False)
                    pg.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE,
                                        graphics=pymupdf.PDF_REDACT_LINE_ART_NONE,
                                        text=pymupdf.PDF_REDACT_TEXT_REMOVE)
            self.clear_text_selection()
            self.modify(do, [i for i, _words in spans])
        elif what == "markups":
            self.delete_selected()
        return what

    def paste_target(self):
        """(page index, PDF point) under the mouse, else the middle of the visible page."""
        for i, pw in enumerate(self.pages):
            local = pw.mapFromGlobal(QCursor.pos())
            if pw.isVisible() and pw.rect().contains(local):
                return i, pw.to_pdf(local)
        i = self.current_page()
        pw = self.pages[i]
        vis = pw.visibleRegion().boundingRect()
        c = vis.center() if not vis.isEmpty() else pw.rect().center()
        return i, pw.to_pdf(c)

    def paste(self):
        """Paste markups copied in this app, else a picture, else text (as a text box)."""
        from . import clip
        kind, payload = clip.get()
        if kind == "pages":
            return self.paste_pages(payload, self.current_page() + 1)
        index, pt = self.paste_target()
        page = self.doc[index]
        if kind == "capture":
            from . import capture
            disp = pymupdf.Point(pt) * page.rotation_matrix
            box = pymupdf.Rect(disp.x, disp.y, disp.x + payload["w"], disp.y + payload["h"])
            model = {"kind": "image", "props": self.tool_props("image"),
                     "rect": box * page.derotation_matrix,
                     "image_bytes": payload["png"], "text": tr("Captured area")}
            made = {}

            def do():
                if payload.get("pdf"):
                    # vector content: stays sharp at any zoom and in print
                    model["img"] = capture.make_form(self.doc, payload["pdf"], payload["box"])
                made["xref"] = annotations.write(self.doc[index], model).xref
            del page
            self.modify(do, [index])
            if "xref" in made:
                self.select_xref(index, made["xref"])
            return "image"
        if kind == "markups":
            box = None
            for m in payload:
                box = annotations.bounds(m) if box is None else box | annotations.bounds(m)
            corner = pymupdf.Point(box.x0, box.y0) * page.rotation_matrix
            target = pymupdf.Point(pt) * page.rotation_matrix
            m_ = page.derotation_matrix
            d = (target - corner) * m_ - pymupdf.Point(0, 0) * m_
            made = []
            payload = self._next_counts(payload)

            def do():
                pg = self.doc[index]
                for m in payload:
                    m = annotations.moved(m, d)
                    form = m.pop("form", None)
                    if form and form[0] == id(self.doc):
                        m["img"] = form[1]          # vector capture copied in the same file
                    made.append(annotations.write(pg, m).xref)
            self.modify(do, [index])
            if made:
                self._set_selection(index, made)
            return "markups"
        cb = QGuiApplication.clipboard()
        md = cb.mimeData()
        if md is not None and md.hasImage():
            from PySide6.QtGui import QImage
            img = QImage(cb.image())
            if not img.isNull():
                png = signatures.qimage_to_png(img)
                disp = pymupdf.Point(pt) * page.rotation_matrix
                w, h = img.width() * 72 / 150, img.height() * 72 / 150
                k = min(1.0, page.rect.width * 0.8 / w, page.rect.height * 0.8 / h)
                box = pymupdf.Rect(disp.x, disp.y, disp.x + w * k, disp.y + h * k)
                self._create(index, {"kind": "image", "props": self.tool_props("image"),
                                     "rect": box * page.derotation_matrix, "image_bytes": png,
                                     "text": tr("Pasted image")}, select=True)
                return "image"
        text = cb.text()
        if text.strip():
            props = self.tool_props("textbox")
            size = float(props.get("fontsize", 11))
            lines = text.splitlines() or [text]
            width = max(pymupdf.get_text_length(t, fontname="helv", fontsize=size) for t in lines)
            disp = pymupdf.Point(pt) * page.rotation_matrix
            box = pymupdf.Rect(disp.x, disp.y, disp.x + min(max(width + 12, 60), 460),
                               disp.y + size * 1.35 * len(lines) + 10)
            self._create(index, {"kind": "textbox", "rect": box * page.derotation_matrix,
                                 "text": text, "props": props}, select=True)
            return "text"
        return None

    # ---- pages: copy, paste, duplicate ---------------------------------------------
    def pages_bytes(self, indices):
        """These pages as a PDF for the clipboard. Their links come along as they are; one
        to a page not copied is kept for a paste into this same document (see paste_pages
        and links.copy_page_links)."""
        from . import links
        if not self.allowed(pymupdf.PDF_PERM_COPY):
            raise PermissionError(tr("Copying pages is not allowed."))
        out = pymupdf.open()
        pages = sorted(set(indices))
        for i in pages:
            out.insert_pdf(self.doc, from_page=i, to_page=i, links=False)
        links.copy_page_links(self.doc, list(zip(pages, range(len(pages)))), out,
                              park=self._clip_id())
        data = out.tobytes(garbage=3, deflate=True)
        out.close()
        return data

    def _clip_id(self):
        """Tells this document's pages on the clipboard from another one's."""
        if getattr(self, "_clip_uid", None) is None:
            import uuid
            self._clip_uid = uuid.uuid4().hex
        return self._clip_uid

    def paste_pages(self, data, at):
        """Insert the PDF pages in data before page index at (== count: at the end)."""
        from . import links
        at = max(0, min(at, self.doc.page_count))
        n = {}

        def do():
            with pymupdf.open(stream=data, filetype="pdf") as other:
                n["n"] = other.page_count
                mine = {self.doc.page_xref(i) for i in range(self.doc.page_count)}
                self.doc.insert_pdf(other, start_at=at, links=False)
                # links to pages that weren't copied work again when pasted back into the
                # document they were copied from (Duplicate pages)
                links.copy_page_links(
                    other, [(k, at + k) for k in range(other.page_count)], self.doc,
                    outside=lambda src, xref: xref if src == self._clip_id() and xref in mine
                    else None)
        self.modify(do, structural=True)
        self.goto_page(at)
        return "pages"

    def delete_pages(self, indices):
        indices = sorted(set(indices), reverse=True)
        if len(indices) >= self.doc.page_count:
            QMessageBox.information(self, tr("Delete pages"), tr("A PDF must keep at least one page."))
            return False

        def do():
            toc = self.doc.get_toc(False)
            for i in indices:
                self.doc.delete_page(i)
            self._retarget_bookmarks(toc, set(indices), len(indices) + self.doc.page_count)
        self.modify(do, structural=True)
        return True

    def _retarget_bookmarks(self, toc, gone, old_count):
        """After pages were deleted: a bookmark to one of them (toc: the bookmarks from
        before) goes to the page that now follows it, or the last page, instead of nowhere."""
        for idx, (_lvl, _title, _page, dest) in enumerate(toc):
            if dest.get("kind") != pymupdf.LINK_GOTO or dest.get("page") not in gone:
                continue
            after = next((p for p in range(dest["page"] + 1, old_count) if p not in gone), None)
            new = self.doc.page_count - 1 if after is None else \
                after - sum(1 for g in gone if g < after)
            self.doc.set_toc_item(idx, dest_dict=dict(dest, page=new, to=pymupdf.Point(0, 0)))
            if not dest.get("color") and dest.get("xref"):
                self.doc.xref_set_key(dest["xref"], "C", "null")   # not grayed out

    def duplicate_pages(self, indices):
        """Copies of these pages right after the last of them."""
        if not self.require_permission(pymupdf.PDF_PERM_COPY, tr("Duplicating pages")):
            return
        data = self.pages_bytes(indices)
        return self.paste_pages(data, max(indices) + 1)

    # ---- tool styles --------------------------------------------------------
    def tool_props(self, tool):
        return annotations.tool_props(tool) if tool in annotations.DEFAULTS else {}

    def tool_color(self, tool):
        if tool == "redact":
            return QColor(0, 0, 0)
        if tool == "erasecontent":
            return QColor(220, 0, 0)
        if tool == "capture":
            return QColor(0, 120, 215)
        return QColor(self.tool_props(tool).get("stroke") or "#0078d7")

    # ---- creating annotations -------------------------------------------------
    def _create(self, index, model, select=False):
        made = {}

        def do():
            made["xref"] = annotations.write(self.doc[index], model).xref
        self.modify(do, [index], permission=pymupdf.PDF_PERM_ANNOTATE)
        if select and "xref" in made:
            self.select_xref(index, made["xref"])
        return made.get("xref")

    def apply_text_tool(self, index, tool, a, b):
        self.apply_text_span(tool, (index, a), (index, b))

    def apply_text_span(self, tool, start, end, box=False):
        """Select or mark up the text from start (page, point) to end, across pages."""
        i0, a = start
        i1, b = end
        spans = self.text_selection_span(i0, a, i1, b, box=box)
        if tool == "redact":
            self._redact_text_spans(spans, a, b)
            return
        usable = [(i, words) for i, _mode, words in spans if words]
        if not usable:
            if tool != "select":
                self.statusMessage.emit(tr("No text there to mark up"))
            return
        if tool == "select":
            self.set_text_spans(usable)
            text = self.selected_text()
            if len(usable) > 1:
                msg = tr("{n} characters selected on {pages} pages: Ctrl+C to copy, Ctrl+X to cut")
            else:
                msg = tr("{n} characters selected: Ctrl+C to copy, Ctrl+X to cut")
            self.statusMessage.emit(msg.format(n=len(text), pages=len(usable)))
            return
        self._markup_spans(tool, usable)

    def _redact_text_spans(self, spans, a, b):
        if len(spans) == 1 and spans[0][1] == "box":
            rect = pymupdf.Rect(a, b).normalize()
            by_page = {spans[0][0]: [rect]} if rect.width > 1 and rect.height > 1 else {}
        else:
            by_page = {}
            for i, _mode, words in spans:
                rects = [r for r in self.line_rects(words) if r.width > 1 and r.height > 1]
                if rects:
                    by_page[i] = rects
        if not by_page:
            return

        def do():
            for i, rects in by_page.items():
                pg = self.doc[i]
                for r in rects:
                    an = pg.add_redact_annot(r, fill=(0, 0, 0))
                    an.set_colors(stroke=(0.85, 0, 0))
                    an.set_info(title=annotations.author(), content=tr("Redaction (not applied yet)"))
                    an.update()
        self.modify(do, list(by_page))

    def markup_text_selection(self, tool):
        """Right-click menu: highlight / underline / strike out / comment on / redact the
        selected text. A selection that crosses pages is marked on each page."""
        if not self.text_sel:
            return
        spans = [(i, "text", words) for i, words in self.text_sel]
        if tool == "redact":
            self._redact_text_spans(spans, None, None)
        else:
            self._markup_spans(tool, [(i, words) for i, words in self.text_sel])
        self.clear_text_selection()

    def _markup_spans(self, tool, spans):
        text = "\n\n".join(self._words_text(words) for _i, words in spans)
        note = ""
        if tool == "comment":
            note, ok = dialogs.get_text(self, tr("Comment"),
                                        tr("Comment on “{text}”:").format(text=text[:60]))
            if not ok:
                return

        def do():
            for index, words in spans:
                model = {"kind": tool, "props": self.tool_props(tool),
                         "quads": [r.quad for r in self.line_rects(words)],
                         "text": note if tool == "comment" else self._words_text(words)}
                annotations.write(self.doc[index], model)
        self.modify(do, [i for i, _words in spans], permission=pymupdf.PDF_PERM_ANNOTATE)

    def _markup_words(self, index, tool, words, text):
        self._markup_spans(tool, [(index, words)])

    def apply_drag_tool(self, index, tool, a, b, is_click):
        page = self.doc[index]
        rect = pymupdf.Rect(a, b).normalize()
        if tool == "eraser":
            if is_click:
                self.apply_point_tool(index, "eraser", a)
                return
            xrefs = [an.xref for an in page.annots() if self._annot_in_box(an, rect)]
            if not xrefs:
                return

            def do():
                for x in xrefs:
                    page.delete_annot(page.load_annot(x))
            self.clear_selection()
            self.modify(do, [index])
            self.statusMessage.emit(tr("Erased {n} annotation(s)").format(n=len(xrefs)))
            return
        props = self.tool_props(tool)
        if tool == "link":
            size = float(annotations.tool_props("addtext").get("fontsize") or 12)
            if is_click or rect.width < 4 or rect.height < 4:
                ln = self.link_at(index, a)
                if ln is not None:
                    self.edit_link(index, ln)
                else:
                    # a click on the page: new link text there (it starts at the click,
                    # centered on it)
                    d = pymupdf.Point(a) * page.rotation_matrix + (0, size * 0.35)
                    self.add_link(index, None, rects=[pymupdf.Rect(a, a)], look="underline",
                                  text_at=(d * page.derotation_matrix, size))
                return
            if self._area_is_blank(index, rect):
                # a box over empty paper: new link text in it (as the page is shown)
                disp = (rect * page.rotation_matrix).normalize()
                size = min(size, max(6.0, disp.height * 0.7))
                d = pymupdf.Point(disp.x0, disp.y0 + (disp.height + size * 0.7) / 2)
                self.add_link(index, rect, look="underline",
                              text_at=(d * page.derotation_matrix, size))
            else:
                self.add_link(index, rect)
            return
        if tool in ("erasecontent", "capture", "crop"):
            if is_click or rect.width < 2 or rect.height < 2:
                self.statusMessage.emit(tr("Drag a box around the area"))
                return
            if tool == "crop":
                scope = self._ask_pages_scope(tr("Crop pages"), tr("Crop to this box on which pages?"))
                if scope is not None:
                    self.crop_pages(index, rect, scope == "all")
                self.setFocus()         # so Escape still puts the Crop tool down
            elif tool == "capture":
                self.capture_area(index, rect)
            else:
                self.erase_content(index, rect)
            return
        disp = (rect * page.rotation_matrix).normalize()       # as the page is shown
        if tool == "textbox":
            if is_click or disp.width < 20 or disp.height < 10:
                c = pymupdf.Point(a) * page.rotation_matrix
                rect = pymupdf.Rect(c.x, c.y, c.x + 200, c.y + 40) * page.derotation_matrix
            text, ok = dialogs.get_text(self, tr("Text box"), tr("Text:"))
            if not ok or not text.strip():
                return
            self._create(index, {"kind": "textbox", "rect": rect, "text": text, "props": props})
            return
        if tool == "image":
            self.place_image(index, a, b, is_click)
            return
        if tool == "placeholder":
            props = self.tool_props("placeholder")
            if is_click or disp.width < 12 or disp.height < 8:
                w, h = (160, 40) if props.get("for") == "signature" else (70, 30)
                c = pymupdf.Point(a) * page.rotation_matrix
                rect = pymupdf.Rect(c.x, c.y, c.x + w, c.y + h) * page.derotation_matrix
            self._create(index, {"kind": "placeholder", "props": props, "rect": rect})
            return
        if tool == "m_calibrate":
            if not is_click and abs(b - a) > 2:
                self.calibrateRequested.emit(index, abs(b - a))
            return
        if tool in ("m_length", "m_radius"):
            if not is_click:
                self._create(index, {"kind": tool, "props": props, "points": [a, b],
                                     "rect": pymupdf.Rect()})
            return
        if tool == "callout":
            text, ok = dialogs.get_text(self, tr("Callout"), tr("Text:"))
            if not ok or not text.strip():
                return
            to_disp = page.rotation_matrix
            ta, tb = pymupdf.Point(a) * to_disp, pymupdf.Point(b) * to_disp
            box = pymupdf.Rect(tb.x, tb.y, tb.x + 160, tb.y + 40)
            if tb.x < ta.x:                     # box to the left of the target
                box = pymupdf.Rect(tb.x - 160, tb.y, tb.x, tb.y + 40)
            self._create(index, {"kind": "callout", "props": props,
                                 "rect": box * page.derotation_matrix,
                                 "points": [a], "text": text})
            return
        if is_click:
            return
        kind = "rect" if tool == "cloud" else tool
        model = {"kind": kind, "props": props, "rect": rect}
        if tool in ("line", "arrow"):
            model["points"] = [a, b]
        self._create(index, model)

    # ---- measurement ------------------------------------------------------------------
    def live_measure(self, index, tool, pts):
        from . import measure
        kind = "m_length" if tool == "m_calibrate" else tool
        if tool == "m_calibrate":
            return tr("{length} in on paper").format(length="%.2f" % (abs(pts[-1] - pts[0]) / 72))
        return measure.measure_text(kind, pts, self.doc[index], props=self.tool_props(tool))

    def place_count(self, index, pt):
        group = self.tool_props("m_count").get("group") or "Count"
        n = self._last_counts().get(group, 0)
        self._create(index, {"kind": "m_count", "props": self.tool_props("m_count"),
                             "points": [pt], "rect": pymupdf.Rect(), "n": n + 1})

    def _last_counts(self):
        """{count group: its highest number} in the document."""
        last = {}
        for i in range(self.doc.page_count):
            pg = self.doc[i]
            for a in annotations.each_annot(pg, (pymupdf.PDF_ANNOT_CIRCLE,)):
                m = annotations.read(a)
                if m and m["kind"] == "m_count":
                    group = m["props"].get("group")
                    last[group] = max(last.get(group, 0), m.get("n", 0))
        return last

    def _next_counts(self, models):
        """Copies (Ctrl+D, paste) of Count markers take the next numbers of their group."""
        if not any(m["kind"] == "m_count" for m in models):
            return models
        last = self._last_counts()
        out = []
        for m in models:
            if m["kind"] == "m_count":
                m = annotations.copy(m)
                group = m["props"].get("group")
                last[group] = m["n"] = last.get(group, 0) + 1
            out.append(m)
        return out

    def page_scale_text(self, index):
        """'Scale: ...' for the status bar; when no scale is set and the sheet's title block
        says one, that is mentioned, since Set scale offers it."""
        from . import measure
        text = measure.describe(self.doc[index])
        if not measure.get_scale(self.doc[index])[3]:
            note = self.sheet_scale_note(index)
            if note and note["ratio"] is not None:
                text += "  |  " + tr("the sheet says {scale}: Measure > Set scale uses it").format(
                    scale=note["label"])
            elif note:
                text += "  |  " + tr("the sheet says NOT TO SCALE")
        return text

    def sheet_scale_note(self, index):
        """The scale note on the sheet (sheet_scale.sheet_scale), read once per page."""
        from . import sheet_scale
        cache = self.__dict__.setdefault("_sheet_scale_cache", {})
        page = self.doc[index]
        key = page.xref
        if key not in cache:
            try:
                cache[key] = sheet_scale.sheet_scale(page)
            except Exception:
                cache[key] = None
        return cache[key]

    def set_page_scale(self, pages, m_per_pt, unit, label):
        """Apply one scale to pages and re-measure existing measurements on them."""
        self.set_page_scales({i: (m_per_pt, unit, label) for i in pages})

    def set_page_scales(self, scales):
        """{page index: (meters per point, unit, label)}: apply them all in one undo step and
        re-measure the existing measurements on those pages."""
        from . import measure
        scales = dict(scales)
        if not scales:
            return

        def do():
            for i, (m_per_pt, unit, label) in scales.items():
                pg = self.doc[i]
                measure.set_scale(pg, m_per_pt, unit, label)
                models = []
                for a in pg.annots():
                    m = annotations.read(a)
                    if m and m["kind"] in annotations.MEASURES and m["kind"] != "m_count":
                        models.append((a.xref, m))
                for xref, m in models:
                    pg.delete_annot(pg.load_annot(xref))
                    annotations.write(pg, m)
        self.clear_selection()
        self.modify(do, list(scales))
        self.scaleChanged.emit()

    def apply_poly(self, index, tool, pts):
        self._create(index, {"kind": tool, "props": self.tool_props(tool), "points": pts,
                             "rect": pymupdf.Rect()})

    # ---- stamps -----------------------------------------------------------------
    def stamp_preview(self):
        key = json.dumps(self.tool_props("stamp"), sort_keys=True) + annotations.author()
        if self._stamp_cache.get("key") != key:
            from . import stamps
            png, aspect = stamps.stamp_png(self.tool_props("stamp"), annotations.author())
            pm = QPixmap()
            if png:
                pm.loadFromData(png, "PNG")
            self._stamp_cache = {"key": key, "pm": pm if png else None, "aspect": aspect or 0.4}
        return self._stamp_cache["pm"]

    def stamp_rect(self, index, pt):
        """Unrotated rect for a stamp centered on unrotated point pt (upright on screen)."""
        from . import stamps
        self.stamp_preview()
        page = self.doc[index]
        w = stamps.default_width(self.tool_props("stamp").get("label") or "")
        h = w * self._stamp_cache["aspect"]
        c = pymupdf.Point(pt) * page.rotation_matrix
        disp = pymupdf.Rect(c.x - w / 2, c.y - h / 2, c.x + w / 2, c.y + h / 2)
        return disp * page.derotation_matrix

    # ---- images and attached files ----------------------------------------------------
    IMAGE_FILTER = tr("Images") + " (*.png *.jpg *.jpeg *.bmp *.gif *.tif *.tiff)"
    RISKY = (".exe", ".bat", ".cmd", ".com", ".msi", ".js", ".jse", ".vbs", ".vbe", ".ps1",
             ".scr", ".lnk", ".hta", ".wsf", ".jar", ".reg", ".pif", ".cpl",
             ".application", ".html", ".htm", ".msc", ".iso", ".dll")
    # the only kinds of file opened from a PDF (after asking): documents, pictures, media and
    # drawings. Anything else, including macro-enabled Office files, must be saved first.
    SAFE_OPEN = (".pdf", ".txt", ".csv", ".rtf", ".docx", ".xlsx", ".pptx", ".odt", ".ods",
                 ".odp", ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff", ".webp",
                 ".mp3", ".wav", ".mp4", ".mov", ".avi", ".dwg", ".dxf", ".dwf", ".msg", ".eml")

    @staticmethod
    def safe_file_name(name):
        """A file name from a PDF made harmless for Windows: no folders, no ":stream" part,
        no trailing dots or spaces (Windows drops them, so "evil.exe." would become
        "evil.exe" after the type check), no characters Windows refuses."""
        name = re.split(r"[\\/]", str(name or ""))[-1].split(":")[0]
        name = re.sub(r'[<>"|?*\x00-\x1f]', "_", name).rstrip(". ")
        return name or "attachment"

    @staticmethod
    def _mark_downloaded(path):
        """Tag a file as from the internet (Mark of the Web), so Windows SmartScreen and
        Office Protected View treat it as untrusted. Windows (NTFS) only."""
        if os.name != "nt":
            return
        try:
            with open(path + ":Zone.Identifier", "w") as f:
                f.write("[ZoneTransfer]\r\nZoneId=3\r\n")
        except OSError:
            pass

    def place_image(self, index, a, b, is_click):
        """Image tool: pick a picture and fit it in the dragged box (or natural size at the
        click), keeping its proportions. It becomes part of the page content."""
        path = dialogs.open_file(self, tr("Insert image"), self.IMAGE_FILTER)
        if not path:
            return
        with open(path, "rb") as f:
            data = f.read()
        try:
            pm = pymupdf.Pixmap(data)
            iw, ih = pm.width, pm.height
            dpi_x, dpi_y = pm.xres or 150, pm.yres or 150
        except Exception:
            QMessageBox.warning(self, tr("Insert image"),
                                tr("That file isn't an image this app can read."))
            return
        page = self.doc[index]
        to_disp, to_pdf = page.rotation_matrix, page.derotation_matrix
        pa, pb = pymupdf.Point(a) * to_disp, pymupdf.Point(b) * to_disp
        prect = page.rect                                   # displayed page size
        if is_click or abs(pb.x - pa.x) < 8 or abs(pb.y - pa.y) < 8:
            # natural size (at the image's own resolution, 150 dpi if unknown), within the page
            w, h = iw * 72.0 / max(dpi_x, 72), ih * 72.0 / max(dpi_y, 72)
            k = min(1.0, prect.width * 0.8 / w, prect.height * 0.8 / h)
            box = pymupdf.Rect(pa.x, pa.y, pa.x + w * k, pa.y + h * k)
        else:
            area = pymupdf.Rect(pa, pb).normalize()
            k = min(area.width / iw, area.height / ih)
            w, h = iw * k, ih * k
            box = pymupdf.Rect(area.x0, area.y0, area.x0 + w, area.y0 + h)
        # into the page itself, like Acrobat's Add Image: PDF viewers can't move or delete it
        # (only markups are theirs to edit); Edit objects moves, resizes and deletes it
        rect = box * to_pdf

        def do():
            pg = self.doc[index]
            pg.insert_image(rect, stream=data, keep_proportion=True, rotate=pg.rotation,
                            overlay=True)
        self.modify(do, [index])
        self.statusMessage.emit(tr("Picture added to the page. Edit objects (Shift+O) moves, "
                                   "resizes or deletes it; Ctrl+Z undoes it."))

    def attach_file(self, index, pt):
        """Attach file tool: embed any file in the PDF, shown as an icon at pt."""
        path = dialogs.open_file(self, tr("Attach a file"))
        if not path:
            return
        size = os.path.getsize(path)
        if size > 50 * 1024 * 1024:
            if QMessageBox.question(self, tr("Attach file"),
                                    tr("{name} is {size} MB. The PDF will grow by about that "
                                       "much, which may be too large to email. Attach it "
                                       "anyway?").format(name=os.path.basename(path),
                                                         size="%.0f" % (size / 1e6))
                                    ) != QMessageBox.Yes:
                return
        with open(path, "rb") as f:
            data = f.read()
        model = {"kind": "attach", "props": self.tool_props("attach"),
                 "rect": pymupdf.Rect(pt, pt + (20, 20)), "file_bytes": data,
                 "filename": os.path.basename(path), "text": os.path.basename(path)}
        self._create(index, model, select=True)

    def attachments(self):
        """[(page index or None, xref or name, file name, size, description)]: files attached
        to markups on pages, and files embedded in the document itself."""
        out = []
        for i in range(self.doc.page_count):
            page = self.doc[i]
            for an in annotations.each_annot(page):
                if an.type[0] == pymupdf.PDF_ANNOT_FILE_ATTACHMENT:
                    info = an.file_info
                    out.append((i, an.xref, info.get("filename", ""), info.get("length", 0),
                                info.get("description", "")))
        for name in self.doc.embfile_names():
            info = self.doc.embfile_info(name)
            out.append((None, name, info.get("filename") or name, info.get("length", 0),
                        info.get("description", "")))
        return out

    def attachment_data(self, page_index, key):
        if page_index is None:
            return self.doc.embfile_get(key)
        page = self.doc[page_index]
        return page.load_annot(key).get_file()

    # ---- links in the PDF (web addresses, other pages, other files) -----------------------
    WEB_SCHEMES = ("http://", "https://", "mailto:", "ftp://")

    def links(self, index):
        """[(rect as displayed, link dict)] of the page's links (cached until the next edit)."""
        key = ("links", index)
        if key not in self._card_cache:
            try:
                lst = self.doc[index].get_links()
                for ln in lst:
                    ln["kz_border"] = link_border(self.doc, ln.get("xref"))
                self._card_cache[key] = [(pymupdf.Rect(ln["from"]), ln) for ln in lst]
            except Exception:
                self._card_cache[key] = []
        return self._card_cache[key]

    def link_at(self, index, pt):
        """The link under unrotated page point pt, or None."""
        lst = self.links(index)
        if not lst:
            return None
        disp = pymupdf.Point(pt) * self.doc[index].rotation_matrix
        # the smallest one: the words' link, not the link of a cloud drawn around them
        hits = [(abs(r), ln) for r, ln in lst if disp in r]
        return min(hits, key=lambda h: h[0])[1] if hits else None

    def link_to_follow(self, index, pt):
        """The link a click at pt follows (Hand tool, Ctrl+click with Select): on a markup,
        only a link made on that markup; a link merely under a markup (the PDF's own link on
        highlighted words) leaves the click to the markup."""
        link = self.link_at(index, pt)
        if link is None or not self.show_markups:
            return link
        page, a = self._annot_under(index, pt)
        if a is None:
            return link
        from . import links
        try:
            own = links.attached(page, annotations.bounds(annotations.read(a)), "markup")
        except Exception:
            own = []
        return link if any(ln["xref"] == link.get("xref") for ln in own) else None

    def link_tip(self, link):
        k = link.get("kind")
        if k == pymupdf.LINK_URI:
            return link.get("uri", "")
        if k in (pymupdf.LINK_GOTO, pymupdf.LINK_NAMED) and link.get("page", -1) >= 0:
            return tr("Go to page {page}").format(page=link["page"] + 1)
        if k == pymupdf.LINK_NAMED:
            return link.get("name") or link.get("nameddest") or tr("Link")
        if k in (pymupdf.LINK_GOTOR, pymupdf.LINK_LAUNCH):
            return tr("Open {file}").format(file=link.get("file") or tr("file"))
        return tr("Link")

    def _go_to(self, page, to=None):
        if not 0 <= page < self.doc.page_count:
            return
        y = 0
        if to is not None:
            pg = self.doc[page]
            y = max(0, (pymupdf.Point(to) * pg.rotation_matrix).y * self.zoom - 20)
        self.goto_page(page, y)

    def follow_link(self, link):
        """Click on a link: go to the page, open the web address (asking first, like Adobe
        and PDF-XChange, unless you said not to ask again), or open the other file."""
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        k = link.get("kind")
        if k in (pymupdf.LINK_GOTO, pymupdf.LINK_NAMED) and link.get("page", -1) >= 0:
            self._go_to(link["page"], link.get("to"))
            return
        if k == pymupdf.LINK_NAMED:
            name = (link.get("name") or "").lower()
            cur = self.current_page()
            target = {"nextpage": cur + 1, "prevpage": cur - 1, "firstpage": 0,
                      "lastpage": self.doc.page_count - 1}.get(name)
            if target is not None:
                self._go_to(target)
            return
        if k == pymupdf.LINK_URI:
            uri = (link.get("uri") or "").strip()
            if uri.lower().startswith("file:"):
                self._open_linked_file(QUrl(uri).toLocalFile(), -1)
                return
            if not uri.lower().startswith(self.WEB_SCHEMES):
                QMessageBox.information(self, tr("Link"),
                                        tr("KanzonasPDF doesn't open this kind of link:")
                                        + "\n" + uri[:300])
                return
            if not self._confirm_web(uri):
                return
            QDesktopServices.openUrl(QUrl(uri))
            return
        if k in (pymupdf.LINK_GOTOR, pymupdf.LINK_LAUNCH):
            self._open_linked_file(link.get("file") or "", link.get("page", -1))

    def _ask_link(self, current=None, text_choice=None, look="box"):
        from .link_dialog import LinkDialog
        dlg = LinkDialog(self, self.doc.page_count, current, text_choice, look)
        return dlg.result_value if dlg.exec() else None

    def _area_is_blank(self, index, rect):
        """Nothing under rect yet (no letters, pictures or shapes): a link drawn there brings
        its own text."""
        r = pymupdf.Rect(rect)
        if any(pymupdf.Rect(w[:4]).intersects(r) for w in self._words(index) if w[4].strip()):
            return False
        objs = self.content_objects(index)
        from .page_objects import overlap
        return not any(overlap(it["rect"], r) and not it.get("whole")
                       for it in (objs.items if objs is not None else []))

    def add_link(self, index, rect, target=None, rects=None, text_lines=False, look=None,
                 text_at=None):
        """Make rect (or rects, all acting as one; unrotated page coordinates) clickable.
        target: ("uri", address) or ("page", index), then optionally the look ("underline",
        "box", "none"; True / False = box / none) and the link's own text to write into the
        page; asked for when None. text_at: (baseline start, size) where its own text goes;
        when given, the window offers "Text to show"."""
        from . import links
        from .link_dialog import look_of
        rects = [pymupdf.Rect(r).normalize() for r in (rects or [rect])]
        if target is None:
            choice = {"text": "", "write": True} if text_at is not None else None
            target = self._ask_link(text_choice=choice, look=look or "box")
        if not target or target[0] == "delete":
            return
        how = look_of(target[2]) if len(target) > 2 else (look or "box")
        words = target[3] if len(target) > 3 else None
        text = None
        if words and text_at is not None:
            text = {"text": words, "origin": pymupdf.Point(text_at[0]), "size": text_at[1]}

        def do():
            links.add(self.doc[index], rects, target[:2], how, text, text_lines)
        self.modify(do, [index], permission=pymupdf.PDF_PERM_MODIFY if text
                    else pymupdf.PDF_PERM_ANNOTATE)
        if text:
            self._fonts_added = True
        self.statusMessage.emit(tr("Link added (Ctrl+Z undoes it)"))

    def _link_current(self, index, link):
        """(kind, value, look, text) of an existing link for the link window, the areas
        acting with it, and whether they're lines of text."""
        from . import links
        page = self.doc[index]
        grp = links.group(page, link.get("xref")) or []
        first = grp[0] if grp else {}
        look = first.get("look") or ("box" if link_border(self.doc, link.get("xref"))
                                     else "none")
        k = link.get("kind")
        value = link.get("page", 0) if k == pymupdf.LINK_GOTO else link.get("uri") or ""
        kind = "page" if k == pymupdf.LINK_GOTO else "uri"
        return (kind, value, look, first.get("text")), grp

    def edit_link(self, index, link, target=None):
        """Change where a link goes, how it looks or the text it wrote, or delete it (target
        ("delete",)). All the areas acting as one link change together."""
        from . import links
        current, grp = self._link_current(index, link)
        if target is None:
            choice = {"text": current[3], "write": True} if current[3] else None
            target = self._ask_link(current, choice)
        if not target:
            return
        page = self.doc[index]
        if not grp:
            grp = [{"xref": link.get("xref"), "under": None, "text": None, "group": None,
                    "look": None,
                    "rect": pymupdf.Rect(link["from"]) * page.derotation_matrix}]
        rects = [g["rect"] for g in grp]
        wrote = next((g["text"] for g in grp if g["text"]), None)
        origin = size = None
        if wrote:
            hit = [ln for r, ln in text_edit.text_lines(page)
                   if any(g["rect"].contains(pymupdf.Point((r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2))
                          for g in grp)]
            if hit:
                origin = pymupdf.Point(hit[0]["spans"][0]["origin"])
                size = max(s["size"] for s in hit[0]["spans"])
        on_text = any(g["under"] and g["under"][1] < g["rect"].y1 - 0.5 and
                      g["under"][3] < g["rect"].y1 - 0.5 for g in grp)
        from .link_dialog import look_of
        how = look_of(target[2]) if len(target) > 2 else current[2]
        words = target[3] if len(target) > 3 else wrote
        xrefs = {g["xref"] for g in grp}

        def do():
            pg = self.doc[index]
            mine = [ln for ln in links.read(pg) if ln["xref"] in xrefs]
            if not mine:
                raise ValueError(tr("The link is no longer on the page."))
            for g in mine:
                if not g["group"]:
                    g["text"] = None            # (a link from elsewhere wrote nothing)
            # its own text is rewritten only when it changed
            keep_text = not wrote or (words == wrote and target[0] != "delete")
            links.remove(pg, mine, keep_text=keep_text)
            if target[0] == "delete":
                return
            text = None
            if wrote and words and not keep_text and origin is not None:
                text = {"text": words, "origin": origin, "size": size}
            if text:
                links.add(pg, [], target[:2], how, text)
            else:
                gid = links.add(pg, rects, target[:2], how, None, on_text or bool(wrote),
                                [g.get("on") for g in grp])
                if wrote and keep_text:
                    # the same words stay: the new link keeps owning them
                    for ln in links.read(pg):
                        if ln["group"] == gid:
                            pg.parent.xref_set_key(ln["xref"], "KZText", links._pdf_string(wrote))
        self.modify(do, [index], permission=pymupdf.PDF_PERM_MODIFY if wrote
                    else pymupdf.PDF_PERM_ANNOTATE)
        self.statusMessage.emit(tr("Link deleted (Ctrl+Z undoes it)") if target[0] == "delete"
                                else tr("Link changed (Ctrl+Z undoes it)"))

    def remove_link_at(self, index, pt):
        """Right-click > Remove link: the link goes, what it was on stays (its own text,
        written by the link, goes with it)."""
        ln = self.link_at(index, pt)
        if ln is not None:
            self.edit_link(index, ln, ("delete",))

    def _selection_link_areas(self):
        """[(page index, rects, lines of text?, what each rect is)] for what's selected: text
        (each line), markups (each one's box) or the page's own objects (each one's box), and
        the look that suits it."""
        if self.text_sel:
            return [(i, [r for r in self.line_rects(words)], True, "text")
                    for i, words in self.text_sel], "underline"
        if self.selection is not None:
            index = self.selection[0]
            return [(index, [annotations.bounds(m) for _x, m in self.selected_models()],
                     False, "markup")], "none"
        if self.obj_sel is not None:
            index, items = self.obj_sel
            return [(index, [pymupdf.Rect(it["rect"]) for it in items], False,
                     [self._obj_on(it) for it in items])], "none"
        return [], "none"

    @staticmethod
    def _obj_on(item):
        """What a link on an Edit objects item is made on (links.ONS)."""
        return "text" if item["kind"] == "text" else "object"

    def add_link_to_selection(self):
        """Right-click > Add link...: the selected text, markups or objects become one link."""
        from . import links
        from .link_dialog import look_of
        areas, look = self._selection_link_areas()
        areas = [a for a in areas if a[1]]
        if not areas:
            self.statusMessage.emit(tr("Select text, markups or objects first"))
            return
        target = self._ask_link(look=look)
        if not target or target[0] == "delete":
            return
        how = look_of(target[2]) if len(target) > 2 else look

        def do():
            for index, rects, on_text, on in areas:
                links.add(self.doc[index], rects, target[:2], how, None, on_text, on)
        self.modify(do, [a[0] for a in areas], permission=pymupdf.PDF_PERM_ANNOTATE)
        self.clear_text_selection()
        self.statusMessage.emit(tr("Link added (Ctrl+Z undoes it)"))

    def _confirm_web(self, uri):
        from PySide6.QtWidgets import QCheckBox
        from . import paths
        s = paths.settings()
        if s.value("links_dont_ask", "false") == "true":
            return True
        box = QMessageBox(QMessageBox.Question, tr("Open link"),
                          tr("This document wants to open:\n\n{address}\n\nOpen it in your "
                             "browser (or email program)?").format(address=uri[:500]),
                          QMessageBox.Yes | QMessageBox.No, self)
        box.setDefaultButton(QMessageBox.Yes)
        again = QCheckBox(tr("Don't ask again"))
        box.setCheckBox(again)
        if box.exec() != QMessageBox.Yes:
            return False
        if again.isChecked():
            s.setValue("links_dont_ask", "true")
        return True

    @staticmethod
    def _is_network_path(path):
        """A \\\\server\\share path, or a mapped network drive (Windows)."""
        p = str(path).replace("/", "\\")
        if p.startswith("\\\\"):
            return True
        if os.name == "nt" and len(p) >= 2 and p[1] == ":":
            try:
                import ctypes
                return ctypes.windll.kernel32.GetDriveTypeW(p[:2] + "\\") == 4   # DRIVE_REMOTE
            except (AttributeError, OSError):
                return False
        return False

    def _open_linked_file(self, path, page):
        """A link to another file: PDFs open here (at the page); other files with the program
        Windows uses for them, after asking; programs and scripts are refused."""
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        if not path:
            return
        if "%" in path:
            # MuPDF hands file names back percent-encoded ("Framing%20Plan.pdf"), also for
            # the plain /F strings CAD exporters write
            from urllib.parse import unquote
            path = unquote(path)
        if not os.path.isabs(path) and self.path:
            path = os.path.join(os.path.dirname(self.path), path)
        path = os.path.normpath(path)
        if self._is_network_path(path):
            # even checking that it exists makes Windows send your sign-in to that computer
            if QMessageBox.question(
                    self, tr("Link"),
                    tr("This link points to a file on another computer:\n\n{path}\n\nOpening "
                       "it sends your Windows sign-in to that computer. Open it?").format(
                        path=path),
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
                return
        if not os.path.exists(path):
            QMessageBox.information(self, tr("Link"),
                                    tr("The linked file isn't there:\n{path}").format(path=path))
            return
        ext = os.path.splitext(path)[1].lower()
        if ext == ".pdf":
            self.openFileRequested.emit(path, page)
            return
        if ext in self.RISKY or ext not in self.SAFE_OPEN:
            QMessageBox.warning(self, tr("Link"),
                                tr("This link would open a program, a script or a file with "
                                   "macros, which KanzonasPDF doesn't do from a PDF:\n{path}")
                                .format(path=path))
            return
        if QMessageBox.question(self, tr("Open file"),
                                tr("This document wants to open:\n\n{path}\n\nOpen it?")
                                .format(path=path)) == QMessageBox.Yes:
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def open_attachment(self, page_index, key, name):
        """Open an attached file with the program Windows uses for it."""
        import tempfile
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        name = self.safe_file_name(name)
        if os.path.splitext(name)[1].lower() not in self.SAFE_OPEN:
            QMessageBox.warning(
                self, tr("Open attached file"),
                tr("{name} could be a program, a script or a file with macros. KanzonasPDF "
                   "doesn't open that kind of file from a PDF.\n\n"
                   "Use Save as and open it yourself if you trust it.").format(name=name))
            return None
        if QMessageBox.question(self, tr("Open attached file"),
                                tr("Open {name}?\n\nOnly open files from people you trust.")
                                .format(name=name)) \
                != QMessageBox.Yes:
            return None
        folder = tempfile.mkdtemp(prefix="kzattach")
        path = os.path.join(folder, name)
        with open(path, "wb") as f:
            f.write(self.attachment_data(page_index, key))
        self._mark_downloaded(path)
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        return path

    def save_attachment(self, page_index, key, name, path=None):
        path = path or dialogs.save_file(self, tr("Save attached file"), self.safe_file_name(name))
        if path:
            with open(path, "wb") as f:
                f.write(self.attachment_data(page_index, key))
        return path

    def delete_attachment(self, page_index, key):
        if page_index is None:
            self.modify(lambda: self.doc.embfile_del(key), [], permission=pymupdf.PDF_PERM_ANNOTATE)
        else:
            page = self.doc[page_index]
            self.clear_selection()
            self.modify(lambda: page.delete_annot(page.load_annot(key)), [page_index], permission=pymupdf.PDF_PERM_ANNOTATE)

    def place_stamp(self, index, pt):
        from . import stamps
        props = self.tool_props("stamp")
        label = props.get("label") or ""
        if not label.startswith(stamps.FORM_PREFIX):
            self._create(index, {"kind": "stamp", "props": props,
                                 "rect": self.stamp_rect(index, pt)})
            return
        values = stamps.ask_form_values(self, label)        # PO #, date ordered, ...
        if values is None:
            return
        page = self.doc[index]
        self._create(index, {"kind": "stamp", "props": props, "detail": "\n".join(values),
                             "rect": self._form_stamp_rect(page, label, values, props,
                                                           pymupdf.Point(pt) * page.rotation_matrix)})

    @staticmethod
    def _form_stamp_rect(page, label, values, props, center):
        """Unrotated rect for a fill-in stamp centered on a display point, sized to its text."""
        from . import stamps
        png, aspect = stamps.render_form(stamps.form_fields(label), values,
                                         props.get("stroke") or "#c00000")
        img = QImage.fromData(png)
        w = img.width() / stamps.SCALE * 0.75
        h = w * aspect
        disp = pymupdf.Rect(center.x - w / 2, center.y - h / 2, center.x + w / 2, center.y + h / 2)
        return disp * page.derotation_matrix

    def apply_ink(self, index, pts):
        self._create(index, {"kind": "ink", "props": self.tool_props("ink"),
                             "strokes": [pts], "rect": pymupdf.Rect()})

    def apply_point_tool(self, index, tool, pt):
        page = self.doc[index]
        if tool == "attach":
            self.attach_file(index, pt)
            return
        if tool == "note":
            text, ok = dialogs.get_text(self, tr("Sticky note"), tr("Note:"))
            if not ok or not text.strip():
                return
            self._create(index, {"kind": "note", "props": self.tool_props("note"),
                                 "rect": pymupdf.Rect(pt, pt + (20, 20)), "text": text})
        elif tool == "eraser":
            target = self._annot_at(page, pt, self._hit_tol())
            if target is None:
                return
            xref = target.xref
            self.clear_selection()
            self.modify(lambda: page.delete_annot(page.load_annot(xref)), [index], permission=pymupdf.PDF_PERM_ANNOTATE)

    # ---- hit testing --------------------------------------------------------------
    @staticmethod
    def _seg_dist(p, a, b):
        ax, ay, bx, by = a[0], a[1], b[0], b[1]
        dx, dy = bx - ax, by - ay
        L = dx * dx + dy * dy
        t = 0 if L == 0 else max(0, min(1, ((p.x - ax) * dx + (p.y - ay) * dy) / L))
        cx, cy = ax + t * dx, ay + t * dy
        return ((p.x - cx) ** 2 + (p.y - cy) ** 2) ** 0.5

    @classmethod
    def _annot_hit(cls, annot, pt, tol=4.0):
        """Precise hit test: strokes must be clicked near the line, not anywhere in their box."""
        t = annot.type[0]
        if t == pymupdf.PDF_ANNOT_POPUP:
            return False
        if (annot.flags or 0) & (pymupdf.PDF_ANNOT_IS_LOCKED | pymupdf.PDF_ANNOT_IS_HIDDEN):
            return False                   # locked / hidden: clicks go through to what's below
        if not (+annot.rect + (-tol, -tol, tol, tol)).contains(pt):
            return False
        width = (annot.border or {}).get("width") or 1
        tol = tol + width
        if t == pymupdf.PDF_ANNOT_INK:
            for stroke in annot.vertices or []:
                if len(stroke) == 1 and cls._seg_dist(pt, stroke[0], stroke[0]) <= tol:
                    return True
                if any(cls._seg_dist(pt, stroke[k], stroke[k + 1]) <= tol
                       for k in range(len(stroke) - 1)):
                    return True
            return False
        if t in (pymupdf.PDF_ANNOT_LINE, pymupdf.PDF_ANNOT_POLY_LINE):
            v = annot.vertices or []
            return any(cls._seg_dist(pt, v[k], v[k + 1]) <= tol for k in range(len(v) - 1))
        if t in (pymupdf.PDF_ANNOT_HIGHLIGHT, pymupdf.PDF_ANNOT_UNDERLINE,
                 pymupdf.PDF_ANNOT_STRIKE_OUT, pymupdf.PDF_ANNOT_SQUIGGLY):
            v = annot.vertices or []
            for k in range(0, len(v) - 3, 4):
                if pymupdf.Quad(v[k:k + 4]).rect.contains(pt):
                    return True
            return False
        if t in (pymupdf.PDF_ANNOT_SQUARE, pymupdf.PDF_ANNOT_CIRCLE, pymupdf.PDF_ANNOT_POLYGON):
            return cls._shape_hit(annot, pt, tol, width)
        return annot.rect.contains(pt)

    @classmethod
    def _shape_hit(cls, annot, pt, tol, width):
        """Rectangles, ellipses and polygons (clouds, areas): a filled one is hit anywhere
        inside, an unfilled one only near its outline (or on its measurement label), so a
        press inside a room outline draws or selects what's in the room, like Bluebeam."""
        t = annot.type[0]
        filled = bool((annot.colors or {}).get("fill"))
        rd = cls._annot_rd(annot)
        cloud = (annot.border or {}).get("clouds", 0) or 0
        if t == pymupdf.PDF_ANNOT_POLYGON:
            v = annot.vertices or []
            if len(v) < 2:
                return annot.rect.contains(pt)
            inside = cls._in_polygon(pt, v)
            if filled and inside:
                return True
            d = min(cls._seg_dist(pt, v[k], v[(k + 1) % len(v)]) for k in range(len(v)))
            # cloud bumps lie outside the outline, up to the /RD margin
            if d <= tol or (not inside and cloud and d <= tol + max(rd)):
                return True
        else:
            r = annot.rect
            inner = pymupdf.Rect(r.x0 + rd[0], r.y0 + rd[1], r.x1 - rd[2], r.y1 - rd[3])
            if t == pymupdf.PDF_ANNOT_SQUARE:
                if filled and inner.contains(pt):
                    return True
                hole = inner + (tol, tol, -tol, -tol)
                if hole.is_empty or not hole.contains(pt):
                    return True
            else:
                cx, cy = (inner.x0 + inner.x1) / 2, (inner.y0 + inner.y1) / 2
                a, b = max(inner.width / 2, 1e-6), max(inner.height / 2, 1e-6)
                dx, dy = pt.x - cx, pt.y - cy
                k = ((dx / a) ** 2 + (dy / b) ** 2) ** 0.5
                if filled and k <= 1:
                    return True
                # distance to the ellipse along the ray from its center
                d = abs(1 - 1 / k) * (dx * dx + dy * dy) ** 0.5 if k else min(a, b)
                if d <= tol or (k > 1 and cloud and d <= tol + max(rd)):
                    return True
        return cls._label_hit(annot, pt, tol)

    @staticmethod
    def _in_polygon(pt, v):
        inside = False
        for k in range(len(v)):
            (x0, y0), (x1, y1) = v[k - 1], v[k]
            if (y0 > pt.y) != (y1 > pt.y) and \
                    pt.x < x0 + (pt.y - y0) * (x1 - x0) / (y1 - y0):
                inside = not inside
        return inside

    @staticmethod
    def _label_hit(annot, pt, tol):
        """The point is on an area / perimeter / volume measurement's label."""
        doc = annot.parent.parent
        try:
            typ, val = doc.xref_get_key(annot.xref, annotations.KZ_KEY)
            stored = json.loads(val) if typ == "string" else {}
        except (ValueError, RuntimeError):
            return False
        kind = stored.get("kind")
        content = annot.info.get("content", "")
        if kind not in annotations.CLOSED_MEASURES or ": " not in content or not annot.vertices:
            return False
        from . import measure
        page = annot.parent
        anchor, _angle = measure.label_anchor(kind, annot.vertices, page)
        size = float(stored.get("props", {}).get("fontsize", 9))
        lines = content.split(": ", 1)[1].split(", ")
        w = max(pymupdf.get_text_length(s, fontname="helv", fontsize=size) for s in lines) / 2 + 2
        h = size * 1.2 * len(lines) / 2 + 1
        if page.rotation % 180:
            w, h = h, w
        return abs(pt.x - anchor.x) <= w + tol and abs(pt.y - anchor.y) <= h + tol

    @classmethod
    def _annot_at(cls, page, pt, tol=4.0):
        """Smallest annotation actually under the point (so big shapes don't swallow clicks)."""
        hits = [an for an in annotations.each_annot(page) if cls._annot_hit(an, pt, tol)]
        if not hits:
            return None
        return min(hits, key=lambda an: an.rect.get_area())

    def _annot_boxes(self, index):
        """[(rect, xref)] of a page's annotations, cached until the page changes, so moving
        the mouse over a page with thousands of markups doesn't load every one of them."""
        key = ("annotx", index)
        boxes = self._card_cache.get(key)
        if boxes is None:
            page = self.doc[index]              # keep the Page alive while reading its annots
            # plain numbers: building and testing pymupdf.Rect objects is slow in Python
            boxes = [(tuple(a.rect), a.xref) for a in annotations.each_annot(page)
                     if a.type[0] != pymupdf.PDF_ANNOT_POPUP]
            self._card_cache[key] = boxes
        return boxes

    def _hit_tol(self):
        """How near (in page points) a press must be to a markup's line: 4 screen pixels."""
        return 4.0 / max(self.zoom, 0.05)

    def _annot_under(self, index, pt, tol=None):
        """Like _annot_at, but loads only the annotations whose box is near the point.
        Returns (page, annot): keep the page alive while using the annot."""
        if tol is None:
            tol = self._hit_tol()
        page = self.doc[index]
        px, py = pt.x, pt.y
        near = [x for (x0, y0, x1, y1), x in self._annot_boxes(index)
                if x0 - tol <= px <= x1 + tol and y0 - tol <= py <= y1 + tol]
        hits = [an for an in (page.load_annot(x) for x in near)
                if an is not None and self._annot_hit(an, pt, tol)]
        return page, (min(hits, key=lambda an: an.rect.get_area()) if hits else None)

    def annot_at(self, index, pt):
        """xref of the annotation under pt, or None. (Returns an id, not an Annot: an Annot
        becomes unusable once its Page object is garbage collected.)"""
        if not self.show_markups:
            return None
        _page, a = self._annot_under(index, pt)
        return a.xref if a is not None else None

    def annot_label(self, index, pt):
        """The kind of markup under pt ("Cloud", "Highlight"...), or ""."""
        _page, a = self._annot_under(index, pt)
        if a is None:
            return ""
        model = annotations.read(a)
        return annotations.LABELS.get(model["kind"], a.type[1]) if model else a.type[1]

    def annot_tooltip(self, index, pt):
        page, a = self._annot_under(index, pt)
        if a is None:
            return ""
        label = self.annot_label(index, pt)
        content = a.info.get("content", "")
        return f"{label}: {content}" if content else label

    @staticmethod
    def _annot_in_box(annot, box):
        """For drag-erase: the annotation lies entirely inside the box,
        or (for pen strokes and lines) any of its points is inside."""
        if annot.type[0] == pymupdf.PDF_ANNOT_POPUP or (annot.flags or 0) & (
                pymupdf.PDF_ANNOT_IS_LOCKED | pymupdf.PDF_ANNOT_IS_HIDDEN):
            return False
        if box.contains(annot.rect):
            return True
        if annot.type[0] in (pymupdf.PDF_ANNOT_INK, pymupdf.PDF_ANNOT_LINE,
                             pymupdf.PDF_ANNOT_POLY_LINE):
            pts = annot.vertices or []
            if pts and isinstance(pts[0], list):
                pts = [p for stroke in pts for p in stroke]
            return any(box.contains(pymupdf.Point(p)) for p in pts)
        return False

    # ---- selecting and editing existing annotations ----------------------------
    def select_xref(self, index, xref, add=False):
        """Select one annotation. add=True (Ctrl+click) adds it to / removes it from the
        selection instead; the first one selected stays the alignment reference."""
        if add and self.selection is not None and self.selection[0] == index and xref:
            xrefs = self.selected_xrefs()
            if xref in xrefs:
                xrefs.remove(xref)
            else:
                xrefs.append(xref)
            self._set_selection(index, xrefs)
            return True
        page = self.doc[index]
        annot = page.load_annot(xref) if xref else None
        model = annotations.read(annot) if annot else None
        old = self.selection
        self.selection = (index, xref) if model else None
        self.selected_model = model
        self.extra = []
        for i in {index, old[0] if old else index}:
            if 0 <= i < len(self.pages):
                self.pages[i].update()
        self.selectionChanged.emit()
        return model is not None

    def _set_selection(self, index, xrefs):
        """Select these xrefs (in order) on one page; unreadable ones are skipped."""
        page = self.doc[index]
        keep, first = [], None
        found = annotations.load_annots(page, xrefs)
        for x in xrefs:
            try:
                m = annotations.read(found[x]) if x in found else None
            except Exception:
                m = None
            if m is not None and x not in keep:
                keep.append(x)
                first = first or m
        old = self.selection
        if not keep:
            self.selection, self.selected_model, self.extra = None, None, []
        else:
            self.selection = (index, keep[0])
            self.selected_model = first
            self.extra = keep[1:]
        for i in {index, old[0] if old else index}:
            if 0 <= i < len(self.pages):
                self.pages[i].update()
        self.selectionChanged.emit()

    def selected_xrefs(self):
        if self.selection is None:
            return []
        return [self.selection[1]] + list(self.extra)

    def selected_models(self):
        """[(xref, model)] for everything selected, first-selected first."""
        if self.selection is None:
            return []
        page = self.doc[self.selection[0]]
        out = []
        xrefs = self.selected_xrefs()
        found = annotations.load_annots(page, xrefs)
        for x in xrefs:
            try:
                m = annotations.read(found[x]) if x in found else None
            except Exception:
                m = None
            if m is not None:
                out.append((x, m))
        return out

    @classmethod
    def _annot_geometry(cls, annot):
        """(lines, closed outline or None, filled) of a markup, for CAD selection regions:
        the lines it draws (or its box), and for rectangles, ellipses and polygons the outline
        whose inside a crossing region can be on."""
        t = annot.type[0]
        v = annot.vertices or []
        r = annot.rect
        box = [[r.tl, r.tr, r.br, r.bl, r.tl]]
        if t == pymupdf.PDF_ANNOT_INK and v:
            return [list(s) for s in v], None, False
        if t in (pymupdf.PDF_ANNOT_LINE, pymupdf.PDF_ANNOT_POLY_LINE) and v:
            return [list(v)], None, False
        if t in (pymupdf.PDF_ANNOT_HIGHLIGHT, pymupdf.PDF_ANNOT_UNDERLINE,
                 pymupdf.PDF_ANNOT_STRIKE_OUT, pymupdf.PDF_ANNOT_SQUIGGLY) and v:
            quads = [pymupdf.Quad(v[k:k + 4]).rect for k in range(0, len(v) - 3, 4)]
            return [[q.tl, q.tr, q.br, q.bl, q.tl] for q in quads], "quads", True
        if t not in (pymupdf.PDF_ANNOT_SQUARE, pymupdf.PDF_ANNOT_CIRCLE,
                     pymupdf.PDF_ANNOT_POLYGON):
            return box, "box", True
        filled = bool((annot.colors or {}).get("fill"))
        if t == pymupdf.PDF_ANNOT_POLYGON and len(v) >= 2:
            outline = list(v) + [v[0]]
        else:
            rd = cls._annot_rd(annot)
            inner = pymupdf.Rect(r.x0 + rd[0], r.y0 + rd[1], r.x1 - rd[2], r.y1 - rd[3])
            if t == pymupdf.PDF_ANNOT_SQUARE:
                outline = [inner.tl, inner.tr, inner.br, inner.bl, inner.tl]
            else:
                cx, cy = (inner.x0 + inner.x1) / 2, (inner.y0 + inner.y1) / 2
                a, b = inner.width / 2, inner.height / 2
                outline = [(cx + a * math.cos(k * math.pi / 24),
                            cy + b * math.sin(k * math.pi / 24)) for k in range(49)]
        return [outline], "outline", filled

    @classmethod
    def _annot_picked(cls, annot, region, crossing):
        """A CAD selection region (page_objects.Box or Lasso) takes this markup: a window one
        lying entirely inside it; a crossing one also when its line or outline runs through
        the region, or the region is on its filling, its highlighted words, or (text boxes,
        notes, stamps and the like) anywhere on it."""
        from .page_objects import Box, overlap
        if not overlap(annot.rect + (-1, -1, 1, 1), region.bounds):
            return False
        lines, closed, filled = cls._annot_geometry(annot)
        if region.contains_rect(annot.rect) if isinstance(region, Box) else \
                region.contains_lines(lines):
            return True
        if not crossing:
            return False
        if region.touches_lines(lines):
            return True
        if closed in ("box", "quads") or filled:
            inner = pymupdf.Point(region.inner_point())
            return any(cls._in_polygon(inner, line[:-1]) for line in lines)
        return False

    @staticmethod
    def _annot_rd(annot):
        """The markup's /RD margins (cloud bumps, line width) as [left, top, right, bottom]."""
        try:
            typ, val = annot.parent.parent.xref_get_key(annot.xref, "RD")
            rd = [float(x) for x in val.strip("[]").split()] if typ == "array" else []
        except (ValueError, RuntimeError):
            rd = []
        return rd if len(rd) == 4 else [0.0] * 4

    def cad_select_region(self, index, region, crossing=False, remove=False):
        """CAD mode, Select tool: a window (a box dragged left to right, or a lasso drawn
        rightward) takes the markups lying entirely inside it, a crossing one (leftward) the
        ones it touches; region is a page_objects.Box or Lasso. They are added to what's
        selected (Shift: taken out of it). A region that takes no markups takes text the
        same way: characters inside it, or touched. Returns what it took."""
        found = self.cad_markups_in(index, region, crossing)
        if found:
            have = self.selected_xrefs() if self.selection is not None and \
                self.selection[0] == index else []
            if remove:
                self._set_selection(index, [x for x in have if x not in found])
            else:
                self._set_selection(index, have + [x for x in found if x not in have])
            return "markups"
        words = self.cad_text(index, region, crossing)
        have = [ws for i, ws in (self.text_sel or []) if i == index]
        have = set(have[0]) if have else set()
        took = set(words)
        keep = have - took if remove else have | took
        self.set_text_selection(index, [w for w in self._words(index) if w in keep])
        return "text" if words else None

    def cad_markups_in(self, index, region, crossing=False):
        """The markups (xrefs) a CAD region takes: entirely inside a window, touched by a
        crossing one."""
        page = self.doc[index]
        found = []
        if self.show_markups:
            for an in annotations.each_annot(page):
                if an.type[0] == pymupdf.PDF_ANNOT_POPUP or (an.flags or 0) & (
                        pymupdf.PDF_ANNOT_IS_LOCKED | pymupdf.PDF_ANNOT_IS_HIDDEN):
                    continue
                if self._annot_picked(an, region, crossing) and annotations.read(an) is not None:
                    found.append(an.xref)
        return found

    def cad_preview(self, index, region, crossing=False, limit=3000):
        """What a CAD region would take if finished now, for the live highlight while it's
        drawn: (outlines [[Point...]], text rects) in page coordinates, at most limit
        outlines."""
        out, rects = [], []
        for lines, more in self.cad_preview_steps(index, region, crossing):
            out += lines
            rects += more
            if len(out) >= limit:
                break
        return out[:limit], rects

    def cad_preview_steps(self, index, region, crossing=False):
        """cad_preview a little at a time: yields (outlines, text rects) for each thing looked
        at (often nothing), so the highlight can be worked out in short slices."""
        if self.tool == "select":
            xrefs = self.cad_markups_in(index, region, crossing)
            if xrefs:
                page = self.doc[index]
                found = annotations.load_annots(page, xrefs[:3000])
                models = [(x, annotations.read(a)) for x, a in found.items()]
                yield self.cad_outlines(index, "markups",
                                        [(x, m) for x, m in models if m is not None]), []
            else:
                yield [], self.line_rects(self.cad_text(index, region, crossing))
            return
        from .page_objects import overlap
        objs = self.content_objects(index)
        for it, taken in (objs.pick_steps(region, crossing) if objs is not None else ()):
            yield (self.object_lines(index, it) if taken else []), []
        for it in self.text_objects(index):
            if overlap(it["rect"], region.bounds) and (
                    region.contains_rect(it["rect"]) or crossing and any(
                        region.touches_rect(r) for r, _ln in it["lines"])):
                r = it["rect"]
                yield [[r.tl, r.tr, r.br, r.bl, r.tl]], []

    def cad_text(self, index, region, crossing=False):
        """The characters a CAD region takes: inside a window, touched by a crossing one."""
        from .page_objects import overlap
        out = []
        for w in self._words(index):
            r = pymupdf.Rect(w[:4])
            if not overlap(r, region.bounds):
                continue
            if region.touches_rect(r) if crossing else region.contains_rect(r):
                out.append(w)
        return out

    def select_in_box(self, index, box, add=False):
        """Select the markups lying entirely inside box. Returns how many."""
        page = self.doc[index]
        found = []
        for an in annotations.each_annot(page):
            if an.type[0] == pymupdf.PDF_ANNOT_POPUP or (an.flags or 0) & (
                    pymupdf.PDF_ANNOT_IS_LOCKED | pymupdf.PDF_ANNOT_IS_HIDDEN):
                continue
            if box.contains(an.rect) and annotations.read(an) is not None:
                found.append(an.xref)
        if add and self.selection is not None and self.selection[0] == index:
            found = self.selected_xrefs() + [x for x in found if x not in self.selected_xrefs()]
        if found:
            self._set_selection(index, found)
        return len(found)

    def reveal(self, index, xref):
        """Scroll to an annotation and select it (used by the markups list)."""
        page = self.doc[index]
        try:
            r = page.load_annot(xref).rect * page.rotation_matrix
        except Exception:
            return
        self.goto_page(index, max(0, r.y0 * self.zoom - self.viewport().height() / 3))
        if self.tool != "select":
            self.selectToolRequested.emit()
        self.select_xref(index, xref)

    def clear_selection(self):
        if self.selection is None:
            return
        old = self.selection
        self.selection = None
        self.selected_model = None
        self.extra = []
        if 0 <= old[0] < len(self.pages):
            self.pages[old[0]].update()
        self.selectionChanged.emit()

    def commit_model(self, index, xref, model):
        """Replace annotation xref with a new version (one undo step); keep it selected."""
        if model["kind"] == "field":
            self._commit_field(index, xref, model)
            return
        self.commit_models(index, [(xref, model)])

    def commit_models(self, index, changes):
        """Replace several annotations in one undo step, keeping their stacking order and
        the selection (with the new xrefs)."""
        changes = [(x, m) for x, m in changes if m["kind"] != "field"]
        if not changes:
            return
        sel = self.selected_xrefs() if self.selection and self.selection[0] == index else []
        made = {}

        def do():
            from . import links
            page = self.doc[index]
            known = links.read(page)        # read once; follow() keeps them current
            models = dict(changes)
            for x, old, new in annotations.replace_many(page, changes):
                made[x] = new
                if old is not None and known:
                    links.follow(page, annotations.bounds(old), annotations.bounds(models[x]),
                                 on="markup", known=known)
        self.modify(do, [index], permission=pymupdf.PDF_PERM_ANNOTATE)
        if made:
            self._set_selection(index, [made.get(x, x) for x in sel] or list(made.values()))

    def update_selected_props(self, props):
        if self.selection is None or self.selected_model is None or \
                self.selected_model["kind"] == "field":
            return
        old = self.selected_model["props"]
        changed = {k: v for k, v in props.items() if old.get(k) != v}
        if not changed:
            return
        out = []
        for x, m in self.selected_models():
            if m["kind"] == "field":
                continue
            m = annotations.copy(m)
            keys = {k: v for k, v in changed.items() if k in m["props"] and k != "rotation"}
            if not keys and "rotation" not in changed:
                continue
            m["props"].update(keys)
            if m["kind"] == "stamp" and ("name" in keys or "date" in keys):
                m["detail"] = None              # redrawn with / without name and date
            if "rotation" in changed and "rotation" in m["props"]:
                m = annotations.rotated(m, changed["rotation"])
            out.append((x, m))
        self.commit_models(self.selection[0], out)

    NUDGE = {"": 1.0, "shift": 10.0, "ctrl": 0.1}     # points per arrow-key press

    def nudge(self, dx, dy, step):
        """Move the selected markups, or the pictures / shapes selected with Edit objects, by
        (dx, dy) * step points as seen on screen. Presses less than 1.5 s apart are one undo
        step. Returns True if something moved."""
        import time
        if self.obj_sel is not None:
            index = self.obj_sel[0]
        elif self.selection is not None:
            index = self.selection[0]
        else:
            return False
        page = self.doc[index]
        m_ = page.derotation_matrix
        d = pymupdf.Point(dx * step, dy * step) * m_ - pymupdf.Point(0, 0) * m_
        key = ("obj", index, tuple(it["n"] for it in self.obj_sel[1])) if self.obj_sel else \
            ("annot", index)
        now = time.monotonic()
        last = getattr(self, "_last_nudge", (None, 0.0))
        self._merge_edit = last[0] == key and now - last[1] < 1.5
        try:
            if self.obj_sel is not None:
                r = self.selected_objects_rect()
                self.move_objects(r + (d.x, d.y, d.x, d.y))
            else:
                changes = [(x, annotations.moved(m, d)) for x, m in self.selected_models()
                           if m["kind"] != "field" and annotations.movable(m)]
                if not changes:
                    return False
                self.commit_models(index, changes)
        finally:
            self._merge_edit = False
        self._last_nudge = (key, now)
        self.statusMessage.emit(tr("Moved {step} pt (Shift+arrow: 10 pt, Ctrl+arrow: 0.1 pt; "
                                   "Ctrl+Z undoes the whole series)").format(step="%g" % step))
        return True

    def delete_selected(self):
        if self.selection is None:
            return
        index, xref = self.selection
        if self.selected_model and self.selected_model["kind"] == "field" and not self.extra:
            self.delete_field(index, xref)
            return
        xrefs = self.selected_xrefs()
        self.clear_selection()
        page = self.doc[index]

        def do():
            from . import links
            for x in xrefs:
                try:
                    box = annotations.bounds(annotations.read(page.load_annot(x)))
                    page.delete_annot(page.load_annot(x))
                except Exception:
                    continue
                mine = links.attached(page, box, "markup")    # the links made for it go too
                if mine:
                    links.remove(page, mine, keep_text=True)
        self.modify(do, [index], permission=pymupdf.PDF_PERM_ANNOTATE)

    # ---- arrange: align, distribute, stacking order -------------------------------
    def _display_bounds(self, page, model):
        return annotations.bounds(model) * page.rotation_matrix

    def align(self, how, ref="first"):
        """how: left, hcenter, right, top, vmiddle, bottom (as seen on screen).
        ref: first selected (default), last selected, selection bounds, or page."""
        models = [(x, m) for x, m in self.selected_models() if annotations.movable(m)]
        if not models or (len(models) < 2 and ref != "page"):
            self.statusMessage.emit(tr("Select two or more markups to align (or align to the page)."))
            return
        index = self.selection[0]
        page = self.doc[index]
        boxes = [self._display_bounds(page, m) for _x, m in models]
        if ref == "page":
            target = pymupdf.Rect(page.rect)
        elif ref == "last":
            target = boxes[-1]
        elif ref == "selection":
            target = pymupdf.Rect(boxes[0])
            for b in boxes[1:]:
                target |= b
        else:
            target = boxes[0]
        to_pdf = page.derotation_matrix
        out = []
        for (x, m), b in zip(models, boxes):
            dx = dy = 0.0
            if how == "left":
                dx = target.x0 - b.x0
            elif how == "right":
                dx = target.x1 - b.x1
            elif how == "hcenter":
                dx = (target.x0 + target.x1 - b.x0 - b.x1) / 2
            elif how == "top":
                dy = target.y0 - b.y0
            elif how == "bottom":
                dy = target.y1 - b.y1
            elif how == "vmiddle":
                dy = (target.y0 + target.y1 - b.y0 - b.y1) / 2
            if abs(dx) > 1e-3 or abs(dy) > 1e-3:
                d = pymupdf.Point(dx, dy) * to_pdf - pymupdf.Point(0, 0) * to_pdf
                out.append((x, annotations.moved(m, d)))
        self.commit_models(index, out)

    def distribute(self, axis):
        """Equal gaps between the selected markups, horizontally ('h') or vertically ('v');
        the two outermost stay put."""
        models = [(x, m) for x, m in self.selected_models() if annotations.movable(m)]
        if len(models) < 3:
            self.statusMessage.emit(tr("Select three or more markups to distribute."))
            return
        index = self.selection[0]
        page = self.doc[index]
        items = [(x, m, self._display_bounds(page, m)) for x, m in models]
        lo = (lambda b: b.x0) if axis == "h" else (lambda b: b.y0)
        size = (lambda b: b.width) if axis == "h" else (lambda b: b.height)
        items.sort(key=lambda t: lo(t[2]) + size(t[2]) / 2)
        first, last = items[0][2], items[-1][2]
        span = lo(last) + size(last) - lo(first)
        gap = (span - sum(size(t[2]) for t in items)) / (len(items) - 1)
        to_pdf = page.derotation_matrix
        pos = lo(first)
        out = []
        for x, m, b in items:
            d = pos - lo(b)
            pos += size(b) + gap
            if abs(d) > 1e-3:
                v = pymupdf.Point(d, 0) if axis == "h" else pymupdf.Point(0, d)
                out.append((x, annotations.moved(m, v * to_pdf - pymupdf.Point(0, 0) * to_pdf)))
        self.commit_models(index, out)

    def arrange(self, how):
        """how: front, back, forward, backward (stacking order of the selected markups, or of
        the page's own pictures and shapes selected with Edit objects)."""
        if self.obj_sel is not None and self.selection is None:
            self.arrange_objects(how)
            return
        if self.selection is None:
            return
        index = self.selection[0]
        sel = self.selected_xrefs()

        def do():
            page = self.doc[index]
            order = annotations.annot_order(page)
            chosen = [x for x in order if x in sel]
            rest = [x for x in order if x not in sel]
            if how == "front":
                new = rest + chosen
            elif how == "back":
                new = chosen + rest
            else:
                new = list(order)
                idx = range(len(new) - 2, -1, -1) if how == "forward" else range(1, len(new))
                for i in idx:
                    j = i + 1 if how == "forward" else i - 1
                    if new[i] in sel and new[j] not in sel:
                        new[i], new[j] = new[j], new[i]
            annotations.set_annot_order(page, new)
        self.modify(do, [index], permission=pymupdf.PDF_PERM_ANNOTATE)
        self._set_selection(index, sel)

    def edit_annot_text(self, index, xref):
        page = self.doc[index]
        model = annotations.read(page.load_annot(xref))
        if model is None:
            return
        if not annotations.text_editable(model):
            what = annotations.LABELS.get(model["kind"], tr("markup")).lower()
            self.statusMessage.emit(tr("The {what}'s text is generated, so it can't be edited: "
                                       "add a note or a text box to comment on it").format(
                                           what=what))
            return
        from . import stamps
        label = model["props"].get("label") or ""
        if model["kind"] == "stamp" and label.startswith(stamps.FORM_PREFIX):
            # fill-in stamp: change the values; the stamp grows or shrinks to fit them
            values = stamps.ask_form_values(self, label, (model.get("detail") or "").split("\n"))
            if values is None or "\n".join(values) == model.get("detail"):
                return
            disp = model["rect"] * page.rotation_matrix
            model["detail"] = "\n".join(values)
            model["rect"] = self._form_stamp_rect(page, label, values, model["props"],
                                                  (disp.tl + disp.br) / 2)
            self.commit_model(index, xref, model)
            return
        title = annotations.LABELS.get(model["kind"], tr("Annotation"))
        text, ok = dialogs.get_text(self, tr("Edit {what}").format(what=title), tr("Text:"),
                                    model.get("text", ""))
        if not ok or text == model.get("text", ""):
            return
        model["text"] = text
        self.commit_model(index, xref, model)

    def edit_annot_at(self, index, pt):
        xref = self.annot_at(index, pt)
        if xref is None:
            return
        page = self.doc[index]
        an = page.load_annot(xref)
        if an.type[0] == pymupdf.PDF_ANNOT_FILE_ATTACHMENT:     # double-click opens the file
            self.open_attachment(index, xref, an.file_info.get("filename", "attachment"))
            return
        self.edit_annot_text(index, xref)

    def comment_cards(self, index):
        """[(anchor rect, text, xref)] for comments on this page (cached)."""
        if not self.show_markups:
            return []
        if index not in self._card_cache:
            cards = []
            page = self.doc[index]
            for a in annotations.each_annot(page):
                if a.type[0] not in (pymupdf.PDF_ANNOT_HIGHLIGHT, pymupdf.PDF_ANNOT_UNDERLINE,
                                     pymupdf.PDF_ANNOT_STRIKE_OUT, pymupdf.PDF_ANNOT_SQUIGGLY):
                    continue
                m = annotations.read(a)
                if m and m["kind"] == "comment":
                    cards.append((annotations.bounds(m), m.get("text", ""), a.xref))
            self._card_cache[index] = cards
        return self._card_cache[index]

    def keyPressEvent(self, e):
        if self._cad_cmd is not None and e.key() in (Qt.Key_Escape, Qt.Key_Return,
                                                     Qt.Key_Enter):
            if e.key() == Qt.Key_Escape:
                self._cad_cmd.cancel()
            else:
                self._cad_cmd.enter()
            return
        if e.key() == Qt.Key_Escape:
            from . import cad_select
            if cad_select.cancel(self):
                return
        drawing = [w for w in self.pages if w._poly]
        if drawing and e.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Escape):
            drawing[0].finish_poly(cancel=e.key() == Qt.Key_Escape)
            return
        if e.key() in (Qt.Key_Delete, Qt.Key_Backspace) and self.selection is not None:
            self.delete_selected()
            return
        if e.key() in (Qt.Key_Delete, Qt.Key_Backspace) and self.obj_sel is not None:
            self.delete_objects()
            return
        if e.key() == Qt.Key_Escape and self.cad_select and (
                self.obj_sel is not None or self.text_sel or self.selection is not None):
            # CAD mouse: clicks and boxes only add to the selection; Escape clears all of it
            self.clear_object_selection()
            self.clear_text_selection()
            self.clear_selection()
            return
        if e.key() == Qt.Key_Escape and self.obj_sel is not None:
            self.clear_object_selection()
            return
        if e.key() == Qt.Key_Escape and self.text_sel is not None:
            self.clear_text_selection()
            return
        if self.field_focus is not None and self.tool in ("hand", "select") and \
                e.key() in (Qt.Key_Space, Qt.Key_Return, Qt.Key_Enter) and not self.read_only:
            self.fill_field(*self.field_focus)
            return
        if e.key() == Qt.Key_Escape and self.field_focus is not None:
            old = self.field_focus
            self.field_focus = None
            self.pages[old[0]].update()
            return
        if e.key() == Qt.Key_Escape:
            if self.selection is not None:
                self.clear_selection()
                return
            # nothing selected: whatever tool is picked, Escape goes back to the default
            # tool (Preferences > Start-up: Hand or Select)
            self.previousToolRequested.emit()
            return
        arrows = {Qt.Key_Left: (-1, 0), Qt.Key_Right: (1, 0), Qt.Key_Up: (0, -1),
                  Qt.Key_Down: (0, 1)}
        mods = e.modifiers() & (Qt.ShiftModifier | Qt.ControlModifier | Qt.AltModifier)
        mod = {Qt.NoModifier: "", Qt.ShiftModifier: "shift",
               Qt.ControlModifier: "ctrl"}.get(mods)
        if e.key() in arrows and mod is not None and \
                (self.selection is not None or self.obj_sel is not None):
            if self.nudge(*arrows[e.key()], self.NUDGE[mod]):
                return
        if e.key() in (Qt.Key_Left, Qt.Key_Right) and not e.modifiers():
            # previous / next page (use Shift+arrows or the scrollbar to scroll sideways)
            self.goto_page(self.current_page() + (1 if e.key() == Qt.Key_Right else -1))
            return
        if e.key() in (Qt.Key_Home, Qt.Key_End) and \
                e.modifiers() in (Qt.NoModifier, Qt.ControlModifier):
            # first / last page (View > Go to), as in other PDF readers
            self.goto_page(0 if e.key() == Qt.Key_Home else self.page_count() - 1)
            return
        if e.key() in (Qt.Key_Left, Qt.Key_Right) and e.modifiers() == Qt.ShiftModifier:
            bar = self.horizontalScrollBar()
            bar.setValue(bar.value() + (1 if e.key() == Qt.Key_Right else -1) * bar.singleStep() * 3)
            return
        super().keyPressEvent(e)

    # ---- editing existing text --------------------------------------------
    def _lines(self, index):
        if index not in self._line_cache:
            self._line_cache[index] = text_edit.text_lines(self.doc[index])
        return self._line_cache[index]

    def text_line_rect(self, index, pt):
        hit = text_edit.line_at(self._lines(index), pt)
        return hit[0] if hit else None

    def text_target_rect(self, index, pt, one_line=False):
        """What a click with Edit text at pt edits, for the outline under the pointer: the
        whole paragraph (see edit_text_at), or the line (one_line: Alt held)."""
        hit = text_edit.line_at(self._lines(index), pt)
        if hit is None:
            return None
        rect, line = hit
        if one_line or self.doc[index].rotation or \
                text_edit.line_rotation(line) % 360:
            return rect
        key = id(line)
        cache = self._hover_para.setdefault(index, {})
        if key not in cache:
            para = self._paragraph_of(index, line)
            box = pymupdf.Rect(rect)
            for ln in para or []:
                box |= pymupdf.Rect(ln["bbox"])
            cache[key] = box
        return cache[key]

    def move_text_line(self, index, pt, offset):
        """Edit text tool, press on a line and drag: move it by offset (PDF points) without
        changing its text or font; comments and highlights on it move along."""
        self.commit_pending()
        hit = text_edit.line_at(self._lines(index), pt)
        if hit is None or not (offset[0] or offset[1]):
            return
        _rect, line = hit
        self._apply_text_edit(index, line, text_edit.line_text(line), offset, None,
                              keep_font=True)
        self.statusMessage.emit(tr("Moved the line (Ctrl+Z undoes it)"))

    def _paragraph_of(self, index, line):
        """The lines of the paragraph holding line (text_edit.paragraph_at), on an
        unrotated page: what a click with Edit text rewrites. None: edit the line."""
        if self.doc[index].rotation:
            return None
        lines = self._lines(index)
        if index not in self._row_cache:
            self._row_cache[index] = text_edit.paragraph_rows(lines)
        return text_edit.paragraph_at(lines, line, self._row_cache[index])

    @staticmethod
    def _bands(rows):
        """The letters' bands of text lines: [(x0, top, x1, bottom)] around each baseline
        (line boxes are taller than the letters and overlap at a tight line spacing)."""
        out = []
        for r, ln in rows:
            size = text_edit.main_span(ln)["size"]
            base = ln["spans"][0]["origin"][1]
            out.append((r.x0, base - 0.7 * size, r.x1, base + 0.15 * size))
        return out

    def _edit_paragraph(self, index, lines, pt):
        """Edit text on a paragraph: type in a box of the paragraph's width; the words
        rewrap as you type and the paragraph is rewritten in its font, size, line spacing and
        alignment."""
        old = text_edit.paragraph_text(lines)
        lay = text_edit.paragraph_layout(lines)
        size = lay["span"]["size"]
        box = pymupdf.Rect()
        for ln in lines:
            box |= pymupdf.Rect(ln["bbox"])
        # the other text on the page, to tell whether the rewritten paragraph runs into it
        mine = {id(sp) for ln in lines for sp in ln["spans"]}
        others = self._bands([(r, ln) for r, ln in self._lines(index)
                              if text_edit.visible(ln) and
                              not any(id(sp) in mine for sp in ln["spans"])])
        w = self.pages[index]
        chosen = self._edit_font()
        picked = self._edit_size()
        annotations.set_tool_props("edittext", dict(annotations.tool_props("edittext"),
                                                    fontsize=round(picked or size, 2)))
        self.textToolPropsChanged.emit()
        ed = InlineEditor(w, w.to_screen(box), old,
                          chosen[0] if chosen else text_edit.font_family_hint(lines[0]),
                          (picked or size) * self.zoom, click=w.to_screen_pt(pt))
        # the box covers the whole paragraph while you type, also when the screen font fits
        # its words on fewer lines than the page does
        from .inline_editor import MARGIN
        ed.min_height = int(box.height * self.zoom + 2 * MARGIN + 4)
        ed.fix_width((lay["right"] - min(lay["left"], lay["first_left"])) * self.zoom)
        # the cursor goes where the page was clicked (the editor's font wraps a little
        # differently from the page's, so the place on screen can be another word)
        cur = ed.text.textCursor()
        cur.setPosition(min(len(old), text_edit.paragraph_index(lines, pt)))
        ed.text.setTextCursor(cur)
        ed.kz_tool, ed.kz_line_size = "edittext", size
        self._inline = ed
        self.statusMessage.emit(tr("Editing the paragraph: the words rewrap as you type. "
                                   "Alt+click edits a single line."))

        def finished():
            self._inline = None
            annotations.reset_tool_props("edittext")
            self.textToolPropsChanged.emit()

        def done(text, dx, dy, wrap_px):
            new_size = self._edit_size()
            font = self._edit_font()
            finished()
            if new_size is not None and abs(new_size - size) < 0.06:
                new_size = None
            wrap = wrap_px / self.zoom if wrap_px else None
            if wrap is not None:
                # the box spans a first line set out before its number too; the body wraps
                # to the rest
                wrap -= max(0.0, lay["left"] - lay["first_left"])
                if abs(wrap - lay["width"]) < 4:
                    wrap = None                 # the paragraph's own width

            def paras(t):
                return [" ".join(p.split()) for p in t.split("\n")]
            if paras(text) == paras(old) and not dx and not dy and \
                    wrap is None and font is None and new_size is None:
                return
            offset = (dx / self.zoom, dy / self.zoom)
            made = {}

            def do():
                from . import links
                pg = self.doc[index]
                made["font"], made["box"], made["bases"] = text_edit.replace_paragraph(
                    pg, lines, text, wrap, font, new_size, offset)
                if offset[0] or offset[1]:
                    links.follow(pg, box, box + (offset[0], offset[1], offset[0], offset[1]),
                                 foreign=True)
            self.modify(do, [index])
            if "box" not in made:
                # it failed (and said why) or was refused: nothing changed
                self.statusMessage.emit(tr("The paragraph wasn't changed."))
                return
            if (made.get("font") or "").startswith("KZ"):
                self._fonts_added = True
            new_box, bases = made["box"], made["bases"]
            sz = new_size or size
            page_rect = self.doc[index].rect
            if bases and new_box.y1 > page_rect.y1 + 0.5:
                self.statusMessage.emit(tr("The paragraph now runs past the bottom of the "
                                           "page. Ctrl+Z undoes it; drag a side of the box "
                                           "wider to keep it shorter."))
                return
            x0, x1 = new_box.x0, new_box.x1
            near = [o for o in others if o[0] < x1 - 0.5 and o[2] > x0 + 0.5 and
                    o[1] < new_box.y1 and o[3] > new_box.y0]
            if any(min(o[3], b + 0.15 * sz) - max(o[1], b - 0.7 * sz) > 0.5
                   for b in bases for o in near):
                self.statusMessage.emit(tr("The paragraph grew and now overlaps text below "
                                           "it. Ctrl+Z undoes it; drag a side of the box "
                                           "wider to keep it shorter."))
                return
            self.statusMessage.emit(tr("Paragraph rewritten (Ctrl+Z undoes it). Alt+click "
                                       "edits a single line."))
        ed.committed.connect(done)
        ed.canceled.connect(finished)

    def edit_text_at(self, index, pt, one_line=False):
        """Edit text tool, click: edit the paragraph there (words rewrap), or, with
        one_line (Alt+click), a scanned page, sideways text or a lone line, just the line."""
        self.commit_pending()          # finish the edit already in progress first
        hit = text_edit.line_at(self._lines(index), pt)
        if hit is None:
            self.statusMessage.emit(tr("No text there. Click on a line of text to edit it."))
            return
        page = self.doc[index]
        if any(a.type[0] == pymupdf.PDF_ANNOT_REDACT for a in page.annots()):
            QMessageBox.warning(self, tr("Edit text"), tr("This page has pending redactions; "
                                "editing text would apply them. Remove them first."))
            return
        rect, line = hit
        old = text_edit.line_text(line)
        w = self.pages[index]
        upright = (text_edit.line_rotation(line) + page.rotation) % 360 == 0
        size = text_edit.main_span(line)["size"]
        try:
            from . import scan_text
            scan = scan_text.analyze(page, line, old)     # a line on a scanned page?
        except Exception:
            scan = None
        if not one_line and not scan and upright:
            para = self._paragraph_of(index, line)
            if para is not None:
                self._edit_paragraph(index, para, pt)
                return
        hint = text_edit.font_family_hint(line)
        if scan:
            # show and write it as the scan looks: the matched font, size and color
            size = scan["size"]
            hint = scan["label"] if scan["font"] and scan["font"][5] else scan["kind"]
        chosen = self._edit_font()
        # Properties shows this line's size while it's edited (a size picked there before
        # clicking the line applies to it); whatever is picked applies to this line only
        picked = self._edit_size()
        annotations.set_tool_props("edittext", dict(annotations.tool_props("edittext"),
                                                    fontsize=round(picked or size, 2)))
        self.textToolPropsChanged.emit()
        new_size = picked
        box = w.to_screen(rect)
        if not upright:
            # sideways text: type in an upright box laid over the middle of the line (it
            # can't run along the line); the text keeps its direction on the page
            c = box.center()
            bw = max(160.0, min(w.width() - 8.0, len(old) * size * 0.6 * self.zoom + 24))
            bh = size * self.zoom * 1.4
            box = QRectF(c.x() - bw / 2, c.y() - bh / 2, bw, bh)
            box.moveLeft(max(0.0, min(box.left(), w.width() - bw)))
            box.moveTop(max(0.0, min(box.top(), w.height() - bh)))
        ed = InlineEditor(w, box, old, chosen[0] if chosen else hint,
                          (new_size or size) * self.zoom,
                          click=w.to_screen_pt(pt) if upright else None,
                          bold=bool(scan and scan["bold"] and not chosen))
        ed.kz_tool, ed.kz_line_size = "edittext", size
        self._inline = ed

        def finished():
            self._inline = None
            annotations.reset_tool_props("edittext")     # the next line keeps its own
            self.textToolPropsChanged.emit()

        def done(text, dx, dy, wrap_px):
            new = self._edit_size()
            font = self._edit_font()
            finished()
            if new is not None and abs(new - size) < 0.06:
                new = None              # the size shown is the line's own: keep it exactly
            if not upright:
                wrap_px = None          # the box's width isn't along the line
            if text == old and not dx and not dy and wrap_px is None and \
                    font is None and new is None:
                return
            # screen movement -> PDF (unrotated) points
            m = self.doc[index].derotation_matrix
            v = pymupdf.Point(dx / self.zoom, dy / self.zoom) * m - pymupdf.Point(0, 0) * m
            wrap = wrap_px / self.zoom if wrap_px else None
            self._apply_text_edit(index, line, text, (v.x, v.y), wrap, size=new, scan=scan,
                                  font=font)
        ed.committed.connect(done)
        ed.canceled.connect(finished)

    def replace_text(self, find, repl, match_case=False, whole_words=False, pages=None):
        """Replace find with repl in the page text (pages: indices, None = all) as one undo
        step. Returns (matches replaced, lines rewritten, pages skipped because they have
        pending redaction marks)."""
        from .replace_dialog import pattern
        self.commit_pending()
        if not find or not self.allowed(pymupdf.PDF_PERM_MODIFY):
            if find:
                self.modify(lambda: None, [])       # says why it's not allowed
            return 0, 0, []
        rx = pattern(find, match_case, whole_words)
        todo, skipped = {}, []
        for i in (range(self.doc.page_count) if pages is None else pages):
            page = self.doc[i]
            if not rx.search(re.sub(r"\s+", " ", page.get_text())):
                continue                # quick test before reading the page's lines
            hits = [(line, text_edit.line_text(line)) for _r, line in self._lines(i)]
            hits = [(line, t) for line, t in hits if rx.search(t)]
            if not hits:
                continue
            if any(a.type[0] == pymupdf.PDF_ANNOT_REDACT for a in page.annots()):
                skipped.append(i)
                continue
            todo[i] = hits
        if not todo:
            return 0, 0, skipped
        count = {"found": 0, "lines": 0}

        def do():
            for i, hits in todo.items():
                page = self.doc[i]
                for line, text in hits:
                    new, n = rx.subn(lambda _m: repl, text)
                    text_edit.replace_line(page, line, new)
                    count["found"] += n
                    count["lines"] += 1
        self.modify(do, list(todo))
        self._fonts_added = True
        self.statusMessage.emit(tr("Replaced {n} (Ctrl+Z undoes it)").format(n=count["found"]))
        return count["found"], count["lines"], skipped

    def _markups_on_line(self, page, line):
        """xrefs of text markups (highlight, underline, comments...) and sticky notes sitting
        on this line of text: they travel with it when the text is moved."""
        box = pymupdf.Rect(line["bbox"])
        out = []
        for an in annotations.each_annot(page):
            t = an.type[0]
            if t in (pymupdf.PDF_ANNOT_HIGHLIGHT, pymupdf.PDF_ANNOT_UNDERLINE,
                     pymupdf.PDF_ANNOT_STRIKE_OUT, pymupdf.PDF_ANNOT_SQUIGGLY):
                v = an.vertices or []
                quads = [pymupdf.Quad(v[k:k + 4]).rect for k in range(0, len(v) - 3, 4)]
                # all of its marked area lies on this line (mostly overlapping it)
                if quads and all(q.get_area() > 0 and (q & box).get_area() >= 0.5 * q.get_area()
                                 for q in quads):
                    out.append(an.xref)
            elif t == pymupdf.PDF_ANNOT_TEXT:
                r = an.rect
                if (box + (-4, -4, 4, 4)).contains(pymupdf.Point(r.x0, r.y0)):
                    out.append(an.xref)
        return out

    def add_text_at(self, index, pt):
        """Add text tool: type at pt; the text is written into the page itself (like
        Acrobat's Add Text), so PDF viewers can't change it and Edit text can."""
        self.commit_pending()
        if not self.allowed(pymupdf.PDF_PERM_MODIFY):
            self.modify(lambda: None, [index])      # says why it's not allowed
            return
        props = annotations.tool_props("addtext")
        size = float(props.get("fontsize") or 12)
        family = props.get("font") or ""
        page = self.doc[index]
        w = self.pages[index]
        top = pymupdf.Point(pt) * page.rotation_matrix          # displayed coordinates
        disp = pymupdf.Rect(top.x, top.y - size * 0.85, top.x + size * 12, top.y + size * 0.35)
        ed = InlineEditor(w, w.to_screen(disp * page.derotation_matrix), "",
                          family or "sans", size * self.zoom)
        ed.kz_tool = "addtext"
        self._inline = ed

        def done(text, dx, dy, wrap_px):
            self._inline = None
            if not text.strip():
                return
            # the size can be changed in Properties while typing
            size = float(annotations.tool_props("addtext").get("fontsize") or 12)
            m = self.doc[index].derotation_matrix
            v = pymupdf.Point(dx / self.zoom, dy / self.zoom) * m - pymupdf.Point(0, 0) * m
            origin = pymupdf.Point(pt) + v
            wrap = wrap_px / self.zoom if wrap_px else None
            used = {}

            def do():
                used["font"] = text_edit.add_text(
                    self.doc[index], origin, text, family, props.get("bold"), props.get("italic"),
                    size, annotations.to_rgb(props.get("text_color")) or (0, 0, 0), wrap)
            self.modify(do, [index])
            font = used.get("font") or ""
            if font.startswith("KZ"):
                self._fonts_added = True
            if family and not font.startswith("KZF") and font:
                self.statusMessage.emit(tr("{font} isn't installed in that style or lacks "
                                           "some of these characters; used a standard font.")
                                        .format(font=family))
            elif font:
                self.statusMessage.emit(tr("Text added to the page. Edit text changes it; "
                                           "Ctrl+Z undoes it."))
        ed.committed.connect(done)
        ed.canceled.connect(lambda: setattr(self, "_inline", None))

    def _edit_size(self):
        """Font size chosen for Edit text in Properties (points), or None = keep each
        line's own size."""
        return float(annotations.tool_props("edittext").get("fontsize") or 0) or None

    def text_tool_props_changed(self):
        """Properties changed while Add text / Edit text is open on the page: show the text
        at the new size right away (it's written at that size when you finish)."""
        ed = self._inline
        tool = getattr(ed, "kz_tool", None)
        if ed is None or tool is None:
            return
        if tool == "addtext":
            size = float(annotations.tool_props("addtext").get("fontsize") or 12)
        else:
            size = self._edit_size() or ed.kz_line_size
        ed.set_pixel_size(size * self.zoom)

    def _edit_font(self):
        """(family, bold, italic) chosen for Edit text in Properties, or None = keep each
        line's own font."""
        p = annotations.tool_props("edittext")
        return (p["font"], bool(p.get("bold")), bool(p.get("italic"))) if p.get("font") else None

    def _apply_text_edit(self, index, line, new, offset, wrap, keep_font=False, size=None,
                         scan="auto", font=None):
        used = {}
        font = None if keep_font else font

        def do():
            page = self.doc[index]
            moving = []
            if offset[0] or offset[1]:
                for x in self._markups_on_line(page, line):
                    m = annotations.read(page.load_annot(x))
                    if m is not None:
                        moving.append((x, m))
            info = {}
            used["font"] = text_edit.replace_line(page, line, new, offset, wrap, font,
                                                  None if keep_font else size, scan, info)
            used["scan"] = info.get("scan")
            d = pymupdf.Point(offset)
            if d.x or d.y:
                from . import links
                old = pymupdf.Rect(line["bbox"])
                links.follow(page, old, old + (d.x, d.y, d.x, d.y), on="text")
            for x, m in moving:
                if "quads" in m:
                    m = annotations.copy(m)
                    m["quads"] = [pymupdf.Quad(q.ul + d, q.ur + d, q.ll + d, q.lr + d)
                                  for q in m["quads"]]
                else:
                    m = annotations.moved(m, d)
                annotations.replace(page, x, m)
            used["moved"] = len(moving)
        self.modify(do, [index])
        wanted = font
        font = used.get("font") or ""
        sc = used.get("scan")
        if font.startswith("KZ"):
            self._fonts_added = True
        if sc and not (wanted and font.startswith("KZF")):
            if not new.strip():
                self.statusMessage.emit(tr("Removed the line from the scan (Ctrl+Z undoes it)."))
            elif sc.get("unsure"):
                self.statusMessage.emit(tr("The scanned letters didn't match their "
                                           "recognized text, so the font couldn't be told: used "
                                           "Helvetica. Pick a font in Properties to change it."))
            elif font.startswith("KZM") or font in ("helv", "hebo", "heit", "hebi", "tiro",
                                                    "tibo", "tiit", "tibi", "cour", "cobo",
                                                    "coit", "cobi"):
                shown = " ".join([sc["label"]] + ([tr("Bold")] if sc["bold"] else []) +
                                 ([tr("Italic")] if sc["italic"] else []))
                if wanted:
                    msg = tr("{wanted} isn't installed in that style or lacks some of these "
                             "characters. Matched the scan: {font}, {size} pt, in the scan's "
                             "color.")
                else:
                    msg = tr("Matched the scan: {font}, {size} pt, in the scan's color.")
                self.statusMessage.emit(msg.format(wanted=wanted[0] if wanted else "",
                                                   font=shown, size="%g" % sc["size"]))
            return
        if font.startswith("KZF"):
            self._fonts_added = True
            self.statusMessage.emit(tr("Edited in {font}.").format(font=wanted[0]))
        elif wanted and new.strip():
            self.statusMessage.emit(tr("{font} isn't installed in that style or lacks some of "
                                       "these characters; kept the line's own font.")
                                    .format(font=wanted[0]))
            if font.startswith("KZS") or font == "KZUni":
                self._fonts_added = True
        elif font.startswith("KZS") or font == "KZUni":
            self._fonts_added = True
            self.statusMessage.emit(tr("Edited using the installed copy of the original font.")
                                    if font.startswith("KZS") else
                                    tr("The original font lacks some of these characters; used "
                                       "a Unicode font for this line."))
        elif font and not font.startswith("KZ"):
            self.statusMessage.emit(tr("Original font isn't available for these characters; "
                                       "used the closest standard font."))

    # ---- redaction ---------------------------------------------------------------------
    def mark_redactions(self, index, rects):
        def do():
            pg = self.doc[index]
            for r in rects:
                a = pg.add_redact_annot(r, fill=(0, 0, 0))
                a.set_colors(stroke=(0.85, 0, 0))
                a.set_info(title=annotations.author(), content=tr("Redaction (not applied yet)"))
                a.update()
        self.modify(do, [index])

    def search_redact(self, text):
        hits = {i: self.doc[i].search_for(text) for i in range(self.doc.page_count)}
        hits = {i: h for i, h in hits.items() if h}
        if hits:
            def do():
                for i, rects in hits.items():
                    pg = self.doc[i]
                    for r in rects:
                        a = pg.add_redact_annot(r, fill=(0, 0, 0))
                        a.set_colors(stroke=(0.85, 0, 0))
                        a.set_info(title=annotations.author(),
                                   content=self.REDACT_TAG + text)
                        a.update()
            self.modify(do, list(hits))
        return sum(len(h) for h in hits.values())

    def erase_content(self, index, rect):
        """Erase content tool: permanently remove the page's own text, images and line art
        inside rect; lines crossing the edge are cut there (see erase.py). Undo works."""
        from . import erase
        page = self.doc[index]
        if any(a.type[0] == pymupdf.PDF_ANNOT_REDACT for a in page.annots()):
            QMessageBox.information(self, tr("Erase content"),
                                    tr("This page has redaction marks that aren't applied yet. "
                                       "Apply or remove them first (erasing would apply them "
                                       "too)."))
            return
        self.clear_selection()
        self.modify(lambda: erase.erase(self.doc[index], rect), [index])
        self.statusMessage.emit(tr("Erased the content inside the box (Ctrl+Z undoes it)"))

    def capture_area(self, index, rect):
        """Capture tool (Bluebeam Snapshot): copy what's in the box, markups included. Ctrl+V
        here pastes it at the same size as an image markup made of the original vector
        drawing; a picture of it also pastes into Word, email and so on."""
        if not self.require_permission(pymupdf.PDF_PERM_COPY,
                                       tr("Copying pictures or page content")):
            return
        from . import clip
        from PySide6.QtGui import QImage
        page = self.doc[index]
        area = (pymupdf.Rect(rect) * page.rotation_matrix) & page.rect    # as displayed
        if area.is_empty:
            return
        dpi = 300 if area.width * area.height < 200_000 else 200
        pix = page.get_pixmap(clip=area, dpi=dpi, annots=True, alpha=False)
        png = pix.tobytes("png")
        img = QImage.fromData(png, "PNG")
        payload = {"png": png, "w": area.width, "h": area.height}
        try:
            from . import capture
            payload["pdf"], payload["box"] = capture.snapshot(page, area)
        except Exception:
            pass                                # the picture alone still pastes
        clip.put("capture", payload, image=img)
        self.statusMessage.emit(tr("Captured: Ctrl+V pastes it here as sharp vector content "
                                   "(and as a picture into Word or email)"))

    # ---- Edit objects: the page's own pictures and shapes ------------------
    def content_objects(self, index):
        """Editable objects of page `index` (cached until the next edit)."""
        cache = self._obj_cache
        if index not in cache:
            from . import page_objects
            QApplication.setOverrideCursor(Qt.WaitCursor)
            try:
                cache[index] = page_objects.Objects(self.doc[index])
            except Exception:
                cache[index] = None
            finally:
                QApplication.restoreOverrideCursor()
        return cache[index]

    TEXT_N = 10 ** 9                   # Edit objects numbers text paragraphs from here

    def text_objects(self, index):
        """The page's visible text as Edit objects items, one per paragraph: kind "text",
        "rect", "lines" [(rect, line)] (cached until the next edit)."""
        if index not in self._text_obj_cache:
            self._text_obj_cache[index] = [
                {"n": self.TEXT_N + i, "kind": "text", "rect": box, "quad": box.quad,
                 "lines": blk}
                for i, (box, blk) in enumerate(text_edit.text_blocks(self._lines(index)))]
        return self._text_obj_cache[index]

    def object_at(self, index, pt):
        """The topmost picture or shape under PDF point pt, or None. Text comes first: what
        you click on a word is the text, even over a filled shape or picture."""
        pad = 2 / self.zoom
        hits = [it for it in self.text_objects(index)
                if (it["rect"] + (-pad, -pad, pad, pad)).contains(pt)]
        if hits:
            return min(hits, key=lambda it: it["rect"].get_area())
        objs = self.content_objects(index)
        return objs.at(pt, 4 / self.zoom) if objs is not None else None

    def objects_in(self, index, box):
        """What a selection box takes: the pictures and shapes inside it, or, when it holds
        none (a box around text alone), the text paragraphs inside it. So a box around a CAD
        detail still selects its line work to resize or rotate, labels left alone."""
        objs = self.content_objects(index)
        box = pymupdf.Rect(box)
        found = objs.inside(box) if objs is not None else []
        return found or [it for it in self.text_objects(index) if box.contains(it["rect"])]

    def cad_objects(self, index, region, crossing=False):
        """What a CAD selection region (page_objects.Box or Lasso) takes with Edit objects, as
        in CAD programs: a window, the pictures, shapes and text lying entirely inside it; a
        crossing one, also the ones it touches."""
        from .page_objects import overlap
        objs = self.content_objects(index)
        found = objs.pick(region, crossing) if objs is not None else []
        texts = []
        for it in self.text_objects(index):
            if not overlap(it["rect"], region.bounds):
                continue
            if region.contains_rect(it["rect"]) or crossing and any(
                    region.touches_rect(r) for r, _ln in it["lines"]):
                texts.append(it)
        return found + texts

    # ---- CAD mode: the page made ready while nothing happens -------------------------------
    PREP_WAIT = 600             # ms without a new reason before preparing starts
    PREP_SLICE = 0.03           # seconds of preparing at a time

    def _cad_prepare_soon(self):
        """In CAD mode, read the page's objects and their lines in short slices while you
        aren't doing anything, so the first box, lasso, highlight or command on a big
        drawing starts at once instead of reading the drawing first."""
        if not self.cad_select or getattr(self, "doc", None) is None:
            return
        t = getattr(self, "_prep_timer", None)
        if t is None:
            t = self._prep_timer = QTimer(self)
            t.setSingleShot(True)
            t.timeout.connect(self._cad_prepare_step)
        t.start(self.PREP_WAIT)

    def _cad_prepare_step(self):
        if not self.cad_select or getattr(self, "doc", None) is None or self.doc.is_closed or \
                not getattr(self, "pages", None):
            return
        index = self.current_page()
        job = getattr(self, "_prep_job", None)
        objs = self._obj_cache.get(index)
        if job is None or job["index"] != index or job["objs"] is not objs or objs is None:
            # first the page's objects (read in slices too: a 60,000-line sheet takes
            # seconds), then its text (quick), then their lines in slices
            if objs is None:
                if index in self._obj_cache:
                    return                  # (nothing it can read: no more tries)
                self._prepare_read(index)
                return
            self.text_objects(index)
            shapes = [it for it in (objs.items if objs is not None else ())
                      if it["kind"] == "shape" and "lines" not in it]
            self._prep_job = {"index": index, "objs": objs, "todo": iter(shapes)}
            if shapes:
                self._prep_timer.start(0)
            return
        end = time.monotonic() + self.PREP_SLICE
        for it in job["todo"]:
            objs.lines(it)
            if time.monotonic() > end:
                self._prep_timer.start(0)   # more next time round, after any input
                return

    def _prepare_read(self, index):
        """One slice of reading page index's objects in idle time; they go into the cache
        when done, unless the page changed (or was read another way) meanwhile."""
        from . import page_objects
        key = (index, id(self.doc), getattr(self, "revision", 0), id(self._obj_cache))
        read = getattr(self, "_prep_read", None)
        if read is None or read["key"] != key:
            try:
                objs, steps = page_objects.Objects.steps(self.doc[index])
            except Exception:
                return
            read = self._prep_read = {"key": key, "objs": objs, "steps": steps}
        end = time.monotonic() + self.PREP_SLICE
        try:
            while time.monotonic() < end:
                next(read["steps"])
        except StopIteration:
            self._prep_read = None
            if index not in self._obj_cache:
                self._obj_cache[index] = read["objs"]
        except Exception:
            self._prep_read = None
            self._obj_cache.setdefault(index, None)     # (as content_objects does)
            return
        self._prep_timer.start(0)           # more next time round, after any input

    # ---- CAD tab commands (cad_commands.py) ----------------------------------------------
    _cad_cmd = None             # the CAD command running, or None

    def cad_targets(self):
        """What a CAD command works on: ("objects", page, items) for the drawing's own objects
        selected with Edit objects, ("markups", page, [(xref, model)]) for selected markups,
        or None."""
        if self.obj_sel is not None and self.obj_sel[1]:
            return "objects", self.obj_sel[0], list(self.obj_sel[1])
        if self.selection is not None:
            models = [(x, m) for x, m in self.selected_models() if m["kind"] != "field"]
            if models:
                return "markups", self.selection[0], models
        return None

    def cad_outlines(self, index, kind, items):
        """The selection's outlines in page coordinates, for a command's preview."""
        out = []
        if kind == "objects":
            for it in items:
                out += self.object_lines(index, it)
            return out
        for _x, m in items:
            if "strokes" in m:
                out += [list(s) for s in m["strokes"]]
            elif "points" in m and m["kind"] in annotations.POINTED:
                pts = list(m["points"])
                out.append(pts + pts[:1] if m["kind"] in ("polygon", "m_area", "cloud")
                           else pts)
            elif "quads" in m:
                out += [[q.ul, q.ur, q.lr, q.ll, q.ul] for q in m["quads"]]
            else:
                pts = annotations.outline(m) if annotations.turned(m) else None
                if pts is None:
                    r = annotations.bounds(m)
                    pts = [r.tl, r.tr, r.br, r.bl]
                out.append(list(pts) + [pts[0]])
        return out

    def cad_apply(self, label, mat, copies=None, keep=False):
        try:
            with _busy():
                out = self._cad_apply(label, mat, copies, keep)
        except Exception:
            if self._cad_cmd is not None:   # (a command that failed doesn't go on)
                self._cad_cmd.finish()
            raise
        self._cad_seen()
        return out

    def _cad_seen(self):
        """The running command made this change itself (Copy goes on after it): it isn't a
        change to the document under it."""
        if self._cad_cmd is not None:
            self._cad_cmd.rev = getattr(self, "revision", 0)

    def _cad_apply(self, label, mat, copies=None, keep=False):
        """A CAD command's change to the selection, as one undo step: mat (a Matrix in page
        coordinates) moves / turns / scales / mirrors it; copies (a list of matrices) adds a
        copy for each instead. The drawing's own text only moves."""
        from . import cad_commands, page_objects
        what = self.cad_targets()
        if what is None:
            return
        kind, index, items = what
        mats = copies if copies is not None else [mat]
        moving_only = all(cad_commands.is_translation(m) for m in mats)
        if kind == "objects":
            texts = [it for it in items if it["kind"] == "text"]
            shapes = [it for it in items if it["kind"] != "text"]
            objs = self._obj_cache.get(index)
            if texts and (copies is not None or not moving_only):
                self.statusMessage.emit(tr("The drawing's text can be moved here, not copied, "
                                           "turned, scaled or mirrored: it stays where it is "
                                           "(Edit text changes it)."))
            if copies is not None:
                if not shapes:
                    return
                self.obj_sel = (index, shapes)
                # many copies of many objects (an array): by reference, as one group placed
                # again and again (fast, and the file stays small)
                big = len(copies) > 20 and len(copies) * len(shapes) > 400
                make = page_objects.block_copies if big else page_objects.copies
                placed = {}
                self._objects_edit(label, lambda pg, ns: make(pg, ns, copies, objs, placed),
                                   keep=False)
                if keep:
                    # the originals stay selected (Copy goes on placing copies of them), where
                    # the copying left them in the drawing order
                    now = set(placed.get("originals", ()))
                    objs = self.content_objects(index)
                    again = [it for it in (objs.items if objs else []) if it["n"] in now]
                    self.obj_sel = (index, again) if again else None
                    self.pages[index].update()
                return
            if texts and moving_only:
                d = pymupdf.Point(mat.e, mat.f)

                def move_text(page, texts):
                    self._move_text_lines(page, [ln for it in texts for _r, ln in it["lines"]],
                                          (d.x, d.y))
                    return [it["rect"] + (d.x, d.y, d.x, d.y) for it in texts]
                self._objects_edit(label, lambda pg, ns: page_objects.transform(pg, ns, mat, objs),
                                   text_fn=move_text)
                return
            if not shapes:
                return
            self.obj_sel = (index, shapes)
            self._objects_edit(label, lambda pg, ns: page_objects.transform(pg, ns, mat, objs))
            return
        # markups
        usable = [(x, m) for x, m in items
                  if moving_only or m["kind"] not in annotations.MARKUP]
        if len(usable) < len(items):
            self.statusMessage.emit(tr("Highlights and other text markups stay on their words: "
                                       "they can only be moved or copied."))
        if not usable:
            return
        if copies is None:
            self.commit_models(index, [(x, annotations.transformed(m, mat)) for x, m in usable])
            self.statusMessage.emit(tr("{what} (Ctrl+Z undoes it)").format(what=label))
            return
        models = self._next_counts([m for _x, m in usable])
        made = []

        def do():
            pg = self.doc[index]
            for c in copies:
                for m in models:
                    made.append(annotations.write(pg, annotations.transformed(m, c)).xref)
        self.modify(do, [index], permission=pymupdf.PDF_PERM_ANNOTATE)
        self.statusMessage.emit(tr("{what} (Ctrl+Z undoes it)").format(what=label))

    def _trimmable_annots(self, page):
        """The markups Trim sees: shown, not hidden or locked."""
        if not self.show_markups:
            return
        for an in annotations.each_annot(page):
            if an.type[0] == pymupdf.PDF_ANNOT_POPUP or (an.flags or 0) & (
                    pymupdf.PDF_ANNOT_IS_LOCKED | pymupdf.PDF_ANNOT_IS_HIDDEN):
                continue
            yield an

    def cad_trim(self, index, pt):
        with _busy():
            out = self._cad_trim(index, pt)
        self._cad_seen()
        return out

    def _cad_trim(self, index, pt):
        """Trim at pt (the CAD tab): the clicked line of the drawing, or line markup, loses
        the part between the nearest lines crossing it (or its end). True if it changed."""
        from . import page_objects, trim
        tol = 6 / self.zoom
        page = self.doc[index]
        objs = self.content_objects(index)
        best = None                         # (distance, what, ...)
        near = []
        if objs is not None:
            # every stroked line near the click, not only the topmost: the nearest one is cut
            # (a click just beside a crossing means the line it's on)
            for item in objs.items:
                r = item["rect"]
                pad = tol + item.get("width", 0) / 2
                if item["kind"] == "shape" and item["stroke"] and not item["fill"] and \
                        r.x0 - pad <= pt.x <= r.x1 + pad and r.y0 - pad <= pt.y <= r.y1 + pad:
                    near.append(item)
        nearest = None                      # (distance, item, subpath number)
        for item in near:
            for k, poly in enumerate(objs.lines(item)):
                if len(poly) < 2:
                    continue
                _s, d = trim.project(poly, trim._cum(poly), pt)
                if d <= tol + item.get("width", 0) / 2 and (nearest is None or d < nearest[0]):
                    nearest = (d, item, k)
        if nearest is not None:
            d, item, k = nearest
            state, parts, paint = page_objects.subpaths(objs.data, item["obj"])
            mat = item["obj"]["ctm"] * objs.tm
            if k < len(parts):
                shown = objs.lines(item)[k]         # (the same subpath, already on the page)
                poly = shown if len(shown) == len(parts[k][1]) else \
                    [q * mat for q in parts[k][1]]
                best = (d, "object", item, k, poly, parts[k][2], state, parts, paint, mat)
        for an in self._trimmable_annots(page):
            m = annotations.read(an)
            if m is None or m["kind"] not in ("line", "polyline", "ink"):
                continue
            strokes = m["strokes"] if m["kind"] == "ink" else [m["points"]]
            for k, poly in enumerate(strokes):
                poly = [pymupdf.Point(q) for q in poly]
                if len(poly) < 2:
                    continue
                _s, d = trim.project(poly, trim._cum(poly), pt)
                if d <= tol and (best is None or d < best[0]):
                    best = (d, "markup", an.xref, k, poly, False, m)
        if best is None:
            self.statusMessage.emit(tr("Trim: no line there. Click on a line of the drawing or "
                                       "a line markup (filled shapes and pictures aren't "
                                       "trimmed)."))
            return False
        poly = best[4]
        r = pymupdf.Rect(poly[0], poly[0])
        for q in poly[1:]:
            r |= q
        r += (-1, -1, 1, 1)
        cutters = []
        if objs is not None:
            for it in objs.items:
                if it["kind"] != "shape" or not page_objects.overlap(it["rect"], r):
                    continue
                for k, line in enumerate(objs.lines(it)):
                    if best[1] == "object" and it is best[2] and k == best[3]:
                        continue
                    cutters.append(line)
        for an in self._trimmable_annots(page):
            if best[1] == "markup" and an.xref == best[2]:
                continue
            if not page_objects.overlap(an.rect, r):
                continue
            lines, _closed, _filled = self._annot_geometry(an)
            cutters += lines
        if best[1] == "markup":
            m = best[6]
            others = (m["strokes"] if m["kind"] == "ink" else [])
            cutters += [list(s) for j, s in enumerate(others) if j != best[3]]
        pieces = trim.trim(poly, best[5], pt, cutters)
        if pieces is None:
            self.statusMessage.emit(tr("Trim: that's where lines cross. Click on the part of "
                                       "the line to cut away, a little to one side."))
            return False
        if best[1] == "object":
            _d, _w, item, k, _poly, _closed, state, parts, paint, mat = best
            inv = ~mat
            new = [p_[0] if j != k else [[q * inv for q in pc] for pc in pieces]
                   for j, p_ in enumerate(parts)]

            fresh = {}

            def do():
                fresh["objs"] = page_objects.rewrite_path(self.doc[index], item["n"], state,
                                                          new, paint, objs)
            self.clear_object_selection()
            self.modify(do, [index])
            got = fresh.get("objs")
            if isinstance(got, page_objects.Objects):
                # the page's objects, worked out without reading the drawing again; the
                # trimmed one's lines are known too
                got_item = next((it for it in got.items if it["n"] == item["n"]), None)
                if got_item is not None and pieces:
                    lines = objs.lines(item)
                    got_item["lines"] = lines[:k] + [list(pc) for pc in pieces] + lines[k + 1:]
                self._obj_cache[index] = got
        else:
            _d, _w, xref, k, _poly, _closed, m = best
            models = []
            if m["kind"] == "ink":
                strokes = [s for j, s in enumerate(m["strokes"]) if j != k] + pieces
                if strokes:
                    n = annotations.copy(m)
                    n["strokes"] = [[pymupdf.Point(q) for q in s] for s in strokes]
                    models.append(n)
            else:
                for pc in pieces:
                    n = annotations.copy(m)
                    n["points"] = [pymupdf.Point(q) for q in pc]
                    if m["kind"] == "line" and len(pc) > 2:
                        n["points"] = [pc[0], pc[-1]]
                    models.append(n)

            def do():
                pg = self.doc[index]
                if models:
                    annotations.replace_many(pg, [(xref, models[0])])
                else:
                    pg.delete_annot(pg.load_annot(xref))
                for mod in models[1:]:
                    annotations.write(pg, mod)
            self.clear_selection()
            self.modify(do, [index], permission=pymupdf.PDF_PERM_ANNOTATE)
        self.statusMessage.emit(tr("Trimmed (Ctrl+Z undoes it)"))
        return True

    def object_lines(self, index, item):
        if item["kind"] == "text":
            q = item["quad"]
            return [[q.ul, q.ur, q.lr, q.ll, q.ul]]
        objs = self.content_objects(index)
        return objs.lines(item) if objs is not None else []

    def selected_objects(self):
        return self.obj_sel[1] if self.obj_sel else []

    def selected_objects_rect(self):
        from .page_objects import bounding
        return bounding(it["rect"] for it in self.selected_objects())

    def select_objects(self, index, items, add=False):
        """Select pictures / shapes on page index; add=True toggles them in the selection."""
        old = self.obj_sel
        if add and old and old[0] == index:
            have = {it["n"]: it for it in old[1]}
            for it in items:
                if it["n"] in have:
                    del have[it["n"]]
                else:
                    have[it["n"]] = it
            items = sorted(have.values(), key=lambda it: it["n"])
        self.obj_sel = (index, list(items)) if items else None
        for i in {old[0] if old else None, index}:
            if i is not None and 0 <= i < len(self.pages):
                self.pages[i].update()
        if bool(old) != bool(self.obj_sel):
            self.selectionChanged.emit()        # menus: Arrange works on objects too
        if items:
            pics = sum(1 for it in items if it["kind"] == "picture")
            groups = sum(1 for it in items if it["kind"] == "group")
            texts = sum(1 for it in items if it["kind"] == "text")
            shapes = len(items) - pics - groups - texts
            what = ", ".join(x for x in (
                (tr("{n} text") if texts == 1 else tr("{n} texts")).format(n=texts)
                if texts else "",
                (tr("{n} picture") if pics == 1 else tr("{n} pictures")).format(n=pics)
                if pics else "",
                (tr("{n} shape") if shapes == 1 else tr("{n} shapes")).format(n=shapes)
                if shapes else "",
                (tr("{n} group") if groups == 1 else tr("{n} groups")).format(n=groups)
                if groups else "") if x)
            how = (tr("drag to move, Delete deletes, right-click for more (Edit text changes "
                      "the words)") if texts else
                   tr("drag to move, drag a handle to resize, Delete deletes, right-click for "
                      "more"))
            self.statusMessage.emit(tr("Selected {what}: {how}").format(what=what, how=how))

    def clear_object_selection(self):
        if self.obj_sel is not None:
            self.select_objects(self.obj_sel[0], [])

    def _objects_edit(self, label, fn, keep=True, text_fn=None, links_fn=None,
                      links_first=False):
        """Run fn(page, ns) on the selected pictures and shapes, then text_fn(page, texts) on
        the selected text, as one undo step; keep them selected. fn may return the page's
        new page_objects.Objects (saves reading the page again). text_fn returns where each
        text paragraph is now (to select it again), or None."""
        from . import page_objects
        if self.obj_sel is None:
            return
        index, items = self.obj_sel
        ns = [it["n"] for it in items if it["kind"] != "text"]
        texts = [it for it in items if it["kind"] == "text"]

        fresh = {}

        def do():
            page = self.doc[index]
            if ns:
                fresh["objs"] = fn(page, ns)
            # the links made for these objects go along (links_fn); before the text when
            # the text's removal would take them, after it when they follow a move
            if links_fn is not None and links_first and links_fn(page):
                fresh["objs"] = None
            if texts and text_fn is not None:
                # (the shapes first: text removal rewrites the page's drawing instructions)
                fresh["text_rects"] = text_fn(page, texts)
                fresh["objs"] = None
            if links_fn is not None and not links_first and links_fn(page):
                fresh["objs"] = None
        before = self._obj_cache.get(index)
        self.modify(do, [index])
        self._obj_cache.pop(index, None)
        if isinstance(fresh.get("objs"), page_objects.Objects) and before is not None:
            # a move / rotate worked out the page's objects without reading it again
            self._obj_cache[index] = fresh["objs"]
        self.obj_sel = None
        if keep:
            objs = self.content_objects(index)
            wanted = set(ns)
            again = [it for it in (objs.items if objs else []) if it["n"] in wanted]
            for r in fresh.get("text_rects") or []:
                near = [it for it in self.text_objects(index)
                        if abs(it["rect"].x0 - r.x0) < 1.5 and abs(it["rect"].y0 - r.y0) < 1.5]
                again += near[:1]
            self.obj_sel = (index, again) if again else None
        self.pages[index].update()
        self.selectionChanged.emit()    # menus (Arrange) follow the reselected objects
        self.statusMessage.emit(tr("{what} (Ctrl+Z undoes it)").format(what=label))

    def move_objects(self, new_rect):
        from . import page_objects
        old = self.selected_objects_rect()
        if self.obj_sel is None:
            return
        objs = self._obj_cache.get(self.obj_sel[0])
        new_rect = pymupdf.Rect(new_rect)
        offset = (new_rect.x0 - old.x0, new_rect.y0 - old.y0)
        if any(it["kind"] == "text" for it in self.obj_sel[1]):
            # text only moves (the box keeps its size: Edit text changes the words)
            new_rect = old + (offset[0], offset[1], offset[0], offset[1])

        def move_text(page, texts):
            self._move_text_lines(page, [ln for it in texts for _r, ln in it["lines"]],
                                  offset)
            d = pymupdf.Point(offset)
            return [it["rect"] + (d.x, d.y, d.x, d.y) for it in texts]
        from . import links
        parts = [(pymupdf.Rect(it["rect"]), self._obj_on(it)) for it in self.obj_sel[1]]
        self._objects_edit(tr("Moved"), lambda pg, ns: page_objects.move_to(pg, ns, old, new_rect, objs),
                           text_fn=move_text,
                           links_fn=lambda pg: links.follow(pg, old, new_rect, parts=parts))

    def _move_text_lines(self, page, lines, offset):
        """Move lines of the page's text by offset (points), with the highlights and other
        markups on them. The last line in the direction of the move goes first, so a moved
        line never lands on one that is still to be taken out."""
        dx, dy = offset
        if not (dx or dy):
            return
        d = pymupdf.Point(offset)
        order = sorted(lines, key=lambda ln: (pymupdf.Rect(ln["bbox"]).y0 * (-1 if dy > 0 else 1),
                                              pymupdf.Rect(ln["bbox"]).x0 * (-1 if dx > 0 else 1)))
        for line in order:
            moving = []
            for x in self._markups_on_line(page, line):
                m = annotations.read(page.load_annot(x))
                if m is not None:
                    moving.append((x, m))
            used = text_edit.replace_line(page, line, text_edit.line_text(line), offset,
                                          scan=None)
            if (used or "").startswith("KZ"):
                self._fonts_added = True
            for x, m in moving:
                if "quads" in m:
                    m = annotations.copy(m)
                    m["quads"] = [pymupdf.Quad(q.ul + d, q.ur + d, q.ll + d, q.lr + d)
                                  for q in m["quads"]]
                else:
                    m = annotations.moved(m, d)
                annotations.replace(page, x, m)

    def rotate_objects(self, degrees):
        from . import page_objects
        if self.obj_sel is None:
            return
        if any(it["kind"] == "text" for it in self.obj_sel[1]):
            self.statusMessage.emit(tr("Text can be moved or deleted here, not turned: select "
                                       "only pictures and shapes to rotate them"))
            return
        rect = self.selected_objects_rect()
        objs = self._obj_cache.get(self.obj_sel[0])
        from . import links
        c = (rect.tl + rect.br) / 2
        turn = pymupdf.Matrix(1, 0, 0, 1, -c.x, -c.y) * pymupdf.Matrix(degrees) * \
            pymupdf.Matrix(1, 0, 0, 1, c.x, c.y)

        boxes = [pymupdf.Rect(it["rect"]) for it in self.obj_sel[1]]

        def turn_links(pg):
            mine = list({ln["xref"]: ln for r in boxes
                         for ln in links.attached(pg, r, "object")}.values())
            if mine:
                links.transform(pg, mine, turn)
            return bool(mine)
        self._objects_edit(tr("Rotated"), lambda pg, ns: page_objects.rotate(pg, ns, rect, degrees, objs),
                           links_fn=turn_links)

    def arrange_objects(self, how):
        """Stacking order of the page's own pictures and shapes (Edit objects): bring them
        in front of what covers them (text too), or send them behind."""
        from . import page_objects
        if self.obj_sel is None:
            return
        if any(it["kind"] == "text" for it in self.obj_sel[1]):
            self.statusMessage.emit(tr("Stacking order is for pictures and shapes: select "
                                       "only those to bring them forward or send them back"))
            return
        index, items = self.obj_sel
        ns = [it["n"] for it in items]
        moved = {"ok": False}

        def do():
            moved["ok"] = page_objects.reorder(self.doc[index], ns, how)
        if how in ("forward", "backward"):
            # nothing overlapping in that direction: say so instead of an empty undo step
            if not page_objects.reorder(self.doc[index], ns, how, dry_run=True):
                self.statusMessage.emit(tr("Nothing overlaps it in that direction"))
                return
        self.modify(do, [index])
        self._obj_cache.pop(index, None)
        # the moved objects get new positions in the drawing order: select them again by place
        rects = [pymupdf.Rect(it["rect"]) for it in items]
        objs = self.content_objects(index)
        again = [it for it in (objs.items if objs else [])
                 if any(abs(it["rect"].x0 - r.x0) < 0.05 and abs(it["rect"].y0 - r.y0) < 0.05
                        and abs(it["rect"].x1 - r.x1) < 0.05 and abs(it["rect"].y1 - r.y1) < 0.05
                        for r in rects)]
        self.obj_sel = (index, again) if again else None
        self.pages[index].update()
        # the edit cleared the selection (and the Arrange buttons with it): tell the menus
        self.selectionChanged.emit()
        label = {"front": tr("Brought to front"), "back": tr("Sent to back"),
                 "forward": tr("Brought forward"), "backward": tr("Sent backward")}[how]
        self.statusMessage.emit(tr("{what} (Ctrl+Z undoes it)").format(what=label))

    def delete_objects(self):
        from . import page_objects
        if self.obj_sel is None:
            return
        index, items = self.obj_sel
        texts = [it for it in items if it["kind"] == "text"]
        if texts and not self._confirm_text_removal(index, texts):
            return

        def delete_text(page, texts):
            text_edit.delete_lines(page, [ln for it in texts for _r, ln in it["lines"]])
        from . import links
        boxes = [(pymupdf.Rect(it["rect"]), self._obj_on(it)) for it in items]

        def drop_links(pg):
            mine = {ln["xref"]: ln for r, on in boxes for ln in links.attached(pg, r, on)}
            if mine:
                links.remove(pg, list(mine.values()), keep_text=True)
            return bool(mine)
        objs = self._obj_cache.get(self.obj_sel[0])
        self._objects_edit(tr("Deleted"), lambda pg, ns: page_objects.delete(pg, ns, objs),
                           keep=False, text_fn=delete_text,
                           links_fn=drop_links, links_first=True)

    def _confirm_text_removal(self, index, texts):
        """Taking text out removes every letter the cut touches. When that would take
        letters of other text overlapping it too, ask first."""
        bands = [b for it in texts for _r, ln in it["lines"] for b in text_edit.removal_bands(ln)]
        others = 0
        for w in self._words(index):                 # one entry per letter
            r = pymupdf.Rect(w[:4])
            c = pymupdf.Point((r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2)
            # this text's own letters are centered on its cut; others only touch it
            if w[4].strip() and any(r.intersects(b) for b in bands) and \
                    not any(c in (b + (-0.5, -0.5, 0.5, 0.5)) for b in bands):
                others += 1
        if not others:
            return True
        return QMessageBox.question(
            self, tr("Delete text"),
            tr("{n} letter(s) of other text overlap this text and would be deleted with "
               "it.\n\nDelete anyway? (Ctrl+Z undoes it.)").format(n=others)) == QMessageBox.Yes

    def delete_text_at(self, index, pt):
        """Edit text tool, right-click > Delete text: take out the paragraph under pt."""
        self.commit_pending()
        hit = [it for it in self.text_objects(index) if (it["rect"] + (-2, -2, 2, 2)).contains(pt)]
        if not hit:
            self.statusMessage.emit(tr("No text there"))
            return
        item = min(hit, key=lambda it: it["rect"].get_area())
        self.obj_sel = (index, [item])
        self.delete_objects()
        self.obj_sel = None

    def ungroup_objects(self):
        """Take the selected groups apart: their shapes, pictures and text become separate
        objects of the page (Edit objects, Edit text)."""
        from . import page_objects
        if self.obj_sel is None or not any(it["kind"] == "group" for it in self.obj_sel[1]):
            return
        groups = [it for it in self.obj_sel[1] if it["kind"] == "group"]
        self.obj_sel = (self.obj_sel[0], groups)
        self._objects_edit(tr("Ungrouped"), page_objects.ungroup, keep=False)

    def copy_picture(self):
        """Copy the one selected picture (Ctrl+V pastes it as an image markup)."""
        if not self.require_permission(pymupdf.PDF_PERM_COPY,
                                       tr("Copying pictures or page content")):
            return
        from . import clip
        from PySide6.QtGui import QImage
        items = self.selected_objects()
        if len(items) != 1 or items[0]["kind"] != "picture":
            return
        index, info = self.obj_sel[0], items[0]
        if not info["xref"]:            # inline picture: copy how that area looks
            page = self.doc[index]
            self.capture_area(index, info["rect"] & page.rect)
            return
        pix = pymupdf.Pixmap(self.doc, info["xref"])
        if pix.n - pix.alpha not in (1, 3):
            pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
        png = pix.tobytes("png")
        r = info["rect"]
        clip.put("capture", {"png": png, "w": r.width, "h": r.height},
                 image=QImage.fromData(png, "PNG"))
        self.statusMessage.emit(tr("Picture copied: Ctrl+V pastes it as an image markup"))

    def save_picture(self):
        if not self.require_permission(pymupdf.PDF_PERM_COPY,
                                       tr("Copying pictures or page content")):
            return
        from PySide6.QtWidgets import QFileDialog
        items = self.selected_objects()
        if len(items) != 1 or not items[0]["xref"]:
            return
        data, ext = annotations.image_bytes(self.doc, items[0]["xref"])
        folder = os.path.dirname(self.path) if self.path else ""
        out, _ = QFileDialog.getSaveFileName(self, tr("Save picture as"),
                                             os.path.join(folder, tr("picture") + "." + ext),
                                             tr("{kind} image").format(kind=ext.upper())
                                             + f" (*.{ext})")
        if out:
            with open(out, "wb") as f:
                f.write(data)
            self.statusMessage.emit(tr("Saved {name}").format(name=os.path.basename(out)))

    REDACT_TAG = "Redaction: "         # Search & redact marks remember their term in /Contents

    @staticmethod
    def _widget_texts(w):
        """Every piece of text a form field carries: value, option list, tooltip, name."""
        out = [w.field_value, w.field_label, w.field_name]
        out += [o if isinstance(o, str) else " ".join(map(str, o)) for o in (w.choice_values or [])]
        return [str(t) for t in out if t]

    @staticmethod
    def _link_texts(ln):
        return [str(ln.get(k)) for k in ("uri", "file") if ln.get(k)]

    def hidden_matches(self, text):
        """Where `text` occurs outside the page drawing (which page redaction can't reach):
        {"fields", "markups", "bookmarks", "metadata"} -> count."""
        t = text.lower()
        n = {"fields": 0, "markups": 0, "links": 0, "bookmarks": 0, "metadata": 0}
        for i in range(self.doc.page_count):
            pg = self.doc[i]
            for w in pg.widgets():
                if any(t in x.lower() for x in self._widget_texts(w)):
                    n["fields"] += 1
            n["links"] += sum(1 for ln in pg.get_links()
                              if any(t in x.lower() for x in self._link_texts(ln)))
            for a in pg.annots():
                if a.type[0] == pymupdf.PDF_ANNOT_REDACT:
                    continue
                if any(t in (a.info.get(k) or "").lower() for k in ("content", "subject", "title")):
                    n["markups"] += 1
        n["bookmarks"] = sum(1 for _l, title, _p in self.doc.get_toc() if t in title.lower())
        n["metadata"] = sum(1 for v in (self.doc.metadata or {}).values()
                            if isinstance(v, str) and t in v.lower())
        return n

    def _redaction_terms(self):
        terms = set()
        for i in range(self.doc.page_count):
            for a in self.doc[i].annots():
                c = a.info.get("content") or ""
                if a.type[0] == pymupdf.PDF_ANNOT_REDACT and c.startswith(self.REDACT_TAG):
                    terms.add(c[len(self.REDACT_TAG):])
        return {t for t in terms if t.strip()}

    @staticmethod
    def _clear_under_marks(pg, rects):
        """Delete form fields and markups that a redaction mark overlaps: page redaction only
        cleans the page drawing, and a field or note keeps its own copy of the text."""
        def hit(r):
            r = pymupdf.Rect(r)
            return any(r.intersects(m) for m in rects)
        for w in list(pg.widgets()):
            if hit(w.rect):
                pg.delete_widget(w)
        for x in [a.xref for a in pg.annots()
                  if a.type[0] not in (pymupdf.PDF_ANNOT_REDACT, pymupdf.PDF_ANNOT_POPUP)
                  and hit(a.rect)]:
            pg.delete_annot(pg.load_annot(x))

    # text a person typed or sees, in KanzonasPDF's private markup data (stamp labels, names
    # and dates, notes): the rest is structure (kind, colors, geometry, picture data), where a
    # search term like "rect" or "fill" must not match
    PRIVATE_TEXT_KEYS = {"text", "detail", "label", "author", "subject", "title", "content"}

    def _private_text(self, xref):
        typ, val = self.doc.xref_get_key(xref, annotations.KZ_KEY)
        if typ == "null" or not val:
            return []
        try:
            data = json.loads(val)
        except ValueError:
            return [val]                    # unreadable: treat it all as text, to be safe
        out = []

        def walk(node, key=None):
            if isinstance(node, dict):
                for k, v in node.items():
                    walk(v, k)
            elif isinstance(node, list):
                for v in node:
                    walk(v, key)
            elif isinstance(node, str) and key in self.PRIVATE_TEXT_KEYS:
                out.append(node)
        walk(data)
        return out

    REDACT_DROP = ("stamp", "image", "attach")      # Search & redact deletes these whole

    def _annot_has(self, pg, xref, pat):
        """The markup's note, subject, author or private text matches the redaction terms."""
        a = pg.load_annot(xref)
        info = [a.info.get(k) or "" for k in ("content", "subject", "title")]
        return any(pat.search(v) for v in info + self._private_text(xref))

    def _scrub_terms(self, terms):
        """Remove Search & redact terms from places outside the page drawing: form field
        values, option lists, tooltips and names and links (deleted), markup text (replaced
        by [redacted] in notes and comments; stamps, pictures and attachments are deleted),
        bookmark titles and document properties (replaced)."""
        import re
        if not terms:
            return
        pat = re.compile("|".join(re.escape(t) for t in sorted(terms, key=len, reverse=True)),
                         re.IGNORECASE)

        def clean(v):
            return pat.sub("[redacted]", v) if isinstance(v, str) else v
        for i in range(self.doc.page_count):
            pg = self.doc[i]
            for w in list(pg.widgets()):
                # value, option list, tooltip or name: its stored appearance and dictionary
                # hold the text, so the whole field goes
                if any(pat.search(x) for x in self._widget_texts(w)):
                    pg.delete_widget(w)
            for ln in pg.get_links():
                if any(pat.search(x) for x in self._link_texts(ln)):
                    pg.delete_link(ln)          # e.g. a mailto: or web address with the term
            for x in [a.xref for a in pg.annots() if a.type[0] != pymupdf.PDF_ANNOT_REDACT]:
                if not self._annot_has(pg, x, pat):
                    continue
                model = annotations.read(pg.load_annot(x))
                if model is not None and model["kind"] not in self.REDACT_DROP and \
                        annotations.text_editable(model):
                    # a note or comment stays, with the term replaced: it's written anew,
                    # so no old copy of the text stays in its appearance or private data
                    model["text"] = clean(model.get("text") or "")
                    model["author"] = clean(model.get("author") or "")
                    x = annotations.replace(pg, x, model)
                    if not self._annot_has(pg, x, pat):
                        continue
                # anything else goes whole: its appearance (a stamp's picture, say) or
                # private data can hold the text too
                pg.delete_annot(pg.load_annot(x))
        toc = self.doc.get_toc(simple=False)
        if any(pat.search(e[1]) for e in toc):
            self.doc.set_toc([[e[0], clean(e[1])] + e[2:] for e in toc])
        meta = self.doc.metadata or {}
        if any(pat.search(v) for v in meta.values() if isinstance(v, str)):
            self.doc.set_metadata({k: clean(v) for k, v in meta.items() if v is not None})
        try:
            if pat.search(self.doc.get_xml_metadata() or ""):
                self.doc.del_xml_metadata()     # XMP copy of the properties
        except Exception:
            pass

    def remove_term(self, term):
        """Search & redact for text that's only in fields, notes, bookmarks or properties."""
        self.clear_selection()
        self.modify(lambda: self._scrub_terms({term}), structural=True)

    def pending_redactions(self, pages=None):
        """How many redaction marks (on these pages; None: all) aren't applied yet."""
        n = 0
        for i in range(self.doc.page_count) if pages is None else pages:
            pg = self.doc[i]
            n += sum(1 for _x, t, *_ in pg.annot_xrefs() if t == pymupdf.PDF_ANNOT_REDACT)
        return n

    def apply_redactions(self, scrub=True):
        """Permanently remove everything under the redaction marks (text, images, drawings).

        Unless scrub is False, also remove metadata, attachments, hidden text, scripts and
        XML metadata, then rewrite the file so unlinked copies of that data are gone.
        """
        def do():
            self._scrub_terms(self._redaction_terms())
            for i in range(self.doc.page_count):
                pg = self.doc[i]
                marks = [pymupdf.Rect(a.rect) for a in pg.annots()
                         if a.type[0] == pymupdf.PDF_ANNOT_REDACT]
                if marks:
                    self._clear_under_marks(pg, marks)
                    # Secure redaction removes crossing paths completely. Keeping them
                    # behind an opaque fill would leave confidential geometry recoverable.
                    pg.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_PIXELS,
                                        graphics=pymupdf.PDF_REDACT_LINE_ART_REMOVE_IF_TOUCHED,
                                        text=pymupdf.PDF_REDACT_TEXT_REMOVE)
            if scrub:
                self.doc.scrub(attached_files=True, clean_pages=True, embedded_files=True,
                               hidden_text=True, javascript=True, metadata=True,
                               redactions=False, remove_links=False, reset_fields=False,
                               reset_responses=True, thumbnails=True, xml_metadata=True)
                remove_scripts(self.doc)
                # scrub unlinks the old objects; a plain tobytes() would still carry them.
                enc = self._orig_enc is not None and (self.doc.metadata or {}).get("encryption")
                data = self.doc.tobytes(
                    garbage=4, deflate=True,
                    **({"encryption": pymupdf.PDF_ENCRYPT_KEEP} if enc else {}))
                self.doc.close()
                self.doc = pymupdf.open(stream=data, filetype="pdf")
                if self.doc.needs_pass and self._orig_enc is not None:
                    for pw in (self._orig_enc.get("owner_pw"), self._orig_enc.get("user_pw")):
                        if pw and self.doc.authenticate(pw):
                            break
        self.clear_selection()
        self.modify(do, structural=True)

    # ---- layers (optional content) -------------------------------------------------------
    def layer_configs(self):
        try:
            return self.doc.layer_ui_configs()
        except Exception:
            return []

    def set_layer(self, number, visible):
        """Show/hide a layer. This is a viewing choice, not an edit (no undo, not 'unsaved')."""
        self.doc.set_layer_ui_config(number, 1 if visible else 2)
        self._redraw_all()

    def set_all_layers(self, visible):
        for c in self.layer_configs():
            if not c.get("locked"):
                self.doc.set_layer_ui_config(c["number"], 1 if visible else 2)
        self._redraw_all()

    def _redraw_all(self):
        self._dlists = {}
        self._tiles = OrderedDict()
        for w in self.pages:
            w.invalidate()
        self.layersChanged.emit()

    # ---- bookmarks & page tools -----------------------------------------------------------
    def get_toc(self):
        return self.doc.get_toc(simple=True)

    def set_toc(self, toc):
        self.modify(lambda: self.doc.set_toc(toc), [])
        self.documentChanged.emit()

    def add_header_footer(self, spec):
        from . import page_tools
        self.modify(lambda: page_tools.add_header_footer(self.doc, spec, os.path.basename(self.path)),
                    spec["pages"])

    def add_watermark(self, spec):
        from . import page_tools
        self.modify(lambda: page_tools.add_watermark(self.doc, spec), spec["pages"])

    def remove_watermarks(self, pages):
        from . import page_tools
        if not pages:
            self.statusMessage.emit(tr("Those pages have no watermark to remove"))
            return
        count = {"n": 0}

        def do():
            count["n"] = page_tools.remove_watermarks(self.doc, pages)
        self.modify(do, pages)
        self._obj_cache = {}
        self.statusMessage.emit(tr("Removed {n} watermark(s) from {pages} page(s) "
                                   "(Ctrl+Z undoes it)").format(n=count["n"], pages=len(pages)))

    def add_background(self, spec, pages):
        from . import background
        self.modify(lambda: background.apply(self.doc, pages, spec), pages)
        self._obj_cache = {}
        self.statusMessage.emit(tr("Background added to {pages} page(s) (Ctrl+Z undoes it)")
                                .format(pages=len(pages)))

    def remove_background(self, pages):
        from . import background
        if not pages:
            self.statusMessage.emit(tr("Those pages have no background to remove"))
            return
        self.modify(lambda: background.remove_pages(self.doc, pages), pages)
        self.statusMessage.emit(tr("Background removed from {pages} page(s)").format(pages=len(pages)))

    # ---- digitally signed documents --------------------------------------------------------
    def check_digital_signatures(self):
        """Validate certificate signatures; signed files open read-only with a banner."""
        self.sig_results = []
        try:
            if self.doc.get_sigflags() < 1:
                return
            from . import digisign
            with open(self.path, "rb") as f:
                self.sig_results = digisign.validate(f.read())
        except Exception as ex:
            # A form with only empty signature fields has nothing to keep valid.
            if not self._has_filled_signature():
                return
            self.sig_results = [{"summary": tr("Couldn't check the signature: {error}").format(
                                     error=ex), "ok": False,
                                 "intact": False}]
        if not self.sig_results:
            return
        self.read_only = True
        good = all(r.get("ok") for r in self.sig_results)
        text = "  ".join(r["summary"] for r in self.sig_results)
        color = "#e7f6e7" if good else "#fde8e8"
        self.show_banner(("✔ " if good else "⚠ ") + text +
                         "  " + tr("This file is read-only so the signature stays valid."),
                         color, tr("Edit anyway"), self._edit_signed)

    def _has_filled_signature(self):
        """True if any signature field holds a signature (/V), false for empty ones only."""
        try:
            for page in self.doc:
                for w in page.widgets(types=[pymupdf.PDF_WIDGET_TYPE_SIGNATURE]):
                    if w.is_signed:
                        return True
        except Exception:
            return True
        return False

    def _edit_signed(self):
        r = QMessageBox.question(
            self, tr("Edit a signed document?"),
            tr("Changing a digitally signed document makes its signature show as changed or "
               "invalid in Acrobat and other readers.\n\nTip: use Save As to keep the signed "
               "original untouched.\n\nEdit anyway?"))
        if r == QMessageBox.Yes:
            self.read_only = False
            self.show_banner(tr("Editing a signed document: when saved, its digital signature "
                                "will no longer validate."), "#fff4d6")

    def show_banner(self, text, color="#fff4d6", button=None, callback=None):
        if getattr(self, "_banner", None) is None:
            self._banner = QWidget(self)
            lay = QHBoxLayout(self._banner)
            lay.setContentsMargins(8, 4, 8, 4)
            self._banner_label = QLabel()
            self._banner_label.setWordWrap(True)
            self._banner_btn = QPushButton()
            self._banner_btn.clicked.connect(lambda: self._banner_cb and self._banner_cb())
            lay.addWidget(self._banner_label, 1)
            lay.addWidget(self._banner_btn)
        self._banner.setStyleSheet(f"background:{color}; color:#222; border-bottom:1px solid #bbb;")
        self._banner_label.setText(text)
        self._banner_cb = callback
        self._banner_btn.setVisible(button is not None)
        if button:
            self._banner_btn.setText(button)
        self._banner.show()
        self._place_banner()

    def _place_banner(self):
        b = getattr(self, "_banner", None)
        if b is None or b.isHidden():        # (isVisible() is False until the window shows)
            return
        b.setFixedWidth(self.width())
        h = b.sizeHint().height()
        b.setGeometry(0, 0, self.width(), h)
        self.setViewportMargins(0, h, 0, 0)
        b.raise_()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._place_banner()
        if self.free_pan:
            self.apply_canvas()
        # Fit width / Fit page keep fitting when the window or the side panels change size
        # (the window often grows to its final size just after a file opens)
        if self.fit_mode and e.size().width() != e.oldSize().width() or \
                self.fit_mode == "page" and e.size().height() != e.oldSize().height():
            if not getattr(self, "_refit_queued", False):
                self._refit_queued = True
                QTimer.singleShot(0, self._refit)

    def _refit(self):
        import shiboken6
        self._refit_queued = False
        if not shiboken6.isValid(self):
            return                      # queued with a timer: the view was closed meanwhile
        if self.fit_mode == "width":
            self.fit_width()
        elif self.fit_mode == "page":
            self.fit_page()

    # ---- signatures & initials -------------------------------------------------------
    SIG_WIDTH = {"signature": 144.0, "initials": 54.0}     # default size in points

    def sig_pixmap(self, kind):
        return self.sig_images.get(kind, (None, None))[1]

    def set_sig_image(self, kind, png):
        pm = QPixmap()
        pm.loadFromData(png, "PNG")
        self.sig_images[kind] = (png, pm)

    def sig_display_rect(self, index, kind, pt, box=None):
        """Displayed (rotated) rect the image will occupy when dropped at unrotated pt."""
        pm = self.sig_pixmap(kind)
        aspect = pm.height() / pm.width() if pm and pm.width() else 0.35
        page = self.doc[index]
        p = pymupdf.Point(pt) * page.rotation_matrix
        if box is not None:
            return box
        w = self.SIG_WIDTH[kind]
        return pymupdf.Rect(p.x - w / 2, p.y - w * aspect / 2, p.x + w / 2, p.y + w * aspect / 2)

    def place_signature(self, index, kind, pt=None, field_rect=None, box=None):
        """Write the saved signature/initials (and today's date) into the page content."""
        if kind not in self.sig_images:
            return
        png, pm = self.sig_images[kind]
        page = self.doc[index]
        if field_rect is not None:      # fill a signature form field
            disp = pymupdf.Rect(field_rect) * page.rotation_matrix
        elif box is not None:           # dragged to size (displayed coordinates)
            disp = pymupdf.Rect(box)
        else:
            disp = self.sig_display_rect(index, kind, pt)
        when = ""                       # the date is its own tool now (Date, Ctrl+;)
        if not hasattr(self, "_last_sig_spot"):
            self._last_sig_spot = {}
        self._last_sig_spot[kind] = pymupdf.Rect(disp)

        def do():
            self._draw_signature(self.doc[index], kind, disp, when)
        # signing a signature field is filling in the form ("Filling in form fields and
        # signing" allows it); placing it anywhere else changes the page
        self.modify(do, [index], permission=pymupdf.PDF_PERM_FORM if field_rect is not None
                    else pymupdf.PDF_PERM_MODIFY)
        self.signed = True
        self.signedDocument.emit()
        self.oneShotPlaced.emit()

    def place_date(self, index, pt):
        """Date tool: today's date (format from Preferences > You) written into the page with
        its baseline at pt, reading upright as displayed."""
        text = signatures.date_text()

        def do():
            pg = self.doc[index]
            pg.insert_text(pymupdf.Point(pt), text, fontsize=10, fontname="helv",
                           color=(0.1, 0.1, 0.1), rotate=pg.rotation)
        # dating a form field is filling in the form; anywhere else it changes the page
        on_field = self.widget_at(index, pymupdf.Point(pt)) is not None
        self.modify(do, [index], permission=pymupdf.PDF_PERM_FORM if on_field
                    else pymupdf.PDF_PERM_MODIFY)
        self.statusMessage.emit(tr("Dated {date} (Ctrl+Z undoes it)").format(date=text))
        self.oneShotPlaced.emit()

    # ---- protection (read-only PDFs) ----------------------------------------------------
    def allowed(self, permission):
        """Honor PDF permission flags independently; signed documents remain protected."""
        if getattr(self, "sig_results", None) and self.read_only and permission not in (
                pymupdf.PDF_PERM_COPY, pymupdf.PDF_PERM_PRINT, pymupdf.PDF_PERM_PRINT_HQ):
            return False
        if getattr(self, "_owner_authorized", False):
            return True
        permissions = self._orig_enc["perms"] if self._orig_enc is not None else self.doc.permissions
        return bool(permissions & permission)

    def require_permission(self, permission, operation):
        if self.allowed(permission):
            return True
        QMessageBox.information(self, tr("Protected document"),
                                tr("{operation} is not allowed by this PDF's permissions.")
                                .format(operation=operation))
        return False

    def _check_permissions(self):
        # (permissions is a signed 32-bit value: restricted files report negative numbers too)
        perm = self.doc.permissions
        self.read_only = not (getattr(self, "_owner_authorized", False) or
                              perm & (pymupdf.PDF_PERM_MODIFY | pymupdf.PDF_PERM_ANNOTATE | pymupdf.PDF_PERM_FORM))

    def unlock(self, password):
        """Unlock editing with the permissions (owner) password."""
        rc = self.doc.authenticate(password)
        if rc & 4:                     # 4 = owner password accepted
            self._owner_authorized = True
            if self._orig_enc is not None:
                self._orig_enc["owner_pw"] = password
            self._check_permissions()
            return not self.read_only
        return False

    def security_state(self):
        """What protection the file has now: {'encrypted', 'open_pw', 'perms'}."""
        meta = self.doc.metadata or {}
        enc = meta.get("encryption")
        return {"encrypted": bool(enc), "method": enc or "", "perms": self.doc.permissions,
                "is_owner": bool(self.doc.permissions & pymupdf.PDF_PERM_MODIFY)}

    def owner_authorized(self):
        """True when the security of this document may be changed: it has no permissions
        password, or that password was given (Unlock with password). A file whose
        permissions allow editing still needs it to change or remove its protection."""
        return bool(getattr(self, "_owner_authorized", False))

    def set_security(self, open_pw="", owner_pw="", perms=-1):
        """Security to apply on the next save ('' / '' removes all protection). When form
        filling isn't allowed, the form's fields are made read-only right away (undoable):
        every PDF reader honors that, even those that ignore permissions (web browsers);
        allowing it again, or removing the security, unlocks the fields locked this way."""
        if not getattr(self, "_owner_authorized", False):
            raise PermissionError(tr("Unlock the document with its permissions password first."))
        lock = bool(owner_pw) and perms != -1 and not perms & pymupdf.PDF_PERM_FORM
        if self.lock_fields(lock, dry_run=True):
            self.modify(lambda: self.lock_fields(lock), list(range(self.doc.page_count)))
        self.security = {"open_pw": open_pw, "owner_pw": owner_pw, "perms": perms}
        from .autosave import _remove
        backup = getattr(self, "_backup_path", None)
        if backup and (open_pw or owner_pw):
            _remove(backup)
            self._backup_path = None
        self.dirty = True
        self.documentChanged.emit()

    LOCK_MARK = "KZLocked"      # on fields KanzonasPDF made read-only when protecting

    def _field_dict(self, w):
        """xref of the dictionary holding a widget's field entries (name, flags): the widget
        itself, or its parent when the widget is only one appearance of a field."""
        typ, _v = self.doc.xref_get_key(w.xref, "T")
        if typ == "null":
            parent = self._parent_xref(w.xref)
            if parent is not None:
                return parent
        return w.xref

    def lock_fields(self, lock, dry_run=False):
        """Make every form field read-only (lock), marked as locked by KanzonasPDF, or undo
        that for the fields so marked. Returns how many fields change (dry_run: count only)."""
        n, seen = 0, set()
        for page in self.doc:
            for w in page.widgets():
                fx = self._field_dict(w)
                if fx in seen:
                    continue
                seen.add(fx)
                typ, val = self.doc.xref_get_key(fx, "Ff")
                ff = int(float(val)) if typ == "int" or (typ and val.lstrip("-").isdigit()) else 0
                marked = self.doc.xref_get_key(fx, self.LOCK_MARK)[0] != "null"
                if lock and not ff & 1:
                    n += 1
                    if not dry_run:
                        self.doc.xref_set_key(fx, "Ff", str(ff | 1))
                        self.doc.xref_set_key(fx, self.LOCK_MARK, "true")
                elif not lock and marked:
                    n += 1
                    if not dry_run:
                        self.doc.xref_set_key(fx, "Ff", str(ff & ~1))
                        self.doc.xref_set_key(fx, self.LOCK_MARK, "null")
        if n and not dry_run:
            self._card_cache.clear()
        return n

    def form_filled(self):
        """True when any form field has an answer (text typed, a box ticked, a choice made)."""
        for page in self.doc:
            for w in page.widgets():
                v = w.field_value
                if v in (None, "", "Off", False) or \
                        w.field_type == pymupdf.PDF_WIDGET_TYPE_BUTTON:
                    continue
                if w.field_type in (pymupdf.PDF_WIDGET_TYPE_COMBOBOX,
                                    pymupdf.PDF_WIDGET_TYPE_LISTBOX) and \
                        self._preselected(w, v):
                    continue                # (a dropdown shows its first choice untouched)
                return True
        return False

    def _preselected(self, w, value):
        """value is what a choice field shows before anyone picks: its default (/DV; a
        dropdown made here gets its first choice as default)."""
        kind, dv = self.doc.xref_get_key(self._field_dict(w), "DV")
        return kind == "string" and dv == value

    # ---- sanitize ---------------------------------------------------------------------------
    SANITIZE_OPTIONS = [  # (key, label, default)
        ("metadata", tr("Document information (author, title, dates, producer)"), True),
        ("javascript", tr("JavaScript and automatic actions"), True),
        ("embedded_files", tr("Attached and embedded files"), True),
        ("hidden_text", tr("Hidden text (e.g. invisible OCR text)"), False),
        ("links", tr("Links"), False),
        ("markups", tr("Comments and markups"), False),
        ("form_data", tr("Data typed into form fields"), False),
        ("thumbnails", tr("Page thumbnails and leftover redaction data"), True),
    ]

    def sanitize(self, opts):
        """Remove hidden or sensitive content (Protect > Sanitize document)."""
        def do():
            self.doc.scrub(attached_files=opts.get("embedded_files", False),
                           embedded_files=opts.get("embedded_files", False),
                           clean_pages=True, hidden_text=opts.get("hidden_text", False),
                           javascript=opts.get("javascript", False),
                           metadata=opts.get("metadata", False),
                           xml_metadata=opts.get("metadata", False),
                           redactions=False, redact_images=0,
                           remove_links=opts.get("links", False),
                           reset_fields=opts.get("form_data", False),
                           reset_responses=opts.get("markups", False),
                           thumbnails=opts.get("thumbnails", False))
            if opts.get("javascript"):
                remove_scripts(self.doc)
            if opts.get("thumbnails"):
                for i in range(self.doc.page_count):   # (scrub left /Thumb in place)
                    if self.doc.xref_get_key(self.doc.page_xref(i), "Thumb")[0] != "null":
                        self.doc.xref_set_key(self.doc.page_xref(i), "Thumb", "null")
            if opts.get("form_data"):
                clear_form_data(self.doc)
            if opts.get("markups"):
                for i in range(self.doc.page_count):
                    pg = self.doc[i]
                    for x in [a.xref for a in pg.annots()]:
                        pg.delete_annot(pg.load_annot(x))
        self.clear_selection()
        self.modify(do, structural=True)

    # ---- apply only some redactions -------------------------------------------------------------
    def apply_selected_redactions(self):
        """Apply the selected redaction marks only; other marks stay pending."""
        if self.selection is None:
            return 0
        index = self.selection[0]
        chosen = [x for x, m in self.selected_models() if m["kind"] == "redact"]
        if not chosen:
            return 0

        def do():
            pg = self.doc[index]
            terms = {a.info.get("content", "")[len(self.REDACT_TAG):]
                     for a in pg.annots() if a.xref in chosen
                     and a.info.get("content", "").startswith(self.REDACT_TAG)}
            self._scrub_terms(terms)
            others = []
            for an in list(pg.annots()):
                if an.type[0] == pymupdf.PDF_ANNOT_REDACT and an.xref not in chosen:
                    others.append(annotations.read(an))
            for an in [a.xref for a in pg.annots()
                       if a.type[0] == pymupdf.PDF_ANNOT_REDACT and a.xref not in chosen]:
                pg.delete_annot(pg.load_annot(an))
            marks = [pymupdf.Rect(a.rect) for a in pg.annots()
                     if a.type[0] == pymupdf.PDF_ANNOT_REDACT]
            self._clear_under_marks(pg, marks)
            pg.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_PIXELS,
                                graphics=pymupdf.PDF_REDACT_LINE_ART_REMOVE_IF_TOUCHED,
                                text=pymupdf.PDF_REDACT_TEXT_REMOVE)
            for m in others:                       # put the other marks back
                annotations.write(pg, m)
        self.clear_selection()
        self.modify(do, [index])
        return len(chosen)

    # ---- digital signatures: clear, timestamp ---------------------------------------------------
    def clear_signatures(self):
        """Remove every digital signature value (fields stay, unsigned). Returns how many."""
        n = {"n": 0}

        def do():
            for i in range(self.doc.page_count):
                pg = self.doc[i]
                for w in list(pg.widgets()):
                    if w.field_type == pymupdf.PDF_WIDGET_TYPE_SIGNATURE:
                        typ, _val = self.doc.xref_get_key(w.xref, "V")
                        if typ != "null":
                            self.doc.xref_set_key(w.xref, "V", "null")
                            self.doc.xref_set_key(w.xref, "AP", "null")
                            n["n"] += 1
            cat = self.doc.pdf_catalog()
            self.doc.xref_set_key(cat, "Perms", "null")     # certification lock
            if n["n"] and self.doc.xref_get_key(cat, "AcroForm/SigFlags")[0] != "null":
                self.doc.xref_set_key(cat, "AcroForm/SigFlags", "0")
        was = self.read_only
        self.read_only = False
        self.modify(do, list(range(self.doc.page_count)))
        if not n["n"]:
            self.read_only = was
        else:
            self.sig_results = []
            self.show_banner(tr("Digital signatures removed. Save to keep the unsigned "
                                "version."), "#fff4d6")
        return n["n"]

    def timestamp(self, url, out_path):
        """Add a trusted timestamp (RFC 3161) from a time server; writes out_path."""
        from . import digisign
        if self.dirty or self.untitled:
            raise RuntimeError(tr("Save your changes first."))
        with open(self.path, "rb") as f:
            data = f.read()
        return digisign.timestamp(data, out_path, url)

    # ---- multi-place signature & placeholders -------------------------------------------------
    def _draw_signature(self, pg, kind, disp, when=""):
        png, _pm = self.sig_images[kind]
        img_rect = disp * pg.derotation_matrix
        pg.insert_image(img_rect, stream=png, keep_proportion=True, rotate=pg.rotation,
                        overlay=True)
        if when:
            size = 9 if kind == "signature" else 7
            base = pymupdf.Point(disp.x0, disp.y1 + size + 1) * pg.derotation_matrix
            pg.insert_text(base, when, fontsize=size, fontname="helv",
                           color=(0.1, 0.1, 0.1), rotate=pg.rotation)

    SIG_SPOTS = ["bottom right", "bottom left", "bottom center", "top right", "top left"]

    def _spot_rect(self, index, kind, spot, margin=36):
        page = self.doc[index]
        pr = page.rect                                     # displayed page
        r = self.sig_display_rect(index, kind, page.rect.tl * page.derotation_matrix)
        w, h = r.width, r.height
        x = {"right": pr.x1 - margin - w, "left": pr.x0 + margin,
             "center": (pr.x0 + pr.x1 - w) / 2}[spot.split()[1]]
        y = (pr.y1 - margin - h - 12) if spot.startswith("bottom") else pr.y0 + margin
        return pymupdf.Rect(x, y, x + w, y + h)

    def place_signature_on_pages(self, kind, pages, spot):
        """Multi-place: the saved signature / initials on several pages at once. spot is a
        corner name, or 'same' = where it was last placed (same spot on every page)."""
        if kind not in self.sig_images or not pages:
            return 0
        when = ""
        last = getattr(self, "_last_sig_spot", {}).get(kind)

        def do():
            for i in pages:
                pg = self.doc[i]
                disp = pymupdf.Rect(last) if spot == "same" and last is not None                     else self._spot_rect(i, kind, spot if spot != "same" else "bottom right")
                self._draw_signature(pg, kind, disp, when)
        self.modify(do, list(pages))
        self.signed = True
        self.signedDocument.emit()
        return len(pages)

    def placeholders(self):
        """[(page, xref, 'signature'|'initials', rect)] for every placeholder in the file."""
        out = []
        for i in range(self.doc.page_count):
            pg = self.doc[i]
            for an in annotations.each_annot(pg):
                m = annotations.read(an) if an.type[0] == pymupdf.PDF_ANNOT_FREE_TEXT else None
                if m and m["kind"] == "placeholder":
                    out.append((i, an.xref, m["props"].get("for", "initials"), m["rect"]))
        return out

    def apply_placeholders(self, kinds=("signature", "initials")):
        """Fill every placeholder with your saved signature / initials (and the date)."""
        todo = [t for t in self.placeholders() if t[2] in kinds and t[2] in self.sig_images]
        if not todo:
            return 0
        when = signatures.date_text()

        def do():
            for i, xref, kind, rect in todo:
                pg = self.doc[i]
                pg.delete_annot(pg.load_annot(xref))
                self._draw_signature(pg, kind, rect * pg.rotation_matrix, when)
        self.clear_selection()
        self.modify(do, sorted({t[0] for t in todo}))
        self.signed = True
        self.signedDocument.emit()
        return len(todo)

    # ---- form filling ----------------------------------------------------------------
    def _widget_at(self, page, pt):
        for w in page.widgets():
            if w.rect.contains(pt):
                return w
        return None

    def widget_at(self, index, pt):
        # cached boxes: this runs on every mouse move, and a big form has hundreds of fields
        key = ("fieldx", index)
        boxes = self._card_cache.get(key)
        if boxes is None:
            boxes = [(tuple(w.rect), w.xref) for w in self.doc[index].widgets()]
            self._card_cache[key] = boxes
        px, py = pt.x, pt.y
        return next((x for (x0, y0, x1, y1), x in boxes
                     if x0 <= px <= x1 and y0 <= py <= y1), None)

    def fill_field(self, index, xref):
        self._set_field_focus(index, xref)
        page = self.doc[index]
        w = page.load_widget(xref)
        if w.field_flags & 1:
            self.statusMessage.emit(
                tr("This field is read-only. Allow filling in form fields in Security "
                   "properties to unlock it.") if self.doc.xref_get_key(
                    self._field_dict(w), self.LOCK_MARK)[0] != "null"
                else tr("This field is read-only."))
            return
        t = w.field_type
        if t == pymupdf.PDF_WIDGET_TYPE_CHECKBOX:
            on = w.on_state()
            value = "Off" if w.field_value == on else on
            self._set_field(index, xref, value)
        elif t == pymupdf.PDF_WIDGET_TYPE_RADIOBUTTON:
            self._choose_option(index, xref)
        elif t in (pymupdf.PDF_WIDGET_TYPE_COMBOBOX, pymupdf.PDF_WIDGET_TYPE_LISTBOX):
            menu = QMenu(self)
            for c in w.choice_values or []:
                # a choice can have a value saved in the file apart from the text shown
                # ([NY, New York]): the saved one is what the form's data needs
                value, label = (c[0], c[1]) if isinstance(c, (list, tuple)) else (c, c)
                act = menu.addAction(label)
                act.setData(value)
                act.setCheckable(True)
                act.setChecked(w.field_value in (value, label))
            typed = None
            if w.field_type == pymupdf.PDF_WIDGET_TYPE_COMBOBOX and \
                    w.field_flags & pymupdf.PDF_CH_FIELD_IS_EDIT:
                menu.addSeparator()
                typed = menu.addAction(tr("Type a value..."))
            pw = self.pages[index]
            r = pw.to_screen(w.rect)
            chosen = menu.exec(pw.mapToGlobal(r.bottomLeft().toPoint()))
            if chosen is not None and chosen is typed:
                text, ok = QInputDialog.getText(self, w.field_name or tr("Dropdown"),
                                                tr("Value:"), text=w.field_value or "")
                if ok:
                    self._set_field(index, xref, text)
            elif chosen is not None:
                self._set_field(index, xref, chosen.data())
        elif t == pymupdf.PDF_WIDGET_TYPE_SIGNATURE:
            self.requestSignature.emit(index, xref)
        elif t == pymupdf.PDF_WIDGET_TYPE_TEXT:
            self._edit_text_field(index, xref)

    def _set_field(self, index, xref, value):
        def do():
            pg = self.doc[index]          # keep the page alive while using its widget
            w = pg.load_widget(xref)
            w.field_value = value
            w.update()
            if value == "":
                blank_appearance(self.doc, xref)   # (else the old text still shows)
        self.modify(do, [index], permission=pymupdf.PDF_PERM_FORM)

    def _choose_option(self, index, xref):
        """Option (radio) button: turn this one on and every other button of its group off.
        A group is the buttons sharing a field name (KanzonasPDF makes each button its own
        field with the group's name) or the kids of one parent field (other PDF makers)."""
        name = self.doc[index].load_widget(xref).field_name
        others = [(i, w.xref) for i in range(self.doc.page_count)
                  for w in self.doc[i].widgets(types=[pymupdf.PDF_WIDGET_TYPE_RADIOBUTTON])
                  if w.field_name == name and (i, w.xref) != (index, xref)]

        def do():
            for _i, x in others:
                self.doc.xref_set_key(x, "AS", "/Off")
                if self.doc.xref_get_key(x, "V")[0] != "null":
                    self.doc.xref_set_key(x, "V", "/Off")
            pg = self.doc[index]
            w = pg.load_widget(xref)
            w.field_value = True
            w.update()
        self.modify(do, sorted({index} | {i for i, _x in others}), permission=pymupdf.PDF_PERM_FORM)

    def _edit_text_field(self, index, xref):
        page = self.doc[index]
        w = page.load_widget(xref)
        pw = self.pages[index]
        r = pw.to_screen(w.rect)
        multiline = bool(w.field_flags & pymupdf.PDF_TX_FIELD_IS_MULTILINE)
        ed = QPlainTextEdit(pw) if multiline else QLineEdit(pw)
        if multiline:
            ed.setPlainText(w.field_value or "")
            from . import spelling
            spelling.install(ed)
        else:
            ed.setText(w.field_value or "")
            ed.selectAll()
        maxlen = w.text_maxlen or 0         # the field's limit (a ZIP code, comb boxes)
        if maxlen > 0 and not multiline:
            ed.setMaxLength(maxlen)
        f = ed.font()
        size = w.text_fontsize or min(12.0, w.rect.height * 0.65)
        f.setPixelSize(max(8, int(size * self.zoom)))
        ed.setFont(f)
        ed.setGeometry(r.toRect().adjusted(-1, -1, 1, 1))
        ed.setStyleSheet("background:#fffbe6; color:#000; border:2px solid #0078d7;")
        done = {"x": False}

        def finish(save=True, next_field=None):
            if done["x"]:
                return
            done["x"] = True
            text = ed.toPlainText() if multiline else ed.text()
            if maxlen > 0:
                text = text[:maxlen]
            ed.hide()
            ed.deleteLater()
            if save and text != (w.field_value or ""):
                self._set_field(index, xref, text)
            if next_field is not None:
                self.next_field(back=next_field == "back", current=(index, xref))

        class Keys(QObject):
            def eventFilter(_s, obj, e):
                if e.type() == QEvent.KeyPress:
                    if e.key() == Qt.Key_Escape:
                        finish(save=False)
                        return True
                    if e.key() in (Qt.Key_Tab, Qt.Key_Backtab):
                        finish(next_field="back" if e.key() == Qt.Key_Backtab or
                               e.modifiers() & Qt.ShiftModifier else "next")
                        return True
                    if e.key() in (Qt.Key_Return, Qt.Key_Enter) and (
                            not multiline or e.modifiers() & Qt.ControlModifier):
                        finish()
                        return True
                elif e.type() == QEvent.FocusOut:
                    finish()
                return False
        self._field_keys = Keys(ed)
        ed.installEventFilter(self._field_keys)
        ed.show()
        ed.setFocus()

    field_focus = None      # (page, xref) of the form field Tab moved to / last filled

    def field_order(self):
        """Fillable fields in reading order: page by page, top to bottom, left to right."""
        order = []
        for i in range(self.doc.page_count):
            page = self.doc[i]
            shown = page.rotation_matrix                # reading order as the page is shown
            ws = [((w.rect * shown).normalize(), w.xref) for w in page.widgets()
                  if w.field_type != pymupdf.PDF_WIDGET_TYPE_BUTTON
                  and not w.field_flags & 1                          # 1 = read-only
                  and not self._annot_flag(w.xref) & 2]              # 2 = hidden
            ws.sort(key=lambda t: t[0].y0)
            # a row is the fields side by side, even when their tops differ by a point or
            # two (rounding each top put a field right of its neighbor first)
            rows = []
            for r, x in ws:
                if rows and r.y0 - rows[-1][0] <= max(3.0, 0.5 * min(r.height, rows[-1][1])):
                    rows[-1][2].append((r, x))
                else:
                    rows.append([r.y0, r.height, [(r, x)]])
            for _y, _h, row in rows:
                order += [(i, x) for _r, x in sorted(row, key=lambda t: t[0].x0)]
        return order

    def _annot_flag(self, xref):
        kind, val = self.doc.xref_get_key(xref, "F")
        try:
            return int(float(val)) if kind in ("int", "float") else 0
        except ValueError:
            return 0

    def next_field(self, back=False, current=None):
        """Tab / Shift+Tab: go to the next (previous) form field. Text fields open for typing;
        Space or Enter fills the others (check, choose, sign). False if there are no fields."""
        order = self.field_order()
        if not order:
            return False
        cur = current or self.field_focus
        if cur in order:
            k = (order.index(cur) + (-1 if back else 1)) % len(order)
        else:                                   # start on the page being viewed
            page = self.current_page()
            here = [k for k, (i, _x) in enumerate(order) if i >= page]
            k = (here[0] if here else 0) if not back else \
                ([k for k, (i, _x) in enumerate(order) if i <= page] or [len(order) - 1])[-1]
        index, xref = order[k]
        self._set_field_focus(index, xref)
        pg = self.doc[index]
        w = pg.load_widget(xref)
        top = self.pages[index].y() + (w.rect * pg.rotation_matrix).y0 * self.zoom
        vbar = self.verticalScrollBar()
        if not vbar.value() + 20 <= top <= vbar.value() + self.viewport().height() - 40:
            vbar.setValue(int(top - self.viewport().height() / 3))
        if w.field_type == pymupdf.PDF_WIDGET_TYPE_TEXT and not self.read_only:
            QTimer.singleShot(0, lambda: self._edit_text_field(index, xref))
        return True

    def _set_field_focus(self, index, xref):
        old = self.field_focus
        self.field_focus = (index, xref)
        for i in {index, old[0] if old else index}:
            if 0 <= i < len(self.pages):
                self.pages[i].update()

    def field_focus_rect(self, index):
        """Rect of the focused field if it's on this page (drawn with a focus outline)."""
        if self.field_focus is None or self.field_focus[0] != index:
            return None
        try:
            return pymupdf.Rect(self.doc[index].load_widget(self.field_focus[1]).rect)
        except Exception:
            return None

    def event(self, e):
        # Tab / Shift+Tab move between form fields (Hand and Select tools) instead of
        # moving the keyboard focus to the next control of the window
        if e.type() == QEvent.KeyPress and e.key() in (Qt.Key_Tab, Qt.Key_Backtab) and \
                self.tool in ("hand", "select") and \
                self.next_field(back=e.key() == Qt.Key_Backtab or
                                bool(e.modifiers() & Qt.ShiftModifier)):
            return True
        return super().event(e)

    # ---- form design ---------------------------------------------------------------
    FIELD_TYPES = {"f_text": pymupdf.PDF_WIDGET_TYPE_TEXT,
                   "f_check": pymupdf.PDF_WIDGET_TYPE_CHECKBOX,
                   "f_radio": pymupdf.PDF_WIDGET_TYPE_RADIOBUTTON,
                   "f_combo": pymupdf.PDF_WIDGET_TYPE_COMBOBOX,
                   "f_sign": pymupdf.PDF_WIDGET_TYPE_SIGNATURE,
                   "f_initials": pymupdf.PDF_WIDGET_TYPE_SIGNATURE}
    FIELD_PREFIX = {"f_text": "Text", "f_check": "Check", "f_radio": "Option",
                    "f_combo": "Dropdown", "f_sign": "Signature",
                    "f_initials": "Initials"}

    def _unique_name(self, prefix):
        names = {w.field_name for pg in self.doc for w in pg.widgets()}
        n = 1
        while f"{prefix}{n}" in names:
            n += 1
        return f"{prefix}{n}"

    def create_field(self, index, tool, a, b, is_click):
        rect = pymupdf.Rect(a, b).normalize()
        if tool in ("f_check", "f_radio"):
            rect = pymupdf.Rect(a.x - 7, a.y - 7, a.x + 7, a.y + 7) if is_click or rect.width < 6 \
                else rect
        elif is_click or rect.width < 10 or rect.height < 8:
            w0, h0 = {"f_sign": (180, 45), "f_initials": (60, 30)}.get(tool, (160, 20))
            rect = pymupdf.Rect(a.x, a.y, a.x + w0, a.y + h0)
        name = self._unique_name(self.FIELD_PREFIX[tool])
        choices = []
        if tool == "f_radio":
            groups = sorted({w.field_name for pg in self.doc for w in pg.widgets()
                             if w.field_type == pymupdf.PDF_WIDGET_TYPE_RADIOBUTTON})
            label = tr("Group name (options in the same group are mutually exclusive):")
            name, ok = QInputDialog.getItem(self, tr("Option button"), label,
                                            groups + [self._unique_name("Group")],
                                            0 if groups else len(groups), True)
            if not ok or not name.strip():
                return
        elif tool == "f_combo":
            text, ok = dialogs.get_text(self, tr("Dropdown"), tr("Choices, one per line:"))
            if not ok:
                return
            choices = [c.strip() for c in text.splitlines() if c.strip()]
            if not choices:
                return

        def do():
            w = pymupdf.Widget()
            w.field_type = self.FIELD_TYPES[tool]
            w.rect = rect
            w.field_name = name.strip()
            w.border_color = (0.2, 0.35, 0.7)
            w.border_width = 1
            w.fill_color = (0.92, 0.95, 1.0)
            if tool == "f_text":
                w.text_fontsize = 0          # auto size
            if tool == "f_combo":
                w.choice_values = choices
                w.field_value = choices[0]  # (also its default: see form_filled)
            if tool == "f_radio":
                w.field_value = False
            pg = self.doc[index]
            before = {x for x, *_ in pg.annot_xrefs()}
            pg.add_widget(w)
            made = [x for x, *_ in pg.annot_xrefs() if x not in before]
            if tool == "f_combo":
                for x in made:
                    fx = self._field_dict(pg.load_widget(x))
                    self.doc.xref_set_key(fx, "DV", pymupdf.get_pdf_str(choices[0]))
            if pg.rotation:
                # on a turned page the field's text turns with it (upright on screen and on
                # paper), as Acrobat's fields do: the widget's /MK /R
                for x in made:
                    self.doc.xref_set_key(x, "MK/R", str(pg.rotation))
                    pg.load_widget(x).update()
            if tool == "f_radio":
                # (w.xref is not filled in by every PyMuPDF version: find the new widget)
                made = [x for x, *_ in pg.annot_xrefs() if x not in before]
                n = sum(1 for q in self.doc for x in q.widgets(types=[pymupdf.PDF_WIDGET_TYPE_RADIOBUTTON])
                        if x.field_name == name.strip())
                for x in made:
                    self.distinct_on_state(self.doc, x, n)
        self.modify(do, [index])

    @staticmethod
    def distinct_on_state(doc, xref, n):
        """Give an option button PyMuPDF just made its own 'on' appearance state name
        (Choice<n>) and start it off. PyMuPDF names the state the same for every button of a
        group ('Yes'; 2.0 even uses the value given, 'False'), and in 2.0 the buttons are kids
        of one parent field, so turning one on would show the whole group on: PDF readers
        light every kid whose state name matches the group's value."""
        typ, ap = doc.xref_get_key(xref, "AP/N")
        if typ != "dict":
            return
        entries = re.findall(r"/([^\s/\[\]<>()]+)\s+(\d+)\s+0\s+R", ap)
        if not entries:
            return
        new = []
        for key, ref in entries:
            new.append(("Off" if key == "Off" else f"Choice{n}", ref))
        doc.xref_set_key(xref, "AP/N", "<<" + "".join(f"/{k} {r} 0 R" for k, r in new) + ">>")
        doc.xref_set_key(xref, "AS", "/Off")
        if doc.xref_get_key(xref, "V")[0] != "null":
            doc.xref_set_key(xref, "V", "/Off")
        typ, parent = doc.xref_get_key(xref, "Parent")
        if typ == "xref":
            doc.xref_set_key(int(parent.split()[0]), "V", "/Off")

    def select_field_at(self, index, pt):
        page = self.doc[index]
        w = self._widget_at(page, pt)
        if w is None:
            return False
        old = self.selection
        self.selection = (index, w.xref)
        self.selected_model = {"kind": "field", "rect": pymupdf.Rect(w.rect), "props": {},
                               "text": w.field_name}
        for i in {index, old[0] if old else index}:
            self.pages[i].update()
        self.selectionChanged.emit()
        return True

    def _commit_field(self, index, xref, model):
        def do():
            pg = self.doc[index]
            w = pg.load_widget(xref)
            w.rect = model["rect"]
            w.update()
        self.modify(do, [index])
        self.selection = (index, xref)
        self.selected_model = dict(model)
        self.pages[index].update()
        self.selectionChanged.emit()

    def edit_field_properties(self, index, xref):
        page = self.doc[index]
        w = page.load_widget(xref)
        name, ok = QInputDialog.getText(self, tr("Field properties"),
                                        tr("{kind} field name:").format(kind=w.field_type_string),
                                        text=w.field_name)
        if not ok or not name.strip():
            return
        mine = self._field_dict(w)
        taken = {x.field_name for pg in self.doc for x in pg.widgets()
                 if self._field_dict(x) != mine}
        if name.strip() != w.field_name and name.strip() in taken and \
                w.field_type != pymupdf.PDF_WIDGET_TYPE_RADIOBUTTON:
            # (two fields with one name are one field: typing in one would fill both)
            QMessageBox.information(self, tr("Field properties"), tr(
                "Another field is already called {name}: choose another name.").format(
                    name=name.strip()))
            return
        choices = None
        if w.field_type in (pymupdf.PDF_WIDGET_TYPE_COMBOBOX, pymupdf.PDF_WIDGET_TYPE_LISTBOX):
            cur = "\n".join(c[1] if isinstance(c, (list, tuple)) else c
                            for c in (w.choice_values or []))
            text, ok = dialogs.get_text(self, tr("Dropdown"), tr("Choices, one per line:"), cur)
            if ok:
                choices = [c.strip() for c in text.splitlines() if c.strip()]

        def do():
            pg = self.doc[index]
            ww = pg.load_widget(xref)
            fx = self._field_dict(ww)
            if fx != xref:
                # the name lives on the field above the widget (KanzonasPDF's own fields,
                # many Acrobat forms): naming the widget changed nothing
                self.doc.xref_set_key(fx, "T", pymupdf.get_pdf_str(name.strip()))
            else:
                ww.field_name = name.strip()
            if choices:
                ww.choice_values = choices
                if ww.field_value not in choices:
                    ww.field_value = choices[0]
            ww.update()
        self.modify(do, [index])

    def delete_field(self, index, xref):
        self.clear_selection()

        def do():
            pg = self.doc[index]
            pg.delete_widget(pg.load_widget(xref))
        self.modify(do, [index])

    # ---- OCR ----------------------------------------------------------------
    def page_has_text(self, index):
        return bool(self.doc[index].get_text("text").strip())

    def run_ocr(self, pages, accuracy="normal"):
        """Recognize text on the given pages and add an invisible, searchable text layer.
        accuracy: auto | fast | normal | high (see ocr.ACCURACY_DPI)."""
        from . import ocr
        dlg = QProgressDialog(tr("Loading OCR engine..."), tr("Cancel"), 0, len(pages), self)
        dlg.setWindowTitle(tr("Recognize text (OCR)"))
        dlg.setWindowModality(Qt.WindowModal)
        dlg.setMinimumDuration(0)
        dlg.setValue(0)
        results = {}
        pool = ThreadPoolExecutor(max_workers=1)

        def ocr_image(rendering):
            fut = pool.submit(ocr.recognize, rendering, dlg.wasCanceled)
            while not fut.done():       # keep the window responsive while OCR runs
                QApplication.processEvents()
                time.sleep(0.03)
                if dlg.wasCanceled():
                    return None
            return fut.result()

        try:
            for n, i in enumerate(pages):
                dlg.setLabelText(tr("Recognizing text on page {page} ({n} of {total})...").format(
                    page=i + 1, n=n + 1, total=len(pages)))
                dpi = ocr.page_dpi(self.doc[i],
                                   ocr.ACCURACY_DPI.get(accuracy, ocr.ACCURACY_DPI["fast"]))
                best = ocr.Rendering(self.doc[i], dpi=dpi)
                res = ocr_image(best)
                if res is None:
                    break
                sharper = ocr.page_dpi(self.doc[i], ocr.ACCURACY_DPI["high"])
                if accuracy == "auto" and sharper > dpi and ocr.needs_sharper(res, best):
                    dlg.setLabelText(tr("Page {page}: small or unclear text, recognizing "
                                        "again at higher resolution...").format(page=i + 1))
                    dpi = sharper
                    best = ocr.Rendering(self.doc[i], dpi=dpi)
                    res = ocr_image(best)
                    if res is None:
                        break
                turn = 0
                if ocr.upside_down(res):
                    # scanned upside down: read it turned upright too (lines the engine
                    # wasn't sure about read right then), keep the better reading
                    dlg.setLabelText(tr("Page {page}: upside down, recognizing it turned...")
                                     .format(page=i + 1))
                    r = ocr.Rendering(self.doc[i], 180, dpi=dpi)
                    alt = ocr_image(r)
                    if alt is None:
                        break
                    if ocr.score(alt) >= ocr.score(res):
                        best, res, turn = r, alt, 180
                turns = (90, 180, 270) if accuracy == "high" else \
                    ((90, 270) if ocr.mostly_vertical(res) else ())
                if turns:
                    # Sideways or upside-down text: try other turns, keep the best.
                    dlg.setLabelText(tr("Page {page}: checking other orientations...")
                                     .format(page=i + 1))
                    for extra in turns:
                        if extra == turn:
                            continue
                        r = ocr.Rendering(self.doc[i], extra, dpi=dpi)
                        alt = ocr_image(r)
                        if alt is None:
                            break
                        # switch only for a clear win: the engine already reads turned text,
                        # so near-equal scores are noise and the upright layout is better
                        if ocr.score(alt) > 1.25 * ocr.score(res) + 5:
                            best, res = r, alt
                    if dlg.wasCanceled():
                        break
                best.release()              # keep the text, not the full-size image
                results[i] = (res, best)
                dlg.setValue(n + 1)
        except Exception as ex:
            QMessageBox.critical(self, tr("OCR failed"), str(ex))
            return
        finally:
            pool.shutdown(wait=False, cancel_futures=True)
            dlg.close()
        if not results:
            return
        counts = {}

        def do():
            for i, (res, rendering) in results.items():
                counts[i] = ocr.add_text_layer(self.doc[i], res, rendering)
        self.modify(do, list(results))
        self.statusMessage.emit(tr("OCR added {lines} lines of text on {pages} page(s)").format(
            lines=sum(counts.values()), pages=len(results)))

    # ---- page operations --------------------------------------------------
    def rotate_page(self, index, delta):
        page = self.doc[index]
        self.modify(lambda: page.set_rotation((page.rotation + delta) % 360), structural=True)

    def _ask_pages_scope(self, title, question):
        """"this", "all" or None (canceled)."""
        box = QMessageBox(QMessageBox.Question, title, question, parent=self)
        this = box.addButton(tr("This page"), QMessageBox.AcceptRole)
        every = box.addButton(tr("All pages"), QMessageBox.AcceptRole)
        box.addButton(QMessageBox.Cancel)
        box.exec()
        return {this: "this", every: "all"}.get(box.clickedButton())

    def crop_pages(self, index, rect, all_pages=False):
        """Crop page index (or every page) to rect, given in page index's unrotated page
        coordinates. Only the visible area changes (the crop box): Remove crop brings the
        rest back. On other pages the same box is used, measured from their own top left."""
        rect = pymupdf.Rect(rect).normalize()
        targets = range(self.doc.page_count) if all_pages else [index]

        def do():
            for i in targets:
                page = self.doc[i]
                cb = page.cropbox
                box = (rect + (cb.x0, cb.y0, cb.x0, cb.y0)) & page.mediabox
                if box.width >= 2 and box.height >= 2:
                    page.set_cropbox(box)
        self.modify(do, structural=True)
        self.statusMessage.emit(tr("Cropped (Ctrl+Z undoes it; Pages > Remove crop shows the "
                                   "whole page again)"))

    def remove_crop(self, index, all_pages=False):
        targets = range(self.doc.page_count) if all_pages else [index]
        if not any(self.doc[i].cropbox != self.doc[i].mediabox for i in targets):
            self.statusMessage.emit(tr("Not cropped"))
            return

        def do():
            for i in targets:
                page = self.doc[i]
                page.set_cropbox(page.mediabox)
        self.modify(do, structural=True)
        self.statusMessage.emit(tr("Crop removed"))

    def delete_page(self, index):
        if self.doc.page_count <= 1:
            QMessageBox.information(self, tr("Delete page"), tr("A PDF must keep at least one page."))
            return

        def do():
            toc = self.doc.get_toc(False)
            self.doc.delete_page(index)
            self._retarget_bookmarks(toc, {index}, self.doc.page_count + 1)
        self.modify(do, structural=True)

    def move_page(self, index, delta):
        target = index + delta
        if not 0 <= target < self.doc.page_count:
            return
        # move_page(pno, to) inserts *before* `to`; -1 means append at the end.
        to = target if delta < 0 else (target + 1 if target + 1 < self.doc.page_count else -1)
        self.modify(lambda: self.doc.move_page(index, to), structural=True)
        self.goto_page(target)

    def _parent_xref(self, xref):
        typ, val = self.doc.xref_get_key(xref, "Parent")
        return int(val.split()[0]) if typ == "xref" else None

    def _mend_form_fields(self, old_fields):
        """After pages were swapped for copies: drop the originals' fields from the form's
        field list (they no longer sit on any page) and give each copy its original name
        back (copying renames a field that already exists, e.g. "f0" to "f0 [27]").
        A field is either the widget itself or, since PyMuPDF 2.0 for every field and in
        any version for radio groups, a parent dictionary holding the name and the widgets
        as its /Kids: the name lives wherever it is, and a parent leaves the field list only
        when all its kids are gone."""
        cat = self.doc.pdf_catalog()
        typ, arr = self.doc.xref_get_key(cat, "AcroForm/Fields")
        if typ != "array":
            return
        gone = {x for lst in old_fields.values() for x, _n in lst}
        gone_parents = {p for lst in old_fields.values() for x, _n in lst
                        if (p := self._parent_xref(x)) is not None}
        refs = []
        for r in (int(r) for r in re.findall(r"(\d+) 0 R", arr)):
            if r in gone:
                continue
            if r in gone_parents:
                typ, kids = self.doc.xref_get_key(r, "Kids")
                kids = [int(k) for k in re.findall(r"(\d+) 0 R", kids)] if typ == "array" else []
                if all(k in gone for k in kids):
                    continue
            refs.append(r)
        self.doc.xref_set_key(cat, "AcroForm/Fields", "[" + " ".join(f"{r} 0 R" for r in refs) + "]")
        renamed = set()
        for i, lst in old_fields.items():
            names = [n for _x, n in lst]
            for w, name in zip(self.doc[i].widgets(), names):
                if not name or w.field_name == name:
                    continue
                parent = self._parent_xref(w.xref)
                target = w.xref if parent is None else parent
                if target in renamed:
                    continue                    # a group: its name was put back already
                if parent is not None and self.doc.xref_get_key(parent, "T")[0] == "null":
                    continue                    # the name is not on the parent: leave it
                self.doc.xref_set_key(target, "T", pymupdf.get_pdf_str(name))
                renamed.add(target)

    def flatten(self, pages=None, widgets=True):
        """Burn annotations (and form fields unless widgets=False) into the page content
        (pages=None: all pages). Redaction marks not applied yet stay marks: burned in, they
        would look like a redaction with the text still under them. Undo works until the
        file is closed."""
        def do():
            # a page PyMuPDF still holds in a reference cycle (an Annot and its Page) stays
            # loaded through the bake and keeps its old list of markups: free those first
            import gc
            gc.collect()
            held = self._hold_redactions(range(self.doc.page_count) if pages is None
                                         else pages)
            try:
                burn()
            finally:
                self._put_back_redactions(held)

        def burn():
            if pages is None:
                self.doc.bake(annots=True, widgets=widgets)
                return
            # Swapping a page in drops bookmarks and links that point to it: remember them
            toc = self.doc.get_toc(simple=False)
            labels = self.doc.get_page_labels()
            scales = {i: self.doc.xref_get_key(self.doc[i].xref, "KZScale") for i in pages}
            outgoing = {i: self.doc[i].get_links() for i in pages}
            for lst in outgoing.values():
                for ln in lst:
                    ln["keys"] = self._link_keys(ln.get("xref"))
            links = {}
            for pg in self.doc:
                for ln in pg.get_links():
                    if ln.get("kind") == pymupdf.LINK_GOTO and ln.get("page") in pages:
                        links.setdefault(pg.number, []).append(ln)
            # the swapped-in page brings fresh copies of its form fields: remember the old
            # ones so they can leave the form's field list and the copies keep their names
            old_fields = {i: [(w.xref, w.field_name) for w in self.doc[i].widgets()]
                          for i in pages}
            for i in sorted(pages, reverse=True):
                # PyMuPDF flattens whole documents: flatten a one-page copy and swap it in
                tmp = pymupdf.open()
                tmp.insert_pdf(self.doc, from_page=i, to_page=i)
                tmp.bake(annots=True, widgets=widgets)
                self.doc.delete_page(i)
                self.doc.insert_pdf(tmp, start_at=i)
                tmp.close()
            self.doc.set_page_labels(labels)
            self._mend_form_fields(old_fields)
            for i, (typ, value) in scales.items():
                if typ == "string":
                    self.doc.xref_set_key(self.doc[i].xref, "KZScale", pymupdf.get_pdf_str(value))
            for i, lst in outgoing.items():
                pg = self.doc[i]
                for ln in pg.get_links():
                    pg.delete_link(ln)
                for ln in lst:
                    # get_links gives the rectangle as displayed; insert_link wants it
                    # unrotated (they differ on rotated pages)
                    keys = ln["keys"]
                    ln = {k: v for k, v in ln.items() if k not in ("xref", "id", "keys")}
                    ln["from"] = pymupdf.Rect(ln["from"]) * pg.derotation_matrix
                    before = {x for x, _k, *_ in pg.annot_xrefs()}
                    pg.insert_link(ln)
                    # what ties a KanzonasPDF link to its underline and words, and its look
                    for x, k, *_ in pg.annot_xrefs():
                        if x not in before and k == pymupdf.PDF_ANNOT_LINK:
                            for key, value in keys:
                                self.doc.xref_set_key(x, key, value)
            if toc:
                self.doc.set_toc(toc)
            for pno, lst in links.items():
                pg = self.doc[pno]
                have = [pymupdf.Rect(ln["from"]) for ln in pg.get_links()]
                for ln in lst:
                    if pymupdf.Rect(ln["from"]) not in have:
                        pg.insert_link({"kind": pymupdf.LINK_GOTO,
                                        "from": pymupdf.Rect(ln["from"]) * pg.derotation_matrix,
                                        "page": ln["page"], "to": ln.get("to", pymupdf.Point(0, 0))})
        self.clear_selection()
        self.modify(do, structural=True)

    LINK_KEYS = ("KZGroup", "KZLook", "KZUnder", "KZText", "KZOn", "BS", "C", "Border")

    def _link_keys(self, xref):
        """[(key, PDF source)] of a link's look and KanzonasPDF ties (see links.py)."""
        return [kv for kv in self._obj_keys(xref) if kv[0] in self.LINK_KEYS] if xref else []

    def _obj_keys(self, xref, skip=()):
        """[(key, PDF source)] of an object's dictionary, to copy onto another one."""
        out = []
        for key in self.doc.xref_get_keys(xref):
            if key in skip:
                continue
            typ, val = self.doc.xref_get_key(xref, key)
            if typ == "string":
                out.append((key, pymupdf.get_pdf_str(val)))
            elif typ not in ("null", ""):
                out.append((key, val))
        return out

    def _hold_redactions(self, pages):
        """Take the redaction marks off these pages for a moment, remembering each one's box
        and dictionary. {page index: [(rect, [(key, PDF source)])]}."""
        held = {}
        for i in pages:
            page = self.doc[i]
            # (page.annots(), not each_annot: that leaves the page in a reference cycle, kept
            # loaded through the bake, so its list of markups would go stale)
            marks = list(page.annots([pymupdf.PDF_ANNOT_REDACT]))
            if not marks:
                continue
            held[i] = [(pymupdf.Rect(a.rect), self._obj_keys(a.xref, self.MARK_SKIP))
                       for a in marks]
            for a in marks:
                page.delete_annot(a)
        return held

    def _put_back_redactions(self, held):
        """The marks _hold_redactions took, as they were (after Flatten current page: on the
        page's new copy)."""
        for i, marks in held.items():
            page = self.doc[i]
            for rect, keys in marks:
                a = page.add_redact_annot(rect)
                for key, value in keys:
                    self.doc.xref_set_key(a.xref, key, value)

    MARK_SKIP = ("Type", "Subtype", "P", "Parent", "Popup", "IRT")

    def reorder_pages(self, order, show=None):
        """Put the pages in this order (old page indices) as one undo step, then show old
        page `show` where it landed. False when nothing changed (or the edit was refused)."""
        n = self.doc.page_count
        order = list(order)
        if order == list(range(n)) or sorted(order) != list(range(n)):
            return False

        def do():
            now = list(range(n))
            for k, src in enumerate(order):
                i = now.index(src)
                if i != k:
                    self.doc.move_page(i, k)        # (inserts before page k)
                    now.insert(k, now.pop(i))
        if not self.modify(do, structural=True):
            return False
        if show is not None:
            self.goto_page(order.index(show))
        return True

    def insert_pdf(self, path, at):
        self.insert_files([path], at)

    def insert_files(self, paths, at):
        """Insert PDFs and pictures, in order, before page `at` (-1: at the end), as one undo
        step. Each picture becomes a page the size of the page it follows (the first page
        when inserted at the start), turned to suit the picture."""
        from .combine import insert_files
        n = self.doc.page_count
        ref = self.page_rects[min(max(at - 1, 0), n - 1) if at != -1 else n - 1]
        self.modify(lambda: insert_files(self.doc, paths, n if at == -1 else at,
                                         (ref.width, ref.height)), structural=True)

    def insert_blank(self, at):
        r = self.page_rects[min(at, len(self.page_rects) - 1)]
        self.modify(lambda: self.doc.new_page(at, width=r.width, height=r.height),
                    structural=True)

    def extract_pages(self, first, last, path):
        if not self.allowed(pymupdf.PDF_PERM_COPY):
            raise PermissionError(tr("Extracting pages is not allowed."))
        out = pymupdf.open()
        out.insert_pdf(self.doc, from_page=first, to_page=last)
        out.save(path, garbage=3, deflate=True)
        out.close()

    # ---- search -----------------------------------------------------------
    SEARCH_SLICE = 0.03         # seconds of searching per turn of the event loop

    def find(self, text, backwards=False):
        """Find text: go to the next (previous) match. A new search starts at the current
        page and runs in short slices, so the window stays responsive on long documents: it
        jumps to the first match as soon as it's found and keeps counting the rest. Returns
        the number of matches found so far, or -1 while still searching with none yet."""
        if not text:
            self.clear_search()
            return 0
        if text != self._search_text:
            self._start_search(text, backwards)
            self._search_step()                     # small documents finish right here
            if self._search_cur is None:
                return -1 if self._search_todo else 0
            return self._search_count()
        if not self.search_hits:
            return -1 if self._search_todo else 0
        self._show_hit(self._step_hit(self._search_cur, backwards))
        return self._search_count()

    def _start_search(self, text, backwards):
        from collections import deque
        self._search_text = text
        self.search_hits = {}
        self._search_list = []
        self._search_cur = None
        self._search_back = backwards
        n, cur = self.doc.page_count, self.current_page()
        pages = list(range(cur, n)) + list(range(0, cur)) if not backwards else \
            list(range(cur, -1, -1)) + list(range(n - 1, cur, -1))
        self._search_todo = deque(pages)
        self._search_gen = getattr(self, "_search_gen", 0) + 1
        for w in self.pages:
            w.update()

    def _search_step(self, gen=None):
        """Search pages for SEARCH_SLICE seconds, then let the window breathe."""
        if gen is not None and gen != self._search_gen:
            return                                  # a newer search (or an edit) took over
        text = self._search_text
        if text is None or not self._search_todo:
            return
        start = time.monotonic()
        first = True
        while self._search_todo:                    # at least one page per slice
            if not first and time.monotonic() - start >= self.SEARCH_SLICE:
                break
            first = False
            i = self._search_todo.popleft()
            if i >= self.doc.page_count:
                continue
            hits = self.doc[i].search_for(text)
            if hits:
                self.search_hits[i] = hits
                self.pages[i].update()
                if self._search_cur is None:        # first match in the search direction
                    self._show_hit((i, len(hits) - 1 if self._search_back else 0))
        if self._search_todo:
            done = self.doc.page_count - len(self._search_todo)
            self.statusMessage.emit(self._search_status() + " " +
                                    tr("(searching, {done} of {total} pages)").format(
                                        done=done, total=self.doc.page_count))
            gen = self._search_gen
            QTimer.singleShot(0, lambda: self._search_step(gen))
        elif self._search_cur is None:
            self.statusMessage.emit(tr("No matches"))
        else:
            self.statusMessage.emit(self._search_status())
        self.searchChanged.emit(*self.search_position())

    def _search_count(self):
        return sum(len(h) for h in self.search_hits.values())

    def _step_hit(self, hit, backwards=False):
        """The match after (before) hit, in page order, wrapping around."""
        import bisect
        pages = sorted(self.search_hits)
        if hit is None or hit[0] not in self.search_hits:
            i = pages[-1] if backwards else pages[0]
            return (i, len(self.search_hits[i]) - 1 if backwards else 0)
        i, k = hit
        if not backwards and k + 1 < len(self.search_hits[i]):
            return (i, k + 1)
        if backwards and k > 0:
            return (i, k - 1)
        n = bisect.bisect_left(pages, i)
        i = pages[(n + (-1 if backwards else 1)) % len(pages)]
        return (i, len(self.search_hits[i]) - 1 if backwards else 0)

    def search_position(self):
        """(number of the match shown, 1-based, or 0; matches found so far; whether the
        search is still running) for the Find box's count."""
        if self._search_text is None:
            return 0, 0, False
        if self._search_cur is None:
            return 0, 0, bool(self._search_todo)
        i, k = self._search_cur
        n = sum(len(h) for p, h in self.search_hits.items() if p < i) + k + 1
        return n, self._search_count(), bool(self._search_todo)

    def _search_status(self):
        n, total, searching = self.search_position()
        if not n:
            return tr("Searching...")
        return tr("Match {n} of {total}").format(n=n, total=total) + ("+" if searching else "")

    def _show_hit(self, hit):
        old = self._search_cur
        self._search_cur = hit
        i, k = hit
        w = self.pages[i]
        if self.fit_mode == "page":
            # whole-page view: bring the match's page in front, centered, not just the match
            self.show_whole_page(i)
        else:
            r = w.to_screen(self.search_hits[i][k])
            top = w.y() + r.y()
            vbar = self.verticalScrollBar()
            if not (vbar.value() + 40 < top < vbar.value() + self.viewport().height() - 40):
                vbar.setValue(int(top - self.viewport().height() / 3))
            hbar = self.horizontalScrollBar()
            left = w.x() + r.x()
            if not (hbar.value() < left < hbar.value() + self.viewport().width() - 40):
                hbar.setValue(int(left - 40))
        for p in {i, old[0] if old else i}:
            if 0 <= p < len(self.pages):
                self.pages[p].update()
        self.statusMessage.emit(self._search_status())
        self.searchChanged.emit(*self.search_position())

    def current_hit(self):
        return self._search_cur

    def search_text(self):
        """The text being searched for, or None when there's no search."""
        return self._search_text

    def clear_search(self):
        self.search_hits = {}
        self._search_list = []
        self._search_text = None
        self._search_cur = None
        self._search_todo = None
        self._search_gen = getattr(self, "_search_gen", 0) + 1     # stops a running search
        self._search_pos = -1
        for w in self.pages:
            w.update()
        self.searchChanged.emit(0, 0, False)

    # ---- saving -----------------------------------------------------------
    def _ask_original_passwords(self):
        """The original permissions (owner) and open passwords, asked for when unknown.
        Raises PermissionError (and nothing is written) if they can't be given."""
        if not self._orig_enc.get("owner_pw"):
            pw, ok = QInputDialog.getText(self, tr("Permissions password required"),
                                          tr("Enter the owner password to preserve this file's "
                                             "protection:"),
                                          QLineEdit.Password)
            original = pymupdf.open(stream=self._orig_data, filetype="pdf")
            try:
                if not ok or not original.authenticate(pw) & 4:
                    raise PermissionError(tr("Saving changes requires the original owner password. "
                                                         "The file was not overwritten."))
            finally:
                original.close()
            self._orig_enc["owner_pw"] = pw
        if self._orig_enc.get("needs_pass") and not self._orig_enc.get("user_pw"):
            pw, ok = QInputDialog.getText(self, tr("Open password required"),
                                          tr("Enter the original open password, or explicitly "
                                             "choose new security settings:"),
                                          QLineEdit.Password)
            original = pymupdf.open(stream=self._orig_data, filetype="pdf")
            try:
                if not ok or not original.authenticate(pw) & 2:
                    raise PermissionError(tr("The original open password is required to preserve "
                                                         "encryption. The file was not overwritten."))
            finally:
                original.close()
            self._orig_enc["user_pw"] = pw

    def save(self, path=None):
        if path is None and self.untitled:
            raise RuntimeError(tr("This PDF hasn't been saved yet: use Save As to choose where."))
        self.commit_pending()
        path = os.path.abspath(path or self.path)
        tmp = path + ".kanzonas-tmp"
        if self._fonts_added:
            # Text edits may embed whole system fonts; keep only the glyphs actually used.
            try:
                self.doc.subset_fonts()
            except Exception:
                pass
            self._fonts_added = False
        sec = self.security
        try:
            self._write_file(tmp, sec)
            os.replace(tmp, path)
            self.disk_stamp = disk_stamp(path)
        except BaseException:
            # e.g. the file is locked by another program: don't leave the copy next to it
            try:
                os.remove(tmp)
            except OSError:
                pass
            raise
        self.path = path
        self.untitled = False
        if self.dirty or sec is not None:
            self._orig_data = None          # the file on disk is our rewrite now
        self.dirty = False
        self.documentChanged.emit()

    def _write_file(self, tmp, sec):
        """Write the document to tmp the way save needs it (see save)."""
        if not self.dirty and sec is None and self._orig_data is not None:
            # nothing changed: write the original bytes, so digital signatures stay valid
            # and protection stays exactly as it was
            with open(tmp, "wb") as f:
                f.write(self._orig_data)
        elif sec is None and self._orig_enc is not None and \
                (self.doc.metadata or {}).get("encryption"):
            # edited a protected file: keep its own encryption, open and permissions passwords
            # and permissions exactly as they were (no password needed, nothing replaced)
            self.doc.save(tmp, garbage=1, deflate=True, encryption=pymupdf.PDF_ENCRYPT_KEEP)
        elif sec is None and self._orig_enc is not None:
            # the in-memory copy lost its encryption: protect it again with the original
            # passwords, which must then be known (never invented: that would lock the owner
            # out)
            self._ask_original_passwords()
            enc = self._orig_enc
            owner = enc["owner_pw"]
            user = enc.get("user_pw") or (owner if enc.get("needs_pass") else "")
            self.doc.save(tmp, garbage=1, deflate=True, encryption=pymupdf.PDF_ENCRYPT_AES_256,
                          owner_pw=owner, user_pw=user, permissions=enc.get("perms", -1))
        elif sec is None:
            self.doc.save(tmp, garbage=1, deflate=True)
        elif not sec.get("open_pw") and not sec.get("owner_pw"):
            self.doc.save(tmp, garbage=1, deflate=True, encryption=pymupdf.PDF_ENCRYPT_NONE)
        else:
            # AES-256. Without an open password anyone can open it; the permissions password
            # (the owner password) is what's needed to change the restrictions.
            owner = sec.get("owner_pw") or sec.get("open_pw")
            self.doc.save(tmp, garbage=1, deflate=True, encryption=pymupdf.PDF_ENCRYPT_AES_256,
                          owner_pw=owner, user_pw=sec.get("open_pw") or "",
                          permissions=sec.get("perms", -1) if sec.get("owner_pw") else -1)

    def close_doc(self):
        self._undo, self._redo = [], []         # free the history (and the shared budget)
        self._inline = None
        self._search_gen += 1                   # a Find still running stops here
        self._search_todo = None
        self.doc.close()
