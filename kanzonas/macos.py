"""KanzonasPDF on macOS: what the Mac does differently (everything here is used only when
sys.platform == "darwin"; Windows and Linux never call it).

- Finder hands PDFs to the app as Apple events, not on the command line: double-clicking a
  PDF, Open With, dropping one on the Dock icon. Qt turns them into QFileOpenEvent on the
  QApplication, both when they start the app and while it runs (macOS never starts a second
  copy for them). FileOpenFilter passes them to the same code as files handed over by a second
  copy started from a terminal.
- The application menu (KanzonasPDF, left of File) holds About, Preferences and Quit: their
  commands get those menu roles, and every other command none, so Qt's guess from a menu
  text ("Options...", "Exit ...", Spanish ones) never moves a command there.
- Qt maps the Ctrl of every shortcut to Command (Ctrl+S is Command-S) and Alt to Option.
  mac_keys() says so in texts that name keys (tool tips, the manual's shortcut table).
- The release has one disk image per kind of Mac (dmg_name()); the app is unsigned, so it
  never replaces itself: Download opens the release page.
"""

import os
import platform
import re
import sys

BUNDLE_ID = "io.github.keithlyding.kanzonaspdf"
# the release's disk images (names that never change, like the AppImage's)
DMG = {"arm64": "KanzonasPDF-macos-arm64.dmg", "x86_64": "KanzonasPDF-macos-x86_64.dmg"}


def is_mac():
    return sys.platform == "darwin"


def machine(name=None):
    """'arm64' (Apple silicon) or 'x86_64' (Intel) for this Mac (or for a platform.machine()
    name)."""
    m = (name if name is not None else platform.machine()).lower()
    return "arm64" if m in ("arm64", "aarch64") else "x86_64"


def dmg_name(name=None):
    """The release's disk image for this kind of Mac."""
    return DMG[machine(name)]


def app_bundle(executable=None):
    """The KanzonasPDF.app folder this program runs from (…/X.app/Contents/MacOS/program), or
    None (run from source, or not in an app bundle)."""
    exe = os.path.abspath(executable or sys.executable)
    macos = os.path.dirname(exe)
    contents = os.path.dirname(macos)
    bundle = os.path.dirname(contents)
    if os.path.basename(macos) == "MacOS" and os.path.basename(contents) == "Contents" \
            and bundle.endswith(".app"):
        return bundle
    return None


def translocated(bundle=None):
    """True when macOS runs the app from a read-only random place (App Translocation: an
    app downloaded from the internet and opened where it was, inside the disk image or the
    Downloads folder, before it was moved to Applications)."""
    bundle = bundle if bundle is not None else app_bundle()
    return bool(bundle) and "/AppTranslocation/" in bundle


# ---- files opened from Finder ------------------------------------------------------------

def file_open_filter(deliver, parent=None):
    """An event filter for the QApplication that hands the files of Finder's open requests
    (QFileOpenEvent) to deliver([absolute paths])."""
    from PySide6.QtCore import QEvent, QObject

    class FileOpenFilter(QObject):
        def eventFilter(self, obj, event):
            if event.type() == QEvent.Type.FileOpen:
                path = event.file()
                if not path:
                    url = event.url()
                    path = url.toLocalFile() if url.isLocalFile() else ""
                if path:
                    deliver([os.path.abspath(path)])
                return True
            return False

    return FileOpenFilter(parent)


# ---- the application menu ----------------------------------------------------------------

def set_menu_roles(win):
    """About, Preferences and Quit go to the application menu; nothing else does."""
    from PySide6.QtGui import QAction
    for a in win.findChildren(QAction):
        if a.menuRole() == QAction.MenuRole.TextHeuristicRole:
            a.setMenuRole(QAction.MenuRole.NoRole)
    win.a_about.setMenuRole(QAction.MenuRole.AboutRole)
    win.a_prefs.setMenuRole(QAction.MenuRole.PreferencesRole)
    win.a_exit.setMenuRole(QAction.MenuRole.QuitRole)


# ---- key names ---------------------------------------------------------------------------

# Qt's Ctrl is the Command key on a Mac, its Alt the Option key and its Meta the Control key
_SYMBOL = {"Meta": "⌃", "Alt": "⌥", "Shift": "⇧", "Ctrl": "⌘"}
_WORD = {"Meta": "Control", "Alt": "Option", "Shift": "Shift", "Ctrl": "Cmd"}
_ORDER = ("Meta", "Alt", "Shift", "Ctrl")           # the order macOS writes them in
_KEY_SYMBOL = {"Up": "↑", "Down": "↓", "Left": "←", "Right": "→",
               "Plus": "+", "Minus": "-", "Del": "⌦", "Delete": "⌦",
               "Backspace": "⌫", "Enter": "↩", "Return": "↩", "Esc": "⎋",
               "Escape": "⎋", "Tab": "⇥", "Space": "Space", "PgUp": "⇞",
               "PgDown": "⇟", "Home": "↖", "End": "↘"}
_COMBO = re.compile(r"\b((?:(?:Ctrl|Alt|Shift|Meta)\+)+)([A-Za-z][A-Za-z0-9]*|[^\sA-Za-z])")


def mac_keys(text, symbols=True, option="Option"):
    """text with its key combinations as a Mac shows them: "Ctrl+Shift+H" -> "⇧⌘H" (or, with
    symbols False, "Cmd+Shift+H"), "Alt+click" -> "Option+click", "Ctrl+wheel" ->
    "Cmd+wheel". Keys without Ctrl, Alt or Meta (F1, Shift+T) stay as they are. option: the
    Option key's name in the text's language."""
    words = dict(_WORD, Alt=option)

    def one(m):
        mods = [x for x in m.group(1).split("+") if x]
        key = m.group(2)
        if not any(x in ("Ctrl", "Alt", "Meta") for x in mods):
            return m.group(0)
        mods = [x for x in _ORDER if x in mods]
        if key[0].isalpha() and len(key) > 1 and key not in _KEY_SYMBOL \
                and not re.fullmatch(r"F\d{1,2}", key):
            # a mouse action or a word (click, drag, wheel): Option+click
            return "+".join(words[x] for x in reversed(mods)) + "+" + key
        if symbols:
            return "".join(_SYMBOL[x] for x in mods) + _KEY_SYMBOL.get(key, key.upper())
        return "+".join(words[x] for x in reversed(mods)) + "+" + key
    return _COMBO.sub(one, text)
