"""KanzonasPDF icon and logo: the owner's artwork (saguaro with a sunflower on a PDF page).

Built from the artwork in assets/ by tools_make_assets.py and embedded in branding_data.py,
so a build can never lose them.
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QImage, QPixmap

from . import branding_data

_cache = {}


def _image(name):
    if name not in _cache:
        img = QImage()
        img.loadFromData(getattr(branding_data, name), "PNG")
        _cache[name] = img
    return _cache[name]


def icon_pixmap(size):
    """Sizes up to 32 px use the simplified icon (cactus and sunflower only)."""
    src = _image("ICON_SMALL" if size <= 32 else "ICON")
    return QPixmap.fromImage(src.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation))


def app_icon():
    """QIcon with a smoothly scaled bitmap for each common size."""
    ic = QIcon()
    for s in (16, 20, 24, 32, 40, 48, 64, 128, 256):
        ic.addPixmap(icon_pixmap(s))
    return ic


def logo_pixmap(height):
    """The full logo (mark, name and tagline) at the given height."""
    return QPixmap.fromImage(_image("LOGO").scaledToHeight(height, Qt.SmoothTransformation))
