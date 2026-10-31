"""The test package. At interpreter exit, the windows and views the tests left behind are
closed and deleted while the QApplication (held by each test module's APP) is still alive.
Left to PySide's own module shutdown, the QApplication destroys them during Python's final
teardown, their Python overrides run on half-dead objects, and the process dies after
reporting OK (exit code 1 on Windows, SIGSEGV on Linux).

atexit runs last-registered first: this hook is registered after PySide6 is imported, so it
runs before PySide's shutdown.

Settings: QSettings resolves its folder once per process, so changing HOME inside a test does
nothing after the first QSettings exists. The whole run is pointed at a fresh temporary folder
here instead (on Linux and macOS; on Windows the native store is the registry and the path is
ignored), so the tests never read or write the developer's real KanzonasPDF settings. Within a
run the store is still shared, so a test that depends on a remembered option sets it."""
import atexit
import gc
import os
import tempfile

os.environ.setdefault("KANZONAS_LANG", "en")      # the tests check English texts

from PySide6.QtCore import QCoreApplication, QEvent, QSettings  # noqa: E402  (before atexit)
from PySide6.QtWidgets import QApplication, QMainWindow, QToolBar, QMenu

_SETTINGS_DIR = tempfile.mkdtemp(prefix="kanzonas-test-settings-")
for _fmt in (QSettings.NativeFormat, QSettings.IniFormat):
    QSettings.setPath(_fmt, QSettings.UserScope, _SETTINGS_DIR)


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
