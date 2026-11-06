"""Selecting in CAD mode, as in AutoCAD, with Select (markups and text) and Edit objects (the
page's own lines, text and pictures):

- click an item: it's added to the selection (Shift+click takes it out);
- click empty paper, move, click again: a selection box. Left to right it's a blue window
  (takes what lies entirely inside it), right to left a dashed green crossing box (takes
  everything it touches). Escape cancels it;
- hold the button and drag: a lasso that follows the pointer. Drawn rightward at first it's a
  window lasso (blue), leftward a crossing lasso (green);
- dragging never moves anything (use the CAD tab's Move); handles still resize;
- while a box or lasso is drawn, what it would take is highlighted, worked out in short
  slices between pointer moves so big drawings stay smooth (it fills in as it goes).

Mouse mode options (Preferences > Mouse) can turn click-click boxes or the lasso off: then a
press-drag-release draws a box instead.
"""
import time

import pymupdf
import shiboken6
from PySide6.QtCore import Qt, QPointF, QRectF, QTimer
from PySide6.QtGui import QColor, QPen, QPolygonF

from .i18n import tr
from .page_objects import Box, Lasso

BLUE = QColor(0, 120, 215)
GREEN = QColor(0, 150, 60)


def active(w):
    v = w.view
    return v.cad_select and v.tool in ("select", "editobjects")


def _shift(e):
    return bool(e.modifiers() & Qt.ShiftModifier)


def press(w, e, pos, pdf, outside=False):
    """A left press on page widget w (CAD mode, Select or Edit objects). outside: on the
    gray canvas around the pages (pos and pdf: the same point in w's terms, off the page),
    where a press only starts a box or lasso."""
    v = w.view
    pick = v._cad_pick
    v._cad_drag_w = w
    if pick is not None:                # the second click of a click, move, click box
        finish_box(v, pick, e)
        w._cad_down = {"ignore": True}
        return
    remove = _shift(e)
    if not outside and not remove:
        box = resize_box(w)             # several items, or markups and objects: one box
        if box is not None:
            from .page_widget import box_handles
            for hid, r in box_handles(box).items():
                if r.adjusted(-3, -3, 3, 3).contains(pos):
                    w._cad_resize = {"mode": hid, "start": pos, "box": box, "now": None}
                    return
    if outside:
        target = ("markup", None)
    elif v.tool == "select" or not w._objects_here():
        # one markup selected: its own handles resize it (with Edit objects too)
        model = w._selected_here()
        if model is not None and not v.extra and not remove:
            for hid, r in w._handles(model).items():
                if r.adjusted(-3, -3, 3, 3).contains(pos):
                    w._edit = {"mode": hid, "start": pos, "model": model, "preview": None}
                    return
    elif w._objects_here() and not remove:
        for hid, r in w._objects_handles().items():
            if r.adjusted(-3, -3, 3, 3).contains(pos):
                w._obj_edit = {"mode": hid, "start": pos, "preview": None}
                return
    if not outside:
        target = target_at(w, pos, pdf)
    w._cad_down = {"start": pos, "pts": [pos], "dir": 0, "mode": None, "now": None,
                   "target": target, "remove": remove, "t": e.timestamp(),
                   "link": getattr(w, "_link_press", None) is not None}


def target_at(w, pos, pdf):
    """What a click at pos (pdf: the same point on the page) takes: ("markup", xref) with
    Select; with Edit objects everything, a markup drawn over the drawing first (it lies on
    top), else ("object", the drawing's own line, text or picture). The target is None for
    empty paper."""
    v = w.view
    xref = w._card_at(pos)
    if xref is None:
        xref = v.annot_at(w.index, pdf)
    if v.tool == "select" or xref is not None:
        return "markup", xref
    return "object", v.object_at(w.index, pdf)


# A press and release this quick, ending this close, is a click even if the pointer moved a
# little meanwhile (clicking "on the way" to the box's other corner): a hand rarely keeps the
# mouse still. Measured by the events' own times, so a moment the app was busy doesn't turn
# a click into a lasso.
CLICK_MS = 250
CLICK_PX = 40
STILL_PX = 10           # held longer: still a click while the pointer stays this close


def _a_click(d, e, pos):
    """The press and release in d (and e, at pos) make a click, not a lasso or a box."""
    far = max([abs(q.x() - d["start"].x()) + abs(q.y() - d["start"].y())
               for q in d["pts"] + [pos]])
    held = e.timestamp() - d.get("t", e.timestamp())
    return far < STILL_PX or (0 <= held < CLICK_MS and far < CLICK_PX)


def move(w, e, pos):
    """Pointer moved with the button held: a lasso (or a box) after a few pixels."""
    d = w._cad_down
    if d.get("ignore"):
        return
    v = w.view
    if d["mode"] is None and (pos - d["start"]).manhattanLength() >= 4:
        d["mode"] = "lasso" if v.lasso else "box"
    if d["mode"] == "lasso":
        if (pos - d["pts"][-1]).manhattanLength() >= 2:
            d["pts"].append(pos)
        if not d["dir"] and abs(pos.x() - d["start"].x()) >= 3:
            d["dir"] = 1 if pos.x() > d["start"].x() else -1
    elif d["mode"] == "box":
        d["now"] = pos
    _schedule(w)
    w.update()
    _outside_update(w)


def hover(w, e):
    """Pointer moved without a button: the click, move, click box follows it; with no box
    started, what a click would take there is highlighted (rollover)."""
    pick = w.view._cad_pick
    if pick is None:
        rollover(w, e.position())
        return
    clear_rollover(w)
    pw = pick["w"]
    if not shiboken6.isValid(pw):       # (the pages were rebuilt)
        w.view._cad_pick = None
        return
    pick["now"] = QPointF(pw.mapFromGlobal(e.globalPosition()))
    _schedule(pw)
    pw.update()
    _outside_update(pw)


# ---- rollover: what a click would take, before the click, so the user sees where Move,
# Mirror, Scale... can take something: the cross becomes a crosshair with a pick box (as in
# AutoCAD) and the item fades (drawn lighter) while the pointer is over it
_PICK_CURSOR = None


def pick_cursor():
    """The CAD cross with a pick box in its middle: a click here takes something."""
    global _PICK_CURSOR
    if _PICK_CURSOR is None:
        from PySide6.QtGui import QCursor, QPixmap, QPainter
        pm = QPixmap(33, 33)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        for color, width in ((QColor(255, 255, 255), 3), (QColor(0, 0, 0), 1)):
            p.setPen(QPen(color, width))
            p.setBrush(Qt.NoBrush)
            p.drawLine(16, 0, 16, 10)
            p.drawLine(16, 22, 16, 32)
            p.drawLine(0, 16, 10, 16)
            p.drawLine(22, 16, 32, 16)
            p.drawRect(11, 11, 10, 10)
        p.end()
        _PICK_CURSOR = QCursor(pm, 16, 16)
    return _PICK_CURSOR


def handle_at(w, pos):
    """The resize handle of a CAD selection under pos (widget point), or None."""
    from .page_widget import box_handles
    box = resize_box(w)
    if box is not None:
        for hid, r in box_handles(box).items():
            if r.adjusted(-3, -3, 3, 3).contains(pos):
                return hid
        return None
    v = w.view
    model = w._selected_here()
    if model is not None and not v.extra and not w._objects_here():
        for hid, r in w._handles(model).items():
            if r.adjusted(-3, -3, 3, 3).contains(pos):
                return hid
    return None


def apply_cursor(w):
    """The pick box cursor over something a click takes, else the view's own cross (a
    resize arrow over a handle)."""
    hid = getattr(w, "_cad_handle", None)
    if hid is not None:
        from .page_widget import handle_cursor
        w.setCursor(handle_cursor(hid))
        return
    hv = _rollover_shown(w)
    if hv is not None and hv["takes"]:
        w.setCursor(pick_cursor())
    else:
        w.unsetCursor()


_OPEN_KINDS = ("line", "arrow", "polyline", "ink", "arc", "opencloud", "m_length", "m_poly",
               "m_angle", "m_radius", "m_dim")


def rollover(w, pos):
    if not active(w) or w._cad_down is not None or w.view._cad_cmd is not None and \
            not w.view._cad_cmd.selecting:
        w._cad_handle = None
        clear_rollover(w)
        return
    v = w.view
    w._cad_handle = handle_at(w, pos)
    if w._cad_handle is not None:
        clear_rollover(w)
        apply_cursor(w)                 # (a resize arrow: a drag here resizes)
        return
    try:
        kind, target = target_at(w, pos, w.to_pdf(pos))
    except Exception:
        target = None
    if target is None:
        clear_rollover(w)
        return
    key = (kind, target if kind == "markup" else target["n"], v.revision, w.index)
    old = getattr(w, "_cad_hover", None)
    if old is not None and old["key"] == key:
        return                          # (the same item: nothing read again)
    lines, fill, width, takes = [], False, 1.0, True
    if kind == "markup" and v.markup_locked(w.index, target):
        takes = False                   # (a locked markup isn't taken: no pick box, no fade)
    elif kind == "markup":
        page = v.doc[w.index]
        annot = page.load_annot(target)
        model = None
        if annot is not None:
            from . import annotations
            model = annotations.read(annot)
        del annot
        if model is not None:
            lines = v.cad_outlines(w.index, "markups", [(target, model)])
            width = float(model.get("props", {}).get("width", 1) or 1)
            # a box-like markup (a shape, a stamp, a text box...) fades all over
            fill = model["kind"] not in _OPEN_KINDS
        del page
    else:
        lines = v.object_lines(w.index, target)
        width = float(target.get("width", 1) or 1)
        fill = target["kind"] != "shape" or bool(target.get("fill"))
    w._cad_hover = {"key": key, "kind": kind, "target": target, "lines": lines[:LIMIT],
                    "fill": fill, "width": width, "takes": takes, "path": None}
    apply_cursor(w)
    w.update()


def clear_rollover(w):
    if getattr(w, "_cad_hover", None) is not None:
        w._cad_hover = None
        if getattr(w, "_cad_handle", None) is None:
            w.unsetCursor()
        w.update()


def _rollover_shown(w):
    """The rollover to draw now, or None (gone stale, or already selected: a selection is
    drawn dashed with grips)."""
    hv = getattr(w, "_cad_hover", None)
    v = w.view
    if hv is None or hv["key"][2] != v.revision or w._cad_down is not None or \
            v._cad_pick is not None or not active(w):
        return None
    if v._cad_cmd is not None and not v._cad_cmd.selecting:
        return None                     # (a command is asking for points, not objects)
    if hv["kind"] == "markup":
        if v.selection is not None and v.selection[0] == w.index and \
                hv["target"] in v.selected_xrefs():
            return None
    elif v.obj_sel is not None and v.obj_sel[0] == w.index and \
            any(it["n"] == hv["target"]["n"] for it in v.obj_sel[1]):
        return None
    return hv


def release(w, e, pos):
    d, w._cad_down = w._cad_down, None
    _outside_update(w)
    _clear(w)
    if d.get("ignore"):
        return
    v = w.view
    if d["mode"] is not None and _a_click(d, e, pos):
        d["mode"] = None                # (a click with the hand moving a little)
    if d["mode"] == "lasso" and len(d["pts"]) >= 3:
        region = Lasso([w.to_pdf(p) for p in d["pts"]])
        pick(w, region, d["dir"] < 0, d["remove"])
    elif d["mode"] == "box" and d["now"] is not None:
        a, b = d["start"], d["now"]
        pick(w, Box(pymupdf.Rect(w.to_pdf(a), w.to_pdf(b))), b.x() < a.x(), d["remove"])
    else:
        kind, target = d["target"]
        if target is not None:
            toggle(w, kind, target, d["remove"])
        elif v.click_click and not d.get("link"):     # (Ctrl+click on a link opens it)
            # the first corner is kept as a point of the page: zooming or scrolling before
            # the second click doesn't move it
            v._cad_pick = {"w": w, "at": w.to_pdf(d["start"]), "now": d["start"],
                           "remove": d["remove"]}
            v.statusMessage.emit(tr("Click the other corner: left to right takes what's "
                                    "inside, right to left what it touches (Escape cancels)"))
    w.update()


def double_click(w, e):
    """A double-click on page widget w in CAD selection (Qt sends it instead of the second
    press). On a markup it edits the markup's text (a text box's words, a shape's comment),
    on the page's own text it opens Edit text there, as in AutoCAD a double-click edits
    text. Otherwise, with Edit objects, it's taken as a click: on a box's first corner
    (clicked again because the first click looked as if it hadn't taken) the box stays
    started. True when handled."""
    if not active(w) or e.button() != Qt.LeftButton:
        return False
    v = w.view
    pk = v._cad_pick
    pos = e.position()
    pdf = w.to_pdf(pos)
    same_spot = pk is not None and pk["w"] is w and \
        (pos - QPointF(w.to_screen_pt(pk["at"]))).manhattanLength() < STILL_PX
    if pk is None or same_spot:
        # (on text, the double-click's first click may have started a box there: the
        # double-click edits instead)
        card = w._card_at(pos)
        xref = card if card is not None else v.annot_at(w.index, pdf)
        text = xref is None and v._line_at(w.index, pdf) is not None
        if xref is not None and not v.markup_locked(w.index, xref) or text:
            cancel(v)
            w._cad_down = {"ignore": True}  # (its release does nothing)
            if text:
                v.clear_object_selection()
                v.edit_text_at(w.index, pdf)
            elif card is not None:
                v.edit_annot_text(w.index, card)
            else:
                v.edit_annot_at(w.index, pdf)
            return True
    if v.tool != "editobjects":
        return False                    # (with Select a double-click selects a word)
    if same_spot:
        w._cad_down = {"ignore": True}  # (its release does nothing)
        return True
    press(w, e, pos, pdf)
    return True


def finish_box(v, pk, e):
    pw = pk["w"]
    if not shiboken6.isValid(pw):
        v._cad_pick = None
        return
    end = QPointF(pw.mapFromGlobal(e.globalPosition()))
    v._cad_pick = None
    _outside_update(pw)
    _clear(pw)
    pw.update()
    a = QPointF(pw.to_screen_pt(pk["at"]))
    if (end - a).manhattanLength() < 3:
        return
    pick(pw, Box(pymupdf.Rect(pw.to_pdf(a), pw.to_pdf(end))), end.x() < a.x(),
         pk["remove"] or _shift(e))


def cancel(v):
    """Escape: drop a click, move, click box in progress. True if there was one."""
    pk = v._cad_pick
    if pk is None:
        return False
    v._cad_pick = None
    if shiboken6.isValid(pk["w"]):
        _clear(pk["w"])
        pk["w"].update()
        _outside_update(pk["w"])
    return True


def drop(v):
    """The document changed, or the tab, tool or mode did: a box or lasso being drawn, and
    its highlight, go (what they'd take was worked out on the drawing as it was)."""
    cancel(v)
    for w in getattr(v, "pages", []):
        if w._cad_down is not None or getattr(w, "_cad_preview", None) is not None or \
                getattr(w, "_preview_job", None) is not None:
            w._cad_down = None
            _clear(w)
            w.update()


def pick(w, region, crossing, remove):
    """Add what the region takes to the selection (or take it out)."""
    v = w.view
    if v.tool == "select":
        v.cad_select_region(w.index, region, crossing, remove)
        return
    # Edit objects in CAD mode takes everything the region holds: the drawing's lines, text
    # and pictures, and the markups drawn on it, in one selection (on one page)
    if not remove:                      # (Shift on another page takes nothing out here)
        if v.obj_sel is not None and v.obj_sel[0] != w.index:
            v.clear_object_selection()
        if v.selection is not None and v.selection[0] != w.index:
            v.clear_selection()
    found = v.cad_objects(w.index, region, crossing)
    took = {it["n"] for it in found}
    have = w._objects_here()
    if remove:
        if have:
            v.select_objects(w.index, [it for it in have if it["n"] not in took])
    else:
        known = {it["n"] for it in have}
        v.select_objects(w.index, have + [it for it in found if it["n"] not in known])
    marks = v.cad_markups_in(w.index, region, crossing)
    mine = v.selected_xrefs() if v.selection is not None and v.selection[0] == w.index else []
    if marks and remove:
        if mine:
            v._set_selection(w.index, [x for x in mine if x not in marks])
    elif marks:
        v._set_selection(w.index, mine + [x for x in marks if x not in mine])
    say(v)


def say(v):
    """The status bar: what CAD mode's selection holds now, and what to do with it."""
    objs = len(v.obj_sel[1]) if v.obj_sel is not None else 0
    marks = len(v.selected_xrefs())
    if not objs and not marks:
        return
    what = ", ".join(x for x in (
        (tr("{n} object") if objs == 1 else tr("{n} objects")).format(n=objs) if objs else "",
        (tr("{n} markup") if marks == 1 else tr("{n} markups")).format(n=marks) if marks
        else "") if x)
    v.statusMessage.emit(tr("Selected {what}: type a command (M move, CO copy, RO rotate...) "
                            "or press Delete; Shift+click takes out, Escape clears").format(
                                what=what))


def toggle(w, kind, target, remove):
    """A click on one item: into the selection (Shift: out of it)."""
    v = w.view
    if kind == "markup" and v.markup_locked(w.index, target):
        v.statusMessage.emit(v.locked_note())
        return
    if v.tool == "editobjects" and not remove:      # (one selection, one page)
        if v.obj_sel is not None and v.obj_sel[0] != w.index:
            v.clear_object_selection()
        if v.selection is not None and v.selection[0] != w.index:
            v.clear_selection()
    if kind == "markup":
        have = v.selected_xrefs() if v.selection is not None and v.selection[0] == w.index \
            else []
        if (target in have) == remove:
            v.select_xref(w.index, target, add=bool(have))
        if v.tool == "editobjects":
            say(v)
        return
    here = {it["n"] for it in w._objects_here()}
    if (target["n"] in here) == remove:
        v.select_objects(w.index, [target], add=True)
    if v.tool == "editobjects":
        say(v)


# ---- the live highlight ---------------------------------------------------------------
def _region(w):
    """(region, crossing) of the box or lasso being drawn on page widget w, or None."""
    d = w._cad_down
    if d is not None and not d.get("ignore"):
        if d["mode"] == "lasso" and len(d["pts"]) >= 3:
            return Lasso([w.to_pdf(p) for p in d["pts"]]), d["dir"] < 0
        if d["mode"] == "box" and d["now"] is not None:
            a, b = d["start"], d["now"]
            return Box(pymupdf.Rect(w.to_pdf(a), w.to_pdf(b))), b.x() < a.x()
    pk = w.view._cad_pick
    if pk is not None and pk["w"] is w:
        a, b = QPointF(w.to_screen_pt(pk["at"])), pk["now"]
        if (b - a).manhattanLength() >= 3:
            return Box(pymupdf.Rect(pk["at"], w.to_pdf(b))), b.x() < a.x()
    return None


FADE = 150                      # how much of the paper's color goes over a faded item (of 255)
SLICE = 0.05                   # seconds of work per step of the live highlight
LIMIT = 3000                    # outlines drawn at most


def _schedule(w):
    """Work out the highlight soon (once for a burst of pointer moves)."""
    t = getattr(w, "_preview_timer", None)
    if t is None:
        t = w._preview_timer = QTimer(w)
        t.setSingleShot(True)
        t.timeout.connect(lambda: _preview(w))
    if not t.isActive():
        t.start(40)


def _key(region, crossing):
    b = region.bounds
    return (type(region).__name__, round(b.x0, 2), round(b.y0, 2), round(b.x1, 2),
            round(b.y1, 2), len(getattr(region, "pts", ())), crossing)


def _preview(w):
    """A short slice of working out the highlight; more slices follow until it's done, so
    the pointer never waits (a big drawing's lines are read a little at a time)."""
    if not shiboken6.isValid(w):
        return
    doc = getattr(w.view, "doc", None)
    if doc is None or doc.is_closed:
        return                          # (the document closed meanwhile)
    try:
        found = _region(w)
        if found is None:
            _clear(w)
            return
        region, crossing = found
        key = _key(region, crossing)
        job = getattr(w, "_preview_job", None)
        if job is None or job["key"] != key:
            job = w._preview_job = {"key": key, "crossing": crossing, "lines": [],
                                    "rects": [], "steps": w.view.cad_preview_steps(
                                        w.index, region, crossing)}
        end = time.monotonic() + SLICE
        done = False
        while time.monotonic() < end:
            try:
                lines, rects = next(job["steps"])
            except StopIteration:
                done = True
                break
            if len(job["lines"]) < LIMIT:
                job["lines"] += lines
            job["rects"] += rects
    except Exception:
        _clear(w)
        return
    w._cad_preview = (job["crossing"], job["lines"][:LIMIT], job["rects"])
    w.update()
    if not done:
        w._preview_timer.start(0)       # the next slice, after the pointer had its turn


def _clear(w):
    t = getattr(w, "_preview_timer", None)
    if t is not None:
        t.stop()
    w._preview_job = None
    if getattr(w, "_cad_preview", None) is not None:
        w._cad_preview = None
        w.update()


# ---- the part of a box or lasso lying off the page, on the gray canvas around it (a box can
# start and end there: a sheet covered by one object leaves no empty paper to start on)
def _shape_now(w):
    """The box ((a, b)) or lasso ([points]) being drawn from page widget w, in w's own
    coordinates, or None."""
    v = w.view
    pk = v._cad_pick
    if pk is not None and pk["w"] is w and shiboken6.isValid(w):
        return "box", (QPointF(w.to_screen_pt(pk["at"])), pk["now"])
    d = w._cad_down
    if d is None or d.get("ignore"):
        return None
    if d["mode"] == "box" and d["now"] is not None:
        return "box", (d["start"], d["now"])
    if d["mode"] == "lasso" and len(d["pts"]) >= 2:
        return "lasso", list(d["pts"])
    return None


def _outside_update(w):
    """Repaint the canvas where the box or lasso is and was (only when it leaves the page:
    on the page, the page widget draws it)."""
    if not shiboken6.isValid(w):
        return
    canvas = w.parentWidget()
    if canvas is None:
        return
    got = _shape_now(w)
    old = getattr(w, "_outside_rect", None)
    rect = None
    if got is not None:
        pts = list(got[1])
        r = QRectF(pts[0], pts[0])
        for q in pts[1:]:
            r = r.united(QRectF(q, q))
        if not QRectF(w.rect()).contains(r):
            rect = r.translated(QPointF(w.pos())).toAlignedRect().adjusted(-4, -4, 4, 4)
    w._outside_rect = rect
    if old is not None:
        canvas.update(old)
    if rect is not None:
        canvas.update(rect)


def paint_outside(view, p):
    """Paint on the canvas (view.widget()) the box or lasso being drawn, wherever it lies off
    its page."""
    w = getattr(view, "_cad_drag_w", None)
    pk = view._cad_pick
    if pk is not None:
        w = pk["w"]
    if w is None or not shiboken6.isValid(w):
        return
    got = _shape_now(w)
    if got is None:
        return
    off = QPointF(w.pos())
    if got[0] == "box":
        a, b = got[1]
        paint_box(p, QPointF(a) + off, QPointF(b) + off)      # (a QPoint + QPointF fails)
    else:
        pts = [QPointF(q) + off for q in got[1]]
        crossing = w._cad_down is not None and w._cad_down.get("dir", 0) < 0
        p.setPen(QPen(GREEN if crossing else BLUE, 1, Qt.DashLine if crossing else Qt.SolidLine))
        p.setBrush(QColor(0, 180, 70, 45) if crossing else QColor(0, 120, 215, 45))
        p.drawPolygon(QPolygonF(pts))
        p.setBrush(Qt.NoBrush)


# ---- resizing a CAD selection of several items (markups, or markups and the drawing's own
# objects) by one box around them all: a handle dragged scales everything in it, one undo
# step (one markup alone has its own handles; the drawing's objects alone, theirs)
def _box_pdf(w):
    """The box around what's selected on page widget w (unrotated page coordinates), when
    it's several markups or markups and objects; else None."""
    v = w.view
    if not v.cad_select:
        return None
    marks = []
    if v.selection is not None and v.selection[0] == w.index:
        marks = v.selected_models_to_paint()
    objs = w._objects_here()
    if not (len(marks) >= 2 or marks and objs):
        return None
    key = (getattr(v, "_gen", 0), v.revision, v.selection, tuple(v.extra), id(v.obj_sel))
    got = getattr(w, "_resize_box", None)
    if got is None or got[0] != key:
        from . import annotations
        from .page_objects import bounding
        rects = [annotations.bounds(m) for _x, m in marks]
        if objs:
            rects.append(v.selected_objects_rect())
        got = w._resize_box = (key, bounding(rects))
    return pymupdf.Rect(got[1])


def resize_box(w):
    """The box's rectangle on w's screen (a little outside what it holds), or None."""
    r = _box_pdf(w)
    if r is None or r.is_empty and r.width == 0 and r.height == 0:
        return None
    return QRectF(w.to_screen(r)).adjusted(-4, -4, 4, 4)


def _resized(box, mode, d, free):
    left, top, right, bottom = box.left(), box.top(), box.right(), box.bottom()
    if "l" in mode:
        left += d.x()
    if "r" in mode:
        right += d.x()
    if "t" in mode:
        top += d.y()
    if "b" in mode:
        bottom += d.y()
    new = QRectF(QPointF(left, top), QPointF(right, bottom)).normalized()
    if len(mode) == 2 and not free and box.width() > 0 and box.height() > 0:
        # a corner keeps the proportions (Shift: free)
        s_ = max(new.width() / box.width(), new.height() / box.height())
        wd, ht = box.width() * s_, box.height() * s_
        ax = box.right() if "l" in mode else box.left()
        ay = box.bottom() if "t" in mode else box.top()
        new = QRectF(ax - wd if "l" in mode else ax, ay - ht if "t" in mode else ay, wd, ht)
    return new


def resize_move(w, e, pos):
    rz = w._cad_resize
    if (pos - rz["start"]).manhattanLength() >= 3:
        rz["now"] = _resized(rz["box"], rz["mode"], pos - rz["start"], _shift(e))
        w.update()


def resize_release(w, e, pos):
    rz, w._cad_resize = w._cad_resize, None
    w.update()
    if rz["now"] is None:
        return
    new = _resized(rz["box"], rz["mode"], pos - rz["start"], _shift(e))
    old = rz["box"]
    if new.width() < 4 or new.height() < 4 or old.width() <= 0 or old.height() <= 0:
        return
    # the change on the screen (the boxes are 4 px outside what they hold), as a change of
    # the page: through the page's own turn and the zoom, as it's drawn
    io = old.adjusted(4, 4, -4, -4)
    nw = new.adjusted(4, 4, -4, -4)
    if io.width() <= 0 and io.height() <= 0:
        return
    sx = nw.width() / io.width() if io.width() > 0 else 1.0
    sy = nw.height() / io.height() if io.height() > 0 else 1.0
    if sx <= 0 or sy <= 0:
        return
    page = w.view.doc[w.index]
    z = w.view.zoom
    to_screen = pymupdf.Matrix(page.rotation_matrix) * pymupdf.Matrix(z, z)
    del page
    on_screen = pymupdf.Matrix(1, 0, 0, 1, -io.left(), -io.top()) * \
        pymupdf.Matrix(sx, 0, 0, sy, 0, 0) * pymupdf.Matrix(1, 0, 0, 1, nw.left(), nw.top())
    mat = to_screen * on_screen * ~to_screen
    w.view.cad_apply(tr("Resized"), mat)


def paint_resize(w, p):
    rz = getattr(w, "_cad_resize", None)
    blue = QColor(0, 120, 215)
    if rz is not None:
        if rz["now"] is not None:
            p.setPen(QPen(blue, 1, Qt.DashLine))
            p.setBrush(Qt.NoBrush)
            p.drawRect(rz["now"])
        return
    if w._cad_down is not None or w.view._cad_pick is not None:
        return
    box = resize_box(w)
    if box is None:
        return
    from .page_widget import box_handles
    p.setPen(QPen(blue, 1, Qt.DashLine))
    p.setBrush(Qt.NoBrush)
    p.drawRect(box)
    p.setPen(QPen(blue, 1))
    p.setBrush(Qt.white)
    for r in box_handles(box).values():
        p.drawRect(r)
    p.setBrush(Qt.NoBrush)


def paint_box(p, a, b):
    """A selection box from a to b: left to right a blue window, right to left a green dashed
    crossing box."""
    crossing = b.x() < a.x()
    p.setPen(QPen(GREEN if crossing else BLUE, 1, Qt.DashLine if crossing else Qt.SolidLine))
    p.setBrush(QColor(0, 180, 70, 45) if crossing else QColor(0, 120, 215, 45))
    p.drawRect(QRectF(a, b).normalized())
    p.setBrush(Qt.NoBrush)


def _glow_path(w, pv):
    """The highlight's lines (pv: w._cad_preview) on w's screen, as one path."""
    from .page_widget import lines_path
    t = w._screen_transform(w.view.doc[w.index])
    key = (t.m11(), t.m12(), t.m21(), t.m22(), t.dx(), t.dy())
    got = getattr(w, "_glow", None)
    if got is None or got[0] is not pv or got[1] != key:
        got = w._glow = (pv, key, t.map(lines_path(pv[1])))
    return got[2]


def paint(w, p):
    paint_resize(w, p)
    hv = _rollover_shown(w)
    if hv is not None and hv["takes"] and hv["lines"]:
        # the item drawn lighter: the paper's color over it, part see-through
        from PySide6.QtGui import QPainterPath
        t = w._screen_transform(w.view.doc[w.index])
        zoom = (t.m11(), t.m12(), t.m21(), t.m22(), t.dx(), t.dy())
        if hv["path"] is None or hv["path"][0] != zoom:
            area = None
            if hv["fill"]:
                area = QPainterPath()
                area.setFillRule(Qt.WindingFill)
                for line in hv["lines"]:
                    if len(line) >= 3:
                        area.addPolygon(QPolygonF([QPointF(q[0], q[1]) for q in line]))
                area = t.map(area)
            # (each line one stroke: drawn piece by piece, the see-through color doubles up
            # where the pieces meet and a curve looks dotted)
            strokes = QPainterPath()
            for line in hv["lines"]:
                if len(line) >= 2:
                    strokes.moveTo(line[0][0], line[0][1])
                    for q in line[1:]:
                        strokes.lineTo(q[0], q[1])
            hv["path"] = (zoom, t.map(strokes), area)
        paper = QColor(0, 0, 0) if getattr(w.view, "night_mode", False) else \
            QColor(255, 255, 255)
        paper.setAlpha(FADE)
        if hv["path"][2] is not None:
            p.fillPath(hv["path"][2], paper)
        scale = (abs(t.m11() * t.m22() - t.m12() * t.m21())) ** 0.5
        p.setPen(QPen(paper, max(3.0, hv["width"] * scale + 2)))
        p.drawPath(hv["path"][1])
    pv = getattr(w, "_cad_preview", None)
    if pv is not None and (w._cad_down is not None or w.view._cad_pick is not None):
        crossing, lines, rects = pv
        color = QColor(GREEN if crossing else BLUE)
        # (a soft glow: what the box would take. What's selected is drawn dashed, with
        # grips, so the two never look alike)
        glow = QColor(color)
        glow.setAlpha(110)
        # one path, made once per step of the highlight and zoom: it's drawn on every pointer
        # move (a point at a time, each loading the page, took 300 ms for 3,000 lines), with
        # square ends (round ends on a path of many pieces are a hundred times slower)
        p.setPen(QPen(glow, 6))
        p.drawPath(_glow_path(w, pv))
        fill = QColor(color)
        fill.setAlpha(70)
        for r in rects:
            p.fillRect(w.to_screen(r), fill)
    pk = w.view._cad_pick
    if pk is not None and pk["w"] is w:
        a = QPointF(w.to_screen_pt(pk["at"]))
        paint_box(p, a, pk["now"])
        # the first corner, marked at once: the box shows it took before the pointer moves
        p.setPen(QPen(BLUE, 1.5))
        p.drawLine(a + QPointF(-7, 0), a + QPointF(7, 0))
        p.drawLine(a + QPointF(0, -7), a + QPointF(0, 7))
        p.drawRect(QRectF(a.x() - 3, a.y() - 3, 6, 6))
    d = w._cad_down
    if d is None or d.get("ignore"):
        return
    if d["mode"] == "box" and d["now"] is not None:
        paint_box(p, d["start"], d["now"])
    elif d["mode"] == "lasso" and len(d["pts"]) >= 2:
        crossing = d["dir"] < 0
        p.setPen(QPen(GREEN if crossing else BLUE, 1, Qt.DashLine if crossing else Qt.SolidLine))
        p.setBrush(QColor(0, 180, 70, 45) if crossing else QColor(0, 120, 215, 45))
        p.drawPolygon(QPolygonF(d["pts"]))
        p.setBrush(Qt.NoBrush)
