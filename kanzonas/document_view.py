"""Scrolling view of one open document, plus every editing operation on it."""

import os

import pymupdf
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QColor, QGuiApplication
from PySide6.QtWidgets import (QScrollArea, QWidget, QVBoxLayout, QInputDialog,
                               QMessageBox, QLineEdit)

from .page_widget import PageWidget

PAGE_GAP = 12
MIN_ZOOM, MAX_ZOOM = 0.1, 8.0
UNDO_LIMIT = 30


def _rgb(qcolor):
    return (qcolor.redF(), qcolor.greenF(), qcolor.blueF())


class DocumentView(QScrollArea):
    pageChanged = Signal(int)
    documentChanged = Signal()      # content edited (thumbnails / title need refresh)
    structureChanged = Signal()     # pages added / removed / reordered / rotated
    zoomChanged = Signal(float)
    statusMessage = Signal(str)

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
        self.dirty = False
        self.zoom = 1.0
        self.tool = "select"
        self.color = QColor(255, 220, 0)
        self.search_hits = {}
        self._search_list = []
        self._search_pos = -1
        self._search_text = None
        self._undo = []
        self._redo = []
        self._pan_origin = None
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
        cursors = {"hand": Qt.OpenHandCursor, "select": Qt.IBeamCursor,
                   "eraser": Qt.PointingHandCursor}
        self.viewport().setCursor(cursors.get(tool, Qt.CrossCursor))

    # ---- undo / modify ----------------------------------------------------
    def _snapshot(self):
        return self.doc.tobytes()

    def _restore(self, data):
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

    def modify(self, fn, pages=None, structural=False):
        """Run an edit with an undo snapshot. pages = indices to repaint."""
        snap = self._snapshot()
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
            self._build_pages()
            self.goto_page(min(page, self.doc.page_count - 1))
            self.structureChanged.emit()
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

    # ---- text helpers -----------------------------------------------------
    @staticmethod
    def _nearest_word(words, pt):
        best, best_d = 0, None
        for i, w in enumerate(words):
            r = pymupdf.Rect(w[:4])
            if r.contains(pt):
                return i
            dx = max(r.x0 - pt.x, 0, pt.x - r.x1)
            dy = max(r.y0 - pt.y, 0, pt.y - r.y1)
            d = dx * dx + dy * dy * 4   # vertical distance matters more (line choice)
            if best_d is None or d < best_d:
                best, best_d = i, d
        return best

    def words_between(self, index, a, b):
        """Words in reading order from point a to point b (like a text cursor selection)."""
        words = self.doc[index].get_text("words", sort=False)
        if not words:
            return []
        i, j = self._nearest_word(words, a), self._nearest_word(words, b)
        if i > j:
            i, j = j, i
        return words[i:j + 1]

    @staticmethod
    def _line_rects(words):
        lines = {}
        order = []
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

    # ---- tools ------------------------------------------------------------
    def apply_drag_tool(self, index, tool, a, b, is_click):
        page = self.doc[index]
        rect = pymupdf.Rect(a, b).normalize()
        col = _rgb(self.color)

        if tool == "select":
            if is_click:
                return
            text = self._words_text(self.words_between(index, a, b))
            if text:
                QGuiApplication.clipboard().setText(text)
                self.statusMessage.emit(f"Copied {len(text)} characters")
            return

        if tool in ("highlight", "underline", "strikeout"):
            words = [] if is_click else self.words_between(index, a, b)
            if not words:
                self.statusMessage.emit("No text there to mark up")
                return
            rects = self._line_rects(words)
            adder = {"highlight": page.add_highlight_annot,
                     "underline": page.add_underline_annot,
                     "strikeout": page.add_strikeout_annot}[tool]

            def do():
                annot = adder(rects)
                annot.set_colors(stroke=col)
                annot.set_info(content=self._words_text(words))
                annot.update()
            self.modify(do, [index])
            return

        if tool == "textbox":
            if is_click or rect.width < 20 or rect.height < 10:
                rect = pymupdf.Rect(a.x, a.y, a.x + 200, a.y + 40)
            text, ok = QInputDialog.getMultiLineText(self, "Text box", "Text:")
            if not ok or not text.strip():
                return

            def do():
                annot = page.add_freetext_annot(rect, text, fontsize=11, fontname="helv",
                                                text_color=(0, 0, 0), border_color=col,
                                                rotate=page.rotation)
                annot.set_border(width=1)
                annot.update()
            self.modify(do, [index])
            return

        if is_click:
            return

        def do():
            if tool == "rect":
                annot = page.add_rect_annot(rect)
            elif tool == "ellipse":
                annot = page.add_circle_annot(rect)
            else:
                annot = page.add_line_annot(a, b)
                if tool == "arrow":
                    annot.set_line_ends(pymupdf.PDF_ANNOT_LE_NONE,
                                        pymupdf.PDF_ANNOT_LE_OPEN_ARROW)
            annot.set_colors(stroke=col)
            annot.set_border(width=2)
            annot.update()
        self.modify(do, [index])

    def apply_ink(self, index, pts):
        page = self.doc[index]
        col = _rgb(self.color)

        def do():
            annot = page.add_ink_annot([[(p.x, p.y) for p in pts]])
            annot.set_colors(stroke=col)
            annot.set_border(width=2)
            annot.update()
        self.modify(do, [index])

    def apply_point_tool(self, index, tool, pt):
        page = self.doc[index]
        if tool == "note":
            text, ok = QInputDialog.getMultiLineText(self, "Sticky note", "Note:")
            if not ok or not text.strip():
                return

            def do():
                annot = page.add_text_annot(pt, text, icon="Note")
                annot.set_colors(stroke=_rgb(self.color))
                annot.update()
            self.modify(do, [index])
        elif tool == "eraser":
            target = self._annot_at(page, pt)
            if target is None:
                return
            xref = target.xref
            self.modify(lambda: page.delete_annot(page.load_annot(xref)), [index])

    @staticmethod
    def _annot_at(page, pt):
        found = None
        for annot in page.annots():
            if annot.rect.contains(pt):
                found = annot      # last one = topmost
        return found

    def edit_annot_at(self, index, pt):
        page = self.doc[index]
        annot = self._annot_at(page, pt)
        if annot is None:
            return
        info = annot.info
        text, ok = QInputDialog.getMultiLineText(self, "Edit " + annot.type[1],
                                                 "Content:", info.get("content", ""))
        if not ok:
            return
        xref = annot.xref

        def do():
            a = page.load_annot(xref)
            a.set_info(content=text)
            a.update()
        self.modify(do, [index])

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
        self.doc.save(tmp, garbage=1, deflate=True)
        os.replace(tmp, path)
        self.path = path
        self.dirty = False
        self.documentChanged.emit()

    def close_doc(self):
        self.doc.close()
