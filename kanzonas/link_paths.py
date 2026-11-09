"""Where a link to another file points.

A link to another file stores a path, and that path is often not right on the computer
opening it: drawing indexes and sheet sets are made on one person's computer and opened on
another (C:\\Users\\<their name>\\OneDrive - ...), folders get moved or synced to another
place, and PDF writers store the path in several ways (C:\\..., /C/..., file:///C:/...,
followed by #nameddest=Sheet1, or with a stray control character at its end).

`split_link` turns what MuPDF hands back into a plain path and a named destination;
`there` says if a file is there (also when Windows can't read a OneDrive file's details);
`find_moved` looks for the linked file from the document's own folder, as the link's last
folders and file name, when the path as written isn't there.
"""
import os
import re
import sys
from urllib.parse import unquote

ANCESTORS = 5       # the document's folder and this many folders above it
TAIL = 8            # the link's last this many folders and its file name
_DRIVE = re.compile(r"^[A-Za-z]:$")
_PDF_DRIVE = re.compile(r"^/([A-Za-z]):?(?=/|$)")       # /C/Users/... or /C:/Users/...
_USERS = re.compile(r"^[A-Za-z]:[\\/]+Users[\\/]+([^\\/]+)", re.IGNORECASE)


def clean(path, windows=None):
    """The path without stray control characters or spaces around it; on Windows, a PDF's
    own way of writing a drive (/C/Users/...) or a file: address's (/C:/Users/...) as C:/..."""
    if windows is None:
        windows = sys.platform == "win32"
    path = "".join(ch for ch in path if ch >= " " and ch != "\x7f").strip()
    if windows:
        path = _PDF_DRIVE.sub(lambda m: m.group(1) + ":", path)
    return path


def split_link(raw, encoded=True, windows=None):
    """(path, named destination or None) from a link's file. MuPDF hands the file name back
    percent-encoded ("%20", and "%23" for a '#' in the name), so there a bare '#' starts what
    to open it at: "#page=3", or "#nameddest=Sheet1" for a link to a named destination."""
    raw = raw or ""
    name = None
    if encoded:
        if "#" in raw:
            raw, frag = raw.split("#", 1)
            m = re.search(r"(?:^|&)nameddest=([^&]*)", frag)
            if m:
                name = unquote(m.group(1)) or None
        raw = unquote(raw)
    return clean(raw, windows), name


def there(path):
    """The file is there. Windows can fail to read the details of a OneDrive file that's
    only online (or while OneDrive isn't running), so its folder's list is asked too."""
    if os.path.exists(path):
        return True
    folder, name = os.path.split(path)
    if not name:
        return False
    try:
        names = os.listdir(folder or ".")
    except (OSError, ValueError):
        return False
    if sys.platform == "win32":
        return name.lower() in (n.lower() for n in names)
    return name in names


def find_moved(path, doc_path, exists=there):
    """The linked file found from the document's folder: the link's file name, or its last
    folders and file name, in the document's folder or in a folder up to ANCESTORS above it
    (above it, only with at least one of the link's folders, never by the file name alone).
    The nearest one wins, then the one that keeps more of the link's folders. None if none."""
    if not path or not doc_path:
        return None
    parts = [p for p in re.split(r"[\\/]+", path)
             if p and p not in (".", "..") and not _DRIVE.match(p)]
    if not parts:
        return None
    parts = parts[-TAIL:]
    folder = os.path.dirname(os.path.abspath(doc_path))
    tried = set()
    for level in range(ANCESTORS + 1):
        for k in range(len(parts), 0, -1):
            if level and k < 2:
                continue
            candidate = os.path.normpath(os.path.join(folder, *parts[-k:]))
            if candidate in tried:
                continue
            tried.add(candidate)
            if exists(candidate) and not os.path.isdir(candidate):
                return candidate
        up = os.path.dirname(folder)
        if up == folder:
            break
        folder = up
    return None


def other_user(path, profile=None):
    """The Windows user whose folder the link points into (C:\\Users\\<name>\\...), when it
    isn't the person's own; None otherwise."""
    m = _USERS.match(path or "")
    if not m:
        return None
    if profile is None:
        profile = os.environ.get("USERPROFILE", "")
    mine = ([p for p in re.split(r"[\\/]+", profile) if p] or [""])[-1]
    name = m.group(1)
    if name.lower() in (mine.lower(), "public", "default"):
        return None
    return name


def named_page(path, name):
    """The page (0-based) a named destination in the PDF at path goes to; -1 if unknown."""
    import pymupdf
    try:
        with pymupdf.open(path) as d:
            if d.needs_pass:
                return -1
            page = (d.resolve_names().get(name) or {}).get("page", -1)
            return int(page) if 0 <= int(page) < d.page_count else -1
    except Exception:       # a damaged or unreadable file: open it at its start
        return -1
