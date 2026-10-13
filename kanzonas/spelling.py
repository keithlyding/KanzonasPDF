"""Spell check as you type (American English) in KanzonasPDF's text boxes: misspelled words
get a red wavy underline, and right-clicking one offers corrections and Add to dictionary.
Edit > Check spelling turns it on and off.

The word list (pyspellchecker) loads the first time a text box opens, not at start-up."""

import re

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import (QColor, QContextMenuEvent, QSyntaxHighlighter, QTextCharFormat,
                           QTextCursor)

WORD = re.compile(r"[A-Za-z][A-Za-z']*[A-Za-z]|[A-Za-z]")
def _settings():
    from .paths import settings
    return settings()


_state = {"checker": None, "enabled": None, "own": None, "known": {}}


def enabled():
    if _state["enabled"] is None:
        _state["enabled"] = _settings().value("spell_check", True, type=bool)
    return _state["enabled"]


def set_enabled(on):
    _state["enabled"] = bool(on)
    _settings().setValue("spell_check", bool(on))


def _own_words():
    if _state["own"] is None:
        words = _settings().value("spell_words", [], type=list) or []
        _state["own"] = {w.lower() for w in words if isinstance(w, str)}
    return _state["own"]


def add_word(word):
    own = _own_words()
    own.add(word.lower())
    _settings().setValue("spell_words", sorted(own))
    _state["known"][word.lower()] = True


def _checker():
    if _state["checker"] is None:
        from spellchecker import SpellChecker          # heavy: only when first needed
        _state["checker"] = SpellChecker(language="en")
    return _state["checker"]


def _skip(word):
    # acronyms (HVAC), words with capitals inside (KanzonasPDF), single letters
    return len(word) < 2 or word.isupper() or any(c.isupper() for c in word[1:])


def is_known(word):
    w = word.strip("'")
    if _skip(w):
        return True
    key = w.lower()
    cache = _state["known"]
    if key not in cache:
        if key in _own_words():
            cache[key] = True
        else:
            sc = _checker()
            cache[key] = key in sc or (key.endswith("'s") and key[:-2] in sc)
    return cache[key]


def suggestions(word, n=5):
    sc = _checker()
    found = sc.candidates(word.lower()) or set()
    best = sc.correction(word.lower())
    ordered = ([best] if best in found else []) + sorted(found - {best},
                                                          key=lambda w: -sc.word_usage_frequency(w))
    out = []
    for w in ordered[:n]:
        out.append(w.capitalize() if word[:1].isupper() else w)
    return out


class Highlighter(QSyntaxHighlighter):
    def __init__(self, document):
        super().__init__(document)
        self.fmt = QTextCharFormat()
        self.fmt.setUnderlineStyle(QTextCharFormat.SpellCheckUnderline)
        self.fmt.setUnderlineColor(QColor(220, 0, 0))

    def highlightBlock(self, text):
        if not enabled():
            return
        for m in WORD.finditer(text):
            if not is_known(m.group()):
                self.setFormat(m.start(), m.end() - m.start(), self.fmt)


def word_at(edit, pos):
    """(QTextCursor selecting the word at viewport point pos, word) or (None, None)."""
    return _word_around(edit.cursorForPosition(pos))


def _word_around(cur):
    """(cursor selecting the word around text cursor cur, word) or (None, None)."""
    block = cur.block().text()
    at = cur.positionInBlock()
    for m in WORD.finditer(block):
        if m.start() <= at <= m.end():
            c = QTextCursor(cur.block())
            c.setPosition(cur.block().position() + m.start())
            c.setPosition(cur.block().position() + m.end(), QTextCursor.KeepAnchor)
            return c, m.group()
    return None, None


def misspelled_at(edit, pos):
    """The misspelled word to offer corrections for: the one under the pointer (pos, in
    the editor's viewport), else the one at the text cursor, so a right-click that lands a
    little off the word still finds it. (cursor, word) or (None, None)."""
    for cur, word in (word_at(edit, pos), _word_around(edit.textCursor())):
        if word is not None and not is_known(word):
            return cur, word
    return None, None


def menu_for(edit, pos):
    """The editor's usual right-click menu, with corrections on top for a misspelled word.
    pos: where it was clicked, in the editor's viewport."""
    menu = edit.createStandardContextMenu(pos)
    if not enabled():
        return menu
    cur, word = misspelled_at(edit, pos)
    if word is None:
        return menu
    first = menu.actions()[0] if menu.actions() else None
    options = suggestions(word)
    for s in options:
        a = menu.addAction(s)
        f = a.font()
        f.setBold(True)
        a.setFont(f)
        a.triggered.connect(lambda _=False, s=s, c=cur: c.insertText(s))
        menu.insertAction(first, a)
    if not options:
        a = menu.addAction("(no suggestions)")
        a.setEnabled(False)
        menu.insertAction(first, a)
    hl = getattr(edit, "_kz_spell", None)

    def remember():
        add_word(word)
        if hl is not None:
            hl.rehighlight()
    a = menu.addAction("Add to dictionary")
    a.triggered.connect(remember)
    menu.insertAction(first, a)
    menu.insertSeparator(first)
    return menu


class _MenuFilter(QObject):
    """Right-click in the editor's text area (its viewport, where the click comes in viewport
    coordinates, the ones the text layout uses). The menu opens on the right-button press and
    the press is kept here: Qt's text box ignores right presses, so on the page (the on-page
    editors are children of the page) the press went on to the page, which opened its own
    Cut / Copy / Paste menu instead of the corrections."""

    def __init__(self, edit):
        super().__init__(edit)
        self.edit = edit

    def _show(self, pos, global_pos):
        m = menu_for(self.edit, pos)
        m.exec(global_pos)
        m.deleteLater()

    def eventFilter(self, obj, e):
        t = e.type()
        if t in (QEvent.MouseButtonPress, QEvent.MouseButtonDblClick) and \
                e.button() == Qt.RightButton:
            self._show(e.position().toPoint(), e.globalPosition().toPoint())
            return True
        if t == QEvent.MouseButtonRelease and e.button() == Qt.RightButton:
            return True
        if t == QEvent.ContextMenu:
            if e.reason() != QContextMenuEvent.Mouse:      # the menu key (mouse: done above)
                self._show(e.pos(), e.globalPos())
            return True
        return False


def install(edit):
    """Spell check a QPlainTextEdit / QTextEdit as you type."""
    edit._kz_spell = Highlighter(edit.document())
    edit._kz_menu = _MenuFilter(edit)
    edit.viewport().installEventFilter(edit._kz_menu)
    return edit._kz_spell
