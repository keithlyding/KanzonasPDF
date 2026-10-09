"""Main application window: tabs, toolbars, menus, thumbnails sidebar."""

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor

import pymupdf
from PySide6.QtCore import Qt, QSize, QTimer, QEvent
from PySide6.QtGui import (QAction, QActionGroup, QKeySequence, QIcon, QPixmap, QImage,
                           QPainter)
from PySide6.QtWidgets import (QMainWindow, QTabWidget, QToolBar, QFileDialog, QMessageBox,
                               QLineEdit, QSpinBox, QLabel, QComboBox, QListWidget,
                               QListWidgetItem, QDockWidget, QAbstractItemView, QToolButton,
                               QVBoxLayout, QHBoxLayout, QMenu, QProgressDialog,
                               QInputDialog, QWidget, QSizePolicy, QApplication, QScrollArea,
                               QDialog, QFormLayout, QRadioButton, QDialogButtonBox, QCheckBox,
                               QPushButton, QSlider)
from PySide6.QtPrintSupport import QPrinter, QPrintDialog

from . import __version__, annotations, export, signatures, theme
from .document_view import DocumentView
from .properties import PropertiesPanel
from .markups_panel import MarkupsPanel
from .tool_chest import ToolChestPanel, tool_for

APP_NAME = "KanzonasPDF"
APP_TITLE = f"KanzonasPDF v{__version__}"


def _title_base():
    """'KanzonasPDF v0.48', plus ' (portable)' when run from the portable folder."""
    from . import paths
    return APP_TITLE + (" (portable)" if paths.is_portable() else "")
PDF_FILTER = "PDF files (*.pdf);;All files (*)"


def parse_page_list(text, count):
    """'1-3, 7' -> [0, 1, 2, 6] (0-based, in order, no repeats); [] if invalid."""
    out = []
    try:
        for part in text.replace(" ", "").split(","):
            if not part:
                continue
            a, _, b = part.partition("-")
            first, last = int(a), int(b or a)
            if not 1 <= first <= last <= count:
                return []
            out += [i - 1 for i in range(first, last + 1) if i - 1 not in out]
    except ValueError:
        return []
    return out
TOOLS = [  # (id, label, shortcut, tooltip)
    ("select", "Select", "V", "Select: drag across text to select it (Ctrl+C copies); click an annotation "
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
    ("image", "Image", "", "Image: drag a box (or click) and pick a picture; it's embedded in the PDF"),
    ("attach", "Attach file", "", "Attach file: click where its icon goes and pick any file "
                                  "(e.g. a video); it's embedded in the PDF. Double-click to open"),
    ("eraser", "Eraser", "X", "Delete the annotation you click (X)"),
    ("signature", "Sign", "G", "Place your saved signature: click where it goes, or drag a box "
                               "to size it (G)"),
    ("initials", "Initials", "I", "Place your saved initials: click where they go, or drag a box "
                                  "to size them (I)"),
    ("date", "Date", "Ctrl+;", "Place today's date: click where it goes (Ctrl+;)"),
]
FORM_TOOLS = [  # form design tools: drag a box (or click) to add a field
    ("f_text", "Text field", "Text field: drag a box"),
    ("f_check", "Checkbox", "Checkbox: click or drag"),
    ("f_radio", "Option button", "Option (radio) button: click; same group name = pick one"),
    ("f_combo", "Dropdown", "Dropdown list: drag a box, then enter the choices"),
    ("f_sign", "Signature field", "Signature field: others click it to sign"),
    ("f_initials", "Initials field", "Initials field: others click it to put their initials"),
]
MEASURE_TOOLS = [
    ("m_length", "Length", "Shift+M", "Measure length: drag from point to point (Shift+M)"),
    ("m_poly", "Polylength", "", "Measure along a path: click points, double-click or Enter to finish"),
    ("m_area", "Area", "Shift+A", "Measure area and perimeter: click corners, double-click or Enter (Shift+A)"),
    ("m_count", "Count", "Shift+C", "Count: click each item; set the group name in Properties (Shift+C)"),
    ("m_calibrate", "Calibrate Tape Measure", "", "Calibrate Tape Measure: drag along a known dimension, then type its real length"),
]
EXTRA_TOOLS = [  # tools reached from menus, not the toolbar
    ("erasecontent", "Erase &content", "Shift+E",
     "Erase content: drag a box; the page's own text, images and lines inside it are deleted "
     "(lines crossing the edge are cut there). Shift+E"),
    ("editobjects", "Edit &objects", "Shift+O",
     "Edit objects: click a picture or shape that's part of the page (Ctrl+click or drag a box "
     "for several); drag to move, drag a handle to resize, Delete deletes, right-click to "
     "rotate. Shift+O"),
    ("capture", "Ca&pture area", "Shift+P",
     "Capture: drag a box to copy that area; Ctrl+V pastes it here as sharp vector content, "
     "or as a picture into Word or email. Shift+P"),
    ("redact", "&Redact (mark text or area)", "Shift+R",
     "Redact: drag across text, or drag a box over any area; then Apply redactions"),
    ("placeholder", "Add signature &placeholder", "",
     "Placeholder: drag a box where a signature or initials go (choose which in Properties); "
     "then Apply all signature placeholders"),
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
# Toolbar tooltips: what each button does (the shortcut is added automatically)
BUTTON_TIPS = {
    "a_open": "Open a PDF", "a_save": "Save the document", "a_print": "Print",
    "a_undo": "Undo the last change", "a_redo": "Redo what you undid",
    "a_zoom_in": "Zoom in", "a_zoom_out": "Zoom out",
    "a_fit_width": "Zoom so the page fills the window's width",
    "a_fit_page": "Zoom so the whole page fits in the window",
    "a_ocr": "Recognize text (OCR): make scanned pages searchable and selectable",
    "a_rot_l": "Rotate the page counterclockwise", "a_rot_r": "Rotate the page clockwise",
    "a_grid": "Show grid: a grid over the page (spacing in View > Grid settings)",
    "a_snap_grid": "Snap to grid: points jump to the nearest grid intersection (Alt = no snap)",
    "a_snap_page": "Snap to page: points jump to the page's corners, edge middles, center "
                   "and edges (Alt = no snap)",
    "a_snap_objects": "Snap to objects: points jump to markup corners, ends and centers and "
                      "to the drawing's line ends and midpoints (Alt = no snap)",
    "tool_highlight": "Highlight: drag across text",
    "tool_underline": "Underline: drag across text",
    "tool_strikeout": "Strike out: drag across text",
    "tool_rect": "Rectangle: drag a box (Shift = square)",
    "tool_ellipse": "Ellipse: drag a box (Shift = circle)",
    "tool_cloud": "Revision cloud: drag a box (Shift = square)",
    "tool_line": "Line: drag (Shift = 45\u00b0 steps)",
    "tool_arrow": "Arrow: drag from tail to head (Shift = 45\u00b0 steps)",
    "tool_eraser": "Eraser: click a markup to delete it, or drag a box to delete everything inside",
}
ARRANGE_TIPS = {
    "al_left": "Align left edges", "al_hcenter": "Align centers (horizontally)",
    "al_right": "Align right edges", "al_top": "Align top edges",
    "al_vmiddle": "Align middles (vertically)", "al_bottom": "Align bottom edges",
    "dist_h": "Distribute horizontally: equal gaps (3 or more markups)",
    "dist_v": "Distribute vertically: equal gaps (3 or more markups)",
    "z_front": "Bring to front: on top of all other markups",
    "z_forward": "Bring forward one step", "z_backward": "Send backward one step",
    "z_back": "Send to back: behind all other markups",
}
ZOOM_PRESETS = ["50%", "75%", "100%", "125%", "150%", "200%", "300%", "400%"]


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        from . import paths
        self.settings = paths.settings()
        self.setWindowTitle(_title_base())
        self.resize(1300, 900)
        self.setAcceptDrops(True)
        # start with the Hand (scroll by dragging, like most viewers) or the Select tool
        self.tool = "select" if self.settings.value("start_tool", "hand") == "select" else "hand"
        self._last_basic_tool = self.tool
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
        self._build_panel_strip()
        self._apply_icons()
        self._apply_saved_shortcuts()
        self._update_ui()
        self._refresh_props()
        QApplication.instance().installEventFilter(self)

        geo = self.settings.value("geometry")
        if geo is not None:
            self.restoreGeometry(geo)

    # ---- construction -----------------------------------------------------
    def _build_panel_strip(self):
        """PDF-XChange style icon strip on the left edge: click an icon to open that panel,
        click it again to fold the panel away (the strip stays)."""
        from . import theme
        ps = self.panel_strip = QToolBar("Panels")
        ps.setObjectName("panel_strip")
        ps.setMovable(False)
        ps.setIconSize(QSize(18, 18))
        ps.setOrientation(Qt.Vertical)
        ps.toggleViewAction().setVisible(False)
        self.addToolBar(Qt.LeftToolBarArea, ps)
        self.strip_actions = []
        self._strip_icons = []          # (action, icon name), re-tinted when the theme changes
        for i, (label, icon) in enumerate((("Pages", "file-multiple-outline"),
                                           ("Bookmarks", "bookmark-outline"),
                                           ("Layers", "layers-outline"),
                                           ("Objects", "shape-outline"))):
            a = QAction(theme.icon_named(icon), label, self, checkable=True)
            self._strip_icons.append((a, icon))
            a.setToolTip(f"{label} panel (click again to fold it away)")
            a.triggered.connect(lambda _=False, k=i: self._strip_clicked(k))
            ps.addAction(a)
            self.strip_actions.append(a)
        ps.addSeparator()
        for a, icon in ((self.a_markups, "comment-text-multiple-outline"),
                        (self.a_attachments, "paperclip")):
            if a.icon().isNull():
                a.setIcon(theme.icon_named(icon))
                self._strip_icons.append((a, icon))
            ps.addAction(a)
        self.a_panel_strip = QAction("Show panel &strip (left edge)", self, checkable=True)
        self.a_panel_strip.setToolTip("Icons on the left edge that open and fold the Pages, "
                                      "Bookmarks, Layers and Objects panels")
        self.a_panel_strip.setChecked(self.settings.value("panel_strip", "true") != "false")
        self.a_panel_strip.toggled.connect(self._toggle_panel_strip)
        self.view_menu.addAction(self.a_panel_strip)
        self.left_tabs.currentChanged.connect(lambda _i: self._sync_strip())
        self.dock.visibilityChanged.connect(lambda _v: self._sync_strip())
        self._toggle_panel_strip(self.a_panel_strip.isChecked())

    def _strip_clicked(self, k):
        if self.dock.isVisible() and self.left_tabs.currentIndex() == k:
            self.dock.hide()                    # second click folds the panel away
        else:
            self.left_tabs.setCurrentIndex(k)
            self.dock.show()
        self._sync_strip()

    def _sync_strip(self):
        for i, a in enumerate(getattr(self, "strip_actions", [])):
            a.setChecked(self.dock.isVisible() and self.left_tabs.currentIndex() == i)

    def _toggle_panel_strip(self, on):
        self.settings.setValue("panel_strip", "true" if on else "false")
        self.panel_strip.setVisible(on)
        self.left_tabs.tabBar().setVisible(not on)     # the strip replaces the tabs
        self._sync_strip()

    def _group_widget(self, items):
        """A row of actions and widgets that can live in a toolbar or the status bar."""
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(1)
        for it in items:
            if isinstance(it, QAction):
                b = QToolButton()
                b.setDefaultAction(it)
                b.setAutoRaise(True)
                b.setIconSize(QSize(16, 16))
                it = b
            h.addWidget(it)
        w.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        return w

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
        self.a_prefs = self._act("Pre&ferences...", self.preferences, "Ctrl+K",
                                 tip="All the remembered options in one place (Ctrl+K)")
        self.a_undo = self._act("&Undo", lambda: v() and v().undo(), QKeySequence.Undo)
        self.a_redo = self._act("&Redo", lambda: v() and v().redo(), QKeySequence.Redo)
        self.a_find = self._act("&Find", self._focus_search, QKeySequence.Find)
        # clipboard: text, markups, or pages (when the page list has the focus)
        self.a_copy = self._act("&Copy", lambda: self._clipboard("copy"), QKeySequence.Copy,
                                tip="Copy the selected text, markups, or pages (in the page list)")
        self.a_cut = self._act("Cu&t", lambda: self._clipboard("cut"), QKeySequence.Cut,
                               tip="Cut the selected text (removes it from the page), markups or pages")
        self.a_paste = self._act("&Paste", lambda: self._clipboard("paste"), QKeySequence.Paste,
                                 tip="Paste markups, pages, a picture, or text (as a text box) "
                                     "where the mouse is")
        self.a_select_all = self._act("Select &all text", lambda: self._clipboard("all"),
                                      QKeySequence.SelectAll,
                                      tip="Select all the text on the current page (or all pages "
                                          "in the page list)")
        self.a_duplicate = self._act("&Duplicate", lambda: self._clipboard("dup"), "Ctrl+D",
                                     tip="Duplicate the selected markups, or the selected pages "
                                         "when the page list has the focus")
        self.a_dup_pages = self._act("D&uplicate pages", lambda: self._page_clip("dup"),
                                     tip="Duplicate the selected pages (page list must be unlocked)")
        self.a_copy_pages = self._act("Copy pa&ges", lambda: self._page_clip("copy"))
        self.a_cut_pages = self._act("Cut pages", lambda: self._page_clip("cut"))
        self.a_paste_pages = self._act("Paste pages after selected", lambda: self._page_clip("paste"))
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
        self.a_combine = self._act("Co&mbine files...", self.combine_files,
                                   tip="Combine several PDFs, in the order you choose, into one "
                                       "new PDF")
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
        self.a_security = self._act("Security &properties (passwords && permissions)...",
                                    self.security_properties,
                                    tip="Require a password to open, and/or restrict printing, "
                                        "editing and copying (AES-256)")
        self.a_remove_security = self._act("&Remove security", self.remove_security)
        self.a_sanitize = self._act("Sa&nitize document...", self.sanitize_document,
                                    tip="Remove hidden data: document information, scripts, "
                                        "attached files, hidden text...")
        self.a_clear_sigs = self._act("&Clear all digital signatures...", self.clear_signatures)
        self.a_timestamp = self._act("&Timestamp document...", self.timestamp_document,
                                     tip="Add a trusted timestamp from a time server: proves the "
                                         "file existed, unchanged, at that time")
        self.a_multi_sign = self._act("&Multi-place signature or initials...", self.multi_place)
        self.a_apply_placeholders = self._act("&Apply all signature placeholders",
                                              self.apply_placeholders)
        self.a_apply_sel_redact = self._act("Apply &selected redactions",
                                            lambda: self._apply_selected_redactions())
        # review
        self.a_next_markup = self._act("&Next comment", lambda: v() and v().goto_markup(1),
                                       "Alt+Down", tip="Go to and select the next comment or markup")
        self.a_prev_markup = self._act("&Previous comment", lambda: v() and v().goto_markup(-1),
                                       "Alt+Up", tip="Go to and select the previous comment or markup")
        self.a_show_markups = self._act("&Show markups", self._toggle_show_markups,
                                        tip="Hide every comment and markup to see the page as if "
                                            "unmarked (nothing is deleted)")
        self.a_show_markups.setCheckable(True)
        self.a_show_markups.setChecked(True)
        self.a_delete_markups = self._act("&Delete comments...", self.delete_comments)
        self.a_flatten_markups = self._act("&Flatten comments...", self.flatten_comments,
                                           tip="Make comments and markups part of the page; "
                                               "form fields stay fillable")
        self.a_hl_fields = self._act("&Highlight form fields", self._toggle_hl_fields,
                                     tip="Shade fillable form fields so they're easy to find "
                                         "(on screen only)")
        self.a_hl_fields.setCheckable(True)
        self.a_hl_fields.setChecked(self.settings.value("highlight_fields", "true") != "false")
        DocumentView.highlight_fields = self.a_hl_fields.isChecked()
        self.a_next_field = self._act("&Next form field\tTab",
                                      lambda: self.view() and self.view().next_field(),
                                      tip="Go to the next form field (Tab; Space or Enter fills it)")
        self.a_prev_field = self._act("&Previous form field\tShift+Tab",
                                      lambda: self.view() and self.view().next_field(back=True),
                                      tip="Go to the previous form field (Shift+Tab)")
        self.a_unlock = self._act("&Unlock with password...", self.unlock_doc)
        self.export_actions = []
        for eid, label, _flt, _ext in EXPORTS:
            a = self._act(label, lambda _=False, e=eid: self.export_as(e))
            self.export_actions.append(a)
        self.a_chest = self._act("Tool &chest", self._toggle_chest, "F8")
        self.a_chest.setCheckable(True)
        self.a_compare = self._act("&Compare documents...", self.compare_documents,
                                   tip="Compare this document with another revision")
        self.a_header = self._act("&Header && footer, page numbers, Bates...", self.header_footer)
        self.a_watermark = self._act("&Watermark...", self.watermark)
        self.a_background = self._act("Bac&kground...", self.background,
                                      tip="Put a color, gradient or picture behind the page "
                                          "content, on this page or the whole document")
        self.a_remove_bg = self._act("Remove back&ground...", self.remove_background)
        self.a_remove_wm = self._act("Remove water&marks...", self.remove_watermarks,
                                     tip="Remove watermarks added by KanzonasPDF, Adobe Acrobat, "
                                         "PDF-XChange and other apps that mark them as watermarks")
        self.a_compress = self._act("&Compress (save a smaller copy)...", self.compress)
        self.a_attachments = self._act("A&ttachments...", self.show_attachments,
                                       tip="Files embedded in this PDF: open, save or delete them")
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
        self.a_cad_mouse = self._act("CAD-style &mouse (wheel zooms, hold wheel to pan)",
                                     self._toggle_cad_mouse, "F11",
                                     tip="Like AutoCAD: the scroll wheel zooms at the cursor; "
                                         "hold the wheel down and drag to move the sheet (F11)")
        self.a_cad_mouse.setCheckable(True)
        self.a_cad_mouse.setChecked(self.settings.value("cad_mouse", "false") == "true")
        DocumentView.cad_mouse = self.a_cad_mouse.isChecked()
        self.a_page_wheel = self._act("Scroll &one page per wheel step",
                                      self._toggle_page_wheel,
                                      tip="When the whole page fits in the window, each step "
                                          "of the scroll wheel moves to the next or previous "
                                          "page")
        self.a_page_wheel.setCheckable(True)
        self.a_page_wheel.setChecked(self.settings.value("page_wheel", "true") == "true")
        DocumentView.page_wheel = self.a_page_wheel.isChecked()
        from . import autosave, measure
        measure.configure(self.settings)
        try:
            minutes = int(self.settings.value("autosave_minutes", 5))
        except (TypeError, ValueError):
            minutes = 5
        self.autosave = autosave.Autosaver(self, minutes)
        DocumentView.open_view = self.settings.value("open_view", "width")
        for kind in ("signature", "initials"):
            try:
                w = float(self.settings.value("sig_width_" + kind, 0) or 0)
            except (TypeError, ValueError):
                w = 0
            if 14 <= w <= 600:
                DocumentView.SIG_WIDTH[kind] = w
        DocumentView.reopen_page = self.settings.value("reopen_page", "true") != "false"
        # grid and snapping (shared by all open documents, remembered)
        self.a_grid = self._act("Show &grid", self._apply_grid_settings,
                                tip="Show a grid over the page (spacing in Grid settings)")
        self.a_snap_grid = self._act("Snap to g&rid", self._apply_grid_settings,
                                     tip="Points you draw or drag jump to the nearest grid "
                                         "intersection (hold Alt to place freely)")
        self.a_snap_objects = self._act("Snap to &objects", self._apply_grid_settings,
                                        tip="Points jump to nearby markup corners, ends and centers "
                                            "and to the drawing's line ends and midpoints "
                                            "(hold Alt to place freely)")
        self.a_snap_page = self._act("Snap to &page", self._apply_grid_settings,
                                     tip="Points jump to the page's corners, the middles of its "
                                         "edges, its center and its edges (hold Alt to place "
                                         "freely)")
        for a, key in ((self.a_grid, "grid_on"), (self.a_snap_grid, "snap_grid"),
                       (self.a_snap_objects, "snap_objects"), (self.a_snap_page, "snap_page")):
            a.setCheckable(True)
            a.setChecked(self.settings.value(key, "false") == "true")
        self.a_grid_settings = self._act("Grid &settings...", self.grid_settings)
        self._apply_grid_settings(save=False)
        self.a_split = self._act("&Split view", self._toggle_split, "F10")
        self.a_split.setCheckable(True)
        self.a_shortcuts = self._act("&Keyboard shortcuts...", self.edit_shortcuts)
        self.a_markups = self._act("&Markups list", self._toggle_markups, "F7")
        self.a_markups.setCheckable(True)
        self.a_author = self._act("&Author name for markups...", self._set_author)
        # arrange: align / distribute / stacking order of the selected markups
        self.arrange_actions = {}
        for key, label, sc, fn in (
                ("al_left", "Align &left", "", lambda: self._align("left")),
                ("al_hcenter", "Align &centers (horizontally)", "", lambda: self._align("hcenter")),
                ("al_right", "Align &right", "", lambda: self._align("right")),
                ("al_top", "Align &top", "", lambda: self._align("top")),
                ("al_vmiddle", "Align &middles (vertically)", "", lambda: self._align("vmiddle")),
                ("al_bottom", "Align &bottom", "", lambda: self._align("bottom")),
                ("dist_h", "Distribute &horizontally", "", lambda: v() and v().distribute("h")),
                ("dist_v", "Distribute &vertically", "", lambda: v() and v().distribute("v")),
                ("z_front", "Bring to &front", "Ctrl+Shift+]", lambda: v() and v().arrange("front")),
                ("z_forward", "Bring &forward", "Ctrl+]", lambda: v() and v().arrange("forward")),
                ("z_backward", "Send bac&kward", "Ctrl+[", lambda: v() and v().arrange("backward")),
                ("z_back", "Send to bac&k", "Ctrl+Shift+[", lambda: v() and v().arrange("back"))):
            self.arrange_actions[key] = self._act(label, fn, sc or None)
        self.a_ribbon = self._act("&Ribbon (instead of toolbars)", self._toggle_ribbon,
                                  tip="Office-style ribbon with labeled tabs; untick for the "
                                      "classic compact toolbars")
        self.a_ribbon.setCheckable(True)
        self.a_ribbon.setChecked(self.settings.value("ui_mode", "ribbon") == "ribbon")
        self.a_collapse = self._act("&Collapse ribbon", self._toggle_collapse, "Ctrl+F1",
                                    tip="Show only the ribbon's tab names (double-click a tab "
                                        "does the same)")
        self.a_collapse.setCheckable(True)
        self.a_group_names = QAction("Show &group names on ribbon", self, checkable=True)
        self.a_group_names.setToolTip("Name each group of ribbon buttons (makes the ribbon taller)")
        self.a_group_names.setChecked(self.settings.value("ribbon_group_names", "false") == "true")
        self.a_group_names.toggled.connect(self._toggle_group_names)
        self.a_menu_bar = QAction("Show &menu bar", self, checkable=True)
        self.a_menu_bar.setShortcut(QKeySequence("Ctrl+Shift+M"))
        self.a_menu_bar.setToolTip("With the ribbon, hide the menu bar to save space; the "
                                   "\u2630 button at the right of the ribbon tabs has every menu")
        self.a_menu_bar.setChecked(self.settings.value("menu_bar", "true") != "false")
        self.a_menu_bar.toggled.connect(self._toggle_menu_bar)
        self.addAction(self.a_menu_bar)            # shortcut works while the menu bar is hidden
        self.a_lock = self._act("&Lock selected", lambda: self._lock_selected(), "Ctrl+L",
                                tip="Lock the selected markups: they can't be clicked, moved or "
                                    "selected on the page (unlock in the Objects panel)")
        self.a_unlock_all = self._act("&Unlock all markups", lambda: self._unlock_all())
        self.align_ref_group = QActionGroup(self)
        self.align_ref_actions = {}
        for key, label in (("first", "First selected"), ("last", "Last selected"),
                           ("selection", "Whole selection"), ("page", "Page")):
            a = QAction("Align to " + label.lower(), self, checkable=True)
            a.triggered.connect(lambda _=False, k=key: self._set_align_ref(k))
            self.align_ref_group.addAction(a)
            self.align_ref_actions[key] = a
        ref = self.settings.value("align_ref", "first")
        self.align_ref_actions.get(ref, self.align_ref_actions["first"]).setChecked(True)
        self.a_flatten = self._act("&Flatten...", self.flatten,
                                   tip="Make annotations and form fields a permanent part of the page")
        self.a_delete_annot = self._act("Delete selected annotation",
                                        lambda: v() and v().delete_selected())
        self.a_manual = self._act("&User manual", self.show_manual, "F1")
        self.a_about = self._act("&About", self.about)
        self.a_check_updates = self._act("&Check for updates...", self.check_updates,
                                         tip="Ask GitHub whether a newer KanzonasPDF is out")
        self.a_auto_updates = QAction("Check for updates &automatically", self, checkable=True)
        self.a_auto_updates.setToolTip("Once a day at start-up; only tells you, never installs")
        self.a_auto_updates.setChecked(self.settings.value("update_check", "true") != "false")
        self.a_auto_updates.toggled.connect(
            lambda on: self.settings.setValue("update_check", "true" if on else "false"))

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
        self.tool_actions[self.tool].setChecked(True)
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
        m.addAction(self.a_combine)
        em = m.addMenu("&Export to")
        em.addActions(self.export_actions)
        m.addAction(self.a_compare)
        m.addSeparator()
        m.addAction(self.a_print)
        m.addSeparator()
        m.addAction(self.a_prefs)
        m.addSeparator()
        m.addActions([self.a_close, self.a_exit])
        m = mb.addMenu("&Edit")
        m.addActions([self.a_undo, self.a_redo])
        m.addSeparator()
        m.addActions([self.a_cut, self.a_copy, self.a_paste, self.a_duplicate, self.a_select_all])
        m.addSeparator()
        m.addAction(self.a_delete_annot)
        m.addSeparator()
        m.addAction(self.a_author)
        m.addSeparator()
        m.addActions([self.a_find, self.a_find_next, self.a_find_prev])
        m = self.view_menu = mb.addMenu("&View")
        m.addActions([self.a_zoom_in, self.a_zoom_out, self.a_actual, self.a_fit_width,
                      self.a_fit_page])
        m.addSeparator()
        m.addActions([self.a_sidebar, self.a_props, self.a_chest, self.a_markups, self.a_cards])
        m.addSeparator()
        m.addAction(self.a_split)
        m.addAction(self.a_cad_mouse)
        m.addAction(self.a_page_wheel)
        m.addAction(self.a_hl_fields)
        m.addSeparator()
        m.addActions([self.a_grid, self.a_snap_grid, self.a_snap_objects, self.a_snap_page,
                      self.a_grid_settings])
        m.addSeparator()
        tm = m.addMenu("&Theme")
        tm.addActions(list(self.theme_actions.values()))
        m.addAction(self.a_labels)
        m.addActions([self.a_ribbon, self.a_collapse, self.a_group_names, self.a_menu_bar])
        m.addSeparator()
        m.addAction(self.a_shortcuts)
        m = mb.addMenu("&Arrange")
        acts = self.arrange_actions
        m.addActions([acts[k] for k in ("al_left", "al_hcenter", "al_right")])
        m.addActions([acts[k] for k in ("al_top", "al_vmiddle", "al_bottom")])
        rm = m.addMenu("Align &relative to")
        rm.addActions(list(self.align_ref_actions.values()))
        m.addSeparator()
        m.addActions([acts["dist_h"], acts["dist_v"]])
        m.addSeparator()
        m.addActions([acts[k] for k in ("z_front", "z_forward", "z_backward", "z_back")])
        m.addSeparator()
        m.addActions([self.a_lock, self.a_unlock_all])
        m.addSeparator()
        hint = m.addAction("Ctrl+click or drag a box with Select to pick several markups")
        hint.setEnabled(False)
        m = mb.addMenu("&Tools")
        m.addActions(self.tool_group.actions())
        m.addSeparator()
        m.addAction(self.a_props)
        m.addSeparator()
        m.addActions([self.a_ocr, self.a_flatten])
        m = mb.addMenu("&Document")
        m.addActions([self.a_header, self.a_watermark, self.a_remove_wm, self.a_background,
                      self.a_remove_bg])
        m.addSeparator()
        m.addAction(self.a_bookmarks)
        m.addAction(self.a_attachments)
        m.addSeparator()
        rm = m.addMenu("&Redaction")
        rm.addActions([self.tool_actions["redact"], self.a_search_redact,
                       self.a_apply_sel_redact, self.a_apply_redact])
        m.addSeparator()
        m.addActions([self.a_compress, self.a_compare, self.a_flatten])
        m = mb.addMenu("&Measure")
        m.addActions([self.tool_actions[t[0]] for t in MEASURE_TOOLS])
        m.addSeparator()
        m.addActions([self.a_set_scale, self.a_measure_summary])
        m = mb.addMenu("&Review")
        m.addActions([self.tool_actions["comment"], self.tool_actions["note"]])
        m.addSeparator()
        m.addActions([self.a_prev_markup, self.a_next_markup, self.a_markups])
        m.addSeparator()
        m.addActions([self.a_show_markups, self.a_cards])
        m.addSeparator()
        m.addActions([self.a_delete_markups, self.a_flatten_markups])
        m = mb.addMenu("&Protect")
        m.addActions([self.tool_actions["signature"], self.tool_actions["initials"],
                      self.tool_actions["date"], self.a_multi_sign])
        # setting up (or replacing) your signature / initials lives in File > Preferences >
        # You: here it read like "add my signature to this document"
        m.addSeparator()
        m.addActions([self.tool_actions["placeholder"], self.a_apply_placeholders])
        m.addSeparator()
        m.addActions([self.a_digisign, self.a_timestamp, self.a_sig_details, self.a_clear_sigs])
        m.addSeparator()
        rm = m.addMenu("Re&daction")
        rm.addActions([self.tool_actions["redact"], self.a_search_redact,
                       self.a_apply_sel_redact, self.a_apply_redact])
        m.addAction(self.a_sanitize)
        m.addSeparator()
        m.addActions([self.a_security, self.a_remove_security, self.a_unlock])
        m = mb.addMenu("F&orms")
        m.addActions([self.tool_actions[t] for t, _, _ in FORM_TOOLS])
        m.addSeparator()
        m.addAction(self.a_hl_fields)
        m.addActions([self.a_next_field, self.a_prev_field])
        hint = m.addAction("To fill in a form: use Select or Hand and click a field")
        hint.setEnabled(False)
        m = mb.addMenu("&Pages")
        m.addActions([self.a_copy_pages, self.a_cut_pages, self.a_paste_pages, self.a_dup_pages])
        m.addSeparator()
        m.addActions([self.a_rot_l, self.a_rot_r])
        m.addSeparator()
        m.addActions([self.a_move_up, self.a_move_down, self.a_del_page])
        m.addSeparator()
        m.addActions([self.a_insert_pdf, self.a_insert_blank, self.a_extract])
        sep = QAction(self)
        sep.setSeparator(True)
        self.thumbs.addActions([self.a_copy_pages, self.a_cut_pages, self.a_paste_pages,
                                self.a_dup_pages, sep, self.a_rot_l, self.a_rot_r, self.a_del_page])
        m = mb.addMenu("&Help")
        m.addAction(self.a_manual)
        m.addSeparator()
        m.addActions([self.a_check_updates, self.a_auto_updates])
        m.addSeparator()
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
        self.zoom_box = QComboBox()
        self.zoom_box.setEditable(True)
        self.zoom_box.addItems(ZOOM_PRESETS)
        self.zoom_box.setMinimumWidth(80)
        self.zoom_box.lineEdit().returnPressed.connect(self._zoom_from_box)
        self.zoom_box.activated.connect(lambda _: self._zoom_from_box())
        # zoom and page groups are widgets so the ribbon layout can move them to the status bar
        self.zoom_group = self._group_widget([self.a_zoom_out, self.zoom_box, self.a_zoom_in])
        self._zoom_group_act = tb.addWidget(self.zoom_group)
        tb.addActions([self.a_fit_width, self.a_fit_page, self.a_cad_mouse])
        tb.addSeparator()
        tb.addActions([self.a_grid, self.a_snap_grid, self.a_snap_objects, self.a_snap_page])
        tb.addSeparator()
        self.page_spin = QSpinBox()
        self.page_spin.setMinimum(1)
        self.page_spin.setKeyboardTracking(False)
        self.page_spin.setButtonSymbols(QSpinBox.NoButtons)       # left/right buttons instead
        self.page_spin.setAlignment(Qt.AlignCenter)
        self.page_spin.valueChanged.connect(lambda n: self.view() and self.view().goto_page(n - 1))
        self.prev_page_btn = QToolButton()
        self.prev_page_btn.setArrowType(Qt.LeftArrow)
        self.prev_page_btn.setToolTip("Previous page (Left arrow key)")
        self.prev_page_btn.clicked.connect(lambda: self._step_page(-1))
        self.next_page_btn = QToolButton()
        self.next_page_btn.setArrowType(Qt.RightArrow)
        self.next_page_btn.setToolTip("Next page (Right arrow key)")
        self.next_page_btn.clicked.connect(lambda: self._step_page(1))
        self.page_total = QLabel(" / 0 ")
        self.first_page_btn = QToolButton()
        self.first_page_btn.setText("\u23EE")
        self.first_page_btn.setToolTip("First page")
        self.first_page_btn.clicked.connect(lambda: self._step_page(-10 ** 9))
        self.last_page_btn = QToolButton()
        self.last_page_btn.setText("\u23ED")
        self.last_page_btn.setToolTip("Last page")
        self.last_page_btn.clicked.connect(lambda: self._step_page(10 ** 9))
        for b in (self.first_page_btn, self.prev_page_btn, self.next_page_btn, self.last_page_btn):
            b.setAutoRaise(True)
        self.nav_group = self._group_widget([QLabel(" Page "), self.first_page_btn,
                                             self.prev_page_btn, self.page_spin,
                                             self.next_page_btn, self.last_page_btn,
                                             self.page_total])
        # bottom-bar extras for the ribbon layout (PDF-XChange style): fit buttons and a slider
        self.zoom_slider = QSlider(Qt.Horizontal)
        self.zoom_slider.setRange(10, 800)
        self.zoom_slider.setFixedWidth(110)
        self.zoom_slider.setToolTip("Zoom: drag to zoom from 10% to 800%")
        self.zoom_slider.sliderMoved.connect(
            lambda val: self.view() and self.view().set_zoom(val / 100))
        self.view_group = self._group_widget([self.a_fit_page, self.a_fit_width, self.a_actual,
                                              self.zoom_slider])
        self._nav_group_act = tb.addWidget(self.nav_group)
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._spacer_act = tb.addWidget(spacer)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Find (Ctrl+F)")
        self.search.setClearButtonEnabled(True)
        self.search.setMaximumWidth(260)
        self.search.returnPressed.connect(lambda: self._find(False))
        self.search.textChanged.connect(lambda t: (not t) and self.view()
                                        and self.view().clear_search())
        self._search_act = tb.addWidget(self.search)

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
        forms_btn.setToolTip("Form field tools: add text fields, checkboxes, option buttons, "
                             "dropdowns and signature fields")
        forms_btn.setPopupMode(QToolButton.InstantPopup)
        fmenu = QMenu(forms_btn)
        fmenu.addActions([self.tool_actions[t] for t, _, _ in FORM_TOOLS])
        forms_btn.setMenu(fmenu)
        tt.addWidget(forms_btn)

        at = self.arrange_tb = QToolBar("Arrange")
        at.setObjectName("arrange")
        at.setMovable(False)
        self.addToolBar(at)
        acts = self.arrange_actions
        at.addActions([acts[k] for k in ("al_left", "al_hcenter", "al_right",
                                         "al_top", "al_vmiddle", "al_bottom")])
        self.align_ref_box = QComboBox()
        self.align_ref_box.setToolTip("Align relative to: the first markup you selected (default), "
                                      "the last one selected, the whole selection, or the page")
        for key, a in self.align_ref_actions.items():
            self.align_ref_box.addItem(a.text().replace("Align to ", "to "), key)
        self.align_ref_box.setCurrentIndex(max(0, self.align_ref_box.findData(self._align_ref())))
        self.align_ref_box.activated.connect(
            lambda i: self._set_align_ref(self.align_ref_box.itemData(i)))
        at.addWidget(self.align_ref_box)
        at.addSeparator()
        at.addActions([acts["dist_h"], acts["dist_v"]])
        at.addSeparator()
        at.addActions([acts[k] for k in ("z_front", "z_forward", "z_backward", "z_back")])
        self._build_ribbon()

    def _build_sidebar(self):
        self.thumbs = QListWidget()
        self.thumbs.setViewMode(QListWidget.ListMode)
        self.thumbs.setIconSize(QSize(120, 160))
        self.thumbs.setSpacing(4)
        self.thumbs.setUniformItemSizes(True)
        self.thumbs.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.thumbs.installEventFilter(self)          # resize: thumbnails follow the panel width
        # drag a thumbnail to a new position to reorder pages (only when unlocked)
        self.thumbs.setDefaultDropAction(Qt.MoveAction)
        self.thumbs.setDropIndicatorShown(True)
        self.thumbs.model().rowsMoved.connect(self._on_thumb_moved)
        self.lock_btn = QToolButton()
        self.lock_btn.setCheckable(True)
        self.lock_btn.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.lock_btn.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.lock_btn.toggled.connect(self._set_pages_locked)
        side = QWidget()
        sl = QVBoxLayout(side)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(2)
        sl.addWidget(self.lock_btn)
        sl.addWidget(self.thumbs)
        self.thumbs.currentRowChanged.connect(self._on_thumb_clicked)
        self.thumbs.setSelectionMode(QAbstractItemView.ExtendedSelection)   # Ctrl/Shift+click
        self.thumbs.setContextMenuPolicy(Qt.ActionsContextMenu)
        self.dock = QDockWidget("Pages")
        self.dock.setObjectName("pages")
        self.dock.setFeatures(QDockWidget.DockWidgetClosable)
        # Pages and Bookmarks are tabs inside one panel (two tabbed dock groups on both sides
        # of the window trigger a Qt bug that draws a phantom duplicate tab bar).
        self.left_tabs = QTabWidget()
        self.left_tabs.setTabPosition(QTabWidget.South)
        self.left_tabs.setDocumentMode(True)
        self.left_tabs.setUsesScrollButtons(True)     # narrow panel: tabs scroll, don't block
        self.left_tabs.tabBar().setElideMode(Qt.ElideRight)
        self.left_tabs.addTab(side, "Pages")
        self.dock.setWidget(self.left_tabs)
        # locked by default so pages can't be moved by accident; remembered between sessions
        locked = self.settings.value("pages_locked", "true") != "false"
        self.lock_btn.setChecked(locked)
        self._set_pages_locked(locked)
        self.dock.setMinimumWidth(70)
        self.left_tabs.setMinimumWidth(70)
        self.dock.visibilityChanged.connect(lambda vis: self.a_sidebar.setChecked(vis))
        self.addDockWidget(Qt.LeftDockWidgetArea, self.dock)

        from .bookmarks_panel import BookmarksPanel
        self.bookmarks = BookmarksPanel()
        self.bookmarks.current_page = lambda: self.view().current_page() if self.view() else 0
        self.bookmarks.jump.connect(lambda i: self.view() and self.view().goto_page(i))
        self.bookmarks.changed.connect(lambda toc: self.view() and self.view().set_toc(toc))
        self.left_tabs.addTab(self._narrowable(self.bookmarks), "Bookmarks")
        from .layers_panel import LayersPanel
        self.layers = LayersPanel()
        self.layers.toggled.connect(lambda n, on: self.view() and self.view().set_layer(n, on))
        self.layers.allToggled.connect(self._all_layers)
        self.left_tabs.addTab(self._narrowable(self.layers), "Layers")
        from .objects_panel import ObjectsPanel
        self.objects = ObjectsPanel()
        self.objects.selectRequested.connect(self._objects_select)
        self.objects.flagsChanged.connect(self._objects_flags)
        self.objects.arrange.connect(lambda how: self.view() and self.view().arrange(how))
        self.left_tabs.addTab(self._narrowable(self.objects), "Objects")
        self._objects_timer = QTimer(self, singleShot=True, interval=150)
        self._objects_timer.timeout.connect(self._refresh_objects)
        self.left_tabs.currentChanged.connect(lambda _i: self._objects_timer.start())

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
        self.chest_dock.visibilityChanged.connect(
            lambda _v: self.a_chest.setChecked(self._chest_showing()))
        self.props_dock.raise_()
        self.resizeDocks([self.dock, self.props_dock], [180, 240], Qt.Horizontal)

        self.markups = MarkupsPanel()
        self.markups.activated.connect(lambda i, x: self.view() and self.view().reveal(i, x))
        self.markups.editRequested.connect(self._edit_markup)
        self.markups.deleteRequested.connect(self._delete_markup)
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
                  self.a_security, self.a_remove_security, self.a_sanitize, self.a_clear_sigs,
                  self.a_timestamp, self.a_multi_sign, self.a_apply_placeholders,
                  self.a_apply_sel_redact, self.a_unlock, self.a_set_scale, self.a_measure_summary,
                  self.a_compare, self.a_header, self.a_watermark, self.a_compress,
                  self.a_background, self.a_remove_bg, self.a_remove_wm,
                  self.a_search_redact, self.a_apply_redact, self.a_digisign, self.a_sig_details,
                  *self.export_actions):
            a.setEnabled(has)
        self.a_delete_annot.setEnabled(has and v.selection is not None)
        self.a_lock.setEnabled(has and v.selection is not None)
        self.a_unlock_all.setEnabled(has)
        if hasattr(self, "_objects_timer"):
            self._objects_timer.start()
        n_sel = len(v.selected_xrefs()) if has else 0
        for key, a in self.arrange_actions.items():
            need = 3 if key.startswith("dist") else 2 if key.startswith("al_") and \
                self._align_ref() != "page" else 1
            # stacking order also works on pictures / shapes selected with Edit objects
            a.setEnabled(n_sel >= need or key.startswith("z_") and has
                         and v.obj_sel is not None)
        self.a_undo.setEnabled(has and v.can_undo())
        self.a_redo.setEnabled(has and v.can_redo())
        self.page_spin.setEnabled(has)
        self.prev_page_btn.setEnabled(has and v.current_page() > 0)
        self.first_page_btn.setEnabled(self.prev_page_btn.isEnabled())
        self.next_page_btn.setEnabled(has and v.current_page() < v.page_count() - 1)
        self.last_page_btn.setEnabled(self.next_page_btn.isEnabled())
        if has:
            self.page_spin.blockSignals(True)
            self.page_spin.setMaximum(v.page_count())
            self.page_spin.setValue(v.current_page() + 1)
            self.page_spin.blockSignals(False)
            self.page_total.setText(f" / {v.page_count()} ")
            self.zoom_box.setEditText(f"{round(v.zoom * 100)}%")
            if not self.zoom_slider.isSliderDown():
                self.zoom_slider.blockSignals(True)
                self.zoom_slider.setValue(round(v.zoom * 100))
                self.zoom_slider.blockSignals(False)
            self.scale_label.setText(v.page_scale_text(v.current_page()))
            name = os.path.basename(v.path) + (" [protected]" if v.read_only else "")
            self.setWindowTitle(f"{'*' if v.dirty else ''}{name} - {_title_base()}")
            for i in range(self.tabs.count()):
                w = self.tabs.widget(i)
                self.tabs.setTabText(i, ("*" if w.dirty else "") + os.path.basename(w.path))
                self.tabs.setTabToolTip(i, w.path)
        else:
            self.page_total.setText(" / 0 ")
            self.scale_label.setText("")
            self.setWindowTitle(_title_base())

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
        v.openFileRequested.connect(self._open_linked_pdf)
        v.signedDocument.connect(self._on_signed)
        v.oneShotPlaced.connect(self._after_one_shot)
        v.selectToolRequested.connect(lambda: self.set_tool("select"))
        v.calibrateRequested.connect(self._calibrate)
        v.layersChanged.connect(lambda: self.sender() is self.view() and self._rebuild_thumbs())
        v.scaleChanged.connect(self._update_ui)
        v.documentChanged.connect(self._markups_timer.start)
        v.structureChanged.connect(self._markups_timer.start)
        v.requestSignature.connect(self._sign_field)
        for kind, png in self._sig_cache.items():
            v.set_sig_image(kind, png)
        if v.read_only:
            QTimer.singleShot(0, lambda: QMessageBox.information(
                self, "Protected document", "This PDF is protected against changes. You can "
                "read, search and print it. Use Protect > Unlock with password if you have its "
                "permissions password."))
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
        self.autosave.discard(v)
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
        self.autosave.discard(v)
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
        self.autosave.discard(v)
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
        from . import autosave
        backups = autosave.folder()
        session = []
        for i in range(self.tabs.count()):
            v = self.tabs.widget(i)
            self._remember_state(v)
            if v.path and os.path.exists(v.path) and \
                    not os.path.normcase(v.path).startswith(os.path.normcase(backups)):
                session.append(v.path)
        self.settings.setValue("session_files", json.dumps(session))
        self.autosave.discard_all()
        self.settings.setValue("geometry", self.saveGeometry())
        e.accept()

    def restore_session(self):
        """Start-up: reopen the files that were open when KanzonasPDF was last closed (if
        that's turned on in Preferences > Start-up)."""
        if self.settings.value("restore_session", "false") != "true":
            return
        try:
            files = json.loads(self.settings.value("session_files", "[]") or "[]")
        except ValueError:
            files = []
        for p in files:
            if isinstance(p, str) and os.path.exists(p):
                self.open_file(p)

    def recover_backups(self):
        """Start-up: offer the automatic backup copies left by a run that didn't exit
        normally (a crash or power cut)."""
        from . import autosave
        try:
            items = autosave.leftovers()
        except OSError:
            return
        if not items:
            return
        names = "\n".join("  " + (os.path.basename(o) if o else os.path.basename(p))
                           for p, o, _t in items[:10])
        r = QMessageBox.question(
            self, "Recover unsaved changes?",
            "KanzonasPDF didn't close normally last time. Automatic backup copies of these "
            f"documents have unsaved changes:\n\n{names}\n\nOpen the copies now? Use Save As "
            "to keep one. (They stay in the backups folder for 30 days either way: "
            "File > Preferences > Saving > Open backup folder.)")
        moved = autosave.set_aside(items)
        if r == QMessageBox.Yes:
            for p in moved:
                self.open_file(p)

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
        if not v or not v.require_permission(pymupdf.PDF_PERM_PRINT, "Printing"):
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
        dpi = min(printer.resolution(), 300 if v.allowed(pymupdf.PDF_PERM_PRINT_HQ) else 150)
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
        if tool in ("hand", "select"):
            self._last_basic_tool = tool            # where signing / dating returns to
        self.tool_actions[tool].setChecked(True)
        for i in range(self.tabs.count()):
            self.tabs.widget(i).set_tool(tool)
        self._refresh_props()

    def _after_one_shot(self):
        """After placing a signature, initials or a date: back to the Hand or Select tool,
        whichever was used last."""
        if self.tool in ("signature", "initials", "date"):
            self.set_tool(getattr(self, "_last_basic_tool", "hand"))

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

    def _open_linked_pdf(self, path, page):
        self.open_file(path)
        v = self.view()
        if v is not None and page >= 0 and os.path.normcase(v.path or "") == os.path.normcase(path):
            QTimer.singleShot(200, lambda: v.goto_page(min(page, v.page_count() - 1)))

    def _on_selection_changed(self):
        if self.sender() is self.view():
            self._refresh_props()
            self._update_ui()

    def _chest_showing(self):
        """True when the tool chest is on screen (not just a tab behind Properties)."""
        d = self.chest_dock
        return d.isVisible() and not d.visibleRegion().isEmpty()

    def _toggle_chest(self):
        """Tool chest (F8, View tab): open it, or close it if it's already showing. When it
        shares the panel with Properties and is the hidden tab, bring it to the front."""
        if self._chest_showing():
            self.chest_dock.hide()
        else:
            self.chest_dock.show()
            self.chest_dock.raise_()
        self.a_chest.setChecked(self._chest_showing())

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
        if t == QEvent.Resize and obj is getattr(self, "thumbs", None):
            QTimer.singleShot(0, self._fit_thumbs)     # after the list has laid out its new size
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
        if op in ("del", "move", "blank") and not self._pages_unlocked():
            return
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

    def combine_files(self):
        from .combine import CombineDialog
        v = self.view()
        first = [v.path] if v is not None and v.path and os.path.isfile(v.path) else []
        if first and v.dirty:
            QMessageBox.information(self, "Combine files", "The current document has unsaved "
                                    "changes; the combined PDF uses the saved file.")
        dlg = CombineDialog(self, self.settings.value("last_dir", ""), first)
        if dlg.exec() and dlg.result_path:
            self.open_file(dlg.result_path)
            self.statusBar().showMessage("Combined into " + dlg.result_path, 5000)

    def insert_from_file(self):
        v = self.view()
        if not v:
            return
        if not self._pages_unlocked():
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
        if not v or not v.require_permission(pymupdf.PDF_PERM_COPY, "Extracting"):
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
        from . import ocr as ocrmod
        n = v.page_count()
        dlg = QDialog(self)
        dlg.setWindowTitle("Recognize text (OCR)")
        form = QFormLayout(dlg)
        rb_all = QRadioButton("All")
        rb_cur = QRadioButton(f"Current page ({v.current_page() + 1})")
        rb_custom = QRadioButton("Pages:")
        custom = QLineEdit()
        custom.setPlaceholderText(f"e.g. 1-3, 7 (of {n})")
        custom.textEdited.connect(lambda _t: rb_custom.setChecked(True))
        rb_all.setChecked(True)
        row = QHBoxLayout()
        for w in (rb_all, rb_cur, rb_custom, custom):
            row.addWidget(w)
        form.addRow("Pages:", row)
        skip = QCheckBox("Skip pages that already contain text")
        skip.setChecked(True)
        skip.setToolTip("Pages that already have text (not scanned) are left alone, so their "
                        "text isn't duplicated")
        form.addRow("", skip)
        acc = QComboBox()
        for key in ("auto", "fast", "normal", "high"):
            acc.addItem(ocrmod.ACCURACY_LABELS[key], key)
        acc.setCurrentIndex(max(0, acc.findData(self.settings.value("ocr_accuracy", "auto"))))
        acc.setToolTip("Accuracy is how sharp a page image the recognizer gets. Higher is slower "
                       "and uses more memory; Auto starts fast and redoes a page sharper only "
                       "when its text is small or unclear.")
        form.addRow("Accuracy:", acc)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.button(QDialogButtonBox.Ok).setText("Recognize")
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        form.addRow(btns)
        if not dlg.exec():
            return
        if rb_cur.isChecked():
            pages = [v.current_page()]
        elif rb_custom.isChecked():
            pages = parse_page_list(custom.text(), n)
            if not pages:
                QMessageBox.warning(self, "OCR", f"Type pages between 1 and {n}, for example "
                                    "1-3, 7.")
                return
        else:
            pages = list(range(n))
        if skip.isChecked():
            with_text = [i for i in pages if v.page_has_text(i)]
            pages = [i for i in pages if i not in with_text]
            if not pages:
                QMessageBox.information(self, "OCR", "The chosen page(s) already have text, so "
                                        "there's nothing to recognize. Untick \"Skip pages that "
                                        "already contain text\" to OCR them anyway (their text "
                                        "may then be duplicated).")
                return
        accuracy = acc.currentData()
        self.settings.setValue("ocr_accuracy", accuracy)
        v.run_ocr(pages, accuracy)

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
        if v is None or v.security is not None or getattr(v, "_asked_protect", False):
            return
        v._asked_protect = True
        r = QMessageBox.question(
            self, "Protect signed document?",
            "Restrict editing of this document with a permissions password when you save it?\n\n"
            "Anyone can still open, read and print it. You choose the password, so you can "
            "unlock it later.\n\nTip: keep an unsigned copy if you may need to change it.")
        if r == QMessageBox.Yes:
            self.security_properties(preset_restrict=True)

    def _sign_field(self, index, xref):
        v = self.sender()
        page = v.doc[index]
        w = page.load_widget(xref)
        # an initials field (made with the Initials field tool, or named so by another app)
        kind = "initials" if "initial" in (w.field_name or "").lower() else "signature"
        rect = w.rect
        if kind not in self._sig_cache:
            png = signatures.get_image(self, kind)
            if png is None:
                return
            self._cache_sig(kind, png)
        v.place_signature(index, kind, field_rect=rect)

    # ---- protection ----------------------------------------------------------------------
    PERMS = [  # (flag, label, allowed by default when restricting)
        (pymupdf.PDF_PERM_PRINT | pymupdf.PDF_PERM_PRINT_HQ, "Printing", True),
        (pymupdf.PDF_PERM_COPY, "Copying text and images", True),
        (pymupdf.PDF_PERM_ANNOTATE, "Adding comments and markups", False),
        (pymupdf.PDF_PERM_FORM, "Filling in form fields and signing", True),
        (pymupdf.PDF_PERM_MODIFY, "Changing the document (text, pages, content)", False),
        (pymupdf.PDF_PERM_ASSEMBLE, "Inserting, deleting and rotating pages", False),
    ]

    def security_properties(self, preset_restrict=False):
        import json
        v = self.view()
        if v is None:
            return
        if v.read_only:
            QMessageBox.information(self, "Security", "This document is protected. Use "
                                    "Protect > Unlock with password with its permissions "
                                    "password first.")
            return
        st = v.security_state()
        dlg = QDialog(self)
        dlg.setWindowTitle("Security properties")
        lay = QVBoxLayout(dlg)
        now = QLabel("Current: " + (f"encrypted ({st['method']})" if st["encrypted"]
                                    else "no security") +
                     (" - changes pending until you save" if v.security is not None else ""))
        lay.addWidget(now)

        def pw_pair():
            a, b = QLineEdit(), QLineEdit()
            for e in (a, b):
                e.setEchoMode(QLineEdit.Password)
            b.setPlaceholderText("Type it again")
            return a, b
        open_on = QCheckBox("Require a password to open the document")
        open_pw, open_pw2 = pw_pair()
        lay.addWidget(open_on)
        f1 = QFormLayout()
        f1.addRow("Open password", open_pw)
        f1.addRow("", open_pw2)
        lay.addLayout(f1)
        note1 = QLabel("Real protection: without it, nobody can read the file. If you forget "
                       "it, the file can't be recovered.")
        note1.setWordWrap(True)
        note1.setStyleSheet("color: gray;")
        lay.addWidget(note1)
        restrict = QCheckBox("Restrict printing, editing and copying")
        own_pw, own_pw2 = pw_pair()
        lay.addWidget(restrict)
        f2 = QFormLayout()
        f2.addRow("Permissions password", own_pw)
        f2.addRow("", own_pw2)
        lay.addLayout(f2)
        lay.addWidget(QLabel("Allow:"))
        boxes = []
        for flag, label, default in self.PERMS:
            c = QCheckBox(label)
            c.setChecked(default)
            boxes.append((flag, c))
            lay.addWidget(c)
        note2 = QLabel("Restrictions are honored by Acrobat, PDF-XChange, Bluebeam and this app, "
                       "but some free tools ignore them. Use an open password for anything "
                       "confidential.")
        note2.setWordWrap(True)
        note2.setStyleSheet("color: gray;")
        lay.addWidget(note2)
        # presets (security policies): which options and permissions, never the passwords
        prow = QHBoxLayout()
        presets = QComboBox()
        try:
            saved = json.loads(self.settings.value("security_presets", "{}") or "{}")
        except (ValueError, TypeError):
            saved = {}
        presets.addItem("(choose a saved policy)")
        presets.addItems(sorted(saved))
        save_p = QPushButton("Save as policy...")
        prow.addWidget(QLabel("Policy:"))
        prow.addWidget(presets, 1)
        prow.addWidget(save_p)
        lay.addLayout(prow)

        def sync():
            for w in (open_pw, open_pw2):
                w.setEnabled(open_on.isChecked())
            for w in (own_pw, own_pw2):
                w.setEnabled(restrict.isChecked())
            for _f, c in boxes:
                c.setEnabled(restrict.isChecked())
        open_on.toggled.connect(sync)
        restrict.toggled.connect(sync)
        restrict.setChecked(preset_restrict)

        def load_preset(i):
            p = saved.get(presets.itemText(i))
            if not p:
                return
            open_on.setChecked(p.get("open", False))
            restrict.setChecked(p.get("restrict", False))
            for flag, c in boxes:
                c.setChecked(bool(p.get("perms", 0) & flag))
        presets.activated.connect(load_preset)

        def save_preset():
            name, ok = QInputDialog.getText(dlg, "Save security policy", "Policy name:")
            if ok and name.strip():
                saved[name.strip()] = {"open": open_on.isChecked(), "restrict": restrict.isChecked(),
                                       "perms": sum(f for f, c in boxes if c.isChecked())}
                self.settings.setValue("security_presets", json.dumps(saved))
                if presets.findText(name.strip()) < 0:
                    presets.addItem(name.strip())
        save_p.clicked.connect(save_preset)
        sync()
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.rejected.connect(dlg.reject)

        def accept():
            if open_on.isChecked() and (not open_pw.text() or open_pw.text() != open_pw2.text()):
                QMessageBox.warning(dlg, "Security", "The open passwords are empty or don't match.")
                return
            if restrict.isChecked() and (not own_pw.text() or own_pw.text() != own_pw2.text()):
                QMessageBox.warning(dlg, "Security",
                                    "The permissions passwords are empty or don't match.")
                return
            if open_on.isChecked() and restrict.isChecked() and open_pw.text() == own_pw.text():
                QMessageBox.warning(dlg, "Security", "Use a different password for permissions: "
                                    "with the same one, anyone who can open it can change it.")
                return
            dlg.accept()
        btns.accepted.connect(accept)
        lay.addWidget(btns)
        if dlg.exec() != QDialog.Accepted:
            return
        perms = pymupdf.PDF_PERM_ACCESSIBILITY | sum(f for f, c in boxes if c.isChecked())
        v.set_security(open_pw.text() if open_on.isChecked() else "",
                       own_pw.text() if restrict.isChecked() else "", perms)
        self.statusBar().showMessage("Security will be applied when you save.", 5000)
        self._update_ui()

    def remove_security(self):
        v = self.view()
        if v is None:
            return
        if v.read_only:
            self.unlock_doc()
            if v.read_only:
                return
        v.set_security("", "", -1)
        self.statusBar().showMessage("Security will be removed when you save.", 5000)
        self._update_ui()

    def sanitize_document(self):
        v = self.view()
        if v is None:
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("Sanitize document")
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel("Remove from this document:"))
        boxes = {}
        for key, label, default in v.SANITIZE_OPTIONS:
            c = QCheckBox(label)
            c.setChecked(default)
            boxes[key] = c
            lay.addWidget(c)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)
        if dlg.exec() == QDialog.Accepted:
            v.sanitize({k: c.isChecked() for k, c in boxes.items()})
            self.statusBar().showMessage("Sanitized. Save to keep it (Undo is available).", 5000)

    def clear_signatures(self):
        v = self.view()
        if v is None:
            return
        if QMessageBox.question(self, "Clear all digital signatures",
                                "Remove every digital signature from this document? The "
                                "signature fields stay, empty. Visible signature images "
                                "you placed aren't affected.") != QMessageBox.Yes:
            return
        n = v.clear_signatures()
        self.statusBar().showMessage(f"Removed {n} digital signature(s).", 5000)
        self._update_ui()

    def timestamp_document(self):
        from . import digisign
        v = self.view()
        if v is None or self._blocked_by_security(v, "Timestamping"):
            return
        if v.dirty:
            QMessageBox.information(self, "Timestamp", "Save your changes first.")
            return
        url, ok = QInputDialog.getItem(self, "Timestamp document",
                                       "Time server (free, needs internet):",
                                       digisign.TIME_SERVERS, 0, True)
        if not ok or not url.strip():
            return
        base, ext = os.path.splitext(v.path)
        out, _ = QFileDialog.getSaveFileName(self, "Save timestamped copy", base + "_timestamped.pdf",
                                             "PDF (*.pdf)")
        if not out:
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            v.timestamp(url.strip(), out)
        except Exception as ex:
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(self, "Timestamp", f"Couldn't get a timestamp from {url}:\n{ex}\n\n"
                                "Check your internet connection or try another server.")
            return
        QApplication.restoreOverrideCursor()
        self.open_file(out)

    def multi_place(self):
        v = self.view()
        if v is None:
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("Multi-place signature or initials")
        form = QFormLayout(dlg)
        what = QComboBox()
        what.addItem("Initials", "initials")
        what.addItem("Signature", "signature")
        form.addRow("Place", what)
        pages = QComboBox()
        pages.addItems(["All pages", "All pages except the first", "All pages except the last",
                        "Pages..."])
        rng = QLineEdit()
        rng.setPlaceholderText("e.g. 1-3, 5, 8")
        form.addRow("On", pages)
        form.addRow("", rng)
        where = QComboBox()
        where.addItem("Same spot as the last one I placed", "same")
        for spot in v.SIG_SPOTS:
            where.addItem(spot.capitalize() + " corner" if "center" not in spot
                          else "Bottom center", spot)
        if not getattr(v, "_last_sig_spot", {}):
            where.setCurrentIndex(1)
        form.addRow("Where", where)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        form.addRow(btns)
        if dlg.exec() != QDialog.Accepted:
            return
        n = v.page_count()
        choice = pages.currentIndex()
        if choice == 0:
            sel = list(range(n))
        elif choice == 1:
            sel = list(range(1, n))
        elif choice == 2:
            sel = list(range(n - 1))
        else:
            sel = self._parse_pages(rng.text(), n)
            if not sel:
                QMessageBox.warning(self, "Multi-place", "Type pages like 1-3, 5.")
                return
        kind = what.currentData()
        if not self._ensure_sig(kind):
            return
        spot = where.currentData()
        if spot == "same" and kind not in getattr(v, "_last_sig_spot", {}):
            spot = "bottom right"
        placed = v.place_signature_on_pages(kind, sel, spot)
        self.statusBar().showMessage(f"Placed your {kind} on {placed} page(s).", 5000)

    @staticmethod
    def _parse_pages(text, n):
        out = []
        for part in text.replace(" ", "").split(","):
            if not part:
                continue
            try:
                if "-" in part:
                    a, b = part.split("-", 1)
                    out += list(range(int(a) - 1, int(b)))
                else:
                    out.append(int(part) - 1)
            except ValueError:
                return []
        return sorted({p for p in out if 0 <= p < n})

    def _ensure_sig(self, kind):
        """Make sure the saved signature / initials image is loaded (asks for the PIN)."""
        if kind not in self._sig_cache:
            png = signatures.get_image(self, kind)
            if png is None:
                return False
            self._cache_sig(kind, png)
        return True

    def apply_placeholders(self):
        v = self.view()
        if v is None:
            return
        found = v.placeholders()
        if not found:
            QMessageBox.information(self, "Placeholders", "This document has no signature "
                                    "placeholders. Add them with Protect > Add signature placeholder.")
            return
        for kind in sorted({k for _i, _x, k, _r in found}):
            if not self._ensure_sig(kind):
                return
        n = v.apply_placeholders()
        self.statusBar().showMessage(f"Filled {n} placeholder(s).", 5000)

    def _apply_selected_redactions(self):
        v = self.view()
        if v is None:
            return
        if QMessageBox.question(self, "Apply selected redactions",
                                "Permanently remove what's under the selected redaction "
                                "marks? Other marks stay pending.") != QMessageBox.Yes:
            return
        n = v.apply_selected_redactions()
        if not n:
            QMessageBox.information(self, "Apply selected redactions",
                                    "Select one or more redaction marks first (Select tool).")

    # ---- objects panel / locking ----------------------------------------------------------
    def _refresh_objects(self):
        if self.left_tabs.currentWidget() is self.objects.parentWidget().parentWidget() and self.dock.isVisible():
            self.objects.refresh(self.view())

    def _objects_select(self, xrefs):
        v = self.view()
        if v is None:
            return
        index = v.current_page()
        objs = {x: (lk, hd) for x, _l, lk, hd in v.page_objects(index)}
        free = [x for x in xrefs if not objs.get(x, (True, True))[0]]
        if len(free) < len(xrefs):
            self.statusBar().showMessage("Locked objects can't be selected: untick Lock first.", 4000)
        if free:
            if self.tool != "select":
                self.set_tool("select")
            v._set_selection(index, free)

    def _objects_flags(self, xrefs, locked, hidden):
        v = self.view()
        if v is not None:
            v.set_object_flags(v.current_page(), xrefs, locked, hidden)

    def _lock_selected(self):
        v = self.view()
        if v is not None:
            n = v.lock_selected()
            self.statusBar().showMessage(f"Locked {n} markup(s). Unlock them in the Objects "
                                         "panel or with Arrange > Unlock all markups.", 5000)

    def _unlock_all(self):
        v = self.view()
        if v is not None:
            self.statusBar().showMessage(f"Unlocked {v.unlock_all()} markup(s).", 4000)

    def _toggle_show_markups(self):
        on = self.a_show_markups.isChecked()
        DocumentView.show_markups = on
        for i in range(self.tabs.count()):
            self.tabs.widget(i).refresh_markup_display()
        self.statusBar().showMessage("Markups shown" if on else
                                     "Markups hidden (they're still in the document)", 4000)

    def delete_comments(self):
        v = self.view()
        if v is None:
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("Delete comments")
        form = QFormLayout(dlg)
        who = QComboBox()
        who.addItem("Everyone's", None)
        me = annotations.author()
        who.addItem(f"Only mine ({me})", me)
        for name in v.markup_authors():
            if name != me:
                who.addItem(f"Only by {name or '(no name)'}", name)
        form.addRow("Delete comments and markups", who)
        where = QComboBox()
        where.addItems(["On all pages", "On this page only"])
        form.addRow("", where)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        form.addRow(btns)
        if dlg.exec() != QDialog.Accepted:
            return
        n = v.delete_markups(who.currentData(),
                             None if where.currentIndex() == 0 else [v.current_page()])
        self.statusBar().showMessage(f"Deleted {n} comment(s) and markup(s). Undo brings "
                                     "them back.", 5000)

    def flatten_comments(self):
        v = self.view()
        if not v:
            return
        choices = ["All pages", "Current page only"]
        pick, ok = QInputDialog.getItem(
            self, "Flatten comments", "Make comments and markups part of the page.\n"
            "They'll look the same but can no longer be edited or moved.\n"
            "Form fields stay fillable. (Undo works until you close the file.)\n\n"
            "Which pages?", choices, 0, False)
        if ok:
            v.flatten(None if pick == choices[0] else [v.current_page()], widgets=False)
            self.statusBar().showMessage("Comments flattened", 4000)

    def _toggle_hl_fields(self):
        on = self.a_hl_fields.isChecked()
        DocumentView.highlight_fields = on
        self.settings.setValue("highlight_fields", "true" if on else "false")
        for i in range(self.tabs.count()):
            for pw in self.tabs.widget(i).pages:
                pw.update()

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
        if not v or not v.require_permission(pymupdf.PDF_PERM_COPY, "Exporting"):
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
    def _all_layers(self, on):
        v = self.view()
        if v:
            v.set_all_layers(on)
            self.layers.set_layers(v.layer_configs())

    def _refresh_layers(self):
        v = self.view()
        self.layers.set_layers(v.layer_configs() if v else [])

    def _show_bookmarks(self):
        self.dock.show()
        self.left_tabs.setCurrentWidget(self.bookmarks.parentWidget().parentWidget())

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

    def background(self):
        from .page_tools import BackgroundDialog
        v = self.view()
        if v:
            dlg = BackgroundDialog(self, v.page_count(), v.current_page())
            if dlg.exec() and dlg.spec:
                v.add_background(dlg.spec, dlg.page_list)

    def remove_background(self):
        from .page_tools import PageChoice
        from . import background as B
        v = self.view()
        if not v:
            return
        have = [i for i in range(v.page_count()) if B.has_background(v.doc[i])]
        if not have:
            QMessageBox.information(self, "Remove background", "No page in this document has a "
                                    "background added with Document > Background.")
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("Remove background")
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel(f"{len(have)} page(s) have a background added with "
                             "Document > Background. Remove it from:"))
        choice = PageChoice(v.page_count(), v.current_page())
        lay.addWidget(choice)
        err = QLabel()
        err.setStyleSheet("color: #c00;")
        lay.addWidget(err)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        lay.addWidget(btns)
        btns.rejected.connect(dlg.reject)

        def ok():
            try:
                dlg.pages_ = choice.pages()
            except ValueError as e:
                err.setText(str(e))
                return
            dlg.accept()
        btns.accepted.connect(ok)
        if dlg.exec():
            v.remove_background([i for i in dlg.pages_ if i in have])

    def remove_watermarks(self):
        from .page_tools import PageChoice, has_watermark
        v = self.view()
        if not v:
            return
        have = [i for i in range(v.page_count()) if has_watermark(v.doc[i])]
        if not have:
            QMessageBox.information(
                self, "Remove watermarks", "No watermark found that can be removed. KanzonasPDF "
                "finds watermarks added with Document > Watermark and by apps that mark them as "
                "watermarks (Adobe Acrobat, PDF-XChange and others). Text or pictures that are "
                "simply part of the page can be taken out with Erase content or Edit objects.")
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("Remove watermarks")
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel(f"{len(have)} page(s) have a watermark. Remove it from:"))
        choice = PageChoice(v.page_count(), v.current_page())
        lay.addWidget(choice)
        err = QLabel()
        err.setStyleSheet("color: #c00;")
        lay.addWidget(err)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        lay.addWidget(btns)
        btns.rejected.connect(dlg.reject)

        def ok():
            try:
                dlg.pages_ = choice.pages()
            except ValueError as e:
                err.setText(str(e))
                return
            dlg.accept()
        btns.accepted.connect(ok)
        if dlg.exec():
            v.remove_watermarks([i for i in dlg.pages_ if i in have])

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
            term = text.strip()
            hidden = v.hidden_matches(term)
            n = v.search_redact(term)
            extra = [f"{c} {what}" for what, c in (("form field(s)", hidden["fields"]),
                     ("markup note(s)", hidden["markups"]), ("bookmark(s)", hidden["bookmarks"]),
                     ("document propert(ies)", hidden["metadata"])) if c]
            msg = (f"Marked {n} occurrence(s) on the pages." if n else
                   "No matches on the pages.")
            if extra and not n:
                if QMessageBox.question(
                        self, "Search & redact",
                        "Not on the pages, but found in " + ", ".join(extra) + ".\n\nRemove it "
                        "from there now? (Fields containing it are deleted; in notes, bookmarks "
                        "and properties it's replaced by [redacted]. Undo works until you close "
                        "the file.)") == QMessageBox.Yes:
                    v.remove_term(term)
                    self.statusBar().showMessage("Removed. Save to make it permanent.", 6000)
                return
            if extra:
                msg += ("\n\nAlso found in " + ", ".join(extra) + ". Those can't be covered "
                        "with a box; they're removed too when you apply the redactions.")
            if n:
                msg += "\n\nReview the marks, then use Apply redactions."
            QMessageBox.information(self, "Search & redact", msg)

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
    def _blocked_by_security(self, v, what):
        """Signing or timestamping a password-protected PDF isn't supported (the signing
        library can't read the encryption PyMuPDF writes). Explain instead of failing."""
        pending = v.security is not None and (v.security.get("open_pw") or v.security.get("owner_pw"))
        if v.security_state()["encrypted"] or pending:
            QMessageBox.information(
                self, what, f"{what} isn't possible on a password-protected PDF yet.\n\n"
                "Use Protect > Remove security and save, then sign. Note that adding a "
                "password after signing changes the file and makes the signature invalid, "
                "so sign the final version.")
            return True
        return False

    def digital_sign(self):
        from . import digisign
        v = self.view()
        if not v or self._blocked_by_security(v, "Digital signing"):
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
        win = QRadioButton("Certificate stored in Windows (cards and tokens too)")
        win_list = QComboBox()
        win_certs = []
        if os.name == "nt":
            try:
                from . import wincerts
                win_certs = wincerts.list_certificates()
            except Exception:
                win_certs = []
        for c in win_certs:
            label = c["name"] + "  (issued by " + ("yourself" if c["self_signed"] else c["issuer"])
            label += ", " + ("EXPIRED " if c["expired"] else "expires ")
            win_list.addItem(label + c["expires"].strftime("%Y-%m-%d") + ")", c["thumbprint"])
        if not win_certs:
            win_list.addItem("No signing certificates in your Windows Personal store")
            win.setEnabled(False)
            win_list.setEnabled(False)
        last = self.settings.value("sign_windows_cert", "")
        if last and win_list.findData(last) >= 0:
            win_list.setCurrentIndex(win_list.findData(last))
        win_list.currentIndexChanged.connect(lambda _: win.setChecked(True))
        source = self.settings.value("sign_source", "")
        if win_certs and (source == "windows"
                          or (not source and not all(c["expired"] for c in win_certs))):
            win.setChecked(True)
        else:
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
        form.addRow(win)
        form.addRow("Windows certificate", win_list)
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
            if win.isChecked():
                from . import wincerts
                thumb = win_list.currentData()
                signer = wincerts.WindowsSigner(thumb)
                self.settings.setValue("sign_windows_cert", thumb)
                self.settings.setValue("sign_source", "windows")
            elif mine.isChecked():
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
            if not win.isChecked():
                signer = digisign.load_signer(path, password.text())
                self.settings.setValue("sign_source", "file")
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
                         "a_rot_l": "rot_l", "a_rot_r": "rot_r", "a_cad_mouse": "cad_mouse",
                         "a_grid": "grid", "a_snap_grid": "snap_grid", "a_snap_objects": "snap_objects",
                         "a_snap_page": "snap_page"}

    def _apply_icons(self):
        for attr, key in self.TOOLBAR_ICON_KEYS.items():
            getattr(self, attr).setIcon(theme.icon(key))
        for key, a in self.arrange_actions.items():
            a.setIcon(theme.icon(key))
        for attr, name in self.RIBBON_ICONS.items():
            getattr(self, attr).setIcon(theme.icon_named(name))
        for tid, a in self.tool_actions.items():
            a.setIcon(theme.icon(tid))
        self.forms_btn.setIcon(theme.icon("forms"))
        for a, name in getattr(self, "_strip_icons", []):
            a.setIcon(theme.icon_named(name))
        labels = self.a_labels.isChecked()
        style = Qt.ToolButtonTextUnderIcon if labels else Qt.ToolButtonIconOnly
        for tb in (self.main_tb, self.tools_tb, self.arrange_tb):
            tb.setToolButtonStyle(style)
            tb.setIconSize(QSize(20, 20))
        if self.a_ribbon.isChecked() and not labels:
            self.main_tb.setIconSize(QSize(16, 16))      # slim quick bar above the ribbon
        for b in (self.shapes_btn, self.measure_btn, self.forms_btn):
            b.setToolButtonStyle(style)
        # tooltips: what the button does, plus its shortcut (icon-only buttons stay discoverable)
        tips = dict(BUTTON_TIPS)
        tips.update({"a_" + k: v for k, v in ARRANGE_TIPS.items()})
        acts = [(k, getattr(self, k)) for k in self.TOOLBAR_ICON_KEYS] + \
            [("a_" + k, a) for k, a in self.arrange_actions.items()] + \
            [("tool_" + k, a) for k, a in self.tool_actions.items()]
        for key, a in acts:
            base = a.property("kz_tip")
            if base is None:                       # first time: remember the plain tip
                base = tips.get(key) or a.toolTip() or a.text().split("\t")[0].replace("&", "")
                sc0 = a.shortcut().toString()
                if sc0 and base.endswith(f"({sc0})"):        # drop a shortcut already in the text
                    base = base[:-len(sc0) - 2].rstrip()
                a.setProperty("kz_tip", base)
            sc = a.shortcut().toString(QKeySequence.NativeText)
            extra = {"a_rot_l": "Ctrl+Shift+Minus", "a_rot_r": "Ctrl+Shift+Plus"}.get(key, sc)
            a.setToolTip(f"{base} ({extra})" if extra else base)
        self.zoom_box.setToolTip("Zoom level: pick one or type a percentage and press Enter")
        self.page_spin.setToolTip("Current page: type a page number and press Enter")
        self.search.setToolTip("Find text in this document (Ctrl+F). Enter or F3 = next match, "
                               "Shift+F3 = previous")
        self.shapes_btn.setToolTip("Shapes: click for the shape shown, or the arrow to pick "
                                   "another (rectangle, ellipse, cloud, polygon, line, arrow, "
                                   "polyline, pen). Hold Shift for squares, circles and straight lines")
        self.measure_btn.setToolTip("Measure: click for the tool shown, or the arrow for length, "
                                    "polylength, area, count, calibrate and scale")

    def _toggle_labels(self):
        self.settings.setValue("toolbar_labels", "true" if self.a_labels.isChecked() else "false")
        self._apply_icons()

    def set_theme(self, mode):
        self.settings.setValue("theme", mode)
        app = QApplication.instance()
        theme.apply(app, mode)
        # widgets with style sheets keep their old colors until re-polished
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
            # only the pages whose markups changed are read again (all after undo, page
            # changes, or switching documents)
            self.markups.refresh(v.doc if v else None, v.take_markup_changes() if v else None)

    # ---- grid and snapping -------------------------------------------------------------
    def _apply_grid_settings(self, *_, save=True):
        from . import snapping
        DocumentView.grid_on = self.a_grid.isChecked()
        DocumentView.snap_grid = self.a_snap_grid.isChecked()
        DocumentView.snap_objects = self.a_snap_objects.isChecked()
        DocumentView.snap_page = self.a_snap_page.isChecked()
        unit = self.settings.value("grid_unit", "in")
        try:
            value = float(self.settings.value("grid_value", 0.5))
            major = int(self.settings.value("grid_major", 4))
        except (TypeError, ValueError):
            value, major = 0.5, 4
        DocumentView.grid_spacing = value * snapping.UNITS.get(unit, 72.0)
        DocumentView.grid_major = major
        if save:
            for a, key in ((self.a_grid, "grid_on"), (self.a_snap_grid, "snap_grid"),
                           (self.a_snap_objects, "snap_objects"), (self.a_snap_page, "snap_page")):
                self.settings.setValue(key, "true" if a.isChecked() else "false")
        if hasattr(self, "tabs"):
            for i in range(self.tabs.count()):
                for pw in self.tabs.widget(i).pages:
                    pw.update()

    def grid_settings(self):
        from PySide6.QtWidgets import QDoubleSpinBox
        from . import snapping
        dlg = QDialog(self)
        dlg.setWindowTitle("Grid settings")
        form = QFormLayout(dlg)
        value = QDoubleSpinBox()
        value.setDecimals(3)
        value.setRange(0.001, 10000)
        unit = QComboBox()
        for k, name in snapping.UNIT_NAMES.items():
            unit.addItem(name, k)
        unit.setCurrentIndex(max(0, unit.findData(self.settings.value("grid_unit", "in"))))
        value.setValue(float(self.settings.value("grid_value", 0.5)))
        row = QWidget()
        rl = QHBoxLayout(row)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.addWidget(value)
        rl.addWidget(unit)
        form.addRow("Grid spacing (on paper)", row)
        major = QSpinBox()
        major.setRange(1, 100)
        major.setValue(int(self.settings.value("grid_major", 4)))
        form.addRow("Darker line every", major)
        show = QCheckBox("Show grid")
        show.setChecked(self.a_grid.isChecked())
        snap = QCheckBox("Snap to grid")
        snap.setChecked(self.a_snap_grid.isChecked())
        objs = QCheckBox("Snap to objects")
        objs.setChecked(self.a_snap_objects.isChecked())
        pagebox = QCheckBox("Snap to page")
        pagebox.setChecked(self.a_snap_page.isChecked())
        for c in (show, snap, objs, pagebox):
            form.addRow("", c)
        hint = QLabel("Hold Alt while drawing or dragging to place a point without snapping.")
        hint.setWordWrap(True)
        form.addRow(hint)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        form.addRow(btns)
        if dlg.exec() != QDialog.Accepted:
            return
        self.settings.setValue("grid_value", value.value())
        self.settings.setValue("grid_unit", unit.currentData())
        self.settings.setValue("grid_major", major.value())
        self.a_grid.setChecked(show.isChecked())
        self.a_snap_grid.setChecked(snap.isChecked())
        self.a_snap_objects.setChecked(objs.isChecked())
        self.a_snap_page.setChecked(pagebox.isChecked())
        self._apply_grid_settings()

    def show_attachments(self):
        from PySide6.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView
        v = self.view()
        if v is None:
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("Attachments")
        dlg.resize(640, 360)
        lay = QVBoxLayout(dlg)
        table = QTableWidget(0, 3)
        table.setHorizontalHeaderLabels(["File", "Size", "Where"])
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        lay.addWidget(table)
        rows = []

        def fill():
            rows[:] = v.attachments()
            table.setRowCount(len(rows))
            for r, (pg, _key, name, size, _desc) in enumerate(rows):
                table.setItem(r, 0, QTableWidgetItem(name))
                table.setItem(r, 1, QTableWidgetItem(f"{size / 1024:,.0f} KB"))
                table.setItem(r, 2, QTableWidgetItem(f"Page {pg + 1}" if pg is not None
                                                     else "Document"))
            empty.setVisible(not rows)
        empty = QLabel("This PDF has no attached files. Use the Attach file tool to add one.")
        lay.addWidget(empty)

        def current():
            r = table.currentRow()
            return rows[r] if 0 <= r < len(rows) else None
        btns = QHBoxLayout()
        for label, fn in (("Open", lambda c: v.open_attachment(c[0], c[1], c[2])),
                          ("Save as...", lambda c: v.save_attachment(c[0], c[1], c[2])),
                          ("Go to", lambda c: c[0] is not None and v.reveal(c[0], c[1])),
                          ("Delete", lambda c: (v.delete_attachment(c[0], c[1]), fill()))):
            b = QPushButton(label)
            b.clicked.connect(lambda _=False, f=fn: current() and f(current()))
            btns.addWidget(b)
        btns.addStretch(1)
        close = QPushButton("Close")
        close.clicked.connect(dlg.accept)
        btns.addWidget(close)
        lay.addLayout(btns)
        table.cellDoubleClicked.connect(lambda r, _c: v.open_attachment(rows[r][0], rows[r][1], rows[r][2]))
        fill()
        dlg.exec()

    def _step_page(self, delta):
        v = self.view()
        if v is not None:
            v.goto_page(max(0, min(v.page_count() - 1, v.current_page() + delta)))

    def _toggle_cad_mouse(self):
        on = self.a_cad_mouse.isChecked()
        DocumentView.cad_mouse = on
        self.settings.setValue("cad_mouse", "true" if on else "false")
        for i in range(self.tabs.count()):
            self.tabs.widget(i).apply_canvas()       # open canvas around the pages, or not
        self.statusBar().showMessage(
            "CAD-style mouse on: scroll wheel zooms, hold the wheel and drag to pan" if on else
            "CAD-style mouse off: scroll wheel scrolls, Ctrl+wheel zooms", 4000)

    def preferences(self):
        from .preferences import PreferencesDialog
        PreferencesDialog(self).exec()

    def _toggle_page_wheel(self):
        on = self.a_page_wheel.isChecked()
        DocumentView.page_wheel = on
        self.settings.setValue("page_wheel", "true" if on else "false")
        self.statusBar().showMessage(
            "Scroll wheel: one page per step when the whole page fits (zoom with Fit page)" if on
            else "Scroll wheel: smooth scrolling", 4000)

    # ---- ribbon --------------------------------------------------------------------------
    # short labels for ribbon buttons (the menus keep the full names)
    RIBBON_LABELS = {
        "a_fit_width": "Fit width", "a_fit_page": "Fit page", "a_actual": "Actual size",
        "a_cad_mouse": "CAD mouse", "a_grid": "Grid", "a_snap_grid": "Snap to grid",
        "a_snap_objects": "Snap to objects", "a_snap_page": "Snap to page",
        "a_grid_settings": "Grid settings",
        "a_set_scale": "Set scale", "a_measure_summary": "Summary", "a_ocr": "OCR",
        "a_rot_l": "Rotate left", "a_rot_r": "Rotate right", "a_lock": "Lock",
        "a_unlock_all": "Unlock all", "a_prev_markup": "Previous", "a_next_markup": "Next",
        "a_markups": "Markups list", "a_show_markups": "Show markups",
        "a_cards": "Comment boxes", "a_delete_markups": "Delete comments",
        "a_flatten_markups": "Flatten comments", "a_multi_sign": "Multi-place",
        "a_setup_sig": "My signature", "a_setup_init": "My initials",
        "a_apply_placeholders": "Apply all", "a_digisign": "Digital sign",
        "a_timestamp": "Timestamp", "a_sig_details": "Signature details",
        "a_clear_sigs": "Clear signatures", "a_search_redact": "Search and redact",
        "a_apply_sel_redact": "Apply selected", "a_apply_redact": "Apply all",
        "a_security": "Security", "a_remove_security": "Remove security", "a_unlock": "Unlock",
        "a_sanitize": "Sanitize", "a_hl_fields": "Highlight fields", "a_move_up": "Move up",
        "a_move_down": "Move down", "a_del_page": "Delete", "a_insert_pdf": "Insert file", "a_combine": "Combine files",
        "a_insert_blank": "Blank page", "a_extract": "Extract", "a_header": "Header and footer",
        "a_watermark": "Watermark", "a_background": "Background",
        "a_remove_bg": "Remove background", "a_remove_wm": "Remove watermarks", "a_bookmarks": "Bookmarks", "a_attachments": "Attachments",
        "a_compress": "Compress", "a_compare": "Compare", "a_flatten": "Flatten",
        "a_sidebar": "Pages panel", "a_props": "Properties", "a_chest": "Tool chest",
        "a_split": "Split view", "a_labels": "Toolbar labels", "a_shortcuts": "Shortcuts",
        "a_manual": "User manual", "a_ribbon": "Ribbon", "a_collapse": "Collapse", "a_group_names": "Group names", "a_menu_bar": "Menu bar",
        "a_zoom_in": "Zoom in", "a_zoom_out": "Zoom out", "a_open": "Open", "a_save": "Save",
        "a_print": "Print", "al_left": "Left", "al_hcenter": "Center", "al_right": "Right",
        "al_top": "Top", "al_vmiddle": "Middle", "al_bottom": "Bottom",
        "dist_h": "Horizontally", "dist_v": "Vertically", "z_front": "To front",
        "z_forward": "Forward", "z_backward": "Backward", "z_back": "To back",
        "tool_redact": "Redact", "tool_placeholder": "Placeholder",
        "tool_erasecontent": "Erase content", "tool_capture": "Capture",
        "tool_editobjects": "Edit objects",
    }
    RIBBON_ICONS = {
        "a_actual": "numeric-1-box-outline", "a_set_scale": "ruler-square",
        "a_measure_summary": "sigma", "a_grid_settings": "cog-outline", "a_lock": "lock-outline",
        "a_unlock_all": "lock-open-variant-outline", "a_prev_markup": "chevron-up",
        "a_next_markup": "chevron-down", "a_markups": "format-list-bulleted",
        "a_show_markups": "eye-outline", "a_cards": "card-text-outline",
        "a_delete_markups": "comment-remove-outline", "a_flatten_markups": "layers-outline",
        "a_multi_sign": "content-copy", "a_setup_sig": "account-edit-outline",
        "a_setup_init": "account-edit", "a_apply_placeholders": "check-all",
        "a_digisign": "certificate-outline", "a_timestamp": "clock-check-outline",
        "a_sig_details": "shield-search", "a_clear_sigs": "shield-remove-outline",
        "a_search_redact": "text-search", "a_apply_sel_redact": "marker-check",
        "a_apply_redact": "check-decagram", "a_security": "shield-lock-outline",
        "a_remove_security": "shield-off-outline", "a_unlock": "lock-open-outline",
        "a_sanitize": "broom", "a_hl_fields": "format-color-highlight",
        "a_move_up": "arrow-up-bold-outline", "a_move_down": "arrow-down-bold-outline",
        "a_del_page": "file-remove-outline", "a_insert_pdf": "file-plus-outline",
        "a_combine": "file-document-multiple-outline",
        "a_insert_blank": "file-outline", "a_extract": "file-export-outline",
        "a_header": "page-layout-header-footer", "a_watermark": "watermark", "a_background": "format-color-fill",
        "a_remove_bg": "format-color-marker-cancel", "a_remove_wm": "water-off-outline",
        "a_bookmarks": "bookmark-outline", "a_attachments": "paperclip",
        "a_compress": "zip-box-outline", "a_compare": "compare", "a_flatten": "layers-triple-outline",
        "a_sidebar": "page-layout-sidebar-left", "a_props": "tune-variant",
        "a_chest": "toolbox-outline", "a_split": "view-split-vertical", "a_labels": "label-outline",
        "a_shortcuts": "keyboard-outline", "a_manual": "help-circle-outline",
        "a_ribbon": "view-dashboard-outline", "a_collapse": "chevron-double-up", "a_group_names": "label-outline", "a_menu_bar": "menu",
    }

    def _build_ribbon(self):
        from .ribbon import Ribbon
        t = self.tool_actions
        A_ = self.arrange_actions
        for attr, label in self.RIBBON_LABELS.items():
            if attr.startswith("tool_"):
                t[attr[5:]].setIconText(label.replace("&&", "&"))
            elif attr in A_:
                A_[attr].setIconText(label)
            else:
                getattr(self, attr).setIconText(label.replace("&&", "&"))
        self.ribbon_align_box = QComboBox()
        for i in range(self.align_ref_box.count()):
            self.ribbon_align_box.addItem(self.align_ref_box.itemText(i), self.align_ref_box.itemData(i))
        self.ribbon_align_box.setCurrentIndex(self.align_ref_box.currentIndex())
        self.ribbon_align_box.setToolTip(self.align_ref_box.toolTip())
        self.ribbon_align_box.activated.connect(
            lambda i: self._set_align_ref(self.ribbon_align_box.itemData(i)))
        r = self.ribbon = Ribbon()
        r.add_tab("Home", [
            ("Tools", "large", [t["select"], t["hand"], t["edittext"], t["editobjects"], t["capture"],
                                t["erasecontent"]]),
            ("Mark up text", "small", [t["highlight"], t["underline"], t["strikeout"],
                                       t["comment"], t["note"], t["textbox"]]),
            ("Insert", "large", [t["stamp"], t["image"], t["attach"]]),
            ("Zoom", "small", [self.a_fit_width, self.a_fit_page, self.a_actual,
                               self.a_zoom_in, self.a_zoom_out, self.a_cad_mouse]),
            ("Sign", "large", [t["signature"], t["initials"]]),
        ])
        r.add_tab("Markup", [
            ("Text", "small", [t["highlight"], t["underline"], t["strikeout"], t["comment"],
                               t["note"], t["textbox"]]),
            ("Callout & stamps", "large", [t["callout"], t["stamp"], t["image"], t["attach"]]),
            ("Shapes", "small", [t["rect"], t["ellipse"], t["cloud"], t["polygon"], t["line"],
                                 t["arrow"], t["polyline"], t["ink"]]),
            ("Erase", "large", [t["eraser"], t["erasecontent"]]),
            ("Styles", "large", [self.a_props, self.a_chest]),
        ])
        # snapping is offered where it's used: Measure, Arrange (lining markups up) and View
        snap_group = [self.a_snap_grid, self.a_snap_objects, self.a_snap_page, self.a_grid,
                      self.a_grid_settings]
        r.add_tab("Measure", [
            ("Measure", "large", [t["m_length"], t["m_poly"], t["m_area"], t["m_count"]]),
            ("Scale", "small", [t["m_calibrate"], self.a_set_scale, self.a_measure_summary]),
            ("Grid & snap", "small", snap_group),
        ])
        r.add_tab("Arrange", [
            ("Align", "small", [A_["al_left"], A_["al_hcenter"], A_["al_right"], A_["al_top"],
                                A_["al_vmiddle"], A_["al_bottom"]]),
            ("Align to", "small", [self.ribbon_align_box]),
            ("Distribute", "small", [A_["dist_h"], A_["dist_v"]]),
            ("Order", "small", [A_["z_front"], A_["z_forward"], A_["z_backward"], A_["z_back"]]),
            ("Lock", "large", [self.a_lock, self.a_unlock_all]),
            ("Snap", "small", snap_group),
        ])
        r.add_tab("Review", [
            ("Add", "large", [t["comment"], t["note"]]),
            ("Navigate", "large", [self.a_prev_markup, self.a_next_markup, self.a_markups]),
            ("Show", "small", [self.a_show_markups, self.a_cards]),
            ("Manage", "large", [self.a_delete_markups, self.a_flatten_markups]),
        ])
        r.add_tab("Protect", [
            ("Sign", "large", [t["signature"], t["initials"], t["date"], self.a_multi_sign]),
            ("Placeholders", "large", [t["placeholder"], self.a_apply_placeholders]),
            ("Digital signatures", "small", [self.a_digisign, self.a_timestamp,
                                             self.a_sig_details, self.a_clear_sigs]),
            ("Redact", "small", [t["redact"], self.a_search_redact, self.a_apply_sel_redact,
                                 self.a_apply_redact]),
            ("Security", "large", [self.a_security, self.a_remove_security, self.a_unlock,
                                   self.a_sanitize]),
        ])
        r.add_tab("Forms", [
            ("Add fields", "large", [t[k] for k, _l, _t in FORM_TOOLS]),
            ("Show", "large", [self.a_hl_fields]),
        ])
        r.add_tab("Pages", [
            ("Rotate", "large", [self.a_rot_l, self.a_rot_r]),
            ("Organize", "small", [self.a_move_up, self.a_move_down, self.a_del_page,
                                   self.a_insert_pdf, self.a_insert_blank, self.a_extract]),
            ("Combine", "large", [self.a_combine]),
            ("Document", "small", [self.a_header, self.a_watermark, self.a_background,
                                   self.a_bookmarks, self.a_attachments, self.a_compress,
                                   self.a_compare]),
            ("Convert", "large", [self.a_ocr, self.a_flatten]),
        ])
        r.add_tab("View", [
            ("Panels", "small", [self.a_sidebar, self.a_props, self.a_markups, self.a_chest,
                                 self.a_split]),
            ("Display", "small", [self.a_hl_fields, self.a_show_markups, self.a_cad_mouse]),
            ("Grid & snap", "small", snap_group),
            ("Ribbon", "small", [self.a_ribbon, self.a_collapse, self.a_group_names,
                                 self.a_menu_bar]),
            ("Help", "large", [self.a_shortcuts, self.a_manual]),
        ])
        r.collapsedChanged.connect(self._ribbon_collapsed)
        # quick-access icons in the tab row (left), find box and menu button (right), like
        # LibreOffice: no separate toolbar row above the ribbon
        q = self.quick_tb = QToolBar()
        q.setIconSize(QSize(16, 16))
        q.setStyleSheet("QToolBar { border: 0; padding: 0; spacing: 0; }")
        q.addActions([self.a_open, self.a_save, self.a_print])
        q.addSeparator()
        q.addActions([self.a_undo, self.a_redo])
        r.setCornerWidget(q, Qt.TopLeftCorner)
        self.ribbon_right = QWidget()
        rh = QHBoxLayout(self.ribbon_right)
        rh.setContentsMargins(0, 0, 2, 0)
        rh.setSpacing(2)
        self.menu_btn = QToolButton()
        self.menu_btn.setText("\u2630")
        self.menu_btn.setToolTip("Menus (shown when the menu bar is hidden: View > Show menu bar)")
        self.menu_btn.setPopupMode(QToolButton.InstantPopup)
        self.menu_btn.setAutoRaise(True)
        menu = QMenu(self.menu_btn)
        for a in self.menuBar().actions():
            menu.addAction(a)
        self.menu_btn.setMenu(menu)
        rh.addWidget(self.menu_btn)
        r.setCornerWidget(self.ribbon_right, Qt.TopRightCorner)
        # keep every menu command's shortcut working when the menu bar is hidden
        def walk(m):
            for a in m.actions():
                if a.menu() is not None:
                    walk(a.menu())
                elif not a.isSeparator() and a not in self.actions():
                    self.addAction(a)
        for top in self.menuBar().actions():
            if top.menu() is not None:
                walk(top.menu())
        self.addToolBarBreak()
        rt = self.ribbon_tb = QToolBar("Ribbon")
        rt.setObjectName("ribbon")
        rt.setMovable(False)
        rt.toggleViewAction().setVisible(False)
        rt.setContentsMargins(0, 0, 0, 0)
        rt.layout().setContentsMargins(0, 0, 0, 0)
        rt.addWidget(r)
        r.set_group_names(self.a_group_names.isChecked())
        self.addToolBar(rt)
        try:
            tab = int(self.settings.value("ribbon_tab", 0))
        except (TypeError, ValueError):
            tab = 0
        r.setCurrentIndex(max(0, min(tab, r.count() - 1)))
        r.currentChanged.connect(lambda i: self.settings.setValue("ribbon_tab", i))
        if self.settings.value("ribbon_collapsed", "false") == "true":
            r.set_collapsed(True)
        self._apply_ui_mode()

    def _apply_ui_mode(self):
        ribbon = self.a_ribbon.isChecked()
        self._place_quick(ribbon)
        self.ribbon_tb.setVisible(ribbon)
        self.tools_tb.setVisible(not ribbon)
        self.arrange_tb.setVisible(not ribbon)
        self.a_collapse.setEnabled(ribbon)
        self.a_group_names.setEnabled(ribbon)
        self.a_menu_bar.setEnabled(ribbon)

    def _toggle_ribbon(self):
        self.settings.setValue("ui_mode", "ribbon" if self.a_ribbon.isChecked() else "classic")
        self._apply_ui_mode()
        self._apply_icons()

    def _place_quick(self, ribbon):
        """Ribbon: zoom and page boxes go to the status bar, Find to the tab row, and the
        top toolbar row disappears. Classic: everything back in the top toolbar."""
        tb, sb = self.main_tb, self.statusBar()
        in_tb = self._zoom_group_act is not None
        if ribbon and in_tb:
            for act in (self._zoom_group_act, self._nav_group_act, self._search_act):
                tb.removeAction(act)
            self._zoom_group_act = self._nav_group_act = self._search_act = None
            sb.addPermanentWidget(self.nav_group)
            sb.addPermanentWidget(self.view_group)
            sb.addPermanentWidget(self.zoom_group)
            self.ribbon_right.layout().insertWidget(0, self.search)
            self.search.setFixedWidth(170)
        elif not ribbon and not in_tb:
            sb.removeWidget(self.zoom_group)
            sb.removeWidget(self.nav_group)
            sb.removeWidget(self.view_group)
            self.search.setMinimumWidth(0)
            self.search.setMaximumWidth(260)
            self._zoom_group_act = tb.insertWidget(self.a_fit_width, self.zoom_group)
            self._nav_group_act = tb.insertWidget(self._spacer_act, self.nav_group)
            self._search_act = tb.addWidget(self.search)
        for w in (self.zoom_group, self.nav_group, self.search):
            w.show()
        self.view_group.setVisible(ribbon)
        tb.setVisible(not ribbon)
        self.menuBar().setVisible(not ribbon or self.a_menu_bar.isChecked())
        self.menu_btn.setVisible(ribbon and not self.a_menu_bar.isChecked())

    def _toggle_menu_bar(self, on):
        self.settings.setValue("menu_bar", "true" if on else "false")
        self._apply_ui_mode()

    def _toggle_group_names(self, on):
        self.settings.setValue("ribbon_group_names", "true" if on else "false")
        self.ribbon.set_group_names(on)

    def _toggle_collapse(self):
        self.ribbon.set_collapsed(self.a_collapse.isChecked())

    def _ribbon_collapsed(self, on):
        self.a_collapse.setChecked(on)
        self.settings.setValue("ribbon_collapsed", "true" if on else "false")

    def _align_ref(self):
        for key, a in self.align_ref_actions.items():
            if a.isChecked():
                return key
        return "first"

    def _set_align_ref(self, key):
        self.align_ref_actions[key].setChecked(True)
        self.settings.setValue("align_ref", key)
        for box in (getattr(self, "align_ref_box", None), getattr(self, "ribbon_align_box", None)):
            if box is not None:
                box.setCurrentIndex(max(0, box.findData(key)))
        self._update_ui()

    def _align(self, how):
        v = self.view()
        if v is not None:
            v.align(how, self._align_ref())

    def _set_author(self):
        name, ok = QInputDialog.getText(self, "Author name",
                                        "Name recorded on your markups, stamps and comments:",
                                        text=annotations.author())
        if ok:
            annotations.set_author(name.strip())
            self._refresh_props()

    def _toggle_sidebar(self):
        self.dock.setVisible(not self.dock.isVisible())

    def show_manual(self):
        from .manual import ManualDialog
        if getattr(self, "_manual", None) is None:
            self._manual = ManualDialog(self)
        self._manual.show()
        self._manual.raise_()
        self._manual.activateWindow()

    def about(self):
        from . import branding, paths
        dlg = QDialog(self)
        dlg.setWindowTitle("About " + APP_NAME)
        lay = QVBoxLayout(dlg)
        logo = QLabel()
        logo.setPixmap(branding.logo_pixmap(110))
        logo.setStyleSheet("background: #f7f9fa; border-radius: 6px; padding: 6px;")
        lay.addWidget(logo)
        text = QLabel(
            f"Version {__version__}{' (portable)' if paths.is_portable() else ''}. A free, fast PDF reader and editor.<br><br>"
            f"Built on PyMuPDF {pymupdf.VersionBind} (MuPDF) and Qt (PySide6).<br>"
            "Free software under the GNU Affero General Public License 3.0.<br>"
            "Source code and downloads: <a href='https://github.com/keithlyding/KanzonasPDF'>"
            "github.com/keithlyding/KanzonasPDF</a>")
        text.setOpenExternalLinks(True)
        text.setWordWrap(True)
        lay.addWidget(text)
        btns = QDialogButtonBox(QDialogButtonBox.Ok)
        btns.accepted.connect(dlg.accept)
        lay.addWidget(btns)
        dlg.exec()

    def _edit_markup(self, index, xref):
        v = self.view()
        if v:
            v.reveal(index, xref)
            v.edit_annot_text(index, xref)

    def _delete_markup(self, index, xref):
        v = self.view()
        if v:
            v.select_xref(index, xref)
            v.delete_selected()

    # ---- updates ---------------------------------------------------------------
    def _updater(self):
        if getattr(self, "_upd", None) is None:
            from .updates import UpdateChecker
            self._upd = UpdateChecker(self.settings, self)
            self._upd.found.connect(self._update_found)
            self._upd.result.connect(lambda t: QMessageBox.information(self, "Check for updates", t))
        return self._upd

    def start_update_check(self):
        """Called a few seconds after start-up: checks at most once a day, if enabled."""
        self._updater().check_if_due()

    def check_updates(self):
        self.statusBar().showMessage("Checking for updates...", 4000)
        self._updater().check(manual=True)

    def _update_found(self, version, url):
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl
        if self._upd.manual:
            # asked for: answer in a box, like the "up to date" answer
            box = QMessageBox(QMessageBox.Information, "Check for updates",
                              f"KanzonasPDF {version} is available (you have {__version__}).\n\n"
                              + ("Update now downloads it, closes KanzonasPDF, replaces the "
                                 "program files in this folder (your data folder is kept) and "
                                 "starts it again.\n\n" if self._self_update_url() else "")
                              + "Download opens the release page in your browser.", parent=self)
            upd = (box.addButton("Update now", QMessageBox.AcceptRole)
                   if self._self_update_url() else None)
            get = box.addButton("Download", QMessageBox.AcceptRole)
            box.addButton("Later", QMessageBox.RejectRole)
            box.exec()
            if upd is not None and box.clickedButton() is upd:
                self.update_portable()
            elif box.clickedButton() is get:
                QDesktopServices.openUrl(QUrl(url))
            return
        old = getattr(self, "_update_bar", None)
        if old is not None:
            self.statusBar().removeWidget(old)
            old.deleteLater()
        bar = QWidget()
        h = QHBoxLayout(bar)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(QLabel(f"<b>KanzonasPDF {version} is available</b> (you have {__version__})."))
        get = QPushButton("Download")
        get.setToolTip("Open the release page to download the installer or portable zip")
        upd = QPushButton("Update now") if self._self_update_url() else None
        if upd is not None:
            upd.setToolTip("Download the new portable version and replace this one in place "
                           "(your data folder is kept)")
        skip = QPushButton("Skip this version")
        close = QPushButton("Later")

        def done():
            self.statusBar().removeWidget(bar)
            bar.deleteLater()
            self._update_bar = None
        get.clicked.connect(lambda: (QDesktopServices.openUrl(QUrl(url)), done()))
        skip.clicked.connect(lambda: (self.settings.setValue("update_skip", version), done()))
        close.clicked.connect(done)
        if upd is not None:
            upd.clicked.connect(lambda: (done(), self.update_portable()))
        for b in (upd, get, skip, close):
            if b is not None:
                h.addWidget(b)
        self._update_bar = bar
        self.statusBar().clearMessage()      # a status message would keep the notice hidden
        self.statusBar().addWidget(bar)
        bar.show()

    def _self_update_url(self):
        """Download address of the new portable zip when this copy can update itself."""
        from . import updates
        upd = getattr(self, "_upd", None)
        if upd is None or not updates.can_self_update():
            return None
        return updates.asset_url(upd.release)

    def update_portable(self):
        """Portable copy: download the new version, then close and let a script swap the files."""
        import tempfile
        from PySide6.QtWidgets import QProgressDialog
        from . import paths, updates
        url = self._self_update_url()
        if not url:
            return
        app_dir = paths.app_dir()
        dl = updates.PortableUpdater(url, app_dir, self)
        prog = QProgressDialog("Downloading the new KanzonasPDF...", "Cancel", 0, 0, self)
        prog.setWindowTitle("Update")
        prog.setMinimumDuration(0)
        prog.canceled.connect(dl.cancel)

        def progress(got, total):
            if total > 0:
                prog.setMaximum(total)
                prog.setValue(got)

        def failed(msg):
            prog.close()
            QMessageBox.warning(self, "Update", msg + "\n\nYou can still download "
                                "KanzonasPDF-portable.zip from the release page and unzip it "
                                "over this folder.")

        def ready(new):
            import subprocess
            prog.close()
            script = os.path.join(tempfile.gettempdir(), "kanzonas-update.cmd")
            with open(script, "w", encoding="mbcs" if os.name == "nt" else "utf-8") as f:
                f.write(updates.swap_script(os.getpid(), new, app_dir))
            if not self.close():          # the user kept a document open: try again later
                import shutil
                shutil.rmtree(os.path.join(app_dir, updates.STAGING), ignore_errors=True)
                os.remove(script)
                return
            subprocess.Popen(["cmd", "/c", script],
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                             close_fds=True)
            QApplication.quit()
        dl.progress.connect(progress)
        dl.failed.connect(failed)
        dl.ready.connect(ready)
        dl.start()

    # ---- signals from views --------------------------------------------------
    def _on_tab_changed(self, _):
        self._rebuild_thumbs()
        self._refresh_bookmarks()
        self._refresh_layers()
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

    def _pages_unlocked(self):
        """True if the page order may change. While it's locked, ask once whether to unlock:
        the lock covers every command that moves, adds or removes pages, not just dragging."""
        if not self.lock_btn.isChecked():
            return True
        if QMessageBox.question(
                self, "Page order locked",
                "The page order is locked, so pages can't be moved, added or removed.\n\n"
                "Unlock it and continue? (Lock it again with the lock button above the page "
                "list.)") != QMessageBox.Yes:
            return False
        self.lock_btn.setChecked(False)
        return True

    def _set_pages_locked(self, locked):
        self.thumbs.setDragDropMode(QAbstractItemView.NoDragDrop if locked
                                    else QAbstractItemView.InternalMove)
        self.lock_btn.setText("\U0001F512 Locked" if locked else "\U0001F513 Unlocked")
        self.lock_btn.setToolTip("Page order locked: pages can't be moved, added or removed "
                                 "(click to unlock)" if locked else
                                 "Unlocked: drag pages to reorder them; move, insert, delete, "
                                 "cut, paste and duplicate pages (click to lock)")
        self.thumbs.setToolTip("Unlock (button above) to drag pages" if locked
                               else "Drag pages to reorder them")
        self.settings.setValue("pages_locked", "true" if locked else "false")

    @staticmethod
    def _narrowable(panel):
        """Let the Pages panel get narrower than this tab's contents (they scroll sideways)."""
        area = QScrollArea()
        area.setWidget(panel)
        area.setWidgetResizable(True)
        area.setFrameShape(QScrollArea.NoFrame)
        return area

    def _fit_thumbs(self):
        """Thumbnails shrink with the Pages panel (they're drawn at 120 x 160 and scaled down)."""
        w = self.thumbs.viewport().width() - 34          # room for the page number
        w = max(36, min(120, w))
        if self.thumbs.iconSize().width() != w:
            self.thumbs.setIconSize(QSize(w, w * 4 // 3))

    def _on_thumb_moved(self, _parent, start, _end, _dest_parent, dest_row):
        """Thumbnail dragged: apply the same move to the PDF (after Qt finishes the drop)."""
        v = self.view()
        if v is not None:
            QTimer.singleShot(0, lambda: v.move_page_to(start, dest_row))

    # ---- clipboard -----------------------------------------------------------------
    def _clipboard(self, op):
        """Edit > Copy / Cut / Paste / Select all: pages when the page list has the focus,
        otherwise text or markups in the document."""
        v = self.view()
        if v is None:
            return
        if op == "dup" and not self.thumbs.hasFocus():
            n = v.duplicate_selected()
            self.statusBar().showMessage(f"Duplicated {n} markup(s)" if n else
                                         "Select markups (or pages in the page list) first", 3000)
            return
        if self.thumbs.hasFocus():
            if op == "all":
                self.thumbs.selectAll()
            else:
                self._page_clip(op)
            return
        if op == "copy":
            what = v.copy()
            self.statusBar().showMessage({"text": "Text copied", "markups": "Markups copied"}.get(
                what, "Select text or markups first"), 3000)
        elif op == "cut":
            what = v.cut()
            self.statusBar().showMessage({"text": "Text cut", "markups": "Markups cut"}.get(
                what, "Select text or markups first"), 3000)
        elif op == "paste":
            what = v.paste()
            if what is None:
                self.statusBar().showMessage("Nothing to paste", 3000)
        elif op == "all":
            if self.tool != "select":
                self.set_tool("select")
            self.statusBar().showMessage(f"Selected {v.select_all_text()} characters", 3000)

    def _selected_pages(self):
        rows = sorted(self.thumbs.row(i) for i in self.thumbs.selectedItems())
        v = self.view()
        return rows or ([v.current_page()] if v else [])

    def _page_clip(self, op):
        from . import clip
        v = self.view()
        if v is None:
            return
        if op != "copy" and not self._pages_unlocked():
            return
        if op in ("copy", "cut", "dup") and not v.require_permission(pymupdf.PDF_PERM_COPY, "Copying pages"):
            return
        pages = self._selected_pages()
        if op in ("copy", "cut"):
            clip.put("pages", v.pages_bytes(pages))
            if op == "cut" and v.delete_pages(pages):
                self.statusBar().showMessage(f"Cut {len(pages)} page(s)", 3000)
            else:
                self.statusBar().showMessage(f"Copied {len(pages)} page(s)", 3000)
        elif op == "paste":
            kind, data = clip.get()
            if kind != "pages":
                self.statusBar().showMessage("Copy some pages first (Pages > Copy pages)", 3000)
                return
            v.paste_pages(data, max(pages) + 1)
        elif op == "dup":
            v.duplicate_pages(pages)
            self.statusBar().showMessage(f"Duplicated {len(pages)} page(s)", 3000)

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

    THUMB_BUDGET = 0.03         # seconds of thumbnail drawing per turn of the event loop

    def _visible_thumb_rows(self):
        vp = self.thumbs.viewport()
        first = self.thumbs.indexAt(vp.rect().topLeft()).row()
        last = self.thumbs.indexAt(vp.rect().bottomRight()).row()
        if first < 0:
            return []
        if last < 0:
            last = self.thumbs.count() - 1
        return list(range(first, last + 1))

    def _thumb_step(self):
        v = self.view()
        if not v or not self._thumb_queue:
            self._thumb_timer.stop()
            return
        if not self.thumbs.isVisible():
            # the Pages panel is hidden: check back now and then instead of drawing
            self._thumb_timer.setInterval(500)
            return
        self._thumb_timer.setInterval(0)
        # thumbnails you can see first
        queued = set(self._thumb_queue)
        seen = [i for i in self._visible_thumb_rows() if i in queued]
        if seen and self._thumb_queue[0] not in seen:
            first = set(seen)
            self._thumb_queue = seen + [i for i in self._thumb_queue if i not in first]
        start = time.monotonic()
        while self._thumb_queue and time.monotonic() - start < self.THUMB_BUDGET:
            i = self._thumb_queue.pop(0)
            if i >= v.page_count() or i >= self.thumbs.count():
                continue
            page = v.doc[i]
            s = min(120 / page.rect.width, 160 / page.rect.height)
            pm = page.get_pixmap(matrix=pymupdf.Matrix(s, s), annots=True)
            img = QImage(pm.samples, pm.width, pm.height, pm.stride,
                         QImage.Format_RGB888).copy()
            self.thumbs.item(i).setIcon(QIcon(QPixmap.fromImage(img)))
