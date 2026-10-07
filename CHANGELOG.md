# Changelog

Each revision gets a version number. It's shown in the window title and Help > About,
and the Windows download is named `KanzonasPDF-v<version>-windows.zip`.

| Version | Commit | Changes |
| --- | --- | --- |
| 0.18 | (this) | User manual kept complete: names every menu command; self-test (and so the Windows build) fails if a command is missing from the manual; CLAUDE.md rules require manual, version and changelog updates with every change |
| 0.17 | 3b481e8 | Built-in user manual: Help > User manual (F1), with contents list and search |
| 0.16 | 7e0603e | Markups on a line of text (highlights, underlines, comments, notes) move with the text; Shift while drawing lines/arrows/measurements/polylines snaps to 45° steps; Shift draws perfect squares and circles and keeps proportions when resizing from a corner; rotation for shapes, lines, ink and stamps (Properties panel or round handle, Shift = 15° steps), text boxes in 90° steps; multi-select (Ctrl+click, drag a box); Arrange menu and toolbar: align (to first selected by default, or last selected, whole selection, page), distribute, bring to front / send to back; Escape twice returns to the Select arrow; stamp name and date are separate options and can be removed from an existing stamp; fixed rectangles and ellipses growing slightly every time they were edited |
| 0.15 | 781fe71 | Fixes: edit-text box can be moved and resized; I-beam cursor for text markup tools; letter-by-letter text selection; click shapes to edit them while drawing; "No border" option; American spelling. CAD: tiled rendering (fast, low-memory high zoom on big sheets), Layers panel, upright stamps and measurement labels on rotated sheets, redaction keeps CAD linework crossing the box, tiled OCR for large scanned drawings (far less memory, better small text); CAD test suite (tests/) |
| 0.14 | 67efd6a | Toolbar icons (labels optional); dark / light / match-Windows theme; split view (second independently scrolling view); reopens each file at its last page and zoom; customizable keyboard shortcuts; fixed Strike shortcut clash with Save As (now Ctrl+Shift+X) |
| 0.13 | d30c79a | Bookmarks panel (add, rename, delete, reorder, indent); redaction (mark text/areas, search & redact, apply permanently, scrub hidden data); header & footer with page numbers, dates and Bates numbering; text and image watermarks; compress to a smaller copy; certificate-based digital signatures (personal or CA certificate, optional certify-lock, validation banner, trust signers) |
| 0.12 | 2b05045 | Tool chest (save styled markups, one-click reuse without changing defaults, export/import to share); Compare documents (red = removed, blue = added, clouds around every change, listed in Markups list) |
| 0.11 | 48a58b1 | Measurement: calibrate or preset scales (architectural, engineering, metric), Length, Polylength, Area + perimeter, Count (groups), live readout, values drawn on the PDF and updated when edited or rescaled, measurement summary with CSV export, scale in status bar |
| 0.10 | 4876a1e | Markups list (filter, click to jump, export CSV); stamps (15 presets, custom text, your own images, name + date); revision clouds; polygons and polylines (cloud option); callouts; author name on markups; shapes grouped under one toolbar button |
| 0.9 | f997718 | Saved wet signature & initials (draw or scan, optional PIN), click to place with date; fill in forms (text, checkbox, option, dropdown, signature fields, Tab to next); create forms; protect document from changes; export to Word, Excel, PowerPoint, AutoCAD DXF, images, text |
| 0.8 | ee4316e | Left/Right arrow keys change page; comments can highlight, underline, strike out or squiggle; Flatten (Tools menu); lock/unlock button for dragging page thumbnails (locked by default) |
| 0.7 | 5e705d5 | Version numbers in the app, the download name and this changelog |
| 0.6 | 5fd2bad | Edit annotations after creating them (move, resize, restyle); properties panel with saved per-tool defaults; text box text/border/fill colors; comment on text; live text selection; edit text in place (move, wrap); fixed missed character; rotate with Ctrl+Shift+Plus/Minus; drag-and-drop page thumbnails; Ctrl+Shift+Up/Down to move pages |
| 0.5 | b1ce862 | Edit existing text (line by line); Ctrl+Enter finishes note/text box dialogs |
| 0.4 | 1448633 | OCR; fixed text box error; fixed over-selecting highlight and eraser; eraser cursor; rotate shortcut change |
| 0.3 | 9a37a10 | Double-click launcher (Start KanzonasPDF.bat) |
| 0.2 | 7e41ba9 | Automatic Windows .exe build |
| 0.1 | e0c7f81 | First version: viewing, markup, page tools, search, print |
