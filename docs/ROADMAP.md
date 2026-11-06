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

## Next
The owner sets this list; nothing below is promised until it's here.
1. **1.10** (chosen by the owner on 6 Nov 2026; each feature done on its own branch, to be merged
   together, then the full checks, long batteries and a break-it battery):
   - Reading comfort (Full screen, Presentation, page layouts, Reading view, Read aloud, Auto
     scroll): `claude/reading`.
   - Batch processing (Action wizard-style steps over many files, into a Processed folder):
     `claude/batch`. Search & redact in a batch applies by default (owner, 6 Nov: the originals
     stay); when only marking, the results say plainly that nothing was removed yet.
   - Bookmarks made from headings, tags or sheet numbers, and Insert table of contents:
     `claude/bookmarks`.
   - Smart forms (calculations, formats and validation from the standard calls, never running
     JavaScript): `claude/forms`. A percent field reads a bare 25 as 25% (owner, 6 Nov; the value
     kept is 0.25, so Acrobat's calculations still work; Acrobat itself shows 2500%).
   - Comments review (XFDF/FDF import and export, reply threads, review statuses):
     `claude/comments`.
   - Accessibility (Check accessibility against PDF/UA, Auto-tag, alt text, reading order):
     `claude/accessibility`.
2. **French, German and Portuguese** (the app and the manual), after 1.10's features (owner,
   6 Nov).
3. **Code signing** for the Windows downloads, once the project qualifies again (a SignPath
   Foundation application was declined as too new; see CODE_SIGNING_POLICY.md).

## Standing decisions
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
- **Branding shared with KanzonasCAD**: the same cactus and sunflower, the icon's PDF tag
  matching KanzonasCAD's CAD tag.
- **Logos come from the website repo** (owner, Nov 2026): every Kanzonas logo is made in
  Kanzonas-Site's `brand/` folder, the single source of truth ("Kanzonas" in Roboto Condensed
  Medium, "PDF" in Saira Condensed, red as the icon; brand/SPEC.md). Changed there, never
  here; its files are copied in.
