"""The short notes for one version from RELEASE_NOTES.md, as the block a GitHub release's text
carries. KanzonasPDF's update box reads that block from every release newer than the copy
that's running and shows them, so people see what changed since their version.

    python tools/release_notes.py 1.5                    print the block
    python tools/release_notes.py 1.5 --github-output    add it to $GITHUB_OUTPUT as "notes"

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


def block(text, version):
    """The release-text block for version (each language in its own marked part), or None."""
    found = {lang: notes for (v, lang), notes in sections(text).items() if v == version and notes}
    if "en" not in found:
        return None
    parts = []
    for lang in ["en"] + sorted(k for k in found if k != "en"):
        tag = "" if lang == "en" else " lang=" + lang
        parts.append("<!-- kanzonas-notes%s -->\n%s\n<!-- /kanzonas-notes -->" % (tag, found[lang]))
    return "\n".join(parts)


def main(argv):
    version = argv[1]
    with open(os.path.join(ROOT, "RELEASE_NOTES.md"), encoding="utf-8") as f:
        text = block(f.read(), version)
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
