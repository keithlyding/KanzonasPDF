"""Click, move, click in CAD mode, as AutoCAD's grips (the owner, 23 Nov 2026: "in cad mouse
mode, the mouse clicks need to function like a cad mouse. No clicking and holding for
anything"):

- a click on a grip of what's selected (a corner or side of its box, a line's end or middle, a
  polygon's corner, the round handle that turns it) makes the grip hot: it follows the
  pointer with no button held, and the next click puts it there;
- a click on what's selected (not on a grip) picks it up: it follows the pointer, and the next
  click puts it down, or a distance typed on the command line moves it that far toward the
  pointer (typed below);
- with the Pen, a click starts the stroke, the pointer draws it and the next click ends it;
  with Highlight and the other text tools, a click starts at a letter and the next ends;
- Escape or a right-click puts everything back as it was. A press, drag and release is a
  click and a move: the next click still places.

Each click, move, click is one undo step (the same step a drag made before). While a grip is
hot, the pointer's moves and the next click go to the page it's on, wherever they happen
(another page, the gray around the pages), in that page's own coordinates.

The Standard and Hand modes still drag. In CAD mode, Preferences > Mouse, "Click, move, click"
off makes these drags again.
"""
import shiboken6
from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QMouseEvent

from .i18n import tr


def clicks(v):
    """True in CAD mode with its click, move, click option on (Preferences > Mouse)."""
    return getattr(v, "mouse_mode", None) == "cad" and getattr(v, "click_click", False)


def on(v):
    """True when a press on a grip or on what's selected in view v starts a click, move,
    click (clicks, and no CAD command asking for points or a selection)."""
    return clicks(v) and getattr(v, "_cad_cmd", None) is None


def _busy(w):
    """What page widget w holds that a click places: "resize" (a box around several items),
    "move" (the selection picked up), "objects" (the drawing's objects' handle), "markup"
    (a markup's grip), "ink" (a stroke being drawn), "text" (text being highlighted, struck
    out...), or None."""
    if getattr(w, "_cad_resize", None) is not None:
        return "resize"
    d = w._cad_down
    if d is not None and d.get("mode") == "drag":
        return "move"
    if w._obj_edit is not None:
        return "objects"
    if w._edit is not None:
        return "markup"
    if w._ink and getattr(w, "_hot_ink", False):
        return "ink"
    if w._text_sel is not None and getattr(w, "_hot_text", False):
        return "text"
    return None


def owner(v):
    """The page widget with a hot grip, a selection picked up or a stroke being drawn, or
    None."""
    w = getattr(v, "_cad_hot", None)
    if w is None:
        return None
    if not shiboken6.isValid(w) or _busy(w) is None:
        v._cad_hot = None               # (placed, dropped, or the pages were rebuilt)
        return None
    return w


def hold(w):
    """A press on page widget w just started a resize, a grip, a move or a stroke: in CAD
    mode it stays hot (its release does nothing) until the next click. True if it does."""
    v = w.view
    what = _busy(w)
    if not on(v) or what is None:
        return False
    v._cad_hot = w
    if getattr(w, "_cad_hover", None) is not None:
        from . import cad_select
        cad_select.clear_rollover(w)
    ed = w._obj_edit if what == "objects" else w._edit if what == "markup" else None
    if what == "ink":
        say = tr("Move to draw, click to end the stroke (Escape or a right-click cancels)")
    elif what == "text":
        say = tr("Move to where the text ends, click there (Escape or a right-click cancels)")
    elif ed is not None and ed.get("mode") == "rot":
        say = tr("Move to turn it, click to set the angle; Shift: 15° steps (Escape or a "
                 "right-click puts it back)")
    elif what == "move":
        say = tr("Move it, click where it goes, or type the distance toward the pointer and "
                 "press Enter (Escape or a right-click puts it back)")
    else:
        say = tr("Move the grip, click where it goes (Escape or a right-click puts it back)")
    v.statusMessage.emit(say)
    return True


def mapped(w, e):
    """Mouse event e (on another widget) as page widget w sees it."""
    local = QPointF(w.mapFromGlobal(e.globalPosition()))
    return QMouseEvent(e.type(), local, e.globalPosition(), e.button(), e.buttons(),
                       e.modifiers())


def move(w, e):
    """The pointer moved (e: in w's coordinates, with or without a button held): what's hot
    follows it, as a drag's preview does."""
    from . import cad_select
    pos = e.position()
    what = _busy(w)
    if what == "resize":
        cad_select.resize_move(w, e, pos)
    elif what == "move":
        cad_select.move(w, e, pos)
    elif what in ("objects", "markup"):
        w._edit_move(e, pos)
    elif what == "ink":
        if (pos - w._ink[-1]).manhattanLength() >= 1:
            w._ink.append(pos)
            w.update()
    elif what == "text":
        w._text_drag_move(pos)


def place(w, e):
    """The click that ends it (e: in w's coordinates): the change is made, one undo step."""
    from . import cad_select
    move(w, e)                          # (where the click is, if no move came first)
    w.view._cad_hot = None
    pos = e.position()
    what = _busy(w)
    w.unsetCursor()
    if what == "resize":
        cad_select.resize_release(w, e, pos)
    elif what == "move":
        cad_select.release(w, e, pos)
    elif what == "objects":
        w._objects_release(e, pos)
    elif what == "markup":
        w._edit_release(e, pos)
    elif what == "ink":
        w._hot_ink = False
        pts = [w.to_pdf(p) for p in w._ink]
        w._ink = []
        w.update()
        if len(pts) > 1:
            w.view.apply_ink(w.index, pts)
    elif what == "text":
        w._hot_text = False
        w._text_release(e, pos)


def cancel(v, quiet=False):
    """Escape, a right-click, the tool or the document changed: what's hot goes back where it
    was (nothing was changed yet; quiet: nothing said). True if something was hot."""
    w = owner(v)
    v._cad_hot = None
    if w is None:
        return False
    from . import cad_select
    w._cad_resize = None
    w._cad_down = None
    w._obj_edit = None
    w._edit = None
    w._ink = []
    w._hot_ink = False
    if getattr(w, "_hot_text", False):
        w._hot_text = False
        w._text_sel = w._text_mode = None
        w._marquee = False
        w._drag_start = w._drag_now = None
        v._set_text_drag(None)
    w._snap_mark = None
    w._snap_guides = []
    w._end_drop()
    cad_select._clear(w)
    cad_select._outside_update(w)
    w.unsetCursor()
    w.update()
    if not quiet:
        v.statusMessage.emit(tr("Put back as it was"))
    return True


def press(w, e):
    """A press anywhere on page widget w (e in w's coordinates) while something is hot on
    view v: the left button places it, the right one puts it back. True if it was taken;
    the press's release then does nothing (w._swallow)."""
    v = w.view
    hot = owner(v)
    if hot is None or e.button() not in (Qt.LeftButton, Qt.RightButton):
        return False
    w._swallow = True
    if e.button() == Qt.RightButton:
        cancel(v)
    else:
        place(hot, e if hot is w else mapped(hot, e))
    return True


def typed(v, text):
    """Text and Enter on the CAD command line while no command runs. With the selection
    picked up, a length moves it that far toward the pointer, as AutoCAD's direct distance
    entry (in the page's measuring unit, as Circle's radius; True: it was taken). With a grip
    hot, the grip is put back and the text runs as typed (False)."""
    w = owner(v)
    if w is None:
        return False
    if _busy(w) != "move":
        cancel(v, quiet=True)
        return False
    t = text.strip()
    if not t:
        return True                     # (Enter alone: it still follows the pointer)
    from . import measure, measure_ui
    page = v.doc[w.index]
    m_per_pt, unit, _label, _set = measure.get_scale(page)
    del page
    if t.count(",") == 1 and "." not in t:
        t = t.replace(",", ".")         # (a decimal comma, as the command line takes it)
    try:
        far = measure_ui.parse_length(t, unit) / m_per_pt
    except (ValueError, ZeroDivisionError, KeyError):
        far = None
    d = w._cad_down
    a, b = w.to_pdf(d["start"]), w.to_pdf(d["now"] if d["now"] is not None else d["start"])
    way = b - a
    if far is None or not 0 < far < 1e6 or abs(way) < 1e-6:
        v.statusMessage.emit(tr("Point the way it goes, then type the distance as a number (or "
                                "12'-6\") and press Enter; or click where it goes"))
        return True
    import pymupdf
    step = way * (far / abs(way))
    v._cad_hot = None
    w._cad_down = None
    w._snap_mark = None
    from . import cad_select
    cad_select._clear(w)
    cad_select._outside_update(w)
    w.unsetCursor()
    w.update()
    v.cad_apply(tr("Moved"), pymupdf.Matrix(1, 0, 0, 1, step.x, step.y))
    return True


def double_click(w, e):
    """A double-click on page widget w while something is hot (Qt sends it in place of the
    second press). On what was just picked up, or where text marking started, still where it
    was, it's a double-click there: what the first click started is dropped and the
    double-click edits or selects a word (False: the caller goes on). Else it's the click
    that places (True)."""
    hot = owner(w.view)
    if hot is None:
        return False
    what = _busy(hot)
    if e.button() == Qt.LeftButton and what in ("move", "text"):
        from . import cad_select
        start = hot._cad_down["start"] if what == "move" else hot._drag_start
        at = mapped(hot, e).position()
        if (at - start).manhattanLength() < cad_select.STILL_PX:
            cancel(w.view, quiet=True)
            return False
    return press(w, e)
