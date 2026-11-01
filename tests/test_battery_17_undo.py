"""Break-it tests for undo and redo through MuPDF's journal (1.7): sequences through the
app's own steps that went wrong once, each checked against what a copy per edit (up to
1.6) gives.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_battery_17_undo
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402

from tests.test_undo_journal import Quiet, canon, rect_markup, sample  # noqa: E402


def annots(doc):
    return [len(list(p.annots())) for p in doc]


def damaged(path, src):
    """A PDF whose table of objects points the contents of page 4 at another object: MuPDF
    repairs the file only when it first reads that object."""
    sample(src)
    with pymupdf.open(src) as d:
        data = d.tobytes(garbage=3, use_objstms=0, expand=255)
    with pymupdf.open("pdf", data) as d:
        target = d[3].get_contents()[0]
    i = data.rindex(b"\nxref\n")
    lines = data[i + 1:].split(b"\n")
    lines[2 + target] = lines[2 + 1]            # ("xref", "0 n", then one line per object)
    with open(path, "wb") as f:
        f.write(data[:i + 1] + b"\n".join(lines))
    return path


class Battery(Quiet):
    def test_a_file_repaired_after_an_edit_keeps_the_edit(self):
        # MuPDF rebuilds the table of objects of a damaged file when it first reads the
        # broken object, and every change made before is lost: a markup added, then the
        # damaged page looked at (or the file saved) dropped the markup, also from the file
        src = damaged(self.path("damaged.pdf"), self.path("sample.pdf"))
        for journal in (True, False):
            with self.subTest(journal=journal):
                v = self.view(journal, name="d%d.pdf" % journal)
                with open(src, "rb") as f, open(v.path, "wb") as g:
                    g.write(f.read())
                v.close_doc()
                from kanzonas.document_view import DocumentView
                v = DocumentView(v.path)
                self.addCleanup(lambda v=v: v.doc.is_closed or v.close_doc())
                self.assertFalse(v.doc.is_repaired)
                rect_markup(v, 0)
                v.doc[3].get_pixmap(dpi=20)            # (reads the broken object)
                self.assertEqual(annots(v.doc), [2, 1, 1, 1])
                rect_markup(v, 1)
                v.save()
                with pymupdf.open(v.path) as saved:
                    self.assertEqual(annots(saved), [2, 2, 1, 1])
                v.undo()
                v.undo()
                self.assertEqual(annots(v.doc), [1, 1, 1, 1])
                v.redo()
                self.assertEqual(annots(v.doc), [2, 1, 1, 1])
                v.dirty = False


if __name__ == "__main__":
    unittest.main()
