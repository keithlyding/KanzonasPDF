"""On-page text editor for the Edit text tool.

Sits over the line being edited, in roughly the same font and size. Drag the top bar to
move the text, drag the corner grip to change the width (text wraps to it, in the PDF too).
Enter = done, Shift+Enter = new line, Esc = cancel, clicking elsewhere = done.
"""

from PySide6.QtCore import Qt, Signal, QEvent
from PySide6.QtGui import QFont, QFontMetricsF, QTextOption
from PySide6.QtWidgets import QFrame, QVBoxLayout, QLabel, QPlainTextEdit, QHBoxLayout

BAR_H = 18
PAD = 4


class _DragBar(QLabel):
    def __init__(self, editor):
        super().__init__("  ⠿ drag to move     Enter = done   Shift+Enter = new line   Esc = cancel")
        self.editor = editor
        self.setFixedHeight(BAR_H)
        self.setStyleSheet("background:#0078d7; color:white; font-size:9pt;")
        self.setCursor(Qt.SizeAllCursor)
        self._start = None

    def mousePressEvent(self, e):
        self._start = (e.globalPosition().toPoint(), self.editor.pos())

    def mouseMoveEvent(self, e):
        if self._start:
            g, p = self._start
            self.editor.move(p + e.globalPosition().toPoint() - g)

    def mouseReleaseEvent(self, e):
        self._start = None
        self.editor.text.setFocus()


class _Grip(QLabel):
    def __init__(self, editor):
        super().__init__("◢")
        self.editor = editor
        self.setCursor(Qt.SizeFDiagCursor)
        self.setStyleSheet("color:#0078d7;")
        self._start = None

    def mousePressEvent(self, e):
        self._start = (e.globalPosition().toPoint(), self.editor.size())

    def mouseMoveEvent(self, e):
        if self._start:
            g, s = self._start
            d = e.globalPosition().toPoint() - g
            self.editor.resize(max(60, s.width() + d.x()), max(BAR_H + 30, s.height() + d.y()))
            self.editor.resized_by_user = True

    def mouseReleaseEvent(self, e):
        self._start = None
        self.editor.text.setFocus()


class InlineEditor(QFrame):
    committed = Signal(str, float, float, object)   # text, dx px, dy px, wrap width px or None
    canceled = Signal()

    def __init__(self, parent, text_rect, text, family, pixel_size):
        """text_rect: QRectF of the line on the page widget (widget coords)."""
        super().__init__(parent)
        self.setFrameShape(QFrame.Box)
        self.setStyleSheet("InlineEditor { border: 1px solid #0078d7; background: white; }")
        self.resized_by_user = False
        self._done = False
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(_DragBar(self))
        self.text = QPlainTextEdit(text)
        f = QFont({"sans": "Arial", "serif": "Times New Roman", "mono": "Courier New"}[family])
        f.setPixelSize(max(6, int(round(pixel_size))))
        self.text.setFont(f)
        self.text.setFrameShape(QFrame.NoFrame)
        self.text.document().setDocumentMargin(0)
        self.text.setWordWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
        self.text.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        self.text.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.text.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.text.setStyleSheet("background: #fffbe6;")
        self.text.installEventFilter(self)
        lay.addWidget(self.text)
        # clicks on the bar / grip must not move keyboard focus to the page behind
        self.setFocusPolicy(Qt.ClickFocus)
        self.setFocusProxy(self.text)
        bottom = QHBoxLayout()
        bottom.setContentsMargins(0, 0, 0, 0)
        bottom.addStretch(1)
        bottom.addWidget(_Grip(self))
        lay.addLayout(bottom)

        fm = QFontMetricsF(f)
        lines = max(1, text.count("\n") + 1)
        width = max(text_rect.width(), max(fm.horizontalAdvance(t) for t in text.split("\n")))
        width += 2 * PAD + 12
        height = BAR_H + lines * fm.lineSpacing() + 2 * PAD + 16
        # keep the editor inside the page horizontally
        width = min(width, max(80, parent.width() - text_rect.x() + PAD))
        self.setGeometry(int(text_rect.x() - PAD), int(text_rect.y() - BAR_H - PAD),
                         int(width), int(height))
        self._start_pos = self.pos()
        self._start_width = self.width()
        self.text.textChanged.connect(self._grow)
        self.show()
        self.raise_()
        self.text.setFocus()
        self.text.selectAll()

    def _grow(self):
        """Widen as you type until the page's right edge (then wrap), and grow downward."""
        fm = QFontMetricsF(self.text.font())
        if not self.resized_by_user:
            need = max(fm.horizontalAdvance(t) for t in self.text.toPlainText().split("\n"))
            need = int(need + 2 * PAD + 12)
            limit = self.parentWidget().width() - self.x() - 4
            if need > self.width():
                self.resize(max(self.width(), min(need, limit)), self.height())
        lines = self.text.document().size().height()
        want = int(BAR_H + lines * fm.lineSpacing() + 2 * PAD + 18)
        if want > self.height():
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
        # Committing on focus-out made the move bar and resize grip end the edit.)
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
