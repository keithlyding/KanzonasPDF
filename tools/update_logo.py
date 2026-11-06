"""Take KanzonasPDF's logo from Kanzonas-Site, the single source of truth for every Kanzonas logo.

The logo (Help > About) is made in https://github.com/keithlyding/Kanzonas-Site by
brand/make_logos.py; it is never drawn or edited here. To bring in a new one, after it's committed
there:

    python tools/update_logo.py <Kanzonas-Site commit>

It downloads brand/out/kanzonas-logo-source.png at that commit (a full 40-character commit, so the
result can't change later), checks it's a 936 x 325 PNG, writes it to
assets/kanzonas-logo-source.png and into kanzonas/branding_data.py (the LOGO part only: the icons
are left as they are), and records where it came from in assets/LOGO_SOURCE.txt.
tests/test_logo_source.py checks those three agree, so a logo edited here by hand fails the build.
A new logo is a user-facing change: version, CHANGELOG and release notes as AGENTS.md says.

    python tools/update_logo.py --check     # is this copy the one the record names? (no download)
"""
import base64
import hashlib
import os
import re
import struct
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = "keithlyding/Kanzonas-Site"
SITE_PATH = "brand/out/kanzonas-logo-source.png"
LOGO = os.path.join(ROOT, "assets", "kanzonas-logo-source.png")
RECORD = os.path.join(ROOT, "assets", "LOGO_SOURCE.txt")
BRANDING = os.path.join(ROOT, "kanzonas", "branding_data.py")
SIZE = (936, 325)
MAX_BYTES = 4 * 1024 * 1024


def png_size(data):
    """(width, height) of PNG bytes; ValueError when they aren't a PNG."""
    if data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        raise ValueError("not a PNG file")
    return struct.unpack(">II", data[16:24])


def read_record():
    """{"commit": ..., "path": ..., "sha256": ...} from assets/LOGO_SOURCE.txt."""
    out = {}
    with open(RECORD, encoding="utf-8") as f:
        for line in f:
            m = re.match(r"(\w+):\s*(\S+)", line)
            if m:
                out[m.group(1)] = m.group(2)
    return out


def branding_with_logo(text, data):
    """branding_data.py's text with its LOGO replaced by data (written as tools_make_assets.py
    writes it), everything before LOGO kept byte for byte."""
    i = text.index("LOGO = base64.b64decode(\n")
    b64 = base64.b64encode(data).decode()
    block = "\n".join(f'    "{b64[k:k + 96]}"' for k in range(0, len(b64), 96))
    return text[:i] + f"LOGO = base64.b64decode(\n{block}\n)\n"


def check():
    """Problems with this copy (empty when the logo, branding_data and the record agree)."""
    problems = []
    rec = read_record()
    data = open(LOGO, "rb").read()
    if hashlib.sha256(data).hexdigest() != rec.get("sha256"):
        problems.append("assets/kanzonas-logo-source.png isn't the file assets/LOGO_SOURCE.txt "
                        "names: logos come from Kanzonas-Site (tools/update_logo.py)")
    ns = {}
    exec(compile(open(BRANDING, encoding="utf-8").read(), BRANDING, "exec"), ns)
    if ns["LOGO"] != data:
        problems.append("kanzonas/branding_data.py's LOGO isn't assets/kanzonas-logo-source.png")
    if png_size(data) != SIZE:
        problems.append("the logo isn't %d x %d" % SIZE)
    return problems


def update(commit):
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise SystemExit("give the full 40-character Kanzonas-Site commit (git rev-parse HEAD)")
    url = f"https://raw.githubusercontent.com/{SITE}/{commit}/{SITE_PATH}"
    with urllib.request.urlopen(url, timeout=60) as r:
        data = r.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise SystemExit("the download is too big for a logo")
    if png_size(data) != SIZE:
        raise SystemExit("the logo at that commit isn't %d x %d" % SIZE)
    with open(LOGO, "wb") as f:
        f.write(data)
    text = open(BRANDING, encoding="utf-8").read()
    with open(BRANDING, "w", encoding="utf-8", newline="\n") as f:
        f.write(branding_with_logo(text, data))
    with open(RECORD, "w", encoding="utf-8", newline="\n") as f:
        f.write("# KanzonasPDF's logo comes from Kanzonas-Site, the single source of truth for every\n"
                "# Kanzonas logo. Written by tools/update_logo.py: don't edit by hand.\n"
                f"repo: https://github.com/{SITE}\n"
                f"commit: {commit}\n"
                f"path: {SITE_PATH}\n"
                f"sha256: {hashlib.sha256(data).hexdigest()}\n")
    problems = check()
    if problems:
        raise SystemExit("\n".join(problems))
    print("logo updated from %s at %s" % (SITE, commit[:7]))


if __name__ == "__main__":
    if sys.argv[1:] == ["--check"]:
        found = check()
        print("\n".join(found) or "the logo is Kanzonas-Site's (as assets/LOGO_SOURCE.txt records)")
        sys.exit(1 if found else 0)
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    update(sys.argv[1])
