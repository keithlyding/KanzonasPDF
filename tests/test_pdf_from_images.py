"""Create PDF from images / Combine with pictures: one page per picture, phone photos turned
upright from their EXIF orientation, JPEGs kept as JPEG, multi-page TIFFs, WebP.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_pdf_from_images
"""
import os
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf as F  # noqa: E402
from PySide6.QtGui import QColor, QImage, QPainter  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import combine  # noqa: E402


def picture(path, w=400, h=300, fmt=None):
    """Red picture with a blue block at its top left."""
    img = QImage(w, h, QImage.Format_RGB32)
    img.fill(QColor("red"))
    p = QPainter(img)
    p.fillRect(0, 0, w // 4, h // 4, QColor("blue"))
    p.end()
    img.save(path, fmt, 90)
    return path


def with_orientation(path, value):
    """Add an EXIF Orientation tag (6 = turn 90 degrees clockwise to view) to a JPEG."""
    tiff = b"MM\x00*\x00\x00\x00\x08" + struct.pack(">H", 1) + \
        struct.pack(">HHIHH", 0x0112, 3, 1, value, 0) + b"\x00\x00\x00\x00"
    app1 = b"Exif\x00\x00" + tiff
    data = open(path, "rb").read()
    data = data[:2] + b"\xff\xe1" + struct.pack(">H", len(app1) + 2) + app1 + data[2:]
    open(path, "wb").write(data)
    return path


def color_at(page, fx, fy):
    pm = page.get_pixmap(dpi=36)
    return pm.pixel(int(pm.width * fx), int(pm.height * fy))


class FromImages(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def p(self, name):
        return os.path.join(self.dir, name)

    def test_letter_pages_turned_to_suit(self):
        wide = picture(self.p("wide.jpg"))
        tall = picture(self.p("tall.png"), 300, 500)
        out = self.p("out.pdf")
        self.assertEqual(combine.combine([wide, tall], out, bookmarks=False), 2)
        d = F.open(out)
        self.assertEqual(d[0].rect, F.Rect(0, 0, 792, 612))           # landscape Letter
        self.assertEqual(d[1].rect, F.Rect(0, 0, 612, 792))           # portrait Letter
        xref = d[0].get_images()[0][0]
        self.assertEqual(d.xref_get_key(xref, "Filter")[1], "/DCTDecode")   # still a JPEG
        r, g, b = color_at(d[0], 0.5, 0.5)[:3]
        self.assertTrue(r > 240 and g < 15 and b < 15)

    def test_phone_photo_upright(self):
        photo = with_orientation(picture(self.p("photo.jpg")), 6)     # stored sideways
        out = self.p("out.pdf")
        combine.combine([photo], out, bookmarks=False, letter=False)
        pg = F.open(out)[0]
        self.assertEqual((round(pg.rect.width), round(pg.rect.height)), (225, 300))   # upright: tall
        # turned clockwise, the blue corner goes from top left to top right
        b = color_at(pg, 0.9, 0.08)
        self.assertGreater(b[2], 200)
        self.assertLess(b[0], 60)

    def test_mixed_with_pdf_tiff_and_webp(self):
        src = F.open()
        src.new_page().insert_text((72, 72), "A PDF page")
        pdf = self.p("doc.pdf")
        src.save(pdf)
        out = self.p("out.pdf")
        n = combine.combine([pdf, picture(self.p("scan.tif")), picture(self.p("pic.webp"))],
                            out)
        self.assertEqual(n, 3)
        d = F.open(out)
        self.assertIn("A PDF page", d[0].get_text())
        self.assertEqual([t[1] for t in d.get_toc()], ["doc", "scan", "pic"])

    def test_dialog_accepts_one_picture(self):
        dlg = combine.CombineDialog(None, self.dir, [picture(self.p("one.png")),
                                                    self.p("notes.txt")], images=True)
        self.assertEqual(dlg.list.count(), 1)                          # not a picture: left out
        self.assertFalse(dlg.bookmarks.isChecked())


if __name__ == "__main__":
    unittest.main()
