# KanzonasPDF

A free, fast PDF reader and editor for Windows, built on [PyMuPDF](https://pymupdf.readthedocs.io/) (MuPDF) and Qt (PySide6).

## Features (v0.1)

- Tabs, drag-and-drop to open, recent files, password-protected PDFs
- Continuous scrolling, Ctrl+mouse-wheel zoom, fit width or page, page thumbnails
- Find with all matches highlighted (Enter, F3 or Shift+F3)
- Select text and copy it to the clipboard
- Markup: highlight, underline, strikeout, sticky note, text box, rectangle, ellipse,
  line, arrow and freehand pen, in any colour. Double-click an annotation to edit its text,
  and use the Eraser to delete one.
- Pages: rotate, delete, reorder, insert a blank page, insert pages from another PDF (merge),
  extract a range of pages to a new file
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

| Key | Tool |
| --- | --- |
| V / H | Select / Hand |
| Ctrl+Shift+H / U / S | Highlight / Underline / Strikeout |
| N / T | Note / Text box |
| R / E / L / A / P | Rectangle / Ellipse / Line / Arrow / Pen |
| X | Eraser |

## Licence

PyMuPDF is AGPL-3.0, so KanzonasPDF must also be distributed under the AGPL-3.0,
with its source code available. That's fine for a free, open-source giveaway.

## Known limitations

- Saving rewrites the whole file, which invalidates existing digital signatures.
- You can't edit existing page text yet (only add annotations and text boxes).
- No OCR, form-field editing or measurement tools yet.
