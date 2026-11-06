# Notices

KanzonasPDF is free software under the GNU AGPL-3.0 (see LICENSE). It is built on the
libraries below (the exact versions and their licenses are in `constraints.txt`):

- PyMuPDF and MuPDF (Artifex), AGPL-3.0 - the PDF engine - https://github.com/pymupdf/PyMuPDF
- Qt for Python (PySide6), LGPL-3.0 - https://www.qt.io/qt-for-python
- RapidOCR (rapidocr_onnxruntime), Apache-2.0, with ONNX Runtime (MIT) and OpenCV (Apache-2.0) -
  text recognition (OCR)
- pdf2docx, python-docx, openpyxl, python-pptx, MIT - exports to Word, Excel and PowerPoint
- ezdxf, MIT - DXF import and export
- pyHanko and pyhanko-certvalidator, MIT - digital signatures
- aiohttp, Apache-2.0 and MIT
- pyspellchecker, MIT - spell checking
- comtypes, MIT - Windows only: scanning through WIA (Windows Image Acquisition)
- QtAwesome, MIT, for its copy of the Material Design Icons font (Apache-2.0) - toolbar icons

What PDF/A copies carry (File > Save as PDF/A): nothing is bundled for it; the copies get
resources built into MuPDF, the same ones KanzonasPDF draws with:

- Artifex's sRGB ICC profile (the output intent) and Artifex's CMYK SWOP ICC profile (for CMYK
  colors), Copyright Artifex Software, part of MuPDF (AGPL-3.0).
- The URW base-35 fonts (Nimbus Sans, Nimbus Roman, Nimbus Mono PS, Standard Symbols PS,
  D050000L), Copyright URW++, part of MuPDF under the AGPL-3.0 with a font exception that lets
  documents embed them: embedded in place of the standard 14 fonts (Helvetica, Times, Courier,
  Symbol, ZapfDingbats) when a document uses them without embedding them.

Scanning (File > Scan): eSCL (AirScan), WSD (WS-Discovery, WS-Scan and WS-Eventing) and
multicast DNS are spoken with Python's standard library, WIA through comtypes (above) and SANE
through the `scanimage` command. It was written from the published eSCL and Microsoft
WS-Scan schemas; sane-airscan (https://github.com/alexpevzner/sane-airscan, GPL-2.0 with an
exception) was read as a reference for how real devices behave. No code was taken from it.

Artwork and type:

- The app icon, logo and their cactus and sunflower are the owner's artwork (`assets/`).
- The logo's lettering is set in Roboto Condensed ("Kanzonas"), Saira Condensed ("PDF") and
  Inter (the tagline), all under the SIL Open Font License 1.1 (Google Fonts). The logos are made
  in the Kanzonas-Site repository's `brand/` folder (https://github.com/keithlyding/Kanzonas-Site), the single
  source of truth for every Kanzonas logo. The icon's
  "PDF" tag is set in Inter Black (SIL OFL 1.1).

Shared with KanzonasCAD (https://github.com/keithlyding/KanzonasCAD, MIT, same owner): its
ribbon and theme started here.
