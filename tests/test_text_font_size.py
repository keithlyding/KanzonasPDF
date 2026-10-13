"""Font size for Edit text and Add text: Edit text keeps each line's size unless a size is
picked in Properties; changing the size while typing shows it right away and writes the text
at the new size.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_text_font_size
"""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf as F  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import annotations as A  # noqa: E402
from kanzonas.document_view import DocumentView  # noqa: E402
from kanzonas.properties import PropertiesPanel  # noqa: E402


def sizes(page, word):
    return [round(s["size"], 1) for b in page.get_text("dict")["blocks"]
            for ln in b.get("lines", []) for s in ln["spans"] if word in s["text"]]


class TextFontSize(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["HOME"] = self.tmp
        self.addCleanup(mock.patch.stopall)
        for n in ("warning", "information"):
            mock.patch.object(QMessageBox, n, return_value=None).start()
        self.saved = {k: A.tool_props(k) for k in ("addtext", "edittext")}
        self.addCleanup(lambda: [A.set_tool_props(k, v) for k, v in self.saved.items()])

    def view(self):
        d = F.open()
        d.new_page().insert_text((72, 100), "Old words here", fontsize=14)
        p = os.path.join(self.tmp, "in%d.pdf" % len(os.listdir(self.tmp)))
        d.save(p)
        v = DocumentView(p)
        v.resize(900, 1100)
        v.show()
        APP.processEvents()
        self.addCleanup(v.close_doc)
        return v

    def edit(self, v, text):
        v.edit_text_at(0, F.Point(80, 96))
        self.assertIsNotNone(v._inline)
        v._inline.text.setPlainText(text)
        v.commit_pending()

    def test_edit_text_keeps_the_line_size_by_default(self):
        self.assertEqual(A.PAGE_TEXT_TOOLS["edittext"]["fontsize"], 0)
        A.set_tool_props("edittext", {"font": "", "bold": False, "italic": False, "fontsize": 0})
        v = self.view()
        self.edit(v, "New words here")
        self.assertEqual(sizes(v.doc[0], "New"), [14.0])

    def test_edit_text_with_a_size(self):
        A.set_tool_props("edittext", {"font": "", "bold": False, "italic": False, "fontsize": 20})
        v = self.view()
        self.edit(v, "Old words here")         # same text, new size: still rewritten
        self.assertEqual(sizes(v.doc[0], "Old"), [20.0])
        v.undo()
        self.assertEqual(sizes(v.doc[0], "Old"), [14.0])

    def test_size_changed_while_typing(self):
        A.set_tool_props("edittext", {"font": "", "bold": False, "italic": False, "fontsize": 0})
        v = self.view()
        v.edit_text_at(0, F.Point(80, 96))
        before = v._inline.text.font().pixelSize()
        A.set_tool_props("edittext", {"font": "", "bold": False, "italic": False, "fontsize": 28})
        v.text_tool_props_changed()
        self.assertGreater(v._inline.text.font().pixelSize(), before)
        v._inline.text.setPlainText("Bigger words")
        v.commit_pending()
        self.assertEqual(sizes(v.doc[0], "Bigger"), [28.0])

        A.set_tool_props("addtext", {"font": "", "bold": False, "italic": False,
                                     "fontsize": 12, "text_color": "#000000"})
        v.add_text_at(0, F.Point(100, 300))
        A.set_tool_props("addtext", {"font": "", "bold": False, "italic": False,
                                     "fontsize": 24, "text_color": "#000000"})
        v.text_tool_props_changed()
        self.assertEqual(v._inline.text.font().pixelSize(), round(24 * v.zoom))
        v._inline.text.setPlainText("Added")
        v.commit_pending()
        self.assertEqual(sizes(v.doc[0], "Added"), [24.0])

    def test_properties_offer_keep_for_edit_text(self):
        panel = PropertiesPanel()
        panel.show_target("edittext", A.tool_props("edittext") | {"fontsize": 0})
        self.assertFalse(panel.rows["fontsize"][1].isHidden())
        self.assertEqual(panel.fontsize.text(), "Keep the line's size")
        panel.show_target("addtext", A.tool_props("addtext"))
        self.assertEqual(panel.fontsize.minimum(), 4)


if __name__ == "__main__":
    unittest.main()
