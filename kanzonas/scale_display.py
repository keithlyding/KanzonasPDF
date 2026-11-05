"""The page's drawing scale where it can't be missed: a large label on the Measure tab and a
bold one in the status bar (red "Scale not set" when the page has none), both opening Set
scale when clicked; and the graphic scale bar drawn on scaled pages (View > Show scale bar),
on screen only: it is never printed, exported or saved.

The bar is a small picture made once per page, zoom and look and kept by the view
(DocumentView.scale_bar_pixmap), so a repaint only copies it."""

from PySide6.QtCore import Qt, QPointF, QRectF, QSize, Signal
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QToolButton, QVBoxLayout

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


class ScalePanel(QToolButton):
    """The Measure tab's 'Page scale' group: a button two rows tall that reads 'Set scale'
    above the current page's scale in large type (red 'Scale not set' without one), and
    opens Set scale; the Show scale bar switch is a small icon beside 'Set scale'. One width
    whatever the scale, so the tab doesn't shift from page to page, and narrow enough for
    the tab to fit a 1366-pixel screen in Spanish too: a longer label is elided (the tool
    tip has it whole)."""

    def __init__(self, set_scale_action, scale_bar_action, parent=None):
        super().__init__(parent)
        self.setAutoRaise(True)
        self.setCursor(Qt.PointingHandCursor)
        self.clicked.connect(set_scale_action.trigger)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 1, 4, 1)
        lay.setSpacing(0)
        self.caption = QLabel(set_scale_action.iconText() or tr("Set scale"))
        f = QFont(self.font())
        f.setPointSizeF(f.pointSizeF() * 0.85)
        self.caption.setFont(f)
        self.caption.setStyleSheet("color: gray;")
        self.caption.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.bar = QToolButton()
        self.bar.setDefaultAction(scale_bar_action)
        self.bar.setAutoRaise(True)
        self.bar.setToolButtonStyle(Qt.ToolButtonIconOnly)
        self.bar.setIconSize(QSize(14, 14))
        self.bar.setFixedSize(18, 18)
        self.bar.setCursor(Qt.ArrowCursor)
        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(2)
        top.addWidget(self.caption, 1)
        top.addWidget(self.bar)
        lay.addLayout(top)
        self.value = QLabel()
        f = QFont(self.font())
        f.setBold(True)
        f.setPointSizeF(f.pointSizeF() * 1.25)
        self.value.setFont(f)
        self.caption.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.value.setAlignment(Qt.AlignCenter)
        self.value.setAttribute(Qt.WA_TransparentForMouseEvents)
        lay.addWidget(self.value)
        fm = self.value.fontMetrics()
        self._text_w = max(fm.horizontalAdvance(tr("Scale not set")),
                           fm.horizontalAdvance('1-1/2" = 1\'-0"'))
        self.setFixedWidth(max(self._text_w, self.caption.sizeHint().width() + 20) + 10)
        from .ribbon import ROWS, SMALL_HEIGHT
        self.setFixedHeight(ROWS * SMALL_HEIGHT)       # (as tall as the ribbon's large buttons)
        self._state = None
        self.show_scale(None, "")

    def text(self):
        return self.value.text()

    def show_scale(self, scale, tip):
        """scale: measure.get_scale's tuple for the current page, None with no document."""
        text = short_text(scale) if scale is not None else tr("Scale not set")
        ok = scale is None or scale[3]
        state = (text, ok, tip, not_set_color(), scale is None)
        if state == self._state:
            return
        self._state = state
        fm = self.value.fontMetrics()
        self.value.setText(fm.elidedText(text, Qt.ElideRight, self._text_w))
        self.setToolTip(tip)
        self.value.setEnabled(scale is not None)
        self.caption.setEnabled(scale is not None)
        self.value.setStyleSheet("" if ok else "color: %s;" % not_set_color())


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
