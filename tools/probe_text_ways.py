"""Probe (throwaway branch): which way of reading a page's text is slow on the Mac."""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pymupdf  # noqa: E402

BODY = ("The contractor agrees to deliver the panels by the end of the month. Every panel is "
        "tested before it leaves the shop, and the test sheet goes with it. ")
FLAGS = pymupdf.TEXT_PRESERVE_WHITESPACE | pymupdf.TEXT_MEDIABOX_CLIP
d = pymupdf.open()
for i in range(200):
    p = d.new_page()
    p.insert_text((72, 130), "%d Part on page %d" % (i, i + 1), fontsize=14, fontname="hebo")
    for k in range(4):
        p.insert_textbox(pymupdf.Rect(72, 150 + k * 150, 540, 290 + k * 150), BODY * 5,
                         fontsize=10)
doc = pymupdf.open("pdf", d.tobytes())
tps = [pg.get_textpage(flags=FLAGS) for pg in doc]
m = pymupdf.mupdf


def json_way(tp):
    res = m.fz_new_buffer(1024)
    out = m.FzOutput(res)
    m.fz_print_stext_page_as_json(out, tp.this, 1.0)
    out.fz_close_output()
    return json.loads(pymupdf.JM_EscapeStrFromBuffer(res))


ways = [
    ("dict", lambda tp: tp.extractDICT()),
    ("rawdict", lambda tp: tp.extractRAWDICT()),
    ("words", lambda tp: tp.extractWORDS()),
    ("blocks", lambda tp: tp.extractBLOCKS()),
    ("text", lambda tp: tp.extractText()),
    ("mupdf json", json_way),
]
for name, fn in ways:
    t = time.perf_counter()
    for tp in tps:
        fn(tp)
    print("%-28s %.3f s" % (name, time.perf_counter() - t), flush=True)
for setting in ("unset_quad_corrections", "set_small_glyph_heights"):
    if hasattr(pymupdf.TOOLS, setting):
        getattr(pymupdf.TOOLS, setting)(True)
        t = time.perf_counter()
        for tp in tps:
            tp.extractDICT()
        print("%-28s %.3f s" % ("dict, " + setting, time.perf_counter() - t), flush=True)
        getattr(pymupdf.TOOLS, setting)(False)
print(pymupdf.__version__, sum(len(b.get("lines", ())) for tp in tps[:1]
                                for b in tp.extractDICT()["blocks"]), "lines on a page")
