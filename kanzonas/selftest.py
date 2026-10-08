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
            lines.append(f"PASS {name} {detail or ''}")
        except Exception:
            ok = False
            lines.append(f"FAIL {name}\n{traceback.format_exc()}")

    # ---- performance budget (runs first, while nothing else is loaded) -------------------
    # Generous limits so slow build machines pass; they catch real regressions (a heavy
    # library imported at start-up, a render that suddenly takes many seconds...).
    HEAVY = ("rapidocr_onnxruntime", "onnxruntime", "pdf2docx", "ezdxf", "openpyxl", "pptx",
             "docx", "pyhanko", "cv2", "aiohttp",
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
        assert mem > 1, "couldn't measure memory"
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

    def t_storage():
        # where settings and personal files go (portable: the data folder beside the exe)
        from . import paths
        st = paths.settings()
        st.setValue("selftest/last_run", "ok")
        st.sync()
        if paths.is_portable():
            ini = os.path.join(paths.data_dir(), "settings.ini")
            assert os.path.exists(ini), "portable settings file missing"
            assert paths.data_dir("signatures").startswith(paths.app_dir())
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
        v.save(out)
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
                                  _orig_enc=None, read_only=False, _backup_path=None)
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
