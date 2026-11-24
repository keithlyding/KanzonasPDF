# KanzonasPDF roadmap

The order of work and the owner's decisions. Read it before starting a feature; update it when
a decision changes or a piece of work lands. Details of each version are in
[CHANGELOG.md](../CHANGELOG.md); plain-language notes in [RELEASE_NOTES.md](../RELEASE_NOTES.md).

## Done
- 0.44-0.60: OCR (PDF-XChange-style dialog), Edit objects (move, resize, delete a page's own
  pictures and shapes), backgrounds.
- 0.70-0.80: the Markup tab, measuring with snapping (to objects, the page, the grid).
- 0.90-0.95: Edit text in place; KanzonasPDF's own Print window; a document in its own window;
  command palette and night mode; Compare documents (text, word by word, or drawing overlay);
  editing text on scanned pages.
- 1.0 (Oct 2026): the first full release.
- 1.1-1.4: Enhance thin lines; File > New PDF; links on anything; paragraph editing.
- 1.5: Spanish (the whole app and manual); Update now installs for installed copies.
- 1.6: mouse modes (Select, Hand, CAD) and CAD mode's AutoCAD-style commands.
- 1.7: Linux (AppImage), with desktop integration and self-update.
- 1.8: print production (Print tab: page boxes, hairlines, preflight check, crop marks); the
  PDF tag on the icon. 1.8.2: the logo set in real fonts, matching KanzonasCAD's.
- 1.8.3: the random editing battery (thousands of edits with undo, redo and saves, checked after
  every step; a short run on every build).
- 1.9 (Nov 2026): File > Scan (eSCL, WSD, WIA, SANE, the printer's panel, a watched folder; the
  owner's priority, for the owner's Dell E525w); styled words in Edit text; Dimension and Legend markups;
  Replace pages; Save as PDF/A and Check PDF/A; the page scale shown, with a scale bar; macOS
  (Apple silicon, unsigned); then a break-it battery (text, markups, scanning and redaction).
- 1.9.1: text editing, from the owner's use (8 Nov: "Editing text is a pain... I can't copy a
  text box and move it elsewhere"): Properties' Bold, Italic and size change the selected words
  while editing; what Add text writes is remembered as one block (a /KZText marked-content
  marker holding numbers only, never the words, so redaction can take them all) and Edit text
  opens all of it; Edit objects copies, cuts, pastes and duplicates the page's text with its
  styles, also into another document. Then (owner, 8 Nov) the page's own pictures and shapes
  copied, cut and pasted to another page or document, and CAD mode's Move and Copy (and a
  selection dragged) across pages: pasted into another document, content drops its layer
  membership (that document doesn't have the layer). Also from the owner's use: the editing
  box no bigger than its text (small text typed enlarged with a true-size preview), and printed
  lines no longer faint (Dark thin lines in the Print window).
- 1.10 (chosen by the owner on 6 Nov 2026; each feature on its own branch, brought up to 1.9.1
  and merged together, then the full checks, long batteries and a break-it battery): smart
  forms (calculations, formats and validation from Acrobat's standard calls, never running
  JavaScript; a percent field reads a bare 25 as 25%, owner, 6 Nov); comments review (replies,
  statuses, XFDF/FDF checked against Apache PDFBox's reader and Acrobat's files, as Adobe's
  copy of the specification couldn't be fetched); accessibility (Check against PDF/UA,
  Auto-tag, alt text, reading order; tags kept in step with every edit; redaction takes out
  alt text); batch processing (Search & redact applies by default, owner, 6 Nov; mark only
  says nothing was removed and names files -marked; the single-file commands' own redaction
  and OCR); bookmarks from headings, tags or sheet numbers and Insert table of contents;
  reading comfort (Full screen, Presentation, page layouts, Reading view, Read aloud with the
  system's voices, Auto scroll; the builds leave out Qt's multimedia backends and FFmpeg).
- 1.10.1: links to other files found again when an index was made on another computer or its
  folders moved (the owner's drawing index, 9 Nov).
- 1.11 (owner, 11 Nov, from the first outside tester's issue #82 and the owner's own use):
  markups anywhere in the gray around a page (the gray works as it always has; a page with
  markups beside it gets just the room they need; Review > Show markups on the page / outside
  pages; Fit page and markups; printed only when asked, on the same sheet or on an extra
  sheet at scale; other PDF programs don't show them, so Sanitize and Remove hidden
  information take them out); Pages > Add space around page (real page, everything staying in
  place); what's drawn stays selected and Set as Default; opacity on pictures and captures
  fixed; the front document tab marked; PyMuPDF 2.1 (MuPDF 1.28.6; issue #80; the owner chose
  to take it with this release, not 1.10.1). Bluebeam's own manual and forum were read for
  how it does these (support.bluebeam.com and community.bluebeam.com are allowed in the
  environment).

- 1.11.1 (owner, 11 Nov, from the owner's use): dragging a page in the Pages panel scrolls the
  list near and past its top or bottom, so a page can go anywhere in a long document; Create
  PDF from images and Combine files can recognize the text on the pictures (OCR) and save it.
- 1.12 (owner, 11 Nov, after a Bluebeam Revu screenshot from a colleague: "add all of the
  features except Studio", "all in one release"; grouping and layers also asked for in issue
  #82): View > Rulers and the pointer's position and page size on the status bar, with a Reuse
  switch; Split view side by side or top and bottom, any open document, Sync by page number or
  by the pages in view; Arrange > Group / Ungroup (the standard PDF group) and Flip; markups on
  layers (the PDF's own optional content: a layer new markups go on, moved between layers,
  the Markups list's Layer column and filter); Spaces (named areas; the Markups list's Space
  column and filter); Sets (several PDFs browsed as one in the Sets panel, by sheet number
  and title, Next / Previous sheet across files, Combine to one PDF). The random battery now
  groups, flips, moves markups between layers, hides layers and draws spaces; it found that
  Duplicate pages gave a page with nothing tagged and its copy the same StructParents key
  (in 1.11.1 too), fixed.
- 1.12.1 (owner, 12 Nov): in CAD mode a drag from the selection moves it (with the four-way
  arrow over it); the Select tool's pointer is the arrow (the text cursor only with text tools
  and where text is typed); Pages > Insert pages from file can recognize the text of the
  pictures inserted (OCR), as an option.
- 1.15.8 (owner, 18 Nov: "When I'm selecting text (not in cad mouse), the cursor is a hand
  instead of the text cursor"; "The cursor should be the pointer arrow until it browses over
  text"): the 12 Nov "no text cursor" holds in CAD mode only. In the Standard and Hand modes,
  Select and the Hand are the arrow, the text cursor over text, and the Hand selects text by a
  drag from it, as Acrobat's does (a drag elsewhere moves the page, with the closed hand;
  Preferences > Mouse, Hand can switch that off, and the Hand is the open hand again). In the
  Standard (Select) mode nothing drags the page ("When in select mode, the hand should not
  drag the page"): the Hand picked there is Select; the held wheel moves the page.
- 1.15.9 (@cloydcc-dev's issue #107, the owner's choices of 19 Nov): Count set up in
  Properties (Group, New count, Layer, the next number); Keep the numbers in order, on by
  default (a delete or a move to another group renumbers the group); a marker's group and
  number changed in Properties (the Markups list stays read-only); placed Count markers
  aren't selected, so Properties keeps the tool's settings while clicking. Then (the same
  day): each New count its own color, a group picked again its markers' look, and a group's
  gaps or repeats said in Properties with Renumber beside it.
- 1.15.10 (owner, 19 Nov): **the Hand only views** ("I want the hand to always show no matter
  what. Selecting text or objects while in hand should not be doable. Hand is like a view only
  type thing"), replacing 1.15.8's Hand that selected text and 1.12's that selected markups:
  always a hand (the pointing hand on a link), never selects or edits, follows links (also
  under a markup) and fills forms, a view-only right-click menu; Space held drags the page with
  any tool. Back / Forward across documents (Alt+Left / Alt+Right, beside Undo and Redo, View >
  Go to, the right-click menu); Ctrl+middle-click a link: a new tab (view only) or the split
  view, asked once; links to turned pages and through named destinations land where they say.
- 1.15.11 (owner, 19 Nov: "Can ctrl+w close the tab (and ask to save if needed)?"): Ctrl+W
  closes the tab, Ctrl+F4 still does; unsaved changes are asked about first.
- 1.15.12 (owner, 20 Nov: "I was in the middle of drawing a polygon and had to zoom. The whole
  shape moved on me"): a zoom while drawing keeps the points clicked so far on the page.
  And Shift while dragging a polygon's corner keeps both its sides straight ("to make them
  connect straight and at right angles").
- 1.15.13 (@cloydcc-dev, issue #107, 21 Nov): a selected Count marker shows a box (its outline
  was a box of no size under its dot). Shipped before the Scan window fix (then 1.15.14), by the
  owner's rule: an outside issue's fix ships first.
- 1.15.14 (owner, 21 Nov: the old Windows test crash, "let's try to identify that bug and fix
  it"): the Scan window's worker threads only queue their answers (no Qt signal from a
  worker thread: one sent while the window was deleted crashed).
- 1.15.15 (owner, 21 Nov): numbered dots: a dot just placed isn't selected (Properties keeps the
  tool's settings, as for Count); the number inside a filled dot takes the text color chosen; Dot
  is named Numbered dot, its tooltip pointing to Count for counting.
- 1.15.16 (owner, 21 Nov: "raise it to 100"): undo keeps the last 100 steps (30 before); the
  manual says when Undo runs out, no message ("It's a normal thing for undo to run out").
- 1.15.17 (owner, 22 Nov: "If we know about a bug, we need to fix it"): Python's garbage
  collector runs only on the main thread (gc_main.py): a collection on a worker thread deleted
  closed windows off their own thread (a crash).
- 1.15.18: only documents open in a tab count in the page list's thumbnail cap (1.15.17's
  build on main failed on it and wasn't published; its notes come with 1.15.18).
- 1.15.19 (@cloydcc-dev, issue #120; the owner, 22 Nov: yes, on the View tab): View > Show
  line weights; off, every line drawn thin on screen (line_weights.py). And (the owner: "let's
  add that too") Properties > Line width for the page's own lines. The owner replies on #120
  once it's out and checks it's what he asked for.
- 1.15.20 (the random battery, seed 13): text written again (Text color, moved, Edit text)
  uses a copy of its font that draws its letters, not one Save cut down to other letters.
- 1.15.21 (owner, 22 Nov: "Almost how Microsoft does it"; "all of them but as one release"):
  lines' Start / End arrowhead, Middle arrow and Line style in Properties, for markups and the
  drawing's own lines (with their Line color and Fill color there too). Its fixes (the
  owner, 22 Nov): Line width's arrows and typed values, and Rotate by showing how far it
  turned instead of going back to 0.
- 1.16 (the owner, 22 Nov: "All non-markup edits need to be in the properties panel ... there
  needs to be a way of differentiating whether what's being edited and added is a markup vs a
  document change"; on the proposal: "Do what you think is best"): Properties and every
  tool's tooltip say Markup or Page content; the page's text selected in Edit objects has
  Font, Font size, Bold, Italic, Underline, Strikethrough, Text color and Text background in
  Properties, and so does the open Edit text / Add text box; Text background is the words
  highlighted in the page itself (each word's own style), as against the Highlight markup.
  Decided against a separate Edit ribbon tab: the Markup tab already holds only markups,
  and the tags and tooltips say which is which.
- 1.16.4 (the owner, 23 Nov): **Fill opacity** apart from the outline's and text's (the fill
  drawn in its own graphics state in the markup's appearance, so other viewers show it);
  **Arrowhead size** (25% to 500% of the size the line's width gives; MuPDF's ends scaled in the
  appearance, the PDF's line endings kept); **grouping the drawing's own objects on big CAD
  sheets**: across layers (each object keeps its layer inside the group), shown as one group,
  and fast (the owner's 174,000-object sheet: 4.6 s to under half a second). The arrowheads of
  the drawing's own lines (Edit objects) keep their size for now.
- 1.16.4 (the owner, 23 Nov: "when making custom colors, a recent or currently used colors
  section"): one color picker for every color in the app (`kanzonas/color_picker.py`): Qt's own
  color dialog inside a small dialog, with a Recent row (the last 12 colors picked anywhere,
  kept in the settings) and an In this document row (the colors of the open document's
  markups, read from the markups only, when the picker opens, without loading pages). A
  small dialog around Qt's rather than Qt's dialog with a strip added: the system's dialog
  (macOS's color panel, GTK's) can't hold the rows, and Qt's own custom color slots are the
  user's to keep.
- 1.17 (the owner, 23 Nov: "the side panels must be able to show several at once, on the
  right and on the left, stacked, with handles to resize"): every panel (Pages, Bookmarks,
  Layers, Objects, Sets, Properties, Tool chest, Markups list) is a Qt dock widget of its own
  (`kanzonas/side_panels.py`), no longer Bookmarks, Layers, Objects and Sets as tabs inside
  Pages: stacked on either side with QMainWindow's handles, dragged by the title (or moved
  from the title's right-click menu) to the other side, kept with saveState (LAYOUT_VERSION 2;
  a layout 1.16 saved is still read). Dock widgets rather than our own splitters: Properties,
  Tool chest and the Markups list were dock widgets already, and Qt gives the handles,
  dragging, tabs and the saved layout. Panels don't float (one left on a monitor that's gone
  would be lost). The panel strip has an icon for each panel; a pulled-out window starts with
  the panels of the window it came from.
- 1.17 (the owner, 23 Nov: the markup shapes stay markups; drawing that isn't a markup gets a
  tab of its own): the **Drawing tab** (`kanzonas/drawing.py`): line, arrow, polyline,
  polygon, rectangle, ellipse, circle, arc, cloud and pen drawn into the page's content stream
  (with the markup tools' clicks, previews, snapping and CAD click-click; each tool's own
  style in Properties), on one layer, the optional content group "KanzonasPDF drawing", so the
  Layers panel hides it and Edit objects selects, restyles, groups and reorders it as the
  drawing's own lines (the stacking order commands now keep an object's layer; a frame clip
  holding all of them no longer stops grouping them). Told apart from markups by its tab, its
  layer, an orange selection and Properties' Page content tag. **Convert to drawing** (the
  Drawing tab, a markup's right-click menu) draws shape and line markups into the page as
  their appearance draws them, one undo step; measurements, notes, stamps, text and
  highlights stay markups.

## Next
The owner sets this list; nothing below is promised until it's here.
- **Takeoff and quantity surveying** (the owner, 23 Nov 2026: estimators and quantity surveyors
  are a key audience, pdf.kanzonas.com/pdf-takeoff-software). Seven pieces, in this order, each
  its own release following AGENTS.md, each measured at scale (thousands of markups) against
  the speed budgets and put in the random battery where it changes markups. When one is
  released the owner is told, so the website session can update that page (its "What it
  doesn't do" list says counting is by clicking and that it doesn't price). Already there
  before them: the scale tools, Length, Polylength, Area, Perimeter, Volume (area x depth),
  named Count groups, Spaces, Legends and the Measurement summary with CSV export (one row a
  kind and Count group; none of the seven below was there, in part or whole).
  1. **Cut-outs in areas** (1.16.1): openings taken out of an Area or Volume (a stair shaft, a
     window, a column); it shows the net value, the summary and legends total net. Kept in
     the markup itself (KZProps geom "holes"), drawn as holes in its appearance (even-odd
     fill), so they move, copy, undo and save with it and other viewers show them.
  2. **Excel export of the takeoff, grouped** (1.16.2): the Measurement summary to .xlsx (openpyxl,
     lazily), grouped by sheet, by Space and by Count group or kind, with quantities, units
     and subtotals; CSV stays. The start of a bill of quantities.
  3. **Wall area from a length** (1.16.3): a Height on Length and Polylength (as Volume's Depth),
     showing length x height as well (drywall, paint, insulation, masonry).
  4. **Drops on runs** (1.16.3): vertical lengths (drops, rises) at chosen points of a Polylength,
     counted in its total, shown on the markup and in the summary (conduit, wire, pipe).
  5. **A quantity per count, and waste** (1.16.3): items per counted item with their own units ("each
     fixture = 2 boxes + 1 whip"), and a waste or extra percentage for a group or
     measurement; the summary and the Excel export show counts and resulting quantities.
  6. **Slope for roof areas** (1.16.3): a pitch on an Area (6:12, or degrees) turning the plan area into
     the sloped area.
  7. **Find similar symbols** (1.17, as Bluebeam's VisualSearch): one symbol picked, its matches
     found on the page or the whole set and placed as Count markers in a group, for the
     user to check before keeping. Last, the hardest: fast on big sheets, with no worker
     thread touching the document.
- **1.14.1: thumbnails and the Preview pane in Windows File Explorer** (owner, 13 Nov:
  "when I look in a folder, it doesn't just show a bunch of KanzonasPDF icons"; "Yes, do both
  thumbnails and preview pane"). KanzonasPDFShell.dll (shell_ext/): a C++ thumbnail handler
  and preview handler drawing with PyMuPDF's own MuPDF (its mupdfcpp64.dll, so PyMuPDF's
  security updates cover it), registered by the installer with the PDF entry (KanzonasPDF's
  ProgID only: thumbnails show when KanzonasPDF is the default PDF app; not the portable
  versions), run by Windows outside Explorer, tested on the Windows build machine.
  **Preview pane changed in 1.15.7** (owner, 16 Nov: Outlook classic said "This file cannot be
  previewed because there is no previewer installed for it"; "I want whatever option makes it
  just simplistic for people who don't know computers very well"): Outlook lists only
  previewers registered for the whole computer, and installs are for one user by default, so
  KanzonasPDF's own Preview pane handler is no longer registered; Windows' own PDF previewer
  shows previews in Explorer and Outlook, as before 1.14.1. Thumbnails stay KanzonasPDF's.
- **Releases** (owner, 12 Nov): a day's notes go into as few releases as practical, but a
  release isn't held for the evening ("I don't want to wait until tonight"); a critical fix
  goes out at once. Outside contributors (@hamishpoole-hill-ctrl's suggestions, issue #82;
  @fexxdev's PRs) come in before our own work of the same day (owner: "Let's get that in
  there before our stuff"), and are credited by GitHub handle only (README, release notes).
  **Merge when green** (owner, 19 Nov, after issue #107's fix took all day: "I agree with both
  of your suggestions. Please do this going forward"): an agent's own pull request is merged,
  and so released, as soon as its checks are green on GitHub and it merges cleanly, unless the
  owner has said to hold it; the owner is told each time. **An outside issue's fix ships
  first**: the fix for what was asked goes out on its own as soon as it's ready, and further
  ideas (the owner's or an agent's) follow in a later release the same day, not in the same one.
- **1.15: colors of the page's own content** (owner, 12 Nov: "Need a way of changing text's
  color and changing the fill color of an object", "Both"; on hold, then asked for on 14 Nov):
  Edit objects / CAD mode > right-click > Line color..., Fill color..., Text color... (Edit
  text already colored single words through Properties). With it, a version never published
  has its notes carried into the next release (owner, 12 Nov; tools/release_notes.py).
0. **The next fix release: Redo lost after undoing Auto bookmarks** (owner, 11 Nov: ship 1.11,
   fix this next; 1.11.1 went to the owner's Pages panel and OCR requests).
   Found by the random battery (seed 31, 1500 steps, PyMuPDF 2.0 and 2.1, also in 1.10.1): after
   an Auto bookmarks step is undone, opening a page with a calculated form field again (MuPDF's
   fz_load_page) makes MuPDF write that field's appearance anew (a new Helvetica font object
   in its /Resources), and that change drops every step to redo. Not reproduced yet outside
   the full run (the state MuPDF keeps in memory matters, not the file); NeedAppearances is
   false and resynth_required and recalculate are 0 at that point. Nothing is lost but Redo.
0. **From the first outside tester (issue #82, @hamishpoole-hill-ctrl, 11 Nov; owner: "good ideas"):**
   - (Done in 1.12: grouping markups and markups on layers.)
   - (Done in 1.11: markups anywhere in the gray, for his use: "plans that are spread across
     multiple sheets back together for review".)
   - **The Mac download not installing** for a colleague of his: asked for the Mac's model,
     macOS version and the message shown (Apple silicon and macOS 14.4 or newer only; not
     signed by Apple yet, so Privacy & Security > Open Anyway the first time).
1. **French, German and Portuguese** (the app and the manual), next now that 1.12 is out
   (owner, 11 Nov: the Bluebeam features first, so their words are translated once; set as
   next on 6 Nov).
2. **Export to Markdown** (owner, 12 Nov: "let's just add it to the roadmap"; not scheduled):
   File > Export to > Markdown, next to Word, Excel and PowerPoint: a document's text with its
   headings, lists, tables, bold and italics as a plain .md file, the way people feed documents
   to AI tools or paste them into notes and wikis. PyMuPDF's companion `pymupdf4llm` does the
   conversion (AGPL, as PyMuPDF; imported only when used, as the other exports). For text
   documents; drawings have little to give, scanned pages need OCR first.
3. **Code signing** for the Windows downloads, once the project qualifies again (a SignPath
   Foundation application was declined as too new; see CODE_SIGNING_POLICY.md).

## Standing decisions
- **Main doesn't run the tests again for files its pull request already tested** (owner,
  23 Nov: "do your efficiency changes"). A pull request squash-merged after main was merged
  into it gives main exactly the files of its last commit, whose build ran every regression
  test; the workflow's `tested` job (tools/tested_on_pr.py) checks that with GitHub, and the
  Windows, Linux and macOS jobs skip their tests then, each only if its own passed there.
  The apps are still built from main and self-tested, installed and updated. Main moved on
  since, no pull request, a test that didn't pass, a tag or a run by hand: every test runs.
  This saved about an hour and a half per release (the Mac's tests).
- **A release can go out without the Mac version** (owner, 23 Nov: "We update this so often,
  we can skip a build for Mac with no issues"). GitHub's Mac machines are sometimes all taken:
  a macOS job that never got one is cancelled after 15 minutes without running a step, and the
  release then goes out with Windows and Linux only (the publish job's "Did the Mac build
  run?" asks GitHub). A Mac build that failed, or started and was cancelled, still publishes
  nothing. On a Mac, the update check offers only releases that have the disk image
  (`updates.up_to_one_with`).
- **The battery runs every night** (owner, 23 Nov: "add a nightly battery test that runs at
  12am"). .github/workflows/nightly-battery.yml runs tests/battery_random.py on main at 05:00
  UTC (midnight EST), 2,000 steps per run with seeds new each night from the date: three runs
  on Linux (one tagged), one on Windows, one on macOS. A failure goes into one open issue
  labeled "battery", with the seed and step: a known bug, fixed like any other.
- **No slop** (owner, 13 Nov: "please add a search for slop in future testing"; what AI tools
  leave behind): `tools/slop_check.py`, its hard rules in every build (tests/test_slop.py), its
  soft report read before each release (see AGENTS.md).
- **Outside contributions are welcome, and speed is a condition for taking them** (owner, 12
  Nov, on @fexxdev's PRs #86 Italian and #87 Dot markers: "I want to make sure the
  program stays fast"). Each must pass `--selftest`'s speed budgets on the current `main`, and
  add no loop over every markup or object on the way to an edit (per-page cached indexes, as
  AGENTS.md's Performance section says). Their code runs in this repository's builds (copied to
  a `claude/review-...` branch: the builds run for branches here only) before it's merged.
  Accepted on those terms: the six fixes of #87 (as their own PR first), Italian (#86), then the
  Dot as its own tool (not folded into Count).
- **No live shared markup sessions like Bluebeam Studio** (owner, 11 Nov): they need a server
  everyone's copy connects to, cloud storage and accounts, against "Free, for good" and
  "Private" below. If shared review is wanted, it would go through files (markups exported to
  a file and several reviewers' files merged into one PDF), never a service.
- **A PDF viewer and editor first**: KanzonasPDF is presented as a free, general PDF viewer and
  editor and an alternative to Acrobat Pro and PDF-XChange Editor (README, store listings,
  screenshots). Measuring for drawings is a feature for one audience; CAD mode is a fun extra,
  not the headline (owner, 6 Nov 2026).
- **Free, for good**: official releases stay free for personal and commercial use: no
  subscriptions, trials, paid tiers, required account or paid cloud service; donations never
  unlock features (README, "Free, for good").
- **AGPL-3.0**, because the PDF engine, PyMuPDF / MuPDF, is AGPL.
- **Windows, Linux and macOS**, the same features on all three; Windows as an installer (this
  user or all users), a portable zip and a PortableApps.com package; Linux as an AppImage; macOS
  (since 1.9) as a disk image for Apple silicon only, no Intel build (owner, 6 Nov 2026), unsigned
  until there's an Apple Developer account.
- **English, Spanish and Italian**: every user-facing text and the user manual in all three;
  the release notes in English and Spanish, and in Italian from 1.13.
- **Standard PDF**: markups are standard PDF annotations, so Acrobat, Bluebeam and others see
  them; nothing locks a file to KanzonasPDF.
- **Private**: no account, no telemetry; the only call home is the optional update check.
- **Fast and light, like PDF-XChange**: the speed and memory budgets in AGENTS.md are checked
  by every build; heavy libraries load only when used.
- **Undo goes through MuPDF's journal** (undo_journal.py), not a copy per edit.
- **Releases**: every change goes through a pull request; the Windows and Linux builds must pass
  (a rule on `main` enforces it); merging a new version publishes it, with SHA-256 checksums.
- **Signing**, when it comes, happens only in the automated build (CODE_SIGNING_POLICY.md).
- **Branding shared with KanzonasCAD**: the same cactus and sunflower, the icon's PDF tag
  matching KanzonasCAD's CAD tag.
- **Logos come from the website repo** (owner, Nov 2026): every Kanzonas logo is made in
  Kanzonas-Site's `brand/` folder, the single source of truth ("Kanzonas" in Roboto Condensed
  Medium, "PDF" in Saira Condensed, red as the icon; brand/SPEC.md). Changed there, never
  here; its files are copied in.
