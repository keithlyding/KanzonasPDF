"""MuPDF 1.28's text reading crashed the whole program (a segmentation fault) on a page with
ActualText inside ActualText around a picture or drawing: Find, text selection, Edit text and
copying read text. kanzonas/text_guard.py reads such pages with TEXT_IGNORE_ACTUALTEXT. Each
case runs in a child process, so a crash fails the test instead of ending the test run.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_text_guard
"""
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

NEST = b"/Span <</ActualText (OUTER)>> BDC /Span <</ActualText (INNER)>> BDC %s EMC EMC"
DRAW_IMG = b"q 40 0 0 40 100 600 cm /Im0 Do Q"
DRAW_FILL = b"10 10 90 90 re f"


def _png():
    pm = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 8, 8), False)
    pm.clear_with(100)
    return pm.tobytes("png")


def _page(d, content, img=True, text=False):
    p = d.new_page()
    if text:
        p.insert_text((72, 72), "Normal words here", fontsize=12)
    if img:
        p.insert_image((300, 300, 340, 340), stream=_png())
        name = d.get_page_images(p.number)[0][7]
        content = content.replace(b"/Im0", b"/" + name.encode())
    xs = p.get_contents()
    if xs:
        d.update_stream(xs[0], d.xref_stream(xs[0]) + b"\n" + content)
    else:
        x = d.get_new_xref()
        d.update_object(x, "<<>>")
        d.update_stream(x, content)
        p.set_contents(x)
    return p


def cases(folder):
    out = {}

    def save(name, d):
        path = os.path.join(folder, name + ".pdf")
        d.save(path)
        out[name] = path

    d = pymupdf.open(); _page(d, NEST % DRAW_IMG); save("picture", d)
    d = pymupdf.open(); _page(d, NEST % DRAW_FILL, img=False); save("fill", d)
    d = pymupdf.open(); _page(d, NEST % DRAW_IMG, text=True); save("picture_after_text", d)
    # three levels
    d = pymupdf.open()
    _page(d, b"/Span <</ActualText (A)>> BDC " + NEST % DRAW_IMG + b" EMC"); save("three", d)
    # the name written with an escape: /Actual#54ext
    d = pymupdf.open()
    _page(d, (NEST % DRAW_IMG).replace(b"/ActualText", b"/Actual#54ext")); save("escaped", d)
    # the ActualText in the page's /Properties, named in the content
    d = pymupdf.open()
    p = _page(d, b"/Span /MC0 BDC /Span /MC1 BDC q 40 0 0 40 100 600 cm /Im0 Do Q EMC EMC")
    a, b = d.get_new_xref(), d.get_new_xref()
    d.update_object(a, "<</ActualText (OUTER)>>")
    d.update_object(b, "<</ActualText (INNER)>>")
    res = d.xref_get_key(p.xref, "Resources")
    rx = int(res[1].split()[0]) if res[0] == "xref" else None
    target = rx if rx else p.xref
    key = "Properties" if rx else "Resources/Properties"
    d.xref_set_key(target, key, "<</MC0 %d 0 R /MC1 %d 0 R>>" % (a, b))
    save("properties", d)
    # inside a form XObject the page draws
    d = pymupdf.open()
    p = _page(d, b"")
    img_name = d.get_page_images(0)[0][7]
    img_x = d.get_page_images(0)[0][0]
    f = d.get_new_xref()
    d.update_object(f, "<</Type/XObject/Subtype/Form/BBox[0 0 612 792]"
                       "/Resources<</XObject<</%s %d 0 R>>>>>>" % (img_name, img_x))
    d.update_stream(f, (NEST % DRAW_IMG).replace(b"/Im0", b"/" + img_name.encode()))
    x = p.get_contents()[0]
    res = d.xref_get_key(p.xref, "Resources")
    rx = int(res[1].split()[0]) if res[0] == "xref" else p.xref
    pre = "XObject" if res[0] == "xref" else "Resources/XObject"
    d.xref_set_key(rx, pre + "/Fm0", "%d 0 R" % f)
    d.update_stream(x, d.xref_stream(x) + b"\nq /Fm0 Do Q")
    save("form", d)
    # in a markup's appearance
    d = pymupdf.open()
    p = d.new_page()
    a = p.add_rect_annot((100, 100, 200, 200))
    a.update()
    ap = int(d.xref_get_key(a.xref, "AP/N")[1].split()[0])
    del a
    d.update_stream(ap, NEST % DRAW_FILL)
    save("markup", d)
    return out


CALLS = ['p.get_text()', 'p.search_for("OUTER")', 'p.get_text("words")', 'p.get_text("dict")',
         'p.get_text("rawdict")', 'p.get_text(flags=pymupdf.TEXT_PRESERVE_IMAGES)',
         'p.get_text("dict", flags=pymupdf.TEXT_PRESERVE_SPANS|pymupdf.TEXT_COLLECT_VECTORS)',
         'p.get_text("dict", flags=pymupdf.TEXT_PRESERVE_SPANS|pymupdf.TEXT_COLLECT_STYLES)']

CHILD = """
import sys, pymupdf
from kanzonas import annotations          # (puts the guard in place, as the app does)
d = pymupdf.open(sys.argv[1]); p = d[0]
for call in sys.argv[2:]:
    eval(call)
print("ok")
"""

APP_CHILD = """
import os, sys
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6.QtWidgets import QApplication
app = QApplication([])
import pymupdf
from kanzonas import text_edit
from kanzonas.document_view import DocumentView
v = DocumentView(sys.argv[1])
page = v.doc[0]
text_edit.page_text_dict(page, pymupdf.TEXTFLAGS_DICT)   # (Edit text, Cut, Replace)
text_edit.text_lines(page)
del page
v.find("OUTER")                           # (Find runs in slices on the event loop)
import time
t = time.monotonic()
while getattr(v, "_search_todo", None) and time.monotonic() - t < 30:
    app.processEvents()
v.dirty = False
v.close_doc()
print("ok")
"""


def run(code, *args):
    env = dict(os.environ, PYTHONPATH=ROOT, QT_QPA_PLATFORM="offscreen")
    return subprocess.run([sys.executable, "-c", code] + list(args), capture_output=True,
                          text=True, env=env, timeout=120)


class Guard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.mkdtemp()
        cls.cases = cases(cls.folder)

    def test_no_text_reading_crashes(self):
        for name, path in self.cases.items():
            r = run(CHILD, path, *CALLS)
            self.assertEqual(r.returncode, 0, "%s: %s" % (name, r.stderr[-500:]))
            self.assertIn("ok", r.stdout, name)

    def test_through_the_app(self):
        for name in ("picture", "form", "markup"):
            r = run(APP_CHILD, self.cases[name])
            self.assertEqual(r.returncode, 0, "%s: %s" % (name, r.stderr[-500:]))

    def test_only_nested_pages_are_read_without_actualtext(self):
        from kanzonas import text_guard
        self.assertTrue(text_guard.apply())
        for name in ("picture", "three", "escaped", "properties", "form", "markup", "fill"):
            with pymupdf.open(self.cases[name]) as d:
                self.assertTrue(text_guard.risky(d[0]), name)
        # one ActualText (not nested), or none: read as before, ActualText applied
        d = pymupdf.open()
        p = d.new_page()
        p.insert_text((72, 72), "Body", fontsize=12)
        x = p.get_contents()[0]
        d.update_stream(x, d.xref_stream(x) + b"\n/Span <</ActualText (LOGOWORD)>> BDC BT "
                        b"/Helv 12 Tf 100 600 Td (L0G0) Tj ET EMC")
        self.assertFalse(text_guard.risky(p))
        self.assertIn("LOGOWORD", p.get_text())
        q = d.new_page()
        q.insert_text((72, 72), "Plain words", fontsize=12)
        self.assertFalse(text_guard.risky(q))

    def test_the_answer_follows_a_change_to_the_page(self):
        from kanzonas import text_guard
        d = pymupdf.open()
        p = d.new_page()
        p.insert_text((72, 72), "Plain", fontsize=12)
        self.assertFalse(text_guard.risky(p))
        x = p.get_contents()[0]
        d.update_stream(x, d.xref_stream(x) + b"\n" + NEST % DRAW_FILL)
        self.assertTrue(text_guard.risky(p))

    def test_redaction_search_is_left_as_it_was(self):
        # (TEXT_COLLECT_STYLES: Remove hidden information's search, which doesn't crash;
        # what redaction removes must not change)
        from kanzonas import text_guard
        with pymupdf.open(self.cases["picture"]) as d:
            f = pymupdf.TEXT_PRESERVE_SPANS | pymupdf.TEXT_COLLECT_STYLES
            self.assertEqual(text_guard.flags_for(d[0], f), f)


if __name__ == "__main__":
    unittest.main()
