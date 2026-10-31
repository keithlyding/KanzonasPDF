"""Edit > Replace text (Ctrl+H): find text in the page itself and replace it, on this page
or in the whole document. Each changed line is rewritten like Edit text does it."""

import re

from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
                               QLabel, QLineEdit, QVBoxLayout)

from .i18n import tr


def pattern(find, match_case=False, whole_words=False):
    p = re.escape(find)
    if whole_words:
        p = r"(?<!\w)" + p + r"(?!\w)"
    return re.compile(p, 0 if match_case else re.IGNORECASE)


class ReplaceDialog(QDialog):
    def __init__(self, parent, view, find=""):
        super().__init__(parent)
        self.view = view
        self.setWindowTitle(tr("Replace text"))
        form = QFormLayout()
        self.find = QLineEdit(find)
        self.repl = QLineEdit()
        self.case = QCheckBox(tr("Match case"))
        self.whole = QCheckBox(tr("Whole words only"))
        self.scope = QComboBox()
        self.scope.addItems([tr("All pages"),
                             tr("This page ({n})").format(n=view.current_page() + 1)])
        form.addRow(tr("Find"), self.find)
        form.addRow(tr("Replace with"), self.repl)
        form.addRow("", self.case)
        form.addRow("", self.whole)
        form.addRow(tr("In"), self.scope)
        self.note = QLabel(tr("Each line that changes is rewritten in its own font when it "
                              "has the characters (like Edit text). Ctrl+Z undoes it all."))
        self.note.setWordWrap(True)
        self.note.setStyleSheet("color: gray;")
        self.result = QLabel()
        self.result.setWordWrap(True)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        self.go = buttons.addButton(tr("Replace all"), QDialogButtonBox.ActionRole)
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
        if found:
            msg = tr("Replaced {matches} in {lines}.").format(
                matches=tr("1 match") if found == 1 else tr("{n} matches").format(n=found),
                lines=tr("1 line") if lines == 1 else tr("{n} lines").format(n=lines))
        else:
            msg = tr("Not found.")
        if skipped:
            msg += " " + tr("Skipped page {pages} (pending redaction marks: apply or remove "
                            "them first).").format(pages=", ".join(str(i + 1) for i in skipped))
        if found and v.replace_overruns:
            msg += " " + tr("On page {pages} the new text runs into other text or past the "
                            "edge of the page (Ctrl+Z undoes it).").format(
                                pages=", ".join(str(i + 1) for i in v.replace_overruns))
        self.result.setText(msg)
