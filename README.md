# KanzonasPDF

A free, fast PDF reader and editor for Windows, built on [PyMuPDF](https://pymupdf.readthedocs.io/) (MuPDF) and Qt (PySide6).

## Features

- Tabs, drag-and-drop to open, recent files, password-protected PDFs
- Continuous scrolling, Ctrl+mouse-wheel zoom, fit width or page
- Page thumbnails: click to jump, drag to reorder pages (unlock first with the lock button)
- Left/Right arrow keys: previous/next page
- Find with all matches highlighted (Enter, F3 or Shift+F3)
- Text selection that shows exactly what's selected as you drag; copy, highlight,
  underline, strike out
- **Comment on text**: select text, it's marked (highlight, underline, strikeout or squiggly,
  set in the Properties panel) and a note box appears beside it
  (also visible as a comment in Acrobat)
- Markup: sticky note, text box, callout, rectangle, ellipse, revision cloud, polygon (optionally
  clouded), line, arrow, polyline, freehand pen
- **Stamps**: Approved, Reviewed, Draft and 12 more, your own text, or your own images; adds
  your name and the date
- **Measurement** (Measure menu): set the scale by calibrating against a known dimension or
  picking a preset (1/4" = 1'-0", 1" = 20', 1:100, ...); measure length, polylength, area and
  perimeter, and count items in groups. Values are drawn on the PDF, update when you edit a
  vertex or change the scale, and total up in Measure > Measurement summary (CSV export)
- **Tool chest** (F8): save a styled markup (e.g. a magenta REVISE cloud) as a named tool and
  reuse it with one click; export/import chests to share them
- **Compare documents** (File menu): overlays this document on an earlier revision (red =
  removed, blue = added) and clouds every change
- **Bookmarks** (F9): view, add, rename, delete, reorder and nest the PDF outline
- **Redaction** (Document menu): mark text or areas, or search & redact every occurrence; apply
  to permanently delete what's underneath (optionally scrub metadata and hidden data)
- **Header & footer** with page numbers, dates, file name and **Bates numbering**; text or
  image **watermarks**; **compress** to a smaller copy
- **Digital signatures** (Sign menu): sign with your own certificate (created for you) or a
  .pfx/.p12 from a certificate authority; optional lock; signed files open read-only with a
  banner saying who signed and whether anything changed since
- **Markups list** (F7): every markup in a table; filter, sort, click to jump, export to CSV
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
- Flatten (Tools menu): burn annotations and form fields into the page, all pages or current
- **Signature & initials** (Sign menu): set up once by drawing or loading a scan/photo of your
  wet signature (background removed automatically), optionally protected by a PIN. Then click
  to place it with today's date. It's written into the page, not a movable annotation
- **Protect document from changes when saved** (offered after signing)
- **Forms**: fill in any PDF form with Select or Hand (Tab moves to the next field); create
  forms with text fields, checkboxes, option buttons, dropdowns and signature fields
- **Export** (File > Export to): Word, Excel, PowerPoint, AutoCAD DXF, PNG/JPEG, text
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
| K / D / Y / Shift+L / M | Callout / Cloud / Polygon / Polyline / Stamp |
| F7 / F8 / F9 | Markups list / Tool chest / Bookmarks |
| Shift+R | Redact |
| Shift+M / Shift+A / Shift+C | Measure length / area / count |
| G / I | Place signature / initials |
| Delete / Esc | Delete / deselect the selected annotation |
| Ctrl+Enter | Finish typing in note / text box / comment dialogs |
| Ctrl+Shift+Plus / Minus | Rotate page clockwise / counter-clockwise |
| Ctrl+Shift+Up / Down | Move current page up / down |
| Left / Right | Previous / next page (Shift+Left/Right scrolls sideways) |
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
- Protection uses standard PDF permissions: Acrobat, PDF-XChange and this app honour them,
  but they're not tamper-proof against determined tools; use a digital signature for that.
- A personal certificate proves a document is unchanged, but others' software only shows your
  identity as verified if they trust your certificate (or you use one from a certificate
  authority). Signing via the Windows certificate store / smart cards isn't supported yet.
- Export: Word works best for ordinary text documents; Excel needs real (not scanned) tables;
  PowerPoint slides are page pictures; AutoCAD export is DXF (not DWG) and leaves out images.
- Measurement labels on rotated pages are drawn in the page's unrotated direction.
- OCR caps large sheets at 6000 px on the long side, so very small text on big drawings may be missed.
