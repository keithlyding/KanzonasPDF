"""The test package. At interpreter exit, the windows and views the tests left behind are
closed and deleted while the QApplication (held by each test module's APP) is still alive.
Left to PySide's own module shutdown, the QApplication destroys them during Python's final
teardown, their Python overrides run on half-dead objects, and the process dies after
reporting OK (exit code 1 on Windows, SIGSEGV on Linux).

atexit runs last-registered first: this hook is registered after PySide6 is imported, so it
runs before PySide's shutdown."""
import atexit
import gc

from PySide6.QtCore import QCoreApplication, QEvent  # noqa: E402  (before atexit.register)
from PySide6.QtWidgets import QApplication


def _shutdown_qt():
    app = QApplication.instance()
    if app is None:
        return
    for _ in range(3):              # timers the tests left queued run while views exist
        app.processEvents()
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
