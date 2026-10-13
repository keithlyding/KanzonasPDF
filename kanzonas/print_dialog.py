"""KanzonasPDF's Print window (File > Print, Ctrl+P): printer, copies, pages, orientation and
size on the left, a preview of each sheet as it will print on the right (like Acrobat's and
PDF-XChange's print dialogs; Windows' standard print dialog has no preview)."""

import re

import pymupdf
from PySide6.QtCore import QRectF, QSizeF, Qt
from PySide6.QtGui import QColor, QImage, QPageLayout, QPageSize, QPainter, QPixmap
from PySide6.QtPrintSupport import QPageSetupDialog, QPrinter, QPrinterInfo
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                               QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
                               QPushButton, QRadioButton, QSpinBox, QToolButton, QVBoxLayout,
                               QWidget)

PREVIEW_W, PREVIEW_H = 380, 470
BAND_BYTES = 48 * 1024 * 1024      # largest piece of a page rendered at once when printing


def parse_pages(text, count):
    """'1-3, 5, 8-' -> [0, 1, 2, 4, 7, 8, ...] (0-based, in order, no repeats). ValueError if
    a part isn't a page number or range within 1..count."""
    out = []
    for part in [p.strip() for p in text.replace(";", ",").split(",") if p.strip()]:
        m = re.fullmatch(r"(\d*)\s*-\s*(\d*)|(\d+)", part)
        if not m:
            raise ValueError(part)
        if m.group(3):
            a = b = int(m.group(3))
        else:
            a = int(m.group(1)) if m.group(1) else 1
            b = int(m.group(2)) if m.group(2) else count
        if not (1 <= a <= b <= count):
            raise ValueError(part)
        out += [i - 1 for i in range(a, b + 1) if i - 1 not in out]
    if not out:
        raise ValueError(text)
    return out


class PrintDialog(QDialog):
    def __init__(self, parent, view):
        super().__init__(parent)
        self.view = view
        self.setWindowTitle("Print")
        self.printer = QPrinter(QPrinter.HighResolution)
        self.printer.setFullPage(True)          # we place each page on the sheet ourselves
        self.printer.setDocName(view.path.rsplit("\\", 1)[-1].rsplit("/", 1)[-1])
        self._shown = 0                         # which sheet the preview shows
        self._cache = {}

        left = QFormLayout()
        self.printer_box = QComboBox()
        names = QPrinterInfo.availablePrinterNames()
        default = QPrinterInfo.defaultPrinterName()
        for n in names:
            self.printer_box.addItem(n)
        if default in names:
            self.printer_box.setCurrentText(default)
        if not names:
            self.printer_box.addItem("(no printer installed)")
            self.printer_box.setEnabled(False)
        setup = QPushButton("Page setup...")
        setup.setToolTip("Paper size and margins for this printer")
        setup.clicked.connect(self._page_setup)
        row = QHBoxLayout()
        row.addWidget(self.printer_box, 1)
        row.addWidget(setup)
        left.addRow("Printer", self._wrap(row))
        self.copies = QSpinBox()
        self.copies.setRange(1, 999)
        left.addRow("Copies", self.copies)

        n = view.page_count()
        self.all_pages = QRadioButton(f"All ({n} page{'s' if n != 1 else ''})")
        self.current = QRadioButton(f"Current page ({view.current_page() + 1})")
        self.some = QRadioButton("Pages")
        self.range_text = QLineEdit()
        self.range_text.setPlaceholderText("e.g. 1-3, 5")
        self.all_pages.setChecked(True)
        group = QButtonGroup(self)
        pages = QVBoxLayout()
        for b in (self.all_pages, self.current):
            group.addButton(b)
            pages.addWidget(b)
        group.addButton(self.some)
        some = QHBoxLayout()
        some.addWidget(self.some)
        some.addWidget(self.range_text, 1)
        pages.addLayout(some)
        left.addRow("Pages", self._wrap(pages))

        self.orientation = QComboBox()
        self.orientation.addItems(["Auto (turn each sheet to fit the page)", "Portrait",
                                   "Landscape"])
        left.addRow("Orientation", self.orientation)
        self.size = QComboBox()
        self.size.addItems(["Fit to paper", "Actual size (shrink pages that are too big)"])
        left.addRow("Size", self.size)
        self.markups = QCheckBox("Print markups and form fields")
        self.markups.setChecked(True)
        left.addRow("", self.markups)

        # preview
        self.picture = QLabel()
        self.picture.setFixedSize(PREVIEW_W, PREVIEW_H)
        self.picture.setAlignment(Qt.AlignCenter)
        self.picture.setStyleSheet("background: #8a8a8a;")
        self.prev_b, self.next_b = QToolButton(), QToolButton()
        self.prev_b.setArrowType(Qt.LeftArrow)
        self.next_b.setArrowType(Qt.RightArrow)
        self.prev_b.clicked.connect(lambda: self._step(-1))
        self.next_b.clicked.connect(lambda: self._step(1))
        self.sheet_label = QLabel()
        nav = QHBoxLayout()
        nav.addStretch(1)
        nav.addWidget(self.prev_b)
        nav.addWidget(self.sheet_label)
        nav.addWidget(self.next_b)
        nav.addStretch(1)
        right = QVBoxLayout()
        right.addWidget(self.picture)
        right.addLayout(nav)

        body = QHBoxLayout()
        body.addLayout(left, 1)
        body.addLayout(right)
        self.buttons = QDialogButtonBox(QDialogButtonBox.Cancel)
        self.print_b = self.buttons.addButton("Print", QDialogButtonBox.AcceptRole)
        self.print_b.setDefault(True)
        self.print_b.setEnabled(bool(names))
        self.buttons.accepted.connect(self._accept)
        self.buttons.rejected.connect(self.reject)
        outer = QVBoxLayout(self)
        outer.addLayout(body)
        outer.addWidget(self.buttons)

        for sig in (self.all_pages.toggled, self.current.toggled, self.some.toggled,
                    self.orientation.currentIndexChanged, self.size.currentIndexChanged,
                    self.markups.toggled, self.printer_box.currentIndexChanged):
            sig.connect(self._changed)
        self.range_text.textChanged.connect(lambda _t: (self.some.setChecked(True),
                                                        self._changed()))
        self._apply_printer()
        self._changed()

    @staticmethod
    def _wrap(layout):
        w = QWidget()
        layout.setContentsMargins(0, 0, 0, 0)
        w.setLayout(layout)
        return w

    # ---- settings ---------------------------------------------------------------------
    def _apply_printer(self):
        if self.printer_box.isEnabled():
            self.printer.setPrinterName(self.printer_box.currentText())

    def _page_setup(self):
        self._apply_printer()
        if QPageSetupDialog(self.printer, self).exec():
            self._changed()

    def pages(self):
        """The pages to print (0-based), or None when the range text isn't valid."""
        v = self.view
        if self.current.isChecked():
            return [v.current_page()]
        if self.some.isChecked():
            try:
                return parse_pages(self.range_text.text(), v.page_count())
            except ValueError:
                return None
        return list(range(v.page_count()))

    def sheet(self, i):
        """(paper size in points, page box on the paper in points) for page i."""
        layout = self.printer.pageLayout()
        paper = layout.pageSize().size(QPageSize.Unit.Point)
        w, h = paper.width(), paper.height()
        page = self.view.doc[i].rect                      # as displayed (rotation applied)
        mode = self.orientation.currentIndex()
        landscape = (page.width > page.height) if mode == 0 else mode == 2
        if landscape != (w > h):
            w, h = h, w
        m = layout.margins(QPageLayout.Unit.Point)
        area = QRectF(m.left(), m.top(), w - m.left() - m.right(), h - m.top() - m.bottom())
        if area.width() < 10 or area.height() < 10:
            area = QRectF(0, 0, w, h)
        pw, ph = page.width, page.height
        k = min(area.width() / pw, area.height() / ph)
        if self.size.currentIndex() == 1:
            k = min(1.0, k)                                # actual size, unless too big
        bw, bh = pw * k, ph * k
        box = QRectF(area.x() + (area.width() - bw) / 2, area.y() + (area.height() - bh) / 2,
                     bw, bh)
        return QSizeF(w, h), box

    def _changed(self, *_):
        self._apply_printer()
        self._cache = {}
        pages = self.pages()
        self.print_b.setEnabled(pages is not None and self.printer_box.isEnabled())
        self.range_text.setStyleSheet("" if pages is not None or not self.some.isChecked()
                                      else "background: #ffe0e0;")
        if pages:
            self._shown = min(self._shown, len(pages) - 1)
        self._draw_preview()

    def _step(self, d):
        pages = self.pages() or []
        self._shown = max(0, min(len(pages) - 1, self._shown + d))
        self._draw_preview()

    # ---- preview ----------------------------------------------------------------------
    def _page_image(self, i, dpi):
        pm = self.view.doc[i].get_pixmap(dpi=int(dpi), annots=self.markups.isChecked())
        return QImage(pm.samples, pm.width, pm.height, pm.stride, QImage.Format_RGB888).copy()

    def _draw_preview(self):
        pages = self.pages()
        canvas = QPixmap(PREVIEW_W, PREVIEW_H)
        canvas.fill(QColor("#8a8a8a"))
        if not pages:
            self.picture.setPixmap(canvas)
            self.sheet_label.setText("No pages" if pages == [] else "Check the page numbers")
            self.prev_b.setEnabled(False)
            self.next_b.setEnabled(False)
            return
        i = pages[self._shown]
        paper, box = self.sheet(i)
        k = min((PREVIEW_W - 20) / paper.width(), (PREVIEW_H - 20) / paper.height())
        ox = (PREVIEW_W - paper.width() * k) / 2
        oy = (PREVIEW_H - paper.height() * k) / 2
        target = QRectF(ox + box.x() * k, oy + box.y() * k, box.width() * k, box.height() * k)
        dpi = max(30, min(110, 72 * target.width() / max(1, self.view.doc[i].rect.width) * 1.5))
        img = self._page_image(i, dpi)
        p = QPainter(canvas)
        try:
            p.setRenderHint(QPainter.SmoothPixmapTransform)
            p.fillRect(QRectF(ox + 3, oy + 3, paper.width() * k, paper.height() * k),
                       QColor(0, 0, 0, 60))
            p.fillRect(QRectF(ox, oy, paper.width() * k, paper.height() * k), Qt.white)
            p.drawImage(target, img)
            self._draw_links(p, i, target)
        finally:
            p.end()
        self.picture.setPixmap(canvas)
        self.sheet_label.setText(f"Sheet {self._shown + 1} of {len(pages)} (page {i + 1})")
        self.prev_b.setEnabled(self._shown > 0)
        self.next_b.setEnabled(self._shown < len(pages) - 1)

    # ---- printing ---------------------------------------------------------------------
    def _accept(self):
        pages = self.pages()
        if not pages:
            QMessageBox.information(self, "Print", "Type pages like 1-3, 5 (this document has "
                                    f"{self.view.page_count()} pages).")
            return
        self._apply_printer()
        self.printer.setCopyCount(self.copies.value())
        if self.print_to(self.printer, pages):
            self.accept()

    def print_to(self, printer, pages):
        """Print pages on printer as previewed. True when done."""
        v = self.view
        dpi = min(printer.resolution(), 600 if v.allowed(pymupdf.PDF_PERM_PRINT_HQ) else 150)
        painter = QPainter()
        try:
            return self._print_pages(printer, painter, pages, dpi)
        finally:
            if painter.isActive():
                painter.end()

    def _print_pages(self, printer, painter, pages, dpi):
        first = True
        for i in pages:
            paper, box = self.sheet(i)
            orient = QPageLayout.Landscape if paper.width() > paper.height() else QPageLayout.Portrait
            printer.setPageOrientation(orient)              # each sheet turned as previewed
            if first:
                if not painter.begin(printer):
                    QMessageBox.critical(self, "Print", "Could not start printing.")
                    return False
                first = False
            else:
                printer.newPage()
            res = printer.resolution() / 72.0
            target = QRectF(box.x() * res, box.y() * res, box.width() * res, box.height() * res)
            self._draw_bands(painter, i, target, dpi)
            self._draw_links(painter, i, target)
        return True

    def _draw_links(self, painter, i, target):
        """Visible link borders, as on screen (MuPDF's rendering leaves them out). They
        print with the markups."""
        if not self.markups.isChecked():
            return
        from PySide6.QtGui import QPen
        page_rect = self.view.doc[i].rect
        k = target.width() / max(1e-6, page_rect.width)
        for r, ln in self.view.links(i):
            b = ln.get("kz_border")
            if not b:
                continue
            width, rgb, style = b
            painter.setPen(QPen(QColor.fromRgbF(*rgb), max(0.5, width * k),
                                Qt.DashLine if style == "D" else Qt.SolidLine))
            painter.setBrush(Qt.NoBrush)
            box = QRectF(target.x() + r.x0 * k, target.y() + r.y0 * k, r.width * k,
                         r.height * k)
            if style == "U":
                painter.drawLine(box.bottomLeft(), box.bottomRight())
            else:
                painter.drawRect(box)

    def _draw_bands(self, painter, i, target, dpi):
        """Draw page i into target in horizontal bands of at most BAND_BYTES each, so a big
        sheet at 600 dpi never needs one huge image in memory."""
        page = self.view.doc[i]
        r = page.rect
        k = dpi / 72.0
        rows = max(1, int(BAND_BYTES / max(1.0, r.width * k * 3)))   # pixel rows per band
        step = rows / k                                                # in page points
        sy = target.height() / r.height
        y = r.y0
        while y < r.y1:
            y1 = min(r.y1, y + step)
            clip = pymupdf.Rect(r.x0, y, r.x1, y1)
            pm = page.get_pixmap(matrix=pymupdf.Matrix(k, k), clip=clip,
                                 annots=self.markups.isChecked())
            img = QImage(pm.samples, pm.width, pm.height, pm.stride, QImage.Format_RGB888)
            painter.drawImage(QRectF(target.x(), target.y() + (y - r.y0) * sy,
                                     target.width(), (y1 - y) * sy), img)
            del img, pm
            y = y1
