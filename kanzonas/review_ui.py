"""The review workflow's menus and dialogs (review.py, xfdf.py): reply, set a status, export
and import comments, summarize them."""

import os

from PySide6.QtWidgets import (QDialog, QVBoxLayout, QFormLayout, QComboBox, QCheckBox,
                               QDialogButtonBox, QMessageBox)

from . import dialogs, review
from .i18n import tr

# (the menus' names: Review > Status, the Markups list, the page's right-click menu)
STATE_ACTIONS = [("Accepted", tr("Accepted")), ("Rejected", tr("Rejected")),
                 ("Cancelled", tr("Cancelled")), ("Completed", tr("Completed")),
                 ("None", tr("No status"))]


def fill_status_menu(menu, view, index, xrefs):
    """Accepted ... No status, then Marked (a tick), for these markups."""
    menu.clear()
    t = view.threads(index)
    state, _ln, marked = t.status(t.root(xrefs[0])) if xrefs else ("", None, False)
    for key, label in STATE_ACTIONS:
        a = menu.addAction(label, lambda k=key: view.set_review_status(index, xrefs, k))
        a.setCheckable(True)
        a.setChecked(state == key or (key == "None" and not state))
    menu.addSeparator()
    a = menu.addAction(tr("Marked"), lambda: view.set_review_status(
        index, xrefs, "Unmarked" if marked else "Marked"))
    a.setCheckable(True)
    a.setChecked(marked)


def add_review_actions(menu, view, index, xrefs):
    """Reply... and Set status for the selected markups, in a right-click menu."""
    if not xrefs:
        return
    menu.addSeparator()
    if len(xrefs) == 1:
        menu.addAction(tr("Reply..."), lambda: view.reply_to(index, xrefs[0]))
    sub = menu.addMenu(tr("Set status"))
    fill_status_menu(sub, view, index, xrefs)


FILTERS = tr("XFDF comments") + " (*.xfdf);;" + tr("FDF comments") + " (*.fdf)"


def export_comments(win, view, only=None):
    """Export the document's markups (or only those in only {page: [xref]}) with their
    replies and statuses to an XFDF or FDF file. Returns the path, or None."""
    from . import xfdf
    base = os.path.splitext(os.path.basename(view.path or "comments"))[0]
    path = dialogs.save_file(win, tr("Export comments"), base + ".xfdf", FILTERS)
    if not path:
        return None
    recs, skipped = xfdf.records(view.doc, only)
    fdf = path.lower().endswith(".fdf")
    if not fdf and not path.lower().endswith(".xfdf"):
        path += ".xfdf"
    name = os.path.basename(view.path or "")
    ids = xfdf.file_ids(view.doc)
    data = xfdf.to_fdf(recs, name, ids) if fdf else xfdf.to_xfdf(recs, name, ids)
    try:
        with open(path, "wb") as f:
            f.write(data)
    except OSError as ex:
        QMessageBox.warning(win, tr("Export comments"), tr(
            "Couldn't save {name}:\n{error}").format(name=os.path.basename(path),
                                                     error=ex.strerror or ex))
        return None
    msg = tr("{n} comments exported to {name}.").format(n=len(recs),
                                                        name=os.path.basename(path))
    if skipped:
        msg += "\n" + tr("Not exported (pictures and attached files stay in the PDF): {n}"
                         ).format(n=sum(skipped.values()))
        QMessageBox.information(win, tr("Export comments"), msg)
    elif hasattr(win, "statusBar"):
        win.statusBar().showMessage(msg, 6000)
    return path


def read_comment_file(path):
    """Records from an XFDF or FDF file (by its contents). Raises ValueError."""
    from . import xfdf
    with open(path, "rb") as f:
        data = f.read(xfdf.MAX_BYTES + 1)       # (a larger one is refused unread)
    if len(data) > xfdf.MAX_BYTES:
        raise ValueError(tr("This comment file is too large to import."))
    if data.lstrip()[:4] == b"%FDF":
        return xfdf.from_fdf(data)
    return xfdf.from_xfdf(data)


def import_comments(win, view):
    """Import an XFDF / FDF file's comments into the document (one undo step)."""
    path = dialogs.open_file(win, tr("Import comments"),
                             tr("Comment files") + " (*.xfdf *.fdf *.xml);;" + FILTERS)
    if not path:
        return None
    try:
        recs = read_comment_file(path)
    except (OSError, ValueError) as ex:
        QMessageBox.warning(win, tr("Import comments"), str(ex))
        return None
    rep = view.import_comments(recs)
    if rep is not None:
        QMessageBox.information(win, tr("Import comments"), rep.text())
    return rep


class SummaryDialog(QDialog):
    """Summarize comments: how to sort, whether to show page thumbnails."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle(tr("Summarize comments"))
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.sort = QComboBox()
        for key, label in (("page", tr("Page")), ("author", tr("Author")),
                           ("date", tr("Date")), ("type", tr("Type"))):
            self.sort.addItem(label, key)
        form.addRow(tr("Sort by:"), self.sort)
        self.thumbs = QCheckBox(tr("Page thumbnails beside their comments (sorted by page)"))
        self.thumbs.setChecked(True)
        form.addRow(self.thumbs)
        lay.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)


def summarize_comments(win, view, ask=True, sort="page", thumbnails=True):
    """Make the comment summary and show it in a new tab, to print or save."""
    if ask:
        dlg = SummaryDialog(win)
        if dlg.exec() != QDialog.Accepted:
            return None
        sort, thumbnails = dlg.sort.currentData(), dlg.thumbs.isChecked()
    doc = review.summarize(view.doc, sort, thumbnails, os.path.basename(view.path or ""))
    v = win._open_untitled(doc)
    win.statusBar().showMessage(tr("Comment summary made: print it (Ctrl+P) or save it "
                                   "(Ctrl+S)"), 8000)
    return v
