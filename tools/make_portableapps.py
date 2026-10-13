"""Lay out KanzonasPDF in the PortableApps.com Format (for portableapps.com), from the
built program in dist/KanzonasPDF:

    KanzonasPDFPortable/
      App/KanzonasPDF/          the program, with portable.txt pointing its data at Data/
      App/AppInfo/              appinfo.ini and icons
      App/AppInfo/Launcher/     KanzonasPDFPortable.ini (for the PortableApps.com Launcher)
      Other/Source/             license and where the source is
      help.html

Two steps need PortableApps.com's own Windows tools and are done by hand (see help in
docs/portableapps.md): the PortableApps.com Launcher Generator makes KanzonasPDFPortable.exe
from the launcher ini, and the PortableApps.com Installer makes the .paf.exe.

    python tools/make_portableapps.py VERSION [DIST] [OUT]
"""
import os
import shutil
import sys

APP_ID = "KanzonasPDFPortable"
HOME = "https://github.com/keithlyding/KanzonasPDF"


def package_version(v):
    """'0.91.1' -> '0.91.1.0' (PortableApps.com wants four numbers)."""
    parts = [p for p in v.split(".") if p.isdigit()][:4]
    return ".".join(parts + ["0"] * (4 - len(parts)))


APPINFO = """[Format]
Type=PortableApps.comFormat
Version=3.9

[Details]
Name=KanzonasPDF Portable
AppID={app_id}
Publisher=KanzonasPDF
Homepage={home}
Category=Office
Description=Free PDF reader and editor: markups, measuring, forms, signing and editing
Language=English

[License]
Shareable=true
OpenSource=true
Freeware=true
CommercialUse=true

[Version]
PackageVersion={package}
DisplayVersion={display}

[Dependencies]
Requires64bitOS=yes

[Control]
Icons=1
Start={app_id}.exe

[Associations]
FileTypes=pdf
"""

LAUNCHER = """[Launch]
ProgramExecutable=KanzonasPDF\\KanzonasPDF.exe
DirectoryMoveOK=yes
SupportsUNC=yes
"""

PORTABLE_TXT = """KanzonasPDF portable (PortableApps.com Format)

Because this file is here, KanzonasPDF keeps its settings, signatures, stamp images and
certificate in the package's Data folder, not in the registry or user folders. The
PortableApps.com Platform updates it, so its own updater is off.
data=..\\..\\Data
updates=off
"""

HELP = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>KanzonasPDF Portable</title></head>
<body style="font-family: Segoe UI, Arial, sans-serif; max-width: 40em; margin: 2em auto">
<h1>KanzonasPDF Portable</h1>
<p>A free PDF reader and editor: markups, measuring, forms, signing and editing a PDF's own
text and pictures. Version {display}.</p>
<p>Run <b>{app_id}.exe</b>. Your settings and files stay in the <b>Data</b> folder of this
package. The user manual is in the program (Help &gt; User manual, F1).</p>
<p>Free software under the GNU AGPL 3.0. Source code and issues:
<a href="{home}">{home}</a>.</p>
</body></html>
"""


def icons(src_png, dest):
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QGuiApplication, QImage
    app = QGuiApplication.instance() or QGuiApplication([])  # noqa: F841 (needed for QImage)
    img = QImage(src_png)
    if img.isNull():
        raise SystemExit("can't read " + src_png)
    for size in (16, 32, 75, 128, 256):
        out = img.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        out.save(os.path.join(dest, f"appicon_{size}.png"))


def build(version, dist="dist/KanzonasPDF", out="KanzonasPDFPortable", root="."):
    if os.path.exists(out):
        shutil.rmtree(out)
    info = os.path.join(out, "App", "AppInfo")
    os.makedirs(os.path.join(info, "Launcher"))
    os.makedirs(os.path.join(out, "Other", "Source"))
    shutil.copytree(dist, os.path.join(out, "App", "KanzonasPDF"))
    with open(os.path.join(out, "App", "KanzonasPDF", "portable.txt"), "w") as f:
        f.write(PORTABLE_TXT)
    fields = {"app_id": APP_ID, "home": HOME, "display": version,
              "package": package_version(version)}
    with open(os.path.join(info, "appinfo.ini"), "w", newline="\r\n") as f:
        f.write(APPINFO.format(**fields))
    with open(os.path.join(info, "Launcher", APP_ID + ".ini"), "w", newline="\r\n") as f:
        f.write(LAUNCHER)
    with open(os.path.join(out, "help.html"), "w", encoding="utf-8") as f:
        f.write(HELP.format(**fields))
    # 256-color and true-color sizes, as the format asks (tools/make_paf_icon.py)
    shutil.copy(os.path.join(root, "assets", "portableapps-appicon.ico"),
                os.path.join(info, "appicon.ico"))
    icons(os.path.join(root, "assets", "kanzonas.png"), info)
    for name in ("LICENSE", "README.md"):
        if os.path.exists(os.path.join(root, name)):
            shutil.copy(os.path.join(root, name), os.path.join(out, "Other", "Source"))
    with open(os.path.join(out, "Other", "Source", "Source.txt"), "w") as f:
        f.write("Complete source code: " + HOME + "\n")
    return out


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        raise SystemExit(__doc__)
    print(build(*args))
