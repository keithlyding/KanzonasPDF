"""File > Combine files: several PDFs and pictures, in an order you choose, into one new PDF.
File > Create PDF from images uses the same window for pictures (scans, phone photos)."""

import os

import pymupdf
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
                               QPushButton, QCheckBox, QLabel, QDialogButtonBox, QFileDialog,
                               QInputDialog, QLineEdit, QMessageBox, QAbstractItemView)


IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".gif", ".webp")
IMAGE_FILTER = "Pictures (*.jpg *.jpeg *.png *.tif *.tiff *.bmp *.gif *.webp)"
LETTER = pymupdf.paper_rect("letter")


def is_image(path):
    return os.path.splitext(path)[1].lower() in IMAGE_EXTS


def _image_pdf(path):
    """The picture (every page of a multi-page TIFF) as a PDF; JPEGs stay JPEG inside and
    phone photos come out upright (MuPDF follows their EXIF orientation)."""
    try:
        img = pymupdf.open(path)
    except Exception:
        # formats MuPDF can't read (WebP): through Qt as PNG
        from PySide6.QtCore import QBuffer, QByteArray, QIODevice
        from PySide6.QtGui import QImage
        q = QImage(path)
        if q.isNull():
            raise ValueError(f"{os.path.basename(path)} isn't a picture KanzonasPDF can read.")
        data = QByteArray()
        buf = QBuffer(data)
        buf.open(QIODevice.WriteOnly)
        q.save(buf, "PNG")
        img = pymupdf.open(stream=bytes(data), filetype="png")
    pdf = pymupdf.open("pdf", img.convert_to_pdf())
    img.close()
    return pdf


def add_image(result, path, letter=True):
    """Add the picture at path to result as page(s): fitted on a Letter page turned to suit it
    (letter=True), or a page the picture's own size."""
    pdf = _image_pdf(path)
    for i in range(pdf.page_count):
        w, h = pdf[i].rect.width, pdf[i].rect.height
        if letter:
            page_w, page_h = (LETTER.height, LETTER.width) if w > h else (LETTER.width, LETTER.height)
        else:
            page_w, page_h = w, h
        page = result.new_page(width=page_w, height=page_h)
        page.show_pdf_page(page.rect, pdf, i)     # keeps proportions, centered
    pdf.close()


class _FileList(QListWidget):
    """Reorder by dragging; drop PDFs from Explorer to add them."""

    def __init__(self):
        super().__init__()
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setAcceptDrops(True)

    def add_paths(self, paths):
        for p in paths:
            if os.path.splitext(p)[1].lower() in (".pdf",) + IMAGE_EXTS and os.path.isfile(p):
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
    def __init__(self, parent, start_dir="", first=None, images=False):
        super().__init__(parent)
        self.images = images
        self.title = "Create PDF from images" if images else "Combine files"
        self.setWindowTitle(self.title)
        self.resize(520, 440)
        self.start_dir = start_dir
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(("Pictures" if images else "PDFs and pictures") +
                             " to put together, top to bottom. Drag to reorder, or drop files "
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
        self.bookmarks.setChecked(not images)
        lay.addWidget(self.bookmarks)
        self.letter = QCheckBox("Put each picture on a Letter page (otherwise the page is the "
                                "picture's own size)")
        self.letter.setChecked(True)
        lay.addWidget(self.letter)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.button(QDialogButtonBox.Ok).setText("Create..." if images else "Combine...")
        btns.accepted.connect(self._ok)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)
        self.result_path = None

    def _add(self):
        filters = (IMAGE_FILTER if self.images else
                   "PDFs and pictures (*.pdf " + IMAGE_FILTER.split("(")[1] + ";;PDF files (*.pdf);;"
                   + IMAGE_FILTER)
        paths, _ = QFileDialog.getOpenFileNames(self, "Add files", self.start_dir, filters)
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
        if not paths or (len(paths) < 2 and not any(is_image(p) for p in paths)):
            QMessageBox.information(self, self.title, "Add at least two PDFs, or a picture.")
            return
        folder = os.path.dirname(paths[0])
        name = (os.path.splitext(os.path.basename(paths[0]))[0] + ".pdf" if self.images
                else "Combined.pdf")
        out, _ = QFileDialog.getSaveFileName(self, "Save the PDF as",
                                             os.path.join(folder, name),
                                             "PDF files (*.pdf)")
        if not out:
            return
        if os.path.abspath(out) in {os.path.abspath(p) for p in paths}:
            QMessageBox.warning(self, self.title, "Choose a new file name: the new PDF can't "
                                "replace one of the files going into it.")
            return
        try:
            n = combine(paths, out, self.bookmarks.isChecked(), self._password,
                        letter=self.letter.isChecked())
        except Exception as e:
            QMessageBox.warning(self, self.title, f"Couldn't make the PDF:\n{e}")
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


def combine(paths, out, bookmarks=True, ask_password=None, letter=True):
    """Write the PDFs and pictures in `paths`, in order, to `out`. Returns the page count, or
    None if a password was needed and not given. Each file's own bookmarks are kept, nested
    under the file's bookmark when `bookmarks` is on. letter: see add_image."""
    result = pymupdf.open()
    toc = []
    for p in paths:
        if is_image(p):
            start = result.page_count
            add_image(result, p, letter)
            if bookmarks:
                toc.append([1, os.path.splitext(os.path.basename(p))[0], start + 1])
            continue
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
