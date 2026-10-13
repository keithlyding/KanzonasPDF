"""Make assets/portableapps-appicon.ico: the app icon with the sizes the PortableApps.com
Format asks for (256 colors at 16, 32 and 48 px, plus true color with transparency at 16,
32, 48 and 256 px; the 256 px one as PNG).

    python tools/make_paf_icon.py
"""
import os
import struct
import sys

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt
from PySide6.QtGui import QGuiApplication, QImage

SRC = "assets/kanzonas.png"
OUT = "assets/portableapps-appicon.ico"


def scaled(img, size):
    return img.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation) \
        .convertToFormat(QImage.Format_ARGB32)


def mask_rows(img, size):
    """AND mask: 1 bit per pixel, rows padded to 4 bytes, bottom-up; set = transparent."""
    stride = ((size + 31) // 32) * 4
    out = bytearray()
    for y in range(size - 1, -1, -1):
        row = bytearray(stride)
        for x in range(size):
            if (img.pixel(x, y) >> 24) < 128:
                row[x // 8] |= 0x80 >> (x % 8)
        out += row
    return bytes(out)


def bmp_8bit(img, size):
    pal = img.convertToFormat(QImage.Format_Indexed8, Qt.ThresholdDither | Qt.AvoidDither)
    colors = pal.colorTable() + [0] * (256 - len(pal.colorTable()))
    header = struct.pack("<IiiHHIIiiII", 40, size, size * 2, 1, 8, 0, 0, 0, 0, 256, 0)
    palette = b"".join(struct.pack("<BBBB", c & 255, (c >> 8) & 255, (c >> 16) & 255, 0)
                       for c in colors[:256])
    stride = (size + 3) & ~3
    pixels = bytearray()
    for y in range(size - 1, -1, -1):
        line = bytes(pal.constScanLine(y))[:size]
        pixels += line + bytes(stride - size)
    return header + palette + bytes(pixels) + mask_rows(img, size)


def bmp_32bit(img, size):
    header = struct.pack("<IiiHHIIiiII", 40, size, size * 2, 1, 32, 0, 0, 0, 0, 0, 0)
    pixels = bytearray()
    for y in range(size - 1, -1, -1):
        for x in range(size):
            p = img.pixel(x, y)
            pixels += struct.pack("<I", p & 0xFFFFFFFF)          # BGRA in memory
    return header + bytes(pixels) + mask_rows(img, size)


def png(img):
    data = QByteArray()
    buf = QBuffer(data)
    buf.open(QIODevice.WriteOnly)
    img.save(buf, "PNG")
    return bytes(data)


def build(src=SRC, out=OUT):
    app = QGuiApplication.instance() or QGuiApplication([])  # noqa: F841
    base = QImage(src)
    if base.isNull():
        raise SystemExit("can't read " + src)
    entries = []                      # (size, bits per pixel, colors, data)
    for size in (16, 32, 48):
        entries.append((size, 8, 0, bmp_8bit(scaled(base, size), size)))
    for size in (16, 32, 48):
        entries.append((size, 32, 0, bmp_32bit(scaled(base, size), size)))
    entries.append((256, 32, 0, png(scaled(base, 256))))
    head = struct.pack("<HHH", 0, 1, len(entries))
    offset = 6 + 16 * len(entries)
    table, body = b"", b""
    for size, bpp, colors, data in entries:
        table += struct.pack("<BBBBHHII", size % 256, size % 256, colors, 0, 1, bpp,
                             len(data), offset + len(body))
        body += data
    with open(out, "wb") as f:
        f.write(head + table + body)
    return out


if __name__ == "__main__":
    print(build(*sys.argv[1:]))
