"""Document > Compare documents...: which way to compare, once the earlier revision is
picked. Text mode for documents that reflow, overlay mode for drawings."""

from PySide6.QtWidgets import (QDialog, QVBoxLayout, QLabel, QRadioButton, QDialogButtonBox)


class CompareModeDialog(QDialog):
    def __init__(self, parent, old_name, new_name, text_default):
        super().__init__(parent)
        self.setWindowTitle("Compare documents")
        lay = QVBoxLayout(self)
        intro = QLabel(f"Comparing <b>{new_name}</b> (this document) with <b>{old_name}</b> "
                       "(the earlier revision). How?")
        intro.setWordWrap(True)
        lay.addWidget(intro)
        self.r_text = QRadioButton("Text, word by word")
        text_note = QLabel("For letters, specifications, permits, anything that reflows: words "
                           "added in this document are highlighted blue, a red mark shows where "
                           "words of the earlier one were removed, and pictures that came, went "
                           "or changed size are boxed. Text that only moved is not a change. "
                           "Each change is listed in the Markups list and on a summary page "
                           "at the end.")
        self.r_overlay = QRadioButton("Drawings, laid over each other")
        over_note = QLabel("For plans and sheets: the two pages are overlaid (red = only in the "
                           "earlier revision, blue = only in this one, gray = unchanged) and "
                           "every area that differs is clouded. A drawing that moved on the "
                           "sheet or was printed at another paper size is lined up first.")
        for note in (text_note, over_note):
            note.setWordWrap(True)
            note.setStyleSheet("color: gray; margin-left: 22px;")
        lay.addWidget(self.r_text)
        lay.addWidget(text_note)
        lay.addWidget(self.r_overlay)
        lay.addWidget(over_note)
        (self.r_text if text_default else self.r_overlay).setChecked(True)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.button(QDialogButtonBox.Ok).setText("Compare")
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)
        self.resize(520, 320)

    def mode(self):
        return "text" if self.r_text.isChecked() else "overlay"
