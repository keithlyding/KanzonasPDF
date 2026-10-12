"""Edit > Replace text (Ctrl+H): find text in the page itself and replace it, on this page
or in the whole document. Each changed line is rewritten like Edit text does it."""

import re

from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
                               QLabel, QLineEdit, QVBoxLayout)


def pattern(find, match_case=False, whole_words=False):
    p = re.escape(find)
    if whole_words:
        p = r"(?<!\w)" + p + r"(?!\w)"
    return re.compile(p, 0 if match_case else re.IGNORECASE)


class ReplaceDialog(QDialog):
    def __init__(self, parent, view, find=""):
        super().__init__(parent)
        self.view = view
        self.setWindowTitle("Replace text")
        form = QFormLayout()
        self.find = QLineEdit(find)
        self.repl = QLineEdit()
        self.case = QCheckBox("Match case")
        self.whole = QCheckBox("Whole words only")
        self.scope = QComboBox()
        self.scope.addItems(["All pages", f"This page ({view.current_page() + 1})"])
        form.addRow("Find", self.find)
        form.addRow("Replace with", self.repl)
        form.addRow("", self.case)
        form.addRow("", self.whole)
        form.addRow("In", self.scope)
        self.note = QLabel("Each line that changes is rewritten in its own font when it has "
                           "the characters (like Edit text). Ctrl+Z undoes it all.")
        self.note.setWordWrap(True)
        self.note.setStyleSheet("color: gray;")
        self.result = QLabel()
        self.result.setWordWrap(True)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        self.go = buttons.addButton("Replace all", QDialogButtonBox.ActionRole)
        self.go.setDefault(True)
        self.go.clicked.connect(self.replace_all)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(self.note)
        lay.addWidget(self.result)
        lay.addWidget(buttons)
        self.find.textChanged.connect(lambda t: self.go.setEnabled(bool(t)))
        self.go.setEnabled(bool(find))
        self.resize(420, self.sizeHint().height())

    def replace_all(self):
        v = self.view
        pages = None if self.scope.currentIndex() == 0 else [v.current_page()]
        found, lines, skipped = v.replace_text(self.find.text(), self.repl.text(),
                                               self.case.isChecked(), self.whole.isChecked(),
                                               pages)
        msg = (f"Replaced {found} match{'es' if found != 1 else ''} in {lines} "
               f"line{'s' if lines != 1 else ''}." if found else "Not found.")
        if skipped:
            msg += " Skipped page " + ", ".join(str(i + 1) for i in skipped) + \
                   " (pending redaction marks: apply or remove them first)."
        self.result.setText(msg)
