"""KanzonasPDF: a free, fast PDF reader and editor."""

__version__ = "1.6.2"

# PyMuPDF 2.0 imports its optional layout-analysis package at import time, and that package
# imports onnxruntime (a 100 MB AI runtime, also shipped here for OCR) as soon as it is
# available: start-up would pay for it on every launch although KanzonasPDF never uses the
# layout analyzer. Hiding onnxruntime while PyMuPDF imports makes that optional import fail
# quietly (PyMuPDF catches it); OCR imports onnxruntime itself later, when it is used.
import os as _os
import sys as _sys

_os.environ.setdefault("PYMUPDF_SUGGEST_LAYOUT_ANALYZER", "0")   # no "install the layout package" hint
if "onnxruntime" not in _sys.modules:
    _sys.modules["onnxruntime"] = None          # makes "import onnxruntime" raise ImportError
    try:
        import pymupdf  # noqa: F401,E402
    finally:
        del _sys.modules["onnxruntime"]
del _sys, _os

from . import pdfcoords as _pdfcoords  # noqa: E402,F401  (gives PyMuPDF the right page matrix)
