"""KanzonasPDF in Spanish: every text in the code that goes through tr() has a Spanish
translation with the same {fields}; the .po reader; the language setting; Qt's own words.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_translation
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import i18n  # noqa: E402


class Catalog(unittest.TestCase):
    def test_every_text_has_a_spanish_translation(self):
        missing, fields = i18n.untranslated("es")
        self.assertEqual(missing, [], "no Spanish for %d texts, e.g. %s" % (
            len(missing), missing[:5]))
        self.assertEqual(fields, [], "the {fields} differ: %s" % fields[:5])

    def test_reading_a_po_file(self):
        src = ('msgid ""\nmsgstr ""\n"Language: es\\n"\n\n'
               'msgid "&File"\nmsgstr "&Archivo"\n\n'
               '#, fuzzy\nmsgid "Open"\nmsgstr "Abrir"\n\n'
               'msgid "Saved {name}"\nmsgstr "Se guardó {name}"\n\n'
               'msgid "Not yet"\nmsgstr ""\n\n'
               'msgid "Two\\n"\n"lines"\nmsgstr "Dos\\n"\n"líneas"\n')
        self.assertEqual(i18n.parse_po(src), {"&File": "&Archivo", "Saved {name}": "Se guardó {name}",
                                              "Two\nlines": "Dos\nlíneas"})


class Language(unittest.TestCase):
    def setUp(self):
        self.saved = dict(i18n._state)
        self.addCleanup(lambda: i18n._state.update(self.saved))

    def pick(self, env, system="en_US"):
        i18n._state.update(lang=None, catalog={})
        with mock.patch.dict(os.environ, {"KANZONAS_LANG": env}), \
                mock.patch.object(i18n, "_system_language", lambda: system.split("_")[0]):
            return i18n.language()

    def test_automatic_follows_windows(self):
        self.assertEqual(self.pick("auto", "es_MX"), "es")
        self.assertEqual(self.pick("auto", "en_US"), "en")
        self.assertEqual(self.pick("auto", "de_DE"), "en")      # no German yet: English

    def test_chosen_language_wins(self):
        self.assertEqual(self.pick("es", "en_US"), "es")
        self.assertEqual(self.pick("en", "es_MX"), "en")

    def test_english_is_the_text_itself_and_spanish_is_looked_up(self):
        self.pick("en")
        self.assertEqual(i18n.tr("Preferences"), "Preferences")
        self.pick("es")
        i18n._state["catalog"]["Preferences"] = "Preferencias"
        self.assertEqual(i18n.tr("Preferences"), "Preferencias")
        self.assertEqual(i18n.tr("Not in the catalog"), "Not in the catalog")

    def test_qt_buttons_in_spanish(self):
        self.pick("es")
        t = i18n.install_qt(APP)
        if t is None:
            self.skipTest("Qt's Spanish translations aren't installed here")
        self.addCleanup(lambda: APP.removeTranslator(t))
        from PySide6.QtCore import QCoreApplication
        self.assertNotEqual(QCoreApplication.translate("QPlatformTheme", "&Yes"), "&Yes")


if __name__ == "__main__":
    unittest.main()
