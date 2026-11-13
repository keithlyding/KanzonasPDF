"""Pages > Replace pages...: which pages take the drawings of which pages of the new revision
(by page numbers, or matched by the sheet numbers in the title blocks, reviewed in a list),
and what markups do on a page whose size changes."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QGridLayout, QLabel, QLineEdit,
                               QRadioButton, QButtonGroup, QTableWidget, QTableWidgetItem,
                               QHeaderView, QDialogButtonBox, QAbstractItemView, QGroupBox,
                               QProgressDialog, QApplication)

from . import replace_pages
from .i18n import tr


class _Stop(Exception):
    pass


class ReplacePagesDialog(QDialog):
    def __init__(self, parent, doc, src, name, current=0):
        super().__init__(parent)
        self.setWindowTitle(tr("Replace pages"))
        self.doc, self.src = doc, src
        self.result_pairs = None
        self._match = None
        self._filling = False
        self.resize(700, 560)
        n, k = doc.page_count, src.page_count
        lay = QVBoxLayout(self)
        intro = QLabel(tr("Replace the drawings of pages here with pages of {name} ({n} "
                          "page(s)). Each page keeps its markups, links, form fields and "
                          "bookmarks: only what is drawn on it changes.").format(name=name, n=k))
        intro.setWordWrap(True)
        lay.addWidget(intro)

        self.by_numbers = QRadioButton(tr("By page numbers"))
        self.by_sheets = QRadioButton(tr("Match sheets by sheet number"))
        group = QButtonGroup(self)
        group.addButton(self.by_numbers)
        group.addButton(self.by_sheets)
        lay.addWidget(self.by_numbers)
        grid = QGridLayout()
        grid.setContentsMargins(24, 0, 0, 0)
        self.here = QLineEdit(f"1-{n}" if n == k else str(current + 1))
        self.new = QLineEdit(f"1-{k}" if n == k else "1")
        for w in (self.here, self.new):
            w.setPlaceholderText(tr("e.g. 1-3, 5"))
        grid.addWidget(QLabel(tr("Replace pages (1-{n}):").format(n=n)), 0, 0)
        grid.addWidget(self.here, 0, 1)
        grid.addWidget(QLabel(tr("with pages of the new file (1-{n}):").format(n=k)), 1, 0)
        grid.addWidget(self.new, 1, 1)
        lay.addLayout(grid)

        lay.addWidget(self.by_sheets)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels([tr("Page"), tr("Sheet number"),
                                              tr("Replaced by page"), tr("New sheet number"),
                                              tr("New title")])
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.table.verticalHeader().hide()
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setToolTip(tr("Correct a match by typing the page of the new file in "
                                 "“Replaced by page”; leave it empty to keep the page "
                                 "as it is."))
        lay.addWidget(self.table, 1)
        self.unmatched = QLabel("")
        self.unmatched.setWordWrap(True)
        lay.addWidget(self.unmatched)

        box = QGroupBox(tr("Markups on a page whose size changes"))
        bl = QVBoxLayout(box)
        self.scale = QRadioButton(tr("Scale them to the new page"))
        self.keep = QRadioButton(tr("Keep them at the same place (measured from the top-left "
                                    "corner)"))
        self.scale.setChecked(True)
        bl.addWidget(self.scale)
        bl.addWidget(self.keep)
        lay.addWidget(box)
        self.size_box = box

        self.summary = QLabel("")
        self.summary.setWordWrap(True)
        lay.addWidget(self.summary)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.ok = btns.button(QDialogButtonBox.Ok)
        self.ok.setText(tr("Replace"))
        btns.accepted.connect(self._accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

        self.by_numbers.setChecked(True)
        self.by_numbers.toggled.connect(self._mode)
        self.here.textChanged.connect(lambda _t: self._preview())
        self.new.textChanged.connect(lambda _t: self._preview())
        self.table.itemChanged.connect(self._edited)
        self._mode()

    # ---- the pages paired ---------------------------------------------------------------
    def pairs(self):
        """[(page index here, page index in the new file)]; ValueError with what's wrong."""
        if self.by_numbers.isChecked():
            return replace_pages.pairs_by_numbers(self.here.text(), self.new.text(),
                                                  self.doc.page_count, self.src.page_count)
        out = []
        for row in range(self.table.rowCount()):
            text = self.table.item(row, 2).text().strip()
            if not text:
                continue
            try:
                j = int(text) - 1
            except ValueError:
                j = -1
            if not 0 <= j < self.src.page_count:
                raise ValueError(tr("Page {page}: the new file has no page {n}.").format(
                    page=row + 1, n=text))
            out.append((row, j))
        return out

    def _mode(self):
        sheets = self.by_sheets.isChecked()
        self.here.setEnabled(not sheets)
        self.new.setEnabled(not sheets)
        self.table.setEnabled(sheets)
        if sheets and self._match is None:
            self._scan()
        self._preview()

    def _scan(self):
        """Read the sheet numbers of both documents (a progress bar: big sets take a while)."""
        total = self.doc.page_count + self.src.page_count
        dlg = QProgressDialog(tr("Reading sheet numbers..."), tr("Cancel"), 0, total, self)
        dlg.setWindowModality(Qt.WindowModal)
        dlg.setMinimumDuration(400)
        done = [0]

        def step():
            done[0] += 1
            dlg.setValue(done[0])
            QApplication.processEvents()
            if dlg.wasCanceled():
                raise _Stop()
        try:
            self._match = replace_pages.match_sheets(self.doc, self.src, step)
        except _Stop:
            self._match = None
            dlg.close()
            self.by_numbers.setChecked(True)
            return
        dlg.close()
        self._fill()

    def _fill(self):
        mt = self._match
        self._filling = True
        self.table.setRowCount(self.doc.page_count)
        for i, info in enumerate(mt["here"]):
            j = mt["pairs"].get(i)
            cells = [str(i + 1), info["number"] if info else "",
                     "" if j is None else str(j + 1), "", ""]
            for c, text in enumerate(cells):
                it = QTableWidgetItem(text)
                if c != 2:
                    it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(i, c, it)
            self._show_new(i)
        self._filling = False
        self.table.resizeColumnsToContents()

    def _show_new(self, row):
        """The new sheet's number and title beside the page typed in Replaced by page."""
        text = self.table.item(row, 2).text().strip()
        info, bad = None, False
        if text:
            try:
                j = int(text) - 1
                bad = not 0 <= j < self.src.page_count
                info = None if bad else self._match["new"][j]
            except ValueError:
                bad = True
        self.table.item(row, 3).setText(info["number"] if info else "")
        self.table.item(row, 4).setText((info or {}).get("title") or "")
        self.table.item(row, 2).setForeground(QBrush(QColor("#c00000")) if bad else QBrush())

    def _edited(self, item):
        if self._filling or item.column() != 2:
            return
        self._filling = True
        self._show_new(item.row())
        self._filling = False
        self._preview()

    def _preview(self):
        self.unmatched.setText("")
        if self.by_sheets.isChecked() and self._match is not None:
            used = set()
            for row in range(self.table.rowCount()):
                try:
                    used.add(int(self.table.item(row, 2).text()) - 1)
                except ValueError:
                    pass  # (not a page number: not counted)
            left = [(j, info) for j, info in enumerate(self._match["new"]) if j not in used]
            if left:
                names = [(info["number"] if info else tr("page {n}").format(n=j + 1))
                         for j, info in left]
                text = ", ".join(names[:12]) + ("..." if len(names) > 12 else "")
                self.unmatched.setText(tr("In the new file but matching no page here (not "
                                          "used): {names}").format(names=text))
        try:
            pairs = self.pairs()
        except ValueError as ex:
            self.summary.setText(str(ex))
            self.ok.setEnabled(False)
            self.size_box.setEnabled(False)
            return
        differ = replace_pages.sizes_differ(self.doc, self.src, pairs)
        self.size_box.setEnabled(bool(differ))
        if not pairs:
            text = tr("No page will be replaced.")
        else:
            text = tr("{n} page(s) will be replaced.").format(n=len(pairs))
            if differ:
                text += " " + tr("{n} of them change size.").format(n=len(differ))
        self.summary.setText(text)
        self.ok.setEnabled(bool(pairs))

    def _accept(self):
        try:
            self.result_pairs = self.pairs()
        except ValueError:
            return
        if self.result_pairs:
            self.accept()

    def scaled(self):
        return self.scale.isChecked()
