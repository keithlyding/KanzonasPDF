"""Entry point: python -m kanzonas [file.pdf ...]"""

import os
import sys

# A windowed Windows exe has no console: give libraries that print or log somewhere to write.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

from PySide6.QtWidgets import QApplication

from .main_window import MainWindow, APP_NAME


def main():
    if len(sys.argv) >= 2 and sys.argv[1] == "--selftest":
        from .selftest import run
        sys.exit(run(sys.argv[2] if len(sys.argv) > 2 else "selftest.log"))
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_NAME)
    from PySide6.QtCore import QSettings
    from . import theme
    theme.apply(app, QSettings(APP_NAME, APP_NAME).value("theme", "system"))
    win = MainWindow()
    win.show()
    for path in sys.argv[1:]:
        win.open_file(path)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
