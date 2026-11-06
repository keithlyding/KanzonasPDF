"""Break-it tests for 1.9's text work: Edit text keeping each word's style (bold, italic,
underline, strikethrough, color and size for selected words), Save as PDF/A and Check PDF/A,
and Find on edited text. Each test is a sequence that went wrong once.

What the battery found:
- Every paragraph edit pushed a word down: the paragraph's own width is its longest line's,
  as the page measures it (in the PDF's glyph widths, rounded), and the font measures the
  same words a little wider, so that line no longer fit. A paragraph got narrower and longer
  with each edit, even an edit to its last word, and lines nobody touched rewrapped.
- Hebrew and Arabic were rewritten backwards: a page's letters are written left to right,
  unshaped, from the line's first letter in reading order (its right end), so a right-to-left
  line edited (a word made bold), dragged, replaced in or moved with a drawing came out in
  the wrong order and ran off the page's edge. Edit text, moving, Replace text and Add text
  now refuse such text and say why, changing nothing.
- Words made larger (Larger text) ran into the line above: the lines stayed the paragraph's
  line spacing apart whatever the size of their words (a word made 20 points larger in 11
  point text was written over the line above it, and read back as part of it). A line with
  larger words now sits lower, as far as they need.
- A hidden word showed: a word inside a line drawn invisibly (render mode 3, as OCR layers
  are; or at no opacity) was written again in ink when anything in its paragraph was edited,
  when its line was dragged, when Replace text changed the line, or when the line was moved
  with a drawing; a word in white was written in the line's color when the line was moved
  with a drawing or changed by Replace text (each word kept only its line's main style
  there). Each word now keeps its opacity, and lines with words in styles of their own keep
  them when moved with a drawing or changed by Replace text.
- Save as PDF/A said a copy was PDF/A when it wasn't: pictures written into a page's content
  (inline images, BI ... ID ... EI) were never looked at, and one compressed with LZW or set
  to be smoothed stayed so (veraPDF: 6.1.10-1, 6.2.8-3), with Check PDF/A finding nothing.
  They are now checked, and Save as PDF/A writes them again (decoded, compressed with Flate,
  not smoothed), drawing exactly as before.
- Find counted a word twice when part of it had been made larger or smaller (MuPDF gives each
  size its own rect, and each rect counted as a match): "contractor" with "actor" made larger
  was 2 matches, "The contractor shall" 3. Rects that go on from one another along a line are
  one match.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_battery_19_text
"""
import base64
import os
import sys
import tempfile
import unittest
import zlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402
from unittest import mock  # noqa: E402

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


    def test_larger_words_get_the_room_they_need(self):
        def letters(page):
            """[(baseline, top of the letters, bottom)] of each line, top to bottom."""
            out = []
            for _r, ln in text_edit.text_lines(page):
                spans = ln["spans"]
                top = min(s["origin"][1] - s["ascender"] * s["size"] for s in spans)
                bot = max(s["origin"][1] - s["descender"] * s["size"] for s in spans)
                out.append((spans[0]["origin"][1], top, bot))
            return sorted(out)
        # a paragraph's word made larger
        d = pymupdf.open()
        bases = embedded_paragraph(d.new_page(), code="helv")
        v = open_view(d, self)
        v.edit_text_at(0, pymupdf.Point(100, bases[0] - 3))
        ed = v._inline
        select(ed, "ordering")
        for _i in range(20):
            ed.grow_size(1)
        ed.commit()
        rows = letters(v.doc[0])
        self.assertGreaterEqual(len(rows), len(bases), rows)
        for a, b in zip(rows, rows[1:]):
            self.assertLessEqual(a[2], b[1] + 0.5, (a, b))     # no letters over the line above
        steps = [round(b[0] - a[0], 1) for a, b in zip(rows, rows[1:])]
        self.assertEqual(steps.count(13.2), len(steps) - 2, steps)   # the others as they were
        # Add text: a large word on the second line
        d = pymupdf.open()
        d.new_page()
        v = open_view(d, self, tool="addtext")
        v.add_text_at(0, pymupdf.Point(72, 200))
        ed = v._inline
        ed.text.insertPlainText("First line\nHuge second")
        select(ed, "Huge")
        for _i in range(24):
            ed.grow_size(1)
        ed.commit()
        rows = letters(v.doc[0])
        self.assertEqual(len(rows), 2, rows)
        self.assertLessEqual(rows[0][2], rows[1][1] + 0.5, rows)

    def test_find_counts_a_word_partly_resized_once(self):
        d = pymupdf.open()
        p = d.new_page()
        bases = embedded_paragraph(p, code="helv")
        p.insert_text((72, 400), "contractor", fontsize=11)        # one under the other:
        p.insert_text((72, 413.2), "contractor", fontsize=11)      # two matches
        v = open_view(d, self)
        v.edit_text_at(0, pymupdf.Point(100, bases[0] - 3))
        ed = v._inline
        i = ed.text.toPlainText().index("contractor")
        cur = ed.text.textCursor()
        cur.setPosition(i + 5)
        cur.setPosition(i + 10, QTextCursor.KeepAnchor)
        ed.text.setTextCursor(cur)
        for _k in range(4):
            ed.grow_size(1)
        ed.commit()
        self.assertEqual(v.find("contractor"), 3)
        v.clear_search()
        self.assertEqual(v.find("The contractor shall"), 1)
        v.clear_search()
        self.assertEqual(v.find("all"), 2)              # (shall, all: apart, two)


def hidden_word_page(kind):
    """A page of five lines of text set as one, its first line with an invisible word in
    it (kind: "tr3" render mode 3, "alpha0" no opacity, "white" white ink)."""
    d = pymupdf.open()
    p = d.new_page()
    p.insert_text((72, 100), "x", fontname="helv", fontsize=11)     # (the font resource)
    hide, show = {"tr3": (b"3 Tr", b"0 Tr"), "alpha0": (b"/GSa gs", b"/GSb gs"),
                  "white": (b"1 1 1 rg", b"0 0 0 rg")}[kind]
    rows = [b"all dimensions in the field ", b"before ordering materials and ",
            b"report any discrepancies to the ", b"architect in writing within two"]
    c = b"BT /helv 11 Tf 13.2 TL 72 742 Td (The contractor shall verify ) Tj " + hide + \
        b" (SECRET ) Tj " + show + b" (now ) Tj T* "
    c += b"".join(b"(" + r + b") Tj T* " for r in rows) + b"ET"
    d.update_stream(p.get_contents()[0], c)
    if kind == "alpha0":
        a, b = d.get_new_xref(), d.get_new_xref()
        d.update_object(a, "<</Type/ExtGState/ca 0/CA 0>>")
        d.update_object(b, "<</Type/ExtGState/ca 1/CA 1>>")
        kind_, val = d.xref_get_key(p.xref, "Resources")
        target, key = (int(val.split()[0]), "ExtGState") if kind_ == "xref" else \
            (p.xref, "Resources/ExtGState")
        d.xref_set_key(target, key, "<</GSa %d 0 R/GSb %d 0 R>>" % (a, b))
    return d


def shows(page, word="SECRET"):
    """True when word is drawn in ink one can see on the page."""
    for sp in page.get_texttrace():
        if word in "".join(chr(c[0]) for c in sp["chars"]):
            ink = sp["type"] != 3 and sp["opacity"] > 0
            white = tuple(sp["color"] or (0,)) in ((1.0, 1.0, 1.0), (1.0,))
            if ink and not white:
                return True
    return False


class HiddenWords(unittest.TestCase):
    def test_a_hidden_word_stays_hidden(self):
        steps = ("paragraph", "line", "drag", "replace", "drawing")
        for kind in ("tr3", "alpha0", "white"):
            for step in steps:
                with self.subTest(kind=kind, step=step):
                    v = open_view(hidden_word_page(kind), self)
                    page = v.doc[0]
                    (_r, first), = [(r, ln) for r, ln in text_edit.text_lines(page)
                                    if "SECRET" in text_edit.line_text(ln)]
                    self.assertFalse(shows(page))
                    pt = pymupdf.Point(100, first["spans"][0]["origin"][1] - 3)
                    if step in ("paragraph", "line"):
                        v.edit_text_at(0, pt, one_line=step == "line")
                        ed = v._inline
                        self.assertIn("SECRET", ed.text.toPlainText())
                        select(ed, "contractor")
                        ed.toggle("bold")
                        ed.commit()
                    elif step == "drag":
                        v.move_text_line(0, pt, (0, 300))
                    elif step == "replace":
                        self.assertEqual(v.replace_text("contractor", "builder")[0], 1)
                    else:
                        lines = [ln for _r, ln in text_edit.text_lines(page)]
                        v.modify(lambda: text_edit.move_lines(v.doc[0], lines, (5, 300)),
                                 [0])
                    page = v.doc[0]
                    text = page.get_text()
                    self.assertIn("SECRET", text)              # (still there, to find)
                    self.assertTrue("contractor" in text or "builder" in text)
                    self.assertFalse(shows(page))
                    if step in ("paragraph", "line"):
                        self.assertTrue(page.search_for("contractor"))
                    v.dirty = False


def lzw(data):
    """data LZW-encoded as PDF's LZWDecode reads it (9 to 12 bit codes, early change)."""
    table = {bytes([i]): i for i in range(256)}
    nxt, width, out, buf, nbits = 258, 9, bytearray(), 0, 0

    def emit(code):
        nonlocal buf, nbits
        buf, nbits = (buf << width) | code, nbits + width
        while nbits >= 8:
            nbits -= 8
            out.append((buf >> nbits) & 255)
    emit(256)
    w = b""
    for c in data:
        if w + bytes([c]) in table:
            w += bytes([c])
            continue
        emit(table[w])
        table[w + bytes([c])] = nxt
        nxt += 1
        if nxt >= (1 << width) and width < 12:
            width += 1
        if nxt >= 4094:
            emit(256)
            table = {bytes([i]): i for i in range(256)}
            nxt, width = 258, 9
        w = bytes([c])
    if w:
        emit(table[w])
    emit(257)
    if nbits:
        out.append((buf << (8 - nbits)) & 255)
    return bytes(out)


class PdfA(unittest.TestCase):
    def test_pictures_inside_the_content_are_made_pdfa(self):
        from kanzonas import pdfa
        img = bytes((x * 7 + y * 13) % 256 for y in range(40) for x in range(120))
        parts = [
            b"BI /W 40 /H 40 /CS /RGB /BPC 8 /F /LZW ID " + lzw(img) + b" EI",
            b"BI /W 40 /H 40 /CS /RGB /BPC 8 /F [/A85 /LZW] ID " +
            base64.a85encode(lzw(img), adobe=True)[2:] + b" EI",
            b"BI /W 4 /H 1 /CS [/I /RGB 1 <ff000000ff00>] /BPC 8 /I true ID "
            b"\x00\x01\x00\x01 EI",
            b"BI /W 6 /H 1 /CS /G /BPC 8 /Interpolate true ID A EI B EI",   # ("EI" in its data)
            b"BI /W 8 /H 2 /IM true /I true /F /AHx ID ff00ff00 > EI",
            b"BI /W 40 /H 40 /CS /RGB /BPC 8 /F /Fl /I true ID " + zlib.compress(img) + b" EI",
            b"BI /W 40 /H 40 /CS /RGB /BPC 8 /F /LZW /DP <</EarlyChange 1>> ID " + lzw(img) +
            b" EI",
        ]
        content = b"".join(b"q 60 0 0 60 %d %d cm %s Q\n" % (72 + 70 * (i % 5), 600 - 100 * (i // 5),
                                                             part)
                           for i, part in enumerate(parts))
        d = pymupdf.open()
        p = d.new_page()
        p.insert_text((72, 72), "Pictures", fontsize=12)
        x = p.get_contents()[0]
        d.update_stream(x, d.xref_stream(x) + b"\n" + content)
        found = {q.text for q in pdfa.check(d)}
        self.assertIn("Part of the file uses LZW compression, which PDF/A doesn't allow.", found)
        self.assertIn("A picture is set to be smoothed when enlarged (Interpolate).", found)
        path = os.path.join(tempfile.mkdtemp(), "inline_A.pdf")
        result = pdfa.convert(d.tobytes(), path)
        self.assertEqual(result["remaining"], [])
        with pymupdf.open(path) as out:
            data = out[0].read_contents()
            self.assertNotIn(b"/LZW", data)
            self.assertNotIn(b"/I true", data)
            self.assertNotIn(b"/Interpolate true", data)
            # drawn exactly as the original drew without smoothing
            plain = pymupdf.open()
            q = plain.new_page()
            q.insert_text((72, 72), "Pictures", fontsize=12)
            y = q.get_contents()[0]
            plain.update_stream(y, plain.xref_stream(y) + b"\n" + content.replace(
                b"/I true", b"/I false").replace(b"/Interpolate true", b"/Interpolate false"))
            self.assertEqual(out[0].get_pixmap(dpi=72).samples,
                             plain[0].get_pixmap(dpi=72).samples)
        self.assertEqual(pdfa._lzw_decode(lzw(img * 20)), img * 20)     # (past 12-bit codes)


class RightToLeft(unittest.TestCase):
    HEBREW = "\u05e9\u05dc\u05d5\u05dd \u05e2\u05d5\u05dc\u05dd \u05d8\u05d5\u05d1"

    def test_right_to_left_text_is_left_as_it_is(self):
        d = pymupdf.open()
        p = d.new_page()
        p.insert_htmlbox(pymupdf.Rect(72, 80, 500, 120),
                         "<p dir='rtl' style='font-size:14px'>%s</p>" % self.HEBREW)
        p.insert_text((72, 200), "Plain words on a line", fontsize=12)
        v = open_view(d, self)
        page = v.doc[0]
        (_r, ln), = [(r, ln) for r, ln in text_edit.text_lines(page) if r.y1 < 150]
        self.assertEqual(text_edit.line_text(ln), self.HEBREW)
        before = page.get_text("rawdict")
        pt = pymupdf.Point(ln["bbox"][0] + 5, (ln["bbox"][1] + ln["bbox"][3]) / 2)
        with mock.patch("kanzonas.document_view.QMessageBox") as box:
            v.edit_text_at(0, pt)                       # no editor: it says why
            self.assertIsNone(v._inline)
            self.assertIn("right to left", box.information.call_args[0][2])
            v.move_text_line(0, pt, (10, 20))           # dragged: refused
            self.assertIn("right to left", box.warning.call_args[0][2])
            box.reset_mock()
            v.replace_text("\u05d8\u05d5\u05d1", "\u05e8\u05e2")   # replaced in: refused
            self.assertIn("right to left", box.warning.call_args[0][2])
        self.assertEqual(v.doc[0].get_text("rawdict"), before)
        self.assertFalse(v.dirty)
        # an English line with Hebrew typed into it, and Add text: refused
        (_r, en), = [(r, ln) for r, ln in text_edit.text_lines(page) if r.y0 > 150]
        with self.assertRaises(ValueError):
            text_edit.replace_line(v.doc[0], en, "Plain " + self.HEBREW)
        with self.assertRaises(ValueError):
            text_edit.add_text(v.doc[0], (72, 300), self.HEBREW)
        self.assertEqual(v.doc[0].get_text("rawdict"), before)


if __name__ == "__main__":
    unittest.main()
