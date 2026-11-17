"""Make the five screenshots the README shows, from sample documents built here.

    QT_QPA_PLATFORM=offscreen python tools/make_screenshots.py [OUTDIR]

OUTDIR defaults to docs/. SHOTS=markup,dark,edit,forms,measure (the default: all of them)
picks which to make. Each picture is the main window at 1440 x 900, grabbed after the
scene is set up through the app's own steps:

  screenshot-markup.png     a catalog page reviewed: highlight, revision cloud, callout
                            (selected), sticky note, APPROVED stamp, the Markups list open
  screenshot-dark.png       the same review in the dark theme
  screenshot-edit-text.png  Edit text open on a paragraph of the catalog's own text
  screenshot-forms.png      the catalog's order form filled in and signed, fields highlighted
  screenshot-measure.png    a floor plan measured to the scale its title block gives: an area
                            (selected), a length, counts, a cloud with a callout, a stamp

The sample catalog ("Desert Bloom", 4 pages) is drawn here with PyMuPDF and its tile
pictures with Pillow; the floor plan is tests/cad_samples.py's. Both go to a temporary
folder. The catalog uses the Inter font when it is installed and Helvetica otherwise.

The settings used are an .ini file in a temporary folder, set before any window exists (as
tests/__init__.py does), so the author name, theme and panels chosen here never touch your
own KanzonasPDF settings."""

import importlib.util
import io
import math
import os
import random
import shutil
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["KANZONAS_LANG"] = "en"

from PySide6.QtCore import QSettings  # noqa: E402

TEMP = tempfile.mkdtemp(prefix="kanzonas-screenshots-")
_SETTINGS_DIR = os.path.join(TEMP, "settings")
os.makedirs(_SETTINGS_DIR)
for _fmt in (QSettings.NativeFormat, QSettings.IniFormat):
    QSettings.setPath(_fmt, QSettings.UserScope, _SETTINGS_DIR)
QSettings.setDefaultFormat(QSettings.IniFormat)

import pymupdf  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QAbstractScrollArea, QApplication, QMessageBox  # noqa: E402

APP = QApplication.instance() or QApplication(sys.argv[:1])
APP.setCursorFlashTime(0)           # (a caret that doesn't blink: Edit text's is always shown)

from kanzonas import paths  # noqa: E402

paths.settings = lambda: QSettings(QSettings.IniFormat, QSettings.UserScope, paths.APP, paths.APP)


def _data_dir(sub=""):
    d = os.path.join(TEMP, "data", sub)
    os.makedirs(d, exist_ok=True)
    return d


paths.data_dir = _data_dir          # (backups and signatures stay in the temporary folder)

# A message box would wait for a click that never comes: each one is noted instead, and the
# run fails at the end (a scene that shows one isn't the scene meant).
MESSAGES = []


def _no_box(*args, **_kw):
    MESSAGES.append(" / ".join(str(a) for a in args[1:3]))
    return QMessageBox.No


for _name in ("question", "information", "warning", "critical"):
    setattr(QMessageBox, _name, staticmethod(_no_box))

from kanzonas import annotations, measure, theme  # noqa: E402
from kanzonas.main_window import MainWindow  # noqa: E402

W, H = 612, 792                      # US Letter
MARGIN = 54
INK = (0.13, 0.13, 0.15)
GRAY = (0.38, 0.38, 0.42)
CREAM = (0.98, 0.97, 0.95)
ORANGE = (0.89, 0.42, 0.18)
NAVY = (0.18, 0.29, 0.48)


def rgb(hex_color):
    h = hex_color.lstrip("#")
    return tuple(int(h[k:k + 2], 16) / 255 for k in (0, 2, 4))


# ---- fonts -------------------------------------------------------------------------------
FONT_DIRS = ["/usr/share/fonts/opentype/inter", "/usr/share/fonts/truetype/inter",
             "/usr/share/fonts/inter", os.path.expanduser("~/.local/share/fonts"),
             os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"),
             os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "Windows", "Fonts")]


def _find_font(names):
    for d in FONT_DIRS:
        for n in names:
            p = os.path.join(d, n)
            if os.path.isfile(p):
                return p
    return None


class Fonts:
    """The catalog's fonts: Inter (regular, semibold, bold) when installed, else Helvetica."""

    def __init__(self):
        self.files = {}
        for key, names in (("reg", ["Inter-Regular.otf", "Inter-Regular.ttf"]),
                           ("semi", ["Inter-SemiBold.otf", "Inter-SemiBold.ttf"]),
                           ("bold", ["Inter-Bold.otf", "Inter-Bold.ttf"])):
            path = _find_font(names)
            if path:
                self.files[key] = path
        if len(self.files) < 3:
            self.files = {}
        self.names = ({"reg": "inter", "semi": "intersemi", "bold": "interbold"} if self.files
                      else {"reg": "helv", "semi": "hebo", "bold": "hebo"})
        self.objects = {k: pymupdf.Font(fontfile=self.files[k]) if self.files
                        else pymupdf.Font(self.names[k]) for k in self.names}

    def install(self, page):
        for k, path in self.files.items():
            page.insert_font(fontname=self.names[k], fontfile=path)

    def text(self, page, pt, s, size, kind="reg", color=INK):
        page.insert_text(pt, s, fontsize=size, fontname=self.names[kind], color=color)

    def right(self, page, x1, y, s, size, kind="reg", color=INK):
        w = self.objects[kind].text_length(s, fontsize=size)
        self.text(page, (x1 - w, y), s, size, kind, color)

    def para(self, page, rect, s, size, kind="reg", color=INK, leading=1.45):
        """Text wrapped in rect, one insert_text per line (lines spaced evenly, as a
        paragraph set by a layout program is)."""
        font = self.objects[kind]
        words, line, y = s.split(), "", rect.y0 + size
        for word in words:
            trial = (line + " " + word).strip()
            if font.text_length(trial, fontsize=size) > rect.width and line:
                self.text(page, (rect.x0, y), line, size, kind, color)
                line, y = word, y + size * leading
            else:
                line = trial
        if line:
            self.text(page, (rect.x0, y), line, size, kind, color)
        return y


def _footer(F, page, number):
    page.draw_line((MARGIN, H - 40), (W - MARGIN, H - 40), color=(0.82, 0.8, 0.77), width=0.5)
    F.text(page, (MARGIN, H - 28), "Desert Bloom Paint & Tile  \u00b7  2026 Catalog", 7.5,
           color=GRAY)
    F.right(page, W - MARGIN, H - 28, str(number), 7.5, color=GRAY)


# ---- the catalog -------------------------------------------------------------------------
PAINTS = [("Saguaro", "#3f6e4a"), ("Sunflower", "#f6c343"), ("Adobe Clay", "#c4683f"),
          ("Prickly Pear", "#c93a72"), ("Monsoon", "#33507e"), ("Mesa Sunset", "#ea7a45"),
          ("Turquoise Sky", "#2aa0a8"), ("Ocotillo", "#d63c34"), ("Sagebrush", "#9aae84"),
          ("Desert Rose", "#e8999a"), ("Juniper", "#4f8a7e"), ("Twilight", "#7a4a86"),
          ("Palo Verde", "#a9bf4a"), ("Canyon Rust", "#a4552c"), ("Night Sky", "#232b52"),
          ("Sand Dune", "#e3cfa4"), ("Marigold", "#ee9a22"), ("Agave", "#2e7f8f"),
          ("Lupine", "#8a72c8"), ("Bone", "#ece5d6")]

PAINT_INTRO = ("Twenty colors taken from the desert at its brightest: interior eggshell, satin "
               "and semi-gloss, low-VOC, in gallon and quart. Order chips by their DB number.")

CARE = ("Zellige is made by hand, so every tile varies in shade and surface: that is its "
        "charm. Install with a 1/16 inch joint and a sanded grout, and seal before and after "
        "grouting. Terrazzo and encaustic tiles ship sealed; reseal once a year in busy "
        "areas. Order 15 percent extra for cuts and future repairs.")

# swatch grid on page 2 (also used to place the markups)
GRID_X, GRID_Y, SW_W, SW_H, GAP_X, ROW = MARGIN, 168, 115.5, 80, 14, 112


def swatch_rect(k):
    r, c = divmod(k, 4)
    x = GRID_X + c * (SW_W + GAP_X)
    y = GRID_Y + r * ROW
    return pymupdf.Rect(x, y, x + SW_W, y + SW_H)


def _sky(stops=((0, "#2a1a4e"), (0.35, "#6a2b6d"), (0.62, "#c2456b"), (0.86, "#f08a4b"),
                (1.0, "#f9b75e"))):
    """The cover's sunset: a smooth vertical gradient, as a picture."""
    img = Image.new("RGB", (8, 600))
    for y in range(600):
        t = y / 599
        for (t0, c0), (t1, c1) in zip(stops, stops[1:]):
            if t0 <= t <= t1:
                u = (t - t0) / (t1 - t0)
                a, b = rgb(c0), rgb(c1)
                col = tuple(int(255 * (x + (z - x) * u)) for x, z in zip(a, b))
                break
        for x in range(8):
            img.putpixel((x, y), col)
    return _png(img)


def _saguaro(shape, x, base, h, s):
    """A saguaro cactus: a trunk and two arms, as rounded bars."""
    tw = 16 * s
    shape.draw_rect(pymupdf.Rect(x - tw / 2, base - h, x + tw / 2, base + 4), radius=0.5)
    for side, at, up in ((-1, 0.45, 0.32), (1, 0.58, 0.28)):
        y = base - h * at
        aw = 12 * s
        x_out = x + side * 30 * s
        shape.draw_rect(pymupdf.Rect(min(x, x_out), y - aw / 2, max(x, x_out), y + aw / 2),
                        radius=0.5)
        shape.draw_rect(pymupdf.Rect(x_out - aw / 2, y - h * up, x_out + aw / 2, y + aw / 2),
                        radius=0.5)


def _cover(F, doc):
    page = doc.new_page(width=W, height=H)
    F.install(page)
    page.insert_image(pymupdf.Rect(0, 0, W, 600), stream=_sky(), keep_proportion=False)
    page.draw_circle((400, 452), 68, color=None, fill=rgb("#fcd77e"), width=0)
    page.draw_polyline([(0, 600), (0, 520), (80, 468), (170, 505), (260, 436), (340, 498),
                        (450, 470), (540, 508), (612, 480), (612, 600)],
                       color=None, fill=rgb("#a2457a"), width=0, closePath=True)
    page.draw_polyline([(0, 620), (0, 540), (90, 500), (190, 560), (300, 480), (400, 545),
                        (500, 500), (612, 560), (612, 620)],
                       color=None, fill=rgb("#6c2b5e"), width=0, closePath=True)
    page.draw_rect(pymupdf.Rect(0, 600, W, H), color=None, fill=rgb("#3a1a3d"), width=0)
    page.draw_polyline([(0, 640), (150, 610), (330, 630), (470, 605), (612, 625), (612, 650),
                        (0, 650)], color=None, fill=rgb("#3a1a3d"), width=0, closePath=True)
    shape = page.new_shape()
    _saguaro(shape, 120, 690, 170, 1.15)
    _saguaro(shape, 470, 700, 120, 0.85)
    _saguaro(shape, 545, 660, 60, 0.5)
    shape.finish(color=None, fill=rgb("#1d0e22"), width=0)
    shape.commit()
    F.text(page, (48, 98), "DESERT BLOOM", 44, "bold", (1, 1, 1))
    F.text(page, (50, 126), "PAINT & TILE", 17, "bold", rgb("#f7a55a"))
    F.text(page, (50, 148), "2026 Color and Tile Catalog", 10.5, "reg", (0.95, 0.9, 0.95))
    F.text(page, (48, H - 46), "Paint colors, handmade tile and free samples.", 9.5, "reg",
           (0.92, 0.85, 0.9))
    F.text(page, (48, H - 32), "Desert Bloom Paint & Tile  \u00b7  Tucson, Arizona", 8, "reg",
           (0.8, 0.7, 0.8))


def _paint_page(F, doc):
    page = doc.new_page(width=W, height=H)
    F.install(page)
    page.draw_rect(page.rect, color=None, fill=CREAM, width=0)
    F.text(page, (MARGIN, 92), "Paint Colors", 32, "bold")
    F.para(page, pymupdf.Rect(MARGIN, 106, W - MARGIN, 150), PAINT_INTRO, 11, color=GRAY)
    for k, (name, color) in enumerate(PAINTS):
        r = swatch_rect(k)
        page.draw_rect(r, color=None, fill=rgb(color), width=0)
        F.text(page, (r.x0, r.y1 + 13), name, 9, "semi")
        F.right(page, r.x1, r.y1 + 13, "DB-%d" % (101 + k), 7, color=GRAY)
    _footer(F, page, 2)


# ---- tile pictures (Pillow) --------------------------------------------------------------
TILE_PX = 480


def _png(img):
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def _shade(hex_color, f):
    r, g, b = (int(hex_color.lstrip("#")[k:k + 2], 16) for k in (0, 2, 4))
    return tuple(max(0, min(255, int(c * f))) for c in (r, g, b))


def _zellige(colors, seed):
    rnd = random.Random(seed)
    img = Image.new("RGB", (TILE_PX, TILE_PX), (226, 220, 206))
    d = ImageDraw.Draw(img)
    n, grout = 5, 5
    size = (TILE_PX - grout) / n
    for r in range(n):
        for c in range(n):
            x0, y0 = c * size + grout, r * size + grout
            base = rnd.choice(colors)
            f = rnd.uniform(0.82, 1.12)
            d.rectangle([x0, y0, x0 + size - grout, y0 + size - grout], fill=_shade(base, f))
            for _ in range(3):              # the glaze pools: lighter and darker patches
                rad = rnd.uniform(8, 20)
                cx = x0 + rnd.uniform(rad + 4, size - grout - rad - 4)
                cy = y0 + rnd.uniform(rad + 4, size - grout - rad - 4)
                d.ellipse([cx - rad, cy - rad, cx + rad, cy + rad],
                          fill=_shade(base, f * rnd.uniform(0.9, 1.15)))
    return _png(img)


def _hexes(colors, seed):
    rnd = random.Random(seed)
    img = Image.new("RGB", (TILE_PX, TILE_PX), (232, 226, 214))
    d = ImageDraw.Draw(img)
    rad = 30
    w = math.sqrt(3) * rad
    for row in range(-1, int(TILE_PX / (1.5 * rad)) + 2):
        for col in range(-1, int(TILE_PX / w) + 2):
            cx = col * w + (w / 2 if row % 2 else 0)
            cy = row * 1.5 * rad
            pts = [(cx + (rad - 3) * math.cos(math.radians(60 * k + 30)),
                    cy + (rad - 3) * math.sin(math.radians(60 * k + 30))) for k in range(6)]
            d.polygon(pts, fill=_shade(rnd.choice(colors), rnd.uniform(0.92, 1.06)))
    return _png(img)


def _encaustic():
    img = Image.new("RGB", (TILE_PX, TILE_PX), (240, 230, 210))
    d = ImageDraw.Draw(img)
    cell = TILE_PX / 4
    for r in range(5):
        for c in range(5):
            cx, cy = c * cell, r * cell
            # navy diamonds on the corners, an orange compass in each cell
            h = cell * 0.42
            d.polygon([(cx, cy - h), (cx + h, cy), (cx, cy + h), (cx - h, cy)],
                      fill=(36, 62, 120))
            d.ellipse([cx - h * 0.5, cy - h * 0.5, cx + h * 0.5, cy + h * 0.5],
                      fill=(226, 104, 48))
            d.ellipse([cx - h * 0.22, cy - h * 0.22, cx + h * 0.22, cy + h * 0.22],
                      fill=(244, 186, 74))
            mx, my = cx + cell / 2, cy + cell / 2
            k = cell * 0.18
            d.polygon([(mx, my - k), (mx + k, my), (mx, my + k), (mx - k, my)],
                      fill=(226, 104, 48))
    return _png(img)


def _terrazzo(seed):
    rnd = random.Random(seed)
    img = Image.new("RGB", (TILE_PX, TILE_PX), (238, 232, 220))
    d = ImageDraw.Draw(img)
    chips = [(214, 60, 52), (246, 195, 67), (36, 62, 120), (42, 160, 168), (234, 122, 69),
             (40, 40, 44), (201, 58, 114), (250, 250, 246)]
    for _ in range(520):
        cx, cy = rnd.uniform(0, TILE_PX), rnd.uniform(0, TILE_PX)
        rad = rnd.uniform(4, 15)
        n = rnd.randint(4, 6)
        pts = [(cx + rad * rnd.uniform(0.6, 1.2) * math.cos(2 * math.pi * k / n + rnd.random()),
                cy + rad * rnd.uniform(0.6, 1.2) * math.sin(2 * math.pi * k / n + rnd.random()))
               for k in range(n)]
        d.polygon(pts, fill=rnd.choice(chips))
    return _png(img)


TILES = [("Zellige - Lagoon", "4 x 4 in glazed terracotta", "$14.50 / sq ft",
          lambda: _zellige(["#1f6f8b", "#2a8fa3", "#17506e", "#3aa3a8"], 1)),
         ("Zellige - Mesa", "4 x 4 in glazed terracotta", "$14.50 / sq ft",
          lambda: _zellige(["#c4683f", "#d97a45", "#b5552f", "#e08a52"], 2)),
         ("Terrazzo - Fiesta", "24 x 24 in polished, 3/8 in", "$18.75 / sq ft",
          lambda: _terrazzo(3)),
         ("Hex Mosaic - Sunflower", "2 in hex on 12 x 12 in mesh", "$11.25 / sq ft",
          lambda: _hexes(["#f6c343", "#ee9a22", "#f2d36b", "#e5822e"], 4)),
         ("Encaustic - Compass", "8 x 8 in cement, sealed", "$16.00 / sq ft", _encaustic),
         ("Hex Mosaic - Monsoon", "2 in hex on 12 x 12 in mesh", "$11.25 / sq ft",
          lambda: _hexes(["#1f5f7a", "#2a8fa3", "#17465e", "#4fb0b8"], 5))]

TILE_SIZE, TILE_GAP, TILE_Y, TILE_ROW = 156, 18, 150, 216


def tile_rect(k):
    r, c = divmod(k, 3)
    x = MARGIN + c * (TILE_SIZE + TILE_GAP)
    y = TILE_Y + r * TILE_ROW
    return pymupdf.Rect(x, y, x + TILE_SIZE, y + TILE_SIZE)


CARE_TOP = TILE_Y + 2 * TILE_ROW + 14


def _tile_page(F, doc):
    page = doc.new_page(width=W, height=H)
    F.install(page)
    page.draw_rect(page.rect, color=None, fill=CREAM, width=0)
    F.text(page, (MARGIN, 92), "Tile Collection", 32, "bold")
    F.text(page, (MARGIN, 120), "Handmade and pressed tile for floors, walls and backsplashes. "
           "Prices are per square foot.", 11, color=GRAY)
    for k, (name, spec, price, make) in enumerate(TILES):
        r = tile_rect(k)
        page.insert_image(r, stream=make())
        F.text(page, (r.x0, r.y1 + 16), name, 10.5, "semi")
        F.text(page, (r.x0, r.y1 + 30), spec, 8.5, color=GRAY)
        F.text(page, (r.x0, r.y1 + 45), price, 10.5, "semi", ORANGE)
    # (room between the heading and the paragraph for Edit text's style bar)
    F.text(page, (MARGIN, CARE_TOP - 2), "Care and installation", 13, "semi")
    F.para(page, pymupdf.Rect(MARGIN, CARE_TOP + 30, W - MARGIN, CARE_TOP + 90), CARE, 10.5,
           leading=1.4)
    _footer(F, page, 3)


# ---- the order form ----------------------------------------------------------------------
def _field(page, name, rect, kind=pymupdf.PDF_WIDGET_TYPE_TEXT):
    w = pymupdf.Widget()
    w.field_type = kind
    w.field_name = name
    w.rect = pymupdf.Rect(rect)
    w.border_color = (0.62, 0.66, 0.74)
    w.border_width = 0.8
    if kind == pymupdf.PDF_WIDGET_TYPE_TEXT:
        w.text_font = "Helv"
        w.text_fontsize = 10
        w.text_color = (0.1, 0.1, 0.12)
    page.add_widget(w)


FORM_ROWS = 4
ITEM_COLS = [("CODE", MARGIN, MARGIN + 70), ("ITEM", MARGIN + 80, MARGIN + 330),
             ("QTY", MARGIN + 340, MARGIN + 410), ("TOTAL", MARGIN + 420, W - MARGIN)]
SIG_LINE_Y = 574


def _form_page(F, doc):
    page = doc.new_page(width=W, height=H)
    F.install(page)
    page.draw_rect(pymupdf.Rect(0, 0, W, 96), color=None, fill=NAVY, width=0)
    F.text(page, (MARGIN, 52), "Sample & Order Form", 26, "bold", (1, 1, 1))
    F.text(page, (MARGIN, 74), "Fill it in on screen, sign it and send it back: no printing "
           "needed.", 9.5, color=(0.86, 0.9, 0.96))
    half = (W - 2 * MARGIN - 24) / 2

    def labeled(label, name, x0, x1, y):
        F.text(page, (x0, y), label, 7, "semi", GRAY)
        _field(page, name, (x0, y + 5, x1, y + 25))

    labeled("NAME", "name", MARGIN, MARGIN + half, 128)
    labeled("COMPANY", "company", MARGIN + half + 24, W - MARGIN, 128)
    labeled("EMAIL", "email", MARGIN, MARGIN + half, 174)
    labeled("PHONE", "phone", MARGIN + half + 24, W - MARGIN, 174)
    labeled("SHIPPING ADDRESS", "address", MARGIN, W - MARGIN, 220)
    F.text(page, (MARGIN, 280), "Items", 14, "semi")
    for label, x0, _x1 in ITEM_COLS:
        F.text(page, (x0, 300), label, 7, "semi", GRAY)
    for r in range(FORM_ROWS):
        y = 306 + r * 32
        for label, x0, x1 in ITEM_COLS:
            _field(page, "%s%d" % (label.lower(), r + 1), (x0, y, x1, y + 20))
    for k, (name, text) in enumerate((("chips", "Send free color chips with my order"),
                                      ("installer", "I'd like an installer to contact me"))):
        y = 450 + k * 36
        _field(page, name, (MARGIN, y, MARGIN + 14, y + 14), pymupdf.PDF_WIDGET_TYPE_CHECKBOX)
        F.text(page, (MARGIN + 24, y + 11), text, 10)
    F.text(page, (MARGIN, 534), "SIGNATURE", 7, "semi", GRAY)
    page.draw_line((MARGIN, SIG_LINE_Y), (MARGIN + half, SIG_LINE_Y), color=GRAY, width=0.8)
    labeled("DATE", "date", MARGIN + half + 24, W - MARGIN, 534)
    F.text(page, (MARGIN, 640), "Questions? Call (520) 555-0100. Samples ship within two "
           "business days.", 9, color=GRAY)
    _footer(F, page, 4)


def build_catalog(path):
    F = Fonts()
    doc = pymupdf.open()
    _cover(F, doc)
    _paint_page(F, doc)
    _tile_page(F, doc)
    _form_page(F, doc)
    doc.set_metadata({"title": "Desert Bloom Paint & Tile: 2026 Catalog",
                      "author": "Desert Bloom Paint & Tile"})
    doc.save(path, garbage=3, deflate=True)
    return path


def build_floorplan(path):
    """tests/cad_samples.py's floor plan (revision A); returns that module."""
    spec = importlib.util.spec_from_file_location(
        "cad_samples", os.path.join(ROOT, "tests", "cad_samples.py"))
    cad = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cad)
    cad.floorplan(path, "A")
    return cad


# ---- the app -----------------------------------------------------------------------------
def pump(seconds=0.6):
    """Run the event loop for a while: timers (thumbnails, the Markups list, page tiles)
    fire and the window is drawn."""
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        APP.processEvents()
        time.sleep(0.01)
    APP.processEvents()


def open_window(path, author, dark=False):
    annotations.set_author(author)
    w = MainWindow()
    w.set_theme("dark" if dark else "light")
    w.resize(1440, 900)
    w.show()
    pump()
    w.open_file(path)
    pump(1.0)
    w.markups_dock.hide()           # (each scene that wants the Markups list opens it)
    return w, w.view()


def show_tab(w, name):
    r = w.ribbon
    for i in range(r.count()):
        if r.tabText(i).replace("&", "") == name:
            r.setCurrentIndex(i)
            return
    raise LookupError(name)


def scroll_to(v, index, pt, left=24, top=24):
    """Scroll so that page point pt is at (left, top) in the view."""
    pw = v.pages[index]
    o = pw.offset()
    v.horizontalScrollBar().setValue(int(pw.x() + o.x() + pt[0] * v.zoom - left))
    v.verticalScrollBar().setValue(int(pw.y() + o.y() + pt[1] * v.zoom - top))
    pump(0.3)


def show_markups_list(w, height):
    w.markups_dock.show()
    w.resizeDocks([w.markups_dock], [height], Qt.Vertical)
    w.resizeDocks([w.props_dock], [270], Qt.Horizontal)
    pump(0.8)


def save_shot(w, outdir, name):
    pump(1.2)
    for area in w.dock.findChildren(QAbstractScrollArea):
        area.verticalScrollBar().setValue(0)        # (the Pages panel from page 1)
    pump(0.5)
    path = os.path.join(outdir, name)
    w.grab().save(path, "PNG")
    print("wrote %s (%d bytes)" % (path, os.path.getsize(path)), flush=True)


def close(w):
    for i in range(w.tabs.count()):
        w.tabs.widget(i).dirty = False
    w._close_confirmed = True
    w.close()
    w.deleteLater()
    pump(0.2)


def text_ends(page, phrase):
    """The left middle of a phrase's first line and the right middle of its last."""
    quads = page.search_for(phrase, quads=True)
    a, b = quads[0].rect, quads[-1].rect
    return pymupdf.Point(a.x0 + 1, (a.y0 + a.y1) / 2), pymupdf.Point(b.x1 - 1, (b.y0 + b.y1) / 2)


def props(kind, **kw):
    p = dict(annotations.tool_props(kind))
    p.update(kw)
    return p


def markup_scene(catalog, outdir, dark):
    w, v = open_window(catalog, "Maria Lopez", dark)
    show_tab(w, "Markup")
    page = v.doc[1]
    v.apply_text_tool(1, "highlight", *text_ends(page, "low-VOC, in gallon"))
    sky = swatch_rect(6)
    cloud = pymupdf.Rect(sky.x0 - 7, sky.y0 - 7, sky.x1 + 7, sky.y1 + 21)
    v._create(1, {"kind": "rect", "props": props("cloud"), "rect": cloud})
    sun = swatch_rect(1)
    box = pymupdf.Rect(sun.x0 - 40, sun.y1 - 38, sun.x1 + 10, sun.y1 - 2)
    callout = v._create(1, {"kind": "callout", "props": props("callout"), "rect": box,
                            "points": [pymupdf.Point(cloud.x0 + 22, cloud.y0 + 10)],
                            "text": "Lobby accent wall: Turquoise Sky, satin"})
    pear = swatch_rect(3)
    v._create(1, {"kind": "note", "props": props("note"),
                  "rect": pymupdf.Rect(pear.x1 - 24, pear.y0 + 4, pear.x1 - 4, pear.y0 + 24),
                  "text": "Can we get this one in semi-gloss for the doors?"})
    v.place_stamp(1, pymupdf.Point(470, 72))
    v.select_xref(1, callout)
    show_markups_list(w, 190)
    v.set_zoom(1.42)
    pump(0.5)
    scroll_to(v, 1, (MARGIN - 40, 40), left=0, top=0)
    save_shot(w, outdir, "screenshot-dark.png" if dark else "screenshot-markup.png")
    close(w)


def edit_text_scene(catalog, outdir):
    w, v = open_window(catalog, "Maria Lopez")
    show_tab(w, "Home")
    v.set_zoom(1.45)
    pump(0.5)
    where = (MARGIN - 34, tile_rect(0).y1 - 28)
    scroll_to(v, 2, where, left=0, top=0)
    w.set_tool("edittext")
    page = v.doc[2]
    r = page.search_for("Order 15")[0]
    v.edit_text_at(2, pymupdf.Point(r.x1 - 0.3, (r.y0 + r.y1) / 2))
    scroll_to(v, 2, where, left=0, top=0)
    save_shot(w, outdir, "screenshot-edit-text.png")
    close(w)


def signature_png(name="Maria Lopez"):
    """A signature in a slanted serif with a stroke under it, dark blue on transparent."""
    font = ImageFont.truetype(io.BytesIO(pymupdf.Font("tiit").buffer), 120)
    img = Image.new("RGBA", (760, 200), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    ink = (24, 36, 110, 255)
    d.text((20, 10), name, font=font, fill=ink, stroke_width=2, stroke_fill=ink)
    d.line([(30, 160), (300, 152), (720, 146)], fill=ink, width=5, joint="curve")
    return _png(img)


FORM_VALUES = {"name": "Maria Lopez", "company": "Lopez Design Studio",
               "email": "maria@example.com", "phone": "(520) 555-0142",
               "address": "2140 E Saguaro Blvd, Tucson, AZ 85719",
               "code1": "DB-107", "item1": "Turquoise Sky, satin", "qty1": "2 gal",
               "total1": "$96.00",
               "code2": "DB-104", "item2": "Prickly Pear, semi-gloss", "qty2": "1 gal",
               "total2": "$52.00",
               "code3": "ZL-01", "item3": "Zellige - Lagoon", "qty3": "48 sq ft",
               "total3": "$696.00"}


def forms_scene(catalog, outdir):
    w, v = open_window(catalog, "Maria Lopez")
    show_tab(w, "Forms")
    if not w.a_hl_fields.isChecked():
        w.a_hl_fields.trigger()
    xrefs = {wd.field_name: wd.xref for wd in v.doc[3].widgets()}
    values = dict(FORM_VALUES, date=time.strftime("%m/%d/%Y"))
    for name, value in values.items():
        v.enter_field_value(3, xrefs[name], value)
    v.fill_field(3, xrefs["chips"])
    w._cache_sig("signature", signature_png())
    v._asked_protect = True         # (no "Protect signed document?" question)
    v.place_signature(3, "signature", box=pymupdf.Rect(MARGIN + 6, SIG_LINE_Y - 36,
                                                        MARGIN + 176, SIG_LINE_Y - 2))
    v.clear_selection()
    v.set_zoom(1.24)
    pump(0.5)
    scroll_to(v, 3, (0, 12), left=0, top=0)
    save_shot(w, outdir, "screenshot-forms.png")
    close(w)


def measure_scene(cad, plan, outdir):
    ft, inch = cad.FT, cad.IN
    ox = oy = 3 * inch                  # where cad_samples.floorplan puts the building
    paths.settings().setValue("show_rulers", "true")
    w, v = open_window(plan, "J. Smith")
    show_tab(w, "Measure")
    note = v.sheet_scale_note(0)        # (as Measure > Read scales from title blocks does)
    v.set_page_scales({0: (measure.scale_from_preset(note["ratio"]), note["unit"],
                           note["label"])})
    P = pymupdf.Point

    def at(x_ft, y_ft):
        return P(ox + x_ft * ft, oy + y_ft * ft)

    area = v._create(0, {"kind": "m_area", "rect": pymupdf.Rect(),
                         "props": props("m_area", fill="#ffc4c4", fontsize=20, opacity=0.6),
                         "points": [at(30.42, 0.67), at(55, 0.67), at(55, 35), at(30.42, 35)]})
    v._create(0, {"kind": "m_length", "props": props("m_length", fontsize=16),
                  "points": [at(55.42, 24), at(80, 24)], "rect": pymupdf.Rect()})
    notes = pymupdf.Rect(25 * inch - 8, 4 * inch - 14, 25 * inch + 330, 4 * inch + 50)
    v._create(0, {"kind": "rect", "props": props("cloud"), "rect": notes})
    v._create(0, {"kind": "callout", "props": props("callout", fontsize=24),
                  "rect": pymupdf.Rect(at(56.5, 9.6), at(77.5, 12)),
                  "points": [P(notes.x0 + 70, notes.y1 - 2)],
                  "text": "REVISE: show extinguishers"})
    r = v.stamp_rect(0, at(67, 4.6))
    c = (r.tl + r.br) / 2
    big = pymupdf.Rect(c, c) + (pymupdf.Rect(r.tl - c, r.br - c) * 3.0)
    v._create(0, {"kind": "stamp", "props": props("stamp"), "rect": big})
    for k in range(10):
        v.place_count(0, at(4 + (8 + k) * 3.6 + 1.5, 38 + 1.2))
    v.select_xref(0, area)
    show_markups_list(w, 190)
    v.set_zoom(0.62)
    pump(0.5)
    scroll_to(v, 0, at(28.5, -3.6), left=0, top=0)
    save_shot(w, outdir, "screenshot-measure.png")
    close(w)
    paths.settings().setValue("show_rulers", "false")


def main():
    outdir = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "docs"))
    os.makedirs(outdir, exist_ok=True)
    s = paths.settings()
    s.setValue("theme", "light")
    s.setValue("ruler_units", "in")
    theme.apply(APP, "light")
    catalog = build_catalog(os.path.join(TEMP, "desert-bloom-catalog.pdf"))
    plan = os.path.join(TEMP, "floorplan_A.pdf")
    cad = build_floorplan(plan)
    only = os.environ.get("SHOTS", "markup,dark,edit,forms,measure").split(",")
    if "markup" in only:
        markup_scene(catalog, outdir, dark=False)
    if "edit" in only:
        edit_text_scene(catalog, outdir)
    if "forms" in only:
        forms_scene(catalog, outdir)
    if "measure" in only:
        measure_scene(cad, plan, outdir)
    if "dark" in only:
        markup_scene(catalog, outdir, dark=True)
    shutil.rmtree(TEMP, ignore_errors=True)
    if MESSAGES:
        sys.exit("A message box came up:\n" + "\n".join(MESSAGES))


if __name__ == "__main__":
    main()
