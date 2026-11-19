"""Back and Forward (View > Go to, the buttons beside Undo and Redo, the page's right-click
menu, Alt+Left / Alt+Right): back to where you were before a jump (a link, a bookmark, Go to
page, First / Last page, a page in the page list, a markup in the Markups list, the first
match of a search), and forward again; also across documents (a link to another PDF), and to
a document whose tab was closed since (opened again). A step to the next page or scrolling
isn't a jump.

The owner, 19 Nov 2026: "I think we need a back (and forward) button, up by the ribbon but
not in a tab. So the user can go back to the previous page after clicking on an internal
link. It should also have a selection in the right-click drop down. Alt + left arrow (back)
and alt + right arrow (fwd) should also be added"; "I would like all of your suggestions,
including cross-document ability".

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_back_forward
"""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402
from PySide6.QtCore import QPoint  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import main_window  # noqa: E402

FOLDER = tempfile.mkdtemp()


def pdf(name, pages, link_to=None, other=None):
    """A PDF of pages letter pages, "Page N" on each; page 1 links to page link_to (0-based)
    or to the first page of the file other."""
    d = pymupdf.open()
    for i in range(pages):
        d.new_page(width=612, height=792).insert_text((72, 100), "Page %d WORD%d" % (i + 1, i),
                                                      fontsize=20)
    r = pymupdf.Rect(72, 200, 300, 220)
    if link_to is not None:
        d[0].insert_link({"kind": pymupdf.LINK_GOTO, "from": r, "page": link_to,
                          "to": pymupdf.Point(0, 0)})
    if other is not None:
        d[0].insert_link({"kind": pymupdf.LINK_GOTOR, "from": r, "file": other, "page": 0})
    path = os.path.join(FOLDER, name)
    d.save(path)
    return path


class History(unittest.TestCase):
    def setUp(self):
        w = self.w = main_window.MainWindow()
        self.addCleanup(lambda: [setattr(x, "_close_confirmed", True) or x.close()
                                 for x in main_window.windows()])
        w.resize(1100, 800)
        w.show()
        APP.processEvents()

    def open(self, path):
        self.w.open_file(path)
        APP.processEvents()
        v = self.w.view()
        v.set_zoom(1.0)
        v.goto_page(0)      # (the app opens a file again where it was left: a test before)
        APP.processEvents()
        return v

    def click_link(self, v):
        """The link on page 1 (followed from where the window is)."""
        v.follow_link(v.doc[0].get_links()[0])
        APP.processEvents()

    def at(self):
        v = self.w.view()
        return os.path.basename(v.path), v.current_page()


class InOneDocument(History):
    def setUp(self):
        super().setUp()
        self.v = self.open(pdf("plan.pdf", 30, link_to=20))

    def test_back_after_a_link_and_forward_again(self):
        self.assertFalse(self.w.a_back.isEnabled())
        self.click_link(self.v)
        self.assertEqual(self.at(), ("plan.pdf", 20))
        self.assertTrue(self.w.a_back.isEnabled())
        self.w.a_back.trigger()
        APP.processEvents()
        self.assertEqual(self.at(), ("plan.pdf", 0))
        self.assertTrue(self.w.a_forward.isEnabled())
        self.w.a_forward.trigger()
        APP.processEvents()
        self.assertEqual(self.at(), ("plan.pdf", 20))

    def test_back_comes_back_to_the_same_spot_and_zoom(self):
        self.v.goto_page(3, 250)
        APP.processEvents()
        before = self.v.location()
        self.v.goto_page(12, remember=True)
        self.v.set_zoom(2.0)
        APP.processEvents()
        self.w.go_back()
        APP.processEvents()
        after = self.v.location()
        self.assertEqual(after["page"], 3)
        self.assertAlmostEqual(after["y"], before["y"], delta=2)
        self.assertAlmostEqual(after["zoom"], 1.0)

    def test_the_next_page_isnt_a_jump(self):
        self.w.a_next_page.trigger()
        self.w.a_next_page.trigger()
        APP.processEvents()
        self.assertFalse(self.w.a_back.isEnabled())

    def test_jumps_that_count(self):
        for jump in (lambda: self.w.a_last_page.trigger(),
                     lambda: self.w.page_spin.setValue(8),
                     lambda: self.w._on_thumb_clicked(15)):
            with self.subTest():
                n = len(self.w._back)
                jump()
                APP.processEvents()
                self.assertEqual(len(self.w._back), n + 1)

    def test_a_new_jump_after_back_drops_forward(self):
        self.click_link(self.v)
        self.w.go_back()
        APP.processEvents()
        self.w.a_last_page.trigger()
        APP.processEvents()
        self.assertFalse(self.w.a_forward.isEnabled())

    def test_the_first_match_of_a_search_is_a_jump(self):
        self.v.find("WORD25")
        for _ in range(50):
            APP.processEvents()
        self.assertEqual(self.v.current_page(), 25)
        self.w.go_back()
        APP.processEvents()
        self.assertEqual(self.v.current_page(), 0)

    def test_the_shortcuts_and_where_the_buttons_are(self):
        self.assertEqual(self.w.a_back.shortcut().toString(), "Alt+Left")
        self.assertEqual(self.w.a_forward.shortcut().toString(), "Alt+Right")
        quick = self.w.quick_tb.actions()
        self.assertIn(self.w.a_back, quick)
        self.assertIn(self.w.a_forward, quick)

    def test_the_right_click_menu_has_them_first(self):
        from PySide6.QtWidgets import QMenu
        seen = []

        class Menu(QMenu):
            def exec(self, *_a):
                seen.extend(self.actions())
        ev = mock.Mock()
        ev.globalPosition.return_value.toPoint.return_value = QPoint(0, 0)
        with mock.patch("PySide6.QtWidgets.QMenu", Menu):
            self.v.pages[0]._content_menu(ev, pymupdf.Point(400, 600))
        self.assertEqual(seen[:2], [self.w.a_back, self.w.a_forward])


class MiddleClick(History):
    """Ctrl+middle-click on a link (the Hand: no Ctrl, as a left click) shows its place aside,
    in a view-only tab of the document or in the split view (Preferences > Mouse; asked the
    first time). The owner, 19 Nov 2026: "click a link by clicking my scroll wheel and opening
    the same document in another tab with that location"; "View only (tab needs to say so in
    parentheses next to it), but Split View as an option in settings and a one time popup".
    """
    def setUp(self):
        super().setUp()
        old = self.w.settings.value(self.w.LINK_ASIDE)
        self.addCleanup(lambda: self.w.settings.setValue(self.w.LINK_ASIDE, old)
                        if old is not None else self.w.settings.remove(self.w.LINK_ASIDE))
        self.v = self.open(pdf("plan.pdf", 30, link_to=20))
        self.w.set_tool("select")

    def middle_click(self, mods=None, move=0):
        from PySide6.QtCore import QEvent, QPointF, Qt
        from PySide6.QtGui import QMouseEvent
        mods = Qt.ControlModifier if mods is None else mods
        page = self.v.pages[0]
        at = QPointF(page.to_screen_pt(pymupdf.Point(100, 210)))
        end = at + QPointF(move, 0)
        page.mousePressEvent(QMouseEvent(QEvent.MouseButtonPress, at, page.mapToGlobal(at),
                                         Qt.MiddleButton, Qt.MiddleButton, mods))
        page.mouseReleaseEvent(QMouseEvent(QEvent.MouseButtonRelease, end,
                                           page.mapToGlobal(end), Qt.MiddleButton,
                                           Qt.NoButton, mods))
        for _ in range(5):
            APP.processEvents()

    def use(self, choice):
        self.w.settings.setValue(self.w.LINK_ASIDE, choice)

    def test_a_view_only_tab_at_the_links_place(self):
        self.use("tab")
        self.middle_click()
        self.assertEqual(self.w.tabs.count(), 2)
        tab = self.w.view()
        self.assertIsNot(tab, self.v)
        self.assertEqual(self.w.tabs.tabText(self.w.tabs.indexOf(tab)), "plan.pdf (view only)")
        self.assertIs(tab.doc, self.v.doc)
        self.assertEqual(tab.current_page(), 20)
        self.assertEqual(self.v.current_page(), 0)          # (the first one stays where it was)

    def test_the_view_only_tab_doesnt_edit_and_saves_the_original(self):
        self.use("tab")
        self.middle_click()
        tab = self.w.view()
        said = []
        tab.statusMessage.connect(said.append)
        tab.modify(lambda: None, [0])
        self.assertIn("view-only", said[-1])
        self.assertIs(self.w._doc_view(), self.v)

    def test_closing_the_view_only_tab_keeps_the_document(self):
        self.use("tab")
        self.middle_click()
        self.w.close_tab(self.w.tabs.indexOf(self.w.view()))
        APP.processEvents()
        self.assertEqual(self.w.tabs.count(), 1)
        self.assertFalse(self.v.doc.is_closed)

    def test_closing_the_document_closes_its_view_only_tabs(self):
        self.use("tab")
        self.middle_click()
        self.w.close_tab(self.w.tabs.indexOf(self.v))
        APP.processEvents()
        self.assertEqual(self.w.tabs.count(), 0)

    def test_in_the_split_view(self):
        self.use("split")
        self.middle_click()
        self.assertEqual(self.w.tabs.count(), 1)
        self.assertTrue(self.w.split_dock.isVisible())
        sv = self.w._split_view
        self.assertIs(sv._source, self.v)
        self.assertEqual(sv.current_page(), 20)

    def test_asked_the_first_time(self):
        self.w.settings.remove(self.w.LINK_ASIDE)
        with mock.patch.object(main_window.MainWindow, "_ask_link_aside",
                               return_value="tab") as ask:
            self.middle_click()
        self.assertTrue(ask.called)
        self.assertEqual(self.w.tabs.count(), 2)

    def test_without_ctrl_it_only_moves_the_page(self):
        from PySide6.QtCore import Qt
        self.use("tab")
        self.middle_click(mods=Qt.NoModifier)
        self.assertEqual(self.w.tabs.count(), 1)

    def test_with_the_hand_no_ctrl_is_needed(self):
        from PySide6.QtCore import Qt
        self.use("tab")
        self.w.set_tool("hand")
        self.middle_click(mods=Qt.NoModifier)
        self.assertEqual(self.w.tabs.count(), 2)

    def test_a_drag_moves_the_page_and_opens_nothing(self):
        self.use("tab")
        self.middle_click(move=40)
        self.assertEqual(self.w.tabs.count(), 1)


class AcrossDocuments(History):
    def setUp(self):
        super().setUp()
        self.b = pdf("details.pdf", 5)
        self.a = pdf("index.pdf", 10, other=self.b)
        self.va = self.open(self.a)
        self.va.goto_page(0)

    def test_back_to_the_document_the_link_was_in(self):
        self.click_link(self.va)
        for _ in range(30):
            APP.processEvents()
        self.assertEqual(self.at()[0], "details.pdf")
        self.w.go_back()
        APP.processEvents()
        self.assertEqual(self.at(), ("index.pdf", 0))
        self.w.go_forward()
        APP.processEvents()
        self.assertEqual(self.at()[0], "details.pdf")

    def test_a_closed_tab_is_opened_again(self):
        self.va.goto_page(6)
        APP.processEvents()
        self.click_link(self.va)
        for _ in range(30):
            APP.processEvents()
        self.assertEqual(self.at()[0], "details.pdf")
        self.w.close_tab(self.w.tabs.indexOf(self.va))
        APP.processEvents()
        self.w.go_back()
        for _ in range(10):
            APP.processEvents()
        self.assertEqual(self.at(), ("index.pdf", 6))

    def test_an_unsaved_closed_document_is_skipped(self):
        place = {"view": None, "path": None, "page": 0, "y": 0, "x": 0, "zoom": 1.0}
        self.w._back.append(place)
        self.w._sync_nav()
        self.w.go_back()
        APP.processEvents()
        self.assertEqual(self.at()[0], "index.pdf")
        self.assertFalse(self.w.a_back.isEnabled())


if __name__ == "__main__":
    unittest.main()
