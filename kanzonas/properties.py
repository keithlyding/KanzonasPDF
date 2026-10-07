"""Properties panel: edits the selected annotation, or the current tool's saved defaults."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPixmap, QIcon
from PySide6.QtWidgets import (QWidget, QFormLayout, QVBoxLayout, QLabel, QToolButton,
                               QCheckBox, QDoubleSpinBox, QSlider, QComboBox, QHBoxLayout,
                               QColorDialog, QPushButton)

from . import annotations as A
from . import stamps as ST

BORDERLESS = ("textbox", "callout", "rect", "ellipse", "polygon", "m_area")


class ColorButton(QToolButton):
    changed = Signal()

    def __init__(self, allow_none=False):
        super().__init__()
        self._color = None
        self.allow_none = allow_none
        self.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.clicked.connect(self._pick)

    def color(self):
        return self._color

    def set_color(self, hex_color):
        self._color = hex_color
        pm = QPixmap(18, 18)
        if hex_color:
            pm.fill(QColor(hex_color))
            self.setText(hex_color)
        else:
            pm.fill(Qt.white)
            self.setText("none")
        self.setIcon(QIcon(pm))

    def _pick(self):
        start = QColor(self._color) if self._color else QColor("#ffffff")
        c = QColorDialog.getColor(start, self, "Choose color")
        if c.isValid():
            self.set_color(c.name())
            self.changed.emit()


class PropertiesPanel(QWidget):
    propsChanged = Signal(dict)      # full props dict after a user change
    resetRequested = Signal()

    def __init__(self):
        super().__init__()
        self._kind = None
        self._loading = False
        outer = QVBoxLayout(self)
        self.title = QLabel()
        self.title.setWordWrap(True)
        self.title.setStyleSheet("font-weight: bold;")
        outer.addWidget(self.title)
        self.hint = QLabel()
        self.hint.setWordWrap(True)
        self.hint.setStyleSheet("color: gray;")
        outer.addWidget(self.hint)
        self.form = QFormLayout()
        outer.addLayout(self.form)

        self.stroke = ColorButton()
        self.no_stroke = QCheckBox("No border")
        stroke_row = QWidget()
        sl = QHBoxLayout(stroke_row)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.addWidget(self.stroke)
        sl.addWidget(self.no_stroke)
        self.fill = ColorButton(allow_none=True)
        self.no_fill = QCheckBox("No fill")
        fill_row = QWidget()
        fl = QHBoxLayout(fill_row)
        fl.setContentsMargins(0, 0, 0, 0)
        fl.addWidget(self.fill)
        fl.addWidget(self.no_fill)
        self.text_color = ColorButton()
        self.width = QDoubleSpinBox()
        self.width.setRange(0, 50)
        self.width.setSingleStep(0.5)
        self.width.setSuffix(" pt")
        self.fontsize = QDoubleSpinBox()
        self.fontsize.setRange(4, 144)
        self.fontsize.setSuffix(" pt")
        self.opacity = QSlider(Qt.Horizontal)
        self.opacity.setRange(10, 100)
        self.head = QComboBox()
        self.head.addItems(list(A.HEADS))
        self.label = QComboBox()            # stamp choice
        self.label.setEditable(True)
        self.label.setInsertPolicy(QComboBox.NoInsert)
        self.label.lineEdit().setPlaceholderText("Type your own stamp text")
        self.add_image = QPushButton("Add image stamp...")
        self.add_image.clicked.connect(self._add_image_stamp)
        label_row = QWidget()
        lr = QVBoxLayout(label_row)
        lr.setContentsMargins(0, 0, 0, 0)
        lr.addWidget(self.label)
        lr.addWidget(self.add_image)
        self.name = QCheckBox("Add my name")
        self.name.setToolTip("Your name is set in Edit > Author name for markups")
        self.date = QCheckBox("Add the date")
        self.rotation = QDoubleSpinBox()
        self.rotation.setRange(-360, 360)
        self.rotation.setDecimals(1)
        self.rotation.setSuffix("\u00b0")
        self.rotation.setWrapping(True)
        self.rotation.setKeyboardTracking(False)
        self.rotation.setToolTip("Counterclockwise. You can also drag the round handle above a "
                                 "selected shape (hold Shift for 15\u00b0 steps).")
        self.cloud = QCheckBox("Cloud border")
        self.markup = QComboBox()
        self.markup.addItems([m.capitalize() for m in A.COMMENT_STYLES])

        self.rows = {}
        for key, label, w in (("label", "Stamp", label_row),
                              ("name", "", self.name),
                              ("date", "", self.date),
                              ("cloud", "", self.cloud),
                              ("markup", "Marks text with", self.markup),
                              ("text_color", "Text color", self.text_color),
                              ("stroke", "Line color", stroke_row),
                              ("fill", "Fill", fill_row),
                              ("width", "Line width", self.width),
                              ("fontsize", "Font size", self.fontsize),
                              ("head", "Arrowhead", self.head),
                              ("rotation", "Rotation", self.rotation),
                              ("opacity", "Opacity", self.opacity)):
            lab = QLabel(label)
            self.form.addRow(lab, w)
            self.rows[key] = (lab, w)

        self.reset = QPushButton("Reset defaults")
        self.reset.clicked.connect(self.resetRequested.emit)
        outer.addWidget(self.reset)
        outer.addStretch(1)

        for b in (self.stroke, self.fill, self.text_color):
            b.changed.connect(self._emit)
        self.no_fill.toggled.connect(self._emit)
        self.no_stroke.toggled.connect(self._emit)
        self.width.valueChanged.connect(self._emit)
        self.fontsize.valueChanged.connect(self._emit)
        self.opacity.sliderReleased.connect(self._emit)
        self.head.currentIndexChanged.connect(self._emit)
        self.markup.currentIndexChanged.connect(self._emit)
        self.label.activated.connect(self._emit)
        self.label.lineEdit().editingFinished.connect(self._emit)
        self.date.toggled.connect(self._emit)
        self.name.toggled.connect(self._emit)
        self.rotation.valueChanged.connect(self._emit)
        self.cloud.toggled.connect(self._emit)
        self.show_target(None, None)

    def show_target(self, kind, props, selected=False):
        self._loading = True
        self._kind = kind
        if kind is None:
            self.title.setText("No tool settings")
            self.hint.setText("Pick a markup tool to set its default style, "
                              "or click an annotation to edit it.")
            for lab, w in self.rows.values():
                lab.hide()
                w.hide()
            self.reset.hide()
            self._loading = False
            return
        name = A.LABELS.get(kind, kind)
        self.title.setText(f"Selected: {name}" if selected else f"{name}: default style")
        self.hint.setText("Changes apply to the selected annotation." if selected else
                          "Saved for next time. New annotations use these settings.")
        self.reset.setVisible(not selected)
        for key, (lab, w) in self.rows.items():
            vis = key in props and (key != "rotation" or selected)   # new markups start upright
            lab.setVisible(vis)
            w.setVisible(vis)
        if "rotation" in props:
            quarter = kind in A.QUARTER_TURNS
            self.rotation.setSingleStep(90 if quarter else 5)
            self.rotation.setDecimals(0 if quarter else 1)
            self.rows["rotation"][0].setText("Rotation (90\u00b0 steps)" if quarter else "Rotation")
            r = float(props.get("rotation") or 0)
            self.rotation.setValue(r - 360 if r > 180 else r)
        if "stroke" in props:
            self.stroke.set_color(props["stroke"] or "#000000")
            # only shapes that can stand without an outline offer "No border"
            self.no_stroke.setVisible(kind in BORDERLESS)
            self.no_stroke.setChecked(props["stroke"] is None and kind in BORDERLESS)
            self.rows["stroke"][0].setText("Border color" if kind == "textbox" else
                                           "Color" if kind in A.MARKUP + ("note", "stamp")
                                           else "Line color")
        if "fill" in props:
            self.fill.set_color(props["fill"])
            self.no_fill.setChecked(props["fill"] is None)
        if "text_color" in props:
            self.text_color.set_color(props["text_color"])
        if "width" in props:
            self.width.setValue(float(props["width"]))
            self.rows["width"][0].setText("Border width" if kind == "textbox" else "Line width")
        if "fontsize" in props:
            self.fontsize.setValue(float(props["fontsize"]))
        if "head" in props:
            self.head.setCurrentText(props["head"])
        if "label" in props:
            self._fill_labels(props["label"])
        if "date" in props:
            self.date.setChecked(bool(props["date"]))
        if "name" in props:
            self.name.setChecked(bool(props["name"]))
        if "cloud" in props:
            self.cloud.setChecked(bool(props["cloud"]))
        if "markup" in props:
            self.markup.setCurrentIndex(A.COMMENT_STYLES.index(props["markup"])
                                        if props["markup"] in A.COMMENT_STYLES else 0)
        if "opacity" in props:
            self.opacity.setValue(int(round(float(props["opacity"]) * 100)))
        self._props = dict(props)
        self._loading = False

    def _fill_labels(self, current):
        self.label.clear()
        for t in ST.PRESETS:
            self.label.addItem(t, t)
        for f in ST.library():
            self.label.addItem("Image: " + f, ST.IMAGE_PREFIX + f)
        if current and self.label.findData(current) < 0:
            self.label.addItem(current, current)          # custom text stamp
        self.label.setCurrentIndex(max(0, self.label.findData(current)))

    def _add_image_stamp(self):
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(self, "Image stamp", "",
                                              "Images (*.png *.jpg *.jpeg *.bmp)")
        if not path:
            return
        name = ST.add_to_library(path)
        self._loading = True
        self._fill_labels(ST.IMAGE_PREFIX + name)
        self._loading = False
        self._emit()

    def _emit(self, *_):
        if self._loading or self._kind is None:
            return
        p = dict(self._props)
        if "stroke" in p:
            no = self.no_stroke.isChecked() and self._kind in BORDERLESS
            p["stroke"] = None if no else (self.stroke.color() or "#000000")
        if "fill" in p:
            if self.no_fill.isChecked():
                p["fill"] = None
            else:
                p["fill"] = self.fill.color() or "#ffffff"
                if self.fill.color() is None:
                    self._loading = True
                    self.fill.set_color("#ffffff")
                    self._loading = False
        if "text_color" in p:
            p["text_color"] = self.text_color.color()
        if "width" in p:
            p["width"] = self.width.value()
        if "fontsize" in p:
            p["fontsize"] = self.fontsize.value()
        if "head" in p:
            p["head"] = self.head.currentText()
        if "markup" in p:
            p["markup"] = A.COMMENT_STYLES[self.markup.currentIndex()]
        if "label" in p:
            data = self.label.currentData()
            text = self.label.currentText().strip()
            p["label"] = data if data and self.label.itemText(self.label.currentIndex()) == text \
                else (text.upper() or "APPROVED")
        if "date" in p:
            p["date"] = self.date.isChecked()
        if "name" in p:
            p["name"] = self.name.isChecked()
        if "cloud" in p:
            p["cloud"] = self.cloud.isChecked()
        if "opacity" in p:
            p["opacity"] = self.opacity.value() / 100
        if "rotation" in p:
            v = self.rotation.value()
            if self._kind in A.QUARTER_TURNS:
                v = round(v / 90.0) * 90
            old = float(p.get("rotation") or 0)
            p["rotation"] = old if abs(((v - old + 180) % 360) - 180) < 1e-6 else v % 360
        self._props = p
        self.propsChanged.emit(p)
