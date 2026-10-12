"""Weekly security check (.github/workflows/security-check.yml): lists newer releases of the
libraries that read untrusted files (PyMuPDF / MuPDF reads every PDF; Qt reads pictures)
than the versions pinned in constraints.txt. MuPDF's security fixes often aren't filed as
PyPI advisories, so pip-audit alone can miss them: a new PyMuPDF release is the signal.

    python tools/check_dependencies.py      # prints a Markdown report; exit 1 when outdated
"""
import json
import re
import sys
import urllib.request

WATCH = ("pymupdf", "PySide6")       # parse documents and images from strangers


def pinned(path="constraints.txt"):
    out = {}
    for line in open(path, encoding="utf-8"):
        m = re.match(r"\s*([A-Za-z0-9_.-]+)==([^\s#]+)", line)
        if m:
            out[m.group(1).lower()] = m.group(2)
    return out


def key(v):
    return tuple(int(x) if x.isdigit() else 0 for x in re.split(r"[.+-]", v))


def latest(name):
    with urllib.request.urlopen(f"https://pypi.org/pypi/{name}/json", timeout=30) as r:
        return json.load(r)["info"]["version"]


def main():
    pins = pinned()
    rows = []
    for name in WATCH:
        have = pins.get(name.lower())
        new = latest(name)
        if have and key(new) > key(have):
            rows.append(f"- **{name}**: pinned {have}, newest {new} "
                        f"(https://pypi.org/project/{name}/{new}/)")
    if rows:
        print("Newer versions of libraries that read untrusted files:\n")
        print("\n".join(rows))
        print("\nRead their release notes for security fixes; bump the line in constraints.txt "
              "on a branch and let the Windows build test it.")
        return 1
    print("The libraries that read untrusted files are up to date.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
