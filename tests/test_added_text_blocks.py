"""Text written with Add text is remembered as one block (added_text.py): Edit text on any of
its lines opens all of it, in a box of the width it wraps to, its line breaks (Shift+Enter)
and each word's style kept, the cursor where it was clicked, and writes it back as one block
from where it started (no creep across edits, saves and reopening). With Edit objects, page
text is copied, cut, pasted (same page, another page, another document) and duplicated as
page text with its styles; every step is one undo step. A redaction mark over a word of a
block takes the word out and leaves nothing of the block's marker. Files without the marker
work as before.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_added_text_blocks
"""
import os
import re
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402
from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtGui import QTextCursor  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

from tests.qt_fonts import ensure_font  # noqa: E402

ensure_font()      # (Windows' offscreen Qt has no font: texts measure 0 px)

from kanzonas import added_text, annotations, clip, text_edit, text_styles  # noqa: E402
from kanzonas.main_window import MainWindow  # noqa: E402
from tests.test_undo_journal import canon  # noqa: E402

NOTE = ("Notes: all work shall be done in accordance with the local building code and the "
        "drawings.")


def pump(n=5):
    for _ in range(n):
        APP.processEvents()


def lines_of(page):
    """[(text, (x, y) of its baseline's start)] of the page's lines, top to bottom."""
    out = []
    for _r, ln in text_edit.text_lines(page):
        o = ln["spans"][0]["origin"]
        out.append((text_edit.line_text(ln).strip(), (round(o[0], 2), round(o[1], 2))))
    return sorted(out, key=lambda t: (t[1][1], t[1][0]))


def styles(page):
    """{word: (bold, italic, underline, color)} of the page's words, as Edit text reads them."""
    out = {}
    for _r, ln in text_edit.text_lines(page):
        st = text_styles.read_line(page, ln)
        for m in re.finditer(r"\S+", st.text):
            k = st.keys[m.start()]
            out[m.group()] = (k.bold, k.italic, k.underline, k.color)
    return out


def props(page):
    """The blocks' numbers (origin rounded), in drawing order."""
    out = []
    for mk in added_text.markers(page):
        p = mk["props"]
        out.append(((round(p["origin"].x, 2), round(p["origin"].y, 2)), p["rotate"],
                    p["width"] and round(p["width"], 2), round(p["step"], 3),
                    [round(y, 2) for y in p["rows"]], sorted(p["breaks"])))
    return out


class Fixture(unittest.TestCase):
    PAGES = 2

    def setUp(self):
        for tool in ("addtext", "edittext"):
            annotations.reset_tool_props(tool)
        self.dir = tempfile.mkdtemp()
        self.path = self.blank("blocks.pdf")
        self.w = w = MainWindow()
        w.resize(1400, 900)
        w.show()
        pump()
        w.open_file(self.path)
        pump()
        self.v = w.view()

    def blank(self, name, pages=None):
        d = pymupdf.open()
        for _ in range(pages or self.PAGES):
            d.new_page()
        path = os.path.join(self.dir, name)
        d.save(path)
        d.close()
        return path

    def tearDown(self):
        self.w._close_confirmed = True
        for v in self.w._views():
            v.dirty = False
        self.w.close()
        pump()

    # ---- the person's steps --------------------------------------------------------------
    def screen(self, pt, index=0):
        pw = self.v.pages[index]
        return pw.to_screen(pymupdf.Rect(pt, pt)).topLeft().toPoint()

    def click(self, pt, index=0, mods=Qt.NoModifier):
        QTest.mouseClick(self.v.pages[index], Qt.LeftButton, mods, self.screen(pt, index))
        pump()

    def click_word(self, word, index=0, nth=0):
        wd = [x for x in self.v.doc[index].get_text("words") if x[4] == word][nth]
        c = pymupdf.Point((wd[0] + wd[2]) / 2, (wd[1] + wd[3]) / 2)
        self.click(c, index)
        return c

    def add(self, parts, at=(80, 120), width=None, index=0):
        """Add text: click, type parts (Shift+Enter between them), narrow the box to width
        points (its words wrap), click elsewhere."""
        self.w.set_tool("addtext")
        pump()
        self.click(pymupdf.Point(at), index)
        ed = self.v._inline
        for k, part in enumerate(parts):
            if k:
                QTest.keyClick(ed.text, Qt.Key_Return, Qt.ShiftModifier)
            QTest.keyClicks(ed.text, part)
        pump()
        if width:
            ed.resized_by_user = True
            ed.resize(int(width * self.v.zoom), ed.height())
            pump()
        self.finish(index)

    def finish(self, index=0):
        self.click(pymupdf.Point(500, 760), index)

    def edit_word(self, word, index=0):
        self.w.set_tool("edittext")
        pump()
        self.click_word(word, index)
        self.assertIsNotNone(self.v._inline)
        return self.v._inline

    def type_over(self, ed, old, new):
        """Select old in the box (as a double-click does) and type new."""
        t = ed.text.toPlainText()
        cur = ed.text.textCursor()
        cur.setPosition(t.index(old))
        cur.setPosition(t.index(old) + len(old), QTextCursor.KeepAnchor)
        ed.text.setTextCursor(cur)
        QTest.keyClicks(ed.text, new)
        pump()

    def select_text_object(self, word, index=0, add=False):
        self.w.set_tool("editobjects")
        pump()
        wd = [x for x in self.v.doc[index].get_text("words") if x[4] == word][0]
        c = pymupdf.Point((wd[0] + wd[2]) / 2, (wd[1] + wd[3]) / 2)
        self.click(c, index, Qt.ShiftModifier if add else Qt.NoModifier)
        self.assertTrue(self.v.obj_sel and any(it["kind"] == "text"
                                               for it in self.v.obj_sel[1]))

    def keys(self, key, index=0):
        self.v.setFocus()
        QTest.keyClick(self.v.pages[index], key, Qt.ControlModifier)
        pump()

    def mouse_to(self, pt, index=0):
        QTest.mouseMove(self.v.pages[index], self.screen(pt, index))
        pump()


class EditWhole(Fixture):
    def test_wrapped_text_opens_whole_and_is_written_back_as_one_block(self):
        self.add([NOTE], width=180)
        page = self.v.doc[0]
        before = lines_of(page)
        self.assertGreaterEqual(len(before), 3)             # (it wraps)
        mark = props(page)
        self.assertEqual(len(mark), 1)
        self.assertTrue(150 < mark[0][2] < 180, mark)       # the box's width
        ed = self.edit_word("accordance")
        self.assertEqual(ed.text.toPlainText(), NOTE)       # all of it, from any line
        pos = ed.text.textCursor().position()
        k = NOTE.index("accordance")
        self.assertTrue(k <= pos <= k + len("accordance"), pos)     # where it was clicked
        self.type_over(ed, "local", "city")
        self.finish()
        page = self.v.doc[0]
        after = lines_of(page)
        self.assertEqual(" ".join(t for t, _o in after), NOTE.replace("local", "city"))
        self.assertEqual([o for _t, o in after][0], before[0][1])  # from where it started
        self.assertEqual(props(page)[0][:4], mark[0][:4])   # the same wrap, still one block

    def test_line_breaks_stay(self):
        self.add(["Title of the note", "first point to make", "second point"])
        ed = self.edit_word("second")
        self.assertEqual(ed.text.toPlainText(),
                         "Title of the note\nfirst point to make\nsecond point")
        self.type_over(ed, "first", "1st")
        self.finish()
        self.assertEqual([t for t, _o in lines_of(self.v.doc[0])],
                         ["Title of the note", "1st point to make", "second point"])
        self.assertEqual(props(self.v.doc[0])[0][5], [0, 1])

    def test_wrapped_and_broken_lines_together(self):
        self.add([NOTE, "Second paragraph of words"], width=160)
        ed = self.edit_word("building")
        self.assertEqual(ed.text.toPlainText(), NOTE + "\nSecond paragraph of words")
        ed.cancel()
        pump()

    def test_each_word_keeps_its_style(self):
        self.w.set_tool("addtext")
        pump()
        self.click(pymupdf.Point(80, 120))
        ed = self.v._inline
        QTest.keyClicks(ed.text, "plain ")
        QTest.keyClick(ed.text, Qt.Key_B, Qt.ControlModifier)
        QTest.keyClicks(ed.text, "bold")
        QTest.keyClick(ed.text, Qt.Key_B, Qt.ControlModifier)
        QTest.keyClicks(ed.text, " and ")
        QTest.keyClick(ed.text, Qt.Key_U, Qt.ControlModifier)
        QTest.keyClicks(ed.text, "underlined")
        QTest.keyClick(ed.text, Qt.Key_U, Qt.ControlModifier)
        QTest.keyClick(ed.text, Qt.Key_Return, Qt.ShiftModifier)
        QTest.keyClicks(ed.text, "words on a line")
        pump()
        self.finish()
        got = styles(self.v.doc[0])
        self.assertTrue(got["bold"][0] and got["underlined"][2])
        ed = self.edit_word("words")
        self.assertEqual(ed.text.toPlainText(), "plain bold and underlined\nwords on a line")
        self.type_over(ed, "plain", "simple")
        self.finish()
        got = styles(self.v.doc[0])
        self.assertTrue(got["bold"][0])
        self.assertFalse(got["simple"][0])
        self.assertTrue(got["underlined"][2])
        self.assertFalse(got["words"][2])
        self.assertEqual(len(props(self.v.doc[0])), 1)

    def test_no_creep_across_edits_saves_and_reopening(self):
        self.add([NOTE, "Last line"], width=170)
        first = lines_of(self.v.doc[0])
        mark = props(self.v.doc[0])
        for cycle in range(5):
            # (as wide either way in Helvetica: the lines stay as they are)
            old, new = ("code", "cede") if cycle % 2 == 0 else ("cede", "code")
            ed = self.edit_word("building")
            self.type_over(ed, old, new)
            self.finish()
            self.assertTrue(self.w.save())
            self.v.dirty = False
            self.w.close_tab(self.w.tabs.currentIndex())
            pump()
            self.w.open_file(self.path)
            pump()
            self.v = self.w.view()
            got = lines_of(self.v.doc[0])
            self.assertEqual([o for _t, o in got], [o for _t, o in first], cycle)
            self.assertEqual(props(self.v.doc[0]), mark, cycle)
        self.assertEqual([t for t, _o in got], [t.replace("code", "cede") for t, _o in first])

    def test_undo_and_redo_are_exact(self):
        self.add([NOTE], width=180)
        before = canon(self.v.doc)
        ed = self.edit_word("drawings.")
        self.type_over(ed, "drawings", "plans")
        self.finish()
        after = canon(self.v.doc)
        self.assertNotEqual(after, before)
        self.v.undo()
        pump()
        self.assertEqual(canon(self.v.doc), before)
        self.v.redo()
        pump()
        self.assertEqual(canon(self.v.doc), after)

    def test_alt_click_still_edits_one_line(self):
        self.add([NOTE], width=180)
        self.w.set_tool("edittext")
        pump()
        wd = [x for x in self.v.doc[0].get_text("words") if x[4] == "accordance"][0]
        self.v.edit_text_at(0, pymupdf.Point((wd[0] + wd[2]) / 2, (wd[1] + wd[3]) / 2),
                            one_line=True)
        self.assertTrue(self.v._inline.text.toPlainText().startswith("accordance"))
        self.v._inline.cancel()
        pump()

    def test_moved_with_edit_objects_stays_one_block(self):
        self.add([NOTE], width=180)
        mark = props(self.v.doc[0])[0]
        self.select_text_object("building")
        r = self.v.selected_objects_rect()
        self.v.move_objects(r + (30, 40, 30, 40))
        pump()
        got = props(self.v.doc[0])
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0][0], (round(mark[0][0] + 30, 2), round(mark[0][1] + 40, 2)))
        self.assertEqual(got[0][2:], mark[2:])
        ed = self.edit_word("building")
        self.assertEqual(ed.text.toPlainText(), NOTE)
        ed.cancel()
        pump()


class RotatedPage(Fixture):
    """A sheet shown turned (its page /Rotate 90), as many drawings are."""
    def blank(self, name, pages=None):
        path = super().blank(name, pages)
        d = pymupdf.open(path)
        d[0].set_rotation(90)
        d.saveIncr()
        d.close()
        return path

    def test_added_text_on_a_turned_page_opens_whole(self):
        # (unrotated page coordinates: the text runs up the page from there)
        self.add([NOTE], at=(80, 500), width=180)
        page = self.v.doc[0]
        self.assertEqual(page.rotation, 90)
        mark = props(page)
        self.assertEqual(mark[0][1], 90)
        before = lines_of(page)
        ed = self.edit_word("accordance")
        self.assertEqual(ed.text.toPlainText(), NOTE)
        self.type_over(ed, "local", "city")
        self.finish()
        page = self.v.doc[0]
        self.assertEqual(props(page)[0][:4], mark[0][:4])
        self.assertEqual(lines_of(page)[0][1], before[0][1])
        self.assertIn("city", page.get_text())


class OldFiles(Fixture):
    def test_text_without_the_marker_is_edited_as_before(self):
        # (Add text up to 1.9 wrote this: its lines, no marker)
        page = self.v.doc[0]
        text_edit.add_text(page, (80, 120), NOTE, "", False, False, 20, (0, 0, 0), 180,
                           mark=False)
        del page
        self.v._clear_caches()
        ed = self.edit_word("accordance")
        self.assertTrue(ed.text.toPlainText().startswith("accordance"))   # its line only
        self.assertNotIn("Notes", ed.text.toPlainText())
        ed.cancel()
        pump()
        self.assertEqual(added_text.markers(self.v.doc[0]), [])


class Clipboard(Fixture):
    def setUp(self):
        super().setUp()
        self.add([NOTE, "Second paragraph"], width=180)
        self.src = lines_of(self.v.doc[0])

    def shifted(self, dx, dy, lines=None):
        return [(t, (round(o[0] + dx, 2), round(o[1] + dy, 2))) for t, o in lines or self.src]

    def offset_of(self, got):
        """(dx, dy) from the copied text's first line to the first matching line in got."""
        o = next(o for t, o in got if t == self.src[0][0] and o != self.src[0][1])
        return o[0] - self.src[0][1][0], o[1] - self.src[0][1][1]

    def test_copy_and_paste_on_the_same_page(self):
        self.select_text_object("building")
        self.keys(Qt.Key_C)
        kind, payload = clip.get()
        self.assertEqual(kind, "pagetext")
        self.assertIn("accordance", QApplication.clipboard().text())    # for other programs
        before = canon(self.v.doc)
        self.mouse_to(pymupdf.Point(100, 400))
        self.keys(Qt.Key_V)
        got = lines_of(self.v.doc[0])
        self.assertEqual(len(got), 2 * len(self.src))
        dx, dy = self.offset_of(got)
        for line in self.shifted(dx, dy):
            self.assertIn(line, got)
        self.assertEqual(len(props(self.v.doc[0])), 2)
        # the copy is selected, and is an added block: Edit text opens all of it
        self.assertEqual(len(self.v.obj_sel[1]), 1)
        after = canon(self.v.doc)
        self.v.undo()
        pump()
        self.assertEqual(canon(self.v.doc), before)
        self.v.redo()
        pump()
        self.assertEqual(canon(self.v.doc), after)
        self.w.set_tool("edittext")
        pump()
        wd = sorted((x for x in self.v.doc[0].get_text("words") if x[4] == "building"),
                    key=lambda x: x[1])[-1]
        self.v.edit_text_at(0, pymupdf.Point((wd[0] + wd[2]) / 2, (wd[1] + wd[3]) / 2))
        self.assertEqual(self.v._inline.text.toPlainText(), NOTE + "\nSecond paragraph")
        self.v._inline.cancel()
        pump()

    def test_paste_on_another_page_keeps_the_styles(self):
        ed = self.edit_word("building")
        cur = ed.text.textCursor()
        cur.setPosition(0)
        cur.setPosition(len("Notes:"), QTextCursor.KeepAnchor)
        ed.text.setTextCursor(cur)
        QTest.keyClick(ed.text, Qt.Key_B, Qt.ControlModifier)       # bold, in the box
        pump()
        self.finish()
        self.src = lines_of(self.v.doc[0])
        self.select_text_object("building")
        self.keys(Qt.Key_C)
        self.v.goto_page(1)
        pump()
        self.mouse_to(pymupdf.Point(150, 200), 1)
        self.keys(Qt.Key_V, 1)
        got = lines_of(self.v.doc[1])
        self.assertEqual([t for t, _o in got], [t for t, _o in self.src])
        self.assertAlmostEqual(got[0][1][0], 150, delta=1)    # at the mouse
        st = styles(self.v.doc[1])
        self.assertTrue(st["Notes:"][0])
        self.assertFalse(st["building"][0])
        self.assertEqual([p[2:] for p in props(self.v.doc[1])],
                         [p[2:] for p in props(self.v.doc[0])])    # its wrap and breaks

    def test_paste_into_another_document(self):
        self.select_text_object("building")
        self.keys(Qt.Key_C)
        other = self.blank("other.pdf", 1)
        self.w.open_file(other)
        pump()
        self.v = self.w.view()
        self.assertEqual(os.path.normcase(self.v.path), os.path.normcase(other))
        self.w.set_tool("editobjects")
        pump()
        self.mouse_to(pymupdf.Point(60, 300))
        self.keys(Qt.Key_V)
        got = lines_of(self.v.doc[0])
        self.assertEqual([t for t, _o in got], [t for t, _o in self.src])
        self.assertEqual(len(props(self.v.doc[0])), 1)
        self.v.dirty = False

    def test_cut(self):
        self.select_text_object("building")
        before = canon(self.v.doc)
        self.keys(Qt.Key_X)
        self.assertEqual(lines_of(self.v.doc[0]), [])
        self.assertEqual(added_text.markers(self.v.doc[0]), [])     # nothing left of it
        self.v.undo()
        pump()
        self.assertEqual(canon(self.v.doc), before)
        self.v.redo()
        pump()
        self.mouse_to(pymupdf.Point(100, 300), 1)
        self.keys(Qt.Key_V, 1)
        self.assertEqual([t for t, _o in lines_of(self.v.doc[1])], [t for t, _o in self.src])

    def test_duplicate(self):
        self.select_text_object("building")
        before = canon(self.v.doc)
        self.keys(Qt.Key_D)
        got = lines_of(self.v.doc[0])
        dup = self.shifted(12 / 1, 12 / 1)
        for line in dup:
            self.assertIn(line, got)
        self.assertEqual(len(props(self.v.doc[0])), 2)
        sel = self.v.obj_sel[1]
        self.assertEqual(len(sel), 1)
        self.assertAlmostEqual(sel[0]["added"].origin.x, self.src[0][1][0] + 12, delta=0.05)
        after = canon(self.v.doc)
        self.v.undo()
        pump()
        self.assertEqual(canon(self.v.doc), before)
        self.v.redo()
        pump()
        self.assertEqual(canon(self.v.doc), after)

    def test_page_text_not_added_here_copies_too(self):
        page = self.v.doc[1]
        page.insert_text((72, 300), "A label of the page", fontsize=14, color=(1, 0, 0))
        del page
        self.v._clear_caches()
        self.v.goto_page(1)
        pump()
        self.select_text_object("label", 1)
        self.keys(Qt.Key_C, 1)
        self.mouse_to(pymupdf.Point(72, 500), 1)
        self.keys(Qt.Key_V, 1)
        got = [t for t, _o in lines_of(self.v.doc[1])]
        self.assertEqual(got, ["A label of the page", "A label of the page"])
        st = styles(self.v.doc[1])
        self.assertEqual(st["label"][3], 0xFF0000)


    def test_cad_copy_copies_the_text_too(self):
        self.select_text_object("building")
        before = canon(self.v.doc)
        self.v.cad_apply("Copied", None, copies=[pymupdf.Matrix(1, 0, 0, 1, 0, 200)])
        pump()
        got = lines_of(self.v.doc[0])
        for line in self.shifted(0, 200):
            self.assertIn(line, got)
        self.assertEqual(len(props(self.v.doc[0])), 2)
        self.v.undo()
        pump()
        self.assertEqual(canon(self.v.doc), before)

    def test_text_from_another_program_goes_into_the_page(self):
        QApplication.clipboard().setText("Typed elsewhere\nsecond line")
        self.w.set_tool("editobjects")
        pump()
        self.mouse_to(pymupdf.Point(100, 500))
        self.keys(Qt.Key_V)
        got = [t for t, _o in lines_of(self.v.doc[0])]
        self.assertIn("Typed elsewhere", got)
        self.assertIn("second line", got)
        self.assertEqual([a for a in self.v.doc[0].annots()], [])      # not a text box
        self.assertEqual(len(props(self.v.doc[0])), 2)


class Fonts(unittest.TestCase):
    def test_a_font_the_other_document_lacks_comes_along(self):
        from unittest import mock
        installed = text_edit._system_fonts()
        family = next((k for k in installed if not k.startswith(("dejavu", "liberation")) and
                       k.isalpha()), None) or next(iter(installed), None)
        if family is None:
            self.skipTest("no font installed here")
        d = pymupdf.open()
        page = d.new_page()
        name = text_edit.add_text(page, (72, 100), "Words in a font", family=family, size=14)
        if not name.startswith("KZF"):
            self.skipTest("the installed font can't be embedded")
        blk = added_text.find(page, text_edit.text_lines(page))[0]
        snap = added_text.snapshot(page, blk)
        fonts = added_text.font_buffers(page, snap["keys"])
        self.assertTrue(fonts)
        own = text_edit.main_span(blk.lines[0][1])["font"]
        for buffers, same in ((None, False), (fonts, True)):
            other = pymupdf.open()
            target = other.new_page()
            with mock.patch.object(text_edit, "_system_fonts", lambda: {}):   # (elsewhere)
                got, text, keys, missing = added_text.prepare(target, snap["text"],
                                                              snap["keys"], buffers)
                added_text.write(target, (72, 300), 0, text, keys, snap["step"], None,
                                 fonts=got)
            span = text_edit.main_span(text_edit.text_lines(target)[0][1])
            self.assertEqual(span["font"] == own, same, (span["font"], own))
            self.assertEqual(bool(missing), not same)


class Redaction(Fixture):
    def test_a_redacted_word_goes_and_nothing_of_the_block_is_left(self):
        self.add(["Secret word inside a note of several words", "next line"], width=150)
        wd = [x for x in self.v.doc[0].get_text("words") if x[4] == "Secret"][0]
        mid = (wd[1] + wd[3]) / 2           # (a box over the word, not the lines around it)
        self.v.mark_redactions(0, [pymupdf.Rect(wd[0], mid - 2, wd[2], mid + 2)])
        self.v.apply_redactions(scrub=False)
        pump()
        page = self.v.doc[0]
        text = page.get_text()
        self.assertNotIn("Secret", text)
        self.assertIn("several", text)
        data = self.v.doc.tobytes(garbage=3)
        self.assertNotIn(b"KZText", data)
        self.assertEqual(added_text.markers(page), [])

    def test_redaction_elsewhere_keeps_the_block(self):
        self.add([NOTE], width=180)
        self.v.doc[0].insert_text((72, 600), "Unrelated private line", fontsize=11)
        self.v._clear_caches()
        wd = [x for x in self.v.doc[0].get_text("words") if x[4] == "private"][0]
        mid = (wd[1] + wd[3]) / 2
        self.v.mark_redactions(0, [pymupdf.Rect(wd[0], mid - 2, wd[2], mid + 2)])
        self.v.apply_redactions(scrub=False)
        pump()
        self.assertEqual(len(added_text.markers(self.v.doc[0])), 1)
        ed = self.edit_word("building")
        self.assertEqual(ed.text.toPlainText(), NOTE)
        ed.cancel()
        pump()


class Markers(unittest.TestCase):
    def test_the_marker_holds_no_text_and_nests_with_tags(self):
        d = pymupdf.open()
        page = d.new_page()
        text_edit.add_text(page, (72, 100), "Hidden words here", wrap_width=60)
        data = b"".join(d.xref_stream(x) for x in page.get_contents())
        m = re.search(rb"/KZText\s*<<([^>]*)>>", data)
        self.assertIsNotNone(m)
        self.assertNotRegex(m.group(1), rb"[A-Za-z]{3,}")       # numbers only
        # tagged inside (a structure tag's marked content) and the block's letters taken out:
        # its marker goes, the tag's sequence stays, properly nested
        x = page.get_contents()[-1]
        body = d.xref_stream(x)
        start = re.search(rb"BDC\n", body).end()
        end = body.rindex(b"EMC")
        d.update_stream(x, body[:start] + b"/P <</MCID 0>> BDC\n" + body[start:end] +
                        b"EMC\n" + body[end:])
        self.assertEqual(len(added_text.markers(page)), 1)
        lines = [ln for _r, ln in text_edit.text_lines(page)]
        text_edit.delete_lines(page, lines)
        data = page.read_contents()
        self.assertNotIn(b"KZText", data)
        self.assertIn(b"MCID", data)
        self.assertEqual(data.count(b"BDC"), data.count(b"EMC"))
        page.clean_contents()                    # (and MuPDF reads it as valid)
        self.assertEqual(page.get_text().strip(), "")

    def test_strings_inside_do_not_confuse_the_reader(self):
        d = pymupdf.open()
        page = d.new_page()
        x = d.get_new_xref()
        d.update_object(x, "<<>>")
        d.update_stream(x, b"/KZText <</O [72 100] /R 0 /W 0 /S 14.4 /Y [0] /H []>> BDC "
                           b"BT /F1 12 Tf 72 692 Td (a \\) EMC \\( (nested) BDC) Tj ET EMC")
        d.xref_set_key(page.xref, "Contents", "%d 0 R" % x)
        found = added_text.markers(page)
        self.assertEqual(len(found), 1)
        self.assertTrue(found[0]["draws"])
        self.assertEqual(d.xref_stream(x)[found[0]["emc"][0]:found[0]["emc"][1]], b"EMC")
        self.assertEqual(found[0]["emc"][1], len(d.xref_stream(x)))


if __name__ == "__main__":
    unittest.main()
