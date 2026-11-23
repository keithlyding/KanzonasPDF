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

# the tools that write into the page itself (not markups): Properties tags them "Page content"
PAGE_TOOLS = frozenset(A.PAGE_TEXT_TOOLS) | {"image", "erasecontent", "editobjects"}

# arrowhead and comment-mark names as shown (the stored values are the keys)
HEAD_NAMES = {"open": tr("open"), "closed": tr("closed"), "open (reversed)": tr("open (reversed)"),
              "closed (reversed)": tr("closed (reversed)"), "circle": tr("circle"),
              "square": tr("square"), "diamond": tr("diamond"), "bar": tr("bar"),
              # a dimension's (dimensions.HEADS): an architect's slash, a dot, or none
              "slash": tr("slash"), "dot": tr("dot"), "none": tr("none")}
DASH_NAMES = {"solid": tr("solid"), "dash": tr("dashed"), "dot": tr("dotted"),
              "dashdot": tr("dash-dot")}
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

    def set_mixed(self):
        """Several colors (the page's text selected in several): shown as such; a color
        picked goes to all of it."""
        self.set_color("")
        self.setText(tr("several"))

    def _pick(self):
        start = QColor(self._color) if self._color else QColor("#ffffff")
        c = QColorDialog.getColor(start, self, tr("Choose color"))
        if c.isValid():
            self.set_color(c.name())
            self.changed.emit()


class PropertiesPanel(QWidget):
    propsChanged = Signal(dict)      # full props dict after a user change
    resetRequested = Signal()
    objectsTurn = Signal(float)      # the page's selected objects: turn by degrees (counterclockwise)
    objectsWidth = Signal(float)     # the page's selected objects: their line width (points)
    objectsStyle = Signal(dict)      # their colors, Line style or arrowheads: what changed
    objectsText = Signal(dict)       # the page's text selected: its font, size, style changed
    _obj_text = None                 # its style shown (DocumentView.object_text_style)
    _obj_width = None                # their line width shown ("" when they differ)
    _obj_style = {}                  # their colors, Line style and arrowheads shown
    countLayer = Signal(object)      # a count's layer picked: None (as the Layers tab), 0 (no
    #                                  layer), a layer's xref, or "new"
    newCountGroup = Signal()         # the Count tool: start a new group ("New count")
    countSetup = Signal(str)         # a Count group's quantities per item and waste (takeoff)
    renumberCount = Signal(str)      # a count group with gaps or repeats: number it again

    def __init__(self):
        super().__init__()
        self._kind = None
        self._selected = False
        self.read_only_counts = False   # (a read-only document: no Renumber)
        self._props = {}
        self._loading = False
        outer = QVBoxLayout(self)
        # what's selected or about to be added: a markup (on top of the page; it can be
        # hidden, moved, deleted, flattened) or the page's own content (it changes the page).
        # The owner, 22 Nov 2026: "there needs to be a way of differentiating whether what's
        # being edited and added is a markup vs a document change"
        self.tag = QLabel()
        self.tag.setWordWrap(True)
        self.tag.hide()
        outer.addWidget(self.tag)
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
        # Text background: the page's own text highlighted (a filled box drawn into the page
        # behind its words), not a Highlight markup
        self.text_back = ColorButton()
        self.no_back = QCheckBox(tr("None"))
        back_row = QWidget()
        bl = QHBoxLayout(back_row)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.addWidget(self.text_back)
        bl.addWidget(self.no_back)
        self.text_back.setToolTip(tr("The words highlighted in the page itself, as part of "
                                     "it: not a Highlight markup, which sits on top and can "
                                     "be hidden or deleted."))
        self.width = QDoubleSpinBox()
        self.width.setRange(0, 50)
        self.width.setSingleStep(0.5)
        self.width.setSuffix(" pt")
        self.width.setKeyboardTracking(False)       # (a number typed applies on Enter, once)
        self.fontsize = QDoubleSpinBox()
        self.fontsize.setRange(4, 144)
        self.fontsize.setSuffix(" pt")
        self.fontsize.setKeyboardTracking(False)    # (a size typed applies on Enter, once)
        self.depth = QDoubleSpinBox()
        self.depth.setRange(0, 1_000_000)
        self.depth.setDecimals(3)
        self.depth.setKeyboardTracking(False)
        self.depth.setToolTip(tr("Volume = area \u00d7 depth. The depth is in the page's scale "
                                 "unit (feet when the scale is in feet and inches)."))
        # a Length's or Polylength's height: its wall area shown too (0: none)
        self.height = QDoubleSpinBox()
        self.height.setRange(0, 1_000_000)
        self.height.setDecimals(3)
        self.height.setKeyboardTracking(False)
        self.height.setSpecialValueText(tr("none"))
        self.height.setToolTip(tr("Wall area = length \u00d7 height, for drywall, paint, "
                                  "insulation or masonry. The height is in the page's scale unit "
                                  "(feet when the scale is in feet and inches); 0 for none."))
        self.opacity = QSlider(Qt.Horizontal)
        self.opacity.setRange(10, 100)
        # the fill's own opacity, on top of the markup's (annotations._fill_opacity): the box or
        # shape see-through while its outline and text stay as they are
        self.fill_opacity = QSlider(Qt.Horizontal)
        self.fill_opacity.setRange(0, 100)
        self.fill_opacity.setToolTip(tr("How solid the fill is (100: solid, 0: none). The "
                                        "outline and text keep the Opacity below."))
        self.head = QComboBox()
        self._heads = None
        self._fill_heads(None)
        # a line's start arrowhead, middle arrow and line style (A.LINE_KINDS, and the page's
        # own lines: show_objects)
        self.head_start = QComboBox()
        for key in A.HEADS:
            self.head_start.addItem(HEAD_NAMES.get(key, key), key)
        self.mid = QComboBox()
        for key in A.MIDS:
            self.mid.addItem(HEAD_NAMES.get(key, key), key)
        self.dash = QComboBox()
        for key in A.DASHES:
            self.dash.addItem(DASH_NAMES[key], key)
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
        # the page's own lines and shapes keep no angle: they're turned by what's typed here,
        # and it goes back to 0 (each arrow click turns them 5 degrees more)
        self.turn = QDoubleSpinBox()
        self.turn.setRange(-180, 180)
        self.turn.setWrapping(True)
        self.turn.setDecimals(1)
        self.turn.setSingleStep(5)
        self.turn.setSuffix("\u00b0")
        self.turn.setKeyboardTracking(False)
        self.turn.setToolTip(tr("Counterclockwise (-90 turns a quarter clockwise). You can also "
                                "drag the round handle above them."))
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
        self.underline = QCheckBox(tr("Underline"))
        self.strike = QCheckBox(tr("Strikethrough"))
        font_row = QWidget()
        fr = QVBoxLayout(font_row)
        fr.setContentsMargins(0, 0, 0, 0)
        fr.addWidget(self.font)
        style_row = QHBoxLayout()
        style_row.addWidget(self.bold)
        style_row.addWidget(self.italic)
        style_row.addStretch(1)
        fr.addLayout(style_row)
        # (the page's text: drawn into the page as thin bars, not an Underline markup)
        deco_row = QHBoxLayout()
        deco_row.addWidget(self.underline)
        deco_row.addWidget(self.strike)
        deco_row.addStretch(1)
        fr.addLayout(deco_row)
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
        # a count's options (counts.py; issue #107): its group, whether the group keeps its
        # numbers in order, and the layer it goes on
        self.group = QComboBox()
        self.group.setEditable(True)
        self.group.setInsertPolicy(QComboBox.NoInsert)
        self.group.lineEdit().setPlaceholderText(tr("Type a name for the group"))
        self.group.setToolTip(tr("Markers of one group are numbered together (1, 2, 3...) and "
                                 "totaled together in the Measurement summary and legends. "
                                 "Pick a group of this document or type a new name."))
        self.new_group = QPushButton(tr("New count"))
        self.new_group.setToolTip(tr("Start another count: a new group whose first marker is "
                                     "number 1"))
        self.new_group.clicked.connect(self.newCountGroup.emit)
        group_row = QWidget()
        gr = QHBoxLayout(group_row)
        gr.setContentsMargins(0, 0, 0, 0)
        gr.addWidget(self.group, 1)
        gr.addWidget(self.new_group)
        self.order = QCheckBox(tr("Keep the numbers in order"))
        self.order.setToolTip(tr("Deleting a marker of the group, or moving it to another "
                                 "group, numbers the rest 1, 2, 3... again, with no gaps. Off: "
                                 "the numbers stay as they are, and the next marker takes the "
                                 "number after the highest."))
        # a group whose numbers have gaps or repeats says so, with the fix beside it
        self.gaps = QLabel()
        self.gaps.setWordWrap(True)
        self.gaps.setStyleSheet("color: #b35c00;")
        self.renumber = QPushButton(tr("Renumber"))
        self.renumber.setToolTip(tr("Number the group 1, 2, 3... again, with no gaps or "
                                    "repeats (Ctrl+Z undoes it)"))
        self.renumber.clicked.connect(lambda: self.renumberCount.emit(self._gap_group))
        self._gap_group = ""
        gaps_row = QWidget()
        gl = QHBoxLayout(gaps_row)
        gl.setContentsMargins(0, 0, 0, 0)
        gl.addWidget(self.gaps, 1)
        gl.addWidget(self.renumber)
        # a Count group's quantities per counted item and its waste (takeoff.group_setup)
        self.count_setup = QPushButton(tr("Quantities and waste..."))
        self.count_setup.setToolTip(tr("What each counted item stands for (each fixture = 2 "
                                       "boxes + 1 whip), with their units, and a waste or "
                                       "extra percent: the Measurement summary and the Excel "
                                       "takeoff show the resulting quantities"))
        self.count_setup.clicked.connect(
            lambda: self.countSetup.emit(self._props.get("group") or ""))
        # a roof Area's pitch: its value is the sloped area (measure.slope_factor)
        self.slope = QLineEdit()
        self.slope.setPlaceholderText(tr("6:12 or 30\u00b0"))
        self.slope.setToolTip(tr("A roof's pitch, rise to run (6:12) or in degrees (30\u00b0): the "
                                 "area shown, summed and exported is then the sloped area. "
                                 "Empty for a flat area."))
        # a measurement's waste or extra percent (the takeoff adds it)
        self.waste = QDoubleSpinBox()
        self.waste.setRange(0, 1000)
        self.waste.setDecimals(1)
        self.waste.setSuffix(" %")
        self.waste.setKeyboardTracking(False)
        self.waste.setToolTip(tr("Waste or extra: the Measurement summary and the Excel takeoff "
                                 "show the quantity with it added"))
        self.layer = QComboBox()
        self.layer.setToolTip(tr("The layer the markers go on (Layers tab: show or hide a "
                                 "layer's markups)"))
        self.layer.activated.connect(self._layer_picked)

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
                              ("group", tr("Group"), group_row),
                              ("n", tr("Number"), self.number),
                              ("order", "", self.order),
                              ("gaps", "", gaps_row),
                              ("layer", tr("Layer"), self.layer),
                              ("setup", tr("Takeoff"), self.count_setup),
                              ("waste", tr("Waste / extra"), self.waste),
                              ("slope", tr("Slope"), self.slope),
                              ("side", tr("Position"), self.side),
                              ("inside", "", self.inside),
                              ("font", tr("Font"), font_row),
                              ("text_color", tr("Text color"), self.text_color),
                              ("text_back", tr("Text background"), back_row),
                              ("stroke", tr("Line color"), stroke_row),
                              ("fill", tr("Fill"), fill_row),
                              ("fill_opacity", tr("Fill opacity"), self.fill_opacity),
                              ("width", tr("Line width"), self.width),
                              ("fontsize", tr("Font size"), self.fontsize),
                              ("head_start", tr("Start arrowhead"), self.head_start),
                              ("head", tr("Arrowhead"), self.head),
                              ("mid", tr("Middle arrow"), self.mid),
                              ("dash", tr("Line style"), self.dash),
                              ("depth", tr("Depth"), self.depth),
                              ("height", tr("Height"), self.height),
                              ("rotation", tr("Rotation"), self.rotation),
                              ("turn", tr("Rotate by"), self.turn),
                              ("opacity", tr("Opacity"), self.opacity)):
            lab = QLabel(label)
            self.form.addRow(lab, w)
            self.rows[key] = (lab, w)

        self.reset = QPushButton(tr("Reset defaults"))
        self.reset.clicked.connect(self.resetRequested.emit)
        outer.addWidget(self.reset)
        outer.addStretch(1)

        for b in (self.stroke, self.fill, self.text_color, self.text_back):
            b.changed.connect(self._emit)
        self.no_back.toggled.connect(self._emit)
        self.no_fill.toggled.connect(self._emit)
        self.no_stroke.toggled.connect(self._emit)
        self.width.valueChanged.connect(self._emit)
        self.fontsize.valueChanged.connect(self._emit)
        self.depth.valueChanged.connect(self._emit)
        self.height.valueChanged.connect(self._emit)
        self.waste.valueChanged.connect(self._emit)
        self.slope.editingFinished.connect(self._emit)
        # (a click on the slider's track or the arrow keys move it without a release: they
        # apply too; a drag applies once, when it's let go)
        for slider in (self.opacity, self.fill_opacity):
            slider.sliderReleased.connect(self._emit)
            slider.valueChanged.connect(
                lambda _v, sl=slider: None if sl.isSliderDown() else self._emit())
        self.head.currentIndexChanged.connect(self._emit)
        for c in (self.head_start, self.mid, self.dash):
            c.currentIndexChanged.connect(self._emit)
        self.markup.currentIndexChanged.connect(self._emit)
        self.for_who.currentIndexChanged.connect(self._emit)
        self.label.activated.connect(self._emit)
        self.label.lineEdit().editingFinished.connect(self._emit)
        self.date.toggled.connect(self._emit)
        self.name.toggled.connect(self._emit)
        self.rotation.valueChanged.connect(self._emit)
        self.turn.valueChanged.connect(self._turn_by)
        self.cloud.toggled.connect(self._emit)
        self.font.currentIndexChanged.connect(self._emit)
        self.bold.toggled.connect(self._emit)
        self.italic.toggled.connect(self._emit)
        self.underline.toggled.connect(self._emit)
        self.strike.toggled.connect(self._emit)
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
        self.inside.toggled.connect(self._inside_toggled)
        self.number.valueChanged.connect(self._emit)
        self.group.activated.connect(self._emit)
        self.group.lineEdit().editingFinished.connect(self._emit)
        self.order.toggled.connect(self._emit)
        self.show_target(None, None)

    def show_tag(self, what):
        """The tag above the title: what="markup", "page" (the page's own content) or None."""
        if what is None:
            self.tag.hide()
            return
        if what == "page":
            self.tag.setText(tr("Page content: changes the page itself"))
            self.tag.setToolTip(tr("Written into the page, as its own text, lines and "
                                   "pictures: every viewer shows it and prints it, and it "
                                   "can't be hidden or taken off as a markup can."))
            color = "rgba(0, 150, 136, 0.30)"
        else:
            self.tag.setText(tr("Markup: on top of the page"))
            self.tag.setToolTip(tr("A markup (annotation) sits on top of the page: it can be "
                                   "hidden, moved, deleted or flattened, and the page under "
                                   "it stays as it was."))
            color = "rgba(142, 68, 173, 0.30)"
        self.tag.setStyleSheet("padding: 2px 5px; border-radius: 3px; font-size: 90%%; "
                               "background: %s;" % color)
        self.tag.show()

    def show_target(self, kind, props, selected=False, tool=None):
        """Settings for kind: a markup selected (selected=True), or a tool's settings for the
        next ones. kind None: nothing to set (tool: the tool in use, for the tag above)."""
        self._loading = True
        self._kind = kind
        self._obj_width = None
        self.width.setSpecialValueText("")          # (blank only for objects of mixed widths)
        if kind is None:
            self.show_tag("page" if tool in PAGE_TOOLS else None)
            self.title.setText(tr("No tool settings"))
            self.title.setStyleSheet("font-weight: bold;")
            self.hint.setText(tr("Click the page's own text, lines or pictures to select "
                                 "them; their settings show here.") if tool == "editobjects"
                              else tr("Pick a markup tool to set its default style, "
                                      "or click an annotation to edit it."))
            for lab, w in self.rows.values():
                lab.hide()
                w.hide()
            self.reset.hide()
            self._loading = False
            return
        name = A.LABELS.get(kind, kind)
        self.show_tag("page" if kind in PAGE_TOOLS else "markup")
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
            self.no_fill.setVisible(True)           # (hidden for the page's own shapes)
            self.no_fill.setChecked(props["fill"] is None)
            self.rows["fill"][0].setText(tr("Fill"))
        if "text_color" in props:
            self.text_color.set_color(props["text_color"])
        if "text_back" in props:
            self.text_back.set_color(props["text_back"] or "#ffff00")
            self.no_back.setChecked(not props["text_back"])
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
            self.rows["head"][0].setText(tr("End arrowhead") if kind in A.LINE_KINDS
                                         else tr("Arrowhead"))
        if "head_start" in props and self.head_start.count() != len(A.HEADS):
            # (the page's own lines have fewer: see show_objects)
            self.head_start.clear()
            for key in A.HEADS:
                self.head_start.addItem(HEAD_NAMES.get(key, key), key)
        for key, combo in (("head_start", self.head_start), ("mid", self.mid),
                           ("dash", self.dash)):
            if key in props:
                combo.setCurrentIndex(max(0, combo.findData(props[key])))
        if "depth" in props:
            self.depth.setValue(float(props["depth"] or 0))
        if "height" in props:
            self.height.setValue(float(props["height"] or 0))
        if "waste" in props:
            self.waste.setValue(float(props["waste"] or 0))
        if "slope" in props:
            self.slope.setText(str(props["slope"] or ""))
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
        if "fill_opacity" in props:
            self.fill_opacity.setValue(int(round(float(props["fill_opacity"]) * 100)))
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
            self.number.setMinimum(1 if kind == "m_count" else 0)
            self.number.setValue(int(props["n"] or 0))
            self.number.setToolTip(
                tr("This marker's number. With Keep the numbers in order on, the others of its "
                   "group move up or down to make room.") if kind == "m_count" else
                tr("New dots take the next number after the highest one in the document."))
        if "group" in props:
            self._fill_groups([], props["group"])
            self.new_group.setVisible(not selected)
        if "order" in props:
            self.order.setChecked(bool(props["order"]))
        if "font" in props:
            self._fill_fonts(kind, props.get("font") or "")
            page_text = kind != "textbox"           # comments can't use bold / italic fonts
            self.bold.setVisible(page_text)
            self.italic.setVisible(page_text)
            self.bold.setChecked(bool(props.get("bold")))
            self.italic.setChecked(bool(props.get("italic")))
        for key, box in (("underline", self.underline), ("strike", self.strike)):
            box.setVisible(key in props)
            box.setChecked(bool(props.get(key)))
        self._props = dict(props)
        self._selected = selected
        self._dot_rows()
        self._loading = False

    def _fill_groups(self, names, current):
        was = self._loading
        self._loading = True
        self.group.clear()
        for name in names:
            self.group.addItem(name)
        if self.group.findText(current) < 0:
            self.group.addItem(current)
        self.group.setCurrentIndex(self.group.findText(current))
        self._loading = was

    def count_rows(self, groups, layers, layer, next_n=None, problem="", group=""):
        """A Count marker's extra rows (after show_target): the document's groups to pick
        from, and the layer row. layers: [(xref, name)]; layer: as countLayer gives it.
        next_n: the Count tool's next number (None for a selected marker). problem: the
        group's gaps or repeats, said (counts.problem_text), with Renumber beside it."""
        self._loading = True
        self._gap_group = group
        self.gaps.setText(problem)
        for w in self.rows["gaps"]:
            w.setVisible(bool(problem) and not self.read_only_counts)
        self._fill_groups(groups, self._props.get("group") or "")
        self.layer.clear()
        if next_n is not None:
            self.layer.addItem(tr("As the Layers tab says"), None)
        self.layer.addItem(tr("No layer"), 0)
        for x, name in layers:
            self.layer.addItem(name, x)
        self.layer.addItem(tr("New layer..."), "new")
        i = self.layer.findData(layer)
        self.layer.setCurrentIndex(i if i >= 0 else 0)
        for w in self.rows["layer"]:
            w.setVisible(True)
        for w in self.rows["setup"]:
            w.setVisible(not self.read_only_counts)
        if next_n is not None:
            self.hint.setText(self.hint.text() + "\n" + tr(
                "The next marker: {group} #{n}").format(group=self._props.get("group") or "",
                                                        n=next_n))
        self._loading = False

    def _layer_picked(self, _i):
        if not self._loading:
            self.countLayer.emit(self.layer.currentData())

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
        from . import dimensions, page_objects
        keys = tuple(dimensions.HEADS) if kind == "m_dim" else \
            tuple(page_objects.HEAD_KINDS) if kind == "objects" else tuple(A.HEADS)
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

    _turn_at = 0.0                   # Rotate by: how far they've turned since selected

    def show_objects(self, what, angle=None, text=False, width=None, style=None, turned=0.0,
                     text_style=None):
        """The page's own objects selected (Edit objects, CAD mode): their rotation, and their
        line width. what: what is selected ("1 picture"). angle: the one picture's or group's
        angle as shown (counterclockwise): Rotation turns it to the angle typed; None (lines
        and shapes keep no angle, or several): Rotate by turns them by what's typed. text: text
        is among them (moved, not turned). width: the line width of the shapes with an outline
        among them (points on the page), "" when they differ, None when none has one.
        style: DocumentView.object_style() (their colors, Line style, arrowheads).
        turned: how far they've turned since they were selected (Rotate by shows it, and a
        new number turns them by the difference). text_style: the selected text's style
        (DocumentView.object_text_style), shown in Font, Font size and Text color."""
        self._loading = True
        self._kind = "objects"
        self._props = {}
        self._obj_angle = angle
        self._obj_width = width
        self._obj_style = dict(style or {})
        self._obj_text = dict(text_style) if text_style else None
        self.show_tag("page")
        self.title.setText(tr("Selected: {name}").format(name=what))
        self.title.setStyleSheet("font-weight: bold; padding: 3px 5px; border-radius: 3px; "
                                 "background: rgba(45, 108, 223, 0.28);")
        for lab, w in self.rows.values():
            lab.hide()
            w.hide()
        self.reset.hide()
        if text:
            self.hint.setText(tr("Text is moved, not turned: select only pictures and shapes "
                                 "to rotate them."))
        elif angle is not None:
            self.hint.setText(tr("Rotation turns it about its middle (counterclockwise), as "
                                 "its round handle does."))
            self.rows["rotation"][0].setText(tr("Rotation"))
            self.rotation.setSingleStep(5)
            self.rotation.setDecimals(1)
            self.rotation.setValue(angle)
            for w in self.rows["rotation"]:
                w.show()
        else:
            self.hint.setText(tr("Rotate by turns them about their middle (counterclockwise), "
                                 "as their round handle does. It shows how far they've turned "
                                 "since you selected them."))
            self._turn_at = float(turned or 0.0)
            self.turn.setValue(self._turn_at)
            for w in self.rows["turn"]:
                w.show()
        style = self._obj_style
        # their colors, Line style and the open lines' arrowheads (several that differ:
        # shown blank, and what's picked goes to all)
        from . import page_objects as P
        for key, row, button in (("stroke", "stroke", self.stroke), ("fill", "fill", self.fill)):
            if key in style:
                button.set_color(style[key] or None)
                for w in self.rows[row]:
                    w.show()
        self.no_stroke.setVisible(False)
        self.no_fill.setVisible(False)
        if "stroke" in style:
            self.rows["stroke"][0].setText(tr("Line color"))
        if "fill" in style:
            self.rows["fill"][0].setText(tr("Fill color"))
        if "dash" in style:
            self.dash.setCurrentIndex(self.dash.findData(style["dash"]))
            for w in self.rows["dash"]:
                w.show()
        if "start" in style:
            self._fill_heads("objects")
            for key, row, combo in (("start", "head_start", self.head_start),
                                    ("end", "head", self.head), ("mid", "mid", self.mid)):
                if combo is self.head_start:
                    combo.clear()
                    for k in P.HEAD_KINDS:
                        combo.addItem(HEAD_NAMES.get(k, k), k)
                combo.setCurrentIndex(combo.findData(style[key]))
                for w in self.rows[row]:
                    w.show()
            self.rows["head"][0].setText(tr("End arrowhead"))
        if self._obj_text is not None:
            # the page's text: its font, size, bold, italic, underline, strikethrough and
            # color (several: Font size blank, the color "several"; what's set goes to all)
            st = self._obj_text
            self._fill_fonts("edittext", "")
            self.rows["font"][0].setText(tr("Font"))
            for box, key in ((self.bold, "bold"), (self.italic, "italic"),
                             (self.underline, "underline"), (self.strike, "strike")):
                box.setVisible(True)
                box.setChecked(bool(st.get(key)))
            self.rows["fontsize"][0].setText(tr("Font size"))
            self.fontsize.setSpecialValueText("" if st.get("fontsize") != "" else " ")
            self.fontsize.setValue(float(st["fontsize"]) if st.get("fontsize") != ""
                                   else self.fontsize.minimum())
            if st.get("text_color"):
                self.text_color.set_color(st["text_color"])
            else:
                self.text_color.set_mixed()
            back = st.get("text_back")
            self.no_back.setChecked(back == "-")
            if back and back != "-":
                self.text_back.set_color(back)
            elif back == "":
                self.text_back.set_mixed()
            else:
                self.text_back.set_color("#ffff00")
            for row in ("font", "fontsize", "text_color", "text_back"):
                for w in self.rows[row]:
                    w.show()
            self.hint.setText(self.hint.text() + " " +
                              tr("A text setting writes the text again in the page where it "
                                 "is: each word keeps the rest of its style."))
        if width is not None:
            # (several of different widths: shown blank, and the width typed goes to all)
            self.rows["width"][0].setText(tr("Line width"))
            self.width.setSpecialValueText("" if width != "" else " ")
            self.width.setValue(float(width) if width != "" else self.width.minimum())
            for w in self.rows["width"]:
                w.show()
        self._loading = False

    def _turn_by(self, value):
        """Rotate by: turned by the difference to the number shown before (the arrows step
        it 5 degrees at a time; past 180 it goes on from -180)."""
        if self._loading or self._kind != "objects":
            return
        delta = (value - self._turn_at + 180.0) % 360.0 - 180.0
        self._turn_at = value
        if abs(delta) > 1e-9:
            self.objectsTurn.emit(delta)

    def _inside_toggled(self, on):
        """The number put inside a filled dot reads white on it: a black text color (the
        default) turns white, any other color chosen stays, and either can be changed."""
        if on and not self._loading and self._kind == "dot" and self.filled.currentData() \
                and self.text_color.color().lower() in ("#000000", "#000"):
            self.text_color.set_color("#ffffff")
        self._emit()

    def _emit(self, *_):
        if self._loading or self._kind is None:
            return
        if self._kind == "objects":
            # (the page's text selected: its font, size, style and color, what was changed)
            st = self._obj_text
            if st is not None and self.rows["font"][1].isVisible():
                changed = {}
                for key, box in (("bold", self.bold), ("italic", self.italic),
                                 ("underline", self.underline), ("strike", self.strike)):
                    if box.isChecked() != bool(st.get(key)):
                        changed[key] = box.isChecked()
                font = self.font.currentData() or ""
                if font != (st.get("font") or ""):
                    changed["font"] = font
                size = round(self.fontsize.value(), 2)
                if size >= 1 and (st.get("fontsize") == "" and
                                  self.fontsize.text().strip() != "" or
                                  st.get("fontsize") != "" and
                                  abs(size - float(st.get("fontsize") or 0)) > 1e-6):
                    changed["fontsize"] = size
                color = self.text_color.color()
                if color and color != st.get("text_color"):
                    changed["text_color"] = color
                if self.sender() is self.text_back and self.no_back.isChecked():
                    self._loading = True
                    self.no_back.setChecked(False)      # (a color picked: that one)
                    self._loading = False
                back = "-" if self.no_back.isChecked() else (self.text_back.color() or "")
                if back and back != st.get("text_back"):
                    changed["text_back"] = back
                if changed:
                    st.update(changed)
                    self.fontsize.setSpecialValueText("")
                    self.objectsText.emit(changed)
                    return
            # (colors, Line style, arrowheads: what was changed goes to the selected shapes)
            style, changed = self._obj_style, {}
            for key, value in (("stroke", self.stroke.color()), ("fill", self.fill.color()),
                               ("dash", self.dash.currentData()),
                               ("start", self.head_start.currentData()),
                               ("end", self.head.currentData()),
                               ("mid", self.mid.currentData())):
                if key in style and value and value != style[key]:
                    changed[key] = value
            if changed:
                style.update(changed)
                self.objectsStyle.emit(changed)
                return
            # (Line width: given to the selected shapes when it's another than they have)
            if self._obj_width is not None and self.rows["width"][1].isVisible():
                w = round(self.width.value(), 3)
                if self._obj_width == "" or abs(w - float(self._obj_width)) > 1e-6:
                    self._obj_width = w
                    self.width.setSpecialValueText("")
                    self.objectsWidth.emit(w)
                    return
            # (Rotation of one picture or group: turned by the difference to the angle typed)
            if self._obj_angle is not None:
                delta = self.rotation.value() - self._obj_angle
                delta = (delta + 180.0) % 360.0 - 180.0
                if abs(delta) > 1e-6:
                    self._obj_angle = self.rotation.value()
                    self.objectsTurn.emit(delta)
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
        if "text_back" in p:
            if self.sender() is self.text_back and self.no_back.isChecked():
                self._loading = True
                self.no_back.setChecked(False)          # (a color picked: that one)
                self._loading = False
            p["text_back"] = "" if self.no_back.isChecked() else (self.text_back.color() or "")
        if "width" in p:
            p["width"] = self.width.value()
        if "fontsize" in p:
            p["fontsize"] = self.fontsize.value()
        if "head" in p:
            p["head"] = self.head.currentData() or self.head.currentText()
        for key, combo in (("head_start", self.head_start), ("mid", self.mid),
                           ("dash", self.dash)):
            if key in p:
                p[key] = combo.currentData()
        if "depth" in p:
            p["depth"] = self.depth.value()
        if "height" in p:
            p["height"] = self.height.value()
        if "waste" in p:
            p["waste"] = self.waste.value()
        if "slope" in p:
            p["slope"] = self.slope.text().strip()
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
        if "fill_opacity" in p:
            p["fill_opacity"] = self.fill_opacity.value() / 100
        if "for" in p:
            p["for"] = self.for_who.currentData()
        if "font" in p:
            p["font"] = self.font.currentData() or ""
            if self._kind != "textbox":
                p["bold"] = self.bold.isChecked()
                p["italic"] = self.italic.isChecked()
        for key, box in (("underline", self.underline), ("strike", self.strike)):
            if key in p:
                p[key] = box.isChecked()
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
        if "group" in p:
            from . import counts
            p["group"] = self.group.currentText().strip() or counts.DEFAULT_GROUP
        if "order" in p:
            p["order"] = self.order.isChecked()
        if "rotation" in p:
            v = self.rotation.value()
            if self._kind in A.QUARTER_TURNS:
                v = round(v / 90.0) * 90
            old = float(p.get("rotation") or 0)
            p["rotation"] = old if abs(((v - old + 180) % 360) - 180) < 1e-6 else v % 360
        self._props = p
        self._dot_rows()
        self.propsChanged.emit(p)
