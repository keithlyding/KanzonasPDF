"""Scale notes read off the sheet: the parser, finding them on a page (title block first,
rotated pages), the Set scale dialog offering them, and Read scales from title blocks."""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tests"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import measure as M  # noqa: E402
from kanzonas import sheet_scale as S  # noqa: E402
from kanzonas.main_window import MainWindow  # noqa: E402
from kanzonas.measure_ui import ScaleDialog  # noqa: E402


def sheet(doc, scale_text, title_block=True, rotation=0, extra=()):
    """A 36x24 inch sheet with a SCALE caption and value in the title block (or elsewhere)."""
    if rotation in (90, 270):
        p = doc.new_page(width=1728, height=2592)       # portrait sheet shown landscape
    else:
        p = doc.new_page(width=2592, height=1728)
    if rotation:
        p.set_rotation(rotation)
    # positions are chosen as displayed (title block lower right as the viewer shows it)
    # and converted to the unrotated coordinates insert_text works in
    x, y = (2200, 1600) if title_block else (300, 300)

    def at(dx, dy):
        return pymupdf.Point(dx, dy) * p.derotation_matrix
    p.insert_text(at(x, y), "SCALE", fontsize=6, rotate=rotation)
    p.insert_text(at(x, y + 13), scale_text, fontsize=10, rotate=rotation)
    for (ex, ey, text) in extra:
        p.insert_text(at(ex, ey), text, fontsize=9, rotate=rotation)
    return p


class Parser(unittest.TestCase):
    def test_architectural_engineering_metric_and_nts(self):
        self.assertEqual(S.parse('SCALE: 1/4" = 1\'-0"'), ('1/4" = 1\'-0"', 48.0, "ft-in"))
        self.assertEqual(S.parse('3/32"=1\'-0"'), ('3/32" = 1\'-0"', 128.0, "ft-in"))
        self.assertEqual(S.parse('1 1/2" = 1\'-0"'), ('1-1/2" = 1\'-0"', 8.0, "ft-in"))
        self.assertEqual(S.parse('1" = 20\''), ('1" = 20\'', 240.0, "ft"))
        self.assertEqual(S.parse("SCALE 1:50"), ("1:50", 50.0, "mm"))
        self.assertEqual(S.parse("1:100"), ("1:100", 100.0, "m"))
        self.assertEqual(S.parse("N.T.S."), ("not to scale", None, ""))
        self.assertEqual(S.parse("NOT TO SCALE"), ("not to scale", None, ""))

    def test_curly_quotes_and_odd_spacing(self):
        self.assertEqual(S.parse("SCALE: 1/8” = 1’-0”")[1], 96.0)
        self.assertEqual(S.parse('1/2"  =  1\'')[1], 24.0)

    def test_things_that_are_not_scales(self):
        for text in ("10:30 AM", "25'-0\"", "AS NOTED", "ROOM 1:1 PLAN", "A-101 REV 3",
                     "DETAIL 3/A-501", "1/2\" PLYWOOD"):
            self.assertIsNone(S.parse(text), text)


class Finding(unittest.TestCase):
    def test_title_block_note_wins_over_a_detail_note(self):
        doc = pymupdf.open()
        p = sheet(doc, '1/8" = 1\'-0"', extra=[(400, 900, 'SCALE: 1/2" = 1\'-0"')])
        found = S.find(p)
        self.assertEqual([f["label"] for f in found], ['1/8" = 1\'-0"', '1/2" = 1\'-0"'])
        self.assertEqual(found[0]["where"], "title block")
        self.assertEqual(found[1]["where"], "drawing")
        self.assertTrue(found[0]["labeled"])
        self.assertEqual(S.sheet_scale(p)["ratio"], 96.0)

    def test_rotated_sheet_still_finds_the_title_block(self):
        doc = pymupdf.open()
        p = sheet(doc, '1/4" = 1\'-0"', rotation=90)
        best = S.sheet_scale(p)
        self.assertIsNotNone(best)
        self.assertEqual(best["ratio"], 48.0)
        self.assertEqual(best["where"], "title block")

    def test_no_note_and_nts(self):
        doc = pymupdf.open()
        p = doc.new_page()
        p.insert_text((72, 72), "just text")
        self.assertIsNone(S.sheet_scale(p))
        q = sheet(doc, "NTS")
        self.assertIsNone(S.sheet_scale(q)["ratio"])

    def test_real_sample_floor_plan(self):
        import cad_samples
        path = os.path.join(tempfile.mkdtemp(), "fp.pdf")
        cad_samples.floorplan(path)
        best = S.sheet_scale(pymupdf.open(path)[0])
        self.assertEqual((best["label"], best["ratio"], best["where"]),
                         ('1/4" = 1\'-0"', 48.0, "title block"))


class Dialog(unittest.TestCase):
    def test_set_scale_offers_and_preselects_the_sheet_scale(self):
        doc = pymupdf.open()
        p = sheet(doc, '1" = 20\'')
        dlg = ScaleDialog(None, p)
        self.assertTrue(dlg.r_sheet.isChecked())
        self.assertEqual(dlg.sheet.count(), 1)
        self.assertEqual(dlg.disp_unit.currentData(), "ft")
        dlg._accept()
        f, unit, label, all_pages = dlg.result_scale
        self.assertAlmostEqual(f, M.scale_from_preset(240))
        self.assertEqual((unit, label, all_pages), ("ft", '1" = 20\'', False))

    def test_calibrate_keeps_known_distance_as_default(self):
        doc = pymupdf.open()
        p = sheet(doc, '1/4" = 1\'-0"')
        dlg = ScaleDialog(None, p, pdf_len=100.0)
        self.assertTrue(dlg.r_known.isChecked())
        self.assertFalse(dlg.r_sheet.isChecked())
        self.assertEqual(dlg.sheet.count(), 1)

    def test_without_a_note_the_option_is_hidden(self):
        doc = pymupdf.open()
        p = doc.new_page()
        dlg = ScaleDialog(None, p)
        self.assertTrue(dlg.r_sheet.isHidden())
        self.assertTrue(dlg.r_preset.isChecked())


class Command(unittest.TestCase):
    def test_read_scales_sets_each_page_from_its_own_sheet(self):
        doc = pymupdf.open()
        sheet(doc, '1/8" = 1\'-0"')
        sheet(doc, "1:50")
        sheet(doc, "N.T.S.")
        doc.new_page().insert_text((72, 72), "no note here")
        path = os.path.join(tempfile.mkdtemp(), "set.pdf")
        doc.save(path)
        w = MainWindow()
        w.show()
        w.open_file(path)
        APP.processEvents()
        self.addCleanup(lambda: (setattr(w, "_close_confirmed", True), w.close()))
        v = w.view()
        self.assertIn("the sheet says 1/8\" = 1'-0\"", v.page_scale_text(0))
        shown = []
        with mock.patch.object(QMessageBox, "information", lambda *a, **k: shown.append(a[2])):
            w.read_sheet_scales()
        self.assertEqual(len(shown), 1)
        self.assertIn("Scale set on 2 of 4", shown[0])
        self.assertIn("not to scale, left as is: page 3", shown[0])
        self.assertIn("No scale note found, left as is: page 4", shown[0])
        f0, u0, l0, ok0 = M.get_scale(v.doc[0])
        f1, u1, l1, ok1 = M.get_scale(v.doc[1])
        self.assertTrue(ok0 and ok1)
        self.assertAlmostEqual(f0, M.scale_from_preset(96))
        self.assertEqual((u0, l0), ("ft-in", '1/8" = 1\'-0"'))
        self.assertAlmostEqual(f1, M.scale_from_preset(50))
        self.assertEqual((u1, l1), ("mm", "1:50"))
        self.assertFalse(M.get_scale(v.doc[2])[3])
        self.assertFalse(M.get_scale(v.doc[3])[3])
        self.assertTrue(v.dirty)
        v.undo()                                 # one step undoes the whole set
        self.assertFalse(M.get_scale(v.doc[0])[3])
        self.assertFalse(M.get_scale(v.doc[1])[3])


if __name__ == "__main__":
    unittest.main()
