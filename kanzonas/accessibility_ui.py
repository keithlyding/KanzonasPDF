"""The windows of accessibility (accessibility.py, autotag.py): Document > Accessibility >
Check accessibility, Auto-tag, Alt text, Title and language, Form field tooltips, Link
descriptions, Tab order, Mark as decorative, Identify as PDF/UA. Every change is one undo
step (DocumentView.modify)."""

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon, QImage, QPixmap
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                               QFormLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                               QListWidget, QListWidgetItem, QMessageBox, QPlainTextEdit,
                               QProgressDialog, QPushButton, QTableWidget, QTableWidgetItem,
                               QTreeWidget, QTreeWidgetItem, QVBoxLayout)

from . import accessibility as acc
from .i18n import tr

PAC = "https://pac.pdf-accessibility.org"
VERAPDF = "https://verapdf.org"


def about_the_check():
    return tr("It checks what a program can check of PDF/UA (ISO 14289-1), the standard for "
              "accessible PDF that WCAG 2.1 and accessibility laws point to, following the "
              "Matterhorn Protocol of the PDF Association. Some things only a person can "
              "judge (listed at the end). For a formal validation, use PAC 2024 (free, for "
              "Windows: {pac}) or veraPDF's PDF/UA profile ({vera}).").format(
        pac=PAC, vera=VERAPDF)


def _progress(parent, text, title, total=0):
    progress = QProgressDialog(text, tr("Cancel"), 0, total, parent)
    progress.setWindowTitle(title)
    progress.setWindowModality(Qt.WindowModal)
    progress.setMinimumDuration(400)
    return progress


# ---- Check accessibility -----------------------------------------------------------------
class ReportDialog(QDialog):
    """What keeps the document from being accessible, by kind, each line with its page (a
    double-click goes there), the rule it breaks, and the fix here that deals with it (Fix
    runs it, then the check again)."""

    def __init__(self, parent, window, view, problems):
        super().__init__(parent)
        self.window, self.view = window, view
        self.setWindowTitle(tr("Check accessibility"))
        self.resize(980, 560)
        self.info = QLabel()
        self.info.setWordWrap(True)
        self.info.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.LinksAccessibleByMouse)
        self.info.setOpenExternalLinks(True)
        tree = self.tree = QTreeWidget()
        tree.setHeaderLabels([tr("What"), tr("Page"), tr("Fix"), tr("Rule")])
        tree.setColumnWidth(0, 560)
        tree.setColumnWidth(1, 50)
        tree.setColumnWidth(2, 150)
        tree.itemDoubleClicked.connect(self._go)
        tree.currentItemChanged.connect(lambda *_: self._enable())
        lay = QVBoxLayout(self)
        lay.addWidget(self.info)
        lay.addWidget(tree, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        self.fix_btn = QPushButton(tr("Fix..."))
        self.fix_btn.setToolTip(tr("Run the fix of the selected line, then check again"))
        self.fix_btn.clicked.connect(self._fix)
        again = QPushButton(tr("Check again"))
        again.clicked.connect(self.recheck)
        buttons.addButton(self.fix_btn, QDialogButtonBox.ActionRole)
        buttons.addButton(again, QDialogButtonBox.ActionRole)
        lay.addWidget(buttons)
        self.show_problems(problems)

    def show_problems(self, problems):
        self.problems = problems
        tree = self.tree
        tree.clear()
        labels, fixes = acc.kind_labels(), acc.fix_labels()
        by_kind = {}
        for p in problems:
            by_kind.setdefault(p.kind, []).append(p)
        for kind in acc.KINDS:
            items = by_kind.get(kind)
            if not items:
                continue
            top = QTreeWidgetItem([tr("{what} ({n})").format(what=labels[kind], n=len(items))
                                   if kind != "manual" else labels[kind], "", "", ""])
            tree.addTopLevelItem(top)
            for p in items:
                it = QTreeWidgetItem([p.text, "" if p.page is None else str(p.page + 1),
                                      fixes.get(p.fix, "") if p.fix else
                                      ("" if kind == "manual" else tr("Can't fix it here")),
                                      p.rule])
                it.setToolTip(0, p.text)
                it.setToolTip(3, p.rule)
                it.setData(0, Qt.UserRole, p)
                top.addChild(it)
            top.setExpanded(len(items) <= 25 or kind == "document")
        found, fixable = acc.summary(problems)
        if found:
            head = tr("{n} problems found; the fixes here deal with {fixable} of them (select "
                      "a line and click Fix). Double-click a line to go to its page.").format(
                n=found, fixable=fixable)
        else:
            head = tr("Nothing found among what a program can check. Check the last group "
                      "yourself.")
        self.info.setText(head + "\n\n" + about_the_check())
        self._enable()

    def _current(self):
        it = self.tree.currentItem()
        return it.data(0, Qt.UserRole) if it is not None else None

    def _enable(self):
        p = self._current()
        self.fix_btn.setEnabled(isinstance(p, acc.Problem) and p.fix is not None)

    def _go(self, item, _col):
        p = item.data(0, Qt.UserRole)
        if isinstance(p, acc.Problem) and p.page is not None and self.view is not None:
            self.view.goto_page(p.page)

    def _fix(self):
        p = self._current()
        if not isinstance(p, acc.Problem) or p.fix is None:
            return
        run_fix(self, self.window, self.view, p.fix)
        self.recheck()

    def recheck(self):
        problems = run_check(self, self.view)
        if problems is not None:
            self.show_problems(problems)


def run_check(parent, view):
    """The check of the open document as it is now, with a progress window; None when
    stopped."""
    view.commit_pending()
    doc = view.doc
    progress = _progress(parent, tr("Checking accessibility..."), tr("Check accessibility"))

    def step():
        QApplication.processEvents()
        return not progress.wasCanceled()
    try:
        return acc.check(doc, step=step)
    finally:
        progress.close()
        progress.deleteLater()


def check_accessibility(window, view):
    """Document > Accessibility > Check accessibility."""
    problems = run_check(window, view)
    if problems is None:
        return
    ReportDialog(window, window, view, problems).exec()


def run_fix(parent, window, view, fix):
    {"autotag": auto_tag, "title": title_language, "lang": title_language,
     "tabs": tab_order, "alt": alt_text, "links": link_descriptions,
     "tooltips": field_tooltips, "fonts": embed_fonts,
     "pdfua": identify_pdfua}[fix](parent, view)


def _done(view, text):
    view.statusMessage.emit(tr("{what} (Ctrl+Z undoes it)").format(what=text))


# ---- Title and language ------------------------------------------------------------------
class LanguageBox(QComboBox):
    """A language tag (en-US, es-ES...): the common ones listed, any other typed."""

    def __init__(self, current=""):
        super().__init__()
        self.setEditable(True)
        for code, name in acc.LANGUAGES:
            self.addItem("%s  (%s)" % (code, name), code)
        cur = current or acc.default_language()
        k = self.findData(cur)
        if k >= 0:
            self.setCurrentIndex(k)
        else:
            self.setEditText(cur)

    def tag(self):
        k = self.currentIndex()
        text = self.currentText().strip()
        if k >= 0 and self.itemText(k) == text:
            return self.itemData(k)
        return text.split()[0] if text else ""


class TitleDialog(QDialog):
    def __init__(self, parent, view):
        super().__init__(parent)
        self.setWindowTitle(tr("Title and language"))
        doc = view.doc
        self.title = QLineEdit(acc.suggested_title(doc))
        self.title.setMinimumWidth(420)
        self.lang = LanguageBox(acc.get_language(doc))
        note = QLabel(tr("The title is what screen readers announce and the window shows "
                         "(not the file name); the language sets the voice and pronunciation "
                         "screen readers use."))
        note.setWordWrap(True)
        form = QFormLayout()
        form.addRow(tr("Title"), self.title)
        form.addRow(tr("Language"), self.lang)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(note)
        lay.addLayout(form)
        lay.addWidget(buttons)


def title_language(parent, view):
    """Document > Accessibility > Title and language: the title (properties, XMP, shown in
    the title bar) and the document's language."""
    dlg = TitleDialog(parent, view)
    if dlg.exec() != QDialog.Accepted:
        return False
    title, lang = dlg.title.text().strip(), dlg.lang.tag()

    def do():
        if title:
            acc.set_title(view.doc, title)
        else:
            acc.set_display_title(view.doc)
        acc.set_language(view.doc, lang)
    if view.modify(do, []):
        _done(view, tr("Title and language set"))
        return True
    return False


def tab_order(parent, view):
    """Document > Accessibility > Tab order: every page's tab order follows the structure
    (/Tabs /S)."""
    n = {"n": 0}

    def do():
        n["n"] = acc.set_tabs(view.doc)
    if view.modify(do, []):
        _done(view, tr("Tab order follows the structure on every page"))


def identify_pdfua(parent, view):
    """Identify as PDF/UA: the PDF/UA-1 identifier in the XMP metadata."""
    problems = run_check(parent, view)
    if problems is None:
        return
    left = [p for p in problems if p.kind != "manual" and p.fix != "pdfua"]
    if left:
        r = QMessageBox.question(parent, tr("Identify as PDF/UA"), tr(
            "The check still finds {n} problems. A file that says it is PDF/UA should meet "
            "the standard: identify it anyway?").format(n=len(left)),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if r != QMessageBox.Yes:
            return
    if view.modify(lambda: acc.set_pdfua(view.doc), []):
        _done(view, tr("Identified as PDF/UA-1"))


def embed_fonts(parent, view):
    """Embed the standard fonts that aren't embedded (as Save as PDF/A does)."""
    n = {"n": 0}

    def do():
        n["n"] = acc.embed_fonts(view.doc)
    if view.modify(do):
        _done(view, tr("Embedded {n} fonts").format(n=n["n"]) if n["n"] != 1 else
              tr("Embedded 1 font"))


# ---- review lists: form field tooltips, link descriptions -----------------------------
class ReviewDialog(QDialog):
    """A list to review and edit: page, what, the text to write (prefilled)."""

    def __init__(self, parent, view, title, note, what, rows):
        super().__init__(parent)
        self.view = view
        self.setWindowTitle(title)
        self.resize(860, 520)
        self.rows = rows
        label = QLabel(note)
        label.setWordWrap(True)
        t = self.table = QTableWidget(len(rows), 3)
        t.setHorizontalHeaderLabels([tr("Page"), what, tr("Text")])
        t.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        t.setColumnWidth(0, 50)
        t.setColumnWidth(1, 280)
        for i, (page, shown, text, _key) in enumerate(rows):
            a = QTableWidgetItem(str(page + 1))
            a.setFlags(a.flags() & ~Qt.ItemIsEditable)
            b = QTableWidgetItem(shown)
            b.setFlags(b.flags() & ~Qt.ItemIsEditable)
            b.setToolTip(shown)
            t.setItem(i, 0, a)
            t.setItem(i, 1, b)
            t.setItem(i, 2, QTableWidgetItem(text))
        t.cellDoubleClicked.connect(self._go)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(label)
        lay.addWidget(t, 1)
        lay.addWidget(buttons)

    def _go(self, row, col):
        if col < 2:
            self.view.goto_page(self.rows[row][0])

    def texts(self):
        return {self.rows[i][3]: self.table.item(i, 2).text().strip()
                for i in range(len(self.rows))}


def field_tooltips(parent, view):
    """Document > Accessibility > Form field tooltips: each field's tooltip (/TU), the name
    screen readers say, offered from the words next to it."""
    found = acc.fields(view.doc)
    if not found:
        QMessageBox.information(parent, tr("Form field tooltips"),
                                tr("This document has no form fields."))
        return
    rows, seen = [], set()
    for f in found:
        if f["field"] in seen:
            continue                    # (a field shown in several places: once)
        seen.add(f["field"])
        rows.append((f["page"], f["name"], f["tooltip"] or f["label"], f["field"]))
    dlg = ReviewDialog(parent, view, tr("Form field tooltips"), tr(
        "The tooltip is what screen readers say for a field (and what a tip shows over it). "
        "Each is offered from the words next to the field: check and correct them. "
        "Double-click a line to go to its page."), tr("Field"), rows)
    if dlg.exec() != QDialog.Accepted:
        return
    tips = dlg.texts()
    pages = sorted({r[0] for r in rows})
    if view.modify(lambda: acc.set_tooltips(view.doc, tips), pages):
        _done(view, tr("Tooltips set for {n} fields").format(n=len(tips)))


def link_descriptions(parent, view):
    """Document > Accessibility > Link descriptions: each link's description (/Contents),
    offered from the words it covers, else where it goes."""
    found = acc.links(view.doc)
    if not found:
        QMessageBox.information(parent, tr("Link descriptions"),
                                tr("This document has no links."))
        return
    rows = [(f["page"], f["uri"] or f["suggestion"], f["contents"] or f["suggestion"],
             f["xref"]) for f in found]
    dlg = ReviewDialog(parent, view, tr("Link descriptions"), tr(
        "The description is what screen readers say for a link. Each is offered from the "
        "words the link covers, or where it goes: check and correct them. Double-click a "
        "line to go to its page."), tr("Link"), rows)
    if dlg.exec() != QDialog.Accepted:
        return
    texts = dlg.texts()
    pages = sorted({r[0] for r in rows})
    if view.modify(lambda: acc.set_contents(view.doc, texts), pages):
        _done(view, tr("Descriptions set for {n} links").format(n=len(texts)))


# ---- Alt text ---------------------------------------------------------------------------
THUMB = 96


def _thumb(doc, page, box, size=THUMB):
    """A picture of box on page (as shown), size pixels at most."""
    import pymupdf
    pg = doc[page]
    if box is None or box.is_empty:
        box = pg.rect
    clip = pymupdf.Rect(box) * pg.derotation_matrix
    clip.normalize()
    clip &= pg.mediabox if pg.rotation == 0 else clip
    zoom = min(4.0, size / max(box.width, box.height, 1))
    pix = pg.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), clip=clip, alpha=False,
                        annots=False)
    img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888).copy()
    return QPixmap.fromImage(img)


class AltTextDialog(QDialog):
    """The document's figures, each with its picture, a description to type, or Decorative
    (then it's an artifact: screen readers skip it)."""

    def __init__(self, parent, view, figs):
        super().__init__(parent)
        self.view = view
        self.figs = figs
        self.setWindowTitle(tr("Alt text"))
        self.resize(900, 560)
        self.alts = [f["alt"] for f in figs]
        self.decor = [False] * len(figs)
        lst = self.list = QListWidget()
        lst.setIconSize(QPixmap(THUMB, THUMB).size())
        lst.setMinimumWidth(320)
        for i, f in enumerate(figs):
            it = QListWidgetItem(self._label(i))
            it.setData(Qt.UserRole, i)
            lst.addItem(it)
        lst.currentRowChanged.connect(self._show)
        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumSize(360, 240)
        self.text = QPlainTextEdit()
        self.text.setPlaceholderText(tr("What the picture shows, or what it's for, in a "
                                        "sentence or two"))
        self.text.textChanged.connect(self._typed)
        self.decorative = QCheckBox(tr("Decorative (an artifact: screen readers skip it)"))
        self.decorative.toggled.connect(self._toggled)
        note = QLabel(tr("Describe each figure for people who can't see it: what it shows, "
                         "or what it's there for. A picture that only decorates is marked "
                         "Decorative instead. Double-click a figure to go to its page."))
        note.setWordWrap(True)
        right = QVBoxLayout()
        right.addWidget(self.preview, 1)
        right.addWidget(QLabel(tr("Alternate text")))
        right.addWidget(self.text)
        right.addWidget(self.decorative)
        row = QHBoxLayout()
        row.addWidget(lst)
        row.addLayout(right, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(note)
        lay.addLayout(row, 1)
        lay.addWidget(buttons)
        lst.itemDoubleClicked.connect(self._go)
        self._cur = -1
        self._todo = list(range(len(figs)))
        self._timer = QTimer(self)
        self._timer.setInterval(0)
        self._timer.timeout.connect(self._thumbs)
        self._timer.start()
        if figs:
            lst.setCurrentRow(0)

    def _label(self, i):
        f = self.figs[i]
        what = tr("Decorative") if self.decor[i] else (self.alts[i] or tr("(no description)"))
        return tr("Page {n}: {what}").format(n=(f["page"] or 0) + 1, what=what[:80])

    def _thumbs(self):
        """A few thumbnails per pass of the event loop (a document with hundreds of pictures
        opens the window at once)."""
        for _ in range(4):
            if not self._todo:
                self._timer.stop()
                return
            i = self._todo.pop(0)
            f = self.figs[i]
            if f["page"] is None:
                continue
            try:
                pm = _thumb(self.view.doc, f["page"], f["box"])
            except Exception:
                continue
            self.list.item(i).setIcon(QIcon(pm))

    def _show(self, i):
        self._cur = -1
        if i < 0:
            return
        f = self.figs[i]
        if f["page"] is not None:
            try:
                self.preview.setPixmap(_thumb(self.view.doc, f["page"], f["box"], 340))
            except Exception:
                self.preview.clear()
        self.text.setPlainText(self.alts[i])
        self.decorative.setChecked(self.decor[i])
        self.text.setEnabled(not self.decor[i])
        self._cur = i

    def _typed(self):
        if self._cur >= 0:
            self.alts[self._cur] = self.text.toPlainText()
            self.list.item(self._cur).setText(self._label(self._cur))

    def _toggled(self, on):
        if self._cur >= 0:
            self.decor[self._cur] = on
            self.text.setEnabled(not on)
            self.list.item(self._cur).setText(self._label(self._cur))

    def _go(self, item):
        f = self.figs[item.data(Qt.UserRole)]
        if f["page"] is not None:
            self.view.goto_page(f["page"])

    def changes(self):
        """([(element, alt)], [element to make decorative])."""
        alts, decor = [], []
        for f, a, d in zip(self.figs, self.alts, self.decor):
            if d:
                decor.append(f["num"])
            elif a.strip() != (f["alt"] or "").strip():
                alts.append((f["num"], a.strip()))
        return alts, decor


def alt_text(parent, view):
    """Document > Accessibility > Alt text: a description for each figure, or Decorative."""
    doc = view.doc
    if not acc.Tree(doc).root:
        r = QMessageBox.question(parent, tr("Alt text"), tr(
            "Alternate text is kept in the document's tags, and this document isn't tagged. "
            "Auto-tag it first?"), QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
        if r != QMessageBox.Yes or not auto_tag(parent, view):
            return
    figs = acc.figures(doc)
    if not figs:
        QMessageBox.information(parent, tr("Alt text"),
                                tr("The document's tags have no figures."))
        return
    dlg = AltTextDialog(parent, view, figs)
    if dlg.exec() != QDialog.Accepted:
        return
    alts, decor = dlg.changes()
    if not alts and not decor:
        return
    pages = sorted({f["page"] for f in figs if f["num"] in set(decor) and f["page"] is not None})

    def do():
        for num, text in alts:
            acc.set_alt(view.doc, num, text)
        for num in decor:
            acc.make_decorative(view.doc, num)
    if view.modify(do, pages):
        _done(view, tr("Alt text: {n} described, {d} decorative").format(n=len(alts),
                                                                        d=len(decor)))


# ---- Auto-tag ----------------------------------------------------------------------------
class AutoTagDialog(QDialog):
    def __init__(self, parent, view):
        super().__init__(parent)
        self.setWindowTitle(tr("Auto-tag"))
        doc = view.doc
        self.title = QLineEdit(acc.suggested_title(doc))
        self.title.setMinimumWidth(420)
        self.lang = LanguageBox(acc.get_language(doc))
        note = QLabel(tr(
            "Auto-tag gives this untagged document the tags screen readers follow: headings "
            "(by size and weight), paragraphs, bulleted and numbered lists, tables drawn with "
            "lines, figures (pictures: describe them afterwards with Alt text), links, form "
            "fields and comments, in reading order (top to bottom, columns left to right). "
            "Headers, footers, page numbers and drawn lines become artifacts (decoration). "
            "What it can't recognize for sure is tagged as a paragraph. It suits simple "
            "layouts: check the result with Check accessibility and, for a formal "
            "validation, PAC 2024 or veraPDF. The pages look the same; Ctrl+Z undoes it."))
        note.setWordWrap(True)
        form = QFormLayout()
        form.addRow(tr("Title"), self.title)
        form.addRow(tr("Language"), self.lang)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText(tr("Auto-tag"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(note)
        lay.addLayout(form)
        lay.addWidget(buttons)


def auto_tag(parent, view):
    """Document > Accessibility > Auto-tag. True when the document was tagged."""
    from . import autotag
    view.commit_pending()
    doc = view.doc
    if autotag.is_tagged(doc):
        QMessageBox.information(parent, tr("Auto-tag"), tr(
            "This document is tagged already. Auto-tag is for untagged documents; use Check "
            "accessibility to see what its tags lack."))
        return False
    dlg = AutoTagDialog(parent, view)
    if dlg.exec() != QDialog.Accepted:
        return False
    title, lang = dlg.title.text().strip(), dlg.lang.tag()
    n = doc.page_count
    progress = _progress(parent, tr("Reading the pages..."), tr("Auto-tag"), 2 * n)

    def step(done, total):
        progress.setValue(done)
        QApplication.processEvents()
        return not progress.wasCanceled()
    try:
        plans = autotag.make_plans(doc, step=step)
    except autotag.Stopped:
        return False
    finally:
        progress.close()
        progress.deleteLater()

    def do():
        autotag.apply(doc, plans, lang=lang)
        if title:
            acc.set_title(doc, title)
        else:
            acc.set_display_title(doc)
    if not view.modify(do, list(range(n))):
        return False
    counts = autotag.counts(plans)
    _done(view, tr("Tagged {pages} pages").format(pages=n))
    text = tr("Tagged {pages} pages: {h} headings, {p} paragraphs, {l} lists, {t} tables, "
              "{f} figures, {a} links, fields and comments.").format(
        pages=n, h=counts["H"], p=counts["P"], l=counts["L"], t=counts["Table"],
        f=counts["Figure"], a=counts["Annot"])
    if counts["Figure"]:
        text += "\n\n" + tr("Figures need a description: Document > Accessibility > Alt "
                            "text.")
    notes = autotag.notes(plans)
    if notes:
        text += "\n\n" + "\n".join(tr("Page {n}: {what}").format(n=i + 1, what=w)
                                   for i, w in notes[:10])
    text += "\n\n" + tr("Check the result with Check accessibility.")
    QMessageBox.information(parent, tr("Auto-tag"), text)
    return True


# ---- Mark as decorative (Edit objects) ----------------------------------------------------
def mark_decorative(parent, view):
    """Document > Accessibility > Mark as decorative: the pictures and shapes selected with
    Edit objects become artifacts."""
    if view.obj_sel is None or not view.obj_sel[1]:
        QMessageBox.information(parent, tr("Mark as decorative"), tr(
            "Select the pictures or shapes with Edit objects first."))
        return
    index, items = view.obj_sel
    if any(it["kind"] == "text" for it in items):
        QMessageBox.information(parent, tr("Mark as decorative"), tr(
            "Mark as decorative is for pictures and shapes: select only those."))
        return
    spans = [(it["obj"]["start"], it["obj"]["end"]) for it in items if "obj" in it]
    n = {"n": 0}

    def do():
        n["n"] = acc.mark_artifacts(view.doc[index], spans)
    if view.modify(do, [index]):
        view.clear_object_selection()
        _done(view, tr("Marked {n} objects as decorative").format(n=n["n"]) if n["n"] != 1
              else tr("Marked 1 object as decorative"))
