"""View > Presentation (F5): the document's pages one at a time, each fitted to the whole
screen on black, for showing to an audience.

Next page: click, Space, Right / Down arrow, Page Down, Enter, N. Previous: right-click,
Backspace, Left / Up arrow, Page Up, P. Home / End: first / last page; a page number and
Enter goes there. B (or .) turns the screen black and W (or ,) white, until any key. L shows a
laser pointer: a red dot where the mouse is. Escape ends the presentation, back at the page
shown.

The pages are drawn here with PyMuPDF, fitted to the screen, the page shown and the next one
kept (the next one drawn while the current one is on screen), so a page turns at once."""

from collections import OrderedDict

import pymupdf
from PySide6.QtCore import Qt, QTimer, QPointF, QRectF, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap, QRadialGradient, QCursor
from PySide6.QtWidgets import QWidget

from .i18n import tr

KEEP = 4                # pages kept drawn


class Presentation(QWidget):
    finished = Signal(int)          # the page shown last (to go back to)

    NEXT = (Qt.Key_Space, Qt.Key_Right, Qt.Key_Down, Qt.Key_PageDown, Qt.Key_Return,
            Qt.Key_Enter, Qt.Key_N)
    PREV = (Qt.Key_Backspace, Qt.Key_Left, Qt.Key_Up, Qt.Key_PageUp, Qt.Key_P)

    def __init__(self, view, page=0, screen=None):
        super().__init__(None, Qt.Window | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setWindowTitle(tr("Presentation"))
        self.view = view
        self.doc = view.doc
        self.page = max(0, min(page, self.doc.page_count - 1))
        self.blank = None           # None, "black" or "white"
        self.laser = False
        self._typed = ""            # a page number being typed
        self._cache = OrderedDict()
        self._laser_at = None
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setStyleSheet("background: black;")
        self._hide_timer = QTimer(self, singleShot=True, interval=2000)
        self._hide_timer.timeout.connect(self._hide_cursor)
        self._ahead = QTimer(self, singleShot=True, interval=30)
        self._ahead.timeout.connect(self._draw_ahead)
        if screen is not None:
            self.setScreen(screen)
            self.setGeometry(screen.geometry())
        view.destroyed.connect(self.close)
        # (the document edited in the window meanwhile, a second screen showing it: the
        # pages drawn again as they are now)
        view.documentChanged.connect(self._doc_changed)
        view.structureChanged.connect(self._doc_changed)

    def start(self):
        self.showFullScreen()
        self.raise_()
        self.activateWindow()
        self.setFocus()
        self._hide_timer.start()

    # ---- pages ---------------------------------------------------------------------
    def _pixmap(self, index):
        dpr = self.devicePixelRatioF()
        size = (self.width(), self.height(), dpr)
        key = (index, size)
        pm = self._cache.get(key)
        if pm is not None:
            self._cache.move_to_end(key)
            return pm
        page = self.doc[index]
        r = page.rect
        s = min(self.width() / max(r.width, 1), self.height() / max(r.height, 1)) * dpr
        try:
            pix = page.get_pixmap(matrix=pymupdf.Matrix(s, s), alpha=False,
                                  annots=bool(getattr(self.view, "show_markups", True)))
        except Exception:
            return None
        img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888)
        pm = QPixmap.fromImage(img.copy())
        pm.setDevicePixelRatio(dpr)
        self._cache[key] = pm
        while len(self._cache) > KEEP:
            self._cache.popitem(last=False)
        return pm

    def _doc_changed(self):
        self._cache.clear()
        if not self.doc.is_closed:
            self.page = max(0, min(self.page, self.doc.page_count - 1))
        self.update()

    def _draw_ahead(self):
        if self.page + 1 < self.doc.page_count and not self.doc.is_closed:
            self._pixmap(self.page + 1)

    def go(self, index):
        index = max(0, min(index, self.doc.page_count - 1))
        if index != self.page:
            self.page = index
        self.blank = None
        self.update()
        self._ahead.start()

    def paintEvent(self, e):
        p = QPainter(self)
        if self.blank:
            p.fillRect(self.rect(), Qt.black if self.blank == "black" else Qt.white)
            return
        p.fillRect(self.rect(), Qt.black)
        if self.doc.is_closed or self.page >= self.doc.page_count:
            return
        pm = self._pixmap(self.page)
        if pm is not None:
            w = pm.width() / pm.devicePixelRatio()
            h = pm.height() / pm.devicePixelRatio()
            p.drawPixmap(QPointF((self.width() - w) / 2, (self.height() - h) / 2), pm)
        if self.laser and self._laser_at is not None:
            c = self._laser_at
            g = QRadialGradient(c, 14)
            g.setColorAt(0, QColor(255, 40, 40, 255))
            g.setColorAt(0.35, QColor(255, 0, 0, 220))
            g.setColorAt(1, QColor(255, 0, 0, 0))
            p.setRenderHint(QPainter.Antialiasing)
            p.setPen(Qt.NoPen)
            p.setBrush(g)
            p.drawEllipse(c, 14, 14)

    # ---- keys and mouse ----------------------------------------------------------------
    def keyPressEvent(self, e):
        k = e.key()
        if k == Qt.Key_Escape:
            self.close()
            return
        if self.blank and k not in (Qt.Key_B, Qt.Key_W, Qt.Key_Period, Qt.Key_Comma):
            self.blank = None               # (any key brings the page back)
            self.update()
            return
        if Qt.Key_0 <= k <= Qt.Key_9:
            self._typed += chr(k)
            return
        if k in (Qt.Key_Return, Qt.Key_Enter) and self._typed:
            n, self._typed = int(self._typed), ""
            self.go(n - 1)
            return
        self._typed = ""
        if k in (Qt.Key_B, Qt.Key_Period):
            self.blank = None if self.blank == "black" else "black"
            self.update()
        elif k in (Qt.Key_W, Qt.Key_Comma):
            self.blank = None if self.blank == "white" else "white"
            self.update()
        elif k == Qt.Key_L:
            self.laser = not self.laser
            self._laser_at = QPointF(self.mapFromGlobal(QCursor.pos())) if self.laser else None
            self.setCursor(Qt.BlankCursor if self.laser else Qt.ArrowCursor)
            self.update()
        elif k in self.NEXT:
            self.go(self.page + 1)
        elif k in self.PREV:
            self.go(self.page - 1)
        elif k == Qt.Key_Home:
            self.go(0)
        elif k == Qt.Key_End:
            self.go(self.doc.page_count - 1)
        else:
            super().keyPressEvent(e)

    def mousePressEvent(self, e):
        if self.blank:
            self.blank = None
            self.update()
        elif e.button() == Qt.LeftButton:
            self.go(self.page + 1)
        elif e.button() == Qt.RightButton:
            self.go(self.page - 1)

    def wheelEvent(self, e):
        dy = e.angleDelta().y()
        if dy:
            self.go(self.page + (1 if dy < 0 else -1))

    def mouseMoveEvent(self, e):
        if self.laser:
            old = self._laser_at
            self._laser_at = e.position()
            for c in (old, self._laser_at):
                if c is not None:
                    self.update(QRectF(c.x() - 16, c.y() - 16, 32, 32).toAlignedRect())
            return
        self.unsetCursor()
        self._hide_timer.start()

    def _hide_cursor(self):
        if not self.laser:
            self.setCursor(Qt.BlankCursor)

    def closeEvent(self, e):
        self._cache.clear()
        self.finished.emit(self.page)
        super().closeEvent(e)
