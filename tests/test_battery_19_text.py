"""Break-it tests for 1.9's text work: Edit text keeping each word's style (bold, italic,
underline, strikethrough, color and size for selected words), Save as PDF/A and Check PDF/A,
and Find on edited text. Each test is a sequence that went wrong once.

What the battery found:
- Every paragraph edit pushed a word down: the paragraph's own width is its longest line's,
  as the page measures it (in the PDF's glyph widths, rounded), and the font measures the
  same words a little wider, so that line no longer fit. A paragraph got narrower and longer
  with each edit, even an edit to its last word, and lines nobody touched rewrapped.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_battery_19_text
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402
from PySide6.QtGui import QTextCursor  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import text_edit, text_styles  # noqa: E402
from kanzonas.document_view import DocumentView  # noqa: E402

WORDS = ("The contractor shall verify all dimensions in the field before ordering materials "
         "and report any discrepancies to the architect in writing within two days of the "
         "start of the work on the site and keep the records").split()


def embedded_paragraph(page, words=WORDS, code="tiro", width=250, x=72, y=100, size=11,
                       styles=None):
    """words wrapped to width in an embedded copy of a built-in font (code); styles:
    {word: fontname of another font inserted, or a color}. Returns the baselines."""
    page.insert_font(fontname="R", fontbuffer=pymupdf.Font(code).buffer)
    font = pymupdf.Font(fontbuffer=pymupdf.Font(code).buffer)
    line, bases = [], [y]
    rows = []
    for w in words:
        if line and font.text_length(" ".join(line + [w]), size) > width:
            rows.append(line)
            line = [w]
        else:
            line.append(w)
    rows.append(line)
    for i, row in enumerate(rows):
        page.insert_text((x, y), " ".join(row) + (" " if i < len(rows) - 1 else ""),
                         fontname="R", fontsize=size)
        if i < len(rows) - 1:
            y += size * 1.2
            bases.append(y)
    return bases


def narrow_widths(doc, by=1):
    """The fonts' glyph widths in the PDF made `by` thousandths of the size narrower than
    the font program's, as producers rounding them down write them (Word: a 2048-unit
    TrueType font's widths in whole thousandths)."""
    for xref in range(1, doc.xref_length()):
        if doc.xref_get_key(xref, "Subtype")[1] not in ("/CIDFontType0", "/CIDFontType2"):
            continue
        kind, val = doc.xref_get_key(xref, "W")
        wx = int(val.split()[0]) if kind == "xref" else None
        src = doc.xref_object(wx) if wx else val
        out, outside, depth = [], [], 0
        for tok in src.replace("[", " [ ").replace("]", " ] ").split():
            if tok == "[":
                depth += 1
                outside = []
            elif tok == "]":
                depth -= 1
            elif depth == 2 or (depth == 1 and len(outside) == 2):
                tok = str(max(1, int(float(tok)) - by))
                outside = []
            elif depth == 1:
                outside.append(tok)
            out.append(tok)
        new = " ".join(out)
        if wx:
            doc.update_object(wx, new)
        else:
            doc.xref_set_key(xref, "W", new)


def open_view(doc, test, tool="edittext"):
    path = os.path.join(tempfile.mkdtemp(), "battery19.pdf")
    doc.save(path)
    v = DocumentView(path)
    v.resize(900, 1100)
    v.show()
    APP.processEvents()
    v.tool = tool
    test.addCleanup(lambda: v.doc.is_closed or v.close_doc())
    return v


def page_lines(page):
    return [text_edit.line_text(ln).strip() for _r, ln in text_edit.text_lines(page)]


def select(ed, word, start=0):
    t = ed.text.toPlainText()
    i = t.index(word, start)
    cur = ed.text.textCursor()
    cur.setPosition(i)
    cur.setPosition(i + len(word), QTextCursor.KeepAnchor)
    ed.text.setTextCursor(cur)


class Paragraphs(unittest.TestCase):
    def test_editing_a_paragraph_keeps_its_lines(self):
        # a word typed at the end of the last line: the lines above stay as they were, edit
        # after edit (they rewrapped, the paragraph narrowing each time); also with a word
        # made bold in the editor (the styled writing)
        for styled in (False, True):
            with self.subTest(styled=styled):
                d = pymupdf.open()
                bases = embedded_paragraph(d.new_page())
                narrow_widths(d)
                v = open_view(d, self)
                before = page_lines(v.doc[0])
                self.assertEqual(len(before), 4)
                for n in range(1, 4):
                    v.edit_text_at(0, pymupdf.Point(100, bases[0] - 3))
                    ed = v._inline
                    if styled and n == 1:
                        select(ed, "architect")
                        ed.toggle("bold")
                    ed.text.moveCursor(QTextCursor.End)
                    ed.text.insertPlainText("!")
                    ed.commit()
                    now = page_lines(v.doc[0])
                    self.assertEqual(now[:3], before[:3], n)
                    self.assertEqual(now[3], before[3] + "!" * n)
                if styled:
                    ws = {}
                    for _r, ln in text_edit.text_lines(v.doc[0]):
                        st = text_styles.read_line(v.doc[0], ln)
                        for i, w in enumerate(st.text.split(" ")):
                            ws.setdefault(w, st.keys[st.text.index(w)])
                    self.assertTrue(ws["architect"].bold)
                    self.assertFalse(ws["the"].bold)


if __name__ == "__main__":
    unittest.main()
