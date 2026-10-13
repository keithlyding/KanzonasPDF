"""The Links tool's window: where a link goes (a web address or a page of this document),
and Delete link when editing one."""

import re

from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QDialog, QDialogButtonBox, QGridLayout, QLabel,
                               QLineEdit, QRadioButton, QSpinBox, QVBoxLayout)


def normalize_url(text):
    """What was typed -> a link address: 'www.x.com' -> 'https://www.x.com', an e-mail
    address -> 'mailto:...'. Returns '' for nothing usable."""
    t = text.strip()
    if not t:
        return ""
    if re.match(r"^[a-z][a-z0-9+.-]*:", t, re.IGNORECASE):
        return t
    if re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", t):
        return "mailto:" + t
    return "https://" + t


class LinkDialog(QDialog):
    """result: ("uri", address, show box) | ("page", 0-based index, show box) |
    ("delete",) | None."""

    def __init__(self, parent, page_count, current=None):
        super().__init__(parent)
        self.setWindowTitle("Edit link" if current else "Add link")
        self.result_value = None
        self.web = QRadioButton("Web address or e-mail")
        self.url = QLineEdit()
        self.url.setPlaceholderText("www.example.com")
        self.to_page = QRadioButton("Page in this document")
        self.page = QSpinBox()
        self.page.setRange(1, max(1, page_count))
        group = QButtonGroup(self)
        group.addButton(self.web)
        group.addButton(self.to_page)
        grid = QGridLayout()
        grid.addWidget(self.web, 0, 0)
        grid.addWidget(self.url, 0, 1)
        grid.addWidget(self.to_page, 1, 0)
        grid.addWidget(self.page, 1, 1)
        kind, value, shown = (tuple(current or ("uri", "")) + (True,))[:3]
        self.show_box = QCheckBox("Show a box around the link")
        self.show_box.setToolTip("Without it, the link is invisible until the pointer is over it")
        self.show_box.setChecked(bool(shown))
        grid.addWidget(self.show_box, 2, 0, 1, 2)
        if kind == "page":
            self.to_page.setChecked(True)
            self.page.setValue(value + 1)
        else:
            self.web.setChecked(True)
            self.url.setText(value)
        self.url.textEdited.connect(lambda _t: self.web.setChecked(True))
        self.page.valueChanged.connect(lambda _v: self.to_page.setChecked(True))
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        if current:
            delete = buttons.addButton("Delete link", QDialogButtonBox.DestructiveRole)
            delete.clicked.connect(self._delete)
        buttons.accepted.connect(self._ok)
        buttons.rejected.connect(self.reject)
        self.error = QLabel()
        self.error.setStyleSheet("color: #c00000;")
        lay = QVBoxLayout(self)
        lay.addLayout(grid)
        lay.addWidget(self.error)
        lay.addWidget(buttons)
        self.resize(440, self.sizeHint().height())

    def _ok(self):
        if self.to_page.isChecked():
            self.result_value = ("page", self.page.value() - 1, self.show_box.isChecked())
        else:
            url = normalize_url(self.url.text())
            if not url:
                self.error.setText("Type a web address, or choose a page.")
                return
            self.result_value = ("uri", url, self.show_box.isChecked())
        self.accept()

    def _delete(self):
        self.result_value = ("delete",)
        self.accept()
