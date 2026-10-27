"""Bringing the KanzonasPDF window to the front when a PDF is opened while it runs.

Opening a PDF (double-click, Open with) starts a second KanzonasPDF that hands the file to
the running one and quits. Windows lets a program bring a window to the front only if it
was started by the program in front (the second one, started by the click, was) or is in
front already; otherwise the window just flashes its taskbar button. So the running
KanzonasPDF answers the hand-over with its window's handle, and the second program, which
has that right, brings the window to the front itself before quitting. The running one
also tries on its own (if it's minimized, behind other windows...) as a fallback.
"""

import sys

ASFW_ANY = 0xFFFFFFFF               # (DWORD)-1: any process may set the foreground window
SW_RESTORE = 9


def _user32():
    """user32 with the argument types of the calls used here (window handles are pointers
    on 64-bit Windows), or None off Windows."""
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        from ctypes import wintypes
        u = ctypes.windll.user32
        u.AllowSetForegroundWindow.argtypes = [wintypes.DWORD]
        u.SetForegroundWindow.argtypes = [wintypes.HWND]
        u.SetForegroundWindow.restype = wintypes.BOOL
        u.GetForegroundWindow.restype = wintypes.HWND
        u.IsIconic.argtypes = [wintypes.HWND]
        u.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        u.BringWindowToTop.argtypes = [wintypes.HWND]
        u.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.c_void_p]
        u.GetWindowThreadProcessId.restype = wintypes.DWORD
        u.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
        return u
    except (ImportError, AttributeError, OSError):
        return None


def _current_thread():
    import ctypes
    return ctypes.windll.kernel32.GetCurrentThreadId()


def allow_foreground():
    """In the program handing over a file: let the running KanzonasPDF come to the front."""
    user32 = _user32()
    if user32 is not None:
        try:
            user32.AllowSetForegroundWindow(ASFW_ANY)
        except Exception:
            pass


def activate(hwnd):
    """Bring the top-level window hwnd to the front, restored if it's minimized (a maximized
    window stays maximized). From the program handing over a file, which may do so."""
    user32 = _user32()
    if user32 is None or not hwnd:
        return False
    try:
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, SW_RESTORE)
        if user32.SetForegroundWindow(hwnd) and user32.GetForegroundWindow() == hwnd:
            return True
        # Windows said no: take part in the input of the window in front for a moment,
        # which lets this thread hand the front over
        front = user32.GetForegroundWindow()
        theirs = user32.GetWindowThreadProcessId(front, None) if front else 0
        mine = _current_thread()
        if theirs and theirs != mine:
            user32.AttachThreadInput(mine, theirs, True)
            try:
                user32.BringWindowToTop(hwnd)
                user32.SetForegroundWindow(hwnd)
            finally:
                user32.AttachThreadInput(mine, theirs, False)
        return user32.GetForegroundWindow() == hwnd
    except Exception:
        return False


def handle(win):
    """The window handle the running KanzonasPDF sends back to the program handing over a
    file (0 off Windows)."""
    return int(win.winId()) if sys.platform == "win32" else 0


def front_from_reply(sock, wait_ms=3000):
    """In the program handing over a file: read the running KanzonasPDF's answer ("HWND n")
    and bring that window to the front."""
    if not sock.canReadLine() and not sock.waitForReadyRead(wait_ms):
        return False
    line = bytes(sock.readLine()).decode("ascii", "replace").strip()
    if not line.startswith("HWND "):
        return False
    try:
        return activate(int(line.split()[1]))
    except ValueError:
        return False


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
    activate(handle(win))
