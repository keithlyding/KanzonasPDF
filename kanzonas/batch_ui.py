"""Tools > Batch processing...: the window. Pick files or a folder, build the list of steps
(or load a recipe), choose where the results go, run, and read the report. The work itself
is batch.py's; this window drives its generator from Qt's event loop in short slices."""

import json
import os
import time

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QButtonGroup, QCheckBox,
                               QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
                               QFileDialog, QFormLayout, QGridLayout, QGroupBox, QHBoxLayout,
                               QHeaderView, QInputDialog, QLabel, QLineEdit, QListWidget,
                               QMenu, QMessageBox, QPlainTextEdit, QProgressBar, QPushButton,
                               QRadioButton, QScrollArea, QSpinBox, QSplitter, QToolButton,
                               QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from . import batch as B
from .i18n import tr

PROTECTED_CHOICES = [("ask", tr("Ask for the password")), ("skip", tr("Skip them"))]
OVERWRITE_CHOICES = [("ask", tr("Ask")), ("number", tr("Add a number: name (2).pdf")),
                     ("replace", tr("Replace it")), ("skip", tr("Skip the file"))]
PATTERNS = ["{name}", "{name}_processed", "{name}_ocr", "{n}_{name}", "{bates}"]


class _FileList(QTreeWidget):
    """The files, with their page counts; files and folders can be dropped on it."""

    def __init__(self, window):
        super().__init__()
        self.window_ = window
        self.setHeaderLabels([tr("File"), tr("Pages"), tr("Status"), tr("Folder")])
        self.setRootIsDecorated(False)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DropOnly)
        h = self.header()
        h.setSectionResizeMode(0, QHeaderView.Interactive)
        self.setColumnWidth(0, 220)
        self.setColumnWidth(1, 80)
        self.setColumnWidth(2, 90)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
        else:
            super().dragEnterEvent(e)

    dragMoveEvent = dragEnterEvent

    def dropEvent(self, e):
        if not e.mimeData().hasUrls():
            return super().dropEvent(e)
        paths = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        e.acceptProposedAction()
        self.window_.add_paths(paths)


class PasswordDialog(QDialog):
    """A protected file's password, asked once: OK, Skip this file, or Skip all of them."""

    def __init__(self, parent, path, kind):
        super().__init__(parent)
        self.setWindowTitle(tr("Password needed"))
        lay = QVBoxLayout(self)
        name = os.path.basename(path)
        text = tr("{name} is password-protected. Its password:") if kind == "open" else \
            tr("{name} doesn't allow changes. Its permissions password:")
        lay.addWidget(QLabel(text.format(name=name)))
        self.edit = QLineEdit()
        self.edit.setEchoMode(QLineEdit.Password)
        lay.addWidget(self.edit)
        note = QLabel(tr("It's tried first on the next protected files, so a set that shares "
                         "one password is asked once."))
        note.setWordWrap(True)
        lay.addWidget(note)
        btns = QDialogButtonBox()
        ok = btns.addButton(QDialogButtonBox.Ok)
        skip = btns.addButton(tr("Skip this file"), QDialogButtonBox.RejectRole)
        skip_all = btns.addButton(tr("Skip all protected files"), QDialogButtonBox.RejectRole)
        self.skip_all = False
        ok.clicked.connect(self.accept)
        skip.clicked.connect(self.reject)
        skip_all.clicked.connect(lambda: (setattr(self, "skip_all", True), self.reject()))
        lay.addWidget(btns)


class ReportDialog(QDialog):
    """What happened to each file: done, skipped or failed, with the reason; saved as text
    or CSV."""

    def __init__(self, parent, results):
        super().__init__(parent)
        self.results = results
        self.setWindowTitle(tr("Batch report"))
        self.resize(900, 460)
        lay = QVBoxLayout(self)
        counts = {s: sum(1 for r in results if r.status == s)
                  for s in (B.DONE, B.SKIPPED, B.FAILED, B.CANCELED)}
        lay.addWidget(QLabel(tr("Done: {done}   Skipped: {skipped}   Failed: {failed}   "
                                "Canceled: {canceled}").format(
            done=counts[B.DONE], skipped=counts[B.SKIPPED], failed=counts[B.FAILED],
            canceled=counts[B.CANCELED])))
        tree = QTreeWidget()
        tree.setRootIsDecorated(False)
        tree.setHeaderLabels([tr("File"), tr("Status"), tr("Output"), tr("Details")])
        tree.setColumnWidth(0, 220)
        tree.setColumnWidth(1, 80)
        tree.setColumnWidth(2, 260)
        colors = {B.FAILED: Qt.red, B.SKIPPED: Qt.darkYellow, B.CANCELED: Qt.gray}
        for r, (path, status, outputs, details) in zip(results, B.report_rows(results)):
            it = QTreeWidgetItem([os.path.basename(path), status,
                                  "; ".join(os.path.basename(p) for p in r.outputs), details])
            it.setToolTip(0, path)
            it.setToolTip(2, outputs)
            it.setToolTip(3, details)
            if r.status in colors:
                it.setForeground(1, colors[r.status])
            tree.addTopLevelItem(it)
        lay.addWidget(tree)
        row = QHBoxLayout()
        save = QPushButton(tr("Save report..."))
        save.clicked.connect(self._save)
        row.addWidget(save)
        folder = next((os.path.dirname(p) for r in results for p in r.outputs), None)
        if folder:
            show = QPushButton(tr("Open the output folder"))
            show.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(folder)))
            row.addWidget(show)
        row.addStretch(1)
        close = QPushButton(tr("Close"))
        close.clicked.connect(self.accept)
        row.addWidget(close)
        lay.addLayout(row)

    def _save(self):
        start = os.path.join(os.path.expanduser("~"), tr("Batch report") + ".csv")
        path, flt = QFileDialog.getSaveFileName(
            self, tr("Save report"), start,
            tr("CSV (opens in Excel)") + " (*.csv);;" + tr("Text file") + " (*.txt)")
        if not path:
            return
        if not os.path.splitext(path)[1]:
            path += ".txt" if "txt" in flt else ".csv"
        try:
            B.write_report(self.results, path)
        except OSError as ex:
            QMessageBox.warning(self, tr("Save report"), str(ex))


class BatchWindow(QDialog):
    """Tools > Batch processing. One per main window; it stays open while you work."""

    @classmethod
    def open_for(cls, window):
        w = getattr(window, "_batch_window", None)
        if w is None:
            w = window._batch_window = cls(window)
        w.show()
        w.raise_()
        w.activateWindow()
        return w

    def __init__(self, window):
        super().__init__(window)
        self.main = window
        self.settings = window.settings
        self.setWindowFlag(Qt.Window, True)
        self.setWindowTitle(tr("Batch processing"))
        self.resize(1000, 720)
        self.steps = []
        self._batch = None
        self._gen = None
        self._results = None
        self._count_todo = []
        self._close_after = False
        lay = QVBoxLayout(self)

        # recipes
        row = QHBoxLayout()
        row.addWidget(QLabel(tr("Recipe:")))
        self.recipe = QComboBox()
        self.recipe.setMinimumWidth(260)
        self.recipe.activated.connect(self._load_recipe)
        row.addWidget(self.recipe)
        self.b_save_recipe = QPushButton(tr("Save recipe..."))
        self.b_save_recipe.clicked.connect(self._save_recipe)
        self.b_del_recipe = QPushButton(tr("Delete recipe"))
        self.b_del_recipe.clicked.connect(self._delete_recipe)
        row.addWidget(self.b_save_recipe)
        row.addWidget(self.b_del_recipe)
        row.addStretch(1)
        lay.addLayout(row)

        split = QSplitter(Qt.Horizontal)
        split.addWidget(self._files_box())
        split.addWidget(self._steps_box())
        split.setSizes([480, 520])
        lay.addWidget(split, 1)
        lay.addWidget(self._output_box())

        # progress and buttons
        self.status = QLabel(tr("Add files, add steps, then Run."))
        lay.addWidget(self.status)
        grid = QGridLayout()
        grid.addWidget(QLabel(tr("This file:")), 0, 0)
        self.file_bar = QProgressBar()
        self.file_bar.setRange(0, 1000)
        grid.addWidget(self.file_bar, 0, 1)
        grid.addWidget(QLabel(tr("All files:")), 1, 0)
        self.all_bar = QProgressBar()
        self.all_bar.setRange(0, 1000)
        grid.addWidget(self.all_bar, 1, 1)
        lay.addLayout(grid)
        row = QHBoxLayout()
        self.b_report = QPushButton(tr("Report..."))
        self.b_report.setEnabled(False)
        self.b_report.clicked.connect(self._show_report)
        row.addWidget(self.b_report)
        row.addStretch(1)
        self.b_run = QPushButton(tr("Run"))
        self.b_run.setDefault(True)
        self.b_run.clicked.connect(self.run)
        self.b_cancel = QPushButton(tr("Cancel"))
        self.b_cancel.setEnabled(False)
        self.b_cancel.setToolTip(tr("Finish the file being processed, then stop"))
        self.b_cancel.clicked.connect(self.cancel)
        self.b_close = QPushButton(tr("Close"))
        self.b_close.clicked.connect(self.close)
        for b in (self.b_run, self.b_cancel, self.b_close):
            row.addWidget(b)
        lay.addLayout(row)

        self._count_timer = QTimer(self)
        self._count_timer.setInterval(0)
        self._count_timer.timeout.connect(self._count_next)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._tick)
        self._fill_recipes()
        self._restore()

    # ---- files ------------------------------------------------------------------------
    def _files_box(self):
        box = QGroupBox(tr("Files"))
        lay = QVBoxLayout(box)
        self.files = _FileList(self)
        lay.addWidget(self.files, 1)
        row = QHBoxLayout()
        add = QPushButton(tr("Add files..."))
        add.clicked.connect(self._add_files)
        folder = QPushButton(tr("Add folder..."))
        folder.clicked.connect(self._add_folder)
        self.subfolders = QCheckBox(tr("Include subfolders"))
        row.addWidget(add)
        row.addWidget(folder)
        row.addWidget(self.subfolders)
        row.addStretch(1)
        lay.addLayout(row)
        row = QHBoxLayout()
        for text, fn in ((tr("Remove"), self._remove_files), (tr("Move up"),
                                                              lambda: self._move_files(-1)),
                         (tr("Move down"), lambda: self._move_files(1)),
                         (tr("Sort by name"), self._sort_files), (tr("Clear"), self._clear_files)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            row.addWidget(b)
        row.addStretch(1)
        lay.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(QLabel(tr("Password-protected files:")))
        self.protected = QComboBox()
        for value, text in PROTECTED_CHOICES:
            self.protected.addItem(text, value)
        row.addWidget(self.protected)
        row.addStretch(1)
        lay.addLayout(row)
        tip = QLabel(tr("Files are processed in this order (Bates numbers and Combine follow "
                        "it). Drop files or folders here."))
        tip.setWordWrap(True)
        lay.addWidget(tip)
        return box

    def _last_dir(self):
        from . import paths
        return paths.stored_str(self.settings, "last_dir", os.path.expanduser("~"))

    def _add_files(self):
        from .main_window import PDF_FILTER
        paths, _ = QFileDialog.getOpenFileNames(self, tr("Add files"), self._last_dir(),
                                                PDF_FILTER)
        if paths:
            self.settings.setValue("last_dir", os.path.dirname(paths[0]))
            self.add_paths(paths)

    def _add_folder(self):
        folder = QFileDialog.getExistingDirectory(self, tr("Add folder"), self._last_dir())
        if folder:
            self.settings.setValue("last_dir", folder)
            self.add_paths([folder])

    def add_paths(self, paths):
        """Add files (PDFs) and folders (their PDFs; subfolders too when ticked), in order,
        leaving out files already in the list."""
        have = {os.path.normcase(it.data(0, Qt.UserRole)) for it in self._items_widgets()}
        new = []
        for p in paths:
            p = os.path.abspath(p)
            if os.path.isdir(p):
                new += B.files_in(p, self.subfolders.isChecked())
            elif os.path.isfile(p) and p.lower().endswith(".pdf"):
                new.append(B.Item(p, os.path.dirname(p)))
        for item in new:
            key = os.path.normcase(item.path)
            if key in have:
                continue
            have.add(key)
            it = QTreeWidgetItem([os.path.basename(item.path), "…", "",
                                  os.path.dirname(item.path)])
            it.setData(0, Qt.UserRole, item.path)
            it.setData(1, Qt.UserRole, item.root)
            it.setToolTip(0, item.path)
            it.setTextAlignment(1, Qt.AlignRight | Qt.AlignVCenter)
            self.files.addTopLevelItem(it)
            self._count_todo.append(it)
        if self._count_todo:
            self._count_timer.start()
        self._update_buttons()

    def _count_next(self):
        """Read one file's page count (one per turn of the event loop: a folder of hundreds
        of files fills in without freezing the window)."""
        while self._count_todo:
            it = self._count_todo.pop(0)
            try:
                if self.files.indexOfTopLevelItem(it) < 0:
                    continue
            except RuntimeError:
                continue
            it.setText(1, str(B.page_count(it.data(0, Qt.UserRole))))
            return
        self._count_timer.stop()

    def _items_widgets(self):
        return [self.files.topLevelItem(i) for i in range(self.files.topLevelItemCount())]

    def items(self):
        return [B.Item(it.data(0, Qt.UserRole), it.data(1, Qt.UserRole))
                for it in self._items_widgets()]

    def _remove_files(self):
        for it in self.files.selectedItems():
            self.files.takeTopLevelItem(self.files.indexOfTopLevelItem(it))
        self._update_buttons()

    def _move_files(self, step):
        rows = sorted(self.files.indexOfTopLevelItem(it) for it in self.files.selectedItems())
        if not rows:
            return
        n = self.files.topLevelItemCount()
        if (step < 0 and rows[0] == 0) or (step > 0 and rows[-1] == n - 1):
            return
        for r in (rows if step < 0 else reversed(rows)):
            it = self.files.takeTopLevelItem(r)
            self.files.insertTopLevelItem(r + step, it)
            it.setSelected(True)

    def _sort_files(self):
        its = self._items_widgets()
        its.sort(key=lambda it: (it.text(3).lower(), it.text(0).lower()))
        self.files.clear()
        self.files.addTopLevelItems(its)

    def _clear_files(self):
        self.files.clear()
        self._count_todo = []
        self._update_buttons()

    # ---- steps ------------------------------------------------------------------------
    def _steps_box(self):
        box = QGroupBox(tr("Steps (done in this order)"))
        lay = QHBoxLayout(box)
        left = QVBoxLayout()
        self.step_list = QListWidget()
        self.step_list.currentRowChanged.connect(self._show_options)
        left.addWidget(self.step_list, 1)
        row = QHBoxLayout()
        add = QToolButton()
        add.setText(tr("Add step"))
        add.setPopupMode(QToolButton.InstantPopup)
        menu = QMenu(add)
        for kind, (name, _desc, _fields) in B.steps_table().items():
            menu.addAction(name, lambda k=kind: self.add_step(B.step(k)))
        add.setMenu(menu)
        row.addWidget(add)
        for text, fn in ((tr("Remove"), self._remove_step), (tr("Move up"),
                                                             lambda: self._move_step(-1)),
                         (tr("Move down"), lambda: self._move_step(1))):
            b = QPushButton(text)
            b.clicked.connect(fn)
            row.addWidget(b)
        left.addLayout(row)
        lay.addLayout(left, 1)
        self.options_area = QScrollArea()
        self.options_area.setWidgetResizable(True)
        self.options_area.setMinimumWidth(300)
        lay.addWidget(self.options_area, 1)
        return box

    def set_steps(self, steps):
        self.steps = [dict(kind=s["kind"], options=dict(s["options"])) for s in steps]
        self.step_list.clear()
        for st in self.steps:
            self.step_list.addItem(B.summary(st))
        self.step_list.setCurrentRow(0 if self.steps else -1)
        if not self.steps:
            self._show_options(-1)
        self._update_buttons()

    def add_step(self, st):
        row = len(self.steps)
        if self.steps and self.steps[-1]["kind"] == "combine" and st["kind"] != "combine":
            row -= 1                    # (Combine stays last)
        self.steps.insert(row, st)
        self.step_list.insertItem(row, B.summary(st))
        self.step_list.setCurrentRow(row)
        self._update_buttons()

    def _remove_step(self):
        row = self.step_list.currentRow()
        if row < 0:
            return
        del self.steps[row]
        self.step_list.takeItem(row)
        self._show_options(self.step_list.currentRow())
        self._update_buttons()

    def _move_step(self, step):
        row = self.step_list.currentRow()
        to = row + step
        if row < 0 or not 0 <= to < len(self.steps):
            return
        self.steps[row], self.steps[to] = self.steps[to], self.steps[row]
        it = self.step_list.takeItem(row)
        self.step_list.insertItem(to, it)
        self.step_list.setCurrentRow(to)

    def _show_options(self, row):
        """The chosen step's options as a form; a change is kept in the step at once."""
        page = QWidget()
        form = QFormLayout(page)
        if 0 <= row < len(self.steps):
            st = self.steps[row]
            name, desc, fields = B.steps_table()[st["kind"]]
            title = QLabel("<b>%s</b>" % name)
            form.addRow(title)
            if desc:
                d = QLabel(desc)
                d.setWordWrap(True)
                form.addRow(d)
            for f in fields:
                w = self._editor(st, f, row)
                if f.type == "bool":
                    form.addRow(w)
                else:
                    form.addRow(f.label, w)
            if not fields:
                form.addRow(QLabel(tr("This step has no options.")))
        self.options_area.setWidget(page)

    def _editor(self, st, f, row):
        o = st["options"]

        def put(value):
            o[f.key] = value
            item = self.step_list.item(row)
            if item is not None:
                item.setText(B.summary(st))
        v = o.get(f.key, f.default)
        if f.type == "bool":
            w = QCheckBox(f.label)
            w.setChecked(bool(v))
            w.toggled.connect(put)
        elif f.type == "int":
            w = QSpinBox()
            w.setRange(f.extra[0], f.extra[1])
            w.setSuffix(f.extra[2])
            w.setValue(int(v))
            w.valueChanged.connect(put)
        elif f.type == "float":
            w = QDoubleSpinBox()
            w.setRange(f.extra[0], f.extra[1])
            w.setSuffix(f.extra[2])
            w.setValue(float(v))
            w.valueChanged.connect(put)
        elif f.type == "choice":
            w = QComboBox()
            for value, text in f.extra:
                w.addItem(text, value)
            values = [c for c, _t in f.extra]
            w.setCurrentIndex(values.index(v) if v in values else 0)
            w.currentIndexChanged.connect(lambda i: put(f.extra[i][0]))
        elif f.type == "color":
            from .properties import ColorButton
            w = ColorButton()
            w.set_color(v or f.default)
            w.changed.connect(lambda: put(w.color()))
        elif f.type == "lines":
            w = QPlainTextEdit(v)
            w.setMaximumHeight(110)
            w.textChanged.connect(lambda: put(w.toPlainText()))
        elif f.type == "image":
            w = QWidget()
            row_ = QHBoxLayout(w)
            row_.setContentsMargins(0, 0, 0, 0)
            edit = QLineEdit(v)
            edit.textChanged.connect(put)
            browse = QPushButton(tr("Browse..."))

            def pick():
                path, _ = QFileDialog.getOpenFileName(self, tr("Watermark image"), "",
                                                      tr("Images") + " (*.png *.jpg *.jpeg *.bmp)")
                if path:
                    edit.setText(path)
            browse.clicked.connect(pick)
            row_.addWidget(edit)
            row_.addWidget(browse)
        else:
            w = QLineEdit(v)
            if f.type == "password":
                w.setEchoMode(QLineEdit.Password)
                w.setPlaceholderText(tr("not saved in recipes"))
            elif f.type == "pages":
                w.setPlaceholderText(f.extra)
            w.textChanged.connect(put)
        return w

    # ---- recipes ----------------------------------------------------------------------
    def _fill_recipes(self, select=None):
        self.recipe.blockSignals(True)
        self.recipe.clear()
        self.recipe.addItem(tr("(choose a recipe)"), None)
        mine = B.user_recipes(self.settings)
        built = B.builtin_recipes()
        for name in list(built) + sorted(n for n in mine if n not in built):
            self.recipe.addItem(name, name)
        if select is not None:
            self.recipe.setCurrentIndex(max(0, self.recipe.findData(select)))
        self.recipe.blockSignals(False)
        self._update_buttons()

    def _load_recipe(self, index):
        name = self.recipe.itemData(index)
        if name is None:
            return
        steps = B.recipes(self.settings).get(name)
        if steps is not None:
            self.set_steps(steps)
        self._update_buttons()

    def _save_recipe(self):
        if not self.steps:
            QMessageBox.information(self, tr("Save recipe"), tr("Add the steps first."))
            return
        current = self.recipe.currentData() or ""
        name, ok = QInputDialog.getText(self, tr("Save recipe"), tr("Recipe name:"),
                                        QLineEdit.Normal, current)
        name = name.strip()
        if not ok or not name:
            return
        if name in B.user_recipes(self.settings) and name != current and QMessageBox.question(
                self, tr("Save recipe"), tr("Replace the recipe {name}?").format(name=name)) \
                != QMessageBox.Yes:
            return
        B.save_recipe(self.settings, name, self.steps)
        self._fill_recipes(name)

    def _delete_recipe(self):
        name = self.recipe.currentData()
        if not name or name not in B.user_recipes(self.settings):
            return
        if QMessageBox.question(self, tr("Delete recipe"),
                                tr("Delete the recipe {name}?").format(name=name)) \
                != QMessageBox.Yes:
            return
        B.delete_recipe(self.settings, name)
        self._fill_recipes()

    # ---- output -----------------------------------------------------------------------
    def _output_box(self):
        box = QGroupBox(tr("Output"))
        grid = QGridLayout(box)
        self.out_next = QRadioButton(tr("A \"Processed\" folder next to each file"))
        self.out_folder = QRadioButton(tr("This folder:"))
        group = QButtonGroup(box)
        group.addButton(self.out_next)
        group.addButton(self.out_folder)
        self.out_next.setChecked(True)
        self.folder = QLineEdit()
        self.folder.textEdited.connect(lambda _t: self.out_folder.setChecked(True))
        browse = QPushButton(tr("Browse..."))
        browse.clicked.connect(self._browse_out)
        self.keep_structure = QCheckBox(tr("Keep the folder structure"))
        self.keep_structure.setChecked(True)
        self.keep_structure.setToolTip(tr("Files from subfolders of an added folder go into the "
                                          "same subfolders of the output folder"))
        grid.addWidget(self.out_next, 0, 0, 1, 2)
        grid.addWidget(self.out_folder, 1, 0)
        row = QHBoxLayout()
        row.addWidget(self.folder, 1)
        row.addWidget(browse)
        row.addWidget(self.keep_structure)
        grid.addLayout(row, 1, 1)
        grid.addWidget(QLabel(tr("File name:")), 2, 0)
        self.pattern = QComboBox()
        self.pattern.setEditable(True)
        self.pattern.addItems(PATTERNS)
        self.pattern.setMinimumWidth(200)
        row = QHBoxLayout()
        row.addWidget(self.pattern)
        hint = QLabel(tr("{name}: the file's name, {n}: its number in the list, "
                         "{date}: today, {bates}: its first Bates number"))
        hint.setWordWrap(True)
        row.addWidget(hint, 1)
        grid.addLayout(row, 2, 1)
        grid.addWidget(QLabel(tr("If the file is already there:")), 3, 0)
        self.overwrite = QComboBox()
        for value, text in OVERWRITE_CHOICES:
            self.overwrite.addItem(text, value)
        self.originals = QCheckBox(tr("Allow replacing the original files"))
        self.originals.setToolTip(tr("Off: a result never replaces the file it was made from"))
        row = QHBoxLayout()
        row.addWidget(self.overwrite)
        row.addWidget(self.originals)
        row.addStretch(1)
        grid.addLayout(row, 3, 1)
        grid.setColumnStretch(1, 1)
        return box

    def _browse_out(self):
        folder = QFileDialog.getExistingDirectory(self, tr("Output folder"),
                                                  self.folder.text() or self._last_dir())
        if folder:
            self.folder.setText(folder)
            self.out_folder.setChecked(True)

    def output(self):
        return {"mode": "folder" if self.out_folder.isChecked() else "next",
                "folder": self.folder.text().strip(),
                "keep_structure": self.keep_structure.isChecked(),
                "pattern": self.pattern.currentText().strip() or "{name}",
                "overwrite": self.overwrite.currentData(),
                "replace_originals": self.originals.isChecked(),
                "protected": self.protected.currentData()}

    # ---- remembered setup -------------------------------------------------------------
    def _remember(self):
        out = self.output()
        self.settings.setValue("batch/output", json.dumps(out))
        self.settings.setValue("batch/steps", json.dumps(B.without_secrets(self.steps)))
        self.settings.setValue("batch/subfolders", "true" if self.subfolders.isChecked()
                               else "false")

    def _restore(self):
        try:
            out = json.loads(self.settings.value("batch/output", "") or "{}")
        except (TypeError, ValueError, RecursionError):
            out = {}
        if not isinstance(out, dict):
            out = {}
        self.out_folder.setChecked(out.get("mode") == "folder")
        self.out_next.setChecked(out.get("mode") != "folder")
        self.folder.setText(str(out.get("folder") or ""))
        self.keep_structure.setChecked(out.get("keep_structure", True) is not False)
        self.pattern.setCurrentText(str(out.get("pattern") or "{name}"))
        for combo, key in ((self.overwrite, "overwrite"), (self.protected, "protected")):
            combo.setCurrentIndex(max(0, combo.findData(out.get(key))))
        self.originals.setChecked(False)        # (never remembered: asked for each run)
        self.subfolders.setChecked(str(self.settings.value("batch/subfolders", "true"))
                                   .lower() == "true")
        try:
            steps = json.loads(self.settings.value("batch/steps", "") or "[]")
        except (TypeError, ValueError, RecursionError):
            steps = []
        self.set_steps(B.normalized(steps))

    def _update_buttons(self):
        running = self._gen is not None
        self.b_run.setEnabled(not running)
        self.b_del_recipe.setEnabled(not running and
                                     self.recipe.currentData() in B.user_recipes(self.settings))

    # ---- running ----------------------------------------------------------------------
    def run(self):
        if self._gen is not None:
            return
        items = self.items()
        problems = [] if items else [tr("Add the files to process.")]
        problems += B.check_steps(self.steps)
        out = self.output()
        if out["mode"] == "folder" and not out["folder"]:
            problems.append(tr("Choose the output folder."))
        if problems:
            QMessageBox.warning(self, tr("Batch processing"), "\n".join(problems))
            return
        probe = B.Batch(items, self.steps, out)
        if not out["replace_originals"] and B.changes_documents(probe.steps) and \
                "{bates}" not in out["pattern"] and \
                (probe.combine is None or probe.combine.get("keep_each")):
            clash = next((it for i, it in enumerate(items) if os.path.normcase(
                probe.output_path(i, it)) == os.path.normcase(os.path.abspath(it.path))), None)
            if clash is not None:
                QMessageBox.warning(self, tr("Batch processing"), tr(
                    "The results would replace the original files (such as {name}). Choose "
                    "another folder or file name, or tick Allow replacing the original "
                    "files.").format(name=os.path.basename(clash.path)))
                return
        self._remember()
        from .main_window import MainWindow
        self._batch = B.Batch(items, self.steps, out, ask_password=self._ask_password,
                              ask_overwrite=self._ask_overwrite,
                              before_write=MainWindow._writing_over,
                              after_write=MainWindow._written_over,
                              pump=QApplication.processEvents)
        self._total = len(items) + (1 if self._batch.combine is not None else 0)
        for it in self._items_widgets():
            it.setText(2, "")
        self._shown = 0
        self._gen = self._batch.run()
        self._set_running(True)
        self.file_bar.setValue(0)
        self.all_bar.setValue(0)
        self._timer.start(0)

    def _set_running(self, on):
        for w in (self.files.parentWidget(), self.step_list.parentWidget(),
                  self.folder.parentWidget(), self.recipe, self.b_save_recipe):
            w.setEnabled(not on)
        self.b_cancel.setEnabled(on)
        self.b_cancel.setText(tr("Cancel"))
        self.b_report.setEnabled(not on and self._results is not None)
        self._update_buttons()

    def _tick(self):
        if self._gen is None:
            return
        end = time.monotonic() + 0.05
        wait = False
        try:
            while time.monotonic() < end:
                ev = next(self._gen)
                if ev is B.WAIT:
                    wait = True
                    break
                self._progress(*ev)
        except StopIteration:
            self._finished()
            return
        except Exception as ex:          # (the engine reports per file: not expected)
            self._finished(str(ex))
            return
        self._mark_rows()
        self._timer.start(30 if wait else 0)

    def _progress(self, i, frac, text):
        self.status.setText(text)
        self.file_bar.setValue(int(frac * 1000))
        self.all_bar.setValue(int((i + frac) / max(1, self._total) * 1000))

    def _mark_rows(self):
        """Each finished file's status in the list."""
        rows = self._items_widgets()
        res = self._batch.results
        while self._shown < len(res) and self._shown < len(rows) and \
                res[self._shown].status is not None:
            r = res[self._shown]
            rows[self._shown].setText(2, B.STATUS_LABELS.get(r.status, ""))
            rows[self._shown].setToolTip(2, r.details())
            self._shown += 1

    def cancel(self):
        if self._batch is None:
            return
        if not self._batch.cancel:
            self._batch.cancel = True
            self.b_cancel.setText(tr("Stop now"))
            self.b_cancel.setToolTip(tr("Stop at once: the file being processed is left out "
                                        "(nothing half-written is left)"))
            self.status.setText(tr("Finishing the current file, then stopping..."))
        else:
            self._batch.stop = True
            self.status.setText(tr("Stopping..."))

    def _finished(self, error=None):
        self._mark_rows()
        self._gen = None
        self._results = self._batch.results
        c = self._batch.counts()
        self._set_running(False)
        self.file_bar.setValue(1000 if not error else 0)
        self.all_bar.setValue(1000 if not (self._batch.cancel or self._batch.stop) else
                              self.all_bar.value())
        self.status.setText(error or tr("Finished. Done: {done}, skipped: {skipped}, failed: "
                                        "{failed}.").format(done=c[B.DONE], skipped=c[B.SKIPPED],
                                                            failed=c[B.FAILED]))
        if self._close_after:
            self.close()
            return
        self._show_report()

    def _show_report(self):
        if self._results is not None:
            ReportDialog(self, self._results).exec()

    def _ask_password(self, path, kind):
        dlg = PasswordDialog(self, path, kind)
        if dlg.exec() and dlg.edit.text():
            return dlg.edit.text()
        if dlg.skip_all and self._batch is not None:
            self._batch.output["protected"] = "skip"
        return None

    def _ask_overwrite(self, path):
        box = QMessageBox(QMessageBox.Question, tr("Batch processing"),
                          tr("{name} is already in {folder}.").format(
                              name=os.path.basename(path), folder=os.path.dirname(path)),
                          parent=self)
        answers = {box.addButton(tr("Replace"), QMessageBox.AcceptRole): "replace",
                   box.addButton(tr("Replace all"), QMessageBox.AcceptRole): "replace_all",
                   box.addButton(tr("Skip"), QMessageBox.RejectRole): "skip",
                   box.addButton(tr("Skip all"), QMessageBox.RejectRole): "skip_all"}
        box.exec()
        return answers.get(box.clickedButton(), "skip")

    def reject(self):
        self.close()                    # (Escape: as the window's close button)

    def closeEvent(self, e):
        if self._gen is not None:
            if QMessageBox.question(self, tr("Batch processing"),
                                    tr("Stop the batch? The file being processed is left out; "
                                       "the files done so far stay.")) != QMessageBox.Yes:
                e.ignore()
                return
            self._batch.cancel = self._batch.stop = True
            self._close_after = True
            e.ignore()
            return
        self._remember()
        super().closeEvent(e)
