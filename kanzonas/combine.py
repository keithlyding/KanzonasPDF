"""File > Combine files: several PDFs and pictures, in an order you choose, into one new PDF.
File > Create PDF from images uses the same window for pictures (scans, phone photos)."""

import os

import pymupdf
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
                               QPushButton, QCheckBox, QLabel, QDialogButtonBox, QFileDialog,
                               QInputDialog, QLineEdit, QMessageBox, QAbstractItemView)

from . import measure
from .i18n import tr

IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".gif", ".webp")
IMAGE_PATTERNS = "(*.jpg *.jpeg *.png *.tif *.tiff *.bmp *.gif *.webp)"
IMAGE_FILTER = tr("Pictures") + " " + IMAGE_PATTERNS
LETTER = pymupdf.paper_rect("letter")


def is_image(path):
    return os.path.splitext(path)[1].lower() in IMAGE_EXTS


# ---- PDFs that don't allow copying ---------------------------------------------------------
# A PDF whose permissions forbid copying (it opens without a password; an owner password
# sets what's allowed) can't be put into another PDF, which wouldn't carry its restrictions:
# as File > Export refuses it, unless its permissions password is typed.
def _copy_ok(src, owner_pw=None):
    if src.permissions & pymupdf.PDF_PERM_COPY:
        return True
    return owner_pw is not None and bool(src.authenticate(owner_pw) & 4)


def not_allowed(path):
    """The message refusing a PDF whose pages may not be copied."""
    return tr("{operation} is not allowed by this PDF's permissions.").format(
        operation=tr("Copying the pages of {name}").format(name=os.path.basename(path)))


def unlock_copy(src, path, ask_owner=None):
    """The permissions password that lets src's pages be copied: "" when none is needed,
    else asked with ask_owner(path) (-> password, or None to give up) until right.
    PermissionError when it's not given."""
    if _copy_ok(src):
        return ""
    while ask_owner is not None:
        pw = ask_owner(path)
        if pw is None:
            break
        if _copy_ok(src, pw):
            return pw
    raise PermissionError(not_allowed(path))


def ask_owner_password(parent, path):
    """Ask for the permissions password of a PDF that doesn't allow copying its pages."""
    pw, ok = QInputDialog.getText(parent, tr("Password needed"),
                                  tr("{name} doesn't allow copying its pages.\nIts permissions "
                                     "(owner) password:").format(name=os.path.basename(path)),
                                  QLineEdit.Password)
    return pw if ok else None


def owner_passwords(paths, ask_owner):
    """{path: permissions password} for the PDFs in paths that don't allow copying their
    pages (asked with ask_owner, see unlock_copy), before inserting them. PermissionError
    when one isn't given. Files that won't open are left to insert_files to report."""
    out = {}
    for p in paths:
        if is_image(p):
            continue
        try:
            src = pymupdf.open(p)
        except Exception:
            continue
        with src:
            if not src.needs_pass:
                pw = unlock_copy(src, p, ask_owner)
                if pw:
                    out[p] = pw
    return out


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
            raise ValueError(tr("{name} isn't a picture KanzonasPDF can read.").format(
                name=os.path.basename(path)))
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


def image_pages(path, size):
    """The picture at path as a new PDF, each picture page fitted on a page of `size` (width,
    height in points), turned to suit the picture (Pages > Insert pages from file)."""
    pdf = _image_pdf(path)
    out = pymupdf.open()
    lo, hi = sorted(size)
    for i in range(pdf.page_count):
        w, h = pdf[i].rect.width, pdf[i].rect.height
        page = out.new_page(width=hi if w > h else lo, height=lo if w > h else hi)
        page.show_pdf_page(page.rect, pdf, i)     # keeps proportions, centered
    pdf.close()
    return out


def insert_files(doc, paths, pos, size, owner=None):
    """Insert the PDFs and pictures in `paths`, in order, into doc before page `pos`; each
    picture page is fitted on a page of `size` (see image_pages). owner: {path: permissions
    password} for PDFs that don't allow copying (owner_passwords)."""
    for path in paths:
        other = image_pages(path, size) if is_image(path) else pymupdf.open(path)
        with other:
            if other.needs_pass:
                raise ValueError(tr("{name} is password-protected: open it and use Combine "
                                    "files instead.").format(name=os.path.basename(path)))
            if not _copy_ok(other, (owner or {}).get(path)):
                raise PermissionError(not_allowed(path))
            doc.insert_pdf(other, start_at=pos)
            measure.copy_scales(other, doc, [(k, pos + k) for k in range(other.page_count)])
            pos += other.page_count


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
        self.title = tr("Create PDF from images") if images else tr("Combine files")
        self.setWindowTitle(self.title)
        self.resize(520, 440)
        self.start_dir = start_dir
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(tr("Pictures to put together, top to bottom. Drag to reorder, "
                                "or drop files here from Explorer.") if images else
                             tr("PDFs and pictures to put together, top to bottom. Drag to "
                                "reorder, or drop files here from Explorer.")))
        row = QHBoxLayout()
        self.list = _FileList()
        if first:
            self.list.add_paths(first)
        row.addWidget(self.list, 1)
        col = QVBoxLayout()
        for text, slot in ((tr("Add files..."), self._add), (tr("Remove"), self._remove),
                           (tr("Move up"), lambda: self._move(-1)),
                           (tr("Move down"), lambda: self._move(1)),
                           (tr("Sort by name"), self._sort)):
            b = QPushButton(text)
            b.clicked.connect(slot)
            col.addWidget(b)
        col.addStretch(1)
        row.addLayout(col)
        lay.addLayout(row, 1)
        self.bookmarks = QCheckBox(tr("Add a bookmark for each file (named after the file)"))
        self.bookmarks.setChecked(not images)
        lay.addWidget(self.bookmarks)
        self.letter = QCheckBox(tr("Put each picture on a Letter page (otherwise the page is "
                                   "the picture's own size)"))
        self.letter.setChecked(True)
        lay.addWidget(self.letter)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.button(QDialogButtonBox.Ok).setText(tr("Create...") if images else tr("Combine..."))
        btns.accepted.connect(self._ok)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)
        self.result_path = None
        # check_target(path) -> False: don't write there (MainWindow: the file is open with
        # unsaved changes and the user said no)
        self.check_target = None

    def _add(self):
        filters = (IMAGE_FILTER if self.images else
                   tr("PDFs and pictures") + " (*.pdf " + IMAGE_PATTERNS[1:] + ";;" +
                   tr("PDF files") + " (*.pdf);;" + IMAGE_FILTER)
        paths, _ = QFileDialog.getOpenFileNames(self, tr("Add files"), self.start_dir, filters)
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
            QMessageBox.information(self, self.title, tr("Add at least two PDFs, or a picture."))
            return
        folder = os.path.dirname(paths[0])
        name = (os.path.splitext(os.path.basename(paths[0]))[0] + ".pdf" if self.images
                else tr("Combined") + ".pdf")
        out, _ = QFileDialog.getSaveFileName(self, tr("Save the PDF as"),
                                             os.path.join(folder, name),
                                             tr("PDF files") + " (*.pdf)")
        if not out:
            return
        if os.path.abspath(out) in {os.path.abspath(p) for p in paths}:
            QMessageBox.warning(self, self.title, tr("Choose a new file name: the new PDF "
                                                     "can't replace one of the files going "
                                                     "into it."))
            return
        if self.check_target is not None and not self.check_target(out):
            return
        try:
            n = combine(paths, out, self.bookmarks.isChecked(), self._password,
                        letter=self.letter.isChecked(),
                        ask_owner=lambda p: ask_owner_password(self, p))
        except Exception as e:
            QMessageBox.warning(self, self.title, tr("Couldn't make the PDF:\n{error}").format(error=e))
            return
        if n is None:
            return
        self.result_path = out
        self.accept()

    def _password(self, path):
        pw, ok = QInputDialog.getText(self, tr("Password needed"),
                                      tr("{name} is password protected.\nPassword (Cancel stops "
                                         "combining):").format(name=os.path.basename(path)),
                                      QLineEdit.Password)
        return pw if ok else None


def _shift(page, start):
    return page + start if page > 0 else -1       # -1: a bookmark with no target page


def combine(paths, out, bookmarks=True, ask_password=None, letter=True, ask_owner=None):
    """Write the PDFs and pictures in `paths`, in order, to `out`. Returns the page count, or
    None if a password was needed and not given. Each file's own bookmarks are kept, nested
    under the file's bookmark when `bookmarks` is on. letter: see add_image. A PDF that
    doesn't allow copying needs its permissions password (ask_owner, see unlock_copy), else
    PermissionError."""
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
            unlock_copy(src, p, ask_owner)
            start = result.page_count
            result.insert_pdf(src)
            measure.copy_scales(src, result, [(k, start + k) for k in range(src.page_count)])
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
