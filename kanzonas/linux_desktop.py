"""Linux: adding KanzonasPDF to the applications menu and opening PDFs with it.

File > Preferences > General > "Add KanzonasPDF to the applications menu and open PDFs with
it" writes, for this user only (never needs root):
  ~/.local/share/applications/kanzonaspdf.desktop     the menu entry (Exec = the AppImage)
  ~/.local/share/icons/hicolor/256x256/apps/kanzonaspdf.png   its icon
and makes it the default for PDF files (xdg-mime, or ~/.config/mimeapps.list when xdg-mime
isn't installed). Removing takes all of it away again, and gives PDFs back to whatever the
desktop picks when nothing is set. ($XDG_DATA_HOME and $XDG_CONFIG_HOME are used when set.)

The menu entry starts the AppImage at the place it was when it was added; an update puts
the new version at that same place. If the AppImage is moved, the entry is pointed at the
new place the next time it starts from there (refresh()).
"""

import os
import re
import shutil
import subprocess
import sys

from .i18n import tr

DESKTOP_ID = "kanzonaspdf.desktop"
ICON_NAME = "kanzonaspdf"
MIME_TYPES = ("application/pdf",)
MARK = "X-KanzonasPDF-Added=true"      # in the entries KanzonasPDF wrote (only those go)
PREVIOUS = "X-KanzonasPDF-Previous-Default="  # the PDF app this user had chosen before
USER_COPY = ".before-kanzonaspdf"      # a kanzonaspdf.desktop the user made, put aside


def available():
    """The option is offered on Linux only."""
    return sys.platform.startswith("linux")


def _home():
    return os.path.expanduser("~")


def data_home():
    d = os.environ.get("XDG_DATA_HOME") or ""
    return d if os.path.isabs(d) else os.path.join(_home(), ".local", "share")


def config_home():
    d = os.environ.get("XDG_CONFIG_HOME") or ""
    return d if os.path.isabs(d) else os.path.join(_home(), ".config")


def desktop_path():
    return os.path.join(data_home(), "applications", DESKTOP_ID)


def icon_path():
    return os.path.join(data_home(), "icons", "hicolor", "256x256", "apps", ICON_NAME + ".png")


def mimeapps_path():
    return os.path.join(config_home(), "mimeapps.list")


def command():
    """What the menu entry runs: the AppImage, the built program, or (run from source)
    this Python with -m kanzonas. None when there is nothing that would still be there."""
    appimage = os.environ.get("APPIMAGE") or ""
    if appimage and os.path.isfile(appimage):
        return [os.path.abspath(appimage)]
    if getattr(sys, "frozen", False):
        return [os.path.abspath(sys.executable)]
    if sys.executable:
        return [os.path.abspath(sys.executable), "-m", "kanzonas"]
    return None


def _source_dir():
    """The checkout to run -m kanzonas in (run from source), else None."""
    if os.environ.get("APPIMAGE") or getattr(sys, "frozen", False):
        return None
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def exec_quote(arg):
    """One argument of an Exec line, quoted as the Desktop Entry specification asks
    (then escaped once more as any value of the file is)."""
    arg = arg.replace("%", "%%")
    if arg and not re.search(r'[\s"\'\\><~|&;$*?#()`=]', arg):
        return arg
    inner = re.sub(r'(["`$\\])', r"\\\1", arg)
    return ('"%s"' % inner).replace("\\", "\\\\")


def _value(text):
    """A plain value of the file, escaped as the Desktop Entry specification asks
    (a path keeps its spaces exactly: TryExec must name the file)."""
    return (str(text).replace("\\", "\\\\").replace("\n", "\\n").replace("\t", "\\t")
            .replace("\r", "\\r"))


def _unvalue(text):
    """A value of the file as written by _value (or by hand), unescaped."""
    return re.sub(r"\\(.)", lambda m: {"s": " ", "n": "\n", "t": "\t", "r": "\r"}.get(
        m.group(1), m.group(1)), text)


def entry_text(cmd, version="", source_dir=None, previous=()):
    """The kanzonaspdf.desktop file for running cmd (a list of arguments)."""
    lines = [
        "[Desktop Entry]",
        "Type=Application",
        "Version=1.0",
        "Name=KanzonasPDF",
        "GenericName=PDF Editor",
        "GenericName[es]=Editor de PDF",
        "Comment=Read, mark up, measure and edit PDF files",
        "Comment[es]=Lee, marca, mide y edita archivos PDF",
        "Exec=" + " ".join(exec_quote(a) for a in cmd) + " %F",
        "TryExec=" + _value(cmd[0]),
        "Icon=" + ICON_NAME,
        "Terminal=false",
        "StartupNotify=true",
        "StartupWMClass=KanzonasPDF",
        "Categories=Office;Viewer;Graphics;",
        "Keywords=PDF;Markup;Annotate;Measure;CAD;Sign;Edit;",
        "MimeType=" + "".join(t + ";" for t in MIME_TYPES),
    ]
    if source_dir:
        lines.append("Path=" + _value(source_dir))
    if version:
        lines.append("X-KanzonasPDF-Version=" + _value(version))
    if previous:
        lines.append(PREVIOUS + _value("".join(p + ";" for p in previous)))
    lines.append(MARK)
    return "\n".join(lines) + "\n"


def is_added():
    """KanzonasPDF's own menu entry is there."""
    return MARK in _entry_lines()


def _entry_lines():
    """The lines of the menu entry kanzonaspdf.desktop ([] when there's none)."""
    try:
        with open(desktop_path(), encoding="utf-8", errors="replace") as f:
            return f.read().splitlines()
    except OSError:
        return []


def _previous_default():
    """The PDF apps this user had chosen before KanzonasPDF was added (kept in its entry)."""
    for line in _entry_lines():
        if line.startswith(PREVIOUS):
            return [x for x in _unvalue(line[len(PREVIOUS):]).split(";")
                    if x.strip() and x.strip() != DESKTOP_ID]
    return []


def _defaults_in_list(path, mime_type):
    """The apps a mimeapps.list file names as the default for mime_type (its
    [Default Applications] line), in order."""
    try:
        with open(path, encoding="utf-8", errors="surrogateescape") as f:
            lines = f.read().splitlines()
    except OSError:
        return []
    section = None
    for line in lines:
        head = line.strip()
        if head.startswith("[") and head.endswith("]"):
            section = head
            continue
        key, eq, value = line.partition("=")
        if section == "[Default Applications]" and eq and key.strip() == mime_type:
            return [x.strip() for x in value.split(";") if x.strip()]
    return []


def _write(path, data, mode="w"):
    """Write a file in one step (a temporary file beside it, renamed over it)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = "%s.%d.tmp" % (path, os.getpid())
    # (text: bytes that aren't UTF-8, read with surrogateescape, are written back as they were)
    with open(tmp, mode + ("b" if isinstance(data, bytes) else ""),
              **({} if isinstance(data, bytes) else {"encoding": "utf-8",
                                                     "errors": "surrogateescape"})) as f:
        f.write(data)
    os.replace(tmp, path)


def _run(args, runner):
    """Run a desktop tool if it's installed; True when it ran and succeeded."""
    if shutil.which(args[0]) is None:
        return False
    try:
        return runner(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                      stderr=subprocess.DEVNULL, timeout=20).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _icon_png():
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice
    from .branding import icon_pixmap
    data = QByteArray()
    buf = QBuffer(data)
    buf.open(QIODevice.WriteOnly)
    icon_pixmap(256).save(buf, "PNG")
    buf.close()
    return bytes(data)


def _set_default_in_list(path, desktop_id, mime_types, on, restore=()):
    """Make desktop_id the default (on) for mime_types in a mimeapps.list file, or take it
    out of the defaults and the added associations (off). Other lines stay as they are.
    restore: when taking it out leaves no default (xdg-mime replaced the one there was),
    these apps are the default again."""
    try:
        with open(path, encoding="utf-8", errors="surrogateescape") as f:
            lines = f.read().splitlines()
    except OSError:
        lines = []
    if not lines and not on:
        return
    # [(section header or None, [lines])]
    sections = [[None, []]]
    for line in lines:
        head = line.strip()
        if head.startswith("[") and head.endswith("]"):
            sections.append([head, [line]])
        else:
            sections[-1][1].append(line)
    defaults = "[Default Applications]"
    if on and not any(h == defaults for h, _ in sections):
        if lines and lines[-1].strip():
            sections[-1][1].append("")
        sections.append([defaults, [defaults]])
    changed = False
    for head, body in sections:
        if head not in (defaults, "[Added Associations]"):
            continue
        set_here = on and head == defaults
        done = set()
        for i, line in enumerate(body):
            key, eq, value = line.partition("=")
            key = key.strip()
            if not eq or key not in mime_types:
                continue
            ids = [x.strip() for x in value.strip().split(";") if x.strip()]
            new = [x for x in ids if x != desktop_id]
            if set_here:
                new.insert(0, desktop_id)
                done.add(key)
            elif not new and not on and head == defaults and restore:
                new = [x for x in restore if x != desktop_id]
            if new != ids:
                body[i] = "%s=%s;" % (key, ";".join(new)) if new else None
                changed = True
        if set_here:
            missing = ["%s=%s;" % (t, desktop_id) for t in mime_types if t not in done]
            if missing:
                at = len(body)
                while at > 1 and not body[at - 1].strip():
                    at -= 1             # (before the blank lines that end the section)
                body[at:at] = missing
                changed = True
    if not changed:
        return
    out = [line for _h, body in sections for line in body if line is not None]
    _write(path, "\n".join(out) + "\n")


def add(version="", runner=subprocess.run):
    """Add the menu entry and the icon, and make KanzonasPDF the default PDF app. Returns
    a list of notes for the user (empty when everything went as planned). Raises OSError
    when the files can't be written."""
    cmd = command()
    if not cmd or any("\n" in a or "\r" in a for a in cmd):
        raise OSError(tr("KanzonasPDF couldn't find its own program file."))
    notes = []
    # what this user had chosen to open PDFs (xdg-mime replaces it): back when taken away
    previous = (_previous_default() if is_added() else
                [x for x in _defaults_in_list(mimeapps_path(), MIME_TYPES[0])
                 if x != DESKTOP_ID])
    _write(icon_path(), _icon_png())
    if os.path.exists(desktop_path()) and not is_added():
        # a kanzonaspdf.desktop this user made: put aside (not a .desktop name, so no menu
        # shows it), and back when KanzonasPDF's own is taken away
        os.replace(desktop_path(), desktop_path() + USER_COPY)
    _write(desktop_path(), entry_text(cmd, version, _source_dir(), previous))
    os.chmod(desktop_path(), 0o755)         # (some desktops only trust executable entries)
    apps = os.path.dirname(desktop_path())
    _run(["update-desktop-database", apps], runner)
    # (no icon cache is written: a cache in the user's own icon folder would hide icons
    # other programs add there later)
    if not _run(["xdg-mime", "default", DESKTOP_ID] + list(MIME_TYPES), runner):
        _set_default_in_list(mimeapps_path(), DESKTOP_ID, MIME_TYPES, True)
    if not os.environ.get("APPIMAGE") and not getattr(sys, "frozen", False):
        notes.append(tr("KanzonasPDF is running from its source code: the menu entry runs "
                        "it the same way."))
    return notes


def remove(runner=subprocess.run):
    """Take away what add() wrote: the menu entry (only KanzonasPDF's own), its icon and
    KanzonasPDF as the default PDF app."""
    previous = []
    if os.path.exists(desktop_path()):
        if not is_added():
            return                      # someone else's entry of that name: left alone
        previous = _previous_default()
        os.remove(desktop_path())
        if os.path.exists(desktop_path() + USER_COPY):
            os.replace(desktop_path() + USER_COPY, desktop_path())     # the user's own back
    try:
        os.remove(icon_path())
    except FileNotFoundError:
        pass
    _set_default_in_list(mimeapps_path(), DESKTOP_ID, MIME_TYPES, False, previous)
    apps = os.path.dirname(desktop_path())
    if os.path.isdir(apps):
        _run(["update-desktop-database", apps], runner)


def refresh(version="", runner=subprocess.run):
    """At start-up: when the menu entry KanzonasPDF added runs a program that's gone (the
    AppImage was moved or renamed) and this is an AppImage, point it here. True if it was
    rewritten. Reads one small file; touches nothing otherwise."""
    if not available() or not is_added():
        return False
    appimage = os.environ.get("APPIMAGE") or ""
    if not appimage or not os.path.isfile(appimage):
        return False
    try:
        with open(desktop_path(), encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError:
        return False
    m = re.search(r"^TryExec=(.*)$", text, re.M)
    old = _unvalue(m.group(1)) if m else ""
    if old and os.path.exists(old):
        return False
    try:
        _write(desktop_path(), entry_text([os.path.abspath(appimage)], version,
                                          previous=_previous_default()))
        os.chmod(desktop_path(), 0o755)
    except OSError:
        return False
    _run(["update-desktop-database", os.path.dirname(desktop_path())], runner)
    return True
