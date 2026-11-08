"""View > Page layout with the editing tools: pages shown two side by side (one spread at a
time, the spreads one under the other, the cover page on its own) work as one under the other
do. Edit objects' copy, cut and paste onto another page, CAD mode's Move and Copy to another
page and a selection dragged onto the page beside it (tests/test_object_clipboard.py, run
again in each layout); Add text and Edit text typed enlarged on a zoomed-out sheet, with its
true-size preview, on the right-hand page (tests/test_small_text_editing.py); pages scanned
into the document; printing with Dark thin lines; and Full screen and Presentation, which
change the document only through DocumentView.modify (one undo step), or not at all.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_reading_layouts
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402
from PySide6.QtCore import QPoint, QRectF, Qt  # noqa: E402
from PySide6.QtGui import QImage, QPainter  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

from tests.qt_fonts import ensure_font  # noqa: E402

ensure_font()      # (Windows' offscreen Qt has no font: texts measure 0 px)

from kanzonas import annotations, reading  # noqa: E402
from kanzonas.main_window import MainWindow  # noqa: E402
from tests import test_object_clipboard as clipboard_tests  # noqa: E402
from tests import test_small_text_editing as small_text_tests  # noqa: E402
from tests.test_undo_journal import canon  # noqa: E402


def pump(n=8):
    for _ in range(n):
        APP.processEvents()


def side_by_side(test, v, a, b):
    """Pages a and b are shown, on one row, a on the left."""
    pa, pb = v.pages[a], v.pages[b]
    test.assertTrue(pa.isVisible() and pb.isVisible())
    test.assertEqual(pa.y(), pb.y())
    test.assertLess(pa.x() + pa.width(), pb.x())


# ---- Edit objects copy and paste, CAD across pages, drags onto the page beside -------------
class _InLayout:
    LAYOUT, COVER = "two", False

    def setUp(self):
        super().setUp()
        self.w.a_cover.setChecked(self.COVER)
        reading.set_layout(self.w, None)
        reading.set_layout(self.w, self.LAYOUT)
        pump()
        self.assertEqual((self.v.page_layout, self.v.cover_page), (self.LAYOUT, self.COVER))
        a, b = (1, 2) if self.COVER else (0, 1)
        side_by_side(self, self.v, a, b)


class TwoPagesCopyAndPaste(_InLayout, clipboard_tests.CopyAndPaste):
    pass


class TwoPagesAcrossPages(_InLayout, clipboard_tests.AcrossPages):
    pass


class TwoContinuousCopyAndPaste(_InLayout, clipboard_tests.CopyAndPaste):
    LAYOUT = "two_continuous"


class CoverPageAcrossPages(_InLayout, clipboard_tests.AcrossPages):
    LAYOUT, COVER = "two_continuous", True


class SideBySideDrag(clipboard_tests.Fixture):
    """A shape dragged from the left page onto the right one, and back, with the mouse."""

    def test_dragged_onto_the_right_page_and_undone(self):
        reading.set_layout(self.w, "two")
        pump()
        v = self.v
        side_by_side(self, v, 0, 1)
        self.w.set_tool("editobjects")
        pump()
        objs = v.content_objects(0)
        circle = next(it for it in objs.items if it["kind"] == "shape" and
                      abs(it["rect"].x0 - 250) < 1)
        v.select_objects(0, [circle])
        before = canon(v.doc)
        p0, p1 = v.pages[0], v.pages[1]
        start = p0.to_screen_pt(pymupdf.Point(335.36, 74.64)).toPoint()   # (on its line)
        # straight across, at the same height: onto the right-hand page
        end = p0.mapFromGlobal(p1.mapToGlobal(QPoint(start.x() - 200, start.y())))
        QTest.mousePress(p0, Qt.LeftButton, Qt.NoModifier, start)
        QTest.mouseMove(p0, start + QPoint(5, 0))
        QTest.mouseMove(p0, end)
        self.assertEqual(getattr(v, "_drop_ghost", (None,))[0], 1)
        QTest.mouseRelease(p0, Qt.LeftButton, Qt.NoModifier, end)
        pump()
        self.assertEqual(len(clipboard_tests.page_objects.Objects(v.doc[0]).items),
                         len(objs.items) - 1)
        moved = [it for it in clipboard_tests.page_objects.Objects(v.doc[1]).items
                 if it["kind"] == "shape"]
        self.assertEqual(len(moved), 1)
        self.assertAlmostEqual(moved[0]["rect"].x0, circle["rect"].x0 - 200, delta=2)
        self.assertAlmostEqual(moved[0]["rect"].y0, circle["rect"].y0, delta=2)
        v.undo()
        pump()
        self.assertEqual(canon(v.doc), before)


# ---- small text typed enlarged, on the right-hand page --------------------------------------
class _RightPage:
    """The sheet of test_small_text_editing twice, shown two side by side: the text goes on
    the right-hand one."""

    def setUp(self):
        for tool in ("addtext", "edittext"):
            annotations.reset_tool_props(tool)
        d = pymupdf.open()
        for _ in range(2):
            d.new_page(width=2592, height=1728)
        path = os.path.join(tempfile.mkdtemp(), "sheets.pdf")
        d.save(path)
        self.w = w = MainWindow()
        w.resize(1400, 900)
        w.show()
        pump()
        w.open_file(path)
        pump()
        self.v = w.view()
        reading.set_layout(w, "two_continuous")
        self.v.set_zoom(self.ZOOM)
        pump(20)
        side_by_side(self, self.v, 0, 1)
        self.pw = self.v.pages[1]
        self.spot = pymupdf.Point(300, 300)
        self.at = self.pw.to_screen(pymupdf.Rect(self.spot, self.spot)).topLeft().toPoint()

    def words(self):
        self.assertEqual(self.v.doc[0].get_text("words"), [])     # (nothing on the left)
        return self.v.doc[1].get_text("words")


class RightPageSmallText(_RightPage, small_text_tests.SmallText):
    pass


class RightPageNormalZoom(_RightPage, small_text_tests.NormalZoom):
    pass


# ---- pages scanned in, printing --------------------------------------------------------------
class _ThreePages(unittest.TestCase):
    def setUp(self):
        d = pymupdf.open()
        for i in range(3):
            p = d.new_page()
            p.insert_text((72, 72), "Page %d" % (i + 1), fontsize=20)
            p.draw_line((72, 100 + i), (500, 103 + i), color=(0, 0, 0), width=0.05)
        self.path = os.path.join(tempfile.mkdtemp(), "three.pdf")
        d.save(self.path)
        self.w = MainWindow()
        self.w.resize(1300, 900)
        self.w.show()
        pump()
        self.w.open_file(self.path)
        pump()
        self.v = self.w.view()
        self.w.lock_btn.setChecked(False)       # (the page order: locked by default)

    def tearDown(self):
        self.v.dirty = False
        self.w._close_confirmed = True
        self.w.close()
        pump()


class ScannedAndPrinted(_ThreePages):
    def scan_in(self, n):
        """File > Scan, Done into the current document (as the random battery does it)."""
        from kanzonas import scan_dialog, scan_net
        from PySide6.QtCore import QBuffer, QByteArray, QIODevice
        from PySide6.QtGui import QColor
        dlg = scan_dialog.ScanDialog(self.w, discover=lambda cancel=None, log=None: ([], []),
                                     open_scanner=lambda d: None)
        try:
            pages = []
            for k in range(n):
                img = QImage(425, 550, QImage.Format_RGB32)
                img.fill(QColor(250, 250, 245))
                p = QPainter(img)
                p.fillRect(40, 40 + 30 * k, 200, 12, QColor(20, 20, 20))
                p.end()
                data = QByteArray()
                buf = QBuffer(data)
                buf.open(QIODevice.WriteOnly)
                img.save(buf, "PNG")
                pages.append(scan_net.check_image(bytes(data), 50))
            dlg.pages = pages
            dlg.rb_current.setChecked(True)
            dlg.ocr.setChecked(False)
            dlg.finish()
        finally:
            dlg._stop()
            dlg.deleteLater()
        pump()

    def test_scanned_pages_take_their_places_in_the_spreads(self):
        for layout, cover in (("two", False), ("two_continuous", True), ("single", False)):
            self.w.a_cover.setChecked(cover)
            reading.set_layout(self.w, None)
            reading.set_layout(self.w, layout)
            v = self.v
            v.goto_page(1)
            pump()
            before = canon(v.doc)
            n = v.doc.page_count
            self.scan_in(2)
            self.assertEqual(v.doc.page_count, n + 2)
            self.assertEqual(len(v.pages), n + 2)
            shown = [i for i, pw in enumerate(v.pages) if not pw.isHidden()]
            want = v.spread(v.current_page()) if v.paged() else list(range(n + 2))
            self.assertEqual(shown, want, layout)
            if v.two_up():
                for i in want:
                    row = v.spread(i)
                    if len(row) == 2:
                        side_by_side(self, v, *row)
            v.undo()
            pump()
            self.assertEqual(canon(v.doc), before)
            self.assertEqual(len(v.pages), n)

    def test_dark_thin_lines_print_the_same_in_two_pages(self):
        from kanzonas.print_dialog import PrintDialog
        dpi, k = 300, 300 / 72.0

        def printed(index):
            dlg = PrintDialog(self.w, self.v)
            dlg.dark_lines.setChecked(True)
            r = self.v.doc[index].rect
            img = QImage(int(r.width * k), int(r.height * k), QImage.Format_RGB32)
            img.fill(0xFFFFFFFF)
            p = QPainter(img)
            self.assertTrue(dlg._draw_bands(p, index, QRectF(0, 0, img.width(),
                                                             img.height()), dpi))
            p.end()
            dlg.deleteLater()
            return img

        want = [printed(i) for i in range(3)]
        reading.set_layout(self.w, "two")
        self.v.goto_page(2)
        pump()
        for i in range(3):
            got = printed(i)
            self.assertEqual(got, want[i], i)
            # the 0.05 pt line prints solid (Dark thin lines), on every page
            x = int(286 * k)
            dark = min(QImage.pixelColor(got, x, y).lightness()
                       for y in range(int((100 + i - 4) * k), int((103 + i + 7) * k)))
            self.assertLess(dark, 40)


# ---- Full screen and Presentation: no edit outside modify ------------------------------------
class FullScreenEdits(_ThreePages):
    def test_edits_in_full_screen_are_undo_steps(self):
        reading.set_layout(self.w, "two")
        reading.enter_full_screen(self.w)
        pump()
        v = self.v
        before = canon(v.doc)
        steps = len(v._undo)
        v.apply_drag_tool(1, "rect", pymupdf.Point(100, 100), pymupdf.Point(200, 180), False)
        pump()
        self.assertEqual(len(v._undo), steps + 1)
        # Delete (the window's shortcut) on the selected markup, in full screen
        v.select_xref(1, [a.xref for a in v.doc[1].annots()][0])
        v.setFocus()
        QTest.keyClick(v.pages[1], Qt.Key_Delete)
        pump()
        self.assertEqual(list(v.doc[1].annots()), [])
        self.assertEqual(len(v._undo), steps + 2)
        v.undo()
        v.undo()
        pump()
        self.assertEqual(canon(v.doc), before)
        reading.leave_full_screen(self.w)
        pump()

    def test_presentation_changes_nothing(self):
        v = self.v
        page = v.doc[0]
        annotations.write(page, {"kind": "rect", "rect": pymupdf.Rect(80, 80, 200, 200),
                                 "props": annotations.tool_props("rect")})
        del page
        v._clear_caches()
        before = canon(v.doc)
        steps, dirty = len(v._undo), v.dirty
        p = reading.start_presentation(self.w)
        pump()
        for key in (Qt.Key_Space, Qt.Key_Delete, Qt.Key_Backspace, Qt.Key_B, Qt.Key_B,
                    Qt.Key_L, Qt.Key_End, Qt.Key_Home):
            QTest.keyClick(p, key)
            pump(2)
        QTest.keyClick(p, Qt.Key_Z, Qt.ControlModifier)          # (no undo from here)
        QTest.keyClick(p, Qt.Key_V, Qt.ControlModifier)          # (no paste either)
        pump()
        p.repaint()
        QTest.keyClick(p, Qt.Key_Escape)
        pump()
        self.assertEqual(canon(v.doc), before)
        self.assertEqual((len(v._undo), v.dirty), (steps, dirty))

    def test_presentation_shows_edits_made_in_the_window(self):
        v = self.v
        p = reading.start_presentation(self.w)
        pump()
        first = p.grab().toImage()
        v.apply_drag_tool(0, "rect", pymupdf.Point(100, 100), pymupdf.Point(400, 400), False)
        pump()
        self.assertNotEqual(p.grab().toImage(), first)        # (not the page as it was)
        v.delete_pages([1, 2])
        pump()
        p.go(5)
        self.assertEqual(p.page, 0)
        p.close()
        pump()


if __name__ == "__main__":
    unittest.main()
