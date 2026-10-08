"""Capture area with vector content: the captured area is kept as PDF drawing (lines, text,
markups) and pasted as an image markup whose picture is that drawing, so it stays sharp at
any zoom and in print. A PNG of the area is also put on the clipboard for other programs."""

import pymupdf


def snapshot(page, area):
    """One-page PDF (bytes) of `page` as displayed, markups baked in, and the PDF-space box
    of `area` (a displayed-page rect) on it."""
    doc = page.parent
    tmp = pymupdf.open()
    try:
        tmp.insert_pdf(doc, from_page=page.number, to_page=page.number, annots=True,
                       widgets=True)
        tmp.bake()                       # markups and form fields become page drawing
        tp = tmp[0]
        tp.remove_rotation()             # the page now shows as displayed, unrotated
        _remove_outside(tp, pymupdf.Rect(area) & tp.rect)
        box = (pymupdf.Rect(area) * ~tp.transformation_matrix).normalize()
        return tmp.tobytes(garbage=3, deflate=True), list(box)
    finally:
        tmp.close()


def _remove_outside(page, keep):
    """Delete what lies outside `keep`, so the pasted copy doesn't carry the rest of the page
    hidden in the file: text and image pixels outside, and lines entirely outside. A line
    crossing the edge stays whole (the box clips it from view); so does a character only
    partly inside, which is removed."""
    r = page.rect
    strips = [pymupdf.Rect(r.x0, r.y0, r.x1, keep.y0), pymupdf.Rect(r.x0, keep.y1, r.x1, r.y1),
              pymupdf.Rect(r.x0, r.y0, keep.x0, r.y1), pymupdf.Rect(keep.x1, r.y0, r.x1, r.y1)]
    hit = False
    for s in strips:
        if s.width > 0 and s.height > 0:
            page.add_redact_annot(s, fill=False)
            hit = True
    if hit:
        page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_PIXELS,
                              graphics=pymupdf.PDF_REDACT_LINE_ART_REMOVE_IF_COVERED,
                              text=pymupdf.PDF_REDACT_TEXT_REMOVE)


def make_form(doc, data, box):
    """Put the snapshot into `doc` as a Form XObject scaled to the unit square (like an
    image), clipped to `box`. Returns its xref."""
    src = pymupdf.open("pdf", data)
    try:
        scratch = doc.new_page(width=10, height=10)
        try:
            inner = scratch.show_pdf_page(scratch.rect, src, 0)   # the whole page as a form
        finally:
            doc.delete_page(scratch.number)
    finally:
        src.close()
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    xref = doc.get_new_xref()
    doc.update_object(xref, (
        f"<< /Type /XObject /Subtype /Form /BBox [{x0:.4f} {y0:.4f} {x1:.4f} {y1:.4f}] "
        f"/Matrix [{1 / w:.8f} 0 0 {1 / h:.8f} {-x0 / w:.8f} {-y0 / h:.8f}] "
        f"/Resources << /XObject << /P {inner} 0 R >> >> >>"))
    doc.update_stream(xref, b"/P Do")
    return xref


def is_form(doc, xref):
    try:
        return doc.xref_get_key(int(xref), "Subtype")[1] == "/Form"
    except Exception:
        return False
