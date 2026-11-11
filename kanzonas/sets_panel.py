"""The Sets panel (1.12; doc_sets.py): the PDFs of a set and their sheets, as one list.

Each file is listed with its pages under it, by sheet number and title where the title block
gives them (read a few pages at a time while the panel is idle), else by page label or
number. A click opens the file at that page; Previous sheet / Next sheet go on across the
files. Right-click a file to move it up or down or take it out of the set. The set file is
saved after every change to it (it's only a list of files)."""

import os

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QToolButton, QMenu,
                               QTreeWidget, QTreeWidgetItem, QLineEdit, QFileDialog,
                               QMessageBox, QInputDialog)

from . import doc_sets
from .i18n import tr

ROLE = Qt.UserRole              # (file path, page index; -1 for a file's own row)
SET_FILTER = tr("KanzonasPDF sets") + " (*" + doc_sets.SUFFIX + ")"
SLICE = 3                       # title blocks read per idle moment


class SetsPanel(QWidget):
    openRequested = Signal(str, int)        # file, page
    stepRequested = Signal(int)             # +1 next sheet, -1 previous
    combineRequested = Signal(list)         # the set's files
    setChanged = Signal()                   # a set opened, closed or changed

    def __init__(self):
        super().__init__()
        self.docset = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(2, 2, 2, 2)
        lay.setSpacing(3)
        self.title = QLabel()
        f = QFont(self.title.font())
        f.setBold(True)
        self.title.setFont(f)
        self.title.setWordWrap(True)
        lay.addWidget(self.title)
        row = QHBoxLayout()
        self.set_btn = QToolButton()
        self.set_btn.setText(tr("Set", ctx="noun"))          # (a set of files)
        self.set_btn.setPopupMode(QToolButton.InstantPopup)
        self.set_btn.setToolButtonStyle(Qt.ToolButtonTextOnly)
        menu = QMenu(self.set_btn)
        self.m_new = menu.addAction(tr("New set..."), self.new_set_dialog)
        self.m_open = menu.addAction(tr("Open set..."), self.open_set_dialog)
        menu.addSeparator()
        self.m_add = menu.addAction(tr("Add files..."), self.add_files_dialog)
        self.m_rename = menu.addAction(tr("Rename set..."), self.rename_dialog)
        self.m_combine = menu.addAction(tr("Combine to one PDF..."),
                                        lambda: self.docset and self.combineRequested.emit(
                                            [f for f in self.docset.files
                                             if os.path.isfile(f)]))
        menu.addSeparator()
        self.m_close = menu.addAction(tr("Close set"), lambda: self.set_docset(None))
        self.set_btn.setMenu(menu)
        row.addWidget(self.set_btn)
        self.prev_btn = QToolButton()
        self.prev_btn.setText("◀")
        self.prev_btn.setToolTip(tr("Previous sheet (across the set's files)"))
        self.prev_btn.clicked.connect(lambda: self.stepRequested.emit(-1))
        self.next_btn = QToolButton()
        self.next_btn.setText("▶")
        self.next_btn.setToolTip(tr("Next sheet (across the set's files)"))
        self.next_btn.clicked.connect(lambda: self.stepRequested.emit(1))
        row.addWidget(self.prev_btn)
        row.addWidget(self.next_btn)
        row.addStretch(1)
        lay.addLayout(row)
        self.find = QLineEdit()
        self.find.setPlaceholderText(tr("Filter sheets"))
        self.find.setClearButtonEnabled(True)
        self.find.textChanged.connect(self._filter)
        lay.addWidget(self.find)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setRootIsDecorated(True)
        self.tree.itemClicked.connect(self._clicked)
        self.tree.itemActivated.connect(self._clicked)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._menu)
        lay.addWidget(self.tree, 1)
        self.empty = QLabel(tr("No set is open. A set lists several PDFs (one per sheet, "
                               "say) to browse as one document without combining them: "
                               "Set > New set... or Open set...."))
        self.empty.setWordWrap(True)
        self.empty.setStyleSheet("color: gray;")
        lay.addWidget(self.empty)
        lay.addStretch(0)
        self._todo = []                     # (file, page) title blocks still to read
        self._timer = QTimer(self, interval=0)
        self._timer.timeout.connect(self._read_some)
        self._current = None
        self.set_docset(None)

    # ---- the set
    def set_docset(self, ds):
        self.docset = ds
        self.fill()
        self.setChanged.emit()

    def fill(self):
        """List the set's files and their pages (as read now)."""
        ds = self.docset
        self.tree.clear()
        self._todo = []
        self._items = {}
        has = ds is not None
        for w in (self.prev_btn, self.next_btn, self.find, self.tree):
            w.setEnabled(has)
        for a in (self.m_add, self.m_rename, self.m_combine, self.m_close):
            a.setEnabled(has)
        self.tree.setVisible(has)
        self.find.setVisible(has)
        self.empty.setVisible(not has)
        if not has:
            self.title.setText(tr("Sets"))
            self._timer.stop()
            return
        self.title.setText(ds.name)
        self.title.setToolTip(ds.path or "")
        bold = QFont(self.tree.font())
        bold.setBold(True)
        for f in ds.files:
            info = doc_sets.file_info(f)
            top = QTreeWidgetItem([os.path.basename(f)])
            top.setFont(0, bold)
            top.setData(0, ROLE, (f, -1))
            top.setToolTip(0, f)
            self.tree.addTopLevelItem(top)
            if info is None:
                top.setText(0, tr("{name} (not found)").format(name=os.path.basename(f))
                            if not os.path.exists(f) else
                            tr("{name} (can't be read)").format(name=os.path.basename(f)))
                top.setForeground(0, Qt.gray)
                continue
            big = info["big"]
            for i in range(info["pages"]):
                text = self._page_text(f, info, i)
                it = QTreeWidgetItem([text])
                it.setToolTip(0, text)          # (a long title is cut short in a narrow panel)
                it.setData(0, ROLE, (f, i))
                top.addChild(it)
                self._items[(os.path.normcase(f), i)] = it
                if i in big and doc_sets.sheet(f, i) is False:
                    self._todo.append((f, i))
            top.setExpanded(True)
        self._filter()
        if self._todo:
            self._timer.start()
        if self._current is not None:
            self.show_current(*self._current)

    @staticmethod
    def _page_text(f, info, i):
        s = doc_sets.sheet(f, i)
        if s:
            return (s["number"] + "  " + s["title"]).strip()
        label = info["labels"][i] if i < len(info["labels"]) else ""
        return label or tr("Page {n}").format(n=i + 1)

    def _read_some(self):
        """A few title blocks, then back to the event loop (PyMuPDF isn't thread-safe)."""
        if not self._todo or self.docset is None:
            self._timer.stop()
            return
        f = self._todo[0][0]
        batch = [i for g, i in self._todo[:SLICE] if g == f]
        self._todo = self._todo[len(batch):]
        doc_sets.read_sheets(f, batch)
        info = doc_sets.file_info(f)
        for i in batch:
            it = self._items.get((os.path.normcase(f), i))
            if it is not None and info is not None:
                it.setText(0, self._page_text(f, info, i))
                it.setToolTip(0, it.text(0))
        if not self._todo:
            self._timer.stop()
            self._filter()

    def _filter(self, *_):
        q = self.find.text().strip().lower()
        for k in range(self.tree.topLevelItemCount()):
            top = self.tree.topLevelItem(k)
            shown = 0
            for c in range(top.childCount()):
                it = top.child(c)
                hide = bool(q) and q not in it.text(0).lower()
                it.setHidden(hide)
                shown += not hide
            top.setHidden(bool(q) and not shown and q not in top.text(0).lower())

    # ---- where we are
    def show_current(self, path, page):
        """Mark the sheet shown now (path, page): selected in the list, without opening it."""
        self._current = (path, page)
        if self.docset is None or not path:
            return
        it = self._items.get((os.path.normcase(os.path.abspath(path)), page))
        self.tree.blockSignals(True)
        if it is not None:
            self.tree.setCurrentItem(it)
            self.tree.scrollToItem(it)
        else:
            self.tree.setCurrentItem(None)
        self.tree.blockSignals(False)

    def _clicked(self, it, _col=0):
        got = it.data(0, ROLE)
        if not got:
            return
        f, i = got
        if doc_sets.file_info(f) is None:
            return
        self.openRequested.emit(f, max(0, i))

    # ---- changes (saved at once)
    def _changed(self):
        ds = self.docset
        if ds is not None and ds.path:
            try:
                ds.save()
            except OSError as ex:
                QMessageBox.warning(self, tr("Sets"), tr("Couldn't save {name}:\n{error}").format(
                    name=os.path.basename(ds.path), error=ex.strerror or ex))
        self.fill()
        self.setChanged.emit()

    def add_files(self, paths):
        if self.docset is not None and self.docset.add(paths):
            self._changed()

    def remove_file(self, path):
        if self.docset is not None:
            self.docset.remove(path)
            self._changed()

    def move_file(self, path, step):
        if self.docset is not None and self.docset.move(path, step):
            self._changed()

    def rename(self, name):
        if self.docset is not None and name and name != self.docset.name:
            self.docset.name = name
            self.docset.dirty = True
            self._changed()

    def _menu(self, pos):
        it = self.tree.itemAt(pos)
        got = it.data(0, ROLE) if it is not None else None
        if not got:
            return
        f = got[0]
        m = QMenu(self)
        m.addAction(tr("Open"), lambda: self.openRequested.emit(f, max(0, got[1])))
        m.addSeparator()
        k = self.docset.index_of(f)
        up = m.addAction(tr("Move up"), lambda: self.move_file(f, -1))
        up.setEnabled(bool(k))
        down = m.addAction(tr("Move down"), lambda: self.move_file(f, 1))
        down.setEnabled(k is not None and k < len(self.docset.files) - 1)
        m.addAction(tr("Remove from set"), lambda: self.remove_file(f))
        m.exec(self.tree.viewport().mapToGlobal(pos))

    # ---- dialogs (the Set button's menu)
    def _start_dir(self):
        from . import paths
        if self.docset is not None and self.docset.path:
            return os.path.dirname(self.docset.path)
        return paths.stored_str(paths.settings(), "last_dir") or os.path.expanduser("~")

    def _pick_pdfs(self, title):
        got, _ = QFileDialog.getOpenFileNames(self, title, self._start_dir(),
                                              tr("PDF files") + " (*.pdf)")
        return got

    def new_set_dialog(self):
        files = self._pick_pdfs(tr("The PDFs in the new set"))
        if not files:
            return
        start = os.path.join(os.path.dirname(files[0]),
                             os.path.basename(os.path.dirname(files[0])) + doc_sets.SUFFIX)
        path, _ = QFileDialog.getSaveFileName(self, tr("Save the set as"), start, SET_FILTER)
        if not path:
            return
        if not path.lower().endswith(doc_sets.SUFFIX):
            path += doc_sets.SUFFIX
        self.new_set(path, files)

    def new_set(self, path, files):
        ds = doc_sets.DocSet(os.path.splitext(os.path.basename(path))[0], files, path)
        try:
            ds.save()
        except OSError as ex:
            QMessageBox.warning(self, tr("Sets"), tr("Couldn't save {name}:\n{error}").format(
                name=os.path.basename(path), error=ex.strerror or ex))
            return None
        self.set_docset(ds)
        return ds

    def open_set_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, tr("Open set"), self._start_dir(),
                                              SET_FILTER)
        if path:
            self.open_set(path)

    def open_set(self, path):
        try:
            ds = doc_sets.DocSet.load(path)
        except doc_sets.SetError as ex:
            QMessageBox.warning(self, tr("Open set"), tr(
                "{name} isn't a set KanzonasPDF can read:\n{error}").format(
                    name=os.path.basename(path), error=ex))
            return None
        self.set_docset(ds)
        return ds

    def add_files_dialog(self):
        files = self._pick_pdfs(tr("Add files to the set"))
        if files:
            self.add_files(files)

    def rename_dialog(self):
        if self.docset is None:
            return
        name, ok = QInputDialog.getText(self, tr("Rename set"), tr("Name of the set:"),
                                        text=self.docset.name)
        if ok and name.strip():
            self.rename(name.strip())
