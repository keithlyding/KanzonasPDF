"""OCR: recognize text on page images and add it as an invisible, searchable text layer.

Uses RapidOCR (Apache-2.0) on ONNX Runtime (MIT). Models ship inside the pip package,
so it works offline with nothing else to install.

Rendering and PDF edits must happen on the GUI thread (PyMuPDF is not thread-safe):
recognize() renders each tile in the thread that calls it and hands it to a worker thread to
read (the engine, ONNX Runtime, no PyMuPDF).
"""

import math
import sys
import threading
import time

import pymupdf

from .i18n import tr

OCR_DPI = 300
MAX_SIDE_PX = 13000     # 42x30in sheets still get ~300 dpi; the image is grayscale (1 byte/px)
TILE_PX = 1600          # OCR runs on overlapping tiles so small text keeps full resolution
OVERLAP_PX = 200        #   (and memory stays small) on big drawings
MIN_CONFIDENCE = 0.5
# Accuracy levels: the engine has no quality dial, so accuracy = how sharp the page image is.
ACCURACY_DPI = {"fast": 150, "normal": 300, "high": 400}
ACCURACY_LABELS = {"auto": tr("Auto (fast, redo sharper if needed)"),
                   "fast": tr("Fast (150 dpi: clean scans, normal-size text)"),
                   "normal": tr("Normal (300 dpi)"),
                   "high": tr("High (400 dpi, checks every orientation: small print, poor "
                              "scans)")}

ENGINE_IDLE_S = 120     # the engine (~45 MB) is let go this long after the last OCR job

_engine = None
_lock = threading.Lock()
_last_used = 0.0


def _get_engine():
    global _engine, _last_used
    with _lock:
        _last_used = time.monotonic()
        if _engine is None:
            import onnxruntime
            onnxruntime.disable_telemetry_events()
            _lean_sessions()
            from rapidocr_onnxruntime import RapidOCR
            _engine = RapidOCR()
            _watch_turns(_engine)
        return _engine


def _lean_sessions():
    """ONNX Runtime's sessions without the memory they keep between runs: RapidOCR already
    turns its memory arena off; the memory pattern (buffers planned and kept for each size
    of picture seen, and the pages' tiles and lines come in many sizes) goes off too."""
    try:
        from rapidocr_onnxruntime import utils
        base = utils.SessionOptions
    except Exception:
        return
    if getattr(base, "kz_lean", False):
        return

    def lean():
        options = base()
        options.enable_cpu_mem_arena = False
        options.enable_mem_pattern = False
        return options
    lean.kz_lean = True
    utils.SessionOptions = lean


def release_engine(idle=0.0):
    """Let the engine go (it's loaded again, in about a second, by the next job) once it has
    been unused for idle seconds; give the memory freed back to the system. True if let go."""
    global _engine
    with _lock:
        if _engine is None or time.monotonic() - _last_used < idle:
            return False
        _engine = None
    import gc
    gc.collect()
    trim_memory()
    return True


def trim_memory():
    """Give the memory OCR freed back to the system. On Linux the C library keeps what a
    thread freed for later (hundreds of MB after a big sheet's tiles); Windows and macOS give
    big blocks back by themselves."""
    if sys.platform.startswith("linux"):
        try:
            import ctypes
            ctypes.CDLL("libc.so.6").malloc_trim(0)
        except (OSError, AttributeError):
            pass


def _watch_turns(engine):
    """Note which lines the engine turned to read them. RapidOCR reads a line that is upside
    down (its angle classifier turns the line's picture) or standing up (a tall line is
    turned a quarter), but returns its corners as they lie in the picture, so the text layer
    would run the wrong way over it: see _reading_order."""
    crop, classify = getattr(engine, "get_crop_img_list", None), getattr(engine, "text_cls", None)
    if crop is None or classify is None:
        return

    def crop_list(img, dt_boxes):
        engine.kz_boxes = list(dt_boxes)
        return crop(img, dt_boxes)

    def classify_turns(img_list):
        out = classify(img_list)
        least = getattr(classify, "cls_thresh", 0.9)
        engine.kz_flips = ["180" in str(label) and float(conf) > least for label, conf in out[1]]
        return out
    engine.get_crop_img_list = crop_list
    engine.text_cls = classify_turns


def _key(box):
    return tuple(round(float(v), 1) for p in box for v in p)


def _reading_order(box, flipped):
    """The line's corners in reading order (top-left, top-right, bottom-right, bottom-left
    of the text) from the picture's order, the way the engine read it: turned a quarter
    when it is tall (as RapidOCR does), and half a turn more when its classifier found it
    upside down."""
    box = [list(p) for p in box]
    w = int(max(math.dist(box[0], box[1]), math.dist(box[2], box[3])))
    h = int(max(math.dist(box[0], box[3]), math.dist(box[1], box[2])))
    k = (1 if w and h / w >= 1.5 else 0) + (2 if flipped else 0)
    return box[k:] + box[:k]


def _read(image):
    """Run the engine on one image: [(box in reading order, text, confidence), ...]."""
    engine = _get_engine()
    engine.kz_boxes = engine.kz_flips = None
    result, _ = engine(image)
    boxes, flips = getattr(engine, "kz_boxes", None), getattr(engine, "kz_flips", None)
    turned = {}
    if boxes and flips and len(boxes) == len(flips):
        turned = {_key(b): f for b, f in zip(boxes, flips)}
    return [(_reading_order(box, turned.get(_key(box), False)), text, conf)
            for box, text, conf in result or []]


class Rendering:
    """A page to read, tile by tile, plus the mapping from image pixels back to displayed page
    coordinates. Only the page's display list is kept (made once): each tile is rendered from
    it when it's read (tile()), so a big sheet never sits in memory as one picture (an ARCH E
    sheet at 300 dpi is over 100 MB in gray). Rendering is PyMuPDF work: make it and call
    tile() on the GUI thread (see recognize)."""

    def __init__(self, page, extra_rotation=0, dpi=OCR_DPI, displaylist=None):
        r = page.rect                                   # displayed (rotated) page size
        scale = min(dpi / 72, MAX_SIDE_PX / max(r.width, r.height))
        self.dpi = dpi
        m = pymupdf.Matrix(scale, scale) * pymupdf.Matrix(extra_rotation)
        # the display list holds the page with its own rotation applied (as get_pixmap does),
        # then our matrix
        box = (r * m).irect                              # the whole image, transformed space
        self.width, self.height = box.width, box.height
        self._m = m
        self._dl = displaylist if displaylist is not None else \
            page.get_displaylist(annots=False)
        self._to_display = ~m
        self._shift = pymupdf.Point(box.tl)              # image origin in transformed space
        self.scale = scale

    def to_display(self, x, y):
        return (pymupdf.Point(x, y) + self._shift) * self._to_display

    def tile(self, x0, y0, w=TILE_PX, h=TILE_PX):
        """The image's pixels x0..x0+w, y0..y0+h (cut at its edges), gray, as a numpy array:
        those of the whole page's image (a scan's exactly; a drawn line's edge pixels can be a
        few gray levels off, as MuPDF antialiases a line cut at the tile's edge)."""
        import numpy as np
        w, h = min(w, self.width - x0), min(h, self.height - y0)
        sx, sy = int(self._shift.x), int(self._shift.y)
        want = pymupdf.IRect(sx + x0, sy + y0, sx + x0 + w, sy + y0 + h)
        pm = self._dl.get_pixmap(matrix=self._m, colorspace=pymupdf.csGRAY, alpha=False,
                                 clip=pymupdf.Rect(want) * self._to_display)
        got = np.frombuffer(pm.samples_mv, np.uint8).reshape(pm.height, pm.stride)[:, :pm.width]
        if (pm.x, pm.y, pm.width, pm.height) == (want.x0, want.y0, w, h):
            return got.copy()
        # (the clip, rounded to pixels, may reach a pixel further: the wanted ones out of it)
        out = np.full((h, w), 255, np.uint8)
        dx, dy = pm.x - want.x0, pm.y - want.y0
        ax, ay = max(0, dx), max(0, dy)
        bx, by = min(w, dx + pm.width), min(h, dy + pm.height)
        if bx > ax and by > ay:
            out[ay:by, ax:bx] = got[ay - dy:by - dy, ax - dx:bx - dx]
        return out

    @property
    def image(self):
        """The whole page's image (small pages, tests); None once released."""
        if self._dl is None:
            return None
        return self.tile(0, 0, self.width, self.height)

    def release(self):
        """Drop the page's display list once it's been read: only the coordinate mapping is
        needed to place the text, so a long batch doesn't keep every page in memory."""
        self._dl = None

    @property
    def png(self):
        """Whole image as PNG (small pages / tests)."""
        img = self.image
        pm = pymupdf.Pixmap(pymupdf.csGRAY, img.shape[1], img.shape[0], img.tobytes(), False)
        return pm.tobytes("png")


def _starts(length):
    step = TILE_PX - OVERLAP_PX
    starts = list(range(0, max(1, length - OVERLAP_PX), step)) or [0]
    return starts


def _read_tile(tile, tx, ty, x0, y0, xs, ys):
    """Read one tile (any thread: no PyMuPDF here); its lines in whole-image pixels, each
    line once: the tile that holds its centre outside the shared overlap keeps it."""
    import numpy as np
    result = _read(np.ascontiguousarray(np.stack([tile] * 3, axis=-1)))
    lo_x = x0 + (OVERLAP_PX / 2 if tx > 0 else 0)
    hi_x = x0 + TILE_PX - (OVERLAP_PX / 2 if tx < len(xs) - 1 else 0)
    lo_y = y0 + (OVERLAP_PX / 2 if ty > 0 else 0)
    hi_y = y0 + TILE_PX - (OVERLAP_PX / 2 if ty < len(ys) - 1 else 0)
    out = []
    for box, text, conf in result:
        box = [[p[0] + x0, p[1] + y0] for p in box]
        cx = sum(p[0] for p in box) / 4
        cy = sum(p[1] for p in box) / 4
        if lo_x <= cx < hi_x and lo_y <= cy < hi_y:
            out.append((box, text, conf))
    return out


def recognize(rendering, cancelled=lambda: False, executor=None, wait=None):
    """OCR the page tile by tile and merge the results: [(box, text, confidence), ...] in
    whole-image pixel coordinates. Each tile is rendered here, in the calling thread (the GUI
    thread: PyMuPDF), and read in executor (a worker thread; none: here) while the next one
    is rendered; wait(future) waits for a tile's reading (default: future.result()), e.g.
    keeping the window responsive. Only a tile or two are in memory at a time."""
    if not isinstance(rendering, Rendering):          # PNG bytes (older callers)
        return _read(rendering)
    xs, ys = _starts(rendering.width), _starts(rendering.height)
    out = []
    pending = None
    for ty, y0 in enumerate(ys):
        for tx, x0 in enumerate(xs):
            if cancelled():
                return out
            tile = rendering.tile(x0, y0)
            if tile.min() > 200:                      # blank paper: nothing to read
                continue
            args = (tile, tx, ty, x0, y0, xs, ys)
            if executor is None:
                out += _read_tile(*args)
                continue
            fut = executor.submit(_read_tile, *args)
            if pending is not None:                   # (read while this one was rendered)
                got = (wait or (lambda f: f.result()))(pending)
                if got is None:
                    return out
                out += got
            pending = fut
    if pending is not None:
        got = (wait or (lambda f: f.result()))(pending)
        out += got or []
    return out


def _good(results):
    return [r for r in results if r[1].strip() and float(r[2]) >= MIN_CONFIDENCE]


def mostly_vertical(results):
    """True if most recognized lines are taller than wide, i.e. the text is sideways."""
    tall = wide = 0
    for box, text, _ in _good(results):
        if len(text.strip()) < 3:
            continue
        w = max(p[0] for p in box) - min(p[0] for p in box)
        h = max(p[1] for p in box) - min(p[1] for p in box)
        if h > 1.5 * w:
            tall += 1
        else:
            wide += 1
    return tall > wide


def upside_down(results):
    """True if most recognized lines run right to left in the image: the page was scanned
    upside down."""
    turned = upright = 0
    for box, text, _ in _good(results):
        if len(text.strip()) < 3:
            continue
        dx, dy = box[1][0] - box[0][0], box[1][1] - box[0][1]
        if abs(dx) > abs(dy):
            if dx < 0:
                turned += 1
            else:
                upright += 1
    return turned > upright


def native_dpi(page):
    """Resolution of the scan on a page (its largest image), or None for pages without one.
    Rendering above it adds no detail, only blur, and makes OCR worse."""
    best = None
    try:
        for info in page.get_image_info():
            bbox = pymupdf.Rect(info["bbox"])
            if bbox.is_empty or not info.get("width"):
                continue
            area = bbox.width * bbox.height
            if best is None or area > best[0]:
                dpi = min(info["width"] * 72 / bbox.width, info["height"] * 72 / bbox.height)
                best = (area, dpi)
    except Exception:
        return None
    if best is None or best[0] < 0.5 * page.rect.width * page.rect.height:
        return None                       # no scan covering most of the page
    return best[1]


def page_dpi(page, wanted):
    """The resolution to render at: the wanted one, but never above the scan's own."""
    native = native_dpi(page)
    return min(wanted, max(150, round(native))) if native else wanted


def needs_sharper(results, rendering):
    """Auto accuracy: after a fast pass, is a sharper pass worth it? Yes when the text came
    out small (about 7 pt or less) or the engine was unsure."""
    good = _good(results)
    if not results:
        return True
    if len(good) < 0.7 * len(results):
        return True
    heights = sorted(min(math.dist(b[0], b[3]), math.dist(b[0], b[1])) for b, _, _ in good)
    # 15 px at 150 dpi is ~7 pt text: below that, a sharper image reads it better
    if heights and heights[len(heights) // 2] < 15 * rendering.dpi / 150:
        return True
    conf = [float(c) for _, _, c in good]
    return bool(conf) and sum(conf) / len(conf) < 0.85


def score(results):
    return sum(float(c) * len(t.strip()) for _, t, c in _good(results))


def add_text_layer(page, results, rendering):
    """Insert recognized lines as invisible text (render mode 3) exactly where they appear."""
    prot = page.rotation
    derot = page.derotation_matrix
    added = 0
    for box, text, conf in _good(results):
        text = text.strip()
        (tlx, tly), (trx, try_), (brx, bry), (blx, bly) = box[:4]
        # Baseline runs bottom-left -> bottom-right of the text (the box is in reading order,
        # see _reading_order); map both ends to the display.
        bl = rendering.to_display(blx, bly)
        br = rendering.to_display(brx, bry)
        tl = rendering.to_display(tlx, tly)
        length = abs(br - bl)
        height = abs(tl - bl)
        if length <= 1 or height <= 1:
            continue
        # Direction of the text on screen, snapped to 0/90/180/270 (clockwise, y down).
        angle = math.degrees(math.atan2(br.y - bl.y, br.x - bl.x))
        disp = int(round(angle / 90.0)) % 4 * 90
        fontsize = height * 0.8
        natural = pymupdf.get_text_length(text, fontname="helv", fontsize=fontsize)
        if natural <= 0:
            continue
        stretch = length / natural
        # Raise the baseline slightly off the box bottom (descenders), toward the box top.
        up = (tl - bl) * (0.2 / 1.0) if height else pymupdf.Point(0, 0)
        origin = (bl + up) * derot
        rot = (prot - disp) % 360          # insert_text rotation in unrotated page space
        morph_m = pymupdf.Matrix(stretch, 1) if rot in (0, 180) else pymupdf.Matrix(1, stretch)
        page.insert_text(origin, text, fontsize=fontsize, fontname="helv", render_mode=3,
                         rotate=rot, morph=(origin, morph_m))
        added += 1
    return added
