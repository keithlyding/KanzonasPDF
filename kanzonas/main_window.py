"""Main application window: tabs, toolbars, menus, thumbnails sidebar."""

import os
import time
from concurrent.futures import ThreadPoolExecutor

import pymupdf
from PySide6.QtCore import Qt, QSize, QTimer, QSettings, QEvent
from PySide6.QtGui import (QAction, QActionGroup, QKeySequence, QIcon, QPixmap, QImage,
                           QColor, QPainter)
from PySide6.QtWidgets import (QMainWindow, QTabWidget, QToolBar, QFileDialog, QMessageBox,
                               QLineEdit, QSpinBox, QLabel, QComboBox, QListWidget,
                               QListWidgetItem, QDockWidget, QAbstractItemView, QToolButton,
                               QVBoxLayout, QHBoxLayout, QMenu, QProgressDialog,
                               QInputDialog, QWidget, QSizePolicy, QApplication, QScrollArea,
                               QDialog, QFormLayout, QRadioButton, QDialogButtonBox, QCheckBox,
                               QPushButton)
from PySide6.QtPrintSupport import QPrinter, QPrintDialog

from . import __version__, annotations, export, signatures, theme
from .document_view import DocumentView
from .properties import PropertiesPanel
from .markups_panel import MarkupsPanel
from .tool_chest import ToolChestPanel, tool_for

APP_NAME = "KanzonasPDF"
APP_TITLE = f"KanzonasPDF v{__version__}"
PDF_FILTER = "PDF files (*.pdf);;All files (*)"
TOOLS = [  # (id, label, shortcut, tooltip)
    ("select", "Select", "V", "Select: drag across text to copy it; click an annotation "
                              "to move, resize or restyle it (V)"),
    ("hand", "Hand", "H", "Pan the page (H)"),
    ("edittext", "Edit text", "Ctrl+E", "Edit existing text: click a line of text (Ctrl+E)"),
    ("highlight", "Highlight", "Ctrl+Shift+H", "Highlight text"),
    ("underline", "Underline", "Ctrl+Shift+U", "Underline text"),
    ("strikeout", "Strike", "Ctrl+Shift+X", "Strike out text (Ctrl+Shift+X)"),
    ("comment", "Comment", "C", "Comment on text: select text, it's highlighted with a note (C)"),
    ("note", "Note", "N", "Sticky note: click where it should go (N)"),
    ("textbox", "Text box", "T", "Text box: drag a box or click (T)"),
    ("callout", "Callout", "K", "Callout: press on the point, drag to where the text goes (K)"),
    ("rect", "Rectangle", "R", "Rectangle (R)"),
    ("ellipse", "Ellipse", "E", "Ellipse (E)"),
    ("cloud", "Cloud", "D", "Revision cloud: drag a box (D)"),
    ("polygon", "Polygon", "Y", "Polygon: click each corner, double-click or Enter to finish (Y)"),
    ("line", "Line", "L", "Line (L)"),
    ("arrow", "Arrow", "A", "Arrow (A)"),
    ("polyline", "Polyline", "Shift+L", "Polyline: click each point, double-click or Enter to finish"),
    ("ink", "Pen", "P", "Freehand pen (P)"),
    ("stamp", "Stamp", "M", "Stamp (Approved, Draft, ... or your own image): click to place (M)"),
    ("eraser", "Eraser", "X", "Delete the annotation you click (X)"),
    ("signature", "Sign", "G", "Place your saved signature (and date): click where it goes (G)"),
    ("initials", "Initials", "I", "Place your saved initials (and date): click where they go (I)"),
]
FORM_TOOLS = [  # form design tools: drag a box (or click) to add a field
    ("f_text", "Text field", "Text field: drag a box"),
    ("f_check", "Checkbox", "Checkbox: click or drag"),
    ("f_radio", "Option button", "Option (radio) button: click; same group name = pick one"),
    ("f_combo", "Dropdown", "Dropdown list: drag a box, then enter the choices"),
    ("f_sign", "Signature field", "Signature field: others click it to sign"),
]
MEASURE_TOOLS = [
    ("m_length", "Length", "Shift+M", "Measure length: drag from point to point (Shift+M)"),
    ("m_poly", "Polylength", "", "Measure along a path: click points, double-click or Enter to finish"),
    ("m_area", "Area", "Shift+A", "Measure area and perimeter: click corners, double-click or Enter (Shift+A)"),
    ("m_count", "Count", "Shift+C", "Count: click each item; set the group name in Properties (Shift+C)"),
    ("m_calibrate", "Calibrate", "", "Calibrate: drag along a known dimension, then type its real length"),
]
EXTRA_TOOLS = [  # tools reached from menus, not the toolbar
    ("redact", "&Redact (mark text or area)", "Shift+R",
     "Redact: drag across text, or drag a box over any area; then Apply redactions"),
]
EXPORTS = [  # (id, menu label, file filter, extension)
    ("word", "Microsoft &Word (.docx)...", "Word document (*.docx)", "docx"),
    ("excel", "Microsoft &Excel (.xlsx)...", "Excel workbook (*.xlsx)", "xlsx"),
    ("ppt", "Microsoft &PowerPoint (.pptx)...", "PowerPoint presentation (*.pptx)", "pptx"),
    ("dxf", "&AutoCAD drawing (.dxf)...", "AutoCAD DXF (*.dxf)", "dxf"),
    ("png", "Images (P&NG)...", "PNG image (*.png)", "png"),
    ("jpg", "Images (&JPEG)...", "JPEG image (*.jpg)", "jpg"),
    ("txt", "Plain &text (.txt)...", "Text file (*.txt)", "txt"),
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
        self._sig_cache = {}            # kind -> png, for this run of the app only

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
        self.scale_label = QLabel()
        self.statusBar().addPermanentWidget(self.scale_label)
        self._thumb_queue = []
        self._thumb_timer = QTimer(self, interval=0)
        self._thumb_timer.timeout.connect(self._thumb_step)
        self._build_split()
        self._apply_icons()
        self._apply_saved_shortcuts()
        self._update_ui()
        self._refresh_props()
        QApplication.instance().installEventFilter(self)

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
        # Ctrl+Shift+Plus/Minus are caught by an event filter (see eventFilter): "+" needs
        # Shift on most keyboards, so normal shortcuts would collide with zoom (Ctrl++).
        # The key names are shown in the menu text after a tab.
        self.a_rot_l = self._act("Rotate page &left\tCtrl+Shift+-", lambda: self._page_op("rot", -90),
                                 tip="Rotate page counter-clockwise (Ctrl+Shift+Minus)")
        self.a_rot_r = self._act("Rotate page &right\tCtrl+Shift++", lambda: self._page_op("rot", 90),
                                 tip="Rotate page clockwise (Ctrl+Shift+Plus)")
        self.a_rot_l.setIconText("Rotate left")
        self.a_rot_r.setIconText("Rotate right")
        self.a_del_page = self._act("&Delete page", lambda: self._page_op("del"))
        self.a_move_up = self._act("Move page &up", lambda: self._page_op("move", -1),
                                   "Ctrl+Shift+Up", "Move current page up (Ctrl+Shift+Up)")
        self.a_move_down = self._act("Move page do&wn", lambda: self._page_op("move", 1),
                                     "Ctrl+Shift+Down", "Move current page down (Ctrl+Shift+Down)")
        self.a_insert_pdf = self._act("&Insert pages from file...", self.insert_from_file)
        self.a_insert_blank = self._act("Insert &blank page after current",
                                        lambda: self._page_op("blank"))
        self.a_extract = self._act("&Extract pages to new file...", self.extract_pages)
        self.a_ocr = self._act("Recognize text (&OCR)...", self.ocr,
                               tip="Make scanned pages searchable and selectable")
        self.a_props = self._act("&Properties panel", self._toggle_props, "F6")
        self.a_props.setCheckable(True)
        self.a_props.setChecked(True)
        self.a_cards = self._act("Show &comment boxes", self._toggle_cards)
        self.a_cards.setCheckable(True)
        self.a_cards.setChecked(self.settings.value("comment_boxes", "true") != "false")
        self.a_setup_sig = self._act("Set up my &signature...", lambda: self.setup_signature("signature"))
        self.a_setup_init = self._act("Set up my &initials...", lambda: self.setup_signature("initials"))
        self.a_protect = self._act("&Protect document from changes when saved", self._toggle_protect,
                                   tip="Anyone can read and print it; editing software that honours "
                                       "PDF permissions won't change it")
        self.a_protect.setCheckable(True)
        self.a_unlock = self._act("&Unlock with password...", self.unlock_doc)
        self.export_actions = []
        for eid, label, _flt, _ext in EXPORTS:
            a = self._act(label, lambda _=False, e=eid: self.export_as(e))
            self.export_actions.append(a)
        self.a_chest = self._act("Tool &chest", lambda: (self.chest_dock.show(), self.chest_dock.raise_()), "F8")
        self.a_compare = self._act("&Compare documents...", self.compare_documents,
                                   tip="Compare this document with another revision")
        self.a_header = self._act("&Header && footer, page numbers, Bates...", self.header_footer)
        self.a_watermark = self._act("&Watermark...", self.watermark)
        self.a_compress = self._act("&Compress (save a smaller copy)...", self.compress)
        self.a_bookmarks = self._act("&Bookmarks", self._show_bookmarks, "F9")
        self.a_search_redact = self._act("&Search && redact...", self.search_redact)
        self.a_apply_redact = self._act("&Apply redactions...", self.apply_redactions)
        self.a_digisign = self._act("&Digitally sign with certificate...", self.digital_sign)
        self.a_sig_details = self._act("Digital signature &details...", self.signature_details)
        self.a_set_scale = self._act("Set &scale...", self.set_scale)
        self.a_measure_summary = self._act("Measurement &summary...", self.measure_summary)
        self.a_labels = self._act("Show text &labels on toolbars", self._toggle_labels)
        self.a_labels.setCheckable(True)
        self.a_labels.setChecked(self.settings.value("toolbar_labels", "false") == "true")
        self.theme_group = QActionGroup(self)
        self.theme_actions = {}
        for key, label in (("system", "Match &Windows"), ("light", "&Light"), ("dark", "&Dark")):
            a = QAction(label, self, checkable=True)
            a.triggered.connect(lambda _=False, k=key: self.set_theme(k))
            self.theme_group.addAction(a)
            self.theme_actions[key] = a
        self.theme_actions[self.settings.value("theme", "system")].setChecked(True)
        self.a_split = self._act("&Split view", self._toggle_split, "F10")
        self.a_split.setCheckable(True)
        self.a_shortcuts = self._act("&Keyboard shortcuts...", self.edit_shortcuts)
        self.a_markups = self._act("&Markups list", self._toggle_markups, "F7")
        self.a_markups.setCheckable(True)
        self.a_author = self._act("&Author name for markups...", self._set_author)
        self.a_flatten = self._act("&Flatten...", self.flatten,
                                   tip="Make annotations and form fields a permanent part of the page")
        self.a_delete_annot = self._act("Delete selected annotation",
                                        lambda: v() and v().delete_selected())
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
        self.tool_group.triggered.connect(lambda _a: self._clear_chest())
        for tid, label, sc, tip in MEASURE_TOOLS + EXTRA_TOOLS:
            a = QAction(label, self, checkable=True)
            if sc:
                a.setShortcut(QKeySequence(sc))
            a.setToolTip(tip)
            a.setStatusTip(tip)
            a.triggered.connect(lambda _=False, t=tid: self.set_tool(t))
            self.tool_group.addAction(a)
            self.tool_actions[tid] = a
        for tid, label, tip in FORM_TOOLS:
            a = QAction(label, self, checkable=True)
            a.setToolTip(tip)
            a.setStatusTip(tip)
            a.triggered.connect(lambda _=False, t=tid: self.set_tool(t))
            self.tool_group.addAction(a)
            self.tool_actions[tid] = a

    def _build_menus(self):
        mb = self.menuBar()
        m = mb.addMenu("&File")
        m.addActions([self.a_open])
        self.recent_menu = m.addMenu("Open &recent")
        self._rebuild_recent()
        m.addActions([self.a_save, self.a_save_as])
        em = m.addMenu("&Export to")
        em.addActions(self.export_actions)
        m.addAction(self.a_compare)
        m.addSeparator()
        m.addAction(self.a_print)
        m.addSeparator()
        m.addActions([self.a_close, self.a_exit])
        m = mb.addMenu("&Edit")
        m.addActions([self.a_undo, self.a_redo])
        m.addAction(self.a_delete_annot)
        m.addSeparator()
        m.addAction(self.a_author)
        m.addSeparator()
        m.addActions([self.a_find, self.a_find_next, self.a_find_prev])
        m = mb.addMenu("&View")
        m.addActions([self.a_zoom_in, self.a_zoom_out, self.a_actual, self.a_fit_width,
                      self.a_fit_page])
        m.addSeparator()
        m.addActions([self.a_sidebar, self.a_props, self.a_chest, self.a_markups, self.a_cards])
        m.addSeparator()
        m.addAction(self.a_split)
        tm = m.addMenu("&Theme")
        tm.addActions(list(self.theme_actions.values()))
        m.addAction(self.a_labels)
        m.addSeparator()
        m.addAction(self.a_shortcuts)
        m = mb.addMenu("&Tools")
        m.addActions(self.tool_group.actions())
        m.addSeparator()
        m.addAction(self.a_props)
        m.addSeparator()
        m.addActions([self.a_ocr, self.a_flatten])
        m = mb.addMenu("&Document")
        m.addActions([self.a_header, self.a_watermark])
        m.addSeparator()
        m.addAction(self.a_bookmarks)
        m.addSeparator()
        rm = m.addMenu("&Redaction")
        rm.addActions([self.tool_actions["redact"], self.a_search_redact, self.a_apply_redact])
        m.addSeparator()
        m.addActions([self.a_compress, self.a_compare, self.a_flatten])
        m = mb.addMenu("&Measure")
        m.addActions([self.tool_actions[t[0]] for t in MEASURE_TOOLS])
        m.addSeparator()
        m.addActions([self.a_set_scale, self.a_measure_summary])
        m = mb.addMenu("&Sign")
        m.addActions([self.tool_actions["signature"], self.tool_actions["initials"]])
        m.addSeparator()
        m.addActions([self.a_setup_sig, self.a_setup_init])
        m.addSeparator()
        m.addActions([self.a_protect, self.a_unlock])
        m.addSeparator()
        m.addActions([self.a_digisign, self.a_sig_details])
        m = mb.addMenu("F&orms")
        m.addActions([self.tool_actions[t] for t, _, _ in FORM_TOOLS])
        m.addSeparator()
        hint = m.addAction("To fill in a form: use Select or Hand and click a field")
        hint.setEnabled(False)
        m = mb.addMenu("&Pages")
        m.addActions([self.a_rot_l, self.a_rot_r])
        m.addSeparator()
        m.addActions([self.a_move_up, self.a_move_down, self.a_del_page])
        m.addSeparator()
        m.addActions([self.a_insert_pdf, self.a_insert_blank, self.a_extract])
        m = mb.addMenu("&Help")
        m.addAction(self.a_about)

    def _build_toolbars(self):
        tb = self.main_tb = QToolBar("Main")
        tb.setObjectName("main")
        tb.setMovable(False)
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
        tt = self.tools_tb = QToolBar("Tools")
        tt.setObjectName("tools")
        tt.setMovable(False)
        self.addToolBar(tt)
        shapes = ("rect", "ellipse", "cloud", "polygon", "line", "arrow", "polyline", "ink")
        main_tools = [self.tool_actions[t[0]] for t in TOOLS if t[0] not in shapes]
        tt.addActions(main_tools[:3])
        tt.addSeparator()
        tt.addActions(main_tools[3:main_tools.index(self.tool_actions["stamp"])])
        # shapes share one button: click = last used shape, arrow = pick another
        self.shapes_btn = QToolButton()
        self.shapes_btn.setPopupMode(QToolButton.MenuButtonPopup)
        smenu = QMenu(self.shapes_btn)
        smenu.addActions([self.tool_actions[t] for t in shapes])
        self.shapes_btn.setMenu(smenu)
        self.shapes_btn.setDefaultAction(self.tool_actions["rect"])
        smenu.triggered.connect(self.shapes_btn.setDefaultAction)
        tt.addWidget(self.shapes_btn)
        tt.addActions(main_tools[main_tools.index(self.tool_actions["stamp"]):])
        self.measure_btn = QToolButton()
        self.measure_btn.setPopupMode(QToolButton.MenuButtonPopup)
        mmenu = QMenu(self.measure_btn)
        mmenu.addActions([self.tool_actions[t[0]] for t in MEASURE_TOOLS])
        mmenu.addSeparator()
        mmenu.addActions([self.a_set_scale, self.a_measure_summary])
        self.measure_btn.setMenu(mmenu)
        self.measure_btn.setDefaultAction(self.tool_actions["m_length"])
        mmenu.triggered.connect(lambda a: a.isCheckable() and self.measure_btn.setDefaultAction(a))
        tt.addWidget(self.measure_btn)
        tt.addSeparator()
        tt.addAction(self.a_ocr)
        tt.addActions([self.a_rot_l, self.a_rot_r])
        tt.addSeparator()
        forms_btn = self.forms_btn = QToolButton()
        forms_btn.setText("Form fields")
        forms_btn.setToolTip("Form field tools")
        forms_btn.setPopupMode(QToolButton.InstantPopup)
        fmenu = QMenu(forms_btn)
        fmenu.addActions([self.tool_actions[t] for t, _, _ in FORM_TOOLS])
        forms_btn.setMenu(fmenu)
        tt.addWidget(forms_btn)

    def _build_sidebar(self):
        self.thumbs = QListWidget()
        self.thumbs.setViewMode(QListWidget.ListMode)
        self.thumbs.setIconSize(QSize(120, 160))
        self.thumbs.setSpacing(4)
        self.thumbs.setUniformItemSizes(True)
        # drag a thumbnail to a new position to reorder pages (only when unlocked)
        self.thumbs.setDefaultDropAction(Qt.MoveAction)
        self.thumbs.setDropIndicatorShown(True)
        self.thumbs.model().rowsMoved.connect(self._on_thumb_moved)
        self.lock_btn = QToolButton()
        self.lock_btn.setCheckable(True)
        self.lock_btn.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.lock_btn.toggled.connect(self._set_pages_locked)
        side = QWidget()
        sl = QVBoxLayout(side)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(2)
        sl.addWidget(self.lock_btn)
        sl.addWidget(self.thumbs)
        self.thumbs.currentRowChanged.connect(self._on_thumb_clicked)
        self.thumbs.setContextMenuPolicy(Qt.ActionsContextMenu)
        self.dock = QDockWidget("Pages")
        self.dock.setObjectName("pages")
        self.dock.setFeatures(QDockWidget.DockWidgetClosable)
        # Pages and Bookmarks are tabs inside one panel (two tabbed dock groups on both sides
        # of the window trigger a Qt bug that draws a phantom duplicate tab bar).
        self.left_tabs = QTabWidget()
        self.left_tabs.setTabPosition(QTabWidget.South)
        self.left_tabs.setDocumentMode(True)
        self.left_tabs.addTab(side, "Pages")
        self.dock.setWidget(self.left_tabs)
        # locked by default so pages can't be moved by accident; remembered between sessions
        locked = self.settings.value("pages_locked", "true") != "false"
        self.lock_btn.setChecked(locked)
        self._set_pages_locked(locked)
        self.dock.setMinimumWidth(170)
        self.dock.visibilityChanged.connect(lambda vis: self.a_sidebar.setChecked(vis))
        self.addDockWidget(Qt.LeftDockWidgetArea, self.dock)

        from .bookmarks_panel import BookmarksPanel
        self.bookmarks = BookmarksPanel()
        self.bookmarks.current_page = lambda: self.view().current_page() if self.view() else 0
        self.bookmarks.jump.connect(lambda i: self.view() and self.view().goto_page(i))
        self.bookmarks.changed.connect(lambda toc: self.view() and self.view().set_toc(toc))
        self.left_tabs.addTab(self.bookmarks, "Bookmarks")

        self.props = PropertiesPanel()
        self.props.propsChanged.connect(self._on_props_changed)
        self.props.resetRequested.connect(self._reset_tool_defaults)
        scroll = QScrollArea()
        scroll.setWidget(self.props)
        scroll.setWidgetResizable(True)
        self.props_dock = QDockWidget("Properties")
        self.props_dock.setObjectName("properties")
        self.props_dock.setFeatures(QDockWidget.DockWidgetClosable)
        self.props_dock.setWidget(scroll)
        self.props_dock.setMinimumWidth(220)
        self.props_dock.visibilityChanged.connect(lambda vis: self.a_props.setChecked(vis))
        self.addDockWidget(Qt.RightDockWidgetArea, self.props_dock)

        self.chest = ToolChestPanel()
        self.chest.use.connect(self._use_chest_tool)
        self.chest.addRequested.connect(self._add_to_chest)
        self.chest_dock = QDockWidget("Tool chest")
        self.chest_dock.setObjectName("toolchest")
        self.chest_dock.setWidget(self.chest)
        self.chest_dock.setFeatures(QDockWidget.DockWidgetClosable)
        self.addDockWidget(Qt.RightDockWidgetArea, self.chest_dock)
        self.tabifyDockWidget(self.props_dock, self.chest_dock)
        self.props_dock.raise_()
        self.resizeDocks([self.dock, self.props_dock], [180, 240], Qt.Horizontal)

        self.markups = MarkupsPanel()
        self.markups.activated.connect(lambda i, x: self.view() and self.view().reveal(i, x))
        self.markups_dock = QDockWidget("Markups list")
        self.markups_dock.setObjectName("markups")
        self.markups_dock.setWidget(self.markups)
        self.addDockWidget(Qt.BottomDockWidgetArea, self.markups_dock)
        self.markups_dock.hide()
        self.markups_dock.visibilityChanged.connect(self._markups_visible)
        self._markups_timer = QTimer(self, singleShot=True, interval=400)
        self._markups_timer.timeout.connect(self._refresh_markups)

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
                  self.a_insert_blank, self.a_extract, self.a_ocr, self.a_flatten,
                  self.a_protect, self.a_unlock, self.a_set_scale, self.a_measure_summary,
                  self.a_compare, self.a_header, self.a_watermark, self.a_compress,
                  self.a_search_redact, self.a_apply_redact, self.a_digisign, self.a_sig_details,
                  *self.export_actions):
            a.setEnabled(has)
        self.a_delete_annot.setEnabled(has and v.selection is not None)
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
            self.scale_label.setText(v.page_scale_text(v.current_page()))
            name = os.path.basename(v.path) + (" [protected]" if v.read_only else "")
            self.a_protect.setChecked(v.protect_on_save)
            self.setWindowTitle(f"{'*' if v.dirty else ''}{name} - {APP_TITLE}")
            for i in range(self.tabs.count()):
                w = self.tabs.widget(i)
                self.tabs.setTabText(i, ("*" if w.dirty else "") + os.path.basename(w.path))
                self.tabs.setTabToolTip(i, w.path)
        else:
            self.page_total.setText(" / 0 ")
            self.scale_label.setText("")
            self.setWindowTitle(APP_TITLE)

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
        v.show_comment_boxes = self.a_cards.isChecked()
        v.selectionChanged.connect(self._on_selection_changed)
        v.signedDocument.connect(self._on_signed)
        v.selectToolRequested.connect(lambda: self.set_tool("select"))
        v.calibrateRequested.connect(self._calibrate)
        v.scaleChanged.connect(self._update_ui)
        v.documentChanged.connect(self._markups_timer.start)
        v.structureChanged.connect(self._markups_timer.start)
        v.requestSignature.connect(self._sign_field)
        for kind, png in self._sig_cache.items():
            v.set_sig_image(kind, png)
        if v.read_only:
            QTimer.singleShot(0, lambda: QMessageBox.information(
                self, "Protected document", "This PDF is protected against changes. You can "
                "read, search and print it. Sign > Unlock with password... if you have the "
                "owner password."))
        v.pageChanged.connect(self._on_page_changed)
        v.zoomChanged.connect(lambda _: self._update_ui())
        v.documentChanged.connect(self._on_doc_changed)
        v.structureChanged.connect(self._on_structure_changed)
        v.statusMessage.connect(lambda m: self.statusBar().showMessage(m, 4000))
        v.check_digital_signatures()
        state = self._file_states().get(os.path.normcase(path))
        if state:
            v.initial_state = state            # reopen at the last page and zoom
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
        self._remember_state(v)
        if self._split_view is not None and getattr(self._split_view, "_source", None) is v:
            self._split_view.deleteLater()
            self._split_view = None
            self.split_dock.hide()
        self.tabs.removeTab(index)
        v.close_doc()
        v.deleteLater()
        self._update_ui()

    def closeEvent(self, e):
        for i in range(self.tabs.count()):
            if not self._confirm_close(self.tabs.widget(i)):
                e.ignore()
                return
        for i in range(self.tabs.count()):
            self._remember_state(self.tabs.widget(i))
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
        if tool in ("signature", "initials") and tool not in self._sig_cache:
            png = signatures.get_image(self, tool)
            if png is None:
                self.tool_actions[self.tool].setChecked(True)
                return
            self._cache_sig(tool, png)
        self.tool = tool
        self.tool_actions[tool].setChecked(True)
        for i in range(self.tabs.count()):
            self.tabs.widget(i).set_tool(tool)
        self._refresh_props()

    # ---- properties panel / tool defaults -------------------------------------
    def _refresh_props(self):
        v = self.view()
        if v is not None and v.selected_model is not None:
            m = v.selected_model
            self.props.show_target(m["kind"], m["props"], selected=True)
        elif self.tool in annotations.DEFAULTS:
            self.props.show_target(self.tool, annotations.tool_props(self.tool))
        else:
            self.props.show_target(None, None)

    def _on_props_changed(self, props):
        v = self.view()
        if v is not None and v.selected_model is not None:
            v.update_selected_props(props)
        elif annotations.OVERRIDE["tool"] == self.tool:
            annotations.OVERRIDE["props"] = dict(props)
        elif self.tool in annotations.DEFAULTS:
            annotations.set_tool_props(self.tool, props)

    def _reset_tool_defaults(self):
        if self.tool in annotations.DEFAULTS:
            annotations.reset_tool_props(self.tool)
            self._refresh_props()

    def _on_selection_changed(self):
        if self.sender() is self.view():
            self._refresh_props()
            self._update_ui()

    def _toggle_props(self):
        self.props_dock.setVisible(not self.props_dock.isVisible())

    def _toggle_cards(self):
        on = self.a_cards.isChecked()
        self.settings.setValue("comment_boxes", "true" if on else "false")
        for i in range(self.tabs.count()):
            w = self.tabs.widget(i)
            w.show_comment_boxes = on
            for pw in w.pages:
                pw.update()

    # ---- rotate keys (Ctrl+Shift+Plus / Minus) ------------------------------
    _PLUS_KEYS = (Qt.Key_Plus, Qt.Key_Equal)
    _MINUS_KEYS = (Qt.Key_Minus, Qt.Key_Underscore)

    def eventFilter(self, obj, e):
        t = e.type()
        if t in (QEvent.ShortcutOverride, QEvent.KeyPress):
            mods = e.modifiers()
            if (mods & Qt.ControlModifier and mods & Qt.ShiftModifier
                    and e.key() in self._PLUS_KEYS + self._MINUS_KEYS
                    and self.isActiveWindow()):
                if t == QEvent.ShortcutOverride:
                    e.accept()          # tell Qt "not a shortcut", so Ctrl++ (zoom) can't claim it
                    return True
                self._page_op("rot", 90 if e.key() in self._PLUS_KEYS else -90)
                return True
        return super().eventFilter(obj, e)

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

    def flatten(self):
        v = self.view()
        if not v:
            return
        choices = ["All pages", "Current page only"]
        pick, ok = QInputDialog.getItem(
            self, "Flatten", "Flatten annotations and form fields into the page.\n"
            "They'll look the same but can no longer be edited or moved.\n"
            "(Undo works until you close the file.)\n\nWhich pages?", choices, 0, False)
        if not ok:
            return
        v.flatten(None if pick == choices[0] else [v.current_page()])
        self.statusBar().showMessage("Flattened", 4000)

    # ---- signing ---------------------------------------------------------------------
    def _cache_sig(self, kind, png):
        self._sig_cache[kind] = png
        for i in range(self.tabs.count()):
            self.tabs.widget(i).set_sig_image(kind, png)

    def setup_signature(self, kind):
        dlg = signatures.SignatureSetup(self, kind)
        if dlg.exec() and dlg.png:
            self._cache_sig(kind, dlg.png)
            self.statusBar().showMessage(f"Your {kind} is saved.", 4000)

    def _on_signed(self):
        v = self.sender()
        if v is None or v.protect_on_save or getattr(v, "_asked_protect", False):
            return
        v._asked_protect = True
        r = QMessageBox.question(
            self, "Protect signed document?",
            "Protect this document from changes when you save it?\n\n"
            "Anyone can still open, read and print it, but PDF editors that honour PDF "
            "permissions (Acrobat, PDF-XChange, this app) won't let it be edited.\n\n"
            "Tip: keep an unsigned copy if you may need to change it later.")
        v.protect_on_save = r == QMessageBox.Yes
        self._update_ui()

    def _sign_field(self, index, xref):
        v = self.sender()
        if "signature" not in self._sig_cache:
            png = signatures.get_image(self, "signature")
            if png is None:
                return
            self._cache_sig("signature", png)
        page = v.doc[index]
        rect = page.load_widget(xref).rect
        v.place_signature(index, "signature", field_rect=rect)

    def _toggle_protect(self):
        v = self.view()
        if v:
            v.protect_on_save = self.a_protect.isChecked()
            v.dirty = True
            self._update_ui()

    def unlock_doc(self):
        v = self.view()
        if not v:
            return
        if not v.read_only:
            QMessageBox.information(self, "Unlock", "This document isn't protected.")
            return
        pw, ok = QInputDialog.getText(self, "Unlock", "Owner password:", QLineEdit.Password)
        if ok and pw:
            if v.unlock(pw):
                self.statusBar().showMessage("Unlocked: you can edit this document now.", 4000)
            else:
                QMessageBox.warning(self, "Unlock", "That password doesn't unlock editing.")
            self._update_ui()

    # ---- export ------------------------------------------------------------------------
    def export_as(self, eid):
        v = self.view()
        if not v:
            return
        _id, label, flt, ext = next(e for e in EXPORTS if e[0] == eid)
        base = os.path.splitext(v.path)[0]
        path, _ = QFileDialog.getSaveFileName(self, "Export", f"{base}.{ext}", flt)
        if not path:
            return
        pages = None
        if v.page_count() > 1:
            pick, ok = QInputDialog.getItem(self, "Export", "Pages:", ["All pages", "Current page"],
                                            0, False)
            if not ok:
                return
            pages = None if pick == "All pages" else [v.current_page()]
        units = None
        if eid == "dxf":
            units, ok = QInputDialog.getItem(
                self, "AutoCAD export", "Drawing units (1 inch on paper = 1 unit if inches):",
                list(export.UNITS), 0, False)
            if not ok:
                return
        data = v.doc.tobytes()
        if eid in ("png", "jpg"):
            base_out = os.path.splitext(path)[0]
            job = lambda: export.to_images(data, base_out, eid, 200, pages)
        elif eid == "dxf":
            job = lambda: export.to_dxf(data, path, pages, units)
        else:
            fn = {"word": export.to_word, "excel": export.to_excel,
                  "ppt": export.to_powerpoint, "txt": export.to_text}[eid]
            job = lambda: fn(data, path, pages)
        dlg = QProgressDialog(f"Exporting to {label.replace('&', '').rstrip('.')}...", None, 0, 0, self)
        dlg.setWindowTitle("Export")
        dlg.setWindowModality(Qt.WindowModal)
        dlg.setMinimumDuration(300)
        pool = ThreadPoolExecutor(max_workers=1)
        fut = pool.submit(job)
        while not fut.done():
            QApplication.processEvents()
            time.sleep(0.03)
        dlg.close()
        pool.shutdown(wait=False)
        try:
            result = fut.result()
        except Exception as ex:
            QMessageBox.critical(self, "Export failed", str(ex))
            return
        msg = "Exported to " + path
        if eid == "excel" and result == 0:
            msg += "\n\nNo tables were detected, so each page's text was exported row by row."
        elif eid in ("png", "jpg"):
            msg = f"Exported {len(result)} image(s) next to {path}"
        elif eid == "dxf":
            msg += (f"\n\n{result['lines']} lines, {result['curves']} curves and "
                    f"{result['text']} text items. Images in the PDF aren't included.")
        elif eid == "ppt":
            msg += "\n\nEach page is a picture on its slide; its text is in the speaker notes."
        QMessageBox.information(self, "Export", msg)

    # ---- measurement ---------------------------------------------------------------
    def _scale_dialog(self, pdf_len=None, page_index=None):
        from .measure_ui import ScaleDialog
        v = self.view()
        if not v:
            return
        page_index = v.current_page() if page_index is None else page_index
        page = v.doc[page_index]
        dlg = ScaleDialog(self, page, pdf_len, v.page_count())
        if dlg.exec() and dlg.result_scale:
            f, unit, label, all_pages = dlg.result_scale
            pages = range(v.page_count()) if all_pages else [page_index]
            v.set_page_scale(list(pages), f, unit, label)
            self.statusBar().showMessage(v.page_scale_text(page_index), 5000)
            self._update_ui()

    def set_scale(self):
        self._scale_dialog()

    def _calibrate(self, index, pdf_len):
        self._scale_dialog(pdf_len, index)

    def measure_summary(self):
        from .measure_ui import SummaryDialog
        v = self.view()
        if v:
            SummaryDialog(self, v.doc).exec()

    # ---- tool chest ------------------------------------------------------------------
    def _clear_chest(self):
        if annotations.OVERRIDE["tool"] is not None and not getattr(self, "_from_chest", False):
            annotations.OVERRIDE.update(tool=None, props=None)
            self._refresh_props()

    def _use_chest_tool(self, tool, props):
        self._from_chest = True
        annotations.OVERRIDE.update(tool=tool, props=props)
        self.set_tool(tool)
        self._from_chest = False
        self._refresh_props()
        self.statusBar().showMessage("Tool chest: next markups use this style. "
                                     "Pick a tool from the toolbar to go back to defaults.", 5000)

    def _add_to_chest(self):
        v = self.view()
        if v is not None and v.selected_model is not None and v.selected_model["kind"] != "field":
            m = v.selected_model
            tool = tool_for(m)
            props = m["props"]
            name = (props.get("label") or annotations.LABELS.get(tool, tool)).replace("image:", "")
        elif self.tool in annotations.DEFAULTS:
            tool, props = self.tool, annotations.tool_props(self.tool)
            name = annotations.LABELS.get(tool, tool)
        else:
            QMessageBox.information(self, "Tool chest", "Select a markup (or pick a markup "
                                    "tool) first, then click Add.")
            return
        if tool is None:
            return
        self.chest.add(tool, props, name)

    # ---- document tools ------------------------------------------------------------
    def _show_bookmarks(self):
        self.dock.show()
        self.left_tabs.setCurrentWidget(self.bookmarks)

    def _refresh_bookmarks(self):
        v = self.view()
        self.bookmarks.set_toc(v.get_toc() if v else [])

    def header_footer(self):
        from .page_tools import HeaderFooterDialog
        v = self.view()
        if v:
            dlg = HeaderFooterDialog(self, v.page_count())
            if dlg.exec() and dlg.spec:
                v.add_header_footer(dlg.spec)

    def watermark(self):
        from .page_tools import WatermarkDialog
        v = self.view()
        if v:
            dlg = WatermarkDialog(self, v.page_count())
            if dlg.exec() and dlg.spec:
                v.add_watermark(dlg.spec)

    def compress(self):
        from . import page_tools
        v = self.view()
        if not v:
            return
        preset, ok = QInputDialog.getItem(self, "Compress", "Image quality:",
                                          list(page_tools.COMPRESS), 1, False)
        if not ok:
            return
        base = os.path.splitext(v.path)[0]
        path, _ = QFileDialog.getSaveFileName(self, "Save smaller copy", base + "_small.pdf", PDF_FILTER)
        if not path:
            return
        try:
            before, after = page_tools.compress(v.doc.tobytes(), path, preset)
        except Exception as ex:
            QMessageBox.critical(self, "Compress failed", str(ex))
            return
        QMessageBox.information(self, "Compress",
                                f"Saved {path}\n\n{before / 1e6:.2f} MB \u2192 {after / 1e6:.2f} MB "
                                f"({100 - after * 100 / max(1, before):.0f}% smaller)")

    def search_redact(self):
        v = self.view()
        if not v:
            return
        text, ok = QInputDialog.getText(self, "Search & redact",
                                        "Mark every occurrence of this text for redaction:")
        if ok and text.strip():
            n = v.search_redact(text.strip())
            QMessageBox.information(self, "Search & redact",
                                    f"Marked {n} occurrence(s). Review them, then use Document > "
                                    "Redaction > Apply redactions." if n else "No matches found.")

    def apply_redactions(self):
        v = self.view()
        if not v:
            return
        n = v.pending_redactions()
        if not n:
            QMessageBox.information(self, "Redaction", "Nothing is marked for redaction yet. "
                                    "Use the Redact tool or Search & redact first.")
            return
        box = QMessageBox(QMessageBox.Warning, "Apply redactions",
                          f"Permanently remove everything under {n} redaction mark(s)? Text, "
                          "images and drawings there are deleted, not just covered.\n\n"
                          "Undo works until you close the file.", parent=self)
        scrub = QCheckBox("Also remove hidden information (metadata, attachments, scripts)")
        box.setCheckBox(scrub)
        box.setStandardButtons(QMessageBox.Apply | QMessageBox.Cancel)
        if box.exec() == QMessageBox.Apply:
            v.apply_redactions(scrub.isChecked())
            self.statusBar().showMessage(f"Applied {n} redaction(s). Save to make it permanent.", 6000)

    # ---- digital signatures ----------------------------------------------------------
    def digital_sign(self):
        from . import digisign
        v = self.view()
        if not v:
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("Digitally sign with a certificate")
        lay = QVBoxLayout(dlg)
        info = QLabel("A digital signature proves who signed and that the document hasn't "
                      "changed since. Tip: place your visible signature first (Sign tool), "
                      "then sign digitally. The signed copy is saved as a new file.")
        info.setWordWrap(True)
        lay.addWidget(info)
        form = QFormLayout()
        mine = QRadioButton("My personal certificate" + ("" if os.path.exists(digisign.my_cert_path())
                                                          else " (created now)"))
        other = QRadioButton("Certificate file from a certificate authority / my company (.pfx, .p12)")
        mine.setChecked(True)
        cert_path = QLineEdit()
        browse = QPushButton("Browse...")
        browse.clicked.connect(lambda: cert_path.setText(QFileDialog.getOpenFileName(
            dlg, "Certificate", "", "Certificates (*.pfx *.p12)")[0] or cert_path.text()))
        row = QHBoxLayout()
        row.addWidget(cert_path)
        row.addWidget(browse)
        password = QLineEdit()
        password.setEchoMode(QLineEdit.Password)
        reason = QComboBox()
        reason.setEditable(True)
        reason.addItems(["I approve this document", "I am the author of this document",
                         "I have reviewed this document", "I agree to the terms"])
        location = QLineEdit()
        lock = QCheckBox("Lock the document: no further changes allowed (certify)")
        form.addRow(mine)
        form.addRow(other)
        form.addRow("Certificate file", row)
        form.addRow("Certificate password", password)
        form.addRow("Reason", reason)
        form.addRow("Location", location)
        form.addRow(lock)
        lay.addLayout(form)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)
        if not dlg.exec():
            return
        try:
            if mine.isChecked():
                path = digisign.my_cert_path()
                if not os.path.exists(path):
                    name, ok = QInputDialog.getText(self, "Create your certificate",
                                                    "Your full name (shown as the signer):",
                                                    text=annotations.author())
                    if not ok or not name.strip():
                        return
                    email, _ok = QInputDialog.getText(self, "Create your certificate",
                                                      "Email (optional):")
                    if not password.text():
                        QMessageBox.warning(self, "Certificate", "Choose a certificate password "
                                            "in the signing dialog to protect your certificate.")
                        return
                    digisign.create_certificate(name.strip(), email.strip(), "", password.text())
            else:
                path = cert_path.text()
                if not os.path.isfile(path):
                    QMessageBox.warning(self, "Certificate", "Choose a certificate file.")
                    return
            signer = digisign.load_signer(path, password.text())
        except Exception as ex:
            QMessageBox.warning(self, "Certificate", f"Couldn't use that certificate: {ex}")
            return
        base = os.path.splitext(v.path)[0]
        out, _ = QFileDialog.getSaveFileName(self, "Save signed copy as", base + "_signed.pdf", PDF_FILTER)
        if not out:
            return
        try:
            digisign.sign(v.doc.tobytes(), out, signer, reason.currentText(), location.text(),
                          lock.isChecked())
        except Exception as ex:
            QMessageBox.critical(self, "Signing failed", str(ex))
            return
        self.open_file(out)

    def signature_details(self):
        v = self.view()
        if not v:
            return
        res = getattr(v, "sig_results", [])
        if not res:
            QMessageBox.information(self, "Digital signatures", "This document has no digital "
                                    "(certificate) signatures.")
            return
        lines = []
        for r in res:
            lines.append(r["summary"])
            if r.get("reason"):
                lines.append(f"   Reason: {r['reason']}")
            if r.get("email"):
                lines.append(f"   Email: {r['email']}")
            if r.get("fingerprint"):
                lines.append(f"   Certificate fingerprint: {r['fingerprint'][:32]}...")
        box = QMessageBox(QMessageBox.Information, "Digital signatures", "\n".join(lines), parent=self)
        untrusted = [r for r in res if r.get("fingerprint") and not r.get("trusted")]
        trust_btn = box.addButton("Trust these signers on this computer", QMessageBox.ActionRole) \
            if untrusted else None
        box.addButton(QMessageBox.Close)
        box.exec()
        if trust_btn is not None and box.clickedButton() is trust_btn:
            from . import digisign
            for r in untrusted:
                digisign.trust(r["fingerprint"])
            v.check_digital_signatures()

    # ---- compare --------------------------------------------------------------------
    def compare_documents(self):
        from . import compare
        v = self.view()
        if not v:
            return
        path, _ = QFileDialog.getOpenFileName(self, "Compare with which earlier revision?",
                                              os.path.dirname(v.path), PDF_FILTER)
        if not path:
            return
        try:
            with open(path, "rb") as f:
                old = f.read()
        except OSError as ex:
            QMessageBox.critical(self, "Compare", str(ex))
            return
        new = v.doc.tobytes()
        old_name, new_name = os.path.basename(path), os.path.basename(v.path)
        dlg = QProgressDialog("Comparing pages...", None, 0, 0, self)
        dlg.setWindowTitle("Compare")
        dlg.setWindowModality(Qt.WindowModal)
        dlg.setMinimumDuration(300)
        pool = ThreadPoolExecutor(max_workers=1)
        fut = pool.submit(compare.compare, old, new, 110, None, old_name, new_name)
        while not fut.done():
            QApplication.processEvents()
            time.sleep(0.03)
        dlg.close()
        pool.shutdown(wait=False)
        try:
            data, counts = fut.result()
        except Exception as ex:
            QMessageBox.critical(self, "Compare failed", str(ex))
            return
        import tempfile
        stem = f"Compare - {os.path.splitext(old_name)[0]} vs {os.path.splitext(new_name)[0]}.pdf"
        out = os.path.join(tempfile.mkdtemp(prefix="kzcompare"), stem)
        with open(out, "wb") as f:
            f.write(data)
        self.open_file(out)
        self.markups_dock.show()
        QMessageBox.information(self, "Compare", f"Found {sum(counts)} changed area(s) on "
                                f"{sum(1 for c in counts if c)} of {len(counts)} page(s).\n\n"
                                "Red = only in the earlier revision, blue = only in this one. "
                                "Each change is clouded and listed in the Markups list. "
                                "Use Save As to keep the comparison.")

    # ---- appearance -------------------------------------------------------------------
    TOOLBAR_ICON_KEYS = {"a_open": "open", "a_save": "save", "a_print": "print", "a_undo": "undo",
                         "a_redo": "redo", "a_zoom_in": "zoom_in", "a_zoom_out": "zoom_out",
                         "a_fit_width": "fit_width", "a_fit_page": "fit_page", "a_ocr": "ocr",
                         "a_rot_l": "rot_l", "a_rot_r": "rot_r"}

    def _apply_icons(self):
        for attr, key in self.TOOLBAR_ICON_KEYS.items():
            getattr(self, attr).setIcon(theme.icon(key))
        for tid, a in self.tool_actions.items():
            a.setIcon(theme.icon(tid))
        self.forms_btn.setIcon(theme.icon("forms"))
        labels = self.a_labels.isChecked()
        style = Qt.ToolButtonTextUnderIcon if labels else Qt.ToolButtonIconOnly
        for tb in (self.main_tb, self.tools_tb):
            tb.setToolButtonStyle(style)
            tb.setIconSize(QSize(20, 20))
        for b in (self.shapes_btn, self.measure_btn, self.forms_btn):
            b.setToolButtonStyle(style)
        # tooltips show the shortcut so icon-only buttons stay discoverable
        for a in list(self.tool_actions.values()) + [getattr(self, k) for k in self.TOOLBAR_ICON_KEYS]:
            sc = a.shortcut().toString()
            name = a.text().split("\t")[0].replace("&", "")
            a.setToolTip(f"{name} ({sc})" if sc and sc not in (a.toolTip() or "") else
                         (a.toolTip() or name))

    def _toggle_labels(self):
        self.settings.setValue("toolbar_labels", "true" if self.a_labels.isChecked() else "false")
        self._apply_icons()

    def set_theme(self, mode):
        self.settings.setValue("theme", mode)
        app = QApplication.instance()
        theme.apply(app, mode)
        # widgets with style sheets keep their old colours until re-polished
        for wdg in app.allWidgets():
            wdg.style().unpolish(wdg)
            wdg.style().polish(wdg)
            wdg.update()
        self._apply_icons()

    # ---- remembered page & zoom per file ------------------------------------------------
    def _file_states(self):
        import json
        try:
            return json.loads(self.settings.value("file_states", "{}") or "{}")
        except (ValueError, TypeError):
            return {}

    def _remember_state(self, v):
        import json
        if v is None or not hasattr(v, "pages") or not v.pages:
            return
        states = self._file_states()
        states[os.path.normcase(v.path)] = {"page": v.current_page(), "zoom": round(v.zoom, 4)}
        if len(states) > 200:                      # keep the 200 most recent
            states = dict(list(states.items())[-200:])
        self.settings.setValue("file_states", json.dumps(states))

    # ---- split view -----------------------------------------------------------------------
    def _build_split(self):
        self.split_dock = QDockWidget("Second view")
        self.split_dock.setObjectName("splitview")
        self.split_dock.setFeatures(QDockWidget.DockWidgetClosable)
        self.split_holder = QWidget()
        QVBoxLayout(self.split_holder).setContentsMargins(0, 0, 0, 0)
        self.split_dock.setWidget(self.split_holder)
        self.addDockWidget(Qt.BottomDockWidgetArea, self.split_dock)
        self.split_dock.hide()
        self.split_dock.visibilityChanged.connect(self._split_visible)
        self._split_view = None
        self.tabs.currentChanged.connect(lambda _: self.split_dock.isVisible() and self._attach_split())

    def _toggle_split(self):
        self.split_dock.setVisible(self.a_split.isChecked())

    def _split_visible(self, vis):
        self.a_split.setChecked(vis)
        if vis:
            self._attach_split()
            self.resizeDocks([self.split_dock], [int(self.height() * 0.42)], Qt.Vertical)
        elif self._split_view is not None:
            self._split_view.deleteLater()
            self._split_view = None

    def _attach_split(self):
        """Show a second, independently scrolled view of the current document."""
        if self._split_view is not None:
            self._split_view.deleteLater()
            self._split_view = None
        v = self.view()
        if v is None:
            return
        sv = DocumentView.mirror(v)
        self.split_holder.layout().addWidget(sv)
        self._split_view = sv
        self.split_dock.setWindowTitle(f"Second view: {os.path.basename(v.path)} "
                                       "(scroll independently; edit in the main view)")

    # ---- keyboard shortcuts --------------------------------------------------------------
    def _shortcut_actions(self):
        """{stable id: QAction} for every action that can have a shortcut."""
        out = {}
        for a in self.findChildren(QAction):
            if a.parent() is not self:        # skip panels' own small menus
                continue
            name = a.text().split("\t")[0].replace("&", "").strip().rstrip(".")
            if name and not a.menu() and name not in out:
                out[name] = a
        return out

    def _apply_saved_shortcuts(self):
        import json
        try:
            saved = json.loads(self.settings.value("shortcuts", "{}") or "{}")
        except (ValueError, TypeError):
            saved = {}
        acts = self._shortcut_actions()
        for name, seq in saved.items():
            if name in acts:
                acts[name].setShortcut(QKeySequence(seq))

    def edit_shortcuts(self):
        import json
        from PySide6.QtWidgets import QTableWidget, QTableWidgetItem, QKeySequenceEdit, QHeaderView
        acts = self._shortcut_actions()
        dlg = QDialog(self)
        dlg.setWindowTitle("Keyboard shortcuts")
        dlg.resize(560, 600)
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel("Click a shortcut and press the new key combination. "
                             "Clear it with Backspace. Ctrl+Shift+Plus/Minus always rotate."))
        filt = QLineEdit()
        filt.setPlaceholderText("Filter")
        lay.addWidget(filt)
        names = sorted(acts)
        table = QTableWidget(len(names), 2)
        table.setHorizontalHeaderLabels(["Command", "Shortcut"])
        table.verticalHeader().hide()
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        editors = {}
        for r, name in enumerate(names):
            item = QTableWidgetItem(name)
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            table.setItem(r, 0, item)
            ed = QKeySequenceEdit(acts[name].shortcut())
            table.setCellWidget(r, 1, ed)
            editors[name] = ed
        filt.textChanged.connect(lambda t: [table.setRowHidden(r, t.lower() not in n.lower())
                                            for r, n in enumerate(names)])
        lay.addWidget(table)
        row = QHBoxLayout()
        reset = QPushButton("Reset all to defaults")
        row.addWidget(reset)
        row.addStretch(1)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        row.addWidget(btns)
        lay.addLayout(row)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)

        def do_reset():
            self.settings.remove("shortcuts")
            QMessageBox.information(dlg, "Keyboard shortcuts",
                                    "Default shortcuts come back the next time you start the app.")
            dlg.reject()
        reset.clicked.connect(do_reset)
        if not dlg.exec():
            return
        seen, clashes, saved = {}, [], {}
        for name, ed in editors.items():
            seq = ed.keySequence().toString()
            if seq:
                if seq in seen:
                    clashes.append(f"{seq}: {seen[seq]} / {name}")
                seen[seq] = name
            if seq != acts[name].shortcut().toString():
                acts[name].setShortcut(QKeySequence(seq))
            saved[name] = seq
        self.settings.setValue("shortcuts", json.dumps(saved))
        self._apply_icons()
        if clashes:
            QMessageBox.warning(self, "Keyboard shortcuts",
                                "These shortcuts are used twice:\n" + "\n".join(clashes))

    def _toggle_markups(self):
        self.markups_dock.setVisible(not self.markups_dock.isVisible())

    def _markups_visible(self, vis):
        self.a_markups.setChecked(vis)
        if vis:
            self._refresh_markups()

    def _refresh_markups(self):
        if self.markups_dock.isVisible():
            v = self.view()
            self.markups.refresh(v.doc if v else None)

    def _set_author(self):
        name, ok = QInputDialog.getText(self, "Author name",
                                        "Name recorded on your markups, stamps and comments:",
                                        text=annotations.author())
        if ok:
            annotations.set_author(name.strip())

    def _toggle_sidebar(self):
        self.dock.setVisible(not self.dock.isVisible())

    def about(self):
        QMessageBox.about(self, "About " + APP_NAME,
                          f"<b>{APP_NAME}</b> version {__version__}<br>A free, fast PDF reader and editor.<br><br>"
                          f"Built on PyMuPDF {pymupdf.VersionBind} (MuPDF) and Qt (PySide6).")

    # ---- signals from views --------------------------------------------------
    def _on_tab_changed(self, _):
        self._rebuild_thumbs()
        self._refresh_bookmarks()
        self._markups_timer.start()
        self._refresh_props()
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
            self._refresh_bookmarks()
        self._update_ui()

    def _set_pages_locked(self, locked):
        self.thumbs.setDragDropMode(QAbstractItemView.NoDragDrop if locked
                                    else QAbstractItemView.InternalMove)
        self.lock_btn.setText("\U0001F512 Page order locked (click to unlock)" if locked
                              else "\U0001F513 Unlocked: drag pages to reorder")
        self.thumbs.setToolTip("Unlock (button above) to drag pages" if locked
                               else "Drag pages to reorder them")
        self.settings.setValue("pages_locked", "true" if locked else "false")

    def _on_thumb_moved(self, _parent, start, _end, _dest_parent, dest_row):
        """Thumbnail dragged: apply the same move to the PDF (after Qt finishes the drop)."""
        v = self.view()
        if v is not None:
            QTimer.singleShot(0, lambda: v.move_page_to(start, dest_row))

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
