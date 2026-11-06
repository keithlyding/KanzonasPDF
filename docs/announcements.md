# Telling people about KanzonasPDF

Drafts for the places where its users are. Post as a maker asking for feedback, not as an
advertiser; be plain about what it doesn't do yet. Keep comparisons to needs ("Bluebeam-style
measuring without the license"), not to other products' faults. Read each forum's
self-promotion rule before posting.

## GitHub repository topics

Settings (gear icon next to About on the repository page) > Topics:

    pdf pdf-editor pdf-viewer pdf-annotation pdf-forms ocr redaction acrobat-alternative
    windows linux portable open-source python pyside6 pymupdf markup measurement
    bluebeam-alternative

## AlternativeTo

KanzonasPDF is first a general PDF viewer and editor and a free alternative to Acrobat; the
measuring and CAD tools are extras. Lead with that. Fields as AlternativeTo's form asks them:

**Name:** KanzonasPDF

**Short description:**

> Free, open-source PDF viewer and editor for Windows and Linux. Comment and mark up, edit a
> PDF's own text, fill in and sign forms, OCR, redact and organize pages, with no account,
> subscription or watermarks.

**Description:**

> KanzonasPDF is a free, open-source PDF viewer and editor for Windows and Linux, made as a
> free alternative to Adobe Acrobat Pro and PDF-XChange Editor. Every feature is free, with no
> watermarks, no account, no subscription and no telemetry.
>
> - Read: tabs, thumbnails, bookmarks, fast search with every match highlighted, split view,
>   light and dark themes.
> - Comment and mark up: highlights, sticky notes, text boxes, callouts, shapes, clouds,
>   stamps, a tool chest of saved styles, and a markups list you can filter and export.
>   Markups are standard PDF annotations, so other PDF apps see them.
> - Edit the PDF itself: change its text in place (paragraphs rewrap as you type), find and
>   replace, move, resize or delete pictures and shapes, add text, pictures, watermarks,
>   headers, footers and page numbers.
> - Forms and signing: fill in and create forms, place your signature and initials, and sign
>   digitally with a certificate.
> - Protect and clean up: passwords and permissions, redaction that also scrubs hidden data,
>   and offline OCR that makes scans searchable.
> - Pages and conversion: rotate, reorder, insert, extract, crop and combine; compare two
>   versions of a document; export to Word, Excel and PowerPoint.
> - Print with a preview, plus print-shop tools (trim and bleed boxes, crop marks, a check for
>   common printing problems).
> - For drawings and plans: calibrated measuring of lengths, areas and volumes, and, as a fun
>   extra, AutoCAD-style editing tools.
>
> It starts in well under a second, runs from a USB stick (portable zip or PortableApps.com) or
> installs without administrator rights, and is available in English and Spanish. Open source
> under the AGPL-3.0.

**License:** Free, Open Source (AGPL-3.0)

**Platforms:** Windows, Linux (AppImage), PortableApps.com. (Mac: after it's released.)

**Website:** https://pdf.kanzonas.com · **Source code:** https://github.com/keithlyding/KanzonasPDF

**Linux note:** 64-bit x86 AppImage; needs glibc 2.35 or later (e.g. Ubuntu 22.04, Debian 12,
Fedora 36 or newer)

**Windows note:** Requires 64-bit Windows 10 or later

**Alternative to:** Adobe Acrobat, PDF-XChange Editor, Foxit PDF Editor, Nitro PDF Pro,
Master PDF Editor, Bluebeam Revu.

**Features (tags):** Ad-free, No registration required, Privacy focused, Works offline,
Portable, Lightweight, Dark mode, Tabbed interface, PDF annotation, Edit PDF text, Fill PDF
forms, Create PDF forms, Digital signature, OCR, Redact PDFs, Merge PDF files, Compare PDF
files, Password protection, Multilingual.

**Screenshots** (in this order; captions to paste):
1. `docs/screenshot-markup.png`: Reviewing a catalog: highlights, a cloud and callout, a
   sticky note and a stamp, with the markups list.
2. `docs/screenshot-edit-text.png`: Editing a paragraph of the PDF's own text; the words rewrap
   as you type.
3. `docs/screenshot-forms.png`: Filling in and signing an order form.
4. `docs/screenshot-dark.png`: The dark theme.
5. `docs/screenshot-measure.png`: Measuring a floor plan to scale.

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
