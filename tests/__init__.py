"""The test package. At interpreter exit, the windows and views the tests left behind are
closed and deleted while the QApplication (held by each test module's APP) is still alive.
Left to PySide's own module shutdown, the QApplication destroys them during Python's final
teardown, their Python overrides run on half-dead objects, and the process dies after
reporting OK (exit code 1 on Windows, SIGSEGV on Linux).

atexit runs last-registered first: this hook is registered after PySide6 is imported, so it
runs before PySide's shutdown.

Settings: QSettings resolves its folder once per process, so changing HOME inside a test does
nothing after the first QSettings exists. The whole run is pointed at a fresh temporary folder
here instead, on every system: the app's own store (paths.settings, QSettings(APP, APP)) is
the registry on Windows and the user's preferences (cfprefsd) on macOS, where that folder is
ignored, so here it is an .ini file in the folder instead. The tests never read or write the
developer's real KanzonasPDF settings: a remembered CAD mouse mode or Snap to objects made two
tests fail on a contributor's Windows machine (13 Nov 2026), and one of them on every other
run, as each run saved the snap switch it had turned. Within a run the store is still shared,
so a test that depends on a remembered option sets it."""
import atexit
import gc
import os
import sys
import tempfile
import unittest

os.environ.setdefault("KANZONAS_LANG", "en")      # the tests check English texts

from PySide6.QtCore import QCoreApplication, QEvent, QSettings  # noqa: E402  (before atexit)
from PySide6.QtWidgets import QApplication, QMainWindow, QToolBar, QMenu

_SETTINGS_DIR = tempfile.mkdtemp(prefix="kanzonas-test-settings-")
for _fmt in (QSettings.NativeFormat, QSettings.IniFormat):
    QSettings.setPath(_fmt, QSettings.UserScope, _SETTINGS_DIR)
QSettings.setDefaultFormat(QSettings.IniFormat)     # (QSettings() with no names, as Print uses)

from kanzonas import paths as _paths  # noqa: E402

_app_settings = _paths.settings


def _test_settings():
    """paths.settings, in the temporary folder on every system (portable: its own .ini)."""
    if _paths.is_portable():
        return _app_settings()
    return QSettings(QSettings.IniFormat, QSettings.UserScope, _paths.APP, _paths.APP)


_paths.settings = _test_settings


def _shutdown_qt():
    app = QApplication.instance()
    if app is None:
        return
    for _ in range(3):              # timers the tests left queued run while views exist
        app.processEvents()
    for w in QApplication.topLevelWidgets():
        # Destroying a main window with its toolbars, menus and ribbon buttons still holding
        # its actions segfaults about one time in three inside Qt (an action being destroyed
        # tells a tool button that is already gone; seen with gdb in QWidget::removeAction).
        # Taking the actions out of every toolbar and menu first makes the teardown clean.
        # The real app never hits this: it exits after closing one window, which we tested.
        try:
            app.removeEventFilter(w)
            if isinstance(w, QMainWindow):
                for tb in w.findChildren(QToolBar):
                    tb.clear()
                for m in w.findChildren(QMenu):
                    m.clear()
                w.menuBar().clear()
        except RuntimeError:
            pass
    for w in QApplication.topLevelWidgets():
        try:
            w.hide()
            w.deleteLater()
        except RuntimeError:
            pass
    for _ in range(3):
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        app.processEvents()
    gc.collect()


atexit.register(_shutdown_qt)


def _delete_closed_windows():
    """The main windows closed by the tests before, deleted. A primary window isn't deleted
    when it closes (in the app, closing it quits), so each one a test made stayed with its
    1,180 widgets: about 800,000 by the end of the suite, which every later walk over the
    widgets (a theme change, a polish, the collector) went through. test_theme_gc's theme
    change took 13 s on Linux and 636 s on the Mac build with them (23 Nov 2026)."""
    main_window = sys.modules.get("kanzonas.main_window")
    app = QApplication.instance()
    if main_window is None or app is None:
        return
    still_open = set(map(id, main_window.windows()))
    closed = []
    for w in QApplication.topLevelWidgets():
        try:
            if (isinstance(w, main_window.MainWindow) and id(w) not in still_open
                    and not w.isVisible()):
                # (its actions out of its toolbars and menus first, as _shutdown_qt does)
                app.removeEventFilter(w)
                for tb in w.findChildren(QToolBar):
                    tb.clear()
                for m in w.findChildren(QMenu):
                    m.clear()
                w.menuBar().clear()
                w.deleteLater()
                closed.append(w)
        except RuntimeError:        # (deleted on the C++ side already)
            pass
    if closed:
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)


_run_test = unittest.TestCase.run


def _run_after_deleting_closed_windows(self, result=None):
    _delete_closed_windows()
    return _run_test(self, result)


unittest.TestCase.run = _run_after_deleting_closed_windows
