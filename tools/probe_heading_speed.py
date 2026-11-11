"""Probe (throwaway branch): how long the automatic-bookmarks heading scan of a 500-page
document takes here, split into PyMuPDF's text reading and KanzonasPDF's own work."""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pymupdf  # noqa: E402
from kanzonas import bookmarks_auto as BA  # noqa: E402

BODY = ("The contractor agrees to deliver the panels by the end of the month. Every panel is "
        "tested before it leaves the shop, and the test sheet goes with it. ")
d = pymupdf.open()
for i in range(500):
    p = d.new_page()
    p.insert_text((72, 40), "Header of the report", fontsize=9)
    p.insert_text((290, 800), "Page %d" % (i + 1), fontsize=9)
    if i % 5 == 0:
        p.insert_text((72, 90), "%d Chapter %d" % (i // 5 + 1, i // 5 + 1), fontsize=18,
                      fontname="hebo")
    p.insert_text((72, 130), "%d.%d Part on page %d" % (i // 5 + 1, i % 5 + 1, i + 1),
                  fontsize=14, fontname="hebo")
    for k in range(4):
        p.insert_textbox(pymupdf.Rect(72, 150 + k * 150, 540, 290 + k * 150), BODY * 5,
                         fontsize=10)
data = d.tobytes()
for attempt in range(3):
    d = pymupdf.open("pdf", data)
    t = time.perf_counter()
    for pg in d:
        tp = pg.get_textpage(flags=BA._FLAGS)
    t_tp = time.perf_counter() - t
    d = pymupdf.open("pdf", data)
    t = time.perf_counter()
    for pg in d:
        pg.get_text("dict", flags=BA._FLAGS)
    t_dict = time.perf_counter() - t
    d = pymupdf.open("pdf", data)
    t = time.perf_counter()
    s = BA.HeadingScan(d)
    for _ in s.run():
        pass
    s.propose()
    t_scan = time.perf_counter() - t
    print("PyMuPDF %s MuPDF %s: textpage %.2f s, dict %.2f s, whole scan %.2f s"
          % (pymupdf.__version__, pymupdf.mupdf_version, t_tp, t_dict, t_scan), flush=True)
if "--profile" in sys.argv:
    import cProfile
    import pstats
    d = pymupdf.open("pdf", data)
    pr = cProfile.Profile()
    pr.enable()
    s = BA.HeadingScan(d)
    for _ in s.run():
        pass
    pr.disable()
    pstats.Stats(pr).sort_stats("tottime").print_stats(12)
