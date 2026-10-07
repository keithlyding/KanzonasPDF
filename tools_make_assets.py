"""Regenerate assets/ (icon, logo, installer artwork) from kanzonas/branding.py.

    QT_QPA_PLATFORM=offscreen python tools_make_assets.py
"""
import io
import sys

from PIL import Image
from PySide6.QtCore import QBuffer, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication

app = QApplication(sys.argv)
from kanzonas import branding as B  # noqa: E402


def to_pil(qimg):
    buf = QBuffer()
    buf.open(QBuffer.ReadWrite)
    qimg.save(buf, "PNG")
    return Image.open(io.BytesIO(bytes(buf.data()))).convert("RGBA")


sizes = [16, 20, 24, 32, 40, 48, 64, 128, 256]
frames = {s: to_pil(B.icon_pixmap(s).toImage()) for s in sizes}
frames[256].save("assets/kanzonas.png")
# each size drawn on its own (the small ones are the simplified design)
frames[256].save("assets/kanzonas.ico", sizes=[(s, s) for s in sizes],
                 append_images=[frames[s] for s in sizes[:-1]])
to_pil(B.logo_pixmap(200).toImage()).save("assets/kanzonas-logo.png")
to_pil(B.logo_pixmap(200, dark=True).toImage()).save("assets/kanzonas-logo-dark.png")

# Inno Setup wizard artwork (BMP, no transparency)
def bmp(w, h, draw, path):
    img = QImage(w, h, QImage.Format_RGB32)
    img.fill(QColor("white"))
    p = QPainter(img)
    draw(p)
    p.end()
    to_pil(img).convert("RGB").save(path)


def large(p):
    B.draw_icon(p, 150)                       # translated below
bmp(164, 314, lambda p: (p.translate(7, 70), B.draw_icon(p, 150)), "assets/wizard-large.bmp")
bmp(55, 55, lambda p: (p.translate(2, 2), B.draw_icon(p, 51)), "assets/wizard-small.bmp")
print("assets written")
