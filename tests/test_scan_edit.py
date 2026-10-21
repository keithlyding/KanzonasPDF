"""Edit text on scanned, OCR'd pages: the old letters in the scan are covered, and the new text
is written in the font, weight, size, color and baseline that match the scan; the OCR text of
other lines survives, form rules stay, ordinary PDFs are untouched.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_scan_edit
"""
import os
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np  # noqa: E402
import pymupdf  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import scan_text as S  # noqa: E402
from kanzonas import text_edit as T  # noqa: E402

GRAY, BLUE, BLACK = (0.4, 0.4, 0.4), (0.15, 0.35, 0.65), (0, 0, 0)
BOX = "\u25a1"           # a checkbox, as OCR reads one


def scan(lines, rule_under=None, boxes=(), rotate=0, ocr_size=1.0, sideways=False):
    """A scanned page: lines [(text, font, size, color, (x, y))] drawn and flattened to a 300
    dpi picture, with an invisible OCR text layer on top (stretched Helvetica, as OCR
    writes it; a line starting with BOX gets that checkbox in a Unicode font). rule_under: index of a line with a faint form rule just under it; boxes:
    rects drawn as checkboxes; sideways: text running down the page."""
    src = pymupdf.open()
    p = src.new_page()
    for i, (t, f, s, c, (x, y)) in enumerate(lines):
        p.insert_text((x, y), t.lstrip(BOX), fontsize=s, fontname=f, color=c,
                      rotate=-90 if sideways else 0)        # (a checkbox is drawn as a box)
        if rule_under == i:
            p.draw_line((x - 10, y + s * 0.25), (x + 420, y + s * 0.25),
                        color=(0.72, 0.82, 0.95), width=0.6)
    for r in boxes:
        p.draw_rect(r, color=BLUE, width=0.8)
    pix = p.get_pixmap(dpi=300)
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_image(page.rect, pixmap=pix)
    uni = pymupdf.Font("cjk")
    for t, f, s, c, (x, y) in lines:
        o = pymupdf.Point(x, y)
        fs = s * ocr_size
        if sideways:
            page.insert_text(o, t, fontsize=fs, fontname="helv", render_mode=3, rotate=-90)
            continue
        font, name = pymupdf.Font("helv"), "helv"
        w = pymupdf.get_text_length(t.lstrip(BOX), f, s)
        if t.startswith(BOX):
            # the OCR read the checkbox before the line as part of it (in a Unicode font, as
            # scanners write their text layer)
            page.insert_font(fontname="KZtestuni", fontbuffer=uni.buffer)
            font, name = uni, "KZtestuni"
            o = pymupdf.Point(x - 13, y)
            w += 13
        nat = font.text_length(t, fontsize=fs)
        page.insert_text(o, t, fontsize=fs, fontname=name, render_mode=3,
                         morph=(o, pymupdf.Matrix(w / nat, 1)))
    if rotate:
        page.set_rotation(rotate)
    return doc


def builtin_only():
    """Match against the built-in PDF fonts only (the same result on every computer, whatever
    fonts are installed)."""
    return mock.patch.object(S, "candidates",
                             lambda: [c for c in S._all_candidates() if c[5] is None])


def line_near(page, x, y):
    hit = T.line_at(T.text_lines(page), pymupdf.Point(x, y))
    return hit[1] if hit else None


def gray(page, clip, dpi=200):
    pm = page.get_pixmap(dpi=dpi, clip=clip, colorspace=pymupdf.csGRAY)
    return np.frombuffer(pm.samples, np.uint8).reshape(pm.height, pm.stride)[:, :pm.width]


SPEC = [("The contractor shall furnish all labor and materials.", "helv", 11, GRAY, (72, 100)),
        ("Submittals are due before fabrication starts.", "tiro", 12, BLACK, (72, 130)),
        ("Payment terms: net thirty days from invoice.", "cour", 10, BLUE, (72, 160)),
        ("Owner reserves the right to reject material.", "hebo", 11, BLACK, (72, 190)),
        ("All work shall conform to the applicable codes.", "tibo", 10, BLUE, (72, 220)),
        ("Small print at eight points for the notes here.", "helv", 8, BLACK, (72, 245))]
KIND = {"helv": ("sans", False), "hebo": ("sans", True), "tiro": ("serif", False),
        "tibo": ("serif", True), "cour": ("mono", False)}


class Matching(unittest.TestCase):
    def test_font_weight_size_color_and_baseline_match_the_scan(self):
        page = scan(SPEC)[0]
        self.assertTrue(S.scanned_page(page))
        for t, f, s, c, (x, y) in SPEC:
            line = line_near(page, x + 30, y - s * 0.3)
            started = time.time()
            r = S.analyze(page, line, T.line_text(line))
            self.assertLess(time.time() - started, 2.0)
            self.assertIsNotNone(r, t)
            self.assertEqual((r["kind"], r["bold"]), KIND[f], t)
            self.assertFalse(r["unsure"], t)
            self.assertAlmostEqual(r["size"], s, delta=s * 0.04, msg=t)
            self.assertAlmostEqual(r["origin"].y, y, delta=0.6, msg=t)
            self.assertAlmostEqual(r["origin"].x, x, delta=0.8, msg=t)
            for got, want in zip(r["color"], c):
                self.assertAlmostEqual(got, want, delta=0.12, msg=t)
            self.assertTrue(r["cover"])

    def test_ordinary_pages_are_not_scans(self):
        d = pymupdf.open()
        p = d.new_page()
        p.insert_text((72, 72), "Born-digital text", fontsize=12)
        self.assertFalse(S.scanned_page(p))
        self.assertIsNone(S.analyze(p, line_near(p, 80, 68), "Born-digital text"))
        # a full-page background picture under visible text isn't a scan either
        p.insert_image(p.rect, pixmap=pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 50, 50), False))
        self.assertFalse(S.scanned_page(p))

    def test_misread_text_falls_back_to_helvetica_at_the_letters_height(self):
        page = scan([("Interview Guide", "hebo", 26, BLUE, (72, 120))])[0]
        line = line_near(page, 100, 112)
        r = S.analyze(page, line, "DM&owhode")              # what the OCR made of it
        self.assertTrue(r["unsure"])
        self.assertIsNone(r["font"])
        self.assertAlmostEqual(r["size"], 26, delta=4)


class Editing(unittest.TestCase):
    def test_old_letters_are_covered_and_the_text_layer_reads_the_new_text(self):
        doc = scan(SPEC)
        page = doc[0]
        line = line_near(page, 100, 126)
        info = {}
        font = T.replace_line(page, line, "Submittals are due.", info=info)
        self.assertIn(font, ("tiro",) + tuple(c[0] for c in S.candidates() if c[2] == "serif"))
        self.assertIsNotNone(info["scan"])
        text = page.get_text()
        self.assertIn("Submittals are due.", text)
        self.assertNotIn("fabrication starts", text)
        # where the old, longer line ran past the new text there's only paper now
        g = gray(page, pymupdf.Rect(200, 118, 330, 134))
        self.assertGreater(g.min(), 230)
        # the other lines are as they were, picture and text layer
        for t, *_ in SPEC:
            if not t.startswith("Submittals"):
                self.assertIn(t, text)
        self.assertLess(np.abs(gray(page, pymupdf.Rect(60, 88, 400, 104)).astype(int)
                               - gray(scan(SPEC)[0], pymupdf.Rect(60, 88, 400, 104))).max(), 3)

    @builtin_only()
    def test_the_new_text_is_drawn_like_the_scan(self):
        """Rewriting a line with its own words gives (nearly) the same picture."""
        for t, f, s, c, (x, y) in SPEC[:4]:
            doc = scan(SPEC)
            page = doc[0]
            T.replace_line(page, line_near(page, x + 30, y - s * 0.3), t)
            clip = pymupdf.Rect(x - 4, y - s * 1.1, x + 330, y + s * 0.4)
            a, b = gray(page, clip).astype(int), gray(scan(SPEC)[0], clip).astype(int)
            differ = (np.abs(a - b) > 96).mean()
            self.assertLess(differ, 0.03, f"{t}: {differ:.3f}")

    def test_tightly_spaced_ocr_lines_keep_their_text(self):
        lines = [("The contractor shall furnish all labor and materials.", "helv", 12, BLACK, (72, 100)),
                 ("Submittals are due before fabrication starts.", "helv", 12, BLACK, (72, 113)),
                 ("All work shall conform to the applicable codes.", "helv", 12, BLACK, (72, 126))]
        page = scan(lines, ocr_size=1.25)[0]              # OCR boxes overlapping each other
        T.replace_line(page, line_near(page, 100, 110), "Submittals are due ten days before.")
        text = page.get_text()
        self.assertIn("The contractor shall furnish all labor and materials.", text)
        self.assertIn("All work shall conform to the applicable codes.", text)
        self.assertIn("Submittals are due ten days before.", text)

    def test_a_form_rule_under_the_line_stays(self):
        doc = scan(SPEC, rule_under=1)
        page = doc[0]
        y = 130 + 12 * 0.25
        before = gray(page, pymupdf.Rect(300, y - 1.5, 480, y + 1.5)).min()
        T.replace_line(page, line_near(page, 100, 126), "Submittals are due.")
        after = gray(page, pymupdf.Rect(300, y - 1.5, 480, y + 1.5)).min()
        self.assertLess(before, 235)                       # the rule is there...
        self.assertLess(after, 235)                        # ... and still is

    def test_a_scanned_checkbox_before_the_line_stays(self):
        lines = [(BOX + "Curiosity and genuine interest in the work", "helv", 10, BLUE, (85, 120))]
        doc = scan(lines, boxes=[pymupdf.Rect(72, 112.5, 79.5, 120)])
        page = doc[0]
        line = line_near(page, 120, 116)
        self.assertEqual(T.line_text(line), BOX + "Curiosity and genuine interest in the work")
        info = {}
        T.replace_line(page, line, BOX + "Curiosity and real interest in the work", info=info)
        self.assertEqual(info["scan"]["lead"], BOX)
        self.assertEqual(info["scan"]["kind"], "sans")
        self.assertAlmostEqual(info["scan"]["size"], 10, delta=0.4)
        self.assertLess(gray(page, pymupdf.Rect(71, 111.5, 80.5, 121)).min(), 160)   # box kept
        self.assertIn("Curiosity and real interest in the work", page.get_text())
        # without the checkbox in the new text, it goes too
        doc = scan(lines, boxes=[pymupdf.Rect(72, 112.5, 79.5, 120)])
        page = doc[0]
        T.replace_line(page, line_near(page, 120, 116), "Curiosity and real interest")
        self.assertGreater(gray(page, pymupdf.Rect(71, 111.5, 80.5, 121)).min(), 225)

    def test_sideways_text_and_rotated_pages(self):
        page = scan([("Revision notes for the drawing set", "helv", 11, BLACK, (300, 100))],
                    sideways=True)[0]
        line = line_near(page, 296, 200)
        r = S.analyze(page, line, T.line_text(line))
        self.assertEqual((r["kind"], r["bold"]), ("sans", False))
        self.assertAlmostEqual(r["size"], 11, delta=0.5)
        page = scan(SPEC[:2], rotate=90)[0]
        line = line_near(page, 100, 96)
        r = S.analyze(page, line, T.line_text(line))
        self.assertEqual((r["kind"], r["bold"]), ("sans", False))
        self.assertAlmostEqual(r["size"], 11, delta=0.5)

    def test_editing_on_a_rotated_scan_covers_the_old_words(self):
        doc = scan(SPEC, rotate=90)
        page = doc[0]
        T.replace_line(page, line_near(page, 100, 126), "Submittals are due.")
        self.assertIn("Submittals are due.", page.get_text())
        self.assertNotIn("fabrication starts", page.get_text())
        page.set_rotation(0)                 # look at it as drawn: the old words are gone
        self.assertGreater(gray(page, pymupdf.Rect(200, 118, 330, 134)).min(), 230)

    @builtin_only()
    def test_second_edit_keeps_the_font_and_adds_no_second_cover(self):
        doc = scan(SPEC)
        page = doc[0]
        T.replace_line(page, line_near(page, 100, 96), "The contractor shall furnish labor.")
        drawings = len(page.get_drawings())
        info = {}
        font = T.replace_line(page, line_near(page, 100, 96), "The contractor furnishes labor.",
                              info=info)
        self.assertIsNone(info["scan"])                    # an ordinary line now
        self.assertEqual(font, "helv")
        self.assertEqual(len(page.get_drawings()), drawings)
        self.assertIn("The contractor furnishes labor.", page.get_text())

    def test_a_line_edited_before_this_version_gets_covered(self):
        doc = scan(SPEC)
        page = doc[0]
        line = line_near(page, 100, 96)
        T.replace_line(page, line, "The contractor shall furnish all labor and materials.", scan=None)
        info = {}
        T.replace_line(page, line_near(page, 100, 96),
                       "The contractor shall furnish all labor and materials.", info=info)
        self.assertIsNotNone(info["scan"])
        self.assertTrue(info["scan"]["cover"])

    def test_text_added_over_paper_is_left_alone(self):
        doc = scan(SPEC)
        page = doc[0]
        page.insert_text((72, 400), "A note added later", fontsize=12, fontname="tiro")
        info = {}
        T.replace_line(page, line_near(page, 100, 396), "A note changed later", info=info)
        self.assertIsNone(info["scan"])

    def test_ordinary_pdf_lines_are_edited_as_before(self):
        d = pymupdf.open()
        p = d.new_page()
        p.insert_text((72, 100), "Invoice due", fontsize=12, fontname="tiro")
        p.insert_text((72, 112), "Pay by June", fontsize=12, fontname="tiro")
        info = {}
        T.replace_line(p, line_near(p, 80, 96), "Invoice paid", info=info)
        self.assertIsNone(info["scan"])
        self.assertEqual(p.get_drawings(), [])
        self.assertEqual([ln for ln in p.get_text().splitlines() if ln.strip()],
                         ["Pay by June", "Invoice paid"])


class Command(unittest.TestCase):
    def test_edit_find_replace_and_undo_in_the_app(self):
        from kanzonas.main_window import MainWindow
        path = os.path.join(tempfile.mkdtemp(), "scan.pdf")
        scan(SPEC).save(path)
        w = MainWindow()
        w.show()
        w.open_file(path)
        APP.processEvents()
        self.addCleanup(lambda: (setattr(w, "_close_confirmed", True), w.close()))
        v = w.view()
        said = []
        v.statusMessage.connect(said.append)
        line = line_near(v.doc[0], 100, 186)
        v._apply_text_edit(0, line, "Owner may reject material.", (0, 0), None)
        self.assertTrue(any(m.startswith("Matched the scan: ") and " Bold, 11 pt" in m
                            for m in said), said)
        self.assertIn("Owner may reject material.", v.doc[0].get_text())
        self.assertTrue(v.doc[0].get_drawings())
        v.undo()
        self.assertEqual(v.doc[0].get_drawings(), [])
        self.assertIn("Owner reserves the right to reject material.", v.doc[0].get_text())
        found, lines, skipped = v.replace_text("thirty", "sixty")
        self.assertEqual((found, lines, skipped), (1, 1, []))
        self.assertIn("Payment terms: net sixty days from invoice.", v.doc[0].get_text())
        self.assertTrue(v.doc[0].get_drawings())


if __name__ == "__main__":
    unittest.main()
