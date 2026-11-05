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

## Next
The owner sets this list; nothing below is promised until it's here.
1. **Random editing battery** (in progress): thousands of random edits with undo and redo mixed
   in, checked after every step (the MuPDF undo journal is where subtle bugs hide); a short run
   on every build, the long one by hand before releases.
2. **1.9** (in progress, chosen by the owner on 4 Nov 2026; each on its own branch, merged
   together, then the full checks and a break-it battery before the owner says build):
   - Dimension markups (measured, with extension lines and arrows): `claude/dimensions`.
   - Replace pages / slip sheets: a new revision of a sheet, by page number or matched by sheet
     number, keeping the markups, bookmarks and links: `claude/replace-pages`.
   - Markup legends that update themselves: `claude/legends`.
   - macOS, unsigned for now (Open Anyway once; signing can be added later): `claude/macos`.
   - Save as PDF/A (PDF/A-2b) with a check; accessibility tagging later: `claude/pdfa`.
   - The page's scale shown large on the Measure tab and the status bar (red when not set), a
     notice on the first unscaled measurement, an on-screen scale bar: `claude/scale-display`.
   - Edit text keeps each word's style; Bold, Italic, Underline, Strikethrough, color and size
     for selected words, bold and italic in the line's own font: `claude/text-styles` (done).
   - Then: the Spanish ribbon tabs fit a 1366-pixel screen; less memory for OCR.
3. **Code signing** for the Windows downloads, once the project qualifies again (a SignPath
   Foundation application was declined as too new; see CODE_SIGNING_POLICY.md).

## Standing decisions
- **Free, for good**: official releases stay free for personal and commercial use: no
  subscriptions, trials, paid tiers, required account or paid cloud service; donations never
  unlock features (README, "Free, for good").
- **AGPL-3.0**, because the PDF engine, PyMuPDF / MuPDF, is AGPL.
- **Windows and Linux**, the same features on both; Windows as an installer (this user or all
  users), a portable zip and a PortableApps.com package; Linux as an AppImage. macOS is coming
  in 1.9 (unsigned until there's an Apple Developer account), with the same features.
- **English and Spanish**: every user-facing text and the release notes in both.
- **Standard PDF**: markups are standard PDF annotations, so Acrobat, Bluebeam and others see
  them; nothing locks a file to KanzonasPDF.
- **Private**: no account, no telemetry; the only call home is the optional update check.
- **Fast and light, like PDF-XChange**: the speed and memory budgets in AGENTS.md are checked
  by every build; heavy libraries load only when used.
- **Undo goes through MuPDF's journal** (undo_journal.py), not a copy per edit.
- **Releases**: every change goes through a pull request; the Windows and Linux builds must pass
  (a rule on `main` enforces it); merging a new version publishes it, with SHA-256 checksums.
- **Signing**, when it comes, happens only in the automated build (CODE_SIGNING_POLICY.md).
- **Branding shared with KanzonasCAD**: the same cactus and sunflower, the logo made by
  KanzonasCAD's tools/make_logos.py ("Kanzonas" in Roboto Condensed Medium, "PDF" in Saira
  Condensed, red as the icon), the icon's PDF tag matching KanzonasCAD's CAD tag.
