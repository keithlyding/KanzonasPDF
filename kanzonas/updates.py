"""Update check: asks GitHub for the newest KanzonasPDF release and tells the user about it.

Notify only: nothing is downloaded or installed. The automatic check runs at most once a day,
in the background (Qt networking), and fails silently when offline or blocked.
"""

import json
import time

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply

from . import __version__

REPO = "keithlyding/KanzonasPDF"
API = "https://api.github.com/repos/" + REPO + "/releases?per_page=20"
RELEASES_PAGE = "https://github.com/" + REPO + "/releases"
DAY = 24 * 3600


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
    current = current or __version__
    best = None
    for r in releases:
        if r.get("draft"):
            continue
        v = version_tuple(r.get("tag_name", ""))
        if not v or v <= version_tuple(current):
            continue
        if best is None or v > best[0]:
            best = (v, r.get("tag_name", "").lstrip("vV"), r.get("html_url") or RELEASES_PAGE)
    return (best[1], best[2]) if best else None


class UpdateChecker(QObject):
    """found(version, url) when a newer release exists; result(text) after a manual check."""
    found = Signal(str, str)
    result = Signal(str)

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.net = None
        self.manual = False

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
        hit = newest(data)
        if hit is None:
            if self.manual:
                self.result.emit("You have the latest version (" + __version__ + ").")
            return
        if not self.manual and self.settings.value("update_skip", "") == hit[0]:
            return
        self.found.emit(hit[0], hit[1])
