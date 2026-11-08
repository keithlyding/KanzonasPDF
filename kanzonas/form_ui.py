"""The smart forms windows: Field properties (name, tooltip, required, calculation, format,
range check, tab order), Detect form fields (what was found, to keep, rename or leave out) and
Set tab order."""

import pymupdf
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QButtonGroup, QCheckBox, QComboBox, QDialog,
                               QDialogButtonBox, QFormLayout, QHBoxLayout, QHeaderView, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem, QMessageBox,
                               QPlainTextEdit, QPushButton, QRadioButton, QSpinBox,
                               QStackedWidget, QTableWidget, QTableWidgetItem, QTabWidget,
                               QVBoxLayout, QWidget)

from . import smart_forms
from .i18n import tr

OPS = [("SUM", tr("Sum (+)")), ("PRD", tr("Product (x)")), ("AVG", tr("Average")),
       ("MIN", tr("Minimum")), ("MAX", tr("Maximum"))]
SEPARATORS = ["1,234.56", "1234.56", "1.234,56", "1234,56", "1'234.56"]
SPECIALS = [tr("ZIP code"), tr("ZIP+4 code"), tr("Phone number"), tr("Social Security number")]


def _script_note(js):
    s = " ".join((js or "").split())
    return s[:160] + ("..." if len(s) > 160 else "")


class FieldPropertiesDialog(QDialog):
    def __init__(self, parent, props):
        super().__init__(parent)
        self.props = props
        self.setWindowTitle(tr("Field properties"))
        self.resize(520, 460)
        lay = QVBoxLayout(self)
        tabs = self.tabs = QTabWidget()
        lay.addWidget(tabs)
        is_text = props["type"] == pymupdf.PDF_WIDGET_TYPE_TEXT
        is_choice = props.get("choices") is not None

        # General
        g = QWidget()
        form = QFormLayout(g)
        self.name = QLineEdit(props["name"])
        form.addRow(tr("Name:"), self.name)
        self.tooltip = QLineEdit(props.get("tooltip") or "")
        self.tooltip.setPlaceholderText(tr("Shown when the pointer rests on the field"))
        form.addRow(tr("Tooltip:"), self.tooltip)
        self.required = QCheckBox(tr("Required (flagged on Save and Print when empty)"))
        self.required.setChecked(props.get("required", False))
        form.addRow("", self.required)
        self.readonly = QCheckBox(tr("Read-only"))
        self.readonly.setChecked(props.get("readonly", False))
        form.addRow("", self.readonly)
        self.choices = None
        if is_choice:
            self.choices = QPlainTextEdit("\n".join(props["choices"]))
            self.choices.setFixedHeight(90)
            form.addRow(tr("Choices, one per line:"), self.choices)
        self.tab = None
        if props.get("tabs"):
            self.tab = QSpinBox()
            self.tab.setRange(1, max(1, props["tabs"]))
            self.tab.setValue(max(1, props.get("tab") or 1))
            form.addRow(tr("Place in the tab order:"), self.tab)
        form.addRow(QLabel(tr("Type: {kind}").format(kind=props.get("type_name", ""))))
        tabs.addTab(g, tr("General"))

        if is_text:
            tabs.addTab(self._format_tab(props.get("format")), tr("Format"))
        if is_text or is_choice:
            tabs.addTab(self._validate_tab(props.get("range")), tr("Validate"))
            tabs.addTab(self._calc_tab(props.get("calc"), props.get("fields", [])),
                        tr("Calculate"))
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    # ---- Format ----
    def _format_tab(self, fmt):
        w = QWidget()
        lay = QVBoxLayout(w)
        row = QHBoxLayout()
        row.addWidget(QLabel(tr("Format:")))
        self.fmt_kind = QComboBox()
        kinds = [("", tr("None")), ("number", tr("Number")), ("percent", tr("Percent")),
                 ("date", tr("Date")), ("special", tr("Special (ZIP, phone, SSN)"))]
        self.custom_fmt = fmt if fmt and "custom" in fmt else None
        if self.custom_fmt:
            kinds.append(("custom", tr("Custom script (not run)")))
        for k, label in kinds:
            self.fmt_kind.addItem(label, k)
        row.addWidget(self.fmt_kind, 1)
        lay.addLayout(row)
        st = self.fmt_stack = QStackedWidget()
        st.addWidget(QWidget())                                         # none
        num = QWidget()
        f = QFormLayout(num)
        self.decimals = QSpinBox()
        self.decimals.setRange(0, 10)
        self.decimals.setValue(2)
        f.addRow(tr("Decimal places:"), self.decimals)
        self.sep = QComboBox()
        self.sep.addItems(SEPARATORS)
        f.addRow(tr("Separator style:"), self.sep)
        self.currency = QLineEdit()
        self.currency.setPlaceholderText(tr("e.g. $ or € (empty: none)"))
        f.addRow(tr("Currency symbol:"), self.currency)
        self.after = QCheckBox(tr("Symbol after the number"))
        f.addRow("", self.after)
        self.neg = QComboBox()
        self.neg.addItems(["-1,234.56", "(1,234.56)"])
        f.addRow(tr("Negative numbers:"), self.neg)
        st.addWidget(num)
        pct = QWidget()
        f = QFormLayout(pct)
        self.pdecimals = QSpinBox()
        self.pdecimals.setRange(0, 10)
        self.pdecimals.setValue(2)
        f.addRow(tr("Decimal places:"), self.pdecimals)
        self.psep = QComboBox()
        self.psep.addItems(SEPARATORS)
        f.addRow(tr("Separator style:"), self.psep)
        note = QLabel(tr("A number typed is a percent: 25 or 25% shows as 25.00%. The value is "
                         "kept as a fraction, 0.25, as Acrobat keeps it."))
        note.setWordWrap(True)
        f.addRow(note)
        st.addWidget(pct)
        dt = QWidget()
        f = QFormLayout(dt)
        self.pattern = QComboBox()
        self.pattern.setEditable(True)
        self.pattern.addItems(smart_forms.DATE_PRESETS)
        f.addRow(tr("Date format:"), self.pattern)
        f.addRow(QLabel(tr("d day, m month (mmm Jan, mmmm January), yy or yyyy year.")))
        st.addWidget(dt)
        sp = QWidget()
        f = QFormLayout(sp)
        self.special = QComboBox()
        self.special.addItems(SPECIALS)
        f.addRow(tr("Kind:"), self.special)
        st.addWidget(sp)
        cu = QWidget()
        f = QVBoxLayout(cu)
        note = QLabel(tr("This field's format is a script KanzonasPDF doesn't run (it's kept "
                         "in the file for Acrobat):") + "\n" +
                      _script_note(self.custom_fmt.get("custom") if self.custom_fmt else ""))
        note.setWordWrap(True)
        f.addWidget(note)
        f.addStretch(1)
        st.addWidget(cu)
        lay.addWidget(st)
        lay.addStretch(1)
        self.fmt_kind.currentIndexChanged.connect(
            lambda: st.setCurrentIndex(["", "number", "percent", "date", "special",
                                        "custom"].index(self.fmt_kind.currentData())))
        # what the field has now
        k = "custom" if self.custom_fmt else (fmt or {}).get("kind", "")
        if k == "number":
            self.decimals.setValue(fmt.get("decimals", 2))
            self.sep.setCurrentIndex(fmt.get("sep", 0))
            self.currency.setText(fmt.get("currency", ""))
            self.after.setChecked(not fmt.get("prepend", True))
            self.neg.setCurrentIndex(1 if fmt.get("neg", 0) in (2, 3) else 0)
        elif k == "percent":
            self.pdecimals.setValue(fmt.get("decimals", 2))
            self.psep.setCurrentIndex(fmt.get("sep", 0))
        elif k == "date":
            self.pattern.setCurrentText(fmt["pattern"])
        elif k == "special":
            self.special.setCurrentIndex(fmt.get("which", 0))
        self.fmt_kind.setCurrentIndex(max(0, self.fmt_kind.findData(k)))
        st.setCurrentIndex(["", "number", "percent", "date", "special", "custom"].index(k))
        return w

    def format_value(self):
        k = self.fmt_kind.currentData()
        if k == "number":
            return {"kind": "number", "decimals": self.decimals.value(),
                    "sep": self.sep.currentIndex(), "neg": 2 if self.neg.currentIndex() else 0,
                    "currency": self.currency.text().strip(), "prepend": not self.after.isChecked()}
        if k == "percent":
            return {"kind": "percent", "decimals": self.pdecimals.value(),
                    "sep": self.psep.currentIndex()}
        if k == "date":
            return {"kind": "date", "pattern": self.pattern.currentText().strip() or "mm/dd/yyyy"}
        if k == "special":
            return {"kind": "special", "which": self.special.currentIndex()}
        if k == "custom":
            return self.custom_fmt
        return None

    # ---- Validate ----
    def _validate_tab(self, rng):
        w = QWidget()
        f = QFormLayout(w)
        self.custom_rng = rng if rng and "custom" in rng else None
        self.use_range = QCheckBox(tr("The value must be in this range"))
        f.addRow(self.use_range)
        self.rmin = QLineEdit()
        self.rmin.setPlaceholderText(tr("(no minimum)"))
        self.rmax = QLineEdit()
        self.rmax.setPlaceholderText(tr("(no maximum)"))
        f.addRow(tr("From:"), self.rmin)
        f.addRow(tr("To:"), self.rmax)
        if self.custom_rng:
            note = QLabel(tr("This field is checked by a script KanzonasPDF doesn't run (it's "
                             "kept unless you set a range):") + "\n" +
                          _script_note(self.custom_rng["custom"]))
            note.setWordWrap(True)
            f.addRow(note)
        elif rng:
            self.use_range.setChecked(True)
            if rng.get("min") is not None:
                self.rmin.setText(smart_forms.number_text(rng["min"]))
            if rng.get("max") is not None:
                self.rmax.setText(smart_forms.number_text(rng["max"]))
        return w

    def range_value(self):
        if not self.use_range.isChecked():
            return self.custom_rng
        lo = smart_forms.to_number(self.rmin.text()) if self.rmin.text().strip() else None
        hi = smart_forms.to_number(self.rmax.text()) if self.rmax.text().strip() else None
        if lo is None and hi is None:
            return None
        return {"min": lo, "max": hi}

    # ---- Calculate ----
    def _calc_tab(self, calc, fields):
        w = QWidget()
        lay = QVBoxLayout(w)
        self.calc_group = QButtonGroup(self)
        self.c_none = QRadioButton(tr("Not calculated"))
        self.c_simple = QRadioButton(tr("Value is the"))
        self.c_formula = QRadioButton(tr("Formula:"))
        self.custom_calc = calc if calc and "custom" in calc else None
        lay.addWidget(self.c_none)
        row = QHBoxLayout()
        row.addWidget(self.c_simple)
        self.op = QComboBox()
        for code, label in OPS:
            self.op.addItem(label, code)
        row.addWidget(self.op)
        row.addWidget(QLabel(tr("of these fields:")))
        row.addStretch(1)
        lay.addLayout(row)
        self.pick = QListWidget()
        chosen = set(calc.get("fields", [])) if calc and "fields" in calc else set()
        for n in fields:
            it = QListWidgetItem(n)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked if n in chosen else Qt.Unchecked)
            self.pick.addItem(it)
        for n in sorted(chosen - set(fields)):
            it = QListWidgetItem(n)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked)
            self.pick.addItem(it)
        lay.addWidget(self.pick, 1)
        row = QHBoxLayout()
        row.addWidget(self.c_formula)
        self.formula = QLineEdit(calc.get("formula", "") if calc else "")
        self.formula.setPlaceholderText(tr("e.g. Price * Qty + Shipping"))
        row.addWidget(self.formula, 1)
        lay.addLayout(row)
        hint = QLabel(tr("Field names, numbers, + - * / and parentheses; a name with spaces or "
                         "other signs takes a backslash before each (Item\\ 1)."))
        hint.setWordWrap(True)
        hint.setStyleSheet("color: gray;")
        lay.addWidget(hint)
        for b in (self.c_none, self.c_simple, self.c_formula):
            self.calc_group.addButton(b)
        if self.custom_calc:
            self.c_custom = QRadioButton(tr("Custom calculation (not run)"))
            self.calc_group.addButton(self.c_custom)
            lay.addWidget(self.c_custom)
            note = QLabel(_script_note(self.custom_calc["custom"]))
            note.setWordWrap(True)
            note.setStyleSheet("color: gray;")
            lay.addWidget(note)
            self.c_custom.setChecked(True)
        elif calc and "formula" in calc:
            self.c_formula.setChecked(True)
        elif calc:
            self.c_simple.setChecked(True)
            self.op.setCurrentIndex(max(0, self.op.findData(calc["op"])))
        else:
            self.c_none.setChecked(True)
        lay.addWidget(QLabel(tr("Calculated fields are worked out by KanzonasPDF as you fill "
                                "in the form, and by Acrobat and other readers.")))
        return w

    def calc_value(self):
        if self.c_simple.isChecked():
            names = [self.pick.item(k).text() for k in range(self.pick.count())
                     if self.pick.item(k).checkState() == Qt.Checked]
            return {"op": self.op.currentData(), "fields": names} if names else None
        if self.c_formula.isChecked():
            text = self.formula.text().strip()
            return {"formula": smart_forms.formula_text(smart_forms.parse_formula(text))} \
                if text else None
        if self.custom_calc and self.c_custom.isChecked():
            return self.custom_calc
        return None

    def result(self):
        out = {"name": self.name.text().strip(), "tooltip": self.tooltip.text().strip(),
               "required": self.required.isChecked(), "readonly": self.readonly.isChecked()}
        if self.choices is not None:
            out["choices"] = [c.strip() for c in self.choices.toPlainText().splitlines()
                              if c.strip()]
        if self.tab is not None:
            out["tab"] = self.tab.value()
        if hasattr(self, "fmt_kind"):
            out["format"] = self.format_value()
        if hasattr(self, "use_range"):
            out["range"] = self.range_value()
        if hasattr(self, "calc_group"):
            out["calc"] = self.calc_value()
        return out

    def accept(self):
        if not self.name.text().strip():
            QMessageBox.information(self, tr("Field properties"), tr("Give the field a name."))
            return
        try:
            out = self.result()
        except smart_forms.FormulaError as ex:
            QMessageBox.information(self, tr("Field properties"),
                                    tr("The formula can't be read: {error}").format(error=ex))
            return
        calc = out.get("calc")
        if calc and out["name"] in smart_forms.calc_inputs(calc):
            QMessageBox.information(self, tr("Field properties"),
                                    tr("A field can't be calculated from itself."))
            return
        if calc and "formula" in calc:
            known = set(self.props.get("fields", []))
            unknown = [n for n in smart_forms.calc_inputs(calc) if n not in known and not
                       any(k.startswith(n + ".") for k in known)]
            if unknown:
                QMessageBox.information(self, tr("Field properties"), tr(
                    "No field is called {names}: check the formula (names are case-sensitive)."
                ).format(names=", ".join(unknown)))
                return
        self.out = out
        super().accept()


def edit_field(parent, props):
    """The Field properties window: the new properties, or None if cancelled."""
    dlg = FieldPropertiesDialog(parent, props)
    return dlg.out if dlg.exec() == QDialog.Accepted else None


# ---- Detect form fields ---------------------------------------------------------------------
KINDS = [("text", tr("Text field")), ("multiline", tr("Text field (several lines)")),
         ("date", tr("Date field")), ("check", tr("Checkbox")),
         ("signature", tr("Signature field")), ("initials", tr("Initials field"))]


class DetectDialog(QDialog):
    """What Detect form fields found, to keep (all, some), rename or retype before anything
    is made. The page shows each one as an orange dashed box while this is open."""

    def __init__(self, view, found):
        super().__init__(view)
        self.view, self.found = view, found
        self.setWindowTitle(tr("Detect form fields"))
        self.resize(560, 460)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(tr("Found {n} place(s) for a field. Untick what you don't want, "
                                "and change a name or kind if needed; nothing changes until "
                                "you click Create fields.").format(n=len(found))))
        t = self.table = QTableWidget(len(found), 4)
        t.setHorizontalHeaderLabels([tr("Use"), tr("Page"), tr("Kind"), tr("Name")])
        t.verticalHeader().setVisible(False)
        t.setSelectionBehavior(QAbstractItemView.SelectRows)
        t.setSelectionMode(QAbstractItemView.SingleSelection)
        t.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.kinds = []
        for row, f in enumerate(found):
            use = QTableWidgetItem()
            use.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            use.setCheckState(Qt.Checked)
            t.setItem(row, 0, use)
            pg = QTableWidgetItem(str(f["page"] + 1))
            pg.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            t.setItem(row, 1, pg)
            kind = QComboBox()
            for k, label in KINDS:
                kind.addItem(label, k)
            kind.setCurrentIndex(max(0, kind.findData(f["kind"])))
            t.setCellWidget(row, 2, kind)
            self.kinds.append(kind)
            t.setItem(row, 3, QTableWidgetItem(f["name"]))
        t.resizeColumnsToContents()
        t.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        t.currentCellChanged.connect(lambda r, *_: self._show(r))
        lay.addWidget(t, 1)
        row = QHBoxLayout()
        for label, state in ((tr("Select all"), Qt.Checked), (tr("Select none"), Qt.Unchecked)):
            b = QPushButton(label)
            b.clicked.connect(lambda _=False, s=state: self._tick_all(s))
            row.addWidget(b)
        row.addStretch(1)
        lay.addLayout(row)
        bb = QDialogButtonBox(QDialogButtonBox.Cancel)
        self.create = bb.addButton(tr("Create fields"), QDialogButtonBox.AcceptRole)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        view.set_detect_preview(found)

    def _tick_all(self, state):
        for r in range(self.table.rowCount()):
            self.table.item(r, 0).setCheckState(state)

    def _show(self, row):
        if 0 <= row < len(self.found):
            self.view.set_detect_preview(self.found, row)

    def chosen(self):
        out = []
        for r, f in enumerate(self.found):
            if self.table.item(r, 0).checkState() != Qt.Checked:
                continue
            out.append(dict(f, kind=self.kinds[r].currentData(),
                            name=self.table.item(r, 3).text().strip() or f["name"]))
        return out

    def done(self, r):
        self.view.set_detect_preview(None)
        super().done(r)


def detect_fields(view, pages):
    """Forms > Detect form fields...: look, show what was found, make what's kept (one undo
    step). Returns how many fields were made."""
    found = view.detect_fields(pages)
    if not found:
        QMessageBox.information(view, tr("Detect form fields"), tr(
            "No place for a field was found: no blank lines, boxes or checkboxes with a label "
            "next to them. (On a scanned page, run Recognize text (OCR) first so the labels "
            "can be read.)"))
        return 0
    dlg = DetectDialog(view, found)
    if dlg.exec() != QDialog.Accepted:
        return 0
    return view.create_detected_fields(dlg.chosen())


# ---- Set tab order ------------------------------------------------------------------------
class TabOrderDialog(QDialog):
    def __init__(self, view, index):
        super().__init__(view)
        self.view, self.index = view, index
        self.setWindowTitle(tr("Set tab order"))
        self.resize(420, 440)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(tr("The order Tab goes through the fields of page {page}:").format(
            page=index + 1)))
        self.rows = QRadioButton(tr("By rows (left to right, top to bottom)"))
        self.cols = QRadioButton(tr("By columns (top to bottom, left to right)"))
        self.manual = QRadioButton(tr("Manual (in the order of this list)"))
        for b in (self.rows, self.cols, self.manual):
            lay.addWidget(b)
        {"rows": self.rows, "columns": self.cols,
         "manual": self.manual}[view.tab_order_of(index)].setChecked(True)
        self.list = QListWidget()
        for x, name, _r in view.page_fields(index):
            it = QListWidgetItem(name)
            it.setData(Qt.UserRole, x)
            self.list.addItem(it)
        self.list.setDragDropMode(QAbstractItemView.InternalMove)
        lay.addWidget(self.list, 1)
        row = QHBoxLayout()
        up, down = QPushButton(tr("Move up")), QPushButton(tr("Move down"))
        up.clicked.connect(lambda: self._move(-1))
        down.clicked.connect(lambda: self._move(1))
        row.addWidget(up)
        row.addWidget(down)
        row.addStretch(1)
        lay.addLayout(row)
        self.all_pages = QCheckBox(tr("Rows or columns: all pages"))
        lay.addWidget(self.all_pages)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _move(self, d):
        r = self.list.currentRow()
        if r < 0 or not 0 <= r + d < self.list.count():
            return
        it = self.list.takeItem(r)
        self.list.insertItem(r + d, it)
        self.list.setCurrentRow(r + d)
        self.manual.setChecked(True)

    def apply(self):
        if self.manual.isChecked():
            xs = [self.list.item(k).data(Qt.UserRole) for k in range(self.list.count())]
            return self.view.set_tab_order([self.index], "manual", {self.index: xs})
        how = "columns" if self.cols.isChecked() else "rows"
        pages = range(self.view.doc.page_count) if self.all_pages.isChecked() else [self.index]
        return self.view.set_tab_order(list(pages), how)


def set_tab_order(view, index):
    dlg = TabOrderDialog(view, index)
    if dlg.exec() == QDialog.Accepted:
        return dlg.apply()
    return False
