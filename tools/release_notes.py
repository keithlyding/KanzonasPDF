"""The short notes for one version from RELEASE_NOTES.md, as the block a GitHub release's text
carries. KanzonasPDF's update box reads that block from every release newer than the copy
that's running and shows them, so people see what changed since their version.

    python tools/release_notes.py 1.5                    print the block
    python tools/release_notes.py 1.5 --github-output    add it to $GITHUB_OUTPUT as "notes"
    python tools/release_notes.py 1.5 --published FILE   with the notes of skipped versions

A version that was never published (its build was stopped, or a newer one merged first, as
1.13.1 on 12 Nov 2026) has its notes carried into the next release: --published names a
file listing the published releases' tags, one per line (gh release list), and every version
in RELEASE_NOTES.md between the newest of them and this one gets its own blocks, marked with
its number (v=1.13.1), after this version's. Copies of KanzonasPDF before 1.15 read only the
unmarked blocks, as before; newer ones list each skipped version as its own entry.

Exits with 1 when RELEASE_NOTES.md has no notes for that version (the Windows build fails).
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEADING = re.compile(r"^## +v?(\d+(?:\.\d+)*)(?: +\((\w+)\))? *$", re.M)


def sections(text):
    """{(version, language): notes}: the English notes under '## 1.5', a translation under
    '## 1.5 (es)'."""
    out = {}
    marks = list(HEADING.finditer(text))
    for k, m in enumerate(marks):
        end = marks[k + 1].start() if k + 1 < len(marks) else len(text)
        out[(m.group(1), m.group(2) or "en")] = text[m.end():end].strip()
    return out


def block(text, version, carried=False):
    """The release-text block for version (each language in its own marked part), or None;
    carried: marked with its number, as a skipped version's notes in a later release."""
    found = {lang: notes for (v, lang), notes in sections(text).items() if v == version and notes}
    if "en" not in found:
        return None
    parts = []
    for lang in ["en"] + sorted(k for k in found if k != "en"):
        tag = "" if lang == "en" else " lang=" + lang
        if carried:
            tag += " v=" + version
        parts.append("<!-- kanzonas-notes%s -->\n%s\n<!-- /kanzonas-notes -->" % (tag, found[lang]))
    return "\n".join(parts)


def _key(version):
    return tuple(int(x) for x in version.split("."))


def skipped(text, version, published):
    """The versions in RELEASE_NOTES.md newer than every published one and older than version,
    oldest first: those whose release never came. published: their numbers ("1.14.2"); none
    known, nothing is taken as skipped."""
    done = {p.strip().lstrip("vV") for p in published if p.strip()}
    done = {d for d in done if d.replace(".", "").isdigit()}
    if not done:
        return []
    newest = max(_key(d) for d in done)
    here = _key(version)
    found = {v for (v, _lang) in sections(text)}
    return sorted((v for v in found if newest < _key(v) < here and v not in done), key=_key)


def with_skipped(text, version, published):
    """This version's block, then each skipped version's (headed for people reading the
    release page), or None when this version has no notes."""
    own = block(text, version)
    if own is None:
        return None
    parts = [own]
    for v in skipped(text, version, published):
        b = block(text, v, carried=True)
        if b:
            parts.append("**Also in this release: %s** (it wasn't released on its own)\n%s" % (v, b))
    return "\n\n".join(parts)


def main(argv):
    version = argv[1]
    published = []
    if "--published" in argv:
        path = argv[argv.index("--published") + 1]
        try:
            with open(path, encoding="utf-8") as f:
                published = f.read().split()
        except OSError:
            published = []          # (unknown: no version is taken as skipped)
    with open(os.path.join(ROOT, "RELEASE_NOTES.md"), encoding="utf-8") as f:
        text = with_skipped(f.read(), version, published)
    if text is None:
        print("RELEASE_NOTES.md has no notes for %s" % version, file=sys.stderr)
        return 1
    if "--github-output" in argv:
        import uuid
        end = "KZ_NOTES_END_" + uuid.uuid4().hex     # (never a line of the notes)
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
            f.write("notes<<%s\n%s\n%s\n" % (end, text, end))
    else:
        sys.stdout.reconfigure(encoding="utf-8")
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
