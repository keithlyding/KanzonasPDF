"""Document > Background: a solid color, a gradient or a picture behind the page content
(like Acrobat's Edit PDF > Background), on chosen pages, at any opacity.

The background is drawn on a one-page scratch PDF the size of the page as displayed, then
placed behind everything with show_pdf_page(overlay=False), which puts it in its own content
stream at the start of the page. That stream is marked as a background artifact (so text
extraction and screen readers skip it) and remembered in the page dictionary (/KZBackground),
so Background can later replace or remove exactly what it added.

A scanned page is one picture covering the whole page, so a background can't show through
it.
"""

import pymupdf

KEY = "KZBackground"
KINDS = ("color", "gradient", "image")
DIRECTIONS = {"down": "Top to bottom", "right": "Left to right",
              "diagonal": "Top left to bottom right", "up": "Bottom to top"}
FITS = {"fit": "Fit (whole picture visible)", "fill": "Fill (cover the page, trim the edges)",
        "stretch": "Stretch to the page", "center": "Center at its own size"}


def _rgb(hexcolor):
    h = (hexcolor or "#ffffff").lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def _scratch(w, h, spec):
    """A w x h one-page PDF with the background drawn on it."""
    doc = pymupdf.open()
    page = doc.new_page(width=w, height=h)
    kind = spec["kind"]
    if kind == "color":
        page.draw_rect(page.rect, color=None, fill=_rgb(spec.get("color")), width=0)
    elif kind == "gradient":
        c0, c1 = _rgb(spec.get("color")), _rgb(spec.get("color2"))
        coords = {"down": (0, h, 0, 0), "up": (0, 0, 0, h), "right": (0, 0, w, 0),
                  "diagonal": (0, h, w, 0)}[spec.get("direction", "down")]
        sh = doc.get_new_xref()
        doc.update_object(sh, (
            "<< /ShadingType 2 /ColorSpace /DeviceRGB /Coords [%s] /Extend [true true] "
            "/Function << /FunctionType 2 /Domain [0 1] /C0 [%s] /C1 [%s] /N 1 >> >>"
            % (" ".join(f"{v:.3f}" for v in coords), " ".join(f"{v:.4f}" for v in c0),
               " ".join(f"{v:.4f}" for v in c1))))
        page.clean_contents()
        doc.xref_set_key(page.xref, "Resources/Shading", f"<< /KZsh {sh} 0 R >>")
        cx = doc.get_new_xref()
        doc.update_object(cx, "<<>>")
        doc.update_stream(cx, b"q /KZsh sh Q")
        page.set_contents(cx)
    elif kind == "image":
        pm = pymupdf.Pixmap(spec["image"])
        if pm.colorspace and pm.colorspace.n == 4:
            pm = pymupdf.Pixmap(pymupdf.csRGB, pm)
        iw, ih = pm.width, pm.height
        fit = spec.get("fit", "fit")
        if fit == "stretch":
            r = page.rect
        elif fit == "center":
            iw_pt, ih_pt = iw * 72 / 96, ih * 72 / 96          # its own size at 96 dpi
            r = pymupdf.Rect(w / 2 - iw_pt / 2, h / 2 - ih_pt / 2,
                             w / 2 + iw_pt / 2, h / 2 + ih_pt / 2)
        else:
            s = (min if fit == "fit" else max)(w / iw, h / ih)
            r = pymupdf.Rect(w / 2 - iw * s / 2, h / 2 - ih * s / 2,
                             w / 2 + iw * s / 2, h / 2 + ih * s / 2)
        page.insert_image(r, pixmap=pm, keep_proportion=False)
    else:
        raise ValueError("Unknown background type " + str(kind))
    opacity = float(spec.get("opacity", 1.0))
    if opacity < 0.999:
        page.clean_contents()
        doc.xref_set_key(page.xref, "Resources/ExtGState/KZa",
                         f"<< /ca {opacity:.3f} /CA {opacity:.3f} >>")
        x = page.get_contents()[0]
        doc.update_stream(x, b"q /KZa gs\n" + doc.xref_stream(x) + b"\nQ")
    return doc


def has_background(page):
    try:
        typ, val = page.parent.xref_get_key(page.xref, KEY)
        return typ == "int"
    except Exception:
        return False


def remove(page):
    """Remove the background Background added to this page, if any. True if removed."""
    doc = page.parent
    typ, val = doc.xref_get_key(page.xref, KEY)
    if typ != "int":
        return False
    x = int(val)
    contents = [c for c in page.get_contents() if c != x]
    data = doc.xref_stream(x) or b""
    if contents:
        doc.xref_set_key(page.xref, "Contents", "[" + " ".join(f"{c} 0 R" for c in contents) + "]")
    else:
        doc.xref_set_key(page.xref, "Contents", "null")
    # drop the form it drew from the page's resources too
    import re
    for name in re.findall(rb"/(fzFrm\d+)\s+Do", data):
        try:
            doc.xref_set_key(page.xref, "Resources/XObject/" + name.decode(), "null")
        except Exception:
            pass
    doc.xref_set_key(page.xref, KEY, "null")
    return True


def apply(doc, pages, spec):
    """Put the background on pages (indices), replacing one Background added before."""
    cache = {}
    for i in pages:
        page = doc[i]
        remove(page)
        page = doc[i]
        disp = page.rect                               # as displayed
        key = (round(disp.width, 2), round(disp.height, 2))
        if key not in cache:
            cache[key] = _scratch(disp.width, disp.height, spec)
        rot = page.rotation
        page.show_pdf_page(disp * page.derotation_matrix, cache[key], 0, overlay=False,
                           rotate=rot if rot <= 180 else rot - 360)
        x = page.get_contents()[0]
        doc.update_stream(x, b"/Artifact << /Type /Pagination /Subtype /Background >> BDC\n"
                          + (doc.xref_stream(x) or b"") + b"\nEMC\n")
        doc.xref_set_key(page.xref, KEY, str(x))
    for d in cache.values():
        d.close()


def remove_pages(doc, pages):
    n = 0
    for i in pages:
        if remove(doc[i]):
            n += 1
    return n
