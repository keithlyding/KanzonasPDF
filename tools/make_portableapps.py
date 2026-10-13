"""Lay out KanzonasPDF in the PortableApps.com Format (for portableapps.com), from the
built program in dist/KanzonasPDF:

    KanzonasPDFPortable/
      App/KanzonasPDF/          the program, with portable.txt pointing its data at Data/
      App/AppInfo/              appinfo.ini and icons
      App/AppInfo/Launcher/     KanzonasPDFPortable.ini (for the PortableApps.com Launcher)
      Other/Source/             license, Readme.txt (source, launcher options), example user INI
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
<html lang="en"><head><meta charset="utf-8"><title>KanzonasPDF Portable Help</title></head>
<body style="font-family: Segoe UI, Arial, sans-serif; max-width: 44em; margin: 2em auto">
<h1>KanzonasPDF Portable Help</h1>
<p>KanzonasPDF Portable is a free PDF reader and editor: markups, measuring, forms, signing and
editing a PDF's own text and pictures. Version {display}. It's packaged with a PortableApps.com
launcher as a <a href="https://portableapps.com/about/what_is_a_portable_app">portable app</a>,
so you can use it from a cloud folder, portable drive, or local folder without needing to
install it on each PC. <a href="{home}">Learn more about KanzonasPDF...</a></p>
<p>Run <b>{app_id}.exe</b>. Your settings, signatures and stamps stay in the <b>Data</b> folder
of this package. The user manual is in the program (Help &gt; User manual, F1).</p>
<ul><li><a href="https://portableapps.com/donate">Support PortableApps.com's Hosting and
Development</a></li></ul>
<p><a href="{home}">Go to the KanzonasPDF Portable Homepage &gt;&gt;</a></p>
<p><a href="https://portableapps.com/">Get more portable apps at PortableApps.com</a></p>
<p>This software is OSI Certified Open Source Software (GNU AGPL 3.0). OSI Certified is a
certification mark of the Open Source Initiative.</p>
<h2>Portable App Issues</h2>
<ul>
<li><a href="https://portableapps.com/support/portable_app#downloading">Downloading a Portable App</a></li>
<li><a href="https://portableapps.com/support/portable_app#installing">Installing a Portable App</a></li>
<li><a href="https://portableapps.com/support/portable_app#using">Using a Portable App</a></li>
<li><a href="https://portableapps.com/support/portable_app#upgrading">Upgrading a Portable App</a></li>
</ul>
<p>You can read about advanced configuration options for the PortableApps.com Launcher in its
<a href="Other/Source/Readme.txt">readme file</a>.</p>
</body></html>
"""

# Other/Source/Readme.txt and the example user INI, from the PortableApps.com Application
# Template 3.7.1, filled in for KanzonasPDF
README_TXT = """The base application's source code is available from the portable app's
homepage listed in the help.html file: {home}

Details of most other things are available there as well.

LICENSE
=======

KanzonasPDF is released under the GNU AGPL 3.0 (LICENSE in this directory). This package's
installer and launcher are released under the GPL. The launcher is the PortableApps.com
Launcher, available with full source and documentation from
https://portableapps.com/development. We request that developers using the PortableApps.com
Launcher please leave this directory intact and unchanged.

USER CONFIGURATION
==================

Some configuration in the PortableApps.com Launcher can be overridden by the user in an INI
file next to {app_id}.exe called {app_id}.ini. There is an example INI included with this
package to get you started. To use it, copy {app_id}.ini from this directory next to
{app_id}.exe. The options in the INI file are as follows:

  AdditionalParameters=
  DisableSplashScreen=false
  RunLocally=false

(There is no need for an INI header in this file; if you have one, though, it won't damage
anything.)

The AdditionalParameters entry allows you to pass additional command-line parameters to the
application.

The DisableSplashScreen entry allows you to run the launcher without the splash screen
showing up. The default is false.

The RunLocally entry allows you to run the portable application from a read-only medium.
This is known as Live mode. It copies what it needs to to a temporary directory on the host
computer, runs the application, and then deletes it afterwards, leaving nothing behind. This
can be useful for running the application from a CD or if you work on a computer that may
have spyware or viruses and you'd like to keep your device set to read-only. As a consequence
of this technique, any changes you make during the Live mode session aren't saved back to
your device. The default is false.
"""

USER_INI = """[{app_id}]
AdditionalParameters=
DisableSplashScreen=false
RunLocally=false
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
    src = os.path.join(out, "Other", "Source")
    with open(os.path.join(src, "Readme.txt"), "w", newline="\r\n") as f:
        f.write(README_TXT.format(**fields))
    with open(os.path.join(src, APP_ID + ".ini"), "w", newline="\r\n") as f:
        f.write(USER_INI.format(**fields))
    return out


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        raise SystemExit(__doc__)
    print(build(*args))
