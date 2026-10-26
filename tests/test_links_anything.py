"""Links on anything: selected text, markups, the page's own pictures, shapes and text, or
new link text written into the page; one link over several lines acts as one; links follow
what they were made for when it moves and go when it's deleted; editing linked words keeps
their link; with the Select tool a link opens only on Ctrl+click.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_links_anything
"""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402
from PySide6.QtCore import QEvent, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QMouseEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QMenu  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import annotations, links, page_objects, text_edit  # noqa: E402
from kanzonas.document_view import DocumentView  # noqa: E402
from kanzonas.link_dialog import LinkDialog  # noqa: E402


def answer(url="", page=None, look=None, text=None, write=None):
    """A stand-in for the link window: fills it in and clicks OK."""
    def exec_(dlg):
        if page is not None:
            dlg.page.setValue(page)
            dlg.to_page.setChecked(True)
        else:
            dlg.url.setText(url)
            dlg._address_typed(url)
        if look:
            dlg.look.setCurrentIndex(dlg.look.findData(look))
        if write is not None and dlg.write is not None:
            dlg.write.setChecked(write)
        if text is not None and dlg.text is not None:
            dlg.text.setText(text)
            dlg._own_text(text)
        dlg._ok()
        return 1 if dlg.result_value else 0
    return mock.patch.object(LinkDialog, "exec", exec_)


def reloaded(v, index=0):
    return pymupdf.open("pdf", v.doc.tobytes())[index]


def uris(page):
    return [ln.get("uri") for ln in page.get_links()]


def shapes(page):
    return [it for it in page_objects.Objects(page).items if it["kind"] == "shape"]


class Base(unittest.TestCase):
    def make(self, rotation=0, pages=2):
        d = pymupdf.open()
        for _ in range(pages):
            p = d.new_page()
            p.set_rotation(rotation)
        d[0].insert_text((72, 100), "See the plans on our website", fontsize=12)
        d[0].insert_text((72, 115), "and the details too", fontsize=12)
        path = os.path.join(tempfile.mkdtemp(), "t.pdf")
        d.save(path)
        v = DocumentView(path)
        self.addCleanup(v.close_doc)
        return v

    def select_text(self, v, a, b):
        spans = v.text_selection_span(0, pymupdf.Point(a), 0, pymupdf.Point(b))
        v.set_text_spans([(i, words) for i, _mode, words in spans])


class SelectedText(Base):
    def test_two_lines_become_one_underlined_link(self):
        v = self.make()
        self.select_text(v, (100, 96), (120, 111))           # from "plans" to "details"
        self.assertIn("\n", v.selected_text())
        with answer("www.example.com"):
            v.add_link_to_selection()
        page = reloaded(v)
        self.assertEqual(uris(page), ["https://www.example.com"] * 2)
        mine = links.read(v.doc[0])
        self.assertEqual(len({ln["group"] for ln in mine}), 1)        # act as one
        self.assertEqual({ln["look"] for ln in mine}, {"underline"})
        self.assertEqual(len(shapes(v.doc[0])), 2)                    # one underline a line
        # the words are untouched
        self.assertIn("See the plans on our website", page.get_text())
        # Edit link changes both; Remove link takes both and their underlines, not the words
        v.edit_link(0, v.link_at(0, pymupdf.Point(110, 96)), ("page", 1, "underline"))
        self.assertEqual([ln["kind"] for ln in reloaded(v).get_links()], [pymupdf.LINK_GOTO] * 2)
        v.remove_link_at(0, pymupdf.Point(110, 111))
        page = reloaded(v)
        self.assertEqual(page.get_links(), [])
        self.assertEqual(shapes(page), [])
        self.assertIn("and the details too", page.get_text())

    def test_editing_linked_words_keeps_the_link(self):
        v = self.make()
        v.add_link(0, pymupdf.Rect(70, 88, 250, 103), ("uri", "https://cad.example", "none"))
        line = next(ln for _r, ln in v._lines(0) if "website" in text_edit.line_text(ln))
        v._apply_text_edit(0, line, "See the drawings on our website", (0, 0), None)
        page = reloaded(v)
        self.assertIn("See the drawings", page.get_text())
        self.assertEqual(uris(page), ["https://cad.example"])
        # and a line moved with Edit text takes its link along
        line = next(ln for _r, ln in v._lines(0) if "drawings" in text_edit.line_text(ln))
        v.move_text_line(0, pymupdf.Point(100, 96), (0, 200))
        self.assertGreater(pymupdf.Rect(reloaded(v).get_links()[0]["from"]).y0, 250)


class NewLinkText(Base):
    def test_click_with_the_links_tool_writes_the_address(self):
        v = self.make()
        with answer("www.kanzonas.example"):
            v.apply_drag_tool(0, "link", pymupdf.Point(100, 400), pymupdf.Point(100, 400), True)
        page = reloaded(v)
        self.assertIn("www.kanzonas.example", page.get_text())        # the address shows
        self.assertEqual(uris(page), ["https://www.kanzonas.example"])
        span = next(s for b in page.get_text("dict")["blocks"] for ln in b.get("lines", [])
                    for s in ln["spans"] if "kanzonas" in s["text"])
        self.assertEqual(span["color"], 0x0059D9)                     # link blue
        r = pymupdf.Rect(page.get_links()[0]["from"])
        self.assertTrue(r.intersects(pymupdf.Rect(span["bbox"])))    # the link is on the words
        self.assertEqual(len(shapes(page)), 1)                        # underlined
        # its own words change with the link, and go with it
        v.edit_link(0, v.link_at(0, pymupdf.Point(110, 400)),
                    ("uri", "https://www.kanzonas.example", "underline", "Our website"))
        page = reloaded(v)
        self.assertIn("Our website", page.get_text())
        self.assertNotIn("kanzonas.example", page.get_text())
        v.remove_link_at(0, pymupdf.Point(110, 400))
        page = reloaded(v)
        self.assertNotIn("Our website", page.get_text())
        self.assertEqual((page.get_links(), shapes(page)), ([], []))
        v.undo()
        self.assertIn("Our website", reloaded(v).get_text())

    def test_own_words_and_a_page_link(self):
        v = self.make()
        with answer(page=2, text="Floor plan"):
            v.apply_drag_tool(0, "link", pymupdf.Point(300, 500), pymupdf.Point(420, 520), False)
        page = reloaded(v)
        self.assertIn("Floor plan", page.get_text())
        self.assertEqual(page.get_links()[0]["page"], 1)

    def test_a_box_over_content_makes_it_clickable_without_text(self):
        v = self.make()
        with answer("example.com", write=True):
            v.apply_drag_tool(0, "link", pymupdf.Point(68, 85), pymupdf.Point(260, 104), False)
        page = reloaded(v)
        self.assertEqual(page.get_text().count("example"), 0)         # nothing written
        self.assertEqual(uris(page), ["https://example.com"])

    def test_rotated_page_text_reads_upright(self):
        v = self.make(rotation=90)
        with answer("rotated.example"):
            v.apply_drag_tool(0, "link", pymupdf.Point(300, 300), pymupdf.Point(300, 300), True)
        page = reloaded(v)
        line = next(ln for b in page.get_text("dict")["blocks"] for ln in b.get("lines", [])
                    if "rotated" in "".join(s["text"] for s in ln["spans"]))
        # reads left to right as the page is shown (the text runs along the rotated page)
        self.assertNotEqual(tuple(round(c) for c in line["dir"]), (1, 0))
        self.assertEqual(uris(page), ["https://rotated.example"])


class FollowsItsItem(Base):
    def test_markup_moves_and_deletes_with_its_link(self):
        v = self.make()
        model = {"kind": "rect", "rect": pymupdf.Rect(300, 300, 400, 360),
                 "props": annotations.tool_props("rect")}
        v.modify(lambda: annotations.write(v.doc[0], model), [0])
        xref = v.annot_at(0, pymupdf.Point(300, 330))
        v.select_xref(0, xref)
        with answer("markup.example"):
            v.add_link_to_selection()
        self.assertEqual(uris(reloaded(v)), ["https://markup.example"])
        m = annotations.moved(v.selected_models()[0][1], pymupdf.Point(50, 100))
        v.commit_model(0, v.selection[1], m)
        r = pymupdf.Rect(reloaded(v).get_links()[0]["from"])
        self.assertAlmostEqual(r.x0, 350, delta=3)
        self.assertAlmostEqual(r.y0, 400, delta=3)
        v.delete_selected()
        self.assertEqual(reloaded(v).get_links(), [])

    def test_shape_and_text_paragraph_with_edit_objects(self):
        v = self.make()
        v.modify(lambda: v.doc[0].draw_rect(pymupdf.Rect(300, 600, 360, 640), width=2), [0])
        item = v.object_at(0, pymupdf.Point(300, 620))
        self.assertEqual(item["kind"], "shape")
        v.select_objects(0, [item])
        with answer("shape.example"):
            v.add_link_to_selection()
        v.select_objects(0, [v.object_at(0, pymupdf.Point(300, 620))])
        old = v.selected_objects_rect()
        v.move_objects(old + (100, 0, 100, 0))
        r = pymupdf.Rect(reloaded(v).get_links()[0]["from"])
        self.assertAlmostEqual(r.x0, old.x0 + 100, delta=3)
        v.select_objects(0, [v.object_at(0, pymupdf.Point(400, 620))])
        v.delete_objects()
        self.assertEqual(reloaded(v).get_links(), [])
        # a paragraph of text with an underlined link: both move, underline included
        self.select_text(v, (72, 96), (200, 96))
        with answer("para.example"):
            v.add_link_to_selection()
        para = v.object_at(0, pymupdf.Point(100, 96))
        self.assertEqual(para["kind"], "text")
        v.select_objects(0, [para])
        v.move_objects(para["rect"] + (0, 300, 0, 300))
        page = reloaded(v)
        self.assertGreater(pymupdf.Rect(page.get_links()[0]["from"]).y0, 380)
        self.assertTrue(all(s["rect"].y0 > 380 for s in shapes(page)))


class Clicking(Base):
    def click(self, v, pt, mods=Qt.NoModifier):
        w = v.pages[0]
        pos = w.to_screen_pt(pymupdf.Point(pt))
        for kind, f in ((QEvent.MouseButtonPress, w.mousePressEvent),
                        (QEvent.MouseButtonRelease, w.mouseReleaseEvent)):
            f(QMouseEvent(kind, pos, w.mapToGlobal(pos), Qt.LeftButton,
                          Qt.LeftButton if kind == QEvent.MouseButtonPress else Qt.NoButton,
                          mods))

    def test_select_needs_ctrl_hand_doesnt(self):
        v = self.make()
        v.add_link(0, pymupdf.Rect(70, 88, 250, 103), ("page", 1, "none"))
        opened = []
        with mock.patch.object(DocumentView, "follow_link", lambda self, ln: opened.append(ln)):
            v.set_tool("select")
            self.click(v, (100, 96))
            self.assertEqual(opened, [])                         # selects, doesn't open
            self.click(v, (100, 96), Qt.ControlModifier)
            self.assertEqual(len(opened), 1)
            v.set_tool("hand")
            self.click(v, (100, 96))
            self.assertEqual(len(opened), 2)
            v.set_tool("edittext")
            self.click(v, (100, 96), Qt.ControlModifier)
            self.assertEqual(len(opened), 2)                     # editing never opens it

    def test_right_click_offers_add_edit_remove(self):
        v = self.make()
        v.set_tool("select")
        self.select_text(v, (72, 96), (200, 96))
        w = v.pages[0]
        seen = []

        class Menu(QMenu):
            def exec(self, *_a):
                seen.append([a.text() for a in self.actions() if a.text()])
        pos = w.to_screen_pt(pymupdf.Point(100, 96))
        with mock.patch("PySide6.QtWidgets.QMenu", Menu):
            w.mousePressEvent(QMouseEvent(QEvent.MouseButtonPress, pos, w.mapToGlobal(pos),
                                          Qt.RightButton, Qt.RightButton, Qt.NoModifier))
        self.assertIn("Add link...", seen[0])
        v.add_link(0, pymupdf.Rect(70, 88, 250, 103), ("page", 1, "none"))
        v.clear_text_selection()
        with mock.patch("PySide6.QtWidgets.QMenu", Menu):
            w.mousePressEvent(QMouseEvent(QEvent.MouseButtonPress, pos, w.mapToGlobal(pos),
                                          Qt.RightButton, Qt.RightButton, Qt.NoModifier))
        self.assertIn("Edit link...", seen[1])
        self.assertIn("Remove link", seen[1])


if __name__ == "__main__":
    unittest.main()
