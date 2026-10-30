"""Main application window: tabs, toolbars, menus, thumbnails sidebar."""

import json
import math
import os
import time
from concurrent.futures import ThreadPoolExecutor

import pymupdf
from PySide6.QtCore import Qt, QSize, QTimer, QEvent, Signal, QMimeData, QPoint
from PySide6.QtGui import (QAction, QActionGroup, QKeySequence, QIcon, QPixmap, QImage,
                           QPainter, QDrag, QMouseEvent, QCursor)
from PySide6.QtWidgets import (QMainWindow, QTabWidget, QTabBar, QToolBar, QFileDialog, QMessageBox,
                               QLineEdit, QSpinBox, QLabel, QComboBox, QListWidget,
                               QListWidgetItem, QDockWidget, QAbstractItemView, QToolButton,
                               QVBoxLayout, QHBoxLayout, QMenu, QProgressDialog,
                               QInputDialog, QWidget, QSizePolicy, QApplication, QScrollArea,
                               QDialog, QFormLayout, QRadioButton, QDialogButtonBox, QCheckBox,
                               QPushButton, QSlider, QAbstractSpinBox, QPlainTextEdit)

from . import __version__, annotations, export, signatures, theme
from .document_view import DocumentView, MIN_ZOOM, MAX_ZOOM
from .i18n import tr
from .properties import PropertiesPanel
from .markups_panel import MarkupsPanel
from .tool_chest import ToolChestPanel, tool_for

APP_NAME = "KanzonasPDF"
APP_TITLE = f"KanzonasPDF v{__version__}"


def _title_base():
    """'KanzonasPDF v0.48', plus ' (portable)' when run from the portable folder."""
    from . import paths
    return tr("{title} (portable)").format(title=APP_TITLE) if paths.is_portable() else APP_TITLE


# file filters: the descriptions are translated, the patterns never
PDF_FILTER = tr("PDF files") + " (*.pdf);;" + tr("All files") + " (*)"


_english_of = {}


def english_name(text):
    """The English a menu or action text was translated from (text itself in English, or when
    it has no translation). Saved shortcuts and the palette's recent commands are keyed by the
    English name, so they survive a change of language."""
    from . import i18n
    if i18n.language() == "en":
        return text
    if not _english_of:
        for en, translated in i18n.load(i18n.language()).items():
            _english_of.setdefault(translated, en)
    return _english_of.get(text, text)


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
    ("select", tr("Select"), "V", tr("Select: drag across text to select it (Ctrl+C copies); click an annotation "
                                     "to move, resize or restyle it (V)")),
    ("hand", tr("Hand"), "H", tr("Pan the page (H)")),
    ("edittext", tr("Edit text"), "Ctrl+E", tr("Edit existing text: click a line of text (Ctrl+E)")),
    ("highlight", tr("Highlight"), "Ctrl+Shift+H", tr("Highlight text")),
    ("underline", tr("Underline"), "Ctrl+Shift+U", tr("Underline text")),
    ("strikeout", tr("Strike"), "Ctrl+Shift+X", tr("Strike out text (Ctrl+Shift+X)")),
    ("comment", tr("Comment"), "C", tr("Comment on text: select text, it's highlighted with a note (C)")),
    ("note", tr("Note"), "N", tr("Sticky note: click where it should go (N)")),
    ("textbox", tr("Text box"), "T", tr("Text box: drag a box or click (T)")),
    ("callout", tr("Callout"), "K", tr("Callout: press on the point, drag to where the text goes (K)")),
    ("rect", tr("Rectangle"), "R", tr("Rectangle (R)")),
    ("ellipse", tr("Ellipse"), "E", tr("Ellipse (E)")),
    ("cloud", tr("Cloud"), "D", tr("Revision cloud: drag a box (D)")),
    ("polygon", tr("Polygon"), "Y", tr("Polygon: click each corner, double-click or Enter to finish (Y)")),
    ("line", tr("Line"), "L", tr("Line (L)")),
    ("arrow", tr("Arrow"), "A", tr("Arrow (A)")),
    ("polyline", tr("Polyline"), "Shift+L", tr("Polyline: click each point, double-click or Enter to finish")),
    ("ink", tr("Pen"), "P", tr("Freehand pen (P)")),
    ("stamp", tr("Stamp"), "M", tr("Stamp (Approved, Draft, ... or your own image): click to place (M)")),
    ("image", tr("Image"), "", tr("Image: drag a box (or click) and pick a picture; it becomes part of "
                                  "the page (move or resize it with Edit objects)")),
    ("attach", tr("Attach file"), "", tr("Attach file: click where its icon goes and pick any file "
                                         "(e.g. a video); it's embedded in the PDF. Double-click to open")),
    ("eraser", tr("Eraser"), "X", tr("Delete the annotation you click (X)")),
    ("signature", tr("Sign"), "G", tr("Place your saved signature: click where it goes, or drag a box "
                                      "to size it (G)")),
    ("initials", tr("Initials"), "I", tr("Place your saved initials: click where they go, or drag a box "
                                         "to size them (I)")),
    ("date", tr("Date"), "Ctrl+;", tr("Place today's date: click where it goes (Ctrl+;)")),
]
FORM_TOOLS = [  # form design tools: drag a box (or click) to add a field
    ("f_text", tr("Text field"), tr("Text field: drag a box")),
    ("f_check", tr("Checkbox"), tr("Checkbox: click or drag")),
    ("f_radio", tr("Option button"), tr("Option (radio) button: click; same group name = pick one")),
    ("f_combo", tr("Dropdown"), tr("Dropdown list: drag a box, then enter the choices")),
    ("f_sign", tr("Signature field"), tr("Signature field: others click it to sign")),
    ("f_initials", tr("Initials field"), tr("Initials field: others click it to put their initials")),
]
MEASURE_TOOLS = [
    ("m_length", tr("Length"), "Shift+M", tr("Measure length: drag from point to point (Shift+M)")),
    ("m_poly", tr("Polylength"), "", tr("Measure along a path: click points, double-click or Enter to finish")),
    ("m_area", tr("Area"), "Shift+A", tr("Measure area and perimeter: click corners, double-click or Enter (Shift+A)")),
    ("m_angle", tr("Angle"), "", tr("Measure an angle: click one end, the corner, then the other end")),
    ("m_radius", tr("Radius"), "", tr("Measure a radius and diameter: drag from the center to the edge")),
    ("m_perimeter", tr("Perimeter"), "", tr("Measure a perimeter: click corners, double-click or Enter to finish")),
    ("m_volume", tr("Volume"), "", tr("Measure volume: click the corners of the area, double-click or Enter; set the depth in Properties")),
    ("m_count", tr("Count"), "Shift+C", tr("Count: click each item; set the group name in Properties (Shift+C)")),
    ("m_calibrate", tr("Calibrate Tape Measure"), "", tr("Calibrate Tape Measure: drag along a known dimension, then type its real length")),
]
EXTRA_TOOLS = [  # tools reached from menus, not the toolbar
    ("erasecontent", tr("Erase &content"), "Shift+E",
     tr("Erase content: drag a box; the page's own text, images and lines inside it are deleted "
        "(lines crossing the edge are cut there). Shift+E")),
    ("addtext", tr("&Add text"), "Shift+T",
     tr("Add text: click where it goes and type; it's written into the page itself (PDF viewers "
        "can't change it; Edit text does). Font, size and color in Properties. Shift+T")),
    ("editobjects", tr("Edit &objects"), "Shift+O",
     tr("Edit objects: click a picture or shape that's part of the page (Ctrl+click or drag a box "
        "for several); drag to move, drag a handle to resize, Delete deletes, right-click to "
        "rotate. Shift+O")),
    ("capture", tr("Ca&pture area"), "Shift+P",
     tr("Capture: drag a box to copy that area; Ctrl+V pastes it here as sharp vector content, "
        "or as a picture into Word or email. Shift+P")),
    ("link", tr("&Links"), "",
     tr("Links: drag a box over what should be clickable, then type a web address or choose a "
        "page; click a link to change or delete it")),
    ("crop", tr("C&rop pages"), "",
     tr("Crop: drag a box around what to keep, then choose this page or all pages; Pages > "
        "Remove crop shows the whole page again")),
    ("redact", tr("&Redact (mark text or area)"), "Shift+R",
     tr("Redact: drag across text, or drag a box over any area; then Apply redactions")),
    ("placeholder", tr("Add signature &placeholder"), "",
     tr("Placeholder: drag a box where a signature or initials go (choose which in Properties); "
        "then Apply all signature placeholders")),
]
EXPORTS = [  # (id, menu label, file filter, extension)
    ("word", tr("Microsoft &Word (.docx)..."), tr("Word document") + " (*.docx)", "docx"),
    ("excel", tr("Microsoft &Excel (.xlsx)..."), tr("Excel workbook") + " (*.xlsx)", "xlsx"),
    ("ppt", tr("Microsoft &PowerPoint (.pptx)..."), tr("PowerPoint presentation") + " (*.pptx)",
     "pptx"),
    ("dxf", tr("&AutoCAD drawing (.dxf)..."), "AutoCAD DXF (*.dxf)", "dxf"),
    ("png", tr("Images (P&NG)..."), tr("PNG image") + " (*.png)", "png"),
    ("jpg", tr("Images (&JPEG)..."), tr("JPEG image") + " (*.jpg)", "jpg"),
    ("txt", tr("Plain &text (.txt)..."), tr("Text file") + " (*.txt)", "txt"),
]
# Toolbar tooltips: what each button does (the shortcut is added automatically)
BUTTON_TIPS = {
    "a_new": tr("Start a new PDF with a blank page"), "a_open": tr("Open a PDF"), "a_save": tr("Save the document"), "a_print": tr("Print"),
    "a_undo": tr("Undo the last change"), "a_redo": tr("Redo what you undid"),
    "a_zoom_in": tr("Zoom in"), "a_zoom_out": tr("Zoom out"),
    "a_fit_width": tr("Zoom so the page fills the window's width"),
    "a_fit_page": tr("Zoom so the whole page fits in the window"),
    "a_ocr": tr("Recognize text (OCR): make scanned pages searchable and selectable"),
    "a_rot_l": tr("Rotate the page counterclockwise"), "a_rot_r": tr("Rotate the page clockwise"),
    "a_grid": tr("Show grid: a grid over the page (spacing in View > Grid settings)"),
    "a_snap_grid": tr("Snap to grid: points jump to the nearest grid intersection (Alt = no snap)"),
    "a_snap_page": tr("Snap to page: points jump to the page's corners, edge middles, center "
                      "and edges (Alt = no snap)"),
    "a_snap_objects": tr("Snap to objects: points jump to markup corners, ends and centers and "
                         "to the drawing's line ends and midpoints (Alt = no snap)"),
    "tool_highlight": tr("Highlight: drag across text"),
    "tool_underline": tr("Underline: drag across text"),
    "tool_strikeout": tr("Strike out: drag across text"),
    "tool_rect": tr("Rectangle: drag a box (Shift = square)"),
    "tool_ellipse": tr("Ellipse: drag a box (Shift = circle)"),
    "tool_cloud": tr("Revision cloud: drag a box (Shift = square)"),
    "tool_line": tr("Line: drag (Shift = 45\u00b0 steps)"),
    "tool_arrow": tr("Arrow: drag from tail to head (Shift = 45\u00b0 steps)"),
    "tool_eraser": tr("Eraser: click a markup to delete it, or drag a box to delete everything inside"),
}
ARRANGE_TIPS = {
    "al_left": tr("Align left edges"), "al_hcenter": tr("Align centers (horizontally)"),
    "al_right": tr("Align right edges"), "al_top": tr("Align top edges"),
    "al_vmiddle": tr("Align middles (vertically)"), "al_bottom": tr("Align bottom edges"),
    "dist_h": tr("Distribute horizontally: equal gaps (3 or more markups)"),
    "dist_v": tr("Distribute vertically: equal gaps (3 or more markups)"),
    "z_front": tr("Bring to front: on top of all other markups"),
    "z_forward": tr("Bring forward one step"), "z_backward": tr("Send backward one step"),
    "z_back": tr("Send to back: behind all other markups"),
}
ZOOM_PRESETS = ["50%", "75%", "100%", "125%", "150%", "200%", "400%", "800%",
                 "1600%", "3200%", "6400%"]
# The slider is logarithmic so 100%–400% still has room, while the top is 6400%.
_SLIDER_STEPS = 1000


def _zoom_to_slider(zoom):
    lo, hi = math.log(MIN_ZOOM * 100), math.log(MAX_ZOOM * 100)
    pct = min(MAX_ZOOM * 100, max(MIN_ZOOM * 100, zoom * 100))
    return int(round((math.log(pct) - lo) / (hi - lo) * _SLIDER_STEPS))


def _slider_to_zoom(val):
    lo, hi = math.log(MIN_ZOOM * 100), math.log(MAX_ZOOM * 100)
    return math.exp(lo + (hi - lo) * (val / _SLIDER_STEPS)) / 100



# every open main window, in the order they were opened, as weak references: the registry
# must not keep a window alive (a window the interpreter frees at exit, after Qt's own
# teardown, corrupts the heap). windows() gives the live ones.
_WINDOW_REFS = []
TAB_MIME = "application/x-kanzonaspdf-tab"
# Panel layout saved with QMainWindow.saveState (which panels are open, their sizes, sides
# and tab order). Bump when a dock or toolbar is renamed or added, so an old layout is ignored.
LAYOUT_VERSION = 1


def _doc_name(v):
    """A document's name on its tab and in the title bar."""
    name = os.path.basename(v.path)
    if v.untitled and getattr(v, "recovered", False):
        # a backup copy opened after a crash, not saved yet (the file name itself stays)
        name = tr("{name} (recovered)").format(name=name)
    return name


def windows():
    """The open main windows, oldest first."""
    out = []
    for ref in list(_WINDOW_REFS):
        w = ref()
        if w is None:
            _WINDOW_REFS.remove(ref)
        else:
            out.append(w)
    return out


def _forget_window(ref):
    if ref in _WINDOW_REFS:
        _WINDOW_REFS.remove(ref)


class _TabBar(QTabBar):
    """Document tabs that can be dragged out of the window (to a second window, on another
    monitor say) or dropped on another KanzonasPDF window's tabs."""

    PULL = 24          # px the pointer must leave the tab bar by before the tab comes out

    def __init__(self, win):
        super().__init__()
        self.win = win
        self.setAcceptDrops(True)
        self._press = None

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._press = self.tabAt(e.position().toPoint())
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        pos = e.position().toPoint()
        if self._press is not None and self._press >= 0 and e.buttons() & Qt.LeftButton and \
                (pos.y() < -self.PULL or pos.y() > self.height() + self.PULL):
            index, self._press = self._press, None
            # end the tab bar's own reorder drag before the tab leaves it
            release = QMouseEvent(QEvent.MouseButtonRelease, e.position(), e.globalPosition(),
                                  Qt.LeftButton, Qt.NoButton, e.modifiers())
            super().mouseReleaseEvent(release)
            self.win.drag_tab_out(index)
            return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        self._press = None
        super().mouseReleaseEvent(e)

    def dragEnterEvent(self, e):
        if e.mimeData().hasFormat(TAB_MIME):
            e.acceptProposedAction()

    def dragMoveEvent(self, e):
        if e.mimeData().hasFormat(TAB_MIME):
            e.acceptProposedAction()

    def dropEvent(self, e):
        if not e.mimeData().hasFormat(TAB_MIME):
            return
        src, index = tab_from_mime(e.mimeData())
        if src is None:
            return
        at = self.tabAt(e.position().toPoint())
        self.win.receive_tab(src, index, at)
        e.acceptProposedAction()


def tab_from_mime(mime):
    """(source window, tab index) a dragged tab stands for, or (None, None)."""
    try:
        wid, index = bytes(mime.data(TAB_MIME)).decode("ascii").split(":")
        src = next(w for w in windows() if str(id(w)) == wid)
        return src, int(index)
    except (ValueError, StopIteration):
        return None, None


class _Tabs(QTabWidget):
    def __init__(self, win):
        super().__init__()
        self.setTabBar(_TabBar(win))


class _FindBox(QLineEdit):
    """The Find box: Enter = next match, Shift+Enter = previous (returnPressed can't tell)."""
    previousRequested = Signal()

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Return, Qt.Key_Enter) and e.modifiers() & Qt.ShiftModifier:
            self.previousRequested.emit()
            return
        super().keyPressEvent(e)

class MainWindow(QMainWindow):
    def __init__(self, primary=None):
        """primary (the default): the app's main window, which owns the session (closing it
        closes the others). A window a tab was pulled out into is not: closing its last
        tab closes it."""
        super().__init__()
        from . import paths
        self.settings = paths.settings()
        self.primary = True if primary is None else bool(primary)
        import weakref
        ref = weakref.ref(self)
        _WINDOW_REFS.append(ref)
        self.destroyed.connect(lambda *_: _forget_window(ref))
        if not self.primary:
            self.setAttribute(Qt.WA_DeleteOnClose)
        self.setWindowTitle(_title_base())
        self.resize(1300, 900)
        self.setAcceptDrops(True)
        # start with the mouse mode's tool: the Hand (scroll by dragging, like most viewers)
        # or Select (Standard and CAD)
        from . import mouse_modes
        mouse_modes.apply(self.settings)
        self.tool = mouse_modes.default_tool(mouse_modes.mode(self.settings))
        self._last_basic_tool = self.tool
        self._sig_cache = {}            # kind -> png, for this run of the app only

        self.tabs = _Tabs(self)
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.setDocumentMode(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self.tabs.tabBar().setContextMenuPolicy(Qt.CustomContextMenu)
        self.tabs.tabBar().customContextMenuRequested.connect(self._tab_menu)
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
        self._restore_layout()

    def _restore_layout(self):
        """Bring back the panels as they were when KanzonasPDF was last closed: which ones
        were open (Pages, Properties, Tool chest, Markups list), their sizes and sides, and
        which of Properties / Tool chest was in front."""
        state = self.settings.value("window_state")
        if state is None or not self.restoreState(state, LAYOUT_VERSION):
            return
        # the toolbars follow the ribbon / classic choice and the panel strip option, not the
        # saved layout (they normally agree; this keeps them right if a setting was changed)
        self._apply_ui_mode()
        self._toggle_panel_strip(self.a_panel_strip.isChecked())
        self.split_dock.hide()          # a second view belongs to a document; start without

    # ---- construction -----------------------------------------------------
    def _build_panel_strip(self):
        """PDF-XChange style icon strip on the left edge: click an icon to open that panel,
        click it again to fold the panel away (the strip stays)."""
        from . import theme
        ps = self.panel_strip = QToolBar(tr("Panels"))
        ps.setObjectName("panel_strip")
        ps.setMovable(False)
        ps.setIconSize(QSize(18, 18))
        ps.setOrientation(Qt.Vertical)
        ps.toggleViewAction().setVisible(False)
        self.addToolBar(Qt.LeftToolBarArea, ps)
        self.strip_actions = []
        self._strip_icons = []          # (action, icon name), re-tinted when the theme changes
        for i, (label, icon, tip) in enumerate((
                (tr("Pages"), "file-multiple-outline",
                 tr("Pages panel (click again to fold it away)")),
                (tr("Bookmarks"), "bookmark-outline",
                 tr("Bookmarks panel (click again to fold it away)")),
                (tr("Layers"), "layers-outline", tr("Layers panel (click again to fold it away)")),
                (tr("Objects"), "shape-outline",
                 tr("Objects panel (click again to fold it away)")))):
            a = QAction(theme.icon_named(icon), label, self, checkable=True)
            self._strip_icons.append((a, icon))
            a.setToolTip(tip)
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
        self.a_panel_strip = QAction(tr("Show panel &strip (left edge)"), self, checkable=True)
        self.a_panel_strip.setToolTip(tr("Icons on the left edge that open and fold the Pages, "
                                         "Bookmarks, Layers and Objects panels"))
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
        self.a_new = self._act(tr("&New PDF..."), self.new_pdf, QKeySequence.New,
                               tr("Start a new PDF with a blank page (it asks for the page size)"))
        self.a_open = self._act(tr("&Open..."), self.open_dialog, QKeySequence.Open)
        self.a_save = self._act(tr("&Save"), self.save, QKeySequence.Save)
        self.a_save_as = self._act(tr("Save &As..."), self.save_as, QKeySequence.SaveAs)
        self.a_print = self._act(tr("&Print..."), self.print_doc, QKeySequence.Print)
        self.a_close = self._act(tr("&Close tab"), lambda: self.close_tab(self.tabs.currentIndex()),
                                 QKeySequence.Close)
        self.a_exit = self._act(tr("E&xit"), self.close, "Alt+F4")
        self.a_detach = self._act(tr("Move tab to new &window"), self.detach_current, "Ctrl+Shift+N",
                                  tip=tr("Open this document in its own window (for a second "
                                         "monitor); drag the tab out of the tab bar does the same"))
        self.a_prefs = self._act(tr("Pre&ferences..."), self.preferences, "Ctrl+K",
                                 tip=tr("All the remembered options in one place (Ctrl+K)"))
        self.a_undo = self._act(tr("&Undo"), lambda: v() and v().undo(), QKeySequence.Undo)
        self.a_redo = self._act(tr("&Redo"), lambda: v() and v().redo(), QKeySequence.Redo)
        self.a_find = self._act(tr("&Find"), self._focus_search, QKeySequence.Find)
        self.a_replace = self._act(tr("R&eplace text..."), self.replace_text, "Ctrl+H",
                                   tip=tr("Find text in the page and replace it (Ctrl+H)"))
        # clipboard: text, markups, or pages (when the page list has the focus)
        self.a_copy = self._act(tr("&Copy"), lambda: self._clipboard("copy"), QKeySequence.Copy,
                                tip=tr("Copy the selected text, markups, or pages (in the page list)"))
        self.a_cut = self._act(tr("Cu&t"), lambda: self._clipboard("cut"), QKeySequence.Cut,
                               tip=tr("Cut the selected text (removes it from the page), markups or pages"))
        self.a_paste = self._act(tr("&Paste"), lambda: self._clipboard("paste"), QKeySequence.Paste,
                                 tip=tr("Paste markups, pages, a picture, or text (as a text box) "
                                        "where the mouse is"))
        self.a_select_all = self._act(tr("Select &all text"), lambda: self._clipboard("all"),
                                      QKeySequence.SelectAll,
                                      tip=tr("Select all the text on the current page (or all pages "
                                             "in the page list)"))
        self.a_duplicate = self._act(tr("&Duplicate"), lambda: self._clipboard("dup"), "Ctrl+D",
                                     tip=tr("Duplicate the selected markups, or the selected pages "
                                            "when the page list has the focus"))
        self.a_dup_pages = self._act(tr("D&uplicate pages"), lambda: self._page_clip("dup"),
                                     tip=tr("Duplicate the selected pages (page list must be unlocked)"))
        self.a_copy_pages = self._act(tr("Copy pa&ges"), lambda: self._page_clip("copy"))
        self.a_cut_pages = self._act(tr("Cut pages"), lambda: self._page_clip("cut"))
        self.a_paste_pages = self._act(tr("Paste pages after selected"), lambda: self._page_clip("paste"))
        self.a_find_next = self._act(tr("Find next"), lambda: self._find(False), QKeySequence.FindNext)
        self.a_find_prev = self._act(tr("Find previous"), lambda: self._find(True),
                                     QKeySequence.FindPrevious)
        self.a_zoom_in = self._act(tr("Zoom &in"), lambda: v() and v().zoom_in(), QKeySequence.ZoomIn)
        self.a_zoom_out = self._act(tr("Zoom &out"), lambda: v() and v().zoom_out(),
                                    QKeySequence.ZoomOut)
        self.a_fit_width = self._act(tr("Fit &width"), lambda: v() and v().fit_width(), "Ctrl+2")
        self.a_fit_page = self._act(tr("Fit &page"), lambda: v() and v().fit_page(), "Ctrl+0")
        self.a_actual = self._act(tr("&Actual size"), lambda: v() and v().set_zoom(1.0), "Ctrl+1")
        self.a_sidebar = self._act(tr("Page &thumbnails"), self._toggle_sidebar, "F4")
        self.a_sidebar.setCheckable(True)
        self.a_sidebar.setChecked(True)
        # Ctrl+Shift+Plus/Minus are caught by an event filter (see eventFilter): "+" needs
        # Shift on most keyboards, so normal shortcuts would collide with zoom (Ctrl++).
        # The key names are shown in the menu text after a tab.
        self.a_rot_l = self._act(tr("Rotate page &left\tCtrl+Shift+-"), lambda: self._page_op("rot", -90),
                                 tip=tr("Rotate page counter-clockwise (Ctrl+Shift+Minus)"))
        self.a_rot_r = self._act(tr("Rotate page &right\tCtrl+Shift++"), lambda: self._page_op("rot", 90),
                                 tip=tr("Rotate page clockwise (Ctrl+Shift+Plus)"))
        self.a_rot_l.setIconText(tr("Rotate left"))
        self.a_rot_r.setIconText(tr("Rotate right"))
        self.a_del_page = self._act(tr("&Delete pages"), lambda: self._page_op("del"),
                                    tip=tr("Delete the pages selected in the page list (Ctrl+click "
                                           "or Shift+click for several), or the current page; "
                                           "Delete in the page list does it too"))
        self.a_move_up = self._act(tr("Move page &up"), lambda: self._page_op("move", -1),
                                   "Ctrl+Shift+Up", tr("Move current page up (Ctrl+Shift+Up)"))
        self.a_move_down = self._act(tr("Move page do&wn"), lambda: self._page_op("move", 1),
                                     "Ctrl+Shift+Down", tr("Move current page down (Ctrl+Shift+Down)"))
        self.a_insert_pdf = self._act(tr("&Insert pages from file..."), self.insert_from_file)
        self.a_combine = self._act(tr("Co&mbine files..."), self.combine_files,
                                   tip=tr("Combine several PDFs, in the order you choose, into one "
                                          "new PDF"))
        self.a_from_images = self._act(tr("Create PDF from &images..."), self.pdf_from_images,
                                       tip=tr("Make a PDF from pictures: scans, phone photos "
                                              "(JPG, PNG, TIFF...), one page each"))
        self.a_insert_blank = self._act(tr("Insert &blank page after current"),
                                        lambda: self._page_op("blank"))
        self.a_extract = self._act(tr("&Extract pages to new file..."), self.extract_pages)
        self.a_sheet_links = self._act(tr("Link sheet &callouts..."), self.link_sheet_callouts,
                                       tip=tr("Read the sheet numbers from the title blocks and make "
                                              "every callout, note and index line that names a sheet a "
                                              "link to it (also to PDFs in the same folder)"))
        self.a_uncrop = self._act(tr("Remove cro&p..."), lambda: self._page_op("uncrop"),
                                  tip=tr("Show the whole page again on this page or all pages"))
        self.a_ocr = self._act(tr("Recognize text (&OCR)..."), self.ocr,
                               tip=tr("Make scanned pages searchable and selectable"))
        self.a_props = self._act(tr("&Properties panel"), self._toggle_props, "F6")
        self.a_props.setCheckable(True)
        self.a_props.setChecked(True)
        self.a_cards = self._act(tr("Show &comment boxes"), self._toggle_cards)
        self.a_cards.setCheckable(True)
        self.a_cards.setChecked(self.settings.value("comment_boxes", "true") != "false")
        self.a_setup_sig = self._act(tr("Set up my &signature..."), lambda: self.setup_signature("signature"))
        self.a_setup_init = self._act(tr("Set up my &initials..."), lambda: self.setup_signature("initials"))
        self.a_security = self._act(tr("Security &properties (passwords && permissions)..."),
                                    self.security_properties,
                                    tip=tr("Require a password to open, and/or restrict printing, "
                                           "editing and copying (AES-256)"))
        self.a_remove_security = self._act(tr("&Remove security"), self.remove_security)
        self.a_sanitize = self._act(tr("Sa&nitize document..."), self.sanitize_document,
                                    tip=tr("Remove hidden data: document information, scripts, "
                                           "attached files, hidden text..."))
        self.a_clear_sigs = self._act(tr("&Clear all digital signatures..."), self.clear_signatures)
        self.a_timestamp = self._act(tr("&Timestamp document..."), self.timestamp_document,
                                     tip=tr("Add a trusted timestamp from a time server: proves the "
                                            "file existed, unchanged, at that time"))
        self.a_multi_sign = self._act(tr("&Multi-place signature or initials..."), self.multi_place)
        self.a_apply_placeholders = self._act(tr("&Apply all signature placeholders"),
                                              self.apply_placeholders)
        self.a_apply_sel_redact = self._act(tr("Apply &selected redactions"),
                                            lambda: self._apply_selected_redactions())
        # review
        self.a_next_markup = self._act(tr("&Next comment"), lambda: v() and v().goto_markup(1),
                                       "Alt+Down", tip=tr("Go to and select the next comment or markup"))
        self.a_prev_markup = self._act(tr("&Previous comment"), lambda: v() and v().goto_markup(-1),
                                       "Alt+Up", tip=tr("Go to and select the previous comment or markup"))
        self.a_show_markups = self._act(tr("&Show markups"), self._toggle_show_markups,
                                        tip=tr("Hide every comment and markup to see the page as if "
                                               "unmarked (nothing is deleted)"))
        self.a_show_markups.setCheckable(True)
        self.a_show_markups.setChecked(True)
        self.a_delete_markups = self._act(tr("&Delete comments..."), self.delete_comments)
        self.a_flatten_markups = self._act(tr("&Flatten comments..."), self.flatten_comments,
                                           tip=tr("Make comments and markups part of the page; "
                                                  "form fields stay fillable"))
        self.a_hl_fields = self._act(tr("&Highlight form fields"), self._toggle_hl_fields,
                                     tip=tr("Shade fillable form fields so they're easy to find "
                                            "(on screen only)"))
        self.a_hl_fields.setCheckable(True)
        self.a_hl_fields.setChecked(self.settings.value("highlight_fields", "true") != "false")
        DocumentView.highlight_fields = self.a_hl_fields.isChecked()
        self.a_next_field = self._act(tr("&Next form field\tTab"),
                                      lambda: self.view() and self.view().next_field(),
                                      tip=tr("Go to the next form field (Tab; Space or Enter fills it)"))
        self.a_prev_field = self._act(tr("&Previous form field\tShift+Tab"),
                                      lambda: self.view() and self.view().next_field(back=True),
                                      tip=tr("Go to the previous form field (Shift+Tab)"))
        self.a_unlock = self._act(tr("&Unlock with password..."), self.unlock_doc)
        self.export_actions = []
        for eid, label, _flt, _ext in EXPORTS:
            a = self._act(label, lambda _=False, e=eid: self.export_as(e))
            self.export_actions.append(a)
        self.a_chest = self._act(tr("Tool &chest"), self._toggle_chest, "F8")
        self.a_chest.setCheckable(True)
        self.a_compare = self._act(tr("&Compare documents..."), self.compare_documents,
                                   tip=tr("Compare this document with another revision"))
        self.a_header = self._act(tr("&Header && footer, page numbers, Bates..."), self.header_footer)
        self.a_watermark = self._act(tr("&Watermark..."), self.watermark)
        self.a_background = self._act(tr("Bac&kground..."), self.background,
                                      tip=tr("Put a color, gradient or picture behind the page "
                                             "content, on this page or the whole document"))
        self.a_remove_bg = self._act(tr("Remove back&ground..."), self.remove_background)
        self.a_remove_wm = self._act(tr("Remove water&marks..."), self.remove_watermarks,
                                     tip=tr("Remove watermarks added by KanzonasPDF, Adobe Acrobat, "
                                            "PDF-XChange and other apps that mark them as watermarks"))
        self.a_compress = self._act(tr("&Compress (save a smaller copy)..."), self.compress)
        self.a_attachments = self._act(tr("A&ttachments..."), self.show_attachments,
                                       tip=tr("Files embedded in this PDF: open, save or delete them"))
        self.a_bookmarks = self._act(tr("&Bookmarks"), self._show_bookmarks, "F9")
        self.a_search_redact = self._act(tr("&Search && redact..."), self.search_redact)
        self.a_apply_redact = self._act(tr("&Apply redactions..."), self.apply_redactions)
        self.a_digisign = self._act(tr("&Digitally sign with certificate..."), self.digital_sign)
        self.a_sig_details = self._act(tr("Digital signature &details..."), self.signature_details)
        self.a_set_scale = self._act(tr("Set &scale..."), self.set_scale)
        self.a_sheet_scales = self._act(tr("Read scales from &title blocks"), self.read_sheet_scales,
                                        tip=tr("Set each page's scale to what its title block says "
                                               "(1/4\" = 1'-0\", 1:50...), for the whole document"))
        self.a_measure_summary = self._act(tr("Measurement &summary..."), self.measure_summary)
        self.a_labels = self._act(tr("Show text &labels on toolbars"), self._toggle_labels)
        self.a_labels.setCheckable(True)
        self.a_labels.setChecked(self.settings.value("toolbar_labels", "false") == "true")
        self.theme_group = QActionGroup(self)
        self.theme_actions = {}
        for key, label in (("system", tr("Match &Windows")), ("light", tr("&Light")),
                           ("dark", tr("&Dark"))):
            a = QAction(label, self, checkable=True)
            a.triggered.connect(lambda _=False, k=key: self.set_theme(k))
            self.theme_group.addAction(a)
            self.theme_actions[key] = a
        self.theme_actions[self.settings.value("theme", "system")].setChecked(True)
        # Mouse mode: Standard, Hand or CAD (mouse_modes.py), each with its own options
        self.mouse_group = QActionGroup(self)
        self.a_mouse_standard = self._act(tr("Mouse: &Standard (arrow, the wheel scrolls)"),
                                          lambda: self.set_mouse_mode("standard"),
                                          tip=tr("Select text and markups with the arrow; the "
                                                 "wheel scrolls, Ctrl+wheel zooms"))
        self.a_mouse_hand = self._act(tr("Mouse: &Hand (drag the page)"),
                                      lambda: self.set_mouse_mode("hand"),
                                      tip=tr("Drag to move the page; click a markup to select "
                                             "it; the wheel scrolls"))
        self.a_cad_mouse = self._act(tr("Mouse: &CAD (wheel zooms, hold wheel to pan)"),
                                     lambda: self.set_mouse_mode("cad", toggle=True), "F11",
                                     tip=tr("Like AutoCAD: the scroll wheel zooms at the cursor; "
                                            "hold the wheel down and drag to move the sheet; a "
                                            "plus cursor; click, move, click for a box (left to "
                                            "right selects what's inside, right to left what it "
                                            "touches) or hold the button for a lasso; the CAD "
                                            "tab's commands (F11 switches CAD on and off)"))
        for a in (self.a_mouse_standard, self.a_mouse_hand, self.a_cad_mouse):
            a.setCheckable(True)
            self.mouse_group.addAction(a)
        self.a_free_pan = self._act(tr("&Free page movement (drag the page past its edges)"),
                                    lambda: self._toggle_mouse_option("free_pan",
                                                                      self.a_free_pan),
                                    tip=tr("The Hand tool (or the held wheel) drags the page "
                                           "anywhere, up, down and sideways, even when the "
                                           "whole page fits in the window"))
        self.a_free_pan.setCheckable(True)
        self.a_page_wheel = self._act(tr("Scroll &one page per wheel step"),
                                      lambda: self._toggle_mouse_option("page_wheel",
                                                                        self.a_page_wheel),
                                      tip=tr("When the whole page fits in the window, each step "
                                             "of the scroll wheel moves to the next or previous "
                                             "page"))
        self.a_page_wheel.setCheckable(True)
        self._sync_mouse_actions()
        self.a_night = self._act(tr("&Night mode (white lines on black)"), self._toggle_night, "F12",
                                 tip=tr("Draw the pages like a CAD screen: lightness inverted, colors "
                                        "kept (black lines turn white, red stays red). Printing and "
                                        "export are not affected (F12)"))
        self.a_night.setCheckable(True)
        self.a_night.setChecked(self.settings.value("night_mode", "false") == "true")
        DocumentView.night_mode = self.a_night.isChecked()
        self.a_thin_lines = self._act(tr("Enhance &thin lines"), self._toggle_thin_lines,
                                      tip=tr("Draw every line at least one screen pixel wide, so "
                                             "the hairlines of CAD drawings stay dark and legible "
                                             "when zoomed out. Printing and export keep the true "
                                             "line widths"))
        self.a_thin_lines.setCheckable(True)
        self.a_thin_lines.setChecked(self.settings.value("thin_lines", "true") == "true")
        DocumentView.thin_lines = self.a_thin_lines.isChecked()
        from . import autosave, measure
        measure.configure(self.settings)
        try:
            minutes = int(self.settings.value("autosave_minutes", 5))
        except (TypeError, ValueError):
            minutes = 5
        self.autosave = autosave.Autosaver(self, minutes)
        annotations.forget_saved_transient()    # an Edit text size saved before 1.2.1
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
        self.a_grid = self._act(tr("Show &grid"), self._apply_grid_settings,
                                tip=tr("Show a grid over the page (spacing in Grid settings)"))
        self.a_snap_grid = self._act(tr("Snap to g&rid"), self._apply_grid_settings,
                                     tip=tr("Points you draw or drag jump to the nearest grid "
                                            "intersection (hold Alt to place freely)"))
        self.a_snap_objects = self._act(tr("Snap to &objects"), self._apply_grid_settings,
                                        tip=tr("Points jump to nearby markup corners, ends and centers "
                                               "and to the drawing's line ends and midpoints "
                                               "(hold Alt to place freely)"))
        self.a_snap_page = self._act(tr("Snap to &page"), self._apply_grid_settings,
                                     tip=tr("Points jump to the page's corners, the middles of its "
                                            "edges, its center and its edges (hold Alt to place "
                                            "freely)"))
        for a, key in ((self.a_grid, "grid_on"), (self.a_snap_grid, "snap_grid"),
                       (self.a_snap_objects, "snap_objects"), (self.a_snap_page, "snap_page")):
            a.setCheckable(True)
            a.setChecked(self.settings.value(key, "false") == "true")
        self.a_grid_settings = self._act(tr("Grid &settings..."), self.grid_settings)
        self._apply_grid_settings(save=False)
        self.a_split = self._act(tr("&Split view"), self._toggle_split, "F10")
        self.a_split.setCheckable(True)
        self.a_shortcuts = self._act(tr("&Keyboard shortcuts..."), self.edit_shortcuts)
        self.a_markups = self._act(tr("&Markups list"), self._toggle_markups, "F7")
        self.a_markups.setCheckable(True)
        self.a_author = self._act(tr("&Author name for markups..."), self._set_author)
        self.a_spell = self._act(tr("Check &spelling"), self._toggle_spelling,
                                 tip=tr("Underline misspelled words while you type in comments, "
                                        "text boxes and Edit text; right-click one for corrections"))
        self.a_spell.setCheckable(True)
        from . import spelling
        self.a_spell.setChecked(spelling.enabled())
        # arrange: align / distribute / stacking order of the selected markups
        self.arrange_actions = {}
        for key, label, sc, fn in (
                ("al_left", tr("Align &left"), "", lambda: self._align("left")),
                ("al_hcenter", tr("Align &centers (horizontally)"), "", lambda: self._align("hcenter")),
                ("al_right", tr("Align &right"), "", lambda: self._align("right")),
                ("al_top", tr("Align &top"), "", lambda: self._align("top")),
                ("al_vmiddle", tr("Align &middles (vertically)"), "", lambda: self._align("vmiddle")),
                ("al_bottom", tr("Align &bottom"), "", lambda: self._align("bottom")),
                ("dist_h", tr("Distribute &horizontally"), "", lambda: v() and v().distribute("h")),
                ("dist_v", tr("Distribute &vertically"), "", lambda: v() and v().distribute("v")),
                ("z_front", tr("Bring to &front"), "Ctrl+Shift+]", lambda: v() and v().arrange("front")),
                ("z_forward", tr("Bring &forward"), "Ctrl+]", lambda: v() and v().arrange("forward")),
                ("z_backward", tr("Send bac&kward"), "Ctrl+[", lambda: v() and v().arrange("backward")),
                ("z_back", tr("Send to bac&k"), "Ctrl+Shift+[", lambda: v() and v().arrange("back"))):
            self.arrange_actions[key] = self._act(label, fn, sc or None)
        self.a_ribbon = self._act(tr("&Ribbon (instead of toolbars)"), self._toggle_ribbon,
                                  tip=tr("Office-style ribbon with labeled tabs; untick for the "
                                         "classic compact toolbars"))
        self.a_ribbon.setCheckable(True)
        self.a_ribbon.setChecked(self.settings.value("ui_mode", "ribbon") == "ribbon")
        self.a_collapse = self._act(tr("&Collapse ribbon"), self._toggle_collapse, "Ctrl+F1",
                                    tip=tr("Show only the ribbon's tab names (double-click a tab "
                                           "does the same)"))
        self.a_collapse.setCheckable(True)
        self.a_group_names = QAction(tr("Show &group names on ribbon"), self, checkable=True)
        self.a_group_names.setToolTip(tr("Name each group of ribbon buttons (makes the ribbon taller)"))
        self.a_group_names.setChecked(self.settings.value("ribbon_group_names", "false") == "true")
        self.a_group_names.toggled.connect(self._toggle_group_names)
        self.a_menu_bar = QAction(tr("Show &menu bar"), self, checkable=True)
        self.a_menu_bar.setShortcut(QKeySequence("Ctrl+Shift+M"))
        self.a_menu_bar.setToolTip(tr("With the ribbon, hide the menu bar to save space; the "
                                      "\u2630 button at the right of the ribbon tabs has every menu"))
        self.a_menu_bar.setChecked(self.settings.value("menu_bar", "true") != "false")
        self.a_menu_bar.toggled.connect(self._toggle_menu_bar)
        self.addAction(self.a_menu_bar)            # shortcut works while the menu bar is hidden
        self.a_lock = self._act(tr("&Lock selected"), lambda: self._lock_selected(), "Ctrl+L",
                                tip=tr("Lock the selected markups: they can't be clicked, moved or "
                                       "selected on the page (unlock in the Objects panel)"))
        self.a_unlock_all = self._act(tr("&Unlock all markups"), lambda: self._unlock_all())
        self.align_ref_group = QActionGroup(self)
        self.align_ref_actions = {}
        # (menu text, the shorter text in the toolbar's "align to" box)
        self._align_ref_short = {}
        for key, label, short in (
                ("first", tr("Align to first selected"), tr("to first selected")),
                ("last", tr("Align to last selected"), tr("to last selected")),
                ("selection", tr("Align to whole selection"), tr("to whole selection")),
                ("page", tr("Align to page"), tr("to page"))):
            a = QAction(label, self, checkable=True)
            a.triggered.connect(lambda _=False, k=key: self._set_align_ref(k))
            self.align_ref_group.addAction(a)
            self.align_ref_actions[key] = a
            self._align_ref_short[key] = short
        ref = self.settings.value("align_ref", "first")
        self.align_ref_actions.get(ref, self.align_ref_actions["first"]).setChecked(True)
        self.a_flatten = self._act(tr("&Flatten..."), self.flatten,
                                   tip=tr("Make annotations and form fields a permanent part of the page"))
        self.a_delete_annot = self._act(tr("Delete selected annotation"),
                                        lambda: v() and v().delete_selected())
        self.a_manual = self._act(tr("&User manual"), self.show_manual, "F1")
        self.a_palette = self._act(tr("Command &palette..."), self.show_palette, "Ctrl+Shift+P",
                                   tip=tr("Type a few letters of any command or tool and run it "
                                          "from the list (Ctrl+Shift+P)"))
        self.a_about = self._act(tr("&About"), self.about)
        self.a_feedback = self._act(tr("&Report a problem or suggest an idea..."), self.open_feedback,
                                    tip=tr("Open KanzonasPDF's GitHub page for bug reports and "
                                           "ideas in your browser"))
        self.a_check_updates = self._act(tr("&Check for updates..."), self.check_updates,
                                         tip=tr("Ask GitHub whether a newer KanzonasPDF is out"))
        self.a_auto_updates = QAction(tr("Check for updates &automatically"), self, checkable=True)
        self.a_auto_updates.setToolTip(tr("Once a day at start-up; only tells you, never installs"))
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
        m = mb.addMenu(tr("&File"))
        m.addActions([self.a_new, self.a_open])
        self.recent_menu = m.addMenu(tr("Open &recent"))
        self._rebuild_recent()
        m.addActions([self.a_save, self.a_save_as])
        m.addActions([self.a_combine, self.a_from_images])
        em = m.addMenu(tr("&Export to"))
        em.addActions(self.export_actions)
        m.addAction(self.a_compare)
        m.addSeparator()
        m.addAction(self.a_print)
        m.addSeparator()
        m.addAction(self.a_prefs)
        m.addSeparator()
        m.addActions([self.a_close, self.a_exit])
        m = mb.addMenu(tr("&Edit"))
        m.addActions([self.a_undo, self.a_redo])
        m.addSeparator()
        m.addActions([self.a_cut, self.a_copy, self.a_paste, self.a_duplicate, self.a_select_all])
        m.addSeparator()
        m.addAction(self.a_delete_annot)
        m.addSeparator()
        m.addActions([self.a_author, self.a_spell])
        m.addSeparator()
        m.addActions([self.a_find, self.a_find_next, self.a_find_prev, self.a_replace])
        m = self.view_menu = mb.addMenu(tr("&View"))
        m.addActions([self.a_zoom_in, self.a_zoom_out, self.a_actual, self.a_fit_width,
                      self.a_fit_page])
        m.addSeparator()
        m.addActions([self.a_sidebar, self.a_props, self.a_chest, self.a_markups, self.a_cards])
        m.addSeparator()
        m.addAction(self.a_split)
        m.addAction(self.a_detach)
        m.addActions([self.a_mouse_standard, self.a_mouse_hand, self.a_cad_mouse])
        m.addAction(self.a_free_pan)
        m.addAction(self.a_page_wheel)
        m.addAction(self.a_night)
        m.addAction(self.a_thin_lines)
        m.addAction(self.a_hl_fields)
        m.addSeparator()
        m.addActions([self.a_grid, self.a_snap_grid, self.a_snap_objects, self.a_snap_page,
                      self.a_grid_settings])
        m.addSeparator()
        tm = m.addMenu(tr("&Theme"))
        tm.addActions(list(self.theme_actions.values()))
        m.addAction(self.a_labels)
        m.addActions([self.a_ribbon, self.a_collapse, self.a_group_names, self.a_menu_bar])
        m.addSeparator()
        m.addAction(self.a_shortcuts)
        m = mb.addMenu(tr("&Arrange"))
        acts = self.arrange_actions
        m.addActions([acts[k] for k in ("al_left", "al_hcenter", "al_right")])
        m.addActions([acts[k] for k in ("al_top", "al_vmiddle", "al_bottom")])
        rm = m.addMenu(tr("Align &relative to"))
        rm.addActions(list(self.align_ref_actions.values()))
        m.addSeparator()
        m.addActions([acts["dist_h"], acts["dist_v"]])
        m.addSeparator()
        m.addActions([acts[k] for k in ("z_front", "z_forward", "z_backward", "z_back")])
        m.addSeparator()
        m.addActions([self.a_lock, self.a_unlock_all])
        m.addSeparator()
        hint = m.addAction(tr("Ctrl+click or drag a box with Select to pick several markups"))
        hint.setEnabled(False)
        m = mb.addMenu(tr("&Tools"))
        m.addActions(self.tool_group.actions())
        m.addSeparator()
        m.addAction(self.a_props)
        m.addSeparator()
        m.addActions([self.a_ocr, self.a_flatten])
        m = mb.addMenu(tr("&Document"))
        m.addActions([self.a_header, self.a_watermark, self.a_remove_wm, self.a_background,
                      self.a_remove_bg])
        m.addSeparator()
        m.addAction(self.a_bookmarks)
        m.addAction(self.a_attachments)
        m.addSeparator()
        rm = m.addMenu(tr("&Redaction"))
        rm.addActions([self.tool_actions["redact"], self.a_search_redact,
                       self.a_apply_sel_redact, self.a_apply_redact])
        m.addSeparator()
        m.addActions([self.a_compress, self.a_compare, self.a_flatten])
        m = mb.addMenu(tr("&Measure"))
        m.addActions([self.tool_actions[t[0]] for t in MEASURE_TOOLS])
        m.addSeparator()
        m.addActions([self.a_set_scale, self.a_sheet_scales, self.a_measure_summary])
        m = mb.addMenu(tr("&Review"))
        m.addActions([self.tool_actions["comment"], self.tool_actions["note"]])
        m.addSeparator()
        m.addActions([self.a_prev_markup, self.a_next_markup, self.a_markups])
        m.addSeparator()
        m.addActions([self.a_show_markups, self.a_cards])
        m.addSeparator()
        m.addActions([self.a_delete_markups, self.a_flatten_markups])
        m = mb.addMenu(tr("&Protect"))
        m.addActions([self.tool_actions["signature"], self.tool_actions["initials"],
                      self.tool_actions["date"], self.a_multi_sign])
        # setting up (or replacing) your signature / initials lives in File > Preferences >
        # You: here it read like "add my signature to this document"
        m.addSeparator()
        m.addActions([self.tool_actions["placeholder"], self.a_apply_placeholders])
        m.addSeparator()
        m.addActions([self.a_digisign, self.a_timestamp, self.a_sig_details, self.a_clear_sigs])
        m.addSeparator()
        rm = m.addMenu(tr("Re&daction"))
        rm.addActions([self.tool_actions["redact"], self.a_search_redact,
                       self.a_apply_sel_redact, self.a_apply_redact])
        m.addAction(self.a_sanitize)
        m.addSeparator()
        m.addActions([self.a_security, self.a_remove_security, self.a_unlock])
        m = mb.addMenu(tr("F&orms"))
        m.addActions([self.tool_actions[t] for t, _, _ in FORM_TOOLS])
        m.addSeparator()
        m.addAction(self.a_hl_fields)
        m.addActions([self.a_next_field, self.a_prev_field])
        hint = m.addAction(tr("To fill in a form: use Select or Hand and click a field"))
        hint.setEnabled(False)
        m = mb.addMenu(tr("&Pages"))
        m.addActions([self.a_copy_pages, self.a_cut_pages, self.a_paste_pages, self.a_dup_pages])
        m.addSeparator()
        m.addActions([self.a_rot_l, self.a_rot_r])
        m.addActions([self.tool_actions["crop"], self.a_uncrop])
        m.addSeparator()
        m.addActions([self.a_move_up, self.a_move_down, self.a_del_page])
        m.addSeparator()
        m.addActions([self.a_insert_pdf, self.a_insert_blank, self.a_extract])
        m.addSeparator()
        m.addAction(self.a_sheet_links)
        sep = QAction(self)
        sep.setSeparator(True)
        self.thumbs.addActions([self.a_copy_pages, self.a_cut_pages, self.a_paste_pages,
                                self.a_dup_pages, sep, self.a_rot_l, self.a_rot_r, self.a_del_page])
        m = mb.addMenu(tr("&Help"))
        m.addAction(self.a_manual)
        m.addAction(self.a_palette)
        m.addSeparator()
        m.addActions([self.a_check_updates, self.a_auto_updates])
        m.addSeparator()
        m.addActions([self.a_feedback, self.a_about])

    def _build_toolbars(self):
        tb = self.main_tb = QToolBar(tr("Main"))
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
        self.prev_page_btn.setToolTip(tr("Previous page (Left arrow key)"))
        self.prev_page_btn.clicked.connect(lambda: self._step_page(-1))
        self.next_page_btn = QToolButton()
        self.next_page_btn.setArrowType(Qt.RightArrow)
        self.next_page_btn.setToolTip(tr("Next page (Right arrow key)"))
        self.next_page_btn.clicked.connect(lambda: self._step_page(1))
        self.page_total = QLabel(" / 0 ")
        self.first_page_btn = QToolButton()
        self.first_page_btn.setText("\u23EE")
        self.first_page_btn.setToolTip(tr("First page"))
        self.first_page_btn.clicked.connect(lambda: self._step_page(-10 ** 9))
        self.last_page_btn = QToolButton()
        self.last_page_btn.setText("\u23ED")
        self.last_page_btn.setToolTip(tr("Last page"))
        self.last_page_btn.clicked.connect(lambda: self._step_page(10 ** 9))
        for b in (self.first_page_btn, self.prev_page_btn, self.next_page_btn, self.last_page_btn):
            b.setAutoRaise(True)
        self.nav_group = self._group_widget([QLabel(tr(" Page ")), self.first_page_btn,
                                             self.prev_page_btn, self.page_spin,
                                             self.next_page_btn, self.last_page_btn,
                                             self.page_total])
        # bottom-bar extras for the ribbon layout (PDF-XChange style): fit buttons and a slider
        self.zoom_slider = QSlider(Qt.Horizontal)
        self.zoom_slider.setRange(0, _SLIDER_STEPS)
        self.zoom_slider.setFixedWidth(110)
        self.zoom_slider.setToolTip(tr("Zoom: drag to zoom from 10% to 6400%"))
        self.zoom_slider.sliderMoved.connect(
            lambda val: self.view() and self.view().set_zoom(_slider_to_zoom(val)))
        self.view_group = self._group_widget([self.a_fit_page, self.a_fit_width, self.a_actual,
                                              self.zoom_slider])
        self._nav_group_act = tb.addWidget(self.nav_group)
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._spacer_act = tb.addWidget(spacer)
        self.search = _FindBox()
        self.search.setPlaceholderText(tr("Find (Ctrl+F)"))
        self.search.setClearButtonEnabled(True)
        self.search.setMaximumWidth(260)
        self.search.returnPressed.connect(lambda: self._find(False))
        self.search.previousRequested.connect(lambda: self._find(True))
        self.search.textChanged.connect(lambda t: (not t) and self.view()
                                        and self.view().clear_search())
        # the Find box with its match count and up / down arrows, kept together wherever
        # the box goes (top toolbar or the ribbon's tab row)
        self.find_count = QLabel()
        self.find_count.setToolTip(tr("Match shown of the matches found"))
        self.find_prev_btn = QToolButton()
        self.find_prev_btn.setArrowType(Qt.UpArrow)
        self.find_prev_btn.setAutoRaise(True)
        self.find_prev_btn.setToolTip(tr("Previous match (Shift+Enter, Shift+F3)"))
        self.find_prev_btn.clicked.connect(lambda: self._find(True))
        self.find_next_btn = QToolButton()
        self.find_next_btn.setArrowType(Qt.DownArrow)
        self.find_next_btn.setAutoRaise(True)
        self.find_next_btn.setToolTip(tr("Next match (Enter, F3)"))
        self.find_next_btn.clicked.connect(lambda: self._find(False))
        self.find_group = QWidget()
        fl = QHBoxLayout(self.find_group)
        fl.setContentsMargins(0, 0, 0, 0)
        fl.setSpacing(2)
        for w in (self.search, self.find_count, self.find_prev_btn, self.find_next_btn):
            fl.addWidget(w)
        self._show_find_count(0, 0, False)
        self._search_act = tb.addWidget(self.find_group)

        self.addToolBarBreak()
        tt = self.tools_tb = QToolBar(tr("Tools"))
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
        mmenu.addActions([self.a_set_scale, self.a_sheet_scales, self.a_measure_summary])
        self.measure_btn.setMenu(mmenu)
        self.measure_btn.setDefaultAction(self.tool_actions["m_length"])
        mmenu.triggered.connect(lambda a: a.isCheckable() and self.measure_btn.setDefaultAction(a))
        tt.addWidget(self.measure_btn)
        tt.addSeparator()
        tt.addAction(self.a_ocr)
        tt.addActions([self.a_rot_l, self.a_rot_r])
        tt.addSeparator()
        forms_btn = self.forms_btn = QToolButton()
        forms_btn.setText(tr("Form fields"))
        forms_btn.setToolTip(tr("Form field tools: add text fields, checkboxes, option buttons, "
                                "dropdowns and signature fields"))
        forms_btn.setPopupMode(QToolButton.InstantPopup)
        fmenu = QMenu(forms_btn)
        fmenu.addActions([self.tool_actions[t] for t, _, _ in FORM_TOOLS])
        forms_btn.setMenu(fmenu)
        tt.addWidget(forms_btn)

        at = self.arrange_tb = QToolBar(tr("Arrange"))
        at.setObjectName("arrange")
        at.setMovable(False)
        self.addToolBar(at)
        acts = self.arrange_actions
        at.addActions([acts[k] for k in ("al_left", "al_hcenter", "al_right",
                                         "al_top", "al_vmiddle", "al_bottom")])
        self.align_ref_box = QComboBox()
        self.align_ref_box.setToolTip(tr("Align relative to: the first markup you selected (default), "
                                         "the last one selected, the whole selection, or the page"))
        for key, a in self.align_ref_actions.items():
            self.align_ref_box.addItem(self._align_ref_short[key], key)
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
        self.dock = QDockWidget(tr("Pages"))
        self.dock.setObjectName("pages")
        self.dock.setFeatures(QDockWidget.DockWidgetClosable)
        # Pages and Bookmarks are tabs inside one panel (two tabbed dock groups on both sides
        # of the window trigger a Qt bug that draws a phantom duplicate tab bar).
        self.left_tabs = QTabWidget()
        self.left_tabs.setTabPosition(QTabWidget.South)
        self.left_tabs.setDocumentMode(True)
        self.left_tabs.setUsesScrollButtons(True)     # narrow panel: tabs scroll, don't block
        self.left_tabs.tabBar().setElideMode(Qt.ElideRight)
        self.left_tabs.addTab(side, tr("Pages"))
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
        self.left_tabs.addTab(self._narrowable(self.bookmarks), tr("Bookmarks"))
        from .layers_panel import LayersPanel
        self.layers = LayersPanel()
        self.layers.toggled.connect(lambda n, on: self.view() and self.view().set_layer(n, on))
        self.layers.allToggled.connect(self._all_layers)
        self.left_tabs.addTab(self._narrowable(self.layers), tr("Layers"))
        from .objects_panel import ObjectsPanel
        self.objects = ObjectsPanel()
        self.objects.selectRequested.connect(self._objects_select)
        self.objects.flagsChanged.connect(self._objects_flags)
        self.objects.arrange.connect(lambda how: self.view() and self.view().arrange(how))
        self.left_tabs.addTab(self._narrowable(self.objects), tr("Objects"))
        self._objects_timer = QTimer(self, singleShot=True, interval=150)
        self._objects_timer.timeout.connect(self._refresh_objects)
        self.left_tabs.currentChanged.connect(lambda _i: self._objects_timer.start())

        self.props = PropertiesPanel()
        self.props.propsChanged.connect(self._on_props_changed)
        self.props.resetRequested.connect(self._reset_tool_defaults)
        scroll = QScrollArea()
        scroll.setWidget(self.props)
        scroll.setWidgetResizable(True)
        self.props_dock = QDockWidget(tr("Properties"))
        self.props_dock.setObjectName("properties")
        self.props_dock.setFeatures(QDockWidget.DockWidgetClosable)
        self.props_dock.setWidget(scroll)
        self.props_dock.setMinimumWidth(220)
        self.props_dock.visibilityChanged.connect(lambda vis: self.a_props.setChecked(vis))
        self.addDockWidget(Qt.RightDockWidgetArea, self.props_dock)

        self.chest = ToolChestPanel()
        self.chest.use.connect(self._use_chest_tool)
        self.chest.addRequested.connect(self._add_to_chest)
        self.chest_dock = QDockWidget(tr("Tool chest"))
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
        self.markups_dock = QDockWidget(tr("Markups list"))
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
        for a in (self.a_save, self.a_save_as, self.a_print, self.a_close, self.a_detach,
                  self.a_find,
                  self.a_find_next, self.a_find_prev, self.a_zoom_in, self.a_zoom_out,
                  self.a_fit_width, self.a_fit_page, self.a_actual, self.a_rot_l, self.a_rot_r,
                  self.a_del_page, self.a_move_up, self.a_move_down, self.a_extract, self.a_ocr, self.a_flatten, self.a_sheet_links,
                  self.a_security, self.a_remove_security, self.a_sanitize, self.a_clear_sigs,
                  self.a_timestamp, self.a_multi_sign, self.a_apply_placeholders,
                  self.a_apply_sel_redact, self.a_unlock, self.a_set_scale, self.a_measure_summary,
                  self.a_sheet_scales,
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
                self.zoom_slider.setValue(_zoom_to_slider(v.zoom))
                self.zoom_slider.blockSignals(False)
            self.scale_label.setText(v.page_scale_text(v.current_page()))
            # (the file name itself is never translated, only the words around it)
            name = tr("{name} [protected]").format(name=_doc_name(v)) if v.read_only \
                else _doc_name(v)
            self.setWindowTitle(f"{'*' if v.dirty else ''}{name} - {_title_base()}")
            for i in range(self.tabs.count()):
                # only changed names: each set lays out the whole tab bar again
                w = self.tabs.widget(i)
                text = ("*" if w.dirty else "") + _doc_name(w)
                if self.tabs.tabText(i) != text:
                    self.tabs.setTabText(i, text)
                tip = tr("Not saved yet") if w.untitled else w.path
                if self.tabs.tabToolTip(i) != tip:
                    self.tabs.setTabToolTip(i, tip)
        else:
            self.page_total.setText(" / 0 ")
            self.scale_label.setText("")
            self.setWindowTitle(_title_base())

    # ---- files --------------------------------------------------------------
    def open_dialog(self):
        start = self.settings.value("last_dir", "")
        paths, _ = QFileDialog.getOpenFileNames(self, tr("Open PDF"), start, PDF_FILTER)
        for p in paths:
            self.open_file(p)

    def open_file(self, path):
        path = os.path.abspath(path)
        for i in range(self.tabs.count()):
            w = self.tabs.widget(i)
            if not w.untitled and os.path.normcase(w.path) == os.path.normcase(path):
                # already open: show it, as it is on disk now if it changed since
                if self._changed_on_disk(w) and self._may_reload(w):
                    w = self._reload_tab(w) or w
                self.tabs.setCurrentWidget(w)
                return
        v = self._load_view(path)
        if v is None:
            return
        idx = self.tabs.addTab(v, os.path.basename(path))
        self.tabs.setCurrentIndex(idx)
        self.settings.setValue("last_dir", os.path.dirname(path))
        self._add_recent(path)

    def _load_view(self, path):
        """A view of the PDF at path, wired to this window (not in a tab yet); None if it
        can't be opened (the reason is shown)."""
        try:
            v = DocumentView(path)
        except Exception as ex:
            QMessageBox.critical(self, tr("Could not open file"), f"{path}\n\n{ex}")
            return None
        self._connect_view(v)
        if v.read_only:
            QTimer.singleShot(0, lambda: QMessageBox.information(
                self, tr("Protected document"), tr("This PDF is protected against changes. You can "
                                                   "read, search and print it. Use Protect > Unlock with password if you have its "
                                                   "permissions password.")))
        v.check_digital_signatures()
        state = self._file_states().get(os.path.normcase(path))
        if state:
            v.initial_state = state            # reopen at the last page and zoom
        return v

    @staticmethod
    def _changed_on_disk(v):
        """True when v's file was replaced or changed since v read or saved it."""
        from .document_view import disk_stamp
        now = disk_stamp(v.path)
        was = getattr(v, "disk_stamp", None)
        return not v.untitled and now is not None and was is not None and now != was

    def _may_reload(self, v):
        """Before reloading v's file: ask when that drops unsaved changes."""
        v.commit_pending()
        if not v.dirty:
            return True
        self.tabs.setCurrentWidget(v)
        return QMessageBox.question(
            self, tr("File changed on disk"),
            tr("{name} has changed on disk since it was opened, and this tab has unsaved "
               "changes.\n\nReload it from disk and lose your changes?").format(
                name=os.path.basename(v.path)),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes

    def _reload_tab(self, v):
        """Show v's file as it is on disk now, in v's place (v and its unsaved changes are
        dropped). Returns the new view, or None if the file can't be opened."""
        i = self.tabs.indexOf(v)
        self._remember_state(v)
        nv = self._load_view(v.path)
        if nv is None or i < 0:
            return None
        current = self.tabs.currentIndex() == i
        self.tabs.insertTab(i + 1, nv, os.path.basename(nv.path))
        if current:
            self.tabs.setCurrentIndex(i + 1)
        v.commit_pending()
        v.dirty = False
        self.close_tab(i)
        return nv

    @staticmethod
    def _writing_over(path, exclude=None, source=None):
        """Before a new PDF is written at path (Save As, Extract pages, Combine files, the
        copies saved by Compress, Timestamp and Digital signature): the tabs, in any window,
        that show the file there now [(window, view)]. When one of them has unsaved changes,
        ask first: None = don't write."""
        key = os.path.normcase(os.path.abspath(path))
        tabs = [(w, v) for w in windows() for v in w._views()
                if v is not exclude and not v.untitled and os.path.normcase(v.path) == key]
        for w, v in tabs:
            v.commit_pending()
        # (source: the tab whose document is written, unsaved changes and all: nothing of
        # it is lost)
        if any(v.dirty and v is not source for _w, v in tabs):
            w = tabs[0][0]
            w.tabs.setCurrentWidget(next(v for _w, v in tabs if v.dirty and v is not source))
            if QMessageBox.warning(
                    w, tr("File is open"),
                    tr("{name} is open in KanzonasPDF with unsaved changes.\n\nReplace it "
                       "anyway and lose those changes?").format(name=os.path.basename(path)),
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
                return None
        return tabs

    @staticmethod
    def _written_over(tabs, close=False):
        """The file these tabs showed was just replaced: show the new one in them (close:
        close them instead), without asking (see _writing_over)."""
        for w, v in tabs:
            i = w.tabs.indexOf(v)
            if i < 0:
                continue
            if close:
                v.commit_pending()
                v.dirty = False
                w.close_tab(i)
            else:
                w._reload_tab(v)

    def _add_recent(self, path):
        from . import paths
        recent = self.settings.value("recent") or []
        if isinstance(recent, str):         # INI settings (portable) give one entry as a str
            recent = [recent]
        recent = [p for p in (paths.follow_drive(r) for r in recent) if p != path]
        recent.insert(0, path)
        self.settings.setValue("recent", recent[:10])
        self._rebuild_recent()

    def _rebuild_recent(self):
        from . import paths
        self.recent_menu.clear()
        recent = self.settings.value("recent") or []
        if isinstance(recent, str):
            recent = [recent]
        # portable: files on the stick follow it to its new drive letter on another PC
        recent = [paths.follow_drive(p) for p in recent]
        for p in recent:
            a = self.recent_menu.addAction(p)
            a.triggered.connect(lambda _=False, p=p: self.open_file(p))
        self.recent_menu.setEnabled(bool(recent))

    def save(self):
        v = self.view()
        if not v:
            return False
        if v.untitled:
            return self.save_as()
        try:
            v.save()
        except Exception as ex:
            QMessageBox.critical(self, tr("Save failed"),
                                 tr("{error}\n\nIf the file is open in another program, close "
                                    "it or use Save As.").format(error=ex))
            return False
        self.autosave.discard(v)
        self.statusBar().showMessage(tr("Saved {path}").format(path=v.path), 4000)
        return True

    def save_as(self):
        v = self.view()
        if not v:
            return False
        path, _ = QFileDialog.getSaveFileName(self, tr("Save As"), v.path, PDF_FILTER)
        if not path:
            return False
        others = self._writing_over(path, exclude=v)
        if others is None:
            return False
        try:
            v.save(path)
        except Exception as ex:
            QMessageBox.critical(self, tr("Save failed"), str(ex))
            return False
        self._written_over(others, close=True)      # this tab is that file now
        self.autosave.discard(v)
        self._add_recent(v.path)
        self.settings.setValue("last_dir", os.path.dirname(v.path))
        self._update_ui()
        return True

    def _confirm_close(self, v):
        v.commit_pending()               # typed text not yet confirmed counts as a change
        if not v.dirty:
            return True
        self.tabs.setCurrentWidget(v)
        r = QMessageBox.question(self, tr("Unsaved changes"),
                                 tr("Save changes to {name}?").format(
                                     name=os.path.basename(v.path)),
                                 QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
        if r == QMessageBox.Save:
            return self.save()
        return r == QMessageBox.Discard

    def _connect_view(self, v):
        """Wire a document view to this window (the connections are kept so the view can
        move to another window, see move_view)."""
        v.set_tool(self.tool)
        v.show_comment_boxes = self.a_cards.isChecked()
        conns = [
            (v.selectionChanged, self._on_selection_changed),
            (v.openFileRequested, self._open_linked_pdf),
            (v.signedDocument, self._on_signed),
            (v.oneShotPlaced, self._after_one_shot),
            (v.selectToolRequested, lambda: self.set_tool("select")),
            (v.previousToolRequested, lambda: self.set_tool(self.default_tool())),
            (v.calibrateRequested, self._calibrate),
            (v.layersChanged, lambda: self.sender() is self.view() and self._rebuild_thumbs()),
            (v.scaleChanged, self._update_ui),
            (v.documentChanged, self._markups_timer.start),
            (v.structureChanged, self._markups_timer.start),
            (v.requestSignature, self._sign_field),
            (v.textToolPropsChanged,
             lambda: self.sender() is self.view() and self._refresh_props()),
            (v.pageChanged, self._on_page_changed),
            (v.zoomChanged, lambda _: self._update_ui()),
            (v.documentChanged, self._on_doc_changed),
            (v.structureChanged, self._on_structure_changed),
            (v.statusMessage, lambda m: self.statusBar().showMessage(m, 4000)),
            (v.searchChanged, self._on_search_changed),
        ]
        for sig, slot in conns:
            sig.connect(slot)
        v._kz_window_conns = conns
        for kind, png in self._sig_cache.items():
            v.set_sig_image(kind, png)

    def _disconnect_view(self, v):
        for sig, slot in getattr(v, "_kz_window_conns", []):
            try:
                sig.disconnect(slot)
            except (RuntimeError, TypeError):
                pass
        v._kz_window_conns = []

    # ---- tabs in other windows --------------------------------------------------------
    def detach_current(self):
        self.detach_tab(self.tabs.currentIndex())

    def detach_tab(self, index, pos=None):
        """Move the tab's document into a new window of its own (pos: where to put the
        window, screen coordinates; else a little offset from this one). The document isn't
        reopened: its unsaved changes and undo history come along."""
        v = self.tabs.widget(index)
        if v is None:
            return None
        win = MainWindow(primary=False)
        win._sig_cache = dict(self._sig_cache)
        win.resize(self.size())
        win.move(pos - QPoint(120, 24) if pos is not None else self.pos() + QPoint(40, 40))
        win.show()
        self.move_view(v, win)
        win.raise_()
        win.activateWindow()
        return win

    def move_view(self, v, target, at=-1):
        """Move document view v from this window to target (at: tab position there)."""
        index = self.tabs.indexOf(v)
        if index < 0 or target is self:
            return
        v.commit_pending()
        title = self.tabs.tabText(index)
        if self._split_view is not None and getattr(self._split_view, "_source", None) is v:
            self._split_view.deleteLater()
            self._split_view = None
            self.split_dock.hide()
        self._disconnect_view(v)
        self.tabs.removeTab(index)
        target.adopt_view(v, title, at)
        self._update_ui()
        if not self.primary and self.tabs.count() == 0:
            QTimer.singleShot(0, self.close)     # a pulled-out window with nothing left in it

    def adopt_view(self, v, title, at=-1):
        self._connect_view(v)
        at = self.tabs.count() if at < 0 else at
        self.tabs.insertTab(at, v, title)
        self.tabs.setCurrentIndex(at)
        self._update_ui()

    def receive_tab(self, src, index, at):
        """A tab dropped on this window's tab bar: from another window, or reordered."""
        if src is self:
            if 0 <= index != at and at >= 0:
                self.tabs.tabBar().moveTab(index, at)
            return
        v = src.tabs.widget(index)
        if v is not None:
            src.move_view(v, self, at)

    def drag_tab_out(self, index):
        """Drag a tab beyond the tab bar: drop it on another window's tabs to move it there,
        or anywhere else to open it in a new window at the pointer."""
        v = self.tabs.widget(index)
        if v is None:
            return
        drag = QDrag(self.tabs.tabBar())
        mime = QMimeData()
        mime.setData(TAB_MIME, f"{id(self)}:{index}".encode("ascii"))
        drag.setMimeData(mime)
        pix = v.grab().scaledToWidth(240, Qt.SmoothTransformation)
        drag.setPixmap(pix)
        drag.setHotSpot(QPoint(pix.width() // 2, 12))
        result = drag.exec(Qt.MoveAction)
        if result == Qt.IgnoreAction and self.tabs.indexOf(v) >= 0:
            self.detach_tab(self.tabs.indexOf(v), QCursor.pos())

    def _tab_menu(self, pos):
        bar = self.tabs.tabBar()
        index = bar.tabAt(pos)
        if index < 0:
            return
        menu = QMenu(self)
        menu.addAction(tr("Move to new window"), lambda: self.detach_tab(index))
        others = [w for w in windows() if w is not self and w.isVisible()]
        for w in others:
            name = w.tabs.tabText(w.tabs.currentIndex()) if w.tabs.count() else \
                tr("empty window")
            menu.addAction(tr("Move to window: {name}").format(name=name),
                           lambda _=False, w=w: self.move_view(self.tabs.widget(index), w))
        menu.addSeparator()
        menu.addAction(tr("Close tab"), lambda: self.close_tab(index))
        menu.exec(bar.mapToGlobal(pos))

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
        if not self.primary and self.tabs.count() == 0:
            QTimer.singleShot(0, self.close)     # a pulled-out window with nothing left in it

    def _views(self):
        return [self.tabs.widget(i) for i in range(self.tabs.count())]

    @staticmethod
    def _all_views():
        """The documents open in every window (view options apply to all of them)."""
        return [v for w in windows() for v in w._views()]

    def closeEvent(self, e):
        """Closing the primary window closes every window (asking about unsaved changes in
        each) and remembers the session; closing a pulled-out window closes just its tabs."""
        others = [w for w in windows() if w is not self] if self.primary else []
        if not getattr(self, "_close_confirmed", False):
            if not self._confirm_exit([(w, v) for w in [self] + others for v in w._views()]):
                e.ignore()
                return
        self._save_session(others)
        if self.primary:
            for w in others:
                w._close_confirmed = True
                w.close()
        self.autosave.discard_all()
        QApplication.instance().removeEventFilter(self)
        _forget_window(next((r for r in _WINDOW_REFS if r() is self), None))
        e.accept()

    def _save_session(self, others=()):
        """Each open document's page and zoom; from the primary window also the files open
        in all windows (Preferences > Start-up reopens them) and the window layout."""
        from . import autosave
        backups = autosave.folder()
        session = []
        for w in [self] + list(others):
            for v in w._views():
                w._remember_state(v)
                if v.path and not v.untitled and os.path.exists(v.path) and \
                        not os.path.normcase(v.path).startswith(os.path.normcase(backups)):
                    session.append(v.path)
        if self.primary:
            self.settings.setValue("session_files", json.dumps(session))
            self.settings.setValue("geometry", self.saveGeometry())
            self.settings.setValue("window_state", self.saveState(LAYOUT_VERSION))
        self.settings.sync()

    def windows_ending(self, *_):
        """Windows is ending KanzonasPDF without closing its windows: a setup updating it
        (the installer closes running copies) or the computer shutting down or signing out.
        Nothing can be asked now, so keep what closing keeps: the open files (reopened at
        start-up when that's on) and, for unsaved changes, backup copies that are offered
        the next time KanzonasPDF starts (unless backups are turned off)."""
        others = [w for w in windows() if w is not self]
        for w in [self] + others:
            for v in w._views():
                v.commit_pending()
            if w.autosave.minutes:
                w.autosave.tick()
        self._save_session(others)

    def _confirm_exit(self, views):
        """Before the window closes: with one document, the usual Save / Discard / Cancel
        when it has unsaved changes. With several documents, one question for all of them
        (Preferences > Start-up turns off the question when none of them has unsaved
        changes): Save all / Don't save / Cancel. False = keep everything open."""
        for _w, v in views:
            v.commit_pending()          # typed text not yet confirmed counts as a change
        if len(views) < 2:
            return all(w._confirm_close(v) for w, v in views)
        dirty = [(w, v) for w, v in views if v.dirty]
        if not dirty and self.settings.value("confirm_exit", "true") == "false":
            return True
        answer = self._ask_exit(len(views), [os.path.basename(v.path or tr("Untitled"))
                                             for _w, v in dirty])
        if answer == "cancel":
            return False
        if answer == "save":
            for w, v in dirty:
                w.tabs.setCurrentWidget(v)
                if not w.save():        # a failed or canceled save keeps everything open
                    return False
        return True

    def _ask_exit(self, count, unsaved):
        """The question before closing with several documents open: 'save' (all the
        unsaved ones), 'discard' or 'cancel'."""
        box = QMessageBox(QMessageBox.Question, tr("Close KanzonasPDF"), "", parent=self)
        if unsaved:
            names = "\n".join("  " + n for n in unsaved[:12])
            if len(unsaved) > 12:
                names += "\n  " + tr("... and {n} more").format(n=len(unsaved) - 12)
            box.setText(tr("{count} documents are open; {unsaved} with unsaved changes:\n"
                           "{names}\n\nSave them before closing?").format(
                count=count, unsaved=len(unsaved), names=names))
            save = box.addButton(tr("Save all"), QMessageBox.AcceptRole)
            box.addButton(tr("Don't save"), QMessageBox.DestructiveRole)
            cancel = box.addButton(QMessageBox.Cancel)
            box.setDefaultButton(save)
        else:
            box.setText(tr("{count} documents are open. Close them all and exit?").format(
                count=count))
            close = box.addButton(tr("Close all"), QMessageBox.AcceptRole)
            cancel = box.addButton(QMessageBox.Cancel)
            box.setDefaultButton(close)
            save = None
        box.setEscapeButton(cancel)
        box.exec()
        clicked = box.clickedButton()
        if clicked is cancel or clicked is None:
            return "cancel"
        return "save" if clicked is save else "discard"

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
            self, tr("Recover unsaved changes?"),
            tr("KanzonasPDF didn't close normally last time. Automatic backup copies of these "
               "documents have unsaved changes:\n\n{names}\n\nOpen the copies now? Each opens "
               "with unsaved changes, and Save asks where to keep it. (They stay in the backups "
               "folder for 30 days either way: File > Preferences > Saving > Open backup "
               "folder.)").format(names=names))
        moved = autosave.set_aside(items)
        if r == QMessageBox.Yes:
            for p, original in moved:
                self._open_recovered(p, original)

    def _open_recovered(self, copy, original):
        """A backup copy offered after a crash: it opens with unsaved changes, named after its
        original file, and Save asks where to save it, offering the original file."""
        try:
            with open(copy, "rb") as f:
                doc = pymupdf.open(stream=f.read(), filetype="pdf")
            if not original:
                v = self._open_untitled(doc)
            else:
                v = DocumentView(original, doc=doc)
                v.recovered = True
                self._connect_view(v)
                self.tabs.setCurrentIndex(self.tabs.addTab(v, _doc_name(v)))
        except Exception as ex:
            QMessageBox.critical(self, tr("Could not open file"), f"{copy}\n\n{ex}")
            return None
        v.dirty = True                  # closing it asks whether to save
        self._update_ui()
        return v

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        for url in e.mimeData().urls():
            if url.isLocalFile():
                self.open_file(url.toLocalFile())

    # ---- printing -----------------------------------------------------------
    def print_doc(self):
        """File > Print: KanzonasPDF's print window, with a preview of each sheet."""
        v = self.view()
        if not v or not v.require_permission(pymupdf.PDF_PERM_PRINT, tr("Printing")):
            return
        from .print_dialog import PrintDialog
        if PrintDialog(self, v).exec():
            self.statusBar().showMessage(tr("Sent to printer"), 4000)

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
        # keyboard focus to the page (unless you're typing somewhere), so Escape puts the
        # tool down even when it was picked from a toolbar button or a stamp menu
        v = self.view()
        typing = isinstance(QApplication.focusWidget(), (QLineEdit, QAbstractSpinBox, QPlainTextEdit))
        if v is not None and not typing:
            v.setFocus()
        self._refresh_props()

    def default_tool(self):
        """Hand or Select (the mouse mode: Hand, or Standard and CAD): the tool at start-up,
        and the one Escape and a placed signature / date go back to."""
        from . import mouse_modes
        return mouse_modes.default_tool(mouse_modes.mode(self.settings))

    def _after_one_shot(self):
        """After placing a signature, initials or a date: back to the default tool."""
        if self.tool in ("signature", "initials", "date"):
            self.set_tool(self.default_tool())

    # ---- properties panel / tool defaults -------------------------------------
    def _refresh_props(self):
        v = self.view()
        if v is not None and v.selected_model is not None:
            m = v.selected_model
            self.props.show_target(m["kind"], m["props"], selected=True)
        elif (self.tool in annotations.DEFAULTS and self.tool != "image") or \
                self.tool in annotations.PAGE_TEXT_TOOLS:
            # (the Image tool writes into the page: no markup settings apply; Add text and
            # Edit text have their font settings here)
            self.props.show_target(self.tool, annotations.tool_props(self.tool))
        else:
            self.props.show_target(None, None)

    def _on_props_changed(self, props):
        v = self.view()
        if v is not None and v.selected_model is not None:
            v.update_selected_props(props)
        elif annotations.OVERRIDE["tool"] == self.tool:
            annotations.OVERRIDE["props"] = dict(props)
        elif self.tool in annotations.DEFAULTS or self.tool in annotations.PAGE_TEXT_TOOLS:
            annotations.set_tool_props(self.tool, props)
            if v is not None and self.tool in annotations.PAGE_TEXT_TOOLS:
                v.text_tool_props_changed()

    def _reset_tool_defaults(self):
        if self.tool in annotations.DEFAULTS or self.tool in annotations.PAGE_TEXT_TOOLS:
            annotations.reset_tool_props(self.tool)
            self._refresh_props()

    def _open_linked_pdf(self, path, page):
        self.open_file(path)
        v = self.view()
        if v is not None and page >= 0 and os.path.normcase(v.path or "") == os.path.normcase(path):
            import shiboken6

            def jump():                 # the tab may be closed again before the timer fires
                if shiboken6.isValid(v) and not v.doc.is_closed:
                    v.goto_page(min(page, v.page_count() - 1))
            QTimer.singleShot(200, jump)

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
        if QApplication.closingDown():
            return False            # the app is being torn down: nothing here is safe to touch
        t = e.type()
        if t == QEvent.Resize and obj is getattr(self, "thumbs", None):
            QTimer.singleShot(0, self._fit_thumbs)     # after the list has laid out its new size
        if t == QEvent.KeyPress and obj is getattr(self, "thumbs", None) and \
                e.key() in (Qt.Key_Delete, Qt.Key_Backspace) and not e.modifiers():
            self._page_op("del")                        # Delete in the page list: those pages
            return True
        if t == QEvent.KeyPress and e.key() == Qt.Key_Escape and not e.modifiers() and \
                self.isActiveWindow() and self._escape_goes_to_page():
            # after a toolbar button, a ribbon tab or a dialog took the keyboard focus, Escape
            # still clears the selection / puts the tool down, as if the page had focus
            v = self.view()
            if v is not None:
                v.setFocus()
                v.keyPressEvent(e)
                return True
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

    def _escape_goes_to_page(self):
        """True when Escape should go to the page: no menu or dialog is open and the keyboard
        focus isn't somewhere Escape means something (a text box, a list, the page itself)."""
        from PySide6.QtWidgets import QAbstractButton
        if QApplication.activePopupWidget() is not None or QApplication.activeModalWidget() is not None:
            return False
        fw = QApplication.focusWidget()
        if fw is None:
            return True
        return isinstance(fw, (QAbstractButton, QToolBar, QTabWidget)) or \
            type(fw).__name__ in ("QTabBar", "_TabBar", "Ribbon")

    def _focus_search(self):
        self.search.setFocus()
        self.search.selectAll()

    def _find(self, backwards):
        v = self.view()
        if not v:
            return
        if not v.find(self.search.text(), backwards) and self.search.text():
            self.statusBar().showMessage(tr("No matches"), 4000)
        self._show_find_count(*v.search_position())

    def _on_search_changed(self, n, total, searching):
        if self.sender() is self.view():       # another tab's search doesn't show here
            self._show_find_count(n, total, searching)

    def _show_find_count(self, n, total, searching):
        """The count beside the Find box: '3 of 120' ('120+' while still searching)."""
        v = self.view()
        if not total and not searching:
            text = tr("No matches") if v is not None and v.search_text() is not None else ""
        elif not n:
            text = tr("Searching...")
        else:
            text = tr("{n} of {total}").format(n=n, total=f"{total}+" if searching else total)
        self.find_count.setText(text)
        self.find_count.setVisible(bool(text))
        for b in (self.find_prev_btn, self.find_next_btn):
            b.setEnabled(total > 0)

    def _zoom_from_box(self):
        v = self.view()
        if not v:
            return
        try:
            # "25,5%" too (a decimal comma); not "nan" or "inf"
            z = float(self.zoom_box.currentText().strip().rstrip("%").strip().replace(",", "."))
            if math.isfinite(z) and z > 0:
                v.set_zoom(z / 100)
        except ValueError:
            pass
        self._update_ui()

    def _page_op(self, op, arg=None):
        v = self.view()
        if not v:
            if op == "blank":           # nothing open: a new PDF is the blank page
                self.new_pdf()
            return
        cur = v.current_page()
        if op in ("del", "move", "blank") and not self._pages_unlocked():
            return
        if op == "rot":
            v.rotate_page(cur, arg)
        elif op == "del":
            pages = self._selected_pages()
            if len(pages) == 1:
                text = tr("Delete page {page}?").format(page=pages[0] + 1)
            else:
                names = ", ".join(str(i + 1) for i in pages[:12]) + \
                    (", ..." if len(pages) > 12 else "")
                text = tr("Delete these {n} pages ({pages})?").format(n=len(pages), pages=names)
            if QMessageBox.question(self, tr("Delete pages"), text) == QMessageBox.Yes and \
                    v.delete_pages(pages):
                self.statusBar().showMessage(
                    tr("Deleted {n} page(s) (Ctrl+Z undoes it)").format(n=len(pages)), 4000)
        elif op == "move":
            v.move_page(cur, arg)
        elif op == "blank":
            v.insert_blank(cur + 1)
        elif op == "uncrop":
            scope = v._ask_pages_scope(tr("Remove crop"), tr("Remove the crop from which pages?"))
            if scope is not None:
                v.remove_crop(cur, scope == "all")
            v.setFocus()                # so Escape still puts the Crop tool down

    def combine_files(self):
        from .combine import CombineDialog
        v = self.view()
        first = [v.path] if v is not None and not v.untitled and v.path and \
            os.path.isfile(v.path) else []
        if first and v.dirty:
            QMessageBox.information(self, tr("Combine files"), tr("The current document has unsaved "
                                                                  "changes; the combined PDF uses the saved file."))
        dlg = CombineDialog(self, self.settings.value("last_dir", ""), first)
        replaced = self._guard_target(dlg)
        if dlg.exec() and dlg.result_path:
            self._written_over(replaced)
            self.open_file(dlg.result_path)
            self.statusBar().showMessage(tr("Combined into {path}").format(path=dlg.result_path),
                                         5000)

    def _guard_target(self, dlg):
        """Have the Combine dialog check the file it's about to write (see _writing_over);
        returns the list that then holds the tabs showing that file."""
        replaced = []

        def check(path):
            tabs = self._writing_over(path)
            replaced[:] = tabs or []
            return tabs is not None
        dlg.check_target = check
        return replaced

    def pdf_from_images(self):
        from .combine import CombineDialog, IMAGE_FILTER
        start = self.settings.value("last_dir", "")
        paths, _ = QFileDialog.getOpenFileNames(self, tr("Create PDF from images"), start,
                                                IMAGE_FILTER)
        if not paths:
            return
        dlg = CombineDialog(self, os.path.dirname(paths[0]), paths, images=True)
        replaced = self._guard_target(dlg)
        if dlg.exec() and dlg.result_path:
            self._written_over(replaced)
            self.open_file(dlg.result_path)
            self.statusBar().showMessage(tr("Created {path}").format(path=dlg.result_path), 5000)

    def insert_from_file(self):
        """Pages > Insert pages from file: PDFs and pictures (each picture a page). With
        nothing open they make a new, unsaved PDF."""
        from .combine import IMAGE_EXTS, is_image
        v = self.view()
        if v and not self._pages_unlocked():
            return
        pics = " ".join("*" + e for e in IMAGE_EXTS)
        paths, _ = QFileDialog.getOpenFileNames(
            self, tr("Insert pages from"), self.settings.value("last_dir", ""),
            tr("PDFs and pictures") + f" (*.pdf {pics});;" + tr("PDF files") + " (*.pdf);;"
            + tr("Pictures") + f" ({pics})")
        if not paths:
            return
        self.settings.setValue("last_dir", os.path.dirname(paths[0]))
        if not v:
            from . import new_pdf
            size = new_pdf.ask(self, self.settings) if any(map(is_image, paths)) else \
                new_pdf.page_size(*new_pdf.remembered(self.settings))
            if size is None:
                return
            from .combine import insert_files
            doc = pymupdf.open()
            try:
                insert_files(doc, paths, 0, size)
            except Exception as ex:
                doc.close()
                QMessageBox.critical(self, tr("Insert pages"), str(ex))
                return
            v = self._open_untitled(doc)
            v.dirty = True              # closing it asks whether to save
            self._update_ui()
            return
        choices = [tr("After current page"), tr("At the end"), tr("At the beginning")]
        where, ok = QInputDialog.getItem(self, tr("Insert pages"), tr("Insert:"), choices, 0, False)
        if not ok:
            return
        at = {0: v.current_page() + 1, 1: -1, 2: 0}[choices.index(where)]
        v.insert_files(paths, at)           # shows what went wrong itself

    def new_pdf(self):
        """File > New PDF: an unsaved document with one blank page of the chosen size; Save
        asks where to save it."""
        from . import new_pdf
        size = new_pdf.ask(self, self.settings)
        if size is None:
            return None
        return self._open_untitled(new_pdf.blank_doc(size))

    def _open_untitled(self, doc):
        """Show a new, unsaved document in a tab named Untitled N."""
        from PySide6.QtCore import QStandardPaths
        folder = self.settings.value("last_dir", "") or \
            QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation)
        taken = {os.path.basename(w.path).lower() for w in
                 (x for win in windows() for x in win._views())}
        n = 1
        while True:
            # (a name of our own for a new document, in the user's language)
            name = tr("Untitled {n}.pdf").format(n=n)
            if name.lower() not in taken and not os.path.exists(os.path.join(folder, name)):
                break
            n += 1
        v = DocumentView(os.path.join(folder, name), doc=doc)
        self._connect_view(v)
        idx = self.tabs.addTab(v, name)
        self.tabs.setCurrentIndex(idx)
        self.statusBar().showMessage(tr("{name} isn't saved yet: Save (Ctrl+S) asks where to "
                                        "save it").format(name=name), 5000)
        return v

    def extract_pages(self):
        v = self.view()
        if not v or not v.require_permission(pymupdf.PDF_PERM_COPY, tr("Extracting")):
            return
        n = v.page_count()
        cur = v.current_page() + 1
        text, ok = QInputDialog.getText(self, tr("Extract pages"),
                                        tr("Page range (1-{n}), e.g. 3-7:").format(n=n),
                                        text=f"{cur}-{cur}")
        if not ok:
            return
        try:
            parts = text.replace(" ", "").split("-")
            first = int(parts[0])
            last = int(parts[-1])
            if not 1 <= first <= last <= n:
                raise ValueError
        except ValueError:
            QMessageBox.warning(self, tr("Extract pages"), tr("Invalid page range."))
            return
        base = os.path.splitext(v.path)[0]
        path, _ = QFileDialog.getSaveFileName(self, tr("Save extracted pages"),
                                              f"{base}_p{first}-{last}.pdf", PDF_FILTER)
        if not path:
            return
        if not v.untitled and os.path.normcase(os.path.abspath(path)) == os.path.normcase(v.path):
            QMessageBox.warning(self, tr("Extract pages"), tr("Choose a new file name: the extracted "
                                                              "pages can't replace the document they come from."))
            return
        replaced = self._writing_over(path)
        if replaced is None:
            return
        try:
            v.extract_pages(first - 1, last - 1, path)
        except Exception as ex:
            QMessageBox.critical(self, tr("Extract pages"),
                                 tr("Couldn't save the pages:\n{error}").format(error=ex))
            return
        self._written_over(replaced)
        self.statusBar().showMessage(tr("Saved {path}").format(path=path), 4000)

    def ocr(self):
        v = self.view()
        if not v:
            return
        from . import ocr as ocrmod
        n = v.page_count()
        dlg = QDialog(self)
        dlg.setWindowTitle(tr("Recognize text (OCR)"))
        form = QFormLayout(dlg)
        rb_all = QRadioButton(tr("All"))
        rb_cur = QRadioButton(tr("Current page ({page})").format(page=v.current_page() + 1))
        rb_custom = QRadioButton(tr("Pages:"))
        custom = QLineEdit()
        custom.setPlaceholderText(tr("e.g. 1-3, 7 (of {n})").format(n=n))
        custom.textEdited.connect(lambda _t: rb_custom.setChecked(True))
        rb_all.setChecked(True)
        row = QHBoxLayout()
        for w in (rb_all, rb_cur, rb_custom, custom):
            row.addWidget(w)
        form.addRow(tr("Pages:"), row)
        skip = QCheckBox(tr("Skip pages that already contain text"))
        skip.setChecked(True)
        skip.setToolTip(tr("Pages that already have text (not scanned) are left alone, so their "
                           "text isn't duplicated"))
        form.addRow("", skip)
        acc = QComboBox()
        for key in ("auto", "fast", "normal", "high"):
            acc.addItem(ocrmod.ACCURACY_LABELS[key], key)
        acc.setCurrentIndex(max(0, acc.findData(self.settings.value("ocr_accuracy", "auto"))))
        acc.setToolTip(tr("Accuracy is how sharp a page image the recognizer gets. Higher is slower "
                          "and uses more memory; Auto starts fast and redoes a page sharper only "
                          "when its text is small or unclear."))
        form.addRow(tr("Accuracy:"), acc)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.button(QDialogButtonBox.Ok).setText(tr("Recognize"))
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
                QMessageBox.warning(self, tr("OCR"), tr("Type pages between 1 and {n}, for "
                                                        "example 1-3, 7.").format(n=n))
                return
        else:
            pages = list(range(n))
        if skip.isChecked():
            with_text = [i for i in pages if v.page_has_text(i)]
            pages = [i for i in pages if i not in with_text]
            if not pages:
                QMessageBox.information(self, tr("OCR"), tr("The chosen page(s) already have text, so "
                                                            "there's nothing to recognize. Untick \"Skip pages that "
                                                            "already contain text\" to OCR them anyway (their text "
                                                            "may then be duplicated)."))
                return
        accuracy = acc.currentData()
        self.settings.setValue("ocr_accuracy", accuracy)
        v.run_ocr(pages, accuracy)

    def flatten(self):
        v = self.view()
        if not v:
            return
        choices = [tr("All pages"), tr("Current page only")]
        pick, ok = QInputDialog.getItem(
            self, tr("Flatten"), tr("Flatten annotations and form fields into the page.\n"
                                    "They'll look the same, but no PDF program sees them as markups or fields any\n"
                                    "more: they can't be edited, moved or filled in as such.\n\n"
                                    "Not a security lock: programs that edit page content (Acrobat, PDF-XChange)\n"
                                    "can still change the page. To make changes detectable, digitally sign it\n"
                                    "with the lock against changes (certify).\n"
                                    "\n(Undo works until you close the file.)\n\nWhich pages?"), choices, 0, False)
        if not ok:
            return
        pages = None if pick == choices[0] else [v.current_page()]
        if not self._flatten_redactions_first(v, pages):
            return
        v.flatten(pages)
        self.statusBar().showMessage(tr("Flattened"), 4000)

    def _flatten_redactions_first(self, v, pages):
        """Before Flatten: redaction marks that aren't applied yet stay marks (the text under
        them is still there). Offer to apply them first. False: don't flatten."""
        n = v.pending_redactions(pages)
        if not n:
            return True
        if pages is None:
            text = tr("This document has {n} redaction mark(s) that aren't applied yet. Flatten "
                      "leaves them as marks: what's under them stays in the file until they're "
                      "applied.\n\nApply the redactions first? (This applies every mark in the "
                      "document.)")
        else:
            text = tr("This page has {n} redaction mark(s) that aren't applied yet. Flatten "
                      "leaves them as marks: what's under them stays in the file until they're "
                      "applied.\n\nApply the redactions first? (This applies every mark in the "
                      "document.)")
        box = QMessageBox(QMessageBox.Warning, tr("Flatten"), text.format(n=n), parent=self)
        apply_btn = box.addButton(tr("Apply them first"), QMessageBox.AcceptRole)
        keep_btn = box.addButton(tr("Keep them as marks"), QMessageBox.DestructiveRole)
        box.addButton(QMessageBox.Cancel)
        box.setDefaultButton(apply_btn)
        box.exec()
        if box.clickedButton() is keep_btn:
            return True
        if box.clickedButton() is not apply_btn:
            return False
        self.apply_redactions()
        return not v.pending_redactions()           # (unless that was canceled)

    # ---- signing ---------------------------------------------------------------------
    def _cache_sig(self, kind, png):
        self._sig_cache[kind] = png
        for i in range(self.tabs.count()):
            self.tabs.widget(i).set_sig_image(kind, png)

    def setup_signature(self, kind):
        dlg = signatures.SignatureSetup(self, kind)
        if dlg.exec() and dlg.png:
            self._cache_sig(kind, dlg.png)
            self.statusBar().showMessage(tr("Your initials are saved.") if kind == "initials"
                                         else tr("Your signature is saved."), 4000)

    def _on_signed(self):
        v = self.sender()
        if v is None or v.security is not None or getattr(v, "_asked_protect", False):
            return
        v._asked_protect = True
        r = QMessageBox.question(
            self, tr("Protect signed document?"),
            tr("Restrict editing of this document with a permissions password when you save it?\n\n"
               "Anyone can still open, read and print it. You choose the password, so you can "
               "unlock it later.\n\nTip: keep an unsigned copy if you may need to change it."))
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
        (pymupdf.PDF_PERM_PRINT | pymupdf.PDF_PERM_PRINT_HQ, tr("Printing"), True),
        (pymupdf.PDF_PERM_COPY, tr("Copying text and images"), True),
        (pymupdf.PDF_PERM_ANNOTATE, tr("Adding comments and markups"), False),
        (pymupdf.PDF_PERM_FORM, tr("Filling in form fields and signing"), True),
        (pymupdf.PDF_PERM_MODIFY, tr("Changing the document (text, pages, content)"), False),
        (pymupdf.PDF_PERM_ASSEMBLE, tr("Inserting, deleting and rotating pages"), False),
    ]

    def security_properties(self, preset_restrict=False):
        import json
        v = self.view()
        if v is None:
            return
        if not v.owner_authorized():
            # encrypted with a permissions password (even one that allows editing): changing
            # the protection needs that password
            self.unlock_doc()
            if not v.owner_authorized():
                return
        st = v.security_state()
        dlg = QDialog(self)
        dlg.setWindowTitle(tr("Security properties"))
        lay = QVBoxLayout(dlg)
        state = tr("encrypted ({method})").format(method=st["method"]) if st["encrypted"] \
            else tr("no security")
        now = QLabel(tr("Current: {state} - changes pending until you save").format(state=state)
                     if v.security is not None else tr("Current: {state}").format(state=state))
        lay.addWidget(now)

        def pw_pair():
            a, b = QLineEdit(), QLineEdit()
            for e in (a, b):
                e.setEchoMode(QLineEdit.Password)
            b.setPlaceholderText(tr("Type it again"))
            return a, b
        open_on = QCheckBox(tr("Require a password to open the document"))
        open_pw, open_pw2 = pw_pair()
        lay.addWidget(open_on)
        f1 = QFormLayout()
        f1.addRow(tr("Open password"), open_pw)
        f1.addRow("", open_pw2)
        lay.addLayout(f1)
        note1 = QLabel(tr("Real protection: without it, nobody can read the file. If you forget "
                          "it, the file can't be recovered."))
        note1.setWordWrap(True)
        note1.setStyleSheet("color: gray;")
        lay.addWidget(note1)
        restrict = QCheckBox(tr("Restrict printing, editing and copying"))
        own_pw, own_pw2 = pw_pair()
        lay.addWidget(restrict)
        f2 = QFormLayout()
        f2.addRow(tr("Permissions password"), own_pw)
        f2.addRow("", own_pw2)
        lay.addLayout(f2)
        lay.addWidget(QLabel(tr("Allow:")))
        boxes = []
        for flag, label, default in self.PERMS:
            c = QCheckBox(label)
            c.setChecked(default)
            boxes.append((flag, c))
            lay.addWidget(c)
        filled = v.form_filled() or preset_restrict
        if filled:
            # a filled-in or signed form is protected to keep its answers: lock its fields
            for flag, c in boxes:
                if flag == pymupdf.PDF_PERM_FORM:
                    c.setChecked(False)
            note_form = QLabel(tr("This form is filled in or signed: its fields will be locked "
                                  "(read-only in every PDF reader) so the answers can't be changed. "
                                  "Tick \"Filling in form fields\" to let others change them."))
            note_form.setWordWrap(True)
            note_form.setStyleSheet("color: gray;")
            lay.addWidget(note_form)
        note2 = QLabel(tr("Restrictions are honored by Acrobat, PDF-XChange, Bluebeam and this app, "
                          "but some free tools ignore them; form fields that aren't allowed to be "
                          "filled in are also made read-only, which every reader honors. Use an "
                          "open password for anything confidential."))
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
        presets.addItem(tr("(choose a saved policy)"))
        presets.addItems(sorted(saved))
        save_p = QPushButton(tr("Save as policy..."))
        prow.addWidget(QLabel(tr("Policy:")))
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
            name, ok = QInputDialog.getText(dlg, tr("Save security policy"), tr("Policy name:"))
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
                QMessageBox.warning(dlg, tr("Security"), tr("The open passwords are empty or don't match."))
                return
            if restrict.isChecked() and (not own_pw.text() or own_pw.text() != own_pw2.text()):
                QMessageBox.warning(dlg, tr("Security"),
                                    tr("The permissions passwords are empty or don't match."))
                return
            if open_on.isChecked() and restrict.isChecked() and open_pw.text() == own_pw.text():
                QMessageBox.warning(dlg, tr("Security"), tr("Use a different password for permissions: "
                                                            "with the same one, anyone who can open it can change it."))
                return
            dlg.accept()
        btns.accepted.connect(accept)
        lay.addWidget(btns)
        if dlg.exec() != QDialog.Accepted:
            return
        perms = pymupdf.PDF_PERM_ACCESSIBILITY | sum(f for f, c in boxes if c.isChecked())
        v.set_security(open_pw.text() if open_on.isChecked() else "",
                       own_pw.text() if restrict.isChecked() else "", perms)
        self.statusBar().showMessage(tr("Security will be applied when you save."), 5000)
        self._update_ui()

    def remove_security(self):
        v = self.view()
        if v is None:
            return
        if not v.owner_authorized():
            self.unlock_doc()
            if not v.owner_authorized():
                return
        v.set_security("", "", -1)
        self.statusBar().showMessage(tr("Security will be removed when you save."), 5000)
        self._update_ui()

    def sanitize_document(self):
        v = self.view()
        if v is None:
            return
        dlg = QDialog(self)
        dlg.setWindowTitle(tr("Sanitize document"))
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel(tr("Remove from this document:")))
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
            self.statusBar().showMessage(tr("Sanitized. Save to keep it (Undo is available)."), 5000)

    def clear_signatures(self):
        v = self.view()
        if v is None:
            return
        if QMessageBox.question(self, tr("Clear all digital signatures"),
                                tr("Remove every digital signature from this document? The "
                                   "signature fields stay, empty. Visible signature images "
                                   "you placed aren't affected.")) != QMessageBox.Yes:
            return
        n = v.clear_signatures()
        self.statusBar().showMessage(tr("Removed {n} digital signature(s).").format(n=n), 5000)
        self._update_ui()

    def timestamp_document(self):
        from . import digisign
        v = self.view()
        if v is None or self._blocked_by_security(v, tr("Timestamping")):
            return
        if v.dirty:
            QMessageBox.information(self, tr("Timestamp"), tr("Save your changes first."))
            return
        url, ok = QInputDialog.getItem(self, tr("Timestamp document"),
                                       tr("Time server (free, needs internet):"),
                                       digisign.TIME_SERVERS, 0, True)
        if not ok or not url.strip():
            return
        base, ext = os.path.splitext(v.path)
        out, _ = QFileDialog.getSaveFileName(self, tr("Save timestamped copy"),
                                             base + "_timestamped.pdf", "PDF (*.pdf)")
        if not out:
            return
        replaced = self._writing_over(out)
        if replaced is None:
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            v.timestamp(url.strip(), out)
        except Exception as ex:
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(self, tr("Timestamp"),
                                tr("Couldn't get a timestamp from {url}:\n{error}\n\nCheck your "
                                   "internet connection or try another server.").format(
                                    url=url, error=ex))
            return
        QApplication.restoreOverrideCursor()
        self._written_over(replaced)
        self.open_file(out)

    def multi_place(self):
        v = self.view()
        if v is None:
            return
        dlg = QDialog(self)
        dlg.setWindowTitle(tr("Multi-place signature or initials"))
        form = QFormLayout(dlg)
        what = QComboBox()
        what.addItem(tr("Initials"), "initials")
        what.addItem(tr("Signature"), "signature")
        form.addRow(tr("Place"), what)
        pages = QComboBox()
        pages.addItems([tr("All pages"), tr("All pages except the first"), tr("All pages except the last"),
                        tr("Pages...")])
        rng = QLineEdit()
        rng.setPlaceholderText(tr("e.g. 1-3, 5, 8"))
        form.addRow(tr("On"), pages)
        form.addRow("", rng)
        where = QComboBox()
        where.addItem(tr("Same spot as the last one I placed"), "same")
        spot_names = {"bottom right": tr("Bottom right corner"),
                      "bottom left": tr("Bottom left corner"),
                      "bottom center": tr("Bottom center"),
                      "top right": tr("Top right corner"), "top left": tr("Top left corner")}
        for spot in v.SIG_SPOTS:
            where.addItem(spot_names.get(spot, spot), spot)
        if not getattr(v, "_last_sig_spot", {}):
            where.setCurrentIndex(1)
        form.addRow(tr("Where"), where)
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
                QMessageBox.warning(self, tr("Multi-place"), tr("Type pages like 1-3, 5."))
                return
        kind = what.currentData()
        if not self._ensure_sig(kind):
            return
        spot = where.currentData()
        if spot == "same" and kind not in getattr(v, "_last_sig_spot", {}):
            spot = "bottom right"
        placed = v.place_signature_on_pages(kind, sel, spot)
        self.statusBar().showMessage(
            (tr("Placed your initials on {n} page(s).") if kind == "initials" else
             tr("Placed your signature on {n} page(s).")).format(n=placed), 5000)

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
            QMessageBox.information(self, tr("Placeholders"), tr("This document has no signature "
                                                                 "placeholders. Add them with Protect > Add signature placeholder."))
            return
        for kind in sorted({k for _i, _x, k, _r in found}):
            if not self._ensure_sig(kind):
                return
        n = v.apply_placeholders()
        self.statusBar().showMessage(tr("Filled {n} placeholder(s).").format(n=n), 5000)

    def _apply_selected_redactions(self):
        v = self.view()
        if v is None:
            return
        if QMessageBox.question(self, tr("Apply selected redactions"),
                                tr("Permanently remove what's under the selected redaction "
                                   "marks? Other marks stay pending.")) != QMessageBox.Yes:
            return
        n = v.apply_selected_redactions()
        if not n:
            QMessageBox.information(self, tr("Apply selected redactions"),
                                    tr("Select one or more redaction marks first (Select tool)."))

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
            self.statusBar().showMessage(tr("Locked objects can't be selected: untick Lock first."), 4000)
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
            self.statusBar().showMessage(tr("Locked {n} markup(s). Unlock them in the Objects "
                                            "panel or with Arrange > Unlock all markups.").format(
                                                n=n), 5000)

    def _unlock_all(self):
        v = self.view()
        if v is not None:
            self.statusBar().showMessage(tr("Unlocked {n} markup(s).").format(n=v.unlock_all()),
                                         4000)

    def _toggle_show_markups(self):
        on = self.a_show_markups.isChecked()
        DocumentView.show_markups = on
        for i in range(self.tabs.count()):
            self.tabs.widget(i).refresh_markup_display()
        self.statusBar().showMessage(tr("Markups shown") if on else
                                     tr("Markups hidden (they're still in the document)"), 4000)

    def delete_comments(self):
        v = self.view()
        if v is None:
            return
        dlg = QDialog(self)
        dlg.setWindowTitle(tr("Delete comments"))
        form = QFormLayout(dlg)
        who = QComboBox()
        who.addItem(tr("Everyone's"), None)
        me = annotations.author()
        who.addItem(tr("Only mine ({name})").format(name=me), me)
        for name in v.markup_authors():
            if name != me:
                who.addItem(tr("Only by {name}").format(name=name or tr("(no name)")), name)
        form.addRow(tr("Delete comments and markups"), who)
        where = QComboBox()
        where.addItems([tr("On all pages"), tr("On this page only")])
        form.addRow("", where)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        form.addRow(btns)
        if dlg.exec() != QDialog.Accepted:
            return
        n = v.delete_markups(who.currentData(),
                             None if where.currentIndex() == 0 else [v.current_page()])
        self.statusBar().showMessage(tr("Deleted {n} comment(s) and markup(s). Undo brings "
                                        "them back.").format(n=n), 5000)

    def flatten_comments(self):
        v = self.view()
        if not v:
            return
        choices = [tr("All pages"), tr("Current page only")]
        pick, ok = QInputDialog.getItem(
            self, tr("Flatten comments"), tr("Make comments and markups part of the page.\n"
                                             "They'll look the same, but no PDF program sees them as markups any more:\n"
                                             "they can't be edited, moved, hidden or deleted as such. Form fields stay fillable.\n\n"
                                             "Not a security lock: programs that edit page content (Acrobat, PDF-XChange)\n"
                                             "can still change the page. To make changes detectable, digitally sign it\n"
                                             "with the lock against changes (certify).\n"
                                             "\n(Undo works until you close the file.)\n\nWhich pages?"), choices, 0, False)
        if not ok:
            return
        pages = None if pick == choices[0] else [v.current_page()]
        if self._flatten_redactions_first(v, pages):
            v.flatten(pages, widgets=False)
            self.statusBar().showMessage(tr("Comments flattened"), 4000)

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
        if v.owner_authorized():
            QMessageBox.information(self, tr("Unlock"), tr("This document isn't protected."))
            return
        pw, ok = QInputDialog.getText(self, tr("Unlock"), tr("Permissions (owner) password:"),
                                      QLineEdit.Password)
        if ok and pw:
            if v.unlock(pw):
                self.statusBar().showMessage(tr("Unlocked: you can edit this document and change "
                                                "its security now."), 4000)
            else:
                QMessageBox.warning(self, tr("Unlock"), tr("That password doesn't unlock editing."))
            self._update_ui()

    # ---- export ------------------------------------------------------------------------
    def export_as(self, eid):
        v = self.view()
        if not v or not v.require_permission(pymupdf.PDF_PERM_COPY, tr("Exporting")):
            return
        _id, label, flt, ext = next(e for e in EXPORTS if e[0] == eid)
        base = os.path.splitext(v.path)[0]
        path, _ = QFileDialog.getSaveFileName(self, tr("Export"), f"{base}.{ext}", flt)
        if not path:
            return
        pages = None
        if v.page_count() > 1:
            choices = [tr("All pages"), tr("Current page")]
            pick, ok = QInputDialog.getItem(self, tr("Export"), tr("Pages:"), choices, 0, False)
            if not ok:
                return
            pages = None if pick == choices[0] else [v.current_page()]
        units = None
        if eid == "dxf":
            # export.UNITS' keys are what to_dxf takes: shown in the user's language
            names = {"inches": tr("inches"), "millimeters": tr("millimeters"),
                     "PDF points (1:1)": tr("PDF points (1:1)")}
            keys = list(export.UNITS)
            shown = [names.get(k, k) for k in keys]
            unit, ok = QInputDialog.getItem(
                self, tr("AutoCAD export"), tr("Drawing units (1 inch on paper = 1 unit if inches):"),
                shown, 0, False)
            if not ok:
                return
            units = keys[shown.index(unit)]
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
        dlg = QProgressDialog(tr("Exporting to {format}...").format(
            format=label.replace('&', '').rstrip('.')), None, 0, 0, self)
        dlg.setWindowTitle(tr("Export"))
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
            QMessageBox.critical(self, tr("Export failed"), str(ex))
            return
        msg = tr("Exported to {path}").format(path=path)
        if eid == "excel" and result == 0:
            msg += "\n\n" + tr("No tables were detected, so each page's text was exported row "
                               "by row.")
        elif eid in ("png", "jpg"):
            msg = tr("Exported {n} image(s) next to {path}").format(n=len(result), path=path)
        elif eid == "dxf":
            msg += "\n\n" + tr("{lines} lines, {curves} curves and {text} text items. Images in "
                               "the PDF aren't included.").format(
                lines=result['lines'], curves=result['curves'], text=result['text'])
        elif eid == "ppt":
            msg += "\n\n" + tr("Each page is a picture on its slide; its text is in the speaker "
                               "notes.")
        QMessageBox.information(self, tr("Export"), msg)

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

    def link_sheet_callouts(self):
        """Pages > Link sheet callouts...: sheet numbers from the title blocks, then a link on
        every callout, note and index line that names one of the sheets."""
        from .sheets_ui import SheetLinksDialog
        from . import sheets
        v = self.view()
        if not v or not v.require_permission(pymupdf.PDF_PERM_ANNOTATE, tr("Adding links")):
            return
        folder = os.path.dirname(v.path) if v.path and os.path.isdir(os.path.dirname(v.path)) else None
        dlg = SheetLinksDialog(self, v.doc, folder)
        if dlg.exec() != QDialog.Accepted or not dlg.result_plan:
            return
        pl = dlg.result_plan
        made = {}

        def do():
            made["links"], made["marks"] = sheets.apply(v.doc, pl, show_box=dlg.box.isChecked(),
                                                        bookmarks=dlg.marks.isChecked())
        pages = sorted({i for i, _r, _t in pl["links"]})
        v.modify(do, pages or [], permission=pymupdf.PDF_PERM_ANNOTATE)
        if dlg.marks.isChecked():
            v.documentChanged.emit()
        if made.get("marks"):
            msg = tr("{links} link(s) made on {pages} page(s); {marks} bookmark(s) added "
                     "(Ctrl+Z undoes it)").format(links=made.get('links', 0), pages=len(pages),
                                                  marks=made['marks'])
        else:
            msg = tr("{links} link(s) made on {pages} page(s) (Ctrl+Z undoes it)").format(
                links=made.get('links', 0), pages=len(pages))
        self.statusBar().showMessage(msg, 6000)
        self._update_ui()

    def read_sheet_scales(self):
        """Measure > Read scales from title blocks: every page gets the scale its own title
        block (or first scale note) says; pages without one, or marked not to scale, are left
        as they are and listed."""
        from . import measure
        v = self.view()
        if not v:
            return
        scales, none, nts = {}, [], []
        for i in range(v.page_count()):
            note = v.sheet_scale_note(i)
            if note is None:
                none.append(i + 1)
            elif note["ratio"] is None:
                nts.append(i + 1)
            else:
                scales[i] = (measure.scale_from_preset(note["ratio"]), note["unit"], note["label"])
        if scales:
            v.set_page_scales(scales)
        lines = [tr("Scale set on {n} of {total} page(s) from what the sheets say.").format(
                     n=len(scales), total=v.page_count())
                 if scales else tr("No sheet in this document says its scale.")]
        if len(set(scales.values())) > 1:
            lines.append(tr("The sheets use different scales; each page got its own."))
        if nts:
            lines.append(tr("Marked not to scale, left as is: page {pages}").format(
                pages=", ".join(map(str, nts[:20]))))
        if none:
            lines.append(tr("No scale note found, left as is: page {pages}").format(
                pages=", ".join(map(str, none[:20])) + (" ..." if len(none) > 20 else "")))
        lines.append(tr("A sheet printed at reduced size still says its original scale: check "
                        "one dimension, and use Calibrate Tape Measure if it is off."))
        QMessageBox.information(self, tr("Read scales from title blocks"), "\n\n".join(lines))
        if scales:
            self.statusBar().showMessage(v.page_scale_text(v.current_page()), 5000)
            self._update_ui()

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
        self.statusBar().showMessage(tr("Tool chest: next markups use this style. "
                                        "Pick a tool from the toolbar to go back to defaults."), 5000)

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
            QMessageBox.information(self, tr("Tool chest"), tr("Select a markup (or pick a markup "
                                                               "tool) first, then click Add."))
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
            QMessageBox.information(self, tr("Remove background"), tr("No page in this document has a "
                                                                      "background added with Document > Background."))
            return
        dlg = QDialog(self)
        dlg.setWindowTitle(tr("Remove background"))
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel(tr("{n} page(s) have a background added with Document > "
                                "Background. Remove it from:").format(n=len(have))))
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
                self, tr("Remove watermarks"), tr("No watermark found that can be removed. KanzonasPDF "
                                                  "finds watermarks added with Document > Watermark and by apps that mark them as "
                                                  "watermarks (Adobe Acrobat, PDF-XChange and others). Text or pictures that are "
                                                  "simply part of the page can be taken out with Erase content or Edit objects."))
            return
        dlg = QDialog(self)
        dlg.setWindowTitle(tr("Remove watermarks"))
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel(tr("{n} page(s) have a watermark. Remove it from:").format(
            n=len(have))))
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
        # page_tools.COMPRESS's keys are what compress() takes: shown in the user's language
        names = {"Good quality (150 dpi images)": tr("Good quality (150 dpi images)"),
                 "Smaller (100 dpi images)": tr("Smaller (100 dpi images)"),
                 "Smallest (72 dpi images)": tr("Smallest (72 dpi images)")}
        keys = list(page_tools.COMPRESS)
        shown = [names.get(k, k) for k in keys]
        preset, ok = QInputDialog.getItem(self, tr("Compress"), tr("Image quality:"),
                                          shown, 1, False)
        if not ok:
            return
        preset = keys[shown.index(preset)]
        base = os.path.splitext(v.path)[0]
        path, _ = QFileDialog.getSaveFileName(self, tr("Save smaller copy"), base + "_small.pdf", PDF_FILTER)
        if not path:
            return
        replaced = self._writing_over(path, source=v)
        if replaced is None:
            return
        try:
            before, after = page_tools.compress(v.doc.tobytes(), path, preset)
        except Exception as ex:
            QMessageBox.critical(self, tr("Compress failed"), str(ex))
            return
        self._written_over(replaced)
        QMessageBox.information(self, tr("Compress"),
                                tr("Saved {path}\n\n{before} MB \u2192 {after} MB ({percent}% "
                                   "smaller)").format(
                                    path=path, before=f"{before / 1e6:.2f}",
                                    after=f"{after / 1e6:.2f}",
                                    percent=f"{100 - after * 100 / max(1, before):.0f}"))

    def search_redact(self):
        v = self.view()
        if not v:
            return
        text, ok = QInputDialog.getText(self, tr("Search & redact"),
                                        tr("Mark every occurrence of this text for redaction:"))
        if ok and text.strip():
            term = text.strip()
            hidden = v.hidden_matches(term)
            n = v.search_redact(term)
            extra = [what.format(n=c) for what, c in (
                (tr("{n} form field(s)"), hidden["fields"]),
                (tr("{n} markup note(s)"), hidden["markups"]), (tr("{n} link(s)"), hidden["links"]),
                (tr("{n} bookmark(s)"), hidden["bookmarks"]),
                (tr("{n} document propert(ies)"), hidden["metadata"])) if c]
            msg = (tr("Marked {n} occurrence(s) on the pages.").format(n=n) if n else
                   tr("No matches on the pages."))
            if extra and not n:
                if QMessageBox.question(
                        self, tr("Search & redact"),
                        tr("Not on the pages, but found in {places}.\n\nRemove it from there "
                           "now? (Fields, links, stamps and attachments containing it are "
                           "deleted; in notes, bookmarks and properties it's replaced by "
                           "[redacted]. Undo works until you close the file.)").format(
                            places=", ".join(extra))) == QMessageBox.Yes:
                    v.remove_term(term)
                    self.statusBar().showMessage(tr("Removed. Save to make it permanent."), 6000)
                return
            if extra:
                msg += "\n\n" + tr("Also found in {places}. Those can't be covered with a box. "
                                   "When you apply the redactions, fields, links, stamps and "
                                   "attachments containing it are deleted; in notes, bookmarks "
                                   "and properties it's replaced by [redacted].").format(
                    places=", ".join(extra))
            if n:
                msg += "\n\n" + tr("Review the marks, then use Apply redactions.")
            QMessageBox.information(self, tr("Search & redact"), msg)

    def apply_redactions(self):
        v = self.view()
        if not v:
            return
        n = v.pending_redactions()
        if not n:
            QMessageBox.information(self, tr("Redaction"), tr("Nothing is marked for redaction yet. "
                                                              "Use the Redact tool or Search & redact first."))
            return
        box = QMessageBox(QMessageBox.Warning, tr("Apply redactions"),
                          tr("Permanently remove everything under {n} redaction mark(s)? Text, "
                             "images and drawings there are deleted, not just covered.\n\n"
                             "Undo works until you close the file.").format(n=n), parent=self)
        scrub = QCheckBox(tr("Remove hidden information (metadata, attachments, hidden text, scripts)"))
        scrub.setChecked(True)
        box.setCheckBox(scrub)
        box.setStandardButtons(QMessageBox.Apply | QMessageBox.Cancel)
        if box.exec() == QMessageBox.Apply:
            v.apply_redactions(scrub.isChecked())
            self.statusBar().showMessage(
                tr("Applied {n} redaction(s). Save to make it permanent.").format(n=n), 6000)

    # ---- digital signatures ----------------------------------------------------------
    def _blocked_by_security(self, v, what):
        """Signing or timestamping a password-protected PDF isn't supported (the signing
        library can't read the encryption PyMuPDF writes). Explain instead of failing."""
        pending = v.security is not None and (v.security.get("open_pw") or v.security.get("owner_pw"))
        if v.security_state()["encrypted"] or pending:
            QMessageBox.information(
                self, what, tr("{what} isn't possible on a password-protected PDF yet.\n\n"
                               "Use Protect > Remove security and save, then sign. Note that "
                               "adding a password after signing changes the file and makes the "
                               "signature invalid, so sign the final version.").format(what=what))
            return True
        return False

    def digital_sign(self):
        from . import digisign
        v = self.view()
        if not v or self._blocked_by_security(v, tr("Digital signing")):
            return
        dlg = QDialog(self)
        dlg.setWindowTitle(tr("Digitally sign with a certificate"))
        lay = QVBoxLayout(dlg)
        info = QLabel(tr("A digital signature proves who signed and that the document hasn't "
                         "changed since. Tip: place your visible signature first (Sign tool), "
                         "then sign digitally. The signed copy is saved as a new file."))
        info.setWordWrap(True)
        lay.addWidget(info)
        form = QFormLayout()
        mine = QRadioButton(tr("My personal certificate") if os.path.exists(digisign.my_cert_path())
                            else tr("My personal certificate (created now)"))
        other = QRadioButton(tr("Certificate file from a certificate authority / my company (.pfx, .p12)"))
        win = QRadioButton(tr("Certificate stored in Windows (cards and tokens too)"))
        win_list = QComboBox()
        win_certs = []
        if os.name == "nt":
            try:
                from . import wincerts
                win_certs = wincerts.list_certificates()
            except Exception:
                win_certs = []
        for c in win_certs:
            issuer = tr("yourself") if c["self_signed"] else c["issuer"]
            date = c["expires"].strftime("%Y-%m-%d")
            label = (tr("{name}  (issued by {issuer}, EXPIRED {date})") if c["expired"] else
                     tr("{name}  (issued by {issuer}, expires {date})")).format(
                name=c["name"], issuer=issuer, date=date)
            win_list.addItem(label, c["thumbprint"])
        if not win_certs:
            win_list.addItem(tr("No signing certificates in your Windows Personal store"))
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
        browse = QPushButton(tr("Browse..."))
        browse.clicked.connect(lambda: cert_path.setText(QFileDialog.getOpenFileName(
            dlg, tr("Certificate"), "", tr("Certificates") + " (*.pfx *.p12)")[0]
            or cert_path.text()))
        row = QHBoxLayout()
        row.addWidget(cert_path)
        row.addWidget(browse)
        password = QLineEdit()
        password.setEchoMode(QLineEdit.Password)
        reason = QComboBox()
        reason.setEditable(True)
        reason.addItems([tr("I approve this document"), tr("I am the author of this document"),
                         tr("I have reviewed this document"), tr("I agree to the terms")])
        location = QLineEdit()
        lock = QCheckBox(tr("Lock the document: no further changes allowed (certify)"))
        form.addRow(win)
        form.addRow(tr("Windows certificate"), win_list)
        form.addRow(mine)
        form.addRow(other)
        form.addRow(tr("Certificate file"), row)
        form.addRow(tr("Certificate password"), password)
        form.addRow(tr("Reason"), reason)
        form.addRow(tr("Location"), location)
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
                    name, ok = QInputDialog.getText(self, tr("Create your certificate"),
                                                    tr("Your full name (shown as the signer):"),
                                                    text=annotations.author())
                    if not ok or not name.strip():
                        return
                    email, _ok = QInputDialog.getText(self, tr("Create your certificate"),
                                                      tr("Email (optional):"))
                    if not password.text():
                        QMessageBox.warning(self, tr("Certificate"), tr("Choose a certificate password "
                                                                        "in the signing dialog to protect your certificate."))
                        return
                    digisign.create_certificate(name.strip(), email.strip(), "", password.text())
            else:
                path = cert_path.text()
                if not os.path.isfile(path):
                    QMessageBox.warning(self, tr("Certificate"), tr("Choose a certificate file."))
                    return
            if not win.isChecked():
                signer = digisign.load_signer(path, password.text())
                self.settings.setValue("sign_source", "file")
        except Exception as ex:
            QMessageBox.warning(self, tr("Certificate"),
                                tr("Couldn't use that certificate: {error}").format(error=ex))
            return
        base = os.path.splitext(v.path)[0]
        out, _ = QFileDialog.getSaveFileName(self, tr("Save signed copy as"), base + "_signed.pdf",
                                             PDF_FILTER)
        if not out:
            return
        replaced = self._writing_over(out, source=v)
        if replaced is None:
            return
        try:
            digisign.sign(v.doc.tobytes(), out, signer, reason.currentText(), location.text(),
                          lock.isChecked())
        except Exception as ex:
            QMessageBox.critical(self, tr("Signing failed"), str(ex))
            return
        self._written_over(replaced)
        self.open_file(out)

    def signature_details(self):
        v = self.view()
        if not v:
            return
        res = getattr(v, "sig_results", [])
        if not res:
            QMessageBox.information(self, tr("Digital signatures"), tr("This document has no digital "
                                                                       "(certificate) signatures."))
            return
        lines = []
        for r in res:
            lines.append(r["summary"])
            if r.get("reason"):
                lines.append("   " + tr("Reason: {reason}").format(reason=r['reason']))
            if r.get("email"):
                lines.append("   " + tr("Email: {email}").format(email=r['email']))
            if r.get("fingerprint"):
                lines.append("   " + tr("Certificate fingerprint: {fingerprint}...").format(
                    fingerprint=r['fingerprint'][:32]))
        box = QMessageBox(QMessageBox.Information, tr("Digital signatures"), "\n".join(lines), parent=self)
        untrusted = [r for r in res if r.get("fingerprint") and not r.get("trusted")]
        trust_btn = box.addButton(tr("Trust these signers on this computer"), QMessageBox.ActionRole) \
            if untrusted else None
        box.addButton(QMessageBox.Close)
        box.exec()
        if trust_btn is not None and box.clickedButton() is trust_btn:
            from . import digisign
            for r in untrusted:
                digisign.trust(r["fingerprint"])
            v.check_digital_signatures()

    # ---- compare --------------------------------------------------------------------
    def _toggle_spelling(self, on):
        from . import spelling
        spelling.set_enabled(on)

    def replace_text(self):
        from .replace_dialog import ReplaceDialog
        v = self.view()
        if not v:
            return
        sel = (v.selected_text() or "").strip().split("\n")[0]
        ReplaceDialog(self, v, sel).exec()

    def compare_documents(self):
        from . import compare
        from .compare_ui import CompareModeDialog
        v = self.view()
        if not v:
            return
        path, _ = QFileDialog.getOpenFileName(self, tr("Compare with which earlier revision?"),
                                              os.path.dirname(v.path), PDF_FILTER)
        if not path:
            return
        try:
            with open(path, "rb") as f:
                old = f.read()
        except OSError as ex:
            QMessageBox.critical(self, tr("Compare"), str(ex))
            return
        new = v.doc.tobytes()
        old_name, new_name = os.path.basename(path), os.path.basename(v.path)
        try:
            texty = compare.has_text(v.doc) and \
                compare.has_text(pymupdf.open(stream=old, filetype="pdf"))
        except Exception:
            texty = False
        choice = CompareModeDialog(self, old_name, new_name, texty)
        if choice.exec() != QDialog.Accepted:
            return
        mode = choice.mode()
        dlg = QProgressDialog(tr("Comparing pages..."), None, 0, 0, self)
        dlg.setWindowTitle(tr("Compare"))
        dlg.setWindowModality(Qt.WindowModal)
        dlg.setMinimumDuration(300)
        pool = ThreadPoolExecutor(max_workers=1)
        if mode == "text":
            fut = pool.submit(compare.compare_text, old, new, None, old_name, new_name)
        else:
            fut = pool.submit(compare.compare, old, new, 110, None, old_name, new_name)
        while not fut.done():
            QApplication.processEvents()
            time.sleep(0.03)
        dlg.close()
        pool.shutdown(wait=False)
        try:
            data, counts = fut.result()
        except Exception as ex:
            QMessageBox.critical(self, tr("Compare failed"), str(ex))
            return
        import tempfile
        # (a name of our own for the result; the two file names in it stay as they are)
        stem = tr("Compare - {old} vs {new}.pdf").format(old=os.path.splitext(old_name)[0],
                                                         new=os.path.splitext(new_name)[0])
        out = os.path.join(tempfile.mkdtemp(prefix="kzcompare"), stem)
        with open(out, "wb") as f:
            f.write(data)
        self.open_file(out)
        self.markups_dock.show()
        found = tr("Found {changes} change(s) on {pages} of {total} page(s).").format(
            changes=sum(counts), pages=sum(1 for c in counts if c), total=len(counts)) + "\n\n"
        if mode == "text":
            QMessageBox.information(self, tr("Compare"), found + tr(
                                    "Blue = words added in this revision; a red mark shows "
                                    "where words of the earlier one were removed (its comment "
                                    "says which). Pictures added, removed or resized are boxed. "
                                    "Every change is listed in the Markups list and on the "
                                    "summary page at the end. Use Save As to keep the comparison."))
        else:
            QMessageBox.information(self, tr("Compare"), found + tr(
                                    "Red = only in the earlier revision, blue = only in this one. "
                                    "Each change is clouded and listed in the Markups list. "
                                    "Use Save As to keep the comparison."))

    # ---- appearance -------------------------------------------------------------------
    TOOLBAR_ICON_KEYS = {"a_open": "open", "a_save": "save", "a_print": "print", "a_undo": "undo",
                         "a_redo": "redo", "a_zoom_in": "zoom_in", "a_zoom_out": "zoom_out",
                         "a_fit_width": "fit_width", "a_fit_page": "fit_page", "a_ocr": "ocr",
                         "a_rot_l": "rot_l", "a_rot_r": "rot_r", "a_cad_mouse": "cad_mouse",
                         "a_free_pan": "free_pan", "a_mouse_standard": "select",
                         "a_mouse_hand": "hand",
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
        self.zoom_box.setToolTip(tr("Zoom level: pick one or type a percentage and press Enter"))
        self.page_spin.setToolTip(tr("Current page: type a page number and press Enter"))
        self.search.setToolTip(tr("Find text in this document (Ctrl+F). Enter or F3 = next match, "
                                  "Shift+Enter or Shift+F3 = previous"))
        self.shapes_btn.setToolTip(tr("Shapes: click for the shape shown, or the arrow to pick "
                                      "another (rectangle, ellipse, cloud, polygon, line, arrow, "
                                      "polyline, pen). Hold Shift for squares, circles and straight lines"))
        self.measure_btn.setToolTip(tr("Measure: click for the tool shown, or the arrow for length, "
                                       "polylength, area, count, calibrate and scale"))

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
        if v is None or not hasattr(v, "pages") or not v.pages or v.untitled:
            return
        states = self._file_states()
        key = os.path.normcase(v.path)
        states.pop(key, None)                      # moves to the end: the most recent
        states[key] = {"page": v.current_page(), "zoom": round(v.zoom, 4)}
        if len(states) > 200:                      # keep the 200 most recent
            states = dict(list(states.items())[-200:])
        self.settings.setValue("file_states", json.dumps(states))

    # ---- split view -----------------------------------------------------------------------
    def _build_split(self):
        self.split_dock = QDockWidget(tr("Second view"))
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
        self.split_dock.setWindowTitle(
            tr("Second view: {name} (scroll independently; edit in the main view)").format(
                name=os.path.basename(v.path)))

    # ---- keyboard shortcuts --------------------------------------------------------------
    @staticmethod
    def action_name(a):
        """An action's name as the user sees it: its menu text without the & and the "..."."""
        return a.text().split("\t")[0].replace("&", "").strip().rstrip(".")

    def _shortcut_actions(self):
        """{stable id: QAction} for every action that can have a shortcut. The id is the
        action's English name (also in another language), so shortcuts saved by name and the
        palette's recent commands survive a change of language; action_name(a) is the name
        to show."""
        out = {}
        for a in self.findChildren(QAction):
            if a.parent() is not self:        # skip panels' own small menus
                continue
            name = english_name(a.text()).split("\t")[0].replace("&", "").strip().rstrip(".")
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
        # the built-in shortcuts, so only the ones a user changes are saved (a later release
        # can then improve a default the user never touched)
        self._default_shortcuts = {n: a.shortcut().toString() for n, a in acts.items()}
        for name, seq in saved.items():
            if name in acts:
                acts[name].setShortcut(QKeySequence(seq))

    def edit_shortcuts(self):
        import json
        from PySide6.QtWidgets import QTableWidget, QTableWidgetItem, QKeySequenceEdit, QHeaderView
        acts = self._shortcut_actions()
        dlg = QDialog(self)
        dlg.setWindowTitle(tr("Keyboard shortcuts"))
        dlg.resize(560, 600)
        lay = QVBoxLayout(dlg)
        intro = QLabel(tr("Click a shortcut and press the new key combination. "
                          "Clear it with Backspace. Ctrl+Shift+Plus/Minus always rotate."))
        intro.setWordWrap(True)         # (longer in other languages: don't widen the dialog)
        lay.addWidget(intro)
        filt = QLineEdit()
        filt.setPlaceholderText(tr("Filter"))
        lay.addWidget(filt)
        shown = {n: self.action_name(a) for n, a in acts.items()}     # in the user's language
        names = sorted(acts, key=lambda n: shown[n].lower())
        table = QTableWidget(len(names), 2)
        table.setHorizontalHeaderLabels([tr("Command"), tr("Shortcut")])
        table.verticalHeader().hide()
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        editors = {}
        for r, name in enumerate(names):
            item = QTableWidgetItem(shown[name])
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            table.setItem(r, 0, item)
            ed = QKeySequenceEdit(acts[name].shortcut())
            table.setCellWidget(r, 1, ed)
            editors[name] = ed
        # (the English name finds a command too)
        filt.textChanged.connect(lambda t: [table.setRowHidden(
            r, t.lower() not in shown[n].lower() and t.lower() not in n.lower())
            for r, n in enumerate(names)])
        lay.addWidget(table)
        row = QHBoxLayout()
        reset = QPushButton(tr("Reset all to defaults"))
        row.addWidget(reset)
        row.addStretch(1)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        row.addWidget(btns)
        lay.addLayout(row)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)

        def do_reset():
            self.settings.remove("shortcuts")
            QMessageBox.information(dlg, tr("Keyboard shortcuts"),
                                    tr("Default shortcuts come back the next time you start the app."))
            dlg.reject()
        reset.clicked.connect(do_reset)
        if not dlg.exec():
            return
        seen, clashes = {}, []
        for name, ed in editors.items():
            seq = ed.keySequence().toString()
            if seq:
                if seq in seen:
                    clashes.append(f"{seq}: {shown[seen[seq]]} / {shown[name]}")
                seen[seq] = name
        if clashes:
            # a key on two commands runs neither: change nothing until that's sorted out
            QMessageBox.warning(self, tr("Keyboard shortcuts"),
                                tr("Nothing was changed: these shortcuts are used twice:")
                                + "\n" + "\n".join(clashes))
            return
        defaults = getattr(self, "_default_shortcuts", {})
        saved = {}
        for name, ed in editors.items():
            seq = ed.keySequence().toString()
            if seq != acts[name].shortcut().toString():
                acts[name].setShortcut(QKeySequence(seq))
            if seq != defaults.get(name, ""):
                saved[name] = seq
        self.settings.setValue("shortcuts", json.dumps(saved))
        self._apply_icons()

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
        dlg.setWindowTitle(tr("Grid settings"))
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
        form.addRow(tr("Grid spacing (on paper)"), row)
        major = QSpinBox()
        major.setRange(1, 100)
        major.setValue(int(self.settings.value("grid_major", 4)))
        form.addRow(tr("Darker line every"), major)
        show = QCheckBox(tr("Show grid"))
        show.setChecked(self.a_grid.isChecked())
        snap = QCheckBox(tr("Snap to grid"))
        snap.setChecked(self.a_snap_grid.isChecked())
        objs = QCheckBox(tr("Snap to objects"))
        objs.setChecked(self.a_snap_objects.isChecked())
        pagebox = QCheckBox(tr("Snap to page"))
        pagebox.setChecked(self.a_snap_page.isChecked())
        for c in (show, snap, objs, pagebox):
            form.addRow("", c)
        hint = QLabel(tr("Hold Alt while drawing or dragging to place a point without snapping."))
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
        dlg.setWindowTitle(tr("Attachments"))
        dlg.resize(640, 360)
        lay = QVBoxLayout(dlg)
        table = QTableWidget(0, 3)
        table.setHorizontalHeaderLabels([tr("File"), tr("Size"), tr("Where")])
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
                table.setItem(r, 2, QTableWidgetItem(tr("Page {page}").format(page=pg + 1)
                                                     if pg is not None else tr("Document")))
            empty.setVisible(not rows)
        empty = QLabel(tr("This PDF has no attached files. Use the Attach file tool to add one."))
        lay.addWidget(empty)

        def current():
            r = table.currentRow()
            return rows[r] if 0 <= r < len(rows) else None
        btns = QHBoxLayout()
        for label, fn in ((tr("Open"), lambda c: v.open_attachment(c[0], c[1], c[2])),
                          (tr("Save as..."), lambda c: v.save_attachment(c[0], c[1], c[2])),
                          (tr("Go to"), lambda c: c[0] is not None and v.reveal(c[0], c[1])),
                          (tr("Delete"), lambda c: (v.delete_attachment(c[0], c[1]), fill()))):
            b = QPushButton(label)
            b.clicked.connect(lambda _=False, f=fn: current() and f(current()))
            btns.addWidget(b)
        btns.addStretch(1)
        close = QPushButton(tr("Close"))
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

    def set_mouse_mode(self, m, toggle=False):
        """Standard, Hand or CAD. toggle (F11, the CAD button): CAD again goes back to the
        mode used before it."""
        from . import mouse_modes
        old = mouse_modes.mode(self.settings)
        if toggle and m == "cad" and old == "cad":
            m = self.settings.value("mouse_before_cad", "hand")
            m = m if m in ("standard", "hand") else "hand"
        if m == "cad" and old != "cad":
            self.settings.setValue("mouse_before_cad", old)
        self.settings.setValue("mouse_mode", m)
        self.apply_mouse_mode()
        self.set_tool(mouse_modes.default_tool(m))
        self.statusBar().showMessage(tr("Mouse: {mode}. {what}").format(
            mode=mouse_modes.labels()[m], what=mouse_modes.descriptions()[m]), 5000)

    def apply_mouse_mode(self):
        """After the mode or one of its options changed: every window and document follows."""
        from . import mouse_modes
        mouse_modes.apply(self.settings)
        for w in windows():
            w._sync_mouse_actions()
        for v in self._all_views():
            v.apply_canvas()        # open canvas around the pages, or not
            v._tool_cursor()        # a plus in CAD mode

    def _sync_mouse_actions(self):
        from . import mouse_modes
        m = mouse_modes.mode(self.settings)
        {"standard": self.a_mouse_standard, "hand": self.a_mouse_hand,
         "cad": self.a_cad_mouse}[m].setChecked(True)
        self.a_free_pan.setChecked(mouse_modes.option(self.settings, m, "free_pan"))
        self.a_page_wheel.setChecked(mouse_modes.option(self.settings, m, "page_wheel"))
        self.a_page_wheel.setEnabled(m != "cad")      # (in CAD mode the wheel zooms)
        ribbon = getattr(self, "ribbon", None)
        cad_tab = getattr(self, "_cad_tab", None)
        if ribbon is not None and cad_tab is not None:
            i = ribbon.indexOf(cad_tab)
            show = m == "cad" and mouse_modes.option(self.settings, "cad", "cad_tab")
            if i >= 0 and ribbon.isTabVisible(i) != show:
                if not show and ribbon.currentIndex() == i:
                    ribbon.setCurrentIndex(0)
                ribbon.setTabVisible(i, show)
        menu = getattr(self, "cad_menu", None)
        if menu is not None:
            menu.menuAction().setVisible(m == "cad")

    def _toggle_mouse_option(self, key, action):
        """View > Free page movement / Scroll one page per wheel step: for the mode in use."""
        from . import mouse_modes
        m = mouse_modes.mode(self.settings)
        mouse_modes.set_option(self.settings, m, key, action.isChecked())
        self.apply_mouse_mode()
        if key == "page_wheel":
            self.statusBar().showMessage(
                tr("Scroll wheel: one page per step when the whole page fits (zoom with Fit page)")
                if action.isChecked() else tr("Scroll wheel: smooth scrolling"), 4000)

    def preferences(self):
        from .preferences import PreferencesDialog
        PreferencesDialog(self).exec()

    def _toggle_thin_lines(self):
        on = self.a_thin_lines.isChecked()
        DocumentView.thin_lines = on
        self.settings.setValue("thin_lines", "true" if on else "false")
        for w in windows():
            w.a_thin_lines.setChecked(on)
            for v in w._views():
                v.redraw_pages()
        self.statusBar().showMessage(tr("Thin lines drawn at least a pixel wide") if on else
                                     tr("Lines drawn at their true width"), 3000)

    def _toggle_night(self):
        on = self.a_night.isChecked()
        DocumentView.night_mode = on
        self.settings.setValue("night_mode", "true" if on else "false")
        for w in windows():
            w.a_night.setChecked(on)
            for v in w._views():
                v.redraw_pages()
        self.statusBar().showMessage(tr("Night mode on: pages drawn white on black (F12 turns it "
                                        "off); printing and export are unchanged") if on else
                                     tr("Night mode off"), 4000)

    # ---- ribbon --------------------------------------------------------------------------
    # short labels for ribbon buttons (the menus keep the full names)
    RIBBON_LABELS = {
        "a_fit_width": tr("Fit width"), "a_fit_page": tr("Fit page"), "a_actual": tr("Actual size"),
        "a_cad_mouse": tr("CAD"), "a_mouse_standard": tr("Standard"), "a_mouse_hand": tr("Hand"),
        "a_free_pan": tr("Free movement"), "a_grid": tr("Grid"), "a_snap_grid": tr("Snap to grid"),
        "a_snap_objects": tr("Snap to objects"), "a_snap_page": tr("Snap to page"),
        "a_grid_settings": tr("Grid settings"),
        "a_set_scale": tr("Set scale"), "a_sheet_scales": tr("Sheet scales"), "a_measure_summary": tr("Summary"), "a_ocr": tr("OCR"),
        "a_rot_l": tr("Rotate left"), "a_rot_r": tr("Rotate right"), "a_lock": tr("Lock"),
        "a_unlock_all": tr("Unlock all"), "a_prev_markup": tr("Previous"), "a_next_markup": tr("Next"),
        "a_markups": tr("Markups list"), "a_show_markups": tr("Show markups"),
        "a_cards": tr("Comment boxes"), "a_delete_markups": tr("Delete comments"),
        "a_flatten_markups": tr("Flatten comments"), "a_multi_sign": tr("Multi-place"),
        "a_setup_sig": tr("My signature"), "a_setup_init": tr("My initials"),
        "a_apply_placeholders": tr("Apply all"), "a_digisign": tr("Digital sign"),
        "a_timestamp": tr("Timestamp"), "a_sig_details": tr("Signature details"),
        "a_clear_sigs": tr("Clear signatures"), "a_search_redact": tr("Search and redact"),
        "a_apply_sel_redact": tr("Apply selected"), "a_apply_redact": tr("Apply all"),
        "a_security": tr("Security"), "a_remove_security": tr("Remove security"), "a_unlock": tr("Unlock"),
        "a_sanitize": tr("Sanitize"), "a_hl_fields": tr("Highlight fields"), "a_move_up": tr("Move up"),
        "a_move_down": tr("Move down"), "a_del_page": tr("Delete"), "a_insert_pdf": tr("Insert file"), "a_sheet_links": tr("Sheet callouts"), "a_combine": tr("Combine files"), "a_from_images": tr("From images"), "a_new": tr("New PDF"),
        "a_insert_blank": tr("Blank page"), "a_extract": tr("Extract"), "a_header": tr("Header and footer"),
        "a_watermark": tr("Watermark"), "a_background": tr("Background"),
        "a_remove_bg": tr("Remove background"), "a_remove_wm": tr("Remove watermarks"), "a_bookmarks": tr("Bookmarks"), "a_attachments": tr("Attachments"),
        "a_compress": tr("Compress"), "a_compare": tr("Compare"), "a_flatten": tr("Flatten"),
        "a_sidebar": tr("Pages panel"), "a_props": tr("Properties"), "a_chest": tr("Tool chest"), "a_night": tr("Night mode"),
        "a_split": tr("Split view"), "a_labels": tr("Toolbar labels"), "a_shortcuts": tr("Shortcuts"),
        "a_manual": tr("User manual"), "a_palette": tr("Command palette"), "a_ribbon": tr("Ribbon"), "a_collapse": tr("Collapse"), "a_group_names": tr("Group names"), "a_menu_bar": tr("Menu bar"),
        "a_zoom_in": tr("Zoom in"), "a_zoom_out": tr("Zoom out"), "a_open": tr("Open"), "a_save": tr("Save"),
        "a_print": tr("Print"), "al_left": tr("Left"), "al_hcenter": tr("Center"), "al_right": tr("Right"),
        "al_top": tr("Top"), "al_vmiddle": tr("Middle"), "al_bottom": tr("Bottom"),
        "dist_h": tr("Horizontally"), "dist_v": tr("Vertically"), "z_front": tr("To front"),
        "z_forward": tr("Forward"), "z_backward": tr("Backward"), "z_back": tr("To back"),
        "tool_redact": tr("Redact"), "tool_placeholder": tr("Placeholder"),
        "tool_erasecontent": tr("Erase content"), "tool_capture": tr("Capture"),
        "tool_crop": tr("Crop"), "a_uncrop": tr("Remove crop"), "tool_link": tr("Links"),
        "tool_editobjects": tr("Edit objects"), "tool_addtext": tr("Add text"),
    }
    RIBBON_ICONS = {
        "a_actual": "numeric-1-box-outline", "a_set_scale": "ruler-square", "a_sheet_scales": "text-box-search-outline", "a_sheet_links": "link-variant-plus",
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
        "a_insert_blank": "file-outline", "a_uncrop": "crop-free",
        "a_from_images": "file-image-outline", "a_new": "file-document-plus-outline", "a_extract": "file-export-outline",
        "a_header": "page-layout-header-footer", "a_watermark": "watermark", "a_background": "format-color-fill",
        "a_remove_bg": "format-color-marker-cancel", "a_remove_wm": "water-off-outline",
        "a_bookmarks": "bookmark-outline", "a_attachments": "paperclip",
        "a_compress": "zip-box-outline", "a_compare": "compare", "a_flatten": "layers-triple-outline",
        "a_sidebar": "page-layout-sidebar-left", "a_props": "tune-variant",
        "a_chest": "toolbox-outline", "a_split": "view-split-vertical", "a_labels": "label-outline",
        "a_shortcuts": "keyboard-outline", "a_manual": "help-circle-outline", "a_palette": "console-line",
        "a_night": "weather-night",
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
        r.add_tab(tr("Home"), [
            (tr("Tools"), "large", [t["select"], t["hand"], t["edittext"], t["addtext"], t["editobjects"],
                                t["capture"],
                                t["erasecontent"]]),
            (tr("Mark up text"), "small", [t["highlight"], t["underline"], t["strikeout"],
                                       t["comment"], t["note"], t["textbox"]]),
            (tr("Insert"), "large", [t["stamp"], t["image"], t["attach"], t["link"]]),
            (tr("Zoom"), "small", [self.a_fit_width, self.a_fit_page, self.a_actual,
                               self.a_zoom_in, self.a_zoom_out]),
            (tr("Mouse"), "small", [self.a_mouse_standard, self.a_mouse_hand, self.a_cad_mouse]),
            (tr("Sign"), "large", [t["signature"], t["initials"]]),
        ])
        # only markups here (PDF viewers can edit those); the Image tool and Erase content change
        # the page itself and live on the Home tab with Add text and Edit objects
        r.add_tab(tr("Markup"), [
            (tr("Text"), "small", [t["highlight"], t["underline"], t["strikeout"], t["comment"],
                               t["note"], t["textbox"]]),
            (tr("Callout & stamps"), "large", [t["callout"], t["stamp"], t["attach"]]),
            (tr("Shapes"), "small", [t["rect"], t["ellipse"], t["cloud"], t["polygon"], t["line"],
                                 t["arrow"], t["polyline"], t["ink"]]),
            (tr("Erase"), "large", [t["eraser"]]),
            (tr("Styles"), "large", [self.a_props, self.a_chest]),
        ])
        # snapping is offered where it's used: Measure, Arrange (lining markups up) and View
        snap_group = [self.a_snap_grid, self.a_snap_objects, self.a_snap_page, self.a_grid,
                      self.a_grid_settings]
        r.add_tab(tr("Measure"), [
            (tr("Measure"), "large", [t["m_length"], t["m_poly"], t["m_area"], t["m_count"]]),
            (tr("More"), "small", [t["m_angle"], t["m_radius"], t["m_perimeter"], t["m_volume"]]),
            (tr("Scale"), "small", [t["m_calibrate"], self.a_set_scale, self.a_sheet_scales,
                                self.a_measure_summary]),
            (tr("Grid & snap"), "small", snap_group),
        ])
        r.add_tab(tr("Arrange"), [
            (tr("Align"), "small", [A_["al_left"], A_["al_hcenter"], A_["al_right"], A_["al_top"],
                                A_["al_vmiddle"], A_["al_bottom"]]),
            (tr("Align to"), "small", [self.ribbon_align_box]),
            (tr("Distribute"), "small", [A_["dist_h"], A_["dist_v"]]),
            (tr("Order"), "small", [A_["z_front"], A_["z_forward"], A_["z_backward"], A_["z_back"]]),
            (tr("Lock"), "large", [self.a_lock, self.a_unlock_all]),
            (tr("Snap"), "small", snap_group),
        ])
        r.add_tab(tr("Review"), [
            (tr("Add"), "large", [t["comment"], t["note"]]),
            (tr("Navigate"), "large", [self.a_prev_markup, self.a_next_markup, self.a_markups]),
            (tr("Show"), "small", [self.a_show_markups, self.a_cards]),
            (tr("Manage"), "large", [self.a_delete_markups, self.a_flatten_markups]),
        ])
        r.add_tab(tr("Protect"), [
            (tr("Sign"), "large", [t["signature"], t["initials"], t["date"], self.a_multi_sign]),
            (tr("Placeholders"), "large", [t["placeholder"], self.a_apply_placeholders]),
            (tr("Digital signatures"), "small", [self.a_digisign, self.a_timestamp,
                                             self.a_sig_details, self.a_clear_sigs]),
            (tr("Redact"), "small", [t["redact"], self.a_search_redact, self.a_apply_sel_redact,
                                 self.a_apply_redact]),
            (tr("Security"), "large", [self.a_security, self.a_remove_security, self.a_unlock,
                                   self.a_sanitize]),
        ])
        r.add_tab(tr("Forms"), [
            (tr("Add fields"), "large", [t[k] for k, _l, _t in FORM_TOOLS]),
            (tr("Show"), "large", [self.a_hl_fields]),
        ])
        r.add_tab(tr("Pages"), [
            (tr("Rotate"), "large", [self.a_rot_l, self.a_rot_r]),
            (tr("Crop"), "large", [t["crop"], self.a_uncrop]),
            (tr("Organize"), "small", [self.a_move_up, self.a_move_down, self.a_del_page,
                                   self.a_insert_pdf, self.a_insert_blank, self.a_extract]),
            (tr("Create"), "large", [self.a_new, self.a_combine, self.a_from_images]),
            (tr("Document"), "small", [self.a_header, self.a_watermark, self.a_background,
                                   self.a_bookmarks, self.a_sheet_links, self.a_attachments,
                                   self.a_compress, self.a_compare]),
            (tr("Convert"), "large", [self.a_ocr, self.a_flatten]),
        ])
        r.add_tab(tr("View"), [
            (tr("Panels"), "small", [self.a_sidebar, self.a_props, self.a_markups, self.a_chest,
                                 self.a_split]),
            (tr("Display"), "small", [self.a_hl_fields, self.a_show_markups, self.a_free_pan,
                                  self.a_night]),
            (tr("Grid & snap"), "small", snap_group),
            (tr("Ribbon"), "small", [self.a_ribbon, self.a_collapse, self.a_group_names,
                                 self.a_menu_bar]),
            (tr("Help"), "large", [self.a_palette, self.a_shortcuts, self.a_manual]),
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
        self.menu_btn.setToolTip(tr("Menus (shown when the menu bar is hidden: View > Show menu bar)"))
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
        rt = self.ribbon_tb = QToolBar(tr("Ribbon"))
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
            self.ribbon_right.layout().insertWidget(0, self.find_group)
            self.search.setFixedWidth(170)
        elif not ribbon and not in_tb:
            sb.removeWidget(self.zoom_group)
            sb.removeWidget(self.nav_group)
            sb.removeWidget(self.view_group)
            self.search.setMinimumWidth(0)
            self.search.setMaximumWidth(260)
            self._zoom_group_act = tb.insertWidget(self.a_fit_width, self.zoom_group)
            self._nav_group_act = tb.insertWidget(self._spacer_act, self.nav_group)
            self._search_act = tb.addWidget(self.find_group)
        for w in (self.zoom_group, self.nav_group, self.find_group):
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
        name, ok = QInputDialog.getText(self, tr("Author name"),
                                        tr("Name recorded on your markups, stamps and comments:"),
                                        text=annotations.author())
        if ok:
            annotations.set_author(name.strip())
            self._refresh_props()

    def _toggle_sidebar(self):
        self.dock.setVisible(not self.dock.isVisible())

    def show_palette(self):
        """Command palette (Ctrl+Shift+P): type to find any command or tool, Enter runs it."""
        from .palette import CommandPalette
        CommandPalette(self).exec()

    def show_manual(self):
        from .manual import ManualDialog
        if getattr(self, "_manual", None) is None:
            self._manual = ManualDialog(self)
        self._manual.show()
        self._manual.raise_()
        self._manual.activateWindow()

    FEEDBACK_URL = "https://github.com/keithlyding/KanzonasPDF/issues/new/choose"

    def open_feedback(self):
        """Help > Report a problem or suggest an idea: GitHub's form, in the browser."""
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        QDesktopServices.openUrl(QUrl(self.FEEDBACK_URL))
        self.statusBar().showMessage(tr("Opened the feedback page in your browser. Please don't "
                                        "attach confidential PDFs."), 6000)

    def about(self):
        from . import branding, paths
        dlg = QDialog(self)
        dlg.setWindowTitle(tr("About {app}").format(app=APP_NAME))
        lay = QVBoxLayout(dlg)
        logo = QLabel()
        logo.setPixmap(branding.logo_pixmap(110))
        logo.setStyleSheet("background: #f7f9fa; border-radius: 6px; padding: 6px;")
        lay.addWidget(logo)
        version = tr("{title} (portable)").format(title=__version__) if paths.is_portable() \
            else __version__
        text = QLabel(tr(
            "Version {version}. A free, fast PDF reader and editor.<br><br>"
            "Built on PyMuPDF {pymupdf} (MuPDF) and Qt (PySide6).<br>"
            "Free software under the GNU Affero General Public License 3.0.<br>"
            "Source code and downloads: <a href='https://github.com/keithlyding/KanzonasPDF'>"
            "github.com/keithlyding/KanzonasPDF</a><br><br>"
            "If KanzonasPDF saves you time, a star on its GitHub page helps other people find "
            "it.").format(version=version, pymupdf=pymupdf.VersionBind))
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
            self._upd.result.connect(
                lambda t: QMessageBox.information(self, tr("Check for updates"), t))
            self._upd.checked.connect(lambda t: self.statusBar().showMessage(
                tr("Checked for updates: {result}").format(result=t), 8000))
        return self._upd

    def start_update_check(self):
        """Called a few seconds after start-up: checks at most once a day, if enabled. While
        KanzonasPDF stays open, it looks again every hour whether a day has passed."""
        self._updater().check_if_due()
        if getattr(self, "_update_timer", None) is None:
            self._update_timer = QTimer(self)
            self._update_timer.timeout.connect(lambda: self._updater().check_if_due())
            self._update_timer.start(3600 * 1000)

    def check_updates(self):
        self.statusBar().showMessage(tr("Checking for updates..."), 4000)
        self._updater().check(manual=True)

    def _update_found(self, version, url):
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl
        if self._upd.manual:
            # asked for: answer in a box, like the "up to date" answer
            self._update_box(version, url)
            return
        old = getattr(self, "_update_bar", None)
        if old is not None:
            self.statusBar().removeWidget(old)
            old.deleteLater()
        bar = QWidget()
        h = QHBoxLayout(bar)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(QLabel(tr("<b>KanzonasPDF {version} is available</b> (you have "
                              "{current}).").format(version=version, current=__version__)))
        news = QPushButton(tr("What's new"))
        news.setToolTip(tr("What changed since your version"))
        get = QPushButton(tr("Download"))
        get.setToolTip(tr("Open the release page to download the installer or portable zip"))
        upd = QPushButton(tr("Update now")) if self._self_update_url() else None
        if upd is not None:
            upd.setToolTip(self._update_now_text())
        skip = QPushButton(tr("Skip this version"))
        close = QPushButton(tr("Later"))

        def done():
            self.statusBar().removeWidget(bar)
            bar.deleteLater()
            self._update_bar = None
        get.clicked.connect(lambda: (QDesktopServices.openUrl(QUrl(url)), done()))
        skip.clicked.connect(lambda: (self.settings.setValue("update_skip", version), done()))
        close.clicked.connect(done)
        if upd is not None:
            upd.clicked.connect(lambda: (done(), self.update_now()))
        news.clicked.connect(lambda: self._update_box(version, url, done))
        for b in (news, upd, get, skip, close):
            if b is not None:
                h.addWidget(b)
        self._update_bar = bar
        self.statusBar().clearMessage()      # a status message would keep the notice hidden
        self.statusBar().addWidget(bar)
        bar.show()

    def _update_box(self, version, url, done=None):
        """The update box: the short notes of every version newer than this one (what changed
        since your version), then Update now / Download / Later. done: closes the notice in
        the status bar when the user updates or downloads."""
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl
        from PySide6.QtWidgets import QDialog, QDialogButtonBox, QTextBrowser
        from . import i18n, updates
        dlg = QDialog(self)
        dlg.setWindowTitle(tr("Check for updates"))
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel(tr("KanzonasPDF {version} is available (you have {current}).").format(
            version=version, current=__version__)))
        lay.addWidget(QLabel("<b>" + tr("What's new since your version") + "</b>"))
        notes = QTextBrowser()
        notes.setOpenExternalLinks(True)
        parts = []
        for v, text, page in updates.notes_since(self._upd.releases, lang=i18n.language()):
            parts.append("### " + tr("Version {version}").format(version=v))
            parts.append(text or "[" + tr("What's new in {version}").format(version=v)
                         + "](" + page + ")")
        notes.setMarkdown("\n\n".join(parts))
        lay.addWidget(notes)
        info = QLabel((self._update_now_text() + "\n\n" if self._self_update_url() else "")
                      + tr("Download opens the release page in your browser."))
        info.setWordWrap(True)
        lay.addWidget(info)
        box = QDialogButtonBox()
        upd = (box.addButton(tr("Update now"), QDialogButtonBox.AcceptRole)
               if self._self_update_url() else None)
        get = box.addButton(tr("Download"), QDialogButtonBox.AcceptRole)
        box.addButton(tr("Later"), QDialogButtonBox.RejectRole)
        chosen = []
        box.clicked.connect(lambda b: (chosen.append(b), dlg.accept()))
        lay.addWidget(box)
        dlg.resize(600, 520)
        dlg.exec()
        if chosen and chosen[0] in (upd, get) and done is not None:
            done()
        if upd is not None and chosen and chosen[0] is upd:
            self.update_now()
        elif chosen and chosen[0] is get:
            QDesktopServices.openUrl(QUrl(url))

    def _self_update_url(self):
        """Download address of what updates this copy in place: the new portable zip, or for
        an installed copy the new setup. None when it can't update itself."""
        from . import updates
        upd = getattr(self, "_upd", None)
        if upd is None:
            return None
        if updates.can_self_update():
            return updates.asset_url(upd.release)
        if updates.can_install_update():
            return updates.asset_url(upd.release, updates.setup_name(self._new_version()))
        return None

    def _new_version(self):
        """The version of the release found ('1.6' for the tag v1.6)."""
        return str((self._upd.release or {}).get("tag_name", "")).strip().lstrip("vV")

    def _update_now_text(self):
        from . import updates
        if updates.can_self_update():
            return tr("Update now downloads it, closes KanzonasPDF, replaces the program files "
                      "in this folder (your data folder is kept) and starts it again.")
        return tr("Update now downloads the new setup, checks it, closes KanzonasPDF (after "
                  "asking to save your work) and installs the new version over this one; "
                  "KanzonasPDF starts again when it's done. Your settings are kept.")

    def update_now(self):
        """Update now: in place, the portable way or with the new setup."""
        from . import updates
        if updates.can_self_update():
            self.update_portable()
        elif updates.can_install_update():
            self.update_installed()

    def update_installed(self):
        """Installed copy: download the new setup, close (saving first) and run it quietly
        over this installation; it starts KanzonasPDF again."""
        from PySide6.QtWidgets import QProgressDialog
        from . import paths, updates
        url = self._self_update_url()
        if not url:
            return
        version = self._new_version()
        dl = updates.InstallerUpdater(url, version, self, expected_sha256=updates.asset_digest(
            self._upd.release, updates.setup_name(version)))
        prog = QProgressDialog(tr("Downloading the new KanzonasPDF..."), tr("Cancel"), 0, 0, self)
        prog.setWindowTitle(tr("Update"))
        prog.setMinimumDuration(0)
        prog.canceled.connect(dl.cancel)

        def progress(got, total):
            if total > 0:
                prog.setMaximum(total)
                prog.setValue(got)

        def failed(msg):
            prog.close()
            QMessageBox.warning(self, tr("Update"), msg + "\n\n" + tr(
                "You can still download the setup from the release page and run it."))

        def ready(setup):
            import shutil
            import subprocess
            prog.close()
            if not self.close():          # the user kept a document open: not now
                shutil.rmtree(os.path.dirname(setup), ignore_errors=True)
                return
            subprocess.Popen(updates.installer_command(setup, paths.app_dir()), close_fds=True)
            QApplication.quit()
        dl.progress.connect(progress)
        dl.failed.connect(failed)
        dl.ready.connect(ready)
        dl.start()

    def update_portable(self):
        """Portable copy: download the new version, then close and let a script swap the files."""
        import tempfile
        from PySide6.QtWidgets import QProgressDialog
        from . import paths, updates
        url = self._self_update_url()
        if not url:
            return
        app_dir = paths.app_dir()
        dl = updates.PortableUpdater(url, app_dir, self,
                                     expected_sha256=updates.asset_digest(self._upd.release))
        prog = QProgressDialog(tr("Downloading the new KanzonasPDF..."), tr("Cancel"), 0, 0, self)
        prog.setWindowTitle(tr("Update"))
        prog.setMinimumDuration(0)
        prog.canceled.connect(dl.cancel)

        def progress(got, total):
            if total > 0:
                prog.setMaximum(total)
                prog.setValue(got)

        def failed(msg):
            prog.close()
            QMessageBox.warning(self, tr("Update"), msg + "\n\n" + tr(
                "You can still download KanzonasPDF-portable.zip from the release page and unzip "
                "it over this folder."))

        def ready(new):
            import subprocess
            prog.close()
            # a new folder only this user can write to (mkdtemp), not a fixed name in Temp
            # that another program could put its own script at before it runs
            script = os.path.join(tempfile.mkdtemp(prefix="kzupdate"), "kanzonas-update.cmd")
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
        # Scrolling to another page selects it in the page list. A page reached by clicking
        # in the list (Ctrl+click, Shift+click, right-click) keeps the pages selected there.
        if not self._thumb_nav and self.thumbs.currentRow() != page:
            from PySide6.QtCore import QItemSelectionModel
            self.thumbs.blockSignals(True)
            self.thumbs.setCurrentRow(page, QItemSelectionModel.ClearAndSelect)
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
                self, tr("Page order locked"),
                tr("The page order is locked, so pages can't be moved, added or removed.\n\n"
                   "Unlock it and continue? (Lock it again with the lock button above the page "
                   "list.)")) != QMessageBox.Yes:
            return False
        self.lock_btn.setChecked(False)
        return True

    def _set_pages_locked(self, locked):
        self.thumbs.setDragDropMode(QAbstractItemView.NoDragDrop if locked
                                    else QAbstractItemView.InternalMove)
        self.lock_btn.setText(tr("\U0001F512 Locked") if locked else tr("\U0001F513 Unlocked"))
        self.lock_btn.setToolTip(tr("Page order locked: pages can't be moved, added or removed "
                                    "(click to unlock)") if locked else
                                 tr("Unlocked: drag pages to reorder them; move, insert, delete, "
                                    "cut, paste and duplicate pages (click to lock)"))
        self.thumbs.setToolTip(tr("Unlock (button above) to drag pages") if locked
                               else tr("Drag pages to reorder them"))
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

    def _on_thumb_moved(self, *_):
        """Thumbnail dragged: apply the new order to the PDF after Qt finishes the drop (it
        moves one row at a time when several pages are dragged), as one undo step."""
        v = self.view()
        if v is not None and not getattr(self, "_thumb_order_queued", False):
            self._thumb_order_queued = True
            QTimer.singleShot(0, lambda: self._apply_thumb_order(v))

    def _apply_thumb_order(self, v):
        self._thumb_order_queued = False
        if v is not self.view():
            return
        # each thumbnail is labeled with the number of the page it shows
        order = [int(self.thumbs.item(i).text()) - 1 for i in range(self.thumbs.count())]
        item = self.thumbs.currentItem()
        show = int(item.text()) - 1 if item is not None else None
        if order != sorted(order) and not v.reorder_pages(order, show):
            self._rebuild_thumbs()          # refused (protected document): back as it is

    # ---- clipboard -----------------------------------------------------------------
    def _clipboard(self, op):
        """Edit > Copy / Cut / Paste / Select all: pages when the page list has the focus,
        otherwise text or markups in the document."""
        v = self.view()
        if v is None:
            return
        if op == "dup" and not self.thumbs.hasFocus():
            n = v.duplicate_selected()
            self.statusBar().showMessage(tr("Duplicated {n} markup(s)").format(n=n) if n else
                                         tr("Select markups (or pages in the page list) first"), 3000)
            return
        if self.thumbs.hasFocus():
            if op == "all":
                self.thumbs.selectAll()
            else:
                self._page_clip(op)
            return
        if op == "copy":
            what = v.copy()
            self.statusBar().showMessage({"text": tr("Text copied"),
                                          "markups": tr("Markups copied")}.get(
                what, tr("Select text or markups first")), 3000)
        elif op == "cut":
            what = v.cut()
            self.statusBar().showMessage({"text": tr("Text cut"), "markups": tr("Markups cut")}.get(
                what, tr("Select text or markups first")), 3000)
        elif op == "paste":
            what = v.paste()
            if what is None:
                self.statusBar().showMessage(tr("Nothing to paste"), 3000)
        elif op == "all":
            if self.tool != "select":
                self.set_tool("select")
            self.statusBar().showMessage(
                tr("Selected {n} characters").format(n=v.select_all_text()), 3000)

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
        if op in ("copy", "cut", "dup") and not v.require_permission(pymupdf.PDF_PERM_COPY, tr("Copying pages")):
            return
        pages = self._selected_pages()
        if op in ("copy", "cut"):
            clip.put("pages", v.pages_bytes(pages))
            if op == "cut" and v.delete_pages(pages):
                self.statusBar().showMessage(tr("Cut {n} page(s)").format(n=len(pages)), 3000)
            else:
                self.statusBar().showMessage(tr("Copied {n} page(s)").format(n=len(pages)), 3000)
        elif op == "paste":
            kind, data = clip.get()
            if kind != "pages":
                self.statusBar().showMessage(tr("Copy some pages first (Pages > Copy pages)"), 3000)
                return
            v.paste_pages(data, max(pages) + 1)
        elif op == "dup":
            v.duplicate_pages(pages)
            self.statusBar().showMessage(tr("Duplicated {n} page(s)").format(n=len(pages)), 3000)

    _thumb_nav = False                  # going to a page clicked in the page list

    def _on_thumb_clicked(self, row):
        v = self.view()
        if v and row >= 0:
            self._thumb_nav = True
            try:
                v.goto_page(row)
            finally:
                self._thumb_nav = False

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
