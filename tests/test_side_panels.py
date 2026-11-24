"""Several panels open at once (the owner, 23 Nov 2026: "the side panels must be able to show
several at once, on the right and on the left, stacked, with handles to resize"): each panel
is a dock widget of its own (kanzonas/side_panels.py), stacked on either side, resized by the
handle between them, moved to the other side by its title, opened and closed by its icon on
the panel strip, its menu command or its key, and remembered across restarts, a layout saved
by 1.16 included. A pulled-out window gets the panels of the window it came from.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_side_panels
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402
from PySide6.QtCore import QByteArray, QEvent, QPoint, QPointF, Qt, QTimer  # noqa: E402
from PySide6.QtGui import QContextMenuEvent, QMouseEvent  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QDockWidget, QMenu  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import main_window, paths, side_panels  # noqa: E402

LEFT, RIGHT = Qt.LeftDockWidgetArea, Qt.RightDockWidgetArea

# The layout 1.16.4 saved (LAYOUT_VERSION 1, made by that version's own MainWindow): Pages
# 260 wide on the left (then holding Bookmarks, Layers, Objects and Sets as tabs, with its
# Bookmarks tab in front), Properties closed so the Tool chest showed in its place, and the
# Markups list open at the bottom.
OLD_LAYOUT = bytes.fromhex(
    "000000ff00000001fd0000000300000000000001040000019dfc0200000001fb0000000a0070006100670065"
    "0073010000006a0000019d0000008f00ffffff00000001000000f00000019dfc0200000001fc0000006a0000"
    "019d0000009100fffffffa000000010200000002fb0000001400700072006f00700065007200740069006500"
    "730000000000ffffffff0000005700fffffffb000000120074006f006f006c00630068006500730074010000"
    "0000ffffffff0000009100ffffff000000030000048e000000f6fc0100000001fb0000000e006d0061007200"
    "6b00750070007301000000220000048e0000021b00ffffff0000028e0000019d000000040000000400000008"
    "00000008fc0000000400000000000000010000001600700061006e0065006c005f0073007400720069007003"
    "00000000ffffffff0000000000000000000000020000000100000008006d00610069006e0000000000ffffff"
    "ff000000000000000000000002000000020000000a0074006f006f006c00730000000000ffffffff00000000"
    "000000000000000e0061007200720061006e006700650000000000ffffffff00000000000000000000000200"
    "0000010000000c0072006900620062006f006e0100000000ffffffff0000000000000000")


def a_pdf():
    d = pymupdf.open()
    for i in range(3):
        d.new_page().insert_text((72, 100), "Page %d" % (i + 1))
    d.set_toc([[1, "One", 1], [1, "Two", 2]])
    path = os.path.join(tempfile.mkdtemp(), "doc.pdf")
    d.save(path)
    return path


def settle():
    for _ in range(3):
        APP.processEvents()


def forget_layout():
    s = paths.settings()
    for key in ("window_state", "geometry", "ui_mode", "panel_strip"):
        s.remove(key)
    s.sync()


class Panels(unittest.TestCase):
    def setUp(self):
        forget_layout()                 # the settings store is shared by the whole test run
        self.addCleanup(forget_layout)
        self.addCleanup(self.close_all)

    @staticmethod
    def close_all():
        for w in main_window.windows():
            w._close_confirmed = True
            for v in w._views():
                v.dirty = False
            w.close()
        settle()

    def window(self, document=False):
        w = main_window.MainWindow()
        w.resize(1200, 800)
        w.show()
        w.activateWindow()
        if document:
            w.open_file(a_pdf())
        settle()
        return w

    def close(self, w):
        w._close_confirmed = True
        w.close()
        settle()

    def assert_stacked(self, w, upper, lower, side):
        """upper and lower both on screen on side, one above the other in one column."""
        for d in (upper, lower):
            self.assertTrue(side_panels.showing(d), d.objectName())
            self.assertEqual(w.dockWidgetArea(d), side, d.objectName())
        a, b = upper.geometry(), lower.geometry()
        self.assertEqual(a.left(), b.left())
        self.assertLessEqual(a.bottom(), b.top())
        self.assertGreaterEqual(b.height(), side_panels.FAIR_MIN)
        self.assertGreaterEqual(a.height(), side_panels.FAIR_MIN)

    # ---- several at once -------------------------------------------------------------------
    def test_every_panel_is_a_dock_of_its_own_that_moves(self):
        w = self.window()
        names = [d.objectName() for d in w._panels()]
        self.assertEqual(names, ["pages", "bookmarks", "layers", "objects", "sets",
                                 "properties", "toolchest", "markups"])
        for d in w._panels():
            self.assertIsInstance(d, QDockWidget)
            self.assertTrue(d.features() & QDockWidget.DockWidgetMovable, d.objectName())
            self.assertTrue(d.features() & QDockWidget.DockWidgetClosable, d.objectName())
            self.assertFalse(d.features() & QDockWidget.DockWidgetFloatable, d.objectName())
        # the start: Pages on the left, Properties on the right, the rest closed
        self.assertEqual([d.objectName() for d in w._panels() if side_panels.showing(d)],
                         ["pages", "properties"])
        for d in (w.bookmarks_dock, w.layers_dock, w.objects_dock, w.sets_dock):
            self.assertEqual(w.dockWidgetArea(d), LEFT)

    def test_two_panels_at_once_on_the_left(self):
        w = self.window(document=True)
        w.strip_actions[w.bookmarks_dock].trigger()
        settle()
        self.assert_stacked(w, w.dock, w.bookmarks_dock, LEFT)
        self.assertEqual(w.bookmarks.tree.topLevelItemCount(), 2)   # (it shows the bookmarks)
        w.strip_actions[w.layers_dock].trigger()
        settle()
        self.assert_stacked(w, w.bookmarks_dock, w.layers_dock, LEFT)
        self.assertTrue(side_panels.showing(w.dock))        # all three at once

    def test_two_panels_at_once_on_the_right(self):
        w = self.window()
        w.strip_actions[w.objects_dock].trigger()
        settle()
        # right-click its title > Move to the right side (what dragging it there does)
        menu = side_panels.title_menu(w, w.objects_dock)
        texts = [a.text() for a in menu.actions()]
        self.assertIn("Move to the &right side", texts)
        self.assertNotIn("Move to the &left side", texts)       # (it's on the left already)
        self.assertIn("Bookmarks", texts)          # then the window's list of panels
        next(a for a in menu.actions() if a.text() == "Move to the &right side").trigger()
        menu.deleteLater()
        settle()
        self.assert_stacked(w, w.props_dock, w.objects_dock, RIGHT)
        self.assertTrue(w.a_objects_panel.isChecked())
        self.assertTrue(w.strip_actions[w.objects_dock].isChecked())
        # and a third one there, while Pages stays on the left
        side_panels.move_to(w, w.sets_dock, RIGHT)
        settle()
        self.assert_stacked(w, w.objects_dock, w.sets_dock, RIGHT)
        self.assertEqual(w.dockWidgetArea(w.dock), LEFT)
        self.assertTrue(side_panels.showing(w.dock))
        # and back
        menu = side_panels.title_menu(w, w.sets_dock)
        next(a for a in menu.actions() if a.text() == "Move to the &left side").trigger()
        menu.deleteLater()
        settle()
        self.assert_stacked(w, w.dock, w.sets_dock, LEFT)

    def test_the_title_menu_comes_up_on_a_right_click_of_the_title_only(self):
        w = self.window()
        shown = []

        def close_menu():
            menu = QApplication.activePopupWidget()
            if isinstance(menu, QMenu):
                shown.append([a.text() for a in menu.actions()])
                menu.close()
        d = w.dock
        for pos in (QPoint(20, 6), QPoint(20, d.height() - 20)):
            QTimer.singleShot(50, close_menu)
            d.contextMenuEvent(QContextMenuEvent(QContextMenuEvent.Mouse, pos,
                                                 d.mapToGlobal(pos)))
            QTest.qWait(100)
        self.assertEqual(len(shown), 1)             # the title; not inside the panel
        self.assertEqual(shown[0][0], "Move to the &right side")
        self.assertIn("Properties", shown[0])

    # ---- resizing --------------------------------------------------------------------------
    def drag(self, w, start, by):
        """A left-button drag on the window itself (where the handles between panels are)."""
        def send(t, pos, button, buttons):
            e = QMouseEvent(t, QPointF(pos), QPointF(w.mapToGlobal(pos)), button, buttons,
                            Qt.NoModifier)
            QApplication.sendEvent(w, e)
        send(QEvent.MouseButtonPress, start, Qt.LeftButton, Qt.LeftButton)
        for k in range(1, 9):
            send(QEvent.MouseMove, start + by * k / 8, Qt.NoButton, Qt.LeftButton)
            APP.processEvents()         # (Qt applies a handle's move on its next turn)
        send(QEvent.MouseButtonRelease, start + by, Qt.LeftButton, Qt.NoButton)
        settle()

    def test_the_handle_between_two_panels_resizes_them(self):
        w = self.window()
        w.strip_actions[w.bookmarks_dock].trigger()
        settle()
        up, down = w.dock.geometry(), w.bookmarks_dock.geometry()
        handle = QPoint(up.center().x(), (up.bottom() + down.top()) // 2)
        self.assertIsNone(w.childAt(handle))            # (the handle is the window's own)
        self.drag(w, handle, QPoint(0, 80))
        self.assertAlmostEqual(w.dock.height(), up.height() + 80, delta=4)
        self.assertAlmostEqual(w.bookmarks_dock.height(), down.height() - 80, delta=4)
        self.assertEqual(w.dock.width(), up.width())
        # the handle beside the page makes the left side wider
        x = w.dock.geometry().right() + 3
        self.assertIsNone(w.childAt(QPoint(x, up.center().y())))
        self.drag(w, QPoint(x, up.center().y()), QPoint(60, 0))
        self.assertAlmostEqual(w.dock.width(), up.width() + 60, delta=4)
        self.assertEqual(w.bookmarks_dock.width(), w.dock.width())
        # and the sizes come back the next time
        sizes = w.dock.size(), w.bookmarks_dock.size()
        self.close(w)
        w2 = self.window()
        self.assertTrue(side_panels.showing(w2.bookmarks_dock))
        self.assertAlmostEqual(w2.dock.width(), sizes[0].width(), delta=4)
        self.assertAlmostEqual(w2.dock.height(), sizes[0].height(), delta=4)
        self.assertAlmostEqual(w2.bookmarks_dock.height(), sizes[1].height(), delta=4)

    def test_a_panel_shown_again_gets_its_share_of_the_height(self):
        w = self.window()
        for d in (w.bookmarks_dock, w.layers_dock, w.objects_dock):
            w._toggle_panel(d)
        settle()
        column = side_panels.column(w, w.dock)
        self.assertEqual(column, [w.dock, w.bookmarks_dock, w.layers_dock, w.objects_dock])
        for d in column:
            self.assertGreaterEqual(d.height(), side_panels.FAIR_MIN, d.objectName())

    # ---- remembered --------------------------------------------------------------------------
    def test_the_layout_comes_back_after_a_restart(self):
        w = self.window()
        w._toggle_panel(w.bookmarks_dock)               # Pages and Bookmarks on the left
        side_panels.move_to(w, w.layers_dock, RIGHT)    # Properties and Layers on the right
        w._toggle_panel(w.markups_dock)
        settle()
        w.resizeDocks([w.dock], [300], Qt.Horizontal)
        settle()
        place = {d.objectName(): (side_panels.showing(d), w.dockWidgetArea(d))
                 for d in w._panels()}
        self.close(w)
        self.assertIsInstance(w.settings.value("window_state"), QByteArray)

        w2 = self.window()
        self.assertEqual({d.objectName(): (side_panels.showing(d), w2.dockWidgetArea(d))
                          for d in w2._panels()}, place)
        self.assert_stacked(w2, w2.dock, w2.bookmarks_dock, LEFT)
        self.assert_stacked(w2, w2.props_dock, w2.layers_dock, RIGHT)
        self.assertAlmostEqual(w2.dock.width(), 300, delta=4)
        # the check marks agree with the panels
        for d, a in w2._panel_actions():
            self.assertEqual(a.isChecked(), side_panels.showing(d), a.text())
            self.assertEqual(w2.strip_actions[d].isChecked(), side_panels.showing(d))

    def test_a_layout_saved_by_1_16_still_comes_back(self):
        s = paths.settings()
        s.setValue("window_state", QByteArray(OLD_LAYOUT))
        s.sync()
        w = self.window(document=True)
        # what it knew: Pages 260 wide, Properties closed, the Tool chest in its place, the
        # Markups list open
        self.assertTrue(side_panels.showing(w.dock))
        self.assertAlmostEqual(w.dock.width(), 260, delta=4)
        self.assertFalse(side_panels.showing(w.props_dock))
        self.assertTrue(side_panels.showing(w.chest_dock))
        self.assertTrue(side_panels.showing(w.markups_dock))
        self.assertTrue(w.a_chest.isChecked())
        self.assertFalse(w.a_props.isChecked())
        # the panels that were its tabs are closed below it, and open beside it
        for d in (w.bookmarks_dock, w.layers_dock, w.objects_dock, w.sets_dock):
            self.assertFalse(side_panels.showing(d), d.objectName())
            self.assertEqual(w.dockWidgetArea(d), LEFT)
        w.strip_actions[w.bookmarks_dock].trigger()
        settle()
        self.assert_stacked(w, w.dock, w.bookmarks_dock, LEFT)
        self.assertTrue(w.ribbon_tb.isVisible())
        self.assertTrue(w.panel_strip.isVisible())
        # saved again in the new form
        self.close(w)
        w2 = self.window()
        self.assert_stacked(w2, w2.dock, w2.bookmarks_dock, LEFT)

    def test_a_damaged_layout_gives_the_usual_one(self):
        s = paths.settings()
        s.setValue("window_state", QByteArray(b"\x00\x00\x00\xff" + b"not a layout" * 9))
        s.sync()
        w = self.window()
        self.assertEqual([d.objectName() for d in w._panels() if side_panels.showing(d)],
                         ["pages", "properties"])

    # ---- the strip -------------------------------------------------------------------------
    def test_each_icon_on_the_strip_opens_and_closes_its_panel(self):
        w = self.window()
        self.assertEqual(list(w.strip_actions), w._panels())
        menu = dict(w._panel_actions())
        for d, a in w.strip_actions.items():
            was = side_panels.showing(d)
            a.trigger()
            settle()
            self.assertNotEqual(side_panels.showing(d), was, d.objectName())
            self.assertEqual(a.isChecked(), not was)
            self.assertEqual(menu[d].isChecked(), not was)
            a.trigger()
            settle()
            self.assertEqual(side_panels.showing(d), was, d.objectName())
            self.assertEqual(a.isChecked(), was)
            self.assertEqual(menu[d].isChecked(), was)
        # its panels open together; closing one leaves the others
        for d in (w.bookmarks_dock, w.layers_dock, w.objects_dock, w.sets_dock):
            w.strip_actions[d].trigger()
        settle()
        w.strip_actions[w.layers_dock].trigger()
        settle()
        self.assertEqual([d.objectName() for d in w._panels() if side_panels.showing(d)],
                         ["pages", "bookmarks", "objects", "sets", "properties"])

    def test_a_tab_behind_comes_to_the_front_first(self):
        # Properties and Tool chest share a tab bar: the chest's icon brings it in front,
        # a second click closes it
        w = self.window()
        self.assertFalse(side_panels.showing(w.chest_dock))
        w.strip_actions[w.chest_dock].trigger()
        settle()
        self.assertTrue(side_panels.showing(w.chest_dock))
        self.assertFalse(side_panels.showing(w.props_dock))
        self.assertFalse(w.strip_actions[w.props_dock].isChecked())
        w.strip_actions[w.props_dock].trigger()           # Properties in front again
        settle()
        self.assertTrue(side_panels.showing(w.props_dock))
        self.assertFalse(w.chest_dock.isHidden())

    def test_without_the_strip_the_menus_open_the_panels(self):
        w = self.window()
        w.a_panel_strip.setChecked(False)
        settle()
        self.assertFalse(w.panel_strip.isVisible())
        for a in (w.a_bookmarks, w.a_layers_panel, w.a_objects_panel, w.a_sets_panel):
            self.assertIn(a, w.view_menu.actions())
            a.trigger()
        settle()
        self.assertEqual([d.objectName() for d in w._panels() if side_panels.showing(d)],
                         ["pages", "bookmarks", "layers", "objects", "sets", "properties"])
        self.close(w)
        w2 = self.window()
        self.assertFalse(w2.panel_strip.isVisible())        # (remembered)
        w2.a_panel_strip.setChecked(True)

    # ---- keys ------------------------------------------------------------------------------
    def test_the_panel_keys(self):
        w = self.window(document=True)
        keys = [(Qt.Key_F4, w.dock), (Qt.Key_F6, w.props_dock), (Qt.Key_F7, w.markups_dock),
                (Qt.Key_F8, w.chest_dock), (Qt.Key_F9, w.bookmarks_dock)]
        for key, d in keys:
            was = side_panels.showing(d)
            QTest.keyClick(w.view(), key)
            settle()
            self.assertNotEqual(side_panels.showing(d), was, d.objectName())
            QTest.keyClick(w.view(), key)
            settle()
            # (F8 then F6: Properties comes back in front of the chest; the chest was closed)
            self.assertEqual(side_panels.showing(d), was, d.objectName())
        # F4 and F9 together: Pages and Bookmarks at once
        QTest.keyClick(w.view(), Qt.Key_F9)
        settle()
        self.assert_stacked(w, w.dock, w.bookmarks_dock, LEFT)
        # a key given to a panel in Keyboard shortcuts works too
        w.a_layers_panel.setShortcut("Ctrl+Alt+Y")
        QTest.keyClick(w.view(), Qt.Key_Y, Qt.ControlModifier | Qt.AltModifier)
        settle()
        self.assertTrue(side_panels.showing(w.layers_dock))

    # ---- ribbon, classic, pulled-out windows -------------------------------------------------
    def test_ribbon_and_classic_layouts(self):
        w = self.window()
        listed = [a for m in w.ribbon.findChildren(QMenu) for a in m.actions()]
        for a in (w.a_bookmarks, w.a_layers_panel, w.a_objects_panel, w.a_sets_panel):
            self.assertIn(a, listed, a.text())       # (under the View tab's Panels arrow)
        w._toggle_panel(w.bookmarks_dock)
        side_panels.move_to(w, w.layers_dock, RIGHT)
        settle()
        w.a_ribbon.setChecked(False)            # classic toolbars
        w._toggle_ribbon()
        settle()
        self.assertTrue(w.tools_tb.isVisible())
        self.assertTrue(w.panel_strip.isVisible())
        self.assert_stacked(w, w.dock, w.bookmarks_dock, LEFT)
        self.assert_stacked(w, w.props_dock, w.layers_dock, RIGHT)
        w.strip_actions[w.sets_dock].trigger()
        settle()
        self.assert_stacked(w, w.bookmarks_dock, w.sets_dock, LEFT)
        self.close(w)
        w2 = self.window()
        self.assertTrue(w2.tools_tb.isVisible())
        self.assertFalse(w2.ribbon_tb.isVisible())
        self.assert_stacked(w2, w2.bookmarks_dock, w2.sets_dock, LEFT)
        self.assert_stacked(w2, w2.props_dock, w2.layers_dock, RIGHT)
        w2.a_ribbon.setChecked(True)
        w2._toggle_ribbon()

    def test_a_pulled_out_window_gets_the_same_panels(self):
        w = self.window(document=True)
        w._toggle_panel(w.bookmarks_dock)
        side_panels.move_to(w, w.objects_dock, RIGHT)
        settle()
        place = {d.objectName(): (side_panels.showing(d), w.dockWidgetArea(d))
                 for d in w._panels()}
        w2 = w.detach_tab(0)
        settle()
        self.assertFalse(w2.primary)
        self.assertEqual({d.objectName(): (side_panels.showing(d), w2.dockWidgetArea(d))
                          for d in w2._panels()}, place)
        self.assert_stacked(w2, w2.dock, w2.bookmarks_dock, LEFT)
        self.assert_stacked(w2, w2.props_dock, w2.objects_dock, RIGHT)
        self.assertEqual(w2.bookmarks.tree.topLevelItemCount(), 2)    # its document's
        self.assertTrue(w2.panel_strip.isVisible())
        # its own strip and keys
        w2.activateWindow()
        w2.strip_actions[w2.layers_dock].trigger()
        settle()
        self.assert_stacked(w2, w2.bookmarks_dock, w2.layers_dock, LEFT)
        self.assertFalse(side_panels.showing(w.layers_dock))          # (not the first one's)
        QTest.keyClick(w2.view(), Qt.Key_F4)
        settle()
        self.assertFalse(side_panels.showing(w2.dock))
        self.assertTrue(side_panels.showing(w.dock))
        # a pulled-out window opened on its own (no window to copy) has the usual panels
        w3 = main_window.MainWindow(primary=False)
        w3.resize(1000, 700)
        w3.show()
        settle()
        self.assertTrue(side_panels.showing(w3.dock))
        w3._toggle_panel(w3.sets_dock)
        settle()
        self.assert_stacked(w3, w3.dock, w3.sets_dock, LEFT)


if __name__ == "__main__":
    unittest.main()
