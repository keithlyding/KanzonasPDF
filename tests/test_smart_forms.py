"""Smart forms: Detect form fields on flat forms, calculated fields (KanzonasPDF's own parser,
never the file's JavaScript), formats and range checks, required fields, tab order, and that
all of it is written as the standard Acrobat actions and survives Save, reopening and undo.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_smart_forms
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
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import form_detect, smart_forms as S  # noqa: E402
from kanzonas import document_view as DV  # noqa: E402
from kanzonas.document_view import DocumentView  # noqa: E402

P = pymupdf.Point
PARA = ("The contractor agrees to deliver the panels by the end of the month. Every panel is "
        "checked before it leaves the shop, and the invoice follows the delivery. ")


# ---- flat forms to detect fields on ----------------------------------------------------------
def lines_form(d):
    p = d.new_page(width=612, height=792)
    p.insert_text((72, 100), "Name:", fontsize=11)
    p.draw_line((110, 102), (330, 102), width=0.8)
    p.insert_text((350, 100), "Date:", fontsize=11)
    p.draw_line((382, 102), (530, 102), width=0.8)
    p.insert_text((72, 140), "Address:", fontsize=11)
    p.draw_line((122, 142), (530, 142), width=0.8)
    p.insert_text((72, 180), "Phone: ______________________", fontsize=11)
    p.draw_line((72, 260), (272, 260), width=0.8)
    p.insert_text((72, 272), "Signature of applicant", fontsize=9)
    return p


def boxes_form(d):
    p = d.new_page(width=612, height=792)
    p.insert_text((72, 100), "Email", fontsize=11)
    p.draw_rect((120, 86, 400, 106), width=0.8)
    p.draw_rect((72, 130, 84, 142), width=0.8)
    p.insert_text((90, 140), "Yes, send me news", fontsize=10)
    p.draw_rect((72, 150, 84, 162), width=0.8)
    p.insert_text((90, 160), "No", fontsize=10)
    p.draw_rect((72, 220, 400, 260), width=0.8)
    p.insert_text((75, 229), "Company name", fontsize=7)
    return p


def table_form(d):
    p = d.new_page(width=612, height=792)
    xs, ys = [72, 272, 352, 452], [100, 120, 140, 160, 180]
    for y in ys:
        p.draw_line((xs[0], y), (xs[-1], y), width=0.8)
    for x in xs:
        p.draw_line((x, ys[0]), (x, ys[-1]), width=0.8)
    for x, t in zip(xs, ["Description", "Qty", "Price"]):
        p.insert_text((x + 3, 114), t, fontsize=10)
    return p


def plain_page(d):
    p = d.new_page(width=612, height=792)
    p.insert_text((72, 80), "Terms and conditions", fontsize=16)
    p.draw_line((72, 90), (540, 90), width=1)
    p.insert_textbox(pymupdf.Rect(72, 100, 540, 200), PARA * 2, fontsize=11)
    p.draw_line((72, 210), (540, 210), width=0.5)
    p.insert_textbox(pymupdf.Rect(72, 220, 540, 320), PARA, fontsize=11)
    p.insert_text((72, 350), "Underlined words here", fontsize=11)
    p.draw_line((72, 352), (190, 352), width=0.6)
    p.draw_rect((36, 36, 576, 756), width=1)            # the page's frame
    p.draw_rect((400, 400, 500, 480), color=(0, 0, 1), fill=(0.8, 0.8, 1))
    return p


def scanned_page(d):
    """A picture of a form (lines and words in the picture) with an OCR text layer."""
    src = pymupdf.open()
    q = src.new_page(width=612, height=792)
    q.insert_text((72, 100), "Name:", fontsize=11)
    q.draw_line((110, 102), (330, 102), width=1.2)
    q.insert_text((72, 140), "City:", fontsize=11)
    q.draw_line((105, 142), (330, 142), width=1.2)
    q.insert_text((72, 180), "Plain sentence with no blank in it at all.", fontsize=11)
    pix = q.get_pixmap(dpi=150)
    p = d.new_page(width=612, height=792)
    p.insert_image(p.rect, stream=pix.tobytes("png"))
    for y, text in ((100, "Name:"), (140, "City:"),
                    (180, "Plain sentence with no blank in it at all.")):
        p.insert_text((72, y), text, fontsize=11, render_mode=3)
    return p


def found(page):
    return [(f["kind"], f["name"]) for f in form_detect.detect(page)]


class Detect(unittest.TestCase):
    def test_blank_lines_underscores_and_a_signature_line(self):
        d = pymupdf.open()
        got = found(lines_form(d))
        self.assertEqual(got, [("text", "Name"), ("date", "Date"), ("text", "Address"),
                               ("text", "Phone"), ("signature", "Signature of applicant")])
        f = {f["name"]: f for f in form_detect.detect(d[0])}
        # the field sits on its line, after its label
        self.assertAlmostEqual(f["Name"]["rect"].y1, 101, delta=1.5)
        self.assertGreaterEqual(f["Name"]["rect"].x0, 109)
        self.assertGreater(f["Signature of applicant"]["rect"].height, 20)

    def test_boxes_and_checkboxes(self):
        d = pymupdf.open()
        self.assertEqual(found(boxes_form(d)), [("text", "Email"), ("check", "Yes, send me news"),
                                                ("check", "No"), ("text", "Company name")])

    def test_a_table_form(self):
        d = pymupdf.open()
        got = found(table_form(d))
        self.assertEqual([n for _k, n in got],
                         ["Description 1", "Qty 1", "Price 1", "Description 2", "Qty 2",
                          "Price 2", "Description 3", "Qty 3", "Price 3"])
        self.assertTrue(all(k == "text" for k, _n in got))

    def test_a_scanned_page_after_ocr(self):
        d = pymupdf.open()
        self.assertEqual(found(scanned_page(d)), [("text", "Name"), ("text", "City")])

    def test_nothing_in_plain_paragraphs(self):
        d = pymupdf.open()
        self.assertEqual(found(plain_page(d)), [])

    def test_rotated_page(self):
        d = pymupdf.open()
        p = lines_form(d)
        p.set_rotation(90)
        self.assertEqual(len(found(p)), 5)

    def test_existing_fields_are_left_alone(self):
        d = pymupdf.open()
        p = lines_form(d)
        have = [f["rect"] for f in form_detect.detect(p)]
        self.assertEqual(form_detect.detect(p, have), [])

    def test_labels_become_clean_names(self):
        self.assertEqual(form_detect.clean_label("1. Full name:"), "Full name")
        self.assertEqual(form_detect.clean_label("Applicant's e.mail *"), "Applicant's email")


class Quiet(unittest.TestCase):
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

    def open(self, build, name="f.pdf"):
        path = os.path.join(self.tmp.name, name)
        d = pymupdf.open()
        build(d)
        d.save(path)
        d.close()
        v = DocumentView(path)
        v.resize(700, 700)
        v.show()
        APP.processEvents()

        def close():
            if not v.doc.is_closed:
                v.dirty = False
                v.close_doc()
        self.addCleanup(close)
        return v

    @staticmethod
    def text_fields(*names, page_size=(612, 792)):
        def build(d):
            p = d.new_page(width=page_size[0], height=page_size[1])
            for k, n in enumerate(names):
                w = pymupdf.Widget()
                w.field_type = pymupdf.PDF_WIDGET_TYPE_TEXT
                w.field_name = n
                w.rect = pymupdf.Rect(100, 80 + 30 * k, 260, 100 + 30 * k)
                p.add_widget(w)
        return build

    def xrefs(self, v):
        pg = v.doc[0]
        return {w.field_name: w.xref for w in pg.widgets()}

    def values(self, v):
        out = {}
        for i in range(v.doc.page_count):
            pg = v.doc[i]
            for w in pg.widgets():
                out[w.field_name] = w.field_value
        return out

    def shown(self, v, i=0):
        return v.doc[i].get_text()

    def fill(self, v, name, text):
        return v.enter_field_value(0, self.xrefs(v)[name], text)

    def props(self, v, name, **props):
        return v.set_field_props(0, self.xrefs(v)[name], props)


class CreateDetected(Quiet):
    def test_detected_fields_are_made_in_one_undo_step(self):
        v = self.open(lambda d: (lines_form(d), table_form(d)))
        found = v.detect_fields()
        self.assertEqual(len(found), 14)
        self.assertEqual({f["page"] for f in found}, {0, 1})
        steps = len(v._undo)
        n = v.create_detected_fields(found)
        self.assertEqual(n, 14)
        self.assertEqual(len(v._undo), steps + 1)
        kinds = {w.field_name: w.field_type for i in range(2) for w in v.doc[i].widgets()}
        self.assertEqual(kinds["Signature of applicant"], pymupdf.PDF_WIDGET_TYPE_SIGNATURE)
        self.assertEqual(kinds["Qty 2"], pymupdf.PDF_WIDGET_TYPE_TEXT)
        # a "Date" label makes a date field: typed dates are checked and shown as mm/dd/yyyy
        self.assertTrue(self.fill(v, "Date", "11/6/26"))
        self.assertEqual(self.values(v)["Date"], "11/06/2026")
        self.assertFalse(self.fill(v, "Date", "13/45/2026"))
        self.assertEqual(self.values(v)["Date"], "11/06/2026")
        # nothing more is found where fields now are
        self.assertEqual(v.detect_fields(), [])
        v.undo()
        v.undo()
        self.assertEqual(sum(1 for i in range(2) for _ in v.doc[i].widgets()), 0)

    def test_only_what_is_kept_and_renamed(self):
        v = self.open(lambda d: lines_form(d))
        found = v.detect_fields()
        keep = [dict(found[0], name="Full name"), dict(found[3], kind="text")]
        v.create_detected_fields(keep)
        self.assertEqual(sorted(self.values(v)), ["Full name", "Phone"])

    def test_names_dont_clash_with_fields_already_there(self):
        v = self.open(lambda d: lines_form(d))
        v.create_field(0, "f_text", P(72, 400), P(200, 420), False)
        x = next(v.doc[0].widgets()).xref
        v.set_field_props(0, x, {"name": "Name"})
        names = [f["name"] for f in v.detect_fields()]
        self.assertIn("Name 2", names)
        self.assertNotIn("Name", names)


class Formulas(unittest.TestCase):
    def test_arithmetic_and_precedence(self):
        vals = {"a": 2.0, "b": 3.0, "Ship Cost": 5.0}

        def ev(text):
            return S.eval_formula(S.parse_formula(text), lambda n: vals[n])
        self.assertEqual(ev("a + b * 2"), 8)
        self.assertEqual(ev("(a + b) * 2"), 10)
        self.assertEqual(ev("a - b - 1"), -2)
        self.assertEqual(ev("-a + 10 / 4"), 0.5)
        self.assertEqual(ev("Ship\\ Cost * 2"), 10)
        with self.assertRaises(ZeroDivisionError):
            ev("a / (b - 3)")

    def test_anything_else_is_refused(self):
        for bad in ("a +", "a b", "__import__('os')", "a; b", "eval(1)", "a ** 2",
                    "(a", "a)", "", "1a", "a == b", "a[0]", "x.y()"):
            with self.subTest(bad=bad), self.assertRaises(S.FormulaError):
                S.parse_formula(bad)

    def test_written_and_read_back_as_acrobat_writes_them(self):
        js = S.calc_js({"formula": "Price*Qty + Ship\\ Cost"})
        self.assertTrue(js.startswith("/** BVCALC Price * Qty + Ship\\ Cost EVCALC **/"))
        self.assertIn('AFMakeNumber(getField("Ship Cost").value)', js)
        self.assertEqual(S.read_calc(js), {"formula": "Price * Qty + Ship\\ Cost"})
        js = S.calc_js({"op": "AVG", "fields": ["a", "b"]})
        self.assertEqual(js, 'AFSimple_Calculate("AVG", new Array ("a", "b"));')
        self.assertEqual(S.read_calc(js), {"op": "AVG", "fields": ["a", "b"]})

    def test_only_the_standard_calls_are_recognized(self):
        self.assertEqual(S.read_calc('AFSimple_Calculate("SUM", "a, b");'),
                         {"op": "SUM", "fields": ["a", "b"]})
        self.assertEqual(S.read_calc("AFSimple_Calculate('PRD', ['x', 'y'])"),
                         {"op": "PRD", "fields": ["x", "y"]})
        for custom in ('AFSimple_Calculate("SUM", new Array("a")); app.alert("hi");',
                       'event.value = 1 + 2;', 'AFSimple_Calculate("POW", ["a"])',
                       'AFSimple_Calculate("SUM", foo())',
                       '/** BVCALC a + EVCALC **/ event.value = 1;'):
            with self.subTest(js=custom):
                self.assertIn("custom", S.read_calc(custom))
        self.assertIsNone(S.parse_call("app.launchURL('x')"))
        self.assertIsNone(S.parse_call('AFNumber_Format(2, 0, 0, 0, "$", true) + x'))


class Calculations(Quiet):
    def test_sum_product_average_minimum_maximum(self):
        v = self.open(self.text_fields("a", "b", "c", "sum", "prd", "avg", "min", "max"))
        for op in ("SUM", "PRD", "AVG", "MIN", "MAX"):
            self.props(v, {"SUM": "sum", "PRD": "prd", "AVG": "avg", "MIN": "min",
                           "MAX": "max"}[op], calc={"op": op, "fields": ["a", "b", "c"]})
        for n, t in (("a", "2"), ("b", "3"), ("c", "7")):
            self.assertTrue(self.fill(v, n, t))
        vals = self.values(v)
        self.assertEqual([vals[n] for n in ("sum", "prd", "avg", "min", "max")],
                         ["12", "42", "4", "2", "7"])
        # an empty field counts as 0
        self.fill(v, "c", "")
        vals = self.values(v)
        self.assertEqual([vals[n] for n in ("sum", "prd", "min")], ["5", "0", "0"])

    def test_a_chain_is_calculated_in_order_and_co_follows_it(self):
        v = self.open(self.text_fields("Price", "Qty", "Subtotal", "Tax", "Total"))
        # set up last-first: the order the fields are calculated in must still work
        self.props(v, "Total", calc={"formula": "Subtotal + Tax"})
        self.props(v, "Tax", calc={"formula": "Subtotal * 0.1"})
        self.props(v, "Subtotal", calc={"formula": "Price * Qty"})
        form = S.read_form(v.doc)
        self.assertEqual(form.co, ["Subtotal", "Tax", "Total"])
        self.fill(v, "Price", "12.5")
        self.fill(v, "Qty", "4")
        vals = self.values(v)
        self.assertEqual((vals["Subtotal"], vals["Tax"], vals["Total"]), ("50", "5", "55"))

    def test_division_by_zero_leaves_the_field_empty(self):
        v = self.open(self.text_fields("a", "b", "ratio"))
        self.props(v, "ratio", calc={"formula": "a / b"})
        self.fill(v, "a", "10")
        self.fill(v, "b", "4")
        self.assertEqual(self.values(v)["ratio"], "2.5")
        self.fill(v, "b", "0")
        self.assertEqual(self.values(v)["ratio"], "")

    def test_a_loop_doesnt_hang(self):
        v = self.open(self.text_fields("a", "b", "x"))
        self.props(v, "a", calc={"formula": "b + 1"})
        self.props(v, "b", calc={"formula": "a + 1"})
        self.fill(v, "x", "3")
        order, looped = S.calc_order(S.read_form(v.doc))
        self.assertEqual(order, [])
        self.assertEqual(sorted(looped), ["a", "b"])

    def test_filling_in_and_recalculating_is_one_undo_step(self):
        v = self.open(self.text_fields("a", "b", "total"))
        self.props(v, "total", calc={"op": "SUM", "fields": ["a", "b"]})
        self.fill(v, "a", "5")
        steps = len(v._undo)
        self.fill(v, "b", "6")
        self.assertEqual(len(v._undo), steps + 1)
        self.assertEqual(self.values(v)["total"], "11")
        v.undo()
        self.assertEqual((self.values(v)["b"], self.values(v)["total"]), ("", "5"))
        v.redo()
        self.assertEqual((self.values(v)["b"], self.values(v)["total"]), ("6", "11"))

    def test_a_calculated_field_isnt_typed_in(self):
        v = self.open(self.text_fields("a", "total"))
        self.props(v, "total", calc={"op": "SUM", "fields": ["a"]})
        msgs = []
        v.statusMessage.connect(msgs.append)
        with mock.patch.object(DocumentView, "_edit_text_field") as edit:
            v.fill_field(0, self.xrefs(v)["total"])
            edit.assert_not_called()
        self.assertTrue(any("calculated" in m for m in msgs))

    def test_checkboxes_and_dropdowns_feed_calculations(self):
        def build(d):
            self.text_fields("total")(d)
            p = d[0]
            w = pymupdf.Widget()
            w.field_type = pymupdf.PDF_WIDGET_TYPE_COMBOBOX
            w.field_name = "pick"
            w.choice_values = ["1", "5", "10"]
            w.field_value = "1"
            w.rect = pymupdf.Rect(300, 80, 400, 100)
            p.add_widget(w)
        v = self.open(build)
        self.props(v, "total", calc={"formula": "pick * 2"})
        v._set_field(0, self.xrefs(v)["pick"], "5")
        self.assertEqual(self.values(v)["total"], "10")


def acrobat_form(d):
    """Fields as Acrobat writes them: field and widget in one dictionary, a group "Price"
    with kids Price.0 and Price.1, totals with AFSimple_Calculate (a list and a comma
    string), a formula in simplified field notation, a custom script, and /CO."""
    p = d.new_page()
    xref = d.get_new_xref

    def widget(name, y, aa="", parent=None):
        x = xref()
        par = f"/Parent {parent} 0 R " if parent else ""
        ft = "" if parent else "/FT /Tx "
        d.update_object(x, f"<< /Type /Annot /Subtype /Widget {ft}/T ({name}) {par}"
                           f"/Rect [72 {y} 250 {y + 20}] /F 4 /DA (/Helv 0 Tf 0 g) "
                           f"/P {p.xref} 0 R {aa}>>")
        return x
    group = xref()
    kids = [widget("0", 700, parent=group), widget("1", 670, parent=group)]
    d.update_object(group, "<< /FT /Tx /T (Price) /Kids [%s] >>" % " ".join(
        f"{k} 0 R" for k in kids))

    def js(text):
        return "<< /S /JavaScript /JS %s >>" % pymupdf.get_pdf_str(text)
    total = widget("Total", 640, "/AA << /C %s /F %s /K %s >>" % (
        js('AFSimple_Calculate("SUM", new Array ("Price"));'),
        js('AFNumber_Format(2, 0, 0, 0, "$", true);'),
        js('AFNumber_Keystroke(2, 0, 0, 0, "$", true);')))
    avg = widget("Avg", 610, "/AA << /C %s >>" % js(
        'AFSimple_Calculate("AVG", "Price.0, Price.1");'))
    sfn = widget("Double", 580, "/AA << /C %s >>" % js(
        '/** BVCALC Total*2 EVCALC **/ event.value = AFMakeNumber(getField("Total").value)*2;'))
    custom = widget("Secret", 550, "/AA << /C %s >>" % js(
        'event.value = 42; app.launchURL("http://example.com");'))
    fields = [group, total, avg, sfn, custom]
    d.xref_set_key(p.xref, "Annots", "[%s]" % " ".join(f"{k} 0 R" for k in kids + fields[1:]))
    d.xref_set_key(d.pdf_catalog(), "AcroForm",
                   "<< /Fields [%s] /CO [%s] /DA (/Helv 0 Tf 0 g) >>" % (
                       " ".join(f"{k} 0 R" for k in fields),
                       " ".join(f"{k} 0 R" for k in fields[1:])))


class AcrobatForms(Quiet):
    def test_acrobat_calculations_are_recognized_and_done_the_same_way(self):
        v = self.open(acrobat_form)
        form = v.smart_form()
        self.assertEqual(form.fields["Total"].calc, {"op": "SUM", "fields": ["Price"]})
        self.assertEqual(form.fields["Avg"].calc, {"op": "AVG", "fields": ["Price.0", "Price.1"]})
        self.assertEqual(form.fields["Double"].calc, {"formula": "Total * 2"})
        self.assertIn("custom", form.fields["Secret"].calc)
        pg = v.doc[0]
        xs = {w.field_name: w.xref for w in pg.widgets()}
        self.assertTrue(v.enter_field_value(0, xs["Price.0"], "5"))
        self.assertTrue(v.enter_field_value(0, xs["Price.1"], "7.25"))
        vals = self.values(v)
        self.assertEqual((vals["Total"], vals["Avg"], vals["Double"]), ("12.25", "6.125", "24.5"))
        self.assertIn("$12.25", self.shown(v))
        # the custom script is never run: its field stays as it was
        self.assertEqual(vals["Secret"], "")
        props = v.field_props(0, xs["Secret"])
        self.assertIn("launchURL", props["calc"]["custom"])

    def test_custom_scripts_are_kept_when_other_properties_change(self):
        v = self.open(acrobat_form)
        pg = v.doc[0]
        xs = {w.field_name: w.xref for w in pg.widgets()}
        v.set_field_props(0, xs["Secret"], {"tooltip": "Not run here"})
        form = S.read_form(v.doc)
        self.assertIn("launchURL", form.fields["Secret"].calc["custom"])
        self.assertIn("Secret", form.co)
        self.assertEqual(form.fields["Secret"].tu, "Not run here")


class Formats(Quiet):
    def test_number_format_shows_formatted_and_keeps_the_number(self):
        v = self.open(self.text_fields("amount"))
        self.props(v, "amount", format={"kind": "number", "decimals": 2, "sep": 0, "neg": 2,
                                        "currency": "$", "prepend": True})
        self.assertTrue(self.fill(v, "amount", "$1,234.5"))
        self.assertEqual(self.values(v)["amount"], "1234.5")
        self.assertIn("$1,234.50", self.shown(v))
        self.assertTrue(self.fill(v, "amount", "-20"))
        self.assertIn("($20.00)", self.shown(v))
        self.assertFalse(self.fill(v, "amount", "twelve"))
        self.assertEqual(self.values(v)["amount"], "-20")
        self.assertTrue(self.warnings and "number" in self.warnings[-1])

    def test_percent_date_and_special_formats(self):
        v = self.open(self.text_fields("pct", "when", "zip", "phone", "ssn"))
        self.props(v, "pct", format={"kind": "percent", "decimals": 1, "sep": 0})
        self.props(v, "when", format={"kind": "date", "pattern": "mmmm d, yyyy"})
        self.props(v, "zip", format={"kind": "special", "which": 0})
        self.props(v, "phone", format={"kind": "special", "which": 2})
        self.props(v, "ssn", format={"kind": "special", "which": 3})
        self.assertTrue(self.fill(v, "pct", "25%"))
        self.assertTrue(self.fill(v, "when", "2026-11-06"))
        self.assertTrue(self.fill(v, "phone", "555 123 4567"))
        self.assertTrue(self.fill(v, "ssn", "123456789"))
        self.assertFalse(self.fill(v, "zip", "1234"))
        self.assertTrue(self.fill(v, "zip", "90210"))
        vals = self.values(v)
        self.assertEqual((vals["pct"], vals["when"], vals["phone"], vals["ssn"]),
                         ("0.25", "November 6, 2026", "5551234567", "123456789"))
        text = self.shown(v)
        for shown in ("25.0%", "November 6, 2026", "(555) 123-4567", "123-45-6789", "90210"):
            self.assertIn(shown, text)

    def test_range_check(self):
        v = self.open(self.text_fields("score"))
        self.props(v, "score", range={"min": 0, "max": 100})
        self.assertTrue(self.fill(v, "score", "75"))
        self.assertFalse(self.fill(v, "score", "150"))
        self.assertIn("between 0 and 100", self.warnings[-1])
        self.assertFalse(self.fill(v, "score", "abc"))
        self.assertEqual(self.values(v)["score"], "75")
        self.assertTrue(self.fill(v, "score", ""))

    def test_typing_letters_into_a_number_field_is_blocked(self):
        v = self.open(self.text_fields("n"))
        self.props(v, "n", format={"kind": "number", "decimals": 0, "sep": 0, "neg": 0,
                                   "currency": "", "prepend": True})
        from PySide6.QtWidgets import QLineEdit
        v._edit_text_field(0, self.xrefs(v)["n"])
        ed = v.findChild(QLineEdit)
        self.assertIsNotNone(ed.validator())
        from PySide6.QtGui import QValidator
        self.assertEqual(ed.validator().validate("12a", 3)[0], QValidator.Invalid)
        self.assertEqual(ed.validator().validate("1,200.5", 7)[0], QValidator.Acceptable)
        v.commit_pending()

    def test_reading_acrobat_format_calls(self):
        self.assertEqual(S.read_format('AFNumber_Format(0, 2, 0, 0, "\\u20ac", false);'),
                         {"kind": "number", "decimals": 0, "sep": 2, "neg": 0,
                          "currency": "€", "prepend": False})
        self.assertEqual(S.read_format("AFDate_FormatEx(\"dd/mm/yyyy\");"),
                         {"kind": "date", "pattern": "dd/mm/yyyy"})
        self.assertEqual(S.read_format("AFDate_Format(2);"),
                         {"kind": "date", "pattern": "mm/dd/yy"})
        self.assertEqual(S.read_format("AFSpecial_Format(3);"), {"kind": "special", "which": 3})
        self.assertEqual(S.read_validate("AFRange_Validate(true, 1, false, 0);"),
                         {"min": 1.0, "max": None})
        self.assertIn("custom", S.read_format('AFTime_Format(0);'))
        self.assertEqual(S.format_value({"kind": "number", "decimals": 2, "sep": 2, "neg": 0,
                                         "currency": " €", "prepend": False}, "1234.5"),
                         "1.234,50 €")


class Required(Quiet):
    def test_empty_required_fields_are_flagged_with_a_notice(self):
        v = self.open(self.text_fields("name", "email", "notes"))
        self.props(v, "name", required=True)
        self.props(v, "email", required=True)
        self.assertEqual(v.check_required_fields(), ["name", "email"])
        self.assertEqual(v._banner_kind, "required")
        self.assertIn("name, email", v._banner_label.text())
        self.assertEqual(len(v.required_flag_rects(0)), 2)
        self.fill(v, "name", "Jane")
        self.assertEqual(len(v.required_flag_rects(0)), 1)
        self.fill(v, "email", "jane@example.com")
        self.assertEqual(v.required_flag_rects(0), [])
        self.assertNotEqual(getattr(v, "_banner_kind", None), "required")

    def test_required_checkbox_and_option_group(self):
        v = self.open(self.text_fields("name"))
        v.create_field(0, "f_check", P(320, 90), P(320, 90), True)
        with mock.patch("PySide6.QtWidgets.QInputDialog.getItem", return_value=("Pick", True)):
            for y in (150, 180):
                v.create_field(0, "f_radio", P(320, y), P(320, y), True)
        pg = v.doc[0]
        ws = {w.xref: w.field_type for w in pg.widgets()}
        check = next(x for x, t in ws.items() if t == pymupdf.PDF_WIDGET_TYPE_CHECKBOX)
        radios = [x for x, t in ws.items() if t == pymupdf.PDF_WIDGET_TYPE_RADIOBUTTON]
        v.set_field_props(0, check, {"required": True})
        v.set_field_props(0, radios[0], {"required": True})
        v.set_field_props(0, radios[1], {"required": True})
        self.assertEqual(sorted(v.check_required_fields()), ["Check1", "Pick"])
        v.fill_field(0, check)
        v.fill_field(0, radios[1])
        self.assertEqual(v.check_required_fields(), [])

    def test_save_and_print_show_the_notice_but_go_on(self):
        from kanzonas.main_window import MainWindow
        path = os.path.join(self.tmp.name, "req.pdf")
        d = pymupdf.open()
        self.text_fields("name")(d)
        d.save(path)
        win = MainWindow()
        self.addCleanup(win.close)
        win.open_file(path)
        v = win.view()
        v.set_field_props(0, next(v.doc[0].widgets()).xref, {"required": True})
        self.assertTrue(win.save())
        self.assertEqual(v._banner_kind, "required")
        self.assertTrue(pymupdf.open(path)[0].first_widget.field_flags & 2)
        v.hide_banner()
        with mock.patch("kanzonas.print_dialog.PrintDialog") as dlg:
            dlg.return_value.exec.return_value = 0
            win.print_doc()
            dlg.assert_called_once()
        self.assertEqual(v._banner_kind, "required")
        v.dirty = False


class SaveAndReopen(Quiet):
    def test_everything_is_kept_and_the_actions_are_well_formed(self):
        v = self.open(self.text_fields("Price", "Qty", "Total", "When"))
        self.props(v, "Total", calc={"formula": "Price * Qty"}, tooltip="Price times quantity",
                   format={"kind": "number", "decimals": 2, "sep": 0, "neg": 0, "currency": "$",
                           "prepend": True}, readonly=True)
        self.props(v, "Qty", range={"min": 1, "max": 99}, required=True)
        self.props(v, "When", format={"kind": "date", "pattern": "dd/mm/yyyy"})
        self.fill(v, "Price", "2.5")
        self.fill(v, "Qty", "4")
        v.save()
        d = pymupdf.open(v.path)
        form = S.read_form(d)
        self.assertEqual(form.fields["Total"].calc, {"formula": "Price * Qty"})
        self.assertEqual(form.fields["Total"].fmt["currency"], "$")
        self.assertEqual(form.fields["Total"].tu, "Price times quantity")
        self.assertTrue(form.fields["Total"].ff & 1)
        self.assertEqual(form.fields["Qty"].rng, {"min": 1.0, "max": 99.0})
        self.assertTrue(form.fields["Qty"].ff & 2)
        self.assertEqual(form.fields["When"].fmt, {"kind": "date", "pattern": "dd/mm/yyyy"})
        self.assertEqual(form.co, ["Total"])
        self.assertEqual(S.field_value(d, form.fields["Total"].fx), "10")
        self.assertIn("$10.00", d[0].get_text())
        # each action is << /S /JavaScript /JS (...) >> with a call a reader recognizes
        for name, keys in (("Total", "KFC"), ("Qty", "V"), ("When", "KF")):
            fx = form.fields[name].fx
            for k in keys:
                self.assertEqual(d.xref_get_key(fx, f"AA/{k}/S"), ("name", "/JavaScript"))
                kind, js = d.xref_get_key(fx, f"AA/{k}/JS")
                self.assertEqual(kind, "string")
                if k != "C":
                    self.assertIsNotNone(S.parse_call(js), js)
        co = d.xref_get_key(d.pdf_catalog(), "AcroForm/CO")
        self.assertEqual(co, ("array", f"[{form.fields['Total'].fx} 0 R]"))
        # nothing that isn't a standard call is written
        raw = d.tobytes(expand=255).decode("latin-1")
        for js in re.findall(r"/JS\s*\((.*?)\)\s*>>", raw):
            self.assertTrue(js.startswith(("/** BVCALC ", "AF")), js)
        d.close()

    def test_removing_a_calculation_takes_it_out_of_co(self):
        v = self.open(self.text_fields("a", "total"))
        self.props(v, "total", calc={"op": "SUM", "fields": ["a"]})
        self.props(v, "total", calc=None, format=None)
        form = S.read_form(v.doc)
        self.assertIsNone(form.fields["total"].calc)
        self.assertEqual(form.co, [])
        self.assertEqual(v.doc.xref_get_key(form.fields["total"].fx, "AA")[0], "null")

    def test_properties_are_one_undo_step(self):
        v = self.open(self.text_fields("a", "total"))
        self.fill(v, "a", "3")
        steps = len(v._undo)
        self.props(v, "total", calc={"op": "SUM", "fields": ["a"]}, required=True,
                   tooltip="Sum")
        self.assertEqual(len(v._undo), steps + 1)
        self.assertEqual(self.values(v)["total"], "3")     # worked out right away
        v.undo()
        form = S.read_form(v.doc)
        self.assertIsNone(form.fields["total"].calc)
        self.assertEqual(form.co, [])
        self.assertEqual(self.values(v)["total"], "")
        self.assertFalse(form.fields["total"].ff & 2)


class TabOrder(Quiet):
    def grid(self, d):
        p = d.new_page()
        for r in range(2):
            for c in range(2):
                w = pymupdf.Widget()
                w.field_type = pymupdf.PDF_WIDGET_TYPE_TEXT
                w.field_name = f"r{r}c{c}"
                w.rect = pymupdf.Rect(100 + 200 * c, 100 + 50 * r, 250 + 200 * c, 120 + 50 * r)
                p.add_widget(w)

    def names(self, v):
        pg = v.doc[0]
        return [pg.load_widget(x).field_name for _i, x in v.field_order()]

    def test_rows_columns_and_manual(self):
        v = self.open(self.grid)
        self.assertEqual(self.names(v), ["r0c0", "r0c1", "r1c0", "r1c1"])
        v.set_tab_order([0], "columns")
        self.assertEqual(self.names(v), ["r0c0", "r1c0", "r0c1", "r1c1"])
        xs = self.xrefs(v)
        v.set_tab_order([0], "manual", {0: [xs["r1c1"], xs["r0c0"], xs["r1c0"], xs["r0c1"]]})
        self.assertEqual(self.names(v), ["r1c1", "r0c0", "r1c0", "r0c1"])
        v.save()
        d = pymupdf.open(v.path)
        self.assertEqual(d.xref_get_key(d[0].xref, "Tabs"), ("name", "/A"))
        d.close()
        v.undo()
        self.assertEqual(self.names(v), ["r0c0", "r1c0", "r0c1", "r1c1"])

    def test_the_tab_order_window(self):
        from kanzonas import form_ui
        v = self.open(self.grid)
        dlg = form_ui.TabOrderDialog(v, 0)
        self.assertTrue(dlg.rows.isChecked())
        self.assertEqual([dlg.list.item(k).text() for k in range(4)],
                         ["r0c0", "r0c1", "r1c0", "r1c1"])
        dlg.list.setCurrentRow(3)
        dlg._move(-1)
        dlg._move(-1)
        self.assertTrue(dlg.manual.isChecked())
        dlg.apply()
        dlg.close()
        self.assertEqual(self.names(v), ["r0c0", "r1c1", "r0c1", "r1c0"])
        dlg = form_ui.TabOrderDialog(v, 0)
        self.assertTrue(dlg.manual.isChecked())
        dlg.cols.setChecked(True)
        dlg.apply()
        dlg.close()
        self.assertEqual(self.names(v), ["r0c0", "r1c0", "r0c1", "r1c1"])

    def test_place_in_the_tab_order_from_field_properties(self):
        v = self.open(self.grid)
        self.props(v, "r1c1", tab=1)
        self.assertEqual(self.names(v), ["r1c1", "r0c0", "r0c1", "r1c0"])
        self.assertEqual(v.field_props(0, self.xrefs(v)["r1c1"])["tab"], 1)


class Dialogs(Quiet):
    def test_field_properties_window_round_trip(self):
        from kanzonas import form_ui
        v = self.open(self.text_fields("a", "b", "total"))
        x = self.xrefs(v)["total"]
        props = v.field_props(0, x)
        dlg = form_ui.FieldPropertiesDialog(v, props)
        dlg.c_formula.setChecked(True)
        dlg.formula.setText("a*b")
        dlg.fmt_kind.setCurrentIndex(dlg.fmt_kind.findData("number"))
        dlg.currency.setText("$")
        dlg.required.setChecked(True)
        dlg.accept()
        out = dlg.out
        self.assertEqual(out["calc"], {"formula": "a * b"})
        self.assertEqual(out["format"]["currency"], "$")
        with mock.patch.object(form_ui, "edit_field", return_value=out):
            v.edit_field_properties(0, x)
        self.fill(v, "a", "3")
        self.fill(v, "b", "4")
        self.assertIn("$12.00", self.shown(v))
        # an unknown name or a field calculated from itself is refused in the window
        dlg = form_ui.FieldPropertiesDialog(v, v.field_props(0, x))
        dlg.formula.setText("a * nope")
        dlg.accept()
        self.assertFalse(hasattr(dlg, "out"))

    def test_detect_window_keeps_what_is_ticked(self):
        from kanzonas import form_ui
        from PySide6.QtCore import Qt
        v = self.open(lambda d: lines_form(d))
        found = v.detect_fields()
        dlg = form_ui.DetectDialog(v, found)
        self.assertEqual(len(v.detect_preview_rects(0)), len(found))
        dlg.table.item(1, 0).setCheckState(Qt.Unchecked)
        dlg.table.item(0, 3).setText("Applicant")
        chosen = dlg.chosen()
        dlg.reject()
        self.assertIsNone(v.detect_preview)
        self.assertEqual(len(chosen), len(found) - 1)
        self.assertEqual(chosen[0]["name"], "Applicant")


class Menus(Quiet):
    def test_forms_menu_and_right_click(self):
        from PySide6.QtCore import QPointF, Qt
        from PySide6.QtGui import QMouseEvent
        from PySide6.QtWidgets import QMenu
        from kanzonas.main_window import MainWindow
        path = os.path.join(self.tmp.name, "menus.pdf")
        d = pymupdf.open()
        self.text_fields("a", "b")(d)
        d.save(path)
        win = MainWindow()
        self.addCleanup(win.close)
        win.open_file(path)
        v = win.view()
        forms = next(a.menu() for a in win.menuBar().actions()
                     if a.menu() and a.text().replace("&", "") == "Forms")
        texts = [a.text() for a in forms.actions()]
        for act in (win.a_detect_fields, win.a_field_props, win.a_tab_order,
                    win.a_check_required):
            self.assertIn(act.text(), texts)
            self.assertTrue(act.isEnabled())
        # Field properties... with no field selected says how to select one
        with mock.patch.object(QMessageBox, "information") as info:
            win.field_properties()
            info.assert_called_once()
        # right-click on a field: its own menu
        shown = []

        class Menu(QMenu):
            def exec(self, *_a):
                shown.append([x.text() for x in self.actions() if not x.isSeparator()])
        pw = v.pages[0]
        pg = v.doc[0]
        r = pg.first_widget.rect
        pos = QPointF((r.x0 + 5) * v.zoom, (r.y0 + 5) * v.zoom)
        ev = QMouseEvent(QMouseEvent.MouseButtonPress, pos, pw.mapToGlobal(pos),
                         Qt.RightButton, Qt.RightButton, Qt.NoModifier)
        with mock.patch("PySide6.QtWidgets.QMenu", Menu):
            pw._content_menu(ev, pw.to_pdf(pos))
            win.set_tool("f_text")
            pw._content_menu(ev, pw.to_pdf(pos))
            far = QPointF(500 * v.zoom, 700 * v.zoom)
            pw._content_menu(QMouseEvent(QMouseEvent.MouseButtonPress, far, pw.mapToGlobal(far),
                                         Qt.RightButton, Qt.RightButton, Qt.NoModifier),
                             pw.to_pdf(far))
        self.assertEqual(shown[0], ["Field properties...", "Set tab order..."])
        self.assertEqual(shown[1], ["Field properties...", "Set tab order...", "Delete field"])
        self.assertEqual(shown[2][:2], ["Detect form fields...", "Set tab order..."])
        # with a field selected, Field properties... opens it
        self.assertEqual(v.selected_field()[1], pg.first_widget.xref)
        with mock.patch("kanzonas.form_ui.edit_field", return_value=None) as edit:
            win.field_properties()
            self.assertEqual(edit.call_args[0][1]["name"], "a")
        v.dirty = False


if __name__ == "__main__":
    unittest.main()
