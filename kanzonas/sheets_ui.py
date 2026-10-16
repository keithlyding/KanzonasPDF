"""Pages > Link sheet callouts...: what was read from the title blocks (editable), what will
be linked, and the options; OK creates the links."""

import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QLabel, QTableWidget, QTableWidgetItem,
                               QHeaderView, QCheckBox, QDialogButtonBox, QAbstractItemView)

from . import sheets


class SheetLinksDialog(QDialog):
    def __init__(self, parent, doc, folder):
        super().__init__(parent)
        self.setWindowTitle("Link sheet callouts")
        self.doc = doc
        self.folder = folder
        self.result_plan = None
        self.resize(640, 480)
        lay = QVBoxLayout(self)
        intro = QLabel("Sheet numbers read from the title blocks. Correct one by clicking it "
                       "(leave it empty for a page that isn't a sheet). Every callout, note or "
                       "index line naming one of these sheets becomes a link to its page.")
        intro.setWordWrap(True)
        lay.addWidget(intro)
        self.table = QTableWidget(doc.page_count, 3)
        self.table.setHorizontalHeaderLabels(["Page", "Sheet number", "Title"])
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.verticalHeader().hide()
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        infos = sheets.scan(doc)
        for i, info in enumerate(infos):
            page = QTableWidgetItem(str(i + 1))
            page.setFlags(page.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(i, 0, page)
            self.table.setItem(i, 1, QTableWidgetItem(info["number"] if info else ""))
            title = QTableWidgetItem((info or {}).get("title") or "")
            title.setFlags(title.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(i, 2, title)
        self.table.resizeColumnsToContents()
        lay.addWidget(self.table)
        self.files = QCheckBox("Also link callouts to other PDFs in the same folder, named by "
                               "sheet number (A-501 Details.pdf)")
        self.files.setChecked(bool(folder))
        self.files.setEnabled(bool(folder))
        self.box = QCheckBox("Show a thin blue box around each link")
        self.box.setChecked(False)
        has_toc = bool(doc.get_toc())
        self.marks = QCheckBox("Add bookmarks for the sheets (number and title)"
                               + ("  (the document already has bookmarks: they would be replaced)"
                                  if has_toc else ""))
        self.marks.setChecked(not has_toc)
        for w in (self.files, self.box, self.marks):
            lay.addWidget(w)
        self.summary = QLabel("")
        self.summary.setWordWrap(True)
        lay.addWidget(self.summary)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.button(QDialogButtonBox.Ok).setText("Create links")
        btns.accepted.connect(self._accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)
        self.table.itemChanged.connect(lambda _it: self._preview())
        self.files.toggled.connect(lambda _on: self._preview())
        self._preview()

    def numbers(self):
        return {i: self.table.item(i, 1).text().strip() for i in range(self.table.rowCount())}

    def _plan(self):
        return sheets.plan(self.doc, self.numbers(),
                           self.folder if self.files.isChecked() else None)

    def _preview(self):
        try:
            pl = self._plan()
        except Exception as ex:                  # an odd page must not block the dialog
            self.summary.setText(f"Could not read the pages: {ex}")
            return
        n_pages = len(pl["pages"])
        n_links = len(pl["links"])
        ext = sum(1 for _i, _r, t in pl["links"] if t[0] == "file")
        text = f"{n_pages} sheet(s) found; {n_links} callout(s) will be linked"
        if ext:
            text += f", {ext} of them to {len(pl['external'])} other PDF(s) in the folder"
        text += "."
        if pl["missing"]:
            names = sorted(pl["missing"], key=lambda k: -pl["missing"][k])[:8]
            text += (" Not linked (no such sheet here or in the folder): " + ", ".join(names)
                     + ("..." if len(pl["missing"]) > 8 else ""))
        self.summary.setText(text)

    def _accept(self):
        self.result_plan = self._plan()
        self.accept()
