"""Update check: asks GitHub for the newest KanzonasPDF release and tells the user about it.

The check only tells the user. The automatic check runs at most once a day, in the background
(Qt networking), and fails silently when offline or blocked.

Portable copies can also update themselves in place (PortableUpdater): download
KanzonasPDF-portable.zip from the GitHub release, and only if its sha256 matches the digest
published with that release, unpack it next to the program. A small script
waits for KanzonasPDF to close, copies the new files over the old ones (the data folder is left
alone), and starts it again. The path to KanzonasPDF.exe never changes, so file associations
("default PDF app") keep working.
"""

import hashlib
import json
import os
import shutil
import time
import zipfile
from urllib.parse import urlparse

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply

from . import __version__

REPO = "keithlyding/KanzonasPDF"
API = "https://api.github.com/repos/" + REPO + "/releases?per_page=20"
RELEASES_PAGE = "https://github.com/" + REPO + "/releases"
DAY = 24 * 3600
PORTABLE_ZIP = "KanzonasPDF-portable.zip"
STAGING = "_update"          # folder beside the exe that holds the unpacked new version
# browser_download_url hosts a portable update is allowed to use. Anything else is refused.
GITHUB_HOSTS = ("github.com", "objects.githubusercontent.com",
                "release-assets.githubusercontent.com")


def version_tuple(text):
    """'v0.36' -> (0, 36); '1.2.3' -> (1, 2, 3). Non-numeric parts end the version."""
    parts = []
    for p in str(text).strip().lstrip("vV").split("."):
        digits = ""
        for ch in p:
            if not ch.isdigit():
                break
            digits += ch
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts)


def newest(releases, current=None):
    """The newest published release newer than `current`, as (version, page url), or None.
    Pre-releases count: every 0.x release is one."""
    r = newest_release(releases, current)
    return (r["tag_name"].lstrip("vV"), r.get("html_url") or RELEASES_PAGE) if r else None


def newest_release(releases, current=None):
    """Like newest(), but the whole release entry from GitHub (or None)."""
    current = current or __version__
    best = None
    for r in releases:
        if r.get("draft"):
            continue
        v = version_tuple(r.get("tag_name", ""))
        if not v or v <= version_tuple(current):
            continue
        if best is None or v > best[0]:
            best = (v, r)
    return best[1] if best else None


def _sha256_hex(asset):
    """Hex digits from an asset digest of the form sha256:<hex>, or None."""
    digest = (asset or {}).get("digest") or ""
    if not isinstance(digest, str) or not digest.startswith("sha256:"):
        return None
    hexpart = digest[len("sha256:"):]
    if not hexpart or any(c not in "0123456789abcdefABCDEF" for c in hexpart):
        return None
    return hexpart


def asset_url(release, name=PORTABLE_ZIP):
    """Download address of the release file called `name`, or None.

    None unless the host is a GitHub release host and the asset has a sha256 digest.
    """
    for a in (release or {}).get("assets") or []:
        if a.get("name") != name:
            continue
        url = a.get("browser_download_url") or ""
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        if parsed.scheme != "https" or parsed.username or parsed.password:
            return None
        if host not in GITHUB_HOSTS or _sha256_hex(a) is None:
            return None
        return url
    return None


def asset_digest(release, name=PORTABLE_ZIP):
    """Hex sha256 published for the release file called `name`, or None."""
    for a in (release or {}).get("assets") or []:
        if a.get("name") == name:
            return _sha256_hex(a)
    return None


def can_self_update():
    """True for the portable Windows program (the installer handles installed copies)."""
    import sys
    from . import paths
    return os.name == "nt" and getattr(sys, "frozen", False) and paths.is_portable()


def _file_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def unpack(zip_path, app_dir):
    """Unpack a downloaded portable zip into app_dir/_update and return the folder holding the
    new KanzonasPDF.exe. Refuses zips that aren't a KanzonasPDF portable build or that would
    write outside the staging folder."""
    stage = os.path.join(app_dir, STAGING)
    shutil.rmtree(stage, ignore_errors=True)
    os.makedirs(stage)
    root = os.path.realpath(stage)
    with zipfile.ZipFile(zip_path) as z:
        bad = z.testzip()
        if bad:
            raise ValueError("The download is damaged (" + bad + "). Try again.")
        for name in z.namelist():
            target = os.path.realpath(os.path.join(stage, name))
            if target != root and not target.startswith(root + os.sep):
                raise ValueError("The download contains an unsafe file name: " + name)
        z.extractall(stage)
    new = os.path.join(stage, "KanzonasPDF")
    if not os.path.isfile(os.path.join(new, "KanzonasPDF.exe")):
        shutil.rmtree(stage, ignore_errors=True)
        raise ValueError("The download isn't a KanzonasPDF portable version.")
    # a data folder in the zip (there is none today) must never replace the user's settings
    shutil.rmtree(os.path.join(new, "data"), ignore_errors=True)
    return new


def swap_script(pid, new, app_dir):
    """Windows batch file text: wait for process `pid` to end, copy `new` over `app_dir`
    (keeping the data folder), remove the staging folder and start the updated program."""
    exe = os.path.join(app_dir, "KanzonasPDF.exe")
    stage = os.path.join(app_dir, STAGING)
    return "\r\n".join([
        "@echo off",
        ":wait",
        'tasklist /FI "PID eq %d" 2>nul | find "%d" >nul' % (pid, pid),
        "if not errorlevel 1 (timeout /t 1 /nobreak >nul & goto wait)",
        # program files: _internal is mirrored so files the new version dropped go away;
        # the top level is copied without touching data or the staging folder
        'robocopy "%s" "%s" /MIR /R:5 /W:1 /NFL /NDL /NJH /NJS >nul'
        % (os.path.join(new, "_internal"), os.path.join(app_dir, "_internal")),
        "set rc=%errorlevel%",
        'robocopy "%s" "%s" /E /XD "%s" "%s" /R:5 /W:1 /NFL /NDL /NJH /NJS >nul'
        % (new, app_dir, os.path.join(new, "_internal"), os.path.join(new, "data")),
        "if errorlevel 8 set rc=8",
        'rmdir /s /q "%s"' % stage,
        'if %%rc%% GEQ 8 (echo Updating KanzonasPDF failed. Unzip KanzonasPDF-portable.zip over'
        ' "%s" by hand. & pause)' % app_dir,
        'start "" "%s"' % exe,
        '(goto) 2>nul & del "%~f0"',
        ""])


class UpdateChecker(QObject):
    """found(version, url) when a newer release exists; result(text) after a manual check."""
    found = Signal(str, str)
    result = Signal(str)

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.net = None
        self.manual = False
        self.release = None          # GitHub's entry for the newest release found

    def enabled(self):
        return self.settings.value("update_check", "true") != "false"

    def check_if_due(self):
        if not self.enabled():
            return
        try:
            last = float(self.settings.value("update_last", 0) or 0)
        except (TypeError, ValueError):
            last = 0
        if time.time() - last >= DAY:
            self.check(manual=False)

    def check(self, manual=True):
        self.manual = manual
        if self.net is None:
            self.net = QNetworkAccessManager(self)
        req = QNetworkRequest(QUrl(API))
        req.setRawHeader(b"Accept", b"application/vnd.github+json")
        req.setRawHeader(b"User-Agent", ("KanzonasPDF/" + __version__).encode())
        req.setTransferTimeout(15000)
        reply = self.net.get(req)
        reply.finished.connect(lambda: self._done(reply))

    def _done(self, reply):
        reply.deleteLater()
        if reply.error() != QNetworkReply.NoError:
            if self.manual:
                self.result.emit("Couldn't reach GitHub to check for updates ("
                                 + reply.errorString() + ").")
            return
        try:
            data = json.loads(bytes(reply.readAll()).decode("utf-8"))
        except ValueError:
            data = None
        if not isinstance(data, list):
            if self.manual:
                self.result.emit("GitHub sent an unexpected answer. Try again later.")
            return
        self.settings.setValue("update_last", time.time())
        self.release = newest_release(data)
        hit = newest(data)
        if hit is None:
            if self.manual:
                self.result.emit("You have the latest version (" + __version__ + ").")
            return
        if not self.manual and self.settings.value("update_skip", "") == hit[0]:
            return
        self.found.emit(hit[0], hit[1])


class PortableUpdater(QObject):
    """Downloads the portable zip. progress(received, total); ready(folder of new version);
    failed(message)."""
    progress = Signal(int, int)
    ready = Signal(str)
    failed = Signal(str)

    def __init__(self, url, app_dir, parent=None, expected_sha256=None):
        super().__init__(parent)
        self.url, self.app_dir = url, app_dir
        self.expected_sha256 = expected_sha256
        self.net = QNetworkAccessManager(self)
        self.reply = None
        self.file = None

    def _expected_hex(self):
        text = (self.expected_sha256 or "").strip().lower()
        if text.startswith("sha256:"):
            text = text[len("sha256:"):]
        if len(text) != 64 or any(c not in "0123456789abcdef" for c in text):
            return ""
        return text

    def start(self):
        if not self._expected_hex():
            self.failed.emit("The update was not applied: the release has no sha256 digest.")
            return
        self.path = os.path.join(self.app_dir, STAGING + ".zip")
        try:
            self.file = open(self.path, "wb")
        except OSError as e:
            self.failed.emit("Can't write next to KanzonasPDF.exe (" + str(e) + ").")
            return
        req = QNetworkRequest(QUrl(self.url))
        req.setRawHeader(b"User-Agent", ("KanzonasPDF/" + __version__).encode())
        req.setAttribute(QNetworkRequest.RedirectPolicyAttribute,
                         QNetworkRequest.NoLessSafeRedirectPolicy)
        req.setTransferTimeout(60000)
        self.reply = self.net.get(req)
        self.reply.readyRead.connect(lambda: self.file.write(bytes(self.reply.readAll())))
        self.reply.downloadProgress.connect(lambda r, t: self.progress.emit(int(r), int(t)))
        self.reply.finished.connect(self._done)

    def cancel(self):
        if self.reply is not None:
            self.reply.abort()

    def _done(self):
        r = self.reply
        r.deleteLater()
        self.file.write(bytes(r.readAll()))
        self.file.close()
        try:
            if r.error() != QNetworkReply.NoError:
                if r.error() != QNetworkReply.OperationCanceledError:
                    self.failed.emit("The download failed (" + r.errorString() + ").")
                return
            expect = self._expected_hex()
            if not expect or _file_sha256(self.path) != expect:
                self.failed.emit("The download was not applied: its sha256 does not match "
                                 "the release.")
                return
            try:
                self.ready.emit(unpack(self.path, self.app_dir))
            except (ValueError, OSError, zipfile.BadZipFile) as e:
                self.failed.emit(str(e))
        finally:
            try:
                os.remove(self.path)
            except OSError:
                pass
