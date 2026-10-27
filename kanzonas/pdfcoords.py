"""Page coordinates <-> PDF user space.

KanzonasPDF works in PyMuPDF's unrotated page coordinates (annot.rect, get_text,
get_drawings: origin at the top-left of the CropBox, y down). What is written into a /Rect
or a content stream is PDF user space (y up, with the MediaBox / CropBox offsets).

PyMuPDF's page.transformation_matrix (PDF -> page) leaves out the CropBox offset on a
rotated page, so on a page that is both rotated and cropped (a plotted sheet after Crop
pages) everything placed through it landed elsewhere: PyMuPDF's own draw_*, insert_image,
show_pdf_page and insert_link use it too. Importing this module (kanzonas/__init__ does)
gives PyMuPDF the right matrix, the one MuPDF itself draws the page with."""

import pymupdf

_PYMUPDF_MATRIX = pymupdf.Page.transformation_matrix


def to_page(page):
    """Matrix from PDF user space to unrotated page coordinates."""
    if not page.parent.is_pdf:
        return pymupdf.Matrix(_PYMUPDF_MATRIX.fget(page))
    mu = pymupdf.mupdf
    ctm = mu.FzMatrix()
    mu.pdf_page_transform(mu.pdf_page_from_fz_page(page.this), mu.FzRect(mu.FzRect.Fixed_UNIT), ctm)
    # MuPDF's matrix maps to the page as displayed (rotated): turn it back
    return pymupdf.Matrix(ctm.a, ctm.b, ctm.c, ctm.d, ctm.e, ctm.f) * page.derotation_matrix


def to_pdf(page):
    """Matrix from unrotated page coordinates to PDF user space."""
    return ~to_page(page)


pymupdf.Page.transformation_matrix = property(to_page, doc=_PYMUPDF_MATRIX.__doc__)
