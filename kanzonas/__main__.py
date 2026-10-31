"""Entry point: python -m kanzonas [file.pdf ...]"""

import os
import sys
import time

_T0 = time.perf_counter()      # launch clock: the self-test reports true launch-to-ready time

# A windowed Windows exe has no console: give libraries that print or log somewhere to write.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

# The self-test checks English texts (the user manual names the commands in English): run it
# in English whatever the language set (before main_window builds its translated tables)
if "--selftest" in sys.argv[1:2]:
    os.environ["KANZONAS_LANG"] = "en"

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from .main_window import MainWindow, APP_NAME


def first_instance(name):
    """Which KanzonasPDF shows the window: (a listening QLocalServer, None) for the first one,
    (None, a socket connected to it) for the others, which hand over their files and quit.
    Programs started at the same moment (Explorer opens one per file when several PDFs are
    opened together) take turns deciding, with a lock file, so exactly one of them listens.
    It listens straight away, before building its window: the others connect meanwhile and
    their files wait. (None, None): no way to tell, run on its own."""
    from PySide6.QtCore import QDir, QLockFile
    from PySide6.QtNetwork import QAbstractSocket, QLocalServer, QLocalSocket
    lock = QLockFile(os.path.join(QDir.tempPath(), name + ".lock"))
    locked = lock.tryLock(10000)
    try:
        for _attempt in range(3):
            sock = QLocalSocket()
            sock.connectToServer(name)
            if sock.waitForConnected(3000):
                return None, sock
            server = QLocalServer()
            if server.listen(name):
                return server, None
            if server.serverError() != QAbstractSocket.SocketError.AddressInUseError:
                break
            if sys.platform != "win32":
                # nothing answered, so this is a socket file left by a run that crashed (a
                # Windows pipe goes away with its program: there the name is in use by a
                # running KanzonasPDF, so try connecting again, never take the name over)
                QLocalServer.removeServer(name)
                if server.listen(name):
                    return server, None
        return None, None
    finally:
        if locked:
            lock.unlock()


def main():
    if len(sys.argv) >= 2 and sys.argv[1] == "--selftest":
        from .selftest import run
        sys.exit(run(sys.argv[2] if len(sys.argv) > 2 else "selftest.log"))
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_NAME)
    files = [os.path.abspath(p) for p in sys.argv[1:] if not p.startswith("--")]
    # One window: if KanzonasPDF is already running, hand it the files and quit
    # (double-clicking PDFs opens them as tabs, like PDF-XChange).
    import getpass
    name = f"{APP_NAME}-{getpass.getuser()}"
    server, sock = first_instance(name)
    if sock is not None:
        from . import winfocus
        winfocus.allow_foreground()          # so the running window may come to the front
        sock.write(("\n".join(files) + "\n").encode("utf-8"))
        sock.flush()
        sock.waitForBytesWritten(1000)
        # the running one answers with its window: this program, started by the click, may
        # bring it to the front (Windows doesn't let the running one do it itself)
        winfocus.front_from_reply(sock)
        sock.disconnectFromServer()
        return
    from . import winfocus
    # Files handed over before the window is ready wait here (several PDFs opened at once)
    state = {"win": None, "waiting": [], "asked": False, "unanswered": []}

    def answer(conn):
        """Tell the program handing over files which window to bring to the front."""
        conn.write(("HWND %d\n" % winfocus.handle(state["win"])).encode("ascii"))
        conn.flush()

    def deliver(paths):
        win = state["win"]
        if win is None:
            state["waiting"] += paths
            state["asked"] = True
            return
        for p in paths:
            win.open_file(p)
        winfocus.bring_to_front(win)

    def incoming():
        while server is not None and server.hasPendingConnections():
            conn = server.nextPendingConnection()
            # straight away, before opening the files: the window to bring forward (once
            # there is one)
            if state["win"] is not None:
                answer(conn)
            else:
                state["unanswered"].append(conn)

            def read(conn=conn, buf=[b""]):
                buf[0] += bytes(conn.readAll())
                *lines, buf[0] = buf[0].split(b"\n")
                if lines:
                    deliver([ln.decode("utf-8", "replace").strip() for ln in lines
                             if ln.strip()])
            conn.readyRead.connect(read)
    if server is not None:
        server.newConnection.connect(incoming)
    from .branding import app_icon
    app.setWindowIcon(app_icon())
    from . import i18n, paths, theme
    i18n.install_qt(app)                 # Qt's own buttons and dialogs in the same language
    theme.apply(app, paths.settings().value("theme", "system"))
    win = MainWindow()
    # a setup closing KanzonasPDF to update it, or Windows shutting down, closes no windows
    app.commitDataRequest.connect(win.windows_ending)
    win.show()
    win.recover_backups()
    if not files:
        win.restore_session()
    for path in files:
        win.open_file(path)
    state["win"] = win
    for conn in state["unanswered"]:
        try:
            answer(conn)
        except RuntimeError:
            pass                        # (it gave up waiting and went)
    if state["asked"]:
        deliver(state["waiting"])
    QTimer.singleShot(5000, win.start_update_check)    # once a day at most; never blocks start-up
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
