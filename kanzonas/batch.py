"""Tools > Batch processing: the same steps on many PDFs at once (OCR 200 scanned invoices
and archive them as PDF/A, Bates-number a set of discovery documents, stamp CONFIDENTIAL on
every file in a folder, flatten markups, shrink a folder to email it).

This module is the engine, without a window (batch_ui.py is the window). Batch.run() is a
generator: each next() does a short piece of work and yields where it is, so the window
drives it from Qt's event loop in slices and stays responsive (PyMuPDF isn't thread-safe:
every document is read and changed on the GUI thread; only the OCR engine and the exports,
which work on their own copy of the bytes, run in a worker thread, as File > Export and
Recognize text do). Tests simply run it to the end (run_all).

One document is open at a time: each file is opened (BatchDoc), the steps run on it through
the app's own code (DocumentView's editing steps, page_tools, ocr, pdfa, export, combine),
everything it produces is written, it is closed and its memory freed before the next file.
A file's outputs appear all together or not at all: exports are made in a temporary folder
and moved into place at the end, and the PDF is written through a temporary file
(DocumentView.save), so stopping or a failure never leaves a half-written file.
"""

import gc
import inspect
import json
import os
import re
import shutil
import tempfile
import types
from collections import namedtuple
from datetime import date

import pymupdf

from .i18n import tr

WAIT = object()     # yielded while a worker thread is busy: come back in a moment

DONE, SKIPPED, FAILED, CANCELED = "done", "skipped", "failed", "canceled"
STATUS_LABELS = {DONE: tr("Done"), SKIPPED: tr("Skipped"), FAILED: tr("Failed"),
                 CANCELED: tr("Canceled")}

# ---- the steps ------------------------------------------------------------------------------
# A step is {"kind": one of STEPS, "options": {key: value}}; its options are described by
# Fields (key, type, label, default, extra), which the window turns into a form and recipes
# keep as JSON. Types: text, lines, int (extra: (min, max, suffix)), float (the same), bool,
# choice (extra: [(value, label)]), color, password (never saved in a recipe), image, pages.
Field = namedtuple("Field", "key type label default extra")


def _f(key, typ, label, default, extra=None):
    return Field(key, typ, label, default, extra)


POSITIONS = [("header", "left"), ("header", "center"), ("header", "right"),
             ("footer", "left"), ("footer", "center"), ("footer", "right")]
POSITION_LABELS = [tr("Header, left"), tr("Header, center"), tr("Header, right"),
                   tr("Footer, left"), tr("Footer, center"), tr("Footer, right")]
_POSITION_CHOICES = [("%s-%s" % p, label) for p, label in zip(POSITIONS, POSITION_LABELS)]
_ALL_PAGES = tr("All pages (or e.g. 1-3, 5, 8-)")


def _pages_field():
    return _f("pages", "pages", tr("Pages"), "", _ALL_PAGES)


def _text_fields(size=9.0):
    return [_f("size", "float", tr("Font size"), size, (5, 48, " pt")),
            _f("color", "color", tr("Color"), "#000000"),
            _f("margin", "float", tr("Margin from edge"), 24.0, (4, 144, " pt")),
            _pages_field()]


def _step_table():
    from . import ocr
    # the labels of Protect > Sanitize document's choices, with their defaults
    from .document_view import DocumentView
    sanitize = [_f(key, "bool", label, default)
                for key, label, default in DocumentView.SANITIZE_OPTIONS]
    hf = [_f("%s_%s" % p, "text", label, "") for p, label in zip(POSITIONS, POSITION_LABELS)]
    return {
        "ocr": (tr("Recognize text (OCR)"), tr(
            "Makes scanned pages searchable and selectable, as Recognize text (OCR) does."), [
            _f("skip_text", "bool", tr("Skip pages that already contain text"), True),
            _f("accuracy", "choice", tr("Accuracy"), "auto",
               [(k, ocr.ACCURACY_LABELS[k]) for k in ("auto", "fast", "normal", "high")]),
            _pages_field()]),
        "pdfa": (tr("Save as PDF/A"), tr(
            "Makes each file a PDF/A-2b archival copy, as File > Save as PDF/A does. Put it "
            "after the steps that change the document; a password-protected file needs Remove "
            "password before it."), []),
        "watermark": (tr("Watermark"), tr(
            "Writes text (or a picture) across the pages, as Document > Watermark does."), [
            _f("text", "text", tr("Text"), tr("CONFIDENTIAL")),
            _f("image", "image", tr("Picture instead of text"), ""),
            _f("size", "float", tr("Font size"), 80.0, (8, 400, " pt")),
            _f("color", "color", tr("Color"), "#ff0000"),
            _f("angle", "int", tr("Angle"), 45, (-90, 90, "°")),
            _f("opacity", "int", tr("Opacity"), 25, (5, 100, "%")),
            _f("behind", "bool", tr("Behind page content"), False),
            _pages_field()]),
        "header_footer": (tr("Header and footer"), tr(
            "Text in the margins, as Document > Header & footer does. Tokens: {page} {pages} "
            "{date} {file} {bates}. Bates numbers continue from one file to the next, in the "
            "order of the list."), hf + [
            _f("bates_prefix", "text", tr("Bates prefix"), ""),
            _f("bates_start", "int", tr("First Bates number"), 1, (0, 10 ** 8, "")),
            _f("bates_digits", "int", tr("Bates digits"), 6, (1, 12, ""))] + _text_fields()),
        "page_numbers": (tr("Page numbers"), tr(
            "Numbers each file's pages. Tokens: {page} {pages}."), [
            _f("text", "text", tr("Text"), tr("Page {page} of {pages}")),
            _f("position", "choice", tr("Position"), "footer-center", _POSITION_CHOICES)]
            + _text_fields()),
        "bates": (tr("Bates numbering"), tr(
            "A Bates number on every page, continuing from one file to the next in the order "
            "of the list (the first file starts at the first number)."), [
            _f("prefix", "text", tr("Bates prefix"), "ABC"),
            _f("start", "int", tr("First Bates number"), 1, (0, 10 ** 8, "")),
            _f("digits", "int", tr("Bates digits"), 6, (1, 12, "")),
            _f("position", "choice", tr("Position"), "footer-right", _POSITION_CHOICES)]
            + _text_fields(10.0)),
        "flatten_comments": (tr("Flatten comments"), tr(
            "Makes comments and markups part of the page, as Review > Flatten comments does. "
            "Form fields stay fillable."), [
            _f("redactions", "choice", tr("Redaction marks not applied yet"), "keep",
               [("keep", tr("Keep them as marks")), ("apply", tr("Apply them first"))])]),
        "flatten_fields": (tr("Flatten form fields"), tr(
            "Makes form fields and what's typed in them part of the page: they can't be filled "
            "in any more."), [
            _f("comments", "bool", tr("Comments and markups too"), False)]),
        "apply_redactions": (tr("Apply redactions"), tr(
            "Permanently removes everything under the redaction marks already in each file, as "
            "Apply redactions does."), [
            _f("scrub", "bool", tr("Remove hidden information (metadata, attachments, hidden "
                                   "text, scripts)"), True)]),
        "search_redact": (tr("Search & redact"), tr(
            "Marks every occurrence of each word or phrase for redaction, as Search & redact "
            "does, then applies the marks (with any marks already in the file)."), [
            _f("words", "lines", tr("Words or phrases (one per line)"), ""),
            _f("apply", "bool", tr("Apply the redactions (untick to only mark them for "
                                   "review)"), True),
            _f("scrub", "bool", tr("Remove hidden information (metadata, attachments, hidden "
                                   "text, scripts)"), True)]),
        "sanitize": (tr("Sanitize document"), tr(
            "Removes hidden or sensitive information, as Protect > Sanitize document does."),
            sanitize),
        "compress": (tr("Reduce file size"), tr(
            "Makes pictures smaller and drops what isn't used, as Document > Compress does. A "
            "file that wouldn't get smaller is kept as it is."), [
            _f("preset", "choice", tr("Image quality"), "Smaller (100 dpi images)",
               [("Good quality (150 dpi images)", tr("Good quality (150 dpi images)")),
                ("Smaller (100 dpi images)", tr("Smaller (100 dpi images)")),
                ("Smallest (72 dpi images)", tr("Smallest (72 dpi images)"))])]),
        "rotate": (tr("Rotate pages"), "", [
            _f("angle", "choice", tr("Turn"), 90, [(90, tr("90° clockwise")),
                                                    (180, tr("180°")),
                                                    (270, tr("90° counterclockwise"))]),
            _f("which", "choice", tr("Which pages"), "all",
               [("all", tr("All pages")), ("odd", tr("Odd pages")), ("even", tr("Even pages")),
                ("landscape", tr("Landscape pages")), ("portrait", tr("Portrait pages"))]),
            _pages_field()]),
        "delete_blank": (tr("Delete blank pages"), tr(
            "Deletes pages with no text and almost no ink (blank sheets from a scanner, specks "
            "and all). A page with markups, form fields or a few written words is kept. The "
            "report lists the pages deleted."), []),
        "add_password": (tr("Add password"), tr(
            "Protects each file, as Protect > Security properties does (AES-256). Passwords "
            "aren't saved in recipes."), [
            _f("open_pw", "password", tr("Open password"), ""),
            _f("owner_pw", "password", tr("Permissions password"), ""),
            _f("print", "bool", tr("Allow printing"), True),
            _f("copy", "bool", tr("Allow copying text and images"), True),
            _f("annotate", "bool", tr("Allow adding comments and markups"), False),
            _f("form", "bool", tr("Allow filling in form fields and signing"), True),
            _f("modify", "bool", tr("Allow changing the document"), False),
            _f("assemble", "bool", tr("Allow inserting, deleting and rotating pages"), False)]),
        "remove_password": (tr("Remove password"), tr(
            "Takes the password protection off. A file that opens without a password but has "
            "a permissions password needs that password."), [
            _f("password", "password", tr("Permissions password"), "")]),
        "properties": (tr("Set document properties"), tr(
            "{name} is the file's name. Empty boxes leave the property as it is."), [
            _f("title", "text", tr("Title"), ""), _f("author", "text", tr("Author"), ""),
            _f("subject", "text", tr("Subject"), ""), _f("keywords", "text", tr("Keywords"), "")]),
        "export": (tr("Export"), tr(
            "Saves a copy in another format next to the PDF, as File > Export to does, from the "
            "document as the steps before it left it."), [
            _f("format", "choice", tr("Format"), "word",
               [("word", tr("Microsoft Word (.docx)")), ("excel", tr("Microsoft Excel (.xlsx)")),
                ("ppt", tr("Microsoft PowerPoint (.pptx)")), ("png", tr("Images (PNG)")),
                ("jpg", tr("Images (JPEG)")), ("txt", tr("Plain text (.txt)"))]),
            _f("dpi", "int", tr("Picture resolution"), 200, (50, 600, " dpi"))]),
        "combine": (tr("Combine all into one PDF"), tr(
            "Puts the processed files together, in the order of the list, into one PDF (the "
            "last step)."), [
            _f("name", "text", tr("File name"), tr("Combined")),
            _f("bookmarks", "bool", tr("A bookmark for each file"), True),
            _f("keep_each", "bool", tr("Also save each file"), False)]),
    }


_TABLE = None


def steps_table():
    """{kind: (label, description, [Field])}, in the order the Add step menu lists them."""
    global _TABLE
    if _TABLE is None:
        _TABLE = _step_table()
    return _TABLE


EXPORT_EXT = {"word": "docx", "excel": "xlsx", "ppt": "pptx", "png": "png", "jpg": "jpg",
              "txt": "txt"}
NOT_EDITS = ("export", "combine")       # steps that don't change the document


def label(kind):
    return steps_table()[kind][0]


def step(kind, **options):
    """A step of this kind with its default options, changed by options."""
    opts = {f.key: f.default for f in steps_table()[kind][2]}
    opts.update(options)
    return {"kind": kind, "options": opts}


def summary(st):
    """A short line describing the step for the list (its label and main choice)."""
    kind, o = st["kind"], st["options"]
    name = label(kind)
    fields = {f.key: f for f in steps_table()[kind][2]}

    def choice(key):
        return dict(fields[key].extra).get(o.get(key), "")
    extra = ""
    if kind == "watermark":
        extra = os.path.basename(o.get("image") or "") or o.get("text", "")
    elif kind == "bates":
        extra = "%s%0*d" % (o.get("prefix", ""), int(o.get("digits", 6)), int(o.get("start", 1)))
    elif kind == "page_numbers":
        extra = o.get("text", "")
    elif kind in ("compress", "export", "ocr"):
        extra = choice({"compress": "preset", "export": "format", "ocr": "accuracy"}[kind])
    elif kind == "rotate":
        extra = choice("angle")
    elif kind == "search_redact":
        words = [w for w in (o.get("words") or "").splitlines() if w.strip()]
        extra = ", ".join(words[:3]) + (", ..." if len(words) > 3 else "")
    return "%s: %s" % (name, extra) if extra else name


def normalized(steps):
    """steps as read from settings or a file (not trusted): unknown kinds left out, each
    option of the right type (else its default), unknown options dropped."""
    out = []
    table = steps_table()
    for st in steps if isinstance(steps, list) else []:
        if not isinstance(st, dict) or st.get("kind") not in table:
            continue
        given = st.get("options") if isinstance(st.get("options"), dict) else {}
        opts = {}
        for f in table[st["kind"]][2]:
            v = given.get(f.key, f.default)
            try:
                if f.type == "bool":
                    v = v if isinstance(v, bool) else str(v).lower() in ("1", "true", "yes")
                elif f.type == "int":
                    v = min(f.extra[1], max(f.extra[0], int(v)))
                elif f.type == "float":
                    v = min(f.extra[1], max(f.extra[0], float(v)))
                elif f.type == "choice":
                    values = [c for c, _l in f.extra]
                    v = next((c for c in values if str(c) == str(v)), f.default)
                else:
                    v = v if isinstance(v, str) else f.default
            except (TypeError, ValueError):
                v = f.default
            opts[f.key] = v
        out.append({"kind": st["kind"], "options": opts})
    return out


def without_secrets(steps):
    """The steps with their passwords left out (recipes and the remembered setup never keep
    a password)."""
    table = steps_table()
    out = []
    for st in normalized(steps):
        for f in table[st["kind"]][2]:
            if f.type == "password":
                st["options"][f.key] = ""
        out.append(st)
    return out


def page_list(text, count):
    """'1-3, 5, 8-' -> page indices, within the document's count (a batch has documents of
    every length: a range past a file's last page stops there). Empty: all pages. ValueError
    when it isn't a page list."""
    text = (text or "").strip()
    if not text:
        return list(range(count))
    out = set()
    for part in text.replace(" ", "").split(","):
        if not part:
            continue
        a, sep, b = part.partition("-")
        a = int(a) if a else 1
        b = (int(b) if b else count) if sep else a
        if a < 1 or b < a:
            raise ValueError(tr("Page range {part} isn't valid.").format(part=part))
        out.update(range(a - 1, min(b, count)))
    return sorted(out)


def check_steps(steps):
    """What keeps these steps from running, as sentences ([]: they can run)."""
    if not steps:
        return [tr("Add at least one step.")]
    problems = []
    kinds = [st["kind"] for st in steps]
    if "combine" in kinds and (kinds.index("combine") != len(kinds) - 1 or
                               kinds.count("combine") > 1):
        problems.append(tr("Combine all into one PDF must be the last step."))
    if "pdfa" in kinds:
        after = kinds[kinds.index("pdfa") + 1:]
        if any(k not in NOT_EDITS for k in after):
            problems.append(tr("Save as PDF/A must come after the steps that change the "
                               "document (only Export and Combine can follow it)."))
        elif "add_password" in kinds:
            problems.append(tr("PDF/A doesn't allow passwords: leave out Add password, or "
                               "make a separate run for it."))
    for st in steps:
        o, kind = st["options"], st["kind"]
        name = label(kind)
        if kind == "add_password":
            if not o.get("open_pw") and not o.get("owner_pw"):
                problems.append(tr("{step}: type an open password, a permissions password, or "
                                   "both.").format(step=name))
            elif o.get("open_pw") and o.get("open_pw") == o.get("owner_pw"):
                problems.append(tr("{step}: use a different password for permissions: with the "
                                   "same one, anyone who can open it can change it.").format(
                                       step=name))
        elif kind == "search_redact" and not (o.get("words") or "").strip():
            problems.append(tr("{step}: type the words to look for.").format(step=name))
        elif kind == "watermark":
            if o.get("image"):
                if not os.path.isfile(o["image"]):
                    problems.append(tr("{step}: the picture {path} isn't there.").format(
                        step=name, path=o["image"]))
            elif not (o.get("text") or "").strip():
                problems.append(tr("{step}: type the text or choose a picture.").format(
                    step=name))
        elif kind == "header_footer" and not any(
                (o.get("%s_%s" % p) or "").strip() for p in POSITIONS):
            problems.append(tr("{step}: type something in at least one position.").format(
                step=name))
        elif kind == "page_numbers" and not (o.get("text") or "").strip():
            problems.append(tr("{step}: type the text.").format(step=name))
        elif kind == "properties" and not any(
                (o.get(k) or "").strip() for k in ("title", "author", "subject", "keywords")):
            problems.append(tr("{step}: type at least one property.").format(step=name))
        elif kind == "combine" and not _safe_name(o.get("name") or ""):
            problems.append(tr("{step}: type a file name.").format(step=name))
        if "pages" in o:
            try:
                page_list(o["pages"], 1)
            except ValueError:
                problems.append(tr("{step}: \"{pages}\" isn't a list of pages such as 1-3, 5, "
                                   "8-.").format(step=name, pages=o["pages"]))
    return problems


def changes_documents(steps):
    return any(st["kind"] not in NOT_EDITS for st in steps)


# ---- recipes --------------------------------------------------------------------------------
RECIPES_KEY = "batch/recipes"


def builtin_recipes():
    """The ready-made recipes: {name: steps}."""
    return {
        tr("Make searchable (OCR)"): [step("ocr")],
        tr("Archive (OCR + PDF/A)"): [step("ocr"), step("pdfa")],
        tr("Confidential (watermark + flatten)"): [step("watermark"), step("flatten_comments"),
                                                   step("flatten_fields")],
        tr("Bates number for production"): [step("bates")],
        tr("Shrink for email"): [step("compress")],
    }


def _stored(settings):
    try:
        data = json.loads(settings.value(RECIPES_KEY, "") or "{}")
    except (TypeError, ValueError):
        return {}
    return {str(k): normalized(v) for k, v in data.items()} if isinstance(data, dict) else {}


def recipes(settings):
    """Every recipe: the ready-made ones, then the user's ({name: steps}); a recipe saved
    with a ready-made one's name takes its place."""
    out = builtin_recipes()
    out.update(_stored(settings))
    return out


def user_recipes(settings):
    return set(_stored(settings))


def save_recipe(settings, name, steps):
    data = _stored(settings)
    data[name] = without_secrets(steps)
    settings.setValue(RECIPES_KEY, json.dumps(data))


def delete_recipe(settings, name):
    data = _stored(settings)
    if data.pop(name, None) is not None:
        settings.setValue(RECIPES_KEY, json.dumps(data))
        return True
    return False


# ---- the files ------------------------------------------------------------------------------
Item = namedtuple("Item", "path root")      # root: the folder it was added from (or its own)


def processed_names():
    return {"processed", tr("Processed").lower()}


def files_in(folder, subfolders=True):
    """The PDFs in folder (and its subfolders), sorted by folder and name, as Items whose
    root is folder. "Processed" folders (where a batch writes) are left out."""
    folder = os.path.abspath(folder)
    skip = processed_names()
    out = []
    for here, dirs, files in os.walk(folder):
        dirs[:] = sorted(d for d in dirs if d.lower() not in skip and not d.startswith("."))
        for name in sorted(files, key=str.lower):
            if name.lower().endswith(".pdf"):
                out.append(Item(os.path.join(here, name), folder))
        if not subfolders:
            break
    return out


def page_count(path):
    """Pages in the PDF at path, for the list: a number, or a short word when it can't be
    told (protected, unreadable)."""
    try:
        with pymupdf.open(path) as doc:
            if doc.needs_pass:
                return tr("protected")
            if not doc.is_pdf:
                return tr("not a PDF")
            return doc.page_count
    except Exception:
        return tr("can't read")


_BAD_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def _safe_name(name):
    return _BAD_CHARS.sub("_", name).strip().strip(".")


# ---- a document opened for the batch -----------------------------------------------------------
class _Mute:
    """Stands for DocumentView's signals: nobody is listening to a batch document."""

    def emit(self, *a, **k):
        pass

    def connect(self, *a, **k):
        pass


class Skip(Exception):
    """The file is left out (the reason is the message)."""


class _Stop(Exception):
    """Stop now was clicked: the current file is dropped."""


class BatchDoc:
    """A PDF opened for the batch, without a window. DocumentView's own steps (flatten,
    apply_redactions, search_redact, sanitize, set_security, delete_pages, save...) run on
    it unchanged: any attribute it doesn't have is looked up on DocumentView, so a method
    runs here exactly as in a tab, and its edits go through modify() below, which simply
    makes them (a batch has no undo, repainting or questions to ask). Opening follows
    DocumentView.__init__: the file's protection and passwords are kept so Save keeps them."""

    def __init__(self, path, passwords=None, ask_password=None):
        self.path = os.path.abspath(path)
        self.untitled = False
        with open(self.path, "rb") as f:
            data = f.read()
        try:
            doc = pymupdf.open(stream=data, filetype="pdf")
        except Exception as ex:
            raise ValueError(tr("It isn't a PDF KanzonasPDF can read ({error}).").format(
                error=ex)) from None
        self.doc = doc
        self._orig_data = data
        self._orig_enc = None
        if (doc.metadata or {}).get("encryption") or doc.needs_pass:
            self._orig_enc = {"needs_pass": bool(doc.needs_pass), "user_pw": None,
                              "owner_pw": None}
        known = passwords if passwords is not None else []
        if doc.needs_pass:
            rc, pw = 0, None
            for cand in known:
                rc = doc.authenticate(cand)
                if rc:
                    pw = cand
                    break
            if not rc and ask_password is not None:
                cand = ask_password(self.path, "open")
                if cand:
                    rc = doc.authenticate(cand)
                    if rc:
                        pw = cand
                        known.append(cand)      # (tried first on the next protected file)
                    else:
                        doc.close()
                        raise Skip(tr("The password given doesn't open it."))
            if not rc:
                doc.close()
                raise Skip(tr("It's password-protected and no password was given."))
            if rc & 2:
                self._orig_enc["user_pw"] = pw
            if rc & 4:
                self._orig_enc["owner_pw"] = pw
        if doc.page_count == 0:
            doc.close()
            raise ValueError(tr("The PDF has no pages"))
        if self._orig_enc is not None:
            self._orig_enc["perms"] = doc.permissions
        try:
            self.signed = doc.get_sigflags() >= 1 or self._has_filled_signature()
        except Exception:
            self.signed = False
        if self._orig_enc is None and not self.signed:
            self._orig_data = None
        self._owner_authorized = self._orig_enc is None or bool(self._orig_enc.get("owner_pw"))
        self._check_permissions()
        self.dirty = False
        self.edits = 0                  # edits made (a file a step wrote is stale after one)
        self.security = None
        self.selection = None
        self.selected_model = None
        self.extra = []
        self.sig_results = []
        self._undo, self._redo = [], []
        self._fonts_added = False
        self._obj_cache = {}
        self._card_cache = {}
        self._backup_path = None
        self.disk_stamp = None

    def __getattr__(self, name):
        # (only called for what this object doesn't have itself)
        from .document_view import DocumentView
        try:
            attr = DocumentView.__dict__[name]
        except KeyError:
            raise AttributeError(name) from None
        from PySide6.QtCore import Signal
        if isinstance(attr, Signal):
            return _Mute()
        if isinstance(attr, staticmethod):
            return attr.__func__
        if isinstance(attr, classmethod):
            return types.MethodType(attr.__func__, DocumentView)
        if isinstance(attr, property):
            return attr.fget(self)
        if inspect.isfunction(attr):
            return types.MethodType(attr, self)
        return attr

    # what DocumentView does with its window, undo and questions: not here
    def modify(self, fn, pages=None, structural=False, permission=pymupdf.PDF_PERM_MODIFY,
               changed=None):
        if not self.allowed(permission):
            raise PermissionError(tr("This PDF is protected against changes. Its permissions "
                                     "password is needed."))
        from .document_view import _collect_all
        if structural:
            _collect_all()
        doc = self.doc
        fn()
        if self.doc is not doc:
            doc.close()         # (replaced by the edit, e.g. Apply redactions' clean copy)
        if structural and self._stale_pages():
            try:
                pymupdf.mupdf.pdf_sync_open_pages(pymupdf._as_pdf_document(self.doc))
            except Exception:
                pass
            if self._stale_pages():
                old = self.doc
                self.doc = self._open_snapshot(self._snapshot())
                old.close()
        self.dirty = True
        self.edits += 1
        return True

    def set_security(self, open_pw="", owner_pw="", perms=-1):
        from .document_view import DocumentView
        DocumentView.set_security(self, open_pw, owner_pw, perms)
        self.edits += 1

    def clear_selection(self):
        pass

    def commit_pending(self):
        pass

    def _page_turned(self, index):
        pass

    def _ask_original_passwords(self):
        """Save keeps a protected file's passwords; here they can't be asked for."""
        enc = self._orig_enc
        if not enc.get("owner_pw") or (enc.get("needs_pass") and not enc.get("user_pw")):
            raise PermissionError(tr("Its passwords are needed to keep its protection: add Remove "
                                     "password or Add password, or give its permissions "
                                     "password."))

    def reload(self, path):
        """Show the PDF a step wrote at path (Reduce file size, Save as PDF/A) as this
        document from now on, unlocked with the passwords known."""
        with open(path, "rb") as f:
            fresh = pymupdf.open(stream=f.read(), filetype="pdf")
        if fresh.needs_pass:
            sec = self.security or {}
            enc = self._orig_enc or {}
            for pw in (sec.get("owner_pw"), sec.get("open_pw"), enc.get("owner_pw"),
                       enc.get("user_pw")):
                if pw and fresh.authenticate(pw):
                    break
        self.doc.close()
        self.doc = fresh
        self._orig_data = None
        self.dirty = True

    def close(self):
        try:
            self.doc.close()
        except Exception:
            pass


# ---- the run --------------------------------------------------------------------------------
class Result:
    """What happened to one file (or the combined PDF)."""

    def __init__(self, path, status=None, reason="", combined=False):
        self.path = path
        self.status = status
        self.reason = reason
        self.outputs = []
        self.notes = []
        self.combined = combined

    def details(self):
        return "; ".join([self.reason] * bool(self.reason) + self.notes)


class _File:
    """The file being processed: its document, notes and what it produced so far."""

    def __init__(self, index, item, view, bates):
        self.index = index
        self.item = item
        self.view = view
        self.bates = bates              # {step index: next Bates number} (committed on success)
        self.bates_first = ""
        self.notes = []
        self.staged = []                # [(file in the temporary folder, suffix)]
        self.ready = None               # a file a step wrote that is this document as it is
        self.ready_at = -1


class Batch:
    """files: [Item]; steps: [{"kind", "options"}]; output: {
        "mode": "next" (a Processed folder next to each file) or "folder",
        "folder": the folder for mode "folder",
        "keep_structure": subfolders of the folder a file was added from kept below it,
        "pattern": the name, with {name} {n} {date} {bates},
        "overwrite": "ask" | "number" | "replace" | "skip" when the output exists,
        "replace_originals": an output may replace its own input file,
        "protected": "ask" | "skip" for files that need a password to open}.
    Callbacks (all optional): ask_password(path, "open" or "permissions") -> password or
    None; ask_overwrite(path) -> "replace" | "replace_all" | "skip" | "skip_all";
    before_write(path) -> a token, or None not to write it (a tab showing it with unsaved
    changes); after_write(token); pump(): keep the window alive during a long single step.
    cancel: finish the current file, then stop; stop: drop the current file now."""

    def __init__(self, files, steps, output, ask_password=None, ask_overwrite=None,
                 before_write=None, after_write=None, pump=None):
        self.files = [f if isinstance(f, Item) else Item(f, os.path.dirname(os.path.abspath(f)))
                      for f in files]
        self.steps = normalized(steps)
        self.output = dict({"mode": "next", "folder": "", "keep_structure": True,
                            "pattern": "{name}", "overwrite": "ask",
                            "replace_originals": False, "protected": "ask"}, **output)
        self.ask_password = ask_password
        self.ask_overwrite = ask_overwrite
        self.before_write = before_write
        self.after_write = after_write
        self.pump = pump
        self.cancel = False
        self.stop = False
        self.results = []
        self.passwords = []             # the passwords given so far (tried on each file)
        self._bates = {}
        self._written = set()
        self._parts = []                # (index, file) for Combine
        self._pool = None
        self._tmp = None
        self._overwrite = self.output["overwrite"]
        self._inputs = {self._key(f.path) for f in self.files}
        self.combine = self.steps[-1]["options"] if self.steps and \
            self.steps[-1]["kind"] == "combine" else None

    # ---- driving it
    def run(self):
        """The generator: yields (file index, fraction of that file done, text), or WAIT
        while a worker thread is busy."""
        self._tmp = tempfile.mkdtemp(prefix="kanzonas-batch-")
        try:
            for i, item in enumerate(self.files):
                if self.cancel or self.stop:
                    r = Result(item.path, CANCELED, tr("Not processed: the run was canceled."))
                    self.results.append(r)
                    continue
                yield (i, 0.0, os.path.basename(item.path))
                yield from self._one(i, item)
            if self.combine is not None:
                yield from self._combine()
        finally:
            if self._pool is not None:
                self._pool.shutdown(wait=True)
                self._pool = None
            shutil.rmtree(self._tmp, ignore_errors=True)
            gc.collect()

    def run_all(self):
        """Run to the end without a window (tests, scripts). Returns the results."""
        import time
        for ev in self.run():
            if ev is WAIT:
                time.sleep(0.005)
        return self.results

    def counts(self):
        out = {DONE: 0, SKIPPED: 0, FAILED: 0, CANCELED: 0}
        for r in self.results:
            out[r.status] = out.get(r.status, 0) + 1
        return out

    # ---- one file
    def _one(self, i, item):
        res = Result(item.path)
        self.results.append(res)
        f = None
        step_name = ""
        try:
            protected_skip = self.output["protected"] == "skip"
            try:
                view = BatchDoc(item.path, self.passwords,
                                None if protected_skip else self._ask_password)
            except OSError as ex:
                raise ValueError(tr("Couldn't read it: {error}").format(
                    error=ex.strerror or ex)) from None
            f = _File(i, item, view, dict(self._bates))
            edits = changes_documents(self.steps)
            if edits and view.signed:
                raise Skip(tr("It's digitally signed: changing it would make the signature "
                              "invalid."))
            if edits and not view.allowed(pymupdf.PDF_PERM_MODIFY):
                self._unlock(view)
            n = len(self.steps)
            for k, st in enumerate(self.steps):
                if self.stop:
                    raise _Stop()
                if st["kind"] == "combine":
                    break
                step_name = label(st["kind"])
                yield (i, k / n, "%s: %s" % (os.path.basename(item.path), step_name))
                run = getattr(self, "_do_" + st["kind"])(f, k, st["options"])
                if inspect.isgenerator(run):
                    for ev in run:
                        if self.stop and ev is not WAIT:
                            raise _Stop()
                        yield WAIT if ev is WAIT else (i, (k + min(1.0, ev)) / n,
                                                        "%s: %s" % (os.path.basename(item.path),
                                                                    step_name))
            step_name = ""
            if self.stop:
                raise _Stop()
            yield (i, 1.0, os.path.basename(item.path))
            self._finish(f, res, edits)
            res.status = DONE
            self._bates = f.bates
        except _Stop:
            res.status = CANCELED
            res.reason = tr("Stopped: nothing was written for this file.")
        except Skip as ex:
            res.status = SKIPPED
            res.reason = str(ex)
        except Exception as ex:
            res.status = FAILED
            text = str(ex) or ex.__class__.__name__
            res.reason = "%s: %s" % (step_name, text) if step_name else text
        finally:
            if f is not None:
                if res.status == DONE:
                    # (only then: a failed file's notes, its Bates numbers say, never were)
                    res.notes = f.notes + res.notes
                for tmp, _suffix in f.staged:
                    _remove(tmp)
                if f.ready:
                    _remove(f.ready)
                f.view.close()
                f.view = None
            del f
            gc.collect()        # (one document at a time: this one's memory is freed now)

    def _ask_password(self, path, kind):
        if self.ask_password is None:
            return None
        return self.ask_password(path, kind)

    def _unlock(self, view):
        """A file that opens but doesn't allow changes: its permissions password (one given
        before, else asked)."""
        given = [st["options"].get("password") for st in self.steps
                 if st["kind"] == "remove_password"]
        for pw in self.passwords + [pw for pw in given if pw]:
            if view.unlock(pw):
                return
        pw = None if self.output["protected"] == "skip" else \
            self._ask_password(view.path, "permissions")
        if pw and view.unlock(pw):
            self.passwords.append(pw)
            return
        raise Skip(tr("It doesn't allow changes, and its permissions password wasn't given."))

    # ---- where things go
    @staticmethod
    def _key(path):
        return os.path.normcase(os.path.abspath(path))

    def folder_for(self, item):
        o = self.output
        if o["mode"] == "folder" and o.get("folder"):
            folder = o["folder"]
            if o.get("keep_structure"):
                rel = os.path.relpath(os.path.dirname(os.path.abspath(item.path)), item.root)
                if rel != "." and not rel.startswith(".."):
                    folder = os.path.join(folder, rel)
            return os.path.abspath(folder)
        return os.path.join(os.path.dirname(os.path.abspath(item.path)), tr("Processed"))

    def name_for(self, i, item, bates=""):
        base = os.path.splitext(os.path.basename(item.path))[0]
        width = max(3, len(str(len(self.files))))
        pattern = self.output.get("pattern") or "{name}"
        name = (pattern.replace("{name}", base).replace("{n}", str(i + 1).zfill(width))
                .replace("{date}", date.today().isoformat()).replace("{bates}", bates or ""))
        return _safe_name(name) or base

    def output_path(self, i, item, ext=".pdf", bates=""):
        """Where the file's output goes (before checking what's there)."""
        return os.path.join(self.folder_for(item), self.name_for(i, item, bates) + ext)

    def _resolve(self, path, own_input=None):
        """The file to write for path, after the rules for files that exist: Skip when it's
        not to be written."""
        key = self._key(path)
        name = os.path.basename(path)
        if own_input is not None and key == self._key(own_input):
            if not self.output.get("replace_originals"):
                raise Skip(tr("Its output would replace the original file. Choose another "
                              "folder or name, or allow replacing the original files."))
        elif key in self._inputs or key in self._written:
            # another file of the list (perhaps not processed yet), or written by this run
            path = _numbered(path)
        elif os.path.exists(path):
            rule = self._overwrite
            if rule == "ask":
                answer = self.ask_overwrite(path) if self.ask_overwrite else "skip"
                if answer in ("replace_all", "skip_all"):
                    self._overwrite = answer.split("_")[0]
                rule = (answer or "skip").split("_")[0]
            if rule == "number":
                path = _numbered(path)
            elif rule != "replace":
                raise Skip(tr("{name} already exists.").format(name=name))
        self._written.add(self._key(path))
        return path

    def _guard(self, path):
        """before_write for a file about to be replaced: a token for after_write, or Skip."""
        if self.before_write is None or not os.path.exists(path):
            return None
        token = self.before_write(path)
        if token is None:
            raise Skip(tr("{name} is open with unsaved changes.").format(
                name=os.path.basename(path)))
        return token

    def _finish(self, f, res, edits):
        """Write what the file produced: its PDF (when a step changes documents) and its
        exports, all or nothing."""
        view, item = f.view, f.item
        ready = f.ready if f.ready and f.ready_at == view.edits else None
        if self.combine is not None:
            if not view.allowed(pymupdf.PDF_PERM_COPY):
                from . import combine
                raise PermissionError(combine.not_allowed(item.path))
            part = os.path.join(self._tmp, "combine", "%05d" % f.index,
                                os.path.splitext(os.path.basename(item.path))[0] + ".pdf")
            os.makedirs(os.path.dirname(part), exist_ok=True)
            if ready:
                shutil.copyfile(ready, part)
            else:
                # (a part only for combining: written without its protection, as Combine
                # files does with a protected PDF once its password is given)
                view.doc.save(part, garbage=1, deflate=True)
            self._parts.append((f.index, part))
        plan = []
        if edits and (self.combine is None or self.combine.get("keep_each")):
            plan.append(("pdf", self._resolve(self.output_path(f.index, item, ".pdf",
                                                               f.bates_first), item.path)))
        for tmp, suffix in f.staged:
            plan.append((tmp, self._resolve(self.output_path(f.index, item, suffix,
                                                             f.bates_first))))
        tokens = [(target, self._guard(target)) for _src, target in plan]
        for src, target in plan:
            os.makedirs(os.path.dirname(target), exist_ok=True)
            if src != "pdf":
                _place(src, target)
            elif ready:
                _place(ready, target, keep=True)
            elif not view.dirty and os.path.exists(item.path) and \
                    self._key(target) != self._key(item.path):
                _place(item.path, target, keep=True)        # unchanged: an exact copy
                f.notes.append(tr("Nothing needed changing: copied as it was."))
            else:
                view.save(target)
            res.outputs.append(target)
        f.staged = []
        for _target, token in tokens:
            if token is not None and self.after_write is not None:
                self.after_write(token)

    # ---- a worker thread for what doesn't touch an open document
    def _worker(self, fn, *args):
        if self._pool is None:
            from concurrent.futures import ThreadPoolExecutor
            self._pool = ThreadPoolExecutor(max_workers=1)
        fut = self._pool.submit(fn, *args)
        while not fut.done():
            yield WAIT
        return fut.result()

    def _step(self):
        """For long single steps (PDF/A): keep the window alive; False when stopped."""
        if self.pump is not None:
            self.pump()
        return not self.stop

    # ---- the steps (each runs on f.view; a generator yields how far it is, 0..1)
    def _do_ocr(self, f, k, o):
        from . import ocr
        view = f.view
        pages = page_list(o.get("pages"), view.doc.page_count)
        if o.get("skip_text"):
            pages = [i for i in pages if not view.page_has_text(i)]
        if not pages:
            f.notes.append(tr("OCR: every page already has text."))
            return
        accuracy = o.get("accuracy") or "auto"
        lines = done = 0
        for n, i in enumerate(pages):
            got = yield from self._ocr_page(view, i, accuracy)
            if got is None:
                raise _Stop()
            res, rendering = got
            count = {}

            def add(i=i, res=res, rendering=rendering, count=count):
                count["n"] = ocr.add_text_layer(view.doc[i], res, rendering)
            view.modify(add, [i])
            lines += count["n"]
            done += 1
            yield (n + 1) / len(pages)
        f.notes.append(tr("OCR added {lines} lines of text on {pages} page(s)").format(
            lines=lines, pages=done))

    def _ocr_page(self, view, i, accuracy):
        """Recognize page i the way Recognize text does (DocumentView.run_ocr): sharper when
        Auto finds small text, turned when it's upside down or sideways. (rendering, results)
        or None when stopped; the page image is let go once read."""
        from . import ocr
        doc = view.doc
        stop = lambda: self.stop        # noqa: E731

        def read(rendering):
            out = yield from self._worker(ocr.recognize, rendering, stop)
            return None if self.stop else out
        dpi = ocr.page_dpi(doc[i], ocr.ACCURACY_DPI.get(accuracy, ocr.ACCURACY_DPI["fast"]))
        best = ocr.Rendering(doc[i], dpi=dpi)
        res = yield from read(best)
        if res is None:
            return None
        sharper = ocr.page_dpi(doc[i], ocr.ACCURACY_DPI["high"])
        if accuracy == "auto" and sharper > dpi and ocr.needs_sharper(res, best):
            dpi = sharper
            best = ocr.Rendering(doc[i], dpi=dpi)
            res = yield from read(best)
            if res is None:
                return None
        turn = 0
        if ocr.upside_down(res):
            r = ocr.Rendering(doc[i], 180, dpi=dpi)
            alt = yield from read(r)
            if alt is None:
                return None
            if ocr.score(alt) >= ocr.score(res):
                best, res, turn = r, alt, 180
            else:
                r.release()
        turns = (90, 180, 270) if accuracy == "high" else \
            ((90, 270) if ocr.mostly_vertical(res) else ())
        for extra in turns:
            if extra == turn:
                continue
            r = ocr.Rendering(doc[i], extra, dpi=dpi)
            alt = yield from read(r)
            if alt is None:
                return None
            if ocr.score(alt) > 1.25 * ocr.score(res) + 5:
                best.release()
                best, res = r, alt
            else:
                r.release()
        best.release()
        return res, best

    def _do_pdfa(self, f, k, o):
        from . import pdfa, pdfa_ui
        view = f.view
        if pdfa_ui.is_protected(view):
            raise ValueError(tr("It's password-protected, and PDF/A doesn't allow encryption: "
                                "put Remove password before Save as PDF/A."))
        out = os.path.join(self._tmp, "pdfa-%05d.pdf" % f.index)
        yield 0.1
        result = pdfa.convert(view.doc.tobytes(), out, step=self._step)
        if result is None:
            raise _Stop()
        view.reload(out)
        if f.ready and f.ready != out:
            _remove(f.ready)
        f.ready, f.ready_at = out, view.edits
        f.notes.append(tr("PDF/A-{part}b").format(part=result["part"]))
        if result["remaining"]:
            f.notes.append(tr("PDF/A: {n} problem(s) couldn't be fixed (File > Check PDF/A "
                              "lists them)").format(n=len(result["remaining"])))

    def _hf(self, f, k, texts, o, prefix="", start=1, digits=6):
        """Header & footer texts on the pages (page_tools through DocumentView); a {bates}
        number continues from the previous file's last one."""
        view = f.view
        pages = page_list(o.get("pages"), view.doc.page_count)
        if not pages:
            f.notes.append(tr("{step}: none of the pages chosen are in this file.").format(
                step=label(self.steps[k]["kind"])))
            return
        bates = any("{bates}" in t for t in texts.values())
        first = f.bates.get(k, int(start)) if bates else int(start)
        spec = {"texts": texts, "size": float(o.get("size", 9)), "color": o.get("color"),
                "margin": float(o.get("margin", 24)), "pages": pages, "bates_prefix": prefix,
                "bates_start": first, "bates_digits": int(digits)}
        view.add_header_footer(spec)
        if bates:
            f.bates[k] = first + len(pages)
            a = "%s%0*d" % (prefix, int(digits), first)
            b = "%s%0*d" % (prefix, int(digits), first + len(pages) - 1)
            f.bates_first = f.bates_first or a
            f.notes.append(tr("Bates {first} to {last}").format(first=a, last=b))

    @staticmethod
    def _position(o):
        where, _sep, align = (o.get("position") or "footer-center").partition("-")
        return (where, align)

    def _do_header_footer(self, f, k, o):
        texts = {p: o.get("%s_%s" % p) for p in POSITIONS if (o.get("%s_%s" % p) or "").strip()}
        self._hf(f, k, texts, o, o.get("bates_prefix", ""), o.get("bates_start", 1),
                 o.get("bates_digits", 6))

    def _do_page_numbers(self, f, k, o):
        self._hf(f, k, {self._position(o): o.get("text") or "{page}"}, o)

    def _do_bates(self, f, k, o):
        self._hf(f, k, {self._position(o): "{bates}"}, o, o.get("prefix", ""),
                 o.get("start", 1), o.get("digits", 6))

    def _do_watermark(self, f, k, o):
        view = f.view
        pages = page_list(o.get("pages"), view.doc.page_count)
        if not pages:
            return
        common = {"pages": pages, "opacity": int(o.get("opacity", 25)) / 100,
                  "behind": bool(o.get("behind"))}
        if o.get("image"):
            spec = dict(common, image=o["image"], scale=0.5)
        else:
            spec = dict(common, text=o.get("text", "").strip(), size=float(o.get("size", 80)),
                        color=o.get("color"), angle=int(o.get("angle", 45)))
        view.add_watermark(spec)

    def _do_flatten_comments(self, f, k, o):
        view = f.view
        if o.get("redactions") == "apply" and view.pending_redactions():
            n = view.pending_redactions()
            view.apply_redactions(True)
            f.notes.append(tr("Applied {n} redaction(s)").format(n=n))
        view.flatten(None, widgets=False)
        n = view.pending_redactions()
        if n:
            f.notes.append(tr("{n} redaction mark(s) not applied yet were kept as marks").format(
                n=n))

    def _do_flatten_fields(self, f, k, o):
        view = f.view
        if o.get("comments"):
            view.flatten(None, widgets=True)
            return
        if not any(True for page in view.doc for _w in page.widgets()):
            f.notes.append(tr("No form fields to flatten"))
            return
        view.modify(lambda: view.doc.bake(annots=False, widgets=True), structural=True)

    def _do_apply_redactions(self, f, k, o):
        view = f.view
        n = view.pending_redactions()
        if not n:
            f.notes.append(tr("No redaction marks to apply"))
            return
        view.apply_redactions(bool(o.get("scrub", True)))
        f.notes.append(tr("Applied {n} redaction(s)").format(n=n))

    def _do_search_redact(self, f, k, o):
        view = f.view
        terms = []
        for w in (o.get("words") or "").splitlines():
            w = w.strip()
            if w and w.lower() not in (t.lower() for t in terms):
                terms.append(w)
        on_pages = elsewhere = 0
        for n, term in enumerate(terms):
            hits = view.search_redact(term)
            on_pages += hits
            if not hits and o.get("apply", True) and any(view.hidden_matches(term).values()):
                # only in fields, notes, links, bookmarks or properties: removed from there,
                # as Search & redact offers
                view.remove_term(term)
                elsewhere += 1
            yield (n + 1) / (len(terms) + 1)
        pending = view.pending_redactions()
        if o.get("apply", True) and pending:
            view.apply_redactions(bool(o.get("scrub", True)))
            f.notes.append(tr("Redacted {n} match(es) on the pages").format(n=on_pages))
        else:
            f.notes.append(tr("Marked {n} occurrence(s) on the pages.").format(n=on_pages))
        if elsewhere:
            f.notes.append(tr("{n} word(s) found only outside the pages (fields, notes, "
                              "bookmarks, properties) were removed there").format(n=elsewhere))

    def _do_sanitize(self, f, k, o):
        from .document_view import DocumentView
        f.view.sanitize({key: bool(o.get(key)) for key, _l, _d in DocumentView.SANITIZE_OPTIONS})

    def _do_compress(self, f, k, o):
        from . import page_tools
        view = f.view
        data, password, protect = view.copy_protection()
        out = os.path.join(self._tmp, "small-%05d-%d.pdf" % (f.index, k))
        yield 0.1
        before, after = page_tools.compress(data, out, o.get("preset") or
                                            "Smaller (100 dpi images)", password, protect)
        now = os.path.getsize(f.ready) if f.ready and f.ready_at == view.edits else \
            os.path.getsize(view.path) if not view.dirty else before
        if after >= now:
            _remove(out)
            f.notes.append(tr("Already as small as it gets: kept as it was"))
            return
        view.reload(out)
        if f.ready:
            _remove(f.ready)
        f.ready, f.ready_at = out, view.edits
        f.notes.append("%s → %s" % (file_size(now), file_size(after)))

    def _do_rotate(self, f, k, o):
        view = f.view
        doc = view.doc
        pages = page_list(o.get("pages"), doc.page_count)
        which = o.get("which") or "all"
        if which == "odd":
            pages = [i for i in pages if i % 2 == 0]
        elif which == "even":
            pages = [i for i in pages if i % 2 == 1]
        elif which in ("landscape", "portrait"):
            wide = which == "landscape"
            pages = [i for i in pages if (doc[i].rect.width > doc[i].rect.height) == wide]
        for i in pages:
            view.rotate_page(i, int(o.get("angle") or 90))
        if not pages:
            f.notes.append(tr("No page to turn"))

    def _do_delete_blank(self, f, k, o):
        from . import page_tools
        view = f.view
        n = view.doc.page_count
        blank = []
        for i in range(n):
            if page_tools.is_blank(view.doc[i]):
                blank.append(i)
            if i % 8 == 7:
                yield (i + 1) / n
        if not blank:
            return
        if len(blank) == n:
            f.notes.append(tr("Every page looks blank: none was deleted"))
            return
        view.delete_pages(blank)
        f.notes.append(tr("Deleted blank page(s): {pages}").format(
            pages=", ".join(str(i + 1) for i in blank)))

    PERMS = {"print": pymupdf.PDF_PERM_PRINT | pymupdf.PDF_PERM_PRINT_HQ,
             "copy": pymupdf.PDF_PERM_COPY, "annotate": pymupdf.PDF_PERM_ANNOTATE,
             "form": pymupdf.PDF_PERM_FORM, "modify": pymupdf.PDF_PERM_MODIFY,
             "assemble": pymupdf.PDF_PERM_ASSEMBLE}

    def _do_add_password(self, f, k, o):
        view = f.view
        if not view.owner_authorized():
            self._unlock(view)
        perms = pymupdf.PDF_PERM_ACCESSIBILITY | sum(
            flag for key, flag in self.PERMS.items() if o.get(key))
        owner = o.get("owner_pw") or ""
        view.set_security(o.get("open_pw") or "", owner, perms if owner else -1)

    def _do_remove_password(self, f, k, o):
        view = f.view
        if view._orig_enc is None and view.security is None:
            f.notes.append(tr("It had no password"))
            return
        if not view.owner_authorized():
            pw = o.get("password") or ""
            if not (pw and view.unlock(pw)):
                self._unlock(view)
        view.set_security("", "", -1)

    def _do_properties(self, f, k, o):
        view = f.view
        base = os.path.splitext(os.path.basename(f.item.path))[0]
        meta = {key: o[key].replace("{name}", base)
                for key in ("title", "author", "subject", "keywords") if (o.get(key) or "").strip()}
        if meta:
            view.modify(lambda: view.doc.set_metadata(meta), [])

    def _do_export(self, f, k, o):
        from . import export
        view = f.view
        if not view.allowed(pymupdf.PDF_PERM_COPY):
            raise PermissionError(tr("{operation} is not allowed by this PDF's permissions.")
                                  .format(operation=tr("Exporting")))
        fmt = o.get("format") or "word"
        ext = EXPORT_EXT[fmt]
        folder = os.path.join(self._tmp, "out-%05d-%d" % (f.index, k))
        os.makedirs(folder, exist_ok=True)
        data = view.doc.tobytes()
        if fmt in ("png", "jpg"):
            base = os.path.join(folder, "x")
            paths = yield from self._worker(export.to_images, data, base, fmt,
                                            int(o.get("dpi") or 200))
            for i, p in enumerate(paths):
                f.staged.append((p, "_p%d.%s" % (i + 1, ext)))
            return
        out = os.path.join(folder, "x." + ext)
        fn = {"word": export.to_word, "excel": export.to_excel, "ppt": export.to_powerpoint,
              "txt": export.to_text}[fmt]
        yield from self._worker(fn, data, out)
        f.staged.append((out, "." + ext))

    def _do_combine(self, f, k, o):
        pass                            # (done once every file is: _combine)

    def _combine(self):
        o = self.combine
        n = len(self.files)
        first = self.files[0] if self.files else None
        name = _safe_name(o.get("name") or "") or tr("Combined")
        target = os.path.join(self.folder_for(first) if first else os.getcwd(), name + ".pdf")
        res = Result(target, combined=True)
        self.results.append(res)
        if self.cancel or self.stop:
            res.status, res.reason = CANCELED, tr("Not combined: the run was canceled.")
            return
        if not self._parts:
            res.status, res.reason = SKIPPED, tr("No file to combine.")
            return
        yield (n, 0.0, tr("Combining {n} files...").format(n=len(self._parts)))
        try:
            from . import combine
            target = self._resolve(target)
            res.path = target
            token = self._guard(target)
            tmp = os.path.join(self._tmp, "combined.pdf")
            pages = combine.combine([p for _i, p in sorted(self._parts)], tmp,
                                    bookmarks=bool(o.get("bookmarks", True)))
            os.makedirs(os.path.dirname(target), exist_ok=True)
            _place(tmp, target)
            if token is not None and self.after_write is not None:
                self.after_write(token)
            res.status = DONE
            res.outputs.append(target)
            res.notes.append(tr("{n} files, {pages} pages").format(n=len(self._parts),
                                                                   pages=pages))
            left = n - len(self._parts)
            if left:
                res.notes.append(tr("{n} file(s) left out: see above").format(n=left))
        except Skip as ex:
            res.status, res.reason = SKIPPED, str(ex)
        except Exception as ex:
            res.status, res.reason = FAILED, str(ex) or ex.__class__.__name__


def file_size(n):
    """1.25 MB, 340 KB."""
    return "%.2f MB" % (n / 1e6) if n >= 1e6 else "%d KB" % max(1, round(n / 1e3))


def _numbered(path):
    """path with " (2)", " (3)"... before its extension: the first that isn't there."""
    base, ext = os.path.splitext(path)
    k = 2
    while os.path.exists("%s (%d)%s" % (base, k, ext)):
        k += 1
    return "%s (%d)%s" % (base, k, ext)


def _remove(path):
    try:
        os.remove(path)
    except OSError:
        pass


def _place(src, target, keep=False):
    """Put the file src at target in one step (the file at target is whole before and
    after): copied next to target, then renamed over it. keep: src stays."""
    tmp = target + ".kanzonas-tmp"
    try:
        shutil.copyfile(src, tmp)
        os.replace(tmp, target)
    except BaseException:
        _remove(tmp)
        raise
    if not keep:
        _remove(src)


# ---- the report -------------------------------------------------------------------------------
def report_rows(results):
    """[(file, status, outputs, details)] in the user's language."""
    return [(r.path, STATUS_LABELS.get(r.status, r.status), "; ".join(r.outputs), r.details())
            for r in results]


def report_text(results):
    lines = []
    for path, status, outputs, details in report_rows(results):
        lines.append("%s: %s" % (status, path))
        if outputs:
            lines.append("    → " + outputs)
        if details:
            lines.append("    " + details)
    return "\n".join(lines) + "\n"


def write_report(results, path):
    """The report as a .csv (opens in Excel; cells that would run as formulas are kept as
    text) or, for any other name, plain text."""
    if path.lower().endswith(".csv"):
        import csv
        from .export import csv_cell
        with open(path, "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.writer(fh)
            w.writerow([tr("File"), tr("Status"), tr("Output"), tr("Details")])
            for row in report_rows(results):
                w.writerow([csv_cell(c) for c in row])
    else:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(report_text(results))
