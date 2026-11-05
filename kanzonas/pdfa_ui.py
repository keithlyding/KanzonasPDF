"""The windows of PDF/A (pdfa.py): File > Save as PDF/A and File > Check PDF/A."""
import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QApplication, QDialog, QDialogButtonBox, QLabel, QMessageBox,
                               QProgressDialog, QPushButton, QTreeWidget, QTreeWidgetItem,
                               QVBoxLayout)

from . import pdfa
from .i18n import tr

VERAPDF = "https://verapdf.org"


def _about_the_check():
    return tr("It checks the common requirements of PDF/A-2b; for a formal validation, use "
              "veraPDF (free, from the PDF Association: {url}).").format(url=VERAPDF)


class ReportDialog(QDialog):
    """What keeps the document from being PDF/A, by kind, each line with its page (a
    double-click goes there). after_save: the report on the copy just written (notes: what
    was changed), else the check of the open document (with a Save as PDF/A button)."""

    def __init__(self, parent, view, problems, after_save=None):
        super().__init__(parent)
        self.view = view
        self.save_requested = False
        self.setWindowTitle(tr("Save as PDF/A") if after_save else tr("Check PDF/A"))
        self.resize(760, 480)
        labels = pdfa.kind_labels()
        tree = QTreeWidget()
        tree.setHeaderLabels([tr("What"), tr("Page")] +
                             ([] if after_save else [tr("Save as PDF/A")]))
        tree.setColumnWidth(0, 540 if not after_save else 640)
        tree.setColumnWidth(1, 50)
        by_kind = {}
        for p in problems:
            by_kind.setdefault(p.kind, []).append(p)
        for kind in pdfa.KINDS:
            items = by_kind.get(kind)
            if not items:
                continue
            top = QTreeWidgetItem([tr("{what} ({n})").format(what=labels[kind], n=len(items)),
                                   ""])
            tree.addTopLevelItem(top)
            for p in items:
                cols = [p.text, "" if p.page is None else str(p.page + 1)]
                if not after_save:
                    cols.append(tr("Fixes it") if p.fixable else tr("Can't fix it"))
                it = QTreeWidgetItem(cols)
                it.setToolTip(0, p.text)
                it.setData(0, Qt.UserRole, p.page)
                top.addChild(it)
            top.setExpanded(len(items) <= 20)
        tree.itemDoubleClicked.connect(self._go)
        lay = QVBoxLayout(self)
        if after_save:
            path, result = after_save
            head = tr("Saved {path} as PDF/A-{part}b.").format(path=path, part=result["part"])
            changes = result["notes"]
            if changes:
                head += "\n\n" + "\n".join("• " + n for n in changes)
            if problems:
                head += "\n\n" + tr("These could not be fixed, so the copy doesn't fully "
                                    "conform yet. Double-click a line to go to its page.")
            else:
                head += "\n\n" + tr("Nothing left that the check finds.")
        else:
            fixable = sum(1 for p in problems if p.fixable)
            if problems:
                head = tr("{n} things keep this document from being PDF/A; Save as PDF/A fixes "
                          "{fixable} of them. Double-click a line to go to its page.").format(
                    n=len(problems), fixable=fixable)
            else:
                head = tr("Nothing found: the document meets the requirements checked.")
        info = QLabel(head + "\n\n" + _about_the_check())
        info.setWordWrap(True)
        info.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lay.addWidget(info)
        if problems:
            lay.addWidget(tree, 1)
        else:
            tree.hide()
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        if not after_save:
            save = QPushButton(tr("Save as PDF/A..."))
            save.clicked.connect(self._save)
            buttons.addButton(save, QDialogButtonBox.ActionRole)
        lay.addWidget(buttons)
        self.tree = tree

    def _go(self, item, _col):
        i = item.data(0, Qt.UserRole)
        if isinstance(i, int) and self.view is not None:
            self.view.goto_page(i)

    def _save(self):
        self.save_requested = True
        self.accept()


def _progress(parent, text, title):
    progress = QProgressDialog(text, tr("Cancel"), 0, 0, parent)
    progress.setWindowTitle(title)
    progress.setWindowModality(Qt.WindowModal)
    progress.setMinimumDuration(400)

    def step():
        QApplication.processEvents()
        return not progress.wasCanceled()
    return progress, step


def check_pdfa(window, view):
    """File > Check PDF/A: the check of the open document, as it is now (unsaved changes
    included)."""
    view.commit_pending()
    progress, step = _progress(window, tr("Checking for PDF/A..."), tr("Check PDF/A"))
    try:
        problems = pdfa.check(view.doc, step=step)
    finally:
        progress.close()
        progress.deleteLater()
    if problems is None:
        return
    dlg = ReportDialog(window, view, problems)
    dlg.exec()
    if dlg.save_requested:
        save_as_pdfa(window, view)


def is_protected(view):
    """Whether saving view would write an encrypted file (its own protection, or protection
    set in Security properties and not saved yet)."""
    sec = view.security
    if sec is not None:
        return bool(sec.get("open_pw") or sec.get("owner_pw"))
    return view._orig_enc is not None


def save_as_pdfa(window, view):
    """File > Save as PDF/A: writes a PDF/A copy where the user chooses; the tab then shows
    that file, as after Save As (the document's unsaved changes are in the copy). Returns
    True when saved."""
    view.commit_pending()
    if is_protected(view):
        QMessageBox.information(window, tr("Save as PDF/A"), tr(
            "This document is protected with a password, and PDF/A doesn't allow encryption "
            "(an archive must open without one). Remove its security first (Protect > Remove "
            "security), then save it as PDF/A."))
        return False
    from PySide6.QtWidgets import QFileDialog
    from .main_window import PDF_FILTER
    base = os.path.splitext(view.path)[0]
    path, _ = QFileDialog.getSaveFileName(window, tr("Save as PDF/A"), base + "_PDFA.pdf",
                                          PDF_FILTER)
    if not path:
        return False
    path = os.path.abspath(path)
    others = window._writing_over(path, exclude=view)
    if others is None:
        return False
    progress, step = _progress(window, tr("Saving as PDF/A..."), tr("Save as PDF/A"))
    try:
        result = pdfa.convert(view.doc.tobytes(), path, step=step)
    except Exception as ex:
        QMessageBox.critical(window, tr("Save failed"), str(ex))
        return False
    finally:
        progress.close()
        progress.deleteLater()
    if result is None:
        return False
    window._written_over(others, close=True)
    # the tab is that file now (as after Save As): the copy is opened in its place, at the
    # same page
    page = view.current_page()
    i = window.tabs.indexOf(view)
    nv = window._load_view(path)
    if nv is not None and i >= 0:
        nv.initial_state = {"page": page, "zoom": round(view.zoom, 4)}
        window.tabs.insertTab(i + 1, nv, os.path.basename(path))
        window.tabs.setCurrentIndex(i + 1)
        view.dirty = False
        window.close_tab(i)
        window._add_recent(path)
        window.settings.setValue("last_dir", os.path.dirname(path))
    window._update_ui()
    ReportDialog(window, nv, result["remaining"], after_save=(path, result)).exec()
    return True
