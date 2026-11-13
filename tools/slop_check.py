"""A search for slop: what AI tools (and hurried people) leave behind. The owner, 13 Nov 2026:
"please add a search for slop in future testing". Most of KanzonasPDF is written by AI agents,
so this looks for their tell-tale mistakes.

Hard findings fail the build (tests/test_slop.py runs them on every build):
  leftover   - TODO/FIXME/XXX, lorem ipsum, "as an AI", "here's the updated code", a Markdown
               code fence or a placeholder like YOUR_API_KEY in the program, its texts or the
               installer
  model      - an AI model's name or identifier in the program, its texts or the notes
  print      - a print() in the program (it has no console: output goes to the self-test log
               or a message)
  reference  - a file, module, function or class that AGENTS.md, CONTRIBUTING.md, README.md or
               docs/ROADMAP.md names but that isn't there (made up, or renamed since)

Soft findings are a report to read before a release (python tools/slop_check.py); some are
fine where they are, and the ones that aren't get fixed (and, if they can be told apart
reliably, a hard rule here):
  wording    - AI-sounding words in what users read (menus, tooltips, manuals, notes, README)
  emoji      - emoji in what users read
  swallowed  - an error caught and ignored (except ...: pass) with no comment saying why
  narrating  - a comment about the change ("# Updated to...", "# Fixed:") instead of the code
  commented  - code left in a comment
  duplicate  - two functions with the same body
  unused     - imports and variables nothing uses (pyflakes, when it's installed)

    python tools/slop_check.py            # the report; exit code 1 if anything hard is found
    python tools/slop_check.py --hard     # only the hard findings
"""
import ast
import glob
import hashlib
import io
import os
import re
import subprocess
import sys
import tokenize

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def rel(path):
    return os.path.relpath(path, ROOT).replace(os.sep, "/")


def files(*patterns):
    out = []
    for p in patterns:
        out += glob.glob(os.path.join(ROOT, p), recursive=True)
    return sorted(set(f for f in out if os.path.isfile(f) and "__pycache__" not in f))


def lines(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read().splitlines()


PROGRAM = ("kanzonas/**/*.py", "shell_ext/*.cpp", "shell_ext/*.h", "shell_ext/*.ps1",
           "installer/*.iss", "packaging/**/*.py", "run.py")
TEXTS = ("kanzonas/locale/*.po", "RELEASE_NOTES.md", "README.md")
GUIDES = ("AGENTS.md", "CONTRIBUTING.md", "README.md", "docs/ROADMAP.md")


# ---- hard ------------------------------------------------------------------------------------

_MARKER = re.compile(r"\b(TODO|FIXME|XXX)\b")     # (capitals only: "todo" is Spanish for "all")
_LEFTOVER = re.compile(
    r"lorem ipsum|\bas an AI\b|\bas a (large )?language model\b|"
    r"here'?s the (updated|complete|full|revised) (code|file|version)|"
    r"here is the (updated|complete|full|revised) (code|file|version)|"
    r"\b(YOUR|your)[_-](API|api)[_-]?(KEY|key)\b|<insert [^>]*here>|\[insert [^\]]*here\]",
    re.IGNORECASE)
_FENCE = re.compile(r"^\s*```")
# AI models' names and identifiers (CLAUDE.md is a file name, not a model)
_MODEL = re.compile(
    r"\b(claude-(opus|sonnet|haiku|fable|instant)[\w.-]*|claude[ -]\d|gpt-?[345][\w.-]*|chatgpt|"
    r"openai|anthropic|gemini[ -]\d|copilot|llama[ -]?\d|mistral[ -]large)\b",
    re.IGNORECASE)


def leftovers():
    out = []
    for path in files(*PROGRAM, *TEXTS):
        md = path.endswith(".md")
        for n, line in enumerate(lines(path), 1):
            # (this file and its test name the words they look for)
            if rel(path) in ("tools/slop_check.py",):
                continue
            m = _MARKER.search(line) or _LEFTOVER.search(line)
            if m:
                out.append(("leftover", rel(path), n, m.group(0)))
            elif not md and _FENCE.match(line):
                out.append(("leftover", rel(path), n, "```"))
    return out


def models():
    out = []
    for path in files(*PROGRAM, *TEXTS, "kanzonas/manual*.py", "CHANGELOG.md"):
        if rel(path) == "tools/slop_check.py":
            continue
        for n, line in enumerate(lines(path), 1):
            m = _MODEL.search(line)
            if m:
                out.append(("model", rel(path), n, m.group(0)))
    return out


def prints():
    out = []
    for path in files("kanzonas/**/*.py"):
        tree = ast.parse(open(path, encoding="utf-8").read(), path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and \
                    node.func.id == "print":
                out.append(("print", rel(path), node.lineno, "print()"))
    return out


# What the guides name that lives elsewhere (the Kanzonas-Site repository's brand/ folder, the
# release's assets, files the build makes, Git branches and the workflow's jobs).
_ELSEWHERE = {"make_logos.py", "SPEC.md", "brand/", "SHA256SUMS.txt", "KanzonasPDF.exe",
              "selftest.log"}


class _Code:
    """What the program defines: each module's top-level names, and each class's attributes
    (methods, class attributes and self.<name> assignments), for the guides' references."""

    def __init__(self):
        self.modules = {}       # module name -> set of top-level names
        self.classes = {}       # class name -> set of attribute names
        self.words = set()      # every name used anywhere in the code
        for path in files("kanzonas/**/*.py", "tests/**/*.py", "tools/**/*.py"):
            if rel(path) in ("tools/slop_check.py", "tests/test_slop.py"):
                continue                # (they name made-up things on purpose)
            src = open(path, encoding="utf-8").read()
            tree = ast.parse(src, path)
            if rel(path).startswith("kanzonas/"):
                name = os.path.splitext(os.path.basename(path))[0]
                top = self.modules.setdefault(name, set())
                for node in tree.body:
                    top.update(self._names(node))
                for node in ast.walk(tree):
                    if isinstance(node, ast.ClassDef):
                        attrs = self.classes.setdefault(node.name, set())
                        for item in node.body:
                            attrs.update(self._names(item))
                        for sub in ast.walk(node):
                            if isinstance(sub, ast.Attribute) and \
                                    isinstance(sub.value, ast.Name) and sub.value.id == "self":
                                attrs.add(sub.attr)
            for node in ast.walk(tree):
                if isinstance(node, ast.Name):
                    self.words.add(node.id)
                elif isinstance(node, ast.Attribute):
                    self.words.add(node.attr)
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    self.words.add(node.name)
                elif isinstance(node, ast.arg):
                    self.words.add(node.arg)
            # (names in strings too: settings keys, CSS, a workflow's names)
            self.words.update(re.findall(r"[A-Za-z_]\w*", src))
        for path in files(".github/workflows/*.yml", "shell_ext/*", "installer/*.iss"):
            self.words.update(re.findall(r"[A-Za-z_]\w*", open(path, encoding="utf-8").read()))

    @staticmethod
    def _names(node):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            return {node.name}
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            out = set()
            for t in targets:
                for sub in ast.walk(t):
                    if isinstance(sub, ast.Name):
                        out.add(sub.id)
            return out
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            return {(a.asname or a.name).split(".")[0] for a in node.names}
        if isinstance(node, (ast.If, ast.Try)):
            out = set()
            for child in ast.iter_child_nodes(node):
                if isinstance(child, ast.stmt):
                    out |= _Code._names(child)
                for h in getattr(node, "handlers", []):
                    for s in h.body:
                        out |= _Code._names(s)
            return out
        return set()


_TICKED = re.compile(r"`([^`\s]+)`")


def references():
    code = _Code()
    out = []
    for path in files(*GUIDES):
        for n, line in enumerate(lines(path), 1):
            for ref in _TICKED.findall(line):
                why = _missing(ref, code)
                if why:
                    out.append(("reference", rel(path), n, "%s (%s)" % (ref, why)))
    return out


def _missing(ref, code):
    ref = ref.rstrip(".,:;")
    if ref in _ELSEWHERE or "://" in ref or ref.startswith(("-", "$", "<", "%")):
        return None
    if "/" in ref or re.search(r"\.(py|md|txt|yml|iss|cpp|h|ps1|bat|json|po|ico|png)$", ref):
        if "*" in ref or "<" in ref or "..." in ref or ref.startswith(("~", "./", "/")):
            return None             # (a pattern, or a path on the user's computer)
        first = ref.split("/")[0]
        if "/" in ref and not os.path.exists(os.path.join(ROOT, first)):
            return None             # (a branch name, or another repository's folder)
        here = os.path.join(ROOT, ref.rstrip("/"))
        if os.path.exists(here):
            return None
        if "/" not in ref.rstrip("/"):
            # a bare file name: anywhere in the repository
            name = ref.rstrip("/")
            for _dir, dirs, names in os.walk(ROOT):
                if ".git" in _dir:
                    continue
                if name in names or name in dirs:
                    return None
        return "no such file"
    m = re.fullmatch(r"([A-Za-z_]\w*)\.([A-Za-z_]\w*)(\(\))?", ref)
    if m:
        first, attr = m.group(1), m.group(2)
        if first in code.modules:
            return None if attr in code.modules[first] else "not in kanzonas/%s.py" % first
        if first in code.classes and not _pymupdf_has(first, attr):
            return None if attr in code.classes[first] else "not in class %s" % first
        return None                 # (PyMuPDF's, Python's: not ours to check)
    m = re.fullmatch(r"[A-Za-z_]\w*(\(\))?", ref)
    if m and "_" in ref.strip("_()") or (m and ref.startswith("_")):
        name = ref.rstrip("()")
        return None if name in code.words else "not in the code"
    return None


def _pymupdf_has(name, attr):
    """True when PyMuPDF has name.attr (the guides name its Page, Document... as ours)."""
    try:
        import pymupdf
    except ImportError:
        return False
    return hasattr(getattr(pymupdf, name, None), attr)


def hard():
    return leftovers() + models() + prints() + references()


# ---- soft ------------------------------------------------------------------------------------

_WORDING = re.compile(
    r"\b(seamless(ly)?|robust(ly|ness)?|leverag(e|es|ed|ing)|delv(e|es|ing)|empower(s|ed|ing)?|"
    r"cutting-edge|game[- ]chang\w+|effortless(ly)?|elevat(e|es|ed|ing)|supercharg\w+|"
    r"streamlin(e|es|ed|ing)|harness(es|ed|ing)?|unleash\w*|revolutioni[sz]\w+|"
    r"state[- ]of[- ]the[- ]art|world[- ]class|best[- ]in[- ]class|next[- ]level|"
    r"it'?s (important|worth) (to note|noting)|in today'?s|rest assured|"
    r"a testament to|tapestry|navigat(e|ing) the (complexities|world)|look no further|"
    r"in the realm of|embark(s|ed|ing)?|holistic|synerg\w+|paradigm)\b", re.IGNORECASE)
_EMOJI = re.compile("[\U0001F300-\U0001FAFF\U0001F600-\U0001F64F⭐✨✅❌]")


def _user_texts():
    """(path, line number, text) of what users read: the program's tr() texts, the manuals,
    the catalogs' translations, the release notes and the README."""
    for path in files("kanzonas/**/*.py"):
        name = os.path.basename(path)
        tree = ast.parse(open(path, encoding="utf-8").read(), path)
        if name.startswith("manual"):
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    for k, t in enumerate(node.value.splitlines()):
                        yield path, node.lineno + k, t
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and \
                    node.func.id == "tr" and node.args and \
                    isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                yield path, node.lineno, node.args[0].value
    for path in files("kanzonas/locale/*.po"):
        for n, line in enumerate(lines(path), 1):
            if line.startswith("msgstr"):
                yield path, n, line
    for path in files("RELEASE_NOTES.md", "README.md"):
        for n, line in enumerate(lines(path), 1):
            yield path, n, line


def wording():
    out = []
    for path, n, t in _user_texts():
        for m in _WORDING.finditer(t):
            out.append(("wording", rel(path), n, m.group(0)))
    return out


def emoji():
    out = []
    for path, n, t in _user_texts():
        m = _EMOJI.search(t)
        if m:
            out.append(("emoji", rel(path), n, m.group(0)))
    return out


def _comments(path):
    """(line, column, text) of each comment in a Python file."""
    with open(path, encoding="utf-8") as f:
        src = f.read()
    try:
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type == tokenize.COMMENT:
                yield tok.start[0], tok.start[1], tok.string
    except (tokenize.TokenError, IndentationError):
        return


def swallowed():
    out = []
    for path in files("kanzonas/**/*.py"):
        text = open(path, encoding="utf-8").read()
        src = text.split("\n")
        commented = {ln for ln, _c, _t in _comments(path)}
        tree = ast.parse(text, path)
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler) and len(node.body) == 1 and \
                    isinstance(node.body[0], ast.Pass):
                # a reason on the except line, the pass line or the line above
                if not ({node.lineno, node.body[0].lineno, node.lineno - 1} & commented):
                    out.append(("swallowed", rel(path), node.lineno, src[node.lineno - 1].strip()))
    return out


_NARRATING = re.compile(
    r"#\s*(updated|changed|fixed|modified|refactored|removed|replaced|new|added)\b\s*(:|\(| - )|"
    r"#\s*(updated|changed|modified|refactored) (to|so|the|this)\b|"
    r"#\s*(this|the) (was|used to be)\b|#\s*previously\b|#\s*now (uses|does|returns|handles)\b",
    re.IGNORECASE)
_CODE_LIKE = re.compile(
    r"^#\s*((import|from|def|class|return|for|while|if|elif|else|try|except|with)\b.*[:\w)]$|"
    r"[A-Za-z_][\w.\[\]]*\s*(=|\+=|-=)\s*\S.*$|[A-Za-z_][\w.]*\(.*\)$)")


def narrating():
    out = []
    for path in files("kanzonas/**/*.py", "tools/**/*.py", "tests/**/*.py"):
        if rel(path) == "tools/slop_check.py":
            continue
        for n, _col, text in _comments(path):
            if _NARRATING.search(text):
                out.append(("narrating", rel(path), n, text.strip()[:80]))
    return out


def commented():
    out = []
    for path in files("kanzonas/**/*.py"):
        for n, _col, text in _comments(path):
            body = text.strip()
            if body.startswith("#!") or "noqa" in body or "type:" in body:
                continue
            if _CODE_LIKE.match(body) and \
                    re.search(r"\(|\[|self\.|\bimport\b|\breturn\b|==", body) and \
                    not re.search(r"\b(the|a|an|is|are|it|its)\b", body[1:]):
                try:
                    ast.parse(body.lstrip("#").strip())
                except SyntaxError:
                    continue
                out.append(("commented", rel(path), n, body[:80]))
    return out


def duplicates(min_statements=6):
    seen = {}
    out = []
    for path in files("kanzonas/**/*.py"):
        tree = ast.parse(open(path, encoding="utf-8").read(), path)
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                body = body[1:]             # (its docstring aside)
            if sum(1 for _ in ast.walk(ast.Module(body=body, type_ignores=[]))
                   if isinstance(_, ast.stmt)) < min_statements:
                continue
            key = hashlib.sha1(ast.dump(ast.Module(body=body, type_ignores=[]),
                                        annotate_fields=False).encode()).hexdigest()
            here = (rel(path), node.lineno, node.name)
            if key in seen:
                first = seen[key]
                out.append(("duplicate", here[0], here[1], "%s, the same as %s in %s:%d" % (
                    here[2], first[2], first[0], first[1])))
            else:
                seen[key] = here
    return out


def unused():
    try:
        r = subprocess.run([sys.executable, "-m", "pyflakes", "kanzonas"], cwd=ROOT,
                           capture_output=True, text=True, timeout=300)
    except (OSError, subprocess.TimeoutExpired):
        return []
    if "No module named pyflakes" in r.stderr:
        return [("unused", "-", 0, "pyflakes isn't installed (pip install pyflakes)")]
    out = []
    for line in r.stdout.splitlines():
        m = re.match(r"(.+?):(\d+):\d+:? (.*(unused|never used|redefinition of unused).*)", line)
        if m:
            out.append(("unused", rel(os.path.join(ROOT, m.group(1))), int(m.group(2)),
                        m.group(3)))
    return out


def soft():
    return wording() + emoji() + swallowed() + narrating() + commented() + duplicates() + \
        unused()


def report(findings, title):
    print("== %s: %d" % (title, len(findings)))
    kinds = {}
    for f in findings:
        kinds.setdefault(f[0], []).append(f)
    for kind, items in kinds.items():
        print("-- %s (%d)" % (kind, len(items)))
        for _k, path, n, what in items:
            print("   %s:%d  %s" % (path, n, what))


def main(argv):
    found = hard()
    report(found, "hard (these fail the build)")
    if "--hard" not in argv:
        report(soft(), "soft (read before a release)")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
