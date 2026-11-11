"""Pages > Add space around page: the page made bigger on the sides chosen, as it's shown,
with its drawing, markups, links and form fields staying where they are on it (issue #82: room
beside a sheet for comments, or to paste other sheets into for one combined plan).

The page's boxes grow outward in PDF space (the media box, and the crop box with it, by the
same amounts on the same sides), so nothing written in the page moves: the new space is real
page, shown, printed and kept by every PDF program. The positions KanzonasPDF keeps in page
coordinates follow (annotations.rebase_page). Crop pages takes the space off again.

(Bluebeam's way, Page Setup with a custom size and Fit Media, scales or re-places the drawing,
and markups then don't always follow it: Bluebeam Community, "increase page extents and
maintain existing markups positions".)"""

import pymupdf
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFormLayout, QGridLayout, QLabel,
                               QMessageBox, QVBoxLayout, QComboBox, QDoubleSpinBox)

from . import annotations, pdfcoords
from .i18n import tr

LARGEST = 14400.0           # PDF's largest page side: 200 inches (ISO 32000, Annex C)


def _media_pdf(page):
    """The page's media box in PDF user space (inherited from the page tree if need be)."""
    mu = pymupdf.mupdf
    obj = mu.pdf_page_from_fz_page(page.this).obj()
    r = mu.pdf_to_rect(mu.pdf_dict_get_inheritable(obj, mu.PDF_ENUM_NAME_MediaBox))
    return pymupdf.Rect(r.x0, r.y0, r.x1, r.y1).normalize()


def grown(page, margins):
    """(media box, crop box) in PDF user space with margins (left, top, right, bottom, in
    points, as the page is shown) added outside the crop box, and the media box grown by
    the same amounts on the same sides."""
    left, top, right, bottom = margins
    shown = page.rect                                       # the page as shown: 0, 0, w, h
    bigger = pymupdf.Rect(shown.x0 - left, shown.y0 - top, shown.x1 + right, shown.y1 + bottom)
    to_pdf = page.derotation_matrix * pdfcoords.to_pdf(page)
    crop = (shown * to_pdf).normalize()
    new_crop = (bigger * to_pdf).normalize()
    media = _media_pdf(page)
    new_media = pymupdf.Rect(media.x0 - (crop.x0 - new_crop.x0),
                             media.y0 - (crop.y0 - new_crop.y0),
                             media.x1 + (new_crop.x1 - crop.x1),
                             media.y1 + (new_crop.y1 - crop.y1))
    return new_media, new_crop


def check(page, margins):
    """A sentence saying why these margins can't be added to page, or None."""
    if any(m < 0 for m in margins):
        return tr("Space can only be added; to take some away, use Crop pages.")
    media, _crop = grown(page, margins)
    if media.width > LARGEST or media.height > LARGEST:
        return tr("A PDF page can be at most 200 inches (5.08 m) on a side.")
    return None


def add_space(page, margins):
    """Grow page by margins (see grown). Returns the page as loaded again."""
    doc = page.parent
    number = page.number
    before = annotations.page_origin(page)
    media, crop = grown(page, margins)
    arr = "[%s]" % " ".join(("%.4f" % c).rstrip("0").rstrip(".") for c in media)
    doc.xref_set_key(page.xref, "MediaBox", arr)
    arr = "[%s]" % " ".join(("%.4f" % c).rstrip("0").rstrip(".") for c in crop)
    doc.xref_set_key(page.xref, "CropBox", arr)
    page = doc[number]
    annotations.sync_page(page)
    annotations.rebase_page(page, annotations.page_origin(page) - before)
    return page


# ---- the window ------------------------------------------------------------------------------
class AddSpaceDialog(QDialog):
    """How much space on each side (as the page is shown), in which unit, on which pages."""

    def __init__(self, parent, view):
        from .print_production_ui import PagesChoice, UNITS
        super().__init__(parent)
        self.view = view
        self.units = UNITS
        self.setWindowTitle(tr("Add space around page"))
        self.unit = QComboBox()
        for name, _k in UNITS:
            self.unit.addItem(name)
        self.unit.setCurrentIndex(1)                        # inches
        self._k = UNITS[1][1]
        self.unit.currentIndexChanged.connect(self._unit_changed)
        grid = QGridLayout()
        self.spins = []
        for c, label in enumerate((tr("Left"), tr("Top", ctx="edge"), tr("Right"),
                                   tr("Bottom", ctx="edge"))):
            s = QDoubleSpinBox()
            s.setRange(0, LARGEST)
            s.setDecimals(3)
            s.setSingleStep(1.0)
            grid.addWidget(QLabel("<b>%s</b>" % label), 0, c)
            grid.addWidget(s, 1, c)
            self.spins.append(s)
        self.spins[2].setValue(10.0)                        # 10 inches on the right
        note = QLabel(tr("The page gets bigger on these sides, as it's shown; the drawing, "
                         "markups, links and form fields stay where they are on it. What you "
                         "put in the new space prints and shows in every PDF program. Crop "
                         "pages takes the space off again."))
        note.setWordWrap(True)
        self.pages = PagesChoice(view)
        self.pages.current.setChecked(True)
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

    def _unit_changed(self, i):
        k = self.units[i][1]
        for s in self.spins:
            s.setValue(s.value() * self._k / k)
        self._k = k

    def margins(self):
        """(left, top, right, bottom) in points."""
        return tuple(s.value() * self._k for s in self.spins)

    def _ok(self):
        from .print_production_ui import _bad_pages
        pages = self.pages.pages()
        if not pages:
            _bad_pages(self, self.view)
            return
        margins = self.margins()
        if not any(margins):
            self.reject()
            return
        try:
            self.view.add_page_space(pages, margins)
        except ValueError as ex:
            QMessageBox.warning(self, tr("Add space around page"), str(ex))
            return
        self.accept()
