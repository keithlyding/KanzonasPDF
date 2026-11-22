"""View > Show line weights, off: every line of the page's drawing shown thin on screen (as
AutoCAD's lineweight display turned off), whatever width the drawing gives it.

The page's parsed drawing (its DisplayList, which already leaves out the layers hidden in the
Layers panel) is played once through a device that passes everything on unchanged to a new
DisplayList, except that each line is stroked with a width of 0 (the thinnest a device can
draw). The screen draws from that list as from the page's own, with Enhance thin lines' one
pixel minimum, so every line shows one pixel wide. The document isn't changed: printing,
export, OCR and Compare draw from the page and keep the true widths. Markups keep theirs (they
are drawn over the content separately).

MuPDF has no setting for this (only a minimum line width, which Enhance thin lines uses). The
device is PyMuPDF's FzDevice2 (as its own get_drawings device), one Python call per drawing
call: about 0.2 s for a sheet of 60,000 separate lines, once per page and change."""
import pymupdf

_m = pymupdf.mupdf
_raw = _m._mupdf          # (the plain wrappers: the friendlier ones turn color pointers into tuples)

# every drawing call a device gets, passed on as it is (begin_tile has its own call: see there)
_CALLS = ("fill_path", "clip_path", "clip_stroke_path", "fill_text", "stroke_text", "clip_text",
          "clip_stroke_text", "ignore_text", "fill_shade", "fill_image", "fill_image_mask",
          "clip_image_mask", "pop_clip", "begin_mask", "end_mask", "begin_group", "end_group",
          "end_tile", "render_flags", "set_default_colorspaces", "begin_layer", "end_layer",
          "begin_structure", "end_structure", "begin_metatext", "end_metatext")


class _Thin(_m.FzDevice2):
    """Passes every call on to target (a list device), each line stroked 0 wide."""

    def __init__(self, target):
        super().__init__()
        self.target = target
        self.failed = None
        for name in _CALLS + ("stroke_path", "begin_tile"):
            getattr(self, "use_virtual_" + name)()

    def stroke_path(self, ctx, path, stroke, ctm, colorspace, color, alpha, params):
        try:
            thin = _raw.ll_fz_clone_stroke_state(stroke)
            thin.linewidth = 0
            try:
                _raw.ll_fz_stroke_path(self.target, path, thin, ctm, colorspace, color, alpha,
                                       params)
            finally:
                _raw.ll_fz_drop_stroke_state(thin)
        except Exception as ex:
            self.failed = self.failed or ex

    def begin_tile(self, ctx, area, view, xstep, ystep, ctm, tile_id, doc_id):
        try:
            return _raw.ll_fz_begin_tile_tid(self.target, area, view, xstep, ystep, ctm,
                                             tile_id, doc_id)
        except Exception as ex:
            self.failed = self.failed or ex
            return 0


def _passed_on(name):
    call = getattr(_raw, "ll_fz_" + name)

    def run(self, ctx, *args):
        try:
            return call(self.target, *args)
        except Exception as ex:
            self.failed = self.failed or ex
    run.__name__ = name
    return run


for _name in _CALLS:
    setattr(_Thin, _name, _passed_on(_name))


def thin(dl):
    """dl (a pymupdf.DisplayList) with every line stroked 0 wide, as a new DisplayList; dl
    itself if a call couldn't be passed on (then the lines keep their widths, nothing is lost)."""
    src = dl.this
    out = _m.FzDisplayList(_m.fz_bound_display_list(src))
    dev = _m.fz_new_list_device(out)
    device = _Thin(dev.m_internal)
    try:
        _m.fz_run_display_list(src, device, _m.FzMatrix(), _m.FzRect(_m.FzRect.Fixed_INFINITE),
                               _m.FzCookie())
        _m.fz_close_device(dev)
    except Exception:
        return dl
    if device.failed is not None:
        return dl
    return pymupdf.DisplayList(out)


def selftest_check():
    """For the self test: a page's lines drawn thin, its fills and text as they were (the
    device's calls are in this build's MuPDF)."""
    d = pymupdf.open()
    p = d.new_page(width=200, height=200)
    p.draw_line((10, 100), (190, 100), color=(0, 0, 0), width=12)
    p.draw_rect((20, 20, 60, 60), color=None, fill=(0, 0, 1))
    p.insert_text((20, 180), "Kanzonas", fontsize=24)
    dl = p.get_displaylist(annots=False)
    t = thin(dl)
    assert t is not dl, "the drawing couldn't be passed on thin"
    before, after = dl.get_pixmap(), t.get_pixmap()
    assert before.pixel(100, 95) == (0, 0, 0) and after.pixel(100, 95) == (255, 255, 255), \
        "a thick line wasn't drawn thin"
    assert after.pixel(40, 40) == before.pixel(40, 40), "a fill changed"
    assert all(after.pixel(x, y) == before.pixel(x, y) for x in range(15, 190, 2)
               for y in range(155, 190, 2)), "the text changed"
    return "(lines thin, fills and text as they were)"
