"""Drawing shapes in CAD mode, as in AutoCAD and Bluebeam: click where the shape starts, move
(the preview follows the pointer with no button held), click where it ends. A press, drag and
release still draws it too. Escape or a right-click cancels a shape in progress.

The first point is kept as a point of the page (view._cad_shape["at"]), so zooming or
scrolling between the two clicks doesn't move it (as cad_select.py keeps the first corner of
its click, move, click box). Snapping, Shift (45 degrees, square or circle) and what each tool
does at the end (a text box asks for its text, Crop asks which pages...) are the same as with
a drag: the second click ends it through the same DocumentView.apply_drag_tool.

The Circle tool draws from its center to a point on the circle; while its second point is
awaited, the radius can be typed on the CAD command line (typed below).
"""
import math

import shiboken6
from PySide6.QtCore import QPointF

from .i18n import tr

# the two-point tools drawn click, move, click in CAD mode (the Image tool still places a
# picture with one click)
TOOLS = {"textbox", "rect", "ellipse", "circle", "mask", "line", "arrow", "eraser", "cloud",
         "callout", "m_length", "m_calibrate", "m_radius", "placeholder", "erasecontent",
         "capture", "crop", "link"}
# a second click on the first point ends these as a click does (a text box of the default
# size, new link text there, a callout); for the rest it would make nothing, so the shape
# stays in progress (a double-click that shook doesn't lose it)
CLICK_ENDS = {"textbox", "placeholder", "link", "callout"}
CLICK_PX = 10           # a press released less than this far from where it went down is a click
QUICK_PX = 24           # ... and one released within QUICK_MS this far away too (a quick
QUICK_MS = 250          #     click whose hand shook)
SAME_PX = 4             # second point this close to the first: the same point
MIN_RADIUS = 0.5        # pt: the smallest circle the Circle tool makes (DocumentView.apply_drag_tool)


def on(v):
    """True when the view's shape tools draw click, move, click (CAD mouse mode)."""
    return getattr(v, "mouse_mode", None) == "cad" and v.tool in TOOLS


def is_click(down, up, ms):
    """A press at down and release at up, ms milliseconds apart: a click (not a drag)?"""
    d = math.hypot(up.x() - down.x(), up.y() - down.y())
    return d < CLICK_PX or (ms is not None and 0 <= ms < QUICK_MS and d < QUICK_PX)


def pending(v):
    """The shape in progress on view v ({"w", "index", "xref", "tool", "at", "now"}), or
    None. One that no longer fits (the tool, the mode or the page changed) is dropped."""
    pk = getattr(v, "_cad_shape", None)
    if pk is None:
        return None
    w = pk["w"]
    doc = getattr(v, "doc", None)
    if not shiboken6.isValid(w) or doc is None or doc.is_closed or not on(v) or \
            getattr(v, "_cad_cmd", None) is not None or v.tool != pk["tool"] or \
            w.index != pk["index"] or pk["index"] >= doc.page_count or \
            doc.page_xref(pk["index"]) != pk["xref"]:
        cancel(v)
        return None
    return pk


def start(w, e, a, b):
    """The release of a press from a to b (widget points) with a shape tool on page widget w:
    in CAD mode a click starts the shape (True); a drag is drawn as before (False)."""
    v = w.view
    if not on(v) or getattr(v, "_cad_cmd", None) is not None:
        return False
    down = getattr(w, "_shape_press", None)     # (raw press position, its time in ms)
    raw = e.position()
    ms = None
    if down is not None:
        ms = e.timestamp() - down[1]
        if not is_click(down[0], raw, ms):
            return False
    elif not is_click(a, b, None):
        return False
    tool = v.tool
    pdf = w.to_pdf(a)
    # a click on a markup with the Eraser deletes it, and on a link with the Links tool
    # changes it, at once (as before): only a click on empty paper starts a box
    if tool == "eraser" and v.annot_at(w.index, pdf) is not None:
        return False
    if tool == "link" and v.link_at(w.index, pdf) is not None:
        return False
    v._cad_shape = {"w": w, "index": w.index, "xref": v.doc.page_xref(w.index), "tool": tool,
                    "at": pdf, "now": w.to_pdf(b)}
    w._drag_start = w._drag_now = None
    w._shape_press = None
    w.update()
    if tool == "circle":
        v.statusMessage.emit(tr("Circle: click a point on the circle, or type the radius and "
                                "press Enter (Escape cancels)"))
    else:
        v.statusMessage.emit(tr("Click where it ends (Escape or a right-click cancels)"))
    return True


def _map(pw, e):
    return QPointF(pw.mapFromGlobal(e.globalPosition()))


def hover(w, e):
    """The pointer moved with no button held (over page widget w): the shape in progress
    follows it. True if there is one."""
    pk = pending(w.view)
    if pk is None:
        return False
    pw = pk["w"]
    if pw is not w and w._snap_mark is not None:
        w._snap_mark = None
        w.update()
    a = pw.to_screen_pt(pk["at"])
    b = pw._shape_point(_map(pw, e), e, a)
    pk["now"] = pw.to_pdf(b)
    pw.update()
    return True


def points(w):
    """(first point, pointer) in w's widget coordinates while w has the shape in progress
    (or its second click is down)."""
    pk = getattr(w.view, "_cad_shape", None)
    if pk is None or pk["w"] is not w:
        done = getattr(w, "_shape_end", None)
        if done is None or done[0]["w"] is not w:
            return None
        pk = done[0]
    return w.to_screen_pt(pk["at"]), w.to_screen_pt(pk["now"])


def finish(w, e):
    """The second click (a press anywhere on a page; e arrived at page widget w): the shape
    ends there, snapped like the drag's end. True if a shape was in progress. It's made when
    the button comes up (released below), as a dragged one is: a text box's or Crop's
    question doesn't open while the button is held."""
    v = w.view
    released(w)                         # (an ended shape whose release never came)
    pk = pending(v)
    if pk is None:
        return False
    pw = pk["w"]
    a = pw.to_screen_pt(pk["at"])
    b = pw._shape_point(_map(pw, e), e, a)
    same = (b - a).manhattanLength() < SAME_PX
    if same and pk["tool"] not in CLICK_ENDS:
        return True                     # (nothing to draw yet: it goes on)
    v._cad_shape = None
    pk["now"] = pw.to_pdf(b)
    w._shape_end = (pk, same)
    pw.update()
    return True


def released(w):
    """The left button came up on page widget w: make the shape its press ended. True if
    there was one."""
    done = getattr(w, "_shape_end", None)
    if done is None:
        return False
    w._shape_end = None
    pk, same = done
    v = w.view
    if shiboken6.isValid(pk["w"]) and pk["w"].index == pk["index"] and \
            pk["index"] < v.doc.page_count and v.doc.page_xref(pk["index"]) == pk["xref"]:
        end(v, pk, pk["now"], same)
    return True


def end(v, pk, b, same=False):
    """Make the shape from the first point to page point b."""
    v._cad_shape = None
    pw = pk["w"]
    pw._snap_mark = None
    pw.update()
    v.apply_drag_tool(pk["index"], pk["tool"], pk["at"], b, same)


def cancel(v):
    """Escape, a right-click, another tool: drop the shape in progress. True if there was
    one."""
    pk = getattr(v, "_cad_shape", None)
    if pk is None:
        return False
    v._cad_shape = None
    if shiboken6.isValid(pk["w"]):
        pk["w"]._snap_mark = None
        pk["w"].update()
    return True


def typed(v, text):
    """Text and Enter on the CAD command line while no command runs. A circle in progress
    takes it as its radius (in the page's measuring unit; True: it was taken). Another shape
    in progress is dropped (a command typed now runs instead)."""
    pk = pending(v)
    if pk is None:
        return False
    if pk["tool"] != "circle":
        cancel(v)
        return False
    if not text.strip():
        return True                     # (Enter alone: still waiting for the radius)
    from . import measure, measure_ui
    page = v.doc[pk["index"]]
    m_per_pt, unit, _label, _set = measure.get_scale(page)
    t = text.strip()
    if t.count(",") == 1 and "." not in t:
        # a decimal comma, as the command line's other values take it (2,5 = 2.5, not 25)
        t = t.replace(",", ".")
    try:
        r = measure_ui.parse_length(t, unit) / m_per_pt
    except (ValueError, ZeroDivisionError, KeyError):
        r = None
    # (a radius under half a point would draw nothing: Circle makes none that small)
    if r is None or not MIN_RADIUS < r < 1e6:
        v.statusMessage.emit(tr("Circle: type the radius as a number (or 12'-6\"), or click a "
                                "point on the circle"))
        return True
    import pymupdf
    at = pymupdf.Point(pk["at"])
    end(v, pk, pymupdf.Point(at.x + r, at.y))
    return True
