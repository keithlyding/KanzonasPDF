"""A single rendered PDF page inside the scrolling document view.

Handles drawing (page image, search hits, comment boxes, selection handles, previews)
and turns mouse input into calls on the DocumentView, which owns all PDF edits.
"""

import math
import time

import pymupdf
from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import (QPainter, QImage, QPixmap, QColor, QPen, QPainterPath,
                           QFontMetrics, QTransform)
from PySide6.QtWidgets import QWidget, QToolTip, QApplication

from . import annotations as A
from . import cad_select
from . import render_layers as RL
from .i18n import tr

TEXT_TOOLS = {"select", "highlight", "underline", "strikeout", "comment", "redact"}
SHAPE_TOOLS = {"textbox", "rect", "ellipse", "line", "arrow", "eraser", "cloud", "callout",
               "m_length", "m_calibrate", "m_radius", "image", "placeholder", "erasecontent",
               "capture", "crop", "link"}
POLY_TOOLS = {"polygon", "polyline", "m_poly", "m_area", "m_angle", "m_perimeter", "m_volume"}
# While one of these drawing tools is active, clicking an existing markup selects it for
# moving / resizing / restyling (like the Select tool) instead of starting a new one.
EDIT_IN_PLACE = {"rect", "ellipse", "cloud", "line", "arrow", "polygon", "polyline", "ink",
                 "textbox", "callout", "note", "stamp", "m_length", "m_poly", "m_area", "m_count",
                 "m_angle", "m_radius", "m_perimeter", "m_volume", "image", "attach", "placeholder"}
MEASURE_TOOLS = {"m_length", "m_calibrate", "m_poly", "m_area", "m_angle", "m_radius",
                 "m_perimeter", "m_volume"}
FORM_TOOLS = {"f_text", "f_check", "f_radio", "f_combo", "f_sign", "f_initials"}
SIGN_TOOLS = {"signature", "initials"}
HANDLE = 7          # handle size in px
FULL_LIMIT = 16_000_000     # device pixels: above this a page is drawn in tiles ...
FULL_MIN = 4_000_000        # ... and above this too when it's more than FULL_SCREENS
FULL_SCREENS = 2.5          #     windowfuls (see PageWidget._tiled)
HEAVY_S = 0.1               # a page whose content takes this long to render is drawn after
                            # showing it as it was (scaled), not while the window waits
PREDECODE_AFTER_S = 0.25    # tiles this slow on a page with big pictures: decode them once
SMALL_PREVIEW = 400         # px: the small copy of a page's bitmap kept once it's let go ...
SMALL_PREVIEWS = 40         # ... for this many pages
TILE = 512                  # tile size in device pixels
TILE_LIMIT = 160            # tiles kept in memory per document (~125 MB)
CARD_W = 190        # comment box width in px
ROT_GAP = 26        # rotation handle distance above the selection, px
# tools whose points snap (to the grid / to objects) while drawing
SNAP_TOOLS = (SHAPE_TOOLS - {"eraser", "erasecontent", "capture", "crop", "link"}) | POLY_TOOLS | {"stamp", "note", "m_count", "attach"}
STRAIGHT_TOOLS = {"line", "arrow", "m_length", "m_calibrate", "m_radius", "callout"}   # Shift = 45° steps
SQUARE_TOOLS = {"rect", "ellipse", "cloud"}                               # Shift = square / circle


def box_handles(r, h=HANDLE):
    """{id: QRectF} the eight resize handles (corners and sides) of screen rect r."""
    c = r.center()
    pts = {"tl": r.topLeft(), "tr": r.topRight(), "bl": r.bottomLeft(), "br": r.bottomRight(),
           "t": QPointF(c.x(), r.top()), "b": QPointF(c.x(), r.bottom()),
           "l": QPointF(r.left(), c.y()), "r": QPointF(r.right(), c.y())}
    return {k: QRectF(v.x() - h / 2, v.y() - h / 2, h, h) for k, v in pts.items()}


def handle_cursor(hid):
    """Mouse cursor over a handle: resize arrows, a hand for rotation, a cross for points."""
    return (Qt.SizeFDiagCursor if hid in ("tl", "br") else
            Qt.SizeBDiagCursor if hid in ("tr", "bl") else
            Qt.SizeVerCursor if hid in ("t", "b") else
            Qt.SizeHorCursor if hid in ("l", "r") else
            Qt.PointingHandCursor if hid == "rot" else Qt.CrossCursor)


def snap45(a, b):
    """b moved so the line a->b runs at a multiple of 45 degrees (same length)."""
    d = b - a
    length = math.hypot(d.x(), d.y())
    if length == 0:
        return QPointF(b)
    ang = round(math.atan2(d.y(), d.x()) / (math.pi / 4)) * (math.pi / 4)
    return a + QPointF(math.cos(ang) * length, math.sin(ang) * length)


def square_corner(a, b):
    """b moved so the box a-b is a square."""
    d = b - a
    side = max(abs(d.x()), abs(d.y()))
    return a + QPointF(side if d.x() >= 0 else -side, side if d.y() >= 0 else -side)


def shift_held(e):
    return bool(e.modifiers() & Qt.ShiftModifier)


def ctrl_held(e):
    return bool(e.modifiers() & Qt.ControlModifier)


def alt_held(e):
    return bool(e.modifiers() & Qt.AltModifier)



HIT_FRAME_MIN = (36, 24)    # px: the frame around the current search match never gets smaller


def hit_frame(rect):
    """The frame drawn around the current search match: the match's screen rect with a
    little padding, widened to HIT_FRAME_MIN around its center when the text is small."""
    r = QRectF(rect).adjusted(-3, -3, 3, 3)
    w, h = max(r.width(), HIT_FRAME_MIN[0]), max(r.height(), HIT_FRAME_MIN[1])
    c = r.center()
    return QRectF(c.x() - w / 2, c.y() - h / 2, w, h)

THIN_LINE_PX = 1.0          # Enhance thin lines: no line drawn on screen narrower than this


class screen_lines:
    """While a page is drawn on screen: with Enhance thin lines on, every line is at least
    THIN_LINE_PX device pixels wide, so the hairlines of CAD drawings don't fade to pale gray
    when zoomed out (as Acrobat's Enhance thin lines). The setting is the rendering engine's,
    for the whole program, so it's reset right after: printing, export, OCR and Compare keep
    the true line widths."""

    def __init__(self, on):
        self.on = on

    def __enter__(self):
        if self.on:
            pymupdf.TOOLS.set_graphics_min_line_width(THIN_LINE_PX)

    def __exit__(self, *exc):
        if self.on:
            pymupdf.TOOLS.set_graphics_min_line_width(0)
        return False


def night_samples(samples, width, height, stride):
    """Night mode (CAD style): the page's lightness is inverted and its hues kept, so a black
    line on white paper becomes a white line on black, red stays red, a yellow highlight stays
    yellow. Per pixel: add (255 - max - min) to every channel. RGB bytes in, RGB bytes out
    (tightly packed)."""
    return _night_array(samples, width, height, stride).tobytes()


def _night_array(samples, width, height, stride):
    """night_samples as a (height, width, 3) array of bytes. Worked in bytes, not wider
    numbers (casting a big page to 16 bits and back took most of a second): a channel c
    between the pixel's min and max becomes (c - min) + (255 - max), never below 0 or
    above 255."""
    import numpy as np
    a = np.frombuffer(samples, dtype=np.uint8)
    rows = a[: height * stride].reshape(height, stride)[:, : width * 3].reshape(height, width, 3)
    r, g, b = rows[:, :, 0], rows[:, :, 1], rows[:, :, 2]
    mx = np.maximum(np.maximum(r, g), b)
    mn = np.minimum(np.minimum(r, g), b)
    out = rows - mn[:, :, None]
    np.subtract(255, mx, out=mx)
    out += mx[:, :, None]
    return out


def lines_path(lines):
    """Lines (lists of points) as one QPainterPath, in their own coordinates. Each piece is
    on its own, so the path draws exactly as one drawLine per piece did (dashes start again
    on each piece), but in one call: drawing a big selection a piece at a time from Python
    took most of a second on each mouse move."""
    path = QPainterPath()
    move, to = path.moveTo, path.lineTo
    for line in lines:
        for a, b in zip(line, line[1:]):
            move(a[0], a[1])
            to(b[0], b[1])
    return path


def tile_span(rect, dpr):
    """(tx0, ty0, tx1, ty1): the tiles holding every device pixel the widget area rect (a
    QRect, whole widget pixels) touches at dpr device pixels per widget pixel: at 150% a
    widget pixel covers a device pixel and a half, and the last one, partly covered, may be
    the first of the next tile (left unpainted, it kept what was on the screen before)."""
    return (int(rect.left() * dpr) // TILE, int(rect.top() * dpr) // TILE,
            (math.ceil((rect.right() + 1) * dpr - 1e-6) - 1) // TILE,
            (math.ceil((rect.bottom() + 1) * dpr - 1e-6) - 1) // TILE)


def check_content(view, i, force=False):
    """Before page i's kept content (display list, renders) is used after it may have
    changed (an edit, an undo, a layer shown): keep it if the page's content key is the one
    it was made from, else let it go."""
    rc = view._rc
    if not force and i not in rc.recheck:
        return
    rc.recheck.discard(i)
    old = rc.keys.get(i)
    if old is None:
        if i in view._dlists or rc.has_page(i):
            view._dlists.pop(i, None)
            rc.drop_page(i)
        return
    if i not in view._dlists and not rc.has_page(i) and \
            not any(k[0] == i for k in view._tiles):
        # nothing drawn from it is kept any more (scrolled far away): its key is let go
        # rather than read again to compare (a layer shown, Show markups, or an edit seen by
        # the split view checks every page: 300 heavy sheets visited, 0.1-0.2 s each time)
        new = None
    else:
        try:
            new = RL.content_key(view.doc[i])
        except Exception:
            new = None
    if new is None or new != old:
        view._dlists.pop(i, None)
        rc.drop_page(i)
        view._img_info.pop(i, None)
        view._img_big.pop(i, None)
        view._decoded = {d for d in view._decoded if d[0] != i}
        for key in [k for k in view._tiles if k[0] == i]:
            del view._tiles[key]
        if new is None:
            rc.keys.pop(i, None)
        else:
            rc.keys[i] = new


def thumbnail(view, i, s):
    """Page i at zoom s for the page list, as a QImage: scaled down from the page's content
    render on screen when there is one (with the markups drawn over it), else rendered from
    its parsed drawing when it was parsed, else from the page (as before)."""
    page = view.doc[i]
    check_content(view, i)
    rc = view._rc
    size = (page.rect * pymupdf.Matrix(s, s)).round()
    best = None
    for (pi, ps, tile, _thin), pm in rc.renders.items():
        if pi == i and tile is None and ps >= s and (best is None or ps < best[0]):
            best = (ps, pm)
    al = RL.annots_list(page) if best is not None or i in view._dlists else None
    if best is not None:
        ps, pm = best
        if al is not None:
            pm = RL.draw_over(pm, al, ps)
        img = QImage(pm.samples_mv, pm.width, pm.height, pm.stride, QImage.Format_RGB888)
        return img.scaled(size.width, size.height, Qt.IgnoreAspectRatio,
                          Qt.SmoothTransformation)
    dl = view._dlists.get(i)
    if dl is not None:
        pm = RL.render(dl, s)
        if al is not None:
            pm = RL.draw_over(pm, al, s)
    else:
        pm = page.get_pixmap(matrix=pymupdf.Matrix(s, s), annots=True)
    return QImage(pm.samples, pm.width, pm.height, pm.stride, QImage.Format_RGB888).copy()


class PageWidget(QWidget):
    def __init__(self, view, index):
        super().__init__()
        self.view = view
        self.index = index
        self._reset_state()
        self.setMouseTracking(True)
        self.setAttribute(Qt.WA_OpaquePaintEvent)
        self.update_size()

    def reuse(self, index):
        """Take over page index after pages were added, removed, moved or rotated: a
        rebuild renumbers the existing widgets instead of making 2,000 new ones."""
        self.index = index
        for child in self.findChildren(QWidget, options=Qt.FindDirectChildrenOnly):
            child.deleteLater()             # an on-page text editor from before
        self._reset_state()
        self.update_size()
        self.update()

    def _reset_state(self):
        self._pix = None
        self._preview = None        # (QPixmap, page rect): the page as last drawn whole
        self._tile_scale = None     # the scale its tiles were last drawn at
        self._failed = set()        # tiles MuPDF couldn't draw: (scale, tx, ty)
        self._drag_start = None     # shape tools / box selection
        self._drag_now = None
        self._text_sel = None       # (mode, words) while selecting text
        self._text_mode = None      # "text" or "box" for the drag in progress
        self._ink = []
        self._hover = None          # edit-text hover rect
        self._edit = None           # dragging a selected annotation
        self._cards = []            # [(QRectF, xref)] comment boxes drawn last paint
        self._ghost = None          # signature / stamp preview position (widget coords)
        self._poly = []             # polygon / polyline points so far (widget coords)
        self._poly_hover = None
        self._marquee = False       # Ctrl+drag with Select: selection box only, no text
        self._cad_down = None       # CAD mode: a press with Select / Edit objects (cad_select.py)
        self._snap_mark = None      # (widget point, "object" | "page" | "grid") last snap
        self._obj_hover = None      # Edit objects: picture under the mouse
        self._obj_edit = None       # Edit objects: dragging / resizing the selected picture
        self._text_move = None      # Edit text: a line being dragged to a new place
        self._sig_drag = None       # signature / initials: press point while sizing
        self._sig_now = None

    # ---- geometry -------------------------------------------------------
    def update_size(self):
        r = self.view.page_rects[self.index]
        z = self.view.zoom
        size = (max(1, int(r.width * z)), max(1, int(r.height * z)))
        if self._pix is not None and size != (self.width(), self.height()):
            # (a new zoom: the page as it was is shown, scaled, until it's drawn sharp again)
            self._preview = (self._pix, r)
        self.setFixedSize(*size)
        self._pix = None

    def invalidate(self):
        """The page changed: its markups are drawn again; its content too if that changed
        (its content key is no longer the same: an erase, a redaction, a text edit...), else
        its content render is reused (a markup added, moved, restyled or deleted)."""
        self._pix = None
        self._preview = None
        self._failed = set()
        v = self.view
        v._small_previews.pop(self.index, None)
        v._alists.pop(self.index, None)
        self._drop_tiles()
        check_content(v, self.index, force=True)
        self.update()

    def drop_cache(self):
        """Far from the window: let the page's bitmaps go (memory). A small copy is kept
        for a while: scrolled back to, a heavy page is shown with it until drawn sharp."""
        pv = self._preview
        if pv is not None and pv[0].width() * pv[0].height() > 0:
            small = pv[0].scaled(SMALL_PREVIEW, SMALL_PREVIEW, Qt.KeepAspectRatio,
                                 Qt.SmoothTransformation)
            keep = self.view._small_previews
            keep[self.index] = (small, pv[1])
            keep.move_to_end(self.index)
            while len(keep) > SMALL_PREVIEWS:
                keep.popitem(last=False)
        self._pix = None
        self._preview = None
        self.view._rc.drop_page(self.index, whole_only=True)

    def redraw(self):
        """A display option changed (night mode, thin lines): draw the page again, from its
        content render when it has one for the option."""
        self._pix = None
        self._preview = None

    def _drop_tiles(self):
        tiles = self.view._tiles
        for key in [k for k in tiles if k[0] == self.index]:
            del tiles[key]

    def _display_list(self):
        """The page's content (without its markups) parsed once, as a DisplayList, and reused
        for every render and tile while the content stays the same."""
        v = self.view
        check_content(v, self.index)
        dl = v._dlists.get(self.index)
        if dl is None:
            page = v.doc[self.index]
            if self.index not in v._rc.keys:
                v._rc.keys[self.index] = RL.content_key(page)
            dl = page.get_displaylist(annots=False)
            v._dlists[self.index] = dl
        return dl

    def _annots(self):
        """The page's markups and form fields as a DisplayList (None: none to draw, or
        View > Show markups off)."""
        v = self.view
        if not v.show_markups:
            return None
        if self.index not in v._alists:
            v._alists[self.index] = RL.annots_list(v.doc[self.index])
        return v._alists[self.index]

    def _content(self, s, clip=None, tile=None):
        """The page's content rendered at zoom s (device pixels per point), whole or the clip,
        as a pymupdf.Pixmap: the one kept from before when there is one."""
        v = self.view
        check_content(v, self.index)
        thin = v.thin_lines
        pm = v._rc.get(self.index, s, tile, thin)
        if pm is None:
            dl = self._display_list()
            t = time.perf_counter()
            with screen_lines(thin):
                pm = RL.render(dl, s, clip)
            v._note_render_cost(self.index, time.perf_counter() - t)
            v._rc.put(self.index, s, tile, thin, pm)
        return pm

    def _with_markups(self, base, s, clip=None):
        """base (the content at zoom s) with the markups drawn over it by MuPDF (blend modes,
        opacity and all, as a whole-page render draws them)."""
        al = self._annots()
        if al is None:
            return base
        with screen_lines(self.view.thin_lines):
            return RL.draw_over(base, al, s, clip)

    def _to_qimage(self, pm):
        """pm as a 32-bit QImage of its own (night mode applied)."""
        # one copy of the pixels, not three: the image is read in place from the rendered
        # pixmap (or night mode's array), both kept alive here until the conversion to
        # 32 bits has made Qt's own copy. (Not .copy() then fromImage: Qt keeps an image
        # of the screen's own format as it is, so it would go on pointing into this memory.)
        if self.view.night_mode:
            data = _night_array(pm.samples_mv, pm.width, pm.height, pm.stride)
            img = QImage(data.data, pm.width, pm.height, pm.width * 3, QImage.Format_RGB888)
        else:
            data = pm.samples_mv
            img = QImage(data, pm.width, pm.height, pm.stride, QImage.Format_RGB888)
        return img.convertToFormat(QImage.Format_RGB32)

    def _to_qpixmap(self, pm, dpr):
        pix = QPixmap.fromImage(self._to_qimage(pm))
        pix.setDevicePixelRatio(dpr)
        return pix

    def _tiled(self):
        """Drawn in tiles (only what's in view) rather than as one bitmap: a page bigger than
        FULL_LIMIT device pixels, or bigger than FULL_MIN and FULL_SCREENS windowfuls (a heavy
        drawing at 400% isn't rendered whole to show a corner of it)."""
        dpr = self.devicePixelRatioF()
        px = self.width() * self.height() * dpr * dpr
        if px <= FULL_MIN:
            return False
        if px > FULL_LIMIT:
            return True
        vp = self.view.viewport()
        return px > FULL_SCREENS * vp.width() * vp.height() * dpr * dpr

    def _paint_tiles(self, p, exposed):
        """Large page at high zoom: draw only the visible area, in cached tiles. Missing tiles
        are rendered together (MuPDF reads the drawing once for all of them); on a heavy page
        with something to show meanwhile (the page as it was, scaled) they're drawn a moment
        later instead (DocumentView._render_tick), so zooming and scrolling don't wait."""
        dpr = self.devicePixelRatioF()
        s = self.view.zoom * dpr
        s5 = round(s, 5)
        full = pymupdf.IRect(0, 0, int(self.width() * dpr), int(self.height() * dpr))
        tiles = self.view._tiles
        rc = self.view._rc
        thin = self.view.thin_lines
        check_content(self.view, self.index)
        tx0, ty0, tx1, ty1 = tile_span(exposed, dpr)
        missing = []
        for ty in range(ty0, ty1 + 1):
            for tx in range(tx0, tx1 + 1):
                key = (self.index, s5, tx, ty)
                hit = tiles.get(key)
                if hit is None:
                    dev = pymupdf.IRect(tx * TILE, ty * TILE, (tx + 1) * TILE, (ty + 1) * TILE) & full
                    if dev.is_empty:
                        continue
                    if (s5, tx, ty) in self._failed:
                        p.fillRect(QRectF(dev.x0 / dpr, dev.y0 / dpr, dev.width / dpr,
                                          dev.height / dpr), Qt.white)
                        continue
                    raw = rc.get(self.index, s, (tx, ty), thin)
                    if raw is None:
                        missing.append((tx, ty, dev))
                        continue
                    try:            # (the content kept: only the markups are drawn again)
                        clip = pymupdf.Rect(dev) / s
                        pix = self._to_qpixmap(self._with_markups(raw, s, clip), dpr)
                        hit = (pix, dev.x0, dev.y0)
                    except Exception:
                        missing.append((tx, ty, dev))
                        continue
                    self._keep_tile(key, hit)
                else:
                    tiles.move_to_end(key)
                pix, x, y = hit
                p.drawPixmap(QPointF(x / dpr, y / dpr), pix)
        if missing:
            if self._defer(s):
                self._paint_preview(p, [QRectF(d.x0 / dpr, d.y0 / dpr, d.width / dpr,
                                               d.height / dpr) for _tx, _ty, d in missing], s)
                self.view._render_later(self)
                return
            for key, hit in self._render_tiles(missing, s, dpr):
                if hit is None:
                    d = key
                    p.fillRect(QRectF(d.x0 / dpr, d.y0 / dpr, d.width / dpr, d.height / dpr),
                               Qt.white)
                    continue
                pix, x, y = hit
                p.drawPixmap(QPointF(x / dpr, y / dpr), pix)
        self._tile_scale = s5

    def _keep_tile(self, key, hit):
        tiles = self.view._tiles
        tiles[key] = hit
        while len(tiles) > TILE_LIMIT:
            tiles.popitem(last=False)

    def _render_tiles(self, missing, s, dpr):
        """Render the tiles [(tx, ty, device rect)]: their content in one go (or a row at a
        time when they're scattered), cut into tiles, the markups drawn over. Yields
        (key, (QPixmap, x, y)), or (device rect, None) for a tile that couldn't be drawn."""
        v = self.view
        s5 = round(s, 5)
        cols = {tx for tx, _ty, _d in missing}
        rows = {ty for _tx, ty, _d in missing}
        if (max(cols) - min(cols) + 1) * (max(rows) - min(rows) + 1) <= 2 * len(missing):
            batches = [missing]
        else:
            batches = [[m for m in missing if m[1] == ty] for ty in sorted(rows)]
        if self.index in v._img_info:
            self._predecode(s)
        for batch in batches:
            box = batch[0][2]
            for _tx, _ty, d in batch[1:]:
                box = box | d
            clip = pymupdf.Rect(box) / s
            try:
                dl = self._display_list()
                t = time.perf_counter()
                with screen_lines(v.thin_lines):
                    pm = RL.render(dl, s, clip)
                took = time.perf_counter() - t
                v._note_render_cost(self.index, took)
                if took >= PREDECODE_AFTER_S and self.index not in v._img_info:
                    # slow: if it's a big picture decoded again for each piece, decode it once
                    # now (and before the tiles of every other zoom of this page)
                    self._predecode(s)
                img = self._to_qimage(self._with_markups(pm, s, clip))
            except Exception:
                for tx, ty, d in batch:
                    self._failed.add((s5, tx, ty))
                    yield d, None
                continue
            for tx, ty, d in batch:
                v._rc.put(self.index, s, (tx, ty), v.thin_lines,
                          pm if len(batch) == 1 else RL.cut(pm, d))
                part = img if len(batch) == 1 else \
                    img.copy(d.x0 - pm.x, d.y0 - pm.y, d.width, d.height)
                pix = QPixmap.fromImage(part)
                pix.setDevicePixelRatio(dpr)
                hit = (pix, d.x0, d.y0)
                key = (self.index, s5, tx, ty)
                self._keep_tile(key, hit)
                yield key, hit

    def _predecode(self, s):
        """A scanned page at high zoom: its big pictures decoded once, at the size the tiles
        need, so each tile doesn't decode the whole JPEG again (render_layers.predecode).
        (Where they're drawn is read once per page, after a slow render: reading it runs the
        page's drawing, a fifth of a second on a heavy sheet.)"""
        v = self.view
        page = v.doc[self.index]
        info = v._img_info.get(self.index)
        if info is None:
            info = []
            big = self._big_images()
            try:
                # (matched by size: asking for xrefs has PyMuPDF checksum every picture)
                shown = page.get_image_info() if big else []
            except Exception:
                shown = []
            for xref, w, h, nbytes in big:
                sizes = [(math.hypot(t[0], t[1]), math.hypot(t[2], t[3]))
                         for t in (x["transform"] for x in shown
                                   if x["width"] == w and x["height"] == h)]
                if sizes:
                    info.append((xref, w, h, nbytes, max(a for a, _b in sizes),
                                 max(b for _a, b in sizes)))
            v._img_info[self.index] = info
        todo = []
        for xref, w, h, nbytes, rw, rh in info:
            # (MuPDF decodes a picture drawn smaller at 1/2, 1/4... of its size)
            dw, dh = max(1.0, rw * s), max(1.0, rh * s)
            n = 0
            while n < 6 and (w >> (n + 1)) >= dw and (h >> (n + 1)) >= dh:
                n += 1
            if (nbytes >> (2 * n)) > RL.DECODE_LIMIT or (self.index, xref, n) in v._decoded:
                continue
            v._decoded.add((self.index, xref, n))
            todo.append((xref, dw, dh))
        if todo:
            RL.predecode(page, todo)

    def _defer(self, s):
        """Show something now (the page as it was, scaled) and render it sharp a moment later
        instead of making the window wait: while Ctrl+wheel zooming, and for a heavy page."""
        v = self.view
        if not v.progressive:
            return False
        # (a page with big pictures counts as heavy: its next zoom may need them decoded
        # at another size, however quick it was the last time)
        heavy = v._render_cost(self.index) >= HEAVY_S or bool(self._big_images())
        if v._zooming:
            return heavy or self._preview_source() is not None
        return heavy and self._preview_source() is not None

    def _big_images(self):
        v = self.view
        big = v._img_big.get(self.index)
        if big is None:
            big = v._img_big[self.index] = RL.big_images(v.doc[self.index])
        return big

    def _preview_source(self):
        """What a page not yet drawn at this zoom is shown with: its last bitmap (at another
        zoom), else its thumbnail from the page list; None when there's neither."""
        rect = self.view.page_rects[self.index]
        for pv in (self._preview, self.view._small_previews.get(self.index)):
            if pv is not None and pv[1] == rect:
                return pv[0]
        if self.view.night_mode:
            return None                 # (the thumbnails aren't in night colors)
        try:
            got = self.view.thumb_icons.get(self.view.doc.page_xref(self.index))
        except Exception:
            got = None
        if got and got[1]:
            sizes = got[0].availableSizes()
            if sizes:
                return got[0].pixmap(max(sizes, key=lambda z: z.width()))
        return None

    def _paint_preview(self, p, rects, s):
        """Fill rects (widget coordinates) with the page as last drawn: tiles of the zoom it
        was last shown at, over its last bitmap (or its thumbnail), scaled to this zoom; the
        paper color where there's neither."""
        p.save()
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        area = QPainterPath()
        for r in rects:
            area.addRect(r)
        p.setClipPath(area, Qt.IntersectClip)
        paper = Qt.black if self.view.night_mode else Qt.white
        src = self._preview_source()
        if src is None:
            for r in rects:
                p.fillRect(r, paper)
        else:
            p.drawPixmap(QRectF(0, 0, self.width(), self.height()), src,
                         QRectF(0, 0, src.width(), src.height()))
        old = getattr(self, "_tile_scale", None)
        if old and abs(old - round(s, 5)) > 1e-9:
            f = s / old
            dpr = self.devicePixelRatioF()
            bound = area.boundingRect()
            for (i, sc, _tx, _ty), (pix, x, y) in list(self.view._tiles.items()):
                if i != self.index or sc != old:
                    continue
                r = QRectF(x * f / dpr, y * f / dpr, pix.width() * f / dpr,
                           pix.height() * f / dpr)
                if r.intersects(bound):
                    p.drawPixmap(r, pix, QRectF(0, 0, pix.width(), pix.height()))
        p.restore()

    def render_step(self):
        """Draw what's waiting to be drawn sharp on this page (DocumentView._render_tick):
        the whole bitmap, or the missing tiles in view. Returns False when there was nothing
        to do."""
        v = self.view
        if v.doc.is_closed or self.index >= v.doc.page_count:
            return False
        vis = self.visibleRegion().boundingRect()
        if vis.isEmpty():
            return False
        if not self._tiled():
            if self._pix is not None:
                return False
            try:
                self._render()
            except Exception:
                return False
            self.update()
            return True
        dpr = self.devicePixelRatioF()
        s = v.zoom * dpr
        s5 = round(s, 5)
        full = pymupdf.IRect(0, 0, int(self.width() * dpr), int(self.height() * dpr))
        tx0, ty0, tx1, ty1 = tile_span(vis, dpr)
        missing = []
        for ty in range(ty0, ty1 + 1):
            for tx in range(tx0, tx1 + 1):
                if (self.index, s5, tx, ty) in v._tiles or (s5, tx, ty) in self._failed or \
                        v._rc.get(self.index, s, (tx, ty), v.thin_lines) is not None:
                    continue
                dev = pymupdf.IRect(tx * TILE, ty * TILE, (tx + 1) * TILE, (ty + 1) * TILE) & full
                if not dev.is_empty:
                    missing.append((tx, ty, dev))
        if not missing:
            return False
        for _key, _hit in self._render_tiles(missing, s, dpr):
            pass
        self.update()
        return True

    def to_pdf(self, pos):
        """Widget position -> unrotated PDF point (what PyMuPDF expects)."""
        page = self.view.doc[self.index]
        z = self.view.zoom
        return pymupdf.Point(pos.x() / z, pos.y() / z) * page.derotation_matrix

    def to_screen(self, rect, page=None):
        """Unrotated PDF rect -> widget QRectF."""
        page = page or self.view.doc[self.index]
        r = pymupdf.Rect(rect) * page.rotation_matrix
        z = self.view.zoom
        return QRectF(r.x0 * z, r.y0 * z, r.width * z, r.height * z)

    def to_screen_pt(self, pt, page=None):
        page = page or self.view.doc[self.index]
        q = pymupdf.Point(pt) * page.rotation_matrix
        return QPointF(q.x * self.view.zoom, q.y * self.view.zoom)

    # ---- painting -------------------------------------------------------
    def _render(self):
        """The whole page at the current zoom as one bitmap: its content (kept from before
        when it's the same) with its markups drawn over it."""
        dpr = self.devicePixelRatioF()
        s = self.view.zoom * dpr
        pm = self._with_markups(self._content(s), s)
        self._pix = self._to_qpixmap(pm, dpr)
        self._preview = (self._pix, self.view.page_rects[self.index])
        self.view._pix_pages.add(self.index)

    def paintEvent(self, event):
        p = QPainter(self)
        if self.view.doc.is_closed or self.index >= self.view.doc.page_count:
            # tab closing, or a widget of a page that was just deleted (its deleteLater is
            # still queued): a repaint must not touch the document
            p.fillRect(event.rect(), Qt.white)
            return
        if self._tiled():
            self._pix = None
            self._paint_tiles(p, event.rect())
        else:
            if self._pix is None:
                s = self.view.zoom * self.devicePixelRatioF()
                check_content(self.view, self.index)
                if self.view._rc.get(self.index, s, None, self.view.thin_lines) is None \
                        and self._defer(s):
                    self._paint_preview(p, [QRectF(event.rect())], s)
                    self.view._render_later(self)
                else:
                    try:
                        self._render()
                    except Exception:
                        p.fillRect(self.rect(), Qt.white)
                        return
            if self._pix is not None:
                p.drawPixmap(0, 0, self._pix)
        page = self.view.doc[self.index]
        if self.view.grid_on:
            self._paint_grid(p, QRectF(event.rect()))
        p.setRenderHint(QPainter.Antialiasing)

        hits = self.view.search_hits.get(self.index)
        if hits:
            cur = self.view.current_hit()
            # (a match can be more than one rect: a word split at a line's end)
            mine = {id(r) for r in self.view.hit_rects(cur)} \
                if cur is not None and cur[0] == self.index else set()
            for r in hits:
                active = id(r) in mine
                color = QColor(255, 120, 0, 120) if active else QColor(255, 230, 0, 90)
                sr = self.to_screen(r, page)
                p.fillRect(sr, color)
                if active:
                    # the match you're on gets a bold frame that stays at least a thumb's
                    # size on screen, so it's easy to spot when zoomed out and the text is tiny
                    frame = hit_frame(sr)
                    p.setPen(QPen(QColor(255, 255, 255, 200), 5))
                    p.drawRect(frame)
                    p.setPen(QPen(QColor(255, 90, 0), 2.5))
                    p.drawRect(frame)

        self._paint_comment_cards(p, page)

        if self.view.highlight_fields and self.view.tool not in FORM_TOOLS:
            # shade fillable fields (screen only) with a blue outline so they stand out even
            # on colored forms; required ones get a red outline
            for r, required in self.view.field_rects(self.index):
                sr = self.to_screen(r, page)
                p.fillRect(sr, QColor(160, 185, 255, 130))
                p.setPen(QPen(QColor(220, 0, 0) if required else QColor(30, 90, 220),
                              2 if required else 1.5))
                p.drawRect(sr.adjusted(0.5, 0.5, -0.5, -0.5))
            fr = self.view.field_focus_rect(self.index)
            if fr is not None:                  # the field Tab moved to
                p.setPen(QPen(QColor(255, 140, 0), 2.5))
                p.drawRect(self.to_screen(fr, page).adjusted(-2, -2, 2, 2))

        tool = self.view.tool
        self._paint_text_selection(p, page, tool)
        cad_select.paint(self, p)

        if tool in FORM_TOOLS:
            p.setPen(QPen(QColor(0, 90, 200), 1, Qt.DashLine))
            for wdg in page.widgets():
                r = self.to_screen(wdg.rect, page)
                p.drawRect(r)
                p.drawText(r.adjusted(2, -14, 200, 0).topLeft() + QPointF(0, 11), wdg.field_name or "")
        if self._drag_start is not None and self._drag_now is not None and tool in FORM_TOOLS:
            p.setPen(QPen(QColor(0, 90, 200), 1.5))
            p.setBrush(QColor(235, 242, 255, 160))
            p.drawRect(QRectF(self._drag_start, self._drag_now).normalized())
            p.setBrush(Qt.NoBrush)
        if self._poly:
            pen = QPen(self.view.tool_color(tool),
                       max(1.0, float(self.view.tool_props(tool).get("width", 2)) * self.view.zoom))
            p.setPen(pen)
            pts = self._poly + ([self._poly_hover] if self._poly_hover is not None else [])
            for a_, b_ in zip(pts, pts[1:]):
                p.drawLine(a_, b_)
            if tool in ("polygon",) + A.CLOSED_MEASURES and len(pts) > 2:
                p.setPen(QPen(self.view.tool_color(tool), 1, Qt.DashLine))
                p.drawLine(pts[-1], pts[0])
            if tool in MEASURE_TOOLS:
                self._draw_readout(p, pts)
        if self._ghost is not None and tool == "stamp":
            pm = self.view.stamp_preview()
            if pm is not None:
                r = self.view.stamp_rect(self.index, self.to_pdf(self._ghost))
                rr = self.to_screen(r)
                p.setOpacity(0.6)
                p.drawPixmap(rr, pm, QRectF(pm.rect()))
                p.setOpacity(1.0)
        if self._sig_drag is not None and tool in SIGN_TOOLS:
            r = self._sig_box()
            pm = self.view.sig_pixmap(tool)
            if r is not None and pm is not None:
                z = self.view.zoom
                p.setOpacity(0.7)
                p.drawPixmap(QRectF(r.x0 * z, r.y0 * z, r.width * z, r.height * z), pm,
                             QRectF(pm.rect()))
                p.setOpacity(1.0)
                p.setPen(QPen(QColor(0, 120, 215), 1, Qt.DashLine))
                p.drawRect(QRectF(r.x0 * z, r.y0 * z, r.width * z, r.height * z))
        elif self._ghost is not None and tool in SIGN_TOOLS:
            pm = self.view.sig_pixmap(tool)
            if pm is not None:
                r = self.view.sig_display_rect(self.index, tool, self.to_pdf(self._ghost))
                z = self.view.zoom
                p.setOpacity(0.6)
                p.drawPixmap(QRectF(r.x0 * z, r.y0 * z, r.width * z, r.height * z), pm,
                             QRectF(pm.rect()))
                p.setOpacity(1.0)
        if self._drag_start is not None and self._drag_now is not None and tool in SHAPE_TOOLS:
            if tool == "eraser":
                pen = QPen(QColor(220, 0, 0), 1.5, Qt.DashLine)
            else:
                pen = QPen(self.view.tool_color(tool),
                           max(1.0, float(self.view.tool_props(tool).get("width", 1)) * self.view.zoom))
            p.setPen(pen)
            if tool in ("line", "arrow", "m_length", "m_calibrate", "m_radius"):
                p.drawLine(self._drag_start, self._drag_now)
                if tool == "m_radius":
                    d = self._drag_now - self._drag_start
                    r = (d.x() ** 2 + d.y() ** 2) ** 0.5
                    p.drawEllipse(self._drag_start, r, r)
                if tool in MEASURE_TOOLS:
                    self._draw_readout(p, [self._drag_start, self._drag_now])
            elif tool == "callout":
                p.drawLine(self._drag_start, self._drag_now)
                p.drawRect(QRectF(self._drag_now, self._drag_now + QPointF(160, 40) * self.view.zoom))
            elif tool == "ellipse":
                p.drawEllipse(QRectF(self._drag_start, self._drag_now).normalized())
            else:
                p.drawRect(QRectF(self._drag_start, self._drag_now).normalized())

        if tool == "editobjects":
            self._paint_objects(p, page)
        self._paint_link_borders(p)
        if tool == "link":
            # the page's links, outlined so they can be found and clicked to change them
            p.setPen(QPen(QColor(0, 90, 220), 1, Qt.DashLine))
            p.setBrush(QColor(0, 90, 220, 28))
            z = self.view.zoom
            for r, _ln in self.view.links(self.index):
                p.drawRect(QRectF(r.x0 * z, r.y0 * z, r.width * z, r.height * z))
            p.setBrush(Qt.NoBrush)

        tm = self._text_move
        if tm is not None and tm["now"] is not None and tm["pix"] is not None:
            d = tm["now"] - tm["start"]
            p.drawPixmap(tm["box"].topLeft() + d, tm["pix"])
            p.setPen(QPen(QColor(0, 120, 215), 1, Qt.DashLine))
            p.drawRect(tm["box"].translated(d))

        if self._hover is not None and tool == "edittext":
            p.setPen(QPen(QColor(0, 120, 215), 1, Qt.DashLine))
            p.drawRect(self.to_screen(self._hover).adjusted(-2, -2, 2, 2))

        if len(self._ink) > 1:
            p.setPen(QPen(self.view.tool_color("ink"),
                          max(1.0, float(self.view.tool_props("ink").get("width", 2)) * self.view.zoom),
                          Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            path = QPainterPath(self._ink[0])
            for pt in self._ink[1:]:
                path.lineTo(pt)
            p.drawPath(path)

        self._paint_selection(p, page)
        if self.view._cad_cmd is not None:
            self.view._cad_cmd.paint(self, p)
        self._paint_snap_mark(p)

        if self.view.current_page() == self.index and self.view.page_count() > 1:
            p.setPen(QPen(QColor(0, 120, 215), 1))
            p.setBrush(Qt.NoBrush)
            p.drawRect(self.rect().adjusted(0, 0, -1, -1))

    def _paint_text_selection(self, p, page, tool):
        """Blue highlight over text being dragged or already selected on this page.

        A drag can start on another page and cross the gap onto this one. A box drag also
        draws its dashed rectangle on the page where the drag began."""
        v = self.view
        words = []
        dragging = False
        for i, _mode, wds in (v._text_drag or []):
            if i == self.index:
                words = wds
                dragging = True
                break
        if not words and v.text_sel:
            for i, wds in v.text_sel:
                if i == self.index:
                    words = wds
                    break
        if words and (tool in TEXT_TOOLS or dragging):
            color = QColor(0, 120, 215, 80) if dragging else QColor(0, 120, 215, 70)
            for r in v.line_rects(words):
                p.fillRect(self.to_screen(r, page), color)
        # a box drag (empty space, or Ctrl) still draws its rectangle when it holds no words yet
        if (self._text_sel is not None and self._drag_start is not None
                and self._drag_now is not None and self._text_mode == "box"):
            p.setPen(QPen(QColor(0, 120, 215), 1, Qt.DashLine))
            p.drawRect(QRectF(self._drag_start, self._drag_now).normalized())

    def _selected_words(self):
        """Character units selected on this page (a finished selection, not a live drag)."""
        for i, words in (self.view.text_sel or []):
            if i == self.index:
                return words
        return []

    def _draw_readout(self, p, pts):
        """Live measurement next to the cursor while drawing."""
        if len(pts) < 2:
            return
        text = self.view.live_measure(self.index, self.view.tool, [self.to_pdf(q) for q in pts])
        if not text:
            return
        fm = QFontMetrics(self.font())
        lines = text.split("\n")
        w_ = max(fm.horizontalAdvance(t) for t in lines) + 10
        h_ = fm.lineSpacing() * len(lines) + 6
        at = pts[-1] + QPointF(14, 14)
        box = QRectF(at.x(), at.y(), w_, h_)
        p.setPen(QPen(QColor(0, 90, 200), 1))
        p.setBrush(QColor(255, 255, 255, 235))
        p.drawRoundedRect(box, 3, 3)
        p.setBrush(Qt.NoBrush)
        p.setPen(Qt.black)
        p.drawText(box.adjusted(5, 3, -5, -3), Qt.AlignLeft | Qt.AlignTop, text)

    def _paint_comment_cards(self, p, page):
        """Adobe-style note boxes beside commented text (drawn by us, not in the PDF)."""
        self._cards = []
        if not self.view.show_comment_boxes:
            return
        fm = QFontMetrics(self.font())
        for anchor, text, xref in self.view.comment_cards(self.index):
            a = self.to_screen(anchor, page)
            body = text if text.strip() else tr("(empty note)")
            br = fm.boundingRect(0, 0, CARD_W - 12, 2000, Qt.TextWordWrap, body)
            h = min(br.height(), fm.lineSpacing() * 6) + 10
            x = a.right() + 14
            if x + CARD_W > self.width():
                x = max(2, self.width() - CARD_W - 2)
                y = a.bottom() + 6
            else:
                y = a.top()
            card = QRectF(x, y, CARD_W, h)
            sel = self.view.selection == (self.index, xref)
            p.setPen(QPen(QColor(180, 150, 0), 1, Qt.DotLine))
            p.drawLine(QPointF(a.right(), a.center().y()), QPointF(card.left(), card.top() + 8))
            p.setPen(QPen(QColor(0, 120, 215) if sel else QColor(190, 160, 0), 2 if sel else 1))
            p.setBrush(QColor(255, 248, 196, 235))
            p.drawRoundedRect(card, 4, 4)
            p.setPen(Qt.black)
            p.drawText(card.adjusted(6, 5, -6, -5), Qt.TextWordWrap, body)
            self._cards.append((card, xref))
        p.setBrush(Qt.NoBrush)

    def _selected_here(self):
        sel = self.view.selection
        if sel is None or sel[0] != self.index or self.view.selected_model is None:
            return None
        return self.view.selected_model

    def _handles(self, model):
        """{id: QRectF} handle squares for the selected annotation (none when several are
        selected: then they move together)."""
        h = HANDLE
        if self.view.extra:
            return {}
        if model["kind"] in ("line", "arrow", "m_length", "m_radius"):
            out = {}
            for i, q in enumerate(model["points"]):
                s = self.to_screen_pt(q)
                out[f"p{i}"] = QRectF(s.x() - h / 2, s.y() - h / 2, h, h)
            out.update(self._rot_handle(model))
            return out
        if model["kind"] in A.VERTEXED:
            out = {}
            for i, q in enumerate(model["points"]):
                s = self.to_screen_pt(q)
                out[f"v{i}"] = QRectF(s.x() - h / 2, s.y() - h / 2, h, h)
            out.update(self._rot_handle(model))
            return out
        if not A.movable(model) or model["kind"] in ("note", "m_count", "attach"):
            return {}
        extra = {}
        if model["kind"] == "callout":
            s_ = self.to_screen_pt(model["points"][0])
            extra["p0"] = QRectF(s_.x() - h / 2, s_.y() - h / 2, h, h)
        out = box_handles(self.to_screen(A.bounds(model)))
        out.update(extra)
        out.update(self._rot_handle(model))
        return out

    def _rot_handle(self, model):
        """Round handle above the shape for free rotation (not text boxes: 90° steps only)."""
        if model["kind"] not in A.ROTATABLE or model["kind"] in A.QUARTER_TURNS or \
                self.view.extra:
            return {}
        r = self.to_screen(A.bounds(model))
        h = HANDLE + 2
        c = QPointF(r.center().x(), r.top() - ROT_GAP)
        return {"rot": QRectF(c.x() - h / 2, c.y() - h / 2, h, h)}

    def _paint_selection(self, p, page):
        model = self._selected_here()
        if model is None:
            return
        blue = QColor(0, 120, 215)
        p.setBrush(Qt.NoBrush)
        if self.view.extra:
            # several markups: their outlines follow the pointer while dragging. The outlines
            # are drawn once and slid; copying every markup on each move is what made a group
            # drag slow, and a box around each one looked empty.
            ed = self._edit
            if ed and ed.get("mode") == "group" and ed.get("ghost_path") is not None \
                    and ed.get("delta") is not None:
                origin = pymupdf.Point(0, 0)
                d = self.to_screen_pt(origin + ed["delta"], page) - self.to_screen_pt(origin, page)
                p.save()
                p.translate(d.x(), d.y())
                p.setPen(QPen(blue, 1.75))
                p.drawPath(ed["ghost_path"])
                p.restore()
                return
            group = self._edit["preview"] if self._edit and self._edit.get("preview") else None
            if group is None:
                group = [m for _x, m in self.view.selected_models_to_paint()]
            for k, m in enumerate(group):
                p.setPen(QPen(blue, 2 if k == 0 else 1, Qt.SolidLine if k == 0 else Qt.DashLine))
                p.drawRect(self.to_screen(A.bounds(m), page).adjusted(-3, -3, 3, 3))
            return
        shown = self._edit["preview"] if self._edit and self._edit.get("preview") else model
        p.setPen(QPen(blue, 1, Qt.DashLine))
        if A.turned(shown):
            pts = [self.to_screen_pt(q, page) for q in A.outline(shown, 36)]
            for a_, b_ in zip(pts, pts[1:] + pts[:1]):
                p.drawLine(a_, b_)
        elif shown["kind"] in ("line", "arrow", "m_length", "m_radius"):
            a, b = (self.to_screen_pt(q, page) for q in shown["points"])
            p.drawLine(a, b)
        elif shown["kind"] in A.VERTEXED:
            pts = [self.to_screen_pt(q, page) for q in shown["points"]]
            if shown["kind"] in ("polygon",) + A.CLOSED_MEASURES:
                pts.append(pts[0])
            for a_, b_ in zip(pts, pts[1:]):
                p.drawLine(a_, b_)
        elif shown["kind"] == "callout":
            p.drawRect(self.to_screen(shown["rect"], page).adjusted(-3, -3, 3, 3))
            p.drawLine(self.to_screen_pt(shown["points"][0], page),
                       self.to_screen(shown["rect"], page).center())
        else:
            p.drawRect(self.to_screen(A.bounds(shown), page).adjusted(-3, -3, 3, 3))
        if self._edit and self._edit["mode"] == "rot":
            p.setPen(blue)
            at = self._edit.get("pos", QPointF())
            p.drawText(at + QPointF(14, -8), f"{A.angle(shown):.0f}\u00b0")
        cad_objects = self.view.cad_select and self.view.tool == "editobjects"
        if not self._edit and not cad_objects:  # (CAD mode changes markups by commands)
            p.setPen(QPen(blue, 1))
            p.setBrush(Qt.white)
            for hid, r in self._handles(model).items():
                if hid == "rot":
                    top = QPointF(r.center().x(), r.center().y() + ROT_GAP)
                    p.drawLine(QPointF(r.center().x(), r.bottom()), top)
                    p.drawEllipse(r)
                else:
                    p.drawRect(r)
            p.setBrush(Qt.NoBrush)

    # ---- Edit objects ---------------------------------------------------
    def _objects_here(self):
        sel = self.view.obj_sel
        return sel[1] if sel is not None and sel[0] == self.index else []

    def _objects_handles(self):
        items = self._objects_here()
        if not items or any(it["kind"] == "text" for it in items):
            return {}                   # text is moved, not resized (Edit text changes it)
        return box_handles(self.to_screen(self.view.selected_objects_rect()).adjusted(-2, -2, 2, 2))

    def _selected_size(self, items):
        """How many line pieces the selected objects have (worked out once per selection)."""
        key = (id(self.view.obj_sel), len(items))
        if getattr(self, "_size_key", None) != key:
            self._size_key = key
            total = 0
            for it in items:
                total += sum(max(0, len(line) - 1)
                             for line in self.view.object_lines(self.index, it))
                if total > 30000:
                    break
            self._size = total
        return self._size

    def _screen_transform(self, page):
        """Unrotated PDF point -> widget point (to_screen_pt) as a QTransform."""
        z = self.view.zoom
        m = page.rotation_matrix
        return QTransform(m.a * z, m.b * z, m.c * z, m.d * z, m.e * z, m.f * z)

    def _draw_object(self, p, item, page):
        p.drawPath(self._screen_transform(page).map(
            lines_path(self.view.object_lines(self.index, item))))

    def _selection_path(self, page):
        """The selected objects' lines on screen, as one path (made once per selection,
        moved onto the screen again only when the zoom or the page's turn changes)."""
        sel = self.view.obj_sel
        t = self._screen_transform(page)
        key = (t.m11(), t.m12(), t.m21(), t.m22(), t.dx(), t.dy())
        got = getattr(self, "_sel_path", None)
        if got is None or got[0] is not sel or got[1] != self.index:
            path = lines_path(line for it in self._objects_here()
                              for line in self.view.object_lines(self.index, it))
            got = self._sel_path = (sel, self.index, path, None, None)
        if got[3] != key:
            got = self._sel_path = got[:3] + (key, t.map(got[2]))
        return got[4]

    def _paint_objects(self, p, page):
        blue = QColor(0, 120, 215)
        p.setBrush(Qt.NoBrush)
        items = self._objects_here()
        chosen = {it["n"] for it in items}
        hover = self._obj_hover
        if hover is not None and hover["n"] not in chosen:
            p.setPen(QPen(QColor(0, 120, 215, 200), 2, Qt.DashLine))
            self._draw_object(p, hover, page)
        ed = self._obj_edit
        if ed is not None and ed["mode"] == "box" and ed.get("now") is not None:
            p.setPen(QPen(blue, 1, Qt.DashLine))
            p.setBrush(QColor(0, 120, 215, 30))
            p.drawRect(QRectF(ed["start"], ed["now"]).normalized())
            p.setBrush(Qt.NoBrush)
        if not items:
            return
        p.setPen(QPen(QColor(0, 120, 215, 220), 2))
        dragging = ed is not None and ed.get("preview") is not None
        if dragging:
            # one picture of the shapes, drawn when the drag starts, then only slid.
            # redrawing every line on each mouse move is what made a group drag slow,
            # and the old preview was an empty box, so the shapes looked like they vanished.
            self._paint_object_ghost(p, ed, page)
        else:
            if len(items) <= 3000 and self._selected_size(items) <= 30000:
                p.drawPath(self._selection_path(page))
            elif len(items) <= 3000:            # (a huge drawing: each one's box)
                for it in items:
                    p.drawRect(self.to_screen(it["rect"], page))
            p.setPen(QPen(blue, 1, Qt.DashLine))
            p.drawRect(self.to_screen(self.view.selected_objects_rect(), page).adjusted(-2, -2, 2, 2))
            if ed is None:
                p.setPen(QPen(blue, 1))
                p.setBrush(Qt.white)
                for r in self._objects_handles().values():
                    p.drawRect(r)
                p.setBrush(Qt.NoBrush)

    def _objects_press(self, e, pos, pdf):
        if self._objects_here() and not ctrl_held(e):
            for hid, r in self._objects_handles().items():
                if r.adjusted(-3, -3, 3, 3).contains(pos):
                    self._obj_edit = {"mode": hid, "start": pos, "preview": None}
                    return
        item = self.view.object_at(self.index, pdf)
        if item is None:
            # drag a box from empty space: select everything inside it
            if not ctrl_held(e):
                self.view.clear_object_selection()
            self._obj_edit = {"mode": "box", "start": pos, "now": None, "preview": None,
                              "add": ctrl_held(e)}
            return
        if ctrl_held(e):
            self.view.select_objects(self.index, [item], add=True)
            return
        if item["n"] not in {it["n"] for it in self._objects_here()}:
            self.view.select_objects(self.index, [item])
        self._obj_edit = {"mode": "move", "start": pos, "preview": None}
        self.update()

    def _objects_preview(self, pos, free=False):
        """The selection's new box on screen while dragging."""
        ed = self._obj_edit
        r = QRectF(self.to_screen(self.view.selected_objects_rect()))
        d = pos - ed["start"]
        mode = ed["mode"]
        if mode == "move":
            return r.translated(d)
        left, top, right, bottom = r.left(), r.top(), r.right(), r.bottom()
        if "l" in mode:
            left += d.x()
        if "r" in mode:
            right += d.x()
        if "t" in mode:
            top += d.y()
        if "b" in mode:
            bottom += d.y()
        new = QRectF(QPointF(left, top), QPointF(right, bottom)).normalized()
        if len(mode) == 2 and not free and r.width() > 0 and r.height() > 0:
            # corner: keep the proportions (Shift = free)
            s_ = max(new.width() / r.width(), new.height() / r.height())
            w, h = r.width() * s_, r.height() * s_
            ax = r.right() if "l" in mode else r.left()
            ay = r.bottom() if "t" in mode else r.top()
            new = QRectF(ax - w if "l" in mode else ax, ay - h if "t" in mode else ay, w, h)
        return new

    def _build_object_ghost(self):
        """Rasterize the selected shapes once, in screen space, so dragging only moves a picture."""
        ed = self._obj_edit
        if ed is None or "ghost_pm" in ed:
            return
        items = self._objects_here()
        page = self.view.doc[self.index]
        bounds = QRectF(self.to_screen(self.view.selected_objects_rect(), page))
        ed["bounds_rect"] = bounds
        if bounds.width() < 1 or bounds.height() < 1 or not items:
            ed["ghost_pm"] = None
            ed["ghost_rect"] = bounds
            return
        pad = 6.0
        src = bounds.adjusted(-pad, -pad, pad, pad)
        max_px = 1_500_000
        w, h = max(1.0, src.width()), max(1.0, src.height())
        scale = (max_px / (w * h)) ** 0.5 if w * h > max_px else 1.0
        img = QImage(max(1, int(w * scale)), max(1, int(h * scale)),
                     QImage.Format_ARGB32_Premultiplied)
        img.fill(Qt.transparent)
        gp = QPainter(img)
        gp.setRenderHint(QPainter.Antialiasing, True)
        gp.scale(scale, scale)
        gp.translate(-src.left(), -src.top())
        gp.setPen(QPen(QColor(0, 90, 200), 1.75))
        gp.setBrush(Qt.NoBrush)
        gp.drawPath(self._selection_path(page))
        gp.end()
        ed["ghost_pm"] = QPixmap.fromImage(img)
        ed["ghost_rect"] = src

    def _paint_object_ghost(self, p, ed, page):
        if "ghost_pm" not in ed:
            self._build_object_ghost()
        pm = ed.get("ghost_pm")
        preview = ed.get("preview")
        bounds = ed.get("bounds_rect")
        src = ed.get("ghost_rect")
        if (pm is not None and not pm.isNull() and bounds is not None and src is not None
                and bounds.width() > 0 and bounds.height() > 0
                and preview is not None and preview.width() > 0 and preview.height() > 0):
            sx = preview.width() / bounds.width()
            sy = preview.height() / bounds.height()
            dest = QRectF(preview.left() - (bounds.left() - src.left()) * sx,
                          preview.top() - (bounds.top() - src.top()) * sy,
                          preview.width() + (src.width() - bounds.width()) * sx,
                          preview.height() + (src.height() - bounds.height()) * sy)
            p.drawPixmap(dest, pm, QRectF(0, 0, pm.width(), pm.height()))
        if preview is not None:
            p.setPen(QPen(QColor(0, 120, 215), 1, Qt.DashLine))
            p.setBrush(Qt.NoBrush)
            p.drawRect(preview)

    def _markup_outline(self, path, model, page):
        """Add one markup's outline to path, in this widget's coordinates."""
        if A.turned(model):
            pts = [self.to_screen_pt(q, page) for q in A.outline(model, 24)]
        elif model["kind"] in ("line", "arrow", "m_length", "m_radius") and model.get("points"):
            pts = [self.to_screen_pt(q, page) for q in model["points"]]
        elif model["kind"] in A.VERTEXED and model.get("points"):
            pts = [self.to_screen_pt(q, page) for q in model["points"]]
            if model["kind"] in ("polygon",) + A.CLOSED_MEASURES and pts:
                pts = pts + [pts[0]]
        elif model["kind"] == "ink":
            for stroke in model.get("strokes") or []:
                pts = [self.to_screen_pt(q, page) for q in stroke]
                if len(pts) >= 2:
                    path.moveTo(pts[0])
                    for q in pts[1:]:
                        path.lineTo(q)
            return
        elif model["kind"] == "ellipse":
            path.addEllipse(self.to_screen(A.bounds(model), page))
            return
        else:
            path.addRect(self.to_screen(A.bounds(model), page).adjusted(-3, -3, 3, 3))
            return
        if len(pts) >= 2:
            path.moveTo(pts[0])
            for q in pts[1:]:
                path.lineTo(q)

    def _build_markup_ghost(self):
        ed = self._edit
        if ed is None or "ghost_path" in ed:
            return
        path = QPainterPath()
        page = self.view.doc[self.index]
        for _x, model in ed.get("group") or []:
            self._markup_outline(path, model, page)
        ed["ghost_path"] = path

    def _objects_release(self, e, pos):
        ed, self._obj_edit = self._obj_edit, None
        self.update()
        if ed["mode"] == "box":
            if ed.get("now") is None:
                return
            q = QRectF(ed["start"], pos).normalized()
            box = pymupdf.Rect(self.to_pdf(q.topLeft()), self.to_pdf(q.bottomRight())).normalize()
            self.view.select_objects(self.index, self.view.objects_in(self.index, box),
                                     add=ed.get("add", False))
            return
        if ed["preview"] is not None and self._objects_here():
            q = ed["preview"]
            new = pymupdf.Rect(self.to_pdf(q.topLeft()), self.to_pdf(q.bottomRight())).normalize()
            self.view.move_objects(new)

    def _paint_link_borders(self, p):
        """Links with a visible border (/BS or /Border): MuPDF doesn't draw these, other
        PDF readers do, so draw them like Acrobat."""
        z = self.view.zoom
        for r, ln in self.view.links(self.index):
            b = ln.get("kz_border")
            if not b:
                continue
            width, rgb, style = b
            pen = QPen(QColor.fromRgbF(*rgb), max(1.0, width * z),
                       Qt.DashLine if style == "D" else Qt.SolidLine)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            box = QRectF(r.x0 * z, r.y0 * z, r.width * z, r.height * z)
            if style == "U":
                p.drawLine(box.bottomLeft(), box.bottomRight())
            else:
                p.drawRect(box)

    def _objects_menu(self, e, pdf):
        """The Edit objects menu; False (no menu) when there's no object there."""
        from PySide6.QtWidgets import QMenu
        item = self.view.object_at(self.index, pdf)
        if item is not None and item["n"] not in {it["n"] for it in self._objects_here()}:
            self.view.select_objects(self.index, [item])
        items = self._objects_here()
        if not items:
            return False
        one_pic = len(items) == 1 and items[0]["kind"] == "picture"
        has_text = any(it["kind"] == "text" for it in items)
        menu = QMenu(self)
        a = menu.addAction(tr("Copy picture"), self.view.copy_picture)
        a.setEnabled(one_pic)
        a = menu.addAction(tr("Save picture as..."), self.view.save_picture)
        a.setEnabled(one_pic and bool(items[0]["xref"]))
        menu.addSeparator()
        a = menu.addAction(tr("Ungroup"), self.view.ungroup_objects)
        a.setEnabled(any(it["kind"] == "group" for it in items))
        menu.addSeparator()
        for deg, label in ((90, tr("Rotate clockwise")), (-90, tr("Rotate counterclockwise"))):
            a = menu.addAction(label, lambda d=deg: self.view.rotate_objects(d))
            a.setEnabled(not has_text)
        menu.addSeparator()
        for how, label, keys in (("front", tr("Bring to front"), "Ctrl+Shift+]"),
                                 ("forward", tr("Bring forward"), "Ctrl+]"),
                                 ("backward", tr("Send backward"), "Ctrl+["),
                                 ("back", tr("Send to back"), "Ctrl+Shift+[")):
            a = menu.addAction(f"{label}\t{keys}", lambda h=how: self.view.arrange_objects(h))
            a.setEnabled(not has_text)
        self._link_actions(menu, pdf, True)
        menu.addSeparator()
        menu.addAction(tr("Delete") + "\tDel", self.view.delete_everything_selected)
        menu.exec(e.globalPosition().toPoint())
        return True

    def _sig_box(self):
        """While dragging to size a signature / initials: its box in displayed page
        coordinates (width from the drag, height from the picture's proportions), or None
        for a plain click."""
        a, b = self._sig_drag, self._sig_now
        if a is None or b is None or abs(b.x() - a.x()) < 6:
            return None
        pm = self.view.sig_pixmap(self.view.tool)
        aspect = pm.height() / pm.width() if pm is not None and pm.width() else 0.35
        z = self.view.zoom
        x0, x1 = sorted((a.x() / z, b.x() / z))
        w = x1 - x0
        h = w * aspect
        y0 = a.y() / z if b.y() >= a.y() else a.y() / z - h
        return pymupdf.Rect(x0, y0, x1, y0 + h)

    def _link_actions(self, menu, pdf, selected):
        """Add link... for what's selected; Edit link... / Remove link for a link here."""
        v = self.view
        here = v.link_at(self.index, pdf)
        if not selected and here is None:
            return
        menu.addSeparator()
        if selected:
            menu.addAction(tr("Add link..."), v.add_link_to_selection)
        if here is not None:
            menu.addAction(tr("Edit link..."), lambda: v.edit_link(self.index, here))
            menu.addAction(tr("Remove link"), lambda: v.remove_link_at(self.index, pdf))

    def _content_menu(self, e, pdf):
        """Right-click on the page: copy / cut / paste / delete, and for selected text the
        text markups. A right-click on a markup that isn't selected selects it first; one
        on selected text keeps the selection."""
        from PySide6.QtWidgets import QMenu
        v = self.view
        win = self.window()
        on_text = any(pymupdf.Rect(w[:4]).contains(pdf) for w in self._selected_words())
        if not on_text:
            xref = v.annot_at(self.index, pdf)
            if xref is not None and xref not in (v.selected_xrefs() if v.selection and
                                                 v.selection[0] == self.index else []):
                v.clear_text_selection()
                v.select_xref(self.index, xref)
        has_text = v.text_sel is not None
        has_markups = v.selection is not None
        menu = QMenu(self)
        if v.tool == "edittext" and v.text_line_rect(self.index, pdf) is not None:
            # the text written into the page under the pointer (its whole paragraph)
            menu.addAction(tr("Delete text"), lambda: v.delete_text_at(self.index, pdf))
            menu.addSeparator()
        # menu-only actions (the Edit menu's own ones keep their enabled state)
        for what, label, keys in (("cut", tr("Cut"), "Ctrl+X"), ("copy", tr("Copy"), "Ctrl+C"),
                                  ("paste", tr("Paste"), "Ctrl+V")):
            act = menu.addAction(f"{label}\t{keys}")
            act.triggered.connect(lambda _=False, w=what: win._clipboard(w))
            if what != "paste":
                act.setEnabled(has_text or has_markups)
        if has_markups:
            if not v.extra and v.selected_model is not None and \
                    A.text_editable(v.selected_model):
                sel = v.selection
                menu.addAction(tr("Edit text..."), lambda: v.edit_annot_text(*sel))
            # (all that's selected: in CAD mode, the drawing's objects selected with them too)
            menu.addAction(tr("Delete"), v.delete_everything_selected)
        elif on_text:
            # right-click on selected text that is also highlighted: offer to remove the markup
            xref = v.annot_at(self.index, pdf)
            if xref is not None:
                def remove(x=xref):
                    v.clear_text_selection()
                    v.select_xref(self.index, x)
                    v.delete_selected()
                menu.addAction(tr("Delete {what}").format(
                    what=v.annot_label(self.index, pdf).lower()), remove)
        if has_text:
            menu.addSeparator()
            for tool, label in (("highlight", tr("Highlight")), ("underline", tr("Underline")),
                                ("strikeout", tr("Strike out")),
                                ("comment", tr("Comment on text...")),
                                ("redact", tr("Mark for redaction"))):
                menu.addAction(label, lambda t=tool: v.markup_text_selection(t))
        self._link_actions(menu, pdf, has_text or has_markups)
        menu.addSeparator()
        act = menu.addAction(tr("Select all text") + "\tCtrl+A")
        act.triggered.connect(lambda: win._clipboard("all"))
        menu.exec(e.globalPosition().toPoint())

    def _objects_hover(self, pos):
        if self._objects_here():
            for hid, r in self._objects_handles().items():
                if r.adjusted(-3, -3, 3, 3).contains(pos):
                    self.setCursor(handle_cursor(hid))
                    return
        item = self.view.object_at(self.index, self.to_pdf(pos))
        if item is not None and not self.view.cad_select:
            self.setCursor(Qt.SizeAllCursor)
        else:
            self.unsetCursor()          # (CAD mode: dragging draws a lasso, nothing moves)
        key = item["n"] if item is not None else None
        if key != (self._obj_hover["n"] if self._obj_hover is not None else None):
            self._obj_hover = item
            self.update()

    # ---- snapping -------------------------------------------------------
    def _snapping(self, e=None):
        v = self.view
        if not (v.snap_grid or v.snap_objects or v.snap_page):
            return False
        return e is None or not e.modifiers() & Qt.AltModifier      # Alt = don't snap

    def _snap(self, pos, e=None, exclude=()):
        """Widget point -> snapped widget point (records the marker)."""
        self._snap_mark = None
        if not self._snapping(e):
            return pos
        r = self.view.snap_point(self.index, self.to_pdf(pos), exclude)
        if r is None:
            return pos
        sp = self.to_screen_pt(r[0])
        self._snap_mark = (sp, r[1])
        return sp

    def _paint_grid(self, p, exposed):
        v = self.view
        step = v.grid_spacing * v.zoom
        major = max(1, int(v.grid_major))
        if step * major < 6:
            return
        only_major = step < 6
        if only_major:
            step, major = step * major, 1
        minor_pen = QPen(QColor(0, 120, 215, 45), 0)
        major_pen = QPen(QColor(0, 120, 215, 100), 0)
        x0, x1 = exposed.left(), exposed.right()
        y0, y1 = exposed.top(), exposed.bottom()
        i = int(x0 // step)
        while i * step <= x1:
            p.setPen(major_pen if i % major == 0 else minor_pen)
            p.drawLine(QPointF(i * step, y0), QPointF(i * step, y1))
            i += 1
        j = int(y0 // step)
        while j * step <= y1:
            p.setPen(major_pen if j % major == 0 else minor_pen)
            p.drawLine(QPointF(x0, j * step), QPointF(x1, j * step))
            j += 1

    def _paint_snap_mark(self, p):
        if self._snap_mark is None:
            return
        pt, kind = self._snap_mark
        p.setBrush(Qt.NoBrush)
        if kind == "object":
            p.setPen(QPen(QColor(230, 0, 160), 1.5))
            p.drawRect(QRectF(pt.x() - 5, pt.y() - 5, 10, 10))
        elif kind == "page":
            p.setPen(QPen(QColor(0, 150, 60), 1.5))
            p.drawEllipse(pt, 5.5, 5.5)
        else:
            p.setPen(QPen(QColor(0, 120, 215), 1.5))
            p.drawLine(pt + QPointF(-6, 0), pt + QPointF(6, 0))
            p.drawLine(pt + QPointF(0, -6), pt + QPointF(0, 6))

    # ---- mouse ----------------------------------------------------------
    def _card_at(self, pos):
        for r, xref in self._cards:
            if r.contains(pos):
                return xref
        return None

    def mousePressEvent(self, e):
        if e.button() == Qt.MiddleButton:
            # hold the wheel down and drag to pan (CAD style), with any tool
            self._mid_pan = True
            self.view.begin_pan(e.globalPosition())
            return
        cmd = self.view._cad_cmd
        if cmd is not None and cmd.selecting and e.button() == Qt.RightButton:
            cmd.enter_key()                 # (selection done: the command goes on)
            return
        if cmd is not None and not cmd.selecting:
            # a CAD tab command takes the clicks (snapped); right-click = Enter
            if e.button() == Qt.LeftButton:
                pos = self._snap(e.position(), e) if cmd.snap else e.position()
                cmd.click(self.index, self.to_pdf(pos))
            elif e.button() == Qt.RightButton:
                cmd.enter_key()
            return
        if e.button() == Qt.RightButton and self.view.tool == "editobjects":
            pdf = self.to_pdf(e.position())
            v = self.view
            # CAD mode: a markup lies on top of the drawing, so it has its own menu
            on_markup = v.cad_select and (self._card_at(e.position()) is not None or
                                          v.annot_at(self.index, pdf) is not None)
            if (on_markup or not self._objects_menu(e, pdf)) and v.cad_select and \
                    not self._poly and self._edit is None:
                self._content_menu(e, pdf)
            return
        if e.button() == Qt.RightButton and not self._poly and self._edit is None:
            self._content_menu(e, self.to_pdf(e.position()))
            return
        if e.button() != Qt.LeftButton:
            return super().mousePressEvent(e)
        if self.view._inline is not None:
            # clicking outside the text editor finishes the edit (and nothing else)
            self.view.commit_pending()
            return
        self.view.setFocus()
        tool = self.view.tool
        pos = e.position()
        pdf = self.to_pdf(pos)

        if tool in ("hand", "select") and not self.view.read_only:
            xref = self.view.widget_at(self.index, pdf)
            if xref is not None:            # fill in a form field
                self.view.clear_selection()
                self.view.fill_field(self.index, xref)
                return
        # a click (press and release without dragging) on a link follows it, also on a markup
        # made a link: with the Hand tool; with Select only on Ctrl+click, so clicking to
        # select or edit what the link is on never opens it by accident
        self._link_press = None
        if tool == "hand" or (tool == "select" and ctrl_held(e)):
            link = self.view.link_to_follow(self.index, pdf)
            if link is not None:
                self._link_press = (link, pos)
        if cad_select.active(self):
            cad_select.press(self, e, pos, pdf)
            return
        if tool == "hand":
            # like Adobe and PDF-XChange: clicking a markup with the Hand selects it (to
            # move, restyle or delete), unless it's a link; anywhere else drags the page
            if self._link_press is None and self.view.show_markups and \
                    self.view.hand_selects and \
                    self._press_on_markup(pos, pdf, ctrl_held(e), cards=True):
                return
            self.view.begin_pan(e.globalPosition())
            return
        if tool == "editobjects":
            self._objects_press(e, pos, pdf)
            return
        if tool in EDIT_IN_PLACE and not self._poly:
            if shift_held(e):
                # Shift = draw a new one here even on top of a markup (to start a line at the
                # end of another, say): no selecting or moving
                if self.view.selection is not None:
                    self.view.clear_selection()
            elif self._press_on_markup(pos, pdf, ctrl_held(e)):
                return
        if tool in SNAP_TOOLS:
            pos = self._snap(pos, e)
            pdf = self.to_pdf(pos)
        if tool == "date":
            self.view.place_date(self.index, pdf)
            return
        if tool in SIGN_TOOLS:
            # click: place at the default size; drag: a box that sets its width
            self._sig_drag = pos
            self._sig_now = pos
            return
        if tool == "stamp":
            self.view.place_stamp(self.index, pdf)
            return
        if tool == "m_count":
            self.view.place_count(self.index, pdf)
            return
        if tool in POLY_TOOLS:
            if self._poly and shift_held(e):
                pos = snap45(self._poly[-1], pos)
            self._poly.append(pos)
            self.update()
            if tool == "m_angle" and len(self._poly) == 3:
                self.finish_poly()          # an angle is three clicks: end, corner, end
            return
        if tool in FORM_TOOLS:
            model = self._selected_here()
            if model is not None and model["kind"] == "field":
                for hid, r in self._handles(model).items():
                    if r.adjusted(-3, -3, 3, 3).contains(pos):
                        self._edit = {"mode": hid, "start": pos, "model": model, "preview": None}
                        return
            if self.view.select_field_at(self.index, pdf):
                self._edit = {"mode": "move", "start": pos, "model": self.view.selected_model,
                              "preview": None}
                return
            self.view.clear_selection()
            self._drag_start = self._drag_now = pos
            return
        if tool == "select":
            if self._link_press is None and self._press_on_markup(pos, pdf, ctrl_held(e),
                                                                  cards=True):
                return
        if tool in TEXT_TOOLS:
            if self._triple_click(e):
                return
            self.view.clear_text_selection()
            self._drag_start = self._drag_now = pos
            mode, words = self.view.text_selection(self.index, pdf, pdf)
            self._marquee = tool == "select" and ctrl_held(e)
            self._text_mode = "box" if self._marquee else mode
            self._text_sel = (self._text_mode, [] if self._marquee else words)
            if self._marquee:
                self.view._set_text_drag([(self.index, "box", [])])
            else:
                self.view._set_text_drag([(self.index, mode, words)])
            self.update()
        elif tool in SHAPE_TOOLS:
            self._drag_start = self._drag_now = pos
        elif tool == "ink":
            self._ink = [pos]
        elif tool == "edittext":
            # click a line to type in it; press on it and drag to move it (like Acrobat)
            self._hover = None
            self.update()
            rect = self.view.text_line_rect(self.index, pdf)
            if rect is None:
                self.view.edit_text_at(self.index, pdf)     # says there's no text there
            else:
                self._text_move = {"start": pos, "pdf": pdf, "rect": rect, "now": None,
                                   "one_line": alt_held(e),
                                   "pix": None}
        elif tool == "addtext":
            self.view.add_text_at(self.index, pdf)
        elif tool in ("note", "attach"):
            self.view.apply_point_tool(self.index, tool, pdf)

    def _press_on_markup(self, pos, pdf, ctrl=False, cards=False):
        """Handle a press on a selected markup's handle or on any markup: select it and start
        moving / resizing / rotating. Ctrl+click adds to / removes from the selection; pressing
        on one of several selected markups moves them all. Returns False when the press is on
        empty page (the caller draws or selects text); the selection is cleared then unless
        Ctrl is held."""
        model = self._selected_here()
        if model is not None and not ctrl:
            for hid, r in self._handles(model).items():
                if r.adjusted(-3, -3, 3, 3).contains(pos):
                    self._edit = {"mode": hid, "start": pos, "model": model, "preview": None}
                    return True
        if cards:
            card = self._card_at(pos)
            if card is not None:
                self.view.select_xref(self.index, card, add=ctrl)
                return True
        xref = self.view.annot_at(self.index, pdf)
        if xref is not None:
            if ctrl:
                if self.view.selection is not None and self.view.selection[0] != self.index:
                    self.view.clear_selection()
                self.view.select_xref(self.index, xref, add=True)
                return True
            if self.view.extra and self.view.selection[0] == self.index and \
                    xref in self.view.selected_xrefs():
                group = [(x, m) for x, m in self.view.selected_models() if A.movable(m)]
                self._edit = {"mode": "group", "start": pos, "group": group, "preview": None}
                return True
            if self.view.select_xref(self.index, xref):
                model = self._selected_here()
                if model is not None and A.movable(model):
                    self._edit = {"mode": "move", "start": pos, "model": model, "preview": None}
            return True
        if self.view.selection is not None and not ctrl:
            self.view.clear_selection()
        return False

    def _snapped_delta(self, model, pos, snap):
        """PDF move vector for a drag, snapping the markup's top-left corner (as displayed)."""
        ed = self._edit
        if not snap:
            return self.to_pdf(pos) - self.to_pdf(ed["start"])
        corner = self.to_screen(A.bounds(model)).topLeft()
        moved = self._snap(corner + (pos - ed["start"]), exclude=set(self.view.selected_xrefs()))
        return self.to_pdf(moved) - self.to_pdf(corner)

    def _edit_preview(self, pos, shift=False, snap=False):
        ed = self._edit
        excl = set(self.view.selected_xrefs())
        if ed["mode"] == "group":
            # the move itself, not a fresh copy of every markup, until the button is released
            if not ed.get("group"):
                return None
            ed["delta"] = self._snapped_delta(ed["group"][0][1], pos, snap)
            self._build_markup_ghost()
            return True
        model = ed["model"]
        if ed["mode"] == "move":
            return A.moved(model, self._snapped_delta(model, pos, snap))
        if snap and (ed["mode"] in ("p0", "p1") or ed["mode"].startswith("v")):
            pos = self._snap(pos, exclude=excl)
        if ed["mode"] == "rot":
            c = self.to_screen(A.bounds(model)).center()
            a0 = math.atan2(ed["start"].y() - c.y(), ed["start"].x() - c.x())
            a1 = math.atan2(pos.y() - c.y(), pos.x() - c.x())
            new = A.angle(model) - math.degrees(a1 - a0)      # screen y grows downward
            if shift:
                new = round(new / 15.0) * 15
            ed["pos"] = pos
            return A.rotated(model, new)
        if ed["mode"] in ("p0", "p1"):
            i = int(ed["mode"][1])
            if shift and model["kind"] != "callout":
                other = self.to_screen_pt(model["points"][1 - i])
                pos = snap45(other, pos)
            return A.with_endpoint(model, i, self.to_pdf(pos))
        if ed["mode"].startswith("v"):
            i = int(ed["mode"][1:])
            if shift and len(model["points"]) > 1:
                pos = snap45(self.to_screen_pt(model["points"][i - 1]), pos)
            return A.with_endpoint(model, i, self.to_pdf(pos))
        r = self.to_screen(A.bounds(model))
        d = pos - ed["start"]
        x0, y0, x1, y1 = r.left(), r.top(), r.right(), r.bottom()
        if "l" in ed["mode"]:
            x0 += d.x()
        if "r" in ed["mode"]:
            x1 += d.x()
        if "t" in ed["mode"]:
            y0 += d.y()
        if "b" in ed["mode"]:
            y1 += d.y()
        if snap and ed["mode"] in ("tl", "tr", "bl", "br", "t", "b", "l", "r"):
            sp = self._snap(QPointF(x0 if "l" in ed["mode"] else x1,
                                    y0 if "t" in ed["mode"] else y1), exclude=excl)
            if "l" in ed["mode"]:
                x0 = sp.x()
            if "r" in ed["mode"]:
                x1 = sp.x()
            if "t" in ed["mode"]:
                y0 = sp.y()
            if "b" in ed["mode"]:
                y1 = sp.y()
        if shift and ed["mode"] in ("tl", "tr", "bl", "br"):
            # Shift on a corner: squares / circles stay perfect, everything else keeps its shape
            fixed = QPointF(x1 if "l" in ed["mode"] else x0, y1 if "t" in ed["mode"] else y0)
            moving = QPointF(x0 if "l" in ed["mode"] else x1, y0 if "t" in ed["mode"] else y1)
            dv = moving - fixed
            if model["kind"] in ("rect", "ellipse") and not A.turned(model):
                moving = square_corner(fixed, moving)
            elif r.width() > 0 and r.height() > 0:
                k = max(abs(dv.x()) / r.width(), abs(dv.y()) / r.height())
                moving = fixed + QPointF(math.copysign(r.width() * k, dv.x() or 1),
                                         math.copysign(r.height() * k, dv.y() or 1))
            x0, y0, x1, y1 = fixed.x(), fixed.y(), moving.x(), moving.y()
        new = pymupdf.Rect(self.to_pdf(QPointF(x0, y0)), self.to_pdf(QPointF(x1, y1))).normalize()
        if new.width < 2 or new.height < 2:
            return model
        return A.resized(model, new)

    def mouseMoveEvent(self, e):
        if getattr(self, "_mid_pan", False):
            self.view.continue_pan(e.globalPosition())
            return
        pos = e.position()
        tool = self.view.tool
        if self.view._cad_cmd is not None and not e.buttons() and \
                not self.view._cad_cmd.selecting:
            cmd = self.view._cad_cmd
            cmd.move(self.index, self.to_pdf(self._snap(pos, e) if cmd.snap else pos))
            return
        if self._cad_down is not None and e.buttons():
            cad_select.move(self, e, pos)
            return
        if not e.buttons():
            cad_select.hover(self, e)
        if not e.buttons():
            if tool in SIGN_TOOLS or tool == "stamp":
                self._ghost = pos
                self.update()
                return
            if tool in SNAP_TOOLS and self._snapping(e):
                old = self._snap_mark
                pos = self._snap(pos, e)
                if old != self._snap_mark and not self._poly:
                    self.update()
            elif self._snap_mark is not None:
                self._snap_mark = None
                self.update()
            if self._poly:
                self._poly_hover = snap45(self._poly[-1], pos) if shift_held(e) else pos
                self.update()
                return
            if tool in ("select", "hand") and self.view.widget_at(self.index, self.to_pdf(pos)) is not None:
                self.setCursor(Qt.PointingHandCursor)
                return
            if tool in ("select", "hand"):
                pdf = self.to_pdf(pos)
                link = self.view.link_to_follow(self.index, pdf)
                if link is not None:
                    if tool == "hand":
                        self.setCursor(Qt.PointingHandCursor)
                    tip = self.view.link_tip(link)
                    if tool == "select":
                        tip += "\n" + tr("Ctrl+click to open")
                    QToolTip.showText(self.mapToGlobal(pos.toPoint()), tip, self)
                    if tool == "hand":
                        return
            if tool == "hand":
                self.unsetCursor()
            if tool == "editobjects":
                self._objects_hover(pos)
                return
            if tool == "edittext":
                # outline what a click edits: the paragraph, or the line with Alt
                r = self.view.text_target_rect(self.index, self.to_pdf(pos), alt_held(e))
                if r != self._hover:
                    self._hover = r
                    self.update()
            elif tool in EDIT_IN_PLACE and not self._poly and shift_held(e):
                self.unsetCursor()              # Shift: the tool draws here, it doesn't move
            elif tool == "select" or (tool in EDIT_IN_PLACE and not self._poly):
                self._update_select_cursor(pos, restore=tool != "select")
            return
        if tool == "hand":
            self.view.continue_pan(e.globalPosition())
        elif self._sig_drag is not None:
            self._sig_now = pos
            self.update()
        elif self._text_move is not None:
            tm = self._text_move
            if tm["now"] is not None or (pos - tm["start"]).manhattanLength() >= 4:
                if tm["pix"] is None:
                    # a picture of the line as it looks now, slid with the pointer
                    tm["box"] = self.to_screen(tm["rect"]).adjusted(-2, -2, 2, 2)
                    tm["pix"] = self.grab(tm["box"].toAlignedRect())
                tm["now"] = pos
                self.setCursor(Qt.SizeAllCursor)
                self.update()
        elif self._obj_edit is not None:
            if (pos - self._obj_edit["start"]).manhattanLength() >= 3:
                if self._obj_edit["mode"] == "box":
                    self._obj_edit["now"] = pos
                else:
                    self._obj_edit["preview"] = self._objects_preview(pos, shift_held(e))
                    self._build_object_ghost()
                self.update()
        elif self._edit is not None:
            if (pos - self._edit["start"]).manhattanLength() >= 3:
                self._edit["preview"] = self._edit_preview(pos, shift_held(e), self._snapping(e))
                self.update()
        elif self._text_sel is not None:
            self._drag_now = pos
            end_i, end_pt = self.view.page_point_from(self, pos)
            spans = self.view.text_selection_span(
                self.index, self.to_pdf(self._drag_start), end_i, end_pt, box=self._marquee)
            self._text_mode = "box" if self._marquee else (spans[0][1] if spans else "text")
            self._text_sel = (self._text_mode, [])
            self.view._set_text_drag(spans)
            self.view.autoscroll_toward(self.mapToGlobal(pos))
        elif self._drag_start is not None:
            if tool in SNAP_TOOLS:
                pos = self._snap(pos, e)
            if shift_held(e) and tool in STRAIGHT_TOOLS:
                pos = snap45(self._drag_start, pos)
            elif shift_held(e) and tool in SQUARE_TOOLS:
                pos = square_corner(self._drag_start, pos)
            self._drag_now = pos
            self.update()
        elif self._ink:
            self._ink.append(pos)
            self.update()

    def _update_select_cursor(self, pos, restore=False):
        model = self._selected_here()
        if model is not None:
            for hid, r in self._handles(model).items():
                if r.adjusted(-3, -3, 3, 3).contains(pos):
                    self.setCursor(handle_cursor(hid))
                    return
        over = self.view.annot_at(self.index, self.to_pdf(pos))
        if over is None:
            over = self._card_at(pos)
        if over is not None:
            if self.view.cad_select and self.view.tool == "select":
                self.unsetCursor()      # CAD mode: dragging draws a lasso, nothing moves
            else:
                self.setCursor(Qt.SizeAllCursor)
            card = self._card_at(pos)
            if card is None:
                tip = self.view.annot_tooltip(self.index, self.to_pdf(pos))
                if tip:
                    QToolTip.showText(self.mapToGlobal(pos.toPoint()), tip, self)
        else:
            self.unsetCursor()

    def mouseReleaseEvent(self, e):
        press = getattr(self, "_link_press", None)
        self._link_press = None
        self._release(e)
        if press is not None and e.button() == Qt.LeftButton:
            p = e.position() - press[1]
            if abs(p.x()) + abs(p.y()) < 5:
                self.view.follow_link(press[0])

    def _release(self, e):
        if e.button() == Qt.LeftButton and self._snap_mark is not None and self._edit is not None:
            self._snap_mark = None
        if e.button() == Qt.MiddleButton and getattr(self, "_mid_pan", False):
            self._mid_pan = False
            self.view.end_pan()
            return
        if e.button() != Qt.LeftButton:
            return
        tool = self.view.tool
        pos = e.position()
        if self._cad_down is not None:
            cad_select.release(self, e, pos)
            return
        if self._text_move is not None:
            tm, self._text_move = self._text_move, None
            self.unsetCursor()
            self.update()
            if tm["now"] is None:
                # a click edits the paragraph; Alt+click just the line
                self.view.edit_text_at(self.index, tm["pdf"], one_line=tm.get("one_line", False))
            else:
                a, b = self.to_pdf(tm["start"]), self.to_pdf(pos)
                self.view.move_text_line(self.index, tm["pdf"], (b.x - a.x, b.y - a.y))
            return
        if tool == "hand":
            self.view.end_pan()
        elif self._sig_drag is not None:
            self._sig_now = pos
            box = self._sig_box()
            start, self._sig_drag, self._sig_now = self._sig_drag, None, None
            self.update()
            if box is None:                       # a click: default size, centered there
                self.view.place_signature(self.index, tool, self.to_pdf(start))
            else:
                self.view.place_signature(self.index, tool, box=box)
        elif self._obj_edit is not None:
            self._objects_release(e, pos)
        elif self._edit is not None:
            ed, self._edit = self._edit, None
            preview = ed.get("preview")
            self.update()
            if ed["mode"] == "group" and ed.get("delta") is not None:
                delta = ed["delta"]
                self.view.commit_models(self.index, [(x, A.moved(m, delta))
                                                     for x, m in ed["group"]])
            elif preview is not None:
                self.view.commit_model(self.index, self.view.selection[1], preview)
        elif self._text_sel is not None:
            a, b = self._drag_start, pos
            mode = self._text_mode
            end_i, end_pt = self.view.page_point_from(self, pos)
            start_pt = self.to_pdf(a)
            marquee = self._marquee
            self._text_sel = None
            self._text_mode = None
            self._marquee = False
            self._drag_start = self._drag_now = None
            self.view._set_text_drag(None)
            if (b - a).manhattanLength() >= 3:
                if tool == "select" and mode == "box" and end_i == self.index:
                    # a box drawn from empty space selects the markups inside it
                    box = pymupdf.Rect(start_pt, self.to_pdf(b)).normalize()
                    if self.view.select_in_box(self.index, box, add=ctrl_held(e)) or ctrl_held(e):
                        return
                self.view.apply_text_span(tool, (self.index, start_pt), (end_i, end_pt),
                                          box=marquee)
        elif self._drag_start is not None and tool in FORM_TOOLS:
            a, b = self._drag_start, self._drag_now
            self._drag_start = self._drag_now = None
            self.update()
            self.view.create_field(self.index, tool, self.to_pdf(a), self.to_pdf(b),
                                   (b - a).manhattanLength() < 4)
        elif self._drag_start is not None:
            a, b = self._drag_start, self._drag_now
            self._drag_start = self._drag_now = None
            self.update()
            self.view.apply_drag_tool(self.index, tool, self.to_pdf(a), self.to_pdf(b),
                                      (b - a).manhattanLength() < 4)
        elif self._ink:
            pts = [self.to_pdf(p) for p in self._ink]
            self._ink = []
            self.update()
            if len(pts) > 1:
                self.view.apply_ink(self.index, pts)

    def finish_poly(self, cancel=False):
        pts, self._poly, self._poly_hover = self._poly, [], None
        self.update()
        tool = self.view.tool
        if cancel or len(pts) < 2 or (tool in ("polygon", "m_angle", "m_volume") and len(pts) < 3):
            return
        self.view.apply_poly(self.index, tool, [self.to_pdf(q) for q in pts])

    def mouseDoubleClickEvent(self, e):
        cad_select.cancel(self.view)        # (a double-click selects a word: no box after it)
        if self.view.tool in POLY_TOOLS:
            # the double-click's first press already added this point
            self.finish_poly()
            return
        if self.view.tool in FORM_TOOLS:
            xref = self.view.widget_at(self.index, self.to_pdf(e.position()))
            if xref is not None:
                self.view.edit_field_properties(self.index, xref)
            return
        if self.view.tool in ("select", "hand"):
            card = self._card_at(e.position())
            pdf = self.to_pdf(e.position())
            if card is not None:
                self.view.edit_annot_text(self.index, card)
            elif self.view.annot_at(self.index, pdf) is not None or self.view.tool == "hand":
                self.view.edit_annot_at(self.index, pdf)
            else:
                self._select_word(pdf, e)
        elif self.view.tool in TEXT_TOOLS:
            self._select_word(self.to_pdf(e.position()), e)

    def _select_word(self, pdf, e):
        """Double-click: select the word under the pointer (a third click selects the line)."""
        word = self.view.word_at(self.index, pdf)
        self._drag_start = self._drag_now = None
        self._text_sel = None
        self.view._set_text_drag(None)
        if word:
            self.view.set_text_selection(self.index, word)
        else:
            self.view.clear_text_selection()
        import time
        self._dbl_click = (time.monotonic(), e.position().toPoint())

    def _triple_click(self, e):
        """True (and the line under the pointer selected) when this press follows a
        double-click closely enough to be the third click."""
        import time
        last = getattr(self, "_dbl_click", None)
        if last is None:
            return False
        t, pos = last
        self._dbl_click = None
        if time.monotonic() - t > QApplication.doubleClickInterval() / 1000 or \
                (e.position().toPoint() - pos).manhattanLength() > 6:
            return False
        line = self.view.line_at(self.index, self.to_pdf(e.position()))
        if line:
            self.view.set_text_selection(self.index, line)
        return bool(line)

    def leaveEvent(self, e):
        if self._obj_hover is not None:
            self._obj_hover = None
            self.update()
        self._poly_hover = None
        if self._snap_mark is not None:
            self._snap_mark = None
            self.update()
        if self._ghost is not None:
            self._ghost = None
            self.update()
        if self._hover is not None:
            self._hover = None
            self.update()
