"""A single rendered PDF page inside the scrolling document view.

Handles drawing (page image, search hits, comment boxes, selection handles, previews)
and turns mouse input into calls on the DocumentView, which owns all PDF edits.
"""

import math
import pymupdf
from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import (QPainter, QImage, QPixmap, QColor, QPen, QPainterPath,
                           QFontMetrics)
from PySide6.QtWidgets import QWidget, QToolTip

from . import annotations as A

TEXT_TOOLS = {"select", "highlight", "underline", "strikeout", "comment", "redact"}
SHAPE_TOOLS = {"textbox", "rect", "ellipse", "line", "arrow", "eraser", "cloud", "callout",
               "m_length", "m_calibrate", "image", "placeholder", "erasecontent", "capture"}
POLY_TOOLS = {"polygon", "polyline", "m_poly", "m_area"}
# While one of these drawing tools is active, clicking an existing markup selects it for
# moving / resizing / restyling (like the Select tool) instead of starting a new one.
EDIT_IN_PLACE = {"rect", "ellipse", "cloud", "line", "arrow", "polygon", "polyline", "ink",
                 "textbox", "callout", "note", "stamp", "m_length", "m_poly", "m_area", "m_count",
                 "image", "attach", "placeholder"}
MEASURE_TOOLS = {"m_length", "m_calibrate", "m_poly", "m_area"}
FORM_TOOLS = {"f_text", "f_check", "f_radio", "f_combo", "f_sign", "f_initials"}
SIGN_TOOLS = {"signature", "initials"}
HANDLE = 7          # handle size in px
FULL_LIMIT = 16_000_000     # device pixels: above this a page is drawn in tiles
TILE = 512                  # tile size in device pixels
TILE_LIMIT = 160            # tiles kept in memory per document (~125 MB)
CARD_W = 190        # comment box width in px
ROT_GAP = 26        # rotation handle distance above the selection, px
# tools whose points snap (to the grid / to objects) while drawing
SNAP_TOOLS = (SHAPE_TOOLS - {"eraser", "erasecontent", "capture"}) | POLY_TOOLS | {"stamp", "note", "m_count", "attach"}
STRAIGHT_TOOLS = {"line", "arrow", "m_length", "m_calibrate", "callout"}   # Shift = 45° steps
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


class PageWidget(QWidget):
    def __init__(self, view, index):
        super().__init__()
        self.view = view
        self.index = index
        self._pix = None
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
        self._snap_mark = None      # (widget point, "object" | "page" | "grid") last snap
        self._obj_hover = None      # Edit objects: picture under the mouse
        self._obj_edit = None       # Edit objects: dragging / resizing the selected picture
        self._sig_drag = None       # signature / initials: press point while sizing
        self._sig_now = None
        self.setMouseTracking(True)
        self.setAttribute(Qt.WA_OpaquePaintEvent)
        self.update_size()

    # ---- geometry -------------------------------------------------------
    def update_size(self):
        r = self.view.page_rects[self.index]
        z = self.view.zoom
        self.setFixedSize(max(1, int(r.width * z)), max(1, int(r.height * z)))
        self._pix = None

    def invalidate(self):
        """Page content changed: forget its display list, bitmap and tiles."""
        self._pix = None
        self.view._dlists.pop(self.index, None)
        self._drop_tiles()
        self.update()

    def drop_cache(self):
        self._pix = None

    def _drop_tiles(self):
        tiles = self.view._tiles
        for key in [k for k in tiles if k[0] == self.index]:
            del tiles[key]

    def _display_list(self):
        """The page's parsed drawing, made once and reused for every render and tile."""
        dl = self.view._dlists.get(self.index)
        if dl is None:
            dl = self.view.doc[self.index].get_displaylist(annots=self.view.show_markups)
            self.view._dlists[self.index] = dl
        return dl

    @staticmethod
    def _to_qpixmap(pm, dpr):
        img = QImage(pm.samples, pm.width, pm.height, pm.stride, QImage.Format_RGB888).copy()
        pix = QPixmap.fromImage(img)
        pix.setDevicePixelRatio(dpr)
        return pix

    def _tiled(self):
        dpr = self.devicePixelRatioF()
        return self.width() * self.height() * dpr * dpr > FULL_LIMIT

    def _paint_tiles(self, p, exposed):
        """Large page at high zoom: draw only the visible area, in cached tiles."""
        dpr = self.devicePixelRatioF()
        s = self.view.zoom * dpr
        dl = self._display_list()
        full = pymupdf.IRect(0, 0, int(self.width() * dpr), int(self.height() * dpr))
        tiles = self.view._tiles
        tx0, ty0 = int(exposed.left() * dpr) // TILE, int(exposed.top() * dpr) // TILE
        tx1, ty1 = int(exposed.right() * dpr) // TILE, int(exposed.bottom() * dpr) // TILE
        for ty in range(ty0, ty1 + 1):
            for tx in range(tx0, tx1 + 1):
                key = (self.index, round(s, 5), tx, ty)
                hit = tiles.get(key)
                if hit is None:
                    dev = pymupdf.IRect(tx * TILE, ty * TILE, (tx + 1) * TILE, (ty + 1) * TILE) & full
                    if dev.is_empty:
                        continue
                    try:
                        pm = dl.get_pixmap(matrix=pymupdf.Matrix(s, s), clip=pymupdf.Rect(dev) / s,
                                           alpha=False)
                        hit = (self._to_qpixmap(pm, dpr), pm.x, pm.y)
                    except Exception:
                        p.fillRect(QRectF(dev.x0 / dpr, dev.y0 / dpr, dev.width / dpr,
                                          dev.height / dpr), Qt.white)
                        continue
                    tiles[key] = hit
                    while len(tiles) > TILE_LIMIT:
                        tiles.popitem(last=False)
                else:
                    tiles.move_to_end(key)
                pix, x, y = hit
                p.drawPixmap(QPointF(x / dpr, y / dpr), pix)

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
        dpr = self.devicePixelRatioF()
        s = self.view.zoom * dpr
        pm = self._display_list().get_pixmap(matrix=pymupdf.Matrix(s, s), alpha=False)
        self._pix = self._to_qpixmap(pm, dpr)
        self.view._pix_pages.add(self.index)

    def paintEvent(self, event):
        p = QPainter(self)
        if self.view.doc.is_closed:      # tab closing: a queued repaint must not touch it
            p.fillRect(event.rect(), Qt.white)
            return
        if self._tiled():
            self._pix = None
            self._paint_tiles(p, event.rect())
        else:
            if self._pix is None:
                try:
                    self._render()
                except Exception:
                    p.fillRect(self.rect(), Qt.white)
                    return
            p.drawPixmap(0, 0, self._pix)
        page = self.view.doc[self.index]
        if self.view.grid_on:
            self._paint_grid(p, QRectF(event.rect()))
        p.setRenderHint(QPainter.Antialiasing)

        hits = self.view.search_hits.get(self.index)
        if hits:
            cur = self.view.current_hit()
            for i, r in enumerate(hits):
                active = cur == (self.index, i)
                color = QColor(255, 120, 0, 120) if active else QColor(255, 230, 0, 90)
                p.fillRect(self.to_screen(r, page), color)

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
            if tool in ("polygon", "m_area") and len(pts) > 2:
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
            if tool in ("line", "arrow", "m_length", "m_calibrate"):
                p.drawLine(self._drag_start, self._drag_now)
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
            body = text if text.strip() else "(empty note)"
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
        if model["kind"] in ("line", "arrow", "m_length"):
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
                group = [m for _x, m in self.view.selected_models()]
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
        elif shown["kind"] in ("line", "arrow", "m_length"):
            a, b = (self.to_screen_pt(q, page) for q in shown["points"])
            p.drawLine(a, b)
        elif shown["kind"] in A.VERTEXED:
            pts = [self.to_screen_pt(q, page) for q in shown["points"]]
            if shown["kind"] in ("polygon", "m_area"):
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
        if not self._edit:
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
        if not items:
            return {}
        return box_handles(self.to_screen(self.view.selected_objects_rect()).adjusted(-2, -2, 2, 2))

    def _draw_object(self, p, item, page):
        for line in self.view.object_lines(self.index, item):
            pts = [self.to_screen_pt(q, page) for q in line]
            for a_, b_ in zip(pts, pts[1:]):
                p.drawLine(a_, b_)

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
            if len(items) <= 3000:
                for it in items:
                    self._draw_object(p, it, page)
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
        for it in items:
            self._draw_object(gp, it, page)
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
        elif model["kind"] in ("line", "arrow", "m_length") and model.get("points"):
            pts = [self.to_screen_pt(q, page) for q in model["points"]]
        elif model["kind"] in A.VERTEXED and model.get("points"):
            pts = [self.to_screen_pt(q, page) for q in model["points"]]
            if model["kind"] in ("polygon", "m_area") and pts:
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

    def _objects_menu(self, e, pdf):
        from PySide6.QtWidgets import QMenu
        item = self.view.object_at(self.index, pdf)
        if item is not None and item["n"] not in {it["n"] for it in self._objects_here()}:
            self.view.select_objects(self.index, [item])
        items = self._objects_here()
        if not items:
            return
        one_pic = len(items) == 1 and items[0]["kind"] == "picture"
        menu = QMenu(self)
        a = menu.addAction("Copy picture", self.view.copy_picture)
        a.setEnabled(one_pic)
        a = menu.addAction("Save picture as...", self.view.save_picture)
        a.setEnabled(one_pic and bool(items[0]["xref"]))
        menu.addSeparator()
        menu.addAction("Rotate clockwise", lambda: self.view.rotate_objects(90))
        menu.addAction("Rotate counterclockwise", lambda: self.view.rotate_objects(-90))
        menu.addSeparator()
        for how, label, keys in (("front", "Bring to front", "Ctrl+Shift+]"),
                                 ("forward", "Bring forward", "Ctrl+]"),
                                 ("backward", "Send backward", "Ctrl+["),
                                 ("back", "Send to back", "Ctrl+Shift+[")):
            menu.addAction(f"{label}\t{keys}", lambda h=how: self.view.arrange_objects(h))
        menu.addSeparator()
        menu.addAction("Delete", self.view.delete_objects)
        menu.exec(e.globalPosition().toPoint())

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
        # menu-only actions (the Edit menu's own ones keep their enabled state)
        for what, label, keys in (("cut", "Cut", "Ctrl+X"), ("copy", "Copy", "Ctrl+C"),
                                  ("paste", "Paste", "Ctrl+V")):
            act = menu.addAction(f"{label}\t{keys}")
            act.triggered.connect(lambda _=False, w=what: win._clipboard(w))
            if what != "paste":
                act.setEnabled(has_text or has_markups)
        if has_markups:
            if not v.extra and (v.selected_model or {}).get("kind") != "field":
                sel = v.selection
                menu.addAction("Edit text...", lambda: v.edit_annot_text(*sel))
            menu.addAction("Delete", v.delete_selected)
        elif on_text:
            # right-click on selected text that is also highlighted: offer to remove the markup
            xref = v.annot_at(self.index, pdf)
            if xref is not None:
                def remove(x=xref):
                    v.clear_text_selection()
                    v.select_xref(self.index, x)
                    v.delete_selected()
                menu.addAction("Delete " + v.annot_tooltip(self.index, pdf).split(":")[0].lower(),
                               remove)
        if has_text:
            menu.addSeparator()
            for tool, label in (("highlight", "Highlight"), ("underline", "Underline"),
                                ("strikeout", "Strike out"), ("comment", "Comment on text..."),
                                ("redact", "Mark for redaction")):
                menu.addAction(label, lambda t=tool: v.markup_text_selection(t))
        menu.addSeparator()
        act = menu.addAction("Select all text\tCtrl+A")
        act.triggered.connect(lambda: win._clipboard("all"))
        menu.exec(e.globalPosition().toPoint())

    def _objects_hover(self, pos):
        if self._objects_here():
            for hid, r in self._objects_handles().items():
                if r.adjusted(-3, -3, 3, 3).contains(pos):
                    self.setCursor(handle_cursor(hid))
                    return
        item = self.view.object_at(self.index, self.to_pdf(pos))
        if item is not None:
            self.setCursor(Qt.SizeAllCursor)
        else:
            self.unsetCursor()
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
        if e.button() == Qt.RightButton and self.view.tool == "editobjects":
            self._objects_menu(e, self.to_pdf(e.position()))
            return
        if e.button() == Qt.RightButton and not self._poly and self._edit is None:
            self._content_menu(e, self.to_pdf(e.position()))
            return
        if e.button() != Qt.LeftButton:
            return super().mousePressEvent(e)
        if self.view._inline is not None:
            # clicking outside the text editor finishes the edit (and nothing else)
            self.view._inline.commit()
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
        # a click (press and release without dragging) on a link follows it
        self._link_press = None
        if tool in ("hand", "select"):
            link = self.view.link_at(self.index, pdf)
            if link is not None and self.view.annot_at(self.index, pdf) is None:
                self._link_press = (link, pos)
        if tool == "hand":
            # like Adobe and PDF-XChange: clicking a markup with the Hand selects it (to
            # move, restyle or delete); anywhere else drags the page
            if self.view.show_markups and self._press_on_markup(pos, pdf, ctrl_held(e), cards=True):
                return
            self.view.begin_pan(e.globalPosition())
            return
        if tool == "editobjects":
            self._objects_press(e, pos, pdf)
            return
        if tool in EDIT_IN_PLACE and not self._poly and self._press_on_markup(pos, pdf, ctrl_held(e)):
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
            if self._press_on_markup(pos, pdf, ctrl_held(e), cards=True):
                return
        if tool in TEXT_TOOLS:
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
            self._hover = None
            self.update()
            self.view.edit_text_at(self.index, pdf)
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
                link = self.view.link_at(self.index, pdf)
                if link is not None and self.view.annot_at(self.index, pdf) is None:
                    self.setCursor(Qt.PointingHandCursor)
                    QToolTip.showText(self.mapToGlobal(pos.toPoint()),
                                      self.view.link_tip(link), self)
                    return
            if tool == "hand":
                self.unsetCursor()
            if tool == "editobjects":
                self._objects_hover(pos)
                return
            if tool == "edittext":
                r = self.view.text_line_rect(self.index, self.to_pdf(pos))
                if r != self._hover:
                    self._hover = r
                    self.update()
            elif tool == "select" or (tool in EDIT_IN_PLACE and not self._poly):
                self._update_select_cursor(pos, restore=tool != "select")
            return
        if tool == "hand":
            self.view.continue_pan(e.globalPosition())
        elif self._sig_drag is not None:
            self._sig_now = pos
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
        over = self.view.annot_at(self.index, self.to_pdf(pos)) is not None or \
            self._card_at(pos) is not None
        if over:
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
        if cancel or len(pts) < 2 or (tool == "polygon" and len(pts) < 3):
            return
        self.view.apply_poly(self.index, tool, [self.to_pdf(q) for q in pts])

    def mouseDoubleClickEvent(self, e):
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
            if card is not None:
                self.view.edit_annot_text(self.index, card)
            else:
                self.view.edit_annot_at(self.index, self.to_pdf(e.position()))

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
