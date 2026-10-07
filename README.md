# KanzonasPDF

A free, fast PDF reader and editor for Windows, built on [PyMuPDF](https://pymupdf.readthedocs.io/) (MuPDF) and Qt (PySide6).

## Features

- Tabs, drag-and-drop to open, recent files, password-protected PDFs
- Continuous scrolling, Ctrl+mouse-wheel zoom, fit width or page
- Page thumbnails: click to jump, **drag to reorder pages**
- Find with all matches highlighted (Enter, F3 or Shift+F3)
- Text selection that shows exactly what's selected as you drag; copy, highlight,
  underline, strike out
- **Comment on text**: select text, it's highlighted and a note box appears beside it
  (also visible as a comment in Acrobat)
- Markup: sticky note, text box, rectangle, ellipse, line, arrow, freehand pen
- **Properties panel** (F6): colours (line, fill, text), line width, font size, arrowhead
  style, opacity
  - With nothing selected it sets each tool's **default style, saved for next time**
  - With an annotation selected it restyles that annotation
- **Edit annotations after creating them** (Select tool): click to select, drag to move,
  drag handles to resize or move line ends, double-click to edit text, Delete to remove
- Eraser: click one annotation, or drag a box around several
- **Edit existing text in place** (Edit text tool, Ctrl+E): click a line, type, Enter.
  Drag the blue bar to move it, drag the corner to set a width (text wraps).
  Keeps size, colour and direction; uses the original font when possible
- Pages: rotate, delete, reorder, insert a blank page, insert pages from another PDF (merge),
  extract a range of pages to a new file
- OCR (Tools > Recognize text): makes scanned pages searchable and selectable. Works offline,
  handles sideways (landscape) scans.
- Undo and redo (Ctrl+Z, Ctrl+Y), print
- Annotations are standard PDF annotations, so Acrobat and other viewers can see them

## Run it (Windows)

1. Install Python 3.10+ from https://www.python.org/downloads/ (tick "Add to PATH").
2. Double-click **`Start KanzonasPDF.bat`**. The first time, it installs the libraries it needs.

   Or from a command prompt: `pip install -r requirements.txt`, then `python run.py`.

## Build a standalone .exe

Double-click `build_windows.bat`. The app ends up in `dist\KanzonasPDF\KanzonasPDF.exe`.
You can zip that folder and give it to anyone; they don't need Python.

## Keyboard shortcuts

| Key | Action |
| --- | --- |
| V / H | Select / Hand |
| Ctrl+E | Edit text (click a line) |
| Ctrl+Shift+H / U / S | Highlight / Underline / Strikeout |
| C | Comment on text |
| N / T | Note / Text box |
| R / E / L / A / P | Rectangle / Ellipse / Line / Arrow / Pen |
| X | Eraser (click one, or drag a box around several) |
| Delete / Esc | Delete / deselect the selected annotation |
| Ctrl+Enter | Finish typing in note / text box / comment dialogs |
| Ctrl+Shift+Plus / Minus | Rotate page clockwise / counter-clockwise |
| Ctrl+Shift+Up / Down | Move current page up / down |
| F4 / F6 | Show/hide page thumbnails / properties panel |

## Licence

PyMuPDF is AGPL-3.0, so KanzonasPDF must also be distributed under the AGPL-3.0,
with its source code available. That's fine for a free, open-source giveaway.

## Known limitations

- Saving rewrites the whole file, which invalidates existing digital signatures.
- Text editing works one line at a time; it doesn't reflow the rest of a paragraph.
  If the original font isn't installed, a close standard font is used.
- Arrowhead size follows line width (that's how PDF arrows work).
- Text box borders use their own colour in this app; Acrobat may redraw a box's border
  in its text colour if you edit that box in Acrobat.
- No form-field editing or measurement tools yet.
- OCR caps large sheets at 6000 px on the long side, so very small text on big drawings may be missed.
