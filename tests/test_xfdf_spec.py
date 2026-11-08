"""Comment files as the specifications describe them and as Acrobat writes them (xfdf.py):
XFDF (Adobe's XFDF Specification 3.0 / ISO 19444-1) and FDF (ISO 32000-1 12.7.8). The
samples are written by hand after the specifications and Acrobat's own files (rich text only,
<f> and <ids> first, a link with an action, coords ending in a comma); the names and formats
were checked against Apache PDFBox's XFDF reader (pdmodel/fdf). Also: a comment file is
untrusted (no DTD, entities, actions or oversized files), and Search & redact cleans replies.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_xfdf_spec
"""
import os
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import annotations as A, review, review_ui, xfdf  # noqa: E402
from kanzonas.document_view import DocumentView  # noqa: E402

R = pymupdf.Rect
NS = "{http://ns.adobe.com/xfdf/}"

# As Acrobat writes a review (by hand, after its files): the sticky note's text only as rich
# text, a reply with a pop-up, a status, a callout with rich text and its own default
# appearance, highlight coords ending in a comma, a line with a caption, a caret, a link with
# an action (not a comment: skipped), dates with time zones, <f> and <ids> before <annots>.
ACROBAT = """<?xml version="1.0" encoding="UTF-8"?>
<xfdf xmlns="http://ns.adobe.com/xfdf/" xml:space="preserve">
<f href="plan.pdf"/>
<ids original="5F4DCC3B5AA765D61D8327DEB882CF99" modified="7C6A180B36896A0A8C02787EEAFB0E4C"/>
<annots>
<text page="0" color="#FFFF00" date="D:20261103101500-05'00'" flags="print,nozoom,norotate"
 name="9a3c-note" rect="100,650,120,670" subject="Sticky Note" title="Reviewer One"
 creationdate="D:20261103101500-05'00'" icon="Comment">
<contents-richtext><body xmlns="http://www.w3.org/1999/xhtml"
 xmlns:xfa="http://www.xfa.org/schema/xfa-data/1.0/" xfa:APIVersion="Acrobat:24.4.0"
 xfa:spec="2.0.2"><p>Check the span</p><p>and the <span style="font-weight:bold">load</span></p></body></contents-richtext>
<popup flags="print,nozoom,norotate" open="no" page="0" rect="400,560,580,670"/>
</text>
<text page="0" color="#FFFF00" date="D:20261104090000-05'00'" flags="print,nozoom,norotate"
 name="9a3c-reply" rect="100,650,120,670" subject="Sticky Note" title="Author Two"
 creationdate="D:20261104090000-05'00'" icon="Comment" inreplyto="9a3c-note" replyType="reply">
<contents>Fixed in rev B&#13;See sheet 4</contents>
<popup flags="print,nozoom,norotate" open="no" page="0" rect="400,450,580,560"/>
</text>
<text page="0" color="#FFFF00" date="D:20261104090100-05'00'"
 flags="hidden,print,nozoom,norotate" name="9a3c-state" rect="100,650,120,670"
 title="Author Two" inreplyto="9a3c-note" state="Completed" statemodel="Review"
 icon="Comment"><contents>Completed set by Author Two</contents></text>
<freetext page="0" date="D:20261103101700Z" flags="print" name="9a3c-callout"
 rect="300,400,460,480" title="Reviewer One" width="1" justification="centered"
 intent="FreeTextCallout" head="OpenArrow" callout="300,400,350,440,360,440"
 fringe="60,0,0,0" creationdate="D:20261103101700Z">
<contents>Move this</contents>
<contents-richtext><body xmlns="http://www.w3.org/1999/xhtml"><p>Move this</p></body></contents-richtext>
<defaultappearance>0 0 1 rg /Helv 12 Tf</defaultappearance>
<defaultstyle>font: Helvetica,sans-serif 12.0pt; text-align:center; color:#0000FF</defaultstyle>
</freetext>
<highlight page="0" color="#FFCD45" date="D:20261103101800-05'00'" flags="print"
 name="9a3c-hl" rect="71,737,151,756" title="Reviewer One"
 coords="72,755,150,755,72,738,150,738,"><contents>Rephrase</contents></highlight>
<line page="0" color="#FF0000" date="D:20261103101900-05'00'" flags="print" name="9a3c-line"
 rect="95,195,305,215" title="Reviewer One" width="2" start="100,200" end="300,200"
 head="OpenArrow" tail="None" caption="yes" caption-style="Top" caption-offset-h="0"
 caption-offset-v="4" leaderLength="10"><contents>10 ft</contents></line>
<caret page="0" color="#0000FF" date="D:20261103102000-05'00'" flags="print" name="9a3c-caret"
 rect="200,300,210,312" title="Reviewer One" symbol="paragraph" fringe="1,1,1,1"/>
<link page="0" rect="72,72,144,90" width="0" actiontype="URI" target="https://example.com"/>
</annots>
</xfdf>
"""

# FDF as Acrobat writes it: every annotation (the pop-ups too) in /Annots with its /Page.
# This one also carries what a comment file must never bring in: a document JavaScript,
# an action (Launch) and additional actions (JavaScript) on the markup.
FDF = rb"""%FDF-1.2
%\xe2\xe3\xcf\xd3
1 0 obj
<</FDF<</Annots[2 0 R 3 0 R 4 0 R]/F(plan.pdf)/ID[<5F4DCC3B5AA765D61D8327DEB882CF99><7C6A180B36896A0A8C02787EEAFB0E4C>]
/JavaScript<</Doc[(x)5 0 R]>>>>/Type/Catalog>>
endobj
2 0 obj
<</Type/Annot/Subtype/Square/Page 0/Rect[100 100 200 160]/C[1 0 0]/T(Reviewer One)
/Contents(Look here)/NM(fdf-square)/M(D:20261103101500-05'00')/F 4/Popup 3 0 R
/A<</S/Launch/F(calc.exe)>>/AA<</E<</S/JavaScript/JS(app.alert\(1\))>>>>>>
endobj
3 0 obj
<</Type/Annot/Subtype/Popup/Page 0/Rect[300 100 480 200]/Open false/Parent 2 0 R/F 28>>
endobj
4 0 obj
<</Type/Annot/Subtype/Text/Page 0/Rect[100 140 120 160]/IRT 2 0 R/RT/R/T(Author Two)
/Contents(Done)/NM(fdf-reply)/M(D:20261104090000-05'00')/F 28/Name/Comment
/A<</S/JavaScript/JS(app.alert\(2\))>>>>
endobj
5 0 obj
<</Length 13>>
stream
app.alert(3);
endstream
endobj
trailer
<</Root 1 0 R>>
%%EOF
"""


def sample(path, pages=2):
    d = pymupdf.open()
    for i in range(pages):
        d.new_page(width=612, height=792).insert_text((72, 100), "Plan words %d" % i)
    d.save(path)
    d.close()
    return path


class Base(unittest.TestCase):
    def setUp(self):
        self.boxes = []
        for name in ("information", "warning", "critical"):
            p = mock.patch.object(QMessageBox, name, lambda *a, **k: self.boxes.append(a[1:3]))
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch.object(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
        p.start()
        self.addCleanup(p.stop)
        p = mock.patch.object(A, "author", lambda: "Tester")
        p.start()
        self.addCleanup(p.stop)
        self.dir = tempfile.mkdtemp()

    def view(self, pages=2):
        v = DocumentView(sample(os.path.join(self.dir, "d%d.pdf" % time.perf_counter_ns()),
                                pages))
        self.addCleanup(v.close_doc)
        self.addCleanup(lambda: setattr(v, "dirty", False))
        return v

    def by_name(self, v, i=0):
        return {nm: x for x, _t, nm in v.doc[i].annot_xrefs() if nm}

    def key(self, v, x, k):
        return v.doc.xref_get_key(x, k)


class AcrobatXfdf(Base):
    def test_reads_what_acrobat_writes(self):
        recs = xfdf.from_xfdf(ACROBAT.encode())
        by = {r["keys"].get("NM"): r for r in recs if not r.get("unknown")}
        note = by["9a3c-note"]["keys"]
        # the text was only in rich text: its paragraphs are the note's lines
        self.assertEqual(note["Contents"], "Check the span\nand the load")
        self.assertTrue(note["RC"].startswith('<body xmlns="http://www.w3.org/1999/xhtml"'))
        self.assertIn("font-weight:bold", note["RC"])
        self.assertEqual(by["9a3c-reply"]["keys"]["Contents"], "Fixed in rev B\rSee sheet 4")
        self.assertEqual(by["9a3c-reply"]["irt"], "9a3c-note")
        self.assertEqual(by["9a3c-reply"]["popup"]["flags"], 28)
        st = by["9a3c-state"]["keys"]
        self.assertEqual((st["State"], st["StateModel"], int(st["F"])), ("Completed", "Review", 30))
        co = by["9a3c-callout"]["keys"]
        self.assertEqual((co["IT"], co["LE"][0], co["CL"], co["RD"], int(co["Q"])),
                         ("FreeTextCallout", "OpenArrow", [300, 400, 350, 440, 360, 440],
                          [60, 0, 0, 0], 1))
        self.assertEqual(co["DA"], "0 0 1 rg /Helv 12 Tf")
        self.assertEqual(co["M"], "D:20261103101700Z")
        self.assertEqual(by["9a3c-hl"]["keys"]["QuadPoints"],
                         [72, 755, 150, 755, 72, 738, 150, 738])
        ln = by["9a3c-line"]["keys"]
        self.assertEqual((ln["L"], ln["LE"], ln["Cap"], ln["CP"], ln["CO"], ln["LL"]),
                         ([100, 200, 300, 200], ["OpenArrow", "None"], True, "Top", [0, 4], 10))
        self.assertEqual(by["9a3c-caret"]["keys"]["Sy"], "P")
        self.assertEqual([r["subtype"] for r in recs if r.get("unknown")], ["link"])

    def test_imported_and_shown(self):
        v = self.view()
        rep = v.import_comments(xfdf.from_xfdf(ACROBAT.encode()))
        self.assertEqual((rep.added, sum(rep.skipped.values())), (7, 1))
        names = self.by_name(v)
        t = review.Threads(v.doc[0])
        note = names["9a3c-note"]
        self.assertEqual([(ln.author, ln.text) for _d, ln in t.replies(note)],
                         [("Author Two", "Fixed in rev B\rSee sheet 4")])
        self.assertEqual(t.status(note)[0], "Completed")
        page = v.doc[0]
        a = page.load_annot(note)
        self.assertEqual(a.info["content"], "Check the span\nand the load")
        self.assertIsNotNone(a.popup_rect)
        self.assertEqual(self.key(v, names["9a3c-caret"], "Sy"), ("name", "/P"))
        self.assertEqual(self.key(v, names["9a3c-line"], "CP"), ("name", "/Top"))
        self.assertEqual(self.key(v, names["9a3c-line"], "CO")[1].split(), ["[0", "4]"])
        self.assertEqual(self.key(v, names["9a3c-callout"], "RC")[0], "string")
        del a, page
        # no link came in
        self.assertEqual(v.doc[0].get_links(), [])

    def test_iso_dates_and_dates_without_their_prefix(self):
        self.assertEqual(xfdf.date_in("2026-11-03T10:15:00-05:00"), "D:20261103101500-05'00'")
        self.assertEqual(xfdf.date_in("2026-11-03T10:15:00Z"), "D:20261103101500Z")
        self.assertEqual(xfdf.date_in("2026-11-03"), "D:20261103000000")
        self.assertEqual(xfdf.date_in("20261103101500"), "D:20261103101500")
        self.assertEqual(xfdf.date_in("D:20261103101500+01'00'"), "D:20261103101500+01'00'")
        self.assertEqual(xfdf.date_out("20261103101500"), "D:20261103101500")


class OurXfdf(Base):
    def exported(self):
        v = self.view()
        v.import_comments(xfdf.from_xfdf(ACROBAT.encode()))
        recs, _ = xfdf.records(v.doc)
        return v, recs, xfdf.to_xfdf(recs, "plan.pdf", xfdf.file_ids(v.doc))

    def test_shape_of_the_file(self):
        v, recs, data = self.exported()
        root, _raws = xfdf.parse_xml(data)
        self.assertEqual(root.tag, NS + "xfdf")
        kids = [el.tag[len(NS):] for el in root]
        self.assertEqual(kids, ["f", "ids", "annots"])          # (f and ids first)
        ids = root.find(NS + "ids")
        self.assertRegex(ids.get("original"), r"^[0-9A-F]+$")
        self.assertEqual((ids.get("original"), ids.get("modified")), xfdf.file_ids(v.doc))
        allowed = {"page", "rect", "name", "title", "subject", "date", "creationdate", "state",
                   "statemodel", "color", "interior-color", "opacity", "flags", "inreplyto",
                   "replyType", "intent", "icon", "rotation", "justification", "width",
                   "style", "intensity", "dashes", "coords", "start", "end", "head", "tail",
                   "leaderLength", "leaderExtend", "leaderOffset", "caption", "caption-style",
                   "caption-offset-h", "caption-offset-v", "fringe", "callout", "symbol"}
        for el in root.find(NS + "annots"):
            for k in el.attrib:
                if not k.startswith("{https://kanzonas.com/"):
                    self.assertIn(k, allowed, el.tag)     # (XFDF's own names only)
            self.assertRegex(el.get("date"), r"^D:\d{14}")
            for p in el.iter(NS + "popup"):
                self.assertEqual(p.get("flags"), "print,nozoom,norotate")
                self.assertEqual(p.get("page"), el.get("page"))
        note = [el for el in root.find(NS + "annots") if el.get("name") == "9a3c-note"][0]
        rich = note.find(NS + "contents-richtext")
        body = rich[0]
        self.assertEqual(body.tag, "{http://www.w3.org/1999/xhtml}body")
        self.assertEqual(xfdf.rich_plain(body), "Check the span\nand the load")
        self.assertEqual(note.find(NS + "contents").text, "Check the span\nand the load")

    def test_round_trip_keeps_line_ends_and_rich_text(self):
        v, recs, data = self.exported()
        self.assertIn(b"Fixed in rev B&#13;See sheet 4", data)
        other = self.view()
        rep = other.import_comments(xfdf.from_xfdf(data))
        self.assertEqual(rep.added, len(recs))
        a, b = self.by_name(v), self.by_name(other)
        for nm in a:
            for k in ("Contents", "RC", "T", "M", "CreationDate", "State", "StateModel",
                      "Sy", "CP", "CO", "IRT"):
                ka, kb = self.key(v, a[nm], k), self.key(other, b[nm], k)
                if k == "IRT":
                    ka = ka[0]
                    kb = kb[0]
                self.assertEqual(ka, kb, (nm, k))

    def test_text_xml_cant_hold_is_left_out(self):
        v = self.view()
        page = v.doc[0]
        a = page.add_text_annot((50, 50), "-")
        x = a.xref
        del a, page
        text = "bell\x07 and esc\x1b here \u2603"
        v.doc.xref_set_key(x, "Contents", "<FEFF%s>" % text.encode("utf-16-be").hex())
        recs, _ = xfdf.records(v.doc)
        data = xfdf.to_xfdf(recs)
        root, _ = xfdf.parse_xml(data)              # (readable)
        c = root.find(NS + "annots")[0].find(NS + "contents").text
        self.assertEqual(c, "bell and esc here \u2603")
        self.assertTrue(x)

    def test_rich_text_that_says_something_else_isnt_kept(self):
        """/RC is shown instead of /Contents by other programs: one that disagrees with the
        plain text (changed by a program that only knew one of them) is left out."""
        v = self.view()
        page = v.doc[0]
        a = page.add_text_annot((50, 50), "the new text")
        x = a.xref
        del a, page
        v.doc.xref_set_key(x, "RC", pymupdf.get_pdf_str(
            '<?xml version="1.0"?><body xmlns="http://www.w3.org/1999/xhtml"><p>the old '
            'text</p></body>'))
        recs, _ = xfdf.records(v.doc)
        self.assertNotIn("RC", recs[0]["keys"])
        self.assertNotIn(b"contents-richtext", xfdf.to_xfdf(recs))
        v.doc.xref_set_key(x, "RC", pymupdf.get_pdf_str("<body><p>the new text</p></body>"))
        recs, _ = xfdf.records(v.doc)
        data = xfdf.to_xfdf(recs)
        # (put in the XHTML namespace: in the file it would otherwise be in XFDF's)
        self.assertIn(b'<contents-richtext><body xmlns="http://www.w3.org/1999/xhtml">', data)
        xfdf.parse_xml(data)


class Fdf(Base):
    def test_reads_acrobat_fdf_and_leaves_its_actions_out(self):
        recs = xfdf.from_fdf(FDF)
        self.assertEqual([r["subtype"] for r in recs], ["Square", "Text"])   # (pop-up: with it)
        self.assertFalse(any(r.get("unknown") for r in recs))
        sq = recs[0]
        self.assertEqual(sq["popup"], {"rect": [300, 100, 480, 200], "open": False, "flags": 28})
        self.assertEqual(recs[1]["irt"], "fdf-square")
        v = self.view()
        rep = v.import_comments(recs)
        self.assertEqual((rep.added, rep.skipped), (2, {}))
        doc = v.doc
        for x, _t, _nm in doc[0].annot_xrefs():
            for k in ("A", "AA", "JS"):
                self.assertEqual(doc.xref_get_key(x, k)[0], "null", k)
        self.assertNotIn("JavaScript", doc.xref_object(doc.pdf_catalog()))
        for x in range(1, doc.xref_length()):
            obj = doc.xref_object(x, compressed=True)
            self.assertNotIn("/Launch", obj)
            self.assertNotIn("app.alert", obj)

    def test_our_fdf_follows_table_248(self):
        v = self.view()
        v.import_comments(xfdf.from_xfdf(ACROBAT.encode()))
        recs, _ = xfdf.records(v.doc)
        data = xfdf.to_fdf(recs, "plan.pdf", xfdf.file_ids(v.doc))
        fdf = pymupdf.open("pdf", data)
        root = int(fdf.xref_get_key(-1, "Root")[1].split()[0])
        self.assertEqual(fdf.xref_get_key(root, "FDF/ID")[0], "array")
        listed = [int(t) for t in fdf.xref_get_key(root, "FDF/Annots")[1].strip("[]")
                  .replace("0 R", "").split()]
        popups = 0
        for x in listed:
            self.assertEqual(fdf.xref_get_key(x, "Page")[0], "int")       # (every one)
            self.assertEqual(fdf.xref_get_key(x, "P")[0], "null")
            if fdf.xref_get_key(x, "Subtype")[1] == "/Popup":
                popups += 1
                parent = int(fdf.xref_get_key(x, "Parent")[1].split()[0])
                self.assertIn(parent, listed)
        self.assertEqual(popups, sum(1 for r in recs if r.get("popup")))
        fdf.close()
        # and read back to the same
        again = xfdf.from_fdf(data)
        self.assertEqual(len(again), len(recs))


class Untrusted(Base):
    def refused(self, data):
        with self.assertRaises(ValueError):
            xfdf.from_xfdf(data)

    def test_no_dtd_or_entities_anywhere(self):
        laughs = (b'<?xml version="1.0"?><!DOCTYPE xfdf [<!ENTITY a "aaaaaaaaaa">'
                  b'<!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;">]>'
                  b'<xfdf xmlns="http://ns.adobe.com/xfdf/"><annots><text page="0" '
                  b'rect="1,1,2,2"><contents>&b;</contents></text></annots></xfdf>')
        self.refused(laughs)
        # after a long comment (more than a first look at the file would see)
        self.refused(b"<!--" + b" " * 10000 + b"-->" + laughs[21:])
        # an external entity, and UTF-16 (a byte search would miss it)
        ext = (b'<?xml version="1.0"?><!DOCTYPE xfdf [<!ENTITY e SYSTEM "file:///etc/passwd">]>'
               b'<xfdf xmlns="http://ns.adobe.com/xfdf/"><annots><text page="0" rect="1,1,2,2">'
               b'<contents>&e;</contents></text></annots></xfdf>')
        self.refused(ext)
        self.refused(ext.decode().replace('version="1.0"', 'version="1.0" encoding="UTF-16"')
                     .encode("utf-16"))
        self.refused(b'<!DOCTYPE xfdf SYSTEM "http://example.com/x.dtd"><xfdf/>')
        # an undeclared entity is an error, not a lookup
        self.refused(b'<xfdf xmlns="http://ns.adobe.com/xfdf/"><annots><text page="0" '
                     b'rect="1,1,2,2"><contents>&x;</contents></text></annots></xfdf>')

    def test_utf16_file_reads(self):
        recs = xfdf.from_xfdf(ACROBAT.replace('encoding="UTF-8"', 'encoding="UTF-16"')
                              .encode("utf-16"))
        self.assertEqual(len(recs), 8)

    def test_size_depth_and_count_limits(self):
        with mock.patch.object(xfdf, "MAX_BYTES", 1000):
            self.refused(ACROBAT.encode())
            with self.assertRaises(ValueError):
                xfdf.from_fdf(FDF + b" " * 1000)
            path = os.path.join(self.dir, "big.xfdf")
            with open(path, "wb") as f:
                f.write(ACROBAT.encode())
            with self.assertRaises(ValueError):
                review_ui.read_comment_file(path)
        self.refused(b"<xfdf>" + b"<a>" * 100 + b"</a>" * 100 + b"</xfdf>")
        with mock.patch.object(xfdf, "MAX_ELEMENTS", 50):
            self.refused(b"<xfdf>" + b"<a/>" * 60 + b"</xfdf>")

    def test_no_action_comes_in_with_a_markup(self):
        data = b"""<xfdf xmlns="http://ns.adobe.com/xfdf/"><annots>
<square page="0" rect="10,10,60,60" color="#FF0000" name="s1" A="/Launch" AA="x">
<OnActivation><Action><Launch><File Name="calc.exe"/></Launch></Action></OnActivation>
<contents>box</contents></square>
<link page="0" rect="10,100,60,120"><OnActivation><Action><JavaScript>app.alert(1)</JavaScript>
</Action></OnActivation></link>
</annots></xfdf>"""
        v = self.view()
        rep = v.import_comments(xfdf.from_xfdf(data))
        self.assertEqual(rep.added, 1)
        x = self.by_name(v)["s1"]
        for k in ("A", "AA"):
            self.assertEqual(self.key(v, x, k)[0], "null")
        self.assertEqual(v.doc[0].get_links(), [])

    def test_our_style_for_a_picture_or_file_isnt_taken_from_a_file(self):
        props = '{"kind": "attach", "props": {}, "geom": {}}'
        data = ('<xfdf xmlns="http://ns.adobe.com/xfdf/" xmlns:kz="https://kanzonas.com/ns/'
                'xfdf/1"><annots><text page="0" rect="10,10,30,30" name="t1" kz:props=%s>'
                '<contents>hi</contents></text></annots></xfdf>' % xfdf.quoteattr(props))
        v = self.view()
        rep = v.import_comments(xfdf.from_xfdf(data.encode()))
        self.assertEqual(rep.added, 1)
        x = self.by_name(v)["t1"]
        self.assertEqual(self.key(v, x, A.KZ_KEY)[0], "null")
        self.assertEqual(v.doc.embfile_count(), 0)

    def test_replies_in_a_circle_or_to_another_page(self):
        data = b"""<xfdf xmlns="http://ns.adobe.com/xfdf/"><annots>
<text page="0" rect="10,10,30,30" name="a" inreplyto="b"><contents>a</contents></text>
<text page="0" rect="10,10,30,30" name="b" inreplyto="a"><contents>b</contents></text>
<square page="1" rect="10,10,60,60" name="sq"/>
<text page="0" rect="10,10,30,30" name="c" inreplyto="sq"><contents>c</contents></text>
</annots></xfdf>"""
        v = self.view()
        rep = v.import_comments(xfdf.from_xfdf(data))
        self.assertEqual(rep.added, 4)
        t = review.Threads(v.doc[0])
        names = self.by_name(v)
        # one of the circle answers the other; the other stays a markup of its own
        self.assertEqual(len([x for x in (names["a"], names["b"]) if t.is_linked(x)]), 1)
        self.assertFalse(t.is_linked(names["c"]))
        self.assertEqual(self.key(v, names["c"], "IRT")[0], "null")
        v.undo()
        self.assertEqual(v.doc[0].annot_xrefs(), [])


class RedactReplies(Base):
    def test_search_and_redact_cleans_a_reply_everywhere_it_keeps_the_word(self):
        """A reply holding the word in its rich text only, and one whose own drawing shows
        it (another program's), are cleaned or go: the word is nowhere afterwards."""
        v = self.view()
        v.import_comments(xfdf.from_xfdf(ACROBAT.encode()))
        names = self.by_name(v)
        doc = v.doc
        rep = names["9a3c-reply"]
        doc.xref_set_key(rep, "RC", pymupdf.get_pdf_str(
            "<body><p>Fixed in rev B, budget secret</p></body>"))
        # a status whose appearance (made by another program) shows the word
        st = names["9a3c-state"]
        ap = doc.get_new_xref()
        doc.update_object(ap, "<</Type/XObject/Subtype/Form/BBox[0 0 200 20]/Resources"
                              "<</Font<</F1<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>>>>>>>")
        doc.update_stream(ap, b"BT /F1 10 Tf 2 5 Td (secret status) Tj ET")
        doc.xref_set_key(st, "AP", "<</N %d 0 R>>" % ap)
        doc.xref_set_key(st, "F", "4")
        v.remove_term("secret")         # (Search & redact for text only in markups)
        self.assertEqual(self.boxes, [])
        for x in range(1, doc.xref_length()):
            try:
                obj = doc.xref_object(x, compressed=True)
            except Exception:
                continue
            self.assertNotIn("secret", obj.lower(), x)
        t = review.Threads(doc[0])
        note = self.by_name(v)["9a3c-note"]
        self.assertEqual([ln.text for _d, ln in t.replies(note)], ["Fixed in rev B\rSee sheet 4"])


if __name__ == "__main__":
    unittest.main()
