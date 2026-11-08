"""Apply redactions with clean-up and Sanitize on a PDF with a reply to a reply (a review thread
from Acrobat). PyMuPDF's scrub(reset_responses=True) deletes each markup's responses while
walking a list of the page's markups made beforehand, and failed on the first one it had
already deleted ("xref ... is not an annot of this page"). pdf_speed.scrub removes the threads
itself first, in one walk of each page.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_scrub_reply_threads
"""
import unittest

import pymupdf

from kanzonas import pdf_speed


def _thread_doc():
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 100), "Some secret text here")
    parent = page.add_text_annot((100, 120), "Please check this")
    reply = page.add_text_annot((100, 120), "Checked")
    reply2 = page.add_text_annot((100, 120), "Thanks")
    px, rx, r2x = parent.xref, reply.xref, reply2.xref
    del parent, reply, reply2
    doc.xref_set_key(rx, "IRT", "%d 0 R" % px)
    doc.xref_set_key(rx, "RT", "/R")
    doc.xref_set_key(r2x, "IRT", "%d 0 R" % rx)          # a reply to the reply
    doc.xref_set_key(r2x, "RT", "/R")
    return pymupdf.open("pdf", doc.tobytes()), px


class ScrubReplyThreads(unittest.TestCase):
    def test_scrub_with_a_reply_to_a_reply(self):
        doc, px = _thread_doc()
        self.assertEqual(len(list(doc[0].annots())), 3)
        pdf_speed.scrub(doc)                         # (raised before)
        left = [a.xref for a in doc[0].annots()]
        self.assertNotIn(px + 1, left)               # the replies are gone ...
        self.assertTrue(left)                        # ... the markup itself stays
        doc.tobytes()                                # and the file still writes

    def test_without_threads_unchanged(self):
        doc = pymupdf.open()
        doc.new_page().add_text_annot((50, 50), "alone")
        pdf_speed.scrub(doc)
        self.assertEqual(len(list(doc[0].annots())), 1)


if __name__ == "__main__":
    unittest.main()
