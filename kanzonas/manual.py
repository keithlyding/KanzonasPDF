"""Built-in user manual (Help > User manual, F1).

The manual is kept here as HTML so it is always packaged with the app (no data files).
Each <h2 id="..."> becomes an entry in the contents list. The Spanish translation is
manual_es.MANUAL (same chapters and ids); manual_html() gives the one for the interface's
language.
"""

import re

from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QVBoxLayout, QListWidget, QTextBrowser,
                               QLineEdit, QPushButton, QSplitter, QLabel)

from .i18n import language, tr

MANUAL = """
<h1>KanzonasPDF user manual</h1>
<p>A free PDF reader and editor. Use the contents list on the left, or type in the
<b>Find in manual</b> box above.</p>

<h2 id="audit-fixes">Document protection and safe editing</h2>
<p>Apply redactions removes any vector path touching a mark, even the part of that path
outside the box. Applying also scrubs metadata, attachments, hidden text, and scripts
unless you turn that off. Check the result before sharing. Search &amp; redact
replaces the text with [redacted] in notes and comments (they're written anew, so no copy of
the text stays in their appearance or private data) and removes stamps, pictures and
attached files containing it completely, including private stamp data and appearances.</p>
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
<p><b>Print</b> (File menu, toolbar, Ctrl+P) opens KanzonasPDF's print window with a preview
of each sheet as it will print: pick the printer and copies, which pages (All, Current page,
or a list such as 1-3, 5), the orientation (Auto turns each sheet to fit its page), the size
(Fit to paper, or Actual size, which only shrinks pages that are too big) and whether markups
and form fields print. <b>Page setup...</b> sets the paper size and margins. Use the arrows
under the preview to see each sheet. Pages print at the printer's resolution up to 600 dpi,
rendered a strip at a time so even large drawings print sharp without using much memory.
Markups and form fields follow their own print setting, as in Acrobat: one made to show on
screen only doesn't print, and one made to print but not show on screen does. While it prints, a
small window shows which page it's on; <b>Cancel</b> there stops the job.</p>
<p>Copying, extracting and exporting require copying permission, and so do Combine files and
Insert pages from file for each PDF they take pages from: a PDF that doesn't allow copying is
refused unless you type its permissions (owner) password when asked. Print requires printing
permission and uses at most 150 dpi when high-quality printing is forbidden. Form filling
and adding markups honor their separate permissions: signing or dating a form field needs only
<b>Filling in form fields and signing</b>, while placing a signature or the date anywhere else
on the page changes the page. A form with only empty signature fields isn't signed, so it opens
for filling in even when it's protected. Flattening selected pages preserves
page labels, outgoing links (and what ties a link to its underline and words) and drawing
calibration. Flatten leaves redaction marks that aren't applied yet as marks. Excel export writes PDF text as literal
cell text, including text starting with an equals sign. OCR disables ONNX Runtime
telemetry before creating recognition sessions.</p>
<h2 id="start">Getting started</h2>
<ul>
<li><b>Open a PDF:</b> File &gt; Open (Ctrl+O), drag a file onto the window, or pick one from
File &gt; Open recent. Each file opens in its own tab, at the page and zoom you left it. When
KanzonasPDF is already open, a PDF opened from Explorer, an e-mail or a browser opens as a new tab
in it, and the window comes to the front (restored if it was minimized). Opening a file that's
already open switches to its tab; if the file has changed on disk since it was opened, the tab
shows it as it is now (asking first if the tab has unsaved changes).</li>
<li><b>Start a new PDF:</b> File &gt; <b>New PDF...</b> (Ctrl+N, or Pages tab &gt; New PDF)
asks for the page size (Letter, Legal, Tabloid, ANSI C to E, ARCH A to E, A4 to A0) and
portrait or landscape, then opens a tab named Untitled 1 with one blank page. Add pages with
Insert blank page after current or Insert pages from file (PDFs and pictures), draw, type or
sign on it as on any PDF. It isn't saved anywhere until you save it: Save (Ctrl+S) asks where,
as Save As does, and closing it after changes asks whether to save. Tick <b>Don't ask
again</b> to always use the size you chose; change it, or go back to being asked, in
Preferences &gt; Pages and display &gt; New PDF page size. With no document open, Insert blank
page starts a new PDF the same way, and Insert pages from file makes a new, unsaved PDF from
the files you choose.</li>
<li><b>Save:</b> Ctrl+S. <b>Save as:</b> Ctrl+Shift+S. Saving as a file that's open in another
tab replaces that file and closes that tab (asking first if it has unsaved changes); the same goes
for Extract pages, Combine files and the copies saved by Compress, Timestamp and digital signing,
except that the other tab then shows the new file. Undo is Ctrl+Z, redo is Ctrl+Y.
Up to 30 steps are kept. Each step keeps only what the edit changed, so undo and redo are quick
and all 30 steps fit even on very large PDFs; the history still stays within a memory budget
(256 MB per document, 512 MB for all open documents together; the oldest steps go first).</li>
<li><b>Panels:</b> Pages/Bookmarks/Layers on the left (F4), Properties on the right (F6),
Markups list (F7), Tool chest (F8), Bookmarks (F9), Split view (F10). The panels you had open
when you closed KanzonasPDF (and their sizes, sides and which of Properties / Tool chest was in
front) come back the next time it starts; the Split view always starts closed.</li>
<li><b>A document in its own window</b> (for a second monitor): drag its tab up or down out
of the tab bar and let go, or right-click the tab &gt; <b>Move to new window</b>, or View &gt;
<b>Move tab to new window</b> (Ctrl+Shift+N). The document isn't reopened: unsaved changes
and undo history come along. Drop a tab on another KanzonasPDF window's tabs (or right-click
it &gt; <b>Move to window</b>) to move it there. Each window has its own panels, tools and
Find box, with the same settings. Closing the last tab of a pulled-out window closes that
window; closing the main window (the first one) closes all of them, and reopening the last
files at start-up brings back the documents from every window, in the main window. Closing a
pulled-out window with several documents asks only about that window's documents. View options
(grid, snapping, comment boxes, highlight form fields, show markups, check spelling, theme, mouse
mode) are the same in every window: change one and every window's menu follows.</li>
<li><b>Closing KanzonasPDF:</b> with one document open, you're asked to save it if it has
unsaved changes. With several documents open you get one question: it lists the ones with
unsaved changes and offers <b>Save all</b>, <b>Don't save</b> or <b>Cancel</b> (Cancel keeps
everything open); when none has unsaved changes it asks "Close them all and exit?" (turn that
off in Preferences &gt; Start-up &gt; <b>Ask before closing KanzonasPDF with several documents
open</b>). Closing a tab asks only about that document.</li>
<li><b>Ribbon:</b> commands are grouped on tabs: Home, Markup, Measure, Arrange, Review,
Protect, Forms, Pages and View. The <b>Markup</b> tab has only markups: comments, notes, text
boxes, callouts, stamps, shapes and attached-file icons. Markups stay editable in any PDF
viewer (Adobe Reader, browsers) until you flatten them. Everything else you add (pictures,
Add text, signatures, initials, dates) is written into the page itself, so in a viewer it
looks and acts flattened; Edit text and Edit objects (Home tab) still change it here, as
Acrobat and PDF-XChange can. Open, save, print, undo and redo sit left of the tabs, and the
Find box (with its match count and up / down arrows) sits right of them. The bottom bar (status bar, bottom right) has page navigation (first,
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
<li><b>Command palette</b> (Ctrl+Shift+P; Help menu, View tab): type a few letters of what you
want to do and pick the command from the list; Enter runs it. Every menu command and tool is
there with its menu and shortcut, so nothing has to be hunted for on the ribbon. The letters
only have to appear in order ("sv as" finds Save As, "rot l" finds Rotate page left), and the
commands you ran from the palette lately come first.</li>
<li><b>Night mode (white lines on black)</b> (F12; View menu, View tab, Preferences &gt; Pages
and display): draws the pages like a CAD screen. Lightness is inverted and colors are kept, so
black lines and text turn white on a black sheet while a red line stays red and a yellow
highlight stays yellow. Pictures and scans are inverted too, like a negative. Only the screen
changes: printing, export, Capture area and the saved file are the same as always. Your choice
is remembered.</li>
<li><b>Enhance thin lines</b> (View menu, Preferences &gt; Pages and display; on by default):
every line is drawn at least one screen pixel wide, like Acrobat's option of the same name. CAD
drawings use very thin lines (a tenth of a point or less); at their true width they cover only
part of a screen pixel when zoomed out and come out pale gray. With this on they stay dark and
legible at any zoom. Only the screen changes: printing, export, OCR, Compare and the saved
file use the true line widths. Your choice is remembered.</li>
<li><b>Theme:</b> View &gt; Theme (Match Windows, Light, Dark). View &gt; Show text labels on
toolbars adds names under the icons. Hover over any toolbar button or box for a tooltip
saying what it does and its keyboard shortcut.</li>
</ul>

<h2 id="free">Free of charge</h2>
<p>Official KanzonasPDF releases stay free of charge for personal and commercial use: no subscriptions, trial expiration, paid feature tiers, required account or required paid cloud service. Optional donations never unlock features. The source code is available under the GNU AGPL-3.0.</p>

<h2 id="install">Installing, updating and uninstalling</h2>
<ul>
<li>Run <b>KanzonasPDF-v&lt;version&gt;-setup.exe</b> (the installer has a blue icon; the program itself is red). No administrator rights are needed: it
installs for your Windows account (choose "all users" on the first page if you're an admin and
want that). It adds a Start-menu shortcut, optionally a desktop shortcut, and offers
KanzonasPDF as an app for opening PDFs.</li>
<li><b>Make it your default PDF app:</b> Windows doesn't let installers do this silently. Right-click
any PDF &gt; Open with &gt; Choose another app &gt; KanzonasPDF, and tick "Always use this app".</li>
<li>Opening another PDF while KanzonasPDF is running opens it as a new tab in the same window.</li>
<li><b>Update:</b> use <b>Update now</b> in the update notice or in Help &gt; Check for
updates. KanzonasPDF downloads the new setup only from GitHub and only runs it when the file's
sha256 matches the digest published with that release; it asks to save open documents, closes,
installs the new version over this one (for you, or for all users with Windows' administrator
prompt if that's how it was installed) and starts again. Or run the newer setup over the old one
yourself; there's no need to uninstall first. Either way it installs in the same place and keeps
your settings, signatures, stamps and tool chest. <b>Uninstall:</b> Windows Settings &gt; Apps, or the uninstaller in the install folder.</li>
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
<li><b>PortableApps.com version</b> (KanzonasPDF Portable, for the PortableApps.com Platform):
your settings and files are kept in the package's <b>Data</b> folder, and the PortableApps.com
Platform updates it, so KanzonasPDF doesn't check for updates or offer Update now unless you
turn Help &gt; Check for updates automatically back on. Both portable versions follow your USB
stick to a new drive letter: if Open recent lists E:\\Docs\\plan.pdf and the stick is now F:, it
opens F:\\Docs\\plan.pdf.</li>
<li><b>Help &gt; Check for updates:</b> asks GitHub whether a newer KanzonasPDF has been released.
A box tells you the answer. If there's a newer version, it lists <b>what's new since your
version</b>: the short notes of every version newer than yours, newest first (in Spanish when
KanzonasPDF is in Spanish); <b>Download</b> opens the release page in your browser and
<b>Update now</b> updates this copy in place (see above; not in the PortableApps.com version,
which its platform updates). The automatic check instead shows a notice at the bottom of the
window with <b>What's new</b> (the same notes), <b>Update now</b>, <b>Download</b>, <b>Skip
this version</b> and <b>Later</b>. Nothing is downloaded or installed until you click a button.
With Help &gt; <b>Check for updates automatically</b> ticked (the default) the app checks
quietly once a day: a few seconds after it starts, and again every day while it stays open.
When there's nothing newer, the status bar says so for a few seconds ("Checked for updates:
You have the latest version"). Untick it to never contact GitHub. If your network blocks
GitHub, the automatic check simply finds nothing.</li>
<li><b>Help &gt; Report a problem or suggest an idea...</b> opens KanzonasPDF's page on GitHub in
your browser, with forms for a bug report or an idea (a free GitHub account is needed to send
one). Describe what you did and what happened; please don't attach confidential PDFs. Security
problems (redaction, passwords, signatures) have their own private form there.</li>
<li>The <b>KanzonasPDF-windows.zip</b> download is the same program without the portable.txt file: it runs
from any folder but stores settings on the computer like the installed version.</li>
</ul>

<h2 id="navigate">Moving around</h2>
<ul>
<li><b>Next / previous page:</b> the &#9664; &#9654; buttons beside the page number (bottom right
with the ribbon, in the toolbar with classic toolbars), the Right / Left arrow keys or Page Down /
Page Up, or type a page number and press Enter. <b>Home</b> and <b>End</b> go to the first and
last page. The same are in <b>View &gt; Go to</b>: <b>Next page</b>, <b>Previous page</b>,
<b>First page</b>, <b>Last page</b> and <b>Go to page...</b> (Ctrl+G: the page box, ready for a
number), so the command palette and the CAD command line find them too ("next page", "last
page").</li>
<li><b>Zoom in / Zoom out:</b> Ctrl+Plus / Ctrl+Minus, Ctrl+mouse wheel, the zoom slider, or the zoom box
(type a percent, from 10% to 6400%; 25.5 and 25,5 both work, and so does 1,000 for 1000%; a
zoom that isn't a whole percent shows one decimal). With the mouse wheel the page follows at
once, a little blurred, and is drawn sharp as soon as the wheel stops. Heavy drawings and big
scans fill in the same way after any zoom or scroll, the middle of the window first, so the
window never waits for them. A very long document can't go
quite as high: all its pages together must stay within the largest size Windows can draw.
Fit width (Ctrl+2), fit page (Ctrl+0), actual size (Ctrl+1). Documents open at Fit width, at
the page you were on last time; change this in File &gt; Preferences &gt; Opening documents.
Fit width and Fit page keep fitting when the window or a side panel changes size, until you
choose a zoom yourself.</li>
<li><b>Page thumbnails</b> (F4) shows or hides the left panel.</li>
<li><b>Links in the PDF:</b> point at a link to see where it goes. With the <b>Hand</b> tool, click
it (the pointer becomes a hand). With the <b>Select</b> tool, <b>Ctrl+click</b> it: a plain click
selects or edits what the link is on, so working on linked text, pictures or markups never
opens the link by accident. Edit text, Edit objects and the Links tool never open links. A link to a page in the document goes there. A web or
email address asks first, then opens in your browser or email program (tick <b>Don't ask
again</b> to skip the question from then on). A link to another PDF opens it in a new tab; a
link to another kind of file asks before opening it, and only common documents, pictures,
media and drawings are opened (links that would start a program, a script or a file with
macros are refused). Links written by AutoCAD and other CAD programs when plotting a sheet set
work this way, including links to files whose names have spaces. A link to a file on another computer (a network share) asks first, because
opening it sends your Windows sign-in to that computer.</li>
<li><b>Make anything a link:</b> select it, right-click and choose <b>Add link...</b>, then type a
web or e-mail address (www.example.com is fine; https:// is added) or choose a page in this
document. It works on <b>words</b> selected with the Select tool (only those words become
clickable; a selection over several lines makes one link), <b>markups</b> (stamps, text boxes,
shapes, pictures, signatures) and the page's own <b>pictures, shapes and text</b> selected with Edit
objects. <b>Look</b>: <b>Underline</b> (a thin blue line drawn into the page; the default for
words), <b>Box around it</b>, or <b>Nothing</b> (the default for pictures, shapes and markups; the
pointer still finds it). The words, picture or markup themselves don't change.</li>
<li><b>Links stay with what they're on:</b> move, resize or rotate a linked markup, picture, shape
or paragraph, or move a linked line with Edit text, and the link (and its underline) goes
along; delete it and its link goes too. A link remembers what it was made on, so only that
goes with it: a cloud or a box drawn around linked words doesn't take the words' link when
it's moved or deleted. Where links overlap, Remove link and Edit link act on the smallest one
under the pointer (the words' link, not the link of a cloud around them). Editing linked words with Edit text keeps their link,
including the links AutoCAD writes on a sheet set.</li>
<li><b>New link text:</b> with the <b>Links</b> tool (Home tab &gt; Insert, Tools menu), click
empty paper, or drag a box over it: the window's <b>Write this text on the page</b> is ticked,
and the text shows the address as you type it; type your own words instead if you like ("Our
website"). The text is written into the page, in blue and underlined, at the Add text size (or
to fit the box), and the link covers exactly it. Drag a box over what's already on the page
(a drawing, a scan) to make that area clickable without writing anything.</li>
<li><b>Change or remove a link:</b> right-click it &gt; <b>Edit link...</b> (where it goes, its look,
and the words it wrote) or <b>Remove link</b> (the link and its underline go; the words or
picture it was on stay; words the link wrote itself go with it). Clicking a link with the Links
tool also opens it for changing, with <b>Delete link</b>. The Links tool shows the page's links as
blue dashed boxes. All the parts of one link (several lines) change and go together. Ctrl+Z
undoes any of it. For a whole drawing set, <b>Link sheet callouts</b> (Pages menu) makes the
links for you from the sheet numbers.</li>
<li><b>Pan:</b> Hand tool (H; KanzonasPDF starts with it in the Hand mouse mode), the scroll bars, or <b>hold the mouse wheel down and drag</b>
(works with any tool). <b>Shift+wheel</b> always scrolls left and right, in every mouse mode and
when one wheel step would otherwise turn the page. Shift+Left/Right scrolls
sideways too.</li>
<li><b>Mouse mode</b> (the first three buttons of the Home tab, <b>Select</b>, <b>Hand</b> and
<b>CAD</b>; the View menu; Preferences &gt; Mouse): three ways to work, each with its own
options (see Preferences below).
<ul>
<li><b>Mouse: Standard (arrow, the wheel scrolls)</b>: KanzonasPDF starts with the Select tool
(the arrow) and Escape goes back to it; the wheel scrolls and Ctrl+wheel zooms.</li>
<li><b>Mouse: Hand (drag the page)</b>: starts with the Hand tool, which drags the page; clicking
a markup with it selects the markup. Free page movement is on in this mode, so the Hand drags the
page anywhere, also when it fits in the window. This is how KanzonasPDF starts at first.</li>
<li><b>Mouse: CAD (wheel zooms, hold wheel to pan)</b> (F11 switches it on, and off again to the
mode you had): like AutoCAD, the scroll wheel zooms in and out around the cursor and holding the
wheel down moves the sheet, so you can navigate a drawing while any tool is active. Like
Bluebeam, hold <b>Ctrl</b> and turn the wheel to scroll up and down. The pages sit on an open
canvas, the pointer is a <b>plus</b> (except with the Hand), selecting works like CAD and the
<b>CAD</b> tab appears, in front, with Move, Copy, Rotate and the other CAD commands: see
<b>CAD mode</b> below.</li>
</ul>
Your choice is remembered. (Before version 1.5 this was the CAD-style mouse switch and a
default tool; your choices carry over.)</li>
<li><b>Free page movement (drag the page past its edges)</b> (View menu, the View tab of the
ribbon): an open canvas around the pages, so the Hand tool (or the held wheel) drags the page
anywhere, up, down and sideways, even when the whole page fits in the window, for example after
Fit page. The menu switches it for the mouse mode in use; each mode remembers its own setting
(on in Hand mode, off in Standard mode, on in CAD mode).</li>
<li><b>Scroll one page per wheel step</b> (View menu): when the whole page fits in the window,
top to bottom and side to side (for example after <b>Fit page</b>), each step of the scroll wheel
jumps to the next or previous page, centered, instead of scrolling a little. As soon as you zoom
in so that any edge of the page is outside the window, the wheel scrolls normally. Hold
<b>Shift</b> to scroll left and right instead of turning the page. On by default; turn it off for smooth scrolling. Each mouse mode remembers its own setting. (In CAD mode the
wheel zooms instead.)</li>
<li><b>Find text:</b> Ctrl+F, then Enter / F3 for the next match and Shift+Enter / Shift+F3
for the previous; the up and down arrows beside the Find box do the same. The count beside
the box shows which match you're on and how many there are ("3 of 120"; "No matches" when
there are none; a word split by a hyphen at a line's end counts as one match). The search starts at the page you're on and shows the first match as soon as
it finds it; on long documents it keeps searching the rest in the background (the count reads
"3 of 120+" and the status bar shows how many pages are done) while you keep working. The match
you're on is shaded orange with a bold orange frame that stays big enough to spot even when
you're zoomed out and the text is tiny. In <b>Fit page</b> view, each match brings its whole
page in front, centered. Changing the text
or editing the document starts a fresh search.</li>
<li><b>Replace text...</b> (Edit menu, Ctrl+H): type what to find and what to replace it with,
tick <b>Match case</b> or <b>Whole words only</b> if needed, choose <b>All pages</b> or this
page, and click <b>Replace all</b>. It changes the PDF's own text (not comments). Each line
that changes is rewritten like Edit text does it, in the line's own font when that has the
characters. A line is rewritten in place and doesn't rewrap: when the new text runs into other
text or past the edge of the page, Replace text says on which pages (Ctrl+Z undoes it; Edit text
can rewrap the paragraph). Pages with redaction marks that aren't applied yet are skipped (it says which).
Ctrl+Z undoes the whole replacement.</li>
<li><b>Split view</b> (F10) shows a second, independently scrolling view of the same file.
It's for looking only: make changes in the main view.</li>
</ul>

<h2 id="cad">CAD mode: selecting and the CAD tab</h2>
<p>In the <b>CAD</b> mouse mode (View &gt; Mouse: CAD, F11) KanzonasPDF selects and edits like a
CAD program. It starts with <b>Edit objects</b>, which selects everything at once: the drawing's
own lines, text and pictures and the markups drawn on it (clouds, lines, notes...), in one
selection. Move, Copy, Rotate, Scale, Mirror, Align, Array and Delete then work on all of it
together, and one Ctrl+Z undoes it (the drawing's text only moves: it isn't copied, turned,
scaled or mirrored). <b>Select</b> (the CAD tab, or V when letters aren't going to the command
line) selects only your markups, or the characters of the page's text, the same way.</p>
<ul>
<li><b>Click</b> something to add it to the selection. <b>Shift+click</b> takes it out.
<b>Escape</b> clears the whole selection. Clicking empty paper keeps the selection. A markup lies
on top of the drawing, so a click on it takes the markup. A locked markup isn't taken.</li>
<li>The <b>arrow keys</b> nudge the whole selection, the drawing's objects and the markups
together. Right-click a markup for its own menu, the drawing's objects for theirs. Selected
markups show no resize handles here: change them with the CAD tab's commands, or with Select.
What's selected is drawn <b>dashed</b> (blue dashes over white, so it shows on a blue line too)
with small blue <b>grips</b> on its ends and corners, as in AutoCAD.</li>
<li><b>Click, move, click</b>: click empty paper, move the pointer (the box follows it) and click
again. Left to right it's a solid <b>blue window</b>: it takes what lies entirely inside it.
Right to left it's a dashed <b>green crossing box</b>: it takes everything it touches, a line
running through it included. The first corner is marked as soon as you click, and the status
bar asks for the other corner. A quick click counts as a click even if the mouse moved a little
while you pressed, and clicking the first corner again keeps the box. Escape drops a box you
started. Hold Shift on the second click to take things out instead.</li>
<li><b>Hold the button and drag</b>: a <b>lasso</b> that follows the pointer. Drawn rightward at
first it's a blue window lasso (what's entirely inside it); leftward, a green crossing lasso
(what it touches). Shift+lasso takes things out.</li>
<li>With Select, a box or lasso that takes no markups selects text: the characters inside a
window, or the ones a crossing box touches (Ctrl+C copies them).</li>
<li>While you draw a box or a lasso, what it would take <b>glows</b> (blue for a window,
green for a crossing box), so you see what you'll get before the second click or before you
let go; once taken, it's drawn dashed with grips. On a very big drawing it fills in over a moment while you move.</li>
<li>Dragging never moves anything in CAD mode, so nothing moves by accident: the square handles
of one selected markup or object still resize it, and the CAD tab's <b>Move</b> moves.</li>
<li>Preferences &gt; Mouse turns each of these on or off (see Preferences).</li>
</ul>
<p>The <b>CAD</b> tab (and the CAD menu) shows only in CAD mode. As in AutoCAD, either select
first and then start a command, or start the command first: with nothing selected it asks you to
<b>select objects</b> (clicks, boxes, lassos as above), and <b>Enter</b> (or a right-click) goes
on with what you selected. Then answer its prompt on the command line:
click points on the page (they snap to line ends and corners like the drawing tools; hold Alt
not to snap), type a value and press Enter, or click a button there. Escape (or Cancel) stops a
command; right-click is Enter. Each change is one Ctrl+Z.</p>
<p>So CAD mode needs no other tab for everyday work, the CAD tab also has the tools used most
next to its commands (they stay on their own tabs too). Similar tools share one button, as on
AutoCAD's ribbon: click the button for the tool it shows, or the arrow beside it to pick another;
the button then shows the one used last (or the tool that's on). <b>Markup</b>: Rectangle (arrow:
Cloud, Polygon, Mask), Circle (arrow: Arc), Line (arrow: Polyline, Curve, Pen), Arrow, Text box (arrow: Callout),
Stamp (arrow: Image); their one-letter shortcuts type into the command line in CAD mode.
<b>Measure</b>: Length (arrow: Polylength, Area, Angle, Radius, Perimeter, Volume, Count,
Calibrate Tape Measure), Snap to objects, Snap to grid, Snap to page. <b>Clean up</b>: Erase
content, Bring to front (arrow: Bring forward, Send backward, Send to back), Align left (arrow:
the other alignments, Distribute horizontally and Distribute vertically).</p>
<p><b>The command line</b>, along the bottom of the window in CAD mode, works like AutoCAD's.
Just start typing over the drawing (you don't have to click in the line first) and press
<b>Enter</b> (Space just types a space, as in "fit page"):</p>
<ul>
<li>AutoCAD's short names: <b>M</b> Move, <b>CO</b> or <b>CP</b> Copy, <b>RO</b> Rotate,
<b>SC</b> Scale, <b>MI</b> Mirror, <b>E</b> Delete (also ERASE, DEL), <b>AL</b> Align,
<b>AR</b> Array, <b>TR</b> Trim; or the start of a command's name: MOV, COP, ROT, TRI...</li>
<li>Any other command by its name, as the command palette (Ctrl+Shift+P) finds it: "rect",
"cloud", "fit page", "save as"... A list of matching commands shows above the line as you
type; Up and Down choose in it. Only a sure match runs: the command's whole name, or at least
three letters that start the name (or one of its words) of that one command and no other.
Accents and capitals don't matter. Commands that close the window or take things out of the
document (Exit, Close tab, Delete pages, Remove watermarks...) run only when typed in full, so
a stray EX never quits. Anything else runs nothing: the line says <b>Unknown command</b> (or
that several commands fit) and keeps what you typed, to correct it or to pick a command in the
list with Up and Down and Enter. A setting switched by typing its name says whether it's now on
or off.</li>
<li>Enter on an empty line repeats the last command.</li>
<li>While a circle is being drawn (its center clicked), type its radius and press Enter.</li>
<li>While a command runs, the line says what to do next and takes what you type: an angle, a
scale factor, or a choice (the first letters of a button's name will do: K for Keep them, D
for Delete them).</li>
<li>Escape clears what you typed; with nothing typed, it cancels the command.</li>
<li>In CAD mode the one-letter tool shortcuts (V for Select, H for Hand...) type into the command
line instead (Preferences &gt; Mouse, CAD options: turn off <b>Letters typed over the drawing go to
the command line</b> to keep them as tool shortcuts; then click in the command line to type a
command); Shift+letter shortcuts (Shift+M Length, Shift+A Area...) still work while nothing
is typed, Ctrl and Alt shortcuts (Ctrl+S, Ctrl+Z...) work as always, and the tools are a name
away ("hand", "select"). Enter still finishes a polygon or area being drawn, and Space and Enter
still fill the form field Tab moved to.</li>
</ul>
<ul>
<li><b>Move</b>: click the base point, then where it goes.</li>
<li><b>Copy</b>: click the base point, then where each copy goes, as many as you like; Enter,
Escape or Done ends it.</li>
<li><b>Rotate</b>: click the base point, then type the angle in degrees (counterclockwise; -90
turns clockwise) and press Enter, or click a point: the selection turns so that "east" points
there.</li>
<li><b>Scale</b>: click the base point, then type the factor (2 = twice as big, 0.5 = half; from
0.001 to 1000) and press Enter, or click a point at a length you know, then the point at the
length it becomes.</li>
<li><b>Mirror</b>: click two points on the mirror line, then <b>Keep them</b> (a mirrored copy)
or <b>Delete them</b> (the originals are replaced).</li>
<li><b>Delete</b>: deletes the selection.</li>
<li><b>Align</b>: click a point on the selection and where it goes, then a second point and where
it goes; then <b>Scale</b> (so the second points meet too) or <b>Don't scale</b>.</li>
<li><b>Array</b>: choose the rows and columns (up to 50 each), then click the base point, where
the next column's copy goes and where the next row's copy goes (the direction counts too). An
array that would make more than 20,000 objects asks first (a group counts every object it
draws). A big array (more than 20 copies of
a large selection) is made as CAD programs make blocks: the selection goes into the file once,
as a drawing group, and each copy places that group, so it's quick and the file stays small.
In Edit objects each such copy is a group; Ungroup takes one apart. This is done only for plain
lines, shapes and pictures that are all under the same clipping and in the same layer, where it
looks exactly like copying each object; anything else (groups, objects in different layers) is
copied object by object, which takes longer. Copies of such a selection (Copy, Mirror's copy
and arrays of any size) are drawn together on top of the originals, as CAD programs draw new
objects; a selection spread over different layers or clipping keeps each copy right above its
own original.</li>
<li><b>Trim</b>: as in AutoCAD, first the <b>cutting edges</b>: the lines selected before TR,
or the ones you select when it asks, then Enter (Enter with nothing selected: every line cuts).
Then click the part of a line to cut away: it goes up to the nearest cutting edges crossing it
on either side (or to its end, when none crosses on that side). With no cutting edges chosen, a
line none crosses goes completely; with cutting edges chosen, a line that crosses none of them
stays (it says so). The click picks the line nearest to it and isn't
snapped; a click right where lines cross says so instead (click a little to one side). Click
again and again; Enter, Escape or Done ends it. It
trims the drawing's own lines and curves (a trimmed curve is redrawn as short straight pieces)
and line, polyline and pen markups. Rectangles, polygons and clouds are trimmed too, and their
own corners cut as well as the lines crossing them: clicking a side of a lone rectangle or cloud
takes that side away from corner to corner, and clicking again takes another. What is left is one
open markup that starts and ends at the gap: a rectangle or polygon becomes a polyline (same
color, width and opacity; its corners go on cutting), and a cloud stays a cloud, its remaining
sides looking just as they did (it moves, turns, mirrors, restyles and trims like any markup;
other PDF readers show it as drawn). A cloud ellipse is cut only where lines cross it. A click
right on a corner says so instead (click on the side, a little away from the corner). Filled
shapes (a Mask too), plain ellipses, arcs, bent lines and pictures aren't trimmed.</li>
</ul>
<p>On a big drawing, CAD mode reads the page's line work in the background while you aren't
doing anything, a little at a time so the window never stops answering, so the first box,
lasso or command starts at once; the pointer shows a busy cursor while a command works. A
window box takes a curve when the curve as drawn lies inside it (its control points may stick
out).</p>
<p>What the commands don't do: the drawing's own text only moves (Move); copying, turning,
scaling or mirroring leaves it where it is and says so (Edit text changes it). Highlights and
other text markups stay on their words, so they only move and copy. A mirrored picture or stamp
keeps reading the right way round, and text boxes turn in quarter turns.</p>

<h2 id="select">Selecting and editing markups</h2>
<ul>
<li><b>Select tool (V):</b> drag across text to select it, including across the gap between
pages (it stays highlighted; see Copy, cut and paste below). Click a markup to select it, then drag
it to move it, drag a square handle to resize it, or change its look in the Properties panel.
In the <b>CAD</b> mouse mode, Select works as in AutoCAD instead: blue window and green
crossing boxes, a lasso, clicks that add to the selection, Shift to take out, Escape to clear,
and dragging moves nothing (see CAD mode).</li>
<li>With a drawing tool active (rectangle, line, callout, ...), clicking an existing markup selects
it too, so you don't have to switch back to the arrow. The <b>Hand tool</b> works the same way:
click a markup (a highlight, a note, a shape...) to select it; drag anywhere else to move the
page. A markup made a link opens its link instead when clicked with the Hand tool, or
Ctrl+clicked with the Select tool (a plain click with Select selects it). A markup on a link
the PDF came with (a highlight on a table of contents entry) is selected; click the link
beside the markup to open it.</li>
<li><b>Outlines and fills:</b> a rectangle, ellipse, cloud, polygon or area measurement
without a fill is picked by its outline (within a few pixels at any zoom, or an area's
label), like in Bluebeam; a filled one anywhere inside. So with a drawing or measuring tool,
pressing inside a room outlined with an Area or a cloud draws there (a Length across the
room, a Count, another cloud) instead of moving the outline.</li>
<li><b>Several markups:</b> Ctrl+click each one, or drag a box from empty space with the Select
tool (Ctrl+drag always draws a selection box). Ctrl+click on a markup made a link opens the
link; drag a box around that one instead. Drag any selected markup to move them all;
Delete removes them all; Properties changes apply to all of them.</li>
<li><b>Delete:</b> Delete or Backspace, or right-click the markup &gt; <b>Delete</b>.
<b>Edit a comment's text:</b> double-click it, or right-click it &gt; <b>Edit text...</b>.
Measurements, stamps and signature placeholders show text made from what they are, so they
don't offer Edit text (double-click a fill-in stamp to change its values); add a note or a
text box to comment on them.
If you right-click highlighted text that's selected, the menu offers <b>Delete highlight</b>.
In the Markups list (F7), double-click a row to edit its text; right-click a row for
<b>Edit text...</b> (when its text can be edited) and <b>Delete</b>, or press Delete.</li>
<li><b>Move with the arrow keys:</b> with markups selected (or pictures and shapes selected with
Edit objects), each press of an arrow key moves them 1 pt; <b>Shift+arrow</b> moves 10 pt and
<b>Ctrl+arrow</b> 0.1 pt, for fine adjustments. A series of presses is one Ctrl+Z. Markups tied to
text (highlights, underlines, strikeouts) stay with their text. With nothing selected, Left and
Right turn the page as usual.</li>
<li><b>Escape</b> clears the selection. With nothing selected, Escape puts down whatever tool
is picked (a stamp, shape, measurement, Crop...) and goes back to your default tool: the Hand
in the Hand mouse mode, Select in the Standard mode, Edit objects in the CAD mode. It works even right after a
dialog or a toolbar click took the keyboard focus.</li>
</ul>

<h2 id="clipboard">Copy, cut and paste</h2>
<ul>
<li><b>Text:</b> with the Select tool, drag across text; the selection stays highlighted.
<b>Double-click</b> a word to select it, and click a <b>third time</b> to select its whole line.
The drag can cross the gap between pages, and the pages in between are included.
<b>Copy</b> (Ctrl+C) puts it on the clipboard, with a blank line between pages;
<b>Cut</b> (Ctrl+X) also removes those letters
from the page (Undo brings them back); the lines above and below keep theirs, even in tightly set
text. On a page with redaction marks that aren't applied yet, Cut leaves the text where it is
(cutting would apply the marks): apply or remove them first. <b>Select all text</b> (Ctrl+A) selects the whole page's
text. Escape or a click elsewhere clears the selection.</li>
<li><b>Right-click menu:</b> right-click the page for Cut, Copy, Paste, Delete (for selected
markups) and Select all text. With text selected, it also offers Highlight, Underline, Strike out,
Comment on text... and Mark for redaction for that text. Right-clicking a markup selects it
first.</li>
<li><b>Markups:</b> select one or more markups, then Copy or Cut. <b>Paste</b> (Ctrl+V) puts them
where the mouse is, on any page or in another open document. Pasted on a page that's turned
another way (a rotated page), they're turned to look as they did where you copied them; a text
box still reads upright.</li>
<li><b>Duplicate</b> (Ctrl+D): copies of the selected markups appear slightly offset, selected
so you can drag them into place. In the page list, Ctrl+D duplicates the selected pages.</li>
<li><b>Pictures and text from other programs:</b> Paste a copied picture (e.g. a screenshot)
as an image markup, or copied text as a text box, where the mouse is.</li>
<li><b>Pages:</b> unlock the page list (lock button above the thumbnails), select thumbnails
(Ctrl+click adds or removes one page, Shift+click selects a run of pages), then right-click any
of the selected pages (the whole selection stays selected) or use the Pages menu:
<b>Copy pages</b>, <b>Cut pages</b>, <b>Paste pages after selected</b>, <b>Duplicate pages</b>
and <b>Delete pages</b>. With the page list clicked, Ctrl+C, Ctrl+X, Ctrl+V and Ctrl+A work on
pages, and Delete (or Backspace) deletes the selected pages, after asking. Pages
can be pasted into another open document too. Links on copied pages come along: a link to
another copied page goes to its copy, and a link to a page not copied still works on a duplicate
or a paste into the same document (in another document it's left out).</li>
</ul>

<h2 id="markup">Text markup and comments</h2>
<ul>
<li><b>Highlight</b> (Ctrl+Shift+H), <b>Underline</b> (Ctrl+Shift+U), <b>Strike</b>
(Ctrl+Shift+X): drag across the text. Selection works letter by letter.</li>
<li><b>Comment</b> (C): select text, type your comment. The text is marked (highlight,
underline, strike or squiggly: choose in Properties) and the comment shows in a box beside it.
Hide the boxes with View &gt; Show comment boxes.</li>
<li><b>Sticky note</b> (N): click where it goes and type.</li>
<li><b>Text box</b> (T): drag a box (or click) and type. Ctrl+Enter finishes typing. A text box
is a comment (a markup): people can move, edit or delete it in any PDF viewer until it's
flattened. Its font can be Helvetica, Times or Courier (Properties > Font): those are the fonts
every PDF viewer has, so the comment looks the same everywhere. To write text that's part of
the page, use <b>Add text</b> (below).</li>
<li><b>Callout</b> (K): press on the point you're pointing at, drag to where the text goes.</li>
<li><b>Author name:</b> Edit &gt; Author name for markups. It's recorded on your markups and
printed on stamps.</li>
<li><b>Check spelling</b> (Edit menu, on at first): while you type a comment, a text box, a
form field with several lines, or with Edit text and Add text, misspelled words get a red
wavy underline (American English). Right-click one for corrections, or <b>Add to
dictionary</b> to stop flagging it (your words are remembered). If the click lands just
beside the word, the word where the text cursor is gets the corrections. Abbreviations in capitals
(HVAC) and names with capitals inside (KanzonasPDF) aren't flagged. Click Check spelling again
to turn it off.</li>
</ul>

<h2 id="review">Reviewing comments (Review menu)</h2>
<ul>
<li><b>Add:</b> the Comment tool (C) marks text and adds a comment beside it; the Note tool (N)
adds a sticky note anywhere.</li>
<li><b>Next comment</b> (Alt+Down) and <b>Previous comment</b> (Alt+Up) walk through every
comment and markup in reading order, page by page, selecting each one. The status bar shows
"Markup 3 of 12". It wraps around at the end.</li>
<li><b>Markups list</b> (F7): all markups in a table, page 1 first (click a column heading
to sort by it); filter, click to jump, export to CSV (in the order shown; if the file can't be
written, open in Excel say, a message tells you). Clicking a locked markup jumps to it without
selecting it, and the list's Delete leaves it: unlock it first.</li>
<li><b>Show markups:</b> untick to hide every comment and markup and see the page as if
unmarked. Nothing is deleted; tick it again to bring them back. <b>Show comment boxes</b>
hides just the yellow boxes beside commented text.</li>
<li><b>Delete comments:</b> everyone's, only yours, or only one person's, on all pages or the
current page. Undo brings them back.</li>
<li><b>Flatten comments:</b> makes comments and markups a permanent part of the page while form
fields stay fillable. (Document &gt; Flatten flattens form fields too.) Redaction marks that
aren't applied yet are never flattened: burned in, they would look like a redaction with the
text still under them. If there are any, it asks first: <b>Apply them first</b> (the usual
Apply redactions, for every mark in the document), <b>Keep them as marks</b> (they stay
markups, the rest is flattened) or Cancel. The markups really
become page drawing: no PDF program sees them as markups any more. Programs that edit page
content (Acrobat's Edit PDF, PDF-XChange's Edit Content, KanzonasPDF's Edit objects) can still
move that drawing, as they can the rest of the page, and so can you (Edit objects selects each
flattened markup as a group; Edit text changes its text); flattening isn't a lock (that's the same
in Acrobat and Bluebeam). It's for sending a file whose markups everyone sees and prints exactly
as you made them. To make any later change detectable, digitally sign the PDF with the lock
against changes (certify): PDF readers that check signatures (Acrobat, PDF-XChange, KanzonasPDF)
then flag any later change.</li>
</ul>

<h2 id="shapes">Shapes, lines and the pen</h2>
<ul>
<li>Rectangle (R), Ellipse (E), Circle (O), Cloud (D), Mask, Polygon (Y), Line (L), Arrow (A),
Polyline (Shift+L), Arc, Curve, Pen (P). The shapes share one toolbar button: click its arrow to pick another.</li>
<li><b>Arc</b> (as AutoCAD's three-point ARC; on the CAD tab under Circle's arrow): click the start, a point the arc
passes through, then the end; the arc follows the pointer before the last click. Drag its three points to reshape it.</li>
<li><b>Bend a line or arrow:</b> select it and drag the diamond in its middle: it becomes a smooth curve through that
point; the ends stay where they are and an arrowhead follows the curve. Drag the diamond back onto the straight line to
straighten it. The <b>Curve</b> tool draws one directly: click the start, the end, then where it bends to.</li>
<li><b>Circle</b> (O): drag from the center to a point on the circle. In CAD mode, click the
center, then a point on the circle, or type the radius on the command line and press Enter (in
the page's measuring unit, as Measure &gt; Set scale shows it, 12'-6" also works; inches on paper
when no scale is set). It makes an ellipse markup, so Properties, the cloud border, moving and
resizing work as for an ellipse.</li>
<li><b>Mask</b>: drag a box over what to hide; it's covered by a white box with no outline (like
AutoCAD's Wipeout). Properties can change its fill color or give it an outline. It hides what's
under it on screen and in print, but that content stays in the file: use Redact to remove it
for good.</li>
<li><b>In CAD mode</b> the tools that draw from one point to another (Line, Arrow, Rectangle,
Ellipse, Circle, Cloud, Mask, Text box, Callout, Length, Radius, Calibrate Tape Measure, the
Eraser's box, Erase content, Capture area, Crop pages, Links, signature placeholders) work as in
AutoCAD: click where it starts, move (the shape follows the pointer with no button held), and
click where it ends. It snaps, and Shift works, as when dragging; pressing, dragging and letting
go still works too. A click that shakes a little is still a click. Escape or a right-click
cancels the shape being drawn; zooming or scrolling between the two clicks doesn't move its first
point. A click on a markup with the Eraser still deletes it at once, a click on a link with the
Links tool still opens it, and two clicks on the same spot with Text box make one of the default
size. Note, Stamp, Count and Image still place with one click.</li>
<li><b>Polygon / polyline:</b> click each point; double-click or Enter to finish, Backspace to take back the last point,
Escape to cancel.</li>
<li>With a drawing tool, clicking an existing markup selects it, and dragging moves it or its
points, without changing tools. <b>Shift+click on a markup</b> starts a new one right there
instead (to start a line at the end of another, say): nothing is selected or moved, and the
point snaps to the markup's end or corner when snapping is on. The pointer shows the drawing
cross while Shift is held.</li>
<li><b>Hold Shift</b> while drawing:
  <ul>
  <li>lines, arrows, measurements and polyline segments snap to 45&deg; steps (horizontal,
  vertical or diagonal);</li>
  <li>rectangles, ellipses and clouds become perfect squares and circles.</li>
  </ul></li>
<li><b>Hold Shift while resizing</b> from a corner: squares and circles stay perfect, other
markups keep their proportions. Shift while dragging a line's end keeps it at 45&deg; steps.</li>
<li><b>Eraser</b> (X): click a markup to delete it, or drag a box to delete everything inside.</li>
<li><b>Erase content</b> (Shift+E; Home tab, Tools menu): like Bluebeam's,
drag a box to permanently delete the page's own content inside it: text, images and lines.
Lines and curves that cross the edge of the box are cut there, so a wall running through the box
keeps its outside parts. A filled shape that crosses the edge (a solid color, a hatch pattern or a
gradient) keeps its outside part and loses what was inside the box; one entirely inside is
removed. Markups aren't touched (use the Eraser for those, which deletes a markup whole). Ctrl+Z
undoes it. Unlike redaction it leaves no black box; for confidential information use Redact, which
also cleans hidden copies (Erase content keeps the outline of a cut fill in the file, hidden).</li>
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
(see Editing the PDF's own pictures, shapes and text).</li>
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
one to change what it says; it resizes to fit. Its comment text (in the Markups list, its CSV
and other PDF programs) reads like "PO # PO-4471, Date ordered 10/26/2026".</li>
</ul>

<h2 id="images">Pictures and attached files (videos and more)</h2>
<ul>
<li><b>Image</b> tool: drag a box and pick a picture (PNG, JPEG, BMP, GIF, TIFF). It's fitted
inside the box keeping its proportions; just click instead to place it at its natural size.
The picture is embedded in the PDF at its original quality and file size and becomes part of
the page itself, like Acrobat's Add Image: PDF viewers can't move or delete it. Move, resize,
rotate or delete it with <b>Edit objects</b> (Shift+O), as in Acrobat and PDF-XChange. For a
picture that stays a movable markup, use <b>Add image stamp...</b> with the Stamp tool. Placed
signatures, initials and dates are part of the page the same way.</li>
<li><b>Attach file</b> tool: click where the paperclip icon should go and pick any file, such
as a video, spreadsheet or photo. The file is embedded inside the PDF, so it travels with it.
<b>Double-click the icon</b> to open the file in the program Windows uses for it (videos play
in your normal video player). Adobe Acrobat, Bluebeam and PDF-XChange can open these too.</li>
<li>Videos don't play inside the page: that only works in a few PDF readers, so attaching
is the reliable way to send a video with a PDF. Large files make the PDF just as much larger
(you're warned above 50 MB).</li>
<li><b>Attachments</b> (Document menu): every file attached to this PDF, including ones added
by other programs. Open, Save as, Go to its page, or Delete.</li>
<li>For your safety, Open asks first and only opens common documents, pictures, sound,
video and drawings (PDF, text, Word/Excel/PowerPoint without macros, images, MP3/MP4,
DWG/DXF...). Anything else, including programs, scripts, web pages and Office files with
macros, is not opened: use Save as and open it yourself if you trust it. Opened copies are
marked as downloaded from the internet, so Windows and Office treat them with the same
care.</li>
</ul>

<h2 id="editobjects">Editing the PDF's own pictures, shapes and text</h2>
<ul>
<li>Edit objects tool (Shift+O; Home tab, Tools menu), like Bluebeam's Edit content: works on
the pictures (logos, photos, scans) and vector shapes (lines, rectangles, circles, curves,
filled areas, CAD line work) that are part of the page itself, not on markups (in the CAD
mouse mode it takes the markups drawn on the drawing too: see CAD mode). Point at an object
to see it outlined; click to select it. Lines are picked up within a few pixels; a filled shape
is picked up anywhere inside it.</li>
<li><b>Text:</b> the page's own text (what Add text wrote, and the text of the PDF) is selected a
paragraph at a time: click a word to select its paragraph, and everything Add text wrote in one
go comes together. A selection box takes text only when there are no pictures or shapes in it
(so a box around a drawing detail selects its line work, not its labels); Ctrl+click adds text
to a selection. In the <b>CAD</b> mouse mode, selecting works as in AutoCAD instead: a blue
window (left to right) takes the lines, text, pictures and markups entirely inside it, a green crossing
box (right to left) everything it touches, text and line work together; clicks, boxes and
lassos add to the selection, Shift takes out of it and Escape clears it, and the CAD tab's
commands change it (see CAD mode). Press <b>Delete</b> (or Backspace) or right-click &gt; <b>Delete</b> to remove
it; drag it to move it (highlights and other markups on it move along). Text isn't resized,
rotated or re-stacked here: change its words, font and size with Edit text. Pictures and lines
under it stay. If other text overlaps it so closely that some of its letters would go too,
KanzonasPDF asks first. Invisible text (a scanner's recognized-text layer) isn't selected.</li>
<li><b>Groups:</b> a drawing group the page places as one piece (flattened markups and stamps
become these, and some programs export a whole drawing as one) is selected, moved, resized,
rotated, deleted and re-stacked as one object, as in Acrobat and PDF-XChange. A group that
fills the whole page isn't picked by a click (that would grab the sheet whenever you click
blank paper): drag a selection box around the page to select it.
Right-click a group &gt; <b>Ungroup</b> to take it apart: it looks the same, but its shapes and
pictures become separate objects you can select one by one, and its text can be changed with
Edit text. A group holding just one other group (as many programs write them) is taken apart
in one go; a group with groups inside still has those after one Ungroup.</li>
<li><b>Several at once:</b> Ctrl+click adds or removes an object, or drag a box from empty space
to select everything entirely inside it (Ctrl+drag adds to the selection). In CAD drawings one
"shape" is often many separate lines, so a box is the quickest way to grab it.</li>
<li>Drag the selection to move it. The shapes follow the pointer (they are not an empty box),
and the page itself changes only when you let go, so a large group stays quick to drag.
Drag a corner handle to resize it, keeping its proportions
(hold Shift to stretch freely), or a side handle to make it wider or taller. Resizing a shape also
scales its line thickness.</li>
<li>Delete (or Backspace) deletes the selection. Right-click for Ungroup (groups), Rotate clockwise, Rotate
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
object (a form XObject; use Ungroup first) or clipping outlines. On very large drawings, the first click on a page
takes a moment while the page is read.</li>
</ul>

<h2 id="edittext">Editing the PDF's own text</h2>
<ul>
<li><b>Add text</b> tool (Shift+T; Home tab next to Edit text, Tools menu): click where the text
goes and type (Enter finishes, Shift+Enter starts a new line). The text is written into the page
itself, like Acrobat's Add Text: PDF viewers can't change it, and Edit text changes it later.
Pick the font (any installed font, plus Bold and Italic), size and color in Properties. The
<b>Font size</b> can also be changed while you type: the text shows at the new size right away.
Only the letters used are stored in the file.</li>
<li><b>Change a line's font or size:</b> with the Edit text tool, click the line: Properties
shows its own <b>Font size</b>. Change the size, or pick a font (and Bold / Italic), and press
Enter, with or without changing the text. The choice applies to that line only: the next line you
click keeps its own font and size again (Keep the line's font / Keep the line's size). A font or
size picked before clicking a line applies to that line.</li>
<li><b>Delete text:</b> with the Edit text tool, right-click the text &gt; <b>Delete text</b>, or
select it with the Edit objects tool and press Delete (see below). The whole paragraph goes, all
the lines Add text wrote in one go; pictures and lines under it stay. Ctrl+Z brings it back.</li>
<li><b>Edit a paragraph:</b> with the Edit text tool (Ctrl+E), the dashed outline under the
pointer shows what a click edits: a whole paragraph, or one line (hold Alt for one line).
Click anywhere in a paragraph: the whole paragraph opens in a box of its width with the cursor on the word you clicked, and as you
type the words rewrap, as in Word. Press Enter and the paragraph is rewritten in its font, size,
color and line spacing, and keeps its alignment (left, right, centered or justified) and a
first line set in (an indent) or set out (a numbered paragraph's hanging indent). A word split by a hyphen at a line's end is joined again when the dictionary
knows the whole word (spe-/cification); a hyphenated word (self-/consolidating) keeps its
hyphen. The number or bullet of a list item stays where it is and its text is rewritten.
Shift+Enter starts a new paragraph. Drag a side handle to make it wider or narrower, or the
outline to move it (links on it move along; highlights and underlines drawn into the page stay
where they were, since the words have moved within it). A paragraph that gets longer grows
downward; it doesn't push what's below it down, so if it now runs into other text or past the
bottom of the page, the status bar says so (Ctrl+Z undoes it). The paragraph is written in one
style: a bold or colored word inside it comes out like the rest.</li>
<li><b>What counts as a paragraph:</b> lines of one size, one under the other at an even line
spacing, lined up on one side (or centered), that wrap like running text. It ends at its
short last line, so numbered steps and paragraphs with no space between them are each their
own; a line that starts with a number or bullet ("2.", "(b)", "1.Turn", a symbol bullet)
starts a new one. Anything else is
edited a line at a time: single lines; drawing labels, title blocks and dimension text; table
and schedule cells; a column next to another column; a heading (its size differs from the text
under it); list items, each on its own (also a list of one-line items whose bullets are
drawn, where every line is a sentence of its own); scanned and sideways text, and rotated
pages.</li>
<li><b>Edit one line:</b> <b>Alt+click</b> a line to edit just that line, even inside a
paragraph. <b>Press on a line and drag</b> to move it (its text and font stay as they are).
Editing a line: the cursor goes where you
clicked, and the line gets a dashed outline with handles, like a selected object. Type the
change; drag the outline to move the text, drag a handle to change the width the text wraps
to (the letters keep their size). Press Enter (or click elsewhere)
to finish, Shift+Enter to start a new line, Escape to cancel. Saving, closing the document,
Undo or a page change also finish an edit in progress, so typed text is never lost.
Sideways text (turned on the page, or on a rotated page) opens in an upright box over the
middle of the line so it's easy to type, with the cursor where you clicked along the line; the
text stays turned on the page when you finish.</li>
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
<li><b>Scanned pages</b> (a picture of the paper with recognized text over it, from your
scanner's OCR or Recognize text): Edit text, Find and replace and moving a line change the
picture too. The old words are covered with the paper's color, and the new text is written
to match the scan: KanzonasPDF draws the old words in each standard font and in common
installed ones (Arial, Calibri, Times New Roman, Courier New and others), regular, bold and
italic, compares them with the scanned letters, and uses the closest one, at the size and on
the baseline that fit, in the scan's ink color (gray, blue...). The editor opens in that font
and size, and the status bar says what was matched ("Matched the scan: Helvetica Bold,
11 pt"). A font or size picked in Properties still wins. Form lines under the text and
the text of the lines above and below stay as they are, and a checkbox the scan's text
starts with stays in the picture as long as the new text still starts with it. The
scanned typeface can't be named from a picture, so the result is the closest available font;
if the recognized text doesn't match the letters (the OCR misread them), Helvetica is used at
the letters' size, and the status bar says so. The new line is real text: search, copy and Edit
text work on it, and editing it again keeps its font.</li>
</ul>

<h2 id="measure">Measuring</h2>
<ul>
<li>Set the drawing scale first: Measure &gt; <b>Set scale</b> (presets such as 1/4" = 1'-0",
1:100), or <b>Calibrate Tape Measure</b> (Calibrate on the ribbon): drag along a known dimension and type its real
length. KanzonasPDF reads the scale notes written on the sheet (SCALE: 1/4" = 1'-0", 1" = 20',
1:50, NTS, in the title block or under detail titles): Set scale offers them as <b>Scale
written on the sheet</b>, picked for you when the title block has one, and the status bar
mentions what the sheet says while no scale is set. A page's scale goes with it: copies made
with Duplicate pages, Copy pages and Paste, Extract pages, Insert pages from file and Combine
files keep it.</li>
<li><b>Read scales from title blocks</b> (Measure menu, Measure tab): for a whole set at once,
every page gets the scale its own title block says; pages marked not to scale or without a
note are left as they are and listed. Trust but check: a sheet printed at reduced size (a
24x36 on 11x17 paper) still says its original scale, and nothing on the page tells. Measure
one known dimension after reading the scales, and use Calibrate Tape Measure if it is off.</li>
<li><b>Length</b> (Shift+M), <b>Polylength</b>, <b>Area</b> with perimeter (Shift+A), and
<b>Count</b> (Shift+C, with named groups). Values update when you edit the markup or change
the scale. A Count marker copied with Duplicate (Ctrl+D) or copy and paste takes the next
number of its group.</li>
<li>More measurements (Measure tab, "More" group, and the Measure menu):
<b>Angle</b>: click one end, the corner, then the other end; it shows the angle in degrees.
<b>Radius</b>: drag from the center of a circle to its edge; it draws the circle and shows the
radius (R) and diameter (&Oslash;).
<b>Perimeter</b>: click the corners, double-click or press Enter; it shows the distance around.
<b>Volume</b>: click the corners of the area, double-click or press Enter; it shows area
&times; depth. Set the <b>Depth</b> in the Properties panel, in the page's scale unit (feet
when the scale is in feet and inches); changing it updates the selected measurement.</li>
<li><b>Measurement summary</b> totals everything and exports to CSV.</li>
</ul>

<h2 id="pages">Pages</h2>
<ul>
<li><b>Rotate page left / Rotate page right:</b> Ctrl+Shift+Minus / Ctrl+Shift+Plus.</li>
<li><b>Crop pages</b> (Pages menu, Pages tab, Tools menu): drag a box around what to keep, then
choose <b>This page</b> or <b>All pages</b> (on other pages the same box is measured from their
top left corner). Only the visible area changes; nothing is deleted, so <b>Remove crop...</b>
(Pages menu, Pages tab) shows the whole page again, on this page or all pages. Ctrl+Z undoes
either.</li>
<li><b>Page list size:</b> drag the Pages panel's edge to make it as narrow as you like; the
thumbnails shrink to fit (the lock button then just reads Locked / Unlocked). Tabs that don't fit
scroll sideways.</li>
<li><b>Page order lock:</b> the lock button above the thumbnails (locked by default) protects
the page order: while it's locked, nothing moves, adds or removes pages, whether by dragging,
the Pages menu, the ribbon or a shortcut (Move page up / down, Delete pages, Insert pages, Insert
blank page, Cut, Paste and Duplicate pages). Using one of those asks whether to unlock first.
Copying pages, rotating and extracting work while locked.</li>
<li><b>Reorder:</b> unlock the page list, then drag thumbnails (several selected pages move
together, and Ctrl+Z undoes the whole drag); or Move page up / Move page down
(Ctrl+Shift+Up / Down).</li>
<li><b>Combine files</b> (File &gt; Combine files..., or Pages tab &gt; Combine files): makes one
new PDF from several. Add the PDFs (Add files..., or drop them onto the list from Explorer); the
open document is already in the list. Drag them, or use Move up / Move down / Sort by name, to
set the order, top to bottom. With "Add a bookmark for each file" ticked, each file gets a
bookmark named after it and keeps its own bookmarks underneath. Click Combine..., choose a name,
and the combined PDF opens. Password-protected files ask for their password. The original files
aren't changed, and the new PDF can't replace one of them.</li>
<li>Combine files also takes pictures (JPG, PNG, TIFF, BMP, GIF, WebP): each becomes a page.
<b>Create PDF from images...</b> (File menu, Pages tab &gt; Create group) starts with pictures: choose them, put
them in order and click Create.... With "Put each picture on a Letter page" ticked (the
default), each picture is fitted on a Letter page turned to suit it (landscape for wide
pictures); untick it to make each page the picture's own size. Phone photos come out upright,
JPEG photos aren't recompressed (no quality loss), and each page of a multi-page TIFF scan
becomes a page.</li>
<li><b>Insert pages from file</b> (Pages menu, Pages tab) inserts PDFs and pictures (JPG, PNG,
TIFF, BMP, GIF, WebP; pick several at once), in the order chosen, after the current page, at the
end or at the beginning, as one undo step. Each picture becomes a page the size of the page
before it, turned to suit the picture. With nothing open, it makes a new, unsaved PDF from
them.</li>
<li>Pages menu: Insert blank page after current (the same size as the current page), Extract
pages to new file (to a new file, not the document itself), Delete pages (the pages selected in
the page list, or the current page; it asks first, and Ctrl+Z brings them back). A bookmark to a
deleted page then goes to the page after it (or the last page).</li>
<li><b>Layers</b> tab: show or hide CAD / optional-content layers.</li>
<li><b>Bookmarks</b> tab: add, rename, reorder and indent bookmarks.</li>
<li><b>Link sheet callouts</b> (Pages menu, Pages tab): for a drawing set plotted without
hyperlinks. KanzonasPDF reads each page's sheet number and title from its title block (the
value after a SHEET, SHEET NO or DWG NO caption, or the largest sheet-like number in the
title block area) and shows them for correction. Then every callout bubble, note or index line
that names one of those sheets (3/A-501, SEE A-201, A101 and A-101 count as the same) becomes a
link to that page; a number that isn't a page here but is in the name of a PDF in the same
folder (A-501 Details.pdf) links to that file. Words that already have a link are left alone,
so AutoCAD's own hyperlinks stay and running it twice adds nothing. Options: a thin blue box
around the links (off by default, to keep drawings clean), and bookmarks named by sheet number
and title. Ctrl+Z undoes it all.</li>
</ul>

<h2 id="forms">Forms</h2>
<ul>
<li><b>Fill in:</b> with Select or Hand, click a field. Option buttons with the same group
name are exclusive: choosing one clears the others in its group. A field's maximum length is
kept to; a dropdown that allows it also takes a typed value (Type a value...). KanzonasPDF
doesn't run a form's JavaScript: totals a form works out itself and number or date formats
written as scripts don't update (check them, or fill such a form in Acrobat Reader).</li>
<li><b>Next form field</b> (Tab) and <b>Previous form field</b> (Shift+Tab), in the Forms menu:
go through the fields in reading order (page by page, top to bottom, left to right as the
page is shown, also on a rotated page). The
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
mouse mode's own tool (Hand, Select, or Edit objects in CAD mode) is active again, so you don't
place a second one by accident. Like any picture on the page, a placed signature can be moved or deleted with Edit
objects (or Ctrl+Z right after placing it).</li>
<li><b>Date</b> (Ctrl+;, Protect tab and menu): click to write today's date there, for example
next to a signature or in a document's own date field. Dating a form field (and signing a
signature or initials field) works on a protected form that allows filling in form fields and
signing. It's separate from signing, so a form
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
the signature stays valid (a file whose signature fields are all empty isn't signed and opens
normally). <b>Digital signature details</b> shows who signed and whether it's
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
fields (values, list options, tooltips and names), links (web and email addresses), markup
notes, bookmark titles and document properties. When you apply, fields, links, stamps and
attached files containing it are deleted, and in notes and comments (they stay), bookmarks
and properties it's replaced by [redacted]. If the text is only in those places, Search &amp; redact offers to remove it right
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
  <li><i>Filled-in forms:</i> when <b>Filling in form fields and signing</b> isn't allowed, the
  form's fields are also made read-only right away (Ctrl+Z undoes it), which every PDF reader
  honors, web browsers included, so the answers can't be changed. On a form that's filled in,
  or when you protect a document you just signed, this box starts unticked; tick it to hand
  out a form for others to fill in. Allowing form filling again, or Remove security, unlocks
  the fields locked this way (fields that were read-only before stay so). KanzonasPDF doesn't
  fill in read-only fields either.</li>
  <li><i>Policies:</i> save your usual settings as a named policy (passwords are never saved).</li>
  </ul>
  Changes take effect when you save. Digital signatures and timestamps can't be added to a
  password-protected PDF yet: remove security, sign the final version, and don't add a
  password afterwards (that would invalidate the signature). <b>Remove security</b> takes protection off (you need the
  permissions password). <b>Unlock with password</b> lets you edit a restricted file and
  accepts the permissions password of a file that already lets you edit, so its protection can
  be changed; Security properties and Remove security ask for that password first when the
  file has one.</li>
<li><b>Saving keeps protection:</b> a password-protected file stays protected when you save
your changes, exactly as it was: the same encryption, open password, permissions password and
restrictions, even if you don't know the permissions password. (Only in the rare case that the
protection can't be carried over does KanzonasPDF ask for the original passwords.) Use Security
properties (new protection uses AES-256) or Remove security to change protection on
purpose.</li>
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
Your choice is remembered. At every accuracy, a page scanned upside down is noticed and read
turned upright, and lines that are upside down or standing up on the page get their text
where their letters are, so Find and Search &amp; redact cover the right words. Edit text then
changes the scan's words in a matching font (see Editing the PDF's own text).</li>
<li><b>Redaction:</b> the Redact (mark text or area) tool (Shift+R) or Search &amp; redact
marks areas; Apply redactions permanently removes what's underneath. A vector path that
touches a mark is removed past the box. Applying scrubs metadata, attachments, hidden text,
and scripts unless you turn that off. Check the result before sharing.</li>
<li><b>Header &amp; footer, page numbers, Bates</b>, <b>Watermark</b>,
<b>Compress (save a smaller copy)</b>, <b>Compare documents</b>, <b>Flatten</b> (make markups part of the page).</li>
<li><b>Compare documents...</b> (Document menu, Pages tab): pick the earlier revision, then
how to compare. <b>Text, word by word</b> is for anything that reflows (letters,
specifications, permits, reports): the words of both documents are compared in reading
order, so text that only moved down a line or a page is not a change. The result is a copy
of this document with the words added in it highlighted blue, a red mark where words of the
earlier one were removed (the mark's comment says which words), and a box around every
picture that was added, removed or changed size. Every change is a markup whose comment
says what changed ("Was: July 13  |  Now: draft"), listed in the Markups list, and a summary
page at the end lists them all, a change repeated on every page (a header) once with its
pages. A moved paragraph counts as removed in one place and added in the other; a scanned
page without a text layer is compared only as a picture (run OCR on both documents first to
compare its words). <b>Drawings, laid over each other</b> is for plans and sheets: a new
document overlays the two on each page: red = only in the earlier one, blue = only in this
one, gray = unchanged, with each changed area clouded and listed in the Markups list. If the
drawing moved on the sheet between revisions (re-plotted with a different margin, say), the
pages are lined up first, so only real changes show; the top of the page says how far it
moved. A revision plotted at another paper size (a 24x36 sheet and its 11x17 print) is scaled
to the earlier one's size first, with some tolerance for the thicker lines a reduced print
has, and the top of the page says so. Two prints of the same drawing should then show no
changes; if a result has changes everywhere, the two files are not the same drawing at the
same scale. The way that fits is picked for you (text when both documents have a text layer
on most pages); either can be chosen.</li>
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
Plain text (.txt). Images make one picture per page, named after the name you choose plus the
page number (plan_p1.png, plan_p2.png...); if any of them exist already, you're asked once
before they're replaced.</li>
</ul>

<h2 id="preferences">Preferences</h2>
<ul>
<li><b>File &gt; Preferences...</b> (Ctrl+K) gathers the options KanzonasPDF remembers in one
window, with the sections listed on the left. An option that also has a menu command does exactly
the same as that command, so you can change it in either place. <b>OK</b> uses your changes and
closes the window; <b>Apply</b> uses them right away and leaves the window open, so you can see
the effect and keep adjusting; <b>Cancel</b> closes it without the changes made since the last
Apply.</li>
<li><b>General:</b> theme (Match Windows, Light, Dark), <b>Language</b> (Automatic, the language
of Windows; English; Español: menus, messages and this manual; a change shows the next time
KanzonasPDF starts), Ribbon (instead of toolbars), Show group names on ribbon, Show menu bar,
Show text labels on toolbars, Check for updates automatically. It also tells you where your
settings are saved (the data folder in portable mode). A saved setting that can't be used (one
edited by hand, say) is replaced by its default. Should one still stop KanzonasPDF from starting,
it starts with the default settings, says so, and lists the old ones in
settings-before-reset.txt in the data folder.</li>
<li><b>You:</b> the Author name for markups (recorded on new markups and shown on stamps), and
Set up my signature... / Set up my initials... with whether each is saved yet, and Change PIN...
to set, change or remove the PIN that protects them (leave the new PIN empty to remove it), and
the Signature width and Initials width used when you click to place them, and the Date format
the Date tool writes.</li>
<li><b>Markup styles:</b> pick a tool on the left to set its default colors, line width, font
size, fill, opacity and so on, the same settings the Properties panel shows when that tool is
active. Reset defaults puts a tool back to how KanzonasPDF came.</li>
<li><b>Start-up and opening:</b> reopen the documents that were open when you closed
KanzonasPDF (off by default; this also works when a setup closes KanzonasPDF to update it, or
Windows closes it to shut down or sign out), whether to ask before closing with several documents open (on
by default), the zoom a document opens
at (Fit width by default; Fit page, the whole page in the window; Actual size; or the zoom it had
when you closed it), and whether to reopen it at the page you were on last time.</li>
<li><b>Saving:</b> how often to back up unsaved changes (every 5 minutes by default; Off turns it
off). A copy of each document with unsaved changes is kept in the backups folder and deleted when
you save or close it. If KanzonasPDF or Windows stops unexpectedly, the next start offers to open
the copies. When a setup or Windows shutting down closes KanzonasPDF, nothing can be asked, so
each document's latest unsaved changes are first written to its copy, and the next start offers
them the same way. Each opens in a tab named after its original file with "(recovered)" added, marked as
unsaved; Save asks where to keep it, offering the original file (or Untitled for a PDF that was
never saved). Offered copies stay in the backups folder (Open backup
folder) for 30 days. <b>Backup folder</b>: Change... picks another folder (if KanzonasPDF can't
write there it says so), Use default goes back to the standard one (in the data folder when
portable). Backups of open documents move to the new folder; recovered copies from earlier stay
in the old one. Password-protected documents aren't backed up, because the copy wouldn't
have the password.</li>
<li><b>Measuring:</b> the units offered for a page that has no scale yet, what feet and inches
round to (1/2" to 1/64"; 1/16" by default) and the decimal places for other units. Existing
measurement labels update when you next move or edit them.</li>
<li><b>Mouse:</b> the mouse mode (<b>Standard</b>, <b>Hand</b> or <b>CAD</b>; the mode's tool
is the one KanzonasPDF starts with and Escape goes back to), and each mode's own options:
<ul>
<li>Standard: Scroll one page per wheel step (on), Free page movement (off).</li>
<li>Hand: Free page movement (on), Scroll one page per wheel step (on), Clicking a markup with
the Hand selects it (on).</li>
<li>CAD: The wheel zooms at the cursor (Ctrl+wheel scrolls), Plus cursor, Open canvas around the
pages, Window (blue) and crossing (green) selection, Click, move, click draws the selection box,
Hold the button and drag to draw a lasso, Show the CAD tab, Letters typed over the drawing go to
the command line: all on (the last one is off for whoever had the CAD-style mouse before 1.5, so
the one-letter tool shortcuts they used keep working). With the click, move, click box and the
lasso off, a press, drag and release draws a box.</li>
</ul>
The note under Scroll one page per wheel step says when it applies: only while the whole page
fits in the window, as after Fit page.</li>
<li><b>Pages and display:</b> lock the page order, Show comment boxes, Highlight form fields,
Night mode (white lines on black), Enhance thin lines, <b>New PDF page size</b> (the size and
orientation File &gt; New PDF uses, or Ask every time),
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
<tr><td>Ctrl+E</td><td>Edit text (click: the paragraph; Alt+click: one line)</td></tr>
<tr><td>Ctrl+P</td><td>Print (with preview)</td></tr>
<tr><td>Ctrl+N</td><td>New PDF (blank page)</td></tr>
<tr><td>Shift+T</td><td>Add text (written into the page)</td></tr>
<tr><td>Ctrl+K</td><td>Preferences</td></tr>
<tr><td>Ctrl+;</td><td>Date (today's date where you click)</td></tr>
<tr><td>Shift+O</td><td>Edit objects (the page's own pictures and shapes)</td></tr>
<tr><td>Ctrl+Shift+H / U / X</td><td>Highlight / Underline / Strike</td></tr>
<tr><td>C / N / T / K</td><td>Comment / Note / Text box / Callout</td></tr>
<tr><td>R / E / O / D / Y</td><td>Rectangle / Ellipse / Circle / Cloud / Polygon</td></tr>
<tr><td>L / A / Shift+L / P</td><td>Line / Arrow / Polyline / Pen</td></tr>
<tr><td>M / X</td><td>Stamp / Eraser</td></tr>
<tr><td>G / I</td><td>Signature / Initials</td></tr>
<tr><td>Shift+M / Shift+A / Shift+C</td><td>Length / Area / Count</td></tr>
<tr><td>Shift+R</td><td>Redact</td></tr>
<tr><td>Shift+E</td><td>Erase content</td></tr>
<tr><td>Shift+P</td><td>Capture area</td></tr>
<tr><td>Ctrl+wheel</td><td>Zoom around the pointer (scroll up and down in the CAD mouse mode)</td></tr>
<tr><td>Shift+wheel</td><td>Scroll left and right</td></tr>
<tr><td>Shift (while drawing)</td><td>45&deg; lines, squares and circles</td></tr>
<tr><td>Shift+click (drawing tool)</td><td>Start a new markup on top of an existing one</td></tr>
<tr><td>Ctrl+click, Ctrl+drag</td><td>Select several markups</td></tr>
<tr><td>Ctrl+click a link (Select tool)</td><td>Open the link, also on a markup made a link (a plain click with the Hand tool)</td></tr>
<tr><td>Escape</td><td>Clear selection / put the tool down (back to the mouse mode's tool: Hand, Select, or Edit objects in CAD mode) / cancel a CAD command or a started selection box</td></tr>
<tr><td>Delete</td><td>Delete what's selected: markups, and in CAD mode the drawing's objects too</td></tr>
<tr><td>Ctrl+C / Ctrl+X / Ctrl+V</td><td>Copy / cut / paste (text, markups, pictures, pages)</td></tr>
<tr><td>Ctrl+A</td><td>Select all text on the page (all pages in the page list)</td></tr>
<tr><td>Ctrl+D</td><td>Duplicate selected markups (or pages, in the page list)</td></tr>
<tr><td>Delete (in the page list)</td><td>Delete the selected pages</td></tr>
<tr><td>Ctrl+L</td><td>Lock selected markups</td></tr>
<tr><td>Ctrl+Shift+] / Ctrl+] / Ctrl+[ / Ctrl+Shift+[</td><td>Front / forward / backward / back</td></tr>
<tr><td>Left / Right, Page Up / Page Down</td><td>Previous / next page</td></tr>
<tr><td>Home / End</td><td>First / last page</td></tr>
<tr><td>Ctrl+G</td><td>Go to page (the page box)</td></tr>
<tr><td>Tab / Shift+Tab</td><td>Next / previous form field (Space or Enter fills it)</td></tr>
<tr><td>Arrow keys (something selected)</td><td>Move it 1 pt; with Shift 10 pt; with Ctrl 0.1 pt</td></tr>
<tr><td>Ctrl+Shift+Plus / Minus</td><td>Rotate page</td></tr>
<tr><td>Ctrl+Shift+Up / Down</td><td>Move page</td></tr>
<tr><td>Ctrl+2 / Ctrl+0 / Ctrl+1</td><td>Fit width / fit page / actual size</td></tr>
<tr><td>Ctrl+F, Enter / F3, Shift+Enter / Shift+F3</td><td>Find, next match, previous match</td></tr>
<tr><td>Ctrl+H</td><td>Replace text</td></tr>
<tr><td>Ctrl+Shift+N</td><td>Move tab to new window</td></tr>
<tr><td>Alt+Down / Alt+Up</td><td>Next / previous comment</td></tr>
<tr><td>F1</td><td>This manual</td></tr>
<tr><td>Ctrl+Shift+P</td><td>Command palette</td></tr>
<tr><td>Ctrl+F1</td><td>Collapse / expand the ribbon</td></tr>
<tr><td>Ctrl+Shift+M</td><td>Show / hide the menu bar (ribbon layout)</td></tr>
<tr><td>F11</td><td>CAD mouse mode on / off (off goes back to Standard or Hand, whichever you had)</td></tr>
<tr><td>Letters, Enter (CAD mode)</td><td>Type a command on the command line (M Move, CO Copy, RO Rotate...); Enter runs it, and on an empty line repeats the last one. One-letter tool shortcuts don't apply in CAD mode (Shift+letter ones do), unless Preferences &gt; Mouse turns typing to the command line off.</td></tr>
<tr><td>F12</td><td>Night mode (white lines on black) on / off</td></tr>
<tr><td>Hold wheel + drag</td><td>Pan (any tool)</td></tr>
<tr><td>Alt (while drawing or dragging)</td><td>Don't snap</td></tr>
<tr><td>F4 / F6 / F7 / F8 / F9 / F10</td><td>Pages / Properties / Markups / Tool chest / Bookmarks / Split view</td></tr>
</table>
<p>Change any shortcut in View &gt; Keyboard shortcuts. A key can be used by only one command: if two commands share one, nothing is changed until you fix it. <b>Reset all to defaults</b> puts the built-in shortcuts back straight away. Changes apply in every window.</p>
"""


def manual_html():
    """The manual in the interface's language: Spanish when it's in Spanish, else English."""
    if language() == "es":
        from . import manual_es
        return manual_es.MANUAL
    return MANUAL


def sections():
    """[(anchor id, title)] of the manual's chapters, in order."""
    return re.findall(r'<h2 id="([^"]+)">(.*?)</h2>', manual_html())


class ManualDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("KanzonasPDF user manual"))
        self.resize(980, 720)
        lay = QVBoxLayout(self)

        bar = QHBoxLayout()
        bar.addWidget(QLabel(tr("Find in manual:")))
        self.find = QLineEdit()
        self.find.setClearButtonEnabled(True)
        self.find.setPlaceholderText(tr("Type a word, then Enter for the next match"))
        self.find.returnPressed.connect(self.find_next)
        bar.addWidget(self.find, 1)
        nxt = QPushButton(tr("Next"))
        nxt.clicked.connect(self.find_next)
        bar.addWidget(nxt)
        self.not_found = QLabel("")
        self.find.textChanged.connect(lambda: self.not_found.setText(""))
        bar.addWidget(self.not_found)
        lay.addLayout(bar)

        split = QSplitter()
        self.contents = QListWidget()
        self.contents.setMaximumWidth(260)
        self.contents.setAccessibleName(tr("Contents"))
        self._anchors = []
        for anchor, title in sections():
            self.contents.addItem(title.replace("&amp;", "&"))
            self._anchors.append(anchor)
        self.contents.currentRowChanged.connect(self._jump)
        split.addWidget(self.contents)
        self.text = QTextBrowser()
        self.text.setOpenLinks(False)
        self.text.setHtml(manual_html())
        split.addWidget(self.text)
        split.setStretchFactor(1, 1)
        lay.addWidget(split, 1)

        close = QPushButton(tr("Close"))
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
        self.not_found.setText("")
        if self.text.find(word):
            return True
        # wrap around to the top
        was, top = self.text.textCursor(), self.text.verticalScrollBar().value()
        cur = self.text.textCursor()
        cur.movePosition(cur.MoveOperation.Start)
        self.text.setTextCursor(cur)
        if self.text.find(word):
            return True
        self.text.setTextCursor(was)        # stay where you were reading
        self.text.verticalScrollBar().setValue(top)
        self.not_found.setText(tr("Not found"))
        return False


# ---- keeping the manual complete -------------------------------------------------
# Menu commands that need no explanation, or are covered under another name (their English
# names, also when the interface is in another language).
NOT_DOCUMENTED = {"exit", "about", "user manual", "close tab"}


def _norm(text):
    text = text.split("\t")[0].replace("&&", "\0").replace("&", "").replace("\0", "&")
    return " ".join(text.replace("...", "").replace("…", "").split()).strip().lower()


def _plain_manual():
    from PySide6.QtGui import QTextDocument
    d = QTextDocument()
    d.setHtml(manual_html())
    return " ".join(d.toPlainText().split()).lower()


def missing_from_manual(window):
    """Names of menu commands (every menu, every tool) that the manual never mentions.
    Used by the self-test so a new feature can't ship without being documented. The names
    are checked in the interface's language against the manual in that language;
    NOT_DOCUMENTED and the recent-files list are recognized by their English names."""
    from .main_window import english_name
    text = _plain_manual()
    missing = []

    def english(a):
        return _norm(english_name(a.text().split("\t")[0]))

    def walk(menu):
        for a in menu.actions():
            if a.menu():
                if english(a) != "open recent":      # the list of recent files
                    walk(a.menu())
                continue
            if a.isSeparator() or not a.isEnabled() and not a.text():
                continue
            name = _norm(a.text())
            if not name or english(a) in NOT_DOCUMENTED or not a.isVisible():
                continue
            if a.isEnabled() is False and a.toolTip() == a.text():
                continue
            if name not in text and name not in missing:
                missing.append(name)
    for top in window.menuBar().actions():
        if top.menu():
            walk(top.menu())
    return missing
