"""File > Preferences (Ctrl+K): the remembered options in one place.

Every checkbox is tied to the menu command that already does the job, so changing an option
here or in its menu does the same thing and both always agree."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget,
                               QCheckBox, QComboBox, QFormLayout, QLabel, QPushButton,
                               QDialogButtonBox, QLineEdit, QListWidget, QListWidgetItem)


def _plain(text):
    return text.replace("&&", "\0").replace("&", "").replace("\0", "&")


class PreferencesDialog(QDialog):
    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.setWindowTitle("Preferences")
        self.resize(640, 560)
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

        # You: name on markups, signature and initials
        from . import annotations
        page, form = self._tab(tabs, "You")
        self.author = QLineEdit(annotations.author())
        self.author.setToolTip("Recorded on new markups and shown on stamps (Edit > Author name "
                               "for markups)")
        form.addRow("Author name for markups:", self.author)
        self._sig_rows = {}
        for kind, action in (("signature", win.a_setup_sig), ("initials", win.a_setup_init)):
            row = QHBoxLayout()
            status = QLabel()
            btn = QPushButton(_plain(action.text()))
            btn.clicked.connect(lambda _=False, k=kind: self._setup_sig(k))
            row.addWidget(status, 1)
            row.addWidget(btn)
            form.addRow("Your " + kind + ":", row)
            self._sig_rows[kind] = status
        self._sig_status()
        hint = QLabel("Your signature and initials are kept on this computer only (in the data "
                      "folder in portable mode), protected by your PIN if you set one.")
        hint.setWordWrap(True)
        form.addRow(hint)

        # Markup styles: each tool's default colors and formats
        page = QWidget()
        tabs.addTab(page, "Markup styles")
        row = QHBoxLayout(page)
        self.kinds = QListWidget()
        self.kinds.setMaximumWidth(170)
        for kind in annotations.DEFAULTS:
            if kind in ("redact", "image", "placeholder"):
                continue
            it = QListWidgetItem(annotations.LABELS.get(kind, kind))
            it.setData(Qt.UserRole, kind)
            self.kinds.addItem(it)
        row.addWidget(self.kinds)
        from .properties import PropertiesPanel
        self.styles = PropertiesPanel()
        row.addWidget(self.styles, 1)
        self._pending = {}
        self.kinds.currentItemChanged.connect(lambda *_: self._show_kind())
        self.styles.propsChanged.connect(self._style_changed)
        self.styles.resetRequested.connect(self._style_reset)
        self.kinds.setCurrentRow(0)

        # Opening documents
        from .document_view import DocumentView
        page, form = self._tab(tabs, "Opening documents")
        self.open_view = QComboBox()
        for key, label in (("page", "Fit page (whole page in the window)"),
                           ("width", "Fit width"), ("actual", "Actual size (100%)"),
                           ("last", "The zoom it had when I closed it")):
            self.open_view.addItem(label, key)
        self.open_view.setCurrentIndex(max(0, self.open_view.findData(DocumentView.open_view)))
        form.addRow("Zoom when opening:", self.open_view)
        self.reopen = QCheckBox("Reopen at the page I was on last time")
        self.reopen.setChecked(DocumentView.reopen_page)
        form.addRow(self.reopen)

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

    def _sig_status(self):
        from . import signatures
        for kind, label in self._sig_rows.items():
            if not signatures.exists(kind):
                label.setText("Not set up yet")
            elif signatures.has_pin():
                label.setText("Saved (protected with your PIN)")
            else:
                label.setText("Saved")

    def _setup_sig(self, kind):
        self.win.setup_signature(kind)
        self._sig_status()

    def _kind(self):
        it = self.kinds.currentItem()
        return it.data(Qt.UserRole) if it is not None else None

    def _show_kind(self):
        from . import annotations
        kind = self._kind()
        if kind is None:
            return
        props = self._pending.get(kind) or annotations.saved_tool_props(kind)
        self.styles.show_target(kind, dict(props))

    def _style_changed(self, props):
        kind = self._kind()
        if kind is not None:
            self._pending[kind] = dict(props)

    def _style_reset(self):
        from . import annotations
        kind = self._kind()
        if kind is not None:
            self._pending[kind] = dict(annotations.DEFAULTS[kind])
            self._show_kind()

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
        from .document_view import DocumentView
        DocumentView.open_view = self.open_view.currentData()
        DocumentView.reopen_page = self.reopen.isChecked()
        win.settings.setValue("open_view", DocumentView.open_view)
        win.settings.setValue("reopen_page", "true" if self.reopen.isChecked() else "false")
        from . import annotations
        name = self.author.text().strip()
        if name != annotations.author():
            annotations.set_author(name)
        for kind, props in self._pending.items():
            annotations.set_tool_props(kind, props)
        if self._pending:
            win._refresh_props()
        self.accept()
