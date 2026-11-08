"""On-page text editor for the Edit text and Add text tools.

Opens right on the line being edited, in roughly the same font and size, with the cursor where
you clicked: no pop-up, just a dashed outline with handles, like a selected object. Drag the
outline to move the text, drag a handle to change the width the text wraps to (in the PDF
too). Enter = done, Shift+Enter = new line, Esc = cancel, clicking elsewhere = done.

Each word shows its own style as it is in the PDF (font, size, bold, italic, color, underline,
strikethrough: text_styles.Style, kept in each character's format), and a small bar above the
box changes the selected words' style: Bold (Ctrl+B), Italic (Ctrl+I), Underline (Ctrl+U),
Strikethrough, Text color, Larger / Smaller text (Ctrl+] / Ctrl+[). Text typed next to a word
takes that word's style; text typed into an empty box takes the paragraph's main style.
"""

import re
import sys

from PySide6.QtCore import Qt, Signal, QEvent, QPoint, QPointF, QRect, QRectF, QSizeF
from PySide6.QtGui import (QColor, QFont, QFontDatabase, QFontMetricsF, QPainter, QPen,
                           QTextCharFormat, QTextCursor, QTextFormat, QTextOption)
from PySide6.QtWidgets import QFrame, QHBoxLayout, QTextEdit, QToolButton, QVBoxLayout

from .i18n import tr

MARGIN = 7          # the outline you grab to move the text (px around the text)
HANDLE = 7          # handle squares on the corners and side middles
# Text smaller than SMALL_PX on screen (a drawing sheet zoomed out) is typed enlarged to
# READABLE_PX in a box just below the spot, and a true-size preview shows where it goes (the
# box used to show it at 6 px at least, many times its real size, around the spot)
SMALL_PX = 8.0
READABLE_PX = 13.0

# a character's PDF style, kept in its format (text_styles.Style's fields)
P_FONT = QTextFormat.UserProperty + 1
P_FLAGS = QTextFormat.UserProperty + 2
P_SIZE = QTextFormat.UserProperty + 3          # points
P_FAMILY = QTextFormat.UserProperty + 4
P_ALPHA = QTextFormat.UserProperty + 5         # opacity 0..255 (0: invisible on the page)

_HINT = {"sans": "Arial", "serif": "Times New Roman", "mono": "Courier New"}
_FAMILIES = {}


def screen_family(style, hint=None):
    """The family to show a run in on screen: the PDF font's own when it's installed
    ("ABCDEF+Calibri-Bold" -> Calibri), else Arial / Times New Roman / Courier New as the
    font looks."""
    if style.family:
        return _HINT.get(style.family, style.family)
    name = (style.font or "").split("+", 1)[-1]
    base = re.split(r"[-,]", name)[0]
    base = re.sub(r"(PSMT|MT|PS)$", "", base)
    if base and base not in _FAMILIES:
        spaced = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", base)
        try:
            have = next((f for f in (base, spaced) if QFontDatabase.hasFamily(f)), None)
        except Exception:
            have = None
        _FAMILIES[base] = have
    if base and _FAMILIES.get(base):
        return _FAMILIES[base]
    if hint:
        return _HINT.get(hint, hint)
    from . import text_edit
    b14 = text_edit._base14({"font": style.font, "flags": style.flags})
    kind = "sans" if b14 in ("helv", "hebo", "heit", "hebi") else \
        "serif" if b14 in ("tiro", "tibo", "tiit", "tibi") else "mono"
    return _HINT[kind]


def _color_int(c):
    return (c.red() << 16) | (c.green() << 8) | c.blue()


class StyleBar(QFrame):
    """The buttons above the editor that style the selected words."""
    STATES = ("bold", "italic", "underline", "strike")      # buttons showing on / off

    def __init__(self, editor):
        super().__init__(editor.parentWidget())
        self.editor = editor
        self.setObjectName("KzStyleBar")
        # light, like the white box under it, in both themes (it sits on the page widget,
        # whose dark gray would otherwise be its buttons' color); a style that the selected
        # words have shows pressed
        self.setStyleSheet(
            "#KzStyleBar { background: #ffffff; border: 1px solid #9a9a9a; "
            "border-radius: 4px; }"
            "#KzStyleBar QToolButton { color: #202020; background: transparent; "
            "border: 1px solid transparent; border-radius: 3px; padding: 1px 3px; }"
            "#KzStyleBar QToolButton:hover { background: #e5f1fb; border-color: #9ccaf0; }"
            "#KzStyleBar QToolButton:checked { background: #cce4f7; border-color: #3d8ee0; }")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(2, 2, 2, 2)
        lay.setSpacing(1)
        self.buttons = {}

        def button(key, label, tip, slot, setup=None):
            b = QToolButton(self)
            b.setText(label)
            if sys.platform == "darwin":
                from .macos import mac_keys     # (Command, as the menus' tips say it)
                tip = mac_keys(tip)
            b.setToolTip(tip)
            b.setAutoRaise(True)
            b.setFocusPolicy(Qt.NoFocus)        # the text keeps its selection
            f = b.font()
            if setup:
                setup(f)
            b.setFont(f)
            b.clicked.connect(slot)
            b.setCheckable(key in self.STATES)
            lay.addWidget(b)
            self.buttons[key] = b
            return b
        e = editor
        button("bold", "B", tr("Bold (Ctrl+B)"), lambda: e.toggle("bold"),
               lambda f: f.setBold(True))
        button("italic", "I", tr("Italic (Ctrl+I)"), lambda: e.toggle("italic"),
               lambda f: f.setItalic(True))
        button("underline", "U", tr("Underline (Ctrl+U)"), lambda: e.toggle("underline"),
               lambda f: f.setUnderline(True))
        button("strike", "S", tr("Strikethrough"), lambda: e.toggle("strike"),
               lambda f: f.setStrikeOut(True))
        button("color", "A", tr("Text color"), e.pick_color, lambda f: f.setBold(True))
        button("larger", "A+", tr("Larger text (Ctrl+])"), lambda: e.grow_size(1))
        button("smaller", "A−", tr("Smaller text (Ctrl+[)"), lambda: e.grow_size(-1))
        for b in self.buttons.values():
            b.setMinimumWidth(24)
        self.adjustSize()
        self.show()
        self.raise_()

    def place(self):
        """Just above the editor (below it when there's no room above, and on the side away
        from the true-size preview of enlarged small text)."""
        e = self.editor
        self.adjustSize()
        above = e.y() - self.height() - 2
        below = e.y() + e.height() + 2
        if e.enlarged() and e.y() > e.home.y():
            y = below                       # (the preview is above the box)
        else:
            y = above if above >= 0 else below
        x = max(0, min(e.x() + MARGIN, self.parentWidget().width() - self.width()))
        self.move(x, y)
        self.raise_()

    def show_state(self, fmt):
        """The color button shows the color at the cursor; Bold, Italic, Underline and
        Strikethrough show pressed when all the selected words (or the text at the cursor)
        have them."""
        c = fmt.foreground().color() if fmt.foreground().style() != Qt.NoBrush else \
            QColor(0, 0, 0)
        self.buttons["color"].setStyleSheet("color: %s;" % c.name())
        parts, a, b = self.editor._selected_formats()
        fmts = [p[2] for p in parts] if a != b else [fmt]
        sts = [self.editor.style_of(f) for f in fmts]
        for key in self.STATES:
            self.buttons[key].setChecked(bool(sts) and all(getattr(st, key) for st in sts))


class InlineEditor(QFrame):
    committed = Signal(str, float, float, object)   # text, dx px, dy px, wrap width px or None
    canceled = Signal()
    # the style of the selected words (or of the text at the cursor) for Properties to show:
    # {"bold", "italic", "fontsize" (pt), "text_color" ("#rrggbb")}; None when the editor closes
    formatShown = Signal(object)

    def __init__(self, parent, text_rect, text, family, pixel_size, click=None, bold=False,
                 runs=None, zoom=None, base=None, tools=True):
        """text_rect: QRectF of the line on the page widget (widget coords). click: the point
        clicked (widget coords), where the cursor goes; None selects all the text. runs:
        [(text, text_styles.Style)] making up text, each shown in its own style; base: the
        Style typed text takes in an empty box (the paragraph's main style, or Add text's);
        zoom: screen pixels per point; tools: show the style buttons."""
        super().__init__(parent)
        from .text_styles import Style
        self.setFrameShape(QFrame.NoFrame)
        self.setStyleSheet("InlineEditor { background: transparent; }")
        self.setMouseTracking(True)
        self.setToolTip(tr("Drag the outline to move the text, drag a handle to change its "
                           "width.\nEnter = done, Shift+Enter = new line, Esc = cancel"))
        self.resized_by_user = False
        self.min_height = 0             # px: at least the text it covers (a paragraph)
        self._done = False
        self._drag = None
        self._hint = family
        if base is None:
            base = Style(size=round(pixel_size / (zoom or 1.0), 2), bold=bool(bold))
        self.base = base
        self.zoom = float(zoom or (pixel_size / base.size if base.size else 1.0))
        self._scale = pixel_size / max(0.01, base.size * self.zoom)
        # where the text goes on the page (widget coords), and how much bigger it's shown
        self.home = QRectF(text_rect)
        self._mag = READABLE_PX / max(0.5, pixel_size) if pixel_size < SMALL_PX else 1.0
        lay = QVBoxLayout(self)
        lay.setContentsMargins(MARGIN, MARGIN, MARGIN, MARGIN)
        lay.setSpacing(0)
        self.text = QTextEdit()
        self.text.setAcceptRichText(False)          # (pasted text takes the style there)
        # a hint ("sans" / "serif" / "mono") from the line edited, or a family picked in Properties
        f = QFont(_HINT.get(family, family))
        f.setPixelSize(max(6, int(round(pixel_size * self._mag))))
        f.setBold(bool(base.bold))
        self.text.setFont(f)
        self.text.setFrameShape(QFrame.NoFrame)
        self.text.document().setDocumentMargin(0)
        self.text.setWordWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
        self.text.setLineWrapMode(QTextEdit.WidgetWidth)
        self.text.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.text.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        # white like the page, so the line reads as edited in place (it covers the old text);
        # black text whatever the theme (the dark theme's palette text is light)
        self.text.setStyleSheet("background: white; color: black;")
        self._fill(runs if runs is not None else [(text, base)])
        self.text.installEventFilter(self)
        from . import spelling
        spelling.install(self.text)
        lay.addWidget(self.text)
        self.setFocusPolicy(Qt.ClickFocus)
        self.setFocusProxy(self.text)

        width = max(text_rect.width() * self._mag, self._natural_width()) + 2 * MARGIN + 6
        height = max(1, text.count("\n") + 1) * QFontMetricsF(f).lineSpacing() + 2 * MARGIN + 4
        # keep the editor inside the page horizontally
        width = min(width, max(80, parent.width() - text_rect.x() + MARGIN))
        y = text_rect.y() - MARGIN
        if self.enlarged():
            # just below the true-size spot (above it near the page's bottom)
            y = text_rect.bottom() + 6
            if y + height > parent.height() - 4:
                y = max(0, text_rect.y() - height - 6)
        self.setGeometry(int(text_rect.x() - MARGIN), int(y), int(width), int(height))
        self._start_pos = self.pos()
        self._start_width = self.width()
        self.text.textChanged.connect(self._changed)
        if self.enlarged():
            self.text.textChanged.connect(self.parentWidget().update)      # (the preview)
        self.bar = StyleBar(self) if tools else None
        self.text.currentCharFormatChanged.connect(self._format_moved)
        self.text.selectionChanged.connect(self._format_moved)
        self.show()
        self.raise_()
        self._grow()
        self.text.setFocus()
        self._click = click
        self._fixed = False
        if click is not None:
            self._place_cursor()
        else:
            self.text.selectAll()
        self._format_moved(self.text.currentCharFormat())

    def enlarged(self):
        """The text is shown bigger than it will be on the page (it would be too small to
        read at this zoom), with a true-size preview at its spot."""
        return self._mag > 1.0

    def preview_origin(self):
        """Where the text's top left goes on the page now (widget coords): its spot, moved
        as the box has been dragged."""
        return self.home.topLeft() + QPointF(self.pos() - self._start_pos)

    def paint_preview(self, p):
        """Draw the text at its true size where it goes (for enlarged small text): white under
        it (the text it replaces), the words, and a thin outline. p: a painter on the page."""
        if not self.enlarged() or self._done:
            return
        doc = self.text.document()
        k = 1.0 / self._mag
        o = self.preview_origin()
        size = QSizeF(min(doc.size().width(), doc.idealWidth()) * k, doc.size().height() * k)
        area = QRectF(o, size)
        if self.pos() == self._start_pos:
            area = area.united(self.home)       # (the text being replaced, at its spot)
        p.save()
        p.fillRect(area.adjusted(-1, -1, 1, 1), Qt.white)
        p.translate(o)
        p.scale(k, k)
        doc.drawContents(p)
        p.restore()
        p.save()
        p.setPen(QPen(QColor(0, 120, 215), 1, Qt.DashLine))
        p.setBrush(Qt.NoBrush)
        p.drawRect(QRectF(o, size).adjusted(-1.5, -1.5, 1.5, 1.5))
        p.restore()

    # ---- styles ---------------------------------------------------------------------
    def format_for(self, style):
        """The character format showing a text_styles.Style on screen."""
        fmt = QTextCharFormat()
        if self._hint and self._hint not in _HINT:
            family = self._hint             # (a family picked in Properties)
        else:
            family = screen_family(style, self._hint if not style.font else None)
        f = QFont(family)
        f.setPixelSize(max(6, int(round(style.size * self.zoom * self._scale * self._mag))))
        f.setBold(bool(style.bold))
        f.setItalic(bool(style.italic))
        f.setUnderline(bool(style.underline))
        f.setStrikeOut(bool(style.strike))
        fmt.setFont(f)
        # (invisible or see-through text shows faint)
        fmt.setForeground(QColor((style.color >> 16) & 255, (style.color >> 8) & 255,
                                 style.color & 255, max(70, min(255, style.alpha))))
        fmt.setProperty(P_ALPHA, int(style.alpha))
        fmt.setProperty(P_FONT, style.font or "")
        fmt.setProperty(P_FLAGS, int(style.flags))
        fmt.setProperty(P_SIZE, float(style.size))
        fmt.setProperty(P_FAMILY, style.family or "")
        return fmt

    def style_of(self, fmt):
        """The text_styles.Style a character format stands for."""
        from .text_styles import Style
        size = fmt.property(P_SIZE)
        if not isinstance(size, (int, float)) or size <= 0:
            size = self.base.size           # (not one of ours: setPlainText's)
        font = fmt.property(P_FONT)
        flags = fmt.property(P_FLAGS)
        family = fmt.property(P_FAMILY)
        alpha = fmt.property(P_ALPHA)
        brush = fmt.foreground()
        color = _color_int(brush.color()) if brush.style() != Qt.NoBrush else self.base.color
        qf = fmt.font()
        return Style(font if isinstance(font, str) else self.base.font,
                     int(flags) if isinstance(flags, int) else self.base.flags,
                     round(float(size), 2), color, qf.bold(), qf.italic(), qf.underline(),
                     qf.strikeOut(), family if isinstance(family, str) else self.base.family,
                     alpha=int(alpha) if isinstance(alpha, int) else self.base.alpha)

    def _fill(self, runs):
        doc = self.text.document()
        doc.clear()
        cur = QTextCursor(doc)
        for t, st in runs:
            cur.insertText(t, self.format_for(st))
        if doc.isEmpty():
            self.text.setCurrentCharFormat(self.format_for(self.base))
        self.text.document().clearUndoRedoStacks()

    def styled_runs(self):
        """[(text, text_styles.Style)] of what's typed, its text toPlainText()'s."""
        out = []
        doc = self.text.document()
        block = doc.begin()
        first = True
        while block.isValid():
            if not first:
                out.append(("\n", out[-1][1] if out else self.base))
            first = False
            it = block.begin()
            while not it.atEnd():
                frag = it.fragment()
                if frag.isValid():
                    t = frag.text().replace(" ", "\n").replace(" ", "\n") \
                        .replace(" ", " ")
                    out.append((t, self.style_of(frag.charFormat())))
                it += 1
            block = block.next()
        if "".join(t for t, _s in out) != self.text.toPlainText():
            return None
        return out

    def _selected_formats(self):
        cur = self.text.textCursor()
        a, b = cur.selectionStart(), cur.selectionEnd()
        if a == b:
            return [], a, b
        out = []
        block = self.text.document().findBlock(a)
        while block.isValid() and block.position() < b:
            it = block.begin()
            while not it.atEnd():
                frag = it.fragment()
                s, e = frag.position(), frag.position() + frag.length()
                if frag.isValid() and s < b and e > a:
                    out.append((max(a, s), min(b, e), frag.charFormat()))
                it += 1
            block = block.next()
        return out, a, b

    def _all_formats(self):
        """[(start, end, QTextCharFormat)] of all the text, as _selected_formats."""
        out = []
        block = self.text.document().begin()
        while block.isValid():
            it = block.begin()
            while not it.atEnd():
                frag = it.fragment()
                if frag.isValid():
                    out.append((frag.position(), frag.position() + frag.length(),
                                frag.charFormat()))
                it += 1
            block = block.next()
        return out

    def _restyle(self, change, whole=False):
        """change(Style) -> Style for the selected words (or the words about to be typed; with
        whole, all the text when nothing is selected). The selection stays selected."""
        parts, a, b = self._selected_formats()
        if a == b and whole and not self.text.document().isEmpty():
            parts, a, b = self._all_formats(), 0, len(self.text.toPlainText())
            pos = self.text.textCursor().position()
            cur = QTextCursor(self.text.document())
            cur.beginEditBlock()
            for s, e, fmt in parts:
                cur.setPosition(s)
                cur.setPosition(e, QTextCursor.KeepAnchor)
                cur.setCharFormat(self.format_for(change(self.style_of(fmt))))
            cur.endEditBlock()
            # what's typed next at the cursor takes the change too
            self.text.setCurrentCharFormat(self.format_for(change(self.style_of(
                self.text.currentCharFormat()))))
            c = self.text.textCursor()
            c.setPosition(min(pos, len(self.text.toPlainText())))
            self.text.setTextCursor(c)
        elif a == b:
            st = change(self.style_of(self.text.currentCharFormat()))
            self.text.setCurrentCharFormat(self.format_for(st))
        else:
            cur = QTextCursor(self.text.document())
            cur.beginEditBlock()
            for s, e, fmt in parts:
                cur.setPosition(s)
                cur.setPosition(e, QTextCursor.KeepAnchor)
                cur.setCharFormat(self.format_for(change(self.style_of(fmt))))
            cur.endEditBlock()
        self._grow()
        self._format_moved(self.text.currentCharFormat())
        self.text.setFocus()

    def shown_format(self):
        """The style Properties shows: of all the selected words (bold only when all of them
        are), or of the text at the cursor."""
        parts, a, b = self._selected_formats()
        fmts = [p[2] for p in parts] if a != b else [self.text.currentCharFormat()]
        sts = [self.style_of(f) for f in fmts] or [self.base]
        first = sts[0]
        return {"bold": all(st.bold for st in sts), "italic": all(st.italic for st in sts),
                "fontsize": round(first.size, 2),
                "text_color": "#%06x" % (first.color & 0xFFFFFF)}

    def apply_format(self, key, value):
        """A change made in Properties while editing: to the selected words, or to all the
        text when nothing is selected (key: "bold", "italic", "fontsize", "text_color")."""
        if key in ("bold", "italic"):
            self._restyle(lambda st: st._replace(**{key: bool(value)}), whole=True)
        elif key == "fontsize":
            size = round(max(1.0, float(value)), 2)
            self._restyle(lambda st: st._replace(size=size), whole=True)
        elif key == "text_color":
            c = QColor(value)
            if c.isValid():
                self._restyle(lambda st: st._replace(color=_color_int(c)), whole=True)

    def toggle(self, kind):
        """Bold / italic / underline / strike: on for the selection, or off when all of it
        has it already."""
        parts, a, b = self._selected_formats()
        fmts = [p[2] for p in parts] if a != b else [self.text.currentCharFormat()]
        on = not all(getattr(self.style_of(f), kind) for f in fmts)
        self._restyle(lambda st: st._replace(**{kind: on}))

    def grow_size(self, step):
        """Larger / smaller text: the selection's sizes up or down a point."""
        self._restyle(lambda st: st._replace(size=round(max(1.0, st.size + step), 2)))

    def set_color(self, color):
        """The selection's color (a QColor)."""
        if color is not None and color.isValid():
            self._restyle(lambda st: st._replace(color=_color_int(color)))

    def pick_color(self):
        from PySide6.QtWidgets import QColorDialog
        st = self.style_of(self.text.currentCharFormat())
        c = QColorDialog.getColor(QColor((st.color >> 16) & 255, (st.color >> 8) & 255,
                                         st.color & 255), self, tr("Text color"))
        self.set_color(c)
        self.text.setFocus()

    def _format_moved(self, fmt=None):
        if self.bar is not None:
            self.bar.show_state(fmt if fmt is not None else self.text.currentCharFormat())
        if not self._done:
            self.formatShown.emit(self.shown_format())

    def _changed(self):
        if self.text.document().isEmpty():
            # typed into an empty box: the paragraph's main style
            self.text.setCurrentCharFormat(self.format_for(self.base))
        self._grow()

    def _place_cursor(self):
        """Put the text cursor where the page was clicked (on enlarged small text: the
        same place in the enlarged text)."""
        click = QPointF(self._click)
        if self.enlarged():
            d = (click - self.preview_origin()) * self._mag
            pt = self.text.viewport().mapTo(self.parentWidget(), QPoint(0, 0))
            click = QPointF(pt) + d
        c = self.text.cursorForPosition(self.text.viewport().mapFrom(self.parentWidget(),
                                                                     click.toPoint()))
        self.text.setTextCursor(c)

    def fix_width(self, width_px):
        """Edit a whole paragraph: the box keeps the paragraph's width and the text wraps in
        it as it will on the page (drag a side handle to change the width)."""
        self.resized_by_user = True
        self._fixed = True
        self.resize(int(width_px * self._mag + 2 * MARGIN + 6), self.height())
        self._start_width = self.width()
        self._grow()
        if self._click is not None:
            # the words now wrap as on the page: the click lands on the word clicked
            self._place_cursor()

    def set_pixel_size(self, pixel_size):
        """Font size changed in Properties while typing: show the text at the new size (every
        word scaled alike)."""
        self._scale = pixel_size / max(0.01, self.base.size * self.zoom)
        f = self.text.font()
        f.setPixelSize(max(6, int(round(pixel_size * self._mag))))
        self.text.setFont(f)
        cur = QTextCursor(self.text.document())
        pos = self.text.textCursor().position()
        anchor = self.text.textCursor().anchor()
        block = self.text.document().begin()
        cur.beginEditBlock()
        while block.isValid():
            it = block.begin()
            while not it.atEnd():
                frag = it.fragment()
                if frag.isValid():
                    cur.setPosition(frag.position())
                    cur.setPosition(frag.position() + frag.length(), QTextCursor.KeepAnchor)
                    cur.setCharFormat(self.format_for(self.style_of(frag.charFormat())))
                it += 1
            block = block.next()
        cur.endEditBlock()
        n = len(self.text.toPlainText())
        c = self.text.textCursor()
        c.setPosition(min(anchor, n))
        c.setPosition(min(pos, n), QTextCursor.KeepAnchor)      # (the selection stays)
        self.text.setTextCursor(c)
        self._grow()
        self.text.setFocus()

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

    def moveEvent(self, e):
        super().moveEvent(e)
        if getattr(self, "bar", None) is not None:
            self.bar.place()
        if getattr(self, "_mag", 1.0) > 1.0:
            self.parentWidget().update()        # (the true-size preview follows)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if getattr(self, "bar", None) is not None:
            self.bar.place()

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
    def _natural_width(self):
        """The widest line of the text, not wrapped (px)."""
        d = self.text.document().clone()
        d.setDocumentMargin(0)
        d.setTextWidth(-1)
        return d.idealWidth()

    def _grow(self):
        """Widen as you type until the page's right edge (then wrap), and grow downward."""
        if not self.resized_by_user:
            # as wide as the text (no wider than the line it replaces needs, and room for
            # the cursor), growing and shrinking as you type, up to the page's right edge
            need = int(self._natural_width() + 2 * MARGIN + 6)
            least = int(max(self.home.width() * self._mag + 2 * MARGIN + 6,
                            2 * MARGIN + 6 + QFontMetricsF(self.text.font()).averageCharWidth()))
            limit = self.parentWidget().width() - self.x() - 4
            want = max(least, min(need, limit))
            if want != self.width():
                self.resize(want, self.height())
        doc = self.text.document()
        h = doc.size().height()
        # (a paragraph's box covers the old paragraph; enlarged text isn't over it)
        want = max(int(h + 2 * MARGIN + 4), 0 if self.enlarged() else self.min_height)
        if want != self.height():
            self.resize(self.width(), want)
        # wrapping in the PDF follows the editor, so the start width must track auto-growth
        if not self.resized_by_user:
            self._start_width = self.width()

    _KEYS = {Qt.Key_B: "bold", Qt.Key_I: "italic", Qt.Key_U: "underline",
             Qt.Key_BracketRight: "larger", Qt.Key_BracketLeft: "smaller"}

    def _style_key(self, e):
        mods = e.modifiers() & ~Qt.KeypadModifier
        if mods != Qt.ControlModifier:
            return None
        return self._KEYS.get(e.key())

    def eventFilter(self, obj, e):
        if obj is self.text:
            t = e.type()
            if t == QEvent.ShortcutOverride and self._style_key(e):
                e.accept()              # (Ctrl+] / Ctrl+[ are the window's too: ours here)
                return True
            if t == QEvent.KeyPress:
                key = self._style_key(e)
                if key in ("bold", "italic", "underline"):
                    self.toggle(key)
                    return True
                if key in ("larger", "smaller"):
                    self.grow_size(1 if key == "larger" else -1)
                    return True
                if e.key() in (Qt.Key_Return, Qt.Key_Enter) and not (e.modifiers() & Qt.ShiftModifier):
                    self.commit()
                    return True
                if e.key() == Qt.Key_Escape:
                    self.cancel()
                    return True
        # (No commit on focus loss: the page commits the edit when you click elsewhere on it.
        # Committing on focus-out made moving and resizing end the edit.)
        return super().eventFilter(obj, e)

    def close_bar(self):
        if self.bar is not None:
            self.bar.hide()
            self.bar.deleteLater()
            self.bar = None

    def commit(self):
        if self._done:
            return
        self._done = True
        moved = self.pos() - self._start_pos
        # Wrap in the PDF exactly when the user resized the box or the text wraps on screen.
        wrap = self.text.viewport().width() - 2 if (self.resized_by_user or self._wraps()) else None
        if wrap is not None:
            wrap /= self._mag                   # (true size on screen: px at the zoom)
        if self._fixed and self.width() == self._start_width:
            wrap = None             # a paragraph's own width, not the box's (no creep)
        self.hide()
        self.close_bar()
        if self.enlarged():
            self.parentWidget().update()        # (the preview goes)
        self.formatShown.emit(None)
        self.committed.emit(self.text.toPlainText(), float(moved.x()), float(moved.y()), wrap)
        self.deleteLater()

    def _wraps(self):
        """Some paragraph wraps onto more than one line on screen."""
        block = self.text.document().begin()
        while block.isValid():
            lay = block.layout()
            if lay is not None and lay.lineCount() > 1:
                return True
            block = block.next()
        return False

    def cancel(self):
        if self._done:
            return
        self._done = True
        self.hide()
        self.close_bar()
        if self.enlarged():
            self.parentWidget().update()        # (the preview goes)
        self.formatShown.emit(None)
        self.canceled.emit()
        self.deleteLater()
