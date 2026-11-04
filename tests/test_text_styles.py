"""Edit text and Add text keep each word's style: font, size, bold, italic, color, underline
and strikethrough survive an edit and the paragraph's reflow; the editor's style buttons and
Ctrl+B / Ctrl+I / Ctrl+U style the selected words; bold and italic keep the line's font (its
real bold / italic when the PDF or the computer has it, else the same font thickened or
slanted); underlines are drawn on the page and read back as the run's.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_text_styles
"""
import os
import re
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402
from PySide6.QtCore import Qt, QEvent  # noqa: E402
from PySide6.QtGui import QColor, QKeyEvent, QTextCursor  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import text_edit, text_styles  # noqa: E402
from kanzonas.document_view import DocumentView  # noqa: E402

WORDS = ("The contractor shall verify all dimensions in the field before ordering materials "
         "and report any discrepancies to the architect in writing within two days of the "
         "start of the work on the site.").split()
RED = (1, 0, 0)


def _embedded_name(code):
    """The name the page's text gives a built-in font's outlines once embedded."""
    d = pymupdf.open()
    p = d.new_page()
    p.insert_font(fontname="F", fontbuffer=pymupdf.Font(code).buffer)
    p.insert_text((50, 50), "x", fontname="F")
    return p.get_text("dict")["blocks"][0]["lines"][0]["spans"][0]["font"]


# Helvetica's outlines as MuPDF has them built in, embedded ("NimbusSans-Regular")
REG = _embedded_name("helv")
BOLD = _embedded_name("hebo")


def write_words(page, words, styles=None, under=(), x0=72, y0=100, right=320, size=11,
                fontname="helv", stroked_under=()):
    """Write words wrapped between x0 and right, word by word; styles: {word: (fontname,
    color)}; under: words underlined with a thin filled bar (as Word's PDF export writes
    them), stroked_under: with a stroked line. Returns the baselines."""
    styles = styles or {}
    x, y = x0, y0
    bases = [y]
    sh = page.new_shape()
    for w in words:
        font, color = styles.get(w, (fontname, (0, 0, 0)))
        wd = pymupdf.get_text_length(w + " ", fontname=font, fontsize=size) \
            if font in ("helv", "hebo", "heit", "tiro") else \
            pymupdf.Font(fontbuffer=pymupdf.Font("helv").buffer).text_length(w + " ", size)
        if x + wd > right:
            x, y = x0, y + size * 1.2
            bases.append(y)
        sh.insert_text((x, y), w + " ", fontname=font, fontsize=size, color=color)
        u = wd - (wd / (len(w) + 1))
        if w in under:
            sh.draw_rect(pymupdf.Rect(x, y + 0.1 * size, x + u, y + 0.15 * size))
            sh.finish(color=None, fill=(0, 0, 0), width=0)
        if w in stroked_under:
            sh.draw_line((x, y + 0.12 * size), (x + u, y + 0.12 * size))
            sh.finish(color=(0, 0, 0), width=0.5)
        x += wd
    sh.commit()
    return bases


def word_styles(page):
    """{word: Style of its first letter} for the page's text, as Edit text reads it."""
    out = {}
    for _r, ln in text_edit.text_lines(page):
        st = text_styles.read_line(page, ln)
        for m in re.finditer(r"\S+", st.text):
            out.setdefault(m.group().strip(".,"), st.keys[m.start()])
    return out


def open_view(doc, test):
    path = os.path.join(tempfile.mkdtemp(), "styles.pdf")
    doc.save(path)
    v = DocumentView(path)
    v.resize(900, 1100)
    v.show()
    APP.processEvents()
    v.tool = "edittext"
    test.addCleanup(v.close_doc)
    return v


def select(ed, word, start=0):
    """Select word in the editor."""
    t = ed.text.toPlainText()
    i = t.index(word, start)
    cur = ed.text.textCursor()
    cur.setPosition(i)
    cur.setPosition(i + len(word), QTextCursor.KeepAnchor)
    ed.text.setTextCursor(cur)


def cursor_at(ed, pos):
    cur = ed.text.textCursor()
    cur.setPosition(pos)
    ed.text.setTextCursor(cur)


def drawn_bars(page):
    """The thin filled or stroked horizontal pieces drawn on the page: [Rect]."""
    out = []
    for d in page.get_drawings():
        r = d["rect"]
        if r.height < 2 and r.width > 3:
            out.append(r)
    return out


class Fixture(unittest.TestCase):
    def para_view(self, styles=None, under=(), stroked_under=(), words=WORDS, extra=None):
        d = pymupdf.open()
        p = d.new_page()
        self.bases = write_words(p, words, styles, under, stroked_under=stroked_under)
        if extra:
            extra(p)
        return open_view(d, self)

    def open_paragraph(self, v, y=None):
        y = self.bases[0] - 3 if y is None else y
        v.edit_text_at(0, pymupdf.Point(100, y))
        ed = v._inline
        self.assertIsNotNone(ed)
        return ed


class KeepsStyles(Fixture):
    def test_bold_and_red_words_survive_an_edit_elsewhere(self):
        # the paragraph's bold word and red word, edited elsewhere: both stay so
        v = self.para_view({"verify": ("hebo", (0, 0, 0)), "architect": ("helv", RED)})
        ed = self.open_paragraph(v)
        self.assertTrue(ed.text.toPlainText().startswith("The contractor shall verify"))
        cursor_at(ed, len("The "))
        QTest.keyClicks(ed.text, "general ")
        ed.commit()
        page = v.doc[0]
        text = " ".join(page.get_text().split())
        self.assertTrue(text.startswith("The general contractor shall verify"), text)
        ws = word_styles(page)
        self.assertEqual(ws["verify"].font, "Helvetica-Bold")
        self.assertTrue(ws["verify"].bold)
        self.assertEqual(ws["architect"].color, 0xFF0000)
        self.assertFalse(ws["general"].bold)
        self.assertEqual(ws["general"].color, 0)
        self.assertEqual(ws["contractor"].font, "Helvetica")
        # Find and text selection find the new words
        self.assertTrue(page.search_for("general contractor"))
        v.undo()                                    # one Ctrl+Z restores it
        self.assertTrue(" ".join(v.doc[0].get_text().split()).startswith(
            "The contractor shall verify"))
        self.assertEqual(word_styles(v.doc[0])["verify"].font, "Helvetica-Bold")

    def test_text_typed_without_the_editor_keeps_the_words_styles(self):
        # (Replace-style edits: the committed text maps onto the words read)
        v = self.para_view({"verify": ("hebo", (0, 0, 0)), "architect": ("helv", RED)})
        ed = self.open_paragraph(v)
        new = ed.text.toPlainText().replace("verify", "verifying").replace(
            "architect", "architect and engineer")
        ed.committed.emit(new, 0, 0, None)
        ws = word_styles(v.doc[0])
        self.assertTrue(ws["verifying"].bold)        # typed next to a bold word: bold
        self.assertEqual(ws["engineer"].color, 0xFF0000)

    def test_typing_next_to_a_bold_word_is_bold(self):
        v = self.para_view({"verify": ("hebo", (0, 0, 0))})
        ed = self.open_paragraph(v)
        t = ed.text.toPlainText()
        cursor_at(ed, t.index("verify") + len("verify"))
        QTest.keyClicks(ed.text, "ing")
        ed.commit()
        ws = word_styles(v.doc[0])
        self.assertEqual(ws["verifying"].font, "Helvetica-Bold")
        self.assertFalse(ws["all"].bold)

    def test_typing_into_an_empty_box_takes_the_main_style(self):
        v = self.para_view({"The": ("hebo", (0, 0, 0))})
        ed = self.open_paragraph(v)
        ed.text.selectAll()
        QTest.keyClick(ed.text, Qt.Key_Delete)
        QTest.keyClicks(ed.text, "A new sentence written in place of the old paragraph text "
                                 "here, long enough to wrap onto two or more lines of it.")
        ed.commit()
        ws = word_styles(v.doc[0])
        self.assertEqual(ws["A"].font, "Helvetica")          # not the bold first word's
        self.assertFalse(ws["new"].bold)


class Buttons(Fixture):
    def test_buttons_and_shortcuts_style_the_selection(self):
        v = self.para_view()
        ed = self.open_paragraph(v)
        self.assertIsNotNone(ed.bar)
        tips = {k: b.toolTip() for k, b in ed.bar.buttons.items()}
        self.assertEqual(tips["bold"], "Bold (Ctrl+B)")
        self.assertEqual(tips["italic"], "Italic (Ctrl+I)")
        self.assertEqual(tips["underline"], "Underline (Ctrl+U)")
        self.assertEqual(tips["strike"], "Strikethrough")
        select(ed, "contractor")
        ed.bar.buttons["bold"].click()
        select(ed, "dimensions")
        QTest.keyClick(ed.text, Qt.Key_I, Qt.ControlModifier)
        select(ed, "field")
        QTest.keyClick(ed.text, Qt.Key_U, Qt.ControlModifier)
        select(ed, "materials")
        ed.bar.buttons["strike"].click()
        select(ed, "report")
        QTest.keyClick(ed.text, Qt.Key_B, Qt.ControlModifier)
        select(ed, "site")
        ed.set_color(QColor(0, 0, 255))
        select(ed, "discrepancies")
        ed.bar.buttons["larger"].click()
        ed.bar.buttons["larger"].click()
        # the editor shows them
        st = ed.styled_runs()
        by = {t.strip(): k for t, k in st if t.strip()}
        self.assertTrue(by["contractor"].bold)
        self.assertTrue(by["dimensions"].italic)
        self.assertTrue(by["field"].underline)
        self.assertTrue(by["materials"].strike)
        self.assertEqual(by["discrepancies"].size, 13.0)
        ed.commit()
        page = v.doc[0]
        ws = word_styles(page)
        self.assertEqual(ws["contractor"].font, "Helvetica-Bold")   # Helvetica's own bold
        self.assertEqual(ws["report"].font, "Helvetica-Bold")
        self.assertEqual(ws["dimensions"].font, "Helvetica-Oblique")
        self.assertTrue(ws["field"].underline)
        self.assertFalse(ws["before"].underline)
        self.assertTrue(ws["materials"].strike)
        self.assertFalse(ws["and"].strike)
        self.assertEqual(ws["site"].color, 0x0000FF)
        self.assertAlmostEqual(ws["discrepancies"].size, 13.0, delta=0.05)
        self.assertAlmostEqual(ws["the"].size, 11.0, delta=0.05)
        self.assertEqual(len(drawn_bars(page)), 2)                  # an underline, a strike
        # toggling again takes the style off
        v.edit_text_at(0, pymupdf.Point(100, self.bases[0] - 3))
        ed = v._inline
        select(ed, "contractor")
        QTest.keyClick(ed.text, Qt.Key_B, Qt.ControlModifier)
        select(ed, "field")
        ed.bar.buttons["underline"].click()
        ed.commit()
        ws = word_styles(v.doc[0])
        self.assertEqual(ws["contractor"].font, "Helvetica")
        self.assertFalse(ws["field"].underline)
        self.assertTrue(ws["materials"].strike)
        self.assertEqual(len(drawn_bars(v.doc[0])), 1)              # the old underline went

    def test_shortcuts_win_over_the_windows_own(self):
        v = self.para_view()
        ed = self.open_paragraph(v)
        for key in (Qt.Key_B, Qt.Key_I, Qt.Key_U, Qt.Key_BracketRight, Qt.Key_BracketLeft):
            e = QKeyEvent(QEvent.ShortcutOverride, key, Qt.ControlModifier)
            QApplication.sendEvent(ed.text, e)
            self.assertTrue(e.isAccepted(), key)
        ed.cancel()

    def test_add_text_styles_words(self):
        d = pymupdf.open()
        d.new_page()
        v = open_view(d, self)
        v.tool = "addtext"
        v.add_text_at(0, pymupdf.Point(72, 200))
        ed = v._inline
        self.assertIsNotNone(ed.bar)
        QTest.keyClicks(ed.text, "Plain words and bold words")
        select(ed, "bold")
        QTest.keyClick(ed.text, Qt.Key_B, Qt.ControlModifier)
        select(ed, "Plain")
        QTest.keyClick(ed.text, Qt.Key_U, Qt.ControlModifier)
        ed.commit()
        page = v.doc[0]
        self.assertTrue(page.search_for("Plain words and bold words"))
        ws = word_styles(page)
        self.assertEqual(ws["bold"].font, "Helvetica-Bold")
        self.assertEqual(ws["words"].font, "Helvetica")
        self.assertTrue(ws["Plain"].underline)
        self.assertEqual(len(drawn_bars(page)), 1)


def embedded_doc(variants=("helv",), words=WORDS, rotate=None):
    """A page whose text is in an embedded font (REG: Helvetica's own outlines embedded);
    variants: the built-in fonts embedded too ("hebo": its bold, on a line of its own)."""
    d = pymupdf.open()
    p = d.new_page()
    p.insert_font(fontname="EmbReg", fontbuffer=pymupdf.Font("helv").buffer)
    if "hebo" in variants:
        p.insert_font(fontname="EmbBold", fontbuffer=pymupdf.Font("hebo").buffer)
        p.insert_text((72, 700), "Bold note", fontname="EmbBold", fontsize=11)
    if rotate is not None:
        p.insert_text((300, 500), " ".join(words), fontname="EmbReg", fontsize=14,
                      rotate=rotate)
        return d, None
    font = pymupdf.Font(fontbuffer=pymupdf.Font("helv").buffer)
    x, y, bases = 72, 100, [100]
    line = []
    for w in words:
        trial = " ".join(line + [w])
        if font.text_length(trial, 11) > 250:
            p.insert_text((x, y), " ".join(line) + " ", fontname="EmbReg", fontsize=11)
            y += 13.2
            bases.append(y)
            line = [w]
        else:
            line.append(w)
    p.insert_text((x, y), " ".join(line), fontname="EmbReg", fontsize=11)
    return d, bases


class SameFont(Fixture):
    def test_real_bold_variant_embedded_in_the_pdf(self):
        d, self.bases = embedded_doc(("helv", "hebo"))
        v = open_view(d, self)
        with mock.patch.object(text_edit, "_system_fonts", lambda: {}):
            ed = self.open_paragraph(v)
            select(ed, "contractor")
            QTest.keyClick(ed.text, Qt.Key_B, Qt.ControlModifier)
            ed.commit()
        page = v.doc[0]
        ws = word_styles(page)
        self.assertEqual(ws["contractor"].font, BOLD)    # the PDF's own bold
        self.assertEqual(ws["shall"].font, REG)
        self.assertNotIn(b" Tr", page.read_contents())               # not thickened

    def test_real_bold_variant_installed(self):
        d, self.bases = embedded_doc(("helv",))
        folder = tempfile.mkdtemp()
        path = os.path.join(folder, "bold.cff")
        with open(path, "wb") as f:
            f.write(pymupdf.Font("hebo").buffer)
        v = open_view(d, self)
        key = text_styles.family_key(REG) + "bold"            # (nimbussansbold)
        with mock.patch.object(text_edit, "_system_fonts", lambda: {key: path}):
            ed = self.open_paragraph(v)
            select(ed, "contractor")
            ed.bar.buttons["bold"].click()
            ed.commit()
        ws = word_styles(v.doc[0])
        self.assertEqual(ws["contractor"].font, BOLD)
        self.assertNotIn(b" Tr", v.doc[0].read_contents())

    def test_synthetic_bold_and_italic_keep_the_font(self):
        # no bold or italic of the font anywhere: the same font, thickened and slanted
        d, self.bases = embedded_doc(("helv",))
        v = open_view(d, self)
        with mock.patch.object(text_edit, "_system_fonts", lambda: {}):
            ed = self.open_paragraph(v)
            select(ed, "contractor")
            QTest.keyClick(ed.text, Qt.Key_B, Qt.ControlModifier)
            select(ed, "dimensions")
            QTest.keyClick(ed.text, Qt.Key_I, Qt.ControlModifier)
            select(ed, "materials")
            QTest.keyClick(ed.text, Qt.Key_B, Qt.ControlModifier)
            QTest.keyClick(ed.text, Qt.Key_I, Qt.ControlModifier)
            ed.commit()
            page = v.doc[0]
            names = {f[3] for f in page.get_fonts()}
            self.assertEqual(len(names), 1, names)               # the one font, no other
            self.assertIn(b"2 Tr", page.read_contents())         # thickened
            ws = word_styles(page)
            self.assertTrue(ws["contractor"].bold and not ws["contractor"].italic)
            self.assertTrue(ws["dimensions"].italic and not ws["dimensions"].bold)
            self.assertTrue(ws["materials"].bold and ws["materials"].italic)
            self.assertFalse(ws["shall"].bold or ws["shall"].italic)
            self.assertEqual({ws[w].font for w in ("contractor", "dimensions", "shall")},
                             {REG})
            # read back as bold / italic, they stay so through the next edit
            ed = self.open_paragraph(v)
            cursor_at(ed, 0)
            QTest.keyClicks(ed.text, "Note: ")
            ed.commit()
            ws = word_styles(v.doc[0])
            self.assertTrue(ws["contractor"].bold)
            self.assertTrue(ws["dimensions"].italic)
            self.assertTrue(ws["materials"].bold and ws["materials"].italic)
            self.assertFalse(ws["Note:"].bold)

    def test_only_a_word_the_font_cant_write_goes_to_another_font(self):
        d, self.bases = embedded_doc(("helv",))
        v = open_view(d, self)
        with mock.patch.object(text_edit, "_system_fonts", lambda: {}):
            ed = self.open_paragraph(v)
            select(ed, "contractor")
            QTest.keyClick(ed.text, Qt.Key_B, Qt.ControlModifier)
            cursor_at(ed, len(ed.text.toPlainText()))
            ed.text.insertPlainText(" \u4e2d\u6587 end")    # (typed: the style there)
            ed.commit()
        page = v.doc[0]
        self.assertTrue(page.search_for("site. \u4e2d\u6587 end"))
        ws = word_styles(page)
        self.assertNotEqual(ws["\u4e2d\u6587"].font, REG)      # (a font that has them)
        self.assertEqual(ws["site"].font, REG)                 # the rest keeps its font
        self.assertEqual(ws["end"].font, REG)
        self.assertTrue(ws["contractor"].bold)

    def test_rotated_text_keeps_its_styles_and_direction(self):
        d, _b = embedded_doc(("helv",), words="Sideways words on a drawing".split(),
                             rotate=90)
        v = open_view(d, self)
        r = v.doc[0].search_for("words on")[0]
        with mock.patch.object(text_edit, "_system_fonts", lambda: {}):
            v.edit_text_at(0, (r.tl + r.br) / 2)
            ed = v._inline
            self.assertIsNotNone(ed)
            select(ed, "drawing")
            QTest.keyClick(ed.text, Qt.Key_I, Qt.ControlModifier)
            QTest.keyClick(ed.text, Qt.Key_U, Qt.ControlModifier)
            ed.commit()
            page = v.doc[0]
            self.assertTrue(page.search_for("Sideways words on a drawing"))
            lines = [ln for _r, ln in text_edit.text_lines(page)
                     if "Sideways" in text_edit.line_text(ln)]
            self.assertEqual(len(lines), 1)
            self.assertEqual(tuple(round(c) for c in lines[0]["dir"]), (0, -1))
            st = text_styles.read_line(page, lines[0])
            k = st.keys[st.text.index("drawing")]
            self.assertTrue(k.italic and k.underline)
            self.assertEqual(k.font, REG)
            self.assertFalse(st.keys[0].italic or st.keys[0].underline)
            bars = drawn_bars(page) + [dr["rect"] for dr in page.get_drawings()
                                       if dr["rect"].width < 2 and dr["rect"].height > 3]
            self.assertEqual(len(bars), 1)
            self.assertLess(bars[0].width, 2)                    # turned with the text


class OneLine(Fixture):
    def test_alt_click_keeps_the_lines_styles(self):
        v = self.para_view({"verify": ("hebo", (0, 0, 0))}, under=("all",))
        v.edit_text_at(0, pymupdf.Point(100, self.bases[0] - 3), one_line=True)
        ed = v._inline
        self.assertIsNotNone(ed.bar)
        self.assertNotIn("field", ed.text.toPlainText())         # just the line
        cursor_at(ed, 0)
        QTest.keyClicks(ed.text, "Note: ")
        select(ed, "contractor")
        QTest.keyClick(ed.text, Qt.Key_I, Qt.ControlModifier)
        ed.commit()
        ws = word_styles(v.doc[0])
        self.assertEqual(ws["verify"].font, "Helvetica-Bold")
        self.assertEqual(ws["contractor"].font, "Helvetica-Oblique")
        self.assertTrue(ws["all"].underline)
        self.assertFalse(ws["Note:"].bold or ws["Note:"].underline)
        self.assertEqual(len(drawn_bars(v.doc[0])), 1)

    def test_a_dragged_line_keeps_its_styles_and_underline(self):
        v = self.para_view({"verify": ("hebo", (0, 0, 0)), "contractor": ("helv", RED)},
                           under=("all",))
        before = drawn_bars(v.doc[0])
        v.move_text_line(0, pymupdf.Point(100, self.bases[0] - 3), (0, 300))
        page = v.doc[0]
        ws = word_styles(page)
        self.assertEqual(ws["verify"].font, "Helvetica-Bold")
        self.assertEqual(ws["contractor"].color, 0xFF0000)
        self.assertTrue(ws["all"].underline)
        after = drawn_bars(page)
        self.assertEqual(len(after), 1)
        self.assertAlmostEqual(after[0].y0, before[0].y0 + 300, delta=0.6)
        self.assertGreater(page.search_for("verify")[0].y0, 300)


class Underlines(Fixture):
    def test_word_style_underline_is_read_and_moves_with_its_word(self):
        v = self.para_view(under=("field",), stroked_under=("writing",))
        page = v.doc[0]
        ws = word_styles(page)
        self.assertTrue(ws["field"].underline)
        self.assertTrue(ws["writing"].underline)
        self.assertFalse(ws["the"].underline)
        before = [r for r in drawn_bars(page)]
        self.assertEqual(len(before), 2)
        ed = self.open_paragraph(v)
        cursor_at(ed, 0)
        QTest.keyClicks(ed.text, "Before any work starts on the site, ")
        ed.commit()
        page = v.doc[0]
        ws = word_styles(page)
        self.assertTrue(ws["field"].underline)
        self.assertTrue(ws["writing"].underline)
        self.assertFalse(ws["Before"].underline)
        after = drawn_bars(page)
        self.assertEqual(len(after), 2)                       # moved, none left behind
        self.assertFalse(any(abs(a.x0 - b.x0) < 0.5 and abs(a.y0 - b.y0) < 0.5
                             for a in after for b in before))
        field = page.search_for("field")[0]
        self.assertTrue(any(abs(a.x0 - field.x0) < 1 and abs(a.x1 - field.x1) < 1.5 and
                            0 < a.y0 - field.y1 + 3 < 4 for a in after), (after, field))
        v.undo()
        self.assertEqual(len(drawn_bars(v.doc[0])), 2)

    def test_underlined_word_wrapping_onto_the_next_line_is_split(self):
        v = self.para_view()
        ed = self.open_paragraph(v)
        select(ed, "verify all dimensions in the field before ordering materials")
        QTest.keyClick(ed.text, Qt.Key_U, Qt.ControlModifier)
        cursor_at(ed, 0)
        QTest.keyClicks(ed.text, "Before any work starts, ")
        ed.commit()
        page = v.doc[0]
        ws = word_styles(page)
        for w in ("verify", "all", "dimensions", "field", "ordering", "materials"):
            self.assertTrue(ws[w].underline, w)
        bases = sorted({round(ln["spans"][0]["origin"][1], 1)
                        for _r, ln in text_edit.text_lines(page)
                        if any(w in text_edit.line_text(ln) for w in ("verify", "materials"))})
        bars = drawn_bars(page)
        self.assertEqual(len(bars), len(bases))               # one bar per line piece
        self.assertGreater(len(bars), 1)

    def test_table_border_and_long_rule_are_not_underlines(self):
        def border(p):
            # a table cell around the paragraph: its bottom border just under the last line
            p.draw_rect(pymupdf.Rect(66, 86, 330, self.bases[-1] + 3), width=0.5)
            # a rule under the first line, longer than its text
            p.draw_line((60, self.bases[0] + 1.5), (340, self.bases[0] + 1.5), width=0.5)
            # a line under "field" running on into the next word
            x = p.search_for("field")[0]
            p.draw_line((x.x0, x.y1 - 1.5), (x.x1 + 6, x.y1 - 1.5), width=0.5)
        d = pymupdf.open()
        p = d.new_page()
        self.bases = write_words(p, WORDS)
        border(p)
        v = open_view(d, self)
        page = v.doc[0]
        drawings = len(page.get_drawings())
        lines = text_edit.paragraph_at(text_edit.text_lines(page),
                                       text_edit.text_lines(page)[0][1])
        st = text_styles.read_paragraph(page, lines)
        self.assertFalse(any(k.underline or k.strike for k in st.keys))
        self.assertEqual(st.decor, [])
        ed = self.open_paragraph(v)
        select(ed, "verify")
        QTest.keyClick(ed.text, Qt.Key_B, Qt.ControlModifier)
        ed.commit()
        self.assertEqual(len(v.doc[0].get_drawings()), drawings)    # all still there
        self.assertTrue(word_styles(v.doc[0])["verify"].bold)


class Alignment(Fixture):
    def rows(self, page):
        out = []
        for _box, blk in text_edit.text_blocks(text_edit.text_lines(page)):
            for r, ln in blk:
                out.append((r.x0, r.x1, ln["spans"][0]["origin"][1]))
        return sorted(out, key=lambda t: t[2])

    def view(self, align):
        d = pymupdf.open()
        p = d.new_page()
        p.insert_textbox(pymupdf.Rect(72, 72, 320, 300), " ".join(WORDS + WORDS),
                         fontsize=11, fontname="helv", align=align)
        return open_view(d, self)

    def test_justified_and_centered_keep_their_alignment(self):
        v = self.view(pymupdf.TEXT_ALIGN_JUSTIFY)
        first = self.rows(v.doc[0])
        v.edit_text_at(0, pymupdf.Point(100, first[0][2] - 3))
        ed = v._inline
        select(ed, "verify")
        QTest.keyClick(ed.text, Qt.Key_B, Qt.ControlModifier)
        select(ed, "architect")
        ed.set_color(QColor(255, 0, 0))
        ed.commit()
        after = self.rows(v.doc[0])
        right = max(r[1] for r in after)
        self.assertTrue(all(abs(r[1] - right) < 1.5 for r in after[:-1]), after)
        self.assertLess(after[-1][1], right - 3)
        ws = word_styles(v.doc[0])
        self.assertTrue(ws["verify"].bold)
        self.assertEqual(ws["architect"].color, 0xFF0000)
        v = self.view(pymupdf.TEXT_ALIGN_CENTER)
        first = self.rows(v.doc[0])
        v.edit_text_at(0, pymupdf.Point(196, first[0][2] - 3))
        ed = v._inline
        select(ed, "verify")
        QTest.keyClick(ed.text, Qt.Key_B, Qt.ControlModifier)
        ed.commit()
        mids = [(r[0] + r[1]) / 2 for r in self.rows(v.doc[0])]
        self.assertLess(max(mids) - min(mids), 1.5)
        self.assertTrue(word_styles(v.doc[0])["verify"].bold)


class Pieces(unittest.TestCase):
    def test_restyle_maps_kept_and_typed_letters(self):
        a, b = text_styles.Style(size=10), text_styles.Style(size=10, bold=True)
        old = "one two three"
        keys = [a] * 4 + [b] * 3 + [a] * 6
        new = "one twos three!"
        got = text_styles.restyle(old, keys, new, a)
        self.assertEqual(got[4:8], [b] * 4)          # "twos": typed after a bold letter
        self.assertEqual(got[-1], a)
        self.assertEqual(text_styles.restyle("", [], "new", b), [b] * 3)

    def test_family_key_and_natural_style(self):
        self.assertEqual(text_styles.family_key("ABCDEF+Arial-BoldItalicMT"), "arial")
        self.assertEqual(text_styles.family_key("TimesNewRomanPS-BoldMT"), "timesnewroman")
        self.assertEqual(text_styles.family_key("Calibri"), "calibri")
        self.assertEqual(text_styles.natural("Arial-BoldMT"), (True, False))
        self.assertEqual(text_styles.natural("Arial,Italic"), (False, True))
        self.assertEqual(text_styles.natural("ArialMT", 16), (True, False))

    def test_underline_metrics_from_the_font(self):
        fonts = text_edit._system_fonts()
        path = fonts.get("dejavusans") or fonts.get("arial") or fonts.get("liberationsans")
        if not path:
            self.skipTest("no TrueType font to read")
        f = text_styles.Font("x", pymupdf.Font(fontfile=path), {"fontfile": path}, False,
                             False)
        under, thick, strike = text_styles.deco_metrics(f)
        self.assertTrue(0.08 <= under <= 0.2 and 0.045 <= thick <= 0.08 and
                        0.15 <= strike <= 0.4, (under, thick, strike))


if __name__ == "__main__":
    unittest.main()
