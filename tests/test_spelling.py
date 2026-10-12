"""Spell check as you type: misspelled words are underlined, right-click offers corrections
and Add to dictionary; acronyms and names with capitals inside aren't flagged.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_spelling
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint  # noqa: E402
from PySide6.QtGui import QTextCharFormat  # noqa: E402
from PySide6.QtWidgets import QApplication, QPlainTextEdit  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import spelling  # noqa: E402


class FakeSettings:
    def __init__(self):
        self.d = {}

    def value(self, k, default=None, type=None):
        return self.d.get(k, default)

    def setValue(self, k, v):
        self.d[k] = v


class Spelling(unittest.TestCase):
    def setUp(self):
        self.store = FakeSettings()
        p = mock.patch.object(spelling, "_settings", lambda: self.store)
        p.start()
        self.addCleanup(p.stop)
        spelling._state.update({"enabled": None, "own": None, "known": {}})

    def underlined(self, edit):
        block = edit.document().firstBlock()
        out = []
        for r in block.layout().formats():
            if r.format.underlineStyle() == QTextCharFormat.SpellCheckUnderline:
                out.append(block.text()[r.start:r.start + r.length])
        return out

    @staticmethod
    def menu_on(edit, word):
        """The right-click menu on word (where the click lands on screen depends on fonts,
        which differ between systems, so the word is given directly)."""
        cur = edit.document().find(word)
        with mock.patch.object(spelling, "word_at", lambda _e, _p: (cur, word)):
            return spelling.menu_for(edit, QPoint(0, 0))

    def test_words(self):
        self.assertTrue(spelling.is_known("Color"))
        self.assertFalse(spelling.is_known("colour"))        # American spelling
        self.assertTrue(spelling.is_known("HVAC"))           # acronym
        self.assertTrue(spelling.is_known("KanzonasPDF"))    # capital inside: a name
        self.assertTrue(spelling.is_known("contractor's"))
        self.assertEqual(spelling.suggestions("Recieve")[0], "Receive")

    def test_underline_menu_and_dictionary(self):
        edit = QPlainTextEdit("Pleese recieve the drawings")
        spelling.install(edit)
        edit.resize(400, 100)
        edit.show()
        APP.processEvents()
        self.assertEqual(self.underlined(edit), ["Pleese", "recieve"])
        menu = self.menu_on(edit, "recieve")
        texts = [a.text() for a in menu.actions()]
        self.assertEqual(texts[0], "receive")
        self.assertIn("Add to dictionary", texts)
        menu.actions()[0].trigger()                          # take the correction
        self.assertEqual(edit.toPlainText(), "Pleese receive the drawings")
        add = [a for a in self.menu_on(edit, "Pleese").actions() if a.text() == "Add to dictionary"]
        add[0].trigger()
        self.assertEqual(self.underlined(edit), [])
        self.assertEqual(self.store.d["spell_words"], ["pleese"])

    def test_turned_off(self):
        spelling.set_enabled(False)
        edit = QPlainTextEdit("recieve")
        spelling.install(edit)
        self.assertEqual(self.underlined(edit), [])
        self.assertNotIn("Add to dictionary",
                         [a.text() for a in spelling.menu_for(edit, QPoint(2, 2)).actions()])


if __name__ == "__main__":
    unittest.main()


class WordAt(unittest.TestCase):
    def test_word_at_cursor(self):
        edit = QPlainTextEdit("one twoo three")
        edit.resize(400, 100)
        edit.show()
        APP.processEvents()
        c = edit.textCursor()
        c.setPosition(6)
        edit.setTextCursor(c)
        cur, word = spelling.word_at(edit, edit.cursorRect().center())
        self.assertEqual((word, cur.selectedText()), ("twoo", "twoo"))
