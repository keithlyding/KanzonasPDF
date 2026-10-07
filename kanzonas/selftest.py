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
        ctypes.windll.psapi.GetProcessMemoryInfo(ctypes.windll.kernel32.GetCurrentProcess(),
                                                 ctypes.byref(pmc), pmc.cb)
        return pmc.PeakWorkingSetSize / 1e6
    except Exception:
        import resource
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


def run(log_path):
    lines, ok = [], True

    def check(name, fn):
        nonlocal ok
        try:
            detail = fn()
            lines.append(f"PASS {name} {detail or ''}")
        except Exception:
            ok = False
            lines.append(f"FAIL {name}\n{traceback.format_exc()}")

    # ---- performance budget (runs first, while nothing else is loaded) -------------------
    # Generous limits so slow build machines pass; they catch real regressions (a heavy
    # library imported at start-up, a render that suddenly takes many seconds...).
    HEAVY = ("rapidocr_onnxruntime", "onnxruntime", "pdf2docx", "ezdxf", "openpyxl", "pptx",
             "docx", "pyhanko", "cv2", "aiohttp")

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
        zoom = time.perf_counter() - t
        mem = _memory_mb()
        win.close_tab(win.tabs.currentIndex())
        win.deleteLater()
        assert startup < 5, f"start-up took {startup:.1f}s (limit 5s)"
        assert first < 5, f"opening a 60k-line sheet took {first:.1f}s (limit 5s)"
        assert zoom < 5, f"zooming to 400% took {zoom:.1f}s (limit 5s)"
        assert mem < 800, f"memory {mem:.0f} MB (limit 800 MB)"
        return f"(start-up {startup:.2f}s, open {first:.2f}s, 400% {zoom:.2f}s, {mem:.0f} MB)"
    check("performance budget", t_performance)

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

    def t_digisign():
        from . import digisign
        cert = os.path.join(tmp, "c.p12")
        digisign.create_certificate("Self Test", "", "", "pw", cert)
        out = os.path.join(tmp, "signed.pdf")
        digisign.sign(data, out, digisign.load_signer(cert, "pw"), "test")
        with open(out, "rb") as f:
            res = digisign.validate(f.read())
        assert res and res[0]["intact"] and not res[0]["modified"], res
    check("digital signature", t_digisign)

    def t_page_tools():
        from . import page_tools
        d = pymupdf.open(stream=data, filetype="pdf")
        page_tools.add_header_footer(d, {"texts": {("footer", "center"): "Page {page} of {pages}"},
                                         "pages": [0]}, "x.pdf")
        page_tools.add_watermark(d, {"text": "DRAFT", "pages": [0]})
        assert "Page 1 of 1" in d[0].get_text()
        page_tools.compress(d.tobytes(), os.path.join(tmp, "small.pdf"), list(page_tools.COMPRESS)[1])
    check("page tools", t_page_tools)

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
        timestamps.HTTPTimeStamper("http://timestamp.digicert.com")
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

    with open(log_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(run(sys.argv[1] if len(sys.argv) > 1 else "selftest.log"))
