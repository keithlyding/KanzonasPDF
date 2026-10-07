"""Entry point: python -m kanzonas [file.pdf ...]"""

import sys

from PySide6.QtWidgets import QApplication

from .main_window import MainWindow, APP_NAME


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_NAME)
    app.setStyle("Fusion")
    win = MainWindow()
    win.show()
    for path in sys.argv[1:]:
        win.open_file(path)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
