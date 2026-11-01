"""What the 1.6.1 break-it battery found, fixed.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_battery_161
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas.document_view import DocumentView  # noqa: E402

P = pymupdf.Point


class SplitView(unittest.TestCase):
    def test_the_split_view_follows_markup_edits_in_the_main_view(self):
        d = pymupdf.open()
        d.new_page().insert_text((72, 72), "Some words on the page")
        path = os.path.join(tempfile.mkdtemp(), "m.pdf")
        d.save(path)
        v = DocumentView(path)
        self.addCleanup(v.close_doc)
        self.addCleanup(lambda: setattr(v, "dirty", False))

        def add():
            a = v.doc[0].add_text_annot((400, 400), "first content")
            a.update()
        v.modify(add, [0])
        m = DocumentView.mirror(v)
        self.addCleanup(m.deleteLater)
        here, there = P(405, 405), P(445, 405)
        self.assertEqual(m.annot_tooltip(0, here), v.annot_tooltip(0, here))
        v._set_selection(0, [v.annot_at(0, here)])
        x, model = v.selected_models()[0]
        model = dict(model, text="second content")
        v.commit_models(0, [(x, model)])
        self.assertIn("second content", m.annot_tooltip(0, here))   # (it read the old text)
        v._set_selection(0, [v.annot_at(0, here)])
        v.nudge(40, 0, 1)
        self.assertEqual(m.annot_tooltip(0, here), "")              # (it showed it here still)
        self.assertEqual(m.annot_tooltip(0, there), v.annot_tooltip(0, there))
        v.undo()
        self.assertEqual(m.annot_tooltip(0, here), v.annot_tooltip(0, here))


if __name__ == "__main__":
    unittest.main()
