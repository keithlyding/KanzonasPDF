"""Where KanzonasPDF keeps settings and personal files.

Installed / normal: settings in the Windows registry, files (signatures, stamp images, your
certificate) in the user's AppData folder.
Portable: when a file named portable.txt sits next to KanzonasPDF.exe, everything goes in a
"data" folder beside the exe instead, so it travels with a USB stick and leaves nothing on
the computer.
"""

import os
import sys

from PySide6.QtCore import QSettings, QStandardPaths

APP = "KanzonasPDF"
MARKER = "portable.txt"


def app_dir():
    """Folder of KanzonasPDF.exe (or of the source checkout when run from Python)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def is_portable():
    return os.path.exists(os.path.join(app_dir(), MARKER))


def data_dir(sub=""):
    """Folder for personal files (created if missing)."""
    if is_portable():
        base = os.path.join(app_dir(), "data")
    else:
        base = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)
    d = os.path.join(base, sub) if sub else base
    os.makedirs(d, exist_ok=True)
    return d


def settings():
    """The app's settings store (an .ini file in data/ when portable)."""
    if is_portable():
        return QSettings(os.path.join(data_dir(), "settings.ini"), QSettings.IniFormat)
    return QSettings(APP, APP)
