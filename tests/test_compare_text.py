"""Compare documents, text mode: reflowed text reports only the real edits (not everything
that moved), repeated changes are summarized once, pictures that came, went or changed size
are reported, the mode is picked from the content, and the command runs end to end.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_compare_text
"""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf as F  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog, QFileDialog, QMessageBox  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import compare  # noqa: E402
from kanzonas.compare_ui import CompareModeDialog  # noqa: E402
from kanzonas.main_window import MainWindow  # noqa: E402

PARA = ("The contractor shall furnish all labor, materials, equipment and services required "
        "to complete the work shown on the drawings. All work shall conform to the applicable "
        "codes and standards. Submittals shall be provided for review before fabrication. ")


def picture(w=120, h=80, shade=200):
    pm = F.Pixmap(F.csRGB, F.IRect(0, 0, w, h), False)
    pm.set_rect(pm.irect, (shade, 220, 240))
    pm.set_rect(F.IRect(10, 10, w - 10, h - 10), (180, 60, 60))
    return pm


def spec(revised, header=None, pic_size=(300, 180)):
    """Numbered paragraphs over several pages; the revised version has one more paragraph,
    two reworded sentences and no picture."""
    doc = F.open()
    paras = []
    for i in range(14):
        text = f"{i + 1}. " + PARA * 2
        if revised and i == 3:
            text = text.replace("before fabrication", "at least ten working days before fabrication")
        if revised and i == 8:
            text = text.replace("applicable codes", "applicable codes, ordinances")
        paras.append(text)
    if revised:
        paras.insert(5, "5A. The owner reserves the right to reject any material that does not "
                        "meet the specified requirements, at no additional cost. " * 2)
    page = doc.new_page()
    y = 72
    if header:
        page.insert_text((72, 40), header, fontsize=9)
    scratch = F.open().new_page()
    for k, text in enumerate(paras):
        rect = F.Rect(72, y, 540, y + 400)
        used = 400 - scratch.insert_textbox(F.Rect(72, 72, 540, 472), text, fontsize=10, fontname="helv")
        if y + used > 720:
            page = doc.new_page()
            y = 72
            if header:
                page.insert_text((72, 40), header, fontsize=9)
            rect = F.Rect(72, y, 540, y + 400)
        page.insert_textbox(rect, text, fontsize=10, fontname="helv")
        y += used + 10
        if k == 2 and not revised:
            page.insert_image(F.Rect(150, y, 150 + pic_size[0], y + pic_size[1]), pixmap=picture())
            y += pic_size[1] + 10
    return doc.tobytes()


def changes_of(data):
    """[(page, type, comment)] of the markups in a result."""
    out = []
    for p in F.open(stream=data):
        for a in p.annots():
            out.append((p.number + 1, a.type[1], a.info["content"]))
    return out


class ReflowedText(unittest.TestCase):
    def test_only_the_real_edits_are_reported(self):
        old, new = spec(False), spec(True)
        _pix, pixel_counts = compare.compare(old, new)
        self.assertGreater(sum(pixel_counts), 5)               # the overlay clouds the reflow
        data, counts = compare.compare_text(old, new, old_name="OLD", new_name="NEW")
        marks = changes_of(data)
        texts = sorted(c.split(": ", 1)[1] for _p, _t, c in marks)
        self.assertTrue(texts[0].startswith("Added: 5A. The owner reserves the right to reject any "
                                            "material that does not meet the specified requirements"))
        self.assertTrue(texts[0].endswith("..."), "a long run is cut short in the comment")
        self.assertEqual(texts[1:], ["Added: at least ten working days",
                                 "Added: at least ten working days",
                                 "Picture removed",
                                 "Was: codes  |  Now: codes, ordinances",
                                 "Was: codes  |  Now: codes, ordinances"])
        self.assertEqual(sum(counts), 6)
        self.assertEqual(len(counts), F.open(stream=new).page_count)
        res = F.open(stream=data)
        self.assertEqual(res.page_count, len(counts) + 1, "a summary page at the end")
        summary = res[-1].get_text()
        self.assertIn("NEW against OLD: 6 change(s)", summary)
        self.assertIn("Picture removed", summary)
        self.assertIn("Was: codes  |  Now: codes, ordinances", summary)
        self.assertIn("blue = added in NEW", res[0].get_text())
        # the added words are highlighted where they are in NEW; the picture box is where
        # the picture was in OLD (page 1, below paragraph 3)
        kinds = {t for _p, t, _c in marks}
        self.assertEqual(kinds, {"Highlight", "Square"})
        box = next(a.rect for a in res[0].annots() if a.type[1] == "Square")
        self.assertTrue(box.y0 > 200 and box.width > 250, box)

    def test_identical_documents_show_no_change(self):
        old = spec(False)
        data, counts = compare.compare_text(old, old)
        self.assertEqual(sum(counts), 0)
        self.assertEqual(changes_of(data), [])
        self.assertIn("0 change(s)", F.open(stream=data)[-1].get_text())

    def test_a_header_changed_on_every_page_is_summarized_once(self):
        def doc(header, n=7):
            d = F.open()
            for i in range(n):
                p = d.new_page()
                p.insert_text((72, 40), header, fontsize=9)
                p.insert_textbox(F.Rect(72, 72, 540, 700), f"{i + 1}. " + PARA * 3, fontsize=10)
            return d.tobytes()
        data, counts = compare.compare_text(doc("Expires July 13, 2031"), doc("Expires draft"))
        self.assertEqual(counts, [1] * 7)
        summary = F.open(stream=data)[-1].get_text()
        self.assertIn("Change 1 and 6 more like it, pages 1-7: Was: July 13, 2031  |  Now: draft",
                      summary)
        data, _counts = compare.compare_text(doc("Expires July 13, 2031", 3), doc("Expires draft", 3))
        self.assertIn("Changes 1, 2, 3, pages 1-3: Was: July 13, 2031  |  Now: draft",
                      F.open(stream=data)[-1].get_text())

    def test_removed_words_are_marked_where_they_were(self):
        a, b = F.open(), F.open()
        a.new_page().insert_text((72, 100), "Payment is due within thirty days of the invoice.")
        b.new_page().insert_text((72, 100), "Payment is due within days of the invoice.")
        data, counts = compare.compare_text(a.tobytes(), b.tobytes())
        self.assertEqual(counts, [1])
        (page, kind, text), = changes_of(data)
        self.assertEqual((page, kind, text), (1, "Square", "Change 1: Removed: thirty"))
        mark = next(an.rect for an in F.open(stream=data)[0].annots())
        within = next(F.Rect(w[:4]) for w in b[0].get_text("words") if w[4] == "within")
        self.assertAlmostEqual(mark.x0, within.x1, delta=1)      # right after "within"

    def test_pictures_added_removed_and_resized(self):
        a, b = F.open(), F.open()
        pa, pb = a.new_page(), b.new_page()
        for p in (pa, pb):
            p.insert_text((72, 72), "Figure 1 and Figure 2")
        pa.insert_image(F.Rect(72, 100, 372, 300), pixmap=picture())           # resized in b
        pb.insert_image(F.Rect(72, 100, 222, 200), pixmap=picture())
        pa.insert_image(F.Rect(72, 400, 192, 480), pixmap=picture(60, 40, 90))  # gone in b
        pb.insert_image(F.Rect(300, 400, 420, 480), pixmap=picture(80, 80, 10))  # new in b
        data, counts = compare.compare_text(a.tobytes(), b.tobytes())
        texts = sorted(c for _p, _t, c in changes_of(data))
        self.assertEqual(texts, ["Change 1: Picture resized: 4.2 x 2.8 in, now 2.1 x 1.4 in",
                                 "Change 2: Picture added", "Change 3: Picture removed"])
        self.assertEqual(counts, [3])

    def test_the_same_picture_saved_again_is_not_a_change(self):
        a, b = F.open(), F.open()
        pa, pb = a.new_page(), b.new_page()
        pa.insert_image(F.Rect(72, 100, 372, 300), pixmap=picture())
        pb.insert_image(F.Rect(72, 100, 372, 300), stream=picture().tobytes("png"))
        self.assertEqual(compare.compare_text(a.tobytes(), b.tobytes())[1], [0])

    def test_has_text(self):
        self.assertTrue(compare.has_text(F.open(stream=spec(False))))
        d = F.open()
        for _ in range(3):
            p = d.new_page()
            p.draw_rect(F.Rect(100, 100, 300, 300), color=(0, 0, 0))
            p.insert_text((100, 90), "A-101", fontsize=8)
        self.assertFalse(compare.has_text(d))
        self.assertFalse(compare.has_text(F.open()))


class OverlayTolerance(unittest.TestCase):
    def test_two_exports_of_the_same_text_show_no_change(self):
        """Word places the same text a fraction of a point apart from one export to the
        next; the overlay must not cloud every word for that."""
        a, b = F.open(), F.open()
        for d, dx in ((a, 0), (b, 0.3)):
            p = d.new_page()
            for i in range(30):
                p.insert_text((72 + dx, 80 + 20 * i), f"{i + 1}. " + PARA[:90], fontsize=10)
        _data, counts = compare.compare(a.tobytes(), b.tobytes())
        self.assertEqual(counts, [0])
        c = F.open()
        p = c.new_page()
        for i in range(30):
            p.insert_text((72, 80 + 20 * i), f"{i + 1}. " + PARA[:90], fontsize=10)
        p.insert_text((72, 700), "A real change", fontsize=10)
        self.assertEqual(compare.compare(a.tobytes(), c.tobytes())[1], [1])


class Command(unittest.TestCase):
    def test_compare_documents_offers_text_mode_and_opens_the_result(self):
        folder = tempfile.mkdtemp()
        old_path, new_path = os.path.join(folder, "spec rev A.pdf"), os.path.join(folder, "spec rev B.pdf")
        open(old_path, "wb").write(spec(False))
        open(new_path, "wb").write(spec(True))
        w = MainWindow()
        w.show()
        w.open_file(new_path)
        APP.processEvents()
        self.addCleanup(lambda: (setattr(w, "_close_confirmed", True), w.close()))
        seen = {}

        def run(self_):
            seen["text_default"] = self_.r_text.isChecked()
            return QDialog.Accepted
        shown = []
        with mock.patch.object(QFileDialog, "getOpenFileName", lambda *a, **k: (old_path, "")), \
                mock.patch.object(CompareModeDialog, "exec", run), \
                mock.patch.object(QMessageBox, "information", lambda *a, **k: shown.append(a[2])):
            w.compare_documents()
        self.assertTrue(seen["text_default"])
        self.assertEqual(len(shown), 1)
        self.assertIn("Found 6 change(s) on 2 of 2 page(s)", shown[0])
        self.assertIn("summary page", shown[0])
        self.assertEqual(w.tabs.count(), 2)
        v = w.view()
        self.assertTrue(os.path.basename(v.path).startswith("Compare - spec rev A vs spec rev B"))
        self.assertEqual(v.doc.page_count, 3, "the two pages and the summary")
        self.assertTrue(w.markups_dock.isVisible())


if __name__ == "__main__":
    unittest.main()
