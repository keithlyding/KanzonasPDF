"""The windows of Make bookmarks from headings / tagged structure / sheet numbers (a preview
to untick, rename and re-level the bookmarks found) and of Insert table of contents, and the
commands behind them. The finding itself is in bookmarks_auto."""

import time

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                               QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
                               QProgressDialog, QPushButton, QRadioButton, QSpinBox,
                               QTreeWidget, QTreeWidgetItem, QVBoxLayout, QAbstractItemView)

from . import bookmarks_auto as BA
from .i18n import tr

SLICE = 0.05            # seconds of reading between two looks at the window


def run_sliced(parent, title, text, steps, total):
    """Run the generator steps (it yields after each page) in short slices on the Qt event
    loop, with a progress bar and Cancel. total(): the number of steps (0: unknown).
    Returns False when cancelled."""
    progress = QProgressDialog(text, tr("Cancel"), 0, 0, parent)
    progress.setWindowTitle(title)
    progress.setWindowModality(Qt.WindowModal)
    progress.setMinimumDuration(400)
    last = time.monotonic()
    try:
        for done in steps:
            now = time.monotonic()
            if now - last < SLICE:
                continue
            last = now
            n = total()
            if n and progress.maximum() != n:
                progress.setMaximum(n)
            if n:
                progress.setValue(min(done, n - 1))
            QApplication.processEvents()
            if progress.wasCanceled():
                steps.close()
                return False
        return not progress.wasCanceled()
    finally:
        progress.close()
        progress.deleteLater()


class PreviewDialog(QDialog):
    """The bookmarks found, to check before they're made: untick, rename (double-click),
    change the level, choose how many levels; replace the bookmarks or add to them."""

    def __init__(self, parent, view, items, note, depth=BA.MAX_LEVELS, sheet_scan=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Make bookmarks"))
        self.resize(640, 620)
        self.view = view
        self.items = [dict(it) for it in items]
        self.sheet_scan = sheet_scan
        self.result_toc = None
        self.replace = True
        lay = QVBoxLayout(self)
        self.note = QLabel(note)
        self.note.setWordWrap(True)
        lay.addWidget(self.note)
        row = QHBoxLayout()
        self.depth = QSpinBox()
        self.depth.setRange(1, BA.MAX_LEVELS)
        self.depth.setValue(max(1, min(BA.MAX_LEVELS, depth)))
        self.depth.valueChanged.connect(lambda _v: self._fill())
        self.group = QCheckBox(tr("Group the sheets by discipline (A - Architectural, S - "
                                  "Structural...)"))
        self.group.toggled.connect(self._regroup)
        if sheet_scan is None:
            row.addWidget(QLabel(tr("Levels:")))
            row.addWidget(self.depth)
            self.group.hide()
        else:
            self.depth.hide()
            row.addWidget(self.group)
        self.titlecase = QCheckBox(tr("Names in capitals in Title Case"))
        self.titlecase.setToolTip(tr("FIRST FLOOR PLAN becomes First Floor Plan"))
        row.addWidget(self.titlecase)
        row.addStretch(1)
        lay.addLayout(row)
        self.tree = QTreeWidget()
        self.tree.setColumnCount(2)
        self.tree.setHeaderLabels([tr("Bookmark"), tr("Page")])
        self.tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.tree.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)
        self.tree.itemChanged.connect(self._edited)
        self.tree.itemClicked.connect(self._go)
        lay.addWidget(self.tree, 1)
        row = QHBoxLayout()
        for text, tip, fn in (
                (tr("Tick all"), None, lambda: self._tick(True)),
                (tr("Untick all"), None, lambda: self._tick(False)),
                ("← " + tr("Level up"), tr("Make the selected bookmarks one level higher"),
                 lambda: self._level(-1)),
                (tr("Level down") + " →", tr("Make the selected bookmarks one level lower "
                                             "(under the one before)"), lambda: self._level(1))):
            b = QPushButton(text)
            if tip:
                b.setToolTip(tip)
            b.clicked.connect(fn)
            row.addWidget(b)
        row.addStretch(1)
        lay.addLayout(row)
        hint = QLabel(tr("Untick what shouldn't be a bookmark; double-click a name to change "
                         "it; click one to see it on its page."))
        hint.setWordWrap(True)
        hint.setStyleSheet("color: gray;")
        lay.addWidget(hint)
        self.mode_replace = QRadioButton(tr("Replace the bookmarks the document has"))
        self.mode_add = QRadioButton(tr("Add these after the bookmarks the document has"))
        self.mode_replace.setChecked(True)
        if view is not None and view.doc.get_toc():
            lay.addWidget(self.mode_replace)
            lay.addWidget(self.mode_add)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText(tr("Make bookmarks"))
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)
        self._fill()

    def _fill(self, select=()):
        depth = self.depth.value() if self.sheet_scan is None else 2
        self.tree.blockSignals(True)
        self.tree.clear()
        parents = {}
        chosen = []
        for k, it in enumerate(self.items):
            lvl = it["level"]
            if lvl > depth:
                continue
            parent = next((parents[p] for p in range(lvl - 1, 0, -1) if p in parents),
                          self.tree.invisibleRootItem())
            item = QTreeWidgetItem(parent, [it["title"], str(it["page"] + 1)])
            item.setFlags(item.flags() | Qt.ItemIsEditable | Qt.ItemIsUserCheckable)
            item.setCheckState(0, Qt.Checked if it.get("on", True) else Qt.Unchecked)
            item.setData(0, Qt.UserRole, k)
            parents[lvl] = item
            for deeper in [p for p in parents if p > lvl]:
                del parents[deeper]
            if k in select:
                chosen.append(item)
        self.tree.expandAll()
        self.tree.resizeColumnToContents(1)
        self.tree.setColumnWidth(0, max(200, self.tree.width() - 90))
        for item in chosen:
            item.setSelected(True)
        if chosen:
            self.tree.setCurrentItem(chosen[0])
        self.tree.blockSignals(False)

    def _edited(self, item, _col):
        k = item.data(0, Qt.UserRole)
        if k is None:
            return
        it = self.items[k]
        it["on"] = item.checkState(0) == Qt.Checked
        title = item.text(0).strip()
        if title:
            it["title"] = title
        else:
            self.tree.blockSignals(True)
            item.setText(0, it["title"])
            self.tree.blockSignals(False)

    def _go(self, item, _col):
        k = item.data(0, Qt.UserRole)
        if k is None or self.view is None:
            return
        it = self.items[k]
        self.view.go_to_destination(it["page"], it.get("to"))

    def _tick(self, on):
        for it in self.items:
            it["on"] = on
        self._fill()

    def _level(self, delta):
        ks = [it.data(0, Qt.UserRole) for it in self.tree.selectedItems()]
        if not ks:
            return
        depth = self.depth.value() if self.sheet_scan is None else 2
        for k in ks:
            self.items[k]["level"] = max(1, min(depth, self.items[k]["level"] + delta))
        self._fill(set(ks))

    def _regroup(self, on):
        if self.sheet_scan is not None:
            self.items = self.sheet_scan.propose(group=on)
            self._fill()

    def entries(self):
        depth = self.depth.value() if self.sheet_scan is None else 2
        return BA.toc_entries(self.items, depth, self.titlecase.isChecked())

    def _accept(self):
        toc = self.entries()
        if not toc:
            QMessageBox.information(self, tr("Make bookmarks"),
                                    tr("Nothing is ticked: tick the bookmarks to make."))
            return
        self.result_toc = toc
        self.replace = not self.mode_add.isChecked()
        self.accept()


# ---- the commands ------------------------------------------------------------------------------
SOURCES = ("headings", "tags", "sheets")


def scan_for(source, doc):
    if source == "tags":
        return BA.TaggedScan(doc)
    if source == "sheets":
        return BA.SheetScan(doc)
    return BA.HeadingScan(doc)


def _note(source, scan, items):
    n = sum(1 for it in items if it.get("on", True))
    if source == "headings":
        looks = "; ".join(tr("level {level}: {look} ({n})").format(level=lv, look=look, n=c)
                          for look, lv, c in scan.styles)
        return tr("{n} heading(s) found by their size, weight and numbering. {looks}").format(
            n=n, looks=looks)
    if source == "tags":
        return tr("{n} heading(s) found in the document's tags (H1-H6).").format(n=n)
    sheets = sum(1 for i in scan.infos if i)
    return tr("{n} sheet(s) found by their title blocks; {none} page(s) without a sheet "
              "number are left out.").format(n=sheets, none=len(scan.infos) - sheets)


def make_bookmarks(window, source, dialog_hook=None):
    """Make bookmarks from headings / tagged structure / sheet numbers (source), through
    the preview. dialog_hook(dlg): for tests, runs the dialog instead of exec(). Returns the
    number of bookmarks made (None when stopped)."""
    v = window.view()
    if v is None:
        return None
    v.commit_pending()
    doc = v.doc
    titles = {"headings": tr("Make bookmarks from headings"),
              "tags": tr("Bookmarks from tagged structure"),
              "sheets": tr("Bookmarks from sheet numbers")}
    if source == "tags" and not BA.struct_root(doc):
        QMessageBox.information(window, titles[source],
                                tr("This PDF isn't tagged: it has no structure to read the "
                                   "headings from. Use Make bookmarks from headings, which "
                                   "finds them by their look."))
        return None
    scan = scan_for(source, doc)
    count = doc.page_count
    texts = {"headings": tr("Reading the headings..."), "tags": tr("Reading the tags..."),
             "sheets": tr("Reading sheet numbers...")}
    if not run_sliced(window, titles[source], texts[source], scan.run(),
                      lambda: getattr(scan, "total", 0) if source == "tags" else count):
        window.statusBar().showMessage(tr("Stopped: no bookmarks were made"), 4000)
        return None
    items = scan.propose()
    if not items and source == "headings" and not scan.rows:
        QMessageBox.information(window, titles[source],
                                tr("This document has no text to find headings in (scanned "
                                   "pages: run Recognize text (OCR) first)."))
        return None
    if not items:
        msg = {"headings": tr("No headings were found: the text is all the same size and "
                              "weight, with no numbered headings."),
               "tags": tr("The tags have no headings (H1-H6)."),
               "sheets": tr("No sheet numbers were found in title blocks.")}[source]
        QMessageBox.information(window, titles[source], msg)
        return None
    depth = BA.MAX_LEVELS
    if source == "headings":
        depth = min(BA.MAX_LEVELS, max(1, len(scan.styles)))
    dlg = PreviewDialog(window, v, items, _note(source, scan, items), depth,
                        sheet_scan=scan if source == "sheets" else None)
    dlg.setWindowTitle(titles[source])
    accepted = dialog_hook(dlg) if dialog_hook is not None else dlg.exec() == QDialog.Accepted
    if not accepted or not dlg.result_toc:
        return None
    toc = BA.combined(doc, dlg.result_toc, dlg.replace)
    if not v.modify(lambda: doc.set_toc(toc), []):
        return None
    v.documentChanged.emit()
    window._refresh_bookmarks()
    window._show_bookmarks()
    n = len(dlg.result_toc)
    window.statusBar().showMessage(tr("{n} bookmark(s) made (Ctrl+Z undoes it)").format(n=n), 6000)
    return n


class TocDialog(QDialog):
    """Insert table of contents: title, levels, where, page size."""

    def __init__(self, parent, view):
        super().__init__(parent)
        self.setWindowTitle(tr("Insert table of contents"))
        doc = view.doc
        self.old = BA.toc_pages(doc)
        before = BA.toc_settings(doc, self.old)
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.title = QLineEdit(before.get("title", tr("Contents")))
        form.addRow(tr("Title:"), self.title)
        self.depth = QSpinBox()
        self.depth.setRange(1, BA.MAX_LEVELS)
        self.depth.setValue(before.get("depth", BA.MAX_LEVELS))
        form.addRow(tr("Levels:"), self.depth)
        self.size = QComboBox()
        self.size.addItem(tr("The size of the page it goes before"), None)
        self.size.addItem(tr("Letter (8.5 x 11 in)"), (612.0, 792.0))
        self.size.addItem(tr("A4 (210 x 297 mm)"), (595.0, 842.0))
        form.addRow(tr("Page size:"), self.size)
        lay.addLayout(form)
        cur = view.current_page()
        self.at_start = QRadioButton(tr("At the start of the document"))
        self.at_current = QRadioButton(tr("Before the current page (page {page})").format(page=cur + 1))
        self.at_old = QRadioButton(tr("In place of the table of contents made before (pages "
                                      "{first}-{last})").format(first=self.old[0] + 1,
                                                                last=self.old[-1] + 1)
                                   if self.old else "")
        lay.addWidget(self.at_start)
        lay.addWidget(self.at_current)
        if self.old:
            lay.addWidget(self.at_old)
            self.at_old.setChecked(True)
        else:
            self.at_old.hide()
            self.at_start.setChecked(True)
        self.current = cur
        note = QLabel(tr("Each line links to its page; the page numbers count the new pages. "
                         "Bookmarks that go elsewhere (a web page, another file) are left out."))
        note.setWordWrap(True)
        note.setStyleSheet("color: gray;")
        lay.addWidget(note)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText(tr("Insert"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def choice(self):
        """{"at", "title", "depth", "size", "replace"} for bookmarks_auto.insert_toc."""
        replace = bool(self.old) and self.at_old.isChecked()
        at = 0 if self.at_start.isChecked() else self.current
        return {"at": at, "title": self.title.text().strip(), "depth": self.depth.value(),
                "size": self.size.currentData(), "replace": replace}


def insert_toc(window, dialog_hook=None):
    """Insert table of contents: pages listing the bookmarks, with links, as one undo step.
    dialog_hook(dlg): for tests. Returns (first page, page count) or None."""
    v = window.view()
    if v is None:
        return None
    v.commit_pending()
    if not v.doc.get_toc():
        QMessageBox.information(window, tr("Insert table of contents"),
                                tr("This document has no bookmarks to list. Make them first "
                                   "(Document > Bookmark tools > Make bookmarks from "
                                   "headings...), or add them in the Bookmarks panel."))
        return None
    dlg = TocDialog(window, v)
    accepted = dialog_hook(dlg) if dialog_hook is not None else dlg.exec() == QDialog.Accepted
    if not accepted:
        return None
    c = dlg.choice()
    if not BA.toc_list(v.doc, c["depth"], c["replace"]):
        QMessageBox.information(window, tr("Insert table of contents"),
                                tr("None of the bookmarks goes to a page of this document."))
        return None
    if hasattr(window, "_pages_unlocked") and not window._pages_unlocked():
        return None
    out = {}

    def do():
        out["r"] = BA.insert_toc(v.doc, c["at"], c["title"], c["depth"], c["size"],
                                 c["replace"])
    if not v.modify(do, structural=True, changed=[]) or not out.get("r"):
        return None
    first, n = out["r"]
    v.goto_page(first)
    window.statusBar().showMessage(
        tr("Table of contents inserted: {n} page(s) from page {page} (Ctrl+Z undoes it)").format(
            n=n, page=first + 1), 6000)
    return out["r"]

