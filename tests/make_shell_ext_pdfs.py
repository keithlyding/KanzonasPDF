"""The PDFs shell_ext/kzshell_test.exe checks Explorer's thumbnails and Preview pane with (on
the Windows build machine):

    python tests/make_shell_ext_pdfs.py DIR
"""
import os
import sys

import pymupdf


def box_page(doc, w=612, h=792):
    pg = doc.new_page(width=w, height=h)
    r = pymupdf.Rect(w / 2 - 75, h / 2 - 100, w / 2 + 75, h / 2 + 100)
    pg.draw_rect(r, color=(0, 0, 0), fill=(0, 0, 0))
    pg.insert_text((72, 72), "KanzonasPDF", fontsize=24)
    return pg


def main(out):
    os.makedirs(out, exist_ok=True)
    d = pymupdf.open()
    box_page(d)
    d.save(os.path.join(out, "page.pdf"))
    d = pymupdf.open()
    box_page(d, 792, 612)
    d.save(os.path.join(out, "wide.pdf"))
    d = pymupdf.open()
    box_page(d)
    box_page(d)
    d.save(os.path.join(out, "two.pdf"))
    d = pymupdf.open()
    box_page(d)
    d.save(os.path.join(out, "locked.pdf"), encryption=pymupdf.PDF_ENCRYPT_AES_256,
           owner_pw="owner", user_pw="user")
    with open(os.path.join(out, "garbage.pdf"), "wb") as f:
        f.write(b"%PDF-1.7\nnot really a PDF\n" + bytes(range(256)) * 8)


if __name__ == "__main__":
    main(sys.argv[1])
