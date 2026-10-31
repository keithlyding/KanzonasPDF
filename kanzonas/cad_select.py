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

from .page_objects import Box, Lasso

BLUE = QColor(0, 120, 215)
GREEN = QColor(0, 150, 60)


def active(w):
    v = w.view
    return v.cad_select and v.tool in ("select", "editobjects")


def _shift(e):
    return bool(e.modifiers() & Qt.ShiftModifier)


def press(w, e, pos, pdf):
    """A left press on page widget w (CAD mode, Select or Edit objects)."""
    v = w.view
    pick = v._cad_pick
    if pick is not None:                # the second click of a click, move, click box
        finish_box(v, pick, e)
        w._cad_down = {"ignore": True}
        return
    remove = _shift(e)
    if v.tool == "select":
        model = w._selected_here()
        if model is not None and not v.extra and not remove:
            for hid, r in w._handles(model).items():       # handles still resize
                if r.adjusted(-3, -3, 3, 3).contains(pos):
                    w._edit = {"mode": hid, "start": pos, "model": model, "preview": None}
                    return
        xref = w._card_at(pos)
        target = ("markup", xref if xref is not None else v.annot_at(w.index, pdf))
    else:
        if w._objects_here() and not remove:
            for hid, r in w._objects_handles().items():
                if r.adjusted(-3, -3, 3, 3).contains(pos):
                    w._obj_edit = {"mode": hid, "start": pos, "preview": None}
                    return
        target = ("object", v.object_at(w.index, pdf))
    w._cad_down = {"start": pos, "pts": [pos], "dir": 0, "mode": None, "now": None,
                   "target": target, "remove": remove,
                   "link": getattr(w, "_link_press", None) is not None}


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


def hover(w, e):
    """Pointer moved without a button: the click, move, click box follows it."""
    pick = w.view._cad_pick
    if pick is None:
        return
    pw = pick["w"]
    if not shiboken6.isValid(pw):       # (the pages were rebuilt)
        w.view._cad_pick = None
        return
    pick["now"] = QPointF(pw.mapFromGlobal(e.globalPosition()))
    _schedule(pw)
    pw.update()


def release(w, e, pos):
    d, w._cad_down = w._cad_down, None
    _clear(w)
    if d.get("ignore"):
        return
    v = w.view
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
    w.update()


def finish_box(v, pk, e):
    pw = pk["w"]
    if not shiboken6.isValid(pw):
        v._cad_pick = None
        return
    end = QPointF(pw.mapFromGlobal(e.globalPosition()))
    v._cad_pick = None
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
    found = v.cad_objects(w.index, region, crossing)
    took = {it["n"] for it in found}
    have = w._objects_here()
    if remove:
        v.select_objects(w.index, [it for it in have if it["n"] not in took])
    else:
        known = {it["n"] for it in have}
        v.select_objects(w.index, have + [it for it in found if it["n"] not in known])


def toggle(w, kind, target, remove):
    """A click on one item: into the selection (Shift: out of it)."""
    v = w.view
    if kind == "markup":
        have = v.selected_xrefs() if v.selection is not None and v.selection[0] == w.index \
            else []
        if (target in have) == remove:
            v.select_xref(w.index, target, add=bool(have))
        return
    here = {it["n"] for it in w._objects_here()}
    if (target["n"] in here) == remove:
        v.select_objects(w.index, [target], add=True)


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


def paint_box(p, a, b):
    """A selection box from a to b: left to right a blue window, right to left a green dashed
    crossing box."""
    crossing = b.x() < a.x()
    p.setPen(QPen(GREEN if crossing else BLUE, 1, Qt.DashLine if crossing else Qt.SolidLine))
    p.setBrush(QColor(0, 180, 70, 45) if crossing else QColor(0, 120, 215, 45))
    p.drawRect(QRectF(a, b).normalized())
    p.setBrush(Qt.NoBrush)


def paint(w, p):
    pv = getattr(w, "_cad_preview", None)
    if pv is not None and (w._cad_down is not None or w.view._cad_pick is not None):
        crossing, lines, rects = pv
        color = QColor(GREEN if crossing else BLUE)
        p.setPen(QPen(color, 2.5))
        for line in lines:
            pts = [QPointF(w.to_screen_pt(q)) for q in line]
            for a, b in zip(pts, pts[1:]):
                p.drawLine(a, b)
        fill = QColor(color)
        fill.setAlpha(70)
        for r in rects:
            p.fillRect(w.to_screen(r), fill)
    pk = w.view._cad_pick
    if pk is not None and pk["w"] is w:
        paint_box(p, QPointF(w.to_screen_pt(pk["at"])), pk["now"])
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
