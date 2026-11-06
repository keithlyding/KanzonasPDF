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
- The release has one disk image, for Macs with Apple silicon (DMG; none for Intel Macs yet);
  the app is unsigned, so it never replaces itself: Download opens the release page.
"""

import os
import platform
import re
import sys

BUNDLE_ID = "io.github.keithlyding.kanzonaspdf"
# the release's disk image (a name that never changes, like the AppImage's): Macs with Apple
# silicon only, for now (no Intel Mac build)
DMG = "KanzonasPDF-macos-arm64.dmg"


def is_mac():
    return sys.platform == "darwin"


def intel(name=None):
    """True on an Intel Mac (or Intel code run by Rosetta 2), which the release has no
    disk image for. name: a platform.machine() name instead of this computer's."""
    m = (name if name is not None else platform.machine()).lower()
    return m not in ("arm64", "aarch64")


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

def menu_bar_actions(win):
    """Every command in win's menu bar, its submenus' too."""
    out = []

    def walk(menu):
        for a in menu.actions():
            out.append(a)
            if a.menu() is not None:
                walk(a.menu())
    walk(win.menuBar())
    return out


def set_menu_roles(win):
    """About, Preferences and Quit go to the application menu; nothing else in the menu bar
    does. (Only the commands whose role changes are touched: a changed command gives the
    buttons showing it its tool tip again.)"""
    from PySide6.QtGui import QAction
    for a in menu_bar_actions(win):
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
