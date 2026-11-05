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
2. **Code signing** for the Windows downloads, once the project qualifies again (a SignPath
   Foundation application was declined as too new; see CODE_SIGNING_POLICY.md).

## Standing decisions
- **Free, for good**: official releases stay free for personal and commercial use: no
  subscriptions, trials, paid tiers, required account or paid cloud service; donations never
  unlock features (README, "Free, for good").
- **AGPL-3.0**, because the PDF engine, PyMuPDF / MuPDF, is AGPL.
- **Windows and Linux**, the same features on both; Windows as an installer (this user or all
  users), a portable zip and a PortableApps.com package; Linux as an AppImage.
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
