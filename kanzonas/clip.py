"""The app's clipboard for markups and pages (text and pictures use the Windows clipboard).

When markups or pages are copied, a marker is put on the system clipboard too; Paste uses
our payload only while that marker is still there, so copying text in another program and
pasting here pastes that text, as you'd expect.
"""

import itertools

from PySide6.QtCore import QMimeData
from PySide6.QtGui import QGuiApplication

MIME = "application/x-kanzonaspdf"
_ids = itertools.count(1)
_state = {"kind": None, "payload": None, "id": None}


def _release():
    """Before Qt shuts down, swap our custom clipboard data for plain text: PySide crashes at
    exit while the clipboard still holds a QMimeData created from Python."""
    try:
        cb = QGuiApplication.clipboard()
        md = cb.mimeData()
        if md is not None and md.hasFormat(MIME):
            cb.setText(md.text())
    except Exception:
        pass


def put(kind, payload, text="", image=None):
    """kind: 'markups' (list of models), 'pages' (PDF bytes) or 'capture' (picture of an
    area). image: a QImage also offered to other programs."""
    if not _state.get("hooked"):
        import atexit
        from PySide6.QtCore import QCoreApplication
        app = QCoreApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(_release)
        atexit.register(_release)
        _state["hooked"] = True
    cid = str(next(_ids))
    _state.update(kind=kind, payload=payload, id=cid)
    md = QMimeData()
    md.setData(MIME, f"{kind}:{cid}".encode())
    if text:
        md.setText(text)
    if image is not None:
        md.setImageData(image)
    QGuiApplication.clipboard().setMimeData(md)


def get():
    """(kind, payload) for our own markups/pages on the clipboard, else (None, None)."""
    md = QGuiApplication.clipboard().mimeData()
    if md is None or not md.hasFormat(MIME):
        return None, None
    kind, _sep, cid = bytes(md.data(MIME)).decode().partition(":")
    if cid != _state["id"]:
        return None, None
    return kind, _state["payload"]
