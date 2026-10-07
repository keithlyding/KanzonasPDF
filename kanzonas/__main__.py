"""Entry point: python -m kanzonas [file.pdf ...]"""

import os
import sys

# A windowed Windows exe has no console: give libraries that print or log somewhere to write.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from .main_window import MainWindow, APP_NAME


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
    from PySide6.QtNetwork import QLocalServer, QLocalSocket
    import getpass
    name = f"{APP_NAME}-{getpass.getuser()}"
    sock = QLocalSocket()
    sock.connectToServer(name)
    if sock.waitForConnected(300):
        sock.write(("\n".join(files) + "\n").encode("utf-8"))
        sock.flush()
        sock.waitForBytesWritten(1000)
        sock.disconnectFromServer()
        return
    from .app_icon import icon
    app.setWindowIcon(icon())
    from PySide6.QtCore import QSettings
    from . import theme
    theme.apply(app, QSettings(APP_NAME, APP_NAME).value("theme", "system"))
    win = MainWindow()
    win.show()
    for path in files:
        win.open_file(path)

    server = QLocalServer()
    QLocalServer.removeServer(name)          # stale socket from a crashed run
    server.listen(name)

    def incoming():
        conn = server.nextPendingConnection()

        def read():
            for line in bytes(conn.readAll()).decode("utf-8", "replace").splitlines():
                if line.strip():
                    win.open_file(line.strip())
            win.setWindowState(win.windowState() & ~Qt.WindowMinimized)
            win.raise_()
            win.activateWindow()
        conn.readyRead.connect(read)
    server.newConnection.connect(incoming)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
