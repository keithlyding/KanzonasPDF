"""Sets (1.12, the owner, 11 Nov, from the Bluebeam comparison: Revu's Sets): several PDFs
browsed as one, without merging them: a drawing set kept as one file per sheet, a project's
specs and drawings. A set is a small file of its own (.kzset, JSON) listing the PDFs, by
paths relative to it when they're in its folder or below (the set and its files can move
together), else in full.

The Sets panel (sets_panel.py) lists every page of every file, by its sheet number and title
when its title block gives them (sheets.sheet_info), opens the file at the page clicked, and
goes on to the next file at the end of one (Next sheet, Previous sheet). Combine to one PDF
makes a single PDF of them (Combine files). The PDFs themselves stay as they are: markups are
saved in each file.

No Qt here."""

import json
import os

import pymupdf

SUFFIX = ".kzset"
# a page this long on a side (11x17 and up) is a drawing sheet: its title block is read (on
# letter and A4 pages, text, the largest "A1" would be taken for a sheet number)
DRAWING_PT = 1000
KIND = "KanzonasPDF set"


class SetError(Exception):
    pass


class DocSet:
    def __init__(self, name="", files=None, path=None):
        self.name = name
        self.files = [os.path.abspath(f) for f in (files or [])]
        self.path = path            # the .kzset file (None: not saved yet)
        self.dirty = False

    # ---- the set file
    @classmethod
    def load(cls, path):
        path = os.path.abspath(path)
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError) as ex:
            raise SetError(str(ex)) from ex
        if not isinstance(data, dict) or data.get("kind") != KIND or \
                not isinstance(data.get("files"), list):
            raise SetError("not a KanzonasPDF set")
        base = os.path.dirname(path)
        files = []
        for entry in data["files"]:
            p = entry.get("path") if isinstance(entry, dict) else entry
            if isinstance(p, str) and p.strip():
                p = p.replace("\\", os.sep).replace("/", os.sep)
                files.append(os.path.normpath(os.path.join(base, p)))
        name = data.get("name") if isinstance(data.get("name"), str) else ""
        return cls(name or os.path.splitext(os.path.basename(path))[0], files, path)

    def save(self, path=None):
        path = os.path.abspath(path or self.path)
        base = os.path.dirname(path)
        out = []
        for f in self.files:
            rel = os.path.relpath(f, base) if _same_drive(f, base) else None
            # (relative when it's in the set's folder or below; "/" on every system)
            p = rel.replace(os.sep, "/") if rel and not rel.startswith("..") else f
            out.append({"path": p})
        data = {"kind": KIND, "version": 1, "name": self.name, "files": out}
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1, ensure_ascii=False)
        os.replace(tmp, path)
        self.path = path
        self.dirty = False

    # ---- the files
    def add(self, paths):
        """Add PDFs not in the set yet (in the order given). Returns how many."""
        have = {os.path.normcase(f) for f in self.files}
        n = 0
        for p in paths:
            p = os.path.abspath(p)
            if os.path.normcase(p) not in have:
                self.files.append(p)
                have.add(os.path.normcase(p))
                n += 1
        self.dirty = self.dirty or bool(n)
        return n

    def remove(self, path):
        key = os.path.normcase(os.path.abspath(path))
        before = len(self.files)
        self.files = [f for f in self.files if os.path.normcase(f) != key]
        self.dirty = self.dirty or len(self.files) != before

    def move(self, path, step):
        """Move a file up (step -1) or down (+1) in the set."""
        key = os.path.normcase(os.path.abspath(path))
        i = next((k for k, f in enumerate(self.files) if os.path.normcase(f) == key), None)
        j = None if i is None else i + step
        if i is None or not 0 <= j < len(self.files):
            return False
        self.files[i], self.files[j] = self.files[j], self.files[i]
        self.dirty = True
        return True

    def index_of(self, path):
        if not path:
            return None
        key = os.path.normcase(os.path.abspath(path))
        return next((k for k, f in enumerate(self.files) if os.path.normcase(f) == key), None)

    def step(self, path, page, by, count=None):
        """The sheet by pages on (1 next, -1 previous) from page of path, across the set's
        files: (file, page) or None at either end. count(file) -> its page count (None: it
        can't be read: skipped)."""
        count = count or page_count
        k = self.index_of(path)
        if k is None:
            return None
        n = count(self.files[k])
        page += by
        while True:
            if n is not None and 0 <= page < n:
                return self.files[k], page
            k += 1 if by > 0 else -1
            if not 0 <= k < len(self.files):
                return None
            n = count(self.files[k])
            page = 0 if by > 0 else (n - 1 if n else 0)


def _same_drive(a, b):
    return os.path.splitdrive(a)[0].lower() == os.path.splitdrive(b)[0].lower()


# ---- what's read of each file (kept while the file is unchanged on disk) -----------------
_info = {}          # path -> (stamp, {"pages": n, "labels": [...], "sheets": {page: info}})


def _stamp(path):
    try:
        st = os.stat(path)
    except OSError:
        return None
    return st.st_mtime_ns, st.st_size


def file_info(path):
    """{"pages": n, "labels": [page label or ""], "big": {drawing-size pages},
    "sheets": {page: sheet read}} of the PDF, or None when
    it's missing or can't be opened (protected by a password, damaged beyond repair)."""
    stamp = _stamp(path)
    if stamp is None:
        return None
    got = _info.get(path)
    if got is not None and got[0] == stamp:
        return got[1]
    try:
        with pymupdf.open(path) as d:
            if d.needs_pass:
                return None
            labels, big = [], set()
            for i in range(d.page_count):
                try:
                    page = d[i]
                    labels.append(page.get_label() or "")
                    if max(page.rect.width, page.rect.height) >= DRAWING_PT:
                        big.add(i)
                except Exception:
                    labels.append("")
            info = {"pages": d.page_count, "labels": labels, "sheets": {}, "big": big}
    except Exception:
        return None
    _info[path] = (stamp, info)
    return info


def page_count(path):
    info = file_info(path)
    return info["pages"] if info else None


def sheet(path, page):
    """{"number", "title"} the page's title block gives (sheets.sheet_info), None when it
    gives none, or False when it hasn't been read yet (read_sheets)."""
    got = _info.get(path)
    if got is None:
        return False
    return got[1]["sheets"].get(page, False)


def read_sheets(path, pages):
    """Read the title blocks of these pages of the PDF (the file opened once); each page is
    read once while the file is unchanged."""
    info = file_info(path)
    if info is None:
        return
    todo = [i for i in pages if 0 <= i < info["pages"] and i not in info["sheets"]]
    if not todo:
        return
    from . import sheets
    try:
        d = pymupdf.open(path)
    except Exception:
        for i in todo:
            info["sheets"][i] = None
        return
    with d:
        for i in todo:
            try:
                got = sheets.sheet_info(d[i])
            except Exception:
                got = None
            info["sheets"][i] = {"number": got["number"], "title": got.get("title") or ""} \
                if got else None


def forget(path=None):
    """Read the file (every file: None) again next time."""
    if path is None:
        _info.clear()
    else:
        _info.pop(path, None)
