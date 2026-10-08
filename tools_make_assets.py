"""Build the icon and logo files from the owner's artwork in assets/.

    QT_QPA_PLATFORM=offscreen python tools_make_assets.py

Sources (the owner's artwork):
- assets/kanzonas-mark-source.png  cactus + sunflower
- assets/kanzonas-logo-source.png  the owner's full logo (Help > About)
The app icon is a red tile (the color people associate with PDF apps); the cactus and
sunflower stand in front of a page whose top comes out above the cactus, as in the owner's
artwork; the page shades from white at the top to transparent at the bottom. Drawn here as vectors so it is sharp at every size; sizes 16-32 use a
simpler page without an outline. Outputs: kanzonas.ico, kanzonas.png,
installer BMPs and the embedded copy kanzonas/branding_data.py.
"""
import base64
import io
import sys

from PIL import Image
from PySide6.QtCore import QBuffer, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QApplication

app = QApplication(sys.argv)
mark = QImage("assets/kanzonas-mark-source.png")


RED_TOP, RED_BOTTOM = "#b30000", "#6e0000"      # red tile: the color people link with PDFs


def _tile(p, size_units, radius):
    g = QLinearGradient(0, 0, size_units * 0.35, size_units)     # light top left, deep bottom
    g.setColorAt(0, QColor(RED_TOP))
    g.setColorAt(1, QColor(RED_BOTTOM))
    p.setPen(Qt.NoPen)
    p.setBrush(g)
    m = size_units / 64
    p.drawRoundedRect(QRectF(m, m, size_units - 2 * m, size_units - 2 * m), radius, radius)


def _page(p, x0, y0, x1, y1, f, line=True):
    """White page with a folded top-right corner (as in the owner's artwork)."""
    page = QPainterPath()
    r = (x1 - x0) * 0.07
    page.moveTo(x0 + r, y0)
    page.lineTo(x1 - f, y0)
    page.lineTo(x1, y0 + f)
    page.lineTo(x1, y1 - r)
    page.quadTo(x1, y1, x1 - r, y1)
    page.lineTo(x0 + r, y1)
    page.quadTo(x0, y1, x0, y1 - r)
    page.lineTo(x0, y0 + r)
    page.quadTo(x0, y0, x0 + r, y0)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(0, 0, 0, 60))                    # soft shadow
    p.drawPath(page.translated((x1 - x0) * 0.02, (x1 - x0) * 0.025))
    p.setBrush(QColor("white"))
    if line:
        p.setPen(QPen(QColor("#5a5a5a"), (x1 - x0) * 0.035))
    p.drawPath(page)
    fold = QPainterPath()
    fold.moveTo(x1 - f, y0)
    fold.lineTo(x1 - f, y0 + f)
    fold.lineTo(x1, y0 + f)
    fold.closeSubpath()
    p.setBrush(QColor("#d9d9d9"))
    p.drawPath(fold)


def _fading_page(p, units, x0, y0, x1, y1, f, line=True, fade_from=0.1, fade_to=1.0):
    """The page drawn on its own layer: white at the top, shading to transparent at the
    bottom, so it seems to come out from behind the cactus."""
    scale = p.device().width() / units
    layer = QImage(p.device().width(), p.device().height(), QImage.Format_ARGB32_Premultiplied)
    layer.fill(Qt.transparent)
    q = QPainter(layer)
    q.setRenderHint(QPainter.Antialiasing)
    q.scale(scale, scale)
    _page(q, x0, y0, x1, y1, f, line)
    q.setCompositionMode(QPainter.CompositionMode_DestinationIn)
    g = QLinearGradient(0, y0 + (y1 - y0) * fade_from, 0, y0 + (y1 - y0) * fade_to)
    g.setColorAt(0, QColor(0, 0, 0, 255))
    g.setColorAt(1, QColor(0, 0, 0, 0))
    q.fillRect(QRectF(0, 0, units, units), g)
    q.end()
    p.save()
    p.resetTransform()
    p.drawImage(0, 0, layer)
    p.restore()


def big_icon(size=512):
    """Red tile; the owner's cactus and sunflower stand in front of a white page whose top
    comes out above the cactus."""
    img = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    p.scale(size / 256.0, size / 256.0)
    _tile(p, 256, 44)
    _fading_page(p, 256, 70, 44, 188, 206, 28)
    h = 178.0
    w = h * mark.width() / mark.height()
    p.drawImage(QRectF(128 - w / 2, 58, w, h), mark)
    p.end()
    return img


def small_icon(size=128):
    """16-32 px: same layout, bolder and simpler (no page outline)."""
    img = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    p.scale(size / 128.0, size / 128.0)
    _tile(p, 128, 24)
    _fading_page(p, 128, 32, 18, 96, 102, 16, line=False)
    h = 96.0
    w = h * mark.width() / mark.height()
    p.drawImage(QRectF(64 - w / 2, 28, w, h), mark)
    p.end()
    return img


def to_pil(qimg):
    buf = QBuffer()
    buf.open(QBuffer.ReadWrite)
    qimg.save(buf, "PNG")
    return Image.open(io.BytesIO(bytes(buf.data()))).convert("RGBA")


big = to_pil(big_icon())
small = to_pil(small_icon())
big.save("assets/kanzonas-icon-source.png")
small.save("assets/kanzonas-icon-small-source.png")
sizes = [16, 20, 24, 32, 40, 48, 64, 128, 256]
frames = {s: (small if s <= 32 else big).resize((s, s), Image.LANCZOS) for s in sizes}
frames[256].save("assets/kanzonas.png")
frames[256].save("assets/kanzonas.ico", sizes=[(s, s) for s in sizes],
                 append_images=[frames[s] for s in sizes[:-1]])


def on_white(w, h, size, pos):
    bg = Image.new("RGB", (w, h), "white")
    im = big.resize((size, size), Image.LANCZOS)
    bg.paste(im, pos, im)
    return bg


on_white(164, 314, 150, (7, 80)).save("assets/wizard-large.bmp")
on_white(55, 55, 51, (2, 2)).save("assets/wizard-small.bmp")


def b64(path):
    data = base64.b64encode(open(path, "rb").read()).decode()
    return "\n".join(f'    "{data[i:i + 96]}"' for i in range(0, len(data), 96))


with open("kanzonas/branding_data.py", "w") as f:
    f.write('"""Generated by tools_make_assets.py from assets/: do not edit."""\n\nimport base64\n\n')
    f.write(f"ICON = base64.b64decode(\n{b64('assets/kanzonas-icon-source.png')}\n)\n\n")
    f.write(f"ICON_SMALL = base64.b64decode(\n{b64('assets/kanzonas-icon-small-source.png')}\n)\n\n")
    f.write(f"LOGO = base64.b64decode(\n{b64('assets/kanzonas-logo-source.png')}\n)\n")
print("assets written")
