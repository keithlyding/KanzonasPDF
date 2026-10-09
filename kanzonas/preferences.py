"""File > Preferences (Ctrl+K): the remembered options in one place.

Every checkbox is tied to the menu command that already does the job, so changing an option
here or in its menu does the same thing and both always agree."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QWidget,
                               QCheckBox, QComboBox, QFormLayout, QLabel, QPushButton,
                               QDialogButtonBox, QLineEdit, QListWidget, QListWidgetItem,
                               QSpinBox, QDoubleSpinBox, QMessageBox)


def _plain(text):
    return text.replace("&&", "\0").replace("&", "").replace("\0", "&")


class _Sections(QWidget):
    """Categories listed on the left, the chosen one shown on the right (fits many sections
    without the scroll arrows a row of tabs would need)."""

    def __init__(self):
        super().__init__()
        from PySide6.QtWidgets import QStackedWidget
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        self.list = QListWidget()
        self.list.setMaximumWidth(190)
        self.stack = QStackedWidget()
        row.addWidget(self.list)
        row.addWidget(self.stack, 1)
        self.list.currentRowChanged.connect(self.stack.setCurrentIndex)

    def addTab(self, widget, title):
        self.stack.addWidget(widget)
        self.list.addItem(title)
        if self.list.count() == 1:
            self.list.setCurrentRow(0)

    def count(self):
        return self.list.count()

    def tabText(self, i):
        return self.list.item(i).text()

    def setCurrentIndex(self, i):
        self.list.setCurrentRow(i)


class PreferencesDialog(QDialog):
    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.setWindowTitle("Preferences")
        self.resize(760, 560)
        self._boxes = []            # (QCheckBox, QAction)
        lay = QVBoxLayout(self)
        tabs = _Sections()
        self.sections = tabs
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
        from .document_view import DocumentView
        self.sig_size = {}
        for kind, label in (("signature", "Signature width:"), ("initials", "Initials width:")):
            sb = QDoubleSpinBox()
            sb.setRange(0.2, 8.0)
            sb.setSingleStep(0.25)
            sb.setDecimals(2)
            sb.setSuffix(" in")
            sb.setValue(DocumentView.SIG_WIDTH[kind] / 72.0)
            sb.setToolTip("How wide it's placed when you click. You can also drag a box when "
                          "placing it to make it exactly that wide.")
            form.addRow(label, sb)
            self.sig_size[kind] = sb
        from . import signatures as sigmod
        from datetime import date as _date
        self.datefmt = QComboBox()
        for fmt in sigmod.DATE_FORMATS:
            self.datefmt.addItem(_date.today().strftime(fmt), fmt)
        self.datefmt.setCurrentIndex(max(0, self.datefmt.findData(sigmod.date_format())))
        self.datefmt.setToolTip("How the Date tool (Ctrl+;) writes today's date")
        form.addRow("Date format:", self.datefmt)
        pin = QPushButton("Change PIN...")
        pin.setToolTip("Set, change or remove the PIN that protects your saved signature and "
                       "initials")
        pin.clicked.connect(self._change_pin)
        form.addRow("Signature PIN:", pin)
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
        page, form = self._tab(tabs, "Start-up and opening")
        self.restore = QCheckBox("Reopen the documents that were open when I closed KanzonasPDF")
        self.restore.setChecked(win.settings.value("restore_session", "false") == "true")
        form.addRow(self.restore)
        self.start_tool = QComboBox()
        self.start_tool.addItem("Hand (drag to scroll)", "hand")
        self.start_tool.addItem("Select", "select")
        self.start_tool.setCurrentIndex(max(0, self.start_tool.findData(
            win.settings.value("start_tool", "hand"))))
        form.addRow("Start with the tool:", self.start_tool)
        self.open_view = QComboBox()
        for key, label in (("width", "Fit width"), ("page", "Fit page (whole page in the window)"),
                           ("actual", "Actual size (100%)"),
                           ("last", "The zoom it had when I closed it")):
            self.open_view.addItem(label, key)
        self.open_view.setCurrentIndex(max(0, self.open_view.findData(DocumentView.open_view)))
        form.addRow("Zoom when opening:", self.open_view)
        self.reopen = QCheckBox("Reopen at the page I was on last time")
        self.reopen.setChecked(DocumentView.reopen_page)
        form.addRow(self.reopen)

        # Saving: automatic backup copies
        page, form = self._tab(tabs, "Saving")
        self.autosave = QSpinBox()
        self.autosave.setRange(0, 60)
        self.autosave.setSuffix(" min")
        self.autosave.setSpecialValueText("Off")
        self.autosave.setValue(win.autosave.minutes)
        form.addRow("Back up unsaved changes every:", self.autosave)
        note = QLabel("A copy of each document with unsaved changes is kept in the backups "
                      "folder and deleted when you save or close the document. If KanzonasPDF "
                      "or Windows stops unexpectedly, you're offered the copies the next time "
                      "it starts. Password-protected documents aren't backed up (the copy "
                      "wouldn't have the password).")
        note.setWordWrap(True)
        form.addRow(note)
        self.backup_dir = win.settings.value("backup_dir", "") or ""
        self.backup_label = QLabel()
        self.backup_label.setWordWrap(True)
        self.backup_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._show_backup_dir()
        form.addRow("Backup folder:", self.backup_label)
        row = QHBoxLayout()
        for text, slot in (("Change...", self._pick_backup_dir),
                           ("Use default", self._default_backup_dir),
                           ("Open backup folder", self._open_backups)):
            b = QPushButton(text)
            b.clicked.connect(slot)
            row.addWidget(b)
        form.addRow(row)
        note = QLabel("Tip: choose a folder on this computer. A network or cloud-synced "
                      "folder works too, but your unsaved changes are then copied there. "
                      "Backups of open documents move to the new folder; recovered copies "
                      "from earlier stay in the old one.")
        note.setWordWrap(True)
        form.addRow(note)

        # Measuring
        from . import measure
        page, form = self._tab(tabs, "Measuring")
        self.m_unit = QComboBox()
        for u, lab in measure.UNIT_LABELS.items():
            self.m_unit.addItem(lab, u)
        self.m_unit.setCurrentIndex(max(0, self.m_unit.findData(measure.DEFAULT_UNIT)))
        form.addRow("Default units for a new scale:", self.m_unit)
        self.m_frac = QComboBox()
        for f in measure.FRACTIONS:
            self.m_frac.addItem(f'1/{f}"', f)
        self.m_frac.setCurrentIndex(max(0, self.m_frac.findData(measure.FRACTION)))
        form.addRow("Feet and inches round to:", self.m_frac)
        self.m_dec = QComboBox()
        self.m_dec.addItem("Automatic (2, whole millimeters)", "auto")
        for d in range(0, 5):
            self.m_dec.addItem(str(d), str(d))
        self.m_dec.setCurrentIndex(max(0, self.m_dec.findData(
            "auto" if measure.DECIMALS is None else str(measure.DECIMALS))))
        form.addRow("Decimal places:", self.m_dec)
        note = QLabel("Existing measurement labels update when you next move or edit them.")
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
        for a in (win.a_cards, win.a_hl_fields):
            self._box(form, a)
        # grid and snapping: all of it here, in one place (same settings as View > Grid
        # settings...)
        from PySide6.QtWidgets import QGroupBox
        from . import snapping
        box = QGroupBox("Grid and snapping")
        gform = QFormLayout(box)
        self.grid_value = QDoubleSpinBox()
        self.grid_value.setDecimals(3)
        self.grid_value.setRange(0.001, 10000)
        self.grid_value.setValue(float(win.settings.value("grid_value", 0.5)))
        self.grid_unit = QComboBox()
        for k, name in snapping.UNIT_NAMES.items():
            self.grid_unit.addItem(name, k)
        self.grid_unit.setCurrentIndex(max(0, self.grid_unit.findData(
            win.settings.value("grid_unit", "in"))))
        row = QHBoxLayout()
        row.addWidget(self.grid_value)
        row.addWidget(self.grid_unit)
        gform.addRow("Grid spacing (on paper):", row)
        self.grid_major = QSpinBox()
        self.grid_major.setRange(1, 100)
        self.grid_major.setValue(int(win.settings.value("grid_major", 4)))
        gform.addRow("Darker line every:", self.grid_major)
        for a in (win.a_grid, win.a_snap_grid, win.a_snap_objects, win.a_snap_page):
            self._box(gform, a)
        gform.addRow(QLabel("Hold Alt while drawing or dragging to place a point without "
                            "snapping."))
        form.addRow(box)

        # OCR
        page, form = self._tab(tabs, "OCR")
        from . import ocr as ocrmod
        self.ocr = QComboBox()
        for key in ("auto", "fast", "normal", "high"):
            self.ocr.addItem(ocrmod.ACCURACY_LABELS[key], key)
        self.ocr.setCurrentIndex(max(0, self.ocr.findData(
            win.settings.value("ocr_accuracy", "auto"))))
        form.addRow("Default accuracy:", self.ocr)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel |
                                QDialogButtonBox.Apply)
        btns.accepted.connect(self._ok)
        btns.rejected.connect(self.reject)
        # Apply: use the changes now and keep the window open (Cancel then closes without
        # undoing what was applied, as in Windows)
        btns.button(QDialogButtonBox.Apply).clicked.connect(self._apply)
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

    def _change_pin(self):
        from . import signatures
        old = None
        if signatures.has_pin():
            old = signatures.ask_pin(self, "Current PIN:")
            if old is None:
                return
            if not signatures._pin_ok(old):
                QMessageBox.warning(self, "Signature PIN", "Wrong PIN.")
                return
        from PySide6.QtWidgets import QInputDialog
        new, ok = QInputDialog.getText(self, "Signature PIN",
                                       "New PIN (leave empty for no PIN):", QLineEdit.Password)
        if not ok:
            return
        again, ok = QInputDialog.getText(self, "Signature PIN", "Type the new PIN again:",
                                         QLineEdit.Password)
        if not ok:
            return
        if new != again:
            QMessageBox.warning(self, "Signature PIN", "The two PINs don't match. Nothing "
                                "was changed.")
            return
        try:
            signatures.set_pin(new, old)
        except Exception as e:
            QMessageBox.warning(self, "Signature PIN", f"Couldn't change the PIN:\n{e}")
            return
        signatures.Session.pin = new or None
        self._sig_status()
        QMessageBox.information(self, "Signature PIN",
                                "PIN changed." if new else "PIN removed.")

    def _show_backup_dir(self):
        from . import autosave
        if self.backup_dir:
            self.backup_label.setText(self.backup_dir)
        else:
            self.backup_label.setText(autosave.default_folder() + "  (default)")

    def _pick_backup_dir(self):
        from PySide6.QtWidgets import QFileDialog
        from . import autosave
        start = self.backup_dir or autosave.default_folder()
        d = QFileDialog.getExistingDirectory(self, "Backup folder", start)
        if not d:
            return
        if not autosave.usable(d):
            QMessageBox.warning(self, "Backup folder", "KanzonasPDF can't write to that "
                                "folder. Choose another one.")
            return
        self.backup_dir = d
        self._show_backup_dir()

    def _default_backup_dir(self):
        self.backup_dir = ""
        self._show_backup_dir()

    def _open_backups(self):
        import os
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        from . import autosave
        d = self.backup_dir or autosave.default_folder()
        os.makedirs(d, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(d))

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
        self._apply()
        self.accept()

    def _apply(self):
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
        from . import signatures as sigmod
        if self.datefmt.currentData() != sigmod.date_format():
            sigmod.set_date_format(self.datefmt.currentData())
        win.settings.setValue("grid_value", self.grid_value.value())
        win.settings.setValue("grid_unit", self.grid_unit.currentData())
        win.settings.setValue("grid_major", self.grid_major.value())
        win._apply_grid_settings()
        from .document_view import DocumentView
        for kind, sb in self.sig_size.items():
            DocumentView.SIG_WIDTH[kind] = sb.value() * 72.0
            win.settings.setValue("sig_width_" + kind, sb.value() * 72.0)
        win.settings.setValue("restore_session", "true" if self.restore.isChecked() else "false")
        win.settings.setValue("start_tool", self.start_tool.currentData())
        win.settings.setValue("autosave_minutes", self.autosave.value())
        if self.backup_dir != (win.settings.value("backup_dir", "") or ""):
            win.autosave.discard_all()      # move the current copies to the new folder
            win.settings.setValue("backup_dir", self.backup_dir)
            if win.autosave.minutes:
                win.autosave.tick()
        win.autosave.set_minutes(self.autosave.value())
        from . import measure
        win.settings.setValue("measure_unit", self.m_unit.currentData())
        win.settings.setValue("measure_fraction", self.m_frac.currentData())
        win.settings.setValue("measure_decimals", self.m_dec.currentData())
        measure.configure(win.settings)
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
        self._pending = {}
