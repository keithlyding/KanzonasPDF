"""Rulers along the top and left of a document view (View > Rulers, Ctrl+R; Bluebeam and
Acrobat have them), and the units the pointer's position is shown in on the status bar.

They measure the page under the pointer, or the page in view when the pointer is elsewhere,
as it's shown (turned), from its top-left corner, in paper units: inches, millimeters or
points (right-click a ruler; the first time, inches where the system measures in inches and
millimeters elsewhere). The page's own length is the lighter band; the pointer's place is
marked on both. A ruler only paints: each move of the pointer is one repaint of two thin
strips, nothing read from the document."""

import math

from PySide6.QtCore import QLocale, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QAction, QActionGroup, QColor, QPainter, QPen
from PySide6.QtWidgets import QMenu, QWidget

from . import paths
from .i18n import tr

THICKNESS = 20                  # pixels
UNITS = ("in", "mm", "pt")
PER_UNIT = {"in": 72.0, "mm": 72.0 / 25.4, "pt": 1.0}      # PDF points in one unit
MIN_GAP = 56                    # pixels between labeled ticks, at least


def unit_names():
    return {"in": tr("Inches"), "mm": tr("Millimeters"), "pt": tr("Points")}


_units = []                     # the units, read once (every pointer move shows them)


def units():
    """The units chosen for the rulers and the pointer's position."""
    if not _units:
        default = "in" if QLocale.system().measurementSystem() != QLocale.MetricSystem else "mm"
        _units.append(paths.stored_str(paths.settings(), "ruler_units", default, UNITS))
    return _units[0]


def set_units(unit):
    paths.settings().setValue("ruler_units", unit)
    forget_units()


def forget_units():
    _units.clear()


def to_units(points, unit=None):
    return points / PER_UNIT[unit or units()]


def fmt(value, unit=None):
    """A length in the units, as the status bar shows it."""
    unit = unit or units()
    return ("%.0f" if unit == "pt" else "%.1f" if unit == "mm" else "%.2f") % value


def step_for(px_per_unit):
    """(labeled step, ticks between labels) in units: the smallest of 1, 2, 5 x 10^k units
    whose labels are at least MIN_GAP pixels apart."""
    if px_per_unit <= 0:
        return 1.0, 1
    raw = MIN_GAP / px_per_unit
    k = math.floor(math.log10(raw))
    for m in (1, 2, 5, 10):
        step = m * 10 ** k
        if step >= raw * 0.999:
            break
    ticks = 10 if m in (1, 10) else (4 if m == 2 else 5)
    while ticks > 1 and step * px_per_unit / ticks < 5:
        ticks = {10: 5, 5: 1, 4: 2, 2: 1}.get(ticks, 1)
    return step, ticks


class Ruler(QWidget):
    """One ruler. horizontal: along the top (x), else along the left (y)."""
    unitsChanged = Signal()

    def __init__(self, view, horizontal):
        super().__init__(view)
        self.view = view
        self.horizontal = horizontal
        self.setContextMenuPolicy(Qt.DefaultContextMenu)
        self.setToolTip(tr("Ruler: right-click to change its units"))

    def contextMenuEvent(self, e):
        menu = QMenu(self)
        group = QActionGroup(menu)
        now = units()
        for key, name in unit_names().items():
            a = QAction(name, menu, checkable=True)
            a.setChecked(key == now)
            a.triggered.connect(lambda _c=False, k=key: self._set(k))
            group.addAction(a)
            menu.addAction(a)
        menu.exec(e.globalPos())

    def _set(self, unit):
        set_units(unit)
        self.view.units_changed()

    def page_span(self):
        """(page index, pixel where the page starts, pixels per point) along this ruler, in
        its own coordinates; None without a page."""
        v = self.view
        index = v.ruler_page()
        if index is None or not 0 <= index < len(v.pages):
            return None
        pw = v.pages[index]
        o = pw.offset()
        at = pw.mapTo(v.viewport(), o.toPoint())
        return index, (at.x() if self.horizontal else at.y()), v.zoom

    def paintEvent(self, _e):
        p = QPainter(self)
        pal = self.palette()
        back = pal.window().color()
        dark = back.lightness() < 128
        p.fillRect(self.rect(), back.darker(115) if not dark else back.lighter(115))
        text = pal.windowText().color()
        length = self.width() if self.horizontal else self.height()
        span = self.page_span()
        if span is not None:
            index, start, zoom = span
            r = self.view.page_rects[index]
            size_pt = r.width if self.horizontal else r.height
            page = QColor(back.lighter(135) if dark else QColor("#ffffff"))
            band = (start, start + size_pt * zoom)
            if self.horizontal:
                p.fillRect(QRectF(band[0], 0, band[1] - band[0], THICKNESS), page)
            else:
                p.fillRect(QRectF(0, band[0], THICKNESS, band[1] - band[0]), page)
            unit = units()
            px_per_unit = zoom * PER_UNIT[unit]
            step, ticks = step_for(px_per_unit)
            p.setPen(QPen(text, 1))
            f = p.font()
            f.setPointSizeF(max(6.0, f.pointSizeF() * 0.8))
            p.setFont(f)
            first = math.floor(-start / px_per_unit / step) * step
            last = (length - start) / px_per_unit
            n = 0
            value = first
            while value <= last + step and n < 2000:
                for t in range(ticks):
                    u = value + t * step / ticks
                    x = start + u * px_per_unit
                    if not -1 <= x <= length + 1:
                        continue
                    tall = THICKNESS * (0.55 if t == 0 else
                                        0.35 if ticks % 2 == 0 and t == ticks // 2 else 0.2)
                    self._tick(p, x, tall)
                    if t == 0:
                        self._label(p, x, value, step)
                value += step
                n += 1
            # where the pointer is
            pos = self.view.pointer_pos()
            if pos is not None and pos[0] == index:
                at = start + (pos[1] if self.horizontal else pos[2]) * zoom
                p.setPen(QPen(pal.highlight().color(), 1))
                self._tick(p, at, THICKNESS)
        p.setPen(QPen(text.darker(150) if not dark else text, 1))
        if self.horizontal:
            p.drawLine(0, THICKNESS - 1, self.width(), THICKNESS - 1)
        else:
            p.drawLine(THICKNESS - 1, 0, THICKNESS - 1, self.height())
        p.end()

    def _tick(self, p, x, tall):
        if self.horizontal:
            p.drawLine(QPointF(x, THICKNESS - tall), QPointF(x, THICKNESS))
        else:
            p.drawLine(QPointF(THICKNESS - tall, x), QPointF(THICKNESS, x))

    def _label(self, p, x, value, step):
        digits = max(0, -int(math.floor(math.log10(step)))) if step < 1 else 0
        s = "%.*f" % (digits, value)
        if s.startswith("-") and float(s) == 0:
            s = s[1:]
        if self.horizontal:
            p.drawText(QPointF(x + 2, THICKNESS * 0.5), s)
        else:
            p.save()
            p.translate(THICKNESS * 0.5, x + 2)
            p.rotate(90)
            p.drawText(QPointF(0, 0), s)
            p.restore()


class Corner(QWidget):
    """The square where the rulers meet: the units, and a right-click to change them."""

    def __init__(self, view):
        super().__init__(view)
        self.view = view
        self.setToolTip(tr("Ruler units: right-click to change them"))

    def contextMenuEvent(self, e):
        Ruler.contextMenuEvent(self.view._rulers[0], e)

    def paintEvent(self, _e):
        p = QPainter(self)
        back = self.palette().window().color()
        p.fillRect(self.rect(), back.darker(115) if back.lightness() >= 128 else back.lighter(115))
        f = p.font()
        f.setPointSizeF(max(6.0, f.pointSizeF() * 0.8))
        p.setFont(f)
        p.setPen(self.palette().windowText().color())
        p.drawText(self.rect(), Qt.AlignCenter, units())
        p.end()
