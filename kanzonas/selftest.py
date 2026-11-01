"""`KanzonasPDF.exe --selftest log.txt`: checks that the bundled features really work in
the built app (OCR engine, every export, signatures, forms). Used by the Windows build."""

import os
import sys
import tempfile
import traceback

import pymupdf


def _memory_mb():
    """Peak memory of this process in MB (Windows and Linux)."""
    try:
        import ctypes
        from ctypes import wintypes

        class PMC(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                        ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                        ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]
        pmc = PMC()
        pmc.cb = ctypes.sizeof(PMC)
        k32 = ctypes.windll.kernel32
        k32.GetCurrentProcess.restype = wintypes.HANDLE      # a 64-bit handle, not an int
        k32.K32GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(PMC), wintypes.DWORD]
        if not k32.K32GetProcessMemoryInfo(k32.GetCurrentProcess(), ctypes.byref(pmc), pmc.cb):
            raise OSError("GetProcessMemoryInfo failed")
        return pmc.PeakWorkingSetSize / 1e6
    except (AttributeError, OSError):
        import resource
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


def run(log_path):
    lines, ok = [], True

    def check(name, fn):
        nonlocal ok
        try:
            detail = fn()
            status = "SKIP" if isinstance(detail, str) and detail.startswith("(skipped:") else "PASS"
            lines.append(f"{status} {name} {detail or ''}")
        except Exception:
            ok = False
            lines.append(f"FAIL {name}\n{traceback.format_exc()}")

    # ---- performance budget (runs first, while nothing else is loaded) -------------------
    # Generous limits so slow build machines pass; they catch real regressions (a heavy
    # library imported at start-up, a render that suddenly takes many seconds...).
    HEAVY = ("rapidocr_onnxruntime", "onnxruntime", "pdf2docx", "ezdxf", "openpyxl", "pptx",
             "docx", "pyhanko", "cv2", "aiohttp", "spellchecker",
             # icons are drawn from the bundled font; loading qtawesome means the font wasn't
             # found (and costs ~0.2 s of start-up)
             "qtawesome", "qtpy")

    def t_performance():
        import time
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])
        t = time.perf_counter()
        from .main_window import MainWindow
        win = MainWindow()
        win.show()
        app.processEvents()
        startup = time.perf_counter() - t
        # from the first line of kanzonas/__main__.py (imported by run.py, or run as -m)
        t0 = [getattr(sys.modules.get(m), "_T0", None) for m in ("kanzonas.__main__", "__main__")]
        t0 = next((x for x in t0 if isinstance(x, float)), None)
        launch = None if t0 is None else time.perf_counter() - t0
        loaded = [m for m in HEAVY if m in sys.modules]
        assert not loaded, "loaded at start-up (import them only when used): " + ", ".join(loaded)
        # a CAD-like page: 60,000 line segments
        d = pymupdf.open()
        pg = d.new_page(width=2592, height=1728)
        sh = pg.new_shape()
        for i in range(60000):
            x, y = (i * 37) % 2500, (i * 53) % 1700
            sh.draw_line((x, y), (x + 40, y + 25))
        sh.finish(color=(0, 0, 0), width=0.3)
        sh.commit()
        path = os.path.join(tempfile.mkdtemp(prefix="kzperf"), "cad.pdf")
        d.save(path)
        t = time.perf_counter()
        win.open_file(path)
        app.processEvents()
        v = win.view()
        v.pages[0].repaint()
        first = time.perf_counter() - t
        t = time.perf_counter()
        v.set_zoom(4.0)
        app.processEvents()
        v.pages[0].repaint()
        shown = time.perf_counter() - t
        # (a heavy page is shown scaled at once and drawn sharp in short steps: the time is
        # until every part in view is sharp)
        timer = getattr(v, "_render_timer", None)
        while time.perf_counter() - t < 30 and (
                v._zooming or getattr(v, "_render_wait", None) or
                (timer is not None and timer.isActive())):
            app.processEvents()
        v.pages[0].repaint()
        zoom = time.perf_counter() - t
        mem = _memory_mb()
        win.close_tab(win.tabs.currentIndex())
        win.deleteLater()
        assert startup < 5, f"start-up took {startup:.1f}s (limit 5s)"
        assert launch is None or launch < 8, f"launch to ready took {launch:.1f}s (limit 8s)"
        assert first < 5, f"opening a 60k-line sheet took {first:.1f}s (limit 5s)"
        assert zoom < 5, f"zooming to 400% took {zoom:.1f}s to be sharp (limit 5s)"
        assert shown < 0.5, f"zooming to 400% showed nothing for {shown:.1f}s (limit 0.5s)"
        assert mem > 1, "couldn't measure memory"
        assert mem < 800, f"memory {mem:.0f} MB (limit 800 MB)"
        lt = "n/a" if launch is None else f"{launch:.2f}s"
        return f"(launch {lt}, window {startup:.2f}s, open {first:.2f}s, 400% {zoom:.2f}s (shown {shown:.2f}s), {mem:.0f} MB)"
    check("performance budget", t_performance)

    def t_pdf_speed():
        # the stand-ins for PyMuPDF's slow steps (pdf_speed.py) are in use and do what
        # PyMuPDF's own do: unique markup names; a delete takes the replies with it
        from . import annotations, pdf_speed
        assert pdf_speed.applied and annotations.pdf_speed.applied, \
            "PyMuPDF changed: its slow markup naming is back in use (see pdf_speed.py)"
        assert pdf_speed.can_delete_many(), \
            "PyMuPDF changed: the fast delete of many markups can't run (see pdf_speed.py)"
        d = pymupdf.open()
        pg = d.new_page()
        xs = [pg.add_rect_annot(pymupdf.Rect(10 + 30 * i, 10, 30 + 30 * i, 30)).xref
              for i in range(6)]
        names = [d.xref_get_key(x, "NM")[1] for x in xs]
        assert len(set(names)) == 6 and all(names), f"markup names not unique: {names}"
        reply = pg.add_text_annot((15, 15), "reply").xref
        d.xref_set_key(reply, "IRT", f"{xs[0]} 0 R")
        pdf_speed.delete_many(pg, xs[:4])
        left = sorted(x for x, *_ in pg.annot_xrefs())
        assert left == sorted(xs[4:]), f"left after deleting 4 (and a reply): {left}"
        # Remove hidden information leaves out the slow hidden-text search only on a page
        # with no text at all, and still removes hidden text elsewhere
        d = pymupdf.open()
        lines = d.new_page()
        sh = lines.new_shape()
        for i in range(200):
            sh.draw_line((10, 10 + 3 * i), (500, 12 + 3 * i))
        sh.finish(color=(0, 0, 0), width=0.5)
        sh.commit()
        hidden = d.new_page()
        hidden.insert_text((72, 72), "Seen text", fontsize=12)
        hidden.insert_text((72, 120), "Secret OCR layer", fontsize=12, render_mode=3)
        before = pdf_speed.skipped_searches
        pdf_speed.scrub(d, hidden_text=True, metadata=False, xml_metadata=False)
        assert pdf_speed.skipped_searches == before + 1, \
            "PyMuPDF changed: Remove hidden information searches pages with no text again " \
            "(see pdf_speed.scrub)"
        text = d[1].get_text()
        assert "Seen" in text and "Secret" not in text, f"hidden text left: {text!r}"
        return "(names, delete with replies, hidden-text search)"
    check("PyMuPDF speed fixes", t_pdf_speed)

    def t_text_guard():
        # MuPDF 1.28 ends the program (a segmentation fault) reading the text of a page with
        # ActualText inside ActualText around a picture; text_guard.py reads such pages
        # with TEXT_IGNORE_ACTUALTEXT. (If the guard is gone, this check ends the self-test:
        # the build fails either way.)
        from . import annotations, text_guard  # noqa: F401 (annotations puts it in place)
        assert text_guard.applied, "PyMuPDF changed: the text reading guard is off " \
            "(see text_guard.py)"
        d = pymupdf.open()
        pg = d.new_page()
        pm = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 8, 8), False)
        pm.clear_with(100)
        pg.insert_image((300, 300, 340, 340), stream=pm.tobytes("png"))
        name = d.get_page_images(0)[0][7]
        x = pg.get_contents()[0]
        d.update_stream(x, d.xref_stream(x) + (
            b"\n/Span <</ActualText (A)>> BDC /Span <</ActualText (B)>> BDC "
            b"q 40 0 0 40 100 600 cm /%s Do Q EMC EMC" % name.encode()))
        assert text_guard.risky(pg), "a page with nested ActualText isn't recognized"
        pg.get_text()
        pg.search_for("A")
        plain = d.new_page()
        plain.insert_text((72, 72), "Plain text", fontsize=12)
        assert not text_guard.risky(plain), "an ordinary page is read without ActualText"
        return "(nested ActualText read safely)"
    check("text reading guard", t_text_guard)

    def t_undo_journal():
        # undo and redo go through MuPDF's journal (undo_journal.py), not a copy of the
        # document per edit: its patches on PyMuPDF and the search for MuPDF's tables of
        # added pictures must work with this PyMuPDF, or the app silently falls back to
        # copies (a second per edit on a big plan set)
        import tempfile
        import time
        from PySide6.QtWidgets import QApplication
        QApplication.instance() or QApplication([])
        from . import undo_journal
        from .document_view import DocumentView, _JStep
        assert undo_journal.usable(), \
            "PyMuPDF changed: undo can't go through MuPDF's journal (see undo_journal.py)"
        d = pymupdf.open()
        for _ in range(3):
            d.new_page().insert_text((72, 72), "Page text", fontsize=12)
        pm = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 8, 8), False)
        pm.clear_with(120)
        png = pm.tobytes("png")
        path = os.path.join(tempfile.mkdtemp(), "journal.pdf")
        d.save(path)
        v = DocumentView(path)
        try:
            t = time.perf_counter()
            v.modify(lambda: v.doc[0].add_rect_annot(pymupdf.Rect(50, 100, 150, 160)),
                     pages=[0])
            v.modify(lambda: v.doc[1].insert_image((50, 100, 90, 140), stream=png), pages=[1])
            v.modify(lambda: v.doc.delete_page(2), structural=True)
            took = time.perf_counter() - t
            assert all(isinstance(s, _JStep) for s in v._undo), \
                f"undo keeps copies: {[type(s).__name__ for s in v._undo]}"
            for _ in range(3):
                v.undo()
            assert v.doc.page_count == 3 and not list(v.doc[0].annots()) and \
                not v.doc[1].get_images(), "undo didn't bring the document back"
            for _ in range(3):
                v.redo()
            assert v.doc.page_count == 2 and len(list(v.doc[0].annots())) == 1, \
                "redo didn't make the edits again"
            v.undo()
            v.undo()
            # (the same picture added again after an undo: MuPDF's table emptied)
            v.modify(lambda: v.doc[1].insert_image((50, 100, 90, 140), stream=png), pages=[1])
            x = v.doc[1].get_images()[0][0]
            assert v.doc.xref_stream_raw(x), "a picture added again after an undo is empty"
            v.save()
            with pymupdf.open(path) as saved:
                assert saved.page_count == 3 and saved[1].get_images(), "saved wrongly"
        finally:
            v.dirty = False
            v.close_doc()
        return "(3 edits in %.0f ms, undone, redone, saved)" % (took * 1000)
    check("undo through MuPDF's journal", t_undo_journal)

    def t_edit_speed():
        # editing on a busy page stays quick: 1,000 markups added, moved and deleted, a
        # sheet's 400 labels moved with its lines, the live CAD highlight in short steps, a
        # repaint not reading the selection again (1.6 took 3 s, 14 s, 4 s...; 45 s to move
        # a heavy sheet's text before it was done in one go)
        import time
        from PySide6.QtWidgets import QApplication
        QApplication.instance() or QApplication([])
        from . import annotations
        from .document_view import DocumentView
        from .page_objects import Box
        d = pymupdf.open()
        pg = d.new_page(width=2592, height=1728)
        sh = pg.new_shape()
        for i in range(20000):
            x, y = (i * 37) % 2500, (i * 53) % 1700
            sh.draw_line((x, y), (x + 40, y + 25))
        sh.finish(color=(0, 0, 0), width=0.3)
        sh.commit()
        for i in range(400):
            pg.insert_text((20 + (i % 20) * 125, 30 + (i // 20) * 80), "LABEL %d" % i, fontsize=9)
        path = os.path.join(tempfile.mkdtemp(prefix="kzedit"), "edit.pdf")
        d.save(path)
        v = DocumentView(path)
        took = {}

        def timed(name, fn):
            t = time.perf_counter()
            fn()
            took[name] = time.perf_counter() - t

        def add():
            page = v.doc[0]
            for i in range(1000):
                x, y = 30 + (i % 50) * 50, 30 + (i // 50) * 40
                page.add_rect_annot(pymupdf.Rect(x, y, x + 30, y + 20))

        def everything():
            page = v.doc[0]
            return [a.xref for a in annotations.each_annot(page)]
        try:
            timed("add", lambda: v.modify(add, [0], permission=pymupdf.PDF_PERM_ANNOTATE))
            v._set_selection(0, everything())
            v.selected_models_to_paint()
            timed("repaint", v.selected_models_to_paint)
            timed("move", lambda: v.cad_apply("Moved", pymupdf.Matrix(1, 0, 0, 1, 5, 5)))
            region = Box(pymupdf.Rect(-5, -5, 2600, 1735))
            v.tool = "editobjects"
            for _ in v.cad_preview_steps(0, region, False):
                pass                        # (the page read once, as idle CAD mode does)
            worst, last = 0.0, time.perf_counter()
            for _ in v.cad_preview_steps(0, region, False):
                now = time.perf_counter()
                worst, last = max(worst, now - last), now
            took["highlight step"] = worst
            v._set_selection(0, everything())
            timed("delete", v.delete_selected)
            v.select_objects(0, v.cad_objects(0, region, False))
            timed("sheet move", lambda: v.cad_apply("Moved", pymupdf.Matrix(1, 0, 0, 1, 5, 5)))
            assert not list(annotations.each_annot(v.doc[0])), "markups left after Delete"
        finally:
            v.dirty = False
            v.close_doc()
        # (about 4 times today's times on the build machine: a slow machine passes, a step
        # that is slow again doesn't)
        limits = {"add": 2, "repaint": 0.05, "move": 2, "highlight step": 0.25, "delete": 1.5,
                  "sheet move": 4}
        slow = [f"{k} {took[k]:.2f}s (limit {lim}s)" for k, lim in limits.items()
                if took[k] >= lim]
        assert not slow, "too slow: " + ", ".join(slow)
        return "(" + ", ".join(f"{k} {took[k]:.2f}s" for k in limits) + ")"
    check("editing speed budget", t_edit_speed)

    def t_heavy_speed():
        # a heavy sheet (60,000 shapes) stays quick to work on: its drawing read for CAD
        # (1.6.1: about 1.4 s, its outlines 1.1 s), a markup added and the page drawn again
        # without drawing the sheet again (0.7 s), undone through MuPDF's journal (0.6 s,
        # with a copy of the document), and the wheel zoom showing the page scaled at once
        # (0.7 s to 2.3 s a notch before)
        import random
        import time
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])
        from . import annotations, page_objects
        from .document_view import DocumentView
        rnd = random.Random(7)
        out = [b"1 0 0 -1 0 800 cm 0.35 w 0.2 0.4 0.1 RG"]
        for i in range(60000):
            x, y = rnd.uniform(20, 1100), rnd.uniform(20, 700)
            if i % 10 < 8:
                out.append(b"%.2f %.2f m %.2f %.2f l S" % (x, y, x + rnd.uniform(-40, 40), y))
            else:
                out.append(b"%.2f %.2f 20 -15 re f" % (x, y))
        d = pymupdf.open()
        pg = d.new_page(width=1200, height=800)
        x = d.get_new_xref()
        d.update_object(x, "<<>>")
        d.update_stream(x, b"\n".join(out))
        pg.set_contents(x)
        path = os.path.join(tempfile.mkdtemp(), "heavy.pdf")
        d.save(path, deflate=True)
        d.close()
        times = {}
        v = DocumentView(path)
        try:
            v.resize(1000, 700)
            v.show()
            app.processEvents()
            t = time.perf_counter()
            objs = page_objects.Objects(v.doc[0])
            times["read"] = time.perf_counter() - t
            t = time.perf_counter()
            for it in objs.items:
                objs.lines(it)
            times["outlines"] = time.perf_counter() - t
            assert len(objs.items) == 60000, f"{len(objs.items)} shapes read"
            del objs
            v.set_zoom(1.0)
            w = v.pages[0]
            w._pix = None
            w._render()                     # (the sheet drawn once, as on opening)
            t = time.perf_counter()
            v._create(0, {"kind": "rect", "props": dict(annotations.DEFAULTS["rect"]),
                          "rect": pymupdf.Rect(200, 200, 300, 300)})
            w._pix = None
            w._render()
            times["markup"] = time.perf_counter() - t
            assert w._pix is not None, "the page wasn't drawn again after the markup"
            t = time.perf_counter()
            v.undo()
            w = v.pages[0]
            w._pix = None
            w._render()
            times["undo"] = time.perf_counter() - t
            assert w._pix is not None, "the page wasn't drawn again after the undo"
            assert not list(v.doc[0].annots()), "the markup is still there after undo"
            v._note_render_cost(0, 1.0)     # (heavy: drawn sharp once the wheel stops)
            t = time.perf_counter()
            v._quick_zoom()
            v.set_zoom(1.25)
            v.viewport().repaint()
            times["zoom"] = time.perf_counter() - t
        finally:
            v.dirty = False
            v.close_doc()
        msg = ", ".join("%s %.0f ms" % (k, times[k] * 1000) for k in
                        ("read", "outlines", "markup", "undo", "zoom"))
        budget = {"read": 2.5, "outlines": 2.0, "markup": 0.3, "undo": 0.3, "zoom": 0.15}
        over = [k for k in budget if times[k] > budget[k]]
        assert not over, f"over budget: {over} ({msg})"
        return "(" + msg + ")"
    check("heavy drawing speed budget", t_heavy_speed)

    def t_everyday_speed():
        # what runs on each mouse move or keystroke stays a few milliseconds, and page work on
        # a long document stays quick (1.6 took: a text-selection drag 32-121 ms per move,
        # hover over many markups 70+ ms, Edit objects hover 15-19 ms, night mode 1.2 s per
        # 8 megapixel page, a command's preview 450+ ms per move, inserting pages into a
        # shown document seconds of layout, 0.2-0.4 s per deleted page, each Tab on a big
        # form re-reading every field)
        import time
        from PySide6.QtCore import QPointF
        from PySide6.QtGui import QColor, QImage, QPainter, QPen, QTransform
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])
        from . import page_widget
        from .document_view import DocumentView
        P = pymupdf.Point
        tmp = tempfile.mkdtemp(prefix="kzday")
        d = pymupdf.open()
        for i in range(300):
            p = d.new_page()
            for k in range(40):
                p.insert_text((50, 60 + 17 * k), "Line %d of page %d: the quick brown fox "
                              "jumps over the lazy dog" % (k, i), fontsize=10)
        p = d[1]
        for i in range(2000):
            x, y = 20 + (i % 40) * 14, 20 + (i // 40) * 15
            p.add_rect_annot(pymupdf.Rect(x, y, x + 10, y + 10))
        for k in range(60):
            w = pymupdf.Widget()
            w.field_type = pymupdf.PDF_WIDGET_TYPE_TEXT
            w.field_name = "f%d" % k
            w.rect = pymupdf.Rect(50 + (k % 3) * 160, 60 + (k // 3) * 30, 190 + (k % 3) * 160,
                                  80 + (k // 3) * 30)
            d[2 + k // 20].add_widget(w)
        path = os.path.join(tmp, "day.pdf")
        d.save(path)
        extra = pymupdf.open()
        for i in range(100):
            extra.new_page().insert_text((72, 72), "inserted %d" % i)
        more = os.path.join(tmp, "more.pdf")
        extra.save(more)
        v = DocumentView(path)
        v.resize(900, 700)
        v.show()
        app.processEvents()
        took = {}

        def per(name, n, fn):
            t = time.perf_counter()
            for k in range(n):
                fn(k)
            took[name] = (time.perf_counter() - t) / n
        try:
            v.text_selection(0, P(50, 60), P(300, 300))
            per("text drag move", 30,
                lambda k: v.text_selection(0, P(50, 52), P(60 + 12 * k, 70 + 20 * k)))
            pts = [P(15 + (k * 37) % 560, 15 + (k * 53) % 760) for k in range(150)]
            for q in pts:
                v.annot_at(1, q)
            per("markup hover", 150, lambda k: v.annot_at(1, pts[k]))
            v.object_at(0, pts[0])
            per("objects hover", 150, lambda k: v.object_at(0, pts[k]))
            w, h = 3264, 2448                       # 8 megapixels
            data = bytes(range(256)) * (w * h * 3 // 256)
            per("night mode", 1, lambda k: page_widget.night_samples(data, w, h, w * 3))
            lines = [[(10 + (k % 150) * 6, 10 + (k // 150) * 9),
                      (14 + (k % 150) * 6, 15 + (k // 150) * 9)] for k in range(15000)]
            img = QImage(1600, 1200, QImage.Format_RGB32)

            def ghost(k):
                path_ = page_widget.lines_path(lines)
                pa = QPainter(img)
                pa.setPen(QPen(QColor(0, 120, 215), 1))
                pa.setTransform(QTransform().translate(k, k))
                pa.drawPath(path_)
                pa.end()
            per("command preview", 3, ghost)
            per("Tab on a form", 20, lambda k: v.field_order())
            per("insert 100 pages", 1, lambda k: (v.insert_pdf(more, 150), app.processEvents()))
            per("delete 10 pages", 1, lambda k: (v.delete_pages(list(range(20, 30))),
                                                 app.processEvents()))
            assert v.doc.page_count == 390, f"pages after insert and delete: {v.doc.page_count}"
        finally:
            v.dirty = False
            v.close_doc()
            v.deleteLater()
        limits = {"text drag move": 0.01, "markup hover": 0.01, "objects hover": 0.005,
                  "night mode": 0.5, "command preview": 0.08, "Tab on a form": 0.02,
                  "insert 100 pages": 2.5, "delete 10 pages": 2.5}
        slow = [f"{k} {took[k] * 1000:.1f} ms (limit {lim * 1000:g} ms)"
                for k, lim in limits.items() if took[k] >= lim]
        assert not slow, "too slow: " + ", ".join(slow)
        return "(" + ", ".join(f"{k} {took[k] * 1000:.1f} ms" for k in limits) + ")"
    check("everyday speed budget", t_everyday_speed)

    def t_efficiency():
        # the v0.81 audit's fixes stay in place: linear annotation walk, bounded undo, sliced
        # search, logarithmic page lookup, bounded per-page caches
        import time
        from . import annotations as A
        from . import document_view as DV
        d = pymupdf.open()
        pg = d.new_page()
        for i in range(1500):
            pg.add_rect_annot(pymupdf.Rect(i % 500, 10, i % 500 + 5, 15))
        t = time.perf_counter()
        n = sum(1 for _ in A.each_annot(pg))
        walk = time.perf_counter() - t
        assert n == 1500 and walk < 1, f"walking 1,500 annotations took {walk:.2f}s"
        assert DV.UNDO_BYTES_PER_DOC <= 512 * 2**20, "undo history has no memory budget"
        assert 0 < DV.DocumentView.SEARCH_SLICE <= 0.1, "Find no longer runs in short time slices"
        d = pymupdf.open()
        for i in range(3000):
            d.new_page(width=200, height=200).insert_text((20, 40), "p%d" % i)
        path = os.path.join(tempfile.mkdtemp(prefix="kzeff"), "many.pdf")
        d.save(path)
        v = DV.DocumentView(path)
        v.resize(800, 600)
        t = time.perf_counter()
        for i in range(0, 3000, 7):
            v.goto_page(i)
            assert v.current_page() == i, f"page lookup returned {v.current_page()} for {i}"
        jump = (time.perf_counter() - t) / (3000 // 7)
        for i in range(100):
            v._words(i)
        v.goto_page(2000)
        kept = len(v._word_cache)
        v.close_doc()
        assert kept <= DV.PAGE_CACHE_PAGES, f"{kept} pages of text kept after scrolling away"
        assert jump < 0.01, f"jumping to a page took {jump * 1000:.1f} ms"
        return f"(1,500 annotations {walk * 1000:.0f} ms, page jump {jump * 1000:.2f} ms)"
    check("efficiency checks", t_efficiency)

    tmp = tempfile.mkdtemp(prefix="kzselftest")
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 100), "Self test Hello World 12345", fontsize=20)
    for r in range(3):
        for c in range(3):
            x, y = 72 + c * 100, 200 + r * 24
            page.draw_rect((x, y, x + 100, y + 24))
            page.insert_text((x + 5, y + 16), f"R{r}C{c}", fontsize=11)
    data = doc.tobytes()

    from . import export, ocr

    def t_ocr():
        scan = pymupdf.open()
        p = scan.new_page()
        p.insert_image(p.rect, pixmap=doc[0].get_pixmap(dpi=150))
        res = ocr.recognize(ocr.Rendering(scan[0]))
        text = " ".join(r[1] for r in res)
        assert "Hello" in text, text
        return f"({len(res)} lines)"
    check("ocr", t_ocr)
    check("word", lambda: export.to_word(data, os.path.join(tmp, "t.docx")))
    check("excel", lambda: export.to_excel(data, os.path.join(tmp, "t.xlsx")))
    check("powerpoint", lambda: export.to_powerpoint(data, os.path.join(tmp, "t.pptx")))
    check("dxf", lambda: export.to_dxf(data, os.path.join(tmp, "t.dxf")))
    check("images", lambda: export.to_images(data, os.path.join(tmp, "t")))
    check("text", lambda: export.to_text(data, os.path.join(tmp, "t.txt")))

    def t_files():
        for f in ("t.docx", "t.xlsx", "t.pptx", "t.dxf", "t_p1.png", "t.txt"):
            assert os.path.getsize(os.path.join(tmp, f)) > 0, f
    check("export files", t_files)

    def t_sig_crypto():
        from . import signatures as S
        blob = S._encrypt("1234", b"png-bytes")
        assert S._decrypt("1234", blob) == b"png-bytes"
        try:
            S._decrypt("9999", blob)
            raise AssertionError("wrong PIN accepted")
        except ValueError:
            pass
    check("signature encryption", t_sig_crypto)

    def t_forms():
        d = pymupdf.open()
        p = d.new_page()
        w = pymupdf.Widget()
        w.field_type = pymupdf.PDF_WIDGET_TYPE_TEXT
        w.rect = pymupdf.Rect(50, 50, 200, 70)
        w.field_name = "Name"
        p.add_widget(w)
        w = next(p.widgets())
        w.field_value = "Filled"
        w.update()
        assert next(d[0].widgets()).field_value == "Filled"
    check("forms", t_forms)

    def t_form_navigation():
        # option buttons of one group are exclusive; Tab goes through fields in reading order;
        # the Initials field tool makes a signature-type field named Initials...
        from PySide6.QtWidgets import QApplication
        from .document_view import DocumentView
        QApplication.instance() or QApplication([])
        d = pymupdf.open()
        p = d.new_page()
        for k in range(3):
            w = pymupdf.Widget()
            w.field_type = pymupdf.PDF_WIDGET_TYPE_RADIOBUTTON
            w.rect = pymupdf.Rect(50, 100 + 30 * k, 64, 114 + 30 * k)
            w.field_name, w.field_value = "Group1", False
            before = {x for x, *_ in p.annot_xrefs()}
            p.add_widget(w)
            for x in (x for x, *_ in p.annot_xrefs() if x not in before):
                DocumentView.distinct_on_state(d, x, k + 1)   # as the Option button tool does
        w = pymupdf.Widget()
        w.field_type = pymupdf.PDF_WIDGET_TYPE_TEXT
        w.rect, w.field_name = pymupdf.Rect(50, 50, 200, 70), "Top"
        p.add_widget(w)
        path = os.path.join(tmp, "radio.pdf")
        d.save(path)
        v = DocumentView(path)
        order = v.field_order()
        pg = v.doc[0]
        names = [pg.load_widget(x).field_name for _i, x in order]
        assert names == ["Top", "Group1", "Group1", "Group1"], names
        radios = [x for _i, x in order[1:]]
        v.fill_field(0, radios[0])
        v.fill_field(0, radios[2])
        pg = v.doc[0]
        on = [pg.load_widget(x).field_value != "Off" for x in radios]
        assert on == [False, False, True], on
        v.field_focus = (0, radios[2])
        v.next_field()
        assert v.field_focus == (0, order[0][1]), "Tab didn't wrap to the first field"
        v.create_field(0, "f_initials", pymupdf.Point(300, 300), pymupdf.Point(300, 300), True)
        pg = v.doc[0]
        ini = [w for w in pg.widgets() if w.field_name.startswith("Initials")]
        assert ini and ini[0].field_type == pymupdf.PDF_WIDGET_TYPE_SIGNATURE
        return "(exclusive options, Tab order, initials field)"
    check("form fields: options, Tab, initials", t_form_navigation)

    def t_watermarks():
        from . import page_tools as T
        d = pymupdf.open()
        p = d.new_page()
        p.insert_text((72, 72), "Body text")
        T.add_watermark(d, {"text": "DRAFT", "pages": [0]})
        T.add_watermark(d, {"text": "BEHIND", "pages": [0], "behind": True})
        # an Adobe-style watermark from another app
        x = p.get_contents()[-1]
        d.update_stream(x, d.xref_stream(x) + b"\n/Artifact <</Subtype /Watermark /Type "
                        b"/Pagination >> BDC q BT /F1 9 Tf (X) Tj ET Q EMC\n")
        assert T.has_watermark(d[0])
        n = T.remove_watermarks(d, [0])
        words = d[0].get_text().split()
        assert n == 3 and words == ["Body", "text"], (n, words)
        assert not T.has_watermark(d[0])
        return "(3 removed, page text kept)"
    check("remove watermarks", t_watermarks)

    def t_object_order():
        # the page's own objects: bring to front / send to back, same look where they land
        from . import page_objects as PO
        d = pymupdf.open()
        p = d.new_page(width=200, height=200)
        p.draw_rect((20, 20, 120, 120), color=None, fill=(1, 0, 0))
        p.draw_rect((60, 60, 160, 160), color=(0, 0, 0), fill=(0, 0, 1), fill_opacity=0.9)
        p.insert_text((30, 100), "TEXT", fontsize=30)
        px = lambda: d[0].get_pixmap().pixel(90, 90)    # where the squares overlap
        blue = px()
        red_n = [it["n"] for it in PO.Objects(d[0]).items if it["rect"].x0 < 30][0]
        assert PO.reorder(d[0], [red_n], "front") and px() == (255, 0, 0), px()
        red_n = [it["n"] for it in PO.Objects(d[0]).items if it["rect"].x0 < 30][0]
        assert PO.reorder(d[0], [red_n], "back") and px() == blue, px()
        red_n = [it["n"] for it in PO.Objects(d[0]).items if it["rect"].x0 < 30][0]
        assert PO.reorder(d[0], [red_n], "forward") and px() == (255, 0, 0), \
            "moved object picked up the transparency where it landed"
        assert d[0].get_text().split() == ["TEXT"]
        return "(front, back, forward; colors kept)"
    check("stacking order of page objects", t_object_order)

    def t_links():
        from PySide6.QtWidgets import QApplication
        from .document_view import DocumentView
        QApplication.instance() or QApplication([])
        d = pymupdf.open()
        for _k in range(3):
            d.new_page()
        d[0].set_rotation(90)
        d[0].insert_link({"kind": pymupdf.LINK_GOTO, "from": pymupdf.Rect(10, 20, 110, 40),
                          "page": 2, "to": pymupdf.Point(0, 0)})
        path = os.path.join(tmp, "links.pdf")
        d.save(path)
        v = DocumentView(path)
        link = v.link_at(0, pymupdf.Point(50, 30))     # unrotated page point inside it
        assert link is not None and link["page"] == 2, link
        assert v.link_at(0, pymupdf.Point(300, 300)) is None
        return "(found on a rotated page)"
    check("links", t_links)

    def t_snap_page():
        from . import snapping
        d = pymupdf.open()
        p = d.new_page(width=612, height=792)
        assert snapping.page_snap(p, pymupdf.Point(3, 4), 9) == pymupdf.Point(0, 0)
        assert snapping.page_snap(p, pymupdf.Point(300, 400), 9) == pymupdf.Point(306, 396)
        assert snapping.page_snap(p, pymupdf.Point(608, 200), 9) == pymupdf.Point(612, 200)
        assert snapping.page_snap(p, pymupdf.Point(200, 300), 9) is None
        p.set_rotation(90)          # corners and center of the page as shown
        assert snapping.page_snap(p, pymupdf.Point(305, 393), 9) == pymupdf.Point(306, 396)
        return "(corners, center, edges)"
    check("snap to page", t_snap_page)

    def t_fillin_stamp():
        from . import stamps, annotations as A
        d = pymupdf.open()
        p = d.new_page()
        label = stamps.FORM_PRESETS[0]
        a = A.write(p, {"kind": "stamp", "props": {"label": label, "stroke": "#c00000"},
                        "detail": "4500123\n10/08/2026", "rect": pymupdf.Rect(100, 100, 270, 140)})
        m = A.read(a)
        assert m["detail"] == "4500123\n10/08/2026" and m["props"]["label"] == label, m
        return "(" + stamps.form_title(label) + ")"
    check("fill-in stamps", t_fillin_stamp)

    from . import digisign

    def t_digisign():
        cert = os.path.join(tmp, "c.p12")
        digisign.create_certificate("Self Test", "", "", "pw", cert)
        out = os.path.join(tmp, "signed.pdf")
        digisign.sign(data, out, digisign.load_signer(cert, "pw"), "test")
        with open(out, "rb") as f:
            res = digisign.validate(f.read())
        assert res and res[0]["intact"] and not res[0]["modified"], res
    check("digital signature", t_digisign)

    def t_wincerts():
        # signing through the Windows certificate store (the build adds two test certificates:
        # RSA and ECDSA, CNG keys, like New-SelfSignedCertificate makes)
        if os.name != "nt":
            return "(skipped: not Windows)"
        from . import wincerts
        certs = [c for c in wincerts.list_certificates() if c["name"] == "KanzonasPDF Self Test"]
        if not certs:
            return "(skipped: no test certificate in the Windows store)"
        for c in certs:
            out = os.path.join(tmp, "win-" + c["thumbprint"] + ".pdf")
            digisign.sign(data, out, wincerts.WindowsSigner(c["thumbprint"]), "test")
            with open(out, "rb") as f:
                res = digisign.validate(f.read())
            assert res and res[0]["intact"] and not res[0]["modified"], res
        return "(%d certificates: signed and verified)" % len(certs)
    check("Windows certificate store signing", t_wincerts)

    def t_page_tools():
        from . import page_tools
        d = pymupdf.open(stream=data, filetype="pdf")
        page_tools.add_header_footer(d, {"texts": {("footer", "center"): "Page {page} of {pages}"},
                                         "pages": [0]}, "x.pdf")
        page_tools.add_watermark(d, {"text": "DRAFT", "pages": [0]})
        assert "Page 1 of 1" in d[0].get_text()
        page_tools.compress(d.tobytes(), os.path.join(tmp, "small.pdf"), list(page_tools.COMPRESS)[1])
    check("page tools", t_page_tools)

    def t_storage():
        # where settings and personal files go (portable: the data folder beside the exe)
        from . import paths
        st = paths.settings()
        st.setValue("selftest/last_run", "ok")
        st.sync()
        if paths.is_portable():
            ini = os.path.join(paths.data_dir(), "settings.ini")
            assert os.path.exists(ini), "portable settings file missing"
            where = paths.portable_options().get("data")
            base = os.path.normpath(os.path.join(paths.app_dir(), where)) if where \
                else paths.app_dir()
            assert paths.data_dir("signatures").startswith(base)
            return f"(portable: {paths.data_dir()})"
        return "(installed: registry + AppData)"
    check("storage location", t_storage)

    def t_updates():
        # the checker needs HTTPS in the packaged app; the version logic must pick the newest
        from PySide6.QtNetwork import QSslSocket
        from . import updates
        assert QSslSocket.supportsSsl(), "no TLS support: update checks can't reach GitHub"
        rel = [{"tag_name": "v0.1", "html_url": "a"}, {"tag_name": "v99.2", "html_url": "b"},
               {"tag_name": "v99.10", "html_url": "c"}, {"tag_name": "v999", "draft": True}]
        assert updates.newest(rel, "0.35") == ("99.10", "c")
        assert updates.newest(rel[:1], "0.35") is None
        assert updates.version_tuple("v1.0-beta") == (1, 0)
        rel[2]["assets"] = [{
            "name": "KanzonasPDF-portable.zip",
            "browser_download_url": "https://evil.example/KanzonasPDF-portable.zip",
            "digest": "sha256:" + "ab" * 32,
        }]
        assert updates.asset_url(updates.newest_release(rel, "0.35")) is None
        rel[2]["assets"][0]["browser_download_url"] = (
            "https://github.com/keithlyding/KanzonasPDF/releases/download/v99.10/"
            "KanzonasPDF-portable.zip")
        rel[2]["assets"][0].pop("digest")
        assert updates.asset_url(updates.newest_release(rel, "0.35")) is None
        rel[2]["assets"][0]["digest"] = "sha256:" + "ab" * 32
        got = updates.asset_url(updates.newest_release(rel, "0.35"))
        assert got and got.startswith("https://github.com/"), got
        assert updates.asset_digest(updates.newest_release(rel, "0.35")) == "ab" * 32
        # portable self-update: unpack into _update, keep data, refuse bad zips
        import zipfile
        app = os.path.join(tmp, "app")
        os.makedirs(app, exist_ok=True)
        good, evil = os.path.join(tmp, "good.zip"), os.path.join(tmp, "evil.zip")
        with zipfile.ZipFile(good, "w") as z:
            z.writestr("KanzonasPDF/KanzonasPDF.exe", "exe")
            z.writestr("KanzonasPDF/_internal/a.dll", "dll")
            z.writestr("KanzonasPDF/data/settings.ini", "theirs")
        with zipfile.ZipFile(evil, "w") as z:
            z.writestr("KanzonasPDF/KanzonasPDF.exe", "exe")
            z.writestr("../../escape.txt", "x")
        new = updates.unpack(good, app)
        assert os.path.isfile(os.path.join(new, "_internal", "a.dll"))
        assert not os.path.exists(os.path.join(new, "data")), "update would replace settings"
        try:
            updates.unpack(evil, app)
            raise AssertionError("unsafe zip accepted")
        except ValueError:
            pass
        bat = updates.swap_script(4242, new, app)
        assert "PID eq 4242" in bat and "/MIR" in bat and "%rc%" in bat and "KanzonasPDF.exe" in bat
        return "(TLS: " + QSslSocket.activeBackend() + ")"
    check("update check", t_updates)

    def t_combine():
        from .combine import combine
        a, b = os.path.join(tmp, "ca.pdf"), os.path.join(tmp, "cb.pdf")
        for path, n in ((a, 2), (b, 3)):
            d = pymupdf.open()
            for _ in range(n):
                d.new_page()
            d.save(path)
        out = os.path.join(tmp, "combined.pdf")
        assert combine([a, b], out) == 5
        toc = pymupdf.open(out).get_toc()
        assert [t[1:] for t in toc] == [["ca", 1], ["cb", 3]], toc
        return "(5 pages, 2 bookmarks)"
    check("combine files", t_combine)

    def t_redaction():
        # Search & redact + Apply must remove the text everywhere, not just from the page:
        # form fields, notes, bookmarks and document properties keep their own copies
        from .document_view import DocumentView
        secret = "123-45-6789"
        path = os.path.join(tmp, "redact.pdf")
        d = pymupdf.open()
        pg = d.new_page()
        pg.insert_text((72, 100), "SSN " + secret)
        w = pymupdf.Widget()
        w.field_type, w.field_name = pymupdf.PDF_WIDGET_TYPE_TEXT, "ssn"
        w.rect, w.field_value = pymupdf.Rect(72, 200, 300, 220), secret
        pg.add_widget(w)
        pg.add_text_annot((400, 100), "note " + secret).update()
        d.set_toc([[1, "Part " + secret, 1]])
        d.set_metadata({"title": "File " + secret})
        d.save(path)
        d.close()
        v = DocumentView(path)
        assert v.search_redact(secret) >= 1
        v.apply_redactions()
        out = os.path.join(tmp, "redacted.pdf")
        v.doc.save(out, garbage=4)
        v.doc.close()
        o = pymupdf.open(out)
        found = secret in "".join(pg.get_text() for pg in o) or \
            any(secret in t[1] for t in o.get_toc()) or secret in (o.metadata["title"] or "") or \
            any(secret in (a.info["content"] or "") for pg in o for a in pg.annots()) or \
            any(secret in str(w.field_value) for pg in o for w in pg.widgets())
        o.close()
        assert not found, "redacted text still in the file"
        return "(page text, field, note, bookmark, title)"
    check("redaction removes text everywhere", t_redaction)

    def t_save_safety():
        # independent test report v0.44 (KZ-01..05): protection and signatures survive Save,
        # partial flatten keeps bookmarks, Unicode text edits, Find sees edited text
        from PySide6.QtWidgets import QInputDialog
        from .document_view import DocumentView
        from . import text_edit
        path = os.path.join(tmp, "locked.pdf")
        d = pymupdf.open()
        for i in range(3):
            d.new_page().insert_text((72, 72), "PAGE %d ALPHA" % (i + 1))
        d.set_toc([[1, "First", 1], [1, "Second", 2], [1, "Third", 3]])
        d.save(path, encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="user", owner_pw="owner")
        d.close()
        ask = QInputDialog.getText
        QInputDialog.getText = staticmethod(lambda *a, **k: ("user", True))
        try:
            v = DocumentView(path)
        finally:
            QInputDialog.getText = ask
        out = os.path.join(tmp, "locked-copy.pdf")
        v.save(out)
        assert open(out, "rb").read() == open(path, "rb").read(), "unchanged save not exact"
        assert v.find("ALPHA") == 3
        v.modify(lambda: v.doc[0].insert_text((72, 130), "ALPHA"), [0])
        assert v.find("ALPHA") == 4, "Find didn't see the edit"
        v.doc[1].add_rect_annot(pymupdf.Rect(100, 100, 200, 200))
        v.flatten([1])
        assert [t[1:] for t in v.doc.get_toc()] == [["First", 1], ["Second", 2], ["Third", 3]]
        line = text_edit.text_lines(v.doc[2])[0][1]
        v._apply_text_edit(2, line, "\u03a9 \u0394 \u4e2d\u6587 caf\u00e9", (0, 0), None)
        assert "\u03a9 \u0394 \u4e2d\u6587 caf\u00e9" in v.doc[2].get_text()
        ask = QInputDialog.getText
        QInputDialog.getText = staticmethod(lambda *a, **k: ("owner", True))
        try:
            v.save(out)
        finally:
            QInputDialog.getText = ask
        v.doc.close()
        r = pymupdf.open(out)
        assert r.needs_pass, "edited protected file saved without its password"
        assert r.authenticate("user")
        assert "\u4e2d\u6587" in r[2].get_text()
        r.close()
        return "(exact copy, password kept, bookmarks, Unicode, Find)"
    check("save keeps protection; edits stay correct", t_save_safety)

    def t_erase():
        # Erase content: text inside goes, a line crossing the box is cut at its edges
        from . import erase
        d = pymupdf.open()
        pg = d.new_page()
        pg.draw_line((50, 100), (550, 100), color=(1, 0, 0), width=2)
        pg.insert_text((250, 150), "SECRET")
        pg.insert_text((60, 400), "KEEP")
        erase.erase(pg, pymupdf.Rect(200, 80, 400, 200))
        d = pymupdf.open("pdf", d.tobytes())
        assert d[0].get_text().split() == ["KEEP"], d[0].get_text()
        segs = sorted((round(i[1].x), round(i[2].x)) for dr in d[0].get_drawings()
                      for i in dr["items"])
        assert segs == [(50, 200), (400, 550)], segs
        return "(text removed, line cut at the box)"
    check("erase content", t_erase)

    def t_capture():
        # Capture area keeps vector content, and nothing from outside the box goes with it
        from . import annotations, capture
        d = pymupdf.open()
        pg = d.new_page()
        pg.draw_line((50, 100), (550, 100), color=(1, 0, 0), width=2)
        pg.insert_text((250, 150), "INSIDE")
        pg.insert_text((60, 400), "OUTSIDE")
        data, box = capture.snapshot(pg, pymupdf.Rect(200, 80, 400, 200))
        dst = pymupdf.open()
        dst.new_page()
        x = capture.make_form(dst, data, box)
        assert capture.is_form(dst, x)
        page = dst[0]
        annotations.write(page, {"kind": "image", "props": {"opacity": 1.0},
                                 "rect": pymupdf.Rect(10, 10, 210, 130), "img": x,
                                 "text": "Captured area"})
        out = pymupdf.open("pdf", dst.tobytes(garbage=3))
        raw = b"".join(out.xref_stream(i) or b"" for i in range(1, out.xref_length())
                       if out.xref_is_stream(i))
        assert b"INSIDE" in raw or "INSIDE" in out[0].get_text(), "vector text missing"
        assert b"OUTSIDE" not in raw and "OUTSIDE" not in out[0].get_text(), "outside leaked"
        pix = out[0].get_pixmap(clip=pymupdf.Rect(10, 10, 210, 130))
        assert pix.color_count() > 1, "pasted capture is blank"
        return "(vector, outside removed)"
    check("capture area", t_capture)

    def t_edit_objects():
        # Edit objects: move / resize / delete one picture of the page, nothing else
        from . import page_objects
        pm = pymupdf.Pixmap(pymupdf.csRGB, (0, 0, 4, 3), False)
        png = pm.tobytes("png")
        d = pymupdf.open()
        pg = d.new_page()
        pg.insert_image((50, 50, 250, 200), stream=png)
        pg.insert_text((60, 120), "OVER")
        pg.insert_image((300, 50, 500, 200), stream=png)    # the same image drawn twice
        d = pymupdf.open("pdf", d.tobytes())
        pg = d[0]
        ims = page_objects.images(pg)
        assert [tuple(round(v) for v in i["rect"]) for i in ims] == \
            [(50, 50, 250, 200), (300, 50, 500, 200)], ims
        page_objects.move_to(pg, [ims[0]["n"]], ims[0]["rect"], pymupdf.Rect(100, 300, 200, 375))
        page_objects.delete(pg, [page_objects.images(pg)[1]["n"]])
        d = pymupdf.open("pdf", d.tobytes())
        boxes = [tuple(round(v) for v in pymupdf.Rect(i["bbox"])) for i in d[0].get_image_info()]
        assert boxes == [(100, 300, 200, 375)], boxes
        assert "OVER" in d[0].get_text()
        # vector shapes: a line and a circle move together, colors stay, a box selects
        d = pymupdf.open()
        pg = d.new_page()
        pg.draw_line((200, 60), (400, 60), color=(0, 0, 1), width=3)
        pg.draw_circle((300, 250), 40, color=(0, 0.5, 0))
        pg.draw_rect((450, 300, 550, 380), color=(1, 0, 0), fill=(1, 1, 0))
        objs = page_objects.Objects(pg)
        line = objs.at((300, 61), 2)
        ring = objs.at((340, 250), 2)
        assert line and ring and line["n"] != ring["n"], (line, ring)
        assert objs.at((300, 250), 2) is None            # inside an unfilled circle
        assert [it["n"] for it in objs.inside(pymupdf.Rect(440, 290, 560, 390))] == \
            [objs.at((500, 340), 2)["n"]]                   # the filled square, by box
        ns = [line["n"], ring["n"]]
        r = line["rect"] | ring["rect"]
        page_objects.move_to(pg, ns, r, r + (0, 100, 0, 100))
        got = sorted((tuple(round(v) for v in dr["rect"]), dr["color"])
                     for dr in pg.get_drawings())
        assert got == [((200, 160, 400, 160), (0.0, 0.0, 1.0)),
                       ((260, 310, 340, 390), (0.0, 0.5, 0.0)),
                       ((450, 300, 550, 380), (1.0, 0.0, 0.0))], got
        return "(pictures and shapes: moved, resized, deleted; text and colors kept)"
    check("edit objects", t_edit_objects)

    def t_backups():
        # automatic backup: written while there are unsaved changes, removed after saving
        import types
        from . import autosave, measure
        d = pymupdf.open()
        d.new_page().insert_text((72, 72), "BACKUP")
        v = types.SimpleNamespace(doc=d, path=os.path.join(tmp, "b.pdf"), dirty=True,
                                  _orig_enc=None, security=None, read_only=False, _backup_path=None)
        saver = autosave.Autosaver.__new__(autosave.Autosaver)
        saver.backup(v)
        bp = v._backup_path
        assert os.path.exists(bp) and "BACKUP" in pymupdf.open(bp)[0].get_text()
        assert any(p == bp for p, _o, _t in autosave.leftovers())
        saver.discard(v)
        assert not os.path.exists(bp)
        old = measure.FRACTION
        measure.FRACTION = 4
        try:
            assert measure.fmt_length(1.0, "ft-in") == "3'-3 1/4\"", measure.fmt_length(1.0, "ft-in")
        finally:
            measure.FRACTION = old
        return "(backup written and removed; measuring precision)"
    check("backups and measuring options", t_backups)

    def t_background():
        # Document > Background: behind the content, removable, rotated pages right way up
        from . import background
        d = pymupdf.open()
        for rot in (0, 90):
            pg = d.new_page(width=300, height=200)
            pg.insert_text((20, 40), "ON TOP")
            pg.set_rotation(rot)
        background.apply(d, [0, 1], {"kind": "gradient", "color": "#ff0000",
                                     "color2": "#0000ff", "direction": "down", "opacity": 1})
        d = pymupdf.open("pdf", d.tobytes(garbage=3))
        for pg in d:
            assert background.has_background(pg)
            assert pg.get_text().split() == ["ON", "TOP"], pg.get_text()
            pm = pg.get_pixmap(dpi=20)
            top, bottom = pm.pixel(pm.width // 2, 1), pm.pixel(pm.width // 2, pm.height - 2)
            assert top[0] > 200 and top[2] < 60 and bottom[2] > 200 and bottom[0] < 60, (top, bottom)
        assert background.remove_pages(d, [0, 1]) == 2
        pm = d[1].get_pixmap(dpi=20)
        assert pm.pixel(pm.width // 2, 1) == (255, 255, 255)
        return "(gradient behind text on normal and rotated pages; removed)"
    check("page background", t_background)

    def t_measure_opacity():
        # a see-through measurement keeps its transparency when its label is added
        from . import annotations
        d = pymupdf.open()
        pg = d.new_page()
        props = annotations.tool_props("m_area")
        props["opacity"] = 0.6
        annotations.write(pg, {"kind": "m_area", "props": props,
                               "points": [pymupdf.Point(50, 50), pymupdf.Point(200, 50),
                                          pymupdf.Point(200, 200)]})
        pymupdf.TOOLS.mupdf_warnings(reset=True)
        r = pymupdf.open("pdf", d.tobytes())
        r[0].get_pixmap()
        warn = pymupdf.TOOLS.mupdf_warnings()
        assert "ExtGState" not in warn, warn
        return "(label added, transparency kept)"
    check("measurement opacity", t_measure_opacity)

    def t_nudge():
        # arrow keys: repeated moves of a page shape fold into one wrapper (no growth)
        from . import page_objects
        d = pymupdf.open()
        pg = d.new_page()
        pg.draw_line((100, 300), (300, 300), color=(0, 0, 1), width=2)
        objs = page_objects.Objects(pg)
        ns = [objs.items[0]["n"]]
        r = objs.items[0]["rect"]
        size0 = None
        for i in range(50):
            page_objects.move_to(pg, ns, r, r + (1, -1, 1, -1))
            r = r + (1, -1, 1, -1)
            if i == 0:
                size0 = len(page_objects._contents(pg))
        # only the numbers change length a little; 50 nested wrappers would add ~2,500 bytes
        assert len(page_objects._contents(pg)) < size0 + 40, "stream grew with each nudge"
        got = [tuple(round(v) for v in dr["rect"]) for dr in pg.get_drawings()]
        assert got == [(150, 250, 350, 250)], got
        return "(50 nudges, exact position, no growth)"
    check("arrow-key nudge", t_nudge)

    def t_edit_embedded_font():
        # Edit text with the PDF's own embedded font (not installed on this computer): the
        # font must survive removing the old line ("need font file or buffer" before v0.66)
        from . import text_edit
        src = pymupdf.Font("cjk")                       # any real font file will do
        d = pymupdf.open()
        pg = d.new_page()
        pg.insert_font(fontname="F1", fontbuffer=src.buffer)
        pg.insert_text((72, 100), "Invoice total", fontname="F1", fontsize=14)
        d = pymupdf.open("pdf", d.tobytes(garbage=3, deflate=True))
        pg = d[0]
        saved = text_edit._SYSTEM_FONTS
        text_edit._SYSTEM_FONTS = {}                    # as if it isn't installed
        try:
            used = text_edit.replace_line(pg, text_edit.text_lines(pg)[0][1], "Invoice paid")
        finally:
            text_edit._SYSTEM_FONTS = saved
        r = pymupdf.open("pdf", d.tobytes())
        assert r[0].get_text().strip() == "Invoice paid", r[0].get_text()
        assert used and used.startswith("KZ"), used
        return "(embedded font reused: " + used + ")"
    check("edit text with an embedded font", t_edit_embedded_font)

    def t_edit_symbols():
        # Edit text with symbols few fonts have: written (as look-alikes at worst), and
        # characters that can't be written are refused by name, never written as others
        from . import text_edit
        d = pymupdf.open()
        d.new_page().insert_text((72, 100), "Original", fontsize=12)
        data = d.tobytes()
        saved = text_edit._SYSTEM_FONTS
        text_edit._SYSTEM_FONTS = {}                    # worst case: no broad fonts
        try:
            for new, want in (("Temp \u221210 C", "Temp -10 C"), ("\u2300 25", "\u00d8 25")):
                doc = pymupdf.open("pdf", data)
                text_edit.replace_line(doc[0], text_edit.text_lines(doc[0])[0][1], new)
                got = pymupdf.open("pdf", doc.tobytes())[0].get_text().strip()
                assert got == want, (new, got)
            doc = pymupdf.open("pdf", data)
            try:
                text_edit.replace_line(doc[0], text_edit.text_lines(doc[0])[0][1], "Hi \U0001F600")
                raise AssertionError("an emoji was written")
            except ValueError as e:
                assert "U+1F600" in str(e), e
        finally:
            text_edit._SYSTEM_FONTS = saved
        return "(minus sign, diameter written; emoji refused by name)"
    check("edit text with symbols", t_edit_symbols)


    def t_security():
        d = pymupdf.open(stream=data, filetype="pdf")
        out = os.path.join(tmp, "secure.pdf")
        d.save(out, encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="own", user_pw="open",
               permissions=pymupdf.PDF_PERM_PRINT)
        x = pymupdf.open(out)
        assert x.needs_pass and not x.authenticate("bad") and x.authenticate("open")
        assert not x.permissions & pymupdf.PDF_PERM_MODIFY
        assert pymupdf.open(out).authenticate("own") & 4
    check("passwords and permissions", t_security)

    def t_timestamp():
        # the time server client must be bundled; stamp with pyHanko's built-in test server
        import aiohttp  # noqa: F401
        from pyhanko.sign import timestamps
        from . import digisign
        timestamps.HTTPTimeStamper("https://timestamp.digicert.com")
        p12 = digisign.create_certificate("Self Test", "", "", "pw", os.path.join(tmp, "t.p12"))
        signer = digisign.load_signer(p12, "pw")
        out = os.path.join(tmp, "ts.pdf")
        digisign.timestamp(data, out, "", timestamps.DummyTimeStamper(signer.signing_cert,
                                                                        signer.signing_key))
        res = digisign.validate(open(out, "rb").read())
        assert res and res[0].get("timestamp") and res[0]["ok"], res
    check("timestamp", t_timestamp)

    def t_manual():
        # every menu command must be described in Help > User manual (kanzonas/manual.py)
        from PySide6.QtWidgets import QApplication
        from . import manual
        from .main_window import MainWindow
        app = QApplication.instance() or QApplication([])
        win = MainWindow()
        try:
            missing = manual.missing_from_manual(win)
        finally:
            win.deleteLater()
        assert not missing, "not in the user manual: " + ", ".join(missing)
        return f"({len(manual.sections())} chapters)"
    check("user manual covers every command", t_manual)

    def t_spelling():
        # the word list is bundled in the exe (--collect-all spellchecker) and American
        from . import spelling
        assert spelling.is_known("receive") and spelling.is_known("color")
        assert not spelling.is_known("recieve") and not spelling.is_known("colour")
        assert "receive" in spelling.suggestions("recieve")
    check("spell check", t_spelling)

    with open(log_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(run(sys.argv[1] if len(sys.argv) > 1 else "selftest.log"))
