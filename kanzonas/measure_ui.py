"""Dialogs for measurement: setting the scale, and the measurement summary."""

import csv
import re

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QRadioButton,
                               QComboBox, QLineEdit, QLabel, QDialogButtonBox, QTableWidget,
                               QTableWidgetItem, QHeaderView, QPushButton, QFileDialog,
                               QMessageBox, QAbstractItemView)

from . import annotations as A
from . import measure as M

_INPUT_UNITS = ["ft-in", "ft", "in", "yd", "m", "cm", "mm"]


def parse_length(text, unit):
    """Text -> meters. Accepts 12'-6", 12' 6 1/2", 6", 12.5 (in the chosen unit)."""
    t = text.strip().replace("’", "'").replace("”", '"')
    if not t:
        raise ValueError("Enter the real length.")
    if "'" in t or '"' in t:
        m = re.fullmatch(r"\s*(?:(\d+(?:\.\d+)?)\s*')?\s*-?\s*(?:(\d+(?:\.\d+)?)?"
                         r"(?:\s+(\d+)/(\d+))?\s*\"?)?\s*", t)
        if not m:
            raise ValueError("Couldn't read that length. Try 12'-6\" or 150.")
        ft = float(m.group(1) or 0)
        inch = float(m.group(2) or 0)
        if m.group(3):
            inch += int(m.group(3)) / int(m.group(4))
        return (ft * 12 + inch) * 0.0254
    value = float(t.replace(",", ""))
    if unit == "ft-in":
        unit = "ft"
    return value * M.UNITS[unit]


class ScaleDialog(QDialog):
    """Pick a preset scale, or (after drawing a calibration line) type its real length."""

    def __init__(self, parent, page, pdf_len=None, page_count=1):
        super().__init__(parent)
        self.setWindowTitle("Calibrate" if pdf_len else "Set scale")
        self.pdf_len = pdf_len
        lay = QVBoxLayout(self)
        _f, cur_unit, cur_label, ok = M.get_scale(page)
        lay.addWidget(QLabel(f"Current: {cur_label}"))
        form = QFormLayout()
        self.r_known = QRadioButton("Known distance")
        self.r_preset = QRadioButton("Preset scale")
        self.length = QLineEdit()
        self.length.setPlaceholderText("e.g. 12'-6\"  or  3.5")
        self.in_unit = QComboBox()
        for u in _INPUT_UNITS:
            self.in_unit.addItem(M.UNIT_LABELS[u], u)
        row = QHBoxLayout()
        row.addWidget(self.length, 1)
        row.addWidget(self.in_unit)
        self.preset = QComboBox()
        for label, ratio, unit in M.PRESETS:
            self.preset.addItem(label, (ratio, unit))
        self.disp_unit = QComboBox()
        for u, lab in M.UNIT_LABELS.items():
            self.disp_unit.addItem(lab, u)
        self.disp_unit.setCurrentIndex(max(0, self.disp_unit.findData(cur_unit if ok else "ft-in")))
        self.pages = QComboBox()
        self.pages.addItems(["This page", "All pages"])
        if page_count < 2:
            self.pages.setEnabled(False)
        if pdf_len:
            lay.addWidget(QLabel("You drew a line. How long is it in real life?"))
            form.addRow(self.r_known, row)
            self.r_known.setChecked(True)
        else:
            self.r_known.hide()
            self.length.hide()
            self.in_unit.hide()
            self.r_preset.setChecked(True)
        form.addRow(self.r_preset, self.preset)
        form.addRow("Show measurements in", self.disp_unit)
        form.addRow("Apply to", self.pages)
        lay.addLayout(form)
        self.preset.currentIndexChanged.connect(self._preset_changed)
        self.preset.activated.connect(lambda _: self.r_preset.setChecked(True))
        self.length.textEdited.connect(lambda _: self.r_known.setChecked(True))
        self.in_unit.currentIndexChanged.connect(self._unit_changed)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)
        self.result_scale = None
        if pdf_len:
            self.length.setFocus()

    def _preset_changed(self, i):
        _ratio, unit = self.preset.itemData(i)
        self.disp_unit.setCurrentIndex(self.disp_unit.findData(unit))

    def _unit_changed(self, _i):
        self.disp_unit.setCurrentIndex(self.disp_unit.findData(self.in_unit.currentData()))

    def _accept(self):
        unit = self.disp_unit.currentData()
        if self.r_known.isChecked() and self.pdf_len:
            try:
                meters = parse_length(self.length.text(), self.in_unit.currentData())
            except ValueError as e:
                QMessageBox.warning(self, "Calibrate", str(e))
                return
            if meters <= 0:
                QMessageBox.warning(self, "Calibrate", "The length must be more than zero.")
                return
            f = meters / self.pdf_len
            label = f"calibrated ({self.length.text().strip()} = drawn line)"
        else:
            ratio, _u = self.preset.currentData()
            f = M.scale_from_preset(ratio)
            label = self.preset.currentText()
        self.result_scale = (f, unit, label, self.pages.currentIndex() == 1)
        self.accept()


def summary_rows(doc):
    """[(kind label, group/page, count, total, unit)] grouped per kind + unit (+ count group)."""
    groups = {}
    for i in range(doc.page_count):
        page = doc[i]
        for a in page.annots():
            m = A.read(a)
            if not m or m["kind"] not in A.MEASURES:
                continue
            value, unit = M.raw_values(m["kind"], m["points"], page)
            key = (A.LABELS[m["kind"]], m["props"].get("group", "") if m["kind"] == "m_count" else "")
            g = groups.setdefault(key + (unit,), {"count": 0, "total": 0.0, "pages": set()})
            g["count"] += 1
            g["total"] += value
            g["pages"].add(i + 1)
    rows = []
    for (label, group, unit), g in sorted(groups.items()):
        pages = ", ".join(str(p) for p in sorted(g["pages"]))
        total = g["count"] if unit == "count" else round(g["total"], 2)
        rows.append((label, group or "", pages, g["count"], total, unit))
    return rows


class SummaryDialog(QDialog):
    COLS = ["Type", "Group", "Pages", "Items", "Total", "Unit"]

    def __init__(self, parent, doc):
        super().__init__(parent)
        self.setWindowTitle("Measurement summary")
        self.resize(640, 360)
        lay = QVBoxLayout(self)
        self.rows = summary_rows(doc)
        t = QTableWidget(len(self.rows), len(self.COLS))
        t.setHorizontalHeaderLabels(self.COLS)
        t.setEditTriggers(QAbstractItemView.NoEditTriggers)
        t.verticalHeader().hide()
        t.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        for r, row in enumerate(self.rows):
            for c, v in enumerate(row):
                it = QTableWidgetItem(f"{v:,}" if isinstance(v, float) else str(v))
                if c in (3, 4):
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                t.setItem(r, c, it)
        lay.addWidget(t)
        if not self.rows:
            lay.addWidget(QLabel("No measurements yet. Use the Measure tools to add some."))
        btns = QHBoxLayout()
        exp = QPushButton("Export CSV...")
        exp.clicked.connect(self._export)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        btns.addWidget(exp)
        btns.addStretch(1)
        btns.addWidget(close)
        lay.addLayout(btns)

    def _export(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export measurements", "measurements.csv",
                                              "CSV (*.csv)")
        if path:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f)
                w.writerow(self.COLS)
                w.writerows(self.rows)
