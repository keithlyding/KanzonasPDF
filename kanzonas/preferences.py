"""File > Preferences (Ctrl+K): the remembered options in one place.

Every checkbox is tied to the menu command that already does the job, so changing an option
here or in its menu does the same thing and both always agree."""

from PySide6.QtWidgets import (QDialog, QVBoxLayout, QTabWidget, QWidget, QCheckBox, QComboBox,
                               QFormLayout, QLabel, QPushButton, QDialogButtonBox)


def _plain(text):
    return text.replace("&&", "\0").replace("&", "").replace("\0", "&")


class PreferencesDialog(QDialog):
    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.setWindowTitle("Preferences")
        self.resize(520, 420)
        self._boxes = []            # (QCheckBox, QAction)
        lay = QVBoxLayout(self)
        tabs = QTabWidget()
        lay.addWidget(tabs)

        # General
        page, form = self._tab(tabs, "General")
        self.theme = QComboBox()
        for key, label in (("system", "Match Windows"), ("light", "Light"), ("dark", "Dark")):
            self.theme.addItem(label, key)
        current = next((k for k, a in win.theme_actions.items() if a.isChecked()), "system")
        self.theme.setCurrentIndex(max(0, self.theme.findData(current)))
        form.addRow("Theme:", self.theme)
        for a in (win.a_ribbon, win.a_group_names, win.a_menu_bar, win.a_labels,
                  win.a_auto_updates):
            self._box(form, a)
        from . import paths
        where = ("the data folder next to KanzonasPDF.exe (portable)" if paths.is_portable()
                 else "your Windows user profile")
        note = QLabel("Settings are saved in " + where + ".")
        note.setWordWrap(True)
        form.addRow(note)

        # Mouse and scrolling
        page, form = self._tab(tabs, "Mouse and scrolling")
        for a in (win.a_cad_mouse, win.a_page_wheel):
            self._box(form, a)

        # Pages and display
        page, form = self._tab(tabs, "Pages and display")
        self.lock = QCheckBox("Lock the page order (Pages panel)")
        self.lock.setToolTip(win.lock_btn.toolTip())
        self.lock.setChecked(win.lock_btn.isChecked())
        form.addRow(self.lock)
        for a in (win.a_cards, win.a_hl_fields, win.a_grid, win.a_snap_grid, win.a_snap_objects):
            self._box(form, a)
        grid = QPushButton("Grid settings...")
        grid.clicked.connect(win.grid_settings)
        form.addRow(grid)

        # OCR
        page, form = self._tab(tabs, "OCR")
        from . import ocr as ocrmod
        self.ocr = QComboBox()
        for key in ("auto", "fast", "normal", "high"):
            self.ocr.addItem(ocrmod.ACCURACY_LABELS[key], key)
        self.ocr.setCurrentIndex(max(0, self.ocr.findData(
            win.settings.value("ocr_accuracy", "auto"))))
        form.addRow("Default accuracy:", self.ocr)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._ok)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def _tab(self, tabs, title):
        page = QWidget()
        form = QFormLayout(page)
        tabs.addTab(page, title)
        return page, form

    def _box(self, form, action):
        b = QCheckBox(_plain(action.text()))
        b.setToolTip(action.toolTip() if action.toolTip() != _plain(action.text()) else "")
        b.setChecked(action.isChecked())
        form.addRow(b)
        self._boxes.append((b, action))

    def _ok(self):
        win = self.win
        key = self.theme.currentData()
        if not win.theme_actions[key].isChecked():
            win.theme_actions[key].setChecked(True)
            win.set_theme(key)
        for b, a in self._boxes:
            if b.isChecked() != a.isChecked():
                a.trigger()             # toggles it and runs its command, as the menu does
        if self.lock.isChecked() != win.lock_btn.isChecked():
            win.lock_btn.setChecked(self.lock.isChecked())
        win.settings.setValue("ocr_accuracy", self.ocr.currentData())
        self.accept()
