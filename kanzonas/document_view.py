"""Scrolling view of one open document, plus every editing operation on it."""

import os
import time
from concurrent.futures import ThreadPoolExecutor

import pymupdf
from PySide6.QtCore import Qt, Signal, QTimer, QObject, QEvent
from PySide6.QtCore import QRectF
from PySide6.QtGui import (QColor, QGuiApplication, QPixmap, QPainter, QPen, QCursor)
from PySide6.QtWidgets import (QScrollArea, QWidget, QVBoxLayout, QInputDialog,
                               QMessageBox, QLineEdit, QProgressDialog, QApplication,
                               QMenu, QPlainTextEdit)

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
    pageChanged = Signal(int)
    documentChanged = Signal()      # content edited (thumbnails / title need refresh)
    structureChanged = Signal()     # pages added / removed / reordered / rotated
    zoomChanged = Signal(float)
    statusMessage = Signal(str)
    selectionChanged = Signal()
    signedDocument = Signal()
    requestSignature = Signal(int, int)      # page index, signature field xref

    def __init__(self, path, parent=None):
        super().__init__(parent)
        self.path = os.path.abspath(path)
        # Load from memory so the file is not locked on Windows and can be overwritten on save.
        with open(self.path, "rb") as f:
            data = f.read()
        self.doc = pymupdf.open(stream=data, filetype="pdf")
        if self.doc.needs_pass:
            pw, ok = QInputDialog.getText(self, "Password required",
                                          os.path.basename(path) + " is protected:",
                                          QLineEdit.Password)
            if not ok or not self.doc.authenticate(pw):
                raise ValueError("Wrong or missing password")
        self._check_permissions()
        self.dirty = False
        self.zoom = 1.0
        self.tool = "select"
        self.selection = None          # (page index, annotation xref)
        self.selected_model = None
        self.show_comment_boxes = True
        self._inline = None
        self.sig_images = {}           # kind -> (png bytes, QPixmap)
        self.signed = False
        self.protect_on_save = False
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
        self._build_pages()
        self._fitted = False

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
            QTimer.singleShot(0, self.fit_width)

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
        self.goto_page(page)

    def wheelEvent(self, e):
        if e.modifiers() & Qt.ControlModifier:
            if e.angleDelta().y() > 0:
                self.zoom_in()
            elif e.angleDelta().y() < 0:
                self.zoom_out()
            e.accept()
        else:
            super().wheelEvent(e)

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
        self.viewport().setCursor(Qt.OpenHandCursor)

    def set_tool(self, tool):
        self.tool = tool
        if tool not in ("select",):
            self.clear_selection()
        if tool == "eraser":
            self.viewport().setCursor(eraser_cursor())
            return
        cursors = {"hand": Qt.OpenHandCursor, "select": Qt.IBeamCursor,
                   "edittext": Qt.IBeamCursor}
        self.viewport().setCursor(cursors.get(tool, Qt.CrossCursor))

    # ---- undo / modify ----------------------------------------------------
    def _snapshot(self):
        return self.doc.tobytes()

    def _restore(self, data):
        self._clear_caches()
        self.selection = None
        self.selected_model = None
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
            QMessageBox.information(self, "Protected document",
                                    "This PDF is protected against changes. Use File > Unlock "
                                    "with password... if you have its owner password.")
            return
        snap = self._snapshot()
        self._clear_caches()
        try:
            fn()
        except Exception as ex:
            QMessageBox.warning(self, "Edit failed", str(ex))
            self._restore(snap)
            return
        self._undo.append(snap)
        del self._undo[:-UNDO_LIMIT]
        self._redo.clear()
        self.dirty = True
        if structural:
            page = self.current_page()
            self.search_hits.clear()
            self._search_list = []
            self._search_text = None
            self.selection = None
            self.selected_model = None
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
        self._line_cache = {}
        self._word_cache = {}
        self._card_cache = {}

    def _words(self, index):
        if index not in self._word_cache:
            self._word_cache[index] = self.doc[index].get_text("words", sort=False)
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
    def _words_text(words):
        out, last = [], None
        for w in words:
            key = (w[5], w[6])
            if last is not None:
                out.append(" " if key == last else "\n")
            out.append(w[4])
            last = key
        return "".join(out)

    # ---- tool styles --------------------------------------------------------
    def tool_props(self, tool):
        return annotations.tool_props(tool) if tool in annotations.DEFAULTS else {}

    def tool_color(self, tool):
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
        if not words:
            if tool != "select":
                self.statusMessage.emit("No text there to mark up")
            return
        text = self._words_text(words)
        if tool == "select":
            QGuiApplication.clipboard().setText(text)
            self.statusMessage.emit(f"Copied {len(text)} characters")
            return
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
        if tool == "textbox":
            if is_click or rect.width < 20 or rect.height < 10:
                rect = pymupdf.Rect(a.x, a.y, a.x + 200, a.y + 40)
            text, ok = dialogs.get_text(self, "Text box", "Text:")
            if not ok or not text.strip():
                return
            self._create(index, {"kind": "textbox", "rect": rect, "text": text, "props": props})
            return
        if is_click:
            return
        model = {"kind": tool, "props": props, "rect": rect}
        if tool in ("line", "arrow"):
            model["points"] = [a, b]
        self._create(index, model)

    def apply_ink(self, index, pts):
        self._create(index, {"kind": "ink", "props": self.tool_props("ink"),
                             "strokes": [pts], "rect": pymupdf.Rect()})

    def apply_point_tool(self, index, tool, pt):
        page = self.doc[index]
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
        if t in (pymupdf.PDF_ANNOT_POPUP, pymupdf.PDF_ANNOT_REDACT):
            return False
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
        if annot.type[0] == pymupdf.PDF_ANNOT_POPUP:
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
    def select_xref(self, index, xref):
        page = self.doc[index]
        annot = page.load_annot(xref) if xref else None
        model = annotations.read(annot) if annot else None
        old = self.selection
        self.selection = (index, xref) if model else None
        self.selected_model = model
        for i in {index, old[0] if old else index}:
            if 0 <= i < len(self.pages):
                self.pages[i].update()
        self.selectionChanged.emit()
        return model is not None

    def select_annot_at(self, index, pt):
        xref = self.annot_at(index, pt)
        if xref is None:
            return False
        return self.select_xref(index, xref)

    def clear_selection(self):
        if self.selection is None:
            return
        old = self.selection
        self.selection = None
        self.selected_model = None
        if 0 <= old[0] < len(self.pages):
            self.pages[old[0]].update()
        self.selectionChanged.emit()

    def commit_model(self, index, xref, model):
        """Replace annotation xref with a new version (one undo step); keep it selected."""
        if model["kind"] == "field":
            self._commit_field(index, xref, model)
            return
        made = {}

        def do():
            page = self.doc[index]
            page.delete_annot(page.load_annot(xref))
            made["xref"] = annotations.write(page, model).xref
        self.modify(do, [index])
        if "xref" in made:
            self.select_xref(index, made["xref"])

    def update_selected_props(self, props):
        if self.selection is None or self.selected_model is None or \
                self.selected_model["kind"] == "field":
            return
        model = annotations.copy(self.selected_model)
        model["props"] = dict(props)
        self.commit_model(self.selection[0], self.selection[1], model)

    def delete_selected(self):
        if self.selection is None:
            return
        index, xref = self.selection
        if self.selected_model and self.selected_model["kind"] == "field":
            self.delete_field(index, xref)
            return
        self.clear_selection()
        page = self.doc[index]
        self.modify(lambda: page.delete_annot(page.load_annot(xref)), [index])

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
        if xref is not None:
            self.edit_annot_text(index, xref)

    def comment_cards(self, index):
        """[(anchor rect, text, xref)] for comments on this page (cached)."""
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
        if e.key() in (Qt.Key_Delete, Qt.Key_Backspace) and self.selection is not None:
            self.delete_selected()
            return
        if e.key() == Qt.Key_Escape and self.selection is not None:
            self.clear_selection()
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
            # on an upright page, screen deltas map straight to PDF points
            offset = (dx / self.zoom, dy / self.zoom)
            wrap = wrap_px / self.zoom if wrap_px else None
            self._apply_text_edit(index, line, text, offset, wrap)
        ed.committed.connect(done)
        ed.cancelled.connect(lambda: setattr(self, "_inline", None))

    def _apply_text_edit(self, index, line, new, offset, wrap):
        used = {}

        def do():
            used["font"] = text_edit.replace_line(self.doc[index], line, new, offset, wrap)
        self.modify(do, [index])
        font = used.get("font") or ""
        if font.startswith("KZS"):
            self._fonts_added = True
            self.statusMessage.emit("Edited using the installed copy of the original font.")
        elif font and not font.startswith("KZ"):
            self.statusMessage.emit("Original font isn't available for these characters; "
                                    "used the closest standard font.")

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

        def do():
            pg = self.doc[index]
            img_rect = disp * pg.derotation_matrix
            pg.insert_image(img_rect, stream=png, keep_proportion=True, rotate=pg.rotation,
                            overlay=True)
            if when:
                size = 9 if kind == "signature" else 7
                base = pymupdf.Point(disp.x0, disp.y1 + size + 1) * pg.derotation_matrix
                pg.insert_text(base, when, fontsize=size, fontname="helv",
                               color=(0.1, 0.1, 0.1), rotate=pg.rotation)
        self.modify(do, [index])
        self.signed = True
        self.signedDocument.emit()

    # ---- protection (read-only PDFs) ----------------------------------------------------
    def _check_permissions(self):
        perm = self.doc.permissions
        self.read_only = perm >= 0 and not (perm & pymupdf.PDF_PERM_MODIFY
                                            and perm & pymupdf.PDF_PERM_ANNOTATE)

    def unlock(self, password):
        ok = self.doc.authenticate(password)
        if ok:
            self._check_permissions()
        return ok and not self.read_only

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

    def run_ocr(self, pages):
        """Recognize text on the given pages and add an invisible, searchable text layer."""
        from . import ocr
        dlg = QProgressDialog("Loading OCR engine...", "Cancel", 0, len(pages), self)
        dlg.setWindowTitle("Recognize text (OCR)")
        dlg.setWindowModality(Qt.WindowModal)
        dlg.setMinimumDuration(0)
        dlg.setValue(0)
        results = {}
        pool = ThreadPoolExecutor(max_workers=1)

        def ocr_image(rendering):
            fut = pool.submit(ocr.recognize, rendering.png)
            while not fut.done():       # keep the window responsive while OCR runs
                QApplication.processEvents()
                time.sleep(0.03)
                if dlg.wasCanceled():
                    return None
            return fut.result()

        try:
            for n, i in enumerate(pages):
                dlg.setLabelText(f"Recognizing text on page {i + 1} ({n + 1} of {len(pages)})...")
                best = ocr.Rendering(self.doc[i])
                res = ocr_image(best)
                if res is None:
                    break
                if ocr.mostly_vertical(res):
                    # Sideways text (e.g. a landscape scan): try both 90-degree turns, keep the best.
                    dlg.setLabelText(f"Page {i + 1}: text is sideways, trying other orientations...")
                    for extra in (90, 270):
                        r = ocr.Rendering(self.doc[i], extra)
                        alt = ocr_image(r)
                        if alt is None:
                            break
                        if ocr.score(alt) > ocr.score(res):
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

    def flatten(self, pages=None):
        """Burn annotations and form fields into the page content (pages=None: all pages).
        Undo works until the file is closed; after saving, flattening is permanent."""
        def do():
            if pages is None:
                self.doc.bake(annots=True, widgets=True)
                return
            for i in sorted(pages, reverse=True):
                # PyMuPDF flattens whole documents: flatten a one-page copy and swap it in
                tmp = pymupdf.open()
                tmp.insert_pdf(self.doc, from_page=i, to_page=i)
                tmp.bake(annots=True, widgets=True)
                self.doc.delete_page(i)
                self.doc.insert_pdf(tmp, start_at=i)
                tmp.close()
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
        if self.protect_on_save:
            # No-changes permissions with a random owner password nobody knows: anyone can
            # open, read and print, but PDF software that honours permissions won't edit.
            import secrets
            self.doc.save(tmp, garbage=1, deflate=True, encryption=pymupdf.PDF_ENCRYPT_AES_256,
                          owner_pw=secrets.token_urlsafe(24), user_pw="",
                          permissions=pymupdf.PDF_PERM_PRINT | pymupdf.PDF_PERM_PRINT_HQ
                          | pymupdf.PDF_PERM_COPY | pymupdf.PDF_PERM_ACCESSIBILITY)
        else:
            self.doc.save(tmp, garbage=1, deflate=True)
        os.replace(tmp, path)
        if self.protect_on_save:
            self.read_only = True
        self.path = path
        self.dirty = False
        self.documentChanged.emit()

    def close_doc(self):
        self.doc.close()
