"""On-page text editor for the Edit text and Add text tools.

Opens right on the line being edited, in roughly the same font and size, with the cursor where
you clicked: no pop-up, just a dashed outline with handles, like a selected object. Drag the
outline to move the text, drag a handle to change the width the text wraps to (in the PDF
too). Enter = done, Shift+Enter = new line, Esc = cancel, clicking elsewhere = done.
"""

from PySide6.QtCore import Qt, Signal, QEvent, QRect
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPen, QTextOption
from PySide6.QtWidgets import QFrame, QVBoxLayout, QPlainTextEdit

MARGIN = 7          # the outline you grab to move the text (px around the text)
HANDLE = 7          # handle squares on the corners and side middles


class InlineEditor(QFrame):
    committed = Signal(str, float, float, object)   # text, dx px, dy px, wrap width px or None
    canceled = Signal()

    def __init__(self, parent, text_rect, text, family, pixel_size, click=None):
        """text_rect: QRectF of the line on the page widget (widget coords). click: the point
        clicked (widget coords), where the cursor goes; None selects all the text."""
        super().__init__(parent)
        self.setFrameShape(QFrame.NoFrame)
        self.setStyleSheet("InlineEditor { background: transparent; }")
        self.setMouseTracking(True)
        self.setToolTip("Drag the outline to move the text, drag a handle to change its width.\n"
                        "Enter = done, Shift+Enter = new line, Esc = cancel")
        self.resized_by_user = False
        self._done = False
        self._drag = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(MARGIN, MARGIN, MARGIN, MARGIN)
        lay.setSpacing(0)
        self.text = QPlainTextEdit(text)
        # a hint ("sans" / "serif" / "mono") from the line edited, or a family picked in Properties
        f = QFont({"sans": "Arial", "serif": "Times New Roman", "mono": "Courier New"}.get(family, family))
        f.setPixelSize(max(6, int(round(pixel_size))))
        self.text.setFont(f)
        self.text.setFrameShape(QFrame.NoFrame)
        self.text.document().setDocumentMargin(0)
        self.text.setWordWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
        self.text.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        self.text.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.text.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        # white like the page, so the line reads as edited in place (it covers the old text)
        self.text.setStyleSheet("background: white;")
        self.text.installEventFilter(self)
        lay.addWidget(self.text)
        self.setFocusPolicy(Qt.ClickFocus)
        self.setFocusProxy(self.text)

        fm = QFontMetricsF(f)
        lines = max(1, text.count("\n") + 1)
        width = max(text_rect.width(), max(fm.horizontalAdvance(t) for t in text.split("\n")))
        width += 2 * MARGIN + 6
        height = lines * fm.lineSpacing() + 2 * MARGIN + 4
        # keep the editor inside the page horizontally
        width = min(width, max(80, parent.width() - text_rect.x() + MARGIN))
        self.setGeometry(int(text_rect.x() - MARGIN), int(text_rect.y() - MARGIN),
                         int(width), int(height))
        self._start_pos = self.pos()
        self._start_width = self.width()
        self.text.textChanged.connect(self._grow)
        self.show()
        self.raise_()
        self.text.setFocus()
        if click is not None:
            c = self.text.cursorForPosition(self.text.mapFrom(parent, click.toPoint()))
            self.text.setTextCursor(c)
        else:
            self.text.selectAll()

    # ---- outline and handles ------------------------------------------------------
    def _handles(self):
        """{name: QRect} of the handles: corners and the middles of the left and right sides
        (the width is what changes; the height follows the text)."""
        w, h, s = self.width(), self.height(), HANDLE
        xs = {"l": 0, "r": w - s}
        ys = {"t": 0, "m": (h - s) // 2, "b": h - s}
        return {v + hz: QRect(xs[hz], ys[v], s, s)
                for v in ("t", "m", "b") for hz in ("l", "r")}

    def paintEvent(self, e):
        p = QPainter(self)
        p.setPen(QPen(QColor(0, 120, 215), 1, Qt.DashLine))
        p.drawRect(QRect(HANDLE // 2, HANDLE // 2, self.width() - HANDLE, self.height() - HANDLE))
        p.setPen(QPen(QColor(0, 120, 215), 1))
        p.setBrush(Qt.white)
        for r in self._handles().values():
            p.drawRect(r.adjusted(0, 0, -1, -1))
        p.end()

    def _zone(self, pos):
        for name, r in self._handles().items():
            if r.adjusted(-2, -2, 2, 2).contains(pos):
                return name
        return "move"

    def mouseMoveEvent(self, e):
        pos = e.position().toPoint()
        if self._drag is None:
            z = self._zone(pos)
            self.setCursor(Qt.SizeAllCursor if z == "move" else Qt.SizeHorCursor)
            return
        zone, g0, geo = self._drag
        d = e.globalPosition().toPoint() - g0
        if zone == "move":
            self.move(geo.topLeft() + d)
            return
        x, w = geo.x(), geo.width()
        if zone.endswith("r"):
            w = max(60, geo.width() + d.x())
        else:                               # left side: the left edge follows the pointer
            w = max(60, geo.width() - d.x())
            x = geo.right() + 1 - w
        self.setGeometry(x, geo.y(), w, self.height())
        self.resized_by_user = True
        self._grow()

    def mousePressEvent(self, e):
        if e.button() != Qt.LeftButton:
            return super().mousePressEvent(e)
        self._drag = (self._zone(e.position().toPoint()), e.globalPosition().toPoint(),
                      self.geometry())

    def mouseReleaseEvent(self, e):
        self._drag = None
        self.text.setFocus()

    # ---- typing ---------------------------------------------------------------------
    def _grow(self):
        """Widen as you type until the page's right edge (then wrap), and grow downward."""
        fm = QFontMetricsF(self.text.font())
        if not self.resized_by_user:
            need = max(fm.horizontalAdvance(t) for t in self.text.toPlainText().split("\n"))
            need = int(need + 2 * MARGIN + 6)
            limit = self.parentWidget().width() - self.x() - 4
            if need > self.width():
                self.resize(max(self.width(), min(need, limit)), self.height())
        lines = self.text.document().size().height()
        want = int(lines * fm.lineSpacing() + 2 * MARGIN + 4)
        if want != self.height():
            self.resize(self.width(), want)
        # wrapping in the PDF follows the editor, so the start width must track auto-growth
        if not self.resized_by_user:
            self._start_width = self.width()

    def eventFilter(self, obj, e):
        if obj is self.text:
            if e.type() == QEvent.KeyPress:
                if e.key() in (Qt.Key_Return, Qt.Key_Enter) and not (e.modifiers() & Qt.ShiftModifier):
                    self.commit()
                    return True
                if e.key() == Qt.Key_Escape:
                    self.cancel()
                    return True
        # (No commit on focus loss: the page commits the edit when you click elsewhere on it.
        # Committing on focus-out made moving and resizing end the edit.)
        return super().eventFilter(obj, e)

    def commit(self):
        if self._done:
            return
        self._done = True
        moved = self.pos() - self._start_pos
        # Wrap in the PDF exactly when the user resized the box or the text wraps on screen.
        wrap = self.text.viewport().width() - 2 if (self.resized_by_user or self._wraps()) else None
        self.hide()
        self.committed.emit(self.text.toPlainText(), float(moved.x()), float(moved.y()), wrap)
        self.deleteLater()

    def _wraps(self):
        """QPlainTextEdit's document height is in visual lines; more lines than
        paragraphs means some paragraph wrapped."""
        return self.text.document().size().height() > self.text.blockCount()

    def cancel(self):
        if self._done:
            return
        self._done = True
        self.hide()
        self.canceled.emit()
        self.deleteLater()
