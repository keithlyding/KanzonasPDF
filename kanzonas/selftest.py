"""`KanzonasPDF.exe --selftest log.txt`: checks that the bundled features really work in
the built app (OCR engine, every export, signatures, forms). Used by the Windows build."""

import os
import sys
import tempfile
import traceback

import pymupdf


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
