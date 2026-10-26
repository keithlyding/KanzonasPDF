"""Text written into the page can be selected with Edit objects and deleted (Delete key or
right-click) or moved; Edit text's font size shows the line's own size and never sticks
from one edit to the next.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_text_objects
"""
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402
from PySide6.QtCore import QEvent, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QKeyEvent, QMouseEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import annotations, text_edit  # noqa: E402
from kanzonas.document_view import DocumentView  # noqa: E402
from kanzonas.main_window import MainWindow  # noqa: E402


def texts(page):
    return [(text_edit.line_text(ln), round(max(s["size"] for s in ln["spans"]), 2))
            for _r, ln in text_edit.text_lines(page)]


def center(r):
    return pymupdf.Point((r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2)


def menu_answer(pick):
    """Right-click menus open without waiting for a click; pick(menu) chooses."""
    class Menu(QMenu):
        def exec(self, *_a):
            pick(self)
    return mock.patch("PySide6.QtWidgets.QMenu", Menu)


def set_addtext(size):
    p = annotations.tool_props("addtext")
    p.update({"fontsize": size, "font": ""})
    annotations.set_tool_props("addtext", p)


class Base(unittest.TestCase):
    def make(self, scan=False):
        d = pymupdf.open()
        p = d.new_page()
        if scan:
            # a picture covering the page (a scan) with a line drawn on it
            src = pymupdf.open()
            sp = src.new_page()
            sp.draw_line((72, 210), (400, 210), width=1)
            sp.insert_text((72, 300), "Printed on the form", fontsize=11)
            p.insert_image(p.rect, stream=sp.get_pixmap(dpi=100).tobytes("png"))
        p.insert_text((72, 500), "Other text stays", fontsize=11)
        path = os.path.join(tempfile.mkdtemp(), "t.pdf")
        d.save(path)
        v = DocumentView(path)
        self.addCleanup(v.close_doc)
        return v

    def add_text(self, v, pt, text, size=12):
        set_addtext(size)
        v.add_text_at(0, pymupdf.Point(pt))
        v._inline.committed.emit(text, 0, 0, None)


class DeleteText(Base):
    def test_select_with_edit_objects_and_press_delete(self):
        v = self.make(scan=True)
        self.add_text(v, (100, 200), "Keith Lyding\nInspector")
        v.set_tool("editobjects")
        item = v.object_at(0, pymupdf.Point(110, 196))
        self.assertEqual(item["kind"], "text")
        self.assertEqual(len(item["lines"]), 2)          # both lines written at once: one piece
        v.select_objects(0, [item])
        images = len(v.doc[0].get_images())
        v.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Delete, Qt.NoModifier))
        self.assertEqual(texts(v.doc[0]), [("Other text stays", 11.0)])
        self.assertEqual(len(v.doc[0].get_images()), images)     # the scan is untouched
        v.undo()
        self.assertIn(("Keith Lyding", 12.0), texts(v.doc[0]))

    def test_right_click_delete_in_edit_objects(self):
        v = self.make()
        self.add_text(v, (100, 200), "Remove me")
        v.set_tool("editobjects")
        w = v.pages[0]
        pos = w.to_screen_pt(pymupdf.Point(110, 196))
        chosen = []

        def run(menu):
            act = next(a for a in menu.actions() if a.text().startswith("Delete"))
            chosen.append([a.text() for a in menu.actions() if not a.isEnabled()])
            act.trigger()
        with menu_answer(run):
            w.mousePressEvent(QMouseEvent(QEvent.MouseButtonPress, pos, w.mapToGlobal(pos),
                                          Qt.RightButton, Qt.RightButton, Qt.NoModifier))
        self.assertEqual(texts(v.doc[0]), [("Other text stays", 11.0)])
        self.assertIn("Rotate clockwise", chosen[0])        # text isn't turned here

    def test_right_click_delete_text_with_edit_text(self):
        v = self.make()
        self.add_text(v, (100, 200), "Gone soon")
        v.set_tool("edittext")
        w = v.pages[0]
        pos = w.to_screen_pt(pymupdf.Point(110, 196))
        with menu_answer(lambda menu: next(
                a for a in menu.actions() if a.text() == "Delete text").trigger()):
            w.mousePressEvent(QMouseEvent(QEvent.MouseButtonPress, pos, w.mapToGlobal(pos),
                                          Qt.RightButton, Qt.RightButton, Qt.NoModifier))
        self.assertEqual(texts(v.doc[0]), [("Other text stays", 11.0)])

    def test_overlapping_other_text_asks_first(self):
        v = self.make()
        self.add_text(v, (72, 506), "XXXXXXXX")              # overlapping "Other text stays"
        item = next(it for it in v.text_objects(0) if "XXXX" in
                    text_edit.line_text(it["lines"][0][1]))
        v.select_objects(0, [item])
        asked = []
        with mock.patch.object(QMessageBox, "question",
                               lambda *a, **k: (asked.append(a[2]), QMessageBox.No)[1]):
            v.delete_objects()
        self.assertTrue(asked and "overlap" in asked[0])
        self.assertEqual(len(texts(v.doc[0])), 2)            # No: nothing deleted

    def test_invisible_ocr_text_is_not_an_object(self):
        v = self.make()
        v.doc[0].insert_text((72, 650), "hidden OCR layer", fontsize=10, render_mode=3)
        v._clear_page_caches([0])
        self.assertFalse([it for it in v.text_objects(0)
                          if "hidden" in text_edit.line_text(it["lines"][0][1])])

    def test_move_text_with_edit_objects(self):
        v = self.make()
        self.add_text(v, (100, 200), "Move me\nand me")
        item = v.object_at(0, pymupdf.Point(110, 196))
        v.select_objects(0, [item])
        old = pymupdf.Rect(item["rect"])
        v.move_objects(old + (50, 100, 50, 100))
        moved = next(it for it in v.text_objects(0) if "Move me" in
                     text_edit.line_text(it["lines"][0][1]))
        self.assertAlmostEqual(moved["rect"].x0, old.x0 + 50, delta=1)
        self.assertAlmostEqual(moved["rect"].y0, old.y0 + 100, delta=1)
        self.assertIn(("and me", 12.0), texts(v.doc[0]))
        self.assertEqual(v.selected_objects()[0]["kind"], "text")   # still selected


    def test_a_selection_box_takes_text_only_without_shapes(self):
        v = self.make()
        self.add_text(v, (100, 200), "Label")
        only_text = v.objects_in(0, pymupdf.Rect(90, 180, 200, 210))
        self.assertEqual([it["kind"] for it in only_text], ["text"])
        v.doc[0].draw_rect(pymupdf.Rect(95, 185, 190, 205), width=1)
        v._clear_page_caches([0])
        both = v.objects_in(0, pymupdf.Rect(90, 180, 200, 210))
        self.assertTrue(both and all(it["kind"] != "text" for it in both))


class EditTextSize(Base):
    def test_added_text_keeps_its_size_and_the_panel_shows_it(self):
        annotations.set_tool_props("edittext", {"font": "", "bold": False, "italic": False,
                                                "fontsize": 0})
        v = self.make()
        self.add_text(v, (100, 200), "Twelve point")
        r = next(r for r, ln in v._lines(0) if "Twelve" in text_edit.line_text(ln))
        shown = []
        v.textToolPropsChanged.connect(
            lambda: shown.append(annotations.tool_props("edittext")["fontsize"]))
        v.edit_text_at(0, center(r))
        self.assertEqual(shown, [12.0])                     # the line's own size
        v._inline.committed.emit("Twelve point edited", 0, 0, None)
        self.assertIn(("Twelve point edited", 12.0), texts(v.doc[0]))
        self.assertEqual(annotations.tool_props("edittext")["fontsize"], 0)   # not kept

    def test_a_size_picked_while_editing_changes_that_line_only(self):
        v = self.make()
        self.add_text(v, (100, 200), "First")
        self.add_text(v, (100, 300), "Second")
        r1 = next(r for r, ln in v._lines(0) if text_edit.line_text(ln) == "First")
        v.edit_text_at(0, center(r1))
        p = annotations.tool_props("edittext")
        p["fontsize"] = 16
        annotations.set_tool_props("edittext", p)            # picked in Properties
        v._inline.committed.emit("First", 0, 0, None)
        r2 = next(r for r, ln in v._lines(0) if text_edit.line_text(ln) == "Second")
        v.edit_text_at(0, center(r2))
        v._inline.committed.emit("Second line", 0, 0, None)
        self.assertIn(("First", 16.0), texts(v.doc[0]))
        self.assertIn(("Second line", 12.0), texts(v.doc[0]))

    def test_a_size_saved_by_an_older_version_is_dropped(self):
        s = annotations._settings()
        s.setValue("tool_defaults", json.dumps({"edittext": {"fontsize": 9},
                                                "textbox": {"fontsize": 14}}))
        w = MainWindow()
        self.addCleanup(lambda: (setattr(w, "_close_confirmed", True), w.close()))
        saved = json.loads(s.value("tool_defaults"))
        self.assertNotIn("edittext", saved)
        self.assertEqual(saved["textbox"], {"fontsize": 14})        # other tools kept
        self.assertEqual(annotations.tool_props("edittext")["fontsize"], 0)


class Blocks(unittest.TestCase):
    def test_paragraphs(self):
        d = pymupdf.open()
        p = d.new_page()
        text_edit.add_text(p, (72, 100), "One\nparagraph\nhere", size=12)
        text_edit.add_text(p, (300, 100), "Beside it", size=12)
        p.insert_text((72, 300), "Far below", fontsize=12)
        got = [[text_edit.line_text(ln) for _r, ln in blk]
               for _box, blk in text_edit.text_blocks(text_edit.text_lines(p))]
        self.assertIn(["One", "paragraph", "here"], got)
        self.assertIn(["Beside it"], got)
        self.assertIn(["Far below"], got)


if __name__ == "__main__":
    unittest.main()
