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
- QtAwesome, MIT, for its copy of the Material Design Icons font (Apache-2.0) - toolbar icons

Artwork and type:

- The app icon, logo and their cactus and sunflower are the owner's artwork (`assets/`).
- The logo's lettering is set in Roboto Condensed ("Kanzonas"), Saira Condensed ("PDF") and
  Inter (the tagline), all under the SIL Open Font License 1.1 (Google Fonts). The logo is made
  by KanzonasCAD's `tools/make_logos.py`, which makes both apps' logos so they match. The icon's
  "PDF" tag is set in Inter Black (SIL OFL 1.1).

Shared with KanzonasCAD (https://github.com/keithlyding/KanzonasCAD, MIT, same owner): its
ribbon and theme started here, and its logo script makes this app's logo.
