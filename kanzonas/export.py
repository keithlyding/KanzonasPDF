"""Export a PDF to other formats.

Word        pdf2docx (MIT): rebuilds paragraphs, tables and images as an editable .docx.
Excel       PyMuPDF table detection -> openpyxl (MIT); one sheet per table found.
PowerPoint  python-pptx (MIT): one slide per page, page as a picture (looks identical,
            not editable as text) with the page text in the speaker notes.
AutoCAD     ezdxf (MIT): vector lines, curves, rectangles and text as real DXF entities.
Images      PNG / JPEG per page. Text: plain .txt.

Every function takes the PDF as bytes (a snapshot of the open document, including
unsaved changes) so it can run in a worker thread without touching the GUI's document.
"""

import math
import os
import tempfile

import pymupdf

UNITS = {"inches": 1 / 72, "millimeters": 25.4 / 72, "PDF points (1:1)": 1.0}
_DXF_UNITS = {"inches": 1, "millimeters": 4, "PDF points (1:1)": 0}


def _pages(doc, pages):
    return range(doc.page_count) if pages is None else pages


def to_word(pdf_bytes, out_path, pages=None, progress=None):
    from pdf2docx import Converter
    fd, tmp = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    try:
        with open(tmp, "wb") as f:
            f.write(pdf_bytes)
        cv = Converter(tmp)
        try:
            cv.convert(out_path, pages=list(pages) if pages is not None else None)
        finally:
            cv.close()
    finally:
        os.remove(tmp)
    return out_path


def to_excel(pdf_bytes, out_path, pages=None, progress=None):
    """Tables found on the pages -> one worksheet each. Pages without detected tables
    get a sheet with their text lines (one per row, split into cells at large gaps)."""
    from openpyxl import Workbook
    from openpyxl.utils import get_column_letter
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    wb = Workbook()
    wb.remove(wb.active)
    tables_found = 0

    def append_text(ws, values):
        ws.append(values)
        for cell in ws[ws.max_row]:
            if isinstance(cell.value, str):
                cell.data_type = "s"  # PDF content is text, never a formula.
    for i in _pages(doc, pages):
        if progress:
            progress(i)
        page = doc[i]
        try:
            tabs = page.find_tables().tables
        except Exception:
            tabs = []
        for k, t in enumerate(tabs, 1):
            ws = wb.create_sheet(f"P{i + 1} table {k}"[:31])
            for row in t.extract():
                append_text(ws, [("" if c is None else str(c)) for c in row])
            tables_found += 1
        if not tabs:
            ws = wb.create_sheet(f"P{i + 1} text"[:31])
            for row in _text_rows(page):
                append_text(ws, row)
    for ws in wb.worksheets:
        for col in ws.columns:
            width = max((len(str(c.value)) for c in col if c.value is not None), default=8)
            ws.column_dimensions[get_column_letter(col[0].column)].width = min(60, width + 2)
    if not wb.worksheets:
        wb.create_sheet("Empty")
    wb.save(out_path)
    doc.close()
    return tables_found


def _text_rows(page):
    """Lines of words, split into cells where the horizontal gap is large."""
    words = page.get_text("words", sort=True)
    rows, cur, cur_y = [], [], None
    for w in words:
        yc = (w[1] + w[3]) / 2
        if cur_y is None or abs(yc - cur_y) > (w[3] - w[1]) * 0.6:
            if cur:
                rows.append(cur)
            cur, cur_y = [], yc
        cur.append(w)
    if cur:
        rows.append(cur)
    out = []
    for row in rows:
        row.sort(key=lambda w: w[0])
        cells, text, last_x1 = [], "", None
        for w in row:
            gap = 0 if last_x1 is None else w[0] - last_x1
            if last_x1 is not None and gap > 2.5 * (w[3] - w[1]):
                cells.append(text)
                text = w[4]
            else:
                text = (text + " " + w[4]) if text else w[4]
            last_x1 = w[2]
        cells.append(text)
        out.append(cells)
    return out


def to_powerpoint(pdf_bytes, out_path, pages=None, progress=None, dpi=200):
    from pptx import Presentation
    from pptx.util import Emu
    import io
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    prs = Presentation()
    first = doc[0].rect
    emu_per_pt = 12700
    prs.slide_width = Emu(int(first.width * emu_per_pt))
    prs.slide_height = Emu(int(first.height * emu_per_pt))
    blank = prs.slide_layouts[6]
    for i in _pages(doc, pages):
        if progress:
            progress(i)
        page = doc[i]
        pm = page.get_pixmap(dpi=dpi, annots=True)
        slide = prs.slides.add_slide(blank)
        # fit the page inside the slide (pages can differ in size)
        sw, sh = prs.slide_width, prs.slide_height
        scale = min(sw / (page.rect.width * emu_per_pt), sh / (page.rect.height * emu_per_pt))
        w, h = int(page.rect.width * emu_per_pt * scale), int(page.rect.height * emu_per_pt * scale)
        slide.shapes.add_picture(io.BytesIO(pm.tobytes("png")), (sw - w) // 2, (sh - h) // 2, w, h)
        text = page.get_text().strip()
        if text:
            slide.notes_slide.notes_text_frame.text = text
    prs.save(out_path)
    doc.close()
    return out_path


def to_dxf(pdf_bytes, out_path, pages=None, units="inches", progress=None):
    """Vector content -> DXF. Each page is placed side by side (with a gap) in model space,
    as it appears on screen (page rotation applied), Y axis pointing up as CAD expects."""
    import ezdxf
    from ezdxf.enums import TextEntityAlignment
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    dxf = ezdxf.new("R2010", setup=True)
    dxf.units = _DXF_UNITS[units]
    msp = dxf.modelspace()
    k = UNITS[units]
    x_offset = 0.0
    counts = {"lines": 0, "curves": 0, "text": 0}
    for i in _pages(doc, pages):
        if progress:
            progress(i)
        page = doc[i]
        m = page.rotation_matrix
        height = page.rect.height                    # displayed height

        def P(pt):
            q = pymupdf.Point(pt) * m
            return ((q.x + x_offset) * k, (height - q.y) * k)

        layer = f"PAGE_{i + 1}"
        dxf.layers.add(layer)
        for path in page.get_drawings():
            color = path.get("color") or path.get("fill") or (0, 0, 0)
            attribs = {"layer": layer,
                       "true_color": ezdxf.rgb2int(tuple(int(c * 255) for c in color[:3]))}
            for item in path["items"]:
                op = item[0]
                if op == "l":
                    msp.add_line(P(item[1]), P(item[2]), dxfattribs=attribs)
                    counts["lines"] += 1
                elif op == "re":
                    r = item[1]
                    pts = [P(r.tl), P(r.tr), P(r.br), P(r.bl)]
                    msp.add_lwpolyline(pts, close=True, dxfattribs=attribs)
                    counts["lines"] += 1
                elif op == "qu":
                    q = item[1]
                    msp.add_lwpolyline([P(q.ul), P(q.ur), P(q.lr), P(q.ll)], close=True,
                                       dxfattribs=attribs)
                    counts["lines"] += 1
                elif op == "c":
                    # cubic Bezier -> polyline with 12 segments (exact enough for drawings)
                    p0, p1, p2, p3 = (pymupdf.Point(v) for v in item[1:5])
                    pts = []
                    for s in range(13):
                        t = s / 12
                        a = (1 - t) ** 3
                        b = 3 * (1 - t) ** 2 * t
                        c = 3 * (1 - t) * t ** 2
                        d = t ** 3
                        pts.append(P(p0 * a + p1 * b + p2 * c + p3 * d))
                    msp.add_lwpolyline(pts, dxfattribs=attribs)
                    counts["curves"] += 1
        td = page.get_text("dict", flags=pymupdf.TEXTFLAGS_DICT & ~pymupdf.TEXT_PRESERVE_IMAGES)
        for b in td["blocks"]:
            if b.get("type") != 0:
                continue
            for line in b["lines"]:
                dx, dy = line["dir"]
                for s in line["spans"]:
                    if not s["text"].strip():
                        continue
                    # direction on screen (apply page rotation), then flip y for CAD
                    v = pymupdf.Point(dx, dy) * pymupdf.Matrix(m.a, m.b, m.c, m.d, 0, 0)
                    angle = math.degrees(math.atan2(-v.y, v.x))
                    c = s["color"]
                    t = msp.add_text(s["text"], height=s["size"] * 0.72 * k, rotation=angle,
                                     dxfattribs={"layer": layer, "true_color": c})
                    t.set_placement(P(s["origin"]), align=TextEntityAlignment.LEFT)
                    counts["text"] += 1
        x_offset += page.rect.width + 36
    dxf.saveas(out_path)
    doc.close()
    return counts


def to_images(pdf_bytes, out_base, fmt="png", dpi=200, pages=None, progress=None):
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    paths = []
    for i in _pages(doc, pages):
        if progress:
            progress(i)
        pm = doc[i].get_pixmap(dpi=dpi, annots=True)
        path = f"{out_base}_p{i + 1}.{fmt}"
        if fmt in ("jpg", "jpeg"):
            pm.save(path, jpg_quality=90)
        else:
            pm.save(path)
        paths.append(path)
    doc.close()
    return paths


def to_text(pdf_bytes, out_path, pages=None, progress=None):
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    with open(out_path, "w", encoding="utf-8") as f:
        for i in _pages(doc, pages):
            if progress:
                progress(i)
            f.write(f"===== Page {i + 1} =====\n")
            f.write(doc[i].get_text(sort=True))
            f.write("\n")
    doc.close()
    return out_path
