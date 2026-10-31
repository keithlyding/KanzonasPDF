"""What a break-it battery of 1.5 found in pages, text and markups, fixed: moving a page while
MuPDF still holds an old page keeps the view in step with the file; Cut refuses on a page with
pending redaction marks and leaves the lines above and below alone; Replace text says when a
longer line runs into other text or off the page; a locked markup can't be selected, moved or
deleted from the Markups list; a page's scale goes with its copies; Edit text on a rotated page
puts the cursor at the click; a blank page after the current one has its size; Find counts a
hyphen-split word once; markups pasted on a page turned otherwise are turned too; Remove
watermarks keeps the background where Remove background can take it out.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_battery_151_pages
"""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import annotations, background, measure, page_tools, text_edit  # noqa: E402
from kanzonas.document_view import DocumentView  # noqa: E402

P = pymupdf.Point
LOREM = ("The Contractor shall deliver the goods described in Schedule A no later than thirty "
         "days after the Effective Date. Payment shall be made within forty-five days.")


def save(d, name="t.pdf"):
    path = os.path.join(tempfile.mkdtemp(), name)
    d.save(path)
    return path


def numbered(n=4, rotations=None):
    d = pymupdf.open()
    for k in range(n):
        pg = d.new_page(width=612, height=792)
        pg.insert_text((72, 60), f"PAGE {k + 1}", fontsize=16)
        pg.insert_textbox(pymupdf.Rect(72, 90, 540, 300), LOREM, fontsize=11)
        if rotations:
            pg.set_rotation(rotations[k])
    return save(d)


def first_lines(doc):
    return [doc[i].get_text().split("\n")[0] for i in range(doc.page_count)]


class Base(unittest.TestCase):
    def view(self, path):
        v = DocumentView(path)
        self.addCleanup(v.close_doc)
        return v


class MovePage(Base):
    def rect(self, v, i, box):
        v._create(i, {"kind": "rect", "props": v.tool_props("rect"), "rect": pymupdf.Rect(box)})

    def test_markup_rotate_markup_then_move_down(self):
        v = self.view(numbered())
        self.rect(v, 2, (100, 620, 200, 700))
        v.rotate_page(1, 90)
        self.rect(v, 2, (300, 620, 400, 700))
        v.move_page(1, 1)
        disk = pymupdf.open(stream=v.doc.tobytes(), filetype="pdf")
        self.assertEqual(first_lines(v.doc), ["PAGE 1", "PAGE 3", "PAGE 2", "PAGE 4"])
        self.assertEqual(first_lines(v.doc), first_lines(disk))

    def test_a_page_still_held_through_the_move(self):
        # MuPDF hands out a page it still has loaded by its old number after move_page:
        # the view opens the document afresh then, and undo, dirty and the path stay right
        path = numbered()
        v = self.view(path)
        held = v.doc[2]._pdf_page()            # (as a reference cycle would keep it)
        v.move_page(1, 1)
        self.assertEqual(first_lines(v.doc), ["PAGE 1", "PAGE 3", "PAGE 2", "PAGE 4"])
        self.assertEqual(first_lines(pymupdf.open(stream=v.doc.tobytes(), filetype="pdf")),
                         ["PAGE 1", "PAGE 3", "PAGE 2", "PAGE 4"])
        self.assertTrue(v.dirty)
        self.assertEqual(v.path, path)
        v.undo()
        self.assertEqual(first_lines(v.doc), ["PAGE 1", "PAGE 2", "PAGE 3", "PAGE 4"])
        del held

    def test_reorder_with_a_page_held(self):
        v = self.view(numbered())
        held = v.doc[0]._pdf_page()
        self.assertTrue(v.reorder_pages([3, 2, 1, 0]))
        self.assertEqual(first_lines(v.doc), ["PAGE 4", "PAGE 3", "PAGE 2", "PAGE 1"])
        del held


class Cut(Base):
    def select(self, v, index, text, after=""):
        words = v._words(index)
        s = "".join(w[4] for w in words)
        k = s.index(text, s.index(after))
        v.text_sel = [(index, words[k:k + len(text)])]

    def test_refused_with_pending_redaction_marks(self):
        v = self.view(numbered(1))
        v.doc[0].add_redact_annot(pymupdf.Rect(72, 50, 200, 65))
        before = v.doc[0].get_text()
        self.select(v, 0, "Contractor")
        with mock.patch.object(QMessageBox, "warning") as warn:
            self.assertEqual(v.cut(), "blocked")
        warn.assert_called_once()
        self.assertEqual(v.doc[0].get_text(), before)
        self.assertEqual([a.type[0] for a in v.doc[0].annots()], [pymupdf.PDF_ANNOT_REDACT])

    def test_tight_lines_keep_their_letters(self):
        for lead in (10.0, 11.0, 13.2):
            d = pymupdf.open()
            pg = d.new_page()
            for k in range(3):
                pg.insert_text((72, 100 + k * lead), f"Line{k} alpha beta gamma delta gjpqy",
                               fontsize=11)
            v = self.view(save(d))
            self.select(v, 0, "lpha beta gam", after="Line1")
            words = v.text_sel[0][1]
            self.assertTrue(all(w[6] == v.text_sel[0][1][0][6] for w in words))
            self.assertEqual(v.cut(), "text")
            t = v.doc[0].get_text().split("\n")
            self.assertEqual(t[0], "Line0 alpha beta gamma delta gjpqy", lead)
            self.assertEqual(t[-2], "Line2 alpha beta gamma delta gjpqy", lead)
            self.assertNotIn("beta", t[1])


class ReplaceOverrun(Base):
    def columns(self):
        d = pymupdf.open()
        pg = d.new_page()
        pg.insert_textbox(pymupdf.Rect(72, 320, 290, 500), "Left column. " + LOREM, fontsize=10)
        pg.insert_textbox(pymupdf.Rect(320, 320, 540, 500), "Right column. " + LOREM, fontsize=10)
        return self.view(save(d))

    def test_longer_text_running_into_the_next_column_is_reported(self):
        v = self.columns()
        found, _lines, _skipped = v.replace_text("Contractor", "Supplier Incorporated Limited, "
                                                 "a Delaware corporation,", match_case=True)
        self.assertEqual(found, 2)
        self.assertEqual(v.replace_overruns, [0])

    def test_shorter_text_is_not(self):
        v = self.columns()
        v.replace_text("Contractor", "Seller", match_case=True)
        self.assertEqual(v.replace_overruns, [])


class LockedMarkup(Base):
    def test_markups_list_shows_but_does_not_select_or_delete_it(self):
        v = self.view(numbered(1))
        v._create(0, {"kind": "rect", "props": v.tool_props("rect"),
                      "rect": pymupdf.Rect(350, 500, 450, 600)})
        xref = [a.xref for a in v.doc[0].annots()][0]
        v.set_object_flags(0, [xref], locked=True)
        self.assertTrue(v.markup_locked(0, xref))
        v.reveal(0, xref)                       # a click on its row in the Markups list
        self.assertIsNone(v.selection)
        self.assertFalse(v.select_xref(0, xref))
        v._set_selection(0, [xref])             # (however it got selected)
        v.delete_selected()
        self.assertEqual([a.xref for a in v.doc[0].annots()], [xref])

    def test_main_window_delete_from_the_list_leaves_it(self):
        from kanzonas import main_window
        from kanzonas.main_window import MainWindow
        w = MainWindow()
        self.addCleanup(lambda: [setattr(x, "_close_confirmed", True) or x.close()
                                 for x in main_window.windows()])
        w.open_file(numbered(1))
        v = w.view()
        v._create(0, {"kind": "rect", "props": v.tool_props("rect"),
                      "rect": pymupdf.Rect(350, 500, 450, 600)})
        xref = [a.xref for a in v.doc[0].annots()][0]
        v.set_object_flags(0, [xref], locked=True)
        with mock.patch.object(QMessageBox, "information") as info:
            w._delete_markup(0, xref)
        info.assert_called_once()
        self.assertEqual([a.xref for a in v.doc[0].annots()], [xref])
        v.dirty = False


class PageScale(Base):
    def test_copies_keep_the_scale(self):
        v = self.view(numbered(2))
        v.set_page_scale([0], 0.1, "m", "1pt=0.1m")
        want = measure.get_scale(v.doc[0])[:3]
        v.duplicate_pages([0])
        self.assertEqual(measure.get_scale(v.doc[1])[:3], want)
        self.assertFalse(measure.get_scale(v.doc[2])[3])
        out = os.path.join(tempfile.mkdtemp(), "x.pdf")
        v.extract_pages(0, 0, out)
        with pymupdf.open(out) as e:
            self.assertEqual(measure.get_scale(e[0])[:3], want)
        # copy and paste into another document; insert from file
        other = self.view(numbered(1))
        other.paste_pages(v.pages_bytes([0]), 1)
        self.assertEqual(measure.get_scale(other.doc[1])[:3], want)
        from kanzonas import combine
        d = pymupdf.open(numbered(1))
        combine.insert_files(d, [out], 0, (612, 792))
        self.assertEqual(measure.get_scale(d[0])[:3], want)
        self.assertFalse(measure.get_scale(d[1])[3])


class RotatedEditText(Base):
    def test_cursor_at_the_click_on_a_rotated_page(self):
        v = self.view(numbered(1, rotations=[90]))
        v.resize(900, 900)
        v.show()
        APP.processEvents()
        _r, line = [x for x in v._lines(0) if "Contractor" in text_edit.line_text(x[1])][0]
        x = line["spans"][0]["bbox"][0]
        pt = P(x + 0.5 * (pymupdf.Rect(line["bbox"]).width), sum(line["bbox"][1::2]) / 2)
        v.edit_text_at(0, pt)
        ed = v._inline
        self.assertIsNotNone(ed)
        cur = ed.text.textCursor()
        self.assertFalse(cur.hasSelection())
        self.assertGreater(cur.position(), 10)
        self.assertLess(cur.position(), len(ed.text.toPlainText()) - 10)
        ed.canceled.emit()
        v._inline = None
        ed.deleteLater()

    def test_line_index_runs_along_the_line(self):
        d = pymupdf.open(numbered(1))
        _r, line = [x for x in text_edit.text_lines(d[0]) if "PAGE" in text_edit.line_text(x[1])][0]
        r = pymupdf.Rect(line["bbox"])
        self.assertEqual(text_edit.line_index(line, P(r.x0 - 5, r.y0)), 0)
        self.assertEqual(text_edit.line_index(line, P(r.x1 + 5, r.y0)), len("PAGE 1"))


class BlankPage(Base):
    def test_the_size_of_the_page_it_follows(self):
        d = pymupdf.open()
        d.new_page(width=612, height=792)
        d.new_page(width=842, height=1191)
        v = self.view(save(d))
        v.insert_blank(1)                       # after page 1
        self.assertEqual(tuple(round(c) for c in v.doc[1].rect[2:]), (612, 792))
        v.undo()
        v.insert_blank(2)                       # after the last page
        self.assertEqual(tuple(round(c) for c in v.doc[2].rect[2:]), (842, 1191))


class FindHyphen(Base):
    def test_a_hyphen_split_word_is_one_match(self):
        d = pymupdf.open()
        pg = d.new_page()
        pg.insert_text((72, 100), "The specifi-", fontsize=11)
        pg.insert_text((72, 114), "cation is final. specification", fontsize=11)
        v = self.view(save(d))
        v.find("specification")
        self.assertEqual(v._search_count(), 2)
        self.assertEqual(len(v.hit_rects((0, 0))), 2)
        self.assertEqual(v.search_position()[:2], (1, 2))
        v.find("specification")                 # next
        self.assertEqual(v.search_position()[:2], (2, 2))
        self.assertEqual(len(v.hit_rects(v.current_hit())), 1)


class PasteOnTurnedPage(Base):
    def test_page_turned_swaps_the_box(self):
        m = {"kind": "rect", "props": {}, "rect": pymupdf.Rect(0, 0, 100, 50)}
        r = annotations.page_turned(m, 270)["rect"]
        self.assertEqual((round(r.width), round(r.height)), (50, 100))

    def test_text_box_from_a_rotated_page(self):
        v = self.view(numbered(2, rotations=[0, 90]))
        page = v.doc[1]
        disp = pymupdf.Rect(100, 100, 300, 150)             # wide on screen
        v._create(1, {"kind": "textbox", "props": v.tool_props("textbox"), "text": "NOTE",
                      "rect": disp * page.derotation_matrix})
        del page
        xref = [a.xref for a in v.doc[1].annots()][0]
        v.select_xref(1, xref)
        self.assertEqual(v.copy(), "markups")
        with mock.patch.object(v, "paste_target", return_value=(0, P(100, 300))):
            self.assertEqual(v.paste(), "markups")
        pg = v.doc[0]                       # (kept alive while its Annot is used)
        a = list(pg.annots())[0]
        self.assertGreater(a.rect.width, a.rect.height)     # wide on screen here too
        self.assertIn(a.rotation, (0, -1))                   # and reading upright


class BackgroundAndWatermark(Base):
    def test_remove_background_after_remove_watermarks(self):
        path = numbered(1)
        with pymupdf.open(path) as d:
            original = d[0].get_pixmap(dpi=40).samples
        d = pymupdf.open(path)
        d[0].clean_contents()                   # one content stream
        background.apply(d, [0], {"kind": "color", "color": "#ffe0a0"})
        page_tools.add_watermark(d, {"text": "DRAFT", "pages": [0], "behind": True})
        page_tools.add_watermark(d, {"text": "COPY", "pages": [0]})
        self.assertTrue(page_tools.remove_watermarks(d, [0]))
        self.assertTrue(background.remove(d[0]))
        self.assertNotIn(b"/Background", d[0].read_contents())
        self.assertEqual(d[0].get_pixmap(dpi=40).samples, original)

    def test_a_background_already_merged_into_the_page(self):
        path = numbered(1)
        with pymupdf.open(path) as d:
            original = d[0].get_pixmap(dpi=40).samples
        d = pymupdf.open(path)
        background.apply(d, [0], {"kind": "color", "color": "#ffe0a0"})
        x = d[0].get_contents()[-1]
        d.update_stream(x, d[0].read_contents())     # (what an older version left)
        d[0].set_contents(x)
        self.assertTrue(background.remove(d[0]))
        self.assertNotIn(b"/Background", d[0].read_contents())
        self.assertEqual(d[0].get_pixmap(dpi=40).samples, original)


if __name__ == "__main__":
    unittest.main()
