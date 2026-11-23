"""The color picker every color in the app is chosen with (Properties, Edit objects' Line,
Fill and Text color, the text editing box, bookmarks, page tools, batch steps).

The owner, 23 Nov 2026: "when making custom colors, a recent or currently used colors
section". It is Qt's own color dialog, for any color, inside a small dialog with two rows of
swatches above it:
  Recent            the last colors picked anywhere in the app, newest first (remembered in
                    the app's settings, so they survive a restart)
  In this document  the colors the open document's markups use (their line, fill and text
                    colors), the most used first
One click on a swatch picks its color; hovering shows its hex value. Every color picked, from
a swatch or from Qt's dialog, goes to the front of Recent.

Qt's dialog is always Qt's own here (never the system's): the system's (macOS's color panel,
a GTK one on Linux) is a separate window that can't hold the swatches, so with it the rows
would be on some systems and not others.

The document's colors are read from its markups only (never the page's own text or
drawings), and only when the picker opens: from the PDF objects directly (one read of each
markup's KanzonasPDF style, or of its /C, /IC and /DA for another program's markups),
without loading pages."""

import json
import re

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (QColorDialog, QDialog, QDialogButtonBox, QGridLayout, QLabel,
                               QPushButton, QToolButton, QVBoxLayout)

from .i18n import tr

RECENT_KEY = "recent_colors"
RECENT_MAX = 12          # colors kept in Recent
DOCUMENT_MAX = 24        # colors shown from the document (two rows)
PER_ROW = 12             # swatches on a row
SWATCH = 20              # px: a swatch's color square

_HEX = re.compile(r"^#[0-9a-f]{6}$")
_REF = re.compile(r"(\d+)\s+\d+\s+R")
_NUM = r"[-+]?(?:\d+\.?\d*|\.\d+)"
_DA_RGB = re.compile(r"(%s)\s+(%s)\s+(%s)\s+rg\b" % (_NUM, _NUM, _NUM))
_DA_GRAY = re.compile(r"(%s)\s+g\b" % _NUM)
_STYLE_KEYS = ("stroke", "fill", "text_color", "text_back")     # (in a markup's KZProps)
_SKIP_TYPES = ("/Popup", "/Link", "/Widget")


def _hex(color):
    """A color (QColor, "#rrggbb" or a name) as "#rrggbb" (lowercase), or None."""
    c = QColor(color) if not isinstance(color, QColor) else color
    return c.name().lower() if c.isValid() else None


def _settings(settings):
    if settings is not None:
        return settings
    from . import paths
    return paths.settings()


# ---- Recent ------------------------------------------------------------------------------
def recent_colors(settings=None):
    """The colors picked lately ("#rrggbb"), newest first, at most RECENT_MAX."""
    from . import paths
    stored = paths.stored_json(_settings(settings), RECENT_KEY, [])
    out = []
    for c in stored:
        if isinstance(c, str) and _HEX.match(c.lower()) and c.lower() not in out:
            out.append(c.lower())
    return out[:RECENT_MAX]


def remember(color, settings=None):
    """Put a color picked at the front of Recent (once: an earlier place is dropped)."""
    h = _hex(color)
    if h is None:
        return
    s = _settings(settings)
    recent = [h] + [c for c in recent_colors(s) if c != h]
    s.setValue(RECENT_KEY, json.dumps(recent[:RECENT_MAX]))


# ---- In this document ----------------------------------------------------------------------
def _pdf_color(text):
    """A PDF color array's text ("[1 0 0]") as "#rrggbb", or None."""
    from .annotations import to_hex
    try:
        nums = [float(x) for x in text.strip("[] \n").split()]
    except ValueError:
        return None
    return to_hex(nums) if nums else None


def _da_color(text):
    """The text color in a markup's /DA ("0 0 1 rg /Helv 12 Tf") as "#rrggbb", or None."""
    from .annotations import to_hex
    m = _DA_RGB.search(text)
    if m:
        return to_hex([float(x) for x in m.groups()])
    m = _DA_GRAY.search(text)
    return to_hex([float(m.group(1))]) if m else None


def _annot_xrefs(doc, pno):
    """The xrefs in page pno's /Annots, read from the page object (the page isn't loaded)."""
    typ, val = doc.xref_get_key(doc.page_xref(pno), "Annots")
    if typ == "xref":                       # (the list kept in an object of its own)
        val = doc.xref_object(int(val.split()[0]), compressed=True)
    elif typ != "array":
        return []
    return [int(x) for x in _REF.findall(val)]


def _markup_colors(doc, xref):
    """The colors one markup uses ("#rrggbb" each)."""
    typ, val = doc.xref_get_key(xref, "KZProps")
    if typ == "string":                     # (KanzonasPDF's own: its style as it was set)
        try:
            props = json.loads(val).get("props") or {}
        except (ValueError, AttributeError):
            props = {}
        return [str(props[k]).lower() for k in _STYLE_KEYS
                if isinstance(props.get(k), str) and _HEX.match(props[k].lower())]
    if doc.xref_get_key(xref, "Subtype")[1] in _SKIP_TYPES:
        return []
    out = []
    for key in ("C", "IC"):
        typ, val = doc.xref_get_key(xref, key)
        if typ == "array":
            out.append(_pdf_color(val))
    typ, val = doc.xref_get_key(xref, "DA")
    if typ == "string":
        out.append(_da_color(val))
    return [c for c in out if c]


def document_colors(doc, limit=DOCUMENT_MAX):
    """The distinct colors the document's markups use ("#rrggbb"), the most used first; []
    with no document."""
    if doc is None or getattr(doc, "is_closed", True) or not getattr(doc, "is_pdf", False):
        return []
    counts = {}
    for pno in range(doc.page_count):
        try:
            xrefs = _annot_xrefs(doc, pno)
        except Exception:
            continue  # (a damaged page object: its markups left out of the row)
        for x in xrefs:
            try:
                colors = _markup_colors(doc, x)
            except Exception:
                continue  # (a damaged markup: left out of the row)
            for c in colors:
                counts[c] = counts.get(c, 0) + 1
    # most used first; a tie in the order first met (dicts keep it, sorted is stable)
    return sorted(counts, key=lambda c: -counts[c])[:limit]


def open_document(widget):
    """The document of the window the widget is in (its tab's document), or None."""
    w = widget
    while w is not None:
        doc_view = getattr(w, "_doc_view", None)
        if callable(doc_view):                       # (the main window: its document tab's)
            v = doc_view()
            return getattr(v, "doc", None) if v is not None else None
        doc = getattr(w, "doc", None)
        if doc is not None and hasattr(doc, "xref_get_key"):     # (a document view)
            return doc
        w = w.parentWidget()
    return None


# ---- the dialog ------------------------------------------------------------------------------
class Swatch(QToolButton):
    """One color of a row: a click picks it; hovering shows its hex value."""

    def __init__(self, hex_color, parent=None):
        super().__init__(parent)
        self.hex = hex_color
        pm = QPixmap(SWATCH, SWATCH)
        pm.fill(QColor(hex_color))
        p = QPainter(pm)
        p.setPen(QColor(128, 128, 128))      # (a white or page-colored swatch still shows)
        p.drawRect(0, 0, SWATCH - 1, SWATCH - 1)
        p.end()
        self.setIcon(QIcon(pm))
        self.setIconSize(pm.size())
        self.setAutoRaise(True)
        self.setToolTip(hex_color)
        self.setAccessibleName(hex_color)


class _QtDialog(QColorDialog):
    """Qt's color dialog as a part of the picker (no buttons of its own). Enter and Esc go
    on to the picker (its OK and Cancel): left to this dialog, Esc would close only it."""

    def keyPressEvent(self, e):
        e.ignore()


class ColorPicker(QDialog):
    """Qt's color dialog with a Recent row and an In this document row of swatches above it.
    color() is the color picked (an invalid QColor when canceled)."""

    def __init__(self, start=None, parent=None, title="", recent=None, in_document=()):
        super().__init__(parent)
        self.setWindowTitle(title or tr("Choose color"))
        self._picked = None
        lay = QVBoxLayout(self)
        self.recent = self._row(lay, tr("Recent"), recent_colors() if recent is None else recent)
        self.in_document = self._row(lay, tr("In this document"), in_document)
        self.dialog = _QtDialog(self)
        self.dialog.setWindowFlags(Qt.Widget)
        self.dialog.setOptions(QColorDialog.DontUseNativeDialog | QColorDialog.NoButtons)
        start = QColor(start) if start is not None else QColor()
        if start.isValid():
            self.dialog.setCurrentColor(start)
        if self.dialog.layout() is not None:     # (its parts lined up with the rows above)
            self.dialog.layout().setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.dialog)
        for b in self.dialog.findChildren(QPushButton):
            # (Enter is OK: left as they are, Enter clicked Qt's Pick Screen Color)
            b.setAutoDefault(False)
            b.setDefault(False)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setDefault(True)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def _row(self, lay, label, colors):
        """A row of swatches under its label (none, and no label, without colors)."""
        swatches = []
        if not colors:
            return swatches
        lay.addWidget(QLabel(label))
        grid = QGridLayout()
        grid.setSpacing(2)
        for i, c in enumerate(colors):
            b = Swatch(c, self)
            b.clicked.connect(lambda _=False, c=c: self.pick(c))
            grid.addWidget(b, i // PER_ROW, i % PER_ROW)
            swatches.append(b)
        grid.setColumnStretch(PER_ROW, 1)
        lay.addLayout(grid)
        return swatches

    def pick(self, color):
        """A swatch clicked: its color is the one picked, and the picker closes."""
        self._picked = QColor(color)
        self.dialog.setCurrentColor(self._picked)
        self.accept()

    def color(self):
        if self.result() != QDialog.Accepted:
            return QColor()
        return QColor(self._picked) if self._picked is not None else self.dialog.currentColor()


def get_color(start=None, parent=None, title="", doc=None):
    """Ask for a color, as QColorDialog.getColor does: the QColor picked, or an invalid one
    when canceled. doc: the document whose markups' colors to offer (None: the one open in
    the parent's window). The color picked goes to the front of Recent."""
    if doc is None:
        doc = open_document(parent)
    dlg = ColorPicker(start, parent, title, in_document=document_colors(doc))
    got = dlg.color() if dlg.exec() == QDialog.Accepted else QColor()
    dlg.deleteLater()
    if got.isValid():
        remember(got)
    return got
