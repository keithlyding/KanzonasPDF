"""Markups outside a page (issue #82): how far they reach past each side of the page, as the
page is shown, read straight from the file (the page's /Annots and each markup's /Rect)
without loading the page: a document is laid out from this when it's opened, so it has to be
quick on thousands of pages, most with no markups at all.

Pop-ups (a note's window, which other programs often leave beside the page) and links don't
count, nor hidden markups."""

import pymupdf

_SKIP = {"Popup", "Link"}
_HIDDEN = 2                          # the annotation flag Hidden (PDF 12.5.3)


def _rect(m, obj):
    if not m.pdf_is_array(obj) or m.pdf_array_len(obj) != 4:
        return None
    x0, y0, x1, y1 = (m.pdf_to_real(m.pdf_array_get(obj, k)) for k in range(4))
    return min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)


def page_outside_margins(doc, index):
    """(left, top, right, bottom): how far, in points, the page's markups reach past each of
    its sides as it's shown (its crop box, turned by its /Rotate); 0 where none does."""
    none = (0.0, 0.0, 0.0, 0.0)
    if not doc.is_pdf:
        return none
    m = pymupdf.mupdf
    pdf = pymupdf._as_pdf_document(doc)
    page = m.pdf_lookup_page_obj(pdf, index)
    annots = m.pdf_dict_get(page, m.PDF_ENUM_NAME_Annots)
    if not m.pdf_is_array(annots) or not m.pdf_array_len(annots):
        return none
    media = _rect(m, m.pdf_dict_get_inheritable(page, m.PDF_ENUM_NAME_MediaBox))
    crop = _rect(m, m.pdf_dict_get_inheritable(page, m.PDF_ENUM_NAME_CropBox))
    box = crop or media
    if box is None:
        return none
    if media is not None and crop is not None:      # (MuPDF shows the crop within the media)
        box = (max(crop[0], media[0]), max(crop[1], media[1]),
               min(crop[2], media[2]), min(crop[3], media[3]))
    left = bottom = right = top = 0.0               # in PDF space: y up
    for k in range(m.pdf_array_len(annots)):
        a = m.pdf_array_get(annots, k)
        if not m.pdf_is_dict(a):
            continue
        sub = m.pdf_dict_get(a, m.PDF_ENUM_NAME_Subtype)
        if m.pdf_is_name(sub) and m.pdf_to_name(sub) in _SKIP:
            continue
        if m.pdf_to_int(m.pdf_dict_get(a, m.PDF_ENUM_NAME_F)) & _HIDDEN:
            continue
        r = _rect(m, m.pdf_dict_get(a, m.PDF_ENUM_NAME_Rect))
        if r is None or not all(abs(c) < 1e7 for c in r):
            continue
        left = max(left, box[0] - r[0])
        bottom = max(bottom, box[1] - r[1])
        right = max(right, r[2] - box[2])
        top = max(top, r[3] - box[3])
    rot = m.pdf_to_int(m.pdf_dict_get_inheritable(page, m.PDF_ENUM_NAME_Rotate)) % 360
    rot = rot - rot % 90
    # the PDF's sides as the page is shown, turned clockwise by /Rotate
    if rot == 90:
        return bottom, left, top, right
    if rot == 180:
        return right, bottom, left, top
    if rot == 270:
        return top, right, bottom, left
    return left, top, right, bottom
