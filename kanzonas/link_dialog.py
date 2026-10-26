"""The link window (Links tool, right-click > Add link... / Edit link...): where a link goes
(a web address or a page of this document), how it looks, the text it writes on the page when
it brings its own, and Delete link when editing one."""

import re

from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                               QGridLayout, QLabel, QLineEdit, QRadioButton, QSpinBox,
                               QVBoxLayout)


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


LOOK_LABELS = (("underline", "Underline (drawn into the page)"),
               ("box", "Box around it"),
               ("none", "Nothing (the pointer still shows it)"))


def look_of(value):
    """A look from a target's third item: old targets used True / False for the box."""
    if value is True:
        return "box"
    if value is False or value is None:
        return "none"
    return value if value in ("underline", "box", "none") else "box"


class LinkDialog(QDialog):
    """result: ("uri", address, look, text) | ("page", 0-based index, look, text) |
    ("delete",) | None. look: "underline", "box" or "none". text: the link's own words to
    write into the page, or None.

    current: the link being changed (kind, value, look[, text]). text_choice: offer
    "Text to show" ({"text": words, "write": ticked at first}), or None."""

    def __init__(self, parent, page_count, current=None, text_choice=None, look="box"):
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
        cur = tuple(current or ("uri", "")) + (None, None)
        kind, value = cur[0], cur[1]
        chosen = look_of(cur[2]) if current and len(current) > 2 else look
        self.look = QComboBox()
        for key, label in LOOK_LABELS:
            self.look.addItem(label, key)
        self.look.setCurrentIndex(max(0, self.look.findData(chosen)))
        self.look.setToolTip("How readers see that it's a link. With Nothing, it shows only when "
                             "the pointer is over it.")
        grid.addWidget(QLabel("Look:"), 2, 0)
        grid.addWidget(self.look, 2, 1)
        self.text = None
        self.write = None
        self._text_edited = False
        if text_choice is not None:
            self.write = QCheckBox("Write this text on the page:")
            self.write.setChecked(bool(text_choice.get("write")))
            self.text = QLineEdit(text_choice.get("text") or "")
            self.text.setPlaceholderText("the address, or your own words")
            self._text_edited = bool(text_choice.get("text"))
            self.text.textEdited.connect(self._own_text)
            self.write.toggled.connect(self.text.setEnabled)
            self.text.setEnabled(self.write.isChecked())
            grid.addWidget(self.write, 3, 0)
            grid.addWidget(self.text, 3, 1)
        if kind == "page":
            self.to_page.setChecked(True)
            self.page.setValue(value + 1)
        else:
            self.web.setChecked(True)
            self.url.setText(value)
        self.url.textEdited.connect(self._address_typed)
        self.page.valueChanged.connect(self._page_chosen)
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
        self.resize(480, self.sizeHint().height())

    # the text to show follows the address until you type your own
    def _own_text(self, _t):
        self._text_edited = bool(self.text.text())

    def _address_typed(self, t):
        self.web.setChecked(True)
        if self.text is not None and not self._text_edited:
            self.text.setText(t.strip())

    def _page_chosen(self, n):
        self.to_page.setChecked(True)
        if self.text is not None and not self._text_edited:
            self.text.setText(f"Page {n}")

    def _ok(self):
        look = self.look.currentData()
        words = None
        if self.write is not None and self.write.isChecked():
            # left empty: the address itself (or "Page 3") is the text
            words = " ".join(self.text.text().split()) or (
                f"Page {self.page.value()}" if self.to_page.isChecked()
                else self.url.text().strip())
        if self.to_page.isChecked():
            self.result_value = ("page", self.page.value() - 1, look, words)
        else:
            url = normalize_url(self.url.text())
            if not url:
                self.error.setText("Type a web address, or choose a page.")
                return
            self.result_value = ("uri", url, look, words)
        self.accept()

    def _delete(self):
        self.result_value = ("delete",)
        self.accept()
