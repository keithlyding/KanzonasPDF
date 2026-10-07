"""A single rendered PDF page inside the scrolling document view.

Handles drawing (page image, search hits, comment boxes, selection handles, previews)
and turns mouse input into calls on the DocumentView, which owns all PDF edits.
"""

import pymupdf
from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import (QPainter, QImage, QPixmap, QColor, QPen, QPainterPath,
                           QFontMetrics, QBrush)
from PySide6.QtWidgets import QWidget, QToolTip

from . import annotations as A

TEXT_TOOLS = {"select", "highlight", "underline", "strikeout", "comment"}
SHAPE_TOOLS = {"textbox", "rect", "ellipse", "line", "arrow", "eraser"}
HANDLE = 7          # handle size in px
CARD_W = 190        # comment box width in px


class PageWidget(QWidget):
    def __init__(self, view, index):
        super().__init__()
        self.view = view
        self.index = index
        self._pix = None
        self._drag_start = None     # shape tools / box selection
        self._drag_now = None
        self._text_sel = None       # (mode, words) while selecting text
        self._ink = []
        self._hover = None          # edit-text hover rect
        self._edit = None           # dragging a selected annotation
        self._cards = []            # [(QRectF, xref)] comment boxes drawn last paint
        self.setMouseTracking(True)
        self.setAttribute(Qt.WA_OpaquePaintEvent)
        self.update_size()

    # ---- geometry -------------------------------------------------------
    def update_size(self):
        r = self.view.page_rects[self.index]
        z = self.view.zoom
        self.setFixedSize(max(1, int(r.width * z)), max(1, int(r.height * z)))
        self._pix = None

    def invalidate(self):
        self._pix = None
        self.update()

    def drop_cache(self):
        self._pix = None

    def to_pdf(self, pos):
        """Widget position -> unrotated PDF point (what PyMuPDF expects)."""
        page = self.view.doc[self.index]
        z = self.view.zoom
        return pymupdf.Point(pos.x() / z, pos.y() / z) * page.derotation_matrix

    def to_screen(self, rect, page=None):
        """Unrotated PDF rect -> widget QRectF."""
        page = page or self.view.doc[self.index]
        r = pymupdf.Rect(rect) * page.rotation_matrix
        z = self.view.zoom
        return QRectF(r.x0 * z, r.y0 * z, r.width * z, r.height * z)

    def to_screen_pt(self, pt, page=None):
        page = page or self.view.doc[self.index]
        q = pymupdf.Point(pt) * page.rotation_matrix
        return QPointF(q.x * self.view.zoom, q.y * self.view.zoom)

    # ---- painting -------------------------------------------------------
    def _render(self):
        page = self.view.doc[self.index]
        dpr = self.devicePixelRatioF()
        s = self.view.zoom * dpr
        pm = page.get_pixmap(matrix=pymupdf.Matrix(s, s), alpha=False, annots=True)
        img = QImage(pm.samples, pm.width, pm.height, pm.stride,
                     QImage.Format_RGB888).copy()
        pix = QPixmap.fromImage(img)
        pix.setDevicePixelRatio(dpr)
        self._pix = pix

    def paintEvent(self, event):
        p = QPainter(self)
        if self._pix is None:
            try:
                self._render()
            except Exception:
                p.fillRect(self.rect(), Qt.white)
                return
        p.drawPixmap(0, 0, self._pix)
        page = self.view.doc[self.index]
        p.setRenderHint(QPainter.Antialiasing)

        hits = self.view.search_hits.get(self.index)
        if hits:
            cur = self.view.current_hit()
            for i, r in enumerate(hits):
                active = cur == (self.index, i)
                color = QColor(255, 120, 0, 120) if active else QColor(255, 230, 0, 90)
                p.fillRect(self.to_screen(r, page), color)

        self._paint_comment_cards(p, page)

        tool = self.view.tool
        # live text selection: shows exactly what will be copied / marked up
        if self._text_sel is not None:
            mode, words = self._text_sel
            if tool == "select":
                fill = QColor(0, 120, 215, 80)
            else:
                fill = QColor(self.view.tool_color(tool))
                fill.setAlpha(110)
            for r in self.view.line_rects(words):
                p.fillRect(self.to_screen(r, page), fill)
            if mode == "box" and self._drag_start is not None:
                p.setPen(QPen(QColor(0, 120, 215), 1, Qt.DashLine))
                p.drawRect(QRectF(self._drag_start, self._drag_now).normalized())

        if self._drag_start is not None and self._drag_now is not None and tool in SHAPE_TOOLS:
            if tool == "eraser":
                pen = QPen(QColor(220, 0, 0), 1.5, Qt.DashLine)
            else:
                pen = QPen(self.view.tool_color(tool),
                           max(1.0, float(self.view.tool_props(tool).get("width", 1)) * self.view.zoom))
            p.setPen(pen)
            if tool in ("line", "arrow"):
                p.drawLine(self._drag_start, self._drag_now)
            elif tool == "ellipse":
                p.drawEllipse(QRectF(self._drag_start, self._drag_now).normalized())
            else:
                p.drawRect(QRectF(self._drag_start, self._drag_now).normalized())

        if self._hover is not None and tool == "edittext":
            p.setPen(QPen(QColor(0, 120, 215), 1, Qt.DashLine))
            p.drawRect(self.to_screen(self._hover).adjusted(-2, -2, 2, 2))

        if len(self._ink) > 1:
            p.setPen(QPen(self.view.tool_color("ink"),
                          max(1.0, float(self.view.tool_props("ink").get("width", 2)) * self.view.zoom),
                          Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            path = QPainterPath(self._ink[0])
            for pt in self._ink[1:]:
                path.lineTo(pt)
            p.drawPath(path)

        self._paint_selection(p, page)

        if self.view.current_page() == self.index and self.view.page_count() > 1:
            p.setPen(QPen(QColor(0, 120, 215), 1))
            p.setBrush(Qt.NoBrush)
            p.drawRect(self.rect().adjusted(0, 0, -1, -1))

    def _paint_comment_cards(self, p, page):
        """Adobe-style note boxes beside commented text (drawn by us, not in the PDF)."""
        self._cards = []
        if not self.view.show_comment_boxes:
            return
        fm = QFontMetrics(self.font())
        for anchor, text, xref in self.view.comment_cards(self.index):
            a = self.to_screen(anchor, page)
            body = text if text.strip() else "(empty note)"
            br = fm.boundingRect(0, 0, CARD_W - 12, 2000, Qt.TextWordWrap, body)
            h = min(br.height(), fm.lineSpacing() * 6) + 10
            x = a.right() + 14
            if x + CARD_W > self.width():
                x = max(2, self.width() - CARD_W - 2)
                y = a.bottom() + 6
            else:
                y = a.top()
            card = QRectF(x, y, CARD_W, h)
            sel = self.view.selection == (self.index, xref)
            p.setPen(QPen(QColor(180, 150, 0), 1, Qt.DotLine))
            p.drawLine(QPointF(a.right(), a.center().y()), QPointF(card.left(), card.top() + 8))
            p.setPen(QPen(QColor(0, 120, 215) if sel else QColor(190, 160, 0), 2 if sel else 1))
            p.setBrush(QColor(255, 248, 196, 235))
            p.drawRoundedRect(card, 4, 4)
            p.setPen(Qt.black)
            p.drawText(card.adjusted(6, 5, -6, -5), Qt.TextWordWrap, body)
            self._cards.append((card, xref))
        p.setBrush(Qt.NoBrush)

    def _selected_here(self):
        sel = self.view.selection
        if sel is None or sel[0] != self.index or self.view.selected_model is None:
            return None
        return self.view.selected_model

    def _handles(self, model):
        """{id: QRectF} handle squares for the selected annotation."""
        h = HANDLE
        if model["kind"] in ("line", "arrow"):
            out = {}
            for i, q in enumerate(model["points"]):
                s = self.to_screen_pt(q)
                out[f"p{i}"] = QRectF(s.x() - h / 2, s.y() - h / 2, h, h)
            return out
        if not A.movable(model) or model["kind"] == "note":
            return {}
        r = self.to_screen(A.bounds(model))
        pts = {"tl": r.topLeft(), "tr": r.topRight(), "bl": r.bottomLeft(),
               "br": r.bottomRight(), "t": QPointF(r.center().x(), r.top()),
               "b": QPointF(r.center().x(), r.bottom()), "l": QPointF(r.left(), r.center().y()),
               "r": QPointF(r.right(), r.center().y())}
        return {k: QRectF(v.x() - h / 2, v.y() - h / 2, h, h) for k, v in pts.items()}

    def _paint_selection(self, p, page):
        model = self._selected_here()
        if model is None:
            return
        shown = self._edit["preview"] if self._edit and self._edit.get("preview") else model
        blue = QColor(0, 120, 215)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(blue, 1, Qt.DashLine))
        if shown["kind"] in ("line", "arrow"):
            a, b = (self.to_screen_pt(q, page) for q in shown["points"])
            p.drawLine(a, b)
        else:
            p.drawRect(self.to_screen(A.bounds(shown), page).adjusted(-3, -3, 3, 3))
        if not self._edit:
            p.setPen(QPen(blue, 1))
            p.setBrush(Qt.white)
            for r in self._handles(model).values():
                p.drawRect(r)
            p.setBrush(Qt.NoBrush)

    # ---- mouse ----------------------------------------------------------
    def _card_at(self, pos):
        for r, xref in self._cards:
            if r.contains(pos):
                return xref
        return None

    def mousePressEvent(self, e):
        if e.button() != Qt.LeftButton:
            return super().mousePressEvent(e)
        self.view.setFocus()
        tool = self.view.tool
        pos = e.position()
        pdf = self.to_pdf(pos)

        if tool == "hand":
            self.view.begin_pan(e.globalPosition())
            return
        if tool == "select":
            model = self._selected_here()
            if model is not None:
                for hid, r in self._handles(model).items():
                    if r.adjusted(-3, -3, 3, 3).contains(pos):
                        self._edit = {"mode": hid, "start": pos, "model": model, "preview": None}
                        return
            card = self._card_at(pos)
            if card is not None:
                self.view.select_xref(self.index, card)
                return
            if self.view.select_annot_at(self.index, pdf):
                model = self._selected_here()
                if model is not None and A.movable(model):
                    self._edit = {"mode": "move", "start": pos, "model": model, "preview": None}
                return
            self.view.clear_selection()
        if tool in TEXT_TOOLS:
            self._drag_start = self._drag_now = pos
            self._text_sel = self.view.text_selection(self.index, pdf, pdf)
            self.update()
        elif tool in SHAPE_TOOLS:
            self._drag_start = self._drag_now = pos
        elif tool == "ink":
            self._ink = [pos]
        elif tool == "edittext":
            self._hover = None
            self.update()
            self.view.edit_text_at(self.index, pdf)
        elif tool == "note":
            self.view.apply_point_tool(self.index, tool, pdf)

    def _edit_preview(self, pos):
        ed = self._edit
        model = ed["model"]
        if ed["mode"] == "move":
            delta = self.to_pdf(pos) - self.to_pdf(ed["start"])
            return A.moved(model, delta)
        if ed["mode"] in ("p0", "p1"):
            return A.with_endpoint(model, int(ed["mode"][1]), self.to_pdf(pos))
        r = self.to_screen(A.bounds(model))
        d = pos - ed["start"]
        x0, y0, x1, y1 = r.left(), r.top(), r.right(), r.bottom()
        if "l" in ed["mode"]:
            x0 += d.x()
        if "r" in ed["mode"]:
            x1 += d.x()
        if "t" in ed["mode"]:
            y0 += d.y()
        if "b" in ed["mode"]:
            y1 += d.y()
        new = pymupdf.Rect(self.to_pdf(QPointF(x0, y0)), self.to_pdf(QPointF(x1, y1))).normalize()
        if new.width < 2 or new.height < 2:
            return model
        return A.resized(model, new)

    def mouseMoveEvent(self, e):
        pos = e.position()
        tool = self.view.tool
        if not e.buttons():
            if tool == "edittext":
                r = self.view.text_line_rect(self.index, self.to_pdf(pos))
                if r != self._hover:
                    self._hover = r
                    self.update()
            elif tool == "select":
                self._update_select_cursor(pos)
            return
        if tool == "hand":
            self.view.continue_pan(e.globalPosition())
        elif self._edit is not None:
            if (pos - self._edit["start"]).manhattanLength() >= 3:
                self._edit["preview"] = self._edit_preview(pos)
                self.update()
        elif self._text_sel is not None:
            self._drag_now = pos
            self._text_sel = self.view.text_selection(self.index, self.to_pdf(self._drag_start),
                                                      self.to_pdf(pos))
            self.update()
        elif self._drag_start is not None:
            self._drag_now = pos
            self.update()
        elif self._ink:
            self._ink.append(pos)
            self.update()

    def _update_select_cursor(self, pos):
        model = self._selected_here()
        if model is not None:
            for hid, r in self._handles(model).items():
                if r.adjusted(-3, -3, 3, 3).contains(pos):
                    self.setCursor(Qt.SizeFDiagCursor if hid in ("tl", "br") else
                                   Qt.SizeBDiagCursor if hid in ("tr", "bl") else
                                   Qt.SizeVerCursor if hid in ("t", "b") else
                                   Qt.SizeHorCursor if hid in ("l", "r") else Qt.CrossCursor)
                    return
        over = self.view.annot_at(self.index, self.to_pdf(pos)) is not None or \
            self._card_at(pos) is not None
        if over:
            self.setCursor(Qt.SizeAllCursor)
            card = self._card_at(pos)
            if card is None:
                tip = self.view.annot_tooltip(self.index, self.to_pdf(pos))
                if tip:
                    QToolTip.showText(self.mapToGlobal(pos.toPoint()), tip, self)
        else:
            self.unsetCursor()

    def mouseReleaseEvent(self, e):
        if e.button() != Qt.LeftButton:
            return
        tool = self.view.tool
        pos = e.position()
        if tool == "hand":
            self.view.end_pan()
        elif self._edit is not None:
            ed, self._edit = self._edit, None
            preview = ed.get("preview")
            self.update()
            if preview is not None:
                self.view.commit_model(self.index, self.view.selection[1], preview)
        elif self._text_sel is not None:
            a, b = self._drag_start, pos
            self._text_sel = None
            self._drag_start = self._drag_now = None
            self.update()
            if (b - a).manhattanLength() >= 3:
                self.view.apply_text_tool(self.index, tool, self.to_pdf(a), self.to_pdf(b))
        elif self._drag_start is not None:
            a, b = self._drag_start, self._drag_now
            self._drag_start = self._drag_now = None
            self.update()
            self.view.apply_drag_tool(self.index, tool, self.to_pdf(a), self.to_pdf(b),
                                      (b - a).manhattanLength() < 4)
        elif self._ink:
            pts = [self.to_pdf(p) for p in self._ink]
            self._ink = []
            self.update()
            if len(pts) > 1:
                self.view.apply_ink(self.index, pts)

    def mouseDoubleClickEvent(self, e):
        if self.view.tool in ("select", "hand"):
            card = self._card_at(e.position())
            if card is not None:
                self.view.edit_annot_text(self.index, card)
            else:
                self.view.edit_annot_at(self.index, self.to_pdf(e.position()))

    def leaveEvent(self, e):
        if self._hover is not None:
            self._hover = None
            self.update()
