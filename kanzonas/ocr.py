"""OCR: recognize text on page images and add it as an invisible, searchable text layer.

Uses RapidOCR (Apache-2.0) on ONNX Runtime (MIT). Models ship inside the pip package,
so it works offline with nothing else to install.

Rendering and PDF edits must happen on the GUI thread (PyMuPDF is not thread-safe);
only recognize() is meant to run in a worker thread.
"""

import math
import threading

import pymupdf

OCR_DPI = 300
MAX_SIDE_PX = 13000     # 42x30in sheets still get ~300 dpi; the image is grayscale (1 byte/px)
TILE_PX = 1600          # OCR runs on overlapping tiles so small text keeps full resolution
OVERLAP_PX = 200        #   (and memory stays small) on big drawings
MIN_CONFIDENCE = 0.5

_engine = None
_lock = threading.Lock()


def _get_engine():
    global _engine
    with _lock:
        if _engine is None:
            from rapidocr_onnxruntime import RapidOCR
            _engine = RapidOCR()
        return _engine


class Rendering:
    """A page image plus the mapping from image pixels back to displayed page coordinates."""

    def __init__(self, page, extra_rotation=0):
        r = page.rect                                   # displayed (rotated) page size
        scale = min(OCR_DPI / 72, MAX_SIDE_PX / max(r.width, r.height))
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
        result, _ = _get_engine()(rendering)
        return result or []
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
            result, _ = _get_engine()(np.ascontiguousarray(np.stack([tile] * 3, axis=-1)))
            # keep each line once: the tile that holds its centre outside the shared overlap
            lo_x = x0 + (OVERLAP_PX / 2 if tx > 0 else 0)
            hi_x = x0 + TILE_PX - (OVERLAP_PX / 2 if tx < len(xs) - 1 else 0)
            lo_y = y0 + (OVERLAP_PX / 2 if ty > 0 else 0)
            hi_y = y0 + TILE_PX - (OVERLAP_PX / 2 if ty < len(ys) - 1 else 0)
            for box, text, conf in result or []:
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
        w = math.dist(box[0], box[1])
        h = math.dist(box[1], box[2])
        if h > 1.5 * w:
            tall += 1
        else:
            wide += 1
    return tall > wide


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
        # Baseline runs bottom-left -> bottom-right in the OCR image; map both ends to the display.
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
