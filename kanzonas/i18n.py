"""KanzonasPDF's own words in the user's language (menus, buttons, dialogs, messages).

Every text the user sees goes through tr("English text"); a translation is looked up in
kanzonas/locale/<language>.po (the standard gettext format translators know) and the English
is used where there's none. The language is File > Preferences > General > Language:
Automatic (the language of Windows), English, Español or Italiano; a change applies at the next
start.
Qt's own dialogs and buttons (Open, Save, Yes, No) come translated with Qt.

Texts with parts filled in use named fields: tr("Saved {name}").format(name=...), so a
translation can put them where its grammar wants them.

The same English word with two meanings, or a place that needs a shorter word than the rest of
the app (a ribbon button), gets a context: tr("Snap to grid", ctx="ribbon") is translated by
the .po entry with msgctxt "ribbon" (gettext's own way), and by the entry without one when
there's none.
"""

import os
import re

LANGUAGES = {"en": "English", "es": "Español", "it": "Italiano"}
_state = {"lang": None, "catalog": {}}


def _wanted():
    """The language set in Preferences ('auto', 'en', 'es', 'it'); KANZONAS_LANG overrides it (the
    tests run in English)."""
    env = os.environ.get("KANZONAS_LANG")
    if env:
        return env
    try:
        from . import paths
        return str(paths.settings().value("language", "auto") or "auto")
    except Exception:
        return "auto"


def _system_language():
    try:
        from PySide6.QtCore import QLocale
        return QLocale.system().name().split("_")[0].lower()
    except Exception:
        return "en"


def language():
    """The language in use: 'en', 'es' or 'it'."""
    if _state["lang"] is None:
        want = _wanted()
        lang = _system_language() if want == "auto" else want
        _state["lang"] = lang if lang in LANGUAGES else "en"
        _state["catalog"] = load(_state["lang"]) if _state["lang"] != "en" else {}
    return _state["lang"]


CTX = "\x04"        # between a msgctxt and its msgid in the catalog's keys (as gettext does)


def tr(text, ctx=None):
    """text in the user's language (as it is when there's no translation); ctx: the context
    of a text whose translation differs there (see above)."""
    if _state["lang"] is None:
        language()
    catalog = _state["catalog"]
    if ctx:
        return catalog.get(ctx + CTX + text) or catalog.get(text) or text
    return catalog.get(text) or text


def po_path(lang):
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "locale", lang + ".po")


_ESC = {"n": "\n", "t": "\t", '"': '"', "\\": "\\"}


def _unquote(s):
    return re.sub(r'\\(.)', lambda m: _ESC.get(m.group(1), m.group(1)), s)


def parse_po(source):
    """{msgid: msgstr} of a .po file's text (untranslated and fuzzy entries left out); an
    entry with a msgctxt is keyed msgctxt + CTX + msgid."""
    out = {}
    cur = {"flags": "", "msgctxt": None, "msgid": None, "msgstr": None}
    field = None

    def flush():
        if cur["msgid"] and cur["msgstr"] and "fuzzy" not in cur["flags"]:
            key = cur["msgid"] if cur["msgctxt"] is None else cur["msgctxt"] + CTX + cur["msgid"]
            out[key] = cur["msgstr"]
    for raw in source.splitlines():
        line = raw.strip()
        if line.startswith("#,"):
            if cur["msgstr"] is not None:           # a new entry's flags
                flush()
                cur.update(flags="", msgctxt=None, msgid=None, msgstr=None)
            cur["flags"] += line
            continue
        if not line or line.startswith("#"):
            continue
        m = re.match(r'(msgctxt|msgid|msgstr)\s+"(.*)"$', line)
        if m:
            if m.group(1) in ("msgctxt", "msgid") and cur["msgstr"] is not None:
                flush()
                cur.update(flags="", msgctxt=None, msgid=None, msgstr=None)
            field = m.group(1)
            cur[field] = _unquote(m.group(2))
        elif line.startswith('"') and line.endswith('"') and field:
            cur[field] = (cur[field] or "") + _unquote(line[1:-1])
    flush()
    return out


def load(lang):
    """{English: translation} from locale/<lang>.po (and any locale/<lang>-*.po beside it)."""
    import glob
    out = {}
    base = po_path(lang)
    for path in [base] + sorted(glob.glob(base[:-3] + "-*.po")):
        try:
            with open(path, encoding="utf-8") as f:
                out.update(parse_po(f.read()))
        except OSError:
            pass
    return out


def install_qt(app):
    """Qt's own words (standard buttons and dialogs) in the same language."""
    lang = language()
    if lang == "en":
        return None
    from PySide6.QtCore import QLibraryInfo, QTranslator
    t = QTranslator(app)
    where = QLibraryInfo.path(QLibraryInfo.TranslationsPath)
    if t.load("qtbase_" + lang, where):
        app.installTranslator(t)
        return t
    return None


# ---- for the build check and translators -------------------------------------------
def texts_in_code(root=None):
    """{text: [file:line]} of every tr("...") in the package's code (literal texts only); a
    text with a context (tr("...", ctx="...")) is keyed as the catalog keys it."""
    import ast
    root = root or os.path.dirname(os.path.abspath(__file__))
    found = {}
    for name in sorted(os.listdir(root)):
        if not name.endswith(".py"):
            continue
        path = os.path.join(root, name)
        with open(path, encoding="utf-8") as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "tr" and \
                    node.args and isinstance(node.args[0], ast.Constant) and \
                    isinstance(node.args[0].value, str):
                text = node.args[0].value
                ctx = [k.value.value for k in node.keywords if k.arg == "ctx" and
                       isinstance(k.value, ast.Constant)]
                if ctx and ctx[0]:
                    text = ctx[0] + CTX + text
                found.setdefault(text, []).append("%s:%d" % (name, node.lineno))
    return found


def untranslated(lang="es"):
    """The texts in the code with no translation in lang, and translations whose {fields}
    don't match the English."""
    catalog = load(lang)
    missing, fields = [], []
    for text, where in texts_in_code().items():
        if text not in catalog:
            missing.append((text, where[0]))
        elif set(re.findall(r"\{(\w*)\}", text)) != set(re.findall(r"\{(\w*)\}", catalog[text])):
            fields.append((text, where[0]))
    return missing, fields
