"""The page's drawing scale where it can't be missed: a large label on the Measure tab and a
bold one in the status bar (red "Scale not set" when the page has none), both opening Set
scale when clicked; and the graphic scale bar drawn on scaled pages (View > Show scale bar),
on screen only: it is never printed, exported or saved.

The bar is a small picture made once per page, zoom and look and kept by the view
(DocumentView.scale_bar_pixmap), so a repaint only copies it."""

from PySide6.QtCore import Qt, QPointF, QRectF, QSize, Signal
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QLabel, QSizePolicy, QToolButton, QVBoxLayout, QWidget)

from . import measure as M
from .i18n import tr

BAR_MARGIN = 12             # from the page's bottom left corner, pixels
BAR_MAX = 280               # the bar's longest length, pixels (and 45% of the page's width)
BAR_MIN = 60                # pages shown smaller than this get no bar


def not_set_color():
    from . import theme
    return "#ff6b6b" if theme.is_dark() else "#c62828"


def short_text(scale):
    """The scale as the Measure tab shows it: its label (1/4" = 1'-0", 1:100), or
    'Scale not set'. scale: measure.get_scale's tuple."""
    m_per_pt, _unit, label, ok = scale
    if not ok:
        return tr("Scale not set")
    label = (label or "").strip()
    if not label:
        label = f"1:{m_per_pt / M.PT_M:.4g}"
    return label


class ScaleStatusLabel(QLabel):
    """The status bar's scale: bold, red while the page has none; a click opens Set scale."""
    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)
        self._state = None

    def show_scale(self, text, ok, tip):
        state = (text, ok, tip, not_set_color())
        if state == self._state:
            return                      # (a style sheet set again restyles the status bar)
        self._state = state
        self.setText(text)
        self.setToolTip(tip)
        self.setStyleSheet("QLabel { font-weight: bold; }" if ok or not text else
                           "QLabel { font-weight: bold; color: %s; }" % not_set_color())

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self.rect().contains(e.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(e)


class ScalePanel(QWidget):
    """The Measure tab's 'Page scale' group: the current page's scale in large type (a button
    that opens Set scale) above the Show scale bar switch."""

    def __init__(self, set_scale_action, scale_bar_action, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.button = QToolButton()
        self.button.setAutoRaise(True)
        self.button.setToolButtonStyle(Qt.ToolButtonTextOnly)
        f = QFont(self.button.font())
        f.setBold(True)
        f.setPointSizeF(f.pointSizeF() * 1.25)
        self.button.setFont(f)
        self.button.setFixedHeight(24)
        self.button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.button.setCursor(Qt.PointingHandCursor)
        self.button.clicked.connect(set_scale_action.trigger)
        self.bar = QToolButton()
        self.bar.setDefaultAction(scale_bar_action)
        self.bar.setAutoRaise(True)
        self.bar.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.bar.setIconSize(QSize(16, 16))
        self.bar.setFixedHeight(20)
        self.bar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        lay.addWidget(self.button)
        lay.addWidget(self.bar)
        # one width whatever the page's scale, so the tab doesn't shift from page to page:
        # room for 'Scale not set' and the usual labels; a longer one is elided (its tool
        # tip has it whole)
        fm = self.button.fontMetrics()
        self._text_w = max(fm.horizontalAdvance(tr("Scale not set")),
                           fm.horizontalAdvance('1-1/2" = 1\'-0"'))
        self.setFixedWidth(max(self._text_w + 16, self.bar.sizeHint().width()))
        self._state = None
        self.show_scale(None, "")

    def show_scale(self, scale, tip):
        """scale: measure.get_scale's tuple for the current page, None with no document."""
        text = short_text(scale) if scale is not None else tr("Scale not set")
        ok = scale is None or scale[3]
        state = (text, ok, tip, not_set_color(), scale is None)
        if state == self._state:
            return
        self._state = state
        fm = self.button.fontMetrics()
        self.button.setText(fm.elidedText(text, Qt.ElideRight, self._text_w).replace("&", "&&"))
        self.button.setToolTip(tip)
        self.button.setEnabled(scale is not None)
        self.button.setStyleSheet("" if ok else "QToolButton { color: %s; }" % not_set_color())


# ---- the graphic scale bar ------------------------------------------------------------------
def bar_pixmap(m_per_pt, unit, zoom, dpr, page_px, night=False, font=None):
    """The scale bar for a page with this scale shown at zoom (screen pixels per PDF point),
    page_px wide: alternating black and white segments with round numbers above them, on a
    plate of its own so it reads on light and dark drawings (dark in night mode). None when
    the page is shown too small for one."""
    max_px = min(BAR_MAX, page_px * 0.45)
    if max_px < BAR_MIN:
        return None
    bar = M.scale_bar(m_per_pt, unit, zoom, max_px)
    if bar is None:
        return None
    seg, labels = bar
    n = len(labels) - 1
    f = QFont(font) if font is not None else QFont()
    f.setPointSizeF(max(6.5, f.pointSizeF() * 0.9))
    fm = QFontMetricsF(f)
    widths = [fm.horizontalAdvance(t) for t in labels]
    # every label when they fit side by side, else every other one, else the ends
    step = 1
    while step < n and any(seg * step < (widths[i] + widths[min(n, i + step)]) / 2 + 6
                           for i in range(0, n, step)):
        step *= 2
    shown = [i for i in range(0, n + 1, step)]
    if shown[-1] != n:
        shown[-1] = n                   # (the end, with the unit, always)
    pad, bar_h, gap = 6.0, 7.0, 2.0
    left = pad + widths[0] / 2
    right = pad + widths[-1] / 2
    w = left + seg * n + right
    h = pad + fm.height() + gap + bar_h + pad - 2
    pm = QPixmap(max(1, round(w * dpr)), max(1, round(h * dpr)))
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.transparent)
    ink, paper = (QColor(235, 235, 235), QColor(25, 25, 25)) if night else \
        (QColor(0, 0, 0), QColor(255, 255, 255))
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    plate = QColor(paper)
    plate.setAlpha(225)
    p.setPen(QPen(QColor(128, 128, 128, 200), 1))
    p.setBrush(plate)
    p.drawRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), 3, 3)
    p.setRenderHint(QPainter.Antialiasing, False)
    y = pad + fm.height() + gap
    p.setPen(QPen(ink, 1))
    for i in range(n):
        p.setBrush(ink if i % 2 == 0 else paper)
        p.drawRect(QRectF(left + seg * i, y, seg, bar_h))
    p.setRenderHint(QPainter.Antialiasing)
    p.setFont(f)
    p.setPen(ink)
    for i in shown:
        x = left + seg * i
        p.drawText(QPointF(x - widths[i] / 2, pad + fm.ascent()), labels[i])
    p.end()
    return pm
