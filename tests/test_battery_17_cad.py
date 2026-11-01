"""Break-it battery for 1.7's quicker CAD reading, Erase content and redaction.

Each test here failed before its fix. Hidden-text cases run in a child process: what broke
there was a crash of MuPDF itself (a segmentation fault ends the whole app, losing the work).

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_battery_17_cad
"""
import os
import subprocess
import sys
import textwrap
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402

from kanzonas import pdf_speed  # noqa: E402

SCRUB = dict(attached_files=True, clean_pages=True, embedded_files=True, hidden_text=True,
             javascript=True, metadata=True, redactions=False, remove_links=False,
             reset_fields=False, reset_responses=True, thumbnails=True, xml_metadata=True)


def page_with(doc, content, res=None):
    pg = doc.new_page()
    x = doc.get_new_xref()
    doc.update_object(x, "<<>>")
    doc.update_stream(x, content)
    pg.set_contents(x)
    if res:
        doc.xref_set_key(pg.xref, "Resources", res)
    return pg


def nested_actualtext_doc():
    """ActualText inside ActualText around drawings (tagged PDFs have it): MuPDF 1.28's text
    device crashed on these when collecting vectors; PyMuPDF's own hidden-text search reads
    them fine."""
    d = pymupdf.open()
    page_with(d, b"/Span <</ActualText (OUTER)>> BDC /Span <</ActualText (INNER)>> BDC "
                 b"10 10 m 100 100 l S EMC EMC")
    page_with(d, b"/Span <</ActualText (A)>> BDC /Span <</ActualText (B)>> BDC "
                 b"10 10 90 90 re f EMC EMC")
    form = d.get_new_xref()
    d.update_object(form, "<</Type/XObject/Subtype/Form/BBox[0 0 595 842]/Resources<<>>>>")
    d.update_stream(form, b"/Span <</ActualText (B)>> BDC 1 1 m 9 9 l S EMC")
    page_with(d, b"/Span <</ActualText (A)>> BDC /Fm0 Do EMC",
              "<</XObject<</Fm0 %d 0 R>>>>" % form)
    page_with(d, b"/Span <</ActualText (A)>> BDC 10 10 m 90 90 l S EMC")     # not nested
    p = d.new_page()                                    # lines only: still skipped
    for i in range(50):
        p.draw_line((10 + i, 10), (10 + i, 300), width=0.3)
    return d.tobytes()


def run_child(code, *args):
    """Run code in a child Python (a crash there doesn't end the tests)."""
    return subprocess.run([sys.executable, "-c", textwrap.dedent(code)] + list(args),
                          capture_output=True, text=True, cwd=ROOT, timeout=300)


class HiddenTextSearch(unittest.TestCase):
    def test_nested_actualtext_does_not_crash_and_matches_pymupdf(self):
        import tempfile
        tmp = tempfile.mkdtemp()
        src = os.path.join(tmp, "nested.pdf")
        with open(src, "wb") as f:
            f.write(nested_actualtext_doc())
        r = run_child("""
            import sys, pymupdf
            from kanzonas import pdf_speed
            from tests.test_battery_17_cad import SCRUB
            d = pymupdf.open(sys.argv[1])
            print([pdf_speed.page_has_no_text(p) for p in d])
            before = pdf_speed.skipped_searches
            pdf_speed.scrub(d, **SCRUB)
            print(pdf_speed.skipped_searches - before)
            open(sys.argv[2], "wb").write(d.tobytes(garbage=4, no_new_id=True))
        """, src, os.path.join(tmp, "quick.pdf"))
        self.assertEqual(r.returncode, 0, "the check crashed: %s" % r.stderr[-500:])
        flags, skipped = r.stdout.strip().splitlines()[-2:]
        self.assertEqual(flags, "[False, False, False, False, True]")
        self.assertEqual(skipped, "1")
        own = pymupdf.open(src)
        own.scrub(**SCRUB)
        with open(os.path.join(tmp, "quick.pdf"), "rb") as f:
            self.assertEqual(f.read(), own.tobytes(garbage=4, no_new_id=True))

    def test_a_page_with_only_replacement_text_is_searched(self):
        d = pymupdf.open()
        page_with(d, b"/Span <</ActualText (SECRET)>> BDC EMC")
        page_with(d, b"/Span <</Alt (described)>> BDC 1 1 m 9 9 l S EMC")
        self.assertEqual([pdf_speed.page_has_no_text(p) for p in d], [False, False])


if __name__ == "__main__":
    unittest.main()
