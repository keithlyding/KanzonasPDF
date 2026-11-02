"""Update check: asks GitHub for the newest KanzonasPDF release and tells the user about it.

The check only tells the user. The automatic check runs at most once a day, in the background
(Qt networking), also while KanzonasPDF stays open for days, and fails silently when offline or
blocked. The box that tells about a new version shows the short notes (RELEASE_NOTES.md, carried
in each release's text) of every version newer than the one running.

Portable copies can also update themselves in place (PortableUpdater): download
KanzonasPDF-portable.zip from the GitHub release, and only if its sha256 matches the digest
published with that release, unpack it next to the program. A small script
waits for KanzonasPDF to close, copies the new files over the old ones (the data folder is left
alone), and starts it again. The path to KanzonasPDF.exe never changes, so file associations
("default PDF app") keep working.

Installed copies update in place too (InstallerUpdater): download the release's setup, check
its sha256 the same way, close KanzonasPDF (saving first), and run the setup quietly over the
installation; it starts KanzonasPDF again when it's done.

On Linux, the AppImage updates itself (AppImageUpdater): the release's
KanzonasPDF-x86_64.AppImage is downloaded next to the running one ($APPIMAGE), checked the
same way, and once KanzonasPDF has closed (saving first) it takes the old file's place in one
step (a rename on the same disk) and is started again. Run from source, Linux only tells.
"""

import hashlib
import json
import math
import os
import re
import shutil
import time
import zipfile
from urllib.parse import urlparse

from PySide6.QtCore import QCoreApplication, QObject, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply

from . import __version__
from .i18n import tr

REPO = "keithlyding/KanzonasPDF"
API = "https://api.github.com/repos/" + REPO + "/releases?per_page=20"
RELEASES_PAGE = "https://github.com/" + REPO + "/releases"
DAY = 24 * 3600
PORTABLE_ZIP = "KanzonasPDF-portable.zip"
APPIMAGE = "KanzonasPDF-x86_64.AppImage"    # the Linux release file (its name never changes)
APPIMAGE_MAX_BYTES = 1500 * 1000 * 1000     # a download past this stops (the build allows 400 MB)
STAGING = "_update"          # folder beside the exe that holds the unpacked new version
# browser_download_url hosts a portable update is allowed to use. Anything else is refused.
GITHUB_HOSTS = ("github.com", "objects.githubusercontent.com",
                "release-assets.githubusercontent.com")


def version_tuple(text):
    """'v0.36' -> (0, 36); '1.2.3' -> (1, 2, 3). Non-numeric parts end the version (and so
    does a part too long to be one: a tag is anyone's text)."""
    parts = []
    for p in str(text).strip().lstrip("vV").split("."):
        digits = ""
        for ch in p:
            if not ch.isdigit():
                break
            digits += ch
        if not digits or len(digits) > 9:
            break
        parts.append(int(digits))
    return tuple(parts)


def _order(v):
    """A version_tuple to compare: trailing zeros don't count (1.5.0 is 1.5)."""
    v = list(v)
    while v and v[-1] == 0:
        v.pop()
    return tuple(v)


def _page(release):
    """The release's GitHub page (the releases page if it has none we can use)."""
    url = release.get("html_url")
    return url if isinstance(url, str) and url else RELEASES_PAGE


def newest(releases, current=None):
    """The newest published release newer than `current`, as (version, page url), or None.
    Pre-releases count: every 0.x release is one."""
    r = newest_release(releases, current)
    return (str(r["tag_name"]).lstrip("vV"), _page(r)) if r else None


# (a part's text never runs into the next part, also when its closing mark is missing)
_OPEN = "<!-- kanzonas-notes"
_CLOSE = "<!-- /kanzonas-notes -->"
_LANG = re.compile(r"(?: lang=(\w+))? -->")


def _notes_blocks(body):
    """{language: notes} from a release's text. Plain string searching (a release text is
    anyone's: no pattern that slows down on odd input)."""
    found = {}
    at = body.find(_OPEN)
    while at >= 0:
        m = _LANG.match(body, at + len(_OPEN))
        if m is None:
            at = body.find(_OPEN, at + 1)
            continue
        start = m.end()
        nxt = body.find(_OPEN, start)
        close = body.find(_CLOSE, start)
        end = min(x for x in (nxt, close, len(body)) if x >= 0)
        found.setdefault(m.group(1) or "en", body[start:end].strip())
        at = nxt
    return found


def release_notes(release, lang="en"):
    """The short notes in a release's text (see tools/release_notes.py): in lang if it has
    them, else in English; None for a release without notes (those before 1.5)."""
    body = (release or {}).get("body") if isinstance(release, dict) else None
    found = _notes_blocks(body if isinstance(body, str) else "")
    return found.get(lang) or found.get("en")


def notes_since(releases, current=None, lang="en"):
    """[(version, notes or None, page url)] for every published release newer than current,
    newest first: what changed since the version the user has."""
    current = _order(version_tuple(current or __version__))
    out = []
    for r in releases or []:
        if not isinstance(r, dict):
            continue
        v = _order(version_tuple(r.get("tag_name", "")))
        if r.get("draft") or not v or v <= current:
            continue
        out.append((v, r))
    out.sort(key=lambda x: x[0], reverse=True)
    return [(str(r["tag_name"]).lstrip("vV"), release_notes(r, lang), _page(r))
            for _v, r in out]


def newest_release(releases, current=None):
    """Like newest(), but the whole release entry from GitHub (or None)."""
    current = current or __version__
    best = None
    for r in releases:
        if not isinstance(r, dict) or r.get("draft"):
            continue
        v = _order(version_tuple(r.get("tag_name", "")))
        if not v or v <= _order(version_tuple(current)):
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
    if len(hexpart) != 64 or any(c not in "0123456789abcdefABCDEF" for c in hexpart):
        return None                     # (a sha256 is 64 hex digits; anything else isn't one)
    return hexpart


def asset_url(release, name=PORTABLE_ZIP):
    """Download address of the release file called `name`, or None.

    None unless the host is a GitHub release host and the asset has a sha256 digest.
    """
    for a in (release or {}).get("assets") or []:
        if not isinstance(a, dict) or a.get("name") != name:
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
        if isinstance(a, dict) and a.get("name") == name:
            return _sha256_hex(a)
    return None


def can_self_update():
    """True for the portable Windows program (the installer handles installed copies)."""
    import sys
    from . import paths
    return (os.name == "nt" and getattr(sys, "frozen", False) and paths.is_portable()
            and not paths.platform_updates())


def running_appimage():
    """The AppImage file KanzonasPDF runs from on Linux ($APPIMAGE, set by the AppImage's
    own start-up), or None (Windows, or run from source)."""
    import sys
    if not sys.platform.startswith("linux"):
        return None
    path = os.environ.get("APPIMAGE") or ""
    # (the file itself, not a link to it: the update is renamed over what it names, and a
    # link replaced by the new file would leave the real one old)
    return os.path.realpath(path) if path and os.path.isfile(path) else None


def can_update_appimage():
    """True when this is the Linux AppImage: Update now replaces it with the new one."""
    return running_appimage() is not None


def appimage_unwritable(path):
    """Why the AppImage at path can't be replaced by this user (text to show), or None when
    it can: the new file is written next to it and renamed over it, so its folder must
    take new files."""
    folder = os.path.dirname(os.path.abspath(path))
    if not os.access(folder, os.W_OK | os.X_OK):
        return tr("You don't have permission to change the folder it is in ({folder}).") \
            .format(folder=folder)
    try:
        st = os.stat(folder)
        import stat as _stat
        if st.st_mode & _stat.S_ISVTX and os.stat(path).st_uid != os.getuid() \
                and st.st_uid != os.getuid():
            # (a shared folder like /tmp: only a file's owner may replace it)
            return tr("It belongs to another user.")
    except OSError as e:
        return str(e)
    return None


def is_appimage_file(path):
    """The file at path is a Linux program packed as an AppImage (type 2: an ELF program
    with AI 2 in its header)."""
    try:
        with open(path, "rb") as f:
            head = f.read(11)
    except OSError:
        return False
    return head[:4] == b"\x7fELF" and head[8:11] == b"AI\x02"


def replace_appimage(new, target):
    """Put the checked new AppImage at target in one step: executable like the old one (and
    by its owner in any case; never changeable by other users, even if the old one was),
    then renamed over it. The running program keeps its own copy open until it ends."""
    try:
        mode = os.stat(target).st_mode & 0o777
    except OSError:
        mode = 0o755
    os.chmod(new, (mode | 0o100) & ~0o022)
    os.replace(new, target)


def restart_env(env=None):
    """The environment to start the new AppImage with: without what this AppImage's start-up
    set for itself (its folder, which goes away when it ends, and the library path
    PyInstaller changed; its earlier value comes back from the LD_LIBRARY_PATH_ORIG copy)."""
    env = dict(os.environ if env is None else env)
    mount = env.get("APPDIR") or ""
    if os.path.basename(mount.rstrip("/")).startswith("appimage_extracted_"):
        # started with --appimage-extract-and-run (no FUSE on this computer): the new one
        # must be started the same way, or it can't start at all
        env["APPIMAGE_EXTRACT_AND_RUN"] = "1"
    # (and the permission to come to the front this start was given: used up already)
    for key in ("APPIMAGE", "APPDIR", "ARGV0", "OWD", "DESKTOP_STARTUP_ID",
                "XDG_ACTIVATION_TOKEN"):
        env.pop(key, None)
    for key in ("LD_LIBRARY_PATH", "LD_PRELOAD"):
        if key + "_ORIG" in env:            # (PyInstaller keeps the value it replaced)
            env[key] = env.pop(key + "_ORIG")
    if mount:
        mount = mount.rstrip("/")
        for key, value in list(env.items()):
            parts = value.split(os.pathsep)
            kept = [p for p in parts if not (p == mount or p.startswith(mount + "/"))]
            if kept != parts:
                if any(kept):
                    env[key] = os.pathsep.join(kept)
                else:
                    del env[key]
    return env


def setup_name(version):
    """The release's installer for version: KanzonasPDF-v1.6-setup.exe."""
    return "KanzonasPDF-v%s-setup.exe" % version


def can_install_update(app_dir=None):
    """True for a copy installed with KanzonasPDF's setup on Windows (its uninstaller sits
    beside the program): Update now downloads the new setup and runs it over this one."""
    import sys
    from . import paths
    if os.name != "nt" or not getattr(sys, "frozen", False) or paths.is_portable():
        return False
    return os.path.exists(os.path.join(app_dir or paths.app_dir(), "unins000.exe"))


# the setup's AppId (installer/KanzonasPDF.iss): its uninstall entry says who it was installed for
UNINSTALL_KEY = (r"Software\Microsoft\Windows\CurrentVersion\Uninstall"
                 r"\{8F4C2A61-5B7E-4D3A-9C1F-2E6B7A9D4C11}_is1")


def _installed_in(hive, app_dir):
    """The setup's uninstall entry under hive (winreg.HKEY_LOCAL_MACHINE / _CURRENT_USER)
    names app_dir as where it installed. None when it can't be read (not Windows, no entry)."""
    try:
        import winreg
    except ImportError:
        return None
    here = os.path.normcase(os.path.abspath(app_dir)).rstrip("\\/")
    found = None
    for view in (getattr(winreg, "KEY_WOW64_64KEY", 0), getattr(winreg, "KEY_WOW64_32KEY", 0)):
        try:
            with winreg.OpenKey(hive, UNINSTALL_KEY, 0, winreg.KEY_READ | view) as k:
                where = winreg.QueryValueEx(k, "InstallLocation")[0]
        except OSError:
            continue
        found = False
        if not str(where or "").strip():
            continue                    # (an empty entry names no folder)
        if os.path.normcase(os.path.abspath(str(where))).rstrip("\\/") == here:
            return True
    return found


def for_all_users(app_dir):
    """The copy in app_dir was installed for all users, so its update needs Windows'
    administrator prompt (and the setup's /ALLUSERS, or it would install a second copy for
    this user). The setup's own uninstall entry says so (also for a custom folder); without
    it, a folder under Program Files does."""
    try:
        import winreg
        mine = _installed_in(winreg.HKEY_CURRENT_USER, app_dir)
        everyone = _installed_in(winreg.HKEY_LOCAL_MACHINE, app_dir)
    except ImportError:
        mine = everyone = None
    if everyone:
        return True
    if mine:
        return False
    here = os.path.normcase(os.path.abspath(app_dir))
    for var in ("ProgramFiles", "ProgramW6432", "ProgramFiles(x86)"):
        base = os.environ.get(var)
        if base and here.startswith(os.path.normcase(os.path.abspath(base)) + os.sep):
            return True
    return False


def installer_command(setup_path, app_dir):
    """How Update now runs the new setup: quietly (a progress window only, no questions),
    over the existing installation with its options kept, closing anything still using the
    files, and starting KanzonasPDF again when done (/RELAUNCH, see installer/KanzonasPDF.iss;
    the Windows build tests this command line)."""
    return [setup_path, "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-",
            "/CLOSEAPPLICATIONS", "/ALLUSERS" if for_all_users(app_dir) else "/CURRENTUSER",
            "/RELAUNCH"]


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
            raise ValueError(tr("The download is damaged ({name}). Try again.").format(name=bad))
        for name in z.namelist():
            target = os.path.realpath(os.path.join(stage, name))
            if target != root and not target.startswith(root + os.sep):
                raise ValueError(tr("The download contains an unsafe file name: {name}").format(
                    name=name))
        z.extractall(stage)
    new = os.path.join(stage, "KanzonasPDF")
    if not os.path.isfile(os.path.join(new, "KanzonasPDF.exe")):
        shutil.rmtree(stage, ignore_errors=True)
        raise ValueError(tr("The download isn't a KanzonasPDF portable version."))
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
    checked = Signal(str)            # an automatic check found nothing newer (a quiet note)

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.net = None
        self.manual = False
        self.release = None          # GitHub's entry for the newest release found
        self.releases = []           # every release GitHub listed (for the notes since yours)

    def enabled(self):
        from . import paths
        # the PortableApps.com platform checks for updates itself: off unless switched on
        default = "false" if paths.platform_updates() else "true"
        return self.settings.value("update_check", default) != "false"

    def check_if_due(self):
        if not self.enabled():
            return
        try:
            last = float(self.settings.value("update_last", 0) or 0)
        except (TypeError, ValueError):
            last = 0
        now = time.time()
        if not math.isfinite(last) or last > now or now - last >= DAY:
            # (a time in the future: the clock was changed; check rather than wait)
            self.check(manual=False)

    _reply = None                    # the request on its way, and whether it was asked for
    _reply_manual = False

    def check(self, manual=True):
        busy = self._reply is not None and self._reply.isRunning()
        if busy and not manual:
            return                      # (a check is already on its way)
        if busy and self._reply_manual:
            return
        if busy:                        # asked for while the automatic one runs: this one
            old, self._reply = self._reply, None
            old.abort()
        if self.net is None:
            self.net = QNetworkAccessManager(self)
        req = QNetworkRequest(QUrl(API))
        req.setRawHeader(b"Accept", b"application/vnd.github+json")
        req.setRawHeader(b"User-Agent", ("KanzonasPDF/" + __version__).encode())
        req.setTransferTimeout(15000)
        reply = self.net.get(req)
        self._reply, self._reply_manual = reply, manual
        reply.finished.connect(lambda: self._done(reply, manual))

    def _done(self, reply, manual=None):
        reply.deleteLater()
        if self._reply is reply:
            self._reply = None
        if manual is None:
            manual = self.manual
        self.manual = manual            # (the window asks: answer in a box or in the notice)
        if reply.error() == QNetworkReply.OperationCanceledError and not manual:
            return
        if reply.error() != QNetworkReply.NoError:
            if manual:
                self.result.emit(tr("Couldn't reach GitHub to check for updates ({error}).")
                                 .format(error=reply.errorString()))
            return
        try:
            data = json.loads(bytes(reply.readAll()).decode("utf-8"))
        except (ValueError, RecursionError):
            data = None
        if not isinstance(data, list):
            if manual:
                self.result.emit(tr("GitHub sent an unexpected answer. Try again later."))
            return
        self.settings.setValue("update_last", time.time())
        self.releases = data
        self.release = newest_release(data)
        hit = newest(data)
        if hit is None:
            text = tr("You have the latest version ({version}).").format(version=__version__)
            (self.result if manual else self.checked).emit(text)
            return
        if not manual and self.settings.value("update_skip", "") == hit[0]:
            return
        self.found.emit(hit[0], hit[1])


_RUNNING = []                           # the downloads on their way (one at a time)


def downloading():
    """An update is being downloaded (Update now waits for it rather than start another)."""
    return any(not st["done"] for st in _RUNNING)


def _abandon(st):
    """The download's window went away or KanzonasPDF quit before it finished: nothing of it
    stays behind (its file, and the setup's own folder)."""
    if st["done"]:
        return
    st["done"] = True
    if st in _RUNNING:
        _RUNNING.remove(st)
    try:
        if st["file"] is not None:
            st["file"].close()
    except OSError:
        pass
    for path in st["paths"]:
        try:
            os.remove(path)
        except OSError:
            pass
    for folder in st["folders"]:
        shutil.rmtree(folder, ignore_errors=True)


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
            self.failed.emit(tr("The update was not applied: the release has no sha256 digest."))
            return
        self.path = self._target()
        try:
            self.file = self._open()
        except OSError as e:
            self.failed.emit(self._write_error(e))
            return
        st = self._state = {"done": False, "file": self.file, "paths": [self.path],
                            "folders": self._folders()}
        _RUNNING.append(st)
        # (not methods of self: they run while self is being destroyed)
        self.destroyed.connect(lambda *_: _abandon(st))
        app = QCoreApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(lambda: _abandon(st))
        req = QNetworkRequest(QUrl(self.url))
        req.setRawHeader(b"User-Agent", ("KanzonasPDF/" + __version__).encode())
        req.setAttribute(QNetworkRequest.RedirectPolicyAttribute,
                         QNetworkRequest.NoLessSafeRedirectPolicy)
        req.setTransferTimeout(60000)
        self.reply = self.net.get(req)
        self.reply.readyRead.connect(lambda: self._write(bytes(self.reply.readAll())))
        self.reply.downloadProgress.connect(lambda r, t: self.progress.emit(int(r), int(t)))
        self.reply.finished.connect(self._done)

    def cancel(self):
        if self.reply is not None:
            self.reply.abort()

    def _done(self):
        st = getattr(self, "_state", None)
        if st is not None:
            if st["done"]:
                return                  # (already cleared away)
            st["done"] = True
            if st in _RUNNING:
                _RUNNING.remove(st)
        r = self.reply
        r.deleteLater()
        self._write(bytes(r.readAll()))
        self._close_file()
        try:
            problem = self._write_problem()
            if problem:
                self.failed.emit(problem)
                return
            if r.error() != QNetworkReply.NoError:
                if r.error() != QNetworkReply.OperationCanceledError:
                    self.failed.emit(tr("The download failed ({error}).").format(
                        error=r.errorString()))
                return
            expect = self._expected_hex()
            if not expect or _file_sha256(self.path) != expect:
                self.failed.emit(tr("The download was not applied: its sha256 does not "
                                    "match the release."))
                return
            try:
                self.ready.emit(self._finish())
            except (ValueError, OSError, zipfile.BadZipFile) as e:
                self.failed.emit(str(e))
        finally:
            self._cleanup()

    # (what InstallerUpdater and AppImageUpdater do differently)
    def _write(self, data):
        self.file.write(data)

    def _close_file(self):
        self.file.close()

    def _write_problem(self):
        return None

    def _write_error(self, e):
        return tr("Can't write next to KanzonasPDF.exe ({error}).").format(error=e)

    def _target(self):
        return os.path.join(self.app_dir, STAGING + ".zip")

    def _open(self):
        return open(self.path, "wb")

    def _finish(self):
        return unpack(self.path, self.app_dir)

    def _folders(self):
        return []

    def _cleanup(self):
        try:
            os.remove(self.path)
        except OSError:
            pass


class InstallerUpdater(PortableUpdater):
    """Downloads the new setup for an installed copy into a fresh folder only this user can
    write to, and checks its sha256 against the release. ready(path of the setup)."""

    def __init__(self, url, version, parent=None, expected_sha256=None):
        super().__init__(url, "", parent, expected_sha256)
        self.version = version

    def _target(self):
        import tempfile
        return os.path.join(tempfile.mkdtemp(prefix="kzsetup"), setup_name(self.version))

    def _folders(self):
        return [os.path.dirname(self.path)]

    def _finish(self):
        self._good = True               # checked: keep it for running
        return self.path

    def _cleanup(self):
        if not getattr(self, "_good", False):
            super()._cleanup()          # a failed or wrong download goes, with its folder
            shutil.rmtree(os.path.dirname(self.path), ignore_errors=True)


class AppImageUpdater(PortableUpdater):
    """Downloads the new AppImage next to the running one (same disk: the rename that puts it
    in place is a single step), and checks its sha256 against the release and that it is an
    AppImage. ready(path of the checked download); the caller closes KanzonasPDF and calls
    replace_appimage. A wrong or failed download is removed, and so is one that grows past
    APPIMAGE_MAX_BYTES (it would fill the disk)."""

    def __init__(self, url, appimage, parent=None, expected_sha256=None):
        super().__init__(url, os.path.dirname(os.path.abspath(appimage)), parent,
                         expected_sha256)
        self.appimage = os.path.abspath(appimage)
        self._too_big = False

    def _write_error(self, e):
        return tr("Can't write next to {name} ({error}).").format(
            name=os.path.basename(self.appimage), error=e)

    _failed_write = None                # the error writing the download met (disk full...)

    def _write(self, data):
        if self._failed_write is not None:
            return
        try:
            self.file.write(data)
        except OSError as e:
            # (the disk filled up, or the folder went away): stop downloading; _done says
            # so and removes what was written
            self._failed_write = e
            if self.reply is not None and self.reply.isRunning():
                self.reply.abort()

    def _close_file(self):
        try:
            self.file.close()
        except OSError as e:
            if self._failed_write is None:
                self._failed_write = e

    def _write_problem(self):
        if self._failed_write is None:
            return None
        return self._write_error(self._failed_write)

    def _target(self):
        return None                     # (named when it's made: see _open)

    def _open(self):
        # a new file only this user can read or change, under a name nobody can guess and
        # never through a link: the folder may be shared (/tmp, a team folder), and whoever
        # else can add files there could otherwise prepare the name (a link to another of
        # the user's files, or a file of theirs they change after it's checked)
        import tempfile
        fd, self.path = tempfile.mkstemp(
            prefix=".%s.update-" % os.path.basename(self.appimage), dir=self.app_dir)
        return os.fdopen(fd, "wb")

    def start(self):
        super().start()
        if self.reply is not None:
            self.reply.downloadProgress.connect(self._limit)

    def _limit(self, received, total):
        if not self._too_big and max(received, total) > APPIMAGE_MAX_BYTES:
            self._too_big = True
            self.reply.abort()

    def _done(self):
        st = getattr(self, "_state", None)
        if not self._too_big or (st is not None and st["done"]):
            super()._done()             # (or already cleared away: KanzonasPDF is quitting)
            return
        # stopped for its size (or it had all come already): never checked, never kept
        blocked = self.blockSignals(True)
        try:
            super()._done()
        finally:
            self.blockSignals(blocked)
        self._good = False
        PortableUpdater._cleanup(self)
        self.failed.emit(tr("The download was stopped: it is far bigger than an "
                            "AppImage of KanzonasPDF."))

    def _finish(self):
        if not is_appimage_file(self.path):
            raise ValueError(tr("The download isn't a KanzonasPDF AppImage."))
        self._good = True               # checked: kept for putting in place
        return self.path

    def _cleanup(self):
        if not getattr(self, "_good", False):
            super()._cleanup()
