"""Generate realistic plotted-CAD PDFs for testing KanzonasPDF.

    python tests/cad_samples.py OUTPUT_DIR

Creates:
  floorplan_A.pdf      ARCH D (36x24") architectural plan at 1/4" = 1'-0": walls, hatching,
                       doors with swings, grid bubbles, dimension strings, ~600 furniture
                       blocks, title block. Real (TrueType-style) text.
  floorplan_B.pdf      Revision B of the same plan (moved wall, new door, deleted furniture,
                       changed title block) for Compare.
  floorplan_rotated.pdf  Same sheet plotted portrait with /Rotate 90 (very common for plots).
  dxf_plot.pdf         A drawing built in ezdxf and plotted by its PDF backend: text becomes
                       vector outlines (like SHX fonts) so there is no selectable text.
  siteplan_heavy.pdf   ARCH E1 (42x30") civil site plan: ~150,000 contour segments, rotated
                       elevation labels, a large aerial-photo raster underlay and optional
                       content layers (OCGs).
  scanned_plan.pdf     The floor plan as a 200 dpi raster only (a scanned/plotted image).
"""

import math
import os
import random
import sys

import pymupdf

IN = 72.0                      # points per inch
SCALE = 48                     # 1/4" = 1'-0"  -> 1 ft = 0.25 in = 18 pt
FT = IN / SCALE * 12           # points per real foot


def _title_block(page, title, rev, sheet="A-101"):
    r = page.rect
    tb = pymupdf.Rect(r.x1 - 5.5 * IN, r.y1 - 2.6 * IN, r.x1 - 0.5 * IN, r.y1 - 0.5 * IN)
    page.draw_rect(pymupdf.Rect(0.5 * IN, 0.5 * IN, r.x1 - 0.5 * IN, r.y1 - 0.5 * IN), width=2)
    page.draw_rect(tb, width=1.5)
    for k in range(1, 5):
        y = tb.y0 + k * tb.height / 5
        page.draw_line((tb.x0, y), (tb.x1, y), width=0.5)
    rows = [("PROJECT", "KANZONAS WAREHOUSE FIT-OUT"), ("SHEET TITLE", title),
            ("SCALE", '1/4" = 1\'-0"'), ("DRAWN BY", "KL      CHECKED: JS"),
            ("SHEET / REV", f"{sheet}     REV {rev}")]
    for k, (lab, val) in enumerate(rows):
        y = tb.y0 + k * tb.height / 5
        page.insert_text((tb.x0 + 6, y + 11), lab, fontsize=6, fontname="helv", color=(0.3, 0.3, 0.3))
        page.insert_text((tb.x0 + 6, y + 24), val, fontsize=10, fontname="hebo")


def _hatch(page, rect, spacing=6, angle=45):
    """ANSI31-style diagonal hatch clipped to rect, as individual line segments."""
    shape = page.new_shape()
    d = rect.width + rect.height
    t = math.tan(math.radians(angle))
    x = rect.x0 - rect.height
    while x < rect.x1:
        # line y = rect.y1 - (X - x) * t  clipped to the rect
        p0 = pymupdf.Point(x, rect.y1)
        p1 = pymupdf.Point(x + rect.height / t, rect.y0)
        a, b = p0, p1
        if a.x < rect.x0:
            a = pymupdf.Point(rect.x0, rect.y1 - (rect.x0 - x) * t)
        if b.x > rect.x1:
            b = pymupdf.Point(rect.x1, rect.y1 - (rect.x1 - x) * t)
        if a.x < b.x:
            shape.draw_line(a, b)
        x += spacing
    shape.finish(color=(0.45, 0.45, 0.45), width=0.25)
    shape.commit()


def _bubble(page, c, label):
    page.draw_circle(c, 14, width=0.8)
    page.insert_text((c.x - 4 * len(label), c.y + 5), label, fontsize=12, fontname="helv")


def _dimension(page, a, b, offset, text):
    """Horizontal/vertical dimension string with ticks and the value."""
    horiz = abs(b.y - a.y) < 1
    if horiz:
        y = a.y + offset
        page.draw_line((a.x, a.y), (a.x, y + 4), width=0.3)
        page.draw_line((b.x, b.y), (b.x, y + 4), width=0.3)
        page.draw_line((a.x, y), (b.x, y), width=0.4)
        for x in (a.x, b.x):
            page.draw_line((x - 3, y + 3), (x + 3, y - 3), width=0.8)
        page.insert_text(((a.x + b.x) / 2 - 3 * len(text), y - 3), text, fontsize=8, fontname="helv")
    else:
        x = a.x + offset
        page.draw_line((a.x, a.y), (x + 4, a.y), width=0.3)
        page.draw_line((b.x, b.y), (x + 4, b.y), width=0.3)
        page.draw_line((x, a.y), (x, b.y), width=0.4)
        for y in (a.y, b.y):
            page.draw_line((x - 3, y + 3), (x + 3, y - 3), width=0.8)
        page.insert_text((x - 3, (a.y + b.y) / 2 + 3 * len(text)), text, fontsize=8,
                         fontname="helv", rotate=90)


def _ftin(feet):
    ft = int(feet)
    inch = round((feet - ft) * 12)
    return f"{ft}'-{inch}\""


def floorplan(path, revision="A", rotated=False, seed=7):
    rnd = random.Random(seed)
    doc = pymupdf.open()
    W, H = 36 * IN, 24 * IN
    page = doc.new_page(width=W, height=H)
    ox, oy = 3 * IN, 3 * IN                       # building origin on the sheet
    bw, bh = 100 * FT, 60 * FT                    # 100' x 60' building
    wall = 0.67 * FT                              # 8" walls
    # exterior walls: double lines + hatch
    outer = pymupdf.Rect(ox, oy, ox + bw, oy + bh)
    inner = pymupdf.Rect(ox + wall, oy + wall, ox + bw - wall, oy + bh - wall)
    page.draw_rect(outer, width=1.2)
    page.draw_rect(inner, width=1.2)
    for strip in (pymupdf.Rect(outer.x0, outer.y0, outer.x1, inner.y0),
                  pymupdf.Rect(outer.x0, inner.y1, outer.x1, outer.y1),
                  pymupdf.Rect(outer.x0, inner.y0, inner.x0, inner.y1),
                  pymupdf.Rect(inner.x1, inner.y0, outer.x1, inner.y1)):
        _hatch(page, strip, spacing=3)
    # interior partitions (revision B moves one)
    xs = [30, 55, 80] if revision == "A" else [30, 60, 80]
    for xf in xs:
        x = ox + xf * FT
        page.draw_rect(pymupdf.Rect(x, inner.y0, x + 0.42 * FT, oy + 35 * FT), width=0.8)
    page.draw_rect(pymupdf.Rect(inner.x0, oy + 35 * FT, inner.x1, oy + 35.42 * FT), width=0.8)
    # doors with swings
    doors = [(15, 35), (42, 35), (67, 35), (90, 35)] + ([(50, 60)] if revision == "B" else [])
    for xf, yf in doors:
        x, y = ox + xf * FT, oy + yf * FT
        page.draw_line((x, y), (x, y - 3 * FT), width=0.6)
        shape = page.new_shape()
        shape.draw_sector((x, y), (x + 3 * FT, y), -90)
        shape.finish(color=(0, 0, 0), width=0.3, dashes="[2 2] 0", closePath=False)
        shape.commit()
    # column grid with bubbles
    for k, xf in enumerate(range(0, 101, 25)):
        x = ox + xf * FT
        page.draw_line((x, oy - 1.2 * IN), (x, oy + bh + 0.3 * IN), width=0.3, dashes="[12 3 2 3] 0")
        _bubble(page, pymupdf.Point(x, oy - 1.4 * IN), str(k + 1))
    for k, yf in enumerate(range(0, 61, 30)):
        y = oy + yf * FT
        page.draw_line((ox - 1.2 * IN, y), (ox + bw + 0.3 * IN, y), width=0.3, dashes="[12 3 2 3] 0")
        _bubble(page, pymupdf.Point(ox - 1.4 * IN, y), "ABC"[k])
    # dimensions
    for xa, xb in ((0, 25), (25, 50), (50, 75), (75, 100)):
        _dimension(page, pymupdf.Point(ox + xa * FT, oy), pymupdf.Point(ox + xb * FT, oy),
                   -0.6 * IN, _ftin(xb - xa))
    _dimension(page, pymupdf.Point(ox, oy), pymupdf.Point(ox + bw, oy), -0.9 * IN, "100'-0\"")
    _dimension(page, pymupdf.Point(ox + bw, oy), pymupdf.Point(ox + bw, oy + bh), 0.6 * IN, "60'-0\"")
    # room tags
    rooms = [("OFFICE 101", 15), ("CONFERENCE 102", 42), ("BREAK ROOM 103", 67), ("STORAGE 104", 90)]
    if revision == "B":
        rooms[1] = ("CONFERENCE 102A", 44)
    for name, xf in rooms:
        x, y = ox + xf * FT, oy + 15 * FT
        page.draw_rect(pymupdf.Rect(x - 40, y - 12, x + 40, y + 6), width=0.5)
        page.insert_text((x - 3 * len(name), y), name, fontsize=8, fontname="hebo")
    page.insert_text((ox + 40 * FT, oy + 48 * FT), "WAREHOUSE 105", fontsize=14, fontname="hebo")
    # racking / furniture blocks (many small repeated entities)
    count = 0
    for row in range(6):
        for col in range(26 if revision == "A" else 22):
            x = ox + 4 * FT + col * 3.6 * FT
            y = oy + 38 * FT + row * 3.4 * FT
            r = pymupdf.Rect(x, y, x + 3 * FT, y + 2.4 * FT)
            page.draw_rect(r, width=0.35)
            page.draw_line(r.tl, r.br, width=0.2)
            page.draw_line(r.tr, r.bl, width=0.2)
            count += 1
    for k in range(120):
        x = ox + rnd.uniform(3, 27) * FT
        y = oy + rnd.uniform(3, 30) * FT
        page.draw_circle((x, y), 0.9 * FT, width=0.3)              # chairs
    # north arrow + scale bar + notes
    na = pymupdf.Point(W - 3 * IN, 2.2 * IN)
    page.draw_polyline([na + (0, -30), na + (12, 12), na + (0, 4), na + (-12, 12), na + (0, -30)],
                       width=0.8, fill=(0, 0, 0))
    page.insert_text(na + (-4, 28), "N", fontsize=12, fontname="hebo")
    for k in range(5):
        x = 3 * IN + k * 10 * FT
        page.draw_rect(pymupdf.Rect(x, H - 2.0 * IN, x + 10 * FT, H - 1.9 * IN),
                       fill=(0, 0, 0) if k % 2 == 0 else None, width=0.5)
        page.insert_text((x - 3, H - 2.05 * IN), f"{k * 10}'", fontsize=7)
    notes = ["GENERAL NOTES:", "1. ALL DIMENSIONS ARE TO FACE OF STUD UNLESS NOTED OTHERWISE.",
             "2. CONTRACTOR TO VERIFY ALL DIMENSIONS IN FIELD.",
             "3. PROVIDE FIRE EXTINGUISHERS PER LOCAL CODE." + (" REV B." if revision == "B" else "")]
    for k, n in enumerate(notes):
        page.insert_text((W - 11 * IN, 4 * IN + k * 14), n, fontsize=8, fontname="helv")
    _title_block(page, "FIRST FLOOR PLAN", revision)
    if rotated:
        # re-plot portrait with /Rotate 90: content drawn on a portrait mediabox
        out = pymupdf.open()
        p2 = out.new_page(width=H, height=W)
        p2.show_pdf_page(p2.rect, doc, 0, rotate=-90)
        p2.set_rotation(90)
        out.save(path, garbage=3, deflate=True)
        return count
    doc.save(path, garbage=3, deflate=True)
    return count


def dxf_plot(path):
    """Build a DXF in ezdxf and plot it to PDF with ezdxf's renderer (text as outlines)."""
    import ezdxf
    from ezdxf.addons.drawing import Frontend, RenderContext, layout
    from ezdxf.addons.drawing.pymupdf import PyMuPdfBackend
    dxf = ezdxf.new("R2018", setup=True)
    msp = dxf.modelspace()
    for name, col in (("WALLS", 7), ("DOORS", 3), ("DIMS", 1), ("TEXT", 5), ("HATCH", 8)):
        dxf.layers.add(name, color=col)
    msp.add_lwpolyline([(0, 0), (1200, 0), (1200, 720), (0, 720)], close=True,
                       dxfattribs={"layer": "WALLS", "const_width": 8})
    for x in (300, 600, 900):
        msp.add_line((x, 0), (x, 420), dxfattribs={"layer": "WALLS"})
        msp.add_arc((x + 4, 420), 36, 0, 90, dxfattribs={"layer": "DOORS"})
    hatch = msp.add_hatch(color=8, dxfattribs={"layer": "HATCH"})
    hatch.set_pattern_fill("ANSI31", scale=8)
    hatch.paths.add_polyline_path([(0, 600), (300, 600), (300, 720), (0, 720)], is_closed=True)
    for x in range(0, 1201, 300):
        d = msp.add_linear_dim(base=(x + 150, -60), p1=(x, 0), p2=(min(x + 300, 1200), 0),
                               dxfattribs={"layer": "DIMS"})
        d.render()
    for k, txt in enumerate(["MECHANICAL ROOM", "ELECTRICAL", "PUMP ROOM", "STORAGE"]):
        msp.add_text(txt, height=18, dxfattribs={"layer": "TEXT"}).set_placement((k * 300 + 40, 200))
    msp.add_mtext("NOTE: PIPE SUPPORTS @ 8'-0\" O.C. MAX\\PVERIFY ALL CLEARANCES",
                  dxfattribs={"layer": "TEXT", "char_height": 12}).set_location((40, 650))
    for k in range(60):
        msp.add_circle((80 + (k % 15) * 70, 470 + (k // 15) * 30), 10, dxfattribs={"layer": "DOORS"})
    from ezdxf.addons.drawing.config import Configuration, BackgroundPolicy
    backend = PyMuPdfBackend()
    cfg = Configuration(background_policy=BackgroundPolicy.WHITE)     # plotted on paper
    Frontend(RenderContext(dxf), backend, config=cfg).draw_layout(msp)
    page = layout.Page(36 * 25.4, 24 * 25.4, layout.Units.mm, margins=layout.Margins.all(20))
    with open(path, "wb") as f:
        f.write(backend.get_pdf_bytes(page))


def siteplan_heavy(path, seed=3):
    rnd = random.Random(seed)
    doc = pymupdf.open()
    W, H = 42 * IN, 30 * IN
    page = doc.new_page(width=W, height=H)
    oc_aerial = doc.add_ocg("Aerial photo", on=True)
    oc_contours = doc.add_ocg("Contours", on=True)
    oc_labels = doc.add_ocg("Elevation labels", on=True)
    # aerial underlay: a smooth noise image, 2400 x 1700 px
    import numpy as np
    h, w = 1700, 2400
    yy, xx = np.mgrid[0:h, 0:w]
    img = (120 + 40 * np.sin(xx / 97.0) * np.cos(yy / 131.0) + 25 * np.sin((xx + yy) / 37.0))
    rgb = np.stack([img * 0.8, img, img * 0.7], axis=-1).clip(0, 255).astype(np.uint8)
    pix = pymupdf.Pixmap(pymupdf.csRGB, w, h, rgb.tobytes(), False)
    page.insert_image(pymupdf.Rect(1 * IN, 1 * IN, W - 7 * IN, H - 1 * IN), pixmap=pix, oc=oc_aerial)
    # contours: many polylines of short segments
    segs = 0
    area = pymupdf.Rect(1 * IN, 1 * IN, W - 7 * IN, H - 1 * IN)
    for k in range(260):
        shape = page.new_shape()
        cx, cy = area.x0 + area.width / 2, area.y0 + area.height / 2
        base = 40 + k * 3.4
        pts = []
        n = 560
        phase = rnd.uniform(0, 6.28)
        for i in range(n + 1):
            t = 2 * math.pi * i / n
            r = base * (1 + 0.18 * math.sin(3 * t + phase) + 0.07 * math.sin(11 * t))
            p = pymupdf.Point(cx + r * 1.5 * math.cos(t), cy + r * math.sin(t))
            if area.contains(p):
                pts.append(p)
        for a, b in zip(pts, pts[1:]):
            if abs(b - a) < 20:
                shape.draw_line(a, b)
                segs += 1
        shape.finish(color=(0.45, 0.25, 0.05) if k % 5 else (0.3, 0.12, 0.0),
                     width=0.6 if k % 5 == 0 else 0.25, oc=oc_contours)
        shape.commit()
    # rotated elevation labels
    labels = 0
    for k in range(0, 260, 5):
        for j in range(8):
            t = 2 * math.pi * j / 8 + k * 0.01
            r = (40 + k * 3.4)
            p = pymupdf.Point(area.x0 + area.width / 2 + r * 1.5 * math.cos(t),
                              area.y0 + area.height / 2 + r * math.sin(t))
            if area.contains(p):
                page.insert_text(p, f"{100 + k // 5}.0", fontsize=5, fontname="helv",
                                 color=(0.3, 0.1, 0), rotate=[0, 90, 180, 270][j % 4], oc=oc_labels)
                labels += 1
    # property line + building pad + title block
    page.draw_polyline([area.tl + (40, 40), area.tr + (-40, 60), area.br + (-80, -40),
                        area.bl + (60, -50), area.tl + (40, 40)], width=2.0, dashes="[18 4 4 4] 0",
                       color=(0.8, 0, 0))
    page.draw_rect(pymupdf.Rect(area.x0 + 900, area.y0 + 600, area.x0 + 1300, area.y0 + 850),
                   width=1.5, fill=(1, 1, 1))
    page.insert_text((area.x0 + 1010, area.y0 + 730), "PROPOSED BUILDING", fontsize=16, fontname="hebo")
    page.insert_text((area.x0 + 1030, area.y0 + 755), "FF ELEV = 112.50", fontsize=10)
    _title_block(page, "GRADING & DRAINAGE PLAN", "A", "C-201")
    doc.save(path, garbage=3, deflate=True)
    return segs, labels


def scanned(path, source):
    src = pymupdf.open(source)
    pm = src[0].get_pixmap(dpi=200, colorspace=pymupdf.csGRAY)
    out = pymupdf.open()
    page = out.new_page(width=src[0].rect.width, height=src[0].rect.height)
    page.insert_image(page.rect, pixmap=pm)
    out.save(path, garbage=3, deflate=True)


def build(out_dir):
    os.makedirs(out_dir, exist_ok=True)
    j = lambda n: os.path.join(out_dir, n)
    info = {"blocks_A": floorplan(j("floorplan_A.pdf"), "A"),
            "blocks_B": floorplan(j("floorplan_B.pdf"), "B")}
    floorplan(j("floorplan_rotated.pdf"), "A", rotated=True)
    dxf_plot(j("dxf_plot.pdf"))
    info["site_segments"], info["site_labels"] = siteplan_heavy(j("siteplan_heavy.pdf"))
    scanned(j("scanned_plan.pdf"), j("floorplan_A.pdf"))
    return info


if __name__ == "__main__":
    print(build(sys.argv[1] if len(sys.argv) > 1 else "cad_samples"))
