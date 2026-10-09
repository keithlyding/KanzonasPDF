"""Automatic backup copies of documents with unsaved changes.

Every few minutes (Preferences > Saving), each open document with unsaved changes is written
to the backups folder (in the data folder when portable). The copy is deleted as soon as the
document is saved or closed, and when KanzonasPDF exits normally. So copies that are still
there at start-up mean KanzonasPDF or Windows stopped without saving: the user is offered to
open them.

Password-protected documents are never backed up: the copy would be written without the
password.
"""

import json
import os
import time
import uuid

from PySide6.QtCore import QObject, QTimer

from . import paths

INDEX = "index.json"
KEEP_DAYS = 30


def default_folder():
    return paths.data_dir("backups")


def folder():
    """The backups folder: the one chosen in Preferences > Saving, else the default (in the
    data folder when portable). Falls back to the default if the chosen one can't be used."""
    chosen = paths.settings().value("backup_dir", "") or ""
    if chosen:
        try:
            os.makedirs(chosen, exist_ok=True)
            if os.access(chosen, os.W_OK):
                return chosen
        except OSError:
            pass
    return default_folder()


def usable(path):
    """True if backups can be written to path."""
    try:
        os.makedirs(path, exist_ok=True)
        test = os.path.join(path, ".kanzonas-test")
        with open(test, "w") as f:
            f.write("ok")
        os.remove(test)
        return True
    except OSError:
        return False


def _index():
    try:
        with open(os.path.join(folder(), INDEX), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_index(data):
    try:
        with open(os.path.join(folder(), INDEX), "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1)
    except OSError:
        pass


def leftovers():
    """[(backup path, original path, modified time)] left by a run that didn't exit normally;
    copies older than KEEP_DAYS are deleted."""
    idx = _index()
    out = []
    now = time.time()
    for name in sorted(os.listdir(folder())):
        p = os.path.join(folder(), name)
        if not name.lower().endswith(".pdf"):
            continue
        t = os.path.getmtime(p)
        if now - t > KEEP_DAYS * 86400:
            _remove(p)
            continue
        out.append((p, idx.get(name, ""), t))
    return out


def _remove(p):
    try:
        os.remove(p)
    except OSError:
        pass
    idx = _index()
    if idx.pop(os.path.basename(p), None) is not None:
        _save_index(idx)


def set_aside(items):
    """Move offered copies to backups/recovered (so they're offered only once); returns the
    new paths. Recovered copies are also deleted after KEEP_DAYS."""
    dest = os.path.join(folder(), "recovered")
    os.makedirs(dest, exist_ok=True)
    now = time.time()
    for name in os.listdir(dest):
        p = os.path.join(dest, name)
        if now - os.path.getmtime(p) > KEEP_DAYS * 86400:
            try:
                os.remove(p)
            except OSError:
                pass
    out = []
    idx = _index()
    for p, _orig, _t in items:
        q = os.path.join(dest, os.path.basename(p))
        try:
            os.replace(p, q)
            out.append(q)
        except OSError:
            continue
        idx.pop(os.path.basename(p), None)
    _save_index(idx)
    return out


class Autosaver(QObject):
    def __init__(self, win, minutes):
        super().__init__(win)
        self.win = win
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.set_minutes(minutes)

    def set_minutes(self, minutes):
        self.minutes = max(0, int(minutes))
        if self.minutes:
            self.timer.start(self.minutes * 60_000)
        else:
            self.timer.stop()

    def views(self):
        tabs = self.win.tabs
        return [tabs.widget(i) for i in range(tabs.count())]

    def tick(self):
        for v in self.views():
            if not v.dirty:
                self.discard(v)
                continue
            if v._orig_enc is not None or any((v.security or {}).get(k) for k in ("open_pw", "owner_pw")) or getattr(v, "read_only", False):
                self.discard(v)
                continue                # never write a protected document out unprotected
            if getattr(v, "_backup_path", None) and \
                    getattr(v, "_backup_rev", None) == getattr(v, "revision", None):
                continue                # nothing changed since the last backup
            self.backup(v)

    def backup(self, v):
        if v._orig_enc is not None or any((v.security or {}).get(k) for k in ("open_pw", "owner_pw")):
            self.discard(v)
            return
        path = getattr(v, "_backup_path", None)
        if path is None:
            stem = os.path.splitext(os.path.basename(v.path or "Untitled"))[0]
            path = os.path.join(folder(), f"{stem} (unsaved changes {time.strftime('%Y-%m-%d %H%M%S')})-{uuid.uuid4().hex}.pdf")
            v._backup_path = path
        try:
            data = v.doc.tobytes(garbage=1)
            tmp = path + ".part"
            with open(tmp, "wb") as f:
                f.write(data)
            os.replace(tmp, path)
        except Exception:
            return
        v._backup_rev = getattr(v, "revision", None)
        idx = _index()
        idx[os.path.basename(path)] = v.path or ""
        _save_index(idx)

    def discard(self, v):
        path = getattr(v, "_backup_path", None)
        if path:
            _remove(path)
            v._backup_path = None
            v._backup_rev = None

    def discard_all(self):
        for v in self.views():
            self.discard(v)
