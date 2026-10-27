"""Pages copied with Duplicate pages or Copy pages / Paste pages keep their links: a link to
another copied page goes to its copy, a link to a page not copied still works on a duplicate
(or a paste into the same document) and is left out in another document. KanzonasPDF's own
link keys (/KZGroup, /KZLook...) and the link's look come along. Deleting a page that a
bookmark points to moves the bookmark to the page after it; Undo brings it back.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_page_copy_links
"""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf as F  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import links  # noqa: E402
from kanzonas.document_view import DocumentView  # noqa: E402


def goto_pages(page):
    return [ln.get("page") for ln in page.get_links() if ln["kind"] == F.LINK_GOTO]


class CopyPageLinks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(mock.patch.stopall)
        mock.patch.object(QMessageBox, "information", return_value=None).start()
        mock.patch.object(QMessageBox, "warning", return_value=None).start()
        self.views = []
        self.addCleanup(lambda: [v.close_doc() for v in self.views])

    def view(self, n=3, name="A"):
        path = os.path.join(self.tmp, name + ".pdf")
        d = F.open()
        for i in range(n):
            d.new_page().insert_text((72, 72), f"{name}{i + 1}", fontsize=24)
        d.save(path)
        d.close()
        v = DocumentView(path)
        self.views.append(v)
        return v

    def labels(self, v):
        return [p.get_text().split()[0] for p in v.doc]

    def test_duplicate_keeps_the_link_to_a_page_not_copied(self):
        v = self.view()
        v.modify(lambda: v.doc[0].insert_link({"kind": F.LINK_GOTO, "page": 2,
                                               "from": F.Rect(72, 50, 150, 80)}))
        v.duplicate_pages([0])
        self.assertEqual(self.labels(v), ["A1", "A1", "A2", "A3"])
        self.assertEqual(goto_pages(v.doc[0]), [3])
        self.assertEqual(goto_pages(v.doc[1]), [3])

    def test_links_between_copied_pages_go_to_the_copies(self):
        v = self.view()
        v.modify(lambda: v.doc[0].insert_link({"kind": F.LINK_GOTO, "page": 1,
                                               "from": F.Rect(72, 50, 150, 80)}))
        v.modify(lambda: v.doc[1].insert_link({"kind": F.LINK_URI, "uri": "https://e.com",
                                               "from": F.Rect(72, 90, 150, 120)}))
        v.duplicate_pages([0, 1])
        self.assertEqual(self.labels(v), ["A1", "A2", "A1", "A2", "A3"])
        self.assertEqual(goto_pages(v.doc[0]), [1])
        self.assertEqual(goto_pages(v.doc[2]), [3])            # the copy of page 2
        self.assertEqual([ln.get("uri") for ln in v.doc[3].get_links()], ["https://e.com"])

    def test_kanzonas_link_keys_and_look_come_along(self):
        v = self.view()
        v.modify(lambda: links.add(v.doc[0], [F.Rect(72, 50, 150, 80)], ("page", 2),
                                   look="box"))
        v.duplicate_pages([0])
        old, new = links.read(v.doc[0])[0], links.read(v.doc[1])[0]
        self.assertEqual((new["group"], new["look"]), (old["group"], old["look"]))
        self.assertEqual(new["rect"], old["rect"])
        self.assertEqual(v.doc.xref_get_key(new["xref"], "C"),
                         v.doc.xref_get_key(old["xref"], "C"))

    def test_paste_into_another_document(self):
        a, b = self.view(), self.view(2, "B")
        a.modify(lambda: a.doc[0].insert_link({"kind": F.LINK_GOTO, "page": 2,
                                               "from": F.Rect(72, 50, 150, 80)}))
        a.modify(lambda: a.doc[1].insert_link({"kind": F.LINK_GOTO, "page": 0,
                                               "from": F.Rect(72, 50, 150, 80)}))
        data = a.pages_bytes([0, 1])
        b.paste_pages(data, 2)
        self.assertEqual(self.labels(b), ["B1", "B2", "A1", "A2"])
        self.assertEqual(goto_pages(b.doc[2]), [])            # its target stayed behind
        self.assertEqual(goto_pages(b.doc[3]), [2])           # to the pasted A1
        # pasted back into the document they came from, both links work
        a.paste_pages(data, 3)
        self.assertEqual(goto_pages(a.doc[3]), [2])
        self.assertEqual(goto_pages(a.doc[4]), [3])

    def test_bookmark_to_a_deleted_page_moves_to_the_next_one(self):
        v = self.view(4)
        v.modify(lambda: v.doc.set_toc([[1, "one", 1], [1, "three", 3], [2, "sub", 3],
                                        [1, "four", 4]]))
        before = v.doc.get_toc()
        self.assertTrue(v.delete_pages([2]))
        self.assertEqual(v.doc.get_toc(), [[1, "one", 1], [1, "three", 3], [2, "sub", 3],
                                           [1, "four", 3]])
        v.undo()
        self.assertEqual(v.doc.get_toc(), before)
        self.assertTrue(v.delete_pages([3]))                  # the last page: to the new last
        self.assertEqual(v.doc.get_toc()[-1], [1, "four", 3])


if __name__ == "__main__":
    unittest.main()
