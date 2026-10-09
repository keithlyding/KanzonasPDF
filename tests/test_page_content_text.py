"""Only markups stay editable in PDF viewers: pictures, added text, signatures and dates
are written into the page (Edit objects / Edit text change them). Fonts: Add text and Edit
text use installed fonts; text box comments use Helvetica / Times / Courier.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_page_content_text
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

from kanzonas import annotations as A, dialogs, text_edit  # noqa: E402
from kanzonas.document_view import DocumentView  # noqa: E402


def installed_family():
    """An installed font family to test with (skip when the machine has none)."""
    for key, path in text_edit._system_fonts().items():
        name = F.Font(fontfile=path).name
        for fam in ("Liberation Serif", "DejaVu Serif", "Times New Roman", "Georgia", "Arial"):
            if name.startswith(fam):
                return fam
    return None


class PageContentText(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["HOME"] = self.tmp
        self.addCleanup(mock.patch.stopall)
        for n in ("warning", "information"):
            mock.patch.object(QMessageBox, n, return_value=None).start()
        self.saved = {k: A.tool_props(k) for k in ("addtext", "edittext")}
        self.addCleanup(lambda: [A.set_tool_props(k, v) for k, v in self.saved.items()])

    def view(self, text=None):
        d = F.open()
        pg = d.new_page()
        if text:
            pg.insert_text((72, 100), text, fontsize=14)
        p = os.path.join(self.tmp, "in%d.pdf" % len(os.listdir(self.tmp)))
        d.save(p)
        v = DocumentView(p)
        v.resize(900, 1100)
        v.show()
        APP.processEvents()
        self.addCleanup(v.close_doc)
        return v

    def test_image_tool_writes_into_the_page(self):
        pm = F.Pixmap(F.csRGB, F.IRect(0, 0, 40, 20), 0)
        pm.set_rect(pm.irect, (0, 120, 215))
        png = os.path.join(self.tmp, "pic.png")
        pm.save(png)
        v = self.view()
        with mock.patch.object(dialogs, "open_file", return_value=png):
            v.place_image(0, F.Point(100, 100), F.Point(300, 200), False)
        self.assertEqual(len(list(v.doc[0].annots())), 0)
        self.assertEqual([it["kind"] for it in v.content_objects(0).items], ["picture"])

    def test_add_text_writes_page_text_in_the_chosen_font(self):
        fam = installed_family()
        if fam is None:
            self.skipTest("no installed font family to test with")
        v = self.view()
        A.set_tool_props("addtext", {"font": fam, "bold": True, "italic": False,
                                     "fontsize": 18, "text_color": "#0050ff"})
        v.add_text_at(0, F.Point(100, 300))
        v._inline.text.setPlainText("Added words")
        v.commit_pending()
        self.assertEqual(len(list(v.doc[0].annots())), 0)
        spans = [s for b in v.doc[0].get_text("dict")["blocks"] for line in b.get("lines", [])
                 for s in line["spans"] if s["text"] == "Added words"]
        self.assertEqual(len(spans), 1)
        self.assertIn(fam.replace(" ", "").lower(), spans[0]["font"].replace(" ", "").lower())
        self.assertEqual(round(spans[0]["size"]), 18)
        self.assertEqual(spans[0]["color"], 0x0050ff)

    def test_edit_text_can_change_a_lines_font(self):
        fam = installed_family()
        if fam is None:
            self.skipTest("no installed font family to test with")
        v = self.view("Original line here")
        A.set_tool_props("edittext", {"font": fam, "bold": False, "italic": False})
        v.edit_text_at(0, F.Point(80, 96))
        v.commit_pending()                      # same text: only the font changes
        spans = [s for b in v.doc[0].get_text("dict")["blocks"] for line in b.get("lines", [])
                 for s in line["spans"]]
        self.assertEqual(spans[0]["text"], "Original line here")
        self.assertIn(fam.replace(" ", "").lower(), spans[0]["font"].replace(" ", "").lower())

    def test_text_box_comment_font(self):
        v = self.view()
        v._create(0, {"kind": "textbox", "props": dict(A.DEFAULTS["textbox"], font="Times"),
                      "rect": F.Rect(50, 50, 300, 90), "text": "Comment in Times"})
        pg = v.doc[0]
        a = pg.first_annot
        self.assertIn("/TiRo", v.doc.xref_get_key(a.xref, "DA")[1])
        self.assertEqual(A.read(a)["props"]["font"], "Times")


if __name__ == "__main__":
    unittest.main()
