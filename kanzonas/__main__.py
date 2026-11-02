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
    path = name if os.path.isabs(name) else os.path.join(QDir.tempPath(), name)
    if sys.platform.startswith("linux") and (_made_by_someone_else(path)
                                             or _made_by_someone_else(path + ".lock")):
        # (the shared temporary folder, without a runtime folder: another user put a file
        # at this user's name. Never hand them the files; run on its own)
        return None, None
    lock = QLockFile(path + ".lock")
    locked = lock.tryLock(10000)
    try:
        for _attempt in range(3):
            sock = QLocalSocket()
            sock.connectToServer(name)
            if sock.waitForConnected(3000):
                if sys.platform.startswith("linux") and not _same_user(sock):
                    sock.abort()
                    return None, None
                return None, sock
            server = QLocalServer()
            if sys.platform != "win32":
                # (a socket in the shared temporary folder: only this user may connect)
                server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
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


def _made_by_someone_else(path):
    """Linux: a file at path that belongs to another user."""
    try:
        return os.lstat(path).st_uid != os.getuid()
    except OSError:
        return False


def _same_user(sock):
    """Linux: the program listening at the other end of the connected QLocalSocket runs as
    this user (the kernel says who it is). False when it can't be told."""
    import socket
    import struct
    try:
        fd = int(sock.socketDescriptor())
        s = socket.socket(fileno=os.dup(fd))
        try:
            cred = s.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
        finally:
            s.close()
        return struct.unpack("3i", cred)[1] == os.getuid()
    except (OSError, ValueError, AttributeError):
        return False


TOKEN_VAR = "XDG_ACTIVATION_TOKEN"     # Wayland's permission to bring a window to the front


def instance_name(app_name, user):
    """The name the running KanzonasPDF listens at for files opened while it runs. Windows: a
    pipe name of this user's. Linux: a socket in this user's own runtime folder
    ($XDG_RUNTIME_DIR, which no other user can enter), so nobody else can take the name
    first; the shared temporary folder when there is none."""
    name = f"{app_name}-{user}"
    if sys.platform == "win32":
        return name
    runtime = os.environ.get("XDG_RUNTIME_DIR") or ""
    try:
        if os.path.isabs(runtime) and os.path.isdir(runtime) \
                and os.stat(runtime).st_uid == os.getuid() \
                and len(os.fsencode(os.path.join(runtime, name))) < 108:
            # (a socket's path holds at most 107 bytes: a longer one can't be listened at)
            return os.path.join(runtime, name)
    except OSError:
        pass
    return name


def file_arguments(args):
    """The files to open from the command line, as absolute paths. A file manager can pass
    file:// addresses (Linux); options (--...) are left out."""
    out = []
    for p in args:
        if p.startswith("--"):
            continue
        linux = sys.platform.startswith("linux")
        if p.startswith("file://") or (linux and p.startswith("file:/")):
            from PySide6.QtCore import QUrl
            url = QUrl(p)
            if linux and url.host().lower() == "localhost":
                url.setHost("")         # (file://localhost/... is a file on this computer)
            local = url.toLocalFile()
            if local:
                p = local
        out.append(os.path.abspath(p))
    return out


def without_qt_options(args, qt_args):
    """args (sys.argv after the program) without what Qt took for itself (-platform xcb,
    -style ..., -display ...): qt_args is QApplication.arguments() after the program, the
    same list with those taken out. Names that aren't UTF-8 are kept as Python has them."""
    out, j = [], 0
    for a in args:
        if j < len(qt_args) and os.fsencode(a).decode("utf-8", "replace") == qt_args[j]:
            out.append(a)
            j += 1
    return out


def _log_error(what):
    """Write the exception being handled to startup-errors.log in the data folder (a windowed
    exe has no console); returns that file's path."""
    import traceback
    from . import paths
    path = os.path.join(paths.data_dir(), "startup-errors.log")
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write("%s %s\n%s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), what,
                                      traceback.format_exc()))
    except OSError:
        pass
    return path


def _reset_settings():
    """Keep a copy of every setting in the data folder, then clear them all. Returns the
    copy's path."""
    from . import paths
    st = paths.settings()
    path = os.path.join(paths.data_dir(), "settings-before-reset.txt")
    try:
        with open(path, "w", encoding="utf-8") as f:
            for key in st.allKeys():
                f.write("%s = %r\n" % (key, st.value(key)))
    except OSError:
        pass
    st.clear()
    st.sync()
    return path


def _build_window(app):
    """The main window. A stored setting that stops it from being built (each one is
    checked as it's read, so this is a last line of defense) doesn't stop KanzonasPDF from
    starting: the settings are put aside and it starts with the default ones."""
    from . import main_window
    try:
        return MainWindow()
    except Exception:
        _log_error("building the window")
        for w in main_window.windows():         # the half-built one
            app.removeEventFilter(w)
            w.deleteLater()
        main_window._WINDOW_REFS.clear()
    kept = _reset_settings()
    win = MainWindow()
    from PySide6.QtWidgets import QMessageBox
    from .i18n import tr
    QTimer.singleShot(0, lambda: QMessageBox.warning(
        win, APP_NAME, tr("A saved setting couldn't be used, so KanzonasPDF started with the "
                          "default settings. The old ones are listed in:\n{path}").format(
                              path=kept)))
    return win


def end_on_sigterm(app, win):
    """Linux: signing out or shutting down ends programs with SIGTERM (and Ctrl+C or closing
    the terminal it was started from, with SIGINT or SIGHUP). Treat it as Windows
    ending KanzonasPDF: keep the open files and backups of unsaved changes for the next
    start, without asking, then quit. (Python only sees a signal when Python code runs, so
    the signal wakes the Qt event loop through a socket.)"""
    import signal
    import socket
    from PySide6.QtCore import QSocketNotifier
    try:
        r, w = socket.socketpair()
        r.setblocking(False)
        w.setblocking(False)
        signal.set_wakeup_fd(w.fileno(), warn_on_full_buffer=False)
    except (OSError, ValueError):
        return None
    got = []
    signal.signal(signal.SIGTERM, lambda *_: got.append(1))
    # Ctrl+C in the terminal it was started from, and that terminal closing, the same way
    # (Ctrl+C otherwise stops whatever Python code runs at that moment, half done, and
    # KanzonasPDF goes on). A signal set to be ignored (nohup, a background job) stays so.
    for sig in (signal.SIGINT, signal.SIGHUP):
        try:
            if signal.getsignal(sig) is not signal.SIG_IGN:
                signal.signal(sig, lambda *_: got.append(1))
        except (OSError, ValueError):
            pass
    notifier = QSocketNotifier(r.fileno(), QSocketNotifier.Type.Read, app)

    def woke():
        try:
            r.recv(512)
        except OSError:
            pass
        if not got:
            return
        got.clear()
        try:
            win.windows_ending()
        except Exception:
            _log_error("keeping the documents at SIGTERM")
        app.quit()
    notifier.activated.connect(woke)
    app._kz_sigterm = (r, w, notifier)          # (kept alive with the application)
    return notifier


def _refresh_menu_entry():
    """Linux: the menu entry KanzonasPDF added follows the AppImage when it was moved."""
    try:
        from . import __version__, linux_desktop
        linux_desktop.refresh(__version__)
    except Exception:
        _log_error("updating the applications menu entry")


def main():
    if len(sys.argv) >= 2 and sys.argv[1] == "--selftest":
        from .selftest import run
        sys.exit(run(sys.argv[2] if len(sys.argv) > 2 else "selftest.log"))
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_NAME)
    if sys.platform.startswith("linux"):
        # the menu entry it belongs to (Wayland shows that entry's name and icon for it)
        app.setDesktopFileName("kanzonaspdf")
    args = sys.argv[1:]
    if sys.platform.startswith("linux"):
        # (Qt's own options, like -platform xcb on Wayland, aren't files to open)
        args = without_qt_options(args, app.arguments()[1:])
    files = file_arguments(args)
    # One window: if KanzonasPDF is already running, hand it the files and quit
    # (double-clicking PDFs opens them as tabs, like PDF-XChange).
    import getpass
    name = instance_name(APP_NAME, getpass.getuser())
    server, sock = first_instance(name)
    if sock is not None:
        from . import winfocus
        winfocus.allow_foreground()          # so the running window may come to the front
        token = os.environ.get(TOKEN_VAR, "") if sys.platform.startswith("linux") else ""
        if token and "\n" not in token:
            # Wayland: the permission to come to the front this start was given, handed on
            # (a line no file can be: the files are absolute paths)
            sock.write(("%s=%s\n" % (TOKEN_VAR, token)).encode("utf-8"))
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
                    got = [ln.decode("utf-8", "replace").strip() for ln in lines if ln.strip()]
                    for ln in [x for x in got if x.startswith(TOKEN_VAR + "=")]:
                        got.remove(ln)
                        if sys.platform.startswith("linux"):
                            # Qt uses it when the window is brought to the front next
                            os.environ[TOKEN_VAR] = ln[len(TOKEN_VAR) + 1:]
                    deliver(got)
            conn.readyRead.connect(read)
    if server is not None:
        server.newConnection.connect(incoming)
    from .branding import app_icon
    app.setWindowIcon(app_icon())
    from . import i18n, paths, theme
    i18n.install_qt(app)                 # Qt's own buttons and dialogs in the same language
    theme.apply(app, paths.stored_str(paths.settings(), "theme", "system"))
    win = _build_window(app)
    # a setup closing KanzonasPDF to update it, or Windows shutting down, closes no windows
    app.commitDataRequest.connect(win.windows_ending)
    if sys.platform.startswith("linux"):
        end_on_sigterm(app, win)
    win.show()
    # (an unexpected error here leaves the window open rather than ending the program)
    try:
        win.recover_backups()
    except Exception:
        _log_error("offering backups")
    if not files:
        try:
            win.restore_session()
        except Exception:
            _log_error("reopening the last documents")
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
    # what the first typed word and the first Edit text change would wait for, made ready
    # while nothing is going on: the spelling word list, the installed fonts
    from . import spelling, text_edit
    spelling.load_soon()
    QTimer.singleShot(3000, text_edit.system_fonts_soon)
    if sys.platform.startswith("linux"):
        QTimer.singleShot(4000, _refresh_menu_entry)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
