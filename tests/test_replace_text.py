"""Edit > Replace text: replaces in the page text across pages as one undo step, with match
case / whole words, and leaves other text alone.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_replace_text
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

from kanzonas.document_view import DocumentView  # noqa: E402
from kanzonas.replace_dialog import ReplaceDialog  # noqa: E402


class ReplaceText(unittest.TestCase):
    def view(self):
        d = F.open()
        for i in range(3):
            pg = d.new_page()
            pg.insert_text((72, 100), f"Contractor: ACME Builders page {i + 1}", fontsize=12)
            pg.insert_text((72, 140), "acme supplies the ACMEX parts", fontsize=12)
            pg.insert_text((72, 180), "Nothing to change here", fontsize=12)
        p = os.path.join(tempfile.mkdtemp(), "r.pdf")
        d.save(p)
        v = DocumentView(p)
        self.addCleanup(v.close_doc)
        return v

    def test_replace_all_whole_words_any_case(self):
        v = self.view()
        found, lines, skipped = v.replace_text("acme", "Zenith", whole_words=True)
        self.assertEqual((found, lines, skipped), (6, 6, []))
        for i in range(3):
            t = v.doc[i].get_text()
            self.assertIn(f"Contractor: Zenith Builders page {i + 1}", t)
            self.assertIn("Zenith supplies the ACMEX parts", t)       # ACMEX isn't a whole word
            self.assertIn("Nothing to change here", t)
        v.undo()                                                    # one step undoes it all
        self.assertIn("ACME Builders", v.doc[2].get_text())
        self.assertNotIn("Zenith", v.doc[0].get_text())

    def test_match_case_and_this_page(self):
        v = self.view()
        found, _l, _s = v.replace_text("ACME", "Zenith", match_case=True, pages=[1])
        self.assertEqual(found, 2)                                  # ACME and ACMEX
        self.assertIn("acme supplies the ZenithX parts", v.doc[1].get_text())
        self.assertIn("ACME Builders", v.doc[0].get_text())

    def test_not_found_and_redaction_pages_skipped(self):
        v = self.view()
        self.assertEqual(v.replace_text("nowhere", "x"), (0, 0, []))
        v.doc[0].add_redact_annot(F.Rect(60, 170, 300, 190))
        found, _l, skipped = v.replace_text("Builders", "Co.")
        self.assertEqual((found, skipped), (2, [0]))

    def test_dialog(self):
        v = self.view()
        dlg = ReplaceDialog(None, v, "Builders")
        dlg.repl.setText("Partners")
        dlg.go.click()
        self.assertIn("Replaced 3 matches in 3 lines", dlg.result.text())
        self.assertIn("ACME Partners", v.doc[1].get_text())


if __name__ == "__main__":
    unittest.main()
