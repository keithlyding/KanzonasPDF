"""Properties panel: edits the selected annotation, or the current tool's saved defaults."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPixmap, QIcon
from PySide6.QtWidgets import (QWidget, QFormLayout, QVBoxLayout, QLabel, QToolButton,
                               QCheckBox, QDoubleSpinBox, QSlider, QComboBox, QHBoxLayout,
                               QSpinBox,
                               QColorDialog, QPushButton, QLineEdit)

from . import annotations as A
from . import stamps as ST
from .i18n import tr

# arrowhead and comment-mark names as shown (the stored values are the keys)
HEAD_NAMES = {"open": tr("open"), "closed": tr("closed"), "open (reversed)": tr("open (reversed)"),
              "closed (reversed)": tr("closed (reversed)"), "circle": tr("circle"),
              "square": tr("square"), "diamond": tr("diamond"), "bar": tr("bar"),
              # a dimension's (dimensions.HEADS): an architect's slash, a dot, or none
              "slash": tr("slash"), "dot": tr("dot"), "none": tr("none")}
MARKUP_NAMES = {"highlight": tr("Highlight"), "underline": tr("Underline"),
                "strikeout": tr("Strikeout"), "squiggly": tr("Squiggly")}

BORDERLESS = ("textbox", "callout", "rect", "ellipse", "circle", "mask", "polygon", "m_area",
              "m_perimeter", "m_volume")


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
            self.setText(tr("none"))
        self.setIcon(QIcon(pm))

    def _pick(self):
        start = QColor(self._color) if self._color else QColor("#ffffff")
        c = QColorDialog.getColor(start, self, tr("Choose color"))
        if c.isValid():
            self.set_color(c.name())
            self.changed.emit()


class PropertiesPanel(QWidget):
    propsChanged = Signal(dict)      # full props dict after a user change
    resetRequested = Signal()

    def __init__(self):
        super().__init__()
        self._kind = None
        self._selected = False
        self._props = {}
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
        self.no_stroke = QCheckBox(tr("No border"))
        stroke_row = QWidget()
        sl = QHBoxLayout(stroke_row)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.addWidget(self.stroke)
        sl.addWidget(self.no_stroke)
        self.fill = ColorButton(allow_none=True)
        self.no_fill = QCheckBox(tr("No fill"))
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
        self.depth = QDoubleSpinBox()
        self.depth.setRange(0, 1_000_000)
        self.depth.setDecimals(3)
        self.depth.setKeyboardTracking(False)
        self.depth.setToolTip(tr("Volume = area \u00d7 depth. The depth is in the page's scale "
                                 "unit (feet when the scale is in feet and inches)."))
        self.opacity = QSlider(Qt.Horizontal)
        self.opacity.setRange(10, 100)
        self.head = QComboBox()
        self._heads = None
        self._fill_heads(None)
        self.label = QComboBox()            # stamp choice
        self.label.setEditable(True)
        self.label.setInsertPolicy(QComboBox.NoInsert)
        self.label.lineEdit().setPlaceholderText(tr("Type your own stamp text"))
        self.add_image = QPushButton(tr("Add image stamp..."))
        self.add_image.clicked.connect(self._add_image_stamp)
        label_row = QWidget()
        lr = QVBoxLayout(label_row)
        lr.setContentsMargins(0, 0, 0, 0)
        lr.addWidget(self.label)
        lr.addWidget(self.add_image)
        self.name = QCheckBox(tr("Add my name"))
        self.name.setToolTip(tr("Your name is set in Edit > Author name for markups"))
        self.date = QCheckBox(tr("Add the date"))
        self.rotation = QDoubleSpinBox()
        self.rotation.setRange(-360, 360)
        self.rotation.setDecimals(1)
        self.rotation.setSuffix("\u00b0")
        self.rotation.setWrapping(True)
        self.rotation.setKeyboardTracking(False)
        self.rotation.setToolTip(tr("Counterclockwise. You can also drag the round handle above "
                                    "a selected shape (hold Shift for 15\u00b0 steps)."))
        self.cloud = QCheckBox(tr("Cloud border"))
        self.for_who = QComboBox()
        self.for_who.addItem(tr("Initials"), "initials")
        self.for_who.addItem(tr("Signature"), "signature")
        self.markup = QComboBox()
        self.markup.addItems([MARKUP_NAMES.get(m, m) for m in A.COMMENT_STYLES])
        # font: the installed fonts for text written into the page (Add text, Edit text);
        # Helvetica / Times / Courier for text box comments (fonts every PDF viewer has)
        self.font = QComboBox()
        self.font.setMaxVisibleItems(20)
        self.bold = QCheckBox(tr("Bold"))
        self.italic = QCheckBox(tr("Italic"))
        font_row = QWidget()
        fr = QVBoxLayout(font_row)
        fr.setContentsMargins(0, 0, 0, 0)
        fr.addWidget(self.font)
        style_row = QHBoxLayout()
        style_row.addWidget(self.bold)
        style_row.addWidget(self.italic)
        style_row.addStretch(1)
        fr.addLayout(style_row)
        self._font_kind = None
        # a legend's options (legend.py)
        self.title_edit = QLineEdit()
        self.scope = QComboBox()
        self.scope.addItem(tr("This page"), "page")
        self.scope.addItem(tr("Whole document"), "document")
        self.scope.setToolTip(tr("Which markups the legend lists: those on its page, or those "
                                 "on every page"))
        self.show_count = QCheckBox(tr("Show the count"))
        self.show_totals = QCheckBox(tr("Show measurement totals"))
        self.show_totals.setToolTip(tr("Total length, area or volume of each kind of "
                                       "measurement, in the page's units"))
        self.border = QCheckBox(tr("Border"))
        # (issue #90) a text box's or callout's height follows its text
        self.fit = QCheckBox(tr("Fit the box to its text"))
        self.fit.setToolTip(tr("The box grows or shrinks to its text as you type or change "
                               "the font size; its width stays, and the text wraps in it. "
                               "Changing its height by hand turns this off."))
        # a dot's options (dots.py)
        self.filled = QComboBox()
        self.filled.addItem(tr("Filled"), True)
        self.filled.addItem(tr("Outline only"), False)
        self.dot_size = QDoubleSpinBox()
        self.dot_size.setRange(1, 72)
        self.dot_size.setSuffix(" pt")
        self.dot_size.setKeyboardTracking(False)
        self.dot_show = QComboBox()
        self.dot_show.addItem(tr("Nothing"), "none")
        self.dot_show.addItem(tr("Number"), "number")
        self.dot_show.addItem(tr("Text"), "text")
        self.dot_show.addItem(tr("Number and text"), "both")
        self.dot_show.setToolTip(tr("What is written with the dot. Its text is asked for when "
                                    "you place it; double-click a dot to change it."))
        self.side = QComboBox()
        self.side.addItem(tr("Right"), "right")
        self.side.addItem(tr("Below"), "below")
        self.side.addItem(tr("Left"), "left")
        self.side.addItem(tr("Above"), "above")
        self.side.setToolTip(tr("Where the number or the text goes. With both, the text goes "
                                "here and the number on the other side of the dot."))
        self.inside = QCheckBox(tr("Number inside the dot"))
        self.number = QSpinBox()
        self.number.setRange(0, 999999)
        self.number.setKeyboardTracking(False)
        self.number.setToolTip(tr("New dots take the next number after the highest one in "
                                  "the document."))

        self.rows = {}
        for key, label, w in (("title", tr("Title"), self.title_edit),
                              ("scope", tr("Markups from"), self.scope),
                              ("count", "", self.show_count),
                              ("totals", "", self.show_totals),
                              ("border", "", self.border),
                              ("fit", "", self.fit),
                              ("label", tr("Stamp"), label_row),
                              ("name", "", self.name),
                              ("date", "", self.date),
                              ("cloud", "", self.cloud),
                              ("markup", tr("Marks text with"), self.markup),
                              ("for", tr("Placeholder for"), self.for_who),
                              ("filled", tr("Dot"), self.filled),
                              ("size", tr("Dot size"), self.dot_size),
                              ("show", tr("Shows"), self.dot_show),
                              ("n", tr("Number"), self.number),
                              ("side", tr("Position"), self.side),
                              ("inside", "", self.inside),
                              ("font", tr("Font"), font_row),
                              ("text_color", tr("Text color"), self.text_color),
                              ("stroke", tr("Line color"), stroke_row),
                              ("fill", tr("Fill"), fill_row),
                              ("width", tr("Line width"), self.width),
                              ("fontsize", tr("Font size"), self.fontsize),
                              ("head", tr("Arrowhead"), self.head),
                              ("depth", tr("Depth"), self.depth),
                              ("rotation", tr("Rotation"), self.rotation),
                              ("opacity", tr("Opacity"), self.opacity)):
            lab = QLabel(label)
            self.form.addRow(lab, w)
            self.rows[key] = (lab, w)

        self.reset = QPushButton(tr("Reset defaults"))
        self.reset.clicked.connect(self.resetRequested.emit)
        outer.addWidget(self.reset)
        outer.addStretch(1)

        for b in (self.stroke, self.fill, self.text_color):
            b.changed.connect(self._emit)
        self.no_fill.toggled.connect(self._emit)
        self.no_stroke.toggled.connect(self._emit)
        self.width.valueChanged.connect(self._emit)
        self.fontsize.valueChanged.connect(self._emit)
        self.depth.valueChanged.connect(self._emit)
        self.opacity.sliderReleased.connect(self._emit)
        # (a click on the slider's track or the arrow keys move it without a release: they
        # apply too; a drag applies once, when it's let go)
        self.opacity.valueChanged.connect(
            lambda _v: None if self.opacity.isSliderDown() else self._emit())
        self.head.currentIndexChanged.connect(self._emit)
        self.markup.currentIndexChanged.connect(self._emit)
        self.for_who.currentIndexChanged.connect(self._emit)
        self.label.activated.connect(self._emit)
        self.label.lineEdit().editingFinished.connect(self._emit)
        self.date.toggled.connect(self._emit)
        self.name.toggled.connect(self._emit)
        self.rotation.valueChanged.connect(self._emit)
        self.cloud.toggled.connect(self._emit)
        self.font.currentIndexChanged.connect(self._emit)
        self.bold.toggled.connect(self._emit)
        self.italic.toggled.connect(self._emit)
        self.title_edit.editingFinished.connect(self._emit)
        self.scope.currentIndexChanged.connect(self._emit)
        self.show_count.toggled.connect(self._emit)
        self.show_totals.toggled.connect(self._emit)
        self.border.toggled.connect(self._emit)
        self.fit.toggled.connect(self._emit)
        self.filled.currentIndexChanged.connect(self._emit)
        self.dot_size.valueChanged.connect(self._emit)
        self.dot_show.currentIndexChanged.connect(self._emit)
        self.side.currentIndexChanged.connect(self._emit)
        self.inside.toggled.connect(self._emit)
        self.number.valueChanged.connect(self._emit)
        self.show_target(None, None)

    def show_target(self, kind, props, selected=False):
        self._loading = True
        self._kind = kind
        if kind is None:
            self.title.setText(tr("No tool settings"))
            self.title.setStyleSheet("font-weight: bold;")
            self.hint.setText(tr("Pick a markup tool to set its default style, "
                                 "or click an annotation to edit it."))
            for lab, w in self.rows.values():
                lab.hide()
                w.hide()
            self.reset.hide()
            self._loading = False
            return
        name = A.LABELS.get(kind, kind)
        self.title.setText(tr("Selected: {name}").format(name=name) if selected else
                           tr("{name}: default style").format(name=name))
        # which one changes, at a glance: a markup on the page (blue) or the tool's style for
        # the next ones (amber); the owner changed a tool's style thinking it was the markup
        # just drawn (10 Nov)
        self.title.setStyleSheet(
            "font-weight: bold; padding: 3px 5px; border-radius: 3px; background: %s;"
            % ("rgba(45, 108, 223, 0.28)" if selected else "rgba(230, 160, 0, 0.28)"))
        self.hint.setText(tr("Changes apply to the selected annotation.") if selected else
                          tr("The line being edited: a font or size picked here changes that "
                             "line only.") if kind == "edittext" else
                          tr("Used for the text you add next; it's written into the page.")
                          if kind in A.PAGE_TEXT_TOOLS else
                          tr("Click the page to place a dot. When it shows a text, you type it "
                             "after the click; double-click a dot to change its text.")
                          if kind == "dot" else
                          tr("For the next ones you make with this tool, saved for next time. "
                             "To change one already on the page, click it first; right-click "
                             "one and choose Set as Default to use its style here."))
        self.reset.setVisible(not selected)
        for key, (lab, w) in self.rows.items():
            # (new markups start upright; a new dot takes the next number)
            vis = key in props and (key not in ("rotation", "n") or selected)
            lab.setVisible(vis)
            w.setVisible(vis)
        if "rotation" in props:
            quarter = kind in A.QUARTER_TURNS
            self.rotation.setSingleStep(90 if quarter else 5)
            self.rotation.setDecimals(0 if quarter else 1)
            self.rows["rotation"][0].setText(tr("Rotation (90\u00b0 steps)") if quarter
                                                else tr("Rotation"))
            r = float(props.get("rotation") or 0)
            self.rotation.setValue(r - 360 if r > 180 else r)
        if "stroke" in props:
            self.stroke.set_color(props["stroke"] or "#000000")
            # only shapes that can stand without an outline offer "No border"
            self.no_stroke.setVisible(kind in BORDERLESS)
            self.no_stroke.setChecked(props["stroke"] is None and kind in BORDERLESS)
            self.rows["stroke"][0].setText(tr("Border color") if kind in ("textbox", "legend") else
                                           tr("Color") if kind in A.MARKUP + ("note", "stamp",
                                                                               "dot")
                                           else tr("Line color"))
        if "fill" in props:
            self.fill.set_color(props["fill"])
            self.no_fill.setChecked(props["fill"] is None)
        if "text_color" in props:
            self.text_color.set_color(props["text_color"])
        if "width" in props:
            self.width.setValue(float(props["width"]))
            self.rows["width"][0].setText(tr("Border width") if kind in ("textbox", "dot")
                                          else tr("Line width"))
        if "fontsize" in props:
            keep = kind == "edittext"          # 0 = keep each line's own size
            self.fontsize.setMinimum(0 if keep else 4)
            self.fontsize.setSpecialValueText(tr("Keep the line's size") if keep else "")
            self.fontsize.setValue(float(props["fontsize"]))
            self.rows["fontsize"][0].setText(tr("Text size") if kind == "legend"
                                             else tr("Font size"))
        if "head" in props:
            self._fill_heads(kind)
            self.head.setCurrentIndex(max(0, self.head.findData(props["head"])))
        if "depth" in props:
            self.depth.setValue(float(props["depth"] or 0))
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
        if "for" in props:
            self.for_who.setCurrentIndex(max(0, self.for_who.findData(props["for"])))
        if "title" in props:
            self.title_edit.setText(props["title"] or "")
        if "scope" in props:
            self.scope.setCurrentIndex(max(0, self.scope.findData(props["scope"])))
        if "count" in props:
            self.show_count.setChecked(bool(props["count"]))
        if "totals" in props:
            self.show_totals.setChecked(bool(props["totals"]))
        if "border" in props:
            self.border.setChecked(bool(props["border"]))
        if "fit" in props:
            self.fit.setChecked(bool(props["fit"]))
        if "filled" in props:
            self.filled.setCurrentIndex(0 if props["filled"] else 1)
        if "size" in props:
            self.dot_size.setValue(float(props["size"]))
        if "show" in props:
            self.dot_show.setCurrentIndex(max(0, self.dot_show.findData(props["show"])))
        if "side" in props:
            self.side.setCurrentIndex(max(0, self.side.findData(props["side"])))
        if "inside" in props:
            self.inside.setChecked(bool(props["inside"]))
        if "n" in props:
            self.number.setValue(int(props["n"] or 0))
        if "font" in props:
            self._fill_fonts(kind, props.get("font") or "")
            page_text = kind != "textbox"           # comments can't use bold / italic fonts
            self.bold.setVisible(page_text)
            self.italic.setVisible(page_text)
            self.bold.setChecked(bool(props.get("bold")))
            self.italic.setChecked(bool(props.get("italic")))
        self._props = dict(props)
        self._selected = selected
        self._dot_rows()
        self._loading = False

    def _dot_rows(self):
        """A dot's rows that mean something for what it shows (none of them when it shows
        nothing but itself)."""
        p = self._props
        if self._kind != "dot":
            return
        show = self.dot_show.currentData()
        number = show in ("number", "both")
        inside = number and self.inside.isChecked()
        for key, vis in (("n", number and self._selected),
                         ("inside", number),
                         ("side", show != "none" and not (show == "number" and inside)),
                         ("text_color", show != "none"),
                         ("fontsize", show != "none")):
            if key in p:
                lab, w = self.rows[key]
                lab.setVisible(vis)
                w.setVisible(vis)

    def _fill_heads(self, kind):
        """The arrowheads the kind of markup can have (a dimension's own set)."""
        from . import dimensions
        keys = tuple(dimensions.HEADS) if kind == "m_dim" else tuple(A.HEADS)
        if keys != self._heads:
            self.head.clear()
            for key in keys:
                self.head.addItem(HEAD_NAMES.get(key, key), key)
            self._heads = keys

    def _fill_fonts(self, kind, current):
        if self._font_kind != kind:
            self.font.clear()
            if kind == "textbox":
                for name in A.COMMENT_FONTS:
                    self.font.addItem(name, name)
            else:
                from PySide6.QtGui import QFontDatabase
                if kind == "edittext":
                    self.font.addItem(tr("Keep the line's font"), "")
                else:
                    self.font.addItem(tr("Helvetica (built into every PDF reader)"), "")
                for fam in QFontDatabase.families():
                    if not QFontDatabase.isPrivateFamily(fam):
                        self.font.addItem(fam, fam)
            self._font_kind = kind
        i = self.font.findData(current)
        self.font.setCurrentIndex(max(0, i))

    def _fill_labels(self, current):
        self.label.clear()
        for t in ST.PRESETS:
            self.label.addItem(t, t)
        for t in ST.FORM_PRESETS:
            self.label.addItem(tr("Fill-in: {name}").format(name=ST.form_title(t)), t)
        for f in ST.library():
            self.label.addItem(tr("Image: {name}").format(name=f), ST.IMAGE_PREFIX + f)
        if current and self.label.findData(current) < 0:
            self.label.addItem(current, current)          # custom text stamp
        self.label.setCurrentIndex(max(0, self.label.findData(current)))

    def _add_image_stamp(self):
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(self, tr("Image stamp"), "",
                                              tr("Images") + " (*.png *.jpg *.jpeg *.bmp)")
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
            p["head"] = self.head.currentData() or self.head.currentText()
        if "depth" in p:
            p["depth"] = self.depth.value()
        if "markup" in p:
            p["markup"] = A.COMMENT_STYLES[self.markup.currentIndex()]
        if "label" in p:
            data = self.label.currentData()
            text = self.label.currentText().strip()
            p["label"] = data if data and self.label.itemText(self.label.currentIndex()) == text \
                else (text.upper() or tr("APPROVED"))
        if "date" in p:
            p["date"] = self.date.isChecked()
        if "name" in p:
            p["name"] = self.name.isChecked()
        if "cloud" in p:
            p["cloud"] = self.cloud.isChecked()
        if "opacity" in p:
            p["opacity"] = self.opacity.value() / 100
        if "for" in p:
            p["for"] = self.for_who.currentData()
        if "font" in p:
            p["font"] = self.font.currentData() or ""
            if self._kind != "textbox":
                p["bold"] = self.bold.isChecked()
                p["italic"] = self.italic.isChecked()
        if "title" in p:
            p["title"] = self.title_edit.text().strip()
        if "scope" in p:
            p["scope"] = self.scope.currentData() or "page"
        if "count" in p:
            p["count"] = self.show_count.isChecked()
        if "totals" in p:
            p["totals"] = self.show_totals.isChecked()
        if "border" in p:
            p["border"] = self.border.isChecked()
        if "fit" in p:
            p["fit"] = self.fit.isChecked()
        if "filled" in p:
            p["filled"] = bool(self.filled.currentData())
        if "size" in p:
            p["size"] = self.dot_size.value()
        if "show" in p:
            p["show"] = self.dot_show.currentData() or "number"
        if "side" in p:
            p["side"] = self.side.currentData() or "right"
        if "inside" in p:
            p["inside"] = self.inside.isChecked()
        if "n" in p:
            p["n"] = self.number.value()
        if "rotation" in p:
            v = self.rotation.value()
            if self._kind in A.QUARTER_TURNS:
                v = round(v / 90.0) * 90
            old = float(p.get("rotation") or 0)
            p["rotation"] = old if abs(((v - old + 180) % 360) - 180) < 1e-6 else v % 360
        self._props = p
        self._dot_rows()
        self.propsChanged.emit(p)
