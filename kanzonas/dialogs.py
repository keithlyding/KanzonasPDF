"""Small reusable dialogs."""

from PySide6.QtCore import Qt, QEvent
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QLabel, QPlainTextEdit,
                               QDialogButtonBox)


class TextDialog(QDialog):
    """Multi-line text entry. Ctrl+Enter = OK, Esc = Cancel, Enter = new line."""

    def __init__(self, parent, title, label, text=""):
        super().__init__(parent)
        self.setWindowTitle(title)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(label))
        self.edit = QPlainTextEdit(text)
        self.edit.installEventFilter(self)
        self.edit.selectAll()
        lay.addWidget(self.edit)
        hint = QLabel("Ctrl+Enter to finish")
        hint.setStyleSheet("color: gray;")
        lay.addWidget(hint)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)
        self.resize(420, 220)

    def eventFilter(self, obj, event):
        if (obj is self.edit and event.type() == QEvent.KeyPress
                and event.key() in (Qt.Key_Return, Qt.Key_Enter)
                and event.modifiers() & Qt.ControlModifier):
            self.accept()
            return True
        return super().eventFilter(obj, event)


def get_text(parent, title, label, text=""):
    """Returns (text, ok) like QInputDialog.getMultiLineText."""
    dlg = TextDialog(parent, title, label, text)
    ok = dlg.exec() == QDialog.Accepted
    return dlg.edit.toPlainText(), ok
