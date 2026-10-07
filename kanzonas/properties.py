"""Properties panel: edits the selected annotation, or the current tool's saved defaults."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPixmap, QIcon
from PySide6.QtWidgets import (QWidget, QFormLayout, QVBoxLayout, QLabel, QToolButton,
                               QCheckBox, QDoubleSpinBox, QSlider, QComboBox, QHBoxLayout,
                               QColorDialog, QPushButton)

from . import annotations as A


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
        c = QColorDialog.getColor(start, self, "Choose colour")
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
        self.markup = QComboBox()
        self.markup.addItems([m.capitalize() for m in A.COMMENT_STYLES])

        self.rows = {}
        for key, label, w in (("markup", "Marks text with", self.markup),
                              ("text_color", "Text colour", self.text_color),
                              ("stroke", "Line colour", self.stroke),
                              ("fill", "Fill", fill_row),
                              ("width", "Line width", self.width),
                              ("fontsize", "Font size", self.fontsize),
                              ("head", "Arrowhead", self.head),
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
        self.width.valueChanged.connect(self._emit)
        self.fontsize.valueChanged.connect(self._emit)
        self.opacity.sliderReleased.connect(self._emit)
        self.head.currentIndexChanged.connect(self._emit)
        self.markup.currentIndexChanged.connect(self._emit)
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
            vis = key in props
            lab.setVisible(vis)
            w.setVisible(vis)
        if "stroke" in props:
            self.stroke.set_color(props["stroke"])
            self.rows["stroke"][0].setText("Border colour" if kind == "textbox" else
                                           "Colour" if kind in A.MARKUP + ("note",)
                                           else "Line colour")
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
        if "markup" in props:
            self.markup.setCurrentIndex(A.COMMENT_STYLES.index(props["markup"])
                                        if props["markup"] in A.COMMENT_STYLES else 0)
        if "opacity" in props:
            self.opacity.setValue(int(round(float(props["opacity"]) * 100)))
        self._props = dict(props)
        self._loading = False

    def _emit(self, *_):
        if self._loading or self._kind is None:
            return
        p = dict(self._props)
        if "stroke" in p:
            p["stroke"] = self.stroke.color()
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
        if "opacity" in p:
            p["opacity"] = self.opacity.value() / 100
        self._props = p
        self.propsChanged.emit(p)
