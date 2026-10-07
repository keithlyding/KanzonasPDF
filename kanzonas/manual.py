"""Built-in user manual (Help > User manual, F1).

The manual is kept here as HTML so it is always packaged with the app (no data files).
Each <h2 id="..."> becomes an entry in the contents list.
"""

import re

from PySide6.QtCore import Qt
from PySide6.QtGui import QTextDocument, QKeySequence, QShortcut
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QVBoxLayout, QListWidget, QTextBrowser,
                               QLineEdit, QPushButton, QSplitter, QWidget, QLabel)

MANUAL = """
<h1>KanzonasPDF user manual</h1>
<p>A free PDF reader and editor. Use the contents list on the left, or type in the
<b>Find in manual</b> box above.</p>

<h2 id="start">Getting started</h2>
<ul>
<li><b>Open a PDF:</b> File &gt; Open (Ctrl+O), drag a file onto the window, or pick one from
File &gt; Open recent. Each file opens in its own tab, at the page and zoom you left it.</li>
<li><b>Save:</b> Ctrl+S. <b>Save as:</b> Ctrl+Shift+S. Undo is Ctrl+Z, redo is Ctrl+Y.</li>
<li><b>Panels:</b> Pages/Bookmarks/Layers on the left (F4), Properties on the right (F6),
Markups list (F7), Tool chest (F8), Bookmarks (F9), Split view (F10).</li>
<li><b>Theme:</b> View &gt; Theme (Match Windows, Light, Dark). View &gt; Show text labels on
toolbars adds names under the icons. Hover over any toolbar button or box for a tooltip
saying what it does and its keyboard shortcut.</li>
</ul>

<h2 id="navigate">Moving around</h2>
<ul>
<li><b>Next / previous page:</b> the &#9664; &#9654; buttons beside the page number in the
toolbar, the Right / Left arrow keys, or type a page number and press Enter.</li>
<li><b>Zoom in / Zoom out:</b> Ctrl+Plus / Ctrl+Minus, Ctrl+mouse wheel, or the zoom box.
Fit width (Ctrl+2), fit page (Ctrl+0), actual size (Ctrl+1).</li>
<li><b>Page thumbnails</b> (F4) shows or hides the left panel.</li>
<li><b>Pan:</b> Hand tool (H), the scroll bars, or <b>hold the mouse wheel down and drag</b>
(works with any tool). Shift+Left/Right scrolls sideways.</li>
<li><b>CAD-style mouse (wheel zooms, hold wheel to pan)</b> (View menu, toolbar button, F11):
like AutoCAD, the scroll wheel zooms in and out around the cursor and holding the wheel down
moves the sheet, so you can navigate a drawing while any markup tool is active. Hold Shift to
scroll with the wheel instead. Your choice is remembered.</li>
<li><b>Find text:</b> Ctrl+F, then Enter / F3 for the next match and Shift+F3 for the previous.</li>
<li><b>Split view</b> (F10) shows a second, independently scrolling view of the same file.</li>
</ul>

<h2 id="select">Selecting and editing markups</h2>
<ul>
<li><b>Select tool (V):</b> drag across text to copy it. Click a markup to select it, then drag
it to move it, drag a square handle to resize it, or change its look in the Properties panel.</li>
<li>With a drawing tool active (rectangle, line, callout, ...), clicking an existing markup selects
it too, so you don't have to switch back to the arrow.</li>
<li><b>Several markups:</b> Ctrl+click each one, or drag a box from empty space with the Select
tool (Ctrl+drag always draws a selection box). Drag any selected markup to move them all;
Delete removes them all; Properties changes apply to all of them.</li>
<li><b>Delete:</b> Delete or Backspace. <b>Edit a note's text:</b> double-click it.</li>
<li><b>Escape</b> clears the selection; <b>Escape twice</b> switches back to the Select (arrow) tool.</li>
</ul>

<h2 id="markup">Text markup and comments</h2>
<ul>
<li><b>Highlight</b> (Ctrl+Shift+H), <b>Underline</b> (Ctrl+Shift+U), <b>Strike</b>
(Ctrl+Shift+X): drag across the text. Selection works letter by letter.</li>
<li><b>Comment</b> (C): select text, type your comment. The text is marked (highlight,
underline, strike or squiggly: choose in Properties) and the comment shows in a box beside it.
Hide the boxes with View &gt; Show comment boxes.</li>
<li><b>Sticky note</b> (N): click where it goes and type.</li>
<li><b>Text box</b> (T): drag a box (or click) and type. Ctrl+Enter finishes typing.</li>
<li><b>Callout</b> (K): press on the point you're pointing at, drag to where the text goes.</li>
<li><b>Author name:</b> Edit &gt; Author name for markups. It's recorded on your markups and
printed on stamps.</li>
</ul>

<h2 id="shapes">Shapes, lines and the pen</h2>
<ul>
<li>Rectangle (R), Ellipse (E), Cloud (D), Polygon (Y), Line (L), Arrow (A), Polyline
(Shift+L), Pen (P). The shapes share one toolbar button: click its arrow to pick another.</li>
<li><b>Polygon / polyline:</b> click each point; double-click or Enter to finish, Escape to cancel.</li>
<li><b>Hold Shift</b> while drawing:
  <ul>
  <li>lines, arrows, measurements and polyline segments snap to 45&deg; steps (horizontal,
  vertical or diagonal);</li>
  <li>rectangles, ellipses and clouds become perfect squares and circles.</li>
  </ul></li>
<li><b>Hold Shift while resizing</b> from a corner: squares and circles stay perfect, other
markups keep their proportions. Shift while dragging a line's end keeps it at 45&deg; steps.</li>
<li><b>Eraser</b> (X): click a markup to delete it, or drag a box to delete everything inside.</li>
</ul>

<h2 id="properties">Colors, borders and styles (Properties panel)</h2>
<ul>
<li>With a tool active, the Properties panel (F6) sets that tool's <b>default style</b>, saved
for next time. With a markup selected, it changes <b>that markup</b>.</li>
<li>Line color, fill (or <b>No fill</b>), <b>No border</b> for boxes and shapes, text color,
line width, font size, arrowheads, cloud border, opacity.</li>
<li><b>Reset defaults</b> puts a tool back to its original style.</li>
<li><b>Tool chest</b> (F8): save a styled markup to reuse with one click, and share chests
with others (export / import).</li>
</ul>

<h2 id="rotate">Rotating markups</h2>
<ul>
<li>Select a shape and drag the <b>round handle</b> above it. Hold Shift for 15&deg; steps.</li>
<li>Or type an angle in <b>Rotation</b> in the Properties panel (counterclockwise).</li>
<li>Text boxes and callouts rotate in 90&deg; steps (a limitation of PDF text boxes).</li>
</ul>

<h2 id="arrange">Align, distribute and stacking order (Arrange)</h2>
<ul>
<li>Select two or more markups, then use the <b>Arrange</b> toolbar or menu: Align left,
Align centers (horizontally), Align right, Align top, Align middles (vertically), Align bottom.</li>
<li><b>Align relative to:</b> Align to first selected (the default), Align to last selected,
Align to whole selection, or Align to page. Choose it in the toolbar dropdown or Arrange &gt;
Align relative to. The first-selected markup has a bolder outline.</li>
<li><b>Distribute horizontally</b> / <b>Distribute vertically</b> (three or more): equal gaps,
the outer two stay put.</li>
<li><b>Bring to front</b> (Ctrl+Shift+]), <b>Bring forward</b> (Ctrl+]),
<b>Send backward</b> (Ctrl+[), <b>Send to back</b> (Ctrl+Shift+[).</li>
</ul>

<h2 id="stamps">Stamps</h2>
<ul>
<li>Stamp tool (M): pick a stamp in Properties (Approved, Draft, ... or type your own text),
then click to place it.</li>
<li><b>Add my name</b> and <b>Add the date</b> are separate checkboxes. Changing them on a
placed stamp redraws it (a re-added date shows today's date).</li>
<li><b>Add image stamp...</b> adds your own picture (PNG/JPG) to the stamp list.</li>
</ul>

<h2 id="edittext">Editing the PDF's own text</h2>
<ul>
<li>Edit text tool (Ctrl+E): click a line of text. Type the change; drag the bar above the
box to move the text, drag the corner grip to make it wrap. Click elsewhere or press
Ctrl+Enter to finish, Escape to cancel.</li>
<li>Highlights, underlines, strikeouts, comments and sticky notes on that line move with it.</li>
<li>The original font is used when it's embedded or installed; otherwise the closest standard
font (the status bar tells you which).</li>
</ul>

<h2 id="measure">Measuring</h2>
<ul>
<li>Set the drawing scale first: Measure &gt; Set scale (presets such as 1/4" = 1'-0", 1:100),
or <b>Calibrate</b>: drag along a known dimension and type its real length.</li>
<li><b>Length</b> (Shift+M), <b>Polylength</b>, <b>Area</b> with perimeter (Shift+A), and
<b>Count</b> (Shift+C, with named groups). Values update when you edit the markup or change
the scale.</li>
<li><b>Measurement summary</b> totals everything and exports to CSV.</li>
</ul>

<h2 id="pages">Pages</h2>
<ul>
<li><b>Rotate page left / Rotate page right:</b> Ctrl+Shift+Minus / Ctrl+Shift+Plus.</li>
<li><b>Reorder:</b> unlock the page list (lock button above the thumbnails), then drag
thumbnails; or Move page up / Move page down (Ctrl+Shift+Up / Down).</li>
<li>Pages menu: Insert pages from file, Insert blank page after current, Extract pages to new
file, Delete page.</li>
<li><b>Layers</b> tab: show or hide CAD / optional-content layers.</li>
<li><b>Bookmarks</b> tab: add, rename, reorder and indent bookmarks.</li>
</ul>

<h2 id="forms">Forms</h2>
<ul>
<li><b>Fill in:</b> with Select or Hand, click a field. Tab moves to the next text field.</li>
<li><b>Create:</b> Forms menu: text field, checkbox, option button, dropdown, signature field.
Double-click a field to change its name and options.</li>
</ul>

<h2 id="sign">Signatures and protection</h2>
<ul>
<li><b>Wet signature / initials:</b> Sign &gt; Set up my signature and Set up my initials
(draw or load an image, optional PIN). Then Sign (G) or Initials (I) and click to place, with the date.</li>
<li><b>Digital signature:</b> Sign &gt; Digitally sign with certificate (a personal certificate
or your company's .pfx/.p12). Signed files open read-only so the signature stays valid.
Digital signature details shows who signed and whether the signature is still valid.</li>
<li><b>Protect document from changes when saved</b> and <b>Unlock with password</b> are in
the Sign menu.</li>
</ul>

<h2 id="document">Document tools</h2>
<ul>
<li><b>Recognize text (OCR):</b> makes scanned pages searchable and selectable.</li>
<li><b>Redaction:</b> the Redact (mark text or area) tool (Shift+R) or Search &amp; redact
marks areas; Apply redactions permanently removes what's underneath.</li>
<li><b>Header &amp; footer, page numbers, Bates</b>, <b>Watermark</b>,
<b>Compress (save a smaller copy)</b>, <b>Compare documents</b> (changes clouded in red and
blue), <b>Flatten</b> (make markups part of the page).</li>
<li><b>Export</b> (File &gt; Export to): Microsoft Word (.docx), Microsoft Excel (.xlsx),
Microsoft PowerPoint (.pptx), AutoCAD drawing (.dxf), Images (PNG), Images (JPEG),
Plain text (.txt).</li>
</ul>

<h2 id="shortcuts">Keyboard shortcuts</h2>
<table border="1" cellpadding="3" cellspacing="0">
<tr><th>Key</th><th>Action</th></tr>
<tr><td>V / H</td><td>Select / Hand</td></tr>
<tr><td>Ctrl+E</td><td>Edit text</td></tr>
<tr><td>Ctrl+Shift+H / U / X</td><td>Highlight / Underline / Strike</td></tr>
<tr><td>C / N / T / K</td><td>Comment / Note / Text box / Callout</td></tr>
<tr><td>R / E / D / Y</td><td>Rectangle / Ellipse / Cloud / Polygon</td></tr>
<tr><td>L / A / Shift+L / P</td><td>Line / Arrow / Polyline / Pen</td></tr>
<tr><td>M / X</td><td>Stamp / Eraser</td></tr>
<tr><td>G / I</td><td>Signature / Initials</td></tr>
<tr><td>Shift+M / Shift+A / Shift+C</td><td>Length / Area / Count</td></tr>
<tr><td>Shift+R</td><td>Redact</td></tr>
<tr><td>Shift (while drawing)</td><td>45&deg; lines, squares and circles</td></tr>
<tr><td>Ctrl+click, Ctrl+drag</td><td>Select several markups</td></tr>
<tr><td>Escape, Escape twice</td><td>Clear selection, back to Select</td></tr>
<tr><td>Delete</td><td>Delete selected markups</td></tr>
<tr><td>Ctrl+Shift+] / Ctrl+] / Ctrl+[ / Ctrl+Shift+[</td><td>Front / forward / backward / back</td></tr>
<tr><td>Left / Right</td><td>Previous / next page</td></tr>
<tr><td>Ctrl+Shift+Plus / Minus</td><td>Rotate page</td></tr>
<tr><td>Ctrl+Shift+Up / Down</td><td>Move page</td></tr>
<tr><td>Ctrl+2 / Ctrl+0 / Ctrl+1</td><td>Fit width / fit page / actual size</td></tr>
<tr><td>Ctrl+F, F3, Shift+F3</td><td>Find, next, previous</td></tr>
<tr><td>F1</td><td>This manual</td></tr>
<tr><td>F11</td><td>CAD-style mouse on / off</td></tr>
<tr><td>Hold wheel + drag</td><td>Pan (any tool)</td></tr>
<tr><td>F4 / F6 / F7 / F8 / F9 / F10</td><td>Pages / Properties / Markups / Tool chest / Bookmarks / Split view</td></tr>
</table>
<p>Change any shortcut in View &gt; Keyboard shortcuts.</p>
"""


def sections():
    """[(anchor id, title)] of the manual's chapters, in order."""
    return re.findall(r'<h2 id="([^"]+)">(.*?)</h2>', MANUAL)


class ManualDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("KanzonasPDF user manual")
        self.resize(980, 720)
        lay = QVBoxLayout(self)

        bar = QHBoxLayout()
        bar.addWidget(QLabel("Find in manual:"))
        self.find = QLineEdit()
        self.find.setClearButtonEnabled(True)
        self.find.setPlaceholderText("Type a word, then Enter for the next match")
        self.find.returnPressed.connect(self.find_next)
        bar.addWidget(self.find, 1)
        nxt = QPushButton("Next")
        nxt.clicked.connect(self.find_next)
        bar.addWidget(nxt)
        lay.addLayout(bar)

        split = QSplitter()
        self.contents = QListWidget()
        self.contents.setMaximumWidth(260)
        self._anchors = []
        for anchor, title in sections():
            self.contents.addItem(title.replace("&amp;", "&"))
            self._anchors.append(anchor)
        self.contents.currentRowChanged.connect(self._jump)
        split.addWidget(self.contents)
        self.text = QTextBrowser()
        self.text.setOpenLinks(False)
        self.text.setHtml(MANUAL)
        split.addWidget(self.text)
        split.setStretchFactor(1, 1)
        lay.addWidget(split, 1)

        close = QPushButton("Close")
        close.clicked.connect(self.close)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(close)
        lay.addLayout(row)
        QShortcut(QKeySequence.Find, self, activated=self.find.setFocus)

    def _jump(self, row):
        if 0 <= row < len(self._anchors):
            self.text.scrollToAnchor(self._anchors[row])

    def show_section(self, anchor):
        if anchor in self._anchors:
            self.contents.setCurrentRow(self._anchors.index(anchor))

    def find_next(self):
        word = self.find.text().strip()
        if not word:
            return False
        if self.text.find(word):
            return True
        # wrap around to the top
        cur = self.text.textCursor()
        cur.movePosition(cur.MoveOperation.Start)
        self.text.setTextCursor(cur)
        return self.text.find(word)


# ---- keeping the manual complete -------------------------------------------------
# Menu commands that need no explanation, or are covered under another name.
NOT_DOCUMENTED = {"exit", "about", "user manual", "close tab"}


def _norm(text):
    text = text.split("\t")[0].replace("&&", "\0").replace("&", "").replace("\0", "&")
    return " ".join(text.replace("...", "").replace("…", "").split()).strip().lower()


def _plain_manual():
    from PySide6.QtGui import QTextDocument
    d = QTextDocument()
    d.setHtml(MANUAL)
    return " ".join(d.toPlainText().split()).lower()


def missing_from_manual(window):
    """Names of menu commands (every menu, every tool) that the manual never mentions.
    Used by the self-test so a new feature can't ship without being documented."""
    text = _plain_manual()
    missing = []

    def walk(menu):
        for a in menu.actions():
            if a.menu():
                if _norm(a.text()) != "open recent":      # the list of recent files
                    walk(a.menu())
                continue
            if a.isSeparator() or not a.isEnabled() and not a.text():
                continue
            name = _norm(a.text())
            if not name or name in NOT_DOCUMENTED or not a.isVisible():
                continue
            if a.isEnabled() is False and a.toolTip() == a.text():
                continue
            if name not in text and name not in missing:
                missing.append(name)
    for top in window.menuBar().actions():
        if top.menu():
            walk(top.menu())
    return missing
