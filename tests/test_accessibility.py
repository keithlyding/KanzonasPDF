"""Document > Accessibility (kanzonas/accessibility.py, autotag.py, accessibility_ui.py).

- Check accessibility finds each problem it looks for in documents made to have it, and
  nothing (but the list of things to check by hand) in a well-tagged one built by hand.
- The fixes write the right keys: title (properties, XMP dc:title, DisplayDocTitle),
  language, tab order, form field tooltips from their labels, link descriptions, alt text
  into the right Figure element, a figure made decorative (its content an artifact, the
  element gone from the tree), pictures and shapes marked decorative from Edit objects,
  standard fonts embedded, the PDF/UA identifier.
- Auto-tag of a generated multi-page document (a title, headings, paragraphs, a bulleted
  list, a picture, a table with ruling lines, a link, a header and a page number on every
  page) gives the expected tree; every piece of content is tagged or an artifact, MCIDs and
  the ParentTree agree, the text reads the same and every page draws pixel for pixel the
  same; Save and open keep it; Ctrl+Z gives back exactly the document from before.

veraPDF's PDF/UA-1 profile passed the auto-tagged sample with the fixes applied when this was
written (veraPDF 1.28); the tests don't need it.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_accessibility
"""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import accessibility as acc, autotag  # noqa: E402

PARA = ("Accessible documents can be read by everyone. A screen reader follows the tags of "
        "the document to read its headings, paragraphs, lists and tables in order.")


def png(w=60, h=40, rgb=(200, 60, 30)):
    pm = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, w, h), False)
    pm.set_rect(pm.irect, rgb)
    return pm.tobytes("png")


def sample(pages=3, link=True):
    """The sample document: on each page a header and a page number, a heading, a paragraph,
    a smaller heading, a bulleted list (bullets drawn on their own), a picture, a table with
    ruling lines and a bold first row, a line with a link; a title on the first page."""
    d = pymupdf.open()
    for i in range(pages):
        p = d.new_page(width=612, height=792)
        p.insert_text((72, 40), "Annual Report 2026", fontsize=9)
        p.insert_text((290, 760), "Page %d" % (i + 1), fontsize=9)
        y = 90
        if i == 0:
            p.insert_text((72, y), "Accessible Documents", fontname="hebo", fontsize=24)
            y += 40
        p.insert_text((72, y), "Section %d" % (i + 1), fontname="hebo", fontsize=16)
        y += 14
        p.insert_textbox(pymupdf.Rect(72, y, 540, y + 60), PARA, fontsize=11)
        y += 60
        p.insert_text((72, y), "Details", fontname="hebo", fontsize=13)
        y += 22
        for item in ["First point", "Second point", "Third point"]:
            p.insert_text((80, y), "•", fontsize=11)
            p.insert_text((94, y), item, fontsize=11)
            y += 16
        y += 10
        p.insert_image(pymupdf.Rect(72, y, 192, y + 80), stream=png())
        y += 100
        cols = [72, 200, 330, 460]
        rows = [y, y + 20, y + 40, y + 60]
        for x in cols:
            p.draw_line((x, rows[0]), (x, rows[-1]))
        for yy in rows:
            p.draw_line((cols[0], yy), (cols[-1], yy))
        data = [["Item", "Count", "Price"], ["Apples", "12", "3.50"], ["Pears", "7", "2.25"]]
        for r_, row in enumerate(data):
            for c_, t in enumerate(row):
                p.insert_text((cols[c_] + 4, rows[r_] + 14), t, fontsize=10,
                              fontname="hebo" if r_ == 0 else "helv")
        y = rows[-1] + 30
        p.insert_text((72, y), "Read more at example.com today.", fontsize=11)
        if link:
            p.insert_link({"kind": pymupdf.LINK_URI, "uri": "https://example.com",
                           "from": pymupdf.Rect(140, y - 10, 205, y + 3)})
    return d


def add_resource(doc, page, kind, name, xref):
    """page's resources[kind][name] = xref (the resources may be an object of their own)."""
    m = pymupdf.mupdf
    pdf = pymupdf._as_pdf_document(doc)
    obj = m.pdf_load_object(pdf, page.xref)
    res = m.pdf_resolve_indirect(m.pdf_dict_gets(obj, "Resources"))
    if not m.pdf_is_dict(res):
        res = m.pdf_dict_puts_dict(obj, "Resources", 2)
    sub = m.pdf_resolve_indirect(m.pdf_dict_gets(res, kind))
    if not m.pdf_is_dict(sub):
        sub = m.pdf_dict_puts_dict(res, kind, 2)
    m.pdf_dict_puts(sub, name, m.pdf_new_indirect(pdf, xref, 0))


def tree_of(doc):
    """The structure tree as nested (type, [kids]) tuples, leaving out MCIDs."""
    t = acc.Tree(doc)
    top = [n for n in t.nodes if n.parent is None]

    def walk(n):
        return (n.type, [walk(k) for k in n.kids])
    return [walk(n) for n in top]


def renders(doc, dpi=72):
    return [p.get_pixmap(dpi=dpi, annots=False).samples for p in doc]


def texts(doc):
    return [p.get_text() for p in doc]


def problems(doc, kind=None):
    found = [p for p in acc.check(doc) if p.kind != "manual"]
    return [p for p in found if kind is None or p.kind == kind]


def texts_of(found):
    return " | ".join(p.text for p in found)


def autotagged(d, lang="en-US"):
    plans = autotag.make_plans(d)
    autotag.apply(d, plans, lang=lang)
    return plans


# ---- a well-tagged document, by hand ---------------------------------------------------
def hand_tagged():
    """One page, tagged by hand the way PDF/UA wants: a heading, a paragraph with a link, a
    figure with its alt text, a header artifact; title, language, embedded font."""
    d = pymupdf.open()
    p = d.new_page(width=612, height=792)
    font = pymupdf.Font("helv")
    p.insert_font(fontname="F1", fontbuffer=font.buffer)
    img = d.get_new_xref()
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 4, 4), False)
    pix.set_rect(pix.irect, (10, 200, 10))
    d.update_object(img, "<</Type /XObject /Subtype /Image /Width 4 /Height 4 "
                         "/ColorSpace /DeviceRGB /BitsPerComponent 8>>")
    d.update_stream(img, bytes(pix.samples))
    add_resource(d, p, "XObject", "Im1", img)
    content = (b"/Artifact <</Type /Pagination /Subtype /Header>> BDC BT /F1 9 Tf 72 760 Td "
               b"(Header) Tj ET EMC\n"
               b"/H1 <</MCID 0>> BDC BT /F1 20 Tf 72 700 Td (Title) Tj ET EMC\n"
               b"/P <</MCID 1>> BDC BT /F1 11 Tf 72 670 Td (Read ) Tj ET EMC\n"
               b"/Link <</MCID 2>> BDC BT /F1 11 Tf 102 670 Td (this) Tj ET EMC\n"
               b"/Figure <</MCID 3>> BDC q 50 0 0 50 72 560 cm /Im1 Do Q EMC\n")
    x = d.get_new_xref()
    d.update_object(x, "<<>>")
    d.update_stream(x, content)
    d.xref_set_key(p.xref, "Contents", "%d 0 R" % x)
    p = d[0]
    p.insert_link({"kind": pymupdf.LINK_URI, "uri": "https://example.com",
                   "from": pymupdf.Rect(100, 112, 125, 125)})
    link = p.annot_xrefs()[0][0]
    d.xref_set_key(link, "Contents", "(Example site)")
    root, top, h1, para, lnk, fig, ptree = (d.get_new_xref() for _ in range(7))
    pg = "%d 0 R" % p.xref
    d.update_object(h1, "<</Type /StructElem /S /H1 /P %d 0 R /Pg %s /K 0>>" % (top, pg))
    d.update_object(lnk, "<</Type /StructElem /S /Link /P %d 0 R /Pg %s /K [2 <</Type /OBJR "
                         "/Obj %d 0 R /Pg %s>>]>>" % (para, pg, link, pg))
    d.update_object(para, "<</Type /StructElem /S /P /P %d 0 R /Pg %s /K [1 %d 0 R]>>" % (
        top, pg, lnk))
    d.update_object(fig, "<</Type /StructElem /S /Figure /P %d 0 R /Pg %s /K 3 /Alt (A green "
                         "square)>>" % (top, pg))
    d.update_object(top, "<</Type /StructElem /S /Document /P %d 0 R /K [%d 0 R %d 0 R %d 0 R]"
                         ">>" % (root, h1, para, fig))
    d.update_object(ptree, "<</Nums [0 [%d 0 R %d 0 R %d 0 R %d 0 R] 1 %d 0 R]>>" % (
        h1, para, lnk, fig, lnk))
    d.update_object(root, "<</Type /StructTreeRoot /K %d 0 R /ParentTree %d 0 R "
                          "/ParentTreeNextKey 2>>" % (top, ptree))
    cat = d.pdf_catalog()
    d.xref_set_key(cat, "StructTreeRoot", "%d 0 R" % root)
    d.xref_set_key(cat, "MarkInfo", "<</Marked true>>")
    d.xref_set_key(p.xref, "StructParents", "0")
    d.xref_set_key(link, "StructParent", "1")
    d.xref_set_key(p.xref, "Tabs", "/S")
    acc.set_title(d, "A tagged document")
    acc.set_language(d, "en-US")
    acc.set_pdfua(d)
    return d


class Check(unittest.TestCase):
    def test_a_well_tagged_document_has_nothing_found(self):
        d = hand_tagged()
        self.assertEqual(problems(d), [], texts_of(problems(d)))
        found = acc.check(d)
        self.assertTrue(found and all(p.kind == "manual" for p in found))   # (by hand)
        # the same after a save and open
        d2 = pymupdf.open("pdf", d.tobytes())
        self.assertEqual(problems(d2), [])

    def test_an_untagged_document(self):
        d = sample(1)
        found = problems(d)
        fixes = {p.fix for p in found}
        self.assertIn("autotag", fixes)
        self.assertIn("title", fixes)
        self.assertIn("lang", fixes)
        self.assertIn("tabs", fixes)
        self.assertIn("links", fixes)
        self.assertIn("fonts", fixes)           # (Helvetica, not embedded)
        doc_texts = texts_of(problems(d, "document"))
        self.assertIn("isn't tagged", doc_texts)
        self.assertIn("no title", doc_texts)
        self.assertIn("language isn't set", doc_texts)
        self.assertIn("DisplayDocTitle", doc_texts)

    def test_document_settings(self):
        d = hand_tagged()
        d.xref_set_key(d.pdf_catalog(), "ViewerPreferences/DisplayDocTitle", "false")
        d.xref_set_key(d.pdf_catalog(), "Lang", "(not a language!)")
        d.xref_set_key(d.pdf_catalog(), "MarkInfo", "<</Marked true /Suspects true>>")
        d.set_xml_metadata("")
        found = texts_of(problems(d))
        self.assertIn("DisplayDocTitle is false", found)
        self.assertIn("isn't a valid language tag", found)
        self.assertIn("suspect", found)
        self.assertIn("no XMP metadata", found)
        self.assertIn("doesn't identify itself as PDF/UA", found)

    def test_content_not_tagged_and_wrong_nesting(self):
        d = hand_tagged()
        p = d[0]
        x = p.get_contents()[0]
        data = d.xref_stream(x)
        data += (b"\nBT /F1 11 Tf 72 400 Td (loose) Tj ET\n"
                 b"/P <</MCID 9>> BDC /Artifact BMC BT /F1 11 Tf 72 380 Td (a) Tj ET EMC EMC\n"
                 b"/Artifact BMC /P <</MCID 8>> BDC BT /F1 11 Tf 72 360 Td (b) Tj ET EMC EMC\n")
        d.update_stream(x, data)
        found = problems(d, "content")
        self.assertEqual(len(found), 3, texts_of(found))
        self.assertIn("neither tagged nor marked as artifacts", texts_of(found))
        self.assertIn("Content marked as an artifact sits inside tagged", texts_of(found))
        self.assertIn("Tagged content sits inside content marked as an artifact",
                      texts_of(found))
        self.assertTrue(all(p.page == 0 for p in found))

    def _edit_tree(self, d, fn):
        t = acc.Tree(d)
        fn(d, t)

    def test_figure_without_alt_and_headings(self):
        d = hand_tagged()
        t = acc.Tree(d)
        fig = next(n for n in t.nodes if n.type == "Figure")
        h1 = next(n for n in t.nodes if n.type == "H1")
        d.xref_set_key(fig.num, "Alt", "null")
        d.xref_set_key(h1.num, "S", "/H2")
        found = problems(d, "structure")
        self.assertIn("A figure has no alternate text", texts_of(found))
        self.assertIn("The first heading is H2, not H1", texts_of(found))
        alt = next(p for p in found if "figure" in p.text)
        self.assertEqual((alt.fix, alt.node, alt.page), ("alt", fig.num, 0))
        # a level skipped; H mixed with H1-H6
        d.xref_set_key(h1.num, "S", "/H1")
        para = next(n for n in t.nodes if n.type == "P")
        d.xref_set_key(para.num, "S", "/H3")
        self.assertIn("H1 is followed by H3", texts_of(problems(d, "structure")))
        d.xref_set_key(para.num, "S", "/H")
        self.assertIn("both H and H1-H6", texts_of(problems(d, "structure")))

    def test_tables_lists_and_role_map(self):
        d = sample(1, link=False)
        autotagged(d)
        t = acc.Tree(d)
        th = [n for n in t.nodes if n.type == "TH"]
        self.assertEqual(len(th), 3)
        for n in th:
            d.xref_set_key(n.num, "A", "null")
        self.assertIn("doesn't say whether it heads a column or a row",
                      texts_of(problems(d, "structure")))
        for n in th:
            d.xref_set_key(n.num, "S", "/TD")
        self.assertIn("A table has no header cells", texts_of(problems(d, "structure")))
        li = next(n for n in t.nodes if n.type == "LI")
        lst = li.parent
        d.xref_set_key(li.num, "S", "/P")
        self.assertIn("A list holds something other than list items",
                      texts_of(problems(d, "structure")))
        d.xref_set_key(lst.num, "A", "<</O /List /ListNumbering /Bullets>>")
        self.assertIn("numbering (Bullets) isn't one", texts_of(problems(d, "structure")))
        root = acc.Tree(d).root
        rx = pymupdf.mupdf.pdf_to_num(pymupdf.mupdf.pdf_dict_gets(
            pymupdf.mupdf.pdf_dict_gets(pymupdf.mupdf.pdf_trailer(
                pymupdf._as_pdf_document(d)), "Root"), "StructTreeRoot"))
        self.assertTrue(root is not None and rx)
        d.xref_set_key(rx, "RoleMap", "<</Para /P /Loop1 /Loop2 /Loop2 /Loop1 /Odd /Thing "
                                      "/P /Span>>")
        found = texts_of(problems(d, "structure"))
        self.assertIn("The standard tag P is mapped to Span", found)
        self.assertIn("Loop1 is mapped in a circle", found)
        self.assertIn("Odd doesn't map to a standard tag", found)
        self.assertNotIn("Para", found)

    def test_annotations_fields_and_tab_order(self):
        d = hand_tagged()
        p = d[0]
        d.xref_set_key(p.xref, "Tabs", "null")
        link = p.annot_xrefs()[0][0]
        d.xref_set_key(link, "Contents", "null")
        w = pymupdf.Widget()
        w.field_name = "phone_number"
        w.field_type = pymupdf.PDF_WIDGET_TYPE_TEXT
        w.rect = pymupdf.Rect(150, 300, 300, 318)
        p.add_widget(w)
        p.add_text_annot((400, 400), "")
        found = problems(d, "annots") + problems(d, "forms")
        text = texts_of(found)
        self.assertIn("tab order", text)
        self.assertIn("A link has no description", text)
        self.assertIn("A form field isn't tagged as a Form", text)
        self.assertIn("A form field has no tooltip", text)
        self.assertIn("isn't tagged as an Annot", text)
        self.assertIn("has no text describing it", text)
        self.assertEqual({p.fix for p in found} - {None}, {"tabs", "links", "tooltips"})
        # a link outside the tags
        d.xref_set_key(link, "StructParent", "null")
        self.assertIn("A link isn't tagged as a Link", texts_of(problems(d, "annots")))

    def test_security_bookmarks_and_fonts(self):
        d = sample(21, link=False)
        self.assertIn("21 pages and no bookmarks", texts_of(problems(d, "document")))
        d.set_toc([[1, "Start", 1]])
        self.assertNotIn("bookmarks", texts_of(problems(d, "document")))
        folder = tempfile.mkdtemp()
        path = os.path.join(folder, "locked.pdf")
        sample(1).save(path, encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="o",
                       user_pw="", permissions=pymupdf.PDF_PERM_PRINT)
        locked = pymupdf.open(path)
        self.assertIn("don't let assistive technology read",
                      texts_of(problems(locked, "document")))
        fonts = problems(sample(1), "fonts")
        self.assertEqual(sorted(p.text for p in fonts),
                         ["Font Helvetica isn't embedded.", "Font Helvetica-Bold isn't "
                                                            "embedded."])
        self.assertTrue(all(p.fix == "fonts" for p in fonts))

    def test_invisible_text_fonts_and_text_without_unicode(self):
        d = pymupdf.open()
        p = d.new_page()
        p.insert_text((72, 72), "recognized words", fontsize=12, render_mode=3)
        self.assertEqual(problems(d, "fonts"), [])     # (invisible text: not required)
        # a Type 3 font without ToUnicode: its text can't be read as letters
        f = d.get_new_xref()
        proc = d.get_new_xref()
        d.update_object(proc, "<<>>")
        d.update_stream(proc, b"500 0 0 0 500 500 d1 0 0 500 500 re f")
        d.update_object(f, "<</Type /Font /Subtype /Type3 /FontBBox [0 0 500 500] "
                           "/FontMatrix [0.001 0 0 0.001 0 0] /CharProcs <</a %d 0 R>> "
                           "/Encoding <</Differences [97 /a]>> /FirstChar 97 /LastChar 97 "
                           "/Widths [500]>>" % proc)
        add_resource(d, p, "Font", "T3", f)
        x = p.get_contents()[0]
        d.update_stream(x, d.xref_stream(x) + b"\nBT /T3 12 Tf 72 300 Td (aaa) Tj ET\n")
        self.assertIn("no Unicode mapping", texts_of(problems(d, "fonts")))


class Fixes(unittest.TestCase):
    def test_title_language_tabs_pdfua(self):
        d = sample(2)
        self.assertEqual(acc.suggested_title(d), "Accessible Documents")
        acc.set_title(d, "My report")
        acc.set_language(d, "es-ES")
        self.assertEqual(acc.set_tabs(d), 2)
        acc.set_pdfua(d)
        cat = d.pdf_catalog()
        self.assertEqual(d.metadata["title"], "My report")
        self.assertIn('<rdf:li xml:lang="x-default">My report</rdf:li>', d.get_xml_metadata())
        self.assertEqual(d.xref_get_key(cat, "ViewerPreferences/DisplayDocTitle"),
                         ("bool", "true"))
        self.assertEqual(d.xref_get_key(cat, "Lang"), ("string", "es-ES"))
        self.assertEqual(acc.get_language(d), "es-ES")
        self.assertTrue(all(d.xref_get_key(p.xref, "Tabs") == ("name", "/S") for p in d))
        self.assertIn("<pdfuaid:part>1</pdfuaid:part>", d.get_xml_metadata())
        # again: replaced, not added twice
        acc.set_title(d, "Other & <title>")
        acc.set_pdfua(d)
        xmp = d.get_xml_metadata()
        self.assertEqual(xmp.count("<dc:title>"), 1)
        self.assertEqual(xmp.count("pdfuaid:part"), 2)          # (its opening and closing)
        self.assertIn("Other &amp; &lt;title&gt;", xmp)
        found = texts_of(problems(d, "document"))
        for gone in ("no title", "language isn't set", "DisplayDocTitle", "PDF/UA"):
            self.assertNotIn(gone, found)

    def test_xmp_of_another_program_keeps_its_parts(self):
        d = sample(1)
        d.set_xml_metadata('<?xpacket begin="" id="W5M0MpCehiHzreSzNTczkc9d"?>'
                           '<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF xmlns:rdf="http://'
                           'www.w3.org/1999/02/22-rdf-syntax-ns#"><rdf:Description rdf:about'
                           '="" xmlns:pdfaid="http://www.aiim.org/pdfa/ns/id/" pdfaid:part="2"'
                           ' pdfaid:conformance="B"/></rdf:RDF></x:xmpmeta>'
                           '<?xpacket end="w"?>')
        acc.set_title(d, "Kept")
        xmp = d.get_xml_metadata()
        self.assertIn('pdfaid:part="2"', xmp)
        self.assertIn(">Kept</rdf:li>", xmp)

    def test_field_tooltips_from_their_labels(self):
        d = pymupdf.open()
        p = d.new_page()
        p.insert_text((72, 100), "Full name:", fontsize=11)
        p.insert_text((72, 160), "Email address", fontsize=11)
        for name, rect in (("f1", (150, 88, 350, 104)), ("f2", (72, 166, 300, 182)),
                           ("zip_code", (400, 400, 450, 416))):
            w = pymupdf.Widget()
            w.field_name = name
            w.field_type = pymupdf.PDF_WIDGET_TYPE_TEXT
            w.rect = pymupdf.Rect(rect)
            p.add_widget(w)
        found = {f["name"]: f for f in acc.fields(d)}
        self.assertEqual(found["f1"]["label"], "Full name")          # (left of it)
        self.assertEqual(found["f2"]["label"], "Email address")      # (above it)
        self.assertEqual(found["zip_code"]["label"], "Zip code")     # (its name)
        acc.set_tooltips(d, {f["field"]: f["label"] for f in found.values()})
        for f in found.values():
            self.assertEqual(d.xref_get_key(f["field"], "TU")[1], f["label"])
        self.assertEqual(problems(d, "forms"), [])

    def test_link_descriptions(self):
        d = sample(1)
        found = acc.links(d)
        self.assertEqual([f["suggestion"] for f in found], ["example.com"])
        p = d[0]
        p.insert_link({"kind": pymupdf.LINK_GOTO, "page": 0,
                       "from": pymupdf.Rect(500, 700, 520, 720)})
        p.insert_link({"kind": pymupdf.LINK_URI, "uri": "https://kanzonas.org",
                       "from": pymupdf.Rect(500, 600, 520, 620)})
        sugg = sorted(f["suggestion"] for f in acc.links(d))
        self.assertEqual(sugg, ["Go to page 1", "example.com", "https://kanzonas.org"])
        acc.set_contents(d, {f["xref"]: f["suggestion"] for f in acc.links(d)})
        for f in acc.links(d):
            self.assertEqual(f["contents"], f["suggestion"])
        self.assertNotIn("link has no description", texts_of(problems(d, "annots")))

    def test_alt_text_goes_into_the_right_figure(self):
        d = sample(2)
        autotagged(d)
        figs = acc.figures(d)
        self.assertEqual([f["page"] for f in figs], [0, 1])
        self.assertTrue(all(f["box"] is not None and abs(f["box"].width - 120) < 1 and
                            abs(f["box"].height - 80) < 1 for f in figs))
        acc.set_alt(d, figs[1]["num"], "A red rectangle")
        t = acc.Tree(d)
        by = {n.num: n for n in t.nodes}
        self.assertEqual(by[figs[1]["num"]].alt, "A red rectangle")
        self.assertIsNone(by[figs[0]["num"]].alt)
        self.assertEqual(by[figs[1]["num"]].type, "Figure")
        self.assertEqual(by[figs[1]["num"]].page, 1)
        alt = [p for p in problems(d, "structure") if p.fix == "alt"]
        self.assertEqual([p.page for p in alt], [0])

    def test_a_figure_made_decorative(self):
        d = sample(1)
        autotagged(d)
        before = renders(d)
        fig = acc.figures(d)[0]
        acc.make_decorative(d, fig["num"])
        t = acc.Tree(d)
        self.assertNotIn(fig["num"], [n.num for n in t.nodes])
        self.assertEqual(acc.figures(d), [])
        data = d[0].read_contents()
        self.assertNotIn(b"/Figure", data)
        self.assertEqual(problems(d, "content"), [])
        self.assertEqual(renders(d), before)
        # its parent tree entry is gone
        k = int(d.xref_get_key(d[0].xref, "StructParents")[1])
        arr = pymupdf.mupdf.pdf_resolve_indirect(t.parent_tree()[k])
        nulls = [i for i in range(pymupdf.mupdf.pdf_array_len(arr))
                 if pymupdf.mupdf.pdf_is_null(pymupdf.mupdf.pdf_array_get(arr, i))]
        self.assertEqual(len(nulls), 1)

    def test_mark_artifacts_from_edit_objects(self):
        from kanzonas import page_objects
        # untagged: wrapped in /Artifact
        d = sample(1, link=False)
        page = d[0]
        objs = page_objects.Objects(page)
        pic = next(it for it in objs.items if it["kind"] == "picture")
        before = renders(d)
        self.assertEqual(acc.mark_artifacts(page, [(pic["obj"]["start"],
                                                    pic["obj"]["end"])]), 1)
        data = d[0].read_contents()
        k = data.find(b"/Artifact BMC")
        self.assertGreater(k, 0)
        self.assertIn(b"Do", data[k:k + 80])
        self.assertEqual(renders(d), before)
        # tagged: the picture alone in its Figure: the sequence becomes an artifact and the
        # element leaves the tree
        d = sample(1, link=False)
        autotagged(d)
        page = d[0]
        objs = page_objects.Objects(page)
        pic = next(it for it in objs.items if it["kind"] == "picture")
        acc.mark_artifacts(page, [(pic["obj"]["start"], pic["obj"]["end"])])
        self.assertEqual(acc.figures(d), [])
        self.assertEqual(problems(d, "content"), [])

    def test_embed_fonts(self):
        d = sample(1)
        before = renders(d)
        self.assertEqual(acc.embed_fonts(d), 2)
        self.assertEqual(problems(d, "fonts"), [])
        self.assertEqual(renders(d), before)
        self.assertEqual(texts(pymupdf.open("pdf", d.tobytes())), texts(sample(1)))


# ---- auto-tag --------------------------------------------------------------------------------
EXPECTED_FIRST = [
    "H1", "H2", "P", "H3", ("L", [("LI", ["Lbl", "LBody"])] * 3), "Figure",
    ("Table", [("TR", ["TH"] * 3)] + [("TR", ["TD"] * 3)] * 2), ("P", ["Link"])]
EXPECTED_OTHER = EXPECTED_FIRST[1:]


def _shape(e):
    if isinstance(e, str):
        return (e, [])
    t, kids = e
    return (t, [_shape(k) for k in kids])


def expected(pages):
    out = []
    for i in range(pages):
        out += [_shape(e) for e in (EXPECTED_FIRST if i == 0 else EXPECTED_OTHER)]
    return [("Document", out)]


def consistent(test, doc):
    """Every MCID on every page is in the ParentTree, pointing at the element that holds it,
    and the other way round; every annotation's StructParent points at its element."""
    t = acc.Tree(doc)
    pt = t.parent_tree()
    for i in range(doc.page_count):
        page = doc[i]
        r = autotag.PageReader(page).read()
        kind, val = doc.xref_get_key(page.xref, "StructParents")
        test.assertEqual(kind, "int")
        arr = pymupdf.mupdf.pdf_resolve_indirect(pt[int(val)])
        refs = [pymupdf.mupdf.pdf_array_get(arr, k) for k in
                range(pymupdf.mupdf.pdf_array_len(arr))]
        held = {mc: n.num for n in t.nodes for pg, mc in n.mcids if pg == i}
        test.assertEqual(sorted(held), sorted(r.mcids))
        test.assertEqual(sorted(held), list(range(len(refs))))
        for mc, num in held.items():
            test.assertEqual(pymupdf.mupdf.pdf_to_num(refs[mc]), num)
        for x, _t, _id in page.annot_xrefs():
            node = t.annot_node(x)
            test.assertIsNotNone(node)
            test.assertIn(x, node.objrs)
        # every piece of content is tagged or an artifact
        for p in r.pieces:
            test.assertTrue(any(k in ("mcid", "artifact") for k, _m, _s in p.mc),
                            (i, p.kind, r.data[p.start:p.end][:60]))


class AutoTag(unittest.TestCase):
    def test_the_sample(self):
        d = sample(3)
        before_text, before_pixels = texts(d), renders(d, dpi=100)
        plans = autotagged(d)
        self.assertEqual(tree_of(d), expected(3))
        self.assertEqual(autotag.counts(plans), {"H": 7, "P": 6, "L": 3, "Table": 3,
                                                 "Figure": 3, "Annot": 3})
        self.assertEqual(texts(d), before_text)
        self.assertEqual(renders(d, dpi=100), before_pixels)
        consistent(self, d)
        t = acc.Tree(d)
        # headings by size, not skipped; the header and page numbers are artifacts
        heads = [n.type for n in t.nodes if n.type.startswith("H")]
        self.assertEqual(heads, ["H1", "H2", "H3", "H2", "H3", "H2", "H3"])
        for i in range(3):
            data = d[i].read_contents()
            self.assertEqual(data.count(b"/Subtype /Header"), 1)
            self.assertEqual(data.count(b"/Subtype /Footer"), 1)
        # the table's first row are headers of their columns
        th = [n for n in t.nodes if n.type == "TH"]
        self.assertTrue(th and all(n.attrs.get("Scope") == "Column" for n in th))
        lists = [n for n in t.nodes if n.type == "L"]
        self.assertTrue(all(n.attrs.get("ListNumbering") == "Disc" for n in lists))
        # the figure has its box; the catalog and pages what PDF/UA asks
        figs = [n for n in t.nodes if n.type == "Figure"]
        self.assertTrue(all("BBox" in n.attrs for n in figs))
        cat = d.pdf_catalog()
        self.assertEqual(d.xref_get_key(cat, "MarkInfo/Marked"), ("bool", "true"))
        self.assertEqual(d.xref_get_key(cat, "Lang"), ("string", "en-US"))
        self.assertTrue(all(d.xref_get_key(p.xref, "Tabs") == ("name", "/S") for p in d))
        # what the check still finds: alt text, link descriptions, title, fonts
        left = {p.fix for p in problems(d)}
        self.assertEqual(left, {"alt", "links", "title", "fonts", "pdfua"})
        # saved and opened again: the same
        d2 = pymupdf.open("pdf", d.tobytes(garbage=3, deflate=True))
        self.assertEqual(tree_of(d2), expected(3))
        consistent(self, d2)
        self.assertEqual(texts(d2), before_text)

    def test_the_text_of_each_element(self):
        d = sample(2)
        plans = autotag.make_plans(d)
        labels = [(e.type, e.label) for e in plans[0].elems]
        self.assertEqual(labels[:4], [("H1", "Accessible Documents"), ("H2", "Section 1"),
                                      ("P", PARA), ("H3", "Details")])
        lst = plans[0].elems[4]
        self.assertEqual([li.kids[1].label.split(" ", 1)[1] for li in lst.kids],
                         ["First point", "Second point", "Third point"])

    def test_with_all_fixes_nothing_is_left(self):
        d = sample(2)
        autotagged(d)
        acc.set_title(d, acc.suggested_title(d))
        acc.embed_fonts(d)
        acc.set_contents(d, {f["xref"]: f["suggestion"] for f in acc.links(d)})
        for f in acc.figures(d):
            acc.set_alt(d, f["num"], "A red rectangle")
        acc.set_pdfua(d)
        self.assertEqual(problems(d), [], texts_of(problems(d)))

    def test_columns_are_read_one_after_the_other(self):
        d = pymupdf.open()
        p = d.new_page(width=612, height=792)
        p.insert_text((72, 60), "Two Columns", fontname="hebo", fontsize=20)
        left = " ".join("left%d" % i for i in range(60))
        right = " ".join("right%d" % i for i in range(60))
        p.insert_textbox(pymupdf.Rect(72, 80, 290, 300), left, fontsize=10)
        p.insert_textbox(pymupdf.Rect(320, 80, 540, 300), right, fontsize=10)
        plans = autotag.make_plans(d)
        labels = [e.label.split()[0] for e in plans[0].elems]
        self.assertEqual(labels, ["Two", "left0", "right0"])

    def test_a_link_inside_a_line_splits_its_text(self):
        d = pymupdf.open()
        p = d.new_page()
        p.insert_text((72, 100), "Visit our site for more.", fontsize=12)
        r = p.search_for("our site")[0]
        p.insert_link({"kind": pymupdf.LINK_URI, "uri": "https://example.com", "from": r})
        autotagged(d)
        t = acc.Tree(d)
        para = next(n for n in t.nodes if n.type == "P")
        self.assertEqual([k.type for k in para.kids], ["Link"])
        self.assertEqual(len(para.mcids), 2)        # before and after the link
        self.assertEqual(len(para.kids[0].mcids), 1)
        self.assertEqual(texts(d)[0].split(), "Visit our site for more.".split())
        consistent(self, d)
        # the link's words are its own marked content
        data = d[0].read_contents()
        k = data.find(b"/Link <</MCID")
        self.assertIn(bytes("our site".encode().hex(), "ascii"), data[k:k + 120])

    def test_a_rotated_page_and_a_scan_with_recognized_text(self):
        d = sample(2, link=False)
        d[1].set_rotation(90)
        p = d.new_page()
        p.insert_image(p.rect, stream=png(100, 130, (240, 240, 240)))
        p.insert_text((72, 100), "Scanned words read by OCR", fontsize=12, render_mode=3)
        before = renders(d)
        plans = autotagged(d)
        self.assertEqual(renders(d), before)
        consistent(self, d)
        kinds = ["H2", "P", "H3", "L", "Figure", "Table", "P"]
        self.assertEqual([e.type for e in plans[1].elems], kinds)
        shapes = tree_of(d)[0][1]
        # the scan: its words a paragraph, the picture behind them an artifact
        self.assertEqual(shapes[-1], ("P", []))
        self.assertIn(b"/Artifact BMC", d[2].read_contents())

    def test_text_split_inside_one_operator(self):
        """A bullet and its words in one string, a table row in one TJ: split between
        characters, drawn the same."""
        d = pymupdf.open()
        p = d.new_page()
        x = p.get_contents()
        p.insert_text((72, 72), "x", fontsize=1)       # (resources for helv)
        content = (b"BT /helv 11 Tf 72 700 Td (\x95 First item) Tj 0 -16 Td (\x95 Second "
                   b"item) Tj 0 -16 Td (\x95 Third item) Tj ET\n")
        del x
        xr = p.get_contents()[0]
        d.update_stream(xr, content)
        before = renders(d)
        autotagged(d)
        self.assertEqual(renders(d), before)
        t = acc.Tree(d)
        self.assertEqual([n.type for n in t.nodes][:5], ["Document", "L", "LI", "Lbl",
                                                         "LBody"])
        consistent(self, d)
        data = d[0].read_contents()
        self.assertIn(b"/Lbl <</MCID 0>> BDC", data)

    def test_tagged_documents_are_left_alone(self):
        d = hand_tagged()
        self.assertTrue(autotag.is_tagged(d))
        self.assertFalse(autotag.is_tagged(sample(1)))

    def test_reading_order_helper(self):
        class It:
            def __init__(self, box, tall=False):
                self.box, self.tall = box, tall
        title = It((50, 10, 550, 30))
        a1, a2 = It((50, 50, 280, 150, ), True), It((50, 160, 280, 300), True)
        b1, b2 = It((320, 50, 550, 200), True), It((320, 210, 550, 300), True)
        foot = It((50, 320, 550, 340))
        order = autotag.reading_order([b2, foot, a2, title, b1, a1])
        self.assertEqual(order, [title, a1, a2, b1, b2, foot])
        # one-line rows of a form side by side: row by row
        r1 = [It((50, 10, 100, 20)), It((200, 10, 250, 20))]
        r2 = [It((50, 30, 100, 40)), It((200, 30, 250, 40))]
        self.assertEqual(autotag.reading_order(r2 + r1), [r1[0], r1[1], r2[0], r2[1]])


# ---- in the app: one undo step ----------------------------------------------------------
class InTheApp(unittest.TestCase):
    def window(self, doc):
        from kanzonas.main_window import MainWindow
        folder = tempfile.mkdtemp()
        path = os.path.join(folder, "a.pdf")
        doc.save(path)
        w = MainWindow()
        w.show()
        w.open_file(path)
        APP.processEvents()
        self.addCleanup(lambda: (setattr(w, "_close_confirmed", True), w.close()))
        return w, w.view()

    def test_the_menu(self):
        from kanzonas.main_window import MainWindow
        w = MainWindow()
        self.addCleanup(lambda: (setattr(w, "_close_confirmed", True), w.close()))
        doc_menu = next(a.menu() for a in w.menuBar().actions() if a.text() == "&Document")
        sub = next(a.menu() for a in doc_menu.actions() if a.text() == "&Accessibility")
        texts_ = [a.text() for a in sub.actions() if not a.isSeparator()]
        self.assertEqual(texts_, ["Check &accessibility...", "Auto-&tag...", "Alt te&xt...",
                                  "&Reading order...", "Title and &language...", "Form field t&ooltips...",
                                  "Lin&k descriptions...", "Ta&b order follows the tags",
                                  "Mark as &decorative", "&Embed fonts",
                                  "Identify as PDF/&UA..."])

    def test_auto_tag_is_one_undo_step(self):
        from tests.battery_random import canon
        from kanzonas import accessibility_ui as ui
        w, v = self.window(sample(2))
        start = canon(v._snapshot())
        pixels = [v.doc[i].get_pixmap(dpi=50).samples for i in range(2)]

        def accept(dlg):
            dlg.title.setText("The title")
            return QDialog.Accepted
        with mock.patch.object(ui.AutoTagDialog, "exec", accept), \
                mock.patch.object(QMessageBox, "information", lambda *a, **k: None):
            self.assertTrue(ui.auto_tag(w, v))
        self.assertTrue(autotag.is_tagged(v.doc))
        self.assertEqual(v.doc.metadata["title"], "The title")
        self.assertEqual(tree_of(v.doc), expected(2))
        self.assertEqual([v.doc[i].get_pixmap(dpi=50).samples for i in range(2)], pixels)
        tagged = canon(v._snapshot())
        self.assertEqual(len(v._undo), 1)
        v.undo()
        self.assertEqual(canon(v._snapshot()), start)
        self.assertFalse(autotag.is_tagged(v.doc))
        v.redo()
        self.assertEqual(canon(v._snapshot()), tagged)
        self.assertEqual(tree_of(v.doc), expected(2))

    def test_check_window_and_its_fixes(self):
        from kanzonas import accessibility_ui as ui
        w, v = self.window(sample(1))
        dlg = ui.ReportDialog(w, w, v, ui.run_check(w, v))
        self.addCleanup(dlg.deleteLater)
        top = [dlg.tree.topLevelItem(i).text(0) for i in range(dlg.tree.topLevelItemCount())]
        self.assertTrue(top[0].startswith("The document ("))
        self.assertEqual(top[-1], "Check these yourself")
        self.assertIn("PAC 2024", dlg.info.text())
        # the title line: Fix opens Title and language
        item = None
        for i in range(dlg.tree.topLevelItemCount()):
            t = dlg.tree.topLevelItem(i)
            for k in range(t.childCount()):
                if t.child(k).data(0, 0x0100).fix == "title":
                    item = t.child(k)
        dlg.tree.setCurrentItem(item)
        self.assertTrue(dlg.fix_btn.isEnabled())

        def accept(d):
            d.title.setText("Fixed title")
            return QDialog.Accepted
        with mock.patch.object(ui.TitleDialog, "exec", accept):
            dlg._fix()
        self.assertEqual(v.doc.metadata["title"], "Fixed title")
        self.assertNotIn("no title", texts_of(dlg.problems))
        self.assertEqual(len(v._undo), 1)

    def test_alt_text_window(self):
        from kanzonas import accessibility_ui as ui
        d = sample(2)
        autotagged(d)
        w, v = self.window(d)

        def fill(dlg):
            for _ in range(5):
                APP.processEvents()
            self.assertFalse(dlg.list.item(0).icon().isNull())      # (thumbnails drawn)
            dlg.list.setCurrentRow(0)
            dlg.text.setPlainText("A red rectangle")
            dlg.list.setCurrentRow(1)
            dlg.decorative.setChecked(True)
            return QDialog.Accepted
        with mock.patch.object(ui.AltTextDialog, "exec", fill):
            ui.alt_text(w, v)
        figs = acc.figures(v.doc)
        self.assertEqual([(f["page"], f["alt"]) for f in figs], [(0, "A red rectangle")])
        self.assertEqual(len(v._undo), 1)
        v.undo()
        self.assertEqual(len(acc.figures(v.doc)), 2)

    def test_tooltips_links_tabs_and_decorative(self):
        from kanzonas import accessibility_ui as ui
        d = sample(1)
        p = d[0]
        p.insert_text((300, 700), "Your name:", fontsize=11)
        wd = pymupdf.Widget()
        wd.field_name = "name"
        wd.field_type = pymupdf.PDF_WIDGET_TYPE_TEXT
        wd.rect = pymupdf.Rect(370, 688, 500, 704)
        p.add_widget(wd)
        w, v = self.window(d)
        with mock.patch.object(ui.ReviewDialog, "exec", lambda dlg: QDialog.Accepted):
            ui.field_tooltips(w, v)
            ui.link_descriptions(w, v)
        ui.tab_order(w, v)
        self.assertEqual(len(v._undo), 3)
        self.assertEqual(problems(v.doc, "forms"), [])
        self.assertNotIn("link has no description", texts_of(problems(v.doc, "annots")))
        self.assertNotIn("tab order", texts_of(problems(v.doc, "annots")))
        # Mark as decorative, from the Edit objects selection
        objs = v.content_objects(0)
        pic = [it for it in objs.items if it["kind"] == "picture"]
        v.select_objects(0, pic)
        APP.processEvents()
        self.assertTrue(w.acc_actions["mark_decorative"].isEnabled())
        ui.mark_decorative(w, v)
        self.assertEqual(len(v._undo), 4)
        self.assertIn(b"/Artifact BMC", v.doc[0].read_contents())

    def test_reading_order_window(self):
        from kanzonas import accessibility_ui as ui
        d = sample(1)
        autotagged(d)
        w, v = self.window(d)
        before = [it["type"] for it in acc.page_order(v.doc, 0)]
        self.assertEqual(before, ["P", "H1", "H2", "P", "H3", "L", "Figure", "Table", "P"])

        def swap(dlg):
            self.assertFalse(dlg.page.pixmap().isNull())        # (the page, numbered)
            dlg.list.setCurrentRow(7)                           # the table before the figure
            dlg._move(-1)
            return QDialog.Accepted
        with mock.patch.object(ui.ReadingOrderDialog, "exec", swap):
            ui.reading_order(w, v)
        after = [it["type"] for it in acc.page_order(v.doc, 0)]
        self.assertEqual(after, ["P", "H1", "H2", "P", "H3", "L", "Table", "Figure", "P"])
        self.assertEqual(tree_of(v.doc)[0][1][6][0], "Table")
        self.assertEqual(len(v._undo), 1)
        v.undo()
        self.assertEqual([it["type"] for it in acc.page_order(v.doc, 0)], before)


if __name__ == "__main__":
    unittest.main()
