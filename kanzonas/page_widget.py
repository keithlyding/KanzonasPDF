"""A single rendered PDF page inside the scrolling document view."""

import pymupdf
from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QPainter, QImage, QPixmap, QColor, QPen, QPainterPath
from PySide6.QtWidgets import QWidget

DRAG_TOOLS = {"select", "highlight", "underline", "strikeout", "textbox",
              "rect", "ellipse", "line", "arrow", "eraser"}


class PageWidget(QWidget):
    def __init__(self, view, index):
        super().__init__()
        self.view = view
        self.index = index
        self._pix = None
        self._drag_start = None
        self._drag_now = None
        self._ink = []
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

        hits = self.view.search_hits.get(self.index)
        if hits:
            page = self.view.doc[self.index]
            cur = self.view.current_hit()
            for i, r in enumerate(hits):
                active = cur == (self.index, i)
                color = QColor(255, 120, 0, 120) if active else QColor(255, 230, 0, 90)
                p.fillRect(self.to_screen(r, page), color)

        tool = self.view.tool
        if self._drag_start is not None and self._drag_now is not None:
            dashed = tool in ("select", "eraser", "highlight", "underline", "strikeout")
            pen = QPen(QColor(220, 0, 0) if tool == "eraser" else self.view.color, 1.5,
                       Qt.DashLine if dashed else Qt.SolidLine)
            p.setPen(pen)
            p.setRenderHint(QPainter.Antialiasing)
            if tool in ("line", "arrow"):
                p.drawLine(self._drag_start, self._drag_now)
            elif tool == "ellipse":
                p.drawEllipse(QRectF(self._drag_start, self._drag_now).normalized())
            else:
                p.drawRect(QRectF(self._drag_start, self._drag_now).normalized())
        if len(self._ink) > 1:
            p.setRenderHint(QPainter.Antialiasing)
            p.setPen(QPen(self.view.color, 2))
            path = QPainterPath(self._ink[0])
            for pt in self._ink[1:]:
                path.lineTo(pt)
            p.drawPath(path)

        if self.view.current_page() == self.index and self.view.page_count() > 1:
            p.setPen(QPen(QColor(0, 120, 215), 1))
            p.drawRect(self.rect().adjusted(0, 0, -1, -1))

    # ---- mouse ----------------------------------------------------------
    def mousePressEvent(self, e):
        if e.button() != Qt.LeftButton:
            return super().mousePressEvent(e)
        tool = self.view.tool
        pos = e.position()
        if tool == "hand":
            self.view.begin_pan(e.globalPosition())
        elif tool in DRAG_TOOLS:
            self._drag_start = pos
            self._drag_now = pos
        elif tool == "ink":
            self._ink = [pos]
        elif tool == "note":
            self.view.apply_point_tool(self.index, tool, self.to_pdf(pos))

    def mouseMoveEvent(self, e):
        pos = e.position()
        if self.view.tool == "hand":
            self.view.continue_pan(e.globalPosition())
        elif self._drag_start is not None:
            self._drag_now = pos
            self.update()
        elif self._ink:
            self._ink.append(pos)
            self.update()

    def mouseReleaseEvent(self, e):
        if e.button() != Qt.LeftButton:
            return
        if self.view.tool == "hand":
            self.view.end_pan()
        elif self._drag_start is not None:
            a, b = self._drag_start, self._drag_now
            self._drag_start = self._drag_now = None
            self.update()
            self.view.apply_drag_tool(self.index, self.view.tool, self.to_pdf(a), self.to_pdf(b),
                                      (b - a).manhattanLength() < 4)
        elif self._ink:
            pts = [self.to_pdf(p) for p in self._ink]
            self._ink = []
            self.update()
            if len(pts) > 1:
                self.view.apply_ink(self.index, pts)

    def mouseDoubleClickEvent(self, e):
        if self.view.tool in ("select", "hand"):
            self.view.edit_annot_at(self.index, self.to_pdf(e.position()))
