"""Edit objects > Ungroup: a group (Form XObject) becomes ordinary page content, looks the
same, and its shapes and text can then be picked one by one.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_ungroup
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf as F  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import page_objects as P  # noqa: E402
from kanzonas.document_view import DocumentView  # noqa: E402


def grouped_doc(path):
    src = F.open()
    s = src.new_page(width=300, height=200)
    s.insert_text((20, 40), "Grouped words", fontsize=16, fontname="tiro")
    s.draw_rect(F.Rect(20, 60, 120, 140), color=(1, 0, 0), fill=(0, 0, 1), width=2)
    s.draw_line((150, 60), (280, 180), color=(0, 0.5, 0), width=3)
    d = F.open()
    pg = d.new_page()
    pg.insert_text((50, 50), "Page words", fontsize=12)         # the page's own font F0...
    pg.show_pdf_page(F.Rect(100, 200, 400, 400), src, 0, rotate=0)
    pg.show_pdf_page(F.Rect(100, 450, 250, 550), src, 0, rotate=90)
    d.save(path)


class Ungroup(unittest.TestCase):
    def test_ungroup_keeps_the_look_and_frees_the_parts(self):
        path = os.path.join(tempfile.mkdtemp(), "g.pdf")
        grouped_doc(path)
        d = F.open(path)
        pg = d[0]
        before = pg.get_pixmap(dpi=72).samples
        objs = P.Objects(pg)
        groups = [it["n"] for it in objs.items if it["kind"] == "group"]
        self.assertEqual(len(groups), 2)
        self.assertEqual(P.ungroup(pg, groups), 2)
        pg = d[0]
        after = pg.get_pixmap(dpi=72).samples
        diff = sum(1 for a, b in zip(before, after) if abs(a - b) > 40)
        self.assertLess(diff, len(before) * 0.002)                 # looks the same
        kinds = [it["kind"] for it in P.Objects(pg).items]
        self.assertNotIn("group", kinds)
        self.assertGreaterEqual(kinds.count("shape"), 4)           # rect + line, twice
        self.assertEqual(pg.get_text().count("Grouped words"), 2)
        self.assertIn("Page words", pg.get_text())
        # survives a save and reopen
        out = path + ".2.pdf"
        d.save(out)
        self.assertEqual(F.open(out)[0].get_pixmap(dpi=72).samples, after)

    def test_menu_command_on_the_view(self):
        path = os.path.join(tempfile.mkdtemp(), "g.pdf")
        grouped_doc(path)
        v = DocumentView(path)
        self.addCleanup(v.close_doc)
        objs = v.content_objects(0)
        g = [it for it in objs.items if it["kind"] == "group"][:1]
        v.select_objects(0, g)
        v.ungroup_objects()
        kinds = [it["kind"] for it in v.content_objects(0).items]
        self.assertEqual(kinds.count("group"), 1)
        v.undo()
        kinds = [it["kind"] for it in v.content_objects(0).items]
        self.assertEqual(kinds.count("group"), 2)


if __name__ == "__main__":
    unittest.main()
