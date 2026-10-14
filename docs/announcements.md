# Telling people about KanzonasPDF

Drafts for the places where its users are. Post as a maker asking for feedback, not as an
advertiser; be plain about what it doesn't do yet. Keep comparisons to needs ("Bluebeam-style
measuring without the license"), not to other products' faults. Read each forum's
self-promotion rule before posting.

## GitHub repository topics

Settings (gear icon next to About on the repository page) > Topics:

    pdf pdf-editor pdf-viewer pdf-annotation markup measurement construction cad
    bluebeam-alternative acrobat-alternative windows portable python pyside6 pymupdf
    open-source

## Reddit

Subreddits to consider (check each one's rules first; some want flair or a weekday):
r/Bluebeam, r/Construction, r/civilengineering, r/estimators, r/architecture, r/opensource,
r/software, r/windows.

**Title:** I made a free, open-source PDF markup and measuring app for drawings (Windows)

**Body:**

> I spend my days marking up and measuring PDF drawings and got tired of paying for it, so
> I've been building KanzonasPDF: a free, open-source PDF editor for Windows aimed at
> construction and engineering work.
>
> What it does: calibrate a sheet and measure length, area, angle, radius, perimeter, volume
> and counts (with a summary you can export to CSV); revision clouds, callouts, stamps and
> the usual markups (standard PDF annotations, so Acrobat and Bluebeam see them); compare two
> revisions and cloud the differences; forms, signatures, redaction, OCR; edit the page's own
> text and objects; combine, rotate, crop, split. It stays fast on big CAD sheets (a 60,000
> line sheet opens and draws in about a second).
>
> No account, no telemetry, nothing phones home except an optional update check. There's an
> installer, a portable zip for a USB stick, and a PortableApps.com package.
>
> What it isn't: finished. It's version 0.9x, the installer isn't code-signed yet (SmartScreen
> warns the first time), it's Windows only, and it has rough edges I'd like to hear about.
>
> Download and source: https://github.com/keithlyding/KanzonasPDF
>
> If you use Bluebeam, Acrobat or PDF-XChange, I'd like to know what you'd need before you
> could use this for real work.

## Hacker News (Show HN)

Post once, after a release with screenshots in the README. Rules: https://news.ycombinator.com/showhn.html

**Title:** Show HN: KanzonasPDF – free, open-source PDF markup and measuring for drawings (Windows)

**Text:**

> KanzonasPDF is a PDF editor for people who mark up and measure construction and
> engineering drawings, the work Bluebeam Revu is usually bought for. It's free software
> (AGPL), Windows only for now.
>
> Technically: Python, PyMuPDF (MuPDF) for rendering and editing, Qt (PySide6) for the UI.
> Big CAD sheets render in tiles from a cached display list, so a 60,000-line sheet opens and
> draws in about a second and zooming to 400% stays smooth; the build fails if start-up,
> rendering or memory goes over a budget. Text editing rewrites one line at a time with the
> original embedded font when it has the glyphs. Redaction removes the content, not just a
> box over it. Everything runs offline; the only network call is an optional update check.
>
> Honest gaps: not code-signed yet (a SignPath application was declined for being too new),
> the installed size is about 440 MB (Qt, Python and the optional OCR/Office/CAD exports), and
> it's 0.9x: I use it daily, but check your output.
>
> https://github.com/keithlyding/KanzonasPDF
>
> I'd value feedback from anyone who has built on MuPDF or shipped a Qt desktop app, and from
> anyone whose work lives in Bluebeam.

## Download sites (Softpedia, MajorGeeks, FileHorse, Download.com)

Each has a "submit software" form. A short description that fits them all:

> KanzonasPDF is a free, open-source PDF reader and editor for Windows, made for marking up
> and measuring drawings and plans: calibrated length, area, angle, radius, perimeter and
> volume measurements, counts, revision clouds, callouts, stamps and comments; compare two
> revisions; fill and create forms; sign with a drawn signature or a certificate; redact; OCR
> scanned pages; edit the page's own text and pictures; rotate, crop, combine and split pages;
> export to Word, Excel, PowerPoint, DXF and images. It starts in under a second, keeps big
> CAD sheets smooth, needs no account and sends nothing home. Available as an installer, a
> portable zip and a PortableApps.com package.

Fields they ask for: license GNU AGPL 3.0; price free; OS Windows 10/11 64-bit; size about
140 MB download; publisher KanzonasPDF; homepage and download URL on GitHub Releases.

## winget

The manifests for the current release are in `packaging/winget` and attached to every
release as `winget-manifests.zip`; see `packaging/winget/README.md` for how to submit them.
Once accepted, `winget install KanzonasPDF.KanzonasPDF` installs and updates it, and the
README can say so.
