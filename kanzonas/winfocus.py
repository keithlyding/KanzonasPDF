"""Bringing the KanzonasPDF window to the front when a PDF is opened while it runs.

Opening a PDF (double-click, Open with) starts a second KanzonasPDF that hands the file to
the running one and quits. Windows lets a program come to the front only if it is in front
already or was given leave: otherwise it just flashes its taskbar button. The second
program, started by the click, has that right, so it passes it on (AllowSetForegroundWindow)
before handing over the file; the running one then brings itself forward.
"""

import sys

ASFW_ANY = 0xFFFFFFFF               # (DWORD)-1: any process may set the foreground window


def _user32():
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        return ctypes.windll.user32
    except (ImportError, AttributeError, OSError):
        return None


def allow_foreground():
    """In the program handing over a file: let the running KanzonasPDF come to the front."""
    user32 = _user32()
    if user32 is not None:
        try:
            user32.AllowSetForegroundWindow(ASFW_ANY)
        except Exception:
            pass


def bring_to_front(win):
    """In the running KanzonasPDF: show the window in front, restored if it was minimized
    (a maximized window stays maximized)."""
    from PySide6.QtCore import Qt
    state = win.windowState()
    if state & Qt.WindowMinimized:
        win.setWindowState(state & ~Qt.WindowMinimized)
    win.show()
    win.raise_()
    win.activateWindow()
    user32 = _user32()
    if user32 is not None:
        try:
            user32.SetForegroundWindow(int(win.winId()))
        except Exception:
            pass
