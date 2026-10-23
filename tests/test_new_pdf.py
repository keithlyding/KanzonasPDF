"""File > New PDF (page size asked, or remembered), unsaved Untitled documents, Insert pages
from file with pictures and with nothing open; Ctrl+click and right-click in the page list
keep the selection.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_new_pdf
"""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QColor, QImage  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QFileDialog, QInputDialog, QMessageBox  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import autosave, new_pdf  # noqa: E402
from kanzonas.document_view import DocumentView  # noqa: E402
from kanzonas.main_window import MainWindow  # noqa: E402


def answer(name, landscape=False, dont_ask=False, seen=None):
    """A stand-in for the page-size question: picks the given answer (or cancels with
    name=None) and records that it was asked."""
    def exec_(dlg):
        if seen is not None:
            seen.append(dlg.choice())
        if name is None:
            return 0
        dlg.size.setCurrentIndex(dlg.size.findData(name))
        dlg.orient.setCurrentIndex(1 if landscape else 0)
        dlg.dont_ask.setChecked(dont_ask)
        return 1
    return mock.patch.object(new_pdf.PageSizeDialog, "exec", exec_)


def picture(path, w, h):
    img = QImage(w, h, QImage.Format_RGB32)
    img.fill(QColor(200, 30, 30))
    img.save(path)
    return path


def sized(doc):
    return [(round(p.rect.width), round(p.rect.height)) for p in doc]


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.w = MainWindow()
        self.w.show()
        self.addCleanup(lambda: (setattr(self.w, "_close_confirmed", True), self.w.close()))
        s = self.w.settings
        s.setValue("last_dir", self.dir)
        s.setValue("new_pdf_ask", "true")
        s.setValue("new_pdf_size", "Letter")
        s.setValue("new_pdf_landscape", "false")


class NewPdf(Base):
    def test_asks_the_size_and_opens_an_unsaved_untitled_tab(self):
        seen = []
        with answer("Tabloid", landscape=True, seen=seen):
            self.w.a_new.trigger()
        self.assertEqual(seen, [("Letter", False)])           # suggests the last choice
        v = self.w.view()
        self.assertTrue(v.untitled)
        self.assertFalse(v.dirty)                              # closes without asking
        self.assertEqual(sized(v.doc), [(1224, 792)])          # 17 x 11 in
        self.assertEqual(self.w.tabs.tabText(self.w.tabs.currentIndex()), "Untitled 1.pdf")
        self.assertEqual(self.w.tabs.tabToolTip(self.w.tabs.currentIndex()), "Not saved yet")
        self.assertFalse(os.path.exists(v.path))               # nothing written anywhere
        # remembered for next time, and still asked
        with answer("Letter", seen=seen):
            self.w.a_new.trigger()
        self.assertEqual(seen[-1], ("Tabloid", True))
        self.assertEqual(self.w.tabs.tabText(self.w.tabs.currentIndex()), "Untitled 2.pdf")

    def test_cancel_makes_nothing(self):
        with answer(None):
            self.w.a_new.trigger()
        self.assertIsNone(self.w.view())

    def test_dont_ask_again_and_preferences(self):
        with answer("A4", dont_ask=True):
            self.w.a_new.trigger()
        seen = []
        with answer("Letter", seen=seen):
            self.w.a_new.trigger()                             # not asked: A4 straight away
        self.assertEqual(seen, [])
        self.assertEqual(sized(self.w.view().doc), [(595, 842)])
        # Preferences shows the size, and "Ask every time" turns the question back on
        from kanzonas.preferences import PreferencesDialog
        dlg = PreferencesDialog(self.w)
        self.assertEqual(dlg.new_size.currentData(), "A4")
        dlg.new_size.setCurrentIndex(dlg.new_size.findData(new_pdf.ASK))
        dlg._apply()
        with answer("Letter", seen=seen):
            self.w.a_new.trigger()
        self.assertEqual(seen, [("A4", False)])
        # choosing a size there stops the question again
        dlg = PreferencesDialog(self.w)
        self.assertEqual(dlg.new_size.currentData(), new_pdf.ASK)
        dlg.new_size.setCurrentIndex(dlg.new_size.findData("ARCH D"))
        dlg.new_orient.setCurrentIndex(1)
        dlg._apply()
        with answer("Letter", seen=seen):
            self.w.a_new.trigger()
        self.assertEqual(len(seen), 1)
        self.assertEqual(sized(self.w.view().doc), [(2592, 1728)])   # 36 x 24 in

    def test_save_asks_where_then_it_is_a_normal_file(self):
        with answer("Letter"):
            self.w.a_new.trigger()
        v = self.w.view()
        self.w.a_insert_blank.setEnabled(True)
        with mock.patch.object(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes):
            self.w.a_insert_blank.trigger()                    # (unlocks the page order)
        self.assertTrue(v.dirty)
        self.assertEqual(v.page_count(), 2)
        with mock.patch.object(QFileDialog, "getSaveFileName", lambda *a, **k: ("", "")):
            self.assertFalse(self.w.save())                    # canceled: still unsaved
        self.assertTrue(v.untitled)
        with self.assertRaises(RuntimeError):
            v.save()                                           # never silently to the name
        out = os.path.join(self.dir, "plan.pdf")
        asked = []
        with mock.patch.object(QFileDialog, "getSaveFileName",
                               lambda *a, **k: (asked.append(a[2]), (out, ""))[1]):
            self.w.a_save.trigger()
        self.assertFalse(v.dirty)
        self.assertTrue(asked[0].endswith("Untitled 1.pdf"))
        self.assertFalse(v.untitled)
        self.assertEqual(v.path, out)
        self.assertEqual(pymupdf.open(out).page_count, 2)
        self.assertEqual(self.w.tabs.tabText(self.w.tabs.currentIndex()), "plan.pdf")
        # from now on Save writes the file without asking
        with mock.patch.object(QFileDialog, "getSaveFileName",
                               side_effect=AssertionError("asked again")):
            self.assertTrue(self.w.save())

    def test_closing_asks_only_after_changes(self):
        with answer("Letter"):
            self.w.a_new.trigger()
        asked = []
        with mock.patch.object(QMessageBox, "question",
                               lambda *a, **k: (asked.append(a[2]), QMessageBox.Discard)[1]):
            self.assertTrue(self.w._confirm_close(self.w.view()))
            self.assertEqual(asked, [])
            self.w.view().dirty = True
            self.assertTrue(self.w._confirm_close(self.w.view()))
        self.assertEqual(asked, ["Save changes to Untitled 1.pdf?"])

    def test_untitled_stays_out_of_session_recent_and_file_matching(self):
        with answer("Letter"):
            self.w.a_new.trigger()
        v = self.w.view()
        # a real file with the suggested name opens in its own tab
        d = pymupdf.open()
        d.new_page()
        d.save(v.path)
        self.w.open_file(v.path)
        self.assertIsNot(self.w.view(), v)
        self.assertEqual(self.w.tabs.count(), 2)
        self.w.tabs.setCurrentWidget(v)
        self.w._remember_state(v)
        self.assertNotIn(os.path.normcase(v.path), self.w._file_states())
        # an automatic backup of it isn't tied to that file
        from kanzonas import paths
        paths.settings().setValue("backup_dir", tempfile.mkdtemp())
        self.addCleanup(paths.settings().setValue, "backup_dir", "")
        v.dirty = True
        self.w.autosave.backup(v)
        self.addCleanup(self.w.autosave.discard, v)
        idx = autosave._index()
        self.assertEqual(idx[os.path.basename(v._backup_path)], "")


class InsertFiles(Base):
    def test_pictures_become_pages_the_size_of_the_page_before(self):
        src = os.path.join(self.dir, "plan.pdf")
        d = pymupdf.open()
        d.new_page(width=792, height=612)                      # Letter landscape
        d.new_page(width=1224, height=792)                     # Tabloid landscape
        d.save(src)
        self.w.open_file(src)
        self.w.lock_btn.setChecked(False)
        v = self.w.view()
        v.goto_page(0)
        tall = picture(os.path.join(self.dir, "tall.png"), 300, 600)
        wide = picture(os.path.join(self.dir, "wide.jpg"), 800, 400)
        other = os.path.join(self.dir, "other.pdf")
        o = pymupdf.open()
        o.new_page(width=200, height=300)
        o.save(other)
        with mock.patch.object(QFileDialog, "getOpenFileNames",
                               lambda *a, **k: ([tall, other, wide], "")), \
                mock.patch.object(QInputDialog, "getItem",
                                  lambda *a, **k: ("After current page", True)):
            self.w.a_insert_pdf.trigger()
        # after page 1 (792 x 612): tall picture turned upright, the PDF as it is, wide one
        self.assertEqual(sized(v.doc), [(792, 612), (612, 792), (200, 300), (792, 612),
                                        (1224, 792)])
        pg = v.doc[1]
        self.assertTrue(pg.get_images())                       # the picture is on it
        v.undo()                                               # one step
        self.assertEqual(v.page_count(), 2)

    def test_with_nothing_open_insert_makes_a_new_pdf(self):
        pic = picture(os.path.join(self.dir, "photo.png"), 400, 300)
        self.assertTrue(self.w.a_insert_pdf.isEnabled())
        self.assertTrue(self.w.a_insert_blank.isEnabled())
        seen = []
        with mock.patch.object(QFileDialog, "getOpenFileNames", lambda *a, **k: ([pic], "")), \
                answer("Legal", seen=seen):
            self.w.a_insert_pdf.trigger()
        v = self.w.view()
        self.assertEqual(len(seen), 1)                         # pictures: the size is asked
        self.assertTrue(v.untitled and v.dirty)
        self.assertEqual(sized(v.doc), [(1008, 612)])          # Legal, turned for a wide photo
        # PDFs alone keep their own size and need no question
        self.w._close_confirmed = True
        pdf = os.path.join(self.dir, "a.pdf")
        d = pymupdf.open()
        d.new_page(width=300, height=300)
        d.save(pdf)
        w2 = MainWindow()
        self.addCleanup(lambda: (setattr(w2, "_close_confirmed", True), w2.close()))
        with mock.patch.object(QFileDialog, "getOpenFileNames", lambda *a, **k: ([pdf], "")), \
                answer("Legal", seen=seen):
            w2.a_insert_pdf.trigger()
        self.assertEqual(len(seen), 1)
        self.assertEqual(sized(w2.view().doc), [(300, 300)])

    def test_blank_page_with_nothing_open_is_a_new_pdf(self):
        with answer("ARCH B"):
            self.w.a_insert_blank.trigger()
        v = self.w.view()
        self.assertTrue(v.untitled)
        self.assertEqual(sized(v.doc), [(864, 1296)])


class PageListSelection(unittest.TestCase):
    def setUp(self):
        path = os.path.join(tempfile.mkdtemp(), "six.pdf")
        d = pymupdf.open()
        for i in range(6):
            d.new_page().insert_text((72, 72), f"Page {i + 1}", fontsize=20)
        d.save(path)
        self.w = MainWindow()
        self.w.show()
        self.addCleanup(lambda: (setattr(self.w, "_close_confirmed", True), self.w.close()))
        self.w.open_file(path)
        APP.processEvents()
        self.t = self.w.thumbs

    def click(self, row, mods=Qt.NoModifier, button=Qt.LeftButton, press_only=False):
        it = self.t.item(row)
        self.t.scrollToItem(it)
        APP.processEvents()
        pos = self.t.visualItemRect(it).center()
        if press_only:
            QTest.mousePress(self.t.viewport(), button, mods, pos)
        else:
            QTest.mouseClick(self.t.viewport(), button, mods, pos)
        APP.processEvents()

    def selected(self):
        return sorted(self.t.row(i) for i in self.t.selectedItems())

    def test_ctrl_click_adds_and_removes_pages(self):
        self.click(0)
        self.click(2, Qt.ControlModifier)
        self.click(5, Qt.ControlModifier)
        self.assertEqual(self.selected(), [0, 2, 5])
        self.assertEqual(self.w.view().current_page(), 5)    # still goes to the page
        self.click(2, Qt.ControlModifier)
        self.assertEqual(self.selected(), [0, 5])

    def test_right_click_keeps_a_shift_selection_for_the_menu(self):
        self.click(1)
        self.click(4, Qt.ShiftModifier)
        self.click(2, button=Qt.RightButton, press_only=True)
        self.assertEqual(self.selected(), [1, 2, 3, 4])
        self.assertEqual(self.w._selected_pages(), [1, 2, 3, 4])

    def test_scrolling_still_selects_the_page_shown(self):
        self.click(0)
        self.click(2, Qt.ControlModifier)
        self.w.view().goto_page(4)
        APP.processEvents()
        self.assertEqual(self.selected(), [4])     # Delete then acts on the page you see


class DocumentViewUntitled(unittest.TestCase):
    def test_a_view_of_a_new_document(self):
        d = new_pdf.blank_doc(new_pdf.page_size("ANSI D", landscape=True))
        v = DocumentView(os.path.join(tempfile.mkdtemp(), "Untitled 1.pdf"), doc=d)
        self.addCleanup(v.close_doc)
        self.assertTrue(v.untitled)
        self.assertEqual(sized(v.doc), [(2448, 1584)])
        with self.assertRaises(RuntimeError):
            v.timestamp("http://example.invalid", os.path.join(tempfile.mkdtemp(), "t.pdf"))
        out = os.path.join(tempfile.mkdtemp(), "saved.pdf")
        v.save(out)
        self.assertFalse(v.untitled)
        self.assertEqual(pymupdf.open(out).page_count, 1)


if __name__ == "__main__":
    unittest.main()
