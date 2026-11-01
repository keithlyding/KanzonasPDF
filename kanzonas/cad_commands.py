"""The CAD tab's commands (CAD mouse mode), as in AutoCAD: select first, then click the command
and answer its prompts in the status bar by clicking points on the page (they snap like the
drawing tools; Alt = don't snap) or typing a value and pressing Enter. Escape cancels.

Move     base point, then where it goes
Copy     base point, then where each copy goes (as many as you like; Enter or Escape ends)
Rotate   base point, then the angle: type it (degrees, counterclockwise) or click a point
Scale    base point, then the factor: type it, or click two points (a length, then the length
         it becomes)
Mirror   two points on the mirror line, then keep or delete the originals
Delete   the selection
Align    first source point, where it goes, second source point, where it goes; then scale or
         not, to make the second pair meet too
Array    rows and columns, then the spacing: click the base point, the next column's place,
         the next row's place
Trim     click the part of a line to cut away, up to the nearest crossing lines (or its end);
         again and again until Escape. No selection needed.

The selection is either the drawing's own objects (Edit objects) or markups (Select). Text of
the drawing only moves (Move); the other commands leave it where it is and say so.
"""
import math

import pymupdf
from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QColor, QPen, QTransform
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel,
                               QLineEdit, QPushButton, QSpinBox, QWidget)

from .i18n import tr
from . import page_objects

GHOST = QColor(0, 120, 215, 200)
BAND = QColor(220, 60, 0)
GHOST_LIMIT = 400           # copies previewed one by one (more: the box they fill)
GHOST_SEGMENTS = 20000      # line pieces drawn while previewing (more: each copy's box)


def _scale():
    """The verb Scale (the CAD tab's command and button): "Scale" alone is translated as the
    noun, the drawing's scale."""
    return tr("&Scale").replace("&", "")


def translate(d):
    return pymupdf.Matrix(1, 0, 0, 1, d.x, d.y)


def about(base, m):
    """Matrix m applied around point base."""
    return translate(-pymupdf.Point(base)) * pymupdf.Matrix(m) * translate(pymupdf.Point(base))


def rotation(base, ccw_degrees):
    """Turn around base, counterclockwise on screen (as CAD measures angles)."""
    return about(base, pymupdf.Matrix(-ccw_degrees))


def screen_angle(base, pt):
    """The direction from base to pt, counterclockwise from east, in degrees."""
    return math.degrees(math.atan2(-(pt.y - base.y), pt.x - base.x))


def mirror(p1, p2):
    d = pymupdf.Point(p2) - pymupdf.Point(p1)
    L = math.hypot(d.x, d.y)
    if L < 1e-9:
        return None
    ux, uy = d.x / L, d.y / L
    a, b = ux * ux - uy * uy, 2 * ux * uy
    m = pymupdf.Matrix(a, b, b, -a, 0, 0)
    p1 = pymupdf.Point(p1)
    q = p1 * m
    return pymupdf.Matrix(a, b, b, -a, p1.x - q.x, p1.y - q.y)


def align(s1, d1, s2, d2, scale=False):
    u, v = s2 - s1, d2 - d1
    lu, lv = math.hypot(u.x, u.y), math.hypot(v.x, v.y)
    turn = math.atan2(v.y, v.x) - math.atan2(u.y, u.x)
    k = lv / lu if scale and lu > 1e-9 else 1.0
    return translate(-s1) * pymupdf.Matrix(math.degrees(turn)) * pymupdf.Matrix(k, k) * \
        translate(d1)


MIN_FACTOR, MAX_FACTOR = 0.001, 1000.0      # a scale outside these makes objects unusable


def number(text):
    """A typed number ("90", "-45", "0,5", "90°"), or None for anything that isn't a finite
    one (nan and inf would write unusable drawing instructions)."""
    try:
        x = float(text.replace(",", ".").replace("\u00b0", "").strip())
    except ValueError:
        return None
    return x if math.isfinite(x) else None


def is_translation(m):
    return abs(m.a - 1) < 1e-9 and abs(m.d - 1) < 1e-9 and abs(m.b) < 1e-9 and abs(m.c) < 1e-9


# AutoCAD's short names for the CAD tab's commands (the command line also takes the start of a
# command's name: MOV, COP, ROT...)
ALIASES = {"m": "move", "co": "copy", "cp": "copy", "ro": "rotate", "sc": "scale",
           "mi": "mirror", "e": "delete", "erase": "delete", "del": "delete", "al": "align",
           "ar": "array", "tr": "trim"}
KEYS = ("move", "copy", "rotate", "scale", "mirror", "delete", "align", "array", "trim")


def names():
    """{command: its name in the language in use}."""
    return {"move": tr("Move"), "copy": tr("Copy"), "rotate": tr("Rotate"),
            "scale": _scale(), "mirror": tr("Mirror"), "delete": tr("Delete"),
            "align": tr("Align"), "array": tr("Array"), "trim": tr("Trim")}


def _plain(text):
    """Lower case without accents ("Simetría" -> "simetria")."""
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", text.lower())
                   if unicodedata.category(c) != "Mn")


def resolve(text):
    """The CAD command typed: an AutoCAD short name (M, CO, RO, SC, MI, E, AL, AR, TR) or the
    start of a command's name, in English or the language in use (MOV, COP, ROT...). None
    when it isn't one (or the start fits two, like A: Align and Array)."""
    t = _plain(text.strip())
    if not t:
        return None
    if t in ALIASES:
        return ALIASES[t]
    hits = {k for k in KEYS if k.startswith(t)}
    hits |= {k for k, n in names().items() if _plain(n).startswith(t)}
    return hits.pop() if len(hits) == 1 else None


def _word_start(typed, name):
    """typed is found in name at its start or at the start of a word (accents and case
    don't matter: "ajustar pagina")."""
    t = " ".join(_plain(typed).split())
    n = _plain(name.replace("&", ""))
    i = n.find(t)
    while i >= 0:
        if i == 0 or not n[i - 1].isalnum():
            return True
        i = n.find(t, i + 1)
    return False


def _whole(typed, name):
    """typed is the command's whole name ("..." left off)."""
    def clean(x):
        return " ".join(_plain(x.replace("&", "")).replace("...", "").replace("\u2026", "")
                        .split())
    return clean(typed) == clean(name)


# commands typed text runs only when typed in full (a few letters must never close the
# window or take things out of the document): EX is AutoCAD's Extend, not Exit
WHOLE_NAME_ONLY = {"Exit", "Close tab", "Delete pages", "Remove crop", "Remove security",
                   "Clear all digital signatures", "Delete comments", "Remove background",
                   "Remove watermarks", "Delete selected annotation"}
MIN_TYPED = 3                           # letters needed before a part of a name runs a command


class CommandLine(QWidget):
    """The command line at the bottom of the window in CAD mode, as in AutoCAD. Type a command
    (M, CO, RO... or any command's name: the command palette's list finds it) and press Enter
    (only Enter: Space types a space, "fit page"); Enter on an empty line repeats the last one.
    Text that is no command's name runs nothing: "Unknown command" (a near match runs only
    when picked from the list with Up / Down). While a command runs, it shows what
    to do next and takes typed values (an angle, a factor) and choices (the first letters of a
    button's name will do). In CAD mode, letters typed over the drawing come here (cad_typing
    in main_window.py)."""

    def __init__(self, win=None, parent=None):
        super().__init__(parent)
        self.win = win
        row = QHBoxLayout(self)
        row.setContentsMargins(4, 1, 4, 1)
        self.label = QLabel()
        self.edit = QLineEdit()
        self.edit.setMinimumWidth(240)
        self.edit.setPlaceholderText(tr("Type a command: M (Move), CO (Copy), RO, SC, MI, E, AL, "
                                        "AR, TR, or any command's name"))
        self.edit.installEventFilter(self)
        self.edit.textChanged.connect(self._suggest)
        if win is not None:
            win.installEventFilter(self)    # (resized: the list of matches goes)
        row.addWidget(self.label)
        row.addWidget(self.edit, 1)
        self.buttons = []
        self.choices = []
        self.cancel_btn = QPushButton(tr("Cancel"))
        self.cancel_btn.setFocusPolicy(Qt.NoFocus)
        self.cancel_btn.clicked.connect(lambda: self.command and self.command.cancel())
        self._row = row
        row.addWidget(self.cancel_btn)
        self.command = None
        self.last = None                # what Enter on an empty line runs again
        self.finder = None
        self.list = None                # the matching commands shown above the line
        self._arrowed = False           # a command was picked in the list with Up / Down
        self._why = None                # why typed text ran nothing (shown on the status bar)
        self._idle()

    # ---- what it shows ---------------------------------------------------------------------
    def _idle(self):
        self.label.setText("<b>%s</b>" % tr("Command:"))
        self.cancel_btn.hide()
        self._clear_choices()

    def _clear_choices(self):
        for b in self.buttons:
            b.deleteLater()
        self.buttons = []
        self.choices = []

    def show_for(self, command, text, typing=False, choices=()):
        self.command = command
        self.label.setText("<b>%s</b>: %s" % (command.title, text))
        self.edit.clear()
        self._clear_choices()
        self.choices = list(choices)
        for label, value in choices:
            b = QPushButton(label)
            b.setFocusPolicy(Qt.NoFocus)    # (a click leaves the keys with the page)
            b.clicked.connect(lambda _=False, v=value: self.command and
                              not self.command.gone() and self.command.choose(v))
            self._row.insertWidget(self._row.indexOf(self.cancel_btn), b)
            self.buttons.append(b)
        self.cancel_btn.show()
        self._hide_list()
        if self.win is not None:
            self.win.show_cad_line()
        self.show()
        if typing:
            self.edit.setFocus()

    def done(self):
        from PySide6.QtWidgets import QApplication
        self.command = None
        self.edit.clear()
        self._idle()
        if self.win is not None:
            self.win.show_cad_line()        # (stays in CAD mode, goes otherwise)
        elif self.parent() is None:
            self.hide()
        focus = QApplication.focusWidget()
        if focus is None or focus is self or self.isAncestorOf(focus) or \
                (self.win is not None and focus is self.win.tabs.tabBar()):
            # ended by a click on the page or a button: the keys (Ctrl+Z, Delete, the
            # arrows) go to the document again, not to the line
            self._back_to_page()

    # ---- typing --------------------------------------------------------------------------
    def take_key(self, e):
        """A key typed over the drawing (CAD mode): it goes into the line."""
        self.edit.setFocus()
        if e.key() in (Qt.Key_Return, Qt.Key_Enter):
            self.run()
        elif e.text() != " " or self.edit.text():
            self.edit.insert(e.text())

    def eventFilter(self, obj, e):
        from PySide6.QtCore import QEvent
        if obj is self.win and e.type() in (QEvent.Resize, QEvent.Move):
            self._hide_list()
            return False
        if obj is self.edit and e.type() == QEvent.FocusOut:
            self._hide_list()
            return False
        if obj is self.edit and e.type() == QEvent.KeyPress:
            k = e.key()
            if k in (Qt.Key_Return, Qt.Key_Enter):
                self.run()
                return True
            if k == Qt.Key_Escape:
                if self.edit.text():
                    self.edit.clear()
                elif self.command is not None:
                    self.command.cancel()
                self._back_to_page()
                return True
            if k in (Qt.Key_Up, Qt.Key_Down) and self.list is not None and self.list.isVisible():
                n = self.list.count()
                r = max(0, min(n - 1, self.list.currentRow() + (1 if k == Qt.Key_Down else -1)))
                self.list.setCurrentRow(r)
                self._arrowed = True
                return True
        return super().eventFilter(obj, e)

    def _typed(self):
        self.run()

    def run(self):
        """Enter on the line."""
        text = self.edit.text().strip()
        cmd = self.command
        if cmd is not None:
            self.edit.clear()
            self._back_to_page()        # (so Ctrl+Z, Delete... reach the document again)
            if cmd.gone():
                return
            if not text:
                cmd.enter_key()
                return
            low = text.lower()
            for label, value in self.choices:
                if label.replace("&", "").lower().startswith(low):
                    cmd.choose(value)
                    return
            if cmd.selecting:
                self.show_for(cmd, tr("select objects (click them, or draw a box or a lasso), "
                                      "then press Enter or right-click"), typing=False)
                return
            cmd.typed(text)
            return
        if not text:
            self._back_to_page()
            if self.last is not None:
                self._start(self.last)
            return
        self._why = None
        what = self._pick(text)
        if what is None:
            # nothing runs; the text stays (selected) to be corrected or typed over
            self._say(self._why or tr(
                "Unknown command: {text}. Type a command's name, or pick one in the list with "
                "Up and Down and press Enter.").format(text=text))
            self.edit.selectAll()
            return
        self.edit.clear()
        self._hide_list()
        self._back_to_page()
        self._start(what)

    def _pick(self, text):
        """("cad", key) or ("action", English name) for what was typed, or None."""
        if self._arrowed and self.list is not None and self.list.isVisible() and \
                self.list.currentItem():
            return self.list.currentItem().data(Qt.UserRole)     # picked with Up / Down
        key = resolve(text)
        if key is not None:
            return ("cad", key)
        f = self._finder()
        if f is None:
            return None
        whole, starts = [], []
        for name, a in f.actions.items():
            shown = f.names.get(name, name)
            if any(_whole(text, n) for n in (shown, name)):
                whole.append((name, a))
            elif any(_word_start(text, n) for n in (shown, name)):
                starts.append((name, a))
        if len(whole) == 1:
            found = whole
        elif whole:
            found = []
        else:
            # only a sure match: what was typed is the start of one command's name or of one
            # of its words ("fit page", "rect", "save as"), not letters scattered through it,
            # not two or three letters, and not the start of several commands
            letters = sum(c.isalnum() for c in text)
            found = [(n, a) for n, a in starts if n not in WHOLE_NAME_ONLY]
            if letters < MIN_TYPED or len(found) != 1:
                if len(found) > 1 or (found and letters < MIN_TYPED):
                    self._why = tr("{text} could be several commands: type more of the name, "
                                   "or pick one in the list with Up and Down and press "
                                   "Enter.").format(text=text)
                found = []
        if not found:
            return None
        name, a = found[0]
        if not a.isEnabled():
            self._why = tr("{command} can't be used now (open a document first?).").format(
                command=f.names.get(name, name).replace("&", ""))
            return None
        return ("action", name)

    def _start(self, what):
        kind, name = what
        self.last = what
        if self.win is None:
            return
        if kind == "cad":
            self.win.start_cad_command(name)
            return
        f = self._finder()
        a = f.actions.get(name) if f is not None else None
        if a is None or not a.isEnabled():
            return
        f.remember(name)
        self._back_to_page()
        a.trigger()
        if a.isCheckable():             # (a setting switched by typing: say which way)
            self._say((tr("{command}: on") if a.isChecked() else tr("{command}: off")).format(
                command=f.names.get(name, name).replace("&", "")))

    def _say(self, text):
        if self.win is not None:
            self.win.statusBar().showMessage(text, 4000)

    def _back_to_page(self):
        v = self.win.view() if self.win is not None else None
        if v is not None:
            v.setFocus()

    # ---- the list of matching commands -----------------------------------------------------
    def _finder(self):
        if self.finder is None and self.win is not None:
            from .palette import Finder
            self.finder = Finder(self.win)
        return self.finder

    def _hide_list(self):
        if self.list is not None:
            self.list.hide()

    def _suggest(self, text):
        self._arrowed = False
        if self.command is not None or self.win is None or not text.strip():
            self._hide_list()
            return
        from PySide6.QtWidgets import QListWidget, QListWidgetItem
        if self.list is None:
            self.list = QListWidget(self.win)
            self.list.setFocusPolicy(Qt.NoFocus)
            self.list.itemClicked.connect(lambda it: (self.edit.clear(), self._hide_list(),
                                                      self._start(it.data(Qt.UserRole))))
        self.list.clear()
        rows = []
        key = resolve(text)
        if key is not None:
            rows.append((("cad", key), names()[key] + "   " + tr("(CAD)")))
        f = self._finder()
        for name, a in (f.rows(text)[:7] if f is not None else []):
            if key is not None and a is getattr(self.win, "a_cad_" + key, None):
                continue
            path = f.paths.get(a, "")
            rows.append((("action", name), f.names.get(name, name) +
                         ("   (" + path + ")" if path else "")))
        if not rows:
            self._hide_list()
            return
        for data, label in rows:
            it = QListWidgetItem(label)
            it.setData(Qt.UserRole, data)
            self.list.addItem(it)
        self.list.setCurrentRow(0)
        h = min(len(rows), 8) * (self.list.sizeHintForRow(0) + 2) + 6
        w = min(max(self.edit.width(), 360), 560)
        top_left = self.edit.mapTo(self.win, self.edit.rect().topLeft())
        self.list.setGeometry(top_left.x(), top_left.y() - h - 2, w, h)
        self.list.show()
        self.list.raise_()


Prompt = CommandLine            # (the name it had before the command line took typed commands)


class Command:
    """One run of a CAD command on a document view (view._cad_cmd while it runs)."""
    title = ""
    needs_selection = True
    snap = True                         # clicks snap to line ends, corners... (not Trim's)

    def __init__(self, view, prompt):
        self.v = view
        self.ui = prompt
        self.page = None
        self.pts = []
        self.hover = None
        self.kind = None
        self.items = []
        self.ghost = []                 # the selection's outlines (page coordinates)

    # ---- running -------------------------------------------------------------------------
    def start(self):
        v = self.v
        # what it needs: the drawing changed (objects), annotating (markups), or both
        perms = [pymupdf.PDF_PERM_MODIFY]
        what = v.cad_targets() if self.needs_selection else None
        if what is not None:
            perms = {"objects": [pymupdf.PDF_PERM_MODIFY],
                     "markups": [pymupdf.PDF_PERM_ANNOTATE]}.get(
                what[0], [pymupdf.PDF_PERM_MODIFY, pymupdf.PDF_PERM_ANNOTATE])
        elif self.needs_selection:      # (nothing selected yet: either may do)
            perms = [pymupdf.PDF_PERM_MODIFY] if not v.allowed(pymupdf.PDF_PERM_ANNOTATE) \
                else []
        if getattr(v, "_source", None) is not None:
            v.modify(lambda: None)          # (the split view says it's read-only)
            return False
        for perm in perms:
            if not v.allowed(perm):
                v.modify(lambda: None, permission=perm)   # says why (once, not per click)
                return False
        if self.needs_selection:
            if what is None:
                if not v.cad_select:
                    v.statusMessage.emit(tr("{command}: select what to change first (click "
                                            "it, or draw a box or a lasso), then click "
                                            "{command}.").format(command=self.title))
                    return False
                # as in AutoCAD, the command first, then what it works on: select (clicks,
                # boxes, lassos), then Enter or right-click goes on
                self.selecting = True
                from . import cad_select
                cad_select.cancel(v)
                v._cad_cmd = self
                self.ui.show_for(self, tr("select objects (click them, or draw a box or a "
                                          "lasso), then press Enter or right-click"),
                                 typing=False)
                return True
            self.kind, self.page, self.items = what
            self.ghost = v.cad_outlines(self.page, self.kind, self.items)
        self.rev = getattr(v, "revision", 0)
        from . import cad_select
        cad_select.cancel(v)                # (a box started before the command is dropped)
        v._cad_cmd = self
        self.ask()
        return True

    selecting = False                   # waiting for the selection (the command came first)

    def selected(self):
        """Enter while selecting: go on with what is selected now (start again, so a command
        that asks something first, as Array, asks it now). True if it went on."""
        if self.v.cad_targets() is None:
            self.v.statusMessage.emit(tr("{command}: nothing is selected yet. Click objects, or "
                                         "draw a box or a lasso, then press Enter (Escape "
                                         "cancels).").format(command=self.title))
            return False
        self.selecting = False
        self.v._cad_cmd = None
        if not self.start():
            self.ui.done()
        return True

    def enter_key(self):
        """Enter (on the line, over the page, or a right-click): ends the selection step
        first, then is the command's own Enter."""
        if self.selecting:
            self.selected()
        else:
            self.enter()

    def ask(self):
        """Show the prompt for the current step."""

    def finish(self, label=None):
        from . import cad_select
        cad_select.cancel(self.v)           # (a box started while selecting goes too)
        self.v._cad_cmd = None
        self.ui.done()
        self._repaint()
        if label:
            self.v.statusMessage.emit(label)

    def cancel(self):
        self.finish(tr("{command} canceled").format(command=self.title))

    def enter(self):
        """Enter with nothing typed."""

    def typed(self, text):
        """A value typed in the prompt and Enter (commands that take clicks only say so)."""
        self.v.statusMessage.emit(tr("{command} takes clicks, not typed values: click the "
                                     "points on the page.").format(command=self.title))

    def choose(self, value):
        """A choice button."""

    rev = 0                             # the document's revision the command works on

    def gone(self):
        """The document changed under the command (Delete, a page rotated or deleted, the
        selection cleared): what it was changing isn't there as it was. Ends it, saying so."""
        if not self.needs_selection or self.selecting:
            return False
        v = self.v
        if getattr(v, "revision", 0) == self.rev and self.page is not None and \
                self.page < len(v.pages) and (
                    (self.kind in ("objects", "both") and v.obj_sel is not None and
                     v.obj_sel[0] == self.page and v.obj_sel[1]) or
                    (self.kind in ("markups", "both") and v.selection is not None and
                     v.selection[0] == self.page)):
            return False
        self.finish(tr("{command} canceled: the document changed under it. Select again and "
                       "start it again.").format(command=self.title))
        return True

    def click(self, index, pt):
        if self.gone():
            return
        if self.page is None:
            self.page = index
        if index != self.page:
            self.v.statusMessage.emit(tr("Click on the same page."))
            return
        self.pts.append(pymupdf.Point(pt))
        self.step()
        self._repaint()

    def step(self):
        """After a click."""

    def move(self, index, pt):
        if self.gone():
            return
        self.hover = pymupdf.Point(pt) if index == self.page or self.page is None else None
        self._repaint()

    def _repaint(self):
        if self.page is not None and 0 <= self.page < len(self.v.pages):
            self.v.pages[self.page].update()

    # ---- preview -------------------------------------------------------------------------
    def preview(self):
        """[Matrix] to draw the selection with while the pointer moves, and the rubber band's
        start point (or None)."""
        return [], None

    def paint(self, w, p):
        if w.index != self.page:
            return
        # page to screen worked out once (to_screen_pt reads the page for each point: a
        # big selection's outline took over a second to draw on each pointer move)
        to = self.v.doc[w.index].rotation_matrix * pymupdf.Matrix(self.v.zoom, self.v.zoom)

        def sp(q):
            q = pymupdf.Point(q) * to
            return QPointF(q.x, q.y)
        mats, start = self.preview()
        if mats and self.ghost:
            p.setPen(QPen(GHOST, 1, Qt.DashLine))
            if not hasattr(self, "_ghost_size"):
                self._ghost_size = sum(max(0, len(line) - 1) for line in self.ghost)
                xs = [q[0] for line in self.ghost for q in line]
                ys = [q[1] for line in self.ghost for q in line]
                self._ghost_box = pymupdf.Rect(min(xs), min(ys), max(xs), max(ys)) if xs \
                    else pymupdf.Rect()
            box = self._ghost_box
            if len(mats) > GHOST_LIMIT:         # (a huge array: just where it all goes)
                box = page_objects.bounding(self._ghost_box * m for m in mats)
                mats = [pymupdf.Matrix(1, 0, 0, 1, 0, 0)]
            lines = self.ghost if self._ghost_size * len(mats) <= GHOST_SEGMENTS and \
                box is self._ghost_box else None
            if lines is not None:
                # the outlines as one path, made once and moved by each matrix (a piece at a
                # time from Python took half a second per mouse move with 15,000 pieces)
                got = getattr(self, "_ghost_path", None)
                if got is None or got[0] is not lines:
                    from .page_widget import lines_path
                    got = self._ghost_path = (lines, lines_path(lines))
                brush = p.brush()
                p.setBrush(Qt.NoBrush)
                for m in mats:
                    t = m * to
                    p.drawPath(QTransform(t.a, t.b, t.c, t.d, t.e, t.f).map(got[1]))
                p.setBrush(brush)
            else:
                for m in mats:
                    r = box
                    line = [r.tl * m, r.tr * m, r.br * m, r.bl * m, r.tl * m]
                    for a, b in zip(line, line[1:]):
                        p.drawLine(sp(a), sp(b))
        if start is not None and self.hover is not None:
            p.setPen(QPen(BAND, 1, Qt.DashLine))
            p.drawLine(sp(start), sp(self.hover))
        p.setPen(QPen(BAND, 1))
        for q in self.pts:
            c = QPointF(sp(q))
            p.drawLine(c + QPointF(-5, 0), c + QPointF(5, 0))
            p.drawLine(c + QPointF(0, -5), c + QPointF(0, 5))


class Move(Command):
    title = tr("Move")

    def ask(self):
        self.ui.show_for(self, tr("click the base point") if not self.pts else
                         tr("click where it goes"))

    def step(self):
        if len(self.pts) == 2:
            self.v.cad_apply(tr("Moved"), translate(self.pts[1] - self.pts[0]))
            self.finish()
        else:
            self.ask()

    def preview(self):
        if len(self.pts) == 1 and self.hover is not None:
            return [translate(self.hover - self.pts[0])], self.pts[0]
        return [], None


class Copy(Command):
    title = tr("Copy")
    made = 0

    def ask(self):
        if not self.pts:
            self.ui.show_for(self, tr("click the base point"))
        else:
            self.ui.show_for(self, tr("click where a copy goes (Enter or Escape when done)"),
                             choices=[(tr("Done"), "done")])

    def step(self):
        if len(self.pts) >= 2:
            rev = self.v.revision
            self.v.cad_apply(tr("Copied"), None, copies=[translate(self.pts[-1] - self.pts[0])],
                             keep=True)
            if self.v.revision != rev:      # (the drawing's text alone isn't copied)
                self.made += 1
        self.ask()

    def enter(self):
        self.choose("done")

    def choose(self, value):
        self.finish((tr("1 copy made") if self.made == 1 else
                     tr("{n} copies made").format(n=self.made)) if self.made else None)

    def cancel(self):
        self.choose("done")

    def preview(self):
        if self.pts and self.hover is not None:
            return [translate(self.hover - self.pts[0])], self.pts[0]
        return [], None


class Rotate(Command):
    title = tr("Rotate")

    def ask(self):
        if not self.pts:
            self.ui.show_for(self, tr("click the base point"))
        else:
            self.ui.show_for(self, tr("type the angle (degrees, counterclockwise) and press Enter, "
                                      "or click a point"), typing=True)

    def step(self):
        if len(self.pts) == 2:
            self._apply(self._angle(self.pts[1]))
        else:
            self.ask()

    def _angle(self, pt):
        """The angle from the base point to pt as seen on screen (a turned page too)."""
        rm = self.v.doc[self.page].rotation_matrix
        return screen_angle(self.pts[0] * rm, pymupdf.Point(pt) * rm)

    def typed(self, text):
        a = number(text)
        if a is None or abs(a) > 1e6:
            self.v.statusMessage.emit(tr("Type a number of degrees, for example 90 or -45."))
            return
        if not self.pts:
            self.v.statusMessage.emit(tr("Click the base point first."))
            return
        self._apply(a)

    def _apply(self, ccw):
        self.v.cad_apply(tr("Rotated"), rotation(self.pts[0], ccw))
        self.finish()

    def preview(self):
        if len(self.pts) == 1 and self.hover is not None:
            return [rotation(self.pts[0], self._angle(self.hover))], self.pts[0]
        return [], None


class Scale(Command):
    title = _scale()

    def ask(self):
        if not self.pts:
            self.ui.show_for(self, tr("click the base point"))
        elif len(self.pts) == 1:
            self.ui.show_for(self, tr("type the scale factor and press Enter (2 = twice as big), "
                                      "or click a point at a length you know"), typing=True)
        else:
            self.ui.show_for(self, tr("click the point at the length it becomes"), typing=True)

    def step(self):
        if len(self.pts) == 2 and abs(self.pts[1] - self.pts[0]) < 1e-6:
            self.pts.pop()                  # (a length of nothing can't be a reference)
            return
        if len(self.pts) == 3:
            k = abs(self.pts[2] - self.pts[0]) / abs(self.pts[1] - self.pts[0])
            if not MIN_FACTOR <= k <= MAX_FACTOR:
                self.pts.pop()
                self._too_far()
                return
            self._apply(k)
        else:
            self.ask()

    def _too_far(self):
        self.v.statusMessage.emit(tr("The factor must be between {lo} and {hi}.").format(
            lo=MIN_FACTOR, hi=int(MAX_FACTOR)))

    def typed(self, text):
        k = number(text)
        if k is None or k <= 0:
            self.v.statusMessage.emit(tr("Type a factor above 0, for example 2 or 0.5."))
            return
        if not MIN_FACTOR <= k <= MAX_FACTOR:
            self._too_far()
            return
        if not self.pts:
            self.v.statusMessage.emit(tr("Click the base point first."))
            return
        self._apply(k)

    def _apply(self, k):
        self.v.cad_apply(tr("Scaled"), about(self.pts[0], pymupdf.Matrix(k, k)))
        self.finish()

    def preview(self):
        if len(self.pts) == 2 and self.hover is not None:
            ref = abs(self.pts[1] - self.pts[0])
            if ref > 1e-6:
                k = abs(self.hover - self.pts[0]) / ref
                return [about(self.pts[0], pymupdf.Matrix(k, k))], self.pts[0]
        return [], self.pts[0] if self.pts else None


class Mirror(Command):
    title = tr("Mirror")

    def ask(self):
        if not self.pts:
            self.ui.show_for(self, tr("click the first point of the mirror line"))
        elif len(self.pts) == 1:
            self.ui.show_for(self, tr("click the second point of the mirror line"))
        else:
            self.ui.show_for(self, tr("delete the originals?"),
                             choices=[(tr("Keep them"), "keep"), (tr("Delete them"), "delete")])

    def step(self):
        if len(self.pts) == 2 and mirror(self.pts[0], self.pts[1]) is None:
            self.pts.pop()
        self.ask()

    def enter(self):
        if len(self.pts) == 2:
            self.choose("keep")

    def choose(self, value):
        if len(self.pts) != 2:
            return
        m = mirror(self.pts[0], self.pts[1])
        if value == "delete":
            self.v.cad_apply(tr("Mirrored"), m)
        else:
            self.v.cad_apply(tr("Mirrored (a copy)"), None, copies=[m])
        self.finish()

    def preview(self):
        if len(self.pts) == 1 and self.hover is not None:
            m = mirror(self.pts[0], self.hover)
            return ([m] if m is not None else []), self.pts[0]
        if len(self.pts) == 2:
            return [mirror(self.pts[0], self.pts[1])], None
        return [], None


class Align(Command):
    title = tr("Align")

    def ask(self):
        texts = [tr("click the first source point"), tr("click where it goes"),
                 tr("click the second source point"), tr("click where it goes")]
        if len(self.pts) < 4:
            self.ui.show_for(self, texts[len(self.pts)])
        else:
            self.ui.show_for(self, tr("scale it so the second points meet too?"),
                             choices=[(tr("Don't scale"), "no"), (_scale(), "yes")])

    def step(self):
        self.ask()

    def enter(self):
        if len(self.pts) == 4:
            self.choose("no")

    def choose(self, value):
        if len(self.pts) != 4:
            return
        s1, d1, s2, d2 = self.pts
        if abs(s2 - s1) < 1e-6:
            self.v.statusMessage.emit(tr("The two source points must be apart."))
            return
        if value == "yes" and not MIN_FACTOR <= abs(d2 - d1) / abs(s2 - s1) <= MAX_FACTOR:
            self.v.statusMessage.emit(tr("To scale, the two points where it goes must be apart "
                                         "too: choose Don't scale, or start Align again."))
            return
        self.v.cad_apply(tr("Aligned"), align(s1, d1, s2, d2, value == "yes"))
        self.finish()

    def preview(self):
        if len(self.pts) == 1 and self.hover is not None:
            return [translate(self.hover - self.pts[0])], self.pts[0]
        if len(self.pts) == 3 and self.hover is not None and abs(self.pts[2] - self.pts[0]) > 1e-6:
            return [align(self.pts[0], self.pts[1], self.pts[2], self.hover)], self.pts[1]
        if len(self.pts) in (2, 4):
            return [translate(self.pts[1] - self.pts[0])] if len(self.pts) == 2 else \
                [align(*self.pts)], None
        return [], None


class Array(Command):
    title = tr("Array")
    rows = cols = 1

    def start(self):
        v = self.v
        if v.cad_targets() is None:
            return super().start()
        dlg = QDialog(v)
        dlg.setWindowTitle(tr("Array"))
        form = QFormLayout(dlg)
        rows, cols = QSpinBox(), QSpinBox()
        for sb, val in ((rows, 1), (cols, 3)):
            sb.setRange(1, 50)
            sb.setValue(val)
        form.addRow(tr("Rows:"), rows)
        form.addRow(tr("Columns:"), cols)
        note = QLabel(tr("Then click the base point, where the next column's copy goes, and "
                         "where the next row's copy goes."))
        note.setWordWrap(True)
        form.addRow(note)
        box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        box.accepted.connect(dlg.accept)
        box.rejected.connect(dlg.reject)
        form.addRow(box)
        if dlg.exec() != QDialog.Accepted or rows.value() * cols.value() < 2:
            return False
        copies = rows.value() * cols.value() - 1
        kind, _page, items = v.cad_targets()
        if kind == "both":                  # (the markups count one each)
            memo = {}
            from .page_objects import group_size
            many = copies * (sum(group_size(v.doc, it["xref"], memo) if it["kind"] == "group"
                                 else 1 for it in items["objects"]) + len(items["markups"]))
        elif kind == "objects":
            # a group (a placed drawing, a copy from a big array) counts what it draws
            from .page_objects import group_size
            memo = {}
            many = copies * sum(group_size(v.doc, it["xref"], memo) if it["kind"] == "group"
                                else 1 for it in items)
        else:
            many = copies * len(items)
        marks = items["markups"] if kind == "both" else items if kind == "markups" else []
        if many > 20000 or copies * len(marks) > 1000:
            from PySide6.QtWidgets import QMessageBox
            if QMessageBox.question(
                    v, tr("Array"), tr("This makes {n} new objects, which can take a while and "
                                       "makes the file bigger. Go on?").format(n=many)) \
                    != QMessageBox.Yes:
                return False
        self.rows, self.cols = rows.value(), cols.value()
        return super().start()

    def _needed(self):
        return 1 + (self.cols > 1) + (self.rows > 1)

    def ask(self):
        if not self.pts:
            self.ui.show_for(self, tr("click the base point"))
        elif len(self.pts) == 1 and self.cols > 1:
            self.ui.show_for(self, tr("click where the next column's copy goes"))
        else:
            self.ui.show_for(self, tr("click where the next row's copy goes"))

    def _vectors(self, pts):
        col = pts[1] - pts[0] if self.cols > 1 and len(pts) > 1 else pymupdf.Point(0, 0)
        k = 2 if self.cols > 1 else 1
        row = pts[k] - pts[0] if self.rows > 1 and len(pts) > k else pymupdf.Point(0, 0)
        return col, row

    def _matrices(self, pts):
        col, row = self._vectors(pts)
        return [translate(col * c + row * r) for r in range(self.rows) for c in range(self.cols)
                if r or c]

    def step(self):
        if len(self.pts) == self._needed():
            n = self.rows * self.cols - 1
            rev = self.v.revision
            self.v.cad_apply(tr("Array"), None, copies=self._matrices(self.pts))
            if self.v.revision != rev:
                self.finish(tr("Array: {n} copies made (Ctrl+Z undoes it)").format(n=n))
            else:                           # (the drawing's text alone isn't copied: it says)
                self.finish()
        else:
            self.ask()

    def preview(self):
        if self.pts and self.hover is not None:
            return self._matrices(self.pts + [self.hover]), self.pts[0]
        return [], None


class Trim(Command):
    """As AutoCAD's TRIM: the cutting edges first (selected before, or selected now and
    Enter; Enter with nothing selected: every line cuts), then click the parts to cut away;
    Enter ends."""
    title = tr("Trim")
    needs_selection = False
    snap = False                        # the click picks a line: it must stay where it is
    done = 0
    edges = None                        # (page, [polylines]) the chosen cutting edges

    def start(self):
        what = self.v.cad_targets()
        if what is not None:
            self._take(what)
        elif self.v.cad_select:
            self.selecting = True
        return super().start()

    def _take(self, what):
        kind, page, items = what
        self.edges = (page, self.v.cad_outlines(page, kind, items))
        self._pages = len(self.v.pages)

    def gone(self):
        if self.edges is not None and len(self.v.pages) != getattr(self, "_pages", 0):
            self.finish(tr("{command} canceled: the document changed under it. Select again "
                           "and start it again.").format(command=self.title))
            return True
        return super().gone()

    def selected(self):
        what = self.v.cad_targets()
        if what is not None:
            self._take(what)
        self.selecting = False
        self.ask()
        return True

    def ask(self):
        if self.selecting:
            self.ui.show_for(self, tr("select the cutting edges, then press Enter (Enter with "
                                      "nothing selected: every line cuts)"))
            return
        self.ui.show_for(self, tr("click the part of a line to cut away, up to the lines that "
                                  "cross it (Enter or Escape when done)") if self.edges is None
                         else tr("click the part of a line to cut away, up to the cutting "
                                 "edges (Enter or Escape when done)"),
                         choices=[(tr("Done"), "done")])

    def click(self, index, pt):
        if self.gone():
            return
        self.page = index
        edges = self.edges[1] if self.edges is not None and self.edges[0] == index else None
        if self.edges is not None and edges is None:
            self.v.statusMessage.emit(tr("Click on the page with the cutting edges."))
            return
        if self.v.cad_trim(index, pymupdf.Point(pt), edges):
            self.done += 1
        self.ask()

    def enter(self):
        self.choose("done")

    def choose(self, value):
        self.finish(tr("{n} trims (Ctrl+Z undoes them one by one)").format(n=self.done)
                    if self.done else None)

    def cancel(self):
        self.choose("done")


class Erase(Command):
    """Delete (E), started with nothing selected: select, Enter, and it goes."""
    title = tr("Delete")

    def ask(self):
        v = self.v
        self.finish()
        v.delete_everything_selected()


COMMANDS = {"move": Move, "copy": Copy, "rotate": Rotate, "scale": Scale, "mirror": Mirror,
            "align": Align, "array": Array, "trim": Trim, "delete": Erase}
