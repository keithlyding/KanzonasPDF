"""Document-wide page tools: headers & footers (page numbers, Bates numbers, dates),
watermarks, and file compression. All are written into the page content.

Header/footer tokens: {page} {pages} {date} {file} {bates}
"""

import os
from datetime import date

import pymupdf
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QGridLayout, QFormLayout, QLineEdit,
                               QLabel, QSpinBox, QDoubleSpinBox, QComboBox, QDialogButtonBox,
                               QCheckBox, QGroupBox, QSlider, QHBoxLayout, QPushButton,
                               QFileDialog, QWidget)

from .properties import ColorButton
from . import annotations as A

POSITIONS = [("header", "left"), ("header", "center"), ("header", "right"),
             ("footer", "left"), ("footer", "center"), ("footer", "right")]
_ALIGN = {"left": pymupdf.TEXT_ALIGN_LEFT, "center": pymupdf.TEXT_ALIGN_CENTER,
          "right": pymupdf.TEXT_ALIGN_RIGHT}


def parse_pages(text, count):
    """'1-3, 5, 8-' -> [0, 1, 2, 4, 7, ...]; empty = all pages."""
    text = (text or "").strip()
    if not text:
        return list(range(count))
    out = set()
    for part in text.replace(" ", "").split(","):
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            a = int(a) if a else 1
            b = int(b) if b else count
        else:
            a = b = int(part)
        if a < 1 or b > count or a > b:
            raise ValueError(f"Page range {part} is outside 1-{count}.")
        out.update(range(a - 1, b))
    return sorted(out)


def _fill(template, i, total, file_name, bates):
    return (template.replace("{page}", str(i + 1)).replace("{pages}", str(total))
            .replace("{date}", date.today().strftime("%m/%d/%Y"))
            .replace("{file}", file_name).replace("{bates}", bates))


def add_header_footer(doc, spec, file_name):
    """spec: {"texts": {(where, align): template}, "size", "color", "margin", "pages",
              "bates_prefix", "bates_start", "bates_digits"}"""
    total = doc.page_count
    color = A.to_rgb(spec.get("color") or "#000000")
    size = float(spec.get("size", 9))
    margin = float(spec.get("margin", 24))
    for n, i in enumerate(spec["pages"]):
        page = doc[i]
        bates = f"{spec.get('bates_prefix', '')}{spec.get('bates_start', 1) + n:0{spec.get('bates_digits', 6)}d}"
        disp = page.rect                                    # displayed size
        for (where, align), template in spec["texts"].items():
            if not template.strip():
                continue
            text = _fill(template, i, total, file_name, bates)
            h = size * 2.4                 # insert_textbox drops text that doesn't fit
            y0 = margin - size if where == "header" else disp.height - margin - size * 1.4
            box = pymupdf.Rect(margin, y0, disp.width - margin, y0 + h)
            box = box * page.derotation_matrix
            rc = page.insert_textbox(box, text, fontsize=size, fontname="helv", color=color,
                                     align=_ALIGN[align], rotate=page.rotation)
            if rc < 0:
                raise ValueError(f"\"{text}\" doesn't fit across the page at {size:g} pt.")


def add_watermark(doc, spec):
    """spec: {"text", "size", "color", "opacity", "angle", "pages", "behind"} or
    {"image": path, "opacity", "scale", "pages", "behind"}"""
    for i in spec["pages"]:
        page = doc[i]
        disp = page.rect
        center = pymupdf.Point(disp.width / 2, disp.height / 2) * page.derotation_matrix
        if spec.get("image"):
            pm = pymupdf.Pixmap(spec["image"])
            if pm.alpha == 0:
                pm = pymupdf.Pixmap(pm, 1)              # add alpha channel
            pm.set_alpha(bytes([int(255 * spec.get("opacity", 0.3))]) * (pm.width * pm.height))
            w = disp.width * spec.get("scale", 0.5)
            h = w * pm.height / pm.width
            r = pymupdf.Rect(disp.width / 2 - w / 2, disp.height / 2 - h / 2,
                             disp.width / 2 + w / 2, disp.height / 2 + h / 2) * page.derotation_matrix
            page.insert_image(r, pixmap=pm, overlay=not spec.get("behind"), rotate=page.rotation)
            continue
        text = spec["text"]
        size = float(spec.get("size", 72))
        width = pymupdf.get_text_length(text, fontname="hebo", fontsize=size)
        start = center + (-width / 2, size * 0.35)
        angle = float(spec.get("angle", 45)) + page.rotation
        page.insert_text(start, text, fontsize=size, fontname="hebo",
                         color=A.to_rgb(spec.get("color") or "#ff0000"),
                         fill_opacity=spec.get("opacity", 0.25), stroke_opacity=spec.get("opacity", 0.25),
                         morph=(center, pymupdf.Matrix(angle)), overlay=not spec.get("behind"))


COMPRESS = {"Good quality (150 dpi images)": (200, 150, 80),
            "Smaller (100 dpi images)": (130, 100, 65),
            "Smallest (72 dpi images)": (90, 72, 50)}


def compress(pdf_bytes, out_path, preset):
    """Downsample/recompress images, subset fonts, drop unused objects."""
    threshold, target, quality = COMPRESS[preset]
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    try:
        doc.rewrite_images(dpi_threshold=threshold, dpi_target=target, quality=quality)
    except Exception:
        pass
    try:
        doc.subset_fonts()
    except Exception:
        pass
    doc.save(out_path, garbage=4, deflate=True, deflate_images=True, deflate_fonts=True,
             clean=True, use_objstms=1)
    doc.close()
    return len(pdf_bytes), os.path.getsize(out_path)


# ---- dialogs ----------------------------------------------------------------------
class HeaderFooterDialog(QDialog):
    def __init__(self, parent, page_count):
        super().__init__(parent)
        self.setWindowTitle("Header, footer, page numbers & Bates numbering")
        self.page_count = page_count
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Type text in any position. Tokens: {page}  {pages}  {date}  "
                             "{file}  {bates}"))
        grid = QGridLayout()
        self.edits = {}
        for c, align in enumerate(("Left", "Center", "Right")):
            grid.addWidget(QLabel(align), 0, c + 1)
        for r, where in enumerate(("header", "footer")):
            grid.addWidget(QLabel(where.capitalize()), r + 1, 0)
            for c, align in enumerate(("left", "center", "right")):
                e = QLineEdit()
                grid.addWidget(e, r + 1, c + 1)
                self.edits[(where, align)] = e
        lay.addLayout(grid)
        presets = QHBoxLayout()
        for label, key, val in (("Page X of Y", ("footer", "center"), "Page {page} of {pages}"),
                                ("Bates number", ("footer", "right"), "{bates}"),
                                ("Date", ("header", "right"), "{date}")):
            b = QPushButton(label)
            b.clicked.connect(lambda _=False, k=key, v=val: self.edits[k].setText(v))
            presets.addWidget(b)
        presets.addStretch(1)
        lay.addLayout(presets)
        form = QFormLayout()
        self.size = QDoubleSpinBox()
        self.size.setRange(5, 48)
        self.size.setValue(9)
        self.color = ColorButton()
        self.color.set_color("#000000")
        self.margin = QDoubleSpinBox()
        self.margin.setRange(4, 144)
        self.margin.setValue(24)
        self.margin.setSuffix(" pt")
        self.pages = QLineEdit()
        self.pages.setPlaceholderText(f"All pages (or e.g. 1-3, 5, 8-)")
        self.prefix = QLineEdit("ABC")
        self.start = QSpinBox()
        self.start.setRange(0, 10 ** 8)
        self.start.setValue(1)
        self.digits = QSpinBox()
        self.digits.setRange(1, 12)
        self.digits.setValue(6)
        form.addRow("Font size", self.size)
        form.addRow("Color", self.color)
        form.addRow("Margin from edge", self.margin)
        form.addRow("Pages", self.pages)
        bates = QHBoxLayout()
        bates.addWidget(QLabel("prefix"))
        bates.addWidget(self.prefix)
        bates.addWidget(QLabel("start"))
        bates.addWidget(self.start)
        bates.addWidget(QLabel("digits"))
        bates.addWidget(self.digits)
        form.addRow("Bates numbering", bates)
        lay.addLayout(form)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._ok)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)
        self.spec = None
        self.error = QLabel()
        self.error.setStyleSheet("color: #c00;")
        lay.addWidget(self.error)

    def _ok(self):
        try:
            pages = parse_pages(self.pages.text(), self.page_count)
        except ValueError as e:
            self.error.setText(str(e))
            return
        texts = {k: e.text() for k, e in self.edits.items() if e.text().strip()}
        if not texts:
            self.error.setText("Type something in at least one position.")
            return
        self.spec = {"texts": texts, "size": self.size.value(), "color": self.color.color(),
                     "margin": self.margin.value(), "pages": pages,
                     "bates_prefix": self.prefix.text(), "bates_start": self.start.value(),
                     "bates_digits": self.digits.value()}
        self.accept()


class WatermarkDialog(QDialog):
    def __init__(self, parent, page_count):
        super().__init__(parent)
        self.setWindowTitle("Watermark")
        self.page_count = page_count
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.kind = QComboBox()
        self.kind.addItems(["Text", "Image"])
        self.text = QComboBox()
        self.text.setEditable(True)
        self.text.addItems(["DRAFT", "CONFIDENTIAL", "COPY", "PRELIMINARY", "NOT FOR CONSTRUCTION",
                            "SAMPLE", "VOID"])
        self.image = QLineEdit()
        browse = QPushButton("Browse...")
        browse.clicked.connect(self._browse)
        img_row = QHBoxLayout()
        img_row.addWidget(self.image)
        img_row.addWidget(browse)
        self.size = QDoubleSpinBox()
        self.size.setRange(8, 400)
        self.size.setValue(80)
        self.color = ColorButton()
        self.color.set_color("#ff0000")
        self.angle = QSpinBox()
        self.angle.setRange(-90, 90)
        self.angle.setValue(45)
        self.angle.setSuffix("°")
        self.opacity = QSlider(Qt.Horizontal)
        self.opacity.setRange(5, 100)
        self.opacity.setValue(25)
        self.behind = QCheckBox("Behind page content")
        self.pages = QLineEdit()
        self.pages.setPlaceholderText("All pages (or e.g. 1-3, 5)")
        form.addRow("Type", self.kind)
        form.addRow("Text", self.text)
        form.addRow("Image", img_row)
        form.addRow("Font size", self.size)
        form.addRow("Color", self.color)
        form.addRow("Angle", self.angle)
        form.addRow("Opacity", self.opacity)
        form.addRow("", self.behind)
        form.addRow("Pages", self.pages)
        lay.addLayout(form)
        self.error = QLabel()
        self.error.setStyleSheet("color: #c00;")
        lay.addWidget(self.error)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._ok)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)
        self.spec = None

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(self, "Watermark image", "",
                                              "Images (*.png *.jpg *.jpeg *.bmp)")
        if path:
            self.image.setText(path)
            self.kind.setCurrentText("Image")

    def _ok(self):
        try:
            pages = parse_pages(self.pages.text(), self.page_count)
        except ValueError as e:
            self.error.setText(str(e))
            return
        common = {"pages": pages, "opacity": self.opacity.value() / 100,
                  "behind": self.behind.isChecked()}
        if self.kind.currentText() == "Image":
            if not os.path.isfile(self.image.text()):
                self.error.setText("Choose an image file.")
                return
            self.spec = {**common, "image": self.image.text(), "scale": 0.5}
        else:
            if not self.text.currentText().strip():
                self.error.setText("Type the watermark text.")
                return
            self.spec = {**common, "text": self.text.currentText().strip(),
                         "size": self.size.value(), "color": self.color.color(),
                         "angle": self.angle.value()}
        self.accept()


class PageChoice(QWidget):
    """Current page / All pages / Pages: [1-3, 7]."""

    def __init__(self, page_count, current, default_all=True):
        super().__init__()
        from PySide6.QtWidgets import QRadioButton
        self.page_count, self.current = page_count, current
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        self.r_current = QRadioButton(f"Current page ({current + 1})")
        self.r_all = QRadioButton("All pages")
        self.r_some = QRadioButton("Pages:")
        self.some = QLineEdit()
        self.some.setPlaceholderText("e.g. 1-3, 7")
        self.some.textEdited.connect(lambda _: self.r_some.setChecked(True))
        for w in (self.r_current, self.r_all, self.r_some, self.some):
            row.addWidget(w)
        (self.r_all if default_all else self.r_current).setChecked(True)

    def pages(self):
        """Chosen page indices (raises ValueError for a bad range)."""
        if self.r_current.isChecked():
            return [self.current]
        if self.r_all.isChecked():
            return list(range(self.page_count))
        if not self.some.text().strip():
            raise ValueError("Type the pages, e.g. 1-3, 7.")
        return parse_pages(self.some.text(), self.page_count)


class BackgroundDialog(QDialog):
    """Document > Background...: solid color, gradient or picture behind the page content."""

    def __init__(self, parent, page_count, current):
        super().__init__(parent)
        from . import background as B
        self.setWindowTitle("Background")
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.kind = QComboBox()
        for key, label in (("color", "Solid color"), ("gradient", "Gradient"),
                           ("image", "Picture")):
            self.kind.addItem(label, key)
        form.addRow("Type", self.kind)
        self.color = ColorButton()
        self.color.set_color("#fff7e0")
        self.color_label = QLabel("Color")
        form.addRow(self.color_label, self.color)
        self.color2 = ColorButton()
        self.color2.set_color("#c8daf0")
        form.addRow("Second color", self.color2)
        self.direction = QComboBox()
        for key, label in B.DIRECTIONS.items():
            self.direction.addItem(label, key)
        form.addRow("Direction", self.direction)
        self.image = QLineEdit()
        browse = QPushButton("Browse...")
        browse.clicked.connect(self._browse)
        img_row = QHBoxLayout()
        img_row.addWidget(self.image)
        img_row.addWidget(browse)
        form.addRow("Picture", img_row)
        self.fit = QComboBox()
        for key, label in B.FITS.items():
            self.fit.addItem(label, key)
        form.addRow("Size", self.fit)
        op_row = QHBoxLayout()
        self.opacity = QSlider(Qt.Horizontal)
        self.opacity.setRange(5, 100)
        self.opacity.setValue(100)
        self.op_label = QLabel("100%")
        self.opacity.valueChanged.connect(lambda v: self.op_label.setText(f"{v}%"))
        op_row.addWidget(self.opacity, 1)
        op_row.addWidget(self.op_label)
        form.addRow("Opacity", op_row)
        self.pages = PageChoice(page_count, current)
        form.addRow("Apply to", self.pages)
        lay.addLayout(form)
        note = QLabel("The background goes behind everything on the page and replaces one "
                      "added here before. Document > Remove background takes it off again. "
                      "It can't show through a scanned page (the scan covers the whole page).")
        note.setWordWrap(True)
        lay.addWidget(note)
        self.error = QLabel()
        self.error.setStyleSheet("color: #c00;")
        lay.addWidget(self.error)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._ok)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)
        self._rows = {"color2": self.color2, "direction": self.direction,
                      "image": img_row, "fit": self.fit, "color": self.color}
        self._form = form
        self.kind.currentIndexChanged.connect(self._update)
        self._update()
        self.spec = None
        self.page_list = None

    def _show(self, field, on):
        w = self._form.labelForField(field)
        if isinstance(field, QHBoxLayout):
            for i in range(field.count()):
                field.itemAt(i).widget().setVisible(on)
        else:
            field.setVisible(on)
        if w is not None:
            w.setVisible(on)

    def _update(self):
        kind = self.kind.currentData()
        self._show(self.color, kind != "image")
        self.color_label.setText("First color" if kind == "gradient" else "Color")
        self._show(self.color2, kind == "gradient")
        self._show(self.direction, kind == "gradient")
        self._show(self._rows["image"], kind == "image")
        self._show(self.fit, kind == "image")
        self.adjustSize()

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(self, "Background picture", "",
                                              "Images (*.png *.jpg *.jpeg *.bmp *.tif *.tiff)")
        if path:
            self.image.setText(path)

    def _ok(self):
        try:
            pages = self.pages.pages()
        except ValueError as e:
            self.error.setText(str(e))
            return
        kind = self.kind.currentData()
        spec = {"kind": kind, "opacity": self.opacity.value() / 100}
        if kind == "image":
            if not os.path.isfile(self.image.text()):
                self.error.setText("Choose a picture file.")
                return
            try:
                pymupdf.Pixmap(self.image.text())
            except Exception:
                self.error.setText("That file isn't a picture KanzonasPDF can read.")
                return
            spec.update(image=self.image.text(), fit=self.fit.currentData())
        else:
            spec["color"] = self.color.color()
            if kind == "gradient":
                spec.update(color2=self.color2.color(), direction=self.direction.currentData())
        self.spec, self.page_list = spec, pages
        self.accept()
