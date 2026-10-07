"""Run KanzonasPDF features against the generated CAD sheets and report timings/results.

    QT_QPA_PLATFORM=offscreen python tests/cad_battery.py SAMPLES_DIR [WORK_DIR]
"""

import os
import resource
import sys
import time

import pymupdf
from PySide6.QtWidgets import QApplication, QMessageBox, QInputDialog

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

SAMPLES = sys.argv[1]
WORK = sys.argv[2] if len(sys.argv) > 2 else os.path.join(SAMPLES, "out")
os.makedirs(WORK, exist_ok=True)
app = QApplication([])
from kanzonas import annotations as A, dialogs, measure as M, export, compare, ocr  # noqa: E402
from kanzonas.main_window import MainWindow  # noqa: E402

QMessageBox.information = staticmethod(lambda *a, **k: None)
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Discard)
warnings = []
QMessageBox.warning = staticmethod(lambda *a, **k: warnings.append(a[2]))
answers = []
dialogs.get_text = lambda *a, **k: (answers.pop(0) if answers else "test", True)
P = pymupdf.Point
FT = 72 / 48 * 12            # 1/4" = 1'-0"


def rss():
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024


def timed(label, fn):
    t = time.time()
    try:
        r = fn()
        print(f"  {label:38s} {time.time() - t:6.2f}s  {'' if r is None else r}", flush=True)
        return r
    except Exception as ex:
        print(f"  {label:38s} FAILED: {type(ex).__name__}: {ex}", flush=True)
        return None


def pump(n=4):
    for _ in range(n):
        app.processEvents()


def drain_thumbs(w):
    t = time.time()
    while w._thumb_queue and time.time() - t < 60:
        w._thumb_step()
    return f"{w.thumbs.count()} thumbnail(s)"


w = MainWindow()
w.resize(1400, 900)
w.show()


def open_doc(name):
    w.open_file(os.path.join(SAMPLES, name))
    pump(6)
    return w.view()


def disp_to_pdf(v, i, x, y):
    """Displayed (rotated) page point -> unrotated PDF point."""
    return P(x, y) * v.doc[i].derotation_matrix


for name in ("floorplan_A.pdf", "floorplan_rotated.pdf", "dxf_plot.pdf", "siteplan_heavy.pdf",
             "scanned_plan.pdf"):
    print(f"\n=== {name}  (peak RSS so far {rss()} MB)")
    v = timed("open + first paint", lambda: open_doc(name) and None) or w.view()
    v = w.view()
    page = v.doc[0]
    print(f"  page {page.rect.width / 72:.0f}x{page.rect.height / 72:.0f} in, rotation {page.rotation}, "
          f"{len(page.get_drawings())} vector paths, {len(page.get_text().strip())} text chars, "
          f"{len(page.get_images())} images, {len(v.doc.get_ocgs())} layers")
    timed("thumbnails", lambda: drain_thumbs(w))
    for z in (2.0, 4.0):
        timed(f"zoom {int(z * 100)}% and paint", lambda z=z: (v.set_zoom(z), pump(3), v.pages[0].repaint(),
                                                         f"{len(v._tiles)} tiles")[-1])
    v.fit_width()
    pump()
    timed("search 'WAREHOUSE'", lambda: f"{v.find('WAREHOUSE')} match(es)")
    v.clear_search()

    # text selection + highlight on a label
    def highlight_label():
        hits = page.search_for("OFFICE") or page.search_for("MECHANICAL") or page.search_for("PROPOSED")
        if not hits:
            mode, sel = v.text_selection(0, P(100, 100), P(600, 400))
            return f"no label text; box selection found {len(sel)} chars ({mode})"
        r = hits[0] * page.rotation_matrix          # drag along the word as seen on screen
        before = len(list(v.doc[0].annots()))
        a = disp_to_pdf(v, 0, r.x0 + 0.5, (r.y0 + r.y1) / 2)
        b = disp_to_pdf(v, 0, r.x1 - 0.5, (r.y0 + r.y1) / 2)
        v.apply_text_tool(0, "highlight", a, b)
        pg = v.doc[0]
        a = list(pg.annots())[-1] if len(list(pg.annots())) > before else None
        return f"highlighted {a.info['content']!r}" if a else "nothing highlighted"
    timed("highlight a label", highlight_label)

    def layers():
        cfg = v.layer_configs()
        if not cfg:
            return "no layers"
        v.set_layer(cfg[0]["number"], False)
        hidden = [c["text"] for c in v.layer_configs() if not c["on"]]
        v.set_layer(cfg[0]["number"], True)
        return f"{len(cfg)} layers; hid {hidden}; dirty={v.dirty}"
    timed("layers", layers)

    # markups: cloud, callout, stamp (in displayed coordinates)
    def markups():
        d = lambda x, y: disp_to_pdf(v, 0, x, y)
        v.apply_drag_tool(0, "cloud", d(300, 300), d(500, 420), False)
        answers.append("Verify this area")
        v.apply_drag_tool(0, "callout", d(400, 360), d(560, 250), False)
        v.place_stamp(0, d(700, 500))
        pg = v.doc[0]
        kinds = [A.read(a)["kind"] for a in pg.annots() if A.read(a)]
        st = [a for a in pg.annots() if a.type[1] == "Stamp"][-1]
        return f"{kinds} | stamp upright on screen: {st.rect * pg.rotation_matrix}"
    timed("cloud + callout + stamp", markups)

    # measurement
    def measure_it():
        pg = v.doc[0]
        if "floorplan" in name:
            v.set_page_scale([0], M.scale_from_preset(48), "ft-in", '1/4" = 1\'-0"')
            # grid line 1 -> 2 is 25'-0": building origin (3in, 3in) on the unrotated landscape plot
            a, b = d0 = disp_to_pdf(v, 0, 3 * 72, 2 * 72), disp_to_pdf(v, 0, 3 * 72 + 25 * FT, 2 * 72)
            v.apply_drag_tool(0, "m_length", a, b, False)
            pg = v.doc[0]
            m = [x for x in pg.annots() if x.info.get("content", "").startswith("Length")][-1]
            return m.info["content"]
        v.apply_poly(0, "m_area", [disp_to_pdf(v, 0, x, y) for x, y in ((200, 200), (400, 200), (400, 350))])
        pg = v.doc[0]
        return [x.info["content"] for x in pg.annots() if x.info.get("content", "").startswith("Area")][-1]
    timed("measure", measure_it)

    # edit title-block text
    def edit_title():
        lines = v._lines(0)
        hit = [(r, l) for r, l in lines if "FLOOR PLAN" in "".join(s["text"] for s in l["spans"])
               or "GRADING" in "".join(s["text"] for s in l["spans"])]
        if not hit:
            return "no editable title text (text is vector outlines or an image)"
        r, line = hit[0]
        v._apply_text_edit(0, line, "REVISED SHEET TITLE", (0, 0), None)
        return "ok" if "REVISED SHEET TITLE" in v.doc[0].get_text() else "edit not found in text"
    timed("edit title block text", edit_title)

    # redaction over a small area: how much geometry disappears?
    def redact_small():
        pg = v.doc[0]
        before = len(pg.get_drawings())
        r = pymupdf.Rect(page.rect.width * 0.25, page.rect.height * 0.4,
                         page.rect.width * 0.25 + 40, page.rect.height * 0.4 + 40) * pg.derotation_matrix
        v.mark_redactions(0, [r])
        v.apply_redactions()
        pg = v.doc[0]
        after = len(pg.get_drawings())
        res = f"vector paths {before} -> {after}"
        v.undo()
        return res
    timed("redact a 40x40pt area (then undo)", redact_small)

    def stamp_upright():
        pg = v.doc[0]
        st = [a for a in pg.annots() if a.type[1] == "Stamp"][-1]
        r = st.rect * pg.rotation_matrix
        return f"stamp on screen {r.width:.0f} x {r.height:.0f} pt (wide = upright)"
    timed("stamp orientation", stamp_upright)

    out = os.path.join(WORK, name.replace(".pdf", "_marked.pdf"))
    timed("save", lambda: (v.save(out), f"{os.path.getsize(out) / 1e6:.2f} MB")[1])
    timed("reopen saved file", lambda: f"{len(list(pymupdf.open(out)[0].annots()))} annotations kept")
    timed("export DXF", lambda: export.to_dxf(v.doc.tobytes(), os.path.join(WORK, name + ".dxf")))
    timed("export PNG 150dpi", lambda: len(export.to_images(v.doc.tobytes(), os.path.join(WORK, name), dpi=150)))
    if name == "scanned_plan.pdf":
        def do_ocr():
            v.run_ocr([0])
            pg = v.doc[0]
            words = pg.get_text().split()
            return f"{len(words)} words; finds WAREHOUSE: {bool(pg.search_for('WAREHOUSE'))}, " \
                   f"OFFICE: {bool(pg.search_for('OFFICE'))}"
        timed("OCR whole sheet", do_ocr)
    if name == "siteplan_heavy.pdf":
        timed("compress (smaller copy)", lambda: export and "%.2f MB -> %.2f MB" % tuple(
            x / 1e6 for x in __import__("kanzonas.page_tools", fromlist=["x"]).compress(
                v.doc.tobytes(), os.path.join(WORK, "site_small.pdf"), "Smaller (100 dpi images)")))
        timed("flatten markups", lambda: (v.flatten(), f"{len(list(v.doc[0].annots()))} annotations left")[1])
    print(f"  peak RSS {rss()} MB")
    w.close_tab(w.tabs.currentIndex())

print("\n=== compare floorplan_A vs floorplan_B")
a = open(os.path.join(SAMPLES, "floorplan_A.pdf"), "rb").read()
b = open(os.path.join(SAMPLES, "floorplan_B.pdf"), "rb").read()
res = timed("compare", lambda: compare.compare(a, b))
if res:
    data, counts = res
    out = pymupdf.open(stream=data, filetype="pdf")
    print("  changes:", counts, [x.info["content"] for x in out[0].annots()])
    out[0].get_pixmap(dpi=40).save(os.path.join(WORK, "compare.png"))
print("\nwarnings shown to user:", warnings)
print("peak RSS", rss(), "MB")
