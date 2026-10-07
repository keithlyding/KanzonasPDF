"""Main application window: tabs, toolbars, menus, thumbnails sidebar."""

import os

import pymupdf
from PySide6.QtCore import Qt, QSize, QTimer, QSettings
from PySide6.QtGui import (QAction, QActionGroup, QKeySequence, QIcon, QPixmap, QImage,
                           QColor, QPainter)
from PySide6.QtWidgets import (QMainWindow, QTabWidget, QToolBar, QFileDialog, QMessageBox,
                               QLineEdit, QSpinBox, QLabel, QComboBox, QListWidget,
                               QListWidgetItem, QDockWidget, QColorDialog, QToolButton,
                               QInputDialog, QWidget, QSizePolicy)
from PySide6.QtPrintSupport import QPrinter, QPrintDialog

from .document_view import DocumentView

APP_NAME = "KanzonasPDF"
PDF_FILTER = "PDF files (*.pdf);;All files (*)"
TOOLS = [  # (id, label, shortcut, tooltip)
    ("select", "Select", "V", "Select text: drag to copy text to the clipboard (V)"),
    ("hand", "Hand", "H", "Pan the page (H)"),
    ("highlight", "Highlight", "Ctrl+Shift+H", "Highlight text"),
    ("underline", "Underline", "Ctrl+Shift+U", "Underline text"),
    ("strikeout", "Strike", "Ctrl+Shift+S", "Strike out text"),
    ("note", "Note", "N", "Sticky note: click where it should go (N)"),
    ("textbox", "Text box", "T", "Text box: drag a box or click (T)"),
    ("rect", "Rectangle", "R", "Rectangle (R)"),
    ("ellipse", "Ellipse", "E", "Ellipse (E)"),
    ("line", "Line", "L", "Line (L)"),
    ("arrow", "Arrow", "A", "Arrow (A)"),
    ("ink", "Pen", "P", "Freehand pen (P)"),
    ("eraser", "Eraser", "X", "Delete the annotation you click (X)"),
]
ZOOM_PRESETS = ["50%", "75%", "100%", "125%", "150%", "200%", "300%", "400%"]


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = QSettings(APP_NAME, APP_NAME)
        self.setWindowTitle(APP_NAME)
        self.resize(1300, 900)
        self.setAcceptDrops(True)
        self.tool = "select"
        self.color = QColor(self.settings.value("color", "#ffdc00"))

        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.setDocumentMode(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self.setCentralWidget(self.tabs)

        self._build_sidebar()
        self._build_actions()
        self._build_menus()
        self._build_toolbars()
        self.statusBar()
        self._thumb_queue = []
        self._thumb_timer = QTimer(self, interval=0)
        self._thumb_timer.timeout.connect(self._thumb_step)
        self._update_ui()

        geo = self.settings.value("geometry")
        if geo is not None:
            self.restoreGeometry(geo)

    # ---- construction -----------------------------------------------------
    def _act(self, text, slot, shortcut=None, tip=None):
        a = QAction(text, self)
        a.triggered.connect(slot)
        if shortcut:
            a.setShortcut(QKeySequence(shortcut))
        if tip:
            a.setToolTip(tip)
            a.setStatusTip(tip)
        return a

    def _build_actions(self):
        v = self.view
        self.a_open = self._act("&Open...", self.open_dialog, QKeySequence.Open)
        self.a_save = self._act("&Save", self.save, QKeySequence.Save)
        self.a_save_as = self._act("Save &As...", self.save_as, QKeySequence.SaveAs)
        self.a_print = self._act("&Print...", self.print_doc, QKeySequence.Print)
        self.a_close = self._act("&Close tab", lambda: self.close_tab(self.tabs.currentIndex()),
                                 QKeySequence.Close)
        self.a_exit = self._act("E&xit", self.close, "Alt+F4")
        self.a_undo = self._act("&Undo", lambda: v() and v().undo(), QKeySequence.Undo)
        self.a_redo = self._act("&Redo", lambda: v() and v().redo(), QKeySequence.Redo)
        self.a_find = self._act("&Find", self._focus_search, QKeySequence.Find)
        self.a_find_next = self._act("Find next", lambda: self._find(False), QKeySequence.FindNext)
        self.a_find_prev = self._act("Find previous", lambda: self._find(True),
                                     QKeySequence.FindPrevious)
        self.a_zoom_in = self._act("Zoom &in", lambda: v() and v().zoom_in(), QKeySequence.ZoomIn)
        self.a_zoom_out = self._act("Zoom &out", lambda: v() and v().zoom_out(),
                                    QKeySequence.ZoomOut)
        self.a_fit_width = self._act("Fit &width", lambda: v() and v().fit_width(), "Ctrl+2")
        self.a_fit_page = self._act("Fit &page", lambda: v() and v().fit_page(), "Ctrl+0")
        self.a_actual = self._act("&Actual size", lambda: v() and v().set_zoom(1.0), "Ctrl+1")
        self.a_sidebar = self._act("Page &thumbnails", self._toggle_sidebar, "F4")
        self.a_sidebar.setCheckable(True)
        self.a_sidebar.setChecked(True)
        # Ctrl+Shift+Plus can't be used: on most keyboards "+" already needs Shift,
        # so Qt sees it as Ctrl++ (zoom in). Ctrl+R / Ctrl+Shift+R are unambiguous.
        self.a_rot_l = self._act("Rotate page &left", lambda: self._page_op("rot", -90),
                                 "Ctrl+Shift+R", "Rotate page counter-clockwise (Ctrl+Shift+R)")
        self.a_rot_r = self._act("Rotate page &right", lambda: self._page_op("rot", 90),
                                 "Ctrl+R", "Rotate page clockwise (Ctrl+R)")
        self.a_del_page = self._act("&Delete page", lambda: self._page_op("del"))
        self.a_move_up = self._act("Move page &up", lambda: self._page_op("move", -1))
        self.a_move_down = self._act("Move page do&wn", lambda: self._page_op("move", 1))
        self.a_insert_pdf = self._act("&Insert pages from file...", self.insert_from_file)
        self.a_insert_blank = self._act("Insert &blank page after current",
                                        lambda: self._page_op("blank"))
        self.a_extract = self._act("&Extract pages to new file...", self.extract_pages)
        self.a_ocr = self._act("Recognize text (&OCR)...", self.ocr,
                               tip="Make scanned pages searchable and selectable")
        self.a_color = self._act("Color", self.pick_color, tip="Annotation color")
        self.a_about = self._act("&About", self.about)

        self.tool_group = QActionGroup(self)
        self.tool_actions = {}
        for tid, label, sc, tip in TOOLS:
            a = QAction(label, self, checkable=True)
            a.setShortcut(QKeySequence(sc))
            a.setToolTip(tip)
            a.setStatusTip(tip)
            a.triggered.connect(lambda _=False, t=tid: self.set_tool(t))
            self.tool_group.addAction(a)
            self.tool_actions[tid] = a
        self.tool_actions["select"].setChecked(True)
        self._refresh_color_icon()

    def _build_menus(self):
        mb = self.menuBar()
        m = mb.addMenu("&File")
        m.addActions([self.a_open])
        self.recent_menu = m.addMenu("Open &recent")
        self._rebuild_recent()
        m.addActions([self.a_save, self.a_save_as])
        m.addSeparator()
        m.addAction(self.a_print)
        m.addSeparator()
        m.addActions([self.a_close, self.a_exit])
        m = mb.addMenu("&Edit")
        m.addActions([self.a_undo, self.a_redo])
        m.addSeparator()
        m.addActions([self.a_find, self.a_find_next, self.a_find_prev])
        m = mb.addMenu("&View")
        m.addActions([self.a_zoom_in, self.a_zoom_out, self.a_actual, self.a_fit_width,
                      self.a_fit_page])
        m.addSeparator()
        m.addAction(self.a_sidebar)
        m = mb.addMenu("&Tools")
        m.addActions(self.tool_group.actions())
        m.addSeparator()
        m.addAction(self.a_color)
        m.addSeparator()
        m.addAction(self.a_ocr)
        m = mb.addMenu("&Pages")
        m.addActions([self.a_rot_l, self.a_rot_r])
        m.addSeparator()
        m.addActions([self.a_move_up, self.a_move_down, self.a_del_page])
        m.addSeparator()
        m.addActions([self.a_insert_pdf, self.a_insert_blank, self.a_extract])
        m = mb.addMenu("&Help")
        m.addAction(self.a_about)

    def _build_toolbars(self):
        tb = QToolBar("Main")
        tb.setObjectName("main")
        tb.setMovable(False)
        tb.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.addToolBar(tb)
        tb.addActions([self.a_open, self.a_save, self.a_print])
        tb.addSeparator()
        tb.addActions([self.a_undo, self.a_redo])
        tb.addSeparator()
        tb.addAction(self.a_zoom_out)
        self.zoom_box = QComboBox()
        self.zoom_box.setEditable(True)
        self.zoom_box.addItems(ZOOM_PRESETS)
        self.zoom_box.setMinimumWidth(80)
        self.zoom_box.lineEdit().returnPressed.connect(self._zoom_from_box)
        self.zoom_box.activated.connect(lambda _: self._zoom_from_box())
        tb.addWidget(self.zoom_box)
        tb.addAction(self.a_zoom_in)
        tb.addActions([self.a_fit_width, self.a_fit_page])
        tb.addSeparator()
        self.page_spin = QSpinBox()
        self.page_spin.setMinimum(1)
        self.page_spin.setKeyboardTracking(False)
        self.page_spin.valueChanged.connect(lambda n: self.view() and self.view().goto_page(n - 1))
        tb.addWidget(QLabel(" Page "))
        tb.addWidget(self.page_spin)
        self.page_total = QLabel(" / 0 ")
        tb.addWidget(self.page_total)
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        tb.addWidget(spacer)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Find (Ctrl+F)")
        self.search.setClearButtonEnabled(True)
        self.search.setMaximumWidth(260)
        self.search.returnPressed.connect(lambda: self._find(False))
        self.search.textChanged.connect(lambda t: (not t) and self.view()
                                        and self.view().clear_search())
        tb.addWidget(self.search)

        self.addToolBarBreak()
        tt = QToolBar("Tools")
        tt.setObjectName("tools")
        tt.setMovable(False)
        tt.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.addToolBar(tt)
        tt.addActions(self.tool_group.actions()[:2])
        tt.addSeparator()
        tt.addActions(self.tool_group.actions()[2:])
        tt.addSeparator()
        btn = QToolButton()
        btn.setDefaultAction(self.a_color)
        btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        tt.addWidget(btn)
        tt.addSeparator()
        tt.addActions([self.a_rot_l, self.a_rot_r])
        tt.addSeparator()
        tt.addAction(self.a_ocr)

    def _build_sidebar(self):
        self.thumbs = QListWidget()
        self.thumbs.setViewMode(QListWidget.IconMode)
        self.thumbs.setFlow(QListWidget.TopToBottom)
        self.thumbs.setWrapping(False)
        self.thumbs.setMovement(QListWidget.Static)
        self.thumbs.setIconSize(QSize(120, 160))
        self.thumbs.setSpacing(6)
        self.thumbs.setUniformItemSizes(True)
        self.thumbs.currentRowChanged.connect(self._on_thumb_clicked)
        self.thumbs.setContextMenuPolicy(Qt.ActionsContextMenu)
        self.dock = QDockWidget("Pages")
        self.dock.setObjectName("pages")
        self.dock.setFeatures(QDockWidget.DockWidgetClosable)
        self.dock.setWidget(self.thumbs)
        self.dock.setMinimumWidth(170)
        self.dock.visibilityChanged.connect(lambda vis: self.a_sidebar.setChecked(vis))
        self.addDockWidget(Qt.LeftDockWidgetArea, self.dock)

    # ---- helpers ----------------------------------------------------------
    def view(self):
        w = self.tabs.currentWidget()
        return w if isinstance(w, DocumentView) else None

    def _update_ui(self):
        v = self.view()
        has = v is not None
        for a in (self.a_save, self.a_save_as, self.a_print, self.a_close, self.a_find,
                  self.a_find_next, self.a_find_prev, self.a_zoom_in, self.a_zoom_out,
                  self.a_fit_width, self.a_fit_page, self.a_actual, self.a_rot_l, self.a_rot_r,
                  self.a_del_page, self.a_move_up, self.a_move_down, self.a_insert_pdf,
                  self.a_insert_blank, self.a_extract, self.a_ocr):
            a.setEnabled(has)
        self.a_undo.setEnabled(has and v.can_undo())
        self.a_redo.setEnabled(has and v.can_redo())
        self.page_spin.setEnabled(has)
        if has:
            self.page_spin.blockSignals(True)
            self.page_spin.setMaximum(v.page_count())
            self.page_spin.setValue(v.current_page() + 1)
            self.page_spin.blockSignals(False)
            self.page_total.setText(f" / {v.page_count()} ")
            self.zoom_box.setEditText(f"{round(v.zoom * 100)}%")
            name = os.path.basename(v.path)
            self.setWindowTitle(f"{'*' if v.dirty else ''}{name} - {APP_NAME}")
            for i in range(self.tabs.count()):
                w = self.tabs.widget(i)
                self.tabs.setTabText(i, ("*" if w.dirty else "") + os.path.basename(w.path))
                self.tabs.setTabToolTip(i, w.path)
        else:
            self.page_total.setText(" / 0 ")
            self.setWindowTitle(APP_NAME)

    def _refresh_color_icon(self):
        pm = QPixmap(16, 16)
        pm.fill(self.color)
        self.a_color.setIcon(QIcon(pm))

    # ---- files --------------------------------------------------------------
    def open_dialog(self):
        start = self.settings.value("last_dir", "")
        paths, _ = QFileDialog.getOpenFileNames(self, "Open PDF", start, PDF_FILTER)
        for p in paths:
            self.open_file(p)

    def open_file(self, path):
        path = os.path.abspath(path)
        for i in range(self.tabs.count()):
            if os.path.normcase(self.tabs.widget(i).path) == os.path.normcase(path):
                self.tabs.setCurrentIndex(i)
                return
        try:
            v = DocumentView(path)
        except Exception as ex:
            QMessageBox.critical(self, "Could not open file", f"{path}\n\n{ex}")
            return
        v.set_tool(self.tool)
        v.color = self.color
        v.pageChanged.connect(self._on_page_changed)
        v.zoomChanged.connect(lambda _: self._update_ui())
        v.documentChanged.connect(self._on_doc_changed)
        v.structureChanged.connect(self._on_structure_changed)
        v.statusMessage.connect(lambda m: self.statusBar().showMessage(m, 4000))
        idx = self.tabs.addTab(v, os.path.basename(path))
        self.tabs.setCurrentIndex(idx)
        self.settings.setValue("last_dir", os.path.dirname(path))
        self._add_recent(path)

    def _add_recent(self, path):
        recent = [p for p in (self.settings.value("recent") or []) if p != path]
        recent.insert(0, path)
        self.settings.setValue("recent", recent[:10])
        self._rebuild_recent()

    def _rebuild_recent(self):
        self.recent_menu.clear()
        recent = self.settings.value("recent") or []
        if isinstance(recent, str):
            recent = [recent]
        for p in recent:
            a = self.recent_menu.addAction(p)
            a.triggered.connect(lambda _=False, p=p: self.open_file(p))
        self.recent_menu.setEnabled(bool(recent))

    def save(self):
        v = self.view()
        if not v:
            return False
        try:
            v.save()
        except Exception as ex:
            QMessageBox.critical(self, "Save failed",
                                 f"{ex}\n\nIf the file is open in another program, close it "
                                 "or use Save As.")
            return False
        self.statusBar().showMessage("Saved " + v.path, 4000)
        return True

    def save_as(self):
        v = self.view()
        if not v:
            return False
        path, _ = QFileDialog.getSaveFileName(self, "Save As", v.path, PDF_FILTER)
        if not path:
            return False
        try:
            v.save(path)
        except Exception as ex:
            QMessageBox.critical(self, "Save failed", str(ex))
            return False
        self._add_recent(v.path)
        self._update_ui()
        return True

    def _confirm_close(self, v):
        if not v.dirty:
            return True
        self.tabs.setCurrentWidget(v)
        r = QMessageBox.question(self, "Unsaved changes",
                                 f"Save changes to {os.path.basename(v.path)}?",
                                 QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
        if r == QMessageBox.Save:
            return self.save()
        return r == QMessageBox.Discard

    def close_tab(self, index):
        v = self.tabs.widget(index)
        if v is None or not self._confirm_close(v):
            return
        self.tabs.removeTab(index)
        v.close_doc()
        v.deleteLater()
        self._update_ui()

    def closeEvent(self, e):
        for i in range(self.tabs.count()):
            if not self._confirm_close(self.tabs.widget(i)):
                e.ignore()
                return
        self.settings.setValue("geometry", self.saveGeometry())
        e.accept()

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        for url in e.mimeData().urls():
            if url.isLocalFile():
                self.open_file(url.toLocalFile())

    # ---- printing -----------------------------------------------------------
    def print_doc(self):
        v = self.view()
        if not v:
            return
        printer = QPrinter(QPrinter.HighResolution)
        printer.setDocName(os.path.basename(v.path))
        printer.setFromTo(1, v.page_count())
        dlg = QPrintDialog(printer, self)
        dlg.setMinMax(1, v.page_count())
        dlg.setOption(QPrintDialog.PrintPageRange, True)
        dlg.setOption(QPrintDialog.PrintCurrentPage, True)
        if dlg.exec() != QPrintDialog.Accepted:
            return
        if printer.printRange() == QPrinter.CurrentPage:
            pages = [v.current_page()]
        elif printer.printRange() == QPrinter.PageRange:
            pages = list(range(printer.fromPage() - 1, printer.toPage()))
        else:
            pages = list(range(v.page_count()))
        dpi = min(printer.resolution(), 300)
        painter = QPainter()
        if not painter.begin(printer):
            QMessageBox.critical(self, "Print", "Could not start printing.")
            return
        self.statusBar().showMessage("Printing...")
        try:
            for n, i in enumerate(pages):
                if n:
                    printer.newPage()
                pm = v.doc[i].get_pixmap(dpi=dpi, annots=True)
                img = QImage(pm.samples, pm.width, pm.height, pm.stride, QImage.Format_RGB888)
                area = painter.viewport()
                size = img.size().scaled(area.size(), Qt.KeepAspectRatio)
                painter.setViewport(area.x(), area.y(), size.width(), size.height())
                painter.setWindow(img.rect())
                painter.drawImage(0, 0, img)
                painter.setViewport(area)
                painter.setWindow(area)
        finally:
            painter.end()
        self.statusBar().showMessage("Sent to printer", 4000)

    # ---- tools / search / pages --------------------------------------------
    def set_tool(self, tool):
        self.tool = tool
        self.tool_actions[tool].setChecked(True)
        for i in range(self.tabs.count()):
            self.tabs.widget(i).set_tool(tool)

    def pick_color(self):
        c = QColorDialog.getColor(self.color, self, "Annotation color")
        if c.isValid():
            self.color = c
            self.settings.setValue("color", c.name())
            self._refresh_color_icon()
            for i in range(self.tabs.count()):
                self.tabs.widget(i).color = c

    def _focus_search(self):
        self.search.setFocus()
        self.search.selectAll()

    def _find(self, backwards):
        v = self.view()
        if not v:
            return
        if not v.find(self.search.text(), backwards) and self.search.text():
            self.statusBar().showMessage("No matches", 4000)

    def _zoom_from_box(self):
        v = self.view()
        if not v:
            return
        try:
            v.set_zoom(float(self.zoom_box.currentText().strip().rstrip("%")) / 100)
        except ValueError:
            pass
        self._update_ui()

    def _page_op(self, op, arg=None):
        v = self.view()
        if not v:
            return
        cur = v.current_page()
        if op == "rot":
            v.rotate_page(cur, arg)
        elif op == "del":
            if QMessageBox.question(self, "Delete page",
                                    f"Delete page {cur + 1}?") == QMessageBox.Yes:
                v.delete_page(cur)
        elif op == "move":
            v.move_page(cur, arg)
        elif op == "blank":
            v.insert_blank(cur + 1)

    def insert_from_file(self):
        v = self.view()
        if not v:
            return
        path, _ = QFileDialog.getOpenFileName(self, "Insert pages from",
                                              self.settings.value("last_dir", ""), PDF_FILTER)
        if not path:
            return
        choices = ["After current page", "At the end", "At the beginning"]
        where, ok = QInputDialog.getItem(self, "Insert pages", "Insert:", choices, 0, False)
        if not ok:
            return
        at = {0: v.current_page() + 1, 1: -1, 2: 0}[choices.index(where)]
        v.insert_pdf(path, at)

    def extract_pages(self):
        v = self.view()
        if not v:
            return
        n = v.page_count()
        cur = v.current_page() + 1
        text, ok = QInputDialog.getText(self, "Extract pages",
                                        f"Page range (1-{n}), e.g. 3-7:", text=f"{cur}-{cur}")
        if not ok:
            return
        try:
            parts = text.replace(" ", "").split("-")
            first = int(parts[0])
            last = int(parts[-1])
            if not 1 <= first <= last <= n:
                raise ValueError
        except ValueError:
            QMessageBox.warning(self, "Extract pages", "Invalid page range.")
            return
        base = os.path.splitext(v.path)[0]
        path, _ = QFileDialog.getSaveFileName(self, "Save extracted pages",
                                              f"{base}_p{first}-{last}.pdf", PDF_FILTER)
        if path:
            v.extract_pages(first - 1, last - 1, path)
            self.statusBar().showMessage("Saved " + path, 4000)

    def ocr(self):
        v = self.view()
        if not v:
            return
        choices = ["Pages without text (scanned pages)", "Current page only",
                   "All pages (even ones that already have text)"]
        pick, ok = QInputDialog.getItem(self, "Recognize text (OCR)",
                                        "Which pages?", choices, 0, False)
        if not ok:
            return
        n = choices.index(pick)
        if n == 1:
            pages = [v.current_page()]
            if v.page_has_text(pages[0]) and QMessageBox.question(
                    self, "OCR", "This page already has text. OCR it anyway? "
                                 "(Text may become duplicated.)") != QMessageBox.Yes:
                return
        elif n == 0:
            pages = [i for i in range(v.page_count()) if not v.page_has_text(i)]
            if not pages:
                QMessageBox.information(self, "OCR", "Every page already has text. "
                                        "Nothing to recognize.")
                return
        else:
            pages = list(range(v.page_count()))
        v.run_ocr(pages)

    def _toggle_sidebar(self):
        self.dock.setVisible(not self.dock.isVisible())

    def about(self):
        QMessageBox.about(self, "About " + APP_NAME,
                          f"<b>{APP_NAME}</b><br>A free, fast PDF reader and editor.<br><br>"
                          f"Built on PyMuPDF {pymupdf.VersionBind} (MuPDF) and Qt (PySide6).")

    # ---- signals from views --------------------------------------------------
    def _on_tab_changed(self, _):
        self._rebuild_thumbs()
        self._update_ui()

    def _on_page_changed(self, page):
        if self.sender() is not self.view():
            return
        self.thumbs.blockSignals(True)
        self.thumbs.setCurrentRow(page)
        self.thumbs.blockSignals(False)
        self._update_ui()

    def _on_doc_changed(self):
        v = self.sender()
        if v is self.view():
            self._queue_thumb(v.current_page(), front=True)
        self._update_ui()

    def _on_structure_changed(self):
        if self.sender() is self.view():
            self._rebuild_thumbs()
        self._update_ui()

    def _on_thumb_clicked(self, row):
        v = self.view()
        if v and row >= 0:
            v.goto_page(row)

    # ---- thumbnails (rendered a few at a time so opening big files stays snappy) ----
    def _rebuild_thumbs(self):
        self._thumb_timer.stop()
        self.thumbs.blockSignals(True)
        self.thumbs.clear()
        v = self.view()
        self._thumb_queue = []
        if v:
            blank = QPixmap(120, 160)
            blank.fill(Qt.white)
            for i in range(v.page_count()):
                self.thumbs.addItem(QListWidgetItem(QIcon(blank), str(i + 1)))
            self.thumbs.setCurrentRow(v.current_page())
            self._thumb_queue = list(range(v.page_count()))
            self._thumb_timer.start()
        self.thumbs.blockSignals(False)

    def _queue_thumb(self, i, front=False):
        if i in self._thumb_queue:
            self._thumb_queue.remove(i)
        if front:
            self._thumb_queue.insert(0, i)
        else:
            self._thumb_queue.append(i)
        self._thumb_timer.start()

    def _thumb_step(self):
        v = self.view()
        if not v or not self._thumb_queue:
            self._thumb_timer.stop()
            return
        for _ in range(3):
            if not self._thumb_queue:
                break
            i = self._thumb_queue.pop(0)
            if i >= v.page_count() or i >= self.thumbs.count():
                continue
            page = v.doc[i]
            s = min(120 / page.rect.width, 160 / page.rect.height)
            pm = page.get_pixmap(matrix=pymupdf.Matrix(s, s), annots=True)
            img = QImage(pm.samples, pm.width, pm.height, pm.stride,
                         QImage.Format_RGB888).copy()
            self.thumbs.item(i).setIcon(QIcon(QPixmap.fromImage(img)))
