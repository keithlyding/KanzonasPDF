"""PyMuPDF for Intel Macs (the macos job's x86_64 build runs it before installing).

PyMuPDF 2.0 is two parts on PyPI: pymupdf-lite, the PDF engine (MuPDF and the `pymupdf`
module KanzonasPDF uses), and add-ons for AI text extraction (pymupdf-layout, pymupdf4llm)
that need ONNX Runtime 1.24 or newer. The `pymupdf` package ties them together, and has no
Intel Mac build, because those ONNX Runtime versions have none. KanzonasPDF doesn't use the
add-ons (the builds leave pymupdf.layout out), so on Intel Macs this makes a stand-in
`pymupdf` wheel of the version pinned in constraints.txt that only asks for pymupdf-lite of
the same version: the same engine, from the same source release, as every other build.
Libraries that ask for PyMuPDF (pdf2docx) are then satisfied without building it from source.

    python packaging/macos/pymupdf_standin.py WHEEL_FOLDER
    python -m pip install --find-links WHEEL_FOLDER -r requirements.txt -c constraints.txt

The wheel has no files of its own: only its name, version and that one requirement.
"""
import base64
import hashlib
import os
import re
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))


def pinned(name, path=None):
    """The version of name pinned in constraints.txt (the line without an environment
    marker, or the one for Intel Macs)."""
    path = path or os.path.join(ROOT, "constraints.txt")
    found = None
    with open(path, encoding="utf-8") as f:
        for line in f:
            m = re.match(r"\s*([A-Za-z0-9_.-]+)==([^\s#;]+)", line)
            if m and m.group(1).lower().replace("_", "-") == name:
                found = m.group(2)
    if not found:
        raise SystemExit(f"{name} isn't pinned in constraints.txt")
    return found


def _record_line(name, data):
    digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
    return f"{name},sha256={digest},{len(data)}"


def make_wheel(folder, version, engine_version=None):
    """Write pymupdf-<version>-py3-none-any.whl into folder; returns its path."""
    engine_version = engine_version or version
    info = f"pymupdf-{version}.dist-info"
    files = {
        f"{info}/METADATA": (
            "Metadata-Version: 2.1\n"
            "Name: pymupdf\n"
            f"Version: {version}\n"
            "Summary: Stand-in for PyMuPDF on Intel Macs: the engine is pymupdf-lite "
            "(KanzonasPDF's macOS build)\n"
            "License: AGPL-3.0\n"
            "Requires-Python: >=3.11\n"
            f"Requires-Dist: pymupdf-lite=={engine_version}\n").encode(),
        f"{info}/WHEEL": (
            "Wheel-Version: 1.0\n"
            "Generator: kanzonaspdf-packaging\n"
            "Root-Is-Purelib: true\n"
            "Tag: py3-none-any\n").encode(),
    }
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"pymupdf-{version}-py3-none-any.whl")
    record = [_record_line(n, d) for n, d in files.items()] + [f"{info}/RECORD,,"]
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for n, d in files.items():
            z.writestr(n, d)
        z.writestr(f"{info}/RECORD", "\n".join(record) + "\n")
    return path


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        raise SystemExit("usage: pymupdf_standin.py WHEEL_FOLDER")
    version = pinned("pymupdf")
    engine = pinned("pymupdf-lite")
    if engine != version:
        raise SystemExit(f"pymupdf-lite is pinned at {engine}, pymupdf at {version}: "
                         "pin both at the same version in constraints.txt")
    print(make_wheel(argv[0], version, engine))


if __name__ == "__main__":
    main()
