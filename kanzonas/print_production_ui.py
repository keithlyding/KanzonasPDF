"""The windows of print production (print_production.py): Set page boxes, Fix hairlines and
Check for printing."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel,
                               QLineEdit, QMessageBox, QProgressDialog, QRadioButton,
                               QVBoxLayout, QWidget, QComboBox, QDoubleSpinBox, QGridLayout,
                               QTreeWidget, QTreeWidgetItem, QPushButton, QApplication,
                               QButtonGroup)

from . import print_production as pp
from .i18n import tr
from .print_dialog import parse_pages

UNITS = [("pt", 1.0), ("in", 72.0), ("mm", 72.0 / 25.4)]


class PagesChoice(QWidget):
    """All pages / Current page / Pages: [1-3, 5]."""
    def __init__(self, view, parent=None):
        super().__init__(parent)
        self.view = view
        n = view.page_count()
        self.all_pages = QRadioButton(tr("All ({n} pages)").format(n=n) if n != 1 else
                                      tr("All (1 page)"))
        self.current = QRadioButton(tr("Current page ({n})").format(n=view.current_page() + 1))
        self.some = QRadioButton(tr("Pages"))
        self.text = QLineEdit()
        self.text.setPlaceholderText(tr("e.g. 1-3, 5"))
        self.text.textChanged.connect(lambda _t: self.some.setChecked(True))
        self.all_pages.setChecked(True)
        group = QButtonGroup(self)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        for b in (self.all_pages, self.current):
            group.addButton(b)
            lay.addWidget(b)
        group.addButton(self.some)
        row = QHBoxLayout()
        row.addWidget(self.some)
        row.addWidget(self.text, 1)
        lay.addLayout(row)

    def pages(self):
        """The pages chosen (0-based), or None when the page numbers aren't valid."""
        v = self.view
        if self.current.isChecked():
            return [v.current_page()]
        if self.some.isChecked():
            try:
                return parse_pages(self.text.text(), v.page_count())
            except ValueError:
                return None
        return list(range(v.page_count()))


def _bad_pages(parent, view):
    QMessageBox.information(parent, tr("Pages"), tr("Type pages like 1-3, 5 (this document "
                                                    "has {n} pages).").format(
                                n=view.page_count()))


def _spin(maximum=10000.0):
    s = QDoubleSpinBox()
    s.setRange(-maximum, maximum)
    s.setDecimals(3)
    s.setSingleStep(1.0)
    return s


# ---- Set page boxes -----------------------------------------------------------------------
class PageBoxesDialog(QDialog):
    """Trim, bleed and art boxes: for each, leave it, set it (margins in from the crop box,
    as the page is shown) or remove it, on the pages chosen."""
    def __init__(self, parent, view):
        super().__init__(parent)
        self.view = view
        self.setWindowTitle(tr("Set page boxes"))
        page = view.doc[view.current_page()]
        crop = page.rect                                    # as shown
        self.unit = QComboBox()
        for name, _k in UNITS:
            self.unit.addItem(name)
        self.unit.setCurrentIndex(1)                        # inches
        self._k = UNITS[1][1]
        self.unit.currentIndexChanged.connect(self._unit_changed)
        grid = QGridLayout()
        heads = [tr("Box"), "", tr("Left"), tr("Top"), tr("Right"), tr("Bottom")]
        for c, h in enumerate(heads):
            grid.addWidget(QLabel("<b>%s</b>" % h if h else ""), 0, c)
        self.rows = {}
        names = {"trimbox": tr("Trim box (finished size)"),
                 "bleedbox": tr("Bleed box (drawing past the trim)"),
                 "artbox": tr("Art box (the meaningful content)")}
        rot = page.rotation_matrix
        for r, which in enumerate(pp.BOXES, start=1):
            what = QComboBox()
            what.addItems([tr("Leave as is"), tr("Set"), tr("Remove")])
            spins = [_spin() for _ in range(4)]
            have = pp.page_box(page, which)
            if have is not None:
                shown = have * rot
                vals = (shown.x0 - crop.x0, shown.y0 - crop.y0, crop.x1 - shown.x1,
                        crop.y1 - shown.y1)
            else:
                vals = (0, 0, 0, 0)
            for s, val in zip(spins, vals):
                s.setValue(val / self._k)
                s.valueChanged.connect(lambda _v, w=what: w.setCurrentIndex(1))
            grid.addWidget(QLabel(names[which]), r, 0)
            grid.addWidget(what, r, 1)
            for c, s in enumerate(spins, start=2):
                grid.addWidget(s, r, c)
            self.rows[which] = (what, spins)
        note = QLabel(tr("Margins are measured in from the page as shown (its crop box); "
                         "positive margins go inward. A box has to stay within the page's "
                         "whole sheet (media box). Current page: {w} × {h}.").format(
            w=self._size(crop.width), h=self._size(crop.height)))
        note.setWordWrap(True)
        self._note = note
        self._crop = crop
        self.pages = PagesChoice(view)
        form = QFormLayout()
        form.addRow(tr("Units"), self.unit)
        form.addRow(tr("Pages"), self.pages)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._ok)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addLayout(grid)
        lay.addWidget(note)
        lay.addLayout(form)
        lay.addWidget(buttons)

    def _size(self, pts):
        name, k = UNITS[self.unit.currentIndex()]
        return "%g %s" % (round(pts / k, 3), name)

    def _unit_changed(self, i):
        k = UNITS[i][1]
        for what, spins in self.rows.values():
            keep = what.currentIndex()
            for s in spins:
                s.blockSignals(True)
                s.setValue(s.value() * self._k / k)
                s.blockSignals(False)
            what.setCurrentIndex(keep)
        self._k = k
        self._note.setText(tr("Margins are measured in from the page as shown (its crop box); "
                              "positive margins go inward. A box has to stay within the page's "
                              "whole sheet (media box). Current page: {w} × {h}.").format(
            w=self._size(self._crop.width), h=self._size(self._crop.height)))

    def choices(self):
        """{box: margins in points (left, top, right, bottom), or None to remove it}."""
        out = {}
        for which, (what, spins) in self.rows.items():
            if what.currentIndex() == 1:
                out[which] = tuple(s.value() * self._k for s in spins)
            elif what.currentIndex() == 2:
                out[which] = None
        return out

    def _ok(self):
        pages = self.pages.pages()
        if not pages:
            _bad_pages(self, self.view)
            return
        choices = self.choices()
        if not choices:
            self.reject()
            return
        try:
            self.view.set_page_boxes(pages, choices)
        except ValueError as ex:
            QMessageBox.warning(self, tr("Set page boxes"), str(ex))
            return
        self.accept()


# ---- Fix hairlines ------------------------------------------------------------------------
class HairlinesDialog(QDialog):
    def __init__(self, parent, view):
        super().__init__(parent)
        self.view = view
        self.setWindowTitle(tr("Fix hairlines"))
        self.below = QDoubleSpinBox()
        self.below.setRange(0.01, 10)
        self.below.setDecimals(2)
        self.below.setSingleStep(0.05)
        self.below.setSuffix(" pt")
        self.below.setValue(0.25)
        self.width = QDoubleSpinBox()
        self.width.setRange(0.01, 10)
        self.width.setDecimals(2)
        self.width.setSingleStep(0.05)
        self.width.setSuffix(" pt")
        self.width.setValue(0.25)
        self.below.valueChanged.connect(lambda v: self.width.setValue(max(self.width.value(), v)))
        self.pages = PagesChoice(view)
        note = QLabel(tr("Lines drawn thinner than this (a width of 0 included: a plotter's "
                         "thinnest line, often too faint to see) are drawn at the new width, "
                         "in the page's own drawing and in the drawing groups it places. "
                         "Markups keep their own widths. Ctrl+Z undoes it. (0.25 pt is about "
                         "0.09 mm.)"))
        note.setWordWrap(True)
        form = QFormLayout()
        form.addRow(tr("Lines thinner than"), self.below)
        form.addRow(tr("Draw them at"), self.width)
        form.addRow(tr("Pages"), self.pages)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._ok)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(note)
        lay.addLayout(form)
        lay.addWidget(buttons)

    def _ok(self):
        pages = self.pages.pages()
        if not pages:
            _bad_pages(self, self.view)
            return
        below, width = self.below.value(), max(self.width.value(), self.below.value())
        n = self.view.fix_hairlines(pages, below, width)
        if n is None:
            return                              # (not allowed: the view said why)
        if n == 0:
            QMessageBox.information(self, tr("Fix hairlines"), tr(
                "No lines thinner than {w} pt on these pages.").format(w="%g" % below))
            return
        self.view.statusMessage.emit(tr("Fix hairlines: {n} lines now {w} pt wide (Ctrl+Z "
                                        "undoes it)").format(n=n, w="%g" % width))
        self.accept()


# ---- Check for printing -------------------------------------------------------------------
class CheckDialog(QDialog):
    """The report: what may go wrong at the printer, by kind, each line with its page (a
    double-click goes there)."""
    def __init__(self, parent, view, found, pages):
        super().__init__(parent)
        self.view = view
        self.setWindowTitle(tr("Check for printing"))
        self.resize(720, 460)
        labels = pp.kind_labels()
        tree = QTreeWidget()
        tree.setHeaderLabels([tr("What"), tr("Page")])
        tree.setColumnWidth(0, 560)
        by_kind = {}
        for kind, i, text in found:
            by_kind.setdefault(kind, []).append((i, text))
        for kind in ("fonts", "pictures", "rgb", "hairlines", "boxes", "sizes"):
            items = by_kind.get(kind)
            if not items:
                continue
            top = QTreeWidgetItem([tr("{what} ({n})").format(what=labels[kind], n=len(items)),
                                   ""])
            tree.addTopLevelItem(top)
            for i, text in items:
                it = QTreeWidgetItem([text, "" if i is None else str(i + 1)])
                it.setData(0, Qt.UserRole, i)
                top.addChild(it)
            top.setExpanded(len(items) <= 20)
        tree.itemDoubleClicked.connect(self._go)
        n = len(pages)
        if found:
            head = (tr("{n} things to look at on {pages} pages checked.") if n != 1 else
                    tr("{n} things to look at on the page checked.")).format(
                n=len(found), pages=n) + " " + tr("Double-click a line to go to its page.")
        else:
            head = (tr("Nothing found on the {pages} pages checked:") if n != 1 else
                    tr("Nothing found on the page checked:")).format(pages=n) + " " + \
                tr("fonts embedded, pictures sharp enough, trim and bleed set, no hairlines.")
        info = QLabel(head + " " + tr("(This is a quick check of common problems, not a "
                                      "preflight against a printing standard such as PDF/X.)"))
        info.setWordWrap(True)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        if by_kind.get("hairlines"):
            fix = QPushButton(tr("Fix hairlines..."))
            fix.clicked.connect(self._fix)
            buttons.addButton(fix, QDialogButtonBox.ActionRole)
        lay = QVBoxLayout(self)
        lay.addWidget(info)
        lay.addWidget(tree, 1)
        lay.addWidget(buttons)
        self.tree = tree

    def _go(self, item, _col):
        i = item.data(0, Qt.UserRole)
        if isinstance(i, int):
            self.view.goto_page(i)

    def _fix(self):
        self.accept()
        HairlinesDialog(self.parent(), self.view).exec()


def check_pages(parent, view, pages, hairline=0.25):
    """Run the check over pages with a progress window; the findings, or None if stopped."""
    progress = QProgressDialog(tr("Checking for printing..."), tr("Cancel"), 0, len(pages),
                               parent)
    progress.setWindowTitle(tr("Check for printing"))
    progress.setWindowModality(Qt.WindowModal)
    progress.setMinimumDuration(400)
    seen = {"n": 0}

    def step(_i):
        progress.setValue(seen["n"])
        seen["n"] += 1
        QApplication.processEvents()
        return not progress.wasCanceled()
    try:
        found = pp.check(view.doc, pages, hairline=hairline, step=step)
        if progress.wasCanceled():
            return None
        return found
    finally:
        progress.close()
        progress.deleteLater()


class CheckChoiceDialog(QDialog):
    def __init__(self, parent, view):
        super().__init__(parent)
        self.setWindowTitle(tr("Check for printing"))
        self.pages = PagesChoice(view)
        self.view = view
        form = QFormLayout()
        form.addRow(tr("Pages"), self.pages)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText(tr("Check"))
        buttons.accepted.connect(self._ok)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(tr("Looks for fonts that aren't embedded, pictures of too low "
                                "resolution at their printed size, RGB pictures, mixed sheet "
                                "sizes, missing trim and bleed boxes, and hairlines.")))
        lay.addLayout(form)
        lay.addWidget(buttons)
        self.chosen = None

    def _ok(self):
        pages = self.pages.pages()
        if not pages:
            _bad_pages(self, self.view)
            return
        self.chosen = pages
        self.accept()


def check_for_printing(parent, view):
    ask = CheckChoiceDialog(parent, view)
    if not ask.exec() or not ask.chosen:
        return
    found = check_pages(parent, view, ask.chosen)
    if found is None:
        return
    CheckDialog(parent, view, found, ask.chosen).exec()
