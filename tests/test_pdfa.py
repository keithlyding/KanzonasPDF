"""File > Save as PDF/A and File > Check PDF/A (kanzonas/pdfa.py, pdfa_ui.py).

A "messy" document with most of what keeps a PDF from being PDF/A (fonts not embedded, CMYK
colors without a profile, scripts, a Launch link, a hidden markup, a markup that doesn't
print, a form left to the viewer to draw, a picture set to be smoothed, a blend mode PDF/A
doesn't know, LZW compression, PDF 2.0, an attached file) is saved as PDF/A: the copy has
what PDF/A wants (output intent, XMP identification, embedded fonts, no encryption, appearances
and the Print flag, no JavaScript), the check finds nothing left in it, and it looks the same.

veraPDF (the PDF Association's validator) passed the copies made here when this was written
(PDF/A-3b with the attachment, PDF/A-2b without); the tests don't need it.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_pdfa
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
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import pdfa  # noqa: E402


def _lzw(data):
    """data LZW-encoded the simplest way (9-bit codes, each byte a literal; short data)."""
    codes = [256] + list(data) + [257]
    bits = "".join(format(c, "09b") for c in codes)
    bits += "0" * (-len(bits) % 8)
    return bytes(int(bits[i:i + 8], 2) for i in range(0, len(bits), 8))


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


def messy_pdf(attachment=True, version20=True):
    d = pymupdf.open()
    p = d.new_page()
    p.insert_text((50, 80), "Hello Helvetica äöü €", fontname="helv",
                  fontsize=14)
    p.insert_text((50, 110), "Times Roman", fontname="tiro", fontsize=14)
    p.insert_text((50, 140), "Courier bold", fontname="cobo", fontsize=14)
    p.insert_text((50, 170), "abgd", fontname="symb", fontsize=14)
    # an Arial that isn't embedded (as Word writes it): TrueType, WinAnsi, its widths
    bold = pymupdf.Font("hebo")
    widths = " ".join(str(round(bold.glyph_advance(c) * 1000)) for c in range(32, 127))
    font = d.get_new_xref()
    d.update_object(font, "<< /Type /Font /Subtype /TrueType /BaseFont /Arial,Bold "
                          "/Encoding /WinAnsiEncoding /FirstChar 32 /LastChar 126 "
                          "/Widths [%s] >>" % widths)
    add_resource(d, p, "Font", "FArial", font)
    # CMYK: a drawing, and a picture in CMYK set to be smoothed
    p.draw_rect(pymupdf.Rect(300, 50, 400, 150), color=(0, 1, 0, 0), fill=(0.2, 0, 1, 0))
    pix = pymupdf.Pixmap(pymupdf.csCMYK, pymupdf.IRect(0, 0, 8, 8), False)
    pix.set_rect(pix.irect, (0, 200, 200, 0))
    p.insert_image(pymupdf.Rect(300, 200, 360, 260), pixmap=pix)
    img_xref = [i[0] for i in p.get_images()][0]
    d.xref_set_key(img_xref, "Interpolate", "true")
    # a blend mode PDF/A doesn't know, a transfer function, LZW, more text in Arial
    gs = d.get_new_xref()
    d.update_object(gs, "<< /Type /ExtGState /BM /Weird /TR /Identity /CA 0.5 >>")
    add_resource(d, p, "ExtGState", "GSx", gs)
    form = d.get_new_xref()
    d.update_object(form, "<< /Type /XObject /Subtype /Form /BBox [0 0 100 100] "
                          "/Resources << >> >>")
    d.update_stream(form, b"0 0 1 rg 10 10 50 50 re f", compress=False)
    lzw = _lzw(b"0 0 1 rg 10 10 50 50 re f")
    d.update_stream(form, lzw, new=False, compress=False)
    d.xref_set_key(form, "Filter", "/LZWDecode")
    d.xref_set_key(form, "Length", str(len(lzw)))
    add_resource(d, p, "XObject", "Fx", form)
    extra = d.get_new_xref()
    d.update_object(extra, "<<>>")
    d.update_stream(extra, b"q /GSx gs 0 1 0 rg 50 400 100 50 re f Q "
                           b"q 1 0 0 1 400 400 cm /Fx Do Q "
                           b"BT /FArial 14 Tf 50 230 Td (Arial Bold) Tj ET")
    d.xref_set_key(p.xref, "Contents", "[%s]" % " ".join(
        "%d 0 R" % x for x in p.get_contents() + [extra]))
    # markups: one that doesn't print, one hidden; a Launch link; a form drawn by the viewer
    a = p.add_text_annot((300, 300), "a note")
    a.set_flags(0)
    a.update()
    hidden = p.add_rect_annot(pymupdf.Rect(400, 300, 450, 350))
    hidden.set_flags(pymupdf.PDF_ANNOT_IS_HIDDEN)
    hidden.update()
    p.add_highlight_annot(pymupdf.Rect(50, 65, 150, 85))
    p.insert_link({"kind": pymupdf.LINK_LAUNCH, "from": pymupdf.Rect(50, 300, 150, 320),
                   "file": "calc.exe"})
    w = pymupdf.Widget()
    w.field_type = pymupdf.PDF_WIDGET_TYPE_TEXT
    w.field_name = "name"
    w.field_value = "Ana"
    w.rect = pymupdf.Rect(50, 500, 250, 520)
    w.script = "app.alert('typed');"
    p.add_widget(w)
    cat = d.pdf_catalog()
    d.xref_set_key(cat, "AcroForm/NeedAppearances", "true")
    js = d.get_new_xref()
    d.update_object(js, "<< /S /JavaScript /JS (app.alert('hi');) >>")
    d.xref_set_key(cat, "OpenAction", "%d 0 R" % js)
    d.xref_set_key(cat, "AA", "<< /WC << /S /JavaScript /JS (1;) >> >>")
    if attachment:
        d.embfile_add("data.csv", b"a,b\n1,2\n", filename="data.csv")
    d.set_metadata({"title": "Test <doc> & co", "author": "Ana",
                    "creationDate": "D:20240102030405+01'00'"})
    if version20:
        pymupdf._as_pdf_document(d).m_internal.version = 20
    return d.tobytes()


def render(doc, i=0):
    return doc[i].get_pixmap(dpi=40, annots=True)


def differing(a, b):
    """How many samples of two pixmaps differ by more than a little."""
    sa, sb = a.samples, b.samples
    return sum(1 for x, y in zip(sa, sb) if abs(x - y) > 24)


class Convert(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp()
        cls.src = messy_pdf()
        cls.path = os.path.join(cls.dir, "out.pdf")
        cls.before = pdfa.check(pymupdf.open(stream=cls.src))
        cls.result = pdfa.convert(cls.src, cls.path)
        cls.out = pymupdf.open(cls.path)
        with open(cls.path, "rb") as f:
            cls.raw = f.read()

    def objects(self):
        return [self.out.xref_object(x) for x in range(1, self.out.xref_length())]

    def test_the_check_finds_what_is_wrong(self):
        texts = " | ".join(p.text for p in self.before)
        for words in ("isn't marked as PDF/A", "no output intent", "Helvetica isn't embedded",
                      "Arial,Bold isn't embedded", "JavaScript", "Launch", "CMYK",
                      "isn't set to print", "hidden", "LZW", "blend mode", "Interpolate",
                      "PDF 2.0", "NeedAppearances", "data.csv"):
            self.assertIn(words, texts)
        self.assertTrue(all(p.fixable for p in self.before), [p for p in self.before
                                                              if not p.fixable])

    def test_nothing_left_and_pdfa_3_for_the_attachment(self):
        self.assertEqual(self.result["remaining"], [])
        self.assertEqual(self.result["part"], 3)
        self.assertEqual(pdfa.check(self.out), [])

    def test_header_id_and_no_encryption(self):
        self.assertTrue(self.raw.startswith(b"%PDF-1.7\n%"))
        self.assertTrue(all(b > 127 for b in self.raw[10:14]))
        self.assertEqual(self.out.xref_get_key(-1, "ID")[0], "array")
        self.assertEqual(self.out.xref_get_key(-1, "Encrypt")[0], "null")
        self.assertFalse(self.out.is_encrypted)

    def test_output_intent_with_srgb_profile(self):
        cat = self.out.pdf_catalog()
        kind, val = self.out.xref_get_key(cat, "OutputIntents")
        self.assertEqual(kind, "array")
        oi = int(re.findall(r"(\d+) 0 R", val)[0])
        self.assertEqual(self.out.xref_get_key(oi, "S")[1], "/GTS_PDFA1")
        prof = int(self.out.xref_get_key(oi, "DestOutputProfile")[1].split()[0])
        icc = self.out.xref_stream(prof)
        self.assertEqual(icc[36:40], b"acsp")
        self.assertEqual(icc[12:20], b"mntrRGB ")
        self.assertLess(icc[8], 5)
        self.assertEqual(self.out.xref_get_key(prof, "N")[1], "3")

    def test_xmp_identification_and_properties_in_sync(self):
        xml = self.out.get_xml_metadata()
        self.assertIn("<pdfaid:part>3</pdfaid:part>", xml)
        self.assertIn("<pdfaid:conformance>B</pdfaid:conformance>", xml)
        self.assertNotRegex(xml.split("?>")[0], r"bytes=|encoding=")
        meta = self.out.metadata
        self.assertEqual(meta["title"], "Test <doc> & co")
        self.assertIn("Test &lt;doc&gt; &amp; co", xml)
        self.assertIn("<rdf:li>Ana</rdf:li>", xml)
        self.assertIn("<xmp:CreateDate>2024-01-02T03:04:05+01:00</xmp:CreateDate>", xml)
        self.assertIn(meta["producer"], xml)
        # the metadata stream isn't compressed (MuPDF leaves XMP readable)
        cat = self.out.pdf_catalog()
        mx = int(self.out.xref_get_key(cat, "Metadata")[1].split()[0])
        self.assertEqual(self.out.xref_get_key(mx, "Filter")[0], "null")

    def test_every_font_embedded_with_its_widths(self):
        fonts = self.out[0].get_fonts()
        self.assertTrue(fonts)
        for f in fonts:
            self.assertNotEqual(f[1], "n/a", f)
        names = {f[3] for f in fonts}
        self.assertIn("Helvetica", names)
        self.assertIn("Helvetica-Bold", names)          # (the Arial,Bold)
        for f in fonts:
            self.assertEqual(self.out.xref_get_key(f[0], "Subtype")[1], "/Type1")
            self.assertEqual(self.out.xref_get_key(f[0], "Widths")[0], "array")
            fd = int(self.out.xref_get_key(f[0], "FontDescriptor")[1].split()[0])
            ff = int(self.out.xref_get_key(fd, "FontFile3")[1].split()[0])
            self.assertEqual(self.out.xref_get_key(ff, "Subtype")[1], "/Type1C")

    def test_annotations_print_and_have_appearances(self):
        page = self.out[0]
        kinds = []
        for xref in [int(x) for x in re.findall(r"(\d+) 0 R",
                                                 self.out.xref_get_key(page.xref, "Annots")[1])]:
            sub = self.out.xref_get_key(xref, "Subtype")[1]
            kinds.append(sub)
            if sub == "/Popup":
                continue
            flags = int(self.out.xref_get_key(xref, "F")[1])
            self.assertTrue(flags & 4, sub)
            self.assertFalse(flags & (1 | 2 | 32 | 256), sub)
            if sub != "/Link":
                self.assertEqual(self.out.xref_get_key(xref, "AP/N")[0], "xref", sub)
                self.assertEqual(self.out.xref_get_key(xref, "AP/D")[0], "null")
        self.assertNotIn("/Square", kinds)              # the hidden one is gone
        self.assertIn("/Text", kinds)
        self.assertEqual(self.out.xref_get_key(self.out.pdf_catalog(),
                                               "AcroForm/NeedAppearances")[0], "null")

    def test_scripts_and_launch_actions_removed(self):
        text = "\n".join(self.objects())
        for word in ("/JavaScript", "/Launch", "/JS", "/AA"):
            self.assertNotIn(word, text)
        self.assertEqual(self.out.xref_get_key(self.out.pdf_catalog(), "OpenAction")[0], "null")

    def test_cmyk_has_a_profile_and_graphics_states_cleaned(self):
        text = "\n".join(self.objects())
        self.assertNotIn("/LZWDecode", text)
        self.assertNotIn("/Weird", text)
        self.assertNotIn("/TR ", text)
        self.assertNotIn("/Interpolate true", text)
        self.assertIn("/DefaultCMYK", text)
        self.assertNotRegex(text, r"/ColorSpace /DeviceCMYK")

    def test_attachment_kept_as_an_associated_file(self):
        self.assertEqual(self.out.embfile_names(), ["data.csv"])
        self.assertEqual(self.out.embfile_get("data.csv"), b"a,b\n1,2\n")
        af = self.out.xref_get_key(self.out.pdf_catalog(), "AF")
        self.assertEqual(af[0], "array")
        spec = int(re.findall(r"(\d+) 0 R", af[1])[0])
        self.assertEqual(self.out.xref_get_key(spec, "AFRelationship")[1], "/Unspecified")
        self.assertEqual(self.out.xref_get_key(spec, "EF/F/Subtype")[1], "/text/csv")

    def test_looks_the_same(self):
        src = pymupdf.open(stream=self.src)
        # (the hidden markup isn't drawn before either; the form field was left to the
        # viewer: compared without markups and fields, then the whole page loosely)
        a = src[0].get_pixmap(dpi=40, annots=False)
        b = self.out[0].get_pixmap(dpi=40, annots=False)
        self.assertEqual((a.width, a.height), (b.width, b.height))
        self.assertLess(differing(a, b), len(a.samples) * 0.001)
        self.assertLess(differing(render(src), render(self.out)), len(a.samples) * 0.01)

    def test_the_text_reads_the_same(self):
        src = pymupdf.open(stream=self.src)
        before, after = src[0].get_text().split(), self.out[0].get_text().split()
        # the Symbol text was written as "abgd" with the Latin encoding but shown as Greek
        # letters; embedded with its own encoding it also reads as what it shows
        self.assertEqual(before[8], "abgd")
        self.assertEqual(after[8], "αβγδ")
        self.assertEqual(before[:8] + before[9:], after[:8] + after[9:])


class PartTwo(unittest.TestCase):
    def test_no_attachment_gives_pdfa_2b(self):
        path = os.path.join(tempfile.mkdtemp(), "a.pdf")
        result = pdfa.convert(messy_pdf(attachment=False, version20=False), path)
        self.assertEqual(result["part"], 2)
        self.assertEqual(result["remaining"], [])
        with pymupdf.open(path) as out:
            self.assertIn("<pdfaid:part>2</pdfaid:part>", out.get_xml_metadata())
            self.assertEqual(out.xref_get_key(out.pdf_catalog(), "AF")[0], "null")

    def test_a_pdfa_attachment_keeps_pdfa_2b(self):
        inner = os.path.join(tempfile.mkdtemp(), "inner.pdf")
        pdfa.convert(messy_pdf(attachment=False), inner)
        d = pymupdf.open()
        d.new_page().insert_text((72, 72), "with a PDF/A attached", fontname="helv")
        with open(inner, "rb") as f:
            d.embfile_add("inner.pdf", f.read(), filename="inner.pdf")
        path = os.path.join(tempfile.mkdtemp(), "b.pdf")
        result = pdfa.convert(d.tobytes(), path)
        self.assertEqual(result["part"], 2)
        self.assertEqual(result["remaining"], [])


class KeepsAGoodOutputIntent(unittest.TestCase):
    def test_cmyk_intent_kept_and_rgb_gets_a_profile(self):
        d = pymupdf.open()
        p = d.new_page()
        p.draw_rect(pymupdf.Rect(50, 50, 150, 150), color=(1, 0, 0), fill=(0, 0, 1))
        p.draw_rect(pymupdf.Rect(200, 50, 300, 150), color=(0, 1, 0, 0), fill=(0, 0, 1, 0))
        prof = d.get_new_xref()
        d.update_object(prof, "<< /N 4 >>")
        d.update_stream(prof, pdfa.icc_profile("cmyk"))
        oi = d.get_new_xref()
        d.update_object(oi, "<< /Type /OutputIntent /S /GTS_PDFA1 /OutputConditionIdentifier "
                            "(CMYK) /DestOutputProfile %d 0 R >>" % prof)
        d.xref_set_key(d.pdf_catalog(), "OutputIntents", "[%d 0 R]" % oi)
        found = pdfa.check(d)
        self.assertIn("RGB colors are used without an RGB color profile.",
                      [x.text for x in found])
        self.assertNotIn("CMYK colors are used without a CMYK color profile.",
                         [x.text for x in found])
        path = os.path.join(tempfile.mkdtemp(), "k.pdf")
        result = pdfa.convert(d.tobytes(), path)
        self.assertEqual(result["remaining"], [])
        with pymupdf.open(path) as out:
            kind, val = out.xref_get_key(out.pdf_catalog(), "OutputIntents")
            oi = int(re.findall(r"(\d+) 0 R", val)[0])
            prof = int(out.xref_get_key(oi, "DestOutputProfile")[1].split()[0])
            self.assertEqual(out.xref_stream(prof)[16:20], b"CMYK")
            text = "\n".join(out.xref_object(x) for x in range(1, out.xref_length()))
            self.assertIn("/DefaultRGB", text)
            self.assertNotIn("/DefaultCMYK", text)
            self.assertEqual(differing(d[0].get_pixmap(dpi=40), out[0].get_pixmap(dpi=40)), 0)


class WhatCantBeFixed(unittest.TestCase):
    def test_a_font_without_a_copy_is_listed_with_its_page(self):
        d = pymupdf.open()
        d.new_page()
        p = d.new_page()
        font = d.get_new_xref()
        d.update_object(font, "<< /Type /Font /Subtype /TrueType /BaseFont /ComicSansMS "
                              "/Encoding /WinAnsiEncoding /FirstChar 32 /LastChar 32 "
                              "/Widths [300] >>")
        add_resource(d, p, "Font", "F9", font)
        c = d.get_new_xref()
        d.update_object(c, "<<>>")
        d.update_stream(c, b"BT /F9 12 Tf 72 72 Td ( ) Tj ET")
        d.xref_set_key(p.xref, "Contents", "%d 0 R" % c)
        found = [x for x in pdfa.check(d) if "ComicSansMS" in x.text]
        self.assertEqual(len(found), 1)
        self.assertEqual((found[0].kind, found[0].page, found[0].fixable), ("fonts", 1, False))
        path = os.path.join(tempfile.mkdtemp(), "c.pdf")
        result = pdfa.convert(d.tobytes(), path)
        left = [x for x in result["remaining"] if "ComicSansMS" in x.text]
        self.assertEqual(len(left), 1)
        self.assertEqual(left[0].page, 1)

    def test_a_huge_page_is_listed(self):
        d = pymupdf.open()
        d.new_page(width=20000, height=500)
        found = [x for x in pdfa.check(d) if x.kind == "pages"]
        self.assertEqual(len(found), 1)
        self.assertFalse(found[0].fixable)

    def test_encrypted_is_reported_and_refused(self):
        d = pymupdf.open()
        d.new_page().insert_text((72, 72), "secret")
        data = d.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="o", user_pw="u")
        enc = pymupdf.open(stream=data)
        problems = pdfa.check(enc)
        self.assertEqual([p.kind for p in problems], ["file"])
        self.assertFalse(problems[0].fixable)
        with self.assertRaises(ValueError):
            pdfa.convert(data, os.path.join(tempfile.mkdtemp(), "x.pdf"))

    def test_the_check_only_reads(self):
        d = pymupdf.open(stream=messy_pdf())
        before = [d.xref_object(x) for x in range(1, d.xref_length())]
        pdfa.check(d)
        self.assertEqual([d.xref_object(x) for x in range(1, d.xref_length())], before)
        self.assertFalse(d.is_dirty)


class Pieces(unittest.TestCase):
    def test_standard_font_names(self):
        for name, std in (("Helvetica", "Helvetica"), ("ABCDEF+Arial", "Helvetica"),
                          ("Arial,Bold", "Helvetica-Bold"), ("Arial-BoldItalicMT",
                                                             "Helvetica-BoldOblique"),
                          ("TimesNewRomanPSMT", "Times-Roman"),
                          ("TimesNewRomanPS-ItalicMT", "Times-Italic"),
                          ("CourierNew,Bold", "Courier-Bold"), ("Symbol", "Symbol")):
            self.assertEqual(pdfa.standard_font(name), std, name)
        for name in ("ArialNarrow", "Arial-Black", "Calibri", "Times-Roman,Condensed"):
            self.assertIsNone(pdfa.standard_font(name), name)

    def test_symbol_font_own_encoding(self):
        font = pymupdf.Font("symb")
        enc = pdfa.cff_builtin_encoding(font.buffer)
        self.assertEqual(pymupdf.mupdf.fz_get_glyph_name2(font.this, enc[ord("a")]), "alpha")
        self.assertEqual(pdfa.cff_builtin_encoding(pymupdf.Font("helv").buffer), "Standard")

    def test_encodings(self):
        win = pdfa.base_encoding("WinAnsiEncoding")
        self.assertEqual((win[0x27], win[0x80], win[0xE9]), ("quotesingle", "Euro", "eacute"))
        std = pdfa.base_encoding("StandardEncoding")
        self.assertEqual((std[0x27], std[0xA4], std[0xE1]), ("quoteright", "fraction", "AE"))
        self.assertEqual(pdfa.base_encoding("MacRomanEncoding")[0x8E], "eacute")

    def test_dates(self):
        self.assertEqual(pdfa._xmp_date("D:20240102030405-05'30'"), "2024-01-02T03:04:05-05:30")
        self.assertEqual(pdfa._xmp_date("D:2024"), "2024-01-01T00:00:00")
        self.assertIsNone(pdfa._xmp_date("yesterday"))

    def test_icc_profiles(self):
        for kind, space, n in (("rgb", b"RGB ", 3), ("cmyk", b"CMYK", 4)):
            data = pdfa.icc_profile(kind)
            self.assertEqual(data[16:20], space)
            self.assertEqual(data[36:40], b"acsp")


class Commands(unittest.TestCase):
    def window(self, path):
        from kanzonas.main_window import MainWindow
        w = MainWindow()
        w.show()
        w.open_file(path)
        APP.processEvents()
        self.addCleanup(lambda: (setattr(w, "_close_confirmed", True), w.close()))
        return w, w.view()

    def test_in_the_file_menu(self):
        from kanzonas.main_window import MainWindow
        w = MainWindow()
        self.addCleanup(lambda: (setattr(w, "_close_confirmed", True), w.close()))
        file_menu = w.menuBar().actions()[0].menu()
        texts = [a.text() for a in file_menu.actions()]
        self.assertIn("Save as P&DF/A...", texts)
        self.assertIn("Chec&k PDF/A...", texts)

    def test_save_as_pdfa_shows_the_copy_in_the_tab(self):
        folder = tempfile.mkdtemp()
        src = os.path.join(folder, "messy.pdf")
        original = messy_pdf()
        with open(src, "wb") as f:
            f.write(original)
        w, v = self.window(src)
        target = os.path.join(folder, "messy_PDFA.pdf")
        from kanzonas import pdfa_ui
        shown = []
        with mock.patch.object(QFileDialog, "getSaveFileName", lambda *a, **k: (target, "")), \
                mock.patch.object(pdfa_ui.ReportDialog, "exec",
                                  lambda self: shown.append(self) or 0):
            self.assertTrue(w.save_as_pdfa())
        self.assertEqual(os.path.normcase(w.view().path), os.path.normcase(target))
        self.assertEqual(w.tabs.count(), 1)
        self.assertEqual(len(shown), 1)
        with open(src, "rb") as f:
            self.assertEqual(f.read(), original)        # the original is left as it was
        self.assertEqual(pdfa.check(w.view().doc), [])

    def test_protected_document_refused(self):
        folder = tempfile.mkdtemp()
        src = os.path.join(folder, "p.pdf")
        d = pymupdf.open()
        d.new_page().insert_text((72, 72), "x")
        d.save(src, encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="owner", permissions=-1)
        w, v = self.window(src)
        told = []
        with mock.patch.object(QMessageBox, "information", lambda *a, **k: told.append(a)), \
                mock.patch.object(QFileDialog, "getSaveFileName",
                                  lambda *a, **k: self.fail("asked for a file name")):
            self.assertFalse(w.save_as_pdfa())
        self.assertEqual(len(told), 1)
        self.assertIn("Remove security", told[0][2])

    def test_check_command_reports(self):
        folder = tempfile.mkdtemp()
        src = os.path.join(folder, "messy.pdf")
        with open(src, "wb") as f:
            f.write(messy_pdf())
        w, v = self.window(src)
        from kanzonas import pdfa_ui
        shown = []
        with mock.patch.object(pdfa_ui.ReportDialog, "exec",
                               lambda self: shown.append(self) or 0):
            w.check_pdfa()
        self.assertEqual(len(shown), 1)
        self.assertGreater(shown[0].tree.topLevelItemCount(), 5)


if __name__ == "__main__":
    unittest.main()
