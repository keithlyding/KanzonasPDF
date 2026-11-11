"""Bookmarks made from the document (headings by their look, a tagged PDF's H1-H6, a drawing
set's sheet numbers), the table of contents pages made from them, and the Bookmarks panel's
tools (sort, styles, a bookmark at the current view).

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_bookmarks_auto
"""
import os
import sys
import tempfile
import time
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog, QLineEdit, QMessageBox  # noqa: E402

APP = QApplication.instance() or QApplication([])

import cad_samples  # noqa: E402
from kanzonas import bookmarks_auto as BA  # noqa: E402
from kanzonas import bookmarks_ui, manual  # noqa: E402
from kanzonas.bookmarks_panel import BookmarksPanel, sort_toc  # noqa: E402
from kanzonas.main_window import MainWindow  # noqa: E402

BODY = ("The contractor agrees to deliver the panels by the end of the month. Every panel is "
        "tested before it leaves the shop, and the test sheet goes with it. ")


class _Writer:
    """Pages of a report written top to bottom, with a header and a footer on every page."""

    def __init__(self, header=True):
        self.doc = pymupdf.open()
        self.page = None
        self.y = 0
        self.header = header
        self.new_page()

    def new_page(self):
        self.page = self.doc.new_page(width=612, height=792)
        n = self.doc.page_count
        if self.header:
            self.page.insert_text((72, 40), "KANZONAS QUARTERLY REVIEW", fontsize=10,
                                  fontname="hebo")
            self.page.insert_text((280, 760), "Page %d of 9" % n, fontsize=9)
        self.y = 72

    def line(self, text, size=10, bold=False, gap=None):
        if self.y > 660:
            self.new_page()
        self.page.insert_text((72, self.y + size), text, fontsize=size,
                              fontname="hebo" if bold else "helv")
        self.y += gap or size * 1.9

    def para(self, words=2):
        if self.y > 600:
            self.new_page()
        self.page.insert_textbox(pymupdf.Rect(72, self.y, 540, self.y + 90), BODY * words,
                                 fontsize=10, fontname="helv")
        self.y += 92


def report():
    """A title, numbered chapters (18 pt bold), numbered sections (14 pt bold), bold
    body-size subsections; the expected bookmarks [(level, title, page index)]."""
    w = _Writer()
    expected = []
    w.line("Kanzonas Quarterly Review 2026", 24, True, 50)
    w.para()
    names = {1: ("Overview", "Scope", "Method"), 2: ("Results", "Sales", "Costs"),
             3: ("Outlook", "Risks", "Plans")}
    for c in (1, 2, 3):
        w.new_page()
        title, s1, s2 = names[c]
        expected.append((1, "%d %s" % (c, title), w.doc.page_count - 1))
        w.line("%d %s" % (c, title), 18, True)
        w.para()
        for k, s in enumerate((s1, s2), 1):
            expected.append((2, "%d.%d %s" % (c, k, s), w.doc.page_count - 1))
            w.line("%d.%d %s" % (c, k, s), 14, True)
            w.para()
            if w.y > 600:
                w.new_page()
            expected.append((3, "Notes on %s" % s.lower(), w.doc.page_count - 1))
            w.line("Notes on %s" % s.lower(), 10, True)
            w.para()
    return w.doc, expected


def spec():
    """Three CSI sections, all in 10 pt: SECTION, PART, 1.1 articles."""
    d = pymupdf.open()
    secs = [("08 71 00", "DOOR HARDWARE"), ("09 29 00", "GYPSUM BOARD"),
            ("09 91 23", "INTERIOR PAINTING")]
    arts = [["SUMMARY", "SUBMITTALS", "QUALITY ASSURANCE"],
            ["MANUFACTURERS", "MATERIALS", "ACCESSORIES"],
            ["EXAMINATION", "INSTALLATION", "CLEANING"]]
    expected = []
    for num, name in secs:
        for part in (1, 2, 3):
            p = d.new_page(width=612, height=792)
            p.insert_text((72, 40), "KANZONAS WAREHOUSE FIT-OUT", fontsize=9)
            p.insert_text((250, 760), "%s - %d" % (num, part), fontsize=10)
            p.insert_text((400, 760), name, fontsize=10)
            y = 80
            if part == 1:
                p.insert_text((200, y), "SECTION %s - %s" % (num, name), fontsize=10)
                expected.append((1, "SECTION %s - %s" % (num, name), d.page_count - 1))
                y += 30
            pname = ["GENERAL", "PRODUCTS", "EXECUTION"][part - 1]
            p.insert_text((72, y), "PART %d - %s" % (part, pname), fontsize=10)
            expected.append((2, "PART %d - %s" % (part, pname), d.page_count - 1))
            y += 24
            for a in range(1, 4):
                p.insert_text((72, y), "%d.%d  %s" % (part, a, arts[part - 1][a - 1]), fontsize=10)
                expected.append((3, "%d.%d %s" % (part, a, arts[part - 1][a - 1]),
                                 d.page_count - 1))
                y += 18
                for b in "AB":
                    p.insert_text((90, y), "%s.  Provide the products listed in the schedule." % b,
                                  fontsize=10)
                    y += 14
                    p.insert_text((108, y), "1.  Comply with the manufacturer's instructions.",
                                  fontsize=10)
                    y += 14
                y += 10
            if part == 3:
                p.insert_text((260, 700), "END OF SECTION", fontsize=10)
    return d, expected


def tagged():
    """A tagged PDF: H1, H2 and a custom role mapped to H3 (Word's "Heading 3"), with
    paragraphs between, on two pages. The heading words are all 11 pt (their look says
    nothing: only the tags do)."""
    d = pymupdf.open()
    font = d.get_new_xref()
    d.update_object(font, "<</Type/Font/Subtype/Type1/BaseFont/Helvetica/Encoding/WinAnsiEncoding>>")
    root, doc_el, ptree = d.get_new_xref(), d.get_new_xref(), d.get_new_xref()
    pages_spec = [[("H1", "Introduction"), ("P", "Some body text here."), ("H2", "Purpose"),
                   ("P", "More body text."), ("Heading3", "Fine print")],
                  [("H2", "Scope of work"), ("P", "Body text."), ("H1", "Appendix")]]
    kids, nums, expected = [], [], []
    for pi, items in enumerate(pages_spec):
        p = d.new_page()
        ops, elems = [], []
        y = 720
        for mcid, (tag, text) in enumerate(items):
            ops.append("/%s <</MCID %d>> BDC BT /F1 11 Tf 72 %d Td (%s) Tj ET EMC" % (
                "P" if tag == "P" else "H", mcid, y, text))
            y -= 30
            x = d.get_new_xref()
            d.update_object(x, "<</Type/StructElem/S/%s/P %d 0 R/Pg %d 0 R/K %d>>" % (
                tag, doc_el, p.xref, mcid))
            elems.append(x)
            if tag != "P":
                expected.append(({"H1": 1, "H2": 2, "Heading3": 3}[tag], text, pi))
        cx = d.get_new_xref()
        d.update_object(cx, "<<>>")
        d.update_stream(cx, "\n".join(ops).encode())
        d.xref_set_key(p.xref, "Contents", "%d 0 R" % cx)
        d.xref_set_key(p.xref, "Resources", "<</Font<</F1 %d 0 R>>>>" % font)
        d.xref_set_key(p.xref, "StructParents", str(pi))
        kids += elems
        nums.append("%d [%s]" % (pi, " ".join("%d 0 R" % x for x in elems)))
    d.update_object(doc_el, "<</Type/StructElem/S/Document/P %d 0 R/K[%s]>>" % (
        root, " ".join("%d 0 R" % x for x in kids)))
    d.update_object(ptree, "<</Nums[%s]>>" % " ".join(nums))
    d.update_object(root, "<</Type/StructTreeRoot/K %d 0 R/ParentTree %d 0 R"
                          "/RoleMap<</Heading3/H3>>>>" % (doc_el, ptree))
    d.xref_set_key(d.pdf_catalog(), "StructTreeRoot", "%d 0 R" % root)
    d.xref_set_key(d.pdf_catalog(), "MarkInfo", "<</Marked true>>")
    return pymupdf.open("pdf", d.tobytes()), expected


def drawing_set():
    d = pymupdf.open()
    for number, title in (("G-001", "COVER SHEET"), ("A-101", "FIRST FLOOR PLAN"),
                          ("A-102", "SECOND FLOOR PLAN"), ("S-201", "FRAMING PLAN")):
        p = d.new_page(width=2592, height=1728)
        cad_samples._title_block(p, title, "A", number)
    return d


def scan(s):
    for _ in s.run():
        pass
    return s


def tree(items):
    return [(it["level"], it["title"], it["page"]) for it in items if it["on"]]


# ---- finding the bookmarks ---------------------------------------------------------------------
class Headings(unittest.TestCase):
    def test_report_hierarchy_by_size_weight_and_numbering(self):
        d, expected = report()
        s = scan(BA.HeadingScan(d))
        items = s.propose()
        self.assertEqual(tree(items), expected)
        # the title is offered, unticked
        self.assertEqual([(it["level"], it["title"], it["on"]) for it in items][0],
                         (1, "Kanzonas Quarterly Review 2026", False))
        titles = " ".join(it["title"] for it in items)
        for junk in ("KANZONAS QUARTERLY REVIEW", "Page", "contractor"):
            self.assertNotIn(junk, titles)
        self.assertEqual([lv for _look, lv, _n in s.styles], [1, 2, 3])
        # each bookmark goes to its heading's place on the page
        for it in items:
            words = d[it["page"]].search_for(it["title"].split()[-1])
            self.assertTrue(any(abs(w.y0 - it["to"].y) < 6 for w in words), it)

    def test_depth_limits_the_levels(self):
        d, expected = report()
        items = scan(BA.HeadingScan(d)).propose()
        toc = BA.toc_entries(items, depth=2)
        self.assertEqual([(e[0], e[1], e[2] - 1) for e in toc],
                         [e for e in expected if e[0] <= 2])
        self.assertTrue(all(e[3]["kind"] == pymupdf.LINK_GOTO for e in toc))

    def test_spec_sections_parts_and_articles(self):
        d, expected = spec()
        items = scan(BA.HeadingScan(d)).propose()
        self.assertEqual(tree(items), expected)
        titles = [it["title"] for it in items]
        self.assertFalse(any(t.startswith(("A.", "1.  Comply", "END OF", "KANZONAS", "08 71"))
                             for t in titles), titles)

    def test_contents_page_parts_lists_and_two_line_headings(self):
        # a contents page (titles with their page numbers) isn't read for headings; a table
        # whose last column is numbers isn't a contents page; "SECTION A" over its title is
        # one heading, even in two sizes
        d = pymupdf.open()
        p = d.new_page()
        p.insert_text((72, 72), "CONTENTS", fontsize=20, fontname="hebo")
        for k, (t, n) in enumerate((("SECTION A", 2), ("SECTION B", 3), ("ATTACHMENT 1", 4))):
            p.insert_text((72, 120 + 20 * k), t, fontsize=14, fontname="hebo")
            p.insert_text((520, 120 + 20 * k), str(n), fontsize=14, fontname="hebo")
        for k, (label, title) in enumerate((("SECTION A", "GENERAL CONDITIONS"),
                                            ("SECTION B", "PERMIT CHANGES"),
                                            ("ATTACHMENT 1", "Fee Selection Form"))):
            p = d.new_page()
            size = 20 if label.startswith("ATT") else 14
            p.insert_text((250, 80), label, fontsize=size, fontname="hebo")
            p.insert_text((180, 80 + size * 1.4), title, fontsize=16, fontname="hebo")
            p.insert_textbox(pymupdf.Rect(72, 140, 540, 400), BODY * 4, fontsize=10)
            if k == 0:                              # a parts list: letters, quantities
                for j, (a, q) in enumerate((("A", 28), ("B", 6), ("C", 4), ("D", 4))):
                    p.insert_text((80, 450 + 18 * j), a, fontsize=12, fontname="hebo")
                    p.insert_text((120, 450 + 18 * j), str(q), fontsize=12)
                    p.insert_text((170, 450 + 18 * j), "Hexagon bolt", fontsize=12)
                p.insert_text((72, 600), "Notes on the parts", fontsize=16, fontname="hebo")
        items = scan(BA.HeadingScan(d)).propose()
        self.assertEqual([(it["title"], it["page"]) for it in items if it["on"]],
                         [("SECTION A - GENERAL CONDITIONS", 1), ("Notes on the parts", 1),
                          ("SECTION B - PERMIT CHANGES", 2),
                          ("ATTACHMENT 1 - Fee Selection Form", 3)])

    def test_numbering_ranks(self):
        n = BA.numbering
        self.assertLess(n("SECTION 08 71 00 - DOOR HARDWARE"), n("PART 2 - PRODUCTS"))
        self.assertLess(n("PART 2 - PRODUCTS"), n("2.1 MANUFACTURERS"))
        self.assertLess(n("2.1 MANUFACTURERS"), n("2.1.3 Hinges"))
        self.assertLess(n("Chapter 3 Results"), n("3.1 Sales"))
        self.assertIsNone(n("1.5 m wide pipe"))
        self.assertIsNone(n("The contractor"))
        self.assertIsNone(n("2026 was a good year"))

    def test_plain_text_has_no_headings(self):
        d = pymupdf.open()
        for _ in range(3):
            d.new_page().insert_textbox(pymupdf.Rect(72, 72, 540, 700), BODY * 8, fontsize=10)
        self.assertEqual(scan(BA.HeadingScan(d)).propose(), [])

    def test_table_of_contents_pages_are_not_read(self):
        d, expected = report()
        d.set_toc(BA.toc_entries(scan(BA.HeadingScan(d)).propose()))
        BA.insert_toc(d, 0)
        n = len(BA.toc_pages(d))
        items = scan(BA.HeadingScan(d)).propose()
        self.assertEqual(tree(items), [(lv, t, p + n) for lv, t, p in expected])

    def test_title_case(self):
        self.assertEqual(BA.title_case("FIRST FLOOR PLAN"), "First Floor Plan")
        self.assertEqual(BA.title_case("PART 2 - PRODUCTS AND THE PARTS"),
                         "Part 2 - Products and the Parts")
        self.assertEqual(BA.title_case("Mixed Case stays"), "Mixed Case stays")


class Tagged(unittest.TestCase):
    def test_headings_and_levels_from_the_tags(self):
        d, expected = tagged()
        self.assertTrue(BA.struct_root(d))
        s = scan(BA.TaggedScan(d))
        self.assertEqual(tree(s.propose()), expected)

    def test_untagged_pdf(self):
        d, _expected = report()
        self.assertEqual(BA.struct_root(d), 0)
        self.assertEqual(scan(BA.TaggedScan(d)).propose(), [])


class Sheets(unittest.TestCase):
    def test_sheet_numbers_and_titles(self):
        d = drawing_set()
        s = scan(BA.SheetScan(d))
        self.assertEqual(tree(s.propose()), [
            (1, "G-001  COVER SHEET", 0), (1, "A-101  FIRST FLOOR PLAN", 1),
            (1, "A-102  SECOND FLOOR PLAN", 2), (1, "S-201  FRAMING PLAN", 3)])
        self.assertEqual(tree(s.propose(group=True)), [
            (1, "G - General", 0), (2, "G-001  COVER SHEET", 0),
            (1, "A - Architectural", 1), (2, "A-101  FIRST FLOOR PLAN", 1),
            (2, "A-102  SECOND FLOOR PLAN", 2),
            (1, "S - Structural", 3), (2, "S-201  FRAMING PLAN", 3)])
        toc = BA.toc_entries(s.propose(), titlecase=True)
        self.assertEqual(toc[1][1], "A-101  First Floor Plan")


class Speed(unittest.TestCase):
    def test_500_pages(self):
        d = pymupdf.open()
        for i in range(500):
            p = d.new_page()
            p.insert_text((72, 40), "Header of the report", fontsize=9)
            p.insert_text((290, 800), "Page %d" % (i + 1), fontsize=9)
            if i % 5 == 0:
                p.insert_text((72, 90), "%d Chapter %d" % (i // 5 + 1, i // 5 + 1), fontsize=18,
                              fontname="hebo")
            p.insert_text((72, 130), "%d.%d Part on page %d" % (i // 5 + 1, i % 5 + 1, i + 1),
                          fontsize=14, fontname="hebo")
            for k in range(4):
                p.insert_textbox(pymupdf.Rect(72, 150 + k * 150, 540, 290 + k * 150), BODY * 5,
                                 fontsize=10)
        d = pymupdf.open("pdf", d.tobytes())
        t = time.perf_counter()
        s = BA.HeadingScan(d)
        longest, last = 0.0, time.perf_counter()
        for _ in s.run():                   # (each step is one page: short slices)
            now = time.perf_counter()
            longest, last = max(longest, now - last), now
        items = s.propose()
        took = time.perf_counter() - t
        self.assertEqual(len(items), 600)
        self.assertEqual(sum(1 for it in items if it["level"] == 1), 100)
        self.assertLess(took, 5.0)
        self.assertLess(longest, 0.25)
        t = time.perf_counter()
        d.set_toc(BA.toc_entries(items))
        BA.insert_toc(d, 0)
        self.assertLess(time.perf_counter() - t, 3.0)


class MuPDFLines(unittest.TestCase):
    """The lines read from MuPDF's own outputs (fast on macOS too) are those PyMuPDF's
    get_text("dict") gives: words, sizes, bold, boxes, direction, and the lines get_text
    leaves out; a page they can't tell everything about is read through get_text."""

    @staticmethod
    def through_dict(page):
        with mock.patch.object(BA, "_mupdf_lines", lambda p: None):
            return BA._line_pieces(page)

    def same(self, page):
        self.assertIsNotNone(BA._mupdf_lines(page), "read from MuPDF's outputs")
        fast, slow = BA._line_pieces(page), self.through_dict(page)
        self.assertEqual([p[:5] for p in fast], [p[:5] for p in slow])
        for a, b in zip(fast, slow):
            self.assertAlmostEqual(abs(a[6].tl - b[6].tl) + abs(a[6].br - b[6].br), 0, delta=0.01)
        return fast

    def test_fonts_sizes_bold_and_turned_pages(self):
        d = pymupdf.open()
        for rotation in (0, 90, 180, 270):
            p = d.new_page()
            p.insert_text((72, 90), "1 Chapter One", fontsize=18, fontname="hebo")
            p.insert_text((72, 130), "Body & <text> été café", fontsize=10)
            tw = pymupdf.TextWriter(p.rect)
            tw.append((72, 160), "Run-in ", font=pymupdf.Font("hebo"), fontsize=11)
            tw.append(tw.last_point, "heading then body", font=pymupdf.Font("helv"),
                      fontsize=11)
            tw.append((72, 190), "Small ", font=pymupdf.Font("tiro"), fontsize=8)
            tw.append(tw.last_point, "and big", font=pymupdf.Font("tiro"), fontsize=16)
            tw.write_text(p)
            p.insert_text((300, 500), "Sideways label", fontsize=10, rotate=90)
            p.set_rotation(rotation)
        d = pymupdf.open("pdf", d.tobytes())
        for page in d:
            pieces = self.same(page)
            texts = [p[1] for p in pieces]
            if page.rotation == 90:             # (only what reads upright as shown)
                self.assertEqual(texts, ["Sideways label"])
            if page.rotation == 0:
                self.assertIn("Body & <text> été café", texts)
                self.assertNotIn("Sideways label", texts)
                run_in = next(p for p in pieces if p[1].startswith("Run-in"))
                self.assertEqual((run_in[3], run_in[4]), (6, 21))     # 6 of 21 letters bold

    def test_lines_with_no_area_are_left_out(self):
        d = pymupdf.open()
        p = d.new_page()
        p.insert_text((72, 100), "Item one", fontsize=11)
        p.insert_text((-200, 300), "Off the page", fontsize=11)
        # a letter drawn with no height (MuPDF lists its line, get_text("dict") doesn't)
        c = p.get_contents()[0]
        d.update_stream(c, d.xref_stream(c) + b"\nq BT /%s 11 Tf 1 0 0 0 72 400 Tm (x) Tj"
                        b" ET Q" % p.get_fonts()[0][4].encode())
        page = pymupdf.open("pdf", d.tobytes())[0]
        self.assertEqual([p[1] for p in self.same(page)], ["Item one"])

    def test_bold_by_the_font_name_or_by_mupdf(self):
        # "Demi" in the name only (MuPDF doesn't take it as bold), and a font MuPDF takes as
        # bold (its descriptor says so) with no such word in its name: both are bold
        for name, descriptor in (("Foundry-Demi", None),
                                 ("Foundry", "<</Type/FontDescriptor/FontName/Foundry"
                                  "/Flags 262176/FontBBox[0 0 1000 1000]/ItalicAngle 0"
                                  "/Ascent 800/Descent -200/CapHeight 700/StemV 160"
                                  "/FontWeight 700>>")):
            d = pymupdf.open()
            p = d.new_page()
            p.insert_text((72, 100), "Some words here", fontsize=12)
            x = p.get_fonts()[0][0]
            d.xref_set_key(x, "BaseFont", "/" + name)
            if descriptor:
                fd = d.get_new_xref()
                d.update_object(fd, descriptor)
                d.xref_set_key(x, "FontDescriptor", "%d 0 R" % fd)
            page = pymupdf.open("pdf", d.tobytes())[0]
            (piece,) = self.same(page)
            self.assertEqual((piece[3], piece[4]), (13, 13), name)

    def test_a_font_named_bold_that_isnt_reads_through_get_text(self):
        # a line in two fonts, and one of the page's fonts named "Demi" though MuPDF doesn't
        # take it as bold: which piece of the line is in it isn't told by MuPDF's outputs
        d = pymupdf.open()
        p = d.new_page()
        tw = pymupdf.TextWriter(p.rect)
        tw.append((72, 100), "Plain words ", font=pymupdf.Font("helv"), fontsize=12)
        tw.append(tw.last_point, "Demi words", font=pymupdf.Font("tiro"), fontsize=12)
        tw.write_text(p)
        x = next(f[0] for f in p.get_fonts() if f[3] == "Times-Roman")
        d.xref_set_key(x, "BaseFont", "/Foundry-Demi")
        page = pymupdf.open("pdf", d.tobytes())[0]
        self.assertIsNone(BA._mupdf_lines(page))
        self.assertEqual(BA._line_pieces(page), self.through_dict(page))

    def test_outputs_not_as_expected_read_through_get_text(self):
        with self.assertRaises(ValueError):
            BA._html_pieces("words outside a span")
        d = pymupdf.open()
        d.new_page().insert_text((72, 100), "Heading", fontsize=18)
        page = pymupdf.open("pdf", d.tobytes())[0]
        with mock.patch.object(BA, "_HTML_LINE", BA.re.compile("(?!)")):    # (no lines)
            self.assertIsNone(BA._mupdf_lines(page))
            self.assertEqual([p[1] for p in BA._line_pieces(page)], ["Heading"])


# ---- the table of contents ----------------------------------------------------------------------
def numbered(n=12):
    d = pymupdf.open()
    for i in range(n):
        d.new_page().insert_text((72, 300), "Body of page %d" % (i + 1), fontsize=11)
    return d


def toc_lines(doc, page):
    """[(title, printed page number, link target page)] of a table of contents page."""
    p = doc[page]
    words = p.get_text("words")
    out = []
    for ln in p.get_links():
        r = ln["from"]
        inside = [w for w in words if pymupdf.Rect(w[:4]).intersects(r)]
        text = [w[4] for w in sorted(inside, key=lambda w: (round(w[3]), w[0]))
                if set(w[4]) != {"."}]
        out.append((" ".join(text[:-1]), int(text[-1]), ln["page"]))
    return out


class TableOfContents(unittest.TestCase):
    def test_links_and_page_numbers_after_the_pages_shift(self):
        d = numbered()
        d.set_toc([[1, "First", 1], [2, "Second", 3, {"kind": pymupdf.LINK_GOTO, "page": 2,
                                                     "to": pymupdf.Point(0, 280)}],
                   [3, "Third", 5], [1, "Fourth", 12], [1, "Web", -1,
                                                       {"kind": pymupdf.LINK_URI,
                                                        "uri": "https://example.com"}]])
        first, n = BA.insert_toc(d, 0)
        self.assertEqual((first, n), (0, 1))
        self.assertEqual(d.page_count, 13)
        lines = toc_lines(d, 0)
        self.assertEqual(lines, [("First", 2, 1), ("Second", 4, 3), ("Third", 6, 5),
                                 ("Fourth", 13, 12)])
        for _title, printed, target in lines:
            self.assertIn("Body of page %d" % (printed - 1), d[target].get_text())
        link = d[0].get_links()[1]
        self.assertAlmostEqual(link["to"].y, 280, delta=1)
        # the bookmarks still go to their pages
        self.assertEqual([e[2] for e in d.get_toc()], [2, 4, 6, 13, -1])
        self.assertEqual(BA.toc_settings(d), {"title": "Contents", "depth": 3})

    def test_update_replaces_the_one_made_before(self):
        d = numbered()
        d.set_toc([[1, "One", 2], [1, "Two", 7]])
        BA.insert_toc(d, 3, title="Index", depth=1)
        self.assertEqual(BA.toc_pages(d), [3])
        # a bookmark to the table itself, and one more bookmark
        toc = d.get_toc(False)
        toc.append([1, "Contents page", 4, {"kind": pymupdf.LINK_GOTO, "page": 3}])
        toc.append([1, "Three", 12, {"kind": pymupdf.LINK_GOTO, "page": 11}])
        d.set_toc(toc)
        BA.insert_toc(d, 0, title="Index", depth=1, replace=True)
        self.assertEqual(BA.toc_pages(d), [3])          # in its place, not a second one
        self.assertEqual(d.page_count, 13)
        self.assertEqual(toc_lines(d, 3), [("One", 2, 1), ("Two", 8, 7), ("Three", 12, 11)])
        self.assertEqual(d.get_toc()[2], [1, "Contents page", 4])
        # many bookmarks: more pages, all replaced together
        body = [i for i in range(d.page_count) if i != 3]
        d.set_toc([[1, "Entry %d" % k, body[k % 12] + 1] for k in range(150)])
        BA.insert_toc(d, 0, replace=True)
        pages = BA.toc_pages(d)
        self.assertGreater(len(pages), 2)
        self.assertEqual(pages, list(range(3, 3 + len(pages))))
        self.assertEqual(d.page_count, 12 + len(pages))
        listed = [x for p in pages for x in toc_lines(d, p)]
        self.assertEqual(len(listed), 150)
        for title, printed, target in listed:
            self.assertEqual(printed, target + 1)
            k = int(title.split()[1])
            self.assertIn("Body of page %d" % (1 + k % 12), d[target].get_text())
            self.assertNotIn(target, pages)

    def test_bigger_pages_and_other_alphabets(self):
        d = numbered(2)
        d.set_toc([[1, "Résumé", 1], [1, "Введение", 2]])
        first, n = BA.insert_toc(d, 0, size=(2592, 1728))
        self.assertEqual(d[0].rect, pymupdf.Rect(0, 0, 2592, 1728))
        text = d[0].get_text()
        self.assertIn("Résumé", text)
        self.assertIn("Введение", text)

    def test_fonts_embedded_for_pdfa(self):
        """The table is written in fonts embedded in its pages (MuPDF's own Helvetica, or a
        Unicode font for other alphabets): Check PDF/A finds no font problem there, and it
        looks the same in every reader."""
        from kanzonas import pdfa
        for titles in (["Résumé", "Second – “quoted”"], ["Введение", "Ελληνικά", "中文"]):
            d = numbered(3)
            d.set_toc([[1, t, k + 1] for k, t in enumerate(titles)])
            BA.insert_toc(d, 0)
            fonts = d[0].get_fonts(full=True)
            self.assertTrue(fonts)
            for f in fonts:
                self.assertNotEqual(f[1], "n/a", f)             # (n/a: not embedded)
            problems = [p for p in pdfa.check(d) if p.kind == "fonts" and p.page == 0]
            self.assertEqual(problems, [], titles)
            text = d[0].get_text()
            for t in titles:
                self.assertIn(t, text)

    def test_entries_are_blocks_of_added_text(self):
        """Each title (and the table's own) is a block of added text (added_text): Edit text
        opens it whole, wrapped as written; a word longer than the line is cut."""
        from kanzonas import added_text, text_edit
        d = numbered(3)
        long = ("A title long enough to wrap onto a second line of the table of contents "
                "page, as long titles do")
        word = "W" * 90
        d.set_toc([[1, "One", 1], [2, long, 2], [1, word, 3]])
        BA.insert_toc(d, 0)
        page = d[0]
        blocks = added_text.find(page, text_edit.text_lines(page))
        texts = [added_text.contents(page, b)[0].text for b in blocks]
        self.assertEqual(texts[:3], ["Contents", "One", long])
        self.assertEqual(texts[3].replace("\n", ""), word)
        self.assertEqual(len(blocks[2].lines), 2)                # wrapped in its block
        self.assertGreater(len(blocks[3].lines), 1)
        self.assertEqual(len(page.get_contents()), 1)
        self.assertEqual(toc_lines(d, 0)[:2], [("One", 2, 1), (long, 3, 2)])


# ---- with the other page tools ------------------------------------------------------------------
class WithOtherTools(unittest.TestCase):
    def test_replace_pages_keeps_a_bookmarks_spot_and_drops_the_table_mark(self):
        """Replace pages: a bookmark to a spot on a page goes to the same spot of the
        drawing on the new, larger page (as its markups do); a table of contents page
        replaced by a drawing is no longer the table (making it again doesn't delete it)."""
        from kanzonas import replace_pages
        d = numbered(4)
        d.set_toc([[1, "Spot", 3, {"kind": pymupdf.LINK_GOTO, "page": 2,
                                   "to": pymupdf.Point(100, 300), "bold": True,
                                   "color": (1, 0, 0)}], [1, "Four", 4]])
        BA.insert_toc(d, 0)
        self.assertEqual(BA.toc_pages(d), [0])
        new = pymupdf.open()
        for _ in range(2):
            new.new_page(width=1190, height=1684).insert_text((72, 72), "NEW", fontsize=12)
        replace_pages.replace(d, new, [(0, 0), (3, 1)], scale=True)
        self.assertEqual(BA.toc_pages(d), [])
        e = d.get_toc(False)[0]
        self.assertEqual(e[2], 4)
        self.assertAlmostEqual(e[3]["to"].x, 200, delta=1)
        self.assertAlmostEqual(e[3]["to"].y, 600, delta=1)
        self.assertTrue(e[3].get("bold"))
        self.assertEqual(tuple(e[3]["color"]), (1, 0, 0))

    def test_combine_keeps_destinations_and_styles(self):
        from kanzonas import combine
        tmp = tempfile.mkdtemp()
        paths = []
        for k in range(2):
            d = numbered(3)
            d.set_toc([[1, "Start %d" % k, 1],
                       [2, "Spot %d" % k, 3, {"kind": pymupdf.LINK_GOTO, "page": 2,
                                              "to": pymupdf.Point(50, 400), "italic": True,
                                              "color": (0, 0, 1)}],
                       [1, "Web", -1, {"kind": pymupdf.LINK_URI, "uri": "https://example.com"}]])
            paths.append(os.path.join(tmp, "f%d.pdf" % k))
            d.save(paths[-1])
        out = os.path.join(tmp, "out.pdf")
        combine.combine(paths, out, bookmarks=True)
        with pymupdf.open(out) as r:
            toc = r.get_toc(False)
            self.assertEqual([e[:3] for e in toc],
                             [[1, "f0", 1], [2, "Start 0", 1], [3, "Spot 0", 3], [2, "Web", -1],
                              [1, "f1", 4], [2, "Start 1", 4], [3, "Spot 1", 6], [2, "Web", -1]])
            spot = toc[6][3]
            self.assertAlmostEqual(spot["to"].y, 400, delta=1)
            self.assertTrue(spot.get("italic"))
            self.assertEqual(tuple(spot["color"]), (0, 0, 1))
            self.assertEqual(toc[7][3].get("uri"), "https://example.com")


class Redaction(unittest.TestCase):
    def test_no_copy_of_a_redacted_title_stays(self):
        """Search & redact takes the term out of the bookmarks (styled ones too, the panel
        showing them) and out of the title a table of contents page remembers; Apply
        redactions on a table's page takes its remembered title away."""
        from kanzonas.document_view import DocumentView
        word = "TOPSECRET"
        tmp = tempfile.mkdtemp()
        for scrub in (True, False):
            d = numbered(4)
            d[2].insert_text((72, 500), "The %s part" % word, fontsize=12)
            d.set_toc([[1, "Intro", 1],
                       [1, "The %s part" % word, 3, {"kind": pymupdf.LINK_GOTO, "page": 2,
                                                    "to": pymupdf.Point(0, 480),
                                                    "bold": True, "color": (1, 0, 0)}]])
            BA.insert_toc(d, 0, title="%s contents" % word)
            path = os.path.join(tmp, "in%d.pdf" % scrub)
            d.save(path)
            v = DocumentView(path)
            self.addCleanup(lambda v=v: (setattr(v, "dirty", False), v.close_doc()))
            self.assertGreater(v.search_redact(word), 0)
            v.apply_redactions(scrub)
            out = os.path.join(tmp, "out%d.pdf" % scrub)
            v.save(out)
            with pymupdf.open(out) as r:
                self.assertNotIn(word.encode(), r.tobytes(expand=255))
                e = r.get_toc(False)[1]
                self.assertEqual(e[1], "The [redacted] part")
                self.assertTrue(e[3].get("bold"))
        # a mark drawn over the table's page (not a search): its remembered title goes
        d = numbered(2)
        d.set_toc([[1, "One", 1]])
        BA.insert_toc(d, 0, title="Private list")
        d[0].add_redact_annot(pymupdf.Rect(40, 40, 400, 90))
        path = os.path.join(tmp, "marked.pdf")
        d.save(path)
        v = DocumentView(path)
        self.addCleanup(lambda: (setattr(v, "dirty", False), v.close_doc()))
        v.apply_redactions(False)
        self.assertNotIn("title", BA.toc_settings(v.doc))
        self.assertEqual(BA.toc_pages(v.doc), [0])

    def test_a_bookmark_to_a_named_destination_still_goes_there(self):
        """Search & redact rewrites the bookmarks when a title has the term: one to a
        named destination kept going nowhere."""
        from kanzonas.document_view import DocumentView
        d = numbered(4)
        d[1].insert_text((72, 500), "SECRET words", fontsize=12)
        d.set_toc([[1, "SECRET plan", 2], [1, "Named", 3]])
        x = d.get_toc(False)[1][3]["xref"]
        names = d.get_new_xref()
        d.update_object(names, "<</Names[(sec)[%d 0 R/XYZ 0 500 0]]>>" % d.page_xref(2))
        d.xref_set_key(d.pdf_catalog(), "Names", "<</Dests %d 0 R>>" % names)
        d.xref_set_key(x, "A", "null")
        d.xref_set_key(x, "Dest", "(sec)")
        path = os.path.join(tempfile.mkdtemp(), "named.pdf")
        d.save(path)
        v = DocumentView(path)
        self.addCleanup(lambda: (setattr(v, "dirty", False), v.close_doc()))
        self.assertGreater(v.search_redact("SECRET"), 0)
        v.apply_redactions(False)
        toc = v.doc.get_toc(False)
        self.assertEqual([e[:3] for e in toc], [[1, "[redacted] plan", 2], [1, "Named", 3]])
        self.assertAlmostEqual(toc[1][3]["to"].y, v.doc[2].rect.height - 500, delta=1)


# ---- in the window: one undo step each ----------------------------------------------------------
class Quiet(unittest.TestCase):
    def setUp(self):
        for name, value in (("information", None), ("warning", None), ("critical", None),
                            ("question", QMessageBox.Yes)):
            p = mock.patch.object(QMessageBox, name, return_value=value)
            p.start()
            self.addCleanup(p.stop)
        self.tmp = tempfile.mkdtemp()

    def window(self, doc, name="doc.pdf"):
        path = os.path.join(self.tmp, name)
        doc.save(path)
        w = MainWindow()
        w.show()
        w.open_file(path)
        APP.processEvents()

        def close():
            v = w.view()
            if v is not None:
                v.dirty = False
            w._close_confirmed = True
            w.close()
        self.addCleanup(close)
        return w, w.view()


def accept(dlg):
    dlg._accept()
    return dlg.result() == QDialog.Accepted


class InTheWindow(Quiet):
    def test_make_bookmarks_replace_or_add_and_undo(self):
        d, expected = report()
        d.set_toc([[1, "Kept", 1, {"kind": pymupdf.LINK_GOTO, "page": 0, "bold": True,
                                   "color": (1, 0, 0), "to": pymupdf.Point(0, 100)}]])
        w, v = self.window(d)
        before = v.doc.get_toc(False)
        self.assertEqual(bookmarks_ui.make_bookmarks(w, "headings", accept), len(expected))
        self.assertEqual([(e[0], e[1], e[2] - 1) for e in v.doc.get_toc()], expected)
        self.assertEqual(len(w.bookmarks.toc), len(expected))
        v.undo()
        self.assertEqual(v.doc.get_toc(False)[0][:3], before[0][:3])
        self.assertTrue(v.doc.get_toc(False)[0][3].get("bold"))

        def add(dlg):
            dlg.mode_add.setChecked(True)
            dlg.depth.setValue(1)
            return accept(dlg)
        self.assertEqual(bookmarks_ui.make_bookmarks(w, "headings", add), 3)
        self.assertEqual([e[1] for e in v.doc.get_toc()], ["Kept", "1 Overview", "2 Results",
                                                           "3 Outlook"])

    def test_preview_untick_rename_and_levels(self):
        d, expected = report()
        w, v = self.window(d)

        def edit(dlg):
            top = dlg.tree.topLevelItem(1)              # "1 Overview" (0 is the title)
            top.setText(0, "Overview")
            first_child = top.child(0)                  # "1.1 Scope"
            first_child.setCheckState(0, Qt.Unchecked)             # unticked: its children move up
            last = dlg.tree.topLevelItem(dlg.tree.topLevelItemCount() - 1)
            last.setSelected(True)
            dlg._level(1)                                # "3 Outlook" under "2 Results"
            return accept(dlg)
        bookmarks_ui.make_bookmarks(w, "headings", edit)
        toc = v.doc.get_toc()
        self.assertEqual(toc[0][:2], [1, "Overview"])
        self.assertEqual(toc[1][:2], [2, "Notes on scope"])
        outlook = next(p for _lv, t, p in expected if t == "3 Outlook")
        self.assertIn([2, "3 Outlook", outlook + 1], toc)

    def test_tagged_and_sheet_routes(self):
        d, expected = tagged()
        w, v = self.window(d)
        bookmarks_ui.make_bookmarks(w, "tags", accept)
        self.assertEqual([(e[0], e[1], e[2] - 1) for e in v.doc.get_toc()], expected)
        d2 = drawing_set()
        w2, v2 = self.window(d2, "set.pdf")
        bookmarks_ui.make_bookmarks(w2, "sheets", accept)
        self.assertEqual(v2.doc.get_toc()[1], [1, "A-101  FIRST FLOOR PLAN", 2])
        self.assertIsNone(bookmarks_ui.make_bookmarks(w2, "tags", accept))   # not tagged

    def test_insert_and_update_toc_one_undo_step_each(self):
        d = numbered(6)
        d.set_toc([[1, "A", 2], [2, "B", 4], [1, "C", 6]])
        w, v = self.window(d)
        data = v.doc.tobytes()
        self.assertEqual(bookmarks_ui.insert_toc(w, lambda dlg: True), (0, 1))
        self.assertEqual(v.doc.page_count, 7)
        self.assertEqual(toc_lines(v.doc, 0), [("A", 3, 2), ("B", 5, 4), ("C", 7, 6)])
        self.assertEqual(len(v.pages), 7)
        # a new bookmark, then the table updated in place
        v.set_toc(v.doc.get_toc(False) + [[1, "D", 2, {"kind": pymupdf.LINK_GOTO, "page": 1}]])

        def update(dlg):
            self.assertTrue(dlg.at_old.isChecked())
            return True
        bookmarks_ui.insert_toc(w, update)
        self.assertEqual(v.doc.page_count, 7)
        self.assertEqual(BA.toc_pages(v.doc), [0])
        self.assertEqual(toc_lines(v.doc, 0), [("A", 3, 2), ("B", 5, 4), ("C", 7, 6),
                                               ("D", 2, 1)])
        v.undo()
        self.assertEqual([x[0] for x in toc_lines(v.doc, 0)], ["A", "B", "C"])
        v.undo()
        v.undo()
        self.assertEqual(v.doc.page_count, 6)
        self.assertEqual(BA.toc_pages(v.doc), [])
        self.assertEqual(v.doc.get_toc(), pymupdf.open("pdf", data).get_toc())
        v.redo()
        self.assertEqual(v.doc.page_count, 7)

    def test_no_bookmarks_no_toc(self):
        w, v = self.window(numbered(2))
        self.assertIsNone(bookmarks_ui.insert_toc(w, lambda dlg: True))
        self.assertEqual(v.doc.page_count, 2)
        self.assertFalse(v.can_undo())

    def test_no_text_no_headings(self):
        d = pymupdf.open()
        d.new_page().draw_rect((100, 100, 300, 300))
        w, v = self.window(d, "scan.pdf")
        with mock.patch.object(QMessageBox, "information") as box:
            self.assertIsNone(bookmarks_ui.make_bookmarks(w, "headings", accept))
        self.assertIn("Recognize text (OCR)", box.call_args[0][2])
        self.assertFalse(v.can_undo())

    def test_every_command_in_the_manual_and_menus(self):
        w, _v = self.window(numbered(2))
        self.assertEqual(manual.missing_from_manual(w), [])
        self.assertEqual(w.a_bm_add_view.shortcut().toString(), "Ctrl+B")
        names = [a.text() for a in w.bookmarks.menu.actions()]
        self.assertIn(w.a_toc.text(), names)
        self.assertIn(w.a_bm_headings.text(), names)


class Panel(Quiet):
    def test_sort_by_page_and_name_keeps_children(self):
        toc = [[1, "Section 10", 9], [2, "b", 12], [2, "a", 10], [1, "Section 9", 3],
               [1, "Section 2", 5]]
        self.assertEqual([e[1] for e in sort_toc(toc, "page")],
                         ["Section 9", "Section 2", "Section 10", "a", "b"])
        self.assertEqual([e[1] for e in sort_toc(toc, "name")],
                         ["Section 2", "Section 9", "Section 10", "a", "b"])

    def test_styles_and_places_survive_editing_another_bookmark(self):
        d = numbered(4)
        d.set_toc([[1, "Red", 2, {"kind": pymupdf.LINK_GOTO, "page": 1, "color": (1, 0, 0),
                                  "bold": True, "to": pymupdf.Point(0, 250)}],
                   [1, "Plain", 3]])
        w, v = self.window(d)
        p = w.bookmarks
        p.tree.setCurrentItem(p.tree.topLevelItem(1))
        with mock.patch("kanzonas.bookmarks_panel.QInputDialog.getText",
                        return_value=("Renamed", True)):
            p._rename()
        red = v.doc.get_toc(False)[0]
        self.assertEqual(red[1], "Red")
        self.assertEqual(red[3]["color"], (1.0, 0.0, 0.0))
        self.assertTrue(red[3]["bold"])
        self.assertAlmostEqual(red[3]["to"].y, 250, delta=1)
        self.assertEqual(v.doc.get_toc()[1][1], "Renamed")
        # italic and a color for the second one
        self.assertTrue(p.toggle_style("italic"))
        self.assertTrue(p.set_color((0, 0, 1)))
        second = v.doc.get_toc(False)[1][3]
        self.assertTrue(second.get("italic"))
        self.assertEqual(second.get("color"), (0.0, 0.0, 1.0))
        self.assertTrue(p.tree.topLevelItem(1).font(0).italic())
        v.undo()
        v.undo()
        self.assertFalse(v.doc.get_toc(False)[1][3].get("italic"))

    def test_a_named_destination_keeps_going_to_its_place(self):
        # (set_toc can't write a named destination: the bookmark went nowhere after any
        # edit in the panel)
        d = numbered(4)
        d.set_toc([[1, "A", 1], [1, "B", 2]])
        xrefs = d.get_outline_xrefs()
        dests = d.get_new_xref()
        d.update_object(dests, "<</chap3 [%d 0 R /XYZ 0 500 0]>>" % d.page_xref(2))
        d.xref_set_key(d.pdf_catalog(), "Dests", "%d 0 R" % dests)
        d.xref_set_key(xrefs[1], "Dest", "/chap3")
        d.xref_set_key(xrefs[1], "A", "null")
        w, v = self.window(d)
        self.assertEqual(v.doc.get_toc(False)[1][3]["kind"], pymupdf.LINK_NAMED)
        p = w.bookmarks
        p.tree.setCurrentItem(p.tree.topLevelItem(0))
        self.assertTrue(p.toggle_style("bold"))
        b = v.doc.get_toc(False)[1]
        self.assertEqual(b[2], 3)
        self.assertEqual(b[3]["kind"], pymupdf.LINK_GOTO)
        self.assertAlmostEqual(b[3]["to"].y, v.doc[2].rect.height - 500, delta=1)

    def test_bookmark_at_view_and_destination(self):
        w, v = self.window(numbered(5))
        v.goto_page(3, 200)
        APP.processEvents()
        page, to, title = v.view_destination()
        self.assertEqual((page, title), (3, ""))
        self.assertGreater(to.y, 50)
        with mock.patch("kanzonas.bookmarks_panel.QInputDialog.getText",
                        return_value=("Here", True)):
            w.a_bm_add_view.trigger()
        e = v.doc.get_toc(False)[0]
        self.assertEqual(e[:3], [1, "Here", 4])
        self.assertAlmostEqual(e[3]["to"].y, to.y, delta=2)
        # the selected bookmark goes to another view
        w.bookmarks.tree.setCurrentItem(w.bookmarks.tree.topLevelItem(0))
        v.goto_page(1)
        APP.processEvents()
        w.a_bm_set_dest.trigger()
        self.assertEqual(v.doc.get_toc()[0], [1, "Here", 2])
        # selected text: the bookmark is named after it and goes to it
        page = v.doc[2]
        words = page.get_text("words")
        v.set_text_selection(2, [(*w_[:5], 0, 0, 0) for w_ in words[:4]])
        page_i, to, title = v.view_destination()
        self.assertEqual(page_i, 2)
        self.assertTrue(title.startswith("Body of page"), title)
        self.assertAlmostEqual(to.y, words[0][1] - 4, delta=1)
        # Ctrl+B in a text box is the text box's
        box = QLineEdit(w)
        box.show()
        box.setFocus()
        APP.processEvents()
        with mock.patch.object(BookmarksPanel, "add_at_view") as add:
            w.bookmark_here()
        if APP.focusWidget() is box:
            add.assert_not_called()


if __name__ == "__main__":
    unittest.main()
