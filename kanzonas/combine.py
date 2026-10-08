"""File > Combine files: several PDFs, in an order you choose, into one new PDF."""

import os

import pymupdf
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
                               QPushButton, QCheckBox, QLabel, QDialogButtonBox, QFileDialog,
                               QInputDialog, QLineEdit, QMessageBox, QAbstractItemView)


class _FileList(QListWidget):
    """Reorder by dragging; drop PDFs from Explorer to add them."""

    def __init__(self):
        super().__init__()
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setAcceptDrops(True)

    def add_paths(self, paths):
        for p in paths:
            if p.lower().endswith(".pdf") and os.path.isfile(p):
                it = QListWidgetItem(os.path.basename(p))
                it.setData(Qt.UserRole, p)
                it.setToolTip(p)
                self.addItem(it)

    def paths(self):
        return [self.item(i).data(Qt.UserRole) for i in range(self.count())]

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
        else:
            super().dragEnterEvent(e)

    def dragMoveEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
        else:
            super().dragMoveEvent(e)

    def dropEvent(self, e):
        if e.mimeData().hasUrls():
            self.add_paths([u.toLocalFile() for u in e.mimeData().urls()])
            e.acceptProposedAction()
        else:
            super().dropEvent(e)


class CombineDialog(QDialog):
    def __init__(self, parent, start_dir="", first=None):
        super().__init__(parent)
        self.setWindowTitle("Combine files")
        self.resize(520, 420)
        self.start_dir = start_dir
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("PDFs to combine, top to bottom. Drag to reorder, or drop files "
                             "here from Explorer."))
        row = QHBoxLayout()
        self.list = _FileList()
        if first:
            self.list.add_paths(first)
        row.addWidget(self.list, 1)
        col = QVBoxLayout()
        for text, slot in (("Add files...", self._add), ("Remove", self._remove),
                           ("Move up", lambda: self._move(-1)),
                           ("Move down", lambda: self._move(1)),
                           ("Sort by name", self._sort)):
            b = QPushButton(text)
            b.clicked.connect(slot)
            col.addWidget(b)
        col.addStretch(1)
        row.addLayout(col)
        lay.addLayout(row, 1)
        self.bookmarks = QCheckBox("Add a bookmark for each file (named after the file)")
        self.bookmarks.setChecked(True)
        lay.addWidget(self.bookmarks)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.button(QDialogButtonBox.Ok).setText("Combine...")
        btns.accepted.connect(self._ok)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)
        self.result_path = None

    def _add(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Add PDFs", self.start_dir,
                                                "PDF files (*.pdf)")
        if paths:
            self.start_dir = os.path.dirname(paths[0])
            self.list.add_paths(paths)

    def _remove(self):
        for it in self.list.selectedItems():
            self.list.takeItem(self.list.row(it))

    def _move(self, step):
        r = self.list.currentRow()
        if r < 0 or not 0 <= r + step < self.list.count():
            return
        it = self.list.takeItem(r)
        self.list.insertItem(r + step, it)
        self.list.setCurrentRow(r + step)

    def _sort(self):
        paths = sorted(self.list.paths(), key=lambda p: os.path.basename(p).lower())
        self.list.clear()
        self.list.add_paths(paths)

    def _ok(self):
        paths = self.list.paths()
        if len(paths) < 2:
            QMessageBox.information(self, "Combine files", "Add at least two PDFs.")
            return
        folder = os.path.dirname(paths[0])
        out, _ = QFileDialog.getSaveFileName(self, "Save combined PDF as",
                                             os.path.join(folder, "Combined.pdf"),
                                             "PDF files (*.pdf)")
        if not out:
            return
        if os.path.abspath(out) in {os.path.abspath(p) for p in paths}:
            QMessageBox.warning(self, "Combine files", "Choose a new file name: the combined "
                                "PDF can't replace one of the files being combined.")
            return
        try:
            n = combine(paths, out, self.bookmarks.isChecked(), self._password)
        except Exception as e:
            QMessageBox.warning(self, "Combine files", f"Couldn't combine the files:\n{e}")
            return
        if n is None:
            return
        self.result_path = out
        self.accept()

    def _password(self, path):
        pw, ok = QInputDialog.getText(self, "Password needed",
                                      f"{os.path.basename(path)} is password protected.\n"
                                      "Password (Cancel stops combining):", QLineEdit.Password)
        return pw if ok else None


def _shift(page, start):
    return page + start if page > 0 else -1       # -1: a bookmark with no target page


def combine(paths, out, bookmarks=True, ask_password=None):
    """Write the PDFs in `paths`, in order, to `out`. Returns the page count, or None if a
    password was needed and not given. Each file's own bookmarks are kept, nested under the
    file's bookmark when `bookmarks` is on."""
    result = pymupdf.open()
    toc = []
    for p in paths:
        src = pymupdf.open(p)
        try:
            if src.needs_pass:
                while True:
                    pw = ask_password(p) if ask_password else None
                    if pw is None:
                        return None
                    if src.authenticate(pw):
                        break
            start = result.page_count
            result.insert_pdf(src)
            inner = src.get_toc(simple=True)
            if bookmarks:
                toc.append([1, os.path.splitext(os.path.basename(p))[0], start + 1])
                toc += [[lvl + 1, title, _shift(page, start)] for lvl, title, page in inner]
            else:
                toc += [[lvl, title, _shift(page, start)] for lvl, title, page in inner]
        finally:
            src.close()
    if toc:
        result.set_toc(toc)
    result.save(out, garbage=3, deflate=True)
    n = result.page_count
    result.close()
    return n
