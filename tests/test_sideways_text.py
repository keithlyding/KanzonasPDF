"""Edit text on sideways text (rotated lines, or a rotated page): it opens in an upright
box on the page at the line, not in a separate dialog, and the text keeps its direction.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_sideways_text
"""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf as F  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import dialogs  # noqa: E402
from kanzonas.document_view import DocumentView  # noqa: E402


class SidewaysText(unittest.TestCase):
    def view(self, page_rotation=0, text_rotate=90):
        d = F.open()
        pg = d.new_page()
        pg.insert_text((200, 400), "Sideways words", fontsize=14, rotate=text_rotate)
        pg.set_rotation(page_rotation)
        p = os.path.join(tempfile.mkdtemp(), "s.pdf")
        d.save(p)
        v = DocumentView(p)
        v.resize(900, 1100)
        v.show()
        APP.processEvents()
        v.tool = "edittext"
        self.addCleanup(v.close_doc)
        return v

    def edit(self, v):
        r = v.doc[0].search_for("Sideways words")[0]
        with mock.patch.object(dialogs, "get_text", side_effect=AssertionError("dialog")):
            v.edit_text_at(0, (r.tl + r.br) / 2)
        ed = v._inline
        self.assertIsNotNone(ed)                         # on the page, no dialog
        box = ed.geometry()
        self.assertGreater(box.width(), box.height())    # upright box
        line = v.pages[0].to_screen(r)
        self.assertTrue(box.intersects(line.toRect()))   # sits at the line
        ed.text.setPlainText("Turned text")
        ed.commit()
        self.assertIsNone(v._inline)
        page = v.doc[0]
        self.assertTrue(page.search_for("Turned text"))
        self.assertFalse(page.search_for("Sideways words"))
        d = [ln["dir"] for b in page.get_text("dict")["blocks"] for ln in b.get("lines", [])
             if "Turned" in "".join(s["text"] for s in ln["spans"])]
        self.assertEqual(len(d), 1)
        return d[0]

    def test_rotated_line(self):
        dx, dy = self.edit(self.view(text_rotate=90))
        self.assertAlmostEqual(dx, 0, places=2)          # still runs up the page
        self.assertAlmostEqual(abs(dy), 1, places=2)

    def test_upright_text_on_rotated_page(self):
        dx, dy = self.edit(self.view(page_rotation=90, text_rotate=0))
        self.assertAlmostEqual(dx, 1, places=2)


if __name__ == "__main__":
    unittest.main()
