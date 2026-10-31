"""OCR: recognize text on page images and add it as an invisible, searchable text layer.

Uses RapidOCR (Apache-2.0) on ONNX Runtime (MIT). Models ship inside the pip package,
so it works offline with nothing else to install.

Rendering and PDF edits must happen on the GUI thread (PyMuPDF is not thread-safe);
only recognize() is meant to run in a worker thread.
"""

import math
import threading

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

_engine = None
_lock = threading.Lock()


def _get_engine():
    global _engine
    with _lock:
        if _engine is None:
            import onnxruntime
            onnxruntime.disable_telemetry_events()
            from rapidocr_onnxruntime import RapidOCR
            _engine = RapidOCR()
            _watch_turns(_engine)
        return _engine


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
    """A page image plus the mapping from image pixels back to displayed page coordinates."""

    def __init__(self, page, extra_rotation=0, dpi=OCR_DPI):
        r = page.rect                                   # displayed (rotated) page size
        scale = min(dpi / 72, MAX_SIDE_PX / max(r.width, r.height))
        self.dpi = dpi
        m = pymupdf.Matrix(scale, scale) * pymupdf.Matrix(extra_rotation)
        # get_pixmap applies the page's own rotation, then our matrix
        pm = page.get_pixmap(matrix=m, annots=False, alpha=False, colorspace=pymupdf.csGRAY)
        import numpy as np
        self.image = np.frombuffer(pm.samples, np.uint8).reshape(pm.height, pm.stride)[:, :pm.width].copy()
        shift = (r * m).irect.tl                         # pixmap origin in transformed space
        self._to_display = ~m
        self._shift = pymupdf.Point(shift)
        self.scale = scale

    def to_display(self, x, y):
        return (pymupdf.Point(x, y) + self._shift) * self._to_display

    def release(self):
        """Drop the page image once it's been read: only the coordinate mapping is needed
        to place the text, so a long batch doesn't keep every full-size scan in memory."""
        self.image = None

    @property
    def png(self):
        """Whole image as PNG (small pages / tests)."""
        pm = pymupdf.Pixmap(pymupdf.csGRAY, self.image.shape[1], self.image.shape[0],
                            self.image.tobytes(), False)
        return pm.tobytes("png")


def _starts(length):
    step = TILE_PX - OVERLAP_PX
    starts = list(range(0, max(1, length - OVERLAP_PX), step)) or [0]
    return starts


def recognize(rendering, cancelled=lambda: False):
    """Runs in a worker thread. OCR the image tile by tile and merge the results.
    Returns [(box, text, confidence), ...] in whole-image pixel coordinates."""
    import numpy as np
    img = rendering.image if hasattr(rendering, "image") else None
    if img is None:                                   # PNG bytes (older callers)
        return _read(rendering)
    h, w = img.shape
    xs, ys = _starts(w), _starts(h)
    out = []
    for ty, y0 in enumerate(ys):
        for tx, x0 in enumerate(xs):
            if cancelled():
                return out
            tile = img[y0:y0 + TILE_PX, x0:x0 + TILE_PX]
            if tile.min() > 200:                      # blank paper: nothing to read
                continue
            result = _read(np.ascontiguousarray(np.stack([tile] * 3, axis=-1)))
            # keep each line once: the tile that holds its centre outside the shared overlap
            lo_x = x0 + (OVERLAP_PX / 2 if tx > 0 else 0)
            hi_x = x0 + TILE_PX - (OVERLAP_PX / 2 if tx < len(xs) - 1 else 0)
            lo_y = y0 + (OVERLAP_PX / 2 if ty > 0 else 0)
            hi_y = y0 + TILE_PX - (OVERLAP_PX / 2 if ty < len(ys) - 1 else 0)
            for box, text, conf in result:
                box = [[p[0] + x0, p[1] + y0] for p in box]
                cx = sum(p[0] for p in box) / 4
                cy = sum(p[1] for p in box) / 4
                if lo_x <= cx < hi_x and lo_y <= cy < hi_y:
                    out.append((box, text, conf))
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
