"""Built-in user manual (Help > User manual, F1).

The manual is kept here as HTML so it is always packaged with the app (no data files).
Each <h2 id="..."> becomes an entry in the contents list.
"""

import re

from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QVBoxLayout, QListWidget, QTextBrowser,
                               QLineEdit, QPushButton, QSplitter, QLabel)

MANUAL = """
<h1>KanzonasPDF user manual</h1>
<p>A free PDF reader and editor. Use the contents list on the left, or type in the
<b>Find in manual</b> box above.</p>

<h2 id="audit-fixes">Document protection and safe editing</h2>
<p>Apply redactions removes any vector path touching a mark, even the part of that path
outside the box. Applying also scrubs metadata, attachments, hidden text, and scripts
unless you turn that off. Check the result before sharing. Search &amp; redact
removes matching annotations completely, including private stamp data and appearances.</p>
<p>Saving edits to an already protected PDF keeps its own protection exactly as it was: the
same open password, permissions password and permissions, with no password needed. So a form
locked with a permissions password you don't know can still be filled in and saved, and stays
locked. (Only in the rare case that the protection can't be carried over, KanzonasPDF asks
for the original passwords; a failed or canceled prompt leaves the existing file intact.)
Search &amp; redact only looks at the text of markups people see (comments, stamp labels,
names and dates), not at their colors or shapes, so redacting a word like "fill" doesn't
delete unrelated markups. Newly protected documents are excluded from automatic backups,
and an existing recovery copy is removed when protection is added. Each recovery copy has
its own unique identity, even for files with the same name.</p>
<p>Copying, extracting and exporting require copying permission; Print requires printing
permission and uses at most 150 dpi when high-quality printing is forbidden. Form filling
and adding markups honor their separate permissions. Flattening selected pages preserves
page labels, outgoing links and drawing calibration. Excel export writes PDF text as literal
cell text, including text starting with an equals sign. OCR disables ONNX Runtime
telemetry before creating recognition sessions.</p>
<h2 id="start">Getting started</h2>
<ul>
<li><b>Open a PDF:</b> File &gt; Open (Ctrl+O), drag a file onto the window, or pick one from
File &gt; Open recent. Each file opens in its own tab, at the page and zoom you left it.</li>
<li><b>Save:</b> Ctrl+S. <b>Save as:</b> Ctrl+Shift+S. Undo is Ctrl+Z, redo is Ctrl+Y.
Up to 30 steps are kept; on very large PDFs fewer, so undo history stays within a memory budget
(256 MB per document, 512 MB for all open documents together; the oldest steps go first).</li>
<li><b>Panels:</b> Pages/Bookmarks/Layers on the left (F4), Properties on the right (F6),
Markups list (F7), Tool chest (F8), Bookmarks (F9), Split view (F10).</li>
<li><b>Ribbon:</b> commands are grouped on tabs: Home, Markup, Measure, Arrange, Review,
Protect, Forms, Pages and View. Open, save, print, undo and redo sit left of the tabs, and the
Find box sits right of them. The bottom bar (status bar, bottom right) has page navigation (first,
previous, page number, next, last page), Fit page, Fit width, Actual size, a zoom slider and the
zoom box with zoom out / zoom in, like PDF-XChange Editor. The ribbon is compact: two rows of
buttons. If the window is too narrow for a tab, scroll it sideways with the mouse wheel or the
thin bar under it. View &gt; <b>Show group names on ribbon</b> adds a name under each group of
buttons (a little taller, like Microsoft Office). View &gt; <b>Show menu bar</b> (Ctrl+Shift+M)
hides or shows the File, Edit, View... menu bar; when it's hidden, the &#9776; button at the right
of the ribbon tabs has every menu, and all keyboard shortcuts still work. <b>Collapse ribbon</b>
(Ctrl+F1, or double-click a tab) shows only the tab names; click a tab to open it again. Untick
View &gt; <b>Ribbon (instead of toolbars)</b> for the classic compact toolbars (zoom, page number
and Find then go back to the top toolbar). The menus always have every command.</li>
<li><b>Panel strip:</b> the icons on the left edge open the Pages, Bookmarks, Layers and
Objects panels; click the lit icon again to fold the panel away and get more room for the page.
The Markups list and Attachments icons are there too. View &gt; <b>Show panel strip (left
edge)</b> hides the strip; the panels then show their names as tabs at the bottom instead.</li>
<li><b>Theme:</b> View &gt; Theme (Match Windows, Light, Dark). View &gt; Show text labels on
toolbars adds names under the icons. Hover over any toolbar button or box for a tooltip
saying what it does and its keyboard shortcut.</li>
</ul>

<h2 id="free">Free of charge</h2>
<p>Official KanzonasPDF releases stay free of charge for personal and commercial use: no subscriptions, trial expiration, paid feature tiers, required account or required paid cloud service. Optional donations never unlock features. The source code is available under the GNU AGPL-3.0.</p>

<h2 id="install">Installing, updating and uninstalling</h2>
<ul>
<li>Run <b>KanzonasPDF-v&lt;version&gt;-setup.exe</b>. No administrator rights are needed: it
installs for your Windows account (choose "all users" on the first page if you're an admin and
want that). It adds a Start-menu shortcut, optionally a desktop shortcut, and offers
KanzonasPDF as an app for opening PDFs.</li>
<li><b>Make it your default PDF app:</b> Windows doesn't let installers do this silently. Right-click
any PDF &gt; Open with &gt; Choose another app &gt; KanzonasPDF, and tick "Always use this app".</li>
<li>Opening another PDF while KanzonasPDF is running opens it as a new tab in the same window.</li>
<li><b>Update:</b> run the newer setup over the old one; there's no need to uninstall first.
It closes KanzonasPDF if it's running, installs in the same place, and keeps your settings,
signatures, stamps and tool chest. <b>Uninstall:</b> Windows Settings &gt; Apps, or the uninstaller in the install folder.</li>
<li><b>Portable version</b> (<b>KanzonasPDF-portable.zip</b>): no installation. Unzip the KanzonasPDF folder
anywhere (a USB stick, a network drive, your Documents) and run KanzonasPDF.exe. Because of the
portable.txt file inside, your settings, signatures, stamp images and certificate are kept in a
<b>data</b> folder next to the program instead of the computer's registry and user folders, so
they travel with the folder. The window title and Help &gt; About say <b>(portable)</b> when
this copy is running in portable mode. Keep the whole folder together. The download has the same name for every version
(KanzonasPDF-portable.zip, with a KanzonasPDF folder inside), so the program's path never has to
change. <b>To update</b>, use <b>Update now</b> in the update notice or in Help &gt; Check for
updates: KanzonasPDF downloads the new portable zip only from GitHub, and only installs it
when the file's sha256 matches the digest published with that release. It asks to save open
documents, closes, replaces its program files in the same folder and starts again. Or do it by hand: close
KanzonasPDF and unzip the new download over the same folder, replacing the files. Your data folder is kept, and if you made KanzonasPDF.exe your default PDF
app (Windows Settings &gt; Apps &gt; Default apps), it stays the default. Tip: if Windows'
Extract All suggests a new folder name, change it to the folder you already use.
(Opening an attached file still uses Windows' temporary folder.)</li>
<li><b>Help &gt; Check for updates:</b> asks GitHub whether a newer KanzonasPDF has been released.
A box tells you the answer; if there's a newer version, <b>Download</b> opens its release page in
your browser. The automatic check instead shows a notice at the bottom of the window with
<b>Download</b>, <b>Skip this version</b> and <b>Later</b> (the portable version also has
<b>Update now</b>, which updates it in place; see above). Nothing is downloaded or installed
until you click a button.
With Help &gt; <b>Check for updates automatically</b> ticked (the default) the app checks
quietly once a day, a few seconds after it starts; untick it to never contact GitHub. If your
network blocks GitHub, the automatic check simply finds nothing.</li>
<li>The <b>KanzonasPDF-windows.zip</b> download is the same program without the portable.txt file: it runs
from any folder but stores settings on the computer like the installed version.</li>
</ul>

<h2 id="navigate">Moving around</h2>
<ul>
<li><b>Next / previous page:</b> the &#9664; &#9654; buttons beside the page number (bottom right
with the ribbon, in the toolbar with classic toolbars), the Right / Left arrow keys, or type a page number and press Enter.</li>
<li><b>Zoom in / Zoom out:</b> Ctrl+Plus / Ctrl+Minus, Ctrl+mouse wheel, or the zoom box.
Fit width (Ctrl+2), fit page (Ctrl+0), actual size (Ctrl+1). Documents open at Fit width, at
the page you were on last time; change this in File &gt; Preferences &gt; Opening documents.
Fit width and Fit page keep fitting when the window or a side panel changes size, until you
choose a zoom yourself.</li>
<li><b>Page thumbnails</b> (F4) shows or hides the left panel.</li>
<li><b>Links in the PDF:</b> with the Hand or Select tool, point at a link to see where it goes
(the pointer becomes a hand) and click it. A link to a page in the document goes there. A web or
email address asks first, then opens in your browser or email program (tick <b>Don't ask
again</b> to skip the question from then on). A link to another PDF opens it in a new tab; a
link to another kind of file asks before opening it; links that would start a program or script
are refused.</li>
<li><b>Pan:</b> Hand tool (H; KanzonasPDF starts with the Hand tool), the scroll bars, or <b>hold the mouse wheel down and drag</b>
(works with any tool). <b>Shift+wheel</b> always scrolls left and right, including when CAD-style
mouse is off and when one wheel step would otherwise turn the page. Shift+Left/Right scrolls
sideways too.</li>
<li><b>CAD-style mouse (wheel zooms, hold wheel to pan)</b> (View menu, toolbar button, F11):
like AutoCAD, the scroll wheel zooms in and out around the cursor and holding the wheel down
moves the sheet, so you can navigate a drawing while any markup tool is active. Like Bluebeam,
hold <b>Ctrl</b> and turn the wheel to scroll up and down. Shift+wheel scrolls left and right
here too, the same as with CAD-style mouse off. The pages sit on an open canvas, so you can drag them anywhere in the window (with the
wheel held down or the Hand tool), even when the whole page already fits. Your choice is
remembered.</li>
<li><b>Scroll one page per wheel step</b> (View menu): when the whole page fits in the window,
top to bottom and side to side (for example after <b>Fit page</b>), each step of the scroll wheel
jumps to the next or previous page, centered, instead of scrolling a little. As soon as you zoom
in so that any edge of the page is outside the window, the wheel scrolls normally. Hold
<b>Shift</b> to scroll left and right instead of turning the page. On by default; turn it off for smooth scrolling. Your choice is remembered. (With CAD-style mouse on, the wheel zooms
instead.)</li>
<li><b>Find text:</b> Ctrl+F, then Enter / F3 for the next match and Shift+F3 for the previous.
The search starts at the page you're on and shows the first match as soon as it finds it; on
long documents it keeps searching the rest in the background (the status bar shows "Match 3
of 120+" and how many pages are done) while you keep working. Changing the text or editing
the document starts a fresh search.</li>
<li><b>Split view</b> (F10) shows a second, independently scrolling view of the same file.</li>
</ul>

<h2 id="select">Selecting and editing markups</h2>
<ul>
<li><b>Select tool (V):</b> drag across text to select it, including across the gap between
pages (it stays highlighted; see Copy, cut and paste below). Click a markup to select it, then drag
it to move it, drag a square handle to resize it, or change its look in the Properties panel.</li>
<li>With a drawing tool active (rectangle, line, callout, ...), clicking an existing markup selects
it too, so you don't have to switch back to the arrow. The <b>Hand tool</b> works the same way:
click a markup (a highlight, a note, a shape...) to select it; drag anywhere else to move the
page.</li>
<li><b>Several markups:</b> Ctrl+click each one, or drag a box from empty space with the Select
tool (Ctrl+drag always draws a selection box). Drag any selected markup to move them all;
Delete removes them all; Properties changes apply to all of them.</li>
<li><b>Delete:</b> Delete or Backspace, or right-click the markup &gt; <b>Delete</b>.
<b>Edit a comment's text:</b> double-click it, or right-click it &gt; <b>Edit text...</b>.
If you right-click highlighted text that's selected, the menu offers <b>Delete highlight</b>.
In the Markups list (F7), double-click a row to edit its text; right-click a row for
<b>Edit text...</b> and <b>Delete</b>, or press Delete.</li>
<li><b>Move with the arrow keys:</b> with markups selected (or pictures and shapes selected with
Edit objects), each press of an arrow key moves them 1 pt; <b>Shift+arrow</b> moves 10 pt and
<b>Ctrl+arrow</b> 0.1 pt, for fine adjustments. A series of presses is one Ctrl+Z. Markups tied to
text (highlights, underlines, strikeouts) stay with their text. With nothing selected, Left and
Right turn the page as usual.</li>
<li><b>Escape</b> clears the selection; <b>Escape twice</b> switches back to the Select (arrow) tool.</li>
</ul>

<h2 id="clipboard">Copy, cut and paste</h2>
<ul>
<li><b>Text:</b> with the Select tool, drag across text; the selection stays highlighted.
The drag can cross the gap between pages, and the pages in between are included.
<b>Copy</b> (Ctrl+C) puts it on the clipboard, with a blank line between pages;
<b>Cut</b> (Ctrl+X) also removes those letters
from the page (Undo brings them back). <b>Select all text</b> (Ctrl+A) selects the whole page's
text. Escape or a click elsewhere clears the selection.</li>
<li><b>Right-click menu:</b> right-click the page for Cut, Copy, Paste, Delete (for selected
markups) and Select all text. With text selected, it also offers Highlight, Underline, Strike out,
Comment on text... and Mark for redaction for that text. Right-clicking a markup selects it
first.</li>
<li><b>Markups:</b> select one or more markups, then Copy or Cut. <b>Paste</b> (Ctrl+V) puts them
where the mouse is, on any page or in another open document.</li>
<li><b>Duplicate</b> (Ctrl+D): copies of the selected markups appear slightly offset, selected
so you can drag them into place. In the page list, Ctrl+D duplicates the selected pages.</li>
<li><b>Pictures and text from other programs:</b> Paste a copied picture (e.g. a screenshot)
as an image markup, or copied text as a text box, where the mouse is.</li>
<li><b>Pages:</b> unlock the page list (lock button above the thumbnails), select thumbnails
(Ctrl+click or Shift+click for several), then right-click or use the Pages menu:
<b>Copy pages</b>, <b>Cut pages</b>, <b>Paste pages after selected</b> and <b>Duplicate pages</b>. With the page list clicked, Ctrl+C, Ctrl+X, Ctrl+V and Ctrl+A work on pages. Pages
can be pasted into another open document too.</li>
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

<h2 id="review">Reviewing comments (Review menu)</h2>
<ul>
<li><b>Add:</b> the Comment tool (C) marks text and adds a comment beside it; the Note tool (N)
adds a sticky note anywhere.</li>
<li><b>Next comment</b> (Alt+Down) and <b>Previous comment</b> (Alt+Up) walk through every
comment and markup in reading order, page by page, selecting each one. The status bar shows
"Markup 3 of 12". It wraps around at the end.</li>
<li><b>Markups list</b> (F7): all markups in a table; filter, click to jump, export to CSV.</li>
<li><b>Show markups:</b> untick to hide every comment and markup and see the page as if
unmarked. Nothing is deleted; tick it again to bring them back. <b>Show comment boxes</b>
hides just the yellow boxes beside commented text.</li>
<li><b>Delete comments:</b> everyone's, only yours, or only one person's, on all pages or the
current page. Undo brings them back.</li>
<li><b>Flatten comments:</b> makes comments and markups a permanent part of the page while form
fields stay fillable. (Document &gt; Flatten flattens form fields too.)</li>
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
<li><b>Erase content</b> (Shift+E; Home tab, Markup tab &gt; Erase, Tools menu): like Bluebeam's,
drag a box to permanently delete the page's own content inside it: text, images and lines.
Lines and curves that cross the edge of the box are cut there, so a wall running through the box
keeps its outside parts. A filled shape that crosses the edge stays whole (one entirely inside is
removed). Markups aren't touched (use the Eraser for those). Ctrl+Z undoes it. Unlike redaction it
leaves no black box; for confidential information use Redact, which also cleans hidden copies.</li>
<li><b>Capture area</b> (Shift+P; Home tab, Tools menu): like Bluebeam's Snapshot, drag a box to
copy that area, markups included. Ctrl+V in KanzonasPDF pastes it as an image markup at the
same size, on any page or in another document, made of the original <b>vector</b> content: lines
and text stay sharp at any zoom and in print, and you can move, resize and rotate it like any
image markup. Only what's inside the box is kept (text, pictures and lines outside it are
removed from the copy; a line crossing the edge is kept whole but only the inside part shows).
The capture also pastes as a picture into Word, Excel, email and other programs.</li>
</ul>

<h2 id="snap">Grid and snapping</h2>
<ul>
<li><b>Show grid</b> (View menu or toolbar) draws a grid over the page. It's only on screen:
it isn't saved in or printed with the PDF.</li>
<li><b>Grid settings</b> (View menu): the spacing in inches, millimeters or points, measured on
the paper, and how often a darker line is drawn. When zoomed far out, only the darker lines
are shown.</li>
<li><b>Snap to grid:</b> points you draw or drag jump to the nearest grid intersection.</li>
<li><b>Snap to objects:</b> points jump to nearby markup corners, edge midpoints, centers and
line ends, and to the drawing's own line ends, midpoints and corners (useful on CAD sheets).</li>
<li>The snap options are in the View menu and toolbar, in the <b>Grid &amp; snap</b> group of
the ribbon's View and Measure tabs and the <b>Snap</b> group of the Arrange tab, in Grid
settings, and in Preferences &gt; Pages and display.</li>
<li><b>Snap to page</b>:
points jump to the page's corners, the middles of its edges and its center, and onto its edges,
so a markup can be lined up exactly with the edge or the middle of the page.</li>
<li>A pink square shows an object snap, a green circle a page snap, a blue cross a grid snap.
When several are on, a nearby object wins, then the page, then the grid.</li>
<li>Snapping works for shapes, lines, measurements, polygons, callouts, text boxes, stamps,
notes and counts, and when moving or resizing markups (a moved markup snaps by its
top-left corner). The pen and text markup tools don't snap.</li>
<li><b>Hold Alt</b> while drawing or dragging to place a point freely, without snapping.</li>
</ul>

<h2 id="properties">Colors, borders and styles (Properties panel)</h2>
<ul>
<li>With a tool active, the Properties panel (F6) sets that tool's <b>default style</b>, saved
for next time. With a markup selected, it changes <b>that markup</b>.</li>
<li>Line color, fill (or <b>No fill</b>), <b>No border</b> for boxes and shapes, text color,
line width, font size, arrowheads, cloud border, opacity.</li>
<li><b>Reset defaults</b> puts a tool back to its original style.</li>
<li><b>Tool chest</b> (F8, or the View tab): your favorite markup styles, one click away. F8
or the button opens it and, when it's showing, closes it again (if it's behind the Properties
tab, it's brought to the front). Click an entry, then
draw: you get that tool with that color and size, and the tool's normal settings stay as they
were. It starts with a few ready-made entries (red revision cloud, yellow and green highlight,
red arrow, blue box, red note text box, yellow callout, APPROVED and REJECTED stamps); rename
or delete them (right-click). To save your own: draw and style a markup, select it and click
<b>Add</b>. <b>More</b> &gt; Add the starter tools brings the ready-made ones back; Export /
Import tool chest shares a chest with others.</li>
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
<b>Send backward</b> (Ctrl+[), <b>Send to back</b> (Ctrl+Shift+[). With pictures or shapes of
the page itself selected (Edit objects tool), these change their order on the page instead
(see Editing the PDF's own pictures and shapes).</li>
</ul>

<h2 id="objects">Objects panel and locking</h2>
<ul>
<li><b>Objects</b> tab (left panel, next to Pages, Bookmarks and Layers): every markup on the
current page, from front (top of the list) to back. Click a row to select that markup even
when it's completely covered by others; Ctrl/Shift+click selects several. Front, Up, Down
and Back change the stacking order.</li>
<li><b>Lock</b> column, or Arrange &gt; <b>Lock selected</b> (Ctrl+L): a locked markup behaves
as if it were part of the page. It can't be clicked, moved, selected or erased, and dragging
on it starts a selection box or a new markup instead. Untick Lock (or Arrange &gt;
<b>Unlock all markups</b>) to edit it again. The lock is the PDF's standard "locked" flag, so
Acrobat and PDF-XChange respect it too.</li>
<li><b>Show</b> column: hide a single markup (it stays in the file; untick Show markups in the
Review menu hides them all).</li>
<li>The last row, <b>Page content</b>, is the original PDF itself. Its text and drawing aren't
separate objects you can pick (a CAD sheet can contain over 100,000 line pieces); use Edit
text for its text and the Layers tab for CAD layers.</li>
</ul>

<h2 id="stamps">Stamps</h2>
<ul>
<li>Stamp tool (M): pick a stamp in Properties (Approved, Draft, ... or type your own text),
then click to place it.</li>
<li><b>Add my name</b> and <b>Add the date</b> are separate checkboxes. Changing them on a
placed stamp redraws it (a re-added date shows today's date).</li>
<li><b>Add image stamp...</b> adds your own picture (PNG/JPG) to the stamp list.</li>
<li><b>Fill-in stamps:</b> <b>Fill-in: PO # / Date ordered</b> and <b>Fill-in: Req # / Date
submitted</b> in the stamp list. When you click to place one, a box asks for the number and the
date (the date starts as today, in your Preferences &gt; You date format). Double-click a placed
one to change what it says; it resizes to fit.</li>
</ul>

<h2 id="images">Pictures and attached files (videos and more)</h2>
<ul>
<li><b>Image</b> tool: drag a box and pick a picture (PNG, JPEG, BMP, GIF, TIFF). It's fitted
inside the box keeping its proportions; just click instead to place it at its natural size.
The picture is embedded in the PDF at its original quality and file size. Move, resize
(Shift on a corner keeps its proportions), rotate, align and delete it like any markup;
Flatten makes it a permanent part of the page.</li>
<li><b>Attach file</b> tool: click where the paperclip icon should go and pick any file, such
as a video, spreadsheet or photo. The file is embedded inside the PDF, so it travels with it.
<b>Double-click the icon</b> to open the file in the program Windows uses for it (videos play
in your normal video player). Adobe Acrobat, Bluebeam and PDF-XChange can open these too.</li>
<li>Videos don't play inside the page: that only works in a few PDF readers, so attaching
is the reliable way to send a video with a PDF. Large files make the PDF just as much larger
(you're warned above 50 MB).</li>
<li><b>Attachments</b> (Document menu): every file attached to this PDF, including ones added
by other programs. Open, Save as, Go to its page, or Delete.</li>
<li>For your safety, an attached program or script (.exe, .bat, .js, .html, .htm, .dll,
.application, .msc, .iso and the like) is not opened. KanzonasPDF warns you and leaves the
file in the PDF. Use Save as and open it yourself if you trust it.</li>
</ul>

<h2 id="editobjects">Editing the PDF's own pictures and shapes</h2>
<ul>
<li>Edit objects tool (Shift+O; Home tab, Tools menu), like Bluebeam's Edit content: works on
the pictures (logos, photos, scans) and vector shapes (lines, rectangles, circles, curves,
filled areas, CAD line work) that are part of the page itself, not on markups. Point at an object
to see it outlined; click to select it. Lines are picked up within a few pixels; a filled shape
is picked up anywhere inside it.</li>
<li><b>Several at once:</b> Ctrl+click adds or removes an object, or drag a box from empty space
to select everything entirely inside it (Ctrl+drag adds to the selection). In CAD drawings one
"shape" is often many separate lines, so a box is the quickest way to grab it.</li>
<li>Drag the selection to move it. Drag a corner handle to resize it, keeping its proportions
(hold Shift to stretch freely), or a side handle to make it wider or taller. Resizing a shape also
scales its line thickness.</li>
<li>Delete (or Backspace) deletes the selection. Right-click for Rotate clockwise, Rotate
counterclockwise, the stacking order commands and Delete, and, for one picture, Copy picture
(Ctrl+V pastes it as an image markup) and Save picture as.... Escape deselects.</li>
<li><b>Stacking order:</b> when the page's own objects cover each other, select one and use
<b>Bring to front</b> (Ctrl+Shift+]), <b>Bring forward</b> (Ctrl+]), <b>Send backward</b>
(Ctrl+[) or <b>Send to back</b> (Ctrl+Shift+[), from the right-click menu or Arrange. Front and
back mean in front of or behind everything on the page, the page's text included; forward and
backward move it past the next object it overlaps. The object keeps its colors, line style and
transparency. If it was cut to a clipping outline where it was, it isn't any more where it
lands.</li>
<li>Only the selected objects change: moving, resizing and rotating keep their place in the
drawing order (text printed over a picture stays on top), their colors and line styles, and
pictures aren't recompressed, so quality doesn't drop. Ctrl+Z undoes each change.</li>
<li>Text can't be selected with this tool (use Edit text), and neither can objects inside a grouped
object (a form XObject) or clipping outlines. On very large drawings, the first click on a page
takes a moment while the page is read.</li>
</ul>

<h2 id="edittext">Editing the PDF's own text</h2>
<ul>
<li>Edit text tool (Ctrl+E): click a line of text. Type the change; drag the bar above the
box to move the text, drag the corner grip to make it wrap. Click elsewhere or press
Ctrl+Enter to finish, Escape to cancel.</li>
<li>Highlights, underlines, strikeouts, comments and sticky notes on that line move with it.</li>
<li>The original font is used when it's embedded or installed and has every character you
typed; otherwise the closest standard font, or, for characters those can't write (Greek such as
&Omega; &Delta;, symbols, Chinese and other scripts), a built-in Unicode font. Only the letters
used are stored, so files stay small. The status bar tells you which font was used. If no
font has a symbol you typed or that came from the PDF (a minus sign, a diameter sign, an
invisible narrow space...), a broader installed font such as Segoe UI is tried, then a look-alike
is used (- for the minus sign, &Oslash; for the diameter sign, a normal space for an invisible
one). Characters that can't be written at all, such as emoji, are named in a message, and
nothing is changed. A line on a
page that still has unapplied redaction marks can't be edited until you apply or remove them.</li>
</ul>

<h2 id="measure">Measuring</h2>
<ul>
<li>Set the drawing scale first: Measure &gt; Set scale (presets such as 1/4" = 1'-0", 1:100),
or <b>Calibrate Tape Measure</b>: drag along a known dimension and type its real length.</li>
<li><b>Length</b> (Shift+M), <b>Polylength</b>, <b>Area</b> with perimeter (Shift+A), and
<b>Count</b> (Shift+C, with named groups). Values update when you edit the markup or change
the scale.</li>
<li><b>Measurement summary</b> totals everything and exports to CSV.</li>
</ul>

<h2 id="pages">Pages</h2>
<ul>
<li><b>Rotate page left / Rotate page right:</b> Ctrl+Shift+Minus / Ctrl+Shift+Plus.</li>
<li><b>Page list size:</b> drag the Pages panel's edge to make it as narrow as you like; the
thumbnails shrink to fit (the lock button then just reads Locked / Unlocked). Tabs that don't fit
scroll sideways.</li>
<li><b>Page order lock:</b> the lock button above the thumbnails (locked by default) protects
the page order: while it's locked, nothing moves, adds or removes pages, whether by dragging,
the Pages menu, the ribbon or a shortcut (Move page up / down, Delete page, Insert pages, Insert
blank page, Cut, Paste and Duplicate pages). Using one of those asks whether to unlock first.
Copying pages, rotating and extracting work while locked.</li>
<li><b>Reorder:</b> unlock the page list, then drag thumbnails; or Move page up / Move page down
(Ctrl+Shift+Up / Down).</li>
<li><b>Combine files</b> (File &gt; Combine files..., or Pages tab &gt; Combine files): makes one
new PDF from several. Add the PDFs (Add files..., or drop them onto the list from Explorer); the
open document is already in the list. Drag them, or use Move up / Move down / Sort by name, to
set the order, top to bottom. With "Add a bookmark for each file" ticked, each file gets a
bookmark named after it and keeps its own bookmarks underneath. Click Combine..., choose a name,
and the combined PDF opens. Password-protected files ask for their password. The original files
aren't changed.</li>
<li>Pages menu: Insert pages from file, Insert blank page after current, Extract pages to new
file, Delete page.</li>
<li><b>Layers</b> tab: show or hide CAD / optional-content layers.</li>
<li><b>Bookmarks</b> tab: add, rename, reorder and indent bookmarks.</li>
</ul>

<h2 id="forms">Forms</h2>
<ul>
<li><b>Fill in:</b> with Select or Hand, click a field. Option buttons with the same group
name are exclusive: choosing one clears the others in its group.</li>
<li><b>Next form field</b> (Tab) and <b>Previous form field</b> (Shift+Tab), in the Forms menu:
go through the fields in reading order (page by page, top to bottom, left to right). The
current field gets an orange outline; a text field opens for typing (Tab moves on, Shift+Tab
goes back); for a checkbox, option button, dropdown, signature or initials field press
<b>Space</b> or <b>Enter</b> to fill it in. Escape clears the outline.</li>
<li><b>Highlight form fields</b> (View or Forms menu, on by default) shades every fillable field
blue with a blue outline; required fields get a red outline. The shading is on screen only.</li>
<li><b>Create:</b> Forms menu: text field, checkbox, option button, dropdown, signature field,
initials field. An <b>initials field</b> works like a signature field: whoever fills in the
form clicks it to put their saved initials there. Double-click a field to change its name and
options.</li>
</ul>

<h2 id="sign">Protect: signatures, passwords, redaction</h2>
<p>Everything here is in the <b>Protect</b> menu.</p>
<ul>
<li><b>Wet signature / initials:</b> Sign (G) or Initials (I), then click to place your signature
or initials. The first time, you're asked to set it up (draw it or load a picture of it, optional
PIN); to replace it later, use File &gt; Preferences &gt; You &gt; Set up my signature... / Set up my
initials.... To choose the size, <b>drag a box</b> instead of clicking: it's placed as wide as you
drag (the height follows its proportions). The size used for a click is set in File &gt;
Preferences &gt; You (2 in for a signature and 0.75 in for initials to start with). Afterwards the
Hand or Select tool, whichever you used last, is active again, so you don't place a second one by
accident. Like any picture on the page, a placed signature can be moved or deleted with Edit
objects (or Ctrl+Z right after placing it).</li>
<li><b>Date</b> (Ctrl+;, Protect tab and menu): click to write today's date there, for example
next to a signature or in a document's own date field. It's separate from signing, so a form
that already prints a date doesn't get two. The format (such as 10/08/2026 or October 08, 2026)
is set in File &gt; Preferences &gt; You.</li>
<li><b>Multi-place signature or initials:</b> put your initials (or signature) on all pages,
all but the first or last, or pages you list, in the same spot as the last one you placed
or in a corner.</li>
<li><b>Add signature placeholder:</b> drag boxes where signatures or initials should go
(choose which in Properties). <b>Apply all signature placeholders</b> then fills every one
with your saved signature or initials and the date.</li>
<li><b>Digitally sign with certificate</b>, with an optional lock against changes (certify).
Choose where the certificate comes from:
<ul>
<li><b>Certificate stored in Windows</b>: the list shows the signing certificates in your
Windows Personal store, the same ones Adobe Acrobat and PDF-XChange Editor use (open
certmgr.msc &gt; Personal &gt; Certificates to see them). Windows does the signing, so
certificates whose key can't be copied, smart cards and USB tokens work too; Windows asks for
the PIN when the key needs one. To add a .pfx/.p12 there, double-click it. KanzonasPDF
remembers the certificate you used last.</li>
<li><b>My personal certificate</b>: one KanzonasPDF makes for you the first time. It signs
documents only. It is not a certificate authority and cannot issue other certificates.</li>
<li><b>Certificate file</b>: a .pfx/.p12 file from a certificate authority or your company,
with its password.</li>
</ul> Signed files open read-only so
the signature stays valid. <b>Digital signature details</b> shows who signed and whether it's
still valid. <b>Clear all digital signatures</b> removes them (the empty fields stay).</li>
<li><b>Timestamp document:</b> gets a trusted timestamp from a free internet time server,
proving the file existed, unchanged, at that moment. Saved as a new copy.</li>
<li><b>Redaction:</b> Redact tool (Shift+R) or Search &amp; redact marks areas. Redaction marks
can be selected, moved and resized; <b>Apply selected redactions</b> applies only the selected
ones, Apply redactions applies them all. Applying removes, not just covers: the text, images
and line art under a mark, and any <b>form field or markup</b> a mark overlaps (they keep their
own copy of the text). A vector path that touches a mark is removed past the box, including
the part outside it. Applying scrubs metadata, attachments, hidden text, and scripts unless
you turn that off in the confirmation (the checkbox starts ticked). <b>Search &amp; redact</b> also finds the text where a box can't go: form
field values, markup notes, bookmark titles and document properties. When you apply, fields
containing it are deleted, and in notes, bookmarks and properties it's replaced by
[redacted]. If the text is only in those places, Search &amp; redact offers to remove it right
away. Check the result before sharing; Undo works until you close the file.</li>
<li><b>Sanitize document:</b> remove hidden data you choose: document information, scripts,
attached files, hidden text, links, comments, form data, thumbnails.</li>
<li><b>Security properties (passwords &amp; permissions):</b> AES-256 encryption.
  <ul>
  <li><i>Open password:</i> nobody can read the file without it. Real protection; if you
  forget it, the file can't be recovered.</li>
  <li><i>Permissions password:</i> choose what others may do (print, copy, comment, fill forms,
  change content, change pages). Acrobat, PDF-XChange, Bluebeam and this app honor it, but
  some free tools ignore it, so don't rely on it for secrets.</li>
  <li><i>Policies:</i> save your usual settings as a named policy (passwords are never saved).</li>
  </ul>
  Changes take effect when you save. Digital signatures and timestamps can't be added to a
  password-protected PDF yet: remove security, sign the final version, and don't add a
  password afterwards (that would invalidate the signature). <b>Remove security</b> takes protection off (you need the
  permissions password). <b>Unlock with password</b> lets you edit a restricted file.</li>
<li><b>Saving keeps protection:</b> a password-protected file stays protected when you save
your changes, with the same open password and restrictions (re-encrypted with AES-256). If you
opened it with the open password only, KanzonasPDF doesn't know the permissions password, so the
saved copy gets a new random one: its restrictions can then only be changed from the original
file. Use Security properties or Remove security to change protection on purpose.</li>
<li><b>Saving keeps signatures:</b> a digitally signed file you haven't changed is saved as an
exact copy (Save or Save As), so its signatures stay valid. Only after "Edit anyway" does saving
change it, and then the signature no longer validates.</li>
</ul>

<h2 id="document">Document tools</h2>
<ul>
<li><b>Recognize text (OCR):</b> makes scanned pages searchable and selectable. Choose the
<b>pages</b> (All, the current page, or a list such as 1-3, 7), whether to <b>skip pages that
already contain text</b> (on by default, so text isn't duplicated), and the <b>accuracy</b>:
<b>Fast</b> (150 dpi) for clean scans with normal-size text; <b>Normal</b> (300 dpi);
<b>High</b> (400 dpi, and it checks every orientation, for small print, poor scans and
sideways or upside-down pages; the slowest); or <b>Auto</b> (the default), which reads each
page fast and redoes it at High resolution only when the text came out small or unclear.
Higher accuracy takes longer and uses more memory, and it never renders a scan sharper than
it was scanned (that only adds blur), so on a 200 dpi scan Normal and High read at 200 dpi.
Your choice is remembered.</li>
<li><b>Redaction:</b> the Redact (mark text or area) tool (Shift+R) or Search &amp; redact
marks areas; Apply redactions permanently removes what's underneath. A vector path that
touches a mark is removed past the box. Applying scrubs metadata, attachments, hidden text,
and scripts unless you turn that off. Check the result before sharing.</li>
<li><b>Header &amp; footer, page numbers, Bates</b>, <b>Watermark</b>,
<b>Compress (save a smaller copy)</b>, <b>Compare documents</b> (changes clouded in red and
blue), <b>Flatten</b> (make markups part of the page).</li>
<li><b>Remove watermarks...</b> (Document menu): takes watermarks off the current page, all
pages or pages such as 1-3, 7. It finds watermarks added with Document &gt; Watermark and those
added by apps that mark them as watermarks (Adobe Acrobat, PDF-XChange and others), and
watermark annotations. Ctrl+Z undoes it. A "watermark" that is just ordinary text or a picture
in the page can't be told apart from the rest of the page; remove it with Erase content or
Edit objects.</li>
<li><b>Background...</b> (Document menu; Pages tab): puts a <b>solid color</b>, a <b>gradient</b>
(two colors, top to bottom, bottom to top, left to right or diagonal) or a <b>picture</b> (Fit,
Fill, Stretch to the page, or Center at its own size) behind everything on the page, at the
opacity you choose. Apply it to the current page, all pages, or pages such as 1-3, 7. It's saved
in the file, so everyone sees it, and it isn't picked up as text. Adding a background to a page
that has one replaces it. <b>Remove background...</b> takes it off the current page, all pages or
the pages you list; Ctrl+Z undoes either. A background can't show through a scanned page, because
the scan is a picture covering the whole page; use a Watermark for those.</li>
<li><b>Export</b> (File &gt; Export to): Microsoft Word (.docx), Microsoft Excel (.xlsx),
Microsoft PowerPoint (.pptx), AutoCAD drawing (.dxf), Images (PNG), Images (JPEG),
Plain text (.txt).</li>
</ul>

<h2 id="preferences">Preferences</h2>
<ul>
<li><b>File &gt; Preferences...</b> (Ctrl+K) gathers the options KanzonasPDF remembers in one
window, with the sections listed on the left. An option that also has a menu command does exactly
the same as that command, so you can change it in either place. <b>OK</b> uses your changes and
closes the window; <b>Apply</b> uses them right away and leaves the window open, so you can see
the effect and keep adjusting; <b>Cancel</b> closes it without the changes made since the last
Apply.</li>
<li><b>General:</b> theme (Match Windows, Light, Dark), Ribbon (instead of toolbars), Show group
names on ribbon, Show menu bar, Show text labels on toolbars, Check for updates automatically.
It also tells you where your settings are saved (the data folder in portable mode).</li>
<li><b>You:</b> the Author name for markups (recorded on new markups and shown on stamps), and
Set up my signature... / Set up my initials... with whether each is saved yet, and Change PIN...
to set, change or remove the PIN that protects them (leave the new PIN empty to remove it), and
the Signature width and Initials width used when you click to place them, and the Date format
the Date tool writes.</li>
<li><b>Markup styles:</b> pick a tool on the left to set its default colors, line width, font
size, fill, opacity and so on, the same settings the Properties panel shows when that tool is
active. Reset defaults puts a tool back to how KanzonasPDF came.</li>
<li><b>Start-up and opening:</b> reopen the documents that were open when you closed
KanzonasPDF (off by default), the tool to start with (Hand or Select), the zoom a document opens
at (Fit width by default; Fit page, the whole page in the window; Actual size; or the zoom it had
when you closed it), and whether to reopen it at the page you were on last time.</li>
<li><b>Saving:</b> how often to back up unsaved changes (every 5 minutes by default; Off turns it
off). A copy of each document with unsaved changes is kept in the backups folder and deleted when
you save or close it. If KanzonasPDF or Windows stops unexpectedly, the next start offers to open
the copies; use Save As to keep one. Offered copies stay in the backups folder (Open backup
folder) for 30 days. <b>Backup folder</b>: Change... picks another folder (if KanzonasPDF can't
write there it says so), Use default goes back to the standard one (in the data folder when
portable). Backups of open documents move to the new folder; recovered copies from earlier stay
in the old one. Password-protected documents aren't backed up, because the copy wouldn't
have the password.</li>
<li><b>Measuring:</b> the units offered for a page that has no scale yet, what feet and inches
round to (1/2" to 1/64"; 1/16" by default) and the decimal places for other units. Existing
measurement labels update when you next move or edit them.</li>
<li><b>Mouse and scrolling:</b> CAD-style mouse, Scroll one page per wheel step.</li>
<li><b>Pages and display:</b> lock the page order, Show comment boxes, Highlight form fields,
and <b>Grid and snapping</b>, all in one place: grid spacing and units, the darker line
interval, Show grid, Snap to grid and Snap to objects (the same settings as View &gt; Grid
settings...).</li>
<li><b>OCR:</b> the accuracy the Recognize text dialog starts with.</li>
<li>Changes apply when you click OK; Cancel leaves everything as it was.</li>
</ul>

<h2 id="shortcuts">Keyboard shortcuts</h2>
<table border="1" cellpadding="3" cellspacing="0">
<tr><th>Key</th><th>Action</th></tr>
<tr><td>V / H</td><td>Select / Hand</td></tr>
<tr><td>Ctrl+E</td><td>Edit text</td></tr>
<tr><td>Ctrl+K</td><td>Preferences</td></tr>
<tr><td>Ctrl+;</td><td>Date (today's date where you click)</td></tr>
<tr><td>Shift+O</td><td>Edit objects (the page's own pictures and shapes)</td></tr>
<tr><td>Ctrl+Shift+H / U / X</td><td>Highlight / Underline / Strike</td></tr>
<tr><td>C / N / T / K</td><td>Comment / Note / Text box / Callout</td></tr>
<tr><td>R / E / D / Y</td><td>Rectangle / Ellipse / Cloud / Polygon</td></tr>
<tr><td>L / A / Shift+L / P</td><td>Line / Arrow / Polyline / Pen</td></tr>
<tr><td>M / X</td><td>Stamp / Eraser</td></tr>
<tr><td>G / I</td><td>Signature / Initials</td></tr>
<tr><td>Shift+M / Shift+A / Shift+C</td><td>Length / Area / Count</td></tr>
<tr><td>Shift+R</td><td>Redact</td></tr>
<tr><td>Shift+E</td><td>Erase content</td></tr>
<tr><td>Shift+P</td><td>Capture area</td></tr>
<tr><td>Ctrl+wheel</td><td>Zoom (scroll up and down when CAD-style mouse is on)</td></tr>
<tr><td>Shift+wheel</td><td>Scroll left and right</td></tr>
<tr><td>Shift (while drawing)</td><td>45&deg; lines, squares and circles</td></tr>
<tr><td>Ctrl+click, Ctrl+drag</td><td>Select several markups</td></tr>
<tr><td>Escape, Escape twice</td><td>Clear selection, back to Select</td></tr>
<tr><td>Delete</td><td>Delete selected markups</td></tr>
<tr><td>Ctrl+C / Ctrl+X / Ctrl+V</td><td>Copy / cut / paste (text, markups, pictures, pages)</td></tr>
<tr><td>Ctrl+A</td><td>Select all text on the page (all pages in the page list)</td></tr>
<tr><td>Ctrl+D</td><td>Duplicate selected markups (or pages, in the page list)</td></tr>
<tr><td>Ctrl+L</td><td>Lock selected markups</td></tr>
<tr><td>Ctrl+Shift+] / Ctrl+] / Ctrl+[ / Ctrl+Shift+[</td><td>Front / forward / backward / back</td></tr>
<tr><td>Left / Right</td><td>Previous / next page</td></tr>
<tr><td>Tab / Shift+Tab</td><td>Next / previous form field (Space or Enter fills it)</td></tr>
<tr><td>Arrow keys (something selected)</td><td>Move it 1 pt; with Shift 10 pt; with Ctrl 0.1 pt</td></tr>
<tr><td>Ctrl+Shift+Plus / Minus</td><td>Rotate page</td></tr>
<tr><td>Ctrl+Shift+Up / Down</td><td>Move page</td></tr>
<tr><td>Ctrl+2 / Ctrl+0 / Ctrl+1</td><td>Fit width / fit page / actual size</td></tr>
<tr><td>Ctrl+F, F3, Shift+F3</td><td>Find, next, previous</td></tr>
<tr><td>Alt+Down / Alt+Up</td><td>Next / previous comment</td></tr>
<tr><td>F1</td><td>This manual</td></tr>
<tr><td>Ctrl+F1</td><td>Collapse / expand the ribbon</td></tr>
<tr><td>Ctrl+Shift+M</td><td>Show / hide the menu bar (ribbon layout)</td></tr>
<tr><td>F11</td><td>CAD-style mouse on / off</td></tr>
<tr><td>Hold wheel + drag</td><td>Pan (any tool)</td></tr>
<tr><td>Alt (while drawing or dragging)</td><td>Don't snap</td></tr>
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
