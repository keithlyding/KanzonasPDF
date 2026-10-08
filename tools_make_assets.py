"""Build the icon and logo files from the owner's artwork in assets/.

    QT_QPA_PLATFORM=offscreen python tools_make_assets.py

Sources (the owner's artwork):
- assets/kanzonas-mark-source.png  cactus + sunflower
- assets/kanzonas-logo-source.png  the owner's full logo (Help > About)
The app icon is a red tile (the color people associate with PDF apps); the cactus and
sunflower stand in front of a page whose top comes out above the cactus, as in the owner's
artwork, set a little to the right and lower (its top level with the top of the cactus),
with lines of writing on it; the cactus has a white outline; the page shades from white
at the top to transparent at the bottom. Drawn here as vectors so it is sharp at every size; sizes 16-32 use a
simpler page without an outline. Outputs: kanzonas.ico, kanzonas.png,
installer BMPs and the embedded copy kanzonas/branding_data.py.
"""
import base64
import io
import sys

from PIL import Image
from PySide6.QtCore import QBuffer, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QApplication

app = QApplication(sys.argv)
mark = QImage("assets/kanzonas-mark-source.png")


RED_TOP, RED_BOTTOM = "#b30000", "#800000"      # red tile: the color people link with PDFs


MARGIN = 3.0      # gap (in tile units of 256) kept between the artwork and the tile's edge


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
    # lines of "writing"
    w = x1 - x0
    gap = w * (0.115 if line else 0.16)
    pen = QPen(QColor("#9a9a9a"), w * (0.03 if line else 0.05))
    pen.setCapStyle(Qt.RoundCap)
    p.setPen(pen)
    y = y0 + w * 0.17
    n = 0
    while y < y1 - w * 0.1:
        right = x1 - f - w * 0.06 if y < y0 + f + w * 0.03 else x1 - w * 0.12
        if n % 3 == 2:
            right -= w * 0.22                          # a shorter line now and then
        p.drawLine(QPointF(x0 + w * 0.12, y), QPointF(right, y))
        y += gap
        n += 1


def _fading_page(p, units, x0, y0, x1, y1, f, line=True, fade_from=0.1, fade_to=1.0):
    """The page drawn on its own layer: white at the top, shading to transparent at the
    bottom, so it seems to come out from behind the cactus."""
    layer = QImage(p.device().width(), p.device().height(), QImage.Format_ARGB32_Premultiplied)
    layer.fill(Qt.transparent)
    q = QPainter(layer)
    q.setRenderHint(QPainter.Antialiasing)
    q.setTransform(p.transform())       # same scale (and enlargement) as the icon
    _page(q, x0, y0, x1, y1, f, line)
    q.setCompositionMode(QPainter.CompositionMode_DestinationIn)
    g = QLinearGradient(0, y0 + (y1 - y0) * fade_from, 0, y0 + (y1 - y0) * fade_to)
    g.setColorAt(0, QColor(0, 0, 0, 255))
    g.setColorAt(1, QColor(0, 0, 0, 0))
    q.fillRect(QRectF(-units, -units, 3 * units, 3 * units), g)
    q.end()
    p.save()
    p.resetTransform()
    p.drawImage(0, 0, layer)
    p.restore()


def _outlined(p, r, width):
    """The owner's cactus and sunflower with a white outline around them."""
    import math
    sil = mark.copy()
    q = QPainter(sil)
    q.setCompositionMode(QPainter.CompositionMode_SourceIn)
    q.fillRect(sil.rect(), QColor("white"))
    q.end()
    for k in range(24):
        a = 2 * math.pi * k / 24
        p.drawImage(r.translated(width * math.cos(a), width * math.sin(a)), sil)
    p.drawImage(r, mark)


def _big_art(p):
    _fading_page(p, 256, 84, 62, 202, 224, 28)
    h = 178.0
    w = h * mark.width() / mark.height()
    _outlined(p, QRectF(128 - w / 2, 58, w, h), 3.0)


def _small_art(p):
    _fading_page(p, 128, 39, 31, 103, 115, 16, line=False)
    h = 96.0
    w = h * mark.width() / mark.height()
    _outlined(p, QRectF(64 - w / 2, 28, w, h), 2.2)


def _render(size, units, transform, art):
    img = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    p.scale(size / units, size / units)
    if transform:
        transform(p)
    art(p)
    p.end()
    return img


def _fit(units, radius, art, size=512):
    """The largest enlargement of the page and cactus, centered in the tile, that stays
    inside the rounded tile (MARGIN units from its edge). Returns a function that applies
    it to a painter."""
    import numpy as np
    k = size / units

    def alpha(img):
        a = np.frombuffer(img.constBits(), np.uint8).reshape(size, size, 4)[:, :, 3]
        return a > 24
    ys, xs = np.nonzero(alpha(_render(size, units, None, art)))
    cx, cy = (xs.min() + xs.max() + 1) / 2 / k, (ys.min() + ys.max() + 1) / 2 / k
    m = units / 64 + MARGIN * units / 256
    tile = QPainterPath()
    tile.addRoundedRect(QRectF(m, m, units - 2 * m, units - 2 * m), radius, radius)
    inside = np.zeros((size, size), bool)
    for y in range(size):
        for x in range(size):
            inside[y, x] = tile.contains(QPointF((x + 0.5) / k, (y + 0.5) / k))

    def make(s):
        def apply(p):
            p.translate(units / 2, units / 2)
            p.scale(s, s)
            p.translate(-cx, -cy)
        return apply
    lo, hi = 1.0, 2.0
    for _ in range(14):
        mid = (lo + hi) / 2
        if (alpha(_render(size, units, make(mid), art)) & ~inside).any():
            hi = mid
        else:
            lo = mid
    print(f"artwork enlarged {lo:.3f}x")
    return make(lo)


def _icon(size, units, radius, art):
    fit = _fit(units, radius, art)
    img = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    p.scale(size / units, size / units)
    _tile(p, units, radius)
    fit(p)
    art(p)
    p.end()
    return img


def big_icon(size=512):
    """Red tile; the owner's cactus and sunflower stand in front of a white page whose top
    comes out above the cactus, as big as fits inside the tile."""
    return _icon(size, 256, 44, _big_art)


def small_icon(size=128):
    """16-32 px: same layout, bolder and simpler (no page outline)."""
    return _icon(size, 128, 24, _small_art)


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
