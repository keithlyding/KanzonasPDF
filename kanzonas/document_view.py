"""Scrolling view of one open document, plus every editing operation on it."""

import json
import os
import secrets
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor

import pymupdf
from PySide6.QtCore import Qt, Signal, QTimer, QObject, QEvent
from PySide6.QtCore import QRectF
from PySide6.QtGui import (QColor, QGuiApplication, QPixmap, QPainter, QPen, QCursor)
from PySide6.QtWidgets import (QScrollArea, QWidget, QVBoxLayout, QInputDialog,
                               QMessageBox, QLineEdit, QProgressDialog, QApplication,
                               QMenu, QPlainTextEdit, QHBoxLayout, QLabel, QPushButton)

from . import annotations, dialogs, signatures, text_edit
from .inline_editor import InlineEditor
from .page_widget import PageWidget

PAGE_GAP = 12
MIN_ZOOM, MAX_ZOOM = 0.1, 8.0
UNDO_LIMIT = 30


_ERASER_CURSOR = None


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


class DocumentView(QScrollArea):
    _orig_data = None               # original file bytes (signed / protected files only)
    _orig_enc = None                # original protection, to keep it when saving edits
    pageChanged = Signal(int)
    documentChanged = Signal()      # content edited (thumbnails / title need refresh)
    structureChanged = Signal()     # pages added / removed / reordered / rotated
    zoomChanged = Signal(float)
    statusMessage = Signal(str)
    selectionChanged = Signal()
    signedDocument = Signal()
    selectToolRequested = Signal()
    calibrateRequested = Signal(int, float)    # page index, drawn length in points
    scaleChanged = Signal()
    layersChanged = Signal()
    requestSignature = Signal(int, int)      # page index, signature field xref

    def __init__(self, path, parent=None):
        super().__init__(parent)
        self.path = os.path.abspath(path)
        # Load from memory so the file is not locked on Windows and can be overwritten on save.
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
            pw, ok = QInputDialog.getText(self, "Password required",
                                          os.path.basename(path) + " is protected:",
                                          QLineEdit.Password)
            rc = self.doc.authenticate(pw) if ok else 0
            if not rc:
                raise ValueError("Wrong or missing password")
            if rc & 2:
                self._orig_enc["user_pw"] = pw
            if rc & 4:
                self._orig_enc["owner_pw"] = pw
        if self._orig_enc is not None:
            self._orig_enc["perms"] = self.doc.permissions
        try:
            signed = self.doc.get_sigflags() >= 1
        except Exception:
            signed = False
        if self._orig_enc is None and not signed:
            self._orig_data = None          # plain file: no need to keep a second copy
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
        container.adjustSize()
        self.verticalScrollBar().setValue(keep)

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
        # Free rendered bitmaps for pages far from the viewport to keep memory low.
        lo, hi = max(0, cur - 4), cur + 6
        for i, w in enumerate(self.pages):
            if (i < lo or i > hi) and w._pix is not None:
                w.drop_cache()

    def current_page(self):
        if not getattr(self, "pages", None):
            return 0
        mid = self.verticalScrollBar().value() + self.viewport().height() // 3
        for i, w in enumerate(self.pages):
            if w.y() + w.height() + PAGE_GAP // 2 >= mid:
                return i
        return len(self.pages) - 1

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

    @classmethod
    def mirror(cls, other):
        """A second, read-only view onto another view's document (split view)."""
        self = cls.__new__(cls)
        QScrollArea.__init__(self)
        self.path = other.path
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
    def set_zoom(self, z):
        z = max(MIN_ZOOM, min(MAX_ZOOM, z))
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
        self.set_zoom(avail / widest)

    def fit_page(self):
        r = self.page_rects[self.current_page()]
        avail_w = self.viewport().width() - 2 * PAGE_GAP
        avail_h = self.viewport().height() - 2 * PAGE_GAP
        page = self.current_page()
        self.set_zoom(min(avail_w / r.width, avail_h / r.height))
        self.show_whole_page(page)

    highlight_fields = True        # shade fillable form fields (View / Forms menu)
    show_markups = True            # Review > Show markups (off: the page as if unmarked)

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
        for an in page.annots():
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
        self.modify(do, [index])

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
        self.modify(do, list(locked))
        return sum(len(x) for x in locked.values())

    # ---- review: walk through, delete, flatten comments ---------------------------------------
    def review_items(self):
        """[(page, xref)] of every markup in reading order (page, then top to bottom)."""
        out = []
        for i in range(self.doc.page_count):
            pg = self.doc[i]
            items = []
            for an in pg.annots():
                if an.type[0] == pymupdf.PDF_ANNOT_POPUP or (an.flags or 0) & (
                        pymupdf.PDF_ANNOT_IS_LOCKED | pymupdf.PDF_ANNOT_IS_HIDDEN):
                    continue
                r = an.rect * pg.rotation_matrix
                items.append((round(r.y0 / 6), r.x0, an.xref))
            out += [(i, x) for _y, _x, x in sorted(items)]
        return out

    def goto_markup(self, step):
        """Select the next (step=1) or previous (step=-1) markup, wrapping around."""
        if not self.show_markups:
            self.statusMessage.emit("Markups are hidden (Review > Show markups).")
            return None
        items = self.review_items()
        if not items:
            self.statusMessage.emit("No comments or markups in this document.")
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
        self.statusMessage.emit(f"Markup {k + 1} of {len(items)} (page {index + 1})")
        return index, xref

    def markup_authors(self):
        names = set()
        for i in range(self.doc.page_count):
            for an in self.doc[i].annots():
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
        self.modify(do, list(doomed))
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
        """Snap a PDF point: to the nearest object point within SNAP_PX, else to the grid.
        Returns (point, kind) with kind 'object' or 'grid', or None when nothing applies."""
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
        if self.snap_grid and self.grid_spacing > 0:
            return snapping.grid_snap(page, pt, self.grid_spacing), "grid"
        return None

    # CAD-style mouse (View menu): the wheel zooms around the cursor, like AutoCAD.
    # Holding the wheel (middle button) down and dragging pans in either mode.
    cad_mouse = False
    page_wheel = False          # one wheel step = one page when the page fits the window
    open_view = "width"         # zoom for newly opened files: width, page, actual, last
    reopen_page = True          # reopen files at the page they were left on

    def wheelEvent(self, e):
        dy = e.angleDelta().y()
        mods = e.modifiers()
        if self.cad_mouse and mods & (Qt.ControlModifier | Qt.ShiftModifier):
            # CAD mouse (Bluebeam-style): the wheel zooms, Ctrl+wheel scrolls up/down,
            # Shift+wheel scrolls left/right
            step = dy or e.angleDelta().x()
            bar = self.horizontalScrollBar() if mods & Qt.ShiftModifier else self.verticalScrollBar()
            bar.setValue(bar.value() - step)
            e.accept()
        elif self.cad_mouse:
            if dy:
                vp = self.viewport().mapFromGlobal(QCursor.pos())
                self.zoom_at(self.zoom * 1.15 ** (dy / 120.0), vp)
            e.accept()
        elif e.modifiers() & Qt.ControlModifier:
            if dy > 0:
                self.zoom_in()
            elif dy < 0:
                self.zoom_out()
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
        self.tool = tool
        self.clear_selection()
        self.clear_object_selection()
        self.clear_text_selection()
        self._tool_cursor()

    def _tool_cursor(self):
        tool = self.tool
        if tool == "eraser":
            self.viewport().setCursor(eraser_cursor())
            return
        text_cursor = ("select", "edittext", "highlight", "underline", "strikeout", "comment",
                       "redact")
        cursors = {"hand": Qt.OpenHandCursor, **{t: Qt.IBeamCursor for t in text_cursor}}
        self.viewport().setCursor(cursors.get(tool, Qt.CrossCursor))

    # ---- undo / modify ----------------------------------------------------
    def _snapshot(self):
        return self.doc.tobytes()

    def _restore(self, data):
        self._clear_caches()
        self.selection = None
        self.selected_model = None
        self.extra = []
        page = self.current_page()
        self.doc.close()
        self.doc = pymupdf.open(stream=data, filetype="pdf")
        self.search_hits.clear()
        self._search_list = []
        self._search_text = None
        self._build_pages()
        self.goto_page(min(page, self.doc.page_count - 1))
        self.dirty = True
        self.structureChanged.emit()
        self.selectionChanged.emit()

    def modify(self, fn, pages=None, structural=False):
        """Run an edit with an undo snapshot. pages = indices to repaint."""
        if self.read_only:
            if getattr(self, "sig_results", None):
                QMessageBox.information(self, "Digitally signed document",
                                        "This PDF is digitally signed, so it's read-only to keep "
                                        "the signature valid. Click \u201cEdit anyway\u201d in the "
                                        "banner if you really need to change it.")
            else:
                QMessageBox.information(self, "Protected document",
                                        "This PDF is protected against changes. Use Protect > Unlock "
                                        "with password if you have its permissions password.")
            return
        # a burst of arrow-key nudges is one undo step: later presses reuse the first snapshot
        merge = getattr(self, "_merge_edit", False) and bool(self._undo)
        snap = None if merge else self._snapshot()
        self._clear_caches()
        try:
            fn()
        except Exception as ex:
            QMessageBox.warning(self, "Edit failed", str(ex))
            self._restore(snap if snap is not None else self._undo.pop())
            return
        if snap is not None:
            self._undo.append(snap)
        del self._undo[:-UNDO_LIMIT]
        self._redo.clear()
        self.dirty = True
        # any edit can change the page text: the next Find searches again
        self._search_text = None
        if structural:
            page = self.current_page()
            self.search_hits.clear()
            self._search_list = []
            self._search_text = None
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

    def can_undo(self):
        return bool(self._undo)

    def can_redo(self):
        return bool(self._redo)

    def undo(self):
        if self._undo:
            self._redo.append(self._snapshot())
            self._restore(self._undo.pop())

    def redo(self):
        if self._redo:
            self._undo.append(self._snapshot())
            self._restore(self._redo.pop())

    # ---- caches (cleared on every change) ------------------------------------
    def _clear_caches(self):
        self._dlists = {}              # page index -> parsed drawing (DisplayList)
        self._tiles = OrderedDict()    # (page, scale, tx, ty) -> rendered tile, LRU
        self._line_cache = {}
        self._word_cache = {}
        self._card_cache = {}
        self.text_sel = None           # (page index, selected character units) for copy / cut
        self._snap_markups = {}        # page index -> snapping.PointIndex of markup points
        self._obj_cache = {}           # page index -> page_objects.Objects (Edit objects)
        self.obj_sel = None            # (page index, [objects]) selected with Edit objects
        # the drawing's own line work rarely changes: re-check it lazily instead of dropping it
        if not hasattr(self, "_snap_content"):
            self._snap_content = {}    # page index -> (content key, PointIndex)
        self._snap_recheck = set(self._snap_content)

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
        old = self.text_sel
        self.text_sel = (index, list(words)) if words else None
        for i in {index, old[0] if old else index}:
            if 0 <= i < len(self.pages):
                self.pages[i].update()

    def clear_text_selection(self):
        if self.text_sel is not None:
            self.set_text_selection(self.text_sel[0], [])

    def select_all_text(self):
        index = self.current_page()
        words = self._words(index)
        self.set_text_selection(index, words)
        return len(words)

    def selected_text(self):
        return self._words_text(self.text_sel[1]) if self.text_sel else ""

    def copy(self):
        """Copy the selected text, or the selected markups. Returns what was copied."""
        from . import clip
        if self.text_sel:
            QGuiApplication.clipboard().setText(self.selected_text())
            return "text"
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
        index = self.selection[0]
        page = self.doc[index]
        m_ = page.derotation_matrix
        d = pymupdf.Point(offset, offset) * m_ - pymupdf.Point(0, 0) * m_
        made = []

        def do():
            pg = self.doc[index]
            for m in models:
                made.append(annotations.write(pg, annotations.moved(m, d)).xref)
        self.modify(do, [index])
        if made:
            self._set_selection(index, made)
        return len(made)

    def cut(self):
        """Cut the selected text (removed from the page) or the selected markups."""
        what = self.copy()
        if what == "text":
            index, words = self.text_sel
            rects = []
            for w in words:
                r = pymupdf.Rect(w[:4])
                padx, pady = r.width * 0.08, r.height * 0.15
                rects.append(pymupdf.Rect(r.x0 + padx, r.y0 + pady, r.x1 - padx, r.y1 - pady))

            def do():
                pg = self.doc[index]
                for r in rects:
                    pg.add_redact_annot(r, fill=False)
                pg.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE,
                                    graphics=pymupdf.PDF_REDACT_LINE_ART_NONE,
                                    text=pymupdf.PDF_REDACT_TEXT_REMOVE)
            self.clear_text_selection()
            self.modify(do, [index])
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
                     "image_bytes": payload["png"], "text": "Captured area"}
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
                                     "text": "Pasted image"}, select=True)
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
        out = pymupdf.open()
        for i in sorted(indices):
            out.insert_pdf(self.doc, from_page=i, to_page=i)
        data = out.tobytes(garbage=3, deflate=True)
        out.close()
        return data

    def paste_pages(self, data, at):
        """Insert the PDF pages in data before page index at (== count: at the end)."""
        at = max(0, min(at, self.doc.page_count))
        n = {}

        def do():
            with pymupdf.open(stream=data, filetype="pdf") as other:
                n["n"] = other.page_count
                self.doc.insert_pdf(other, start_at=at)
        self.modify(do, structural=True)
        self.goto_page(at)
        return "pages"

    def delete_pages(self, indices):
        indices = sorted(set(indices), reverse=True)
        if len(indices) >= self.doc.page_count:
            QMessageBox.information(self, "Delete pages", "A PDF must keep at least one page.")
            return False

        def do():
            for i in indices:
                self.doc.delete_page(i)
        self.modify(do, structural=True)
        return True

    def duplicate_pages(self, indices):
        """Copies of these pages right after the last of them."""
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
        self.modify(do, [index])
        if select and "xref" in made:
            self.select_xref(index, made["xref"])
        return made.get("xref")

    def apply_text_tool(self, index, tool, a, b):
        mode, words = self.text_selection(index, a, b)
        if tool == "redact":
            rects = self.line_rects(words) if mode == "text" else [pymupdf.Rect(a, b).normalize()]
            rects = [r for r in rects if r.width > 1 and r.height > 1]
            if rects:
                self.mark_redactions(index, rects)
            return
        if not words:
            if tool != "select":
                self.statusMessage.emit("No text there to mark up")
            return
        text = self._words_text(words)
        if tool == "select":
            # keep the selection: Ctrl+C copies, Ctrl+X cuts, Ctrl+V pastes
            self.set_text_selection(index, words)
            self.statusMessage.emit(f"{len(text)} characters selected: Ctrl+C to copy, "
                                    "Ctrl+X to cut")
            return
        self._markup_words(index, tool, words, text)

    def markup_text_selection(self, tool):
        """Right-click menu: highlight / underline / strike out / comment on / redact the
        selected text."""
        if not self.text_sel:
            return
        index, words = self.text_sel
        if tool == "redact":
            rects = [r for r in self.line_rects(words) if r.width > 1 and r.height > 1]
            if rects:
                self.mark_redactions(index, rects)
        else:
            self._markup_words(index, tool, words, self._words_text(words))
        self.clear_text_selection()

    def _markup_words(self, index, tool, words, text):
        model = {"kind": tool, "props": self.tool_props(tool),
                 "quads": [r.quad for r in self.line_rects(words)],
                 "text": text if tool != "comment" else ""}
        if tool == "comment":
            note, ok = dialogs.get_text(self, "Comment", f"Comment on “{text[:60]}”:")
            if not ok:
                return
            model["text"] = note
        self._create(index, model)

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
            self.statusMessage.emit(f"Erased {len(xrefs)} annotation(s)")
            return
        props = self.tool_props(tool)
        if tool in ("erasecontent", "capture"):
            if is_click or rect.width < 2 or rect.height < 2:
                self.statusMessage.emit("Drag a box around the area")
                return
            if tool == "capture":
                self.capture_area(index, rect)
            else:
                self.erase_content(index, rect)
            return
        if tool == "textbox":
            if is_click or rect.width < 20 or rect.height < 10:
                rect = pymupdf.Rect(a.x, a.y, a.x + 200, a.y + 40)
            text, ok = dialogs.get_text(self, "Text box", "Text:")
            if not ok or not text.strip():
                return
            self._create(index, {"kind": "textbox", "rect": rect, "text": text, "props": props})
            return
        if tool == "image":
            self.place_image(index, a, b, is_click)
            return
        if tool == "placeholder":
            props = self.tool_props("placeholder")
            if is_click or rect.width < 12 or rect.height < 8:
                w, h = (160, 40) if props.get("for") == "signature" else (70, 30)
                rect = pymupdf.Rect(a.x, a.y, a.x + w, a.y + h)
            self._create(index, {"kind": "placeholder", "props": props, "rect": rect})
            return
        if tool == "m_calibrate":
            if not is_click and abs(b - a) > 2:
                self.calibrateRequested.emit(index, abs(b - a))
            return
        if tool == "m_length":
            if not is_click:
                self._create(index, {"kind": "m_length", "props": props, "points": [a, b],
                                     "rect": pymupdf.Rect()})
            return
        if tool == "callout":
            text, ok = dialogs.get_text(self, "Callout", "Text:")
            if not ok or not text.strip():
                return
            box = pymupdf.Rect(b.x, b.y, b.x + 160, b.y + 40)
            if b.x < a.x:                       # box to the left of the target
                box = pymupdf.Rect(b.x - 160, b.y, b.x, b.y + 40)
            self._create(index, {"kind": "callout", "props": props, "rect": box,
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
            return f"{abs(pts[-1] - pts[0]) / 72:.2f} in on paper"
        return measure.measure_text(kind, pts, self.doc[index])

    def place_count(self, index, pt):
        group = self.tool_props("m_count").get("group") or "Count"
        n = 0
        for i in range(self.doc.page_count):
            pg = self.doc[i]
            for a in pg.annots():
                m = annotations.read(a) if a.type[0] == pymupdf.PDF_ANNOT_CIRCLE else None
                if m and m["kind"] == "m_count" and m["props"].get("group") == group:
                    n = max(n, m.get("n", 0))
        self._create(index, {"kind": "m_count", "props": self.tool_props("m_count"),
                             "points": [pt], "rect": pymupdf.Rect(), "n": n + 1})

    def page_scale_text(self, index):
        from . import measure
        return measure.describe(self.doc[index])

    def set_page_scale(self, pages, m_per_pt, unit, label):
        """Apply a scale and re-measure existing measurements on those pages."""
        from . import measure

        def do():
            for i in pages:
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
        self.modify(do, list(pages))
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
    IMAGE_FILTER = "Images (*.png *.jpg *.jpeg *.bmp *.gif *.tif *.tiff)"
    RISKY = (".exe", ".bat", ".cmd", ".com", ".msi", ".js", ".jse", ".vbs", ".vbe", ".ps1",
             ".scr", ".lnk", ".hta", ".wsf", ".jar", ".reg", ".pif", ".cpl")

    def place_image(self, index, a, b, is_click):
        """Image tool: pick a picture and fit it in the dragged box (or natural size at the
        click), keeping its proportions."""
        path = dialogs.open_file(self, "Insert image", self.IMAGE_FILTER)
        if not path:
            return
        with open(path, "rb") as f:
            data = f.read()
        try:
            pm = pymupdf.Pixmap(data)
            iw, ih = pm.width, pm.height
            dpi_x, dpi_y = pm.xres or 150, pm.yres or 150
        except Exception:
            QMessageBox.warning(self, "Insert image", "That file isn't an image this app can read.")
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
        model = {"kind": "image", "props": self.tool_props("image"), "rect": box * to_pdf,
                 "image_bytes": data, "text": os.path.basename(path)}
        self._create(index, model, select=True)

    def attach_file(self, index, pt):
        """Attach file tool: embed any file in the PDF, shown as an icon at pt."""
        path = dialogs.open_file(self, "Attach a file")
        if not path:
            return
        size = os.path.getsize(path)
        if size > 50 * 1024 * 1024:
            if QMessageBox.question(self, "Attach file",
                                    f"{os.path.basename(path)} is {size / 1e6:.0f} MB. The PDF will "
                                    "grow by about that much, which may be too large to email. "
                                    "Attach it anyway?") != QMessageBox.Yes:
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
            for an in page.annots():
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

    def open_attachment(self, page_index, key, name):
        """Open an attached file with the program Windows uses for it."""
        import tempfile
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        if os.path.splitext(name)[1].lower() in self.RISKY:
            if QMessageBox.warning(self, "Open attached file",
                                   f"{name} is a program or script. Opening files from untrusted "
                                   "PDFs can harm your computer. Open it anyway?",
                                   QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
                return None
        folder = tempfile.mkdtemp(prefix="kzattach")
        path = os.path.join(folder, os.path.basename(name) or "attachment")
        with open(path, "wb") as f:
            f.write(self.attachment_data(page_index, key))
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        return path

    def save_attachment(self, page_index, key, name, path=None):
        path = path or dialogs.save_file(self, "Save attached file", name)
        if path:
            with open(path, "wb") as f:
                f.write(self.attachment_data(page_index, key))
        return path

    def delete_attachment(self, page_index, key):
        if page_index is None:
            self.modify(lambda: self.doc.embfile_del(key), [])
        else:
            page = self.doc[page_index]
            self.clear_selection()
            self.modify(lambda: page.delete_annot(page.load_annot(key)), [page_index])

    def place_stamp(self, index, pt):
        self._create(index, {"kind": "stamp", "props": self.tool_props("stamp"),
                             "rect": self.stamp_rect(index, pt)})

    def apply_ink(self, index, pts):
        self._create(index, {"kind": "ink", "props": self.tool_props("ink"),
                             "strokes": [pts], "rect": pymupdf.Rect()})

    def apply_point_tool(self, index, tool, pt):
        page = self.doc[index]
        if tool == "attach":
            self.attach_file(index, pt)
            return
        if tool == "note":
            text, ok = dialogs.get_text(self, "Sticky note", "Note:")
            if not ok or not text.strip():
                return
            self._create(index, {"kind": "note", "props": self.tool_props("note"),
                                 "rect": pymupdf.Rect(pt, pt + (20, 20)), "text": text})
        elif tool == "eraser":
            target = self._annot_at(page, pt)
            if target is None:
                return
            xref = target.xref
            self.clear_selection()
            self.modify(lambda: page.delete_annot(page.load_annot(xref)), [index])

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
        return annot.rect.contains(pt)

    @classmethod
    def _annot_at(cls, page, pt):
        """Smallest annotation actually under the point (so big shapes don't swallow clicks)."""
        hits = [an for an in page.annots() if cls._annot_hit(an, pt)]
        if not hits:
            return None
        return min(hits, key=lambda an: an.rect.get_area())

    def annot_at(self, index, pt):
        """xref of the annotation under pt, or None. (Returns an id, not an Annot: an Annot
        becomes unusable once its Page object is garbage collected.)"""
        if not self.show_markups:
            return None
        a = self._annot_at(self.doc[index], pt)
        return a.xref if a is not None else None

    def annot_tooltip(self, index, pt):
        page = self.doc[index]
        a = self._annot_at(page, pt)
        if a is None:
            return ""
        model = annotations.read(a)
        label = annotations.LABELS.get(model["kind"], a.type[1]) if model else a.type[1]
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
        keep = []
        for x in xrefs:
            try:
                if annotations.read(page.load_annot(x)) is not None and x not in keep:
                    keep.append(x)
            except Exception:
                pass
        old = self.selection
        if not keep:
            self.selection, self.selected_model, self.extra = None, None, []
        else:
            self.selection = (index, keep[0])
            self.selected_model = annotations.read(page.load_annot(keep[0]))
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
        for x in self.selected_xrefs():
            try:
                m = annotations.read(page.load_annot(x))
            except Exception:
                m = None
            if m is not None:
                out.append((x, m))
        return out

    def select_in_box(self, index, box, add=False):
        """Select the markups lying entirely inside box. Returns how many."""
        page = self.doc[index]
        found = []
        for an in page.annots():
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
            page = self.doc[index]
            for x, m in changes:
                made[x] = annotations.replace(page, x, m)
        self.modify(do, [index])
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
        self.statusMessage.emit(f"Moved {step:g} pt (Shift+arrow: 10 pt, Ctrl+arrow: 0.1 pt; "
                                "Ctrl+Z undoes the whole series)")
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
            for x in xrefs:
                try:
                    page.delete_annot(page.load_annot(x))
                except Exception:
                    pass
        self.modify(do, [index])

    # ---- arrange: align, distribute, stacking order -------------------------------
    def _display_bounds(self, page, model):
        return annotations.bounds(model) * page.rotation_matrix

    def align(self, how, ref="first"):
        """how: left, hcenter, right, top, vmiddle, bottom (as seen on screen).
        ref: first selected (default), last selected, selection bounds, or page."""
        models = [(x, m) for x, m in self.selected_models() if annotations.movable(m)]
        if not models or (len(models) < 2 and ref != "page"):
            self.statusMessage.emit("Select two or more markups to align (or align to the page).")
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
            self.statusMessage.emit("Select three or more markups to distribute.")
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
        """how: front, back, forward, backward (stacking order of the selected markups)."""
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
        self.modify(do, [index])
        self._set_selection(index, sel)

    def edit_annot_text(self, index, xref):
        page = self.doc[index]
        model = annotations.read(page.load_annot(xref))
        if model is None:
            return
        title = annotations.LABELS.get(model["kind"], "Annotation")
        text, ok = dialogs.get_text(self, "Edit " + title, "Text:", model.get("text", ""))
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
            for a in page.annots():
                if a.type[0] not in (pymupdf.PDF_ANNOT_HIGHLIGHT, pymupdf.PDF_ANNOT_UNDERLINE,
                                     pymupdf.PDF_ANNOT_STRIKE_OUT, pymupdf.PDF_ANNOT_SQUIGGLY):
                    continue
                m = annotations.read(a)
                if m and m["kind"] == "comment":
                    cards.append((annotations.bounds(m), m.get("text", ""), a.xref))
            self._card_cache[index] = cards
        return self._card_cache[index]

    def keyPressEvent(self, e):
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
        if e.key() == Qt.Key_Escape and self.obj_sel is not None:
            self.clear_object_selection()
            return
        if e.key() == Qt.Key_Escape and self.text_sel is not None:
            self.clear_text_selection()
            return
        if e.key() == Qt.Key_Escape:
            # Escape twice in a row: back to the Select (arrow) tool
            import time
            now = time.monotonic()
            twice = now - getattr(self, "_last_esc", -10.0) < 0.8
            self._last_esc = -10.0 if twice else now
            if twice and self.tool != "select":
                self.selectToolRequested.emit()
                return
            if self.selection is not None:
                self.clear_selection()
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

    def edit_text_at(self, index, pt):
        if self._inline is not None:
            self._inline.commit()      # finish the edit already in progress first
        hit = text_edit.line_at(self._lines(index), pt)
        if hit is None:
            self.statusMessage.emit("No text there. Click on a line of text to edit it.")
            return
        page = self.doc[index]
        if any(a.type[0] == pymupdf.PDF_ANNOT_REDACT for a in page.annots()):
            QMessageBox.warning(self, "Edit text", "This page has pending redactions; "
                                "editing text would apply them. Remove them first.")
            return
        rect, line = hit
        old = text_edit.line_text(line)
        w = self.pages[index]
        upright = (text_edit.line_rotation(line) + page.rotation) % 360 == 0
        if not upright:
            # sideways text: the on-page editor can't sit along it, use the dialog
            new, ok = dialogs.get_text(self, "Edit text", "Line text:", old)
            if ok and new != old:
                self._apply_text_edit(index, line, new, (0, 0), None)
            return
        size = text_edit.main_span(line)["size"]
        ed = InlineEditor(w, w.to_screen(rect), old, text_edit.font_family_hint(line),
                          size * self.zoom)
        self._inline = ed

        def done(text, dx, dy, wrap_px):
            self._inline = None
            if text == old and not dx and not dy and wrap_px is None:
                return
            # screen movement -> PDF (unrotated) points
            m = self.doc[index].derotation_matrix
            v = pymupdf.Point(dx / self.zoom, dy / self.zoom) * m - pymupdf.Point(0, 0) * m
            wrap = wrap_px / self.zoom if wrap_px else None
            self._apply_text_edit(index, line, text, (v.x, v.y), wrap)
        ed.committed.connect(done)
        ed.canceled.connect(lambda: setattr(self, "_inline", None))

    def _markups_on_line(self, page, line):
        """xrefs of text markups (highlight, underline, comments...) and sticky notes sitting
        on this line of text: they travel with it when the text is moved."""
        box = pymupdf.Rect(line["bbox"])
        out = []
        for an in page.annots():
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

    def _apply_text_edit(self, index, line, new, offset, wrap):
        used = {}

        def do():
            page = self.doc[index]
            moving = []
            if offset[0] or offset[1]:
                for x in self._markups_on_line(page, line):
                    m = annotations.read(page.load_annot(x))
                    if m is not None:
                        moving.append((x, m))
            used["font"] = text_edit.replace_line(page, line, new, offset, wrap)
            d = pymupdf.Point(offset)
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
        font = used.get("font") or ""
        if font.startswith("KZS") or font == "KZUni":
            self._fonts_added = True
            self.statusMessage.emit("Edited using the installed copy of the original font."
                                    if font.startswith("KZS") else
                                    "The original font lacks some of these characters; used "
                                    "a Unicode font for this line.")
        elif font and not font.startswith("KZ"):
            self.statusMessage.emit("Original font isn't available for these characters; "
                                    "used the closest standard font.")

    # ---- redaction ---------------------------------------------------------------------
    def mark_redactions(self, index, rects):
        def do():
            pg = self.doc[index]
            for r in rects:
                a = pg.add_redact_annot(r, fill=(0, 0, 0))
                a.set_colors(stroke=(0.85, 0, 0))
                a.set_info(title=annotations.author(), content="Redaction (not applied yet)")
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
            QMessageBox.information(self, "Erase content", "This page has redaction marks that "
                                    "aren't applied yet. Apply or remove them first (erasing "
                                    "would apply them too).")
            return
        self.clear_selection()
        self.modify(lambda: erase.erase(self.doc[index], rect), [index])
        self.statusMessage.emit("Erased the content inside the box (Ctrl+Z undoes it)")

    def capture_area(self, index, rect):
        """Capture tool (Bluebeam Snapshot): copy what's in the box, markups included. Ctrl+V
        here pastes it at the same size as an image markup made of the original vector
        drawing; a picture of it also pastes into Word, email and so on."""
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
        self.statusMessage.emit("Captured: Ctrl+V pastes it here as sharp vector content "
                                "(and as a picture into Word or email)")

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

    def object_at(self, index, pt):
        """The topmost picture or shape under PDF point pt, or None."""
        objs = self.content_objects(index)
        return objs.at(pt, 4 / self.zoom) if objs is not None else None

    def objects_in(self, index, box):
        objs = self.content_objects(index)
        return objs.inside(box) if objs is not None else []

    def object_lines(self, index, item):
        objs = self.content_objects(index)
        return objs.lines(item) if objs is not None else []

    def selected_objects(self):
        return self.obj_sel[1] if self.obj_sel else []

    def selected_objects_rect(self):
        r = pymupdf.Rect()
        for it in self.selected_objects():
            r |= it["rect"]
        return r

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
        if items:
            pics = sum(1 for it in items if it["kind"] == "picture")
            shapes = len(items) - pics
            what = ", ".join(x for x in (
                f"{pics} picture" + ("s" if pics != 1 else "") if pics else "",
                f"{shapes} shape" + ("s" if shapes != 1 else "") if shapes else "") if x)
            self.statusMessage.emit(f"Selected {what}: drag to move, drag a handle to resize, "
                                    "Delete deletes, right-click for more")

    def clear_object_selection(self):
        if self.obj_sel is not None:
            self.select_objects(self.obj_sel[0], [])

    def _objects_edit(self, label, fn, keep=True):
        """Run fn(page, ns) on the selected objects as one undo step; keep them selected."""
        if self.obj_sel is None:
            return
        index, items = self.obj_sel
        ns = [it["n"] for it in items]

        def do():
            fn(self.doc[index], ns)
        self.modify(do, [index])
        self._obj_cache.pop(index, None)
        self.obj_sel = None
        if keep:
            objs = self.content_objects(index)
            again = [it for it in (objs.items if objs else []) if it["n"] in set(ns)]
            self.obj_sel = (index, again) if again else None
        self.pages[index].update()
        self.statusMessage.emit(label + " (Ctrl+Z undoes it)")

    def move_objects(self, new_rect):
        from . import page_objects
        old = self.selected_objects_rect()
        if self.obj_sel is None:
            return
        self._objects_edit("Moved", lambda pg, ns: page_objects.move_to(pg, ns, old, new_rect))

    def rotate_objects(self, degrees):
        from . import page_objects
        if self.obj_sel is None:
            return
        rect = self.selected_objects_rect()
        self._objects_edit("Rotated", lambda pg, ns: page_objects.rotate(pg, ns, rect, degrees))

    def delete_objects(self):
        from . import page_objects
        self._objects_edit("Deleted", page_objects.delete, keep=False)

    def copy_picture(self):
        """Copy the one selected picture (Ctrl+V pastes it as an image markup)."""
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
        self.statusMessage.emit("Picture copied: Ctrl+V pastes it as an image markup")

    def save_picture(self):
        from PySide6.QtWidgets import QFileDialog
        items = self.selected_objects()
        if len(items) != 1 or not items[0]["xref"]:
            return
        data, ext = annotations.image_bytes(self.doc, items[0]["xref"])
        folder = os.path.dirname(self.path) if self.path else ""
        out, _ = QFileDialog.getSaveFileName(self, "Save picture as",
                                             os.path.join(folder, "picture." + ext),
                                             f"{ext.upper()} image (*.{ext})")
        if out:
            with open(out, "wb") as f:
                f.write(data)
            self.statusMessage.emit("Saved " + os.path.basename(out))

    REDACT_TAG = "Redaction: "         # Search & redact marks remember their term in /Contents

    def hidden_matches(self, text):
        """Where `text` occurs outside the page drawing (which page redaction can't reach):
        {"fields", "markups", "bookmarks", "metadata"} -> count."""
        t = text.lower()
        n = {"fields": 0, "markups": 0, "bookmarks": 0, "metadata": 0}
        for i in range(self.doc.page_count):
            pg = self.doc[i]
            for w in pg.widgets():
                if t in str(w.field_value or "").lower():
                    n["fields"] += 1
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

    def _scrub_terms(self, terms):
        """Remove Search & redact terms from places outside the page drawing: form field
        values, markup text, bookmark titles and document properties."""
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
                val = w.field_value
                if isinstance(val, str) and pat.search(val):
                    pg.delete_widget(w)         # its stored appearance holds the text too
            for x in [a.xref for a in pg.annots() if a.type[0] != pymupdf.PDF_ANNOT_REDACT]:
                a = pg.load_annot(x)
                info = {k: a.info.get(k) or "" for k in ("content", "subject", "title")}
                if any(pat.search(v) for v in info.values()):
                    a.set_info(**{k: clean(v) for k, v in info.items()})
                    a.update()
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

    def pending_redactions(self):
        n = 0
        for i in range(self.doc.page_count):
            pg = self.doc[i]
            n += sum(1 for a in pg.annots() if a.type[0] == pymupdf.PDF_ANNOT_REDACT)
        return n

    def apply_redactions(self, scrub=False):
        """Permanently remove everything under the redaction marks (text, images, drawings)."""
        def do():
            self._scrub_terms(self._redaction_terms())
            for i in range(self.doc.page_count):
                pg = self.doc[i]
                marks = [pymupdf.Rect(a.rect) for a in pg.annots()
                         if a.type[0] == pymupdf.PDF_ANNOT_REDACT]
                if marks:
                    self._clear_under_marks(pg, marks)
                    # Line art: remove only what's fully inside a mark. "If touched" deleted
                    # entire long paths (contours, walls, borders) crossing a small box on CAD
                    # sheets. Text and image pixels under the mark are always removed.
                    pg.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_PIXELS,
                                        graphics=pymupdf.PDF_REDACT_LINE_ART_REMOVE_IF_COVERED,
                                        text=pymupdf.PDF_REDACT_TEXT_REMOVE)
            if scrub:
                self.doc.scrub(attached_files=True, clean_pages=True, embedded_files=True,
                               hidden_text=True, javascript=True, metadata=True,
                               redactions=False, remove_links=False, reset_fields=False,
                               reset_responses=True, thumbnails=True, xml_metadata=True)
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

    def add_background(self, spec, pages):
        from . import background
        self.modify(lambda: background.apply(self.doc, pages, spec), pages)
        self._obj_cache = {}
        self.statusMessage.emit(f"Background added to {len(pages)} page(s) (Ctrl+Z undoes it)")

    def remove_background(self, pages):
        from . import background
        if not pages:
            self.statusMessage.emit("Those pages have no background to remove")
            return
        self.modify(lambda: background.remove_pages(self.doc, pages), pages)
        self.statusMessage.emit(f"Background removed from {len(pages)} page(s)")

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
            self.sig_results = [{"summary": f"Couldn't check the signature: {ex}", "ok": False,
                                 "intact": False}]
        if not self.sig_results:
            return
        self.read_only = True
        good = all(r.get("ok") for r in self.sig_results)
        text = "  ".join(r["summary"] for r in self.sig_results)
        color = "#e7f6e7" if good else "#fde8e8"
        self.show_banner(("✔ " if good else "⚠ ") + text +
                         "  This file is read-only so the signature stays valid.",
                         color, "Edit anyway", self._edit_signed)

    def _edit_signed(self):
        r = QMessageBox.question(
            self, "Edit a signed document?",
            "Changing a digitally signed document makes its signature show as changed or "
            "invalid in Acrobat and other readers.\n\nTip: use Save As to keep the signed "
            "original untouched.\n\nEdit anyway?")
        if r == QMessageBox.Yes:
            self.read_only = False
            self.show_banner("Editing a signed document: when saved, its digital signature "
                             "will no longer validate.", "#fff4d6")

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

    def place_signature(self, index, kind, pt=None, field_rect=None):
        """Write the saved signature/initials (and today's date) into the page content."""
        if kind not in self.sig_images:
            return
        png, pm = self.sig_images[kind]
        page = self.doc[index]
        if field_rect is not None:      # fill a signature form field
            disp = pymupdf.Rect(field_rect) * page.rotation_matrix
        else:
            disp = self.sig_display_rect(index, kind, pt)
        when = signatures.date_text()
        if not hasattr(self, "_last_sig_spot"):
            self._last_sig_spot = {}
        self._last_sig_spot[kind] = pymupdf.Rect(disp)

        def do():
            self._draw_signature(self.doc[index], kind, disp, when)
        self.modify(do, [index])
        self.signed = True
        self.signedDocument.emit()

    # ---- protection (read-only PDFs) ----------------------------------------------------
    def _check_permissions(self):
        # (permissions is a signed 32-bit value: restricted files report negative numbers too)
        perm = self.doc.permissions
        self.read_only = not (perm & pymupdf.PDF_PERM_MODIFY and perm & pymupdf.PDF_PERM_ANNOTATE)

    def unlock(self, password):
        """Unlock editing with the permissions (owner) password."""
        rc = self.doc.authenticate(password)
        if rc & 4:                     # 4 = owner password accepted
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

    def set_security(self, open_pw="", owner_pw="", perms=-1):
        """Security to apply on the next save ('' / '' removes all protection)."""
        if self.read_only:
            raise PermissionError("Unlock the document with its permissions password first.")
        self.security = {"open_pw": open_pw, "owner_pw": owner_pw, "perms": perms}
        self.dirty = True
        self.documentChanged.emit()

    # ---- sanitize ---------------------------------------------------------------------------
    SANITIZE_OPTIONS = [  # (key, label, default)
        ("metadata", "Document information (author, title, dates, producer)", True),
        ("javascript", "JavaScript and automatic actions", True),
        ("embedded_files", "Attached and embedded files", True),
        ("hidden_text", "Hidden text (e.g. invisible OCR text)", False),
        ("links", "Links", False),
        ("markups", "Comments and markups", False),
        ("form_data", "Data typed into form fields", False),
        ("thumbnails", "Page thumbnails and leftover redaction data", True),
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
                                graphics=pymupdf.PDF_REDACT_LINE_ART_REMOVE_IF_COVERED,
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
            self.show_banner("Digital signatures removed. Save to keep the unsigned version.",
                             "#fff4d6")
        return n["n"]

    def timestamp(self, url, out_path):
        """Add a trusted timestamp (RFC 3161) from a time server; writes out_path."""
        from . import digisign
        if self.dirty:
            raise RuntimeError("Save your changes first.")
        with open(self.path, "rb") as f:
            data = f.read()
        return digisign.timestamp(data, out_path, url)

    # ---- multi-place signature & placeholders -------------------------------------------------
    def _draw_signature(self, pg, kind, disp, when):
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
        when = signatures.date_text()
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
            for an in pg.annots():
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
        w = self._widget_at(self.doc[index], pt)
        return w.xref if w is not None else None

    def fill_field(self, index, xref):
        page = self.doc[index]
        w = page.load_widget(xref)
        t = w.field_type
        if t == pymupdf.PDF_WIDGET_TYPE_CHECKBOX:
            on = w.on_state()
            value = "Off" if w.field_value == on else on
            self._set_field(index, xref, value)
        elif t == pymupdf.PDF_WIDGET_TYPE_RADIOBUTTON:
            self._set_field(index, xref, True)
        elif t in (pymupdf.PDF_WIDGET_TYPE_COMBOBOX, pymupdf.PDF_WIDGET_TYPE_LISTBOX):
            menu = QMenu(self)
            for c in w.choice_values or []:
                label = c[1] if isinstance(c, (list, tuple)) else c
                act = menu.addAction(label)
                act.setCheckable(True)
                act.setChecked(label == w.field_value)
            pw = self.pages[index]
            r = pw.to_screen(w.rect)
            chosen = menu.exec(pw.mapToGlobal(r.bottomLeft().toPoint()))
            if chosen is not None:
                self._set_field(index, xref, chosen.text())
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
        self.modify(do, [index])

    def _edit_text_field(self, index, xref):
        page = self.doc[index]
        w = page.load_widget(xref)
        pw = self.pages[index]
        r = pw.to_screen(w.rect)
        multiline = bool(w.field_flags & pymupdf.PDF_TX_FIELD_IS_MULTILINE)
        ed = QPlainTextEdit(pw) if multiline else QLineEdit(pw)
        if multiline:
            ed.setPlainText(w.field_value or "")
        else:
            ed.setText(w.field_value or "")
            ed.selectAll()
        f = ed.font()
        size = w.text_fontsize or min(12.0, w.rect.height * 0.65)
        f.setPixelSize(max(8, int(size * self.zoom)))
        ed.setFont(f)
        ed.setGeometry(r.toRect().adjusted(-1, -1, 1, 1))
        ed.setStyleSheet("background:#fffbe6; border:2px solid #0078d7;")
        done = {"x": False}

        def finish(save=True, next_field=False):
            if done["x"]:
                return
            done["x"] = True
            text = ed.toPlainText() if multiline else ed.text()
            ed.hide()
            ed.deleteLater()
            if save and text != (w.field_value or ""):
                self._set_field(index, xref, text)
            if next_field:
                self._next_text_field(index, xref)

        class Keys(QObject):
            def eventFilter(_s, obj, e):
                if e.type() == QEvent.KeyPress:
                    if e.key() == Qt.Key_Escape:
                        finish(save=False)
                        return True
                    if e.key() == Qt.Key_Tab:
                        finish(next_field=True)
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

    def _next_text_field(self, index, xref):
        """Tab: go to the next text field (this page, then following pages)."""
        order = []
        for i in range(self.doc.page_count):
            pg = self.doc[i]
            ws = sorted((w for w in pg.widgets() if w.field_type == pymupdf.PDF_WIDGET_TYPE_TEXT),
                        key=lambda w: (round(w.rect.y0), w.rect.x0))
            order += [(i, w.xref) for w in ws]
        if (index, xref) in order:
            k = order.index((index, xref))
            if k + 1 < len(order):
                ni, nx = order[k + 1]
                if ni != index:
                    self.goto_page(ni)
                QTimer.singleShot(0, lambda: self._edit_text_field(ni, nx))

    # ---- form design ---------------------------------------------------------------
    FIELD_TYPES = {"f_text": pymupdf.PDF_WIDGET_TYPE_TEXT,
                   "f_check": pymupdf.PDF_WIDGET_TYPE_CHECKBOX,
                   "f_radio": pymupdf.PDF_WIDGET_TYPE_RADIOBUTTON,
                   "f_combo": pymupdf.PDF_WIDGET_TYPE_COMBOBOX,
                   "f_sign": pymupdf.PDF_WIDGET_TYPE_SIGNATURE}
    FIELD_PREFIX = {"f_text": "Text", "f_check": "Check", "f_radio": "Option",
                    "f_combo": "Dropdown", "f_sign": "Signature"}

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
            w0, h0 = {"f_sign": (180, 45)}.get(tool, (160, 20))
            rect = pymupdf.Rect(a.x, a.y, a.x + w0, a.y + h0)
        name = self._unique_name(self.FIELD_PREFIX[tool])
        choices = []
        if tool == "f_radio":
            groups = sorted({w.field_name for pg in self.doc for w in pg.widgets()
                             if w.field_type == pymupdf.PDF_WIDGET_TYPE_RADIOBUTTON})
            label = "Group name (options in the same group are mutually exclusive):"
            name, ok = QInputDialog.getItem(self, "Option button", label,
                                            groups + [self._unique_name("Group")],
                                            0 if groups else len(groups), True)
            if not ok or not name.strip():
                return
        elif tool == "f_combo":
            text, ok = dialogs.get_text(self, "Dropdown", "Choices, one per line:")
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
                w.field_value = choices[0]
            if tool == "f_radio":
                w.field_value = False
            self.doc[index].add_widget(w)
        self.modify(do, [index])

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
        name, ok = QInputDialog.getText(self, "Field properties",
                                        f"{w.field_type_string} field name:", text=w.field_name)
        if not ok or not name.strip():
            return
        choices = None
        if w.field_type in (pymupdf.PDF_WIDGET_TYPE_COMBOBOX, pymupdf.PDF_WIDGET_TYPE_LISTBOX):
            cur = "\n".join(c[1] if isinstance(c, (list, tuple)) else c
                            for c in (w.choice_values or []))
            text, ok = dialogs.get_text(self, "Dropdown", "Choices, one per line:", cur)
            if ok:
                choices = [c.strip() for c in text.splitlines() if c.strip()]

        def do():
            pg = self.doc[index]
            ww = pg.load_widget(xref)
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
        dlg = QProgressDialog("Loading OCR engine...", "Cancel", 0, len(pages), self)
        dlg.setWindowTitle("Recognize text (OCR)")
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
                dlg.setLabelText(f"Recognizing text on page {i + 1} ({n + 1} of {len(pages)})...")
                dpi = ocr.page_dpi(self.doc[i],
                                   ocr.ACCURACY_DPI.get(accuracy, ocr.ACCURACY_DPI["fast"]))
                best = ocr.Rendering(self.doc[i], dpi=dpi)
                res = ocr_image(best)
                if res is None:
                    break
                sharper = ocr.page_dpi(self.doc[i], ocr.ACCURACY_DPI["high"])
                if accuracy == "auto" and sharper > dpi and ocr.needs_sharper(res, best):
                    dlg.setLabelText(f"Page {i + 1}: small or unclear text, "
                                     "recognizing again at higher resolution...")
                    dpi = sharper
                    best = ocr.Rendering(self.doc[i], dpi=dpi)
                    res = ocr_image(best)
                    if res is None:
                        break
                turns = (90, 180, 270) if accuracy == "high" else \
                    ((90, 270) if ocr.mostly_vertical(res) else ())
                if turns:
                    # Sideways or upside-down text: try other turns, keep the best.
                    dlg.setLabelText(f"Page {i + 1}: checking other orientations...")
                    for extra in turns:
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
                results[i] = (res, best)
                dlg.setValue(n + 1)
        except Exception as ex:
            QMessageBox.critical(self, "OCR failed", str(ex))
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
        self.statusMessage.emit(f"OCR added {sum(counts.values())} lines of text "
                                f"on {len(results)} page(s)")

    # ---- page operations --------------------------------------------------
    def rotate_page(self, index, delta):
        page = self.doc[index]
        self.modify(lambda: page.set_rotation((page.rotation + delta) % 360), structural=True)

    def delete_page(self, index):
        if self.doc.page_count <= 1:
            QMessageBox.information(self, "Delete page", "A PDF must keep at least one page.")
            return
        self.modify(lambda: self.doc.delete_page(index), structural=True)

    def move_page(self, index, delta):
        target = index + delta
        if not 0 <= target < self.doc.page_count:
            return
        # move_page(pno, to) inserts *before* `to`; -1 means append at the end.
        to = target if delta < 0 else (target + 1 if target + 1 < self.doc.page_count else -1)
        self.modify(lambda: self.doc.move_page(index, to), structural=True)
        self.goto_page(target)

    def flatten(self, pages=None, widgets=True):
        """Burn annotations (and form fields unless widgets=False) into the page content
        (pages=None: all pages). Undo works until the file is closed."""
        def do():
            if pages is None:
                self.doc.bake(annots=True, widgets=widgets)
                return
            # Swapping a page in drops bookmarks and links that point to it: remember them
            toc = self.doc.get_toc(simple=False)
            links = {}
            for pg in self.doc:
                for ln in pg.get_links():
                    if ln.get("kind") == pymupdf.LINK_GOTO and ln.get("page") in pages:
                        links.setdefault(pg.number, []).append(ln)
            for i in sorted(pages, reverse=True):
                # PyMuPDF flattens whole documents: flatten a one-page copy and swap it in
                tmp = pymupdf.open()
                tmp.insert_pdf(self.doc, from_page=i, to_page=i)
                tmp.bake(annots=True, widgets=widgets)
                self.doc.delete_page(i)
                self.doc.insert_pdf(tmp, start_at=i)
                tmp.close()
            if toc:
                self.doc.set_toc(toc)
            for pno, lst in links.items():
                pg = self.doc[pno]
                have = [pymupdf.Rect(ln["from"]) for ln in pg.get_links()]
                for ln in lst:
                    if pymupdf.Rect(ln["from"]) not in have:
                        pg.insert_link({"kind": pymupdf.LINK_GOTO, "from": ln["from"],
                                        "page": ln["page"], "to": ln.get("to", pymupdf.Point(0, 0))})
        self.clear_selection()
        self.modify(do, structural=True)

    def move_page_to(self, src, dest_before):
        """Move page src so it sits before old page index dest_before (== count: end)."""
        n = self.doc.page_count
        if dest_before in (src, src + 1) or not 0 <= src < n:
            return
        to = dest_before if dest_before < n else -1
        self.modify(lambda: self.doc.move_page(src, to), structural=True)
        self.goto_page(dest_before if dest_before < src else dest_before - 1)

    def insert_pdf(self, path, at):
        def do():
            with pymupdf.open(path) as other:
                self.doc.insert_pdf(other, start_at=at)
        self.modify(do, structural=True)

    def insert_blank(self, at):
        r = self.page_rects[min(at, len(self.page_rects) - 1)]
        self.modify(lambda: self.doc.new_page(at, width=r.width, height=r.height),
                    structural=True)

    def extract_pages(self, first, last, path):
        out = pymupdf.open()
        out.insert_pdf(self.doc, from_page=first, to_page=last)
        out.save(path, garbage=3, deflate=True)
        out.close()

    # ---- search -----------------------------------------------------------
    def find(self, text, backwards=False):
        if not text:
            self.clear_search()
            return 0
        if text != self._search_text:
            self._search_text = text
            self.search_hits = {}
            self._search_list = []
            for i, page in enumerate(self.doc):
                hits = page.search_for(text)
                if hits:
                    self.search_hits[i] = hits
                    self._search_list.extend((i, k) for k in range(len(hits)))
            # start at the first hit at or after the current page
            cur = self.current_page()
            self._search_pos = next((n - 1 for n, (i, _) in enumerate(self._search_list)
                                     if i >= cur), -1)
            for w in self.pages:
                w.update()
        if not self._search_list:
            return 0
        step = -1 if backwards else 1
        self._search_pos = (self._search_pos + step) % len(self._search_list)
        i, k = self._search_list[self._search_pos]
        w = self.pages[i]
        r = w.to_screen(self.search_hits[i][k])
        top = w.y() + r.y()
        vbar = self.verticalScrollBar()
        if not (vbar.value() + 40 < top < vbar.value() + self.viewport().height() - 40):
            vbar.setValue(int(top - self.viewport().height() / 3))
        hbar = self.horizontalScrollBar()
        left = w.x() + r.x()
        if not (hbar.value() < left < hbar.value() + self.viewport().width() - 40):
            hbar.setValue(int(left - 40))
        for w in self.pages:
            if w.index in self.search_hits:
                w.update()
        self.statusMessage.emit(f"Match {self._search_pos + 1} of {len(self._search_list)}")
        return len(self._search_list)

    def current_hit(self):
        if 0 <= self._search_pos < len(self._search_list):
            return self._search_list[self._search_pos]
        return None

    def clear_search(self):
        self.search_hits = {}
        self._search_list = []
        self._search_text = None
        self._search_pos = -1
        for w in self.pages:
            w.update()

    # ---- saving -----------------------------------------------------------
    def save(self, path=None):
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
        if not self.dirty and sec is None and self._orig_data is not None:
            # nothing changed: write the original bytes, so digital signatures stay valid
            # and protection stays exactly as it was
            with open(tmp, "wb") as f:
                f.write(self._orig_data)
        elif sec is None and self._orig_enc is not None:
            # edited a protected file: save it protected again (PyMuPDF writes a full save
            # unencrypted unless told otherwise)
            enc = self._orig_enc
            owner = enc.get("owner_pw") or enc.get("user_pw") or secrets.token_urlsafe(24)
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
        os.replace(tmp, path)
        self.path = path
        if self.dirty or sec is not None:
            self._orig_data = None          # the file on disk is our rewrite now
        self.dirty = False
        self.documentChanged.emit()

    def close_doc(self):
        self.doc.close()
