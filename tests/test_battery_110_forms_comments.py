"""What the 1.10 break-it battery found in smart forms and comments review, fixed. Form
scripts and comment files come from other people (untrusted); each of these stopped
KanzonasPDF with an error, hung it, or let a file reach where it shouldn't:

Smart forms
- a formula nested deeply ("((((...1))))"), or a long one (A + A + ... 100,000 times), or an
  Acrobat call with arrays inside arrays, went past Python's limit on calls inside calls:
  reading the form failed, and with it every value filled in;
- a chain of thousands of calculated fields (each reading the one before) did the same when
  working out the calculation order; fields nested 3,000 deep did it when reading the form;
- a 400-digit number (infinity to Python) in a field: shown with a number format, an error;
  typed, kept as an empty value; inf + -inf in a sum, an error; a format's "decimals" of
  400 digits, an error reading the form; a range of "nan" written back as broken JavaScript;
- a date format with the weekday first ("dddd, mmmm d, yyyy") read 11/6/26 as June 11;
- what reads a removed field (Apply redactions) was found by trying every field against
  every other: 3,000 chained fields, a quarter of a second, ten times that for 10,000.

Comments review
- an imported comment's KanzonasPDF style naming an image stamp by path
  ("image:C:/Users/.../photo.png", "image:../../x.png", a \\\\server\\share one) made
  KanzonasPDF read that picture off the disk (or the network) into the document, to be sent
  back with the comments: only a stamp library file, by its bare name, is read now;
- a fill-in stamp of 3,000 rows (or a 100,000-letter label) was drawn as a picture of
  gigabytes: the import hung for minutes;
- NaN, infinity or 1e300 in a position or size went into the PDF (/Rect [nan ...], a markup
  2 billion points wide), and one in a rotation stopped the whole import with "cannot
  convert float NaN to integer"; an ink drawing whose strokes couldn't be read was made 4
  billion points wide: now that one comment is skipped and said so, the rest imported;
- a style (kz:props) nested 100,000 deep stopped the whole import, and with Search & redact
  on a document holding one, the search;
- 2,000 comments imported onto one page took 15 s (10,000: many minutes, the app hung), and
  KanzonasPDF's own markups 112 s for 2,000: MuPDF looks through every markup loaded at each
  one drawn; now 10,000 in about 1 s, and 10,000 of KanzonasPDF's own in about 20 s;
- a thread of thousands of replies, each answering the one before, went past Python's
  limit: the Markups list, Summarize comments and Reply stopped with an error.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_battery_110_forms_comments
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

from kanzonas import annotations as A, review, smart_forms as S, stamps, xfdf  # noqa: E402
from kanzonas import document_view as DV  # noqa: E402
from kanzonas.document_view import DocumentView  # noqa: E402

XFDF = ('<?xml version="1.0" encoding="UTF-8"?><xfdf xmlns="http://ns.adobe.com/xfdf/" '
        'xmlns:kz="https://kanzonas.com/ns/xfdf/1"><annots>%s</annots></xfdf>')


def js(text):
    return "<< /S /JavaScript /JS %s >>" % pymupdf.get_pdf_str(text)


class Case(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        self.warnings = []
        for name, value in (("information", None), ("critical", None),
                            ("question", QMessageBox.Yes)):
            patch = mock.patch.object(QMessageBox, name, return_value=value)
            patch.start()
            self.addCleanup(patch.stop)
        patch = mock.patch.object(QMessageBox, "warning",
                                  side_effect=lambda *a, **k: self.warnings.append(a[2]))
        patch.start()
        self.addCleanup(patch.stop)
        patch = mock.patch.object(DV, "USE_JOURNAL", True)
        patch.start()
        self.addCleanup(patch.stop)

    def view(self, d):
        path = os.path.join(self.tmp.name, "f%d.pdf" % id(d))
        d.save(path)
        d.close()
        v = DocumentView(path)

        def close():
            if not v.doc.is_closed:
                v.dirty = False
                v.close_doc()
        self.addCleanup(close)
        return v

    def blank(self, pages=1):
        d = pymupdf.open()
        for _ in range(pages):
            d.new_page(width=612, height=792)
        return d

    def imported(self, v, body):
        """Import an XFDF file's annotations (body) into view v: its Report."""
        return v.import_comments(xfdf.from_xfdf((XFDF % body).encode("utf-8")))


# ---- smart forms ------------------------------------------------------------------------------
def chained_fields(d, n, extra=None):
    """n text fields f0..f(n-1), each f(k) the sum of f(k-1); /CO in reverse (worst) order."""
    p = d[0] if d.page_count else d.new_page()
    fx = []
    for i in range(n):
        x = d.get_new_xref()
        fx.append(x)
        aa = "/AA << /C %s >>" % js('AFSimple_Calculate("SUM", new Array ("f%d"));' % (i - 1)) \
            if i else ""
        d.update_object(x, "<< /Type /Annot /Subtype /Widget /FT /Tx /T (f%d) /Rect [10 10 60 "
                           "30] /P %d 0 R %s >>" % (i, p.xref, aa))
    d.xref_set_key(p.xref, "Annots", "[%s]" % " ".join("%d 0 R" % x for x in fx))
    d.xref_set_key(d.pdf_catalog(), "AcroForm", "<< /Fields [%s] /CO [%s] /DA (/Helv 0 Tf 0 g) >>"
                   % (" ".join("%d 0 R" % x for x in fx),
                      " ".join("%d 0 R" % x for x in reversed(fx[1:]))))
    return fx


class Formulas(unittest.TestCase):
    def test_a_deeply_nested_or_very_long_formula_is_refused_not_a_crash(self):
        for formula in ("(" * 5000 + "1" + ")" * 5000, "-" * 5000 + "1",
                        " + ".join(["A"] * 100000)):
            with self.subTest(formula=formula[:20]):
                with self.assertRaises(S.FormulaError):
                    S.parse_formula(formula)
                js_ = "/** BVCALC %s EVCALC **/ event.value = 0;" % formula
                self.assertIn("custom", S.read_calc(js_))       # (shown as not run)
                self.assertIsNone(S.calculate({"formula": formula}, lambda n: 1.0))
        # what a person writes still works, at the limits too
        self.assertEqual(S.calculate({"formula": "(" * 40 + "2 * 3" + ")" * 40}, None), 6)
        self.assertEqual(S.calculate({"formula": " + ".join(["a"] * 200)}, lambda n: 1.0), 200)

    def test_arrays_inside_arrays_in_a_script_are_not_a_crash(self):
        script = "AFNumber_Format(" + "[" * 5000 + "]" * 5000 + ", 0, 0, 0);"
        self.assertIsNone(S.parse_call(script))
        self.assertIn("custom", S.read_format(script))
        self.assertEqual(S.parse_call("f([[1, 2], [3]])"), ("f", [[[1.0, 2.0], [3.0]]]))

    def test_infinite_and_huge_numbers(self):
        big = "9" * 400                                       # (float: infinity)
        self.assertIsNone(S.to_number(big))
        self.assertIsNone(S.to_number(float("inf")))
        number = {"kind": "number", "decimals": 2, "sep": 0, "neg": 0, "currency": "",
                  "prepend": True}
        self.assertEqual(S.format_value(number, big), big)
        self.assertEqual(S.format_value({"kind": "percent", "decimals": 2}, big), big)
        self.assertEqual(S.format_value({"kind": "percent", "decimals": 0}, 1e308), 1e308)
        ok, value, _why = S.check_input(big, number)
        self.assertFalse(ok)                                   # (was kept as "")
        self.assertIsNone(S.calculate({"op": "SUM", "fields": ["a", "b"]},
                                      lambda n: float("inf") if n == "a" else -float("inf")))
        for script in ('AFNumber_Format(%s, 0, 0, 0, "", true);' % big,
                       'AFNumber_Format("inf", 0, 0, 0, "", true);',
                       "AFPercent_Format(%s, 0);" % big, "AFDate_Format(%s);" % big,
                       "AFSpecial_Format(%s);" % big):
            with self.subTest(script=script[:20]):
                S.read_format(script)                          # (OverflowError before)
        rng = S.read_validate('AFRange_Validate(true, "nan", true, "inf");')
        self.assertIn("custom", rng)
        self.assertEqual(S.validate_js(rng), 'AFRange_Validate(true, "nan", true, "inf");')

    def test_a_weekday_first_in_a_date_format(self):
        fmt = {"kind": "date", "pattern": "dddd, mmmm d, yyyy"}
        self.assertEqual(S.check_input("11/6/26", fmt)[1], "Friday, November 6, 2026")
        self.assertEqual(S.check_input("Friday, November 6, 2026", fmt)[1],
                         "Friday, November 6, 2026")
        self.assertEqual(S.check_input("6/11/2026", {"kind": "date",
                                                     "pattern": "ddd dd/mm/yyyy"})[1],
                         "Fri 06/11/2026")


class FormDocuments(Case):
    def test_a_chain_of_thousands_of_calculated_fields(self):
        d = self.blank()
        chained_fields(d, 3000)
        form = S.read_form(d)
        order, looped = S.calc_order(form)
        self.assertEqual((len(order), looped), (2999, []))
        self.assertEqual(order[:3], ["f1", "f2", "f3"])
        out = S.recalculate(d, form, {"f0": "5"})
        self.assertEqual((len(out), out["f2999"]), (2999, "5"))
        t = time.perf_counter()
        self.assertEqual(len(S.dependents(form, {"f0"})), 2999)
        self.assertLess(time.perf_counter() - t, 0.1)
        self.assertEqual(S.dependents(form, {"f2998"}), {"f2999"})
        # a loop is still a loop
        d.xref_set_key(form.fields["f0"].fx, "AA", "<< /C %s >>" % js(
            'AFSimple_Calculate("SUM", new Array ("f2999"));'))
        order, looped = S.calc_order(S.read_form(d))
        self.assertEqual((order, len(looped)), ([], 3000))

    def test_filling_in_a_chain_in_the_app(self):
        d = self.blank()
        chained_fields(d, 1100)
        v = self.view(d)
        x0 = next(w.xref for w in v.doc[0].widgets() if w.field_name == "f0")
        self.assertTrue(v.enter_field_value(0, x0, "7"))
        last = next(w for w in v.doc[0].widgets() if w.field_name == "f1099")
        self.assertEqual(last.field_value, "7")
        self.assertEqual(self.warnings, [])

    def test_fields_nested_thousands_deep(self):
        d = self.blank()
        p = d[0]
        xs = [d.get_new_xref() for _ in range(3000)]
        for i, x in enumerate(xs):
            kids = "/Kids [%d 0 R]" % xs[i + 1] if i + 1 < len(xs) else \
                "/Subtype /Widget /Rect [0 0 10 10] /FT /Tx /P %d 0 R" % p.xref
            d.update_object(x, "<< /T (n%d) %s %s >>" % (
                i, kids, "/Parent %d 0 R" % xs[i - 1] if i else ""))
        d.xref_set_key(p.xref, "Annots", "[%d 0 R]" % xs[-1])
        d.xref_set_key(d.pdf_catalog(), "AcroForm", "<< /Fields [%d 0 R] >>" % xs[0])
        S.read_form(d)                  # (RecursionError before)
        self.assertEqual(len(S.field_tree(d)), 3000)


# ---- comments review --------------------------------------------------------------------------
class StampFiles(Case):
    def test_an_imported_stamp_never_reads_a_picture_off_the_disk(self):
        secret = os.path.join(self.tmp.name, "secret.png")
        pm = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 37, 23), 0)
        pm.set_rect(pm.irect, (10, 200, 30))
        pm.save(secret)
        lib = stamps.library_dir()
        names = [secret, os.path.relpath(secret, lib), "..\\..\\secret.png",
                 "\\\\server\\share\\secret.png", "../" + os.path.basename(secret)]
        for name in names:
            with self.subTest(name=name):
                self.assertEqual(stamps.image_stamp(name), (None, None))
        v = self.view(self.blank())
        for name in names:
            props = '{"kind":"stamp","props":{"label":"image:%s"}}' % name.replace("\\", "\\\\")
            self.imported(v, '<stamp page="0" rect="100,100,200,200" name="s%d" '
                             "kz:props='%s'/>" % (names.index(name), props))
        for x in range(1, v.doc.xref_length()):
            if v.doc.xref_get_key(x, "Subtype")[1] == "/Image":
                self.assertNotEqual((v.doc.xref_get_key(x, "Width")[1],
                                     v.doc.xref_get_key(x, "Height")[1]), ("37", "23"))
        # a stamp of the library itself still works
        mine = os.path.join(lib, "battery-110-stamp.png")
        pm.save(mine)
        self.addCleanup(os.remove, mine)
        png, aspect = stamps.image_stamp("battery-110-stamp.png")
        self.assertIsNotNone(png)
        self.assertAlmostEqual(aspect, 23 / 37)

    def test_a_huge_stamp_label_or_fill_in_stamp_doesnt_hang(self):
        v = self.view(self.blank())
        t = time.perf_counter()
        rep = self.imported(
            v, '<stamp page="0" rect="0,0,100,100" name="a" kz:props=\'{"kind":"stamp",'
               '"props":{"label":"form:%s"}}\'/><stamp page="0" rect="0,0,100,100" name="b" '
               'kz:props=\'{"kind":"stamp","props":{"label":"%s"}}\'/>' % ("a|" * 3000,
                                                                         "W" * 100000))
        self.assertLess(time.perf_counter() - t, 5)
        self.assertEqual(rep.added, 2)
        self.assertEqual(len(stamps.form_fields("form:" + "a|" * 3000)), stamps.MAX_ROWS)


class ImportedNumbers(Case):
    def test_numbers_that_arent_positions_skip_that_comment_only(self):
        v = self.view(self.blank())
        bad = ['<square page="0" rect="nan,0,100,100" name="b1"/>',
               '<square page="0" rect="0,0,inf,100" name="b2"/>',
               '<square page="0" rect="0,0,1e300,100" name="b3"/>',
               '<freetext page="0" rect="0,0,100,100" rotation="nan" name="b4">'
               '<contents>x</contents></freetext>',
               '<freetext page="0" rect="0,0,100,100" rotation="1e999" name="b5"/>',
               '<square page="0" rect="0,0,100,100" width="nan" name="b6"/>',
               '<highlight page="0" rect="0,0,100,100" coords="nan,1,2,3,4,5,6,7" name="b7"/>',
               '<line page="0" rect="0,0,100,100" start="nan,1" end="2,3" name="b8"/>',
               '<ink page="0" rect="0,0,100,100" name="b9"><inklist><gesture>nan,1;2,3'
               '</gesture></inklist></ink>',
               '<ink page="0" rect="0,0,100,100" name="b10"/>',
               '<polygon page="0" rect="0,0,100,100" name="b11"><vertices>1,2</vertices>'
               '</polygon>']
        good = '<square page="0" rect="10,10,50,50" name="good"/>'
        rep = self.imported(v, "".join(bad) + good)
        self.assertIsNotNone(rep, self.warnings)
        self.assertEqual(rep.added, 1)
        self.assertEqual(sum(rep.skipped.values()), len(bad))
        rects = [a.rect for a in v.doc[0].annots()]
        self.assertEqual(rects, [pymupdf.Rect(10, 742, 50, 782)])
        # a pop-up's place that isn't one: the note comes, without it
        rep = self.imported(v, '<text page="0" rect="0,0,20,20" name="n"><popup '
                               'rect="nan,0,1,1"/></text>')
        self.assertEqual(rep.added, 1)

    def test_a_style_nested_too_deep_or_with_nan_is_left_out(self):
        v = self.view(self.blank())
        for k, props in enumerate(("[" * 100000 + "]" * 100000,
                                   '{"kind":"ink","geom":{"strokes":[[[1e308,1e308]]]}}',
                                   '{"kind":"rect","props":{"width":NaN}}')):
            rep = self.imported(v, '<square page="0" rect="10,10,50,50" name="s%d" '
                                   'kz:props="%s"/>' % (k, props.replace('"', "&quot;")))
            self.assertIsNotNone(rep, self.warnings)
            self.assertEqual(rep.added, 1)
        for a in v.doc[0].annots():
            self.assertEqual(v.doc.xref_get_key(a.xref, A.KZ_KEY)[0], "null")
            self.assertLess(a.rect.width, 100)
        self.assertTrue(xfdf.props_ok('{"kind":"rect","props":{"width":2}}'))

    def test_search_and_redact_with_a_style_nested_too_deep(self):
        d = self.blank()
        p = d[0]
        p.insert_text((72, 100), "Nothing here", fontsize=12)
        a = p.add_rect_annot((100, 100, 200, 200))
        a.set_info(content="TOPSECRET plan")
        a.update()
        d.xref_set_key(a.xref, A.KZ_KEY, pymupdf.get_pdf_str("[" * 100000 + "]" * 100000))
        v = self.view(d)
        v.remove_term("TOPSECRET")
        self.assertEqual(self.warnings, [])
        self.assertNotIn(b"TOPSECRET", v.doc.tobytes(expand=255))


class ManyComments(Case):
    def test_thousands_of_comments_on_one_page(self):
        v = self.view(self.blank())
        body = "".join('<square page="0" rect="%d,%d,%d,%d" name="n%d" title="me"><contents>c%d'
                       '</contents></square>' % (i % 500, i % 700, i % 500 + 5, i % 700 + 5, i, i)
                       for i in range(3000))
        t = time.perf_counter()
        rep = self.imported(v, body)
        self.assertLess(time.perf_counter() - t, 6)        # (was 34 s)
        self.assertEqual(rep.added, 3000)
        recs, _ = xfdf.records(v.doc)
        self.assertEqual(len(recs), 3000)
        self.assertTrue(all(v.doc.xref_get_key(a.xref, "AP")[0] == "dict"
                            for a in v.doc[0].annots()))

    def test_thousands_of_kanzonas_markups_on_one_page(self):
        d = self.blank()
        props = '{&quot;kind&quot;:&quot;rect&quot;,&quot;props&quot;:{}}'
        body = "".join('<square page="0" rect="%d,%d,%d,%d" name="n%d" kz:props="%s"/>'
                       % (i % 500, i % 700, i % 500 + 5, i % 700 + 5, i, props)
                       for i in range(1500))
        recs = xfdf.from_xfdf((XFDF % body).encode("utf-8"))
        t = time.perf_counter()
        rep = xfdf.import_records(d, recs)
        self.assertLess(time.perf_counter() - t, 12)       # (was about 60 s)
        self.assertEqual(rep.added, 1500)
        names = [d.xref_get_key(x, "NM")[1] for x in A.annot_order(d[0])]
        self.assertEqual(names, ["n%d" % i for i in range(1500)])    # (in their order)
        self.assertTrue(all(d.xref_get_key(a.xref, A.KZ_KEY)[0] == "string"
                            for a in d[0].annots()))


class LongThreads(Case):
    def test_a_thread_of_thousands_of_replies(self):
        v = self.view(self.blank(2))
        body = '<square page="0" rect="0,0,10,10" name="r0"/>' + "".join(
            '<text page="0" rect="0,0,10,10" name="r%d" inreplyto="r%d" '
            'date="D:2026010101%04d"><contents>reply %d</contents></text>' % (i, i - 1, i, i)
            for i in range(1, 3000))
        self.assertEqual(self.imported(v, body).added, 3000)
        t = review.Threads(v.doc[0])
        root = [x for x in t.order if not t.is_linked(x)]
        self.assertEqual(len(root), 1)
        replies = t.replies(root[0])
        self.assertEqual(len(replies), 2999)
        self.assertEqual([d for d, _ln in replies[:3]], [1, 2, 3])
        self.assertEqual(replies[-1][1].text, "reply 2999")
        self.assertGreater(review.summarize(v.doc).page_count, 10)
        from kanzonas import markups_panel as MP
        panel = MP.MarkupsPanel()
        self.addCleanup(panel.deleteLater)
        panel.refresh(v.doc)                # (RecursionError before)
        self.assertEqual(self.warnings, [])
        # replies still come in their order: a, with b and c answering it (c older), and d
        # answering b
        body = ('<square page="1" rect="0,0,10,10" name="a"/>'
                '<text page="1" rect="0,0,10,10" name="b" inreplyto="a" date="D:20260102"/>'
                '<text page="1" rect="0,0,10,10" name="c" inreplyto="a" date="D:20260101"/>'
                '<text page="1" rect="0,0,10,10" name="d" inreplyto="b" date="D:20260103"/>')
        self.imported(v, body)
        t = review.Threads(v.doc[1])
        names = {x: v.doc.xref_get_key(x, "NM")[1] for x in t.order}
        root = next(x for x in t.order if names[x] == "a")
        self.assertEqual([(d, names[ln.xref]) for d, ln in t.replies(root)],
                         [(1, "c"), (1, "b"), (2, "d")])


class CutAndPaste(Case):
    def test_a_markup_cut_and_pasted_keeps_its_replies_and_statuses(self):
        d = self.blank(2)
        a = d[0].add_rect_annot((100, 100, 200, 200))
        a.update()
        x = a.xref
        v = self.view(d)
        v.reply_to(0, x, "First answer")
        r1 = review.Threads(v.doc[0]).children[x][0]
        v.reply_to(0, r1, "Answer to the answer")
        v.set_review_status(0, [x], "Accepted")
        before = review.thread_of(v.doc, review.Threads(v.doc[0]), x)
        self.assertEqual(len(before), 3)
        v.select_xref(0, x)
        self.assertEqual(v.cut(), "markups")
        self.assertEqual(list(v.doc[0].annots()), [])
        with mock.patch.object(v, "paste_target", lambda: (1, pymupdf.Point(300, 300))):
            self.assertEqual(v.paste(), "markups")
        t = review.Threads(v.doc[1])
        root = next(y for y in t.order if not t.is_linked(y))
        after = review.thread_of(v.doc, t, root)
        self.assertEqual(sorted(map(repr, after)), sorted(map(repr, before)))
        self.assertEqual(t.status(root)[0], "Accepted")
        self.assertEqual([(dp, ln.text) for dp, ln in t.replies(root)],
                         [(1, "First answer"), (2, "Answer to the answer")])
        # one undo step each way
        v.undo()
        self.assertEqual(list(v.doc[1].annots()), [])
        v.undo()
        self.assertEqual(len(review.Threads(v.doc[0]).descendants([x])), 3)
        # Copy (not Cut) makes a copy of the markup alone, as before
        v.select_xref(0, x)
        self.assertEqual(v.copy(), "markups")
        with mock.patch.object(v, "paste_target", lambda: (1, pymupdf.Point(300, 300))):
            v.paste()
        self.assertEqual(len(list(v.doc[1].annots())), 1)


if __name__ == "__main__":
    unittest.main()
