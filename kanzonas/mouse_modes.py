"""Mouse mode: Standard, Hand or CAD (File > Preferences > Mouse, the View menu, the ribbon's
Home tab; F11 switches CAD on and off). The mode sets the default tool (the one at start-up
and the one Escape goes back to) and how the wheel, the pointer and selecting behave. Each
mode has its own options, switched on and off in Preferences.

Settings: "mouse_mode", and "mouse/<mode>/<option>" ("true" / "false") for each option.
"""
from .i18n import tr

MODES = ("standard", "hand", "cad")


def labels():
    return {"standard": tr("Standard"), "hand": tr("Hand"), "cad": tr("CAD")}


def descriptions():
    return {
        "standard": tr("The arrow: select text and markups; the wheel scrolls, Ctrl+wheel zooms."),
        "hand": tr("The Hand: drag to move the page; click a markup to select it; the wheel "
                   "scrolls."),
        "cad": tr("Like CAD programs: the wheel zooms at the cursor, hold the wheel to pan, a "
                  "plus cursor, window and crossing selection, and the CAD tab's commands.")}


def options(mode):
    """[(option, label, default)] for a mode, in the order Preferences shows them."""
    page_wheel = ("page_wheel", tr("Scroll one page per wheel step"), True)
    if mode == "standard":
        return [page_wheel,
                ("free_pan", tr("Free page movement (drag the page past its edges)"), False)]
    if mode == "hand":
        return [("free_pan", tr("Free page movement (drag the page past its edges)"), True),
                page_wheel,
                ("hand_selects", tr("Clicking a markup with the Hand selects it"), True)]
    return [("wheel_zoom", tr("The wheel zooms at the cursor (Ctrl+wheel scrolls)"), True),
            ("plus_cursor", tr("Plus cursor"), True),
            ("free_pan", tr("Open canvas around the pages (drag the drawing anywhere)"), True),
            ("cad_select", tr("Window (blue) and crossing (green) selection: clicks add to the "
                              "selection, Shift takes out, Escape clears"), True),
            ("click_click", tr("Click, move, click draws the selection box"), True),
            ("lasso", tr("Hold the button and drag to draw a lasso"), True),
            ("cad_tab", tr("Show the CAD tab (Move, Copy, Rotate...)"), True)]


def mode(settings):
    """The mouse mode in use. Before 1.5 there was CAD-style mouse on / off and a default
    tool (Hand or Select): those choices carry over."""
    m = settings.value("mouse_mode", "")
    if m in MODES:
        return m
    if settings.value("cad_mouse", "false") == "true":
        return "cad"
    return "standard" if settings.value("start_tool", "hand") == "select" else "hand"


def option(settings, m, key):
    for k, _label, default in options(m):
        if k == key:
            if m in ("standard", "hand") and key == "page_wheel" and \
                    settings.value("mouse/%s/%s" % (m, key)) is None:
                # (before 1.5 one setting for every mode)
                return settings.value("page_wheel", "true") != "false"
            v = settings.value("mouse/%s/%s" % (m, key))
            return default if v is None else v == "true"
    return False


def set_option(settings, m, key, on):
    settings.setValue("mouse/%s/%s" % (m, key), "true" if on else "false")


def default_tool(m):
    return "hand" if m == "hand" else "select"


def apply(settings):
    """Set the view behaviors (DocumentView's class attributes) for the mode in use."""
    from .document_view import DocumentView
    m = mode(settings)
    DocumentView.mouse_mode = m
    listed = {k for k, _label, _default in options(m)}
    for key in ("page_wheel", "free_pan", "hand_selects", "wheel_zoom", "plus_cursor",
                "cad_select", "click_click", "lasso"):
        # an option a mode doesn't list keeps its usual behavior there: the Hand tool picked
        # in Standard or CAD mode still selects the markup it clicks
        on = option(settings, m, key) if key in listed else UNLISTED.get(key, False)
        setattr(DocumentView, key, on)
    return m


UNLISTED = {"hand_selects": True}
