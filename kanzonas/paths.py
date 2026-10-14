r"""Where KanzonasPDF keeps settings and personal files.

Installed / normal: settings in the Windows registry, files (signatures, stamp images, your
certificate) in the user's AppData folder.
Portable: when a file named portable.txt sits next to KanzonasPDF.exe, everything goes in a
"data" folder beside the exe instead, so it travels with a USB stick and leaves nothing on
the computer.

portable.txt can hold settings, one per line (the PortableApps.com package uses them):
  data=..\..\Data    keep the data somewhere else (relative to the exe's folder)
  updates=off        the program doesn't update itself (the PortableApps.com platform does)
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


def portable_options():
    """key=value settings in portable.txt (keys lowercased); {} when there are none."""
    out = {}
    try:
        with open(os.path.join(app_dir(), MARKER), encoding="utf-8", errors="replace") as f:
            for line in f:
                key, eq, value = line.partition("=")
                if eq and key.strip() and " " not in key.strip():
                    out[key.strip().lower()] = value.strip()
    except OSError:
        pass
    return out


def follow_drive(path, exists=os.path.exists, splitdrive=os.path.splitdrive):
    """Portable copies move between PCs and the stick's drive letter changes (E: here, F:
    there): a remembered file that's gone from its old drive but is on the drive the program
    now runs from is found there. Other paths come back unchanged."""
    if not path or not is_portable() or exists(path):
        return path
    old, rest = splitdrive(path)
    here = splitdrive(app_dir())[0]
    if old and here and old.lower() != here.lower() and exists(here + rest):
        return here + rest
    return path


def platform_updates():
    """True when something else (the PortableApps.com platform) updates this copy."""
    return is_portable() and portable_options().get("updates", "").lower() == "off"


def data_dir(sub=""):
    """Folder for personal files (created if missing)."""
    if is_portable():
        where = portable_options().get("data")
        base = os.path.normpath(os.path.join(app_dir(), where)) if where else \
            os.path.join(app_dir(), "data")
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
