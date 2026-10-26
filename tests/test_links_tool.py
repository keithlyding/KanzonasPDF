"""Links tool: drag a box to add a link to a web address or a page; click a link to change
or delete it; undo; works on rotated pages.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_links_tool
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

from kanzonas.document_view import DocumentView  # noqa: E402
from kanzonas.link_dialog import LinkDialog, normalize_url  # noqa: E402


class LinksTool(unittest.TestCase):
    def view(self, rotation=0):
        d = F.open()
        for _ in range(3):
            d.new_page().set_rotation(rotation)
        p = os.path.join(tempfile.mkdtemp(), "l.pdf")
        d.save(p)
        v = DocumentView(p)
        self.addCleanup(v.close_doc)
        return v

    def test_normalize(self):
        self.assertEqual(normalize_url("www.example.com"), "https://www.example.com")
        self.assertEqual(normalize_url("me@x.org"), "mailto:me@x.org")
        self.assertEqual(normalize_url("http://a.b/c"), "http://a.b/c")
        self.assertEqual(normalize_url("  "), "")

    def test_add_change_delete_undo(self):
        v = self.view()
        v.add_link(0, F.Rect(100, 100, 200, 130), ("uri", "https://example.com"))
        links = v.doc[0].get_links()
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0]["uri"], "https://example.com")
        self.assertEqual(v.link_at(0, F.Point(150, 115))["uri"], "https://example.com")
        v.edit_link(0, v.link_at(0, F.Point(150, 115)), ("page", 2))
        ln = v.doc[0].get_links()
        self.assertEqual((len(ln), ln[0]["kind"], ln[0]["page"]), (1, F.LINK_GOTO, 2))
        self.assertEqual(F.Rect(ln[0]["from"]), F.Rect(100, 100, 200, 130))
        v.edit_link(0, v.link_at(0, F.Point(150, 115)), ("delete",))
        self.assertEqual(v.doc[0].get_links(), [])
        v.undo()
        self.assertEqual(v.doc[0].get_links()[0]["page"], 2)

    def test_rotated_page_keeps_place(self):
        v = self.view(rotation=90)
        r = F.Rect(100, 100, 200, 130)                       # unrotated page coordinates
        v.add_link(0, r, ("uri", "https://a.example"))
        shown = F.Rect(v.doc[0].get_links()[0]["from"])
        self.assertEqual(shown, r * v.doc[0].rotation_matrix)
        v.edit_link(0, v.doc[0].get_links()[0], ("uri", "https://b.example"))
        self.assertEqual(F.Rect(v.doc[0].get_links()[0]["from"]), shown)

    def test_tool_click_opens_link_for_editing(self):
        v = self.view()
        v.add_link(1, F.Rect(50, 50, 150, 80), ("uri", "https://example.com"))
        with mock.patch.object(LinkDialog, "exec", lambda self: (self._delete(), 1)[1]):
            v.apply_drag_tool(1, "link", F.Point(100, 60), F.Point(100, 60), True)
        self.assertEqual(v.doc[1].get_links(), [])
        # dragging a box asks where it goes
        def answer(dlg):
            dlg.url.setText("www.example.org")
            dlg._ok()
            return 1
        with mock.patch.object(LinkDialog, "exec", answer):
            v.apply_drag_tool(1, "link", F.Point(10, 10), F.Point(90, 40), False)
        self.assertEqual(v.doc[1].get_links()[0]["uri"], "https://www.example.org")


if __name__ == "__main__":
    unittest.main()


class VisibleLinks(unittest.TestCase):
    def view(self):
        d = F.open()
        d.new_page(width=300, height=200)
        p = os.path.join(tempfile.mkdtemp(), "v.pdf")
        d.save(p)
        v = DocumentView(p)
        v.resize(600, 500)
        v.show()
        APP.processEvents()
        self.addCleanup(v.close_doc)
        return v

    def blue_pixels(self, img, box):
        n = 0
        for y in range(int(box.top()), int(box.bottom()) + 1):
            for x in range(int(box.left()), int(box.right()) + 1):
                c = img.pixelColor(x, y)
                n += c.blue() > 150 and c.red() < 100
        return n

    def test_new_link_has_a_box_drawn_on_screen(self):
        from kanzonas.document_view import link_border
        v = self.view()
        v.add_link(0, F.Rect(40, 40, 200, 80), ("uri", "https://example.com"))
        ln = v.doc[0].get_links()[0]
        self.assertEqual(link_border(v.doc, ln["xref"])[0], 1.0)
        pw = v.pages[0]
        img = pw.grab().toImage()
        box = pw.to_screen(F.Rect(40, 40, 200, 80))
        self.assertGreater(self.blue_pixels(img, box.adjusted(-2, -2, 2, 2)), 50)
        # and it survives editing where it goes
        v.edit_link(0, v.doc[0].get_links()[0], ("page", 0, True))
        self.assertIsNotNone(link_border(v.doc, v.doc[0].get_links()[0]["xref"]))

    def test_hidden_link_option(self):
        from kanzonas.document_view import link_border
        v = self.view()
        v.add_link(0, F.Rect(40, 40, 200, 80), ("uri", "https://example.com", False))
        self.assertIsNone(link_border(v.doc, v.doc[0].get_links()[0]["xref"]))

    def test_dialog_remembers_the_look(self):
        dlg = LinkDialog(None, 3, ("uri", "https://a.example", False))   # (an older target)
        self.assertEqual(dlg.look.currentData(), "none")
        dlg._ok()
        self.assertEqual(dlg.result_value, ("uri", "https://a.example", "none", None))

    def test_printed_with_markups(self):
        from PySide6.QtCore import QRectF
        from PySide6.QtGui import QImage, QPainter
        from kanzonas.print_dialog import PrintDialog
        v = self.view()
        v.add_link(0, F.Rect(40, 40, 200, 80), ("uri", "https://example.com"))
        dlg = PrintDialog(None, v)
        img = QImage(600, 400, QImage.Format_RGB32)
        img.fill(0xFFFFFF)
        p = QPainter(img)
        dlg._draw_links(p, 0, QRectF(0, 0, 600, 400))
        p.end()
        self.assertGreater(self.blue_pixels(img, QRectF(78, 78, 324, 84)), 50)
