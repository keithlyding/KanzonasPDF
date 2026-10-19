"""Option (radio) buttons stay mutually exclusive: groups made with the Option button tool
(each button gets its own 'on' state name; PyMuPDF would give them all the same one, and
2.0 makes them kids of one parent field) and groups written the way Acrobat writes them."""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402
from PySide6.QtWidgets import QApplication, QInputDialog  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas.document_view import DocumentView  # noqa: E402


def blank():
    d = pymupdf.open()
    d.new_page()
    p = os.path.join(tempfile.mkdtemp(), "b.pdf")
    d.save(p)
    return p


def acrobat_group(path):
    d = pymupdf.open()
    p = d.new_page()
    par = d.get_new_xref()
    kids = []
    for k in range(3):
        x = d.get_new_xref()
        on = d.get_new_xref()
        d.update_object(on, "<< /Type /XObject /Subtype /Form /BBox [0 0 14 14] >>")
        d.update_stream(on, b"0 g 2 2 10 10 re f")
        off = d.get_new_xref()
        d.update_object(off, "<< /Type /XObject /Subtype /Form /BBox [0 0 14 14] >>")
        d.update_stream(off, b"0 G 0.5 0.5 13 13 re S")
        y = 100 + 30 * k
        d.update_object(x, f"<< /Type /Annot /Subtype /Widget /Rect [50 {y} 64 {y + 14}] /F 4 "
                           f"/Parent {par} 0 R /AS /Off /AP << /N << /Choice{k + 1} {on} 0 R "
                           f"/Off {off} 0 R >> >> >>")
        kids.append(x)
    d.update_object(par, "<< /FT /Btn /Ff 32768 /T (Group1) /V /Off /Kids ["
                         + " ".join(f"{x} 0 R" for x in kids) + "] >>")
    d.xref_set_key(p.xref, "Annots", "[" + " ".join(f"{x} 0 R" for x in kids) + "]")
    d.xref_set_key(d.pdf_catalog(), "AcroForm", f"<< /Fields [{par} 0 R] >>")
    d.save(path)


class RadioGroups(unittest.TestCase):
    def view(self, path):
        v = DocumentView(path)
        v.resize(600, 600)
        v.show()
        APP.processEvents()
        self.addCleanup(v.close_doc)
        return v

    def states(self, v):
        pg = v.doc[0]
        xs = [x for _i, x in v.field_order()]
        return [pg.load_widget(x).field_value != "Off" for x in xs], xs

    def test_option_tool_makes_an_exclusive_group(self):
        v = self.view(blank())
        with mock.patch.object(QInputDialog, "getItem", lambda *a, **k: ("Group1", True)):
            for k in range(3):
                v.create_field(0, "f_radio", pymupdf.Point(57, 107 + 30 * k),
                               pymupdf.Point(57, 107 + 30 * k), True)
        on, xs = self.states(v)
        self.assertEqual(on, [False, False, False])
        pg = v.doc[0]                       # keep the page alive while its widgets are used
        names = {pg.load_widget(x).on_state() for x in xs}
        self.assertEqual(len(names), 3, "each button has its own 'on' state name")
        v.fill_field(0, xs[0])
        v.fill_field(0, xs[2])
        self.assertEqual(self.states(v)[0], [False, False, True])
        v.fill_field(0, xs[1])
        self.assertEqual(self.states(v)[0], [False, True, False])
        # saved and reopened, still exclusive and still one group
        out = os.path.join(tempfile.mkdtemp(), "o.pdf")
        v.save(out)
        d = pymupdf.open(out)
        ws = list(d[0].widgets())
        self.assertEqual({w.field_name for w in ws}, {"Group1"})
        self.assertEqual([w.field_value != "Off" for w in ws].count(True), 1)

    def test_acrobat_style_group_is_exclusive(self):
        path = os.path.join(tempfile.mkdtemp(), "a.pdf")
        acrobat_group(path)
        v = self.view(path)
        on, xs = self.states(v)
        v.fill_field(0, xs[0])
        v.fill_field(0, xs[2])
        self.assertEqual(self.states(v)[0], [False, False, True])
        v.fill_field(0, xs[0])
        self.assertEqual(self.states(v)[0], [True, False, False])


if __name__ == "__main__":
    unittest.main()
