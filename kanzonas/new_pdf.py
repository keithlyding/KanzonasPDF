"""File > New PDF: a blank, unsaved document; the page size is asked for (or remembered:
Preferences > Pages and display > New PDF page size)."""

import pymupdf
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QFormLayout, QComboBox, QCheckBox,
                               QDialogButtonBox, QLabel)

from .i18n import tr

# name -> (width, height) in inches, portrait
SIZES = {
    "Letter": (8.5, 11), "Legal": (8.5, 14), "Tabloid": (11, 17),
    "ANSI C": (17, 22), "ANSI D": (22, 34), "ANSI E": (34, 44),
    "ARCH A": (9, 12), "ARCH B": (12, 18), "ARCH C": (18, 24), "ARCH D": (24, 36),
    "ARCH E": (36, 48),
    "A4": (8.27, 11.69), "A3": (11.69, 16.54), "A2": (16.54, 23.39), "A1": (23.39, 33.11),
    "A0": (33.11, 46.81),
}
ASK = "ask"                     # the Preferences choice "Ask every time"


def label(name):
    w, h = SIZES[name]
    if name.startswith("A") and name[1:].isdigit():
        mm = pymupdf.paper_size(name.lower())
        return f"{name} ({round(mm[0] / 72 * 25.4)} x {round(mm[1] / 72 * 25.4)} mm)"
    return f"{_PAPER_NAMES.get(name, name)} ({w:g} x {h:g} in)"


# the US paper names as shown (the SIZES keys are kept in the settings)
_PAPER_NAMES = {"Letter": tr("Letter"), "Legal": tr("Legal"), "Tabloid": tr("Tabloid")}


def page_size(name, landscape=False):
    """(width, height) in points."""
    if name.startswith("A") and name[1:].isdigit():
        w, h = pymupdf.paper_size(name.lower())
    else:
        w, h = (v * 72 for v in SIZES.get(name, SIZES["Letter"]))
    return (h, w) if landscape else (w, h)


def remembered(settings):
    """(size name, landscape) from the settings."""
    from . import paths
    return (paths.stored_str(settings, "new_pdf_size", "Letter", SIZES),
            settings.value("new_pdf_landscape", "false") == "true")


def size_combo(with_ask=False):
    box = QComboBox()
    if with_ask:
        box.addItem(tr("Ask every time"), ASK)
    for name in SIZES:
        box.addItem(label(name), name)
    return box


def orientation_combo():
    box = QComboBox()
    box.addItem(tr("Portrait"), False)
    box.addItem(tr("Landscape"), True)
    return box


class PageSizeDialog(QDialog):
    def __init__(self, parent, settings):
        super().__init__(parent)
        self.setWindowTitle(tr("New PDF"))
        lay = QVBoxLayout(self)
        form = QFormLayout()
        name, landscape = remembered(settings)
        self.size = size_combo()
        self.size.setCurrentIndex(max(0, self.size.findData(name)))
        form.addRow(tr("Page size:"), self.size)
        self.orient = orientation_combo()
        self.orient.setCurrentIndex(1 if landscape else 0)
        form.addRow(tr("Orientation:"), self.orient)
        lay.addLayout(form)
        self.dont_ask = QCheckBox(tr("Don't ask again"))
        lay.addWidget(self.dont_ask)
        hint = QLabel(tr("You can change the size later in File > Preferences > Pages and "
                         "display."))
        hint.setWordWrap(True)
        lay.addWidget(hint)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.button(QDialogButtonBox.Ok).setText(tr("Create"))
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def choice(self):
        return self.size.currentData(), bool(self.orient.currentData())


def ask(parent, settings):
    """The page size for a new PDF as (width, height) in points, or None if canceled. Asks
    unless the user chose "Don't ask again"; remembers the answer either way."""
    if settings.value("new_pdf_ask", "true") == "false":
        return page_size(*remembered(settings))
    dlg = PageSizeDialog(parent, settings)
    if not dlg.exec():
        return None
    name, landscape = dlg.choice()
    settings.setValue("new_pdf_size", name)
    settings.setValue("new_pdf_landscape", "true" if landscape else "false")
    if dlg.dont_ask.isChecked():
        settings.setValue("new_pdf_ask", "false")
    return page_size(name, landscape)


def blank_doc(size):
    doc = pymupdf.open()
    doc.new_page(width=size[0], height=size[1])
    return doc
